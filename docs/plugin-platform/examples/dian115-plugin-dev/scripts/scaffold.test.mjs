import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync, writeFileSync, mkdirSync, cpSync, rmSync, symlinkSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'
import { spawnSync } from 'node:child_process'
import { root, json, verify } from './lib.mjs'
const temp=mkdtempSync(resolve(tmpdir(),'dian115-skill-test-'))
process.on('exit',()=>rmSync(temp,{recursive:true,force:true}))
function run(script,args=[],options={}){return spawnSync(process.execPath,[resolve(root,'scripts',script),...args],{encoding:'utf8',...options})}
function init(name,extra=[]){const dest=resolve(temp,name);const result=run('init.mjs',['--dir',dest,'--id','dev.test.sample','--name','名称 "测试"','--publisher','作者',...extra]);assert.equal(result.status,0,result.stderr);return dest}
function contract(dest){const result=spawnSync(process.execPath,[resolve(dest,'.dian115/conformance/project-check.mjs'),'--manifest',resolve(dest,'manifest.template.json'),'--market',resolve(dest,'market-entry.template.json'),'--build-root',resolve(dest,'.dian115/no-build')],{encoding:'utf8'});assert.equal(result.status,0,result.stderr)}
test('minimal generated project is self-contained with zero business permissions',()=>{
 const dest=init('minimal 空格');const manifest=json(resolve(dest,'manifest.template.json'))
 assert.equal(manifest.id,'dev.test.sample');assert.equal(manifest.name,'名称 "测试"')
 assert.deepEqual(manifest.permissions,{apis:[],network:[]});assert.equal(manifest.runtime.resident,false)
 for(const name of ['jobs','events','telegram'])assert.equal(manifest[name],undefined)
 assert.match(readFileSync(resolve(dest,'go.mod'),'utf8'),/=> \.\/\.dian115\/examples\/sdk/)
 assert.equal(json(resolve(dest,'.dian115/contract-lock.json')).api_count,verify().api_count)
 assert.equal(json(resolve(dest,'package-lock.json')).packages[''].name,'dev-test-sample')
 contract(dest)
})
test('existing project and malformed identity are refused without modifying files',()=>{
 const dest=resolve(temp,'existing');mkdirSync(dest);writeFileSync(resolve(dest,'keep'),'author content')
 const result=run('init.mjs',['--dir',dest,'--id','dev.test.a','--name','a','--publisher','b'])
 assert.notEqual(result.status,0);assert.equal(readFileSync(resolve(dest,'keep'),'utf8'),'author content')
 const invalid=run('init.mjs',['--dir',resolve(temp,'invalid'),'--id','../escape','--name','a','--publisher','b']);assert.notEqual(invalid.status,0)
})
test('complete template remains opt-in and imports the local public SDK',()=>{
 const dest=init('complete',['--template','complete','--version','2.1.0'])
 const manifest=json(resolve(dest,'manifest.template.json'));assert.ok(manifest.permissions.apis.length>0);assert.ok(manifest.jobs.length>0)
 assert.equal(manifest.version,'2.1.0')
 for(const file of ['main.ts','AppPage.vue','actions.ts','background-job.ts','preview-bridge.ts'])assert.ok(!readFileSync(resolve(dest,'src',file),'utf8').includes("'../../sdk/ui'"))
 contract(dest)
})
test('corrupted or added installed resources fail before project creation',()=>{
 const copy=resolve(temp,'skill-copy');cpSync(root,copy,{recursive:true})
 writeFileSync(resolve(copy,'assets/public-kit/openapi-v1.yaml'),'tampered')
 const result=spawnSync(process.execPath,[resolve(copy,'scripts/init.mjs'),'--dir',resolve(temp,'tampered-project'),'--id','dev.test.a','--name','a','--publisher','b'],{encoding:'utf8'})
 assert.notEqual(result.status,0);assert.match(result.stderr,/integrity/)
 const original=run('verify.mjs');assert.equal(original.status,0,original.stderr)
})
test('API discovery filters exact public methods and fails for unavailable capabilities',()=>{
 const found=run('api.mjs',['--query','/api/plugin-runtime/storage/:key','--method','GET','--json']);assert.equal(found.status,0,found.stderr)
 const rows=JSON.parse(found.stdout).entries;assert.equal(rows.length,1);assert.equal(rows[0].method,'GET')
 assert.equal(run('api.mjs',['--query','definitely-not-a-real-capability-987']).status,1)
 assert.equal(run('api.mjs',['--method','TRACE']).status,1)
})
test('doctor reports missing tools without installing or pretending build readiness',()=>{
 const result=run('doctor.mjs',['--json'],{env:{...process.env,PATH:resolve(temp,'empty-path'),TINYGO:resolve(temp,'no-tinygo'),WASMOPT:resolve(temp,'no-wasm-opt')}})
 assert.equal(result.status,1,result.stderr);const report=JSON.parse(result.stdout)
 assert.equal(report.ready,false);assert.equal(report.tools.find(tool=>tool.name==='tinygo').available,false)
})
test('signing requires an external absolute key and rejects symlink targets inside project',()=>{
 const dest=init('signing'),script=resolve(dest,'scripts/sign.mjs')
 for(const key of ['', 'relative.pem',resolve(dest,'private.pem')]){
  const result=spawnSync(process.execPath,[script],{encoding:'utf8',env:{...process.env,DIAN115_PLUGIN_SIGNING_KEY:key}})
  assert.notEqual(result.status,0);assert.match(result.stderr,/outside|absolute/)
 }
 const real=resolve(dest,'key.pem');writeFileSync(real,'sentinel')
 const link=resolve(temp,'key-link.pem');symlinkSync(real,link)
 const result=spawnSync(process.execPath,[script],{encoding:'utf8',env:{...process.env,DIAN115_PLUGIN_SIGNING_KEY:link}})
 assert.notEqual(result.status,0);assert.match(result.stderr,/outside/);assert.equal(readFileSync(real,'utf8'),'sentinel')
})

test('installed skill preserves snapshot bytes through Git autocrlf checkout',()=>{
 const repo=resolve(temp,'checkout-test');mkdirSync(repo);cpSync(root,resolve(repo,'skill'),{recursive:true})
 for(const args of [['init','-q'],['config','core.autocrlf','true'],['add','.'],['-c','user.name=bot','-c','user.email=bot@example.com','commit','-qm','snapshot']]){
  const result=spawnSync('git',args,{cwd:repo,encoding:'utf8'});assert.equal(result.status,0,result.stderr)
 }
 rmSync(resolve(repo,'skill'),{recursive:true});const checkout=spawnSync('git',['restore','.'],{cwd:repo,encoding:'utf8'});assert.equal(checkout.status,0,checkout.stderr)
 const result=spawnSync(process.execPath,[resolve(repo,'skill/scripts/verify.mjs')],{encoding:'utf8'});assert.equal(result.status,0,result.stderr)
})

test('initializing through a symlink cannot write into installed skill resources',()=>{
 const alias=resolve(temp,'installed-alias');symlinkSync(root,alias,'dir')
 const result=run('init.mjs',['--dir',resolve(alias,'new-project'),'--id','dev.test.a','--name','a','--publisher','b'])
 assert.notEqual(result.status,0);assert.match(result.stderr,/outside the installed skill/)
 assert.equal(run('verify.mjs').status,0)
})
