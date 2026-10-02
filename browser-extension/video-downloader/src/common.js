// Shared helpers for the DIAN115 video push extension.
//
// Everything here is dependency free so it can be imported from the MV3
// service worker and from both extension pages.

export const API_PREFIX = '/api/openapi/v1/video-downloads'
/** 外部推送插件：115 分享转存 / 磁力 / ED2K 离线。 */
export const PUSH115_PREFIX = '/api/openapi/v1/external-push'
/** 115 账号与目录（用 DIAN115 已保存的账号，扩展不需要单独登录）。 */
export const API115_PREFIX = '/api/openapi/v1/115'

/**
 * 115 推送的默认值单独存一份，和页面推送的 settings 完全隔离：
 * 用户选了别的账号/目录不会影响原有的视频下载配置。
 */
export const PUSH115_DEFAULTS = {
  accountMode: 'main',
  accountId: 0,
  accountName: '',
  shareCid: '',
  shareName: '',
  offlineCid: '',
  offlineName: '',
}

export async function loadPush115() {
  const stored = await chrome.storage.local.get('push115')
  return { ...PUSH115_DEFAULTS, ...(stored && stored.push115 ? stored.push115 : {}) }
}

export async function savePush115(patch) {
  const current = await loadPush115()
  const next = { ...current, ...patch }
  await chrome.storage.local.set({ push115: next })
  return next
}

const SHARE115_RE = /https?:\/\/(?:share\.)?115(?:\.com|cdn\.com)\/[^\s<>"'【】《》[\]]+/i
const MAGNET_RE = /magnet:\?[^\s<>"'【】《》[\]]+/i
const ED2K_RE = /ed2k:\/\/[^\s<>"'【】《》[\]]+/i

/**
 * 识别一段文本/地址属于哪种推送：115 分享、磁力、ED2K 还是普通视频页面。
 * 返回 { kind, link, label }；kind 为 share115 | magnet | ed2k | video | unknown。
 */
export function detectPushLink(value) {
  const text = String(value || '').trim()
  if (!text) return { kind: 'unknown', link: '', label: '' }
  let matched = text.match(SHARE115_RE)
  if (matched) return { kind: 'share115', link: matched[0], label: '115 分享' }
  matched = text.match(MAGNET_RE)
  if (matched) return { kind: 'magnet', link: matched[0], label: '磁力' }
  matched = text.match(ED2K_RE)
  if (matched) return { kind: 'ed2k', link: matched[0], label: 'ED2K' }
  if (/^https?:\/\//i.test(text)) return { kind: 'video', link: text, label: '视频页面' }
  return { kind: 'unknown', link: text, label: '' }
}

export const ACTIVE_STATUSES = ['queued', 'resolving', 'downloading', 'postprocessing', 'paused']

export const STATUS_LABELS = {
  queued: '排队中',
  resolving: '解析中',
  downloading: '下载中',
  postprocessing: '处理中',
  paused: '已暂停',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
  interrupted: '已中断',
}

export const DEFAULT_SETTINGS = {
  baseUrl: '',
  apiKey: '',
  mode: 'video',
  quality: '',
  destinationId: '',
  cookieProfileId: '',
  autoListProbe: true,
  localConfirmThreshold: 5,
  confirmBytes: 20 * 1024 * 1024 * 1024,
  pollSeconds: 20,
  notifyOnComplete: true,
  notifyOnFailed: true,
  notifyOnQueued: true,
  // 推送时同时把当前站点 Cookie 同步到 DIAN115（默认关闭，需用户显式开启）。
  updateCookies: false,
}

// The API key is kept out of chrome.storage.local (persisted to disk in
// plaintext) and stored in chrome.storage.session instead, which is
// memory-only and cleared when the browser closes.
export async function loadSettings() {
  const [stored, session] = await Promise.all([
    chrome.storage.local.get('settings'),
    chrome.storage.session.get('apiKey'),
  ])
  const base = { ...DEFAULT_SETTINGS, ...(stored && stored.settings ? stored.settings : {}) }
  return { ...base, apiKey: (session && session.apiKey) || '' }
}

export async function saveSettings(patch) {
  const current = await loadSettings()
  const next = { ...current, ...patch }
  const { apiKey, ...rest } = next
  await Promise.all([
    chrome.storage.local.set({ settings: rest }),
    chrome.storage.session.set({ apiKey: apiKey || '' }),
  ])
  return next
}

// Drop trailing slashes so `${base}${path}` is always well formed.
export function normalizeBaseUrl(raw) {
  const value = String(raw || '').trim().replace(/\/+$/, '')
  if (!value) return ''
  if (!/^https?:\/\//i.test(value)) return ''
  return value
}

// buildApiUrl joins the configured server with one OpenAPI path. The prefix is
// overridable so the same helper serves the video-downloads, external-push and
// 115 helper surfaces.
export function buildApiUrl(settings, path, prefix = API_PREFIX) {
  const base = normalizeBaseUrl(settings.baseUrl)
  if (!base) return ''
  return base + prefix + path
}

export function newIdempotencyKey() {
  const uuid = typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : Math.random().toString(36).slice(2) + Date.now().toString(36)
  // The server requires 16-128 printable ASCII characters.
  return ('dian115-ext-' + uuid).slice(0, 120)
}

/**
 * dianFetch performs one OpenAPI call. It never throws for an HTTP error
 * status: callers inspect `ok`, `status` and the parsed `code` instead.
 */
export async function dianFetch(settings, path, options = {}) {
  const url = buildApiUrl(settings, path, options.prefix || API_PREFIX)
  if (!url) {
    return { ok: false, status: 0, code: 'not_configured', message: '尚未配置 DIAN115 服务器地址', data: null }
  }
  if (!settings.apiKey) {
    return { ok: false, status: 0, code: 'not_configured', message: '尚未配置 OpenAPI Key', data: null }
  }
  const method = options.method || 'GET'
  const headers = {
    'X-OpenAPI-Key': settings.apiKey,
    Accept: 'application/json',
  }
  if (options.body !== undefined && options.body !== null) {
    headers['Content-Type'] = 'application/json'
  }
  if (options.idempotencyKey) {
    headers['Idempotency-Key'] = options.idempotencyKey
  }
  const controller = new AbortController()
  const timeoutMs = options.timeoutMs === 0 ? 0 : (options.timeoutMs || 120000)
  const timer = timeoutMs > 0 ? setTimeout(() => controller.abort(), timeoutMs) : null
  try {
    const response = await fetch(url, {
      method,
      headers,
      body: options.body === undefined || options.body === null ? undefined : JSON.stringify(options.body),
      signal: controller.signal,
      cache: 'no-store',
      credentials: 'omit',
    })
    const text = await response.text()
    let data = null
    if (text) {
      try {
        data = JSON.parse(text)
      } catch {
        data = { raw: text.slice(0, 500) }
      }
    }
    return {
      ok: response.ok,
      status: response.status,
      code: data && data.code ? data.code : '',
      message: data && data.message ? data.message : '',
      data,
    }
  } catch (error) {
    const aborted = error && error.name === 'AbortError'
    return {
      ok: false,
      status: 0,
      code: aborted ? 'timeout' : 'network_error',
      message: aborted ? '请求超时，视频站点响应太慢' : '无法连接 DIAN115 服务器：' + (error && error.message ? error.message : '未知网络错误'),
      data: null,
    }
  } finally {
    if (timer) clearTimeout(timer)
  }
}

export function formatBytes(value) {
  const n = Number(value || 0)
  if (!n || n < 0) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = n
  let unit = 0
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024
    unit += 1
  }
  const digits = size >= 100 || unit === 0 ? 0 : 1
  return size.toFixed(digits) + ' ' + units[unit]
}

export function formatDuration(seconds) {
  const total = Math.round(Number(seconds || 0))
  if (!total || total < 0) return ''
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

const PLAYLIST_HINTS = [
  'list=', '/playlist', '/playlists', '/channel/', '/channels/', '/space/',
  '/album/', '/series', '/season', '/collection', '/mix', '/sets/', '/show/',
  '/bangumi/', '/media/', 'space.bilibili.com', 'medialist',
]

export function looksLikePlaylistUrl(raw) {
  const lower = String(raw || '').toLowerCase()
  if (!lower) return false
  return PLAYLIST_HINTS.some((hint) => lower.includes(hint))
}

export function hostOf(raw) {
  try {
    return new URL(raw).host
  } catch {
    return ''
  }
}

// extractUrlsFromText pulls http(s) links out of a text selection so a user can
// select a block of links on a page and push them in one go.
export function extractUrlsFromText(text) {
  const found = String(text || '').match(/https?:\/\/[^\s<>"'）)】\]]+/gi)
  if (!found) return []
  const seen = new Set()
  const urls = []
  for (const raw of found) {
    const cleaned = raw.replace(/[.,;:]+$/, '')
    if (!seen.has(cleaned)) {
      seen.add(cleaned)
      urls.push(cleaned)
    }
  }
  return urls.slice(0, 100)
}

export function truncate(text, max) {
  const value = String(text || '')
  if (value.length <= max) return value
  return value.slice(0, Math.max(1, max - 1)) + '…'
}

/**
 * 读取某个页面所属站点的 Cookie。
 * 只有在用户开启「推送时同时更新 CK」后才会被调用；返回值直接对应服务端
 * /cookies 接口的 cookies 字段。需要 manifest 里的 "cookies" 权限。
 */
export async function collectSiteCookies(pageUrl) {
  const host = hostOf(pageUrl)
  if (!host) return { host: '', cookies: [] }
  const list = await chrome.cookies.getAll({ url: pageUrl })
  const cookies = (list || [])
    .filter((item) => item && item.name)
    .map((item) => ({
      name: String(item.name),
      value: String(item.value ?? ''),
      domain: String(item.domain || host),
      path: String(item.path || '/'),
      expires: Number(item.expirationDate || 0),
      secure: item.secure === true,
      httpOnly: item.httpOnly === true,
    }))
  return { host, cookies }
}

// ---------------------------------------------------------------- 115 helper

/** 列出 DIAN115 里可用（已保存 Cookie）的 115 账号。 */
export async function fetch115Accounts(settings) {
  const res = await dianFetch(settings, '/accounts', { prefix: API115_PREFIX, timeoutMs: 20000 })
  if (!res.ok) return { ok: false, message: res.message || res.code || '读取账号失败', accounts: [], defaultAccount: null }
  const data = res.data || {}
  return {
    ok: true,
    accounts: Array.isArray(data.accounts) ? data.accounts : [],
    defaultAccount: data.default || null,
  }
}

/** 用 DIAN115 已保存的账号列出某个 CID 下的子目录，用来选转存/离线目标。 */
export async function fetch115Dirs(settings, cid, account) {
  const params = new URLSearchParams()
  params.set('cid', String(cid || '0'))
  if (account && account.mode) params.set('account_mode', String(account.mode))
  if (account && Number(account.id) > 0) params.set('account_id', String(account.id))
  const res = await dianFetch(settings, '/dirs?' + params.toString(), { prefix: API115_PREFIX, timeoutMs: 30000 })
  if (!res.ok) return { ok: false, message: res.message || res.code || '读取目录失败', dirs: [] }
  const data = res.data || {}
  return { ok: true, dirs: Array.isArray(data.dirs) ? data.dirs : [], cid: data.cid || cid }
}

/** 提交一条 115 分享/磁力/ED2K 到外部推送插件，返回 request_id。 */
export async function submitExternalPush(settings, { link, source, targetCid }) {
  const body = { source: source || '浏览器扩展', link: String(link || '') }
  if (targetCid) body.target_cid = String(targetCid)
  const res = await dianFetch(settings, '', {
    prefix: PUSH115_PREFIX,
    method: 'POST',
    body,
    idempotencyKey: newIdempotencyKey(),
    timeoutMs: 30000,
  })
  if (!res.ok) return { ok: false, message: res.message || res.code || '推送失败' }
  const data = res.data || {}
  return { ok: true, requestId: data.request_id || '', status: data.status || 'queued', type: data.type || '' }
}

/** 查询外部推送的执行结果。 */
export async function fetchExternalPushStatus(settings, requestId) {
  if (!requestId) return { ok: false, message: '缺少请求 ID' }
  const res = await dianFetch(settings, '/' + encodeURIComponent(requestId), { prefix: PUSH115_PREFIX, timeoutMs: 20000 })
  if (!res.ok) return { ok: false, message: res.message || res.code || '查询失败' }
  return { ok: true, record: res.data || {} }
}

/** 视频下载可用的目标目录（供扩展做下拉，不再手输目录 ID）。 */
export async function fetchVideoDestinations(settings) {
  const res = await dianFetch(settings, '/destinations', { timeoutMs: 20000 })
  if (!res.ok) return { ok: false, message: res.message || res.code || '读取目录失败', destinations: [], defaultId: '' }
  const data = res.data || {}
  return {
    ok: true,
    destinations: Array.isArray(data.destinations) ? data.destinations : [],
    defaultId: data.default_id || '',
  }
}
