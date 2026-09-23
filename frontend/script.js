/**
 * Q-ROUTE Main Application Script
 * Multi-user traffic route optimization with quantum-inspired algorithms
 */

// ── Application State ────────────────────────────────────────────────
const state = {
  sourcePoint: null,
  targetPoint: null,
  benchmark: null,
  mapSelectionMode: null,
  sourceLabel: null,
  targetLabel: null,
  routes: null,
  multiRoutes: null,       // New multi-route results
  currentRequestId: null,  // Current route request ID
  trafficOverlayVisible: false,
  optimizationInProgress: false,
  backendConnected: false,
  cityInfo: null,
  currentUser: null,
  charts: { time: null, cost: null, fitness: null },
};

// Route colors for multi-route display
const MULTI_ROUTE_COLORS = [
  '#06b6d4', '#f59e0b', '#2563eb', '#10b981', '#8b5cf6',
  '#e11d48', '#0891b2', '#d97706', '#7c3aed', '#16a34a',
];

const ALGO_COLORS = {
  dijkstra: '#2563eb', astar: '#8b5cf6', qpso: '#06b6d4',
  aco: '#f59e0b', qiga: '#10b981', bpr: '#e11d48',
};

function getRouteColor(routeOrKey) {
  const val = typeof routeOrKey === 'string' ? routeOrKey : routeOrKey?.algorithm || '';
  const n = val.toLowerCase();
  if (n.includes('a*')) return ALGO_COLORS.astar;
  if (n.includes('qpso') || n.includes('quantum-diversified')) return ALGO_COLORS.qpso;
  if (n.includes('aco') || n.includes('candidate')) return ALGO_COLORS.aco;
  if (n.includes('dijkstra') || n.includes('optimal')) return ALGO_COLORS.dijkstra;
  if (n.includes('qiga') || n.includes('quantum-inspired')) return ALGO_COLORS.qiga;
  if (n.includes('bpr')) return ALGO_COLORS.bpr;
  const key = Object.keys(ALGO_COLORS).find(k => n.includes(k));
  return ALGO_COLORS[key || 'qiga'];
}

// ── DOM Elements ─────────────────────────────────────────────────────
const elements = {};
function cacheElements() {
  const ids = [
    'map', 'source-input', 'target-input', 'pick-source', 'pick-target',
    'map-selection-guide', 'source-autocomplete', 'target-autocomplete',
    'optimize-btn', 'swap-locations', 'clear-target', 'emergency-mode',
    'results-panel', 'results-body', 'close-results',
    'comparison-panel', 'comparison-table-body',
    'qiga-panel', 'loading-overlay', 'loading-text',
    'error-toast', 'error-message', 'close-toast', 'success-toast', 'success-message',
    'backend-status', 'city-info', 'traffic-status',
    'minimize-search', 'minimize-comparison', 'toggle-qiga',
    'zoom-in', 'zoom-out', 'fit-routes', 'clear-routes',
    'toggle-traffic', 'fullscreen',
    'qpso-population', 'qpso-iterations', 'qpso-seed',
    'weight-time', 'weight-distance', 'weight-congestion',
    'rerun-qpso', 'traffic-mode', 'save-experiment', 'fitness-chart',
    'optimization-mode', 'benchmark-mode-select',
    'traffic-pref-group', 'num-routes-group',
    'history-panel', 'history-body', 'close-history',
    'user-display-name', 'header-logout-btn', 'user-profile-chip',
  ];
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (el) elements[id.replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = el;
  });
}

// ── Initialize ───────────────────────────────────────────────────────
async function init() {
  cacheElements();
  try {
    showLoading('Connecting to backend...');

    // Check auth
    try {
      const me = await api.getMe();
      state.currentUser = me.user;
      if (elements.userDisplayName) elements.userDisplayName.textContent = me.user.name || me.user.username;
    } catch {
      // Not logged in - redirect to auth
      window.location.href = 'auth.html';
      return;
    }

    const bounds = await api.checkHealth();
    state.backendConnected = true;
    state.cityInfo = bounds;
    updateStatusUI(bounds);

    const center = [bounds.center.lat, bounds.center.lon];
    await mapProvider.initialize('map', center, 12, { provider: 'leaflet' });

    setupMapListeners();
    setupUIListeners();
    setupSearch();
    hideLoading();
    console.log('Q-ROUTE initialized successfully');
  } catch (error) {
    console.error('Initialization error:', error);
    showBackendOffline();
    hideLoading();
  }
}

function updateStatusUI(bounds) {
  const statusDot = elements.backendStatus?.querySelector('.status-dot');
  const statusText = elements.backendStatus?.querySelector('.status-text');
  if (statusDot) statusDot.classList.add('connected');
  if (statusText) statusText.textContent = 'Connected';
  if (elements.cityInfo) elements.cityInfo.querySelector('span').textContent = bounds.city || 'Bengaluru';
  if (elements.trafficStatus) {
    const t = elements.trafficStatus.querySelector('span');
    t.textContent = bounds.dataset_loaded ? 'Live' : 'Simulated';
    elements.trafficStatus.style.color = bounds.dataset_loaded ? 'var(--accent-green)' : 'var(--text-secondary)';
  }
}

function showBackendOffline() {
  const statusDot = elements.backendStatus?.querySelector('.status-dot');
  const statusText = elements.backendStatus?.querySelector('.status-text');
  if (statusDot) statusDot.classList.add('disconnected');
  if (statusText) statusText.textContent = 'Offline';
  showError('Backend unavailable. Start the Flask server.');
}

// ── Map ──────────────────────────────────────────────────────────────
function setupMapListeners() {
  mapProvider.on('click', handleMapClick);
}

function handleMapClick(e) {
  if (state.optimizationInProgress) return;
  let lat, lng;
  if (mapProvider.getProvider() === 'google') {
    lat = e.latLng.lat(); lng = e.latLng.lng();
  } else {
    lat = e.latlng.lat; lng = e.latlng.lng;
  }
  const type = state.mapSelectionMode || (!state.sourcePoint ? 'source' : !state.targetPoint ? 'target' : null);
  if (!type) { setMapSelectionMode('source'); return; }
  // Reverse geocode to get area name
  reverseGeocodeAndSetPoint(lat, lng, type);
}

async function reverseGeocodeAndSetPoint(lat, lng, type) {
  try {
    const results = await api.geocode(`${lat}, ${lng}`);
    const areaName = results?.[0]?.area_name || results?.[0]?.display_name?.split(',').slice(0, 2).join(', ') || 'Map selection';
    setPoint(lat, lng, type, areaName);
  } catch {
    setPoint(lat, lng, type, 'Map selection');
  }
  if (type === 'source' && !state.targetPoint) {
    setMapSelectionMode('target');
  } else {
    setMapSelectionMode(null);
  }
}

// ── UI Listeners ─────────────────────────────────────────────────────
function setupUIListeners() {
  // Navigation
  document.querySelectorAll('.nav-link').forEach(link => link.addEventListener('click', e => {
    e.preventDefault();
    activateNavigationSection(link.dataset.section);
  }));

  // Console tabs
  document.querySelectorAll('.console-tab').forEach(tab => tab.addEventListener('click', () => {
    document.querySelectorAll('.console-tab, .console-view').forEach(i => i.classList.remove('active'));
    tab.classList.add('active');
    document.querySelector(`[data-console-view="${tab.dataset.consoleTab}"]`)?.classList.add('active');
  }));

  // Weight sliders
  ['weightTime', 'weightDistance', 'weightCongestion'].forEach(key => {
    const input = elements[key];
    if (input) input.addEventListener('input', () => {
      document.getElementById(`${input.id}-value`).textContent = Number(input.value).toFixed(2);
    });
  });

  // Traffic preference buttons
  document.querySelectorAll('.traffic-pref-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.traffic-pref-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
    });
  });

  // Number of routes buttons
  document.querySelectorAll('.num-route-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.num-route-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
    });
  });

  // Buttons
  if (elements.rerunQpso) elements.rerunQpso.addEventListener('click', optimizeRoute);
  if (elements.trafficMode) elements.trafficMode.addEventListener('change', async () => {
    try {
      await api.updateTrafficMode(elements.trafficMode.value);
      showSuccess('Traffic mode updated');
    } catch (error) { showError(error.message); }
  });
  if (elements.saveExperiment) elements.saveExperiment.addEventListener('click', async () => {
    if (!state.routes && !state.multiRoutes) { showError('Run an experiment first.'); return; }
    try {
      await api.saveExperiment({ routes: state.routes || state.multiRoutes });
      showSuccess('Experiment saved');
    } catch (error) { showError(error.message); }
  });

  if (elements.swapLocations) elements.swapLocations.addEventListener('click', swapLocations);
  if (elements.pickSource) elements.pickSource.addEventListener('click', () => setMapSelectionMode('source'));
  if (elements.pickTarget) elements.pickTarget.addEventListener('click', () => setMapSelectionMode('target'));
  if (elements.clearTarget) elements.clearTarget.addEventListener('click', clearTarget);
  if (elements.optimizeBtn) elements.optimizeBtn.addEventListener('click', optimizeRoute);
  if (elements.closeResults) elements.closeResults.addEventListener('click', () => elements.resultsPanel?.classList.remove('show'));
  if (elements.minimizeSearch) elements.minimizeSearch.addEventListener('click', () => document.querySelector('.search-panel')?.classList.toggle('minimized'));
  if (elements.minimizeComparison) elements.minimizeComparison.addEventListener('click', () => elements.comparisonPanel?.classList.toggle('minimized'));
  if (elements.toggleQiga) elements.toggleQiga.addEventListener('click', () => elements.qigaPanel?.classList.toggle('show'));
  if (elements.closeToast) elements.closeToast.addEventListener('click', hideError);
  if (elements.closeHistory) elements.closeHistory.addEventListener('click', () => elements.historyPanel?.classList.remove('show'));

  // Map controls
  if (elements.zoomIn) elements.zoomIn.addEventListener('click', () => mapProvider.setCenter(mapProvider.getCenter(), mapProvider.getZoom() + 1));
  if (elements.zoomOut) elements.zoomOut.addEventListener('click', () => mapProvider.setCenter(mapProvider.getCenter(), mapProvider.getZoom() - 1));
  if (elements.fitRoutes) elements.fitRoutes.addEventListener('click', fitAllRoutes);
  if (elements.clearRoutes) elements.clearRoutes.addEventListener('click', clearAllRoutes);
  if (elements.toggleTraffic) elements.toggleTraffic.addEventListener('click', toggleTrafficOverlay);
  if (elements.fullscreen) elements.fullscreen.addEventListener('click', toggleFullscreen);

  // Logout
  if (elements.headerLogoutBtn) elements.headerLogoutBtn.addEventListener('click', async () => {
    try { await api.logout(); } catch {}
    localStorage.removeItem('qroute-session');
    window.location.href = 'auth.html';
  });
}

function activateNavigationSection(section) {
  document.querySelectorAll('.nav-link').forEach(l => l.classList.toggle('active', l.dataset.section === section));

  // Hide all panels first
  if (elements.comparisonPanel) elements.comparisonPanel.classList.remove('show');
  if (elements.qigaPanel) elements.qigaPanel.classList.remove('show');
  if (elements.historyPanel) elements.historyPanel.classList.remove('show');

  if (section === 'analysis') {
    elements.comparisonPanel?.classList.add('show');
    if (state.sourcePoint && state.targetPoint) runBenchmark();
    else showError('Select source A and destination B before benchmarking.');
  } else if (section === 'about') {
    elements.qigaPanel?.classList.add('show');
  } else if (section === 'history') {
    loadRouteHistory();
  }
}

// ── Benchmark ────────────────────────────────────────────────────────
async function runBenchmark() {
  if (state.optimizationInProgress || !state.sourcePoint || !state.targetPoint) return;
  state.optimizationInProgress = true;
  const mode = elements.benchmarkModeSelect?.value || 'quick';
  showLoading(`Running ${mode} benchmark...`);
  try {
    const response = await api.benchmarkRoutes({
      source_lat: state.sourcePoint.lat, source_lon: state.sourcePoint.lon,
      target_lat: state.targetPoint.lat, target_lon: state.targetPoint.lon,
      emergency_mode: elements.emergencyMode?.checked || false,
      benchmark_mode: mode,
      settings: {
        population_size: Number(elements.qpsoPopulation?.value || 6),
        iterations: Number(elements.qpsoIterations?.value || 5),
        seed: Number(elements.qpsoSeed?.value || 42),
      },
    });
    state.benchmark = api.normalizeBenchmarkData(response);
    displayBenchmarkRoutes();
    displayComparison();
  } catch (error) {
    showError(error.message || 'Benchmark failed.');
  } finally {
    state.optimizationInProgress = false;
    hideLoading();
  }
}

function displayBenchmarkRoutes() {
  mapProvider.clearPolylines();
  state.benchmark.algorithms.forEach(route => {
    if (!route.path_coords?.length) return;
    mapProvider.addPolyline(
      route.path_coords.map(p => [p.lat, p.lon]),
      { color: getRouteColor(route), weight: route.algorithm === state.benchmark.recommended_algorithm ? 7 : 4, opacity: route.algorithm === state.benchmark.recommended_algorithm ? 0.95 : 0.55 }
    );
  });
  const allCoords = state.benchmark.algorithms.flatMap(r => (r.path_coords || []).map(p => [p.lat, p.lon]));
  if (allCoords.length) mapProvider.fitBounds(allCoords, { padding: [50, 50] });
}

// ── Search ───────────────────────────────────────────────────────────
function setupSearch() {
  let sourceTimer, targetTimer;
  elements.sourceInput?.addEventListener('input', e => {
    clearTimeout(sourceTimer);
    const q = e.target.value.trim();
    if (q.length < 3) { elements.sourceAutocomplete?.classList.remove('show'); return; }
    sourceTimer = setTimeout(() => performSearch(q, 'source'), 300);
  });
  elements.targetInput?.addEventListener('input', e => {
    clearTimeout(targetTimer);
    const q = e.target.value.trim();
    if (q.length < 3) { elements.targetAutocomplete?.classList.remove('show'); return; }
    targetTimer = setTimeout(() => performSearch(q, 'target'), 300);
  });
  elements.sourceInput?.addEventListener('keydown', e => handleManualEntry(e, 'source'));
  elements.targetInput?.addEventListener('keydown', e => handleManualEntry(e, 'target'));

  document.addEventListener('click', e => {
    if (!elements.sourceInput?.contains(e.target) && !elements.sourceAutocomplete?.contains(e.target))
      elements.sourceAutocomplete?.classList.remove('show');
    if (!elements.targetInput?.contains(e.target) && !elements.targetAutocomplete?.contains(e.target))
      elements.targetAutocomplete?.classList.remove('show');
  });
}

async function handleManualEntry(event, type) {
  if (event.key !== 'Enter') return;
  event.preventDefault();
  const input = type === 'source' ? elements.sourceInput : elements.targetInput;
  const match = input.value.trim().match(/^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$/);
  if (match) {
    const lat = Number(match[1]), lon = Number(match[2]);
    if (lat < -90 || lat > 90 || lon < -180 || lon > 180) { showError('Invalid coordinates.'); return; }
    await reverseGeocodeAndSetPoint(lat, lon, type);
    mapProvider.setCenter([lat, lon], 14);
    return;
  }
  if (input.value.trim().length < 3) { showError('Enter an address or coordinates.'); return; }
  try {
    const results = await api.geocode(input.value.trim());
    if (!results.length) { showError('Location not found.'); return; }
    const r = results[0];
    setPoint(r.lat, r.lon, type, r.area_name || getAreaName(r.display_name));
    mapProvider.setCenter([r.lat, r.lon], 14);
    (type === 'source' ? elements.sourceAutocomplete : elements.targetAutocomplete)?.classList.remove('show');
  } catch (error) { showError(error.message); }
}

function setMapSelectionMode(type) {
  state.mapSelectionMode = type;
  elements.pickSource?.classList.toggle('active', type === 'source');
  elements.pickTarget?.classList.toggle('active', type === 'target');
  const mapEl = document.getElementById('map');
  if (mapEl) mapEl.style.cursor = type ? 'crosshair' : '';
  elements.mapSelectionGuide?.classList.toggle('show', Boolean(type));
  if (type && elements.mapSelectionGuide) {
    elements.mapSelectionGuide.innerHTML = type === 'source'
      ? '<i class="fa-solid fa-location-crosshairs"></i><span>Click map to place <strong>A</strong> (Origin)</span>'
      : '<i class="fa-solid fa-location-crosshairs"></i><span>Click map to place <strong>B</strong> (Destination)</span>';
  }
}

async function performSearch(query, type) {
  try {
    const results = await api.geocode(query);
    const dropdown = type === 'source' ? elements.sourceAutocomplete : elements.targetAutocomplete;
    if (!results?.length) { dropdown?.classList.remove('show'); return; }
    dropdown.innerHTML = '';
    results.forEach(result => {
      const item = document.createElement('div');
      item.className = 'autocomplete-item';
      const areaName = result.area_name || getAreaName(result.display_name);
      item.innerHTML = `
        <div class="autocomplete-main">${areaName}</div>
        <div class="autocomplete-sub">${Number(result.lat).toFixed(5)}, ${Number(result.lon).toFixed(5)}</div>
      `;
      item.addEventListener('click', () => {
        setPoint(result.lat, result.lon, type, areaName);
        dropdown.classList.remove('show');
        mapProvider.setCenter([result.lat, result.lon], 14);
      });
      dropdown.appendChild(item);
    });
    dropdown.classList.add('show');
  } catch (error) { console.error('Search error:', error); }
}

function getAreaName(displayName) {
  return String(displayName || 'Selected location')
    .split(',')
    .map(part => part.trim())
    .filter(Boolean)
    .slice(0, 2)
    .join(', ');
}

function formatLocationLabel(label, lat, lon) {
  return `${label || 'Map selection'} (${Number(lat).toFixed(5)}, ${Number(lon).toFixed(5)})`;
}

// ── Set Point ────────────────────────────────────────────────────────
function setPoint(lat, lon, type = null, label = null) {
  if (type === 'source' || (!state.sourcePoint && type !== 'target')) {
    state.sourcePoint = { lat, lon };
    state.sourceLabel = formatLocationLabel(label, lat, lon);
    if (elements.sourceInput) elements.sourceInput.value = state.sourceLabel;
    updateOptimizeButton();
  } else if (type === 'target' || (!state.targetPoint && type !== 'source')) {
    state.targetPoint = { lat, lon };
    state.targetLabel = formatLocationLabel(label, lat, lon);
    if (elements.targetInput) elements.targetInput.value = state.targetLabel;
    updateOptimizeButton();
  }
  renderEndpointMarkers();
}

function renderEndpointMarkers() {
  mapProvider.clearMarkers();
  if (state.sourcePoint) mapProvider.addMarker([state.sourcePoint.lat, state.sourcePoint.lon], { icon: createMarkerIcon('source') });
  if (state.targetPoint) mapProvider.addMarker([state.targetPoint.lat, state.targetPoint.lon], { icon: createMarkerIcon('target') });
}

function createMarkerIcon(type) {
  const label = type === 'source' ? 'A' : 'B';
  const color = type === 'source' ? '#10b981' : '#ef4444';
  if (mapProvider.getProvider() === 'google') {
    return {
      path: google.maps.SymbolPath.CIRCLE,
      fillColor: color,
      fillOpacity: 1,
      strokeColor: '#ffffff',
      strokeWeight: 3,
      scale: 12,
      label: { text: label, color: '#ffffff', fontWeight: '700', fontSize: '12px' },
    };
  }
  return L.divIcon({
    className: 'custom-marker',
    html: `<div style="background:${color};width:32px;height:32px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);border:3px solid white;box-shadow:0 2px 8px rgba(0,0,0,0.35);position:relative"><span style="display:block;color:white;font-size:14px;font-weight:800;line-height:26px;text-align:center;transform:rotate(45deg)">${label}</span></div>`,
    iconSize: [32, 44],
    iconAnchor: [16, 44],
  });
}

function swapLocations() {
  if (!state.sourcePoint || !state.targetPoint) return;
  [state.sourcePoint, state.targetPoint] = [state.targetPoint, state.sourcePoint];
  [state.sourceLabel, state.targetLabel] = [state.targetLabel, state.sourceLabel];
  if (elements.sourceInput) elements.sourceInput.value = state.sourceLabel;
  if (elements.targetInput) elements.targetInput.value = state.targetLabel;
  renderEndpointMarkers();
}

function clearTarget() {
  state.targetPoint = null; state.targetLabel = null;
  if (elements.targetInput) elements.targetInput.value = '';
  updateOptimizeButton();
  renderEndpointMarkers();
}

function updateOptimizeButton() {
  if (elements.optimizeBtn) elements.optimizeBtn.disabled = !(state.sourcePoint && state.targetPoint);
}

// ── Optimize Route (Multi-Route) ─────────────────────────────────────
async function optimizeRoute() {
  if (!state.sourcePoint || !state.targetPoint || state.optimizationInProgress) return;
  state.optimizationInProgress = true;
  state.benchmark = null;
  if (elements.optimizeBtn) elements.optimizeBtn.disabled = true;
  showLoading('Finding optimized routes...');

  const numRoutes = Number(document.querySelector('.num-route-btn.active')?.dataset.value || 3);
  const trafficPref = document.querySelector('.traffic-pref-btn.active')?.dataset.value || 'any';
  const optMode = elements.optimizationMode?.value || 'balanced';

  try {
    const response = await api.calculateRoutes({
      source_lat: state.sourcePoint.lat,
      source_lon: state.sourcePoint.lon,
      target_lat: state.targetPoint.lat,
      target_lon: state.targetPoint.lon,
      num_routes: numRoutes,
      traffic_preference: trafficPref,
      optimization_mode: optMode,
      emergency_mode: elements.emergencyMode?.checked || false,
      source_label: state.sourceLabel || '',
      destination_label: state.targetLabel || '',
    });

    state.multiRoutes = response;
    state.currentRequestId = response.request_id;
    displayMultiRoutes();
    displayMultiRouteCards();
    fitAllRoutes();
    showSuccess(`Found ${response.total_routes} optimized route${response.total_routes > 1 ? 's' : ''}`);
  } catch (error) {
    console.error('Route optimization error:', error);
    showError(error.message || 'Unable to calculate routes.');
  } finally {
    state.optimizationInProgress = false;
    if (elements.optimizeBtn) elements.optimizeBtn.disabled = false;
    hideLoading();
  }
}

// ── Display Multi-Routes on Map ──────────────────────────────────────
function displayMultiRoutes() {
  mapProvider.clearPolylines();
  if (!state.multiRoutes?.routes) return;

  state.multiRoutes.routes.forEach((route, idx) => {
    if (!route.path_coords?.length) return;
    const latlngs = route.path_coords.map(p => [p.lat, p.lon]);
    const color = getRouteColor(route);
    const isFirst = idx === 0;
    mapProvider.addPolyline(latlngs, {
      color,
      weight: isFirst ? 7 : 4,
      opacity: isFirst ? 0.95 : 0.65,
    });
  });
}

// ── Display Multi-Route Cards ────────────────────────────────────────
function displayMultiRouteCards() {
  if (!elements.resultsPanel || !elements.resultsBody) return;
  elements.resultsPanel.classList.add('show');
  elements.resultsBody.innerHTML = '';

  if (!state.multiRoutes?.routes?.length) {
    elements.resultsBody.innerHTML = '<div class="empty-state"><i class="fa-solid fa-route"></i><p>No routes found.</p></div>';
    return;
  }

  // Summary header
  const summary = document.createElement('div');
  summary.className = 'multi-route-summary';
  summary.innerHTML = `
    <div class="summary-row">
      <span class="summary-label">Mode</span>
      <span class="summary-value">${state.multiRoutes.optimization_mode || 'balanced'}</span>
    </div>
    <div class="summary-row">
      <span class="summary-label">Traffic</span>
      <span class="summary-value">${(state.multiRoutes.traffic_preference || 'any').toUpperCase()}</span>
    </div>
    <div class="summary-row">
      <span class="summary-label">Computed in</span>
      <span class="summary-value">${state.multiRoutes.compute_time_sec}s</span>
    </div>
  `;
  elements.resultsBody.appendChild(summary);

  state.multiRoutes.routes.forEach((route, idx) => {
    const color = getRouteColor(route);
    const trafficClass = (route.traffic_level || 'MEDIUM').toLowerCase();
    const fuelL = route.fuel_consumption_l != null ? route.fuel_consumption_l.toFixed(3) : '—';
    const fuelCost = route.fuel_cost != null ? `₹${route.fuel_cost.toFixed(0)}` : '—';

    const card = document.createElement('div');
    card.className = `route-card multi-route-card ${idx === 0 ? 'recommended' : ''}`;
    card.dataset.routeIndex = idx;
    card.innerHTML = `
      <div class="route-card-header">
        <div class="route-card-title">
          <span class="route-color-dot" style="background:${color}"></span>
          Route ${route.route_index}
          ${idx === 0 ? '<span class="recommended-badge">★ BEST</span>' : ''}
        </div>
        <span class="route-traffic-badge traffic-${trafficClass}">${route.traffic_level || 'MEDIUM'}</span>
      </div>
      <div class="route-card-metrics">
        <div class="route-metric">
          <div class="route-metric-label">Distance</div>
          <div class="route-metric-value">${route.distance_km} km</div>
        </div>
        <div class="route-metric">
          <div class="route-metric-label">Time</div>
          <div class="route-metric-value">${route.travel_time_min} min</div>
        </div>
        <div class="route-metric">
          <div class="route-metric-label">Fuel</div>
          <div class="route-metric-value">${fuelL} L</div>
        </div>
        <div class="route-metric">
          <div class="route-metric-label">Fuel Cost</div>
          <div class="route-metric-value">${fuelCost}</div>
        </div>
        <div class="route-metric">
          <div class="route-metric-label">Congestion</div>
          <div class="route-metric-value">${Number(route.avg_congestion).toFixed(2)}</div>
        </div>
        <div class="route-metric">
          <div class="route-metric-label">Weighted cost</div>
          <div class="route-metric-value">${Number(route.cost ?? 0).toFixed(3)}</div>
        </div>
        <div class="route-metric">
          <div class="route-metric-label">Graph edges</div>
          <div class="route-metric-value">${route.weighted_edges?.length ?? 0}</div>
        </div>
        <div class="route-metric">
          <div class="route-metric-label">Score</div>
          <div class="route-metric-value score-value">${route.optimization_score?.toFixed(1) || '—'}</div>
        </div>
      </div>
      <div class="route-card-algo">${route.algorithm}</div>
      <button class="view-route-btn" data-idx="${idx}">
        <i class="fa-solid fa-eye"></i> View Route
      </button>
    `;

    card.querySelector('.view-route-btn').addEventListener('click', e => {
      e.stopPropagation();
      highlightMultiRoute(idx);
    });

    card.addEventListener('click', () => highlightMultiRoute(idx));
    elements.resultsBody.appendChild(card);
  });
}

function highlightMultiRoute(idx) {
  document.querySelectorAll('.multi-route-card').forEach(c => c.classList.remove('selected'));
  document.querySelectorAll(`.multi-route-card[data-route-index="${idx}"]`).forEach(c => c.classList.add('selected'));

  mapProvider.clearPolylines();
  state.multiRoutes.routes.forEach((route, i) => {
    if (!route.path_coords?.length) return;
    const color = getRouteColor(route);
    const isSelected = i === idx;
    mapProvider.addPolyline(
      route.path_coords.map(p => [p.lat, p.lon]),
      { color, weight: isSelected ? 8 : 3, opacity: isSelected ? 0.95 : 0.25 }
    );
  });

  const selected = state.multiRoutes.routes[idx];
  if (selected?.path_coords?.length) {
    mapProvider.fitBounds(selected.path_coords.map(p => [p.lat, p.lon]), { padding: [50, 50] });
  }
}

// ── Comparison ───────────────────────────────────────────────────────
function displayComparison() {
  if (!elements.comparisonPanel) return;
  elements.comparisonPanel.classList.add('show');

  if (state.benchmark) {
    const b = state.benchmark;
    const best = b.recommended_algorithm;
    const worst = b.worst_algorithm;
    const colors = ['#2563eb', '#06b6d4', '#16a34a', '#d97706', '#7c3aed', '#e11d48'];
    const sorted = b.algorithms.slice().sort((a, c) => a.rank - c.rank);

    const body = elements.comparisonPanel.querySelector('.comparison-body');
    if (!body) return;

    body.innerHTML = `
      <div class="benchmark-mode-selector">
        <label>Benchmark Mode:</label>
        <select id="benchmark-mode-select">
          <option value="quick" ${b.benchmark_mode === 'quick' ? 'selected' : ''}>Quick</option>
          <option value="standard" ${b.benchmark_mode === 'standard' ? 'selected' : ''}>Standard</option>
          <option value="detailed" ${b.benchmark_mode === 'detailed' ? 'selected' : ''}>Detailed</option>
        </select>
      </div>
      <div class="benchmark-simple-header">
        <strong>Algorithm Ranking</strong>
        <span>Score = time(45%) + congestion(25%) + distance(20%) + compute(10%)</span>
      </div>
      <div class="benchmark-verdict"><strong>BEST: ${best}</strong><span>WORST: ${worst}</span></div>
      <div class="benchmark-simple-list">
        ${sorted.map((r, i) => `
          <div class="benchmark-simple-row ${r.algorithm === best ? 'is-best' : ''} ${r.algorithm === worst ? 'is-worst' : ''}">
            <div class="benchmark-simple-label">
              <span class="benchmark-color" style="background:${colors[i % colors.length]}"></span>
              <b>#${r.rank}</b><strong>${r.algorithm}</strong>
              ${r.algorithm === best ? '<span class="best-label">BEST</span>' : r.algorithm === worst ? '<span class="worst-label">WORST</span>' : ''}
            </div>
            <div class="benchmark-line-track">
              <span class="benchmark-line" style="width:${Math.max(4, r.overall_score_pct)}%;background:${colors[i % colors.length]}"></span>
            </div>
            <strong class="benchmark-percent">${Number(r.overall_score_pct).toFixed(2)}%</strong>
            <span class="benchmark-time">${r.travel_time_min}min | ₹${(r.fuel_cost || 0).toFixed(0)} | ${r.traffic_level || '-'}</span>
          </div>
        `).join('')}
      </div>
      <p class="benchmark-simple-note">All algorithms use the same weighted multi-objective cost function. Higher score = better.</p>
    `;

    // Rebind benchmark mode select
    const newSelect = document.getElementById('benchmark-mode-select');
    if (newSelect) {
      elements.benchmarkModeSelect = newSelect;
      newSelect.addEventListener('change', () => runBenchmark());
    }
  }
}

// ── Route History ────────────────────────────────────────────────────
async function loadRouteHistory() {
  if (!elements.historyPanel || !elements.historyBody) return;
  elements.historyPanel.classList.add('show');
  elements.historyBody.innerHTML = '<div class="loading-inline"><div class="loading-spinner-small"></div> Loading history...</div>';

  try {
    const data = await api.getRouteHistory();
    const history = data.history || [];

    if (!history.length) {
      elements.historyBody.innerHTML = '<div class="empty-state"><i class="fa-solid fa-history"></i><p>No route history yet.</p></div>';
      return;
    }

    elements.historyBody.innerHTML = history.map(req => `
      <div class="history-card">
        <div class="history-header-row">
          <div class="history-date">${new Date(req.created_at).toLocaleString()}</div>
          <span class="history-mode-badge">${req.optimization_mode || 'balanced'}</span>
        </div>
        <div class="history-route-info">
          <div class="history-endpoint"><i class="fa-solid fa-circle-dot" style="color:#10b981"></i> ${req.origin_label || 'Origin'}</div>
          <div class="history-endpoint"><i class="fa-solid fa-location-dot" style="color:#ef4444"></i> ${req.destination_label || 'Destination'}</div>
        </div>
        <div class="history-meta">
          <span>Traffic: ${(req.traffic_preference || 'any').toUpperCase()}</span>
        </div>
        ${req.routes?.length ? `
          <div class="history-routes-list">
            ${req.routes.map(r => `
              <div class="history-route-row ${r.selected ? 'selected' : ''}">
                <span class="history-route-algo">${r.algorithm}</span>
                <span>${r.distance_km} km</span>
                <span>${r.travel_time_min} min</span>
                <span>₹${(r.fuel_cost || 0).toFixed(0)}</span>
                <span class="traffic-${(r.traffic_level || 'MEDIUM').toLowerCase()}">${r.traffic_level || '-'}</span>
                ${r.selected ? '<span class="selected-badge">✓ Selected</span>' : ''}
              </div>
            `).join('')}
          </div>
        ` : ''}
      </div>
    `).join('');
  } catch (error) {
    elements.historyBody.innerHTML = `<div class="empty-state"><p>${error.message}</p></div>`;
  }
}

// ── Fit & Clear ──────────────────────────────────────────────────────
function fitAllRoutes() {
  const allCoords = [];
  if (state.multiRoutes?.routes) {
    state.multiRoutes.routes.forEach(r => {
      if (r.path_coords) allCoords.push(...r.path_coords.map(p => [p.lat, p.lon]));
    });
  }
  if (state.sourcePoint) allCoords.push([state.sourcePoint.lat, state.sourcePoint.lon]);
  if (state.targetPoint) allCoords.push([state.targetPoint.lat, state.targetPoint.lon]);
  if (allCoords.length > 1) mapProvider.fitBounds(allCoords, { padding: [50, 50] });
}

function clearAllRoutes() {
  mapProvider.clearPolylines();
  mapProvider.clearMarkers();
  state.routes = null;
  state.multiRoutes = null;
  state.benchmark = null;
  state.sourcePoint = null;
  state.targetPoint = null;
  state.sourceLabel = null;
  state.targetLabel = null;
  if (elements.sourceInput) elements.sourceInput.value = '';
  if (elements.targetInput) elements.targetInput.value = '';
  elements.resultsPanel?.classList.remove('show');
  elements.comparisonPanel?.classList.remove('show');
  elements.qigaPanel?.classList.remove('show');
  elements.historyPanel?.classList.remove('show');
  updateOptimizeButton();
}

// ── Traffic Overlay ──────────────────────────────────────────────────
async function toggleTrafficOverlay() {
  if (state.trafficOverlayVisible) {
    mapProvider.clearTrafficOverlay();
    state.trafficOverlayVisible = false;
    elements.toggleTraffic?.classList.remove('active');
    return;
  }
  try {
    showLoading('Loading traffic data...');
    const congestion = await api.getCongestion();
    mapProvider.addTrafficOverlay(congestion.edges);
    state.trafficOverlayVisible = true;
    elements.toggleTraffic?.classList.add('active');
    hideLoading();
  } catch (error) {
    showError(`Failed to load traffic: ${error.message}`);
    hideLoading();
  }
}

function toggleFullscreen() {
  if (!document.fullscreenElement) document.documentElement.requestFullscreen();
  else document.exitFullscreen();
}

// ── Loading / Error / Success ────────────────────────────────────────
function showLoading(text = 'Loading...') {
  if (elements.loadingText) elements.loadingText.textContent = text;
  elements.loadingOverlay?.classList.add('show');
}

function hideLoading() {
  elements.loadingOverlay?.classList.remove('show');
}

function showError(message) {
  if (elements.errorMessage) elements.errorMessage.textContent = message;
  elements.errorToast?.classList.add('show');
  setTimeout(hideError, 5000);
}

function hideError() {
  elements.errorToast?.classList.remove('show');
}

function showSuccess(message) {
  if (elements.successMessage) elements.successMessage.textContent = message;
  const toast = elements.successToast;
  if (toast) {
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 3000);
  }
}

// ── Init ─────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', init);
