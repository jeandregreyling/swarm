(function () {
  if (window.__aigFocus) return;

  let lastKey = '';
  let debounceTimer = null;

  function _post(payload) {
    fetch('/api/governor/focus', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).catch(() => {});
  }

  function _surfaceFromNode(node) {
    if (!node || !node.closest) return null;
    const home = node.closest('.home-card[data-win-id]');
    if (home) {
      return {
        surface: home.dataset.winId || 'home-card',
        title: home.dataset.winTitle || home.dataset.winId || '',
        source: 'home-card',
        path: home.dataset.winTemplate || '',
      };
    }
    const win = node.closest('[id^="win-"]');
    if (win) {
      const winId = (win.id || '').replace(/^win-/, '') || 'window';
      const titleNode = win.querySelector('.window-title, .window-header-title, .window-name');
      return {
        surface: winId,
        title: titleNode ? String(titleNode.textContent || '').trim() : winId,
        source: 'window',
        path: win.getAttribute('data-template') || '',
      };
    }
    return null;
  }

  function _emit(surface) {
    if (!surface || !surface.surface) return;
    const key = [surface.surface, surface.title, surface.source, surface.path].join('|');
    if (key === lastKey) return;
    lastKey = key;
    _post(surface);
  }

  function _schedule(surface) {
    if (!surface) return;
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => _emit(surface), 150);
  }

  document.addEventListener('click', function (ev) {
    _schedule(_surfaceFromNode(ev.target));
  }, true);

  document.addEventListener('focusin', function (ev) {
    _schedule(_surfaceFromNode(ev.target));
  }, true);

  window.__aigFocus = { emit: _emit };
})();
