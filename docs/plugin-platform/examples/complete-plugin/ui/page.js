export async function mount(root, ctx) {
  const doc = root.ownerDocument
  const wrapper = doc.createElement('section')
  wrapper.className = 'api-lab'
  const style = doc.createElement('style')
  style.textContent = `.api-lab{background:var(--app-surface);color:var(--app-text);padding:20px;border-radius:12px}.api-lab form{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr));gap:16px}.api-lab label{display:grid;gap:6px}.api-lab input,.api-lab textarea,.api-lab button{font:inherit;color:inherit;background:var(--app-bg);border:1px solid var(--app-border);border-radius:6px;padding:10px;box-sizing:border-box;min-height:44px}.api-lab .actions{display:flex;flex-wrap:wrap;gap:10px;margin:20px 0}.api-lab pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:50vh;overflow:auto}.api-lab button:focus-visible{outline:2px solid var(--app-accent)}.api-lab button:disabled{opacity:.55}`
  wrapper.append(style)
  const title = doc.createElement('h2'); title.textContent = '插件 API 测试台'; wrapper.append(title)
  const note = doc.createElement('p'); note.textContent = '地址与账号在安装后填写。登录、CookieCloud 写入、监听和通知只在点击相应按钮时执行。'; wrapper.append(note)
  const form = doc.createElement('form'); form.addEventListener('submit', event => event.preventDefault())
  const fields = {}
  for (const [name, label, type, fallback] of [
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
  wrapper.append(form)
  const actions = doc.createElement('div'); actions.className='actions';wrapper.append(actions)
  const output = doc.createElement('pre'); output.setAttribute('aria-live','polite'); wrapper.append(output)
  const read = () => Object.fromEntries(Object.entries(fields).map(([k,v])=>[k,v.value]))
  let disposed=false
  const buttons=[]
  function action(title, fn) { const b=doc.createElement('button');b.type='button';b.textContent=title;buttons.push(b);actions.append(b);b.addEventListener('click',async()=>{buttons.forEach(x=>x.disabled=true);output.textContent='正在调用…';try{const result=await fn(read());if(!disposed)output.textContent=JSON.stringify(result??{ok:true},null,2)}catch(e){if(!disposed)output.textContent=e.message||String(e)}finally{if(!disposed)buttons.forEach(x=>x.disabled=false)}}) }
  action('保存配置', value=>ctx.storage.set('site',value))
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
  action('增加本地目录轮询',value=>ctx.watch.add({id:'probe-watch',kind:'local',path:value.path,job:'probe',interval_seconds:10}))
  action('删除目录轮询',()=>ctx.watch.remove('probe-watch'))
  action('启动测试任务',value=>ctx.tasks.run('probe',value.business,{source:'api-lab'}))
  action('任务记录',()=>ctx.tasks.list())
  action('存储分页',()=>ctx.storage.list())
  action('磁盘用量',()=>ctx.usage())
  action('下载到插件文件（二进制）',value=>ctx.http.request({url:value.url,save_to:'downloads/probe.bin',timeout_seconds:Number(value.timeout)}))
  action('下载链接',()=>({url:ctx.files.downloadURL('downloads/probe.bin')}))
  action('实时监听（仅视频）',value=>ctx.watch.add({id:'probe-realtime',kind:'local',path:value.path,job:'probe',interval_seconds:300,patterns:['*.mkv','*.mp4']}))
  action('删除实时监听',()=>ctx.watch.remove('probe-realtime'))
  action('开启测试端口',async()=>{const settings=await ctx.settings.get();return ctx.server.listen({id:'probe',port:Number(settings.listen_port||18765)})})
  action('端口与回调地址',async()=>({listeners:await ctx.server.list(),hook:ctx.server.hookURL('echo'),public:ctx.server.publicHookURL('echo')+'?token=…'}))
  action('关闭测试端口',()=>ctx.server.close('probe'))
  action('最近宿主事件',()=>ctx.storage.get('host-events'))
  action('通知渠道',()=>ctx.notifications.channels())
  action('Markdown 通知（按渠道内容）',value=>ctx.notifications.send({title:'插件 API 测试',level:'success',format:'markdown',body:'**格式测试**\n- 列表项\n> 引用\n[链接](https://example.com)',overrides:{wecom:{format:'text',body:'格式测试（企业微信纯文本）'}},dedupe_key:value.business+':markdown'}))
  action('发送测试通知',value=>ctx.notify({title:'插件 API 测试',body:'这是用户主动触发的测试通知',dedupe_key:value.business+':notification'}))
  root.append(wrapper)
  const stored=await ctx.storage.get('site');if(stored&&!disposed)for(const [k,v]of Object.entries(stored)){if(fields[k])fields[k].value=String(v)}
  return ()=>{disposed=true;wrapper.remove()}
}
