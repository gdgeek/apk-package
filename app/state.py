"""Shared application state - in-memory stores and service instances."""

from app.services.apk_processor import APKProcessor
from app.services.storage_service import StorageService

# Service instances
storage = StorageService()
processor = APKProcessor()

# In-memory stores
# apk_id -> {"filename": str, "cache_status": CacheStatus, "size": int, "uploaded_at": datetime}
apk_metadata: dict[str, dict] = {}

# task_id -> {"apk_id": str, "status": TaskStatus, "created_at": datetime, ...}
tasks: dict[str, dict] = {}
