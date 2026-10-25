/* DIAN115 Wiki · 用户使用指南。 */
window.DIAN_WIKI = {
  "version": "5.0.42",
  "demo": "https://madbrolab.github.io/dian115/demo/",
  "codeSamples": {
    "dian-host-compose": {
      "label": "compose.yml · Host 网络（推荐）",
      "text": "services:\n  dian115:\n    image: madbrolab/dian115:latest\n    container_name: dian115\n    restart: unless-stopped\n    network_mode: host\n    environment:\n      - PORT=8095\n      - TZ=Asia/Shanghai\n    volumes:\n      - ./config:/config\n      - ./dian115AI:/dian115AI\n      # 替换为自己的宿主机目录\n      - /mnt/user/media:/媒体库\n      - /mnt/cache/CloudNAS:/CloudNAS:rslave"
    },
    "dian-start": {
      "label": "启动与检查 · 在 compose.yml 所在目录执行",
      "text": "mkdir -p config dian115AI\ndocker compose pull dian115\ndocker compose up -d dian115\ndocker compose ps\ndocker compose logs --tail=200 dian115"
    },
    "dian-bridge-compose": {
      "label": "compose.yml · 桥接网络（备选）",
      "text": "services:\n  dian115:\n    image: madbrolab/dian115:latest\n    container_name: dian115\n    restart: unless-stopped\n    ports:\n      - \"8095:8095\"\n      - \"8098:8098\" # 第一个 Emby 代理实例，按实际配置调整\n      # - \"8111:8111\" # 启用 RAVE 时按实际配置映射\n      # - \"4534:4534\" # 保留原音乐协议服务时按需映射\n    environment:\n      - PORT=8095\n      - TZ=Asia/Shanghai\n    volumes:\n      - ./config:/config\n      - ./dian115AI:/dian115AI\n      # 替换为自己的宿主机目录\n      - /mnt/user/media:/媒体库\n      - /mnt/cache/CloudNAS:/CloudNAS:rslave"
    },
    "cd2-compose": {
      "label": "compose.cd2.yml · CloudDrive2",
      "text": "services:\n  clouddrive2:\n    image: cloudnas/clouddrive2:latest\n    container_name: clouddrive2\n    restart: unless-stopped\n    network_mode: host\n    pid: host\n    privileged: true\n    devices:\n      - /dev/fuse:/dev/fuse\n    environment:\n      - CLOUDDRIVE_HOME=/Config\n      - TZ=Asia/Shanghai\n    volumes:\n      - ./cd2-config:/Config\n      - /mnt/cache/CloudNAS:/CloudNAS:shared"
    },
    "cd2-start": {
      "label": "准备目录与启动 · Linux / NAS 示例",
      "text": "mkdir -p /mnt/cache/CloudNAS /mnt/user/media ./cd2-config\ndocker compose -f compose.cd2.yml up -d\ndocker compose -f compose.cd2.yml logs --tail=100"
    },
    "mount-check": {
      "label": "检查宿主机的挂载传播",
      "text": "findmnt -o TARGET,PROPAGATION -T /mnt/cache/CloudNAS\n# 如需将该目录单独设为共享挂载点，按宿主系统方案执行：\nmountpoint -q /mnt/cache/CloudNAS || sudo mount --bind /mnt/cache/CloudNAS /mnt/cache/CloudNAS\nsudo mount --make-rshared /mnt/cache/CloudNAS"
    },
    "shared-mounts": {
      "label": "三套容器的 volumes 配置",
      "text": "# CloudDrive2\nvolumes:\n  - /mnt/cache/CloudNAS:/CloudNAS:shared\n\n# DIAN115\nvolumes:\n  - /mnt/cache/CloudNAS:/CloudNAS:rslave\n  - /mnt/user/media:/媒体库\n\n# Emby：与 DIAN115 的宿主机目录、容器目标路径一致\nvolumes:\n  - /mnt/cache/CloudNAS:/CloudNAS:rslave\n  - /mnt/user/media:/媒体库"
    },
    "flaresolverr-compose": {
      "label": "追加到 compose.yml · 供同机 Host 模式访问",
      "text": "services:\n  # 保留原有 dian115 服务，将下面服务加入同一份文件\n  flaresolverr:\n    image: ghcr.io/flaresolverr/flaresolverr:latest\n    container_name: flaresolverr\n    restart: unless-stopped\n    ports:\n      - \"127.0.0.1:8191:8191\"\n    environment:\n      - LOG_LEVEL=info\n      - TZ=Asia/Shanghai\n    volumes:\n      - ./flaresolverr:/config\n    # DIAN115 使用 Host 网络时填写 http://127.0.0.1:8191"
    },
    "flaresolverr-start": {
      "label": "启动 FlareSolverr",
      "text": "docker compose up -d flaresolverr\ndocker compose logs --tail=100 flaresolverr"
    },
    "flaresolverr-remote": {
      "label": "独立部署时追加端口 · 使用实际内网 IP",
      "text": "# 追加到 flaresolverr 服务，替换为这台主机的实际内网 IP\nports:\n  - \"192.168.1.10:8191:8191\"\n# DIAN115 中填写 http://192.168.1.10:8191"
    },
    "database-postgresql-1": {
      "label": "准备镜像、目录和数据库",
      "text": "mkdir -p config dian115AI postgres-data"
    },
    "database-postgresql-2": {
      "label": "保存 compose.yml",
      "text": "services:\n  postgres:\n    image: postgres:18\n    container_name: dian115-postgres\n    restart: unless-stopped\n    environment:\n      POSTGRES_DB: dian115\n      POSTGRES_USER: dian115\n      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?请在 .env 填写数据库密码}\n    ports:\n      - \"127.0.0.1:15432:5432\"\n    volumes:\n      - ./postgres-data:/var/lib/postgresql\n\n  dian115:\n    image: ${DIAN115_IMAGE:?请填写支持 PostgreSQL 的镜像}\n    container_name: dian115\n    restart: unless-stopped\n    network_mode: host\n    environment:\n      PORT: \"8095\"\n      TZ: Asia/Shanghai\n      DIAN115_DB_DRIVER: pgsql\n      DIAN115_PG_DSN: ${DIAN115_PG_DSN:?请在 .env 填写数据库连接串}\n    volumes:\n      - ./config:/config\n      - ./dian115AI:/dian115AI\n      - /mnt/user/media:/媒体库\n      - /mnt/cache/CloudNAS:/CloudNAS:rslave\n"
    },
    "database-postgresql-3": {
      "label": "填写 .env 连接配置",
      "text": "# 两处密码必须相同。示例密码请自行替换；使用字母和数字可直接放入连接串。\nPOSTGRES_PASSWORD=ChangeThisPassword2026\nDIAN115_PG_DSN=postgres://dian115:ChangeThisPassword2026@127.0.0.1:15432/dian115?sslmode=disable\n# 已有指定镜像时，可填写完整镜像名；要求 v5.0.42 或更新且包含 PostgreSQL 支持。\nDIAN115_IMAGE=madbrolab/dian115:5.0.42\n"
    },
    "database-postgresql-4": {
      "label": "填写已有数据库的连接串",
      "text": "DIAN115_DB_DRIVER=pgsql\nDIAN115_PG_DSN=postgres://dian115:YourPassword@192.168.1.10:5432/dian115?sslmode=require"
    },
    "database-postgresql-5": {
      "label": "启动并完成首次设置",
      "text": "docker compose up -d postgres\ndocker compose up -d dian115\ndocker compose ps"
    },
    "database-migration-1": {
      "label": "停止旧实例并备份配置目录",
      "text": "docker compose stop dian115\ncp -a ./config \"./config-sqlite-backup-$(date +%Y%m%d-%H%M%S)\""
    },
    "database-migration-2": {
      "label": "准备空目标库并修改连接配置",
      "text": "docker compose up -d postgres"
    },
    "database-migration-3": {
      "label": "生成并执行外部迁移脚本",
      "text": "cat > migrate-to-pgsql.sh <<'SH'\n#!/bin/sh\nset -eu\ndocker compose stop dian115\ndocker compose run --rm --no-deps   --entrypoint /usr/local/bin/dian115-db   dian115 migrate --db /config/dian115.db\ndocker compose up -d dian115\nSH\nsh migrate-to-pgsql.sh"
    },
    "database-migration-4": {
      "label": "已有外部脚本时的用法",
      "text": "export DIAN115_PG_DSN='postgres://dian115:YourPassword@127.0.0.1:15432/dian115?sslmode=disable'\nsh migrate-sqlite-to-pgsql.sh --config /mnt/appdata/dian115/config --image madbrolab/dian115:5.0.42\ndocker compose up -d dian115"
    }
  },
  "groups": [
    {
      "id": "automate",
      "title": "让收藏，自动生长",
      "label": "发现与自动化",
      "icon": "spark",
      "subtitle": "从一句“想看”，到一部已入库的作品。",
      "items": [
        {
          "id": "discover",
          "title": "探索发现",
          "desc": "电影、剧集与多个资源来源，在同一个入口探索。",
          "route": "automation/discovery"
        },
        {
          "id": "subscribe",
          "title": "媒体订阅",
          "desc": "电影、剧集、演员订阅，配合来源和质量策略持续追新。",
          "route": "automation/subscriptions"
        },
        {
          "id": "calendar",
          "title": "追剧日历",
          "desc": "按日期查看订阅剧集的播出计划与更新状态。",
          "route": "automation/calendar"
        },
        {
          "id": "organize",
          "title": "媒体整理",
          "desc": "识别、刮削、分类、命名，评分洗版与多版共存。",
          "route": "automation/organizing"
        },
        {
          "id": "strm",
          "title": "STRM 与虚拟影库",
          "desc": "维护目录树与同步规则，生成轻量、可扫描的播放入口。",
          "route": "automation/portable-strm"
        }
      ]
    },
    {
      "id": "media",
      "title": "给每一份收藏，找到位置",
      "label": "媒体与资源",
      "icon": "film",
      "subtitle": "云端资源、本地文件与播放服务，相互连接。",
      "items": [
        {
          "id": "rave",
          "title": "RAVE 媒体空间",
          "desc": "内置媒体服务器与全新独立前台，连接电影、剧集、直播、音乐、电台和漫画。",
          "route": "resources/plugins/media-server"
        },
        {
          "id": "library-manager",
          "title": "媒体库管理工具",
          "desc": "统一管理 RAVE 与 Emby，按整理分类预览建库、切换层级和独立同步。",
          "route": "resources/plugins/library-manager"
        },
        {
          "id": "my-media",
          "title": "我的媒体与 Emby",
          "desc": "媒体浏览、缺集补全、质量检查、分享与多实例播放代理。",
          "route": "resources/media"
        },
        {
          "id": "files",
          "title": "文件管理",
          "desc": "目录书签、批量改名、原地刮削，以及文件整理与分享。",
          "route": "resources/files"
        },
        {
          "id": "accounts",
          "title": "115 账号配置",
          "desc": "主账号、备用 CK、目录策略、登录检查和账号运维。",
          "route": "resources/accounts"
        },
        {
          "id": "pt",
          "title": "PT 与下载管理",
          "desc": "站点认证、搜索、RSS，连接 qBittorrent 或 Transmission。",
          "route": "resources/sites"
        },
        {
          "id": "music",
          "title": "音乐中心",
          "desc": "音乐源、元数据、专辑与歌词管理，在 RAVE 中播放音乐和电台。",
          "route": "automation/music"
        }
      ]
    },
    {
      "id": "extend",
      "title": "好用，还可以更顺手",
      "label": "插件与扩展",
      "icon": "grid",
      "subtitle": "将日常的小步骤，接成自己的工作流。",
      "items": [
        {
          "id": "plugins",
          "title": "内置插件",
          "desc": "RAVE、媒体库管理、秒传、迁移、推送、字幕等 23 项内置工具。",
          "route": "resources/plugins"
        },
        {
          "id": "notifications",
          "title": "三通道通知",
          "desc": "Telegram、企业微信、微信 ClawBot 各自配置和触发。",
          "route": "resources/plugins/notifications"
        },
        {
          "id": "ai",
          "title": "点点 AI 助手",
          "desc": "解释状态、流式对话，按使用位置选择模型与管理工具。",
          "route": "control/settings"
        },
        {
          "id": "satellite",
          "title": "卫星发布树",
          "desc": "按 STRM 规则发布目录树，为客户端分配独立访问凭据。",
          "route": "control/settings"
        },
        {
          "id": "plugin-platform",
          "title": "用户插件",
          "desc": "从插件仓库管理扩展，区分第三方插件与内置能力。",
          "route": "resources/plugins"
        }
      ]
    },
    {
      "id": "operate",
      "title": "每一次运行，都有迹可循",
      "label": "控制与运维",
      "icon": "activity",
      "subtitle": "从连接状态到任务详情，理解系统正在做什么。",
      "items": [
        {
          "id": "dashboard",
          "title": "总览",
          "desc": "连接健康、系统资源、任务、下载和播放汇总。",
          "route": "overview"
        },
        {
          "id": "queue",
          "title": "任务队列与日志",
          "desc": "追踪阶段、进度、调度与原始错误，定位具体失败环节。",
          "route": "control/jobs"
        },
        {
          "id": "cache",
          "title": "缓存与数据运维",
          "desc": "TMDB、FFP、分享与播放缓存，以及实时播放与使用趋势。",
          "route": "control/cache"
        },
        {
          "id": "container",
          "title": "DianCupLite",
          "desc": "容器状态、镜像检查、更新队列和计划任务。",
          "route": "control/container-update"
        },
        {
          "id": "settings",
          "title": "系统设置",
          "desc": "CD2 / AURA、网络、安全、API、词表与 AI 提供商。",
          "route": "control/settings"
        }
      ]
    }
  ],
  "portal": [
    {
      "id": "overview",
      "title": "概览",
      "group": "core",
      "desc": "公告、账户有效期、最近入库与观影足迹。"
    },
    {
      "id": "account",
      "title": "账户中心",
      "group": "core",
      "desc": "资料、密码、续期、Telegram 绑定与邀请朋友。"
    },
    {
      "id": "115",
      "title": "115 账号",
      "group": "core",
      "desc": "独享账号扫码 / CK 绑定与检查；共享连接由管理员维护。"
    },
    {
      "id": "media",
      "title": "媒体库",
      "group": "media",
      "desc": "浏览当前 Emby 权限允许访问的电影、剧集与最近入库。"
    },
    {
      "id": "requests",
      "title": "求片",
      "group": "media",
      "desc": "搜索电影或剧集、选择季数、填写备注并跟踪处理。"
    },
    {
      "id": "server",
      "title": "服务连接",
      "group": "media",
      "desc": "服务器状态、访问线路、在线会话与个人播放缓存。"
    },
    {
      "id": "watchlist",
      "title": "想看 / 看过",
      "group": "media",
      "desc": "保存观影计划，记录看过、个人评分与短评。"
    },
    {
      "id": "history",
      "title": "播放历史",
      "group": "media",
      "desc": "按时间线回访播放记录；已结束播放计入时长。"
    },
    {
      "id": "checkin",
      "title": "签到积分",
      "group": "social",
      "desc": "签到日历、连续天数、积分余额和收支流水。"
    },
    {
      "id": "shop",
      "title": "积分商店",
      "group": "social",
      "desc": "浏览可兑换商品、使用积分并查看兑换记录。"
    },
    {
      "id": "community",
      "title": "观影社区",
      "group": "social",
      "desc": "分类发帖、回复、点赞，按最新、热门或活跃度浏览。"
    },
    {
      "id": "achievements",
      "title": "成就排行",
      "group": "social",
      "desc": "观看目标、个人成就、观看时长与播放次数排行。"
    },
    {
      "id": "badges",
      "title": "勋章收藏",
      "group": "social",
      "desc": "按稀有度和分类收藏勋章，选择佩戴展示。"
    },
    {
      "id": "resources",
      "title": "资源分享",
      "group": "social",
      "desc": "提交资源链接与版本说明，审核通过后获得积分。"
    },
    {
      "id": "messages",
      "title": "消息中心",
      "group": "support",
      "desc": "系统通知、站点动态、未读消息与批量已读。"
    },
    {
      "id": "tickets",
      "title": "工单支持",
      "group": "support",
      "desc": "按分类、优先级提交问题，与管理员持续回复沟通。"
    }
  ],
  "plugins": [
    [
      "媒体库管理工具",
      "按整理规则管理 RAVE 和 Emby 媒体库，先预览分类，再执行建库与层级调整。各实例独立保存方案、模板和自动同步设置。",
      "library-manager"
    ],
    [
      "RAVE",
      "内置媒体服务器与独立媒体空间，统一管理媒体账号与访问权限，提供影视、直播、音乐、电台和漫画入口。",
      "media-server"
    ],
    [
      "文件秒传",
      "以 SHA1 秒传本地文件到 115，支持失败时普通上传或 CD2 后处理。",
      "rapid-upload"
    ],
    [
      "外部推送",
      "接收其他项目推送的 115、ED2K 与磁力链接，按配置转存或离线。",
      "external-push"
    ],
    [
      "多号云迁移",
      "将主账号目录中目标账号缺失的内容单向补齐，支持定时与实时跟随。",
      "account-migration"
    ],
    [
      "文件清理",
      "扫描本地或 CD2 目录，按条件清理文件与文件夹，保护系统配置目录。",
      "file-cleanup"
    ],
    [
      "秘享空间",
      "将选中内容生成限时、限次短码，领取后进入转存队列。",
      "mystery-share"
    ],
    [
      "推送助手",
      "S.O. 专属：目录监听、按偏好派送、用户接力秒传与 Telegram 小程序，最多 500 个绑定账号。",
      "push-assistant"
    ],
    [
      "Telegram 频道监控",
      "独立维护资源解析、消息转发与视频保存工作流。",
      "tg-channel"
    ],
    [
      "SnowLuma QQ 监控",
      "接入 OneBot WebSocket，采集群聊 / 私聊并执行资源规则。",
      "qq-monitor"
    ],
    [
      "私聊机器人",
      "会话收件箱、网页与群组话题回复、关键词自动回复和广告拦截。",
      "tg-private-bot"
    ],
    [
      "群组管理机器人",
      "S.O. 专属：欢迎验证、防护策略、成员权限、AI 配额与审计。",
      "tg-group-bot"
    ],
    [
      "Emby 封面生成",
      "为媒体库生成统一风格封面，支持样式、字体与批量刷新。",
      "emby-cover"
    ],
    [
      "通知中心",
      "Telegram、企业微信与微信 ClawBot，事件开关和静默时段各自独立。",
      "notifications"
    ],
    [
      "每日统计海报",
      "以今日或昨日数据生成可编辑统计海报，配合独立消息模板发送。",
      "daily-report"
    ],
    [
      "PT 刷流",
      "按促销、H&R、大小、做种数与删种策略添加和维护任务。",
      "pt-brush"
    ],
    [
      "癫影",
      "以 OpenAPI Key 接入签到、分享与检索；Key 创建依赖平台 VIP。",
      "dianying"
    ],
    [
      "PT 站点统计",
      "集中查看上传、下载、分享率、魔力与做种数据。",
      "pt-site-stats"
    ],
    [
      "Emby 媒体画像",
      "读取容器、媒体流与章节，匹配 115 SHA1 并汇报 FFP 画像。",
      "emby-media-lite"
    ],
    [
      "CLASH 监控",
      "监控代理访问健康，联动 Clash / Mihomo Selector 切换节点。",
      "clash-monitor"
    ],
    [
      "AI 字幕翻译",
      "将已有非中文文本字幕翻译为中文 SRT，查看对照、任务与用量。",
      "ai-subtitle"
    ],
    [
      "视频下载器",
      "解析视频、音频与播放列表，配置格式、目录、代理和浏览器接入。",
      "video-downloader"
    ],
    [
      "STRM 助手",
      "批量替换 STRM 内容，支持正则与捕获组，先预览命中再执行。",
      "strm-helper"
    ]
  ],
  "setup": [
    {
      "title": "准备与部署",
      "short": "先给收藏一个家",
      "text": "Linux / NAS 优先推荐 Host 网络。先部署 CloudDrive2，规划 shared / rslave 挂载与媒体目录，再用推荐的 Host 配置启动 DIAN115。使用需验证的资源站时，按需加入 FlareSolverr。",
      "doc": "deploy"
    },
    {
      "title": "账号与连接",
      "short": "接通你的云端",
      "text": "初始化管理员与授权，添加 115 主账号。配置 CD2 地址与 API Token，自动读取 /CloudNAS/CloudDrive，并选择主账号实际对应的云盘。",
      "doc": "connections"
    },
    {
      "title": "媒体与规则",
      "short": "把第一部作品归好档",
      "text": "测试整理与分类，按需要生成 STRM。选择 RAVE 或已有 Emby 扫描媒体；用媒体库管理工具预览分类建库，再验证播放。",
      "doc": "first-library"
    },
    {
      "title": "自动化与扩展",
      "short": "让日常变得更轻松",
      "text": "按需加入 PT、下载器、订阅、通知、音乐与 AI。共享给其他用户时，再配置门户、访问线路与邀请码。",
      "doc": "automation"
    }
  ],
  "docs": {
    "about": {
      "title": "DIAN115 是什么",
      "kicker": "THE IDEA",
      "lead": "把云端收藏，变成触手可及的私人影音空间。",
      "sections": [
        [
          "围绕媒体的一套工作流",
          "DIAN115 是面向自托管用户的媒体自动化控制中心。它连接 115 网盘、CloudDrive2 / AURA、PT 来源与通知系统，将发现、订阅、转存、整理、元数据和 STRM 组织成可以追踪的任务，再通过 RAVE 或 Emby 回访自己的收藏。"
        ],
        [
          "组件如何协作",
          "115 提供文件、分享与离线能力；CD2 或 AURA 让云端目录可访问；DIAN115 负责识别、规则和任务编排。内置 RAVE 提供独立媒体服务和统一前台，也可以继续使用已有 Emby 实例。"
        ],
        [
          "从个人收藏到用户门户",
          "个人使用可以先完成一个账号、一条整理规则与一次播放。需要服务家庭、朋友或社区时，再加入独立门户、账号分配、求片、工单、积分与社区功能。"
        ],
        [
          "开始前需要什么",
          "准备一台可运行 Linux Docker 的主机、持久化目录，以及计划使用的外部服务账号。具体能力受授权、依赖连接和功能开关共同影响。"
        ]
      ]
    },
    "discover": {
      "title": "探索发现",
      "kicker": "DISCOVER",
      "lead": "先找到故事，再选择适合你的资源。",
      "sections": [
        [
          "媒体探索",
          "电影与剧集支持热度、上映时间、评分、类型、语言、年份和地区筛选。媒体身份由 TMDB 元数据承接，可在探索后创建订阅。"
        ],
        [
          "资源来源",
          "PT、癫影与 Telegram 频道采集是不同来源；公开索引页签提供磁力检索。来源的认证、网络和可用性分别配置，某一个来源异常不代表其他来源不可用。"
        ],
        [
          "连接到自动化",
          "选中媒体后可按来源与质量策略订阅；直接找到资源则进入下载、转存或离线链路。落地位置由账号目录与对应来源配置决定。"
        ]
      ]
    },
    "subscribe": {
      "title": "媒体订阅",
      "kicker": "FOLLOW A STORY",
      "lead": "把“想看”保存下来，让更新有一个明确的目标。",
      "sections": [
        [
          "电影、剧集与演员",
          "电影和剧集按 TMDB 身份持续追踪，剧集结合季集覆盖判断。演员订阅先确认人物，再按媒体类型、年份等条件筛选作品，可暂停、重新评估和查看排除原因。"
        ],
        [
          "来源与质量",
          "可组合癫影、PT、TG 和聚合策略；电影、剧集维护质量方案。候选按优先级比较，失败时可尝试其他来源。"
        ],
        [
          "搜索、RSS 与后处理",
          "PT 周期搜索与 RSS 匹配分别控制。下载完成后，视频或字幕可秒传到 115，失败按配置回退普通上传或 CD2 后处理。PT 下载完成与 115 后处理属于不同任务，应分别查看结果。"
        ]
      ]
    },
    "calendar": {
      "title": "追剧日历",
      "kicker": "COMING NEXT",
      "lead": "下一集什么时候来，在日历里一目了然。",
      "sections": [
        [
          "按日期回访订阅",
          "日历展示订阅剧集的播出与更新计划，帮助区分尚未播出、未找到资源、下载未完成和入库缺集。"
        ],
        [
          "排查更新状态",
          "先确认订阅是否启用与季集范围，再查看资源搜索、下载器和整理队列。播出日期不等于已经拥有可入库资源。"
        ]
      ]
    },
    "organize": {
      "title": "媒体整理",
      "kicker": "A PLACE FOR EVERYTHING",
      "lead": "文件名、身份和版本，逐步整理成一份可靠的收藏。",
      "sections": [
        [
          "识别与刮削",
          "使用词表与文件 / 路径证据提取标题、年份、季集和技术字段；TMDB 确认媒体身份，ffprobe 提供流信息。可按条件使用 AI 辅助识别。"
        ],
        [
          "路径与执行方式",
          "本地规则支持本地到本地的移动或硬链接，硬链接需要同一文件系统；CD2 规则的源和目标均位于挂载根下，由服务执行移动。不要把混合路径当成同一种规则。"
        ],
        [
          "版本决策",
          "单一版本可跳过、按大小覆盖或评分洗版；多版共存可全部保留或在 4K、DV、HDR、1080P 等槽位内竞争。历史记录保留决策结果。"
        ],
        [
          "先验证，再扩展",
          "用少量文件测试识别、命名、分类、字幕联动与版本规则。确认输出和历史后再扩大范围；第一次调试保留源文件更容易核对。"
        ]
      ]
    },
    "strm": {
      "title": "STRM 与虚拟影库",
      "kicker": "LIGHTWEIGHT LIBRARY",
      "lead": "用轻量文件，为云端内容建立稳定的播放入口。",
      "sections": [
        [
          "目录树与 STRM",
          "STRM 规则维护源目录树、输出路径、链接模式与同步状态。先全量建树，再小范围生成文件；Emby 扫描输出，播放请求交给对应代理或重定向链路。"
        ],
        [
          "同步与清理",
          "支持全量、增量、实时或定时同步，孤立清理移除已不存在的输出。反向代理场景下，生成链接使用的外部地址必须能被播放端访问。"
        ],
        [
          "虚拟影库",
          "虚拟影库可以解析外部 115 分享或已有 P1 标记，预览支持的媒体并输出跨实例使用的虚拟文件。冲突策略包括跳过、覆盖或添加序号；使用前核对输出目录。"
        ],
        [
          "旧库迁移",
          "已有 Emby 库时，先保留目录树和媒体画像，完成路径匹配、Madby / FFP 接入，再生成新 STRM 与扫描新库。"
        ]
      ]
    },
    "my-media": {
      "title": "我的媒体与 Emby",
      "kicker": "YOUR COLLECTION",
      "lead": "从媒体视角回访收藏，补齐缺集，选择准确的分享范围。",
      "sections": [
        [
          "媒体工作区",
          "浏览电影、剧集与已有版本，查看媒体统计、缺集与质量状态，选择 Emby 实例和媒体库。"
        ],
        [
          "精确分享",
          "按电影版本、剧集季度、单集和字幕选择范围，支持 115 链接、ED2K、Telegram、癫影或秘享短码。真实分享依赖文件树中的 115 身份和可转换的 Emby 路径。"
        ],
        [
          "多实例代理",
          "配置各实例后端、API Key、播放线路与路径转换。高级版最多 3 个 Emby 代理实例，S.O. 最多 6 个。Host 网络直接使用各实例设置的宿主机端口；桥接网络则需逐个映射对应端口。"
        ]
      ]
    },
    "files": {
      "title": "文件管理",
      "kicker": "KEEP IT IN ORDER",
      "lead": "把人工整理需要的最后几步，也放在同一个地方。",
      "sections": [
        [
          "浏览与基础操作",
          "容器可见目录支持面包屑、书签、列表 / 网格、排序与批量选择。提供上传、下载、预览、新建、改名、复制、移动与删除。"
        ],
        [
          "媒体操作",
          "可执行识别、原地刮削、批量改名，或交给已启用整理规则；选中内容可生成秘享码。先确认当前路径、规则和任务范围。"
        ],
        [
          "目录边界",
          "操作以容器中的实际路径为准。直接删除会作用于真实文件，不能把本地删除当作 115 回收站。"
        ]
      ]
    },
    "accounts": {
      "title": "115 账号配置",
      "kicker": "CONNECTED TO YOUR CLOUD",
      "lead": "账号、目录和连接状态，分别管理才更清楚。",
      "sections": [
        [
          "主账号池",
          "扫码添加、检查、刷新、编辑与激活账号。活跃主账号供全局客户端使用，支持自动切换、QPS、签到、空间与 VIP 状态查看。"
        ],
        [
          "备用 CK 与用途",
          "备用 CK 独立于活跃主账号，不参与主账号自动切换、签到和全局目录配置。只有明确支持备用池的功能会使用它。"
        ],
        [
          "目录策略",
          "分别设置转存、离线、秘享接收与来源默认目录。为主账号选择真实对应的 CD2 云盘，避免跨账号目录错配。"
        ],
        [
          "常见运维",
          "检查 Cookie 有效性，按需要设置安全码，维护分享记录与回收站。首次接入后通过小范围任务验证目录 CID。"
        ]
      ]
    },
    "pt": {
      "title": "PT 与下载管理",
      "kicker": "RESOURCE SOURCES",
      "lead": "认证、搜索和下载，一层一层接通。",
      "sections": [
        [
          "站点配置",
          "维护站点类型、域名、认证、代理、超时、搜索与 RSS。可以刷新上传、下载、分享率、等级、魔力和做种数据。"
        ],
        [
          "下载器",
          "连接 qBittorrent 或 Transmission，确认 WebUI、账号、默认客户端、保存路径与任务标签。先手动提交一个测试任务。"
        ],
        [
          "自动化接入",
          "搜索结果可进入订阅策略，RSS 用于持续匹配。PT 刷流会主动添加和删除任务，应在站点与下载器验证后按需求开启。"
        ]
      ]
    },
    "music": {
      "title": "音乐中心与 RAVE 音乐",
      "kicker": "A SOUNDTRACK FOR YOUR DAY",
      "lead": "后台整理曲库，前台专心听歌。",
      "sections": [
        [
          "管理音乐源",
          "在自动化 → 音乐中心添加来源，扫描并编辑歌曲、专辑、艺术家、封面与歌词。管理端负责资料与任务，RAVE 提供统一播放界面。"
        ],
        [
          "音乐与电台权限",
          "在插件中心 → RAVE 中管理媒体账号，分别开启音乐、电台和访问来源。旧音乐账号升级为统一媒体账号；同名冲突与密码准备按页面提示处理。"
        ],
        [
          "全新的音乐页面",
          "在 RAVE 选择音乐，浏览专辑、艺术家、歌曲、喜欢与歌单；支持搜索、队列、同步歌词、随机和循环。底部播放器在切换页面时继续播放，展开后可查看歌词与播放列表。"
        ],
        [
          "电台与地图",
          "电台提供公共列表、发现目录、中文分类、组合筛选、收藏与地图选台。地图展示当前已加载且有有效坐标的结果，点击收听后开始播放。音频由浏览器直接连接来源。",
          {
            "guides": [
              "rave-radio"
            ]
          }
        ],
        [
          "客户端接入",
          "RAVE 与原音乐端口保留 Subsonic / OpenSubsonic 协议入口，按账号权限连接兼容客户端。网页旧音乐入口已改为 RAVE；在线演示也使用全新界面。"
        ]
      ]
    },
    "plugins": {
      "title": "23 项内置工具",
      "kicker": "THE TOOLBOX",
      "lead": "每一个小工具，都服务于一段具体的日常工作。",
      "sections": [
        [
          "按需要启用",
          "内置插件随主程序运行；其配置、依赖与任务仍由主程序管理。它们与第三方用户插件不是同一种发布和运行机制。"
        ],
        [
          "依赖先行",
          "使用前确认相应的账号、目录、媒体服务、下载器、机器人或代理连接。任务结果可回到统一任务队列查看。"
        ]
      ],
      "pluginList": true
    },
    "push-assistant": {
      "title": "推送助手 · S.O. 专属",
      "kicker": "LET GOOD STORIES ARRIVE",
      "lead": "让新增媒体按用户的喜好，自动抵达各自的 115 网盘。",
      "sections": [
        [
          "S.O. 专属与账号名额",
          "推送助手仅支持 S.O. 版本，最多绑定 500 个账号。这一名额与门户用户数量分开计算；暂停、凭据失效或尚未添加凭据的绑定账号仍占名额，解绑后释放。"
        ],
        [
          "监听目录，发现新增媒体",
          "选择主账号或已映射 CD2 / AURA 云盘的备用账号目录，定时发现新增文件并识别媒体。首次扫描建立历史基线，历史文件不会自动派送；暂停和重启后保留基线。"
        ],
        [
          "按偏好派送到各自的网盘",
          "用户绑定自己的 115 账号，设置接收目录、媒体分类和画质偏好。新资源按偏好匹配接收者，各用户独立排队、处理与重试；管理员可查看派送进度与失败原因。"
        ],
        [
          "首位接收，后续接力",
          "首位用户接收成功后，可复用已送达副本作为接力来源，为其他用户继续秒传。管理员在接力缓存与资源管理中查看可用来源、派送结果和保留策略。"
        ],
        [
          "Telegram 小程序与独立 Bot",
          "通过专用 Bot 完成绑定，在小程序中扫码添加 115 账号、搜索与接收媒体、调整偏好并查看派送进度。管理员维护绑定码、用户分组和搜索额度，也可配置小程序品牌、配色与页面风格。"
        ],
        [
          "频道消息与日常管理",
          "TG 消息发送器支持图文、分享消息及定时发送，可面向个人、群组或频道发布。管理端同时提供运行总览、监听目录、用户管理、资源与清理和日志。"
        ],
        [
          "从哪里开始",
          "激活 S.O. 授权后，进入插件中心 → 推送助手。先设置专用 Bot 和小程序访问地址，再添加监听目录、生成绑定码；用一个用户完成账号绑定、接收目录与偏好配置，验证一份新增资源送达后再扩大范围。",
          {
            "guides": [
              "so"
            ]
          }
        ]
      ]
    },
    "notifications": {
      "title": "通知中心",
      "kicker": "STAY IN THE KNOW",
      "lead": "重要的进展，送到你习惯使用的地方。",
      "sections": [
        [
          "三个独立渠道",
          "Telegram、企业微信和微信 ClawBot 分别维护事件开关、静默时段、文案模板与图片配置。一个渠道的静默不影响另外两个。"
        ],
        [
          "Telegram 模板",
          "支持经典 HTML 与 Rich Message / 结构化 Blocks。在通知设计器内选择事件，查看该事件支持的变量，完成预览、保存和测试消息。"
        ],
        [
          "配置顺序",
          "先验证账号与接收对象，再选事件、静默时段和模板。企业微信需要相应应用信息及回调配置；每个渠道使用各自支持的格式和变量。"
        ],
        [
          "事件与变量",
          "整理完成、订阅更新、转存结果等事件可分别启用。编辑模板时，从当前事件的可用变量列表插入字段，预览实际样例；发送测试消息确认接收与排版后再启用。"
        ]
      ]
    },
    "ai": {
      "title": "点点 AI 助手",
      "kicker": "A LITTLE HELP",
      "lead": "用自然语言了解系统，也让重复操作少一点。",
      "sections": [
        [
          "网页与聊天入口",
          "支持流式回复、推理与工具进度、Markdown、复制、停止生成、新会话及历史。管理与闲聊场景可以选择不同工具范围。"
        ],
        [
          "提供商与使用位置",
          "支持 OpenAI 兼容 Chat Completions / Responses 协议。网页助手、Telegram 助手、媒体识别、AI 字幕等位置可以分别选择提供商与模型。"
        ],
        [
          "管理工具",
          "管理模式可读取系统、账号、订阅、任务、PT 和整理状态，也可在授权范围内执行后台操作。保留危险操作确认，敏感凭据应由后端配置。"
        ]
      ]
    },
    "satellite": {
      "title": "卫星发布树",
      "kicker": "CONNECTED INSTANCES",
      "lead": "把明确的一部分目录树，交给明确的客户端。",
      "sections": [
        [
          "按规则发布",
          "选择指定 STRM 规则发布文件树，供其他 DIAN115 子服务实例读取。发布范围由允许规则控制。"
        ],
        [
          "客户端管理",
          "每个客户端独立名称、API Key、允许规则、到期与备注。心跳报告版本、在线状态和本地文件数量；请求可按来源与结果审计。"
        ],
        [
          "维护方式",
          "客户端退役时吊销对应凭据。不要让多个实例共用一个 API Key，便于定位和单独撤销访问。"
        ]
      ]
    },
    "plugin-platform": {
      "title": "用户插件",
      "kicker": "MAKE ROOM FOR MORE",
      "lead": "把扩展交给明确的协议和独立的管理入口。",
      "sections": [
        [
          "与内置工具区分",
          "用户插件从插件仓库安装和管理，使用独立的插件协议与界面接入；内置工具直接随主程序编译。使用文档和问题排查应按这两种体系区分。"
        ],
        [
          "管理入口",
          "在插件中心维护仓库与安装项，查看操作结果并进入插件页面。安装前核对来源、权限和兼容性，实际能力以插件说明为准。"
        ]
      ]
    },
    "dashboard": {
      "title": "总览",
      "kicker": "AT A GLANCE",
      "lead": "先知道系统是否连接，再知道任务有没有向前。",
      "sections": [
        [
          "连接与资源",
          "集中观察 115、CD2、媒体服务等连接，系统 CPU、内存、空间与账号状态。"
        ],
        [
          "任务与播放",
          "查看任务进度、下载速度、播放统计和在线会话。日常排查先看连接，再看失败任务，再读对应日志。"
        ]
      ]
    },
    "queue": {
      "title": "任务队列与日志",
      "kicker": "EVERY STEP COUNTS",
      "lead": "把“出了问题”，缩小到一个明确的步骤。",
      "sections": [
        [
          "任务阶段",
          "查看整理、转存、秒传、字幕、STRM、分享和插件任务的状态、阶段、耗时、进度与关联规则。失败任务的原始错误比整体统计更有诊断价值。"
        ],
        [
          "调度与日志",
          "查看定时任务、Cron 和下次执行时间；日志可按类型、级别和关键词筛选。反馈问题时提供版本、操作步骤与脱敏后的相关片段。"
        ]
      ]
    },
    "cache": {
      "title": "缓存与数据运维",
      "kicker": "A RELIABLE MEMORY",
      "lead": "复用有价值的信息，也看见系统的实时变化。",
      "sections": [
        [
          "缓存中心",
          "包括 TMDB、115 分享、链接黑名单、链接状态绑定、虚拟缓存、TG 分享、离线链接与 FFP-cache。缓存减少重复请求，但不能替代账号、来源和路径配置。"
        ],
        [
          "FFP",
          "以 SHA1 复用容器、媒体流、章节与技术信息。本地优先、远端命中写回，低完整度信息避免覆盖更完整的记录。"
        ],
        [
          "数据运维",
          "高级版和 S.O. 可使用数据运维入口，观察实时播放、在线会话、实例与使用趋势，并转到门户账号管理。"
        ]
      ]
    },
    "container": {
      "title": "DianCupLite 容器管理",
      "kicker": "CARE FOR THE SYSTEM",
      "lead": "把容器维护也纳入可查看的工作流。",
      "sections": [
        [
          "状态、镜像与更新",
          "查看容器资源和镜像，检查远端更新，通过队列手动或定时执行更新。支持启动、停止与重启等运维操作。"
        ],
        [
          "部署依赖",
          "容器管理需要部署时提供受控的 Docker 访问。普通媒体功能不依赖此项；请按自己的部署方案配置 socket proxy 或相应权限。"
        ],
        [
          "更新前",
          "备份 /config，结束重要任务，再更新关键服务。升级后核对连接、配置与最近日志。"
        ]
      ]
    },
    "settings": {
      "title": "系统设置",
      "kicker": "MAKE IT YOURS",
      "lead": "连接、安全与规则，共同决定系统如何工作。",
      "sections": [
        [
          "网盘文件服务",
          "当前设置支持 CD2 与 AURA，分别保存地址、令牌和挂载根。选择服务并检查目录在 DIAN115 内实际可读。"
        ],
        [
          "网络与安全",
          "配置 TMDB 服务与图片地址、HTTP 代理、FlareSolverr、安全密码、两步验证与 OpenAPI Key。桥接网络内的 127.0.0.1 指向容器自身。"
        ],
        [
          "词表与 AI",
          "维护识别替换、制作组、分类词表和 AI 提供商池。媒体整理、网页助手和字幕使用位置可以分别选模型。"
        ]
      ]
    },
    "deploy": {
      "title": "部署 DIAN115",
      "kicker": "GET CONNECTED",
      "lead": "Linux / NAS 优先推荐 Host 网络。接好挂载与媒体目录，让你的影音空间顺利启动。",
      "sections": [
        [
          "选择数据库",
          "默认使用 SQLite。使用 PostgreSQL 时填写数据库类型和直接连接串；已有 SQLite 数据先迁移再启动。具体配置、迁移脚本和维护操作见下方教程。",
          {
            "guides": [
              "database-postgresql",
              "database-migration",
              "database-maintenance"
            ]
          }
        ],
        [
          "部署前",
          "准备 Linux / NAS、Docker Engine 和 Compose v2。先部署 CD2，确认 /dev/fuse 可用和宿主机支持共享挂载，再为 DIAN115 与 Emby 规划一致的目录。AURA 用户可按自身部署方案连接文件服务。",
          {
            "guides": [
              "cd2",
              "paths"
            ]
          }
        ],
        [
          "推荐部署：Host 网络",
          "将下方配置保存为 compose.yml，按实际目录修改 volumes。network_mode: host 让 DIAN115 直接使用宿主机网络，无需添加 ports。Web 管理端默认 8095，Emby 代理与音乐服务使用各自在页面中配置的端口；多个实例应设置不同端口。",
          {
            "code": "dian-host-compose"
          }
        ],
        [
          "目录与持久化",
          "/config 保存账号、授权和配置；/dian115AI 保存 AI 工作区。示例将 /mnt/user/media 映射为 /媒体库，将 /mnt/cache/CloudNAS 映射为 /CloudNAS:rslave；这两项在 Emby 中保持一致。Host 网络处理网络连接，shared / rslave 处理文件挂载传播，两项都需要正确配置。",
          {
            "guides": [
              "paths"
            ]
          }
        ],
        [
          "启动与初始化",
          "在 compose.yml 所在目录执行下方命令，访问 http://服务器IP:8095。初始化管理员密码并激活授权；连接 CD2、自动读取挂载点，再从文件管理确认挂载目录可读。",
          {
            "code": "dian-start"
          }
        ],
        [
          "FlareSolverr 按需接入",
          "使用 UIndex 等需要 Cloudflare 验证的来源时，再部署 FlareSolverr。按教程将同机服务的 8191 映射到宿主机 127.0.0.1，在系统设置的“FlareSolverr 过盾设置”填写 http://127.0.0.1:8191，保存并测试。普通网盘挂载与播放不依赖它。",
          {
            "guides": [
              "flaresolverr"
            ]
          }
        ],
        [
          "备选部署：桥接网络",
          "需要 Docker 网络隔离时，可用下方完整配置替换 Host 配置，仍保存为 compose.yml。桥接模式不设置 network_mode: host，需要逐个映射实际使用的代理和音乐端口。127.0.0.1 指向 DIAN115 容器自身；同一桥接网络的 FlareSolverr 使用 http://flaresolverr:8191，CD2 等其他服务按实际内网地址连接。",
          {
            "code": "dian-bridge-compose"
          }
        ],
        [
          "验收与备份",
          "测试小范围整理、STRM 输出与 Emby 播放，确认 CD2 重启后目录仍可见。升级前备份完整 /config；AI 工作区有内容时一同备份。"
        ]
      ]
    },
    "cd2": {
      "title": "CloudDrive2 部署与接入",
      "kicker": "CONNECT YOUR CLOUD",
      "lead": "从容器启动到自动读取挂载点，让云盘目录真正可用。",
      "sections": [
        [
          "1. 准备 Linux / NAS 主机",
          "确认系统支持 FUSE，存在 /dev/fuse，并准备持久化的 CD2 配置目录与云盘挂载目录。下方示例使用宿主机 /mnt/cache/CloudNAS；按自己的 NAS 路径调整。示例采用 CD2 官方支持的 Host 网络与 FUSE 权限配置。",
          {
            "code": "cd2-compose"
          }
        ],
        [
          "2. 启动 CD2",
          "将示例保存为 compose.cd2.yml，创建目录后启动。打开 http://服务器IP:19798，注册或登录 CD2，添加自己的 115 账号。Host 网络不再使用 ports 映射；19798 是这台宿主机上的 CD2 入口。",
          {
            "code": "cd2-start"
          }
        ],
        [
          "3. 确认共享挂载传播",
          "CD2 的 /CloudNAS 使用 :shared；宿主机上的对应挂载点也要支持 shared / rshared。若容器启动提示挂载未共享，先检查宿主机传播属性。下方命令用于普通 Linux 的独立挂载点示例；NAS 的持久化方式按系统设置，宿主机重启后也要验证。",
          {
            "code": "mount-check"
          }
        ],
        [
          "4. 配置 CloudDrive 挂载与 Token",
          "在 CD2 的挂载设置中，挂载点名称使用 CloudDrive，源目录选择根目录 /，启用启动时自动挂载，挂载在 /CloudNAS 下。创建供 DIAN115 使用的 API Token，至少允许文件读取、创建、修改与删除。"
        ],
        [
          "5. 在 DIAN115 连接 CD2",
          "进入系统设置 → 网盘文件服务，选 CD2，填写如 http://192.168.1.10:19798/ 的 API 地址与 Token。保存后点击“自动读取”，确认挂载路径类似 /CloudNAS/CloudDrive。这里使用 DIAN115 容器内看到的路径，不填宿主机 /mnt/cache/CloudNAS。"
        ],
        [
          "6. 关联主账号与验证",
          "进入账号配置，添加 115 主账号，选中它实际对应的 CD2 云盘。云盘名称使用 CD2 中的真实名称，如 115open；目录从正确云盘的根开始选择。最后检查文件管理能浏览该云盘，再创建整理和 STRM 规则。",
          {
            "guides": [
              "paths",
              "connections"
            ]
          }
        ]
      ]
    },
    "paths": {
      "title": "CD2、DIAN115 与 Emby 路径搭配",
      "kicker": "ONE DIRECTORY TREE",
      "lead": "同一份文件，在宿主机和各容器里分别叫什么，一次说清。",
      "sections": [
        [
          "1. 两个共享目录，三套容器",
          "云盘挂载目录用来接收 CD2 的 FUSE 子挂载；媒体目录用来保存整理输出或本地 STRM。CD2 发布挂载，DIAN115 与 Emby 接收挂载。DIAN115 和 Emby 的宿主机来源、容器目标路径保持一致。",
          {
            "code": "shared-mounts"
          }
        ],
        [
          "2. 路径对照表",
          "左侧是宿主机目录，右侧才是程序配置要填写的容器路径。:shared 与 :rslave 是卷挂载选项，不是路径名称的一部分。",
          {
            "table": {
              "headers": [
                "位置 / 用途",
                "示例路径或配置",
                "在哪里使用"
              ],
              "rows": [
                [
                  "宿主机云盘目录",
                  "/mnt/cache/CloudNAS",
                  "CD2、DIAN115、Emby 的 volumes 左侧"
                ],
                [
                  "CD2 发布挂载",
                  "/CloudNAS:shared",
                  "CD2 的 volumes 右侧"
                ],
                [
                  "DIAN115 / Emby 接收",
                  "/CloudNAS:rslave",
                  "两个容器的 volumes 右侧"
                ],
                [
                  "CD2 自动读取挂载点",
                  "/CloudNAS/CloudDrive",
                  "DIAN115 → 系统设置 → 网盘文件服务"
                ],
                [
                  "主账号云盘名称",
                  "115open（示例）",
                  "账号配置中选择真实 CD2 云盘"
                ],
                [
                  "云盘中的电影目录",
                  "/CloudNAS/CloudDrive/115open/电影",
                  "文件管理 / 规则的本地挂载路径示例"
                ],
                [
                  "宿主机媒体输出",
                  "/mnt/user/media",
                  "DIAN115 与 Emby 的 volumes 左侧"
                ],
                [
                  "容器媒体输出",
                  "/媒体库/strm",
                  "DIAN115 的 STRM 输出与 Emby 扫描目录"
                ]
              ]
            }
          }
        ],
        [
          "3. shared 与 rslave 为什么不同",
          "CD2 使用 shared 将云盘子挂载传播到宿主机。DIAN115 与 Emby 使用 rslave 接收宿主机的挂载变化，CD2 重启后重建的子挂载也能继续看见。宿主机传播未配置时，单独写 :rslave 无法解决问题。修改 volumes 后需要重新创建容器。"
        ],
        [
          "4. 挂载点、云盘名与目录不要混用",
          "/CloudNAS 是容器卷根；/CloudNAS/CloudDrive 是自动读取的挂载点；115open 是 CD2 的云盘名称。真实云盘名以自己的 CD2 为准。CD2 API 的目录选择器和本地文件选择器可能显示不同前缀，应使用对应入口选择目录。"
        ],
        [
          "5. 从 STRM 输出到 Emby 扫描",
          "例如 DIAN115 把 STRM 输出到 /媒体库/strm，Emby 也将这个目录作为媒体库目录。容器中的 /媒体库/strm 实际对应宿主机 /mnt/user/media/strm。若已有 Emby 路径不同，先配置路径转换并检查匹配，再扫描，避免重复条目。"
        ],
        [
          "6. 按配置引导逐步验收",
          "先对齐三套 Compose → 在 CD2 挂载根目录并生成 Token → DIAN115 保存 CD2 地址并自动读取 → 添加 115 主账号并选云盘 → 配置整理与 STRM → 首次全量同步 → 在我的媒体控制中心接入 Emby。先用一部作品确认读取、输出和播放，再扩大范围。"
        ]
      ]
    },
    "flaresolverr": {
      "title": "FlareSolverr 部署与配置",
      "kicker": "CONNECT RESOURCE SOURCES",
      "lead": "跟随推荐的 Host 部署方式，接通需要 Cloudflare 验证的资源站。",
      "sections": [
        [
          "什么时候需要",
          "UIndex 等来源可能触发 Cloudflare 验证。遇到此类验证时部署 FlareSolverr，由它提供浏览器处理能力；普通 115、CD2 与 Emby 连接无需因此额外配置。验证能否成功还取决于资源站当时的限制。"
        ],
        [
          "推荐搭配：DIAN115 Host + 同机 FlareSolverr",
          "将下方 flaresolverr 服务合并到 compose.yml 的 services 下，保留已有 dian115 服务，只保留一个 services 根节点。DIAN115 使用 network_mode: host；FlareSolverr 保留默认桥接网络，通过 127.0.0.1:8191:8191 将接口提供给同机 DIAN115。",
          {
            "code": "flaresolverr-compose"
          }
        ],
        [
          "启动与查看状态",
          "在 compose.yml 所在目录保存并启动服务，查看日志。首次请求需要启动浏览器环境，可能比后续请求慢。",
          {
            "code": "flaresolverr-start"
          }
        ],
        [
          "在 DIAN115 配置",
          "按上方推荐搭配部署后，进入系统设置 → FlareSolverr 过盾设置，服务地址填写 http://127.0.0.1:8191，点击保存 FlareSolverr 设置，再点击测试连接。确认测试成功后，回到对应来源重新搜索。地址在界面保存。"
        ],
        [
          "备选：同一桥接网络",
          "DIAN115 与 FlareSolverr 都在同一 Compose 桥接网络时，服务地址改为 http://flaresolverr:8191，可移除 FlareSolverr 的 ports 映射。自定义网络时将两个服务接入同一网络。桥接容器中的 127.0.0.1 指向容器自身；DIAN115 使用 Host 时不能按 Docker 服务名访问这个桥接服务。"
        ],
        [
          "不同机器或不同 Docker 网络",
          "用下方 ports 替换示例中的本机端口映射，绑定 FlareSolverr 主机的实际内网 IP。在 DIAN115 中填写 http://FlareSolverr主机IP:8191。",
          {
            "code": "flaresolverr-remote"
          }
        ],
        [
          "连接失败时",
          "依次检查容器是否运行、服务地址与端口、网络可达性、日志和来源状态。8191 仅供自己的实例或内网访问；连接测试通过只能说明服务可达，不保证所有站点验证都能成功。"
        ]
      ]
    },
    "connections": {
      "title": "连接账号与服务",
      "kicker": "CONNECT THE PIECES",
      "lead": "让一条最小链路真正连通，再逐步添加服务。",
      "sections": [
        [
          "管理员与授权",
          "完成首次密码初始化与 License Key 激活，确认重启后状态仍保留。"
        ],
        [
          "CD2 部署与路径",
          "先在 CD2 设置 CloudDrive 根目录挂载与 API Token；DIAN115 与 Emby 的 /CloudNAS 使用 rslave，媒体目录保持同一路径。",
          {
            "guides": [
              "cd2",
              "paths"
            ]
          }
        ],
        [
          "CD2 或 AURA",
          "在系统设置 → 网盘文件服务选择 CD2，保存 API 地址与 Token，点击自动读取，确认返回 /CloudNAS/CloudDrive。使用 AURA 时切换为 AURA 并按实际服务配置。"
        ],
        [
          "115 主账号",
          "扫码添加并选为活跃账号，选择它真实对应的 CD2 云盘；分别设置转存、离线、秘享接收目录。"
        ],
        [
          "FlareSolverr",
          "需 Cloudflare 验证的来源在系统设置配置 FlareSolverr 服务地址、保存并测试。推荐的 DIAN115 Host + 同机端口映射方案使用 http://127.0.0.1:8191；两个服务都在同一桥接网络时使用 http://flaresolverr:8191。",
          {
            "guides": [
              "flaresolverr"
            ]
          }
        ],
        [
          "Emby",
          "在我的媒体 → 控制中心添加 Emby 后端、API Key 与代理端口。确认媒体目录与 DIAN115 一致；需要时配置路径转换。Host 直接使用实例配置的端口，桥接模式需对应映射。先验证库统计、单个条目与播放，再开启大范围扫描。"
        ],
        [
          "已有媒体库迁移",
          "已有媒体库时先构建目录树但不生成 STRM；读取 Emby 媒体画像、检查路径匹配、接入 Madby 并上报 FFP，最后切换新 STRM。"
        ]
      ]
    },
    "first-library": {
      "title": "建立第一份媒体库",
      "kicker": "YOUR FIRST COLLECTION",
      "lead": "从一部作品开始，确认每个细节都如预期。",
      "sections": [
        [
          "准备测试目录",
          "选择一个小目录，确认源与目标模式一致，输出对 Emby 可见。"
        ],
        [
          "测试整理规则",
          "核对媒体识别、TMDB、命名、分类、字幕和版本策略。先保留被过滤或替换的源文件。"
        ],
        [
          "生成与播放",
          "按需要少量生成 STRM，通过 RAVE 或 Emby 扫描与播放。RAVE 可直接添加本地媒体目录；多实例分类建库可使用媒体库管理工具，先预览再执行。"
        ],
        [
          "开启同步",
          "验证成功后选择定时或实时模式，观察任务队列和日志，再扩大到更多目录。"
        ]
      ]
    },
    "automation": {
      "title": "开启自动化",
      "kicker": "LET IT FLOW",
      "lead": "给自动化一个可靠的起点。",
      "sections": [
        [
          "资源来源",
          "先验证下载器连接、目录和任务，再接入 PT 认证、搜索、RSS、TG 或癫影。"
        ],
        [
          "订阅策略",
          "设置电影 / 剧集的质量方案与来源优先级，创建一个订阅并观察搜索、下载 / 转存、后处理、整理的独立结果。"
        ],
        [
          "消息通知",
          "验证渠道与接收对象，再启用事件模板和静默时段。Telegram、企业微信、微信各自保存。"
        ],
        [
          "扩展能力",
          "按需启用音乐、AI、字幕或机器人。准备多人服务时，最后配置门户、权限、访问线路与邀请码。"
        ]
      ]
    },
    "personal": {
      "title": "个人与家庭使用",
      "kicker": "YOUR OWN LITTLE CINEMA",
      "lead": "为喜欢的故事，留出更多时间。",
      "sections": [
        [
          "一个轻量起点",
          "一个主账号、一套连接、一条小范围规则、一次成功播放，就能验证个人使用链路。"
        ],
        [
          "每日回访",
          "探索喜欢的电影，订阅追看的剧集，在日历看更新。整理完成后从 RAVE 或 Emby 回访收藏，在统一媒体空间里继续听歌与收听电台。"
        ],
        [
          "把偏好写成规则",
          "按分辨率、质量、语言或多版槽位配置收藏方式，用规则减少每次手动判断。"
        ],
        [
          "音乐与助手",
          "音乐中心收藏专辑与歌单，点点帮助解释系统状态；重要进展通过你常用的通知渠道送达。"
        ],
        [
          "家人也能轻松使用",
          "门户提供独立的用户入口。高级版支持最多 10 个门户小号；管理员维护共享账号或配置独享模式，用户使用自己的权限范围。"
        ]
      ]
    },
    "so": {
      "title": "S.O. 版本",
      "kicker": "MORE ROOM TO PLAY",
      "lead": "为更多用户、更多实例、资源派送与群组管理，扩展你的空间。",
      "sections": [
        [
          "高级版共有能力",
          "媒体自动化、用户门户、音乐中心和数据运维，在高级版与 S.O. 中均可使用。S.O. 适合需要更大用户规模、资源派送与群组管理的场景。"
        ],
        [
          "用户与实例数量",
          "高级版最多创建 10 个门户小号，S.O. 不设这一数量上限；Emby 代理实例上限分别为 3 与 6。实际容量取决于主机、账号与外部服务。"
        ],
        [
          "S.O. 专属推送助手",
          "监听主账号或已映射的备用账号目录，发现新增媒体并按用户的分类、画质偏好派送到各自的 115 网盘。首位用户接收成功后，后续用户可通过接力秒传继续接收；Telegram 小程序提供账号绑定、媒体搜索、接收偏好和派送进度。仅 S.O. 可用，最多 500 个绑定账号，名额与门户用户数量分开计算。",
          {
            "guides": [
              "push-assistant"
            ]
          }
        ],
        [
          "S.O. 群组管理机器人",
          "独立 Telegram 群管 Bot，包含欢迎验证、广告与安全策略、成员权限、命令菜单、群组 AI、独立 Token 配额、审计与 OpenAPI 外部推送。"
        ],
        [
          "捐赠金额与选择",
          "个人版（高级版）199 元，适合个人、家庭与小范围共享；S.O. 版 499 元，适合更多门户用户、Emby 代理实例、推送助手与群组管理。选定版本后扫码捐赠，付款备注邮箱即可。授权有效期与附加功能以收到的密钥为准。",
          {
            "guides": [
              "license"
            ]
          }
        ]
      ]
    },
    "license": {
      "title": "捐赠与授权码激活",
      "kicker": "YOUR ACCESS KEY",
      "lead": "个人版 199 元 · S.O. 版 499 元。扫码捐赠，备注邮箱，开启你的私人影音空间。",
      "sections": [
        [
          "选择版本",
          "个人版（高级版）的捐赠金额为 199 元，S.O. 版为 499 元。选择适合自己的版本，按对应金额扫码捐赠。"
        ],
        [
          "扫码捐赠与接收",
          "使用本页官方二维码完成捐赠，付款备注填写可正常收信的邮箱，通过该邮箱接收授权码。保存付款记录，收到 License Key 后妥善保管。"
        ],
        [
          "填写 License Key",
          "首次启动时，在激活页面填写收到的密钥。已激活实例可从账号菜单进入更换密钥；页面提示需要重启时按提示完成。"
        ],
        [
          "未收到或验证异常",
          "未收到授权码或捐赠遇到问题时，可联系 @succt，提供捐赠时间、付款记录与备注邮箱。验证异常先检查网络、系统时间和日志；反馈问题时隐藏完整密钥。"
        ]
      ],
      "contact": true,
      "donation": true
    },
    "portal": {
      "title": "门户功能完整指南",
      "kicker": "A PLACE FOR EVERYONE",
      "lead": "用户有自己的放映室，管理员有清晰的服务工作台。",
      "sections": [
        [
          "账户与注册",
          "由管理员创建和分配账号，或开启邀请码注册。账户中心维护资料、密码、有效期、续期、Telegram 通知连接与邀请。"
        ],
        [
          "共享与独享模式",
          "共享模式使用管理员维护的 115 账号池，用户不操作共享凭据；独享模式由用户扫码或手动绑定自己的 115 账号，管理登录检测与安全码。"
        ],
        [
          "媒体与服务",
          "根据用户在 Emby 中的访问权限展示媒体，提供求片、访问线路、在线会话、个人播放缓存、想看 / 看过和播放历史。"
        ],
        [
          "社区与积分",
          "签到积分、积分兑换、社区帖子、观影目标、成就排行、勋章佩戴与资源投稿，共同组成用户互动体验。"
        ],
        [
          "通知与支持",
          "消息中心收取广播与动态；工单按分类和优先级提交，用户与管理员持续回复并跟进状态。"
        ],
        [
          "管理员工作台",
          "门户总控分为账号中心、求片、工单、社区与积分、通知广播、站点设计、用户缓存、系统配置。可配置功能开关、账号分配、积分规则、商品、勋章和访问线路。"
        ],
        [
          "版本与上线",
          "高级版最多 10 个门户小号，S.O. 不设这一数量上限。实际入口受功能开关影响，对外访问使用 HTTPS，并验证注册、播放、消息与工单流程。"
        ]
      ],
      "portalList": true
    },
    "demo": {
      "title": "在线 Demo",
      "kicker": "SEE IT FOR YOURSELF",
      "lead": "体验 v5.0.42 管理端、用户门户与 RAVE 页面，所有操作使用独立演示数据。",
      "sections": [
        [
          "新版管理端",
          "直接体验 v5.0.42 的管理端页面、当前导航与内置插件，包括 RAVE 和媒体库管理工具。演示填充媒体、账号、任务、规则、录制方案与用户假数据，首次进入默认深色。"
        ],
        [
          "新版用户门户",
          "体验当前门户的概览、媒体、求片、服务连接、积分、社区、消息、工单与账户页面，以演示用户直接进入。门户继续承担用户服务，不代替独立媒体前台。"
        ],
        [
          "全新 RAVE",
          "体验统一媒体空间中的电影、剧集选集、片单、音乐、电台地图、直播界面和阅读样例。电影、剧集、音乐、电台、直播、漫画和有声书均使用真实作品资料，配套独立演示状态。歌曲可播放公开试听片段。",
          {
            "guides": [
              "rave",
              "music",
              "rave-comics"
            ]
          }
        ],
        [
          "演示数据",
          "操作只作用于浏览器中的演示状态，刷新后恢复样例。无需输入真实 115 凭据或后台密码；实际扫描、转存、下载、直播和录制需在自己的实例中配置。"
        ]
      ]
    },
    "rave": {
      "title": "RAVE 独立媒体空间",
      "kicker": "YOUR MEDIA, TOGETHER",
      "lead": "电影、剧集、直播、音乐、电台与漫画，在同一个地方相遇。",
      "sections": [
        [
          "从哪里开启",
          "进入插件中心 → 内置插件 → RAVE。先添加本地媒体库和独立媒体账号，再扫描媒体并启用服务。默认端口为 8111；Host 网络直接使用该端口，桥接网络按实际配置映射。媒体路径必须是服务可读取的 Linux 绝对路径。"
        ],
        [
          "全新媒体前台",
          "打开媒体库后，在发现、媒体库、片单、直播、音乐和电台之间切换。电影和剧集分别展示，剧集按季与单集浏览；个人收藏、继续观看和历史各自保留。手机从底部“全部”进入更多内容。"
        ],
        [
          "统一账号与内容权限",
          "媒体账号与后台管理员独立。为账号分别分配影视库、音乐源、直播、电台与漫画权限，并按需要设置播放、下载、并发和访问策略。用户只会看到被允许的内容。"
        ],
        [
          "播放与客户端",
          "支持本地视频、STRM 与虚拟影库。网页提供原画、转封装与兼容转码，实际能力取决于媒体格式、浏览器、服务配置与用户权限；兼容 Emby 的客户端可使用同一服务器和媒体账号连接。"
        ],
        [
          "网站外观",
          "在网站外观中调整影院主题、强调色、导航、海报密度、首页模块和播放器偏好。草稿可预览，发布后才影响用户。在线演示默认深色，作品和账号均为假数据。"
        ],
        [
          "直播与漫画",
          "直播支持频道、分组、线路和节目单；后台可配置录制方案。漫画使用 RAVE 统一账号与端口，支持公共书库和授权书源。更多配置见对应指南。",
          {
            "guides": [
              "rave-live",
              "rave-comics",
              "library-manager"
            ]
          }
        ],
        [
          "演示范围",
          "在线演示展示当前正式页面。影视使用真实海报、简介与演职人员，音乐使用真实歌手、专辑和公开试听；电台、直播、漫画和有声书使用真实资料。直播排期为示例，电台与有声书使用合成声音，漫画阅读器不提供正文。有声书正式服务仍待后续接入，演示中的阅读样例不代表已连接真实书库。"
        ]
      ]
    },
    "library-manager": {
      "title": "媒体库管理工具",
      "kicker": "A LIBRARY THAT FITS",
      "lead": "整理规则决定目录，媒体库方案决定如何呈现。",
      "sections": [
        [
          "选择实例与规则",
          "进入插件中心 → 媒体库管理工具，选择 RAVE 或 Emby 实例，再绑定一条整理规则。同一规则可供多个实例分别使用；各实例独立保存建库层级、模板与自动同步开关。"
        ],
        [
          "先查看预览",
          "媒体根目录、媒体类型及分类目录来自整理规则。预览会列出保留、新增、原地改名、冲突和待移除内容。名称与路径完全一致时保留已有媒体库，同路径改名时保留库标识。"
        ],
        [
          "媒体库与模板",
          "查看、搜索、编辑、扫描、复制或移除媒体库。电影和剧集可分别配置通用模板与另存模板；模板不携带路径，修改模板只影响之后的建库，已有库需主动应用。"
        ],
        [
          "自动同步",
          "确认预览后主动开启实例自动同步。规则目录、类型或分类结构变化时，关联实例会暂停同步，需要重新核对方案并保存。任务结果在统一任务队列中查看。"
        ],
        [
          "移除开关",
          "“自动移除媒体库”与“自动删除分类目录”各自独立，默认关闭。移除库条目保留文件，删除分类目录会删除其中媒体文件。执行前查看预览和任务范围。"
        ]
      ]
    },
    "rave-live": {
      "title": "RAVE 直播与录制",
      "kicker": "ON AIR",
      "lead": "看频道，也为想留下的节目做好计划。",
      "sections": [
        [
          "频道与节目单",
          "在 RAVE 后台添加 M3U 订阅或文本，按需配置节目单、请求头与刷新周期。网页展示频道、分组和可用线路，账号需要有直播权限。"
        ],
        [
          "录制方案",
          "在 RAVE → 直播录制创建方案，选择频道和线路、Linux 本地保存目录、录制时长或停止时间。支持手动、一次、每天和每周预约，并可设置电影或剧集结构与命名模板。"
        ],
        [
          "原流与硬件转码",
          "默认原流保存，按来源格式选择 TS、MKV 或 MP4。硬件转码需要兼容的 FFmpeg、显卡与设备权限；检测结果和任务历史用于确认实际处理方式。"
        ],
        [
          "任务记录",
          "录制进度与取消操作进入统一任务队列。查看方案、文件路径、已保存大小、编码器与异常信息。在线演示只展示真实频道资料和示例方案，不连接真实直播源。"
        ]
      ]
    },
    "rave-radio": {
      "title": "RAVE 电台与地图",
      "kicker": "LISTEN A LITTLE FURTHER",
      "lead": "从熟悉的声音，听到远方的频率。",
      "sections": [
        [
          "列表与发现",
          "从 RAVE 电台页浏览公共电台，或进入世界目录发现内容。支持关键词、国家、语言、风格、标签、编码与码率筛选，个人收藏与公共发布分别管理。"
        ],
        [
          "地图选台",
          "地图显示已加载且有有效坐标的结果；没有坐标的频道仍可从列表选择。手机默认列表，可主动展开地图。选择电台后点击收听才开始播放。"
        ],
        [
          "播放与频谱",
          "音频由浏览器直连上游。HTTPS 页面、媒体格式和来源跨域规则可能影响播放；频谱由用户主动开启，使用设备分析当前音频。无法分析时继续普通播放。"
        ],
        [
          "演示声音",
          "演示地图展示 BBC Radio 3、KEXP、FIP、Radio Paradise 与 SomaFM 的真实资料和标志，收听时使用合成声音示例。在线演示不调用真实电台媒体，不提交公共目录修改。"
        ]
      ]
    },
    "rave-comics": {
      "title": "RAVE 漫画书库",
      "kicker": "STORIES ON PAPER",
      "lead": "把书库、书源与阅读进度，交给清晰的权限。",
      "sections": [
        [
          "配置书库",
          "在 RAVE 后台启用漫画服务，添加可读取的本地漫画目录并扫描。公共书库支持 CBZ / ZIP、CBR / RAR、EPUB 与 PDF；解析能力取决于实际文件和运行环境。"
        ],
        [
          "同一账号与端口",
          "漫画复用 RAVE 监听端口。为统一媒体账号开启漫画权限，并选择允许访问的书库与书源，不再单独配置漫画端口。"
        ],
        [
          "书源与扩展",
          "管理员可管理规则书源和扩展仓库，实际搜索、章节与页图能力需要对具体来源验证。新安装来源需明确启用并授权，安装成功不等于所有站点功能均已验证。"
        ],
        [
          "网页与阅读客户端",
          "网页支持书架、章节、阅读方向和进度。提供 Komga 核心阅读接口、OPDS 目录与部分设备进度协议；下载和归档管理由后台执行，客户端兼容范围按实际验证为准。"
        ],
        [
          "独立演示",
          "公开 Demo 展示《航海王》《哆啦A梦》《名侦探柯南》等真实漫画的卷封、作者与简介，以及阅读器版式样例，支持单页、双页、方向与长条阅读，不连接书源、不保存正式账号记录。"
        ]
      ]
    },
    "database-postgresql": {
      "title": "使用 PostgreSQL 新装 DIAN115",
      "kicker": "数据库安装与维护",
      "lead": "准备 PostgreSQL 数据库，在容器中填写数据库类型和连接串。首次启动自动建表；配置目录继续保存密钥、图片和其他本地文件。",
      "manual": "/dian115/docs/database-postgresql/",
      "sections": [
        [
          "准备镜像、目录和数据库",
          "使用包含 PostgreSQL 支持的 DIAN115 v5.0.42 或更新镜像。下面示例将 PostgreSQL 18 与 DIAN115 部署在同一台 Linux / NAS，数据库只映射到本机 15432 端口。已有 PostgreSQL 服务的用户直接使用现有库地址、库名、用户名和密码，跳到“填写连接串”。/mnt/user/media 与 /mnt/cache/CloudNAS 替换为自己的媒体和挂载目录。",
          {
            "code": "database-postgresql-1"
          }
        ],
        [
          "保存 compose.yml",
          "将以下内容保存为 compose.yml。DIAN115 使用 Host 网络；PostgreSQL 使用普通容器网络，通过宿主机 127.0.0.1:15432 连接。PostgreSQL 18 的持久化目录为 /var/lib/postgresql。已有数据库时仅保留 dian115 服务，保留原来的所有目录挂载。",
          {
            "code": "database-postgresql-2"
          }
        ],
        [
          "填写 .env 连接配置",
          "在 compose.yml 同目录新建 .env，替换密码。POSTGRES_PASSWORD 用于首次创建 PostgreSQL 账号；DIAN115_PG_DSN 用于应用连接。两处密码必须一致。DSN 中的用户名、密码若含 @、:、/、?、#、% 等特殊字符，应先做 URL 百分号编码。例子中的 sslmode=disable 用于同机连接；远程 TLS 数据库按服务提供方要求填写 sslmode。",
          {
            "code": "database-postgresql-3"
          }
        ],
        [
          "填写已有数据库的连接串",
          "DIAN115 的数据库配置只需 DIAN115_DB_DRIVER=pgsql 和 DIAN115_PG_DSN。连接串的格式为 postgres://用户名:密码@地址:端口/库名。Host 网络填写宿主机或数据库服务器地址；桥接模式下，只有同一 Docker 网络才能用 postgres 这样的服务名。下面是已有数据库的填写格式。",
          {
            "code": "database-postgresql-4"
          }
        ],
        [
          "启动并完成首次设置",
          "在 compose.yml 所在目录启动。打开 http://服务器IP:8095，设置管理员密码并按页面完成授权。应用连接 PostgreSQL 后自动创建当前业务表。首次使用 PostgreSQL 不需要先创建 SQLite 数据或运行迁移命令。",
          {
            "code": "database-postgresql-5"
          }
        ],
        [
          "确认当前数据库",
          "打开“系统设置 → 基础设置 → 数据库维护”。“当前数据库”应显示 PostgreSQL、已连接，并显示实际库名和版本。继续配置网盘服务、账号与媒体目录。/config 必须继续持久化，不能因使用 PostgreSQL 而删除。",
          {}
        ]
      ]
    },
    "database-migration": {
      "title": "把旧 SQLite 数据迁移到 PostgreSQL",
      "kicker": "数据库安装与维护",
      "lead": "停止旧实例，备份原配置目录，将当前业务数据迁入空的 PostgreSQL 数据库，再使用同一配置目录和 PostgreSQL 连接启动。历史废表、废列自动忽略。",
      "manual": "/dian115/docs/database-migration/",
      "sections": [
        [
          "停止旧实例并备份配置目录",
          "在原 compose.yml 所在目录操作。先停止 DIAN115，再备份整个配置目录，包含所有 SQLite 分库、密钥和本地资源。示例的 ./config 要换成当前容器 /config 对应的真实宿主机目录；不要只复制 dian115.db。",
          {
            "code": "database-migration-1"
          }
        ],
        [
          "准备空目标库并修改连接配置",
          "按“使用 PostgreSQL 新装 DIAN115”准备数据库。已有 PostgreSQL 时新建一个空数据库供此次迁移使用。在原 dian115 服务加入 DIAN115_DB_DRIVER=pgsql 和 DIAN115_PG_DSN，保留原来的所有 volumes、端口和其他配置。此时先不要启动 dian115。若新建同机 PostgreSQL，只启动 postgres 服务。",
          {
            "code": "database-migration-2"
          }
        ],
        [
          "生成并执行外部迁移脚本",
          "下面命令会在当前目录生成 migrate-to-pgsql.sh 并执行。脚本复用 Compose 中的镜像、数据库连接和 /config 挂载，运行镜像内的迁移工具。逐表导入完成后显示 {\"backend\":\"pgsql\",\"ready\":true}，随后正常启动 DIAN115。脚本不要求访问项目源码。",
          {
            "code": "database-migration-3"
          }
        ],
        [
          "已有外部脚本时的用法",
          "如果已经取得 migrate-sqlite-to-pgsql.sh，也可直接执行下列命令。--config 填原配置目录的 Linux 绝对路径；--image 填当前使用的镜像。连接串必须与启动后的 DIAN115 一致。同一 Docker 网络连接数据库时追加 --network 网络名；自定义主库文件名追加 --db 文件名。此方式完成后，手动执行 docker compose up -d dian115。",
          {
            "code": "database-migration-4"
          }
        ],
        [
          "迁移保留哪些数据",
          "迁入当前业务使用的表和字段，保留记录 ID、自增序号与加密凭据，音乐数据转换为当前结构。历史废表、废列、旧索引和无关文件会忽略；未使用过的可选分库、表或升级字段按当前默认值初始化。原 SQLite 文件不会删除。",
          {}
        ],
        [
          "确认已经切换",
          "登录后打开“系统设置 → 基础设置 → 数据库维护”，确认显示 PostgreSQL 与目标库名。查看账号、整理规则、任务和音乐等原有内容。迁移后新增数据写入 PostgreSQL，不会同步回原 SQLite。",
          {}
        ],
        [
          "连接或导入失败时处理",
          "脚本发生真实连接或字段转换错误时会停止，并指出出错位置。修正对应地址、权限或数据问题后，换一个空目标库重新迁移。不要对已正常运行并产生新数据的 PostgreSQL 库重复执行导入。原配置目录及备份可供恢复旧 SQLite 实例使用；切回 SQLite 只能得到迁移前数据。",
          {}
        ]
      ]
    },
    "database-maintenance": {
      "title": "查看和维护当前数据库",
      "kicker": "数据库安装与维护",
      "lead": "在基础设置查看当前数据库，在系统诊断观察连接池与等待。PostgreSQL 维护按表整理可复用空间并更新查询统计，进度和结果在页面中展示。",
      "manual": "/dian115/docs/database-maintenance/",
      "sections": [
        [
          "查看实际数据库信息",
          "打开“系统设置 → 基础设置 → 数据库维护”，查看数据库类型和连接状态。PostgreSQL 还显示库名、服务版本、数据库占用、业务表数量、连接数、缓存命中率、预估待回收记录与自动空间维护状态。点击“刷新数据库信息”重新读取。",
          {}
        ],
        [
          "查看占用较大的表",
          "展开“查看占用较大的业务表”，按占用查看最多 20 张表，包含预估有效记录、待回收记录以及最近空间维护和统计更新时间。记录数来自 PostgreSQL 统计估算，不是实时逐行计数。",
          {}
        ],
        [
          "执行一次维护",
          "点击“立即维护”，阅读本次范围后选择“开始维护”。任务在后台清理过期记录，再对 PostgreSQL 业务表执行普通 VACUUM (ANALYZE)。页面显示执行阶段、已处理表数、总表数、上次成功时间与结果摘要；有错误时显示对应原因。SQLite 使用自己的增量空间回收和检查点。",
          {}
        ],
        [
          "理解空间变化",
          "PostgreSQL 普通维护会让删除记录占用的空间可被后续写入复用，并更新查询统计，数据库文件不一定缩小。应用不执行 VACUUM FULL。自动空间维护与手动维护可以并用，不需要每天反复点击。",
          {}
        ],
        [
          "从诊断页观察连接等待",
          "打开“系统诊断 → 运行概览 → 数据库连接与等待”，查看 PostgreSQL 实际连接池的已打开、使用中、空闲和等待统计。点击“数据库维护”进入设置页操作。等待次数累计自本次进程启动；等待连接不等于消耗 CPU。",
          {}
        ],
        [
          "区分进程内存与数据库内存",
          "诊断页的“手动释放内存”回收 DIAN115 进程内存。PostgreSQL 服务端缓存由数据库管理，不会被这个按钮清空。SQLite 与 PostgreSQL 的维护记录分别保留，切库后显示当前后端的记录。",
          {}
        ]
      ]
    }
  }
};
