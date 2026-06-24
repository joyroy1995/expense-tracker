// ── State ──
let currentUser = null;
let chartInstances = [];

// ── API Client ──
const FETCH_OPTS = { credentials: 'include' };

const api = {
  async get(url) {
    try {
      const res = await fetch(url, FETCH_OPTS);
      const data = await res.json();
      if (!res.ok) return { ok: false, error: data.error || 'Request failed' };
      return { ok: true, data };
    } catch { return { ok: false, error: 'Network error' }; }
  },
  async post(url, body) {
    try {
      const res = await fetch(url, {
        ...FETCH_OPTS,
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) return { ok: false, error: data.error || 'Request failed' };
      return { ok: true, data };
    } catch { return { ok: false, error: 'Network error' }; }
  },
  async postForm(url, formData) {
    try {
      const res = await fetch(url, {
        ...FETCH_OPTS,
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) return { ok: false, error: data.error || 'Request failed' };
      return { ok: true, data };
    } catch { return { ok: false, error: 'Network error' }; }
  },
  async del(url) {
    try {
      const res = await fetch(url, { ...FETCH_OPTS, method: 'DELETE' });
      const data = await res.json();
      if (!res.ok) return { ok: false, error: data.error || 'Request failed' };
      return { ok: true, data };
    } catch { return { ok: false, error: 'Network error' }; }
  },
  async put(url, body) {
    try {
      const res = await fetch(url, {
        ...FETCH_OPTS,
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) return { ok: false, error: data.error || 'Request failed' };
      return { ok: true, data };
    } catch { return { ok: false, error: 'Network error' }; }
  },
};

// ── Router ──

function getRoute() {
  const u = new URL(window.location.href);
  const path = u.pathname;
  const p = Object.fromEntries(u.searchParams.entries());

  const m = path.match(/^\/reset-password\/(.+)$/);
  if (m) return { view: 'reset-password', token: m[1] };

  const routes = {
    '/login': 'login',
    '/register': 'register',
    '/forgot-password': 'forgot-password',
    '/': 'home',
    '/dashboard': 'dashboard',
    '/profile': 'profile',
    '/budgets': 'budgets',
    '/calendar': 'calendar',
    '/recurring': 'recurring',
    '/admin/users': 'admin-users',
    '/admin/notifications': 'admin-notifications',
  };
  return { view: routes[path] || 'home', params: p };
}

function navigate(path) {
  if (path === window.location.pathname + window.location.search) return;
  history.pushState(null, '', path);
  renderRoute();
}

document.addEventListener('click', (e) => {
  const link = e.target.closest('[data-link]');
  if (link) {
    e.preventDefault();
    navigate(link.getAttribute('href'));
  }
});

window.addEventListener('popstate', renderRoute);

// ── Layout ──

function setLayout(type) {
  const sidebar = document.getElementById('sidebar');
  const menuToggle = document.getElementById('menuToggle');
  const topbar = document.getElementById('topbar');
  const app = document.getElementById('app');
  const adminLink = document.getElementById('adminLink');
  const adminNotifLink = document.getElementById('adminNotifLink');

  if (type === 'auth') {
    document.body.className = 'login-page';
    document.body.classList.remove('sidebar-open', 'sidebar-collapsed');
    if (sidebar) sidebar.style.display = 'none';
    if (menuToggle) menuToggle.style.display = 'none';
    if (topbar) topbar.style.display = 'none';
    app.className = 'login-container';
  } else {
    document.body.className = '';
    document.body.classList.remove('sidebar-open');
    if (sidebar) sidebar.style.display = '';
    if (menuToggle) menuToggle.style.display = '';
    if (topbar) topbar.style.display = '';
    app.className = 'container';
    if (adminLink) {
      adminLink.style.display = currentUser?.role === 'superuser' ? '' : 'none';
    }
    if (adminNotifLink) {
      adminNotifLink.style.display = currentUser?.role === 'superuser' ? '' : 'none';
    }
    const path = window.location.pathname;
    document.querySelectorAll('.nav-link[data-link]').forEach(el => {
      el.classList.toggle('active', el.getAttribute('href') === path);
    });
  }
}

document.addEventListener('click', (e) => {
  const menuToggle = document.getElementById('menuToggle');
  const overlay = document.getElementById('sidebarOverlay');
  const sidebarToggle = document.getElementById('sidebarToggle');

  if (e.target.closest('#menuToggle')) {
    document.body.classList.toggle('sidebar-open');
  }

  if (e.target.closest('#sidebarOverlay')) {
    document.body.classList.remove('sidebar-open');
  }

  if (e.target.closest('#sidebarToggle')) {
    if (window.innerWidth >= 769) {
      document.body.classList.toggle('sidebar-collapsed');
    } else {
    document.body.classList.remove('sidebar-open', 'sidebar-collapsed');
    }
  }
});

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    document.body.classList.remove('sidebar-open', 'sidebar-collapsed');
  }
});

// ── Mobile touch: swipe + tab tap ──

let touchStartX = 0;
let touchStartY = 0;

document.addEventListener('touchstart', (e) => {
  touchStartX = e.changedTouches[0].screenX;
  touchStartY = e.changedTouches[0].screenY;
});

document.addEventListener('touchend', (e) => {
  if (window.innerWidth > 768) return;
  const deltaX = e.changedTouches[0].screenX - touchStartX;
  const deltaY = e.changedTouches[0].screenY - touchStartY;
  if (Math.abs(deltaX) < 30) return;
  if (Math.abs(deltaX) < Math.abs(deltaY) * 1.5) return;
  const isOpen = document.body.classList.contains('sidebar-open');
  if (deltaX > 80 && touchStartX < 40 && !isOpen) {
    document.body.classList.add('sidebar-open');
  } else if (deltaX < -80 && isOpen) {
    document.body.classList.remove('sidebar-open');
  }
});

document.getElementById('sidebarTab')?.addEventListener('click', () => {
  if (window.innerWidth <= 768) {
    document.body.classList.toggle('sidebar-open');
  }
});

// ── Toast ──

function showToast(message, type = 'success') {
  const toast = document.getElementById('toast');
  if (!toast) return;
  toast.textContent = message;
  toast.className = `toast ${type} show`;
  setTimeout(() => toast.classList.remove('show'), 3000);
}

function showBudgetToastAlerts(alerts) {
  if (!alerts || !alerts.length) return;
  alerts.forEach(a => {
    const level = a.percentage >= 100 ? 'danger' : 'warning';
    const icon = a.percentage >= 100 ? '🚨' : '⚠️';
    const displayName = catDisplayName(a.category);
    const text = a.percentage >= 100
      ? `${displayName} budget exceeded! ৳${a.spent.toFixed(2)} of ৳${a.budget_amount.toFixed(2)}`
      : `${displayName} at ${a.percentage}% of budget (৳${a.spent.toFixed(2)}/৳${a.budget_amount.toFixed(2)})`;
    showToast(`${icon} ${text}`, level);
  });
}

// ── Helpers ──

function esc(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

function buildCategoryOptions(selected) {
  return Object.keys(window.categoryColors || {}).map(c =>
    `<option value="${c}" ${c === selected ? 'selected' : ''}>${c}</option>`
  ).join('');
}

function makeExpenseItem(exp) {
  return `
    <div class="expense-item" data-id="${exp.id}">
      <div class="expense-info">
        <div class="expense-description">${esc(exp.description)}</div>
        <span class="category-badge" style="background-color: ${exp.color}">${esc(exp.category)}</span>
      </div>
      <div class="expense-actions">
        <span class="expense-amount">৳${Number(exp.amount).toFixed(2)}</span>
        <button class="btn-delete" onclick="deleteExpense(${exp.id})">&times;</button>
      </div>
    </div>`;
}

function makePagination(baseUrl, page, totalPages) {
  if (totalPages <= 1) return '';
  let html = '<div class="pagination">';
  if (page > 1) html += `<a href="${baseUrl}page=${page - 1}" data-link class="page-link">&laquo; Prev</a>`;
  for (let p = 1; p <= totalPages; p++) {
    if (p === page) {
      html += `<span class="page-link page-current">${p}</span>`;
    } else if (p <= 3 || p > totalPages - 3 || (p >= page - 1 && p <= page + 1)) {
      html += `<a href="${baseUrl}page=${p}" data-link class="page-link">${p}</a>`;
    } else if ((p === 4 && page > 5) || (p === totalPages - 3 && page < totalPages - 4)) {
      html += `<span class="page-dots">...</span>`;
    }
  }
  if (page < totalPages) html += `<a href="${baseUrl}page=${page + 1}" data-link class="page-link">Next &raquo;</a>`;
  html += '</div>';
  return html;
}

function makeDateGroups(expenses) {
  let html = '', lastDate = '';
  for (const exp of expenses) {
    if (exp.date !== lastDate) {
      if (lastDate) html += '</div>';
      html += `<div class="date-group"><h3 class="date-header">${esc(exp.date)}</h3>`;
      lastDate = exp.date;
    }
    html += makeExpenseItem(exp);
  }
  if (lastDate) html += '</div>';
  return html;
}

// ── Delete Expense (global for onclick) ──

async function deleteExpense(id) {
  if (!confirm('Delete this expense?')) return;
  const res = await api.del(`/api/delete_expense/${id}`);
  if (!res.ok) { showToast(res.error, 'error'); return; }
  showToast('Expense deleted', 'success');
  const el = document.querySelector(`[data-id="${id}"]`);
  if (el) {
    const txt = el.querySelector('.expense-amount')?.textContent || '';
    const amt = parseFloat(txt.replace(/[৳,]/g, '')) || 0;
    el.style.opacity = '0';
    el.style.transform = 'translateX(-10px)';
    setTimeout(() => el.remove(), 300);
    // Update today total if present
    const statVal = document.querySelector('.stat-card .stat-value');
    if (statVal) {
      const cur = parseFloat(statVal.textContent.replace(/[৳,]/g, '')) || 0;
      statVal.textContent = `৳${(cur - amt).toFixed(2)}`;
    }
  }
}

// ── Views ──

// ── Login ──
async function renderLogin() {
  setLayout('auth');
  document.title = 'Sign In - Expense Tracker';
  const app = document.getElementById('app');
  app.innerHTML = `
    <div class="login-card">
      <div class="login-header">
        <div class="logo"><span class="logo-icon">৳</span></div>
        <h1>Expense Tracker</h1>
        <p>Track your expenses effortlessly</p>
      </div>
      <form id="loginForm" class="login-form">
        <div id="loginError" class="alert alert-error" style="display:none;"></div>
        <div class="form-group">
          <label for="loginUsername">Username</label>
          <input type="text" id="loginUsername" name="username" required autocomplete="username">
        </div>
        <div class="form-group">
          <label for="loginPassword">Password</label>
          <input type="password" id="loginPassword" name="password" required autocomplete="current-password">
        </div>
        <button type="submit" class="btn btn-primary btn-full">Sign In</button>
      </form>
      <div class="auth-links">
        <a href="/register" data-link>Create an account</a>
        <span class="auth-sep">|</span>
        <a href="/forgot-password" data-link>Forgot password?</a>
      </div>
    </div>`;

  document.getElementById('loginForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const errEl = document.getElementById('loginError');
    try {
      const username = document.getElementById('loginUsername').value.trim();
      const password = document.getElementById('loginPassword').value.trim();
      // Start permission request synchronously (within user gesture)
      let notifPromise;
      if ("Notification" in window && Notification.permission === "default") {
        try { notifPromise = Notification.requestPermission(); } catch {}
      }
      const res = await api.post('/api/login', { username, password });
      if (!res.ok) {
        errEl.textContent = res.error;
        errEl.style.display = '';
        return;
      }
      currentUser = res.data;
      let permission = "denied";
      if ("Notification" in window) {
        permission = Notification.permission;
        if (notifPromise) {
          try { permission = await notifPromise; } catch {}
        }
      }
      navigate('/');
    } catch (err) {
      errEl.textContent = err.message || 'Unexpected error';
      errEl.style.display = '';
    }
  });
}

// ── Register ──
async function renderRegister() {
  setLayout('auth');
  document.title = 'Register - Expense Tracker';
  const app = document.getElementById('app');
  app.innerHTML = `
    <div class="login-card">
      <div class="login-header">
        <div class="logo"><span class="logo-icon">৳</span></div>
        <h1>Create Account</h1>
        <p>Join Expense Tracker</p>
      </div>
      <form id="registerForm" class="login-form">
        <div id="regError" class="alert alert-error" style="display:none;"></div>
        <div class="form-group">
          <label for="regUsername">Username</label>
          <input type="text" id="regUsername" name="username" required minlength="3" autocomplete="username">
        </div>
        <div class="form-group">
          <label for="regPassword">Password</label>
          <input type="password" id="regPassword" name="password" required minlength="4" autocomplete="new-password">
        </div>
        <div class="form-group">
          <label for="regConfirm">Confirm Password</label>
          <input type="password" id="regConfirm" name="confirm" required autocomplete="new-password">
        </div>
        <button type="submit" class="btn btn-primary btn-full">Create Account</button>
      </form>
      <div class="auth-links">
        Already have an account? <a href="/login" data-link>Sign In</a>
      </div>
    </div>`;

  document.getElementById('registerForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const errEl = document.getElementById('regError');
    const username = document.getElementById('regUsername').value.trim();
    const password = document.getElementById('regPassword').value;
    const confirm = document.getElementById('regConfirm').value;
    const res = await api.post('/api/register', { username, password, confirm });
    if (!res.ok) {
      errEl.textContent = res.error;
      errEl.style.display = '';
      return;
    }
    currentUser = res.data;
    let permission = "denied";
    if ("Notification" in window) {
      permission = Notification.permission;
      if (permission === "default") {
        try { await Notification.requestPermission(); } catch {}
        permission = Notification.permission;
      }
    }
    navigate('/');
  });
}

// ── Forgot Password ──
async function renderForgotPassword() {
  setLayout('auth');
  document.title = 'Forgot Password - Expense Tracker';
  const app = document.getElementById('app');
  app.innerHTML = `
    <div class="login-card">
      <div class="login-header">
        <h1>Forgot Password</h1>
        <p>Enter your username to reset</p>
      </div>
      <form id="forgotForm" class="login-form">
        <div id="fpError" class="alert alert-error" style="display:none;"></div>
        <div id="fpSuccess" class="alert alert-success" style="display:none;"></div>
        <div class="form-group">
          <label for="fpUsername">Username</label>
          <input type="text" id="fpUsername" name="username" required autocomplete="username">
        </div>
        <button type="submit" class="btn btn-primary btn-full">Reset Password</button>
      </form>
      <div class="auth-links">
        <a href="/login" data-link>Back to Sign In</a>
      </div>
    </div>`;

  document.getElementById('forgotForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const errEl = document.getElementById('fpError');
    const successEl = document.getElementById('fpSuccess');
    const username = document.getElementById('fpUsername').value.trim();
    const res = await api.post('/api/forgot-password', { username });
    if (!res.ok) {
      errEl.textContent = res.error;
      errEl.style.display = '';
      successEl.style.display = 'none';
      return;
    }
    errEl.style.display = 'none';
    successEl.innerHTML = `Reset link: <a href="/reset-password/${res.data.token}" data-link>Click here</a>`;
    successEl.style.display = '';
  });
}

// ── Reset Password ──
async function renderResetPassword(token) {
  setLayout('auth');
  document.title = 'Reset Password - Expense Tracker';
  const app = document.getElementById('app');

  // Validate token first
  const validRes = await api.get(`/api/reset/${token}`);
  if (!validRes.ok) {
    app.innerHTML = `
      <div class="login-card">
        <div class="login-header"><h1>Invalid Link</h1></div>
        <div class="alert alert-error">${esc(validRes.error)}</div>
        <div class="auth-links"><a href="/forgot-password" data-link>Request a new reset link</a></div>
      </div>`;
    return;
  }

  app.innerHTML = `
    <div class="login-card">
      <div class="login-header">
        <h1>Reset Password</h1>
        <p>Choose a new password</p>
      </div>
      <form id="resetForm" class="login-form">
        <div id="resetError" class="alert alert-error" style="display:none;"></div>
        <div class="form-group">
          <label for="resetPassword">New Password</label>
          <input type="password" id="resetPassword" name="password" required minlength="4" autocomplete="new-password">
        </div>
        <div class="form-group">
          <label for="resetConfirm">Confirm Password</label>
          <input type="password" id="resetConfirm" name="confirm" required autocomplete="new-password">
        </div>
        <button type="submit" class="btn btn-primary btn-full">Set New Password</button>
      </form>
    </div>`;

  document.getElementById('resetForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const errEl = document.getElementById('resetError');
    const password = document.getElementById('resetPassword').value;
    const confirm = document.getElementById('resetConfirm').value;
    const res = await api.post(`/api/reset-password/${token}`, { password, confirm });
    if (!res.ok) {
      errEl.textContent = res.error;
      errEl.style.display = '';
      return;
    }
    showToast('Password reset successfully!', 'success');
    navigate('/login');
  });
}

// ── Home ──
async function renderHome(page = 1) {
  setLayout('app');
  document.title = 'Expense Tracker';
  const app = document.getElementById('app');

  const res = await api.get(`/api/index?page=${page}`);
  if (!res.ok) { handleAuthError(res); return; }
  const d = res.data;
  window.categoryColors = d.category_colors;

  // Auto-process due recurring transactions
  api.post('/api/recurring/process').then(pRes => {
    if (pRes.ok && pRes.data.processed > 0) {
      showToast(`🔄 Created ${pRes.data.processed} recurring expense(s)`, 'success');
    }
  });

  const todayHtml = d.today_expenses.length
    ? d.today_expenses.map(makeExpenseItem).join('')
    : '<div class="empty-state"><p>No expenses today. Add your first one!</p></div>';

  app.innerHTML = `
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-label">Today's Total</div>
        <div class="stat-value">৳${Number(d.today_total).toFixed(2)}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Monthly Total</div>
        <div class="stat-value">৳${Number(d.month_total).toFixed(2)}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Today's Expenses</div>
        <div class="stat-value">${d.today_expenses.length}</div>
      </div>
    </div>

    ${renderBudgetAlerts(d.budget_alerts)}

    <div class="ai-chat-card" id="aiChatCard">
      <div class="card-header-row" id="aiChatToggle" style="cursor:pointer;">
        <span style="font-weight:600;font-size:15px;"><span class="ai-icon">🤖</span> Ask AI</span>
        <div class="card-header-actions" style="display:flex;align-items:center;gap:8px;">
          <button class="chat-clear-btn" id="chatClearBtn" title="Clear chat">&times;</button>
          <span class="collapse-icon" id="aiChatCollapseIcon">▼</span>
        </div>
      </div>
      <div id="aiChatBody" class="chat-body">
        <div class="chat-messages" id="chatMessages"></div>
        <div class="chat-input-area">
          <button id="chatAttachBtn" class="chat-icon-btn" title="Attach receipt">📎</button>
          <input type="file" id="chatGalleryInput" accept="image/*" style="display:none">
          <div class="chat-input-inner">
            <textarea id="chatInput" rows="1" placeholder="Ask a question..." autocomplete="off"></textarea>
            <button id="voiceBtn" class="chat-input-btn" title="Voice input">🎤</button>
            <button id="chatSendBtn" class="chat-input-btn" title="Send" style="display:none"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg></button>
          </div>
          <div id="voicePreview" class="chat-voice-preview" style="display:none"></div>
        </div>
      </div>
    </div>

    <div class="main-grid">
      <div class="card add-expense-card">
        <h2 class="card-title">Add Expense</h2>
        <form id="expenseForm" class="expense-form" novalidate>
          <div class="form-row">
            <div class="form-group form-date">
              <label for="date">Date</label>
              <input type="date" id="date" name="date" value="${d.today}" required>
            </div>
            <div class="form-group form-desc">
              <label for="description">What did you spend?</label>
              <input type="text" id="description" name="description" required placeholder="e.g., badam 30 taka, rickshaw 50 tk" autocomplete="off">
              <div id="preview" class="preview-container"></div>
              <input type="file" id="receiptInput" accept="image/*" style="display:none">
            </div>
          </div>
          <div class="form-actions">
            <button type="button" id="scanBtn" class="btn btn-outline btn-scan">📷 Scan Receipt</button>
            <button type="submit" class="btn btn-primary btn-lg flex-1" id="submitBtn">
            <span class="btn-text">Add Expense</span>
            <span class="btn-loader" style="display:none;">
              <span class="spinner"></span>
            </span>
          </button>
          </div>
        </form>
      </div>

      <div class="card today-card">
        <h2 class="card-title">Today's Expenses</h2>
        <div id="todayExpenses" class="expense-list">${todayHtml}</div>
      </div>
    </div>
`;

  attachExpenseForm(d.today);
  initChatCard();
  renderChatMessages();
}

function renderBudgetAlerts(alerts) {
  if (!alerts || !alerts.length) return '';
  const items = alerts.map(a => {
    const level = a.percentage >= 100 ? 'danger' : 'warning';
    const icon = a.percentage >= 100 ? '🚨' : '⚠️';
    const displayName = a.category === '__overall__' ? 'Total Spending' : a.category;
    const text = a.percentage >= 100
      ? `<strong>${esc(displayName)}</strong> budget exceeded! ৳${a.spent.toFixed(2)} spent of ৳${a.budget_amount.toFixed(2)}`
      : `<strong>${esc(displayName)}</strong> budget nearly reached: ৳${a.spent.toFixed(2)} of ৳${a.budget_amount.toFixed(2)} (${a.percentage}%)`;
    return `<div class="budget-alert ${level}">
      <div class="budget-alert-icon">${icon}</div>
      <div class="budget-alert-content">
        <div class="budget-alert-text">${text}</div>
        <div class="budget-alert-progress">
          <div class="budget-alert-progress-bar ${level}" style="width:${Math.min(a.percentage, 100)}%"></div>
        </div>
      </div>
      <a href="/budgets" class="budget-alert-link" data-link>View Budgets</a>
    </div>`;
  }).join('');
  return `<div class="budget-alerts">${items}</div>`;
}

const SPLIT_SEPARATORS = /(\s+ar\s+|,|\s+ও\s+|\s+and\s+|\s*\+\s*)/i;

function attachExpenseForm(today) {
  const form = document.getElementById('expenseForm');
  const input = document.getElementById('description');
  const preview = document.getElementById('preview');
  const scanBtn = document.getElementById('scanBtn');
  const receiptInput = document.getElementById('receiptInput');
  if (!form || !input) return;

  let predictTimeout;
  let userModifiedPreview = false;
  let splitMode = false;

  // ── Receipt scanning ──
  scanBtn?.addEventListener('click', () => receiptInput?.click());

  receiptInput?.addEventListener('change', async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const submitBtn = document.getElementById('submitBtn');
    if (!preview) return;

    const compressed = await compressImage(file, 1200, 0.7);

    preview.innerHTML = `<div class="scanning-indicator"><span class="spinner"></span> Scanning receipt...</div>`;
    if (submitBtn) submitBtn.disabled = true;

    const formData = new FormData();
    formData.append('image', compressed, 'receipt.jpg');

    const res = await api.postForm('/api/scan_receipt', formData);
    if (submitBtn) submitBtn.disabled = false;
    e.target.value = '';

    if (!res.ok || !res.data?.items?.length) {
      const errMsg = res.data?.error || res.error || 'Could not read receipt';
      preview.innerHTML = `
        <div class="scan-error">
          <span class="scan-error-msg">❌ ${esc(errMsg)}</span>
          <button type="button" class="btn btn-outline btn-sm" onclick="document.getElementById('receiptInput').click()">Retake</button>
        </div>`;
      return;
    }

    splitItemsCache = res.data.items.map(item => ({
      description: item.description || '',
      amount: item.amount || 0,
      category: item.category || 'Other',
    }));
    splitMode = true;
    renderSplitPreview(splitItemsCache);

    input.value = splitItemsCache.map(i => i.description).join(', ');
    input.dispatchEvent(new Event('input'));

    if (submitBtn) {
      submitBtn.querySelector('.btn-text').textContent = `Add All (${splitItemsCache.length})`;
    }
  });

  input.addEventListener('input', () => {
    clearTimeout(predictTimeout);
    splitMode = false;
    userModifiedPreview = false;
    const val = input.value.trim();
    if (val.length < 2) { preview.innerHTML = ''; return; }
    predictTimeout = setTimeout(() => predictExpense(val), 600);
  });

  async function predictExpense(description) {
    if (preview.querySelector('.split-preview-card')) return;
    const res = await api.post('/api/predict_expense', { description });
    if (!res.ok || !res.data.category) return;
    const data = res.data;
    const catColor = data.color || '#6b7280';
    preview.innerHTML = `
      <div class="preview-card editable-preview">
        <div class="preview-field">
          <label class="preview-field-label">Category</label>
          <select class="preview-category-select" style="border-color: ${catColor}40;">
            ${buildCategoryOptions(data.category)}
          </select>
        </div>
        <div class="preview-field preview-amount-field">
          <label class="preview-field-label">Amount (৳)</label>
          <div class="preview-amount-input-wrap">
            <span class="preview-currency-sign">৳</span>
            <input type="number" class="preview-amount-input" step="0.01" min="0" value="${data.amount.toFixed(2)}">
          </div>
        </div>
      </div>`;
    preview.querySelectorAll('select, input').forEach(el => {
      el.addEventListener('change', () => { userModifiedPreview = true; });
      el.addEventListener('input', () => { userModifiedPreview = true; });
    });

    // Check if description looks splittable
    if (SPLIT_SEPARATORS.test(description)) {
      const splitBtn = document.createElement('div');
      splitBtn.className = 'split-trigger';
      splitBtn.innerHTML = `<button type="button" class="btn btn-split" onclick="triggerSplit(this)">↔ Split found!</button>`;
      preview.appendChild(splitBtn);
    }
  }

  function getPreviewValues() {
    const s = preview.querySelector('.preview-category-select');
    const a = preview.querySelector('.preview-amount-input');
    return s && a ? { category: s.value, amount: parseFloat(a.value) || 0 } : null;
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('submitBtn');
    const btnText = btn.querySelector('.btn-text');
    const btnLoader = btn.querySelector('.btn-loader');
    btn.disabled = true;
    btnText.style.display = 'none';
    btnLoader.style.display = 'flex';

    // Bulk submit in split mode (also check DOM in case stray input event reset splitMode)
    if (splitMode || preview?.querySelector('.split-preview-card')) {
      const date = document.getElementById('date').value;
      const splitItems = getSplitItems();
      if (!splitItems.length) {
        showToast('No valid items to add', 'error');
        btn.disabled = false;
        btnText.style.display = 'inline';
        btnLoader.style.display = 'none';
        return;
      }
      const res = await api.post('/api/expenses/bulk', { date, items: splitItems });
      btn.disabled = false;
      btnText.style.display = 'inline';
      btnLoader.style.display = 'none';
      if (!res.ok) { showToast(res.error, 'error'); return; }
      showToast(res.data.count + ' expenses added!', 'success');
      form.reset();
      preview.innerHTML = '';
      splitMode = false;
      splitItemsCache = [];
      userModifiedPreview = false;
      setTimeout(() => renderHome(), 400);
      return;
    }

    // Single expense submit (existing behavior)
    const fd = {
      date: document.getElementById('date').value,
      description: input.value,
    };
    const pv = getPreviewValues();
    if (pv) {
      fd.category = pv.category;
      fd.amount = pv.amount;
      if (userModifiedPreview) fd.learn = true;
    }

    const res = await api.post('/api/add_expense', fd);
    btn.disabled = false;
    btnText.style.display = 'inline';
    btnLoader.style.display = 'none';

    if (!res.ok) { showToast(res.error, 'error'); return; }
    showToast('Expense added!', 'success');
    showBudgetToastAlerts(res.data.budget_alerts);
    form.reset();
    preview.innerHTML = '';
    splitMode = false;
    splitItemsCache = [];
    userModifiedPreview = false;

    if (res.data.date === getTodayStr()) {
      addExpenseToList(res.data);
      updateTodayTotal(res.data.amount);
    } else {
      setTimeout(() => renderHome(), 800);
    }
  });
}


function getTodayStr() {
  return new Date().toISOString().split('T')[0];
}


// ── Split helpers (global for onclick) ──

let splitItemsCache = [];

async function triggerSplit(btnEl) {
  const input = document.getElementById('description');
  if (!input) return;
  const description = input.value.trim();
  if (!description) return;

  btnEl.disabled = true;
  btnEl.textContent = 'Splitting...';

  const res = await api.post('/api/split_expense', { description });
  if (!res.ok || !res.data.items || res.data.items.length < 2) {
    showToast('Could not split into multiple items', 'error');
    btnEl.disabled = false;
    btnEl.textContent = '↔ Split found!';
    return;
  }

  splitItemsCache = res.data.items;
  renderSplitPreview(res.data.items);
  splitMode = true;
}

function renderSplitPreview(items) {
  const preview = document.getElementById('preview');
  const submitBtn = document.getElementById('submitBtn');
  if (!preview) return;

  const total = items.reduce((s, i) => s + (i.amount || 0), 0);
  let rowsHtml = items.map((item, idx) => renderSplitItemRow(item, idx)).join('');

  preview.innerHTML = `
    <div class="split-preview-card">
      <div class="split-preview-rows" id="splitRows">
        ${rowsHtml}
      </div>
      <div class="split-preview-footer">
        <span class="split-preview-total">Total: ৳${total.toFixed(2)}</span>
        <button type="button" class="btn btn-danger btn-sm" onclick="cancelSplit()">Cancel</button>
      </div>
    </div>`;

  if (submitBtn) {
    submitBtn.querySelector('.btn-text').textContent = `Add All (${items.length})`;
  }
}

function renderSplitItemRow(item, idx) {
  const descSafe = item.description.replace(/'/g, "\\'");
  return `
    <div class="split-preview-row" data-idx="${idx}">
      <input type="text" class="split-item-desc" value="${esc(item.description)}"
             onchange="updateSplitItem(${idx},'desc',this.value)"
             placeholder="Description">
      <select class="split-item-cat" onchange="updateSplitItem(${idx},'cat',this.value)">
        ${buildCategoryOptions(item.category)}
      </select>
      <div class="split-item-amount-wrap">
        <span class="split-currency-sign">৳</span>
        <input type="number" class="split-item-amount" step="0.01" min="0" value="${item.amount.toFixed(2)}"
               onchange="updateSplitItem(${idx},'amt',parseFloat(this.value)||0)">
      </div>
      <button type="button" class="split-item-del" onclick="removeSplitItem(${idx})">&times;</button>
    </div>`;
}

function updateSplitItem(idx, field, value) {
  if (!splitItemsCache[idx]) return;
  if (field === 'desc') splitItemsCache[idx].description = value;
  else if (field === 'cat') splitItemsCache[idx].category = value;
  else if (field === 'amt') splitItemsCache[idx].amount = value;
  updateSplitTotal();
}

function removeSplitItem(idx) {
  splitItemsCache.splice(idx, 1);
  if (splitItemsCache.length < 2) {
    cancelSplit();
    return;
  }
  const container = document.getElementById('splitRows');
  if (container) {
    container.innerHTML = splitItemsCache.map((item, i) => renderSplitItemRow(item, i)).join('');
  }
  updateSplitTotal();
  const submitBtn = document.getElementById('submitBtn');
  if (submitBtn) {
    submitBtn.querySelector('.btn-text').textContent = `Add All (${splitItemsCache.length})`;
  }
}

function updateSplitTotal() {
  const footer = document.querySelector('.split-preview-footer');
  if (!footer) return;
  const total = splitItemsCache.reduce((s, i) => s + (i.amount || 0), 0);
  const el = footer.querySelector('.split-preview-total');
  if (el) el.textContent = `Total: ৳${total.toFixed(2)}`;
}

function cancelSplit() {
  splitMode = false;
  splitItemsCache = [];
  const preview = document.getElementById('preview');
  if (preview) preview.innerHTML = '';
  const submitBtn = document.getElementById('submitBtn');
  if (submitBtn) submitBtn.querySelector('.btn-text').textContent = 'Add Expense';
}

function getSplitItems() {
  return splitItemsCache.filter(i => i.description.trim() && i.amount > 0);
}

function compressImage(file, maxDim, quality) {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => resolve(file), 10000);
    const reader = new FileReader();
    reader.onload = (e) => {
      const img = new Image();
      img.onerror = () => { clearTimeout(timeout); resolve(file); };
      img.onload = () => {
        clearTimeout(timeout);
        let { width, height } = img;
        if (width > maxDim || height > maxDim) {
          const ratio = Math.min(maxDim / width, maxDim / height);
          width = Math.round(width * ratio);
          height = Math.round(height * ratio);
        }
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0, width, height);
        canvas.toBlob((blob) => {
          if (blob) resolve(new File([blob], 'receipt.jpg', { type: 'image/jpeg' }));
          else { clearTimeout(timeout); resolve(file); }
        }, 'image/jpeg', quality);
      };
      img.src = e.target.result;
    };
    reader.onerror = () => { clearTimeout(timeout); resolve(file); };
    reader.readAsDataURL(file);
  });
}

function addExpenseToList(expense) {
  const container = document.getElementById('todayExpenses');
  if (!container) return;
  const empty = container.querySelector('.empty-state');
  if (empty) empty.remove();
  const el = document.createElement('div');
  el.innerHTML = makeExpenseItem(expense);
  container.insertBefore(el.firstElementChild, container.firstChild);
}

function updateTodayTotal(amount) {
  const totalEl = document.querySelector('.stats-grid .stat-card:first-child .stat-value');
  if (totalEl) {
    const cur = parseFloat(totalEl.textContent.replace(/[৳,]/g, '')) || 0;
    totalEl.textContent = `৳${(cur + amount).toFixed(2)}`;
  }
  const cntEl = document.querySelector('.stats-grid .stat-card:last-child .stat-value');
  if (cntEl) cntEl.textContent = parseInt(cntEl.textContent) + 1;
}

// ── Dashboard ──
let expandedCategory = null;

async function renderDashboard(params) {
  setLayout('app');
  document.title = 'Dashboard - Expense Tracker';
  const app = document.getElementById('app');
  const now = new Date();
  const year = parseInt(params.year) || now.getFullYear();
  const month = parseInt(params.month) || now.getMonth() + 1;
  const page = parseInt(params.page) || 1;
  const qs = `year=${year}&month=${month}&page=${page}` +
    (params.search ? `&search=${encodeURIComponent(params.search)}` : '') +
    (params.user_id ? `&user_id=${params.user_id}` : '');

  const [dashRes, forecastRes] = await Promise.all([
    api.get(`/api/dashboard?${qs}`),
    (now.getFullYear() === year && now.getMonth() + 1 === month)
      ? api.get('/api/forecast')
      : Promise.resolve(null),
  ]);
  if (!dashRes.ok) { handleAuthError(dashRes); return; }
  const d = dashRes.data;
  const fc = forecastRes?.ok ? forecastRes.data : null;
  window.categoryColors = d.category_colors;
  expandedCategory = null;
  const monthNames = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  const monthAbbr = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  // Category table rows
  let catRows = d.category_totals.map(c => {
    const pct = d.month_total > 0 ? (c.total / d.month_total * 100) : 0;
    const color = d.category_colors[c.category] || '#6b7280';
    return `<tr class="category-row" data-category="${esc(c.category)}" onclick="toggleCategoryExpansion('${esc(c.category)}')">
      <td><span class="category-dot" style="background:${color}"></span>${esc(c.category)}</td>
      <td>৳${Number(c.total).toFixed(2)}</td>
      <td>${c.count}</td>
      <td>
        <div class="progress-bar"><div class="progress-fill" style="width:${pct}%;background:${color}"></div></div>
        <span class="progress-text">${pct.toFixed(1)}%</span>
      </td>
    </tr>`;
  }).join('');
  if (!catRows) catRows = '<tr><td colspan="4" class="empty-state">No data for this period</td></tr>';

  // Expense list
  const expBody = d.month_expenses.length
    ? makeDateGroups(d.month_expenses)
    : '<div class="empty-state"><p>No expenses for this period</p></div>';

  // User filter
  let userFilterHtml = '';
  if (d.users_list && d.users_list.length) {
    const opts = d.users_list.map(u =>
      `<option value="${u.id}" ${d.filter_user_id === u.id ? 'selected' : ''}>${esc(u.username)}</option>`
    ).join('');
    userFilterHtml = `
      <div class="user-filter">
        <select id="userFilter" onchange="changePeriod()">
          <option value="">All Users</option>
          ${opts}
        </select>
      </div>`;
  }

  // ── Forecast card ──
  let forecastHtml = '';
  if (fc) {
    const statusIcon = { over: '🚨', warning: '⚠️', under: '✅', no_budget: '📊' };
    const statusClass = fc.status === 'over' ? 'over' : fc.status === 'warning' ? 'warning' : fc.status === 'under' ? 'under' : 'no_budget';
    const vsMonthHtml = fc.vs_last_month
      ? `<span class="forecast-vs ${fc.vs_last_month.direction}">${fc.vs_last_month.direction === 'up' ? '↑' : '↓'} ${Math.abs(fc.vs_last_month.pct)}% vs last month</span>`
      : '';
    const budgetHtml = fc.overall_budget != null ? `৳${Number(fc.overall_budget).toLocaleString(undefined, {minimumFractionDigits:0, maximumFractionDigits:0})}` : '—';
    const barPct = fc.overall_budget && fc.overall_budget > 0
      ? Math.min((fc.projected / fc.overall_budget) * 100, 100) : 0;
    const dayPct = (fc.days_elapsed / fc.days_in_month) * 100;

    // AI insights
    const ai = fc.ai || {};
    const confDot = ai.confidence === 'high' ? '🟢' : ai.confidence === 'medium' ? '🟡' : '🔴';
    const confLabel = ai.confidence === 'high' ? 'High' : ai.confidence === 'medium' ? 'Medium' : 'Low';
    const rangeLow = ai.best_case != null && ai.worst_case != null ? Math.min(ai.best_case, ai.worst_case) : null;
    const rangeHigh = ai.best_case != null && ai.worst_case != null ? Math.max(ai.best_case, ai.worst_case) : null;
    const rangeHtml = (rangeLow != null && rangeHigh != null && rangeLow !== rangeHigh)
      ? `<div class="forecast-range">Range: ৳${Number(rangeLow).toLocaleString()} – ৳${Number(rangeHigh).toLocaleString()}</div>`
      : '';
    const reasoningHtml = ai.reasoning
      ? `<div class="forecast-reasoning">💡 ${esc(ai.reasoning)}</div>`
      : '';
    const notesHtml = ai.notes
      ? `<div class="forecast-notes">${esc(ai.notes)}</div>`
      : '';

    forecastHtml = `
      <div class="card forecast-card">
        <div class="forecast-header">
          <h2 class="card-title">📈 Spending Forecast</h2>
          ${vsMonthHtml}
          <span class="forecast-confidence forecast-confidence-${ai.confidence || 'low'}">${confDot} ${confLabel}</span>
        </div>
        <div class="forecast-grid">
          <div class="forecast-metric">
            <div class="forecast-value">৳${Number(fc.spent_so_far).toLocaleString(undefined, {minimumFractionDigits:0, maximumFractionDigits:0})}</div>
            <div class="forecast-label">Spent so far</div>
          </div>
          <div class="forecast-metric">
            <div class="forecast-value">৳${Number(fc.daily_avg).toLocaleString(undefined, {minimumFractionDigits:0, maximumFractionDigits:0})}</div>
            <div class="forecast-label">Avg / day</div>
          </div>
          <div class="forecast-metric">
            <div class="forecast-value forecast-projected">৳${Number(fc.projected).toLocaleString(undefined, {minimumFractionDigits:0, maximumFractionDigits:0})}</div>
            <div class="forecast-label">Projected</div>
          </div>
          <div class="forecast-metric">
            <div class="forecast-value">${budgetHtml}</div>
            <div class="forecast-label">Budget</div>
          </div>
        </div>
        ${rangeHtml}
        ${fc.overall_budget ? `
        <div class="forecast-progress">
          <div class="forecast-bar-track">
            <div class="forecast-bar-fill" style="width:${barPct}%"></div>
            <div class="forecast-bar-marker" style="left:${dayPct}%"></div>
          </div>
          <div class="forecast-bar-labels">
            <span>Day ${fc.days_elapsed}</span>
            <span>${fc.days_in_month} days</span>
          </div>
        </div>` : ''}
        <div class="forecast-status forecast-status-${statusClass}">
          <span>${statusIcon[fc.status] || '📊'}</span>
          <span>${esc(fc.status_text)}</span>
        </div>
        ${reasoningHtml}
        ${notesHtml}
        ${fc.status === 'no_budget' ? `<a href="/budgets" data-link class="forecast-set-budget">Set a budget →</a>` : ''}
      </div>`;
  }

  // Pagination base
  const pagBase = `/dashboard?year=${year}&month=${month}` +
    (d.search_query ? `&search=${encodeURIComponent(d.search_query)}` : '') +
    (d.filter_user_id ? `&user_id=${d.filter_user_id}` : '') + '&';

  app.innerHTML = `
    <div class="dashboard-header">
      <h1>Dashboard</h1>
      <div class="dashboard-controls">
        <div class="date-selector">
          <select id="yearSelect" onchange="changePeriod()">
            ${d.years.map(y => `<option value="${y}" ${y === year ? 'selected' : ''}>${y}</option>`).join('')}
          </select>
          <select id="monthSelect" onchange="changePeriod()">
            ${monthAbbr.map((m, i) => `<option value="${i+1}" ${i+1 === month ? 'selected' : ''}>${m}</option>`).join('')}
          </select>
        </div>
        ${userFilterHtml}
      </div>
    </div>

    <div class="dashboard-toolbar">
      <div class="stat-card stat-card-large" style="margin-bottom:0;">
        <div class="stat-label">Total for ${monthNames[month-1]} ${year}</div>
        <div class="stat-value">৳${Number(d.month_total).toFixed(2)}</div>
      </div>
      <form class="search-form" id="searchForm">
        <input type="hidden" name="year" value="${year}">
        <input type="hidden" name="month" value="${month}">
        ${d.filter_user_id ? `<input type="hidden" name="user_id" value="${d.filter_user_id}">` : ''}
        <div class="search-bar">
          <input type="text" id="searchInput" placeholder="Search expenses..." value="${esc(d.search_query)}" class="search-input">
          <button type="submit" class="btn btn-primary btn-search">Search</button>
          ${d.search_query ? `<a href="/dashboard?year=${year}&month=${month}${d.filter_user_id ? `&user_id=${d.filter_user_id}` : ''}" data-link class="btn btn-outline btn-clear">Clear</a>` : ''}
        </div>
      </form>
      <div class="export-buttons">
        <a href="/api/export/csv?year=${year}&month=${month}${d.filter_user_id ? `&user_id=${d.filter_user_id}` : ''}${d.search_query ? `&search=${encodeURIComponent(d.search_query)}` : ''}" class="btn-export" title="Export as CSV"><span class="export-icon">📄</span> CSV</a>
        <a href="/api/export/xlsx?year=${year}&month=${month}${d.filter_user_id ? `&user_id=${d.filter_user_id}` : ''}${d.search_query ? `&search=${encodeURIComponent(d.search_query)}` : ''}" class="btn-export" title="Export as Excel"><span class="export-icon">📊</span> Excel</a>
        <a href="/api/export/pdf?year=${year}&month=${month}${d.filter_user_id ? `&user_id=${d.filter_user_id}` : ''}${d.search_query ? `&search=${encodeURIComponent(d.search_query)}` : ''}" class="btn-export" title="Export as PDF"><span class="export-icon">📕</span> PDF</a>
      </div>
    </div>

    ${forecastHtml}

    <div class="dashboard-grid">
      <div class="card chart-card">
        <h2 class="card-title">Category Breakdown</h2>
        <div class="chart-container"><canvas id="categoryChart"></canvas></div>
      </div>
      <div class="card chart-card">
        <h2 class="card-title">Monthly Trend</h2>
        <div class="chart-container"><canvas id="monthlyChart"></canvas></div>
      </div>
    </div>

    <div class="card">
      <h2 class="card-title">Category Details</h2>
      <div class="table-container">
        <table class="data-table" id="categoryTable">
          <thead><tr><th>Category</th><th>Amount</th><th>Transactions</th><th>Percentage</th></tr></thead>
          <tbody>${catRows}</tbody>
        </table>
      </div>
    </div>

    <div class="card">
      <div class="card-header-row">
        <h2 class="card-title" style="margin-bottom:0;">Expenses for ${monthNames[month-1]} ${year}</h2>
        <span class="expense-count">${d.total} expense(s)</span>
      </div>
      <div class="expense-list">${expBody}</div>
      ${makePagination(pagBase, d.page, d.total_pages)}
    </div>`;

  initCharts(d.category_totals, d.monthly_totals, d.category_colors);

  document.getElementById('searchForm')?.addEventListener('submit', (e) => {
    e.preventDefault();
    const s = document.getElementById('searchInput')?.value.trim();
    let url = `/dashboard?year=${year}&month=${month}`;
    if (s) url += `&search=${encodeURIComponent(s)}`;
    if (d.filter_user_id) url += `&user_id=${d.filter_user_id}`;
    navigate(url);
  });
}

function changePeriod() {
  const y = document.getElementById('yearSelect')?.value;
  const m = document.getElementById('monthSelect')?.value;
  if (!y || !m) return;
  let url = `/dashboard?year=${y}&month=${parseInt(m)}`;
  const uf = document.getElementById('userFilter');
  if (uf && uf.value) url += `&user_id=${uf.value}`;
  navigate(url);
}

async function toggleCategoryExpansion(category) {
  const existingRow = document.querySelector('.category-expanded-row');
  const tbody = document.querySelector('#categoryTable tbody');
  if (!tbody) return;

  if (expandedCategory === category && existingRow) {
    existingRow.remove();
    expandedCategory = null;
    tbody.querySelectorAll('.category-active').forEach(el => el.classList.remove('category-active'));
    return;
  }

  existingRow?.remove();
  tbody.querySelectorAll('.category-active').forEach(el => el.classList.remove('category-active'));

  expandedCategory = category;

  const rows = tbody.querySelectorAll('.category-row');
  let targetRow = null;
  for (const row of rows) {
    if (row.dataset.category === category) {
      targetRow = row;
      row.classList.add('category-active');
      break;
    }
  }
  if (!targetRow) return;

  const loader = document.createElement('tr');
  loader.className = 'category-expanded-row';
  loader.innerHTML = `<td colspan="4"><div class="category-expanded-content"><div class="page-loader" style="min-height:60px"><div class="spinner-lg"></div></div></div></td>`;
  targetRow.insertAdjacentElement('afterend', loader);

  const year = document.getElementById('yearSelect')?.value;
  const month = document.getElementById('monthSelect')?.value;
  const uf = document.getElementById('userFilter');
  const userId = uf?.value;

  let url = `/api/expenses/category-breakdown?year=${year}&month=${month}&category=${encodeURIComponent(category)}&per_page=500`;
  if (userId) url += `&user_id=${userId}`;

  const res = await api.get(url);
  if (!res.ok) {
    loader.innerHTML = `<td colspan="4"><div class="category-expanded-content"><div class="empty-state"><p>${esc(res.error)}</p></div></div></td>`;
    return;
  }

  const d = res.data;
  const body = d.expenses.length
    ? makeDateGroups(d.expenses)
    : '<div class="empty-state"><p>No expenses for this category</p></div>';

  loader.innerHTML = `<td colspan="4"><div class="category-expanded-content"><div class="category-expense-list">${body}</div></div></td>`;
}

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function initCharts(categoryTotals, monthlyTotals, colors) {
  chartInstances.forEach(c => c.destroy());
  chartInstances = [];
  const borderColor = cssVar('--border') || '#e2e8f0';
  const primaryColor = cssVar('--primary') || '#6366f1';

  const catCtx = document.getElementById('categoryChart');
  if (catCtx && categoryTotals && categoryTotals.length) {
    const labels = categoryTotals.map(c => c.category);
    const data = categoryTotals.map(c => c.total);
    const col = labels.map(l => colors[l] || '#6b7280');
    chartInstances.push(new Chart(catCtx, {
      type: 'doughnut',
      data: { labels, datasets: [{ data, backgroundColor: col, borderWidth: 0, hoverOffset: 8 }] },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { position: 'bottom', labels: { padding: 16, usePointStyle: true, pointStyleWidth: 10, font: { size: 12 }, color: cssVar('--text-secondary') } },
          tooltip: { callbacks: { label: (ctx) => {
            const val = ctx.parsed || 0;
            const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
            return `${ctx.label}: ৳${val.toFixed(2)} (${((val/total)*100).toFixed(1)}%)`;
          }}}
        }
      }
    }));
  }

  const monCtx = document.getElementById('monthlyChart');
  if (monCtx && monthlyTotals && monthlyTotals.length) {
    const sorted = [...monthlyTotals].reverse();
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    const labels = sorted.map(m => {
      const [y, mo] = m.month.split('-');
      return `${months[parseInt(mo)-1]} ${y}`;
    });
    const data = sorted.map(m => m.total);
    chartInstances.push(new Chart(monCtx, {
      type: 'bar',
      data: { labels, datasets: [{ label: 'Monthly Total', data, backgroundColor: primaryColor, borderRadius: 6, borderSkipped: false }] },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => `৳${ctx.parsed.y.toFixed(2)}` } } },
        scales: {
          y: { beginAtZero: true, ticks: { callback: (v) => `৳${v}`, color: cssVar('--text-secondary') }, grid: { color: borderColor } },
          x: { ticks: { color: cssVar('--text-secondary') }, grid: { display: false } }
        }
      }
    }));
  }
}

// ── Profile ──
async function renderProfile() {
  setLayout('app');
  document.title = 'Profile - Expense Tracker';
  const app = document.getElementById('app');

  const res = await api.get('/api/profile');
  if (!res.ok) { handleAuthError(res); return; }
  const s = res.data;

  app.innerHTML = `
    <div class="card profile-card">
      <div class="profile-header">
        <div class="profile-avatar">${esc(s.username[0].toUpperCase())}</div>
        <div>
          <h1>${esc(s.username)}</h1>
          <span class="role-badge ${s.role === 'superuser' ? 'role-superuser' : ''}">${esc(s.role)}</span>
        </div>
      </div>

      <div class="profile-section">
        <h2>Account Info</h2>
        <div class="profile-info-grid">
          <div class="info-item">
            <span class="info-label">Username</span>
            <span class="info-value">${esc(s.username)}</span>
          </div>
          <div class="info-item">
            <span class="info-label">Role</span>
            <span class="info-value">${esc(s.role)}</span>
          </div>
          <div class="info-item">
            <span class="info-label">Member Since</span>
            <span class="info-value">${esc(s.member_since)}</span>
          </div>
          <div class="info-item">
            <span class="info-label">Total Expenses</span>
            <span class="info-value">${s.total_count}</span>
          </div>
          <div class="info-item">
            <span class="info-label">Total Amount Spent</span>
            <span class="info-value">৳${Number(s.total_amount).toFixed(2)}</span>
          </div>
        </div>
      </div>

      <div class="profile-section">
        <h2>Change Password</h2>
        <form id="pwForm" class="password-form">
          <div id="pwError" class="alert alert-error" style="display:none;"></div>
          <div id="pwSuccess" class="alert alert-success" style="display:none;"></div>
          <div class="form-group">
            <label for="pwCurrent">Current Password</label>
            <input type="password" id="pwCurrent" name="current_password" required>
          </div>
          <div class="form-group">
            <label for="pwNew">New Password</label>
            <input type="password" id="pwNew" name="new_password" required minlength="4">
          </div>
          <div class="form-group">
            <label for="pwConfirm">Confirm New Password</label>
            <input type="password" id="pwConfirm" name="confirm_password" required>
          </div>
          <button type="submit" class="btn btn-primary">Update Password</button>
        </form>
      </div>
    </div>`;

  document.getElementById('pwForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const errEl = document.getElementById('pwError');
    const sucEl = document.getElementById('pwSuccess');
    errEl.style.display = 'none';
    sucEl.style.display = 'none';

    const res = await api.post('/api/profile/change-password', {
      current_password: document.getElementById('pwCurrent').value,
      new_password: document.getElementById('pwNew').value,
      confirm_password: document.getElementById('pwConfirm').value,
    });
    if (!res.ok) {
      errEl.textContent = res.error;
      errEl.style.display = '';
      return;
    }
    sucEl.textContent = 'Password updated successfully';
    sucEl.style.display = '';
    document.getElementById('pwForm').reset();
  });
}

// ── Admin Users ──
// ── Budgets ──

function catDisplayName(cat) {
  return cat === '__overall__' ? 'Overall' : cat;
}

async function renderBudgets() {
  setLayout('app');
  document.title = 'Budgets - Expense Tracker';
  const app = document.getElementById('app');
  app.innerHTML = '<div class="budget-page page-loader"><div class="spinner-lg"></div></div>';

  const [budgetsRes, catRes] = await Promise.all([
    api.get('/api/budgets'),
    api.get('/api/categories'),
  ]);
  if (!budgetsRes.ok) { handleAuthError(budgetsRes); return; }

  const budgets = budgetsRes.data.budgets || [];
  const defaultCategories = ['Food','Transport','Shopping','Bills','Entertainment','Health','Education','Rent','Dining Out','Fruits','Groceries','Travel','Personal Care','Gifts','Investment','Savings','Other'];
  const allCategories = catRes.ok ? (catRes.data.categories || defaultCategories) : (Object.keys(window.categoryColors || {}).length ? Object.keys(window.categoryColors || {}) : defaultCategories);

  // Separate overall budget from per-category budgets
  const overallBudget = budgets.find(b => b.category === '__overall__');
  const catBudgets = budgets.filter(b => b.category !== '__overall__');
  const setCatCategories = new Set(catBudgets.map(b => b.category));
  const availableCategories = allCategories.filter(c => !setCatCategories.has(c));

  function budgetCard(b, isOverall) {
    const pct = b.percentage || 0;
    const barClass = pct >= 100 ? 'danger' : pct >= 80 ? 'warning' : 'safe';
    const spentClass = pct >= 100 ? 'danger' : pct >= 80 ? 'warning' : '';
    const name = isOverall ? 'Overall' : b.category;
    const dotColor = isOverall ? '#6366f1' : (b.color || '#6b7280');
    return `<div class="budget-card ${isOverall ? 'budget-card-overall' : ''}">
      <div class="budget-card-top">
        <div class="budget-card-category">
          <span class="budget-category-dot" style="background:${dotColor}"></span>
          ${isOverall ? '📊 ' : ''}${esc(name)}
        </div>
        <div class="budget-card-actions">
          <span class="budget-amount">৳${Number(b.amount).toFixed(2)}/month</span>
          <button class="btn btn-danger btn-sm" onclick="deleteBudget(${b.id})">Delete</button>
        </div>
      </div>
      <div class="budget-spent ${spentClass}">
        Spent: ৳${Number(b.spent || 0).toFixed(2)} (${pct}%)
      </div>
      <div class="budget-progress">
        <div class="budget-progress-bar ${barClass}" style="width:${Math.min(pct, 100)}%"></div>
      </div>
    </div>`;
  }

  app.innerHTML = `
    <div class="budget-page">
      <div class="budget-header">
        <h2>💰 Budgets</h2>
      </div>

      <!-- Overall budget section -->
      <div class="budget-form" id="overallBudgetForm">
        <div class="budget-form-label">Total Monthly Spending Limit</div>
        <div class="budget-form-row">
          <input type="number" id="overallBudgetAmount" placeholder="Overall budget (৳)" min="1" step="0.01" value="${overallBudget ? overallBudget.amount : ''}">
          <button class="btn btn-primary" onclick="setOverallBudget()">${overallBudget ? 'Update' : 'Set'} Overall Budget</button>
          ${overallBudget ? `<button class="btn btn-danger btn-sm" onclick="deleteBudget(${overallBudget.id})">Remove</button>` : ''}
        </div>
      </div>

      ${overallBudget ? `<div class="budget-list overall-section">${budgetCard(overallBudget, true)}</div>` : ''}

      <hr class="budget-divider">

      <!-- Per-category budget section -->
      <div class="budget-form" id="budgetForm" style="${availableCategories.length ? '' : 'display:none'}">
        <div class="budget-form-label">Per-Category Budgets</div>
        <div class="budget-form-row">
          <select id="budgetCategory">
            <option value="">Select category...</option>
            ${availableCategories.map(c => `<option value="${c}">${c}</option>`).join('')}
          </select>
          <input type="number" id="budgetAmount" placeholder="Monthly budget (৳)" min="1" step="0.01">
          <button class="btn btn-primary" onclick="setBudget()">Set Budget</button>
        </div>
      </div>
      <div class="budget-list">
        ${catBudgets.length ? catBudgets.map(b => budgetCard(b, false)).join('') : '<div class="budget-empty"><p>No per-category budgets set yet.</p><p class="text-secondary">Use the form above or ask AI to set budgets for individual categories.</p></div>'}
      </div>
    </div>`;
}

async function setOverallBudget() {
  const amtEl = document.getElementById('overallBudgetAmount');
  const amount = parseFloat(amtEl?.value);
  if (!amount || amount <= 0) { showToast('Please enter a valid amount', 'error'); return; }
  const res = await api.post('/api/budgets/set', { category: '__overall__', amount });
  if (!res.ok) { showToast(res.error || 'Failed to set overall budget', 'error'); return; }
  showToast(`Overall budget set to ৳${amount.toFixed(2)}`, 'success');
  renderBudgets();
}

async function setBudget() {
  const catEl = document.getElementById('budgetCategory');
  const amtEl = document.getElementById('budgetAmount');
  const category = catEl?.value;
  const amount = parseFloat(amtEl?.value);
  if (!category) { showToast('Please select a category', 'error'); return; }
  if (!amount || amount <= 0) { showToast('Please enter a valid amount', 'error'); return; }
  const res = await api.post('/api/budgets/set', { category, amount });
  if (!res.ok) { showToast(res.error || 'Failed to set budget', 'error'); return; }
  showToast(`${catDisplayName(category)} budget set to ৳${amount.toFixed(2)}`, 'success');
  renderBudgets();
}

async function deleteBudget(id) {
  if (!confirm('Delete this budget?')) return;
  const res = await api.del(`/api/budgets/delete/${id}`);
  if (!res.ok) { showToast(res.error || 'Failed to delete budget', 'error'); return; }
  showToast('Budget deleted', 'success');
  renderBudgets();
}

// ── Admin ──

async function renderAdminUsers() {
  if (currentUser?.role !== 'superuser') { navigate('/'); return; }
  setLayout('app');
  document.title = 'Admin - Expense Tracker';
  const app = document.getElementById('app');

  const res = await api.get('/api/admin/users');
  if (!res.ok) { handleAuthError(res); return; }
  const { users } = res.data;

  const rows = users.map(u => `
    <tr>
      <td>
        <span class="user-name">${esc(u.username)}</span>
        ${u.id === currentUser.id ? '<span class="you-badge">(you)</span>' : ''}
      </td>
      <td><span class="role-badge ${u.role === 'superuser' ? 'role-superuser' : ''}">${esc(u.role)}</span></td>
      <td class="text-muted">${u.expense_count}</td>
      <td class="actions-cell">
        ${u.id !== currentUser.id ? `
          <button class="btn btn-small btn-outline" onclick="adminChangeRole(${u.id})">${u.role === 'superuser' ? 'Demote' : 'Promote'}</button>
          <button class="btn btn-small btn-danger" onclick="adminDeleteUser(${u.id})">Delete</button>
        ` : '<span class="text-muted">—</span>'}
      </td>
    </tr>
  `).join('');

  app.innerHTML = `
    <div class="card">
      <h1 class="card-title" style="font-size:24px;">User Management</h1>
      <div class="table-container">
        <table class="data-table">
          <thead><tr><th>Username</th><th>Role</th><th>Expenses</th><th>Actions</th></tr></thead>
          <tbody>${rows || '<tr><td colspan="4" class="empty-state">No users</td></tr>'}</tbody>
        </table>
      </div>
    </div>`;
}

async function adminChangeRole(userId) {
  const res = await api.post(`/api/admin/users/${userId}/change-role`);
  if (!res.ok) { showToast(res.error, 'error'); return; }
  showToast('Role updated', 'success');
  renderAdminUsers();
}

async function adminDeleteUser(userId) {
  if (!confirm('Delete this user and all their expenses?')) return;
  const res = await api.post(`/api/admin/users/${userId}/delete`);
  if (!res.ok) { showToast(res.error, 'error'); return; }
  showToast('User deleted', 'success');
  renderAdminUsers();
}

// ── Admin Notifications ──

async function renderAdminNotifications() {
  if (currentUser?.role !== 'superuser') { navigate('/'); return; }
  setLayout('app');
  document.title = 'Daily Digest - Expense Tracker';
  const app = document.getElementById('app');

  app.innerHTML = `
    <div class="card">
      <h1 class="card-title" style="font-size:24px;">Daily Digest</h1>
      <p class="text-muted" style="margin-bottom:16px;">Send the daily summary push notification to all subscribed users.</p>
      <button class="btn btn-primary" onclick="adminTriggerDigest()" id="digestBtn">📤 Send Daily Digest Now</button>
      <div id="digestResult" style="margin-top:12px;"></div>
    </div>`;
}

async function adminTriggerDigest() {
  const btn = document.getElementById('digestBtn');
  const result = document.getElementById('digestResult');
  btn.disabled = true;
  btn.textContent = 'Sending...';
  result.innerHTML = '';

  const res = await api.post('/api/admin/notifications/daily-digest/trigger');
  btn.disabled = false;
  btn.textContent = '📤 Send Daily Digest Now';

  if (!res.ok) {
    result.innerHTML = `<div class="alert alert-error">${esc(res.error)}</div>`;
    return;
  }
  const d = res.data;
  let details = `<div class="alert alert-success">Digest sent to <strong>${d.sent}</strong> user(s)</div>`;
  if (d.failed > 0) {
    details += `<div class="alert alert-warning">${d.failed} user(s) had no subscriptions</div>`;
  }
  if (d.vapid_loaded === false || d.webpush_available === false) {
    details += `<div class="alert alert-error">Push system not healthy: VAPID loaded=${d.vapid_loaded}, webpush=${d.webpush_available}</div>`;
  }
  if (d.subscribed === 0) {
    details += `<div class="alert alert-warning">No users have push subscriptions. Users need to visit the site and grant notification permission.</div>`;
  }
  details += `<p class="text-muted" style="font-size:13px;margin-top:8px;">Subscribed users: ${d.subscribed} | VAPID: ${d.vapid_loaded ? '✅' : '❌'} | WebPush: ${d.webpush_available ? '✅' : '❌'}</p>`;
  result.innerHTML = details;
}

// ── Auth Error ──

function handleAuthError(res) {
  if (res.error === 'Unauthorized') {
    currentUser = null;
    navigate('/login');
    return;
  }
  showToast(res.error, 'error');
}

// ── NL Q&A Chat ──

let chatMessages = [];

function initChatCard() {
  const input = document.getElementById('chatInput');
  const sendBtn = document.getElementById('chatSendBtn');
  const micBtn = document.getElementById('voiceBtn');
  const attachBtn = document.getElementById('chatAttachBtn');
  const chatCameraInput = document.getElementById('chatCameraInput');
  const chatGalleryInput = document.getElementById('chatGalleryInput');

  function toggleInputButtons() {
    const hasText = input && input.value.trim().length > 0;
    if (micBtn) micBtn.style.display = hasText ? 'none' : 'flex';
    if (sendBtn) sendBtn.style.display = hasText ? 'flex' : 'none';
  }

  if (input) {
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendChatMessage();
      }
    });
    input.addEventListener('input', () => {
      input.style.height = 'auto';
      input.style.height = Math.min(input.scrollHeight, 300) + 'px';
      toggleInputButtons();
    });
    input.addEventListener('focus', () => {
      const container = document.getElementById('chatMessages');
      if (container) container.scrollTop = container.scrollHeight;
    });
    toggleInputButtons();
  }

  if (sendBtn) {
    sendBtn.addEventListener('click', sendChatMessage);
  }

  if (micBtn) {
    const hasNativeSpeech = !!(window.SpeechRecognition || window.webkitSpeechRecognition);
    const hasMediaRecorder = !!(navigator.mediaDevices?.getUserMedia);
    if (!hasNativeSpeech && !hasMediaRecorder) {
      micBtn.style.display = 'none';
    } else {
      micBtn.addEventListener('click', () => {
        if (voiceRecognition || voiceMediaRecorder) {
          stopVoiceInput();
        } else {
          startVoiceInput();
        }
      });
    }
  }

  // ── Attach button (opens gallery directly) ──
  if (attachBtn && chatGalleryInput) {
    attachBtn.addEventListener('click', () => chatGalleryInput.click());
  }

  // ── Collapse / expand ──
  const toggle = document.getElementById('aiChatToggle');
  const body = document.getElementById('aiChatBody');
  const icon = document.getElementById('aiChatCollapseIcon');
  if (toggle && body && icon) {
    const saved = localStorage.getItem('aiChatCollapsed');
    const isMobile = window.innerWidth <= 768;
    const collapsed = saved !== null ? saved === 'true' : isMobile;
    if (collapsed) {
      body.classList.add('chat-body-collapsed');
      icon.textContent = '▶';
    } else {
      body.classList.remove('chat-body-collapsed');
      icon.textContent = '▼';
    }
    toggle.addEventListener('click', () => {
      body.classList.toggle('chat-body-collapsed');
      const c = body.classList.contains('chat-body-collapsed');
      icon.textContent = c ? '▶' : '▼';
      localStorage.setItem('aiChatCollapsed', c);
    });
  }

  // ── Clear button ──
  const clearBtn = document.getElementById('chatClearBtn');
  if (clearBtn) {
    clearBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      clearChatMessages();
    });
  }

  chatCameraInput?.addEventListener('change', (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (file) chatScanReceipt(file, null);
  });
  chatGalleryInput?.addEventListener('change', (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (file) chatScanReceipt(file, null);
  });
}

async function chatScanReceipt(file, cropRect) {
  stopVoiceInput();

  let imageFile;
  if (cropRect) {
    const img = new Image();
    img.src = URL.createObjectURL(file);
    await new Promise(r => { img.onload = r; });
    const canvas = document.createElement('canvas');
    canvas.width = cropRect.w;
    canvas.height = cropRect.h;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(img, cropRect.x, cropRect.y, cropRect.w, cropRect.h, 0, 0, cropRect.w, cropRect.h);
    URL.revokeObjectURL(img.src);
    const blob = await new Promise(r => canvas.toBlob(r, 'image/jpeg', 0.85));
    imageFile = new File([blob], 'receipt-cropped.jpg', { type: 'image/jpeg' });
  } else {
    imageFile = file;
  }

  const compressed = await compressImage(imageFile, 1200, 0.7);

  addChatMessage('loading', '');
  const formData = new FormData();
  formData.append('image', compressed, 'receipt.jpg');
  const res = await api.postForm('/api/scan_receipt', formData);

  chatMessages = chatMessages.filter(m => m.type !== 'loading');
  renderChatMessages();

  if (!res.ok || !res.data?.items?.length) {
    showToast('Scan failed: ' + (res.data?.error || res.error || 'Could not read receipt'), 'error');
    return;
  }

  const items = res.data.items;
  const text = items.map(i => `${i.description} ৳${Number(i.amount).toFixed(2)}`).join(', ');
  const total = items.reduce((s, i) => s + Number(i.amount || 0), 0);
  const message = `Scanned receipt: ${text} (Total: ৳${total.toFixed(2)})`;

  const input = document.getElementById('chatInput');
  if (input) {
    input.value = message;
  }
  sendChatMessage();
}

let voiceRecognition = null;
let voiceSilenceTimer = null;
let voiceFinalTranscript = '';
let voiceMediaRecorder = null;
let voiceStream = null;
let voiceChunks = [];
let voiceIsNative = false;
let voiceActive = false;
let isSendingMessage = false;

function startVoiceInput() {
  const voiceBtn = document.getElementById('voiceBtn');
  const input = document.getElementById('chatInput');
  if (!input || !voiceBtn) return;

  voiceActive = true;
  const hasNativeSpeech = !!(window.SpeechRecognition || window.webkitSpeechRecognition);

  if (hasNativeSpeech) {
    startNativeVoice(input, voiceBtn);
  } else {
    startMediaRecorderVoice(input, voiceBtn);
  }
}

function startNativeVoice(input, voiceBtn) {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  voiceFinalTranscript = '';
  voiceIsNative = true;

  const recognition = new SpeechRecognition();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = 'en-US';

    recognition.onresult = (event) => {
    let interim = '';
    let final = '';
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const transcript = event.results[i][0].transcript;
      if (event.results[i].isFinal) {
        final += transcript;
      } else {
        interim += transcript;
      }
    }
    voiceFinalTranscript += final;
    input.value = voiceFinalTranscript + interim;
    const preview = document.getElementById('voicePreview');
    if (preview) {
      preview.textContent = voiceFinalTranscript || interim || '...';
    }

    clearTimeout(voiceSilenceTimer);
    voiceSilenceTimer = setTimeout(() => {
      if (voiceActive && input.value.trim()) {
        stopVoiceInput();
        sendChatMessage();
      }
    }, 1500);
  };

  recognition.onerror = (event) => {
    if (event.error === 'no-speech') return;
    if (event.error === 'aborted') return;
    showToast('Voice error: ' + event.error, 'error');
    stopVoiceInput();
  };

  recognition.onend = () => {
    if (voiceRecognition) {
      recognition.start();
    }
  };

  try {
    recognition.start();
    voiceRecognition = recognition;
    voiceBtn.classList.add('recording');
    voiceBtn.title = 'Stop recording';
    input.placeholder = 'Listening...';
    input.focus();
    const preview = document.getElementById('voicePreview');
    if (preview) { preview.style.display = 'block'; preview.textContent = 'Listening...'; }
  } catch (e) {
    showToast('Failed to start voice input', 'error');
  }
}

function startMediaRecorderVoice(input, voiceBtn) {
  voiceIsNative = false;

  const mimeTypes = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus'];
  let mimeType = '';
  for (const mt of mimeTypes) {
    if (MediaRecorder.isTypeSupported(mt)) {
      mimeType = mt;
      break;
    }
  }

  navigator.mediaDevices.getUserMedia({ audio: true })
    .then((stream) => {
      voiceStream = stream;
      voiceChunks = [];
      voiceMediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : {});

      voiceMediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) voiceChunks.push(e.data);
      };

      voiceMediaRecorder.onstop = () => {
        if (!voiceActive) return;
        const blob = new Blob(voiceChunks, { type: mimeType || 'audio/webm' });
        const formData = new FormData();
        formData.append('audio', blob, 'recording.' + (mimeType.includes('mp4') ? 'mp4' : 'webm'));

        voiceBtn.classList.add('sending');
        voiceBtn.textContent = '⏳';
        input.placeholder = 'Transcribing...';

        api.postForm('/api/transcribe', formData).then((res) => {
          voiceBtn.classList.remove('sending');
          voiceBtn.textContent = '🎤';
          if (res.ok && res.data.text) {
            input.value = res.data.text;
            sendChatMessage();
          } else {
            showToast('Transcription failed', 'error');
            input.placeholder = 'Ask a question...';
          }
        });
      };

      voiceMediaRecorder.start();
      voiceBtn.classList.add('recording');
      voiceBtn.title = 'Stop recording';
      input.placeholder = 'Recording...';
    })
    .catch((err) => {
      if (err.name === 'NotAllowedError') {
        showToast('Microphone permission denied', 'error');
      } else {
        showToast('Could not access microphone', 'error');
      }
    });
}

function stopVoiceInput() {
  clearTimeout(voiceSilenceTimer);
  voiceActive = false;

  if (voiceRecognition) {
    try {
      voiceRecognition.onresult = null;
      voiceRecognition.onerror = null;
      voiceRecognition.onend = null;
      voiceRecognition.stop();
    } catch (e) {}
    voiceRecognition = null;
  }

  if (voiceMediaRecorder && voiceMediaRecorder.state === 'recording') {
    voiceMediaRecorder.stop();
    voiceMediaRecorder = null;
  }

  if (voiceStream) {
    voiceStream.getTracks().forEach((t) => t.stop());
    voiceStream = null;
  }

  const voiceBtn = document.getElementById('voiceBtn');
  const input = document.getElementById('chatInput');

  if (voiceBtn) {
    voiceBtn.classList.remove('recording', 'sending');
    voiceBtn.textContent = '🎤';
    voiceBtn.title = 'Voice input';
  }
  if (input) {
    input.placeholder = 'Ask a question...';
  }
  const preview = document.getElementById('voicePreview');
  if (preview) { preview.style.display = 'none'; preview.textContent = ''; }
  voiceFinalTranscript = '';
  voiceChunks = [];
}

function _richCatColor(cat) {
  const colors = window.categoryColors || {};
  return colors[cat] || '#6b7280';
}

function renderRichAnswer(answer) {
  if (typeof answer === 'string') return highlightInline(answer);
  if (!answer || !answer.type) return highlightInline(String(answer));
  const t = answer.type;
  let h = '<div class="rich-answer">';

  if (t === 'budget') {
    const pct = Math.min(answer.pct || 0, 100);
    const cls = pct < 80 ? 'safe' : pct < 100 ? 'warn' : 'danger';
    const catHtml = answer.category ? `<span class="rich-cat-badge" style="background:${_richCatColor(answer.category)}20;color:${_richCatColor(answer.category)};border:1px solid ${_richCatColor(answer.category)}40">${esc(answer.category)}</span>` : '';
    h += `<div class="rich-total-hero"><div class="amount" style="color:${answer.remaining > 0 ? '#22c55e' : '#ef4444'}">${answer.remaining > 0 ? '✅' : '⚠️'} ৳${Number(answer.remaining).toFixed(2)}</div><div class="sub">${answer.remaining > 0 ? 'remaining' : 'overspent'}</div></div>`;
    h += `${catHtml}`;
    h += `<div class="rich-progress"><div class="rich-progress-fill ${cls}" style="width:${pct}%"></div></div>`;
    h += `<div class="rich-budget-stats"><div class="rich-budget-stat"><div class="value">৳${Number(answer.spent).toFixed(2)}</div><div class="label">Spent</div></div><div class="rich-budget-stat"><div class="value">৳${Number(answer.budget).toFixed(2)}</div><div class="label">Budget</div></div><div class="rich-budget-stat"><div class="value">${pct}%</div><div class="label">Used</div></div></div>`;
  } else if (t === 'pacing') {
    const de = answer.days_elapsed || 1;
    const dim = answer.days_in_month || 30;
    const dayPct = Math.min((de / dim) * 100, 100);
    h += `<div class="rich-pacing-grid">`;
    h += `<div class="rich-pacing-item"><span class="value">৳${Number(answer.total).toLocaleString('en-IN', {maximumFractionDigits:0})}</span><div class="label">Spent</div></div>`;
    h += `<div class="rich-pacing-item"><span class="value">৳${Number(answer.daily_avg).toLocaleString('en-IN', {maximumFractionDigits:0})}</span><div class="label">Avg / day</div></div>`;
    h += `<div class="rich-pacing-item"><span class="value">৳${Number(answer.projected).toLocaleString('en-IN', {maximumFractionDigits:0})}</span><div class="label">Projected</div></div>`;
    h += `<div class="rich-pacing-item"><span class="value">${de}/${dim}</span><div class="label">Days</div></div>`;
    h += `</div>`;
    h += `<div class="rich-pacing-track"><div class="rich-pacing-fill" style="width:${dayPct}%"></div></div>`;
    h += `<div class="rich-pacing-sub">${de} of ${dim} days elapsed (${Math.round(dayPct)}%)</div>`;
  } else if (t === 'comparison') {
    const months = answer.months || [];
    const maxAmt = Math.max(...months.map(m => m.amount), 1);
    h += `<div class="rich-compare">`;
    months.forEach(m => {
      const pct = (m.amount / maxAmt) * 100;
      h += `<div class="rich-compare-bar"><span class="rich-compare-label">${esc(m.label)}</span><div class="rich-compare-track"><div class="rich-compare-fill" style="width:${Math.max(pct, 4)}%">${pct > 25 ? '৳' + Number(m.amount).toLocaleString('en-IN', {maximumFractionDigits:0}) : ''}</div></div><span class="rich-compare-amount">৳${Number(m.amount).toLocaleString('en-IN', {maximumFractionDigits:0})}</span></div>`;
    });
    h += `</div>`;
    const mBars = months.map(m => ({label: m.label, value: m.amount, color: '#6366f1'}));
    h += _miniSvgChart(mBars, 180, 80);
    if (months.length === 2) {
      const diff = months[0].amount - months[1].amount;
      const dir = diff > 0 ? '&#x2191;' : diff < 0 ? '&#x2193;' : '&#x2194;';
      const cls = diff > 0 ? 'up' : diff < 0 ? 'down' : 'same';
      h += `<div class="rich-compare-diff ${cls}">${dir} ৳${Math.abs(diff).toLocaleString('en-IN', {maximumFractionDigits:0})} ${diff > 0 ? 'increase' : diff < 0 ? 'decrease' : 'no change'}</div>`;
    }
  } else if (t === 'category_breakdown') {
    const cats = answer.categories || [];
    const maxAmt = Math.max(...cats.map(c => c.amount), 1);
    h += `<div class="rich-cat-breakdown">`;
    cats.forEach(c => {
      const pct = (c.amount / maxAmt) * 100;
      const col = _richCatColor(c.name);
      h += `<div class="rich-cat-row"><span class="rich-cat-name">${esc(c.name)}</span><div class="rich-cat-bar" style="width:${Math.max(pct, 4)}%;background:${col}"></div><span class="rich-cat-amt">৳${Number(c.amount).toFixed(2)}</span><span class="rich-cat-pct">${c.pct}%</span></div>`;
    });
    h += `</div>`;
    const catBars = cats.map(c => ({label: c.name, value: c.amount, color: _richCatColor(c.name)}));
    h += _miniSvgChart(catBars, 180, 80);
  } else if (t === 'forecast') {
    const pct = Math.min((answer.total / answer.projected) * 100, 100);
    const pctBudget = answer.budget ? Math.min((answer.projected / answer.budget) * 100, 100) : 0;
    const exceedCls = answer.will_exceed ? 'danger' : 'safe';
    h += `<div class="rich-forecast">`;
    h += `<div class="rich-total-hero"><div class="amount">৳${Number(answer.projected).toLocaleString('en-IN', {maximumFractionDigits:0})}</div><div class="sub">projected end-of-month</div></div>`;
    h += `<div class="rich-compare" style="margin-top:8px">`;
    h += `<div class="rich-compare-bar"><span class="rich-compare-label">Spent so far</span><div class="rich-compare-track"><div class="rich-compare-fill" style="width:${Math.max(pct, 4)}%">${pct > 20 ? '৳' + Number(answer.total).toLocaleString('en-IN', {maximumFractionDigits:0}) : ''}</div></div><span class="rich-compare-amount">৳${Number(answer.total).toLocaleString('en-IN', {maximumFractionDigits:0})}</span></div>`;
    if (answer.budget) {
      h += `<div class="rich-compare-bar"><span class="rich-compare-label">Budget</span><div class="rich-compare-track"><div class="rich-compare-fill ${exceedCls}" style="width:${Math.max(pctBudget, 4)}%">${pctBudget > 20 ? '৳' + Number(answer.budget).toLocaleString('en-IN', {maximumFractionDigits:0}) : ''}</div></div><span class="rich-compare-amount">৳${Number(answer.budget).toLocaleString('en-IN', {maximumFractionDigits:0})}</span></div>`;
    }
    h += `<div class="rich-compare-bar"><span class="rich-compare-label">Days</span><div class="rich-compare-track"><div class="rich-compare-fill" style="width:${Math.min((answer.days_elapsed / answer.days_in_month) * 100, 100)}%;background:#a78bfa"></div></div><span class="rich-compare-amount">${answer.days_elapsed}/${answer.days_in_month}</span></div>`;
    h += `</div></div>`;
    const fBars = [
      {label: 'Spent', value: answer.total, color: '#6366f1'},
      {label: 'Projected', value: answer.projected, color: '#f59e0b'},
    ];
    if (answer.budget) fBars.push({label: 'Budget', value: answer.budget, color: '#22c55e'});
    h += _miniSvgChart(fBars, 180, 70);
  } else if (t === 'total') {
    h += `<div class="rich-total-hero"><div class="amount">৳${Number(answer.total).toLocaleString('en-IN', {maximumFractionDigits:0})}</div>`;
    if (answer.count) h += `<div class="sub">across ${answer.count} transaction(s)</div>`;
    h += `</div>`;
  } else if (t === 'expense') {
    const col = _richCatColor(answer.category);
    h += `<div>`;
    if (answer.category) h += `<span class="rich-cat-badge" style="background:${col}20;color:${col};border:1px solid ${col}40">${esc(answer.category)}</span> `;
    h += `<span class="rich-amount-sm">৳${Number(answer.amount).toFixed(2)}</span>`;
    if (answer.description) h += `<div class="rich-subtitle">${esc(answer.description)}</div>`;
    if (answer.date) h += `<div class="rich-subtitle">${esc(answer.date)}</div>`;
    h += `</div>`;
  } else if (t === 'extremum') {
    const col = _richCatColor(answer.category);
    h += `<div>${answer.is_max ? '&#x1F7E2;' : '&#x1F534;'} <span class="rich-amount-sm">৳${Number(answer.value).toFixed(2)}</span>`;
    if (answer.category) h += ` <span class="rich-cat-badge" style="background:${col}20;color:${col};border:1px solid ${col}40">${esc(answer.category)}</span>`;
    if (answer.description) h += `<div class="rich-subtitle">${esc(answer.description)}</div>`;
    h += `</div>`;
  } else if (t === 'average') {
    h += `<div class="rich-total-hero"><div class="amount">৳${Number(answer.avg).toFixed(2)}</div>`;
    if (answer.count) h += `<div class="sub">across ${answer.count} day(s)</div>`;
    h += `</div>`;
  } else if (t === 'frequency') {
    const col = _richCatColor(answer.category);
    h += `<div style="text-align:center;padding:4px 0"><span class="rich-cat-badge" style="background:${col}20;color:${col};border:1px solid ${col}40;font-size:14px;padding:4px 14px">${esc(answer.category)}</span><div style="font-size:22px;font-weight:700;margin:6px 0">${answer.count}</div><div class="rich-subtitle">transaction(s)</div></div>`;
  } else if (t === 'list') {
    h += `<div>Found <strong>${answer.count}</strong> result(s)`;
    if (answer.total) h += ` totaling <span class="rich-highlight-amt">৳${Number(answer.total).toFixed(2)}</span>`;
    h += `.</div>`;
  } else if (t === 'text') {
    h += `<div>${esc(answer.text)}</div>`;
  } else {
    // llm or unknown — inline highlight
    h += highlightInline(answer.text || '');
  }

  h += '</div>';
  return h;
}

function _miniSvgChart(bars, w, h) {
  if (!bars || !bars.length) return '';
  const max = Math.max(...bars.map(b => b.value), 1);
  const pad = 2, gap = 4, totalW = Math.max(bars.length * 40, w);
  const bw = Math.max((totalW - pad * 2 - gap * (bars.length - 1)) / bars.length, 8);
  const ch = h - 24;
  let svg = `<svg width="${totalW}" height="${h}" viewBox="0 0 ${totalW} ${h}" style="display:block;margin:6px auto 0;overflow:visible"><g transform="translate(${pad},0)">`;
  bars.forEach((b, i) => {
    const bh = Math.max((b.value / max) * ch, 2);
    const x = i * (bw + gap);
    const y = ch - bh;
    const col = b.color || '#6366f1';
    svg += `<rect x="${x}" y="${y}" width="${bw}" height="${bh}" rx="2" fill="${col}" opacity="0.85"><title>${esc(b.label)}: ৳${Number(b.value).toLocaleString('en-IN', {maximumFractionDigits:0})}</title></rect>`;
    svg += `<text x="${x + bw / 2}" y="${ch + 14}" text-anchor="middle" font-size="10" fill="var(--text-secondary)">${esc(b.label)}</text>`;
  });
  svg += '</g></svg>';
  return svg;
}

function highlightInline(text) {
  if (!text) return '';
  let s = esc(text);
  s = s.replace(/৳([\d,]+\.?\d*)/g, '<span class="rich-highlight-amt">৳$1</span>');
  s = s.replace(/(\d+) transaction\(s\)/g, '<span class="rich-highlight-num">$1</span> transaction(s)');
  s = s.replace(/(\d+) day\(s\)/g, '<span class="rich-highlight-num">$1</span> day(s)');
  return s;
}

function getWelcomeHtml() {
  let chips = '';
  const pool = cachedSuggestions.length ? cachedSuggestions : FALLBACK_SUGGESTIONS;
  const count = window.innerWidth < 768 ? 2 : 3;
  const picks = pool.sort(() => Math.random() - 0.5).slice(0, count);
  if (picks.length) {
    chips = `<div class="chat-suggestion-chips">`;
    picks.forEach(s => {
      const safe = s.replace(/'/g, "\\'");
      chips += `<button class="chat-suggestion-chip" onclick="sendSuggestion('${safe}')">${esc(s)}</button>`;
    });
    chips += `</div>`;
  }
  return `<div class="chat-message ai-message">
    <div class="chat-bubble ai-bubble welcome-bubble">
      Ask me about your expenses, or just type them to log!<br>
      <small>e.g., <em>"biryani 250"</em> or <em>"rickshaw 50 ar coffee 120"</em></small>
    </div>
    ${chips}
  </div>`;
}

function addChatMessage(type, content, sql, data, columns, suggestions) {
  chatMessages.push({ type, content, sql, data, columns, suggestions });
  renderChatMessages();
}

const FOLLOWUP_TEMPLATES = {
  budget: [
    { text: 'Which categories are over budget?' },
    { text: 'Show all budgets' },
    { text: 'How much on {category} total this month?', show: a => a.category },
    { text: 'Compare spending on {category} to last month', show: a => a.category },
  ],
  pacing: [
    { text: 'Which categories am I spending most on?' },
    { text: 'Compare to last month' },
    { text: 'Show breakdown by category this month' },
    { text: 'What was my biggest expense this month?' },
  ],
  comparison: [
    { text: 'What changed most between months?' },
    { text: 'Show breakdown by category for {months.0.label}', show: a => a.months && a.months.length > 0 },
    { text: 'Show breakdown by category for {months.1.label}', show: a => a.months && a.months.length > 1 },
    { text: 'View as chart' },
  ],
  category_breakdown: [
    { text: 'Show expenses for {categories.0.name}', show: a => a.categories && a.categories.length > 0 },
    { text: 'Compare to last month' },
    { text: 'What changed since last month?' },
    { text: 'What was my biggest expense this month?' },
  ],
  total: [
    { text: 'Show breakdown by category' },
    { text: 'Compare to last month' },
    { text: 'What was my biggest expense?' },
    { text: 'Show top 5 expenses' },
  ],
  expense: [
    { text: 'How much on {category} total?', show: a => a.category },
    { text: 'Show all {category} expenses', show: a => a.category },
    { text: 'Compare to last month' },
  ],
  extremum: [
    { text: 'Show second most expensive' },
    { text: 'Show all {category} expenses', show: a => a.category },
    { text: 'Compare to last month' },
    { text: 'What is my average daily spending?', show: a => a.value > 5000 },
  ],
  average: [
    { text: 'Show breakdown by category' },
    { text: 'Show top 5 expenses' },
    { text: 'Compare to last month' },
  ],
  frequency: [
    { text: 'Show all {category} expenses', show: a => a.category },
    { text: 'How much on {category} total?', show: a => a.category },
    { text: 'Compare to last month' },
  ],
  list: [
    { text: 'Show breakdown by category' },
    { text: 'Compare to last month' },
    { text: 'Show top 5 expenses' },
  ],
};

function generateFollowups(answer) {
  if (!answer || !answer.type) return [];
  const templates = FOLLOWUP_TEMPLATES[answer.type];
  if (!templates) return [];

  const valid = [];
  for (const t of templates) {
    if (t.show && !t.show(answer)) continue;
    const text = t.text.replace(/\{(\w+(?:\.\w+)*)\}/g, (_, path) => {
      const val = path.split('.').reduce((o, k) => o != null ? o[k] : undefined, answer);
      return val != null ? String(val) : _;
    });
    if (valid.indexOf(text) === -1) valid.push(text);
  }

  return valid.sort(() => Math.random() - 0.5).slice(0, 3);
}

const FALLBACK_SUGGESTIONS = [
  "How does this week compare to last week?",
  "Show me the breakdown by category",
  "What's my average daily spending this month?",
  "What was my biggest expense this month?",
  "How much did I spend on Dining Out this month?",
  "How am I doing on my budget this month?",
];

let cachedSuggestions = [];

async function fetchSuggestions() {
  const res = await api.get('/api/suggestions');
  if (res.ok && res.data.suggestions && res.data.suggestions.length) {
    cachedSuggestions = res.data.suggestions;
    return res.data.suggestions;
  }
  const shuffled = [...FALLBACK_SUGGESTIONS].sort(() => Math.random() - 0.5);
  cachedSuggestions = shuffled.slice(0, 3);
  return cachedSuggestions;
}

function renderChatMessages() {
  const container = document.getElementById('chatMessages');
  if (!container) return;
  if (!chatMessages.length) {
    container.innerHTML = getWelcomeHtml();
    return;
  }
  let html = chatMessages.map((msg, idx) => {
    if (msg.type === 'user') {
      return `<div class="chat-message user-message"><div class="chat-bubble user-bubble">${esc(msg.content)}</div></div>`;
    }
    if (msg.type === 'ai') {
      let h = `<div class="chat-message ai-message"><div class="chat-bubble ai-bubble">${renderRichAnswer(msg.content)}`;
      if (msg.data && msg.data.length) {
        h += renderDataTable(msg.columns, msg.data);
      }
      if (msg.sql) {
        h += `<div class="chat-sql-toggle" onclick="this.nextElementSibling.classList.toggle('chat-sql-visible')">Show SQL</div>`;
        h += `<pre class="chat-sql-block">${esc(msg.sql)}</pre>`;
      }
      h += `</div>`;
      if (msg.suggestions && msg.suggestions.length) {
        h += `<div class="chat-suggestion-chips">`;
        msg.suggestions.forEach(s => {
          const safe = s.replace(/'/g, "\\'");
          h += `<button class="chat-suggestion-chip" onclick="sendSuggestion('${safe}')">${esc(s)}</button>`;
        });
        h += `</div>`;
      }
      h += `</div>`;
      return h;
    }
    if (msg.type === 'expense_preview') {
      const items = msg.items || [];
      let total = items.reduce((s, i) => s + (i.amount || 0), 0);
      let h = `<div class="chat-message ai-message"><div class="chat-bubble ai-bubble">`;
      const dateVal = msg.date || new Date().toISOString().slice(0, 10);
      h += `<div class="chat-expense-header">I found these expenses <input type="date" class="chat-expense-date" value="${dateVal}" onchange="updateChatExpenseDate(${idx}, this.value)">:</div>`;
      h += `<div class="chat-expense-list">`;
      items.forEach((i, itemIdx) => {
        const col = i.color || '#6b7280';
        const catOptions = (window.categoryColors ? Object.keys(window.categoryColors) : []).map(c =>
          `<option value="${c}" ${c === i.category ? 'selected' : ''}>${c}</option>`
        ).join('');
        h += `<div class="chat-expense-item">
          <select class="chat-category-select" style="border-color:${col}40;background-color:${col}20;color:${col}"
            onchange="updateChatItemCategory(${idx}, ${itemIdx}, this.value)">
            ${catOptions}
          </select>
          <textarea class="chat-expense-desc" rows="1" 
            oninput="this.style.height='auto';this.style.height=Math.min(this.scrollHeight,120)+'px';updateChatItemDesc(${idx}, ${itemIdx}, this.value)">${esc(i.description || '')}</textarea>
          <span class="chat-expense-amt-prefix">৳</span><input class="chat-expense-amt" type="number" step="0.01" min="0" value="${(i.amount || 0).toFixed(2)}"
            oninput="updateChatItemAmount(${idx}, ${itemIdx}, this.value)">
        </div>`;
      });
      h += `</div>`;
      h += `<div class="chat-expense-total">Total: ৳${total.toFixed(2)}</div>`;
      h += `<div class="chat-expense-actions">`;
      if (msg.saving) {
        h += `<span class="chat-expense-saving">Saving...</span>`;
      } else {
        h += `<button class="btn btn-primary btn-sm" onclick="confirmChatExpenses(${idx})">✓ Save</button>`;
        h += `<button class="btn btn-outline btn-sm" onclick="dismissChatExpenses(${idx})">✗ Skip</button>`;
      }
      h += `</div></div></div>`;
      return h;
    }
    if (msg.type === 'loading') {
      return `<div class="chat-message ai-message"><div class="chat-bubble ai-bubble"><div class="chat-loader"><span class="typing-dots"><span></span><span></span><span></span></span></div></div></div>`;
    }
    return '';
  }).join('');
  container.innerHTML = html;
  // Auto-resize description textareas
  container.querySelectorAll('.chat-expense-desc').forEach(ta => {
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 120) + 'px';
  });
  if (container.scrollHeight - container.scrollTop - container.clientHeight < 120) {
    container.scrollTop = container.scrollHeight;
  }
}

function _isAmountCol(name) {
  const n = name.toLowerCase();
  return n === 'total' || n === 'spent' || n === 'remaining' || n === 'budget_amount' ||
    n.includes('amount') || n.includes('spent') || n.includes('total') ||
    n === 'avg' || n === 'average' || n === 'avg_daily' || n === 'daily_avg' ||
    n === 'sum' || n === 'cost' || n === 'budget';
}

function _renderCell(col, val) {
  if (typeof val === 'number') {
    if (_isAmountCol(col)) return `<span class="td-amount">৳${val.toFixed(2)}</span>`;
    if (col.toLowerCase() === 'count' || col === 'cnt') return `<span class="td-count">${val}</span>`;
    return val;
  }
  const cl = col.toLowerCase();
  if (cl === 'category' && val) {
    const colors = window.categoryColors || {};
    const c = colors[val] || '#6b7280';
    return `<span class="category-badge" style="background:${c}20;color:${c};border-color:${c}40">${esc(val)}</span>`;
  }
  if (val == null) return '';
  return esc(String(val));
}

function _renderTable(columns, data, shownRows) {
  const catIdx = columns.findIndex(c => c.toLowerCase() === 'category');
  const rows = data.slice(0, shownRows);
  let h = '<table><thead><tr>';
  columns.forEach((c, ci) => {
    h += `<th onclick="_sortTable(this)" data-col="${ci}" class="td-sortable">${esc(c)} <span class="td-sort-arrow"></span></th>`;
  });
  h += '</tr></thead><tbody>';
  rows.forEach(r => {
    h += '<tr>';
    columns.forEach(c => {
      h += `<td>${_renderCell(c, r[c])}</td>`;
    });
    h += '</tr>';
  });
  h += '</tbody></table>';
  return h;
}

let _sortStates = {};

function _sortTable(th) {
  const el = th.closest('[id^="td-"]');
  if (!el) return;
  const idx = parseInt(el.id.replace('td-', ''), 10);
  const store = window._tableStore[idx];
  if (!store) return;
  const ci = parseInt(th.dataset.col, 10);
  const col = store.columns[ci];
  if (!col) return;

  const key = idx + '-' + ci;
  const prev = _sortStates[key] || 0;
  const dir = prev >= 1 ? -1 : 1;
  _sortStates[key] = dir;

  store.columns.forEach((_, i) => {
    const h = el.querySelectorAll('th')[i];
    if (h) {
      const arrow = h.querySelector('.td-sort-arrow');
      if (arrow) arrow.textContent = i === ci ? (dir === 1 ? ' ▲' : ' ▼') : '';
    }
  });

  const allCols = store.columns;
  const catIdx = allCols.findIndex(c => c.toLowerCase() === 'category');
  store.data.sort((a, b) => {
    let va = a[col], vb = b[col];
    if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * dir;
    va = String(va != null ? va : '').toLowerCase();
    vb = String(vb != null ? vb : '').toLowerCase();
    if (col.toLowerCase() === 'date') {
      const da = va ? new Date(va) : null;
      const db = vb ? new Date(vb) : null;
      if (da && db) return (da - db) * dir;
    }
    return va < vb ? -dir : va > vb ? dir : 0;
  });
  store.shown = 10;
  el.innerHTML = _renderTable(store.columns, store.data, store.shown) + _tableFooter(store, idx);
}

function _tableFooter(store, idx) {
  let h = '';
  if (store.shown < store.data.length) {
    h += `<button class="chat-show-more" onclick="showMoreTable(${idx})">Show more (${store.data.length - store.shown} remaining)</button>`;
  } else if (store.data.length > 10) {
    h += `<div class="chat-table-more">Showing all ${store.data.length} entries</div>`;
  }
  return h;
}

function renderDataTable(columns, data) {
  if (!columns || !columns.length || !data || !data.length) return '';
  const visibleCols = columns.filter(c => c.toLowerCase() !== 'id');
  if (!visibleCols.length) return '';
  const maxRows = 10;

  if (!window._tableStore) window._tableStore = [];
  const storeId = 'td-' + window._tableStore.length;
  window._tableStore.push({ columns: visibleCols, data: [...data], shown: maxRows });

  return `<div class="chat-data-table" id="${storeId}">${_renderTable(visibleCols, data, maxRows)}${_tableFooter(null, window._tableStore.length - 1)}</div>`;
}

function showMoreTable(idx) {
  const store = window._tableStore[idx];
  if (!store) return;
  const el = document.getElementById('td-' + idx);
  if (!el) return;
  store.shown = Math.min(store.shown + 10, store.data.length);
  el.innerHTML = _renderTable(store.columns, store.data, store.shown) + _tableFooter(store, idx);
}

async function sendChatMessage() {
  if (isSendingMessage) return;
  isSendingMessage = true;
  try {
    stopVoiceInput();
    const input = document.getElementById('chatInput');
    if (!input) return;
    let message = input.value.trim();
    if (!message) return;
    input.value = '';
    input.style.height = 'auto';
    // Restore mic visibility after clearing input
    const micBtn = document.getElementById('voiceBtn');
    const sendBtn = document.getElementById('chatSendBtn');
    if (micBtn) micBtn.style.display = 'flex';
    if (sendBtn) sendBtn.style.display = 'none';

    // Strip leading action words for cleaner parsing
    message = message.replace(/^(add|save|log|record)\s+/i, '').trim();

    // Build conversation history (last 6 pairs)
    const history = [];
    for (const m of chatMessages) {
      if (m.type === 'ai' || m.type === 'user') {
        const text = typeof m.content === 'object' && m.content ? (m.content.text || '') : m.content;
        history.push({ role: m.type, content: text });
      }
    }

    addChatMessage('user', message);
    addChatMessage('loading', '');
    const res = await api.post('/api/chat', { message, history: history.slice(-12) });
    chatMessages = chatMessages.filter(m => m.type !== 'loading');
    if (!res.ok) {
      addChatMessage('ai', 'Sorry, I couldn\'t process that. ' + (res.error || 'Please try again.'));
      return;
    }
    const d = res.data;

    if (d.type === 'budget') {
      const res = await api.post('/api/budgets/set', { category: d.category, amount: d.amount });
      if (res.ok) {
        const displayName = d.category === '__overall__' ? 'Overall' : d.category;
        addChatMessage('ai', `✅ Budget set: **${displayName}** → ৳${Number(d.amount).toFixed(2)}/month`);
        showToast(`${displayName} budget set to ৳${Number(d.amount).toFixed(2)}`, 'success');
      } else {
        addChatMessage('ai', `Sorry, I couldn't set that budget. ${res.error || 'Please try again.'}`);
      }
      return;
    }

    if (d.type === 'expense') {
      chatMessages.push({ type: 'expense_preview', items: d.items, date: d.date });
      renderChatMessages();
      return;
    }

    // Q&A response — generate context-aware follow-ups
    let suggestions = generateFollowups(d.answer);
    if (!suggestions.length) {
      const fallback = await pickSuggestions(message, d.answer);
      suggestions = fallback.slice(0, 3);
    }
    addChatMessage('ai', d.answer || 'I found ' + (d.data ? d.data.length : 0) + ' result(s).', d.sql, d.data, d.columns, suggestions);
  } finally {
    isSendingMessage = false;
  }
}

function updateChatItemCategory(msgIdx, itemIdx, newCategory) {
  const msg = chatMessages[msgIdx];
  if (!msg || msg.type !== 'expense_preview' || !msg.items[itemIdx]) return;
  msg.items[itemIdx].category = newCategory;
  msg.items[itemIdx].color = (window.categoryColors || {})[newCategory] || '#6b7280';
}

function updateChatItemDesc(msgIdx, itemIdx, value) {
  const msg = chatMessages[msgIdx];
  if (!msg || msg.type !== 'expense_preview' || !msg.items[itemIdx]) return;
  msg.items[itemIdx].description = value;
}

function updateChatItemAmount(msgIdx, itemIdx, value) {
  const msg = chatMessages[msgIdx];
  if (!msg || msg.type !== 'expense_preview' || !msg.items[itemIdx]) return;
  const amt = parseFloat(value);
  msg.items[itemIdx].amount = isNaN(amt) ? 0 : amt;
}

function updateChatExpenseDate(msgIdx, value) {
  const msg = chatMessages[msgIdx];
  if (!msg || msg.type !== 'expense_preview') return;
  msg.date = value;
}

async function confirmChatExpenses(index) {
  const msg = chatMessages[index];
  if (!msg || msg.type !== 'expense_preview' || msg.saving) return;
  msg.saving = true;
  renderChatMessages();

  const date = msg.date || new Date().toISOString().slice(0, 10);
  const res = await api.post('/api/expenses/bulk', { date, items: msg.items });
  if (!res.ok) {
    showToast(res.error || 'Failed to save expenses', 'error');
    msg.saving = false;
    renderChatMessages();
    return;
  }

  const count = res.data.count || msg.items.length;
  const summary = msg.items.map(i => `${i.description || ''}: ৳${i.amount.toFixed(2)}`).join(', ');
  chatMessages[index] = { type: 'ai', content: `✅ Saved ${count} expense(s): ${summary}` };
  renderChatMessages();
  showToast(`Logged ${count} expense(s)!`, 'success');
  showBudgetToastAlerts(res.data.budget_alerts);
  refreshHomeData();
}

function dismissChatExpenses(index) {
  chatMessages.splice(index, 1);
  renderChatMessages();
}

function clearChatMessages() {
  chatMessages = [];
  renderChatMessages();
  const input = document.getElementById('chatInput');
  if (input) {
    input.value = '';
    input.style.height = 'auto';
  }
  const micBtn = document.getElementById('voiceBtn');
  const sendBtn = document.getElementById('chatSendBtn');
  if (micBtn) micBtn.style.display = 'flex';
  if (sendBtn) sendBtn.style.display = 'none';
}

async function refreshHomeData() {
  const res = await api.get('/api/index');
  if (!res.ok) return;
  const d = res.data;
  window.categoryColors = d.category_colors;

  // Update stats
  const statValues = document.querySelectorAll('.stat-value');
  if (statValues.length >= 3) {
    statValues[0].textContent = '৳' + Number(d.today_total).toFixed(2);
    statValues[1].textContent = '৳' + Number(d.month_total).toFixed(2);
    statValues[2].textContent = d.today_expenses.length;
  }

  // Update today's expenses list
  const todayEl = document.getElementById('todayExpenses');
  if (todayEl) {
    todayEl.innerHTML = d.today_expenses.length
      ? d.today_expenses.map(makeExpenseItem).join('')
      : '<div class="empty-state"><p>No expenses today. Add your first one!</p></div>';
  }

  // Refresh budget alerts
  const alertsContainer = document.querySelector('.budget-alerts');
  if (alertsContainer) {
    alertsContainer.outerHTML = renderBudgetAlerts(d.budget_alerts);
  }
}

async function pickSuggestions(question, answer) {
  // Try to fetch fresh suggestions from the API, fall back to cached
  const res = await api.get('/api/suggestions');
  if (res.ok && res.data.suggestions && res.data.suggestions.length) {
    cachedSuggestions = res.data.suggestions;
    return res.data.suggestions;
  }
  // Use cached or fallback pool
  if (cachedSuggestions.length) return cachedSuggestions;
  const shuffled = [...FALLBACK_SUGGESTIONS].sort(() => Math.random() - 0.5);
  return shuffled.slice(0, 3);
}

function sendSuggestion(text) {
  const input = document.getElementById('chatInput');
  if (input) {
    input.value = text;
    sendChatMessage();
  }
}


// ── Init ──

async function init() {
  const me = await api.get('/api/me');
  if (me.ok) {
    currentUser = me.data;
  }
  // Pre-fetch suggestions for welcome screen
  await fetchSuggestions();
  renderRoute();
}

// ── Push Notification Subscription ──

function urlB64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = atob(base64);
  return Uint8Array.from([...rawData].map((c) => c.charCodeAt(0)));
}

async function subscribeToPush() {
  if (!("Notification" in window) || !("serviceWorker" in navigator)) return;
  if (Notification.permission === "denied") return;
  if (Notification.permission !== "granted") {
    const permission = await Notification.requestPermission();
    if (permission !== "granted") return;
  }
  try {
    const registration = await navigator.serviceWorker.register('/sw.js');
    // Wait for SW to be active before subscribing
    if (registration.installing) {
      await new Promise((resolve, reject) => {
        registration.installing.addEventListener('statechange', () => {
          if (registration.installing.state === 'activated') resolve();
          if (registration.installing.state === 'redundant') reject(new Error('SW redundant'));
        });
      });
    } else if (registration.waiting && !registration.active) {
      registration.waiting.postMessage({ type: 'SKIP_WAITING' });
      await new Promise((resolve) => {
        const onStateChange = () => { if (registration.active) { resolve(); } };
        registration.addEventListener('updatefound', onStateChange);
        if (registration.active) resolve();
      });
    }
    const keyRes = await api.get("/api/notifications/vapid-public-key");
    if (!keyRes.ok || !keyRes.data?.publicKey) return;
    // Unsubscribe existing subscription first to avoid reusing stale endpoints
    const existingSub = await registration.pushManager.getSubscription();
    if (existingSub) {
      await existingSub.unsubscribe();
    }
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlB64ToUint8Array(keyRes.data.publicKey),
    });
    const key = subscription.toJSON();
    const subRes = await api.post("/api/notifications/subscribe", {
      endpoint: key.endpoint,
      keys: { p256dh: key.keys.p256dh, auth: key.keys.auth },
    });
    if (!subRes.ok) {
      console.error('[push] Failed to save subscription on server:', subRes.error);
    }
  } catch (e) {
    console.error('[push] subscribeToPush failed:', e);
  }
}

async function unsubscribeFromPush() {
  try {
    if (!("serviceWorker" in navigator)) return;
    const registration = await navigator.serviceWorker.getRegistration();
    if (!registration) return;
    const subscription = await registration.pushManager.getSubscription();
    if (subscription) {
      const key = subscription.toJSON();
      await api.post("/api/notifications/unsubscribe", { endpoint: key.endpoint });
      await subscription.unsubscribe();
    }
  } catch (e) {
    console.error('unsubscribeFromPush failed:', e);
  }
}

// Logout handler
document.getElementById('logoutBtn')?.addEventListener('click', async () => {
  await api.post('/api/logout');
  currentUser = null;
  navigate('/login');
});

// Theme toggle handler
function syncThemeButton() {
  const btn = document.getElementById('themeToggle');
  if (!btn) return;
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  if (btn.classList.contains('theme-toggle-sidebar')) {
    btn.textContent = isDark ? '☀️ Light Mode' : '🌙 Dark Mode';
  } else {
    btn.textContent = isDark ? '☀️' : '🌙';
  }
  btn.title = isDark ? 'Switch to light mode' : 'Switch to dark mode';
}

function toggleTheme() {
  const html = document.documentElement;
  const isDark = html.getAttribute('data-theme') === 'dark';
  if (isDark) {
    html.removeAttribute('data-theme');
    localStorage.setItem('theme', 'light');
  } else {
    html.setAttribute('data-theme', 'dark');
    localStorage.setItem('theme', 'dark');
  }
  syncThemeButton();
}

document.addEventListener('DOMContentLoaded', syncThemeButton);
document.getElementById('themeToggle')?.addEventListener('click', toggleTheme);

async function renderRoute() {
  const { view, params, token } = getRoute();
  const authViews = ['login', 'register', 'forgot-password', 'reset-password'];

  // If not logged in and trying to access protected route, redirect to login
  if (!currentUser && !authViews.includes(view)) {
    navigate('/login');
    return;
  }
  // If logged in and on auth page, redirect to home
  if (currentUser && authViews.includes(view)) {
    navigate('/');
    return;
  }

  // Show loading spinner immediately for app views
  if (currentUser && !authViews.includes(view)) {
    const app = document.getElementById('app');
    app.innerHTML = '<div class="page-loader"><div class="spinner-lg"></div></div>';
  }

  switch (view) {
    case 'login': renderLogin(); break;
    case 'register': renderRegister(); break;
    case 'forgot-password': renderForgotPassword(); break;
    case 'reset-password': renderResetPassword(token); break;
    case 'home': renderHome(parseInt(params?.page) || 1); break;
    case 'dashboard': renderDashboard(params || {}); break;
    case 'budgets': renderBudgets(); break;
    case 'profile': renderProfile(); break;
    case 'calendar': renderCalendar(); break;
    case 'recurring': renderRecurringTransactions(); break;
    case 'admin-users': renderAdminUsers(); break;
    case 'admin-notifications': renderAdminNotifications(); break;
    default: renderHome(1);
  }
}

// ── Calendar Heatmap ─────────────────────────────────────

async function renderCalendar() {
  setLayout('app');
  document.title = 'Calendar - Expense Tracker';
  const app = document.getElementById('app');
  const now = new Date();
  let year = now.getFullYear();
  let month = now.getMonth() + 1;

  async function loadCalendar() {
    app.innerHTML = '<div class="page-loader"><div class="spinner-lg"></div></div>';
    const totalsRes = await api.get(`/api/expenses/daily-totals?year=${year}&month=${month}`);
    if (!totalsRes.ok) { handleAuthError(totalsRes); return; }
    const totalsMap = totalsRes.data.totals || {};

    const daysInMonth = new Date(year, month, 0).getDate();
    const firstDay = new Date(year, month - 1, 1).getDay();
    const monthNames = ['January','February','March','April','May','June','July','August','September','October','November','December'];
    const dayHeaders = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];

    const values = Object.values(totalsMap).filter(v => v > 0);
    const maxVal = values.length ? Math.max(...values) : 0;

    function getTier(total) {
      if (total === 0) return 0;
      if (maxVal === 0) return 0;
      const pct = total / maxVal;
      if (pct <= 0.25) return 1;
      if (pct <= 0.5) return 2;
      if (pct <= 0.75) return 3;
      return 4;
    }

    let cells = '';
    for (let i = 0; i < firstDay; i++) {
      cells += '<div class="cal-day cal-day-empty"></div>';
    }
    for (let d = 1; d <= daysInMonth; d++) {
      const dateStr = `${year}-${String(month).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
      const total = totalsMap[dateStr] || 0;
      const tier = getTier(total);
      const amtStr = total > 0 ? `৳${Number(total).toFixed(0)}` : '';
      cells += `<div class="cal-day cal-tier-${tier}" data-date="${dateStr}" title="${dateStr}${total > 0 ? ` - ${amtStr}` : ' - No expenses'}" onclick="selectCalendarDay('${dateStr}')">
        <span class="cal-day-num">${d}</span>
        ${total > 0 ? `<span class="cal-day-amt">${amtStr}</span>` : ''}
      </div>`;
    }

    const todayStr = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;

    app.innerHTML = `
      <div class="cal-page">
        <div class="cal-header">
          <button class="cal-nav-btn" onclick="calendarNav(${year}, ${month}, -1)">◀</button>
          <h2 class="cal-title">${monthNames[month-1]} ${year}</h2>
          <button class="cal-nav-btn" onclick="calendarNav(${year}, ${month}, 1)">▶</button>
          <button class="cal-today-btn" onclick="calendarToday()">Today</button>
        </div>
        <div class="cal-heatmap">
          <div class="cal-weekdays">
            ${dayHeaders.map(h => `<div class="cal-weekday">${h}</div>`).join('')}
          </div>
          <div class="cal-grid">
            ${cells}
          </div>
        </div>
        <div class="cal-legend">
          <span class="cal-legend-label">Less</span>
          <span class="cal-legend-swatch cal-tier-0"></span>
          <span class="cal-legend-swatch cal-tier-1"></span>
          <span class="cal-legend-swatch cal-tier-2"></span>
          <span class="cal-legend-swatch cal-tier-3"></span>
          <span class="cal-legend-swatch cal-tier-4"></span>
          <span class="cal-legend-label">More</span>
        </div>
        <div id="calExpenses" class="cal-expenses"></div>
      </div>`;

    if (todayStr.startsWith(`${year}-${String(month).padStart(2,'0')}`)) {
      selectCalendarDay(todayStr);
    }
  }

  window.calendarNav = function(y, m, dir) {
    m += dir;
    if (m < 1) { m = 12; y--; }
    if (m > 12) { m = 1; y++; }
    year = y; month = m;
    loadCalendar();
  };

  window.calendarToday = function() {
    year = now.getFullYear();
    month = now.getMonth() + 1;
    loadCalendar();
  };

  window.selectCalendarDay = async function(dateStr) {
    document.querySelectorAll('.cal-day.selected').forEach(el => el.classList.remove('selected'));
    const dayEl = document.querySelector(`.cal-day[data-date="${dateStr}"]`);
    if (dayEl) dayEl.classList.add('selected');

    const el = document.getElementById('calExpenses');
    if (!el) return;
    el.innerHTML = '<div class="page-loader"><div class="spinner-lg"></div></div>';
    const res = await api.get(`/api/expenses/${dateStr}`);
    if (!res.ok) { el.innerHTML = ''; return; }
    const expenses = res.data;
    if (!expenses.length) {
      el.innerHTML = `<div class="cal-expenses-header"><h3>${dateStr}</h3><span class="expense-count">No expenses</span></div>`;
      return;
    }
    const total = expenses.reduce((s, e) => s + e.amount, 0);
    el.innerHTML = `
      <div class="cal-expenses-header"><h3>${dateStr}</h3><span class="expense-count">৳${total.toFixed(2)}</span></div>
      <div class="expense-list">${expenses.map(makeExpenseItem).join('')}</div>`;
  };

  loadCalendar();
}

// ── Recurring Transactions ───────────────────────────────

async function renderRecurringTransactions() {
  setLayout('app');
  document.title = 'Recurring - Expense Tracker';
  const app = document.getElementById('app');
  app.innerHTML = '<div class="page-loader"><div class="spinner-lg"></div></div>';

  const [recRes, catRes] = await Promise.all([
    api.get('/api/recurring'),
    api.get('/api/categories'),
  ]);
  if (!recRes.ok) { handleAuthError(recRes); return; }

  const transactions = recRes.data.transactions || [];
  const categories = catRes.ok ? (catRes.data.categories || Object.keys(catRes.data.colors || {})) : [];
  const frequencies = ['daily', 'weekly', 'monthly', 'yearly'];
  let editingId = null;

  window.saveRecurring = async function() {
    const desc = document.getElementById('recDesc')?.value.trim();
    const amt = parseFloat(document.getElementById('recAmount')?.value);
    const cat = document.getElementById('recCategory')?.value;
    const freq = document.getElementById('recFrequency')?.value;
    const nd = document.getElementById('recNextDate')?.value;
    const ed = document.getElementById('recEndDate')?.value || null;
    if (!desc || !amt || !cat || !nd) { showToast('Fill in all required fields', 'error'); return; }

    const body = { description: desc, amount: amt, category: cat, frequency: freq, next_date: nd };
    if (ed) body.end_date = ed;

    let res;
    if (editingId) {
      body.is_active = true;
      res = await api.put(`/api/recurring/${editingId}`, body);
    } else {
      res = await api.post('/api/recurring', body);
    }
    if (!res.ok) { showToast(res.error || 'Error saving', 'error'); return; }
    showToast(editingId ? 'Updated!' : 'Added!', 'success');
    editingId = null;
    renderRecurringTransactions();
  };

  window.editRecurring = function(id) {
    const rec = transactions.find(t => t.id === id);
    if (!rec) return;
    editingId = id;
    const el = document.getElementById('recDesc'); if (el) el.value = rec.description;
    const amt = document.getElementById('recAmount'); if (amt) amt.value = rec.amount;
    const cat = document.getElementById('recCategory'); if (cat) cat.value = rec.category;
    const freq = document.getElementById('recFrequency'); if (freq) freq.value = rec.frequency;
    const nd = document.getElementById('recNextDate'); if (nd) nd.value = rec.next_date;
    const ed = document.getElementById('recEndDate'); if (ed) ed.value = rec.end_date || '';
    const btn = document.getElementById('recSaveBtn');
    if (btn) btn.textContent = 'Update';
    const cancel = document.getElementById('recCancelBtn');
    if (cancel) cancel.style.display = 'inline-block';
    document.getElementById('recForm')?.scrollIntoView({ behavior: 'smooth' });
  };

  window.cancelEditRecurring = function() {
    editingId = null;
    const form = document.getElementById('recForm');
    if (form) form.reset();
    const btn = document.getElementById('recSaveBtn');
    if (btn) btn.textContent = 'Add';
    const cancel = document.getElementById('recCancelBtn');
    if (cancel) cancel.style.display = 'none';
  };

  window.deleteRecurring = async function(id) {
    if (!confirm('Delete this recurring transaction?')) return;
    const res = await api.del(`/api/recurring/${id}`);
    if (!res.ok) { showToast('Error deleting', 'error'); return; }
    showToast('Deleted!', 'success');
    renderRecurringTransactions();
  };

  window.toggleRecurring = async function(id, checked) {
    const res = await api.put(`/api/recurring/${id}`, { is_active: checked ? 1 : 0 });
    if (!res.ok) { showToast('Error toggling', 'error'); return; }
  };

  window.processDueRecurring = async function() {
    const btn = document.getElementById('processDueBtn');
    if (btn) { btn.disabled = true; btn.textContent = 'Processing...'; }
    const res = await api.post('/api/recurring/process');
    if (btn) { btn.disabled = false; btn.textContent = 'Process Due'; }
    if (!res.ok) { showToast('Error processing', 'error'); return; }
    const count = res.data.processed || 0;
    if (count > 0) {
      showToast(`Created ${count} expense(s)!`, 'success');
      renderRecurringTransactions();
    } else {
      showToast('No due transactions', 'info');
    }
  };

  const today = new Date().toISOString().split('T')[0];
  const monthNames = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  const freqLabels = { daily: 'Daily', weekly: 'Weekly', monthly: 'Monthly', yearly: 'Yearly' };

  const listHtml = transactions.length
    ? transactions.map(t => {
        const isOverdue = t.is_active && t.next_date < today;
        return `
          <div class="rec-card ${!t.is_active ? 'rec-inactive' : ''}">
            <div class="rec-card-top">
              <div class="rec-card-info">
                <div class="rec-desc">${esc(t.description)}</div>
                <div class="rec-meta">
                  <span class="rec-amount">৳${Number(t.amount).toFixed(2)}</span>
                  <span class="category-badge" style="background:${t.color}">${esc(t.category)}</span>
                  <span class="rec-freq">${freqLabels[t.frequency] || t.frequency}</span>
                </div>
              </div>
              <button class="btn-delete" onclick="deleteRecurring(${t.id})">&times;</button>
            </div>
            <div class="rec-card-bottom">
              <span class="rec-next ${isOverdue ? 'rec-overdue' : ''}">Next: ${t.next_date}${isOverdue ? ' ⚠' : ''}</span>
              <label class="rec-toggle">
                <input type="checkbox" ${t.is_active ? 'checked' : ''} onchange="toggleRecurring(${t.id}, this.checked)">
                <span class="rec-toggle-slider"></span>
              </label>
              <button class="rec-edit-btn" onclick="editRecurring(${t.id})">✎</button>
            </div>
          </div>`;
      }).join('')
    : '<div class="empty-state"><p>No recurring transactions yet.</p></div>';

  app.innerHTML = `
    <div class="rec-page">
      <div class="rec-page-header">
        <h1>Recurring Transactions</h1>
        <button id="processDueBtn" class="btn btn-primary" onclick="processDueRecurring()">Process Due</button>
      </div>

      <div class="card rec-form-card" id="recForm">
        <h2 class="card-title" id="recFormTitle">Add Recurring</h2>
        <div class="rec-form">
          <div class="form-row">
            <div class="form-group form-desc">
              <label for="recDesc">Description</label>
              <input type="text" id="recDesc" placeholder="e.g. House Rent" autocomplete="off">
            </div>
            <div class="form-group form-amount">
              <label for="recAmount">Amount (৳)</label>
              <input type="number" id="recAmount" step="0.01" min="0" placeholder="0.00">
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label for="recCategory">Category</label>
              <select id="recCategory">
                ${categories.map(c => `<option value="${c}">${c}</option>`).join('')}
              </select>
            </div>
            <div class="form-group">
              <label for="recFrequency">Frequency</label>
              <select id="recFrequency">
                ${frequencies.map(f => `<option value="${f}">${f.charAt(0).toUpperCase() + f.slice(1)}</option>`).join('')}
              </select>
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label for="recNextDate">Start / Next Date</label>
              <input type="date" id="recNextDate" value="${today}">
            </div>
            <div class="form-group">
              <label for="recEndDate">End Date (optional)</label>
              <input type="date" id="recEndDate">
            </div>
          </div>
          <div class="form-actions">
            <button id="recSaveBtn" class="btn btn-primary" onclick="saveRecurring()">Add</button>
            <button id="recCancelBtn" class="btn btn-outline" onclick="cancelEditRecurring()" style="display:none">Cancel</button>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header-row">
          <h2 class="card-title">Your Transactions</h2>
          <span class="expense-count">${transactions.length} transaction(s)</span>
        </div>
        <div class="rec-list">${listHtml}</div>
      </div>
    </div>`;
}

document.addEventListener('DOMContentLoaded', init);
