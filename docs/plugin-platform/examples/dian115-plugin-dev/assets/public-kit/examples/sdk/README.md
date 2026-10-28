# 轻量插件 SDK

此 SDK 只依赖公开插件契约，不读取主项目源码或数据库。

- `pluginjson`：字段读取、Raw 片段、确定性编码；不链接 `encoding/json`。Raw 借用输入内存，跨缓冲区复用时必须复制。
- `hostapi`：Host Call HTTP 错误解析、正文 Base64、Storage 读写/元数据分页/用量、任务查询/取消、ETag/CAS 与幂等键检查。

Go 插件使用模块依赖：

```go
require example.com/dian115-plugin-sdk v0.0.0
replace example.com/dian115-plugin-sdk => ../sdk
```

完整用例见 [完整插件](../complete-plugin/README.md) 的 `storage-demo`。`hostapi.Client.Call` 注入 reactor 的宿主传输函数；它不建立 socket，不包含宿主凭据，也不连接数据库。

## 数据和重试

业务数据只放 Host Storage。键如 `settings`、`rules.rule01`，不能是文件路径；单值 256 KiB、每安装 16 MiB。`schema_version` 是业务格式版本，ETag 是并发修改版本，二者独立。

读取不存在值返回状态为 404 的 `*hostapi.Problem`。PUT 省略 ETag 表示覆盖；传入读取所得 ETag 表示 CAS，412 表示需要重新读取并由业务合并。DELETE 对不存在键成功，不接受用户指定的 If-Match。SDK 不自动重试写入，也不自行生成新幂等键。对同一业务尝试使用相同请求与相同 key；新业务必须使用不同 key。

Storage GET/PUT 会校验 HTTP 200、value（允许 JSON null）、请求键、revision、ETag 一致性及更新时间；响应缺失或不符会报错。PUT 的 ETag 必须是带双引号的正整数版本，如 `"pkv_2"`。

Host Call 的目标 HTTP 4xx/5xx 是协议层的正常返回，不代表业务成功。使用 `CheckResponse` 或 Storage helper 检查 `Problem.Status`、`Code`、`Detail` 和 `Retryable`，不要只检查传输 error。

主程序重启、插件重启和闲置释放后重新读取持久状态。卸载清空插件数据；重新安装从空配置开始。页面内存和 guest 全局变量都不是持久化存储。

## 有界分页

先探测 `host.capabilities` 的 `features.storage_catalog_v1`，并声明 `GET /api/plugin-runtime/storage` 与 `GET /api/plugin-runtime/storage-usage` 权限：

```go
page, err := client.StorageList(ctx, "rules.", "", 50)
if err != nil { return err }
// page.Items 仅含 Key、Revision、Bytes、UpdatedAt；按需 StorageGet。
if page.NextCursor != "" {
    next, err := client.StorageList(ctx, "rules.", page.NextCursor, 50)
    if err != nil { return err }
    _ = next // 每次处理一页，不无限积累结果。
}
usage, err := client.StorageUsage(ctx)
if err != nil { return err }
_ = usage.UsedBytes
```

前缀区分大小写且按字面匹配；游标绑定前缀和安装，15 分钟过期。SDK 不自动遍历、重试或将过期游标替换为空；400 时由业务决定重新开始。用量统计包括受管 UI 偏好，不包含宿主数据库文件大小。完整语义见 [存储协议](../../storage-and-lifecycle.md)。

分页响应必须提供合法的 next_cursor：null 表示结束，非空字符串表示下一页。缺失、错误类型、重复当前游标或空页携带下一页游标会报错，避免漏读或无限翻页。

## 查询和取消后台任务

在 Manifest 声明 `GET /api/plugin-host/jobs/:job_ref` 与 `POST /api/plugin-host/jobs/:job_ref/cancel`。无需手写私有运行能力名称；宿主根据批准的公开接口推导权限。只声明查询接口不会取得 115 任务的取消权限。

```go
job, err := client.JobGet(ctx, jobRef)
if err != nil { return err }
switch job.Status {
case hostapi.JobSucceeded:
    // 按该任务种类的业务协议读取 job.Result；含子任务引用时继续查询。
case hostapi.JobAttentionRequired:
    // 先核实上游结果，保留 job.Failure.Code / DiagnosticID。
case hostapi.JobFailed, hostapi.JobCancelled:
    // 已结束；取消可能发生在部分外部工作完成之后。
default:
    // 尚未结束，由页面或现有调度器控制有界刷新频率。
}
if job.CanCancel() {
    err = client.JobCancel(ctx, jobRef, "cancel-business-123456")
    if err != nil { return err }
    // 已接纳取消请求，再查询同一 jobRef 确认最终状态。
}
```

每次 JobGet/JobCancel 仅发送一次 Host Call，不创建轮询 goroutine、定时器或重试循环。JobGet 校验引用、状态枚举、进度与取消标志，错误响应返回 `*hostapi.Problem`；可用时从 Problem.DiagnosticID 或 Job.Failure.DiagnosticID 取得诊断编号。Job.Terminal() 包括 attention_required。JobSucceeded 表示此引用自身的工作完成；页面后台调用结果若为 accepted 并携带子任务引用，仍须确认子任务结果。

JobCancel 必须提供稳定幂等键，并核对 HTTP 202、任务引用与 cancellation_requested 回执。成功只表示请求已提交；有恢复记录的 failed/attention_required 仍可取消，宿主同时清空检查点并停止后续恢复。`CanCancel()` 包含该情况；`Terminal()` 只描述当前执行是否结束，不能单独用来判断恢复意图。无恢复记录的已结束任务或不支持取消返回 409，先查询现有状态。相同取消重试复用原 key，新的业务取消使用新 key。任务引用不能是路径或 URL，宿主始终限定当前安装所有权。

## 验证

```bash
go test ./...
go test ./pluginjson -fuzz=FuzzAccessNeverPanics -fuzztime=5s
```

测试中可使用 Go 标准 JSON 库作为对照，它不会进入正式 WASM。实际构包使用 TinyGo 等受支持工具链，并运行公开 project-check。包、构建产物和私钥均不属于 SDK 源码发布范围。

`ui.ts` 提供受管页面存储、后台调用记录与能力探测类型。原生浏览器存储已隔离，受管存储契约见 [UI 隔离协议](../../ui-isolation-v1.md)。


## 可恢复后台任务

`Client.CurrentJob(ctx)` 返回当前可恢复 job 的稳定业务 ID、检查点及验证标志；普通 action/event/cron 投递返回 nil。`Client.SaveCheckpoint(ctx, raw, progress)` 一次提交不超过 16 KiB 的 JSON 与进度，不自动轮询或重试。只有当前执行代次可写，核对、取消、卸载及包变化后的写入会被拒绝。

两个方法校验完整 JSON 回执，不接受合法字段后带尾随正文的伪成功。已落库的取消请求在异常退出后仍有效，启动恢复不会重新提交该任务。

Manifest 声明 recovery_handler 后，宿主在恢复时先进入只读 recover 回调；插件核对实际业务结果后返回 resume、complete 或 attention_required。页面用 api.jobs.resume(jobRef) 请求重新核对；应持久保留 job_ref，网络重试保留同一 start invocation ID。协议、封套与完整 Go 用法见 [可恢复任务](../../job-recovery-v1.md)，完整示例用 Host Storage 中的 operation_ref 证明写入是否已经完成。

页面短动作可调用 `api.invokeAction(action, input, invocationId)`。业务需要安全重试时先持久保存调用编号和原输入，再提交；结果不确定仍复用同一请求，不省略编号换新调用。成功之后的界面刷新失败单独处理。完整示例的 actions.ts 展示该流程，预览桥提供有界的编号重放与冲突检查，预览记录仅存内存。
