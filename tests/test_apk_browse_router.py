"""Unit tests for APK browse routes (files, file content, tasks)."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app import state
from app.main import app
from app.models.schemas import CacheStatus, TaskStatus
from app.services.storage_service import StorageService


@pytest.fixture(autouse=True)
def _clean_state(tmp_path):
    """Reset shared state and use a temp directory for storage before each test."""
    original_storage = state.storage
    original_processor = state.processor
    original_meta = state.apk_metadata
    original_tasks = state.tasks

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


APK_ID = "test-apk-id"


@pytest.fixture
def ready_apk(tmp_path):
    """Set up an APK with READY cache containing a small file tree."""
    cache_dir = state.storage.get_cache_dir(APK_ID)
    decompiled = cache_dir / "decompiled"
    decompiled.mkdir(parents=True)

    # Create a small file tree
    (decompiled / "AndroidManifest.xml").write_text("<manifest/>", encoding="utf-8")
    res_dir = decompiled / "res" / "values"
    res_dir.mkdir(parents=True)
    (res_dir / "strings.xml").write_text('<resources><string name="app_name">Test</string></resources>', encoding="utf-8")

    state.apk_metadata[APK_ID] = {
        "filename": "test.apk",
        "cache_status": CacheStatus.READY,
        "size": 1024,
        "uploaded_at": datetime.now(tz=timezone.utc),
    }
    return APK_ID


class TestListAPKFiles:
    """GET /api/v1/apks/{apk_id}/files"""

    def test_nonexistent_apk_returns_404(self, client):
        resp = client.get("/api/v1/apks/nonexistent/files")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "APK_NOT_FOUND"

    def test_cache_not_ready_returns_409(self, client):
        state.apk_metadata["decompiling-apk"] = {
            "filename": "test.apk",
            "cache_status": CacheStatus.DECOMPILING,
            "size": 100,
            "uploaded_at": datetime.now(tz=timezone.utc),
        }
        resp = client.get("/api/v1/apks/decompiling-apk/files")
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "CACHE_NOT_READY"

    def test_returns_file_tree(self, client, ready_apk):
        resp = client.get(f"/api/v1/apks/{ready_apk}/files")
        assert resp.status_code == 200
        files = resp.json()["files"]
        assert isinstance(files, list)
        assert len(files) > 0

        # Should contain res directory and AndroidManifest.xml
        names = {f["name"] for f in files}
        assert "AndroidManifest.xml" in names
        assert "res" in names

    def test_file_tree_has_nested_children(self, client, ready_apk):
        resp = client.get(f"/api/v1/apks/{ready_apk}/files")
        files = resp.json()["files"]
        res_node = next(f for f in files if f["name"] == "res")
        assert res_node["is_directory"] is True
        assert len(res_node["children"]) > 0


class TestReadAPKFile:
    """GET /api/v1/apks/{apk_id}/files/{path}"""

    def test_nonexistent_apk_returns_404(self, client):
        resp = client.get("/api/v1/apks/nonexistent/files/some/path.txt")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "APK_NOT_FOUND"

    def test_cache_not_ready_returns_409(self, client):
        state.apk_metadata["decompiling-apk"] = {
            "filename": "test.apk",
            "cache_status": CacheStatus.DECOMPILING,
            "size": 100,
            "uploaded_at": datetime.now(tz=timezone.utc),
        }
        resp = client.get("/api/v1/apks/decompiling-apk/files/some/path.txt")
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "CACHE_NOT_READY"

    def test_read_existing_file(self, client, ready_apk):
        resp = client.get(f"/api/v1/apks/{ready_apk}/files/AndroidManifest.xml")
        assert resp.status_code == 200
        assert resp.json()["content"] == "<manifest/>"

    def test_read_nested_file(self, client, ready_apk):
        resp = client.get(f"/api/v1/apks/{ready_apk}/files/res/values/strings.xml")
        assert resp.status_code == 200
        assert "app_name" in resp.json()["content"]

    def test_file_not_found_returns_404(self, client, ready_apk):
        resp = client.get(f"/api/v1/apks/{ready_apk}/files/nonexistent.txt")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "FILE_NOT_FOUND"

    def test_path_traversal_returns_400(self, client, ready_apk):
        # URL-encode the dots so they pass through to the handler as literal ".."
        resp = client.get(f"/api/v1/apks/{ready_apk}/files/res/..%2F..%2Fetc%2Fpasswd")
        assert resp.status_code == 400


class TestListAPKTasks:
    """GET /api/v1/apks/{apk_id}/tasks"""

    def test_nonexistent_apk_returns_404(self, client):
        resp = client.get("/api/v1/apks/nonexistent/tasks")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "APK_NOT_FOUND"

    def test_empty_task_list(self, client, ready_apk):
        resp = client.get(f"/api/v1/apks/{ready_apk}/tasks")
        assert resp.status_code == 200
        assert resp.json()["tasks"] == []

    def test_returns_associated_tasks(self, client, ready_apk):
        now = datetime.now(tz=timezone.utc)
        state.tasks["task-1"] = {
            "apk_id": ready_apk,
            "status": TaskStatus.COMPLETED,
            "created_at": now,
            "completed_at": now,
        }
        state.tasks["task-2"] = {
            "apk_id": ready_apk,
            "status": TaskStatus.PENDING,
            "created_at": now,
        }
        # Task for a different APK — should not appear
        state.tasks["task-other"] = {
            "apk_id": "other-apk",
            "status": TaskStatus.PENDING,
            "created_at": now,
        }

        resp = client.get(f"/api/v1/apks/{ready_apk}/tasks")
        assert resp.status_code == 200
        tasks = resp.json()["tasks"]
        assert len(tasks) == 2
        task_ids = {t["task_id"] for t in tasks}
        assert task_ids == {"task-1", "task-2"}

    def test_task_summary_fields(self, client, ready_apk):
        now = datetime.now(tz=timezone.utc)
        state.tasks["task-x"] = {
            "apk_id": ready_apk,
            "status": TaskStatus.COMPLETED,
            "created_at": now,
            "completed_at": now,
        }

        resp = client.get(f"/api/v1/apks/{ready_apk}/tasks")
        task = resp.json()["tasks"][0]
        assert task["task_id"] == "task-x"
        assert task["status"] == "completed"
        assert "created_at" in task
        assert task["completed_at"] is not None
