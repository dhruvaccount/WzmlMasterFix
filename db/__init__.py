"""Database clients - modular DB layer supporting multiple backends"""

from db.base import DatabaseClient, DatabaseConfig, get_database, register_database

from db.mongodb import (
    MongoDBClient,
    get_mongodb_client,
    init_mongodb,
    close_mongodb,
)

__all__ = [
    "DatabaseClient",
    "DatabaseConfig",
    "get_database",
    "register_database",
    "MongoDBClient",
    "get_mongodb_client",
    "init_mongodb",
    "close_mongodb",
]
