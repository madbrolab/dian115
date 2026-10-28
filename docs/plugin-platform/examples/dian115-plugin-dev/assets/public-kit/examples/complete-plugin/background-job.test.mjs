import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const source = readFileSync(new URL('./src/background-job.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } })
const { createBackgroundJobSession } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`)

function fixture() {
  const values = new Map()
  const calls = []
  const job = { job_ref: 'job_example', status: 'queued', cancellable: true }
  const api = {
    storage: {
      get: async key => values.get(key) ?? null,
      set: async (key, value) => { values.set(key, value) },
      remove: async key => { values.delete(key) },
    },
    jobs: {
      start: async (_name, id) => { calls.push(id); assert.equal(values.get('refresh-job-invocation'), id); return { ...job } },
      get: async () => ({ ...job }),
      cancel: async () => { job.status = 'cancelled' },
    },
  }
  let state
  const session = createBackgroundJobSession(api, value => { state = value }, () => 'inv_stable_example')
  return { session, api, values, calls, job, state: () => state }
}

test('restoring an existing job blocks premature and duplicate starts', async () => {
  const f = fixture()
  f.values.set('refresh-job-ref', f.job.job_ref)
  let release
  const get = f.api.storage.get
  f.api.storage.get = key => new Promise(resolve => { release = async () => resolve(await get(key)) })
  const restore = f.session.restore()
  await f.session.run('start')
  assert.deepEqual(f.calls, [])
  f.api.storage.get = get
  await release()
  await restore
  await f.session.run('start')
  assert.deepEqual(f.calls, [])
  assert.equal(f.state().job.status, 'queued')
})

test('a failed intent write is persisted again before retrying the start', async () => {
  const f = fixture()
  await f.session.restore()
  const set = f.api.storage.set
  f.api.storage.set = async () => { throw new Error('storage unavailable') }
  await assert.rejects(f.session.run('start'), /storage unavailable/)
  assert.deepEqual(f.calls, [])
  f.api.storage.set = set
  await f.session.run('start')
  assert.deepEqual(f.calls, ['inv_stable_example'])
  assert.equal(f.values.get('refresh-job-ref'), f.job.job_ref)
})

test('an accepted start with a lost response reuses the persisted invocation', async () => {
  const f = fixture()
  await f.session.restore()
  const start = f.api.jobs.start
  f.api.jobs.start = async (...args) => { await start(...args); throw new Error('response lost') }
  await assert.rejects(f.session.run('start'), /response lost/)
  f.api.jobs.start = start
  await f.session.run('start')
  assert.deepEqual(f.calls, ['inv_stable_example', 'inv_stable_example'])
  assert.equal(f.values.has('refresh-job-invocation'), false)
})

test('explicit cancellation reads the final job without starting or polling', async () => {
  const f = fixture()
  f.values.set('refresh-job-ref', f.job.job_ref)
  await f.session.restore()
  await f.session.run('cancel')
  assert.equal(f.state().job.status, 'cancelled')
  assert.deepEqual(f.calls, [])
})
