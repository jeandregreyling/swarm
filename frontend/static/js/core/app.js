// Core app — window opening, home, navigation
// Extracted from terminal_base.html

// ═══════════════════════════════════════════════════════════════════════════
// WINDOW FUNCTIONS
// ═══════════════════════════════════════════════════════════════════════════

function openWindow(id, title, templateId) {
  _troubleshootLog('info', 'openWindow requested', `id=${id} title=${title} template=${templateId}`);
  // Strip any existing emoji from title  
  const cleanTitle = title.replace(/^[^\w\s]+ /, '').trim();
  const icon = windowIcons[id] || '📦';
  const titleWithIcon = `${icon} ${cleanTitle}`;
  let windowKey = id;
  let windowTitle = titleWithIcon;
  const existing = winManager.windows.get(id);
  if (existing && !existing.minimized) {
    // Window is open — clicking again toggles it to minimized
    winManager.minimize(id);
    return;
  }
  if (existing && existing.minimized) {
    let n = 2;
    while (winManager.windows.has(`${id}__${n}`)) n += 1;
    windowKey = `${id}__${n}`;
    windowTitle = `${titleWithIcon} ${n}`;
  }
  const win = winManager.create(windowKey, windowTitle, templateId, { baseId: id });
  if (!win) {
    _troubleshootLog('error', 'winManager.create returned no window', `id=${id}`);
    return;
  }
  
  // Load data based on window type
  setTimeout(() => {
    try {
      if (id === 'chat') loadChatData(win);
      else if (id === 'terminal') loadTerminalData(win);
      else if (id === 'files') loadFilesData(win);
      else if (id === 'git') loadGitData(win);
      else if (id === 'memory') loadMemoryData(win);
      else if (id === 'monitor') loadMonitorData(win);
      else if (id === 'docs') loadDocsData(win);
      else if (id === 'skills') loadSkillsData(win);
      else if (id === 'tickets') loadTicketsData(win);
      else if (id === 'studio') loadStudioData(win);
      else if (id === 'time-wizard') initTimeWizard();
      else if (id === 'ghost-brief') initGhostBrief();
      else if (id === 'access') loadAccessData(win);
      else if (id === 'agents-config') loadAgentsConfigData(win);
      _troubleshootLog('info', 'Window opened', `id=${windowKey} base=${id}`);
    } catch (err) {
      _troubleshootLog('error', 'Window loader failed', `id=${windowKey} base=${id} error=${err?.message || err}`);
      throw err;
    }
  }, 100);
  
  showToast(`Opened ${cleanTitle}`, 'success');
}

function goHome() {
  // Close all open windows and return to home
  Array.from(winManager.windows.keys()).forEach(id => {
    winManager.close(id);
  });
}

function bindHomeLaunchClicks() {
  const launchNodes = Array.from(document.querySelectorAll('#quick-cards .home-card, #home-content .stat-card'));
  launchNodes.forEach((node) => {
    if (node.dataset.launchBound === '1') return;
    node.dataset.launchBound = '1';
    node.addEventListener('click', (event) => {
      if (node.dataset.dragSuppress === '1') {
        event.preventDefault();
        event.stopPropagation();
        node.dataset.dragSuppress = '0';
        return;
      }
      // Primary path: data attributes. Fallback: legacy inline onclick parser.
      if (event.defaultPrevented) return;
      let winId = String(node.dataset.winId || '').trim();
      let winTitle = String(node.dataset.winTitle || '').trim();
      let winTemplate = String(node.dataset.winTemplate || '').trim();
      if (!winId || !winTitle || !winTemplate) {
        const inline = String(node.getAttribute('onclick') || '');
        const match = inline.match(/openWindow\('([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\)/);
        if (!match) return;
        winId = match[1];
        winTitle = match[2];
        winTemplate = match[3];
      }
      event.preventDefault();
      try {
        _troubleshootLog('info', 'Card click launch', `id=${winId} template=${winTemplate}`);
        openWindow(winId, winTitle, winTemplate);
        const afterOpen = String(node.dataset.afterOpen || '').trim();
        if (afterOpen.startsWith('docsSetTab:')) {
          const tab = afterOpen.split(':')[1] || 'all';
          setTimeout(() => {
            if (typeof docsSetTab === 'function') docsSetTab(tab);
          }, 120);
        }
      } catch (err) {
        _troubleshootLog('error', 'Card click launch failed', String(err?.message || err));
        showToast('Open window failed: ' + (err?.message || err), 'error');
      }
    }, { capture: true });
  });
}

const QUICK_CARD_ORDER_KEY = 'fridays_quick_card_order';

function initHomeCardReorder() {
  const grid = document.getElementById('quick-cards');
  if (!grid || grid.dataset.reorderBound === '1') return;
  grid.dataset.reorderBound = '1';

  _restoreQuickCardOrder(grid);

  let holdTimer = null;
  let dragCard = null;
  let placeholder = null;
  let pointerOffsetX = 0;
  let pointerOffsetY = 0;
  let activePointerId = null;

  const cleanupPending = () => {
    if (holdTimer) {
      clearTimeout(holdTimer);
      holdTimer = null;
    }
  };

  const saveOrder = () => {
    const order = Array.from(grid.querySelectorAll('.home-card[data-win-id]'))
      .filter((card) => !card.classList.contains('drag-placeholder'))
      .map((card) => card.dataset.winId)
      .filter(Boolean);
    try { localStorage.setItem(QUICK_CARD_ORDER_KEY, JSON.stringify(order)); } catch (_) {}
  };

  const animateGridReflow = (mutate) => {
    const cards = Array.from(grid.querySelectorAll('.home-card'));
    const first = new Map(cards.map((card) => [card, card.getBoundingClientRect()]));
    mutate();
    const nextCards = Array.from(grid.querySelectorAll('.home-card'));
    nextCards.forEach((card) => {
      const before = first.get(card);
      if (!before || card.classList.contains('drag-active')) return;
      const after = card.getBoundingClientRect();
      const dx = before.left - after.left;
      const dy = before.top - after.top;
      if (!dx && !dy) return;
      card.style.transition = 'none';
      card.style.transform = `translate(${dx}px, ${dy}px)`;
      requestAnimationFrame(() => {
        card.style.transition = 'transform 0.22s cubic-bezier(0.2, 0.8, 0.2, 1)';
        card.style.transform = '';
      });
    });
  };

  const positionDraggedCard = (event) => {
    if (!dragCard) return;
    dragCard.style.left = `${event.clientX - pointerOffsetX}px`;
    dragCard.style.top = `${event.clientY - pointerOffsetY}px`;
  };

  const reorderPlaceholder = (event) => {
    if (!placeholder || !dragCard) return;
    const siblings = Array.from(grid.querySelectorAll('.home-card')).filter((card) => card !== dragCard && card !== placeholder);
    const target = siblings.find((card) => {
      const rect = card.getBoundingClientRect();
      return event.clientY < rect.top + (rect.height / 2) && event.clientX < rect.right;
    });
    animateGridReflow(() => {
      if (target) {
        grid.insertBefore(placeholder, target);
      } else {
        grid.appendChild(placeholder);
      }
    });
  };

  const endDrag = () => {
    cleanupPending();
    if (!dragCard || !placeholder) return;
    const droppedCard = dragCard;
    const droppedPlaceholder = placeholder;
    droppedCard.releasePointerCapture?.(activePointerId);
    dragCard = null;
    placeholder = null;
    activePointerId = null;

    animateGridReflow(() => {
      grid.insertBefore(droppedCard, droppedPlaceholder);
      droppedPlaceholder.remove();
      droppedCard.classList.remove('drag-active');
      droppedCard.style.position = '';
      droppedCard.style.left = '';
      droppedCard.style.top = '';
      droppedCard.style.width = '';
      droppedCard.style.height = '';
      droppedCard.style.pointerEvents = '';
    });

    droppedCard.dataset.dragSuppress = '1';
    window.setTimeout(() => {
      droppedCard.dataset.dragSuppress = '0';
    }, 220);
    saveOrder();
    document.removeEventListener('pointermove', onPointerMove, true);
    document.removeEventListener('pointerup', onPointerUp, true);
    document.removeEventListener('pointercancel', onPointerUp, true);
  };

  const startDrag = (card, event) => {
    const rect = card.getBoundingClientRect();
    dragCard = card;
    activePointerId = event.pointerId;
    pointerOffsetX = event.clientX - rect.left;
    pointerOffsetY = event.clientY - rect.top;
    placeholder = card.cloneNode(true);
    placeholder.classList.add('drag-placeholder');
    placeholder.removeAttribute('id');
    placeholder.dataset.launchBound = '1';
    placeholder.dataset.dragSuppress = '1';

    animateGridReflow(() => {
      grid.insertBefore(placeholder, card.nextSibling);
    });

    card.classList.add('drag-active');
    card.style.width = `${rect.width}px`;
    card.style.height = `${rect.height}px`;
    card.style.position = 'fixed';
    card.style.left = `${rect.left}px`;
    card.style.top = `${rect.top}px`;
    card.style.pointerEvents = 'none';
    card.setPointerCapture?.(event.pointerId);
    positionDraggedCard(event);

    document.addEventListener('pointermove', onPointerMove, true);
    document.addEventListener('pointerup', onPointerUp, true);
    document.addEventListener('pointercancel', onPointerUp, true);
  };

  const onPointerMove = (event) => {
    if (!dragCard) return;
    positionDraggedCard(event);
    reorderPlaceholder(event);
  };

  const onPointerUp = () => {
    if (dragCard) {
      endDrag();
    } else {
      cleanupPending();
    }
  };

  grid.querySelectorAll('.home-card').forEach((card) => {
    card.classList.add('drag-ready');
    card.addEventListener('pointerdown', (event) => {
      if (event.button !== 0) return;
      cleanupPending();
      holdTimer = window.setTimeout(() => {
        startDrag(card, event);
      }, 170);
    });
    card.addEventListener('pointerup', cleanupPending);
    card.addEventListener('pointerleave', cleanupPending);
    card.addEventListener('pointercancel', cleanupPending);
  });
}

function _restoreQuickCardOrder(grid) {
  let savedOrder = [];
  try {
    savedOrder = JSON.parse(localStorage.getItem(QUICK_CARD_ORDER_KEY) || '[]');
  } catch (_) {
    savedOrder = [];
  }
  if (!Array.isArray(savedOrder) || !savedOrder.length) return;
  const cardsById = new Map(Array.from(grid.querySelectorAll('.home-card[data-win-id]')).map((card) => [card.dataset.winId, card]));
  savedOrder.forEach((id) => {
    const card = cardsById.get(id);
    if (card) grid.appendChild(card);
  });
}
