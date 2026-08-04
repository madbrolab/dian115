#!/usr/bin/env node

import fs from 'node:fs/promises'
import path from 'node:path'
import process from 'node:process'
import readline from 'node:readline'
import { Readable } from 'node:stream'
import { createGunzip } from 'node:zlib'

const defaults = {
  sourceUrl: 'https://raw.githubusercontent.com/yanghuaioc/QuantumultX/main/CollectionRender.txt',
  exportDate: yesterdayUTC(),
  output: 'online-rules/collections/movie-community.yaml',
}

function yesterdayUTC() {
  const date = new Date(Date.now() - 24 * 60 * 60 * 1000)
  return [
    String(date.getUTCMonth() + 1).padStart(2, '0'),
    String(date.getUTCDate()).padStart(2, '0'),
    String(date.getUTCFullYear()),
  ].join('_')
}

function parseArgs(argv) {
  const options = { ...defaults }
  for (let index = 0; index < argv.length; index += 1) {
    const key = argv[index]
    const value = argv[index + 1]
    if (key === '--source-url' && value) options.sourceUrl = value
    else if (key === '--export-date' && value) options.exportDate = value
    else if (key === '--output' && value) options.output = value
    else throw new Error(`unknown or incomplete argument: ${key}`)
    index += 1
  }
  if (!/^\d{2}_\d{2}_\d{4}$/.test(options.exportDate)) {
    throw new Error('--export-date must use MM_DD_YYYY')
  }
  return options
}

async function fetchOK(url) {
  const response = await fetch(url, { redirect: 'follow' })
  if (!response.ok || !response.body) {
    throw new Error(`${url} returned HTTP ${response.status}`)
  }
  return response
}

function normalizeCollectionName(raw) {
  let name = String(raw || '').normalize('NFKC').trim()
  name = name.replace(/\s+系列\s*$/u, '').trim()
  name = name.replace(/^["'“”‘’]+|["'“”‘’]+$/gu, '').trim()
  const replacements = new Map([
    ['/', '／'], ['\\', '＼'], [':', '：'], ['*', '＊'], ['?', '？'],
    ['"', '＂'], ['<', '＜'], ['>', '＞'], ['|', '｜'],
  ])
  name = name.replace(/[\\/:*?"<>|]/g, value => replacements.get(value))
  name = name.replace(/[\u0000-\u001f\u007f]/g, '').replace(/\s+/g, ' ').trim()
  name = name.replace(/\.+$/g, '').trim()
  if ([...name].length > 120) name = [...name].slice(0, 120).join('').trim()
  if (/^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$/i.test(name)) name += ' 合集'
  return name
}

function parseCollectionRender(source) {
  const linePattern = /tmdb-\(\?:([0-9|]+)\)\\\}.*=>\s*(.+?)\/\\1\s*$/u
  const groups = new Map()
  let parsedLines = 0
  let rejectedLines = 0
  for (const rawLine of source.split(/\r?\n/)) {
    const line = rawLine.trim()
    if (!line) continue
    const match = linePattern.exec(line)
    if (!match) {
      rejectedLines += 1
      continue
    }
    parsedLines += 1
    const name = normalizeCollectionName(match[2])
    if (!name || name === '.' || name === '..') {
      rejectedLines += 1
      continue
    }
    if (!groups.has(name)) groups.set(name, new Set())
    const ids = groups.get(name)
    for (const value of match[1].split('|')) {
      const id = Number(value)
      if (Number.isSafeInteger(id) && id > 0) ids.add(id)
    }
  }
  return { groups, parsedLines, rejectedLines }
}

async function loadValidMovieIDs(exportDate, wanted) {
  const url = `https://files.tmdb.org/p/exports/movie_ids_${exportDate}.json.gz`
  const response = await fetchOK(url)
  const stream = Readable.fromWeb(response.body).pipe(createGunzip())
  const lines = readline.createInterface({ input: stream, crlfDelay: Infinity })
  const found = new Set()
  for await (const line of lines) {
    const match = /"id":(\d+)/.exec(line)
    if (!match) continue
    const id = Number(match[1])
    if (wanted.has(id)) found.add(id)
  }
  return { found, url }
}

function cleanGroups(groups, validMovieIDs) {
  const ownerByID = new Map()
  const cleaned = []
  let conflicts = 0
  let invalidIDs = 0
  let singleItemGroups = 0
  for (const [name, values] of groups) {
    const ids = []
    for (const id of [...values].sort((a, b) => a - b)) {
      if (!validMovieIDs.has(id)) {
        invalidIDs += 1
        continue
      }
      if (ownerByID.has(id)) {
        conflicts += 1
        continue
      }
      ownerByID.set(id, name)
      ids.push(id)
    }
    if (ids.length < 2) {
      singleItemGroups += 1
      for (const id of ids) ownerByID.delete(id)
      continue
    }
    cleaned.push({ name, tmdb_ids: ids })
  }
  cleaned.sort((a, b) => a.name < b.name ? -1 : a.name > b.name ? 1 : 0)
  return { cleaned, conflicts, invalidIDs, singleItemGroups }
}

function renderYAML(entries, sourceUrl, exportURL) {
  const lines = [
    '# dian115 movie collection vocabulary.',
    `# Source rules: ${sourceUrl}`,
    `# TMDB movie ID validation: ${exportURL}`,
    '# Movie and TV namespaces are intentionally isolated; this source only populates movie.',
    'schema_version: 1',
    'movie:',
  ]
  for (const entry of entries) {
    lines.push(`  - name: ${JSON.stringify(entry.name)}`)
    lines.push(`    tmdb_ids: [${entry.tmdb_ids.join(', ')}]`)
  }
  lines.push('tv: []', '')
  return lines.join('\n')
}

async function main() {
  const options = parseArgs(process.argv.slice(2))
  const sourceResponse = await fetchOK(options.sourceUrl)
  const source = await sourceResponse.text()
  const parsed = parseCollectionRender(source)
  const wanted = new Set()
  for (const ids of parsed.groups.values()) for (const id of ids) wanted.add(id)
  const movieExport = await loadValidMovieIDs(options.exportDate, wanted)
  const result = cleanGroups(parsed.groups, movieExport.found)
  if (!result.cleaned.length) throw new Error('generation produced no movie collections')
  const output = path.resolve(options.output)
  await fs.mkdir(path.dirname(output), { recursive: true })
  await fs.writeFile(output, renderYAML(result.cleaned, options.sourceUrl, movieExport.url), 'utf8')
  const idCount = result.cleaned.reduce((sum, entry) => sum + entry.tmdb_ids.length, 0)
  process.stdout.write(JSON.stringify({
    output,
    source_lines: parsed.parsedLines,
    source_unparsed: parsed.rejectedLines,
    source_unique_ids: wanted.size,
    movie_collections: result.cleaned.length,
    movie_ids: idCount,
    invalid_or_removed_movie_ids: result.invalidIDs,
    conflicting_assignments_removed: result.conflicts,
    groups_below_two_movies_removed: result.singleItemGroups,
  }, null, 2) + '\n')
}

main().catch(error => {
  process.stderr.write(`${error.stack || error.message}\n`)
  process.exitCode = 1
})
