// Generates host-api-quick-reference.md (one line per route) and
// host-api-reference.md (parameters, fields, call snippet and examples per route).
//   node generate-reference.mjs          write
//   node generate-reference.mjs --check  fail when either file is stale
import { readFileSync, writeFileSync } from 'node:fs'
import { root, operations, resolve, jsonContent, successResponse, parameters, sample, typeLabel, fieldRows } from './openapi-model.mjs'

const ops = operations()
const cell = v => String(v ?? '').replaceAll('|', ' / ').replaceAll('\n', ' ')
const quick = '# 宿主接口速查\n\n插件通过普通 HTTP 调用宿主 API。以下仅列出插件可调用的公开稳定契约，权限仍由宿主检查。运行中的宿主仍按自身版本与业务配置处理请求。`/v3/releases` 为独立加密服务接口，不在 DIAN115 宿主端口。逐个接口的参数、字段与示例见[宿主接口参考](host-api-reference.md)。\n\n| 方法 | 路径 | 用途 |\n| --- | --- | --- |\n' +
  ops.map(({ path, method, op }) => `| ${method.toUpperCase()} | \`${path}\` | ${cell(op.summary)} |`).join('\n') + '\n'

const groupOf = path => {
  if (path.startsWith('/plugin-hooks') || path.startsWith('/api/extensions')) return '插件平台'
  if (path.startsWith('/v3/')) return '加密服务'
  return path.split('/')[2] || '其他'
}
const groupTitles = { '115': '115 账号、离线与分享', 'local-files': '宿主文件管理', 'local-dirs': '宿主文件管理', browse: 'CD2', cd2: 'CD2', 'plugin-host': 'Emby', 'emby-control': 'Emby', organize: '整理', rules: '同步规则与 STRM', subscribe: '订阅', tmdb: 'TMDB', tasks: '任务队列', workqueue: '任务队列', scheduler: '任务队列', dashboard: '看板与历史', history: '看板与历史', library: '媒体库' }
const anchor = (method, path) => `${method}-${path}`.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')

function pathWithSamples(path, op) {
  return path.replace(/\{([^}]+)\}/g, (_, name) => {
    const p = parameters(op).find(x => x.in === 'path' && x.name === name)
    return encodeURIComponent(String(sample(p?.schema || { type: 'string' }, name) ?? name)).replace(/%3C|%3E/g, '')
  })
}

function section({ path, method, op }) {
  const lines = [`### ${method.toUpperCase()} \`${path}\``, '', `<a id="${anchor(method, path)}"></a>`, '', cell(op.summary) + '。' + (op.description ? ' ' + op.description : '')]
  const params = parameters(op).filter(p => p.in !== 'header')
  if (params.length) {
    lines.push('', '**参数**', '', '| 名称 | 位置 | 类型 | 必填 | 说明 |', '| --- | --- | --- | --- | --- |')
    for (const p of params) lines.push(`| \`${p.name}\` | ${p.in} | ${cell(typeLabel(p.schema))} | ${p.required ? '是' : ''} | ${cell(p.description)} |`)
  }
  const body = jsonContent(op.requestBody)
  if (body) {
    const rows = fieldRows(body.schema)
    if (rows.length) {
      lines.push('', '**请求体（JSON）**', '', '| 字段 | 类型 | 必填 | 说明 |', '| --- | --- | --- | --- |')
      for (const r of rows) lines.push(`| \`${r.key}\` | ${cell(r.type)} | ${r.required ? '是' : ''} | ${cell(r.description)} |`)
    }
  } else if (resolve(op.requestBody)?.content) {
    lines.push('', `**请求体**：${Object.keys(resolve(op.requestBody).content).join(' / ')}`)
  }
  // Call snippet
  let url = pathWithSamples(path, op)
  const query = op['x-example-query'] || parameters(op).filter(p => p.in === 'query' && p.required).map(p => `${p.name}=${encodeURIComponent(String(sample(p.schema, p.name)))}`).join('&')
  if (query) url += '?' + query
  const requestExample = body ? (body.example ?? sample(body.schema)) : undefined
  if (path.startsWith('/api/')) {
    const call = method === 'get' || method === 'head' || method === 'delete' && !body
      ? `const res = await ctx.api.${method}('${url}')`
      : `const res = await ctx.api.${method}('${url}', ${JSON.stringify(requestExample ?? {}, null, 2)})`
    lines.push('', '**调用**', '', '```js', call, '```')
  }
  const ok = successResponse(op)
  const content = ok && jsonContent(ok.response)
  if (content) {
    const handWritten = content.example !== undefined
    const example = handWritten ? content.example : sample(content.schema)
    lines.push('', `**响应 ${ok.status}**${handWritten ? '' : '（按契约结构生成的示例值）'}`, '', '```json', JSON.stringify(example, null, 2), '```')
    const rows = fieldRows(content.schema)
    if (rows.length) {
      lines.push('', '| 字段 | 类型 | 说明 |', '| --- | --- | --- |')
      for (const r of rows) lines.push(`| \`${r.key}\` | ${cell(r.type)} | ${cell(r.description)} |`)
    } else if (!resolve(content.schema)?.properties) {
      lines.push('', '响应为宿主或上游服务原样透传的 JSON，字段可能随上游变化；以 HTTP 2xx 判断成功。')
    }
  } else if (ok) {
    lines.push('', `**响应 ${ok.status}**：${cell(ok.response?.description)}`)
  }
  return lines.join('\n')
}

const groups = new Map()
for (const item of ops) {
  const title = groupTitles[groupOf(item.path)] || groupOf(item.path)
  if (!groups.has(title)) groups.set(title, [])
  groups.get(title).push(item)
}
const reference = ['# 宿主接口参考', '',
  '本页由 `openapi-v3.json` 生成：每个接口的参数、请求字段、调用写法、示例和响应字段。字段说明来自宿主代码注释、[字段词汇表](conformance/api-glossary.json)与[常用接口示例](conformance/api-cookbook.json)；手写示例已按契约校验。', '',
  '## 调用与解析约定', '',
  '- 后台用 `ctx.api.get/post/put/patch/delete(path, body)`，页面用同名的 `ctx.api`；路径必须以 `/api/` 开头，GET 参数写在查询串里。',
  '- 返回值就是接口原始 JSON（不再包一层）。不同接口的外层结构不同：有的直接是对象，有的为 `{code:"ok",data}`，以本页“响应”为准。',
  '- HTTP 非 2xx 时抛错：后台错误对象含 `status`、`method`、`path`、`data`（通常为 `{error:"原因"}`）；页面沿用 Axios 错误（`e.response.status`、`e.response.data.error`）。',
  '- 写操作超时或中断时先查询业务结果再决定是否重试，不要盲目重发转存、离线等外部动作。',
  '- 115 目录只按节点 ID（cid）和父 ID 组织；名称是不透明元数据。', '',
  '## 目录', '', ...[...groups.keys()].map(t => `- [${t}](#${t.toLowerCase().replace(/[^a-z0-9一-龥]+/g, '-').replace(/^-|-$/g, '')})（${groups.get(t).length}）`), '',
  ...[...groups].flatMap(([title, items]) => [`## ${title}`, '', ...items.map(section).flatMap(s => [s, ''])])
].join('\n').trimEnd() + '\n'

const outputs = [[new URL('host-api-quick-reference.md', root), quick], [new URL('host-api-reference.md', root), reference]]
for (const [target, content] of outputs) {
  if (process.argv.includes('--check')) {
    let current = ''
    try { current = readFileSync(target, 'utf8') } catch {}
    if (current !== content) throw Error(`${target.pathname.split('/').pop()} 未同步，请运行 generate-reference.mjs`)
  } else writeFileSync(target, content)
}
console.log(`接口文档${process.argv.includes('--check') ? '一致' : '已更新'}：${ops.length} 个接口`)
