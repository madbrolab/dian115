# 错误码与调试

插件开发时必须先判断错误发生在哪一层。WASM import 状态、Host API 的 HTTP 状态、运行时回调状态和 process JSON-RPC error 是四套不同信号，不能把它们混成一个布尔值。

## 1. 四层结果模型

### 1.1 WASM Host Call 状态

`dian115.host_call` 返回一个打包后的 `i64`。高 32 位是 ABI 状态，低 32 位是长度；完整编码见 [运行时与回调契约](runtime-contract-v1.md)。

| 状态 | 含义 | guest 应做什么 |
| --- | --- | --- |
| `0` | Host Call 已执行，响应 JSON 已写入 guest 缓冲区 | 按低 32 位读取响应，再判断其中的 HTTP `status` |
| `1` | 响应缓冲区过小，低 32 位是所需字节数 | 扩大缓冲区并以完全相同的请求重试；本次没有响应正文 |
| `2` | ABI、内存、请求 JSON、大小限制、上下文或宿主调度错误 | 本次没有可解析的 Host API 响应；记录上下文并让当前 invocation 失败 |

状态 `0` 不代表业务成功。404、409、429、500 等 Host API 响应也会正常封装，并返回 ABI 状态 `0`。

### 1.2 HostCallResponse 与 HTTP Problem

成功完成一次 transport 后，WASM 与 process 的 `host.call` 都会得到同一语义的响应：

```json
{
  "status": 409,
  "headers": {"Content-Type": ["application/problem+json"]},
  "body_base64": "eyJ0eXBlIjoiaHR0cHM6Ly8uLi4ifQ=="
}
```

先 base64 解码 `body_base64`。2xx JSON 通常使用统一数据 envelope：

```json
{
  "data": {},
  "meta": {
    "request_id": "req_...",
    "idempotent_replay": false
  }
}
```

非 2xx 通常是 `application/problem+json`：

```json
{
  "type": "https://dian115.example/problems/conflict",
  "title": "Conflict",
  "status": 409,
  "code": "conflict",
  "detail": "资源状态已变化",
  "request_id": "req_...",
  "retryable": false
}
```

程序逻辑使用稳定的 `code`，日志同时记录 `request_id`；不要匹配可能翻译或调整的 `title`、`detail`。只有 `retryable: true` 且业务仍有意义时才重试。

### 1.3 Runtime callback 状态

UI action 的运行时响应必须是 JSON 对象，`status` 只能是：

| `status` | 含义 |
| --- | --- |
| `succeeded` | 当前 action 已同步完成 |
| `failed` | action 已执行并产生终态失败；这是有效的协议响应，不是 transport 异常 |
| `accepted` | 工作已可靠接收，将异步继续；任务结果应写回 state、插件日志，必要时发送插件通知 |
| `skipped` | 请求有效，但因当前状态、去重或条件不满足而未执行 |

定时 job 只能返回 `accepted` 或 `skipped`；action 必须使用上表四种状态。event 为兼容最小消费者可以返回任意安全 JSON object，但应明确返回 `accepted` 或 `skipped`。缺少 action/job 必需状态、返回不支持的值、无效 JSON 或超过 256 KiB 会变成 `runtime_protocol_error`。不要用进程退出、WASM trap 或 JSON-RPC error 表示一个可预期的业务失败；action 返回 `failed` 并把安全的错误信息写入响应/state。

### 1.4 Process JSON-RPC error

process 插件通过 `Content-Length` 帧传输 JSON-RPC 2.0。RPC error 的结构为：

```json
{
  "jsonrpc": "2.0",
  "id": "h:12",
  "error": {"code": -32602, "message": "invalid params"}
}
```

标准错误建议使用 `-32600`（Invalid Request）、`-32601`（Method not found）、`-32602`（Invalid params）、`-32603`（Internal error）。宿主调用插件时，RPC error 表示协议/运行时拒绝，通常映射为 `runtime_rejected`；业务终态仍应放在正常 `result` 的 callback `status` 中。

插件调用宿主时目前还可能收到：

- `-32001`：`host.call` 在 transport/ABI 层无法执行。
- `-32002`：插件日志被拒绝。
- `-32601`：插件请求了未知的 host 方法。
- `-32602`：`host.log` 参数无效。

一个 RPC error 只结束对应 `id` 的请求。无效帧、错误 `Content-Length`、未知字段、超过 256 KiB 或向 stdout 写普通文本会破坏整个协议连接；普通诊断文本必须写 stderr 或调用 `host.log`。

## 2. 稳定错误码

以下 `application/problem+json.code` 或运行时错误码可用于程序分支。某个 endpoint 是否会返回该码，以 [Host API 参考](host-api-reference.md) 为准。

| code | 常见含义 | 推荐处理 |
| --- | --- | --- |
| `invalid_request` | 参数、JSON、header、路径或状态不合法 | 修正请求，不自动重试 |
| `unauthorized` | 插件调用身份不存在或已失效 | 结束当前调用，等待宿主恢复 |
| `license_required` | 宿主许可当前不可用 | 提示用户检查宿主状态 |
| `capability_denied` | manifest 没声明所需接口/能力，或安装许可不包含它 | 提高版本并修正声明，不能在运行时绕过 |
| `permission_denied` | 宿主文件系统或底层服务拒绝访问 | 让用户检查挂载和宿主配置 |
| `not_found` | 通用对象不存在，如 KV、job | 重新读取或创建，避免盲重试 |
| `resource_not_found` | 账号、目录、文件、watch、运行时资源不存在或引用已失效 | 重新使用 picker/列表接口获取引用 |
| `account_unavailable` | 目标主账号/备用账号不可用 | 让用户重选账号，或稍后按策略重试 |
| `version_conflict` | KV/storage 的 `If-Match` 版本过期 | GET 最新值、合并，再用新版本提交 |
| `conflict` | 资源状态不允许当前操作 | 刷新资源状态后决定是否重试 |
| `quota_exceeded` | 存储、响应大小或其他配额超限 | 减少请求/内容，不原样重试 |
| `rate_limited` | 调用或插件通知超过限流 | 尊重 `retryable`/`Retry-After`，退避并加抖动 |
| `network_error` | 外部来源、代理或上游网络失败 | 保留幂等键并指数退避；向用户显示目标 origin |
| `idempotency_conflict` | 同一个 Idempotency-Key 被用于不同请求 | 这是调用方错误；为新操作生成新键 |
| `idempotency_in_progress` | 相同写请求仍在处理 | 稍后用同一键和同一请求重试 |
| `invocation_conflict` | invocation/delivery ID 被用于不同内容 | 生成新 ID 或修正持久化去重逻辑 |
| `invocation_in_progress` | 相同 invocation 仍在执行 | 保持同一 ID，稍后查询/重试 |
| `plugin_disabled` | 安装实例已禁用 | 停止后台工作，等待用户启用 |
| `runtime_invalid` | 已安装 runtime/UI/manifest 元数据不成立 | 修复插件包并发布新版本 |
| `runtime_protocol_error` | runtime 返回非法 envelope、JSON 或帧 | 修复协议实现；不要自动无限重试 |
| `runtime_rejected` | runtime trap、RPC error 或主动拒绝 | 查看插件日志；仅在明确瞬时错误时重试 |
| `runtime_unavailable` | runtime 未启动、正在回退或暂时失联 | 有界退避，保留同一 invocation ID |
| `runtime_unsupported` | 当前 runtime 类型/协议不受支持 | 按当前文档重新构建并发布新版本 |

## 3. 幂等与重试

所有会产生副作用的 Host API 按参考文档传 `Idempotency-Key`。合法值为 16–128 个可打印 ASCII 字符；推荐 `<plugin-id>:<operation>:<持久化UUID>`。同一个逻辑操作在超时、`network_error`、`idempotency_in_progress` 或可重试 5xx 后必须复用同一个 key 和完全相同的 method、path、query、body；改变任一内容就生成新 key。

```text
io.example.helper:transfer:0191c08f-8ed1-7c56-a87d-f4e556ca9337
```

不要把时间戳每次重新生成后当作重试 key，否则超时后的重复请求可能创建两份任务。收到 `meta.idempotent_replay: true` 表示宿主返回了第一次已保存的结果，按成功/失败原结果处理即可。

推荐重试策略：初始 1 秒，指数退避到 30 秒并加入随机抖动；前台 action 有界重试，后台任务把下次尝试时间写入私有 storage。`invalid_request`、`capability_denied`、`idempotency_conflict` 和确定的 4xx 不重试。

## 4. 常见问题定位

### 安装与签名

| 现象 | 检查 |
| --- | --- |
| `key_id` 不匹配 | 用 `sha256(raw public key)` 重新计算；确认 manifest 与 signature 使用同一值，base64url 没有 `=` |
| Ed25519 验签失败 | 确认签名消息有两个 NUL；manifest/integrity 使用 RFC 8785 JCS；签名后未改文件 |
| integrity size/hash 不一致 | 对 ZIP 内原始字节计算，不对工作区文件计算；检查 LF/CRLF、JSON 格式化和 SVG 优化 |
| ZIP member 未登记 | integrity 必须覆盖除自身和 signature 外的每个成员；不要 `zip -r` 加入目录或隐藏文件 |
| 路径或文件类型被拒绝 | 检查绝对路径、`..`、反斜杠、符号链接、NFC/大小写冲突和 Unix mode |
| process 无法启动 | 确认架构是与宿主一致的 Linux amd64/arm64、入口 `0755`、程序已静态链接；再检查宿主内核是否提供 Landlock ABI 3+，沙箱无法完整建立时会 fail closed |

完整规则见 [打包、完整性与签名](packaging-signing.md)。

### UI 与 state

| 现象 | 检查 |
| --- | --- |
| `duplicate ui field id "name"` | 同一 UI 文档中的 section、field、action ID 必须在各自校验范围唯一；给重复字段使用语义化 key/ID，不要复制后遗留同名 ID |
| 页面空白或显示 `null` | `source` 从 `state` 根开始解析，确认 state 返回对象且路径存在；不要把原始 JSON 当成页面 |
| picker 没有账号/目录 | picker 的 options/source 必须指向数组；每个 option 提供文档要求的 label 与稳定 value/ref；账号与目录引用要来自宿主接口 |
| 点击按钮无响应 | action ID 必须在 UI schema 声明，runtime 响应必须是合法 callback JSON；检查 invocation 与插件日志 |
| 修改 UI 后仍显示旧版 | 包内容变化必须提高版本、新文件名和 SHA-256；刷新具体仓库后升级插件 |

完整字段与响应式状态规则见 [声明式 UI 开发手册](ui-development-guide.md)。

### 权限、事件与后台任务

| 现象 | 检查 |
| --- | --- |
| `capability_denied` | manifest 与市场 index 必须逐项声明准确的 `METHOD + path`；安装后不能动态扩大权限 |
| 外部网站访问失败 | origin 必须精确为 `https://host[:port]`，方法和 `proxy_mode` 必须声明；重定向目标也必须获批 |
| watch 创建成功但没收到事件 | `event_topic` 必须同时列入 manifest `events`，并声明 `files.watch`/`events.subscribe` 对应 API 能力 |
| job 不执行 | job ID/handler 必须在 manifest `jobs` 中，cron 合法，插件已启用且 runtime 健康 |
| CD2 与本地路径行为不符 | 只传宿主 picker/文件接口返回的 root/ref；不要猜挂载前缀或自行把 host path 转成 CD2 路径 |

### 市场缓存与升级

1. 确认刷新的是具体自定义仓库，而不是只切换市场 TAB。
2. 用浏览器或 `curl` 获取 index 的最终 HTTPS URL，检查版本、包 URL 和 SHA-256。
3. 每次字节变化提高 SemVer 并使用新包名；不要覆盖相同 URL 的同版本包。
4. 相对 `package_url`、`icon_url` 以 index URL 为基准解析；确认跳转后仍是 HTTPS。
5. 对比市场权限与包内 manifest，二者必须完全一致。

## 5. 诊断信息与大小限制

报告问题时至少记录：插件 ID/版本、运行时类型、action/job/event ID、invocation ID、Host API method/path、HTTP status、problem `code`/`request_id`、是否幂等重放，以及脱敏后的插件日志。不要记录 Cookie、token、账号凭据、签名 seed、外部站点授权 header 或完整隐私路径。

关键限制：

- WASM invocation request 与 response：各 256 KiB。
- WASM `host_call` request 与 response：各 256 KiB；短缓冲用 ABI 状态 `1` 协商。
- WASM `log` import 单次输入：最多 16 KiB，最终单条 message/fields 各最多 8 KiB。
- process JSON-RPC 单帧：256 KiB；header：8 KiB；stdout 只能输出协议帧。
- manifest、UI、integrity、signature 单个 JSON：最多 256 KiB。
- 插件独立日志：每个安装实例最多 4 MiB、5000 条，保留 14 天，先达到任一条件即裁剪。

先在插件中心查看 runtime 健康状态和独立日志，再对照 [运行时契约](runtime-contract-v1.md)、[Host API 参考](host-api-reference.md) 和 [OpenAPI](openapi-v1.yaml)。
