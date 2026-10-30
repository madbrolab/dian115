// Webhook / listener handler. Requests arrive from /api/extensions/v3/<id>/hook/...,
// /plugin-hooks/<id>/... (http.public) and listeners started with ctx.server.listen.
export async function handle(ctx, req) {
  const settings = await ctx.settings.get()
  if (req.source === 'public' && req.query.token !== settings.hook_token) return { status: 401, json: { error: 'token required' } }
  if (req.path === '/probe-file') return { file: 'probe.txt' }
  const digest = ctx.crypto.sha256(req.body_base64 ? ctx.codec.base64Decode(req.body_base64) : '')
  return { json: { plugin: ctx.plugin.id, method: req.method, path: req.path, query: req.query, sha256: digest, source: req.source } }
}
