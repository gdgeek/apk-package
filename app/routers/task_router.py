"""任务和下载路由"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse

from app import state
from app.models.schemas import (
    CacheStatus,
    CreateTaskRequest,
    RuleResult,
    TaskResponse,
    TaskStatus,
)
from app.services.rule_engine import RuleEngine

router = APIRouter(prefix="/api/v1", tags=["tasks"])


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


async def _run_task(task_id: str, apk_id: str, rules: list) -> None:
    """Background task: process the APK modification."""
    task = state.tasks[task_id]
    task["status"] = TaskStatus.PROCESSING

    cache_dir = state.storage.get_cache_dir(apk_id)
    work_dir = state.storage.get_work_dir(task_id)
    output_path = state.storage.get_output_path(task_id)

    try:
        rule_results = await state.processor.process_task(cache_dir, work_dir, output_path, rules)
        task["status"] = TaskStatus.COMPLETED
        task["download_url"] = f"/api/v1/download/{task_id}"
        task["rule_results"] = rule_results
        task["completed_at"] = datetime.now(tz=timezone.utc)
    except Exception as e:
        task["status"] = TaskStatus.FAILED
        task["error"] = str(e)
        task["completed_at"] = datetime.now(tz=timezone.utc)


@router.post("/tasks")
async def create_task(request: CreateTaskRequest, background_tasks: BackgroundTasks):
    """创建修改任务：验证规则，检查缓存就绪，启动后台处理。"""
    # Check APK exists
    if request.apk_id not in state.apk_metadata:
        return _error_response(404, "APK_NOT_FOUND", f"APK {request.apk_id} 不存在")

    # Check cache is ready
    meta = state.apk_metadata[request.apk_id]
    if meta.get("cache_status") != CacheStatus.READY:
        return _error_response(409, "CACHE_NOT_READY", "APK 缓存尚未就绪")

    # Validate rules
    engine = RuleEngine()
    validation = engine.validate_rules(request.rules)
    if not validation.valid:
        return _error_response(
            400,
            "INVALID_RULE",
            "规则验证失败",
            {"errors": [e.model_dump() for e in validation.errors]},
        )

    # Create task
    task_id = uuid4().hex
    now = datetime.now(tz=timezone.utc)
    state.tasks[task_id] = {
        "apk_id": request.apk_id,
        "status": TaskStatus.PENDING,
        "created_at": now,
        "completed_at": None,
        "download_url": None,
        "rule_results": [],
        "error": None,
    }

    # Start background processing
    background_tasks.add_task(_run_task, task_id, request.apk_id, request.rules)

    return {"task_id": task_id, "status": "pending"}


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str):
    """查询任务状态。"""
    if task_id not in state.tasks:
        return _error_response(404, "TASK_NOT_FOUND", f"任务 {task_id} 不存在")

    task = state.tasks[task_id]
    return TaskResponse(
        task_id=task_id,
        apk_id=task["apk_id"],
        status=task["status"],
        created_at=task["created_at"],
        completed_at=task.get("completed_at"),
        download_url=task.get("download_url"),
        rule_results=task.get("rule_results", []),
        error=task.get("error"),
    )


@router.get("/download/{task_id}")
async def download_task(task_id: str):
    """下载修改后的 APK 文件。"""
    if task_id not in state.tasks:
        return _error_response(404, "TASK_NOT_FOUND", f"任务 {task_id} 不存在")

    task = state.tasks[task_id]
    if task["status"] != TaskStatus.COMPLETED:
        return _error_response(404, "DOWNLOAD_NOT_FOUND", "下载文件不存在或任务未完成")

    output_path = state.storage.get_output_path(task_id)
    if not output_path.exists():
        return _error_response(404, "DOWNLOAD_NOT_FOUND", "下载文件不存在")

    # Use original APK filename for download
    apk_id = task["apk_id"]
    meta = state.apk_metadata.get(apk_id, {})
    filename = meta.get("filename", f"{task_id}.apk")

    return FileResponse(
        path=str(output_path),
        media_type="application/vnd.android.package-archive",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
