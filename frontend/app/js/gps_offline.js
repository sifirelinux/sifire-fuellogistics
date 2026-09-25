/**
 * S.I.F.I.R.E. FuelLogistics - Gestor GPS offline-first.
 * Captura posiciones continuamente, las almacena en localStorage cuando
 * no hay conexion, y las sincroniza al backend en lotes.
 */
class GPSManager {
  /**
   * @param {object} opts
   * @param {string} opts.apiBase - URL base de la API
   * @param {string} opts.dispositivoId - ID unico del dispositivo
   * @param {string} opts.pedidoId - UUID del pedido activo
   * @param {function} opts.onPosition - callback con la posicion capturada
   * @param {function} opts.onQueueChange - callback con el numero de pendientes
   * @param {function} opts.onSync - callback tras sincronizar
   */
  constructor(opts) {
    this.apiBase = opts.apiBase;
    this.dispositivoId = opts.dispositivoId;
    this.pedidoId = opts.pedidoId;
    this.onPosition = opts.onPosition || (() => {});
    this.onQueueChange = opts.onQueueChange || (() => {});
    this.onSync = opts.onSync || (() => {});

    this.watchId = null;
    this.syncInterval = null;
    this.esModoDuress = false;

    this.QUEUE_KEY = 'sifire_gps_queue';
    this.QUEUE_MAX = 5000;
    this.BATCH_SIZE = 500;
    this.SYNC_INTERVAL_MS = 30000;

    // Bind handlers
    this._handleOnline = this._handleOnline.bind(this);
    this._handleOffline = this._handleOffline.bind(this);
    this._syncLoop = this._syncLoop.bind(this);
  }

  // ─── Control del tracking ──────────────────────────────────

  start() {
    if (this.watchId !== null) {
      console.warn('[GPS] Tracking ya activo');
      return;
    }

    if (!navigator.geolocation) {
      console.error('[GPS] Geolocation no soportada');
      throw new Error('Geolocation no soportada en este dispositivo');
    }

    console.log('[GPS] Iniciando watchPosition');
    this.watchId = navigator.geolocation.watchPosition(
      (pos) => this._onPosicion(pos),
      (err) => this._onError(err),
      {
        enableHighAccuracy: true,
        maximumAge: 0,
        timeout: 15000,
      }
    );

    // Auto-sync cada 30 segundos
    this.syncInterval = setInterval(this._syncLoop, this.SYNC_INTERVAL_MS);

    // Detectar cambios de conexion
    window.addEventListener('online', this._handleOnline);
    window.addEventListener('offline', this._handleOffline);

    // Actualizar contador inicial
    this._emitQueueCount();
  }

  stop() {
    if (this.watchId !== null) {
      navigator.geolocation.clearWatch(this.watchId);
      this.watchId = null;
      console.log('[GPS] Tracking detenido');
    }

    if (this.syncInterval) {
      clearInterval(this.syncInterval);
      this.syncInterval = null;
    }

    window.removeEventListener('online', this._handleOnline);
    window.removeEventListener('offline', this._handleOffline);
  }

  setDuressMode(active) {
    this.esModoDuress = Boolean(active);
    console.log('[GPS] Modo duress:', this.esModoDuress);
  }

  setPedidoId(pedidoId) {
    this.pedidoId = pedidoId;
  }

  // ─── Handlers de posicion ──────────────────────────────────

  _onPosicion(pos) {
    const coords = pos.coords;

    // Marcar dispositivo con prefijo si es duress
    const dispositivoMarcado = this.esModoDuress
      ? `DURESS-${this.dispositivoId}`
      : this.dispositivoId;

    // Limitar precision_m al maximo permitido por el schema (1000 m)
    let precision = null;
    if (coords.accuracy !== null && coords.accuracy !== undefined) {
      precision = Math.min(coords.accuracy, 1000.0);
    }

    // Limitar velocidad_kmh al maximo (200 km/h)
    let velocidad = null;
    if (coords.speed !== null && coords.speed !== undefined) {
      velocidad = Math.min(coords.speed * 3.6, 200.0);
    }

    // Limitar rumbo_grados a [0, 360)
    let rumbo = null;
    if (coords.heading !== null && coords.heading !== undefined) {
      rumbo = coords.heading % 360;
      if (rumbo < 0) rumbo += 360;
    }

    const punto = {
      latitud: coords.latitude,
      longitud: coords.longitude,
      velocidad_kmh: velocidad,
      rumbo_grados: rumbo,
      precision_m: precision,
      timestamp_gps: new Date(pos.timestamp).toISOString(),
      dispositivo_id: dispositivoMarcado,
    };

    // Callback para la UI
    this.onPosition(punto);

    // Intentar enviar inmediatamente si hay conexion
    if (navigator.onLine) {
      this._enviarPuntoInmediato(punto).catch((err) => {
        console.warn('[GPS] Envio inmediato fallo, encolando:', err.message);
        this._encolarPunto(punto);
      });
    } else {
      this._encolarPunto(punto);
    }
  }

  _onError(err) {
    console.error('[GPS] Error de geolocation:', err.message, 'code:', err.code);
  }

  // ─── Cola FIFO ─────────────────────────────────────────────

  _getQueue() {
    try {
      const raw = localStorage.getItem(this.QUEUE_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  }

  _setQueue(queue) {
    try {
      localStorage.setItem(this.QUEUE_KEY, JSON.stringify(queue));
      this._emitQueueCount();
    } catch (e) {
      console.error('[GPS] Error guardando cola:', e);
    }
  }

  _encolarPunto(punto) {
    const queue = this._getQueue();
    queue.push(punto);

    // Si supera el maximo, descartar los mas antiguos
    if (queue.length > this.QUEUE_MAX) {
      queue.splice(0, queue.length - this.QUEUE_MAX);
    }

    this._setQueue(queue);
  }

  _emitQueueCount() {
    const count = this._getQueue().length;
    this.onQueueChange(count);
  }

  // ─── Sincronizacion ────────────────────────────────────────

  async _enviarPuntoInmediato(punto) {
    if (!this.pedidoId) {
      throw new Error('Sin pedidoId configurado');
    }

    const payload = {
      pedido_id: this.pedidoId,
      lote_id: crypto.randomUUID(),
      es_offline: false,
      dispositivo_id: this.dispositivoId,
      puntos: [punto],
    };

    const token = localStorage.getItem('sifire_conductor_token') || '';
    const res = await fetch(`${this.apiBase}/api/v1/telemetria/sync-batch`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }

    return await res.json();
  }

  async syncBatch() {
    if (!this.pedidoId) {
      console.warn('[GPS] syncBatch sin pedidoId');
      return;
    }

    const queue = this._getQueue();
    if (queue.length === 0) return;

    // Tomar hasta BATCH_SIZE puntos
    const lote = queue.slice(0, this.BATCH_SIZE);

    const payload = {
      pedido_id: this.pedidoId,
      lote_id: crypto.randomUUID(),
      es_offline: true,
      dispositivo_id: this.dispositivoId,
      puntos: lote,
    };

    console.log(`[GPS] Enviando lote de ${lote.length} puntos...`);

    try {
      const token = localStorage.getItem('sifire_conductor_token') || '';
      const res = await fetch(`${this.apiBase}/api/v1/telemetria/sync-batch`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      const resultado = await res.json();
      console.log('[GPS] Sync OK:', resultado);

      // Eliminar los puntos enviados de la cola
      const restantes = queue.slice(lote.length);
      this._setQueue(restantes);

      this.onSync(resultado);
      return resultado;
    } catch (err) {
      console.error('[GPS] Sync fallo, cola conservada:', err.message);
      // NO eliminar la cola en caso de error
      throw err;
    }
  }

  // ─── Eventos de red ────────────────────────────────────────

  async _handleOnline() {
    console.log('[GPS] Conexion recuperada. Sincronizando...');
    try {
      await this.syncBatch();
    } catch (e) {
      console.warn('[GPS] Sync al volver online fallo:', e.message);
    }
  }

  _handleOffline() {
    console.log('[GPS] Conexion perdida. Modo offline.');
  }

  async _syncLoop() {
    if (!navigator.onLine) return;
    const queue = this._getQueue();
    if (queue.length === 0) return;

    try {
      await this.syncBatch();
    } catch (e) {
      // Silencioso en el loop automatico
    }
  }

  // ─── API publica ───────────────────────────────────────────

  getPendientesCount() {
    return this._getQueue().length;
  }

  clearQueue() {
    this._setQueue([]);
  }

  isTracking() {
    return this.watchId !== null;
  }
}
