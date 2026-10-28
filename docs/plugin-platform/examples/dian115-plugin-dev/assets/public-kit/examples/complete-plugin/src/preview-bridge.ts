import type { PluginJob, PluginUIBridge, RuntimeCallbackResponse } from '../../sdk/ui'

const identifier = /^[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*$/
const bytes = (value: unknown) => new TextEncoder().encode(JSON.stringify(value)).length
function copy<T>(value: T): T {
  const raw = JSON.stringify(value)
  if (raw === undefined) throw new TypeError('值必须能序列化为 JSON')
  if (raw.length > 1_048_576 || new TextEncoder().encode(raw).length > 1_048_576) throw new TypeError('插件消息超过 1 MiB 上限')
  return JSON.parse(raw) as T
}
function storageKey(key: string) {
  if (!key || key.length > 80 || !identifier.test(key)) throw new Error('invalid_storage_key')
}

/** Local preview of the public bridge. Host I/O actions fail explicitly;
 * timers run only for manually started mock callbacks, with bounded records. */
export function createPreviewBridge(state: Record<string, unknown>, declaredJobs: readonly string[]): PluginUIBridge {
  const storage: Record<string, unknown> = Object.create(null)
  const jobs = new Map<string, PluginJob>()
  const invocations = new Map<string, string>()
  const actions = new Map<string, { signature: string; response: RuntimeCallbackResponse }>()
  const timers = new Map<string, ReturnType<typeof setTimeout>>()
  let sequence = 0
  const update = (message: string, status = 'succeeded') => {
    state.revision = Number(state.revision || 0) + 1
    state.lastStatus = status
    state.lastMessage = message
  }
  const find = (ref: string) => {
    const job = jobs.get(ref)
    if (!job) throw new Error('resource_not_found')
    return job
  }
  return {
    async reportError(stage, reason, severity = 'error') { console[severity === 'warning' ? 'warn' : 'error']('[plugin-preview]', stage, reason); return 'diag_preview' },
    capabilities: { isolation: 'opaque-origin-v1', storage: 'host-ui-v1', jobs: true },
    storage: {
      async get<T>(key: string) { storageKey(key); return key in storage ? copy(storage[key]) as T : null },
      async set(key, value) {
        storageKey(key)
        const saved = copy(value)
        const next = { ...storage, [key]: saved }
        if (bytes(saved) > 16 * 1024 || Object.keys(next).length > 128 || bytes(next) > 64 * 1024) throw new Error('quota_exceeded')
        storage[key] = saved
      },
      async remove(key) { storageKey(key); delete storage[key] },
      async clear() { for (const key of Object.keys(storage)) delete storage[key] },
    },
    async getState(view = 'main') {
      if (!identifier.test(view) || view.length > 80) throw new Error('invalid_view')
      const version = `state-v${Number(state.revision || 1)}`
      return { state: copy(state), state_version: version, etag: `"${version}"` }
    },
    async refresh() { return copy(state) },
    async invokeAction(action, input = {}, invocationId) {
      if (!identifier.test(action) || action.length > 80) throw new Error('invalid_action')
      const signature = JSON.stringify([action, copy(input)])
      const invocation_id = invocationId ?? `inv_preview_${++sequence}`
      if (!invocation_id.startsWith('inv_') || invocation_id.length > 80 || !identifier.test(invocation_id)) throw new Error('invalid_invocation_id')
      const existing = actions.get(invocation_id)
      if (existing) {
        if (existing.signature !== signature) throw new Error('invocation_conflict')
        return { ...copy(existing.response), replayed: true }
      }
      if (actions.size >= 128) throw new Error('preview_action_capacity')
      let result: RuntimeCallbackResponse['result']
      if (action === 'refresh') result = { status: 'succeeded', message: '运行时状态已刷新' }
      else if (action === 'external-link') result = { status: 'succeeded', url: 'https://example.com/oauth/start', message: '外部页面地址已生成' }
      else result = { status: 'failed', message: '本地预览未连接宿主，请安装插件后验证此业务动作' }
      state.actionCount = Number(state.actionCount || 0) + 1
      update(result.message || '', result.status)
      const response = { invocation_id, replayed: false, result }
      actions.set(invocation_id, { signature, response: copy(response) })
      return response
    },
    jobs: {
      async start(id, invocationId) {
        if (!declaredJobs.includes(id)) throw new Error('job_not_declared')
        if (!invocationId.startsWith('inv_') || invocationId.length > 80 || !identifier.test(invocationId)) throw new Error('invalid_invocation_id')
        const existing = invocations.get(invocationId)
        if (existing) {
          const job = find(existing)
          if (job.kind !== `runtime.job.${id}`) throw new Error('invocation_conflict')
          return copy(job)
        }
        if (timers.size >= 16 || jobs.size >= 128) throw new Error('job_queue_full')
        const ref = `job_${(++sequence).toString(16).padStart(32, '0')}`
        const job: PluginJob = { job_ref: ref, kind: `runtime.job.${id}`, status: 'queued', progress: 0, cancellable: true }
        jobs.set(ref, job)
        invocations.set(invocationId, ref)
        timers.set(ref, setTimeout(() => {
          timers.delete(ref)
          job.status = 'succeeded'; job.progress = 100
          job.result = { status: 'accepted', message: '定时刷新已接受' }
          update('定时刷新已接受')
        }, 0))
        return copy(job)
      },
      async get(ref) { return copy(find(ref)) },
      async resume() { throw new Error("本地预览不执行上游核对和任务恢复，请安装插件后验证") },
      async cancel(ref) {
        const job = find(ref)
        if (job.status !== 'queued' && job.status !== 'running') return { job: copy(job) }
        clearTimeout(timers.get(ref)); timers.delete(ref)
        job.cancel_requested = true; job.status = 'cancelled'
        return { status: 'cancellation_requested' }
      },
    },
  }
}
