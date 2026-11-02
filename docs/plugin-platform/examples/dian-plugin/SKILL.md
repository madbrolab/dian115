---
name: dian-plugin
description: 开发、修改、排错和审查 DIAN115 v3 第三方插件（.dian115p）。用于宿主 API、消息与常驻任务、本机源码调试、编译 MCP 和正式交付，以及安装前恶意代码审查。随主程序编译的内置功能不属于此流程。
---

# DIAN115 插件开发与审查

当前契约是宿主插件 API 3.9。先判断任务类型：

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
   - 按主题：`messaging.md`、`long-connections.md`、`network.md`、`subscriptions.md`、`media-and-ai.md`、`notifications.md`、`ui-theme.md`、`storage-and-lifecycle.md`
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
- 插件数据放 `ctx.storage`，账号密码放设置，不写进源码、日志或报告。
- 只申请用到的 `permissions`，TG 账号权限尽量配合关键字过滤。能用 HTTP 或 WebSocket 时不要申请 `network.tcp`。

## 验证边界

先验证只读路径，再验证有副作用的操作。未经用户明确同意，不登录第三方站点、不发通知、不转存、不删除文件、不更新服务器。没有环境时明确区分“本地检查通过”和“真实业务未验证”。

默认不要求 Docker、真实数据库或压力测试。发布到公开仓库时遵守 `assets/public-kit/publication-policy.md`，不包含主项目源码。
