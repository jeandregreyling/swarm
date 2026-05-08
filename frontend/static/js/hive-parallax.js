// P4-M31: Hive Grid creao.ai-style parallax (minimal first pass).
// Listens for mousemove on .home-card and writes --hc-rx / --hc-ry CSS vars
// to drive a subtle 3D tilt. Cheap (no observers, single rAF), GPU-only.
// Honours prefers-reduced-motion.
(function () {
  if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  const MAX_TILT = 6; // degrees
  let rafQueued = false;
  let lastTarget = null;
  let lastEvent = null;

  function _apply() {
    rafQueued = false;
    if (!lastTarget || !lastEvent) return;
    const card = lastTarget;
    const ev = lastEvent;
    const r = card.getBoundingClientRect();
    if (!r.width || !r.height) return;
    const px = (ev.clientX - r.left) / r.width;   // 0..1
    const py = (ev.clientY - r.top) / r.height;   // 0..1
    const ry = (px - 0.5) * 2 * MAX_TILT;          // left/right
    const rx = -(py - 0.5) * 2 * MAX_TILT;         // up/down (invert)
    card.style.setProperty('--hc-rx', rx.toFixed(2) + 'deg');
    card.style.setProperty('--hc-ry', ry.toFixed(2) + 'deg');
  }

  function _onMove(ev) {
    const card = ev.target.closest && ev.target.closest('.home-card');
    if (!card) return;
    lastTarget = card;
    lastEvent = ev;
    if (!rafQueued) {
      rafQueued = true;
      requestAnimationFrame(_apply);
    }
  }

  function _onLeave(ev) {
    const card = ev.target.closest && ev.target.closest('.home-card');
    if (!card) return;
    card.style.setProperty('--hc-rx', '0deg');
    card.style.setProperty('--hc-ry', '0deg');
    lastTarget = null;
  }

  document.addEventListener('mousemove', _onMove, { passive: true });
  document.addEventListener('mouseleave', _onLeave, true);
  document.addEventListener('mouseout', _onLeave, true);
})();
