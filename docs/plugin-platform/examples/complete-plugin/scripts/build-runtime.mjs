import { mkdirSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const output = join(root, 'build', 'runtime', 'plugin')
const requestedArch = String(process.env.DIAN115_PLUGIN_GOARCH || '').trim()
const goarch = requestedArch || (process.arch === 'arm64' ? 'arm64' : 'amd64')

if (!['amd64', 'arm64'].includes(goarch)) {
  throw new Error('DIAN115_PLUGIN_GOARCH must be amd64 or arm64')
}

mkdirSync(dirname(output), { recursive: true })
const result = spawnSync('go', ['build', '-trimpath', '-ldflags=-s -w', '-o', output, './runtime'], {
  cwd: root,
  env: { ...process.env, CGO_ENABLED: '0', GOOS: 'linux', GOARCH: goarch },
  encoding: 'utf8',
  stdio: 'inherit',
})

if (result.error) throw result.error
if (result.status !== 0) throw new Error(`Go runtime build failed with exit code ${result.status}`)
process.stdout.write(`Built static linux/${goarch} runtime: ${output}\n`)
