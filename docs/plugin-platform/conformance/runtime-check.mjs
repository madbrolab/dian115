import { readFileSync } from 'node:fs'
const [base,id,cookieFile]=process.argv.slice(2)
if(!base||!id||!cookieFile)throw Error('用法：node runtime-check.mjs <宿主URL> <插件ID> <仓库外Cookie文件>')
const cookie=readFileSync(cookieFile,'utf8').trim(),root=new URL('/api/extensions/v3/'+encodeURIComponent(id),base)
for(const suffix of ['', '/runs?limit=2','/storage?limit=2','/usage','/watches']){
 const response=await fetch(root.href+suffix,{headers:{cookie},signal:AbortSignal.timeout(30000),redirect:'error'})
 if(!response.ok)throw Error(`GET ${suffix||'/'} HTTP ${response.status}`)
 const data=await response.json();if(data===null)throw Error('响应为空');console.log(`通过：GET ${suffix||'安装详情'}`)
}
console.log('只读黑盒检查完成；未发送通知、登录站点、启动任务或修改文件。')
