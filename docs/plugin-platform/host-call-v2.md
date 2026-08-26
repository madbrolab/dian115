# DIAN115 Host Call v2

`host.call` 是 process 插件唯一的网络与宿主业务入口。它同时承载：

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
- 默认总超时 10 秒；process `host.call` 不提供自定义超时字段；
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

插件进程的 `socket`、`connect`、`bind`、`listen`、`accept`、send/receive 和 socket option 系统调用由 seccomp 拒绝，因此不能用自己的 DNS/HTTP 客户端绕过 Broker。

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
