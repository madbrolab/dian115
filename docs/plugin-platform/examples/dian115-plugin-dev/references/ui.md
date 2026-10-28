# 页面接入

正式 UI 是 ui.mode=page 的完整 HTML 页面。src/main.ts 调用公开 SDK connectPluginPage，再自行建立 Vue 应用和组件 Provider；SDK 不依赖 Vue，也不接管布局、渲染或全局错误。普通依赖随页面打包，Vite base 设置为 ./，不使用宿主框架实例或组件动态导入协议。

SDK context 提供安装身份、runtime、runtimeState、navKey 和 themeContract。subscribe 立即交付 context，后续只更新状态和主题，不能每次重新 createApp。SDK 自动应用 --dian-* 变量；页面自己的 Naive UI Provider 根据变化更新配色，模板已演示。正式入口加载页面 CSS，包含自己的 html/body/root 基线。

宿主提供稳定视口，页面自行滚动。使用流式宽度、窄屏换列、路径折行和局部表格滚动；不要观察内容高度再要求宿主扩缩 iframe。状态、动作、受管存储和任务通过 api 使用，读取偏好失败不能重置覆盖。

不透明来源隔离主程序页面、管理员身份和原生浏览器持久存储。偏好用 api.storage，业务网络走 runtime/Host Call，Blob Worker 可运行。不得取消来源隔离来解决布局问题；用户手势弹窗受浏览器规则约束，外部授权提供复制链接与手工回填备用流程。

页面自己的错误处理负责局部 loading/error/retry。只有需要保留的真实故障才显式 api.reportError(stage, reason, severity)；SDK 不把 Script error 或布局通知自动上报，不销毁页面。渲染问题与业务结果不确定分别提示，业务重试保留原编号。

开发独立窗口的 mock 不代表真实接口可用。按变更验证首次打开、状态更新不重建页面、刷新、回退缓存恢复、请求失败、持久偏好隔离、卸载清空及移动布局。类型和连接实现读 public-kit/examples/sdk/ui.ts 与 page.ts，主题和资源规则读 ui-page-v1.md、ui-isolation-v1.md。
