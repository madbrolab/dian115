/** Preserve a useful asset basename without leaking signed URLs or secrets. */
export function pluginErrorDetail(reason: unknown): string {
  let detail = '插件页面发生错误'
  try {
    if (reason instanceof Error) detail = `${reason.message}\n${reason.stack || ''}`
    else if (typeof reason === 'string') detail = reason
  } catch { /* Error accessors belong to the plugin. */ }
  detail = detail.slice(0, 6000)
    .replace(/https?:\/\/[^\s<>"']+/gi, value => {
      try {
        const name = new URL(value).pathname.split('/').pop() || ''
        return /^[A-Za-z0-9_.-]{1,160}\.(?:m?js|css|html|woff2?|png|jpe?g|svg)$/i.test(name) ? `[resource:${name}]` : '[resource]'
      } catch { return '[resource]' }
    })
    .replace(/\bBearer\s+[^\s,;"']+/gi, 'Bearer [redacted]')
    .replace(/((?:["']?(?:password|passwd|token|secret|api[_-]?key|authorization|cookie)["']?)\s*[:=]\s*)(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\s,;]+)/gi, '$1[redacted]')
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, ' ')
  while (new TextEncoder().encode(detail).length > 3000) detail = detail.slice(0, Math.floor(detail.length * .8))
  return detail || '插件页面发生错误'
}
