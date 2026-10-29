# WASM 运行协议 v1

本协议定义 `dian115:wasm@1` reactor 与宿主的二进制 ABI、JSON 消息和生命周期。插件无需主项目源码。Manifest 使用 Plugin API v2；包签名、前端和 Host API 分别遵循对应公开文档。

## 模块与 ABI

模块导出名为 memory 的线性内存，以及下面两个函数：

```text
dian115_alloc(size: i32) -> i32
dian115_handle(ptr: i32, length: i32) -> i64
```

alloc 返回可写输入缓冲区地址，宿主复制完整 UTF-8 JSON 后调用 handle。handle 的 i64 高 32 位是输出地址，低 32 位是输出字节长度。所有地址和长度都必须位于 guest memory 内。宿主在返回前复制输出；输入和输出存活到本次调用结束即可，下次调用可以复用缓冲区。ABI 没有宿主调用的 free 函数，guest 应复用缓冲区或使用自己的有界分配策略。

模块可以导入 WASI preview1 函数，以及命名空间 dian115 下的两个函数：

```text
host_call(ptr: i32, length: i32) -> i32
host_read(ptr: i32, capacity: i32) -> i32
```

host_call 接受一个完整 JSON 请求，并返回响应字节数。guest 分配足够空间后调用 host_read；成功返回写入字节数并消费该响应。容量不足、内存越界或没有响应时返回 0。每实例只有一个待取响应，不得在读取前发起下一次 host_call；resident 与服务实例的响应缓冲相互独立。

模块必须是 reactor，不得导出 `_start`。可使用 `_initialize` 做语言运行时初始化。Go 示例通过 TinyGo 的 WASI c-shared 模式构建，普通 Go 标准运行时和 `encoding/json` 不在可接受构包范围；公开 SDK 的 `pluginjson` 提供轻量 JSON 工具。

## 消息封套

宿主调用 guest：

```json
{"method":"runtime.initialize","params":{"protocol":"dian115:wasm@1","plugin_id":"example.helper","plugin_version":"1.0.0","installation_id":1,"locale":"zh-CN","timezone":"Asia/Shanghai"}}
```

guest 必须返回 result 或 error 之一：

```json
{"result":{"ready":true,"protocol":"dian115:wasm@1"}}
```

```json
{"error":{"code":-32602,"message":"invalid request"}}
```

这里不是 stdio 流，也没有额外 JSON-RPC id。拒绝未知封套字段和尾随 JSON；error 与 result 不得同时出现。

guest 调用宿主：

```json
{"method":"host.call","params":{"method":"GET","path":"/api/plugin-runtime/storage/settings","headers":{"accept":"application/json"}}}
```

读取成功响应为 `{result: ...}`。宿主方法被拒绝时 ABI 返回 `{error: "安全说明"}`；它与 guest 返回的结构化 RPC error 形状不同。目标 HTTP 的 404、412、429、500 等仍返回在 result 中的 status/body_base64，必须按 [Host Call](host-call-v2.md) 检查，不能只检查传输是否报错。

## 初始化与停止

每次模块加载都会调用 runtime.initialize。ready 必须为 true；protocol 可以省略，提供时必须匹配。guest 通过 Host Storage 读取持久状态，不能假设上次 guest 的全局变量仍存在。

WASM 构造初始化（`_initialize`）及 `runtime.initialize` 只允许读取 Host API、查询能力和写诊断日志；业务写入、通知与检查点提交须在正式调用中执行，避免冷启动重复副作用。

runtime.shutdown 参数包含 reason，允许返回 `{stopping:true}`。宿主有关闭预算，guest 必须及时释放工作。runtime.ping 由宿主对存活模块应答，不要求 guest 实现；它不是业务健康诊断的替代品。

## 调用入口

```json
{"method":"runtime.invoke","params":{"envelope":{"op":"action","invocation_id":"inv_example123","payload":{"id":"refresh","input":{},"context":{"locale":"zh-CN","timezone":"Asia/Shanghai"}}},"background":false}}
```

op 分为 state、action、job、event，以及专门的 resident。服务实例一次执行一个 guest 调用；max_concurrency 影响接纳门限，不代表 guest 多线程执行。

### 状态

payload 为 `{view:"main",if_none_match?:"强 ETag"}`。完整返回：

```json
{"result":{"state_version":"state-v1","etag":"\"state-v1\"","state":{"enabled":true}}}
```

state_version 长 1–80 字符，使用字母数字及不连续、不位于首尾的点、短横线或下划线。ETag 必须是同版本的强 ETag；可省略，由宿主生成。未变化时仅在请求提供相同 ETag 的条件下返回 `{not_modified:true,etag:"原 ETag"}`。

状态查询只允许只读 Host Call、能力查询和诊断日志；写入、通知、检查点提交与 host.ui.invalidate 均被拒绝，避免刷新信号产生自激循环。应读取小型快照，不能每次重新扫描完整网盘。guest 全局计数适合演示，正式业务状态应持久化。

### 动作

payload 包含 id、input 和 context。成功解析的业务返回必须包含以下 status 之一：succeeded、failed、accepted、skipped。`ok` 不合法。可附加 message、job_ref 和插件自行定义的业务字段。动作 input 可以直接携带用户填写的账号、密码、Cookie、验证码，无需改名或编码绕过。

```json
{"result":{"status":"accepted","job_ref":"job_example","message":"任务已受理"}}
```

长操作通过现有 Host Job/业务任务能力提交，然后查询结果；不能只启动 guest 内存中的 goroutine 就承诺宿主重启后继续运行。重试同一动作使用原 invocation_id 和相同内容，防止不确定结果造成重复提交。

### 定时任务

payload 包含 id、handler、scheduled_for、trigger 和 attempt。任务必须在 Manifest jobs 中声明；使用数字五字段 cron，间隔至少五分钟。返回 status 只允许 accepted 或 skipped，`succeeded` 不合法。guest 自己的后续业务成功与调度投递被受理是不同状态。

### 恢复核对

声明 `jobs[].recovery_handler` 的后台调用支持持久检查点、宿主重启后的只读核对和安全续跑。`recover` 只能返回 `resume`、`complete` 或 `attention_required` 决策；完整封套、限制和示例见 [可恢复任务](job-recovery-v1.md)。

### 事件

payload 包含 id、topic、occurred_at 和 data，id 是稳定事件 ID。普通事件返回有界 JSON 对象；重复投递使用稳定事件 ID，插件业务必须幂等。Telegram 消息和按钮回调分别遵循 [Host Call](host-call-v2.md) 中的专门返回模型。

Telegram 命令和关键词在 Manifest 声明，宿主在未加载 guest 时也可匹配并唤醒插件。host.telegram.list 可读取当前登记；运行时 `host.telegram.register` 和 `host.telegram.unregister` 不再支持，均被拒绝。停用和卸载撤销路由，闲置释放保留路由。

## 宿主方法

| 方法 | 用途 |
| --- | --- |
| host.call | 安装时批准的宿主 API 或 Broker HTTP/HTTPS |
| host.log | 有界、脱敏、按安装归属的日志 |
| host.capabilities | 宿主版本、公开目录、已授予和不可用接口、特性 |
| host.telegram.list | Manifest 已登记的 Telegram 路由 |
| host.ui.invalidate | 返回 accepted，并向当前安装已打开的页面合并推送刷新信号；无页面时不唤醒 guest |
| host.job.current | 当前可恢复后台任务的引用、稳定业务 ID、检查点和核对阶段；普通调用返回 job:null |
| host.job.checkpoint | 当前可恢复任务原子提交不超过 16 KiB 的 JSON 检查点及 0–100 进度；核对阶段拒绝 |

支持 `host_call_timeout_ms` 特性的宿主允许每次 host.call 带 1–30000 毫秒 timeout_ms。先查询 capabilities，缺少特性时提示升级宿主；嵌套调用的执行期限不会超出外层调用。

## 资源预算与错误

| 层次 | 默认或上限 |
| --- | --- |
| WASM 文件 | 2 MiB |
| 线性内存 | 每实例默认 64 MiB，允许 4–512 MiB |
| 启动 | 默认 30 秒，允许 1–60 秒；另有编译槽等待预算 |
| 前台执行 | 默认 30 秒，允许 0.1–120 秒 |
| 后台执行 | 默认 5 分钟，允许 1 秒–1 小时 |
| 等待执行 | 30 秒；已加载安装 pending 最多 32 |
| ABI JSON 帧 | 16 MiB |
| 解码后的 Host Call 正文 | 请求、响应各 8 MiB |
| 普通业务输入、输出和持久回执 | 256 KiB |
| Storage | 单值 256 KiB，每安装 16 MiB |
| 宿主接纳 | 加载中及驻留安装默认最多 32；声明内存预算默认 1024 MiB，resident 按两个实例计费 |
| 常驻 | 默认最多 2 个 resident 安装，不与普通调用共享长驻执行槽 |
| 全局调用 | 最多 128 个等待/运行调用，执行最多 8 个；同一模块仍串行 |
| 宿主后台任务 | 接纳 64 / 每安装 16；执行 8 / 每安装 2；排队 30 秒，执行最长 1 小时 |

普通业务 JSON 保留不透明文本和业务标识，包括 `/`、`\`、以 `/` 开头的远端名称、插件路由、外部 cid/file_id 和分页 page_token；不根据这些内容推导路径或宿主数据库身份。宿主路径、内部 ID 和凭据在各 Host API 的权限及响应模型边界处理。通用业务校验限制 256 KiB、嵌套深度 64、值节点 16384，不根据字段名称拒绝插件业务数据，password、cookie、authorization、access_token 等自有凭据字段均允许。宿主自身凭据仍由各 Host API 控制，不能借此取得其他插件或管理员的秘密。限额作用于不同层次，不能用 8 MiB HTTP 正文限制推断页面 state 也允许 8 MiB。

排队取消不会关闭健康模块。已经开始的动作使用宿主执行预算，页面断连不撤销它；实际超时会关闭 guest，以终止死循环，并通过监管器恢复。不能通过关闭执行期限保护来规避错误。

| 机器码 | 含义与处理 |
| --- | --- |
| invocation_queue_full | 接纳门限已满，稍后使用相同业务 ID 重试 |
| invocation_queue_timeout | 等待超时，本次没有进入 guest 执行 |
| invocation_cancelled | 调用方在等待中取消 |
| runtime_starting | 运行 generation 正在切换，可稍后重试 |
| runtime_resource_limit | 宿主加载或声明内存预算不足；释放闲置插件、缩小声明或稍后重试，不消耗崩溃预算 |
| runtime_backoff | 宿主正在退避恢复 |
| runtime_package_invalid | 模块编译、ABI 或包入口无效，修复插件包后重装 |
| runtime_failed | 暂停自动重启，检查原因并更新包或手动重启 |
| runtime_timeout | guest 执行超时，需要核对副作用，不能盲目重提 |
| runtime_protocol_error | 返回结构、枚举、版本或大小不符合协议 |

暂时启动失败与运行故障共享有界重试预算；最多自动重启五次，带抖动退避。超过预算的暂时故障冷却 30 分钟后可由下次调用或常驻协调触发新预算；永久初始化拒绝不自动冷却恢复。业务失败和排队满不计作 guest 崩溃。

## 常驻模式

默认 resident 为 false，插件按需加载、空闲释放，调度、目录 watch 和 Telegram 路由由宿主管理。需要常驻主循环时才声明 resident 为 true；宿主创建第二个模块实例，两实例分别完成 runtime.initialize 后才进入 resident 调用。

两实例不共享线性内存，持久交换使用 Host Storage。resident 返回或报错均视为循环停止并触发恢复；关闭时宿主中断循环。该调用没有普通前台执行期限，插件必须在阻塞式等待、可取消 Host Call 或合理睡眠中让出资源，不能使用忙轮询。

## 持久数据

数据位置、JSON 结构、CAS、升级迁移和卸载清空规则见 [插件数据存储与生命周期](storage-and-lifecycle.md)。卸载清空，重新安装为空配置；插件不得依赖旧的保留数据或浏览器残留恢复业务状态。

调用回执按安装、调用种类和编号去重。并发相同编号只有一个执行者，其余收到可重试的 invocation_in_progress；已完成则重放原结果，相同编号改变请求返回 invocation_conflict。可重试回执重新接纳和保存结果均核对当前执行次数，旧执行迟到的成功或失败不能覆盖新执行；已进入终态的回执不再被旧结果改写。停用或卸载中的安装不能创建、重新接纳新回执，卸载后的迟到请求不能重新创建记录。

## 宿主资源设置

这些是宿主部署设置，不是 guest 的环境权限：

| 环境变量 | 默认与行为 |
| --- | --- |
| DIAN115_PLUGIN_WASM_MAX_LOADED | 默认 16 个加载实例；0 取消数量上限，常驻和忙碌实例不会强行驱逐 |
| DIAN115_PLUGIN_WASM_MAX_LOADS | 默认 4 个同时编译槽；至少 1 |
| DIAN115_PLUGIN_WASM_IDLE_TIMEOUT | 默认 15 分钟；0 关闭闲置释放 |
| DIAN115_PLUGIN_WASM_UNUSED_TIMEOUT | 默认 2 分钟；针对尚未服务过调用的预加载实例 |

资源检查约每 2 分钟运行，释放时间不是精确计时承诺。编译缓存位于宿主数据目录，可重建；它不是业务数据。


### 宿主资源开关

DIAN115_PLUGIN_WASM_MAX_EXECUTIONS 默认 8（1–64），MAX_ACTIVE 默认 32（1–128），MEMORY_BUDGET_MB 默认 1024（1–65536），MAX_RESIDENT 默认 2（1–32），后三项同样使用 DIAN115_PLUGIN_WASM_ 前缀。MAX_LOADS 编译并发默认 4，允许 1–64；无效环境值回退默认。原 MAX_LOADED 仍是闲置/LRU 软目标，不取代加载准入门限。

准入不足时先回收已经使用且没有待处理调用的普通闲置模块，不驱逐常驻或正在执行的工作；仍不足才返回 runtime_resource_limit。内存预算按 manifest 线性内存上限做加载前保守接纳估算，不是进程 RSS/cgroup 限额；编译缓存、Go heap 和正在关闭的旧代次也会占用资源，不能据此承诺 RSS 不超过该数值。减少 resident 和批量大小通常比抬高预算更合适。

全局执行槽在拿到模块串行槽之后取得，因此单个插件不能用多条等待请求占满全部执行槽。显式宿主后台取消会传到执行中的 guest，普通浏览器断连仍不撤销已开始的动作。页面后台调用、任务恢复和检查点见 [UI 隔离与后台调用](ui-isolation-v1.md)。
