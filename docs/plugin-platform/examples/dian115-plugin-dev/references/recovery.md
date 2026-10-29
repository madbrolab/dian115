# 动作、长任务与恢复

## 短动作的副作用

复用完整示例 `src/actions.ts` 的 intent 流程：点击处理函数先占用 busy，恢复完成后读取未确认记录，普通业务保存稳定 invocation ID 和原输入成功后才提交；密码/Cookie 使用 transientInput:true，只保存编号，重新提供原字段，由宿主请求哈希阻止改内容重放，回执由宿主加密保存。新输入不得覆盖未确认业务。`api.invokeAction(action,input,id)` 的第三参必须保留；跨页面重试仍用同一编号。对可能来自较旧宿主的桥，应先核对支持情况，不能丢掉编号悄悄调用。

Host Call 写请求用该业务 ID 派生稳定 Idempotency-Key。外部系统仍有自己的幂等/查询规则，宿主回执不能证明无限期 exactly-once。网络断开、runtime timeout 或丢失响应时先查询回执或上游业务事实，不换编号直接重发。回执过期后也遵循事实核对。

收到已确认动作结果后，清除意图失败或刷新失败单独展示，不能抛回成新的业务失败；清理实际提交但响应丢失是需要测试的窗口。先保留已经知道的结果，再决定是否允许新的操作。

## 长任务

页面用 `api.jobs.start(handler,invocationId)`，先持久保存 start ID，取得 job_ref 后保存引用；响应不确定时保留原 start ID。调用记录进入宿主统一任务队列，不创建插件自己的常驻队列或后台 goroutine 来绕过预算。Host API 返回的异步业务 job_ref 与页面后台任务引用按对应协议分别查询，父调用 accepted 不代表子业务完成。

复用完整示例 `src/background-job.ts`；给用户查询、取消及必要时“核对并恢复”入口。取消可与状态更新竞争，202/取消接纳不代表业务回滚；查询最终结果。恢复意图的取消在宿主重启后仍有效。隐藏页面暂停非必要查询，优先宿主刷新信号；确需轮询时有界退避并在离开页面时清理。

需要异常退出后安全续跑时，在 Manifest job 声明 recovery_handler；读 job-recovery-v1.md 的完整封套。通过 CurrentJob/SaveCheckpoint 保存业务 ID、游标和有界进度。恢复回调先只读查询上游事实：已完成→complete；确定未完成且安全→resume；无法确认→attention_required。核对失败不能假定没执行。resume 后仅执行未完成的幂等步骤。

包变化、取消和过时代次的检查点拒绝按宿主错误处理，不绕过校验。resident 是第二个独立 WASM 实例，与服务实例不共享内存；只有持续连接等需求确实不能由调度/watch/事件完成时才考虑它。
