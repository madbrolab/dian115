// Shared by the isolated page script and extension pages. No credentials or DOM.
(() => {
  const EXTERNAL_KINDS = new Set(['share115', 'magnet', 'ed2k'])
  const label = { share115: '115 分享', magnet: '磁力', ed2k: 'ED2K' }
  const tokens = /ed2k:\/\/\|file\|[^|\r\n<>]+\|[0-9]+\|[a-f0-9]{32}\|[^\s<>"']*|(?:https?:\/\/|magnet:\?|ed2k:\/\/)[^\s<>"'【】《》\[\]，。；）]+/gi
  const trimEnd = value => value.replace(/[.,;!）)]+$/, '')
  function parse(value) {
    const raw = trimEnd(String(value || '').trim().replace(/&amp;/gi, '&'))
    if (new TextEncoder().encode(raw).length > 8192) return null
    if (/^ed2k:\/\//i.test(raw)) {
        const match = raw.match(/^ed2k:\/\/\|file\|([^|]+)\|([0-9]+)\|([a-f0-9]{32})\|(?:[^\s]*)$/i)
        if (!match || BigInt(match[2]) <= 0n || BigInt(match[2]) > 9223372036854775807n || !/\|\//.test(raw)) return null
        return { kind: 'ed2k', label: label.ed2k, key: 'ed2k:' + match[3].toLowerCase(), link: raw }
    }
    try {
      const url = new URL(raw)
      if (url.protocol === 'http:' || url.protocol === 'https:') {
        const host = url.hostname.toLowerCase().replace(/^www\./, '')
        if (!['115.com', '115cdn.com', 'share.115.com', 'share.115cdn.com'].includes(host) || url.username || url.password) return null
        const match = url.pathname.match(host.startsWith('share.') ? /^\/(?:s\/)?([a-z0-9]{6,64})\/?$/i : /^\/s\/([a-z0-9]{6,64})\/?$/i)
        if (!match) return null
        const password = (url.searchParams.get('password') || url.searchParams.get('receive_code') || url.searchParams.get('pwd') || '').trim()
        if (password && !/^[a-z0-9]{1,32}$/i.test(password)) return null
        const code = match[1]
        return { kind: 'share115', label: label.share115, key: 'share115:' + code.toLowerCase(), link: 'https://115.com/s/' + code + (password ? '?password=' + encodeURIComponent(password) : '') }
      }
      if (url.protocol === 'magnet:') {
        const hashes = url.searchParams.getAll('xt').filter(item => /^urn:btih:(?:[a-f0-9]{40}|[a-f0-9]{32}|[a-z2-7]{32})$/i.test(item))
        if (!hashes.length) return null
        let hash = hashes.find(item => /^urn:btih:/i.test(item)) || hashes[0]
        if (/^urn:btih:[a-z2-7]{32}$/i.test(hash) && !/^urn:btih:[a-f0-9]{32}$/i.test(hash)) {
          let bits = 0, data = 0, hex = ''
          for (const char of hash.slice(9).toUpperCase()) {
            data = (data << 5) | 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'.indexOf(char)
            bits += 5
            if (bits >= 8) { bits -= 8; hex += ((data >> bits) & 255).toString(16).padStart(2, '0') }
          }
          hash = 'urn:btih:' + hex
        }
        return { kind: 'magnet', label: label.magnet, key: 'magnet:' + hash.toLowerCase(), link: raw }
      }
    } catch {}
    return null
  }
  function extract(value) {
    const text = String(value || '')
    const results = []
    for (const match of text.matchAll(tokens)) {
      const item = parse(match[0])
      if (!item) continue
      const tail = text.slice(match.index + match[0].length, match.index + match[0].length + 40)
      results.push({ ...withAdjacentCode(item, tail), index: match.index, length: trimEnd(match[0]).length })
    }
    return results
  }
  function withAdjacentCode(item, tail) {
    if (item.kind !== 'share115' || item.link.includes('?password=')) return item
    // A code must immediately follow this share, never another resource.
    const code = String(tail || '').match(/^\s*(?:[（(]\s*)?(?:提取码|访问码|密码|提码|口令)\s*[:：]?\s*([a-z0-9]{4})(?:\b|$)/i)
    return code ? { ...item, link: item.link + '?password=' + encodeURIComponent(code[1]) } : item
  }
  function unique(items) {
    const byKey = new Map()
    for (const item of items || []) {
      if (!item || !EXTERNAL_KINDS.has(item.kind)) continue
      const previous = byKey.get(item.key)
      if (!previous || (item.kind === 'share115' && !previous.link.includes('?password=') && item.link.includes('?password='))) byKey.set(item.key, item)
    }
    return [...byKey.values()]
  }
  globalThis.Dian115Links = Object.freeze({ parse, extract, unique, withAdjacentCode, isExternal: kind => EXTERNAL_KINDS.has(kind) })
})()
