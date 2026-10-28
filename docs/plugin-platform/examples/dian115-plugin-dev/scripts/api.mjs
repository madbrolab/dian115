import { resolve } from 'node:path'
import { kit, json, parse, verify, cli } from './lib.mjs'
cli(() => {
  const args = parse(process.argv.slice(2), ['--query', '--method', '--json', '--help'])
  if (args['--help']) { process.stdout.write('api.mjs [--query text] [--method GET|POST|PUT|PATCH|DELETE|HEAD] [--json]\n'); return }
  verify()
  const method = args['--method']?.toUpperCase()
  if (method && !['GET','POST','PUT','PATCH','DELETE','HEAD'].includes(method)) throw new Error('Unknown HTTP method')
  const query = (args['--query'] || '').toLowerCase()
  const catalog = json(resolve(kit, 'host-api-catalog.json'))
  const entries = catalog.entries.filter(entry => (!method || entry.method === method) && Object.values(entry).join(' ').toLowerCase().includes(query))
  if (!entries.length) throw new Error('No matching public Host API; inspect the public contract before choosing another capability')
  process.stdout.write(args['--json'] ? JSON.stringify({ openapi_sha256: catalog.openapi_sha256, entries }, null, 2) + '\n' : entries.map(entry => `${entry.method} ${entry.path} | ${entry.title} | ${entry.risk}\n  ${entry.description}`).join('\n') + '\n')
})
