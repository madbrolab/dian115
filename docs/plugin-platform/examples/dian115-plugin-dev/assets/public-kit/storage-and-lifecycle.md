# 插件数据存储与生命周期

插件的持久 JSON 数据存储在宿主管理的数据库中，由安装身份隔离。插件通过 `host.call` 使用 `/api/plugin-runtime/storage/:key`，不直接打开数据库，也不取得连接字符串。

## 数据位置

SQLite 部署将插件表放在宿主主数据库，默认主库为 `/config/dian115.db`。PostgreSQL 部署使用已配置后端中的插件表，本地数据目录仍保存插件包、编译缓存和宿主加密材料。部署可配置数据目录，开发者不能硬编码宿主路径。

宿主负责插件包和私有文件。guest 只看到当前签名包的只读 `/package`；没有可写 `/data` 和 `/tmp`。包升级会替换只读资源，业务数据不能写入包内。宿主不创建可写 data/tmp 目录。

WASM 的 Host Call 身份来自宿主持有的安装上下文。安装只保存签名包信息、运行元数据及权限，不向插件发放客户端密码或 webhook 密钥。宿主已有凭据通过受管的 `credential_ref` 绑定使用；用户在插件中填写的自有账号密码和 Cookie 可直接经 action 提交 HTTP 登录，Cookie 由受管会话加密持久化。

| 内容 | 存储方式 |
| --- | --- |
| 配置、规则、少量业务记录 | Host Storage JSON |
| 任务结果和进度 | 对应 Host Job API，插件保存 job_ref |
| 可恢复长任务的检查点 | 宿主加密保存的恢复记录，单条最多 16 KiB，不计入业务 KV 用量 |
| 宿主媒体与文件 | Host API 给出的业务数据与引用，不复制完整宿主数据库 |
| 自有站点登录 | 页面直接输入密码、Cookie；受管 HTTP 会话加密保存 Cookie，动作重放记录加密保存；普通页面偏好不保存秘密 |
| 宿主密钥 | 宿主凭据绑定的 credential_ref，不用普通 KV 冒充密钥库 |
| 包内模板等固定资源 | 只读 `/package` |
| 页面偏好 | 可丢弃且有明确命名空间的界面状态；业务数据仍使用 Host Storage |

## 键与 JSON 结构

键长 1–160 字符，由 ASCII 字母、数字和点、短横线、下划线组成；分隔符不能连续或位于首尾。`settings`、`rules.rule01` 合法，`settings/rules.json`、`a..b` 不合法。

每个 JSON 值最大 256 KiB，每安装所有值合计最大 16 MiB。超额返回 HTTP 413 和 `quota_exceeded`。列表拆成有界记录，不把整个媒体库、图片 Base64 或无限历史塞进一个配置值。

```json
{"value":{"schema_version":1,"enabled":true,"selected_emby_instance":2,"rules":[{"id":"rule01","enabled":true}]}}
```

请求的 `value` 可以是任意有效 JSON；业务 schema_version 由插件维护。响应外层是 `{data,meta}`，`data` 包含 key、value、revision 和 updated_at；HTTP ETag 如 `"pkv_2"`。不要把 HTTP 传输封套、Host Call Base64 封套与业务 JSON 混为一层。

## 读写一致性

GET 不存在键返回 404。PUT 必须使用 16–128 字符的 Idempotency-Key。省略 If-Match 允许覆盖；需要读取后修改时带回原 ETag，版本不符返回 412 `version_conflict`。If-Match 必须为带双引号的正整数版本 ETag（如 `"pkv_2"`），不接受裸数字、未加引号或弱 ETag。发生冲突先读取最新值，再由业务合并，不能无限覆盖重试。

DELETE 必须使用 Idempotency-Key，对不存在键成功；携带 If-Match 返回 400；此接口由宿主在事务中核对当前版本。Storage 提供单键读写、元数据分页和用量查询，不提供任意 SQL、跨键事务、目录或二进制对象库。

## 分页与用量

使用前通过 `host.capabilities` 确认 `features.storage_catalog_v1 === true`，并在 Manifest 声明对应的 GET Host API。两个接口均需要 `storage.kv`，只读取当前安装的数据：

| 接口 | 行为 |
| --- | --- |
| `GET /api/plugin-runtime/storage?prefix=rules.&limit=50&cursor=...` | 按键升序返回元数据，默认 50、最多 100 条 |
| `GET /api/plugin-runtime/storage-usage` | 返回 keys、used_bytes、remaining_bytes、limit_bytes、value_limit_bytes |

分页响应为 `{data:{items:[{key,revision,bytes,updated_at}],next_cursor},meta}`，不包含 value，也不读取值正文。需要展示具体记录时再逐键 GET。`prefix` 是区分大小写的字面前缀，可为空或由存储键字符组成；下划线没有通配符含义，`rules.` 这样的未完成键可以作为前缀。

后续页使用相同 prefix 和返回的完整不透明 cursor；next_cursor 为 null 时结束。游标绑定当前安装与前缀，15 分钟后过期，篡改、跨安装、换前缀或过期返回 400 `invalid_cursor`，从第一页重新查询。分页采用键游标，不是快照：并发增删改可能在翻页期间可见，不用于跨键事务或全量一致备份。

用量按已提交 JSON 值的 UTF-8 字节数计算，不含键、索引、日志、包或数据库文件大小。`keys` 是 KV 行数，受管页面偏好 `ui.preferences.v1` 计为一个键，其整个 JSON 值计入用量。该值查询结果反映读取时刻；并发写入仍以写入事务的配额判断为准，不能用 remaining_bytes 绕过 413。卸载后新安装从零开始。

轻量 SDK 提供 `StorageList`、`StorageUsage`，不自动拉取所有页或重试。示例见 [SDK](examples/sdk/README.md)。

## 生命周期

| 操作 | 持久数据 | 运行行为 |
| --- | --- | --- |
| 页面关闭 | 保留 | 停止页面刷新，后台工作由宿主继续管理 |
| 空闲释放 | 保留 | 释放 guest，打开页面或新工作会按需唤醒 |
| 插件或宿主重启 | 保留 | 重新初始化，从宿主读取业务状态 |
| 停用 | 保留 | 拒绝新调用，停止插件调度和路由 |
| 同插件升级 | 保留 | 插件按 schema_version 幂等迁移数据 |
| 卸载 | 清空 | 停止执行，删除私有数据和文件 |
| 卸载后重装 | 空配置 | 不恢复旧配置、密钥、缓存或调用回执 |

声明 `recovery_handler` 的页面后台长任务可以通过 `host.job.checkpoint` 保存检查点。宿主重启后先调用只读核对回调，由插件查询上游业务事实，再决定续跑、完成或请求人工处理；没有核对回调的任务保持不确定状态，不会自动重复副作用。用户主动取消（包括尚待核对的任务）会终止后续执行并删除恢复记录。每安装最多 128 条、全局最多 1024 条恢复记录，完整协议见 [长任务恢复](job-recovery-v1.md)。

卸载清理 KV、日志、调用回执、幂等记录、任务、加密恢复记录和投递、目录监控、调度记录、绑定凭据、账户引用及私有包及其所属目录、待确认导入包和专属编译缓存。清理失败会保留停用的清理状态，管理员可重试，宿主启动也会继续清理；全部完成后才报告成功。

安装接纳与卸载使用同一生命周期顺序：已接纳安装时卸载返回冲突；清理标记存在时拒绝新的安装及本地导入。待确认包的领取、校验和安装意图提交不能跨过卸载的撤销阶段；旧令牌被清除后重新提交返回失效。后台安装工作实际解压前再次核对持久操作仍为 queued/running，已删除或已结束的旧工作不会重建安装或私有文件。卸载完成后的新导入按全新请求处理。

已经完成的用户媒体、转存文件和主项目订阅按各自业务生命周期管理。卸载只删除插件私有状态并撤销后续执行权，不级联删除用户媒体。

## 浏览器存储与备份

当前插件 UI 使用不透明来源沙箱，原生浏览器存储不可访问。页面偏好通过 `api.storage` 保存在同安装 KV，单值 16 KiB、合计 64 KiB、最多 128 键；卸载一并清空，旧安装晚写被拒绝。业务持久状态仍使用 Host Storage。详见 [隔离与受管存储](ui-isolation-v1.md)。

备份由宿主管理。JSON 数据随所选数据库备份，加密材料和包随数据目录备份；编译缓存可以重建。插件不接触备份密钥。升级修改数据结构之前应验证回滚兼容性，不能只回退包而忽略已经迁移的数据。

## HTTP Cookie 会话

HTTP 会话独立于普通 KV，按安装编号和账号会话隔离并加密保存。每安装最多 32 个会话，每会话 256 条 Cookie、256 KiB；没有常驻浏览器或 Cookie 保活任务。休眠、停用及重启保留，卸载与迟到写入保护沿用安装生命周期；重装为空。CookieCloud 导入是私有副本，显式写回是对共享用户服务的业务操作，不随卸载撤销。完整协议见 [HTTP 会话](http-sessions-v1.md)。

安装后自定义站点通过 HTTP sites 接口加密保存于当前安装的 `http.sites.v1` KV，计入既有 KV 用量；无需新增表、改写签名 Manifest 或重新安装。卸载与普通 KV 一并删除，格式见 HTTP 会话协议。
