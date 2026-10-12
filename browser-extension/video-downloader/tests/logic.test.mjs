import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import vm from 'node:vm'
import test from 'node:test'

const commonSource = await readFile(new URL('../src/common.js', import.meta.url), 'utf8')
const linksSource = await readFile(new URL('../src/links.js', import.meta.url), 'utf8')
const backgroundSource = await readFile(new URL('../src/background.js', import.meta.url), 'utf8')
const copy = value => structuredClone(value)

async function extension(fetchHandler, initial = {}) {
  const state = { settings: { baseUrl: 'https://dian.test', apiKey: 'test-key', notifyOnQueued: false, ...initial.settings }, tracked: [], ...initial }
  const listeners = {}
  const event = name => ({ addListener: fn => { listeners[name] = fn } })
  const requests = []
  const cookieReads = []
  const menuUpdates = []
  const chrome = {
    storage: { local: {
      get: async keys => Object.fromEntries((Array.isArray(keys) ? keys : [keys]).map(key => [key, copy(state[key])])),
      set: async patch => Object.assign(state, copy(patch)),
      remove: async key => { delete state[key] },
    }, onChanged: event('storage') },
    runtime: { id: 'test-extension', onInstalled: event('installed'), onStartup: event('startup'), onMessage: event('message'), getURL: path => path, openOptionsPage: async () => {} },
    alarms: { onAlarm: event('alarm'), clear: async () => {}, create: () => {} },
    contextMenus: { update: (id, options, callback) => { menuUpdates.push({ id, ...options }); callback?.() }, onClicked: event('menu'), removeAll: async () => {}, create: () => {} },
    tabs: { onActivated: event('activated'), onUpdated: event('updated'), get: async () => ({ url: 'https://example.com' }) },
    notifications: { onButtonClicked: event('button'), onClicked: event('notification'), create: async () => {}, clear: async () => {} },
    action: { setBadgeBackgroundColor: async () => {}, setBadgeText: async () => {} },
    cookies: { getAll: async filter => { cookieReads.push(filter); return [{ name: 'SID', value: 'test', domain: '.example.com', path: '/', secure: true, httpOnly: true }] } },
  }
  const context = vm.createContext({ chrome, URL, URLSearchParams, AbortController, setTimeout, clearTimeout, crypto: globalThis.crypto, TextEncoder, fetch: async (url, options) => {
    const request = { url, path: new URL(url).pathname, body: options.body ? JSON.parse(options.body) : null, options }
    requests.push(request)
    const result = await fetchHandler(request)
    return { ok: (result.status || 200) < 400, status: result.status || 200, text: async () => JSON.stringify(result.data || {}) }
  } })
  const common = new vm.SourceTextModule(commonSource, { context })
  const links = new vm.SourceTextModule(linksSource, { context })
  await links.link(() => { throw new Error('unexpected import') })
  await common.link(() => links)
  const background = new vm.SourceTextModule(backgroundSource, { context })
  await background.link(() => common)
  await background.evaluate()
  return { state, requests, cookieReads, menuUpdates, listeners, common: common.namespace, send: (message, sender = {}) => new Promise(resolve => listeners.message(message, sender, resolve)) }
}

const single = request => request.path.endsWith('/quick')
  ? { data: { result: { total_items: 1, queue_free: 100 } } }
  : { data: { result: { accepted: 1, tasks: [{ id: 2, status: 'queued' }] } } }

test('video preflight uses only supported fields and preserves URLs with commas', async () => {
  const app = await extension(single)
  assert.equal((await app.send({ type: 'push', urls: ['https://example.com/video?a=1,2'], probe: 'quick' })).ok, true)
  const preview = app.requests[0]
  assert.deepEqual(Object.keys(preview.body).sort(), ['probe', 'url'])
  assert.equal(preview.body.url, 'https://example.com/video?a=1,2')
  assert.equal(preview.options.redirect, 'error')
  assert.equal(app.cookieReads.length, 0)
})

test('115 push forwards the selected account and target', async () => {
  const app = await extension(() => ({ data: { request_id: 'ep_test' } }))
  const result = await app.send({ type: 'push115', link: 'magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567', targetCid: '567', accountMode: 'backup', accountId: 9 })
  assert.equal(result.ok, true)
  assert.equal(app.requests[0].body.account_mode, 'backup')
  assert.equal(app.requests[0].body.account_id, 9)
  assert.equal(app.requests[0].body.target_cid, '567')
})

test('confirmation freezes mode and destination and keeps the server token', async () => {
  const app = await extension(request => request.path.endsWith('/quick') ? { data: { result: { total_items: 20, queue_free: 100, requires_confirmation: true, confirm_token: 'approved-20' } } } : { data: { result: { accepted: 20, tasks: [] } } }, { settings: { baseUrl: 'https://dian.test', apiKey: 'test-key', mode: 'video', destinationId: 'original' } })
  assert.equal((await app.send({ type: 'push', urls: ['https://example.com/playlist'], probe: 'list' })).pending, true)
  app.state.settings.mode = 'audio'
  app.state.settings.destinationId = 'changed'
  assert.equal((await app.send({ type: 'confirm' })).ok, true)
  const body = app.requests.at(-1).body
  assert.equal(body.mode, 'video')
  assert.equal(body.destination_id, 'original')
  assert.equal(body.confirm_token, 'approved-20')
  assert.equal(body.playlist, true)
})

test('concurrent polling preserves tasks added while the request was in flight', async () => {
  let finishPoll
  let beganPoll
  const began = new Promise(resolve => { beganPoll = resolve })
  const app = await extension(request => {
    if (request.path.endsWith('/tasks/1')) { beganPoll(); return new Promise(resolve => { finishPoll = resolve }) }
    return single(request)
  }, { tracked: [{ id: 1, status: 'queued' }] })
  const refresh = app.send({ type: 'refresh' })
  await began
  await app.send({ type: 'push', urls: ['https://example.com/video'], probe: 'quick' })
  finishPoll({ data: { task: { id: 1, status: 'completed', progress: 100 } } })
  await refresh
  assert.deepEqual(app.state.tracked.map(item => item.id).sort(), [1, 2])
  assert.equal(app.state.tracked.find(item => item.id === 1).status, 'completed')
})

test('clearing records during polling does not restore removed records', async () => {
  let finishPoll
  let beganPoll
  const began = new Promise(resolve => { beganPoll = resolve })
  const app = await extension(() => { beganPoll(); return new Promise(resolve => { finishPoll = resolve }) }, { tracked: [{ id: 1, status: 'queued' }] })
  const refresh = app.send({ type: 'refresh' })
  await began
  await app.send({ type: 'clearTracked' })
  finishPoll({ data: { task: { id: 1, status: 'completed' } } })
  await refresh
  assert.equal(app.state.tracked.length, 0)
})

test('zero accepted tasks is a failure and reports the rejected count', async () => {
  const app = await extension(request => request.path.endsWith('/quick') ? single(request) : { data: { result: { accepted: 0, rejected: 1, tasks: [] } } })
  const result = await app.send({ type: 'push', urls: ['https://example.com/video'], probe: 'quick' })
  assert.equal(result.ok, false)
  assert.equal(result.rejected, 1)
  assert.match(result.message, /没有任务/)
})

test('multiple selected links respect the local confirmation threshold', async () => {
  const app = await extension(single)
  const urls = Array.from({ length: 6 }, (_, i) => 'https://example.com/' + i)
  assert.equal((await app.send({ type: 'push', urls })).pending, true)
  assert.equal(app.requests.length, 0)
  await app.send({ type: 'cancel' })
  assert.equal(app.state.pendingPush, undefined)
  assert.equal(app.requests.length, 0)
})

test('server URL validation rejects embedded credentials, queries and fragments', async () => {
  const app = await extension(single)
  for (const value of ['https://user:password@example.com', 'https://example.com?x=1', 'https://example.com#x', 'https://', 'file:///tmp/file']) assert.equal(app.common.normalizeBaseUrl(value), '')
  assert.equal(app.common.normalizeBaseUrl(' https://example.com/base/// '), 'https://example.com/base')
})

test('an unrelated successful push keeps an earlier pending confirmation', async () => {
  const app = await extension(single)
  await app.send({ type: 'push', urls: Array.from({ length: 6 }, (_, i) => 'https://example.com/' + i) })
  const original = app.state.pendingPush.id
  await app.send({ type: 'push', urls: ['https://example.com/single'], probe: 'quick' })
  assert.equal(app.state.pendingPush.id, original)
})

test('stale confirmation buttons cannot approve a newer push', async () => {
  const app = await extension(single)
  const urls = Array.from({ length: 6 }, (_, i) => 'https://example.com/' + i)
  await app.send({ type: 'push', urls })
  const original = app.state.pendingPush.id
  await app.send({ type: 'push', urls: urls.map(value => value + '/other') })
  assert.equal((await app.send({ type: 'confirm', pendingId: original })).code, 'pending_changed')
  assert.equal(app.requests.length, 0)
})

test('opt-in cookie collection preserves parent-domain and HTTP-only attributes', async () => {
  const app = await extension(request => request.path.endsWith('/cookies') ? { data: { profile: { id: 'site' } } } : single(request), { settings: { baseUrl: 'https://dian.test', apiKey: 'test-key', updateCookies: true } })
  await app.send({ type: 'push', urls: ['https://www.example.com/watch'], probe: 'quick' })
  assert.equal(app.cookieReads.length, 2)
  const cookies = app.requests.find(item => item.path.endsWith('/cookies')).body.cookies
  assert.equal(cookies.length, 1)
  assert.equal(cookies[0].domain, '.example.com')
  assert.equal(cookies[0].httpOnly, true)
  assert.equal(cookies[0].secure, true)
})


test('automatic preflight lets the extractor classify an unhinted Bilibili anthology', async () => {
  const app = await extension(request => request.path.endsWith('/quick') ? { data: { result: { probe: 'list', total_items: 2, items: [{ url: 'https://example.com/1' }, { url: 'https://example.com/2' }], queue_free: 100 } } } : single(request))
  await app.send({ type: 'push', urls: ['https://www.bilibili.com/video/BV1wDhj6wEa8/'] })
  assert.equal(app.requests[0].body.probe, 'list')
  assert.equal(app.requests[1].body.playlist, true)
})

test('preview synchronizes opted-in site cookies before metadata extraction', async () => {
  const app = await extension(request => request.path.endsWith('/cookies') ? { data: { profile: { id: 'bili' } } } : single(request), { settings: { baseUrl: 'https://dian.test', apiKey: 'test-key', updateCookies: true } })
  const result = await app.send({ type: 'preview', url: 'https://www.example.com/watch' })
  assert.equal(result.ok, true)
  assert.ok(app.requests[0].path.endsWith('/cookies'))
  assert.ok(app.requests[1].path.endsWith('/quick'))
  assert.equal(result.cookieSync.ok, true)
})

test('page scripts cannot read settings or API keys', async () => {
  const app = await extension(single)
  const result = await new Promise(resolve => app.listeners.message({ type: 'state' }, { tab: { id: 1 } }, resolve))
  assert.equal(result.code, 'page_operation_denied')
  const overlay = await new Promise(resolve => app.listeners.message({ type: 'overlayState' }, { tab: { id: 1 } }, resolve))
  assert.deepEqual(Object.keys(overlay).sort(), ['enabled', 'ok'])
})

test('client does not suppress a user pushing the same resource again', async () => {
  const app = await extension(() => ({ data: { request_id: 'ep_new' } }), { push115: { accountMode: 'main', accountId: 1, offlineCid: '567' } })
  const message = { type: 'push115', link: 'magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567' }
  await app.send(message)
  await app.send(message)
  assert.equal(app.requests.length, 2)
  assert.notEqual(app.requests[0].options.headers['Idempotency-Key'], app.requests[1].options.headers['Idempotency-Key'])
})

test('batch normalizes duplicate page links once and preserves all distinct resources', async () => {
  const app = await extension(request => ({ data: { request_id: 'ep_' + app.requests.length } }), { push115: { accountMode: 'backup', accountId: 9, shareCid: '123', offlineCid: '567' } })
  const result = await app.send({ type: 'push115Batch', links: ['https://115.com/s/abc123', 'https://115cdn.com/s/abc123?password=a1b2', 'magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567', 'magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567&dn=dup'] })
  assert.equal(result.total, 2)
  for (let i = 0; i < 100 && app.state.batch115.status === 'running'; i++) await new Promise(resolve => setTimeout(resolve, 1))
  assert.equal(app.state.batch115.status, 'completed')
  assert.equal(app.requests.length, 2)
  assert.equal(app.requests[0].body.link, 'https://115.com/s/abc123?password=a1b2')
  assert.equal(app.requests[0].body.target_cid, '123')
  assert.equal(app.requests[1].body.target_cid, '567')
  assert.equal(app.requests[1].body.account_id, 9)
})

test('root target is refused before submission', async () => {
  const app = await extension(single)
  const result = await app.send({ type: 'push115', link: 'https://115.com/s/abc123', targetCid: '0' })
  assert.equal(result.code, 'target_missing')
  assert.equal(app.requests.length, 0)
})

const settleBatch = async app => {
  for (let i = 0; i < 200 && app.state.batch115?.status === 'running'; i++) await new Promise(resolve => setTimeout(resolve, 1))
}

test('an interrupted worker resumes the persisted item with the same idempotency key', async () => {
  let release, began
  const ready = new Promise(resolve => { began = resolve })
  const app = await extension(() => { began(); return new Promise(resolve => { release = resolve }) }, { push115: { accountMode: 'main', accountId: 1, shareCid: '123' } })
  await app.send({ type: 'push115Batch', links: ['https://115.com/s/resume'] })
  await ready
  const resumed = await extension(() => ({ data: { request_id: 'same-request', duplicate: true } }), copy(app.state))
  resumed.listeners.alarm({ name: 'dian115-batch115' })
  await settleBatch(resumed)
  assert.equal(resumed.state.batch115.status, 'completed')
  assert.equal(resumed.requests[0].options.headers['Idempotency-Key'], app.requests[0].options.headers['Idempotency-Key'])
  release({ data: { request_id: 'same-request' } })
  await settleBatch(app)
})

test('a busy batch is refused and server changes stop the remaining submissions', async () => {
  let release, began
  const ready = new Promise(resolve => { began = resolve })
  const app = await extension(() => { began(); return new Promise(resolve => { release = resolve }) }, { push115: { accountMode: 'main', accountId: 1, shareCid: '123' } })
  await app.send({ type: 'push115Batch', links: ['https://115.com/s/one111', 'https://115.com/s/two222'] })
  await ready
  assert.equal((await app.send({ type: 'push115Batch', links: ['https://115.com/s/three3'] })).ok, false)
  app.state.settings.apiKey = 'changed-key'
  release({ data: { request_id: 'first' } })
  await settleBatch(app)
  assert.equal(app.state.batch115.status, 'stopped')
  assert.equal(app.requests.length, 1)
  assert.equal(app.state.batch115.cursor, 1)
})

test('batch failures are recorded without abandoning the remaining links', async () => {
  const app = await extension(request => request.body.link.endsWith('/one111') ? { status: 400, data: { message: '分享已失效' } } : { data: { request_id: 'second' } }, { push115: { accountMode: 'main', accountId: 1, shareCid: '123' } })
  await app.send({ type: 'push115Batch', links: ['https://115.com/s/one111', 'https://115.com/s/two222'] })
  await settleBatch(app)
  assert.deepEqual(app.state.batch115.results.map(item => item.ok), [false, true])
  assert.equal(app.state.batch115.cursor, 2)
})

test('115 context actions ignore background tabs and reset on active video navigation', async () => {
  const app = await extension(single)
  await app.send({ type: 'context115', value: 'https://115.com/s/one111' }, { tab: { id: 1, active: true } })
  assert.equal(app.menuUpdates.at(-1).visible, true)
  app.listeners.updated(2, { url: 'https://example.com/video' }, { active: false })
  assert.equal(app.menuUpdates.at(-1).visible, true)
  await app.listeners.activated({ tabId: 2 })
  assert.equal(app.menuUpdates.at(-1).visible, false)
  await app.send({ type: 'context115', value: 'https://115.com/s/one111' }, { tab: { id: 1, active: false } })
  assert.equal(app.menuUpdates.at(-1).visible, false)
})

test('the next batch starts after previous alarm cleanup even when submitted immediately', async () => {
  const app = await extension(() => ({ data: { request_id: 'new' } }), { push115: { accountMode: 'main', accountId: 1, shareCid: '123' } })
  await app.send({ type: 'push115Batch', links: ['https://115.com/s/first1'] })
  await settleBatch(app)
  assert.equal((await app.send({ type: 'push115Batch', links: ['https://115.com/s/second'] })).ok, true)
  await settleBatch(app)
  assert.equal(app.state.batch115.status, 'completed')
  assert.equal(app.requests.length, 2)
  assert.equal(app.requests.at(-1).body.link, 'https://115.com/s/second')
})
