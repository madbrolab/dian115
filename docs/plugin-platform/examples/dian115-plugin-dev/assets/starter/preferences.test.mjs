import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
const source=ts.transpileModule(readFileSync(new URL('./src/preferences.ts',import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}}).outputText
const {readDisplayName,saveDisplayName}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'))
test('missing preference has an empty default; failed and corrupt reads remain errors',async()=>{
 assert.equal(await readDisplayName({get:async()=>null}),'')
 await assert.rejects(readDisplayName({get:async()=>{throw Error('offline')}}),/offline/)
 await assert.rejects(readDisplayName({get:async()=>({name:'wrong'})}),/格式/)
})
test('cannot overwrite before restoration; save reports persistence failure',async()=>{
 let writes=0;const storage={set:async()=>{writes++}}
 await assert.rejects(saveDisplayName(storage,'new',false));assert.equal(writes,0)
 await saveDisplayName(storage,'new',true);assert.equal(writes,1)
 await assert.rejects(saveDisplayName({set:async()=>{throw Error('quota')}},'new',true),/quota/)
})
test('preference input is bounded before persistence',async()=>{
 let writes=0;await assert.rejects(saveDisplayName({set:async()=>{writes++}},'x'.repeat(121),true));assert.equal(writes,0)
})
