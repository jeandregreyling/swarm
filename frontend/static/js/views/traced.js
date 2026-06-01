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
    'sync_story',
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
    const kinds = Array.from(state.kinds).filter(k => k !== 'sync_story');
    if (kinds.length) q.set('kinds', kinds.join(','));
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
        if (state.kinds.size && !_matchesKindFilter(ev)) return;
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
    const shown = state.events.filter(e => {
      if (!_matchesKindFilter(e)) return false;
      if (!q) return true;
      const hay = [
        e.message || '',
        e.agent || '',
        e.source || '',
        e.kind || '',
        _syncStorySummaryText(e),
      ].join(' ').toLowerCase();
      return hay.includes(q);
    });

    if (summary) summary.textContent = `${shown.length} / ${state.events.length} events`;

    list.innerHTML = shown.map(ev => {
      const ts = new Date((ev.ts || 0) * 1000);
      const hh = String(ts.getHours()).padStart(2, '0');
      const mm = String(ts.getMinutes()).padStart(2, '0');
      const ss = String(ts.getSeconds()).padStart(2, '0');
      const sel = (ev.id === state.selected) ? ' selected' : '';
      if (_isSyncStory(ev)) {
        const story = ev.payload || {};
        const origin = story.origin || {};
        const intent = story.intent || {};
        const transition = story.transition || {};
        const consequence = story.consequence || {};
        const risk = String(story.risk || 'review-recommended').toLowerCase();
        const branch = intent.branch || 'unknown';
        const fromSha = intent.from_sha || 'none';
        const toSha = intent.to_sha || fromSha;
        const route = `${origin.source_node || ev.agent || 'node'} → ${origin.target_node || origin.transport || 'upstream'}`;
        const cats = Array.isArray(transition.categories) && transition.categories.length
          ? transition.categories.join(', ')
          : 'uncategorized';
        return `<div class="traced-row traced-sync-row${sel}" data-id="${_esc(ev.id)}">
          <span class="traced-ts">${hh}:${mm}:${ss}</span>
          <span class="traced-kind traced-kind-sync">git.sync</span>
          <span class="traced-sev ${_esc(ev.severity)}">${_esc(risk)}</span>
          <span class="traced-msg">
            <span class="traced-sync-head">${_esc(route)} · ${_esc(branch)} · ${_esc(fromSha)} → ${_esc(toSha)}</span>
            <span class="traced-sync-sub">${_esc(cats)} · ${_esc(consequence.result || 'unknown')}</span>
          </span>
        </div>`;
      }
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
    if (_isSyncStory(ev)) {
      detail.innerHTML = _renderSyncStoryDetail(ev);
      return;
    }
    detail.textContent = JSON.stringify(ev, null, 2);
  }

  function _isSyncStory(ev) {
    return !!(ev && ev.payload && ev.payload.kind === 'sync_story');
  }

  function _matchesKindFilter(ev) {
    if (!state.kinds.size) return true;
    if (state.kinds.has('sync_story') && _isSyncStory(ev)) return true;
    return state.kinds.has(ev.kind);
  }

  function _syncStorySummaryText(ev) {
    if (!_isSyncStory(ev)) return '';
    const story = ev.payload || {};
    const origin = story.origin || {};
    const intent = story.intent || {};
    const transition = story.transition || {};
    const consequence = story.consequence || {};
    const categories = Array.isArray(transition.categories) ? transition.categories.join(' ') : '';
    return [
      story.summary || '',
      origin.source_node || '',
      origin.target_node || '',
      origin.transport || '',
      intent.branch || '',
      intent.from_sha || '',
      intent.to_sha || '',
      consequence.result || '',
      consequence.reason || '',
      story.risk || '',
      categories,
    ].join(' ');
  }

  function _renderSyncStoryDetail(ev) {
    const story = ev.payload || {};
    const origin = story.origin || {};
    const intent = story.intent || {};
    const transition = story.transition || {};
    const consequence = story.consequence || {};
    const intervention = story.intervention || {};
    const stateNow = consequence.current_state || {};
    const categories = Array.isArray(transition.categories) ? transition.categories : [];
    const paths = Array.isArray(transition.paths) ? transition.paths : [];
    const actions = Array.isArray(intervention.recommended) ? intervention.recommended : [];
    return `
      <div class="traced-sync-detail">
        <div class="traced-sync-card-head">
          <span class="traced-sync-card-title">${_esc(story.summary || 'Sync Story')}</span>
          <span class="traced-sync-risk traced-sync-risk-${_esc(String(story.risk || 'review-recommended').toLowerCase())}">${_esc(story.risk || 'review-recommended')}</span>
        </div>
        <div class="traced-sync-grid">
          <div class="traced-sync-block">
            <div class="traced-sync-label">Origin</div>
            <div>${_esc(origin.source_node || 'unknown')} → ${_esc(origin.target_node || origin.transport || 'upstream')}</div>
            <div>${_esc(origin.transport || 'unknown')} · actor=${_esc(origin.actor || '')}</div>
            <div>trigger=${_esc(origin.trigger || '')}</div>
          </div>
          <div class="traced-sync-block">
            <div class="traced-sync-label">Intent</div>
            <div>${_esc(intent.branch || 'unknown')} · ${_esc(intent.from_sha || 'none')} → ${_esc(intent.to_sha || intent.from_sha || 'none')}</div>
            <div>changes=${_esc(String(intent.change_count || 0))} · threshold=${_esc(String(intent.threshold || 'n/a'))}</div>
            <div>${_esc(intent.reason || '')}</div>
          </div>
          <div class="traced-sync-block">
            <div class="traced-sync-label">Consequence</div>
            <div>result=${_esc(consequence.result || 'unknown')} · pushed=${_esc(String(!!consequence.pushed))}</div>
            <div>restart=${_esc(String(!!stateNow.restart_recommended))} · clean=${_esc(String(!!stateNow.clean_after_sync))}</div>
            <div>${_esc(consequence.next || '')}</div>
          </div>
          <div class="traced-sync-block">
            <div class="traced-sync-label">Impact Summary</div>
            <div>Touched: ${_esc(categories.join(', ') || 'uncategorized')}</div>
            <div>${paths.length} path${paths.length === 1 ? '' : 's'}${transition.paths_truncated ? ' (truncated)' : ''}</div>
          </div>
        </div>
        ${paths.length ? `<div class="traced-sync-section"><div class="traced-sync-label">Paths</div><div class="traced-sync-paths">${paths.map(p => `<div>${_esc(p)}</div>`).join('')}</div></div>` : ''}
        ${actions.length ? `<div class="traced-sync-section"><div class="traced-sync-label">Intervention</div><div class="traced-sync-actions">${actions.map(a => `<span class="traced-sync-action">${_esc(a)}</span>`).join('')}</div></div>` : ''}
        <details class="traced-sync-raw"><summary>Raw Event</summary><pre>${_esc(JSON.stringify(ev, null, 2))}</pre></details>
      </div>
    `;
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
