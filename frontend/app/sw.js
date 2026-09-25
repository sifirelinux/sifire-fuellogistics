/**
 * S.I.F.I.R.E. FuelLogistics - Service Worker v2
 * Cachea los archivos estaticos para funcionamiento offline.
 */
const CACHE_NAME = 'sifire-conductor-v2';  // ← v2 invalida el viejo
const ASSETS = [
  './',
  './index.html',
  './manifest.json',
  './js/app.js',
  './js/gps_offline.js',
  './js/websocket.js',
];

self.addEventListener('install', (event) => {
  console.log('[SW] Instalando v2...');
  // Forzar activacion inmediata
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('[SW] Cacheando assets v2');
      return cache.addAll(ASSETS);
    })
  );
});

self.addEventListener('activate', (event) => {
  console.log('[SW] Activando v2');
  // Eliminar TODOS los caches antiguos
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((k) => k !== CACHE_NAME).map((k) => {
          console.log('[SW] Eliminando cache viejo:', k);
          return caches.delete(k);
        })
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  // Solo cachear peticiones GET al mismo origen
  if (event.request.method !== 'GET') return;
  if (!event.request.url.startsWith(self.location.origin)) return;

  // Estrategia: network-first para el JS y HTML (evita cache viejo)
  if (event.request.url.endsWith('.js') || event.request.url.endsWith('.html')) {
    event.respondWith(
      fetch(event.request).then((response) => {
        const clone = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        return response;
      }).catch(() => caches.match(event.request))
    );
    return;
  }

  // Cache-first para imagenes y otros
  event.respondWith(
    caches.match(event.request).then((cached) => {
      return cached || fetch(event.request).then((response) => {
        return caches.open(CACHE_NAME).then((cache) => {
          cache.put(event.request, response.clone());
          return response;
        });
      });
    })
  );
});
