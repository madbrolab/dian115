const byId = id => document.getElementById(id)
const settings = !!byId('cloud-settings')
let state
let busy = false

function action(action, fields = {}) {
  return new Promise(resolve => chrome.runtime.sendMessage({ type: 'cloud', action, ...fields }, result => {
    resolve(chrome.runtime.lastError || !result?.ok ? { error: result?.message || '扩展连接中断' } : result)
  }))
}

function feedback(note) {
  const node = byId(settings ? 'cloud-feedback' : 'cloud-summary')
  node.hidden = !note
  node.textContent = note
}

function render() {
  const ready = !!state?.configured
  const result = state?.result
  const summary = !ready ? '请在「连接」设置服务器' : result?.outcome === 'error' ? result.note : result?.last
    ? result.domains + ' 个域名 · ' + result.count + ' 项 Cookie' : '等待首次同步'
  byId('cloud-now').disabled = busy || !ready
  byId('cloud-summary').textContent = summary
  if (!settings) return
  byId('cloud-total').textContent = state?.keywords?.trim() ? '按关键词' : state?.blacklist?.trim() ? '全部 · 含排除' : '全部域名'
  byId('cloud-last').textContent = result?.last ? '最近同步 · ' + new Date(result.last).toLocaleString() : ''
  byId('cloud-target').textContent = ready ? '接收服务器 · ' + state.base : '请先在「连接」保存服务器地址和 OpenAPI Key'
  byId('cloud-auto').checked = !!state?.auto
  byId('cloud-minutes').value = String(state?.minutes || 10)
  byId('cloud-keywords').value = state?.keywords || ''
  byId('cloud-blacklist').value = state?.blacklist || ''
  for (const node of byId('cloud-settings').elements) node.disabled = busy || !ready
}

async function perform(name, fields = {}) {
  if (busy) return
  busy = true
  const previous = state
  if (name === 'save') state = { ...state, ...fields }
  render()
  feedback(name === 'sync' ? '正在同步…' : '')
  const result = await action(name, { base: state?.base, ...fields })
  busy = false
  state = result.error ? previous : result
  render()
  if (result.error) { feedback(result.error); return }
  if (name === 'sync') feedback(state.result?.note || '等待同步')
  if (name === 'save') feedback('已保存')
}

if (settings) {
  function showPane() {
    const name = ['cookiecloud', 'push'].includes(location.hash.slice(1)) ? location.hash.slice(1) : 'connection'
    document.querySelectorAll('.pane').forEach(pane => { pane.hidden = pane.id !== name })
    document.querySelectorAll('.segmented a').forEach(a => a.setAttribute('aria-current', a.hash === '#' + name ? 'page' : 'false'))
    document.querySelector('.settings-save').hidden = name === 'cookiecloud'
    if (name === 'cookiecloud') void perform('state')
  }
  window.addEventListener('hashchange', showPane)
  showPane()
  const save = () => {
    if (!byId('cloud-settings').reportValidity()) return
    void perform('save', {
      auto: byId('cloud-auto').checked,
      minutes: byId('cloud-minutes').valueAsNumber,
      keywords: byId('cloud-keywords').value,
      blacklist: byId('cloud-blacklist').value,
    })
  }
  byId('cloud-settings').onsubmit = event => { event.preventDefault(); save() }
  byId('cloud-auto').onchange = save
} else {
  byId('cloud-open').onclick = () => chrome.tabs.create({ url: chrome.runtime.getURL('src/options.html#cookiecloud') })
  void perform('state')
}
byId('cloud-now').onclick = () => perform('sync')
