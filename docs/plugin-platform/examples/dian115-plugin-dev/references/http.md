# 登录站点与轻量 HTTP

先读固定快照 [HTTP 会话协议](../assets/public-kit/http-sessions-v1.md)，请求和响应字段以 [OpenAPI](../assets/public-kit/openapi-v1.yaml) 为准。SDK 在 `examples/sdk/hostapi/http.go`，可执行 action 示例在 `examples/complete-plugin/runtime/http_sessions.go`。

- 页面可以直接填写账号密码、Cookie 和自定义地址，不把 CookieCloud 当唯一登录方式，不因 password/cookie 等字段名拒绝业务。含凭据动作使用示例 transientInput:true，只保存编号，原字段由用户重新提供；宿主加密动作回执。
- 使用 PostForm 提交任意站点字段、验证码和 CSRF；预取和登录使用同一 Session。SetCookieHeader 持久保存手填 CK，SetCookies 处理已知属性的独立 Cookie。
- Sites / SaveSite / DeleteSite 支持安装后配置 HTTP(S) 地址，声明三个 sites 方法即可，不为每个新地址改包。DeleteSite 的空 id 清空地址并可恢复损坏配置。
- 探测 features.http_sites_v1、features.credential_fields_v1 和 features.http_sessions_v1，使用 Client.HTTP；不同账号用独立 Session。宿主自动处理 Set-Cookie、跳转、过期与加密保存，不把秘密写普通偏好或日志。
- 检查目标 HTTP 状态及站点业务码。200 可能只是登录页或验证页；先验证搜索、详情和资源数据，不能仅凭页面加载成功认定业务完成。
- 用户选择已有登录时，通过 CookieCloud 导入所选域名；站点在 permissions.network 声明或通过 sites 保存。范围覆盖已声明或已保存 hostname 及其子域，需要父域时明确添加父域。复用宿主本地服务，不索取全局 Key/密码，不用内置业务接口替代。
- 写回共享 CookieCloud 必须是用户要求的业务动作，保留所选域名和读取到的 revision。遇到 409 停止覆盖，重新读取后按业务意图合并；不把新 revision 当作自动重试许可。
- 只有 HTTP 确实不够时才按需 RenderPage；复用已配置 FlareSolverr，不要求 DIAN115 内置 Chromium，不把 FlareSolverr 当通用点击/脚本接口。它的合成 200 不能证明站点业务成功。
- 写方法使用稳定业务编号派生幂等键，不在重试时换号。初始化、state、唤醒和只读恢复不自动登录、不写回 CookieCloud。
- 卸载清空插件自己的会话、导入副本、记录和绑定。显式导出到用户共享 CookieCloud 属于已提交的外部结果，不随卸载回滚；不清空其他插件或站点的数据。
- 用隔离 HTTP fixture 验证登录 Set-Cookie、重定向、会话恢复、串号隔离、过期删除、并发请求、卸载迟到响应，以及 CookieCloud 版本冲突。真实站点验收使用用户授权账号，不把账号密码、Cookie 或站点私有数据放进示例、技能或公共提交。

## 慢页、缓存与并发

- HTTP 默认 60 秒、TimeoutMS 最高 300000；前台默认 120 秒、Manifest 最高 600000 毫秒。外层执行预算要覆盖页面处理、请求及返回；批量长工作用统一后台任务，不在页面加入无限等待或自动重放。
- 探测 http_network_v2 / http_batch_v1。宿主复用连接，每安装网络在途最多 8、全局 32。独立 GET/HEAD 用 HTTPBatch，一次最多 8 项、并发默认 4、每项响应 1 MiB，按原顺序处理单项错误；不要并发操作同一 WASM ABI 缓冲。
- 按业务选择 CacheMode、CacheTTLMS 和 MaxResponseBytes。默认遵守上游新鲜度，显式 TTL 不覆盖 no-store/no-cache；Set-Cookie、跳转、截断及托管凭据响应不缓存。登录/验证码选 no-store。缓存内存有界、按安装及账号版本隔离，HTTPCache / ClearHTTPCache 分别查询及清空，不清除 Cookie。
- 展示 Network 的耗时、排队、缓存和复用信息，检查 Truncated。504 超时、499 取消和 409 cookie_session_conflict 分别处理；保留 request_id，先核对写入事实。原始请求/响应字节保持，不能用 HTTP 200 取代业务验证。
- 同一 Cookie 会话可以并发读取；依赖 Cookie/CSRF 更新的登录步骤按序执行。清空、导入、重新登录或卸载后旧响应不能恢复旧 Cookie/缓存。测试慢页超过 10 秒、并发合并、取消、缓存失效和隔离边界。
