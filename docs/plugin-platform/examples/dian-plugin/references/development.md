# 开发细则

## 任务

- `run(ctx, input)` 是默认入口，所有异步操作必须 `await`。
- `business_key` 要稳定：相同 key 和输入返回原任务，重试不重复执行。用户每次点击都是新业务时才带时间戳。
- 任务写 `title`，用于队列明细中的运行名称。API 3.12 起，同一插件的可见任务合并为一个条目；批量取消作用于当前可见的运行和等待任务，执行上下文、结果与插件历史仍各自独立。
- 测试、预览这类短任务在 job 设置 `queue: false`。插件顶层 `queue: false` 可关闭全部队列展示，包括页面文件操作；任务级开关不能覆盖关闭的总开关，使用顶层开关声明 `requires.api: "3.12"`。
- 每个普通后台任务只加载自身入口及其依赖。把重逻辑拆成独立文件，在需要的分支 `await import('./heavy.js')`；静态导入会提前加载，巨型单文件不会自动按函数拆分。详见 `assets/public-kit/developer-guide.md` 的“按任务加载逻辑”。
- 批量用 `ctx.task.update({total,done,failed,message})` 上报计数。
- 不允许重叠的任务被重启打断后处于“需要核对”，会拒绝新运行。页面要提供 `ctx.tasks.retry(id)`。
- 通知用稳定的 `dedupe_key`，不要换 key 绕过未知结果。

## 恢复

超时、重启、调用失败都不能证明外部动作没发生。写操作前后各存一次检查点，`recover` 先查询真实结果：

| 情况 | 返回 |
| --- | --- |
| 已确认完成 | `{action:'complete', result}` |
| 已确认没发生 | `{action:'resume'}` |
| 无法确认 | `{action:'attention'}` |

## 页面

- `mount(element, ctx)` 返回清理函数，异步请求传 `ctx.signal` 或在清理时取消。
- 宿主隐藏顶栏，不添加容器内边距。页面自行设置手机安全区与间距，并提供调用 `ctx.navigation.close()` 的返回入口；HTML 使用 `window.DIAN115Plugin.navigation.close()`。关闭仅卸载页面，不停用插件或取消后台任务。
- 跟随明暗主题，用 `--app-bg`、`--app-surface`、`--app-text`、`--app-text-secondary`、`--app-border`、`--app-accent`。
- 显示状态和原始业务错误，表单要有标签。不要把 Script error 或 ResizeObserver 提示当业务失败。
- 有页面的插件把设置做在页面里，不声明 `settings`。
- 加密交付时，页面和静态资源放 `ui/`，后台代码放在 `ui/` 之外。

## 网络

- 无需站点挑战的页面渲染和操作用共享 Chromium；已确认的挑战优先用 FlareSolverr 的 ctx.http.render。按 browser.md 的选用说明处理，FlareSolverr 不保证必过，也不提供完整页面操作；宿主目前不自动切换，两套会话状态也不会自动共享。
- 站点登录、验证、慢响应先读 `network.md` 的“登录与自动验证”和“避免每次查询都等待浏览器”。
- 大响应用 `save_to` 写盘，不读进内存。
- FlareSolverr 用 `network-capabilities` 探测，不读全局设置。
- 完整浏览器用 `ctx.browser`，先读 `browser.md`。后台会话随任务结束关闭，profile 登录状态保留；页面退出主动 close。检查 Runtime.evaluate 的 exceptionDetails 与事件 lost/truncated，不把超时当作未提交。
- 浏览器 API 3.11 的 open 接受 proxy_mode 与 proxy_url；不要把 ctx.http 的 proxy 参数照搬到 browser。系统域名分流包含子资源和重定向，账号密码不返回插件；更换设置后关闭并重新 open。
- 动态站点在 `declared_usage` 说明由用户配置。
- 安装报告的固定 IP 加密 DNS 仅用于安装或更新前的快照；插件运行期网络仍按 `ctx.http`、浏览器或 FlareSolverr 自身的代理参数处理，不把快照当作业务请求的解析策略。

## 文件

- 相对路径是插件自有目录；API 3.9 起，除受保护路径外，宿主绝对路径均可 read/write/append，包括 CD2 挂载路径。单次 read 最多 16 MiB，可分段读取。
- 允许的宿主文件可以复制或移动到插件目录；受保护目录和敏感数据仍不可访问。
- 内容读写、HTTP save_to/body_file/multipart、页面文件上传下载直接使用文件系统，可直接写 CD2 挂载路径；双边都在 CD2 挂载内的移动/复制走 gRPC，任一边在外走系统文件操作；跨云盘先移到本地。
- 后台 HTTP 下载每秒自动更新当前任务进度；页面用 ctx.tasks.get(runId) 查询 progress/stage/message。批量整体进度由 total/done/failed 决定，不被单文件覆盖。
- 目录读取失败时保留基线，不要推断文件被删除。

## 订阅

先读 `subscriptions.md`。用 `GET /api/cache/magnet/changes` 和 `POST /api/pt/search` 的 incremental 模式，按“订阅 × 来源”保存基线；完整空结果才推进基线，先保存候选再推进。

## 图片和媒体

先读 `media-and-ai.md`，复用宿主的图片处理、FFP 探测和 AI 调用。传受限的 width/height，不要自己重写这些能力。

## 消息和长连接

- `/` 开头的文本和宿主能识别的链接由宿主优先处理，其他命中的文本排在 AI 对话之前。
- 回复用 `ctx.messaging.reply(input, {...})`，它按来源渠道发送。
- 常驻任务断线时直接抛错，宿主按退避时间重启，不要自己写重连循环。
- 普通任务有超时，长连接放进 `daemon: true` 的任务。
- 每个插件最多 16 条长连接，SSE 和 TCP 都计入。
- 对外实时推送在 HTTP 处理器里用 `ctx.response.sse()`，定时发 `stream.comment()` 心跳。
- 原生 TCP 需要 `network.tcp` 授权。地址放设置里，监听默认绑定 `127.0.0.1`，放进常驻任务。对外开放端口必须自己鉴权。

## 常见错误

| 现象 | 原因 |
| --- | --- |
| `Cannot read property 'x' of undefined or null` | ctx 成员写错，或在后台用了页面才有的成员。报错末尾有文件和行号 |
| `SyntaxError` 指向 `for await` | 引擎不支持，循环调用 `next()` |
| `permission ... is not granted` | 用户没开授权，或清单没声明 |
| 安装报引用了禁止接口 | 用了受保护的接口，换成公开能力 |
| 插件被停用，提示代码被修改 | 安装后不能改代码，提高版本重新打包更新 |
| `本次运行同时进行的宿主调用超过 32 个`（busy） | 一次发出太多宿主调用，按 16～32 个分批 |
| `同时存在的定时器超过 1000 个` | 定时器没清理，或改用循环加 `ctx.sleep` |
| `Maximum call stack size exceeded` | 递归超过 10000 层，改成循环 |
| `console.warn is not a function` | 宿主低于 API 3.13，声明 `requires.api: "3.13"` 或只用 `console.log` |
| 检查报 `… 不是清单字段` | 清单字段拼错，宿主会忽略它；按 manifest.md 改正 |
| 任务等待中且带 `retry_at` | 声明了 retry，正在等自动重试 |

## 交付

- 可读源码目录或 `.dian115p` 用于自己的 DIAN115 安装调试及编译输入，输出放源码目录之外；打包工具不生成正式编译证明。
- 不要把 `node_modules`、构建缓存、私钥和真实凭据打进包。
- 正式编译、会员验证与本机调试规则先读 [compilation.md](compilation.md)。旧网页加密保留 v3 兼容，不能替代新格式正式编译；当前 MCP 未就绪的产出能力必须明确报告。
- 上架市场要满足 `market.md`，用 `conformance/market-check.mjs` 检查索引。
