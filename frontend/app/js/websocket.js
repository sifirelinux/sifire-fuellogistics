/**
 * S.I.F.I.R.E. FuelLogistics - Cliente WebSocket para chat corporativo.
 * Version app del conductor: acepta callback getToken() para JWT.
 */
class ChatWebSocketClient {
  /**
   * @param {string} pedidoId - UUID del pedido
   * @param {string} usuarioId - UUID del usuario (del token)
   * @param {object} callbacks - { onMessage, onStatusChange, getToken }
   */
  constructor(pedidoId, usuarioId, callbacks = {}) {
    this.pedidoId = pedidoId;
    this.usuarioId = usuarioId;
    this.onMessage = callbacks.onMessage || (() => {});
    this.onStatusChange = callbacks.onStatusChange || (() => {});
    this.getToken = callbacks.getToken || (() => localStorage.getItem('sifire_conductor_token') || '');

    this.ws = null;
    this.reconnectAttempts = 0;
    this.reconnectTimer = null;
    this.manualClose = false;

    // Base URL: siempre apuntar a produccion (Render)
    // Esto evita problemas cuando se sirve desde localhost sin Uvicorn activo
    this.wsBase = 'wss://sifire-fuellogistics.onrender.com';
  }

  connect() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      return;
    }

    this.manualClose = false;
    const token = this.getToken();
    const url = `${this.wsBase}/ws/chat/${this.pedidoId}/${this.usuarioId}?token=${token}`;
    console.log('[WS] Conectando a', url.split('?')[0]);
    this.onStatusChange('conectando');

    try {
      this.ws = new WebSocket(url);
    } catch (err) {
      console.error('[WS] Error al crear WebSocket:', err);
      this.onStatusChange('error');
      this._scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      console.log('[WS] Conexion abierta');
      this.reconnectAttempts = 0;
      this.onStatusChange('conectado');
    };

    this.ws.onmessage = (event) => {
      try {
        const mensaje = JSON.parse(event.data);
        this.onMessage(mensaje);
      } catch (err) {
        console.error('[WS] Error al parsear mensaje:', err);
      }
    };

    this.ws.onerror = (err) => {
      console.error('[WS] Error:', err);
      this.onStatusChange('error');
    };

    this.ws.onclose = (event) => {
      console.log('[WS] Conexion cerrada:', event.code, event.reason);
      this.onStatusChange('desconectado');

      // Si el cierre fue por token invalido (1008) o forbidden (4003), no reconectar
      if (event.code === 1008 || event.code === 4003) {
        console.warn('[WS] Cierre por autenticacion. No reconectar.');
        this.manualClose = true;
        return;
      }

      if (!this.manualClose) {
        this._scheduleReconnect();
      }
    };
  }

  _scheduleReconnect() {
    if (this.reconnectTimer) return;

    this.reconnectAttempts += 1;
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts - 1), 30000);
    console.log(`[WS] Reintentando en ${delay}ms (intento ${this.reconnectAttempts})`);
    this.onStatusChange('reconectando');

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }

  send(contenido) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn('[WS] No se puede enviar: socket no conectado');
      return false;
    }

    const payload = {
      tipo: 'TEXTO',
      contenido: contenido.trim(),
    };

    this.ws.send(JSON.stringify(payload));
    return true;
  }

  disconnect() {
    this.manualClose = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.onStatusChange('cerrado');
  }

  isConnected() {
    return this.ws && this.ws.readyState === WebSocket.OPEN;
  }
}
