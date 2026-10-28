import { readFileSync, readdirSync, lstatSync } from 'node:fs'
import { resolve, relative, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createHash } from 'node:crypto'
export const root = fileURLToPath(new URL('../', import.meta.url))
export const kit = resolve(root, 'assets/public-kit')
export const sha = data => createHash('sha256').update(data).digest('hex')
export const json = path => JSON.parse(readFileSync(path, 'utf8'))
export function walk(directory) {
  const paths = []
  for (const name of readdirSync(directory).sort()) {
    const path = resolve(directory, name), info = lstatSync(path)
    if (info.isSymbolicLink()) throw new Error(`Symlink is not allowed in skill resources: ${path}`)
    if (info.isDirectory()) paths.push(...walk(path))
    else if (info.isFile()) paths.push(path)
    else throw new Error(`Unsupported resource: ${path}`)
  }
  return paths
}
export function verify() {
  const lock = json(resolve(root, 'contract-lock.json'))
  if (lock.schema_version !== 1 || lock.skill !== 'dian115-plugin-dev' || !/^[a-f0-9]{40}$/.test(lock.source_commit)) throw new Error('Invalid contract lock')
  const actual = walk(resolve(root, 'assets')).map(path => relative(root, path).split(sep).join('/')).sort()
  if (JSON.stringify(actual) !== JSON.stringify(Object.keys(lock.files).sort())) throw new Error('Skill resource inventory differs from contract lock')
  for (const path of actual) {
    if (!path.startsWith('assets/') || path.split('/').includes('..') || sha(readFileSync(resolve(root, path))) !== lock.files[path]) throw new Error(`Resource integrity failed: ${path}`)
  }
  const catalog = json(resolve(kit, 'host-api-catalog.json'))
  if (catalog.openapi_sha256 !== sha(readFileSync(resolve(kit, 'openapi-v1.yaml'))) || catalog.entries.length !== lock.api_count) throw new Error('API catalog does not match locked OpenAPI')
  return lock
}
export function parse(args, allowed) {
  const result = {}
  for (let i = 0; i < args.length; i++) {
    const key = args[i]
    if (!allowed.includes(key)) throw new Error(`Unknown argument: ${key}`)
    if (key === '--json' || key === '--help') result[key] = true
    else {
      const value = args[++i]
      if (!value || value.startsWith('--')) throw new Error(`Missing value: ${key}`)
      if (key in result) throw new Error(`Repeated argument: ${key}`)
      result[key] = value
    }
  }
  return result
}
export function cli(work) {
  try { work() } catch (error) { process.stderr.write(`${error.message}\n`); process.exitCode = 1 }
}
