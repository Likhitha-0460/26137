const SESSION_KEY = 'qroute-session';
const API_BASE = `${window.location.origin}/api`;

function setSession(user) {
  localStorage.setItem(SESSION_KEY, JSON.stringify(user));
}

function getSession() {
  const item = localStorage.getItem(SESSION_KEY);
  if (!item) return null;
  try { return JSON.parse(item); } catch { return null; }
}

function showAlert(elementId, text, type = 'error') {
  const el = document.getElementById(elementId);
  el.textContent = text;
  el.className = `alert show ${type}`;
}

function hideAlert(elementId) {
  const el = document.getElementById(elementId);
  el.textContent = '';
  el.className = 'alert';
}

function switchTab(tabName) {
  document.querySelectorAll('.tab-button').forEach(button => {
    button.classList.toggle('active', button.dataset.tab === tabName);
  });
  document.querySelectorAll('.form-panel').forEach(panel => {
    panel.classList.toggle('active', panel.id === `${tabName}-panel`);
  });
}

document.querySelectorAll('.tab-button').forEach(button => {
  button.addEventListener('click', () => switchTab(button.dataset.tab));
});

document.getElementById('signup-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  hideAlert('signup-alert');

  const payload = {
    name: document.getElementById('signup-name').value.trim(),
    email: document.getElementById('signup-email').value.trim(),
    phone: document.getElementById('signup-phone').value.trim(),
    username: document.getElementById('signup-username').value.trim(),
    password: document.getElementById('signup-password').value.trim(),
    role: document.getElementById('signup-role').value,
  };

  if (!payload.name || !payload.email || !payload.phone || !payload.username || !payload.password) {
    showAlert('signup-alert', 'Please fill in all details.', 'error');
    return;
  }

  try {
    const response = await fetch(`${API_BASE}/auth/signup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(payload),
    });
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || 'Signup failed.');
    }

    showAlert('signup-alert', `${payload.role === 'admin' ? 'Admin' : 'User'} account created successfully!`, 'success');
    document.getElementById('signup-form').reset();
    setTimeout(() => switchTab('login'), 1500);
  } catch (error) {
    showAlert('signup-alert', error.message, 'error');
  }
});

document.getElementById('login-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  hideAlert('login-alert');

  const identifier = document.getElementById('login-identifier').value.trim();
  const password = document.getElementById('login-password').value.trim();

  if (!identifier || !password) {
    showAlert('login-alert', 'Please enter your login details and password.', 'error');
    return;
  }

  try {
    const response = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ identifier, password }),
    });
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || 'Login failed.');
    }

    setSession(data.user);

    // Redirect based on role
    if (data.user.role === 'admin') {
      window.location.href = 'admin.html';
    } else {
      // Regular users go to main map
      window.location.href = '/map';
    }
  } catch (error) {
    showAlert('login-alert', error.message, 'error');
  }
});

(async function initAuthRedirect() {
  const session = getSession();
  if (!session) return;

  try {
    const response = await fetch(`${API_BASE}/auth/me`, { credentials: 'include' });
    if (!response.ok) {
      localStorage.removeItem(SESSION_KEY);
      return;
    }
    const data = await response.json();
    if (data.user) {
      setSession(data.user);
      if (data.user.role === 'admin') {
        window.location.href = 'admin.html';
      } else {
        window.location.href = '/map';
      }
    }
  } catch (error) {
    console.warn('Session validation failed:', error);
  }
})();
