"""Unit tests for task and download routes."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app import state
from app.main import app
from app.models.schemas import CacheStatus, RuleResult, TaskStatus


@pytest.fixture(autouse=True)
def _clean_state(tmp_path):
    """Reset shared state and use a temp directory for storage before each test."""
    original_storage = state.storage
    original_processor = state.processor
    original_meta = state.apk_metadata
    original_tasks = state.tasks

    from app.services.storage_service import StorageService
    state.storage = StorageService(base_dir=str(tmp_path / "data"))
    state.apk_metadata = {}
    state.tasks = {}

    yield

    state.storage = original_storage
    state.processor = original_processor
    state.apk_metadata = original_meta
    state.tasks = original_tasks


@pytest.fixture
def client():
    return TestClient(app)


def _seed_apk(apk_id: str = "abc123", cache_status: CacheStatus = CacheStatus.READY):
    """Insert a fake APK into shared state."""
    state.apk_metadata[apk_id] = {
        "filename": "test.apk",
        "cache_status": cache_status,
        "size": 1024,
        "uploaded_at": datetime.now(tz=timezone.utc),
    }


def _seed_completed_task(task_id: str, apk_id: str = "abc123", create_file: bool = True):
    """Insert a completed task into shared state and optionally create the output file."""
    state.tasks[task_id] = {
        "apk_id": apk_id,
        "status": TaskStatus.COMPLETED,
        "created_at": datetime.now(tz=timezone.utc),
        "completed_at": datetime.now(tz=timezone.utc),
        "download_url": f"/api/v1/download/{task_id}",
        "rule_results": [RuleResult(rule_index=0, success=True, message="ok")],
        "error": None,
    }
    if create_file:
        output_path = state.storage.get_output_path(task_id)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake apk content")


# ---- POST /api/v1/tasks ----

class TestCreateTask:
    def test_valid_rules_returns_task_id(self, client):
        _seed_apk()
        resp = client.post("/api/v1/tasks", json={
            "apk_id": "abc123",
            "rules": [
                {"type": "script", "target_path": "res/values/strings.xml", "pattern": "old", "replacement": "new"}
            ],
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "task_id" in body
        assert body["status"] == "pending"
        assert body["task_id"] in state.tasks

    def test_invalid_apk_id_returns_404(self, client):
        resp = client.post("/api/v1/tasks", json={
            "apk_id": "nonexistent",
            "rules": [
                {"type": "script", "target_path": "a.txt", "pattern": "x", "replacement": "y"}
            ],
        })
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "APK_NOT_FOUND"

    def test_cache_not_ready_returns_409(self, client):
        _seed_apk(cache_status=CacheStatus.DECOMPILING)
        resp = client.post("/api/v1/tasks", json={
            "apk_id": "abc123",
            "rules": [
                {"type": "script", "target_path": "a.txt", "pattern": "x", "replacement": "y"}
            ],
        })
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "CACHE_NOT_READY"

    def test_invalid_rules_returns_400(self, client):
        _seed_apk()
        resp = client.post("/api/v1/tasks", json={
            "apk_id": "abc123",
            "rules": [
                {"type": "script", "target_path": "", "pattern": "x", "replacement": "y"}
            ],
        })
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "INVALID_RULE"

    def test_path_traversal_rule_returns_400(self, client):
        _seed_apk()
        resp = client.post("/api/v1/tasks", json={
            "apk_id": "abc123",
            "rules": [
                {"type": "script", "target_path": "../etc/passwd", "pattern": "x", "replacement": "y"}
            ],
        })
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "INVALID_RULE"


# ---- GET /api/v1/tasks/{task_id} ----

class TestGetTask:
    def test_existing_task_returns_response(self, client):
        _seed_apk()
        now = datetime.now(tz=timezone.utc)
        state.tasks["task-1"] = {
            "apk_id": "abc123",
            "status": TaskStatus.PENDING,
            "created_at": now,
            "completed_at": None,
            "download_url": None,
            "rule_results": [],
            "error": None,
        }

        resp = client.get("/api/v1/tasks/task-1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["task_id"] == "task-1"
        assert body["apk_id"] == "abc123"
        assert body["status"] == "pending"
        assert body["download_url"] is None

    def test_completed_task_has_download_url(self, client):
        _seed_apk()
        _seed_completed_task("task-done")

        resp = client.get("/api/v1/tasks/task-done")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        assert body["download_url"] == "/api/v1/download/task-done"
        assert len(body["rule_results"]) == 1

    def test_failed_task_has_error(self, client):
        _seed_apk()
        state.tasks["task-fail"] = {
            "apk_id": "abc123",
            "status": TaskStatus.FAILED,
            "created_at": datetime.now(tz=timezone.utc),
            "completed_at": datetime.now(tz=timezone.utc),
            "download_url": None,
            "rule_results": [],
            "error": "recompile failed",
        }

        resp = client.get("/api/v1/tasks/task-fail")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "failed"
        assert body["error"] == "recompile failed"

    def test_nonexistent_task_returns_404(self, client):
        resp = client.get("/api/v1/tasks/no-such-task")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "TASK_NOT_FOUND"


# ---- GET /api/v1/download/{task_id} ----

class TestDownloadTask:
    def test_download_completed_task(self, client):
        _seed_apk()
        _seed_completed_task("dl-task")

        resp = client.get("/api/v1/download/dl-task")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/vnd.android.package-archive"
        assert "test.apk" in resp.headers["content-disposition"]
        assert resp.content == b"fake apk content"

    def test_download_non_completed_task_returns_404(self, client):
        _seed_apk()
        state.tasks["pending-task"] = {
            "apk_id": "abc123",
            "status": TaskStatus.PENDING,
            "created_at": datetime.now(tz=timezone.utc),
            "completed_at": None,
            "download_url": None,
            "rule_results": [],
            "error": None,
        }

        resp = client.get("/api/v1/download/pending-task")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "DOWNLOAD_NOT_FOUND"

    def test_download_nonexistent_task_returns_404(self, client):
        resp = client.get("/api/v1/download/no-such-task")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "TASK_NOT_FOUND"

    def test_download_completed_but_file_missing_returns_404(self, client):
        _seed_apk()
        _seed_completed_task("missing-file", create_file=False)

        resp = client.get("/api/v1/download/missing-file")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "DOWNLOAD_NOT_FOUND"
