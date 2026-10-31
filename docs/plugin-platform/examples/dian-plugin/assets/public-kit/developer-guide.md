# 开发指南 v3

## 最小目录

```text
plugin.json
ui/page.js
jobs/job.js
```

```json
{"schema_version":3,"id":"example.transfer","name":"资源转存","version":"1.0.0","ui":{"entry":"ui/page.js"},"jobs":[{"id":"transfer","entry":"jobs/job.js","handler":"run","recover":"recover","timeout_seconds":1800}],"declared_usage":{"apis":["POST /api/115/share/receive"],"sites":["用户自定义地址"],"files":[],"risk":"创建115文件并发送通知"}}
```

UI 和 jobs 至少提供一项。ID 使用小写字母、数字、点和连字符。代码通过相对 ESM 导入共享模块；后台只加载安装快照内的 JS，不提供 Node 的 require、进程启动或 npm 内置模块。浏览器页面可使用自己的框架与构建产物。

## 普通宿主 API

页面 `ctx.api.post('/api/115/share/receive', payload)` 与普通页面请求使用同一路由、登录和业务校验。后台也使用 `ctx.api`，宿主在进程内调用同一组 HTTP handler，不执行端点授权清单或协议嵌套。

SDK 只是便捷函数，不是强制协议。浏览器也可直接 fetch；在跨域部署或 APP 中，优先使用传入的客户端处理服务器地址和登录。`api.get/post/put/patch/delete/head` 返回原接口 JSON；非成功状态抛错。后台 API 错误含 status/method/path/data，message 展示路由、状态及服务端错误；页面客户端沿用普通 Axios 错误结构。GET 查询参数放在 URL 中。上传、大文件下载和流式接口使用页面原生 HTTP 或宿主现有专用接口；后台的通用 JSON 客户端适合业务编排，单次响应最多捕获 64 MiB；大文件走文件下载/流式接口，避免在宿主进程中整份缓冲。

每个接口要传什么、返回什么，查[宿主接口参考](host-api-reference.md)：参数表、请求与响应字段说明、可直接复制的 `ctx.api` 调用和示例。用 TypeScript 或支持 JSDoc 的编辑器时，SDK 的 `host-api.d.ts` 会按路径推断：

```ts
const tasks = await ctx.api.get('/api/115/offline/tasks?status=downloading') // 推断为 OfflineTaskList
tasks.items[0].progress                                                       // number，0–1
await ctx.api.post('/api/115/share/receive', { share_url, target_cid })      // 请求体字段拼错会报错
```

稳定业务输入输出以 [OpenAPI](openapi-v3.json) 为准。公开目录仅收录插件可调用的接口，权限由宿主检查；未写入稳定契约的接口随宿主版本变化，不保证可用。先用 `conformance/project-check.mjs` 检查结构，再由宿主安装检查确认可接受性，见[安全限制](security.md)。

## 后台任务

```js
export async function run(ctx, input) {
  await ctx.task.checkpoint({ stage: 'before-transfer', share: input.share_url })
  const result = await ctx.api.post('/api/115/share/receive', input)
  await ctx.task.checkpoint({ stage: 'transferred', result })
  await ctx.notify({title:'转存完成',body:'资源已提交',dedupe_key:ctx.task.id+':done'})
  return result
}
export async function recover(ctx, checkpoint) {
  if (checkpoint?.stage === 'transferred') return {action:'complete',result:checkpoint.result}
  // 先查询目标目录、业务记录或远端状态，证实未执行后才允许 resume。
  return {action:'attention'}
}
```

任务由统一工作队列执行，插件 SQLite 保存独立历史。提交必须带稳定 business_key；相同 job、标识和输入返回原记录，改变输入返回冲突。默认不重叠，包括尚未核对的中断记录。需要并行的任务显式设置 allow_overlap。

通知见[插件通知](notifications.md)：`ctx.notify({title, body, format, channels, overrides})` 可选择 Telegram / 企业微信、内容格式与按渠道内容，并返回逐渠道结果。

后台 ctx 包含 api、storage.get/set/remove、http、files.call、watch.add/remove、cd2.call、notify、cookiecloud、sleep、settings.get、server、codec、crypto、html、xml、plugin（id/version/generation/revision/host_api），以及 task.id/update/log/checkpoint/checkpointValue。后台 storage.set 返回版本数字；页面 storage.set 返回 `{revision}`，分别对应进程内存储和普通 HTTP 响应。宿主返回的结构统一使用文档中的小写 JSON 字段名。

## 后台标准库（宿主 API 3.1）

后台没有 DOM 与 Node 内置模块，但提供常用 Web 基础对象，便于直接移植浏览器侧代码：

- 全局：`fetch`、`Headers`、`Response`、`URL`、`URLSearchParams`、`TextEncoder`、`TextDecoder`（含 gbk/gb18030/big5 等）、`atob`、`btoa`、`setTimeout`/`setInterval`/`clear*`、`queueMicrotask`、`structuredClone`、`AbortController`、`crypto.randomUUID/getRandomValues`。`fetch` 走 ctx.http（同一会话、Cookie、代理），`init.session`、`init.timeout_seconds`、`init.proxy` 可选。
- `ctx.codec`：utf8Encode/utf8Decode、encode/decode（任意字符集）、base64Encode/base64Decode、hexEncode/hexDecode、concat。二进制统一为 Uint8Array。
- `ctx.crypto`：hash/md5/sha1/sha256/sha512、hmac、aesEncrypt/aesDecrypt（cbc/gcm/ctr/ecb，默认 PKCS7）、rsaEncrypt/rsaDecrypt/rsaSign/rsaVerify（PEM 或 Base64 DER；pkcs1/oaep/pss），randomBytes。`output` 可为 hex、base64、base64url、utf8、bytes。
- `ctx.html.load(html,{baseURL})` 返回类 jQuery 选择集：find/filter/eq/first/parent/closest/children/next/prev/siblings、text/html/outerHTML/attr/attrs/url（按 baseURL 解析成绝对地址）、map/each/toArray；`ctx.html.select(html, selector)` 直接得到 `{text,html,attrs}` 数组。
- `ctx.xml.parse(xml)` 返回 `{name,attrs,text,children}` 树，适合 RSS/Torznab。

定时器只在处理器仍在等待 Promise 时运行；处理器返回后未触发的定时器随运行结束。需要跨越运行的周期动作使用清单定时任务。

task.update 接收 stage、message、progress（0–100）以及任务级计数 total、done、failed（见下节）；checkpoint 保存 JSON；sleep 单次 0–24 小时且可取消。默认单次任务 30 分钟，timeout_seconds 可自定义（至 365 天）；实际生命周期还受宿主关闭、用户取消和工作队列停止影响。长流程应分段提交并记录检查点。

## 任务队列与进度

（宿主插件 API 3.2 起提供 job `title`、`queue` 与任务级计数；较低版本宿主忽略这些字段。）每次后台运行（定时、监听、事件、页面 `ctx.tasks.run`）都会进入宿主的统一任务队列，任务队列页面实时显示，可在那里取消。

- **名称**：显示为“插件名：标题”。标题取清单 job 的 `title`（不超过 40 字），省略时用任务 ID。
- **进度**：`ctx.task.update({progress})` 直接设置百分比，队列只显示进度条。批量处理时上报任务级计数 `total`、`done`、`failed`，队列显示“已处理 done / total”和失败数；只给计数不给 progress 时，进度按 (done + failed) ÷ total 计算。
- **文件操作**：任务里调用宿主 move/copy/remove 时，宿主每秒把当前文件的进度写进 message（如“移动 a.mkv 1.2 GiB/4.0 GiB”）。上报了 total 的任务，整体进度只由计数决定，不会被单个文件的 0–100% 来回覆盖；没有上报计数的任务，文件进度就是任务进度。
- **隐藏短任务**：job 设置 `"queue": false` 时不在任务队列页面显示，适合测试、预览这类由页面发起、几秒内完成的任务；运行记录、日志和结果仍保存在插件历史里。
- **中断后的核对**：已开始执行的任务被宿主重启打断后记为“需要核对”（attention_required）。不允许重叠的 job 在核对前不接受新的运行，包括定时和监听触发，页面应提供 `ctx.tasks.retry(id)` 入口，由 recover 处理器判断完成、继续或继续等待核对。

```js
export async function run(ctx, input) {
  const items = await listWork(ctx)
  let done = 0, failed = 0
  await ctx.task.update({ stage: 'scan', message: `共 ${items.length} 项`, total: items.length, done, failed })
  for (const item of items) {
    try { await handle(ctx, item); done++ } catch (e) { failed++; await ctx.task.log(`${item.name}：${e.message}`) }
    await ctx.task.update({ stage: 'work', message: item.name, done, failed })
  }
  return { done, failed }
}
```

默认定时任务在 job 指定 default_schedule（标准五段 cron）或 interval_seconds，两者互斥。宿主时区生效。调度不补发宿主停机期间错过的周期。

## 文件与 CD2

插件不直接读写宿主文件内容。宿主文件操作仅接受允许的业务路径，也不能把宿主文件复制或移动进插件自己的目录，详见[安全限制](security.md)。文件只有两类路径：

- **插件自有路径**（相对路径，位于插件 data/files）：可 read/write/append，用于配置导出、下载暂存、生成待交付文件；单次 read 最多 16 MiB（用 offset/length 分段）。不能通过 `..` 或符号链接逃出该目录，卸载时清空。
- **宿主路径**（绝对 Linux 路径，CD2 文件写挂载路径）：只能做 list、stat、exists、walk、hash、mkdir、rename、move、copy、remove，由宿主执行，插件拿不到文件内容。read/write 宿主路径会被拒绝。

宿主路径按 CD2 挂载前缀（系统设置中的 CD2 挂载路径）自动分流：

| 源与目标 | 执行方式 | 进度 |
| --- | --- | --- |
| 两边都在 CD2 挂载路径内 | CloudDrive2 gRPC 服务端执行，不经过本地 I/O；只能在同一云盘内 | 按项目数 |
| 任一边不在 CD2 内 | 系统命令 mkdir/mv/cp/rm，CD2 一侧使用其挂载路径 | 按字节（每秒） |
| 都是普通本地路径 | 系统命令；同文件系统 mv 为即时重命名 | 按字节 |

```js
// 下载到插件目录，再交给宿主移动到 CD2（本地→挂载路径，系统命令执行，带字节进度）
await ctx.http.request({ url, save_to: 'downloads/a.torrent' })
await ctx.files.call({ operation: 'move', path: 'downloads/a.torrent', destination_dir: '/mnt/cd2/115/种子' })
await ctx.files.call({ operation: 'move', paths: ['/mnt/inbox/A', '/mnt/inbox/B'], destination_dir: '/mnt/media/电影' })
await ctx.files.call({ operation: 'rename', path: '/mnt/cd2/115/a.mkv', name: 'b.mkv' })
```

- move/copy：`destination`（单个源的完整目标路径）或 `destination_dir`（多个源保留原名）；目标已存在默认失败，`overwrite:true` 才覆盖。目录移动到已存在目录时合并内容。复制先写入同目录暂存区，完成后原子改名，取消不会留下半个目标。
- remove 可用 `paths` 批量；rename 用 `name`（只改名不换目录）；mkdir 递归创建；walk 仅限本地路径（CD2 请用 list 逐层）；hash 仅 sha256 且只限本地路径，避免通过挂载下载整个云端文件。
- 返回：system 方式为 `{backend:'system',items:[{source,path,size}]}`；CD2 方式为 `{backend:'cd2',result}`；list/stat 条目含 name/path/is_dir/size/modified/backend。

**进度**：后台任务里调用 move/copy/remove 时，宿主每秒把进度写入当前任务（stage=`file:move`、progress 百分比、message 如“移动 a.mkv 1.2 GiB/4.0 GiB（1/3）”），任务队列页面实时可见；`progress:false` 关闭。页面通过 `ctx.files.call` 发起的宿主移动/复制/删除会作为“插件 X：文件移动”任务进入统一任务队列，默认等待完成并返回 `{task_id,result}`；`ctx.files.start(options)` 立即返回 `{task_id}`，在任务队列查看进度。CD2 gRPC 操作由 CD2 服务端完成，只有开始和完成两个进度点。

页面：`ctx.files.downloadURL(path)` 与 `ctx.files.upload(path, file)` 只作用于插件自有路径。

115 返回的 name/fn/file_name 是不透明元数据，即使包含 `/` 或 `\` 也不据此拆层级。目录层级按节点 ID 与父 ID；投影到 Linux 文件名时才将 `/` 映射为 `／`，保留原始 name。

`ctx.cd2.call(method, options)` 复用主项目连接，路径可写挂载路径或 CD2 路径，传挂载路径时结果也返回挂载路径：list/stat/mkdir/rename/move/copy/remove/search。list 接收 path、force_refresh，返回 path/name/id/size/modified/is_dir 数组；mkdir 用 parent/name，rename 用 path/name，move/copy 用 path/destination，search 用 path/query/fuzzy。rename/move 返回逐项 path/file/error/retryable，宿主做身份与结果核对；move 使用 Skip 冲突策略。stat/search 返回相同文件结构；mkdir 返回 file/result，copy/remove 返回 success/error_message/paths。其他变更接口遇到超时，作者必须先查询业务结果，不应直接重发。

## 目录监听和消息触发

```js
await ctx.watch.add({id:'inbox',path:'/mnt/inbox',job:'organize',interval_seconds:5})
await ctx.watch.add({id:'cloud',path:'/mnt/cd2/115/Inbox',job:'organize',interval_seconds:15})
```

宿主按 CD2 挂载前缀判断路径：挂载目录内的路径走 CD2 接口，其余是本地监听，`kind` 不用填。事件的 `path` 是挂载路径，CD2 监听同时带 `cd2_path`。CD2 监听默认只看一层，`recursive:true` 时递归，最多 500 个目录；每个目录都是一次云端请求，请把 `interval_seconds` 设得足够大。

local 监听默认实时：宿主用 inotify 订阅目录，事件发生后经 `debounce_ms`（默认 500）立即做一次快照比较；interval_seconds 仍作为兜底全量扫描，可调大（例如 300）。`realtime:false` 关闭实时；`patterns:['*.mkv','*.mp4']` 按文件名过滤；`recursive:false` 只看第一层。超过 8192 个目录或系统 inotify 上限时自动退回轮询。cd2 为当前目录的完整 gRPC 列表轮询。首次快照建立基线，后续变化以 `{watch,changes:[{path,kind:'created|changed|removed'}]}` 提交任务。目录读取、挂载或 CD2 流失败会保留上次快照与错误，不把失败当作删除。待提交事件持久保存；后台任务恢复仍由插件核对。替换监听先 remove 再 add。此功能不改变内置整理的轮询策略。

可选清单 events：`{event:'message',job:'search',commands:['find'],prefixes:['搜索 ']}`（关键字、正则和账号消息见[消息渠道](messaging.md)）、`{event:'callback',job:'buttons'}` 或宿主业务事件 `{event:'host',job:'on-organize',types:['library_organize_*','media_library_add']}`。宿主事件在推送渠道开关、静默时段和聚合之前投递，与是否开启通知无关；`types` 支持 `*` 和前缀通配，可用类型由 `GET /api/extensions/v3/_events` 列出（整理成功/跳过/失败、STRM 生成、入库、播放、订阅、签到等）。任务输入为 `{id,type,title,content,data,at}`；事件可能密集到达，订阅任务建议设置 `allow_overlap:true`，否则上一条未结束时后续事件提交会失败。消息命中后入队；输入为宿主投影的消息或按钮事件。插件任务自行调用通知接口反馈；不会占用一个常驻脚本。同一消息分发给所有命中的插件，作者应使用独特前缀。

## 监听端口与 Webhook

清单声明同步 HTTP 处理器后，宿主可把三类入站请求交给插件：

```json
{"http":{"entry":"jobs/http.js","handler":"handle","timeout_seconds":60,"public":true},"listeners":[{"id":"api","port":18080}]}
```

```js
export async function handle(ctx, req) {
  // req: method/path/url/query/headers/remote_addr/host/source/body/body_base64/json
  if (req.headers['X-Token']?.[0] !== (await ctx.settings.get()).token) return { status: 401, json: { error: 'unauthorized' } }
  if (req.path === '/file') return { file: 'export/latest.xml' }
  return { status: 200, headers: { 'Cache-Control': 'no-store' }, json: { ok: true } }
}
```

- `/api/extensions/v3/<id>/hook/<路径>`：走宿主登录，适合页面或已登录客户端调用。
- `/plugin-hooks/<id>/<路径>`：仅当 `http.public=true`，不经宿主登录，插件必须自行校验签名或令牌。
- 独立端口：清单 `listeners` 在启用时绑定；运行时可用 `ctx.server.listen({id,port,host})` 新增并持久保存，`ctx.server.close(id)` 关闭。停用、更新、卸载和宿主关闭都会释放端口；绑定失败写入 `ctx.server.list()` 的 error。Docker 部署需映射对应端口或使用 host 网络。

返回值：字符串为 text/plain；null 为 204；对象可带 status、headers、body/body_base64/json，或 `file`（插件自有路径，支持 Range）。每个请求独立执行一次处理器（不入任务队列），单插件并发 32，请求体上限 32 MiB，默认超时 60 秒（最多 3600）。

## 设置、图标与菜单

```json
{"icon":"ui/icon.svg","menu":{"title":"资源搜索","order":10},"requires":{"api":"3.1"},
 "settings":[{"key":"site","label":"站点地址","type":"url","required":true},{"key":"token","label":"令牌","type":"password"},{"key":"mode","label":"模式","type":"select","options":[{"label":"快速","value":"fast"}],"default":"fast"}]}
```

**设置放在插件页面里**：有页面的插件应把全部设置做在自己的页面内，默认值写在插件代码里，不要再声明清单 `settings`。清单 `settings` 只用于没有页面的插件：宿主据此在插件卡片上显示设置图标，点开后在“设置”标签渲染表单，类型有 text、password、textarea、number、boolean、select、path、url；值保存在插件 KV 的 `settings` 键，后台与页面 `ctx.settings.get()` 返回默认值叠加已保存值。

**插件卡片**：主按钮“打开”进入插件页面；图标只用于设置（仅声明了清单 settings 时出现）、调试（任务运行与日志）和安装记录；启用开关和“侧边栏”开关在卡片上，更新与卸载在“更多”菜单。

**侧边栏**：插件页面是否出现在宿主侧边栏完全由用户在卡片上的“侧边栏”开关决定，新安装的插件默认不出现；`menu` 只提供入口的标题和排序，不会自动加入侧边栏。`icon` 用于插件中心卡片与页面标题，建议提供 SVG。`requires.api` 高于宿主版本时拒绝安装。

## 发布

源码目录或 .dian115p 包根目录直接包含 plugin.json。安装先 inspect 展示报告，再用返回 token 确认安装；token 15 分钟失效。更新走 inspect → update，ID 必须一致，先停止活跃任务和目录轮询；保留数据。无旧协议兼容或旧安装迁移。安装过程不调用 run 入口；启用后的定时和消息触发器按清单生效。

运行 `node conformance/project-check.mjs <插件目录>` 检查源码，再运行示例测试。安装用户自己选择是否信任；不要用混淆、动态下载代码或遗漏声明来暗示代码已经被完整审核。

## 市场与远程安装

插件中心支持 .dian115p 包、服务器源码目录和 HTTP/HTTPS 交付地址。市场索引 schema_version=3，记录每个版本的 id/name/version/source_url/sha256/delivery，可附作者声明；协议见 plugin-market/index.schema.json。用户主动刷新时才请求市场，不影响首次打开已安装插件。

用户在插件中心管理来源、刷新市场和选择版本。宿主核对下载摘要及真实清单，再对实际代码生成报告，由用户确认安装或更新。来源索引只描述交付信息，不授予权限；直接地址安装也会重新解析实际代码。

## 媒体与 AI 插件

图片裁剪、宿主 badge 水印、真实分辨率、翻译与 Emby 演员头像使用 [API 3.3 的共享能力](media-and-ai.md)。先在插件目录暂存远程图片，再由宿主处理和移动；不要自己搭建 FFP、AI 代理或读取系统配置。业务字段策略、任务恢复、并发和订阅存储仍由插件编排。

### 订阅时间基线（API 3.5）

复用 [订阅增量接口](subscriptions.md)，不按固定周期重复读取整份磁力 / ED2K 缓存或全部 PT 搜索结果。基线与未提交候选一起保存，完整空结果也推进；查询错误与未完成分页必须保留原基线。
