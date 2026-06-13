// ── State ──
let currentUser = null;
let chartInstances = [];

// ── API Client ──
const api = {
  async get(url) {
    try {
      const res = await fetch(url);
      const data = await res.json();
      if (!res.ok) return { ok: false, error: data.error || 'Request failed' };
      return { ok: true, data };
    } catch { return { ok: false, error: 'Network error' }; }
  },
  async post(url, body) {
    try {
      const res = await fetch(url, {
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
      const res = await fetch(url, { method: 'DELETE' });
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
    '/admin/users': 'admin-users',
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
    const username = document.getElementById('loginUsername').value.trim();
    const password = document.getElementById('loginPassword').value.trim();
    const res = await api.post('/api/login', { username, password });
    if (!res.ok) {
      errEl.textContent = res.error;
      errEl.style.display = '';
      return;
    }
    currentUser = res.data;
    navigate('/');
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

  const todayHtml = d.today_expenses.length
    ? d.today_expenses.map(makeExpenseItem).join('')
    : '<div class="empty-state"><p>No expenses today. Add your first one!</p></div>';

  const recentBody = d.recent_expenses.length
    ? makeDateGroups(d.recent_expenses)
    : '<div class="empty-state"><p>No expenses yet. Start tracking!</p></div>';

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

    <div class="card ai-chat-card" id="aiChatCard">
      <div class="card-header-row" id="aiChatToggle" style="cursor:pointer;">
        <h2 class="card-title" style="margin-bottom:0;">
          <span class="ai-icon">🤖</span> Ask AI
        </h2>
        <div class="card-header-actions" style="display:flex;align-items:center;gap:8px;">
          <button class="chat-clear-btn" id="chatClearBtn" title="Clear chat">&times;</button>
          <span class="collapse-icon" id="aiChatCollapseIcon">▼</span>
        </div>
      </div>
      <div id="aiChatBody" class="chat-body">
        <div class="chat-messages" id="chatMessages"></div>
        <div class="chat-input-area">
          <input type="text" id="chatInput" placeholder="Ask a question..." autocomplete="off">
          <button id="voiceBtn" class="voice-btn" title="Voice input">🎤</button>
          <button id="chatSendBtn" class="btn btn-primary" onclick="sendChatMessage()">Send</button>
        </div>
      </div>
    </div>

    <div class="main-grid">
      <div class="card add-expense-card">
        <h2 class="card-title">Add Expense</h2>
        <form id="expenseForm" class="expense-form">
          <div class="form-row">
            <div class="form-group form-date">
              <label for="date">Date</label>
              <input type="date" id="date" name="date" value="${d.today}" required>
            </div>
            <div class="form-group form-desc">
              <label for="description">What did you spend?</label>
              <input type="text" id="description" name="description" required placeholder="e.g., badam 30 taka, rickshaw 50 tk" autocomplete="off">
              <div id="preview" class="preview-container"></div>
            </div>
          </div>
          <button type="submit" class="btn btn-primary btn-full btn-lg" id="submitBtn">
            <span class="btn-text">Add Expense</span>
            <span class="btn-loader" style="display:none;">
              <span class="spinner"></span>
            </span>
          </button>
        </form>
      </div>

      <div class="card today-card">
        <h2 class="card-title">Today's Expenses</h2>
        <div id="todayExpenses" class="expense-list">${todayHtml}</div>
      </div>
    </div>

    <div class="card recent-card">
      <div class="card-header-row">
        <h2 class="card-title" style="margin-bottom:0;">Recent Activity</h2>
        <span class="expense-count">${d.recent_total} expense(s)</span>
      </div>
      <div class="expense-list">${recentBody}</div>
      ${makePagination('/?', d.recent_page, d.recent_total_pages)}
    </div>`;

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
  if (!form || !input) return;

  let predictTimeout;
  let userModifiedPreview = false;
  let splitMode = false;

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

  const res = await api.get(`/api/dashboard?${qs}`);
  if (!res.ok) { handleAuthError(res); return; }
  const d = res.data;
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
  const toggle = document.getElementById('aiChatToggle');
  const input = document.getElementById('chatInput');
  const clearBtn = document.getElementById('chatClearBtn');
  const body = document.getElementById('aiChatBody');
  const icon = document.getElementById('aiChatCollapseIcon');

  // Restore collapse state from localStorage
  if (body && icon) {
    const collapsed = localStorage.getItem('aiChatCollapsed') === 'true';
    if (collapsed) {
      body.classList.add('chat-body-collapsed');
      icon.textContent = '▶';
    } else {
      body.classList.remove('chat-body-collapsed');
      icon.textContent = '▼';
    }
  }

  if (toggle) {
    toggle.addEventListener('click', () => {
      if (body && icon) {
        body.classList.toggle('chat-body-collapsed');
        const collapsed = body.classList.contains('chat-body-collapsed');
        icon.textContent = collapsed ? '▶' : '▼';
        localStorage.setItem('aiChatCollapsed', collapsed);
      }
    });
  }

  if (input) {
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendChatMessage();
      }
    });
  }

  if (clearBtn) {
    clearBtn.addEventListener('click', () => {
      chatMessages = [];
      const container = document.getElementById('chatMessages');
      if (container) {
        container.innerHTML = getWelcomeHtml();
      }
      const ci = document.getElementById('chatInput');
      if (ci) ci.focus();
    });
  }

  const voiceBtn = document.getElementById('voiceBtn');
  if (voiceBtn) {
    const hasNativeSpeech = !!(window.SpeechRecognition || window.webkitSpeechRecognition);
    const hasMediaRecorder = !!(navigator.mediaDevices?.getUserMedia);
    if (!hasNativeSpeech && !hasMediaRecorder) {
      voiceBtn.style.display = 'none';
    } else {
      voiceBtn.addEventListener('click', () => {
        if (voiceRecognition || voiceMediaRecorder) {
          stopVoiceInput();
        } else {
          startVoiceInput();
        }
      });
    }
  }
}

let voiceRecognition = null;
let voiceSilenceTimer = null;
let voiceFinalTranscript = '';
let voiceMediaRecorder = null;
let voiceStream = null;
let voiceChunks = [];
let voiceIsNative = false;

function startVoiceInput() {
  const voiceBtn = document.getElementById('voiceBtn');
  const input = document.getElementById('chatInput');
  if (!input || !voiceBtn) return;

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

    clearTimeout(voiceSilenceTimer);
    voiceSilenceTimer = setTimeout(() => {
      if (input.value.trim()) {
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

  if (voiceRecognition) {
    try {
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
  voiceFinalTranscript = '';
  voiceChunks = [];
}

function getWelcomeHtml() {
  return `<div class="chat-message ai-message">
    <div class="chat-bubble ai-bubble welcome-bubble">
      Ask me about your expenses, or just type them to log!<br>
      <small>e.g., <em>"biryani 250"</em> or <em>"rickshaw 50 ar coffee 120"</em></small>
    </div>
  </div>`;
}

function addChatMessage(type, content, sql, data, columns, suggestions) {
  chatMessages.push({ type, content, sql, data, columns, suggestions });
  renderChatMessages();
}

const SUGGESTIONS_POOL = [
  "How does this compare to last month?",
  "Show me the breakdown by category",
  "What was my biggest expense?",
  "What did I spend most on this month?",
  "Show me all expenses over ৳1000",
  "What's my average daily spending?",
  "How much did I spend on groceries?",
  "What's my total spending on transport?",
];

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
      let h = `<div class="chat-message ai-message"><div class="chat-bubble ai-bubble">${esc(msg.content)}`;
      if (msg.data && msg.data.length) {
        h += renderDataTable(msg.columns, msg.data);
      }
      if (msg.sql) {
        h += `<div class="chat-sql-toggle" onclick="this.nextElementSibling.classList.toggle('chat-sql-visible')">Show SQL</div>`;
        h += `<pre class="chat-sql-block">${esc(msg.sql)}</pre>`;
      }
      h += `</div></div>`;
      if (msg.suggestions && msg.suggestions.length) {
        h += `<div class="chat-suggestion-chips">`;
        msg.suggestions.forEach(s => {
          const safe = s.replace(/'/g, "\\'");
          h += `<button class="chat-suggestion-chip" onclick="sendSuggestion('${safe}')">${esc(s)}</button>`;
        });
        h += `</div>`;
      }
      return h;
    }
    if (msg.type === 'expense_preview') {
      const items = msg.items || [];
      let total = items.reduce((s, i) => s + (i.amount || 0), 0);
      let h = `<div class="chat-message ai-message"><div class="chat-bubble ai-bubble">`;
      const headerDate = msg.date && msg.date !== new Date().toISOString().slice(0, 10) ? ` for ${msg.date}` : '';
      h += `<div class="chat-expense-header">I found these expenses${headerDate}:</div>`;
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
          <span class="chat-expense-desc">${esc(i.description || '')}</span>
          <span class="chat-expense-amt">৳${(i.amount || 0).toFixed(2)}</span>
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
  container.scrollTop = container.scrollHeight;
}

function renderDataTable(columns, data) {
  if (!columns || !columns.length || !data || !data.length) return '';
  const visibleCols = columns.filter(c => c.toLowerCase() !== 'id');
  if (!visibleCols.length) return '';
  const maxRows = 10;
  const rows = data.slice(0, maxRows);
  let h = '<div class="chat-data-table"><table><thead><tr>';
  visibleCols.forEach(c => { h += `<th>${esc(c)}</th>`; });
  h += '</tr></thead><tbody>';
  rows.forEach(r => {
    h += '<tr>';
    visibleCols.forEach(c => {
      let v = r[c];
      if (typeof v === 'number') {
        v = c.toLowerCase().includes('amount') || c === 'total' ? `৳${v.toFixed(2)}` : v;
      }
      h += `<td>${v != null ? esc(String(v)) : ''}</td>`;
    });
    h += '</tr>';
  });
  h += '</tbody></table>';
  if (data.length > maxRows) {
    h += `<div class="chat-table-more">+${data.length - maxRows} more</div>`;
  }
  h += '</div>';
  return h;
}

async function sendChatMessage() {
  stopVoiceInput();
  const input = document.getElementById('chatInput');
  if (!input) return;
  let message = input.value.trim();
  if (!message) return;
  input.value = '';

  // Strip leading action words for cleaner parsing
  message = message.replace(/^(add|save|log|record)\s+/i, '').trim();

  // Build conversation history (last 6 pairs)
  const history = [];
  for (const m of chatMessages) {
    if (m.type === 'ai' || m.type === 'user') {
      history.push({ role: m.type, content: m.content });
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
    const body = document.getElementById('aiChatBody');
    const icon = document.getElementById('aiChatCollapseIcon');
    if (body && body.classList.contains('chat-body-collapsed')) {
      body.classList.remove('chat-body-collapsed');
      if (icon) icon.textContent = '▼';
      localStorage.setItem('aiChatCollapsed', 'false');
    }
    return;
  }

  if (d.type === 'expense') {
    chatMessages.push({ type: 'expense_preview', items: d.items, date: d.date });
    renderChatMessages();
    const body = document.getElementById('aiChatBody');
    const icon = document.getElementById('aiChatCollapseIcon');
    if (body && body.classList.contains('chat-body-collapsed')) {
      body.classList.remove('chat-body-collapsed');
      if (icon) icon.textContent = '▼';
      localStorage.setItem('aiChatCollapsed', 'false');
    }
    return;
  }

  // Q&A response
  const suggestions = pickSuggestions(message, d.answer);
  addChatMessage('ai', d.answer || 'I found ' + (d.data ? d.data.length : 0) + ' result(s).', d.sql, d.data, d.columns, suggestions);

  const body = document.getElementById('aiChatBody');
  const icon = document.getElementById('aiChatCollapseIcon');
  if (body && body.classList.contains('chat-body-collapsed')) {
    body.classList.remove('chat-body-collapsed');
    if (icon) icon.textContent = '▼';
    localStorage.setItem('aiChatCollapsed', 'false');
  }
}

function updateChatItemCategory(msgIdx, itemIdx, newCategory) {
  const msg = chatMessages[msgIdx];
  if (!msg || msg.type !== 'expense_preview' || !msg.items[itemIdx]) return;
  msg.items[itemIdx].category = newCategory;
  msg.items[itemIdx].color = (window.categoryColors || {})[newCategory] || '#6b7280';
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
  const msg = chatMessages[index];
  if (!msg || msg.type !== 'expense_preview') return;
  chatMessages.splice(index, 1);
  renderChatMessages();
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

function pickSuggestions(question, answer) {
  const q = question.toLowerCase();
  const pool = [...SUGGESTIONS_POOL];
  const picks = [];

  // Remove the current question pattern from pool
  const filtered = pool.filter(s => {
    const sl = s.toLowerCase();
    return !q.includes(sl) || sl.includes(q);
  });

  // Pick 3 random from filtered
  for (let i = 0; i < 3 && filtered.length; i++) {
    const idx = Math.floor(Math.random() * filtered.length);
    picks.push(filtered.splice(idx, 1)[0]);
  }
  return picks;
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
  renderRoute();
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
    case 'admin-users': renderAdminUsers(); break;
    default: renderHome(1);
  }
}

document.addEventListener('DOMContentLoaded', init);
