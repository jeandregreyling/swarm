// grokpot.js — Studio Grok Pot tile (review-only)
//
// Lists curated Grok Pot intake docs + the matching origin/grok-pot-* branches.
// Reading a doc is read-only here. To pull a Grok branch into a working tree,
// use the Git tile (Browse/Compare/Checkout).

(function () {
  function _esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function _fmtBytes(n) {
    n = Number(n || 0);
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / 1024 / 1024).toFixed(2)} MB`;
  }

  async function grokpotRefresh() {
    const sidebar = document.getElementById('grokpot-sidebar');
    if (!sidebar) return;
    sidebar.innerHTML = '<div style="color:var(--text-dim);font-size:11px;">Loading…</div>';
    try {
      const r = await fetch('/api/grokpot/summary');
      const d = await r.json();
      const parts = [];
      (d.sections || []).forEach(sec => {
        if (!sec.exists) {
          parts.push(`<div style="margin-bottom:10px;color:var(--text-dim);font-size:11px;">${_esc(sec.label)} · not on disk</div>`);
          return;
        }
        parts.push(`<div style="margin-bottom:10px;">
          <div style="font-size:11px;font-weight:700;color:var(--text);margin-bottom:4px;">${_esc(sec.label)}</div>
          <div style="font-size:10px;color:var(--text-dim);margin-bottom:6px;font-family:monospace;">${_esc(sec.path || '')}</div>
          ${(sec.docs || []).map(doc => `
            <div onclick="grokpotOpenDoc('${_esc(doc.path).replace(/'/g, "\\'")}')"
              style="cursor:pointer;padding:4px 6px;border-radius:4px;display:flex;justify-content:space-between;gap:8px;font-size:11px;"
              onmouseover="this.style.background='rgba(255,255,255,0.04)'"
              onmouseout="this.style.background='transparent'">
              <span style="color:var(--text);font-family:monospace;">${_esc(doc.name)}</span>
              <span style="color:var(--text-dim);">${_fmtBytes(doc.bytes)}</span>
            </div>`).join('')}
        </div>`);
      });

      const branches = d.branches || [];
      const branchHtml = branches.length === 0
        ? '<div style="color:var(--text-dim);font-size:11px;padding:4px;">No origin/grok-pot-* branches found.</div>'
        : branches.map(b => `<div style="padding:4px 6px;border-bottom:1px solid var(--border);font-size:11px;">
            <div style="font-family:monospace;color:var(--text);">${_esc(b.short)}</div>
            <div style="color:var(--text-dim);font-size:10px;">${_esc(b.committed_at)} · ${_esc(b.subject)}</div>
            <div style="margin-top:3px;display:flex;gap:4px;">
              <button onclick="grokpotJumpToGit('${_esc(b.ref).replace(/'/g, "\\'")}', 'compare')"
                style="background:transparent;border:1px solid var(--border);color:var(--text-dim);font-size:10px;padding:2px 6px;border-radius:3px;cursor:pointer;">Compare</button>
              <button onclick="grokpotJumpToGit('${_esc(b.ref).replace(/'/g, "\\'")}', 'browse')"
                style="background:transparent;border:1px solid var(--border);color:var(--text-dim);font-size:10px;padding:2px 6px;border-radius:3px;cursor:pointer;">Browse</button>
            </div>
          </div>`).join('');

      parts.push(`<div style="margin-top:14px;padding-top:10px;border-top:1px solid var(--border);">
        <div style="font-size:11px;font-weight:700;color:var(--text);margin-bottom:6px;">Remote branches</div>
        ${branchHtml}
      </div>`);
      sidebar.innerHTML = parts.join('');
    } catch (e) {
      sidebar.innerHTML = `<div style="color:#ef4444;font-size:11px;">Failed to load: ${_esc(e.message || e)}</div>`;
    }
  }

  async function grokpotOpenDoc(path) {
    const titleEl = document.getElementById('grokpot-detail-title');
    const bodyEl = document.getElementById('grokpot-detail-body');
    if (titleEl) titleEl.textContent = path;
    if (bodyEl) bodyEl.textContent = 'Loading…';
    try {
      const r = await fetch(`/api/grokpot/doc?path=${encodeURIComponent(path)}`);
      const d = await r.json();
      if (!d.ok) throw new Error(d.error || 'load failed');
      if (bodyEl) bodyEl.textContent = (d.truncated ? '(truncated)\n' : '') + (d.content || '');
    } catch (e) {
      if (bodyEl) bodyEl.textContent = `Failed: ${e.message || e}`;
    }
  }

  function grokpotJumpToGit(ref, action) {
    if (typeof openWindow === 'function') openWindow('git', 'Git', 'view-git');
    setTimeout(() => {
      const sel = document.querySelector('#view-git #git-branch-select, .wm-window #git-branch-select');
      if (sel) {
        const opt = Array.from(sel.options).find(o => o.value === ref || o.value === ref.replace(/^origin\//, ''));
        if (opt) sel.value = opt.value;
      }
      if (action === 'compare' && typeof window.gitCompareSelectedBranch === 'function') window.gitCompareSelectedBranch();
      if (action === 'browse'  && typeof window.gitBrowseSelectedBranch  === 'function') window.gitBrowseSelectedBranch();
    }, 500);
  }

  function initializeGrokPotPanel() { grokpotRefresh(); }

  window.grokpotRefresh = grokpotRefresh;
  window.grokpotOpenDoc = grokpotOpenDoc;
  window.grokpotJumpToGit = grokpotJumpToGit;
  window.initializeGrokPotPanel = initializeGrokPotPanel;
})();
