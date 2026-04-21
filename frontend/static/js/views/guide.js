'use strict';

/* ──────────────────────────────────────────────────────────────────────────
   guide.js — Interactive User Guide
   Fetches sections from /api/guide, renders markdown with marked.js.
   Exposes: loadGuideData(win), guideSetSection(id), guideSearch(q)
────────────────────────────────────────────────────────────────────────── */

let _guideSections = [];
let _guideCurrentId = null;
let _guideWin = null;
let _guideSectionCache = {};   // id → content string

(function _guideInjectStyle() {
  if (document.getElementById('guide-css')) return;
  const s = document.createElement('style');
  s.id = 'guide-css';
  s.textContent = `
    .guide-nav-item { display:flex;align-items:center;gap:8px;padding:8px 14px;cursor:pointer;font-size:12px;color:var(--text-dim);border-radius:4px;margin:1px 8px;transition:background .12s,color .12s;white-space:nowrap;overflow:hidden;text-overflow:ellipsis; }
    .guide-nav-item:hover { background:var(--hover);color:var(--text); }
    .guide-nav-item.guide-nav-active { background:color-mix(in srgb,var(--accent) 15%,transparent);color:var(--accent);font-weight:700;border-left:2px solid var(--accent); }
    .guide-nav-icon { font-size:14px;flex-shrink:0; }
    #guide-body h1 { font-size:18px;font-weight:800;margin:0 0 16px;color:var(--text);border-bottom:1px solid var(--border);padding-bottom:10px; }
    #guide-body h2 { font-size:14px;font-weight:700;margin:22px 0 8px;color:var(--text); }
    #guide-body h3 { font-size:13px;font-weight:700;margin:16px 0 6px;color:var(--text-dim); }
    #guide-body p  { margin:0 0 10px;color:var(--text); }
    #guide-body ul,#guide-body ol { margin:0 0 10px;padding-left:20px;color:var(--text); }
    #guide-body li { margin-bottom:4px; }
    #guide-body table { width:100%;border-collapse:collapse;margin:0 0 14px;font-size:12px; }
    #guide-body th { background:var(--window-header);padding:6px 10px;text-align:left;border:1px solid var(--border);font-weight:700;color:var(--text); }
    #guide-body td { padding:5px 10px;border:1px solid var(--border);color:var(--text); }
    #guide-body code { background:var(--window-header);border:1px solid var(--border);border-radius:4px;padding:1px 5px;font-size:11px;font-family:monospace; }
    #guide-body pre { background:var(--window-header);border:1px solid var(--border);border-radius:6px;padding:12px;overflow-x:auto;margin:0 0 12px; }
    #guide-body pre code { background:none;border:none;padding:0; }
    #guide-body kbd { background:var(--window-header);border:1px solid var(--border);border-radius:3px;padding:1px 6px;font-size:11px;font-family:inherit; }
    #guide-body blockquote { border-left:3px solid var(--accent);margin:0 0 12px;padding:8px 14px;background:color-mix(in srgb,var(--accent) 8%,transparent);border-radius:0 6px 6px 0; }
    .guide-search-hit { background:color-mix(in srgb,var(--accent) 25%,transparent);border-radius:2px; }
  `;
  document.head.appendChild(s);
})();

function loadGuideData(win) {
  _guideWin = win;
  _guideSectionCache = {};

  const nav  = win.el.querySelector('#guide-nav');
  const body = win.el.querySelector('#guide-body');
  const searchInput = win.el.querySelector('#guide-search');
  if (!nav || !body) return;

  body.innerHTML = '<div style="color:var(--text-dim);padding:20px;font-size:13px;">Loading guide…</div>';

  fetch('/api/guide')
    .then(r => r.json())
    .then(data => {
      _guideSections = data.sections || [];
      _guideRenderNav(nav);
      if (_guideSections.length) guideSetSection(_guideSections[0].id);
    })
    .catch(() => {
      body.innerHTML = '<div style="color:var(--text-dim);padding:20px;">Failed to load guide.</div>';
    });

  if (searchInput) {
    searchInput.addEventListener('input', () => guideSearch(searchInput.value));
  }
}

function _guideRenderNav(nav) {
  nav.innerHTML = _guideSections.map(s => `
    <div class="guide-nav-item${s.id === _guideCurrentId ? ' guide-nav-active' : ''}"
         data-guide-id="${s.id}" onclick="guideSetSection('${s.id}')">
      <span class="guide-nav-icon">${s.icon || '📄'}</span>
      <span>${s.title}</span>
    </div>
  `).join('');
}

function guideSetSection(id) {
  _guideCurrentId = id;

  // Update nav active state
  const win = _guideWin;
  if (win) {
    win.el.querySelectorAll('.guide-nav-item').forEach(el => {
      el.classList.toggle('guide-nav-active', el.dataset.guideId === id);
    });
    // Clear search
    const si = win.el.querySelector('#guide-search');
    if (si) si.value = '';
  }

  const body = (win ? win.el.querySelector('#guide-body') : null) || document.getElementById('guide-body');
  if (!body) return;

  // Use cache if available
  if (_guideSectionCache[id]) {
    _guideRenderContent(body, _guideSectionCache[id]);
    return;
  }

  body.innerHTML = '<div style="color:var(--text-dim);padding:20px;font-size:13px;">Loading…</div>';

  fetch(`/api/guide/${id}`)
    .then(r => r.json())
    .then(data => {
      _guideSectionCache[id] = data.content || '';
      _guideRenderContent(body, data.content || '');
    })
    .catch(() => {
      body.innerHTML = '<div style="color:var(--text-dim);padding:20px;">Failed to load section.</div>';
    });
}

function _guideRenderContent(body, markdown) {
  if (typeof window !== 'undefined' && typeof window.safeMarkdown === 'function') {
    body.innerHTML = window.safeMarkdown(markdown);
  } else if (typeof marked !== 'undefined' && marked.parse) {
    body.innerHTML = marked.parse(markdown);
  } else {
    // Fallback: basic markdown-to-HTML
    body.innerHTML = markdown
      .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
      .replace(/^### (.+)$/gm,'<h3>$1</h3>')
      .replace(/^## (.+)$/gm,'<h2>$1</h2>')
      .replace(/^# (.+)$/gm,'<h1>$1</h1>')
      .replace(/`([^`]+)`/g,'<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>')
      .replace(/\n\n/g,'</p><p>')
      .replace(/^/,'<p>').replace(/$/,'</p>');
  }
  body.scrollTop = 0;
}

function guideSearch(q) {
  const win  = _guideWin;
  const body = (win ? win.el.querySelector('#guide-body') : null) || document.getElementById('guide-body');
  const nav  = (win ? win.el.querySelector('#guide-nav') : null) || document.getElementById('guide-nav');
  if (!body) return;

  if (!q || q.length < 2) {
    // Clear highlights, restore nav
    nav && nav.querySelectorAll('.guide-nav-item').forEach(el => el.style.display = '');
    if (_guideCurrentId && _guideSectionCache[_guideCurrentId]) {
      _guideRenderContent(body, _guideSectionCache[_guideCurrentId]);
    }
    return;
  }

  const ql = q.toLowerCase();

  // Filter nav to matching sections
  if (nav) {
    nav.querySelectorAll('.guide-nav-item').forEach(el => {
      const id    = el.dataset.guideId;
      const sec   = _guideSections.find(s => s.id === id);
      const title = (sec?.title || '').toLowerCase();
      const cache = (_guideSectionCache[id] || '').toLowerCase();
      el.style.display = (title.includes(ql) || cache.includes(ql)) ? '' : 'none';
    });
  }

  // Search within current section content
  if (_guideCurrentId && _guideSectionCache[_guideCurrentId]) {
    const rendered = _guideSectionCache[_guideCurrentId];
    if ((typeof window !== 'undefined' && typeof window.safeMarkdown === 'function') || (typeof marked !== 'undefined' && marked.parse)) {
      const html = (typeof window !== 'undefined' && typeof window.safeMarkdown === 'function') ? window.safeMarkdown(rendered) : marked.parse(rendered);
      // Highlight matches in text nodes via a simple regex on innerHTML
      body.innerHTML = html.replace(
        new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')})`, 'gi'),
        '<mark class="guide-search-hit">$1</mark>'
      );
    }
  }
}
