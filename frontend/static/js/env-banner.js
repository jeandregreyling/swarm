// env-banner.js — compact DEV/UAT glow badge + env switcher pill (all envs)
(function () {
  const stage = (window.ENV_STAGE || '').toUpperCase();
  if (!stage) return;   // no ENV_STAGE at all — do nothing

  // ── 1. Compact glow badge — DEV and UAT only ─────────────────────────────
  if (stage !== 'PROD') {
    const isDev = stage === 'DEV';
    const cfg = isDev
      ? {
          label: 'MONDAYS · DEVELOPMENT',
          gradient: 'linear-gradient(135deg,#0d4fff,#4facfe 62%,#9edbff 100%)',
          glow: 'rgba(79,172,254,0.65)',
          border: 'rgba(173,224,255,0.68)',
        }
      : {
          label: 'WEDNESDAYS · TESTING / UAT',
          gradient: 'linear-gradient(135deg,#ff8d2b,#ff6a00 58%,#ffc27a 100%)',
          glow: 'rgba(255,106,0,0.58)',
          border: 'rgba(255,205,150,0.7)',
        };

    const style = document.createElement('style');
    style.textContent = `
      @keyframes envBadgeGlow{
        0%{ box-shadow:0 10px 24px ${cfg.glow}, 0 0 0 0 rgba(255,255,255,0.06); transform:translateX(-50%) translateY(0); }
        100%{ box-shadow:0 14px 34px ${cfg.glow}, 0 0 22px ${cfg.glow}; transform:translateX(-50%) translateY(1px); }
      }
      @media (max-width: 720px){
        #env-banner{
          top:8px !important;
          padding:7px 12px !important;
          font-size:10px !important;
          max-width:calc(100vw - 24px) !important;
        }
      }
    `;
    document.head.appendChild(style);

    function _appendBadge() {
      if (document.getElementById('env-banner')) return;
      const badge = document.createElement('div');
      badge.id = 'env-banner';
      badge.textContent = cfg.label;
      badge.style.cssText = [
        'position:fixed', 'top:10px', 'left:50%', 'transform:translateX(-50%)',
        'z-index:10002', 'display:inline-flex', 'align-items:center', 'justify-content:center',
        'padding:8px 16px', 'max-width:min(460px,calc(100vw - 36px))',
        'border-radius:999px', `background:${cfg.gradient}`, 'color:#fff',
        'font-size:11px', 'font-weight:800', 'letter-spacing:0.11em', 'text-align:center',
        'border:1px solid ' + cfg.border,
        'backdrop-filter:blur(10px)',
        'text-shadow:0 1px 1px rgba(0,0,0,0.25)',
        'animation:envBadgeGlow 2.4s ease-in-out infinite alternate',
      ].join(';');
      document.body.appendChild(badge);
    }
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', _appendBadge);
    } else {
      _appendBadge();
    }
  }

  // ── 2. Env switcher pill — all environments, fixed bottom-right ───────────
  // Floats at same level as taskbar (both bottom: 14px)
  const pills = [
    { label: 'Fridays',    href: 'http://localhost:5050/ui', active: stage === 'PROD', color: 'var(--accent,#2f6bff)', glow: null },
    { label: 'Mondays',    href: 'http://localhost:5051/ui', active: stage === 'DEV',  color: '#4facfe',               glow: '#4facfe88' },
    { label: 'Wednesdays', href: 'http://localhost:5053/ui', active: stage === 'UAT',  color: '#ff6a00',               glow: '#ff6a0088' },
  ];

  const switcher = document.createElement('div');
  switcher.id = 'env-switcher';
  switcher.style.cssText = [
    'position:fixed', 'bottom:14px', 'right:14px', 'z-index:200',
    'display:flex', 'align-items:center', 'gap:2px',
    'background:var(--card,#fff)', 'border:1px solid var(--border,#d6e0ef)',
    'border-radius:8px', 'padding:3px',
    'box-shadow:0 2px 12px rgba(0,0,0,0.22)',
  ].join(';');

  pills.forEach(function (p) {
    if (p.active) {
      const span = document.createElement('span');
      span.textContent = p.label;
      span.style.cssText = 'padding:4px 10px;border-radius:6px;font-size:11px;font-weight:700;letter-spacing:0.03em;color:#fff;'
        + 'background:' + p.color + ';'
        + (p.glow ? 'box-shadow:0 0 8px ' + p.glow + ';' : '');
      switcher.appendChild(span);
    } else {
      const a = document.createElement('a');
      a.href = p.href;
      a.textContent = p.label;
      a.style.cssText = 'padding:4px 10px;border-radius:6px;font-size:11px;font-weight:600;color:var(--text-dim,#617590);text-decoration:none;';
      switcher.appendChild(a);
    }
  });

  function _appendSwitcher() {
    document.body.appendChild(switcher);
    // P4-S32: relocate the top-bar services dropdown into the bottom-right strip,
    // immediately to the LEFT of Fridays. Keep the same DOM node so existing
    // toggleServicesDropdown() / loadServicesPanel() bindings continue to work.
    try {
      const wrap = document.getElementById('services-dropdown-wrap');
      if (wrap && wrap.parentNode !== switcher) {
        // Strip top-bar styling that doesn't fit the bottom strip
        wrap.style.position = 'static';
        const btn = wrap.querySelector('#services-dropdown-btn');
        if (btn) {
          btn.style.height = '24px';
          btn.style.borderRadius = '6px';
          btn.style.padding = '0 10px';
          btn.style.fontSize = '11px';
          btn.style.fontWeight = '600';
          btn.style.background = 'transparent';
          btn.style.border = '1px solid transparent';
          btn.style.color = 'var(--text-dim,#617590)';
        }
        switcher.insertBefore(wrap, switcher.firstChild);
      }
    } catch (_) { /* non-fatal */ }
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _appendSwitcher);
  } else {
    _appendSwitcher();
  }
})();
