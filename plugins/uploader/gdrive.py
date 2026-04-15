import asyncio
import logging
import os
import time
from typing import Any, Optional

from plugins.base import UploaderPlugin, PluginContext, PluginResult

logger = logging.getLogger("wzml.gdrive_uploader")


class GDriveUploader(UploaderPlugin):
    name = "gdrive"
    plugin_type = "uploader"

    def __init__(self):
        self._credentials = None
        self._service = None
        self._folder_id = "root"

    async def initialize(self, credentials_path: str = None) -> bool:
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            if credentials_path and os.path.exists(credentials_path):
                self._credentials = (
                    service_account.Credentials.from_service_account_file(
                        credentials_path,
                        scopes=[
                            "https://www.googleapis.com/auth/drive",
                        ],
                    )
                )
                self._service = build(
                    "drive", "v3", credentials=self._credentials, cache_discovery=False
                )
                logger.info("GDrive uploader initialized with service account")
                return True
            else:
                # Optionally allow initialization without service account if using a different method or relying on user passing config
                logger.warning("No valid credentials_path provided for GDrive uploader")
                return False
        except Exception as e:
            logger.error(f"GDrive init error: {e}")
            return False

    def set_credentials(self, credentials):
        self._credentials = credentials

    def _get_service(self):
        from googleapiclient.discovery import build

        if self._service:
            return self._service
        if self._credentials:
            return build(
                "drive", "v3", credentials=self._credentials, cache_discovery=False
            )
        raise Exception("No GDrive credentials configured")

    async def upload(self, context: PluginContext, config: dict) -> PluginResult:
        file_path = context.source
        folder_id = config.get("folder_id", self._folder_id)

        if not os.path.exists(file_path):
            return PluginResult(success=False, error="File not found")

        try:
            from googleapiclient.http import MediaFileUpload
            from core.task import update_task_progress, _task_store

            service = self._get_service()
            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)

            metadata = {"name": file_name, "parents": [folder_id] if folder_id else []}

            media = MediaFileUpload(
                file_path,
                resumable=True,
                chunksize=10 * 1024 * 1024,  # 10MB chunks
            )

            request = service.files().create(
                body=metadata, media_body=media, fields="id,name,webViewLink"
            )

            response = None
            start_time = time.time()
            last_update = start_time

            while response is None:
                # Check task cancellation
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
                                stage="Uploading",
                                plugin=self.name,
                                progress=pct,
                                speed=speed,
                                eta=eta,
                                uploaded=current,
                                total=total,
                            )
                        )
                        last_update = now

            result = {
                "id": response.get("id"),
                "name": response.get("name"),
                "url": response.get("webViewLink"),
                "size": file_size,
            }

            return PluginResult(
                success=True,
                output_path=response.get("webViewLink"),
                metadata=result,
            )

        except Exception as e:
            logger.error(f"GDrive upload error: {e}")
            return PluginResult(success=False, error=str(e))

    async def upload_folder(
        self, folder_path: str, parent_id: str = None
    ) -> PluginResult:
        try:
            service = self._get_service()
            folder_name = os.path.basename(folder_path)

            metadata = {
                "name": folder_name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id] if parent_id else [],
            }

            folder = await asyncio.to_thread(
                service.files().create(body=metadata, fields="id").execute
            )
            folder_id = folder.get("id")

            for root, dirs, files in os.walk(folder_path):
                # Create subdirectories
                rel_path = os.path.relpath(root, folder_path)
                current_parent = folder_id

                # We would need to properly map nested structures here for a complete implementation,
                # but for now we flatten or assume shallow structure based on original code.

                for file in files:
                    file_path = os.path.join(root, file)
                    await self._upload_file_direct(service, file_path, folder_id)

            return PluginResult(
                success=True,
                output_path=f"https://drive.google.com/drive/folders/{folder_id}",
                metadata={"folder_id": folder_id, "name": folder_name},
            )

        except Exception as e:
            logger.error(f"GDrive folder upload error: {e}")
            return PluginResult(success=False, error=str(e))

    async def _upload_file_direct(self, service, file_path: str, parent_id: str):
        from googleapiclient.http import MediaFileUpload

        file_name = os.path.basename(file_path)
        metadata = {"name": file_name, "parents": [parent_id]}
        media = MediaFileUpload(file_path, resumable=True)

        return await asyncio.to_thread(
            service.files().create(body=metadata, media_body=media, fields="id").execute
        )

    async def create_folder(self, name: str, parent_id: str = None) -> dict:
        try:
            service = self._get_service()
            metadata = {
                "name": name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id] if parent_id else [],
            }

            result = await asyncio.to_thread(
                service.files()
                .create(body=metadata, fields="id,name,webViewLink")
                .execute
            )
            return result

        except Exception as e:
            logger.error(f"GDrive folder error: {e}")
            return {}

    async def list_files(self, folder_id: str = "root") -> list:
        try:
            service = self._get_service()
            results = await asyncio.to_thread(
                service.files()
                .list(
                    q=f"'{folder_id}' in parents and trashed=false",
                    fields="files(id,name,mimeType,size,webViewLink)",
                )
                .execute
            )
            return results.get("files", [])
        except Exception as e:
            logger.error(f"GDrive list error: {e}")
            return []

    async def get_file(self, file_id: str) -> dict:
        try:
            service = self._get_service()
            file = await asyncio.to_thread(
                service.files()
                .get(
                    fileId=file_id,
                    fields="id,name,size,mimeType,webViewLink,webContentLink",
                )
                .execute
            )
            return file
        except Exception as e:
            logger.error(f"GDrive get file error: {e}")
            return {}

    async def delete_file(self, file_id: str) -> bool:
        try:
            service = self._get_service()
            await asyncio.to_thread(service.files().delete(fileId=file_id).execute)
            return True
        except Exception as e:
            logger.error(f"GDrive delete error: {e}")
            return False

    async def share_file(
        self, file_id: str, role: str = "reader", type: str = "anyone"
    ) -> str:
        try:
            service = self._get_service()
            permission = {"type": type, "role": role}
            await asyncio.to_thread(
                service.permissions().create(fileId=file_id, body=permission).execute
            )

            file = await self.get_file(file_id)
            return file.get("webViewLink", "")
        except Exception as e:
            logger.error(f"GDrive share error: {e}")
            return ""

    async def clone_file(self, file_id: str, parent_id: str = None) -> Optional[dict]:
        try:
            service = self._get_service()
            file_meta = await self.get_file(file_id)
            if not file_meta:
                return None

            copy_meta = {"name": file_meta.get("name")}
            if parent_id:
                copy_meta["parents"] = [parent_id]

            result = await asyncio.to_thread(
                service.files()
                .copy(
                    fileId=file_id,
                    body=copy_meta,
                    fields="id,name,size,mimeType,webViewLink",
                )
                .execute
            )
            return result
        except Exception as e:
            logger.error(f"GDrive clone error: {e}")
            return None
