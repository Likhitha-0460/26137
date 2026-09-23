const API_BASE = 'http://localhost:5000/api';
const SESSION_KEY = 'qroute-session';

const session = JSON.parse(localStorage.getItem(SESSION_KEY) || 'null');
if (!session) {
  window.location.href = 'auth.html';
}

const userNameEl = document.getElementById('user-name');
const routeCountEl = document.getElementById('route-count');
const trafficFilter = document.getElementById('traffic-filter');
const routeListEl = document.getElementById('route-list');
const userLocationEl = document.getElementById('user-location');
const trafficText = document.getElementById('traffic-status-text');

userNameEl.textContent = session?.name || 'User';

function setRouteSummary(message) {
  userLocationEl.innerHTML = message;
}

document.getElementById('logout-btn').addEventListener('click', async () => {
  try {
    await fetch(`${API_BASE}/auth/logout`, { method: 'POST', credentials: 'include' });
  } catch (error) {
    console.warn('Logout request failed:', error);
  }
  localStorage.removeItem(SESSION_KEY);
  window.location.href = 'auth.html';
});

async function loadRoutes() {
  const traffic = trafficFilter.value;
  try {
    const response = await fetch(`${API_BASE}/user/routes?traffic=${encodeURIComponent(traffic)}`, {
      credentials: 'include',
    });
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || 'Could not fetch routes.');
    }

    const routes = data.routes || [];
    routeListEl.innerHTML = routes.map(route => `
      <div class="route-card ${route.traffic_level === 'low' ? 'selected' : ''}" data-id="${route.id}">
        <div class="route-meta">
          <strong>${route.name}</strong>
          <span class="route-badge ${route.congestion.toLowerCase()}">${route.congestion}</span>
        </div>
        <div>Time: ${route.travel_time_min} min | Distance: ${route.distance_km} km | Score: ${route.score}%</div>
        <button class="secondary-btn" type="button" data-select="${route.id}">Select route</button>
      </div>
    `).join('');

    routeCountEl.textContent = String(routes.length);
    document.querySelectorAll('[data-select]').forEach(button => {
      button.addEventListener('click', async () => {
        const selectedId = button.dataset.select;
        document.querySelectorAll('.route-card').forEach(card => {
          card.classList.toggle('selected', card.dataset.id === selectedId);
        });

        try {
          const routeResponse = await fetch(`${API_BASE}/user/route-selection`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ route_id: selectedId }),
          });
          const routeData = await routeResponse.json();
          if (!routeResponse.ok) {
            throw new Error(routeData.error || 'Failed to select route.');
          }
          const selectedRoute = routes.find(route => route.id === selectedId);
          setRouteSummary(`<strong>Selected route:</strong> ${selectedRoute.name}<br>Traffic: ${selectedRoute.congestion}<br>Travel time: ${selectedRoute.travel_time_min} min<br>Distance: ${selectedRoute.distance_km} km<br>Score: ${selectedRoute.score}%`);
        } catch (error) {
          userLocationEl.textContent = error.message;
        }
      });
    });
  } catch (error) {
    routeListEl.innerHTML = `<div class="route-card">${error.message}</div>`;
  }
}

trafficFilter.addEventListener('change', () => {
  const value = trafficFilter.value;
  if (value === 'low') trafficText.textContent = 'Low congestion';
  if (value === 'medium') trafficText.textContent = 'Balanced';
  if (value === 'high') trafficText.textContent = 'Heavy traffic';
  loadRoutes();
});

loadRoutes();
setRouteSummary('Select a route to view the summary and trip details.');
