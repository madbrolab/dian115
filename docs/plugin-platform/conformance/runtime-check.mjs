// Runtime validation from the public schema, with no host-source dependency.
export function validateRuntime(runtime, schema) {
  if (!runtime || typeof runtime !== 'object' || Array.isArray(runtime)) throw new Error('runtime must be an object')
  if (!['process', 'wasm'].includes(runtime.kind)) throw new Error('unsupported runtime.kind')
  const contract = schema.$defs?.[runtime.kind + 'Runtime']
  if (!contract?.properties) throw new Error('runtime schema is unavailable')
  for (const key of contract.required || []) {
    if (!(key in runtime)) throw new Error(`runtime.${key} is required`)
  }
  for (const [key, value] of Object.entries(runtime)) {
    let rule = contract.properties[key]
    if (!rule) throw new Error(`runtime.${key} is unsupported for ${runtime.kind}`)
    if (rule.$ref) rule = schema.$defs[rule.$ref.split('/').pop()]
    const fail = detail => { throw new Error(`runtime.${key} ${detail}`) }
    if (rule.const !== undefined && value !== rule.const) fail(`must be ${rule.const}`)
    if (rule.type === 'integer') {
      if (!Number.isSafeInteger(value)) fail('must be an integer')
      if (value < rule.minimum || value > rule.maximum) fail(`must be between ${rule.minimum} and ${rule.maximum}`)
    }
    if (rule.type === 'string') {
      if (typeof value !== 'string') fail('must be a string')
      if (rule.minLength !== undefined && value.length < rule.minLength) fail('is too short')
      if (rule.maxLength !== undefined && value.length > rule.maxLength) fail('is too long')
      if (rule.pattern && !new RegExp(rule.pattern).test(value)) fail('does not match the public schema')
    }
  }
}
