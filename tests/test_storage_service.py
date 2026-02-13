"""StorageService 单元测试"""

import io
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from app.services.storage_service import StorageService


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """创建临时数据目录"""
    return tmp_path / "data"


@pytest.fixture
def storage(tmp_data_dir: Path) -> StorageService:
    """创建使用临时目录的 StorageService 实例"""
    return StorageService(base_dir=str(tmp_data_dir))


def _make_apk_bytes(manifest_content: bytes = b"<manifest/>") -> bytes:
    """创建一个包含 AndroidManifest.xml 的最小有效 APK (ZIP) 文件"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("AndroidManifest.xml", manifest_content)
    return buf.getvalue()


def _make_upload_file(content: bytes, filename: str = "test.apk") -> MagicMock:
    """创建模拟的 UploadFile 对象"""
    upload = AsyncMock()
    upload.filename = filename
    upload.read = AsyncMock(return_value=content)
    return upload


# === 目录结构测试 ===


class TestDirectoryStructure:
    def test_creates_all_directories(self, storage: StorageService, tmp_data_dir: Path):
        """初始化时应创建 uploads、cache、workspace、output 目录"""
        assert (tmp_data_dir / "uploads").is_dir()
        assert (tmp_data_dir / "cache").is_dir()
        assert (tmp_data_dir / "workspace").is_dir()
        assert (tmp_data_dir / "output").is_dir()


# === save_upload 测试 ===


class TestSaveUpload:
    @pytest.mark.asyncio
    async def test_save_valid_apk(self, storage: StorageService):
        """上传有效 APK 应返回 apk_id 并保存文件"""
        apk_bytes = _make_apk_bytes()
        upload = _make_upload_file(apk_bytes)

        apk_id = await storage.save_upload(upload)

        assert apk_id  # 非空字符串
        assert len(apk_id) == 32  # UUID hex 长度
        saved_path = storage.get_apk_path(apk_id)
        assert saved_path.exists()
        assert saved_path.read_bytes() == apk_bytes

    @pytest.mark.asyncio
    async def test_save_generates_unique_ids(self, storage: StorageService):
        """每次上传应生成不同的 apk_id"""
        apk_bytes = _make_apk_bytes()
        ids = set()
        for _ in range(5):
            upload = _make_upload_file(apk_bytes)
            apk_id = await storage.save_upload(upload)
            ids.add(apk_id)
        assert len(ids) == 5

    @pytest.mark.asyncio
    async def test_reject_non_zip_file(self, storage: StorageService):
        """非 ZIP 文件应被拒绝"""
        upload = _make_upload_file(b"this is not a zip file")
        with pytest.raises(ValueError, match="ZIP"):
            await storage.save_upload(upload)

    @pytest.mark.asyncio
    async def test_reject_empty_file(self, storage: StorageService):
        """空文件应被拒绝"""
        upload = _make_upload_file(b"")
        with pytest.raises(ValueError, match="ZIP"):
            await storage.save_upload(upload)

    @pytest.mark.asyncio
    async def test_reject_zip_without_manifest(self, storage: StorageService):
        """没有 AndroidManifest.xml 的 ZIP 应被拒绝"""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("some_file.txt", "hello")
        upload = _make_upload_file(buf.getvalue())
        with pytest.raises(ValueError, match="AndroidManifest.xml"):
            await storage.save_upload(upload)

    @pytest.mark.asyncio
    async def test_rejected_file_not_stored(self, storage: StorageService):
        """被拒绝的文件不应留在存储中"""
        upload = _make_upload_file(b"not a zip")
        with pytest.raises(ValueError):
            await storage.save_upload(upload)
        # uploads 目录应为空
        assert list(storage.uploads_dir.glob("*.apk")) == []


# === 路径方法测试 ===


class TestPathMethods:
    def test_get_apk_path(self, storage: StorageService, tmp_data_dir: Path):
        assert storage.get_apk_path("abc123") == tmp_data_dir / "uploads" / "abc123.apk"

    def test_get_cache_dir(self, storage: StorageService, tmp_data_dir: Path):
        assert storage.get_cache_dir("abc123") == tmp_data_dir / "cache" / "abc123"

    def test_get_work_dir(self, storage: StorageService, tmp_data_dir: Path):
        assert storage.get_work_dir("task1") == tmp_data_dir / "workspace" / "task1"

    def test_get_output_path(self, storage: StorageService, tmp_data_dir: Path):
        assert storage.get_output_path("task1") == tmp_data_dir / "output" / "task1.apk"


# === file_exists 测试 ===


class TestFileExists:
    def test_existing_file(self, storage: StorageService, tmp_data_dir: Path):
        f = tmp_data_dir / "uploads" / "test.apk"
        f.write_bytes(b"data")
        assert storage.file_exists(f) is True

    def test_nonexistent_file(self, storage: StorageService, tmp_data_dir: Path):
        f = tmp_data_dir / "uploads" / "nonexistent.apk"
        assert storage.file_exists(f) is False


# === list_apks 测试 ===


class TestListApks:
    def test_empty_uploads(self, storage: StorageService):
        """空 uploads 目录应返回空列表"""
        result = storage.list_apks()
        assert result == []

    def test_lists_uploaded_apks(self, storage: StorageService):
        """应返回所有已上传 APK 的信息"""
        # 手动创建几个 APK 文件
        for name in ["aaa.apk", "bbb.apk"]:
            (storage.uploads_dir / name).write_bytes(b"fake apk data")

        result = storage.list_apks()
        assert len(result) == 2
        ids = {r["apk_id"] for r in result}
        assert ids == {"aaa", "bbb"}

    def test_list_apk_fields(self, storage: StorageService):
        """返回的字典应包含必要字段"""
        content = b"some data"
        (storage.uploads_dir / "test123.apk").write_bytes(content)

        result = storage.list_apks()
        assert len(result) == 1
        apk_info = result[0]
        assert apk_info["apk_id"] == "test123"
        assert apk_info["filename"] == "test123.apk"
        assert apk_info["size"] == len(content)
        assert isinstance(apk_info["uploaded_at"], datetime)

    def test_ignores_non_apk_files(self, storage: StorageService):
        """应忽略非 .apk 文件"""
        (storage.uploads_dir / "readme.txt").write_text("hello")
        (storage.uploads_dir / "valid.apk").write_bytes(b"data")

        result = storage.list_apks()
        assert len(result) == 1
        assert result[0]["apk_id"] == "valid"


# === delete_apk 测试 ===


class TestDeleteApk:
    @pytest.mark.asyncio
    async def test_delete_apk_file(self, storage: StorageService):
        """应删除原始 APK 文件"""
        apk_path = storage.get_apk_path("apk1")
        apk_path.write_bytes(b"data")
        assert apk_path.exists()

        await storage.delete_apk("apk1", [])
        assert not apk_path.exists()

    @pytest.mark.asyncio
    async def test_delete_cache_dir(self, storage: StorageService):
        """应删除缓存目录"""
        cache = storage.get_cache_dir("apk1")
        decompiled = cache / "decompiled"
        decompiled.mkdir(parents=True)
        (decompiled / "file.txt").write_text("content")

        await storage.delete_apk("apk1", [])
        assert not cache.exists()

    @pytest.mark.asyncio
    async def test_delete_associated_tasks(self, storage: StorageService):
        """应删除关联任务的输出和工作目录"""
        # 创建任务产物
        output1 = storage.get_output_path("task1")
        output1.write_bytes(b"modified apk")
        work1 = storage.get_work_dir("task1")
        work1.mkdir(parents=True)
        (work1 / "file.txt").write_text("work")

        output2 = storage.get_output_path("task2")
        output2.write_bytes(b"modified apk 2")

        await storage.delete_apk("apk1", ["task1", "task2"])

        assert not output1.exists()
        assert not work1.exists()
        assert not output2.exists()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_apk_no_error(self, storage: StorageService):
        """删除不存在的 APK 不应报错"""
        await storage.delete_apk("nonexistent", ["task_x"])
        # 不应抛出异常

    @pytest.mark.asyncio
    async def test_delete_all_resources(self, storage: StorageService):
        """完整删除场景：APK + 缓存 + 多个任务产物"""
        apk_id = "full_test"
        task_ids = ["t1", "t2"]

        # 创建所有资源
        storage.get_apk_path(apk_id).write_bytes(b"apk")
        cache = storage.get_cache_dir(apk_id)
        (cache / "decompiled").mkdir(parents=True)
        for tid in task_ids:
            storage.get_output_path(tid).write_bytes(b"out")
            wd = storage.get_work_dir(tid)
            wd.mkdir(parents=True)
            (wd / "f.txt").write_text("x")

        await storage.delete_apk(apk_id, task_ids)

        assert not storage.get_apk_path(apk_id).exists()
        assert not cache.exists()
        for tid in task_ids:
            assert not storage.get_output_path(tid).exists()
            assert not storage.get_work_dir(tid).exists()
