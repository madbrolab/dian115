<!-- markdownlint-disable MD013 MD024 MD033 MD036 -->

# Telegram 通知模板设计器使用手册

本文档对应 Dian115 当前的 39 个独立 Telegram 通知模板，说明模板语法、图片策略、Telegram 富文本、导入导出，以及每个通知事件实际可用的变量。变量合同以服务端为准，设计器只显示当前选中事件能够接收的字段。

> 重要：39 个事件没有通用业务模板，也不会从通知大类继承变量。请勿把一个事件的变量直接复制到另一个事件；导入时服务端会按事件合同逐项校验。

## 快速使用

1. 进入 **插件中心 -> 通知插件 -> 推送模板设计器**。
2. 选择一个具体通知事件，例如 `playback_start`，再编辑它自己的标题和正文。
3. 从右侧“可用变量”点击插入。使用“可选行”可自动生成 `{% if variable %}...{% endif %}`，变量为空时整行不显示。
4. 在 Telegram 富文本预览中检查标题、换行、引用和链接。
5. 自定义图片必须先通过预览校验；最后点击页面底部“保存通知配置”才会正式生效。

## 模板语法

| 目的 | 写法 | 说明 |
| --- | --- | --- |
| 输出变量 | `{{ title }}` | 变量不存在或为空时输出空字符串。 |
| 设置默认文字 | `{{ title or '未知标题' }}` | 左侧为空、`0` 或 `false` 时使用后备值；后备值也可以是另一个变量。 |
| 可选内容 | `{% if rating %}评分：{{ rating }}{% endif %}` | 条件不成立时整段隐藏。 |
| 多条件 | `{% if year and rating %}...{% endif %}` | 支持 `and`、`or`、`not`。 |
| 比较 | `{% if media_type == '电视剧' %}...{% endif %}` | 支持 `==` 与 `!=`。 |
| 多分支 | `{% if success_count %}成功{% elif failed_count %}失败{% else %}无结果{% endif %}` | 支持任意数量的 `elif`、一个可选的 `else`，也支持嵌套。 |

模板故意不支持过滤器、函数调用、循环、include 或任意代码。不要直接书写 HTML 标签；Telegram 格式必须使用下方受控变量。

## Telegram 富文本变量

下列格式变量对全部 39 个事件可用。所有“开始 / 结束”变量必须成对、按正确顺序闭合，不能交叉嵌套。

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `tg_bold_start` | 粗体开始 | 从这里开始加粗，必须与“粗体结束”成对使用 | `{{ tg_bold_start }}重点{{ tg_bold_end }}` |
| `tg_bold_end` | 粗体结束 | 结束粗体范围 | `{{ tg_bold_end }}` |
| `tg_italic_start` | 斜体开始 | 从这里开始使用斜体 | `{{ tg_italic_start }}说明{{ tg_italic_end }}` |
| `tg_italic_end` | 斜体结束 | 结束斜体范围 | `{{ tg_italic_end }}` |
| `tg_underline_start` | 下划线开始 | 从这里开始添加下划线 | `{{ tg_underline_start }}提醒{{ tg_underline_end }}` |
| `tg_underline_end` | 下划线结束 | 结束下划线范围 | `{{ tg_underline_end }}` |
| `tg_strike_start` | 删除线开始 | 从这里开始添加删除线 | `{{ tg_strike_start }}旧状态{{ tg_strike_end }}` |
| `tg_strike_end` | 删除线结束 | 结束删除线范围 | `{{ tg_strike_end }}` |
| `tg_spoiler_start` | 剧透开始 | 内容点击后才显示，适合隐藏敏感信息 | `{{ tg_spoiler_start }}隐藏内容{{ tg_spoiler_end }}` |
| `tg_spoiler_end` | 剧透结束 | 结束剧透范围 | `{{ tg_spoiler_end }}` |
| `tg_code_start` | 行内代码开始 | 使用等宽字体显示一小段内容 | `{{ tg_code_start }}/media/path{{ tg_code_end }}` |
| `tg_code_end` | 行内代码结束 | 结束行内代码范围 | `{{ tg_code_end }}` |
| `tg_pre_start` | 代码块开始 | 多行等宽文本块，适合日志、路径树和清单 | `{{ tg_pre_start }}第一行<br>第二行{{ tg_pre_end }}` |
| `tg_pre_end` | 代码块结束 | 结束多行代码块 | `{{ tg_pre_end }}` |
| `tg_quote_start` | 引用开始 | 单行或多行普通引用；结束位置由“引用结束”决定 | `{{ tg_quote_start }}一行引用{{ tg_quote_end }}` |
| `tg_quote_end` | 引用结束 | 结束普通引用范围 | `{{ tg_quote_end }}` |
| `tg_expandable_quote_start` | 折叠引用开始 | 默认可折叠的多行引用，适合长简介、错误和文件列表 | `{{ tg_expandable_quote_start }}第一行<br>第二行{{ tg_expandable_quote_end }}` |
| `tg_expandable_quote_end` | 折叠引用结束 | 结束可折叠引用范围 | `{{ tg_expandable_quote_end }}` |
| `tg_newline` | 换行 | 在当前位置插入一个换行 | `第一行{{ tg_newline }}第二行` |
| `tg_blankline` | 空行 | 在当前位置插入一个空白分隔行 | `第一段{{ tg_blankline }}第二段` |

推荐写法：长路径、错误详情和文件树使用 `tg_expandable_quote_start/end`；短状态说明使用普通引用；分享码等敏感内容使用 `tg_spoiler_start/end`；短 ID 或短路径使用行内代码。

## TMDB 与 IMDb 文字链接

- `{{ tmdb_link }}` 和 `{{ imdb_link }}` 分别显示为可点击的“TMDB”和“IMDb”，不会把真实 URL 打印到正文。
- 自定义链接文字使用 `{{ tmdb_link_start }}查看 TMDB 详情{{ tmdb_link_end }}`，IMDb 同理。
- 只有当前事件实际拥有对应媒体身份时才会显示这些变量；应始终放在 `if` 条件中。
- 剧集、季和单集通知都使用整部剧（Series）的 TMDB / IMDb 身份，不使用季图片或单集详情页。

## 自动画质点评

`quality_comment` 会根据真实质量字段生成一句简短评价，识别优先级为 **Dolby Vision / DoVi / DV -> HDR / HLG -> 4K / 2160P / UHD -> 1080P / Full HD / FHD / 1920x1080**。一条通知只使用最高优先级命中的一档，建议放在条件块中：

`{% if quality_comment %}{{ tg_quote_start }}✨ {{ quality_comment }}{{ tg_quote_end }}{% endif %}`

当前支持该变量的事件：`playback_start`、`playback_stop`、`media_library_add`、`media_library_update`、`media_library_delete`、`library_organize_success`、`library_organize_skip`、`media_auto_share`。

这 8 个事件在模板设计器中各自拥有独立的 Dolby Vision、HDR、4K、1080P 点评文案。系统提供默认值，用户可逐条修改；清空某一档并保存后，该事件命中这一档时不再显示点评。恢复点评默认只影响当前事件，不会覆盖其他事件。

## 图片策略

每个事件都独立选择图片模式：

| 模式 | 行为 |
| --- | --- |
| 自动（`auto`） | 有明确 TMDB 图片时使用 TMDB 图片；否则使用该事件自己的后端默认图。默认图真实地址不会显示在前端或导出包中。 |
| 自定义（`custom`） | 无 TMDB 图片时使用用户填写并验证成功的公网图片链接。链接必须在 3 秒内成功返回可预览图片，验证失败不能保存或导入。 |
| 关闭（`disabled`） | 无 TMDB 图片时发送纯文本，不附带默认图或自定义图。明确的 TMDB 图片仍优先。 |

`poster_url` / `image_url` 是部分媒体事件提供给正文模板的业务字段，不等于模板头图设置。将它们写进正文会显示 URL；通常应使用图片模式控制头图。

## 导入与导出

- **全量导出**：导出全部 39 个独立事件的标题、正文和图片策略。
- **选择导出**：只导出勾选事件，适合分享一组模板。
- 导出包不包含 Telegram Token、白名单、通知开关或后端默认图地址。
- 导入后先逐项审核预览并选择；自定义图片必须重新通过 3 秒校验。
- “应用选择”只写入当前页面编辑状态，仍需点击“保存通知配置”才会生效。
- 导入包中的事件键必须唯一；未知事件、非法变量、未配对富文本或错误模板语法会被拒绝。

## 事件目录

### 播放通知（2）

- [开始播放 `playback_start`](#playback_start)
- [停止播放 `playback_stop`](#playback_stop)

### 入库通知（3）

- [资源入库 `media_library_add`](#media_library_add)
- [媒体更新 `media_library_update`](#media_library_update)
- [媒体删除 `media_library_delete`](#media_library_delete)

### Emby 账户安全（7）

- [用户登录成功 `emby_user_authenticated`](#emby_user_authenticated)
- [用户登录失败 `emby_user_authentication_failed`](#emby_user_authentication_failed)
- [用户被锁定 `emby_user_locked_out`](#emby_user_locked_out)
- [用户已创建 `emby_user_created`](#emby_user_created)
- [用户已删除 `emby_user_deleted`](#emby_user_deleted)
- [用户密码更改 `emby_user_password_changed`](#emby_user_password_changed)
- [用户策略更新 `emby_user_policy_updated`](#emby_user_policy_updated)

### 文件整理通知（6）

- [整理完成 `library_organize_success`](#library_organize_success)
- [整理跳过 `library_organize_skip`](#library_organize_skip)
- [整理失败 `library_organize_fail`](#library_organize_fail)
- [质量扫描 `library_quality_scan`](#library_quality_scan)
- [缺集扫描 `library_missing_scan`](#library_missing_scan)
- [STRM 生成 `strm_generate`](#strm_generate)

### 文件操作通知（8）

- [分享转存 `share_receive`](#share_receive)
- [离线下载 `offline_download`](#offline_download)
- [TG 自动转存 `tg_auto_transfer`](#tg_auto_transfer)
- [TG 自动离线 `tg_auto_offline`](#tg_auto_offline)
- [TG 视频下载 `tg_video_download`](#tg_video_download)
- [多号云迁移 `account_migration`](#account_migration)
- [ED2K 任务 `ed2k_task`](#ed2k_task)
- [媒体自动分享 `media_auto_share`](#media_auto_share)

### 账号状态（4）

- [Cookie 失效 `account_cookie_invalid`](#account_cookie_invalid)
- [账号切换 `account_switched`](#account_switched)
- [115 签到 `account_checkin`](#account_checkin)
- [癫影签到 `dianying_checkin`](#dianying_checkin)

### 容器更新（4）

- [容器更新检查 `container_update_check`](#container_update_check)
- [容器更新结果 `container_update_result`](#container_update_result)
- [容器通知测试 `container_update_test`](#container_update_test)
- [Dian115 自更新 `dian115_self_update`](#dian115_self_update)

### Clash 监控（2）

- [Clash 监控日报 `proxy_health_daily_report`](#proxy_health_daily_report)
- [Clash 测试报告 `proxy_health_test_report`](#proxy_health_test_report)

### 订阅通知（3）

- [添加订阅 `subscribe_added`](#subscribe_added)
- [订阅完成 `subscribe_landed`](#subscribe_landed)
- [订阅部分完成 `subscribe_partial`](#subscribe_partial)

## 39 个独立事件变量与默认模板

<a id="playback_start"></a>

### 开始播放 `playback_start`

Emby 客户端开始播放媒体。所属大类：`playback`（播放通知）；聚合：**不支持**；TMDB 头图来源：**可能有**。

图片规则：明确的 TMDB 海报始终优先；自动模式无 TMDB 时使用“开始播放”默认图，自定义模式改用已验证链接，关闭模式无 TMDB 时发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
▶️ 开始播放｜{{ show_name or title }}{% if season_episode %} · {{ season_episode }}{% endif %}
```

**正文**

```jinja
{% if user_name or client %}👤 {{ user_name or '未知用户' }}{% if client %} · {{ client }}{% endif %}
{% endif %}{% if quality %}🎞️ {{ quality }}
{% endif %}{% if device_name or ip %}📺 {{ device_name or '未知设备' }}{% if ip %} · {{ ip }}{% endif %}
{% endif %}{% if emby_instance_name %}🖥️ {{ emby_instance_name }}
{% endif %}🕐 {{ now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |

#### 媒体

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `title` | 标题 | 媒体、任务或资源标题 | `三体` |
| `show_name` | 剧名 | 剧集聚合时使用的系列名称 | `三体` |
| `raw_title` | 原始标题 | 规范化前的标题，可能包含年份或 TMDB 标记 | `三体 (2023) -{tmdbid=204541}` |
| `raw_show_name` | 原始剧名 | 规范化前的系列名称 | `三体 (2023) -{tmdbid=204541}` |
| `title_year` | 标题年份 | 自动组合的“标题 (年份)” | `三体 (2023)` |
| `media_type` | 媒体类型 | 电影、电视剧或音乐 | `电视剧` |
| `year` | 年份 | 媒体发行年份 | `2023` |
| `season_episode` | 季集 | 单集或聚合后的季集范围 | `S01E01-E03` |
| `rating` | 评分 | 媒体评分 | `8.7` |
| `genres` | 类型标签 | 媒体类型或标签 | `剧情 / 科幻` |
| `overview` | 简介 | 媒体简介，可能为空 | `人类文明首次收到来自宇宙深处的信息。` |
| `poster_url` | 海报地址 | 通知卡片使用的海报 URL | `https://image.tmdb.org/t/p/w500/demo.jpg` |
| `image_url` | 图片地址 | 通知图片 URL，通常与 poster_url 相同 | `https://image.tmdb.org/t/p/w500/demo.jpg` |
| `tmdb_id` | TMDB ID | TMDB 媒体编号 | `204541` |
| `tmdb_media_type` | TMDB 类型 | movie 或 tv | `tv` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `type` | 类型别名 | media_type 的兼容别名 | `电视剧` |
| `season_fmt` | 季集别名 | season_episode 的兼容别名 | `S01E01-E03` |
| `vote_average` | 评分别名 | rating 的兼容别名 | `8.7` |
| `category` | 类别 | 优先为媒体库名称，否则回退到类型标签 | `电视剧` |
| `instance_name` | 实例名称别名 | emby_instance_name 的兼容别名 | `客厅 Emby` |
| `username` | 用户名别名 | user_name 或 account_name 的兼容别名 | `Alice` |
| `resource_term` | 质量别名 | quality 的兼容别名 | `2160P / WEB-DL / H.265` |

#### 媒体链接

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `tmdb_link` | TMDB 文字链接 | 显示为可点击的“TMDB”，真实详情页地址不会显示在消息正文中 | `TMDB（可点击）` |
| `tmdb_link_start` | TMDB 自定义文字开始 | 为自定义文字添加TMDB详情页超链接，必须与结束变量成对使用 | `{{ tmdb_link_start }}查看 TMDB{{ tmdb_link_end }}` |
| `tmdb_link_end` | TMDB 自定义文字结束 | 结束TMDB文字超链接范围 | `{{ tmdb_link_end }}` |
| `imdb_id` | IMDb ID | 当前电影或整部剧的 IMDb title ID；缺失时为空 | `tt13016388` |
| `imdb_link` | IMDb 文字链接 | 显示为可点击的“IMDb”，真实详情页地址不会显示在消息正文中 | `IMDb（可点击）` |
| `imdb_link_start` | IMDb 自定义文字开始 | 为自定义文字添加IMDb详情页超链接，必须与结束变量成对使用 | `{{ imdb_link_start }}查看 IMDb{{ imdb_link_end }}` |
| `imdb_link_end` | IMDb 自定义文字结束 | 结束IMDb文字超链接范围 | `{{ imdb_link_end }}` |

#### Emby 实例

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `emby_instance_id` | Emby 实例 ID | Dian115 配置中的 Emby 实例 ID | `2` |
| `emby_instance_name` | Emby 实例名称 | Dian115 多实例配置里的名称；推荐用它区分服务器 | `客厅 Emby` |
| `emby_server_name` | Emby 服务器名 | Emby/Madby 事件自报的服务器名称 | `MediaServer` |
| `server_name` | 服务器名 | 优先为配置的实例名，否则为 Emby 自报名称 | `客厅 Emby` |
| `proxy_id` | 代理实例 ID | 与 emby_instance_id 相同的内部路由 ID | `2` |

#### 事件

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `event_type` | 事件名称 | 可读事件名称，例如开始播放或新入库 | `新入库` |

#### 播放

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `user_id` | 用户 ID | Emby 用户唯一标识 | `user-100` |
| `user_name` | 用户 | Emby 播放或安全事件用户 | `Alice` |
| `session_id` | 播放会话 ID | Emby 播放会话唯一标识 | `session-300` |
| `client` | 客户端 | Emby 客户端名称 | `Emby for Android` |
| `client_info` | 客户端信息 | 客户端名称原始值；client 的来源或兼容字段 | `Emby for Android TV` |
| `user_agent` | User-Agent | 播放请求上报的客户端 User-Agent | `Emby/3.4 Android/14` |
| `device_id` | 设备 ID | Emby 设备唯一标识 | `device-200` |
| `device_name` | 设备 | 播放或登录设备名称 | `客厅电视` |
| `ip` | 网络地址 | 播放客户端远端地址 | `192.168.1.20` |
| `percentage` | 播放进度 | 不带百分号的播放进度 | `42.5` |
| `position_ticks` | 播放位置 ticks | Emby 上报的原始播放位置 | `18000000000` |
| `runtime_ticks` | 媒体时长 ticks | Emby 上报的媒体总时长 | `42000000000` |

#### 质量

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `resolution` | 分辨率 | 视频分辨率 | `2160P` |
| `video_codec` | 视频编码 | 视频编码 | `H.265` |
| `audio_codec` | 音频编码 | 音频编码 | `DTS-HD MA` |
| `audio_channels` | 音频声道数 | 原始声道数量 | `6` |
| `audio_channels_label` | 声道 | 格式化后的声道，例如 5.1 | `5.1` |
| `hdr_type` | HDR | HDR/Dolby Vision 类型 | `Dolby Vision` |
| `source_type` | 片源 | WEB-DL、BluRay 等片源类型 | `WEB-DL` |
| `frame_rate` | 帧率 | 视频帧率 | `23.976fps` |
| `container` | 封装格式 | MKV、MP4 等媒体封装格式 | `MKV` |
| `quality` | 质量摘要 | 自动拼接分辨率、片源、编码、HDR 等 | `2160P / WEB-DL / H.265 / Dolby Vision` |
| `quality_comment` | 画质点评 | 按 Dolby Vision、HDR、4K、1080P 优先级生成；四档文案可在当前模板中独立修改或清空关闭 | `Dolby Vision 动态画面：逐场景优化明暗与色彩，明暗过渡更细腻。` |

<a id="playback_stop"></a>

### 停止播放 `playback_stop`

Emby 播放会话停止并报告最终进度。所属大类：`playback`（播放通知）；聚合：**不支持**；TMDB 头图来源：**可能有**。

图片规则：明确的 TMDB 海报始终优先；自动模式无 TMDB 时使用“停止播放”默认图，自定义模式改用已验证链接，关闭模式无 TMDB 时发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
⏹️ 停止播放｜{{ show_name or title }}{% if season_episode %} · {{ season_episode }}{% endif %}
```

**正文**

```jinja
{% if percentage %}🏁 最终进度 {{ percentage }}%
{% endif %}{% if user_name or device_name %}👤 {{ user_name or '未知用户' }}{% if device_name %} · {{ device_name }}{% endif %}
{% endif %}{% if client %}📱 {{ client }}
{% endif %}{% if emby_instance_name %}🖥️ {{ emby_instance_name }}
{% endif %}🕐 {{ now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |

#### 媒体

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `title` | 标题 | 媒体、任务或资源标题 | `三体` |
| `show_name` | 剧名 | 剧集聚合时使用的系列名称 | `三体` |
| `raw_title` | 原始标题 | 规范化前的标题，可能包含年份或 TMDB 标记 | `三体 (2023) -{tmdbid=204541}` |
| `raw_show_name` | 原始剧名 | 规范化前的系列名称 | `三体 (2023) -{tmdbid=204541}` |
| `title_year` | 标题年份 | 自动组合的“标题 (年份)” | `三体 (2023)` |
| `media_type` | 媒体类型 | 电影、电视剧或音乐 | `电视剧` |
| `year` | 年份 | 媒体发行年份 | `2023` |
| `season_episode` | 季集 | 单集或聚合后的季集范围 | `S01E01-E03` |
| `rating` | 评分 | 媒体评分 | `8.7` |
| `genres` | 类型标签 | 媒体类型或标签 | `剧情 / 科幻` |
| `overview` | 简介 | 媒体简介，可能为空 | `人类文明首次收到来自宇宙深处的信息。` |
| `poster_url` | 海报地址 | 通知卡片使用的海报 URL | `https://image.tmdb.org/t/p/w500/demo.jpg` |
| `image_url` | 图片地址 | 通知图片 URL，通常与 poster_url 相同 | `https://image.tmdb.org/t/p/w500/demo.jpg` |
| `tmdb_id` | TMDB ID | TMDB 媒体编号 | `204541` |
| `tmdb_media_type` | TMDB 类型 | movie 或 tv | `tv` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `type` | 类型别名 | media_type 的兼容别名 | `电视剧` |
| `season_fmt` | 季集别名 | season_episode 的兼容别名 | `S01E01-E03` |
| `vote_average` | 评分别名 | rating 的兼容别名 | `8.7` |
| `category` | 类别 | 优先为媒体库名称，否则回退到类型标签 | `电视剧` |
| `instance_name` | 实例名称别名 | emby_instance_name 的兼容别名 | `客厅 Emby` |
| `username` | 用户名别名 | user_name 或 account_name 的兼容别名 | `Alice` |
| `resource_term` | 质量别名 | quality 的兼容别名 | `2160P / WEB-DL / H.265` |

#### 媒体链接

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `tmdb_link` | TMDB 文字链接 | 显示为可点击的“TMDB”，真实详情页地址不会显示在消息正文中 | `TMDB（可点击）` |
| `tmdb_link_start` | TMDB 自定义文字开始 | 为自定义文字添加TMDB详情页超链接，必须与结束变量成对使用 | `{{ tmdb_link_start }}查看 TMDB{{ tmdb_link_end }}` |
| `tmdb_link_end` | TMDB 自定义文字结束 | 结束TMDB文字超链接范围 | `{{ tmdb_link_end }}` |
| `imdb_id` | IMDb ID | 当前电影或整部剧的 IMDb title ID；缺失时为空 | `tt13016388` |
| `imdb_link` | IMDb 文字链接 | 显示为可点击的“IMDb”，真实详情页地址不会显示在消息正文中 | `IMDb（可点击）` |
| `imdb_link_start` | IMDb 自定义文字开始 | 为自定义文字添加IMDb详情页超链接，必须与结束变量成对使用 | `{{ imdb_link_start }}查看 IMDb{{ imdb_link_end }}` |
| `imdb_link_end` | IMDb 自定义文字结束 | 结束IMDb文字超链接范围 | `{{ imdb_link_end }}` |

#### Emby 实例

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `emby_instance_id` | Emby 实例 ID | Dian115 配置中的 Emby 实例 ID | `2` |
| `emby_instance_name` | Emby 实例名称 | Dian115 多实例配置里的名称；推荐用它区分服务器 | `客厅 Emby` |
| `emby_server_name` | Emby 服务器名 | Emby/Madby 事件自报的服务器名称 | `MediaServer` |
| `server_name` | 服务器名 | 优先为配置的实例名，否则为 Emby 自报名称 | `客厅 Emby` |
| `proxy_id` | 代理实例 ID | 与 emby_instance_id 相同的内部路由 ID | `2` |

#### 事件

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `event_type` | 事件名称 | 可读事件名称，例如开始播放或新入库 | `新入库` |

#### 播放

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `user_id` | 用户 ID | Emby 用户唯一标识 | `user-100` |
| `user_name` | 用户 | Emby 播放或安全事件用户 | `Alice` |
| `session_id` | 播放会话 ID | Emby 播放会话唯一标识 | `session-300` |
| `client` | 客户端 | Emby 客户端名称 | `Emby for Android` |
| `client_info` | 客户端信息 | 客户端名称原始值；client 的来源或兼容字段 | `Emby for Android TV` |
| `user_agent` | User-Agent | 播放请求上报的客户端 User-Agent | `Emby/3.4 Android/14` |
| `device_id` | 设备 ID | Emby 设备唯一标识 | `device-200` |
| `device_name` | 设备 | 播放或登录设备名称 | `客厅电视` |
| `ip` | 网络地址 | 播放客户端远端地址 | `192.168.1.20` |
| `percentage` | 播放进度 | 不带百分号的播放进度 | `42.5` |
| `position_ticks` | 播放位置 ticks | Emby 上报的原始播放位置 | `18000000000` |
| `runtime_ticks` | 媒体时长 ticks | Emby 上报的媒体总时长 | `42000000000` |

#### 质量

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `resolution` | 分辨率 | 视频分辨率 | `2160P` |
| `video_codec` | 视频编码 | 视频编码 | `H.265` |
| `audio_codec` | 音频编码 | 音频编码 | `DTS-HD MA` |
| `audio_channels` | 音频声道数 | 原始声道数量 | `6` |
| `audio_channels_label` | 声道 | 格式化后的声道，例如 5.1 | `5.1` |
| `hdr_type` | HDR | HDR/Dolby Vision 类型 | `Dolby Vision` |
| `source_type` | 片源 | WEB-DL、BluRay 等片源类型 | `WEB-DL` |
| `frame_rate` | 帧率 | 视频帧率 | `23.976fps` |
| `container` | 封装格式 | MKV、MP4 等媒体封装格式 | `MKV` |
| `quality` | 质量摘要 | 自动拼接分辨率、片源、编码、HDR 等 | `2160P / WEB-DL / H.265 / Dolby Vision` |
| `quality_comment` | 画质点评 | 按 Dolby Vision、HDR、4K、1080P 优先级生成；四档文案可在当前模板中独立修改或清空关闭 | `Dolby Vision 动态画面：逐场景优化明暗与色彩，明暗过渡更细腻。` |

<a id="media_library_add"></a>

### 资源入库 `media_library_add`

Emby 新增媒体；同剧集短窗口内聚合。所属大类：`media_library`（入库通知）；聚合：**支持**；TMDB 头图来源：**可能有**。

图片规则：明确的 TMDB 海报始终优先；自动模式无 TMDB 时使用“资源入库”默认图，自定义模式改用已验证链接，关闭模式无 TMDB 时发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
📥 资源入库｜{{ show_name or title }}{% if season_episode %} · {{ season_episode }}{% endif %}
```

**正文**

```jinja
{% if file_count %}📦 {{ file_count }} 个文件{% if total_size %} · {{ total_size }}{% endif %}
{% elif episode_count %}📺 共 {{ episode_count }} 集
{% elif total_size %}💾 {{ total_size }}
{% endif %}{% if quality %}🎞️ {{ quality }}
{% endif %}{% if year or rating or genres %}ℹ️{% if year %} {{ year }}{% endif %}{% if rating %} · ⭐ {{ rating }}{% endif %}{% if genres %} · {{ genres }}{% endif %}
{% endif %}{% if library_name or emby_instance_name %}🗂️{% if library_name %} {{ library_name }}{% endif %}{% if emby_instance_name %} · {{ emby_instance_name }}{% endif %}
{% endif %}🕐 {{ time_range or now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |

#### 媒体

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `title` | 标题 | 媒体、任务或资源标题 | `三体` |
| `show_name` | 剧名 | 剧集聚合时使用的系列名称 | `三体` |
| `raw_title` | 原始标题 | 规范化前的标题，可能包含年份或 TMDB 标记 | `三体 (2023) -{tmdbid=204541}` |
| `raw_show_name` | 原始剧名 | 规范化前的系列名称 | `三体 (2023) -{tmdbid=204541}` |
| `title_year` | 标题年份 | 自动组合的“标题 (年份)” | `三体 (2023)` |
| `media_type` | 媒体类型 | 电影、电视剧或音乐 | `电视剧` |
| `year` | 年份 | 媒体发行年份 | `2023` |
| `season_episode` | 季集 | 单集或聚合后的季集范围 | `S01E01-E03` |
| `rating` | 评分 | 媒体评分 | `8.7` |
| `genres` | 类型标签 | 媒体类型或标签 | `剧情 / 科幻` |
| `genre_names` | 紧凑类型标签 | 以斜杠拼接的类型标签 | `剧情/科幻` |
| `overview` | 简介 | 媒体简介，可能为空 | `人类文明首次收到来自宇宙深处的信息。` |
| `poster_url` | 海报地址 | 通知卡片使用的海报 URL | `https://image.tmdb.org/t/p/w500/demo.jpg` |
| `image_url` | 图片地址 | 通知图片 URL，通常与 poster_url 相同 | `https://image.tmdb.org/t/p/w500/demo.jpg` |
| `tmdb_id` | TMDB ID | TMDB 媒体编号 | `204541` |
| `tmdb_media_type` | TMDB 类型 | movie 或 tv | `tv` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `type` | 类型别名 | media_type 的兼容别名 | `电视剧` |
| `season_fmt` | 季集别名 | season_episode 的兼容别名 | `S01E01-E03` |
| `vote_average` | 评分别名 | rating 的兼容别名 | `8.7` |
| `category` | 类别 | 优先为媒体库名称，否则回退到类型标签 | `电视剧` |
| `instance_name` | 实例名称别名 | emby_instance_name 的兼容别名 | `客厅 Emby` |
| `resource_term` | 质量别名 | quality 的兼容别名 | `2160P / WEB-DL / H.265` |
| `size` | 大小别名 | 格式化后的 total_size 兼容别名 | `9.25GB` |

#### 媒体链接

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `tmdb_link` | TMDB 文字链接 | 显示为可点击的“TMDB”，真实详情页地址不会显示在消息正文中 | `TMDB（可点击）` |
| `tmdb_link_start` | TMDB 自定义文字开始 | 为自定义文字添加TMDB详情页超链接，必须与结束变量成对使用 | `{{ tmdb_link_start }}查看 TMDB{{ tmdb_link_end }}` |
| `tmdb_link_end` | TMDB 自定义文字结束 | 结束TMDB文字超链接范围 | `{{ tmdb_link_end }}` |
| `imdb_id` | IMDb ID | 当前电影或整部剧的 IMDb title ID；缺失时为空 | `tt13016388` |
| `imdb_link` | IMDb 文字链接 | 显示为可点击的“IMDb”，真实详情页地址不会显示在消息正文中 | `IMDb（可点击）` |
| `imdb_link_start` | IMDb 自定义文字开始 | 为自定义文字添加IMDb详情页超链接，必须与结束变量成对使用 | `{{ imdb_link_start }}查看 IMDb{{ imdb_link_end }}` |
| `imdb_link_end` | IMDb 自定义文字结束 | 结束IMDb文字超链接范围 | `{{ imdb_link_end }}` |

#### 事件

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `event_id` | 事件 ID | Madby/Emby 事件唯一标识 | `evt-20260812-001` |
| `event_type` | 事件名称 | 可读事件名称，例如开始播放或新入库 | `新入库` |
| `event_action` | 事件动作 | 入库、更新、删除等动作 | `新入库` |

#### 状态

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `status` | 媒体状态 | 媒体或任务原始状态 | `Ended` |

#### 入库

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `library_id` | 媒体库 ID | Emby 媒体库编号 | `library-1` |
| `library_name` | 媒体库 | Emby 媒体库名称 | `电视剧` |
| `item_id` | 项目 ID | Emby Item ID；聚合时为首个项目 | `12345` |
| `series_id` | 系列 ID | Emby Series ID | `series-100` |
| `media_source_id` | 媒体源 ID | Emby MediaSource ID | `source-1` |
| `madby_source` | Madby 来源 | Madby 事件来源标识 | `emby` |

#### Emby 实例

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `emby_instance_id` | Emby 实例 ID | Dian115 配置中的 Emby 实例 ID | `2` |
| `emby_instance_name` | Emby 实例名称 | Dian115 多实例配置里的名称；推荐用它区分服务器 | `客厅 Emby` |
| `emby_server_name` | Emby 服务器名 | Emby/Madby 事件自报的服务器名称 | `MediaServer` |
| `server_name` | 服务器名 | 优先为配置的实例名，否则为 Emby 自报名称 | `客厅 Emby` |
| `proxy_id` | 代理实例 ID | 与 emby_instance_id 相同的内部路由 ID | `2` |

#### 质量

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `resolution` | 分辨率 | 视频分辨率 | `2160P` |
| `video_codec` | 视频编码 | 视频编码 | `H.265` |
| `audio_codec` | 音频编码 | 音频编码 | `DTS-HD MA` |
| `audio_channels` | 音频声道数 | 原始声道数量 | `6` |
| `audio_channels_label` | 声道 | 格式化后的声道，例如 5.1 | `5.1` |
| `hdr_type` | HDR | HDR/Dolby Vision 类型 | `Dolby Vision` |
| `source_type` | 片源 | WEB-DL、BluRay 等片源类型 | `WEB-DL` |
| `frame_rate` | 帧率 | 视频帧率 | `23.976fps` |
| `container` | 封装格式 | MKV、MP4 等媒体封装格式 | `MKV` |
| `release_group` | 制作组 | 资源发布组 | `FRDS` |
| `web_source` | 平台来源 | Netflix、Disney+ 等平台 | `Netflix` |
| `quality` | 质量摘要 | 自动拼接分辨率、片源、编码、HDR 等 | `2160P / WEB-DL / H.265 / Dolby Vision` |
| `quality_comment` | 画质点评 | 按 Dolby Vision、HDR、4K、1080P 优先级生成；四档文案可在当前模板中独立修改或清空关闭 | `Dolby Vision 动态画面：逐场景优化明暗与色彩，明暗过渡更细腻。` |

#### 聚合

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `file_count` | 文件数 | 当前聚合卡片包含的文件或项目数量 | `3` |
| `item_count` | 项目数 | 上游事件提供的项目数量 | `3` |
| `aggregation_count` | 聚合数 | 当前聚合卡片的事件数量 | `3` |
| `episode_count` | 集数 | 当前聚合卡片覆盖的去重剧集数量 | `3` |
| `file_size` | 文件字节数 | 单文件大小或聚合前原始大小 | `3310703957` |
| `total_size` | 总大小 | 格式化后的聚合文件总大小 | `9.25GB` |
| `total_size_bytes` | 总字节数 | 未格式化的聚合文件总大小 | `9932111872` |
| `started_at` | 开始时间 | 聚合窗口第一条事件时间 | `08-12 20:29` |
| `ended_at` | 结束时间 | 聚合窗口最后一条事件时间 | `08-12 20:30` |

<a id="media_library_update"></a>

### 媒体更新 `media_library_update`

Emby 媒体元数据或文件发生更新；同作品短窗口内聚合。所属大类：`media_library`（入库通知）；聚合：**支持**；TMDB 头图来源：**可能有**。

图片规则：明确的 TMDB 海报始终优先；自动模式无 TMDB 时使用“媒体更新”默认图，自定义模式改用已验证链接，关闭模式无 TMDB 时发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
🔄 媒体更新｜{{ show_name or title }}{% if season_episode %} · {{ season_episode }}{% endif %}
```

**正文**

```jinja
{% if media_type or year %}🎬 {{ media_type }}{% if year %} · {{ year }}{% endif %}
{% endif %}{% if library_name %}🗂️ 媒体库：{{ library_name }}
{% endif %}{% if quality %}🎞️ {{ quality }}
{% endif %}{% if emby_instance_name %}🖥️ {{ emby_instance_name }}
{% endif %}🕐 {{ now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |

#### 媒体

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `title` | 标题 | 媒体、任务或资源标题 | `三体` |
| `show_name` | 剧名 | 剧集聚合时使用的系列名称 | `三体` |
| `raw_title` | 原始标题 | 规范化前的标题，可能包含年份或 TMDB 标记 | `三体 (2023) -{tmdbid=204541}` |
| `raw_show_name` | 原始剧名 | 规范化前的系列名称 | `三体 (2023) -{tmdbid=204541}` |
| `title_year` | 标题年份 | 自动组合的“标题 (年份)” | `三体 (2023)` |
| `media_type` | 媒体类型 | 电影、电视剧或音乐 | `电视剧` |
| `year` | 年份 | 媒体发行年份 | `2023` |
| `season_episode` | 季集 | 单集或聚合后的季集范围 | `S01E01-E03` |
| `rating` | 评分 | 媒体评分 | `8.7` |
| `genres` | 类型标签 | 媒体类型或标签 | `剧情 / 科幻` |
| `genre_names` | 紧凑类型标签 | 以斜杠拼接的类型标签 | `剧情/科幻` |
| `overview` | 简介 | 媒体简介，可能为空 | `人类文明首次收到来自宇宙深处的信息。` |
| `poster_url` | 海报地址 | 通知卡片使用的海报 URL | `https://image.tmdb.org/t/p/w500/demo.jpg` |
| `image_url` | 图片地址 | 通知图片 URL，通常与 poster_url 相同 | `https://image.tmdb.org/t/p/w500/demo.jpg` |
| `tmdb_id` | TMDB ID | TMDB 媒体编号 | `204541` |
| `tmdb_media_type` | TMDB 类型 | movie 或 tv | `tv` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `type` | 类型别名 | media_type 的兼容别名 | `电视剧` |
| `season_fmt` | 季集别名 | season_episode 的兼容别名 | `S01E01-E03` |
| `vote_average` | 评分别名 | rating 的兼容别名 | `8.7` |
| `category` | 类别 | 优先为媒体库名称，否则回退到类型标签 | `电视剧` |
| `instance_name` | 实例名称别名 | emby_instance_name 的兼容别名 | `客厅 Emby` |
| `resource_term` | 质量别名 | quality 的兼容别名 | `2160P / WEB-DL / H.265` |
| `size` | 大小别名 | 格式化后的 total_size 兼容别名 | `9.25GB` |

#### 媒体链接

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `tmdb_link` | TMDB 文字链接 | 显示为可点击的“TMDB”，真实详情页地址不会显示在消息正文中 | `TMDB（可点击）` |
| `tmdb_link_start` | TMDB 自定义文字开始 | 为自定义文字添加TMDB详情页超链接，必须与结束变量成对使用 | `{{ tmdb_link_start }}查看 TMDB{{ tmdb_link_end }}` |
| `tmdb_link_end` | TMDB 自定义文字结束 | 结束TMDB文字超链接范围 | `{{ tmdb_link_end }}` |
| `imdb_id` | IMDb ID | 当前电影或整部剧的 IMDb title ID；缺失时为空 | `tt13016388` |
| `imdb_link` | IMDb 文字链接 | 显示为可点击的“IMDb”，真实详情页地址不会显示在消息正文中 | `IMDb（可点击）` |
| `imdb_link_start` | IMDb 自定义文字开始 | 为自定义文字添加IMDb详情页超链接，必须与结束变量成对使用 | `{{ imdb_link_start }}查看 IMDb{{ imdb_link_end }}` |
| `imdb_link_end` | IMDb 自定义文字结束 | 结束IMDb文字超链接范围 | `{{ imdb_link_end }}` |

#### 事件

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `event_id` | 事件 ID | Madby/Emby 事件唯一标识 | `evt-20260812-001` |
| `event_type` | 事件名称 | 可读事件名称，例如开始播放或新入库 | `新入库` |
| `event_action` | 事件动作 | 入库、更新、删除等动作 | `新入库` |

#### 状态

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `status` | 媒体状态 | 媒体或任务原始状态 | `Ended` |

#### 入库

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `library_id` | 媒体库 ID | Emby 媒体库编号 | `library-1` |
| `library_name` | 媒体库 | Emby 媒体库名称 | `电视剧` |
| `item_id` | 项目 ID | Emby Item ID；聚合时为首个项目 | `12345` |
| `series_id` | 系列 ID | Emby Series ID | `series-100` |
| `media_source_id` | 媒体源 ID | Emby MediaSource ID | `source-1` |
| `madby_source` | Madby 来源 | Madby 事件来源标识 | `emby` |

#### Emby 实例

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `emby_instance_id` | Emby 实例 ID | Dian115 配置中的 Emby 实例 ID | `2` |
| `emby_instance_name` | Emby 实例名称 | Dian115 多实例配置里的名称；推荐用它区分服务器 | `客厅 Emby` |
| `emby_server_name` | Emby 服务器名 | Emby/Madby 事件自报的服务器名称 | `MediaServer` |
| `server_name` | 服务器名 | 优先为配置的实例名，否则为 Emby 自报名称 | `客厅 Emby` |
| `proxy_id` | 代理实例 ID | 与 emby_instance_id 相同的内部路由 ID | `2` |

#### 质量

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `resolution` | 分辨率 | 视频分辨率 | `2160P` |
| `video_codec` | 视频编码 | 视频编码 | `H.265` |
| `audio_codec` | 音频编码 | 音频编码 | `DTS-HD MA` |
| `audio_channels` | 音频声道数 | 原始声道数量 | `6` |
| `audio_channels_label` | 声道 | 格式化后的声道，例如 5.1 | `5.1` |
| `hdr_type` | HDR | HDR/Dolby Vision 类型 | `Dolby Vision` |
| `source_type` | 片源 | WEB-DL、BluRay 等片源类型 | `WEB-DL` |
| `frame_rate` | 帧率 | 视频帧率 | `23.976fps` |
| `container` | 封装格式 | MKV、MP4 等媒体封装格式 | `MKV` |
| `release_group` | 制作组 | 资源发布组 | `FRDS` |
| `web_source` | 平台来源 | Netflix、Disney+ 等平台 | `Netflix` |
| `quality` | 质量摘要 | 自动拼接分辨率、片源、编码、HDR 等 | `2160P / WEB-DL / H.265 / Dolby Vision` |
| `quality_comment` | 画质点评 | 按 Dolby Vision、HDR、4K、1080P 优先级生成；四档文案可在当前模板中独立修改或清空关闭 | `Dolby Vision 动态画面：逐场景优化明暗与色彩，明暗过渡更细腻。` |

#### 聚合

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `file_count` | 文件数 | 当前聚合卡片包含的文件或项目数量 | `3` |
| `item_count` | 项目数 | 上游事件提供的项目数量 | `3` |
| `aggregation_count` | 聚合数 | 当前聚合卡片的事件数量 | `3` |
| `episode_count` | 集数 | 当前聚合卡片覆盖的去重剧集数量 | `3` |
| `file_size` | 文件字节数 | 单文件大小或聚合前原始大小 | `3310703957` |
| `total_size` | 总大小 | 格式化后的聚合文件总大小 | `9.25GB` |
| `total_size_bytes` | 总字节数 | 未格式化的聚合文件总大小 | `9932111872` |
| `started_at` | 开始时间 | 聚合窗口第一条事件时间 | `08-12 20:29` |
| `ended_at` | 结束时间 | 聚合窗口最后一条事件时间 | `08-12 20:30` |

<a id="media_library_delete"></a>

### 媒体删除 `media_library_delete`

Emby 媒体项目从库中删除。所属大类：`media_library`（入库通知）；聚合：**不支持**；TMDB 头图来源：**可能有**。

图片规则：明确的 TMDB 海报始终优先；自动模式无 TMDB 时使用“媒体删除”默认图，自定义模式改用已验证链接，关闭模式无 TMDB 时发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
🗑️ 媒体删除｜{{ show_name or title }}{% if season_episode %} · {{ season_episode }}{% endif %}
```

**正文**

```jinja
{% if media_type %}🎬 {{ media_type }}
{% endif %}{% if library_name %}🗂️ 原媒体库：{{ library_name }}
{% endif %}{% if item_id %}🆔 Item {{ item_id }}
{% endif %}{% if emby_instance_name %}🖥️ {{ emby_instance_name }}
{% endif %}🕐 {{ now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |

#### 媒体

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `title` | 标题 | 媒体、任务或资源标题 | `三体` |
| `show_name` | 剧名 | 剧集聚合时使用的系列名称 | `三体` |
| `raw_title` | 原始标题 | 规范化前的标题，可能包含年份或 TMDB 标记 | `三体 (2023) -{tmdbid=204541}` |
| `raw_show_name` | 原始剧名 | 规范化前的系列名称 | `三体 (2023) -{tmdbid=204541}` |
| `title_year` | 标题年份 | 自动组合的“标题 (年份)” | `三体 (2023)` |
| `media_type` | 媒体类型 | 电影、电视剧或音乐 | `电视剧` |
| `year` | 年份 | 媒体发行年份 | `2023` |
| `season_episode` | 季集 | 单集或聚合后的季集范围 | `S01E01-E03` |
| `rating` | 评分 | 媒体评分 | `8.7` |
| `genres` | 类型标签 | 媒体类型或标签 | `剧情 / 科幻` |
| `genre_names` | 紧凑类型标签 | 以斜杠拼接的类型标签 | `剧情/科幻` |
| `overview` | 简介 | 媒体简介，可能为空 | `人类文明首次收到来自宇宙深处的信息。` |
| `poster_url` | 海报地址 | 通知卡片使用的海报 URL | `https://image.tmdb.org/t/p/w500/demo.jpg` |
| `image_url` | 图片地址 | 通知图片 URL，通常与 poster_url 相同 | `https://image.tmdb.org/t/p/w500/demo.jpg` |
| `tmdb_id` | TMDB ID | TMDB 媒体编号 | `204541` |
| `tmdb_media_type` | TMDB 类型 | movie 或 tv | `tv` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `type` | 类型别名 | media_type 的兼容别名 | `电视剧` |
| `season_fmt` | 季集别名 | season_episode 的兼容别名 | `S01E01-E03` |
| `vote_average` | 评分别名 | rating 的兼容别名 | `8.7` |
| `category` | 类别 | 优先为媒体库名称，否则回退到类型标签 | `电视剧` |
| `instance_name` | 实例名称别名 | emby_instance_name 的兼容别名 | `客厅 Emby` |
| `resource_term` | 质量别名 | quality 的兼容别名 | `2160P / WEB-DL / H.265` |

#### 媒体链接

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `tmdb_link` | TMDB 文字链接 | 显示为可点击的“TMDB”，真实详情页地址不会显示在消息正文中 | `TMDB（可点击）` |
| `tmdb_link_start` | TMDB 自定义文字开始 | 为自定义文字添加TMDB详情页超链接，必须与结束变量成对使用 | `{{ tmdb_link_start }}查看 TMDB{{ tmdb_link_end }}` |
| `tmdb_link_end` | TMDB 自定义文字结束 | 结束TMDB文字超链接范围 | `{{ tmdb_link_end }}` |
| `imdb_id` | IMDb ID | 当前电影或整部剧的 IMDb title ID；缺失时为空 | `tt13016388` |
| `imdb_link` | IMDb 文字链接 | 显示为可点击的“IMDb”，真实详情页地址不会显示在消息正文中 | `IMDb（可点击）` |
| `imdb_link_start` | IMDb 自定义文字开始 | 为自定义文字添加IMDb详情页超链接，必须与结束变量成对使用 | `{{ imdb_link_start }}查看 IMDb{{ imdb_link_end }}` |
| `imdb_link_end` | IMDb 自定义文字结束 | 结束IMDb文字超链接范围 | `{{ imdb_link_end }}` |

#### 事件

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `event_id` | 事件 ID | Madby/Emby 事件唯一标识 | `evt-20260812-001` |
| `event_type` | 事件名称 | 可读事件名称，例如开始播放或新入库 | `新入库` |
| `event_action` | 事件动作 | 入库、更新、删除等动作 | `新入库` |

#### 状态

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `status` | 媒体状态 | 媒体或任务原始状态 | `Ended` |

#### 入库

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `library_id` | 媒体库 ID | Emby 媒体库编号 | `library-1` |
| `library_name` | 媒体库 | Emby 媒体库名称 | `电视剧` |
| `item_id` | 项目 ID | Emby Item ID；聚合时为首个项目 | `12345` |
| `series_id` | 系列 ID | Emby Series ID | `series-100` |
| `media_source_id` | 媒体源 ID | Emby MediaSource ID | `source-1` |
| `madby_source` | Madby 来源 | Madby 事件来源标识 | `emby` |

#### Emby 实例

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `emby_instance_id` | Emby 实例 ID | Dian115 配置中的 Emby 实例 ID | `2` |
| `emby_instance_name` | Emby 实例名称 | Dian115 多实例配置里的名称；推荐用它区分服务器 | `客厅 Emby` |
| `emby_server_name` | Emby 服务器名 | Emby/Madby 事件自报的服务器名称 | `MediaServer` |
| `server_name` | 服务器名 | 优先为配置的实例名，否则为 Emby 自报名称 | `客厅 Emby` |
| `proxy_id` | 代理实例 ID | 与 emby_instance_id 相同的内部路由 ID | `2` |

#### 质量

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `resolution` | 分辨率 | 视频分辨率 | `2160P` |
| `video_codec` | 视频编码 | 视频编码 | `H.265` |
| `audio_codec` | 音频编码 | 音频编码 | `DTS-HD MA` |
| `audio_channels` | 音频声道数 | 原始声道数量 | `6` |
| `audio_channels_label` | 声道 | 格式化后的声道，例如 5.1 | `5.1` |
| `hdr_type` | HDR | HDR/Dolby Vision 类型 | `Dolby Vision` |
| `source_type` | 片源 | WEB-DL、BluRay 等片源类型 | `WEB-DL` |
| `frame_rate` | 帧率 | 视频帧率 | `23.976fps` |
| `container` | 封装格式 | MKV、MP4 等媒体封装格式 | `MKV` |
| `release_group` | 制作组 | 资源发布组 | `FRDS` |
| `web_source` | 平台来源 | Netflix、Disney+ 等平台 | `Netflix` |
| `quality` | 质量摘要 | 自动拼接分辨率、片源、编码、HDR 等 | `2160P / WEB-DL / H.265 / Dolby Vision` |
| `quality_comment` | 画质点评 | 按 Dolby Vision、HDR、4K、1080P 优先级生成；四档文案可在当前模板中独立修改或清空关闭 | `Dolby Vision 动态画面：逐场景优化明暗与色彩，明暗过渡更细腻。` |

<a id="emby_user_authenticated"></a>

### 用户登录成功 `emby_user_authenticated`

Emby 用户通过身份验证。所属大类：`emby_security`（Emby 账户安全）；聚合：**不支持**；TMDB 头图来源：**无**。

图片规则：用户登录成功事件没有 TMDB 图片来源；自动模式使用“登录成功”默认图，自定义模式使用已验证链接，关闭模式发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
🔓 Emby 登录成功｜{{ user_name or '未知用户' }}
```

**正文**

```jinja
{% if device_name %}📱 {{ device_name }}
{% endif %}{% if description %}📝 {{ description }}
{% endif %}🖥️ {{ emby_instance_name or server_name }}
🕐 {{ now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |

#### Emby 实例

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `emby_instance_id` | Emby 实例 ID | Dian115 配置中的 Emby 实例 ID | `2` |
| `emby_instance_name` | Emby 实例名称 | Dian115 多实例配置里的名称；推荐用它区分服务器 | `客厅 Emby` |
| `emby_server_name` | Emby 服务器名 | Emby/Madby 事件自报的服务器名称 | `MediaServer` |
| `server_name` | 服务器名 | 优先为配置的实例名，否则为 Emby 自报名称 | `客厅 Emby` |
| `proxy_id` | 代理实例 ID | 与 emby_instance_id 相同的内部路由 ID | `2` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `instance_name` | 实例名称别名 | emby_instance_name 的兼容别名 | `客厅 Emby` |
| `username` | 用户名别名 | user_name 或 account_name 的兼容别名 | `Alice` |

#### 事件

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `event_id` | 事件 ID | Madby/Emby 事件唯一标识 | `evt-20260812-001` |
| `event_type` | 事件名称 | 可读事件名称，例如开始播放或新入库 | `新入库` |
| `event_label` | Emby 事件名称 | Emby 官方事件的中文名称 | `用户登录成功` |
| `occurred_at` | 事件发生时间 | Emby/Madby 上报的原始事件时间 | `2026-08-12T20:29:58+08:00` |
| `notification_title` | 通知原始标题 | Emby 官方事件附带的原始标题 | `User authenticated` |
| `description` | 事件说明 | Emby 事件正文 | `管理员已更新插件` |
| `severity` | 严重级别 | Emby 事件严重级别 | `Info` |
| `url` | 事件链接 | Emby 事件附带的链接 | `https://emby.example.com` |

#### 播放

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `user_id` | 用户 ID | Emby 用户唯一标识 | `user-100` |
| `user_name` | 用户 | Emby 播放或安全事件用户 | `Alice` |
| `device_id` | 设备 ID | Emby 设备唯一标识 | `device-200` |
| `device_name` | 设备 | 播放或登录设备名称 | `客厅电视` |

<a id="emby_user_authentication_failed"></a>

### 用户登录失败 `emby_user_authentication_failed`

Emby 用户身份验证失败。所属大类：`emby_security`（Emby 账户安全）；聚合：**不支持**；TMDB 头图来源：**无**。

图片规则：用户登录失败事件没有 TMDB 图片来源；自动模式使用“登录失败”默认图，自定义模式使用已验证链接，关闭模式发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
🔒 Emby 登录失败｜{{ user_name or '未知用户' }}
```

**正文**

```jinja
{% if device_name %}📱 {{ device_name }}
{% endif %}{% if severity %}⚠️ 级别：{{ severity }}
{% endif %}{% if description %}📝 {{ description }}
{% endif %}🖥️ {{ emby_instance_name or server_name }} · {{ now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |

#### Emby 实例

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `emby_instance_id` | Emby 实例 ID | Dian115 配置中的 Emby 实例 ID | `2` |
| `emby_instance_name` | Emby 实例名称 | Dian115 多实例配置里的名称；推荐用它区分服务器 | `客厅 Emby` |
| `emby_server_name` | Emby 服务器名 | Emby/Madby 事件自报的服务器名称 | `MediaServer` |
| `server_name` | 服务器名 | 优先为配置的实例名，否则为 Emby 自报名称 | `客厅 Emby` |
| `proxy_id` | 代理实例 ID | 与 emby_instance_id 相同的内部路由 ID | `2` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `instance_name` | 实例名称别名 | emby_instance_name 的兼容别名 | `客厅 Emby` |
| `username` | 用户名别名 | user_name 或 account_name 的兼容别名 | `Alice` |

#### 事件

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `event_id` | 事件 ID | Madby/Emby 事件唯一标识 | `evt-20260812-001` |
| `event_type` | 事件名称 | 可读事件名称，例如开始播放或新入库 | `新入库` |
| `event_label` | Emby 事件名称 | Emby 官方事件的中文名称 | `用户登录成功` |
| `occurred_at` | 事件发生时间 | Emby/Madby 上报的原始事件时间 | `2026-08-12T20:29:58+08:00` |
| `notification_title` | 通知原始标题 | Emby 官方事件附带的原始标题 | `User authenticated` |
| `description` | 事件说明 | Emby 事件正文 | `管理员已更新插件` |
| `severity` | 严重级别 | Emby 事件严重级别 | `Info` |
| `url` | 事件链接 | Emby 事件附带的链接 | `https://emby.example.com` |

#### 播放

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `user_id` | 用户 ID | Emby 用户唯一标识 | `user-100` |
| `user_name` | 用户 | Emby 播放或安全事件用户 | `Alice` |
| `device_id` | 设备 ID | Emby 设备唯一标识 | `device-200` |
| `device_name` | 设备 | 播放或登录设备名称 | `客厅电视` |

<a id="emby_user_locked_out"></a>

### 用户被锁定 `emby_user_locked_out`

Emby 用户因安全策略被锁定。所属大类：`emby_security`（Emby 账户安全）；聚合：**不支持**；TMDB 头图来源：**无**。

图片规则：用户锁定事件没有 TMDB 图片来源；自动模式使用“用户锁定”默认图，自定义模式使用已验证链接，关闭模式发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
🚫 Emby 用户锁定｜{{ user_name or '未知用户' }}
```

**正文**

```jinja
{% if description %}📝 {{ description }}
{% endif %}{% if severity %}⚠️ 级别：{{ severity }}
{% endif %}🖥️ {{ emby_instance_name or server_name }}
🕐 {{ now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |

#### Emby 实例

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `emby_instance_id` | Emby 实例 ID | Dian115 配置中的 Emby 实例 ID | `2` |
| `emby_instance_name` | Emby 实例名称 | Dian115 多实例配置里的名称；推荐用它区分服务器 | `客厅 Emby` |
| `emby_server_name` | Emby 服务器名 | Emby/Madby 事件自报的服务器名称 | `MediaServer` |
| `server_name` | 服务器名 | 优先为配置的实例名，否则为 Emby 自报名称 | `客厅 Emby` |
| `proxy_id` | 代理实例 ID | 与 emby_instance_id 相同的内部路由 ID | `2` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `instance_name` | 实例名称别名 | emby_instance_name 的兼容别名 | `客厅 Emby` |
| `username` | 用户名别名 | user_name 或 account_name 的兼容别名 | `Alice` |

#### 事件

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `event_id` | 事件 ID | Madby/Emby 事件唯一标识 | `evt-20260812-001` |
| `event_type` | 事件名称 | 可读事件名称，例如开始播放或新入库 | `新入库` |
| `event_label` | Emby 事件名称 | Emby 官方事件的中文名称 | `用户登录成功` |
| `occurred_at` | 事件发生时间 | Emby/Madby 上报的原始事件时间 | `2026-08-12T20:29:58+08:00` |
| `notification_title` | 通知原始标题 | Emby 官方事件附带的原始标题 | `User authenticated` |
| `description` | 事件说明 | Emby 事件正文 | `管理员已更新插件` |
| `severity` | 严重级别 | Emby 事件严重级别 | `Info` |
| `url` | 事件链接 | Emby 事件附带的链接 | `https://emby.example.com` |

#### 播放

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `user_id` | 用户 ID | Emby 用户唯一标识 | `user-100` |
| `user_name` | 用户 | Emby 播放或安全事件用户 | `Alice` |

<a id="emby_user_created"></a>

### 用户已创建 `emby_user_created`

Emby 新用户创建事件。所属大类：`emby_security`（Emby 账户安全）；聚合：**不支持**；TMDB 头图来源：**无**。

图片规则：用户创建事件没有 TMDB 图片来源；自动模式使用“用户创建”默认图，自定义模式使用已验证链接，关闭模式发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
👤 Emby 用户已创建｜{{ user_name or '未命名用户' }}
```

**正文**

```jinja
{% if description %}📝 {{ description }}
{% endif %}{% if device_name %}📱 操作端：{{ device_name }}
{% endif %}🖥️ {{ emby_instance_name or server_name }}
🕐 {{ now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |

#### Emby 实例

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `emby_instance_id` | Emby 实例 ID | Dian115 配置中的 Emby 实例 ID | `2` |
| `emby_instance_name` | Emby 实例名称 | Dian115 多实例配置里的名称；推荐用它区分服务器 | `客厅 Emby` |
| `emby_server_name` | Emby 服务器名 | Emby/Madby 事件自报的服务器名称 | `MediaServer` |
| `server_name` | 服务器名 | 优先为配置的实例名，否则为 Emby 自报名称 | `客厅 Emby` |
| `proxy_id` | 代理实例 ID | 与 emby_instance_id 相同的内部路由 ID | `2` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `instance_name` | 实例名称别名 | emby_instance_name 的兼容别名 | `客厅 Emby` |
| `username` | 用户名别名 | user_name 或 account_name 的兼容别名 | `Alice` |

#### 事件

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `event_id` | 事件 ID | Madby/Emby 事件唯一标识 | `evt-20260812-001` |
| `event_type` | 事件名称 | 可读事件名称，例如开始播放或新入库 | `新入库` |
| `event_label` | Emby 事件名称 | Emby 官方事件的中文名称 | `用户登录成功` |
| `occurred_at` | 事件发生时间 | Emby/Madby 上报的原始事件时间 | `2026-08-12T20:29:58+08:00` |
| `notification_title` | 通知原始标题 | Emby 官方事件附带的原始标题 | `User authenticated` |
| `description` | 事件说明 | Emby 事件正文 | `管理员已更新插件` |
| `severity` | 严重级别 | Emby 事件严重级别 | `Info` |
| `url` | 事件链接 | Emby 事件附带的链接 | `https://emby.example.com` |

#### 播放

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `user_id` | 用户 ID | Emby 用户唯一标识 | `user-100` |
| `user_name` | 用户 | Emby 播放或安全事件用户 | `Alice` |
| `device_id` | 设备 ID | Emby 设备唯一标识 | `device-200` |
| `device_name` | 设备 | 播放或登录设备名称 | `客厅电视` |

<a id="emby_user_deleted"></a>

### 用户已删除 `emby_user_deleted`

Emby 用户已删除事件。所属大类：`emby_security`（Emby 账户安全）；聚合：**不支持**；TMDB 头图来源：**无**。

图片规则：用户删除事件没有 TMDB 图片来源；自动模式使用“用户删除”默认图，自定义模式使用已验证链接，关闭模式发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
👤 Emby 用户已删除｜{{ user_name or '未知用户' }}
```

**正文**

```jinja
{% if description %}📝 {{ description }}
{% endif %}{% if severity %}⚠️ 级别：{{ severity }}
{% endif %}🖥️ {{ emby_instance_name or server_name }}
🕐 {{ now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |

#### Emby 实例

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `emby_instance_id` | Emby 实例 ID | Dian115 配置中的 Emby 实例 ID | `2` |
| `emby_instance_name` | Emby 实例名称 | Dian115 多实例配置里的名称；推荐用它区分服务器 | `客厅 Emby` |
| `emby_server_name` | Emby 服务器名 | Emby/Madby 事件自报的服务器名称 | `MediaServer` |
| `server_name` | 服务器名 | 优先为配置的实例名，否则为 Emby 自报名称 | `客厅 Emby` |
| `proxy_id` | 代理实例 ID | 与 emby_instance_id 相同的内部路由 ID | `2` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `instance_name` | 实例名称别名 | emby_instance_name 的兼容别名 | `客厅 Emby` |
| `username` | 用户名别名 | user_name 或 account_name 的兼容别名 | `Alice` |

#### 事件

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `event_id` | 事件 ID | Madby/Emby 事件唯一标识 | `evt-20260812-001` |
| `event_type` | 事件名称 | 可读事件名称，例如开始播放或新入库 | `新入库` |
| `event_label` | Emby 事件名称 | Emby 官方事件的中文名称 | `用户登录成功` |
| `occurred_at` | 事件发生时间 | Emby/Madby 上报的原始事件时间 | `2026-08-12T20:29:58+08:00` |
| `notification_title` | 通知原始标题 | Emby 官方事件附带的原始标题 | `User authenticated` |
| `description` | 事件说明 | Emby 事件正文 | `管理员已更新插件` |
| `severity` | 严重级别 | Emby 事件严重级别 | `Info` |
| `url` | 事件链接 | Emby 事件附带的链接 | `https://emby.example.com` |

#### 播放

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `user_id` | 用户 ID | Emby 用户唯一标识 | `user-100` |
| `user_name` | 用户 | Emby 播放或安全事件用户 | `Alice` |

<a id="emby_user_password_changed"></a>

### 用户密码更改 `emby_user_password_changed`

Emby 用户密码已更改。所属大类：`emby_security`（Emby 账户安全）；聚合：**不支持**；TMDB 头图来源：**无**。

图片规则：密码更改事件没有 TMDB 图片来源；自动模式使用“密码更改”默认图，自定义模式使用已验证链接，关闭模式发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
🔑 Emby 密码已更改｜{{ user_name or '未知用户' }}
```

**正文**

```jinja
{% if description %}📝 {{ description }}
{% endif %}{% if device_name %}📱 {{ device_name }}
{% endif %}🖥️ {{ emby_instance_name or server_name }}
🕐 {{ now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |

#### Emby 实例

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `emby_instance_id` | Emby 实例 ID | Dian115 配置中的 Emby 实例 ID | `2` |
| `emby_instance_name` | Emby 实例名称 | Dian115 多实例配置里的名称；推荐用它区分服务器 | `客厅 Emby` |
| `emby_server_name` | Emby 服务器名 | Emby/Madby 事件自报的服务器名称 | `MediaServer` |
| `server_name` | 服务器名 | 优先为配置的实例名，否则为 Emby 自报名称 | `客厅 Emby` |
| `proxy_id` | 代理实例 ID | 与 emby_instance_id 相同的内部路由 ID | `2` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `instance_name` | 实例名称别名 | emby_instance_name 的兼容别名 | `客厅 Emby` |
| `username` | 用户名别名 | user_name 或 account_name 的兼容别名 | `Alice` |

#### 事件

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `event_id` | 事件 ID | Madby/Emby 事件唯一标识 | `evt-20260812-001` |
| `event_type` | 事件名称 | 可读事件名称，例如开始播放或新入库 | `新入库` |
| `event_label` | Emby 事件名称 | Emby 官方事件的中文名称 | `用户登录成功` |
| `occurred_at` | 事件发生时间 | Emby/Madby 上报的原始事件时间 | `2026-08-12T20:29:58+08:00` |
| `notification_title` | 通知原始标题 | Emby 官方事件附带的原始标题 | `User authenticated` |
| `description` | 事件说明 | Emby 事件正文 | `管理员已更新插件` |
| `severity` | 严重级别 | Emby 事件严重级别 | `Info` |
| `url` | 事件链接 | Emby 事件附带的链接 | `https://emby.example.com` |

#### 播放

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `user_id` | 用户 ID | Emby 用户唯一标识 | `user-100` |
| `user_name` | 用户 | Emby 播放或安全事件用户 | `Alice` |
| `device_id` | 设备 ID | Emby 设备唯一标识 | `device-200` |
| `device_name` | 设备 | 播放或登录设备名称 | `客厅电视` |

<a id="emby_user_policy_updated"></a>

### 用户策略更新 `emby_user_policy_updated`

Emby 用户访问策略已更新。所属大类：`emby_security`（Emby 账户安全）；聚合：**不支持**；TMDB 头图来源：**无**。

图片规则：用户策略更新事件没有 TMDB 图片来源；自动模式使用“策略更新”默认图，自定义模式使用已验证链接，关闭模式发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
🛡️ Emby 用户策略更新｜{{ user_name or '未知用户' }}
```

**正文**

```jinja
{% if description %}📝 {{ description }}
{% endif %}{% if url %}🔗 {{ url }}
{% endif %}🖥️ {{ emby_instance_name or server_name }}
🕐 {{ now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |

#### Emby 实例

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `emby_instance_id` | Emby 实例 ID | Dian115 配置中的 Emby 实例 ID | `2` |
| `emby_instance_name` | Emby 实例名称 | Dian115 多实例配置里的名称；推荐用它区分服务器 | `客厅 Emby` |
| `emby_server_name` | Emby 服务器名 | Emby/Madby 事件自报的服务器名称 | `MediaServer` |
| `server_name` | 服务器名 | 优先为配置的实例名，否则为 Emby 自报名称 | `客厅 Emby` |
| `proxy_id` | 代理实例 ID | 与 emby_instance_id 相同的内部路由 ID | `2` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `instance_name` | 实例名称别名 | emby_instance_name 的兼容别名 | `客厅 Emby` |
| `username` | 用户名别名 | user_name 或 account_name 的兼容别名 | `Alice` |

#### 事件

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `event_id` | 事件 ID | Madby/Emby 事件唯一标识 | `evt-20260812-001` |
| `event_type` | 事件名称 | 可读事件名称，例如开始播放或新入库 | `新入库` |
| `event_label` | Emby 事件名称 | Emby 官方事件的中文名称 | `用户登录成功` |
| `occurred_at` | 事件发生时间 | Emby/Madby 上报的原始事件时间 | `2026-08-12T20:29:58+08:00` |
| `notification_title` | 通知原始标题 | Emby 官方事件附带的原始标题 | `User authenticated` |
| `description` | 事件说明 | Emby 事件正文 | `管理员已更新插件` |
| `severity` | 严重级别 | Emby 事件严重级别 | `Info` |
| `url` | 事件链接 | Emby 事件附带的链接 | `https://emby.example.com` |

#### 播放

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `user_id` | 用户 ID | Emby 用户唯一标识 | `user-100` |
| `user_name` | 用户 | Emby 播放或安全事件用户 | `Alice` |

<a id="library_organize_success"></a>

### 整理完成 `library_organize_success`

一个或多个媒体文件整理成功。所属大类：`library_organize`（文件整理通知）；聚合：**支持**；TMDB 头图来源：**可能有**。

图片规则：整理结果明确匹配到 TMDB 时优先使用其海报；自动模式无 TMDB 时使用“整理完成”默认图，自定义模式改用已验证链接，关闭模式无 TMDB 时发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
✅ 整理完成｜{{ show_name or title }}{% if season_episode %} · {{ season_episode }}{% endif %}
```

**正文**

```jinja
{% if file_count %}📦 {{ file_count }} 个文件{% if total_size %} · {{ total_size }}{% endif %}
{% elif episode_count %}📺 共 {{ episode_count }} 集
{% endif %}{% if quality %}🎞️ {{ quality }}
{% endif %}{% if year or rating or genres %}ℹ️{% if year %} {{ year }}{% endif %}{% if rating %} · ⭐ {{ rating }}{% endif %}{% if genres %} · {{ genres }}{% endif %}
{% endif %}{% if is_wash %}♻️ {{ wash_status or '洗版完成' }}{% if wash_reason %} · {{ wash_reason }}{% endif %}
{% endif %}🕐 {{ time_range or now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |

#### 媒体

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `title` | 标题 | 媒体、任务或资源标题 | `三体` |
| `show_name` | 剧名 | 剧集聚合时使用的系列名称 | `三体` |
| `raw_title` | 原始标题 | 规范化前的标题，可能包含年份或 TMDB 标记 | `三体 (2023) -{tmdbid=204541}` |
| `raw_show_name` | 原始剧名 | 规范化前的系列名称 | `三体 (2023) -{tmdbid=204541}` |
| `title_year` | 标题年份 | 自动组合的“标题 (年份)” | `三体 (2023)` |
| `media_type` | 媒体类型 | 电影、电视剧或音乐 | `电视剧` |
| `year` | 年份 | 媒体发行年份 | `2023` |
| `season_episode` | 季集 | 单集或聚合后的季集范围 | `S01E01-E03` |
| `rating` | 评分 | 媒体评分 | `8.7` |
| `genres` | 类型标签 | 媒体类型或标签 | `剧情 / 科幻` |
| `genre_names` | 紧凑类型标签 | 以斜杠拼接的类型标签 | `剧情/科幻` |
| `overview` | 简介 | 媒体简介，可能为空 | `人类文明首次收到来自宇宙深处的信息。` |
| `poster_url` | 海报地址 | 通知卡片使用的海报 URL | `https://image.tmdb.org/t/p/w500/demo.jpg` |
| `tmdb_id` | TMDB ID | TMDB 媒体编号 | `204541` |
| `tmdb_media_type` | TMDB 类型 | movie 或 tv | `tv` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `type` | 类型别名 | media_type 的兼容别名 | `电视剧` |
| `season_fmt` | 季集别名 | season_episode 的兼容别名 | `S01E01-E03` |
| `vote_average` | 评分别名 | rating 的兼容别名 | `8.7` |
| `category` | 类别 | 优先为媒体库名称，否则回退到类型标签 | `电视剧` |
| `size` | 大小别名 | 格式化后的 total_size 兼容别名 | `9.25GB` |
| `resource_term` | 质量别名 | quality 的兼容别名 | `2160P / WEB-DL / H.265` |

#### 媒体链接

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `tmdb_link` | TMDB 文字链接 | 显示为可点击的“TMDB”，真实详情页地址不会显示在消息正文中 | `TMDB（可点击）` |
| `tmdb_link_start` | TMDB 自定义文字开始 | 为自定义文字添加TMDB详情页超链接，必须与结束变量成对使用 | `{{ tmdb_link_start }}查看 TMDB{{ tmdb_link_end }}` |
| `tmdb_link_end` | TMDB 自定义文字结束 | 结束TMDB文字超链接范围 | `{{ tmdb_link_end }}` |
| `imdb_id` | IMDb ID | 当前电影或整部剧的 IMDb title ID；缺失时为空 | `tt13016388` |
| `imdb_link` | IMDb 文字链接 | 显示为可点击的“IMDb”，真实详情页地址不会显示在消息正文中 | `IMDb（可点击）` |
| `imdb_link_start` | IMDb 自定义文字开始 | 为自定义文字添加IMDb详情页超链接，必须与结束变量成对使用 | `{{ imdb_link_start }}查看 IMDb{{ imdb_link_end }}` |
| `imdb_link_end` | IMDb 自定义文字结束 | 结束IMDb文字超链接范围 | `{{ imdb_link_end }}` |

#### 订阅

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `action` | 订阅动作 | added、landed 或 partial | `landed` |

#### 整理

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `action_text` | 整理动作 | 整理完成、整理跳过或整理失败 | `整理完成` |
| `detail_msg` | 整理详情 | 整理或洗版过程产生的详细说明 | `已替换为更高质量版本` |
| `is_wash` | 是否洗版 | 当前整理事件是否属于洗版流程 | `true` |
| `wash_status` | 洗版状态 | 洗版成功、跳过或失败 | `洗版完成` |
| `wash_reason` | 洗版原因 | 质量比较或洗版失败原因 | `新资源质量更高` |

#### 状态

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `status` | 媒体状态 | 媒体或任务原始状态 | `Ended` |

#### 文件

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `target_path` | 目标路径 | 整理或文件操作目标路径 | `/media/TV/三体` |
| `source_path` | 源路径 | 整理输入路径 | `/downloads/demo.mkv` |
| `file_name` | 文件名 | 文件或 STRM 名称 | `三体.S01E01.mkv` |

#### 聚合

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `file_count` | 文件数 | 当前聚合卡片包含的文件或项目数量 | `3` |
| `aggregation_count` | 聚合数 | 当前聚合卡片的事件数量 | `3` |
| `episode_count` | 集数 | 当前聚合卡片覆盖的去重剧集数量 | `3` |
| `file_size` | 文件字节数 | 单文件大小或聚合前原始大小 | `3310703957` |
| `total_size` | 总大小 | 格式化后的聚合文件总大小 | `9.25GB` |
| `total_size_bytes` | 总字节数 | 未格式化的聚合文件总大小 | `9932111872` |
| `started_at` | 开始时间 | 聚合窗口第一条事件时间 | `08-12 20:29` |
| `ended_at` | 结束时间 | 聚合窗口最后一条事件时间 | `08-12 20:30` |

#### 质量

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `resolution` | 分辨率 | 视频分辨率 | `2160P` |
| `video_codec` | 视频编码 | 视频编码 | `H.265` |
| `audio_codec` | 音频编码 | 音频编码 | `DTS-HD MA` |
| `audio_channels` | 音频声道数 | 原始声道数量 | `6` |
| `audio_channels_label` | 声道 | 格式化后的声道，例如 5.1 | `5.1` |
| `hdr_type` | HDR | HDR/Dolby Vision 类型 | `Dolby Vision` |
| `source_type` | 片源 | WEB-DL、BluRay 等片源类型 | `WEB-DL` |
| `frame_rate` | 帧率 | 视频帧率 | `23.976fps` |
| `container` | 封装格式 | MKV、MP4 等媒体封装格式 | `MKV` |
| `release_group` | 制作组 | 资源发布组 | `FRDS` |
| `web_source` | 平台来源 | Netflix、Disney+ 等平台 | `Netflix` |
| `quality` | 质量摘要 | 自动拼接分辨率、片源、编码、HDR 等 | `2160P / WEB-DL / H.265 / Dolby Vision` |
| `quality_comment` | 画质点评 | 按 Dolby Vision、HDR、4K、1080P 优先级生成；四档文案可在当前模板中独立修改或清空关闭 | `Dolby Vision 动态画面：逐场景优化明暗与色彩，明暗过渡更细腻。` |

<a id="library_organize_skip"></a>

### 整理跳过 `library_organize_skip`

整理因规则或目标状态被跳过。所属大类：`library_organize`（文件整理通知）；聚合：**支持**；TMDB 头图来源：**可能有**。

图片规则：跳过项目明确匹配到 TMDB 时优先使用其海报；自动模式无 TMDB 时使用“整理跳过”默认图，自定义模式改用已验证链接，关闭模式无 TMDB 时发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
⏭️ 整理跳过｜{{ show_name or title }}{% if season_episode %} · {{ season_episode }}{% endif %}
```

**正文**

```jinja
{% if skip_reason %}🧾 原因：{{ skip_reason }}
{% elif wash_reason %}🧾 原因：{{ wash_reason }}
{% endif %}{% if source_path %}📄 来源：{{ source_path }}
{% endif %}🕐 {{ time_range or now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |

#### 媒体

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `title` | 标题 | 媒体、任务或资源标题 | `三体` |
| `show_name` | 剧名 | 剧集聚合时使用的系列名称 | `三体` |
| `raw_title` | 原始标题 | 规范化前的标题，可能包含年份或 TMDB 标记 | `三体 (2023) -{tmdbid=204541}` |
| `raw_show_name` | 原始剧名 | 规范化前的系列名称 | `三体 (2023) -{tmdbid=204541}` |
| `title_year` | 标题年份 | 自动组合的“标题 (年份)” | `三体 (2023)` |
| `media_type` | 媒体类型 | 电影、电视剧或音乐 | `电视剧` |
| `year` | 年份 | 媒体发行年份 | `2023` |
| `season_episode` | 季集 | 单集或聚合后的季集范围 | `S01E01-E03` |
| `rating` | 评分 | 媒体评分 | `8.7` |
| `genres` | 类型标签 | 媒体类型或标签 | `剧情 / 科幻` |
| `genre_names` | 紧凑类型标签 | 以斜杠拼接的类型标签 | `剧情/科幻` |
| `overview` | 简介 | 媒体简介，可能为空 | `人类文明首次收到来自宇宙深处的信息。` |
| `poster_url` | 海报地址 | 通知卡片使用的海报 URL | `https://image.tmdb.org/t/p/w500/demo.jpg` |
| `tmdb_id` | TMDB ID | TMDB 媒体编号 | `204541` |
| `tmdb_media_type` | TMDB 类型 | movie 或 tv | `tv` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `type` | 类型别名 | media_type 的兼容别名 | `电视剧` |
| `season_fmt` | 季集别名 | season_episode 的兼容别名 | `S01E01-E03` |
| `vote_average` | 评分别名 | rating 的兼容别名 | `8.7` |
| `category` | 类别 | 优先为媒体库名称，否则回退到类型标签 | `电视剧` |
| `size` | 大小别名 | 格式化后的 total_size 兼容别名 | `9.25GB` |
| `resource_term` | 质量别名 | quality 的兼容别名 | `2160P / WEB-DL / H.265` |
| `err_msg` | 错误别名 | error_message 的兼容别名 | `目标目录不可写` |

#### 媒体链接

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `tmdb_link` | TMDB 文字链接 | 显示为可点击的“TMDB”，真实详情页地址不会显示在消息正文中 | `TMDB（可点击）` |
| `tmdb_link_start` | TMDB 自定义文字开始 | 为自定义文字添加TMDB详情页超链接，必须与结束变量成对使用 | `{{ tmdb_link_start }}查看 TMDB{{ tmdb_link_end }}` |
| `tmdb_link_end` | TMDB 自定义文字结束 | 结束TMDB文字超链接范围 | `{{ tmdb_link_end }}` |
| `imdb_id` | IMDb ID | 当前电影或整部剧的 IMDb title ID；缺失时为空 | `tt13016388` |
| `imdb_link` | IMDb 文字链接 | 显示为可点击的“IMDb”，真实详情页地址不会显示在消息正文中 | `IMDb（可点击）` |
| `imdb_link_start` | IMDb 自定义文字开始 | 为自定义文字添加IMDb详情页超链接，必须与结束变量成对使用 | `{{ imdb_link_start }}查看 IMDb{{ imdb_link_end }}` |
| `imdb_link_end` | IMDb 自定义文字结束 | 结束IMDb文字超链接范围 | `{{ imdb_link_end }}` |

#### 订阅

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `action` | 订阅动作 | added、landed 或 partial | `landed` |

#### 整理

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `action_text` | 整理动作 | 整理完成、整理跳过或整理失败 | `整理完成` |
| `detail_msg` | 整理详情 | 整理或洗版过程产生的详细说明 | `已替换为更高质量版本` |
| `is_wash` | 是否洗版 | 当前整理事件是否属于洗版流程 | `true` |
| `wash_status` | 洗版状态 | 洗版成功、跳过或失败 | `洗版完成` |
| `wash_reason` | 洗版原因 | 质量比较或洗版失败原因 | `新资源质量更高` |
| `skip_reason` | 跳过原因 | 整理未执行的原因 | `目标文件已存在` |

#### 状态

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `status` | 媒体状态 | 媒体或任务原始状态 | `Ended` |
| `error_message` | 错误信息 | 失败原因 | `目标目录不可写` |

#### 文件

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `target_path` | 目标路径 | 整理或文件操作目标路径 | `/media/TV/三体` |
| `source_path` | 源路径 | 整理输入路径 | `/downloads/demo.mkv` |
| `file_name` | 文件名 | 文件或 STRM 名称 | `三体.S01E01.mkv` |

#### 聚合

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `file_count` | 文件数 | 当前聚合卡片包含的文件或项目数量 | `3` |
| `aggregation_count` | 聚合数 | 当前聚合卡片的事件数量 | `3` |
| `episode_count` | 集数 | 当前聚合卡片覆盖的去重剧集数量 | `3` |
| `file_size` | 文件字节数 | 单文件大小或聚合前原始大小 | `3310703957` |
| `total_size` | 总大小 | 格式化后的聚合文件总大小 | `9.25GB` |
| `total_size_bytes` | 总字节数 | 未格式化的聚合文件总大小 | `9932111872` |
| `started_at` | 开始时间 | 聚合窗口第一条事件时间 | `08-12 20:29` |
| `ended_at` | 结束时间 | 聚合窗口最后一条事件时间 | `08-12 20:30` |

#### 质量

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `resolution` | 分辨率 | 视频分辨率 | `2160P` |
| `video_codec` | 视频编码 | 视频编码 | `H.265` |
| `audio_codec` | 音频编码 | 音频编码 | `DTS-HD MA` |
| `audio_channels` | 音频声道数 | 原始声道数量 | `6` |
| `audio_channels_label` | 声道 | 格式化后的声道，例如 5.1 | `5.1` |
| `hdr_type` | HDR | HDR/Dolby Vision 类型 | `Dolby Vision` |
| `source_type` | 片源 | WEB-DL、BluRay 等片源类型 | `WEB-DL` |
| `frame_rate` | 帧率 | 视频帧率 | `23.976fps` |
| `container` | 封装格式 | MKV、MP4 等媒体封装格式 | `MKV` |
| `release_group` | 制作组 | 资源发布组 | `FRDS` |
| `web_source` | 平台来源 | Netflix、Disney+ 等平台 | `Netflix` |
| `quality` | 质量摘要 | 自动拼接分辨率、片源、编码、HDR 等 | `2160P / WEB-DL / H.265 / Dolby Vision` |
| `quality_comment` | 画质点评 | 按 Dolby Vision、HDR、4K、1080P 优先级生成；四档文案可在当前模板中独立修改或清空关闭 | `Dolby Vision 动态画面：逐场景优化明暗与色彩，明暗过渡更细腻。` |

<a id="library_organize_fail"></a>

### 整理失败 `library_organize_fail`

一个或多个整理失败项目的列表通知。所属大类：`library_organize`（文件整理通知）；聚合：**支持**；TMDB 头图来源：**无**。

图片规则：整理失败聚合不使用媒体图片；自动模式使用“整理失败”默认图，自定义模式使用已验证链接，关闭模式发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
⚠️ 整理失败{% if failure_count %}｜{{ failure_count }} 项{% endif %}
```

**正文**

```jinja
{% if failure_details %}{{ failure_details }}
{% elif error_message %}🧾 {{ error_message }}
{% else %}{{ message_text }}
{% endif %}{% if target_path %}📂 目标：{{ target_path }}
{% endif %}🕐 {{ time_range or now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `message_title` | 默认消息标题 | 业务在套用自定义模板前生成的完整标题 | `📚 新入库 · 三体` |
| `message_text` | 默认消息正文 | 业务在套用自定义模板前生成的完整正文 | `📂 季集：S01E01-E03` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `original_text` | 默认正文别名 | message_text 的兼容别名 | `📂 季集：S01E01-E03` |
| `err_msg` | 错误别名 | error_message 的兼容别名 | `目标目录不可写` |

#### 订阅

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `action` | 订阅动作 | added、landed 或 partial | `landed` |

#### 整理

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `action_text` | 整理动作 | 整理完成、整理跳过或整理失败 | `整理完成` |
| `detail_msg` | 整理详情 | 整理或洗版过程产生的详细说明 | `已替换为更高质量版本` |
| `is_wash` | 是否洗版 | 当前整理事件是否属于洗版流程 | `true` |
| `wash_status` | 洗版状态 | 洗版成功、跳过或失败 | `洗版完成` |
| `wash_reason` | 洗版原因 | 质量比较或洗版失败原因 | `新资源质量更高` |

#### 状态

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `status` | 媒体状态 | 媒体或任务原始状态 | `Ended` |
| `error_message` | 错误信息 | 失败原因 | `目标目录不可写` |

#### 媒体

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `title` | 标题 | 媒体、任务或资源标题 | `三体` |
| `show_name` | 剧名 | 剧集聚合时使用的系列名称 | `三体` |

#### 文件

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `file_name` | 文件名 | 文件或 STRM 名称 | `三体.S01E01.mkv` |
| `source_path` | 源路径 | 整理输入路径 | `/downloads/demo.mkv` |
| `target_path` | 目标路径 | 整理或文件操作目标路径 | `/media/TV/三体` |

#### 任务

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `failure_count` | 失败项数 | 当前整理失败汇总包含的失败项目数量 | `3` |
| `failure_details` | 失败明细 | 整理失败聚合后的精简多行列表 | `• 三体.S01E01.mkv — 目标目录不可写` |

#### 聚合

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `aggregation_count` | 聚合数 | 当前聚合卡片的事件数量 | `3` |
| `started_at` | 开始时间 | 聚合窗口第一条事件时间 | `08-12 20:29` |
| `ended_at` | 结束时间 | 聚合窗口最后一条事件时间 | `08-12 20:30` |

<a id="library_quality_scan"></a>

### 质量扫描 `library_quality_scan`

Emby 媒体质量扫描汇总。所属大类：`library_organize`（文件整理通知）；聚合：**不支持**；TMDB 头图来源：**无**。

图片规则：质量扫描汇总没有 TMDB 图片来源；自动模式使用“质量扫描”默认图，自定义模式使用已验证链接，关闭模式发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
🎞️ 质量扫描完成｜发现 {{ problem_count }} 项问题
```

**正文**

```jinja
📊 共 {{ total_count }} 项 · 正常 {{ normal_count }} · 问题 {{ problem_count }}
{% if elapsed %}⏱️ 耗时 {{ elapsed }}
{% endif %}🕐 {{ now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `message_title` | 默认消息标题 | 业务在套用自定义模板前生成的完整标题 | `📚 新入库 · 三体` |
| `message_text` | 默认消息正文 | 业务在套用自定义模板前生成的完整正文 | `📂 季集：S01E01-E03` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `original_text` | 默认正文别名 | message_text 的兼容别名 | `📂 季集：S01E01-E03` |

#### 任务

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `task_name` | 任务名 | 扫描或后台任务名称 | `缺集扫描` |
| `task_type` | 任务类型 | 扫描检测等任务分类 | `扫描检测` |
| `normal_count` | 正常数 | 扫描正常项目数量 | `120` |
| `problem_count` | 问题数 | 扫描问题项目数量 | `3` |
| `total_count` | 总数 | 扫描项目总数 | `123` |

#### 状态

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `elapsed` | 耗时 | 操作耗时 | `12.6s` |
| `status_text` | 状态文本 | 完成、失败、部分成功等 | `完成` |
| `status_emoji` | 状态图标 | 与当前状态对应的 emoji | `✅` |

<a id="library_missing_scan"></a>

### 缺集扫描 `library_missing_scan`

多 Emby 实例缺集检测汇总。所属大类：`library_organize`（文件整理通知）；聚合：**不支持**；TMDB 头图来源：**无**。

图片规则：缺集扫描汇总没有 TMDB 图片来源；自动模式使用“缺集扫描”默认图，自定义模式使用已验证链接，关闭模式发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
🧩 缺集扫描完成｜{{ problem_count }} 部待补
```

**正文**

```jinja
📚 已检查 {{ total_count }} 部 · 完整 {{ normal_count }} · 缺集 {{ problem_count }}
{% if result_details %}{{ result_details }}
{% endif %}{% if elapsed %}⏱️ 耗时 {{ elapsed }}
{% endif %}🕐 {{ now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `message_title` | 默认消息标题 | 业务在套用自定义模板前生成的完整标题 | `📚 新入库 · 三体` |
| `message_text` | 默认消息正文 | 业务在套用自定义模板前生成的完整正文 | `📂 季集：S01E01-E03` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `original_text` | 默认正文别名 | message_text 的兼容别名 | `📂 季集：S01E01-E03` |

#### 任务

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `task_name` | 任务名 | 扫描或后台任务名称 | `缺集扫描` |
| `task_type` | 任务类型 | 扫描检测等任务分类 | `扫描检测` |
| `normal_count` | 正常数 | 扫描正常项目数量 | `120` |
| `problem_count` | 问题数 | 扫描问题项目数量 | `3` |
| `total_count` | 总数 | 扫描项目总数 | `123` |
| `result_details` | 结果详情 | 扫描结果的多行详情 | `【客厅】《三体》缺2集` |

#### 状态

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `elapsed` | 耗时 | 操作耗时 | `12.6s` |
| `status_text` | 状态文本 | 完成、失败、部分成功等 | `完成` |
| `status_emoji` | 状态图标 | 与当前状态对应的 emoji | `✅` |

<a id="strm_generate"></a>

### STRM 生成 `strm_generate`

STRM 批量生成目录树。所属大类：`library_organize`（文件整理通知）；聚合：**支持**；TMDB 头图来源：**无**。

图片规则：STRM 生成事件没有 TMDB 图片来源；自动模式使用“STRM 生成”默认图，自定义模式使用已验证链接，关闭模式发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
📺 STRM 已生成{% if file_count %}｜{{ file_count }} 个{% endif %}
```

**正文**

```jinja
📊 生成数量：{{ file_count }} 个 STRM
{% if strm_tree %}📂 完整路径（点击展开）：
{{ strm_tree }}
{% elif strm_path %}📂 完整路径（点击展开）：
{{ strm_path }}
{% endif %}
🕐 {{ time_range or now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |

#### 媒体

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `show_name` | 剧名 | 剧集聚合时使用的系列名称 | `三体` |
| `season_episode` | 季集 | 单集或聚合后的季集范围 | `S01E01-E03` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `season_fmt` | 季集别名 | season_episode 的兼容别名 | `S01E01-E03` |

#### 文件

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `file_name` | 文件名 | 文件或 STRM 名称 | `三体.S01E01.mkv` |
| `strm_path` | STRM 完整路径 | 本批次第一项生成后的完整 STRM 路径 | `/媒体库/电视剧/三体/Season 01/三体.S01E01.strm` |

#### STRM

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `strm_tree` | 完整路径目录树 | 本批次全部完整 STRM 路径组成的目录树；超长时在单条消息内截断 | `媒体库<br>└ 媒体库<br>  └ 电视剧<br>    └ 三体` |

#### 聚合

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `file_count` | 文件数 | 当前聚合卡片包含的文件或项目数量 | `3` |
| `aggregation_count` | 聚合数 | 当前聚合卡片的事件数量 | `3` |
| `started_at` | 开始时间 | 聚合窗口第一条事件时间 | `08-12 20:29` |
| `ended_at` | 结束时间 | 聚合窗口最后一条事件时间 | `08-12 20:30` |

<a id="share_receive"></a>

### 分享转存 `share_receive`

115 分享链接转存结果。所属大类：`file_transfer`（文件操作通知）；聚合：**不支持**；TMDB 头图来源：**无**。

图片规则：分享转存结果没有 TMDB 图片来源；自动模式使用“分享转存”默认图，自定义模式使用已验证链接，关闭模式发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
📥 分享转存{{ status_text }}{% if file_name %}｜{{ file_name }}{% endif %}
```

**正文**

```jinja
📊 成功 {{ success_count }} · 失败 {{ failed_count }}{% if elapsed %} · {{ elapsed }}{% endif %}
{% if transfer_source %}📡 来源：{{ transfer_source }}
{% endif %}{% if target_path %}📂 目标：{{ target_path }}
{% endif %}{% if error_message %}⚠️ {{ error_message }}
{% endif %}🕐 {{ now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `message_title` | 默认消息标题 | 业务在套用自定义模板前生成的完整标题 | `📚 新入库 · 三体` |
| `message_text` | 默认消息正文 | 业务在套用自定义模板前生成的完整正文 | `📂 季集：S01E01-E03` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |
| `content` | 业务正文 | 业务提供的原始正文别名 | `任务执行完成` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `original_text` | 默认正文别名 | message_text 的兼容别名 | `📂 季集：S01E01-E03` |
| `err_msg` | 错误别名 | error_message 的兼容别名 | `目标目录不可写` |

#### 文件操作

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `operation_type` | 操作类型 | 转存、离线下载、秒传等 | `TG 自动转存` |
| `transfer_source` | 操作来源 | 触发文件操作的来源 | `TG 自动转存` |
| `share_code` | 分享码 | 115 分享码 | `abc123` |

#### 文件

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `file_name` | 文件名 | 文件或 STRM 名称 | `三体.S01E01.mkv` |
| `target_path` | 目标路径 | 整理或文件操作目标路径 | `/media/TV/三体` |

#### 状态

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `success_count` | 成功数 | 成功处理的项目数量 | `8` |
| `failed_count` | 失败数 | 失败处理的项目数量 | `1` |
| `status_text` | 状态文本 | 完成、失败、部分成功等 | `完成` |
| `status_emoji` | 状态图标 | 与当前状态对应的 emoji | `✅` |
| `error_message` | 错误信息 | 失败原因 | `目标目录不可写` |
| `elapsed` | 耗时 | 操作耗时 | `12.6s` |

<a id="offline_download"></a>

### 离线下载 `offline_download`

115 离线任务批量添加结果。所属大类：`file_transfer`（文件操作通知）；聚合：**不支持**；TMDB 头图来源：**无**。

图片规则：离线下载结果没有 TMDB 图片来源；自动模式使用“离线下载”默认图，自定义模式使用已验证链接，关闭模式发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
☁️ 离线下载{{ status_text }}{% if url_count %}｜{{ url_count }} 个链接{% endif %}
```

**正文**

```jinja
📊 成功 {{ success_count }} · 失败 {{ failed_count }}{% if elapsed %} · {{ elapsed }}{% endif %}
{% if target_path %}📂 保存到：{{ target_path }}
{% endif %}{% if transfer_source %}📡 来源：{{ transfer_source }}
{% endif %}{% if error_message %}⚠️ {{ error_message }}
{% endif %}🕐 {{ now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `message_title` | 默认消息标题 | 业务在套用自定义模板前生成的完整标题 | `📚 新入库 · 三体` |
| `message_text` | 默认消息正文 | 业务在套用自定义模板前生成的完整正文 | `📂 季集：S01E01-E03` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |
| `content` | 业务正文 | 业务提供的原始正文别名 | `任务执行完成` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `original_text` | 默认正文别名 | message_text 的兼容别名 | `📂 季集：S01E01-E03` |
| `err_msg` | 错误别名 | error_message 的兼容别名 | `目标目录不可写` |

#### 文件操作

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `operation_type` | 操作类型 | 转存、离线下载、秒传等 | `TG 自动转存` |
| `transfer_source` | 操作来源 | 触发文件操作的来源 | `TG 自动转存` |
| `url_count` | 链接数 | 本次处理的链接数量 | `9` |

#### 文件

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `file_name` | 文件名 | 文件或 STRM 名称 | `三体.S01E01.mkv` |
| `target_path` | 目标路径 | 整理或文件操作目标路径 | `/media/TV/三体` |

#### 状态

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `success_count` | 成功数 | 成功处理的项目数量 | `8` |
| `failed_count` | 失败数 | 失败处理的项目数量 | `1` |
| `status_text` | 状态文本 | 完成、失败、部分成功等 | `完成` |
| `status_emoji` | 状态图标 | 与当前状态对应的 emoji | `✅` |
| `error_message` | 错误信息 | 失败原因 | `目标目录不可写` |
| `elapsed` | 耗时 | 操作耗时 | `12.6s` |

<a id="tg_auto_transfer"></a>

### TG 自动转存 `tg_auto_transfer`

TG 频道资源自动转存结果。所属大类：`file_transfer`（文件操作通知）；聚合：**不支持**；TMDB 头图来源：**无**。

图片规则：TG 自动转存结果没有 TMDB 图片来源；自动模式使用“TG 自动转存”默认图，自定义模式使用已验证链接，关闭模式发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
📲 TG 自动转存{{ status_text }}{% if file_name %}｜{{ file_name }}{% endif %}
```

**正文**

```jinja
{% if source_name %}📣 频道：{{ source_name }}
{% endif %}📦 成功 {{ success_count }} · 失败 {{ failed_count }}
{% if target_path %}📂 目标：{{ target_path }}
{% endif %}{% if error_message %}⚠️ {{ error_message }}
{% endif %}🕐 {{ now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `message_title` | 默认消息标题 | 业务在套用自定义模板前生成的完整标题 | `📚 新入库 · 三体` |
| `message_text` | 默认消息正文 | 业务在套用自定义模板前生成的完整正文 | `📂 季集：S01E01-E03` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |
| `content` | 业务正文 | 业务提供的原始正文别名 | `任务执行完成` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `original_text` | 默认正文别名 | message_text 的兼容别名 | `📂 季集：S01E01-E03` |
| `err_msg` | 错误别名 | error_message 的兼容别名 | `目标目录不可写` |

#### 文件操作

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `operation_type` | 操作类型 | 转存、离线下载、秒传等 | `TG 自动转存` |
| `transfer_source` | 操作来源 | 触发文件操作的来源 | `TG 自动转存` |
| `source_name` | 来源名称 | 频道、账号或任务名称 | `资源频道` |

#### 文件

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `file_name` | 文件名 | 文件或 STRM 名称 | `三体.S01E01.mkv` |
| `target_path` | 目标路径 | 整理或文件操作目标路径 | `/media/TV/三体` |

#### 状态

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `success_count` | 成功数 | 成功处理的项目数量 | `8` |
| `failed_count` | 失败数 | 失败处理的项目数量 | `1` |
| `status_text` | 状态文本 | 完成、失败、部分成功等 | `完成` |
| `status_emoji` | 状态图标 | 与当前状态对应的 emoji | `✅` |
| `error_message` | 错误信息 | 失败原因 | `目标目录不可写` |
| `elapsed` | 耗时 | 操作耗时 | `12.6s` |

<a id="tg_auto_offline"></a>

### TG 自动离线 `tg_auto_offline`

TG 频道链接自动离线结果。所属大类：`file_transfer`（文件操作通知）；聚合：**不支持**；TMDB 头图来源：**无**。

图片规则：TG 自动离线结果没有 TMDB 图片来源；自动模式使用“TG 自动离线”默认图，自定义模式使用已验证链接，关闭模式发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
🧲 TG 自动离线{{ status_text }}{% if file_name %}｜{{ file_name }}{% endif %}
```

**正文**

```jinja
{% if source_name %}📣 频道：{{ source_name }}
{% endif %}{% if url_count %}🔗 链接：{{ url_count }} 个
{% endif %}📊 成功 {{ success_count }} · 失败 {{ failed_count }}
{% if target_path %}📂 目标：{{ target_path }}
{% endif %}{% if error_message %}⚠️ {{ error_message }}
{% endif %}🕐 {{ now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `message_title` | 默认消息标题 | 业务在套用自定义模板前生成的完整标题 | `📚 新入库 · 三体` |
| `message_text` | 默认消息正文 | 业务在套用自定义模板前生成的完整正文 | `📂 季集：S01E01-E03` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |
| `content` | 业务正文 | 业务提供的原始正文别名 | `任务执行完成` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `original_text` | 默认正文别名 | message_text 的兼容别名 | `📂 季集：S01E01-E03` |
| `err_msg` | 错误别名 | error_message 的兼容别名 | `目标目录不可写` |

#### 文件操作

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `operation_type` | 操作类型 | 转存、离线下载、秒传等 | `TG 自动转存` |
| `transfer_source` | 操作来源 | 触发文件操作的来源 | `TG 自动转存` |
| `source_name` | 来源名称 | 频道、账号或任务名称 | `资源频道` |
| `url_count` | 链接数 | 本次处理的链接数量 | `9` |

#### 文件

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `file_name` | 文件名 | 文件或 STRM 名称 | `三体.S01E01.mkv` |
| `target_path` | 目标路径 | 整理或文件操作目标路径 | `/media/TV/三体` |

#### 状态

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `success_count` | 成功数 | 成功处理的项目数量 | `8` |
| `failed_count` | 失败数 | 失败处理的项目数量 | `1` |
| `status_text` | 状态文本 | 完成、失败、部分成功等 | `完成` |
| `status_emoji` | 状态图标 | 与当前状态对应的 emoji | `✅` |
| `error_message` | 错误信息 | 失败原因 | `目标目录不可写` |
| `elapsed` | 耗时 | 操作耗时 | `12.6s` |

<a id="tg_video_download"></a>

### TG 视频下载 `tg_video_download`

TG 频道视频下载到本地的结果。所属大类：`file_transfer`（文件操作通知）；聚合：**不支持**；TMDB 头图来源：**无**。

图片规则：TG 视频下载结果没有 TMDB 图片来源；自动模式使用“TG 视频下载”默认图，自定义模式使用已验证链接，关闭模式发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
🎬 TG 视频下载{{ status_text }}{% if file_name %}｜{{ file_name }}{% endif %}
```

**正文**

```jinja
{% if source_name %}📣 频道：{{ source_name }}
{% endif %}{% if target_path %}📂 文件：{{ target_path }}
{% endif %}{% if total_size %}💾 大小：{{ total_size }}
{% endif %}{% if error_message %}⚠️ {{ error_message }}
{% endif %}🕐 {{ now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `message_title` | 默认消息标题 | 业务在套用自定义模板前生成的完整标题 | `📚 新入库 · 三体` |
| `message_text` | 默认消息正文 | 业务在套用自定义模板前生成的完整正文 | `📂 季集：S01E01-E03` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |
| `content` | 业务正文 | 业务提供的原始正文别名 | `任务执行完成` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `original_text` | 默认正文别名 | message_text 的兼容别名 | `📂 季集：S01E01-E03` |
| `err_msg` | 错误别名 | error_message 的兼容别名 | `目标目录不可写` |
| `size` | 大小别名 | 格式化后的 total_size 兼容别名 | `9.25GB` |

#### 文件操作

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `operation_type` | 操作类型 | 转存、离线下载、秒传等 | `TG 自动转存` |
| `transfer_source` | 操作来源 | 触发文件操作的来源 | `TG 自动转存` |
| `source_name` | 来源名称 | 频道、账号或任务名称 | `资源频道` |

#### 文件

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `file_name` | 文件名 | 文件或 STRM 名称 | `三体.S01E01.mkv` |
| `target_path` | 目标路径 | 整理或文件操作目标路径 | `/media/TV/三体` |

#### 状态

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `success_count` | 成功数 | 成功处理的项目数量 | `8` |
| `failed_count` | 失败数 | 失败处理的项目数量 | `1` |
| `status_text` | 状态文本 | 完成、失败、部分成功等 | `完成` |
| `status_emoji` | 状态图标 | 与当前状态对应的 emoji | `✅` |
| `error_message` | 错误信息 | 失败原因 | `目标目录不可写` |
| `elapsed` | 耗时 | 操作耗时 | `12.6s` |

#### 聚合

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `file_size` | 文件字节数 | 单文件大小或聚合前原始大小 | `3310703957` |
| `total_size` | 总大小 | 格式化后的聚合文件总大小 | `9.25GB` |
| `total_size_bytes` | 总字节数 | 未格式化的聚合文件总大小 | `9932111872` |

<a id="account_migration"></a>

### 多号云迁移 `account_migration`

115 多账号云端秒传任务结果。所属大类：`file_transfer`（文件操作通知）；聚合：**不支持**；TMDB 头图来源：**无**。

图片规则：多账号云迁移结果没有 TMDB 图片来源；自动模式使用“账号迁移”默认图，自定义模式使用已验证链接，关闭模式发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
🔁 多号云迁移{{ status_text }}{% if file_name %}｜{{ file_name }}{% endif %}
```

**正文**

```jinja
📊 成功 {{ success_count }} · 失败 {{ failed_count }}{% if skipped_count %} · 跳过 {{ skipped_count }}{% endif %}
{% if scanned_count %}🔎 扫描：{{ scanned_count }} 个
{% endif %}{% if total_size %}💾 秒传：{{ total_size }}
{% endif %}{% if target_path %}🎯 目标：{{ target_path }}
{% endif %}{% if elapsed %}⏱️ {{ elapsed }}
{% endif %}{% if error_message %}⚠️ {{ error_message }}
{% endif %}🕐 {{ now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `message_title` | 默认消息标题 | 业务在套用自定义模板前生成的完整标题 | `📚 新入库 · 三体` |
| `message_text` | 默认消息正文 | 业务在套用自定义模板前生成的完整正文 | `📂 季集：S01E01-E03` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |
| `content` | 业务正文 | 业务提供的原始正文别名 | `任务执行完成` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `original_text` | 默认正文别名 | message_text 的兼容别名 | `📂 季集：S01E01-E03` |
| `err_msg` | 错误别名 | error_message 的兼容别名 | `目标目录不可写` |
| `size` | 大小别名 | 格式化后的 total_size 兼容别名 | `9.25GB` |

#### 文件操作

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `operation_type` | 操作类型 | 转存、离线下载、秒传等 | `TG 自动转存` |
| `transfer_source` | 操作来源 | 触发文件操作的来源 | `TG 自动转存` |

#### 文件

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `file_name` | 文件名 | 文件或 STRM 名称 | `三体.S01E01.mkv` |
| `target_path` | 目标路径 | 整理或文件操作目标路径 | `/media/TV/三体` |

#### 状态

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `success_count` | 成功数 | 成功处理的项目数量 | `8` |
| `failed_count` | 失败数 | 失败处理的项目数量 | `1` |
| `status_text` | 状态文本 | 完成、失败、部分成功等 | `完成` |
| `status_emoji` | 状态图标 | 与当前状态对应的 emoji | `✅` |
| `error_message` | 错误信息 | 失败原因 | `目标目录不可写` |
| `elapsed` | 耗时 | 操作耗时 | `12.6s` |
| `scanned_count` | 扫描数 | 任务扫描到的项目总数 | `20` |
| `skipped_count` | 跳过数 | 任务中跳过的项目数量 | `7` |

#### 聚合

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `total_size` | 总大小 | 格式化后的聚合文件总大小 | `9.25GB` |
| `total_size_bytes` | 总字节数 | 未格式化的聚合文件总大小 | `9932111872` |

<a id="ed2k_task"></a>

### ED2K 任务 `ed2k_task`

ED2K 生成、上报或发送任务结果。所属大类：`file_transfer`（文件操作通知）；聚合：**不支持**；TMDB 头图来源：**无**。

图片规则：ED2K 任务结果没有 TMDB 图片来源；自动模式使用“ED2K 任务”默认图，自定义模式使用已验证链接，关闭模式发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
🔗 ED2K 任务{{ status_text }}{% if title %}｜{{ title }}{% endif %}
```

**正文**

```jinja
{% if media_type %}🎬 {{ media_type }}{% if tmdb_id %} · TMDB {{ tmdb_id }}{% endif %}
{% endif %}📦 成功 {{ success_count }} · 失败 {{ failed_count }}{% if file_count %} · 共 {{ file_count }}{% endif %}
{% if total_size %}💾 {{ total_size }}
{% endif %}{% if transfer_source %}🧭 {{ transfer_source }}
{% endif %}{% if elapsed %}⏱️ {{ elapsed }}
{% endif %}{% if error_message %}⚠️ {{ error_message }}
{% endif %}🕐 {{ now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `message_title` | 默认消息标题 | 业务在套用自定义模板前生成的完整标题 | `📚 新入库 · 三体` |
| `message_text` | 默认消息正文 | 业务在套用自定义模板前生成的完整正文 | `📂 季集：S01E01-E03` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |
| `content` | 业务正文 | 业务提供的原始正文别名 | `任务执行完成` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `original_text` | 默认正文别名 | message_text 的兼容别名 | `📂 季集：S01E01-E03` |
| `err_msg` | 错误别名 | error_message 的兼容别名 | `目标目录不可写` |
| `size` | 大小别名 | 格式化后的 total_size 兼容别名 | `9.25GB` |

#### 文件操作

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `operation_type` | 操作类型 | 转存、离线下载、秒传等 | `TG 自动转存` |
| `transfer_source` | 操作来源 | 触发文件操作的来源 | `TG 自动转存` |

#### 文件

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `file_name` | 文件名 | 文件或 STRM 名称 | `三体.S01E01.mkv` |
| `target_path` | 目标路径 | 整理或文件操作目标路径 | `/media/TV/三体` |

#### 状态

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `success_count` | 成功数 | 成功处理的项目数量 | `8` |
| `failed_count` | 失败数 | 失败处理的项目数量 | `1` |
| `status_text` | 状态文本 | 完成、失败、部分成功等 | `完成` |
| `status_emoji` | 状态图标 | 与当前状态对应的 emoji | `✅` |
| `error_message` | 错误信息 | 失败原因 | `目标目录不可写` |
| `elapsed` | 耗时 | 操作耗时 | `12.6s` |

#### 媒体

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `title` | 标题 | 媒体、任务或资源标题 | `三体` |
| `media_type` | 媒体类型 | 电影、电视剧或音乐 | `电视剧` |
| `tmdb_id` | TMDB ID | TMDB 媒体编号 | `204541` |

#### 聚合

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `file_count` | 文件数 | 当前聚合卡片包含的文件或项目数量 | `3` |
| `total_size` | 总大小 | 格式化后的聚合文件总大小 | `9.25GB` |
| `total_size_bytes` | 总字节数 | 未格式化的聚合文件总大小 | `9932111872` |

#### 账号

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `details` | 附加详情 | 账号事件附加信息 | `获得 5 积分` |

<a id="media_auto_share"></a>

### 媒体自动分享 `media_auto_share`

入库媒体自动创建 115 分享结果。所属大类：`file_transfer`（文件操作通知）；聚合：**不支持**；TMDB 头图来源：**可能有**。

图片规则：媒体分享明确匹配到 TMDB 时优先使用其海报；自动模式无 TMDB 时使用“媒体自动分享”默认图，自定义模式改用已验证链接，关闭模式无 TMDB 时发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
📤 媒体自动分享{{ status_text }}｜{{ title }}
```

**正文**

```jinja
{% if media_type or tmdb_id %}🎬 {{ media_type }}{% if tmdb_id %} · TMDB {{ tmdb_id }}{% endif %}
{% endif %}{% if file_count or total_size %}📦 {{ file_count }} 个文件{% if total_size %} · {{ total_size }}{% endif %}
{% endif %}{% if quality %}🎞️ {{ quality }}
{% endif %}{% if target_path %}🎯 {{ target_path }}
{% endif %}{% if details %}📝 {{ details }}
{% endif %}🕐 {{ now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `message_title` | 默认消息标题 | 业务在套用自定义模板前生成的完整标题 | `📚 新入库 · 三体` |
| `message_text` | 默认消息正文 | 业务在套用自定义模板前生成的完整正文 | `📂 季集：S01E01-E03` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |
| `content` | 业务正文 | 业务提供的原始正文别名 | `任务执行完成` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `original_text` | 默认正文别名 | message_text 的兼容别名 | `📂 季集：S01E01-E03` |
| `size` | 大小别名 | 格式化后的 total_size 兼容别名 | `9.25GB` |
| `err_msg` | 错误别名 | error_message 的兼容别名 | `目标目录不可写` |

#### 媒体

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `title` | 标题 | 媒体、任务或资源标题 | `三体` |
| `media_type` | 媒体类型 | 电影、电视剧或音乐 | `电视剧` |
| `year` | 年份 | 媒体发行年份 | `2023` |
| `tmdb_id` | TMDB ID | TMDB 媒体编号 | `204541` |
| `tmdb_media_type` | TMDB 类型 | movie 或 tv | `tv` |
| `poster_url` | 海报地址 | 通知卡片使用的海报 URL | `https://image.tmdb.org/t/p/w500/demo.jpg` |
| `image_url` | 图片地址 | 通知图片 URL，通常与 poster_url 相同 | `https://image.tmdb.org/t/p/w500/demo.jpg` |

#### 文件

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `file_name` | 文件名 | 文件或 STRM 名称 | `三体.S01E01.mkv` |
| `target_path` | 目标路径 | 整理或文件操作目标路径 | `/media/TV/三体` |

#### 媒体链接

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `tmdb_link` | TMDB 文字链接 | 显示为可点击的“TMDB”，真实详情页地址不会显示在消息正文中 | `TMDB（可点击）` |
| `tmdb_link_start` | TMDB 自定义文字开始 | 为自定义文字添加TMDB详情页超链接，必须与结束变量成对使用 | `{{ tmdb_link_start }}查看 TMDB{{ tmdb_link_end }}` |
| `tmdb_link_end` | TMDB 自定义文字结束 | 结束TMDB文字超链接范围 | `{{ tmdb_link_end }}` |
| `imdb_id` | IMDb ID | 当前电影或整部剧的 IMDb title ID；缺失时为空 | `tt13016388` |
| `imdb_link` | IMDb 文字链接 | 显示为可点击的“IMDb”，真实详情页地址不会显示在消息正文中 | `IMDb（可点击）` |
| `imdb_link_start` | IMDb 自定义文字开始 | 为自定义文字添加IMDb详情页超链接，必须与结束变量成对使用 | `{{ imdb_link_start }}查看 IMDb{{ imdb_link_end }}` |
| `imdb_link_end` | IMDb 自定义文字结束 | 结束IMDb文字超链接范围 | `{{ imdb_link_end }}` |

#### 聚合

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `file_count` | 文件数 | 当前聚合卡片包含的文件或项目数量 | `3` |
| `total_size` | 总大小 | 格式化后的聚合文件总大小 | `9.25GB` |
| `total_size_bytes` | 总字节数 | 未格式化的聚合文件总大小 | `9932111872` |

#### 质量

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `quality` | 质量摘要 | 自动拼接分辨率、片源、编码、HDR 等 | `2160P / WEB-DL / H.265 / Dolby Vision` |
| `quality_comment` | 画质点评 | 按 Dolby Vision、HDR、4K、1080P 优先级生成；四档文案可在当前模板中独立修改或清空关闭 | `Dolby Vision 动态画面：逐场景优化明暗与色彩，明暗过渡更细腻。` |

#### 文件操作

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `operation_type` | 操作类型 | 转存、离线下载、秒传等 | `TG 自动转存` |
| `share_code` | 分享码 | 115 分享码 | `abc123` |

#### 状态

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `success_count` | 成功数 | 成功处理的项目数量 | `8` |
| `failed_count` | 失败数 | 失败处理的项目数量 | `1` |
| `status_text` | 状态文本 | 完成、失败、部分成功等 | `完成` |
| `status_emoji` | 状态图标 | 与当前状态对应的 emoji | `✅` |
| `error_message` | 错误信息 | 失败原因 | `目标目录不可写` |

#### 账号

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `details` | 附加详情 | 账号事件附加信息 | `获得 5 积分` |

<a id="account_cookie_invalid"></a>

### Cookie 失效 `account_cookie_invalid`

115 账号 Cookie 健康检查异常。所属大类：`account_status`（账号状态）；聚合：**不支持**；TMDB 头图来源：**无**。

图片规则：Cookie 失效事件没有 TMDB 图片来源；自动模式使用“账号失效”默认图，自定义模式使用已验证链接，关闭模式发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
🔑 115 Cookie 失效{% if account_name %}｜{{ account_name }}{% endif %}
```

**正文**

```jinja
{% if status_message %}⚠️ {{ status_message }}
{% endif %}{% if details %}{{ details }}
{% endif %}🕐 {{ now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `message_title` | 默认消息标题 | 业务在套用自定义模板前生成的完整标题 | `📚 新入库 · 三体` |
| `message_text` | 默认消息正文 | 业务在套用自定义模板前生成的完整正文 | `📂 季集：S01E01-E03` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |
| `content` | 业务正文 | 业务提供的原始正文别名 | `任务执行完成` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `original_text` | 默认正文别名 | message_text 的兼容别名 | `📂 季集：S01E01-E03` |
| `username` | 用户名别名 | user_name 或 account_name 的兼容别名 | `Alice` |
| `err_msg` | 错误别名 | error_message 的兼容别名 | `目标目录不可写` |

#### 账号

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `status_type` | 账号事件 | 签到成功、Cookie 失效等 | `签到成功` |
| `status_message` | 账号状态 | 账号状态详情 | `今日签到成功` |
| `account_name` | 账号名 | 115 或癫影账号显示名 | `主账号` |
| `details` | 附加详情 | 账号事件附加信息 | `获得 5 积分` |

#### 状态

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `status_text` | 状态文本 | 完成、失败、部分成功等 | `完成` |
| `status_emoji` | 状态图标 | 与当前状态对应的 emoji | `✅` |
| `error_message` | 错误信息 | 失败原因 | `目标目录不可写` |

<a id="account_switched"></a>

### 账号切换 `account_switched`

115 当前活动账号发生切换。所属大类：`account_status`（账号状态）；聚合：**不支持**；TMDB 头图来源：**无**。

图片规则：账号切换事件没有 TMDB 图片来源；自动模式使用“账号切换”默认图，自定义模式使用已验证链接，关闭模式发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
🔄 115 账号已切换{% if account_name %}｜{{ account_name }}{% endif %}
```

**正文**

```jinja
{% if status_message %}{{ status_message }}
{% endif %}{% if operation_type %}🧭 {{ operation_type }}
{% endif %}{% if details %}📝 {{ details }}
{% endif %}🕐 {{ now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `message_title` | 默认消息标题 | 业务在套用自定义模板前生成的完整标题 | `📚 新入库 · 三体` |
| `message_text` | 默认消息正文 | 业务在套用自定义模板前生成的完整正文 | `📂 季集：S01E01-E03` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |
| `content` | 业务正文 | 业务提供的原始正文别名 | `任务执行完成` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `original_text` | 默认正文别名 | message_text 的兼容别名 | `📂 季集：S01E01-E03` |
| `username` | 用户名别名 | user_name 或 account_name 的兼容别名 | `Alice` |

#### 账号

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `status_type` | 账号事件 | 签到成功、Cookie 失效等 | `签到成功` |
| `status_message` | 账号状态 | 账号状态详情 | `今日签到成功` |
| `account_name` | 账号名 | 115 或癫影账号显示名 | `主账号` |
| `details` | 附加详情 | 账号事件附加信息 | `获得 5 积分` |

#### 状态

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `status_text` | 状态文本 | 完成、失败、部分成功等 | `完成` |
| `status_emoji` | 状态图标 | 与当前状态对应的 emoji | `✅` |

#### 文件操作

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `operation_type` | 操作类型 | 转存、离线下载、秒传等 | `TG 自动转存` |

<a id="account_checkin"></a>

### 115 签到 `account_checkin`

115 账号签到结果。所属大类：`account_status`（账号状态）；聚合：**不支持**；TMDB 头图来源：**无**。

图片规则：115 签到结果没有 TMDB 图片来源；自动模式使用“账号签到”默认图，自定义模式使用已验证链接，关闭模式发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
{{ status_emoji or '✅' }} 115 签到{% if account_name %}｜{{ account_name }}{% endif %}
```

**正文**

```jinja
{% if status_message %}{{ status_message }}
{% endif %}{% if points %}🎁 本次积分：{{ points }}
{% endif %}{% if total_points %}🏆 总积分：{{ total_points }}
{% endif %}{% if checkin_count or checkin_points %}📊 本机累计{% if checkin_count %} {{ checkin_count }} 次{% endif %}{% if checkin_points %} · {{ checkin_points }} 积分{% endif %}
{% endif %}🕐 {{ now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `message_title` | 默认消息标题 | 业务在套用自定义模板前生成的完整标题 | `📚 新入库 · 三体` |
| `message_text` | 默认消息正文 | 业务在套用自定义模板前生成的完整正文 | `📂 季集：S01E01-E03` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |
| `content` | 业务正文 | 业务提供的原始正文别名 | `任务执行完成` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `original_text` | 默认正文别名 | message_text 的兼容别名 | `📂 季集：S01E01-E03` |
| `username` | 用户名别名 | user_name 或 account_name 的兼容别名 | `Alice` |

#### 账号

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `status_type` | 账号事件 | 签到成功、Cookie 失效等 | `签到成功` |
| `status_message` | 账号状态 | 账号状态详情 | `今日签到成功` |
| `account_name` | 账号名 | 115 或癫影账号显示名 | `主账号` |
| `details` | 附加详情 | 账号事件附加信息 | `获得 5 积分` |
| `points` | 获得积分 | 本次签到获得积分 | `5` |
| `total_points` | 总积分 | 签到后的总积分 | `120` |
| `checkin_count` | 签到次数 | 本机累计签到次数 | `26` |
| `checkin_points` | 累计签到积分 | 本机累计签到积分 | `130` |

#### 状态

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `status_text` | 状态文本 | 完成、失败、部分成功等 | `完成` |
| `status_emoji` | 状态图标 | 与当前状态对应的 emoji | `✅` |

<a id="dianying_checkin"></a>

### 癫影签到 `dianying_checkin`

癫影账号自动签到结果。所属大类：`account_status`（账号状态）；聚合：**不支持**；TMDB 头图来源：**无**。

图片规则：癫影签到结果没有 TMDB 图片来源；自动模式使用“癫影签到”默认图，自定义模式使用已验证链接，关闭模式发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
🎞️ 癫影签到{% if account_name %}｜{{ account_name }}{% endif %}
```

**正文**

```jinja
{% if status_message %}{{ status_message }}
{% endif %}{% if points %}🎁 本次积分：{{ points }}
{% endif %}{% if total_points %}🏆 总积分：{{ total_points }}
{% endif %}{% if details %}🎲 {{ details }}
{% endif %}{% if checkin_count %}📅 累计签到：{{ checkin_count }} 次
{% endif %}🕐 {{ now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `message_title` | 默认消息标题 | 业务在套用自定义模板前生成的完整标题 | `📚 新入库 · 三体` |
| `message_text` | 默认消息正文 | 业务在套用自定义模板前生成的完整正文 | `📂 季集：S01E01-E03` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |
| `content` | 业务正文 | 业务提供的原始正文别名 | `任务执行完成` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `original_text` | 默认正文别名 | message_text 的兼容别名 | `📂 季集：S01E01-E03` |
| `username` | 用户名别名 | user_name 或 account_name 的兼容别名 | `Alice` |

#### 账号

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `status_type` | 账号事件 | 签到成功、Cookie 失效等 | `签到成功` |
| `status_message` | 账号状态 | 账号状态详情 | `今日签到成功` |
| `account_name` | 账号名 | 115 或癫影账号显示名 | `主账号` |
| `details` | 附加详情 | 账号事件附加信息 | `获得 5 积分` |
| `points` | 获得积分 | 本次签到获得积分 | `5` |
| `total_points` | 总积分 | 签到后的总积分 | `120` |
| `checkin_count` | 签到次数 | 本机累计签到次数 | `26` |
| `checkin_points` | 累计签到积分 | 本机累计签到积分 | `130` |

#### 状态

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `status_text` | 状态文本 | 完成、失败、部分成功等 | `完成` |
| `status_emoji` | 状态图标 | 与当前状态对应的 emoji | `✅` |

<a id="container_update_check"></a>

### 容器更新检查 `container_update_check`

DianCupLite 容器镜像检查结果。所属大类：`container_update`（容器更新）；聚合：**不支持**；TMDB 头图来源：**无**。

图片规则：容器更新检查没有 TMDB 图片来源；自动模式使用“容器检查”默认图，自定义模式使用已验证链接，关闭模式发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
🔎 容器更新检查｜可更新 {{ available_count }} 个
```

**正文**

```jinja
📦 共 {{ container_count }} 个 · 已最新 {{ current_count }}{% if check_error_count %} · 检查失败 {{ check_error_count }}{% endif %}
{% if details %}{{ details }}
{% endif %}🕐 {{ now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `message_title` | 默认消息标题 | 业务在套用自定义模板前生成的完整标题 | `📚 新入库 · 三体` |
| `message_text` | 默认消息正文 | 业务在套用自定义模板前生成的完整正文 | `📂 季集：S01E01-E03` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |
| `content` | 业务正文 | 业务提供的原始正文别名 | `任务执行完成` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `original_text` | 默认正文别名 | message_text 的兼容别名 | `📂 季集：S01E01-E03` |

#### 容器更新

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `update_phase` | 更新阶段 | 容器更新流程阶段：check 或 result | `result` |
| `container_count` | 容器数 | 本次检查或更新涉及的容器数量 | `6` |
| `available_count` | 可更新数 | 检查到有新版本的容器数量 | `2` |
| `current_count` | 当前数 | 检查到已是最新版本的容器数量 | `4` |
| `check_error_count` | 检查失败数 | 检查版本时失败的容器数量 | `0` |

#### 账号

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `details` | 附加详情 | 账号事件附加信息 | `获得 5 积分` |

<a id="container_update_result"></a>

### 容器更新结果 `container_update_result`

DianCupLite 容器更新执行结果。所属大类：`container_update`（容器更新）；聚合：**不支持**；TMDB 头图来源：**无**。

图片规则：容器更新结果没有 TMDB 图片来源；自动模式使用“容器更新”默认图，自定义模式使用已验证链接，关闭模式发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
🐳 容器更新结果｜成功 {{ success_count }} · 失败 {{ failed_count }}
```

**正文**

```jinja
{% if trigger %}⚙️ 触发：{{ trigger }}
{% endif %}📦 共处理 {{ container_count }} 个容器
{% if details %}{{ details }}
{% endif %}🕐 {{ now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `message_title` | 默认消息标题 | 业务在套用自定义模板前生成的完整标题 | `📚 新入库 · 三体` |
| `message_text` | 默认消息正文 | 业务在套用自定义模板前生成的完整正文 | `📂 季集：S01E01-E03` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |
| `content` | 业务正文 | 业务提供的原始正文别名 | `任务执行完成` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `original_text` | 默认正文别名 | message_text 的兼容别名 | `📂 季集：S01E01-E03` |

#### 容器更新

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `update_phase` | 更新阶段 | 容器更新流程阶段：check 或 result | `result` |
| `trigger` | 触发方式 | 触发检查或更新的来源 | `scheduled` |
| `container_count` | 容器数 | 本次检查或更新涉及的容器数量 | `6` |

#### 状态

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `success_count` | 成功数 | 成功处理的项目数量 | `8` |
| `failed_count` | 失败数 | 失败处理的项目数量 | `1` |

#### 账号

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `details` | 附加详情 | 账号事件附加信息 | `获得 5 积分` |

<a id="container_update_test"></a>

### 容器通知测试 `container_update_test`

验证 DianCupLite 通知通道。所属大类：`container_update`（容器更新）；聚合：**不支持**；TMDB 头图来源：**无**。

图片规则：容器通知测试没有 TMDB 图片来源；自动模式使用“容器检查”默认图，自定义模式使用已验证链接，关闭模式发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
🧪 DianCupLite 通知测试
```

**正文**

```jinja
✅ {{ test_message or '容器更新消息推送通道工作正常' }}
🕐 {{ now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `message_title` | 默认消息标题 | 业务在套用自定义模板前生成的完整标题 | `📚 新入库 · 三体` |
| `message_text` | 默认消息正文 | 业务在套用自定义模板前生成的完整正文 | `📂 季集：S01E01-E03` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |
| `content` | 业务正文 | 业务提供的原始正文别名 | `任务执行完成` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `original_text` | 默认正文别名 | message_text 的兼容别名 | `📂 季集：S01E01-E03` |

#### 容器更新

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `update_phase` | 更新阶段 | 容器更新流程阶段：check 或 result | `result` |

#### 测试

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `test_message` | 测试说明 | 测试通知用于确认通道可用的说明 | `容器更新消息推送通道工作正常` |

<a id="dian115_self_update"></a>

### Dian115 自更新 `dian115_self_update`

Dian115 主容器自更新完成或失败。所属大类：`container_update`（容器更新）；聚合：**不支持**；TMDB 头图来源：**无**。

图片规则：Dian115 自更新事件没有 TMDB 图片来源；自动模式使用“DIAN115 更新”默认图，自定义模式使用已验证链接，关闭模式发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
{% if update_success %}✅ Dian115 更新成功{% else %}❌ Dian115 更新失败{% endif %}
```

**正文**

```jinja
{% if current_version %}📦 当前版本：{{ current_version }}
{% endif %}{% if build_channel %}🏷️ 通道：{{ build_channel }}{% if build_commit %} · {{ build_commit }}{% endif %}
{% endif %}{% if error_message %}⚠️ {{ error_message }}
{% elif details %}{{ details }}
{% endif %}🕐 {{ now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `message_title` | 默认消息标题 | 业务在套用自定义模板前生成的完整标题 | `📚 新入库 · 三体` |
| `message_text` | 默认消息正文 | 业务在套用自定义模板前生成的完整正文 | `📂 季集：S01E01-E03` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |
| `content` | 业务正文 | 业务提供的原始正文别名 | `任务执行完成` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `original_text` | 默认正文别名 | message_text 的兼容别名 | `📂 季集：S01E01-E03` |

#### 容器更新

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `update_phase` | 更新阶段 | 容器更新流程阶段：check 或 result | `result` |

#### 自更新

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `update_success` | 更新成功 | Dian115 自更新是否完成 | `true` |
| `current_version` | 当前版本 | Dian115 当前运行版本 | `v2.8.12` |
| `build_channel` | 构建通道 | Dian115 当前构建通道 | `stable` |
| `build_commit` | 构建提交 | Dian115 当前 Git 提交短哈希 | `a1b2c3d4e5f6` |

#### 账号

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `details` | 附加详情 | 账号事件附加信息 | `获得 5 积分` |

#### 状态

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `error_message` | 错误信息 | 失败原因 | `目标目录不可写` |

<a id="proxy_health_daily_report"></a>

### Clash 监控日报 `proxy_health_daily_report`

Clash/Mihomo 每日请求、切换和流量汇总。所属大类：`proxy_health`（Clash 监控）；聚合：**不支持**；TMDB 头图来源：**无**。

图片规则：Clash 监控日报没有 TMDB 图片来源；自动模式使用“监控日报”默认图，自定义模式使用已验证链接，关闭模式发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
🌐 Clash 监控日报｜{{ day }}
```

**正文**

```jinja
📡 请求 {{ request_count }} · 失败 {{ failure_count }} · 成功率 {{ success_rate }}
🔀 切换 {{ switch_count }} 次{% if auto_switch_count or manual_switch_count %}（自动 {{ auto_switch_count }} / 手动 {{ manual_switch_count }}）{% endif %}
⬆️ 上传 {{ upload_bytes }} B · ⬇️ 下载 {{ download_bytes }} B
🕐 {{ now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `message_title` | 默认消息标题 | 业务在套用自定义模板前生成的完整标题 | `📚 新入库 · 三体` |
| `message_text` | 默认消息正文 | 业务在套用自定义模板前生成的完整正文 | `📂 季集：S01E01-E03` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |
| `content` | 业务正文 | 业务提供的原始正文别名 | `任务执行完成` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `original_text` | 默认正文别名 | message_text 的兼容别名 | `📂 季集：S01E01-E03` |

#### 媒体

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `title` | 标题 | 媒体、任务或资源标题 | `三体` |

#### 报表

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `day` | 报表日期 | Clash 日报统计日期 | `2026-08-11` |

#### 代理监控

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `request_count` | 请求数 | 日报统计的代理请求数量 | `1200` |
| `success_rate` | 成功率 | 日报统计的代理请求成功率 | `99.8%` |
| `switch_count` | 切换次数 | 代理节点自动与手动切换总次数 | `4` |
| `auto_switch_count` | 自动切换数 | 代理自动切换次数 | `3` |
| `manual_switch_count` | 手动切换数 | 代理手动切换次数 | `1` |
| `upload_bytes` | 上传字节数 | 日报统计的上传流量（字节） | `1073741824` |
| `download_bytes` | 下载字节数 | 日报统计的下载流量（字节） | `8589934592` |

#### 任务

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `failure_count` | 失败项数 | 当前整理失败汇总包含的失败项目数量 | `3` |

<a id="proxy_health_test_report"></a>

### Clash 测试报告 `proxy_health_test_report`

验证 Clash 监控通知并展示当日快照。所属大类：`proxy_health`（Clash 监控）；聚合：**不支持**；TMDB 头图来源：**无**。

图片规则：Clash 测试报告没有 TMDB 图片来源；自动模式使用“监控日报”默认图，自定义模式使用已验证链接，关闭模式发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
🧪 Clash 测试报告｜{{ day }}
```

**正文**

```jinja
✅ 通知通道可用
📡 今日请求 {{ request_count }} · 失败 {{ failure_count }} · 成功率 {{ success_rate }}
🔀 自动切换 {{ auto_switch_count }} · 手动切换 {{ manual_switch_count }}
🕐 {{ now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `message_title` | 默认消息标题 | 业务在套用自定义模板前生成的完整标题 | `📚 新入库 · 三体` |
| `message_text` | 默认消息正文 | 业务在套用自定义模板前生成的完整正文 | `📂 季集：S01E01-E03` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |
| `content` | 业务正文 | 业务提供的原始正文别名 | `任务执行完成` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `original_text` | 默认正文别名 | message_text 的兼容别名 | `📂 季集：S01E01-E03` |

#### 媒体

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `title` | 标题 | 媒体、任务或资源标题 | `三体` |

#### 报表

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `day` | 报表日期 | Clash 日报统计日期 | `2026-08-11` |

#### 代理监控

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `request_count` | 请求数 | 日报统计的代理请求数量 | `1200` |
| `success_rate` | 成功率 | 日报统计的代理请求成功率 | `99.8%` |
| `switch_count` | 切换次数 | 代理节点自动与手动切换总次数 | `4` |
| `auto_switch_count` | 自动切换数 | 代理自动切换次数 | `3` |
| `manual_switch_count` | 手动切换数 | 代理手动切换次数 | `1` |
| `upload_bytes` | 上传字节数 | 日报统计的上传流量（字节） | `1073741824` |
| `download_bytes` | 下载字节数 | 日报统计的下载流量（字节） | `8589934592` |

#### 任务

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `failure_count` | 失败项数 | 当前整理失败汇总包含的失败项目数量 | `3` |

<a id="subscribe_added"></a>

### 添加订阅 `subscribe_added`

创建电影或剧集订阅。所属大类：`subscribe`（订阅通知）；聚合：**不支持**；TMDB 头图来源：**可能有**。

图片规则：订阅媒体明确匹配到 TMDB 时优先使用其海报；自动模式无 TMDB 时使用“添加订阅”默认图，自定义模式改用已验证链接，关闭模式无 TMDB 时发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
📌 已添加订阅｜{{ title_year }}{% if season_episode %} · {{ season_episode }}{% endif %}
```

**正文**

```jinja
{% if media_type %}🎬 {{ media_type }}
{% endif %}{% if needed_episodes %}🎯 待补：{{ needed_episodes }}
{% endif %}{% if channel %}📡 渠道：{{ channel }}
{% endif %}{% if rating or genres %}⭐ {{ rating }}{% if genres %} · {{ genres }}{% endif %}
{% endif %}🕐 {{ now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |

#### 媒体

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `title` | 标题 | 媒体、任务或资源标题 | `三体` |
| `raw_title` | 原始标题 | 规范化前的标题，可能包含年份或 TMDB 标记 | `三体 (2023) -{tmdbid=204541}` |
| `title_year` | 标题年份 | 自动组合的“标题 (年份)” | `三体 (2023)` |
| `media_type` | 媒体类型 | 电影、电视剧或音乐 | `电视剧` |
| `year` | 年份 | 媒体发行年份 | `2023` |
| `season_episode` | 季集 | 单集或聚合后的季集范围 | `S01E01-E03` |
| `rating` | 评分 | 媒体评分 | `8.7` |
| `genres` | 类型标签 | 媒体类型或标签 | `剧情 / 科幻` |
| `overview` | 简介 | 媒体简介，可能为空 | `人类文明首次收到来自宇宙深处的信息。` |
| `poster_url` | 海报地址 | 通知卡片使用的海报 URL | `https://image.tmdb.org/t/p/w500/demo.jpg` |
| `image_url` | 图片地址 | 通知图片 URL，通常与 poster_url 相同 | `https://image.tmdb.org/t/p/w500/demo.jpg` |
| `tmdb_id` | TMDB ID | TMDB 媒体编号 | `204541` |
| `tmdb_media_type` | TMDB 类型 | movie 或 tv | `tv` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `type` | 类型别名 | media_type 的兼容别名 | `电视剧` |
| `season_fmt` | 季集别名 | season_episode 的兼容别名 | `S01E01-E03` |
| `vote_average` | 评分别名 | rating 的兼容别名 | `8.7` |
| `category` | 类别 | 优先为媒体库名称，否则回退到类型标签 | `电视剧` |

#### 媒体链接

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `tmdb_link` | TMDB 文字链接 | 显示为可点击的“TMDB”，真实详情页地址不会显示在消息正文中 | `TMDB（可点击）` |
| `tmdb_link_start` | TMDB 自定义文字开始 | 为自定义文字添加TMDB详情页超链接，必须与结束变量成对使用 | `{{ tmdb_link_start }}查看 TMDB{{ tmdb_link_end }}` |
| `tmdb_link_end` | TMDB 自定义文字结束 | 结束TMDB文字超链接范围 | `{{ tmdb_link_end }}` |
| `imdb_id` | IMDb ID | 当前电影或整部剧的 IMDb title ID；缺失时为空 | `tt13016388` |
| `imdb_link` | IMDb 文字链接 | 显示为可点击的“IMDb”，真实详情页地址不会显示在消息正文中 | `IMDb（可点击）` |
| `imdb_link_start` | IMDb 自定义文字开始 | 为自定义文字添加IMDb详情页超链接，必须与结束变量成对使用 | `{{ imdb_link_start }}查看 IMDb{{ imdb_link_end }}` |
| `imdb_link_end` | IMDb 自定义文字结束 | 结束IMDb文字超链接范围 | `{{ imdb_link_end }}` |

#### 订阅

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `channel` | 订阅渠道 | PT 或聚合订阅 | `PT` |
| `needed_episodes` | 待补集 | 添加订阅时的目标待补集，或部分完成后仍待补的集数 | `9-12` |

<a id="subscribe_landed"></a>

### 订阅完成 `subscribe_landed`

订阅资源已完整入库。所属大类：`subscribe`（订阅通知）；聚合：**不支持**；TMDB 头图来源：**可能有**。

图片规则：已完成订阅明确匹配到 TMDB 时优先使用其海报；自动模式无 TMDB 时使用“订阅完成”默认图，自定义模式改用已验证链接，关闭模式无 TMDB 时发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
🎉 订阅完成｜{{ title_year }}{% if season_episode %} · {{ season_episode }}{% endif %}
```

**正文**

```jinja
{% if landed_via %}📡 入库来源：{{ landed_via }}{% if landed_tag %} · {{ landed_tag }}{% endif %}
{% endif %}{% if rating or genres %}⭐ {{ rating }}{% if genres %} · {{ genres }}{% endif %}
{% endif %}🕐 {{ now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |

#### 媒体

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `title` | 标题 | 媒体、任务或资源标题 | `三体` |
| `raw_title` | 原始标题 | 规范化前的标题，可能包含年份或 TMDB 标记 | `三体 (2023) -{tmdbid=204541}` |
| `title_year` | 标题年份 | 自动组合的“标题 (年份)” | `三体 (2023)` |
| `media_type` | 媒体类型 | 电影、电视剧或音乐 | `电视剧` |
| `year` | 年份 | 媒体发行年份 | `2023` |
| `season_episode` | 季集 | 单集或聚合后的季集范围 | `S01E01-E03` |
| `rating` | 评分 | 媒体评分 | `8.7` |
| `genres` | 类型标签 | 媒体类型或标签 | `剧情 / 科幻` |
| `overview` | 简介 | 媒体简介，可能为空 | `人类文明首次收到来自宇宙深处的信息。` |
| `poster_url` | 海报地址 | 通知卡片使用的海报 URL | `https://image.tmdb.org/t/p/w500/demo.jpg` |
| `image_url` | 图片地址 | 通知图片 URL，通常与 poster_url 相同 | `https://image.tmdb.org/t/p/w500/demo.jpg` |
| `tmdb_id` | TMDB ID | TMDB 媒体编号 | `204541` |
| `tmdb_media_type` | TMDB 类型 | movie 或 tv | `tv` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `type` | 类型别名 | media_type 的兼容别名 | `电视剧` |
| `season_fmt` | 季集别名 | season_episode 的兼容别名 | `S01E01-E03` |
| `vote_average` | 评分别名 | rating 的兼容别名 | `8.7` |
| `category` | 类别 | 优先为媒体库名称，否则回退到类型标签 | `电视剧` |

#### 媒体链接

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `tmdb_link` | TMDB 文字链接 | 显示为可点击的“TMDB”，真实详情页地址不会显示在消息正文中 | `TMDB（可点击）` |
| `tmdb_link_start` | TMDB 自定义文字开始 | 为自定义文字添加TMDB详情页超链接，必须与结束变量成对使用 | `{{ tmdb_link_start }}查看 TMDB{{ tmdb_link_end }}` |
| `tmdb_link_end` | TMDB 自定义文字结束 | 结束TMDB文字超链接范围 | `{{ tmdb_link_end }}` |
| `imdb_id` | IMDb ID | 当前电影或整部剧的 IMDb title ID；缺失时为空 | `tt13016388` |
| `imdb_link` | IMDb 文字链接 | 显示为可点击的“IMDb”，真实详情页地址不会显示在消息正文中 | `IMDb（可点击）` |
| `imdb_link_start` | IMDb 自定义文字开始 | 为自定义文字添加IMDb详情页超链接，必须与结束变量成对使用 | `{{ imdb_link_start }}查看 IMDb{{ imdb_link_end }}` |
| `imdb_link_end` | IMDb 自定义文字结束 | 结束IMDb文字超链接范围 | `{{ imdb_link_end }}` |

#### 订阅

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `landed_via` | 入库来源 | 订阅资源最终来源 | `PT` |
| `landed_tag` | 资源质量 | 订阅入库资源的质量标签 | `2160P WEB-DL` |

<a id="subscribe_partial"></a>

### 订阅部分完成 `subscribe_partial`

剧集订阅已有部分集数入库，并显示仍待补集数。所属大类：`subscribe`（订阅通知）；聚合：**不支持**；TMDB 头图来源：**可能有**。

图片规则：部分完成订阅明确匹配到 TMDB 时优先使用其海报；自动模式无 TMDB 时使用“订阅部分完成”默认图，自定义模式改用已验证链接，关闭模式无 TMDB 时发送纯文本。

<details>
<summary>查看系统默认模板</summary>

**标题**

```jinja
📥 订阅更新｜{{ title_year }}{% if season_episode %} · {{ season_episode }}{% endif %}
```

**正文**

```jinja
{% if covered_episodes %}✅ 已覆盖：{{ covered_episodes }}
{% endif %}{% if needed_episodes %}🎯 仍待补：{{ needed_episodes }}
{% endif %}{% if landed_via %}📡 入库来源：{{ landed_via }}{% if landed_tag %} · {{ landed_tag }}{% endif %}
{% endif %}🕐 {{ now }}
```

</details>

#### 通用

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `notification_type` | 事件类型 | 当前实际事件键，例如 subscribe_landed | `media_library` |
| `parent_type` | 通知大类 | 控制通知开关的父类型 | `media_library` |
| `now` | 当前时间 | 消息渲染时间 | `2026-08-12 20:30:00` |
| `time_range` | 时间范围 | 聚合消息的开始至结束时间；非聚合消息回退为当前时间 | `08-12 20:29 – 08-12 20:30` |

#### 媒体

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `title` | 标题 | 媒体、任务或资源标题 | `三体` |
| `raw_title` | 原始标题 | 规范化前的标题，可能包含年份或 TMDB 标记 | `三体 (2023) -{tmdbid=204541}` |
| `title_year` | 标题年份 | 自动组合的“标题 (年份)” | `三体 (2023)` |
| `media_type` | 媒体类型 | 电影、电视剧或音乐 | `电视剧` |
| `year` | 年份 | 媒体发行年份 | `2023` |
| `season_episode` | 季集 | 单集或聚合后的季集范围 | `S01E01-E03` |
| `rating` | 评分 | 媒体评分 | `8.7` |
| `genres` | 类型标签 | 媒体类型或标签 | `剧情 / 科幻` |
| `overview` | 简介 | 媒体简介，可能为空 | `人类文明首次收到来自宇宙深处的信息。` |
| `poster_url` | 海报地址 | 通知卡片使用的海报 URL | `https://image.tmdb.org/t/p/w500/demo.jpg` |
| `image_url` | 图片地址 | 通知图片 URL，通常与 poster_url 相同 | `https://image.tmdb.org/t/p/w500/demo.jpg` |
| `tmdb_id` | TMDB ID | TMDB 媒体编号 | `204541` |
| `tmdb_media_type` | TMDB 类型 | movie 或 tv | `tv` |

#### 兼容别名

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `type` | 类型别名 | media_type 的兼容别名 | `电视剧` |
| `season_fmt` | 季集别名 | season_episode 的兼容别名 | `S01E01-E03` |
| `vote_average` | 评分别名 | rating 的兼容别名 | `8.7` |
| `category` | 类别 | 优先为媒体库名称，否则回退到类型标签 | `电视剧` |

#### 媒体链接

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `tmdb_link` | TMDB 文字链接 | 显示为可点击的“TMDB”，真实详情页地址不会显示在消息正文中 | `TMDB（可点击）` |
| `tmdb_link_start` | TMDB 自定义文字开始 | 为自定义文字添加TMDB详情页超链接，必须与结束变量成对使用 | `{{ tmdb_link_start }}查看 TMDB{{ tmdb_link_end }}` |
| `tmdb_link_end` | TMDB 自定义文字结束 | 结束TMDB文字超链接范围 | `{{ tmdb_link_end }}` |
| `imdb_id` | IMDb ID | 当前电影或整部剧的 IMDb title ID；缺失时为空 | `tt13016388` |
| `imdb_link` | IMDb 文字链接 | 显示为可点击的“IMDb”，真实详情页地址不会显示在消息正文中 | `IMDb（可点击）` |
| `imdb_link_start` | IMDb 自定义文字开始 | 为自定义文字添加IMDb详情页超链接，必须与结束变量成对使用 | `{{ imdb_link_start }}查看 IMDb{{ imdb_link_end }}` |
| `imdb_link_end` | IMDb 自定义文字结束 | 结束IMDb文字超链接范围 | `{{ imdb_link_end }}` |

#### 订阅

| 变量 | 含义 | 使用说明 | 示例值 / 写法 |
| --- | --- | --- | --- |
| `needed_episodes` | 待补集 | 添加订阅时的目标待补集，或部分完成后仍待补的集数 | `9-12` |
| `landed_via` | 入库来源 | 订阅资源最终来源 | `PT` |
| `landed_tag` | 资源质量 | 订阅入库资源的质量标签 | `2160P WEB-DL` |
| `covered_episodes` | 已覆盖集 | 部分完成时已覆盖的集数 | `1-8` |

## 常见问题

### 为什么变量在另一个模板里不能用？

每个事件只有自己的变量合同。设计器选择事件后显示的变量列表就是唯一可信清单；即使两个事件名称相近，也不保证字段相同。

### 为什么某一行只剩图标或标签？

动态值为空但固定文字仍会输出。把整行包进条件块，例如：`{% if rating %}⭐ 评分：{{ rating }}{% endif %}`。

### 为什么 TMDB / IMDb 没显示？

媒体没有对应 ID 时文字链接变量为空。剧集事件需要整部剧的 Series ID；请使用 `{% if tmdb_link %}...{% endif %}`。

### 为什么没有画质点评？

只有上文列出的 8 个事件支持 `quality_comment`，并且需要质量数据能识别到 Dolby Vision、HDR/HLG、4K/UHD/2160P 或 1080P/Full HD/FHD/1920x1080。若对应档位文案已在当前事件模板中清空，该档按设计不显示点评。

### 为什么导入后没有立即生效？

导入只是应用到当前编辑状态。审核完成后还要点击页面底部“保存通知配置”。

### 为什么长内容被截断？

Telegram 单条消息有长度限制。Dian115 会安全截断超长内容，避免拆成多条；长路径、错误和 STRM 树建议使用可展开引用，优先保留消息主体的可读性。
