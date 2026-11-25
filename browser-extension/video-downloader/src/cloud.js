import { loadSettings, normalizeBaseUrl } from './common.js'

export const cloudAlarm = 'dian115-site-sync'
const snapshotDomain = '@snapshot-v3'
const initial = () => ({ base: '', auto: false, minutes: 10, keywords: '', blacklist: '', revision: 0 })
let database
let run
let currentRequest

function openDatabase() {
  if (!database) database = new Promise((resolve, reject) => {
    const req = indexedDB.open('dian115-site-pairs', 3)
    req.onupgradeneeded = event => {
      if (!event.oldVersion) { req.result.createObjectStore('config'); return }
      const store = req.transaction.objectStore('config')
      const old = store.get('sync')
      old.onsuccess = () => {
        // The old opt-in covered selected sites. Start the expanded scope paused.
        store.put({ ...initial(), minutes: old.result?.minutes || 10 }, 'sync')
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => { database = undefined; reject(req.error) }
  })
  return database
}

async function config(edit) {
  const db = await openDatabase()
  return new Promise((resolve, reject) => {
    const tx = db.transaction('config', edit ? 'readwrite' : 'readonly')
    const store = tx.objectStore('config')
    const req = store.get('sync')
    let value
    req.onsuccess = () => {
      value = req.result || initial()
      if (edit) { edit(value); store.put(value, 'sync') }
    }
    tx.oncomplete = () => resolve(value)
    tx.onabort = () => reject(tx.error || new Error('无法保存同步设置'))
    tx.onerror = () => reject(tx.error)
  })
}

export async function scheduleCloud() {
  const state = await config()
  const connection = await loadSettings()
  if (!state.auto || !connection.apiKey || state.base !== normalizeBaseUrl(connection.baseUrl)) {
    await chrome.alarms.clear(cloudAlarm)
    return
  }
  if ((await chrome.alarms.get(cloudAlarm))?.periodInMinutes !== state.minutes) {
    await chrome.alarms.create(cloudAlarm, { periodInMinutes: state.minutes, delayInMinutes: state.minutes })
  }
}

export async function forgetCloudTarget(oldBase) {
  const base = normalizeBaseUrl(oldBase)
  if (currentRequest?.base === base) currentRequest.controller.abort()
  await config(state => {
    if (state.base !== base) return
    state.auto = false
    state.base = ''
    state.revision++
    delete state.result
  })
  await scheduleCloud()
}

const encoder = new TextEncoder()
async function uploadKey(apiKey) {
  const secret = await crypto.subtle.importKey('raw', encoder.encode(apiKey), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign'])
  const bytes = await crypto.subtle.sign('HMAC', secret, encoder.encode('dian115-cookiecloud-upload-v2\0' + snapshotDomain))
  return crypto.subtle.importKey('raw', bytes, 'AES-GCM', false, ['encrypt'])
}

function base64(data) {
  let result = ''
  for (let i = 0; i < data.length; i += 8192) result += String.fromCharCode(...data.subarray(i, i + 8192))
  return btoa(result)
}

async function transmit(base, key, body, signal) {
  const nonce = crypto.getRandomValues(new Uint8Array(12))
  const receipt = crypto.randomUUID().replaceAll('-', '')
  const plain = encoder.encode(JSON.stringify({ ...body, at: Date.now(), receipt }))
  if (plain.length > 8 * 1024 * 1024) throw new Error('同步数据超过 8 MiB，请缩小域名范围')
  const encrypted = await crypto.subtle.encrypt({ name: 'AES-GCM', iv: nonce, additionalData: encoder.encode(snapshotDomain) }, key, plain)
  const response = await fetch(base + '/cookiecloud/browser-sync', {
    method: 'POST', redirect: 'error', credentials: 'omit', cache: 'no-store', referrerPolicy: 'no-referrer',
    headers: { 'Content-Type': 'application/json' }, signal,
    body: JSON.stringify({ domain: snapshotDomain, nonce: base64(nonce), data: base64(new Uint8Array(encrypted)) }),
  })
  const result = await response.json().catch(() => null)
  if (!response.ok) {
    if (response.status === 401) throw new Error('请在「连接」核对 OpenAPI Key')
    if (response.status === 404 || response.status === 400) throw new Error('请更新 DIAN115 主程序，并检查浏览器时间')
    if (response.status === 409) throw new Error(result?.message || '服务器数据已更新，请重试')
    throw new Error('服务器未接收（HTTP ' + response.status + '）')
  }
  if (result?.receipt !== receipt || result.received !== (body.cookies?.length || 0)) throw new Error('服务器回执无效')
}

function lines(value) {
  return value.split('\n').map(word => word.trim()).filter(Boolean)
}

async function readCookies(state) {
  let rows
  try { rows = await chrome.cookies.getAll({ partitionKey: {} }) }
  catch (err) {
    // Chrome versions before 119 do not expose partitionKey.
    if (!/Unexpected property.*partitionKey/i.test(err.message)) throw err
    rows = await chrome.cookies.getAll({})
  }
  const keywords = lines(state.keywords)
  const blacklist = lines(state.blacklist)
  return rows.filter(cookie => cookie.domain && (keywords.length
    ? keywords.some(word => cookie.domain.includes(word))
    : !blacklist.some(word => cookie.domain.includes(word))))
}

async function syncSnapshot(scheduled) {
  const [state, connection] = await Promise.all([config(), loadSettings()])
  const base = normalizeBaseUrl(connection.baseUrl)
  if (!base || !connection.apiKey || state.base !== base || (scheduled && !state.auto)) return
  const controller = new AbortController()
  currentRequest = { base, scheduled, controller }
  const timer = setTimeout(() => controller.abort(), 25000)
  const allowed = async () => {
    const [latest, settings] = await Promise.all([config(), loadSettings()])
    return !controller.signal.aborted && latest.revision === state.revision && latest.base === base
      && (!scheduled || latest.auto) && normalizeBaseUrl(settings.baseUrl) === base && settings.apiKey === connection.apiKey
  }
  let result
  try {
    const key = await uploadKey(connection.apiKey)
    await transmit(base, key, { probe: true }, controller.signal)
    if (!await allowed()) return
    const cookies = await readCookies(state)
    if (!await allowed()) return
    await transmit(base, key, { cookies }, controller.signal)
    result = { outcome: 'ok', count: cookies.length, domains: new Set(cookies.map(c => c.domain)).size, note: '同步完成' }
  } catch (err) {
    result = { outcome: 'error', note: controller.signal.aborted ? '同步已中断' : err instanceof TypeError ? '无法连接服务器' : err.message || '同步失败' }
  } finally { clearTimeout(timer); currentRequest = undefined }
  await config(saved => {
    if (saved.base === base && saved.revision === state.revision) saved.result = { ...result, last: Date.now() }
  })
}

export function syncCloud(scheduled = true) {
  if (!run) run = syncSnapshot(scheduled).finally(() => { run = undefined })
  return run
}

export async function cloudAction(message, sender) {
  const page = sender.url?.split(/[?#]/)[0]
  const options = page === chrome.runtime.getURL('src/options.html')
  const popup = page === chrome.runtime.getURL('src/popup.html')
  if (sender.id !== chrome.runtime.id || (!options && !popup)) throw new Error('请从扩展打开 CookieCloud')
  const connection = await loadSettings()
  const base = normalizeBaseUrl(connection.baseUrl)
  const configured = !!base && !!connection.apiKey
  const action = message.action
  if (action !== 'state') {
    if (!configured) throw new Error('请在「连接」保存服务器地址和 OpenAPI Key')
    if (base !== message.base) throw new Error('服务器地址已变更，请重新打开')
  }
  if (action === 'sync') {
    await config(state => { state.base = base })
    await syncCloud(false)
  } else if (action === 'save' && options) {
    if (!Number.isSafeInteger(message.minutes) || message.minutes < 1) throw new Error('同步间隔至少 1 分钟')
    if (typeof message.keywords !== 'string' || typeof message.blacklist !== 'string') throw new Error('域名筛选格式无效')
    currentRequest?.controller.abort()
    await config(state => {
      state.base = base
      state.auto = message.auto === true
      state.minutes = message.minutes
      state.keywords = message.keywords.trim()
      state.blacklist = message.blacklist.trim()
      state.revision++
    })
    await scheduleCloud()
  } else if (action !== 'state') throw new Error('操作无效')
  const state = await config()
  return { ok: true, ...state, base, configured, auto: configured && state.base === base && state.auto, result: state.base === base ? state.result : undefined }
}
