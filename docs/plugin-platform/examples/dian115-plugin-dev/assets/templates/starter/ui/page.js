export function mount(element, ctx) {
  element.innerHTML = `
    <section style="padding:16px;display:grid;gap:12px;color:var(--app-text)">
      <button type="button" data-run style="justify-self:start">执行任务</button>
      <pre data-out style="white-space:pre-wrap;color:var(--app-text-secondary)"></pre>
    </section>`
  const out = element.querySelector('[data-out]')
  const button = element.querySelector('[data-run]')
  button.onclick = async () => {
    button.disabled = true
    try {
      const run = await ctx.tasks.run('work', 'work:' + Date.now(), {})
      out.textContent = '已提交：' + run.id
    } catch (error) {
      out.textContent = '失败：' + error.message
    } finally {
      button.disabled = false
    }
  }
  return () => { element.innerHTML = '' }
}
