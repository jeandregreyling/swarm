/* Live activity in main chat (owner 14 Nov). One bubble per task: the agents working on it as a linked chain (APEX, then Fred, joined by a dotted line),
 * each with plain statuses written by HB. When a task's next turn starts, its older bubble hands over (is removed) instead of
 * freezing as "stalled". Work with no bubble on screen shows in a small corner panel. Data: /api/peer/v1/hb/activity */
(function () {
  'use strict';
  if (typeof document === 'undefined') return;
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const COLOR = { APEX: 'var(--hb-role-apex,#b48ce8)', Fred: 'var(--hb-role-fred,#3fb68b)', HB: 'var(--accent,#6aa9ff)', Codex: 'var(--hb-role-codex,#e06060)', Gemini: 'var(--hb-role-gemini,#e0a030)' };
  const ico = n => (window.HBIcons && window.HBIcons.svg) ? window.HBIcons.svg(n) : `<span data-hb-icon="${n}"></span>`;
  const CSS = '.hb-chain{margin-top:6px;font:12px/1.4 system-ui,sans-serif}.hb-chain-task{font-weight:600;opacity:.9;margin-bottom:4px}' +
    '.hb-link{position:relative;padding-left:18px;margin:2px 0 6px}.hb-link:before{content:"";position:absolute;left:5px;top:6px;width:9px;height:9px;border-radius:50%;background:var(--c)}' +
    '.hb-link:not(:last-child):after{content:"";position:absolute;left:9px;top:16px;bottom:-8px;border-left:2px dotted var(--c)}' +
    '.hb-link b{color:var(--c)}.hb-link small{opacity:.65}.hb-step{opacity:.8;font-size:11px}.hb-step:last-child{opacity:1}';
  let open = true;
  function style() { if (!document.getElementById('hb-activity-css')) { const s = document.createElement('style'); s.id = 'hb-activity-css'; s.textContent = CSS; document.head.appendChild(s); } }
  const ridOf = node => { const m = /-request-(\d+)$/.exec(node.dataset.pendingJobId || ''); return m ? m[1] : null; };

  function chainHtml(c) {
    return `<div class="hb-chain"><div class="hb-chain-task">${esc(c.task)}</div>` + c.members.map(m =>
      `<div class="hb-link" style="--c:${COLOR[m.role] || 'var(--text-dim,#9aa7b8)'}"><b>${esc(m.role)}</b> <small>${esc(m.model)}${m.where ? ' · ' + esc(m.where) : ''}</small>` +
      m.steps.map(s => `<div class="hb-step">${esc(s.at)} · ${esc(s.what)}</div>`).join('') + `</div>`).join('') + `</div>`;
  }

  function panel() {
    let el = document.getElementById('hb-activity');
    if (!el) {
      el = document.createElement('div'); el.id = 'hb-activity';
      el.style.cssText = 'position:fixed;left:14px;bottom:14px;z-index:8999;max-width:460px;max-height:42vh;overflow:auto;padding:8px 10px;border-radius:10px;' +
        'border:1px solid var(--border,#2c3a50);background:var(--card,rgba(15,21,32,.95));color:var(--text,#cfe0f5);box-shadow:0 8px 24px rgba(0,0,0,.4)';
      el.addEventListener('click', e => { if (e.target.dataset.toggle) { open = !open; refresh(); } });
      document.body.appendChild(el);
    }
    return el;
  }

  async function refresh() {
    if (document.hidden) return;
    let d;
    try {
      const r = await fetch('/api/peer/v1/hb/activity', { credentials: 'same-origin' });
      if (!r.ok) return;
      d = await r.json();
    } catch (_) { return; }
    style();
    const chains = d.chains || [], taskOf = d.requests || {};
    const liveByTask = new Map(chains.filter(c => c.task_id).map(c => [c.task_id, c]));
    const bubbles = [...document.querySelectorAll('[data-pending-job-id]')];
    // Hand-over: a bubble whose task now has newer work, or a frozen bubble of a task that is running again, goes away.
    const newest = new Map();
    bubbles.forEach(b => { const rid = ridOf(b), t = rid && taskOf[rid]; if (t && (!newest.has(t) || +rid > +ridOf(newest.get(t)))) newest.set(t, b); });
    const running = new Set(chains.flatMap(c => c.members.map(m => String(m.request_id))));
    bubbles.forEach(b => {
      const rid = ridOf(b), t = rid && taskOf[rid];
      if (!t || newest.get(t) === b) { b.style.display = ''; return; }
      if (running.has(rid)) b.style.display = 'none';     // still working: folded into its task's bubble (no flicker)
      else b.remove();                                    // finished or frozen: handed over to the newer bubble
    });
    const loose = [];
    chains.forEach(c => {
      const host = c.task_id && newest.get(c.task_id) && newest.get(c.task_id).isConnected ? newest.get(c.task_id)
        : c.members.map(m => document.querySelector(`[data-pending-job-id$="-request-${m.request_id}"]`)).find(Boolean);
      if (!host) { loose.push(c); return; }
      let box = host.querySelector(':scope > .hb-act');
      if (!box) { box = document.createElement('div'); box.className = 'hb-act'; host.appendChild(box); }
      box.innerHTML = chainHtml(c);
    });
    const el = panel();
    if (!loose.length) { el.style.display = 'none'; return; }
    el.style.display = '';
    el.innerHTML = `<div data-toggle="1" style="cursor:pointer;color:var(--accent,#6aa9ff);font-weight:700;font-size:12px">${ico('gear')} Live activity ${ico(open ? 'less' : 'more')}</div>` +
      (open ? loose.map(chainHtml).join('') : '');
  }
  window.hbActivityRefresh = refresh;
  setInterval(refresh, 3000); setTimeout(refresh, 1000);
})();
