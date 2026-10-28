import { createApp, defineComponent, h, shallowReactive, shallowRef } from 'vue'
import { NConfigProvider, darkTheme } from 'naive-ui'
import { connectPluginPage } from '../.dian115/examples/sdk/page'
import type { PluginUIBridge, PluginPageConnection, PluginPageProps } from '../.dian115/examples/sdk/ui'
import AppPage from './AppPage.vue'
import './preview.css'

function createPreview(): PluginUIBridge {
 let name: unknown = null
 const unsupported = async (): Promise<never> => { throw new Error('本地预览未连接宿主') }
 return {
  capabilities: { isolation: 'opaque-origin-v1', storage: 'host-ui-v1', jobs: true },
  storage: { get: async <T,>() => structuredClone(name) as T | null,
   set: async (key, value) => { if (key !== 'display-name' || typeof value !== 'string' || value.length > 120) throw new Error('invalid preference'); name = value },
   remove: async () => { name = null }, clear: async () => { name = null } },
  getState: async () => ({ state_version: 'state-v1', etag: '"state-v1"', state: { message: '模拟状态已就绪' } }),
  refresh: async () => ({ preview: true }), invokeAction: unsupported,
  reportError: async (stage, reason) => { console.error('[plugin-preview]', stage, reason); return 'diag_preview' },
  jobs: { start: unsupported, get: unsupported, cancel: unsupported, resume: unsupported },
 }
}
async function start() {
 let connection: PluginPageConnection | undefined
 let initial: PluginPageProps
 if (import.meta.env.DEV && window.parent === window) initial = { api: createPreview(), installationId: 1, pluginId: 'example.complete-plugin', runtime: null, runtimeState: { preview: true }, navKey: 'main', themeContract: 'dian115-theme-v1' }
 else { connection = await connectPluginPage(); initial = { api: connection.api, ...connection.context } }
 const props = shallowReactive(initial)
 const appearance = shallowRef(theme())
 connection?.subscribe(context => { Object.assign(props, context); appearance.value = theme() })
 const Page = defineComponent({ setup: () => () => h(NConfigProvider, appearance.value, { default: () => h(AppPage, props) }) })
 const app = createApp(Page)
 app.config.errorHandler = reason => { console.error('[plugin-page]', reason); void initial.api.reportError('ui_render', reason).catch(error => console.error('[plugin-page]', error)) }
 app.mount('#app')
}
function theme() {
 const style = document.documentElement.style
 const color = (name: string, fallback: string) => style.getPropertyValue(`--dian-${name}`).trim() || fallback
 return { theme: color('color-scheme', 'light') === 'dark' ? darkTheme : null,
  themeOverrides: { common: { primaryColor: color('primary', '#2196f3'), primaryColorHover: color('primary-hover', '#1976d2'), primaryColorPressed: color('primary-pressed', '#1565c0') } } }
}
void start().catch(reason => { const root = document.getElementById('app'); if (root) root.textContent = reason instanceof Error ? reason.message : '插件页面启动失败' })
