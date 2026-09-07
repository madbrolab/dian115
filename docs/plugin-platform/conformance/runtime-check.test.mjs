import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { validateRuntime, validateJobSchedules } from './runtime-check.mjs'
const schema = JSON.parse(readFileSync(new URL('../manifest.schema.json', import.meta.url)))
const runtime = { kind: 'wasm', protocol: 'dian115:wasm@1', entry: 'runtime/plugin.wasm', timeout_ms: 120000, background_timeout_ms: 300000, memory_mb: 128 }
test('accepts a two-minute foreground budget and five-minute background job', () => {
  assert.doesNotThrow(() => validateRuntime(runtime, schema))
})
test('rejects the released 180000 ms installation regression', () => {
  assert.throws(() => validateRuntime({ ...runtime, timeout_ms: 180000 }, schema), /runtime.timeout_ms must be between 100 and 120000/)
})
test('validates kind/protocol pairing and rejects unsupported runtime fields', () => {
  assert.throws(() => validateRuntime({ ...runtime, protocol: 'dian115:process@1' }, schema), /protocol/)
  assert.throws(() => validateRuntime({ ...runtime, timeout_ms: 120000.5 }, schema), /integer/)
  assert.throws(() => validateRuntime({ ...runtime, action_path: '/action' }, schema), /unsupported/)
})
test('rejects one-minute jobs and short gaps across hour boundaries', () => {
  const check = schedule => validateJobSchedules([{ id: 'refresh', default_schedule: schedule }])
  assert.throws(() => check('* * * * *'), /at least five minutes/)
  assert.throws(() => check('*/7 * * * *'), /at least five minutes/)
  assert.doesNotThrow(() => check('*/5 * * * *'))
  assert.doesNotThrow(() => check('0 8 * * 1-5'))
})
