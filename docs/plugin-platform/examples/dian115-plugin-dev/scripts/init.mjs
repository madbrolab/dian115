import {cpSync,existsSync,readFileSync,writeFileSync} from 'node:fs'
import {resolve,isAbsolute} from 'node:path'
import {fileURLToPath} from 'node:url'
const [directory,id]=process.argv.slice(2)
if(!directory||!isAbsolute(directory)||(id||'').length>128||!/^[a-z0-9]+(?:[.-][a-z0-9]+)*$/.test(id||''))throw Error('用法：node init.mjs <新的绝对目录> <插件ID>')
if(existsSync(directory))throw Error('目标目录已存在；请直接修改现有项目')
const source=fileURLToPath(new URL('../assets/public-kit/examples/complete-plugin',import.meta.url));cpSync(source,directory,{recursive:true});const file=resolve(directory,'plugin.json'),manifest=JSON.parse(readFileSync(file,'utf8'));manifest.id=id;manifest.name=id;writeFileSync(file,JSON.stringify(manifest,null,2)+'\n');console.log('已创建 '+directory)
