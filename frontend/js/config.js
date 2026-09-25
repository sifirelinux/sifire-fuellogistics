/**
 * S.I.F.I.R.E. FuelLogistics - Configuracion global del frontend.
 * Todos los valores se pueden sobreescribir sin tocar el resto del codigo.
 */
const CONFIG = Object.freeze({
  // URL de la API en produccion (Render)
  API_BASE_URL: 'https://sifire-fuellogistics.onrender.com',

  // URL del WebSocket (mismo host, protocolo wss)
  WS_BASE_URL: 'wss://sifire-fuellogistics.onrender.com',

  // Centro inicial del mapa: Caracas, Venezuela
  DEFAULT_CENTER: [10.4806, -66.9036],
  DEFAULT_ZOOM: 13,

  // Intervalo de polling para refrescar lista de pedidos (ms)
  POLL_INTERVAL_MS: 10000,

  // Endpoints especificos (para no hardcodear strings en varios archivos)
  ENDPOINTS: {
    PEDIDOS: '/api/v1/pedidos',
    PEDIDO_DETALLE: (id) => `/api/v1/pedidos/${id}`,
    TELEMETRIA: (id) => `/api/v1/telemetria/${id}`,
    CHAT_WS: (pedidoId, usuarioId) => `/ws/chat/${pedidoId}/${usuarioId}`,
    HEALTH: '/health',
  },

  // ID unico del despachador (sesion actual del navegador)
  // Se regenera cada vez que se recarga la pagina
  USUARIO_ID: crypto.randomUUID(),

  // Nombre visible del despachador (siempre el mismo en el chat)
  NOMBRE_DESPACHADOR: 'Despachador Central',

  // Colores por estado de pedido (para badges)
  ESTADO_COLORES: {
    SOLICITADO:    { bg: 'bg-blue-500/20',   text: 'text-blue-300',   border: 'border-blue-500' },
    EN_TRANSITO:   { bg: 'bg-yellow-500/20', text: 'text-yellow-300', border: 'border-yellow-500' },
    DESPACHANDO:   { bg: 'bg-purple-500/20', text: 'text-purple-300', border: 'border-purple-500' },
    COMPLETADO:    { bg: 'bg-green-500/20',  text: 'text-green-300',  border: 'border-green-500' },
    ALERTA_MERMA:  { bg: 'bg-red-500/20',    text: 'text-red-300',    border: 'border-red-500', pulsante: true },
    CANCELADO:     { bg: 'bg-gray-500/20',   text: 'text-gray-400',   border: 'border-gray-500' },
  },
});

// Congela el objeto para evitar modificaciones accidentales
Object.freeze(CONFIG.ENDPOINTS);
Object.freeze(CONFIG.ESTADO_COLORES);
