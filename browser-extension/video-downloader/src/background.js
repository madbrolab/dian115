// MV3 service worker: context menus, pre-flight, confirmation, tracking.

import {
  ACTIVE_STATUSES,
  collectSiteCookies,
  DEFAULT_SETTINGS,
  STATUS_LABELS,
  dianFetch,
  extractUrlsFromText,
  formatBytes,
  detectPushLink,
  fetch115Accounts,
  fetch115Dirs,
  fetchExternalPushStatus,
  loadSettings,
  loadPush115,
  looksLikePlaylistUrl,
  newIdempotencyKey,
  savePush115,
  submitExternalPush,
  truncate,
} from './common.js'

const POLL_ALARM = 'dian115-poll'
const CONFIRM_NOTIFICATION = 'dian115-confirm'
const STATUS_NOTIFICATION = 'dian115-status'

const MENU_PAGE = 'dian115-push-page'
const MENU_LIST = 'dian115-push-list'
const MENU_LINK = 'dian115-push-link'
const MENU_SELECTION = 'dian115-push-selection'
const MENU_PUSH115 = 'dian115-push-115'

const MAX_TRACKED = 1000
let trackedUpdates = Promise.resolve()
let pollPromise = null
let confirmationPromise = null
let pendingUpdates = Promise.resolve()

function updatePending(change) {
  const operation = pendingUpdates.then(async () => {
    const stored = await chrome.storage.local.get('pendingPush')
    const next = change(stored.pendingPush)
    if (next) await chrome.storage.local.set({ pendingPush: next })
    else await chrome.storage.local.remove('pendingPush')
  })
  pendingUpdates = operation.catch(() => {})
  return operation
}

function updateTracked(change) {
  const operation = trackedUpdates.then(async () => {
    const latest = await getTracked()
    const next = change(latest)
    await chrome.storage.local.set({ tracked: next })
    return next
  })
  trackedUpdates = operation.catch(() => {})
  return operation
}

// ---------------------------------------------------------------- lifecycle

chrome.runtime.onInstalled.addListener(() => {
  void bootstrap()
})

chrome.runtime.onStartup.addListener(() => {
  void bootstrap()
})

async function bootstrap() {
  const stored = await chrome.storage.local.get(['settings', 'tracked', 'pendingPush'])
  if (!stored.settings) {
    await chrome.storage.local.set({ settings: { ...DEFAULT_SETTINGS } })
  }
  if (!Array.isArray(stored.tracked)) {
    await chrome.storage.local.set({ tracked: [] })
  }
  await buildMenus()
  await schedulePoll()
  await refreshBadge()
}

chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== 'local' || !changes.settings) return
  void schedulePoll()
  const previous = changes.settings.oldValue
  const next = changes.settings.newValue
  if (previous && next && previous.baseUrl !== next.baseUrl) {
    void updateTracked(() => []).then(() => refreshBadge())
    void updatePending(() => null)
  }
})

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === POLL_ALARM) void pollTracked()
})

async function buildMenus() {
  await chrome.contextMenus.removeAll()
  chrome.contextMenus.create({
    id: MENU_PAGE,
    title: '推送到 DIAN115 下载',
    contexts: ['page', 'video', 'audio'],
  })
  chrome.contextMenus.create({
    id: MENU_LIST,
    title: '推送当前页面节目单（列表探测）',
    contexts: ['page'],
  })
  chrome.contextMenus.create({
    id: MENU_LINK,
    title: '推送此链接到 DIAN115',
    contexts: ['link'],
  })
  chrome.contextMenus.create({
    id: MENU_SELECTION,
    title: '推送选中的链接到 DIAN115',
    contexts: ['selection'],
  })
  chrome.contextMenus.create({
    id: MENU_PUSH115,
    title: '推送到 115（转存 / 离线）',
    contexts: ['page', 'link', 'selection'],
  })
}

chrome.contextMenus.onClicked.addListener((info, tab) => {
  void handleMenuClick(info, tab)
})

async function handleMenuClick(info, tab) {
  if (info.menuItemId === MENU_PUSH115) {
    const candidate = info.linkUrl || info.selectionText || info.pageUrl || (tab && tab.url) || ''
    await startPush115(candidate, { source: '右键菜单' })
    return
  }
  if (info.menuItemId === MENU_LINK && info.linkUrl) {
    await startPush([info.linkUrl], { source: 'link' })
    return
  }
  if (info.menuItemId === MENU_SELECTION) {
    const urls = extractUrlsFromText(info.selectionText)
    if (!urls.length) {
      await notify('没有可推送的链接', '选中的文字里没有找到 http/https 链接。')
      return
    }
    await startPush(urls, { source: 'selection' })
    return
  }
  const pageUrl = info.pageUrl || (tab && tab.url) || ''
  if (!pageUrl) return
  if (info.menuItemId === MENU_LIST) {
    await startPush([pageUrl], { source: 'menu-list', probe: 'list' })
    return
  }
  await startPush([pageUrl], { source: 'menu' })
}

// --------------------------------------------------------------- push flow

/**
 * 把一条 115 分享 / 磁力 / ED2K 交给「外部推送」插件处理。
 * 目标目录优先用调用方传入的（弹窗里临时选择的），否则用扩展里保存的默认值。
 */
async function startPush115(rawValue, options = {}) {
  const settings = await loadSettings()
  if (!settings.baseUrl || !settings.apiKey) {
    await notify('尚未配置 DIAN115', '请先在扩展设置里填写服务器地址和 OpenAPI Key。', { openOptions: true })
    return { ok: false, code: 'not_configured' }
  }
  const detected = detectPushLink(rawValue)
  if (detected.kind !== 'share115' && detected.kind !== 'magnet' && detected.kind !== 'ed2k') {
    await notify('没有识别到 115 链接', '支持 115 分享链接、磁力链接和 ED2K 链接。')
    return { ok: false, code: 'no_115_link' }
  }
  const defaults = await loadPush115()
  const isShare = detected.kind === 'share115'
  const targetCid = String(
    options.targetCid
    || (isShare ? defaults.shareCid : defaults.offlineCid)
    || '',
  ).trim()
  if (!targetCid) {
    await notify('请先选择 115 目录', (isShare ? '转存' : '离线') + '目标目录未设置：打开扩展弹窗选一次并「保存为默认」即可。')
    return { ok: false, code: 'target_missing' }
  }
  const submit = await submitExternalPush(settings, {
    link: detected.link,
    source: options.source || '浏览器扩展',
    targetCid,
    accountMode: options.accountMode || defaults.accountMode,
    accountId: options.accountId ?? defaults.accountId,
  })
  if (!submit.ok) {
    await notify('115 推送失败', submit.message || 'DIAN115 返回了错误。')
    return { ok: false, code: 'submit_failed', message: submit.message }
  }
  if (options.deferPoll) {
    return { ok: true, requestId: submit.requestId, kind: detected.kind, type: submit.type }
  }
  const finished = await pollExternalPush(settings, submit.requestId, 60)
  await notify(finished.ok ? '已推送到 115' : '115 推送失败', finished.message)
  return { ok: finished.ok, requestId: submit.requestId, message: finished.message }
}

/** 轮询外部推送结果；成功后返回目标路径，失败返回原因。 */
async function pollExternalPush(settings, requestId, timeoutSeconds = 60) {
  if (!requestId) return { ok: true, message: '已提交，可稍后在 DIAN115 的外部推送记录里查看结果' }
  const deadline = Date.now() + timeoutSeconds * 1000
  while (Date.now() < deadline) {
    const res = await fetchExternalPushStatus(settings, requestId)
    if (!res.ok) return { ok: false, message: res.message || '查询推送状态失败' }
    const record = res.record || {}
    const status = String(record.status || '')
    if (status === 'succeeded') return { ok: true, status, record, message: '已完成：' + (record.target_path || record.link_display || '') }
    if (status === 'failed' || status === 'rejected') {
      return { ok: false, status, record, message: record.error_message || record.error_code || '115 处理失败' }
    }
    await new Promise((resolve) => setTimeout(resolve, 3000))
  }
  return { ok: true, status: 'processing', message: '已提交，仍在处理中，可稍后在 DIAN115 里查看结果' }
}

async function startPush(rawUrls, options = {}) {
  const urls = (rawUrls || []).map((u) => String(u || '').trim()).filter(Boolean)
  if (!urls.length) return { ok: false, code: 'no_url' }
  // 用户在预览里点选的格式 id；为空时由服务端按 quality/默认规则挑。
  const formatId = String(options.formatId || '').trim()
  const settings = await loadSettings()
  if (!settings.baseUrl || !settings.apiKey) {
    await notify(
      '尚未配置 DIAN115',
      '请先在扩展设置里填写服务器地址和 OpenAPI Key。',
      { openOptions: true },
    )
    return { ok: false, code: 'not_configured' }
  }

  let preview = null
  // 「推送时同时更新站点 CK」默认关闭。开启后先把该站点的 Cookie 同步到服务端，
  // 但这是尽力而为：同步失败不影响推送本身。
  let cookieSync = null
  if (settings.updateCookies && urls.length === 1) {
    cookieSync = await syncSiteCookies(settings, urls[0])
  }
  if (urls.length === 1) {
    const probe = options.probe
      || (settings.autoListProbe && looksLikePlaylistUrl(urls[0]) ? 'list' : 'quick')
    const res = await dianFetch(settings, '/quick', {
      method: 'POST',
      body: {
        url: urls[0],
        probe,
        destination_id: settings.destinationId || undefined,
        ...(settings.cookieProfileId ? { cookie_profile_id: settings.cookieProfileId } : {}),
      },
      timeoutMs: 180000,
    })
    if (!res.ok) {
      await notify('推送失败：无法预检', res.message || 'DIAN115 返回了错误。')
      return { ok: false, code: res.code, message: res.message || '视频预检失败' }
    }
    preview = res.data && res.data.result ? res.data.result : null
  }

  if (preview && needsLocalConfirmation(settings, preview)) {
    return await openConfirmation({
      urls,
      preview,
      confirmToken: preview.confirm_token || '',
      reason: 'local',
      formatId,
      settings,
      cookieSync,
    })
  }

  if (!preview && urls.length > Number(settings.localConfirmThreshold || 5)) {
    return openConfirmation({ urls, preview: { total_items: urls.length }, formatId, settings, cookieSync })
  }

  return await submitBatch(urls, preview, settings, '', cookieSync, formatId)
}

function needsLocalConfirmation(settings, preview) {
  const total = Number(preview.total_items || 1)
  if (preview.requires_confirmation) return true
  if (total > Number(settings.localConfirmThreshold || 0)) return true
  const bytes = Number(preview.estimated_bytes || 0)
  if (bytes > 0 && Number(settings.confirmBytes || 0) > 0 && bytes > Number(settings.confirmBytes)) return true
  if (total > Number(preview.queue_free || 0)) return true
  return false
}

async function submitBatch(urls, preview, settings, confirmToken, cookieSync = null, formatId = '', submission = {}) {
  const body = {
    urls,
    mode: settings.mode,
    playlist: false,
    dedupe: true,
  }
  // 具体格式优先于清晰度筛选；两者都由服务端再校验一次。
  if (formatId) body.format_id = formatId
  else if (settings.quality) body.quality = settings.quality
  if (settings.destinationId) body.destination_id = settings.destinationId
  if (settings.cookieProfileId) body.cookie_profile_id = settings.cookieProfileId
  if (urls.length === 1 && preview && Number(preview.total_items || 0) > 1) {
    body.playlist = true
    body.batch_url = urls[0]
  } else if (urls.length > 1) {
    body.batch_url = urls[0]
  }
  if (confirmToken) body.confirm_token = confirmToken

  const res = await dianFetch(settings, '/tasks', {
    method: 'POST',
    body,
    idempotencyKey: submission.idempotencyKey || newIdempotencyKey(),
    timeoutMs: 60000,
  })

  if (res.status === 409 && res.code === 'confirmation_required') {
    const info = (res.data && res.data.result) || {}
    return await openConfirmation({
      urls,
      preview: {
        title: (preview && preview.title) || urls[0],
        total_items: Number(info.total_items || 0),
        estimated_bytes: Number(info.estimated_bytes || 0),
        queue_free: Number(info.queue_free || 0),
      },
      confirmToken: info.confirm_token || '',
      expiresAt: info.confirm_expires_at || '',
      reason: 'server',
      formatId,
      settings,
      cookieSync,
    })
  }

  if (!res.ok) {
    await notify('推送失败', res.message || 'DIAN115 返回了错误。')
    return { ok: false, code: res.code, message: res.message }
  }

  const result = (res.data && res.data.result) || {}
  await trackTasks(result, urls)
  if (submission.pendingId) {
    await updatePending(current => current && current.id !== submission.pendingId ? current : null)
  }
  const accepted = Number(result.accepted || 0)
  const duplicates = Number(result.duplicates || 0)
  if (settings.notifyOnQueued) {
    const parts = [`已加入 ${accepted} 个任务`]
    if (duplicates > 0) parts.push(`${duplicates} 个已存在，未重复创建`)
    if (Number(result.rejected || 0) > 0) parts.push(`${result.rejected} 个被拒绝`)
    if (cookieSync && cookieSync.ok) parts.push(`已同步站点 CK ${cookieSync.count} 条`)
    if (cookieSync && cookieSync.ok === false) parts.push('站点 CK 同步失败：' + (cookieSync.message || '未知错误'))
    await notify(accepted > 0 || duplicates > 0 ? '已推送到 DIAN115' : '视频推送未入队', parts.join('，'))
  }
  await refreshBadge()
  return { ok: accepted > 0 || duplicates > 0, accepted, duplicates, rejected: Number(result.rejected || 0), message: accepted > 0 || duplicates > 0 ? '' : '没有任务加入队列，请检查目标目录、下载选项和队列余量' }
}

/**
 * 把当前站点 Cookie 同步到 DIAN115（仅在设置里开启时调用）。
 * 任何失败都只记录，不影响推送流程。
 */
async function syncSiteCookies(settings, pageUrl) {
  try {
    const { host, cookies } = await collectSiteCookies(pageUrl)
    if (!host || !cookies.length) return null
    const res = await dianFetch(settings, '/cookies', {
      method: 'POST',
      body: { host, cookies, name: host + '（浏览器同步）' },
      idempotencyKey: newIdempotencyKey(),
      timeoutMs: 30000,
    })
    if (!res.ok) return { ok: false, message: res.message || res.code || '同步失败' }
    return { ok: true, host, count: cookies.length }
  } catch (error) {
    return { ok: false, message: (error && error.message) || '同步失败' }
  }
}

async function openConfirmation(pending) {
  const record = {
    id: newIdempotencyKey(),
    idempotencyKey: newIdempotencyKey(),
    urls: pending.urls,
    preview: pending.preview || {},
    confirmToken: pending.confirmToken || '',
    expiresAt: pending.expiresAt || '',
    reason: pending.reason || '',
    formatId: pending.formatId || '',
    settings: pending.settings,
    cookieSync: pending.cookieSync || null,
    createdAt: Date.now(),
  }
  await updatePending(() => record)
  const total = Number(record.preview.total_items || record.urls.length || 1)
  const bytes = Number(record.preview.estimated_bytes || 0)
  const message = [
    `本次将加入 ${total} 个任务`,
    bytes > 0 ? `预计 ${formatBytes(bytes)}` : '',
    `队列剩余 ${Number(record.preview.queue_free || 0)} 个名额`,
  ].filter(Boolean).join('，') + '。确认后开始下载。'
  try {
      await chrome.notifications.create(CONFIRM_NOTIFICATION + ':' + record.id, {
      type: 'basic',
      iconUrl: chrome.runtime.getURL('icons/icon128.png'),
      title: 'DIAN115 需要确认',
      message: truncate(message, 220),
      buttons: [{ title: '确认加入' }, { title: '取消' }],
      requireInteraction: true,
    })
  } catch {
    // Notifications are best effort; the popup still shows the confirmation.
  }
  return { ok: true, pending: true, total }
}

async function resolvePending(approve, expectedId) {
  if (confirmationPromise) return { ok: false, code: 'confirmation_busy', message: '正在提交确认，请等待结果' }
  confirmationPromise = resolvePendingOnce(approve, expectedId).finally(() => { confirmationPromise = null })
  return confirmationPromise
}

async function resolvePendingOnce(approve, expectedId) {
  const stored = await chrome.storage.local.get('pendingPush')
  const pending = stored.pendingPush
  if (!pending) return { ok: false, code: 'no_pending' }
  if (expectedId && expectedId !== pending.id) return { ok: false, code: 'pending_changed', message: '待确认的推送已变化，请刷新后重新确认' }
  await chrome.notifications.clear(CONFIRM_NOTIFICATION + ':' + pending.id).catch(() => {})
  if (!approve) {
    await updatePending(current => current && current.id !== pending.id ? current : null)
    return { ok: true, cancelled: true }
  }
  const settings = pending.settings || await loadSettings()
  return await submitBatch(pending.urls, pending.preview, settings, pending.confirmToken, pending.cookieSync, pending.formatId || '', { pendingId: pending.id, idempotencyKey: pending.idempotencyKey })
}

chrome.notifications.onButtonClicked.addListener((notificationId, buttonIndex) => {
  if (!notificationId.startsWith(CONFIRM_NOTIFICATION + ':')) return
  void resolvePending(buttonIndex === 0, notificationId.slice(CONFIRM_NOTIFICATION.length + 1))
})

chrome.notifications.onClicked.addListener((notificationId) => {
  if (notificationId.startsWith(CONFIRM_NOTIFICATION + ':')) {
    void chrome.runtime.openOptionsPage().catch(() => {})
  }
})

// -------------------------------------------------------------- task stats

async function getTracked() {
  const stored = await chrome.storage.local.get('tracked')
  return Array.isArray(stored.tracked) ? stored.tracked : []
}

async function trackTasks(result, urls) {
  await updateTracked((tracked) => {
  const byId = new Map(tracked.map((item) => [String(item.id), item]))
  const batchId = result.batch_id || ''
  for (const task of result.tasks || []) {
    if (!task || task.id === undefined || task.id === null) continue
    const key = String(task.id)
    const existing = byId.get(key)
    if (existing) {
      existing.batchId = existing.batchId || task.batch_id || batchId
      if (ACTIVE_STATUSES.includes(task.status) && !ACTIVE_STATUSES.includes(existing.status)) existing.notifiedTerminal = false
      existing.status = task.status || existing.status
      existing.progress = Number(task.progress || 0)
      existing.duplicate = !!task.duplicate
      existing.misses = 0
      existing.revision = newIdempotencyKey()
      continue
    }
    byId.set(key, {
      id: task.id,
      url: task.url || urls[0],
      title: task.title || task.url || urls[0],
      status: task.status || 'queued',
      progress: Number(task.progress || 0),
      duplicate: !!task.duplicate,
      batchId: task.batch_id || batchId,
      createdAt: Date.now(),
      notifiedTerminal: false,
      misses: 0,
      revision: newIdempotencyKey(),
    })
  }
  const merged = Array.from(byId.values())
    .sort((a, b) => Number(ACTIVE_STATUSES.includes(b.status)) - Number(ACTIVE_STATUSES.includes(a.status)) || (b.createdAt || 0) - (a.createdAt || 0))
    .slice(0, MAX_TRACKED)
  return merged
  })
}

async function pollTracked() {
  if (pollPromise) return pollPromise
  pollPromise = pollTrackedOnce().finally(() => { pollPromise = null })
  return pollPromise
}

async function pollTrackedOnce() {
  const settings = await loadSettings()
  if (!settings.baseUrl || !settings.apiKey) return
  const tracked = await getTracked()
  if (!tracked.length) return

  const finished = []
  const active = tracked.filter((item) => ACTIVE_STATUSES.includes(item.status))
  const storedCursor = await chrome.storage.local.get('pollCursor')
  const cursor = active.length ? Number(storedCursor.pollCursor || 0) % active.length : 0
  const selected = Array.from({ length: Math.min(30, active.length) }, (_, i) => active[(cursor + i) % active.length])
  const fetched = new Map()
  async function pollItem(item) {
    const res = await dianFetch(settings, '/tasks/' + encodeURIComponent(String(item.id)), { timeoutMs: 20000 })
    if (!res.ok) {
      if (res.status === 404) {
        item.misses = (item.misses || 0) + 1
        fetched.set(String(item.id), item)
        if (item.misses >= 3) item.status = 'removed'
      }
      return
    }
    const task = (res.data && res.data.task) || null
    if (!task) return
    fetched.set(String(item.id), item)
    item.misses = 0
    const nextStatus = task.status || item.status
    if (nextStatus !== item.status) {
      item.status = nextStatus
      if (nextStatus === 'completed' || nextStatus === 'failed' || nextStatus === 'cancelled' || nextStatus === 'interrupted') {
        finished.push(item)
      }
    }
    const nextProgress = Number(task.progress || 0)
    if (Math.abs(nextProgress - Number(item.progress || 0)) > 0.01) {
      item.progress = nextProgress
    }
    if (task.title && task.title !== item.title) {
      item.title = task.title
    }
    if (task.speed_bytes !== undefined) item.speedBytes = Number(task.speed_bytes || 0)
  }
  for (let i = 0; i < selected.length; i += 5) await Promise.all(selected.slice(i, i + 5).map(pollItem))
  await chrome.storage.local.set({ pollCursor: active.length ? (cursor + selected.length) % active.length : 0 })

  const notices = []
  await updateTracked((latest) => {
    return latest.map((item) => {
      const update = fetched.get(String(item.id))
      if (!update || item.revision !== update.revision) return item
      const merged = { ...item, ...update }
      if (finished.some((done) => String(done.id) === String(item.id)) && !item.notifiedTerminal) {
        merged.notifiedTerminal = true
        notices.push(merged)
      }
      return merged
    })
  })

  for (const item of notices) {
    if (item.status === 'completed' && settings.notifyOnComplete) {
      await notify('视频下载完成', truncate(item.title || item.url, 180))
    } else if (item.status === 'failed' && settings.notifyOnFailed) {
      await notify('视频下载失败', truncate(item.title || item.url, 180))
    }
  }
  await refreshBadge()
}

async function refreshBadge() {
  const tracked = await getTracked()
  const active = tracked.filter((item) => ACTIVE_STATUSES.includes(item.status)).length
  await chrome.action.setBadgeBackgroundColor({ color: active > 0 ? '#2f7cf6' : '#6b7280' }).catch(() => {})
  await chrome.action.setBadgeText({ text: active > 0 ? String(active) : '' }).catch(() => {})
}

async function schedulePoll() {
  const settings = await loadSettings()
  const seconds = Math.max(60, Number(settings.pollSeconds) || 60)
  await chrome.alarms.clear(POLL_ALARM)
  chrome.alarms.create(POLL_ALARM, {
    periodInMinutes: seconds / 60,
    delayInMinutes: seconds / 60,
  })
}

// ------------------------------------------------------------- messaging

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  void (async () => {
    const type = message && message.type
    if (type === 'state') {
      const settings = await loadSettings()
      const stored = await chrome.storage.local.get(['tracked', 'pendingPush'])
      sendResponse({
        ok: true,
        runtimeId: chrome.runtime.id,
        settings: { ...settings, apiKey: settings.apiKey ? maskKey(settings.apiKey) : '' },
        configured: !!(settings.baseUrl && settings.apiKey),
        tracked: Array.isArray(stored.tracked) ? stored.tracked : [],
        pending: stored.pendingPush ? { ...stored.pendingPush, settings: undefined } : null,
      })
      return
    }
    if (type === 'preview') {
      const settings = await loadSettings()
      const url = String((message && message.url) || '').trim()
      if (!url) {
        sendResponse({ ok: false, code: 'no_url' })
        return
      }
      const probe = (message && message.probe) || (settings.autoListProbe && looksLikePlaylistUrl(url) ? 'list' : 'quick')
      const res = await dianFetch(settings, '/quick', {
        method: 'POST',
        body: { url, probe, destination_id: settings.destinationId || undefined, ...(settings.cookieProfileId ? { cookie_profile_id: settings.cookieProfileId } : {}) },
        timeoutMs: 180000,
      })
      sendResponse({ ok: res.ok, code: res.code, message: res.message, preview: res.data && res.data.result ? res.data.result : null, probe })
      return
    }
    if (type === 'push') {
      const result = await startPush((message && message.urls) || [], {
        probe: message && message.probe,
        formatId: message && message.formatId,
        source: 'popup',
      })
      sendResponse(result || { ok: true })
      return
    }
    if (type === 'push115') {
      const result = await startPush115((message && message.link) || '', {
        source: '浏览器扩展',
        targetCid: message && message.targetCid,
        accountMode: message && message.accountMode,
        accountId: message && message.accountId,
        deferPoll: true,
      })
      sendResponse(result || { ok: true })
      return
    }
    if (type === 'push115Status') {
      const settings = await loadSettings()
      const res = await fetchExternalPushStatus(settings, (message && message.requestId) || '')
      sendResponse(res)
      return
    }
    if (type === 'accounts115') {
      const settings = await loadSettings()
      sendResponse(await fetch115Accounts(settings))
      return
    }
    if (type === 'dirs115') {
      const settings = await loadSettings()
      sendResponse(await fetch115Dirs(settings, message && message.cid, {
        mode: message && message.accountMode,
        id: message && message.accountId,
      }))
      return
    }
    if (type === 'save115Defaults') {
      sendResponse({ ok: true, push115: await savePush115((message && message.push115) || {}) })
      return
    }
    if (type === 'confirm') {
      sendResponse(await resolvePending(true, message && message.pendingId))
      return
    }
    if (type === 'cancel') {
      sendResponse(await resolvePending(false, message && message.pendingId))
      return
    }
    if (type === 'refresh') {
      await pollTracked()
      sendResponse({ ok: true })
      return
    }
    if (type === 'clearTracked') {
      await updateTracked(() => [])
      await refreshBadge()
      sendResponse({ ok: true })
      return
    }
    sendResponse({ ok: false, code: 'unknown_message' })
  })().catch((error) => sendResponse({ ok: false, code: 'extension_error', message: (error && error.message) || '扩展处理失败，请重试' }))
  return true
})

function maskKey(key) {
  const value = String(key)
  if (value.length <= 8) return '****'
  return value.slice(0, 4) + '****' + value.slice(-4)
}

// ------------------------------------------------------------ notifications

async function notify(title, message, options = {}) {
  try {
    await chrome.notifications.create(STATUS_NOTIFICATION + '-' + Date.now(), {
      type: 'basic',
      iconUrl: chrome.runtime.getURL('icons/icon128.png'),
      title: truncate(title, 80),
      message: truncate(message, 220),
      priority: 0,
    })
  } catch {
    // Ignore: the popup still reports the same information.
  }
  if (options.openOptions) {
    await chrome.runtime.openOptionsPage().catch(() => {})
  }
}

export const __statusLabels = STATUS_LABELS
