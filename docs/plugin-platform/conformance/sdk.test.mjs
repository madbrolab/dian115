import {test} from 'node:test'
import {fileURLToPath} from 'node:url'
import assert from 'node:assert/strict'
import {createPluginContext} from '../examples/sdk/index.js'

test('shared browser client stays in the calling plugin namespace',async()=>{
  const calls=[]
  const ctx=createPluginContext('example.browser',async(method,path,body)=>{calls.push({method,path,body});return {id:'page-1',profile:'login'}})
  await ctx.browser.status()
  const page=await ctx.browser.open({profile:'login',operation:'forged',proxy_mode:'custom',proxy_url:'socks5://127.0.0.1:1080'})
  await ctx.browser.command({session:page.id,method:'Runtime.evaluate',params:{expression:'document.title'}})
  await ctx.browser.events({session:page.id,after:12,wait_ms:100})
  await ctx.browser.close(page.id)
  assert(calls.every(call=>call.method==='POST'&&call.path==='/api/extensions/v3/example.browser/browser'))
  assert.deepEqual(calls.map(call=>call.body.operation),['status','open','command','events','close'])
  assert.equal(calls[1].body.profile,'login')
  assert.equal(calls[1].body.proxy_mode,'custom')
  assert.equal(calls[1].body.proxy_url,'socks5://127.0.0.1:1080')
  assert.equal(calls[4].body.session,'page-1')
})
import {checkProject} from './project-check.mjs'
import {run,recover} from '../examples/complete-plugin/jobs/job.js'
test('public SDK uses ordinary host API and plugin-owned namespaces',async()=>{const calls=[];const request=async(method,path,body)=>{calls.push({method,path,body});return path.includes('/storage/')?{value:42,revision:1}:{ok:true}};const a=createPluginContext('example.a',request),b=createPluginContext('example.b',request);assert.equal(await a.storage.get('x/y'),42);await b.storage.set('x',1,0);await a.api.post('/api/115/share/receive',{share_url:'example'});await a.http.importCookies({cookies:[]});await a.http.render({endpoint:'http://localhost:8191',url:'https://example.test'});await a.cookiecloud('read',{domains:['example.test']});await a.tasks.run('probe','same',{x:1});assert.equal(calls[0].path,'/api/extensions/v3/example.a/storage/x%2Fy');assert.equal(calls[1].path,'/api/extensions/v3/example.b/storage/x');assert.equal(calls[2].path,'/api/115/share/receive');assert.deepEqual(calls[2].body,{share_url:'example'});assert(!calls.some(c=>c.path.includes('host-call')||c.path.includes('plugin-runtime')));assert.equal(calls.at(-1).body.business_key,'same')})
test('sample recovery verifies observed state and avoids duplicate write',async()=>{let count=0,checkpoint;const ctx={storage:{get:async()=>count,set:async(k,v)=>{count=v}},task:{checkpoint:async value=>{checkpoint=value},update:async()=>{}}};const result=await run(ctx,{x:1});assert.equal(count,1);assert.deepEqual(await recover(ctx,checkpoint),{action:'complete',result});assert.deepEqual(await recover(ctx,{stage:'before-write',previous:0}),{action:'complete',result:{count:1,recovered:true}});assert.deepEqual(await recover(ctx,{stage:'before-write',previous:1}),{action:'resume'});assert.deepEqual(await recover(ctx,{stage:'unknown'}),{action:'attention'})})
test('current complete sample passes source inspection',()=>{assert.deepEqual(checkProject(fileURLToPath(new URL('../examples/complete-plugin',import.meta.url))).errors,[])})
test('standalone SDK binds installation and code version without changing API bodies',async()=>{let actual;const client=createPluginContext('example.a',async(method,path,body,source)=>{actual={method,path,body,source};return {ok:true}},{generation:'install-A',revision:'code-A'});await client.api.post('/api/115/share/receive',{share_url:'https://example.test/share'});assert.deepEqual(actual.source,{plugin_id:'example.a',generation:'install-A',revision:'code-A'});assert.deepEqual(actual.body,{share_url:'https://example.test/share'})})
