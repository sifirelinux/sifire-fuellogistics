/**
 * S.I.F.I.R.E. FuelLogistics - Cliente WebSocket para chat corporativo.
 * Maneja conexion, reconexion automatica y envio de mensajes.
 */
class ChatWebSocketClient {
  /**
   * @param {string} pedidoId - UUID del pedido
   * @param {string} usuarioId - UUID del usuario (despachador)
   * @param {object} callbacks - { onMessage, onStatusChange }
   */
  constructor(pedidoId, usuarioId, callbacks = {}) {
    this.pedidoId = pedidoId;
    this.usuarioId = usuarioId;
    this.onMessage = callbacks.onMessage || (() => {});
    this.onStatusChange = callbacks.onStatusChange || (() => {});

    this.ws = null;
    this.reconnectAttempts = 0;
    this.reconnectTimer = null;
    this.manualClose = false;
  }

  /**
   * Abre la conexion WebSocket.
   */
  connect() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      return;
    }

    this.manualClose = false;
    const url = `${CONFIG.WS_BASE_URL}${CONFIG.ENDPOINTS.CHAT_WS(this.pedidoId, this.usuarioId)}`;
    console.log('[WS] Conectando a', url);
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
      if (!this.manualClose) {
        this._scheduleReconnect();
      }
    };
  }

  /**
   * Programa una reconexion con backoff exponencial.
   */
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

  /**
   * Envia un mensaje de texto al chat.
   * @param {string} contenido
   */
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

  /**
   * Cierra la conexion sin reconectar.
   */
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

  /**
   * @returns {boolean} true si esta conectado.
   */
  isConnected() {
    return this.ws && this.ws.readyState === WebSocket.OPEN;
  }
}
