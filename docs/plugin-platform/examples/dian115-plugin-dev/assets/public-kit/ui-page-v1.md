# DIAN115 独立插件页面 v1

插件提供完整 HTML 页面及静态资源。宿主直接导航 iframe 到签名入口，不导入 Vue 组件、不共享框架实例、不负责挂载组件、不监测内容高度，也不监听页面全局异常来替换界面。页面可以使用普通 HTML/JavaScript，示例使用 Vue 3 和 Naive UI，并自行创建 Provider。

## Manifest 与构建

```json
{
  "ui": {
    "mode": "page",
    "entry": "frontend/dist/index.html",
    "assets_root": "frontend/dist",
    "icon": "frontend/icon.svg"
  }
}
```

`entry` 是 `assets_root/` 内的 `.html` 文件。入口、所有静态资源和可选图标均须打入 `.d115p` 并由完整性清单覆盖。UI 是必需项。没有其他 UI 模式或旧格式回退。

Vite 项目设置 `base: './'`，保证 HTML、脚本、CSS、图片和字体相对当前签名资源目录加载；不能把 `/assets/...` 当成插件资源地址。示例的 `src/main.ts` 同时是正式入口和开发入口，只有 `import.meta.env.DEV` 的独立窗口分支启用内存 mock，正式构建不包含 mock。

```ts
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
export default defineConfig({
  base: './',
  plugins: [vue()],
  build: { target: 'esnext', outDir: 'build/frontend/dist' },
})
```

插件自行打包所需依赖，按实际使用选择组件，避免引入整套未用功能。推荐把必需资源随包提供，避免首次打开依赖外部 CDN。宿主资源入口以安装 ID、包摘要和签名能力绑定；入口 HTML 不缓存，静态资源按包摘要缓存。停用或卸载后，服务端不再提供该安装的可执行页面资源。

## SDK 连接与页面生命周期

公开实现是 [page.ts](examples/sdk/page.ts)，类型见 [ui.ts](examples/sdk/ui.ts)。SDK 没有框架依赖。

```ts
import { connectPluginPage } from '../../sdk/page'
const connection = await connectPluginPage()
const { api } = connection
const initial = connection.context
const unsubscribe = connection.subscribe(context => {
  // 更新自己的组件状态；不要在每次状态变化时重建应用。
  console.log(context.installationId, context.runtimeState)
})
```

HTML 入口的 URL fragment 由宿主填写随机通道，SDK 向当前父窗口发送 ready，收到匹配来源与通道的 init 后完成连接。连接只接受当前父窗口消息，不接收其他插件或过期通道的返回。初始化默认 30 秒，`connectPluginPage({timeoutMS})` 可在 100–60000 毫秒内调整；失败会移除监听器。

context 包含 installationId、pluginId、runtime、runtimeState、navKey（main）和 themeContract（dian115-theme-v1）。subscribe 立即交付当前 context，之后交付状态和主题变化；它不创建新的 Vue 应用。返回的 unsubscribe 可结束单个订阅，dispose 结束整个连接并拒绝尚未完成的请求。

SDK 不轮询，不注册 ResizeObserver，不监听 error/unhandledrejection，不接管渲染器。页面作者自行挂载应用、处理组件错误、布局与滚动。回退缓存恢复时 pageshow 会重新握手并更新 context，保持连接对象；真正关闭页面会清理 RPC 和监听器。后台任务独立于页面存在，重新打开后按持久 job_ref 查询。

宿主提供稳定的 iframe 视口，内容在插件文档内正常滚动；高度为 `max(480px, 100dvh - 240px)`，不会根据内容反复扩缩。页面自行提供 html/body/root 基线和必要 CSS；正式入口会加载这些 CSS，不再存在预览专用样式被正式页面遗漏的情况。

## 状态、动作、存储和后台任务

插件页面可以提供账号、密码、明文 Cookie、验证码和自定义站点地址输入框。`invokeAction` 的输入与返回数据不会因 password、cookie 等字段名被拒绝。表单使用 submit.prevent，通过 action → WASM → HTTP 提交，不能依赖 iframe 向第三方原生直投表单。CookieCloud 是可选来源，不是必需登录步骤。

敏感输入不要写入普通 `api.storage`。完整示例 `invokeSavedAction(..., undefined, { transientInput: true })` 只保存动作编号；响应不确定时重新填写原值并复用编号，由宿主哈希拒绝不同内容。宿主动作用于重放的请求和响应、HTTP Cookie 均加密保存并随卸载清空。用户名、站点地址等非秘密配置可正常持久化；插件自行决定明确的凭据展示，不能自动写入日志或整页快照。

```ts
const response = await api.getState('main')
const result = await api.invokeAction('save', { name: 'demo' }, 'inv_save_business_1')
await api.storage.set('display-settings', { schema_version: 1, compact: true })
const settings = await api.storage.get('display-settings')
const job = await api.jobs.start('refresh', 'inv_refresh_business_1')
const latest = await api.jobs.get(job.job_ref)
await api.jobs.cancel(job.job_ref)
await api.jobs.resume(job.job_ref)
await api.refresh()
```

getState 返回完整状态封套（state、state_version、etag/not_modified）；invokeAction 返回 invocation_id、replayed 和 result。refresh 返回刷新后的状态对象。持久 ID 必须在副作用前保存，同一次业务重试复用原编号和相同输入；刷新失败不能据此重做已经成功的业务。任务恢复先核对上游事实。

页面偏好使用受管 api.storage，业务数据使用 Host Storage。前者 get 返回值或 null，set/remove/clear 成功表示宿主已经提交；读取失败不能覆盖成空值。升级、停用和休眠保留数据，卸载清空该安装全部持久数据，重装为空。详情见 [隔离与生命周期](ui-isolation-v1.md)。

所有桥接值必须可经 JSON 往返，单条消息最多 1 MiB，同时最多 32 个未完成请求。这些边界只限制主项目接口通道，不限制组件渲染。state/action/refresh 超时依据前台预算、启动预算和 70 秒排队及传输余量，最大 250 秒；其他 RPC 为 30 秒。超时不等于外部业务已撤销。

## 页面错误与诊断

普通浏览器通知和未捕获事件留在浏览器控制台；宿主不会因为 `Script error.`、布局通知或单次异步异常而销毁页面。页面自行展示局部错误和重试。

作者明确需要记录真实故障时调用：

```ts
const diagnosticId = await api.reportError('ui_resource', error, 'warning')
```

stage 为 ui_load（页面加载）、ui_render（组件渲染）、ui_async（页面脚本）、ui_resource（静态资源），severity 为 warning/error，默认 error。此调用不改变页面生命周期。可在自己的 Vue errorHandler 中上报渲染错误；业务请求失败首先处理其业务结果，不把所有失败再重复记录为页面错误。

上报会脱敏凭据和完整资源 URL，只保留安全的资源文件名，每条最多 3000 字节；每安装每分钟最多 10 条。宿主诊断显示发生时间、级别和重复次数，UI 记录提供页面排查建议，只有业务诊断才提示原业务编号重试。记录是历史事实，不表示当前仍在失败。

## 权限边界

页面仍处于不透明来源的 iframe 中；HTML 响应本身带 sandbox 策略，直接打开签名入口也不会取得管理页面权限。原生 localStorage、sessionStorage、IndexedDB、Cookie、Cache API、Service Worker 和父页面 DOM 不可访问。持久偏好使用受管存储，确保按安装隔离和卸载清空。

页面的普通脚本、样式、图片、字体、媒体和 Blob Worker 可以运行；宿主不共享 Vue 实例，也不注入组件 Provider。直接 fetch/XHR/WebSocket 仍不授予权限，网络和主项目操作通过 action → WASM → Host Call，避免借用管理员身份绕过插件授权。子 frame、object、表单直投和顶层导航不开放。弹窗仍受用户手势和继承沙箱约束，外部授权应提供复制 URL/手工回填 code 的备用流程。

## 主题变量 `dian115-theme-v1`

宿主在 iframe 根元素声明所有 `--dian-*` 变量，并在主题切换时原地更新。插件不要覆盖宿主提供的 `:root --dian-*` 值，也不要依赖 Naive UI 内部 `--n-*` 变量；可以在局部组件内派生自己的变量。

### 主题变量1 模式、背景和表面

| 变量 | 用途 |
| --- | --- |
| `--dian-color-scheme` | `light` 或 `dark` |
| `--dian-background` | 页面背景 |
| `--dian-surface` | 基础表面 |
| `--dian-surface-raised` | 模态/提升表面 |
| `--dian-surface-soft` | 弱对比表面 |
| `--dian-surface-hover` | hover 表面 |

### 主题变量2 文字和边界

| 变量 | 用途 |
| --- | --- |
| `--dian-text-primary` | 主文字 |
| `--dian-text-secondary` | 次文字 |
| `--dian-text-muted` | 辅助/占位文字 |
| `--dian-text-inverse` | 反色文字 |
| `--dian-border` | 常规边框 |
| `--dian-border-strong` | 强边框 |
| `--dian-divider` | 分隔线 |

### 主题变量3 主色和状态

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

### 主题变量4 阴影、圆角、间距和字体

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


SDK 把宿主解析后的 `--dian-*` 变量写入文档根元素，并在主题变化时原地更新。页面自己的 Naive UI Provider 根据变量更新配色，完整示例已演示深浅色切换。不要依赖宿主私有 CSS、内部组件或 `--n-*` 变量。

## 页面基线示例

```css
html { box-sizing: border-box; color-scheme: var(--dian-color-scheme); }
html, body, #app { width: 100%; min-width: 0; margin: 0; }
*, *::before, *::after { box-sizing: inherit; }
body { background: var(--dian-background); color: var(--dian-text-primary); }
```

按实际 iframe 宽度设计，长 ID 和路径可折行，表格局部滚动，多列在窄视口换列。不要用宿主内容高度反过来驱动自己的页面布局。
