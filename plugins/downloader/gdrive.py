import asyncio
import logging
import os
from typing import Any, Optional
from secrets import token_hex

from plugins.base import DownloaderPlugin, PluginContext, PluginResult

logger = logging.getLogger("wzml.gdrive_downloader")


class GDriveDownloader(DownloaderPlugin):
    name = "gdrive"
    plugin_type = "downloader"

    def __init__(self):
        self._credentials = None
        self._service = None

    async def initialize(self, credentials_path: str = None) -> bool:
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            if credentials_path:
                self._credentials = (
                    service_account.Credentials.from_service_account_file(
                        credentials_path,
                        scopes=["https://www.googleapis.com/auth/drive.readonly"],
                    )
                )
                self._service = build("drive", "v3", credentials=self._credentials)
                logger.info("GDrive initialized")
                return True
            else:
                logger.warning("No credentials provided")
                return False
        except Exception as e:
            logger.error(f"GDrive init error: {e}")
            return False

    def set_credentials(self, credentials):
        self._credentials = credentials

    async def download(self, context: PluginContext, config: dict) -> PluginResult:
        url = context.source
        output_path = config.get("path", "/tmp/downloads")

        if "drive.google.com" not in url and "docs.google.com" not in url:
            return PluginResult(success=False, error="Not a GDrive link")

        try:
            file_id = self._extract_file_id(url)
            if not file_id:
                return PluginResult(success=False, error="Invalid GDrive link")

            file_metadata = await self._get_file_metadata(file_id)
            if not file_metadata:
                return PluginResult(success=False, error="File not found")

            file_name = file_metadata.get("name")
            mime_type = file_metadata.get("mimeType")

            if mime_type == "application/vnd.google-apps.folder":
                await self._download_folder(file_id, output_path)
            else:
                await self._download_file(file_id, file_name, output_path)

            return PluginResult(
                success=True,
                output_path=os.path.join(output_path, file_name),
                metadata=file_metadata,
            )

        except Exception as e:
            logger.error(f"GDrive download error: {e}")
            return PluginResult(success=False, error=str(e))

    def _extract_file_id(self, url: str) -> Optional[str]:
        if "id=" in url:
            from urllib.parse import parse_qs, urlparse

            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            return params.get("id", [None])[0]

        parts = url.split("/")
        for i, part in enumerate(parts):
            if part == "d" and i + 1 < len(parts):
                return parts[i + 1]

        return None

    async def _get_file_metadata(self, file_id: str) -> Optional[dict]:
        try:
            from googleapiclient.discovery import build

            service = build("drive", "v3", credentials=self._credentials)
            file = (
                service.files()
                .get(fileId=file_id, fields="id,name,mimeType,size,parents")
                .execute()
            )

            return {
                "id": file.get("id"),
                "name": file.get("name"),
                "mimeType": file.get("mimeType"),
                "size": file.get("size"),
            }
        except Exception as e:
            logger.error(f"GDrive metadata error: {e}")
            return None

    async def _download_file(self, file_id: str, file_name: str, output_path: str):
        from googleapiclient.discovery import build

        service = build("drive", "v3", credentials=self._credentials)

        request = service.files().get_media(fileId=file_id)
        output_file = os.path.join(output_path, file_name)

        with open(output_file, "wb") as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

        return output_file

    async def _download_folder(self, folder_id: str, output_path: str):
        from googleapiclient.discovery import build

        service = build("drive", "v3", credentials=self._credentials)

        results = (
            service.files()
            .list(q=f"'{folder_id}' in parents", fields="files(id,name,mimeType)")
            .execute()
        )

        files = results.get("files", [])

        for file in files:
            if file["mimeType"] == "application/vnd.google-apps.folder":
                new_folder = os.path.join(output_path, file["name"])
                os.makedirs(new_folder, exist_ok=True)
                await self._download_folder(file["id"], new_folder)
            else:
                await self._download_file(file["id"], file["name"], output_path)

    async def list_files(self, folder_id: str = "root") -> list:
        try:
            from googleapiclient.discovery import build

            service = build("drive", "v3", credentials=self._credentials)
            results = (
                service.files()
                .list(
                    q=f"'{folder_id}' in parents", fields="files(id,name,mimeType,size)"
                )
                .execute()
            )

            return results.get("files", [])
        except Exception as e:
            logger.error(f"GDrive list error: {e}")
            return []

    async def get_status(self, file_id: str = None) -> dict:
        if not file_id:
            file_id = self._extract_file_id(context.source)

        return await self._get_file_metadata(file_id)

    async def copy_file(self, file_id: str, dest_folder_id: str = "root") -> dict:
        try:
            from googleapiclient.discovery import build

            service = build("drive", "v3", credentials=self._credentials)

            copy_metadata = {"name": f"Copy of {file_id}", "parents": [dest_folder_id]}

            result = service.files().copy(fileId=file_id, body=copy_metadata).execute()

            return result
        except Exception as e:
            logger.error(f"GDrive copy error: {e}")
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

    async def create_folder(self, name: str, parent_id: str = "root") -> dict:
        try:
            from googleapiclient.discovery import build

            service = build("drive", "v3", credentials=self._credentials)

            folder_metadata = {
                "name": name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id],
            }

            result = (
                service.files().create(body=folder_metadata, fields="id,name").execute()
            )

            return result
        except Exception as e:
            logger.error(f"GDrive folder error: {e}")
            return {}

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
