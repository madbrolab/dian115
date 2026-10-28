import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const source = readFileSync(new URL('./src/preview-bridge.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } })
const { createPreviewBridge } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`)
const fixture = () => createPreviewBridge({ revision: 1, actionCount: 0 }, ['refresh', 'other'])

test('preview uses detached state and real action-result shapes', async () => {
  const api = fixture()
  assert.equal(api.capabilities.storage, 'host-ui-v1')
  const before = await api.getState()
  before.state.revision = 99
  assert.equal((await api.refresh()).revision, 1)
  const result = await api.invokeAction('refresh')
  assert.match(result.invocation_id, /^inv_/)
  assert.equal(result.replayed, false)
  assert.equal(result.result.status, 'succeeded')
  const state = await api.getState()
  assert.equal(state.etag, `"${state.state_version}"`)
  assert.equal((await api.invokeAction('external-link')).result.url, 'https://example.com/oauth/start')
  assert.equal((await api.invokeAction('fetch-local')).result.status, 'failed')
  assert.equal((await api.invokeAction('unknown-action')).result.status, 'failed')
  await assert.rejects(api.invokeAction('refresh', { value: 1n }), /JSON|BigInt/)
})

test('preview actions preserve stable IDs, detached replays and conflict checks', async () => {
  const api = fixture()
  const first = await api.invokeAction('refresh', { value: 1 }, 'inv_action_stable')
  first.result.message = 'changed by caller'
  const replay = await api.invokeAction('refresh', { value: 1 }, 'inv_action_stable')
  assert.equal(replay.replayed, true)
  assert.equal(replay.invocation_id, 'inv_action_stable')
  assert.notEqual(replay.result.message, first.result.message)
  assert.equal((await api.getState()).state.actionCount, 1)
  await assert.rejects(api.invokeAction('refresh', { value: 2 }, 'inv_action_stable'), /invocation_conflict/)
  await assert.rejects(api.invokeAction('external-link', { value: 1 }, 'inv_action_stable'), /invocation_conflict/)
  await assert.rejects(api.invokeAction('refresh', {}, 'invalid'), /invalid_invocation_id/)
})

test('preview storage matches JSON copy, key, quota and installation boundaries', async () => {
  const api = fixture()
  assert.equal(await api.storage.get('constructor'), null)
  const original = { nested: { value: 1 } }
  await api.storage.set('settings', original)
  original.nested.value = 2
  const saved = await api.storage.get('settings')
  saved.nested.value = 3
  assert.equal((await api.storage.get('settings')).nested.value, 1)
  assert.equal(await fixture().storage.get('settings'), null)
  await assert.rejects(api.storage.set('a..b', 1), /invalid_storage_key/)
  await assert.rejects(api.storage.set('large', 'x'.repeat(16 * 1024)), /quota_exceeded/)
  assert.equal(await api.storage.get('large'), null)
  await api.storage.clear()
  assert.equal(await api.storage.get('settings'), null)
})

test('preview jobs deduplicate, reject conflicts and retain cancellation', async () => {
  const api = fixture()
  await assert.rejects(api.jobs.start('missing', 'inv_preview1'), /job_not_declared/)
  const job = await api.jobs.start('refresh', 'inv_preview1')
  await assert.rejects(api.jobs.resume(job.job_ref), /本地预览/)
  assert.equal(job.status, 'queued')
  assert.equal((await api.jobs.start('refresh', 'inv_preview1')).job_ref, job.job_ref)
  await assert.rejects(api.jobs.start('other', 'inv_preview1'), /invocation_conflict/)
  assert.deepEqual(await api.jobs.cancel(job.job_ref), { status: 'cancellation_requested' })
  await new Promise(resolve => setTimeout(resolve, 10))
  assert.equal((await api.jobs.get(job.job_ref)).status, 'cancelled')
  assert.equal((await api.jobs.cancel(job.job_ref)).job.status, 'cancelled')
  await assert.rejects(fixture().jobs.get(job.job_ref), /resource_not_found/)
  const completed = await api.jobs.start('refresh', 'inv_preview2')
  await new Promise(resolve => setTimeout(resolve, 10))
  const latest = await api.jobs.get(completed.job_ref)
  assert.equal(latest.status, 'succeeded')
  assert.equal(latest.result.status, 'accepted')
})
