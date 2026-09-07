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

// Numeric cron contract, including the gap across the end of the hour.
export function validateJobSchedules(jobs = []) {
  if (!Array.isArray(jobs)) throw new Error('jobs must be an array')
  for (const job of jobs) {
    if (job.default_schedule === undefined) continue
    const error = message => { throw new Error(`job ${job.id}: ${message}`) }
    if (typeof job.default_schedule !== 'string') error('schedule must be a string')
    const fields = job.default_schedule.trim().split(/\s+/)
    if (fields.length !== 5) error('cron requires five numeric fields')
    const bounds = [[0, 59], [0, 23], [1, 31], [1, 12], [0, 6]]
    const expanded = fields.map((field, index) => {
      const [min, max] = bounds[index]
      const candidates = Array.from({ length: max - min + 1 }, (_, n) => n + min)
      const values = field.split(',').flatMap(part => {
        const match = /^(\*|(?:0|[1-9]\d*)(?:-(?:0|[1-9]\d*))?)(?:\/([1-9]\d*))?$/.exec(part)
        if (!match) error('invalid numeric cron field')
        const range = match[1] === '*' ? [min, max] : match[1].split('-').map(Number)
        const [start, end = start] = range, step = Number(match[2] || 1)
        if (start < min || end > max || end < start || step > candidates.length) error('cron field is outside its range')
        return candidates.filter(n => n >= start && n <= end && (n - start) % step === 0)
      })
      return [...new Set(values)].sort((a, b) => a - b)
    })
    const minutes = expanded[0]
    if (minutes.some((minute, i) => (i + 1 < minutes.length ? minutes[i + 1] : minutes[0] + 60) - minute < 5)) error('cron interval must be at least five minutes')
    if (fields[2] !== '*' && fields[4] !== '*') error('day-of-month and day-of-week cannot both be restricted')
  }
}
