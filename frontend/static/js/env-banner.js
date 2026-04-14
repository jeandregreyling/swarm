// env-banner.js — Thin glowing strip for DEV/UAT only. PROD gets nothing.
(function () {
  const stage = (window.ENV_STAGE || '').toUpperCase();
  if (stage === 'PROD' || !stage) return;   // ← no banner on production

  const isDev = stage === 'DEV';
  const cfg = isDev
    ? { label: 'MONDAYS — DEV', gradient: 'linear-gradient(90deg,#00c6fb,#4facfe)', glow: '#4facfe' }
    : { label: 'WEDNESDAYS — UAT', gradient: 'linear-gradient(90deg,#ffb347,#ff6a00)', glow: '#ff9500' };

  const strip = document.createElement('div');
  strip.id = 'env-banner';
  strip.textContent = cfg.label;
  strip.style.cssText = [
    'position:fixed', 'top:0', 'left:0', 'right:0', 'z-index:10002',
    'height:26px', 'line-height:26px',
    'text-align:center', 'font-size:11px', 'font-weight:700', 'letter-spacing:0.08em',
    `background:${cfg.gradient}`, 'color:#fff',
    `box-shadow:0 0 18px 4px ${cfg.glow}99`,
    `animation:envStripGlow 2.2s infinite alternate`,
  ].join(';');

  const style = document.createElement('style');
  style.textContent = `@keyframes envStripGlow{0%{box-shadow:0 0 14px 3px ${cfg.glow}77}100%{box-shadow:0 0 28px 8px ${cfg.glow}cc}}`;

  document.head.appendChild(style);
  document.body.prepend(strip);

  // Push body content down so the strip doesn't overlap anything
  document.body.style.paddingTop = '26px';
})();
