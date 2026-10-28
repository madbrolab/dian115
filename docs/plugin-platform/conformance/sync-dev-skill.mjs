import { existsSync, mkdirSync, lstatSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { dirname, relative, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'
import { createHash } from 'node:crypto'
const platform=resolve(dirname(fileURLToPath(import.meta.url)),'..')
const skill=resolve(platform,'examples/dian115-plugin-dev'), target=resolve(skill,'assets/public-kit')
const check=process.argv.includes('--check')
const hash=data=>createHash('sha256').update(data).digest('hex')
const expected=new Map([['.gitattributes',Buffer.from('* -text\n')]])
const add=(source,dest)=>{const path=resolve(platform,source);if(!lstatSync(path).isFile())throw Error('Expected a regular public source file: '+source);expected.set(dest,readFileSync(path))}
const docs=['README.md','skill-installation.md','developer-guide.md','package-format-v1.md','wasm-runtime-v1.md','host-call-v2.md','storage-and-lifecycle.md','ui-federation-v1.md','ui-isolation-v1.md','job-recovery-v1.md','troubleshooting.md','publication-policy.md','host-api-quick-reference.md','openapi-v1.yaml','manifest.schema.json','integrity.schema.json','signature.schema.json','market-index.schema.json']
for(const file of docs)add(file,file)
for(const file of ['README.md','verify-public-surface.mjs','project-check.mjs','runtime-check.mjs','openapi-check.mjs','generate-reference.mjs','openapi-check.test.mjs','runtime-check.test.mjs'])add('conformance/'+file,'conformance/'+file)
// Explicit public source inventory; never collect untracked local files or secrets.
const sources=[
  "examples/complete-plugin/.gitignore",
  "examples/complete-plugin/README.md",
  "examples/complete-plugin/actions.test.mjs",
  "examples/complete-plugin/background-job.test.mjs",
  "examples/complete-plugin/frontend/icon.svg",
  "examples/complete-plugin/go.mod",
  "examples/complete-plugin/index.html",
  "examples/complete-plugin/manifest.template.json",
  "examples/complete-plugin/market-entry.template.json",
  "examples/complete-plugin/package-lock.json",
  "examples/complete-plugin/package.json",
  "examples/complete-plugin/preview-bridge.test.mjs",
  "examples/complete-plugin/runtime/main.go",
  "examples/complete-plugin/scripts/build-runtime.mjs",
  "examples/complete-plugin/scripts/package.mjs",
  "examples/complete-plugin/src/AppPage.vue",
  "examples/complete-plugin/src/actions.ts",
  "examples/complete-plugin/src/background-job.ts",
  "examples/complete-plugin/src/env.d.ts",
  "examples/complete-plugin/src/main.ts",
  "examples/complete-plugin/src/preview-bridge.ts",
  "examples/complete-plugin/src/preview.css",
  "examples/complete-plugin/tsconfig.json",
  "examples/complete-plugin/vite.config.ts",
  "examples/sdk/README.md",
  "examples/sdk/go.mod",
  "examples/sdk/hostapi/checkpoints.go",
  "examples/sdk/hostapi/checkpoints_test.go",
  "examples/sdk/hostapi/client.go",
  "examples/sdk/hostapi/client_test.go",
  "examples/sdk/hostapi/jobs.go",
  "examples/sdk/hostapi/jobs_test.go",
  "examples/sdk/hostapi/storage_catalog.go",
  "examples/sdk/hostapi/storage_catalog_test.go",
  "examples/sdk/pluginjson/pluginjson.go",
  "examples/sdk/pluginjson/pluginjson_test.go",
  "examples/sdk/ui.ts"
]
for(const file of sources)add(file,file)
const openapi=expected.get('openapi-v1.yaml').toString('utf8')
const block=openapi.split('x-dian115-host-apis:')[1]?.split('\nx-dian115-subscription-host-apis:')[0]
if(!block)throw Error('Missing standard Host API catalog')
const entries=[...block.matchAll(/^    - method: (\S+)\n      path: (\S+)\n      category: (\S+)\n      risk: (\S+)\n      title: (.+)\n      description: (.+)\n      host_credentials: (true|false)/gm)].map(m=>({method:m[1],path:m[2],category:m[3].startsWith('"')?JSON.parse(m[3]):m[3],risk:m[4],title:JSON.parse(m[5]),description:JSON.parse(m[6]),host_credentials:m[7]==='true'}))
if(!entries.length || entries.length!==[...block.matchAll(/^    - method:/gm)].length || new Set(entries.map(e=>e.method+' '+e.path)).size!==entries.length)throw Error('Incomplete or duplicate API catalog')
expected.set('host-api-catalog.json',Buffer.from(JSON.stringify({openapi_sha256:hash(expected.get('openapi-v1.yaml')),entries},null,2)+'\n'))
function walk(dir){return readdirSync(dir,{withFileTypes:true}).flatMap(e=>e.isDirectory()?walk(resolve(dir,e.name)):[resolve(dir,e.name)]).sort()}
if(check){
 if(!existsSync(target))throw Error('Skill public-kit is missing')
 const actual=walk(target).map(p=>relative(target,p).split(sep).join('/')).sort()
 if(JSON.stringify(actual)!==JSON.stringify([...expected.keys()].sort()))throw Error('Public-kit file inventory drift')
 for(const [file,data] of expected)if(!readFileSync(resolve(target,file)).equals(data))throw Error('Public-kit is out of date: '+file)
}else{
 rmSync(target,{recursive:true,force:true});mkdirSync(target,{recursive:true})
 for(const [file,data]of expected){mkdirSync(dirname(resolve(target,file)),{recursive:true});writeFileSync(resolve(target,file),data)}
 const result=spawnSync('git',['rev-parse','HEAD'],{cwd:platform,encoding:'utf8'});if(result.status!==0)throw Error('Cannot read public source revision')
 const files=Object.fromEntries(walk(resolve(skill,'assets')).map(p=>[relative(skill,p).split(sep).join('/'),hash(readFileSync(p))]).sort(([a],[b])=>a<b?-1:a>b?1:0))
 writeFileSync(resolve(skill,'contract-lock.json'),JSON.stringify({schema_version:1,skill:'dian115-plugin-dev',version:existsSync(resolve(skill,'contract-lock.json'))?JSON.parse(readFileSync(resolve(skill,'contract-lock.json'),'utf8')).version:'1.0.0',source_repository:'https://github.com/madbrolab/dian115',source_commit:result.stdout.trim(),api_count:entries.length,toolchain:{node:'20+',go:'1.25+',tinygo:'0.43.0',binaryen:'133'},files},null,2)+'\n')
}
process.stdout.write(`Skill public-kit ${check?'freshness':'sync'}: PASS (${expected.size} public files; ${entries.length} APIs)\n`)
