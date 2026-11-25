import {readFileSync,writeFileSync,mkdirSync,rmSync,existsSync} from 'node:fs'
import {resolve,dirname} from 'node:path'
import {fileURLToPath} from 'node:url'
import {createHash} from 'node:crypto'
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..'),target=resolve(root,'examples/dian-plugin/assets/public-kit'),check=process.argv.includes('--check'),expected=new Map()
const add=(path)=>expected.set(path,readFileSync(resolve(root,path)))
for(const name of [
  'README.md',
  'publication-policy.md',
  'manifest.schema.json',
  'market-index.schema.json',
  'openapi-v3.json',
  'host-api-reference.md',
  'host-api-quick-reference.md',
  'guides/dianying-and-moviepilot.md',
  'guides/quickstart.md',
  'guides/cookbook.md',
  'guides/security-audit.md',
  'guides/developer-guide.md',
  'guides/storage-and-lifecycle.md',
  'guides/encrypted-delivery.md',
  'guides/package-format.md',
  'guides/troubleshooting.md',
  'guides/skill-installation.md',
  'guides/market.md',
  'reference/api-reference.md',
  'reference/media-and-ai.md',
  'reference/subscriptions.md',
  'reference/notifications.md',
  'reference/messaging.md',
  'reference/long-connections.md',
  'reference/manifest.md',
  'reference/network.md',
  'reference/browser.md',
  'reference/ui-theme.md',
  'reference/security.md',
])add(name)
for(const name of ['project-check.mjs','audit.mjs','audit.test.mjs','market-check.mjs','runtime-check.mjs','pack.mjs','openapi-check.mjs','generate-reference.mjs','openapi-model.mjs','annotate-openapi.mjs','generate-sdk-types.mjs','api-glossary.json','api-cookbook.json','sdk-types.check.ts','sdk.test.mjs','verify-public-surface.mjs','README.md'])add('conformance/'+name)
for(const name of ['index.js','index.d.ts','core-types.d.ts','background.d.ts','host-api.d.ts','README.md'])add('examples/sdk/'+name)
for(const name of ['plugin.json','ui/page.js','ui/ai.js','ui/icon.svg','jobs/job.js','jobs/events.js','jobs/http.js','README.md'])add('examples/complete-plugin/'+name)
const hash=b=>createHash('sha256').update(b).digest('hex'),lock=Object.fromEntries([...expected].map(([path,data])=>[path,hash(data)]))
if(check){for(const [path,data]of expected)if(!existsSync(resolve(target,path))||hash(readFileSync(resolve(target,path)))!==hash(data))throw Error('skill 材料未同步：'+path);const actual=JSON.parse(readFileSync(resolve(root,'examples/dian-plugin/contract-lock.json'),'utf8'));if(JSON.stringify(actual)!==JSON.stringify(lock))throw Error('skill 摘要未同步')}else{rmSync(target,{recursive:true,force:true});for(const [path,data]of expected){const dest=resolve(target,path);mkdirSync(dirname(dest),{recursive:true});writeFileSync(dest,data)};writeFileSync(resolve(root,'examples/dian-plugin/contract-lock.json'),JSON.stringify(lock,null,2)+'\n')}
console.log('skill 公开材料 '+(check?'一致':'已同步'))
