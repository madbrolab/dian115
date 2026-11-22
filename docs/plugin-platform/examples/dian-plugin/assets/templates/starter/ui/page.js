export function mount(element, ctx) {
  element.innerHTML = `
    <section class="starter-page">
      <style>
        .starter-page { box-sizing:border-box; height:100%; min-width:0; display:grid; grid-template-rows:auto minmax(0,1fr); background:var(--app-bg); color:var(--app-text) }
        .starter-page header { display:flex; align-items:center; flex-wrap:wrap; gap:8px; padding:8px 12px; border-bottom:1px solid var(--app-border) }
        .starter-page main { min-height:0; overflow:auto; overscroll-behavior-y:contain; padding:16px }
        .starter-page button { min-width:44px; min-height:44px; padding:0 12px; font:inherit; color:inherit; background:var(--app-surface); border:1px solid var(--app-border); border-radius:8px }
        .starter-page button:focus-visible { outline:2px solid var(--app-accent) }
        .starter-page pre { white-space:pre-wrap; overflow-wrap:anywhere; color:var(--app-text-secondary) }
        .starter-page [data-menu] { display:none }
        @media (max-width:768px), (max-height:500px) and (hover:none) and (pointer:coarse) {
          .starter-page [data-menu]:not([hidden]) { display:inline-block }
        }
      </style>
      <header>
        <button type="button" data-menu hidden>主菜单</button>
        <button type="button" data-back hidden>返回插件中心</button>
      </header>
      <main>
        <button type="button" data-run>执行任务</button>
        <pre data-out role="status"></pre>
      </main>
    </section>`
  const out = element.querySelector('[data-out]')
  const menu = element.querySelector('[data-menu]')
  const back = element.querySelector('[data-back]')
  if (ctx.navigation?.openSidebar) {
    menu.hidden = false
    menu.onclick = () => ctx.navigation.openSidebar()
  }
  if (ctx.navigation?.close) {
    back.hidden = false
    back.onclick = () => ctx.navigation.close()
  }
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
  return () => { element.replaceChildren() }
}
