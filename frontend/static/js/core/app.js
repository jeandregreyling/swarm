// app.js — Core app — window opening, home, navigation
// Clean version - no top-level return, all functions defined properly

// Early definitions to prevent ReferenceErrors
function loadStudioData(win) {
    console.log('[Studio] loadStudioData called for window', win ? win.id : 'unknown');
    // Real implementation will be added once base UI is stable
}

function studioSetTab(tab) {
    console.log('[Studio] studioSetTab called with', tab);
    // Real tab switching will be added later
}

function bindHomeLaunchClicks() {
    console.log('[App] bindHomeLaunchClicks called');
    
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
                _troubleshootLog && _troubleshootLog('info', 'Card click launch', `id=${winId} template=${winTemplate}`);
                openWindow(winId, winTitle, winTemplate);
                
                const afterOpen = String(node.dataset.afterOpen || '').trim();
                if (afterOpen.startsWith('docsSetTab:')) {
                    const tab = afterOpen.split(':')[1] || 'all';
                    setTimeout(() => {
                        if (typeof docsSetTab === 'function') docsSetTab(tab);
                    }, 120);
                }
            } catch (err) {
                _troubleshootLog && _troubleshootLog('error', 'Card click launch failed', String(err?.message || err));
                showToast && showToast('Open window failed: ' + (err?.message || err), 'error');
            }
        }, { capture: true });
    });
}

function openWindow(id, title, templateId) {
    _troubleshootLog && _troubleshootLog('info', 'openWindow requested', `id=${id} title=${title} template=${templateId}`);
    
    const cleanTitle = title.replace(/^[^\w\s]+ /, '').replace(/<[^>]+>/g, '').trim();
    
    const existing = winManager && winManager.windows ? winManager.windows.get(id) : null;
    
    if (existing && existing.minimized) {
        winManager.minimize(id); // restore minimized window
        return;
    }
    
    if (existing && !existing.minimized) {
        winManager.focus(id);
        return;
    }
    
    const win = winManager.create(id, cleanTitle, templateId, { baseId: id });
    if (!win) {
        _troubleshootLog && _troubleshootLog('error', 'winManager.create returned no window', `id=${id}`);
        return;
    }
    
    // Load data based on window type
    setTimeout(() => {
        try {
            if (id === 'chat') loadChatData && loadChatData(win);
            else if (id === 'terminal') loadTerminalData && loadTerminalData(win);
            else if (id === 'files') loadFilesData && loadFilesData(win);
            else if (id === 'git') loadGitData && loadGitData(win);
            else if (id === 'memory') loadMemoryData && loadMemoryData(win);
            else if (id === 'monitor') loadMonitorData && loadMonitorData(win);
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
            else if (id === 'trace') initTraceView && initTraceView(win);
            else if (id === 'onboarding') _initOnboarding && _initOnboarding();
            else if (id === 'knowledge') loadKnowledgeData && loadKnowledgeData(win);
            else if (id === 'vpn') loadVpnData && loadVpnData(win);
            
            _troubleshootLog && _troubleshootLog('info', 'Window opened', `id=${windowKey} base=${id}`);
        } catch (err) {
            _troubleshootLog && _troubleshootLog('error', 'Window loader failed', `id=${windowKey} base=${id} error=${err?.message || err}`);
        }
    }, 100);
    
    showToast && showToast(`Opened ${cleanTitle}`, 'success');
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
    _initDragAndDrop(grid);
    console.log('[App] initHomeCardReorder ready — drag enabled');
}

function _initDragAndDrop(grid) {
    let dragged = null;       // the card being moved
    let placeholder = null;   // visual gap marker
    let startX = 0, startY = 0;
    let offsetX = 0, offsetY = 0;
    let hasMoved = false;

    // Mark all cards as draggable
    grid.querySelectorAll('.home-card').forEach(c => {
        if (!c.classList.contains('home-card-add')) c.classList.add('drag-ready');
    });

    grid.addEventListener('pointerdown', (e) => {
        const card = e.target.closest('.home-card');
        if (!card || card.classList.contains('home-card-add')) return;
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

        // Find which card we're hovering over
        const cards = Array.from(grid.querySelectorAll('.home-card:not(.drag-active):not(.home-card-add)'));
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

// Log that app.js loaded cleanly
console.log('[App.js] Core functions loaded successfully');