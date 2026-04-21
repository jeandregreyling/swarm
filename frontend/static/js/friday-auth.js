/* friday-auth.js — Login, registration, session, and user management UI
 *
 * On page load, checks /api/auth/me.
 * If not logged in, shows login overlay.
 * If owner has no password, shows first-time setup.
 * Owner can manage users from a panel inside the Skills/Identity tile.
 */
(function () {
  'use strict';

  let _currentUser = null;
  const LOGIN_PREFS_KEY = 'fridays-login-prefs';

  function _loadLoginPrefs() {
    try {
      const raw = JSON.parse(localStorage.getItem(LOGIN_PREFS_KEY) || '{}');
      return {
        username: String(raw.username || '').trim(),
        remember: !!raw.remember,
      };
    } catch (_) {
      return { username: '', remember: false };
    }
  }

  function _saveLoginPrefs(username, remember) {
    if (!remember) {
      localStorage.removeItem(LOGIN_PREFS_KEY);
      return;
    }
    localStorage.setItem(LOGIN_PREFS_KEY, JSON.stringify({ username: String(username || '').trim().toLowerCase(), remember: true }));
  }

  // ── Bootstrap ────────────────────────────────────────────────────────────
  window.addEventListener('DOMContentLoaded', () => _authCheck());

  function _authCheck() {
    fetch('/api/auth/me')
      .then(r => r.json())
      .then(data => {
        if (data.user) {
          _currentUser = data.user;
          window.__fridayUser = data.user;
          // Sync identity pill with auth session on page load
          try {
            const authState = { acting_user: (data.user.username || 'ghost').toLowerCase(), proxy_as: '' };
            const existing = JSON.parse(localStorage.getItem('fridays-auth-state') || '{}');
            // Only overwrite if still default or stale
            if (!existing.acting_user || existing.acting_user === 'ghost') {
              localStorage.setItem('fridays-auth-state', JSON.stringify(authState));
            }
            if (typeof _renderIdentityPill === 'function') _renderIdentityPill();
          } catch (_) {}
          _hideAuthOverlay();
          _renderUserBadge();
        } else {
          // Check if first-time setup needed
          return fetch('/api/auth/setup-status')
            .then(r => r.json())
            .then(status => {
              if (!status.owner_has_password) {
                _showSetup();
              } else {
                _showLogin();
              }
            });
        }
      })
      .catch(() => {
        // Auth endpoint not available — allow through (backward compat)
        _hideAuthOverlay();
      });
  }

  // ── Overlay management ──────────────────────────────────────────────────
  function _getOrCreateOverlay() {
    let overlay = document.getElementById('friday-auth-overlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'friday-auth-overlay';
      overlay.className = 'friday-auth-overlay';
      document.body.appendChild(overlay);
    }
    return overlay;
  }

  function _hideAuthOverlay() {
    const overlay = document.getElementById('friday-auth-overlay');
    if (overlay) overlay.remove();
  }

  // ── First-time setup ───────────────────────────────────────────────────
  function _showSetup() {
    const overlay = _getOrCreateOverlay();
    overlay.innerHTML = `
      <div class="friday-auth-card">
        <div class="friday-auth-logo">
          <h1>Friday</h1>
          <p>First-time setup — create your owner account</p>
        </div>
        <div class="friday-auth-form" id="auth-setup-form">
          <label>Display Name</label>
          <input type="text" id="setup-display" placeholder="Your name" autocomplete="name">
          <label>Password</label>
          <input type="password" id="setup-pass" placeholder="Min 6 characters" autocomplete="new-password">
          <label>Confirm Password</label>
          <input type="password" id="setup-pass2" placeholder="Confirm password" autocomplete="new-password">
          <div id="setup-msg"></div>
          <button class="friday-auth-submit" id="setup-btn">Create Owner Account</button>
          <div class="friday-auth-setup-note">
            This account has full control. Other users will need your approval to join.
          </div>
        </div>
      </div>
    `;
    const btn = overlay.querySelector('#setup-btn');
    const pass = overlay.querySelector('#setup-pass');
    const pass2 = overlay.querySelector('#setup-pass2');
    const display = overlay.querySelector('#setup-display');
    const msg = overlay.querySelector('#setup-msg');

    btn.addEventListener('click', () => {
      const p = pass.value.trim();
      const p2 = pass2.value.trim();
      const dn = display.value.trim();
      if (p.length < 6) return _setMsg(msg, 'Password must be at least 6 characters', 'error');
      if (p !== p2) return _setMsg(msg, 'Passwords do not match', 'error');
      btn.disabled = true;
      btn.textContent = 'Setting up...';
      fetch('/api/auth/setup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: p, display_name: dn }),
      })
      .then(r => r.json())
      .then(data => {
        if (data.ok) {
          _currentUser = data.user;
          window.__fridayUser = data.user;
          _hideAuthOverlay();
          _renderUserBadge();
        } else {
          _setMsg(msg, data.error || 'Setup failed', 'error');
          btn.disabled = false;
          btn.textContent = 'Create Owner Account';
        }
      })
      .catch(() => {
        _setMsg(msg, 'Network error', 'error');
        btn.disabled = false;
        btn.textContent = 'Create Owner Account';
      });
    });

    // Enter key
    [pass, pass2].forEach(el => el.addEventListener('keydown', e => {
      if (e.key === 'Enter') btn.click();
    }));
  }

  // ── Login / Register ──────────────────────────────────────────────────
  function _showLogin() {
    const overlay = _getOrCreateOverlay();
    const loginPrefs = _loadLoginPrefs();
    overlay.innerHTML = `
      <div class="friday-auth-card">
        <div class="friday-auth-logo">
          <h1>Friday</h1>
          <p>Sign in to continue</p>
        </div>
        <div class="friday-auth-tabs">
          <button class="friday-auth-tab active" data-tab="login">Sign In</button>
          <button class="friday-auth-tab" data-tab="register">Register</button>
        </div>
        <div id="auth-login-panel" class="friday-auth-form">
          <label>Username, email, or display name</label>
          <input type="text" id="login-user" placeholder="Username, email, or display name" autocomplete="username" value="${_esc(loginPrefs.username)}">
          <label>Password</label>
          <input type="password" id="login-pass" placeholder="Password" autocomplete="current-password">
          <label class="friday-auth-check">
            <input type="checkbox" id="login-remember" ${loginPrefs.remember ? 'checked' : ''}>
            <span>Remember me on this device</span>
          </label>
          <div class="friday-auth-setup-note">Username can be your account name, email, or display name. Password stays in the browser password manager, not local storage.</div>
          <div id="login-msg"></div>
          <button class="friday-auth-submit" id="login-btn">Sign In</button>
        </div>
        <div id="auth-register-panel" class="friday-auth-form" style="display:none;">
          <label>Username</label>
          <input type="text" id="reg-user" placeholder="lowercase, no spaces" autocomplete="username">
          <label>Display Name</label>
          <input type="text" id="reg-display" placeholder="Your name" autocomplete="name">
          <label>Password</label>
          <input type="password" id="reg-pass" placeholder="Min 6 characters" autocomplete="new-password">
          <div id="reg-msg"></div>
          <button class="friday-auth-submit" id="reg-btn">Request Access</button>
          <div class="friday-auth-setup-note">
            Your account will need owner approval before you can sign in.
          </div>
        </div>
      </div>
    `;

    // Tab switching
    overlay.querySelectorAll('.friday-auth-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        overlay.querySelectorAll('.friday-auth-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        const isLogin = tab.dataset.tab === 'login';
        overlay.querySelector('#auth-login-panel').style.display = isLogin ? 'flex' : 'none';
        overlay.querySelector('#auth-register-panel').style.display = isLogin ? 'none' : 'flex';
      });
    });

    // Login
    const loginBtn = overlay.querySelector('#login-btn');
    const loginUser = overlay.querySelector('#login-user');
    const loginPass = overlay.querySelector('#login-pass');
    const loginRemember = overlay.querySelector('#login-remember');
    const loginMsg = overlay.querySelector('#login-msg');
    loginBtn.addEventListener('click', () => {
      const u = loginUser.value.trim().toLowerCase();
      const p = loginPass.value.trim();
      const remember = !!loginRemember.checked;
      if (!u || !p) return _setMsg(loginMsg, 'Enter username and password', 'error');
      loginBtn.disabled = true;
      loginBtn.textContent = 'Signing in...';
      fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: u, password: p, remember }),
      })
      .then(r => r.json())
      .then(data => {
        if (data.ok) {
          _currentUser = data.user;
          window.__fridayUser = data.user;
          _saveLoginPrefs(u, remember);
          // Sync identity pill with login session
          try {
            const authState = { acting_user: (data.user.username || 'ghost').toLowerCase(), proxy_as: '' };
            localStorage.setItem('fridays-auth-state', JSON.stringify(authState));
            if (typeof _renderIdentityPill === 'function') _renderIdentityPill();
          } catch (_) {}
          _hideAuthOverlay();
          _renderUserBadge();
        } else {
          _setMsg(loginMsg, data.error || 'Login failed', 'error');
          loginBtn.disabled = false;
          loginBtn.textContent = 'Sign In';
        }
      })
      .catch(() => {
        _setMsg(loginMsg, 'Network error', 'error');
        loginBtn.disabled = false;
        loginBtn.textContent = 'Sign In';
      });
    });
    loginPass.addEventListener('keydown', e => { if (e.key === 'Enter') loginBtn.click(); });

    // Register
    const regBtn = overlay.querySelector('#reg-btn');
    const regUser = overlay.querySelector('#reg-user');
    const regDisplay = overlay.querySelector('#reg-display');
    const regPass = overlay.querySelector('#reg-pass');
    const regMsg = overlay.querySelector('#reg-msg');
    regBtn.addEventListener('click', () => {
      const u = regUser.value.trim().toLowerCase();
      const p = regPass.value.trim();
      const dn = regDisplay.value.trim();
      if (!u || !p) return _setMsg(regMsg, 'Fill in all fields', 'error');
      if (p.length < 6) return _setMsg(regMsg, 'Password must be at least 6 characters', 'error');
      regBtn.disabled = true;
      regBtn.textContent = 'Registering...';
      fetch('/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: u, password: p, display_name: dn }),
      })
      .then(r => r.json())
      .then(data => {
        if (data.ok) {
          _setMsg(regMsg, data.message || 'Registered! Waiting for approval.', 'success');
          regBtn.textContent = 'Registered';
        } else {
          _setMsg(regMsg, data.error || 'Registration failed', 'error');
          regBtn.disabled = false;
          regBtn.textContent = 'Request Access';
        }
      })
      .catch(() => {
        _setMsg(regMsg, 'Network error', 'error');
        regBtn.disabled = false;
        regBtn.textContent = 'Request Access';
      });
    });
    regPass.addEventListener('keydown', e => { if (e.key === 'Enter') regBtn.click(); });
  }

  // ── User badge in header ─────────────────────────────────────────────
  function _renderUserBadge() {
    // Insert after env badge if present, or into the header bar
    let host = document.querySelector('.home-chat-bar-right') || document.querySelector('.tm-header');
    if (!host) return;
    let badge = document.getElementById('friday-user-badge');
    if (badge) badge.remove();
    badge = document.createElement('div');
    badge.id = 'friday-user-badge';
    badge.className = 'friday-user-badge';
    badge.title = 'Click to manage account';
    const u = _currentUser;
    badge.innerHTML = `
      <span>${_esc(u.display_name || u.username)}</span>
      <span class="user-role">${_esc(u.role)}</span>
    `;
    badge.addEventListener('click', _showUserMenu);
    host.prepend(badge);
  }

  function _showUserMenu() {
    // Simple dropdown: Logout, and if owner, Manage Users
    let menu = document.getElementById('friday-user-menu');
    if (menu) { menu.remove(); return; }
    menu = document.createElement('div');
    menu.id = 'friday-user-menu';
    menu.style.cssText = 'position:fixed;top:40px;right:12px;z-index:10000;background:var(--card);border:1px solid var(--border);border-radius:8px;box-shadow:0 4px 20px rgba(0,0,0,0.3);padding:6px 0;min-width:160px;animation:authFadeIn 0.2s ease-out;';
    const items = [];
    items.push(`<div style="padding:8px 14px;font-size:11px;color:var(--text-dim);border-bottom:1px solid var(--border);">Signed in as <strong>${_esc(_currentUser.username)}</strong></div>`);
    if (_currentUser.role === 'owner') {
      items.push(`<button onclick="fridayManageUsers()" style="display:block;width:100%;text-align:left;padding:8px 14px;background:none;border:none;color:var(--text);font-size:11px;cursor:pointer;">Manage Users</button>`);
    }
    items.push(`<button onclick="fridayLogout()" style="display:block;width:100%;text-align:left;padding:8px 14px;background:none;border:none;color:#f44336;font-size:11px;cursor:pointer;">Sign Out</button>`);
    menu.innerHTML = items.join('');
    document.body.appendChild(menu);
    // Close on outside click
    setTimeout(() => {
      const close = (e) => { if (!menu.contains(e.target)) { menu.remove(); document.removeEventListener('click', close); } };
      document.addEventListener('click', close);
    }, 50);
  }

  // ── Global functions ──────────────────────────────────────────────────
  window.fridayLogout = function () {
    const menu = document.getElementById('friday-user-menu');
    if (menu) menu.remove();
    fetch('/api/auth/logout', { method: 'POST' })
      .then(() => { window.location.reload(); })
      .catch(() => { window.location.reload(); });
  };

  window.fridayManageUsers = function () {
    const menu = document.getElementById('friday-user-menu');
    if (menu) menu.remove();
    // Open user management in a window if WindowManager available, else overlay
    if (typeof openWindow === 'function') {
      openWindow('users', 'User Management');
    } else {
      _showUsersOverlay();
    }
  };

  window.fridayGetCurrentUser = function () {
    return _currentUser;
  };

  // ── Load users into a WindowManager window ───────────────────────────
  window._loadUsersWindowContent = function (win) {
    // win is the window state object; win.el is the DOM element
    const el = win && win.el ? win.el : win;
    if (!el) return;
    const body = el.querySelector('.window-content');
    if (!body) return;
    body.innerHTML = '<div style="padding:12px;"><div style="font-size:13px;font-weight:700;margin-bottom:10px;color:var(--text);">User Management</div><div id="friday-users-list" style="color:var(--text-dim);font-size:11px;">Loading...</div></div>';
    _loadUsersList();
  };

  // ── User management overlay (owner only) ─────────────────────────────
  function _showUsersOverlay() {
    let panel = document.getElementById('friday-users-overlay');
    if (panel) { panel.remove(); return; }
    panel = document.createElement('div');
    panel.id = 'friday-users-overlay';
    panel.style.cssText = 'position:fixed;top:60px;right:12px;z-index:9998;background:var(--card);border:1px solid var(--border);border-radius:12px;box-shadow:0 8px 40px rgba(0,0,0,0.4);padding:16px;min-width:340px;max-width:420px;animation:authCardIn 0.3s ease-out;';
    panel.innerHTML = '<div style="font-size:13px;font-weight:700;margin-bottom:10px;color:var(--text);">User Management</div><div id="friday-users-list" style="color:var(--text-dim);font-size:11px;">Loading...</div><button onclick="document.getElementById(\'friday-users-overlay\').remove()" style="margin-top:10px;padding:5px 12px;border-radius:6px;border:1px solid var(--border);background:transparent;color:var(--text-dim);font-size:10px;cursor:pointer;">Close</button>';
    document.body.appendChild(panel);
    _loadUsersList();
  }

  function _loadUsersList() {
    const host = document.getElementById('friday-users-list');
    if (!host) return;
    fetch('/api/auth/users')
      .then(r => r.json())
      .then(data => {
        if (!data.ok || !data.users) { host.textContent = 'Failed to load'; return; }
        if (data.users.length === 0) { host.textContent = 'No users found'; return; }
        host.innerHTML = data.users.map(u => {
          const pending = !u.approved;
          const status = pending ? '<span class="friday-pending-badge">PENDING</span>' : (u.is_active ? '' : '<span style="color:#f44336;font-size:9px;">disabled</span>');
          const actions = [];
          if (pending) {
            actions.push(`<button class="approve" onclick="fridayApproveUser('${_esc(u.username)}')">Approve</button>`);
            actions.push(`<button class="reject" onclick="fridayRejectUser('${_esc(u.username)}')">Reject</button>`);
          } else if (u.username !== 'ghost') {
            actions.push(`<button onclick="fridayRejectUser('${_esc(u.username)}')">Disable</button>`);
          }
          return `<div class="friday-user-row">
            <div class="friday-user-info">
              <span class="name">${_esc(u.display_name || u.username)} ${status}</span>
              <span class="meta">${_esc(u.username)} · ${_esc(u.role)} · ${_esc(u.created_at || '')}</span>
            </div>
            <div class="friday-user-actions">${actions.join('')}</div>
          </div>`;
        }).join('');
      })
      .catch(() => { host.textContent = 'Error loading users'; });
  }

  window.fridayApproveUser = function (username) {
    fetch(`/api/auth/users/${encodeURIComponent(username)}/approve`, { method: 'POST' })
      .then(r => r.json())
      .then(data => { if (data.ok) _loadUsersList(); })
      .catch(() => {});
  };

  window.fridayRejectUser = function (username) {
    fetch(`/api/auth/users/${encodeURIComponent(username)}/reject`, { method: 'POST' })
      .then(r => r.json())
      .then(data => { if (data.ok) _loadUsersList(); })
      .catch(() => {});
  };

  // ── Helpers ──────────────────────────────────────────────────────────
  function _setMsg(el, text, type) {
    if (!el) return;
    el.className = type === 'success' ? 'friday-auth-success' : 'friday-auth-error';
    el.textContent = text;
  }

  function _esc(s) {
    const d = document.createElement('div');
    d.textContent = s || '';
    return d.innerHTML;
  }

})();
