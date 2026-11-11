# 癫影与 MoviePilot 公共连接器

这两组接口供页面和后台通过 `ctx.api` 调用。使用宿主中已经配置的账号与连接，不要求插件再次保存宿主账号密钥。接口存在性取决于宿主版本；先探测状态，遇到 404 提示升级宿主。后台错误码语义沿用插件 API 3.13。

## 三个边界

| 使用者 | 订阅由谁管理 | 调用方式 |
| --- | --- | --- |
| DIAN115 系统订阅 + 内置 PT | DIAN115 | 宿主自己的 PT 搜索、下载 |
| DIAN115 系统订阅 + MoviePilot | DIAN115 | MP 搜索与取种；DIAN115 筛选、解析并直连下载器 |
| 第三方插件 | 按插件自己的业务决定 | 可使用 MoviePilot 完整 HTTP API，包括远端订阅功能 |

**系统订阅不会创建、接管或取消 MoviePilot 订阅。成功提交下载即完成本轮获取**，立即按本系统规则更新覆盖集数、追更或结束订阅，不轮询下载进度，不增加独立回执表。插件调用远端订阅 API 是插件自己的业务，不会自动生成系统订阅。

系统设置中的 PT 站点来源选择内置 PT 或 MoviePilot，订阅来源始终为 `pt`；癫影可独立搭配；缓存来源继续按宿主原有流程参与比较。各来源使用本系统共同的规则组、优先级、缺集和洗版判断。

## MoviePilot 通用 HTTP 调用

```js
const status = await ctx.api.get('/api/connectors/moviepilot/status')
// api_version 是配置值：auto、v2 或 v3。
const catalog = (await ctx.api.get('/api/connectors/moviepilot/options')).data
// catalog.api_version 为解析后的 v2 / v3；sites/downloaders/paths 是远端选项。
const isV2 = catalog.api_version === 'v2'

const response = await ctx.api.post('/api/connectors/moviepilot/request', {
  method: 'GET',
  path: isV2 ? '/search/media/tmdb:71' : '/search/media/71',
  query: { ...(isV2 ? {} : { media_source: ['themoviedb'] }), mtype: ['电影'], sites: ['3,7'] },
  timeout_seconds: 300,
})
const remote = response.data
if (remote.status < 200 || remote.status >= 300 || remote.body?.success !== true) {
  throw Object.assign(new Error(remote.body?.message || 'MoviePilot 调用失败'), { code: 'upstream' })
}
const resources = remote.body.data
```

`path` 相对于该实例的 `/api/v1`，例如 `/site/`、`/download/clients`、`/history/download`、`/subscribe/`。也可传 `/api/v1/...`，宿主只追加一次版本前缀。V2 精确搜索使用 `/search/media/tmdb:{id}`；V3 使用 `/search/media/{id}` 与 `media_source=themoviedb`；剧集加 `mtype=['电视剧']`、`season=['0']` 或其他季号，特别篇的 0 不可省略。

| 请求字段 | 约定 |
| --- | --- |
| `method` | GET（默认）、POST、PUT、PATCH、DELETE、HEAD、OPTIONS |
| `path` | 必须以 `/` 开头，不能是完整 URL、包含查询串或目录跳转 |
| `query` | `Record<string, string[]>`，数字和布尔值也转换成字符串 |
| `body` | 原始 JSON，与 `body_base64` 互斥；GET/HEAD 不接受请求体 |
| `body_base64` | 完整二进制或 multipart 请求体的 Base64，配合 `content_type` |
| `content_type` | 默认 application/json；multipart 须带与请求体一致的 boundary |
| `timeout_seconds` | 1–300，默认 60；搜索建议 300 |

返回 `{code:'ok',data:{status,headers,body?,body_base64?}}`。`status` 是上游 HTTP 状态，`body` 为原始 JSON（通常包含 `success/message/data`），非 JSON 使用 `body_base64`。分页头 `X-Total-Count` 等在 `headers` 中；不要假定所有上游响应具有相同业务结构。

宿主响应 200 表示连接器已取得响应；**必须检查上游 `status` 和业务结果**。远端 401/403 需要用户检查 MoviePilot 的 API Key 与权限。连接器支持有限时长的 HTTP 请求和文件传输，请求体与响应体各最多 8 MiB；不提供无限时长 SSE 或 WebSocket 隧道。

连接器开放该实例 HTTP API 的全部业务范围，站点、下载器、搜索、下载、整理、历史、远端订阅及插件操作都使用同一个入口。实际端点、参数与权限以目标实例的 V2 / V3 文档为准；连接器不翻译通用请求里的版本字段。插件也可调用远端配置类能力，因此须按任务目的说明所用能力和外部写操作。宿主本身的连接地址和密钥设置只在系统设置页管理；插件不能读取或修改这些设置。宿主代为注入 `X-API-KEY`，不接受插件自带认证头/查询参数（公开版本端点固定的 `token=moviepilot` 引导参数除外），不跟随重定向，不回传宿主注入的密钥。

读取站点、下载器与目录可直接使用脱敏的 `GET /api/connectors/moviepilot/options`，返回 `{code:"ok",data:{api_version,server_version?,sites,downloaders,paths}}`；`sites` 仅含 id/name/is_active/pri/domain/url，不包含站点 Cookie。`save_path` 兼容旧 V2 的 `download_path` 回退。V2 的 `/site/` 和 `/download/clients` 返回裸数组；当前 V3 普通 JSON 接口采用 `{success,data}` 包装。宿主内部 options 同时兼容两种结构，通用 request 始终保留上游原始响应，插件需按目标版本读取。

### 下载选中的资源

传入搜索结果中的两个原始对象，不要用目标媒体信息冒充候选身份。远端站点 ID、下载器名称、保存路径均属于 MoviePilot，不能使用本机 PT 的编号代替。

```js
const selected = resources[0] // 实际插件须先做身份、季集与质量筛选
if (!selected) return { items: [] }

// 使用插件已有的检查点保存 API，在调用前保存稳定业务标识。
const result = await ctx.api.post('/api/connectors/moviepilot/request', {
  method: 'POST', path: '/download/',
  body: {
    media_in: selected.media_info,
    torrent_in: selected.torrent_info,
    downloader: 'MoviePilot 中的下载器名称',
    // save_path: 'MoviePilot 中配置的路径或目录别名',
  },
  timeout_seconds: 300,
})
const upstream = result.data
if (upstream.status < 200 || upstream.status >= 300 || upstream.body?.success !== true || !upstream.body.data?.download_id) {
  // 外部提交失败不证明没有接单；按 recover 规则处理，不盲目自动重试。
  throw Object.assign(new Error('下载提交未获明确确认，请核对 MoviePilot'), { code: 'conflict' })
}
return { download_id: upstream.body.data.download_id }
```

系统订阅按成功提交结算；这不承诺下载器已完成传输或媒体已经入库。插件如有自己的监控需求，可自行查询 `/download/` 和历史接口；系统不会额外轮询。网络超时等无法确定的写入只保留现有任务错误/尝试记录，不自动重放。插件应使用自身检查点与 `recover` 区分明确成功、明确未提交及结果不明。

### 创建系统管理的订阅

```js
const intent = await ctx.api.post('/api/subscribe/pool/intents', {
  tmdb_id: 1399, media_type: 'tv', title: '权力的游戏',
  season: 1, total_episodes: 10,
  episode_scope_mode: 'fixed', initial_needed_episodes: '4-10',
  enabled_sources: ['dianying', 'pt'],
  // 系统订阅使用本机 PT 身份；宿主按系统开关选择站点来源，MP 站点按域名自动识别。
  sites: JSON.stringify([3, 7]), downloader: '本机下载器名称',
  // save_path: '/downloads/tv', filter_params: JSON.stringify({ free_only: true, min_seeders: 3 }),
})
// 返回的是 DIAN115 PoolIntent，不是 MoviePilot 的 subscribe ID。
```

系统订阅调用统一 PT 能力：MoviePilot 负责搜索与取种，DIAN115 沿用自己的过滤、种子文件解析和逐文件选集，再直接连接 DIAN115 中配置的 qBittorrent / Transmission，沿用原下载器和工作目录。因此整季包补缺集、指定目录、任务限速和保留文件删除继续使用现有业务参数，不经过 MP 下载接口或配套插件转发。MP 无需配置下载器；配套插件只提供站点能力。缺少解析或选集条件时明确报错，不静默整包下载。

系统管理接口 `/api/pt/execution`、`/api/pt/moviepilot/*`（站点导入）和连接器设置不向第三方插件开放。系统站点按域名及目录别名自动识别，不需要插件维护映射。插件创建本机订阅时使用本机站点 ID、下载器名和路径；插件直接调用 `/api/connectors/moviepilot/request` 时使用远端原生 ID 与参数。两类合同不能混用。插件 HTTP 调用保持独立，不受系统 PT 开关限制。

## 癫影稳定业务接口

统一前缀 `/api/plugin-host/dianying`。第三方插件仅开放下表 10 个接口，范围为查询、解锁、签到和脱敏账号信息；账号相关能力包括账号列表、状态、积分、会员及社区资料查询。其他癫影能力不开放给插件。返回结构沿用各业务端点，**不统一多包一层 `data`**；具体字段见 [OpenAPI](openapi-v3.json) 与 [宿主接口参考](host-api-reference.md)。

| 方法与相对路径 | 用途与关键字段 |
| --- | --- |
| GET `/accounts` | `{items:[{id,name,enabled,status,points,is_vip,auto_share}],availability}`；没有 API Key |
| GET `/availability` | 可选 `account_id`，查询配置及授权状态 |
| GET `/rss/options` | 资源筛选选项 |
| GET `/ffp-stats` | 文件指纹统计 |
| POST `/checkin` | `{account_id?}` 签到 |
| POST `/resources/list-shares` | `{account_id?,tmdb_id,media_type,season?,page?,size?,sort?,...}` |
| POST `/resources/unlock` | `{account_id?,share_id?,resource_id?}`；按实际资源填写编号，可能消耗积分 |
| GET `/community/profile` | 可选 `account_id/refresh` 查询参数 |
| POST `/community/ranking` | 社区排行，`account_id/refresh` 为宿主选项 |
| POST `/community/my-shares` | 我的分享，其他字段按社区查询传入 |

```js
const accounts = await ctx.api.get('/api/plugin-host/dianying/accounts')
const account = accounts.items.find(item => item.enabled)
if (!account) throw Object.assign(new Error('请先配置癫影账号'), { code: 'unavailable' })

const page = await ctx.api.post('/api/plugin-host/dianying/resources/list-shares', {
  account_id: account.id, tmdb_id: 1399, media_type: 'tv',
  season: 1, page: 1, size: 20,
})
// page.items / page.total / page.page / page.size
return { items: page.items, total: page.total }
```

没有配置的业务返回 409 和 `configuration_required`，不是可通过盲目重试修复的上游故障。积分与权限仍由宿主业务检查。解锁可能消耗积分，签到会更新账号状态；提交前保存检查点，异常后先判断已完成的业务结果。第三方插件不开放癫影转存、分享、删除、清理等操作，账号增删、API Key、自动分享及签到计划等配置继续由宿主管理。MoviePilot 公共连接器的 HTTP API 业务范围保持上述约定。
