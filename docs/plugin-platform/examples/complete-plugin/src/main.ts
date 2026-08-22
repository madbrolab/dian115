import { createApp, defineComponent, h, reactive } from 'vue'
import { NConfigProvider, NDialogProvider, NMessageProvider, NNotificationProvider } from 'naive-ui'
import AppPage from './AppPage.vue'
import './preview.css'

const previewState = reactive({
  revision: 1,
  actionCount: 0,
  eventCount: 0,
  watchActive: false,
  lastStatus: 'ready',
  lastMessage: '本地预览已就绪',
})

const previewBridge = {
  async getState() {
    return { state: previewState, state_version: 'preview-v1', etag: '"preview-v1"' }
  },
  async invokeAction(action: string) {
    previewState.actionCount += 1
    previewState.revision += 1
    previewState.lastStatus = 'succeeded'
    previewState.lastMessage = `本地预览已执行 ${action}`
    return { result: { status: 'succeeded' as const, message: previewState.lastMessage } }
  },
  async refresh() {
    return previewState
  },
}

// This entry is only for local preview and type checking. The signed package
// loads the exposed Federation module declared in manifest.template.json.
const Preview = defineComponent({
  setup: () => () => h(NConfigProvider, null, {
    default: () => h(NMessageProvider, null, {
      default: () => h(NNotificationProvider, null, {
        default: () => h(NDialogProvider, null, {
          default: () => h(AppPage, {
            api: previewBridge,
            hostApi: previewBridge,
            installationId: 1,
            pluginId: 'example.complete-plugin',
            runtime: { health_status: 'healthy', process_state: 'running' },
            runtimeState: previewState,
            navKey: 'main',
            themeContract: 'dian115-theme-v1',
          }),
        }),
      }),
    }),
  }),
})

createApp(Preview).mount('#app')
