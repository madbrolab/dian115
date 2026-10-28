import { existsSync, realpathSync, mkdirSync, mkdtempSync, cpSync, readFileSync, writeFileSync, renameSync, rmSync } from 'node:fs'
import { basename, dirname, resolve, relative, sep, isAbsolute } from 'node:path'
import { root, kit, json, parse, verify, cli } from './lib.mjs'
const inside = (base, path) => { const rel = relative(base,path); return !rel || (!rel.startsWith('..'+sep) && rel !== '..' && !isAbsolute(rel)) }
cli(() => {
  const args = parse(process.argv.slice(2), ['--dir','--id','--name','--publisher','--version','--compatibility','--template','--help'])
  if (args['--help']) { process.stdout.write('init.mjs --dir NEW_PATH --id publisher.plugin --name NAME --publisher AUTHOR [--version 1.0.0] [--compatibility RANGE] [--template minimal|complete]\n'); return }
  const lock = verify()
  for (const key of ['--dir','--id','--name','--publisher']) if (!args[key]?.trim()) throw new Error(`Required: ${key}`)
  const id = args['--id'], version = args['--version'] || '1.0.0', template = args['--template'] || 'minimal'
  if (!/^[a-z0-9](?:[a-z0-9.-]{1,126}[a-z0-9])$/.test(id) || id.includes('..')) throw new Error('Invalid plugin ID')
  if (!/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$/.test(version)) throw new Error('Version must be SemVer')
  for (const [key,max] of [['--name',80],['--publisher',100],['--compatibility',80]]) if (args[key] && (args[key].length>max || /[\x00-\x1f\x7f]/.test(args[key]))) throw new Error(`Invalid value: ${key}`)
  if (!['minimal','complete'].includes(template)) throw new Error('Template must be minimal or complete')
  const dest = resolve(args['--dir'])
  let ancestor=dest,tail=[]
  while(!existsSync(ancestor)){tail.unshift(basename(ancestor));ancestor=dirname(ancestor)}
  const physical=resolve(realpathSync(ancestor),...tail)
  if (inside(realpathSync(root),physical) || inside(root,dest)) throw new Error('Choose a project directory outside the installed skill')
  if (existsSync(dest)) throw new Error('Destination already exists; existing projects are never overwritten')
  mkdirSync(dirname(dest),{recursive:true})
  const stage = mkdtempSync(resolve(dirname(dest),'.dian115-init-'))
  try {
    const source = template === 'minimal' ? resolve(root,'assets/starter') : resolve(kit,'examples/complete-plugin')
    cpSync(source,stage,{recursive:true})
    cpSync(kit,resolve(stage,'.dian115'),{recursive:true})
    writeFileSync(resolve(stage,'.dian115/contract-lock.json'),JSON.stringify(lock,null,2)+'\n')
    const manifest = json(resolve(stage,'manifest.template.json')), market = json(resolve(stage,'market-entry.template.json'))
    Object.assign(manifest,{id,name:args['--name'],version,homepage:'https://example.invalid/'+id,repository:'https://example.invalid/source/'+id})
    manifest.publisher={name:args['--publisher'],key_id:'ed25519:REPLACED_BY_PACKAGER'}
    manifest.compatibility.dian115=args['--compatibility'] || manifest.compatibility.dian115
    Object.assign(market,{id,name:args['--name'],author:args['--publisher'],version,description:manifest.description,homepage:manifest.homepage,package_url:`https://example.invalid/releases/${id}-${version}.d115p`,permissions:manifest.permissions})
    const pkg=json(resolve(stage,'package.json'));pkg.name=id.replaceAll('.','-');pkg.version=version
    pkg.scripts.check='node .dian115/conformance/project-check.mjs --manifest manifest.template.json --market market-entry.template.json --build-root build --require-build'
    pkg.scripts['check:contract']='node .dian115/conformance/project-check.mjs --manifest manifest.template.json --market market-entry.template.json --build-root .dian115/no-build'
    pkg.scripts.package='node scripts/sign.mjs'
    for (const [name,value] of [['manifest.template.json',manifest],['market-entry.template.json',market],['package.json',pkg]]) writeFileSync(resolve(stage,name),JSON.stringify(value,null,2)+'\n')
    const packageLock=json(resolve(stage,'package-lock.json')); packageLock.name=pkg.name;packageLock.version=version;Object.assign(packageLock.packages[''],{name:pkg.name,version});writeFileSync(resolve(stage,'package-lock.json'),JSON.stringify(packageLock,null,2)+'\n')
    const go=readFileSync(resolve(stage,'go.mod'),'utf8').replace(/^module .+$/m,`module example.com/${pkg.name}`).replace('=> ../sdk','=> ./.dian115/examples/sdk')
    writeFileSync(resolve(stage,'go.mod'),go)
    // Import paths are rewritten only for known public template source files.
    for (const name of ['main.ts','AppPage.vue','preview-bridge.ts','actions.ts','background-job.ts']) {
      const path=resolve(stage,'src',name)
      if (existsSync(path)) writeFileSync(path,readFileSync(path,'utf8').replaceAll("'../../sdk/","'../.dian115/examples/sdk/"))
    }
    const main=resolve(stage,'src/main.ts');writeFileSync(main,readFileSync(main,'utf8').replaceAll("'example.complete-plugin'",JSON.stringify(id)))
    for (const file of ['build-runtime.mjs','package.mjs']) cpSync(resolve(kit,'examples/complete-plugin/scripts',file),resolve(stage,'scripts',file))
    cpSync(resolve(root,'assets/starter/scripts/sign.mjs'),resolve(stage,'scripts/sign.mjs'))
    writeFileSync(resolve(stage,'README.md'),`# ${args['--name']}\n\nDIAN115 第三方插件，${template} 模板，契约来源 ${lock.source_commit}。\n\n运行 npm ci、npm test、go test ./runtime（完整模板的 ABI 文件需 WASM 工具链）、npm run build、npm run check。构建前可用 npm run check:contract。\n\n通过项目外的 DIAN115_PLUGIN_SIGNING_KEY 指定作者密钥后运行 npm run package；首次明确添加 -- --generate-key。请替换 example.invalid 发布地址，完整模板还需删减演示权限并修改示例 Telegram 命令/关键词。生成包位于 releases/，可在插件中心 → 仓库与开发 → 导入本地插件。\n\n升级/重启/休眠保留持久数据；卸载清空插件数据，重装为空。取消/卸载不会撤销已发生的外部业务。\n\n本地 npm run dev 是内存模拟预览；真实 Host Call、唤醒、恢复与卸载需在宿主测试。已构建/实测范围应在发布前补充。公开协议见 .dian115/developer-guide.md。\n`)
    if (JSON.stringify(verify())!==JSON.stringify(lock)) throw new Error('Installed skill changed during generation; retry with one fixed version')
    // rename is atomic; recheck to avoid replacing a path created during generation.
    if (existsSync(dest)) throw new Error('Destination appeared during generation')
    renameSync(stage,dest)
    process.stdout.write(JSON.stringify({project:dest,template,id,source_commit:lock.source_commit,api_count:lock.api_count},null,2)+'\n')
  } finally { rmSync(stage,{recursive:true,force:true}) }
})
