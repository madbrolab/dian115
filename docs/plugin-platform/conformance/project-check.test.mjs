import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'
const root = dirname(fileURLToPath(import.meta.url))
const manifestTemplate = JSON.parse(readFileSync(resolve(root, '../examples/complete-plugin/manifest.template.json'), 'utf8'))
const marketTemplate = JSON.parse(readFileSync(resolve(root, '../examples/complete-plugin/market-entry.template.json'), 'utf8'))
function fixture(t) {
 const directory = mkdtempSync(resolve(tmpdir(), 'plugin-page-contract-'))
 t.after(() => rmSync(directory, { recursive: true, force: true }))
 const manifest = structuredClone(manifestTemplate)
 const build = resolve(directory, 'build')
 mkdirSync(resolve(build, 'runtime'), { recursive: true }); mkdirSync(resolve(build, 'frontend/dist/assets'), { recursive: true })
 writeFileSync(resolve(build, 'runtime/plugin.wasm'), Buffer.from([0,97,115,109,1,0,0,0]))
 writeFileSync(resolve(build, 'frontend/dist/assets/app.js'), 'document.body.dataset.loaded="yes"')
 const html = '<!doctype html><html><script type="module" src="./assets/app.js"></script></html>'
 writeFileSync(resolve(build, 'frontend/dist/index.html'), html)
 writeFileSync(resolve(directory, 'market.json'), JSON.stringify(marketTemplate))
 function run() {
  writeFileSync(resolve(directory, 'manifest.json'), JSON.stringify(manifest))
  return spawnSync(process.execPath, [resolve(root, 'project-check.mjs'), '--manifest', resolve(directory, 'manifest.json'), '--market', resolve(directory, 'market.json'), '--build-root', build, '--require-build'], { encoding: 'utf8' })
 }
 return { directory, manifest, build, html, run }
}
test('ordinary HTML needs no host framework declarations and resolves packaged assets', t => {
 const f = fixture(t), result = f.run(); assert.equal(result.status, 0, result.stderr)
})
test('missing entry, host-root asset URLs and missing scripts fail before packaging', t => {
 const f = fixture(t), entry = resolve(f.build, 'frontend/dist/index.html')
 for (const html of [f.html.replace('./assets/app.js','/assets/app.js'), f.html.replace('app.js','missing.js'), '<p>not a document</p>']) {
  writeFileSync(entry, html); const result = f.run(); assert.notEqual(result.status, 0, html)
 }
 rmSync(entry); assert.notEqual(f.run().status, 0)
})
test('non-HTML, escaping and unknown UI declarations are rejected', t => {
 const f = fixture(t)
 for (const declaration of [
  {mode:'page',entry:'frontend/dist/assets/app.js',assets_root:'frontend/dist'},
  {mode:'page',entry:'frontend/elsewhere/index.html',assets_root:'frontend/dist'},
  {mode:'page',entry:'../index.html',assets_root:'frontend/dist'},
  {mode:'page',entry:'frontend/dist/index.html',assets_root:'frontend/dist',module:'unused'},
 ]) { f.manifest.ui = declaration; assert.notEqual(f.run().status, 0, JSON.stringify(declaration)) }
})
