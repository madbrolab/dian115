# 登录站点与轻量 HTTP

先读固定快照 [HTTP 会话协议](../assets/public-kit/http-sessions-v1.md)，请求和响应字段以 [OpenAPI](../assets/public-kit/openapi-v1.yaml) 为准。SDK 在 `examples/sdk/hostapi/http.go`，可执行 action 示例在 `examples/complete-plugin/runtime/http_sessions.go`。

- 探测 `features.http_sessions_v1`，用 `Client.HTTP`；不同站点账号分配独立 Session。宿主自动处理 Set-Cookie、跳转、过期与加密保存，不自行把 Cookie 串塞进普通 KV、页面 state 或日志。
- 检查目标 HTTP 状态及站点业务码。200 可能只是登录页或验证页；先验证搜索、详情和资源数据，不能仅凭页面加载成功认定业务完成。
- 需要用户已有登录时，通过公开 CookieCloud 接口导入明确选择的域名，并在 permissions.network 声明对应站点 origin。共享凭据范围限定为已声明 hostname 及其子域；需要父域 Cookie 时明确申报父域。复用宿主本地服务，不索取宿主全局 Key/密码，不用内置业务接口代替通用 CookieCloud。
- 写回共享 CookieCloud 必须是用户要求的业务动作，保留所选域名和读取到的 revision。遇到 409 停止覆盖，重新读取后按业务意图合并；不把新 revision 当作自动重试许可。
- 只有 HTTP 确实不够时才按需 RenderPage；复用已配置 FlareSolverr，不要求 DIAN115 内置 Chromium，不把 FlareSolverr 当通用点击/脚本接口。它的合成 200 不能证明站点业务成功。
- 写方法使用稳定业务编号派生幂等键，不在重试时换号。初始化、state、唤醒和只读恢复不自动登录、不写回 CookieCloud。
- 卸载清空插件自己的会话、导入副本、记录和绑定。显式导出到用户共享 CookieCloud 属于已提交的外部结果，不随卸载回滚；不清空其他插件或站点的数据。
- 用隔离 HTTP fixture 验证登录 Set-Cookie、重定向、会话恢复、串号隔离、过期删除、并发请求、卸载迟到响应，以及 CookieCloud 版本冲突。真实站点验收使用用户授权账号，不把账号密码、Cookie 或站点私有数据放进示例、技能或公共提交。
