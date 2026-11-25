import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createHmac, webcrypto } from 'node:crypto'
import { pathToFileURL } from 'node:url'
import test from 'node:test'

const modulePath = process.env.DIAN115_PLAYWRIGHT_MODULE
const chromium = modulePath ? (await import(pathToFileURL(modulePath))).chromium : null

test('all-domain encrypted snapshots, optional filters, scheduling, migration and key rotation', { skip: !chromium }, async () => {
  const browser = await chromium.launch({ headless: true, executablePath: process.env.DIAN115_CHROMIUM_PATH || undefined })
  try {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 }, reducedMotion: 'reduce' })
    const errors = []
    page.on('pageerror', e => errors.push(e.message))
    const domain = '@snapshot-v3'
    const apiKey = 'test-system-api-key'
    const key = createHmac('sha256', apiKey).update('dian115-cookiecloud-upload-v2\0' + domain).digest()
    const aes = await webcrypto.subtle.importKey('raw', key, 'AES-GCM', false, ['decrypt'])
    const packets = []
    let revoked = false
    await page.route('https://dian.test/cookiecloud/browser-sync', async route => {
      const { domain, data, nonce } = route.request().postDataJSON()
      assert.ok(!JSON.stringify(route.request().headers()).includes(apiKey) && !route.request().postData().includes(apiKey))
      assert.equal(domain, '@snapshot-v3')
      if (revoked) { await route.fulfill({ status: 401, json: { code: 'unauthorized' } }); return }
      const plain = await webcrypto.subtle.decrypt({name:'AES-GCM',iv:Buffer.from(nonce,'base64'),additionalData:Buffer.from(domain)}, aes, Buffer.from(data,'base64'))
      const payload = JSON.parse(Buffer.from(plain))
      packets.push(payload)
      await route.fulfill({ json: { received: payload.cookies?.length || 0, receipt: payload.receipt } })
    })
    await page.route('https://extension.test/**', async route => {
      const path = new URL(route.request().url()).pathname
      if (path === '/favicon.ico') return route.fulfill({ status: 404 })
      const type = path.endsWith('js') ? 'text/javascript' : path.endsWith('css') ? 'text/css' : path.endsWith('png') ? 'image/png' : 'text/html'
      await route.fulfill({ contentType: type, body: await readFile(new URL('..' + path, import.meta.url)) })
    })
    await page.addInitScript(() => {
      const rows = [
        { domain: 'media.example.org', path: '/', name: 'theme', value: 'test-choice' },
        { domain: '.example.org', path: '/', name: 'outside', value: 'all-domains' },
        { domain: 'media.example.org', path: '/area', name: 'path', value: 'other-path' },
        { domain: 'media.example.org', path: '/', name: 'partition', partitionKey: {}, value: 'partition' },
      ]
      window.fixture = { rows, legacy: false, lookups: [], alarms: {}, server: 'https://dian.test', key: 'test-system-api-key' }
      const f = window.fixture
      const getURL = path => 'chrome-extension://fixture/' + path
      window.chrome = {
        storage: { local: { get: async k => ({ [k]: k === 'settings' ? { baseUrl: f.server, apiKey: f.key } : undefined }) } },
        tabs: { query: async () => [
          { url: 'https://media.example.org/videos' }, { url: 'https://outside.test/' },
          { url: 'https://incognito.example/', incognito: true }, { url: 'chrome://settings' },
        ] },
        cookies: { getAll: async filter => { f.lookups.push(filter); if (f.legacy && filter.partitionKey) throw new Error("Unexpected property: 'partitionKey'"); return f.rows } },
        alarms: {
          get: async k => f.alarms[k], clear: async k => delete f.alarms[k],
          create: (k, val) => { f.alarms[k] = val },
        },
        runtime: { id: 'fixture', getURL, sendMessage(message, cb) {
          import('/src/cloud.js').then(m => m.cloudAction(message, { id: 'fixture', url: getURL('src/options.html') })).then(cb, e => cb({ ok: false, message: e.message }))
        } },
      }
    })
    await page.goto('https://extension.test/src/options.html#cookiecloud')
    await page.waitForFunction(() => document.querySelector('#cloud-target').textContent.includes('https://dian.test'))
    assert.equal(await page.locator('#cloud-auto').isDisabled(), false)
    assert.equal((await page.evaluate(() => fixture.lookups)).length, 0)
    assert.equal(await page.locator('#cloud-choose').count(), 0)
    await page.locator('#cloud-now').click()
    await page.waitForFunction(() => document.querySelector('#cloud-summary').textContent.includes('4 项 Cookie'))
    assert.equal(packets[0].probe, true)
    assert.deepEqual(packets[1].cookies.map(x => x.name), ['theme', 'outside', 'path', 'partition'])
    assert.deepEqual(await page.evaluate(() => fixture.lookups), [{ partitionKey: {} }])
    await page.locator('#cloud-minutes').fill('0')
    await page.locator('#cloud-save').click()
    assert.equal(await page.locator('#cloud-minutes').evaluate(n => n.validity.rangeUnderflow), true)
    await page.locator('#cloud-minutes').fill('1')
    await page.locator('#cloud-save').click()
    await page.waitForFunction(() => document.querySelector('#cloud-feedback').textContent === '已保存')
    await page.locator('#cloud-auto').check()
    await page.waitForFunction(() => fixture.alarms['dian115-site-sync']?.periodInMinutes === 1)
    const before = packets.length
    await page.evaluate(async () => (await import('/src/cloud.js')).syncCloud())
    assert.equal(packets.length, before + 2)
    assert.equal(packets.at(-1).cookies.length, 4)
    await page.locator('summary').click()
    await page.locator('#cloud-blacklist').fill('media.example')
    await page.locator('#cloud-save').click()
    await page.waitForFunction(() => document.querySelector('#cloud-feedback').textContent === '已保存')
    await page.locator('#cloud-now').click()
    await page.waitForFunction(() => document.querySelector('#cloud-summary').textContent.includes('1 项 Cookie'))
    assert.deepEqual(packets.at(-1).cookies.map(x => x.name), ['outside'])
    // Include keywords take precedence over the exclusion list, matching CookieCloud.
    await page.locator('#cloud-keywords').fill('media.example')
    await page.locator('#cloud-save').click()
    await page.waitForFunction(() => document.querySelector('#cloud-feedback').textContent === '已保存')
    await page.locator('#cloud-now').click()
    await page.waitForFunction(() => document.querySelector('#cloud-summary').textContent.includes('3 项 Cookie'))
    assert.deepEqual(packets.at(-1).cookies.map(x => x.name), ['theme', 'path', 'partition'])
    await page.evaluate(() => { fixture.rows = []; fixture.legacy = true })
    await page.locator('#cloud-now').click()
    await page.waitForFunction(() => document.querySelector('#cloud-summary').textContent.includes('0 项 Cookie'))
    assert.deepEqual(packets.at(-1).cookies, [])
    assert.deepEqual((await page.evaluate(() => fixture.lookups)).slice(-2), [{ partitionKey: {} }, {}])
    assert.equal(await page.locator('.pane:not([hidden])').evaluate(n => getComputedStyle(n).animationName), 'none')
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
    if (process.env.DIAN115_CLOUD_PREVIEW) {
      await page.evaluate(() => { document.querySelector('#cloud-now').blur(); window.scrollTo(0,0) })
      await page.screenshot({ path: process.env.DIAN115_CLOUD_PREVIEW, fullPage: true })
    }
    await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'no-preference' })
    await page.setViewportSize({ width: 680, height: 900 })
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
    await page.reload()
    await page.waitForFunction(() => document.querySelector('#cloud-auto').checked)
    revoked = true
    await page.locator('#cloud-now').click()
    await page.waitForFunction(() => document.querySelector('#cloud-summary').textContent.includes('OpenAPI Key'))
    assert.equal((await page.evaluate(() => fixture.lookups)).length, 0)
    await page.evaluate(async () => {
      const worker = await import('/src/cloud.js')
      try { await worker.cloudAction({ action: 'sync', base: fixture.server }, { id: 'fixture', url: 'https://untrusted.test/' }) } catch { return }
      throw Error('Web sender was accepted')
    })
    await page.evaluate(() => { fixture.server = 'https://changed.test' })
    await page.evaluate(async () => (await import('/src/cloud.js')).syncCloud())
    assert.equal((await page.evaluate(() => fixture.lookups)).length, 0)
    await page.evaluate(async () => (await import('/src/cloud.js')).forgetCloudTarget('https://dian.test'))
    assert.equal(await page.evaluate(() => !!fixture.alarms['dian115-site-sync']), false)
    // Navigate away to release the worker's fixture DB handle before seeding 1.3.0.
    await page.route('https://extension.test/migration', r => r.fulfill({contentType:'text/html',body:'<!doctype html><title>Upgrade fixture</title>'}))
    await page.goto('https://extension.test/migration')
    await page.evaluate(() => new Promise((resolve,reject) => {
      const req = indexedDB.deleteDatabase('dian115-site-pairs')
      req.onsuccess = resolve
      req.onerror = () => reject(req.error)
    }))
    const upgraded = await page.evaluate(async () => {
      // Simulate the previous schema in a fresh origin database after a reload.
      const db = await new Promise((resolve, reject) => {
        const req = indexedDB.open('dian115-site-pairs', 1)
        req.onupgradeneeded = () => req.result.createObjectStore('config')
        req.onsuccess = () => resolve(req.result)
        req.onerror = () => reject(req.error)
      })
      await new Promise(resolve => {
        const tx = db.transaction('config', 'readwrite')
        tx.objectStore('config').put({ auto: true, minutes: 30, sites: [
          { domain: 'media.example.org', id: 'one', base: fixture.server, key: 'obsolete' },
          { domain: 'old.example.org', id: 'two', base: fixture.server, outcome: 'revoked' },
        ] }, 'sync')
        tx.oncomplete = resolve
      })
      db.close()
      const {cloudAction} = await import('/src/cloud.js')
      return cloudAction({action:'state'}, {id:'fixture',url:chrome.runtime.getURL('src/options.html')})
    })
    assert.equal(upgraded.keywords, '')
    assert.equal(upgraded.blacklist, '')
    assert.equal(upgraded.sites, undefined)
    assert.equal(upgraded.auto, false)
    assert.equal(upgraded.minutes, 30)
    assert.deepEqual(errors, [])
  } finally { await browser.close() }
})
