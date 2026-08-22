import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import { resolve } from 'node:path'

const args = process.argv.slice(2)
const valueOf = (name, fallback) => {
  const index = args.indexOf(name)
  return index >= 0 && args[index + 1] ? args[index + 1] : fallback
}
const runtimePath = resolve(valueOf('--runtime', 'build/runtime/plugin'))
const timeoutMs = Math.max(1000, Number(valueOf('--timeout-ms', '5000')) || 5000)
const verbose = args.includes('--verbose')

if (!existsSync(runtimePath)) throw new Error(`runtime not found: ${runtimePath}`)
if (process.platform !== 'linux') throw new Error('runtime-smoke.mjs must run on Linux, WSL, or a Linux container')

const child = spawn(runtimePath, [], {
  cwd: resolve('.'),
  env: {
    DIAN115_PLUGIN_FILESYSTEM: 'private-root',
    DIAN115_PLUGIN_PACKAGE: '/package/runtime',
    DIAN115_PLUGIN_DATA: '/data',
    TMPDIR: '/tmp',
    PATH: '/usr/bin:/bin',
  },
  stdio: ['pipe', 'pipe', 'pipe'],
})

let buffer = Buffer.alloc(0)
let nextID = 1
const pending = new Map()
const exitPromise = new Promise((resolvePromise, rejectPromise) => {
  child.once('error', rejectPromise)
  child.once('exit', (code, signal) => {
    if (code === 0 && !signal) resolvePromise()
    else rejectPromise(new Error(`runtime exited with code=${code} signal=${signal}`))
  })
})

function frame(message) {
  const payload = Buffer.from(JSON.stringify(message), 'utf8')
  return Buffer.concat([
    Buffer.from(`Content-Length: ${payload.length}\r\nContent-Type: application/json\r\n\r\n`),
    payload,
  ])
}

function send(message) {
  child.stdin.write(frame(message))
}

function handle(message) {
  if (verbose && message.method) process.stderr.write(`[runtime] ${message.method}\n`)
  if (message.method) {
    if (message.method === 'host.telegram.register') {
      send({ jsonrpc: '2.0', id: message.id, result: { commands: message.params?.commands || [], keywords: message.params?.keywords || [] } })
    } else if (message.method === 'host.telegram.list' || message.method === 'host.telegram.unregister') {
      send({ jsonrpc: '2.0', id: message.id, result: { commands: [], keywords: [] } })
    } else if (message.method === 'host.log') {
      send({ jsonrpc: '2.0', id: message.id, result: { accepted: true } })
    } else if (message.method === 'host.ui.invalidate') {
      send({ jsonrpc: '2.0', id: message.id, result: { accepted: true } })
    } else if (message.method === 'host.call') {
      send({ jsonrpc: '2.0', id: message.id, result: { status: 200, headers: {}, body_base64: '' } })
    } else {
      send({ jsonrpc: '2.0', id: message.id, error: { code: -32601, message: 'method not provided by smoke host' } })
    }
    return
  }
  const waiter = pending.get(String(message.id))
  if (!waiter) return
  pending.delete(String(message.id))
  if (message.error) waiter.reject(new Error(`${message.error.code}: ${message.error.message}`))
  else waiter.resolve(message.result)
}

function parseFrames() {
  while (true) {
    const separator = buffer.indexOf(Buffer.from('\r\n\r\n'))
    if (separator < 0) return
    const headers = buffer.subarray(0, separator).toString('ascii').split('\r\n')
    const line = headers.find((value) => /^content-length:/i.test(value))
    const length = line ? Number(line.split(':', 2)[1].trim()) : NaN
    if (!Number.isInteger(length) || length <= 0 || length > 256 * 1024) throw new Error('invalid runtime response frame')
    const start = separator + 4
    if (buffer.length < start + length) return
    const payload = buffer.subarray(start, start + length)
    buffer = buffer.subarray(start + length)
    handle(JSON.parse(payload.toString('utf8')))
  }
}

child.stdout.on('data', (chunk) => {
  try {
    buffer = Buffer.concat([buffer, chunk])
    parseFrames()
  } catch (error) {
    child.kill('SIGTERM')
    process.stderr.write(`Plugin runtime smoke: FAIL: ${error?.message || error}\n`)
    process.exitCode = 1
  }
})
child.stderr.on('data', (chunk) => {
  if (verbose) process.stderr.write(chunk)
})
child.on('error', (error) => {
  for (const waiter of pending.values()) waiter.reject(error)
})

function request(method, params) {
  const id = `smoke-${nextID++}`
  return new Promise((resolvePromise, rejectPromise) => {
    const timer = setTimeout(() => {
      pending.delete(id)
      rejectPromise(new Error(`timeout waiting for ${method}`))
    }, timeoutMs)
    pending.set(id, {
      resolve: (value) => {
        clearTimeout(timer)
        resolvePromise(value)
      },
      reject: (error) => {
        clearTimeout(timer)
        rejectPromise(error)
      },
    })
    send({ jsonrpc: '2.0', id, method, params })
  })
}

try {
  const initialized = await request('runtime.initialize', {
    protocol: 'dian115:process@1',
    plugin_id: 'conformance.runtime-smoke',
    plugin_version: '1.0.0',
    installation_id: 1,
    locale: 'zh-CN',
    timezone: 'Asia/Shanghai',
  })
  if (!initialized || initialized.ready !== true) throw new Error('runtime.initialize did not return ready=true')

  const state = await request('runtime.invoke', {
    envelope: {
      op: 'state',
      invocation_id: 'smoke-state-1',
      payload: { view: 'main' },
    },
    background: false,
  })
  if (!state || typeof state.state_version !== 'string' || typeof state.etag !== 'string' || !state.state || typeof state.state !== 'object') {
    throw new Error('runtime state response does not match Plugin API v2')
  }

  const shutdown = await request('runtime.shutdown', { reason: 'conformance-smoke' })
  if (!shutdown || typeof shutdown !== 'object' || Array.isArray(shutdown)) throw new Error('runtime.shutdown did not return an object')
  await Promise.race([exitPromise, new Promise((_, rejectPromise) => setTimeout(() => rejectPromise(new Error('runtime did not exit after shutdown')), timeoutMs))])
  process.stdout.write('Plugin runtime smoke: PASS\n')
} catch (error) {
  child.kill('SIGTERM')
  process.stderr.write(`Plugin runtime smoke: FAIL: ${error?.message || error}\n`)
  process.exitCode = 1
}
