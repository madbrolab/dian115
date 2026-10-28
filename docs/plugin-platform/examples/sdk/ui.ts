/** Public UI bridge. No native browser persistence or host credentials. */
export interface PluginUIStorage {
  get<T = unknown>(key: string): Promise<T | null>
  set(key: string, value: unknown): Promise<unknown>
  remove(key: string): Promise<unknown>
  clear(): Promise<unknown>
}
export interface PluginJob {
  job_ref: string
  kind: string
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled' | 'attention_required'
  progress: number
  cancellable: boolean
  cancel_requested?: boolean
  recovery_supported?: boolean
  recovery_pending?: boolean
  recovery_attempt?: number
  retryable?: boolean
  result?: unknown
  error?: { code?: string; detail?: string; diagnostic_id?: string }
}
export type PluginJobCancellation = { status: 'cancellation_requested' } | { job: PluginJob }
export interface RuntimeStateResponse {
  state_version?: string
  state?: Record<string, unknown>
  not_modified?: boolean
  etag?: string
}
export interface RuntimeCallbackResponse {
  invocation_id: string
  replayed: boolean
  result: { status: 'succeeded' | 'failed' | 'accepted' | 'skipped'; message?: string; [key: string]: unknown }
}
export interface PluginRuntimeSummary {
  installation_id: number
  runtime_kind: 'wasm'
  protocol?: 'dian115:wasm@1'
  entry?: string
  memory_mb?: number
  timeout_ms: number
  startup_timeout_ms?: number
  shutdown_timeout_ms?: number
  restart_policy?: 'on-failure'
  background_timeout_ms?: number
  max_concurrency?: number
  loaded?: boolean
  health_status: string
  health_error?: string
  diagnostic_id?: string
  process_state?: string
  restart_count?: number
}
export interface PluginUIBridge {
  readonly capabilities: { isolation: 'opaque-origin-v1'; storage: 'host-ui-v1'; jobs: true }
  readonly storage: PluginUIStorage
  readonly jobs: {
    /** Retain invocationId for the same business attempt; never change it on transport retry. */
    start(job: string, invocationId: string): Promise<PluginJob>
    get(jobRef: string): Promise<PluginJob>
    /** Also stops pending recovery. Completed external work is not undone; query the final state. */
    cancel(jobRef: string): Promise<PluginJobCancellation>
    /** Verify upstream state in the signed read-only callback before resuming. */
    resume(jobRef: string): Promise<PluginJob>
  }
  getState(view?: string): Promise<RuntimeStateResponse>
  /** Persist invocationId before a side effect; reuse it with identical input on retry. */
  invokeAction(action: string, input?: unknown, invocationId?: string): Promise<RuntimeCallbackResponse>
  refresh(): Promise<Record<string, unknown>>
  /** Explicit diagnostics only. Reporting never unmounts or reloads the page. */
  reportError(stage: PluginUIErrorStage, reason: unknown, severity?: 'warning' | 'error'): Promise<string>
}
export type PluginUIErrorStage = 'ui_load' | 'ui_render' | 'ui_async' | 'ui_resource'
export interface PluginPageProps {
  api: PluginUIBridge
  installationId: number
  pluginId: string
  runtime: PluginRuntimeSummary | null
  runtimeState: Record<string, unknown>
  navKey: string
  themeContract: 'dian115-theme-v1'
}
export type PluginPageContext = Omit<PluginPageProps, 'api'>
export interface PluginPageConnection {
  readonly api: PluginUIBridge
  readonly context: PluginPageContext
  /** Receives current context immediately, then host state/theme updates. */
  subscribe(listener: (context: PluginPageContext) => void): () => void
  dispose(): void
}
