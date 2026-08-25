import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const fail = (message) => {
  process.stderr.write(`OpenAPI contract check: FAIL: ${message}\n`)
  process.exit(1)
}

const contractPath = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'openapi-v1.yaml')
const source = readFileSync(contractPath, 'utf8')
const catalogStart = source.indexOf('x-dian115-host-apis:')
const catalogEnd = source.indexOf('x-dian115-subscription-host-apis:')
const pathsStart = source.indexOf('\npaths:')
const componentsStart = source.indexOf('\ncomponents:')
if (catalogStart < 0 || catalogEnd < catalogStart || pathsStart < 0 || componentsStart < pathsStart) fail('required OpenAPI sections are missing')

const catalog = new Set()
const catalogText = source.slice(catalogStart, catalogEnd)
for (const match of catalogText.matchAll(/^    - method: (GET|HEAD|POST|PUT|PATCH|DELETE)\r?\n      path: (\/api\/\S+)$/gm)) {
  const key = `${match[1]} ${match[2]}`
  if (catalog.has(key)) fail(`duplicate Host API catalog entry: ${key}`)
  catalog.add(key)
}
if (!catalog.size) fail('Host API catalog is empty')

const normalizePath = (value) => value.replace(/\{([^}]+)\}/g, ':$1')
const published = new Map()
const pathsText = source.slice(pathsStart, componentsStart)
const pathPattern = /^  (\/api\/[^\s]+):\r?\n([\s\S]*?)(?=^  \/api\/|(?![\s\S]))/gm
for (const pathMatch of pathsText.matchAll(pathPattern)) {
  const path = pathMatch[1]
  const block = pathMatch[2]
  const operations = [...block.matchAll(/^    (get|head|post|put|patch|delete):\r?$/gm)]
  for (let index = 0; index < operations.length; index += 1) {
    const operation = operations[index]
    const bodyStart = operation.index + operation[0].length
    const bodyEnd = index + 1 < operations.length ? operations[index + 1].index : block.length
    const body = block.slice(bodyStart, bodyEnd)
    if (!body.includes('x-dian115-in-process-only: true')) continue
    const key = `${operation[1].toUpperCase()} ${normalizePath(path)}`
    if (published.has(key)) fail(`duplicate published Host API operation: ${key}`)
    published.set(key, body)
  }
}

for (const key of catalog) if (!published.has(key)) fail(`catalog operation has no documented path operation: ${key}`)
for (const key of published.keys()) if (!catalog.has(key)) fail(`documented Host API operation is absent from catalog: ${key}`)

const placeholder = ['Direct', 'Response'].join('')
for (const [key, body] of published) {
  if (!body.includes('      responses:')) fail(`${key} has no responses`)
  if (!/        '2\d\d':\r?\n[\s\S]*?          content:\r?\n/.test(body)) fail(`${key} has no typed success response`)
  if (!body.includes("        '400':")) fail(`${key} has no explicit 400 response`)
  if (body.includes(placeholder) || body.includes('与对应主项目接口一致')) fail(`${key} uses an opaque response placeholder`)
  if (/^(POST|PUT|PATCH|DELETE) /.test(key) && !body.includes("#/components/parameters/IdempotencyKey")) {
    fail(`${key} does not document the required Idempotency-Key`)
  }
  const template = key.slice(key.indexOf(' ') + 1)
  for (const match of template.matchAll(/:([A-Za-z0-9_]+)/g)) {
    const openAPIName = `{${match[1]}}`
    if (!key.includes(`:${match[1]}`) || !source.includes(template.replace(`:${match[1]}`, openAPIName))) {
      fail(`${key} path parameter is not represented in the OpenAPI path`)
    }
  }
}

const componentNames = new Map()
let componentSection = ''
for (const line of source.slice(componentsStart).split(/\r?\n/)) {
  const sectionMatch = /^  (schemas|responses|parameters|requestBodies):$/.exec(line)
  if (sectionMatch) {
    componentSection = sectionMatch[1]
    if (!componentNames.has(componentSection)) componentNames.set(componentSection, new Set())
    continue
  }
  const nameMatch = /^    ([A-Za-z][A-Za-z0-9]*):$/.exec(line)
  if (componentSection && nameMatch) componentNames.get(componentSection).add(nameMatch[1])
}
for (const match of source.matchAll(/\$ref: '#\/components\/(schemas|responses|parameters|requestBodies)\/([^']+)'/g)) {
  const [, section, name] = match
  if (!componentNames.get(section)?.has(name)) fail(`unresolved component reference: ${section}/${name}`)
}

process.stdout.write(`OpenAPI contract check: PASS (${catalog.size} Host API operations)\n`)
