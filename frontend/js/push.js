/**
 * S.I.F.I.R.E. FuelLogistics - Cliente de notificaciones push.
 * Maneja: registro del SW, suscripcion, permisos.
 */
const PushManagerClient = {
  TOKEN_KEY: 'sifire_token',
  SW_PATH: './sw.js',

  // ─── Estado ──────────────────────────────────────────────
  estaSoportado() {
    return 'serviceWorker' in navigator
      && 'PushManager' in window
      && 'Notification' in window;
  },

  estaSuscrito() {
    return Notification.permission === 'granted' && localStorage.getItem('sifire_push_endpoint') !== null;
  },

  // ─── Registro del SW ─────────────────────────────────────
  async registrarSW() {
    if (!this.estaSoportado()) {
      throw new Error('Notificaciones push no soportadas en este navegador');
    }
    const reg = await navigator.serviceWorker.register(this.SW_PATH);
    console.log('[Push] SW registrado:', reg.scope);
    return reg;
  },

  // ─── Suscripcion ─────────────────────────────────────────
  async obtenerVapidKey(apiBase) {
    const res = await fetch(`${apiBase}/api/v1/push/vapid-public-key`);
    if (!res.ok) throw new Error('No se pudo obtener la clave VAPID');
    const data = await res.json();
    if (!data.enabled || !data.public_key) {
      throw new Error('Notificaciones push no habilitadas en el servidor');
    }
    return data.public_key;
  },

  urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    const rawData = atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) {
      outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
  },

  async suscribirse(apiBase) {
    // 1. Pedir permiso
    const permiso = await Notification.requestPermission();
    if (permiso !== 'granted') {
      throw new Error('Permiso de notificaciones denegado');
    }

    // 2. Registrar SW
    const reg = await this.registrarSW();
    await navigator.serviceWorker.ready;

    // 3. Obtener clave VAPID
    const vapidKey = await this.obtenerVapidKey(apiBase);

    // 4. Suscribirse al push manager
    let sub = await reg.pushManager.getSubscription();
    if (!sub) {
      sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: this.urlBase64ToUint8Array(vapidKey),
      });
    }
    console.log('[Push] Suscripcion obtenida:', sub.endpoint);

    // 5. Enviar al backend
    const token = localStorage.getItem(this.TOKEN_KEY);
    const payload = {
      endpoint: sub.endpoint,
      keys: {
        p256dh: this._arrayBufferToBase64(sub.getKey('p256dh')),
        auth: this._arrayBufferToBase64(sub.getKey('auth')),
      },
      user_agent: navigator.userAgent.slice(0, 255),
    };

    const res = await fetch(`${apiBase}/api/v1/push/subscribe`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
      throw new Error(err.detail || 'Error al registrar suscripcion');
    }

    const resultado = await res.json();
    localStorage.setItem('sifire_push_endpoint', resultado.endpoint);
    console.log('[Push] Suscripcion registrada en el backend');
    return resultado;
  },

  _arrayBufferToBase64(buffer) {
    if (!buffer) return '';
    const bytes = new Uint8Array(buffer);
    let binary = '';
    for (let i = 0; i < bytes.byteLength; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
  },

  // ─── Desuscribirse ───────────────────────────────────────
  async desuscribirse(apiBase) {
    const endpoint = localStorage.getItem('sifire_push_endpoint');
    if (!endpoint) return;

    const token = localStorage.getItem(this.TOKEN_KEY);
    try {
      await fetch(`${apiBase}/api/v1/push/unsubscribe?endpoint=${encodeURIComponent(endpoint)}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` },
      });
    } catch (err) {
      console.warn('[Push] Error al desuscribir:', err);
    }

    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    if (sub) await sub.unsubscribe();

    localStorage.removeItem('sifire_push_endpoint');
    console.log('[Push] Desuscrito');
  },

  // ─── Test ────────────────────────────────────────────────
  async enviarTest(apiBase) {
    const token = localStorage.getItem(this.TOKEN_KEY);
    const res = await fetch(`${apiBase}/api/v1/push/test`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({
        titulo: 'Prueba S.I.F.I.R.E.',
        cuerpo: 'Si ves esto, las notificaciones funcionan!',
        urgente: false,
      }),
    });

    if (!res.ok) throw new Error('Error al enviar test');
    return await res.json();
  },
};
