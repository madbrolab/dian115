import type { PluginJob, PluginUIBridge } from '../../sdk/ui'

export interface BackgroundJobState {
  job: PluginJob | null
  ready: boolean
  busy: boolean
}

/** No polling or implicit retries. Persist intent before every start attempt. */
export function createBackgroundJobSession(
  api: Pick<PluginUIBridge, 'storage' | 'jobs'>,
  publish: (state: BackgroundJobState) => void,
  newInvocation = () => `inv_ui_${Array.from(crypto.getRandomValues(new Uint32Array(4)), value => value.toString(16).padStart(8, '0')).join('')}`,
) {
  let job: PluginJob | null = null
  let pending = ''
  let ready = false
  let busy = false
  const emit = () => publish({ job, ready, busy })
  return {
    async restore() {
      if (busy) return
      busy = true
      ready = false
      emit()
      try {
        pending = await api.storage.get<string>('refresh-job-invocation') || ''
        const ref = await api.storage.get<string>('refresh-job-ref')
        job = ref ? await api.jobs.get(ref) : null
        ready = true
      } finally { busy = false; emit() }
    },
    async run(operation: 'start' | 'get' | 'resume' | 'cancel') {
      if (busy || !ready) return
      if (operation === 'start' && ['queued', 'running'].includes(job?.status || '')) return
      busy = true
      emit()
      try {
        if (operation === 'start') {
          pending ||= newInvocation()
          // A previous persistence failure must not leave a memory-only ID.
          await api.storage.set('refresh-job-invocation', pending)
          job = await api.jobs.start('refresh', pending)
          await api.storage.set('refresh-job-ref', job.job_ref)
          await api.storage.remove('refresh-job-invocation')
          pending = ''
        } else if (job) {
          if (operation === 'cancel') await api.jobs.cancel(job.job_ref)
          job = await api.jobs[operation === 'resume' ? 'resume' : 'get'](job.job_ref)
        }
      } finally { busy = false; emit() }
    },
  }
}
