<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { NButton, NEmpty, NIcon, NPopconfirm, NSpin, NTag, useMessage } from 'naive-ui'
import { RefreshCw, Trash2 } from '@lucide/vue'

interface HostBridge {
  getState(view?: string): Promise<any>
  invokeAction(action: string, input?: unknown): Promise<any>
  refresh(): Promise<Record<string, unknown>>
}

const props = defineProps<{ api: HostBridge }>()

interface SnapshotItem {
  rank: number
  title: string
  year?: string
  douban_id?: string
  tmdb_id?: number
	media_type: string
	/** TMDB 封面地址（https://image.tmdb.org/...） */
	poster?: string
	link?: string
  status: string
  reason?: string
}

interface RankDash {
  key: string
  name: string
  media_type: string
  enabled: boolean
  fetched_at?: string
  items: SnapshotItem[]
}

interface HistoryEntry {
  title: string
  year?: string
  media_type: string
  season?: number
  tmdb_id?: number
  poster?: string
  link?: string
  source: string
  source_key: string
  users?: string[]
  subscribed_at: string
  existing: boolean
  removed?: boolean
}

/** 想看订阅来源的豆瓣用户（昵称/头像由运行时抓取缓存，ID 始终可用） */
interface DoubanUser {
  id: string
  name?: string
  avatar?: string
  /** 该用户来源的想看订阅条数（仅仪表盘返回） */
  count?: number
}

interface DashData {
  generated_at?: string
  ranks?: RankDash[]
  rank_history?: HistoryEntry[]
  wish_history?: HistoryEntry[]
  wish_users?: DoubanUser[]
  observe_queue?: SnapshotItem[]
  blacklist_hits?: SnapshotItem[]
  stats?: Record<string, any>
  run_state?: Record<string, any>
}

const message = useMessage()
const loading = ref(false)
const dash = ref<DashData | null>(null)
const brokenPosters = ref<Set<string>>(new Set())
const clearing = ref('')
// 榜单快照固定只展示前 TOP_LIMIT 名（需与运行时 config.go 的 rankDisplayLimit 保持一致）
const TOP_LIMIT = 5

async function load(retry = true) {
  loading.value = true
  try {
    const res = await props.api.invokeAction('dashboard')
    dash.value = (res?.result || {}) as DashData
  } catch {
    // 组件挂载时宿主桥偶发未就绪，短暂等待后重试一次
    if (retry) {
      await new Promise((r) => setTimeout(r, 2000))
      loading.value = false
      return load(false)
    }
    dash.value = null
  } finally {
    loading.value = false
  }
}

onMounted(() => load())
function reload() { return load() }
defineExpose({ reload })

const ranks = computed(() => dash.value?.ranks || [])
const rankHistory = computed(() => dash.value?.rank_history || [])
const wishHistory = computed(() => dash.value?.wish_history || [])
const observeQueue = computed(() => dash.value?.observe_queue || [])
const blacklistHits = computed(() => dash.value?.blacklist_hits || [])
const stats = computed(() => dash.value?.stats || {})
const perRank = computed(() => (stats.value.per_rank as Record<string, number>) || {})
const wishUsers = computed<DoubanUser[]>(() => dash.value?.wish_users || [])

/** 豆瓣 ID → 用户信息（昵称/头像） */
const userMap = computed(() => {
  const m = new Map<string, DoubanUser>()
  for (const u of wishUsers.value) if (u?.id) m.set(u.id, u)
  return m
})

function userName(id: string): string {
  return userMap.value.get(id)?.name || id
}

function userDisplay(id: string): string {
  const name = userMap.value.get(id)?.name
  return name ? `${name}（${id}）` : id
}

function userAvatar(id: string): string {
  return userMap.value.get(id)?.avatar || ''
}

/** 每位用户的想看订阅条数（用于「想看订阅」区块头部汇总） */
const wishUserStats = computed(() =>
  wishUsers.value.map((u) => ({ id: u.id, name: userName(u.id), avatar: userAvatar(u.id), count: u.count || 0 })),
)

function hideAvatar(evt: Event) {
  ;(evt.target as HTMLImageElement).style.display = 'none'
}

/** 榜单快照只展示前 TOP_LIMIT 项 */
function visibleItems(rd: RankDash): SnapshotItem[] {
  return rd.items.slice(0, TOP_LIMIT)
}

async function clearHistory(scope: 'rank' | 'wish') {
  clearing.value = scope
  try {
    const res = await props.api.invokeAction('clear-history', { scope })
    const result = res?.result || {}
    if (result.status === 'failed') throw new Error(String(result.message || '清空失败'))
    message.success(String(result.message || '订阅历史已清空'))
    await load(false)
    try { await props.api.refresh() } catch { /* 忽略刷新失败 */ }
  } catch (error: any) {
    message.error(String(error?.message || '清空失败'))
  } finally {
    clearing.value = ''
  }
}

// 每个榜单的主题色（对齐参考图的多彩标签风格）
const RANK_COLORS: Record<string, string> = {
  coming: '#f59e0b',
  tv_real_time: '#14b8a6',
  tv_chinese: '#eab308',
  tv_global: '#8b5cf6',
  movie_weekly: '#ec4899',
  bangumi: '#3b82f6',
  wish: '#22c55e',
}

function rankColor(key: string): string {
  return RANK_COLORS[key] || '#8b5cf6'
}

const STATUS_TEXT: Record<string, string> = {
  subscribed: '已订阅',
  existing: '已存在',
  observing: '观察中',
  blacklisted: '黑名单',
  filtered: '已过滤',
  unresolved: 'TMDB 未匹配',
  removed: '已删除',
  beyond: '超出订阅数量',
}

function statusType(s: string): 'success' | 'info' | 'warning' | 'error' | 'default' {
  switch (s) {
    case 'subscribed': return 'success'
    case 'observing': return 'info'
    case 'filtered': return 'warning'
    case 'blacklisted': return 'error'
    case 'removed': return 'warning'
    case 'beyond': return 'info'
    default: return 'default'
  }
}

function statusText(s: string): string {
  return STATUS_TEXT[s] || s
}

function historyStatusType(e: HistoryEntry): 'success' | 'default' | 'warning' {
  if (e.removed) return 'warning'
  return e.existing ? 'default' : 'success'
}

function historyStatusText(e: HistoryEntry): string {
  if (e.removed) return '已删除·不再重订'
  return e.existing ? '已存在' : '订阅成功'
}

/** 想看订阅的来源用户标签：优先显示昵称，昵称未抓到时退回豆瓣 ID。 */
function userLabel(users?: string[]): string {
  const list = (users || []).filter(Boolean)
  if (list.length === 0) return ''
  if (list.length === 1) return `想看 · ${userName(list[0])}`
  return `想看 · ${userName(list[0])} 等 ${list.length} 人`
}

/** 鼠标悬浮时展示「昵称（ID）」，方便核对是哪个账号 */
function userTitle(users?: string[]): string {
  const list = (users || []).filter(Boolean)
  if (list.length === 0) return ''
  return `来源豆瓣用户：${list.map((id) => userDisplay(id)).join('、')}`
}

function posterKey(poster?: string, title?: string): string {
  return `${poster || ''}|${title || ''}`
}

function showPoster(item: { poster?: string; title: string }): boolean {
  return !!item.poster && !brokenPosters.value.has(posterKey(item.poster, item.title))
}

function onPosterError(item: { poster?: string; title: string }) {
  const next = new Set(brokenPosters.value)
  next.add(posterKey(item.poster, item.title))
  brokenPosters.value = next
}

function openLink(link?: string) {
  if (link) window.open(link, '_blank', 'noopener')
}

function shortDate(s?: string): string {
  return (s || '').slice(0, 10)
}
</script>

<template>
  <div class="dash">
    <div class="dash-toolbar">
      <span class="dash-time">数据生成于 {{ dash?.generated_at || '—' }}</span>
      <NButton size="small" :loading="loading" @click="reload">
        <template #icon><NIcon :component="RefreshCw" /></template>刷新
      </NButton>
    </div>

    <NSpin :show="loading && !dash">
      <!-- 1. 榜单快照 -->
      <section class="dash-section">
        <div class="section-head">
          <span class="section-index">1</span>
          <h3>榜单快照</h3>
          <span class="section-sub">最近一次榜单同步的识别与订阅状态，每个榜单显示前 {{ TOP_LIMIT }} 项（封面来自 TMDB）</span>
        </div>
        <div v-if="ranks.every((r) => r.items.length === 0)" class="dash-empty">
          <NEmpty description="暂无榜单数据，请先在「设置」中启用榜单并运行一次榜单订阅" />
        </div>
        <div v-else class="rank-grid">
          <div v-for="rd in ranks" :key="rd.key" class="rank-col">
            <div class="rank-col-head" :style="{ borderColor: rankColor(rd.key) }">
              <span class="rank-col-name" :style="{ color: rankColor(rd.key) }">{{ rd.name }}</span>
              <NTag size="tiny" :bordered="false">{{ rd.items.length }}</NTag>
            </div>
            <div v-if="rd.items.length === 0" class="rank-col-empty">未启用或未运行</div>
            <div v-for="it in visibleItems(rd)" :key="rd.key + '-' + it.rank + '-' + it.title" class="snap-item"
              :class="{ clickable: !!it.link }" @click="openLink(it.link)">
              <div class="poster">
                <img v-if="showPoster(it)" :src="it.poster" :alt="it.title" loading="lazy"
                  referrerpolicy="no-referrer" @error="onPosterError(it)" />
                <div v-else class="poster-fallback">{{ it.title.slice(0, 1) }}</div>
              </div>
              <div class="snap-info">
                <div class="snap-title" :title="it.title">{{ it.title }}</div>
                <div class="snap-meta">
                  <span v-if="it.year">{{ it.year }}</span>
                  <NTag size="tiny" :type="statusType(it.status)" :bordered="false">{{ statusText(it.status) }}</NTag>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- 2. 黑名单拦截 / 观察队列 -->
      <div class="dash-duo">
        <section class="dash-section half">
          <div class="section-head">
            <span class="section-index">2</span>
            <h3>黑名单拦截</h3>
            <span class="section-sub">最近快照共 {{ blacklistHits.length }} 条</span>
          </div>
          <div v-if="blacklistHits.length === 0" class="dash-empty small">
            <NEmpty description="暂无被黑名单过滤的条目" />
          </div>
          <div v-for="(it, i) in blacklistHits" :key="'bl-' + i" class="mini-item">
            <span class="mini-title">{{ it.title }}</span>
            <NTag size="tiny" type="error" :bordered="false">黑名单</NTag>
          </div>
        </section>

        <section class="dash-section half">
          <div class="section-head">
            <span class="section-index">3</span>
            <h3>观察队列</h3>
            <span class="section-sub">待观察期结束自动订阅，共 {{ observeQueue.length }} 条</span>
          </div>
          <div v-if="observeQueue.length === 0" class="dash-empty small">
            <NEmpty description="暂无观察期条目" />
          </div>
          <div v-for="(it, i) in observeQueue" :key="'ob-' + i" class="mini-item">
            <span class="mini-title">{{ it.title }}</span>
            <NTag size="tiny" type="info" :bordered="false">观察中</NTag>
          </div>
        </section>
      </div>

      <!-- 4. 订阅历史（榜单订阅 / 想看订阅 分开） -->
      <section class="dash-section">
        <div class="section-head">
          <span class="section-index">4</span>
          <h3>订阅历史</h3>
          <span class="section-sub">
            榜单订阅 {{ stats.rank_total || 0 }} 条 · 想看订阅 {{ stats.wish_total || 0 }} 条<template
              v-if="stats.removed_count"> · 已删除 {{ stats.removed_count }} 条（不再自动重订）</template>
          </span>
        </div>

        <div class="history-block">
          <div class="history-head">
            <span class="history-label">榜单订阅</span>
            <NTag size="tiny" :bordered="false">{{ rankHistory.length }}</NTag>
            <span class="history-head-spacer" />
            <NPopconfirm @positive-click="clearHistory('rank')" positive-text="确认清空" negative-text="取消">
              <template #trigger>
                <NButton size="tiny" secondary type="error" :loading="clearing === 'rank'">
                  <template #icon><NIcon :component="Trash2" /></template>清空历史
                </NButton>
              </template>
              清空榜单订阅历史后，插件下一轮会重新评估榜单条目；<br />
              被你删除过的订阅可能会被重新订阅。确定清空吗？
            </NPopconfirm>
          </div>
          <div v-if="rankHistory.length === 0" class="dash-empty small">
            <NEmpty description="暂无榜单订阅记录" />
          </div>
          <div v-for="(e, i) in rankHistory" :key="'rh-' + i" class="history-item" :class="{ clickable: !!e.link }"
            @click="openLink(e.link)">
            <div class="poster small">
              <img v-if="showPoster(e)" :src="e.poster" :alt="e.title" loading="lazy" referrerpolicy="no-referrer"
                @error="onPosterError(e)" />
              <div v-else class="poster-fallback">{{ e.title.slice(0, 1) }}</div>
            </div>
            <div class="history-info">
              <div class="history-title">{{ e.title }}<span v-if="e.year" class="history-year">{{ e.year }}</span></div>
              <div class="history-meta">
                <span class="source-tag" :style="{ background: rankColor(e.source_key) + '1a', color: rankColor(e.source_key) }">
                  {{ e.source }}
                </span>
                <span class="history-date">{{ shortDate(e.subscribed_at) || '—' }}</span>
              </div>
            </div>
            <NTag size="small" :type="historyStatusType(e)" :bordered="false" class="history-status">
              {{ historyStatusText(e) }}
            </NTag>
          </div>
        </div>

        <div class="history-block">
          <div class="history-head">
            <span class="history-label">想看订阅</span>
            <NTag size="tiny" :bordered="false">{{ wishHistory.length }}</NTag>
            <div v-if="wishUserStats.length" class="user-summary">
              <span v-for="u in wishUserStats" :key="'wu-' + u.id" class="user-chip" :title="`豆瓣用户：${u.name}（${u.id}）`">
                <img v-if="u.avatar" class="user-avatar" :src="u.avatar" :alt="u.name" loading="lazy"
                  referrerpolicy="origin" @error="hideAvatar" />
                <span class="user-chip-name">{{ u.name }}</span>
                <span class="user-chip-count">{{ u.count }} 条</span>
              </span>
            </div>
            <span class="history-head-spacer" />
            <NPopconfirm @positive-click="clearHistory('wish')" positive-text="确认清空" negative-text="取消">
              <template #trigger>
                <NButton size="tiny" secondary type="error" :loading="clearing === 'wish'">
                  <template #icon><NIcon :component="Trash2" /></template>清空历史
                </NButton>
              </template>
              清空想看订阅历史后，插件下一轮会重新评估「想看」列表；<br />
              被你删除过的订阅可能会被重新订阅。确定清空吗？
            </NPopconfirm>
          </div>
          <div v-if="wishHistory.length === 0" class="dash-empty small">
            <NEmpty description="暂无想看订阅记录" />
          </div>
          <div v-for="(e, i) in wishHistory" :key="'wh-' + i" class="history-item" :class="{ clickable: !!e.link }"
            @click="openLink(e.link)">
            <div class="poster small">
              <img v-if="showPoster(e)" :src="e.poster" :alt="e.title" loading="lazy" referrerpolicy="no-referrer"
                @error="onPosterError(e)" />
              <div v-else class="poster-fallback">{{ e.title.slice(0, 1) }}</div>
            </div>
            <div class="history-info">
              <div class="history-title">{{ e.title }}<span v-if="e.year" class="history-year">{{ e.year }}</span></div>
              <div class="history-meta">
                <span class="source-tag" :style="{ background: rankColor('wish') + '1a', color: rankColor('wish') }">
                  {{ e.source }}
                </span>
                <span v-if="(e.users || []).length" class="user-tag" :title="userTitle(e.users)">
                  {{ userLabel(e.users) }}
                </span>
                <span class="history-date">{{ shortDate(e.subscribed_at) || '—' }}</span>
              </div>
            </div>
            <NTag size="small" :type="historyStatusType(e)" :bordered="false" class="history-status">
              {{ historyStatusText(e) }}
            </NTag>
          </div>
        </div>
      </section>

      <!-- 5. 订阅统计 -->
      <section class="dash-section">
        <div class="section-head">
          <span class="section-index">5</span>
          <h3>订阅统计</h3>
        </div>
        <div class="stats-grid">
          <div class="stat-card">
            <span class="stat-num accent">{{ stats.total_subscribed || 0 }}</span>
            <span class="stat-label">总订阅数</span>
          </div>
          <div class="stat-card">
            <span class="stat-num accent">{{ stats.month_new || 0 }}</span>
            <span class="stat-label">本月新增</span>
          </div>
          <div v-if="stats.removed_count" class="stat-card">
            <span class="stat-num removed">{{ stats.removed_count }}</span>
            <span class="stat-label">已删除不重订</span>
          </div>
          <div v-for="rd in ranks" :key="'st-' + rd.key" class="stat-card">
            <span class="stat-num" :style="{ color: rankColor(rd.key) }">{{ perRank[rd.key] || 0 }}</span>
            <span class="stat-label">{{ rd.name }}</span>
          </div>
          <div class="stat-card">
            <span class="stat-num" :style="{ color: rankColor('wish') }">{{ stats.wish_total || 0 }}</span>
            <span class="stat-label">豆瓣想看</span>
          </div>
          <div v-for="u in wishUserStats" :key="'st-wu-' + u.id" class="stat-card">
            <span class="stat-num" :style="{ color: rankColor('wish') }">{{ u.count }}</span>
            <span class="stat-label" :title="`豆瓣用户 ID：${u.id}`">{{ u.name }}</span>
          </div>
        </div>
      </section>
    </NSpin>
  </div>
</template>

<style scoped>
.dash {
  display: grid;
  gap: var(--dian-space-4);
}

.dash-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--dian-space-3);
}

.dash-time {
  color: var(--dian-text-muted);
  font-size: 12px;
}

.dash-section {
  border: 1px solid var(--dian-border);
  border-radius: var(--dian-radius-md);
  padding: var(--dian-space-4);
  background: var(--dian-surface-soft);
}

.section-head {
  display: flex;
  align-items: baseline;
  gap: var(--dian-space-2);
  margin-bottom: var(--dian-space-3);
}

.section-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 6px;
  background: var(--dian-accent, #8b5cf6);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  flex: none;
  transform: translateY(2px);
}

.section-head h3 {
  margin: 0;
  font-size: 15px;
  color: var(--dian-text-primary);
}

.section-sub {
  color: var(--dian-text-muted);
  font-size: 12px;
}

.dash-empty {
  padding: var(--dian-space-4) 0;
}

.dash-empty.small {
  padding: var(--dian-space-2) 0;
}

.dash-duo {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--dian-space-4);
}

@media (max-width: 800px) {
  .dash-duo {
    grid-template-columns: 1fr;
  }
}

/* 榜单快照 */
.rank-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: var(--dian-space-3);
}

.rank-col {
  border: 1px solid var(--dian-border);
  border-radius: var(--dian-radius-md);
  background: var(--dian-surface-raised);
  padding: var(--dian-space-2);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.rank-col-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--dian-space-1) var(--dian-space-2);
  border-left: 3px solid transparent;
  margin-bottom: var(--dian-space-1);
}

.rank-col-name {
  font-weight: 700;
  font-size: 13px;
}

.rank-col-empty {
  color: var(--dian-text-muted);
  font-size: 12px;
  text-align: center;
  padding: var(--dian-space-3) 0;
}

.snap-item {
  display: flex;
  gap: var(--dian-space-2);
  align-items: center;
  padding: 4px var(--dian-space-2);
  border-radius: var(--dian-radius-sm);
}

.snap-item.clickable {
  cursor: pointer;
}

.snap-item.clickable:hover {
  background: var(--dian-surface-soft);
}

.poster {
  width: 34px;
  height: 50px;
  border-radius: 4px;
  overflow: hidden;
  flex: none;
  background: var(--dian-surface-soft);
}

.poster.small {
  width: 40px;
  height: 58px;
}

.poster img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.poster-fallback {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--dian-text-muted);
  font-size: 14px;
  font-weight: 700;
  background: var(--dian-surface-soft);
}

.snap-info {
  min-width: 0;
  flex: 1;
}

.snap-title {
  font-size: 12.5px;
  color: var(--dian-text-primary);
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.snap-meta {
  display: flex;
  align-items: center;
  gap: var(--dian-space-2);
  color: var(--dian-text-muted);
  font-size: 11px;
  margin-top: 2px;
}

/* 黑名/观察 */
.mini-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--dian-space-2);
  padding: 6px var(--dian-space-2);
  border-radius: var(--dian-radius-sm);
}

.mini-item:nth-child(odd) {
  background: var(--dian-surface-raised);
}

.mini-title {
  font-size: 13px;
  color: var(--dian-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 订阅历史 */
.history-block + .history-block {
  margin-top: var(--dian-space-4);
  padding-top: var(--dian-space-3);
  border-top: 1px dashed var(--dian-border);
}

.history-head {
  display: flex;
  align-items: center;
  gap: var(--dian-space-2);
  margin-bottom: var(--dian-space-2);
}

.history-head-spacer {
  flex: 1;
}

.history-label {
  font-weight: 600;
  font-size: 13px;
  color: var(--dian-text-secondary);
}

.history-item {
  display: flex;
  align-items: center;
  gap: var(--dian-space-3);
  padding: var(--dian-space-2);
  border-radius: var(--dian-radius-sm);
}

.history-item.clickable {
  cursor: pointer;
}

.history-item.clickable:hover {
  background: var(--dian-surface-raised);
}

.history-info {
  flex: 1;
  min-width: 0;
}

.history-title {
  font-size: 14px;
  color: var(--dian-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-year {
  color: var(--dian-text-muted);
  font-size: 12px;
  margin-left: 6px;
}

.history-meta {
  display: flex;
  align-items: center;
  gap: var(--dian-space-2);
  margin-top: 3px;
}

.source-tag {
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 999px;
  font-weight: 600;
}

.history-date {
  color: var(--dian-text-muted);
  font-size: 12px;
}

/* 想看订阅来源用户标签 */
.user-tag {
  font-size: 11px;
  padding: 1px 7px;
  border-radius: 999px;
  background: var(--dian-surface-soft);
  color: var(--dian-text-secondary);
  white-space: nowrap;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 「想看订阅」头部的每位用户汇总 */
.user-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-left: 2px;
}

.user-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 1px 9px 1px 3px;
  border: 1px solid var(--dian-border);
  border-radius: 999px;
  background: var(--dian-surface-raised);
  font-size: 11px;
  color: var(--dian-text-secondary);
  max-width: 200px;
}

.user-chip-name {
  font-weight: 600;
  color: var(--dian-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-chip-count {
  color: var(--dian-text-muted);
  flex: none;
}

.user-avatar {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  object-fit: cover;
  flex: none;
}

.history-status {
  flex: none;
}

/* 统计 */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
  gap: var(--dian-space-3);
}

.stat-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  border: 1px solid var(--dian-border);
  border-radius: var(--dian-radius-md);
  padding: var(--dian-space-3) var(--dian-space-2);
  background: var(--dian-surface-raised);
}

.stat-num {
  font-size: 22px;
  font-weight: 800;
  color: var(--dian-text-primary);
}

.stat-num.accent {
  color: var(--dian-accent, #8b5cf6);
}

.stat-num.removed {
  color: var(--dian-text-muted);
}

.stat-label {
  font-size: 12px;
  color: var(--dian-text-muted);
}
</style>
