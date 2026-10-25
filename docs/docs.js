(() => {
  const input = document.getElementById('doc-search')
  const results = document.getElementById('search-results')
  let catalog
  let searchSequence = 0
  const normalize = value => value.toLocaleLowerCase().replace(/[^\p{L}\p{N}]/gu, '')
  async function search() {
    const sequence = ++searchSequence
    const query = normalize(input.value.trim())
    results.replaceChildren()
    if (!query) { results.hidden = true; return }
    results.hidden = false
    results.textContent = '正在查找…'
    try {
      catalog ||= fetch('/dian115/docs/search-index.json').then(r => { if (!r.ok) throw new Error(); return r.json() })
      const entries = await catalog
      if (sequence !== searchSequence) return
      const hits = entries.map(g => ({ ...g, score: (normalize(g.title).includes(query) ? 100 : 0) + (normalize(g.summary).includes(query) ? 30 : 0) + (normalize(g.text).includes(query) ? 10 : 0) })).filter(g => g.score).sort((a, b) => b.score - a.score).slice(0, 15)
      results.replaceChildren()
      if (!hits.length) results.textContent = '没有找到对应文档。可换用页面名或字段名称。'
      for (const hit of hits) {
        const a = document.createElement('a')
        a.href = '/dian115/docs/' + encodeURIComponent(hit.id) + '/'
        const title = document.createElement('strong'); title.textContent = hit.title
        const detail = document.createElement('span'); detail.textContent = hit.group + ' · ' + hit.summary
        a.append(title, detail); results.append(a)
      }
    } catch { results.textContent = '搜索暂时无法加载，请使用左侧目录。'; catalog = null }
  }
  input.addEventListener('input', search)
  input.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown') { e.preventDefault(); results.querySelector('a')?.focus() }
    if (e.key === 'Enter') { const first = results.querySelector('a'); if (first) first.click() }
  })
  results.addEventListener('keydown', e => {
    if (!['ArrowDown', 'ArrowUp'].includes(e.key)) return
    e.preventDefault()
    const items = [...results.querySelectorAll('a')], index = items.indexOf(document.activeElement)
    items[(index + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length]?.focus()
  })
  document.addEventListener('keydown', e => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); input.focus() }
    if (e.key === 'Escape') { results.hidden = true; input.focus() }
  })
  document.addEventListener('click', e => { if (!e.target.closest('.search')) results.hidden = true })
  document.getElementById('menu-toggle').addEventListener('click', e => {
    const expanded = e.currentTarget.getAttribute('aria-expanded') !== 'true'
    e.currentTarget.setAttribute('aria-expanded', String(expanded)); document.body.classList.toggle('menu-open', expanded)
  })
  let dark = false
  try { dark = localStorage.getItem('dian115-docs-theme') === 'dark' } catch {}
  document.documentElement.dataset.theme = dark ? 'dark' : 'light'
  document.getElementById('theme-toggle').addEventListener('click', () => {
    dark = !dark; document.documentElement.dataset.theme = dark ? 'dark' : 'light'
    try { localStorage.setItem('dian115-docs-theme', dark ? 'dark' : 'light') } catch {}
  })
  let feedbackTimer
  document.addEventListener('click', async e => {
    const button = e.target.closest('[data-copy]')
    if (!button) return
    const code = button.closest('.code-block').querySelector('code').textContent
    try {
      await navigator.clipboard.writeText(code)
      button.textContent = '已复制'
      const status = document.getElementById('copy-status'); status.textContent = '配置已复制'
      clearTimeout(feedbackTimer); feedbackTimer = setTimeout(() => { button.textContent = '复制'; status.textContent = '' }, 2200)
    } catch {
      const selection = getSelection(), range = document.createRange(); range.selectNodeContents(button.closest('.code-block').querySelector('code')); selection.removeAllRanges(); selection.addRange(range)
      document.getElementById('copy-status').textContent = '内容已选中，请按 Ctrl / ⌘ C 复制'
    }
  })
})()
