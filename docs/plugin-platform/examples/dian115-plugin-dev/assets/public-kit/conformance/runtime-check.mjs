// Public contract validation. No main-project source or runtime is required.
export function validateRuntime(runtime, schema) {
  const contract = schema?.$defs?.wasmRuntime
  if (!contract || !runtime || typeof runtime !== 'object' || Array.isArray(runtime)) throw new Error('runtime must be an object described by manifest.schema.json')
  for (const key of contract.required) if (!(key in runtime)) throw new Error(`runtime.${key} is required`)
  for (const [key, value] of Object.entries(runtime)) {
    const rule = contract.properties[key]
    if (!rule) throw new Error(`runtime.${key} is not supported`)
    if ('const' in rule && value !== rule.const) throw new Error(`runtime.${key} must be ${rule.const}`)
    if (rule.type === 'integer' && (!Number.isSafeInteger(value) || value < rule.minimum || value > rule.maximum)) throw new Error(`runtime.${key} must be an integer between ${rule.minimum} and ${rule.maximum}`)
    if (rule.type === 'boolean' && typeof value !== 'boolean') throw new Error(`runtime.${key} must be boolean`)
  }
  const entry = runtime.entry
  if (typeof entry !== 'string' || !entry.endsWith('.wasm') || entry.length > 240 || entry.normalize('NFC') !== entry || /[\\\x00-\x1f:]/.test(entry) || entry.startsWith('/') || entry.split('/').some(part => !part || part === '.' || part === '..' || /[. ]$/.test(part))) throw new Error('runtime.entry must be a normalized relative .wasm package path')
  return runtime
}

function cronField(text, min, max) {
  const values = new Set()
  for (const item of text.split(',')) {
    const match = /^(\*|\d+(?:-\d+)?)(?:\/(\d+))?$/.exec(item)
    if (!match) throw new Error('jobs require numeric five-field cron expressions')
    const step = Number(match[2] || 1)
    if (!Number.isSafeInteger(step) || step < 1) throw new Error('cron step must be positive')
    let start = min, end = max
    if (match[1] !== '*') {
      const range = match[1].split('-').map(Number)
      start = range[0]; end = range[1] ?? (match[2] ? max : start)
    }
    if (start < min || end > max || end < start) throw new Error('cron field is outside its allowed range')
    for (let value = start; value <= end; value += step) values.add(value)
  }
  return [...values].sort((a, b) => a - b)
}

export function validateJobSchedules(jobs = []) {
  if (!Array.isArray(jobs) || jobs.length > 32) throw new Error('jobs must be an array of at most 32 entries')
  const ids = new Set()
  const handlers = new Set()
  for (const job of jobs) {
    if (!job || typeof job.id !== 'string' || !/^[a-z0-9]+(?:[._-][a-z0-9]+)*$/.test(job.id || '') || job.id.length > 80 || ids.has(job.id)) throw new Error('job id is invalid or duplicated')
    if (Object.keys(job).some(key => !['id','handler','default_schedule','allow_overlap','recovery_handler'].includes(key))) throw new Error('unknown job field')
    ids.add(job.id)
    if (typeof job.handler !== 'string' || !/^[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*$/.test(job.handler || '') || job.handler.length > 80) throw new Error('job handler is invalid')
    if (handlers.has(job.handler)) throw new Error('job handler is duplicated')
    handlers.add(job.handler)
    if ('recovery_handler' in job && (typeof job.recovery_handler !== 'string' || job.recovery_handler.length > 80 || !/^[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*$/.test(job.recovery_handler))) throw new Error('job recovery_handler is invalid')
    if ('allow_overlap' in job && typeof job.allow_overlap !== 'boolean') throw new Error('job allow_overlap must be boolean')
    if ('default_schedule' in job && typeof job.default_schedule !== 'string') throw new Error('job default_schedule must be a string')
    if (!('default_schedule' in job) || job.default_schedule === '') continue
    const fields = String(job.default_schedule || '').trim().split(/\s+/)
    if (fields.length !== 5) throw new Error('jobs require numeric five-field cron expressions')
    const [minutes, hours, days, months, weekdays] = fields.map((field, index) => cronField(field, ...[[0, 59], [0, 23], [1, 31], [1, 12], [0, 6]][index]))
    const times = hours.flatMap(hour => minutes.map(minute => hour * 60 + minute))
    for (let i = 1; i < times.length; i++) if (times[i] - times[i - 1] < 5) throw new Error('job interval must be at least five minutes')
    // Test actual adjacent allowed days, including month/year boundaries and
    // leap days. DOM/DOW use standard cron OR semantics when both are restricted.
    const dayWildcard = fields[2].startsWith('*'), weekWildcard = fields[4].startsWith('*')
    let previous = null
    for (let day = Date.UTC(2024, 0, 1); day < Date.UTC(2032, 0, 1); day += 86400000) {
      const date = new Date(day)
      if (!months.includes(date.getUTCMonth() + 1)) continue
      const dom = days.includes(date.getUTCDate()), dow = weekdays.includes(date.getUTCDay())
      if (!(dayWildcard || weekWildcard ? dom && dow : dom || dow)) continue
      if (previous !== null && (day / 60000 + times[0]) - previous < 5) throw new Error('job interval across day boundaries must be at least five minutes')
      previous = day / 60000 + times.at(-1)
    }
  }
  return jobs
}
