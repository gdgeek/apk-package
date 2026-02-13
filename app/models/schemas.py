"""APK 修改工具后端服务 - 数据模型定义"""

from datetime import datetime
from enum import Enum
from typing import Optional, Union

from pydantic import BaseModel, Field


# === 规则模型 ===


class RuleType(str, Enum):
    SCRIPT = "script"
    IMAGE = "image"


class ScriptRule(BaseModel):
    """脚本替换规则"""

    type: RuleType = RuleType.SCRIPT
    target_path: str = Field(..., description="APK 内目标脚本文件路径")
    pattern: str = Field(..., description="匹配模式（支持正则表达式）")
    replacement: str = Field(..., description="替换文本")
    use_regex: bool = Field(default=False, description="是否使用正则表达式匹配")


class ImageRule(BaseModel):
    """图片替换规则"""

    type: RuleType = RuleType.IMAGE
    target_path: str = Field(..., description="APK 内目标图片文件路径")
    image_data: str = Field(..., description="替换图片的 Base64 编码数据")


ReplacementRule = Union[ScriptRule, ImageRule]


# === 任务模型 ===


class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class RuleResult(BaseModel):
    """单条规则的执行结果"""

    rule_index: int
    success: bool
    message: str


class CreateTaskRequest(BaseModel):
    """创建修改任务的请求"""

    apk_id: str
    rules: list[Union[ScriptRule, ImageRule]]


class TaskResponse(BaseModel):
    """任务状态响应"""

    task_id: str
    apk_id: str
    status: TaskStatus
    created_at: datetime
    completed_at: Optional[datetime] = None
    download_url: Optional[str] = None
    rule_results: list[RuleResult] = []
    error: Optional[str] = None


class TaskSummary(BaseModel):
    """任务摘要（用于列表展示）"""

    task_id: str
    status: TaskStatus
    created_at: datetime
    completed_at: Optional[datetime] = None


# === 文件浏览模型 ===


class FileNode(BaseModel):
    """文件树节点"""

    name: str
    path: str
    is_directory: bool
    children: list["FileNode"] = []
    size: Optional[int] = None


# === APK 模型 ===


class CacheStatus(str, Enum):
    DECOMPILING = "decompiling"
    READY = "ready"
    FAILED = "failed"


class APKUploadResponse(BaseModel):
    """APK 上传响应"""

    apk_id: str
    filename: str
    size: int
    cache_status: CacheStatus


class APKInfo(BaseModel):
    """已上传 APK 信息"""

    apk_id: str
    filename: str
    size: int
    uploaded_at: datetime
    cache_status: CacheStatus
    task_count: int


# === 规则验证结果 ===


class ValidationError(BaseModel):
    """单条规则的验证错误"""

    rule_index: int
    field: str
    message: str


class ValidationResult(BaseModel):
    """规则集合的验证结果"""

    valid: bool
    errors: list[ValidationError] = []
