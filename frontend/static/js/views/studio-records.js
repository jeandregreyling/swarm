// Studio Records sub-tab — universal viewer for the 10 Platinum record kinds.
// Backend: GET /api/records/_kinds, /api/records/<kind>?q=, /api/records/<kind>/<id>
//          POST /api/records/<kind>/<id>/promote, /links

(function () {
  let _kinds = null;
  let _currentKind = 'project';
  let _currentRecord = null;

  function _esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function _q(sel, root) { return (root || document).querySelector(sel); }

  async function loadStudioRecordsPanel() {
    const panel = document.getElementById('studio-records-panel');
    if (!panel) return;
    if (!panel.dataset.bootstrapped) {
      panel.innerHTML = `
        <div style="padding:10px 14px;border-bottom:1px solid var(--border);display:flex;gap:10px;align-items:center;flex-wrap:wrap;background:var(--window-header);">
          <div style="font-size:13px;font-weight:700;">
            <svg viewBox="0 0 16 16" width="13" height="13" fill="none" style="vertical-align:-1px"><rect x="3" y="2" width="10" height="12" rx="1.5" stroke="currentColor" stroke-width="1.2"/><path d="M5.5 5.5h5M5.5 8h5M5.5 10.5h3" stroke="currentColor" stroke-width="1" stroke-linecap="round"/></svg>
            Records
          </div>
          <select id="studio-records-kind" style="padding:5px 8px;background:var(--card);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:11px;"></select>
          <input id="studio-records-search" type="text" placeholder="Search title or id…"
            style="flex:1;min-width:160px;max-width:340px;padding:5px 8px;background:var(--card);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:11px;outline:none;">
          <button id="studio-records-refresh" style="padding:5px 10px;border:1px solid var(--border);background:transparent;border-radius:4px;color:var(--text-dim);font-size:11px;cursor:pointer;">↻</button>
          <span id="studio-records-count" style="font-size:10px;color:var(--text-dim);"></span>
        </div>
        <div style="flex:1;display:flex;min-height:0;">
          <div id="studio-records-list" style="flex:0 0 320px;overflow-y:auto;border-right:1px solid var(--border);">
            <div style="padding:14px;color:var(--text-dim);font-size:11px;">Loading…</div>
          </div>
          <div style="flex:1;display:flex;flex-direction:column;min-width:0;">
            <div id="studio-records-toolbar" style="padding:8px 12px;border-bottom:1px solid var(--border);display:flex;gap:8px;align-items:center;flex-wrap:wrap;background:rgba(255,255,255,0.02);">
              <div id="studio-records-title" style="flex:1;font-size:12px;font-weight:700;color:var(--text-dim);">Select a record</div>
              <button id="studio-records-promote-btn" style="display:none;padding:4px 10px;border:1px solid var(--accent);border-radius:4px;background:transparent;color:var(--accent);font-size:11px;cursor:pointer;">Promote…</button>
              <button id="studio-records-link-btn" style="display:none;padding:4px 10px;border:1px solid var(--border);border-radius:4px;background:transparent;color:var(--text-dim);font-size:11px;cursor:pointer;">Add link…</button>
              <button id="studio-records-open-btn" style="display:none;padding:4px 10px;border:1px solid var(--border);border-radius:4px;background:transparent;color:var(--text-dim);font-size:11px;cursor:pointer;">Open file</button>
            </div>
            <div id="studio-records-detail" style="flex:1;overflow:auto;padding:14px;font-size:12px;line-height:1.5;color:var(--text);">
              <div style="color:var(--text-dim);">Pick a kind on the left and a record from the list to inspect its sidecar, links, and promotion chain.</div>
            </div>
          </div>
        </div>
      `;
      panel.style.display = 'flex';
      panel.style.flexDirection = 'column';
      panel.style.flex = '1';
      panel.dataset.bootstrapped = '1';

      _q('#studio-records-kind').addEventListener('change', (e) => {
        _currentKind = e.target.value;
        _loadList();
      });
      _q('#studio-records-refresh').addEventListener('click', _loadList);
      let _to = null;
      _q('#studio-records-search').addEventListener('input', () => {
        clearTimeout(_to);
        _to = setTimeout(_loadList, 200);
      });
      _q('#studio-records-promote-btn').addEventListener('click', _promoteCurrent);
      _q('#studio-records-link-btn').addEventListener('click', _linkCurrent);
      _q('#studio-records-open-btn').addEventListener('click', _openFile);
    }

    if (!_kinds) {
      try {
        const r = await fetch('/api/records/_kinds');
        const j = await r.json();
        _kinds = j.kinds || [];
      } catch (e) {
        _kinds = ['project','step','case','run','proposal','ticket','email','note','doc','thread'];
      }
      const sel = _q('#studio-records-kind');
      sel.innerHTML = _kinds.map(k => `<option value="${_esc(k)}">${_esc(k)}</option>`).join('');
      sel.value = _currentKind;
    }
    _loadList();
  }

  async function _loadList() {
    const list = _q('#studio-records-list');
    const counter = _q('#studio-records-count');
    if (!list) return;
    const kind = _currentKind;
    const q = (_q('#studio-records-search').value || '').trim();
    list.innerHTML = '<div style="padding:14px;color:var(--text-dim);font-size:11px;">Loading…</div>';
    try {
      const url = '/api/records/' + encodeURIComponent(kind) + (q ? ('?q=' + encodeURIComponent(q)) : '');
      const r = await fetch(url);
      const j = await r.json();
      if (!j.ok) {
        list.innerHTML = `<div style="padding:14px;color:#f77;font-size:11px;">${_esc(j.error || 'load failed')}</div>`;
        return;
      }
      counter.textContent = (j.count || 0) + ' shown';
      const items = j.items || [];
      if (!items.length) {
        list.innerHTML = '<div style="padding:14px;color:var(--text-dim);font-size:11px;">No records.</div>';
        return;
      }
      list.innerHTML = items.map(it => {
        const id = _esc(it.id);
        const title = _esc(it.title || it.id || '(untitled)');
        const status = it.status ? `<span style="font-size:9px;padding:1px 5px;border-radius:8px;background:var(--card);color:var(--text-dim);border:1px solid var(--border);">${_esc(it.status)}</span>` : '';
        const updated = it.updated_at ? `<span style="font-size:9px;color:var(--text-dim);">${_esc(String(it.updated_at).slice(0,16))}</span>` : '';
        return `<div class="srec-item" data-id="${id}"
          style="padding:8px 12px;border-bottom:1px solid var(--border);cursor:pointer;display:flex;flex-direction:column;gap:3px;">
          <div style="display:flex;justify-content:space-between;gap:6px;align-items:center;">
            <div style="font-size:11px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${title}</div>
            ${status}
          </div>
          <div style="display:flex;justify-content:space-between;gap:6px;align-items:center;">
            <div style="font-size:9px;color:var(--text-dim);font-family:monospace;">${id}</div>
            ${updated}
          </div>
        </div>`;
      }).join('');
      list.querySelectorAll('.srec-item').forEach(el => {
        el.addEventListener('click', () => {
          list.querySelectorAll('.srec-item').forEach(x => x.style.background = '');
          el.style.background = 'color-mix(in srgb, var(--accent) 15%, transparent)';
          _loadDetail(kind, el.getAttribute('data-id'));
        });
      });
    } catch (e) {
      list.innerHTML = `<div style="padding:14px;color:#f77;font-size:11px;">${_esc(e.message)}</div>`;
    }
  }

  async function _loadDetail(kind, rid) {
    const det = _q('#studio-records-detail');
    const tit = _q('#studio-records-title');
    const promBtn = _q('#studio-records-promote-btn');
    const linkBtn = _q('#studio-records-link-btn');
    const openBtn = _q('#studio-records-open-btn');
    det.innerHTML = '<div style="color:var(--text-dim);">Loading…</div>';
    try {
      const r = await fetch('/api/records/' + encodeURIComponent(kind) + '/' + encodeURIComponent(rid));
      const j = await r.json();
      if (!j.ok) {
        det.innerHTML = `<div style="color:#f77;">${_esc(j.error || 'not found')}</div>`;
        return;
      }
      _currentRecord = { kind: kind, id: rid, json_path: j.json_path, payload: j.record };
      const data = (j.record && j.record.data) || {};
      tit.textContent = (data.title || data.name || data.subject || data.doc_name || rid) + '  ·  ' + kind + '/' + rid;
      promBtn.style.display = '';
      linkBtn.style.display = '';
      openBtn.style.display = j.json_path ? '' : 'none';

      const md = j.markdown || '';
      const links = j.links || { outgoing: [], incoming: [] };
      const chain = j.chain || [];

      const renderLinks = (arr, dir) => {
        if (!arr || !arr.length) return `<div style="color:var(--text-dim);font-size:11px;">none</div>`;
        return arr.map(l => {
          const other = (dir === 'out')
            ? (l.dst_kind + '/' + l.dst_id)
            : (l.src_kind + '/' + l.src_id);
          return `<div style="font-size:11px;font-family:monospace;padding:2px 0;">
              <span style="color:var(--accent);">${_esc(l.rel)}</span>
              <span style="color:var(--text-dim);">${dir === 'out' ? '→' : '←'}</span>
              <a href="#" data-kind="${_esc(dir==='out' ? l.dst_kind : l.src_kind)}"
                 data-id="${_esc(dir==='out' ? l.dst_id : l.src_id)}"
                 class="srec-link">${_esc(other)}</a>
            </div>`;
        }).join('');
      };

      const renderChain = () => {
        if (!chain.length) return '';
        const items = chain.map(c => `<span style="font-family:monospace;font-size:11px;">${_esc(c.kind)}/${_esc(c.id)}</span>`).join(' <span style="color:var(--text-dim);">→</span> ');
        return `<div style="margin-bottom:14px;padding:8px 10px;background:rgba(255,255,255,0.03);border-left:3px solid var(--accent);border-radius:3px;">
          <div style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px;">Promotion chain</div>
          <div>${items}</div>
        </div>`;
      };

      det.innerHTML = `
        ${renderChain()}
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;">
          <div>
            <div style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;">Markdown sidecar</div>
            <pre style="background:var(--card);border:1px solid var(--border);padding:10px;border-radius:4px;font-size:11px;white-space:pre-wrap;word-break:break-word;max-height:520px;overflow:auto;margin:0;">${_esc(md || '(no .md sidecar)')}</pre>
          </div>
          <div>
            <div style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;">Links</div>
            <div style="margin-bottom:6px;font-size:10px;color:var(--text-dim);">Outgoing</div>
            ${renderLinks(links.outgoing, 'out')}
            <div style="margin:10px 0 6px;font-size:10px;color:var(--text-dim);">Incoming</div>
            ${renderLinks(links.incoming, 'in')}
            <details style="margin-top:14px;">
              <summary style="cursor:pointer;font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;">Raw JSON</summary>
              <pre style="background:var(--card);border:1px solid var(--border);padding:10px;border-radius:4px;font-size:10px;white-space:pre-wrap;word-break:break-all;max-height:380px;overflow:auto;margin:6px 0 0;">${_esc(JSON.stringify(j.record, null, 2))}</pre>
            </details>
            ${j.json_path ? `<div style="margin-top:10px;font-size:10px;color:var(--text-dim);font-family:monospace;">${_esc(j.json_path)}</div>` : ''}
          </div>
        </div>
      `;
      det.querySelectorAll('.srec-link').forEach(a => {
        a.addEventListener('click', (ev) => {
          ev.preventDefault();
          const k = a.getAttribute('data-kind');
          const i = a.getAttribute('data-id');
          if (k && i) {
            _currentKind = k;
            const sel = _q('#studio-records-kind');
            if (sel) sel.value = k;
            _loadList();
            _loadDetail(k, i);
          }
        });
      });
      // Seven sees — propose-only insight panel.
      try {
        if (window.SevenPanel) {
          window.SevenPanel.mount(det, { kind: kind, id: rid });
        }
      } catch (e) { /* noop */ }
    } catch (e) {
      det.innerHTML = `<div style="color:#f77;">${_esc(e.message)}</div>`;
    }
  }

  async function _promoteCurrent() {
    if (!_currentRecord) return;
    const dst = prompt('Promote ' + _currentRecord.kind + '/' + _currentRecord.id + ' to which kind?\n(thread → ticket → proposal → project)');
    if (!dst) return;
    try {
      const r = await fetch('/api/records/' + encodeURIComponent(_currentRecord.kind) + '/' + encodeURIComponent(_currentRecord.id) + '/promote', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dst_kind: dst.trim(), actor: 'studio-records' })
      });
      const j = await r.json();
      if (!j.ok) { alert('Promote failed: ' + (j.error || 'unknown')); return; }
      if (typeof showToast === 'function') showToast('Promoted to ' + j.kind + '/' + j.id, 'success');
      _currentKind = j.kind;
      const sel = _q('#studio-records-kind'); if (sel) sel.value = j.kind;
      _loadList();
      _loadDetail(j.kind, j.id);
    } catch (e) {
      alert('Promote error: ' + e.message);
    }
  }

  async function _linkCurrent() {
    if (!_currentRecord) return;
    const rel = prompt('Relation name (e.g. references, blocks, mentions):');
    if (!rel) return;
    const dstKind = prompt('Target kind:');
    if (!dstKind) return;
    const dstId = prompt('Target id:');
    if (!dstId) return;
    try {
      const r = await fetch('/api/records/' + encodeURIComponent(_currentRecord.kind) + '/' + encodeURIComponent(_currentRecord.id) + '/links', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rel: rel.trim(), dst_kind: dstKind.trim(), dst_id: dstId.trim(), actor: 'studio-records' })
      });
      const j = await r.json();
      if (!j.ok) { alert('Link failed: ' + (j.error || 'unknown')); return; }
      if (typeof showToast === 'function') showToast('Link added', 'success');
      _loadDetail(_currentRecord.kind, _currentRecord.id);
    } catch (e) {
      alert('Link error: ' + e.message);
    }
  }

  function _openFile() {
    if (!_currentRecord || !_currentRecord.json_path) return;
    // Best-effort: open in VS Code via vscode://file URI built from absolute path.
    const abs = '/home/seven/swarm/' + _currentRecord.json_path;
    window.open('vscode://file/' + abs, '_blank');
  }

  // Expose to studio.js
  window.loadStudioRecordsPanel = loadStudioRecordsPanel;
  // External callers (record-shortcuts.js, other tiles) can jump straight to a record.
  window.studioRecordsSelect = function (kind, id) {
    if (!kind || !id) return;
    loadStudioRecordsPanel();
    setTimeout(() => {
      _currentKind = kind;
      const sel = document.getElementById('studio-records-kind');
      if (sel) sel.value = kind;
      _loadList();
      _loadDetail(kind, id);
    }, 100);
  };
})();
