export async function handle(ctx, request) {
  const { secret } = await ctx.settings.get()
  // Public hooks need no host login, so the secret is the only gate.
  if (!secret || request.headers['X-Secret']?.[0] !== secret) return { status: 401, json: { error: 'denied' } }
  await ctx.notify({ title: '收到回调', body: (request.body || '').slice(0, 500) })
  return { json: { ok: true } }
}
