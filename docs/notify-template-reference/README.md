# Dian115 Telegram 通知模板参考包

这里提供 5 套可以直接导入 Dian115 的 Telegram 通知模板。每套模板都覆盖当前 39 个独立通知事件，保留事件自身的变量契约，不使用“通用模板”拼接不同事件的数据。

## 五套风格

| 文件 | 风格 | 适合场景 |
| --- | --- | --- |
| `notify-templates-formal-report.json` | 正式运维报告 | 管理员频道、审计留档、家庭服务器值班 |
| `notify-templates-cinema-premiere.json` | 影院首映 | 电影/剧集为主的媒体频道，强调观影氛围 |
| `notify-templates-cyber-terminal.json` | 赛博终端 | 自动化任务、下载、容器和代理监控频道 |
| `notify-templates-weird-lab.json` | 实验室玩梗 | 想要有点古怪、有趣，但仍需完整信息的频道 |
| `notify-templates-minimal-editorial.json` | 极简编辑 | 只保留重点字段、追求低噪音和留白的频道 |

每套包都包含相同的 39 个 key，因此可以整包导入，也可以在导入预览中只勾选需要的事件。五套包的差别只在标题、排版和文案气质；事件可用变量、富文本安全规则、图片策略保持一致。

## 导入方式

1. 打开 Dian115 的「通知设置 → Telegram 推送 → 推送模板设计器」。
2. 选择「导入模板」，上传任意一个 JSON 文件。
3. 在预览中检查模板名称、标题和正文，只勾选要导入的通知类型。
4. 确认导入后，按需继续在设计器中调整文案、变量和富文本格式。

导入包的格式标识为 `dian115-notify-template-package`，版本为 `1`。`customized: true` 表示导入该条完整自定义内容；`image_mode: "auto"` 表示沿用站内图片策略，不把默认图片地址写进可分享的模板文件。

## 图片策略

- 模板文件不会暴露默认图片 URL，也不会携带 `image_url` 字段。
- 发送时由 Dian115 后端决定图片：有 TMDB 媒体图时使用媒体图；没有 TMDB 图时使用该通知类型的默认图；用户选择自定义图片时使用已通过预览校验的链接；用户选择无图片时发送纯文本。
- 参考包中的 `image_mode: "auto"` 适合直接导入。导入后仍可对每个通知单独选择自动、指定图片或无图片。
- TMDB 和 IMDb 只使用文字超链变量（`tmdb_link`、`imdb_link`），不会把原始长 URL 打进正文。

## 变量写法

模板使用 Jinja 风格表达式：

```text
{{ title }}
{% if season_episode %} · {{ season_episode }}{% endif %}
```

常见写法：

```text
{{ title or '未命名资源' }}
{% if overview %}{{ tg_expandable_quote_start }}{{ overview }}{{ tg_expandable_quote_end }}{% endif %}
{% if tmdb_link or imdb_link %}🔎 {% if tmdb_link %}{{ tmdb_link }}{% endif %}{% if tmdb_link and imdb_link %} · {% endif %}{% if imdb_link %}{{ imdb_link }}{% endif %}{% endif %}
```

### Telegram 富文本变量

所有事件都可以使用这些成对变量（开始和结束必须配对）：

| 用途 | 变量 |
| --- | --- |
| 粗体 | `tg_bold_start` / `tg_bold_end` |
| 斜体、下划线、删除线 | `tg_italic_start` / `tg_italic_end`、`tg_underline_start` / `tg_underline_end`、`tg_strike_start` / `tg_strike_end` |
| 剧透 | `tg_spoiler_start` / `tg_spoiler_end` |
| 行内代码、代码块 | `tg_code_start` / `tg_code_end`、`tg_pre_start` / `tg_pre_end` |
| 引用、可折叠引用 | `tg_quote_start` / `tg_quote_end`、`tg_expandable_quote_start` / `tg_expandable_quote_end` |
| 换行、空行 | `tg_newline`、`tg_blankline` |

### 媒体链接

有 TMDB/IMDb 身份的事件提供 `tmdb_link` 和 `imdb_link`。它们已经是“文字超链”，例如直接写 `{{ tmdb_link }}` 会显示为可点击的「TMDB」文字；不要改用 `tmdb_url` 或 `imdb_url`，以免把长地址显示给用户。

### 画质点评

支持画质点评的事件（播放开始、播放结束、入库新增/更新/删除、整理完成、整理跳过、媒体自动分享）都附带四档可编辑文案：`dolby_vision`、`hdr`、`4k`、`1080p`。模板正文通过 `{{ quality_comment }}` 显示匹配当前媒体的点评。例如默认文案可以改成更技术化、影评化或幽默的版本。

## 覆盖的通知事件

播放：`playback_start`、`playback_stop` ；媒体库：`media_library_add`、`media_library_update`、`media_library_delete` ；Emby 账户安全：`emby_user_authenticated`、`emby_user_authentication_failed`、`emby_user_locked_out`、`emby_user_created`、`emby_user_deleted`、`emby_user_password_changed`、`emby_user_policy_updated` ；文件整理：`library_organize_success`、`library_organize_skip`、`library_organize_fail`、`library_quality_scan`、`library_missing_scan`、`strm_generate` ；文件操作：`share_receive`、`offline_download`、`tg_auto_transfer`、`tg_auto_offline`、`tg_video_download`、`account_migration`、`ed2k_task`、`media_auto_share` ；账号状态：`account_cookie_invalid`、`account_switched`、`account_checkin`、`dianying_checkin` ；容器：`container_update_check`、`container_update_result`、`container_update_test`、`dian115_self_update` ；代理：`proxy_health_daily_report`、`proxy_health_test_report` ；订阅：`subscribe_added`、`subscribe_landed`、`subscribe_partial`。

## 自定义建议

- 先复制一套最接近频道气质的包，再只改动标题和正文，保留条件判断，避免空字段留下孤行。
- 长路径、简介和错误详情优先放进 `tg_pre_*` 或 `tg_expandable_quote_*`，Telegram 会保持可读性，Dian115 仍会按消息上限统一截断，不拆成多条消息。
- 一条通知只使用该事件设计器显示的变量。导入器会拒绝未知变量、未闭合的富文本标签和未通过图片预览校验的自定义图片。

