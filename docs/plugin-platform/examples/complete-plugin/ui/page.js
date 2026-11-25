import { mountAI } from './ai.js'

export async function mount(root, ctx) {
  const doc = root.ownerDocument
  const wrapper = doc.createElement('section')
  wrapper.className = 'api-lab'
  const style = doc.createElement('style')
  style.textContent = `
    .api-lab{box-sizing:border-box;min-block-size:100%;background:var(--app-surface);color:var(--app-text);padding:clamp(16px,4vw,32px)}
    .api-lab header{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin-block-end:12px}
    .api-lab h2{margin-block-start:0}
    .api-lab form{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr));gap:16px}
    .api-lab label,.api-lab .ai-field{display:grid;min-width:0;gap:6px}
    .api-lab input{min-width:0;max-width:100%}
    .api-lab :is(input,select,textarea,button){font:inherit;color:inherit;background:var(--app-bg);border:1px solid var(--app-border);border-radius:12px;padding:10px;box-sizing:border-box;min-block-size:44px}
    .api-lab button{min-inline-size:44px;border-radius:999px;padding-inline:16px;cursor:pointer;touch-action:manipulation}
    .api-lab .mobile-menu{display:none}
    @media (max-width:768px), (max-height:500px) and (hover:none) and (pointer:coarse){
      .api-lab .mobile-menu{display:inline-block}
    }
    .api-lab button[data-primary]{background:color-mix(in srgb,var(--app-accent) 17%,var(--app-surface));font-weight:650}
    @media (pointer:coarse){.api-lab :is(input,textarea,select){font-size:max(16px,1em)}}
    .api-lab .actions{display:flex;flex-wrap:wrap;gap:8px;margin-block:20px}
    .api-lab fieldset{min-inline-size:0;border:1px solid var(--app-border);border-radius:12px;margin:0 0 20px;padding:16px}
    .api-lab fieldset form{align-items:start}
    .api-lab select{max-inline-size:100%}
    .api-lab pre{white-space:pre-wrap;overflow-wrap:anywhere;overflow:auto}
    .api-lab :is(button,input,select,textarea):focus-visible{outline:2px solid var(--app-accent);outline-offset:2px}
    .api-lab button:disabled{opacity:.55;cursor:default}
    .api-lab button:active:not(:disabled){opacity:.75}
    @media (prefers-reduced-motion: no-preference){
      .api-lab button{transition:scale 160ms cubic-bezier(.2,.75,.25,1),opacity 140ms ease}
      .api-lab button:active:not(:disabled){scale:.98;transition-duration:0ms}
    }
  `
  wrapper.append(style)
  const header = doc.createElement('header')
  const output = doc.createElement('pre')
  output.setAttribute('aria-live', 'polite')
  function addNavigation(label, method, mobileOnly = false) {
    if (typeof ctx.navigation?.[method] !== 'function') return
    const button = doc.createElement('button')
    button.type = 'button'
    button.textContent = label
    if (mobileOnly) button.className = 'mobile-menu'
    button.addEventListener('click', async () => {
      try { await ctx.navigation[method]() } catch (error) { output.textContent = error.message }
    })
    header.append(button)
  }
  addNavigation('打开主菜单', 'openSidebar', true)
  addNavigation('返回插件中心', 'close')
  wrapper.append(header)
  const title = doc.createElement('h2'); title.textContent = '插件 API 测试台'; wrapper.append(title)
  const note = doc.createElement('p'); note.textContent = '地址与账号在安装后填写。登录、CookieCloud 写入、监听和通知只在点击相应按钮时执行。'; wrapper.append(note)
  const form = doc.createElement('form'); form.addEventListener('submit', event => event.preventDefault())
  const fields = {}
  for (const [name, label, type, fallback] of [
    ['hook_token','公开回调令牌','password',''],['listen_port','测试监听端口','number','18765'],
    ['url','自定义站点 URL','url',''],['login','登录表单 URL（完整地址）','url',''],
    ['username','账号 / 邮箱','text',''],['password','密码','password',''],['cookie','明文 Cookie','text',''],
    ['flare','FlareSolverr 地址','url','http://192.168.2.2:8191'],['domain','CookieCloud 域名','text',''],
    ['api','宿主 GET 接口','text','/api/dashboard/stats'],['timeout','HTTP 超时（秒）','number','180'],
    ['path','CD2 或本地监听目录','text',''],['business','任务业务标识','text','probe-1'],
  ]) {
    const input = doc.createElement('input'); input.type = type; input.name = name; input.value = fallback
    if(type==='password') input.autocomplete='current-password'
    const row = doc.createElement('label'); row.append(doc.createTextNode(label),input);form.append(row);fields[name]=input
  }
  mountAI(wrapper, ctx)
  wrapper.append(form)
  const actions = doc.createElement('div'); actions.className='actions';wrapper.append(actions)
  wrapper.append(output)
  const read = () => Object.fromEntries(Object.entries(fields).map(([k,v])=>[k,v.value]))
  let disposed=false
  const buttons=[]
  function action(title, fn, primary = false) { const b=doc.createElement('button');b.type='button';b.textContent=title;b.toggleAttribute('data-primary',primary);buttons.push(b);actions.append(b);b.addEventListener('click',async()=>{buttons.forEach(x=>x.disabled=true);output.textContent='正在调用…';try{const result=await fn(read());if(!disposed)output.textContent=JSON.stringify(result??{ok:true},null,2)}catch(e){if(!disposed)output.textContent=e.message||String(e)}finally{if(!disposed)buttons.forEach(x=>x.disabled=false)}}) }
  action('保存配置', async value => {
    const port = Number(value.listen_port)
    if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('请输入 1 至 65535 的端口')
    const { username, password, cookie, hook_token, listen_port, ...site } = value
    const previous = await ctx.settings.get()
    await ctx.settings.set({ ...previous, username, password, cookie, hook_token, listen_port: port })
    await ctx.storage.set('site', site)
    return { saved: true }
  }, true)
  action('调用宿主 GET', value=>ctx.api.get(value.api))
  action('HTTP 页面', value=>ctx.http.request({url:value.url,timeout_seconds:Number(value.timeout)}))
  action('提交账号密码登录', value=>ctx.http.request({url:value.login,method:'POST',headers:{'Content-Type':['application/x-www-form-urlencoded']},body:new URLSearchParams({username:value.username,password:value.password}).toString(),timeout_seconds:Number(value.timeout)}))
  action('保存明文 CK', value=>ctx.http.cookies({url:value.url,cookie:value.cookie}))
  action('读取当前 CK', value=>ctx.http.cookies({url:value.url}))
  action('CookieCloud 导入',async value=>{const snapshot=await ctx.cookiecloud('read',{domains:[value.domain]});await ctx.http.importCookies({cookies:snapshot.cookies});return {revision:snapshot.revision,count:snapshot.cookies.length}})
  action('CookieCloud 导出',async value=>{const snapshot=await ctx.cookiecloud('read',{domains:[value.domain]});const cookies=await ctx.http.cookies({url:value.url});return ctx.cookiecloud('write',{domains:[value.domain],cookies,revision:snapshot.revision})})
  action('FlareSolverr 页面', value=>ctx.http.render({endpoint:value.flare,url:value.url,timeout_seconds:Number(value.timeout)}))
  action('插件文件读写',async()=>{await ctx.files.call({operation:'write',path:'probe.txt',content:'plugin-owned file'});return ctx.files.call({operation:'read',path:'probe.txt'})})
  action('CD2 列表',value=>ctx.cd2.call('list',{path:value.path,force_refresh:true}))
  action('增加本地目录轮询',value=>ctx.watch.add({id:'probe-watch',path:value.path,job:'probe',interval_seconds:10}))
  action('删除目录轮询',()=>ctx.watch.remove('probe-watch'))
  action('启动测试任务',value=>ctx.tasks.run('probe',value.business,{source:'api-lab'}))
  action('任务记录',()=>ctx.tasks.list())
  action('存储分页',()=>ctx.storage.list())
  action('磁盘用量',()=>ctx.usage())
  action('下载到插件文件（二进制）',value=>ctx.http.request({url:value.url,save_to:'downloads/probe.bin',timeout_seconds:Number(value.timeout)}))
  action('下载链接',()=>({url:ctx.files.downloadURL('downloads/probe.bin')}))
  action('实时监听（仅视频）',value=>ctx.watch.add({id:'probe-realtime',path:value.path,job:'probe',interval_seconds:300,patterns:['*.mkv','*.mp4']}))
  action('删除实时监听',()=>ctx.watch.remove('probe-realtime'))
  action('开启测试端口',async()=>{const settings=await ctx.settings.get();return ctx.server.listen({id:'probe',port:Number(settings.listen_port||18765)})})
  action('端口与回调地址',async()=>({listeners:await ctx.server.list(),hook:ctx.server.hookURL('echo'),public:ctx.server.publicHookURL('echo')+'?token=…'}))
  action('关闭测试端口',()=>ctx.server.close('probe'))
  action('最近宿主事件',()=>ctx.storage.get('host-events'))
  action('通知渠道',()=>ctx.notifications.channels())
  action('Markdown 通知（按渠道内容）',value=>ctx.notifications.send({title:'插件 API 测试',level:'success',format:'markdown',body:'**格式测试**\n- 列表项\n> 引用\n[链接](https://example.com)',overrides:{wecom:{format:'text',body:'格式测试（企业微信纯文本）'}},dedupe_key:value.business+':markdown'}))
  action('发送测试通知',value=>ctx.notify({title:'插件 API 测试',body:'这是用户主动触发的测试通知',dedupe_key:value.business+':notification'}))
  root.append(wrapper)
  try {
    const [stored, settings] = await Promise.all([ctx.storage.get('site'), ctx.settings.get()])
    if (!ctx.signal?.aborted) {
      for (const [key, value] of Object.entries({ ...stored, ...settings })) {
        if (fields[key] && value != null) fields[key].value = String(value)
      }
    }
  } catch (error) { if (!ctx.signal?.aborted) output.textContent = error.message }
  return ()=>{disposed=true;wrapper.remove()}
}
