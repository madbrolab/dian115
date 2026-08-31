/* Runtime cache for the web application shell. API and streaming requests are
 * deliberately left to the network so credentials and live data stay fresh. */
const CACHE_PREFIX = 'dian115-pwa-'
const SHELL_CACHE = `${CACHE_PREFIX}shell-v1`
const STATIC_CACHE = `${CACHE_PREFIX}static-v1`
const FONT_CACHE = `${CACHE_PREFIX}font-v1`
const scopeUrl = new URL('./', self.registration.scope)
const shellUrl = new URL('./index.html', scopeUrl).href

function isCacheableResponse(response) {
  return response && response.ok && (response.type === 'basic' || response.type === 'cors')
}

async function cacheResponse(cacheName, request, response) {
  if (!isCacheableResponse(response)) return response
  const cache = await caches.open(cacheName)
  await cache.put(request, response.clone())
  return response
}

async function cacheShell() {
  const cache = await caches.open(SHELL_CACHE)
  const candidates = [
    scopeUrl.href,
    shellUrl,
    new URL('./manifest.webmanifest', scopeUrl).href,
    new URL('./logo.png', scopeUrl).href,
    new URL('./ico.png', scopeUrl).href,
  ]

  await Promise.all(candidates.map(async url => {
    try {
      const response = await fetch(new Request(url, { cache: 'no-cache' }))
      if (isCacheableResponse(response)) await cache.put(url, response)
    } catch {
      // The page can still be controlled when an optional shell asset is absent.
    }
  }))
}

async function networkFirst(request) {
  try {
    const response = await fetch(request)
    await cacheResponse(SHELL_CACHE, request, response)
    return response
  } catch {
    const cache = await caches.open(SHELL_CACHE)
    return (await cache.match(request)) || (await cache.match(shellUrl)) || Response.error()
  }
}

async function staleWhileRevalidate(request) {
  const cacheName = request.destination === 'font' ? FONT_CACHE : STATIC_CACHE
  const cache = await caches.open(cacheName)
  const cached = await cache.match(request)
  const network = fetch(request)
    .then(response => cacheResponse(cacheName, request, response))
    .catch(() => undefined)

  return cached || (await network) || Response.error()
}

self.addEventListener('install', event => {
  event.waitUntil(cacheShell())
  // Do not interrupt an already running page during an update. The client can
  // explicitly activate a waiting worker after the user confirms the update.
  if (!self.registration.active) self.skipWaiting()
})

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const cacheNames = await caches.keys()
    await Promise.all(cacheNames
      .filter(name => name.startsWith(CACHE_PREFIX) && ![SHELL_CACHE, STATIC_CACHE, FONT_CACHE].includes(name))
      .map(name => caches.delete(name)))
    await self.clients.claim()
  })())
})

self.addEventListener('fetch', event => {
  const request = event.request
  if (request.method !== 'GET' || new URL(request.url).origin !== self.location.origin) return

  if (request.mode === 'navigate') {
    event.respondWith(networkFirst(request))
    return
  }

  if (['script', 'style', 'worker', 'font', 'image'].includes(request.destination)) {
    event.respondWith(staleWhileRevalidate(request))
  }
})

self.addEventListener('message', event => {
  if (event.data?.type === 'SKIP_WAITING') {
    self.skipWaiting()
    return
  }

  if (event.data?.type === 'CLEAR_CACHES') {
    event.waitUntil(caches.keys().then(names => Promise.all(
      names.filter(name => name.startsWith(CACHE_PREFIX)).map(name => caches.delete(name)),
    )))
  }
})
