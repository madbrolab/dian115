import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

// Generate only from the public catalog; usable outside the main repository.
export function generateReference(text) {
  const catalog = text.split('x-dian115-host-apis:')[1]?.split('\nx-dian115-subscription-host-apis:')[0]
  if (!catalog) throw new Error('public Host API catalog is missing')
  const entries = [...catalog.matchAll(/^    - method: (\S+)\n      path: (\S+)\n      category: (\S+)\n      risk: (\S+)\n      title: (.+)\n      description: (.+)\n      host_credentials: (true|false)/gm)].map(match => ({ method: match[1], path: match[2], category: match[3], risk: match[4], title: JSON.parse(match[5]), description: JSON.parse(match[6]), credentials: match[7] === 'true' }))
  if (!entries.length) throw new Error('public Host API catalog has no entries')
  const categories = [...new Set(entries.map(entry => entry.category))].sort()
  const escape = value => String(value).replaceAll('|', '\\|').replaceAll('\n', ' ')
  let output = `# 宿主接口速查表\n\n从 [OpenAPI](openapi-v1.yaml) 的公开目录生成，共 ${entries.length} 项。安装时声明精确的方法和路径模板；调用方式见 [Host Call v2](host-call-v2.md)。\n\n网络声明是代理路由偏好。扩展访问与可选接口规则见开发指南；下表描述标准目录。\n`
  for (const category of categories) {
    output += `\n## ${category}\n\n| 方法 | 路径模板 | 用途 | 风险 | 宿主管理凭据 |\n| --- | --- | --- | --- | --- |\n`
    for (const entry of entries.filter(entry => entry.category === category)) output += `| ${entry.method} | \`${entry.path}\` | ${escape(entry.title)}：${escape(entry.description)} | ${{ read: '读取', write: '写入', dangerous: '删除或不可逆操作' }[entry.risk] || escape(entry.risk)} | ${entry.credentials ? '是' : '否'} |\n`
  }
  return output
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const target = new URL('../host-api-quick-reference.md', import.meta.url)
  const output = generateReference(readFileSync(new URL('../openapi-v1.yaml', import.meta.url), 'utf8'))
  if (process.argv.includes('--check')) {
    if (readFileSync(target, 'utf8') !== output) throw new Error('Host API reference is out of date; run generate-reference.mjs')
  } else writeFileSync(target, output)
}
