// 本地 WASM 测试台：模拟 dian115 宿主，验证插件运行时行为
// 用法：node scripts/wasm-harness.mjs [plugin.wasm]
//   HARNESS_DEBUG=1 输出 host.call 请求日志
import { readFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { WASI } from 'node:wasi'

const wasmPath = process.argv[2] || 'build/runtime/plugin.wasm'
const bytes = readFileSync(wasmPath)

// ---- 模拟宿主（强制 CAS：更新已有值时无 If-Match 的 PUT 返回 412）----
const storage = new Map() // key -> { value, etag }
let etagSeq = 0
let intentSeq = 100
const idemSeen = new Map() // idem key -> body hash

// ---- 有状态订阅池（用于检验「已删除订阅是否会重复订阅」）----
// intents：宿主当前真实存在的订阅；intentPosts：插件发起过的建订阅请求（含被宿主接受的）。
const intents = []
const intentPosts = [] // { tmdb_id, media_type, season, title }
let intentsApiFail = false // true 时模拟订阅池读取失败
// 豆瓣原名/又名接口（rexxar）请求记录，用于验证「只在标题搜不到时才走」与缓存
const aliasRequests = []
// Host Storage 读取记录（键名），用于验证「结果写回标题缓存后不再重复读豆瓣原名缓存」
const storageGets = []
// 豆瓣条目表：type 是条目的真实类型（剧集/电影），original/aka 是原名与又名。
// 真实豆瓣接口在类型不符时会 301 到正确地址，这里照同行为模拟。
const doubanSubjects = {
  // 《流人 第六季》：TMDB 里只有英文名 Slow Horses，靠原名才能识别
  36000001: { type: 'tv', original: 'Slow Horses Season 6', aka: ['翻盘特工队(港)', '外放特务组(台)', '驽马', '慢马'] },
  // 《驽马 第六季》：同一部剧的另一种译名（豆瓣另一条目），用它验证标题搜索
  // 不中时「豆瓣原名兜底」这条路径。
  36000002: { type: 'tv', original: 'Slow Horses Season 6', aka: ['流人', '慢马'] },
  // 《漫长的季节》：豆瓣是剧集；榜单把它当电影搜时必然搜不到，
  // 取原名时也会撞上类型不符 → 301，用于验证重定向纠正
  35123456: { type: 'tv', original: '漫长的季节', aka: [] },
}
function dropAllIntents() {
  // 模拟用户在 dian115 侧删除全部订阅
  intents.length = 0
}

// ---- 模拟数据 ----
const rssXMLMock = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item><title>漫长的季节</title><link>https://movie.douban.com/subject/35123456/</link><description>中国大陆 / 2023 / 剧情 / 95000 人评价</description><category>剧集</category><pubDate>Mon, 22 Apr 2023</pubDate></item>
<item><title>流浪地球3</title><link>https://movie.douban.com/subject/35234567/</link><description>中国大陆 / 2027 / 科幻 / 50000 人想看</description><category>电影</category><pubDate>Mon, 01 Jan 2027</pubDate></item>
<item><title>庆余年 第三季</title><link>https://movie.douban.com/subject/35345678/</link><description>中国大陆 / 2026 / 古装 / 第三季 / 30000 人想看</description><category>剧集</category><pubDate>Mon, 01 Jan 2026</pubDate></item>
<item><title>三体 第二季</title><link>https://movie.douban.com/subject/35456789/</link><description>中国大陆 / 2026 / 科幻 / 第二季 / 28000 人想看</description><category>剧集</category><pubDate>Mon, 01 Feb 2026</pubDate></item>
<item><title>狂飙 第二季</title><link>https://movie.douban.com/subject/35567890/</link><description>中国大陆 / 2026 / 犯罪 / 第二季 / 22000 人想看</description><category>剧集</category><pubDate>Mon, 01 Mar 2026</pubDate></item>
<item><title>哪吒之魔童闹海</title><link>https://movie.douban.com/subject/35678901/</link><description>中国大陆 / 2025 / 动画 / 180000 人评价</description><category>电影</category><pubDate>Mon, 29 Jan 2025</pubDate></item>
<item><title>沙丘3</title><link>https://movie.douban.com/subject/35789012/</link><description>美国 / 2026 / 科幻 / 40000 人想看</description><category>电影</category><pubDate>Mon, 18 Dec 2026</pubDate></item>
<item><title>长安的荔枝</title><link>https://movie.douban.com/subject/35890123/</link><description>中国大陆 / 2025 / 古装 / 35000 人评价</description><category>电影</category><pubDate>Mon, 25 Jul 2025</pubDate></item>
</channel></rss>`

// BangumiTV 榜单独供 mock：标题是真实风格的「日文原名 + 篇章名 + 季号」长串。
// 这类整串在 TMDB 搜不到，必须靠标题变体回退才能识别 —— 验证 titleCandidates。
const bangumiXMLMock = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item><title>Re:ゼロから始める異世界生活 4th season 奪還編</title><link>https://bgm.tv/subject/633836</link><description>&lt;img src="https://lain.bgm.tv/a.jpg"&gt;&lt;br&gt;10397 人关注</description><category>TV</category><pubDate>Wed, 12 Aug 2026</pubDate></item>
<item><title>スティール・ボール・ラン ジョジョの奇妙な冒険 2nd &amp; 3rd STAGE</title><link>https://bgm.tv/subject/400001</link><description>&lt;img src="https://lain.bgm.tv/b.jpg"&gt;&lt;br&gt;8000 人关注</description><category>TV</category><pubDate>Wed, 01 Apr 2026</pubDate></item>
</channel></rss>`

// 全球口碑榜单独 mock：验证「dian115 内部识别引擎优先」「TMDB 模糊搜索返回的高票
// 无关条目必须被拒绝」「本地化标题对不上时用 TMDB 原名回退识别」与「宿主识别也
// 给不出结论时靠豆瓣原名/又名兜底」四个识别要点。
// 描述里的 <img> 与真实 RSS 一致（当前版本不再解析它，保留以贴近真实数据）。
const tvGlobalXMLMock = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item><title>流人 第六季</title><link>https://movie.douban.com/subject/36000001/</link><description>英国 / 2026 / 剧情 / 80000 人评价&lt;img src="https://img3.doubanio.com/view/photo/m_ratio_poster/public/p28888888.webp" referrerpolicy="no-referrer"&gt;</description><category>剧集</category><pubDate>Mon, 01 Sep 2026</pubDate></item>
<item><title>ヤニねこ</title><link>https://movie.douban.com/subject/37000001/</link><description>日本 / 2026 / 动画 / 30000 人评价&lt;img src="https://img3.doubanio.com/view/photo/m_ratio_poster/public/p28888889.webp"&gt;</description><category>剧集</category><pubDate>Fri, 03 Jul 2026</pubDate></item>
<item><title>驽马 第六季</title><link>https://movie.douban.com/subject/36000002/</link><description>英国 / 2026 / 剧情 / 12000 人想看</description><category>剧集</category><pubDate>Mon, 01 Sep 2026</pubDate></item>
</channel></rss>`

// 想看列表 mock：按用户 ID 返回不同列表，用于验证「多用户合并去重」。
// 用户 10000001（A）与 10000002（B）都收藏了《漫长的季节》，用于验证跨用户去重。
// 日期用相对今天的偏移生成，避免被「只看最近 N 天」过滤后测试随时间失效。
// 昵称写在个人资料块的头像 alt 里（与豆瓣真实页面一致），B 的昵称含 HTML 实体用于验证反转义。
const daysAgo = (n) => {
  const d = new Date(Date.now() - n * 86400000)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
const wishMockByUser = {
  '10000001': {
    name: '甲壳虫',
    items: [
      { id: '35123456', title: '漫长的季节', date: daysAgo(1) },
      { id: '35234567', title: '流浪地球3 (2027)', date: daysAgo(2) },
      { id: '35999999', title: '独占测试片', date: daysAgo(3) },
    ],
  },
  '10000002': {
    name: '李四&amp;Co',
    items: [
      { id: '35123456', title: '漫长的季节', date: daysAgo(1) },
      { id: '35888999', title: '哪吒之魔童闹海', date: daysAgo(2) },
      { id: '35999999', title: '独占测试片', date: daysAgo(3) },
    ],
  },
}

function wishHTMLFor(userID) {
  const entry = wishMockByUser[userID]
  const list = entry ? entry.items : []
  const name = entry ? entry.name : ''
  const rows = list.map(
    (x) => `<div class="item"><a href="https://movie.douban.com/subject/${x.id}/"><em>${x.title}</em></a><img src="https://img.douban.com/p${x.id}.jpg"/><span class="date">${x.date}</span></div>`,
  )
  // 个人资料块：豆瓣真实页面里头像 alt 就是昵称原文，h1 为「昵称想看的影视(N)」
  const profile = `<div id="db-usr-profile"><div class="pic"><a href="/people/${userID}/"><img height="48" width="48" alt="${name}" src="https://img2.doubanio.com/icon/u${userID}-1.jpg" /></a></div><div class="info"><h1>${name}想看的影视(${list.length})</h1></div></div>`
  return `<html><head><title>${name}想看的影视(${list.length})</title></head><body>${profile}<div class="grid">${rows.join('')}</div></body></html>`
}

const wishHTMLMock = wishHTMLFor('10000001')

function tmdbSearchMock(q) {
  tmdbSearchCalls++
  // votes 可覆盖票数，original 可指定 TMDB 原名（默认与本地化名相同）。
  const mk = (id, title, mt, date, vote, votes = 8000, original = '') => ({
    id, title: mt === 'movie' ? title : '', name: mt === 'tv' ? title : '', media_type: mt,
    release_date: mt === 'movie' ? date : '', first_air_date: mt === 'tv' ? date : '',
    original_title: mt === 'movie' ? (original || title) : '',
    original_name: mt === 'tv' ? (original || title) : '',
    poster_path: '/p.jpg', vote_average: vote, vote_count: votes, popularity: 99,
  })
  const empty = { page: 1, total_results: 0, total_pages: 0, results: [] }
  const results = []
  // 模拟真实 TMDB：带季号的查询（如「信号 第二季」）搜不到结果，必须用基础剧名搜
  if (/第\s*(?:\d+|[一二三四五六七八九十]+)\s*季|Season\s*\d+/i.test(q)) return empty
  // BangumiTV 风格长标题：整串（含篇章名 / 多段季号）搜不到，
  // 只有回退到「剥掉篇章名」或「截短」的候选才命中 —— 验证 titleCandidates 变体回退。
  if (q.includes('奪還編') || q.includes('STAGE')) return empty
  if (q === 'Re:ゼロから始める異世界生活 4th season') {
    // 与真实 TMDB 一致：本地化名是中文意译，原名才是榜单给出的日文标题。
    return { page: 1, total_results: 1, total_pages: 1, results: [mk(51111, '从零开始的异世界生活', 'tv', '2026-08-12', 8.9, 8000, 'Re:ゼロから始める異世界生活')] }
  }
  if (q === 'スティール・ボール・ラン ジョジョの奇妙な冒険') {
    return { page: 1, total_results: 1, total_pages: 1, results: [mk(52222, 'JOJO的奇妙冒险', 'tv', '2026-04-01', 8.7, 8000, 'ジョジョの奇妙な冒険')] }
  }
  if (q.includes('ゼロから始める') || q.includes('スティール・ボール・ラン')) return empty
  // 模拟 TMDB 的中文模糊搜索：搜「流人」返回的其实是标题里恰好含有「流人」二字的
  // 无关条目，且票数极高。旧实现按票数排序会把「潮流合伙人」当成《流人》，
  // 于是封面张冠李戴 —— 新实现必须拒绝这类候选。
  if (q === '流人') {
    return {
      page: 1, total_results: 2, total_pages: 1,
      results: [
        mk(99999, '潮流合伙人', 'tv', '2019-12-06', 2.0, 999999),
        mk(99998, '千古风流人物', 'tv', '2021-10-15', 0, 999999),
      ],
    }
  }
  // 本地化标题对不上、但 TMDB 原名完全一致时，应靠原名识别成功
  // （榜单给的是原名，TMDB 的中文名是意译）。
  if (q === 'ヤニねこ') {
    return { page: 1, total_results: 1, total_pages: 1, results: [mk(88888, '尼古喵喵', 'tv', '2026-07-03', 7.2, 73, 'ヤニねこ')] }
  }
  // 与真实 TMDB 一致：这部剧根本没有中文标题（本地化名就是英文原名），
  // 所以搜「流人」永远搜不到，只能靠豆瓣条目的原名命中。
  if (q === 'Slow Horses' || q === 'Slow Horses Season 6') {
    return { page: 1, total_results: 1, total_pages: 1, results: [mk(95480, 'Slow Horses', 'tv', '2022-04-01', 8.2, 1001)] }
  }
  if (q.includes('Slow Horses')) return empty
  if (q.includes('漫长')) results.push(mk(23456, '漫长的季节', 'tv', '2023-04-22', 9.4))
  if (q.includes('流浪')) results.push(mk(12345, '流浪地球3', 'movie', '2027-01-01', 8.1))
  if (q.includes('庆余')) results.push(mk(34567, '庆余年', 'tv', '2026-01-01', 8.5))
  if (q.includes('三体')) results.push(mk(45678, '三体', 'tv', '2026-02-01', 8.8))
  if (q.includes('狂飙')) results.push(mk(45679, '狂飙', 'tv', '2026-03-01', 8.2))
  if (q.includes('哪吒')) results.push(mk(45680, '哪吒之魔童闹海', 'movie', '2025-01-29', 8.5))
  if (q.includes('沙丘')) results.push(mk(45681, '沙丘3', 'movie', '2026-12-18', 8.0))
  if (q.includes('荔枝')) results.push(mk(45682, '长安的荔枝', 'movie', '2025-07-25', 7.9))
  if (q.includes('独占')) results.push(mk(45999, '独占测试片', 'movie', '2026-06-01', 7.5))
  return { page: 1, total_results: results.length, total_pages: 1, results }
}
let tmdbSearchCalls = 0

function b64decode(s) { return Buffer.from(s, 'base64') }
function b64encode(b) { return Buffer.from(b).toString('base64') }

// host.* 请求的 JSON-RPC 应答封套
const rpcOK = (value) => ({ result: value })
const rpcErr = (msg) => ({ error: msg })
const http = (status, headers = {}, body = {}) => rpcOK({ status, headers, body_base64: b64encode(JSON.stringify(body)) })
// 原始文本响应（HTML/XML 等非 JSON 正文）
const httpRaw = (status, headers = {}, text = '') => rpcOK({ status, headers, body_base64: b64encode(text) })
// 二进制响应（图片等）
const httpBytes = (status, headers = {}, buf = Buffer.alloc(0)) => rpcOK({ status, headers, body_base64: Buffer.from(buf).toString('base64') })

function handleHostCall(reqJSON) {
  let parsed
  try { parsed = JSON.parse(reqJSON) } catch { return rpcErr('invalid json') }
  const rpcMethod = parsed && parsed.method
  const req = parsed && parsed.params ? parsed.params : parsed
  if (!req || typeof req !== 'object') return rpcErr('invalid params')
  if (process.env.HARNESS_DEBUG) {
    console.error(`[host] ${rpcMethod} ${req.path || ''} if-match=${(req.headers || {})['if-match'] || '-'} idem=${((req.headers || {})['idempotency-key'] || '-').slice(-6)} body=${(req.body_base64 || '').length}b`)
  }
  // host.log / host.telegram.* / host.ui.* 等非 HTTP 方法
  if (rpcMethod !== 'host.call') {
    if (process.env.HARNESS_DEBUG && rpcMethod === 'host.log') {
      const p = req || {}
      console.error(`[log] ${p.level || ''} ${p.message || ''} ${JSON.stringify(p.fields || {})}`)
    }
    return rpcOK({ accepted: true })
  }
  const httpMethod = req.method
  const path = req.path || ''
  const headers = req.headers || {}
  const h = {}
  for (const [k, v] of Object.entries(headers)) h[k.toLowerCase()] = v

  // Host Storage
  const m = path.match(/^\/api\/plugin-runtime\/storage\/([A-Za-z0-9][A-Za-z0-9._-]*)$/)
  if (m) {
    const key = m[1]
    if (httpMethod === 'GET') {
      storageGets.push(key)
      const item = storage.get(key)
      if (!item) return http(404)
      return http(200, { ETag: [item.etag] }, { data: { value: item.value }, meta: {} })
    }
    if (httpMethod === 'PUT') {
      const idem = h['idempotency-key']
      if (!idem || idem.length < 16) return http(400, {}, { detail: 'idempotency key too short' })
      const body = b64decode(req.body_base64 || '').toString('utf8')
      const hash = createHash('sha256').update(body).digest('hex')
      if (idemSeen.has(idem) && idemSeen.get(idem) !== hash) {
        return http(422, {}, { detail: 'idempotency key reused with different body' })
      }
      idemSeen.set(idem, hash)
      const item = storage.get(key)
      const ifMatch = h['if-match']
      if (item && !ifMatch) {
        // 模拟宿主强制 CAS：更新已有值必须带 If-Match
        return http(412, {}, { detail: 'precondition required' })
      }
      if (item && ifMatch && ifMatch !== item.etag) {
        return http(412, {}, { detail: 'etag mismatch' })
      }
      etagSeq++
      const etag = `"pkv_${etagSeq}"`
      let value
      try { value = JSON.parse(body).value } catch { value = null }
      storage.set(key, { value, etag })
      return http(200, { ETag: [etag] }, { data: { value }, meta: {} })
    }
  }

  // ---- 豆瓣条目的原名 / 又名（rexxar）----
  // 只有原名能救回 TMDB 没有中文标题的条目（《流人 第六季》→ Slow Horses）。
  if (path.includes('/rexxar/api/v2/')) {
    aliasRequests.push({ url: path, referer: h['referer'] || '' })
    const am = path.match(/rexxar\/api\/v2\/(tv|movie)\/(\d+)/)
    const kind = am ? am[1] : ''
    const sid = am ? am[2] : ''
    const subj = doubanSubjects[sid]
    // 类型猜错时豆瓣 301 到正确地址（宿主的 Broker 不跨类型跟随跳转，
    // 插件按响应体里的地址纠正后重试）
    if (subj && kind !== subj.type) {
      return httpRaw(301, {}, `Your browser should have been redirected to https://m.douban.com/rexxar/api/v2/${subj.type}/${sid}`)
    }
    if (subj) {
      return http(200, {}, { original_title: subj.original, aka: subj.aka })
    }
    return http(200, {}, { original_title: '', aka: [] })
  }

  // 订阅意图
  if (path.startsWith('/api/subscribe/pool/intents') && httpMethod === 'GET') {
    if (intentsApiFail) return http(500, {}, { detail: 'subscribe pool unavailable' })
    const mt = decodeURIComponent((path.match(/[?&]media_type=([^&]*)/) || [])[1] || '')
    const data = intents.filter((it) => !mt || it.media_type === mt)
    return http(200, {}, { code: 'ok', data, counts: {} })
  }
  if (path === '/api/subscribe/pool/intents' && httpMethod === 'POST') {
    const body = JSON.parse(b64decode(req.body_base64 || '').toString('utf8') || '{}')
    intentPosts.push({
      tmdb_id: body.tmdb_id,
      media_type: body.media_type,
      season: body.season || 0,
      title: body.title,
    })
    const created = { id: ++intentSeq, tmdb_id: body.tmdb_id, media_type: body.media_type, season: body.season || 0, title: body.title, state: 'active' }
    intents.push(created)
    return http(200, {}, { code: 'ok', data: created })
  }
  // TMDB
  if (path.startsWith('/api/tmdb/search')) {
    // 用 URLSearchParams 做标准 form 解码：Go 的 url.QueryEscape 把空格编成「+」，
    // 只做 decodeURIComponent 无法还原，会导致含空格的精确匹配查询失真。
    const q = new URLSearchParams(path.split('?')[1] || '').get('q') || ''
    return http(200, {}, tmdbSearchMock(q))
  }
  if (path.startsWith('/api/tmdb/movie/')) {
    return http(200, {}, { id: 12345, title: '流浪地球3', release_date: '2027-01-01', poster_path: '/p.jpg', vote_average: 8.1 })
  }
  if (path.startsWith('/api/tmdb/tv/')) {
    return http(200, {}, { id: 23456, name: '漫长的季节', first_air_date: '2023-04-22', poster_path: '/p2.jpg', vote_average: 9.4 })
  }

  // 通知
  if (path === '/api/notifications/plugin' && httpMethod === 'POST') {
    return http(200, {}, { data: {}, meta: {} })
  }
  // 其他本地 API
  if (path.startsWith('/api/')) {
    return http(200, {}, { code: 'ok', data: [], counts: {} })
  }
  // 外部 HTTP：模拟宿主对禁用请求头的校验（-32001）
  const bannedHeaders = ['host', 'proxy-authorization', 'connection', 'keep-alive', 'proxy-connection', 'transfer-encoding', 'te', 'trailer', 'upgrade', 'content-length', 'expect']
  for (const bh of bannedHeaders) {
    if (h[bh] !== undefined) {
      return rpcErr(`plugin process RPC -32001: outbound header "${bh}" is not allowed`)
    }
  }
  // CookieCloud 服务器模拟
  if (path.includes('/get/')) {
    if (globalThis.__cc_failHost && path.includes(globalThis.__cc_failHost)) {
      return http(502, {}, { detail: 'bad gateway' })
    }
    if (globalThis.__cc_encrypted) {
      return http(200, {}, { encrypted: globalThis.__cc_encrypted })
    }
    return http(404, {}, { detail: 'not found' })
  }
  // 豆瓣想看页模拟（按 URL 中的用户 ID 返回对应用户的列表）
  if (path.includes('/wish')) {
    const um = path.match(/people\/([^/?]+)\/wish/)
    return httpRaw(200, {}, wishHTMLFor(um ? um[1] : ''))
  }
  // RSSHub 榜单模拟（BangumiTV 用单独的 mock，标题为「日文原名 + 篇章名 + 季号」长串）
  if (path.includes('/bangumi')) {
    return httpRaw(200, {}, bangumiXMLMock)
  }
  if (path.includes('tv_global_best_weekly')) {
    return httpRaw(200, {}, tvGlobalXMLMock)
  }
  if (path.includes('rsshub') || path.includes('/douban/')) {
    return httpRaw(200, {}, rssXMLMock)
  }
  return http(200, {}, { ok: true })
}

// ---- dian115 导入 ----
let hostRespBuffer = null
// slowModeMs 模拟真实网络往返耗时（忙等），让单片预算跑不完全部条目，
// 用于验证长任务确实被拆成多片、且中断后能从断点继续。
let slowModeMs = 0
// callTimes 记录每次 host.call 的时刻，用于验证片与片之间确实有让出空隙。
const callTimes = []
function busyWait(ms) {
  const end = Date.now() + ms
  while (Date.now() < end) {
    /* busy wait */
  }
}

const imports = {
  dian115: {
    host_call: (ptr, length) => {
      const mem = new Uint8Array(instance.exports.memory.buffer)
      const req = new TextDecoder().decode(mem.subarray(ptr, ptr + length))
      const envelope = handleHostCall(req)
      if (slowModeMs > 0) busyWait(slowModeMs)
      callTimes.push(Date.now())
      hostRespBuffer = JSON.stringify(envelope)
      return hostRespBuffer.length
    },
    host_read: (ptr, capacity) => {
      if (!hostRespBuffer) return 0
      const bytes_ = new TextEncoder().encode(hostRespBuffer)
      const n = Math.min(bytes_.length, capacity)
      new Uint8Array(instance.exports.memory.buffer).set(bytes_.subarray(0, n), ptr)
      hostRespBuffer = null
      return n
    },
  },
}

const wasi = new WASI({ version: 'preview1' })
const importObject = { wasi_snapshot_preview1: wasi.wasiImport, dian115: imports.dian115 }

const mod = await WebAssembly.compile(bytes)
const instance = await WebAssembly.instantiate(mod, importObject)
wasi.initialize(instance)

const { dian115_alloc, dian115_handle } = instance.exports

function call(message) {
  const payload = new TextEncoder().encode(JSON.stringify(message))
  const ptr = dian115_alloc(payload.length)
  new Uint8Array(instance.exports.memory.buffer).set(payload, ptr)
  const ret = dian115_handle(ptr, payload.length)
  const addr = Number(ret >> 32n & 0xffffffffn)
  const len = Number(ret & 0xffffffffn)
  const out = new Uint8Array(instance.exports.memory.buffer).subarray(addr, addr + len)
  return JSON.parse(new TextDecoder().decode(out))
}

let idc = 0
function rpc(method, params) {
  return call({ jsonrpc: '2.0', id: `t-${++idc}`, method, params })
}

function invoke(op, payload, background = false) {
  return rpc('runtime.invoke', {
    envelope: { op, invocation_id: `inv-${idc}`, payload },
    background,
  })
}

function assert(cond, label) {
  if (!cond) {
    console.error(`ASSERT FAIL: ${label}`)
    process.exitCode = 1
  } else {
    console.log(`ASSERT OK: ${label}`)
  }
}

// ---- 测试流程 ----
console.log('== initialize ==')
const init = rpc('runtime.initialize', {
  protocol: 'dian115:wasm@1', plugin_id: 'local.douban115', plugin_version: '1.0.0',
  installation_id: 1, locale: 'zh-CN', timezone: 'Asia/Shanghai',
})
assert(init.result?.ready === true, 'runtime.initialize ready')

console.log('\n== state（含安全字段断言）==')
const st = invoke('state', { view: 'main' })
assert(!st.error, 'state 无 error')
const s = st.result?.state || {}
assert((s.ranks || []).length === 6, `state.ranks 有 6 个榜单（实际 ${(s.ranks || []).length}）`)
assert(Object.keys(s.config?.rank_configs || {}).length === 6, 'state.config.rank_configs 有 6 项')
const stateJSON = JSON.stringify(st.result)
assert(!/cookie/i.test(stateJSON), 'state 结果中不含 cookie 字样 key')
assert(!/password/i.test(stateJSON), 'state 结果中不含 password 字样 key')
assert(!JSON.stringify(s.ranks).match(/"\/[^/]/), 'ranks.route 不以 / 开头（绝对路径规则）')
console.log('state size:', stateJSON.length, 'bytes')

console.log('\n== save-config（宿主强制 CAS）==')
const saveRes = invoke('action', {
  id: 'save-config',
  input: { config: { rsshub_domain: 'https://rsshub.ddsrem.com', notify: true, douban_user_id: '10000001' } },
})
assert(saveRes.result?.status === 'succeeded', `save-config 成功（实际 ${JSON.stringify(saveRes).slice(0, 120)}）`)
assert(!/cookie/i.test(JSON.stringify(saveRes)), 'save-config 结果不含敏感 key')

console.log('\n== 再次 save-config（触发 CAS 更新路径）==')
const saveRes2 = invoke('action', {
  id: 'save-config',
  input: { config: { notify: false, blacklist: '综艺' } },
})
assert(saveRes2.result?.status === 'succeeded', `第二次 save-config 成功（实际 ${JSON.stringify(saveRes2).slice(0, 120)}）`)

console.log('\n== storage 落盘内容 ==')
for (const [k, v] of storage) console.log(' ', k, 'etag=' + v.etag, JSON.stringify(v.value).slice(0, 140))

console.log('\n== 条件 state（if_none_match，先取最新 etag）==')
const stFresh = invoke('state', { view: 'main' })
const st2 = invoke('state', { view: 'main', if_none_match: stFresh.result?.etag })
assert(st2.result?.not_modified === true, '条件 state 返回 not_modified')

console.log('\n== job rank-sync（无启用榜单）==')
const jb = invoke('job', { id: 'rank-sync', handler: 'rank-sync', scheduled_for: new Date().toISOString(), trigger: 'manual', attempt: 1 }, true)
assert(jb.result?.status === 'accepted', `job 返回 accepted（实际 ${JSON.stringify(jb).slice(0, 120)}）`)

console.log('\n== 启用榜单后完整 run-ranks 流程（队列 + 常驻实例执行）==')
const saveRank = invoke('action', {
  id: 'save-config',
  input: {
    config: {
      rank_configs: {
        tv_chinese: { enabled: true, count: 5, min_vote: 0, min_year: 0, regions: [] },
        tv_global: { enabled: true, count: 5, min_vote: 0, min_year: 0, regions: [] },
        movie_weekly: { enabled: true, count: 5, min_vote: 0, min_year: 0, regions: [] },
      },
    },
  },
})
assert(saveRank.result?.status === 'succeeded', '保存启用榜单配置成功')

// 1) action 只入队并立即返回 accepted
const rr = invoke('action', { id: 'run-ranks' })
console.log('run-ranks:', JSON.stringify(rr).slice(0, 300))
assert(rr.result?.status === 'accepted', 'run-ranks 返回 accepted（已入队）')
const reqAfter = storage.get('run_requests')
assert((reqAfter?.value?.rank || 0) > 0, 'run_requests.rank 已入队')
const stQueued = invoke('state', { view: 'main' })
assert(stQueued.result?.state?.lastStatus === 'running', '入队后 state 为 running')

// 2) 模拟常驻实例：job 执行（同步跑完整流程，同时应清掉队列标记）
const rankJob = invoke('job', { id: 'rank-sync', handler: 'rank-sync', trigger: 'cron', attempt: 1 }, true)
assert(rankJob.result?.status === 'accepted', 'job rank-sync 执行完成')
const reqAfterRun = storage.get('run_requests')
assert((reqAfterRun?.value?.rank || 0) === 0, '执行后队列标记已清除')
const stDone = invoke('state', { view: 'main' })
const rankDoneMsg = String(stDone.result?.state?.lastMessage || '')
console.log('run-ranks 结果:', rankDoneMsg.slice(0, 200))
assert(stDone.result?.state?.lastStatus === 'succeeded', '执行后 state 为 succeeded')
assert(rankDoneMsg.includes('已订阅'), `至少订阅了一部（message=${rankDoneMsg.slice(0, 160)}）`)

console.log(`  首轮建订阅请求：${intentPosts.map((p) => `${p.media_type}:${p.tmdb_id}`).join(', ') || '（无）'}`)
{
  const keys = new Set()
  let dup = 0
  for (const p of intentPosts) {
    const k = `${p.media_type}:${p.tmdb_id}:${p.season || 0}`
    if (keys.has(k)) dup++
    keys.add(k)
  }
  assert(intentPosts.length > 0, '首轮产生了建订阅请求')
  assert(dup === 0, `首轮内不重复订阅同一条目（重复 ${dup} 次）`)
}

console.log('\n== run-wish 完整流程（多用户：两个豆瓣 ID 合并）==')
const saveWish = invoke('action', {
  id: 'save-config',
  input: { config: { douban_cookie: 'dbcl2="10000001:xyz"; ck=ABCD; bid=123', wish_enabled: true, douban_user_id: '10000001,10000002' } },
})
assert(saveWish.result?.status === 'succeeded', '保存想看配置成功')
const wishPostsBefore = intentPosts.length
const rw = invoke('action', { id: 'run-wish' })
console.log('run-wish:', JSON.stringify(rw).slice(0, 300))
assert(rw.result?.status === 'accepted', 'run-wish 返回 accepted（已入队）')
const wishJob = invoke('job', { id: 'wish-sync', handler: 'wish-sync', trigger: 'cron', attempt: 1 }, true)
assert(wishJob.result?.status === 'accepted', 'job wish-sync 执行完成')
const stWishDone = invoke('state', { view: 'main' })
assert(stWishDone.result?.state?.lastStatus === 'succeeded', '想看执行后 state 为 succeeded')

console.log('\n== 多用户想看：合并去重 + 来源用户 ==')
{
  const sameUsers = (a = [], b = []) => JSON.stringify([...a].sort()) === JSON.stringify([...b].sort())
  const whMap = storage.get('wish_history')?.value || {}
  const whEntries = Object.values(whMap)
  const byTitle = (kw) => whEntries.find((e) => String(e.title || '').includes(kw))
  const changman = byTitle('漫长的季节')   // 两个用户都有
  const liulang = byTitle('流浪地球3')     // 仅用户 A
  const nezha = byTitle('哪吒')            // 仅用户 B
  const duli = byTitle('独占测试片')        // 两个用户都有，且是全新条目
  console.log('  想看历史：', whEntries.map((e) => `${e.title}[${(e.users || []).join('+')}]`).join(' | '))
  assert(whEntries.length === 4, `两个用户共 4 条不同想看（去重后，实际 ${whEntries.length}）`)
  assert(changman && sameUsers(changman.users, ['10000001', '10000002']),
    `重叠条目记录两个来源用户（实际 ${JSON.stringify(changman?.users)}）`)
  assert(liulang && sameUsers(liulang.users, ['10000001']), `用户 A 独有条目来源正确（实际 ${JSON.stringify(liulang?.users)}）`)
  assert(nezha && sameUsers(nezha.users, ['10000002']), `用户 B 独有条目来源正确（实际 ${JSON.stringify(nezha?.users)}）`)
  assert(duli && sameUsers(duli.users, ['10000001', '10000002']), `共有的新条目记录两个来源用户（实际 ${JSON.stringify(duli?.users)}）`)
  // 跨用户重叠的条目只应产生一次订阅请求
  const wishKeys = intentPosts.slice(wishPostsBefore).map((p) => `${p.media_type}:${p.tmdb_id}:${p.season || 0}`)
  const dupWish = wishKeys.length - new Set(wishKeys).size
  const sharedNewSubs = wishKeys.filter((k) => k === 'movie:45999:0').length
  console.log(`  想看阶段建订阅请求：${wishKeys.join(', ') || '（无，均已存在）'}`)
  assert(dupWish === 0, `跨用户重叠的想看只订阅一次（重复 ${dupWish}）`)
  assert(sharedNewSubs === 1, `两个用户共同的全新条目只建一次订阅（实际 ${sharedNewSubs}）`)
}

console.log('\n== 想看订阅标记用户名（昵称解析 + 缓存 + 展示）==')
{
  // 昵称随想看页一起解析，并缓存到 Host Storage（ID -> 昵称/头像）
  const cache = storage.get('wish_users')?.value || {}
  console.log('  昵称缓存：', JSON.stringify(cache))
  assert(cache['10000001']?.name === '甲壳虫', `用户 A 昵称解析正确（实际 ${JSON.stringify(cache['10000001']?.name)}）`)
  assert(cache['10000002']?.name === '李四&Co', `用户 B 昵称反转义正确（实际 ${JSON.stringify(cache['10000002']?.name)}）`)
  assert(String(cache['10000002']?.avatar || '').includes('u10000002-1.jpg'), '头像地址解析正确（协议补全为 https）')

  // 仪表盘需要把 ID 换成昵称展示，并提供每位用户的订阅条数
  const dbu = invoke('action', { id: 'dashboard' })
  const wu = dbu.result?.wish_users || []
  console.log('  dashboard.wish_users：', JSON.stringify(wu))
  assert(wu.length === 2, `dashboard 返回 2 位想看用户（实际 ${wu.length}）`)
  assert(wu[0].id === '10000001' && wu[1].id === '10000002', '用户顺序与配置一致')
  assert(wu[0].name === '甲壳虫' && wu[1].name === '李四&Co', 'dashboard 带出昵称')
  const countById = Object.fromEntries(wu.map((u) => [u.id, u.count || 0]))
  assert(countById['10000001'] === 3 && countById['10000002'] === 3,
    `每位用户的想看订阅条数正确（实际 ${JSON.stringify(countById)}）`)

  // 历史条目仍只存用户 ID，昵称靠 ID 映射补全（便于界面渲染）
  const whUsers = Object.values(storage.get('wish_history')?.value || {}).flatMap((e) => e.users || [])
  assert(whUsers.every((u) => cache[u]), '每条想看历史的来源用户都能在昵称缓存里找到')

  // 测试连接也返回昵称（界面把它显示成「昵称（ID）」）
  const td = invoke('action', { id: 'test-douban' })
  const tdUsers = td.result?.users || []
  console.log('  test-douban：', JSON.stringify(td.result?.message || ''))
  assert(tdUsers.length === 2 && tdUsers.every((u) => u.name), '测试连接返回每位用户的昵称')
  assert(String(td.result?.message || '').includes('甲壳虫'), '测试连接消息里显示用户名')

  // state 也带上用户列表（设置页「已识别用户」）
  const stUsers = invoke('state', { view: 'main' }).result?.state?.wishUsers || []
  assert(stUsers.length === 2 && stUsers[0].name === '甲壳虫', 'state.wishUsers 带昵称')

  // 昵称解析失败时不应污染缓存（空昵称回退旧值）
  const keep = storage.get('wish_users')?.value || {}
  assert(keep['10000001'].name === '甲壳虫', '缓存未被空昵称覆盖')
}

console.log('\n== dashboard（仪表盘数据）==')
const db = invoke('action', { id: 'dashboard' })
const dbStr = JSON.stringify(db)
console.log('dashboard 长度:', dbStr.length, '字节')
assert(db.result?.status === 'succeeded', 'dashboard 成功')
assert(dbStr.length < 256 * 1024, 'dashboard 结果小于 256 KiB')
const dbRanks = db.result?.ranks || []
assert(dbRanks.length === 6, `dashboard.ranks 有 6 个榜单（实际 ${dbRanks.length}）`)
const tvReal = dbRanks.find(r => r.key === 'tv_chinese') || { items: [] }
assert(tvReal.items.length > 0, `已启用榜单的快照有条目（实际 ${tvReal.items.length}）`)
assert(tvReal.items.every(it => it.status && it.title), '快照条目均含 status/title')
assert(tvReal.items.some(it => it.status === 'subscribed'), '快照中有已订阅条目')
assert(!dbStr.includes('/p.jpg">'), '占位符安全')
// 安全字段规则：不得出现 cookie 键名 / 绝对路径字符串值
assert(!/"[^"]*cookie[^"]*"\s*:/.test(dbStr), 'dashboard 无 cookie 键名')
assert(!/"[^"]*(password|_token|_secret)"\s*:/.test(dbStr), 'dashboard 无敏感键名')
const rhCount = (db.result?.rank_history || []).length
const whCount = (db.result?.wish_history || []).length
assert(rhCount > 0, `榜单订阅历史有条目（实际 ${rhCount}）`)
assert(whCount > 0, `想看订阅历史有条目（实际 ${whCount}）`)
assert((db.result?.rank_history || []).every(e => e.source && e.source_key && (e.subscribed_at || e.existing || e.removed)), '历史条目含来源，且已订阅条目含时间')
assert(db.result?.stats?.total_subscribed > 0, '统计 total_subscribed > 0')
assert(db.result?.stats?.per_rank && Object.keys(db.result.stats.per_rank).length > 0, '统计 per_rank 有数据')

console.log('\n== cron-next ==')
const cn = invoke('action', { id: 'cron-next' })
console.log('cron-next:', JSON.stringify(cn).slice(0, 300))
assert(cn.result?.rank?.next && cn.result?.wish?.next && cn.result?.emby?.next, '三个任务的下次触发时间均已计算')

console.log('\n== 非法 cron 保存被拒绝 ==')
const badCron = invoke('action', { id: 'save-config', input: { config: { rank_cron: 'abc xyz' } } })
assert(badCron.result?.status === 'failed', '非法 cron 被拒绝')
assert(String(badCron.result?.message || '').includes('Cron'), '错误信息提到 Cron')

console.log('\n== 合法自定义 cron 保存成功 ==')
const goodCron = invoke('action', { id: 'save-config', input: { config: { rank_cron: '*/15 8-22 * * *', wish_cron: '30 3 * * 1' } } })
assert(goodCron.result?.status === 'succeeded', `自定义 cron 保存成功（实际 ${JSON.stringify(goodCron).slice(0, 160)}）`)
const badCron2 = invoke('action', { id: 'save-config', input: { config: { rank_cron: '0 8 1 * 1' } } })
assert(badCron2.result?.status === 'failed', '日周同时受限的 cron 被拒绝')

console.log('\n== CookieCloud 解密自测 ==')
// 用官方算法构造一段加密数据再让插件解密
const crypto = await import('node:crypto')
const CC_UUID = 'test-uuid-1234'
const CC_PASS = 'test-pass'
const passphrase = crypto.createHash('md5').update(CC_UUID + '-' + CC_PASS).digest('hex').substring(0, 16)
const salt = crypto.randomBytes(8)
// EVP_BytesToKey MD5
function evp(pass, salt, klen, ivlen) {
  const total = klen + ivlen
  let d = Buffer.alloc(0)
  let prev = Buffer.alloc(0)
  while (d.length < total) {
    prev = crypto.createHash('md5').update(Buffer.concat([prev, pass, salt])).digest()
    d = Buffer.concat([d, prev])
  }
  return [d.subarray(0, klen), d.subarray(klen, total)]
}
const [k, iv] = evp(Buffer.from(passphrase), salt, 32, 16)
const payload = JSON.stringify({
  cookie_data: {
    '.douban.com': [
      { name: 'dbcl2', value: '"123456:abcdef"', domain: '.douban.com' },
      { name: 'ck', value: 'ABCD', domain: '.douban.com' },
    ],
    '.example.com': [{ name: 'x', value: 'y', domain: '.example.com' }],
  },
})
const cipherCbC = crypto.createCipheriv('aes-256-cbc', k, iv)
const enc = Buffer.concat([Buffer.from('Salted__'), salt, cipherCbC.update(Buffer.from(payload)), cipherCbC.final()])
const encryptedB64 = enc.toString('base64')
// 外部 HTTP mock：让 sync-cookiecloud 拉到这段数据
const origHandle = handleHostCall
// 简化：直接通过注入 storage 的方式不可行，改为 monkey-patch 外部 HTTP 返回
// （handleHostCall 对外部 HTTP 统一返回 {ok:true}，这里临时替换全局行为）
globalThis.__cc_encrypted = encryptedB64
// 重新走 action：save cloud 配置后再同步
const saveCloud = invoke('action', {
  id: 'save-config',
  input: { config: { cloud_url: 'https://cc.example.com', cloud_uuid: CC_UUID, cloud_passcode: CC_PASS } },
})
assert(saveCloud.result?.status === 'succeeded', '保存 CookieCloud 配置成功')

// 给 mock 的外部 HTTP 打补丁：重新构建 instance 不可行，改用直接验证解密函数逻辑
// —— 通过 action sync-cookiecloud 触发；mock 对非 /api/ 路径返回 {ok:true}，
// 缺少 encrypted 字段，插件应返回明确错误。
const syncRes = invoke('action', { id: 'sync-cookiecloud' })
console.log('sync-cookiecloud（有加密数据时）:', JSON.stringify(syncRes).slice(0, 200))
assert(syncRes.result?.status === 'accepted', `sync-cookiecloud 立即返回并排队（实际 ${JSON.stringify(syncRes).slice(0, 160)}）`)

// 模拟常驻实例消费队列：真正执行 CookieCloud 拉取
const cloudJob = invoke('job', { id: 'cloud-sync', trigger: 'resident', attempt: 1 }, true)
console.log('job cloud-sync:', JSON.stringify(cloudJob).slice(0, 200))
assert(cloudJob.result?.status === 'accepted', 'job cloud-sync 执行完成')
const ccState = invoke('state', { view: 'main' })
const ccMsg = String(ccState.result?.state?.lastMessage || '')
assert(ccMsg.includes('已从 CookieCloud 获取'), `后台结果经跨实例状态回传（实际 ${ccMsg.slice(0, 120)}）`)
assert(ccState.result?.state?.doubanLoggedIn === true, '状态标记豆瓣已登录')

// 验证配置里真的存进了豆瓣 Cookie（读 storage 而非 state，state 不下发敏感字段）
const cfgStored = storage.get('config')
const cookieStr = cfgStored?.value?.douban_cookie || ''
assert(cookieStr.includes('dbcl2="123456:abcdef"') && cookieStr.includes('ck=ABCD'), '豆瓣 Cookie 已正确提取并保存')
assert(!cookieStr.includes('x=y'), '非豆瓣域 Cookie 未混入')

console.log('\n== CookieCloud 候选地址回退 ==')
// 配置地址不可用（502）时，插件应自动回退到本机其他候选地址
globalThis.__cc_failHost = '127.0.0.1:9999'
invoke('action', {
  id: 'save-config',
  input: { config: { cloud_url: 'http://127.0.0.1:9999/cookiecloud', cloud_uuid: CC_UUID, cloud_passcode: CC_PASS } },
})
const fbSite = invoke('action', { id: 'sync-cookiecloud' })
assert(fbSite.result?.status === 'accepted', '首选地址不可用时仍成功排队')
invoke('job', { id: 'cloud-sync', trigger: 'resident', attempt: 1 }, true)
const stFb = invoke('state', { view: 'main' })
const fbMsg = String(stFb.result?.state?.lastMessage || '')
assert(fbMsg.includes('已从 CookieCloud 获取'), `首选地址失败后自动回退到可用候选（实际 ${fbMsg.slice(0, 120)}）`)
globalThis.__cc_failHost = null

console.log('\n== CookieCloud 地址归一化 ==')
invoke('action', { id: 'save-config', input: { config: { cloud_url: 'http://127.0.0.1:3000' } } })
const stNorm = invoke('state', { view: 'main' })
const normURL = String(stNorm.result?.state?.config?.cloud_url || '')
assert(normURL === 'http://127.0.0.1:3000/cookiecloud', `未写路径时自动补 /cookiecloud（实际 ${normURL}）`)

console.log('\n== 去重检验 A：订阅未变动时重复运行 ==')
const basePosts = intentPosts.length
const rerun = invoke('job', { id: 'rank-sync', handler: 'rank-sync', trigger: 'cron', attempt: 1 }, true)
assert(rerun.result?.status === 'accepted', '第二次 rank-sync 执行完成')
const afterRerun = intentPosts.length
console.log(`  建订阅请求：基线 ${basePosts} → 重复运行后 ${afterRerun}（新增 ${afterRerun - basePosts}）`)
assert(afterRerun === basePosts, `订阅未变动时重复运行不产生新订阅（新增 ${afterRerun - basePosts}）`)

console.log('\n== 去重检验 B：用户在 dian115 删除订阅后重新运行 ==')
// 记录删除前宿主里真实存在的订阅（用于验证「被删的订阅不被重订」）
const prevSubKeys = new Set(intents.map((i) => `${i.media_type}:${i.tmdb_id}:${i.season || 0}`))
dropAllIntents() // 模拟用户在宿主侧把订阅全部删除
const beforeDelete = intentPosts.length
invoke('job', { id: 'rank-sync', handler: 'rank-sync', trigger: 'cron', attempt: 1 }, true)
const afterDelete = intentPosts.length
const delResub = afterDelete - beforeDelete
console.log(`  建订阅请求：删除前 ${beforeDelete} → 删除后重新运行 ${afterDelete}（新增 ${delResub}）`)
console.log(`  → 已删除订阅${delResub > 0 ? '会被' : '不会被'}自动重新订阅`)
// 期望：尊重用户删除意图，被删掉的订阅不自动重订（标记 removed，可用清空历史重置）。
// 注意：此前因「订阅数量」配额而排队（beyond）的条目本轮被订阅是预期行为，不算重订。
const resubDeleted = intentPosts
  .slice(beforeDelete)
  .filter((p) => prevSubKeys.has(`${p.media_type}:${p.tmdb_id}:${p.season || 0}`))
assert(resubDeleted.length === 0, `已删除的订阅不会被自动重复订阅（被重订 ${resubDeleted.length} 条）`)

// 仪表盘应能如实反映「已被你删掉」而不是继续显示「已订阅」
const dbAfterDelete = invoke('action', { id: 'dashboard' })
const removedSnaps = []
for (const r of dbAfterDelete.result?.ranks || []) {
  for (const it of r.items) if (it.status === 'removed') removedSnaps.push(it.title)
}
assert(removedSnaps.length > 0, `删除后的条目在榜单快照中标记为已删除（${removedSnaps.length} 条：${removedSnaps.join('、')}）`)
assert((dbAfterDelete.result?.stats?.removed_count || 0) > 0, `统计 removed_count > 0（实际 ${dbAfterDelete.result?.stats?.removed_count}）`)
const rmHist = (dbAfterDelete.result?.rank_history || []).filter((e) => e.removed)
assert(rmHist.length > 0, `订阅历史中保留已删除记录（${rmHist.length} 条）`)
// 「总订阅数」只统计仍在订阅中的条目（已删除的排除）。
// 想看订阅与榜单订阅共用该统计，因此基线需加上当前想看侧的已订阅条目。
const wishSubCount = Object.values(storage.get('wish_history')?.value || {})
  .filter((e) => e.subscribed && !e.removed && !e.existing).length
assert((dbAfterDelete.result?.stats?.total_subscribed || 0) === delResub + wishSubCount, `已删除条目不计入「总订阅数」（total=${dbAfterDelete.result?.stats?.total_subscribed}，本轮新增 ${delResub} + 想看已订阅 ${wishSubCount}）`)

console.log('\n== 去重检验 C：清空订阅历史后重新运行（重置手段）==')
const beforeClear = intentPosts.length
const clr = invoke('action', { id: 'clear-history', input: { scope: 'rank' } })
console.log('clear-history(rank):', JSON.stringify(clr).slice(0, 240))
assert(clr.result?.status === 'succeeded', 'clear-history(rank) 成功')
assert((clr.result?.cleared ?? -1) > 0, `clear-history 返回清空条数（实际 ${clr.result?.cleared}）`)
invoke('job', { id: 'rank-sync', handler: 'rank-sync', trigger: 'cron', attempt: 1 }, true)
const afterClear = intentPosts.length
console.log(`  建订阅请求：清空前 ${beforeClear} → 清空后重新运行 ${afterClear}（新增 ${afterClear - beforeClear}）`)
assert(afterClear > beforeClear, `清空历史后会重新评估并订阅（新增 ${afterClear - beforeClear}）`)

console.log('\n== 去重检验 C2：同一部剧出现在多个榜榜单时是否重复建订阅 ==')
const runSlice = intentPosts.slice(beforeClear)
const seenKeys = new Set()
let dupInRun = 0
for (const p of runSlice) {
  const k = `${p.media_type}:${p.tmdb_id}:${p.season || 0}`
  if (seenKeys.has(k)) dupInRun++
  seenKeys.add(k)
}
console.log(`  本次运行共 ${runSlice.length} 次建订阅请求，去重后 ${seenKeys.size} 条，重复 ${dupInRun} 次`)
assert(runSlice.length > 0, '本次运行有建订阅请求')
assert(dupInRun === 0, `同一次运行内不重复订阅同一条目（重复 ${dupInRun} 次）`)

console.log('\n== 去重检验 D：订阅池读取失败 + 历史为空时是否重复订阅 ==')
// 危险组合：插件不知道订阅池里已有什么（读取失败），又没有历史记录兜底，
// 届时会把榜单条目全部当成新条目重新订阅 —— 这正是「重复订阅」最可能发生的场景。
intentsApiFail = true
invoke('action', { id: 'clear-history', input: { scope: 'rank' } })
const beforeFail = intentPosts.length
invoke('job', { id: 'rank-sync', handler: 'rank-sync', trigger: 'cron', attempt: 1 }, true)
intentsApiFail = false
const afterFail = intentPosts.length
console.log(`  建订阅请求：失败前 ${beforeFail} → 失败后 ${afterFail}（新增 ${afterFail - beforeFail}）`)
assert(afterFail === beforeFail, `订阅池不可用时中止同步、不重复订阅（实际新增 ${afterFail - beforeFail}）`)

console.log('\n== 去重检验 E：清空想看历史（scope 隔离）==')
// 先跑一轮榜单同步把榜单历史补回来，再验证清空想看历史不影响榜单历史
invoke('job', { id: 'rank-sync', handler: 'rank-sync', trigger: 'cron', attempt: 1 }, true)
const clrWish = invoke('action', { id: 'clear-history', input: { scope: 'wish' } })
assert(clrWish.result?.status === 'succeeded' && (clrWish.result?.cleared ?? 0) > 0, `clear-history(wish) 成功（cleared=${clrWish.result?.cleared}）`)
const rhAfterWishClear = storage.get('rank_history')?.value || {}
const rankHistSize = Object.values(rhAfterWishClear).reduce((n, b) => n + (b?.length || 0), 0)
assert(rankHistSize > 0, `清空想看历史不影响榜单历史（榜单历史 ${rankHistSize} 条）`)
const whAfter = storage.get('wish_history')?.value || {}
assert(Object.keys(whAfter).length === 0, '想看历史已清空')
const badScope = invoke('action', { id: 'clear-history', input: { scope: 'nope' } })
assert(badScope.result?.status === 'failed', '非法 scope 被拒绝')

console.log('\n== 检验 F：订阅数量只订榜单前 N 名（按榜单位置，不裁剪快照）==')
// 把华语口碑的订阅数量压到 3，榜单 RSS 有 8 条。
// 期望：快照仍展示全部 8 条；只有前 3 名参与订阅评估（其中第 2 名是电影、在剧集榜中无法识别，
// 属预期），第 4 名及以后全部标记 beyond。
invoke('action', {
  id: 'save-config',
  input: { config: { rank_configs: { tv_chinese: { enabled: true, count: 3, min_vote: 0, min_year: 0, regions: [] } } } },
})
dropAllIntents()
invoke('action', { id: 'clear-history', input: { scope: 'rank' } })
const beforeF = intentPosts.length
const callsBeforeF = tmdbSearchCalls
invoke('job', { id: 'rank-sync', handler: 'rank-sync', trigger: 'cron', attempt: 1 }, true)
const fAdded = intentPosts.length - beforeF
const dbF = invoke('action', { id: 'dashboard' })
const tvCn = (dbF.result?.ranks || []).find((r) => r.key === 'tv_chinese') || { items: [] }
const fSub = tvCn.items.filter((it) => it.status === 'subscribed').length
const fBeyond = tvCn.items.filter((it) => it.status === 'beyond').length
console.log(`  tv_chinese 快照 ${tvCn.items.length} 条（subscribed=${fSub}, beyond=${fBeyond}），本轮新增订阅 ${fAdded} 条`)
assert(tvCn.items.length === 8, `快照展示完整榜单而不受订阅数量限制（实际 ${tvCn.items.length} 条）`)
assert(fSub === 2, `count=3 时只有前 3 名可被订阅（其中 1 条为剧集榜中的电影，不可识别；实际 ${fSub}）`)
assert(fBeyond === 5, `第 4 名及以后全部标记超出订阅数量 beyond（实际 ${fBeyond}）`)
// 展示范围内（前 rankDisplayLimit=5 名）的条目即使超出订阅数量也要做 TMDB 识别，界面才有封面
const fBeyondInWindow = tvCn.items.slice(0, 5).filter((it) => it.status === 'beyond')
assert(
  fBeyondInWindow.length === 2 && fBeyondInWindow.every((it) => it.tmdb_id > 0 && it.poster),
  `展示范围内的 beyond 条目也带 TMDB 与封面（实际 ${JSON.stringify(fBeyondInWindow.map((it) => [it.title, it.tmdb_id, !!it.poster]))}）`,
)
// 展示范围外的条目不做额外的 TMDB 识别（省掉无用的宿主调用）
const fBeyondOutWindow = tvCn.items.slice(5).filter((it) => it.status === 'beyond')
assert(
  fBeyondOutWindow.length === 3 && fBeyondOutWindow.every((it) => !it.tmdb_id),
  `展示范围外的 beyond 条目不做 TMDB 识别（实际 ${JSON.stringify(fBeyondOutWindow.map((it) => [it.title, it.tmdb_id]))}）`,
)
// TMDB 缓存：重复运行不再发起相同的 TMDB 搜索
invoke('job', { id: 'rank-sync', handler: 'rank-sync', trigger: 'cron', attempt: 1 }, true)
console.log(`  TMDB 搜索调用：首轮 ${callsBeforeF} → 重复运行后 ${tmdbSearchCalls}`)
assert(tmdbSearchCalls === callsBeforeF, `TMDB 搜索结果已缓存，重复运行不重复搜索（新增 ${tmdbSearchCalls - callsBeforeF} 次）`)

console.log('\n== 检验 G：含季号剧名剥离季号后按基础剧名识别 ==')
// 「三体 第二季」「庆余年 第三季」直接搜会失败（mock 模拟真实 TMDB 对带季号查询返回空），
// 应剥离季号后用「三体」「庆余年」识别，且订阅时带上正确季号。
invoke('action', {
  id: 'save-config',
  input: { config: { rank_configs: { tv_chinese: { enabled: true, count: 5, min_vote: 0, min_year: 0, regions: [] } } } },
})
dropAllIntents()
invoke('action', { id: 'clear-history', input: { scope: 'rank' } })
const callsBeforeG = tmdbSearchCalls
invoke('job', { id: 'rank-sync', handler: 'rank-sync', trigger: 'cron', attempt: 1 }, true)
const dbG = invoke('action', { id: 'dashboard' })
const tvG = (dbG.result?.ranks || []).find((r) => r.key === 'tv_chinese') || { items: [] }
const stItem = tvG.items.find((it) => it.title.includes('三体'))
const qyItem = tvG.items.find((it) => it.title.includes('庆余年'))
console.log(`  三体 第二季 → ${stItem ? stItem.status + ' tmdb=' + stItem.tmdb_id : '快照缺失'}；庆余年 第三季 → ${qyItem ? qyItem.status + ' tmdb=' + qyItem.tmdb_id : '快照缺失'}`)
assert(stItem && stItem.status === 'subscribed' && stItem.tmdb_id === 45678, `「三体 第二季」剥离季号后识别为 TMDB 45678 并订阅（实际 ${stItem ? stItem.status + '/' + stItem.tmdb_id : '缺失'}）`)
assert(qyItem && qyItem.status === 'subscribed' && qyItem.tmdb_id === 34567, `「庆余年 第三季」剥离季号后识别为 TMDB 34567 并订阅（实际 ${qyItem ? qyItem.status + '/' + qyItem.tmdb_id : '缺失'}）`)
const santiIntent = intents.find((i) => i.tmdb_id === 45678)
const qyIntent = intents.find((i) => i.tmdb_id === 34567)
assert(santiIntent && (santiIntent.season || 0) === 2, `三体订阅季号为 2（实际 ${santiIntent ? santiIntent.season : '无订阅'}）`)
assert(qyIntent && (qyIntent.season || 0) === 3, `庆余年订阅季号为 3（实际 ${qyIntent ? qyIntent.season : '无订阅'}）`)
console.log(`  TMDB 搜索调用（检验 G 本轮）：新增 ${tmdbSearchCalls - callsBeforeG} 次`)

console.log('\n== 检验 H：黑名单拦截的条目仍带封面，且不会被订阅 ==')
// 黑名单过滤移到 TMDB 识别之后：被拦截的条目在仪表盘上依然显示封面。
invoke('action', {
  id: 'save-config',
  input: {
    config: {
      blacklist: '漫长的季节',
      rank_configs: { tv_chinese: { enabled: true, count: 5, min_vote: 0, min_year: 0, regions: [] } },
    },
  },
})
dropAllIntents()
invoke('action', { id: 'clear-history', input: { scope: 'rank' } })
const beforeH = intentPosts.length
invoke('job', { id: 'rank-sync', handler: 'rank-sync', trigger: 'cron', attempt: 1 }, true)
const dbH = invoke('action', { id: 'dashboard' })
const tvH = (dbH.result?.ranks || []).find((r) => r.key === 'tv_chinese') || { items: [] }
const blHits = tvH.items.filter((it) => it.status === 'blacklisted')
console.log(`  黑名单命中 ${blHits.length} 条：${JSON.stringify(blHits.map((it) => [it.title, it.tmdb_id, !!it.poster]))}`)
assert(blHits.length === 1, `黑名单命中的条目状态为 blacklisted（实际 ${blHits.length}）`)
assert(
  blHits.every((it) => it.tmdb_id > 0 && it.poster),
  '黑名单条目标注了 TMDB ID 与封面（识别先于过滤）',
)
assert(!intents.some((i) => i.tmdb_id === 23456), '被黑名单拦截的条目不会被订阅')
assert(
  (dbH.result?.blacklist_hits || []).some((it) => it.title.includes('漫长的季节')),
  `仪表盘黑名单区块包含被拦截的条目（实际 ${(dbH.result?.blacklist_hits || []).length} 条）`,
)
invoke('action', { id: 'save-config', input: { config: { blacklist: '' } } })

console.log('\n== 检验 I：BangumiTV 长标题的 TMDB 变体回退 ==')
invoke('action', {
  id: 'save-config',
  input: {
    config: {
      rank_configs: { bangumi: { enabled: true, count: 3, min_vote: 0, min_year: 0, regions: [] } },
    },
  },
})
invoke('action', { id: 'clear-history', input: { scope: 'rank' } })
// 预置一份「旧版识别策略」缓存（version=1，且把长标题记成了未识别）。
// 新代码应因版本号不符而丢弃它，条目重新识别并成功 —— 保证识别逻辑的修复对存量用户生效。
storage.set('tmdb_cache', { value: { version: 1, items: { 'tv:reゼロ:': null, 'tv:スティール:': null } }, etag: 'stale' })
const callsBeforeI = tmdbSearchCalls
invoke('job', { id: 'rank-sync', handler: 'rank-sync', trigger: 'cron', attempt: 1 }, true)
const dbI = invoke('action', { id: 'dashboard' })
const bgm = (dbI.result?.ranks || []).find((r) => r.key === 'bangumi') || { items: [] }
console.log(`  bangumi 快照 ${bgm.items.length} 条：`)
for (const it of bgm.items) console.log(`    ${it.status.padEnd(10)} tmdb=${it.tmdb_id} poster=${!!it.poster}  ${it.title}`)
assert(bgm.items.length === 2, `bangumi 快照展示 2 条（实际 ${bgm.items.length}）`)
const reiItem = bgm.items.find((it) => it.title.includes('ゼロから始める'))
assert(
  reiItem && reiItem.status === 'subscribed' && reiItem.tmdb_id === 51111 && reiItem.poster,
  `「…4th season 奪還編」剥掉篇章名后识别为 51111 并订阅（实际 ${JSON.stringify(reiItem && [reiItem.status, reiItem.tmdb_id, !!reiItem.poster])}）`,
)
const sbrItem = bgm.items.find((it) => it.title.includes('スティール・ボール・ラン'))
assert(
  sbrItem && sbrItem.status === 'subscribed' && sbrItem.tmdb_id === 52222 && sbrItem.poster,
  `「スティール・ボール・ラン …STAGE」截短后识别为 52222 并订阅（实际 ${JSON.stringify(sbrItem && [sbrItem.status, sbrItem.tmdb_id, !!sbrItem.poster])}）`,
)
assert(!bgm.items.some((it) => it.status === 'unresolved'), 'bangumi 快照没有未识别条目（全部靠变体回退命中）')
const cacheI = storage.get('tmdb_cache')?.value || {}
assert(cacheI.version === 4, `旧版 TMDB 缓存被识别策略版本号作废并重写为 v4（实际 ${cacheI.version}）`)
assert(!cacheI.items?.['tv:reゼロ:'], '旧缓存里的「未识别」记录没有被沿用')
const bgmIntents = intents.filter((i) => i.tmdb_id === 51111 || i.tmdb_id === 52222)
assert(bgmIntents.length === 2, `两条长标题条目各建 1 次订阅（实际 ${bgmIntents.length}）`)
console.log(`  TMDB 搜索调用（检验 I 本轮）：新增 ${tmdbSearchCalls - callsBeforeI} 次`)

console.log('\n== 检验 J：无关候选被拒绝 → 豆瓣原名回退 → 历史错配按版本刷新 ==')
// 真实案例：TMDB 搜「流人」返回的第一条是票数极高的《潮流合伙人》，
// 旧实现按票数排序把它当成《流人 第六季》，封面因此张冠李戴。
// 现在名称相关性不达标的候选会被打分拒收，《流人 第六季》靠豆瓣原名兜底命中。
// 清掉 TMDB 缓存与豆瓣原名缓存，逼使本轮真的走一遍识别（否则会命中前序用例留下的缓存）
aliasRequests.length = 0
storage.delete('douban_alias')
storage.set('tmdb_cache', { value: { version: 4, items: {} }, etag: 'cleared' })
invoke('action', {
  id: 'save-config',
  input: {
    config: {
      rank_configs: {
        bangumi: { enabled: false, count: 3, min_vote: 0, min_year: 0, regions: [] },
        tv_global: { enabled: true, count: 5, min_vote: 0, min_year: 0, regions: [] },
      },
    },
  },
})
dropAllIntents()
invoke('action', { id: 'clear-history', input: { scope: 'rank' } })
invoke('job', { id: 'rank-sync', handler: 'rank-sync', trigger: 'cron', attempt: 1 }, true)
const dbJ = invoke('action', { id: 'dashboard' })
const tvJ = (dbJ.result?.ranks || []).find((r) => r.key === 'tv_global') || { items: [] }
console.log(`  tv_global 快照 ${tvJ.items.length} 条：`)
for (const it of tvJ.items) console.log(`    ${it.status.padEnd(10)} tmdb=${it.tmdb_id} poster=${!!it.poster}  ${it.title}`)
const liuren = tvJ.items.find((it) => it.title.includes('流人'))
assert(
  liuren && liuren.tmdb_id !== 99999 && liuren.tmdb_id !== 99998,
  `《流人 第六季》不会被配成《潮流合伙人》这类无关条目（实际 tmdb=${liuren && liuren.tmdb_id}）`,
)
assert(
  liuren && liuren.tmdb_id === 95480 && liuren.status === 'subscribed' && String(liuren.poster || '').startsWith('https://image.tmdb.org/'),
  `《流人 第六季》识别为 95480 并订阅（实际 ${JSON.stringify(liuren && [liuren.status, liuren.tmdb_id, liuren.poster])}）`,
)
// 《流人 第六季》在 TMDB 没有中文标题，标题搜索全部被拒收后，靠豆瓣原名兜底命中：
assert(
  aliasRequests.some((r) => r.url.endsWith('/tv/36000001')),
  '标题搜索失败后走豆瓣原名兜底（实际 ' + JSON.stringify(aliasRequests.map((r) => r.url)) + '）',
)
const yani = tvJ.items.find((it) => it.title.includes('ヤニねこ'))
assert(
  yani && yani.tmdb_id === 88888 && yani.poster,
  `「ヤニねこ」本地化名对不上时靠 TMDB 原名匹配到 88888（实际 ${JSON.stringify(yani && [yani.tmdb_id, !!yani.poster])}）`,
)
assert(
  !intents.some((i) => i.tmdb_id === 99999 || i.tmdb_id === 99998),
  '被拒绝的无关联想条目没有被拿去建订阅',
)

// 历史错配刷新：把已订阅条目在历史里的 TMDB 关联改成旧策略留下的错配值，
// 识别策略版本号落后时应重新识别并回写，否则错误封面会随历史一直沿用。
const rhJ = storage.get('rank_history')?.value || {}
const tampered = (rhJ.tv_global || []).find((h) => String(h.title || '').includes('ヤニねこ'))
assert(tampered && tampered.subscribed, '历史里找到已订阅的「ヤニねこ」')
tampered.tmdb_id = 99999
tampered.poster = 'https://image.tmdb.org/t/p/w500/wrong-poster.jpg'
tampered.resolve_ver = 0
storage.set('rank_history', { value: rhJ, etag: 'tampered' })
storage.set('tmdb_cache', { value: { version: 4, items: {} }, etag: 'cleared' })
invoke('job', { id: 'rank-sync', handler: 'rank-sync', trigger: 'cron', attempt: 1 }, true)
const fixed = (storage.get('rank_history')?.value?.tv_global || []).find((h) => String(h.title || '').includes('ヤニねこ'))
assert(
  fixed && fixed.tmdb_id === 88888 && String(fixed.poster).includes('/p.jpg') && !String(fixed.poster).includes('wrong'),
  `历史里的错配封面被按新策略修正（实际 ${JSON.stringify(fixed && [fixed.tmdb_id, fixed.poster])}）`,
)
assert(fixed && fixed.resolve_ver === 4, `修正后的历史条目记录识别策略版本号（实际 ${fixed && fixed.resolve_ver}）`)

console.log('\n== 检验 K：豆瓣原名兜底（TMDB 没有中文标题的条目）==')
// 真实案例：TMDB 里这部剧只有英文名 Slow Horses（中文本地化名就是原名），
// 搜「流人」只会返回标题里恰含「流人」二字的无关条目，识别逻辑为避免张冠李戴把
// 它们全部拒收 —— 结果是「TMDB 未匹配」，永远看不到封面。这里用同一部剧的另一个
// 豆瓣条目「驽马 第六季」验证：标题搜索给不出结论时，拿豆瓣条目自己的
// 原名 Slow Horses Season 6 重搜即可命中。
aliasRequests.length = 0
storage.delete('douban_alias')
storage.set('tmdb_cache', { value: { version: 4, items: {} }, etag: 'cleared' })
invoke('action', {
  id: 'save-config',
  input: {
    config: {
      rank_configs: {
        tv_global: { enabled: true, count: 5, min_vote: 0, min_year: 0, regions: [] },
        // 电影口碑榜：豆瓣条目里混着剧集（豆瓣条目类型与榜单类型不一致），
        // 用它触发「取原名时类型不符 → 301 → 按真实地址重试」这条路径
        movie_weekly: { enabled: true, count: 5, min_vote: 0, min_year: 0, regions: [] },
      },
    },
  },
})
invoke('action', { id: 'clear-history', input: { scope: 'rank' } })
storageGets.length = 0
invoke('job', { id: 'rank-sync', handler: 'rank-sync', trigger: 'cron', attempt: 1 }, true)
const dbK = invoke('action', { id: 'dashboard' })
const ranksK = dbK.result?.ranks || []
const rankOf = (k) => ranksK.find((r) => r.key === k) || { items: [] }
const liurenK = rankOf('tv_global').items.find((it) => it.title.includes('流人'))
assert(
  liurenK && liurenK.tmdb_id === 95480,
  `《流人 第六季》识别为 Slow Horses（95480）（实际 ${liurenK && liurenK.tmdb_id}）`,
)
assert(
  String(liurenK.poster || '').startsWith('https://image.tmdb.org/'),
  `榜单封面回到 TMDB（实际 ${String(liurenK && liurenK.poster).slice(0, 52)}）`,
)
assert(!Object.keys(liurenK).includes('cover_key'), '榜单快照不再下发豆瓣封面字段（豆瓣封面机制已整体移除）')

// 驽马 第六季：标题搜索不中，靠豆瓣原名兜底命中
const niumaK = rankOf('tv_global').items.find((it) => it.title.includes('驽马'))
assert(
  niumaK && niumaK.tmdb_id === 95480 && String(niumaK.poster || '').startsWith('https://image.tmdb.org/'),
  `标题搜不到时回落豆瓣原名兜底：《驽马 第六季》→ 95480（实际 ${JSON.stringify(niumaK && [niumaK.tmdb_id, niumaK.poster])}）`,
)

// 豆瓣原名只对「标题真的搜不到」的条目才请求
const aliasSubjects = new Set(aliasRequests.map((r) => (r.url.match(/(\d+)$/) || [])[1]))
assert(
  aliasRequests.length > 0 && aliasRequests.every((r) => /^https:\/\/m\.douban\.com\/rexxar\/api\/v2\/(tv|movie)\/\d+$/.test(r.url)),
  `同步时为识别失败的条目请求豆瓣原名接口（实际 ${aliasRequests.length} 次：${[...aliasSubjects].join(', ')}）`,
)
assert(
  !aliasSubjects.has('37000001'),
  'ヤニねこ一次就靠 TMDB 原名命中，不该再去豆瓣取原名',
)
assert(
  aliasSubjects.has('36000001'),
  '《流人 第六季》标题搜索失败后读豆瓣原名兜底',
)
assert(
  aliasRequests.every((r) => /^https:\/\/m\.douban\.com\//.test(r.referer)),
  `取原名带豆瓣 referer（实际 ${JSON.stringify([...new Set(aliasRequests.map((r) => r.referer))])}）`,
)
assert(
  aliasRequests.some((r) => r.url.endsWith('/tv/36000002')),
  '《驽马 第六季》按剧集类型取到豆瓣原名',
)
// 类型不符时豆瓣 301，插件按响应体里的真实地址纠正后重试
assert(
  aliasRequests.some((r) => r.url.endsWith('/movie/35123456')) && aliasRequests.some((r) => r.url.endsWith('/tv/35123456')),
  `取原名时类型猜错（movie）会按豆瓣 301 纠正为 tv 并重试（实际 ${JSON.stringify(aliasRequests.map((r) => r.url.split('/api/v2/')[1]))}）`,
)

// 原名/又名缓存
const aliasCache = storage.get('douban_alias')?.value || {}
assert(aliasCache.version === 1, `原名缓存带版本号（实际 ${aliasCache.version}）`)
assert(
  aliasCache.items?.['36000002']?.original === 'Slow Horses Season 6',
  `原名缓存写入 Slow Horses Season 6（实际 ${aliasCache.items?.['36000002']?.original}）`,
)
assert(
  (aliasCache.items?.['36000002']?.aka || []).length === 2 && (aliasCache.items?.['36000002']?.aka || []).every((s) => !/[（(）)]/.test(s)),
  `又名里的「(港)/(台)」注释被清理（实际 ${JSON.stringify(aliasCache.items?.['36000002']?.aka)}）`,
)

// 第二轮：兜底命中过的条目结果已写回「榜单标题」缓存键 → 直接命中，
// 既不再请求豆瓣，也不再读一次原名缓存（仍识别不出的条目才会再读）。
const aliasReads1 = storageGets.filter((k) => k === 'douban_alias').length
aliasRequests.length = 0
storageGets.length = 0
invoke('job', { id: 'rank-sync', handler: 'rank-sync', trigger: 'cron', attempt: 1 }, true)
const aliasReads2 = storageGets.filter((k) => k === 'douban_alias').length
assert(aliasRequests.length === 0, `原名已缓存，下一轮不再请求豆瓣（实际 ${aliasRequests.length} 次）`)
assert(
  aliasReads2 < aliasReads1,
  `兜底命中过的条目下一轮不再读原名缓存（第 1 轮 ${aliasReads1} 次 → 第 2 轮 ${aliasReads2} 次）`,
)
const itemsK = storage.get('tmdb_cache')?.value?.items || {}
const titleKeyK = Object.keys(itemsK).find((k) => k.startsWith('v4:tv:') && k.includes('驽马'))
assert(
  titleKeyK && itemsK[titleKeyK]?.id === 95480,
  `兜底命中的结果写回「榜单标题」缓存键，下一轮直接命中（实际 ${titleKeyK}=${itemsK[titleKeyK]?.id}）`,
)
const keysK = Object.keys(itemsK)
assert(
  keysK.some((k) => k.includes('slowhorses')),
  `豆瓣原名搜到的结果写进 TMDB 缓存（实际 ${JSON.stringify(keysK.filter((k) => k.includes('slow')).slice(0, 3))}）`,
)

// 豆瓣封面机制已整体移除：没有封面缓存，也没有 rank-covers 动作
assert(
  ![...storage.keys()].some((k) => k.startsWith('cover_')),
  `不再有豆瓣封面缓存（实际 ${JSON.stringify([...storage.keys()].filter((k) => k.startsWith('cover_')))}）`,
)
assert(
  invoke('action', { id: 'rank-covers', input: { rank: 'tv_global' } }).result?.code === 'unknown_action',
  'rank-covers 动作已随豆瓣封面一起移除',
)

console.log('\n== 检验 L：长任务分片执行 + 断点续跑 ==')
{
  // 先把历史清干净，保证这一轮要处理的条目足够多
  invoke('action', { id: 'clear-history', input: { scope: 'rank' } })
  invoke('action', {
    id: 'save-config',
    input: {
      config: {
        rank_configs: {
          tv_chinese: { enabled: true, count: 5, min_vote: 0, min_year: 0, regions: [] },
          tv_global: { enabled: true, count: 5, min_vote: 0, min_year: 0, regions: [] },
          movie_weekly: { enabled: true, count: 5, min_vote: 0, min_year: 0, regions: [] },
        },
      },
    },
  })
  // 1) 慢速模式下跑一整轮：任务内部应按片推进，片与片之间有让出空隙
  callTimes.length = 0
  slowModeMs = 150
  invoke('action', { id: 'run-ranks' })
  const jobRes = invoke('job', { id: 'rank-sync', handler: 'rank-sync', trigger: 'cron', attempt: 1 }, true)
  slowModeMs = 0
  assert(jobRes.result?.status === 'accepted', '分片任务 job 调用返回 accepted')
  let maxGap = 0
  for (let i = 1; i < callTimes.length; i++) {
    maxGap = Math.max(maxGap, callTimes[i] - callTimes[i - 1])
  }
  console.log(`  本轮 host.call ${callTimes.length} 次，最大间隔 ${maxGap}ms`)
  assert(callTimes.length > 5, `本轮确实发起了多次宿主调用（实际 ${callTimes.length}）`)
  assert(maxGap >= 500, `片与片之间有让出空隙，宿主可回收控制权（实际最大间隔 ${maxGap}ms）`)

  const stL = invoke('state', { view: 'main' })
  assert(stL.result?.state?.lastStatus === 'succeeded', `分片任务最终完成（实际 ${stL.result?.state?.lastStatus}）`)
  assert(!storage.get('job_state')?.value?.kind, '任务完成后 job_state 已清空，不会卡住后续调度')
  const reqL = storage.get('run_requests')?.value || {}
  assert((reqL.rank || 0) === 0, '分片任务结束后队列标记已清除')

  // 2) 注入一个「上次中断」的半成品 job state：应从中途继续，而不是从头重来
  const nowJs = () => {
    const d = new Date()
    const p = (n) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
  }
  const wishLike = [
    { title: '漫长的季节', link: 'https://movie.douban.com/subject/35123456/', douban_id: '35123456', year: '2023', media_type: 'tv', category: '剧集' },
    { title: '庆余年 第三季', link: 'https://movie.douban.com/subject/35345678/', douban_id: '35345678', year: '2026', media_type: 'tv', category: '剧集' },
    { title: '三体 第二季', link: 'https://movie.douban.com/subject/35456789/', douban_id: '35456789', year: '2026', media_type: 'tv', category: '剧集' },
  ]
  storage.set('job_state', {
    value: {
      kind: 'rank', manual: false, phase: 'process', started_at: nowJs(), updated_at: nowJs(),
      slices: 3, lines: [],
      rank: {
        // 第 1 条已处理（pos=1），续跑应从第 2 条开始
        ranks: [{ key: 'tv_chinese', name: '华语口碑', route: '/douban/list/tv_chinese_best_weekly', media_type: 'tv', count: 5, min_vote: 0, min_year: 0, fetch_size: 20, fetched: true, items: wishLike, snap: [] }],
        idx: 0, pos: 1, total: 3, done: 1, new_subs: 0, existing_movie: [], existing_tv: [], pool_read: false,
      },
    },
    etag: 'resume-test',
  })
  const resumeRes = invoke('job', { id: 'rank-sync', handler: 'rank-sync', trigger: 'cron', attempt: 1 }, true)
  assert(resumeRes.result?.status === 'accepted', '续跑调用返回 accepted')
  const stResume = invoke('state', { view: 'main' })
  assert(stResume.result?.state?.lastStatus === 'succeeded', `注入的断点任务被执行完成（实际 ${stResume.result?.state?.lastStatus}）`)
  assert(!storage.get('job_state')?.value?.kind, '续跑完成后 job_state 同样被清空')
}

console.log('\n== shutdown ==')
const sd = rpc('runtime.shutdown', { reason: 'conformance' })
assert(sd.result?.stopping === true, 'runtime.shutdown')

console.log('\n完成。storage keys:', [...storage.keys()].join(', '))
