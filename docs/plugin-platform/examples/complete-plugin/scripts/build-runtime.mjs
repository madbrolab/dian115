import { mkdirSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const output = join(root, 'build', 'runtime', 'plugin.wasm')
mkdirSync(dirname(output), { recursive: true })
// The host only accepts modules from a size-optimising toolchain: one module may
// not exceed 2 MiB, and the Go standard compiler alone links in a runtime that
// blows past that on its own. TinyGo compiles the same Go source without it.
const tinygo = process.env.TINYGO || 'tinygo'
const result = spawnSync(tinygo, ['build', '-target=wasi', '-buildmode=c-shared', '-opt=z', '-o', output, './runtime'], {
  cwd: root,
  env: { ...process.env },
  encoding: 'utf8',
  stdio: 'inherit',
})

if (result.error) {
  if (result.error.code === 'ENOENT') {
    throw new Error('tinygo was not found on PATH; install TinyGo to build a low-overhead plugin runtime')
  }
  throw result.error
}
if (result.status !== 0) throw new Error(`TinyGo runtime build failed with exit code ${result.status}`)
process.stdout.write(`Built low-overhead WASM runtime: ${output}\n`)
