# 页面与主题 v3

推荐 `ui.entry: "ui/page.js"`，导出 `mount(element,ctx)`。打开插件时宿主只显示插件自己的页面：页面占满内容区，并在插件区域内部滚动，宿主保留侧栏、隐藏顶栏，桌面和手机均不为插件容器添加内边距；任务记录、基础设置、服务与端口、安装报告在插件中心的“管理”里。页面里的吸顶元素（position: sticky）相对插件区域生效。宿主直接 import ESM 并挂载到页面，不套协议沙箱，不要求指定框架。返回清理函数；停止事件、定时器、订阅及框架应用，异步请求使用 ctx.signal。mount 可以返回清理函数的 Promise。

ctx 是 [SDK](examples/sdk/index.js) 客户端，并增加 signal 和 theme。页面通过 `await ctx.navigation.close()` 关闭当前页面并返回插件中心的“用户插件”标签；只卸载页面，不停用插件或取消后台任务。HTML 页面直接调用 `window.DIAN115Plugin.navigation.close()`。宿主已离开该挂载实例后，迟到的 close 调用无效。请在自己的页面中提供可见的返回入口；内边距、手机安全区（`env(safe-area-inset-*)`）与响应式布局由插件自行处理。theme.mode 是 light/dark；theme.subscribe(fn) 立即回调当前值，返回取消订阅函数。直接挂载的 DOM 继承宿主 CSS 变量：--app-bg、--app-surface、--app-text、--app-text-secondary、--app-border、--app-accent。不要覆盖宿主全局样式。

完整 HTML 可用 `ui.entry: "ui/index.html"`，在普通同源无 sandbox 的文档容器里显示，保留页面自身结构。宿主注入资源 base 与 `window.DIAN115Plugin`；主题模式与上述变量同步。脚本可直接读取该对象，也可监听 dian115:ready。页面同样有宿主权限；容器仅管理文档与挂载生命周期，不提供权限隔离。

安装代码 revision 参与资源 URL，同一版本的资源地址固定：浏览器缓存页面的 JS、样式、图片和字体（`private, max-age=31536000, immutable`，带 ETag），再次打开插件不再重新下载。更新或重装改变地址，旧缓存自然失效；失败响应不缓存，停用后再次启用能够重新加载。每次打开时入口模块带一次性参数重新执行，`mount` 总在新的入口实例中运行；入口相对引用的其他模块在同一浏览器页面内复用，模块顶层状态会保留，需要每次重置的状态请放在 `mount` 里。某个模块导入失败时，宿主自动换一次性地址重试一次。加密发行包的资源在服务端解密一次后复用，不再每个文件重新解密整个发行包。ESM、图片、样式可以用相对路径。宿主注入的客户端自动携带 X-DIAN115-Extension、X-DIAN115-Extension-Generation、X-DIAN115-Extension-Revision，绑定安装与代码版本的生命周期。停用、更新和重装后的迟到调用会明确失败；长请求保留取消信号。这些标记不是权限凭据，不限制当前用户能调用的接口；普通 HTTP 继续使用原有宿主登录。源码资源只接受有效安装资源链接，禁止目录逃逸；这与业务 API 调用权限无关。

有页面的插件把设置做在页面内，不声明清单 `settings`（仅无页面插件使用，由宿主渲染表单）；快捷入口由用户在卡片菜单或“权限与显示”中“添加到侧边栏”；宿主侧栏底部提供统一编辑入口，菜单可以跨组移动、排序，只有插件菜单可以改名、换图标或移除。配置保存在服务器，旧侧栏收藏自动沿用；`menu` 只提供默认标题与排序；`icon` 显示在插件中心卡片与页面标题。页面 SDK 另有 files.downloadURL/upload、server.list/listen/close/hookURL/publicHookURL、settings.get/set、events.catalog。

保持明暗两种主题可读、表单有标签、异步请求显示状态和原始业务错误。不要将 ResizeObserver 提示或浏览器通用 Script error 自动包装成业务失败，更不要在未知业务结果时建议盲目重复转存。

加密交付必须把页面及其静态依赖放在独立公共目录（例如 ui/），后台入口与原始工程源码放在该目录之外。静态资源接口只解密返回该公共目录中的文件；后台代码通过宿主运行时读取。页面仍可按正常浏览器规则使用网络和宿主 API。

完整 HTML 通过 srcdoc 预先注入上下文，document.baseURI 指向真实资源目录；document.location 为 about:srcdoc。需要页面内路由时使用 hash/memory，或配置适合嵌入目录的路由 base，不把 document.location 当作宿主接口地址。
