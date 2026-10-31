# HTTP、登录和 Cookie v3

插件可以提供账号、明文密码、CK 和自定义站点输入。协议不按字段名称拒绝凭据。用插件 storage 保存配置，页面只按用户交互填写；不要把密码写进日志、公开报告或插件包默认值。

```js
await ctx.storage.set('site',{url:'https://user.example',username:'user',password:'...'} )
await ctx.http.cookies({url:'https://user.example',cookie:'session=...; another=...'})
const page=await ctx.http.request({url:'https://user.example/account',timeout_seconds:180,session:'default'})
```

http.request 返回 status、最终 url、headers（值为字符串数组）、body 文本、cached。文本按 Content-Type 或页面 meta 自动把 GBK/Big5 等转成 UTF-8，`charset` 可强制指定。

请求体五选一：`body`（字符串）、`body_base64`（二进制，可直接传 Uint8Array）、`body_file`（插件自有路径，流式上传）、`form`（对象，自动 urlencoded）、`json`（自动序列化）、`multipart`（`{fields,files:[{field,filename,path|base64|text,content_type}，path 为插件自有路径]}`，文件流式发送）。`response_type:'base64'` 返回 body_base64，`'json'` 额外返回解析后的 data。`save_to:'downloads/a.torrent'`（插件自有相对路径）把 2xx 响应流式写盘并返回 `{path,size,sha256}`，不受默认 64 MiB 限制（设置 max_bytes 才限制）；要放到宿主目录或 CD2 时再调用 files move，由宿主执行并显示进度，非 2xx 不写文件而返回错误正文。`follow_redirects:false` 返回原始 3xx，`max_redirects` 默认 10。全局 `fetch` 是同一能力的标准写法。默认 GET、120 秒、64 MiB 单次响应；timeout_seconds 可设 1–86400，0 使用默认。不写盘的响应 max_bytes 最多 256 MiB（进入宿主共享内存）；更大的内容必须用 save_to。POST body 为字符串，表单用 application/x-www-form-urlencoded，JSON 自行 stringify 并设置 headers。HTTP 错误状态作为 status 返回；连接和超时抛错。请求不自动重发变更动作。默认复用宿主网络代理选择；proxy 可填写代理 URL 或 direct 直连。

自动处理重定向各跳 Set-Cookie；插件内不同 session 独立记忆登录态，Cookie 属性及会话 Cookie 在重启后保留。未指定 User-Agent 时使用此前渲染取得的 UA。明文 Cookie 头只包含 name/value，不能表达原始 Path/HttpOnly/Secure 等属性；CookieCloud 导入使用 importCookies 保留属性。

```js
const snapshot=await ctx.cookiecloud('read',{domains:['user.example']})
await ctx.http.importCookies({session:'default',cookies:snapshot.cookies})
const cookies=await ctx.http.cookies({url:'https://user.example'})
await ctx.cookiecloud('write',{domains:['user.example'],cookies,revision:snapshot.revision})
```

CookieCloud 使用宿主已经配置并启用的本地服务。115 相关域名（115.com、115cdn.com、115cdn.net、115vod.com、anxia.com 及其子域）的 Cookie 不能读取或写入：显式请求会报错，较宽的域名（如 com）返回和导出时也会跳过它们。read 未选择域名只返回摘要；write 需要明确 domains 和最新 revision，避免覆盖其他客户端更新。导出只替换所选域，保留其他域、LocalStorage 和未知顶层字段。importCookies 的 replace=true 清空当前插件 session 后再导入；不会清空共享 CookieCloud。

每个插件 session 最多记忆 4096 条 Cookie。可选 cache_seconds（0–31536000 秒）只缓存显式请求的 GET 200；带 Set-Cookie 或 Cache-Control:no-store 不缓存。缓存按插件、URL、调用者请求头和 Cookie 区分，默认不缓存。缓存加密存放于插件 SQLite，最多 128 MiB，按到期时间淘汰；此容量不占用 KV 配额。缓存可能包含私密页面，使用适合业务的短 TTL。超时不再沿用普通管理接口的十秒上限。

需要 JavaScript 挑战页面时复用宿主已有服务；省略 endpoint 由宿主内部读取 FlareSolverr 地址，不向插件开放系统设置：

```js
const page=await ctx.http.render({url:'https://user.example',timeout_seconds:180})
```

宿主不内置 Chromium。渲染等待 wait_seconds 可设 0–86400，整体仍受本次 timeout_seconds、任务截止时间及清理预算约束；共用 FlareSolverr 客户端单次 JSON 响应最多 16 MiB。FlareSolverr 每次使用独立临时会话并尝试销毁，结果 Cookie 回存插件 session；只用于页面请求，不提供完整自动化浏览器。HTTPStatusVerified=false 表示其合成的成功状态不能证明站点业务成功。支持正常的 HTTP/HTTPS 跨站重定向，返回最终文档与该文档的 Cookie。初始请求只注入匹配目标站点的 Cookie；需要跨站登录时应明确对登录站点完成登录，不能把临时渲染会话当作完整持久浏览器。会话回写处理 Cookie 删除，并保留并行 HTTP 操作已经更新的值。

GET `/api/extensions/v3/{id}/network-capabilities` 仅返回 `default_render_endpoint` 与 `render_configured` 布尔值，供插件识别默认渲染能力与配置状态，不返回地址或凭据。旧宿主没有此接口时返回 404，可保留用户已有的显式 endpoint 配置；新的显式 endpoint 仍优先于宿主默认。浏览器等待后的文档直接返回，补采 Cookie 的第二次导航不会覆盖该文档；同名同路径 Cookie 优先采用浏览器新生成的精确域 Cookie。

这些新增渲染行为需要安装包含相应实现的宿主；仅声明 `requires.api=3.5` 不能代替能力探测。`network-capabilities` 的 404 才表示旧宿主；401、网络故障或其他错误不能被当作“未配置”。插件不得读取 `/api/settings` 来发现服务地址，也不提供浏览器表单点击、任意页面脚本执行或 `ready_selector` 参数。

## 登录与自动验证

复用同一 `session` 完成挑战获取、协议提交、账号登录和后续查询。浏览器与普通 HTTP 的传输特征可能不同，浏览器验证成功不保证该 Cookie 在 HTTP 中也有效；可直接消费已经取得的渲染结果，资源 JSON 则继续核对站点业务码和字段。Cookie 数量、HTTP 200、渲染成功或公共页的用户摘要均不能单独证明登录：应重新请求受保护账号页，核验真实登录入口或已识别的账号数据；重定向至登录页是未登录。

对站点有公开、已确认的机器验证协议时，插件可以自行用 HTTP、`ctx.crypto`、`ctx.codec` 和受限计算实现，无需内置浏览器。限制参数长度、迭代次数、计算时间和响应大小；计算分批让出运行时以支持取消。同会话验证应使用带到期时间的独占记录，保存所属 run ID，以便确认旧任务已结束后回收；取消和异常也应释放。不要执行任意远端脚本，也不要将某个站点的协议硬编码为通用宿主行为。

只有站点协议明确证明原操作在处理前被拒绝，才考虑有限重试。例如某站点的 `code=419, refresh=1` 明确表示需要更新机器验证，可验证后最多重试一次；这不是通用 HTTP 419 语义。密码错误、人工验证码、反复验证、超时和响应丢失分别处理，后两者不能证明原提交未发生。变更动作先写检查点，恢复时先查实际结果。

导入或更新 Cookie 后可清除该会话的普通失败退避，并增加会话修订号，使旧任务的失败不覆盖新状态；服务端 429 / Retry-After 仍须保留。Cookie 的 Domain、Path、Secure、有效期和 UA 同样需要匹配，不要为修复机器验证而清空账号 Cookie。

## 避免每次查询都等待浏览器

`wait_seconds` 是页面请求后的固定等待，不是“内容就绪立即返回”。每个页面都等待 45 秒会使两页登录检查至少多等待 90 秒。先检查响应：标题为 Loading、HTML 无目标标签，不代表页面没有业务数据。部分站点已经将列表、分页、IMDb、季集和账号字段放入内联 JSON；解析已知数据字段并验证结构，可省去浏览器启动和等待。

读取这类字段时只解析已识别的 JSON 字面量，处理字符串转义与嵌套并限制大小；不要用 `eval` 执行脚本。核验条目 ID、类型、路径、列数组长度和分页范围，展示前转义。结构未知或变化时可回退浏览器；解析失败不能当作空结果，公共页摘要不能当作账号登录证明。浏览器返回 JSON 包装页时可解析 `pre` 文本，但仍要核对业务结果。

读取内联脚本数据用 `ctx.html.load(html).find('script:not([src])').toArray()` 后的 `node.text()`。宿主的 `node.html()` 会序列化并转义引号等字符，例如 `"` 变成 `&#34;`，不能直接送入 JSON.parse；也不要盲目再解实体，否则会改写 JSON 字符串中原本的 `&amp;` 等值。本地 DOM 模拟库的行为可能不同，需要在真实宿主检查此路径。

分别测量已有会话、首次验证、列表、搜索、详情和账号检查的实际耗时，并同时核对结果数量；只测缓存命中不能代表首次速度。优先消除多余请求和固定等待，保持请求间隔、取消、并发互斥和服务端退避。确有需要时再加短期缓存：按站点、会话修订和完整查询隔离，提供强制刷新并显示原获取时间，不能因读取缓存而刷新资源发现时间或推进订阅基线。
