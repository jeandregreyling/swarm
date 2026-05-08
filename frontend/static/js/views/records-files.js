// Records Files tile — folder browser anchored at runtime/records/.
// Backend: GET /api/records/_browse?path=<rel>
//          GET /api/records/<kind>/<id>     (used when a *.json file is opened)

(function () {
  let _currentPath = '';

  function _esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function _humanSize(n) {
    if (n == null) return '';
    if (n < 1024) return n + ' B';
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
    return (n / 1024 / 1024).toFixed(1) + ' MB';
  }

  function loadRecordsFilesData(win) {
    const root = win && win.el ? win.el : document;
    const panel = root.querySelector('.records-files-root');
    if (!panel) return;
    if (!panel.dataset.bootstrapped) {
      panel.dataset.bootstrapped = '1';
      panel.querySelector('#rfb-up').addEventListener('click', () => {
        if (!_currentPath) return;
        const parts = _currentPath.split('/');
        parts.pop();
        _navigate(panel, parts.join('/'));
      });
      panel.querySelector('#rfb-refresh').addEventListener('click', () => _navigate(panel, _currentPath));
    }
    _navigate(panel, '');
  }

  async function _navigate(panel, p) {
    _currentPath = p || '';
    const list = panel.querySelector('#rfb-list');
    const crumb = panel.querySelector('#rfb-crumb');
    list.innerHTML = '<div style="padding:14px;color:var(--text-dim);font-size:11px;">Loading…</div>';
    crumb.innerHTML = _renderCrumb(_currentPath);
    crumb.querySelectorAll('[data-crumb]').forEach(a => {
      a.addEventListener('click', (ev) => {
        ev.preventDefault();
        _navigate(panel, a.getAttribute('data-crumb'));
      });
    });
    try {
      const r = await fetch('/api/records/_browse?path=' + encodeURIComponent(_currentPath));
      const j = await r.json();
      if (!j.ok) {
        list.innerHTML = `<div style="padding:14px;color:#f77;">${_esc(j.error || 'failed')}</div>`;
        return;
      }
      panel.querySelector('#rfb-count').textContent = j.count + ' entr' + (j.count === 1 ? 'y' : 'ies');
      if (!j.entries.length) {
        list.innerHTML = '<div style="padding:14px;color:var(--text-dim);">empty folder</div>';
        return;
      }
      list.innerHTML = j.entries.map(e => {
        const dt = e.mtime ? new Date(e.mtime * 1000).toISOString().slice(0, 16).replace('T', ' ') : '';
        const icon = e.is_dir
          ? '<svg viewBox="0 0 16 16" width="14" height="14" fill="none"><path d="M2.5 5h4l1-1.5h6V12H2.5z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>'
          : (e.name.endsWith('.json')
              ? '<svg viewBox="0 0 16 16" width="14" height="14" fill="none"><rect x="3" y="2" width="10" height="12" rx="1.5" stroke="currentColor" stroke-width="1.2"/><path d="M5.5 5.5h5M5.5 8h5M5.5 10.5h3" stroke="currentColor" stroke-width="1" stroke-linecap="round"/></svg>'
              : '<svg viewBox="0 0 16 16" width="14" height="14" fill="none"><rect x="3.5" y="2" width="9" height="12" rx="1.2" stroke="currentColor" stroke-width="1.2"/></svg>');
        return `<div class="rfb-item" data-rel="${_esc(e.rel)}" data-dir="${e.is_dir ? '1' : '0'}" data-name="${_esc(e.name)}"
          style="display:grid;grid-template-columns:24px 1fr 80px 130px;gap:8px;align-items:center;padding:6px 12px;border-bottom:1px solid var(--border);cursor:pointer;font-size:11px;">
          <span style="color:var(--text-dim);">${icon}</span>
          <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_esc(e.name)}</span>
          <span style="color:var(--text-dim);text-align:right;">${e.is_dir ? '' : _humanSize(e.size)}</span>
          <span style="color:var(--text-dim);font-family:monospace;">${_esc(dt)}</span>
        </div>`;
      }).join('');
      list.querySelectorAll('.rfb-item').forEach(el => {
        el.addEventListener('click', () => {
          const rel = el.getAttribute('data-rel');
          const isDir = el.getAttribute('data-dir') === '1';
          if (isDir) {
            _navigate(panel, rel);
          } else {
            _openFile(panel, rel, el.getAttribute('data-name'));
          }
        });
      });
    } catch (e) {
      list.innerHTML = `<div style="padding:14px;color:#f77;">${_esc(e.message)}</div>`;
    }
  }

  function _renderCrumb(p) {
    const segs = p ? p.split('/') : [];
    const parts = [`<a href="#" data-crumb="" style="color:var(--accent);text-decoration:none;">runtime/records</a>`];
    let acc = '';
    segs.forEach(s => {
      acc = acc ? (acc + '/' + s) : s;
      parts.push(`<span style="color:var(--text-dim);">/</span><a href="#" data-crumb="${_esc(acc)}" style="color:var(--accent);text-decoration:none;">${_esc(s)}</a>`);
    });
    return parts.join('');
  }

  async function _openFile(panel, rel, name) {
    const detail = panel.querySelector('#rfb-detail');
    detail.style.display = '';
    detail.innerHTML = '<div style="color:var(--text-dim);padding:14px;">Loading…</div>';
    // If it is a record JSON file, parse <kind>/<...>/<id>.json and use the records detail API.
    const m = rel.match(/^([^\/]+)\/.*\/([^\/]+)\.json$/);
    if (m) {
      const kind = m[1];
      const id = m[2];
      try {
        const r = await fetch('/api/records/' + encodeURIComponent(kind) + '/' + encodeURIComponent(id));
        const j = await r.json();
        if (j.ok) {
          const md = j.markdown || '';
          const links = j.links || { outgoing: [], incoming: [] };
          const chain = j.chain || [];
          detail.innerHTML = `
            <div style="padding:10px 14px;border-bottom:1px solid var(--border);background:rgba(255,255,255,0.02);display:flex;justify-content:space-between;align-items:center;">
              <div style="font-size:12px;font-weight:700;">${_esc(name)} <span style="color:var(--text-dim);font-weight:400;font-size:10px;">${_esc(kind)}/${_esc(id)}</span></div>
              <button id="rfb-close" style="padding:3px 10px;border:1px solid var(--border);background:transparent;border-radius:4px;color:var(--text-dim);font-size:11px;cursor:pointer;">Close</button>
            </div>
            <div style="padding:14px;overflow:auto;max-height:520px;">
              ${chain.length ? '<div style="margin-bottom:10px;font-size:11px;color:var(--text-dim);">chain: ' + chain.map(c => `${_esc(c.kind)}/${_esc(c.id)}`).join(' → ') + '</div>' : ''}
              <pre style="background:var(--card);border:1px solid var(--border);padding:10px;border-radius:4px;font-size:11px;white-space:pre-wrap;word-break:break-word;margin:0 0 10px;">${_esc(md || '(no .md sidecar)')}</pre>
              <details><summary style="cursor:pointer;font-size:10px;color:var(--text-dim);">Raw JSON</summary>
                <pre style="background:var(--card);border:1px solid var(--border);padding:10px;border-radius:4px;font-size:10px;white-space:pre-wrap;word-break:break-all;margin:6px 0 0;">${_esc(JSON.stringify(j.record, null, 2))}</pre>
              </details>
              <div style="margin-top:10px;font-size:10px;color:var(--text-dim);">links: out=${(links.outgoing || []).length} in=${(links.incoming || []).length}</div>
            </div>`;
          panel.querySelector('#rfb-close').addEventListener('click', () => { detail.style.display = 'none'; detail.innerHTML = ''; });
          return;
        }
      } catch (e) { /* fall through to raw */ }
    }
    // Generic file: show absolute path + a link to open in VS Code.
    const abs = '/home/seven/swarm/runtime/records/' + rel;
    detail.innerHTML = `
      <div style="padding:10px 14px;border-bottom:1px solid var(--border);background:rgba(255,255,255,0.02);display:flex;justify-content:space-between;align-items:center;">
        <div style="font-size:12px;font-weight:700;">${_esc(name)}</div>
        <button id="rfb-close" style="padding:3px 10px;border:1px solid var(--border);background:transparent;border-radius:4px;color:var(--text-dim);font-size:11px;cursor:pointer;">Close</button>
      </div>
      <div style="padding:14px;font-size:11px;">
        <div style="font-family:monospace;color:var(--text-dim);margin-bottom:8px;">${_esc(rel)}</div>
        <a href="vscode://file${_esc(abs)}" style="color:var(--accent);">Open in VS Code</a>
      </div>`;
    panel.querySelector('#rfb-close').addEventListener('click', () => { detail.style.display = 'none'; detail.innerHTML = ''; });
  }

  window.loadRecordsFilesData = loadRecordsFilesData;
  // External callers can jump to a kind subfolder.
  window.recordsFilesNavigate = function (relPath) {
    // Find the most recently mounted records-files-root and navigate it.
    const panel = document.querySelector('.records-files-root');
    if (panel) _navigate(panel, relPath || '');
  };
})();
