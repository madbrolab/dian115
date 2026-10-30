# 插件订阅与增量搜索（API 3.5）

插件继续使用自己的存储、消息与定时任务管理订阅。宿主提供查询及提交能力；不需要另建后台服务或读取宿主数据库文件。使用以下增量能力须声明 `requires.api: "3.5"`。

## 磁力与 ED2K 缓存

```js
const page = await ctx.api.get(
  '/api/cache/magnet/changes?keyword=SSIS-001&since=2026-01-01T00%3A00%3A00Z&limit=100'
)
// { items: [...], until: '2026-01-02T00:00:00Z', complete: false,
//   cursor_time: '2026-01-01T12:00:00Z', cursor_id: 123 }
```

`ctx.api.get` 只接收路径；查询参数须编码进 URL。该接口同时返回磁力和 ED2K，时间范围在数据库查询端筛选，按 `updated_at, id` 升序用游标续读，不做全量 COUNT 或 OFFSET。标题与文件名提供宽匹配，插件仍应核对精确番号。

- `since` 包含下界，省略从 1970-01-01 开始；`until` 排除上界，省略由宿主固定为查询开始的 UTC 整秒。时间须为整秒 RFC3339，不接受未来时间。
- `limit` 为 1–500，默认 100。未读完时，下一次带上同一 `since/until` 和返回的 `cursor_time/cursor_id`。同一秒的多条记录不会因仅比较时间而跳过。
- `complete=true` 表示此窗口读完，即使 `items=[]` 也应把基线更新为 `until`。`complete=false` 仅保存续页游标；异常不返回可推进的成功窗口。
- 更新旧缓存也属于增量。下一轮可回看 60 秒覆盖同秒写入及短暂延迟，配合资源去重；这不是重新读取全部历史。长期回填的旧时间数据需要显式重扫。
- `magnet_link` 存储原始链接，`link_type` 为 `magnet` 或 `ed2k`。ED2K 的 `info_hash` 是 MD4，**不能**拼成 BTIH 磁力。保留 ED2K 链接提交 `POST /api/115/offline/add`，核对 `success=true` 与 `accepted` 数量。

## 馒头按发布时间查询

```js
const response = await ctx.api.post('/api/pt/search', {
  keyword: 'SSIS-001', site_ids: [7], mteam_mode: 'adult',
  incremental: true, published_after: '2026-01-01T00:00:00Z', page: 1,
})
const { torrents, window } = response.data
// window: { since, until, complete, next_page?, page_signature? }
```

`incremental=true` 必须明确指定一个已启用的馒头站点和 `keyword`；多站点由插件并发调用并分别保存基线。其他 PT 站点暂不支持这一模式。宿主复用站点认证、请求调度和下载器；将发布时间范围传给馒头，按发布时间倒序，每次实时取一页 100 条，不复用普通搜索页缓存。

`published_after` 包含下界，省略为 1970-01-01；`published_before` 为排他上界，首次可省略，由宿主固定。续页必须沿用 `window.since/until` 并传 `page=window.next_page`，不能将上界改成新的当前时间。整页 100 条不会被当作完成，仍须取下一页；空末页同样允许推进。重复 `page_signature`、错误、缺少窗口、站点返回不符合时间范围/排序的数据均不可推进基线。查询范围按发布时间定义，不表示历史种子做种人数或促销状态的变更流。

此模式返回原始候选，不执行影视匹配和优先级过滤；`page_size/max_pages/extra_keywords/priority_rule/stop_when_found` 不参与此单页查询。插件核对番号后用原有 `POST /api/pt/download` 提交下载器。PT 资源不要转交 115。普通搜索的既有行为保持不变。

## 持久化与恢复顺序

以“订阅 ID × 来源 ID / 站点 ID”为键，保存 `baseline_at`、尚未完成的固定窗口及游标、最近检查时间、错误。首次查询历史匹配资源；新增或变更来源仅重建该来源进度。

1. 请求当前窗口的一页；各来源失败互不影响。
2. 将候选和该来源进度在同一次版本比较写入中保存。完整窗口推进基线，未完成窗口仅保存游标。完整空结果也推进基线。
3. 消费已保存候选；提交前持久化提交意图，成功后记录回执。只提交一条时仍保留剩余候选，供恢复或“继续寻找其他资源”处理。
4. 超时、任务中断、响应丢失不能证明未提交。先核对远端；无法确认时等待人工核对，禁止自动重发。ED2K 的 MD4 不应与 BTIH 混用来核对任务。

外部 HTTP 数据库接口也必须真实接收 `since/until/cursor` 并在来源端过滤；建议返回 `{ items, complete, next_cursor }`。未提供这一能力的传统接口可兼容使用，但应明确显示全量模式，不能假装设置本地时间就减少了远端读取。敏感请求头和带签名 URL 不写日志。
