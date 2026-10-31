#!/usr/bin/env node
// Checks a market index against the required listing fields before publishing.
//   node market-check.mjs <index.json>
import {readFileSync} from 'node:fs'
import {resolve} from 'node:path'
const index=JSON.parse(readFileSync(resolve(process.argv[2]||'index.json'),'utf8')),errors=[],seen=new Set()
const url=v=>{try{return ['http:','https:'].includes(new URL(v).protocol)}catch{return false}}
if(index.schema_version!==3||!index.repository?.id||!index.repository?.name||!Array.isArray(index.plugins))errors.push('索引须为 v3，并提供 repository.id、repository.name 和 plugins')
for(const item of index.plugins||[]){
 const label=`${item.id||'未命名'} ${item.version||''}`.trim(),key=`${item.id}\0${item.version}`
 if(seen.has(key))errors.push(`${label}：重复版本`);seen.add(key)
 for(const field of ['id','name','version','author','description','changelog','delivery'])if(!String(item[field]||'').trim())errors.push(`${label}：缺少 ${field}`)
 if(!url(item.homepage))errors.push(`${label}：homepage 须为 HTTP/HTTPS 地址`)
 if(!url(item.source_url))errors.push(`${label}：source_url 须为 HTTP/HTTPS 地址`)
 if(!/^[a-fA-F0-9]{64}$/.test(item.sha256||''))errors.push(`${label}：sha256 须为 64 位十六进制`)
 if(!['source','encrypted'].includes(item.delivery))errors.push(`${label}：delivery 须为 source 或 encrypted`)
}
if(errors.length){console.error(errors.join('\n'));process.exitCode=1}else console.log(`通过：${index.plugins.length} 个版本`)
