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

需要 JavaScript 挑战页面时显式复用已有服务：

```js
const page=await ctx.http.render({endpoint:'http://192.168.2.2:8191',url:'https://user.example',timeout_seconds:180})
```

宿主不内置 Chromium。渲染等待 wait_seconds 可设 0–86400，整体仍受本次 timeout_seconds、任务截止时间及清理预算约束；共用 FlareSolverr 客户端单次 JSON 响应最多 16 MiB。FlareSolverr 每次使用独立临时会话并尝试销毁，结果 Cookie 回存插件 session；只用于页面请求，不提供完整自动化浏览器。HTTPStatusVerified=false 表示其合成的成功状态不能证明站点业务成功。支持正常的 HTTP/HTTPS 跨站重定向，返回最终文档与该文档的 Cookie。初始请求只注入匹配目标站点的 Cookie；需要跨站登录时应明确对登录站点完成登录，不能把临时渲染会话当作完整持久浏览器。会话回写处理 Cookie 删除，并保留并行 HTTP 操作已经更新的值。
