# 宿主接口速查

插件通过普通 HTTP 调用宿主 API。以下仅列出插件可调用的公开稳定契约，权限仍由宿主检查。运行中的宿主仍按自身版本与业务配置处理请求。`/v3/releases` 为独立加密服务接口，不在 DIAN115 宿主端口。逐个接口的参数、字段与示例见[宿主接口参考](host-api-reference.md)。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/115/accounts/options` | 列出可用账号 |
| GET | `/api/115/browse-dirs` | 浏览 115 目录树 |
| GET | `/api/115/directories` | 浏览 115 目录 |
| POST | `/api/115/offline/add` | 创建离线任务 |
| POST | `/api/115/offline/clear` | 清理离线任务 |
| POST | `/api/115/offline/delete` | 删除离线任务 |
| GET | `/api/115/offline/download-path` | 查询默认离线目录 |
| POST | `/api/115/offline/pause` | 暂停离线任务 |
| GET | `/api/115/offline/quota` | 查询离线额度 |
| POST | `/api/115/offline/restart` | 重试离线任务 |
| POST | `/api/115/offline/resume` | 恢复离线任务 |
| GET | `/api/115/offline/tasks` | 查询离线任务 |
| GET | `/api/115/recyclebin` | 读取回收站 |
| POST | `/api/115/recyclebin/clear` | 清空回收站 |
| POST | `/api/115/recyclebin/delete` | 彻底删除回收站文件 |
| POST | `/api/115/recyclebin/revert` | 还原回收站文件 |
| GET | `/api/115/share-notlogin-quota` | 查询免登录转存额度 |
| POST | `/api/115/share/receive` | 转存 115 分享 |
| GET | `/api/115/shares` | 列出分享链接 |
| GET | `/api/115/shares/{share_code}` | 读取分享详情 |
| DELETE | `/api/115/shares/{share_code}` | 删除分享 |
| GET | `/api/115/shares/{share_code}/access-users` | 读取分享领取记录 |
| POST | `/api/115/shares/{share_code}/activate` | 激活分享 |
| GET | `/api/115/shares/{share_code}/download-details` | 读取分享下载明细 |
| POST | `/api/115/shares/{share_code}/renew` | 续期分享 |
| POST | `/api/115/shares/{share_code}/update` | 更新分享设置 |
| GET | `/api/115/status` | 查询 115 账号状态 |
| GET | `/api/browse` | 浏览 CD2 |
| GET | `/api/cache/magnet/changes` | 按时间窗口增量查询磁力和 ED2K 缓存 |
| GET | `/api/cd2/clouds` | 列出 CD2 云盘 |
| GET | `/api/dashboard/emby-latest` | 读取看板最新媒体 |
| GET | `/api/dashboard/library` | 读取看板媒体库 |
| GET | `/api/dashboard/quick-stats` | 读取看板快报 |
| GET | `/api/dashboard/resource-center-stats` | 读取资源中心统计 |
| GET | `/api/dashboard/stats` | 读取看板统计 |
| GET | `/api/dashboard/sync-chart` | 读取同步图表 |
| POST | `/api/emby-control/items/{id}/refresh` | 刷新 Emby 媒体 |
| GET | `/api/emby-control/libraries` | 读取 Emby 控制媒体库 |
| POST | `/api/emby-control/library/refresh` | 刷新 Emby 媒体库 |
| GET | `/api/emby-control/status` | 读取 Emby 控制状态 |
| GET | `/api/extensions/v3/_events` | 宿主业务事件目录（events[].types 可订阅的类型） |
| GET | `/api/extensions/v3/_notify/channels` | 列出通知渠道及插件可用的格式与功能 |
| GET | `/api/extensions/v3/{id}` | 安装元数据、风险报告及资源基础地址 |
| POST | `/api/extensions/v3/{id}/ai/complete` | 复用宿主 AI 生成或翻译文本 |
| GET | `/api/extensions/v3/{id}/ai/providers` | 读取可用于插件的 AI 提供商与模型 |
| POST | `/api/extensions/v3/{id}/cd2/{method}` | 复用宿主 CD2 gRPC 客户端 |
| POST | `/api/extensions/v3/{id}/cookiecloud/{operation}` | 读取或写入宿主本地 CookieCloud |
| POST | `/api/extensions/v3/{id}/cookies` | 读取 Cookie 或写入明文 Cookie 头 |
| POST | `/api/extensions/v3/{id}/cookies/import` | 导入 CookieCloud 格式 Cookie；保留属性 |
| POST | `/api/extensions/v3/{id}/data/sqlite` | 只读查询插件自有静态 SQLite |
| POST | `/api/extensions/v3/{id}/files` | 文件操作：相对路径为插件自有（可读写内容）；绝对路径或 cd2: 为宿主路径，仅宿主执行管理操作。宿主 move/copy/remove 进入任务队列 |
| GET | `/api/extensions/v3/{id}/files/download` | 下载插件自有文件（相对路径，支持 Range） |
| POST | `/api/extensions/v3/{id}/files/upload` | 流式上传到插件自有路径 |
| GET | `/api/extensions/v3/{id}/hook/{path}` | 登录态 Webhook：交给清单 http 处理器同步响应 |
| POST | `/api/extensions/v3/{id}/hook/{path}` | 登录态 Webhook：交给清单 http 处理器同步响应 |
| PUT | `/api/extensions/v3/{id}/hook/{path}` | 登录态 Webhook：交给清单 http 处理器同步响应 |
| PATCH | `/api/extensions/v3/{id}/hook/{path}` | 登录态 Webhook：交给清单 http 处理器同步响应 |
| DELETE | `/api/extensions/v3/{id}/hook/{path}` | 登录态 Webhook：交给清单 http 处理器同步响应 |
| POST | `/api/extensions/v3/{id}/http` | 普通 HTTP，持久 Cookie，可选缓存及超时 |
| GET | `/api/extensions/v3/{id}/icon` | 插件清单 icon 图片 |
| POST | `/api/extensions/v3/{id}/jobs/{job}` | 提交持久任务；相同业务标识和输入返回原任务 |
| GET | `/api/extensions/v3/{id}/listeners` | 独立监听端口及运行状态 |
| POST | `/api/extensions/v3/{id}/listeners` | 开启并持久化运行时监听端口 |
| DELETE | `/api/extensions/v3/{id}/listeners/{listener}` | 关闭运行时监听端口 |
| GET | `/api/extensions/v3/{id}/media/badges` | 列出宿主 badge 包与图片 |
| POST | `/api/extensions/v3/{id}/media/badges/read` | 读取宿主 badge 图片或保存到插件目录 |
| POST | `/api/extensions/v3/{id}/media/emby-image` | 上传插件图片到 Emby 条目主图 |
| POST | `/api/extensions/v3/{id}/media/image` | 裁剪、缩放与合成插件图片 |
| POST | `/api/extensions/v3/{id}/media/nfo` | 读取媒体 NFO 的结构化资料 |
| POST | `/api/extensions/v3/{id}/media/probe` | 复用宿主 FFP 获取真实媒体信息 |
| GET | `/api/extensions/v3/{id}/network-capabilities` | 查询宿主默认渲染能力与配置状态（不返回地址和凭据） |
| POST | `/api/extensions/v3/{id}/notify` | 发送插件通知（选择渠道、格式与按渠道内容） |
| POST | `/api/extensions/v3/{id}/render` | 按需复用外部 FlareSolverr |
| GET | `/api/extensions/v3/{id}/runs` | 读取插件/runs |
| GET | `/api/extensions/v3/{id}/runs/{run}` | 读取插件/runs/{run} |
| POST | `/api/extensions/v3/{id}/runs/{run}/cancel` | 取消任务 |
| POST | `/api/extensions/v3/{id}/runs/{run}/retry` | 调用恢复处理器核对任务结果 |
| GET | `/api/extensions/v3/{id}/settings` | 清单默认值叠加已保存的 settings |
| PUT | `/api/extensions/v3/{id}/sidebar` | 设置插件页面是否显示在侧边栏 |
| GET | `/api/extensions/v3/{id}/storage` | 读取插件/storage |
| GET | `/api/extensions/v3/{id}/storage/{key}` | 读取插件/storage/{key} |
| PUT | `/api/extensions/v3/{id}/storage/{key}` | 写入 JSON，支持乐观版本检查 |
| DELETE | `/api/extensions/v3/{id}/storage/{key}` | 删除插件 KV |
| GET | `/api/extensions/v3/{id}/usage` | 读取插件/usage |
| GET | `/api/extensions/v3/{id}/watches` | 读取插件/watches |
| POST | `/api/extensions/v3/{id}/watches` | 持久化目录轮询；变化进入统一任务队列 |
| DELETE | `/api/extensions/v3/{id}/watches/{watch}` | 删除监听并阻止晚到轮询写回 |
| GET | `/api/history` | 读取操作历史 |
| GET | `/api/history/stats` | 读取历史统计 |
| POST | `/api/library/check-owned` | 检查媒体库是否已存在 |
| GET | `/api/local-dirs` | 浏览可选目录 |
| GET | `/api/local-files` | 列出文件 |
| DELETE | `/api/local-files` | 删除文件 |
| POST | `/api/local-files/batch` | 批量管理文件 |
| GET | `/api/local-files/batch-status` | 查询文件任务 |
| POST | `/api/local-files/copy` | 复制文件 |
| POST | `/api/local-files/mkdir` | 创建目录 |
| POST | `/api/local-files/move` | 移动文件 |
| POST | `/api/local-files/organize` | 整理文件 |
| GET | `/api/local-files/organize-options` | 读取整理选项 |
| POST | `/api/local-files/recognize` | 识别媒体文件 |
| POST | `/api/local-files/rename` | 重命名文件 |
| POST | `/api/local-files/rename/execute` | 执行批量重命名 |
| POST | `/api/local-files/rename/preview` | 预览重命名 |
| POST | `/api/local-files/scrape` | 刮削文件 |
| GET | `/api/local-files/search` | 搜索文件 |
| GET | `/api/local-files/tree` | 读取目录树 |
| POST | `/api/local-files/upload` | 上传文件 |
| GET | `/api/organize/categories` | 读取整理分类 |
| GET | `/api/organize/categories/{id}` | 读取整理分类详情 |
| GET | `/api/organize/category-templates` | 读取分类模板 |
| GET | `/api/organize/config` | 读取整理配置 |
| GET | `/api/organize/history` | 读取整理历史 |
| DELETE | `/api/organize/history/{id}` | 删除整理历史 |
| GET | `/api/organize/history/{id}/detail` | 读取整理详情 |
| POST | `/api/organize/history/{id}/manual-organize` | 手动整理 |
| GET | `/api/organize/history/{id}/manual-organize-context` | 读取手动整理上下文 |
| POST | `/api/organize/history/{id}/rename-source` | 重命名整理来源 |
| GET | `/api/organize/jobs/{job_id}/progress` | 读取整理进度 |
| GET | `/api/organize/queue` | 读取整理队列 |
| POST | `/api/organize/retry-failed` | 重试失败整理 |
| GET | `/api/organize/rules` | 读取整理规则 |
| POST | `/api/organize/rules` | 创建整理规则 |
| PUT | `/api/organize/rules/{id}` | 更新整理规则 |
| DELETE | `/api/organize/rules/{id}` | 删除整理规则 |
| POST | `/api/organize/rules/{id}/scan` | 扫描整理规则 |
| POST | `/api/organize/rules/{id}/submit` | 提交整理任务 |
| POST | `/api/organize/rules/{id}/trigger` | 触发整理规则 |
| GET | `/api/organize/template-variables` | 读取模板变量 |
| GET | `/api/organize/tmdb-cache/stats` | 读取 TMDB 缓存统计 |
| GET | `/api/organize/tmdb/search` | 整理模块搜索 TMDB |
| GET | `/api/organize/wash-version/default` | 读取洗版默认配置 |
| GET | `/api/plugin-host/emby/episodes` | 读取 Emby 缺集 |
| GET | `/api/plugin-host/emby/instances` | 列出 Emby 实例 |
| GET | `/api/plugin-host/emby/items` | 查询 Emby 媒体 |
| GET | `/api/plugin-host/emby/items/{id}` | 读取 Emby 媒体详情 |
| GET | `/api/plugin-host/emby/libraries` | 读取 Emby 媒体库 |
| GET | `/api/plugin-host/emby/stats` | 读取 Emby 统计 |
| POST | `/api/pt/download` | 将 PT 种子提交宿主下载器 |
| GET | `/api/pt/downloaders` | 读取下载器列表（密码与 API Key 脱敏） |
| POST | `/api/pt/search` | 搜索指定 PT 站点 |
| GET | `/api/pt/sites` | 读取 PT 站点列表（凭据脱敏） |
| GET | `/api/rules` | 读取同步规则 |
| POST | `/api/rules` | 创建同步规则 |
| POST | `/api/rules/sync-all` | 同步全部规则 |
| PUT | `/api/rules/{id}` | 更新同步规则 |
| DELETE | `/api/rules/{id}` | 删除同步规则 |
| POST | `/api/rules/{id}/clean-orphans` | 清理孤立文件 |
| POST | `/api/rules/{id}/full-sync` | 全量同步规则 |
| POST | `/api/rules/{id}/generate-strm` | 生成 STRM |
| POST | `/api/rules/{id}/sync` | 同步规则 |
| POST | `/api/rules/{id}/sync-metadata` | 同步元数据 |
| POST | `/api/rules/{id}/toggle` | 启停同步规则 |
| DELETE | `/api/rules/{id}/tree` | 清空规则目录树 |
| GET | `/api/rules/{id}/tree/stats` | 读取规则目录统计 |
| GET | `/api/scheduler/jobs` | 读取宿主任务 |
| POST | `/api/scheduler/jobs/trigger` | 触发宿主任务 |
| GET | `/api/subscribe/air-calendar` | 读取追剧日历 |
| POST | `/api/subscribe/batch-delete` | 批量删除订阅 |
| POST | `/api/subscribe/delete-by-media` | 按媒体删除订阅 |
| GET | `/api/subscribe/entry-settings` | 读取订阅入口设置 |
| PUT | `/api/subscribe/entry-settings` | 更新订阅入口设置 |
| GET | `/api/subscribe/history` | 读取订阅历史 |
| GET | `/api/subscribe/library-settings` | 读取媒体库订阅设置 |
| PUT | `/api/subscribe/library-settings` | 更新媒体库订阅设置 |
| GET | `/api/subscribe/pool/intents` | 查询聚合订阅 |
| POST | `/api/subscribe/pool/intents` | 创建聚合订阅 |
| GET | `/api/subscribe/pool/intents/{id}` | 读取聚合订阅 |
| DELETE | `/api/subscribe/pool/intents/{id}` | 取消聚合订阅 |
| PATCH | `/api/subscribe/pool/intents/{id}/episodes` | 更新订阅集数 |
| GET | `/api/subscribe/pt-search-site-selection` | 读取订阅站点选择 |
| PUT | `/api/subscribe/pt-search-site-selection` | 更新订阅站点选择 |
| GET | `/api/subscribe/records` | 查询订阅记录 |
| GET | `/api/tasks` | 列出后台任务 |
| GET | `/api/tasks/{id}` | 读取任务详情 |
| POST | `/api/tasks/{id}/cancel` | 取消任务 |
| GET | `/api/tmdb/discover/movie` | 发现 TMDB 电影 |
| GET | `/api/tmdb/discover/tv` | 发现 TMDB 剧集 |
| GET | `/api/tmdb/genres` | 查询 TMDB 类型 |
| GET | `/api/tmdb/movie/{id}` | 查询 TMDB 电影 |
| GET | `/api/tmdb/search` | 搜索 TMDB |
| GET | `/api/tmdb/trending` | 查询 TMDB 趋势 |
| GET | `/api/tmdb/tv/{id}` | 查询 TMDB 剧集 |
| GET | `/api/workqueue/stats` | 读取工作队列统计 |
| GET | `/plugin-hooks/{id}/{path}` | 公开回调（清单 http.public=true；无需宿主登录，插件自行鉴权） |
| POST | `/plugin-hooks/{id}/{path}` | 公开回调（清单 http.public=true；无需宿主登录，插件自行鉴权） |
| PUT | `/plugin-hooks/{id}/{path}` | 公开回调（清单 http.public=true；无需宿主登录，插件自行鉴权） |
| PATCH | `/plugin-hooks/{id}/{path}` | 公开回调（清单 http.public=true；无需宿主登录，插件自行鉴权） |
| DELETE | `/plugin-hooks/{id}/{path}` | 公开回调（清单 http.public=true；无需宿主登录，插件自行鉴权） |
| POST | `/v3/decrypt` | 管理员上传加密 .dian115p 并解密为源码包；不留档、不执行插件 |
| GET | `/v3/info` | 读取加密 Worker 的插件包格式与上传容量 |
| POST | `/v3/releases` | 公开上传完整源码 .dian115p 包并取得加密交付包，无需登录或口令 |
