import type { PluginPageConnection, PluginPageContext, PluginUIBridge, PluginUIErrorStage } from './ui'
import { clonePluginMessage } from './message'
import { pluginErrorDetail } from './diagnostics'

const SOURCE = 'dian115-plugin-page'
type Message = Record<string, any>

/** Connect an ordinary HTML page. This SDK does not mount a framework,
 * observe layout, intercept global errors, poll, or control page rendering. */
export function connectPluginPage(options: { timeoutMS?: number } = {}): Promise<PluginPageConnection> {
  return new Promise((resolve, reject) => {
    const channel = decodeURIComponent(window.location.hash.slice(1))
    if (window.parent === window || !channel || channel.length > 160) {
      reject(new Error('请从 DIAN115 插件中心打开此页面'))
      return
    }
    const pending = new Map<string, { resolve: (value: any) => void; reject: (reason: Error) => void; timer: number }>()
    const listeners = new Set<(context: PluginPageContext) => void>()
    let context: PluginPageContext
    let connected = false, disposed = false, sequence = 0
    const timeout = Math.max(100, Math.min(60_000, options.timeoutMS || 30_000))
    const initTimer = window.setTimeout(() => dispose(new Error('插件页面连接宿主超时')), timeout)
    function send(message: Message) {
      window.parent.postMessage(clonePluginMessage({ ...message, source: SOURCE, channel }), '*')
    }
    function dispose(reason = new Error('插件页面连接已关闭')) {
      if (disposed) return
      disposed = true
      window.clearTimeout(initTimer)
      window.removeEventListener('message', receive)
      window.removeEventListener('pageshow', pageShow)
      window.removeEventListener('pagehide', pageHide)
      for (const request of pending.values()) { window.clearTimeout(request.timer); request.reject(reason) }
      pending.clear()
      listeners.clear()
      if (!connected) reject(reason)
    }
    function call(op: string, payload: Message = {}): Promise<any> {
      if (disposed) return Promise.reject(new Error('插件页面连接已关闭'))
      if (!connected) return Promise.reject(new Error('插件页面尚未连接宿主'))
      if (pending.size >= 32) return Promise.reject(new Error('插件页面请求过多，请等待当前操作完成'))
      const id = `${Date.now().toString(36)}-${++sequence}`
      const runtime = context.runtime
      const callTimeout = ['invokeAction', 'getState', 'refresh'].includes(op)
        ? Math.max(100, Math.min(120_000, Number(runtime?.timeout_ms) || 30_000)) + Math.max(1_000, Math.min(60_000, Number(runtime?.startup_timeout_ms) || 30_000)) + 70_000
        : 30_000
      return new Promise((accept, fail) => {
        const timer = window.setTimeout(() => { pending.delete(id); fail(new Error('宿主响应超时')) }, callTimeout)
        pending.set(id, { resolve: accept, reject: fail, timer })
        try { send({ type: 'rpc', id, op, ...payload }) }
        catch (reason) { window.clearTimeout(timer); pending.delete(id); fail(reason) }
      })
    }
    const api: Readonly<PluginUIBridge> = Object.freeze({
      capabilities: Object.freeze({ isolation: 'opaque-origin-v1', storage: 'host-ui-v1', jobs: true }),
      getState: (view = 'main') => call('getState', { view }),
      invokeAction: (action: string, input: unknown = {}, invocationId?: string) => call('invokeAction', { action, input, invocationId }),
      refresh: () => call('refresh'),
      reportError: (stage: PluginUIErrorStage, reason: unknown, severity: 'warning' | 'error' = 'error') => call('diagnostics.report', { stage, detail: pluginErrorDetail(reason), severity }),
      storage: Object.freeze({
        get: (key: string) => call('storage.get', { key }),
        set: (key: string, value: unknown) => call('storage.set', { key, value }),
        remove: (key: string) => call('storage.remove', { key }),
        clear: () => call('storage.clear'),
      }),
      jobs: Object.freeze({
        start: (job: string, invocationId: string) => call('jobs.start', { action: job, value: invocationId }),
        get: (jobRef: string) => call('jobs.get', { key: jobRef }),
        cancel: (jobRef: string) => call('jobs.cancel', { key: jobRef }),
        resume: (jobRef: string) => call('jobs.resume', { key: jobRef }),
      }),
    })
    const connection: PluginPageConnection = {
      api,
      get context() { return context },
      subscribe(listener) {
        if (disposed) throw new Error('插件页面连接已关闭')
        listeners.add(listener)
        try { listener(context) } catch (reason) { listeners.delete(listener); throw reason }
        return () => { listeners.delete(listener) }
      },
      dispose: () => dispose(),
    }
    function publish() {
      // A plugin subscriber failure must not break RPC delivery or other subscribers.
      for (const listener of listeners) {
        try { listener(context) } catch (reason) { console.error('[plugin-page] 状态订阅失败', reason) }
      }
    }
    function theme(values: Message) {
      for (const [name, value] of Object.entries(values)) {
        if (/^--dian-[a-z0-9-]+$/.test(name) && typeof value === 'string' && value.length <= 2048) document.documentElement.style.setProperty(name, value)
      }
    }
    function receive(event: MessageEvent) {
      if (disposed || event.source !== window.parent || event.data?.source !== SOURCE || event.data?.channel !== channel) return
      let message: Message
      try { message = clonePluginMessage(event.data) } catch { return }
      if (message.type === 'rpc-result' && typeof message.id === 'string') {
        const request = pending.get(message.id)
        if (!request) return
        pending.delete(message.id)
        window.clearTimeout(request.timer)
        if (message.error) request.reject(new Error(String(message.error)))
        else request.resolve(message.value)
        return
      }
      if (message.type === 'init') {
        if (!Number.isSafeInteger(message.installation?.id) || message.installation.id <= 0 || typeof message.installation.plugin_id !== 'string') return
        context = Object.freeze({ installationId: message.installation.id, pluginId: message.installation.plugin_id,
          runtime: message.runtime || null, runtimeState: message.runtimeState?.state || {}, navKey: 'main', themeContract: 'dian115-theme-v1' })
        if (message.theme) theme(message.theme)
        if (!connected) { connected = true; window.clearTimeout(initTimer); resolve(connection) }
        publish()
      } else if (connected && message.type === 'state') {
        context = Object.freeze({ ...context, runtime: message.runtime === undefined ? context.runtime : message.runtime,
          runtimeState: message.runtimeState?.state || context.runtimeState })
        publish()
      } else if (connected && message.type === 'theme' && message.theme) {
        theme(message.theme)
        publish()
      }
    }
    function pageShow(event: PageTransitionEvent) { if (event.persisted && !disposed) send({ type: 'ready' }) }
    function pageHide(event: PageTransitionEvent) { if (!event.persisted) dispose() }
    window.addEventListener('message', receive)
    window.addEventListener('pageshow', pageShow)
    window.addEventListener('pagehide', pageHide)
    try { send({ type: 'ready' }) } catch (reason) { dispose(reason instanceof Error ? reason : new Error('插件页面连接失败')) }
  })
}
