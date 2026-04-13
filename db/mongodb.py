"""MongoDB database client"""

import os
import logging
from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.server_api import ServerApi
from pymongo.errors import PyMongoError

from db.base import DatabaseClient, DatabaseConfig

logger = logging.getLogger("wzml.mongodb")


class MongoDBClient(DatabaseClient):
    """MongoDB database client"""

    name = "mongodb"
    platform = "mongodb"

    def __init__(self):
        self._client: Optional[AsyncIOMotorClient] = None
        self._db = None
        self._connected = False

    async def connect(self, config: DatabaseConfig = None) -> bool:
        if config is None:
            config = DatabaseConfig(
                url=os.getenv("DATABASE_URL"),
                database=os.getenv("DATABASE_NAME", "wzmlx"),
            )

        if not config.url:
            logger.warning("DATABASE_URL not set, MongoDB disabled")
            return False

        try:
            self._client = AsyncIOMotorClient(config.url, server_api=ServerApi("1"))
            await self._client.admin.command("ping")
            self._db = self._client[config.database]
            self._connected = True
            logger.info("MongoDB connected successfully")
            return True
        except PyMongoError as e:
            logger.error(f"MongoDB connection failed: {e}")
            self._connected = False
            return False

    async def disconnect(self) -> bool:
        if self._client:
            self._client.close()
            self._client = None
            self._db = None
            self._connected = False
            logger.info("MongoDB disconnected")
        return True

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def save_task(self, task_id: str, task_data: dict) -> None:
        if not self._connected:
            return
        await self._db.tasks.update_one(
            {"_id": task_id}, {"$set": task_data}, upsert=True
        )

    async def get_task(self, task_id: str) -> Optional[dict]:
        if not self._connected:
            return None
        return await self._db.tasks.find_one({"_id": task_id})

    async def delete_task(self, task_id: str) -> None:
        if not self._connected:
            return
        await self._db.tasks.delete_one({"_id": task_id})

    async def list_tasks(
        self, user_id: int = None, status: str = None, limit: int = 100
    ) -> list:
        if not self._connected:
            return []
        query = {}
        if user_id:
            query["user_id"] = user_id
        if status:
            query["status"] = status
        cursor = self._db.tasks.find(query).sort("created_at", -1).limit(limit)
        return [doc async for doc in cursor]

    async def save_user(self, user_id: int, user_data: dict) -> None:
        if not self._connected:
            return
        await self._db.users.update_one(
            {"_id": user_id}, {"$set": user_data}, upsert=True
        )

    async def get_user(self, user_id: int) -> Optional[dict]:
        if not self._connected:
            return None
        return await self._db.users.find_one({"_id": user_id})

    async def list_users(self) -> list:
        if not self._connected:
            return []
        return [doc async for doc in self._db.users.find({})]

    async def save_rss_feed(self, user_id: int, feed_data: dict) -> None:
        if not self._connected:
            return
        await self._db.rss.update_one(
            {"_id": user_id}, {"$set": feed_data}, upsert=True
        )

    async def get_rss_feed(self, user_id: int) -> Optional[dict]:
        if not self._connected:
            return None
        return await self._db.rss.find_one({"_id": user_id})

    async def delete_rss_feed(self, user_id: int) -> None:
        if not self._connected:
            return
        await self._db.rss.delete_one({"_id": user_id})

    async def save_setting(self, key: str, value: Any) -> None:
        if not self._connected:
            return
        await self._db.settings.config.update_one(
            {"_id": "config"}, {"$set": {key: value}}, upsert=True
        )

    async def get_setting(self, key: str) -> Optional[Any]:
        if not self._connected:
            return None
        doc = await self._db.settings.config.find_one({"_id": "config"})
        return doc.get(key) if doc else None

    async def get_settings(self) -> dict:
        if not self._connected:
            return {}
        doc = await self._db.settings.config.find_one({"_id": "config"})
        return doc or {}

    async def save_config(self, config_data: dict) -> None:
        if not self._connected:
            return
        await self._db.settings.deployConfig.update_one(
            {"_id": "deploy"}, {"$set": config_data}, upsert=True
        )

    async def get_config(self) -> dict:
        if not self._connected:
            return {}
        doc = await self._db.settings.deployConfig.find_one({"_id": "deploy"})
        return doc or {}

    async def save_private_file(self, user_id: int, key: str, data: bytes) -> None:
        if not self._connected:
            return
        await self._db.users[f"{user_id}"].update_one(
            {"_id": key}, {"$set": {"data": data}}, upsert=True
        )

    async def get_private_file(self, user_id: int, key: str) -> Optional[bytes]:
        if not self._connected:
            return None
        doc = await self._db.users[f"{user_id}"].find_one({"_id": key})
        return doc.get("data") if doc else None

    async def add_pm_user(self, user_id: int) -> None:
        if not self._connected:
            return
        if not await self._db.pm_users.find_one({"_id": user_id}):
            await self._db.pm_users.insert_one({"_id": user_id})
            logger.info(f"New PM User Added: {user_id}")

    async def remove_pm_user(self, user_id: int) -> None:
        if not self._connected:
            return
        await self._db.pm_users.delete_one({"_id": user_id})

    async def list_pm_users(self) -> list:
        if not self._connected:
            return []
        return [doc async for doc in self._db.pm_users.find({})]

    async def find(self, collection: str, query: dict) -> list:
        """Find documents in collection"""
        if not self._connected:
            return []
        return [doc async for doc in self._db[collection].find(query)]

    async def find_all(self, collection: str) -> list:
        """Find all documents in collection"""
        if not self._connected:
            return []
        return [doc async for doc in self._db[collection].find({})]

    async def find_one(self, collection: str, query: dict) -> Optional[dict]:
        """Find one document in collection"""
        if not self._connected:
            return None
        return await self._db[collection].find_one(query)

    async def insert_one(self, collection: str, document: dict) -> None:
        """Insert one document"""
        if self._connected:
            await self._db[collection].insert_one(document)

    async def update_one(self, collection: str, query: dict, update: dict) -> None:
        """Update one document"""
        if self._connected:
            await self._db[collection].update_one(query, update)

    async def delete_one(self, collection: str, query: dict) -> None:
        """Delete one document"""
        if self._connected:
            await self._db[collection].delete_one(query)


_mongodb_client: Optional[MongoDBClient] = None


def get_mongodb_client() -> MongoDBClient:
    """Get or create MongoDB client instance"""
    global _mongodb_client
    if _mongodb_client is None:
        _mongodb_client = MongoDBClient()
    return _mongodb_client


async def init_mongodb(config: DatabaseConfig = None) -> bool:
    """Initialize MongoDB"""
    client = get_mongodb_client()
    return await client.connect(config)


async def close_mongodb() -> bool:
    """Close MongoDB connection"""
    client = get_mongodb_client()
    return await client.disconnect()


__all__ = [
    "MongoDBClient",
    "get_mongodb_client",
    "init_mongodb",
    "close_mongodb",
]
