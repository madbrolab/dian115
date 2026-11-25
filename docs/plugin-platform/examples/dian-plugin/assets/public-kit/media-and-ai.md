# 图片、宿主 badge、FFP 与 AI（API 3.5）

插件清单使用 `"requires":{"api":"3.3"}`。页面和后台都通过现有 `ctx.api` 调用自己的 `/api/extensions/v3/${ctx.id}` 路径，无需独立服务或额外密钥。任务取消、停用和卸载会取消这些调用；不得访问其他插件的路径。接口和完整字段见 [OpenAPI](openapi-v3.json) 与 [逐接口参考](host-api-reference.md)。

## 图片处理和 badge

```js
const base = `/api/extensions/v3/${ctx.id}`
const catalog = await ctx.api.get(`${base}/media/badges`)
const pack = catalog.packs.find(p => p.id === catalog.active_id)
const badge = pack.badges[0] // 实际插件应让用户选择或用 /api/resource-badges/match 匹配
await ctx.http.request({url: coverURL, save_to:'art/source', max_bytes:32*1024*1024})
const result = await ctx.api.post(`${base}/media/image`, {
  source:'art/source', destination:'art/poster.jpg', crop:'face', ratio:2/3,
  width:600, format:'jpeg', quality:92,
  overlays: badge ? [{source:badge.asset_url,corner:'top-left',scale:0.18,x:8,y:8}] : []
})
await ctx.files.call({operation:'move',path:result.path,destination:'/media/movie/poster.jpg',overwrite:true})
```

`source`、覆盖层 `source` 和 `destination` 接受插件 `data/files` 相对路径及允许的宿主绝对路径（包括 CD2 挂载路径）；覆盖层也可使用目录接口返回的宿主 badge `asset_url`。所有文件路径沿用宿主保护规则；不接受远程 URL，远程图片先用已有 HTTP 下载。宿主绝对路径读写需要 API 3.9。页面上传自定义水印使用现有 `ctx.files.upload(path, file)`。

`crop` 支持 `none/left/right/center/face`；人脸模式在宿主本地检测最大的人脸，无法检出时明确回退 `right`，结果 `image.faces`、`image.crop_applied` 可用于展示。`ratio` 为裁剪后的宽高比，默认 `2/3`；`width/height` 只填一项时等比缩放，均填写时 `fit:contain` 等比适应框，`cover` 填满后居中裁剪。`inspect:true` 只读栅格图片头或 SVG 尺寸，不解压像素、不渲染 SVG，不需要 `destination`；返回 JPEG EXIF 纠正后的宽高。检查通过不代表压缩像素完整，处理仍可能失败，候选图回退必须覆盖实际处理阶段。

支持 JPEG、PNG、GIF 首帧、WebP 与静态 SVG 子集；纠正 JPEG EXIF 朝向。SVG 不执行脚本、不加载外部资源，不承诺完整 SVG 浏览器渲染。输出 JPEG 或 PNG；JPEG 的透明区域合成为白色，完全不透明图不创建白底。ICO badge 可以读取原始字节，但当前图片合成解码器不支持 ICO。输入最多 32 MiB，图片最多 24 MP、每边最多 12000 像素，覆盖层最多 24 个；宿主同时处理最多 2 个请求，且正在处理的源图像素合计不超过 24 MP，超出者在解码前等待，总时限 90 秒（含排队）。像素预算也覆盖 Emby 头像处理，取消或失败会释放额度；它不是整个宿主的内存硬上限。

传入合适的输出尺寸可降低后续占用。宿主裁剪只选择原图区域，再生成目标尺寸图，随后在同一成品画布上依次叠加 badge，避免逐个水印复制整图。插件若只需封面，可先 `inspect`，把目标宽度限制到 `Math.min(1200, 原图宽度, 裁剪后宽度)`，避免放大小图。宿主不会隐式缩小未指定 `width/height` 的图片，也不改写源文件。首次解码仍会展开原图，本次优化不等于 JPEG 缩略解码。

覆盖层支持固定宽度 `width` 或相对成品宽度 `scale`、四角 `corner`、向内边距 `x/y`、`opacity`。按照数组顺序叠加，超出画布部分裁掉；叠放、顺逆时针、分类策略由插件计算覆盖层数组，不在宿主写业务规则。

读取原始 badge：

```js
const raw = await ctx.api.post(`${base}/media/badges/read`, {asset_url:badge.asset_url})
// {body_base64,content_type,size}
const saved = await ctx.api.post(`${base}/media/badges/read`, {asset_url:badge.asset_url,save_to:'art/badge'})
// {path,size,sha256,content_type}
```

badge 版本发生变化后旧地址会失效，重新读取目录或匹配；不要猜测资源磁盘路径。目录返回包 ID、名称、版本和图片标识，不暴露管理配置。`POST /api/resource-badges/match` 沿用现有文本匹配，传入 `{pack_id,texts}`，返回 `results[].badges[].icon_url` 可直接用作图片 source。

## FFP 真实媒体信息

```js
const media = await ctx.api.post(`${base}/media/probe`, {path:'/media/movie.mkv'})
// width,height,resolution,duration,video_codec,audio_tracks,subtitle_tracks,...
```

`path` 是受宿主文件保护规则约束的绝对媒体路径，CD2 文件写挂载路径。支持 MP4/MKV/AVI/MOV/WMV/FLV/TS/M2TS/M4V/WebM/MPG/MPEG/ISO/VOB。可选 `sha1` 用于复用已有 SHA1 FFP 缓存；缺失时走宿主已有探测服务。缓存命中不占探测槽，真实探测共享整理服务的全局并发与内置 FFP 工具；总时限 120 秒。

不接受任意命令、可执行文件参数、HTTP URL 或 STRM 文件；不返回原始探测输出、访问直链或凭据。没有可用 FFP/挂载/视频流时返回错误或空尺寸，插件必须明确选择失败、等待或采用文件名，不得把文件名推测标成真实分辨率。

## AI 图文与对话

宿主插件 API 3.14 在页面和后台都提供 `ctx.ai`。清单中声明 `"requires":{"api":"3.14"}`。先读目录，用 `providers[].name` 展示供应商名称，提交对应的 `id`。模型选项来自该项的 `models` 和 `model`。默认选择来自目录顶层的 `default_provider_id` 和 `default_model`。可运行的选择器见[插件 API 测试台](examples/complete-plugin/ui/ai.js)。

```js
const catalog = await ctx.ai.providers()
// providerID 和 modelName 取自用户在目录中的选择。
const firstTurn = {
  role: 'user', content: '读出封面上的书名和作者。',
  images: [{path: 'covers/book.jpg'}]
}
const selection = {provider_id: providerID, model: modelName}
const reply = await ctx.ai.complete({...selection, messages: [firstTurn]})
const next = await ctx.ai.complete({
  ...selection,
  messages: [firstTurn, {role: 'assistant', content: reply.text}],
  prompt: '把刚才的书名翻译成英文。'
})
// next.text、model、provider_id、usage、finish_reason
```

- 供应商由宿主管理密钥。省略供应商时沿用“整理”场景；显式选择供应商后，省略模型即使用该供应商自己的默认模型。所选供应商失效时返回错误。识图需要选择支持视觉输入的模型，费用计入所选供应商。
- 单次调用可以只传 `{prompt}`，也可以传 `{prompt, images}` 或只传图片。每张图用 `{path}` 指定插件文件或允许读取的宿主/CD2 挂载文件，用 `{url}` 指定供应商可访问的 HTTP(S) 图片链接或 Base64 data URL，如 `data:image/png;base64,…`。链接直接交给供应商读取。本地和内嵌图片支持 JPEG、PNG、GIF、WebP。
- 多轮消息按时间顺序传入 `messages`。角色可为 `user` 或 `assistant`，图片放在用户消息中。顶层 `prompt` 和 `images` 会追加为本轮提问，`context`（任意 JSON）会附在最后一条用户消息后。对话以用户消息结尾。插件自行保存需要延续的轮次，宿主聊天记录和工具均不参与调用。
- 每次最多 64 条对话消息、8 张图片。本地和内嵌图片合计最多 8 MiB，文本与上下文合计最多 128 KiB，整个 JSON 请求体最多 12 MiB。全局同时最多 4 个调用，每次最多 150 秒。
- 支持 `system`、`max_tokens`（默认 4096，上限 16384）和 `temperature`（0–2）。返回实际使用的供应商、模型、文本、token 用量和 `finish_reason`。解析 JSON 前请检查截断状态和返回内容。

旧插件仍可通过 `ctx.api` 请求 `GET /api/extensions/v3/{id}/ai/providers` 和 `POST /api/extensions/v3/{id}/ai/complete`（纯文本自 3.3 起）。页面取 `ctx.id`，后台取 `ctx.plugin.id`。请求体和返回值与 `ctx.ai` 一致。

## 文件整理与演员资料

复用 `ctx.files.call` 的 `copy/move` 和现有任务进度。3.3 新增 `hardlink/symlink`：单个普通源文件、完整 `destination`，源和目标必须是 CD2 挂载之外的宿主本地路径；拒绝 `overwrite:true`，不自动创建目标父目录；硬链接要求同一文件系统。文件操作继续保护系统目录和宿主敏感数据；允许的宿主文件可读写或放入插件目录。`rmdir` 只删除一个空的插件或本地目录，不递归，不支持 CD2；自动清空源目录应使用它，不能用递归 `remove` 代替。

```js
await ctx.files.call({operation:'hardlink',path:'/incoming/movie.mkv',destination:'/media/movie.mkv'})
await ctx.files.call({operation:'rmdir',path:'/incoming/empty'})
const people = await ctx.api.get('/api/plugin-host/emby/items?type=Person&limit=50&offset=0&proxy_id=1')
await ctx.api.put('/api/emby-control/items/person-id/metadata?proxy_id=1',{overview:'Actor biography'})
await ctx.api.post(`${base}/media/emby-image?proxy_id=1`,{item_id:'person-id',source:'actors/portrait.jpg'})
```

`type=Person` 复用 Emby 条目查询的分页、实例选择与返回字段，宿主请求 Emby `/Persons`。头像接口从插件相对路径或允许的宿主/CD2 挂载路径读取图片，转为最长框 1200×1800 的 JPEG，使用宿主所持凭据上传为该条目的 Primary 图；属于覆盖操作。简介沿用现有元数据接口，刷新沿用现有媒体库/条目刷新接口。插件不需要读取 Emby API Key。

PT 搜索与提交也继续用现有 `/api/pt/search`、`/api/pt/download`。新增可选 `mteam_mode:"normal"|"adult"` 只用于馒头适配器；模式参与搜索缓存键。选择 adult 时不附加电影/剧集分类。番号订阅应显式选择站点 ID、按番号复核候选并把 PT 种子只提交下载器；订阅状态与去重、重试策略由插件维护。

## 静态 SQLite 资料库与 NFO（3.4）

这两项调用要求 `requires.api=3.4`。现有媒体与 AI 调用保持兼容。页面和后台使用相同的 `ctx.api`，不增加数据库运行时对象。

```js
// 先通过现有 HTTP 下载或页面上传，保存到插件自己的 data/files。
const tables = await ctx.api.post(`${base}/data/sqlite`, {source:'reference/actors.db'})
const page = await ctx.api.post(`${base}/data/sqlite`, {
  source:'reference/actors.db', table:'Names', columns:['Alias','Name'],
  equals:{Alias:'示例演员'}, limit:20, offset:0
})
// {columns,items,limit,offset}；table 留空时为 {tables}。
const metadata = await ctx.api.post(`${base}/media/nfo`, {path:'/media/example/movie.nfo'})
```

SQLite 接受插件相对路径或允许的宿主绝对路径（API 3.9，包括 CD2 挂载路径），最大 512 MiB；宿主敏感数据库路径仍受保护，不接受任意 SQL、连接字符串、ATTACH 或扩展。查询验证表和列名，筛选值使用参数绑定；每个筛选条件用 AND 连接、精确比较及 SQLite ASCII NOCASE。最多 64 列、200 行、offset 1000000、5 秒。文本最多前 8192 个字符，BLOB 返回 null，总文本最多 2 MiB，超限应缩小查询。表必须是真实表，不能查询视图。省略 columns 返回该表所有列及列目录。

文件按 `mode=ro&immutable=1` 打开，不读取外置 WAL。仅用于下载完成、已关闭并完成 checkpoint 的静态快照；不得查询仍被其他任务写入的数据库。第三方资料按需下载并缓存在插件自己的文件区，下载到临时路径、验证后再替换；不需要打包数据库驱动、整库或启动外部服务。数据库使用许可由资料提供者规定。

NFO 只接受受宿主保护规则约束的绝对 `.nfo` 路径，CD2 文件写挂载路径。只读普通文件，最多 2 MiB、50000 元素、32 层、单字段 64 KiB；要求单个 `movie` 根节点。不执行 DTD/外部实体，也不返回原始 XML。返回标题、简介、日期、厂商、合集、演员及头像、类型和标签等已声明字段；`uniqueid` 仅在 `type=num/jav` 时作为番号候选。调用者仍须将 NFO 的番号与当前媒体核对后再整理。
