import { readFileSync, readdirSync, lstatSync } from 'node:fs'
import { resolve, relative, sep } from 'node:path'
import { pathToFileURL } from 'node:url'
export function checkProject(directory) {
 const root=resolve(directory), manifest=JSON.parse(readFileSync(resolve(root,'plugin.json'),'utf8')), errors=[]
 const id=/^[a-z0-9]+(?:[.-][a-z0-9]+)*$/
 if(manifest.schema_version!==3||!id.test(manifest.id)||manifest.id.length>128||!manifest.name||!manifest.version)errors.push('schema_version 3、有效 id、name、version 为必填')
 if(!manifest.ui&&!manifest.jobs?.length&&!manifest.http)errors.push('至少提供页面、任务或 HTTP 处理器')
 const validPath=name=>typeof name==='string'&&name!==''&&!name.includes('\\')&&!name.includes('\0')&&!name.startsWith('/')&&name.split('/').every(p=>p&&p!=='.'&&p!=='..')
 const exists=name=>{if(!validPath(name))return false;try{return lstatSync(resolve(root,name)).isFile()}catch{return false}}
 if(manifest.ui&&(!exists(manifest.ui.entry)||! /\.(js|html)$/.test(manifest.ui.entry)))errors.push('ui.entry 必须是目录内存在的 .js 或 .html')
 const jobs=new Set()
 for(const j of manifest.jobs||[]){if(!id.test(j.id)||jobs.has(j.id)||!exists(j.entry))errors.push('任务 ID 重复或入口无效：'+j.id);jobs.add(j.id);for(const k of ['timeout_seconds','interval_seconds'])if(j[k]!==undefined&&(!Number.isInteger(j[k])||j[k]<0||j[k]>31536000))errors.push('任务时限无效：'+k);if(j.default_schedule&&j.interval_seconds)errors.push('cron 与 interval_seconds 不能并用');if(j.title!==undefined&&(typeof j.title!=='string'||[...j.title].length>40))errors.push('任务标题须为不超过 40 字的字符串：'+j.id);if(j.queue!==undefined&&typeof j.queue!=='boolean')errors.push('任务 queue 须为布尔值：'+j.id)}
 for(const event of manifest.events||[])if(!jobs.has(event.job)||!['message','callback','host'].includes(event.event)||(event.event==='message'&&!event.commands?.length&&!event.prefixes?.length)||(event.event==='host'&&!event.types?.length))errors.push('消息或宿主事件触发配置无效')
 if(manifest.http&&!exists(manifest.http.entry))errors.push('http.entry 必须是目录内存在的文件')
 if(manifest.icon&&(!exists(manifest.icon)||!/\.(svg|png|webp)$/.test(manifest.icon)))errors.push('icon 必须是目录内存在的 svg/png/webp')
 if(manifest.menu&&!manifest.ui)errors.push('menu 需要 ui.entry')
 const listenerIDs=new Set();for(const l of manifest.listeners||[]){if(!manifest.http||!id.test(l.id)||listenerIDs.has(l.id)||!Number.isInteger(l.port)||l.port<1||l.port>65535)errors.push('监听端口配置无效：'+l.id);listenerIDs.add(l.id)}
 const settingKeys=new Set(),settingTypes=['text','password','textarea','number','boolean','select','path','url'];for(const f of manifest.settings||[]){if(!f.key||settingKeys.has(f.key)||!f.label||!settingTypes.includes(f.type)||(f.type==='select'&&!f.options?.length))errors.push('设置项无效：'+f.key);settingKeys.add(f.key)}
 const inspect=dir=>{for(const name of readdirSync(dir)){if(['.git','node_modules','build','releases'].includes(name))continue;const file=resolve(dir,name),info=lstatSync(file),rel=relative(root,file).split(sep).join('/');if(info.isSymbolicLink())errors.push('源码不能含符号链接：'+rel);else if(info.isDirectory())inspect(file)}};inspect(root)
 return {manifest,errors}
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href){try{const result=checkProject(process.argv[2]||'.');if(result.errors.length){console.error(result.errors.join('\n'));process.exitCode=1}else console.log(`通过：${result.manifest.id} ${result.manifest.version}。此检查不证明安全或站点业务成功；安装时宿主再次解析实际代码。`)}catch(e){console.error(e.message);process.exitCode=1}}
