// Host business events (organize, STRM, library...) arrive as {id,type,title,content,data,at}.
export async function run(ctx, event) {
  const history = (await ctx.storage.get('host-events')) || []
  history.unshift({ type: event.type, title: event.title || event.data?.title || '', at: event.at })
  await ctx.storage.set('host-events', history.slice(0, 20))
  return { recorded: event.type }
}
