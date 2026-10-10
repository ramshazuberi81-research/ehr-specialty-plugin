// Caches ONLY the empty app shell so it opens like an installed app.
// Patient data (/ask, /previsit, /nlp/*) is never cached: those requests always go to the network.
const SHELL = "ask-shell-v1";
const FILES = ["/ask-page", "/manifest.webmanifest", "/icon-192.png", "/icon-512.png"];
self.addEventListener("install", e => e.waitUntil(caches.open(SHELL).then(c => c.addAll(FILES))));
self.addEventListener("activate", e => e.waitUntil(
  caches.keys().then(ks => Promise.all(ks.filter(k => k !== SHELL).map(k => caches.delete(k))))));
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || !FILES.includes(url.pathname)) return;   // everything else: network only
  e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
});
