# 页面与主题 v3

推荐 `ui.entry: "ui/page.js"`，导出 `mount(element,ctx)`。打开插件时宿主只显示插件自己的页面：页面占满内容区，并在插件区域内部滚动，宿主保留侧栏、隐藏顶栏，宿主仅预留设备安全区（普通桌面为 0），不添加业务内边距；任务记录、基础设置、服务与端口、安装报告在插件中心的“管理”里。页面里的吸顶元素（position: sticky）和挂载区域内的固定元素（position: fixed）相对插件区域生效。宿主直接 import ESM 并挂载到页面，不套协议沙箱，不要求指定框架。返回清理函数；停止事件、定时器、订阅及框架应用，异步请求使用 ctx.signal。mount 可以返回清理函数的 Promise。

插件通过宿主注入的 `ctx.navigation` 调用页面导航。ESM 页面使用 `mount(element, ctx)` 收到的 ctx，HTML 页面使用 `window.DIAN115Plugin`。

| 操作 | ESM 页面 | HTML 页面 |
| --- | --- | --- |
| 返回插件中心的“用户插件”标签 | `await ctx.navigation.close()` | `await window.DIAN115Plugin.navigation.close()` |
| 打开宿主手机侧边栏 | `await ctx.navigation.openSidebar()` | `await window.DIAN115Plugin.navigation.openSidebar()` |

请保留可见的返回入口。手机主菜单的入口由插件自行安排，可放在工具栏或“更多”菜单里。打开侧边栏时插件继续显示，重复调用保持展开。桌面布局下调用无效果。兼容旧版宿主时，可用 `typeof ctx.navigation?.openSidebar === 'function'` 判断是否显示入口。返回插件中心时宿主卸载页面，后台任务继续运行。页面卸载后，两种导航调用都失效。

## iPhone PWA 页面适配契约

本节适用于所有提供 `ui.entry` 的第三方插件，包括 ESM 模块和完整 HTML。插件可以自定视觉风格，手机页面须满足以下交互要求。

| 项目 | 页面要求 |
| --- | --- |
| 容器与安全区 | 宿主在滚动区外预留状态栏、横屏两侧和底部手势区。布局以挂载元素或 iframe 的实际宽高为准。满高使用 `height: 100%`，插件只加业务间距。根布局使用 `100vh`、`100dvh`、`window.innerHeight` 或再次累加安全区，会造成底部遮挡或双份留白。 |
| 滚动与工具栏 | 普通长页沿内容自然滚动。满高工作区将顶栏、正文和底栏放在同一布局，只有正文纵向滚动。最后一项和获得焦点的控件都须能滚到可见位置。宽表格、时间轴只在自己的区域内横向滚动。 |
| 导航与触控 | 提供清楚的返回入口，手机主菜单由插件安排。使用上面的宿主导航接口。图标按钮须有可访问名称，主要操作的触控区域至少 44 × 44 CSS 像素。弹层可以关闭，关闭后焦点回到触发控件。 |
| 软键盘与缩放 | 触屏输入框、文本域和下拉框的文字至少 16 CSS 像素。键盘打开和收起时，编辑框、提交和关闭操作要能看见或滚到。弹层和底部操作区随可用容器缩放，避免在挂载时缓存高度。保留系统双指缩放。 |
| 窄屏与横屏 | 在 320 CSS 像素宽仍能完成主要操作。表单随空间改为单列，长标题和按钮组可换行。横屏手机也要保留触控入口。导航可参考宿主移动断点：宽度不超过 768px，或高度不超过 500px 且为无悬停的粗指针设备。 |
| 主题与生命周期 | 使用宿主主题变量，响应 `ctx.theme.subscribe` 及减少动态效果偏好。后台恢复、旋转和键盘收起后仍能继续当前操作，保留表单内容。页面卸载时清理监听和订阅，用 `ctx.signal` 取消页面请求。 |
| PWA 归属 | 安装入口、manifest、Service Worker 和应用更新由宿主管理。插件内导航限定在自己的挂载区或文档中，弹层也挂在插件内；不要改宿主的 viewport、全局样式或顶层地址。 |

**满高工作区示例。** 顶栏和操作栏占据自己的行，正文占剩余高度。普通长页可以省去这个布局。ESM 把这些类放在自己的根节点下；HTML 文档还要让框架根元素继承高度，例如 `html, body, #app { height: 100%; margin: 0; }`。

```css
.my-plugin-screen {
  box-sizing: border-box;
  height: 100%;
  min-width: 0;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  color: var(--app-text);
  background: var(--app-bg);
}
.my-plugin-screen > main { min-height: 0; overflow: auto; overscroll-behavior-y: contain; }
.my-plugin-screen > :is(header, footer) { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.my-plugin-screen button { min-height: 44px; min-width: 44px; }
@media (pointer: coarse) {
  .my-plugin-screen :is(input, textarea, select) { font-size: max(16px, 1em); }
}
```

**交付前验收。** 用手机视口分别检查 Safari 浏览模式和主屏幕独立模式，覆盖竖屏、横屏及明暗主题。打开菜单再关闭，滚动到最后一项，聚焦最靠下的输入框，输入后收起键盘，再切到后台并恢复。检查工具栏在安全区内、整页没有横向溢出、输入值仍在、弹层操作可达。仅通过构建无法验证这些行为。

HTML 插件在 iframe 内只能量到自己文档的视口。宿主使用顶层页面的可视高度调整挂载区，插件应让布局跟随容器。参见 [MDN 的 VisualViewport 说明](https://developer.mozilla.org/en-US/docs/Web/API/VisualViewport)和 [WebKit 的 iPhone 安全区说明](https://webkit.org/blog/7929/designing-websites-for-iphone-x/)。

ctx 是页面 SDK 客户端，并增加 signal 和 theme。theme.mode 是 light/dark；theme.subscribe(fn) 立即回调当前值，返回取消订阅函数。ESM 继承宿主 CSS 变量，HTML 由宿主同步 `--app-bg`、`--app-surface`、`--app-text`、`--app-text-secondary`、`--app-border`、`--app-accent`。

完整 HTML 可用 `ui.entry: "ui/index.html"`，在普通同源无 sandbox 的文档容器里显示，保留页面自身结构。宿主注入资源 base 与 `window.DIAN115Plugin`；主题模式与上述变量同步。脚本可直接读取该对象，也可监听 dian115:ready。页面同样有宿主权限；容器仅管理文档与挂载生命周期，不提供权限隔离。

安装代码 revision 参与资源 URL，同一版本的资源地址固定：浏览器缓存页面的 JS、样式、图片和字体（`private, max-age=31536000, immutable`，带 ETag），再次打开插件不再重新下载。更新或重装改变地址，旧缓存自然失效；失败响应不缓存，停用后再次启用能够重新加载。每次打开时入口模块带一次性参数重新执行，`mount` 总在新的入口实例中运行；入口相对引用的其他模块在同一浏览器页面内复用，模块顶层状态会保留，需要每次重置的状态请放在 `mount` 里。某个模块导入失败时，宿主自动换一次性地址重试一次。加密发行包的资源在服务端解密一次后复用，不再每个文件重新解密整个发行包。ESM、图片、样式可以用相对路径。宿主注入的客户端自动携带 X-DIAN115-Extension、X-DIAN115-Extension-Generation、X-DIAN115-Extension-Revision，绑定安装与代码版本的生命周期。停用、更新和重装后的迟到调用会明确失败；长请求保留取消信号。这些标记不是权限凭据，不限制当前用户能调用的接口；普通 HTTP 继续使用原有宿主登录。源码资源只接受有效安装资源链接，禁止目录逃逸；这与业务 API 调用权限无关。

有页面的插件把设置做在页面内，不声明清单 `settings`（仅无页面插件使用，由宿主渲染表单）；快捷入口由用户在卡片菜单或“权限与显示”中“添加到侧边栏”；宿主侧栏底部提供统一编辑入口，菜单可以跨组移动、排序，只有插件菜单可以改名、换图标或移除。配置保存在服务器，旧侧栏收藏自动沿用；`menu` 只提供默认标题与排序；`icon` 显示在插件中心卡片与页面标题。页面 SDK 另有 files.downloadURL/upload、server.list/listen/close/hookURL/publicHookURL、settings.get/set、events.catalog。

保持明暗两种主题可读、表单有标签、异步请求显示状态和原始业务错误。不要将 ResizeObserver 提示或浏览器通用 Script error 自动包装成业务失败，更不要在未知业务结果时建议盲目重复转存。

加密交付必须把页面及其静态依赖放在独立公共目录（例如 ui/），后台入口与原始工程源码放在该目录之外。静态资源接口只解密返回该公共目录中的文件；后台代码通过宿主运行时读取。页面仍可按正常浏览器规则使用网络和宿主 API。

完整 HTML 通过 srcdoc 预先注入上下文，document.baseURI 指向真实资源目录；document.location 为 about:srcdoc。需要页面内路由时使用 hash/memory，或配置适合嵌入目录的路由 base，不把 document.location 当作宿主接口地址。
