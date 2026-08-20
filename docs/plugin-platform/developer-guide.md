# DIAN115 插件开发指南

## 1. 最小插件

插件包是签名的 `.d115p` ZIP：

```text
manifest.json
ui/schema.json                 # 可选
ui/icon.svg                    # 可选
runtime/plugin.wasm
integrity.json
signature.json
```

WASM 仅导出 `memory`、`dian115_alloc`、`dian115_invoke`（`dian115_free` 可选），仅导入 `dian115.host_call` 和 `dian115.log`。插件不能启动进程、读环境变量、读数据库、访问文件系统或打开 socket。

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

`path` 使用宿主登记的路径模板；参数放在 query、path 或 JSON body 中，不要把账号 Cookie、绝对路径或凭据放进请求。写操作带唯一 `Idempotency-Key`。不要声明未实际使用的接口。

## 3. 通用 host_call

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

调用已声明的外部网络来源时使用同一个 `host_call`，但传入 `url` 而不是 `path`：

```json
{
  "method": "GET",
  "url": "https://example.com/v1/items",
  "headers": {"accept": "application/json"},
  "body_base64": ""
}
```

宿主只允许 manifest `permissions.network` 中声明的 HTTPS origin、方法和 `proxy_mode`；外部请求不会获得 DIAN115 管理员 Cookie 或主项目凭据。`url` 不能与 `path` 同时提供。

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

具体 query 参数和响应以当前 OpenAPI/接口目录为准；插件不得猜测未登记的 TMDB v3 路径。图片也应使用宿主返回的代理地址，不要直连 `image.tmdb.org`。完整接口目录通过 `GET /api/plugin-center/v1/host-apis` 查看。

## 5. 115、多账号与文件/CD2

插件先调用登记的账号选项接口，让用户选择 `main`、`backup_pool` 或指定备用账号；随后把宿主返回的账号选择值原样放入业务请求。插件不读取 Cookie，也不自行轮询账号。

目录、离线任务、离线额度和默认离线目录的 GET 请求使用 `account_mode` 与可选的 `account_id` query；离线新增、删除、清理、重试和分享转存的 POST 请求使用 `{"account":{"mode":"backup","id":12}}`。省略账号选择时保持主账号兼容行为。`backup_pool` 每次请求只选择一次，并在响应的 `account` 中返回实际账号摘要；后续必须继续操作同一账号时，改用该摘要中的 `id` 和 `backup` 模式。

文件操作直接提交宿主登记接口要求的目录标识或路径字段。115 云端目录只能在同一账号上下文内操作。源和目的都是 CD2 挂载目录时宿主走 CD2 gRPC；任一端不是 CD2 目录时，宿主按已暴露的本地挂载路径执行。插件不能取得 gRPC 凭据。

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
- 声明调度能力后可在 manifest 声明 cron job；声明目录监控后由宿主轮询本地/CD2 目录并投递事件。
- `dian115.log` 和日志接口只写当前安装实例的日志；宿主限制单条大小、总容量和保留天数，超限从最旧记录裁剪。
- KV、任务、事件和日志均按安装实例隔离；禁用插件会停止新调用、调度和事件投递。

## 7. UI 与主题

UI 只能使用 `ui-schema-v1.schema.json` 声明 `form`、`table`、`status`、`progress`、`log` 和 `actions`。页面由宿主使用内置插件相同的布局、主题、移动端断点和弹窗系统渲染。插件可选择受控的主题、密度、卡片和布局 token，但不能提交 CSS、HTML、Vue 组件或独立弹窗。

需要按权限隐藏 UI 时，`requires_capabilities` 直接填写已声明的 `/api/...` 路径或 HTTPS 来源；不要填写旧的内部 capability 名称。

表单字段 id、action id、view id 和 section id 在各自作用域必须唯一；不要重复使用 `name` 作为同一作用域的两个字段 id。

## 8. 安装、发布与检查

安装页展示所有 `permissions.apis`、`permissions.network`、账号模式、后台调度和日志行为；用户一次性整体同意。接口或域名声明发生变化必须重新确认。市场索引中的权限披露必须与包内 manifest 完全一致。

发布前检查：验证 JSON Schema、ZIP 路径、完整性清单和 Ed25519 签名；在 Linux/Docker 环境验证 WASM；不上传源码，不运行独立插件服务。插件市场包通过 HTTPS 发布到自己的发行位置，官方索引只记录包 URL、摘要、版本和权限披露。

完整的错误码、签名规则和 OpenAPI 定义见本目录其他文件。若某路径尚未出现在接口目录，先等待宿主登记后再写入 manifest；不要自行新增“兼容转换接口”。
