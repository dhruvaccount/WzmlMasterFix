"""Database client interface"""

from abc import ABC, abstractmethod
from typing import Any, Optional
from dataclasses import dataclass


@dataclass
class DatabaseConfig:
    """Database configuration"""

    url: str = ""
    database: str = "wzmlx"


class DatabaseClient(ABC):
    """Base database client interface"""

    name: str = ""
    platform: str = ""

    @abstractmethod
    async def connect(self, config: DatabaseConfig) -> bool:
        """Connect to database"""
        pass

    @abstractmethod
    async def disconnect(self) -> bool:
        """Disconnect from database"""
        pass

    @property
    def is_connected(self) -> bool:
        """Check if connected"""
        return False

    async def save_task(self, task_id: str, task_data: dict) -> None:
        """Save task data"""
        pass

    async def get_task(self, task_id: str) -> Optional[dict]:
        """Get task by ID"""
        return None

    async def delete_task(self, task_id: str) -> None:
        """Delete task"""
        pass

    async def list_tasks(
        self, user_id: int = None, status: str = None, limit: int = 100
    ) -> list:
        """List tasks"""
        return []

    async def save_user(self, user_id: int, user_data: dict) -> None:
        """Save user data"""
        pass

    async def get_user(self, user_id: int) -> Optional[dict]:
        """Get user by ID"""
        return None

    async def list_users(self) -> list:
        """List all users"""
        return []

    async def save_rss_feed(self, user_id: int, feed_data: dict) -> None:
        """Save RSS feed"""
        pass

    async def get_rss_feed(self, user_id: int) -> Optional[dict]:
        """Get RSS feed"""
        return None

    async def delete_rss_feed(self, user_id: int) -> None:
        """Delete RSS feed"""
        pass

    async def save_setting(self, key: str, value: Any) -> None:
        """Save setting"""
        pass

    async def get_setting(self, key: str) -> Optional[Any]:
        """Get setting"""
        return None

    async def get_settings(self) -> dict:
        """Get all settings"""
        return {}

    async def save_config(self, config_data: dict) -> None:
        """Save config data"""
        pass

    async def get_config(self) -> dict:
        """Get config data"""
        return {}

    async def save_private_file(self, user_id: int, key: str, data: bytes) -> None:
        """Save private file"""
        pass

    async def get_private_file(self, user_id: int, key: str) -> Optional[bytes]:
        """Get private file"""
        return None

    async def add_pm_user(self, user_id: int) -> None:
        """Add PM user"""
        pass

    async def remove_pm_user(self, user_id: int) -> None:
        """Remove PM user"""
        pass

    async def list_pm_users(self) -> list:
        """List PM users"""
        return []

    async def find(self, collection: str, query: dict) -> list:
        """Find documents in collection"""
        return []

    async def find_all(self, collection: str) -> list:
        """Find all documents in collection"""
        return []

    async def find_one(self, collection: str, query: dict) -> Optional[dict]:
        """Find one document in collection"""
        return None

    async def insert_one(self, collection: str, document: dict) -> None:
        """Insert one document"""
        pass

    async def update_one(self, collection: str, query: dict, update: dict) -> None:
        """Update one document"""
        pass

    async def delete_one(self, collection: str, query: dict) -> None:
        """Delete one document"""
        pass


def get_database(name: str = None) -> Optional[DatabaseClient]:
    """Get database client"""
    from bots.clients import registry

    if name is None:
        from config.database import DATABASE_CLIENT

        name = DATABASE_CLIENT or "mongodb"

    return registry.get(name)


def register_database(name: str, client_class: type) -> None:
    """Register a database client"""
    from bots.clients import registry


__all__ = [
    "DatabaseClient",
    "DatabaseConfig",
    "get_database",
    "register_database",
]
