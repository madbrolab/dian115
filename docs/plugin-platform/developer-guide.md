# DIAN115 插件开发指南

## 1. 选择运行时

插件包是签名的 `.d115p` ZIP：

```text
manifest.json
ui/schema.json                 # 可选
ui/icon.svg                    # 可选
runtime/plugin.wasm
integrity.json
signature.json
```

轻量插件使用 `wasm`。WASM 仅导出 `memory`、`dian115_alloc`、`dian115_invoke`（`dian115_free` 可选），仅导入 `dian115.host_call` 和 `dian115.log`；它不能启动进程、读环境变量、读数据库、访问文件系统或打开 socket。函数签名、`i64` 编码、短缓冲和内存所有权见[运行时与回调契约](runtime-contract-v1.md)。

仓库中的[最小零权限 WASM 示例](examples/in-process-wasm-status/)已经使用 Plugin API v2，可直接参考其 manifest、状态响应、声明式 UI、完整性清单和 Ed25519 签名。它只演示运行时与打包契约，故意不申请 Host API 或外部网络权限；需要调用 115、文件/CD2、订阅、TMDB、通知或外部网站时，仍须按下文在 manifest 中逐项声明。

需要常驻循环、第三方运行库或自主后台任务的插件使用 `process`，包结构中的运行文件改为 Linux 可执行文件：

```text
manifest.json
ui/schema.json                 # 可选
ui/icon.svg                    # 可选
runtime/plugin                 # Linux 可执行文件，ZIP 中保留执行位
integrity.json
signature.json
```

DIAN115 在当前容器内启动并监管该进程；插件不创建额外 Docker 服务、不监听 HTTP 端口，也不持有 DIAN115 Token。启用时启动，禁用、更新、卸载和宿主退出时停止，崩溃时由宿主退避重启。process 可以常驻循环和启动包内子进程，但会在进入插件入口前强制应用 Landlock 与 seccomp：包目录只读且可执行，插件私有 data 目录可读写但不可执行，其他宿主路径不可访问，直接 socket/外部网络被阻止；子进程继承同一限制。沙箱建立失败或 Landlock ABI 低于 3 时拒绝启动，不会退化为无沙箱运行。115、文件/CD2、TMDB、订阅、通知和外部 HTTPS 都必须通过安装时声明并获批的 `host.call`。完整边界见[进程运行时协议](process-runtime-v1.md)。

## 2. manifest

manifest 最小结构如下（完整字段以 `manifest.schema.json` 为准）：

```json
{
  "schema_version": 1,
  "id": "example.media-helper",
  "name": "媒体助手",
  "version": "1.0.0",
  "description": "查询媒体并创建任务。",
  "default_locale": "zh-CN",
  "publisher": {"name": "Example", "key_id": "ed25519:..."},
  "compatibility": {"dian115": ">=3.8.47 <4.0.0", "plugin_api": "^2.0"},
  "runtime": {"kind": "wasm", "entry": "runtime/plugin.wasm", "abi": "dian115:plugin@1"},
  "permissions": {
    "apis": [
      {"method": "GET", "path": "/api/tmdb/movie/:id", "reason": "显示电影详情"},
      {"method": "POST", "path": "/api/115/offline/add", "reason": "创建离线任务"}
    ],
    "network": []
  },
  "ui": {"schema": "ui/schema.json", "icon": "ui/icon.svg"}
}
```

常驻进程只把 `runtime` 改为：

```json
{
  "kind": "process",
  "entry": "runtime/plugin",
  "protocol": "dian115:process@1",
  "startup_timeout_ms": 10000,
  "shutdown_timeout_ms": 5000,
  "timeout_ms": 30000,
  "background_timeout_ms": 300000,
  "max_concurrency": 4,
  "restart_policy": "on-failure"
}
```

进程入口必须是包内完整性清单覆盖的 Linux ELF，并保留可执行位；当前只支持 `linux/amd64` 与 `linux/arm64`。由于沙箱不允许读取或执行宿主的动态链接器和共享库，入口及包内子程序应构建为自包含的静态链接文件，并按架构分别发布。stdio 协议、进程环境、关闭与重启语义见[进程运行时协议](process-runtime-v1.md)。

`path` 使用宿主登记的路径模板；参数放在 query、path 或 JSON body 中，不要把账号 Cookie 或凭据放进请求。插件不能猜测宿主文件系统布局；只有文件/目录 picker 或 Host API 返回的已授权 host path/ref 才能回传给文件与 watch 接口。写操作带稳定的 `Idempotency-Key`。不要声明未实际使用的接口。

## 3. 通用 host_call

本节只展示 JSON 形状；WASM 的精确 import/export ABI、ptr/len、`i64` 返回值、256 KiB 上限，及 health/state/action/job/event 的完整 envelope 以[运行时与回调契约](runtime-contract-v1.md)为准。`dian115:process@1` 当前稳定支持 `state`、`action`、`job` 和 `event`，全部通过 JSON-RPC stdio 的 `runtime.invoke` 承载；process 的健康状态由初始化握手、进程存活与退出状态判断，而不是额外承诺一个 `health` invocation。

一次 `dian115_invoke` 接收 JSON 信封：

```json
{"op":"action","invocation_id":"inv_01","payload":{"id":"search","input":{"query":"沙丘"}}}
```

调用 DIAN115 主项目接口时发送：

```json
{
  "method": "GET",
  "path": "/api/tmdb/movie/693134",
  "headers": {"accept": "application/json"},
  "body_base64": ""
}
```

宿主在进程内执行真实接口并返回：

```json
{"status":200,"headers":{"content-type":["application/json"]},"body_base64":"eyJkYXRhIjp7fX0"}
```

禁止设置 `Host`、`Cookie`、`Authorization`、`Proxy-Authorization` 或宿主身份头。响应中的凭据、内部路径和敏感 header 会被过滤。错误使用 `application/problem+json`，插件应根据稳定的 `code` 处理。

调用已声明的外部网络来源时使用同一个 `host_call`，把完整 HTTPS URL 放在 `path`：

```json
{
  "method": "GET",
  "path": "https://example.com/v1/items",
  "headers": {"accept": "application/json"},
  "body_base64": ""
}
```

宿主只允许 manifest `permissions.network` 中声明的 HTTPS origin、方法和 `proxy_mode`；外部请求不会获得 DIAN115 管理员 Cookie 或主项目凭据。

## 4. TMDB（宿主缓存）

TMDB 查询必须走登记的宿主接口，不能使用 `network` 直连 TMDB。宿主自动使用配置的语言、代理、轮换 Key 和缓存；命中缓存时插件无需承担网络请求。当前已登记的查询路径包括：

```text
GET /api/tmdb/search
GET /api/tmdb/movie/:id
GET /api/tmdb/tv/:id
GET /api/tmdb/trending
GET /api/tmdb/discover/movie
GET /api/tmdb/discover/tv
GET /api/tmdb/genres
```

具体 query 参数、缓存语义和响应见 [Host API 参考](host-api-reference.md)与 [OpenAPI](openapi-v1.yaml)；插件不得猜测未登记的 TMDB v3 路径。图片使用宿主返回的地址；只有在 manifest 另行声明对应 HTTPS origin 后才能直连外部图片域名。当前安装环境的可用接口目录可在插件中心“仓库与开发”中查看。

## 5. 115、多账号与文件/CD2

插件先调用登记的账号选项接口，让用户选择 `main`、`backup_pool` 或指定备用账号；随后把宿主返回的账号选择值原样放入业务请求。插件不读取 Cookie，也不自行轮询账号。

目录、离线任务、离线额度和默认离线目录的 GET 请求使用 `account_mode` 与可选的 `account_id` query；离线新增、删除、清理、重试和分享转存的 POST 请求使用 `{"account":{"mode":"backup","id":12}}`。省略账号选择时保持主账号兼容行为。`backup_pool` 每次请求只选择一次，并在响应的 `account` 中返回实际账号摘要；后续必须继续操作同一账号时，改用该摘要中的 `id` 和 `backup` 模式。

文件操作直接提交宿主 picker/接口返回的目录标识、ref 或授权 host path。不要从显示名称拼接路径，也不要假设 `/config`、`/media` 或 CD2 挂载前缀。115 云端目录只能在同一账号上下文内操作。源和目的都是 CD2 挂载目录时宿主走 CD2 gRPC；任一端不是 CD2 目录时，宿主按已暴露的本地挂载路径执行。插件不能取得 gRPC 凭据。

## 6. 订阅、通知、调度与监控

### 6.1 订阅业务

宿主登记了不暴露站点或下载器凭据的订阅业务接口，以下 16 个操作全部可在 `permissions.apis` 中逐项声明并直接调用：

```text
GET    /api/subscribe/records
DELETE /api/subscribe/records/:id
PUT    /api/subscribe/records/:id/status
GET    /api/subscribe/pool/intents
POST   /api/subscribe/pool/intents
GET    /api/subscribe/pool/intents/:id
PATCH  /api/subscribe/pool/intents/:id/episodes
DELETE /api/subscribe/pool/intents/:id
GET    /api/pt/subscriptions
POST   /api/pt/subscriptions
GET    /api/pt/subscriptions/:id
DELETE /api/pt/subscriptions/:id
POST   /api/pt/subscriptions/:id/cancel
POST   /api/pt/subscriptions/:id/search
GET    /api/pt/subscriptions/:id/attempts
GET    /api/pt/subscriptions/:id/download-tasks
```

这些接口使用宿主已配置的 PT 站点、TMDB、代理和下载器，但不会向插件返回相关凭据。PT 执行记录的 `download_url` 会由宿主删除；PT 搜索、站点/RSS、全局订阅设置和下载器管理接口不在插件接口目录中。`dangerous` 风险接口会在安装页明确显示，写操作仍必须使用 `Idempotency-Key`。

`GET /api/subscribe/records`、`DELETE /api/subscribe/records/:id` 与 `PUT /api/subscribe/records/:id/status` 直接沿用主项目 Handler 的请求、ID 和状态语义；宿主不生成插件专用 ID，也不缩窄可提交的状态。管理 PT 或聚合订阅时，也可直接调用上表对应的专用接口。

- 订阅调用直接使用登记的 `/api/...` 订阅接口，响应保持主项目语义。
- 插件通知调用登记的通知接口，宿主以独立 `plugin_notification_message` 类型发送到 Telegram；通知内容必须脱敏。
- manifest 中声明 cron job 后，宿主会在页面关闭时继续调度；同一 job 默认不重叠执行。示例：

```json
{
  "jobs": [
    {
      "id": "refresh-catalog",
      "handler": "refresh_catalog",
      "default_schedule": "0 */6 * * *",
      "allow_overlap": false
    }
  ]
}
```
- 插件通过已批准的 `/api/plugin-runtime/watches` 接口登记持久化目录监控。宿主负责访问所选宿主目录、重启恢复、扫描、稳定 event ID、失败重试和事件投递；process 沙箱不能直接打开这些宿主路径。
- `dian115.log` 和日志接口只写当前安装实例的日志；宿主限制单条大小、总容量和保留天数，超限从最旧记录裁剪。
- KV、任务、事件和日志均按安装实例隔离；禁用插件会停止新调用、调度和事件投递。

### 6.2 目录监控

本地或 CD2 目录直接使用文件管理器/picker 返回的宿主路径；下例路径只是响应值示意，不能由插件硬编码或猜测：

```json
{
  "source": {"kind": "host_path", "path": "/媒体库/待整理"},
  "event_topic": "files.changed",
  "recursive": true,
  "interval_seconds": 30
}
```

路径命中系统配置的 CD2 挂载前缀时，宿主只通过 CD2 gRPC 扫描；其他路径走本地挂载。监控 115 目录时固定账号和 CID，不能在每轮重新抽取备用号池：

```json
{
  "source": {"kind": "115", "account": {"mode": "backup", "id": 12}, "cid": "0"},
  "event_topic": "files.changed",
  "recursive": false,
  "interval_seconds": 60
}
```

可用操作如下，均须逐项写入 `permissions.apis`：

```text
GET    /api/plugin-runtime/watches
POST   /api/plugin-runtime/watches
PATCH  /api/plugin-runtime/watches/:watch_ref
DELETE /api/plugin-runtime/watches/:watch_ref
POST   /api/plugin-runtime/watches/:watch_ref/retry
POST   /api/plugin-runtime/watches/:watch_ref/resync
```

首次成功扫描只建立基线，不产生“全部新增”事件。后续事件至少包含 `watch_ref`、`backend`、`added`、`removed`、`modified`、`occurred_at` 和 `resync_required`。投递达到重试上限后进入 dead letter，不会永久冻结监控；插件可在处理问题后重试，或请求重新建立基线。插件应按稳定 `event_id` 去重。

每个 watch 的 `event_topic` 必须同时列在 manifest 的 `events` 中，否则安装或创建监控会被拒绝：

```json
{"events":["files.changed"]}
```

## 7. UI 与主题

UI 是插件自己的完整工作区，不是调试 JSON 或临时弹窗。使用 `ui-schema-v1.schema.json` 声明应用导航、页面 header、统计、提示、表单、列表/表格、进度、任务、日志和操作；宿主使用与内置功能一致的组件、主题、移动端断点、对话框、加载态、空状态和错误态渲染。插件可选择受控的主题、密度、卡片和布局 token，但不能提交 CSS、HTML、Vue 组件或独立弹窗。

建议把插件拆成少量清晰页面，例如“工作台 / 任务 / 监控 / 日志 / 设置”。桌面端由宿主渲染 tabs 或侧栏，移动端自动变为紧凑导航；URL 会保留当前 view。UI Schema v1 没有 `refresh` 字段：宿主在打开/切换 view、action 完成或 process 发出 `host.ui.invalidate` 后重新获取 state；需要定时变化的数据由 job、watch 或 process 常驻循环更新 state，再触发失效通知。

账号和目录不要渲染成几十张通用卡片。需要 115 账号时使用宿主 `account-picker`，需要本地/CD2/115 目录时使用 `directory-picker`；选项可由 state 中的动态 source 提供。危险操作的 `confirm` 由宿主统一对话框呈现。

需要按权限隐藏 UI 时，`requires_capabilities` 直接填写已声明的 `/api/...` 路径或 HTTPS 来源；不要填写旧的内部 capability 名称。

表单字段 id、action id、view id 和 section id 在各自作用域必须唯一；不要重复使用 `name` 作为同一作用域的两个字段 id。

## 8. 安装、发布与检查

安装页展示运行时类型、所有 `permissions.apis`、`permissions.network`、账号模式、后台调度、目录监控和日志行为；用户一次性整体同意。`process` 还会显示不可隐藏的原生进程说明：它可持续运行和启动包内子进程，但包目录/私有 data、无 socket 和 Host Call 白名单边界由宿主强制执行。接口、域名或运行时声明发生变化必须重新确认。市场索引中的权限与运行时披露必须与包内 manifest 完全一致。

发布前检查：验证 JSON Schema、ZIP 路径、执行位、完整性清单和 Ed25519 签名；只在 Linux/Docker 环境验证 WASM 或原生进程；不要为插件运行额外 Docker 服务。插件市场包通过 HTTPS 发布到自己的发行位置，官方索引只记录签名包 URL、摘要、版本、运行时和权限披露。官方仓库不接收插件或主项目源码。可复制命令见[打包、完整性与签名](packaging-signing.md)，端到端步骤见[快速开始](quickstart.md)。

完整 UI 字段见[声明式 UI 开发手册](ui-development-guide.md)，请求/响应见 [Host API 参考](host-api-reference.md)与 [OpenAPI](openapi-v1.yaml)，错误语义见[错误码与调试](errors-debugging.md)。若某路径尚未出现在接口目录，先等待宿主登记后再写入 manifest；不要自行新增“兼容转换接口”。
