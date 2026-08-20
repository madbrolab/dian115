# Plugin Host API v2 参考

本文是第三方插件调用 DIAN115 宿主能力的接口参考。接口的 OpenAPI 3.1 机器可读版本见 [`openapi-v1.yaml`](./openapi-v1.yaml)。

插件不会自行连接 DIAN115 的 HTTP 端口。WASM 插件通过 `dian115.host_call`，受管 process 插件通过运行时协议的 `host.call`，把同一个 Host Call 请求交给宿主。宿主先核对安装时批准的 `METHOD + /api/path`，再分发到 DIAN115 的真实业务 Handler；返回状态码和 JSON 字段与该 Handler 一致。

## 1. Host Call 契约

请求：

```json
{
  "method": "POST",
  "path": "/api/115/offline/add",
  "headers": {
    "Content-Type": "application/json",
    "Idempotency-Key": "offline-01J6YQ8V7JWQF2PM2S3N8K3A1C"
  },
  "body_base64": "eyJhY2NvdW50Ijp7Im1vZGUiOiJtYWluIn0sInVybHMiOlsibWFnbmV0Oj94dD11cm46YnRpaDphYmNkZWYiXSwic2F2ZV9jaWQiOiIxMjMifQ=="
}
```

`body_base64` 解码后是：

```json
{
  "account": { "mode": "main" },
  "urls": ["magnet:?xt=urn:btih:abcdef"],
  "save_cid": "123"
}
```

响应：

```json
{
  "status": 200,
  "headers": {
    "Content-Type": ["application/json; charset=utf-8"]
  },
  "body_base64": "eyJzdWNjZXNzIjp0cnVlLCJhY2NlcHRlZCI6MSwic2F2ZV9jaWQiOiIxMjMiLCJhY2NvdW50Ijp7Im1vZGUiOiJtYWluIiwiaWQiOjEsIm5hbWUiOiLkuLvlj7cifX0="
}
```

插件必须先判断外层 `status`，再按接口文档解码 `body_base64`。业务失败仍会得到正常的 Host Call 响应，例如外层 `status: 400`，解码后的 Handler 响应为 `{"error":"..."}`。只有权限拒绝、Host Call 格式错误或运行时故障才会让 Host Call 本身失败。

### 1.1 允许的字段与限制

- `method`：`GET`、`HEAD`、`POST`、`PUT`、`PATCH` 或 `DELETE`。
- `path`：本页登记的 `/api/...` 实际路径；路径参数必须替换为真实值，查询参数直接拼入 `path`。
- `headers`：只允许 `Accept`、`Content-Type`、`If-Match`、`If-None-Match`、`Idempotency-Key`、`X-Correlation-ID`。
- `body_base64`：可省略或为空；非空时必须是标准或无填充 Base64，解码后最多 256 KiB。
- 单次响应体最多 256 KiB。
- 插件不要发送 `Authorization`、Cookie、反向代理头或 DIAN115 内部头；宿主会注入自身认证上下文。
- 所有会创建、更新、删除、移动、转存或发送通知的调用都应带稳定且唯一的 `Idempotency-Key`。同一次业务重试复用原值，不同业务使用新值。

### 1.2 安装时声明

`manifest.json` 必须逐项声明准确的方法和模板路径：

```json
{
  "permissions": {
    "apis": [
      {
        "method": "GET",
        "path": "/api/115/directories",
        "reason": "让用户选择转存目录"
      },
      {
        "method": "POST",
        "path": "/api/115/offline/add",
        "reason": "把用户输入的离线地址提交到所选账号"
      }
    ],
    "network": []
  }
}
```

声明参数路由时保留冒号模板，例如 `/api/pt/subscriptions/:id`；调用时使用 `/api/pt/subscriptions/42`。批准一个参数模板不会批准同级的静态路由。

## 2. 115 多账号接口

### 2.1 账号选择器

GET 接口使用查询参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `account_mode` | `main \| backup_pool \| backup` | 省略时为 `main`。`backup_ref`/`small` 仅为内部兼容名，插件不要使用。 |
| `account_id` | int64 | `account_mode=backup` 时必填且必须大于 0。 |

POST 接口在 JSON 中使用：

```json
{ "account": { "mode": "backup", "id": 7 } }
```

- `main`：当前主账号；`id` 可省略。
- `backup`：指定备用账号；`id` 必填。
- `backup_pool`：宿主选择一个当前可用的备用账号。第一次目录或业务调用后，应读取响应中的 `account.id`，后续调用改用 `{ "mode": "backup", "id": 返回值 }`，保证目录浏览和最终写入始终落到同一账号。
- Cookie、Token 和登录材料始终留在宿主进程内；账号列表只返回安全的显示字段。

### 2.2 接口目录

| 方法与路径 | 查询或请求体 | 成功响应 |
| --- | --- | --- |
| `GET /api/115/accounts/options` | 无 | `{accounts:[{mode,id?,name,user_name?,cloud_name?,is_vip?,cookie_status?}]}` |
| `GET /api/115/directories` | 账号查询参数；`cid` 默认 `0` | `{dirs:[{cid,name}],cid,account:{mode,id,name}}` |
| `GET /api/115/offline/tasks` | 账号查询参数；`page` 默认 1；`page_size` 默认 30；可选 `stat` | 115 离线列表字段，加宿主生成的安全 `account` 摘要 |
| `GET /api/115/offline/quota` | 账号查询参数 | 115 离线额度字段，加安全 `account` 摘要 |
| `GET /api/115/offline/download-path` | 账号查询参数 | 默认离线目录字段，加安全 `account` 摘要 |
| `POST /api/115/offline/add` | `{account,urls:[1..100],save_cid?}` | `{success:true,accepted,save_cid,account}` |
| `POST /api/115/offline/delete` | `{account,info_hash?,info_hashes?,delete_source}` | 115 删除结果，加安全 `account` 摘要 |
| `POST /api/115/offline/clear` | `{account,flag}` | 115 清理结果，加安全 `account` 摘要 |
| `POST /api/115/offline/restart` | `{account,info_hash}` | 115 重试结果，加安全 `account` 摘要 |
| `POST /api/115/share/receive` | `{account,share_url?或share_code?,receive_code?,file_ids?,target_cid?}` | `{success:true,share_code,target_cid,account}` |

备用账号没有主账号的默认保存目录，`save_cid`/`target_cid` 必须明确提供。

目录浏览示例：

```json
{
  "method": "GET",
  "path": "/api/115/directories?account_mode=backup&account_id=7&cid=0",
  "headers": {},
  "body_base64": ""
}
```

分享转存的解码后请求体：

```json
{
  "account": { "mode": "backup", "id": 7 },
  "share_url": "https://115.com/s/example?password=1234",
  "target_cid": "987654321"
}
```

`file_ids` 省略时转存分享的全部内容。若同时提供 `share_url` 和 `share_code`，宿主以解析后的链接信息为准；显式 `receive_code` 优先于链接中的接收码。

## 3. 文件管理与 CD2

插件传入的始终是宿主文件管理器显示的路径。宿主按已配置的 `cd2_mount_prefix` 自动选后端：

- 浏览、创建目录、重命名以及纯 CD2 的删除/移动/复制直接走 CD2 gRPC。
- 路径不在 CD2 前缀内时走容器内本地文件系统。
- 移动/复制只要任一源或目标不是 CD2 路径，整次操作就通过容器可见的挂载路径执行；只有全部源和目标都在 CD2 命名空间时才走 CD2 gRPC。
- `/proc`、`/sys`、`/dev`、文件系统根、CD2 挂载根和不允许修改的云盘根会被拒绝。

### 3.1 浏览接口

| 方法与路径 | 查询参数 | 成功响应 |
| --- | --- | --- |
| `GET /api/local-dirs` | `path?`、`source_path?`、`root_path?` | `{current,entries:[{name,path,is_dir}]}` |
| `GET /api/local-files` | `path`，省略时 `/` | `{current,parent,backend:"local"|"cd2",entries:[FileEntry]}` |
| `GET /api/local-files/tree` | `path`，省略时 `/` | `{name,path,children:[...]}`；只返回当前层目录节点 |
| `GET /api/browse` | CD2 原生 `path`，默认 `/` | `{path,files:[{name,path,is_dir,size}]}` |
| `GET /api/cd2/clouds` | 无 | `{clouds:[{name,path}]}` |
| `GET /api/local-files/organize-options` | `path` | `{path,mode,rules:[{id,name,mode,source_path,target_path,media_type,transfer_mode,cloud_name?}]}` |
| `GET /api/local-files/batch-status` | 必填 `task_id` | `{id,operation,status,total,done,errors}` |

`FileEntry`：

```json
{
  "name": "example.mkv",
  "path": "/media/example.mkv",
  "is_dir": false,
  "size": 734003200,
  "mod_time": "2026-08-21T02:00:00Z",
  "ext": ".mkv"
}
```

### 3.2 写接口

| 方法与路径 | 请求体 | 成功响应 |
| --- | --- | --- |
| `POST /api/local-files/mkdir` | `{path}` | `{success:true,path}` |
| `POST /api/local-files/rename` | `{old_path,new_name}` | `{success:true,new_path}` |
| `DELETE /api/local-files` | `{paths:[...]}` | `{success:true}` |
| `POST /api/local-files/move` | `{src_paths:[...],dest_dir}` | `{success:true}` |
| `POST /api/local-files/copy` | `{src_paths:[...],dest_dir}` | `{success:true}` |
| `POST /api/local-files/recognize` | `{path}` | 宿主媒体识别结果对象 |
| `POST /api/local-files/organize` | `{path,rule_id}` | `{message:"整理任务已提交"}` |
| `POST /api/local-files/batch` | `{operation:"delete"|"move"|"copy",paths:[...],dest_dir?}` | HTTP 202：`{task_id,status,total}` |

同步移动示例的解码后请求体：

```json
{
  "src_paths": ["/mnt/cd2/115/Incoming/Movie.mkv"],
  "dest_dir": "/mnt/cd2/115/Movies"
}
```

批量任务创建后轮询：

```json
{
  "method": "GET",
  "path": "/api/local-files/batch-status?task_id=file-operation-01J6YQ...",
  "headers": {},
  "body_base64": ""
}
```

## 4. 插件实例存储（KV）

三个接口都只能访问当前安装实例自己的数据。`key` 必须为 1–160 个字符，由字母、数字以及非连续的 `. _ -` 组成，不能以分隔符开头或结尾。

| 方法与路径 | 请求 | 成功响应 |
| --- | --- | --- |
| `GET /api/plugin-runtime/storage/:key` | 无 | `{data:{key,value,revision,updated_at},meta:{request_id,idempotent_replay}}`，并返回 `ETag: "pkv_N"` |
| `PUT /api/plugin-runtime/storage/:key` | `{value:<任意 JSON>}`；更新时带 `If-Match: "pkv_N"` | 同 GET，版本递增 |
| `DELETE /api/plugin-runtime/storage/:key` | `Idempotency-Key`；重复删除仍成功 | `{data:{},meta:{...}}` |

首次创建时可以不带 `If-Match`；更新必须使用最近一次 GET/PUT 返回的 ETag。两个执行流同时写同一 key 时，失败的一方得到 `412 version_conflict`，应重新 GET、合并后再用新的幂等键 PUT。

```json
{
  "method": "PUT",
  "path": "/api/plugin-runtime/storage/settings",
  "headers": {
    "Content-Type": "application/json",
    "If-Match": "\"pkv_3\"",
    "Idempotency-Key": "settings-update-01J6YQ..."
  },
  "body_base64": "eyJ2YWx1ZSI6eyJlbmFibGVkIjp0cnVlLCJpbnRlcnZhbCI6MzB9fQ=="
}
```

不要把 Cookie、Token、接收码、下载地址或其他凭据写入插件存储。

## 5. 目录监控与轮询

目录监控由宿主持久化并按间隔轮询。插件进程/实例重启后任务仍存在；变化以插件运行时事件投递。每个安装实例最多 32 条，轮询间隔为 5–86400 秒，默认 30 秒。

| 方法与路径 | 请求体 | 成功响应 |
| --- | --- | --- |
| `GET /api/plugin-runtime/watches` | 无 | `{data:{items:[Watch]},meta:{...}}` |
| `POST /api/plugin-runtime/watches` | `{source,event_topic,interval_seconds?,recursive}` | HTTP 201：`{data:Watch,meta:{...}}` |
| `PATCH /api/plugin-runtime/watches/:watch_ref` | 至少一个：`event_topic`、`interval_seconds`、`recursive`、`state` | `{data:Watch,meta:{...}}` |
| `DELETE /api/plugin-runtime/watches/:watch_ref` | 无 | `{data:{watch_ref,deleted:true},meta:{...}}` |
| `POST /api/plugin-runtime/watches/:watch_ref/retry` | 空体 | HTTP 202：`{data:{watch_ref,event_id,status:"retrying"},meta:{...}}` |
| `POST /api/plugin-runtime/watches/:watch_ref/resync` | 空体 | HTTP 202：`{data:{watch_ref,status:"baseline_pending"},meta:{...}}` |

本地/CD2 源：

```json
{
  "source": {
    "kind": "host_path",
    "path": "/mnt/cd2/115/Incoming"
  },
  "event_topic": "files.incoming.changed",
  "interval_seconds": 30,
  "recursive": true
}
```

115 源：

```json
{
  "source": {
    "kind": "115",
    "account": { "mode": "backup", "id": 7 },
    "cid": "987654321"
  },
  "event_topic": "cloud.incoming.changed",
  "interval_seconds": 60,
  "recursive": false
}
```

`event_topic` 必须同时出现在插件 manifest 的 `events` 声明中，并获得运行时事件订阅能力；否则创建/更新会返回 400。`backup_pool` 只在创建时分配一次，Watch 中保存的是实际备用账号 ID。

变化事件的 `data`：

```json
{
  "watch_ref": "fw_0123456789abcdef",
  "source_kind": "host_path",
  "backend": "cd2",
  "added": ["Movie.mkv"],
  "removed": [],
  "modified": ["status.json"],
  "truncated": false,
  "resync_required": false,
  "occurred_at": "2026-08-21T02:00:00.123Z"
}
```

插件必须按事件 ID 幂等处理。`truncated` 或 `resync_required` 为 true 时重新枚举目录并在完成后调用 `resync`。投递失败会自动重试；进入死信后可调用 `retry`。

## 6. 订阅接口

宿主在把订阅响应交给插件前会递归删除 `download_url`，把 Cookie、Token、API Key、passkey 等字段替换为 `[redacted]`，并对错误、详情和消息中的可复用 URL 做脱敏。插件不能通过这些接口读取 PT 站点或下载器凭据。

### 6.1 统一订阅记录

| 方法与路径 | 查询或请求体 | 成功响应 |
| --- | --- | --- |
| `GET /api/subscribe/records` | 可选 `channel=pt|aggregate`、`media_type=movie|tv` | `{code:"ok",data:{records:[SubscribeRecord]}}` |
| `DELETE /api/subscribe/records/:id` | 历史记录数字 ID | `{code:"ok"}` |
| `PUT /api/subscribe/records/:id/status` | `{status}` | `{code:"ok"}` |

后两个接口是旧记录兼容操作。`cancelled`、`completed`、`landed` 会物理删除记录；新插件优先操作下列 PT/聚合权威订阅。

### 6.2 聚合订阅

| 方法与路径 | 查询或请求体 | 成功响应 |
| --- | --- | --- |
| `GET /api/subscribe/pool/intents` | `state?`、`media_type?`、`limit` 默认 100/最大 500、`offset` 默认 0 | `{code:"ok",data:[PoolIntent],counts:{...}}` |
| `POST /api/subscribe/pool/intents` | `PoolIntentCreate` | `{code:"ok",data:PoolIntent}` |
| `GET /api/subscribe/pool/intents/:id` | 数字 ID | `{code:"ok",data:PoolIntent}` |
| `PATCH /api/subscribe/pool/intents/:id/episodes` | `{total_episodes,needed_episodes?,covered_episodes?}` | `{code:"ok",data:PoolIntent}` |
| `DELETE /api/subscribe/pool/intents/:id` | 数字 ID | `{code:"ok"}` |

创建电影：

```json
{
  "tmdb_id": 550,
  "media_type": "movie",
  "title": "Fight Club",
  "year": "1999",
  "enabled_sources": ["dianying", "pt", "tg"]
}
```

创建剧集：

```json
{
  "tmdb_id": 1396,
  "media_type": "tv",
  "season": 1,
  "title": "Breaking Bad",
  "total_episodes": 7,
  "initial_covered_episodes": "1-3",
  "initial_needed_episodes": "4-7",
  "library_snapshot_provided": true
}
```

`media_type` 只能是 `movie`/`tv`。剧集未传 `season` 时默认为 1；显式 season 必须大于等于 0。重复订阅或修正规则裁剪后已无缺集会返回 409。

### 6.3 PT 订阅

| 方法与路径 | 查询或请求体 | 成功响应 |
| --- | --- | --- |
| `GET /api/pt/subscriptions` | 可选 `state` | `{code:"ok",data:[PTSubscription]}` |
| `POST /api/pt/subscriptions` | `PTSubscriptionCreate` | `{code:"ok",data:PTSubscription,search_submitted,search_message}` |
| `GET /api/pt/subscriptions/:id` | 数字 ID | `{code:"ok",data:PTSubscription}` |
| `DELETE /api/pt/subscriptions/:id` | 数字 ID | `{code:"ok"}` |
| `POST /api/pt/subscriptions/:id/cancel` | 空体；语义与 DELETE 相同 | `{code:"ok"}` |
| `POST /api/pt/subscriptions/:id/search` | 空体 | `{code:"ok",message}` |
| `GET /api/pt/subscriptions/:id/attempts` | `limit` 默认/最大 50 | `{code:"ok",data:[PTSubscriptionAttempt]}`，不含 `download_url` |
| `GET /api/pt/subscriptions/:id/download-tasks` | `limit` 默认 20、最大 100 | `{code:"ok",data:[PTDownloadTask]}` |

最小创建请求：

```json
{
  "tmdb_id": 550,
  "media_type": "movie",
  "title": "Fight Club"
}
```

常用可选字段包括 `season`、`year`、`poster_path`、`backdrop_path`、`total_episodes_known`、`sites`（JSON 数组字符串）、`search_interval_seconds`、`needed_episodes`、`covered_episodes`、`is_upgrade`、`keyword`、`search_imdbid`、`episode_priority` 和 `filter_params`。下载器和保存路径由宿主配置解析，插件不能传入或读取下载器凭据。

## 7. 插件通知

`POST /api/notifications/plugin` 只产生独立的 `plugin_notification_message` 类型。插件 ID 和名称由宿主安装记录注入，插件不能冒充其他插件。

```json
{
  "level": "success",
  "title": "整理完成",
  "body": "已整理 12 个文件，失败 0 个",
  "job_ref": "job_01J6YQ8V7JWQF2PM2S3N8K3A1C",
  "dedupe_key": "organize-job-01J6YQ8V7JWQF2PM2S3N8K3A1C"
}
```

- `level`：`info`、`success`、`warning`、`error`。
- `title`：必填，最多 160 个字符。
- `body`：必填，最多 2000 个字符。
- `job_ref`：可选，必须属于当前插件且形如 `job_...`，最多 128 个字符。
- `dedupe_key`：可选，最多 200 个字符；10 分钟内重复值会返回 `deduplicated:true`。
- 每个安装实例每分钟最多 12 条；429 响应带 `Retry-After`。

成功或接受排队的响应：

```json
{
  "data": {
    "event": "plugin_notification_message",
    "accepted": true
  },
  "meta": {
    "request_id": "req_example",
    "idempotent_replay": false
  }
}
```

`deduplicated` 和 `suppressed` 只在值为 `true` 时出现。通知被用户关闭或 Telegram 未配置也是成功结果，`accepted:false`、`suppressed:true` 并给出 `suppression_reason`，插件不应无限重试。

## 8. TMDB 宿主缓存接口

所有请求都走宿主现有 TMDB 客户端、代理、缓存和限流链路；API Key 不会交给插件。

| 方法与路径 | 查询参数 | 成功响应 |
| --- | --- | --- |
| `GET /api/tmdb/search` | 必填 `q`；`page` 默认 1 | `{page,total_results,total_pages,results:[TmdbItem]}` |
| `GET /api/tmdb/movie/:id` | 正整数电影 ID | 电影详情对象 |
| `GET /api/tmdb/tv/:id` | 正整数剧集 ID；`raw_episode_counts=true` 可跳过宿主集数修正 | 剧集详情和 `seasons` |
| `GET /api/tmdb/trending` | `media_type` 默认 `all`；`time_window` 默认 `day`；`page` 默认 1 | TMDB 搜索结果 |
| `GET /api/tmdb/discover/movie` | TMDB discover 查询参数 | TMDB 搜索结果 |
| `GET /api/tmdb/discover/tv` | TMDB discover 查询参数 | TMDB 搜索结果 |
| `GET /api/tmdb/genres` | `type=movie|tv`，其他值按 movie | `{genres:[{id,name}]}` |

搜索示例：

```json
{
  "method": "GET",
  "path": "/api/tmdb/search?q=Breaking%20Bad&page=1",
  "headers": { "Accept": "application/json" },
  "body_base64": ""
}
```

Discover Handler 会把查询参数传给 TMDB；常用参数包括 `page`、`sort_by`、`with_genres`、`without_genres`、`with_original_language`、`vote_average.gte`、`vote_count.gte`、`primary_release_year`、`first_air_date_year`、`include_adult`、`region`、`with_watch_providers`、`watch_region`。不要传 `api_key`，语言由宿主 TMDB 配置决定。

## 9. 错误与重试

普通 DIAN115 Handler 的错误通常为：

```json
{ "error": "参数或业务错误", "code": "optional_machine_code" }
```

插件实例存储、Watch 和通知使用 `application/problem+json`：

```json
{
  "type": "https://dian115.example/problems/version-conflict",
  "title": "Storage write rejected",
  "status": 412,
  "code": "version_conflict",
  "detail": "plugin kv version conflict",
  "request_id": "req_example",
  "retryable": false
}
```

处理规则：

- 400/403/404/409/412：先修正请求、权限或状态，不要原样无限重试。
- 429：遵守 `Retry-After`，并加入抖动。
- 500/502/503：可用原 `Idempotency-Key` 做有上限的指数退避。
- 202：请求已持久化或排队，不代表最终业务完成；按对应状态接口或运行时事件跟踪。
- 所有日志只记录方法、模板路径、状态码、宿主 request ID 和脱敏摘要；不要记录 Cookie、Token、接收码、分享链接、磁力链接或完整外部 URL。
