import {
  DEFAULT_SETTINGS,
  PUSH115_DEFAULTS,
  dianFetch,
  fetchVideoDestinations,
  loadPush115,
  loadSettings,
  normalizeBaseUrl,
  savePush115,
  saveSettings,
} from './common.js'

const el = (id) => document.getElementById(id)
const GB = 1024 * 1024 * 1024

function showResult(text, kind) {
  const node = el('test-result')
  node.hidden = false
  node.textContent = text
  node.style.borderColor = kind === 'ok' ? 'var(--ok)' : 'var(--danger)'
  node.style.color = kind === 'ok' ? 'var(--ok)' : 'var(--danger)'
}

function readForm() {
  const confirmGb = Number(el('confirmGb').value || 0)
  return {
    baseUrl: normalizeBaseUrl(el('baseUrl').value),
    apiKey: el('apiKey').value.trim(),
    mode: el('mode').value,
    quality: el('quality').value.trim(),
    destinationId: el('destinationId').value.trim(),
    cookieProfileId: el('cookieProfileId').value.trim(),
    updateCookies: el('updateCookies').checked,
    pageOverlay: el('pageOverlay').checked,
    autoListProbe: el('autoListProbe').checked,
    localConfirmThreshold: Math.max(1, Math.min(100, Number(el('localConfirmThreshold').value || DEFAULT_SETTINGS.localConfirmThreshold))),
    confirmBytes: Math.max(0, confirmGb) * GB,
    pollSeconds: Math.max(60, Math.min(3600, Number(el('pollSeconds').value || DEFAULT_SETTINGS.pollSeconds))),
    notifyOnQueued: el('notifyOnQueued').checked,
    notifyOnComplete: el('notifyOnComplete').checked,
    notifyOnFailed: el('notifyOnFailed').checked,
  }
}

/** 清晰度下拉：旧值不在预设里时回落到「自动」。 */
function fillQualityOptions(value) {
  const select = el('quality')
  const allowed = Array.from(select.options).map((option) => option.value)
  select.value = allowed.includes(String(value || '')) ? String(value || '') : ''
}

function fillForm(settings) {
  el('baseUrl').value = settings.baseUrl || ''
  el('apiKey').value = settings.apiKey || ''
  el('mode').value = settings.mode || 'video'
  fillQualityOptions(settings.quality || '')
  fillDestinationOptions(settings.destinationId || '')
  el('cookieProfileId').value = settings.cookieProfileId || ''
  el('updateCookies').checked = settings.updateCookies === true
  el('pageOverlay').checked = settings.pageOverlay !== false
  el('autoListProbe').checked = settings.autoListProbe !== false
  el('localConfirmThreshold').value = settings.localConfirmThreshold || DEFAULT_SETTINGS.localConfirmThreshold
  el('confirmGb').value = Math.round((Number(settings.confirmBytes || 0) / GB) * 10) / 10
  el('pollSeconds').value = settings.pollSeconds || DEFAULT_SETTINGS.pollSeconds
  el('notifyOnQueued').checked = settings.notifyOnQueued !== false
  el('notifyOnComplete').checked = settings.notifyOnComplete !== false
  el('notifyOnFailed').checked = settings.notifyOnFailed !== false
}

/** 用服务器返回的受控目录填充下拉，避免手输目录 ID。 */
async function loadDestinations(selected) {
  const settings = { ...readForm() }
  const res = await fetchVideoDestinations(settings)
  const select = el('destinationId')
  select.innerHTML = '<option value="">使用服务器默认目录</option>'
  if (res.ok) {
    for (const item of res.destinations) {
      const option = document.createElement('option')
      option.value = item.id
      option.textContent = item.name + (item.free_bytes ? `（剩余 ${Math.round(Number(item.free_bytes) / 1024 / 1024 / 1024 * 10) / 10} GB）` : '')
      select.appendChild(option)
    }
    if (!select.value && res.defaultId) select.value = res.defaultId
  }
  if (selected !== undefined) select.value = selected || ''
  return res
}

function fillDestinationOptions(selected) {
  const select = el('destinationId')
  select.innerHTML = '<option value="">使用服务器默认目录</option>'
  if (selected) {
    const option = document.createElement('option')
    option.value = selected
    option.textContent = selected + '（点「刷新」读取名称）'
    select.appendChild(option)
    select.value = selected
  }
}

async function testConnection() {
  const draft = readForm()
  if (!draft.baseUrl) {
    showResult('请先填写一个 http(s) 服务器地址。', 'bad')
    return
  }
  if (!draft.apiKey) {
    showResult('请先填写 OpenAPI Key。', 'bad')
    return
  }
  // /destinations 同时要求「Key 正确」和「外部 API 已启用」，又不需要任务 id，
  // 所以既不会误报，也不会像 /tasks/0 那样被参数校验挡成 400。
  const res = await dianFetch(draft, '/destinations', { timeoutMs: 20000 })
  if (res.ok) {
    const list = res.data && Array.isArray(res.data.destinations) ? res.data.destinations : []
    showResult(`连接成功：OpenAPI Key 校验已通过，服务器上有 ${list.length} 个受控下载目录。`, 'ok')
    return
  }
  if (res.status === 401) {
    showResult('鉴权失败：OpenAPI Key 不正确，请核对系统设置里的 openapi key。', 'bad')
    return
  }
  if (res.status === 403) {
    if (res.code === 'external_api_disabled') {
      showResult('服务器未启用外部 API，请到“视频下载器 → 外部 API”打开开关。', 'bad')
    } else {
      showResult(res.message || '服务器拒绝了这次请求。', 'bad')
    }
    return
  }
  showResult(res.message || ('连接失败（HTTP ' + res.status + '）'), 'bad')
}

el('save').addEventListener('click', async () => {
  const draft = readForm()
  if (!draft.baseUrl) {
    showResult('服务器地址必须以 http:// 或 https:// 开头。', 'bad')
    return
  }
  await saveSettings(draft)
  showResult('已保存。', 'ok')
})

el('test').addEventListener('click', () => {
  void testConnection()
})

el('refresh-destinations').addEventListener('click', async () => {
  const selected = el('destinationId').value
  const res = await loadDestinations(selected)
  showResult(res.ok ? '已读取服务器上的受控目录。' : (res.message || '读取目录失败'), res.ok ? 'ok' : 'bad')
})

el('clear115').addEventListener('click', async () => {
  await savePush115(PUSH115_DEFAULTS)
  await renderPush115Summary()
  showResult('已清除 115 默认值（页面推送配置不受影响）。', 'ok')
})

async function renderPush115Summary() {
  const push115 = await loadPush115()
  const parts = []
  if (push115.accountName || push115.accountId) parts.push('账号：' + (push115.accountName || ('#' + push115.accountId)))
  if (push115.shareCid) parts.push('转存目录：' + (push115.shareName || push115.shareCid))
  if (push115.offlineCid) parts.push('离线目录：' + (push115.offlineName || push115.offlineCid))
  el('push115-summary').textContent = parts.length ? parts.join('\n') : '未设置（在扩展弹窗里选择并「保存为默认」）'
  el('push115-summary').style.whiteSpace = 'pre-line'
}

void loadSettings().then(async (settings) => {
  fillForm(settings)
  await renderPush115Summary()
  // 有服务器地址与 key 时顺带把目录下拉填满，失败也不打扰用户。
  if (settings.baseUrl && settings.apiKey) void loadDestinations(settings.destinationId || '')
})
