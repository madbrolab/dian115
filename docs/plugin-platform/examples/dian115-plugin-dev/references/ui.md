# 页面接入

正式页面接受公开 SDK 的 PluginPageProps，只通过 `api` 使用状态、动作、受管存储和任务。Vue 3、Naive UI、@lucide/vue 共享 singleton 且 generate:false，使用 dian115-theme-v1 变量，避免打入第二份 UI 框架。

页根保持 width/max-width:100%、min-width:0，使用实际宿主窄视口设计；侧栏打开时 900–1000px 左右应能够换列，长 ID/路径折行，表格局部滚动。展示明确的 loading、empty、error 和 retry；交互采用有标签的控件、可见焦点和移动布局。宿主已经提供 provider；预览入口才自行建立 Provider。

不透明来源 sandbox 中浏览器存储和直接 fetch 不可用；偏好用 api.storage，业务网络通过 runtime。读取偏好失败不能重置并覆盖。加载失败与业务失败分别提示，保留 diagnostic_id。用户点击才打开外部窗口；异步 OAuth 先同步打开空窗口再填入返回 URL，拦截时提供复制方式。不要降级 sandbox。

本地 `src/main.ts` 明确标识模拟预览。mock 只能模拟它实际实现的能力，对真实通知/文件/网络等返回未连接，不伪造成功；它不替代宿主 Federation 验收。正式 `AppPage.vue` 不依赖预览专用 CSS 才能布局，preview.css 只提供宿主题变量。

按实现范围验证首次挂载、存储读取失败、双击提交、动作成功后刷新失败、卸载页面、长文本和手机宽度。更多桥接类型读 public-kit/examples/sdk/ui.ts，主题和资源规则读 ui-federation-v1.md 与 ui-isolation-v1.md。
