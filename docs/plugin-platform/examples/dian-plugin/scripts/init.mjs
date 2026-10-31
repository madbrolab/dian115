#!/usr/bin/env node
// Creates a plugin from a template.
//   node init.mjs <新的绝对目录> <插件ID> [--template starter|bot|daemon|webhook|lab] [--name 名称] [--author 作者]
import { cpSync, existsSync, readFileSync, writeFileSync } from 'node:fs'
import { isAbsolute, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const args = process.argv.slice(2), option = (name, fallback) => { const index = args.indexOf('--' + name); return index >= 0 ? args[index + 1] : fallback }
const [directory, id] = args
const template = option('template', 'starter')
const sources = { starter: '../assets/templates/starter', bot: '../assets/templates/bot', daemon: '../assets/templates/daemon', webhook: '../assets/templates/webhook', lab: '../assets/public-kit/examples/complete-plugin' }
if (!directory || !isAbsolute(directory) || (id || '').length > 128 || !/^[a-z0-9]+(?:[.-][a-z0-9]+)*$/.test(id || '') || !sources[template]) {
  throw Error('用法：node init.mjs <新的绝对目录> <插件ID> [--template starter|bot|daemon|webhook|lab] [--name 名称] [--author 作者]')
}
if (existsSync(directory)) throw Error('目标目录已存在；请直接修改现有项目')
cpSync(fileURLToPath(new URL(sources[template], import.meta.url)), directory, { recursive: true })
const file = resolve(directory, 'plugin.json'), manifest = JSON.parse(readFileSync(file, 'utf8'))
manifest.id = id
manifest.version = '0.1.0'
manifest.name = option('name', template === 'lab' ? id : manifest.name)
manifest.author = option('author', manifest.author || '')
writeFileSync(file, JSON.stringify(manifest, null, 2) + '\n')
console.log(`已创建 ${manifest.name}（${template}）：${directory}\n下一步：改代码后运行 node scripts/check.mjs ${directory}`)
