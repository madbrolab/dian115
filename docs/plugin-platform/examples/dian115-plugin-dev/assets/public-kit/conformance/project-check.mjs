import { existsSync, readFileSync, statSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { validateRuntime, validateJobSchedules } from './runtime-check.mjs'

const args = process.argv.slice(2)
const valueOf = (name, fallback) => {
  const index = args.indexOf(name)
  return index >= 0 && args[index + 1] ? args[index + 1] : fallback
}
const fail = (message) => {
  process.stderr.write(`Plugin project check: FAIL: ${message}\n`)
  process.exit(1)
}
const readJSON = (path, label) => {
  try {
    return JSON.parse(readFileSync(path, 'utf8'))
  } catch (error) {
    fail(`${label} is not valid JSON: ${error?.message || error}`)
  }
}
const isObject = (value) => value && typeof value === 'object' && !Array.isArray(value)
const requireText = (value, label, max) => {
  if (typeof value !== 'string' || !value.trim() || value.length > max) fail(`${label} is missing or too long`)
}
const methods = new Set(['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE'])
const manifestPath = resolve(valueOf('--manifest', 'manifest.template.json'))
const marketPath = resolve(valueOf('--market', 'market-entry.template.json'))
const buildRoot = resolve(valueOf('--build-root', 'build'))
const requireBuild = args.includes('--require-build')
const conformanceRoot = dirname(fileURLToPath(import.meta.url))
const openAPIPath = resolve(conformanceRoot, '..', 'openapi-v1.yaml')

if (!existsSync(manifestPath)) fail(`manifest not found: ${manifestPath}`)
if (!existsSync(marketPath)) fail(`market entry not found: ${marketPath}`)
const manifest = readJSON(manifestPath, 'manifest')
const market = readJSON(marketPath, 'market entry')

if (manifest.schema_version !== 1) fail('manifest.schema_version must be 1')
if (!/^[a-z0-9](?:[a-z0-9.-]{1,126}[a-z0-9])$/.test(manifest.id || '') || String(manifest.id).includes('..')) fail('manifest.id is invalid')
if (!/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$/.test(manifest.version || '')) fail('manifest.version must be SemVer')
requireText(manifest.name, 'manifest.name', 80)
requireText(manifest.description, 'manifest.description', 500)
requireText(manifest.default_locale, 'manifest.default_locale', 32)
requireText(manifest.publisher?.name, 'manifest.publisher.name', 100)
requireText(manifest.publisher?.key_id, 'manifest.publisher.key_id', 128)
requireText(manifest.compatibility?.dian115, 'manifest.compatibility.dian115', 80)
requireText(manifest.compatibility?.plugin_api, 'manifest.compatibility.plugin_api', 40)

try {
  validateRuntime(manifest.runtime, readJSON(resolve(conformanceRoot, '..', 'manifest.schema.json'), 'manifest schema'))
  validateJobSchedules(manifest.jobs)
} catch (error) {
  fail(error.message)
}
requireText(manifest.runtime?.entry, 'manifest.runtime.entry', 240)
if (manifest.ui?.mode !== 'page') fail('ui.mode must be page')
for (const field of ['entry', 'assets_root']) {
  const value = manifest.ui?.[field]
  requireText(value, `manifest.ui.${field}`, 240)
  if (value.startsWith('/') || value.includes('\\') || value.split('/').some(part => !part || part === '.' || part === '..')) fail(`manifest.ui.${field} must be a canonical package path`)
}
if (!manifest.ui.entry.endsWith('.html') || !manifest.ui.entry.startsWith(`${manifest.ui.assets_root}/`)) fail('HTML page entry must be below ui.assets_root')
if (Object.keys(manifest.ui).some(key => !['mode','entry','assets_root','icon'].includes(key))) fail('Unknown UI declaration field')

if (!isObject(manifest.permissions)) fail('manifest.permissions must be an object')
if (!Array.isArray(manifest.permissions.apis) || manifest.permissions.apis.length > 512) fail('permissions.apis must be an array of at most 512 entries')
if (!['standard', 'extended'].includes(manifest.permissions.host_access || 'standard')) fail('permissions.host_access must be standard or extended')
if ('capabilities' in manifest || 'account_access' in manifest || 'capabilities' in manifest.permissions || 'account_access' in manifest.permissions) {
  fail('legacy capabilities/account_access fields are not supported')
}
for (const [index, permission] of (manifest.permissions.apis || []).entries()) {
  if (!methods.has(permission?.method) || !String(permission?.path || '').startsWith('/api/')) fail(`permissions.apis[${index}] has an invalid method/path`)
  requireText(permission?.reason, `permissions.apis[${index}].reason`, 240)
  if ('optional' in permission && typeof permission.optional !== 'boolean') fail(`permissions.apis[${index}].optional must be boolean`)
}

if (!existsSync(openAPIPath)) fail(`public OpenAPI contract not found: ${openAPIPath}`)
const openAPI = readFileSync(openAPIPath, 'utf8')
if (new RegExp(`${['Direct', 'Response'].join('')}|与对应主项目接口一致`).test(openAPI)) fail('public OpenAPI still contains an opaque response placeholder')
const catalog = new Set()
const catalogPattern = /^    - method: (GET|HEAD|POST|PUT|PATCH|DELETE)\r?\n      path: (\/api\/\S+)$/gm
for (const match of openAPI.matchAll(catalogPattern)) catalog.add(`${match[1]} ${match[2]}`)
if (!catalog.size) fail('public OpenAPI Host API catalog could not be read')
for (const [index, permission] of (manifest.permissions.apis || []).entries()) {
  const key = `${permission.method} ${permission.path}`
  if (!catalog.has(key) && !permission.optional && manifest.permissions.host_access !== 'extended') fail(`permissions.apis[${index}] is not in the public Host API catalog: ${key}`)
}
for (const [index, permission] of (manifest.permissions.network || []).entries()) {
  let url
  try { url = new URL(permission?.origin) } catch { fail(`permissions.network[${index}].origin is invalid`) }
  if (!['http:', 'https:'].includes(url.protocol) || url.pathname !== '/' || url.search || url.hash || url.username || url.password) fail(`permissions.network[${index}].origin must be an HTTP(S) origin`)
  const declaredMethods = permission.methods === undefined ? ['GET'] : permission.methods
  if (!Array.isArray(declaredMethods) || !declaredMethods.length || declaredMethods.some((method) => !methods.has(method))) fail(`permissions.network[${index}].methods is invalid`)
  if (!['system', 'direct', 'required'].includes(permission.proxy_mode || 'system')) fail(`permissions.network[${index}].proxy_mode is invalid`)
  requireText(permission?.reason, `permissions.network[${index}].reason`, 240)
}
if ((manifest.events || []).length > 64 || (manifest.jobs || []).length > 32) fail('manifest events/jobs exceed limits')

if (market.id !== manifest.id || market.version !== manifest.version) fail('market id/version do not match manifest')
if (manifest.runtime.kind !== 'wasm') fail('manifest runtime.kind must be wasm; native process plugins are no longer supported')
const expectedTrust = 'wasm-sandbox'
// autostart is a fixed disclosure ("the host decides when this runs"), not a
// per-plugin switch, so it has to be present and true in every entry.
if (JSON.stringify(market.runtime) !== JSON.stringify({ kind: manifest.runtime.kind, protocol: manifest.runtime.protocol, autostart: true, trust_level: expectedTrust })) fail('market runtime disclosure must match the manifest and include autostart: true (fixed disclosure: the host owns the runtime lifecycle)')
if (JSON.stringify(market.permissions || {}) !== JSON.stringify(manifest.permissions || {})) fail('market permissions do not exactly match manifest')
if ('capabilities' in market || 'account_access' in market) fail('market entry uses removed permission fields')

const runtimePath = resolve(buildRoot, manifest.runtime.entry)
const pagePath = resolve(buildRoot, manifest.ui.entry)
if (requireBuild || existsSync(buildRoot)) {
  if (!existsSync(runtimePath) || !statSync(runtimePath).isFile()) fail(`runtime build is missing: ${runtimePath}`)
  const moduleBytes = readFileSync(runtimePath)
  if (moduleBytes.length < 8 || !moduleBytes.subarray(0, 8).equals(Buffer.from([0, 0x61, 0x73, 0x6d, 1, 0, 0, 0]))) fail('runtime build is not a valid WebAssembly module')
  // Mirror the host rule so authors get the answer here instead of at install
  // time. The Go standard compiler is refused because it links a runtime that
  // commits megabytes of linear memory per plugin.
  const wasmEntryMaxBytes = 2 << 20
  const markers = moduleBytes.toString('latin1')
  if (markers.includes('go:buildid') && markers.includes('runtime.gc')) {
    fail(`runtime build was produced by the Go standard compiler (${moduleBytes.length} bytes); build it with TinyGo or Rust/Zig/C instead`)
  }
  // The plugin protocol asks authors not to link encoding/json: the host keeps
  // a loaded plugin's compiled code, so one heavy package is paid for by every
  // plugin. This mirrors the host check so it is caught here, not at install.
  if (markers.includes('encoding/json')) {
    fail('runtime build links encoding/json (~1 MB); use the pluginjson helper from the reference runtime and read fields directly — see wasm-runtime-v1.md "构建要求"')
  }
  if (moduleBytes.length > wasmEntryMaxBytes) {
    fail(`runtime build is ${moduleBytes.length} bytes, above the ${wasmEntryMaxBytes} byte host budget`)
  }
  if (!existsSync(pagePath) || !statSync(pagePath).isFile()) fail(`HTML page entry is missing: ${pagePath}`)
  const html = readFileSync(pagePath, 'utf8')
  if (!/<html[\s>]|<!doctype\s+html/i.test(html)) fail('UI entry must be an HTML document')
  const assetRoot = resolve(buildRoot, manifest.ui.assets_root)
  for (const match of html.matchAll(/(?:src|href)=["']([^"'#]+)["']/gi)) {
    const reference = match[1]
    if (/^(?:https?:|data:|blob:|mailto:|tel:)/i.test(reference)) continue
    if (reference.startsWith('/')) fail(`Page assets must use relative URLs: ${reference}`)
    const asset = resolve(dirname(pagePath), reference.split(/[?#]/)[0])
    if (!asset.startsWith(assetRoot + '/') || !existsSync(asset) || !statSync(asset).isFile()) fail(`Page asset is missing or outside assets_root: ${reference}`)
  }
}

process.stdout.write(`Plugin project check: PASS (${manifest.id}@${manifest.version})\n`)
