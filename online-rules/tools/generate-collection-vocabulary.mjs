#!/usr/bin/env node

import fs from 'node:fs/promises'
import path from 'node:path'
import process from 'node:process'
import readline from 'node:readline'
import { Readable } from 'node:stream'
import { createGunzip } from 'node:zlib'

const defaultSourceRef = 'b305943deedeb82bc0f8c6797ef1dae1eb70d5ff'

const defaults = {
  sourceRef: defaultSourceRef,
  sourceUrl: `https://raw.githubusercontent.com/yanghuaioc/QuantumultX/${defaultSourceRef}/CollectionRender.txt`,
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
  let customSourceURL = false
  let customSourceRef = false
  for (let index = 0; index < argv.length; index += 1) {
    const key = argv[index]
    const value = argv[index + 1]
    if (key === '--source-url' && value) {
      options.sourceUrl = value
      customSourceURL = true
    }
    else if (key === '--source-ref' && value) {
      options.sourceRef = value
      customSourceRef = true
    }
    else if (key === '--export-date' && value) options.exportDate = value
    else if (key === '--output' && value) options.output = value
    else throw new Error(`unknown or incomplete argument: ${key}`)
    index += 1
  }
  if (customSourceURL && !customSourceRef) options.sourceRef = 'custom-unpinned-source'
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

function normalizeCollectionName(raw, lineNumber) {
  let name = String(raw || '').normalize('NFC').trim()
  const sourceName = name
  const replacements = new Map([
    ['/', '／'], ['\\', '＼'], [':', '：'], ['*', '＊'], ['?', '？'],
    ['"', '＂'], ['<', '＜'], ['>', '＞'], ['|', '｜'],
  ])
  name = name.replace(/[\\/:*?"<>|]/g, value => replacements.get(value))
  if (/[\u0000-\u001f\u007f]/u.test(name)) {
    throw new Error(`source line ${lineNumber} collection name contains control characters`)
  }
  if (!name || name === '.' || name === '..') {
    throw new Error(`source line ${lineNumber} collection name is empty or unsafe`)
  }
  if (name.endsWith('.')) {
    throw new Error(`source line ${lineNumber} collection name ends with a dot: ${JSON.stringify(sourceName)}`)
  }
  if ([...name].length > 120) {
    throw new Error(`source line ${lineNumber} collection name exceeds 120 characters`)
  }
  const deviceBase = name.split('.', 1)[0].trim()
  if (/^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$/i.test(deviceBase)) {
    throw new Error(`source line ${lineNumber} collection name is a reserved device name`)
  }
  return { name, sanitized: name !== sourceName }
}

function parseCollectionRender(source) {
  const linePattern = /tmdb-\(\?:([0-9|]+)\)\\\}.*=>\s*(.+?)\/\\1\s*$/u
  const groups = new Map()
  let parsedLines = 0
  let rejectedLines = 0
  let sanitizedNames = 0
  const rejectedExamples = []
  for (const [index, rawLine] of source.split(/\r?\n/).entries()) {
    const line = rawLine.trim()
    if (!line) continue
    const match = linePattern.exec(line)
    if (!match) {
      rejectedLines += 1
      if (rejectedExamples.length < 10) rejectedExamples.push({ line: index + 1, text: line })
      continue
    }
    parsedLines += 1
    const normalized = normalizeCollectionName(match[2], index + 1)
    const name = normalized.name
    if (normalized.sanitized) sanitizedNames += 1
    if (!groups.has(name)) groups.set(name, new Set())
    const ids = groups.get(name)
    for (const value of match[1].split('|')) {
      const id = Number(value)
      if (Number.isSafeInteger(id) && id > 0) ids.add(id)
    }
  }
  return { groups, parsedLines, rejectedLines, rejectedExamples, sanitizedNames }
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
  const ownersByID = new Map()
  const invalidIDs = new Set()
  for (const [name, values] of groups) {
    for (const id of values) {
      if (!validMovieIDs.has(id)) {
        invalidIDs.add(id)
        continue
      }
      if (!ownersByID.has(id)) ownersByID.set(id, new Set())
      ownersByID.get(id).add(name)
    }
  }
  const preferredSeriesOwnerByID = new Map()
  const ambiguousIDs = new Map()
  for (const [id, owners] of ownersByID) {
    if (owners.size <= 1) continue
    const names = [...owners]
    const bases = new Set(names.map(name => name.replace(/\s+系列\s*$/u, '').trim()))
    const seriesNames = names.filter(name => /\s+系列\s*$/u.test(name))
    if (bases.size === 1 && seriesNames.length === 1) {
      preferredSeriesOwnerByID.set(id, seriesNames[0])
      continue
    }
    ambiguousIDs.set(id, owners)
  }
  const cleaned = []
  let singleItemGroups = 0
  for (const [name, values] of groups) {
    const ids = []
    for (const id of [...values].sort((a, b) => a - b)) {
      if (!validMovieIDs.has(id) || ambiguousIDs.has(id)) continue
      const preferredOwner = preferredSeriesOwnerByID.get(id)
      if (preferredOwner && preferredOwner !== name) continue
      ids.push(id)
    }
    if (ids.length < 2) {
      singleItemGroups += 1
      continue
    }
    cleaned.push({ name, tmdb_ids: ids })
  }
  cleaned.sort((a, b) => a.name < b.name ? -1 : a.name > b.name ? 1 : 0)
  return { cleaned, ambiguousIDs, preferredSeriesOwnerByID, invalidIDs, singleItemGroups }
}

function renderYAML(entries, sourceUrl, sourceRef, exportURL, result) {
  const lines = [
    '# dian115 CollectionRender-derived movie grouping vocabulary.',
    `# Source rules: ${sourceUrl}`,
    `# Source revision: ${sourceRef}`,
    `# TMDB movie ID existence check (not official Collection membership): ${exportURL}`,
    `# Equivalent source aliases were resolved in favor of names ending in "系列": ${result.preferredSeriesOwnerByID.size}`,
    `# Ambiguous IDs assigned to multiple source names were excluded: ${result.ambiguousIDs.size}`,
    '# Source target names are preserved, including the terminal word "系列".',
    '# Movie and TV namespaces are isolated; this source only populates verified movie IDs.',
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
  if (parsed.rejectedLines > 0) {
    throw new Error(`source contains ${parsed.rejectedLines} unparsed non-empty lines: ${JSON.stringify(parsed.rejectedExamples)}`)
  }
  const wanted = new Set()
  for (const ids of parsed.groups.values()) for (const id of ids) wanted.add(id)
  const movieExport = await loadValidMovieIDs(options.exportDate, wanted)
  const result = cleanGroups(parsed.groups, movieExport.found)
  if (!result.cleaned.length) throw new Error('generation produced no movie collections')
  const output = path.resolve(options.output)
  await fs.mkdir(path.dirname(output), { recursive: true })
  await fs.writeFile(output, renderYAML(result.cleaned, options.sourceUrl, options.sourceRef, movieExport.url, result), 'utf8')
  const idCount = result.cleaned.reduce((sum, entry) => sum + entry.tmdb_ids.length, 0)
  const ambiguousExamples = [...result.ambiguousIDs]
    .sort(([left], [right]) => left - right)
    .slice(0, 20)
    .map(([id, owners]) => ({ id, owners: [...owners].sort() }))
  process.stdout.write(JSON.stringify({
    output,
    source_ref: options.sourceRef,
    source_lines: parsed.parsedLines,
    source_unparsed: parsed.rejectedLines,
    source_names_sanitized_for_filesystem: parsed.sanitizedNames,
    source_unique_ids: wanted.size,
    movie_collections: result.cleaned.length,
    movie_ids: idCount,
    invalid_or_removed_movie_ids: result.invalidIDs.size,
    equivalent_series_alias_ids_resolved: result.preferredSeriesOwnerByID.size,
    ambiguous_ids_excluded: result.ambiguousIDs.size,
    ambiguous_examples: ambiguousExamples,
    groups_below_two_movies_removed: result.singleItemGroups,
  }, null, 2) + '\n')
}

main().catch(error => {
  process.stderr.write(`${error.stack || error.message}\n`)
  process.exitCode = 1
})
