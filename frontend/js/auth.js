/**
 * S.I.F.I.R.E. FuelLogistics - Gestion de autenticacion JWT.
 * Maneja login, logout, token en localStorage y wrapper de fetch.
 */
const AuthManager = {
  TOKEN_KEY: 'sifire_token',
  USUARIO_KEY: 'sifire_usuario',

  // ─── Token ────────────────────────────────────────────────
  getToken() {
    return localStorage.getItem(this.TOKEN_KEY);
  },

  setToken(token) {
    localStorage.setItem(this.TOKEN_KEY, token);
  },

  getUsuario() {
    const raw = localStorage.getItem(this.USUARIO_KEY);
    if (!raw) return null;
    try { return JSON.parse(raw); } catch { return null; }
  },

  setUsuario(usuario) {
    localStorage.setItem(this.USUARIO_KEY, JSON.stringify(usuario));
  },

  estaAutenticado() {
    return !!this.getToken();
  },

  logout() {
    localStorage.removeItem(this.TOKEN_KEY);
    localStorage.removeItem(this.USUARIO_KEY);
  },

  // ─── Login ────────────────────────────────────────────────
  async login(email, password, apiBase) {
    const res = await fetch(`${apiBase}/api/v1/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
      throw new Error(err.detail || 'Error de autenticacion');
    }

    const data = await res.json();
    this.setToken(data.access_token);
    this.setUsuario(data.usuario);
    return data.usuario;
  },

  // ─── Fetch autenticado ────────────────────────────────────
  async fetchAuth(url, options = {}) {
    const token = this.getToken();
    const headers = {
      ...(options.headers || {}),
      'Authorization': `Bearer ${token}`,
    };

    const res = await fetch(url, { ...options, headers });

    if (res.status === 401) {
      console.warn('[Auth] Token expirado o invalido. Cerrando sesion...');
      this.logout();
      window.location.reload();
      throw new Error('Sesion expirada');
    }

    return res;
  },

  // ─── URL del WebSocket con token ──────────────────────────
  getWsUrl(baseUrl, pedidoId, usuarioId) {
    const token = this.getToken();
    return `${baseUrl}/ws/chat/${pedidoId}/${usuarioId}?token=${token}`;
  },
};
