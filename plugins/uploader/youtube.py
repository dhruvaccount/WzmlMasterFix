import asyncio
import logging
import os
import time
from typing import Any, Optional

from plugins.base import UploaderPlugin, PluginContext, PluginResult
from core.exceptions import PluginExecutionError

logger = logging.getLogger("wzml.youtube_uploader")


class YouTubeUploader(UploaderPlugin):
    name = "youtube"
    plugin_type = "uploader"

    def __init__(self):
        self._credentials = None
        self._service = None

    async def initialize(self, credentials_path: str = None) -> bool:
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            if credentials_path and os.path.exists(credentials_path):
                self._credentials = (
                    service_account.Credentials.from_service_account_file(
                        credentials_path,
                        scopes=[
                            "https://www.googleapis.com/auth/youtube.upload",
                        ],
                    )
                )
                self._service = build(
                    "youtube",
                    "v3",
                    credentials=self._credentials,
                    cache_discovery=False,
                )
                logger.info("YouTube uploader initialized")
                return True
            else:
                logger.warning(
                    "No valid credentials_path provided for YouTube uploader"
                )
                return False
        except Exception as e:
            logger.error(f"YouTube init error: {e}")
            return False

    def _get_service(self):
        from googleapiclient.discovery import build

        if self._service:
            return self._service
        if self._credentials:
            return build(
                "youtube", "v3", credentials=self._credentials, cache_discovery=False
            )
        raise Exception("No YouTube credentials configured")

    async def upload(self, context: PluginContext, config: dict) -> PluginResult:
        video_path = context.source
        title = config.get("title", os.path.basename(video_path))
        description = config.get("description", "")
        category_id = config.get("category_id", "22")
        tags = config.get("tags", [])
        privacy = config.get("privacy", "private")

        if not os.path.exists(video_path):
            return PluginResult(success=False, error="File not found")

        try:
            from googleapiclient.http import MediaFileUpload
            from core.task import update_task_progress, _task_store

            service = self._get_service()
            file_size = os.path.getsize(video_path)

            snippet = {
                "categoryId": category_id,
                "title": title,
                "description": description,
                "tags": tags,
            }

            body = {
                "snippet": snippet,
                "status": {"privacyStatus": privacy},
            }

            media = MediaFileUpload(
                video_path, chunksize=10 * 1024 * 1024, resumable=True
            )

            request = service.videos().insert(
                part=",".join(body.keys()), body=body, media_body=media
            )

            response = None
            start_time = time.time()
            last_update = start_time

            while response is None:
                t = _task_store.get(context.task_id)
                if t and t.status.value == "cancelled":
                    raise Exception("Task cancelled by user")

                status, response = await asyncio.to_thread(request.next_chunk)
                if status:
                    current = int(status.resumable_progress)
                    total = int(status.total_size)

                    now = time.time()
                    if now - last_update > 1.0:
                        speed = current / (now - start_time) if now > start_time else 0
                        eta = (
                            int((total - current) / speed) if speed > 0 and total else 0
                        )
                        pct = (current / total) * 100 if total else 0.0

                        asyncio.create_task(
                            update_task_progress(
                                task_id=context.task_id,
                                stage="Uploading to YouTube",
                                plugin=self.name,
                                progress=pct,
                                speed=speed,
                                eta=eta,
                                uploaded=current,
                                total=total,
                            )
                        )
                        last_update = now

            video_id = response.get("id")
            video_url = f"https://youtube.com/watch?v={video_id}"

            result = {
                "id": video_id,
                "title": title,
                "url": video_url,
                "size": file_size,
            }

            return PluginResult(
                success=True,
                output_path=video_url,
                metadata=result,
            )

        except Exception as e:
            logger.error(f"YouTube upload error: {e}")
            return PluginResult(success=False, error=str(e))

    async def get_video(self, video_id: str) -> dict:
        try:
            service = self._get_service()
            result = await asyncio.to_thread(
                service.videos().list(part="snippet,statistics", id=video_id).execute
            )
            items = result.get("items", [])
            if items:
                return items[0]
            return {}
        except Exception as e:
            logger.error(f"YouTube get video error: {e}")
            return {}

    async def update_video(self, video_id: str, updates: dict) -> bool:
        try:
            service = self._get_service()
            video = await self.get_video(video_id)
            if not video:
                return False

            snippet = video.get("snippet", {})
            if "title" in updates:
                snippet["title"] = updates["title"]
            if "description" in updates:
                snippet["description"] = updates["description"]
            if "tags" in updates:
                snippet["tags"] = updates["tags"]
            if "categoryId" in updates:
                snippet["categoryId"] = updates["categoryId"]

            body = {"id": video_id, "snippet": snippet}
            await asyncio.to_thread(
                service.videos().update(part="snippet", body=body).execute
            )
            return True
        except Exception as e:
            logger.error(f"YouTube update error: {e}")
            return False

    async def delete_video(self, video_id: str) -> bool:
        try:
            service = self._get_service()
            await asyncio.to_thread(service.videos().delete(id=video_id).execute)
            return True
        except Exception as e:
            logger.error(f"YouTube delete error: {e}")
            return False

    async def set_thumbnail(self, video_id: str, image_path: str) -> bool:
        try:
            service = self._get_service()
            await asyncio.to_thread(
                service.thumbnails()
                .set(videoId=video_id, media_body=image_path)
                .execute
            )
            return True
        except Exception as e:
            logger.error(f"YouTube thumbnail error: {e}")
            return False
