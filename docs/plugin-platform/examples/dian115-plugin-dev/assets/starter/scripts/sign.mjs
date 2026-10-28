import { realpathSync, existsSync, mkdirSync } from 'node:fs'
import { basename, dirname, resolve, relative, isAbsolute, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'
const root=realpathSync(fileURLToPath(new URL('../',import.meta.url)))
const key=process.env.DIAN115_PLUGIN_SIGNING_KEY
if (!key || !isAbsolute(key)) throw new Error('Set DIAN115_PLUGIN_SIGNING_KEY to an absolute file path outside this project')
const args=process.argv.slice(2)
if (args.some(arg=>arg!=='--generate-key')) throw new Error('Only --generate-key is supported')
let existing=resolve(key),tail=[]
while (!existsSync(existing)) { tail.unshift(basename(existing));existing=dirname(existing) }
const physical=resolve(realpathSync(existing),...tail),rel=relative(root,physical)
if (!rel || (rel!=='..' && !rel.startsWith('..'+sep) && !isAbsolute(rel))) throw new Error('Signing key must be outside the project, including symlink targets')
if (!existsSync(key) && args.includes('--generate-key')) mkdirSync(dirname(key),{recursive:true,mode:0o700})
const output=spawnSync(process.execPath,[fileURLToPath(new URL('./package.mjs',import.meta.url)),...args],{cwd:root,env:{...process.env,DIAN115_PLUGIN_SIGNING_KEY:key},stdio:'inherit'})
if (output.error) throw output.error
process.exitCode=output.status ?? 1
