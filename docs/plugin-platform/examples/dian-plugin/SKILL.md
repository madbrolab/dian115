---
name: dian-plugin
description: 开发、修改、排错和审查 DIAN115 v3 第三方插件（.dian115p）。用于宿主 API、消息与常驻任务、本机源码调试、编译 MCP 和正式交付，以及安装前恶意代码审查。随主程序编译的内置功能不属于此流程。
---

# DIAN115 插件开发与审查

当前契约是宿主插件 API 3.13。按实际使用的能力声明最低 `requires.api`，不要无故提高已有插件的最低版本。先判断任务类型：

- **审查插件**（用户问是否安全、有没有恶意代码、能不能装）：读 [references/malware-review.md](references/malware-review.md) 并照做。全程只读，绝不运行插件，不写新代码。
- **开发或修改插件**：继续看下面。

## 开发流程

1. 问清楚缺失的关键信息：做什么、触发方式（页面、定时、命令、关键字、常驻）、要碰哪些外部站点和宿主能力。其他按合理默认值决定。
2. 从模板创建：

   ```sh
   node scripts/init.mjs <绝对目录> <插件ID> --template <模板> --name <名称> --author <作者>
   ```

   | 模板 | 适合 |
   | --- | --- |
   | `starter` | 页面加后台任务，默认选它 |
   | `bot` | TG 和企业微信的命令、关键字、回复 |
   | `daemon` | 开机常驻、WebSocket 长连接 |
   | `webhook` | 接收外部回调 |
   | `lab` | 全功能测试台，只用来试接口 |

   用户已有项目时直接改，不要用模板覆盖。
3. 实现业务。按需查文档，不要凭印象写接口：
   - 需要写法：`assets/public-kit/cookbook.md`
   - 字段规则：`assets/public-kit/manifest.md`
   - ctx 全部能力：`assets/public-kit/api-reference.md`
   - 宿主接口：先搜 `assets/public-kit/host-api-quick-reference.md`，再查 `host-api-reference.md` 对应段落。这个文件超过一万行，只搜索，不要整篇读
   - 按主题：`messaging.md`、`long-connections.md`、`network.md`、`browser.md`、`subscriptions.md`、`media-and-ai.md`、`notifications.md`、`ui-theme.md`、`storage-and-lifecycle.md`
4. 检查并生成可读源码包，供自己的 DIAN115 安装调试或作为编译输入：

   ```sh
   node scripts/check.mjs <插件目录> --pack <目录外的输出.dian115p>
   ```

   结构错误必须修。扫描结果里的 `do-not-install` 和 `needs-review` 要逐条看：是真问题就改，确实需要就写进 `declared_usage`。
5. 正式交付先读 [references/compilation.md](references/compilation.md)，查询宿主编译 MCP 的真实能力。连接使用系统 OpenAPI Key，由宿主实时验证癫影账号的 API Key；不读取或把凭据写进插件。加密与来源签名由 DIAN115 本地完成，不扩展会员服务接口。正式开发者名称取宿主实时校验并签名绑定的会员昵称，不用源码自填署名冒充。仅当编译返回非错误结果、`release_ready: true` 和可校验的 `package_base64` 时报告成功；缺少配置如实报告，不用旧网页加密替代。
6. 报告改动、检查结果、本机调试方法、正式编译是否完成，以及哪些外部业务没有实测。保留现有插件兼容和第三方业务调用。

更多规则和常见错误见 [references/development.md](references/development.md)，开始写代码前读一遍。

## 必须遵守

- 后台脚本不支持 `for await` 和异步生成器，没有 DOM、Node 模块、`require`。
- 后台 ctx 没有 `tasks`、`events`、`usage`，这些只在页面。`ws`、`tcp`、`http.stream` 只在后台，`response` 只在 HTTP 处理器。
- 所有异步调用都要 `await`，处理函数返回后脚本结束，未完成的连接会被关闭。
- CD2 文件一律写挂载路径，比如 `/mnt/cd2/115/电影`，不要写 `cd2:`，`ctx.watch.add` 不要填 `kind`。
- 除受保护路径外，插件可读写宿主和 CD2 挂载文件，HTTP save_to 可直接写目标目录；需要此能力声明 requires.api: "3.9"。内容读写走文件系统，双边 CD2 的移动/复制仍走 gRPC。Token 和渠道配置仍由宿主管理，不要绕过受限接口。
- 外部写操作前保存检查点，`recover` 先核对结果。不确定是否已执行时返回 `attention`，不要换标识重做。
- 后台按任务入口及依赖加载；重逻辑拆成独立模块，分支需要时再 `import()`，不要把所有功能聚合到每个任务入口。任务显示与模块加载规则见 `references/development.md`。
- API 3.12 的插件级 `queue: false` 隐藏全部任务队列活动，job 可进一步隐藏；可见任务按插件合并，执行与历史各自独立。权限和侧边栏设置在“更多 → 权限管理与显示”，不放在插件卡片上。
- 插件数据放 `ctx.storage`，账号密码放设置，不写进源码、日志或报告。
- 网络选用：普通接口与静态内容用 ctx.http.request；无需站点挑战的页面渲染和操作用共享 Chromium 的 ctx.browser；已确认遇到挑战时优先 ctx.http.render（FlareSolverr）。先读 `assets/public-kit/browser.md` 的选用说明，不保证挑战必过，不把 403 一概视为挑战；两者不自动切换或共享 Cookie、档案与代理。
- 需要页面脚本、点击、截图或网络事件时，先读 `assets/public-kit/browser.md`，使用宿主共享 `ctx.browser`；声明 API 3.10 与 browser 权限。运行包由宿主管理，不在插件中下载 Chromium，不接管 FlareSolverr 内部进程。Runtime.evaluate 表达式可用网页 DOM，后台脚本自身仍无 DOM。
- 浏览器代理参数需要 API 3.11：open 默认 system 按宿主域名清单分流；direct 强制直连；custom 配合 proxy_url。主页面、子资源和重定向均按各自域名处理，策略在打开时固定，更换代理需重新打开。代理密码从设置读取，不放日志；ctx.http.render 仍独立使用 FlareSolverr。
- 错误要带码（API 3.13）：失败时 `throw Object.assign(new Error('原因'), {code})`，code 用 invalid_input、not_found、forbidden、conflict、unavailable、busy、timeout、upstream；宿主调用失败的 `e.code`/`e.retryable` 可直接判断。只有 busy/timeout/unavailable/upstream 会触发自动重试。
- 瞬时失败交给宿主重试：job 声明 `"retry": {"attempts": 3, "delay_seconds": 30}`，不要在脚本里写重试循环；处理函数必须可安全重跑，或配合 checkpoint + `recover`。daemon 不设 retry。
- 长循环看 `ctx.remaining()`，余量不足先保存 checkpoint 再返回；日志用 `console.info/warn/error`（对象自动转 JSON）。
- 每次运行最多同时 32 个宿主调用、1000 个定时器、10000 层调用：`Promise.all` 分批，递归改循环。
- 清单不写 Schema 之外的字段；拼错的字段宿主会忽略，`scripts/check.mjs` 会报错。
- 只申请用到的 `permissions`，TG 账号权限尽量配合关键字过滤。能用 HTTP 或 WebSocket 时不要申请 `network.tcp`。

## 验证边界

先验证只读路径，再验证有副作用的操作。未经用户明确同意，不登录第三方站点、不发通知、不转存、不删除文件、不更新服务器。没有环境时明确区分“本地检查通过”和“真实业务未验证”。

默认不要求 Docker、真实数据库或压力测试。发布到公开仓库时遵守 `assets/public-kit/publication-policy.md`，不包含主项目源码。
