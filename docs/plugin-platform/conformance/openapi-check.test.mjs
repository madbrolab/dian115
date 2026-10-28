import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const tool = fileURLToPath(new URL('./openapi-check.mjs', import.meta.url))
const source = readFileSync(new URL('../openapi-v1.yaml', import.meta.url), 'utf8')

test('published contract parses uniquely; duplicate paths/components fail', () => {
  const dir = mkdtempSync(join(tmpdir(), 'plugin-openapi-'))
  try {
    for (const [name, text, success, reason] of [
      ['valid', source, true, 'PASS'],
      ['path', source.replace('\npaths:\n', '\npaths:\n  /api/plugin-runtime/storage:\n    description: duplicate\n'), false, 'duplicate OpenAPI path'],
      ['schema', source.replace('\n  schemas:\n', '\n  schemas:\n    StorageUsage:\n      type: object\n'), false, 'duplicate component'],
    ]) {
      const path = join(dir, name + '.yaml')
      writeFileSync(path, text)
      const result = spawnSync(process.execPath, [tool, '--contract', path], { encoding: 'utf8' })
      assert.equal(result.status === 0, success, name + result.stdout + result.stderr)
      assert.ok((result.stdout + result.stderr).includes(reason))
    }
  } finally {
    rmSync(dir, { recursive: true, force: true })
  }
})

test('job contract documents accepted cancellation and its persistent states', () => {
  const query = source.split('\n  /api/plugin-host/jobs/{job_ref}:\n')[1]?.split('\n  /api/')[0]
  const cancel = source.split('\n  /api/plugin-host/jobs/{job_ref}/cancel:\n')[1]?.split('\n  /api/')[0]
  assert.match(query, /'200':[\s\S]*?#\/components\/schemas\/PluginJobEnvelope/)
  assert.match(cancel, /'202':[\s\S]*?#\/components\/schemas\/PluginJobCancellationEnvelope/)
  assert.match(cancel, /'409':/)
  assert.doesNotMatch(cancel, /'200':/)
  const job = source.split('\n    PluginJob:\n')[1]?.split('\n    PluginJobEnvelope:')[0]
  assert.match(job, /enum: \[queued, running, succeeded, failed, cancelled, attention_required\]/)
  assert.match(job, /required: \[job_ref, kind, status, progress, cancellable, created_at\]/)
  assert.doesNotMatch(job, /installation_id|idempotency_key|task_id/)
})
