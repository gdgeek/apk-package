"""APK 上传和管理路由"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, UploadFile
from fastapi.responses import JSONResponse

from app.models.schemas import APKInfo, APKUploadResponse, CacheStatus, TaskSummary, TaskStatus
from app import state

router = APIRouter(prefix="/api/v1/apks", tags=["apks"])

# 500 MB file size limit
MAX_FILE_SIZE = 500 * 1024 * 1024


def _error_response(status_code: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    """Build a standardized error response."""
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            }
        },
    )


@router.post("", response_model=APKUploadResponse)
async def upload_apk(file: UploadFile):
    """上传 APK 文件，存储并立即反编译到缓存。"""
    # Read content and check file size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        return _error_response(
            413,
            "FILE_TOO_LARGE",
            f"文件大小超过限制，最大允许 {MAX_FILE_SIZE // (1024 * 1024)} MB",
        )

    # Reset file position so save_upload can read it again
    await file.seek(0)

    # Save the uploaded file (validates APK format internally)
    try:
        apk_id = await state.storage.save_upload(file)
    except ValueError as e:
        return _error_response(400, "INVALID_APK_FORMAT", str(e))
    except Exception as e:
        return _error_response(500, "STORAGE_ERROR", f"存储文件失败: {e}")

    # Decompile to cache
    apk_path = state.storage.get_apk_path(apk_id)
    cache_dir = state.storage.get_cache_dir(apk_id)

    try:
        await state.processor.decompile_to_cache(apk_path, cache_dir)
    except RuntimeError as e:
        # Decompile failed — clean up the stored APK file
        apk_path = state.storage.get_apk_path(apk_id)
        if apk_path.exists():
            apk_path.unlink()
        # Also clean up partial cache
        import shutil
        if cache_dir.exists():
            shutil.rmtree(cache_dir, ignore_errors=True)
        return _error_response(500, "DECOMPILE_ERROR", str(e))

    # Store metadata
    filename = file.filename or f"{apk_id}.apk"
    size = len(content)
    now = datetime.now(tz=timezone.utc)

    state.apk_metadata[apk_id] = {
        "filename": filename,
        "cache_status": CacheStatus.READY,
        "size": size,
        "uploaded_at": now,
    }

    return APKUploadResponse(
        apk_id=apk_id,
        filename=filename,
        size=size,
        cache_status=CacheStatus.READY,
    )


@router.get("")
async def list_apks():
    """获取已上传 APK 列表。"""
    raw_apks = state.storage.list_apks()
    result: list[APKInfo] = []

    for apk in raw_apks:
        apk_id = apk["apk_id"]
        meta = state.apk_metadata.get(apk_id, {})

        # Count tasks associated with this APK
        task_count = sum(
            1 for t in state.tasks.values() if t.get("apk_id") == apk_id
        )

        result.append(APKInfo(
            apk_id=apk_id,
            filename=meta.get("filename", apk["filename"]),
            size=apk["size"],
            uploaded_at=apk["uploaded_at"],
            cache_status=meta.get("cache_status", CacheStatus.READY),
            task_count=task_count,
        ))

    return {"apks": result}


@router.delete("/{apk_id}")
async def delete_apk(apk_id: str):
    """删除 APK 及其缓存和关联任务产物。"""
    # Check if APK exists
    apk_path = state.storage.get_apk_path(apk_id)
    if not state.storage.file_exists(apk_path):
        return _error_response(404, "APK_NOT_FOUND", f"APK {apk_id} 不存在")

    # Gather associated task IDs
    task_ids = [
        tid for tid, t in state.tasks.items() if t.get("apk_id") == apk_id
    ]

    # Delete from storage
    await state.storage.delete_apk(apk_id, task_ids)

    # Clean up in-memory metadata
    state.apk_metadata.pop(apk_id, None)
    for tid in task_ids:
        state.tasks.pop(tid, None)

    return {"success": True}

@router.get("/{apk_id}/files")
async def list_apk_files(apk_id: str):
    """浏览 APK 文件结构（从缓存读取）。"""
    if apk_id not in state.apk_metadata:
        return _error_response(404, "APK_NOT_FOUND", f"APK {apk_id} 不存在")

    meta = state.apk_metadata[apk_id]
    if meta.get("cache_status") != CacheStatus.READY:
        return _error_response(409, "CACHE_NOT_READY", "APK 缓存尚未就绪")

    cache_dir = state.storage.get_cache_dir(apk_id)
    files = state.processor.list_files_from_cache(cache_dir)
    return {"files": files}


@router.get("/{apk_id}/files/{path:path}")
async def read_apk_file(apk_id: str, path: str):
    """查看 APK 内部脚本文件内容（从缓存读取）。"""
    if apk_id not in state.apk_metadata:
        return _error_response(404, "APK_NOT_FOUND", f"APK {apk_id} 不存在")

    meta = state.apk_metadata[apk_id]
    if meta.get("cache_status") != CacheStatus.READY:
        return _error_response(409, "CACHE_NOT_READY", "APK 缓存尚未就绪")

    cache_dir = state.storage.get_cache_dir(apk_id)
    try:
        content = state.processor.read_file_from_cache(cache_dir, path)
    except ValueError as e:
        return _error_response(400, "INVALID_RULE", str(e))
    except FileNotFoundError:
        return _error_response(404, "FILE_NOT_FOUND", f"文件不存在: {path}")

    return {"content": content}


@router.get("/{apk_id}/tasks")
async def list_apk_tasks(apk_id: str):
    """获取 APK 关联的任务列表。"""
    if apk_id not in state.apk_metadata:
        return _error_response(404, "APK_NOT_FOUND", f"APK {apk_id} 不存在")

    task_summaries = [
        TaskSummary(
            task_id=tid,
            status=TaskStatus(t["status"]) if isinstance(t["status"], str) else t["status"],
            created_at=t["created_at"],
            completed_at=t.get("completed_at"),
        )
        for tid, t in state.tasks.items()
        if t.get("apk_id") == apk_id
    ]
    return {"tasks": task_summaries}

