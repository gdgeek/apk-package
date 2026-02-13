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
- Bootstrap 5 响应式 Web UI

## 快速开始

### Docker Compose（推荐）

```bash
git clone git@github.com:gdgeek/apk-package.git
cd apk-package
docker compose up --build
```

服务启动后：
- Web UI：http://localhost:8000
- API 文档（Swagger）：http://localhost:8000/docs
- Health Check：http://localhost:8000/health

`docker-compose.yml` 使用 volume 挂载 `./app` 和 `./static`，修改代码后自动热重载，无需重新构建。

### 本地运行

```bash
pip install -r requirements.txt

# 确保 apktool 已安装
# macOS: brew install apktool
# Linux: apt install apktool

uvicorn app.main:app --reload --port 8000
```

### 从 GHCR 拉取

```bash
docker pull ghcr.io/gdgeek/apk-package:main
docker run -p 8000:8000 -v ./data:/app/data ghcr.io/gdgeek/apk-package:main
```

---

## 使用说明

### 方式一：Web UI

打开 http://localhost:8000 即可使用图形界面，支持以下操作：

1. **上传 APK** — 点击上传区域或拖拽 APK 文件
2. **浏览文件** — 点击已上传的 APK，左侧显示文件树，点击文件查看内容
3. **添加规则** — 点击「脚本」或「图片」按钮添加替换规则
4. **创建任务** — 点击「创建修改任务」，系统异步处理
5. **下载结果** — 任务完成后，点击下载按钮获取修改后的 APK

### 方式二：API 调用

完整流程示例（使用 curl）：

#### 第一步：上传 APK

```bash
curl -X POST http://localhost:8000/api/v1/apks \
  -F "file=@your-app.apk"
```

响应：
```json
{
  "apk_id": "a1b2c3d4",
  "filename": "your-app.apk",
  "size": 12345678,
  "cache_status": "ready"
}
```

上传成功后 APK 会立即被 apktool 反编译并缓存，`cache_status` 为 `ready` 表示可以开始操作。

#### 第二步：浏览文件结构

```bash
curl http://localhost:8000/api/v1/apks/{apk_id}/files
```

响应：
```json
{
  "files": [
    {
      "name": "AndroidManifest.xml",
      "path": "AndroidManifest.xml",
      "is_directory": false,
      "size": 4096
    },
    {
      "name": "res",
      "path": "res",
      "is_directory": true,
      "children": [
        {
          "name": "values",
          "path": "res/values",
          "is_directory": true,
          "children": [...]
        }
      ]
    }
  ]
}
```

#### 第三步：查看文件内容

```bash
curl http://localhost:8000/api/v1/apks/{apk_id}/files/res/values/strings.xml
```

响应：
```json
{
  "content": "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n<resources>\n    <string name=\"app_name\">MyApp</string>\n</resources>"
}
```

#### 第四步：创建修改任务

```bash
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "apk_id": "a1b2c3d4",
    "rules": [
      {
        "type": "script",
        "target_path": "res/values/strings.xml",
        "pattern": "MyApp",
        "replacement": "NewApp",
        "use_regex": false
      },
      {
        "type": "image",
        "target_path": "res/drawable/icon.png",
        "image_data": "iVBORw0KGgoAAAANSUhEUg..."
      }
    ]
  }'
```

响应：
```json
{
  "task_id": "e5f6g7h8",
  "status": "pending"
}
```

#### 第五步：查询任务状态

```bash
curl http://localhost:8000/api/v1/tasks/{task_id}
```

响应（处理中）：
```json
{
  "task_id": "e5f6g7h8",
  "apk_id": "a1b2c3d4",
  "status": "processing",
  "created_at": "2026-02-13T10:00:00Z",
  "completed_at": null,
  "download_url": null,
  "rule_results": [],
  "error": null
}
```

响应（已完成）：
```json
{
  "task_id": "e5f6g7h8",
  "apk_id": "a1b2c3d4",
  "status": "completed",
  "created_at": "2026-02-13T10:00:00Z",
  "completed_at": "2026-02-13T10:00:15Z",
  "download_url": "/api/v1/download/e5f6g7h8",
  "rule_results": [
    {"rule_index": 0, "success": true, "message": "替换了 2 处匹配"},
    {"rule_index": 1, "success": true, "message": "图片替换成功"}
  ],
  "error": null
}
```

#### 第六步：下载修改后的 APK

```bash
curl -OJ http://localhost:8000/api/v1/download/{task_id}
```

---

## API 参考

| 方法 | 路径 | 描述 |
|------|------|------|
| `GET` | `/health` | 健康检查 |
| `GET` | `/` | Web UI 首页 |
| `POST` | `/api/v1/apks` | 上传 APK 文件（multipart/form-data） |
| `GET` | `/api/v1/apks` | 获取已上传 APK 列表 |
| `DELETE` | `/api/v1/apks/{apk_id}` | 删除 APK 及关联资源 |
| `GET` | `/api/v1/apks/{apk_id}/files` | 浏览 APK 文件结构 |
| `GET` | `/api/v1/apks/{apk_id}/files/{path}` | 查看文件内容 |
| `GET` | `/api/v1/apks/{apk_id}/tasks` | 获取 APK 关联任务列表 |
| `POST` | `/api/v1/tasks` | 创建修改任务 |
| `GET` | `/api/v1/tasks/{task_id}` | 查询任务状态 |
| `GET` | `/api/v1/download/{task_id}` | 下载修改后的 APK |

## 替换规则详解

### 脚本替换（ScriptRule）

用于替换 APK 内文本文件中的内容，如 XML、smali 等。

```json
{
  "type": "script",
  "target_path": "res/values/strings.xml",
  "pattern": "旧文本",
  "replacement": "新文本",
  "use_regex": false
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | string | 是 | 固定为 `"script"` |
| `target_path` | string | 是 | APK 内目标文件的相对路径 |
| `pattern` | string | 是 | 要匹配的文本或正则表达式 |
| `replacement` | string | 是 | 替换后的文本 |
| `use_regex` | bool | 否 | 默认 `false`，设为 `true` 时 `pattern` 使用 Python 正则语法 |

正则示例：
```json
{
  "type": "script",
  "target_path": "smali/com/example/Config.smali",
  "pattern": "const-string v0, \"https?://[^\"]+\"",
  "replacement": "const-string v0, \"https://new-server.com/api\"",
  "use_regex": true
}
```

### 图片替换（ImageRule）

用于替换 APK 内的图片资源文件。

```json
{
  "type": "image",
  "target_path": "res/drawable-hdpi/ic_launcher.png",
  "image_data": "iVBORw0KGgoAAAANSUhEUg..."
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | string | 是 | 固定为 `"image"` |
| `target_path` | string | 是 | APK 内目标图片的相对路径 |
| `image_data` | string | 是 | 替换图片的 Base64 编码数据（不含 `data:image/...;base64,` 前缀） |

生成 Base64 数据：
```bash
base64 -i new_icon.png | tr -d '\n'
```

### 规则验证

- `target_path` 不能为空
- `target_path` 不能包含 `..`（防止路径遍历）
- `target_path` 不能是绝对路径
- `pattern` 不能为空（脚本规则）
- `image_data` 必须是合法的 Base64 编码（图片规则）
- `use_regex: true` 时 `pattern` 必须是合法的正则表达式

## 错误码

| HTTP 状态码 | 错误码 | 说明 |
|-------------|--------|------|
| 400 | `INVALID_APK_FORMAT` | 上传文件不是有效的 APK（缺少 PK 魔数或 AndroidManifest.xml） |
| 400 | `INVALID_RULE` | 规则格式验证失败 |
| 404 | `APK_NOT_FOUND` | 指定的 APK ID 不存在 |
| 404 | `TASK_NOT_FOUND` | 指定的任务 ID 不存在 |
| 404 | `FILE_NOT_FOUND` | APK 内部文件路径不存在 |
| 404 | `DOWNLOAD_NOT_FOUND` | 下载文件不存在或任务未完成 |
| 409 | `CACHE_NOT_READY` | APK 缓存尚未就绪 |
| 413 | `FILE_TOO_LARGE` | 文件超过 500 MB 限制 |
| 500 | `DECOMPILE_ERROR` | apktool 反编译失败 |
| 500 | `PROCESSING_ERROR` | 任务处理过程中发生错误 |

## 测试

```bash
python -m pytest tests/ -v
```

共 143 个测试用例，覆盖单元测试和属性测试（hypothesis）。

## 项目结构

```
├── app/
│   ├── main.py              # FastAPI 入口，CORS，静态文件，健康检查
│   ├── state.py             # 共享状态（内存存储）
│   ├── models/
│   │   └── schemas.py       # Pydantic 数据模型
│   ├── routers/
│   │   ├── apk_router.py    # APK 上传/管理/浏览路由
│   │   └── task_router.py   # 任务创建/查询/下载路由
│   └── services/
│       ├── storage_service.py   # 文件存储管理
│       ├── apk_processor.py     # APK 反编译/缓存/打包
│       └── rule_engine.py       # 规则验证与执行
├── static/
│   └── index.html           # Bootstrap 5 Web UI
├── tests/                   # 测试文件（143 个用例）
├── data/                    # 运行时数据目录
│   ├── uploads/             # 上传的原始 APK
│   ├── cache/               # apktool 反编译缓存
│   ├── workspace/           # 任务工作副本
│   └── output/              # 修改后的 APK
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## License

MIT
