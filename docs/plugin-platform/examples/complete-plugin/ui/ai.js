function imageDataURL(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve({ url: reader.result })
    reader.onerror = () => reject(new Error('图片读取失败，请重新选择文件'))
    reader.readAsDataURL(file)
  })
}

export function mountAI(wrapper, ctx) {
  const doc = wrapper.ownerDocument
  const group = doc.createElement('fieldset')
  const legend = doc.createElement('legend')
  legend.textContent = 'AI 图文对话'
  const form = doc.createElement('form')
  const status = doc.createElement('p')
  status.setAttribute('role', 'status')
  const transcript = doc.createElement('pre')
  transcript.setAttribute('aria-label', '对话记录')
  group.append(legend, form, status, transcript)
  wrapper.append(group)

  function field(name, title, tag) {
    const label = doc.createElement('label')
    const control = doc.createElement(tag)
    control.id = ctx.id + '-ai-' + name
    label.htmlFor = control.id
    label.textContent = title
    const row = doc.createElement('div')
    row.className = 'ai-field'
    row.append(label, control)
    form.append(row)
    return control
  }
  function option(control, value, title) {
    const el = doc.createElement('option')
    el.value = value
    el.textContent = title
    control.append(el)
  }

  const provider = field('provider', '供应商', 'select')
  const model = field('model', '模型', 'select')
  const prompt = field('prompt', '问题', 'textarea')
  const images = field('images', '图片（可选）', 'input')
  images.type = 'file'
  images.accept = 'image/png,image/jpeg,image/webp,image/gif'
  images.multiple = true
  const actions = doc.createElement('div')
  actions.className = 'actions'
  const send = doc.createElement('button')
  send.type = 'submit'
  send.textContent = '发送'
  const clear = doc.createElement('button')
  clear.type = 'button'
  clear.textContent = '新对话'
  actions.append(send, clear)
  form.append(actions)

  let providers = []
  let history = []
  let imageCount = 0
  let imageBytes = 0
  function newChat() {
    history = []
    imageCount = 0
    imageBytes = 0
    transcript.textContent = ''
    status.textContent = ''
    clear.disabled = true
  }
  function showModels(preferred) {
    const selected = providers.find(item => item.id === provider.value)
    model.replaceChildren()
    const names = new Set([selected?.model, ...(selected?.models || []), preferred].filter(Boolean))
    for (const name of names) option(model, name, name)
    model.value = preferred || selected?.model || model.value
    send.disabled = !model.value
  }
  provider.addEventListener('change', () => { newChat(); showModels() })
  model.addEventListener('change', newChat)
  clear.addEventListener('click', () => {
    newChat()
    prompt.value = ''
    images.value = ''
    prompt.focus()
  })

  form.addEventListener('submit', async event => {
    event.preventDefault()
    if (group.disabled || !model.value) return
    const content = prompt.value.trim()
    const files = Array.from(images.files)
    if (!content && !files.length) {
      status.textContent = '请输入问题或选择图片。'
      prompt.focus()
      return
    }
    const bytes = files.reduce((sum, file) => sum + file.size, 0)
    if (imageCount + files.length > 8 || imageBytes + bytes > 8 * 1024 * 1024 || history.length >= 64) {
      status.textContent = '本次对话已达上限（64 条消息、8 张图片、合计 8 MiB），请减少附件或开始新对话。'
      return
    }
    group.disabled = true
    status.textContent = '正在等待模型回复…'
    try {
      const turn = { role: 'user', content, images: await Promise.all(files.map(imageDataURL)) }
      if (ctx.signal?.aborted) return
      const result = await ctx.ai.complete({ provider_id: provider.value, model: model.value, messages: [...history, turn] })
      if (ctx.signal?.aborted) return
      history.push(turn, { role: 'assistant', content: result.text })
      imageCount += files.length
      imageBytes += bytes
      transcript.textContent += ['我', content, ...files.map(file => '图片 · ' + file.name), result.model, result.text, ''].join('\n') + '\n'
      status.textContent = result.finish_reason === 'length' ? '已达模型输出长度上限，可继续追问。' : '已收到回复。'
      prompt.value = ''
      images.value = ''
      clear.disabled = false
      try { await ctx.storage.set('ai-selection', { provider_id: provider.value, model: model.value }) }
      catch { if (!ctx.signal?.aborted) status.textContent += ' 此次模型选择未能保存。' }
    } catch (error) {
      if (!ctx.signal?.aborted) status.textContent = error.response?.data?.error || error.data?.error || error.message
    } finally {
      if (!ctx.signal?.aborted) { group.disabled = false; prompt.focus() }
    }
  })

  group.disabled = true
  clear.disabled = true
  status.textContent = '正在读取宿主 AI 供应商…'
  Promise.all([ctx.ai.providers(), ctx.storage.get('ai-selection').catch(() => null)]).then(([catalog, saved]) => {
    if (ctx.signal?.aborted) return
    providers = catalog.providers
    for (const item of providers) option(provider, item.id, item.name)
    if (!providers.length) {
      status.textContent = '请先在宿主 AI 设置中启用供应商和模型。'
      return
    }
    const previous = providers.find(item => item.id === saved?.provider_id)
    provider.value = previous?.id || catalog.default_provider_id || providers[0].id
    const defaultModel = provider.value === catalog.default_provider_id ? catalog.default_model : ''
    const available = [previous?.model, ...(previous?.models || []), defaultModel]
    const restored = previous && available.includes(saved.model)
    showModels(restored ? saved.model : defaultModel)
    status.textContent = ''
    group.disabled = false
  }).catch(error => {
    if (!ctx.signal?.aborted) status.textContent = error.response?.data?.error || error.message
  })
}
