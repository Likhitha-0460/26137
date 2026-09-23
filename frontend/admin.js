const API_BASE = 'http://localhost:5000/api';
const SESSION_KEY = 'qroute-session';

const session = JSON.parse(localStorage.getItem(SESSION_KEY) || 'null');
if (!session) {
  window.location.href = 'auth.html';
}

const adminNameEl = document.getElementById('admin-name');
adminNameEl.textContent = session?.name || 'Admin';

document.getElementById('logout-btn').addEventListener('click', async () => {
  try {
    await fetch(`${API_BASE}/auth/logout`, { method: 'POST', credentials: 'include' });
  } catch (error) {
    console.warn('Logout request failed:', error);
  }
  localStorage.removeItem(SESSION_KEY);
  window.location.href = 'auth.html';
});

const table = document.getElementById('admin-user-table');
const adminSnapshot = document.getElementById('admin-snapshot');
const lowCount = document.getElementById('lowcount');
const midCount = document.getElementById('midcount');
const highCount = document.getElementById('highcount');

function getStatusClass(status) {
  const normalized = (status || 'Offline').toLowerCase();
  if (normalized === 'live') return 'status-live';
  if (normalized === 'idle') return 'status-idle';
  return 'status-offline';
}

async function loadAdminUsers() {
  try {
    const response = await fetch(`${API_BASE}/auth/me`, { credentials: 'include' });
    const authData = await response.json();
    if (!response.ok || authData.user.role !== 'admin') {
      throw new Error('Admin access required');
    }

    const usersResponse = await fetch(`${API_BASE}/admin/users`, { credentials: 'include' });
    const usersData = await usersResponse.json();
    if (!usersResponse.ok) {
      throw new Error(usersData.error || 'Could not fetch users.');
    }

    const users = usersData.users || [];
    table.innerHTML = users.map(user => {
      const locationText = user.location ? `${user.location.lat}, ${user.location.lon}` : 'No live location';
      return `
        <tr>
          <td>${user.name}</td>
          <td>${user.email}</td>
          <td>${locationText}</td>
          <td><span class="status-pill ${getStatusClass(user.status)}">${user.status || 'Offline'}</span></td>
        </tr>
      `;
    }).join('');

    const trafficCounts = { low: 1, medium: 2, high: 1 };
    lowCount.textContent = trafficCounts.low;
    midCount.textContent = trafficCounts.medium;
    highCount.textContent = trafficCounts.high;

    adminSnapshot.innerHTML = `
      <strong>Current route traffic split:</strong><br>
      Low: ${trafficCounts.low} user routes<br>
      Medium: ${trafficCounts.medium} user routes<br>
      High: ${trafficCounts.high} user routes<br>
      <br>
      Admin visibility includes active and offline users with their current location and route selection status.
    `;
  } catch (error) {
    table.innerHTML = `<tr><td colspan="4">${error.message}</td></tr>`;
    window.location.href = 'auth.html';
  }
}

loadAdminUsers();
