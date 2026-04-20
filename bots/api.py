"""
API Client for WZML-X Bots
Ensures all bot interactions go through the API layer.
"""

import logging
import httpx
from typing import Optional, Dict, Any, List

from config import get_config

logger = logging.getLogger("wzml.bot.api")

class APIClient:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(APIClient, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        
        cfg = get_config()
        port = cfg.limits.API_PORT or 8080
        host = cfg.limits.API_HOST or "127.0.0.1"
        if host == "0.0.0.0":
            host = "127.0.0.1"
            
        self.base_url = f"http://{host}:{port}"
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)
        self._initialized = True

    async def _post(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        try:
            response = await self.client.post(endpoint, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            err_data = e.response.json() if e.response.content else {"error": str(e)}
            logger.error(f"API Error {e.response.status_code} on {endpoint}: {err_data}")
            return {"error": err_data}
        except Exception as e:
            logger.error(f"API Request Failed on {endpoint}: {e}")
            return {"error": str(e)}

    async def _get(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        try:
            response = await self.client.get(endpoint, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            err_data = e.response.json() if e.response.content else {"error": str(e)}
            logger.error(f"API Error {e.response.status_code} on {endpoint}: {err_data}")
            return {"error": err_data}
        except Exception as e:
            logger.error(f"API Request Failed on {endpoint}: {e}")
            return {"error": str(e)}
            
    async def _delete(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        try:
            response = await self.client.delete(endpoint, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            err_data = e.response.json() if e.response.content else {"error": str(e)}
            logger.error(f"API Error {e.response.status_code} on {endpoint}: {err_data}")
            return {"error": err_data}
        except Exception as e:
            logger.error(f"API Request Failed on {endpoint}: {e}")
            return {"error": str(e)}

    # Task creation endpoints
    async def create_mirror(self, source: str, user_id: int, destination: str = "", is_leech: bool = False, is_qbit: bool = False, metadata: dict = None) -> Dict[str, Any]:
        params = {
            "source": source,
            "user_id": user_id,
            "destination": destination,
            "is_leech": str(is_leech).lower(),
            "is_qbit": str(is_qbit).lower()
        }
        if metadata:
            return await self._post("/api/mirror", params=params, json=metadata)
        return await self._post("/api/mirror", params=params)

    async def create_clone(self, source_id: str, user_id: int, destination: str = "") -> Dict[str, Any]:
        params = {
            "source_id": source_id,
            "user_id": user_id,
            "destination": destination
        }
        return await self._post("/api/clone", params=params)

    async def create_ytdlp(self, url: str, user_id: int, quality: str = "best") -> Dict[str, Any]:
        params = {
            "url": url,
            "user_id": user_id,
            "quality": quality
        }
        return await self._post("/api/ytdlp", params=params)

    async def create_rss(self, feed_url: str, user_id: int) -> Dict[str, Any]:
        params = {
            "feed_url": feed_url,
            "user_id": user_id
        }
        return await self._post("/api/rss", params=params)

    # Task control endpoints
    async def cancel_task(self, task_id: str) -> Dict[str, Any]:
        return await self._delete(f"/tasks/{task_id}")
        
    async def cancel_task_v2(self, task_id: str) -> Dict[str, Any]:
        return await self._post(f"/api/{task_id}/cancel")

    # Status endpoints
    async def get_active_tasks(self, user_id: Optional[int] = None) -> Dict[str, Any]:
        params = {"user_id": user_id} if user_id else {}
        return await self._get("/api/status/active", params=params)
        
    async def get_user_tasks(self, user_id: int, limit: int = 50) -> Dict[str, Any]:
        params = {"limit": limit}
        return await self._get(f"/api/status/user/{user_id}", params=params)

    async def get_queue_stats(self) -> Dict[str, Any]:
        return await self._get("/api/queue/stats")

    async def get_task(self, task_id: str) -> Dict[str, Any]:
        return await self._get(f"/tasks/{task_id}")

api_client = APIClient()
