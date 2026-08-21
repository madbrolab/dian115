# DIAN115 Vue Federation UI v1

每个插件必须提供一个签名的 Vue 3 Module Federation 页面。该页面在独立 opaque-origin iframe 中运行，使用宿主提供的 Vue 3、Naive UI 和 `@lucide/vue` singleton，并通过 `dian115-theme-v1` 变量跟随宿主主题。

不存在声明式 UI、HTML 片段模式或加载失败回退协议。Federation 页面无法加载时，宿主显示错误，用户可以重试或管理插件。

## 1. Manifest 契约

```json
{
  "ui": {
    "mode": "federation",
    "icon": "frontend/icon.svg",
    "federation": {
      "entry": "frontend/dist/assets/remoteEntry.js",
      "assets_root": "frontend/dist/assets",
      "module": "./AppPage"
    }
  }
}
```

- `ui`、`mode` 和 `federation` 必需；
- `mode` 固定为 `federation`；
- `entry` 和 `assets_root` 是包内相对路径；
- `entry` 必须位于 `assets_root/` 内；
- `module` 省略时为 `./AppPage`；
- `icon` 可选，但界面本身不可选；
- entry、icon 和所有动态 import 的 JS/CSS/字体/图片必须存在于包中并由 `integrity.json` 覆盖。

宿主用安装 ID、包 SHA-256 和 HMAC capability token 构造只读资源 URL。升级后 SHA 路径变化，旧资源 URL 自动失效。资源响应允许跨 origin ESM 加载，但不授予业务 API 权限。

## 2. 构建配置

`package.json` 应把三个宿主包同时列为 peer 和开发依赖：

```json
{
  "type": "module",
  "peerDependencies": {
    "vue": "^3.4.0",
    "naive-ui": "^2.38.0",
    "@lucide/vue": "^1.16.0"
  },
  "devDependencies": {
    "vue": "^3.4.0",
    "naive-ui": "^2.38.0",
    "@lucide/vue": "^1.16.0",
    "@originjs/vite-plugin-federation": "^1.4.1",
    "@vitejs/plugin-vue": "^5.2.4",
    "vite": "^6.4.3",
    "typescript": "^5.0.0",
    "vue-tsc": "^2.0.0"
  }
}
```

`vite.config.ts`：

```ts
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import federation from '@originjs/vite-plugin-federation'

// 当前插件的运行时支持 singleton，但发布的类型声明尚未包含该字段。
const hostSharedDependencies = {
  vue: { singleton: true, requiredVersion: false, generate: false },
  'naive-ui': { singleton: true, requiredVersion: false, generate: false },
  '@lucide/vue': { singleton: true, requiredVersion: false, generate: false },
} as any

export default defineConfig({
  plugins: [
    vue(),
    federation({
      name: 'example_complete_plugin',
      filename: 'remoteEntry.js',
      exposes: {
        './AppPage': './src/AppPage.vue',
      },
      shared: hostSharedDependencies,
    }),
  ],
  build: {
    target: 'esnext',
    cssCodeSplit: true,
    assetsDir: 'assets',
  },
})
```

`@originjs/vite-plugin-federation` 的生产端默认生成 ESM remote entry，不要添加只适用于消费端 remote 配置的顶层 `format`。三个 shared 必须使用 `singleton: true` 和 `generate: false`。示例中的局部 `as any` 只用于绕过当前 Federation 插件缺少 `singleton` 字段的 TypeScript 声明，不会改变生成配置。插件不能打包自己的第二份 Vue/Naive UI/Lucide。宿主返回的 Federation descriptor 会明确列出 `shared: ["vue", "naive-ui", "@lucide/vue"]`。

不要从 CDN 动态加载框架、脚本、CSS、字体或图标。构建产物必须全部进入签名包。业务数据不得在浏览器直接请求第三方站点，应通过 action 进入 process，再由 `host.call` 请求。

## 3. 组件 TypeScript 契约

远程模块 default export 必须是可渲染 Vue component。推荐 props/emit 类型：

```ts
export interface PluginRuntimeSummary {
  installation_id: number
  runtime_kind: 'process' | string
  entry?: string
  timeout_ms: number
  background_timeout_ms?: number
  max_concurrency?: number
  loaded?: boolean
  health_status: 'healthy' | 'unhealthy' | 'unknown' | 'unbound'
  health_error?: string
  process_state?: string
  pid?: number
  started_at?: string
  exited_at?: string
  exit_code?: number
  restart_count?: number
}

export interface RuntimeStateResponse {
  state_version?: string
  state?: Record<string, unknown>
  not_modified?: boolean
  etag?: string
}

export interface RuntimeCallbackResponse {
  invocation_id?: string
  replayed?: boolean
  result?: {
    status: 'succeeded' | 'failed' | 'accepted' | 'skipped'
    [key: string]: unknown
  }
}

export interface PluginHostBridge {
  getState(view?: string): Promise<RuntimeStateResponse>
  invokeAction(action: string, input?: unknown): Promise<RuntimeCallbackResponse>
  refresh(): Promise<Record<string, unknown>>
}

export interface PluginPageProps {
  api: PluginHostBridge
  hostApi: PluginHostBridge
  installationId: number
  pluginId: string
  runtime: PluginRuntimeSummary | null
  runtimeState: Record<string, unknown>
  navKey: 'main' | string
  themeContract: 'dian115-theme-v1'
}

const props = defineProps<PluginPageProps>()
const emit = defineEmits<{
  action: []
  refresh: []
  close: []
}>()
```

运行时同时用 camelCase 和 Vue kebab-case 传递名称，因此 `<script setup>` 的 `runtimeState`、`themeContract` 和 `hostApi` 可正常接收。`api` 与 `hostApi` 是同一个冻结对象，提供兼容命名但不扩大权限。

### 3.1 `getState(view)`

直接请求指定 view 的 runtime state，并返回完整 `{state_version,state,etag}`。`view` 默认 `main`。页面自行调用时当前 bridge 不携带缓存 ETag；宿主页面的主状态轮询会使用 ETag。

### 3.2 `invokeAction(action, input)`

调用 process 的 action。宿主生成 `inv_...` invocation ID，并附加当前浏览器 locale 和 IANA timezone。返回 wrapper：

```json
{
  "invocation_id": "inv_...",
  "replayed": false,
  "result": {
    "status": "succeeded",
    "message": "done"
  }
}
```

页面必须处理 promise rejection，以及 result 的四种业务状态。完成后调用 `api.refresh()` 或 emit `refresh` 获取新 state。

### 3.3 `refresh()`

强制宿主重新加载 `main` state，随后返回 state object（不是包含 ETag 的完整 envelope）。成功加载的新 state 也通过 prop 更新传入组件。

### 3.4 emits

- `refresh`：让宿主刷新主状态；
- `action`：当前同样只触发刷新，不携带 action 名；调用业务 action 必须使用 `api.invokeAction`；
- `close`：离开当前插件页面。

## 4. iframe 安全模型

页面加载在：

```html
<iframe sandbox="allow-scripts">
```

没有 `allow-same-origin`。因此页面：

- 不能访问管理后台 DOM、Vue app、Pinia、router 或 Axios；
- 不能读取宿主 Cookie、localStorage、sessionStorage 或 IndexedDB；
- 不能直接请求带管理员身份的 DIAN115 API；
- 不能依赖固定 iframe origin；
- 不能导航父页面或弹出未授权窗口；
- 只能通过带随机 channel token 的 `postMessage` bridge 执行 `getState`、`invokeAction`、`refresh`、`close`。

宿主只接受来自当前 iframe window、正确 source 标识和随机 channel 的消息。bridge 每次调用 30 秒超时。iframe 高度由 sandbox 根据内容 ResizeObserver 自动上报，限制在 320-100000 px。

宿主为 sandbox 建立 Naive UI provider 栈：`NConfigProvider`、`NMessageProvider`、`NNotificationProvider`、`NDialogProvider`。远程组件可正常使用 `useMessage`、`useNotification` 和 `useDialog`。

## 5. `dian115-theme-v1`

宿主在 iframe 根元素声明所有 `--dian-*` 变量，并在主题切换时原地更新。插件不得覆盖 `:root` 或依赖 Naive UI 内部 `--n-*` 变量。可以在局部组件内派生自己的变量。

### 5.1 模式、背景和表面

| 变量 | 用途 |
| --- | --- |
| `--dian-color-scheme` | `light` 或 `dark` |
| `--dian-background` | 页面背景 |
| `--dian-surface` | 基础表面 |
| `--dian-surface-raised` | 模态/提升表面 |
| `--dian-surface-soft` | 弱对比表面 |
| `--dian-surface-hover` | hover 表面 |

### 5.2 文字和边界

| 变量 | 用途 |
| --- | --- |
| `--dian-text-primary` | 主文字 |
| `--dian-text-secondary` | 次文字 |
| `--dian-text-muted` | 辅助/占位文字 |
| `--dian-text-inverse` | 反色文字 |
| `--dian-border` | 常规边框 |
| `--dian-border-strong` | 强边框 |
| `--dian-divider` | 分隔线 |

### 5.3 主色和状态

| 变量 | 用途 |
| --- | --- |
| `--dian-primary` | 主操作 |
| `--dian-primary-hover` | 主操作 hover |
| `--dian-primary-pressed` | 主操作 pressed |
| `--dian-primary-contrast` | 主色上的文字/图标 |
| `--dian-focus-ring` | 键盘焦点环 |
| `--dian-success` | 成功 |
| `--dian-warning` | 警告 |
| `--dian-error` | 错误 |
| `--dian-info` | 信息 |

### 5.4 阴影、圆角、间距和字体

| 变量 | 用途 |
| --- | --- |
| `--dian-shadow-sm` | 小阴影 |
| `--dian-shadow-md` | 中阴影 |
| `--dian-shadow-lg` | 大阴影 |
| `--dian-radius-sm` | 8 px 基础小圆角 |
| `--dian-radius-md` | 12 px 基础中圆角 |
| `--dian-radius-lg` | 卡片圆角 |
| `--dian-radius-panel` | 大面板圆角 |
| `--dian-radius-pill` | 胶囊/圆形 |
| `--dian-space-1` | 4 px |
| `--dian-space-2` | 8 px |
| `--dian-space-3` | 12 px |
| `--dian-space-4` | 16 px |
| `--dian-space-5` | 20 px |
| `--dian-space-6` | 24 px |
| `--dian-font-family` | 宿主正文字体 |
| `--dian-font-mono` | 宿主等宽字体 |

宿主会把主题色、边框、阴影、圆角和字体的解析值同步到 iframe。间距变量属于 v1 固定尺寸。Naive UI 的 common theme 同步主色、状态色、body/card/modal、边框、文字和字体，并根据 `--dian-color-scheme` 切换 `darkTheme`。

## 6. 基础样式

sandbox 已提供两个稳定 class：

```css
.dian-plugin-page {
  min-width: 0;
  color: var(--dian-text-primary);
  font-family: var(--dian-font-family);
}

.dian-plugin-card {
  border: 1px solid var(--dian-border);
  border-radius: var(--dian-radius-lg);
  background: var(--dian-surface-raised);
  box-shadow: var(--dian-shadow-sm);
}
```

推荐页面根节点使用 `dian-plugin-page`。不要在卡片内再嵌套装饰卡片；用 full-width section、grid、tabs、data table、list 或 form 组织工作流。

响应式布局示例：

```css
.plugin-grid {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(260px, 1fr);
  gap: var(--dian-space-4);
}

@media (max-width: 760px) {
  .plugin-grid { grid-template-columns: minmax(0, 1fr); }
}
```

不要用 viewport 宽度缩放字体。为工具栏、图标按钮、表格列、计数器等固定格式元素声明稳定尺寸，确保 loading、hover、长文本和移动端不会导致跳动或重叠。

## 7. 控件与图标

- 使用 Naive UI 的 button、input、select、tabs、table、dialog、drawer、switch、checkbox、slider、progress 和状态组件；
- 使用 `@lucide/vue` 提供的图标，不手绘通用 SVG；
- 图标工具按钮提供 tooltip 和 `aria-label`；
- 颜色选项使用 swatch，模式使用 segmented/tabs，布尔值使用 switch/checkbox；
- 危险写操作使用明确确认对话框；
- 页面必须实现 loading、empty、error、disabled、success 和 retry 状态；
- 用户可重复执行的常用流程应保持少步骤，并在 action 结束后刷新 state。

## 8. 最小组件

```vue
<script setup lang="ts">
import { ref } from 'vue'
import { NButton, NIcon, NSpin, useMessage } from 'naive-ui'
import { RefreshCw } from '@lucide/vue'

const props = defineProps<{
  api: {
    invokeAction(action: string, input?: unknown): Promise<any>
    refresh(): Promise<Record<string, unknown>>
  }
  runtimeState?: Record<string, unknown>
  themeContract?: string
}>()

const message = useMessage()
const busy = ref(false)

async function refreshNow() {
  busy.value = true
  try {
    const response = await props.api.invokeAction('refresh', {})
    if (response.result?.status === 'failed') throw new Error(response.result.message || '刷新失败')
    await props.api.refresh()
    message.success('已刷新')
  } catch (error: any) {
    message.error(String(error?.message || '刷新失败'))
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="dian-plugin-page page">
    <section class="toolbar">
      <h2>插件工作台</h2>
      <NButton type="primary" :loading="busy" @click="refreshNow">
        <template #icon><NIcon :component="RefreshCw" /></template>
        刷新
      </NButton>
    </section>
    <NSpin :show="busy">
      <pre>{{ JSON.stringify(runtimeState || {}, null, 2) }}</pre>
    </NSpin>
  </main>
</template>

<style scoped>
.page { display: grid; gap: var(--dian-space-4); }
.toolbar { display: flex; align-items: center; justify-content: space-between; gap: var(--dian-space-3); }
h2 { margin: 0; color: var(--dian-text-primary); }
pre { overflow: auto; color: var(--dian-text-secondary); font-family: var(--dian-font-mono); }
</style>
```

完整构建和运行时交互见 [`examples/complete-plugin`](examples/complete-plugin/README.md)。
