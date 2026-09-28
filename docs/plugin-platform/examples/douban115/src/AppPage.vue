<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import {
  NAlert,
  NButton,
  NCollapse,
  NCollapseItem,
  NDivider,
  NEmpty,
  NForm,
  NFormItem,
  NIcon,
  NInput,
  NInputNumber,
  NSelect,
  NSpace,
  NSwitch,
  NTag,
  useMessage,
} from 'naive-ui'
import {
  BookMarked,
  Clapperboard,
  CloudDownload,
  Eye,
  LayoutDashboard,
  MonitorPlay,
  Play,
  Save,
  Settings,
  Tv,
} from '@lucide/vue'
import DashboardPanel from './DashboardPanel.vue'

interface HostBridge {
  getState(view?: string): Promise<any>
  invokeAction(action: string, input?: unknown): Promise<any>
  refresh(): Promise<Record<string, unknown>>
}

const props = defineProps<{
  api: HostBridge
  hostApi?: HostBridge
  installationId?: number
  pluginId?: string
  runtime?: Record<string, unknown> | null
  runtimeState?: Record<string, unknown>
  navKey?: string
  themeContract?: string
}>()

interface RankConfigForm {
  enabled: boolean
  count: number
  min_vote: number
  min_year: number
  regions: string[]
}

interface ConfigForm {
  douban_cookie: string
  douban_user_id: string
  rsshub_domain: string
  cloud_url: string
  cloud_uuid: string
  cloud_passcode: string
  rank_configs: Record<string, RankConfigForm>
  blacklist: string
  observe_days: number
  rank_cron: string
  wish_cron: string
  emby_cron: string
  wish_enabled: boolean
  wish_days: number
  wish_max_pages: number
  emby_enabled: boolean
  emby_url: string
  emby_api_key: string
  emby_user_id: string
  emby_mark_do: boolean
  emby_mark_collect: boolean
  notify: boolean
}

interface RankDef {
  key: string
  name: string
  route: string
  media_type: string
  coming?: boolean
}

const REGION_OPTIONS = [
  '中国大陆', '中国香港', '中国台湾', '美国', '日本', '韩国', '英国', '法国',
  '德国', '泰国', '印度', '俄罗斯', '西班牙', '加拿大', '澳大利亚', '意大利',
].map((label) => ({ label, value: label }))

const message = useMessage()
const busy = ref('')
const asyncMessage = ref('')
const activeView = ref<'dashboard' | 'settings'>('dashboard')
const dashPanel = ref<InstanceType<typeof DashboardPanel> | null>(null)

function defaultRankConfig(): RankConfigForm {
  return { enabled: false, count: 3, min_vote: 0, min_year: 0, regions: [] }
}

function defaultForm(): ConfigForm {
  return {
    douban_cookie: '',
    douban_user_id: '',
    rsshub_domain: 'https://rsshub.ddsrem.com',
    cloud_url: '',
    cloud_uuid: '',
    cloud_passcode: '',
    rank_configs: {},
    blacklist: '',
    observe_days: 0,
    rank_cron: '0 8 * * *',
    wish_cron: '0 */6 * * *',
    emby_cron: '*/30 * * * *',
    wish_enabled: false,
    wish_days: 7,
    wish_max_pages: 3,
    emby_enabled: false,
    emby_url: '',
    emby_api_key: '',
    emby_user_id: '',
    emby_mark_do: true,
    emby_mark_collect: true,
    notify: false,
  }
}

const form = reactive<ConfigForm>(defaultForm())
const ranks = ref<RankDef[]>([])
const doubanLoggedIn = ref(false)
const embyApiKeySet = ref(false)
const cloudSyncSet = ref(false)
// 想看订阅使用的豆瓣用户（含昵称，昵称来自上次抓取想看列表时的缓存）
const wishUsers = ref<{ id: string; name?: string; avatar?: string }[]>([])

const state = computed(() => props.runtimeState || {})

function applyState() {
  const s = state.value as any
  const cfg = s.config || {}
  Object.assign(form, defaultForm())
  if (cfg.douban_cookie !== undefined) form.douban_cookie = cfg.douban_cookie || ''
  if (cfg.douban_user_id !== undefined) form.douban_user_id = cfg.douban_user_id || ''
  if (cfg.rsshub_domain !== undefined) form.rsshub_domain = cfg.rsshub_domain || 'https://rsshub.ddsrem.com'
  if (cfg.cloud_url !== undefined) form.cloud_url = cfg.cloud_url || ''
  if (cfg.cloud_uuid !== undefined) form.cloud_uuid = cfg.cloud_uuid || ''
  if (cfg.blacklist !== undefined) form.blacklist = cfg.blacklist || ''
  if (cfg.observe_days !== undefined) form.observe_days = Number(cfg.observe_days) || 0
  if (cfg.rank_cron !== undefined) form.rank_cron = cfg.rank_cron || '0 8 * * *'
  if (cfg.wish_cron !== undefined) form.wish_cron = cfg.wish_cron || '0 */6 * * *'
  if (cfg.emby_cron !== undefined) form.emby_cron = cfg.emby_cron || '*/30 * * * *'
  if (cfg.wish_enabled !== undefined) form.wish_enabled = !!cfg.wish_enabled
  if (cfg.wish_days !== undefined) form.wish_days = Number(cfg.wish_days) || 7
  if (cfg.wish_max_pages !== undefined) form.wish_max_pages = Number(cfg.wish_max_pages) || 3
  if (cfg.emby_enabled !== undefined) form.emby_enabled = !!cfg.emby_enabled
  if (cfg.emby_url !== undefined) form.emby_url = cfg.emby_url || ''
  if (cfg.emby_api_key !== undefined) form.emby_api_key = cfg.emby_api_key || ''
  if (cfg.emby_user_id !== undefined) form.emby_user_id = cfg.emby_user_id || ''
  if (cfg.emby_mark_do !== undefined) form.emby_mark_do = !!cfg.emby_mark_do
  if (cfg.emby_mark_collect !== undefined) form.emby_mark_collect = !!cfg.emby_mark_collect
  if (cfg.notify !== undefined) form.notify = !!cfg.notify
  const rc = cfg.rank_configs || {}
  const merged: Record<string, RankConfigForm> = {}
  for (const rd of (s.ranks || [])) {
    merged[rd.key] = { ...defaultRankConfig(), ...(rc[rd.key] || {}) }
    merged[rd.key].regions = merged[rd.key].regions || []
  }
  form.rank_configs = merged
  ranks.value = s.ranks || []
  doubanLoggedIn.value = !!s.doubanLoggedIn
  embyApiKeySet.value = !!s.embyApiKeySet
  cloudSyncSet.value = !!s.cloudSyncSet
  wishUsers.value = Array.isArray(s.wishUsers) ? s.wishUsers : []
}

watch(() => props.runtimeState, applyState, { immediate: true, deep: true })

async function runAction(action: string, input: Record<string, unknown> = {}, successPrefix = '') {
  busy.value = action
  try {
    const response = await props.api.invokeAction(action, input)
    const result = response.result || {}
    if (result.status === 'failed') throw new Error(String(result.message || '操作失败'))
    // 异步任务：立即返回 accepted，轮询 state 直到完成
    if (result.status === 'accepted') {
      message.info(String(result.message || '任务已开始'))
      await pollTaskDone()
      message.success('任务完成')
      if (activeView.value === 'dashboard') dashPanel.value?.reload()
      else await props.api.refresh()
      return result
    }
    await props.api.refresh()
    message.success(String(result.message || successPrefix + '完成'))
    return result
  } catch (error: any) {
    message.error(String(error?.message || '操作失败'))
  } finally {
    busy.value = ''
  }
}

// 轮询 state 直到 lastStatus 不再是 running（最长 10 分钟）
async function pollTaskDone(timeoutMs = 600000) {
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    await new Promise((r) => setTimeout(r, 3000))
    try {
      const fresh = await props.api.getState('main')
      const s = (fresh?.state || {}) as any
      if (s.lastStatus && s.lastStatus !== 'running') {
        asyncMessage.value = String(s.lastMessage || '')
        return
      }
    } catch { /* 轮询失败忽略，继续 */ }
  }
}

async function saveConfig() {
  await runAction('save-config', { config: JSON.parse(JSON.stringify(form)) }, '配置保存')
}

async function runRanks() { await runAction('run-ranks', {}) }
async function runWish() { await runAction('run-wish', {}) }
async function runEmby() { await runAction('run-emby', {}) }
async function testDouban() { await runAction('test-douban', {}) }

/** 豆瓣头像加载失败时隐藏（昵称仍然显示） */
function hideAvatar(evt: Event) {
  ;(evt.target as HTMLImageElement).style.display = 'none'
}
async function testEmby() { await runAction('test-emby', {}) }
async function syncCookieCloud() {
  // 直接使用表单里刚填写的 CookieCloud 信息，无需先点保存
  const res = await runAction('sync-cookiecloud', {
    cloud_url: form.cloud_url,
    cloud_uuid: form.cloud_uuid,
    cloud_passcode: form.cloud_passcode,
  })
  if (res) {
    form.cloud_passcode = ''
    await refreshConfigOnly()
  }
}

// 同步 Cookie 后只刷新状态，不重置用户正在编辑的表单
async function refreshConfigOnly() {
  try {
    const fresh = await props.api.getState('main')
    const s = (fresh.state || {}) as any
    doubanLoggedIn.value = !!s.doubanLoggedIn
    cloudSyncSet.value = !!s.cloudSyncSet
  } catch { /* 忽略刷新失败 */ }
}

const lastMessage = computed(() => asyncMessage.value || String(state.value.lastMessage || ''))
const lastStatus = computed(() => String(state.value.lastStatus || ''))
const runState = computed(() => (state.value.runState as any) || {})

/* ───────────────────────── 插件沙箱高度自纠 ─────────────────────────
 * 宿主桥接把 iframe 高度取为 max(body.scrollHeight, documentElement.scrollHeight, …)，
 * 而宿主基线 CSS 给 html/body/#plugin-sandbox-root 设了 min-height:100%，且根元素的
 * scrollHeight 永远不会小于视口（= iframe 当前高度）。三者叠加导致 iframe 高度
 * 「只增不减」：内容一旦从高变矮（收起折叠、切回较矮的视图），底部就固化出大片空白。
 *
 * 修复分两层：
 * 1. 在 iframe 环境里给根元素加 douban115-sandbox class，由下方全局样式清掉 min-height，
 *    让 body.scrollHeight 回到真实内容高度；
 * 2. 内容尺寸变化时按宿主的 resize 协议（postMessage，channel 在 iframe URL hash 里）
 *    主动上报组件根的真实高度，把 iframe 高度拉回实际值。桥接自身仍会上报一次
 *    「不低于当前视口」的旧值，因此上报后短促补发两次，确保最终以真实值生效。
 * 本地预览（window.parent === window）不处于沙箱，全部逻辑自动跳过。 */
const pageRoot = ref<HTMLElement | null>(null)
const SANDBOX_SOURCE = 'dian115-plugin-sandbox'
let sandboxRO: ResizeObserver | null = null
let sandboxTimers: number[] = []

function sandboxChannel(): string {
  try {
    return decodeURIComponent(String(window.location.hash.slice(1)).trim())
  } catch {
    return ''
  }
}

function reportSandboxHeight(retries = 2) {
  if (window.parent === window) return
  const channel = sandboxChannel()
  const el = pageRoot.value
  if (!channel || !el) return
  const height = Math.min(100000, Math.max(320, Math.ceil(el.getBoundingClientRect().height)))
  try {
    window.parent.postMessage({ source: SANDBOX_SOURCE, channel, type: 'resize', height }, '*')
  } catch { /* postMessage 失败忽略，下轮重试 */ }
  if (retries > 0) {
    sandboxTimers.push(window.setTimeout(() => reportSandboxHeight(retries - 1), 120))
  }
}

function onSandboxWinResize() {
  reportSandboxHeight()
}

onMounted(() => {
  if (window.parent === window || !sandboxChannel()) return
  // 沙箱环境：清掉宿主基线的 min-height:100%，否则 body.scrollHeight 被钉在视口高度
  document.documentElement.classList.add('douban115-sandbox')
  sandboxRO = new ResizeObserver(() => reportSandboxHeight())
  if (pageRoot.value) sandboxRO.observe(pageRoot.value)
  window.addEventListener('resize', onSandboxWinResize)
  nextTick(() => reportSandboxHeight(4))
})

onBeforeUnmount(() => {
  sandboxRO?.disconnect()
  sandboxRO = null
  window.removeEventListener('resize', onSandboxWinResize)
  sandboxTimers.forEach((t) => clearTimeout(t))
  sandboxTimers = []
})
</script>

<template>
  <main ref="pageRoot" class="dian-plugin-page douban-page">
    <header class="page-header">
      <div>
        <h2>豆瓣订阅中心</h2>
        <p>榜单 / 想看自动订阅，Emby 观影记录同步到豆瓣。</p>
      </div>
      <div class="view-switch">
        <button class="view-btn" :class="{ active: activeView === 'dashboard' }" @click="activeView = 'dashboard'">
          <NIcon :component="LayoutDashboard" :size="15" /> 仪表盘
        </button>
        <button class="view-btn" :class="{ active: activeView === 'settings' }" @click="activeView = 'settings'">
          <NIcon :component="Settings" :size="15" /> 设置
        </button>
      </div>
    </header>

    <NAlert v-if="lastMessage" :type="lastStatus === 'failed' ? 'error' : 'info'" :bordered="false" class="status-alert">
      <pre class="status-pre">{{ lastMessage }}</pre>
    </NAlert>

    <DashboardPanel v-show="activeView === 'dashboard'" ref="dashPanel" :api="props.api" />

    <template v-if="activeView === 'settings'">
    <section class="actions">
      <NButton type="primary" :loading="busy === 'save-config'" @click="saveConfig">
        <template #icon><NIcon :component="Save" /></template>保存配置
      </NButton>
      <NButton :loading="busy === 'run-ranks'" @click="runRanks">
        <template #icon><NIcon :component="Clapperboard" /></template>立即运行榜单
      </NButton>
      <NButton :loading="busy === 'run-wish'" @click="runWish">
        <template #icon><NIcon :component="BookMarked" /></template>立即运行想看
      </NButton>
      <NButton :loading="busy === 'run-emby'" @click="runEmby">
        <template #icon><NIcon :component="MonitorPlay" /></template>立即同步 Emby
      </NButton>
    </section>

    <NCollapse :default-expanded-names="['general']">
      <NCollapseItem title="通用设置" name="general">
        <template #header-extra><NIcon :component="Settings" /></template>
        <NForm label-placement="top">
          <NFormItem label="豆瓣 Cookie（留空保持不变；可用下方 CookieCloud 自动同步）">
            <NInput v-model:value="form.douban_cookie" type="password" show-password-on="click"
              :placeholder="doubanLoggedIn ? '已配置，留空保持不变' : '粘贴豆瓣 Cookie（需包含 dbcl2）'" clearable />
          </NFormItem>
          <div class="cloud-box">
            <p class="hint">
              CookieCloud 同步：填入 CookieCloud 服务器地址与 UUID、密码，一键拉取浏览器扩展已同步的豆瓣 Cookie，
              无需手动复制。使用 dian115 内置的 CookieCloud 时，地址一般形如
              <code>http://127.0.0.1:8095/cookiecloud</code>；也可以填独立的 CookieCloud Server 地址。
              同步在后台执行（拉取的数据量较大，通常需要几秒到几十秒），点击后请稍候，结果会自动显示在上方状态栏。
            </p>
            <div class="row">
              <NFormItem label="CookieCloud 服务器地址">
                <NInput v-model:value="form.cloud_url" placeholder="例如 http://127.0.0.1:8095/cookiecloud" clearable />
              </NFormItem>
              <NFormItem label="UUID">
                <NInput v-model:value="form.cloud_uuid" placeholder="CookieCloud UUID" clearable />
              </NFormItem>
              <NFormItem label="密码（留空保持不变）">
                <NInput v-model:value="form.cloud_passcode" type="password" show-password-on="click"
                  :placeholder="cloudSyncSet ? '已配置，留空保持不变' : 'CookieCloud 端对端加密密码'" clearable />
              </NFormItem>
            </div>
            <NSpace>
              <NButton size="small" type="primary" secondary :loading="busy === 'sync-cookiecloud'"
                @click="syncCookieCloud">从 CookieCloud 同步豆瓣 Cookie</NButton>
            </NSpace>
          </div>
          <NFormItem label="豆瓣用户 ID（支持多个，逗号分隔）">
            <NInput v-model:value="form.douban_user_id" type="textarea" :rows="2"
              placeholder="留空时从 Cookie 自动解析，也可直接粘贴个人主页链接" clearable />
          </NFormItem>
          <div class="hint">想看订阅会逐个读取这些用户的「想看」列表并合并去重：同一部片只订阅一次；豆瓣用户 ID 可在个人主页地址 douban.com/people/<b>ID</b>/ 中找到</div>
          <div v-if="wishUsers.length" class="wish-users">
            <span class="wish-users-label">已识别用户</span>
            <span v-for="u in wishUsers" :key="'wu-' + u.id" class="user-chip" :title="`豆瓣用户 ID：${u.id}`">
              <img v-if="u.avatar" class="user-avatar" :src="u.avatar" :alt="u.name || u.id" loading="lazy"
                referrerpolicy="origin" @error="hideAvatar" />
              <span class="user-chip-name">{{ u.name || u.id }}</span>
              <span v-if="u.name" class="user-chip-id">{{ u.id }}</span>
            </span>
          </div>
          <div v-else-if="form.douban_user_id" class="hint">昵称会在下次同步「想看」或点击下方「测试豆瓣连接」后显示</div>
          <NFormItem label="RSSHub 域名">
            <NInput v-model:value="form.rsshub_domain" placeholder="https://rsshub.ddsrem.com" clearable />
          </NFormItem>
          <NFormItem label="黑名单关键词（每行一个，支持 regex: 前缀）">
            <NInput v-model:value="form.blacklist" type="textarea" :rows="3" placeholder="例如：纪录片&#10;综艺" />
          </NFormItem>
          <div class="row">
            <NFormItem label="观察期天数（0 关闭）">
              <NInputNumber v-model:value="form.observe_days" :min="0" :max="30" />
            </NFormItem>
            <NFormItem label="结果通知">
              <NSwitch v-model:value="form.notify" />
            </NFormItem>
          </div>
          <NSpace>
            <NButton size="small" :loading="busy === 'test-douban'" @click="testDouban">测试豆瓣连接</NButton>
          </NSpace>
        </NForm>
      </NCollapseItem>

      <NCollapseItem title="榜单订阅" name="rank">
        <template #header-extra><NIcon :component="Tv" /></template>
        <p class="hint">启用后，插件会按 Cron 周期把豆瓣榜单条目加入 dian115 订阅（自动追更）。Cron 为 5 个数字字段：分 时 日 月 周。</p>
        <NForm label-placement="top">
          <NFormItem label="同步间隔（Cron 表达式）">
            <NInput v-model:value="form.rank_cron" placeholder="0 8 * * *（每天 8 点）" clearable />
          </NFormItem>
        </NForm>
        <div v-if="ranks.length === 0" class="empty"><NEmpty description="暂无榜单配置" /></div>
        <div v-for="rd in ranks" :key="rd.key" class="rank-card">
          <div class="rank-head">
            <div>
              <div class="rank-title">
                {{ rd.name }}
                <NTag size="small" :type="rd.media_type === 'movie' ? 'warning' : 'info'">
                  {{ rd.media_type === 'movie' ? '电影' : '剧集' }}
                </NTag>
                <NTag v-if="rd.coming" size="small" type="success">即将上映</NTag>
              </div>
              <div class="rank-sub">{{ rd.route }}</div>
            </div>
            <NSwitch v-model:value="form.rank_configs[rd.key].enabled" />
          </div>
          <div v-if="form.rank_configs[rd.key].enabled" class="rank-body">
            <NForm label-placement="top">
              <div class="row">
                <NFormItem label="订阅数量（0 不限制）">
                  <NInputNumber v-model:value="form.rank_configs[rd.key].count" :min="0" :max="50" />
                  <div class="hint">只订阅榜单前 N 名（按榜单位置计算）；榜单快照始终拉取完整榜单用于展示，超出数量的条目不会订阅</div>
                </NFormItem>
                <NFormItem label="最低评分">
                  <NInputNumber v-model:value="form.rank_configs[rd.key].min_vote" :min="0" :max="10" :step="0.1" />
                </NFormItem>
                <NFormItem label="最低年份">
                  <NInputNumber v-model:value="form.rank_configs[rd.key].min_year" :min="0" :max="2100" />
                </NFormItem>
              </div>
              <NFormItem label="地区筛选（空不限）">
                <NSelect v-model:value="form.rank_configs[rd.key].regions" multiple :options="REGION_OPTIONS"
                  placeholder="选择地区" clearable />
              </NFormItem>
            </NForm>
          </div>
        </div>
      </NCollapseItem>

      <NCollapseItem title="想看订阅" name="wish">
        <template #header-extra><NIcon :component="Eye" /></template>
        <p class="hint">
          读取「豆瓣用户 ID」中配置的用户（支持多个，见上方「豆瓣账号」）的想看列表并自动订阅；多用户时同一部片只订阅一次。
        </p>
        <NForm label-placement="top">
          <div class="row">
            <NFormItem label="启用想看自动订阅">
              <NSwitch v-model:value="form.wish_enabled" />
            </NFormItem>
            <NFormItem label="只看最近 N 天">
              <NInputNumber v-model:value="form.wish_days" :min="1" :max="90" />
            </NFormItem>
            <NFormItem label="翻页数">
              <NInputNumber v-model:value="form.wish_max_pages" :min="1" :max="20" />
            </NFormItem>
          </div>
          <NFormItem label="同步间隔（Cron 表达式）">
            <NInput v-model:value="form.wish_cron" placeholder="0 */6 * * *（每 6 小时）" clearable />
          </NFormItem>
        </NForm>
      </NCollapseItem>

      <NCollapseItem title="Emby 观影同步" name="emby">
        <template #header-extra><NIcon :component="Play" /></template>
        <p class="hint">插件直连 Emby 读取播放记录，并把电影标记「看过」、剧集标记「在看/看过」到豆瓣。</p>
        <NForm label-placement="top">
          <div class="row">
            <NFormItem label="启用 Emby 同步">
              <NSwitch v-model:value="form.emby_enabled" />
            </NFormItem>
            <NFormItem label="标记剧集「在看」">
              <NSwitch v-model:value="form.emby_mark_do" />
            </NFormItem>
            <NFormItem label="标记「看过」">
              <NSwitch v-model:value="form.emby_mark_collect" />
            </NFormItem>
          </div>
          <NFormItem label="Emby 地址">
            <NInput v-model:value="form.emby_url" placeholder="例如 http://192.168.1.10:8096" clearable />
          </NFormItem>
          <NFormItem label="Emby API Key（留空保持不变）">
            <NInput v-model:value="form.emby_api_key" type="password" show-password-on="click"
              :placeholder="embyApiKeySet ? '已配置，留空保持不变' : 'Emby 管理后台生成的 API Key'" clearable />
          </NFormItem>
          <NFormItem label="Emby 用户 ID（可选，留空自动选择）">
            <NInput v-model:value="form.emby_user_id" placeholder="用户 ID" clearable />
          </NFormItem>
          <NFormItem label="同步间隔（Cron 表达式）">
            <NInput v-model:value="form.emby_cron" placeholder="*/30 * * * *（每 30 分钟）" clearable />
          </NFormItem>
          <NSpace>
            <NButton size="small" :loading="busy === 'test-emby'" @click="testEmby">测试 Emby 连接</NButton>
          </NSpace>
        </NForm>
      </NCollapseItem>
    </NCollapse>

    <NDivider />

    <section class="runstate">
      <div class="runstate-item">
        <span class="label">累计订阅</span>
        <span class="value">{{ runState.subscribed_total || 0 }}</span>
      </div>
      <div class="runstate-item">
        <span class="label">上次榜单运行</span>
        <span class="value">{{ runState.last_rank_run || '—' }}</span>
      </div>
      <div class="runstate-item">
        <span class="label">上次想看运行</span>
        <span class="value">{{ runState.last_wish_run || '—' }}</span>
      </div>
      <div class="runstate-item">
        <span class="label">上次 Emby 同步</span>
        <span class="value">{{ runState.last_emby_run || '—' }}</span>
      </div>
    </section>
    </template>
  </main>
</template>

<style scoped>
.douban-page {
  display: grid;
  gap: var(--dian-space-4);
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--dian-space-3);
  border-bottom: 1px solid var(--dian-divider);
  padding-bottom: var(--dian-space-4);
}

.page-header h2 {
  margin: 0;
  color: var(--dian-text-primary);
}

.page-header p {
  margin: var(--dian-space-1) 0 0;
  color: var(--dian-text-secondary);
}

.view-switch {
  display: flex;
  gap: 2px;
  border: 1px solid var(--dian-border);
  border-radius: var(--dian-radius-md);
  padding: 3px;
  background: var(--dian-surface-soft);
}

.view-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: none;
  border-radius: calc(var(--dian-radius-md) - 3px);
  padding: 6px 14px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  background: transparent;
  color: var(--dian-text-secondary);
  transition: background 0.15s ease, color 0.15s ease;
}

.view-btn.active {
  background: var(--dian-accent, #8b5cf6);
  color: #fff;
}

.view-btn:not(.active):hover {
  color: var(--dian-text-primary);
}

.status-alert {
  margin: 0;
}

.status-pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--dian-font-mono);
  font-size: 13px;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--dian-space-3);
}

.hint {
  margin: 0 0 var(--dian-space-3);
  color: var(--dian-text-secondary);
  font-size: 13px;
  line-height: 1.7;
}

.hint code {
  padding: 1px 5px;
  border-radius: 4px;
  background: var(--dian-surface-2, rgba(127, 127, 127, 0.16));
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  word-break: break-all;
}

.cloud-box {
  border: 1px dashed var(--dian-border);
  border-radius: var(--dian-radius-md);
  padding: var(--dian-space-3);
  margin-bottom: var(--dian-space-3);
  background: var(--dian-surface-soft);
}

.row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--dian-space-4);
}

.row > * {
  flex: 1 1 140px;
  min-width: 140px;
}

.rank-card {
  border: 1px solid var(--dian-border);
  border-radius: var(--dian-radius-md);
  padding: var(--dian-space-3);
  margin-bottom: var(--dian-space-3);
  background: var(--dian-surface-soft);
}

.rank-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--dian-space-3);
}

.rank-title {
  display: flex;
  align-items: center;
  gap: var(--dian-space-2);
  font-weight: 600;
  color: var(--dian-text-primary);
}

.rank-sub {
  color: var(--dian-text-muted);
  font-family: var(--dian-font-mono);
  font-size: 12px;
  margin-top: 2px;
}

.rank-body {
  margin-top: var(--dian-space-3);
  padding-top: var(--dian-space-3);
  border-top: 1px dashed var(--dian-border);
}

.empty {
  padding: var(--dian-space-4) 0;
}

.runstate {
  display: flex;
  flex-wrap: wrap;
  gap: var(--dian-space-4);
}

.runstate-item {
  flex: 1 1 180px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  border: 1px solid var(--dian-border);
  border-radius: var(--dian-radius-md);
  padding: var(--dian-space-3);
  background: var(--dian-surface-raised);
}

.runstate-item .label {
  color: var(--dian-text-muted);
  font-size: 12px;
}

.runstate-item .value {
  color: var(--dian-text-primary);
  font-size: 15px;
  font-weight: 600;
}

/* 已识别的想看订阅用户（昵称 + ID） */
.wish-users {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin: 0 0 var(--dian-space-3) 2px;
}

.wish-users-label {
  font-size: 12px;
  color: var(--dian-text-muted);
}

.user-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 1px 9px 1px 3px;
  border: 1px solid var(--dian-border);
  border-radius: 999px;
  background: var(--dian-surface-raised);
  font-size: 12px;
  max-width: 220px;
}

.user-chip-name {
  font-weight: 600;
  color: var(--dian-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-chip-id {
  color: var(--dian-text-muted);
  font-size: 11px;
  flex: none;
}

.user-avatar {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  object-fit: cover;
  flex: none;
}

@media (max-width: 700px) {
  .page-header {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>

<style>
/* 宿主插件沙箱的高度棘轮修复（见 script 内「插件沙箱高度自纠」注释）。
   宿主基线 CSS 把 html/body/#plugin-sandbox-root 钉在 min-height:100%，
   配合桥接「取 max(…, documentElement.scrollHeight)」的测量方式，iframe 高度只增不减。
   该 class 只在检测到沙箱 iframe 时由脚本添加，不影响本地预览。 */
html.douban115-sandbox,
html.douban115-sandbox body,
html.douban115-sandbox #plugin-sandbox-root {
  min-height: 0 !important;
}
</style>
