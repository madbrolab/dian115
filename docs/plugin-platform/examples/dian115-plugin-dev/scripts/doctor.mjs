import { spawnSync } from 'node:child_process'
import { verify, parse, cli } from './lib.mjs'
cli(() => {
  const args = parse(process.argv.slice(2), ['--json', '--help'])
  if (args['--help']) { process.stdout.write('doctor.mjs [--json] (read-only; requires Node 20+, npm, Go 1.25+, TinyGo and wasm-opt)\n'); return }
  const lock = verify()
  const commands = [['node',process.execPath,['--version']],['npm','npm',['--version']],['go','go',['version']],['tinygo',process.env.TINYGO || 'tinygo',['version']],['wasm-opt',process.env.WASMOPT || 'wasm-opt',['--version']]]
  const tools = commands.map(([name,command,args]) => {
    const output = spawnSync(command, args, { encoding:'utf8', timeout:5000, shell:false })
    const version = (output.stdout || output.stderr || '').trim().slice(0,300)
    let available = !output.error && output.status === 0
    if (name === 'node') available &&= Number(version.match(/v(\d+)/)?.[1] || 0) >= 20
    if (name === 'go') { const match = version.match(/go(\d+)\.(\d+)/); available &&= !!match && (Number(match[1]) > 1 || (Number(match[1]) === 1 && Number(match[2]) >= 25)) }
    return {name,command,available,version,error:output.error ? output.error.code || output.error.message : undefined}
  })
  const report = {ready:tools.every(tool=>tool.available),tested:lock.toolchain,tools}
  process.stdout.write(args['--json'] ? JSON.stringify(report,null,2)+'\n' : tools.map(tool=>`${tool.available?'OK':'MISSING/UNSUPPORTED'} ${tool.name}: ${tool.version || tool.error || 'unavailable'}`).join('\n')+`\nTested toolchain: ${JSON.stringify(lock.toolchain)}\n`)
  if (!report.ready) process.exitCode=1
})
