// Spendly service worker.
// It does ONE thing: if you open the app while you are offline, it shows a small "you are offline" page.
// It never stores your expenses, budgets or any page you were logged in to.
const CACHE = "spendly-offline-v1";
const OFFLINE_URL = "/offline";

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE).then(cache => cache.add(OFFLINE_URL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", event => {
  if (event.request.mode === "navigate") {
    event.respondWith(fetch(event.request).catch(() => caches.match(OFFLINE_URL)));
  }
  // every other request (data, scripts, images) goes straight to the network
});
