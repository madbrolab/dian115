# 宿主接口速查表

从 [OpenAPI](openapi-v1.yaml) 的公开目录生成，共 176 项。安装时声明精确的方法和路径模板；调用方式见 [Host Call v2](host-call-v2.md)。

网络声明是代理路由偏好。扩展访问与可选接口规则见开发指南；下表描述标准目录。

## "files-upload"

| 方法 | 路径模板 | 用途 | 风险 | 宿主管理凭据 |
| --- | --- | --- | --- | --- |
| POST | `/api/local-files/upload` | 上传文件：以 multipart 表单上传文件到文件管理器目录。 | 写入 | 否 |

## "plugin-files"

| 方法 | 路径模板 | 用途 | 风险 | 宿主管理凭据 |
| --- | --- | --- | --- | --- |
| GET | `/api/plugin-host/files/entries` | 列出目录条目：按目录引用分页列出文件条目。 | 读取 | 否 |
| GET | `/api/plugin-host/files/entries/:entry_ref` | 读取条目详情：读取一个文件条目的元数据。 | 读取 | 否 |
| GET | `/api/plugin-host/files/entries/:entry_ref/content` | 读取文件内容：分页读取文件内容，支持 Range，单页最大 4MiB，可循环读取完整文件。 | 读取 | 否 |
| GET | `/api/plugin-host/files/roots` | 列出插件文件根：列出当前插件可访问的本地与 CD2/AURA 挂载根目录。 | 读取 | 否 |
| PATCH | `/api/plugin-host/files/entries/:entry_ref` | 重命名条目：重命名一个文件或目录条目。 | 删除或不可逆操作 | 否 |
| POST | `/api/plugin-host/files/directories` | 创建目录：在可写根目录下创建目录。 | 写入 | 否 |
| POST | `/api/plugin-host/files/downloads` | 下载文件到目录：把远程文件流式下载到指定本地可写目录（排除 CD2/AURA 挂载），返回任务引用。 | 写入 | 否 |
| POST | `/api/plugin-host/files/operations` | 复制或移动：异步复制或移动文件条目，返回任务引用。 | 删除或不可逆操作 | 否 |
| PUT | `/api/plugin-host/files/entries/:entry_ref/content` | 写入文件内容：按偏移写入本地文件内容，单次最大 4MiB。 | 写入 | 否 |

## "plugin-jobs"

| 方法 | 路径模板 | 用途 | 风险 | 宿主管理凭据 |
| --- | --- | --- | --- | --- |
| GET | `/api/plugin-host/jobs/:job_ref` | 查询插件任务：查询当前插件的一个异步任务状态。 | 读取 | 否 |
| POST | `/api/plugin-host/jobs/:job_ref/cancel` | 取消插件任务：取消当前插件的一个异步任务；仍有恢复记录的 failed/attention_required 任务也可取消，原子清空检查点并停止后续恢复。 | 写入 | 否 |

## "plugin-runtime"

| 方法 | 路径模板 | 用途 | 风险 | 宿主管理凭据 |
| --- | --- | --- | --- | --- |
| DELETE | `/api/plugin-runtime/storage/:key` | 删除插件数据：删除当前安装实例自己的持久化数据。 | 删除或不可逆操作 | 否 |
| GET | `/api/plugin-runtime/storage/:key` | 读取插件数据：读取当前安装实例自己的持久化数据。 | 读取 | 否 |
| PUT | `/api/plugin-runtime/storage/:key` | 保存插件数据：保存当前安装实例自己的持久化数据。 | 写入 | 否 |

## "plugin-runtime/watch"

| 方法 | 路径模板 | 用途 | 风险 | 宿主管理凭据 |
| --- | --- | --- | --- | --- |
| DELETE | `/api/plugin-runtime/watches/:watch_ref` | 删除目录监控：永久删除当前插件的一条目录监控及其游标。 | 删除或不可逆操作 | 否 |
| GET | `/api/plugin-runtime/watches` | 查询目录监控：读取当前插件创建的宿主目录监控任务。 | 读取 | 否 |
| PATCH | `/api/plugin-runtime/watches/:watch_ref` | 更新目录监控：更新当前插件的监控周期、事件主题、递归或启停状态。 | 写入 | 否 |
| POST | `/api/plugin-runtime/watches` | 创建目录监控：由宿主持久化轮询本地、CD2 或 115 目录，并向插件投递变化事件。 | 写入 | 是 |
| POST | `/api/plugin-runtime/watches/:watch_ref/resync` | 重建目录监控基线：清空监控游标并从当前目录状态重新建立基线。 | 删除或不可逆操作 | 是 |
| POST | `/api/plugin-runtime/watches/:watch_ref/retry` | 重试目录事件：立即重试最近待投递或进入死信的目录变化事件。 | 写入 | 是 |

## "plugin-transfer"

| 方法 | 路径模板 | 用途 | 风险 | 宿主管理凭据 |
| --- | --- | --- | --- | --- |
| GET | `/api/plugin-host/accounts/115` | 列出 115 账号选项：列出当前插件可用的 115 账号选项。 | 读取 | 是 |
| GET | `/api/plugin-host/transfers/115/offline-quota` | 查询离线配额：查询 115 离线配额。 | 读取 | 是 |
| GET | `/api/plugin-host/transfers/115/offline-tasks` | 查询离线任务：查询 115 离线任务列表。 | 读取 | 是 |
| GET | `/api/plugin-host/transfers/115/share-previews/:preview_ref/items` | 列出分享条目：列出分享预览中的条目。 | 读取 | 是 |
| GET | `/api/plugin-host/transfers/115/targets` | 列出转存目标：列出 115 转存目标目录。 | 读取 | 是 |
| POST | `/api/plugin-host/accounts/115/selections` | 创建账号选择：创建一个有有效期的 115 账号选择引用。 | 写入 | 是 |
| POST | `/api/plugin-host/transfers/115/offline-downloads` | 创建离线下载：向账号选择指向的账号提交离线下载。 | 写入 | 是 |
| POST | `/api/plugin-host/transfers/115/share-previews` | 预览 115 分享：解析 115 分享链接并创建预览。 | 读取 | 是 |
| POST | `/api/plugin-host/transfers/115/share-receives` | 接收 115 分享：把 115 分享转存到账号选择指向的目录。 | 写入 | 是 |
| POST | `/api/plugin-host/transfers/115/targets` | 创建转存目标：创建 115 转存目标目录引用。 | 写入 | 是 |

## 115

| 方法 | 路径模板 | 用途 | 风险 | 宿主管理凭据 |
| --- | --- | --- | --- | --- |
| DELETE | `/api/115/shares/:share_code` | 删除分享：删除一条分享链接。 | 删除或不可逆操作 | 是 |
| GET | `/api/115/accounts/options` | 列出可用账号：返回不含 Cookie 的主账号和备用号池选项。 | 读取 | 是 |
| GET | `/api/115/browse-dirs` | 浏览 115 目录树：读取目标账号的目录树。 | 读取 | 是 |
| GET | `/api/115/directories` | 浏览 115 目录：读取目标账号的目录列表。 | 读取 | 是 |
| GET | `/api/115/offline/download-path` | 查询默认离线目录：查询目标账号的默认离线目录。 | 读取 | 是 |
| GET | `/api/115/offline/quota` | 查询离线额度：查询目标账号的离线配额。 | 读取 | 是 |
| GET | `/api/115/offline/tasks` | 查询离线任务：查询目标账号的离线任务。 | 读取 | 是 |
| GET | `/api/115/recyclebin` | 读取回收站：读取目标账号的回收站列表。 | 读取 | 是 |
| GET | `/api/115/share-notlogin-quota` | 查询免登录转存额度：查询目标账号的免登录转存配额。 | 读取 | 是 |
| GET | `/api/115/shares` | 列出分享链接：读取目标账号创建的分享列表。 | 读取 | 是 |
| GET | `/api/115/shares/:share_code` | 读取分享详情：读取一条分享的详情。 | 读取 | 是 |
| GET | `/api/115/shares/:share_code/access-users` | 读取分享领取记录：读取一条分享的领取用户记录。 | 读取 | 是 |
| GET | `/api/115/shares/:share_code/download-details` | 读取分享下载明细：读取一条分享的下载明细。 | 读取 | 是 |
| GET | `/api/115/status` | 查询 115 账号状态：读取目标账号的在线状态。 | 读取 | 是 |
| POST | `/api/115/offline/add` | 创建离线任务：将磁力、ED2K 或其他离线地址添加到指定目录。 | 写入 | 是 |
| POST | `/api/115/offline/clear` | 清理离线任务：批量清理目标账号中的离线任务。 | 删除或不可逆操作 | 是 |
| POST | `/api/115/offline/delete` | 删除离线任务：删除目标账号中的离线任务。 | 删除或不可逆操作 | 是 |
| POST | `/api/115/offline/pause` | 暂停离线任务：暂停目标账号的离线任务。 | 写入 | 是 |
| POST | `/api/115/offline/restart` | 重试离线任务：重新提交一个离线任务。 | 写入 | 是 |
| POST | `/api/115/offline/resume` | 恢复离线任务：恢复目标账号的离线任务。 | 写入 | 是 |
| POST | `/api/115/recyclebin/clear` | 清空回收站：清空目标账号的回收站。 | 删除或不可逆操作 | 是 |
| POST | `/api/115/recyclebin/delete` | 彻底删除回收站文件：从回收站彻底删除文件。 | 删除或不可逆操作 | 是 |
| POST | `/api/115/recyclebin/revert` | 还原回收站文件：还原回收站中的文件。 | 写入 | 是 |
| POST | `/api/115/share/receive` | 转存 115 分享：将 115 分享链接转存到目标账号的指定目录。 | 写入 | 是 |
| POST | `/api/115/shares/:share_code/activate` | 激活分享：激活一条分享。 | 写入 | 是 |
| POST | `/api/115/shares/:share_code/renew` | 续期分享：续期一条分享。 | 写入 | 是 |
| POST | `/api/115/shares/:share_code/update` | 更新分享设置：更新一条分享的有效期等设置。 | 写入 | 是 |

## cd2

| 方法 | 路径模板 | 用途 | 风险 | 宿主管理凭据 |
| --- | --- | --- | --- | --- |
| GET | `/api/browse` | 浏览 CD2：通过宿主已配置的 CD2 gRPC 连接浏览目录。 | 读取 | 是 |
| GET | `/api/cd2/clouds` | 列出 CD2 云盘：读取宿主配置中可用的 CD2 云盘名称。 | 读取 | 是 |

## dashboard

| 方法 | 路径模板 | 用途 | 风险 | 宿主管理凭据 |
| --- | --- | --- | --- | --- |
| GET | `/api/dashboard/emby-latest` | 读取看板最新媒体：读取看板最新入库媒体。 | 读取 | 否 |
| GET | `/api/dashboard/library` | 读取看板媒体库：读取看板媒体库视图。 | 读取 | 否 |
| GET | `/api/dashboard/quick-stats` | 读取看板快报：读取看板快速统计。 | 读取 | 否 |
| GET | `/api/dashboard/resource-center-stats` | 读取资源中心统计：读取资源中心统计。 | 读取 | 否 |
| GET | `/api/dashboard/stats` | 读取看板统计：读取看板汇总统计。 | 读取 | 否 |
| GET | `/api/dashboard/sync-chart` | 读取同步图表：读取同步趋势图表数据。 | 读取 | 否 |

## emby

| 方法 | 路径模板 | 用途 | 风险 | 宿主管理凭据 |
| --- | --- | --- | --- | --- |
| GET | `/api/emby-control/libraries` | 读取 Emby 控制媒体库：读取 Emby 媒体库及同步配置。 | 读取 | 是 |
| GET | `/api/emby-control/status` | 读取 Emby 控制状态：读取 Emby 控制模块状态。 | 读取 | 是 |
| GET | `/api/plugin-host/emby/episodes` | 读取 Emby 缺集：按实例、TMDB 剧集和季数读取已有集与缺集，不返回地址、密钥或路径。 | 读取 | 是 |
| GET | `/api/plugin-host/emby/instances` | 列出 Emby 实例：列出可供插件选择的已启用 Emby 实例，不返回服务器地址或 API Key。 | 读取 | 是 |
| GET | `/api/plugin-host/emby/items` | 查询 Emby 媒体：分页搜索或列出选定 Emby 实例中的安全媒体元数据。 | 读取 | 是 |
| GET | `/api/plugin-host/emby/items/:id` | 读取 Emby 媒体详情：读取选定 Emby 实例中的一条安全媒体元数据。 | 读取 | 是 |
| GET | `/api/plugin-host/emby/libraries` | 读取 Emby 媒体库：读取选定 Emby 实例的媒体库名称和类型，不返回媒体路径。 | 读取 | 是 |
| GET | `/api/plugin-host/emby/stats` | 读取 Emby 统计：读取选定 Emby 实例的媒体数量和在线统计。 | 读取 | 是 |
| POST | `/api/emby-control/items/:id/refresh` | 刷新 Emby 媒体：刷新一个 Emby 媒体的元数据。 | 写入 | 是 |
| POST | `/api/emby-control/library/refresh` | 刷新 Emby 媒体库：刷新 Emby 媒体库。 | 写入 | 是 |

## files

| 方法 | 路径模板 | 用途 | 风险 | 宿主管理凭据 |
| --- | --- | --- | --- | --- |
| DELETE | `/api/local-files` | 删除文件：删除文件或目录。 | 删除或不可逆操作 | 否 |
| GET | `/api/local-dirs` | 浏览可选目录：读取文件管理器可用目录。 | 读取 | 否 |
| GET | `/api/local-files` | 列出文件：列出本地挂载或 CD2 挂载目录中的文件。 | 读取 | 否 |
| GET | `/api/local-files/batch-status` | 查询文件任务：查询批量文件任务状态。 | 读取 | 否 |
| GET | `/api/local-files/organize-options` | 读取整理选项：读取可用的整理目标和规则。 | 读取 | 否 |
| GET | `/api/local-files/raw` | 读取文件内容：读取文件管理器中单个文件的内容（最大 10MB）。 | 读取 | 否 |
| GET | `/api/local-files/search` | 搜索文件：在文件管理器中按名称搜索文件。 | 读取 | 否 |
| GET | `/api/local-files/tree` | 读取目录树：读取本地挂载或 CD2 挂载目录树。 | 读取 | 否 |
| POST | `/api/library/check-owned` | 检查媒体库是否已存在：按 TMDB 信息检查媒体是否已入库。 | 读取 | 是 |
| POST | `/api/local-files/batch` | 批量管理文件：批量复制、移动或删除文件。 | 删除或不可逆操作 | 否 |
| POST | `/api/local-files/copy` | 复制文件：按宿主规则在本地挂载或 CD2 之间复制文件。 | 写入 | 否 |
| POST | `/api/local-files/mkdir` | 创建目录：在文件管理器中创建目录。 | 写入 | 否 |
| POST | `/api/local-files/move` | 移动文件：按宿主规则在本地挂载或 CD2 之间移动文件。 | 删除或不可逆操作 | 否 |
| POST | `/api/local-files/organize` | 整理文件：调用宿主文件整理能力。 | 删除或不可逆操作 | 否 |
| POST | `/api/local-files/recognize` | 识别媒体文件：调用宿主识别能力分析文件。 | 写入 | 否 |
| POST | `/api/local-files/rename` | 重命名文件：重命名文件或目录。 | 删除或不可逆操作 | 否 |
| POST | `/api/local-files/rename/execute` | 执行批量重命名：执行批量重命名。 | 删除或不可逆操作 | 否 |
| POST | `/api/local-files/rename/preview` | 预览重命名：预览批量重命名结果。 | 读取 | 否 |
| POST | `/api/local-files/scrape` | 刮削文件：调用宿主刮削能力处理文件。 | 写入 | 否 |

## history

| 方法 | 路径模板 | 用途 | 风险 | 宿主管理凭据 |
| --- | --- | --- | --- | --- |
| GET | `/api/history` | 读取操作历史：读取宿主操作历史记录。 | 读取 | 否 |
| GET | `/api/history/stats` | 读取历史统计：读取操作历史统计。 | 读取 | 否 |

## notifications

| 方法 | 路径模板 | 用途 | 风险 | 宿主管理凭据 |
| --- | --- | --- | --- | --- |
| POST | `/api/notifications/plugin` | 发送插件通知：通过宿主 Telegram 通知配置反馈插件任务结果。 | 写入 | 是 |

## organize

| 方法 | 路径模板 | 用途 | 风险 | 宿主管理凭据 |
| --- | --- | --- | --- | --- |
| DELETE | `/api/organize/history/:id` | 删除整理历史：删除一条整理历史记录。 | 删除或不可逆操作 | 否 |
| DELETE | `/api/organize/rules/:id` | 删除整理规则：删除一条整理规则。 | 删除或不可逆操作 | 否 |
| GET | `/api/organize/categories` | 读取整理分类：读取整理分类列表。 | 读取 | 否 |
| GET | `/api/organize/categories/:id` | 读取整理分类详情：读取一个整理分类的详情。 | 读取 | 否 |
| GET | `/api/organize/category-templates` | 读取分类模板：读取整理分类模板。 | 读取 | 否 |
| GET | `/api/organize/config` | 读取整理配置：读取文件整理配置。 | 读取 | 否 |
| GET | `/api/organize/history` | 读取整理历史：读取文件整理历史。 | 读取 | 否 |
| GET | `/api/organize/history/:id/detail` | 读取整理详情：读取一条整理历史详情。 | 读取 | 否 |
| GET | `/api/organize/history/:id/manual-organize-context` | 读取手动整理上下文：读取一条历史记录的手动整理上下文。 | 读取 | 否 |
| GET | `/api/organize/jobs/:job_id/progress` | 读取整理进度：读取一个整理任务的进度。 | 读取 | 否 |
| GET | `/api/organize/queue` | 读取整理队列：读取待整理队列。 | 读取 | 否 |
| GET | `/api/organize/rules` | 读取整理规则：读取文件整理规则列表。 | 读取 | 否 |
| GET | `/api/organize/template-variables` | 读取模板变量：读取整理路径模板可用变量。 | 读取 | 否 |
| GET | `/api/organize/tmdb-cache/stats` | 读取 TMDB 缓存统计：读取整理模块的 TMDB 缓存统计。 | 读取 | 是 |
| GET | `/api/organize/tmdb/search` | 整理模块搜索 TMDB：使用宿主 TMDB 凭据搜索媒体。 | 读取 | 是 |
| GET | `/api/organize/wash-version/default` | 读取洗版默认配置：读取默认洗版配置。 | 读取 | 否 |
| POST | `/api/organize/history/:id/manual-organize` | 手动整理：对一条历史记录执行手动整理。 | 写入 | 否 |
| POST | `/api/organize/history/:id/rename-source` | 重命名整理来源：修正一条历史记录的来源名称。 | 写入 | 否 |
| POST | `/api/organize/retry-failed` | 重试失败整理：重试失败的整理任务。 | 写入 | 否 |
| POST | `/api/organize/rules` | 创建整理规则：创建文件整理规则。 | 写入 | 否 |
| POST | `/api/organize/rules/:id/scan` | 扫描整理规则：扫描一条整理规则的待处理文件。 | 写入 | 否 |
| POST | `/api/organize/rules/:id/submit` | 提交整理任务：提交一条整理规则的执行任务。 | 写入 | 否 |
| POST | `/api/organize/rules/:id/trigger` | 触发整理规则：立即执行一条整理规则。 | 写入 | 否 |
| PUT | `/api/organize/rules/:id` | 更新整理规则：更新一条整理规则。 | 写入 | 否 |

## plugin-http

| 方法 | 路径模板 | 用途 | 风险 | 宿主管理凭据 |
| --- | --- | --- | --- | --- |
| GET | `/api/plugin-runtime/http/cookies` | 读取站点 Cookie：读取当前插件会话中匹配目标 URL 的 Cookie。 | 读取 | 否 |
| PUT | `/api/plugin-runtime/http/cookies` | 写入站点 Cookie：向当前插件会话应用 Set-Cookie 或手动填写的 Cookie。 | 写入 | 否 |
| DELETE | `/api/plugin-runtime/http/cookies` | 清空站点会话：清空当前插件的一个 HTTP Cookie 会话。 | 删除或不可逆操作 | 否 |
| GET | `/api/plugin-runtime/http/cookiecloud` | 读取本地 CookieCloud 概况：读取本地 CookieCloud 的域名、数量和写入版本，不返回全局密码。 | 读取 | 是 |
| POST | `/api/plugin-runtime/http/cookiecloud/import` | 导入本地 CookieCloud：把指定域名的 Cookie 复制到当前插件会话。 | 读取 | 是 |
| POST | `/api/plugin-runtime/http/cookiecloud/export` | 写回本地 CookieCloud：按指定域名合并写回共享 CookieCloud，并检查版本防止覆盖并发上传。 | 删除或不可逆操作 | 是 |
| POST | `/api/plugin-runtime/http/render` | 按需渲染站点页面：使用已配置的 FlareSolverr 取页并保存当前插件会话 Cookie。 | 读取 | 是 |
| GET | `/api/plugin-runtime/http/sites` | 读取自定义站点：读取当前插件安装后配置的站点地址。 | 读取 | 否 |
| PUT | `/api/plugin-runtime/http/sites` | 保存自定义站点：安装后添加或修改站点地址，也用于选择共享 CookieCloud 的站点范围。 | 写入 | 否 |
| DELETE | `/api/plugin-runtime/http/sites` | 删除自定义站点：删除一个自定义地址并移除其 CookieCloud 范围，不删除共享数据。 | 写入 | 否 |

## plugin-runtime

| 方法 | 路径模板 | 用途 | 风险 | 宿主管理凭据 |
| --- | --- | --- | --- | --- |
| GET | `/api/plugin-runtime/storage` | 分页列出插件存储：按键游标返回当前安装的存储元数据，不读取值。 | 读取 | 否 |
| GET | `/api/plugin-runtime/storage-usage` | 查询插件存储用量：读取当前安装的键数、JSON 字节用量与配额，包含页面偏好。 | 读取 | 否 |

## rules

| 方法 | 路径模板 | 用途 | 风险 | 宿主管理凭据 |
| --- | --- | --- | --- | --- |
| DELETE | `/api/rules/:id` | 删除同步规则：删除一条同步规则。 | 删除或不可逆操作 | 否 |
| DELETE | `/api/rules/:id/tree` | 清空规则目录树：清空一条同步规则已生成的目录树。 | 删除或不可逆操作 | 否 |
| GET | `/api/rules` | 读取同步规则：读取云盘同步规则列表。 | 读取 | 否 |
| GET | `/api/rules/:id/tree/stats` | 读取规则目录统计：读取一条同步规则的目录树统计。 | 读取 | 否 |
| POST | `/api/rules` | 创建同步规则：创建云盘同步规则。 | 写入 | 否 |
| POST | `/api/rules/:id/clean-orphans` | 清理孤立文件：清理一条规则产生的孤立文件。 | 删除或不可逆操作 | 否 |
| POST | `/api/rules/:id/full-sync` | 全量同步规则：全量执行一条同步规则。 | 写入 | 否 |
| POST | `/api/rules/:id/generate-strm` | 生成 STRM：为一条同步规则生成 STRM 文件。 | 写入 | 否 |
| POST | `/api/rules/:id/sync` | 同步规则：执行一条同步规则。 | 写入 | 否 |
| POST | `/api/rules/:id/sync-metadata` | 同步元数据：同步一条规则的元数据。 | 写入 | 否 |
| POST | `/api/rules/:id/toggle` | 启停同步规则：启用或停用一条同步规则。 | 写入 | 否 |
| POST | `/api/rules/sync-all` | 同步全部规则：执行全部同步规则。 | 写入 | 否 |
| PUT | `/api/rules/:id` | 更新同步规则：更新一条同步规则。 | 写入 | 否 |

## scheduler

| 方法 | 路径模板 | 用途 | 风险 | 宿主管理凭据 |
| --- | --- | --- | --- | --- |
| GET | `/api/scheduler/jobs` | 读取宿主任务：读取宿主定时任务列表。 | 读取 | 否 |
| POST | `/api/scheduler/jobs/trigger` | 触发宿主任务：立即触发一个宿主定时任务。 | 写入 | 否 |

## subscriptions

| 方法 | 路径模板 | 用途 | 风险 | 宿主管理凭据 |
| --- | --- | --- | --- | --- |
| DELETE | `/api/subscribe/pool/intents/:id` | 取消聚合订阅：取消一条聚合订阅意图。 | 删除或不可逆操作 | 否 |
| GET | `/api/subscribe/air-calendar` | 读取追剧日历：读取订阅播出日历。 | 读取 | 否 |
| GET | `/api/subscribe/entry-settings` | 读取订阅入口设置：读取订阅入口设置。 | 读取 | 否 |
| GET | `/api/subscribe/history` | 读取订阅历史：读取订阅执行历史。 | 读取 | 否 |
| GET | `/api/subscribe/library-settings` | 读取媒体库订阅设置：读取媒体库订阅设置。 | 读取 | 否 |
| GET | `/api/subscribe/pool/intents` | 查询聚合订阅：读取聚合订阅意图。 | 读取 | 否 |
| GET | `/api/subscribe/pool/intents/:id` | 读取聚合订阅：读取一条聚合订阅意图。 | 读取 | 否 |
| GET | `/api/subscribe/pt-search-site-selection` | 读取订阅站点选择：读取订阅搜索使用的站点选择。 | 读取 | 否 |
| GET | `/api/subscribe/records` | 查询订阅记录：读取宿主订阅记录。 | 读取 | 否 |
| PATCH | `/api/subscribe/pool/intents/:id/episodes` | 更新订阅集数：更新聚合订阅需要的集数。 | 写入 | 否 |
| POST | `/api/subscribe/batch-delete` | 批量删除订阅：批量删除订阅记录。 | 删除或不可逆操作 | 否 |
| POST | `/api/subscribe/delete-by-media` | 按媒体删除订阅：按媒体删除订阅记录。 | 删除或不可逆操作 | 否 |
| POST | `/api/subscribe/pool/intents` | 创建聚合订阅：创建聚合订阅意图。 | 写入 | 否 |
| PUT | `/api/subscribe/entry-settings` | 更新订阅入口设置：更新订阅入口设置。 | 写入 | 否 |
| PUT | `/api/subscribe/library-settings` | 更新媒体库订阅设置：更新媒体库订阅设置。 | 写入 | 否 |
| PUT | `/api/subscribe/pt-search-site-selection` | 更新订阅站点选择：更新订阅搜索使用的站点选择。 | 写入 | 否 |

## tasks

| 方法 | 路径模板 | 用途 | 风险 | 宿主管理凭据 |
| --- | --- | --- | --- | --- |
| GET | `/api/tasks` | 列出后台任务：读取宿主后台任务列表。 | 读取 | 否 |
| GET | `/api/tasks/:id` | 读取任务详情：读取一个后台任务的详情。 | 读取 | 否 |
| GET | `/api/workqueue/stats` | 读取工作队列统计：读取宿主工作队列统计。 | 读取 | 否 |
| POST | `/api/tasks/:id/cancel` | 取消任务：取消一个后台任务。 | 写入 | 否 |

## tmdb

| 方法 | 路径模板 | 用途 | 风险 | 宿主管理凭据 |
| --- | --- | --- | --- | --- |
| GET | `/api/tmdb/discover/movie` | 发现 TMDB 电影：按条件发现电影。 | 读取 | 是 |
| GET | `/api/tmdb/discover/tv` | 发现 TMDB 剧集：按条件发现剧集。 | 读取 | 是 |
| GET | `/api/tmdb/genres` | 查询 TMDB 类型：读取电影和剧集类型。 | 读取 | 是 |
| GET | `/api/tmdb/movie/:id` | 查询 TMDB 电影：读取电影详情。 | 读取 | 是 |
| GET | `/api/tmdb/search` | 搜索 TMDB：搜索电影、剧集和人物。 | 读取 | 是 |
| GET | `/api/tmdb/trending` | 查询 TMDB 趋势：读取电影或剧集趋势。 | 读取 | 是 |
| GET | `/api/tmdb/tv/:id` | 查询 TMDB 剧集：读取剧集详情和季度信息。 | 读取 | 是 |
