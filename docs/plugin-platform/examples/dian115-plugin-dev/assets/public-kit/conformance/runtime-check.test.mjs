import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { validateRuntime, validateJobSchedules } from './runtime-check.mjs'

const schema = JSON.parse(readFileSync(new URL('../manifest.schema.json', import.meta.url)))
const runtime = { kind: 'wasm', entry: 'runtime/plugin.wasm', protocol: 'dian115:wasm@1' }
test('runtime follows public schema defaults and limits', () => {
  assert.equal(validateRuntime({ ...runtime, timeout_ms: 120000, background_timeout_ms: 300000 }, schema).kind, 'wasm')
  for (const changes of [{ kind: 'process' }, { protocol: 'wrong' }, { timeout_ms: 180000 }, { resident: 'true' }, { entry: '../plugin.wasm' }, { memory_mb: 513 }, { unknown: 1 }]) assert.throws(() => validateRuntime({ ...runtime, ...changes }, schema))
})
test('cron validates cadence, ranges and identities', () => {
  const job = schedule => [{ id: 'refresh', handler: 'refresh', default_schedule: schedule, allow_overlap: false }]
  for (const schedule of ['*/5 * * * *', '0 * * * *', '0 0 1 1 *', '0,59 0 1 * *']) assert.doesNotThrow(() => validateJobSchedules(job(schedule)))
  for (const schedule of ['* * * * *', '0,59 * * * *', '0 0 * * * *', '60 * * * *', '*/0 * * * *']) {
    assert.throws(() => validateJobSchedules(job(schedule)), schedule)
  }
  assert.throws(() => validateJobSchedules([...job('*/5 * * * *'), ...job('*/5 * * * *')]))
})
test('manual recoverable jobs use the same identifiers and optional schedule as the host', () => {
  const job = { id: 'refresh', handler: 'refresh', recovery_handler: 'refresh-recover' }
  assert.doesNotThrow(() => validateJobSchedules([job]))
  assert.throws(() => validateJobSchedules([job, { ...job, id: 'other' }]))
  assert.doesNotThrow(() => validateJobSchedules([{ ...job, default_schedule: '' }]))
  for (const changes of [{ id: 'REFRESH' }, { id: 123 }, { handler: 123 }, { extra: true }, { default_schedule: ['*/5 * * * *'] }, { handler: 'x'.repeat(81) }, { handler: 'a..b' }, { recovery_handler: 'a..b' }, { recovery_handler: '' }, { default_schedule: null }]) {
    assert.throws(() => validateJobSchedules([{ ...job, ...changes }]))
  }
})
