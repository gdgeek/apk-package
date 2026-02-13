"""Storage Service - 文件存储与管理"""

import os
import shutil
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import UploadFile


class StorageService:
    """存储服务：管理 APK 文件、缓存目录和输出文件"""

    # ZIP magic bytes: PK\x03\x04
    ZIP_MAGIC = b"PK\x03\x04"

    def __init__(self, base_dir: str = "data") -> None:
        self.base_dir = Path(base_dir)
        self.uploads_dir = self.base_dir / "uploads"
        self.cache_dir = self.base_dir / "cache"
        self.workspace_dir = self.base_dir / "workspace"
        self.output_dir = self.base_dir / "output"
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """创建所需的目录结构"""
        for d in [self.uploads_dir, self.cache_dir, self.workspace_dir, self.output_dir]:
            d.mkdir(parents=True, exist_ok=True)

    async def save_upload(self, file: UploadFile) -> str:
        """保存上传的 APK 文件，返回 apk_id。

        1. 读取文件内容
        2. 验证 APK 格式 (ZIP magic + AndroidManifest.xml)
        3. 生成 UUID 作为 apk_id
        4. 保存到 data/uploads/{apk_id}.apk
        5. 返回 apk_id
        """
        content = await file.read()

        self._validate_apk_format(content)

        apk_id = uuid.uuid4().hex
        apk_path = self.uploads_dir / f"{apk_id}.apk"
        apk_path.write_bytes(content)

        return apk_id

    def _validate_apk_format(self, content: bytes) -> None:
        """验证 APK 格式：检查 ZIP 魔数和 AndroidManifest.xml 存在性。

        Raises:
            ValueError: 文件不是有效的 APK 格式
        """
        if len(content) < 4 or content[:4] != self.ZIP_MAGIC:
            raise ValueError("文件不是有效的 ZIP 格式（缺少 PK 魔数）")

        try:
            import io
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                if "AndroidManifest.xml" not in zf.namelist():
                    raise ValueError("ZIP 文件中缺少 AndroidManifest.xml，不是有效的 APK")
        except zipfile.BadZipFile:
            raise ValueError("文件不是有效的 ZIP 格式")

    def get_apk_path(self, apk_id: str) -> Path:
        """获取原始 APK 文件的本地路径"""
        return self.uploads_dir / f"{apk_id}.apk"

    def get_cache_dir(self, apk_id: str) -> Path:
        """获取 APK 解压缓存目录路径"""
        return self.cache_dir / apk_id

    def get_work_dir(self, task_id: str) -> Path:
        """获取任务工作副本目录路径"""
        return self.workspace_dir / task_id

    def get_output_path(self, task_id: str) -> Path:
        """获取修改后 APK 的输出路径"""
        return self.output_dir / f"{task_id}.apk"

    def file_exists(self, path: Path) -> bool:
        """检查文件是否存在"""
        return path.exists()

    def list_apks(self) -> list[dict]:
        """扫描 uploads 目录，返回所有已上传 APK 的信息列表。

        Returns:
            包含 apk_id、filename、size、uploaded_at 的字典列表
        """
        apks: list[dict] = []
        if not self.uploads_dir.exists():
            return apks

        for apk_file in sorted(self.uploads_dir.glob("*.apk")):
            stat = apk_file.stat()
            apk_id = apk_file.stem
            apks.append(
                {
                    "apk_id": apk_id,
                    "filename": apk_file.name,
                    "size": stat.st_size,
                    "uploaded_at": datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.utc
                    ),
                }
            )

        return apks

    async def delete_apk(self, apk_id: str, task_ids: list[str]) -> None:
        """删除 APK 文件、缓存目录及关联任务产物。

        1. 删除 data/uploads/{apk_id}.apk
        2. 删除 data/cache/{apk_id}/ 目录
        3. 删除 data/output/{task_id}.apk 和 data/workspace/{task_id}/ (每个关联 task)
        """
        # 删除原始 APK
        apk_path = self.get_apk_path(apk_id)
        if apk_path.exists():
            apk_path.unlink()

        # 删除缓存目录
        cache_dir = self.get_cache_dir(apk_id)
        if cache_dir.exists():
            shutil.rmtree(cache_dir)

        # 删除关联任务的输出和工作目录
        for task_id in task_ids:
            output_path = self.get_output_path(task_id)
            if output_path.exists():
                output_path.unlink()

            work_dir = self.get_work_dir(task_id)
            if work_dir.exists():
                shutil.rmtree(work_dir)
