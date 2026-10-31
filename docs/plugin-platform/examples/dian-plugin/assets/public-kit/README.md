# DIAN115 第三方可信扩展 v3

插件与宿主共同运行：页面直接使用宿主 HTTP API，后台 JavaScript 编排业务，主项目负责实际转存、整理、通知与队列调度。无需主项目源码、WASM、Node、额外容器或内置浏览器。

宿主插件 API 3.8 能力一览：宿主公开的业务 HTTP API、二进制 HTTP 与流式下载上传、后台任务进入宿主任务队列并显示任务级进度与计数（3.2）、由宿主执行并带进度的文件移动复制删除（CD2 gRPC/挂载路径自动分流）、实时目录监听（created/changed/removed）、宿主业务事件订阅、独立监听端口与 Webhook、Cookie/CookieCloud/FlareSolverr、CD2、通知、定时与消息触发、设置表单、侧栏菜单与图标，以及后台 fetch/URL/编码/加密/HTML/XML 标准库。

- [快速开始](quickstart.md)：10 分钟做出第一个插件。
- [配方](cookbook.md)：命令、关键字、定时、监听、Webhook、长连接等可直接改用的写法。
- [清单参考](manifest.md)：plugin.json 全部字段和校验规则。
- [消息渠道](messaging.md)：Telegram 机器人、企业微信和 TG 账号收发消息。
- [长连接与常驻任务](long-connections.md)：开机常驻、WebSocket、SSE、流式读取与输出、原生 TCP。
- [安全审查](security-audit.md)：安装前用 AI 或扫描工具检查恶意代码。
- [市场规范](market.md)：上架要求、宿主校验、安装确认与接口分级。
- [插件包格式](package-format.md)：统一的 .dian115p 交付、打包与安装。
- [开发指南](developer-guide.md)：目录、入口、API、任务、文件与监听。
- [安装与数据生命周期](storage-and-lifecycle.md)：更新、停用、恢复、卸载。
- [插件通知](notifications.md)：选择 Telegram / 企业微信渠道、text / markdown / html 格式、按渠道内容、图片按钮及逐渠道结果。
- [订阅与增量搜索](subscriptions.md)：磁力 / ED2K 缓存、馒头时间窗口、独立基线及中断续读。
- [网络与登录](network.md)：账号密码、明文 CK、自定义站点、CookieCloud、FlareSolverr。
- [加密交付](encrypted-delivery.md)：作者网页加密、直接离线安装、维护者审查。
- [页面与主题](ui-theme.md)：直接挂载页面和完整 HTML。
- [安全限制](security.md)：调用权限、CookieCloud 与宿主文件保护、安装后防篡改。
- [插件 API 完整参考](api-reference.md)：清单、页面与后台 ctx、文件、事件、处理器、限额一页列全。
- [宿主接口参考](host-api-reference.md)：逐个接口的参数、请求与响应字段、`ctx.api` 调用写法和示例；[速查](host-api-quick-reference.md)为一行一个接口。
- [宿主接口速查](host-api-quick-reference.md)、[OpenAPI](openapi-v3.json)、[清单 Schema](manifest.schema.json)。
- [完整示例](examples/complete-plugin/README.md)、[SDK](examples/sdk/README.md)、[开发 skill](skill-installation.md)。
- [黑盒检查工具](conformance/README.md)、[排错](troubleshooting.md)、[公开材料边界](publication-policy.md)。

安装会展示实际代码静态分析、作者声明、已识别接口和站点以及未确定范围。等级和声明只作告知；宿主仍执行[权限检查](security.md)：受限调用在安装时拒绝或运行时返回 403；公开文档只收录插件可调用的接口。安装后代码被修改即停用，需重新安装。宿主原有登录、授权版本与业务参数校验继续适用。

可信扩展可以影响宿主和外部文件，无法以进程内执行同时承诺强制内存隔离或完整撤销任意全局副作用。请选择信任的作者。每个插件的默认数据、任务与 Cookie 独立保存；卸载清空这部分全部本地数据。

本目录保留的其他独立客户端和用户脚本示例不作为 v3 安装模板；开发本平台扩展请使用 complete-plugin 与当前 SDK。

3.8 新增：[原生 TCP 客户端与服务端、对外 SSE 和流式响应](long-connections.md)；TCP 需要用户授权 `network.tcp`。

3.7 新增：CD2 路径统一按挂载前缀判定，监听的 `kind` 可省略，`ctx.cd2.call` 接受挂载路径，`cd2:` 写法仅保留兼容；任务报错带文件和行号。

3.7 新增：[长连接与常驻任务](long-connections.md)：开机自启的常驻任务、后台 WebSocket、流式读取与 SSE。

3.6 新增：[消息渠道](messaging.md)：授权后可用 Telegram 机器人、企业微信和 TG 监控账号收发消息、读取会话，并按命令、前缀、关键字和正则触发任务。

3.5 新增：[订阅增量查询](subscriptions.md)：缓存按更新时间和 ID 续读、馒头按发布时间范围实时分页；空结果推进基线，失败保留进度。

3.4 新增：插件自有 SQLite 结构化只读查询和媒体 NFO 解析，见同一份 [媒体与资料接口文档](media-and-ai.md)。

3.3 新增：[图片处理、宿主 badge、FFP、AI 与演员图片](media-and-ai.md)。现有 PT 搜索支持馒头 normal/adult 模式；文件接口增加硬/软链接和非递归空目录删除。
