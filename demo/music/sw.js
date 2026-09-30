/* The music player owns this namespace only. Never cache account, lyrics,
 * cover-art, download, or streaming responses containing Subsonic credentials. */
const MUSIC_BUILD = 'development'
const MUSIC_PRECACHE = ['/music/', '/music/offline.html', '/music/manifest.webmanifest', '/music/icon.svg', '/music/icon-192.png', '/music/icon-512.png', '/music/apple-touch-icon.png']
const MUSIC_CACHE_PREFIX = 'dian115-music-shell-'
const MUSIC_CACHE = MUSIC_CACHE_PREFIX + MUSIC_BUILD
const allowedPaths = new Set(MUSIC_PRECACHE)

self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(MUSIC_CACHE)
    await cache.addAll(MUSIC_PRECACHE.map(url => new Request(url, { cache: 'reload', credentials: 'omit' })))
    if (!self.registration.active) await self.skipWaiting()
  })())
})
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const names = await caches.keys()
    await Promise.all(names.filter(name => name.startsWith(MUSIC_CACHE_PREFIX) && name !== MUSIC_CACHE).map(name => caches.delete(name)))
    await self.clients.claim()
  })())
})
self.addEventListener('fetch', event => {
  const { request } = event
  const url = new URL(request.url)
  if (request.method !== 'GET' || url.origin !== self.location.origin || request.headers.has('authorization') || request.headers.has('range') || url.search || url.username || url.password) return
  if (request.mode === 'navigate' && url.pathname.startsWith('/music/')) {
    event.respondWith((async () => {
      try {
        const response = await fetch(request)
        if (response.ok) return response
      } catch { /* Fall back to this build's complete shell. */ }
      const cache = await caches.open(MUSIC_CACHE)
      return await cache.match('/music/') || await cache.match('/music/offline.html') || Response.error()
    })())
    return
  }
  if (!allowedPaths.has(url.pathname)) return
  event.respondWith((async () => {
    const cache = await caches.open(MUSIC_CACHE)
    return await cache.match(request) || fetch(request)
  })())
})
self.addEventListener('message', event => {
  if (event.data?.type === 'MUSIC_SKIP_WAITING') self.skipWaiting()
})
