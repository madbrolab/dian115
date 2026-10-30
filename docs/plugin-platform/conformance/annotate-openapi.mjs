// Applies api-glossary.json and api-cookbook.json to openapi-v3.json.
// Every cookbook example is validated against the operation schema first.
//   node annotate-openapi.mjs          write
//   node annotate-openapi.mjs --check  fail if the spec is not up to date or an example is invalid
import { readFileSync, writeFileSync } from 'node:fs'
const root = new URL('../', import.meta.url)
const specURL = new URL('openapi-v3.json', root)
const original = readFileSync(specURL, 'utf8')
const doc = JSON.parse(original)
const glossary = JSON.parse(readFileSync(new URL('api-glossary.json', import.meta.url), 'utf8')).fields
const cookbook = JSON.parse(readFileSync(new URL('api-cookbook.json', import.meta.url), 'utf8')).operations
const errors = []
const resolve = node => {
  for (let i = 0; node && node.$ref && i < 8; i++) node = node.$ref.slice(2).split('/').reduce((v, k) => v?.[k], doc)
  return node
}

// 1. Glossary: describe recurring fields and parameters that have no description yet.
let described = 0
const seen = new Set()
const walk = schema => {
  if (!schema || typeof schema !== 'object' || seen.has(schema)) return
  seen.add(schema)
  for (const [name, prop] of Object.entries(schema.properties || {})) {
    if (prop && typeof prop === 'object' && !prop.$ref && !prop.description && glossary[name] && glossary[name].scope !== 'param') { prop.description = glossary[name].description; described++ }
    walk(prop)
  }
  for (const key of ['items', 'additionalProperties']) walk(schema[key])
  for (const key of ['allOf', 'anyOf', 'oneOf']) for (const s of schema[key] || []) walk(s)
}
for (const schema of Object.values(doc.components.schemas)) walk(schema)
for (const ops of Object.values(doc.paths)) for (const op of Object.values(ops)) {
  if (!op || typeof op !== 'object') continue
  for (const p of op.parameters || []) if (!p.$ref && !p.description && glossary[p.name]) { p.description = glossary[p.name].description; described++ }
  for (const content of Object.values(op.requestBody?.content || {})) walk(content.schema)
}

// 1b. Schema-specific field descriptions from the cookbook (override generic text).
const cookbookSchemas = JSON.parse(readFileSync(new URL('api-cookbook.json', import.meta.url), 'utf8')).schemas || {}
for (const [key, text] of Object.entries(cookbookSchemas)) {
  const [schemaName, field] = key.split('.')
  const prop = doc.components.schemas[schemaName]?.properties?.[field]
  if (!prop) { errors.push(`${key}: 契约中不存在该字段`); continue }
  if (prop.$ref) continue
  if (prop.description !== text) { prop.description = text; described++ }
}

// 2. Cookbook: validate and attach descriptions and examples.
const typeOf = v => Array.isArray(v) ? 'array' : v === null ? 'null' : Number.isInteger(v) ? 'integer' : typeof v
function validate(value, schema, at, out) {
  schema = resolve(schema)
  if (!schema || Object.keys(schema).length === 0) return
  if (schema.anyOf || schema.oneOf) {
    const branches = schema.anyOf || schema.oneOf, base = { ...schema }; delete base.anyOf; delete base.oneOf
    if (Object.keys(base).length) validate(value, base, at, out)
    if (!branches.some(b => { const e = []; validate(value, { ...base, ...resolve(b) }, at, e); return e.length === 0 })) out.push(`${at}: 不满足任一分支`)
    return
  }
  if (schema.const !== undefined && value !== schema.const) out.push(`${at}: 应为 ${JSON.stringify(schema.const)}`)
  if (schema.enum && !schema.enum.includes(value)) out.push(`${at}: 不在枚举 ${schema.enum.join('/')}`)
  const t = schema.type, actual = typeOf(value)
  if (t && !(t === actual || (t === 'number' && actual === 'integer') || (Array.isArray(t) && t.includes(actual)))) { out.push(`${at}: 类型应为 ${t}，实际 ${actual}`); return }
  if (actual === 'object') {
    for (const r of schema.required || []) if (!(r in value)) out.push(`${at}: 缺少必填字段 ${r}`)
    for (const [k, v] of Object.entries(value)) {
      if (schema.properties?.[k]) validate(v, schema.properties[k], `${at}.${k}`, out)
      else if (schema.additionalProperties === false || (schema.properties && schema.additionalProperties === undefined)) out.push(`${at}: 契约中没有字段 ${k}`)
    }
  }
  if (actual === 'array' && schema.items) value.forEach((v, i) => validate(v, schema.items, `${at}[${i}]`, out))
}
for (const [key, entry] of Object.entries(cookbook)) {
  const [method, path] = key.split(' ')
  const op = doc.paths[path]?.[method.toLowerCase()]
  if (!op) { errors.push(`${key}: 契约中不存在`); continue }
  if (entry.description) op.description = entry.description
  if (entry.query) {
    const names = new Set((op.parameters || []).map(resolve).filter(p => p.in === 'query').map(p => p.name))
    for (const name of new URLSearchParams(entry.query).keys()) if (!names.has(name)) errors.push(`${key}: 示例查询参数 ${name} 不在契约中`)
    op['x-example-query'] = entry.query
  }
  if (entry.request !== undefined) {
    const content = resolve(op.requestBody)?.content?.['application/json']
    if (!content) { errors.push(`${key}: 没有 JSON 请求体`); continue }
    const out = []; validate(entry.request, content.schema, 'request', out)
    errors.push(...out.map(e => `${key}: ${e}`))
    if (op.requestBody.$ref) op.requestBody = JSON.parse(JSON.stringify(resolve(op.requestBody)))
    op.requestBody.content['application/json'].example = entry.request
  }
  if (entry.response !== undefined) {
    const status = op.responses['200'] ? '200' : Object.keys(op.responses).find(s => /^2/.test(s))
    if (op.responses[status]?.$ref) op.responses[status] = JSON.parse(JSON.stringify(resolve(op.responses[status])))
    const content = op.responses[status]?.content?.['application/json']
    if (!content) { errors.push(`${key}: 没有 JSON 成功响应`); continue }
    const out = []; validate(entry.response, content.schema, 'response', out)
    errors.push(...out.map(e => `${key}: ${e}`))
    content.example = entry.response
  }
}
if (errors.length) { console.error(errors.join('\n')); process.exit(1) }
const next = JSON.stringify(doc, null, 1) + '\n'
if (process.argv.includes('--check')) {
  if (next !== original) { console.error('openapi-v3.json 未应用最新的字段词汇表或示例，请运行 annotate-openapi.mjs'); process.exit(1) }
  console.log(`契约说明与示例一致：${Object.keys(cookbook).length} 个常用接口`)
} else {
  writeFileSync(specURL, next)
  console.log(`已补充 ${described} 处字段说明，写入 ${Object.keys(cookbook).length} 个接口的说明与示例`)
}
