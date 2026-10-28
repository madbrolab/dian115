import { createApp, defineComponent, h, reactive } from 'vue'
import { NConfigProvider, NDialogProvider, NMessageProvider, NNotificationProvider } from 'naive-ui'
import AppPage from './AppPage.vue'
import './preview.css'
import { createPreviewBridge } from './preview-bridge'
import manifest from '../manifest.template.json'

const previewState = reactive({
  revision: 1,
  actionCount: 0,
  eventCount: 0,
  watchActive: false,
  lastStatus: 'ready',
  lastMessage: '本地预览已就绪',
})

const previewBridge = createPreviewBridge(previewState, manifest.jobs.map(job => job.id))

// This entry is only for local preview and type checking. The signed package
// loads the exposed Federation module declared in manifest.template.json.
const Preview = defineComponent({
  setup: () => () => h(NConfigProvider, null, {
    default: () => h(NMessageProvider, null, {
      default: () => h(NNotificationProvider, null, {
        default: () => h(NDialogProvider, null, {
          default: () => h(AppPage, {
            api: previewBridge,
            installationId: 1,
            pluginId: 'example.complete-plugin',
            runtime: { installation_id: 1, runtime_kind: 'wasm', timeout_ms: 30000, health_status: 'healthy', process_state: 'running' },
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
