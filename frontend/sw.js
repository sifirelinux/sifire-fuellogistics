/**
 * S.I.F.I.R.E. FuelLogistics - Service Worker del panel.
 * Maneja: cache offline + notificaciones push.
 */
const CACHE_NAME = 'sifire-panel-v2';
const ASSETS = [
  './',
  './index.html',
  './manifest.json',
  './js/config.js',
  './js/auth.js',
  './js/push.js',
  './js/websocket.js',
];

// ─── Install ──────────────────────────────────────────────────────
self.addEventListener('install', (event) => {
  console.log('[SW] Instalando v2');
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS)).catch(() => {})
  );
});

// ─── Activate ─────────────────────────────────────────────────────
self.addEventListener('activate', (event) => {
  console.log('[SW] Activando v2');
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// ─── Fetch (network-first para HTML/JS) ───────────────────────────
self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  if (!event.request.url.startsWith(self.location.origin)) return;

  const url = event.request.url;
  if (url.endsWith('.js') || url.endsWith('.html') || url.endsWith('/')) {
    event.respondWith(
      fetch(event.request)
        .then((res) => {
          const clone = res.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          return res;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cached) => {
      return cached || fetch(event.request).then((res) => {
        return caches.open(CACHE_NAME).then((cache) => {
          cache.put(event.request, res.clone());
          return res;
        });
      });
    })
  );
});

// ─── PUSH: recibir notificacion ───────────────────────────────────
self.addEventListener('push', (event) => {
  console.log('[SW] Push recibido');

  let data = {
    title: 'S.I.F.I.R.E. FuelLogistics',
    body: 'Nueva notificacion',
    url: '/sifire/',
    tag: 'sifire-default',
    urgente: false,
  };

  if (event.data) {
    try {
      data = { ...data, ...event.data.json() };
    } catch (err) {
      data.body = event.data.text();
    }
  }

  const options = {
    body: data.body,
    icon: '/sifire/img/icon-192.png',
    badge: '/sifire/img/badge-72.png',
    tag: data.tag || 'sifire',
    requireInteraction: data.urgente === true,
    vibrate: data.urgente ? [200, 100, 200, 100, 200] : [100],
    data: { url: data.url || '/sifire/' },
    actions: data.urgente
      ? [{ action: 'open', title: 'Abrir' }, { action: 'close', title: 'Cerrar' }]
      : [{ action: 'open', title: 'Ver' }],
  };

  event.waitUntil(self.registration.showNotification(data.title, options));
});

// ─── NOTIFICATION CLICK: abrir la app ─────────────────────────────
self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  const url = (event.notification.data && event.notification.data.url) || '/sifire/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if (client.url.includes('/sifire/') && 'focus' in client) {
          client.navigate(url);
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(url);
      }
    })
  );
});

// ─── PUSH SUBSCRIPTION CHANGE: renovar suscripcion ────────────────
self.addEventListener('pushsubscriptionchange', (event) => {
  console.log('[SW] Suscripcion push cambio');
  event.waitUntil(
    self.registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: event.oldSubscription?.options?.applicationServerKey,
    }).then((newSub) => {
      return fetch('/api/v1/push/subscribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newSub),
      });
    }).catch((err) => console.error('[SW] Error renovando:', err))
  );
});
