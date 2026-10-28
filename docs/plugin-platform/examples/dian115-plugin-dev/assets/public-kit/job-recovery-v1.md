# 可恢复后台任务

本契约适用于 `api.jobs.start` 接纳、且在签名 Manifest 的 job 中声明 `recovery_handler` 的 WASM 后台调用。任务、恢复描述和检查点先在同一事务保存，再进入主项目统一任务队列；不保存可执行闭包、不增加插件进程。宿主特性为 `recoverable_jobs_v1`。

```json
{"id":"refresh","handler":"refresh","recovery_handler":"refresh-recover","default_schedule":"*/5 * * * *","allow_overlap":false}
```

恢复 handler 长 1–80，使用 runtime identifier 规则。default_schedule 可省略或为空，此时不创建定时任务。普通 cron 回调和短 action 不自动成为可恢复的业务执行；需要长工作的页面通过后台入口接纳。现有转存等子任务仍须查询对应的 job_ref 与实际上游结果。

## 正常执行与检查点

后台 job payload 在现有字段之外包含 `job_ref`、`checkpoint` 和 `recovery_attempt`。第一次 checkpoint 为 null，recovery_attempt 为 0；恢复时为 1–3。业务 `invocation_id` 始终保持原值，scheduled_for 保持原时间。原 payload.attempt 是投递封套常量，不用它生成新的业务幂等键。

```go
client := hostapi.Client{Call: transport}
current, err := client.CurrentJob(ctx)
// current 为 nil 表示当前不是受管可恢复后台执行。
if err == nil && current != nil && !current.Verifying {
    err = client.SaveCheckpoint(ctx, pluginjson.Raw(`{"schema_version":1,"cursor":20}`), 50)
}
```

`host.job.current` 返回 `{job:null}` 或 `{job:{job_ref,invocation_id,attempt,checkpoint,verifying}}`。`host.job.checkpoint` 参数为 `{checkpoint,progress}`，提交成功返回 `{saved:true}`。检查点最多 16 KiB 有效 JSON，进度必须为 0–100 整数，深度、节点数和明确凭据字段规则与普通业务 JSON 相同。

检查点和进度一起提交；取消、卸载、停用、包变化或旧恢复代次的晚写被拒绝。检查点保存在宿主数据库、加密落盘，不占业务 KV，不会被页面存储接口读取。每安装最多 128 个未清理恢复记录，全局最多 1024；成功、取消及卸载清理，启动时清理孤立或已完成记录。业务本身的长期事实仍保存到 Host Storage 或对应主项目服务。

## 重启与上游结果核对

宿主异常退出或平滑退出后，未完成任务保持检查点并标记为结果待核实；用户主动取消不进入自动恢复。重启后重新接纳支持恢复的描述。恢复复用统一队列及其接纳、执行和取消预算，沿用调度循环每 15 秒检查；一次最多取 16 条、每安装两条。失败后至少等待 30 秒，最多恢复三次。

取消请求一旦持久提交，即使宿主在工作线程收尾前异常退出，启动恢复也优先记录 cancelled 并删除恢复描述，不会清除取消标记后再排队。恢复列表和重新接纳同时核对取消事实；取消不承诺撤销已经发生的外部副作用。

恢复先发起 `runtime.invoke`，op 为 `recover`，payload 为：

```json
{"id":"refresh","handler":"refresh-recover","job_ref":"job_…","checkpoint":{"schema_version":1,"cursor":20},"attempt":1}
```

恢复回调只允许 Host API 的 GET/HEAD 查询、host.capabilities、host.job.current 和 host.log。写请求、通知、Telegram 操作、检查点提交及其他 Host 方法均拒绝；核对不能先产生新的业务副作用。模块构造与 runtime.initialize 同样只读，正常 job 执行才取得写入能力。

插件必须查询实际业务标记、上游任务或已保存的结果，返回下列一个决策：

```json
{"decision":"resume","checkpoint":{"schema_version":1,"cursor":20}}
{"decision":"complete","result":{"status":"accepted","message":"已核对完成，无需重复提交"}}
{"decision":"attention_required"}
```

- resume 必须附带合法检查点；宿主提交核对后的检查点，再调用原 job handler，保留原业务 invocation_id。每次恢复使用独立交付回执，避免改写原回执或造成封套冲突。
- complete 的 result 必须是合法 job 响应（accepted/skipped），宿主据此完成当前后台引用并清理恢复记录，不再次调用业务 handler。
- attention_required 停止自动续跑，记录 recovery_verification_required。包摘要或恢复 handler 变化时记录 recovery_package_changed，不能用新包猜测旧检查点。

检查点提交不能与任意外部系统的写入构成跨系统事务。插件仍须使用稳定业务幂等键，并在核对阶段确认“写入已成功但检查点尚未提交”等情况；结果不确定时必须返回 attention_required。

## 页面查询与人工恢复

```ts
const job = await api.jobs.get(savedJobRef)
if (job.recovery_supported && ['failed', 'attention_required'].includes(job.status)) {
  const checking = await api.jobs.resume(job.job_ref)
}
```

job 可带 recovery_supported、recovery_pending 和 recovery_attempt。resume 仍先执行只读核对，只接纳当前安装拥有、未超过恢复预算的记录；忙碌、不支持或预算耗尽返回 409。重试同一次 start 要保存原 invocation ID；页面应持久保存 job_ref，不能刷新后另起同一业务。完整示例展示稳定业务标记、检查点、恢复决策及页面引用保存。

`api.jobs.cancel(jobRef)` 同样可取消 failed/attention_required 状态下仍有恢复记录的任务，包括等待自动核对和已停止自动核对的记录。宿主原子地记录 cancelled、删除检查点并生成新的取消事件；与恢复接纳竞争时，要么取消尚未接纳的恢复，要么向已接纳执行提交取消请求。取消之后不会再次自动恢复。已完成且没有恢复记录的任务不能撤销外部业务结果。

页面首次挂载应等待受管存储中的任务引用读取完成，再开放启动入口；读取失败提供显式重读。每次 start 重试都先持久保存相同 invocation ID，不能因上次写存储失败而只使用内存中的 ID。完整示例不自动轮询，只有用户操作才查询或恢复任务。
