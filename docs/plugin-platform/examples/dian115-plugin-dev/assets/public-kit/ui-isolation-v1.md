# UI 隔离、持久存储与后台调用

UI 入口协议见 [独立页面](ui-page-v1.md)。宿主不接管渲染、全局错误或内容尺寸。当前 UI 特性标识为 `opaque-origin-v1`，存储标识为 `host-ui-v1`。运行时 UI 声明返回 isolation/storage，组件通过 `api.capabilities` 探测。WASM ABI 仍为 `dian115:wasm@1`。

## 浏览器边界

页面由完整签名 HTML 入口提供。宿主 iframe 使用 `sandbox="allow-scripts allow-forms allow-popups allow-downloads"`，不授予 allow-same-origin、顶层导航或弹窗逃逸。每个文档有独立的不透明来源，不能访问父页面 DOM、宿主/其他插件的 localStorage、sessionStorage、IndexedDB、Cache API、Cookie 或 Service Worker。不要通过修改键名前缀来模拟隔离，也不要移除沙箱或退回同源加载。

插件 HTML 文档的 CSP 禁止直接 fetch/XHR/WebSocket、子 frame、表单提交、object 和 base URL 修改，允许 Blob Worker。签名页面和静态资源通过支持匿名 CORS 的能力地址加载；SDK 同步主题变量，插件自行打包框架并建立 Provider。图片、字体、媒体仍受 CSP、CORS 和混合内容规则约束。网络业务使用 action → WASM → Host Call。

postMessage 只接纳当前 frame window、source 和随机 channel；异步回复也核对原 frame/channel。插件不能在消息里选择其他 installation_id。每页同时最多 32 个未完成 RPC；JSON 消息最多 1 MiB，原有业务响应 256 KiB 限制不变。页面替换后不向新插件回复旧请求结果。

弹窗继承沙箱，不能依赖外部页面拥有普通窗口的全部 Cookie、表单和存储行为。需要外部授权的插件必须提供复制授权 URL、手工粘贴 code 等备用流程。不能通过 allow-popups-to-escape-sandbox 为任意插件打开同源存储访问。

## 受管页面存储

```ts
await api.storage.set('display-settings', { schema_version: 1, compact: true })
const settings = await api.storage.get('display-settings') // 不存在返回 null
await api.storage.remove('display-settings')
await api.storage.clear() // 仅清理此安装的页面偏好
```

接口全部异步，成功表示宿主已提交，不是假装同步 localStorage 后台写入。键遵循运行时标识符规则，最长 80 字符；每值 JSON 最多 128 KiB，最多 512 个键，全部序列化后最多 1 MiB。超过限制拒绝写入；没有隐式无限重试。数据放在同安装既有 KV 的 `ui.preferences.v1`，计入该安装 64 MiB 总配额，不新建浏览器数据库、进程或连接池。插件不应把此保留键当作自己的普通配置键覆写。

多个页面修改不同键通过 CAS 合并，不丢失已提交值；同键后提交覆盖先提交。持续争用返回 version_conflict，可由用户重新操作。存储不是密钥库，敏感服务凭据使用宿主 credential_ref。短暂表单和页面会话状态留在 Vue 内存即可。

升级、停用、重启和页面刷新保留受管偏好；卸载连同业务 KV 一起清空。旧页面使用旧 installation_id 的晚写被拒绝，重新安装使用新身份、空存储。clear 不清理业务 KV，也不影响宿主或其他插件。

## 可查询、可取消的后台调用

```ts
const invocationId = 'inv_sync_business_20261027' // 同一次业务重试保留此 ID
const run = await api.jobs.start('refresh', invocationId)
const latest = await api.jobs.get(run.job_ref)
await api.jobs.cancel(run.job_ref)
```

start 仅允许安装清单已声明的 job，立即接纳并返回任务引用，不把后台执行预算当浏览器请求超时。相同安装和 invocation ID 重放同一记录；更换 job 却复用 ID 返回 invocation_conflict。页面关闭不会取消已接纳工作，取消必须显式请求。get/cancel 只允许当前安装的任务引用，包括 action 返回的宿主子任务引用。

cancel 也可终止仍持有恢复记录的 failed/attention_required 任务，清除检查点和后续恢复意图；返回取消接纳回执后查询同一引用确认状态。成功终态及无恢复记录的其他终态只返回现有记录，不承诺撤销已经完成的业务。停用和卸载状态下不能请求恢复，订阅注册与启停、卸载共用生命周期保护，已撤销页面不能重新挂上旧安装事件流。

宿主收到 revoked 时立即关闭旧沙箱，再读取当前安装列表；卸载跳回插件中心，停用使用最新停用状态。旧页面加载请求晚到不能重新挂载已撤销的代次。事件连接只在安装身份、启用状态、页面可见性或运行组件可用性变化时重建；普通运行元数据更新不重连，避免初始刷新与重连形成循环。

外层记录表示一次 guest job 调用的执行与交付。其 succeeded 表示该回调已返回合法响应；原回调仍只能返回 accepted/skipped，accepted 不等于业务全部完成。如果返回子任务 job_ref，应继续查询那个引用；不要将回调成功作为文件转存等上游业务成功。插件通过 Host Storage 保存有界检查点，并用稳定业务键避免重复副作用。

任务先持久化，随后排队执行。默认宿主后台任务同时接纳 64 个、每安装 16 个；执行上限全局 8 个、每安装 2 个；排队最多 30 秒，实际执行最长 1 小时，guest 仍受 manifest 更短预算约束。满额不创建额外 goroutine 或持久队列记录；排队超时/取消、执行失败、期限和结果保存失败有明确终态。回调 panic 被限制在单任务内。

页面发起的后台 job 和 Host Job Broker 的长任务进入主项目“任务队列”，类型为“第三方插件后台任务”。进度从同一持久任务记录同步；统一队列的取消传到原任务，已完成终态拒绝晚到取消。插件仍通过原 job_ref 查询，不依赖主项目队列内部 ID。任务使用有界的插件执行通道，不占用整理、扫描的普通 worker；没有新增轮询服务或独立任务数据库。短 action、普通 state 和定时回调投递不会为了显示而各造一条队列任务。

不支持手动取消的业务仍保留原限制；停用和卸载属于执行权撤销，会停止关联工作。卸载同时移除该安装在统一队列中的记录，不影响其他插件或主项目任务。统一队列历史在内存中，宿主重启后的事实以持久 Host Job 为准，不承诺重新展示旧队列行或自动重做外部操作。

显式取消会传到执行中的 guest；中断执行可能需要关闭该模块，下一次调用重新初始化。这种取消不消耗崩溃重启预算。宿主退出、停用和卸载会取消关联后台工作；结果不确定的非幂等上游操作必须查询事实，不能因为本地显示取消就重复提交。

统一任务队列、页面后台接口和 Host Job 取消使用同一套持久化与唤醒逻辑。仍在等待执行槽的任务收到取消后立即退出等待，无需等满排队期限。取消与完成竞争时以持久终态为准；任务已经结束后，不再将其修改为取消。

宿主重启后，未完成 host job 进入 attention_required，并标记 submission_uncertain。声明 recovery_handler 的 WASM 后台调用会通过统一队列先只读核对，按结果完成或从检查点续跑；其余任务保留待核实状态，不盲目重做上游操作。持久化 cron 队列按原 invocation ID 恢复。调度取数每安装最多两条，运行同样每安装最多两条，防止单个安装的积压挡住其他插件。

后台引用、调用 ID 与恢复入口见 [可恢复任务](job-recovery-v1.md)。页面保存 job_ref 后，即使刷新页面也能查询同一任务；`api.jobs.resume(jobRef)` 会重新核对，不直接重复业务写入。

页面刷新信号复用宿主有界 SSE；同一安装最多 8 个页面、全局 256 个订阅，信号每 250 毫秒合并，无持久历史。连接重建时刷新一次当前状态，页面隐藏时断开；在线时停止定时状态轮询，断线时使用原有有界刷新。运行元数据变化只读取 metadata，不为显示空闲状态唤醒 guest。

## 管理端传输入口

这些入口供宿主页面桥使用，继承管理员鉴权，不是可让 guest 直连的 Host API。页面无需获得管理员 token。

| 方法与路径（共同前缀 `/api/plugin-center/v1/installations/:id/runtime`） | 作用 |
| --- | --- |
| GET `/ui-events` | SSE invalidate/status/revoked 信号，不携带业务数据 |
| POST `/ui-errors` | 显式页面诊断，stage/detail/severity，返回 diagnostic_id，每安装每分钟最多 10 条 |
| POST `/job-runs/:ref/resume` | 重新核对并恢复声明支持的任务，返回 202 job |
| GET `/ui-storage/:key` | 返回 `{value}` |
| PUT `/ui-storage/:key` | 请求 `{value}`，提交页面偏好 |
| DELETE `/ui-storage/:key` | 删除页面键 |
| DELETE `/ui-storage` | 清空当前安装页面偏好 |
| POST `/jobs/:job/runs` | 请求 `{invocation_id}`，202 返回 `{job,replayed}` |
| GET `/job-runs/:ref` | 返回 `{job}` |
| DELETE `/job-runs/:ref` | 请求取消，已完成任务返回现有记录 |
| GET `/diagnostics` | 管理员读取最近诊断、级别、发生时间与 KV 用量，不开放给 guest |

## 当前接入要求

业务数据使用 Host Storage，页面偏好使用 api.storage，网络业务使用 action/Host Call。页面通过 `api.capabilities.storage === 'host-ui-v1'` 确认受管存储能力；缺少所需能力时明确报错。

插件必须满足当前 WASM、签名资源和沙箱契约。宿主不提供旧页面同源加载、原生浏览器存储或旧运行方式的回退通道。

可复用类型见 [SDK UI 类型](examples/sdk/ui.ts)。宿主来源隔离依照 [HTML iframe sandbox 标准](https://html.spec.whatwg.org/multipage/iframe-embed-object.html#attr-iframe-sandbox)；后台和资源预算还见 [WASM 协议](wasm-runtime-v1.md)。
