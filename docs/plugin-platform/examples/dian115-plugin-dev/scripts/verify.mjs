import { verify, cli } from './lib.mjs'
cli(() => {
  const lock = verify()
  process.stdout.write(`Skill resources: PASS (${Object.keys(lock.files).length} files; ${lock.api_count} Host APIs; skill ${lock.version})\n`)
})
