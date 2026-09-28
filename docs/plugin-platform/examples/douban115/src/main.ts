import { createApp, defineComponent, h, reactive } from 'vue'
import { NConfigProvider, NDialogProvider, NMessageProvider, NNotificationProvider } from 'naive-ui'
import AppPage from './AppPage.vue'
import './preview.css'

const previewState = reactive({
  revision: 1,
  lastStatus: 'ready',
  lastMessage: '本地预览已就绪',
  config: {
    rsshub_domain: 'https://rsshub.ddsrem.com',
    rank_configs: {},
    douban_user_id: '10000001,10000002',
    wish_enabled: true,
    emby_enabled: false,
    notify: false,
  },
  runState: {},
  rankPreview: {},
  wishPreview: [],
  embyPreview: {},
  ranks: [],
  // 想看订阅用户（昵称/头像来自运行时抓取缓存）
  wishUsers: [
    { id: '10000001', name: '影迷甲', avatar: 'https://img2.doubanio.com/icon/u10000001-1.jpg' },
    { id: '10000002', name: '影迷乙', avatar: 'https://img2.doubanio.com/icon/u10000002-1.jpg' },
  ],
  doubanCookieSet: false,
  embyApiKeySet: false,
})

const previewBridge = {
  async getState() {
    return { state: previewState, state_version: 'preview-v1', etag: '"preview-v1"' }
  },
  async invokeAction(action: string, input?: unknown) {
    if (action === 'dashboard') {
      // 返回深拷贝，模拟真实宿主每次返回新对象（避免同引用导致 Vue 不触发更新）
      return { result: JSON.parse(JSON.stringify(previewDashboard)) }
    }
    if (action === 'clear-history') {
      const scope = (input as any)?.scope || 'all'
      const label = scope === 'rank' ? '榜单' : scope === 'wish' ? '想看' : '全部'
      if (scope === 'rank' || scope === 'all') previewDashboard.rank_history = []
      if (scope === 'wish' || scope === 'all') previewDashboard.wish_history = []
      previewState.lastStatus = 'succeeded'
      previewState.lastMessage = `已清空${label}订阅历史（本地预览）`
      return { result: { status: 'succeeded', message: previewState.lastMessage, cleared: 3, scope } }
    }
    previewState.revision += 1
    previewState.lastStatus = 'succeeded'
    previewState.lastMessage = `本地预览已执行 ${action}`
    return { result: { status: 'succeeded' as const, message: previewState.lastMessage } }
  },
  async refresh() {
    return previewState
  },
}

const mkItem = (rank: number, title: string, year: string, status: string, reason = '') => ({
  rank, title, year, media_type: 'tv', status, reason,
  poster: '', link: 'https://movie.douban.com/subject/36156234/',
})

// 一个较长的榜单，用于验证「榜单快照只展示前 5 项」
const longRankTitles = [
  '银翼杀手2099', '赛博朋克：边缘行者 第二季', '终极名单 第二季', '三体：黑暗森林', '凡人修仙传 第五季',
  '长安十二时辰 第二季', '雾山五行 第三季', '灵笼 第二季', '大理寺日志 第三季', '时光代理人 第三季',
  '伍六七 第五季', '非人哉 第三季', '镇魂街 第五季', '罗小黑战记 第二季',
]

const previewDashboard = {
  status: 'succeeded',
  generated_at: '2026-09-28 10:30:00',
  ranks: [
    { key: 'coming', name: '即将上映', media_type: 'movie', enabled: true, fetched_at: '2026-09-28 08:00:00', items: longRankTitles.map((t, i) => mkItem(i + 1, t, '2026', i % 4 === 0 ? 'subscribed' : i % 3 === 0 ? 'observing' : i % 7 === 0 ? 'removed' : i % 5 === 0 ? 'beyond' : 'filtered')) },
    { key: 'tv_real_time', name: '实时热门', media_type: 'tv', enabled: true, fetched_at: '2026-09-28 08:00:00', items: [mkItem(1, '兰香如故', '2026', 'subscribed'), mkItem(2, '我不是大师', '2026', 'existing'), mkItem(3, '早春晴朗', '2026', 'unresolved')] },
    { key: 'tv_chinese', name: '华语口碑', media_type: 'tv', enabled: true, fetched_at: '2026-09-28 08:00:00', items: [mkItem(1, '交锋', '2026', 'subscribed'), mkItem(2, '开庭', '2026', 'filtered', '评分 6.1 < 7.0')] },
    { key: 'tv_global', name: '全球口碑', media_type: 'tv', enabled: true, fetched_at: '2026-09-28 08:00:00', items: [mkItem(1, '流人 第六季', '2026', 'subscribed'), mkItem(2, '万物生灵 第七季', '2026', 'subscribed')] },
    { key: 'movie_weekly', name: '电影口碑', media_type: 'movie', enabled: false, items: [] },
    { key: 'bangumi', name: 'BangumiTV', media_type: 'tv', enabled: true, fetched_at: '2026-09-28 08:00:00', items: [mkItem(1, 'Re：从零开始的异世界生活 第四季', '2026', 'subscribed'), mkItem(2, '无职转生 第三季', '2026', 'observing')] },
  ],
  rank_history: [
    { title: '流人 第六季', year: '2026', media_type: 'tv', season: 6, source: '全球口碑', source_key: 'tv_global', subscribed_at: '2026-09-26 08:00:00', existing: false, poster: '', link: 'https://movie.douban.com/subject/36156234/' },
    { title: '万物生灵 第七季', year: '2026', media_type: 'tv', season: 7, source: '全球口碑', source_key: 'tv_global', subscribed_at: '2026-09-25 08:00:00', existing: false, poster: '' },
    { title: '兰香如故', year: '2026', media_type: 'tv', season: 1, source: '实时热门', source_key: 'tv_real_time', subscribed_at: '2026-09-25 08:00:00', existing: true, poster: '' },
    { title: '凡人修仙传 第五季', year: '2026', media_type: 'tv', season: 5, source: '即将上映', source_key: 'coming', subscribed_at: '2026-09-24 08:00:00', existing: false, removed: true, poster: '' },
  ],
  wish_history: [
    { title: '老江湖', year: '2026', media_type: 'movie', source: '豆瓣想看', source_key: 'wish', users: ['10000001', '10000002'], subscribed_at: '2026-09-26 08:00:00', existing: false, poster: '' },
    { title: '蝙蝠侠：骑士陨落', year: '2026', media_type: 'movie', source: '豆瓣想看', source_key: 'wish', users: ['10000002'], subscribed_at: '2026-09-25 08:00:00', existing: false, poster: '' },
    { title: '敦煌英雄', year: '2025', media_type: 'movie', source: '豆瓣想看', source_key: 'wish', users: ['10000001'], subscribed_at: '2026-09-24 08:00:00', existing: true, poster: '' },
  ],
  // 每位用户的想看订阅条数（仪表盘头部汇总与统计卡使用）
  wish_users: [
    { id: '10000001', name: '影迷甲', avatar: 'https://img2.doubanio.com/icon/u10000001-1.jpg', count: 2 },
    { id: '10000002', name: '影迷乙', avatar: 'https://img2.doubanio.com/icon/u10000002-1.jpg', count: 2 },
  ],
  observe_queue: [mkItem(2, '赛博朋克：边缘行者 第二季', '2026', 'observing'), mkItem(2, '无职转生 第三季', '2026', 'observing')],
  blacklist_hits: [mkItem(3, '终极名单 第二季', '2026', 'blacklisted')],
  stats: { total_subscribed: 6, month_new: 6, wish_total: 3, rank_total: 4, per_rank: { tv_global: 2, tv_real_time: 1, bangumi: 1 }, blacklist_hits: 1, observing: 2, removed_count: 1 },
  run_state: { subscribed_total: 5, last_rank_run: '2026-09-28 08:00:00' },
  message: 'ok',
}

const Preview = defineComponent({
  setup: () => () => h(NConfigProvider, null, {
    default: () => h(NMessageProvider, null, {
      default: () => h(NNotificationProvider, null, {
        default: () => h(NDialogProvider, null, {
          default: () => h(AppPage, {
            api: previewBridge,
            hostApi: previewBridge,
            installationId: 1,
            pluginId: 'local.douban115',
            runtime: { health_status: 'healthy', process_state: 'running' },
            runtimeState: previewState,
            navKey: 'main',
            themeContract: 'dian115-theme-v1',
          }),
        }),
      }),
    }),
  }),
})

createApp(Preview).mount('#app')
