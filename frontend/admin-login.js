const API_BASE = 'http://localhost:5000/api';
const SESSION_KEY = 'qroute-session';

function setSession(user) {
  localStorage.setItem(SESSION_KEY, JSON.stringify(user));
}

function showAlert(message, type = 'error') {
  const el = document.getElementById('admin-login-alert');
  el.textContent = message;
  el.className = `alert show ${type}`;
}

document.getElementById('admin-login-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const identifier = document.getElementById('admin-identifier').value.trim();
  const password = document.getElementById('admin-password').value.trim();

  if (!identifier || !password) {
    showAlert('Please enter admin credentials.');
    return;
  }

  try {
    const response = await fetch(`${API_BASE}/admin/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ identifier, password }),
    });
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || 'Admin login failed.');
    }

    setSession(data.user);
    window.location.href = 'admin.html';
  } catch (error) {
    showAlert(error.message, 'error');
  }
});
