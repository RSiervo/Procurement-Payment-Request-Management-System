// Service worker for the installed app.
//
// The portal always needs the server (requests, approvals and files are live data), so
// nothing from the API is ever cached. The worker exists so browsers offer "Install",
// and so an installed app shows a clear message instead of a browser error when the
// server cannot be reached.

const OFFLINE = `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Procurement &amp; Payment Portal</title>
<style>
  body{margin:0;min-height:100vh;display:grid;place-items:center;font-family:system-ui,Segoe UI,Arial,sans-serif;background:#f4f6fb;color:#1b2540}
  main{max-width:340px;padding:24px;text-align:center}
  img{width:64px;height:64px}
  h1{font-size:18px;margin:16px 0 6px}
  p{font-size:14px;line-height:1.5;color:#5b6784;margin:0 0 18px}
  button{font:inherit;font-weight:600;padding:9px 18px;border:0;border-radius:8px;background:#2160e0;color:#fff;cursor:pointer}
</style></head><body><main>
  <img src="/icon-192.png" alt="">
  <h1>Cannot reach the portal</h1>
  <p>Check that you are connected to the office network, then try again.</p>
  <button onclick="location.reload()">Try again</button>
</main></body></html>`

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open('ppms-shell-v1').then((cache) => cache.add('/icon-192.png')).then(() => self.skipWaiting()))
})

self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()))

self.addEventListener('fetch', (event) => {
  const request = event.request
  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).catch(() => new Response(OFFLINE, { headers: { 'Content-Type': 'text/html; charset=utf-8' } })))
  } else if (new URL(request.url).pathname === '/icon-192.png') {
    event.respondWith(fetch(request).catch(() => caches.match(request)))
  }
  // Everything else goes straight to the network, untouched.
})
