/* Owner 14 Nov: "the approvals should be in the header banner as well as have a popup in the main chat linked to it, otherwise
 * I keep having to check". The header's needs-you counter glows while something waits; a small popup in main chat names the
 * newest item. Show jumps to it in the Needs-you bar; Later hides it until something new arrives. Data: window.hbNeedsYouItems()
 * (hb-needs-you.js). */
(function () {
  'use strict';
  if (typeof document === 'undefined') return;
  const WORD = { confirm: 'Confirm', halted: 'HB stopped', review: 'Review', accept: 'Approve', plan: 'Plan', workflow: 'Start', step: 'Studio step' };
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const S = { later: new Set(), sig: '' };
  const CSS = '#dial-needs-you:not([data-count="0"]){background:var(--accent,#e0a030);color:#000;border-radius:10px;box-shadow:0 0 8px var(--accent,#e0a030);animation:hb-needs-pulse 2s infinite}' +
    '@keyframes hb-needs-pulse{50%{box-shadow:0 0 2px var(--accent,#e0a030)}}' +
    '#hb-approval-popup{position:fixed;right:18px;bottom:90px;z-index:9000;max-width:340px;padding:10px 14px;border-radius:12px;' +
    'border:1px solid var(--accent,#e0a030);background:var(--card,#141c2b);color:var(--text,#e8eef8);font-size:13px;box-shadow:0 10px 28px rgba(0,0,0,.4)}' +
    '#hb-approval-popup b{color:var(--accent,#e0a030)}#hb-approval-popup .hb-pop-more{opacity:.7;font-size:12px}' +
    '#hb-approval-popup button{margin:8px 6px 0 0;padding:3px 10px;border-radius:7px;border:1px solid var(--accent,#e0a030);background:transparent;color:inherit;cursor:pointer}' +
    '#hb-approval-popup button.hb-pop-show{background:var(--accent,#e0a030);color:#000;font-weight:700}';

  const ico = n => (window.HBIcons && window.HBIcons.svg) ? window.HBIcons.svg(n) : `<span data-hb-icon="${n}"></span>`;
  function style() {
    if (document.getElementById('hb-approval-css')) return;
    const st = document.createElement('style'); st.id = 'hb-approval-css'; st.textContent = CSS; document.head.appendChild(st);
  }

  function popup() {
    let el = document.getElementById('hb-approval-popup');
    if (!el) {
      el = document.createElement('div'); el.id = 'hb-approval-popup'; el.setAttribute('role', 'status'); el.setAttribute('aria-live', 'polite');
      document.body.appendChild(el);
    }
    return el;
  }

  function check() {
    const items = (typeof window.hbNeedsYouItems === 'function' ? window.hbNeedsYouItems() : []).filter(i => !i.info);
    const fresh = items.filter(i => !S.later.has(i.key));
    const sig = fresh.map(i => i.key).join('|');
    if (sig === S.sig) return;
    S.sig = sig;
    style();
    const old = document.getElementById('hb-approval-popup');
    if (!fresh.length) { if (old) old.remove(); return; }
    const top = fresh[fresh.length - 1];
    const el = popup();
    el.innerHTML = `${ico('flag')} <b>Needs you:</b> ${esc(WORD[top.kind] || 'Review')} - ${esc(top.label)}` +
      (fresh.length > 1 ? `<div class="hb-pop-more">and ${fresh.length - 1} more waiting</div>` : '') +
      `<div><button type="button" class="hb-pop-show">Show</button><button type="button" class="hb-pop-later">Later</button></div>`;
    el.querySelector('.hb-pop-show').onclick = () => { if (typeof window.hbNeedsFocusBar === 'function') window.hbNeedsFocusBar(); };
    el.querySelector('.hb-pop-later').onclick = () => { fresh.forEach(i => S.later.add(i.key)); S.sig = null; check(); };
  }
  window.hbApprovalPopupCheck = check;
  setInterval(check, 3000);
  setTimeout(check, 1500);
})();
