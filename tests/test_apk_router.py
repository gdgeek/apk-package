"""Unit tests for APK upload and management routes."""

import io
import zipfile
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app import state
from app.main import app
from app.models.schemas import CacheStatus


@pytest.fixture(autouse=True)
def _clean_state(tmp_path):
    """Reset shared state and use a temp directory for storage before each test."""
    original_storage = state.storage
    original_processor = state.processor
    original_meta = state.apk_metadata
    original_tasks = state.tasks

    # Use temp storage
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


def _make_apk_bytes() -> bytes:
    """Create a minimal valid APK (ZIP with AndroidManifest.xml)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("AndroidManifest.xml", "<manifest/>")
    return buf.getvalue()


def _make_zip_bytes() -> bytes:
    """Create a ZIP without AndroidManifest.xml (invalid APK)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("hello.txt", "hello")
    return buf.getvalue()


class TestUploadAPK:
    """POST /api/v1/apks"""

    @patch.object(state, "processor")
    def test_successful_upload(self, mock_processor, client):
        mock_processor.decompile_to_cache = AsyncMock()

        apk_data = _make_apk_bytes()
        resp = client.post(
            "/api/v1/apks",
            files={"file": ("test.apk", apk_data, "application/octet-stream")},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert "apk_id" in body
        assert body["filename"] == "test.apk"
        assert body["size"] == len(apk_data)
        assert body["cache_status"] == "ready"

        # Verify metadata was stored
        assert body["apk_id"] in state.apk_metadata

    def test_invalid_format_returns_400(self, client):
        resp = client.post(
            "/api/v1/apks",
            files={"file": ("bad.txt", b"not an apk", "application/octet-stream")},
        )

        assert resp.status_code == 400
        body = resp.json()
        assert body["error"]["code"] == "INVALID_APK_FORMAT"

    def test_zip_without_manifest_returns_400(self, client):
        zip_data = _make_zip_bytes()
        resp = client.post(
            "/api/v1/apks",
            files={"file": ("fake.apk", zip_data, "application/octet-stream")},
        )

        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "INVALID_APK_FORMAT"

    @patch("app.routers.apk_router.MAX_FILE_SIZE", 10)
    def test_file_too_large_returns_413(self, client):
        apk_data = _make_apk_bytes()  # larger than 10 bytes
        resp = client.post(
            "/api/v1/apks",
            files={"file": ("big.apk", apk_data, "application/octet-stream")},
        )

        assert resp.status_code == 413
        assert resp.json()["error"]["code"] == "FILE_TOO_LARGE"

    @patch.object(state, "processor")
    def test_decompile_failure_returns_500_and_cleans_up(self, mock_processor, client):
        mock_processor.decompile_to_cache = AsyncMock(
            side_effect=RuntimeError("apktool not found")
        )

        apk_data = _make_apk_bytes()
        resp = client.post(
            "/api/v1/apks",
            files={"file": ("test.apk", apk_data, "application/octet-stream")},
        )

        assert resp.status_code == 500
        assert resp.json()["error"]["code"] == "DECOMPILE_ERROR"

        # The APK file should have been cleaned up
        apk_files = list(state.storage.uploads_dir.glob("*.apk"))
        assert len(apk_files) == 0


class TestListAPKs:
    """GET /api/v1/apks"""

    def test_empty_list(self, client):
        resp = client.get("/api/v1/apks")
        assert resp.status_code == 200
        assert resp.json()["apks"] == []

    @patch.object(state, "processor")
    def test_list_after_upload(self, mock_processor, client):
        mock_processor.decompile_to_cache = AsyncMock()

        apk_data = _make_apk_bytes()
        upload_resp = client.post(
            "/api/v1/apks",
            files={"file": ("my.apk", apk_data, "application/octet-stream")},
        )
        apk_id = upload_resp.json()["apk_id"]

        resp = client.get("/api/v1/apks")
        assert resp.status_code == 200
        apks = resp.json()["apks"]
        assert len(apks) == 1
        assert apks[0]["apk_id"] == apk_id
        assert apks[0]["filename"] == "my.apk"
        assert apks[0]["cache_status"] == "ready"
        assert apks[0]["task_count"] == 0

    @patch.object(state, "processor")
    def test_list_with_task_count(self, mock_processor, client):
        mock_processor.decompile_to_cache = AsyncMock()

        apk_data = _make_apk_bytes()
        upload_resp = client.post(
            "/api/v1/apks",
            files={"file": ("my.apk", apk_data, "application/octet-stream")},
        )
        apk_id = upload_resp.json()["apk_id"]

        # Simulate tasks in state
        state.tasks["task-1"] = {"apk_id": apk_id, "status": "completed"}
        state.tasks["task-2"] = {"apk_id": apk_id, "status": "pending"}

        resp = client.get("/api/v1/apks")
        apks = resp.json()["apks"]
        assert apks[0]["task_count"] == 2


class TestDeleteAPK:
    """DELETE /api/v1/apks/{apk_id}"""

    def test_delete_nonexistent_returns_404(self, client):
        resp = client.delete("/api/v1/apks/nonexistent")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "APK_NOT_FOUND"

    @patch.object(state, "processor")
    def test_delete_existing_apk(self, mock_processor, client):
        mock_processor.decompile_to_cache = AsyncMock()

        apk_data = _make_apk_bytes()
        upload_resp = client.post(
            "/api/v1/apks",
            files={"file": ("del.apk", apk_data, "application/octet-stream")},
        )
        apk_id = upload_resp.json()["apk_id"]

        # Add a fake task
        state.tasks["task-x"] = {"apk_id": apk_id, "status": "completed"}

        resp = client.delete(f"/api/v1/apks/{apk_id}")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        # Metadata and tasks should be cleaned up
        assert apk_id not in state.apk_metadata
        assert "task-x" not in state.tasks

        # File should be gone
        assert not state.storage.get_apk_path(apk_id).exists()
