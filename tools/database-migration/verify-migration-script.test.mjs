import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync, existsSync, realpathSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'

const script = resolve(dirname(fileURLToPath(import.meta.url)), 'migrate-sqlite-to-pgsql.sh')
const dummyDSN = 'postgres://example:dummy%40password@postgres:5432/empty_db?sslmode=disable'
function fixture(t, name = 'config') {
  const root = realpathSync(mkdtempSync(join(tmpdir(), 'dian115-public-migration-')))
  t.after(() => rmSync(root, { recursive: true, force: true }))
  const config = join(root, name)
  const bin = join(root, 'bin')
  const capture = join(root, 'docker-call.json')
  mkdirSync(config)
  mkdirSync(bin)
  writeFileSync(join(config, 'dian115.db'), 'test fixture, no real database required')
  writeFileSync(join(bin, 'docker'), `#!${process.execPath}\nconst fs = require('node:fs');\nfs.writeFileSync(process.env.MIGRATION_MOCK_CAPTURE, JSON.stringify({args:process.argv.slice(2),dsn:process.env.DIAN115_PG_DSN}));\nconst status=Number(process.env.MIGRATION_MOCK_EXIT||0);\nif(!status) console.log('{"backend":"pgsql","ready":true}');\nprocess.exit(status);\n`, { mode: 0o755 })
  const env = { ...process.env, PATH: `${bin}:${process.env.PATH}`, DIAN115_PG_DSN: dummyDSN, MIGRATION_MOCK_CAPTURE: capture }
  delete env.DIAN115_IMAGE
  const run = (args, overrides = {}) => spawnSync('sh', [script, ...args], { env: { ...env, ...overrides }, cwd: root, encoding: 'utf8' })
  return { root, config, capture, env, run, call: () => JSON.parse(readFileSync(capture, 'utf8')) }
}

test('help explains the selected-image dependency without invoking Docker', t => {
  const f = fixture(t)
  const r = f.run(['--help'], { DIAN115_PG_DSN: '' })
  assert.equal(r.status, 0)
  assert.match(r.stdout, /\/usr\/local\/bin\/dian115-db/)
  assert.match(r.stdout, /新装 PostgreSQL 不需要迁移/)
  assert.equal(existsSync(f.capture), false)
})

test('default run forwards credentials via environment and invokes only the migrator', t => {
  const f = fixture(t)
  const r = f.run(['--config', f.config])
  assert.equal(r.status, 0, r.stderr)
  assert.deepEqual(f.call(), { args: ['run', '--rm', '--network', 'host', '--entrypoint', '/usr/local/bin/dian115-db', '--mount', `type=bind,"src=${f.config}",dst=/config`, '-e', 'DIAN115_DB_DRIVER=pgsql', '-e', 'DIAN115_PG_DSN', 'madbrolab/dian115:latest', 'migrate', '--db', '/config/dian115.db', '--timeout', '2h'], dsn: dummyDSN })
  assert.equal(f.call().args.join(' ').includes(dummyDSN), false)
  assert.equal((r.stdout + r.stderr).includes(dummyDSN), false)
  assert.match(r.stdout, /迁移完成/)
})

test('image, network, main filename and timeout can be selected', t => {
  const f = fixture(t)
  writeFileSync(join(f.config, 'custom.db'), 'fixture')
  const r = f.run(['--config', f.config, '--image', 'example/migrator@sha256:012345', '--network', 'dian115-storage', '--db', 'custom.db', '--timeout', '6h'])
  assert.equal(r.status, 0, r.stderr)
  const args = f.call().args
  assert.equal(args[args.indexOf('--network') + 1], 'dian115-storage')
  assert.deepEqual(args.slice(-6), ['example/migrator@sha256:012345', 'migrate', '--db', '/config/custom.db', '--timeout', '6h'])
})

test('the image variable is used, and an explicit image overrides it', t => {
  const f = fixture(t)
  let r = f.run(['--config', f.config], { DIAN115_IMAGE: 'example/app:compatible' })
  assert.equal(r.status, 0)
  assert.ok(f.call().args.includes('example/app:compatible'))
  r = f.run(['--config', f.config, '--image', 'example/app:chosen'], { DIAN115_IMAGE: 'example/app:compatible' })
  assert.equal(r.status, 0)
  assert.ok(f.call().args.includes('example/app:chosen'))
  assert.equal(f.call().args.includes('example/app:compatible'), false)
})

test('spaces, Chinese, commas, quotes and shell metacharacters remain literal paths', t => {
  const f = fixture(t, '配置 空格,"quoted";$(touch PWNED)')
  const r = f.run(['--config', f.config])
  assert.equal(r.status, 0, r.stderr)
  const args = f.call().args
  assert.equal(args[args.indexOf('--mount') + 1], `type=bind,"src=${f.config.replaceAll('"', '""')}",dst=/config`)
  assert.equal(existsSync(join(f.root, 'PWNED')), false)
})

test('relative configuration directory is resolved before mounting', t => {
  const f = fixture(t)
  const r = f.run(['--config', './config'])
  assert.equal(r.status, 0, r.stderr)
  assert.ok(f.call().args.includes(`type=bind,"src=${f.config}",dst=/config`))
})

test('missing PG connection fails before Docker is called', t => {
  const f = fixture(t)
  const r = f.run(['--config', f.config], { DIAN115_PG_DSN: '' })
  assert.equal(r.status, 2)
  assert.match(r.stderr, /DIAN115_PG_DSN/)
  assert.equal(existsSync(f.capture), false)
})

test('missing old main database fails without creating it', t => {
  const f = fixture(t)
  rmSync(join(f.config, 'dian115.db'))
  const r = f.run(['--config', f.config])
  assert.equal(r.status, 2)
  assert.match(r.stderr, /找不到旧 SQLite 主库/)
  assert.equal(existsSync(join(f.config, 'dian115.db')), false)
  assert.equal(existsSync(f.capture), false)
})

test('database paths cannot escape the selected configuration directory', t => {
  const f = fixture(t)
  for (const name of ['', '../other.db', 'nested/file.db', 'nested\\file.db']) {
    const r = f.run(['--config', f.config, '--db', name])
    assert.equal(r.status, 2, name)
    assert.equal(existsSync(f.capture), false)
  }
})

test('invalid and incomplete arguments do not start Docker', t => {
  const f = fixture(t)
  for (const args of [['--unknown'], ['--config'], ['--config', f.config, '--image', '--privileged']]) {
    assert.equal(f.run(args).status, 2)
    assert.equal(existsSync(f.capture), false)
  }
})

test('a failed migrator preserves its exit code and never reports success', t => {
  const f = fixture(t)
  const r = f.run(['--config', f.config], { MIGRATION_MOCK_EXIT: '17' })
  assert.equal(r.status, 17, r.stderr)
  assert.match(r.stderr, /迁移失败，退出码 17/)
  assert.equal(r.stdout.includes('迁移完成'), false)
  assert.equal(f.call().args[0], 'run')
})
