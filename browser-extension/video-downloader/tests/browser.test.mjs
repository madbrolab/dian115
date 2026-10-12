import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { pathToFileURL } from 'node:url'
import test from 'node:test'

// Optional browser QA: provide an installed Playwright module and Chromium.
// No live server or credentials are used; all chrome APIs and pages are fixtures.
const modulePath = process.env.DIAN115_PLAYWRIGHT_MODULE
const chromium = modulePath ? (await import(pathToFileURL(modulePath))).chromium : null
const source = name => readFile(new URL('../' + name, import.meta.url), 'utf8')
const hash = '0123456789abcdef0123456789abcdef01234567'
const ed = '1234567890abcdef1234567890abcdef'
const resources = ['https://115.com/s/abc123?password=a1b2', `magnet:?xt=urn:btih:${hash}`, `ed2k://|file|a.mkv|100|${ed}|/`]

async function launch() {
  return chromium.launch({ headless: true, ...(process.env.DIAN115_CHROMIUM_PATH ? { executablePath: process.env.DIAN115_CHROMIUM_PATH } : {}) })
}

async function mock(page, config = {}) {
  await page.addInitScript(config => {
    // Inspection only: production shadows remain closed.
    const attach = Element.prototype.attachShadow
    Element.prototype.attachShadow = function (options) { return attach.call(this, { ...options, mode: 'open' }) }
    window.__messages = []
    window.__settingsChanged = null
    window.__incoming = null
    const state = { settings: { mode: 'video', pageOverlay: config.enabled !== false }, push115: { accountMode: 'main', accountId: 1, shareCid: '123', offlineCid: '567' } }
    window.chrome = {
      storage: {
        local: { get: async key => ({ [key]: state[key] }), set: async patch => Object.assign(state, patch) },
        onChanged: { addListener: fn => { window.__settingsChanged = fn } },
      },
      runtime: {
        onMessage: { addListener: fn => { window.__incoming = fn } },
        openOptionsPage: () => {},
        sendMessage: (message, callback) => {
          window.__messages.push(message)
          let result = { ok: true }
          if (message.type === 'overlayState') result.enabled = config.enabled !== false
          if (message.type === 'state') Object.assign(result, { configured: true, settings: state.settings, tracked: [] })
          if (message.type === 'accounts115') Object.assign(result, { accounts: [{ mode: 'main', id: 1, name: '测试账号' }] })
          if (message.type === 'push115Batch') result.batchId = 'fixture-batch'
          if (message.type === 'batch115State') result.batch = { id: 'fixture-batch', status: 'completed', total: 3, cursor: 3, results: [] }
          if (message.type === 'push115') { result.ok = !window.__failPush; result.message = window.__failPush ? '提交失败' : ''; result.requestId = 'fixture' }
          if (message.type === 'preview') Object.assign(result, { preview: { title: '测试视频', total_items: 1, formats: [], warning: '需要站点登录态' }, probe: 'list' })
          queueMicrotask(() => callback(result))
        },
      },
      tabs: {
        query: async () => [{ id: 1, url: config.tabURL || 'https://www.bilibili.com/video/BV1wDhj6wEa8/', title: '测试页面' }],
        sendMessage: (_tabId, _message, callback) => callback({ ok: true, links: config.links || [] }),
      },
    }
  }, config)
}

test('page overlays deduplicate resources, preserve text and support dynamic links and batch deletion', { skip: !chromium }, async () => {
  const browser = await launch()
  try {
    const page = await browser.newPage()
    const errors = []; page.on('pageerror', error => errors.push(error.message))
    await mock(page)
    await page.route('https://fixture.test/**', route => route.fulfill({ contentType: 'text/html; charset=utf-8', body: `<!doctype html><meta charset="utf-8"><body>
      <p><a id="share" href="https://115.com/s/abc123">分享</a> 提取码：a1b2</p>
      <p><a href="https://115cdn.com/s/abc123">重复分享</a></p>
      <p><a href="${resources[1]}">磁力</a> ${resources[1]}&dn=duplicate</p>
      <p id="ed">电驴 ${resources[2]} 和 ed2k://|file|b.mkv|100|${ed.toUpperCase()}|/</p>
      <a href="https://115.com/login">登录页</a></body>` }))
    await page.goto('https://fixture.test/watch')
    const original = await page.locator('body').textContent()
    await page.addScriptTag({ content: await source('src/links.js') })
    await page.addScriptTag({ content: await source('src/content.js') })
    await page.waitForFunction(() => document.querySelectorAll('[data-dian115-overlay]').length === 4)
    assert.equal(await page.locator('.inline').count(), 3)
    const items = await page.evaluate(() => window.__dian115PageLinks.scan())
    assert.equal(items.length, 3)
    assert.equal(items[0].link, resources[0])
    assert.equal(await page.locator('body').textContent(), original)
    const textCount = () => page.evaluate(() => { const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT); let n = 0; while (w.nextNode()) n++; return n })
    const before = await textCount()
    await page.evaluate(() => { for (let i = 0; i < 10; i++) window.__dian115PageLinks.scan() })
    assert.equal(await textCount(), before)
    await page.locator('#share + [data-dian115-overlay] button').click()
    await page.waitForFunction(() => window.__messages.some(message => message.type === 'push115'))
    assert.equal((await page.evaluate(() => window.__messages.find(message => message.type === 'push115'))).link, resources[0])
    await page.locator('#share + [data-dian115-overlay] button').click()
    assert.equal((await page.evaluate(() => window.__messages.filter(message => message.type === 'push115'))).length, 2)
    await page.evaluate(() => { window.__failPush = true })
    await page.locator('#share + [data-dian115-overlay] button').click()
    await page.waitForFunction(() => Array.from(document.querySelectorAll('[data-dian115-overlay]')).some(host => host.shadowRoot?.querySelector('.inline')?.textContent === '!'))
    await page.evaluate(() => { document.querySelector('#share').after(document.createTextNode(' https://115.com/s/new111 ')) })
    await page.waitForFunction(() => document.querySelectorAll('[data-dian115-overlay]').length >= 5 && window.__dian115PageLinks.scan().length === 4)
    assert.equal(await page.locator('.inline').count(), 4)
    await page.getByRole('button', { name: /批量推送/ }).click()
    assert.equal(await page.locator('.item').count(), 4)
    await page.locator('.item input').first().check()
    await page.getByRole('button', { name: '删除选中', exact: true }).click()
    assert.equal(await page.locator('.item').count(), 3)
    await page.getByRole('button', { name: '全选', exact: true }).click()
    await page.getByRole('button', { name: '删除选中', exact: true }).click()
    assert.equal(await page.locator('.item').count(), 0)
    assert.equal(await page.locator('a').count(), 4)
    await page.getByRole('button', { name: '恢复列表', exact: true }).click()
    assert.equal(await page.locator('.item').count(), 4)
    await page.locator('.item').first().getByRole('button', { name: '删除', exact: true }).click()
    await page.getByRole('button', { name: '一键推送全部', exact: true }).click()
    await page.waitForFunction(() => window.__messages.some(message => message.type === 'push115Batch'))
    const batch = await page.evaluate(() => window.__messages.find(message => message.type === 'push115Batch'))
    assert.equal(batch.links.length, 3)
    assert.equal(new Set(batch.links).size, 3)
    await page.evaluate(() => window.__settingsChanged({ settings: { newValue: { pageOverlay: false } } }, 'local'))
    assert.equal(await page.locator('[data-dian115-overlay]').count(), 0)
    assert.equal((await page.evaluate(() => window.__dian115PageLinks.scan(false))).length, 4)
    await page.evaluate(() => window.__settingsChanged({ settings: { newValue: { pageOverlay: true } } }, 'local'))
    assert.equal(await page.locator('.inline').count(), 4)
    assert.deepEqual(errors, [])
  } finally { await browser.close() }
})

test('popup hides 115 on ordinary video pages and exposes a unique batch list in the format area', { skip: !chromium }, async () => {
  const browser = await launch()
  try {
    const checks = [[], resources.map((link, i) => ({ link, kind: ['share115', 'magnet', 'ed2k'][i], key: 'fixture:' + i, label: ['115 分享', '磁力', 'ED2K'][i] }))]
    for (const links of checks) {
      const page = await browser.newPage({ viewport: { width: 400, height: 900 } })
      const errors = []; page.on('pageerror', error => errors.push(error.message))
      await mock(page, { links })
      await page.route('http://extension.test/**', async route => {
        const name = new URL(route.request().url()).pathname.slice(1)
        await route.fulfill({ contentType: name.endsWith('.js') ? 'text/javascript' : name.endsWith('.css') ? 'text/css' : 'text/html', body: await source(name) })
      })
      await page.goto('http://extension.test/src/popup.html')
      await page.waitForFunction(() => document.querySelector('#page-title').textContent === '测试页面')
      await page.waitForFunction(() => window.__messages.some(message => message.type === 'state'))
      assert.equal(await page.locator('#card-115').isVisible(), links.length > 0)
      assert.equal(await page.locator('#format-card').isVisible(), links.length > 1)
      assert.equal(await page.locator('#video-controls').isVisible(), true)
      if (links.length) {
        await page.locator('#batch-links').click()
        assert.equal(await page.locator('#bulk-list .resource-row').count(), 3)
        await page.locator('#bulk-list input').first().check()
        await page.locator('#bulk-delete').click()
        assert.equal(await page.locator('#bulk-list .resource-row').count(), 2)
        await page.locator('#bulk-select-all').click()
        await page.locator('#bulk-push-selected').click()
        await page.waitForFunction(() => window.__messages.some(message => message.type === 'push115Batch'))
        const batch = await page.evaluate(() => window.__messages.find(message => message.type === 'push115Batch'))
        assert.equal(batch.links.length, 2)
        assert.equal(batch.targets.accountId, 1)
        assert.equal(batch.targets.offlineCid, '567')
      } else {
        await page.locator('#probe-list').click()
        await page.waitForFunction(() => !document.querySelector('#preview-card').hidden)
        assert.match(await page.locator('#preview-source').textContent(), /需要站点登录态/)
      }
      assert.deepEqual(errors, [])
      await page.close()
    }
  } finally { await browser.close() }
})
