/**
 * S.I.F.I.R.E. FuelLogistics - App del Conductor
 * Logica principal con Alpine.js.
 */
function conductorApp() {
  return {
    // ─── Configuracion ─────────────────────────────────────
    apiBase: 'https://sifire-fuellogistics.onrender.com',
    wsBase: 'wss://sifire-fuellogistics.onrender.com',
    usuarioId: crypto.randomUUID(),
    dispositivoId: 'mobile-' + crypto.randomUUID().slice(0, 8),

    // ─── Estado del pedido ─────────────────────────────────
    pedidoActivoId: null,
    pedidoActivo: null,

    // ─── Tracking GPS ──────────────────────────────────────
    trackingActivo: false,
    gpsManager: null,
    ultimaPosicion: {
      lat: null,
      lon: null,
      velocidad: null,
      precision: null,
      timestamp: null,
    },
    puntosPendientesSync: 0,
    totalPuntosEnviados: 0,

    // ─── Estado de conexion ────────────────────────────────
    estadoConexion: 'ONLINE',

    // ─── Autenticacion PIN ─────────────────────────────────
    autenticado: false,
    pinIngresado: '',
    pinCorrecto: '1234',
    pinDuress: '9999',
    esModoDuress: false,

    // ─── UI ────────────────────────────────────────────────
    tabActiva: 'dashboard',
    mensajesChat: [],
    nuevoMensaje: '',
    wsCliente: null,
    wsEstado: 'cerrado',

    // ─── Despacho simulado ─────────────────────────────────
    despachoEnCurso: false,
    litrosDespachados: 0,
    litrosTotales: 0,
    caudalLPorMin: 0,

    // ─── Inicializacion ────────────────────────────────────
    async init() {
      console.log('[App] Iniciando app del conductor');

      // Restaurar estado
      this.estadoConexion = navigator.onLine ? 'ONLINE' : 'OFFLINE';
      this.puntosPendientesSync = this.getQueueCount();

      // Restaurar pedido activo
      const savedPedido = localStorage.getItem('sifire_pedido_activo');
      if (savedPedido) {
        this.pedidoActivoId = savedPedido;
        await this.cargarPedido();
      }

      // Listeners de conexion
      window.addEventListener('online', () => {
        this.estadoConexion = 'ONLINE';
        console.log('[App] Conexion recuperada');
      });
      window.addEventListener('offline', () => {
        this.estadoConexion = 'OFFLINE';
        console.log('[App] Conexion perdida');
      });

      // Refrescar contador cada 5 segundos
      setInterval(() => {
        this.puntosPendientesSync = this.getQueueCount();
      }, 5000);

      // Registrar Service Worker
      if ('serviceWorker' in navigator) {
        try {
          await navigator.serviceWorker.register('./sw.js');
          console.log('[App] Service Worker registrado');
        } catch (e) {
          console.warn('[App] Service Worker fallo:', e);
        }
      }

      // Reconectar WS al recuperar foco de la pestana
      document.addEventListener('visibilitychange', () => {
        if (!document.hidden && this.pedidoActivoId) {
          console.log('[App] Volviendo al foco, reconectando WS');
          this.conectarWebSocket(this.pedidoActivoId);
        }
      });
    },

    // ─── Pedido activo ─────────────────────────────────────
    async asignarPedido() {
      const uuid = prompt('Ingresa el UUID del pedido:');
      if (!uuid) return;
      if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(uuid)) {
        alert('UUID invalido');
        return;
      }
      this.pedidoActivoId = uuid;
      localStorage.setItem('sifire_pedido_activo', uuid);
      await this.cargarPedido();
    },

    async cargarPedido() {
      if (!this.pedidoActivoId) return;
      try {
        const res = await fetch(`${this.apiBase}/api/v1/pedidos/${this.pedidoActivoId}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        this.pedidoActivo = await res.json();
        console.log('[App] Pedido cargado:', this.pedidoActivo.codigo);
      } catch (e) {
        console.error('[App] Error cargando pedido:', e);
        this.pedidoActivo = null;
      }
    },

    cerrarPedido() {
      if (!confirm('¿Desasignar el pedido actual?')) return;
      this.pedidoActivoId = null;
      this.pedidoActivo = null;
      localStorage.removeItem('sifire_pedido_activo');
      if (this.trackingActivo) this.detenerTracking();
    },

    // ─── Tracking GPS ──────────────────────────────────────
    iniciarTracking() {
      if (!this.pedidoActivoId) {
        alert('Primero asigna un pedido');
        return;
      }
      if (this.trackingActivo) return;

      const self = this;
      this.gpsManager = new GPSManager({
        apiBase: this.apiBase,
        dispositivoId: this.dispositivoId,
        pedidoId: this.pedidoActivoId,
        onPosition: (punto) => self.onNuevaPosicion(punto),
        onQueueChange: (count) => { self.puntosPendientesSync = count; },
        onSync: (resultado) => {
          self.totalPuntosEnviados += resultado.almacenados || 0;
          console.log('[App] Sync completado:', resultado);
        },
      });

      this.gpsManager.setDuressMode(this.esModoDuress);
      this.gpsManager.start();
      this.trackingActivo = true;
      console.log('[App] Tracking iniciado');
    },

    detenerTracking() {
      if (this.gpsManager) {
        this.gpsManager.stop();
        this.gpsManager = null;
      }
      this.trackingActivo = false;
      console.log('[App] Tracking detenido');
    },

    onNuevaPosicion(punto) {
      this.ultimaPosicion = {
        lat: punto.latitud,
        lon: punto.longitud,
        velocidad: punto.velocidad_kmh,
        precision: punto.precision_m,
        timestamp: punto.timestamp_gps,
      };
    },

    getQueueCount() {
      try {
        const raw = localStorage.getItem('sifire_gps_queue');
        return raw ? JSON.parse(raw).length : 0;
      } catch {
        return 0;
      }
    },

    async sincronizarManual() {
      if (!this.gpsManager) {
        alert('Tracking no activo');
        return;
      }
      try {
        this.estadoConexion = 'SINCRONIZANDO';
        await this.gpsManager.syncBatch();
        this.estadoConexion = 'ONLINE';
      } catch (e) {
        this.estadoConexion = 'ONLINE';
        alert('Sync fallo: ' + e.message);
      }
    },

    // ─── PIN / Autenticacion ───────────────────────────────
    ingresarPin(digito) {
      if (this.pinIngresado.length >= 4) return;
      this.pinIngresado += String(digito);

      if (this.pinIngresado.length === 4) {
        setTimeout(() => this.validarPin(), 200);
      }
    },

    borrarPin() {
      this.pinIngresado = this.pinIngresado.slice(0, -1);
    },

    validarPin() {
      if (this.pinIngresado === this.pinCorrecto) {
        this.autenticado = true;
        this.esModoDuress = false;
        console.log('[App] Autenticado (normal)');
      } else if (this.pinIngresado === this.pinDuress) {
        this.autenticado = true;
        this.esModoDuress = true;
        console.log('[App] Autenticado (modo silencioso)');
        this.activarProtocoloDuress();
      } else {
        console.log('[App] PIN incorrecto');
        this.pinIngresado = '';
        return;
      }
      this.pinIngresado = '';
      this.tabActiva = 'dashboard';
    },

    async activarProtocoloDuress() {
      console.log('[App] ⚠ PROTOCOLO DURESS ACTIVADO');

      // Marcar el GPS en modo duress
      if (this.gpsManager) {
        this.gpsManager.setDuressMode(true);
      }

      // Enviar alerta por chat WebSocket
      await this.enviarAlertaDuress();
    },

    // ─── Despacho simulado ─────────────────────────────────
    iniciarDespacho(litrosTotales) {
      this.despachoEnCurso = true;
      this.litrosDespachados = 0;
      this.litrosTotales = litrosTotales || 100;
      this.caudalLPorMin = this.esModoDuress ? 2 : 40;
      console.log(`[App] Despacho iniciado. Caudal: ${this.caudalLPorMin} L/min`);

      const segundosPorLitro = 60 / this.caudalLPorMin;
      const totalSegundos = this.litrosTotales * segundosPorLitro;

      // Simular progreso
      const inicio = Date.now();
      const interval = setInterval(() => {
        const elapsed = (Date.now() - inicio) / 1000;
        const progreso = Math.min(elapsed / totalSegundos, 1);
        this.litrosDespachados = (this.litrosTotales * progreso).toFixed(2);

        if (progreso >= 1) {
          clearInterval(interval);
          this.despachoEnCurso = false;
          console.log('[App] Despacho completado');
        }
      }, 1000);
    },

    // ─── Chat WebSocket ────────────────────────────────────
    conectarWebSocket() {
      if (!this.pedidoActivoId) return;
      if (this.wsCliente && this.wsCliente.pedidoId === this.pedidoActivoId) return;

      if (this.wsCliente) {
        this.wsCliente.disconnect();
        this.wsCliente = null;
      }

      const self = this;
      setTimeout(() => {
        self.wsCliente = new ChatWebSocketClient(this.pedidoActivoId, this.usuarioId, {
          onMessage: (msg) => self.recibirMensaje(msg),
          onStatusChange: (estado) => { self.wsEstado = estado; },
        });
        self.wsCliente.connect();
      }, 300);
    },

    recibirMensaje(msg) {
      this.mensajesChat.push(msg);
      // Scroll al final
      this.$nextTick(() => {
        const el = document.getElementById('chat-scroll');
        if (el) el.scrollTop = el.scrollHeight;
      });
    },

    enviarMensaje() {
      if (!this.nuevoMensaje.trim() || !this.wsCliente) return;
      const payload = {
        tipo: 'TEXTO',
        contenido: this.nuevoMensaje,
        nombre: 'Conductor',
      };
      if (this.wsCliente.ws && this.wsCliente.ws.readyState === WebSocket.OPEN) {
        this.wsCliente.ws.send(JSON.stringify(payload));
      }
      this.nuevoMensaje = '';
    },

    async enviarAlertaDuress() {
      if (!this.wsCliente || !this.wsCliente.ws) return;
      if (this.wsCliente.ws.readyState !== WebSocket.OPEN) return;

      const payload = {
        tipo: 'ALERTA',
        contenido: 'PANIC_SIGNAL',
        nombre: 'SYSTEM',
      };
      this.wsCliente.ws.send(JSON.stringify(payload));
      console.log('[App] Alerta duress enviada');
    },

    // ─── Tabs ──────────────────────────────────────────────
    setTab(tab) {
      this.tabActiva = tab;
      if (tab === 'chat' && this.pedidoActivoId && !this.wsCliente) {
        this.conectarWebSocket();
      }
    },

    // ─── Helpers ───────────────────────────────────────────
    getColorConexion() {
      switch (this.estadoConexion) {
        case 'ONLINE': return 'bg-green-500';
        case 'OFFLINE': return 'bg-red-500';
        case 'SINCRONIZANDO': return 'bg-yellow-500';
        default: return 'bg-slate-500';
      }
    },

    getEstadoAutenticacion() {
      if (!this.autenticado) return 'BLOQUEADO';
      return this.esModoDuress ? 'AUTENTICADO' : 'AUTENTICADO';
    },

    formatHora(iso) {
      try {
        return new Date(iso).toLocaleTimeString('es-VE', { hour: '2-digit', minute: '2-digit' });
      } catch { return ''; }
    },
  };
}
