/**
 * S.I.F.I.R.E. FuelLogistics - App del Conductor
 * Login JWT + PIN como segunda capa + GPS + Chat
 */
function conductorApp() {
  return {
    // ─── Configuracion ─────────────────────────────────────
    apiBase: 'https://sifire-fuellogistics.onrender.com',
    wsBase: 'wss://sifire-fuellogistics.onrender.com',

    // ─── Autenticacion JWT ────────────────────────────────
    autenticado: false,
    cargandoLogin: false,
    errorLogin: null,
    formLogin: {
      email: 'conductor@sifire.com',
      password: 'conductor123',
    },
    usuarioActual: null,
    token: null,
    usuarioId: null,
    dispositivoId: null,

    // ─── PIN (segunda capa) ────────────────────────────────
    pinDesbloqueado: false,
    pinIngresado: '',
    pinCorrecto: '1234',
    pinDuress: '9999',
    esModoDuress: false,

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

      // Restaurar sesion
      this.token = localStorage.getItem('sifire_conductor_token');
      const usuarioRaw = localStorage.getItem('sifire_conductor_usuario');

      if (this.token && usuarioRaw) {
        try {
          this.usuarioActual = JSON.parse(usuarioRaw);
          this.usuarioId = this.usuarioActual.id;
          this.autenticado = true;
          console.log('[App] Sesion restaurada:', this.usuarioActual.email);
        } catch (e) {
          console.warn('[App] Error al parsear usuario:', e);
          this.autenticado = false;
        }
      }

      // Restaurar estado del dispositivo
      this.dispositivoId = localStorage.getItem('sifire_conductor_dispositivo');
      if (!this.dispositivoId) {
        this.dispositivoId = 'mobile-' + this.generarUUID().slice(0, 8);
        localStorage.setItem('sifire_conductor_dispositivo', this.dispositivoId);
      }

      // Estado de conexion
      this.estadoConexion = navigator.onLine ? 'ONLINE' : 'OFFLINE';
      this.puntosPendientesSync = this.getQueueCount();

      // Restaurar pedido activo (solo si hay token valido)
      const savedPedido = localStorage.getItem('sifire_conductor_pedido');
      if (savedPedido && this.autenticado && this.token) {
        this.pedidoActivoId = savedPedido;
        await this.cargarPedido();
      }

      // Listeners
      window.addEventListener('online', () => {
        this.estadoConexion = 'ONLINE';
      });
      window.addEventListener('offline', () => {
        this.estadoConexion = 'OFFLINE';
      });

      setInterval(() => {
        this.puntosPendientesSync = this.getQueueCount();
      }, 5000);

      // Service Worker
      if ('serviceWorker' in navigator) {
        try {
          await navigator.serviceWorker.register('./sw.js');
          console.log('[App] Service Worker registrado');
        } catch (e) {
          console.warn('[App] Service Worker fallo:', e);
        }
      }

      // Reconectar WS al recuperar foco
      document.addEventListener('visibilitychange', () => {
        if (!document.hidden && this.pedidoActivoId && this.wsCliente) {
          this.conectarWebSocket(this.pedidoActivoId);
        }
      });
    },

    generarUUID() {
      if (typeof crypto !== 'undefined' && crypto.randomUUID) {
        try { return crypto.randomUUID(); } catch (e) {}
      }
      return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
        const r = (Math.random() * 16) | 0;
        const v = c === 'x' ? r : (r & 0x3) | 0x8;
        return v.toString(16);
      });
    },

    // ─── Login JWT ─────────────────────────────────────────
    async hacerLogin() {
      this.cargandoLogin = true;
      this.errorLogin = null;

      try {
        const res = await fetch(`${this.apiBase}/api/v1/auth/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.formLogin),
        });

        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
          throw new Error(err.detail || 'Error de autenticacion');
        }

        const data = await res.json();

        // Verificar que sea CONDUCTOR
        if (data.usuario.rol !== 'CONDUCTOR') {
          throw new Error(`Esta app es solo para conductores. Tu rol es ${data.usuario.rol}`);
        }

        this.token = data.access_token;
        this.usuarioActual = data.usuario;
        this.usuarioId = data.usuario.id;
        this.autenticado = true;

        localStorage.setItem('sifire_conductor_token', this.token);
        localStorage.setItem('sifire_conductor_usuario', JSON.stringify(this.usuarioActual));

        console.log('[App] Login OK:', this.usuarioActual.email);

      } catch (err) {
        console.error('[App] Error de login:', err);
        this.errorLogin = err.message || 'Error desconocido';
      } finally {
        this.cargandoLogin = false;
      }
    },

    bloquearApp() {
      // Detener tracking si esta activo
      if (this.trackingActivo) {
        this.detenerTracking();
      }

      // Desconectar WS
      if (this.wsCliente) {
        this.wsCliente.disconnect();
        this.wsCliente = null;
      }

      // Volver a la pantalla de PIN
      this.pinDesbloqueado = false;
      this.pinIngresado = '';
      this.esModoDuress = false;
      this.tabActiva = 'dashboard';

      console.log('[App] App bloqueada. Se requiere PIN.');
    },

    hacerLogout() {
      if (!confirm('¿Cerrar sesión?')) return;

      localStorage.removeItem('sifire_conductor_token');
      localStorage.removeItem('sifire_conductor_usuario');
      localStorage.removeItem('sifire_conductor_pedido');
      this.autenticado = false;
      this.pinDesbloqueado = false;
      this.pinIngresado = '';
      this.esModoDuress = false;
      this.pedidoActivo = null;
      this.pedidoActivoId = null;
      window.location.reload();
    },

    // ─── PIN (segunda capa) ────────────────────────────────
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

    limpiarPin() {
      this.pinIngresado = '';
    },

    validarPin() {
      if (this.pinIngresado === this.pinCorrecto) {
        this.pinDesbloqueado = true;
        this.esModoDuress = false;
        console.log('[App] PIN normal. Acceso desbloqueado.');
      } else if (this.pinIngresado === this.pinDuress) {
        this.pinDesbloqueado = true;
        this.esModoDuress = true;
        console.log('[App] PIN duress. Protocolo silencioso activado.');
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
      console.log('[App] PROTOCOLO DURESS ACTIVADO');

      if (this.gpsManager) {
        this.gpsManager.setDuressMode(true);
      }

      if (this.pedidoActivoId) {
        if (!this.wsCliente || this.wsCliente.ws?.readyState !== WebSocket.OPEN) {
          console.log('[App] Conectando WS para enviar alerta...');
          this.conectarWebSocket(this.pedidoActivoId);
          await new Promise((resolve) => {
            let intentos = 0;
            const check = setInterval(() => {
              intentos++;
              if (this.wsCliente && this.wsCliente.ws?.readyState === WebSocket.OPEN) {
                clearInterval(check);
                resolve();
              } else if (intentos > 50) {
                clearInterval(check);
                resolve();
              }
            }, 100);
          });
        }
        await this.enviarAlertaDuress();
      }
    },

    // ─── Pedido activo ─────────────────────────────────────
    async asignarPedido() {
      const uuid = prompt('Ingresa el UUID del pedido:');
      if (!uuid) return;
      if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(uuid)) {
        alert('UUID invalido');
        return;
      }

      // Desconectar WS anterior si existe
      if (this.wsCliente) {
        console.log('[App] Desconectando WS anterior');
        this.wsCliente.disconnect();
        this.wsCliente = null;
        this.mensajesChat = [];
      }

      this.pedidoActivoId = uuid;
      localStorage.setItem('sifire_conductor_pedido', uuid);
      await this.cargarPedido();

      // Reconectar WS al nuevo pedido
      if (this.pedidoActivo && this.usuarioId && this.token) {
        console.log('[App] Reconectando WS al nuevo pedido');
        this.conectarWebSocket(this.pedidoActivoId);
      }
    },

    async cargarPedido() {
      if (!this.pedidoActivoId) return;
      try {
        const res = await fetch(`${this.apiBase}/api/v1/pedidos/${this.pedidoActivoId}`, {
          headers: { 'Authorization': `Bearer ${this.token}` },
        });
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
      localStorage.removeItem('sifire_conductor_pedido');
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

    // ─── Despacho simulado ─────────────────────────────────
    iniciarDespacho(litrosTotales) {
      this.despachoEnCurso = true;
      this.litrosDespachados = 0;
      this.litrosTotales = litrosTotales || 100;
      this.caudalLPorMin = this.esModoDuress ? 2 : 40;
      console.log(`[App] Despacho iniciado. Caudal: ${this.caudalLPorMin} L/min`);

      const segundosPorLitro = 60 / this.caudalLPorMin;
      const totalSegundos = this.litrosTotales * segundosPorLitro;
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
    conectarWebSocket(pedidoId) {
      if (!pedidoId || !this.token || !this.usuarioId) return;
      if (this.wsCliente && this.wsCliente.pedidoId === pedidoId) return;

      if (this.wsCliente) {
        this.wsCliente.disconnect();
        this.wsCliente = null;
      }

      const self = this;
      setTimeout(() => {
        self.wsCliente = new ChatWebSocketClient(
          pedidoId,
          self.usuarioId,
          {
            onMessage: (msg) => self.recibirMensaje(msg),
            onStatusChange: (estado) => { self.wsEstado = estado; },
            getToken: () => self.token,
          }
        );
        self.wsCliente.connect();
      }, 300);
    },

    recibirMensaje(msg) {
      this.mensajesChat.push(msg);
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
        nombre: this.usuarioActual?.nombre_completo || 'Conductor',
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
        this.conectarWebSocket(this.pedidoActivoId);
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

    formatHora(iso) {
      try {
        return new Date(iso).toLocaleTimeString('es-VE', { hour: '2-digit', minute: '2-digit' });
      } catch { return ''; }
    },
  };
}
