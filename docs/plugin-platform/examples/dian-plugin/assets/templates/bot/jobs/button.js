export async function run(ctx, input) {
  await ctx.telegram.bot.send({ chat_id: input.chat_id, text: '按钮：' + input.data })
}
