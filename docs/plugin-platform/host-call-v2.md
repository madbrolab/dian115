# DIAN115 Host Call v2

`host.call` 是 WASM 插件的网络与宿主业务入口。WASM 使用 `dian115.host_call` / `host_read` 导入承载下述业务请求，外层封装见 [WASM 协议](wasm-runtime-v1.md)。它同时承载：

- 安装时批准的 DIAN115 本地 Host API；
- 任意 HTTP/HTTPS 网站或本地服务请求。

插件不连接 DIAN115 HTTP 端口，也不持有管理员 Token。宿主在进程内校验安装实例、权限、路径、代理、目标地址、请求大小和响应内容后执行调用。

## 1. JSON-RPC 方法

插件发送：

```json
{
  "jsonrpc": "2.0",
  "id": "p:call:1",
  "method": "host.call",
  "params": {
    "method": "GET",
    "path": "/api/tmdb/search?q=Dune&page=1",
    "headers": {"accept": "application/json"},
    "body_base64": ""
  }
}
```

宿主成功执行调用后返回 HTTP 语义结果。目标 HTTP 的 4xx/5xx 也是正常 JSON-RPC result，不是 JSON-RPC error：

```json
{
  "jsonrpc": "2.0",
  "id": "p:call:1",
  "result": {
    "status": 200,
    "headers": {"content-type": ["application/json"]},
    "body_base64": "eyJkYXRhIjpbXX0"
  }
}
```

参数格式：

| 字段 | 必需 | 说明 |
| --- | --- | --- |
| `method` | 是 | `GET`、`HEAD`、`POST`、`PUT`、`PATCH`、`DELETE`；空值按 `GET` 处理，但开发者应显式填写 |
| `path` | 是 | `/api/...` 请求 URI，或小写 `http://` / `https://` 开头的绝对 URL；最长 4096 字符 |
| `headers` | 否 | 单值 header map；规则因本地/外部请求不同 |
| `body_base64` | 否 | 标准 Base64；请求接受 padded/unpadded，响应固定 unpadded |
| `credential_ref` | 否 | 外部 HTTP/HTTPS 可用的安装实例托管凭据引用；使用 HTTP 时秘密会以明文传输 |
| `timeout_ms` | 否 | 当前 Host Call 的时间上限，1–10000 毫秒；省略或 0 使用既有默认值，实际截止时间不会晚于本次插件执行的截止时间 |

发送 `timeout_ms` 前先调用 `host.capabilities`，仅当 `result.features.host_call_timeout_ms` 为 `true` 时使用该字段。旧宿主拒绝未知字段，未声明能力时应省略它。此扩展保持 `dian115:wasm@1` ABI 不变。批量插件应将剩余时间传给每次嵌套调用，耗尽预算后保留未确认状态，避免把超时当成业务否定结果。截止时间通过请求上下文传递；本地 Handler 必须将该上下文继续传给下游网络调用。

JSON 解码器拒绝未知字段和尾随 JSON。JSON-RPC 帧上限为 16 MiB；解码后的 Host Call 请求正文和返回正文上限均为 8 MiB。该上限只防止异常插件耗尽主容器内存，不再把正常数据限制在 256 KiB；列表接口仍应使用各自的分页参数。

以下情况返回 JSON-RPC `-32001`：参数无效、路径歧义、本地 API 未批准、凭据引用无效或宿主无法调度调用。错误消息已经脱敏，不应按自由文本分支业务逻辑。

## 2. 本地 Host API

本地 `path` 是以 `/api/` 开头的 request URI，可带 query。例如：

```json
{
  "method": "POST",
  "path": "/api/notifications/plugin",
  "headers": {
    "content-type": "application/json",
    "idempotency-key": "complete-job-20260822-0001"
  },
  "body_base64": "eyJsZXZlbCI6InN1Y2Nlc3MiLCJ0aXRsZSI6IuS7u+WKoeWujOaIkCIsImJvZHkiOiLlt7LlpITnkIYgMTIg6aG555uuIn0"
}
```

授权使用规范化后的 HTTP 方法和实际 URL path 匹配 Manifest 中的路径模板。query 不参与模板身份，但仍会进入真实 Handler。`/api/x/:id` 只匹配同段数的参数路径；若同时存在更具体的静态路径，宿主按具体路由授权，不能利用参数模板越权。

本地请求只允许这些调用方 header：

```text
Accept
Content-Type
If-Match
If-None-Match
Idempotency-Key
X-Correlation-ID
```

大小写不敏感，但同一名称不能重复。插件不能设置 `Authorization`、`Cookie`、`Host`、代理身份或 DIAN115 内部身份头。宿主自行附加一次性的内部管理员身份，并在 Handler 完成后删除 `Set-Cookie` 和 `Authorization` 响应头。

本地 API 的完整请求、响应、ETag、状态码和 Problem 结构见 [openapi-v1.yaml](openapi-v1.yaml)。可声明目录同时位于 OpenAPI 的 `x-dian115-host-apis.entries`。运行中的宿主可由管理员调用：

```text
GET /api/plugin-center/v1/host-apis
```

该管理接口只用于发现，不授予已安装插件新权限。

### 2.1 幂等

除 `GET` 和 `HEAD` 外，通用 Host Gateway 要求 `Idempotency-Key`。它必须是 16-128 个可打印 ASCII 字符。相同安装实例、方法、路由模板和 key：

- 请求 URI、业务 header 和 body 相同：返回保存的响应；
- 指纹不同：返回 `idempotency_conflict`；
- 原调用仍进行中：返回 `idempotency_in_progress`。

存储 KV 与插件通知等少数 Handler 自己实现更细的幂等/ETag 语义，OpenAPI 会明确其要求。任何可能产生副作用的重试都应复用原 key，不要为同一次业务尝试生成新 key。

### 2.2 Problem 响应

插件专用 Handler 使用 `application/problem+json`：

```json
{
  "type": "https://dian115.example/problems/invalid-request",
  "title": "Invalid request",
  "status": 400,
  "code": "invalid_request",
  "detail": "stable human-readable detail",
  "request_id": "req_...",
  "retryable": false
}
```

以 `code` 和 `retryable` 为程序判断依据。各接口的请求、成功响应和错误结构以对应 OpenAPI operation 为准；公开契约不要求开发者读取任何宿主实现源码。

### 2.3 读取宿主 Emby 数据

插件后端需要读取媒体库时，声明并调用专用的只读接口，不要自行索要 Emby 地址或 API Key：

```json
{
  "apis": [
    {"method":"GET","path":"/api/plugin-host/emby/instances","reason":"列出用户可选择的 Emby 实例"},
    {"method":"GET","path":"/api/plugin-host/emby/libraries","reason":"读取媒体库选项"},
    {"method":"GET","path":"/api/plugin-host/emby/items","reason":"搜索媒体库内容"},
    {"method":"GET","path":"/api/plugin-host/emby/items/:id","reason":"读取选中媒体详情"}
  ]
}
```

可声明的 Emby Host API 恰好为：

```text
GET /api/plugin-host/emby/instances
GET /api/plugin-host/emby/stats
GET /api/plugin-host/emby/libraries
GET /api/plugin-host/emby/items
GET /api/plugin-host/emby/items/:id
```

先读取实例：

```json
{"method":"GET","path":"/api/plugin-host/emby/instances"}
```

响应正文示例：

```json
{"items":[{"id":2,"name":"家庭媒体库","is_default":true,"api_key_configured":true}]}
```

将选中的正整数 `id` 作为其他接口的 `proxy_id`：

```json
{"method":"GET","path":"/api/plugin-host/emby/libraries?proxy_id=2"}
```

```json
{"method":"GET","path":"/api/plugin-host/emby/items?proxy_id=2&library_id=library-1&type=Movie&q=Dune&limit=20&offset=0&sort_by=date_created&sort_order=desc"}
```

若宿主只有一个可用实例或已经设置有效默认实例，可以省略 `proxy_id`。旧版单实例配置在实例列表中使用 `id: 0`；此时不要传 `proxy_id=0`，直接省略参数。存在多个实例且没有有效默认实例时，省略参数会返回 `409`；不存在、禁用或格式错误的显式 `proxy_id` 返回 `400`，宿主不会静默改用另一个实例。

宿主使用自己保存的地址和 API Key 发起请求。插件只能获得 OpenAPI 列出的安全字段；地址、API Key、媒体路径、`MediaSources`、用户播放数据、用户身份、会话、设备和日志不会返回，也没有 Emby 写接口。统计接口中的 `user_count` 和 `playing_count` 只是数量。媒体列表一次最多 50 条，应按 `offset + limit` 分页，直到已读取数量达到 `total`。

### 2.4 插件通知与通道能力

`POST /api/notifications/plugin` 只管"发什么"，不选通道：宿主把它投递到当前所有已配置的通道（Telegram、企业微信）。但**两条通道能承载的东西不一样**，所以响应里的 `channels` 会如实报告每条通道会保留和丢弃什么：

```json
{
  "event": "plugin_notification",
  "accepted": true,
  "channels": [
    {"channel": "telegram", "preserved": ["link_buttons", "callback_buttons", "images"]},
    {"channel": "wecom", "preserved": ["link_buttons", "images"], "dropped": ["callback_buttons"]}
  ]
}
```

当前能力对照：

| 能力 | Telegram | 企业微信 |
| --- | --- | --- |
| `link_buttons`（链接按钮） | ✓ | ✓（只取第一个） |
| `callback_buttons`（回调按钮） | ✓ | ✗ |
| `images`（图片） | ✓ | ✓ |

**只要 `callback_buttons` 出现在某条通道的 `dropped` 里，就该认为这条通道上的按钮交互不可用**：企业微信会把第一个链接按钮当作跳转地址，回调按钮没有 URL，因此会被丢弃。插件应当据此降级——例如改用链接按钮，或提示用户回复文字后由插件处理，而不是等待一个永远不会到来的回调。

响应只描述通道会保留什么，不代表消息已经送达；投递失败由宿主的持久化队列重试。`accepted` 为真表示通知已被接受并进入投递流程。

`preserved` 说的是通道**能**承载什么，通道自身的通知设置（例如某条通道关闭了图片）仍可能让图片不发。

## 3. 外部 HTTP/HTTPS 与本地服务

把完整 URL 放入 `path`：

```json
{
  "method": "PATCH",
  "path": "http://127.0.0.1:8080/v1/items/42",
  "headers": {
    "accept": "application/json",
    "content-type": "application/json"
  },
  "body_base64": "eyJlbmFibGVkIjp0cnVlfQ"
}
```

地址访问没有 origin 白名单。任何安装实例都能通过 Broker 请求任意 HTTP/HTTPS 地址，包括互联网、局域网、宿主机、容器、`localhost`、loopback 和插件可达的本地项目；Manifest `permissions.network` 只提供代理路由偏好。以下边界始终存在：

- URL 必须以精确小写 `http://` 或 `https://` 开头；
- 禁止 URL userinfo 和 fragment；
- 只支持 `GET`、`HEAD`、`POST`、`PUT`、`PATCH`、`DELETE`；
- HTTPS 使用 TLS 最低 1.2、证书、SNI 和 hostname 正常校验；HTTP 不提供加密或证书保护，插件应只把 HTTP 用于本地/受信任网络或本身不含秘密的接口；
- 默认总超时 10 秒；`host.call` 不提供自定义超时字段；
- 最多跟随 3 次跳转，每次重新校验 URL、DNS、目标地址和代理规则；跳转仍只能到 HTTP/HTTPS；
- `301/302` 的 POST 和 `303` 会转为 GET 并丢弃 body；
- 响应正文最多 8 MiB；极端超大响应会在 8 MiB 处截断并返回 `x-dian115-body-truncated: true`，常规列表应使用上游分页参数；
- 查询与 fragment 不会写入审计日志，审计记录 origin、方法、状态、耗时和代理范围。

外部请求 header 名必须是小写合法 HTTP token，最多 64 个；单值最长 8192 字节且不能包含 CR/LF。禁止这些请求头：

```text
host
proxy-authorization
connection
keep-alive
proxy-connection
transfer-encoding
te
trailer
upgrade
content-length
expect
```

插件可以在外部请求中自行提供它已知的 `authorization`、`cookie` 或站点自定义 header；这些值属于插件自身已掌握的数据，宿主不会自动提供管理员、115、TMDB、Telegram 或代理凭据。更推荐使用第 6 节的托管凭据，避免把秘密暴露给插件进程和日志。

响应会删除 `set-cookie`、认证挑战、`location`、长度和 hop-by-hop header。其他安全 header 以小写名称返回。跳转的 `Location` 只供宿主内部处理，不直接交给插件。

Broker 失败返回 HTTP 语义的 `502` Host Call result，body 为脱敏 JSON，例如：

```json
{"error":"upstream request failed"}
```

## 4. 目标地址与 DNS 规则

直连时宿主解析目标 hostname，依次尝试解析得到的地址，并保留原 hostname 用于 HTTP Host 与 HTTPS SNI。此版本有意允许 loopback、局域网、容器、宿主机、link-local 和其他非公网地址，以便插件对接本地项目；因此安装者必须把插件发布者和插件包视为同一信任边界。每个 redirect 都会重新解析目标。使用代理时由宿主选择的代理解析目标，以支持只能通过代理 DNS 解析的地址；宿主代理域名列表的命中规则始终优先。

`localhost`、`127.0.0.1` 和 `::1` 指 DIAN115 宿主进程所在的网络命名空间；Docker 部署中通常是当前 DIAN115 容器。访问物理宿主机或其他容器时，应使用该目标在 DIAN115 容器网络中可解析、可路由的 hostname 或 IP（例如同一 Docker network 的服务名、明确配置的宿主网关名或局域网地址）。

HTTP 明文请求可能被同机或同网段观察或篡改；插件不要把密码、Token 或托管凭据发送到不受信任的 HTTP 地址。HTTPS 仍建议用于互联网服务。

WASM 模块没有 Socket 能力，也不能创建子进程，因此不能用自己的 DNS/HTTP 客户端绕过 Broker。

## 5. 代理优先级

对每次请求和 redirect，按以下顺序决定：

1. 宿主代理域名列表命中：强制使用该宿主代理；
2. 未命中且 Manifest 对当前 `(method, origin)` 声明 `required`：使用宿主全局代理，没有配置则失败；
3. 未命中且声明 `direct`：直连；
4. 未命中且声明 `system` 或未声明：直连。

因此插件的 `direct` 永远不能覆盖宿主代理域名规则。`permissions.network` 示例：

```json
{
  "network": [
    {
      "origin": "http://127.0.0.1:8080",
      "methods": ["GET", "POST"],
      "proxy_mode": "direct",
      "reason": "宿主未指定代理时优先直连该服务"
    },
    {
      "origin": "https://restricted.example.net:8443",
      "methods": ["GET"],
      "proxy_mode": "required",
      "reason": "该服务必须经已配置代理访问"
    }
  ]
}
```

origin 包含非默认端口时，声明也必须包含该端口。

## 6. 安装实例托管凭据

需要第三方站点秘密时，Manifest 应在 `permissions.network` 中声明对应 origin。宿主由此为该安装实例启用托管凭据能力。管理员通过管理端为该安装实例创建绑定，秘密被宿主加密保存；插件只保存返回的 `credential_ref`，调用时提交引用。HTTP 地址同样支持托管凭据，但秘密会以明文经过网络，因此只应绑定受信任的本地或内网服务：

```json
{
  "method": "GET",
  "path": "https://api.example.com/v1/private",
  "headers": {"accept": "application/json"},
  "credential_ref": "cred_0123456789abcdef"
}
```

管理接口不是插件 Host API，不能由插件进程调用：

```text
GET    /api/plugin-center/v1/installations/:id/secret-bindings
POST   /api/plugin-center/v1/installations/:id/secret-bindings
DELETE /api/plugin-center/v1/installations/:id/secret-bindings/:credential_ref
```

创建请求：

```json
{
  "label": "Example API token",
  "host": "api.example.com",
  "method": "GET",
  "path_prefix": "/v1/",
  "injection_mode": "static",
  "location": "header",
  "name": "authorization",
  "prefix": "Bearer ",
  "suffix": "",
  "secret": "actual-secret-value"
}
```

绑定按安装实例、hostname、方法和规范化 path prefix 限制。`method` 可为 `*` 或六种支持方法。`location` 可为：

- `header`：注入单值 header；
- `query`：注入 query 参数；
- `body`：仅当 Host Call 的 `Content-Type` 包含 `application/json` 且 body 是 JSON object 时注入字段。

插件不能在请求中预先设置同名目标；冲突会拒绝调用。静态秘密不出现在 Host Call 请求、进程环境或审计日志。若上游在响应正文或安全响应 header 中反射秘密，宿主返回 `credential_reflected`，不把响应交给插件。

`injection_mode=hmac-sha256-request-v1` 仅允许 `location=header`、`name=x-signature`，不能设置 prefix/suffix。绑定可保存 `install_id`，否则请求必须提供合法 `x-install-id`。宿主为每次实际请求生成：

```text
x-install-id
x-timestamp       # Unix seconds
x-nonce           # 16 random bytes, lowercase hex
x-signature       # lowercase hex HMAC-SHA256
```

HMAC canonical message：

```text
UPPERCASE_METHOD + "\n" +
escaped_path + "\n" +
sorted_url_query + "\n" +
install_id + "\n" +
timestamp + "\n" +
nonce + "\n" +
lowercase_hex(SHA256(body))
```

签名 key 是绑定秘密原始 UTF-8 字节。query 按 key 排序，同 key values 再排序，最后使用 URL query escaping。带凭据跳转只能留在完全相同的 scheme/authority、hostname 和 path prefix 内；方法变化也必须满足绑定方法。

## 7. 文件与宿主凭据边界

115、TMDB、CD2、订阅和通知本身使用宿主已经配置的凭据，但这些凭据只留在真实 Handler 内。插件声明并调用对应 Host API，不需要也不会获得相关 token。

文件 Host API 会对输入和输出路径做额外过滤。禁止访问 `/config` 和 Linux 系统路径，包括 `/app`、`/bin`、`/boot`、`/dev`、`/etc`、`/home`、`/lib*`、`/proc`、`/root`、`/run`、`/sbin`、`/srv`、`/sys`、`/tmp`、`/usr`、`/var` 等。合法媒体挂载通常位于 `/data`、`/media`、`/mnt` 或配置的 CD2 挂载前缀，但是否可用仍由宿主文件管理器配置决定。

路径保护同时应用于请求路径、规范化路径、符号链接解析结果、返回数据和已保存目录监控源。错误不会向插件暴露真实受保护路径。

## 8. 指定实例和集数的订阅流程

1. 读取 `/api/plugin-host/emby/instances`，让用户选择已配置凭据的实例；可将选择保存到本插件 Host Storage，不修改宿主默认。实例被停用、删除或移除凭据时要求重新选择，不能悄悄换库。
2. 使用 `/api/tmdb/search?q=...` 确认 TV 候选，再读取 `/api/tmdb/tv/:id` 的 `seasons`。不能用同名电影或搜索第一项直接创建订阅。第 0 季为特别篇，总集数未知时应提示用户。
3. 调用 `GET /api/plugin-host/emby/episodes?proxy_id=7&tmdb_id=123&season=2&total_episodes=8`。返回实例、TMDB、季、修正后总集数、`covered_episodes`、`needed_episodes` 和 `complete`。该接口严格匹配 TMDB 与季并读取所选实例；上游失败或分页不完整返回错误，不能显示为“全部缺失”。legacy 实例 ID 为 0 时省略 `proxy_id`。
4. 确认后创建 `POST /api/subscribe/pool/intents`，传同一 `proxy_id`、`tmdb_id`、`media_type: "tv"`、`season`、`total_episodes`。自动追更使用 `episode_scope_mode: "follow"`；固定范围使用 `episode_scope_mode: "fixed"` 和 `initial_needed_episodes: "1-3,5"`。集数可以包含已公布但尚未播出的集，范围仍需在有效总集数内。普通插件请求不传 `library_snapshot_provided`，不需要 `library_id`。
5. 宿主在创建前再次读取覆盖并从固定目标扣除已有集，然后才允许搜索排队。例如目标 `1-3`、已有 `1,3`，实际只补 `2`；空范围、非法范围或全部已有不会创建新记录。自动模式沿用宿主的补缺/洗版规则。未指定资源源时沿用宿主配置，仍受宿主订阅开关、资源源与授权条件限制。
6. 只在收到 `code: "ok"` 和正数 `data.id` 后显示创建成功。保存该 ID，取消时调用对应 DELETE 并等待确认；网络超时不能当作未创建，必须查询宿主记录再决定是否重试。每次新的用户操作使用新幂等键，同一次重试保留原键。

缺集能力必须以运行宿主的 API 目录为准。旧宿主没有 `/api/plugin-host/emby/episodes` 时应提示升级，不能退化为跳过媒体库核对。排期可使用 TV 详情的 `next_episode_to_air`；缺少该字段表示没有已公布的下一集信息。

## 9. 扩展访问模式（host_access）

标准模式下插件只能调用 `x-dian115-host-apis.entries` 发布的 Host API 目录。需要更深集成的插件可以在 Manifest 中声明：

```json
{
  "permissions": {
    "host_access": "extended",
    "apis": [
      {"method":"GET","path":"/api/organize/rules","reason":"读取宿主整理规则"}
    ]
  }
}
```

`extended` 模式下插件可以调用除下列受保护前缀之外的任何 `/api` 路由，不要求逐条出现在目录中：

```text
/api/auth/            认证与 2FA
/api/115/cookie、login、qrcode、captcha、check-*、backup-accounts、backup/qrcode
/api/accounts/115     115 账号与 Cookie 管理
/api/settings         宿主安全设置
/api/system/、/api/debug/、/api/guard、/api/self-update
/api/plugin-center/   插件管理本身
/api/emby-control/system/、/api/emby-manager/、/api/emby-proxies
/api/plugins/tg-private-bot、/api/plugins/tg-group-bot
/api/portal、/api/user-portal、/api/logs
```

边界说明：

- `extended` 在安装确认对话框中作为高风险权限单独展示，管理员明确同意后生效；
- 扩展调用的 JSON 响应会经过通用密钥字段与 URL 凭据脱敏；非 JSON 响应原样返回；
- 写方法仍需 `Idempotency-Key`，审计、路径保护、代理规则和大小上限与目录接口一致；
- `permissions.apis` 在扩展模式下仍然建议逐条声明，作为安装时的用途披露。

## 10. 可选接口声明与运行时自省

声明 `"optional": true` 的接口在宿主不提供时不再导致安装失败；宿主把它记录到安装记录的 `unavailable_apis`，调用时返回 `host API was not approved` 错误。插件可以用运行时自省代替试错：

```json
{"method":"host.capabilities"}
```

返回当前宿主版本、Plugin API 版本、访问级别、完整 Host API 目录以及本安装实例已批准和不可用的接口清单：

```json
{
  "host_version": "3.9.0",
  "plugin_api": "2.0.0",
  "host_access": "standard",
  "apis": [{"method":"GET","path":"/api/tmdb/search","category":"tmdb"}],
  "granted_apis": [{"method":"GET","path":"/api/tmdb/search"}],
  "unavailable_apis": []
}
```

插件应按 `granted_apis` 与目录分支功能，而不是按宿主版本号猜测。宿主版本超出 Manifest `compatibility.dian115` 范围时，运行时会以 `plugin_incompatible` 暂停插件并提示升级，而不是继续运行到崩溃。

## 11. 文件、115 传输与任务 Broker

`/api/plugin-host/` 下的 broker 接口把原来只有外部 `/plugin-api/v1` 通道可用的能力开放给 host.call。所有资源引用（`entry_ref`、`preview_ref`、`job_ref` 等）都是安装实例作用域内的不透明标识，跨插件不可复用。

文件 Broker：

- `GET /api/plugin-host/files/roots`、`GET /files/entries`、`GET /files/entries/:entry_ref`：浏览宿主向插件开放的本地与 CD2/AURA 挂载根目录。
- `GET /files/entries/:entry_ref/content`：读取文件内容。支持 `Range: bytes=start-end` 分页，单页最大 4MiB，循环分页即可读取任意大小的完整文件；CD2/AURA 挂载文件经宿主挂载点流式读取，插件无需接触云盘凭据或 gRPC 连接。
- `PUT /files/entries/:entry_ref/content`：以 `{data_base64, offset, truncate}` 按偏移写入本地文件，单次最大 4MiB；可选 `If-Match` 乐观锁。仅纯本地根目录可写，CD2/AURA 挂载与 115 云端条目不提供内容写入。
- `PATCH /files/entries/:entry_ref`（改名）、`POST /files/directories`（建目录）、`POST /files/operations`（异步复制/移动，返回 `job_ref`）。
- `POST /files/downloads`：以 `{url, parent_ref, name?}` 把远程文件流式下载到指定本地可写目录，单个任务上限 8GiB，异步执行并返回 `job_ref`。下载目标明确排除 CD2/AURA 挂载目录与 115 云端。

115 传输 Broker：`GET /api/plugin-host/accounts/115`、`POST /accounts/115/selections` 创建账号选择引用；`GET/POST /transfers/115/targets`、`POST /transfers/115/share-previews`、`GET /transfers/115/share-previews/:preview_ref/items`、`POST /transfers/115/share-receives`、`POST /transfers/115/offline-downloads`、`GET /transfers/115/offline-tasks`、`GET /transfers/115/offline-quota`。账号 Cookie 始终留在宿主，插件只持有不透明引用。

任务查询：`GET /api/plugin-host/jobs/:job_ref` 查询状态与结果，`POST /api/plugin-host/jobs/:job_ref/cancel` 取消。

查询返回 `{data:{job_ref,kind,status,progress,cancellable,...},meta}`。status 为 queued、running、succeeded、failed、cancelled 或 attention_required；succeeded 表示当前任务自身的工作完成。页面后台 job 的外层引用完成只表示 guest 回调已交付，结果若含 accepted 和子任务 job_ref，应继续查询子任务，不能把受理当成全部业务完成。进度范围 0–100，失败 error 中提供安全错误码和可用的 diagnostic_id。created_at/started_at/finished_at 使用 Asia/Shanghai 的 `YYYY-MM-DD HH:mm:ss` 字符串，未开始/结束的时间字段省略。

取消携带 Idempotency-Key，202 返回 `{data:{job_ref,status:"cancellation_requested"},meta}`，并立即唤醒本地等待者。已经结束或不允许取消返回 409，任务不存在或不属于当前安装返回 404；查询同一 job_ref 确认终态。只批准查询权限不授予 115 任务取消权限。轻量封装见 SDK 的 [JobGet/JobCancel](examples/sdk/README.md#查询和取消后台任务)。

这些异步 Host Job 与页面 `api.jobs.start` 使用主项目统一任务队列，展示插件来源、进度、终态和诊断编号；插件仍查询原 job_ref。不支持手动取消的任务保留原策略，卸载会撤销执行并删除该安装的队列记录。执行与重启恢复边界见 [后台调用](ui-isolation-v1.md#可查询可取消的后台调用)。

插件 JSON 存储另有元数据分页 `GET /api/plugin-runtime/storage` 和用量 `GET /api/plugin-runtime/storage-usage`；先探测 `features.storage_catalog_v1` 并声明相应权限。单页最多 100 条，不返回值正文，详见 [存储协议](storage-and-lifecycle.md#分页与用量)。

声明这些接口后宿主自动推导所需的 `files.local.*`、`files.cloud.*`、`transfer.115.*`、`accounts.115.use` 运行能力；broker 写操作自带幂等生命周期，重试同一 `Idempotency-Key` 不会重复执行。

## 12. Telegram 回调按钮

通知和回复按钮除 `url` 外还支持 `callback_data`（二选一，最长 32 字节，不含控制字符）：

```json
{"buttons": [[{"text": "重试", "callback_data": "retry:job9"}]]}
```

用户点击按钮后，宿主向该按钮所属的插件安装实例投递 `telegram.callback` 事件（需在 manifest `events` 中声明并具备 `events.subscribe` 能力）：

```json
{
  "callback": {"data": "retry:job9"},
  "message": {"message_id": 123, "chat_id": 456, "chat_type": "private", "user_id": 789, "date": 1759000000}
}
```

插件返回 `{handled, answer, alert, reply}`：`answer`（≤200 字符）作为按钮提示 toast，`alert` 控制是否弹窗，`reply` 与 `telegram.message` 的回复格式相同（文本/HTML、HTTPS 图片、按钮，按钮同样支持 `callback_data`）。空响应视为静默确认。每次点击有独立的 Telegram 回调 ID，宿主按它做幂等去重，重试不会重复执行插件逻辑。
