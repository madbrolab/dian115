# 轻量 HTTP 会话、CookieCloud 与按需渲染

插件通过 WASM `host.call` 访问 HTTP/HTTPS。DIAN115 不内置 Chromium，不为普通 HTTP 请求启动浏览器。公开 SDK 的 `hostapi.Client` 封装以下能力，页面经 action 调用 WASM，不能直接读取宿主 Cookie。

## 自动 Cookie 与账号隔离

先检查 `host.capabilities.features.http_sessions_v1`，缺少时提示升级宿主。外部请求新增可选 `cookie_session`：省略时为 `default`；不同账号使用不同名称；`none` 仅对此请求关闭自动 Cookie。名称为 1–64 个 ASCII 字符，以字母或数字开头，后续允许字母、数字、点、下划线、短横线。

```json
{"method":"GET","path":"https://site.example/resources","cookie_session":"account-a","timeout_ms":30000}
```

宿主处理每次响应及跳转中的多条独立 `Set-Cookie`，随后按域名、HostOnly、路径、Secure、过期时间选择 Cookie。保存 HttpOnly、SameSite 和 Cookie 的绝对到期时间，正确应用 Max-Age 删除。同名不同路径的 Cookie 分开保存。会话 Cookie 按用户要求记住，直到清空、被站点删除或卸载。每个会话最多 256 条 Cookie、256 KiB 序列化数据，每个安装最多 32 个会话；独立于普通 KV 配额。

HTTP 客户端不具备浏览器的顶层站点上下文，SameSite 作为属性保存，不模拟浏览器跨站导航。Partitioned/CHIPS Cookie 不导入普通 HTTP 会话，避免丢失分区后串号。公共后缀、非法域名和无效安全前缀 Cookie 不接收。HTTP 响应不能覆盖既有 Secure Cookie。

会话由安装编号隔离，Cookie 加密存入宿主数据库，密钥沿用宿主已有插件密钥。不创建浏览器用户目录、不使用插件页面的 document.cookie、LocalStorage 或 IndexedDB，不启动轮询。重启、休眠唤醒、WASM 释放和停用保留数据；卸载删除全部插件私有会话，重装为空，卸载后的迟到响应不能重新写入。

同一会话的请求与清空按顺序执行，避免并发响应覆盖 Cookie。独立账号可以使用不同会话。请求显式提供 `cookie` 时，在原始 origin 使用该值；跳转到不同 origin 会移除原来的 Cookie 和 Authorization，再为新地址选择受管 Cookie。Cookie 的域名作用域不以端口隔离，这是标准 HTTP Cookie 语义。

响应的 `set-cookie` 仍不直接转交页面；它由宿主先应用。插件需要读取自己会话的 Cookie 时，通过下面的已授权接口读取。托管凭据的秘密不会因反射到 Set-Cookie 而泄漏进插件会话。

Cookie 会话格式有独立 schema_version，当前为 1。损坏的 JSON 或密文会明确报错，不当作空配置覆盖；显式清空接口仍可重置损坏会话。没有 Cookie 或 User-Agent 变化的普通请求不创建空会话记录。

## 会话接口

接口只允许通过已授权 `host.call` 调用。Manifest 声明精确方法与路径；写方法提供稳定 `Idempotency-Key`，同一业务重试复用相同请求和 key。所有响应禁止缓存，成功封套为 `{data:{...},meta:{...}}`。完整字段以 [OpenAPI](openapi-v1.yaml) 为准。

| 方法 | 路径 | 请求及结果 |
| --- | --- | --- |
| GET | `/api/plugin-runtime/http/cookies` | query `url` 必填，`session` 可选；返回匹配 Cookie、会话总数及 User-Agent |
| PUT | `/api/plugin-runtime/http/cookies` | `{url,session?,set_cookie:["name=value; Path=/; HttpOnly"]}`；每条 header 独立，最多 64 条，不按逗号拆分 |
| DELETE | `/api/plugin-runtime/http/cookies` | query `session` 可选；清空该会话所有域名 Cookie 和 User-Agent |
| GET | `/api/plugin-runtime/http/cookiecloud` | 本地 CookieCloud 域名、数量和 revision，不返回 Cookie 值或全局密码 |
| POST | `/api/plugin-runtime/http/cookiecloud/import` | `{session?,domains:["site.example"]}`；替换该会话中所选域名及其子域的 Cookie 副本，其他域名保持 |
| POST | `/api/plugin-runtime/http/cookiecloud/export` | `{session?,domains:["site.example"],revision}`；将所选域名合并写回共享本地 CookieCloud |
| POST | `/api/plugin-runtime/http/render` | `{url,session?,wait_seconds?:3}`；按需用已配置 FlareSolverr 渲染 GET 页面并保存 Cookie |

管理接口中的 session 不能使用保留名称 `none`；它仅用于外部 HTTP 请求的无状态选项。

GET cookies 返回值属于当前插件掌握的站点凭据。不要显示到页面状态、记录日志或提交仓库。多账号使用独立 session，不将管理员、115 或其他插件的凭据当作站点会话。

## 本地 CookieCloud

除对应 API 权限外，Manifest `permissions.network` 必须声明所需站点 origin，例如 `https://site.example`。CookieCloud 概况、导入和导出仅覆盖该 hostname 及其子域；访问未声明域名返回 403 `cookiecloud_scope_not_approved`。需要父域 Cookie 时应明确声明父域 origin，不能借一个子域读取整个父域。公共后缀不能作为凭据范围；IP 和单标签主机只匹配该主机。网络声明在此用于宿主管理凭据的数据范围，普通外部 HTTP 仍沿用既有联网规则。一个站点插件无法通过 CookieCloud 取得其他站点的登录信息。

复用宿主已经配置的本地 CookieCloud 的 Key、密码和端到端加密格式，不要求插件再保存它们。未配置或未启用本地服务时返回 503 `cookiecloud_unavailable`，不静默访问远程 CookieCloud。当前接口使用本地服务既有的 CryptoJS/OpenSSL Salted 格式，不额外引入另一套 CookieCloud 服务。

导入先显式选择域名，只把所选 Cookie 复制进当前插件安装及账号会话；宿主配置的站点 User-Agent 一并用于后续请求。导入及写回不触发 PT 站点创建、验证或其他内置业务。

写回先读取 GET cookiecloud 的 revision，再提交 export。服务器在写入时原子检查旧密文；浏览器扩展或其他插件已经上传新数据时返回 HTTP 409 `cookiecloud_conflict`。此时重新读取并由用户意图决定合并，不自动用新 revision 覆盖。空服务也能通过其初始 revision 创建第一份数据。

仅替换明确选定的域名及其子域 Cookie，保留其他域名、分区 Cookie、全部 LocalStorage 和未知顶层字段。LocalStorage 不导入普通 HTTP 会话，也不通过此接口修改。

CookieCloud 是用户共享服务：显式 export 与写入远程站点一样属于外部业务结果。卸载清空插件自己的 Cookie 副本、会话、记录及凭据绑定；不删除用户共享 CookieCloud，也不撤销已经提交的写回。需要移除某域名的共享 Cookie 时，应明确以空会话导出该域名，不能通过卸载连带清空其他用户数据。

## FlareSolverr

只有插件明确调用 render 时才使用宿主 `flaresolverr_url` 指向的既有服务。未配置返回 503 `browser_unavailable`。宿主全局最多运行一个插件渲染请求，30 秒总预算，每次创建独立临时会话，成功、失败或取消后均尝试关闭，不共享其他任务的 session，也不枚举服务上的其他 session。

render 的目标 DNS 和 localhost 由 FlareSolverr 所在网络命名空间解析；本地服务及代理应使用该服务可达的地址。

支持 GET 取页，不提供任意脚本执行或表单 POST。登录优先使用 HTTP；需要交互验证码时让用户完成并从 CookieCloud 导入。最多返回 4 MiB HTML，wait_seconds 允许 0–10 秒。响应包含 `url`、`html`、`user_agent`、`http_status_verified:false`。FlareSolverr 3.x 的 HTTP 200 可能是合成值，必须检查站点内容和业务码。

复用同一 Cookie 会话及宿主目标代理配置，保存浏览器返回的 User-Agent。针对 3.4.6 在 waitInSeconds 前截取 Cookie 的行为，等待后再次收集当前 Cookie；从浏览器删除的已注入 Cookie 不会重新出现在 HTTP 会话中。外站 Cookie 不混入目标站点，跨主机跳转不作为成功会话导入。

FlareSolverr 自身可能记录请求体，包括注入的 Cookie。服务端应关闭包含凭据的请求日志；DIAN115 不经此接口传递登录密码，也不把 Cookie 写入自己的审计日志。普通 HTTP 与渲染都不自动重试业务写入。

## SDK 示例

```go
client := hostapi.Client{Call: peer.call}
response, err := client.HTTP(ctx, hostapi.HTTPRequest{
    Method: "GET", URL: "https://site.example/resources", Session: "account-a",
    TimeoutMS: 30000,
})
if err != nil { return err }
if response.Status != 200 { /* 按该站点处理登录失效或错误，保留原业务编号 */ }
// 再检查站点的业务码和数据结构，勿把 HTTP 200 当成登录成功。
overview, err := client.CookieCloud(ctx)
if err != nil { return err }
revision := pluginjson.Text(pluginjson.Field(overview, "revision"))
_, err = client.ImportCookieCloud(ctx, "account-a", []string{"site.example"}, "import-account-a-0001")
// 只有明确要求写回共享 CookieCloud 时调用 ExportCookieCloud。
_ = revision
```

网络副作用使用插件已有的稳定 invocation ID、幂等记录和统一任务队列；不要为 Cookie 保持登录另启常驻任务。只读恢复回调仍然不允许 POST/PUT/DELETE，应以 HTTP GET 核实业务结果。
