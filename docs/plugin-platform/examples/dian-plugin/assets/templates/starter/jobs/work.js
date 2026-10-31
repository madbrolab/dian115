export async function run(ctx, input) {
  await ctx.task.update({ stage: 'read', message: '读取账号状态' })
  const status = await ctx.api.get('/api/115/status')
  await ctx.storage.set('last', { at: new Date().toISOString(), input })
  await ctx.task.log(JSON.stringify(status))
  return status
}

// Called after a restart interrupted the job. This job only reads, so it can
// run again; a job that writes must check the real result here first.
export async function recover() {
  return { action: 'resume' }
}
