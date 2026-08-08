"""citra-mongo — shared MongoDB connection manager."""
from .manager import (
    MongoDBManager,
    MONGODB_DATABASE,
    get_async_mongo_client,
    get_mongo_client,
    get_async_database,
    get_sync_database,
    get_mongodb_manager,
    get_database_name,
    close_all_connections,
)

__all__ = [
    "MongoDBManager",
    "MONGODB_DATABASE",
    "get_async_mongo_client",
    "get_mongo_client",
    "get_async_database",
    "get_sync_database",
    "get_mongodb_manager",
    "get_database_name",
    "close_all_connections",
]
