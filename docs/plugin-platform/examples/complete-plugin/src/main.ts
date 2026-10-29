import { createApp, defineComponent, h, shallowReactive, shallowRef } from 'vue'
import { NConfigProvider, NDialogProvider, NMessageProvider, NNotificationProvider, darkTheme } from 'naive-ui'
import { connectPluginPage } from '../../sdk/page'
import type { PluginPageConnection, PluginPageProps } from '../../sdk/ui'
import AppPage from './AppPage.vue'
import './preview.css'

async function start() {
  let connection: PluginPageConnection | undefined
  let initial: PluginPageProps
  if (import.meta.env.DEV && window.parent === window) {
    const { createPreviewBridge } = await import('./preview-bridge')
    const { default: manifest } = await import('../manifest.template.json')
    const state = shallowReactive<Record<string, unknown>>({ revision: 1, actionCount: 0, eventCount: 0, watchActive: false, lastStatus: 'ready', lastMessage: '本地预览已就绪' })
    initial = { api: createPreviewBridge(state, manifest.jobs.map(job => job.id)), installationId: 1, pluginId: manifest.id,
      runtime: { installation_id: 1, runtime_kind: 'wasm', timeout_ms: 300000, health_status: 'healthy', process_state: 'running' },
      runtimeState: state, navKey: 'main', themeContract: 'dian115-theme-v1' }
  } else {
    connection = await connectPluginPage()
    initial = { api: connection.api, ...connection.context }
  }
  const props = shallowReactive(initial)
  const appearance = shallowRef(theme())
  connection?.subscribe(context => { Object.assign(props, context); appearance.value = theme() })
  const Page = defineComponent({ setup: () => () => h(NConfigProvider, appearance.value, {
    default: () => h(NMessageProvider, null, { default: () => h(NNotificationProvider, null, {
      default: () => h(NDialogProvider, null, { default: () => h(AppPage, props) }),
    }) }),
  }) })
  const app = createApp(Page)
  app.config.errorHandler = reason => {
    console.error('[plugin-page]', reason)
    void initial.api.reportError('ui_render', reason).catch(error => console.error('[plugin-page] 诊断上报失败', error))
  }
  app.mount('#app')
}
function theme() {
  const style = document.documentElement.style
  const color = (name: string, fallback: string) => style.getPropertyValue(`--dian-${name}`).trim() || fallback
  return { theme: color('color-scheme', 'light') === 'dark' ? darkTheme : null,
    themeOverrides: { common: { primaryColor: color('primary', '#2196f3'), primaryColorHover: color('primary-hover', '#1976d2'), primaryColorPressed: color('primary-pressed', '#1565c0'),
      bodyColor: color('surface', '#f5f6f8'), cardColor: color('surface', '#ffffff'), textColorBase: color('text-primary', 'rgba(0,0,0,.88)') } } }
}
void start().catch(reason => {
  const root = document.getElementById('app')
  if (root) root.textContent = reason instanceof Error ? reason.message : '插件页面启动失败'
})
