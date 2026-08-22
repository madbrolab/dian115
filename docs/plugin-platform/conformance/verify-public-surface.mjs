import { spawnSync } from 'node:child_process'

const args = process.argv.slice(2)
const refIndex = args.indexOf('--ref')
const ref = refIndex >= 0 ? args[refIndex + 1] : ''
const command = ref ? ['ls-tree', '-r', '--name-only', ref] : ['ls-files']
const result = spawnSync('git', command, { encoding: 'utf8' })
if (result.status !== 0) throw new Error(result.stderr || `git ${command.join(' ')} failed`)

const files = result.stdout.split(/\r?\n/).map((value) => value.trim()).filter(Boolean)
const alwaysForbidden = [
  /(?:^|\/)(?:node_modules|build|releases)(?:\/|$)/,
  /(?:^|\/)(?:developer-|publisher-).*(?:\.pem|\.key)$/i,
  /\.d115p$/i,
]
const mainSourceForbidden = [
  /^cmd\//,
  /^internal\//,
  /^frontend\/src\//,
  /^frontend\/(?:package(?:-lock)?\.json|vite\.config\.(?:js|ts)|tsconfig.*\.json)$/,
  /^(?:go\.mod|go\.sum|Dockerfile|docker-compose\.ya?ml)$/,
  /^scripts\//,
  /^vendor\//,
  /^(?:dist|config|logs|tmp|temp|cache)\//,
]
const allowedPluginExample = /^docs\/plugin-platform\/examples\//
const violations = files.filter((file) => alwaysForbidden.some((pattern) => pattern.test(file)) || (!allowedPluginExample.test(file) && mainSourceForbidden.some((pattern) => pattern.test(file))))

if (violations.length) {
  process.stderr.write('Public surface check failed. Main project source or release material is tracked:\n')
  for (const file of violations) process.stderr.write(`- ${file}\n`)
  process.exit(1)
}
process.stdout.write(`Public surface check passed: ${files.length} tracked files inspected${ref ? ` at ${ref}` : ''}.\n`)
