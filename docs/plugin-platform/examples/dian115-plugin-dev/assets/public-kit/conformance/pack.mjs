import { readFileSync, readdirSync, lstatSync, writeFileSync } from 'node:fs'
import { resolve, relative, sep, isAbsolute } from 'node:path'
import { deflateRawSync } from 'node:zlib'
import { createHash } from 'node:crypto'
import { pathToFileURL } from 'node:url'

const crcTable = Uint32Array.from({ length: 256 }, (_, n) => { for (let i = 0; i < 8; i++) n = n & 1 ? 0xedb88320 ^ n >>> 1 : n >>> 1; return n >>> 0 })
function crc32(body) { let value = 0xffffffff; for (const n of body) value = crcTable[(value ^ n) & 255] ^ value >>> 8; return (value ^ 0xffffffff) >>> 0 }
export function packPlugin(directory, output) {
  const root = resolve(directory), target = resolve(output), targetRelative = relative(root, target)
  if (!target.toLowerCase().endsWith('.dian115p')) throw Error('输出文件必须使用 .dian115p 后缀')
  if (!targetRelative.startsWith('..' + sep) && !isAbsolute(targetRelative)) throw Error('请将生成包放在源码目录之外，避免重复打包')
  const manifest = JSON.parse(readFileSync(resolve(root, 'plugin.json'), 'utf8'))
  if (manifest.schema_version !== 3 || !/^[a-z0-9]+(?:[.-][a-z0-9]+)*$/.test(manifest.id) || !manifest.name || !manifest.version) throw Error('plugin.json 需要有效的 v3 清单')
  const sources = []
  let total = 0
  function visit(directory) {
    for (const entry of readdirSync(directory, { withFileTypes: true }).sort((a, b) => Buffer.compare(Buffer.from(a.name), Buffer.from(b.name)))) {
      if (entry.name === '.git' || entry.name === 'node_modules') continue
      const absolute = resolve(directory, entry.name), stat = lstatSync(absolute)
      if (stat.isSymbolicLink()) throw Error('源码包不包含软链接：' + entry.name)
      if (stat.isDirectory()) { visit(absolute); continue }
      if (!stat.isFile()) throw Error('源码包只包含普通文件')
      const name = relative(root, absolute).split(sep).join('/')
      if (/[\\\0]/.test(name)) throw Error('源码文件路径无效')
      total += stat.size
      if (total > 512 * 1024 * 1024 || sources.length >= 65535) throw Error('源码包超过传输容量，请移除无关依赖和缓存')
      sources.push({ name: Buffer.from(name), plain: readFileSync(absolute) })
    }
  }
  visit(root)
  const names = new Set(sources.map(file => file.name.toString()))
  for (const entry of [manifest.ui?.entry, ...(manifest.jobs || []).map(job => job.entry)].filter(Boolean)) if (!names.has(entry)) throw Error('入口文件不存在：' + entry)
  if (!manifest.ui && !manifest.jobs?.length) throw Error('插件必须包含页面或后台任务')
  const local = [], central = []
  let offset = 0
  for (const { name, plain } of sources) {
    if (name.length > 65535) throw Error('源码路径过长')
    const compressed = deflateRawSync(plain), crc = crc32(plain)
    const header = Buffer.alloc(30)
    header.writeUInt32LE(0x04034b50); header.writeUInt16LE(20, 4); header.writeUInt16LE(0x800, 6); header.writeUInt16LE(8, 8)
    header.writeUInt32LE(crc, 14); header.writeUInt32LE(compressed.length, 18); header.writeUInt32LE(plain.length, 22); header.writeUInt16LE(name.length, 26)
    local.push(header, name, compressed)
    const record = Buffer.alloc(46)
    record.writeUInt32LE(0x02014b50); record.writeUInt16LE(20, 4); record.writeUInt16LE(20, 6); record.writeUInt16LE(0x800, 8); record.writeUInt16LE(8, 10)
    record.writeUInt32LE(crc, 16); record.writeUInt32LE(compressed.length, 20); record.writeUInt32LE(plain.length, 24); record.writeUInt16LE(name.length, 28); record.writeUInt32LE(offset, 42)
    central.push(record, name); offset += header.length + name.length + compressed.length
  }
  const end = Buffer.alloc(22), index = Buffer.concat(central)
  end.writeUInt32LE(0x06054b50); end.writeUInt16LE(sources.length, 8); end.writeUInt16LE(sources.length, 10); end.writeUInt32LE(index.length, 12); end.writeUInt32LE(offset, 16)
  const archive = Buffer.concat([...local, index, end])
  writeFileSync(target, archive, { flag: 'wx' })
  return { id: manifest.id, file: target, bytes: archive.length, sha256: createHash('sha256').update(archive).digest('hex') }
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const [directory, output] = process.argv.slice(2)
  if (!directory || !output) throw Error('用法：node pack.mjs <插件源码目录> <目录外的插件.dian115p>')
  console.log(JSON.stringify(packPlugin(directory, output), null, 2))
}
