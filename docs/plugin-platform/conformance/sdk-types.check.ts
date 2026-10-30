import type { BackgroundContext } from '../examples/sdk/background.js'
import type { OfflineTaskList, ShareReceiveResult, TmdbMovieDetail } from '../examples/sdk/core-types.js'
type Equal<A, B> = (<T>() => T extends A ? 1 : 2) extends (<T>() => T extends B ? 1 : 2) ? true : false
const assert = <T extends true>() => {}
export async function run(ctx: BackgroundContext) {
  const tasks = await ctx.api.get('/api/115/offline/tasks?page=1&status=downloading')
  assert<Equal<typeof tasks, OfflineTaskList>>()
  const first = tasks.items[0].progress
  const r = await ctx.api.post('/api/115/share/receive', { share_url: 'https://115cdn.com/s/x', target_cid: '0' })
  assert<Equal<typeof r, ShareReceiveResult>>()
  const movie = await ctx.api.get('/api/tmdb/movie/603')
  assert<Equal<typeof movie, TmdbMovieDetail>>()
  // @ts-expect-error unknown body field is rejected
  await ctx.api.post('/api/115/share/receive', { share_link: 'x' })
  const other = await ctx.api.get('/api/not-documented')
  assert<Equal<typeof other, unknown>>()
  const dynamic: string = '/api/history'
  const any = await ctx.api.get(dynamic)
  assert<Equal<typeof any, unknown>>()
  return first
}
