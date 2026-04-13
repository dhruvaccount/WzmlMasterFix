import asyncio
import logging
import os
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
            from googleapiclient.http import MediaFileUpload

            if credentials_path:
                self._credentials = (
                    service_account.Credentials.from_service_account_file(
                        credentials_path,
                        scopes=[
                            "https://www.googleapis.com/auth/youtube.upload",
                            "https://www.googleapis.com/auth/youtube.force-ssl",
                        ],
                    )
                )
                self._service = build(
                    "youtube",
                    "v3",
                    credentials=self._credentials,
                    discoveryServiceName="youtube",
                    discoveryApiVersion="v3",
                )
                logger.info("YouTube uploader initialized")
                return True
            else:
                logger.warning("No credentials provided")
                return False
        except Exception as e:
            logger.error(f"YouTube init error: {e}")
            return False

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

            snippet = {
                "title": title,
                "description": description,
                "categoryId": category_id,
                "tags": tags,
            }

            if tags:
                snippet["tags"] = tags

            status = {"privacyStatus": privacy}

            body = {
                "snippet": snippet,
                "status": status,
            }

            media = MediaFileUpload(
                video_path, chunksize=1 * 1024 * 1024, resumable=True
            )

            request = self._service.videos().insert(
                part=",".join(body.keys()), body=body, media_body=media
            )

            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    logger.info(f"Upload progress: {int(status.progress() * 100)}%")

            video_id = response.get("id")
            video_url = f"https://youtube.com/watch?v={video_id}"

            result = {
                "video_id": video_id,
                "url": video_url,
                "title": title,
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
            response = (
                self._service.videos()
                .list(part="snippet,statistics,contentDetails", id=video_id)
                .execute()
            )

            if response.get("items"):
                return response["items"][0]
            return {}

        except Exception as e:
            logger.error(f"YouTube get video error: {e}")
            return {}

    async def update_video(
        self,
        video_id: str,
        title: str = None,
        description: str = None,
        tags: list = None,
    ) -> dict:
        try:
            snippet = {}
            if title:
                snippet["title"] = title
            if description:
                snippet["description"] = description
            if tags:
                snippet["tags"] = tags

            body = {
                "id": video_id,
                "snippet": snippet,
            }

            response = (
                self._service.videos().update(part="snippet", body=body).execute()
            )

            return response

        except Exception as e:
            logger.error(f"YouTube update error: {e}")
            return {}

    async def delete_video(self, video_id: str) -> bool:
        try:
            self._service.videos().delete(id=video_id).execute()
            return True
        except Exception as e:
            logger.error(f"YouTube delete error: {e}")
            return False

    async def list_videos(self, mine: bool = True) -> list:
        try:
            response = (
                self._service.mine()
                .list(part="snippet,contentDetails,statistics", mine=True)
                .execute()
            )

            return response.get("items", [])
        except Exception as e:
            logger.error(f"YouTube list error: {e}")
            return []

    async def get_categories(self) -> list:
        try:
            response = (
                self._service.videoCategories()
                .list(part="snippet", regionCode="US")
                .execute()
            )

            return [
                {"id": c["id"], "title": c["snippet"]["title"]}
                for c in response.get("items", [])
            ]
        except Exception as e:
            logger.error(f"YouTube categories error: {e}")
            return []

    async def set_thumbnail(self, video_id: str, thumbnail_path: str) -> dict:
        try:
            from googleapiclient.http import MediaFileUpload

            media = MediaFileUpload(thumbnail_path)

            result = (
                self._service.thumbnails()
                .set(videoId=video_id, media_body=media)
                .execute()
            )

            return result
        except Exception as e:
            logger.error(f"YouTube thumbnail error: {e}")
            return {}

    async def get_my_channel(self) -> dict:
        try:
            response = (
                self._service.channels()
                .list(part="snippet,contentDetails,statistics", mine=True)
                .execute()
            )

            if response.get("items"):
                return response["items"][0]
            return {}
        except Exception as e:
            logger.error(f"YouTube channel error: {e}")
            return {}
