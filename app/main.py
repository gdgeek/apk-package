"""APK Modifier Service - FastAPI 应用入口"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routers.apk_router import router as apk_router
from app.routers.task_router import router as task_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时确保数据目录存在"""
    from app import state

    state.storage._ensure_directories()
    yield


app = FastAPI(
    title="APK Modifier Service",
    description="APK 修改工具后端服务 - 一次上传，多次修改下载",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS 中间件 - 允许所有来源（开发阶段）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(apk_router)
app.include_router(task_router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """全局异常处理器 - 统一错误响应格式"""
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": str(exc),
                "details": {},
            }
        },
    )


@app.get("/health")
async def health_check():
    return {"status": "ok"}
