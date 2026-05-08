// app.js — Core app — window opening, home, navigation
// Clean version - no top-level return, all functions defined properly
//
// NOTE (V7C-A01, 2026-04-24): the previous stub definitions of
// loadStudioData() and studioSetTab() lived here as "Early definitions to
// prevent ReferenceErrors". They are now removed — the real implementations
// in views/studio.js are the single source of truth and that file loads
// before any Studio window can be opened (see terminal_base.html script
// order: app.js @2414, studio.js @2430, Studio window opens on user click
// which happens after the full script suite has parsed). Keeping the stubs
// here was a latent footgun: any future script inserted between app.js and
// studio.js would mask the real Studio wiring with silent console.log
// no-ops. Covered by tests/test_v7c_a01_studio_default.py.

function _launchHomeNode(node) {
    if (!node) return false;

    let winId = String(node.dataset.winId || '').trim();
    let winTitle = String(node.dataset.winTitle || '').trim();
    let winTemplate = String(node.dataset.winTemplate || '').trim();

    if (!winId || !winTitle || !winTemplate) {
        const inline = String(node.getAttribute('onclick') || '');
        const match = inline.match(/openWindow\('([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\)/);
        if (!match) return false;
        winId = match[1];
        winTitle = match[2];
        winTemplate = match[3];
    }

    _troubleshootLog && _troubleshootLog('info', 'Card click launch', `id=${winId} template=${winTemplate}`);
    openWindow(winId, winTitle, winTemplate);

    const afterOpen = String(node.dataset.afterOpen || '').trim();
    if (afterOpen.startsWith('docsSetTab:')) {
        const tab = afterOpen.split(':')[1] || 'all';
        setTimeout(() => {
            if (typeof docsSetTab === 'function') docsSetTab(tab);
        }, 120);
    } else if (afterOpen.startsWith('studioSetTab:')) {
        const tab = afterOpen.split(':')[1] || 'pending';
        setTimeout(() => {
            if (typeof studioSetTab === 'function') studioSetTab(tab);
        }, 140);
    }

    return true;
}

function syncTaskbarLaunchers() {
    const strip = document.getElementById('taskbar-launchers');
    if (!strip) return;
    const PINNED_LAUNCHERS = ['chat', 'terminal', 'knowledge', 'studio', 'media-center'];
    const PINNED_LAUNCHER_META = {
        'chat':         { title: 'Chat',         template: 'view-chat' },
        'terminal':     { title: 'Terminal',     template: 'view-terminal' },
        'knowledge':    { title: 'Knowledge',    template: 'view-knowledge' },
        'studio':       { title: 'Studio',       template: 'view-studio' },
        'media-center': { title: 'Media Center', template: 'view-media-center' },
    };

    // V8 Orbs overhaul (S-EAA7C440CC): mark active windows with a ring +
    // underline, support a data-badge count on the source home card for
    // unread / attention indicators.
    const openWinIds = new Set();
    try {
        if (window.winManager && window.winManager.windows) {
            window.winManager.windows.forEach((w) => {
                const base = (w && (w.baseId || w.id)) ? String(w.baseId || w.id).split('-')[0] : '';
                if (base) openWinIds.add(base);
            });
        }
    } catch (_) { /* no-op */ }

    strip.innerHTML = '';
    const launchNodes = Array.from(document.querySelectorAll('#quick-cards .home-card[data-win-id]'));
    const launchNodeMap = new Map(launchNodes.map((node) => [String(node.dataset.winId || '').trim(), node]));
    const orderedNodes = [];
    PINNED_LAUNCHERS.forEach((winId) => {
        const node = launchNodeMap.get(winId);
        if (node) {
            orderedNodes.push(node);
            return;
        }
        const meta = PINNED_LAUNCHER_META[winId];
        if (meta) {
            orderedNodes.push({
                dataset: {
                    winId,
                    winTitle: meta.title,
                    winTemplate: meta.template,
                },
            });
        }
    });
    launchNodes.forEach((node) => {
        if (!orderedNodes.includes(node)) orderedNodes.push(node);
    });

    orderedNodes.forEach((node) => {
        const winId = String(node.dataset.winId || '').trim();
        const winTitle = String(node.dataset.winTitle || '').trim();
        if (!winId || !winTitle || winId === 'email') return;

        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'taskbar-launcher-btn';
        btn.title = winTitle;
        btn.setAttribute('aria-label', winTitle);
        if (openWinIds.has(winId)) btn.dataset.active = '1';
        btn.innerHTML = fridaysWindowIconMarkup(winId);
        const badgeCount = parseInt(node.dataset.badge || '0', 10);
        if (badgeCount > 0) {
            const badge = document.createElement('span');
            badge.className = 'taskbar-badge';
            badge.textContent = badgeCount > 99 ? '99+' : String(badgeCount);
            btn.appendChild(badge);
        }
        btn.addEventListener('click', (event) => {
                event.preventDefault();
                event.stopPropagation();
            try {
                if (node instanceof HTMLElement) {
                    _launchHomeNode(node);
                } else {
                    openWindow(winId, winTitle, String(node?.dataset?.winTemplate || `view-${winId}`));
                }
            } catch (err) {
                _troubleshootLog && _troubleshootLog('error', 'Taskbar launcher failed', String(err?.message || err));
                showToast && showToast('Open window failed: ' + (err?.message || err), 'error');
            }
        });
        strip.appendChild(btn);
    });
}

function bindHomeLaunchClicks() {
    if (window.__SWARM_DEBUG) console.debug('[App] bindHomeLaunchClicks called');
    
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
            
            if (event.defaultPrevented) return;
            
            event.preventDefault();
            
            try {
                if (!_launchHomeNode(node)) return;
            } catch (err) {
                _troubleshootLog && _troubleshootLog('error', 'Card click launch failed', String(err?.message || err));
                showToast && showToast('Open window failed: ' + (err?.message || err), 'error');
            }
        }, { capture: true });
    });
}

function openWindow(id, title, templateId, options = {}) {
    _troubleshootLog && _troubleshootLog('info', 'openWindow requested', `id=${id} title=${title} template=${templateId}`);

    const cleanTitle = title.replace(/^[^\w\s]+ /, '').replace(/<[^>]+>/g, '').trim();
    const multi     = options.multi || false;
    const windowKey = multi ? `${id}-${Date.now()}` : id;

    if (!multi) {
        const existing = winManager && winManager.windows ? winManager.windows.get(windowKey) : null;
        if (existing && existing.minimized) {
            winManager.minimize(windowKey);
            return;
        }
        if (existing) {
            // Focus existing window — opening a second instance with shared DOM IDs
            // (e.g. #question-input, #chat-messages) breaks getElementById lookups.
            winManager.focus(windowKey);
            return;
        }
    }

    const win = winManager.create(windowKey, cleanTitle, templateId, { baseId: id, templateId });
    if (!win) {
        _troubleshootLog && _troubleshootLog('error', 'winManager.create returned no window', `id=${windowKey}`);
        return;
    }

    // Load data based on the base window type (id, not windowKey)
    setTimeout(() => {
        try {
            if (id === 'chat') loadChatData && loadChatData(win);
            else if (id === 'terminal') loadTerminalData && loadTerminalData(win);
            else if (id === 'files') loadFilesData && loadFilesData(win);
            else if (id === 'git') loadGitData && loadGitData(win);
            else if (id === 'memory') loadMemoryData && loadMemoryData(win);
            else if (id === 'monitor') loadMonitorData && loadMonitorData(win);
            else if (id === 'settings') loadSettingsWindowData && loadSettingsWindowData(win);
            else if (id === 'docs') loadDocsData && loadDocsData(win);
            else if (id === 'skills') loadSkillsData && loadSkillsData(win);
            else if (id === 'tickets') loadTicketsData && loadTicketsData(win);
            else if (id === 'studio') loadStudioData(win);
            else if (id === 'email') loadEmailData && loadEmailData(win);
            else if (id === 'library') libInit && libInit();
            else if (id === 'time-wizard') initTimeWizard && initTimeWizard();
            else if (id === 'ghost-brief') initGhostBrief && initGhostBrief();
            else if (id === 'access') loadAccessData && loadAccessData(win);
            else if (id === 'agents-config') loadAgentsConfigData && loadAgentsConfigData(win);
            else if (id === 'localai') initializeLocalAiPanel && initializeLocalAiPanel();
            else if (id === 'media-center') initMediaCenter && initMediaCenter(win);
            else if (id === 'trace') initTraceView && initTraceView(win);
            else if (id === 'onboarding') _initOnboarding && _initOnboarding();
            else if (id === 'knowledge') loadKnowledgeData && loadKnowledgeData(win);
            else if (id === 'vpn') loadVpnData && loadVpnData(win);
            else if (id === 'tasker') loadTaskerData && loadTaskerData(win);
            else if (id === 'health-digest') loadHealthDigest && loadHealthDigest(win);
            else if (id === 'media') loadMediaData && loadMediaData(win);
            else if (id === 'records-files') loadRecordsFilesData && loadRecordsFilesData(win);
            else if (id === 'money-hub') loadMoneyHubData && loadMoneyHubData(win);
            else if (id === 'users') _loadUsersWindowContent && _loadUsersWindowContent(win);

            _troubleshootLog && _troubleshootLog('info', 'Window opened', `id=${windowKey} base=${id}`);
        } catch (err) {
            _troubleshootLog && _troubleshootLog('error', 'Window loader failed', `id=${windowKey} base=${id} error=${err?.message || err}`);
        }
    }, 100);

    showToast && showToast(`Opened ${cleanTitle}`, 'success');
}

// Open a second instance of any tile — called by the ⧉ button in window headers.
function openWindowDuplicate(winId) {
    const state = winManager && winManager.windows ? winManager.windows.get(winId) : null;
    if (!state) return;
    const baseId     = state.baseId || winId;
    const templateId = state.templateId || `view-${baseId}`;
    openWindow(baseId, state.title, templateId, { multi: true });
}

function goHome() {
    if (winManager && winManager.windows) {
        Array.from(winManager.windows.keys()).forEach(id => {
            winManager.close(id);
        });
    }
}

// Quick card reordering (kept from your original)
const QUICK_CARD_ORDER_KEY = 'fridays_quick_card_order';

function initHomeCardReorder() {
    const grid = document.getElementById('quick-cards');
    if (!grid || grid.dataset.reorderBound === '1') return;
    grid.dataset.reorderBound = '1';
    
    _restoreQuickCardOrder(grid);
    syncTaskbarLaunchers();
    _initDragAndDrop(grid);
    if (window.__SWARM_DEBUG) console.debug('[App] initHomeCardReorder ready — drag enabled');
}

function _initDragAndDrop(grid) {
    let dragged = null;       // the card being moved
    let placeholder = null;   // visual gap marker
    let startX = 0, startY = 0;
    let offsetX = 0, offsetY = 0;
    let hasMoved = false;

    // Mark all cards as draggable (Phase-5 SMALL: include home-card-add so the "+" tile
    // can be repositioned like any other tile).
    grid.querySelectorAll('.home-card').forEach(c => c.classList.add('drag-ready'));

    grid.addEventListener('pointerdown', (e) => {
        const card = e.target.closest('.home-card');
        if (!card) return;
        if (e.button !== 0) return; // left click only

        dragged = card;
        hasMoved = false;
        const rect = card.getBoundingClientRect();
        startX = e.clientX;
        startY = e.clientY;
        offsetX = e.clientX - rect.left;
        offsetY = e.clientY - rect.top;

        // Delay activation until actual movement (so clicks still work)
        const onMove = (ev) => {
            const dx = Math.abs(ev.clientX - startX);
            const dy = Math.abs(ev.clientY - startY);
            if (dx < 5 && dy < 5) return; // dead zone for taps

            if (!hasMoved) {
                hasMoved = true;
                _startDrag(card, rect);
            }
            _moveDrag(ev);
        };

        const onUp = () => {
            document.removeEventListener('pointermove', onMove);
            document.removeEventListener('pointerup', onUp);
            if (hasMoved) _endDrag();
            dragged = null;
        };

        document.addEventListener('pointermove', onMove);
        document.addEventListener('pointerup', onUp);
    });

    function _startDrag(card, rect) {
        card.classList.add('drag-active');
        card.style.position = 'fixed';
        card.style.zIndex = '9999';
        card.style.width = rect.width + 'px';
        card.style.height = rect.height + 'px';
        card.style.left = rect.left + 'px';
        card.style.top = rect.top + 'px';
        card.style.pointerEvents = 'none';
        card.style.transition = 'none';

        // Create placeholder
        placeholder = document.createElement('div');
        placeholder.className = 'drag-placeholder';
        placeholder.style.width = rect.width + 'px';
        placeholder.style.height = rect.height + 'px';
        card.parentNode.insertBefore(placeholder, card);
    }

    function _moveDrag(ev) {
        if (!dragged) return;
        dragged.style.left = (ev.clientX - offsetX) + 'px';
        dragged.style.top  = (ev.clientY - offsetY) + 'px';

        // Find which card we're hovering over (include home-card-add so "+" is a valid neighbour)
        const cards = Array.from(grid.querySelectorAll('.home-card:not(.drag-active)'));
        let closest = null, closestDist = Infinity;
        for (const c of cards) {
            const r = c.getBoundingClientRect();
            const cx = r.left + r.width / 2;
            const cy = r.top + r.height / 2;
            const dist = Math.hypot(ev.clientX - cx, ev.clientY - cy);
            if (dist < closestDist) {
                closestDist = dist;
                closest = c;
            }
        }
        if (closest && placeholder) {
            const r = closest.getBoundingClientRect();
            const after = ev.clientX > r.left + r.width / 2;
            if (after) {
                closest.parentNode.insertBefore(placeholder, closest.nextSibling);
            } else {
                closest.parentNode.insertBefore(placeholder, closest);
            }
        }
    }

    function _endDrag() {
        if (!dragged) return;
        dragged.classList.remove('drag-active');
        dragged.style.position = '';
        dragged.style.zIndex = '';
        dragged.style.width = '';
        dragged.style.height = '';
        dragged.style.left = '';
        dragged.style.top = '';
        dragged.style.pointerEvents = '';
        dragged.style.transition = '';

        // Drop card at placeholder position
        if (placeholder && placeholder.parentNode) {
            placeholder.parentNode.insertBefore(dragged, placeholder);
            placeholder.remove();
        }
        placeholder = null;

        // Save new order
        _saveCardOrder(grid);
    }
}

function _saveCardOrder(grid) {
    const order = Array.from(grid.querySelectorAll('.home-card[data-win-id]'))
        .map(c => c.dataset.winId);
    try {
        localStorage.setItem(QUICK_CARD_ORDER_KEY, JSON.stringify(order));
    } catch (_) {}
    syncTaskbarLaunchers();
}

function _restoreQuickCardOrder(grid) {
    let savedOrder = [];
    try {
        savedOrder = JSON.parse(localStorage.getItem(QUICK_CARD_ORDER_KEY) || '[]');
    } catch (_) {}
    if (!Array.isArray(savedOrder) || !savedOrder.length) return;
    
    const cardsById = new Map(Array.from(grid.querySelectorAll('.home-card[data-win-id]')).map((card) => [card.dataset.winId, card]));
    savedOrder.forEach((id) => {
        const card = cardsById.get(id);
        if (card) grid.appendChild(card);
    });
}

// Make functions globally available
window.openWindow = openWindow;
window.goHome = goHome;
window.bindHomeLaunchClicks = bindHomeLaunchClicks;
window.loadStudioData = loadStudioData;
window.studioSetTab = studioSetTab;
window.initHomeCardReorder = initHomeCardReorder;
window.syncTaskbarLaunchers = syncTaskbarLaunchers;

// Log that app.js loaded cleanly
if (window.__SWARM_DEBUG) console.debug('[App.js] Core functions loaded successfully');
