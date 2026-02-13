# 需求文档：APK 修改工具后端服务

## 简介

本系统是一个后端 RESTful API 服务，允许用户上传 APK 文件，系统立即解压并缓存解压后的目录。用户可以定义替换规则（脚本内容替换和图片资源替换），每次创建修改任务时，系统从缓存的解压目录复制一份副本，应用规则后打包生成修改后的 APK 文件，并提供下载链接。同一个 APK 可以反复创建多个不同的修改任务，实现"一次上传，多次修改下载"的高效流程。

## 术语表

- **APK_Modifier_Service**: 核心后端服务，负责接收用户请求、执行 APK 修改操作并返回结果
- **Rule_Engine**: 规则引擎组件，负责解析和执行用户定义的替换规则
- **APK_Processor**: APK 处理组件，负责解压、修改内容和重新打包 APK 文件
- **Storage_Service**: 存储服务组件，负责管理原始 APK、缓存目录和修改后 APK 的网络存储与下载
- **Decompile_Cache**: 解压缓存，存储 APK 上传后立即反编译的目录，供后续多次修改任务复用
- **Replacement_Rule**: 用户定义的替换规则，包含目标文件路径、匹配模式和替换内容
- **Script_Rule**: 针对 APK 内部脚本文件的文本替换规则
- **Image_Rule**: 针对 APK 内部图片资源的图片替换规则
- **Task**: 一次 APK 修改任务，包含源 APK 标识符、替换规则集合和任务状态

## 需求

### 需求 1：APK 文件上传与解压缓存

**用户故事：** 作为用户，我希望上传 APK 文件后系统立即解压并缓存，以便后续多次快速修改而无需重复解压。

#### 验收标准

1. WHEN 用户通过 API 上传一个有效的 APK 文件, THE APK_Modifier_Service SHALL 接收该文件并存储到 Storage_Service 中，返回唯一的文件标识符
2. WHEN APK 文件存储成功, THE APK_Processor SHALL 立即使用 apktool 反编译该 APK 文件，并将解压结果存储到 Decompile_Cache 中
3. WHEN 用户上传的文件不是有效的 APK 格式, THE APK_Modifier_Service SHALL 返回 400 错误响应，包含明确的错误描述信息
4. WHEN 用户上传的文件大小超过系统允许的最大限制, THE APK_Modifier_Service SHALL 返回 413 错误响应，包含文件大小限制说明
5. IF 文件上传过程中发生网络中断或存储失败, THEN THE APK_Modifier_Service SHALL 清理已接收的临时数据并返回 500 错误响应
6. IF APK 反编译过程中发生错误, THEN THE APK_Modifier_Service SHALL 删除已存储的 APK 文件，清理临时数据，并返回 500 错误响应，包含反编译失败原因

### 需求 2：替换规则定义

**用户故事：** 作为用户，我希望能够定义脚本和图片的替换规则，以便系统按照我的规则自动修改 APK 内容。

#### 验收标准

1. WHEN 用户提交脚本替换规则（包含目标文件路径、匹配文本和替换文本）, THE Rule_Engine SHALL 验证规则格式并存储该 Script_Rule
2. WHEN 用户提交图片替换规则（包含目标图片路径和替换图片）, THE Rule_Engine SHALL 验证规则格式并存储该 Image_Rule
3. WHEN 用户提交的规则中目标文件路径为空或格式无效, THE Rule_Engine SHALL 返回 400 错误响应，指明具体的验证失败原因
4. WHEN 用户提交包含多条替换规则的规则集合, THE Rule_Engine SHALL 逐条验证每条规则，并返回所有验证结果
5. THE Rule_Engine SHALL 支持正则表达式作为脚本替换规则的匹配模式

### 需求 3：APK 修改任务执行（基于缓存）

**用户故事：** 作为用户，我希望能够基于同一个已上传的 APK 反复创建修改任务，每次替换不同的资产，实现一次上传多次修改下载。

#### 验收标准

1. WHEN 用户提交修改任务（包含 APK 文件标识符和规则集合）, THE APK_Processor SHALL 从 Decompile_Cache 中复制该 APK 的解压目录副本，在副本上按照规则集合依次执行替换操作，并重新打包为新的 APK 文件
2. WHEN APK_Processor 执行脚本替换规则时, THE APK_Processor SHALL 在目标脚本文件中查找匹配内容并替换为指定文本
3. WHEN APK_Processor 执行图片替换规则时, THE APK_Processor SHALL 将目标路径的图片文件替换为用户提供的新图片
4. WHEN 规则中指定的目标文件在 APK 内不存在, THE APK_Processor SHALL 在任务结果中记录该规则执行失败，并继续执行剩余规则
5. WHEN 所有规则执行完毕, THE APK_Processor SHALL 重新打包 APK 文件并存储到 Storage_Service 中
6. IF APK 副本创建或重新打包过程中发生错误, THEN THE APK_Processor SHALL 终止任务，清理工作副本，并返回详细的错误信息
7. WHEN 多个修改任务同时针对同一个 APK 的 Decompile_Cache 创建副本, THE APK_Processor SHALL 确保各任务的工作副本互相隔离，互不影响

### 需求 4：任务状态查询

**用户故事：** 作为用户，我希望能够查询修改任务的执行状态，以便了解任务进度和结果。

#### 验收标准

1. WHEN 用户查询任务状态, THE APK_Modifier_Service SHALL 返回任务的当前状态（pending、processing、completed、failed）
2. WHEN 任务状态为 completed, THE APK_Modifier_Service SHALL 在响应中包含修改后 APK 的下载链接和每条规则的执行结果
3. WHEN 任务状态为 failed, THE APK_Modifier_Service SHALL 在响应中包含详细的失败原因

### 需求 5：修改后 APK 下载

**用户故事：** 作为用户，我希望能够通过下载链接获取修改后的 APK 文件，以便分发和使用。

#### 验收标准

1. WHEN 用户通过下载链接请求修改后的 APK 文件, THE Storage_Service SHALL 返回该文件的二进制流，并设置正确的 Content-Type 和 Content-Disposition 响应头
2. WHEN 下载链接对应的文件不存在或已过期, THE Storage_Service SHALL 返回 404 错误响应
3. THE Storage_Service SHALL 为每个修改后的 APK 文件生成唯一的下载 URL

### 需求 6：APK 内容浏览

**用户故事：** 作为用户，我希望能够浏览已上传 APK 的内部文件结构，以便确定需要修改的目标文件路径。

#### 验收标准

1. WHEN 用户请求查看已上传 APK 的文件列表, THE APK_Processor SHALL 从 Decompile_Cache 中读取该 APK 的解压目录，返回内部文件和目录的树形结构
2. WHEN 用户请求查看 APK 内某个脚本文件的内容, THE APK_Processor SHALL 从 Decompile_Cache 中读取该文件的文本内容
3. WHEN 用户请求查看的文件路径在 APK 内不存在, THE APK_Processor SHALL 返回 404 错误响应

### 需求 7：规则序列化与反序列化

**用户故事：** 作为用户，我希望能够以 JSON 格式提交和获取替换规则，以便与其他系统集成。

#### 验收标准

1. WHEN 用户以 JSON 格式提交替换规则, THE Rule_Engine SHALL 将 JSON 反序列化为内部 Replacement_Rule 对象
2. THE Rule_Engine SHALL 将内部 Replacement_Rule 对象序列化为 JSON 格式返回给用户
3. FOR ALL 有效的 Replacement_Rule 对象, 序列化为 JSON 再反序列化 SHALL 产生与原始对象等价的结果（往返一致性）

### 需求 8：已上传 APK 管理

**用户故事：** 作为用户，我希望能够查看已上传的 APK 列表及其关联的修改任务，以便管理我的 APK 和历史修改记录。

#### 验收标准

1. WHEN 用户请求已上传 APK 列表, THE APK_Modifier_Service SHALL 返回所有已上传 APK 的信息列表，包含 apk_id、文件名、上传时间和缓存状态
2. WHEN 用户请求某个 APK 的关联任务列表, THE APK_Modifier_Service SHALL 返回该 APK 下所有修改任务的摘要信息
3. WHEN 用户删除一个已上传的 APK, THE Storage_Service SHALL 同时删除原始 APK 文件、Decompile_Cache 中的解压目录以及所有关联的修改后 APK 文件
