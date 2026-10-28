import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const source = readFileSync(new URL('./src/actions.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } })
const { invokeSavedAction } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`)

test('uncertain actions retain intent across page instances and replay the same ID', async () => {
  const values = new Map(); const calls = []; let lost = true
  const api = {
    storage: { get: async key => values.get(key) ?? null, set: async (key, value) => { values.set(key, structuredClone(value)) }, remove: async key => { values.delete(key) } },
    invokeAction: async (action, input, id) => {
      assert.equal(values.get('action-intent.'+action).invocationId, id)
      calls.push({ action, input, id })
      if (lost) throw new Error('response lost')
      return { invocation_id: id, replayed: true, result: { status: 'succeeded' } }
    },
  }
  await assert.rejects(invokeSavedAction(api, 'save', { value: 1 }, () => 'inv_original'), /response lost/)
  await assert.rejects(invokeSavedAction(api, 'save', { value: 2 }, () => 'inv_changed'), /尚未确认/)
  assert.equal(calls.length, 1)
  lost = false
  const result = await invokeSavedAction(api, 'save', { value: 1 }, () => 'inv_must_not_be_used')
  assert.equal(result.invocation_id, 'inv_original')
  assert.deepEqual(calls.map(call => call.id), ['inv_original', 'inv_original'])
  assert.equal(values.size, 0)
})

test('an action is never dispatched when its intent could not be saved', async () => {
  let called = false
  const api = { storage: { get: async () => null, set: async () => { throw new Error('storage failed') } }, invokeAction: async () => { called = true } }
  await assert.rejects(invokeSavedAction(api, 'save', {}, () => 'inv_save'), /storage failed/)
  assert.equal(called, false)
})

test('a lost cleanup acknowledgement does not turn confirmed success into failure', async () => {
  const values = new Map()
  const api = {
    storage: { get: async key => values.get(key) ?? null, set: async (key, value) => { values.set(key, value) }, remove: async key => { values.delete(key); throw new Error('cleanup response lost') } },
    invokeAction: async (_action, _input, id) => ({ invocation_id: id, replayed: false, result: { status: 'succeeded' } }),
  }
  const response = await invokeSavedAction(api, 'save', {}, () => 'inv_confirmed')
  assert.equal(response.result.status, 'succeeded')
  assert.equal(response.confirmation_pending, true)
  assert.equal(values.size, 0)
})
