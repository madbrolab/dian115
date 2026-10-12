// Isolated world only: the page never receives the OpenAPI Key or cookies.
(() => {
  if (globalThis.__dian115PageLinks) return
  const links = globalThis.Dian115Links
  const MAX_LINKS = 500
  const ownHosts = new Set()
  const outcomes = new Map()
  const dismissed = new Set()
  const selected = new Set()
  let pageLinks = [], enabled = false, timer = null, toolbar = null, panel = null, batchRunning = false
  let currentURL = location.href, truncated = false
  const styleText = `
    :host { all: initial; color-scheme: light; font: 13px/1.5 system-ui,sans-serif; }
    * { box-sizing: border-box; } [hidden] { display:none !important; }
    button { font:inherit; cursor:pointer; border:1px solid #dce2ec; background:#fff; color:#263248; border-radius:8px; padding:6px 10px; }
    button:hover { background:#edf3ff; } button:disabled { opacity:.55; cursor:wait; }
    .primary { background:#3669ed; color:#fff; border-color:#3669ed; } .primary:hover { background:#2855ce; }
    .inline { display:inline-flex; align-items:center; justify-content:center; width:26px; height:24px; padding:0; margin:0 4px; vertical-align:middle; font-weight:700; }
    .ok { color:#16865c; } .bad { color:#c43c43; } .muted { color:#6b788c; }
    .launcher { box-shadow:0 4px 24px #14294b26; font-weight:600; padding:10px 14px; }
    .panel { width:min(470px,calc(100vw - 32px)); max-height: min(650px,calc(100vh - 40px)); overflow:auto; background:#fff; color:#263248; border:1px solid #dce2ec; border-radius:14px; padding:16px; box-shadow:0 12px 50px #14294b40; }
    .row { display:flex; gap:8px; align-items:center; margin:8px 0; } .between { justify-content:space-between; } .grow { flex:1; min-width:0; }
    h3 { margin:0; font-size:15px; } .items { max-height:340px; overflow:auto; margin:10px 0; }
    .item { display:flex; gap:8px; align-items:flex-start; border-top:1px solid #edf0f5; padding:10px 0; }
    .item input { margin:5px 0; } .name { font-weight:600; } .url { overflow-wrap:anywhere; font-size:11px; color:#6b788c; max-height:34px; overflow:hidden; }
    .status { font-size:12px; margin-top:4px; } .summary { white-space:pre-wrap; padding:8px; border-radius:8px; background:#f3f6fb; }
    .toast { background:#263248; color:#fff; border-radius:10px; padding:10px 14px; box-shadow:0 4px 24px #14294b26; max-width:400px; }
  `
  function host(position) {
    const node = document.createElement('span')
    node.dataset.dian115Overlay = 'true'
    if (position) node.style.cssText = position
    ownHosts.add(node)
    const shadow = node.attachShadow({ mode: 'closed' })
    const css = document.createElement('style'); css.textContent = styleText; shadow.append(css)
    return { node, shadow }
  }
  function button(text, action, className = '') {
    const node = document.createElement('button')
    node.type = 'button'; node.textContent = text; node.className = className
    node.addEventListener('click', event => {
      event.preventDefault(); event.stopPropagation()
      if (event.isTrusted && !node.disabled) void action()
    })
    return node
  }
  function send(message) {
    return new Promise(resolve => {
      try {
        chrome.runtime.sendMessage(message, result => {
          const error = chrome.runtime.lastError
          resolve(error ? { ok: false, message: '扩展已更新或连接中断，请刷新页面后重试' } : (result || { ok: false, message: '扩展没有返回结果' }))
        })
      } catch { resolve({ ok: false, message: '扩展已更新，请刷新页面后重试' }) }
    })
  }
  function toast(text) {
    if (!enabled) return
    const ui = host('position:fixed;right:20px;bottom:72px;z-index:2147483647;')
    const box = document.createElement('div'); box.className = 'toast'; box.textContent = text
    ui.shadow.append(box); document.documentElement.append(ui.node)
    setTimeout(() => { ownHosts.delete(ui.node); ui.node.remove() }, 6000)
  }
  function candidates(anchor) {
    const results = links.extract(anchor.getAttribute('href') || '')
    try {
      const url = new URL(anchor.getAttribute('href') || '', location.href)
      for (const key of ['url', 'target', 'link', 'download', 'u']) results.push(...links.extract(url.searchParams.get(key)))
    } catch {}
    results.push(...links.extract(anchor.textContent || ''))
    const context = links.extract(anchor.parentElement?.textContent || '')
    let tail = ''
    for (let next = anchor.nextSibling; next && tail.length < 80; next = next.nextSibling) {
      if (next.nodeType === Node.ELEMENT_NODE && (next.matches('a') || next.querySelector('a'))) break
      tail += next.textContent || ''
    }
    return links.unique(results.map(item => context.find(other => other.key === item.key && other.link.includes('?password=')) || links.withAdjacentCode(item, tail)))
  }
  function eligible(node) {
    const parent = node.parentElement
    return parent && !parent.closest('a,script,style,noscript,textarea,input,select,button,[contenteditable]:not([contenteditable="false"]),[data-dian115-overlay]')
  }
  function inlineIcon(item) {
    const ui = host()
    const state = outcomes.get(item.key)
    const action = button(state?.busy ? '…' : state?.ok ? '✓' : state ? '!' : '↥', () => pushOne(item), 'inline')
    action.title = item.label + '：推送到 115'
    action.setAttribute('aria-label', action.title)
    action.disabled = state?.busy === true
    if (state) { action.title = state.message; action.classList.add(state.ok ? 'ok' : 'bad') }
    ui.shadow.append(action)
    return ui.node
  }
  function scan(decorate = enabled) {
    observer.disconnect()
    // Remove only our inline decorations. Original links and text are retained.
    for (const node of ownHosts) if (node !== toolbar?.node && node !== panel?.node && !node.style.position) { node.remove(); ownHosts.delete(node) }
    if (currentURL !== location.href) { currentURL = location.href; dismissed.clear(); selected.clear(); outcomes.clear() }
    const found = links.extract(location.href), decorations = []
    let visited = 0; truncated = false
    for (const anchor of document.querySelectorAll('a[href]')) {
      if (++visited > 10000 || found.length >= MAX_LINKS) { truncated = true; break }
      if (anchor.closest('[data-dian115-overlay]') || anchor.isContentEditable) continue
      for (const item of candidates(anchor)) {
        const titled = { ...item, title: (anchor.textContent || '').trim().slice(0, 160) || item.label }
        found.push(titled)
        if (decorate) decorations.push({ anchor, item: titled })
      }
    }
    const texts = []
    if (document.body) {
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
      while (walker.nextNode()) {
        if (++visited > 20000 || found.length >= MAX_LINKS) { truncated = true; break }
        const node = walker.currentNode
        if (!eligible(node) || !/(?:115(?:cdn)?\.com|magnet:\?|ed2k:\/\/)/i.test(node.data)) continue
        const context = links.extract(node.parentElement.textContent || '')
        const items = links.extract(node.data).map(item => {
          const withCode = context.find(other => other.key === item.key && other.link.includes('?password='))
          return withCode ? { ...item, link: withCode.link } : item
        })
        found.push(...items.map(item => ({ ...item, title: item.label })))
        if (items.length && decorate) texts.push({ node, items })
      }
    }
    pageLinks = links.unique(found).slice(0, MAX_LINKS)
    if (decorate) {
      const canonical = new Map(pageLinks.map(item => [item.key, item]))
      const decorated = new Set()
      for (const { anchor, item } of decorations) {
        if (decorated.has(item.key)) continue
        decorated.add(item.key)
        anchor.after(inlineIcon(canonical.get(item.key) || item))
      }
      // Work from right to left to preserve text offsets, even for several URIs
      // in a single node. The URI itself is never rewritten or removed.
      for (const { node, items } of texts) {
        const pending = items.filter(item => {
          if (decorated.has(item.key)) return false
          decorated.add(item.key)
          return true
        })
        for (const item of pending.reverse()) {
          if (item.index + item.length > node.length) continue
          if (item.index + item.length < node.length) node.splitText(item.index + item.length)
          node.after(inlineIcon(canonical.get(item.key) || item))
          if (item.index > 0) node.splitText(item.index)
        }
      }
      renderToolbar()
    }
    if (enabled && document.body) observer.observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ['href'] })
    return pageLinks
  }
  function scheduleScan() {
    if (!enabled) return
    clearTimeout(timer); timer = setTimeout(() => scan(), 250)
  }
  const observer = new MutationObserver(records => {
    if (records.some(record => !record.target.parentElement?.closest('[data-dian115-overlay]') && !ownHosts.has(record.target))) scheduleScan()
  })
  function renderToolbar() {
    toolbar?.node.remove(); if (toolbar) ownHosts.delete(toolbar.node); toolbar = null
    if (!enabled || pageLinks.length < 2) return
    toolbar = host('position:fixed;right:20px;bottom:20px;z-index:2147483646;')
    toolbar.shadow.append(button('↥ 批量推送 · ' + pageLinks.length, () => openPanel(), 'launcher primary'))
    document.documentElement.append(toolbar.node)
  }
  function visibleItems() { return pageLinks.filter(item => !dismissed.has(item.key)) }
  function closePanel() { if (panel) { ownHosts.delete(panel.node); panel.node.remove(); panel = null } }
  function openPanel() {
    if (!enabled) return
    scan()
    if (!panel) {
      panel = host('position:fixed;right:16px;bottom:70px;z-index:2147483647;')
      panel.box = document.createElement('div'); panel.box.className = 'panel'
      panel.box.setAttribute('role', 'dialog'); panel.box.setAttribute('aria-label', '115 链接批量推送')
      panel.shadow.append(panel.box); document.documentElement.append(panel.node)
    }
    renderPanel()
  }
  function renderPanel() {
    if (!panel) return
    const box = panel.box; box.replaceChildren()
    const items = visibleItems()
    const row = document.createElement('div'); row.className = 'row between'
    const title = document.createElement('h3'); title.textContent = '页面资源 · ' + items.length + ' 个（已去重）'
    row.append(title, button('关闭', closePanel)); box.append(row)
    const note = document.createElement('div'); note.className = 'muted'
    note.textContent = '使用扩展保存的账号和转存／离线目录。删除仅移除本次列表。' + (truncated ? ' 页面较大，仅扫描前 500 个候选链接。' : '')
    box.append(note)
    const actions = document.createElement('div'); actions.className = 'row'
    actions.append(button('全选', () => { for (const item of items) selected.add(item.key); renderPanel() }), button('取消选择', () => { selected.clear(); renderPanel() }), button('删除选中', () => { for (const key of selected) dismissed.add(key); selected.clear(); renderPanel() }), button('恢复列表', () => { dismissed.clear(); renderPanel() }))
    for (const action of actions.children) action.disabled = batchRunning
    box.append(actions)
    const list = document.createElement('div'); list.className = 'items'
    for (const item of items) {
      const line = document.createElement('div'); line.className = 'item'
      const check = document.createElement('input'); check.type = 'checkbox'; check.checked = selected.has(item.key); check.disabled = batchRunning
      check.setAttribute('aria-label', '选择 ' + item.label)
      check.addEventListener('change', () => { if (check.checked) selected.add(item.key); else selected.delete(item.key) })
      const details = document.createElement('div'); details.className = 'grow'
      const name = document.createElement('div'); name.className = 'name'; name.textContent = item.title || item.label
      const url = document.createElement('div'); url.className = 'url'; url.textContent = item.link
      const status = document.createElement('div'); status.className = 'status'
      const state = outcomes.get(item.key); status.textContent = state?.message || item.label; status.classList.add(state?.ok ? 'ok' : state ? 'bad' : 'muted')
      details.append(name, url, status)
      const remove = button('删除', () => { dismissed.add(item.key); selected.delete(item.key); renderPanel() }); remove.disabled = batchRunning
      line.append(check, details, remove); list.append(line)
    }
    box.append(list)
    const submit = document.createElement('div'); submit.className = 'row'
    submit.append(button('推送选中', () => pushBatch(false), 'primary'), button('一键推送全部', () => pushBatch(true), 'primary'))
    for (const action of submit.children) action.disabled = batchRunning || !items.length
    box.append(submit)
    if (panel.summary) { const summary = document.createElement('div'); summary.className = 'summary'; summary.textContent = panel.summary; box.append(summary) }
  }
  async function pushOne(item, snapshot) {
    if (outcomes.get(item.key)?.busy) return { ok: true, duplicate: true }
    outcomes.set(item.key, { busy: true, message: '正在提交…' }); renderPanel()
    const options = snapshot ? { accountMode: snapshot.accountMode, accountId: snapshot.accountId, targetCid: item.kind === 'share115' ? snapshot.shareCid : snapshot.offlineCid } : {}
    const res = snapshot && !options.targetCid ? { ok: false, message: '请先在扩展弹窗选择并保存' + (item.kind === 'share115' ? '转存' : '离线') + '目录' } : await send({ type: 'push115', link: item.link, ...options })
    const message = res.ok ? (res.duplicate ? '已存在，未重复创建' : '已提交到 115') : (res.message || '推送失败，请在扩展弹窗检查账号和目录')
    outcomes.set(item.key, { ok: res.ok, message, requestId: res.requestId })
    if (!batchRunning) { toast(message); scan() }
    renderPanel()
    return res
  }
  async function pushBatch(all) {
    if (batchRunning || !enabled) return
    const items = visibleItems().filter(item => all || selected.has(item.key))
    if (!items.length) { toast('请先选择要推送的链接'); return }
    batchRunning = true
    renderPanel()
    try {
      const submitted = await send({ type: 'push115Batch', links: items.map(item => item.link) })
      if (!submitted.ok) { toast(submitted.message || '批量推送失败'); return }
      while (enabled) {
        const state = await send({ type: 'batch115State', batchId: submitted.batchId })
        if (!state.ok || !state.batch) break
        const batch = state.batch
        let accepted = 0, duplicates = 0, failed = 0
        for (const result of batch.results) {
          if (result.ok) { if (result.duplicate) duplicates++; else accepted++; selected.delete(result.key) } else failed++
          outcomes.set(result.key, { ok: result.ok, message: result.ok ? (result.duplicate ? '已存在，未重复创建' : '已提交到 115') : result.message || '推送失败' })
        }
        if (panel) panel.summary = `已处理 ${batch.cursor}/${batch.total} · 已提交 ${accepted} · 已存在 ${duplicates} · 失败 ${failed}` + (batch.message ? '\n' + batch.message : '')
        renderPanel()
        if (batch.status !== 'running') break
        await new Promise(resolve => setTimeout(resolve, 1000))
      }
    } finally { batchRunning = false; renderPanel(); if (enabled) scan() }
  }

  function disable() {
    enabled = false; clearTimeout(timer); observer.disconnect(); closePanel()
    for (const node of ownHosts) node.remove()
    ownHosts.clear(); toolbar = null
  }
  let lastContext = ''
  function updateContext(target) {
    const anchor = target?.closest?.('a[href]')
    const selection = window.getSelection()?.toString() || ''
    const value = anchor ? (candidates(anchor)[0]?.link || '') : (links.extract(selection)[0]?.link || links.extract(location.href)[0]?.link || '')
    if (value === lastContext) return
    lastContext = value; void send({ type: 'context115', value })
  }
  document.addEventListener('pointerover', event => updateContext(event.target), true)
  document.addEventListener('contextmenu', event => updateContext(event.target), true)
  document.addEventListener('selectionchange', () => updateContext(null), true)
  chrome.runtime.onMessage.addListener((message, _sender, respond) => {
    if (message.type === 'pageLinks') { respond({ ok: true, links: scan(enabled), truncated }); return }
    if (message.type === 'openBatch115') {
      if (enabled) openPanel()
      respond({ ok: enabled, message: enabled ? '' : '页面叠加层已关闭，可在扩展弹窗使用批量列表' }); return
    }
  })
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== 'local' || !changes.settings) return
    if (changes.settings.newValue?.pageOverlay === false) disable()
    else { enabled = true; scan() }
  })
  globalThis.__dian115PageLinks = { scan }
  void send({ type: 'overlayState' }).then(result => { enabled = result.enabled !== false; if (enabled) scan() })
})()
