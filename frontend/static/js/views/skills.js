// Skills view — capabilities, permissions, identity manager
// Extracted from terminal_base.html

/* drag-drop pulse animation now in skills.css */

function switchSkillsTab(tab) {
  document.querySelectorAll('.skills-tab').forEach(b => {
    b.classList.toggle('active', b.dataset.tab === tab);
  });
  document.querySelectorAll('.skills-tab-panel').forEach(p => {
    p.classList.toggle('active', p.id === 'skills-tab-' + tab);
  });
}

function loadSkillsData(win) {
  const content = win.el.querySelector('#skills-content');
  const summary = win.el.querySelector('#skills-identity-summary');
  const userSelect = win.el.querySelector('#skills-user-select');
  const permContent = win.el.querySelector('#skills-permissions-content');
  const matrixContent = win.el.querySelector('#skills-capability-matrix');
  if (!content) return;

  const auth = _getAuthState();
  if (summary) {
    const eff = auth.proxy_as || auth.acting_user;
    summary.textContent = `Acting as ${auth.acting_user}${auth.proxy_as ? ' • Proxying ' + auth.proxy_as : ''} • Effective ${eff}`;
  }

  if (userSelect) {
    const profiles = Array.isArray(window.__fridaysProfiles) ? window.__fridaysProfiles : [];
    userSelect.innerHTML = profiles.map(p => {
      const u = p.username || '';
      const active = Number(p.is_active || 0) ? '' : ' (inactive)';
      return `<option value="${u}">${u}${active}</option>`;
    }).join('');
    const current = auth.proxy_as || auth.acting_user;
    if (current && profiles.some(p => p.username === current)) {
      userSelect.value = current;
    }
  }

  fetch('/api/skills')
    .then(r => r.json())
    .then(data => {
      const skills = Array.isArray(data) ? data : (data.skills || []);
      window.__skillNames = skills.map(s => (s.name || '').trim().toLowerCase()).filter(Boolean);
      if (skills.length > 0) {
        content.innerHTML = skills.map(s => {
          const name    = _escHtml(s.name || '?');
          const desc    = _escHtml(s.description || '');
          const usage   = s.usage   ? `<div class="skill-card-usage">${_escHtml(s.usage)}</div>` : '';
          const example = s.example ? `<div class="skill-card-example">e.g. ${_escHtml(s.example)}</div>` : '';
          return `<div class="skill-card">
            <strong>${name}</strong>
            <div class="skill-card-desc">${desc}</div>
            ${usage}${example}
          </div>`;
        }).join('');
      } else {
        content.innerHTML = '<span class="skills-empty">No skills available</span>';
      }

      if (permContent) {
        loadSkillPermissionEditor();
      }
      if (matrixContent) {
        loadCapabilityMatrix(matrixContent);
      }
    })
    .catch(e => { content.innerHTML = `<span class="skills-error">Failed to load skills: ${e.message}</span>`; });
}

function loadCapabilityMatrix(host) {
  if (!host) return;
  host.innerHTML = '<p class="skills-empty">Loading capability matrix…</p>';

  fetch('/api/agents/capability-matrix')
    .then(r => r.json().then(data => ({ status: r.status, data })))
    .then(({ status, data }) => {
      if (status >= 400 || data.ok === false) {
        throw new Error(data.error || `HTTP ${status}`);
      }
      const agents = Array.isArray(data.agents) ? data.agents : [];
      if (!agents.length) {
        host.innerHTML = '<p class="skills-empty">No capability data found.</p>';
        return;
      }

      window.__capabilityMatrixData = agents;
      const highAccessOptions = agents
        .slice()
        .sort((a, b) => String(a.agent || '').localeCompare(String(b.agent || '')))
        .map(a => {
          const agentName = String(a.agent || '').trim().toLowerCase();
          if (!agentName) return '';
          const display = agentName.charAt(0).toUpperCase() + agentName.slice(1);
          return `<option value="${_escHtml(agentName)}">${_escHtml(display)}</option>`;
        })
        .join('');

      host.innerHTML = `
        <div class="cap-bar">
          <label class="skills-label">Has capability:</label>
          <input id="capability-filter-text" class="skills-input" type="text" placeholder="e.g. git_execute">
          <label class="skills-label">Min trust:</label>
          <select id="capability-filter-trust" class="skills-select">
            <option value="0">0+</option>
            <option value="1">1+</option>
            <option value="2">2+</option>
          </select>
          <label class="skills-label">Preset:</label>
          <select id="capability-filter-preset" class="skills-select">
            <option value="">Custom</option>
            <option value="git-executors">Git Executors</option>
            <option value="high-trust">High Trust (2+)</option>
            <option value="no-git">No Git Access</option>
          </select>
          <button id="capability-filter-reset" class="skills-btn">Reset</button>
          <span id="capability-filter-count" class="cap-bar-count"></span>
        </div>
        <div class="cap-bar">
          <label class="skills-label">High access agent:</label>
          <select id="capability-high-agent" class="skills-select">
            ${highAccessOptions}
          </select>
          <button id="capability-high-enable" class="cap-btn-high-enable">Enable High Access</button>
          <button id="capability-high-disable" class="cap-btn-high-disable">Disable High Access</button>
          <span class="cap-bar-bundle-info">Bundle: git_execute, propose_work, coordinate, shared_write, memory_read_all, skill_shell, skill_schedule</span>
        </div>
        <div class="cap-drag-palette">
          <label class="cap-drag-label">⇣ Drag to assign:</label>
          ${_ALL_CAPS.map(c => `<span class="cap-pill-palette" draggable="true" data-cap-drag="${c}">${c}</span>`).join(' ')}
          <span class="cap-drag-hint">drag pills onto agent rows below</span>
        </div>
        <div id="capability-matrix-list"></div>
      `;

      const filterText = host.querySelector('#capability-filter-text');
      const filterTrust = host.querySelector('#capability-filter-trust');
      const filterPreset = host.querySelector('#capability-filter-preset');
      const filterReset = host.querySelector('#capability-filter-reset');
      const highEnable = host.querySelector('#capability-high-enable');
      const highDisable = host.querySelector('#capability-high-disable');

      const rerender = () => renderCapabilityMatrixList(host);
      if (filterText && !filterText.dataset.bound) {
        filterText.dataset.bound = '1';
        filterText.addEventListener('input', rerender);
      }
      if (filterTrust && !filterTrust.dataset.bound) {
        filterTrust.dataset.bound = '1';
        filterTrust.addEventListener('change', rerender);
      }
      if (filterPreset && !filterPreset.dataset.bound) {
        filterPreset.dataset.bound = '1';
        filterPreset.addEventListener('change', () => {
          applyCapabilityPreset(host, String(filterPreset.value || ''));
          rerender();
        });
      }
      if (filterReset && !filterReset.dataset.bound) {
        filterReset.dataset.bound = '1';
        filterReset.addEventListener('click', () => {
          if (filterText) filterText.value = '';
          if (filterTrust) filterTrust.value = '0';
          if (filterPreset) filterPreset.value = '';
          rerender();
        });
      }
      if (highEnable && !highEnable.dataset.bound) {
        highEnable.dataset.bound = '1';
        highEnable.addEventListener('click', () => toggleHighAccessBundle(host, true));
      }
      if (highDisable && !highDisable.dataset.bound) {
        highDisable.dataset.bound = '1';
        highDisable.addEventListener('click', () => toggleHighAccessBundle(host, false));
      }

      renderCapabilityMatrixList(host);

      // Bind drag on the palette pills
      host.querySelectorAll('[data-cap-drag]').forEach(pill => {
        pill.addEventListener('dragstart', e => {
          e.dataTransfer.setData('text/plain', pill.dataset.capDrag);
          e.dataTransfer.effectAllowed = 'copy';
        });
      });
    })
    .catch(e => {
      host.innerHTML = `<p class="skills-error">Failed to load capability matrix: ${_escHtml(e.message || String(e))}</p>`;
    });
}

function renderCapabilityMatrixList(host) {
  if (!host) return;
  const listEl = host.querySelector('#capability-matrix-list');
  const countEl = host.querySelector('#capability-filter-count');
  if (!listEl) return;

  const allAgents = Array.isArray(window.__capabilityMatrixData) ? window.__capabilityMatrixData : [];
  const needCap = String(host.querySelector('#capability-filter-text')?.value || '').trim().toLowerCase();
  const minTrust = Number(host.querySelector('#capability-filter-trust')?.value || 0);
  const preset = String(host.querySelector('#capability-filter-preset')?.value || '');

  const filtered = allAgents.map(item => {
    const caps = Array.isArray(item.capabilities) ? item.capabilities : [];
    const capsByTrust = caps.filter(cap => Number(cap.trust_level || 0) >= minTrust);
    const match = !needCap || capsByTrust.some(cap => String(cap.capability || '').toLowerCase().includes(needCap));
    const hasGit = caps.some(cap => ['git_execute', 'git_propose'].includes(String(cap.capability || '').toLowerCase()));
    const presetMatch = !preset ||
      (preset === 'git-executors' && caps.some(cap => String(cap.capability || '').toLowerCase() === 'git_execute')) ||
      (preset === 'high-trust' && caps.some(cap => Number(cap.trust_level || 0) >= 2)) ||
      (preset === 'no-git' && !hasGit);
    return {
      ...item,
      _caps: capsByTrust,
      _match: match && presetMatch,
    };
  }).filter(item => item._match);

  if (countEl) countEl.textContent = `${filtered.length} of ${allAgents.length} agents`;

  if (!filtered.length) {
    listEl.innerHTML = '<p class="skills-empty">No agents match current filters.</p>';
    return;
  }

  listEl.innerHTML = filtered.map(item => {
    const name = _escHtml(String(item.agent || '?'));
    const caps = item._caps || [];
    const agent = String(item.agent || '').toLowerCase();
    const hasGitExecute = caps.some(cap => String(cap.capability || '').toLowerCase() === 'git_execute');
    const chips = caps.length
      ? caps.map(cap => {
          const cname = _escHtml(String(cap.capability || '?'));
          const trust = Number(cap.trust_level || 0);
          return `<span class="cap-pill" draggable="true" data-cap-drag="${_escHtml(cap.capability || '')}" title="trust ${trust} — drag to assign">${cname} · t${trust}</span>`;
        }).join(' ')
      : '<span class="skills-empty">no capabilities at current trust filter</span>';

    return `<div class="cap-agent-row" data-cap-agent="${_escHtml(agent)}">
      <div class="cap-agent-header">
        <strong>${name}</strong>
        <span class="cap-agent-count">${Number(item.granted_count || 0)} granted</span>
      </div>
      <div class="cap-agent-caps">${chips}</div>
      <div class="cap-agent-actions">
        <button class="${hasGitExecute ? 'cap-btn-disable' : 'cap-btn-enable'}" onclick="toggleSingleAgentCapability('${agent}','git_execute',${hasGitExecute ? 'false' : 'true'})">${hasGitExecute ? 'Disable git_execute' : 'Enable git_execute'}</button>
      </div>
    </div>`;
  }).join('');

  // Bind drag-drop for capability assignment (Tier 2.2)
  _bindCapDragDrop(listEl);
}

function applyCapabilityPreset(host, preset) {
  if (!host) return;
  const filterText = host.querySelector('#capability-filter-text');
  const filterTrust = host.querySelector('#capability-filter-trust');
  if (!filterText || !filterTrust) return;

  if (preset === 'git-executors') {
    filterText.value = 'git_execute';
    filterTrust.value = '0';
    return;
  }
  if (preset === 'high-trust') {
    filterText.value = '';
    filterTrust.value = '2';
    return;
  }
  if (preset === 'no-git') {
    filterText.value = '';
    filterTrust.value = '0';
  }
}

function _highAccessCapabilityBundle() {
  return [
    'git_propose',
    'git_execute',
    'propose_work',
    'coordinate',
    'shared_write',
    'memory_read_all',
    'skill_shell',
    'skill_schedule',
  ];
}

async function toggleHighAccessBundle(host, enabled) {
  const agentSelect = host?.querySelector('#capability-high-agent');
  const agent = String(agentSelect?.value || '').trim().toLowerCase();
  if (!agent) {
    showToast('Select an agent first', 'error');
    return;
  }
  await setAgentCapabilities(agent, _highAccessCapabilityBundle(), enabled);
  await loadCapabilityMatrix(host);
}

async function toggleSingleAgentCapability(agent, capability, enabled) {
  const host = document.getElementById('skills-capability-matrix');
  if (!host) return;
  await setAgentCapabilities(String(agent || '').toLowerCase(), [capability], enabled);
  await loadCapabilityMatrix(host);
}

async function setAgentCapabilities(agent, capabilities, enabled) {
  if (!agent || !Array.isArray(capabilities) || !capabilities.length) return;
  const auth = _getAuthState();
  const effective = auth.proxy_as || auth.acting_user;
  if (effective !== 'ghost') {
    showToast('Capability changes require Ghost identity. Use Identity switch first.', 'error');
    return;
  }
  try {
    const res = await fetch('/api/agents/capabilities', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ..._authPayload(),
        agent,
        capabilities,
        enabled: !!enabled,
        notes: enabled ? 'ui_high_access_enable' : 'ui_high_access_disable',
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) {
      throw new Error(data.error || `HTTP ${res.status}`);
    }
    showToast(`${agent}: ${enabled ? 'enabled' : 'disabled'} ${capabilities.length} capability${capabilities.length === 1 ? '' : 'ies'}`, 'success');
  } catch (e) {
    showToast(`Capability update failed: ${e.message || e}`, 'error');
  }
}

function _getAuthState() {
  const raw = localStorage.getItem('fridays-auth-state');
  try {
    const parsed = raw ? JSON.parse(raw) : {};
    return {
      acting_user: (parsed.acting_user || 'ghost').toLowerCase(),
      proxy_as: (parsed.proxy_as || '').toLowerCase(),
    };
  } catch {
    return { acting_user: 'ghost', proxy_as: '' };
  }
}

function _saveAuthState(state) {
  const normalized = {
    acting_user: (state.acting_user || 'ghost').toLowerCase(),
    proxy_as: (state.proxy_as || '').toLowerCase(),
  };
  localStorage.setItem('fridays-auth-state', JSON.stringify(normalized));
  return normalized;
}

function _authPayload() {
  const s = _getAuthState();
  return {
    acting_user: s.acting_user,
    proxy_as: s.proxy_as,
  };
}

function _renderIdentityPill() {
  const label = document.getElementById('auth-user-pill-label');
  if (!label) return;
  const s = _getAuthState();
  label.textContent = s.proxy_as ? `${s.acting_user} ▶ ${s.proxy_as}` : s.acting_user;
}

function _syncAuthStateWithProfiles() {
  const profiles = Array.isArray(window.__fridaysProfiles) ? window.__fridaysProfiles : [];
  if (!profiles.length) return;
  const names = new Set(profiles.map(p => (p.username || '').toLowerCase()));
  const state = _getAuthState();
  if (!names.has(state.acting_user)) {
    state.acting_user = names.has('ghost') ? 'ghost' : (profiles[0].username || 'ghost');
  }
  if (state.proxy_as && !names.has(state.proxy_as)) {
    state.proxy_as = '';
  }
  _saveAuthState(state);
}

function loadAuthProfiles(refreshSkills = false) {
  fetch('/api/auth/profiles?include_inactive=1')
    .then(r => r.json())
    .then(data => {
      window.__fridaysProfiles = Array.isArray(data.profiles) ? data.profiles : [];
      _syncAuthStateWithProfiles();
      _renderIdentityPill();
      if (refreshSkills && window.windows && window.windows.skills) {
        loadSkillsData(window.windows.skills);
      }
    })
    .catch(e => {
      console.error('Failed to load profiles:', e);
      _renderIdentityPill();
    });
}

function openIdentityManager() {
  // Remove existing panel if open (toggle behaviour)
  const existing = document.getElementById('identity-manager-panel');
  if (existing) { existing.remove(); return; }

  const profiles = Array.isArray(window.__fridaysProfiles) ? window.__fridaysProfiles : [];
  if (!profiles.length) {
    showToast('No user profiles loaded yet', 'error');
    return;
  }
  const state = _getAuthState();

  // Create inline panel anchored to the pill button
  const pill = document.getElementById('auth-user-pill');
  const panel = document.createElement('div');
  panel.id = 'identity-manager-panel';
  panel.style.cssText = 'position:fixed;top:42px;right:12px;z-index:10001;background:var(--card);border:1px solid var(--border);border-radius:10px;box-shadow:0 6px 24px rgba(0,0,0,0.35);padding:12px 14px;min-width:220px;max-width:300px;font-size:11px;color:var(--text);';

  const actingOptions = profiles.map(p => {
    const sel = p.username === state.acting_user ? ' selected' : '';
    return `<option value="${_escHtml(p.username)}"${sel}>${_escHtml(p.display_name || p.username)}</option>`;
  }).join('');
  const proxyOptions = `<option value="">None</option>` + profiles.map(p => {
    const sel = p.username === state.proxy_as ? ' selected' : '';
    return `<option value="${_escHtml(p.username)}"${sel}>${_escHtml(p.display_name || p.username)}</option>`;
  }).join('');

  panel.innerHTML =
    `<div style="font-weight:700;margin-bottom:8px;">Identity</div>` +
    `<label style="display:block;margin-bottom:3px;color:var(--text-dim);">Acting as</label>` +
    `<select id="idm-acting" style="width:100%;padding:4px 6px;border-radius:6px;border:1px solid var(--border);background:var(--bg);color:var(--text);font-size:11px;margin-bottom:8px;">${actingOptions}</select>` +
    `<label style="display:block;margin-bottom:3px;color:var(--text-dim);">Proxy as</label>` +
    `<select id="idm-proxy" style="width:100%;padding:4px 6px;border-radius:6px;border:1px solid var(--border);background:var(--bg);color:var(--text);font-size:11px;margin-bottom:10px;">${proxyOptions}</select>` +
    `<div style="display:flex;gap:6px;justify-content:flex-end;">` +
      `<button id="idm-apply" style="padding:4px 12px;border-radius:6px;border:1px solid var(--accent);background:var(--accent);color:#fff;font-size:11px;cursor:pointer;">Apply</button>` +
      `<button id="idm-close" style="padding:4px 10px;border-radius:6px;border:1px solid var(--border);background:transparent;color:var(--text-dim);font-size:11px;cursor:pointer;">Close</button>` +
    `</div>`;

  document.body.appendChild(panel);

  const close = () => panel.remove();
  panel.querySelector('#idm-close').addEventListener('click', close);
  panel.querySelector('#idm-apply').addEventListener('click', () => {
    const actingNorm = (panel.querySelector('#idm-acting').value || 'ghost').toLowerCase();
    const proxyNorm = (panel.querySelector('#idm-proxy').value || '').toLowerCase();
    _saveAuthState({ acting_user: actingNorm, proxy_as: proxyNorm });
    _renderIdentityPill();
    if (typeof winManager !== 'undefined' && winManager.windows && winManager.windows.get('skills')) {
      loadSkillsData(winManager.windows.get('skills'));
    }
    showToast(`Identity set: ${actingNorm}${proxyNorm ? ' ▶ ' + proxyNorm : ''}`, 'success');
    close();
  });

  // Close on outside click (delay to avoid immediate close)
  setTimeout(() => {
    const outsideClick = (e) => {
      if (!panel.contains(e.target) && e.target !== pill && !pill.contains(e.target)) {
        close();
        document.removeEventListener('click', outsideClick);
      }
    };
    document.addEventListener('click', outsideClick);
  }, 100);
}

// Escape helper for identity manager HTML attributes
function _escHtml(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function createUserProfileFromSkills() {
  const usernameEl = document.getElementById('skills-new-user');
  const displayEl = document.getElementById('skills-new-display');
  const typeEl = document.getElementById('skills-new-type');
  if (!usernameEl || !typeEl) return;

  const username = (usernameEl.value || '').trim().toLowerCase();
  const displayName = (displayEl && displayEl.value) ? displayEl.value.trim() : username;
  const userType = (typeEl.value || 'human').trim().toLowerCase();
  if (!username) {
    showToast('Username required', 'error');
    return;
  }

  fetch('/api/auth/profiles', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ..._authPayload(),
      username,
      display_name: displayName,
      user_type: userType,
      linked_agent: userType === 'agent' ? username : '',
      is_active: true,
      can_proxy: false,
    })
  })
    .then(r => r.json().then(data => ({ status: r.status, data })))
    .then(({ status, data }) => {
      if (status >= 400 || data.ok === false) {
        throw new Error(data.error || `HTTP ${status}`);
      }
      usernameEl.value = '';
      if (displayEl) displayEl.value = '';
      showToast(`User created: ${username}`, 'success');
      loadAuthProfiles(true);
    })
    .catch(e => showToast(`Create user failed: ${e.message}`, 'error'));
}

function loadSkillPermissionEditor() {
  const host = document.getElementById('skills-permissions-content');
  const selector = document.getElementById('skills-user-select');
  if (!host || !selector) return;

  const username = (selector.value || '').trim().toLowerCase();
  if (!username) {
    host.innerHTML = '<p class="skills-empty">Select a user to manage permissions.</p>';
    return;
  }

  const skillNames = Array.isArray(window.__skillNames) ? window.__skillNames : [];

  fetch('/api/skills/permissions?username=' + encodeURIComponent(username))
    .then(r => r.json().then(data => ({ status: r.status, data })))
    .then(({ status, data }) => {
      if (status >= 400 || data.ok === false) {
        throw new Error(data.error || `HTTP ${status}`);
      }
      const perms = Array.isArray(data.permissions) ? data.permissions : [];
      const map = {};
      perms.forEach(p => { map[(p.skill_name || '').toLowerCase()] = !!p.allowed; });
      const auth = _getAuthState();
      const readonly = auth.acting_user !== 'ghost';

      host.innerHTML = skillNames.map(skill => {
        const explicit = Object.prototype.hasOwnProperty.call(map, skill);
        const allowed = explicit ? !!map[skill] : true;
        const hint = explicit ? 'explicit' : 'default allow';
        return `<label class="perm-row">
          <div>
            <div class="perm-name">${skill}</div>
            <div class="perm-hint">${hint}</div>
          </div>
          <input type="checkbox" ${allowed ? 'checked' : ''} ${readonly ? 'disabled' : ''} onchange="setSkillPermissionToggle(${JSON.stringify(username)},${JSON.stringify(skill)},this.checked)">
        </label>`;
      }).join('') + (readonly ? '<div class="perm-note">Only ghost can update permissions.</div>' : '');
    })
    .catch(e => {
      host.innerHTML = `<div class="skills-error">Failed to load permissions: ${e.message}</div>`;
    });
}

function setSkillPermissionToggle(username, skillName, allowed) {
  fetch('/api/skills/permissions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ..._authPayload(),
      username,
      skill_name: skillName,
      allowed: !!allowed,
    })
  })
    .then(r => r.json().then(data => ({ status: r.status, data })))
    .then(({ status, data }) => {
      if (status >= 400 || data.ok === false) {
        throw new Error(data.error || `HTTP ${status}`);
      }
      showToast(`Permission updated: ${username}/${skillName}=${allowed ? 'allow' : 'deny'}`, 'success');
      loadSkillPermissionEditor();
    })
    .catch(e => {
      showToast(`Permission update failed: ${e.message}`, 'error');
      loadSkillPermissionEditor();
    });
}

// ── Capability drag-drop (Tier 2.2) ──────────────────────────────────────────
const _ALL_CAPS = [
  'ticket_create','ticket_close','sandpit_read','sandpit_write',
  'memory_write_own','memory_read_all','shared_read','shared_write',
  'skill_shell','skill_schedule','git_propose','git_execute',
  'propose_work','coordinate','file_read',
];

function _bindCapDragDrop(listEl) {
  // Drag start on capability pills
  listEl.querySelectorAll('[data-cap-drag]').forEach(pill => {
    pill.addEventListener('dragstart', e => {
      e.dataTransfer.setData('text/plain', pill.dataset.capDrag);
      e.dataTransfer.effectAllowed = 'copy';
    });
  });

  // Drop on agent rows
  listEl.querySelectorAll('.cap-agent-row').forEach(row => {
    row.addEventListener('dragover', e => {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'copy';
      row.classList.add('cap-drag-over');
    });
    row.addEventListener('dragleave', () => {
      row.classList.remove('cap-drag-over');
    });
    row.addEventListener('drop', e => {
      e.preventDefault();
      row.classList.remove('cap-drag-over');
      const cap = e.dataTransfer.getData('text/plain');
      const agent = row.dataset.capAgent;
      if (cap && agent) {
        toggleSingleAgentCapability(agent, cap, true);
      }
    });
  });
}

// _escHtml defined once at line ~475 — do not duplicate

