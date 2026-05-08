// WindowManager — Floating window system
// Extracted from terminal_base.html

// ═══════════════════════════════════════════════════════════════════════════
// WINDOW MANAGER — Floating window system
// ═══════════════════════════════════════════════════════════════════════════

const FRIDAYS_WINDOW_ICON_SVGS = {
  chat: '<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M3 4.5h10v6H7l-3 2v-2H3z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>',
  terminal: '<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M2.5 3.5h11v9h-11zM5 6l2 2-2 2M8.5 10h2.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  files: '<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M2.5 5h4l1-1.5h6V12H2.5z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>',
  memory: '<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M6 4a2 2 0 0 0-3 1.7v1.8A2.5 2.5 0 0 0 4.8 10H6m4-6a2 2 0 0 1 3 1.7v1.8A2.5 2.5 0 0 1 11.2 10H10M6 4v8m4-8v8M6 8h4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  knowledge: '<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M3 3.5h3v9H3zM7 3.5h3v9H7zM11.5 3.5l2.5 8.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  settings: '<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M8 3.3 9 4l1.3-.3.8 1.2-.8 1 .2 1.2 1 .8-.5 1.3-1.4.1-.8 1-.1 1.3-1.4.3-.7-1.1H7l-.7 1.1-1.4-.3-.1-1.3-.8-1-1.4-.1-.5-1.3 1-.8.2-1.2-.8-1 .8-1.2L7 4l1-.7Z" stroke="currentColor" stroke-width="1.1" stroke-linejoin="round"/><circle cx="8" cy="8" r="1.7" stroke="currentColor" stroke-width="1.2"/></svg>',
  monitor: '<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M8 8l2.5-2.5M4.5 11.5A5 5 0 0 1 11.5 4.5M2.8 13.2a7.4 7.4 0 0 1 10.4-10.4M8 8l-1.5 4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
  trace: '<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M6 2h4M5.5 2v4.5L3 11.5a1 1 0 0 0 .9 1.5h8.2a1 1 0 0 0 .9-1.5L10.5 6.5V2" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  docs: '<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M4 3.5h7.5v9H4a1.5 1.5 0 0 0 0-3h7.5M4 3.5a1.5 1.5 0 0 0 0 3M4 6.5h7.5" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>',
  skills: '<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M8 5.2a2.8 2.8 0 1 0 0 5.6 2.8 2.8 0 0 0 0-5.6Zm0-2.2v1.2m0 7.6V13m5-5H11.8M4.2 8H3m8.1-3.1.9-.9M4 12l.9-.9m6.2 0 .9.9M4 4l.9.9" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
  tickets: '<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M3 5.5h10v2a1.5 1.5 0 0 0 0 3v2H3v-2a1.5 1.5 0 0 0 0-3zM6 5.5v7" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>',
  studio: '<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M8 3c-2.8 0-5 1.9-5 4.4 0 2.4 2 4.3 4.5 4.3H9a1.5 1.5 0 0 0 0-3h-.5a.8.8 0 0 1-.8-.8A1.9 1.9 0 0 1 9.6 6H11A2 2 0 0 0 13 4c0-.6-.3-1-.8-1.1A9.4 9.4 0 0 0 8 3Z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><circle cx="5.2" cy="7" r=".7" fill="currentColor"/><circle cx="7" cy="5.7" r=".7" fill="currentColor"/></svg>',
  'time-wizard': '<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M8 3.2a4.8 4.8 0 1 0 4.1 2.3M8 1.8v2.4M8 8h2.3M12 3.3l.4 2.3-2.3.4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  access: '<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M6.5 9.5A2.5 2.5 0 1 1 9 7h4v2h-1.5v1.5H10V12H8.5V9.9A2.5 2.5 0 0 1 6.5 9.5Z" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  'agents-config': '<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><rect x="4" y="5" width="8" height="6.5" rx="1.5" stroke="currentColor" stroke-width="1.3"/><path d="M8 3v2M6 8h0M10 8h0M6.2 10.1h3.6" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
  email: '<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><rect x="2" y="4" width="12" height="8" rx="1.5" stroke="currentColor" stroke-width="1.3"/><path d="M2 5.5L8 9l6-3.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  feeds: '<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M3 12a1 1 0 1 0 2 0 1 1 0 0 0-2 0ZM3 8.5a4.5 4.5 0 0 1 4.5 4.5M3 5a8 8 0 0 1 8 8" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
  'media-center': '<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><rect x="2.5" y="4" width="11" height="8" rx="1.5" stroke="currentColor" stroke-width="1.3"/><path d="M5 3v10M11 6.2c0 1.6-1.2 3.1-3 3.6V6.2c1.8.5 3 2 3 3.6Z" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  git: '<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M5 4.5a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3Zm6 4a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3ZM5 7.5v2c0 .8.7 1.5 1.5 1.5H9.5M9.5 5H11v3.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  media: '<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><rect x="2.5" y="4" width="8" height="8" rx="1.4" stroke="currentColor" stroke-width="1.3"/><path d="M6 6.5v3l2.3-1.5L6 6.5Z" stroke="currentColor" stroke-width="1.1" stroke-linejoin="round"/><path d="M12 5v6M14 6v4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
  'records-files': '<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M2.5 5h4l1-1.5h6V12H2.5z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M6 8h6M6 10h4" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/></svg>',
  tasker: '<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.3"/><path d="M8 5v3l2 2" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
  'wishlist-cyber': '<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M8 2l5 2v4c0 3-2 5-5 6-3-1-5-3-5-6V4l5-2zM6 8l1.5 1.5L11 6" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  'wishlist-financial': '<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M2.5 12.5h11M4 11V7M7 11V4M10 11V8M13 11V5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
  'wishlist-trading': '<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M2.5 11l3.5-4 3 2 4.5-5M11 4h2.5v2.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  'wishlist-business': '<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M2.5 6h11v7h-11zM5 6V4h6v2M5 9h6M5 11h4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
};

function fridaysCleanWindowTitle(title) {
  return String(title || '').replace(/^[^\w\s]+ /, '').trim();
}

function fridaysWindowIconMarkup(id) {
  const key = String(id || '').toLowerCase();
  const svg = FRIDAYS_WINDOW_ICON_SVGS[key]
    || '<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><rect x="3" y="3" width="10" height="10" rx="1.5" stroke="currentColor" stroke-width="1.3"/><path d="M3 6.5h10" stroke="currentColor" stroke-width="1.3"/></svg>';
  return `<span class="window-title-icon" aria-hidden="true">${svg}</span>`;
}

class WindowManager {
  constructor() {
    this.windows = new Map();
    this.zIndex = 100;
    this.dragging = null;
    this.resizing = null;
    this.load();
  }

  create(id, title, contentTemplateId, options = {}) {
    if (this.windows.has(id)) {
      this.focus(id);
      return this.windows.get(id);
    }

    const baseId = options.baseId || id;

    const defaults = {
      width: Math.max(520, Math.min(860, Math.round(window.innerWidth * 0.42))),
      height: Math.min(600, window.innerHeight * 0.7),
      x: Math.random() * 100 + 50,
      y: Math.random() * 100 + 50,
      docked: false,
    };

    const persisted = this.savedState?.[id] || {};
    const config = { ...defaults, ...persisted, ...options };
    // Tile opens should use remembered floating geometry, not dock-first behavior.
    config.docked = false;
    const initialWindowTheme = config.windowTheme || 'auto';

    // Get template
    const template = document.getElementById(contentTemplateId);
    const content = template ? template.content.cloneNode(true) : document.createElement('div');

    // Create window
    const win = document.createElement('div');
    win.className = 'floating-window';
    win.id = `win-${id}`;
    win.style.width = config.width + 'px';
    win.style.height = config.height + 'px';
    win.style.left = config.x + 'px';
    win.style.top = config.y + 'px';
    win.style.zIndex = this.zIndex++;

    // Header
    const header = document.createElement('div');
    header.className = 'window-header';
    header.innerHTML = `
      <div class="window-title-wrap">
        <div class="window-title">${fridaysWindowIconMarkup(baseId)}<span class="window-title-label">${fridaysCleanWindowTitle(title)}</span></div>
      </div>
      <div class="window-controls">
        <button class="window-btn" onclick="openWindowHelp('${id}')" title="Help">?</button>
        <button class="window-btn" onclick="openWindowDuplicate('${id}')" title="New window">⧉</button>
        <button class="window-btn" onclick="winManager.toggleMaximize('${id}')" title="Maximize">⬚</button>
        <button class="window-btn" onclick="winManager.minimize('${id}')" title="Minimize">_</button>
        <button class="window-btn" onclick="winManager.pin('${id}')" title="Pin"><svg viewBox="0 0 16 16" width="11" height="11" fill="none" style="vertical-align:-1px"><path d="M10 2L6 6 3 5.5 2 10l4-1 4-4M8.5 3.5l4 4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
        <button class="window-btn" onclick="winManager.fullscreen('${id}')" title="Fullscreen"><svg viewBox="0 0 16 16" width="11" height="11" fill="none" style="vertical-align:-1px"><path d="M2 6V2h4M14 6V2h-4M2 10v4h4M14 10v4h-4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
        <button class="window-btn close" onclick="winManager.close('${id}')" title="Close">✕</button>
      </div>
    `;

    const handles = [
      'n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw',
    ].map(dir => {
      const el = document.createElement('div');
      el.className = `resize-handle resize-${dir}`;
      el.dataset.dir = dir;
      return el;
    });

    // Content area
    const contentDiv = document.createElement('div');
    contentDiv.className = 'window-content';
    contentDiv.appendChild(content);

    // MD-FEATURE-CCD996631130 — Spotlight launch shortcut on every window
    // bottom-bar. A small floating chip sits at the bottom-right inside the
    // window frame so the operator can pop Spotlight without leaving the tile.
    const spotlightBar = document.createElement('button');
    spotlightBar.className = 'window-spotlight-launch';
    spotlightBar.type = 'button';
    spotlightBar.title = 'Open Spotlight (Ctrl+Space)';
    spotlightBar.setAttribute('aria-label', 'Open Spotlight');
    spotlightBar.innerHTML = '<svg viewBox="0 0 16 16" width="11" height="11" fill="none" aria-hidden="true"><circle cx="7" cy="7" r="4.2" stroke="currentColor" stroke-width="1.4"/><path d="M10.4 10.4l3.1 3.1" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>';
    spotlightBar.addEventListener('click', (e) => {
      e.stopPropagation();
      try { if (typeof window.openSpotlight === 'function') window.openSpotlight(); }
      catch (_err) { /* spotlight not yet ready */ }
    });

    win.appendChild(header);
    win.appendChild(contentDiv);
    win.appendChild(spotlightBar);
    handles.forEach(h => win.appendChild(h));

    // Events
    header.addEventListener('mousedown', (e) => this.startDrag(e, id));
    handles.forEach(handle => {
      handle.addEventListener('mousedown', (e) => this.startResize(e, id, handle.dataset.dir));
    });

    document.getElementById('window-container').appendChild(win);

    this.windows.set(id, {
      el: win,
      id,
      baseId,
      templateId: options.templateId || contentTemplateId,
      title,
      config,
      docked: !!config.docked,
      minimized: false,
      maximized: false,
      fullscreen: false,
      pinned: false,
      windowTheme: config.windowTheme || 'auto',
    });

    this.setDocked(id, !!config.docked);
    applyWindowThemeToWindow(this.windows.get(id), this.windows.get(id).windowTheme || 'auto');

    this.addTaskbarBtn(id, title, baseId);
    this.save();
    return this.windows.get(id);
  }

  focus(id) {
    const win = this.windows.get(id);
    if (win) {
      win.el.style.zIndex = this.zIndex++;
      const taskbarBtn = document.querySelector(`[data-winid="${id}"]`);
      if (taskbarBtn) {
        document.querySelectorAll('.taskbar-btn').forEach(b => b.classList.remove('active'));
        taskbarBtn.classList.add('active');
      }
    }
  }

  startDrag(e, id) {
    if (e.target.closest('.window-btn')) return;
    const winState = this.windows.get(id);
    if (!winState || winState.docked) return;
    this.dragging = {
      id,
      startX: e.clientX,
      startY: e.clientY,
      startLeft: this.windows.get(id).el.offsetLeft,
      startTop: this.windows.get(id).el.offsetTop,
    };
    this._boundDrag = (evt) => this.drag(evt);
    this._boundStopDrag = () => this.stopDrag();
    document.addEventListener('mousemove', this._boundDrag);
    document.addEventListener('mouseup', this._boundStopDrag);
  }

  drag(e) {
    if (!this.dragging) return;
    const win = this.windows.get(this.dragging.id).el;
    const dx = e.clientX - this.dragging.startX;
    const dy = e.clientY - this.dragging.startY;
    win.style.left = (this.dragging.startLeft + dx) + 'px';
    win.style.top = (this.dragging.startTop + dy) + 'px';
  }

  stopDrag() {
    if (this.dragging) {
      this.focus(this.dragging.id);
      this.dragging = null;
      this.save();
    }
    if (this._boundDrag) {
      document.removeEventListener('mousemove', this._boundDrag);
      document.removeEventListener('mouseup', this._boundStopDrag);
      this._boundDrag = null;
      this._boundStopDrag = null;
    }
  }

  startResize(e, id, direction = 'se') {
    const winState = this.windows.get(id);
    if (!winState) return;
    if (winState.docked && direction !== 'w') return;
    this.resizing = {
      id,
      direction,
      startX: e.clientX,
      startY: e.clientY,
      startWidth: winState.el.offsetWidth,
      startHeight: winState.el.offsetHeight,
      startLeft: winState.el.offsetLeft,
      startTop: winState.el.offsetTop,
    };
    this._boundResize = (evt) => this.resize(evt);
    this._boundStopResize = () => this.stopResize();
    document.addEventListener('mousemove', this._boundResize);
    document.addEventListener('mouseup', this._boundStopResize);
  }

  resize(e) {
    if (!this.resizing) return;
    const state = this.windows.get(this.resizing.id);
    const win = state.el;
    const dw = e.clientX - this.resizing.startX;
    const dh = e.clientY - this.resizing.startY;
    const dir = this.resizing.direction || 'se';
    const minW = 320;
    const minH = 220;

    if (state.docked) {
      const nextW = Math.max(minW, this.resizing.startWidth - dw);
      win.style.width = nextW + 'px';
      return;
    }

    if (dir.includes('e')) {
      win.style.width = Math.max(minW, this.resizing.startWidth + dw) + 'px';
    }
    if (dir.includes('s')) {
      win.style.height = Math.max(minH, this.resizing.startHeight + dh) + 'px';
    }
    if (dir.includes('w')) {
      const width = Math.max(minW, this.resizing.startWidth - dw);
      const left = this.resizing.startLeft + (this.resizing.startWidth - width);
      win.style.width = width + 'px';
      win.style.left = left + 'px';
    }
    if (dir.includes('n')) {
      const height = Math.max(minH, this.resizing.startHeight - dh);
      const top = this.resizing.startTop + (this.resizing.startHeight - height);
      win.style.height = height + 'px';
      win.style.top = top + 'px';
    }
  }

  stopResize() {
    if (this.resizing) {
      this.resizing = null;
      this.save();
    }
    if (this._boundResize) {
      document.removeEventListener('mousemove', this._boundResize);
      document.removeEventListener('mouseup', this._boundStopResize);
      this._boundResize = null;
      this._boundStopResize = null;
    }
  }

  setDocked(id, docked) {
    const win = this.windows.get(id);
    if (!win) return;
    // Docking disabled: always keep windows as floating.
    win.docked = false;
    win.el.classList.remove('docked-right');
    win.el.style.right = '';
    win.el.style.left = (win.config.x || 80) + 'px';
    win.el.style.top = (win.config.y || 60) + 'px';
    win.el.style.width = (win.config.width || 640) + 'px';
    win.el.style.height = (win.config.height || 600) + 'px';
    win.el.style.zIndex = this.zIndex++;
    this.save();
  }

  toggleDock(id) {
    const win = this.windows.get(id);
    if (!win) return;
    this.setDocked(id, false);
    showToast('Dock mode disabled: windows stay floating', 'info');
  }

  minimize(id) {
    const win = this.windows.get(id);
    if (!win) return;
    win.minimized = !win.minimized;
    if (win.minimized) {
      // Hide window (move off-screen)
      win.el.style.display = 'none';
      showToast(`Minimized ${fridaysCleanWindowTitle(win.title)}`, 'info');
    } else {
      // Restore window
      win.el.style.display = 'flex';
      this.focus(id);
      showToast(`Restored ${fridaysCleanWindowTitle(win.title)}`, 'info');
    }
    this.save();
  }

  minimizeAllToTaskbar() {
    this.windows.forEach((win, id) => {
      if (!win.minimized) {
        this.minimize(id);
      }
    });
  }

  toggleMaximize(id) {
    const win = this.windows.get(id);
    if (!win) return;
    if (win.maximized) {
      win.el.style.left = win.config.x + 'px';
      win.el.style.top = win.config.y + 'px';
      win.el.style.width = win.config.width + 'px';
      win.el.style.height = win.config.height + 'px';
     win.el.style.zIndex = this.zIndex++;
    } else {
      win.config.x = win.el.offsetLeft;
      win.config.y = win.el.offsetTop;
      win.config.width = win.el.offsetWidth;
      win.config.height = win.el.offsetHeight;
      win.el.style.left = '0px';
      win.el.style.top = '0px';
      win.el.style.width = '100vw';
      win.el.style.height = 'calc(100vh - 50px)';
      win.el.style.zIndex = 999;
    }
    win.maximized = !win.maximized;
    this.save();
  }

  pin(id) {
    const win = this.windows.get(id);
    if (win) {
      win.pinned = !win.pinned;
      showToast(win.pinned ? `Pinned ${fridaysCleanWindowTitle(win.title)}` : `Unpinned ${fridaysCleanWindowTitle(win.title)}`, 'info');
      this.save();
    }
  }

  fullscreen(id) {
    const win = this.windows.get(id);
    if (!win) return;
    const removeQuickActions = () => {
      const stale = win.el.querySelectorAll('.quick-actions');
      stale.forEach(node => node.remove());
    };

    if (win.fullscreen) {
      // Restore from fullscreen
      document.getElementById('home-page').style.display = 'flex';
      win.el.style.width = win.config.width + 'px';
      win.el.style.height = win.config.height + 'px';
      win.el.style.left = win.config.x + 'px';
      win.el.style.top = win.config.y + 'px';
      win.el.style.zIndex = this.zIndex++;
      removeQuickActions();
      showToast(`Exited fullscreen`, 'info');
    } else {
      // Enter fullscreen (replace home)
      document.getElementById('home-page').style.display = 'none';
      win.config.x = win.el.offsetLeft;
      win.config.y = win.el.offsetTop;
      win.config.width = win.el.offsetWidth;
      win.config.height = win.el.offsetHeight;
      win.el.style.width = '100vw';
      win.el.style.height = '100vh';
      win.el.style.left = '0px';
      win.el.style.top = '0px';
      win.el.style.zIndex = 999;
      
      // Re-create quick actions on each entry and remove on exit to avoid sticky controls.
      removeQuickActions();
      const quickActions = document.createElement('div');
      quickActions.className = 'quick-actions';
      quickActions.style.cssText = 'position: absolute; top: 60px; left: 20px; display: flex; gap: 8px; z-index: 1002;';
      quickActions.innerHTML = `
        <button onclick="winManager.fullscreen('${id}')" style="padding: 8px 16px; background: var(--card); border: 1px solid var(--border); border-radius: 4px; cursor: pointer; color: var(--text); transition: all 0.2s;">← Exit Fullscreen</button>
      `;
      win.el.appendChild(quickActions);
      
      showToast(`Fullscreen: ${fridaysCleanWindowTitle(win.title)}`, 'success');
    }
    win.fullscreen = !win.fullscreen;
    this.save();
  }

  close(id) {
    const win = this.windows.get(id);
    if (win) {
      if (typeof win.beforeClose === 'function') {
        try {
          win.beforeClose();
        } catch (err) {
          console.warn('[WindowManager] beforeClose failed for', id, err);
        }
      }
      if (win.fullscreen) {
        const home = document.getElementById('home-page');
        if (home) home.style.display = 'flex';
        const stale = win.el.querySelectorAll('.quick-actions');
        stale.forEach(node => node.remove());
        win.fullscreen = false;
      }
      // Persist last known floating geometry even after the window is closed.
      this.savedState = this.savedState || {};
      this.savedState[id] = {
        x: win.el.offsetLeft,
        y: win.el.offsetTop,
        width: win.el.offsetWidth,
        height: win.el.offsetHeight,
        minimized: false,
        maximized: false,
        fullscreen: false,
        pinned: !!win.pinned,
        docked: false,
        windowTheme: win.windowTheme || 'auto',
      };
      win.el.remove();
      this.windows.delete(id);
      const taskbarBtn = document.querySelector(`[data-winid="${id}"]`);
      if (taskbarBtn) taskbarBtn.remove();
      this.save();
    }
  }

  addTaskbarBtn(id, title, baseId) {
    const cleanTitle = fridaysCleanWindowTitle(title);
    const btn = document.createElement('button');
    btn.className = 'taskbar-btn active';
    btn.setAttribute('data-winid', id);
    btn.innerHTML = `${fridaysWindowIconMarkup(baseId || id)}<span class="taskbar-label">${cleanTitle}</span>`;
    
    // Add preview tooltip
    const preview = document.createElement('div');
    preview.className = 'taskbar-preview';
    preview.textContent = cleanTitle;
    btn.appendChild(preview);
    
    btn.onclick = () => {
      const win = this.windows.get(id);
      if (win && win.minimized) {
        this.minimize(id); // restore
      } else if (win) {
        this.minimize(id); // minimize (toggle)
      }
    };
    const taskbar = document.getElementById('taskbar');
    const spacer = document.getElementById('spacer');
    taskbar.insertBefore(btn, spacer);
  }

  save() {
    const state = { ...(this.savedState || {}) };
    this.windows.forEach((win, id) => {
      state[id] = {
        x: win.el.offsetLeft,
        y: win.el.offsetTop,
        width: win.el.offsetWidth,
        height: win.el.offsetHeight,
        minimized: win.minimized,
        maximized: win.maximized,
        fullscreen: win.fullscreen,
        pinned: win.pinned,
        docked: false,
        windowTheme: win.windowTheme || 'auto',
      };
    });
    this.savedState = state;
    localStorage.setItem('fridays-windows', JSON.stringify(state));
  }

  load() {
    const saved = localStorage.getItem('fridays-windows');
    if (saved) {
      try {
        this.savedState = JSON.parse(saved);
      } catch (e) {
        this.savedState = {};
      }
    } else {
      this.savedState = {};
    }
  }
}

function resetWindowLayout() {
  try {
    localStorage.removeItem('fridays-windows');
    if (winManager) {
      winManager.savedState = {};
      winManager.windows.forEach((win, id) => {
        win.el.remove();
        const taskbarBtn = document.querySelector(`[data-winid="${id}"]`);
        if (taskbarBtn) taskbarBtn.remove();
      });
      winManager.windows.clear();
      winManager.save();
    }
    showToast('Window layout reset', 'success');
  } catch (e) {
    showToast('Layout reset failed: ' + (e?.message || e), 'error');
  }
}

const winManager = new WindowManager();
