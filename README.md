# APK Modifier Service

基于 Python + FastAPI 的 APK 修改工具后端服务。核心特性：**一次上传，多次修改下载**。

APK 上传后立即使用 `apktool` 反编译并缓存，后续每次修改任务从缓存复制副本操作，避免重复解压。

## 功能

- 上传 APK 文件，自动反编译缓存
- 浏览 APK 内部文件结构和内容
- 定义脚本替换规则（支持正则）和图片替换规则
- 基于同一 APK 创建多个不同修改任务
- 异步任务处理，查询状态，下载修改后的 APK
- 管理已上传 APK 及关联任务

## 快速开始

### 本地运行

```bash
# 安装依赖
pip install -r requirements.txt

# 确保 apktool 已安装
# macOS: brew install apktool
# Linux: apt install apktool

# 启动服务
uvicorn app.main:app --reload --port 8000
```

### Docker 运行

```bash
docker build -t apk-modifier .
docker run -p 8000:8000 -v ./data:/app/data apk-modifier
```

### 从 GHCR 拉取

```bash
docker pull ghcr.io/gdgeek/apk-package:main
docker run -p 8000:8000 -v ./data:/app/data ghcr.io/gdgeek/apk-package:main
```

## API

启动后访问 http://localhost:8000/docs 查看完整的 Swagger 文档。

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/v1/apks` | 上传 APK 文件 |
| GET | `/api/v1/apks` | 获取已上传 APK 列表 |
| DELETE | `/api/v1/apks/{apk_id}` | 删除 APK 及关联资源 |
| GET | `/api/v1/apks/{apk_id}/files` | 浏览 APK 文件结构 |
| GET | `/api/v1/apks/{apk_id}/files/{path}` | 查看文件内容 |
| GET | `/api/v1/apks/{apk_id}/tasks` | 获取 APK 关联任务 |
| POST | `/api/v1/tasks` | 创建修改任务 |
| GET | `/api/v1/tasks/{task_id}` | 查询任务状态 |
| GET | `/api/v1/download/{task_id}` | 下载修改后的 APK |

## 使用示例

```bash
# 1. 上传 APK
curl -X POST http://localhost:8000/api/v1/apks \
  -F "file=@your-app.apk"
# 返回 {"apk_id": "xxx", "filename": "your-app.apk", ...}

# 2. 浏览文件结构
curl http://localhost:8000/api/v1/apks/{apk_id}/files

# 3. 查看文件内容
curl http://localhost:8000/api/v1/apks/{apk_id}/files/res/values/strings.xml

# 4. 创建修改任务
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "apk_id": "xxx",
    "rules": [
      {
        "type": "script",
        "target_path": "res/values/strings.xml",
        "pattern": "OldAppName",
        "replacement": "NewAppName"
      }
    ]
  }'
# 返回 {"task_id": "yyy", "status": "pending"}

# 5. 查询任务状态
curl http://localhost:8000/api/v1/tasks/{task_id}

# 6. 下载修改后的 APK
curl -O http://localhost:8000/api/v1/download/{task_id}
```

## 替换规则

### 脚本替换（ScriptRule）

```json
{
  "type": "script",
  "target_path": "res/values/strings.xml",
  "pattern": "旧文本",
  "replacement": "新文本",
  "use_regex": false
}
```

`use_regex: true` 时 `pattern` 支持 Python 正则表达式语法。

### 图片替换（ImageRule）

```json
{
  "type": "image",
  "target_path": "res/drawable/icon.png",
  "image_data": "Base64编码的图片数据"
}
```

## 测试

```bash
python -m pytest tests/ -v
```

## 项目结构

```
app/
├── main.py              # FastAPI 入口，CORS，全局异常处理
├── state.py             # 共享状态（内存存储）
├── models/
│   └── schemas.py       # Pydantic 数据模型
├── routers/
│   ├── apk_router.py    # APK 上传/管理/浏览路由
│   └── task_router.py   # 任务/下载路由
└── services/
    ├── storage_service.py   # 文件存储管理
    ├── apk_processor.py     # APK 反编译/缓存/打包
    └── rule_engine.py       # 规则验证与执行
```

## License

MIT
