/* DIAN115 Wiki · 独立文档内容，不包含主项目源码。 */
window.DIAN_WIKI = {
  version: '4.0.96',
  demo: 'https://madbrolab.github.io/dian115/demo/',
  codeSamples: {
    'cd2-compose': {label:'compose.cd2.yml · CloudDrive2',text:`services:
  clouddrive2:
    image: cloudnas/clouddrive2:latest
    container_name: clouddrive2
    restart: unless-stopped
    network_mode: host
    pid: host
    privileged: true
    devices:
      - /dev/fuse:/dev/fuse
    environment:
      - CLOUDDRIVE_HOME=/Config
      - TZ=Asia/Shanghai
    volumes:
      - ./cd2-config:/Config
      - /mnt/cache/CloudNAS:/CloudNAS:shared`},
    'cd2-start': {label:'准备目录与启动 · Linux / NAS 示例',text:`mkdir -p /mnt/cache/CloudNAS /mnt/user/media ./cd2-config
docker compose -f compose.cd2.yml up -d
docker compose -f compose.cd2.yml logs --tail=100`},
    'mount-check': {label:'检查宿主机的挂载传播',text:`findmnt -o TARGET,PROPAGATION -T /mnt/cache/CloudNAS
# 如需将该目录单独设为共享挂载点，按宿主系统方案执行：
mountpoint -q /mnt/cache/CloudNAS || sudo mount --bind /mnt/cache/CloudNAS /mnt/cache/CloudNAS
sudo mount --make-rshared /mnt/cache/CloudNAS`},
    'shared-mounts': {label:'三套容器的 volumes 配置',text:`# CloudDrive2
volumes:
  - /mnt/cache/CloudNAS:/CloudNAS:shared

# DIAN115
volumes:
  - /mnt/cache/CloudNAS:/CloudNAS:rslave
  - /mnt/user/media:/媒体库

# Emby：与 DIAN115 的宿主机目录、容器目标路径一致
volumes:
  - /mnt/cache/CloudNAS:/CloudNAS:rslave
  - /mnt/user/media:/媒体库`},
    'flaresolverr-compose': {label:'追加到 DIAN115 的 Compose · 同一网络',text:`services:
  # 保留原有 dian115 服务，将下面服务加入同一份文件
  flaresolverr:
    image: ghcr.io/flaresolverr/flaresolverr:latest
    container_name: flaresolverr
    restart: unless-stopped
    environment:
      - LOG_LEVEL=info
      - TZ=Asia/Shanghai
    volumes:
      - ./flaresolverr:/config
    # 同一 Compose 默认网络通过服务名访问，无需映射端口`},
    'flaresolverr-start': {label:'启动 FlareSolverr',text:`docker compose up -d flaresolverr
docker compose logs --tail=100 flaresolverr`},
    'flaresolverr-remote': {label:'独立部署时追加端口 · 使用实际内网 IP',text:`# 追加到 flaresolverr 服务，替换为这台主机的实际内网 IP
ports:
  - "192.168.1.10:8191:8191"
# DIAN115 中填写 http://192.168.1.10:8191`}
  },
  groups: [
    { id: 'automate', title: '让收藏，自动生长', label: '发现与自动化', icon: 'spark', subtitle: '从一句“想看”，到一部已入库的作品。', items: [
      {id:'discover',title:'探索发现',desc:'电影、剧集与多个资源来源，在同一个入口探索。',route:'automation/discovery'},
      {id:'subscribe',title:'媒体订阅',desc:'电影、剧集、演员订阅，配合来源和质量策略持续追新。',route:'automation/subscriptions'},
      {id:'calendar',title:'追剧日历',desc:'按日期查看订阅剧集的播出计划与更新状态。',route:'automation/calendar'},
      {id:'organize',title:'媒体整理',desc:'识别、刮削、分类、命名，评分洗版与多版共存。',route:'automation/organizing'},
      {id:'strm',title:'STRM 与虚拟影库',desc:'维护目录树与同步规则，生成轻量、可扫描的播放入口。',route:'automation/portable-strm'}
    ]},
    { id: 'media', title: '给每一份收藏，找到位置', label: '媒体与资源', icon: 'film', subtitle: '云端资源、本地文件与播放服务，相互连接。', items: [
      {id:'my-media',title:'我的媒体与 Emby',desc:'媒体浏览、缺集补全、质量检查、分享与多实例播放代理。',route:'resources/media'},
      {id:'files',title:'文件管理',desc:'目录书签、批量改名、原地刮削，以及文件整理与分享。',route:'resources/files'},
      {id:'accounts',title:'115 账号配置',desc:'主账号、备用 CK、目录策略、登录检查和账号运维。',route:'resources/accounts'},
      {id:'pt',title:'PT 与下载管理',desc:'站点认证、搜索、RSS，连接 qBittorrent 或 Transmission。',route:'resources/sites'},
      {id:'music',title:'音乐中心',desc:'音乐源、资料编辑、专辑、歌单、歌词与独立播放器。',route:'automation/music'}
    ]},
    { id: 'extend', title: '好用，还可以更顺手', label: '插件与扩展', icon: 'grid', subtitle: '将日常的小步骤，接成自己的工作流。', items: [
      {id:'plugins',title:'内置插件',desc:'秒传、迁移、推送、字幕、机器人、视频下载等 21 项工具。',route:'resources/plugins'},
      {id:'notifications',title:'三通道通知',desc:'Telegram、企业微信、微信 ClawBot 各自配置和触发。',route:'resources/plugins/notifications'},
      {id:'ai',title:'点点 AI 助手',desc:'解释状态、流式对话，按使用位置选择模型与管理工具。',route:'control/settings'},
      {id:'satellite',title:'卫星发布树',desc:'按 STRM 规则发布目录树，为客户端分配独立访问凭据。',route:'control/settings'},
      {id:'plugin-platform',title:'用户插件',desc:'从插件仓库管理扩展，区分第三方插件与内置能力。',route:'resources/plugins'}
    ]},
    { id: 'operate', title: '每一次运行，都有迹可循', label: '控制与运维', icon: 'activity', subtitle: '从连接状态到任务详情，理解系统正在做什么。', items: [
      {id:'dashboard',title:'总览',desc:'连接健康、系统资源、任务、下载和播放汇总。',route:'overview'},
      {id:'queue',title:'任务队列与日志',desc:'追踪阶段、进度、调度与原始错误，定位具体失败环节。',route:'control/jobs'},
      {id:'cache',title:'缓存与数据运维',desc:'TMDB、FFP、分享与播放缓存，以及实时播放与使用趋势。',route:'control/cache'},
      {id:'container',title:'DianCupLite',desc:'容器状态、镜像检查、更新队列和计划任务。',route:'control/container-update'},
      {id:'settings',title:'系统设置',desc:'CD2 / AURA、网络、安全、API、词表与 AI 提供商。',route:'control/settings'}
    ]}
  ],
  portal: [
    {id:'overview',title:'概览',group:'core',desc:'公告、账户有效期、最近入库与观影足迹。'},
    {id:'account',title:'账户中心',group:'core',desc:'资料、密码、续期、Telegram 绑定与邀请朋友。'},
    {id:'115',title:'115 账号',group:'core',desc:'独享账号扫码 / CK 绑定与检查；共享连接由管理员维护。'},
    {id:'media',title:'媒体库',group:'media',desc:'浏览当前 Emby 权限允许访问的电影、剧集与最近入库。'},
    {id:'requests',title:'求片',group:'media',desc:'搜索电影或剧集、选择季数、填写备注并跟踪处理。'},
    {id:'server',title:'服务连接',group:'media',desc:'服务器状态、访问线路、在线会话与个人播放缓存。'},
    {id:'watchlist',title:'想看 / 看过',group:'media',desc:'保存观影计划，记录看过、个人评分与短评。'},
    {id:'history',title:'播放历史',group:'media',desc:'按时间线回访播放记录；已结束播放计入时长。'},
    {id:'checkin',title:'签到积分',group:'social',desc:'签到日历、连续天数、积分余额和收支流水。'},
    {id:'shop',title:'积分商店',group:'social',desc:'浏览可兑换商品、使用积分并查看兑换记录。'},
    {id:'community',title:'观影社区',group:'social',desc:'分类发帖、回复、点赞，按最新、热门或活跃度浏览。'},
    {id:'achievements',title:'成就排行',group:'social',desc:'观看目标、个人成就、观看时长与播放次数排行。'},
    {id:'badges',title:'勋章收藏',group:'social',desc:'按稀有度和分类收藏勋章，选择佩戴展示。'},
    {id:'resources',title:'资源分享',group:'social',desc:'提交资源链接与版本说明，审核通过后获得积分。'},
    {id:'messages',title:'消息中心',group:'support',desc:'系统通知、站点动态、未读消息与批量已读。'},
    {id:'tickets',title:'工单支持',group:'support',desc:'按分类、优先级提交问题，与管理员持续回复沟通。'}
  ],
  plugins: [
    ['文件秒传','以 SHA1 秒传本地文件到 115，支持失败时普通上传或 CD2 后处理。','rapid-upload'],
    ['外部推送','接收其他项目推送的 115、ED2K 与磁力链接，按配置转存或离线。','external-push'],
    ['多号云迁移','将主账号目录中目标账号缺失的内容单向补齐，支持定时与实时跟随。','account-migration'],
    ['文件清理','扫描本地或 CD2 目录，按条件清理文件与文件夹，保护系统配置目录。','file-cleanup'],
    ['秘享空间','将选中内容生成限时、限次短码，领取后进入转存队列。','mystery-share'],
    ['推送助手','目录监听、用户接力秒传、Telegram 小程序与订阅偏好派送。','push-assistant'],
    ['Telegram 频道监控','独立维护资源解析、消息转发与视频保存工作流。','tg-channel'],
    ['SnowLuma QQ 监控','接入 OneBot WebSocket，采集群聊 / 私聊并执行资源规则。','qq-monitor'],
    ['私聊机器人','会话收件箱、网页与群组话题回复、关键词自动回复和广告拦截。','tg-private-bot'],
    ['群组管理机器人','S.O. 专属：欢迎验证、防护策略、成员权限、AI 配额与审计。','tg-group-bot'],
    ['Emby 封面生成','为媒体库生成统一风格封面，支持样式、字体与批量刷新。','emby-cover'],
    ['通知中心','Telegram、企业微信与微信 ClawBot，事件开关和静默时段各自独立。','notifications'],
    ['每日统计海报','以今日或昨日数据生成可编辑统计海报，配合独立消息模板发送。','daily-report'],
    ['PT 刷流','按促销、H&R、大小、做种数与删种策略添加和维护任务。','pt-brush'],
    ['癫影','以 OpenAPI Key 接入签到、分享与检索；Key 创建依赖平台 VIP。','dianying'],
    ['PT 站点统计','集中查看上传、下载、分享率、魔力与做种数据。','pt-site-stats'],
    ['Emby 媒体画像','读取容器、媒体流与章节，匹配 115 SHA1 并汇报 FFP 画像。','emby-media-lite'],
    ['CLASH 监控','监控代理访问健康，联动 Clash / Mihomo Selector 切换节点。','clash-monitor'],
    ['AI 字幕翻译','将已有非中文文本字幕翻译为中文 SRT，查看对照、任务与用量。','ai-subtitle'],
    ['视频下载器','解析视频、音频与播放列表，配置格式、目录、代理和浏览器接入。','video-downloader'],
    ['STRM 助手','批量替换 STRM 内容，支持正则与捕获组，先预览命中再执行。','strm-helper']
  ],
  setup: [
    {title:'准备与部署',short:'先给收藏一个家',text:'先部署 CloudDrive2，规划 shared / rslave 挂载与媒体目录，再启动 DIAN115。使用需验证的资源站时，按需加入 FlareSolverr。',doc:'deploy'},
    {title:'账号与连接',short:'接通你的云端',text:'初始化管理员与授权，添加 115 主账号。配置 CD2 地址与 API Token，自动读取 /CloudNAS/CloudDrive，并选择主账号实际对应的云盘。',doc:'connections'},
    {title:'媒体与规则',short:'把第一部作品归好档',text:'接入 Emby，先在小目录验证识别、分类与命名。生成少量 STRM，确认扫描与播放；再开启实时或定时同步。',doc:'first-library'},
    {title:'自动化与扩展',short:'让日常变得更轻松',text:'按需加入 PT、下载器、订阅、通知、音乐与 AI。共享给其他用户时，再配置门户、访问线路与邀请码。',doc:'automation'}
  ],
  docs: {
    about:{title:'DIAN115 是什么',kicker:'THE IDEA',lead:'把云端收藏，变成触手可及的私人影音空间。',sections:[
      ['围绕媒体的一套工作流','DIAN115 是面向自托管用户的媒体自动化控制中心。它连接 115 网盘、CloudDrive2 / AURA、Emby、PT 来源与通知系统，将发现、订阅、转存、整理、元数据、STRM 和播放请求组织成可以追踪的任务。'],
      ['组件如何协作','115 提供文件、分享与离线能力；CD2 或 AURA 让云端目录可访问；DIAN115 负责识别、规则和任务编排；Emby 等媒体服务负责媒体浏览与播放。各环节可以按实际需要组合。'],
      ['从个人收藏到用户门户','个人使用可以先完成一个账号、一条整理规则与一次播放。需要服务家庭、朋友或社区时，再加入独立门户、账号分配、求片、工单、积分与社区功能。'],
      ['开始前需要什么','准备一台可运行 Linux Docker 的主机、持久化目录，以及计划使用的外部服务账号。具体能力受授权、依赖连接和功能开关共同影响。']
    ]},
    discover:{title:'探索发现',kicker:'DISCOVER',lead:'先找到故事，再选择适合你的资源。',sections:[['媒体探索','电影与剧集支持热度、上映时间、评分、类型、语言、年份和地区筛选。媒体身份由 TMDB 元数据承接，可在探索后创建订阅。'],['资源来源','PT、癫影与 Telegram 频道采集是不同来源；公开索引页签提供磁力检索。来源的认证、网络和可用性分别配置，某一个来源异常不代表其他来源不可用。'],['连接到自动化','选中媒体后可按来源与质量策略订阅；直接找到资源则进入下载、转存或离线链路。落地位置由账号目录与对应来源配置决定。']]},
    subscribe:{title:'媒体订阅',kicker:'FOLLOW A STORY',lead:'把“想看”保存下来，让更新有一个明确的目标。',sections:[['电影、剧集与演员','电影和剧集按 TMDB 身份持续追踪，剧集结合季集覆盖判断。演员订阅先确认人物，再按媒体类型、年份等条件筛选作品，可暂停、重新评估和查看排除原因。'],['来源与质量','可组合癫影、PT、TG 和聚合策略；电影、剧集维护质量方案。候选按优先级比较，失败时可尝试其他来源。'],['搜索、RSS 与后处理','PT 周期搜索与 RSS 匹配分别控制。下载完成后，视频或字幕可秒传到 115，失败按配置回退普通上传或 CD2 后处理。PT 下载完成与 115 后处理属于不同任务，应分别查看结果。']]},
    calendar:{title:'追剧日历',kicker:'COMING NEXT',lead:'下一集什么时候来，在日历里一目了然。',sections:[['按日期回访订阅','日历展示订阅剧集的播出与更新计划，帮助区分尚未播出、未找到资源、下载未完成和入库缺集。'],['排查更新状态','先确认订阅是否启用与季集范围，再查看资源搜索、下载器和整理队列。播出日期不等于已经拥有可入库资源。']]},
    organize:{title:'媒体整理',kicker:'A PLACE FOR EVERYTHING',lead:'文件名、身份和版本，逐步整理成一份可靠的收藏。',sections:[['识别与刮削','使用词表与文件 / 路径证据提取标题、年份、季集和技术字段；TMDB 确认媒体身份，ffprobe 提供流信息。可按条件使用 AI 辅助识别。'],['路径与执行方式','本地规则支持本地到本地的移动或硬链接，硬链接需要同一文件系统；CD2 规则的源和目标均位于挂载根下，由服务执行移动。不要把混合路径当成同一种规则。'],['版本决策','单一版本可跳过、按大小覆盖或评分洗版；多版共存可全部保留或在 4K、DV、HDR、1080P 等槽位内竞争。历史记录保留决策结果。'],['先验证，再扩展','用少量文件测试识别、命名、分类、字幕联动与版本规则。确认输出和历史后再扩大范围；第一次调试保留源文件更容易核对。']]},
    strm:{title:'STRM 与虚拟影库',kicker:'LIGHTWEIGHT LIBRARY',lead:'用轻量文件，为云端内容建立稳定的播放入口。',sections:[['目录树与 STRM','STRM 规则维护源目录树、输出路径、链接模式与同步状态。先全量建树，再小范围生成文件；Emby 扫描输出，播放请求交给对应代理或重定向链路。'],['同步与清理','支持全量、增量、实时或定时同步，孤立清理移除已不存在的输出。反向代理场景下，生成链接使用的外部地址必须能被播放端访问。'],['虚拟影库','虚拟影库可以解析外部 115 分享或已有 P1 标记，预览支持的媒体并输出跨实例使用的虚拟文件。冲突策略包括跳过、覆盖或添加序号；使用前核对输出目录。'],['旧库迁移','已有 Emby 库时，先保留目录树和媒体画像，完成路径匹配、Madby / FFP 接入，再生成新 STRM 与扫描新库。']]},
    'my-media':{title:'我的媒体与 Emby',kicker:'YOUR COLLECTION',lead:'从媒体视角回访收藏，补齐缺集，选择准确的分享范围。',sections:[['媒体工作区','浏览电影、剧集与已有版本，查看媒体统计、缺集与质量状态，选择 Emby 实例和媒体库。'],['精确分享','按电影版本、剧集季度、单集和字幕选择范围，支持 115 链接、ED2K、Telegram、癫影或秘享短码。真实分享依赖文件树中的 115 身份和可转换的 Emby 路径。'],['多实例代理','配置各实例后端、API Key、播放线路与路径转换。高级版最多 3 个 Emby 代理实例，S.O. 最多 6 个；具体端口应与部署映射一致。']]},
    files:{title:'文件管理',kicker:'KEEP IT IN ORDER',lead:'把人工整理需要的最后几步，也放在同一个地方。',sections:[['浏览与基础操作','容器可见目录支持面包屑、书签、列表 / 网格、排序与批量选择。提供上传、下载、预览、新建、改名、复制、移动与删除。'],['媒体操作','可执行识别、原地刮削、批量改名，或交给已启用整理规则；选中内容可生成秘享码。先确认当前路径、规则和任务范围。'],['目录边界','操作以容器中的实际路径为准。直接删除会作用于真实文件，不能把本地删除当作 115 回收站。']]},
    accounts:{title:'115 账号配置',kicker:'CONNECTED TO YOUR CLOUD',lead:'账号、目录和连接状态，分别管理才更清楚。',sections:[['主账号池','扫码添加、检查、刷新、编辑与激活账号。活跃主账号供全局客户端使用，支持自动切换、QPS、签到、空间与 VIP 状态查看。'],['备用 CK 与用途','备用 CK 独立于活跃主账号，不参与主账号自动切换、签到和全局目录配置。只有明确支持备用池的功能会使用它。'],['目录策略','分别设置转存、离线、秘享接收与来源默认目录。为主账号选择真实对应的 CD2 云盘，避免跨账号目录错配。'],['常见运维','检查 Cookie 有效性，按需要设置安全码，维护分享记录与回收站。首次接入后通过小范围任务验证目录 CID。']]},
    pt:{title:'PT 与下载管理',kicker:'RESOURCE SOURCES',lead:'认证、搜索和下载，一层一层接通。',sections:[['站点配置','维护站点类型、域名、认证、代理、超时、搜索与 RSS。可以刷新上传、下载、分享率、等级、魔力和做种数据。'],['下载器','连接 qBittorrent 或 Transmission，确认 WebUI、账号、默认客户端、保存路径与任务标签。先手动提交一个测试任务。'],['自动化接入','搜索结果可进入订阅策略，RSS 用于持续匹配。PT 刷流会主动添加和删除任务，应在站点与下载器验证后按需求开启。']]},
    music:{title:'音乐中心',kicker:'A SOUNDTRACK FOR YOUR DAY',lead:'影像之外，也为好音乐留一个位置。',sections:[['音乐源与资料','添加音乐源，读取音频资料，检查歌曲、专辑、艺术家、封面和重复文件。可手动修正信息与封面。'],['独立播放器','音乐端包含专辑、艺术家、歌曲、搜索、收藏、歌单、同步歌词和播放队列，支持主题切换与 PWA 安装。独立音乐账号和权限由管理端配置。'],['服务与兼容','配置音乐源与用户权限后，可进入独立音乐播放器。需要第三方音乐客户端时，根据客户端支持情况配置 Subsonic 兼容服务。']]},
    plugins:{title:'21 项内置工具',kicker:'THE TOOLBOX',lead:'每一个小工具，都服务于一段具体的日常工作。',sections:[['按需要启用','内置插件随主程序运行；其配置、依赖与任务仍由主程序管理。它们与第三方用户插件不是同一种发布和运行机制。'],['依赖先行','使用前确认相应的账号、目录、媒体服务、下载器、机器人或代理连接。任务结果可回到统一任务队列查看。']],pluginList:true},
    notifications:{title:'通知中心',kicker:'STAY IN THE KNOW',lead:'重要的进展，送到你习惯使用的地方。',sections:[['三个独立渠道','Telegram、企业微信和微信 ClawBot 分别维护事件开关、静默时段、文案模板与图片配置。一个渠道的静默不影响另外两个。'],['Telegram 模板','支持经典 HTML 与 Rich Message / 结构化 Blocks。在通知设计器内选择事件，查看该事件支持的变量，完成预览、保存和测试消息。'],['配置顺序','先验证账号与接收对象，再选事件、静默时段和模板。企业微信需要相应应用信息及回调配置；每个渠道使用各自支持的格式和变量。'],['事件与变量','整理完成、订阅更新、转存结果等事件可分别启用。编辑模板时，从当前事件的可用变量列表插入字段，预览实际样例；发送测试消息确认接收与排版后再启用。']]},
    ai:{title:'点点 AI 助手',kicker:'A LITTLE HELP',lead:'用自然语言了解系统，也让重复操作少一点。',sections:[['网页与聊天入口','支持流式回复、推理与工具进度、Markdown、复制、停止生成、新会话及历史。管理与闲聊场景可以选择不同工具范围。'],['提供商与使用位置','支持 OpenAI 兼容 Chat Completions / Responses 协议。网页助手、Telegram 助手、媒体识别、AI 字幕等位置可以分别选择提供商与模型。'],['管理工具','管理模式可读取系统、账号、订阅、任务、PT 和整理状态，也可在授权范围内执行后台操作。保留危险操作确认，敏感凭据应由后端配置。']]},
    satellite:{title:'卫星发布树',kicker:'CONNECTED INSTANCES',lead:'把明确的一部分目录树，交给明确的客户端。',sections:[['按规则发布','选择指定 STRM 规则发布文件树，供其他 DIAN115 子服务实例读取。发布范围由允许规则控制。'],['客户端管理','每个客户端独立名称、API Key、允许规则、到期与备注。心跳报告版本、在线状态和本地文件数量；请求可按来源与结果审计。'],['维护方式','客户端退役时吊销对应凭据。不要让多个实例共用一个 API Key，便于定位和单独撤销访问。']]},
    'plugin-platform':{title:'用户插件',kicker:'MAKE ROOM FOR MORE',lead:'把扩展交给明确的协议和独立的管理入口。',sections:[['与内置工具区分','用户插件从插件仓库安装和管理，使用独立的插件协议与界面接入；内置工具直接随主程序编译。使用文档和问题排查应按这两种体系区分。'],['管理入口','在插件中心维护仓库与安装项，查看操作结果并进入插件页面。安装前核对来源、权限和兼容性，实际能力以插件说明为准。']]},
    dashboard:{title:'总览',kicker:'AT A GLANCE',lead:'先知道系统是否连接，再知道任务有没有向前。',sections:[['连接与资源','集中观察 115、CD2、媒体服务等连接，系统 CPU、内存、空间与账号状态。'],['任务与播放','查看任务进度、下载速度、播放统计和在线会话。日常排查先看连接，再看失败任务，再读对应日志。']]},
    queue:{title:'任务队列与日志',kicker:'EVERY STEP COUNTS',lead:'把“出了问题”，缩小到一个明确的步骤。',sections:[['任务阶段','查看整理、转存、秒传、字幕、STRM、分享和插件任务的状态、阶段、耗时、进度与关联规则。失败任务的原始错误比整体统计更有诊断价值。'],['调度与日志','查看定时任务、Cron 和下次执行时间；日志可按类型、级别和关键词筛选。反馈问题时提供版本、操作步骤与脱敏后的相关片段。']]},
    cache:{title:'缓存与数据运维',kicker:'A RELIABLE MEMORY',lead:'复用有价值的信息，也看见系统的实时变化。',sections:[['缓存中心','包括 TMDB、115 分享、链接黑名单、链接状态绑定、虚拟缓存、TG 分享、离线链接与 FFP-cache。缓存减少重复请求，但不能替代账号、来源和路径配置。'],['FFP','以 SHA1 复用容器、媒体流、章节与技术信息。本地优先、远端命中写回，低完整度信息避免覆盖更完整的记录。'],['数据运维','高级版和 S.O. 可使用数据运维入口，观察实时播放、在线会话、实例与使用趋势，并转到门户账号管理。']]},
    container:{title:'DianCupLite 容器管理',kicker:'CARE FOR THE SYSTEM',lead:'把容器维护也纳入可查看的工作流。',sections:[['状态、镜像与更新','查看容器资源和镜像，检查远端更新，通过队列手动或定时执行更新。支持启动、停止与重启等运维操作。'],['部署依赖','容器管理需要部署时提供受控的 Docker 访问。普通媒体功能不依赖此项；请按自己的部署方案配置 socket proxy 或相应权限。'],['更新前','备份 /config，结束重要任务，再更新关键服务。升级后核对连接、配置与最近日志。']]},
    settings:{title:'系统设置',kicker:'MAKE IT YOURS',lead:'连接、安全与规则，共同决定系统如何工作。',sections:[['网盘文件服务','当前设置支持 CD2 与 AURA，分别保存地址、令牌和挂载根。选择服务并检查目录在 DIAN115 内实际可读。'],['网络与安全','配置 TMDB 服务与图片地址、HTTP 代理、FlareSolverr、安全密码、两步验证与 OpenAPI Key。桥接网络内的 127.0.0.1 指向容器自身。'],['词表与 AI','维护识别替换、制作组、分类词表和 AI 提供商池。媒体整理、网页助手和字幕使用位置可以分别选模型。']]},
    deploy:{title:'部署 DIAN115',kicker:'GET CONNECTED',lead:'先部署挂载服务，把三套容器的路径接好，再启动你的影音空间。',sections:[['部署前','准备 Linux / NAS、Docker Engine 和 Compose v2。先部署 CD2，确认 /dev/fuse 可用和宿主机支持共享挂载，再为 DIAN115 与 Emby 规划一致的目录。AURA 用户可按自身部署方案连接文件服务。',{guides:['cd2','paths']}],['目录与持久化','/config 保存账号、授权和配置；/dian115AI 保存 AI 工作区。示例将 /mnt/user/media 映射为 /媒体库，将 /mnt/cache/CloudNAS 映射为 /CloudNAS:rslave；这两项在 Emby 中保持一致。所有路径都可替换，但要同步修改相关容器与规则。'],['最小 Compose','下方提供独立编写的运行示例，使用已发布镜像。按实际 Emby 代理实例映射端口；挂载传播仍需要 CD2 与宿主机共同支持。'],['FlareSolverr 按需部署','使用 UIndex 等需要 Cloudflare 验证的来源时，额外部署 FlareSolverr，再在系统设置的“FlareSolverr 过盾设置”填写地址、保存并测试。普通网盘挂载与播放不依赖它。',{guides:['flaresolverr']}],['首次启动','运行 docker compose pull 与 docker compose up -d，访问 http://服务器IP:8095。初始化管理员密码并激活授权；连接 CD2、自动读取挂载点，再从文件管理确认挂载目录可读。'],['验收与备份','测试小范围整理、STRM 输出与 Emby 播放，确认 CD2 重启后目录仍可见。升级前备份完整 /config；AI 工作区有内容时一同备份。']],code:'compose'},
    cd2:{title:'CloudDrive2 部署与接入',kicker:'CONNECT YOUR CLOUD',lead:'从容器启动到自动读取挂载点，让云盘目录真正可用。',sections:[['1. 准备 Linux / NAS 主机','确认系统支持 FUSE，存在 /dev/fuse，并准备持久化的 CD2 配置目录与云盘挂载目录。下方示例使用宿主机 /mnt/cache/CloudNAS；按自己的 NAS 路径调整。示例采用 CD2 官方支持的 Host 网络与 FUSE 权限配置。',{code:'cd2-compose'}],['2. 启动 CD2','将示例保存为 compose.cd2.yml，创建目录后启动。打开 http://服务器IP:19798，注册或登录 CD2，添加自己的 115 账号。Host 网络不再使用 ports 映射；19798 是这台宿主机上的 CD2 入口。',{code:'cd2-start'}],['3. 确认共享挂载传播','CD2 的 /CloudNAS 使用 :shared；宿主机上的对应挂载点也要支持 shared / rshared。若容器启动提示挂载未共享，先检查宿主机传播属性。下方命令用于普通 Linux 的独立挂载点示例；NAS 的持久化方式按系统设置，宿主机重启后也要验证。',{code:'mount-check'}],['4. 配置 CloudDrive 挂载与 Token','在 CD2 的挂载设置中，挂载点名称使用 CloudDrive，源目录选择根目录 /，启用启动时自动挂载，挂载在 /CloudNAS 下。创建供 DIAN115 使用的 API Token，至少允许文件读取、创建、修改与删除。'],['5. 在 DIAN115 连接 CD2','进入系统设置 → 网盘文件服务，选 CD2，填写如 http://192.168.1.10:19798/ 的 API 地址与 Token。保存后点击“自动读取”，确认挂载路径类似 /CloudNAS/CloudDrive。这里使用 DIAN115 容器内看到的路径，不填宿主机 /mnt/cache/CloudNAS。'],['6. 关联主账号与验证','进入账号配置，添加 115 主账号，选中它实际对应的 CD2 云盘。云盘名称使用 CD2 中的真实名称，如 115open；目录从正确云盘的根开始选择。最后检查文件管理能浏览该云盘，再创建整理和 STRM 规则。',{guides:['paths','connections']}]]},
    paths:{title:'CD2、DIAN115 与 Emby 路径搭配',kicker:'ONE DIRECTORY TREE',lead:'同一份文件，在宿主机和各容器里分别叫什么，一次说清。',sections:[['1. 两个共享目录，三套容器','云盘挂载目录用来接收 CD2 的 FUSE 子挂载；媒体目录用来保存整理输出或本地 STRM。CD2 发布挂载，DIAN115 与 Emby 接收挂载。DIAN115 和 Emby 的宿主机来源、容器目标路径保持一致。',{code:'shared-mounts'}],['2. 路径对照表','左侧是宿主机目录，右侧才是程序配置要填写的容器路径。:shared 与 :rslave 是卷挂载选项，不是路径名称的一部分。',{table:{headers:['位置 / 用途','示例路径或配置','在哪里使用'],rows:[['宿主机云盘目录','/mnt/cache/CloudNAS','CD2、DIAN115、Emby 的 volumes 左侧'],['CD2 发布挂载','/CloudNAS:shared','CD2 的 volumes 右侧'],['DIAN115 / Emby 接收','/CloudNAS:rslave','两个容器的 volumes 右侧'],['CD2 自动读取挂载点','/CloudNAS/CloudDrive','DIAN115 → 系统设置 → 网盘文件服务'],['主账号云盘名称','115open（示例）','账号配置中选择真实 CD2 云盘'],['云盘中的电影目录','/CloudNAS/CloudDrive/115open/电影','文件管理 / 规则的本地挂载路径示例'],['宿主机媒体输出','/mnt/user/media','DIAN115 与 Emby 的 volumes 左侧'],['容器媒体输出','/媒体库/strm','DIAN115 的 STRM 输出与 Emby 扫描目录']]}}],['3. shared 与 rslave 为什么不同','CD2 使用 shared 将云盘子挂载传播到宿主机。DIAN115 与 Emby 使用 rslave 接收宿主机的挂载变化，CD2 重启后重建的子挂载也能继续看见。宿主机传播未配置时，单独写 :rslave 无法解决问题。修改 volumes 后需要重新创建容器。'],['4. 挂载点、云盘名与目录不要混用','/CloudNAS 是容器卷根；/CloudNAS/CloudDrive 是自动读取的挂载点；115open 是 CD2 的云盘名称。真实云盘名以自己的 CD2 为准。CD2 API 的目录选择器和本地文件选择器可能显示不同前缀，应使用对应入口选择目录。'],['5. 从 STRM 输出到 Emby 扫描','例如 DIAN115 把 STRM 输出到 /媒体库/strm，Emby 也将这个目录作为媒体库目录。容器中的 /媒体库/strm 实际对应宿主机 /mnt/user/media/strm。若已有 Emby 路径不同，先配置路径转换并检查匹配，再扫描，避免重复条目。'],['6. 按配置引导逐步验收','先对齐三套 Compose → 在 CD2 挂载根目录并生成 Token → DIAN115 保存 CD2 地址并自动读取 → 添加 115 主账号并选云盘 → 配置整理与 STRM → 首次全量同步 → 在我的媒体控制中心接入 Emby。先用一部作品确认读取、输出和播放，再扩大范围。']]},
    flaresolverr:{title:'FlareSolverr 部署与配置',kicker:'CONNECT RESOURCE SOURCES',lead:'需要 Cloudflare 验证的资源站，多接好一个服务。',sections:[['什么时候需要','UIndex 等来源可能触发 Cloudflare 验证。遇到此类验证时部署 FlareSolverr，由它提供浏览器处理能力；普通 115、CD2 与 Emby 连接无需因此额外配置。验证能否成功还取决于资源站当时的限制。'],['同一 Compose 部署','把下方服务加入 DIAN115 的 Compose 文件，保留已有 dian115 配置。两个服务都使用默认桥接网络时，可以直接通过 http://flaresolverr:8191 访问；自定义网络时，将它们接入同一个网络。',{code:'flaresolverr-compose'}],['启动与查看状态','保存 Compose 后启动服务并查看日志。首次请求需要启动浏览器环境，可能比后续请求慢。',{code:'flaresolverr-start'}],['在 DIAN115 配置','进入系统设置 → FlareSolverr 过盾设置，服务地址填写 http://flaresolverr:8191，点击保存 FlareSolverr 设置，再点击测试连接。确认测试成功后，回到对应来源重新搜索。地址在界面保存，不使用其他服务的代理地址替代。'],['独立部署或 Host 网络','如果 FlareSolverr 与 DIAN115 不在同一个 Docker 网络，使用 FlareSolverr 主机的实际内网 IP 并发布 8191 端口。DIAN115 使用 Host 且与服务同机时才可使用 http://127.0.0.1:8191；桥接网络里的 127.0.0.1 指向 DIAN115 容器自身。',{code:'flaresolverr-remote'}],['连接失败时','依次检查容器是否运行、服务地址与端口、网络可达性、日志和来源状态。8191 仅供自己的实例或内网访问；连接测试通过只能说明服务可达，不保证所有站点验证都能成功。']]},
    connections:{title:'连接账号与服务',kicker:'CONNECT THE PIECES',lead:'让一条最小链路真正连通，再逐步添加服务。',sections:[['管理员与授权','完成首次密码初始化与 License Key 激活，确认重启后状态仍保留。'],['CD2 部署与路径','先在 CD2 设置 CloudDrive 根目录挂载与 API Token；DIAN115 与 Emby 的 /CloudNAS 使用 rslave，媒体目录保持同一路径。',{guides:['cd2','paths']}],['CD2 或 AURA','在系统设置 → 网盘文件服务选择 CD2，保存 API 地址与 Token，点击自动读取，确认返回 /CloudNAS/CloudDrive。使用 AURA 时切换为 AURA 并按实际服务配置。'],['115 主账号','扫码添加并选为活跃账号，选择它真实对应的 CD2 云盘；分别设置转存、离线、秘享接收目录。'],['FlareSolverr','需 Cloudflare 验证的来源在系统设置配置 FlareSolverr 服务地址、保存并测试。同一 Compose 网络可使用 http://flaresolverr:8191。',{guides:['flaresolverr']}],['Emby','在我的媒体 → 控制中心添加 Emby 后端、API Key 与代理端口。确认媒体目录与 DIAN115 一致；需要时配置路径转换。先验证库统计、单个条目与播放，再开启大范围扫描。'],['已有媒体库迁移','已有媒体库时先构建目录树但不生成 STRM；读取 Emby 媒体画像、检查路径匹配、接入 Madby 并上报 FFP，最后切换新 STRM。']]},
    'first-library':{title:'建立第一份媒体库',kicker:'YOUR FIRST COLLECTION',lead:'从一部作品开始，确认每个细节都如预期。',sections:[['准备测试目录','选择一个小目录，确认源与目标模式一致，输出对 Emby 可见。'],['测试整理规则','核对媒体识别、TMDB、命名、分类、字幕和版本策略。先保留被过滤或替换的源文件。'],['生成与播放','同步目录树，少量生成 STRM，扫描 Emby。确认路径转换、播放地址与对应账号生效。'],['开启同步','验证成功后选择定时或实时模式，观察任务队列和日志，再扩大到更多目录。']]},
    automation:{title:'开启自动化',kicker:'LET IT FLOW',lead:'给自动化一个可靠的起点。',sections:[['资源来源','先验证下载器连接、目录和任务，再接入 PT 认证、搜索、RSS、TG 或癫影。'],['订阅策略','设置电影 / 剧集的质量方案与来源优先级，创建一个订阅并观察搜索、下载 / 转存、后处理、整理的独立结果。'],['消息通知','验证渠道与接收对象，再启用事件模板和静默时段。Telegram、企业微信、微信各自保存。'],['扩展能力','按需启用音乐、AI、字幕或机器人。准备多人服务时，最后配置门户、权限、访问线路与邀请码。']]},
    personal:{title:'个人与家庭使用',kicker:'YOUR OWN LITTLE CINEMA',lead:'为喜欢的故事，留出更多时间。',sections:[['一个轻量起点','一个主账号、一套连接、一条小范围规则、一次成功播放，就能验证个人使用链路。'],['每日回访','探索喜欢的电影，订阅追看的剧集，在日历看更新。整理完成后从 Emby 或你的播放端回访收藏。'],['把偏好写成规则','按分辨率、质量、语言或多版槽位配置收藏方式，用规则减少每次手动判断。'],['音乐与助手','音乐中心收藏专辑与歌单，点点帮助解释系统状态；重要进展通过你常用的通知渠道送达。'],['家人也能轻松使用','门户提供独立的用户入口。高级版支持最多 10 个门户小号；管理员维护共享账号或配置独享模式，用户使用自己的权限范围。']]},
    so:{title:'S.O. 版本',kicker:'MORE ROOM TO PLAY',lead:'为更多用户、更多实例与群组管理，扩展你的空间。',sections:[['高级版共有能力','媒体自动化、用户门户、音乐中心和数据运维，在高级版与 S.O. 中均可使用。S.O. 适合需要更大用户规模与群组管理的场景。'],['用户与实例数量','高级版最多创建 10 个门户小号，S.O. 不设这一数量上限；Emby 代理实例上限分别为 3 与 6。实际容量取决于主机、账号与外部服务。'],['S.O. 群组管理机器人','独立 Telegram 群管 Bot，包含欢迎验证、广告与安全策略、成员权限、命令菜单、群组 AI、独立 Token 配额、审计与 OpenAPI 外部推送。'],['如何选择','个人与家庭场景按日常需要配置；需要更多门户用户、更多 Emby 代理实例或群组管理时，可联系官方了解 S.O. 授权。授权有效期与附加功能以收到的密钥为准。']]},
    license:{title:'捐赠与授权码激活',kicker:'YOUR ACCESS KEY',lead:'支持项目，开启你的私人影音空间。',sections:[['获取渠道','通过 Telegram 联系官方 @succt，说明个人、家庭或多人服务的使用场景，确认授权类型、捐赠金额与发码规则。使用交流可加入 @dian115group。'],['扫码捐赠与接收','使用本页官方二维码完成捐赠，付款备注填写可正常收信的邮箱。保存付款记录，收到 License Key 后妥善保管。S.O. 的获取方式、有效期与附加权益请在捐赠前确认。'],['填写 License Key','首次启动时，在激活页面填写收到的密钥。已激活实例可从账号菜单进入更换密钥；页面提示需要重启时按提示完成。'],['未收到或验证异常','联系官方时提供捐赠时间、付款记录与备注邮箱。验证异常先检查网络、系统时间和日志；反馈问题时隐藏完整密钥。']],contact:true,donation:true},
    portal:{title:'门户功能完整指南',kicker:'A PLACE FOR EVERYONE',lead:'用户有自己的放映室，管理员有清晰的服务工作台。',sections:[['账户与注册','由管理员创建和分配账号，或开启邀请码注册。账户中心维护资料、密码、有效期、续期、Telegram 通知连接与邀请。'],['共享与独享模式','共享模式使用管理员维护的 115 账号池，用户不操作共享凭据；独享模式由用户扫码或手动绑定自己的 115 账号，管理登录检测与安全码。'],['媒体与服务','根据用户在 Emby 中的访问权限展示媒体，提供求片、访问线路、在线会话、个人播放缓存、想看 / 看过和播放历史。'],['社区与积分','签到积分、积分兑换、社区帖子、观影目标、成就排行、勋章佩戴与资源投稿，共同组成用户互动体验。'],['通知与支持','消息中心收取广播与动态；工单按分类和优先级提交，用户与管理员持续回复并跟进状态。'],['管理员工作台','门户总控分为账号中心、求片、工单、社区与积分、通知广播、站点设计、用户缓存、系统配置。可配置功能开关、账号分配、积分规则、商品、勋章和访问线路。'],['版本与上线','高级版最多 10 个门户小号，S.O. 不设这一数量上限。实际入口受功能开关影响，对外访问使用 HTTPS，并验证注册、播放、消息与工单流程。']],portalList:true},
    demo:{title:'在线 Demo',kicker:'SEE IT FOR YOURSELF',lead:'亲自打开，感受每一个真实的功能入口。',sections:[['管理控制台','从总览进入探索、订阅、整理、文件、插件和控制面板。演示站使用真实前端页面和静态演示数据。'],['用户门户','体验独立用户视角：概览、媒体库、求片、积分、社区和工单。'],['音乐播放器','体验专辑、歌曲、歌单、收藏、歌词与播放界面。'],['演示与真实服务','Demo 用于浏览界面和交互，数据与操作由演示环境提供，不连接你的 115 账号或生产媒体库。']]}
  }
};
