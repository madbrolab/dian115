#!/usr/bin/env node
// Structure check, malware scan and optional packing in one step.
//   node check.mjs <插件目录> [--pack <目录外的输出.dian115p>]
import { resolve } from 'node:path'
import { checkProject } from '../assets/public-kit/conformance/project-check.mjs'
import { auditPlugin } from '../assets/public-kit/conformance/audit.mjs'
import { packPlugin } from '../assets/public-kit/conformance/pack.mjs'

const args = process.argv.slice(2), packIndex = args.indexOf('--pack')
const output = packIndex >= 0 ? args[packIndex + 1] : ''
const directory = args.find((arg, index) => !arg.startsWith('--') && index !== packIndex + 1 || (packIndex < 0 && !arg.startsWith('--')))
if (!directory || (packIndex >= 0 && !output)) { console.error('用法：node check.mjs <插件目录> [--pack <目录外的输出.dian115p>]'); process.exit(64) }

const project = checkProject(resolve(directory))
if (project.errors.length) { console.error('结构检查失败：\n' + project.errors.map(item => '- ' + item).join('\n')); process.exit(1) }
console.log(`结构检查通过：${project.manifest.id} ${project.manifest.version}`)

const report = auditPlugin(directory)
console.log(`安全扫描：${report.verdict}  ${report.summary}`)
for (const item of report.findings.filter(finding => finding.severity === 'critical' || finding.severity === 'high')) {
  console.log(`- [${item.severity}] ${item.title}  ${item.file}${item.line ? ':' + item.line : ''}`)
}
if (report.verdict === 'do-not-install') { console.error('存在高危特征，已停止。确认是误报后再单独运行 pack.mjs。'); process.exit(2) }
if (output) {
  const packed = packPlugin(directory, output)
  console.log('已打包：' + (packed?.output || output))
}
