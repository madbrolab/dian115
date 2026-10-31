# 插件 API 完整参考（宿主插件 API 3.8）

本页列出插件可用的全部能力。第一次开发先看[快速开始](quickstart.md)，字段规则见[清单参考](manifest.md)，常见写法见[配方](cookbook.md)。业务细节见[开发指南](developer-guide.md)、[网络](network.md)、[生命周期](storage-and-lifecycle.md)、[页面](ui-theme.md)；接口契约见 [OpenAPI](openapi-v3.json) 与[速查](host-api-quick-reference.md)；类型见 [SDK](examples/sdk/)。

## 1. 清单 plugin.json

| 字段 | 说明 |
| --- | --- |
| `schema_version` | 固定 3 |
| `id` / `name` / `version` | 小写 id（字母数字、点、连字符，≤128）、显示名、版本 |
| `description` / `author` / `homepage` | 说明信息 |
| `requires.api` | 最低宿主插件 API，例如 `"3.1"`；宿主更低时拒绝安装。3.2 新增 job 的 `title`、`queue` 与 `task.update` 的 `total/done/failed`，较低宿主会忽略这些字段 |
| `icon` | 包内 svg/png/webp，显示在插件中心与页面标题 |
| `ui.entry` | `ui/page.js`（导出 `mount(el, ctx)`）或 `ui/index.html` |
| `menu` | `{title, order}`，侧栏入口的标题与排序（需要 ui）；是否显示由用户在插件卡片的“侧边栏”开关决定，默认不显示 |
| `settings[]` | `{key,label,type,default,options,required,help,placeholder}`；type：text/password/textarea/number/boolean/select/path/url。值存在 KV 的 `settings` 键 |
| `jobs[]` | `{id,entry,handler='run',recover,timeout_seconds,default_schedule|interval_seconds,allow_overlap,title,queue,daemon}`；`daemon:true` 是[常驻任务](long-connections.md)；`title`（≤40 字）是任务在宿主任务队列里的名称（显示为“插件名：标题”）；`queue:false` 不在任务队列页面显示，适合测试、预览等短任务 |
| `events[]` | `message`（commands/prefixes/keywords/patterns/channels）、`account_message`（prefixes/keywords/patterns/all/peer_types/include_outgoing）、`callback`、`host`（types，支持 `*` 与前缀通配），见[清单参考](manifest.md) |
| `permissions[]` | `telegram.bot`、`wecom`、`telegram.account`、`network.tcp`，用户授权后生效，见[消息渠道](messaging.md)和[长连接](long-connections.md) |
| `http` | `{entry,handler='handle',timeout_seconds≤3600,public}`：Webhook、公开回调与监听端口的处理器 |
| `listeners[]` | `{id,port,host}`，启用时自动绑定的端口（需要 http） |
| `declared_usage` | 作者声明（apis/sites/files/risk…），仅告知，不是权限白名单 |

UI、jobs、http 至少提供一项。

## 2. 页面 ctx（`mount(el, ctx)` / `window.DIAN115Plugin`）

| 成员 | 说明 |
| --- | --- |
| `id`、`signal`、`theme.mode`、`theme.subscribe(fn)` | 插件 ID、页面关闭中止信号、明暗主题 |
| `api.get/post/put/patch/delete/head(path, body)` | 调用任意宿主 `/api/` 接口，沿用登录与业务校验 |
| `storage.get/set(key,value,expected_revision)/remove/list` | 插件 KV（加密），CAS 用 expected_revision |
| `settings.get()` / `settings.set(value)` | 默认值叠加已保存设置 / 保存 |
| `http.request/cookies/importCookies/render` | 同后台，由宿主发出请求 |
| `files.call(options)` | 见第 5 节；宿主移动/复制/删除进入任务队列，返回 `{task_id,result}` |
| `files.start(options)` | 宿主移动/复制/删除立即返回 `{task_id}` |
| `files.downloadURL(path)` / `files.upload(path, file)` | 插件自有文件的下载地址（Range）与流式上传 |
| `cd2.call(method, options)` | list/stat/mkdir/rename/move/copy/remove/search |
| `watch.list/add/remove` | 目录监听（第 6 节） |
| `tasks.run(job, business_key, input)/list/get/cancel/retry` | 统一任务队列 |
| `server.list/listen/close/hookURL/publicHookURL` | 监听端口与回调地址 |
| `events.catalog()` | 可订阅的宿主事件类型 |
| `notifications.send(options)` / `notify(options)`、`notifications.channels()` | 发送通知、查看渠道（见[插件通知](notifications.md)） |
| `cookiecloud(op, options)`、`usage()` | CookieCloud、磁盘用量 |
| `telegram.bot.*`、`telegram.account.*`、`wecom.*`、`messaging.reply` | 需授权，见[消息渠道](messaging.md) |

## 3. 后台 ctx（`export async function run(ctx, input)`）

| 成员 | 说明 |
| --- | --- |
| `api.*` | 进程内调用宿主 `/api/` 路由，返回原接口 JSON；失败抛错含 status/method/path/data |
| `storage.get/set/remove` | set 返回版本号 |
| `settings.get()` | 设置值 |
| `task.id/checkpointValue/update({stage,message,progress,total,done,failed})/log(text)/checkpoint(value)` | 任务进度、日志（单条 ≤8 KiB，保留最近 500 条）、检查点；进度实时显示在宿主任务队列，见[开发指南](developer-guide.md#任务队列与进度) |
| `http.request/cookies/importCookies/render` | 见[网络](network.md) |
| `files.call(options)` | 见第 5 节，宿主文件进度自动写入当前任务 |
| `notify(options)` / `notifications.send`、`notifications.channels()` | 通知：channels 选渠道、format 选 text/markdown/html、overrides 按渠道内容，返回逐渠道 deliveries（见[插件通知](notifications.md)） |
| `cd2.call(method, options)`、`watch.add/remove`、`cookiecloud` | 同页面 |
| `server.list/listen/close`、`server.hookPath/publicHookPath` | 端口与回调路径 |
| `telegram.bot.*`、`telegram.account.*`、`wecom.*`、`messaging.reply` | 需授权，见[消息渠道](messaging.md) |
| `ws.connect(options)`、`http.stream(options)` | 长连接与流式读取，仅后台，见[长连接](long-connections.md) |
| `tcp.connect(options)`、`tcp.listen(options)` | 原生 TCP，需要 `network.tcp` 授权，仅后台 |
| `response.sse(options)`、`response.stream(options)` | 流式输出，仅 HTTP 处理器 |
| `sleep(ms)` | 可取消等待，单次 ≤24 小时 |
| `plugin` | `{id,name,version,generation,revision,host_api}` |
| `codec` | utf8Encode/utf8Decode、encode/decode(任意字符集)、base64Encode/Decode、hexEncode/Decode、concat |
| `crypto` | hash/md5/sha1/sha256/sha512、hmac、aesEncrypt/aesDecrypt、rsaEncrypt/rsaDecrypt/rsaSign/rsaVerify、randomBytes、randomUUID |
| `html.load(html,{baseURL})`、`html.select(html, selector)` | 类 jQuery 选择集 |
| `xml.parse(xml)` | `{name,attrs,text,children}` |

`recover(ctx, checkpoint)` 返回 `{action:'complete',result}`、`{action:'resume'}` 或 `{action:'attention'}`。

后台全局：`fetch`、`WebSocket`、`Headers`、`Response`、`URL`、`URLSearchParams`、`TextEncoder`、`TextDecoder`、`atob`、`btoa`、`setTimeout/setInterval/clear*`、`queueMicrotask`、`structuredClone`、`AbortController`、`crypto.randomUUID/getRandomValues`、`console.log`（写入任务日志）。没有 DOM、Node 内置模块、`require` 和子进程。脚本引擎支持 async/await，不支持 `for await` 和异步生成器。后台 ctx 没有 `tasks`、`events`、`usage`，这些只在页面提供；任务报错的文字末尾带文件和行号。

## 4. HTTP 处理器（`export async function handle(ctx, req)`）

入口：`/api/extensions/v3/<id>/hook/<路径>`（需登录）、`/plugin-hooks/<id>/<路径>`（`http.public`，插件自行鉴权）、`listeners` 与 `ctx.server.listen` 打开的端口。

`req`：method、path、url、query、headers、remote_addr、host、source（hook/public/listener:&lt;id&gt;）、body、body_base64、json。返回字符串、null（204）或 `{status,headers,body|body_base64|json|file}`；`file` 为插件自有路径。ctx 与后台相同（无 task 进度持久化）。

## 5. 文件

| 路径 | 允许的操作 |
| --- | --- |
| 相对路径（插件 data/files） | read（≤16 MiB/次）、write、append、list、walk、stat、exists、hash、mkdir、rename、move、copy、remove |
| 绝对路径（宿主，CD2 文件写挂载路径） | list、walk（仅本地）、stat、exists、hash（仅本地，sha256）、mkdir、rename、move、copy、remove；**不能 read/write** |

宿主路径分流：两边都在 CD2 挂载内走 CD2 gRPC；任一边不在 CD2 内走系统命令，CD2 一侧使用挂载路径。系统命令操作每秒报告字节进度。参数：path/paths、destination/destination_dir、name、overwrite、progress、pattern、limit。

## 6. 监听与事件

- 目录监听：`{id,path,job,kind?,interval_seconds,realtime,debounce_ms,patterns,recursive}`，`kind` 通常省略，由宿主按 CD2 挂载前缀判定；任务输入 `{watch,changes:[{path,cd2_path?,kind:'created'|'changed'|'removed'}]}`。
- 宿主事件：任务输入 `{id,type,title,content,data,at}`；类型列表 `GET /api/extensions/v3/_events`。
- 消息与按钮：`message`/`callback` 事件，输入为宿主投影的消息或回调。
- 定时：`default_schedule`（五段 cron）或 `interval_seconds`。

## 7. 宿主业务接口（`ctx.api`）

逐个接口的参数、字段、调用与示例见[宿主接口参考](host-api-reference.md)；SDK 的 `host-api.d.ts` 为 `ctx.api` 提供按路径推断的类型。返回值是接口原始 JSON；非 2xx 抛错，错误对象的 `data.error` 为原因。公开契约只收录插件可调用的接口，宿主仍执行[权限检查](security.md)。

## 8. 插件自有能力路由

插件使用 `/api/extensions/v3/${ctx.id}` 下的自有数据、任务、网络、文件、媒体和 AI 能力；共享事件与通知渠道由 `ctx.events`、`ctx.notifications` 获取。完整字段与可用操作见[速查](host-api-quick-reference.md)。

## 9. 资源与限额

| 项目 | 限额 |
| --- | --- |
| 脚本内存 | 宿主监测存活堆：运行插件脚本期间堆比空闲基线增长超过 `DIAN115_EXTENSION_MEMORY_MB`（默认 512 MiB）即中止正在运行的插件脚本，任务记为失败“内存超出预算”。只有一个脚本在运行时精确归属；多个同时运行时一并中止 |
| 宿主文件内容 | 不进入插件；插件自有文件单次读 16 MiB |
| HTTP 响应 | 默认 64 MiB，不写盘最多 256 MiB；更大用 save_to |
| HTTP 处理器 | 单插件并发 32，请求体 32 MiB，默认 60 秒 |
| 异步宿主调用 | 全局 128（`DIAN115_EXTENSION_IO_CONCURRENCY`），满时立即报错 |
| 目录快照 | 并发 4（`DIAN115_EXTENSION_WATCH_CONCURRENCY`），实时监听 ≤8192 个目录 |
| 任务 | 默认 30 分钟，最多 365 天；日志单条 8 KiB、保留 500 条 |
| HTTP 缓存 | 每插件 128 MiB；Cookie 每会话 4096 条 |
| 长连接 | 每插件 16 条，含 WebSocket、流式读取、TCP 和对外推送；WebSocket 单条消息默认 1 MiB，最大 16 MiB；TCP 单次写入 16 MiB |
| 常驻任务 | 重启等待 1 秒到 5 分钟；保留最近 200 条日志 |
| 消息渠道 | 每插件每分钟：机器人 30、企业微信 20、账号发送 20、账号读取 60 |
| CD2 递归监听 | 最多 500 个目录，单次扫描 2 分钟 |

插件是可信扩展：与宿主同进程、同登录权限运行。限额防止失控，不构成安全隔离。

## API 3.3 媒体与 AI

完整参数、限制、页面/后台示例见 [media-and-ai.md](media-and-ai.md)。通过 ctx.api 复用图片处理、badge 图片读取、FFP、AI 与 Emby 图片上传；文件 call 增加 hardlink/symlink/rmdir，PT 搜索增加 mteam_mode。

## API 3.7 长连接

`jobs[].daemon`、`ctx.ws`、`ctx.http.stream` 与全局 `WebSocket` 见 [long-connections.md](long-connections.md)。3.8 增加 `ctx.tcp` 和 `ctx.response`。

## API 3.6 消息渠道

`permissions`、`keywords`、`patterns`、`account_message` 事件以及 `ctx.telegram`、`ctx.wecom`、`ctx.messaging` 见 [messaging.md](messaging.md)。

## API 3.5 订阅增量查询

通过 `GET /api/cache/magnet/changes` 读取磁力及 ED2K 缓存增量，`POST /api/pt/search` 的 `incremental` 模式实时查询单个馒头站点的发布时间窗口。按每个订阅与来源独立保存基线、分页进度及待提交候选。详见 [subscriptions.md](subscriptions.md)。
