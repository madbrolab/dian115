export async function run(ctx, input) {
  // input.trigger says which rule matched: command, prefix, keyword or pattern.
  const text = input.trigger.type === 'prefix' ? input.text.slice(input.trigger.value.length) : input.text
  const buttons = input.channel === 'telegram' ? [[{ text: '再试一次', callback_data: 'again' }]] : undefined
  await ctx.messaging.reply(input, { text: '收到：' + text, buttons })
}
