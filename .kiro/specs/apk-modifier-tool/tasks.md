# Implementation Plan: APK 修改工具后端服务

## Overview

基于 Python + FastAPI 实现 APK 修改工具后端服务，核心优化为"一次上传，多次修改下载"。按照数据模型 → 核心组件（Rule Engine、Storage、APK Processor） → API 路由 → 集成的顺序逐步构建，每个阶段包含对应的测试任务。

## Tasks

- [x] 1. 项目初始化与数据模型
  - [x] 1.1 创建项目结构和依赖配置
    - 创建 `pyproject.toml` 或 `requirements.txt`，包含 fastapi、uvicorn、pydantic、python-multipart、hypothesis、pytest、pytest-asyncio 依赖
    - 创建目录结构：`app/`、`app/models/`、`app/services/`、`app/routers/`、`tests/`
    - 创建 `app/main.py` FastAPI 应用入口
    - _Requirements: 全部_

  - [x] 1.2 实现数据模型
    - 在 `app/models/schemas.py` 中实现所有 Pydantic 模型：RuleType、ScriptRule、ImageRule、ReplacementRule、TaskStatus、RuleResult、CreateTaskRequest、TaskResponse、TaskSummary、FileNode、CacheStatus、APKUploadResponse、APKInfo、ValidationError、ValidationResult
    - _Requirements: 2.1, 2.2, 4.1, 7.1, 7.2, 8.1, 8.2_

  - [ ]* 1.3 编写规则序列化往返属性测试
    - **Property 12: 规则序列化往返一致性**
    - 使用 hypothesis 生成随机 ScriptRule 和 ImageRule，验证 JSON 序列化再反序列化后与原始对象等价
    - **Validates: Requirements 7.3**

- [x] 2. 实现 Rule Engine
  - [x] 2.1 实现规则验证逻辑
    - 在 `app/services/rule_engine.py` 中实现 `RuleEngine.validate_rules()` 方法
    - 验证 target_path 非空、不包含 `..` 路径遍历、格式合法
    - 验证 ScriptRule 的 pattern 字段非空，use_regex=True 时验证正则表达式语法
    - 验证 ImageRule 的 image_data 为有效 Base64 编码
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [ ]* 2.2 编写规则验证属性测试
    - **Property 3: 有效规则验证通过**
    - **Property 4: 无效规则路径拒绝**
    - **Property 5: 批量验证完整性**
    - 使用 hypothesis 生成有效和无效的规则，验证验证逻辑的正确性
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4**

  - [x] 2.3 实现脚本替换逻辑
    - 在 `app/services/rule_engine.py` 中实现 `RuleEngine.apply_script_rule()` 方法
    - 支持普通文本匹配和正则表达式匹配（根据 use_regex 字段）
    - 读取目标文件内容，执行替换，写回文件
    - 目标文件不存在时返回失败的 RuleResult
    - _Requirements: 2.5, 3.2, 3.4_

  - [x] 2.4 实现图片替换逻辑
    - 在 `app/services/rule_engine.py` 中实现 `RuleEngine.apply_image_rule()` 方法
    - 将 Base64 编码的 image_data 解码并写入目标路径
    - 目标文件不存在时返回失败的 RuleResult
    - _Requirements: 3.3, 3.4_

  - [ ]* 2.5 编写替换逻辑属性测试
    - **Property 6: 脚本替换正确性**
    - **Property 7: 图片替换正确性**
    - 使用 hypothesis 生成随机文件内容和替换规则，验证替换结果的正确性
    - **Validates: Requirements 2.5, 3.2, 3.3**

- [x] 3. Checkpoint - 确保核心逻辑测试通过
  - 确保所有测试通过，如有问题请向用户确认。

- [x] 4. 实现 Storage Service
  - [x] 4.1 实现文件存储服务
    - 在 `app/services/storage_service.py` 中实现 StorageService
    - 实现 `save_upload()`：生成 UUID 作为 apk_id，保存文件到 `data/uploads/`
    - 实现 `get_apk_path()`、`get_cache_dir()`、`get_work_dir()`、`get_output_path()`、`file_exists()`
    - 实现 APK 格式验证（检查 ZIP 魔数和 AndroidManifest.xml 存在性）
    - 实现 `list_apks()`：扫描 uploads 目录，返回 APK 信息列表
    - 实现 `delete_apk()`：删除原始 APK、缓存目录和关联的输出 APK
    - 创建 `data/` 目录结构（uploads、cache、workspace、output）
    - _Requirements: 1.1, 1.3, 1.4, 5.1, 5.3, 8.1, 8.3_

  - [ ]* 4.2 编写存储服务属性测试
    - **Property 1: 上传往返一致性**
    - **Property 10: 下载 URL 唯一性**
    - **Property 15: APK 删除完整性**
    - **Validates: Requirements 1.1, 5.3, 8.3**

- [x] 5. 实现 APK Processor（含缓存机制）
  - [x] 5.1 实现 APK 反编译与缓存
    - 在 `app/services/apk_processor.py` 中实现 APKProcessor
    - 实现 `decompile_to_cache()`：调用 apktool d 命令反编译 APK 到 `data/cache/{apk_id}/decompiled/`
    - 实现 `copy_cache_to_workdir()`：使用 shutil.copytree 从缓存目录复制工作副本到 `data/workspace/{task_id}/`
    - 实现 `recompile()`：调用 apktool b 命令重新打包 APK
    - _Requirements: 1.2, 3.1, 3.7_

  - [x] 5.2 实现缓存目录浏览功能
    - 实现 `list_files_from_cache()`：遍历缓存目录构建 FileNode 树
    - 实现 `read_file_from_cache()`：从缓存目录读取指定文件的文本内容
    - 验证文件路径不包含路径遍历攻击
    - _Requirements: 6.1, 6.2, 6.3_

  - [x] 5.3 实现完整的修改任务流程
    - 实现 `process_task()`：复制缓存 → 应用规则 → 重新打包 → 存储输出
    - 任务失败时清理工作副本目录
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [ ]* 5.4 编写缓存不可变性属性测试
    - **Property 8: 缓存不可变性**
    - 创建临时缓存目录，执行复制和修改操作后，验证缓存目录内容未变
    - **Validates: Requirements 3.1, 3.7**

  - [ ]* 5.5 编写缓存读取准确性属性测试
    - **Property 11: 缓存文件读取准确性**
    - 创建临时目录结构，验证 list_files_from_cache 和 read_file_from_cache 返回正确结果
    - **Validates: Requirements 6.1, 6.2**

- [x] 6. Checkpoint - 确保存储和处理器测试通过
  - 确保所有测试通过，如有问题请向用户确认。

- [x] 7. 实现 API 路由层
  - [x] 7.1 实现 APK 上传和管理路由
    - 在 `app/routers/apk_router.py` 中实现：
    - `POST /api/v1/apks`：接收 multipart 文件上传，调用 StorageService 存储，调用 APKProcessor 反编译到缓存，返回 APKUploadResponse
    - `GET /api/v1/apks`：调用 StorageService.list_apks()，返回 APK 列表
    - `DELETE /api/v1/apks/{apk_id}`：调用 StorageService.delete_apk()，删除 APK 及关联资源
    - 实现文件大小限制检查和错误处理
    - 反编译失败时清理已存储的 APK 文件
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 8.1, 8.3_

  - [x] 7.2 实现 APK 浏览路由
    - 在 `app/routers/apk_router.py` 中实现：
    - `GET /api/v1/apks/{apk_id}/files`：从缓存读取文件树
    - `GET /api/v1/apks/{apk_id}/files/{path:path}`：从缓存读取文件内容
    - `GET /api/v1/apks/{apk_id}/tasks`：返回该 APK 关联的任务列表
    - 检查缓存状态，未就绪时返回 409
    - _Requirements: 6.1, 6.2, 6.3, 8.2_

  - [x] 7.3 实现任务和下载路由
    - 在 `app/routers/task_router.py` 中实现：
    - `POST /api/v1/tasks`：验证规则，检查缓存就绪，创建任务，启动后台处理，返回 task_id
    - `GET /api/v1/tasks/{task_id}`：查询任务状态，返回 TaskResponse
    - `GET /api/v1/download/{task_id}`：返回修改后 APK 的文件流，设置正确的响应头
    - 使用 FastAPI BackgroundTasks 执行异步 APK 处理
    - _Requirements: 3.1, 4.1, 4.2, 4.3, 5.1, 5.2, 5.3_

  - [ ]* 7.4 编写任务状态一致性属性测试
    - **Property 9: 任务状态响应一致性**
    - 验证不同状态下 TaskResponse 字段的一致性约束
    - **Validates: Requirements 4.1, 4.2, 4.3**

  - [ ]* 7.5 编写 API 路由单元测试
    - 使用 FastAPI TestClient 测试各端点
    - 测试错误响应格式和 HTTP 状态码
    - 测试无效文件上传返回 400
    - 测试不存在的资源返回 404
    - 测试缓存未就绪返回 409
    - _Requirements: 1.2, 1.3, 1.6, 4.1, 5.2, 6.3_

- [x] 8. 集成与连接
  - [x] 8.1 连接所有组件并配置应用
    - 在 `app/main.py` 中注册所有路由
    - 配置 CORS 中间件
    - 添加应用启动时创建数据目录的逻辑
    - 添加全局异常处理器，统一错误响应格式
    - 实现内存中的任务和 APK 元数据存储（dict）
    - _Requirements: 全部_

  - [ ]* 8.2 编写集成测试
    - 测试完整的上传 → 浏览文件 → 创建任务 → 查询状态 → 下载流程
    - 测试同一 APK 创建多个不同修改任务的场景
    - 测试删除 APK 后关联资源清理
    - 使用测试用 APK 文件（小型 ZIP 文件模拟）
    - **Property 13: APK 列表完整性**
    - **Property 14: APK 关联任务列表完整性**
    - _Requirements: 1.1, 3.1, 4.1, 5.1, 8.1, 8.2_

- [x] 9. Final checkpoint - 确保所有测试通过
  - 确保所有测试通过，如有问题请向用户确认。

## Notes

- 标记 `*` 的任务为可选任务，可跳过以加快 MVP 开发
- 每个任务引用了具体的需求编号以确保可追溯性
- Checkpoint 任务用于阶段性验证
- 属性测试验证通用正确性属性，单元测试验证具体示例和边界情况
- 系统依赖 `apktool` 命令行工具，需确保运行环境已安装
- 核心优化：APK 上传时立即反编译缓存，后续任务从缓存复制副本，避免重复解压
