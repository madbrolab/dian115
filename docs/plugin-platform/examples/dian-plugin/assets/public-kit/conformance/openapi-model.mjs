// Shared helpers for reading openapi-v3.json: $ref resolution, operation
// listing and example generation from schemas plus the field glossary.
import { readFileSync } from 'node:fs'

export const root = new URL('../', import.meta.url)
export const doc = JSON.parse(readFileSync(new URL('openapi-v3.json', root), 'utf8'))
const glossary = JSON.parse(readFileSync(new URL('api-glossary.json', import.meta.url), 'utf8')).fields
export const methods = ['get', 'post', 'put', 'patch', 'delete', 'head']

export function resolve(node) {
  for (let i = 0; node && node.$ref && i < 8; i++) node = node.$ref.slice(2).split('/').reduce((v, k) => v?.[k], doc)
  return node
}
export const refName = node => (node?.$ref || '').split('/').pop()

export function operations() {
  const out = []
  for (const [path, ops] of Object.entries(doc.paths)) for (const method of methods) if (ops[method]) out.push({ path, method, op: ops[method] })
  return out
}

export const jsonContent = node => resolve(node)?.content?.['application/json']
export function successResponse(op) {
  const status = Object.keys(op.responses || {}).filter(s => /^2/.test(s)).sort()[0]
  return status ? { status, response: resolve(op.responses[status]) } : null
}
export const parameters = op => (op.parameters || []).map(resolve).filter(Boolean)

// sample builds a plausible value for a schema; glossary samples win for known field names.
export function sample(schema, name = '', depth = 0) {
  schema = resolve(schema)
  if (!schema || depth > 5) return null
  if (schema.example !== undefined) return schema.example
  if (name && glossary[name]?.sample !== undefined) return glossary[name].sample
  if (schema.const !== undefined) return schema.const
  if (schema.enum) return schema.enum[0]
  if (schema.default !== undefined) return schema.default
  for (const key of ['anyOf', 'oneOf', 'allOf']) if (schema[key]?.length) {
    const base = { ...schema }; delete base[key]
    return sample({ ...base, ...resolve(schema[key][0]) }, name, depth + 1)
  }
  const type = Array.isArray(schema.type) ? schema.type[0] : schema.type || (schema.properties ? 'object' : schema.items ? 'array' : '')
  switch (type) {
    case 'string':
      if (schema.format === 'date-time') return '2026-10-29T21:30:00+08:00'
      if (schema.format === 'uri') return 'https://example.com/'
      return name ? `<${name}>` : ''
    case 'integer': return schema.minimum > 0 ? schema.minimum : 0
    case 'number': return 0
    case 'boolean': return true
    case 'array': return schema.items ? [sample(schema.items, '', depth + 1)] : []
    case 'object': {
      const out = {}
      for (const [k, v] of Object.entries(schema.properties || {})) out[k] = sample(v, k, depth + 1)
      return out
    }
  }
  return null
}

export function typeLabel(schema) {
  const raw = schema
  schema = resolve(schema)
  if (!schema) return 'any'
  if (raw?.$ref) return refName(raw)
  if (schema.enum) return schema.enum.map(v => JSON.stringify(v)).join(' / ')
  if (schema.const !== undefined) return JSON.stringify(schema.const)
  const type = Array.isArray(schema.type) ? schema.type.join('/') : schema.type
  if (type === 'array') return `${typeLabel(schema.items)}[]`
  if (type) return schema.format ? `${type}(${schema.format})` : type
  if (schema.properties) return 'object'
  return 'any'
}

// fieldRows flattens object properties to dotted rows (two levels deep).
export function fieldRows(schema, prefix = '', depth = 0, out = []) {
  schema = resolve(schema)
  if (!schema || depth > 2) return out
  if (schema.type === 'array' || (!schema.properties && schema.items)) return fieldRows(schema.items, prefix ? `${prefix}[]` : '[]', depth, out)
  const required = new Set(schema.required || [])
  for (const [name, prop] of Object.entries(schema.properties || {})) {
    const key = prefix ? `${prefix}.${name}` : name
    const target = resolve(prop) || {}
    out.push({ key, type: typeLabel(prop), required: required.has(name), description: prop.description || target.description || '' })
    if (target.properties || (target.items && resolve(target.items)?.properties)) fieldRows(prop, key, depth + 1, out)
  }
  return out
}
