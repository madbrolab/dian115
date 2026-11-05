# 宿主共享浏览器（API 3.10；代理配置需 3.11）

DIAN115 管理一份 Chromium 运行包，供主程序功能和第三方插件共同调用。运行包不进入主程序 payload 或 Docker 镜像：使用 `madbrolab/dian115-browser-runtime` 的固定版本清单及 SHA256，版本随宿主发布更新，不能在设置或插件中修改；宿主在授权激活后的启动阶段后台下载，校验、解压并缓存到数据目录的 `browser/`。下载失败不阻止主程序启动；升级失败保留已安装版本。缺少当前架构或尚未安装完成时，不能打开浏览器。

浏览器在 **DIAN115 的 Linux 后端**运行，APK 和浏览器前端均通过宿主接口调用，无需给 APK 或页面再装一份内核。当前使用无界面的 Chromium headless shell，支持网页渲染、页面脚本、输入、截图和网络观察；不是可远程观看的桌面 Chrome，也不承诺任意网站验证一定通过。

## 如何选择 Chromium 与 FlareSolverr

建议按页面需求选择，APK、浏览器前端和后台任务采用同一原则：

| 需求 | 建议接口 |
| --- | --- |
| 普通接口或静态页面，不需要执行 JavaScript | `ctx.http.request`，无需启动浏览器 |
| 无站点挑战，需要 JavaScript 渲染、DOM、点击、输入、截图或网络事件 | `ctx.browser`，使用宿主共享 Chromium（Chrome 内核） |
| 已确认遇到 Cloudflare 等站点挑战，需要尝试自动验证并取得页面 | 优先 `ctx.http.render`，复用已配置的 FlareSolverr，见[网络能力](network.md) |

这是选用建议，宿主不会自动识别挑战或在两套接口间切换。不能把所有 403、超时或空页面都当成挑战；应结合 `cf-mitigated: challenge`、页面特征及目标业务内容判断。FlareSolverr 也可能验证失败或需要人工处理，未触发挑战的 HTTP 200 不算过盾成功。

`ctx.http.render` 是一次页面请求，不提供完整的 DOM、点击和截图控制；需要这些操作时仍使用 `ctx.browser`。两者的浏览器进程、Cookie、登录档案和代理配置不会自动共享，FlareSolverr 验证成功也不能直接认定 Chromium 会话或普通 HTTP 会话已经通过验证。

## 授权与能力探测

```json
{"requires":{"api":"3.10"},"permissions":["browser"]}
```

声明后还需要用户在插件中心开启“浏览器控制”。`status` 可在授权前探测，其他操作每次都校验授权。撤销授权、停用、更新和卸载会关闭相应会话；卸载还删除该安装的所有浏览器登录档案。更新保留同一安装的档案，重新安装与其他插件隔离。

页面和后台均提供 `ctx.browser`：

| 方法 | 参数 | 返回 |
| --- | --- | --- |
| `status()` | 无 | `{state,available,configured,sandbox:false,architecture,version?,downloaded_bytes,total_bytes,active_sessions,error?}` |
| `open(options?)` | `{profile?:'default',proxy_mode?:'system',proxy_url?,timeout_seconds?:30}` | `{id,profile,proxy_mode}` |
| `command(options)` | `{session,method,params?:{},timeout_seconds?:30}` | 原始页面 CDP result 对象 |
| `events(options)` | `{session,after?:0,limit?:100,wait_ms?:0,timeout_seconds?:30}` | `{events:[{sequence,method,params,truncated?}],next_cursor,lost}` |
| `close(session)` | `open` 返回的 id 字符串 | `{ok:true}` |

普通 HTTP 对应 `POST /api/extensions/v3/{id}/browser`，JSON 为上述参数加 `operation:'status'|'open'|'command'|'events'|'close'`；close 使用 `{operation:'close',session:id}`。调用方由安装身份绑定，不能传入或切换 owner。旧宿主返回 404 或没有 `ctx.browser`；401、403、网络错误不能视为未配置。运行包未就绪返回 503，会话不存在或属于其他调用方返回 410。

`state` 为 `unconfigured`、`missing`、`downloading`、`extracting`、`ready`、`failed`。升级失败时 `available` 仍可能为 true，表示上一个已安装版本可用。不要仅按 state 推断是否能打开浏览器。

## 页面操作示例

后台不需要 Node、Playwright 或额外容器。页面的 ctx 使用同样写法。CDP 字段名称沿用 Chromium 的 camelCase，外层宿主参数使用 snake_case。

```js
export async function run(ctx, input) {
  const status = await ctx.browser.status()
  if (!status.available) throw new Error(status.error || '请先在宿主设置中安装浏览器运行包')
  const page = await ctx.browser.open({ profile: 'account-a' })
  const command = (method, params = {}) => ctx.browser.command({ session: page.id, method, params })
  try {
    const navigation = await command('Page.navigate', { url: input.url })
    if (navigation.errorText) throw new Error(navigation.errorText)
    // Page.navigate 返回不代表页面已经加载。按业务条件等待，始终有截止时间。
    const deadline = Date.now() + 15000
    let ready = false
    while (Date.now() < deadline) {
      const r = await command('Runtime.evaluate', {
        expression: "document.readyState === 'complete' && !!document.querySelector('button')",
        returnByValue: true,
      })
      if (r.exceptionDetails) throw new Error('页面脚本执行失败')
      if (r.result?.value === true) { ready = true; break }
      await ctx.sleep(100) // 页面使用有取消处理的定时器
    }
    if (!ready) throw new Error('页面内容未按时就绪')
    const result = await command('Runtime.evaluate', {
      expression: '({title:document.title,html:document.documentElement.outerHTML})',
      returnByValue: true,
    })
    if (result.exceptionDetails) throw new Error('读取页面失败')
    return result.result.value
  } finally {
    await ctx.browser.close(page.id)
  }
}
```

`Runtime.evaluate` 的页面异常通过 `exceptionDetails` 返回，必须检查；`returnByValue:true` 才直接序列化值。可传 `awaitPromise:true` 等待页面 Promise。宿主不会自动解释页面业务结果，也不会自动重放导航、点击、提交等命令；超时或取消时关闭对应会话，原操作是否发生需要业务自行核对。

真实鼠标与输入：先用 `DOM.getBoxModel` 或页面脚本取得坐标，再调用 `Input.dispatchMouseEvent`，`type` 依次为 `mousePressed`、`mouseReleased`，包含 `x`、`y`、`button:'left'` 和 `clickCount:1`。输入框先 focus，再用 `Input.insertText({text:'中文'})`。页面 DOM 的 `.click()` 也能使用，但其事件属性与真实输入不同。

`Page.captureScreenshot({format:'png'})` 返回 `{data:'base64...'}`，默认视口 1280×800，可用 `Emulation.setDeviceMetricsOverride` 调整。截图属于浏览器当前页面，不会生成宿主截图文件。

## 网络与登录状态

页面、Runtime、DOM 和网络事件在会话打开后自动采集，无需再次发送 enable。持续读取事件：

```js
let cursor = 0
const batch = await ctx.browser.events({ session: page.id, after: cursor, wait_ms: 1000 })
if (batch.lost) throw new Error('事件已溢出，不能把本次网络记录当作完整结果')
for (const event of batch.events) {
  if (event.truncated) continue // 内容过大，不能按完整事件解析
  if (event.method === 'Network.responseReceived') {
    // 结合 loadingFinished 再获取响应正文，避免正文尚未到齐。
    const { requestId, response } = event.params
  }
}
cursor = batch.next_cursor
```

`Network.getResponseBody({requestId})` 返回 `{body,base64Encoded}`。应在匹配的 `Network.loadingFinished` 后读取，判断是否需要 base64 解码，并核验站点业务码。Chromium 的正文缓冲有上限，较早或过大的响应可能已经不可用；这不是通用的大文件下载 API。

同一调用方与同一 `profile` 的 Cookie、LocalStorage 等浏览器状态持久保存；profile 只能使用 1–64 位字母、数字、点、横线和下划线。一个 profile 同时只能打开一次。不同插件、不同安装与宿主功能的 profile 相互独立。浏览器状态与 `ctx.http` 的 session **不会自动互相同步**，也不会自动注入宿主账号、CookieCloud 或 FlareSolverr Cookie。需要时显式使用 `Network.getCookies/setCookies` 并保留属性、校验域名及业务结果。

## 代理配置（API 3.11）

使用代理参数时声明 `requires.api:"3.11"`，仍只需 `browser` 授权。宿主、APK 页面、浏览器页面与后台任务共用相同规则，代理在 Linux 后端执行。

| proxy_mode | 行为 |
| --- | --- |
| `system`（默认） | 使用宿主设置的代理与内置、自定义域名清单。命中才走代理，未命中或未配置代理时直连；不是全站代理。 |
| `direct` | 本会话所有网页请求直连，覆盖宿主代理；不继承 HTTP_PROXY、HTTPS_PROXY、ALL_PROXY 等环境变量。 |
| `custom` | 本会话所有网页请求使用 `proxy_url`，不受宿主域名清单限制；未填写或地址无效时报错。 |

```js
const system = await ctx.browser.open({ profile: 'system', proxy_mode: 'system' })
await ctx.browser.close(system.id)
const direct = await ctx.browser.open({ profile: 'direct', proxy_mode: 'direct' })
await ctx.browser.close(direct.id)
// 代理地址来自插件自己的设置；不要打印含密码的 URL。
const settings = await ctx.settings.get()
const custom = await ctx.browser.open({
  profile: 'account-a', proxy_mode: 'custom', proxy_url: settings.proxy_url,
})
try {
  await ctx.browser.command({ session: custom.id, method: 'Page.navigate', params: { url: 'https://example.com/' } })
} finally { await ctx.browser.close(custom.id) }
```

`proxy_url` 仅允许在 `open` 且 `proxy_mode=custom` 时提供；支持 `http://`、`https://`、`socks5://`（`socks5h://` 同义），默认端口分别为 80、443、1080。可写 `scheme://user:password@host:port`，账号密码中的特殊字符须百分号编码，IPv6 地址用方括号。不接受 PAC、URL 路径、查询参数或任意浏览器参数；当前 HTTP/HTTPS 代理认证为 Basic，SOCKS5 支持用户名密码并由代理解析目标域名。

系统模式按**每个请求目标**处理主文档、脚本、图片、fetch/XHR、iframe、HTTP(S) 重定向和 WebSocket；跨到另一个域名会重新匹配。内置精确主机规则保持精确，内置父域和用户添加的域名同时匹配根域及子域，不能用 `example.com.evil` 绕过匹配。清单外 CDN 会直连，需要管理员将该 CDN 加入系统清单，或由插件选择 custom。

打开时复制系统代理和域名清单，当前会话中的既有连接保持原策略；修改系统设置、插件代理或切换出口后须 close 再 open。代理配置不保存在 profile 中，返回值仅包含 proxy_mode，不返回宿主的代理地址或密码。不同会话可选择不同代理；同一 profile 仍不能同时打开。

实现使用带有会话认证的本机回环转发层。上游代理凭据留在宿主，不进入 Chromium 命令行、环境变量、页面请求头或公共 CDP 事件。HTTPS/WSS 使用 CONNECT 原样转发，目标 TLS 握手与证书验证仍由 Chromium 执行；HTTPS 上游代理的证书也正常验证。不关闭 HTTP/2、不解密目标 TLS。HTTP 与 HTTPS 代理的目标 DNS 由上游解析，清单外直连按宿主 DNS 解析。

命中代理后的连接或认证失败返回网络失败，**不回退为直连**。会话打开时会检查本机转发与 Chromium 的代理认证是否可用；这不代表远端代理一定可连，需实际导航并核验 `Page.navigate.errorText`、网络失败事件及页面业务内容。会话关闭时同时回收回环端口、隧道与连接。范围是网页 HTTP(S)/WS(S)，不承诺转发 WebRTC、UDP、扩展或宿主其他网络活动。

运行包清单与压缩包下载也使用宿主按域名分流的 HTTP 客户端，每次 HTTPS 重定向重新选路；不使用插件会话的 custom 代理。`ctx.http.request` 的 `proxy` 参数和 `ctx.http.render` 的 FlareSolverr 选路保持独立，浏览器代理配置不会替换它们。

## 允许的 CDP 命令

支持以下页面范围的命令，其字段与返回值查 [Chromium CDP](https://chromedevtools.github.io/devtools-protocol/)：

- Page：navigate、reload、stopLoading、getFrameTree、getNavigationHistory、navigateToHistoryEntry、captureScreenshot、getLayoutMetrics、setDocumentContent、addScriptToEvaluateOnNewDocument、removeScriptToEvaluateOnNewDocument、bringToFront。
- Runtime：evaluate、callFunctionOn、getProperties、releaseObject、releaseObjectGroup、awaitPromise。
- DOM：getDocument、getFlattenedDocument、querySelector、querySelectorAll、getOuterHTML、setOuterHTML、getAttributes、setAttributeValue、removeAttribute、focus、getBoxModel、getContentQuads、describeNode、resolveNode、requestNode、scrollIntoViewIfNeeded。
- Input：dispatchMouseEvent、dispatchKeyEvent、dispatchTouchEvent、insertText、synthesizeScrollGesture、synthesizeTapGesture。
- Network：getResponseBody、getRequestPostData、getCookies、setCookie、setCookies、deleteCookies、clearBrowserCookies、clearBrowserCache、setCacheDisabled、setExtraHTTPHeaders、setUserAgentOverride、setBlockedURLs。
- Emulation：setDeviceMetricsOverride、clearDeviceMetricsOverride、setTouchEmulationEnabled、setEmulatedMedia、setTimezoneOverride、setLocaleOverride、setGeolocationOverride、clearGeolocationOverride。

不开放 Target、Browser、系统文件上传、任意启动参数、调试端口、下载目录或 Fetch 拦截配置。仅允许 HTTP(S) 顶层导航；内部请求拦截拒绝非 HTTP(S) 请求；浏览器自动文件下载关闭。需要下载业务文件仍使用已有的 HTTP/files 接口。

## 生命周期、限额与运行边界

- 共用的是运行包和管理服务。不同 profile 使用独立浏览器进程，以保留各自登录档案。
- 全局最多 4 个会话，每个调用方最多 2 个；空闲 5 分钟自动关闭，可能再有最多 30 秒回收扫描延迟。正在执行的命令不会按空闲回收。
- 后台会话归当前任务所有，任务返回、取消或结束即关闭；页面应主动 close；宿主卸载页面时也会回收该页面已取得的会话。请求响应丢失或页面异常时由空闲回收兜底。
- 单次调用默认 30 秒，最大 120 秒；事件等待最多 25000 毫秒，每批最多 256 条。事件环形缓冲最多 512 条或 4 MiB，单条超过 256 KiB 标记 truncated；丢失事件时 lost=true。
- 命令参数最多 1 MiB，单条 CDP 消息最多 16 MiB。截图和响应正文占用宿主内存，避免并行获取大内容。
- **Chromium 使用 `--no-sandbox`**。接口和 profile 隔离不等于网页进程的系统隔离；浏览器漏洞仍可能影响容器内 DIAN115 的数据。继承现有 Docker 限制，不要求 privileged、SYS_ADMIN 或关闭容器 seccomp，也不关闭网页同源检查或 HTTPS 证书验证。
- 运行包支持 Linux amd64/arm64 按清单选择，当前已验证的二进制为 amd64，不能把架构选择代码视为 ARM64 实测通过。
- FlareSolverr 的 `ctx.http.render` 保持独立，仍是一次页面请求；不会自动升级成 browser，也不复用它的内部浏览器。

## 运行包来源

来源是[独立仓库 Releases](https://github.com/madbrolab/dian115-browser-runtime/releases/tag/chromium-153.0.8010.0-r1)，地址和清单 SHA256 写在宿主代码里，随宿主版本一起升级，不跟随 latest。新安装在授权激活后自动后台下载，缓存完整时不重复下载。来源没有读取或修改接口；`GET /api/browser/status` 查询状态，`POST /api/browser/install` 在失败后重试安装。

清单固定为 `schema_version:1`、`version` 与 `platforms`；平台键如 `linux-amd64`，每项包含 `url`、`sha256`、`size`，指向固定布局的 `.tar.br` 运行包。清单摘要必须匹配宿主内置的值，压缩包摘要及大小必须匹配清单。解压拒绝路径穿越、链接和特殊文件；压缩包最多 512 MiB，解压最多 1 GiB、4096 项。缓存和安装档案位于数据目录 `browser/`，不开放给插件文件接口。
