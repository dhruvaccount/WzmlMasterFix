import asyncio
import logging
import os
from typing import Any, Optional
from secrets import token_hex

from plugins.base import UploaderPlugin, PluginContext, PluginResult
from core.exceptions import PluginExecutionError

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

            if credentials_path:
                self._credentials = (
                    service_account.Credentials.from_service_account_file(
                        credentials_path,
                        scopes=[
                            "https://www.googleapis.com/auth/drive.file",
                            "https://www.googleapis.com/auth/drive.upload",
                        ],
                    )
                )
                self._service = build("drive", "v3", credentials=self._credentials)
                logger.info("GDrive uploader initialized")
                return True
            else:
                logger.warning("No credentials provided")
                return False
        except Exception as e:
            logger.error(f"GDrive init error: {e}")
            return False

    def set_credentials(self, credentials):
        self._credentials = credentials

    async def upload(self, context: PluginContext, config: dict) -> PluginResult:
        file_path = context.source
        folder_id = config.get("folder_id", self._folder_id)

        if not os.path.exists(file_path):
            return PluginResult(success=False, error="File not found")

        try:
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload

            service = build("drive", "v3", credentials=self._credentials)

            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)

            metadata = {"name": file_name, "parents": [folder_id] if folder_id else []}

            media = MediaFileUpload(
                file_path, resumable=True, chunksize=1 * 1024 * 1024
            )

            file = (
                service.files()
                .create(body=metadata, media_body=media, fields="id,name,webViewLink")
                .execute()
            )

            result = {
                "id": file.get("id"),
                "name": file.get("name"),
                "url": file.get("webViewLink"),
                "size": file_size,
            }

            return PluginResult(
                success=True,
                output_path=file.get("webViewLink"),
                metadata=result,
            )

        except Exception as e:
            logger.error(f"GDrive upload error: {e}")
            return PluginResult(success=False, error=str(e))

    async def upload_folder(
        self, folder_path: str, parent_id: str = None
    ) -> PluginResult:
        try:
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload

            service = build("drive", "v3", credentials=self._credentials)

            folder_name = os.path.basename(folder_path)

            metadata = {
                "name": folder_name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id] if parent_id else [],
            }

            folder = service.files().create(body=metadata, fields="id").execute()
            folder_id = folder.get("id")

            for root, dirs, files in os.walk(folder_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    await self._upload_file(service, file_path, folder_id)

            return PluginResult(
                success=True,
                output_path=folder_id,
                metadata={"folder_id": folder_id},
            )

        except Exception as e:
            logger.error(f"GDrive folder upload error: {e}")
            return PluginResult(success=False, error=str(e))

    async def _upload_file(self, service, file_path: str, parent_id: str):
        from googleapiclient.http import MediaFileUpload

        file_name = os.path.basename(file_path)
        metadata = {"name": file_name, "parents": [parent_id]}
        media = MediaFileUpload(file_path, resumable=True)

        return (
            service.files()
            .create(body=metadata, media_body=media, fields="id")
            .execute()
        )

    async def create_folder(self, name: str, parent_id: str = None) -> dict:
        try:
            from googleapiclient.discovery import build

            service = build("drive", "v3", credentials=self._credentials)

            metadata = {
                "name": name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id] if parent_id else [],
            }

            result = (
                service.files()
                .create(body=metadata, fields="id,name,webViewLink")
                .execute()
            )

            return result

        except Exception as e:
            logger.error(f"GDrive folder error: {e}")
            return {}

    async def list_files(self, folder_id: str = "root") -> list:
        try:
            from googleapiclient.discovery import build

            service = build("drive", "v3", credentials=self._credentials)

            results = (
                service.files()
                .list(
                    q=f"'{folder_id}' in parents",
                    fields="files(id,name,mimeType,size,webViewLink)",
                )
                .execute()
            )

            return results.get("files", [])

        except Exception as e:
            logger.error(f"GDrive list error: {e}")
            return []

    async def get_file(self, file_id: str) -> dict:
        try:
            from googleapiclient.discovery import build

            service = build("drive", "v3", credentials=self._credentials)

            file = (
                service.files()
                .get(
                    fileId=file_id,
                    fields="id,name,size,mimeType,webViewLink,webContentLink",
                )
                .execute()
            )

            return file

        except Exception as e:
            logger.error(f"GDrive get file error: {e}")
            return {}

    async def delete_file(self, file_id: str) -> bool:
        try:
            from googleapiclient.discovery import build

            service = build("drive", "v3", credentials=self._credentials)
            service.files().delete(fileId=file_id).execute()
            return True

        except Exception as e:
            logger.error(f"GDrive delete error: {e}")
            return False

    async def copy_file(
        self, file_id: str, new_name: str = None, folder_id: str = None
    ) -> dict:
        try:
            from googleapiclient.discovery import build

            service = build("drive", "v3", credentials=self._credentials)

            copy_metadata = {
                "name": new_name,
                "parents": [folder_id] if folder_id else [],
            }

            result = service.files().copy(fileId=file_id, body=copy_metadata).execute()

            return result

        except Exception as e:
            logger.error(f"GDrive copy error: {e}")
            return {}

    async def get_share_link(self, file_id: str) -> str:
        try:
            from googleapiclient.discovery import build

            service = build("drive", "v3", credentials=self._credentials)

            service.permissions().create(
                fileId=file_id, body={"type": "anyone", "role": "reader"}
            ).execute()

            file = service.files().get(fileId=file_id, fields="webViewLink").execute()
            return file.get("webViewLink")

        except Exception as e:
            logger.error(f"GDrive share error: {e}")
            return ""

    async def get_capacity(self) -> dict:
        try:
            from googleapiclient.discovery import build

            service = build("drive", "v3", credentials=self._credentials)
            about = service.about().get(fields="storageQuota,storageUsed").execute()

            return {
                "limit": about.get("storageQuota", {}).get("limit"),
                "used": about.get("storageUsed"),
            }

        except Exception as e:
            logger.error(f"GDrive capacity error: {e}")
            return {}

    async def search(self, query: str, folder_id: str = None) -> list:
        try:
            from googleapiclient.discovery import build

            service = build("drive", "v3", credentials=self._credentials)

            q = f"name contains '{query}'"
            if folder_id:
                q += f" and '{folder_id}' in parents"

            results = (
                service.files()
                .list(q=q, fields="files(id,name,mimeType,size)")
                .execute()
            )

            return results.get("files", [])

        except Exception as e:
            logger.error(f"GDrive search error: {e}")
            return []
