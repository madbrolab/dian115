/** DIAN115 v3: a convenience client over ordinary host HTTP APIs. */
export function createPluginContext(id, request, options = {}) {
  const base = `/api/extensions/v3/${encodeURIComponent(id)}`
  const source = { plugin_id: id, generation: options.generation, revision: options.revision }
  const own = (method, suffix, body) => request(method, base + suffix, body, source)
  const api = Object.fromEntries(['get','post','put','patch','delete','head'].map(method => [method, (path, body) => request(method.toUpperCase(), path, body, source)]))
  return {
    id, api,
    storage: { get: async key => (await own('GET', '/storage/' + encodeURIComponent(key))).value,
      set: (key, value, expected_revision) => own('PUT', '/storage/' + encodeURIComponent(key), { value, expected_revision }),
      remove: key => own('DELETE', '/storage/' + encodeURIComponent(key)),
      list: (limit=50, offset=0) => own('GET', `/storage?limit=${limit}&offset=${offset}`) },
    http: { request: options => own('POST', '/http', options), cookies: options => own('POST', '/cookies', options), importCookies: options => own('POST','/cookies/import',options), render: options => own('POST','/render',options) },
    files: { call: options => own('POST', '/files', options), start: options => own('POST', '/files?wait=0', options),
      downloadURL: (path, opts = {}) => (options.baseURL || '') + base + '/files/download?path=' + encodeURIComponent(path) + (opts.inline ? '&inline=1' : ''),
      upload: (path, file) => { const form = new FormData(); form.append('path', path); form.append('file', file); return own('POST', '/files/upload', form) } },
    server: { list: () => own('GET', '/listeners'), listen: options => own('POST', '/listeners', options), close: id => own('DELETE', '/listeners/' + encodeURIComponent(id)),
      hookURL: (path = '') => (options.baseURL || '') + base + '/hook/' + String(path).replace(/^\/+/, ''),
      publicHookURL: (path = '') => (options.baseURL || '') + '/plugin-hooks/' + encodeURIComponent(id) + '/' + String(path).replace(/^\/+/, '') },
    settings: { get: () => own('GET', '/settings'), set: value => own('PUT', '/storage/settings', { value }) },
    events: { catalog: () => request('GET', '/api/extensions/v3/_events', undefined, source) },
    cd2: { call: (method, options) => own('POST', '/cd2/' + encodeURIComponent(method), options) },
    watch: { list: () => own('GET','/watches'), add: options => own('POST','/watches',options), remove: id => own('DELETE','/watches/'+encodeURIComponent(id)) },
    tasks: { run: (job, business_key, input={}) => own('POST','/jobs/'+encodeURIComponent(job),{business_key,input}),
      list: (limit=50,offset=0) => own('GET',`/runs?limit=${limit}&offset=${offset}`),
      get: id => own('GET','/runs/'+encodeURIComponent(id)),
      cancel: id => own('POST','/runs/'+encodeURIComponent(id)+'/cancel'),
      retry: id => own('POST','/runs/'+encodeURIComponent(id)+'/retry') },
    notify: options => own('POST','/notify',options),
    notifications: { send: options => own('POST','/notify',options), channels: () => request('GET', '/api/extensions/v3/_notify/channels', undefined, source) },
    cookiecloud: (operation, options) => own('POST','/cookiecloud/'+encodeURIComponent(operation),options),
    usage: () => own('GET','/usage'),
  }
}
