import {
  ACTIVE_STATUSES,
  STATUS_LABELS,
  PUSH115_DEFAULTS,
  detectPushLink,
  isExternalPushKind,
  uniquePushLinks,
  formatBytes,
  formatDuration,
  hostOf,
  truncate,
} from './common.js'

const el = (id) => document.getElementById(id)

let runtimeId = ''
let currentTab = null
let lastPreview = null
let lastFormats = []
let pendingId = ''
let pageLinks = []
let batchLinks = []
const bulkSelected = new Set()
let bulkRunning = false
let previewRequest = 0

function send(message) {
  return new Promise((resolve) => chrome.runtime.sendMessage(message, (response) => {
    const error = chrome.runtime.lastError
    resolve(error ? { ok: false, message: error.message || '扩展连接中断，请重试' } : (response || { ok: false, message: '扩展未返回结果，请重试' }))
  }))
}

function toast(text) {
  const node = el('toast')
  node.textContent = text
  node.classList.add('show')
  setTimeout(() => node.classList.remove('show'), 2600)
}

function statusTag(status) {
  const label = STATUS_LABELS[status] || status
  const cls = status === 'completed' ? 'ok' : (status === 'failed' || status === 'cancelled' ? 'fail' : (status === 'paused' || status === 'interrupted' ? 'warn' : ''))
  return `<span class="tag ${cls}">${escapeHtml(label)}</span>`
}

function renderPending(pending) {
  pendingId = pending ? pending.id : ''
  const card = el('pending-card')
  if (!pending) {
    card.hidden = true
    return
  }
  const preview = pending.preview || {}
  const total = Number(preview.total_items || pending.urls.length || 1)
  const bytes = Number(preview.estimated_bytes || 0)
  const parts = [`本次将加入 ${total} 个任务`]
  if (bytes > 0) parts.push(`预计 ${formatBytes(bytes)}`)
  parts.push(`队列剩余 ${Number(preview.queue_free || 0)} 个名额`)
  if (pending.expiresAt) parts.push(`确认有效期至 ${pending.expiresAt}`)
  el('pending-text').textContent = parts.join('，') + '。'
  card.hidden = false
}

function renderTasks(tracked) {
  const host = el('tasks')
  if (!tracked || !tracked.length) {
    host.innerHTML = '<div class="empty">还没有推送记录。</div>'
    return
  }
  const batches = new Map()
  const loose = []
  for (const item of tracked) {
    if (item.batchId) {
      if (!batches.has(item.batchId)) batches.set(item.batchId, [])
      batches.get(item.batchId).push(item)
    } else {
      loose.push(item)
    }
  }

  const rows = []
  for (const [batchId, items] of batches) {
    const done = items.filter((i) => i.status === 'completed').length
    const failed = items.filter((i) => i.status === 'failed').length
    const percent = items.length ? Math.round(items.reduce((sum, i) => sum + Number(i.progress || 0), 0) / items.length) : 0
    const cls = failed > 0 ? 'fail' : (done === items.length ? 'done' : '')
    rows.push(`
      <div class="task">
        <div class="row between">
          <div class="grow ellipsis small">${escapeHtml(truncate(items[0].title || items[0].url, 60))}</div>
          <span class="tag">批次 ${items.length} 项</span>
        </div>
        <div class="small muted">${done}/${items.length} 已完成${failed ? '，' + failed + ' 个失败' : ''}</div>
        <div class="bar ${cls}"><i style="width:${percent}%"></i></div>
      </div>`)
  }
  for (const item of loose) {
    const progress = Math.max(0, Math.min(100, Number(item.progress || 0)))
    const cls = item.status === 'completed' ? 'done' : (item.status === 'failed' ? 'fail' : '')
    const stalled = item.status === 'downloading' && Number(item.speedBytes || 0) === 0
    rows.push(`
      <div class="task">
        <div class="row between">
          <div class="grow ellipsis small">${escapeHtml(truncate(item.title || item.url, 60))}</div>
          ${statusTag(item.status)}
        </div>
        <div class="small muted">
          ${item.duplicate ? '已存在，未重复创建 · ' : ''}
          ${ACTIVE_STATUSES.includes(item.status) ? progress.toFixed(0) + '%' : ''}
          ${stalled ? ' · 疑似停滞' : ''}
        </div>
        <div class="bar ${cls}"><i style="width:${progress}%"></i></div>
      </div>`)
  }
  host.innerHTML = rows.join('')
}

function escapeHtml(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/** 服务端格式项 → 一行可读文案（推荐、清晰度、编码、容器、体积、是否要合并音轨）。 */
function formatOptionLabel(item) {
  const codec = item.vcodec && item.vcodec !== 'none' ? item.vcodec : item.acodec
  const size = Number(item.filesize || item.filesize_approx || 0)
  const parts = [
    item.recommended ? '★ 推荐' : '',
    item.resolution,
    codec,
    item.container,
    size > 0 ? formatBytes(size) : '',
    item.needs_audio ? '需合并音轨' : '',
  ].filter(Boolean)
  return parts.join(' · ') || item.label || String(item.id)
}

/** 按当前下载模式挑出可选格式：推荐项最前，其余按分辨率、码率降序。 */
function visibleFormats() {
  const mode = el('mode').value === 'audio' ? 'audio' : 'video'
  return (lastFormats || [])
    .filter((item) => {
      const kind = item.kind || 'video'
      return mode === 'audio' ? kind === 'audio' : kind !== 'audio'
    })
    .sort((a, b) => {
      if (!!b.recommended !== !!a.recommended) return b.recommended ? 1 : -1
      const height = Number(b.height || 0) - Number(a.height || 0)
      if (height) return height
      return Number(b.tbr || 0) - Number(a.tbr || 0)
    })
}

/** 重建格式下拉；默认选中推荐项，并尽量保留用户已选的那一条。 */
function renderFormatOptions() {
  const field = el('preview-format-field')
  const select = el('preview-format')
  const list = visibleFormats()
  if (!list.length) {
    select.innerHTML = ''
    field.hidden = true
    el('format-card').hidden = pageLinks.length < 2
    return
  }
  const previous = select.value
  select.innerHTML = list
    .map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(formatOptionLabel(item))}</option>`)
    .join('')
  const keep = list.some((item) => String(item.id) === previous) ? previous : String(list[0].id)
  select.value = keep
  field.hidden = false
  el('format-card').hidden = false
}

/** 预览里选中的格式 id；没有下拉（未解析/无可用格式）时返回空串。 */
function selectedFormatId() {
  const field = el('preview-format-field')
  if (!field || field.hidden) return ''
  return el('preview-format').value || ''
}

function renderPreview(preview, probe) {
  const card = el('preview-card')
  if (!preview) {
    card.hidden = true
    return
  }
  lastPreview = { preview, probe, url: currentTab?.url }
  lastFormats = Array.isArray(preview.formats) ? preview.formats : []
  el('preview-title').textContent = preview.title || '(未命名)'
  el('preview-probe').textContent = probe === 'list' ? '节目单' : '单个视频'
  const source = [preview.extractor, hostOf(preview.webpage_url || '')].filter(Boolean).join(' · ')
  el('preview-source').textContent = [source, preview.warning].filter(Boolean).join(' · ')
  if (preview.thumbnail) {
    const img = el('preview-thumb')
    img.src = preview.thumbnail
    img.hidden = false
  } else {
    el('preview-thumb').hidden = true
  }
  const stats = []
  stats.push(`<div><b>${Number(preview.total_items || 1)}</b>条目</div>`)
  if (Number(preview.estimated_bytes || 0) > 0) stats.push(`<div><b>${formatBytes(preview.estimated_bytes)}</b>预计体积</div>`)
  stats.push(`<div><b>${Number(preview.queue_free || 0)}</b>队列剩余</div>`)
  if (preview.duration) stats.push(`<div><b>${formatDuration(preview.duration)}</b>时长</div>`)
  if (preview.is_live) stats.push('<div><b>直播</b>进行中</div>')
  el('preview-stats').innerHTML = stats.join('')
  renderFormatOptions()
  const list = el('preview-items')
  if (Array.isArray(preview.items) && preview.items.length) {
    list.innerHTML = preview.items.slice(0, 30).map((item) => `
      <li>
        <span class="idx">${Number(item.index || 0)}</span>
        <span class="grow ellipsis">${escapeHtml(item.title || item.url || '')}</span>
        <span class="muted">${formatDuration(item.duration)}</span>
      </li>`).join('') + (preview.playlist_truncated ? '<li><span class="idx">…</span><span class="grow muted">列表已截断，仅显示前若干项</span></li>' : '')
    list.hidden = false
  } else {
    list.hidden = true
  }
  card.hidden = false
}

async function loadState() {
  const state = await send({ type: 'state' })
  if (!state.ok) return
  runtimeId = state.runtimeId || ''
  el('conn-dot').className = 'dot ' + (state.configured ? 'ok' : 'off')
  renderPending(state.pending)
  renderTasks(state.tracked)
  if (state.settings && state.settings.mode) el('mode').value = state.settings.mode
  if (state.settings && state.settings.baseUrl) {
    const link = el('open-in-server')
    link.href = state.settings.baseUrl
    link.hidden = false
  }
}

async function loadTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true })
  currentTab = tabs && tabs[0] ? tabs[0] : null
  if (currentTab) {
    el('page-title').textContent = currentTab.title || '(无标题)'
    el('page-url').textContent = hostOf(currentTab.url || '') || currentTab.url || ''
  }
}

async function probe(probeName) {
  if (!currentTab || !currentTab.url) return
  const request = ++previewRequest
  const url = currentTab.url
  el('probe-list').disabled = true
  el('push-page').disabled = true
  try {
    const res = await send({ type: 'preview', url, probe: probeName })
    if (request !== previewRequest || currentTab?.url !== url) return
    if (!res.ok) {
      lastPreview = null; lastFormats = []; renderPreview(null); renderFormatOptions()
      toast(res.message || '预检失败')
      return
    }
    renderPreview(res.preview, res.preview?.probe || res.probe || probeName)
    if (res.cookieSync?.ok === false) toast('站点登录态同步失败：' + res.cookieSync.message)
  } finally {
    el('probe-list').disabled = false
    el('push-page').disabled = false
  }
}

el('push-page').addEventListener('click', async () => {
  if (!currentTab || !currentTab.url) return
  el('push-page').disabled = true
  const res = await send({ type: 'push', urls: [currentTab.url], probe: lastPreview?.url === currentTab.url ? lastPreview.probe : undefined, formatId: selectedFormatId() })
  el('push-page').disabled = false
  if (res && res.pending) toast('需要确认后才会开始下载')
  else if (res && res.ok) toast('已加入下载队列')
  else toast((res && res.message) || '推送失败')
  await loadState()
})

el('probe-list').addEventListener('click', () => void probe('list'))

el('preview-push').addEventListener('click', async () => {
  if (!lastPreview || !currentTab) return
  const res = await send({
    type: 'push',
    urls: [lastPreview.url],
    probe: lastPreview.probe,
    formatId: selectedFormatId(),
  })
  if (res && res.pending) toast('需要确认后才会开始下载')
  else if (res && res.ok) toast('已加入下载队列')
  else if (res && res.message) toast(res.message)
  await loadState()
})

el('preview-close').addEventListener('click', () => {
  lastPreview = null
  lastFormats = []
  el('preview-format').innerHTML = ''
  el('preview-format-field').hidden = true
  el('preview-card').hidden = true
  renderFormatOptions()
})

el('pending-confirm').addEventListener('click', async () => {
  const res = await send({ type: 'confirm', pendingId })
  toast(res && res.pending ? '列表或确认条件发生变化，请重新确认' : (res && res.ok ? '已确认，开始下载' : ((res && res.message) || '确认失败')))
  await loadState()
})

el('pending-cancel').addEventListener('click', async () => {
  const res = await send({ type: 'cancel', pendingId })
  toast(res && res.ok ? '已取消' : ((res && res.message) || '取消失败'))
  await loadState()
})

el('refresh').addEventListener('click', async () => {
  await send({ type: 'refresh' })
  await loadState()
  await loadPageLinks()
})

el('clear').addEventListener('click', async () => {
  await send({ type: 'clearTracked' })
  await loadState()
})

el('open-options').addEventListener('click', () => chrome.runtime.openOptionsPage())

el('mode').addEventListener('change', async () => {
  await chrome.storage.local.get('settings').then((stored) => {
    const settings = { ...(stored.settings || {}), mode: el('mode').value }
    return chrome.storage.local.set({ settings })
  })
  // 模式变了，可选格式也不同，按新模式重挑一遍。
  if (lastFormats.length) renderFormatOptions()
})

async function loadPageLinks() {
  const current = detectPushLink(currentTab?.url || '')
  let scanned = []
  if (currentTab?.id && /^https?:\/\//i.test(currentTab.url || '')) {
    scanned = await new Promise(resolve => {
      chrome.tabs.sendMessage(currentTab.id, { type: 'pageLinks' }, response => {
        const error = chrome.runtime.lastError
        resolve(!error && response?.ok ? response.links || [] : [])
      })
    })
  }
  pageLinks = uniquePushLinks([...(isExternalPushKind(current.kind) ? [current] : []), ...scanned])
  detected115 = pageLinks.find(item => item.key === detected115.key) || pageLinks[0] || { kind: 'unknown', link: '', label: '' }
  el('video-controls').hidden = isExternalPushKind(current.kind)
  const validPage = /^https?:\/\//i.test(currentTab?.url || '')
  el('push-page').disabled = !validPage
  el('probe-list').disabled = !validPage
  el('batch-links').hidden = pageLinks.length < 2
  el('batch-links').textContent = '↥ 批量推送 · ' + pageLinks.length
  el('page-link-count').hidden = pageLinks.length < 2
  el('page-link-count').textContent = '115 分享／磁力／ED2K：' + pageLinks.length + ' 个，已按内容去重'
  const select = el('p115-link-select'); select.replaceChildren()
  for (const item of pageLinks) {
    const option = document.createElement('option'); option.value = item.key; option.textContent = item.label + ' · ' + truncate(item.title || item.link, 50); select.append(option)
  }
  select.value = detected115.key || ''
  el('p115-link-field').hidden = pageLinks.length < 2
  renderFormatOptions(); renderPush115()
}

function renderBulk() {
  const host = el('bulk-list'); host.replaceChildren()
  for (const item of batchLinks) {
    const row = document.createElement('div'); row.className = 'resource-row'
    const check = document.createElement('input'); check.type = 'checkbox'; check.checked = bulkSelected.has(item.key); check.disabled = bulkRunning
    check.setAttribute('aria-label', '选择 ' + item.label)
    check.addEventListener('change', () => { if (check.checked) bulkSelected.add(item.key); else bulkSelected.delete(item.key) })
    const text = document.createElement('span'); text.className = 'grow small'; text.textContent = item.label + ' · ' + (item.title || item.link); text.title = item.link
    const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = '删除'; remove.className = 'ghost tiny'; remove.disabled = bulkRunning
    remove.addEventListener('click', () => { batchLinks = batchLinks.filter(link => link.key !== item.key); bulkSelected.delete(item.key); renderBulk() })
    row.append(check, text, remove); host.append(row)
  }
  for (const id of ['bulk-select-all','bulk-unselect','bulk-delete','bulk-push-selected','bulk-push-all']) el(id).disabled = bulkRunning || !batchLinks.length
}

async function pushBulk(all) {
  if (bulkRunning) return
  const items = batchLinks.filter(item => all || bulkSelected.has(item.key))
  if (!items.length) { toast('请先选择要推送的链接'); return }
  const account = currentAccount()
  bulkRunning = true; renderBulk()
  const node = el('bulk-status'); node.hidden = false; node.textContent = '正在提交…'
  const submitted = await send({ type: 'push115Batch', links: items.map(item => item.link), targets: { accountMode: account.mode, accountId: account.id, shareCid: push115.shareCid, offlineCid: push115.offlineCid } })
  if (!submitted.ok) { node.textContent = submitted.message || '批量推送失败'; bulkRunning = false; renderBulk(); return }
  while (true) {
    const result = await send({ type: 'batch115State', batchId: submitted.batchId })
    const batch = result.batch
    if (!result.ok || !batch) break
    const accepted = batch.results.filter(item => item.ok && !item.duplicate).length
    const duplicates = batch.results.filter(item => item.ok && item.duplicate).length
    const errors = batch.results.filter(item => !item.ok)
    node.textContent = `已处理 ${batch.cursor}/${batch.total} · 已提交 ${accepted} · 已存在 ${duplicates} · 失败 ${errors.length}` + (batch.message ? '\n' + batch.message : '') + (errors.length ? '\n' + errors.map(item => item.message || '推送失败').join('；') : '')
    if (batch.status !== 'running') break
    await new Promise(resolve => setTimeout(resolve, 1000))
  }
  bulkRunning = false; renderBulk()
}

el('batch-links').addEventListener('click', () => { if (!bulkRunning) { batchLinks = [...pageLinks]; bulkSelected.clear(); renderBulk() } el('bulk-card').hidden = false })
el('bulk-close').addEventListener('click', () => { el('bulk-card').hidden = true })
el('bulk-select-all').addEventListener('click', () => { for (const item of batchLinks) bulkSelected.add(item.key); renderBulk() })
el('bulk-unselect').addEventListener('click', () => { bulkSelected.clear(); renderBulk() })
el('bulk-delete').addEventListener('click', () => { batchLinks = batchLinks.filter(item => !bulkSelected.has(item.key)); bulkSelected.clear(); renderBulk() })
el('bulk-push-selected').addEventListener('click', () => void pushBulk(false))
el('bulk-push-all').addEventListener('click', () => void pushBulk(true))
el('p115-link-select').addEventListener('change', () => { detected115 = pageLinks.find(item => item.key === el('p115-link-select').value) || detected115; renderPush115() })

// ----------------------------------------------------- 115 转存 / 离线

// 115 的账号与目录默认值单独保存，完全不碰页面推送用的 settings。
let push115 = { ...PUSH115_DEFAULTS }
let accounts115 = []
let detected115 = { kind: 'unknown', link: '', label: '' }
let browse115 = { kind: 'share', stack: [{ cid: '0', name: '115 根目录' }] }
let push115Polling = null
let dirRequest = 0

function accountKey(account) {
  return `${account.mode || 'main'}:${Number(account.id) || 0}`
}

function currentAccount() {
  const key = el('p115-account') ? el('p115-account').value : ''
  return accounts115.find((item) => accountKey(item) === key) || { mode: 'main', id: 0, name: '' }
}

function setStatus(text, kind) {
  const node = el('p115-status')
  if (!node) return
  if (!text) { node.hidden = true; node.textContent = ''; return }
  node.hidden = false
  node.textContent = text
  node.style.color = kind === 'ok' ? 'var(--ok)' : (kind === 'bad' ? 'var(--danger)' : '')
}

function renderPush115() {
  el('card-115').hidden = !isExternalPushKind(detected115.kind) && !pageLinks.length
  const kindNode = el('p115-kind')
  const linkNode = el('p115-link')
  if (kindNode) {
    const labels = { share115: '115 分享', magnet: '磁力', ed2k: 'ED2K', video: '视频页面', unknown: '未识别' }
    kindNode.textContent = labels[detected115.kind] || '未识别'
    kindNode.className = 'tag ' + (detected115.kind === 'unknown' || detected115.kind === 'video' ? '' : 'ok')
  }
  if (linkNode) {
    linkNode.textContent = detected115.link
      ? detected115.link
      : '当前页面不是 115 分享 / 磁力 / ED2K 链接（可右键链接或选中文字推送）'
  }
  const shareName = el('p115-share-name')
  const offlineName = el('p115-offline-name')
  if (shareName) shareName.textContent = push115.shareCid ? (push115.shareName || ('CID ' + push115.shareCid)) : '未选择'
  if (offlineName) offlineName.textContent = push115.offlineCid ? (push115.offlineName || ('CID ' + push115.offlineCid)) : '未选择'
}

function fillAccounts(defaultAccount) {
  const select = el('p115-account')
  if (!select) return
  select.innerHTML = ''
  if (!accounts115.length) {
    const option = document.createElement('option')
    option.value = ''
    option.textContent = '没有可用的 115 账号'
    select.appendChild(option)
    return
  }
  for (const account of accounts115) {
    const option = document.createElement('option')
    option.value = accountKey(account)
    const suffix = account.mode === 'backup' ? '（备用号）' : '（主账号）'
    option.textContent = `${account.name || account.user_name || '未命名账号'}${suffix}${account.cookie_valid === false ? ' · CK 失效' : ''}`
    select.appendChild(option)
  }
  const preferred = push115.accountId
    ? accountKey({ mode: push115.accountMode, id: push115.accountId })
    : (defaultAccount ? accountKey(defaultAccount) : '')
  const fallback = accountKey(accounts115[0])
  select.value = accounts115.some((item) => accountKey(item) === preferred) ? preferred : fallback
}

async function load115() {
  const stored = await chrome.storage.local.get('push115')
  push115 = { ...PUSH115_DEFAULTS, ...(stored && stored.push115 ? stored.push115 : {}) }
  const response = await send({ type: 'accounts115' })
  accounts115 = response && response.ok && Array.isArray(response.accounts) ? response.accounts : []
  fillAccounts(response && response.defaultAccount)
  if (push115.accountId && accountKey(currentAccount()) !== accountKey({ mode: push115.accountMode, id: push115.accountId })) {
    push115.shareCid = ''; push115.shareName = ''
    push115.offlineCid = ''; push115.offlineName = ''
    setStatus('原账号已不可用，请为当前账号重新选择目录。', 'bad')
  }
  if (!accounts115.length) setStatus(response && response.message ? response.message : '读不到 115 账号，请先在 DIAN115 的账号配置里添加并启用。', 'bad')
  renderPush115()
}

function renderDirList(dirs) {
  const host = el('p115-dirs')
  if (!host) return
  host.innerHTML = ''
  if (!dirs.length) {
    host.innerHTML = '<div class="muted">这里没有子目录</div>'
    return
  }
  for (const dir of dirs) {
    const button = document.createElement('button')
    button.className = 'ghost tiny'
    button.style.display = 'block'
    button.style.width = '100%'
    button.style.textAlign = 'left'
    button.textContent = '📁 ' + dir.name
    button.addEventListener('click', () => {
      browse115.stack.push({ cid: dir.cid, name: dir.name })
      void loadDirs115()
    })
    host.appendChild(button)
  }
}

async function loadDirs115() {
  const request = ++dirRequest
  const account = currentAccount()
  const current = browse115.stack[browse115.stack.length - 1]
  el('p115-path').textContent = browse115.stack.map((item) => item.name).join(' / ')
  el('p115-dirs').innerHTML = '<div class="muted">正在读取…</div>'
  const res = await send({ type: 'dirs115', cid: current.cid, accountMode: account.mode, accountId: account.id })
  if (request !== dirRequest) return
  if (!res || !res.ok) {
    el('p115-dirs').innerHTML = '<div class="muted">' + escapeHtml((res && res.message) || '读取目录失败') + '</div>'
    return
  }
  renderDirList(res.dirs || [])
}

function openBrowser115(kind) {
  browse115 = { kind, stack: [{ cid: '0', name: '115 根目录' }] }
  el('p115-browser').hidden = false
  void loadDirs115()
}

async function pushLink115() {
  if (detected115.kind !== 'share115' && detected115.kind !== 'magnet' && detected115.kind !== 'ed2k') {
    setStatus('当前页面没有识别到 115 分享 / 磁力 / ED2K 链接。', 'bad')
    return
  }
  const account = currentAccount()
  const isShare = detected115.kind === 'share115'
  const targetCid = isShare ? push115.shareCid : push115.offlineCid
  if (!targetCid) {
    setStatus('请先选择' + (isShare ? '转存' : '离线') + '目录。', 'bad')
    return
  }
  setStatus('正在提交…')
  const res = await send({
    type: 'push115',
    link: detected115.link,
    targetCid,
    accountMode: account.mode,
    accountId: account.id,
  })
  if (!res || !res.ok) {
    setStatus((res && res.message) || '推送失败', 'bad')
    return
  }
  setStatus(res.duplicate ? '已存在，未重复创建；正在读取结果…' : '已提交，正在等待 115 处理…')
  if (push115Polling) clearInterval(push115Polling)
  let attempts = 0
  push115Polling = setInterval(async () => {
    attempts += 1
    const status = await send({ type: 'push115Status', requestId: res.requestId })
    const record = (status && status.record) || {}
    if (record.status === 'succeeded') {
      clearInterval(push115Polling); push115Polling = null
      setStatus('已完成：' + (record.target_path || record.link_display || ''), 'ok')
      return
    }
    if (record.status === 'failed' || record.status === 'rejected') {
      clearInterval(push115Polling); push115Polling = null
      setStatus(record.error_message || record.error_code || '115 处理失败', 'bad')
      return
    }
    if (attempts >= 20) {
      clearInterval(push115Polling); push115Polling = null
      setStatus('已提交，仍在处理中，可稍后在 DIAN115 里查看结果。')
    }
  }, 3000)
}

el('p115-account').addEventListener('change', () => {
  push115.shareCid = ''; push115.shareName = ''
  push115.offlineCid = ''; push115.offlineName = ''
  browse115.stack = [{ cid: '0', name: '115 根目录' }]
  renderPush115()
  if (!el('p115-browser').hidden) void loadDirs115()
})
el('p115-share-browse').addEventListener('click', () => openBrowser115('share'))
el('p115-offline-browse').addEventListener('click', () => openBrowser115('offline'))
el('p115-up').addEventListener('click', () => {
  if (browse115.stack.length > 1) {
    browse115.stack.pop()
    void loadDirs115()
  }
})
el('p115-close').addEventListener('click', () => { el('p115-browser').hidden = true })
el('p115-choose').addEventListener('click', () => {
  const current = browse115.stack[browse115.stack.length - 1]
  if (String(current.cid) === '0') {
    setStatus('请选择根目录下的具体目录。', 'bad')
    return
  }
  if (browse115.kind === 'share') {
    push115.shareCid = String(current.cid)
    push115.shareName = current.name
  } else {
    push115.offlineCid = String(current.cid)
    push115.offlineName = current.name
  }
  el('p115-browser').hidden = true
  renderPush115()
  setStatus('已选择「' + current.name + '」，点「保存为默认」后下次推送会沿用。')
})
el('p115-push').addEventListener('click', () => void pushLink115())
el('p115-save').addEventListener('click', async () => {
  const account = currentAccount()
  const res = await send({
    type: 'save115Defaults',
    push115: {
      accountMode: account.mode,
      accountId: Number(account.id) || 0,
      accountName: account.name || '',
      shareCid: push115.shareCid || '',
      shareName: push115.shareName || '',
      offlineCid: push115.offlineCid || '',
      offlineName: push115.offlineName || '',
    },
  })
  const saved = (res && res.push115) || push115
  push115 = { ...PUSH115_DEFAULTS, ...saved }
  renderPush115()
  setStatus('已保存为默认（不影响页面推送的下载配置）。', 'ok')
})

void (async () => {
  await loadTab()
  await loadPageLinks()
  renderPush115()
  if (!el('card-115').hidden) await load115()
  void loadState()
})()
setInterval(() => void send({ type: 'refresh' }).then(() => loadState()), 5000)
