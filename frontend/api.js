/**
 * API Service Layer
 * Centralized backend communication with error handling and response normalization
 */

class APIService {
  constructor() {
    this.baseURL = this.determineBaseURL();
    this.timeout = 120000;
  }

  determineBaseURL() {
    if (window.location.protocol === 'file:') return 'http://localhost:5000';
    if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
      return window.location.port === '5000' ? '' : 'http://localhost:5000';
    }
    return '';
  }

  async request(endpoint, options = {}) {
    const url = `${this.baseURL}${endpoint}`;
    const defaultOptions = {
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      signal: AbortSignal.timeout(this.timeout),
    };
    const merged = { ...defaultOptions, ...options };
    try {
      const response = await fetch(url, merged);
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new APIError(data.error || `HTTP ${response.status}: ${response.statusText}`, response.status);
      }
      return await response.json();
    } catch (error) {
      if (error.name === 'AbortError') throw new APIError('Request timeout. Please try again.', 408);
      if (error instanceof APIError) throw error;
      throw new APIError(error.message || 'Network error occurred', 0);
    }
  }

  // ── Auth ────────────────────────────────────────────────────────────
  async checkHealth() {
    return await this.request('/api/graph-bounds');
  }

  async signup(payload) {
    return await this.request('/api/auth/signup', { method: 'POST', body: JSON.stringify(payload) });
  }

  async login(identifier, password) {
    return await this.request('/api/auth/login', { method: 'POST', body: JSON.stringify({ identifier, password }) });
  }

  async adminLogin(identifier, password) {
    return await this.request('/api/admin/login', { method: 'POST', body: JSON.stringify({ identifier, password }) });
  }

  async logout() {
    return await this.request('/api/auth/logout', { method: 'POST' });
  }

  async getMe() {
    return await this.request('/api/auth/me');
  }

  // ── Geocode ─────────────────────────────────────────────────────────
  async geocode(query) {
    if (!query || query.trim().length < 3) throw new APIError('Query too short.', 400);
    return await this.request(`/api/geocode?q=${encodeURIComponent(query)}`);
  }

  // ── Traffic ─────────────────────────────────────────────────────────
  async getCongestion() {
    return await this.request('/api/congestion');
  }

  async updateTrafficMode(mode) {
    return await this.request('/api/traffic-mode', { method: 'POST', body: JSON.stringify({ mode }) });
  }

  // ── Multi-Route Calculation (NEW) ───────────────────────────────────
  async calculateRoutes(params) {
    const required = ['source_lat', 'source_lon', 'target_lat', 'target_lon'];
    for (const f of required) {
      if (params[f] === undefined || params[f] === null) throw new APIError(`Missing: ${f}`, 400);
    }
    const response = await this.request('/api/routes/calculate', {
      method: 'POST',
      body: JSON.stringify(params),
    });
    return {
      ...response,
      routes: (response.routes || []).map(route => ({
        ...route,
        path_coords: route.path_coords || [],
        weighted_edges: route.weighted_edges || [],
      })),
    };
  }

  async selectRoute(routeId, requestId) {
    return await this.request('/api/routes/select', {
      method: 'POST',
      body: JSON.stringify({ route_id: routeId, request_id: requestId }),
    });
  }

  // ── Route History ───────────────────────────────────────────────────
  async getRouteHistory() {
    return await this.request('/api/routes/history');
  }

  // ── User Profile ────────────────────────────────────────────────────
  async getUserProfile() {
    return await this.request('/api/user/profile');
  }

  // ── Benchmark ───────────────────────────────────────────────────────
  async benchmarkRoutes(params) {
    return await this.request('/api/benchmark', { method: 'POST', body: JSON.stringify(params) });
  }

  normalizeBenchmarkData(response) {
    return {
      algorithms: (response.algorithms || []).map(r => ({ ...r, path_coords: r.path_coords || [] })),
      recommended_algorithm: response.recommended_algorithm,
      worst_algorithm: response.worst_algorithm,
      best_travel_time: response.best_travel_time,
      scoring: response.scoring,
      benchmark_mode: response.benchmark_mode,
    };
  }

  // ── Legacy Optimize ─────────────────────────────────────────────────
  async optimizeRoute(params) {
    return await this.request('/api/optimize', { method: 'POST', body: JSON.stringify(params) });
  }

  normalizeRouteData(response) {
    const normalized = {
      source: response.source_coords,
      target: response.target_coords,
      emergency_mode: response.emergency_mode || false,
      routes: {},
      comparisons: {},
      experiment: response.experiment || {},
    };
    if (response.dijkstra && !response.dijkstra.error) {
      normalized.routes.dijkstra = { algorithm: 'Dijkstra', ...response.dijkstra };
    }
    if (response.astar && !response.astar.error) {
      normalized.routes.astar = { algorithm: 'A*', ...response.astar };
    }
    const qr = response.qpso || response.qiga;
    if (qr && !qr.error) {
      normalized.routes.qiga = { algorithm: qr.algorithm || 'QPSO', ...qr };
    }
    if (normalized.routes.dijkstra && normalized.routes.qiga) {
      normalized.comparisons = {
        improvement_vs_dijkstra_pct: response.improvement_vs_dijkstra_pct || 0,
        time_saved_min: response.time_saved_min || 0,
      };
    }
    return normalized;
  }

  // ── Fleet & VRP ─────────────────────────────────────────────────────
  async optimizeFleet(params) {
    return await this.request('/api/fleet-optimize', { method: 'POST', body: JSON.stringify(params) });
  }

  async optimizeVrp(params) {
    return await this.request('/api/vrp-optimize', { method: 'POST', body: JSON.stringify(params) });
  }

  normalizeFleetData(response) {
    return {
      source: response.source_coords, target: response.target_coords,
      emergency_mode: response.emergency_mode || false,
      fleet: {
        vehicle_count: response.vehicle_count,
        max_time_minutes: response.max_time_minutes,
        unique_route_count: response.unique_route_count,
        routes_within_limit: response.routes_within_limit,
        max_travel_time_min: response.max_travel_time_min,
        assignments: response.assignments || [],
      },
    };
  }

  normalizeVrpData(response) {
    return {
      source: response.source_coords, target: response.target_coords,
      emergency_mode: response.emergency_mode || false,
      fleet: {
        vehicle_count: response.vehicle_count,
        max_time_minutes: response.max_route_time_minutes,
        unique_route_count: response.route_count,
        routes_within_limit: (response.assignments || []).filter(r => r.within_max_time).length,
        max_travel_time_min: Math.max(0, ...(response.assignments || []).map(r => r.travel_time_min)),
        assignments: response.assignments || [],
        vrp: true,
        stop_count: response.stop_count,
        served_stop_count: response.served_stop_count,
        unassigned_stop_count: response.unassigned_stop_count,
      },
    };
  }

  // ── Experiments ─────────────────────────────────────────────────────
  async saveExperiment(experiment) {
    return await this.request('/api/experiments', { method: 'POST', body: JSON.stringify(experiment) });
  }

  // ── Admin ───────────────────────────────────────────────────────────
  async getAdminUsers() {
    return await this.request('/api/admin/users');
  }

  async getAdminStatistics() {
    return await this.request('/api/admin/statistics');
  }

  async getAdminRoutes() {
    return await this.request('/api/admin/routes');
  }

  async getAdminPerformance() {
    return await this.request('/api/admin/performance');
  }
}

class APIError extends Error {
  constructor(message, code) {
    super(message);
    this.name = 'APIError';
    this.code = code;
  }
}

const api = new APIService();
