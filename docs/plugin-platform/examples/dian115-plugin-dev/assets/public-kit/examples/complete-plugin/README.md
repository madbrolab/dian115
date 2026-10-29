# 完整插件示例

本目录是一个可以直接构建、签名和发布的插件，而不是只有 UI 的片段。它演示：

- 完整 HTML 页面及签名静态资源；
- 插件自行打包的 Vue 3、Naive UI 和 `@lucide/vue`；
- `dian115-theme-v1` 主题变量；
- Go WASM reactor runtime（`dian115:wasm@1`）；
- reactor ABI 上的 JSON-RPC 调用封套（`dian115_alloc`/`dian115_handle`）；
- `runtime.initialize`、state、action、job、普通 event、Telegram event 和 shutdown；
- `host.call` 发送插件通知、读写 Host Storage、访问本地 HTTP 服务和创建目录监控；
- 在 manifest 的 `telegram` 段声明 1 个命令和 1 个关键词（最多各 3 个）。宿主在安装时登记路由，所以插件未加载时也能匹配消息；
- 常驻模块模式（`runtime.resident`）：第二个模块实例运行不限时的 `resident` 主循环，定时把心跳写入 Host Storage，并在启动时发送带回调按钮的通知；
- Telegram 回调按钮：通知和回复按钮携带 `callback_data`，点击后以 `telegram.callback` 事件回到插件，插件用 `answer`/`alert`/`reply` 应答并可持续多轮交互；
- 用户点击触发的 `window.open()` 外部弹窗、图片渲染和受管页面偏好存储；
- 生成完整性清单、Ed25519 签名、包 SHA-256 和市场条目。

## 前置条件

- Node.js 20+
- npm
- TinyGo 0.43.0、Binaryen 133（本示例已实测的工具链）；`wasm-opt` 在 `PATH` 上或通过 `WASMOPT` 指定

宿主不接受 Go 标准编译器构建的模块，也拒绝链接 `encoding/json` 的模块：runtime 使用相邻 [SDK](../sdk/README.md) 的 `pluginjson` 做字段级读写，并通过 `hostapi` 处理 Storage 和 HTTP 错误。

WASM 产物与宿主 CPU 架构无关；构建环境须安装上述工具链。本示例已在 macOS x86_64 构建验证，宿主运行平台为 Linux。

## 构建

```bash
npm ci
npm run build
npm run check
npm test
```

本地预览 Vue 页面：

```bash
npm run dev
```

同一入口在正式环境通过 SDK connectPluginPage 连接宿主，自行创建 Naive UI Provider 和 Vue 应用；开发独立窗口才使用 mock。主题变量由 SDK 同步，业务操作统一使用 api。

本地 mock 支持 JSON 复制、页面存储键/额度、后台调用去重、取消和状态查询；页面偏好保存在内存，刷新预览页会重置。预览任务最多保留 128 条记录、16 个待完成回调，限额明确报错。外部地址动作返回示例 URL；通知、Host Storage、真实网络和目录监控需要安装到宿主验证，预览会明确返回 failed，不伪造成功。运行 npm test 可检查这些契约，mock 不能代替宿主集成验收。

示例页独立加载自己的框架与组件，在不透明来源沙箱中运行，宿主不接管渲染或内容高度。使用 `api.storage` 保存页面偏好，网络业务通过 action → WASM → Host Call；原生浏览器存储和直接 fetch 不可用。参见 [隔离与受管存储](../../ui-isolation-v1.md)。

UI 输出到 `build/frontend/dist/assets`，runtime 输出到 `build/runtime/plugin.wasm`。构包脚本会再次检查 WASM magic、ABI 和完整性。

运行公开的 WASM package contract check：

```bash
node ../../conformance/project-check.mjs --manifest manifest.template.json --market market-entry.template.json --build-root build --require-build
```

该检查只使用公开 schema 和 Node.js 标准库，不读取主项目源码、数据库、配置或 Docker 构建上下文。WASM 运行时的 Host Call、配额和取消语义由宿主集成测试验证。

## 首次本地签名

本地开发可生成一次 Ed25519 私钥：

```bash
npm run package -- --generate-key
```

它在本目录生成被 `.gitignore` 排除的 `developer-ed25519-private.pem`。之后直接：

```bash
npm run package
```

正式 CI 不应生成新密钥。把固定发布私钥作为 secret 文件注入，并设置：

```bash
DIAN115_PLUGIN_SIGNING_KEY=/secure/path/publisher-ed25519-private.pem npm run package
```

PowerShell：

```powershell
$env:DIAN115_PLUGIN_SIGNING_KEY = 'D:\secure\publisher-ed25519-private.pem'
npm run package
```

输出（示例模板的 URL 是占位地址；本插件包不自动上传任何仓库）：

```text
releases/example.complete-plugin-1.0.0.d115p
releases/market-entry.generated.json
```

脚本把公钥原始 32 字节的 SHA-256 编为 key ID，替换 Manifest 模板中的占位符，然后生成按 UTF-8 路径排序的完整性清单。签名原文严格为 domain、NUL、JCS Manifest、NUL、JCS integrity。私钥不会进入包。

## 发布前修改

至少修改：

1. `manifest.template.json` 中的 ID、名称、描述、版本、发布者、兼容范围、主页和仓库；
2. `market-entry.template.json` 中的包 URL；本地开发可使用 `https://example.invalid/...` 占位符，管理员也可以直接从插件中心导入 `.d115p`；
3. `index.html`、`src/main.ts` 和页面组件的名称与内容；
4. `runtime/main.go` 的 action/job/event 业务；
5. `src/AppPage.vue` 的界面；
6. Manifest 中准确的 Host API 和网络路由偏好。

如果删除 `create-watch` action，也应删除 `/api/plugin-runtime/watches` 权限和 `files.changed` event。如果新增 Host API，先确认它存在于 `../../openapi-v1.yaml` 的 Host API 目录。Host Storage 使用 `/api/plugin-runtime/storage/:key`，写入时带 `Idempotency-Key`，并在并发更新时使用响应的 `ETag` 发送 `If-Match`。

## 样例运行时说明

runtime 是 reactor，宿主在一次调用内进入 ABI；guest 可以同步调用宿主 imports。服务实例串行执行，首次打开和闲置释放后都会重新初始化。state 使用 `state-vN` 与匹配强 ETag；action 返回四种合法状态之一；job 只返回 `accepted/skipped`；Telegram event 返回严格的 `handled/reply`。

测试通知用 action invocation ID 派生 `Idempotency-Key`。目录监控同样使用稳定 key，topic 已在 Manifest events 中声明。`storage-demo` 展示 Host Storage 的 GET/PUT；`fetch-local` 接受 `http://127.0.0.1:8080/health` 或其他 HTTP/HTTPS 地址，由宿主网络 Broker 发出，宿主代理域名规则优先，非 HTTPS 不会被平台拦截。宿主消息解析仍然优先；只有未被宿主处理且命中 `/plugin_example` 或“完整插件示例”的消息才进入该 runtime。

Telegram 路由在 Manifest 的 telegram 段声明，由宿主安装和启停流程协调；闲置释放保留路由。运行时 register/unregister 均被拒绝，host.telegram.list 可读取登记。宿主先处理自己的消息，随后才向匹配插件投递。

**示例默认 `resident: false`**，不会启动额外模块、心跳或启动通知。常驻模块仅在 Manifest 中显式声明 `runtime.resident: true` 后启用：宿主用同一编译产物实例化第二个模块，在两个实例分别完成初始化后，向第二个实例发起一次不限时的 `resident` 调用，插件在其中运行主循环（示例每分钟向 Host Storage 写入一次心跳）。常驻模块与服务模块是两个独立实例、内存不共享，跨模块状态必须通过 Host Storage 等宿主服务交换；`resident` 调用返回或报错均视为循环停止，由监督器按 `restart_policy` 重启。

回调按钮在按钮对象中用 `callback_data` 代替 `url`（二选一，最长 32 字节）。点击后宿主向创建该按钮的安装实例投递 `telegram.callback` 事件，事件需要在 Manifest `events` 中声明；插件返回 `handled`、`answer`（按钮提示，≤200 字符）、`alert` 和可选的 `reply`，`reply` 与 `telegram.message` 回复格式相同且同样支持回调按钮，可构成多轮交互。空响应视为静默确认。

外部 OAuth 或详情页必须在用户点击回调中同步调用 `window.open('about:blank', ...)`，再把 action 返回的 URL 写入弹窗的 `location`。后台定时任务不能打开弹窗；浏览器拦截时应保留复制 URL 或粘贴 code 的备用流程。

## 不要复制的占位信息

`example.com`、示例插件 ID、发布者名称和市场 URL 都是占位符。不要把开发私钥或 `releases/` 提交到源码仓库。正式发布时必须使用长期稳定的发布者密钥和真实 HTTPS 包地址。

插件开发只依赖 `docs/plugin-platform/` 的公开契约；主项目源码不会作为 SDK、联调包或发布附件提供。公共发布边界见 [`../../publication-policy.md`](../../publication-policy.md)。

## 站点会话示例

`fetch-local` 使用公开 `Client.HTTP`，自动记住 Cookie，可传 input.session 区分账号；页面仅显示状态，不展示 Cookie 或响应正文。新增 action 只在明确调用时执行：

- `site-list` / `site-save` / `site-delete`：读取、保存 `{site_id,url,label}` 或删除地址，无需改包重装。
- `site-login`：页面直接填写账号、密码和附加表单字段，`PostForm` 提交；返回 verified:false，需由实际站点适配器核实业务结果，不能把 HTTP 200 当登录成功。
- `cookie-save`：输入 `{url,session,cookie}`，手填 Cookie 加密保存。
- `cookiecloud-info`：读取本地服务域名概况和 revision。
- `cookiecloud-import`：输入 `{domain,session}`，导入所选域名。
- `cookiecloud-export`：输入 `{domain,session,revision}`，明确写回共享 CookieCloud。
- `cookies-clear`：输入 `{session}`，清空自己的账号会话。
- `http-render`：输入 `{url,session}`，按需渲染；仅返回 HTML 字节数。
- `http-batch`：输入 `{urls:[...],session}`，最多 8 个地址、并发 4，缓存 TTL 30 秒；逐项返回 HTTP 状态、耗时、缓存及截断标志，不回显正文或地址。
- `http-cache-info` / `http-cache-clear`：查询或清空当前安装响应缓存，保留 Cookie。

这些 action 可通过自有页面的 api.invokeAction 调用，稳定编号按 src/actions.ts 的流程先保存。登录和手填 Cookie 使用 transientInput:true，只在普通页面存储中保存编号；密码或 Cookie 不写普通页面偏好。丢失响应后用相同内容和原编号核实/重试，不能改变输入换号登录。export 前应明确展示目标域名和用户意图，409 时不自动覆盖。所需接口在 Manifest 和市场条目中一致声明；CookieCloud 可访问 network 声明或 sites 接口保存的站点及其子域。普通 HTTP 可直接使用用户配置的地址，账号密码登录和手填 Cookie 无需 CookieCloud。正式插件删除不用的权限。示例要求宿主 5.0.53+。代码见 runtime/http_sessions.go，完整说明见 [HTTP 会话](../../http-sessions-v1.md)。

## 数据生命周期

`storage-demo` 在同一有界配置值中保存本次 invocation ID 作为 operation_ref，重试先核对已保存的业务标记，确认已完成就直接返回成功，不用新的时间戳重新写入同一幂等请求。并发版本冲突应重新核对业务状态，不自动覆盖。配置存入 Host Storage，升级、重启和休眠保留；卸载清空，重装不恢复。state 中的演示计数只存在内存，每次重新加载会重置，不能作为正式业务数据。常驻心跳使用本次业务时间作唯一标识，不用重启后归零的计数生成幂等键；所有 Host Call 均检查目标 HTTP 状态。详见 [存储与生命周期](../../storage-and-lifecycle.md)。


## 检查点与只读恢复示例

refresh job 声明 recovery_handler: refresh-recover。受管后台执行先提交游标和进度，再用稳定 invocation ID 将完成标记保存到 jobs.refresh；恢复回调只 GET 该标记，已完成就返回 complete，不存在才返回 resume，查询失败则保留错误而不假定未完成。实际插件应替换为自己的上游事实核对与幂等业务步骤。普通 cron 回调没有后台 job_ref，继续保持轻量投递。

页面提供启动、查询、“核对并恢复”和取消入口，持久保存任务引用和未确认的 start ID。首次挂载等引用恢复完成才开放启动；读取失败可显式重读，每次重试 start 都先持久保存原 ID。取消也可终止尚未核对的恢复记录。它不自动轮询；查询失败后使用同一引用重读，预览 mock 对真实恢复明确报错。详细限制见 [可恢复后台任务](../../job-recovery-v1.md)。WASM 初始化仅查询配置，不执行写入或通知；host.ui.invalidate 会向已打开页面合并推送刷新信号。

`npm test` 覆盖预览桥和页面任务会话：恢复引用期间不能启动、存储失败重试先补写原 ID、丢失 start 响应时复用原 ID、显式取消后查询。测试不创建轮询器。

## 动作重试与异常退出

页面的 actions.ts 在动作提交前保存 `action-intent.<action>`，把稳定编号作为 `api.invokeAction` 的第三个参数。响应丢失或超时保留该记录，重试使用相同输入和编号；尚未确认时修改输入会被拒绝，应先核对上游业务事实。拿到响应后清除意图，后续状态刷新失败单独提示，避免把已成功动作误判为失败。预览桥最多保存 128 条内存动作回执，重复编号重放，改变请求拒绝；它不代替真实宿主的持久回执测试。

清除意图的确认响应也可能丢失。示例保留已收到的动作结果并提示确认状态尚待核对，不把清理失败重新抛成业务失败；否则“清理已提交但响应丢失”可能导致下一次重试换用新编号。测试同时覆盖该窗口。

后台任务的取消请求一旦落库，异常退出后也保持取消，不会因尚未收尾而自动续跑。`npm test` 另覆盖动作意图写入失败不提交、丢失响应后跨页面复用原编号、预览动作重放及冲突。

网络面板可直接执行小批量只读请求和缓存查询/清空，结果仅在页面内存显示。该示例显式设置前台预算 300000 毫秒；普通请求最多等待 120 秒，批量每项 60 秒。实际网络能力探测 http_network_v2/http_batch_v1；预览环境明确报告未连接宿主。
