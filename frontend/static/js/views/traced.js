/* traced.js — Session 29 Traced window. History view of spine events.
 *
 * Renders into <div id="traced-panel"> inside the view-traced template.
 * Uses the shared window.__trace bus for live updates.
 *
 * Public: loadTracedPanel(filter)
 */
(function () {
  const EVENT_KINDS = [
    'relay_step', 'watchdog', 'checkpoint', 'ticket',
    'testlab', 'route', 'chat', 'system', 'guardian',
  ];

  const state = {
    kinds: new Set(),              // empty = all
    minSeverity: 'info',
    limit: 200,
    events: [],
    selected: null,                // event id
    query: '',
  };

  window.loadTracedPanel = function loadTracedPanel(filter) {
    filter = filter || {};
    if (filter.kinds) state.kinds = new Set(filter.kinds);
    if (filter.minSeverity) state.minSeverity = filter.minSeverity;
    if (filter.highlight) state.selected = filter.highlight;
    _ensureStructure();
    _fetch();
    _bindLive();
  };

  function _ensureStructure() {
    const panel = document.getElementById('traced-panel');
    if (!panel) return;
    if (panel.dataset.built === '1') return;

    panel.innerHTML = `
      <div id="traced-toolbar">
        <select id="traced-kind">
          <option value="">All kinds</option>
          ${EVENT_KINDS.map(k => `<option value="${k}">${k}</option>`).join('')}
        </select>
        <select id="traced-sev">
          <option value="debug">≥ debug</option>
          <option value="info" selected>≥ info</option>
          <option value="warn">≥ warn</option>
          <option value="error">≥ error</option>
        </select>
        <input type="text" id="traced-search" placeholder="filter text…" style="width:160px" />
        <button onclick="tracedRefresh()">Refresh</button>
        <button onclick="tracedClear()">Clear</button>
        <span id="traced-summary"></span>
      </div>
      <div id="traced-list"></div>
      <div id="traced-detail" class="traced-detail" style="display:none"></div>
    `;
    panel.dataset.built = '1';

    document.getElementById('traced-kind').onchange = (e) => {
      state.kinds = e.target.value ? new Set([e.target.value]) : new Set();
      _fetch();
    };
    document.getElementById('traced-sev').onchange = (e) => {
      state.minSeverity = e.target.value;
      _fetch();
    };
    document.getElementById('traced-search').oninput = (e) => {
      state.query = (e.target.value || '').toLowerCase();
      _render();
    };
  }

  function _fetch() {
    const q = new URLSearchParams();
    q.set('limit', String(state.limit));
    q.set('min_severity', state.minSeverity);
    if (state.kinds.size) q.set('kinds', Array.from(state.kinds).join(','));
    q.set('source', 'db');

    fetch('/api/spine/events?' + q.toString())
      .then(r => r.json())
      .then(data => {
        if (!data || !data.ok) return;
        state.events = data.items || [];
        _render();
      })
      .catch(() => {});
  }

  function _bindLive() {
    if (window.__trace && !window.__traced_live_bound) {
      window.__trace.on('event', (ev) => {
        // prepend if it matches current filter
        if (state.kinds.size && !state.kinds.has(ev.kind)) return;
        const order = { debug: 0, info: 1, warn: 2, error: 3, critical: 4 };
        if ((order[ev.severity] || 0) < (order[state.minSeverity] || 1)) return;
        state.events.unshift(ev);
        if (state.events.length > state.limit) state.events.length = state.limit;
        _render();
      });
      window.__traced_live_bound = true;
    }
  }

  function _render() {
    const list = document.getElementById('traced-list');
    const summary = document.getElementById('traced-summary');
    if (!list) return;

    const q = state.query;
    const shown = q
      ? state.events.filter(e =>
          (e.message || '').toLowerCase().includes(q) ||
          (e.agent || '').toLowerCase().includes(q) ||
          (e.source || '').toLowerCase().includes(q) ||
          (e.kind || '').toLowerCase().includes(q))
      : state.events;

    if (summary) summary.textContent = `${shown.length} / ${state.events.length} events`;

    list.innerHTML = shown.map(ev => {
      const ts = new Date((ev.ts || 0) * 1000);
      const hh = String(ts.getHours()).padStart(2, '0');
      const mm = String(ts.getMinutes()).padStart(2, '0');
      const ss = String(ts.getSeconds()).padStart(2, '0');
      const sel = (ev.id === state.selected) ? ' selected' : '';
      return `<div class="traced-row${sel}" data-id="${_esc(ev.id)}">
        <span class="traced-ts">${hh}:${mm}:${ss}</span>
        <span class="traced-kind">${_esc(ev.kind || '')}</span>
        <span class="traced-sev ${_esc(ev.severity)}">${_esc(ev.severity)}</span>
        <span class="traced-msg">${_esc(ev.agent ? ev.agent + ' · ' : '')}${_esc(ev.message || '')}</span>
      </div>`;
    }).join('');

    list.querySelectorAll('.traced-row').forEach(row => {
      row.onclick = () => _select(row.dataset.id);
    });

    if (state.selected) _select(state.selected);
  }

  function _select(id) {
    state.selected = id;
    document.querySelectorAll('.traced-row').forEach(r => {
      r.classList.toggle('selected', r.dataset.id === id);
    });
    const ev = state.events.find(e => e.id === id);
    const detail = document.getElementById('traced-detail');
    if (!detail) return;
    if (!ev) { detail.style.display = 'none'; return; }
    detail.style.display = 'block';
    detail.textContent = JSON.stringify(ev, null, 2);
  }

  function _esc(s) {
    if (window.SwarmChat && window.SwarmChat.esc) return window.SwarmChat.esc(s);
    return String(s || '').replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
  }

  window.tracedRefresh = function () { _fetch(); };
  window.tracedClear = function () {
    state.events = [];
    state.selected = null;
    _render();
  };
})();
