export async function run(ctx) {
  const { url } = await ctx.settings.get()
  if (!url) {
    // Waiting avoids a tight restart loop until the user fills in the setting.
    await ctx.sleep(60000)
    return
  }
  const socket = await ctx.ws.connect({ url })
  console.log('已连接：' + url)
  for (;;) {
    const message = await socket.receive()
    if (message.type === 'close') throw new Error('连接关闭：' + message.code)
    if (message.type === 'text') await ctx.notify({ title: '新事件', body: message.text.slice(0, 500) })
  }
}
