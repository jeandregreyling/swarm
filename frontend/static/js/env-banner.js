// env-banner.js — DEV/UAT glowing strip + env switcher pill (all envs)
(function () {
  const stage = (window.ENV_STAGE || '').toUpperCase();
  if (!stage) return;   // no ENV_STAGE at all — do nothing

  // ── 1. Glowing strip — DEV and UAT only ──────────────────────────────────
  if (stage !== 'PROD') {
    const isDev = stage === 'DEV';
    const cfg = isDev
      ? { label: 'MONDAYS — DEV', gradient: 'linear-gradient(90deg,#00c6fb,#4facfe)', glow: '#4facfe' }
      : { label: 'WEDNESDAYS — UAT', gradient: 'linear-gradient(90deg,#ffb347,#ff6a00)', glow: '#ff9500' };

    const style = document.createElement('style');
    style.textContent = `@keyframes envStripGlow{0%{box-shadow:0 0 14px 3px ${cfg.glow}77}100%{box-shadow:0 0 28px 8px ${cfg.glow}cc}}`;
    document.head.appendChild(style);

    const strip = document.createElement('div');
    strip.id = 'env-banner';
    strip.textContent = cfg.label;
    strip.style.cssText = [
      'position:fixed', 'top:0', 'left:0', 'right:0', 'z-index:10002',
      'height:26px', 'line-height:26px',
      'text-align:center', 'font-size:11px', 'font-weight:700', 'letter-spacing:0.08em',
      `background:${cfg.gradient}`, 'color:#fff',
      `animation:envStripGlow 2.2s infinite alternate`,
    ].join(';');
    document.body.prepend(strip);

    // #home-page is position:absolute top:0 — push it below the strip
    function _offsetHomePage() {
      const hp = document.getElementById('home-page');
      if (hp) {
        hp.style.top = '26px';
        hp.style.height = 'calc(100% - 26px)';
      }
    }
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', _offsetHomePage);
    } else {
      _offsetHomePage();
    }
  }

  // ── 2. Env switcher pill — all environments, fixed bottom-right ───────────
  // Sits above the taskbar (48px) so it never overlaps any header content
  const pills = [
    { label: 'Fridays',    href: 'http://localhost:5050/ui', active: stage === 'PROD', color: 'var(--accent,#2f6bff)', glow: null },
    { label: 'Mondays',    href: 'http://localhost:5051/ui', active: stage === 'DEV',  color: '#4facfe',               glow: '#4facfe88' },
    { label: 'Wednesdays', href: 'http://localhost:5053/ui', active: stage === 'UAT',  color: '#ff6a00',               glow: '#ff6a0088' },
  ];

  const switcher = document.createElement('div');
  switcher.id = 'env-switcher';
  switcher.style.cssText = [
    'position:fixed', 'bottom:60px', 'right:14px', 'z-index:10001',
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
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _appendSwitcher);
  } else {
    _appendSwitcher();
  }
})();
