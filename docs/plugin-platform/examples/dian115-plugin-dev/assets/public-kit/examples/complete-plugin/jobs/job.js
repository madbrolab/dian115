export async function run(ctx, input) {
  const previous = await ctx.storage.get('probe-count') || 0
  await ctx.task.checkpoint({ stage: 'before-write', previous })
  await ctx.storage.set('probe-count', previous + 1)
  const result = { count: previous + 1, echo: input }
  await ctx.task.checkpoint({ stage: 'written', result })
  await ctx.task.update({ progress: 100, message: '存储与任务接口完成' })
  return result
}
export async function recover(ctx, checkpoint) {
  if (checkpoint?.stage === 'written') return { action: 'complete', result: checkpoint.result }
  if (checkpoint?.stage === 'before-write') {
    const count = await ctx.storage.get('probe-count')
    if (count === checkpoint.previous) return { action: 'resume' }
    if (count === checkpoint.previous + 1) return { action: 'complete', result: { count, recovered: true } }
  }
  return { action: 'attention' }
}
