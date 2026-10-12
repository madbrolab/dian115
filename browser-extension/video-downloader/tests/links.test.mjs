import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import vm from 'node:vm'
import test from 'node:test'
const context = vm.createContext({ URL, BigInt, TextEncoder })
vm.runInContext(await readFile(new URL('../src/links.js', import.meta.url), 'utf8'), context)
const { parse, extract, unique } = context.Dian115Links
const hash = '0123456789abcdef0123456789abcdef01234567'
const ed = '1234567890abcdef1234567890abcdef'

test('ordinary video pages and 115 home/login pages do not become share links', () => {
  for (const value of ['https://www.bilibili.com/video/BV1wDhj6wEa8/', 'https://115.com/', 'https://115.com/?ct=home', 'https://115.com/login', 'https://evil.example/s/abc123', 'https://115.com.evil.example/s/abc123']) assert.equal(parse(value), null)
})
test('same-page duplicate shares collapse across supported hosts and keep extraction code', () => {
  const items = unique(extract('https://115.com/s/abc123 https://115cdn.com/s/abc123?password=x1y2 https://www.115.com/s/abc123 提取码：x1y2'))
  assert.equal(items.length, 1)
  assert.equal(items[0].link, 'https://115.com/s/abc123?password=x1y2')
})
test('same-page duplicate magnets collapse despite title and tracker differences', () => {
  const items = unique(extract(`magnet:?xt=urn:btih:${hash}&dn=One magnet:?xt=urn:btih:${hash.toUpperCase()}&dn=Two&tr=https%3A%2F%2Ftracker.example`))
  assert.equal(items.length, 1)
  assert.equal(items[0].kind, 'magnet')
})
test('same-page duplicate ed2k files collapse by content hash without changing the original URI', () => {
  const first = `ed2k://|file|a.mkv|100|${ed}|/`
  const items = unique(extract(`${first} ed2k://|file|b.mkv|100|${ed.toUpperCase()}|/`))
  assert.equal(items.length, 1)
  assert.equal(items[0].link, first)
})
test('different links remain independent and malformed URIs are ignored', () => {
  const items = unique(extract(`https://115.com/s/aaa111 https://115.com/s/bbb222 magnet:?xt=urn:btih:${hash} ed2k://|file|a|100|${ed}|/ magnet:?xt=broken ed2k://broken`))
  assert.equal(items.length, 4)
  assert.equal(parse('ed2k://|file|a|0|' + ed + '|/'), null)
})
test('html ampersands, adjacent share passwords and punctuation keep valid payloads', () => {
  const items = extract(`下载：https://115.com/s/abc123 提取码：a1b2，磁力：magnet:?xt=urn:btih:${hash}&amp;dn=One。`)
  assert.equal(items.length, 2)
  assert.equal(items[0].link, 'https://115.com/s/abc123?password=a1b2')
  assert.equal(items[1].link, `magnet:?xt=urn:btih:${hash}&dn=One`)
})

test('share password aliases and legacy hex magnets match the server contract', () => {
  assert.equal(parse('https://share.115cdn.com/abc123?pwd=a1b2').link, 'https://115.com/s/abc123?password=a1b2')
  assert.equal(parse('https://115.com/s/short'), null)
  assert.equal(parse('https://115.com/s/abc123?password=a%2Fb'), null)
  const legacy = 'abcdefabcdefabcdefabcdefabcdefab'
  assert.equal(parse('magnet:?xt=urn:btih:' + legacy).key, 'magnet:urn:btih:' + legacy)
  const base32 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
  const canonical = parse('magnet:?xt=urn:btih:' + base32).key
  assert.equal(unique(extract(`magnet:?xt=urn:btih:${base32} magnet:?xt=${canonical.slice(7)}`)).length, 1)
})

test('ed2k filenames may contain spaces without losing the resource', () => {
  const raw = `ed2k://|file|A Movie 2026.mkv|100|${ed}|/`
  assert.equal(extract('资源 ' + raw + ' 下载')[0].link, raw)
  assert.equal(parse(`ed2k://|file|huge|9223372036854775808|${ed}|/`), null)
})
