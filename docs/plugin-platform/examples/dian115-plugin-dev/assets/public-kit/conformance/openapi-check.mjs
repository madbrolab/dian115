import {readFileSync} from 'node:fs'
const doc=JSON.parse(readFileSync(new URL('../openapi-v3.json',import.meta.url),'utf8'));const errors=[]
function inspect(node){if(!node||typeof node!=='object')return;for(const [key,value]of Object.entries(node)){if(key==='$ref'&&typeof value==='string'&&value.startsWith('#/')){let target=doc;for(const part of value.slice(2).split('/'))target=target?.[part.replaceAll('~1','/').replaceAll('~0','~')];if(!target)errors.push('Missing reference '+value)}else inspect(value)}}inspect(doc)
for(const [path,operations]of Object.entries(doc.paths)){if(path.startsWith('/api/plugin-runtime')||path.startsWith('/api/plugin-center'))errors.push('Retired route '+path);for(const [method,op]of Object.entries(operations))if(['get','post','put','patch','delete','head'].includes(method)&&!op.responses)errors.push('Missing response '+method+' '+path)}
if(errors.length)throw Error(errors.join('\n'));console.log(`OpenAPI v3 引用完整：${Object.keys(doc.paths).length} 条路径`)
