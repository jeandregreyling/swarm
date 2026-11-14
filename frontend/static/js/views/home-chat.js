// ═══════════════════════════════════════════════════════════════════════════
// HOME CHAT — lightweight embedded chat on the home page
// Shares conversation data + agent selection with the full Chat window.
// ═══════════════════════════════════════════════════════════════════════════

(function () {
  'use strict';

  if (!window.__fridaysHomeChatRegistryListenerBound) {
    window.addEventListener('fridays:agent-registry-loaded', () => {
      try { _hcRenderAgentPills(); } catch (_) {}
      try { _hcUpdateMeta(); } catch (_) {}
    });
    window.__fridaysHomeChatRegistryListenerBound = true;
  }

  // ── State ────────────────────────────────────────────────────────────────
  let _hcConvId = null;
  let _hcConversations = [];
  let _hcSending = false;
  let _hcInitialized = false;
  let _hcViewVersion = 0;
  let _hcSendVersion = 0;
  const _hcEnv = (window.ENV_STAGE || 'PROD').toUpperCase();

  // An explicitly pinned shared room is restored on both chat surfaces.
  const HC_ACTIVE_THREAD_KEY = 'fridays-home-chat-active-thread';
  const HC_AGENT_TOGGLE_PREFIX = 'fridays-chat-thread-agents-';
  const HC_GLOBAL_AGENTS_KEY = 'fridays-chat-enabled-agents';

  // Agent registry — populated from _loadAgentRegistry() in chat.js
  function _hcAgentOptions() {
    return (typeof CHAT_AGENT_OPTIONS !== 'undefined' && Array.isArray(CHAT_AGENT_OPTIONS))
      ? CHAT_AGENT_OPTIONS
      : [];
  }

  // ── Initialization ───────────────────────────────────────────────────────
  function _hcEnsureChatFirst() {
    const content = document.getElementById('home-content');
    const chat = document.querySelector('.home-chat-section');
    const tiles = document.querySelector('.home-tiles-section');
    const workspace = document.getElementById('home-workspace');   // 12 Nov: Core Workspace sits above chat, collapsible
    if (!content || !chat || !tiles) return;
    // Older running servers may still serve the pre-fix cached template.
    if (workspace) {
      if (content.firstElementChild !== workspace) content.prepend(workspace);
      if (workspace.nextElementSibling !== chat) workspace.insertAdjacentElement('afterend', chat);
    } else if (content.firstElementChild !== chat) content.prepend(chat);
    if (chat.nextElementSibling !== tiles) chat.insertAdjacentElement('afterend', tiles);
  }

  function _hcFitLiveRoom() {
    const chat = document.querySelector('.home-chat-section');
    const content = document.getElementById('home-content');
    if (!chat || !content) return;
    const top = chat.getBoundingClientRect().top + content.scrollTop;
    const taskbarTop = document.getElementById('taskbar')?.getBoundingClientRect().top;
    const bottom = taskbarTop > 0 ? taskbarTop : window.innerHeight;
    chat.style.setProperty('--chat-live-room-height', `${Math.max(280, bottom - top - 14)}px`);
  }
  window.homeFitLiveRoom = _hcFitLiveRoom;

  // ── Other chats active (12 Nov): conversations with activity in the last 15 minutes, one click away ──
  function _hcElsewhere() {
    const bar = document.querySelector('#home-chat-bar .home-chat-bar-center');
    if (!bar) return;
    fetch('/api/conversations', { credentials: 'same-origin' }).then(r => (r.ok ? r.json() : null)).then(list => {
      if (!Array.isArray(list)) return;
      const cutoff = Date.now() - 15 * 60 * 1000;
      const active = list.filter(c => c && c.id && Number(c.id) !== Number(_hcConvId) && c.last_message_at &&
        Date.parse(String(c.last_message_at).replace(' ', 'T') + 'Z') >= cutoff);
      let chip = document.getElementById('home-chat-elsewhere');
      if (!active.length) { if (chip) chip.remove(); return; }
      if (!chip) {
        chip = document.createElement('details');
        chip.id = 'home-chat-elsewhere';
        chip.className = 'hb-elsewhere';
        bar.appendChild(chip);
      }
      const open = chip.open;
      chip.innerHTML = `<summary title="Other conversations with activity in the last 15 minutes">● ${active.length} other chat${active.length === 1 ? '' : 's'} active</summary>` +
        `<div class="hb-elsewhere-list">` + active.slice(0, 8).map(c =>
          `<button type="button" data-conv="${Number(c.id)}">#${Number(c.id)} ${_hcEsc(String(c.title || 'conversation').slice(0, 48))}` +
          `<small> · ${_hcEsc(String(c.last_from || ''))}</small></button>`).join('') + `</div>`;
      chip.open = open;
      chip.querySelectorAll('button[data-conv]').forEach(btn => btn.addEventListener('click', () => {
        const sel = document.getElementById('home-chat-thread-select');
        if (sel) {
          if (![...sel.options].some(o => o.value === btn.dataset.conv)) sel.add(new Option('#' + btn.dataset.conv, btn.dataset.conv));
          sel.value = btn.dataset.conv;
          sel.dispatchEvent(new Event('change'));
        }
        chip.open = false;
      }));
    }).catch(() => {});
  }
  setInterval(() => { if (!document.hidden) _hcElsewhere(); }, 30000);
  setTimeout(_hcElsewhere, 3000);

  // Owner 13 Nov: scrolled up in main chat -> a floating arrow jumps back to the latest message.
  // Owner 13 Nov: main chat shows the latest 20 messages; scrolling to the top loads the 20 before them.
  let _hcOlderBusy = false, _hcNoOlder = null;
  function _hcInitOlderLoader() {
    const list = document.getElementById('home-chat-messages');
    if (!list || list.dataset.olderLoader) return;
    list.dataset.olderLoader = '1';
    list.addEventListener('scroll', () => {
      if (list.scrollTop > 80 || _hcOlderBusy || !_hcConvId || _hcNoOlder === _hcConvId) return;
      const first = list.querySelector('.hc-bubble[data-message-id]');
      if (!first) return;
      _hcOlderBusy = true;
      const convId = _hcConvId;
      fetch(`/api/conversations/${convId}/messages?limit=20&before=${Number(first.dataset.messageId)}`)
        .then(r => (r.ok ? r.json() : null))
        .then(data => {
          if (!data || _hcConvId !== convId) return;
          _hcNoOlder = data.has_more ? null : convId;
          const height = list.scrollHeight;
          list._hcPrependAt = Date.now();
          (data.messages || []).forEach(msg => {
            const el = _hcAppendBubble(msg);
            if (el) list.insertBefore(el, first);
          });
          list.scrollTop += list.scrollHeight - height;
        })
        .catch(() => {})
        .finally(() => { _hcOlderBusy = false; });
    }, { passive: true });
  }

  function _hcInitJumpButton() {
    const list = document.getElementById('home-chat-messages');
    const main = document.getElementById('home-chat-main');
    if (!list || !main || document.getElementById('hc-jump-bottom')) return;
    const btn = document.createElement('button');
    btn.id = 'hc-jump-bottom';
    btn.type = 'button';
    btn.title = 'Click: jump to the latest message. Double-click: auto scroll on or off';
    let auto = localStorage.getItem('hc-auto-follow') !== '0';
    btn.classList.toggle('auto', auto);
    btn.addEventListener('dblclick', () => {
      auto = !auto;
      localStorage.setItem('hc-auto-follow', auto ? '1' : '0');
      btn.classList.toggle('auto', auto);
      if (auto) list.scrollTop = list.scrollHeight;
    });
    btn.setAttribute('aria-label', 'Jump to the latest message');
    btn.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M12 5v13M6 12l6 6 6-6" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    main.appendChild(btn);
    const update = () => {
      const away = list.scrollHeight - list.scrollTop - list.clientHeight > 120;
      btn.classList.toggle('show', away || auto);
      const input = document.getElementById('home-chat-input-area');
      btn.style.bottom = ((input ? input.offsetHeight : 0) + 14) + 'px';
    };
    list.addEventListener('scroll', update, { passive: true });
    if (window.ResizeObserver) new ResizeObserver(update).observe(list);
    new MutationObserver(() => {
      if (auto && Date.now() - (list._hcPrependAt || 0) > 400) list.scrollTop = list.scrollHeight;
      update();
    }).observe(list, { childList: true, subtree: true });
    btn.addEventListener('click', () => list.scrollTo({ top: list.scrollHeight, behavior: 'smooth' }));
    update();
  }

  window.initHomeChat = function () {
    _hcEnsureChatFirst();
    _hcInitJumpButton();
    _hcInitOlderLoader();
    if (_hcInitialized) {
      _hcLoadThreadsListOnly();
      return;
    }
    _hcInitialized = true;
    const savedThread = getSharedChatThreadId() || Number(localStorage.getItem(HC_ACTIVE_THREAD_KEY));
    _hcConvId = Number.isSafeInteger(savedThread) && savedThread > 0 ? savedThread : null;

    _hcSetEnvBadge();
    _hcBindEvents();
    _hcRenderAgentPills();
    refreshChatParticipants();
    _hcLoadThreads();
    _hcSetGreeting();
    _hcFetchInterests();
    _hcInitMiniLandscape();
    _hcRestorePanelState();
    _hcFitLiveRoom();
    window.addEventListener('resize', _hcFitLiveRoom);
	    _hcBindCrossSurfaceRefresh();
	    _hcPruneStaleAgentToggles();
	    _hcLoadProofTrail();

    window.addEventListener('pageshow', (ev) => {
      if (ev.persisted) _hcLoadThreadsListOnly();
    });
  };

  // ── Session 28 fix: cross-surface refresh ────────────────────────────────
  // When another chat surface (main chat window, spotlight, etc.) creates or
  // deletes a conversation, refresh the home-chat thread list so the tile is
  // never stale. Also refresh when the page regains focus, in case an event
  // was missed while the tab was backgrounded.
  let _hcCrossBound = false;
  function _hcBindCrossSurfaceRefresh() {
    if (_hcCrossBound) return;
    _hcCrossBound = true;
    window.addEventListener('hummingbird:shared-thread', (event) => {
      _hcSwitchThread(event.detail.conversation_id);
    });
    window.addEventListener('swarm:conversation-changed', (ev) => {
      const detail = (ev && ev.detail) || {};
      // If the deleted conv is the one we're viewing, drop back to welcome.
      if (detail.type === 'deleted' && Number(detail.conversation_id) === Number(_hcConvId)) {
        _hcNewThread();
        return;
      }
      // Created/updated conversations should only refresh the dropdown. A full
      // _hcLoadThreads() reset clears _hcConvId and replaces the visible
      // transcript with the starter screen while a just-sent turn is rendering.
      _hcLoadThreadsListOnly();
    });
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') {
        _hcLoadThreadsListOnly();
        if (_hcConvId) _hcSilentRefresh(_hcConvId);
      }
    });
    window.addEventListener('focus', () => _hcLoadThreadsListOnly());
  }

  // ── Environment badge ────────────────────────────────────────────────────
  function _hcSetEnvBadge() {
    const badge = document.getElementById('home-chat-env-badge');
    if (!badge) return;
    const env = _hcEnv.toLowerCase();
    const labels = { prod: 'PROD', dev: 'DEV', uat: 'UAT' };
    badge.textContent = labels[env] || env.toUpperCase();
    badge.setAttribute('data-env', env);
  }

  // ── @ participant menu ───────────────────────────────────────────────────
  const _HC_MENTIONS = [
    { key: 'apex', label: 'APEX', role: 'Local execution partner' },
    { key: 'codex', label: 'Codex', role: 'Instructor / connected terminal session' },
    { key: 'instructor', label: 'VS Code Instructor', role: 'Instructor / reviewer' },
    { key: 'gemini', label: 'Gemini', role: 'Architecture advisor' },
    { key: 'claude', label: 'Claude', role: 'Claude Code via its CLI (costs tokens)' },
  ];
  let _hcMention = { open: false, start: -1, end: -1, active: 0, items: [] };
  // Owner 13 Nov: @ list follows Live status: available online peers and every local model not switched Off.
  let _hcMentionLive = null, _hcMentionLiveAt = 0;
  function _hcLoadMentions(input) {
    if (Date.now() - _hcMentionLiveAt < 30000) return;
    _hcMentionLiveAt = Date.now();
    fetch('/api/peer/v1/hb/mentions', { credentials: 'same-origin' })
      .then(r => (r.ok ? r.json() : null))
      .then(data => {
        if (!data || !Array.isArray(data.items)) return;
        const roles = Object.fromEntries(_HC_MENTIONS.map(m => [m.key, m.role]));
        _hcMentionLive = data.items.map(item => ({ key: item.key, label: item.label,
          role: item.tier === 'model' ? 'Local model · ' + item.note : (roles[item.key] || item.note) }));
        if (document.activeElement === input && _hcMention.open) _hcMentionUpdate(input);
      })
      .catch(() => {});
  }

  function _hcMentionClose() {
    const menu = document.getElementById('home-chat-mention-menu');
    if (menu) { menu.style.display = 'none'; menu.innerHTML = ''; }
    _hcMention = { open: false, start: -1, end: -1, active: 0, items: [] };
  }

  function _hcMentionPick(input, idx) {
    const item = _hcMention.items[idx];
    if (!_hcMention.open || !item) return false;
    const value = input.value;
    const before = value.slice(0, _hcMention.start) + (item.slash ? '/' : '@') + item.key + ' ';
    input.value = before + value.slice(_hcMention.end);
    input.focus();
    input.setSelectionRange(before.length, before.length);
    _hcMentionClose();
    input.dispatchEvent(new Event('input'));
    return true;
  }

  // ── "/" Hummingbird system commands (list comes from the server) ─────────
  let _hcSlashCommands = null;
  function _hcLoadSlashCommands(input) {
    if (_hcSlashCommands) return;
    _hcSlashCommands = [];
    fetch('/api/peer/v1/hb/commands', { credentials: 'same-origin' })
      .then(r => (r.ok ? r.json() : null))
      .then(data => {
        if (data && Array.isArray(data.commands)) {
          _hcSlashCommands = data.commands;
          if (document.activeElement === input) _hcMentionUpdate(input);
        } else { _hcSlashCommands = null; }
      })
      .catch(() => { _hcSlashCommands = null; });
  }

  function _hcMentionUpdate(input) {
    const menu = document.getElementById('home-chat-mention-menu');
    const caret = Number(input.selectionStart || 0);
    const typed = input.value.slice(0, caret);
    const slash = typed.match(/^\s*\/([a-zA-Z]*)$/);
    const match = slash ? null : typed.match(/(^|\s)@([a-zA-Z0-9.\-]*)$/);
    if (!menu || (!match && !slash)) { _hcMentionClose(); return; }
    let query, items;
    if (slash) {
      _hcLoadSlashCommands(input);
      query = slash[1].toLowerCase();
      items = (_hcSlashCommands || []).filter(c => c.name.startsWith(query))
        .map(c => ({ key: c.name, label: c.usage, role: c.description + (c.confirm ? ' · asks first' : ''), slash: true }));
    } else {
      query = match[2].toLowerCase();
      _hcLoadMentions(input);
      items = (_hcMentionLive || _HC_MENTIONS).filter(item =>
        item.key.startsWith(query) || item.label.toLowerCase().includes(query));
    }
    if (!items.length) { _hcMentionClose(); return; }
    const active = Math.min(_hcMention.open ? _hcMention.active : 0, items.length - 1);
    _hcMention = { open: true, start: caret - query.length - 1, end: caret, active, items };
    menu.innerHTML = items.map((item, idx) =>
      `<button type="button" role="option" class="chat-mention-item${idx === active ? ' active' : ''}" data-idx="${idx}">` +
      (item.slash ? `<span><strong>${_hcEsc(item.label)}</strong></span>`
                  : `<span><strong>${_hcEsc(item.label)}</strong> @${_hcEsc(item.key)}</span>`) +
      `<span class="chat-mention-meta">${_hcEsc(item.role)}</span></button>`).join('');
    menu.querySelectorAll('button').forEach(btn => {
      btn.addEventListener('mousedown', (e) => { e.preventDefault(); _hcMentionPick(input, Number(btn.dataset.idx)); });
    });
    menu.style.display = 'block';
  }

  function _hcMentionKeydown(e, input) {
    if (!_hcMention.open) return false;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      const count = _hcMention.items.length;
      _hcMention.active = (_hcMention.active + (e.key === 'ArrowDown' ? 1 : count - 1)) % count;
      _hcMentionUpdate(input);
      return true;
    }
    if (e.key === 'Enter' || e.key === 'Tab') {
      e.preventDefault();
      return _hcMentionPick(input, _hcMention.active);
    }
    if (e.key === 'Escape') {
      e.preventDefault();
      _hcMentionClose();
      return true;
    }
    return false;
  }

  // ── Event bindings ───────────────────────────────────────────────────────
  function _hcBindEvents() {
    const input = document.getElementById('home-chat-input');
    const sendBtn = document.getElementById('home-chat-send-btn');
    const threadSel = document.getElementById('home-chat-thread-select');
    const newBtn = document.getElementById('home-chat-new-btn');
    const expandBtn = document.getElementById('home-chat-expand-btn');
    _hcBindHfControls();

    if (sendBtn) {
      sendBtn.textContent = 'Send';
      sendBtn.addEventListener('click', _hcSend);
    }
    if (newBtn) newBtn.addEventListener('click', _hcNewThread);
    if (expandBtn) expandBtn.addEventListener('click', () => {
      // Session 28 fix: hand the current home-chat thread to the main chat
      // window so expand preserves context. Without this the main chat
      // opens on a fresh thread (by design, see conversations.js).
      if (_hcConvId) window.__fridaysChatOpenWithConvId = _hcConvId;
      if (typeof openWindow === 'function') openWindow('chat', 'Chat', 'view-chat');
    });
    if (threadSel) threadSel.addEventListener('change', (e) => {
      const val = e.target.value;
      if (val) {
        _hcSwitchThread(Number(val));
      } else {
        _hcNewThread();
      }
    });
    if (input) {
      input.setAttribute('aria-label', 'Message Hummingbird');
      input.placeholder = 'Message Hummingbird — @ to address a teammate, / for commands';
      input.addEventListener('keydown', (e) => {
        if (_hcMentionKeydown(e, input)) return;
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          _hcSend();
        }
      });
      input.addEventListener('input', () => { _hcAutoGrow(input); _hcUpdateTokenCount(input); _hcUpdateMeta(); _hcMentionUpdate(input); });
      input.addEventListener('blur', () => setTimeout(_hcMentionClose, 150));
      _hcUpdateTokenCount(input);
    }

    // Quick-launch: typing anywhere on home page focuses chat input
    const homePage = document.getElementById('home-page');
    if (homePage && input) {
      homePage.addEventListener('keydown', (e) => {
        // Skip if already in an input/textarea/select, or if modifier keys
        if (e.ctrlKey || e.metaKey || e.altKey) return;
        const tag = (e.target.tagName || '').toLowerCase();
        if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
        if (e.target.closest('button, summary, a, [role="button"]')) return;
        if (e.key.length === 1 && !e.target.isContentEditable) {
          input.focus();
          // Let the character flow into the now-focused input naturally
        }
      });
    }
  }

  function _hcBindHfControls() {
    const status=document.getElementById('hb-hf-status');
    const show=(value)=>{if(status)status.textContent=value;};
    const format=(data)=>{
      const m=data?.mirror||data||{};const states=m.file_states||{};const repos=m.repository_states||{};
      const active=m.active_transfer;
      const path=active?`; active ${active.repo}/${active.path}`:'';
      const scope=m.acquisition_policy?.mode||'full (legacy)';
      const progress=`${m.files_verified||0} verified / ${m.files_known||0} known files; ${m.catalogue_enumeration_complete?'catalogue complete':'catalogue still discovering'}`;
      const blocked=`; ${states.filtered||0} filtered, ${states.budget_blocked||0} budget blocked, ${repos.access_blocked||0} restricted`;
      return `Mirror ${m.state||'unknown'} · ${scope} · ${progress}${blocked}${path}. No ETA until comparable throughput is recorded.`;
    };
    const request=async(action,repo)=>{
      show('Contacting HB…');
      try{
        const response=await fetch(action==='status'?'/api/chat/hf-mirror/status':'/api/chat/hf-mirror/control',{
          method:action==='status'?'GET':'POST',credentials:'same-origin',
          headers:action==='status'?{}:{'Content-Type':'application/json','X-HB-Owner-Action':'1'},
          body:action==='status'?undefined:JSON.stringify(repo?{action,repo}:{action})});
        const data=await response.json();
        if(!response.ok||data.ok!==true)throw new Error(data.error||`HB returned ${response.status}`);
        show((data.message?data.message+' ':'')+format(data));
        if(repo){const input=document.getElementById('hb-hf-repo');if(input)input.value='';}
      }catch(error){show(`HB control failed: ${String(error.message||error)}`);}
    };
    const bind=(id,action)=>{const button=document.getElementById(id);if(button&&!button.dataset.hfBound){button.dataset.hfBound='1';button.addEventListener('click',()=>{
      if(action==='include'){const repo=document.getElementById('hb-hf-repo')?.value.trim();if(!repo){show('Enter a public Hub repository ID such as Qwen/Qwen3-Coder.');return;}request(action,repo);}
      else request(action);
    });}};
    bind('hb-hf-refresh','status');bind('hb-hf-pause','pause');bind('hb-hf-curate','curate');bind('hb-hf-include','include');bind('hb-hf-resume','resume');
  }

  // ── Auto-grow textarea ───────────────────────────────────────────────────
  function _hcAutoGrow(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, Math.min(window.innerHeight * 0.4, 360)) + 'px';
  }

  // ── Load threads ─────────────────────────────────────────────────────────
  function _hcLoadThreadsListOnly() {
    return fetch('/api/conversations')
      .then(r => {
        if (!r.ok) throw new Error('Cannot load conversation history');
        return r.json();
      })
      .then(data => {
        _hcConversations = Array.isArray(data) ? data : [];
        _hcRenderThreadSelect();
      })
      .catch(err => {
        if (typeof showToast === 'function') showToast(err.message, 'error');
      });
  }

  function _hcLoadThreads() {
    _hcLoadThreadsListOnly();
    if (_hcConvId) {
      _hcLoadMessages(_hcConvId);
      _hcStartLiveSync();
    } else {
      _hcShowWelcome(true);
    }
  }

  function _hcRenderThreadSelect() {
    const sel = document.getElementById('home-chat-thread-select');
    if (!sel) return;
    const current = _hcConvId;
    const threads = [..._hcConversations];
    if (current && !threads.some(c => Number(c.id) === Number(current))) {
      threads.unshift({ id: current, title: 'Saved conversation' });
    }
    const fmtTs = (s) => {
      if (!s) return '';
      try {
        if (/^\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}/.test(s) && !/[Z+]/.test(s.slice(-6))) s = s.replace(' ','T')+'Z';
        const d = new Date(s);
        if (isNaN(d)) return s.slice(0, 10);
        return d.toLocaleDateString('en-AU', { day: '2-digit', month: '2-digit' }) + ' ' +
               d.toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit' });
      } catch (e) { return ''; }
    };
    sel.innerHTML = '<option value="">New conversation</option>' +
      threads.map(c => {
        const title = _hcEsc(String(c.title || '(untitled)')).slice(0, 44);
        const ts = fmtTs(c.timestamp || c.created_at || c.updated_at || '');
        const isSel = Number(c.id) === Number(current) ? ' selected' : '';
        const tsBit = ts ? ' · ' + ts : '';
        return `<option value="${c.id}"${isSel}>#${c.id} · ${title}${tsBit}</option>`;
      }).join('');
    renderChatParticipants();
  }

  // ── Live sync (SSE-driven; mirrors chat tile messages without a timer) ───
  // The backend publishes `chat` SSE events (see frontend/blueprints/sse.py)
  // when a message is committed. We refresh only for the active thread and
  // only on that signal — no 2s polling interval.
  let _hcLiveSyncBound = false;
  function _hcStartLiveSync() {
    if (_hcLiveSyncBound) return;
    _hcLiveSyncBound = true;
    document.addEventListener('hummingbird:chat-sync', e => {
      if (_hcConvId && Number(e.detail.conversation_id) === Number(_hcConvId)) _hcSilentRefresh(_hcConvId);
    });
    document.addEventListener('sse:chat', (e) => {
      const d = (e && e.detail) || {};
      if (_hcApplyPeerProgress(d)) return;
      if (d.owner_command && d.status === 'running' && _hcSending && _hcConvId
          && String(d.conversation_id || '') === String(_hcConvId)) {
        const pending = document.querySelector('#home-chat-messages .hc-bubble[data-pending-job-id^="hc-tmp-"]');
        if (pending) _hcUpsertThinkingBubble({
          job_id: pending.dataset.pendingJobId, agent: 'fridays', status: 'running',
          stage: d.stage || 'Running the owner-pasted HB package command',
        });
        return;
      }
      if (d.status === 'queued' && _hcSending && _hcConvId
          && String(d.conversation_id || '') === String(_hcConvId)) {
        // The backend queues a message sent while APEX is mid-turn; say so instead of looking stuck.
        const pending = document.querySelector('#home-chat-messages .hc-bubble[data-pending-job-id^="hc-tmp-"]');
        if (pending) _hcUpsertThinkingBubble({
          job_id: pending.dataset.pendingJobId, agent: d.agent || 'apex', status: 'running',
          stage: `queued: APEX finishes ${d.position || 1} earlier turn(s) first`,
        });
        return;
      }
      if (!_hcConvId) return;
      if (d.conversation_id && String(d.conversation_id) !== String(_hcConvId)) return;
      if (d.state) _hcSetLaneState(d.state, d.error || '');
      if (['completed', 'failed', 'tool_receipt', 'instructor_requested'].includes(d.status)) _hcSilentRefresh(_hcConvId);
    });
  }

  function _hcApplyPeerProgress(detail) {
    const job = chatPeerProgressJob(detail, _hcConvId);
    if (!job) return false;
    if (['queued', 'running'].includes(job.status)) _hcUpsertThinkingBubble(job);
    else {
      const node = document.querySelector(`#home-chat-messages [data-pending-job-id="${CSS.escape(job.job_id)}"]`);
      if (node) node.remove();
      delete _hcJobHistory[job.job_id];
      _hcSilentRefresh(_hcConvId);
    }
    return true;
  }

  // ── Lane state surface: ok | recovery | offline | error ──────────────────
  // `recovery` = primary storage exception (continuity journal in use).
  // `offline`  = APEX endpoint unreachable / timed out.
  let _hcLaneState = 'ok';
  const _HC_LANE_LABEL = { ok: 'Ready', recovery: 'Recovery', offline: 'Offline', error: 'Error' };
  function _hcSetLaneState(state, detail) {
    const next = String(state || 'ok').toLowerCase();
    _hcLaneState = _HC_LANE_LABEL[next] ? next : 'error';
    const statusEl = document.getElementById('home-chat-status');
    if (statusEl) {
      statusEl.textContent = _HC_LANE_LABEL[_hcLaneState];
      statusEl.dataset.laneState = _hcLaneState;
    }
    const root = document.getElementById('home-chat-input-area');
    if (root) root.dataset.laneState = _hcLaneState;
    return _hcLaneState;
  }

  function _hcApplyLaneResponse(data) {
    const state = _hcSetLaneState(data && data.state, '');
    if (state === 'offline' || state === 'error') {
      _hcAppendBubble({
        sender: 'system',
        message_type: 'system',
        content: (data && data.response) || (state === 'offline' ? 'APEX is offline.' : 'APEX error.'),
        created_at: new Date().toISOString()
      });
      return false;
    }
    return true;
  }

  function _hcSilentRefresh(convId, settled = false) {
    const viewVersion = _hcViewVersion;
    const sendVersion = _hcSendVersion;
    return fetch(`/api/conversations/${convId}/messages?limit=${Math.max(20, document.querySelectorAll('#home-chat-messages .hc-bubble[data-message-id]').length)}`)
      .then(r => {
        if (!r.ok) throw new Error(`Live chat refresh failed (HTTP ${r.status})`);
        return r.json();
      })
      .then(data => {
        if (_hcConvId !== convId || _hcViewVersion !== viewVersion) return;
        const msgs = data.messages || [];
        if (!msgs.length) return;
        const container = document.getElementById('home-chat-messages');
        if (!container) return;
        const atBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 90;
        if (settled && !_hcSending && sendVersion === _hcSendVersion && _hcLaneState === 'ok'
            && !container.querySelector('.hc-bubble[data-pending-job-id]')) {
          const top = container.scrollTop;
          _hcClearMessages();
          msgs.forEach(msg => _hcAppendBubble(msg));
          if (atBottom) _hcScrollBottom();
          else container.scrollTop = top;
          return;
        }
        const persisted = Array.from(container.querySelectorAll('.hc-bubble[data-message-id]'));
        const lastId = Math.max(0, ...persisted.map(el => Number(el.dataset.messageId)));
        const ids = new Set(persisted.map(el => String(el.dataset.messageId)));
        msgs.forEach(msg => {
          if (ids.has(String(msg.id))) return;
          // Adopt only new persisted rows; an older identical message is not this optimistic turn.
          const optimistic = Number(msg.id) > lastId
            ? Array.from(container.querySelectorAll('.hc-bubble:not([data-message-id])'))
              .find(el => !el.dataset.pendingJobId && el._chatMessage
                && el._chatMessage.content === msg.content
                && String(el._chatMessage.sender || el._chatMessage.from_agent).toLowerCase()
                  === String(msg.sender || msg.from_agent).toLowerCase())
            : null;
          const bubble = _hcAppendBubble(msg);
          if (optimistic) optimistic.remove();
          const later = Array.from(container.querySelectorAll('.hc-bubble[data-message-id]'))
            .find(el => Number(el.dataset.messageId) > Number(msg.id));
          if (later) container.insertBefore(bubble, later);
          else {
            const pending = container.querySelector('.hc-bubble[data-pending-job-id]');
            if (pending) container.insertBefore(bubble, pending);
          }
          ids.add(String(msg.id));
        });
        if (atBottom) _hcScrollBottom();
      })
      .catch(error => {
        console.error('Home chat live refresh:', error);
        const status = document.getElementById('home-chat-status');
        if (status) status.textContent = 'Live updates unavailable — reconnecting';
      });
  }

  // ── Switch thread ────────────────────────────────────────────────────────
  function _hcSwitchThread(convId) {
    _hcViewVersion += 1;
    _hcConvId = convId;
    localStorage.setItem(HC_ACTIVE_THREAD_KEY, String(convId));
    _hcRenderThreadSelect();
    _hcLoadMessages(convId);
    _hcRenderAgentPills();
    _hcStartLiveSync();
  }

  function _hcNewThread() {
    _hcViewVersion += 1;
    _hcConvId = null;
    localStorage.removeItem(HC_ACTIVE_THREAD_KEY);
    const sel = document.getElementById('home-chat-thread-select');
    if (sel) sel.value = '';
    _hcClearMessages();
    _hcShowWelcome(true);
    _hcRenderAgentPills();
    _hcUpdateMeta();
    renderChatParticipants();
  }

  // ── Load messages ────────────────────────────────────────────────────────
  function _hcLoadMessages(convId) {
    const viewVersion = _hcViewVersion;
    fetch(`/api/conversations/${convId}/messages?limit=20`)
      .then(r => {
        if (r.status === 404) return null;
        if (!r.ok) throw new Error('Cannot load this conversation');
        return r.json();
      })
      .then(data => {
        if (_hcConvId !== convId || _hcViewVersion !== viewVersion) return;
        if (data === null) {
          // Saved thread was deleted elsewhere — drop the stale marker and start fresh.
          _hcNewThread();
          _hcRenderThreadSelect();
          return;
        }
        if (data.conv && !_hcConversations.some(c => Number(c.id) === Number(convId))) {
          _hcConversations.push(data.conv);
          _hcRenderThreadSelect();
        }
        const msgs = data.messages || [];
        _hcClearMessages();
        if (msgs.length === 0) {
          _hcShowWelcome(true);
          return;
        }
        _hcShowWelcome(false);
        msgs.forEach(m => _hcAppendBubble(m));
        _hcScrollBottom();
      })
      .catch(err => {
        if (typeof showToast === 'function') showToast(err.message, 'error');
      });
  }

  // ── Render bubbles ───────────────────────────────────────────────────────
  function _hcClearMessages() {
    const container = document.getElementById('home-chat-messages');
    if (!container) return;
    // Remove all bubbles but keep welcome
    container.querySelectorAll('.hc-bubble').forEach(b => b.remove());
  }

  function _hcShowWelcome(show) {
    const w = document.querySelector('.home-chat-welcome');
    if (w) w.style.display = show ? 'flex' : 'none';
  }

  // Owner 13 Nov: Fred's (the larger local model's) advice was a system bubble with raw JSON. Read it into plain parts.
  function _hcFredAdvice(msg) {
    const raw = String(msg.content || '');
    const m = raw.match(/^HB local review job (J-[0-9A-F]+) (\w+)\./);
    if (!m || String(msg.sender || msg.from_agent || '').toLowerCase() !== 'hummingbird') return null;
    const line = raw.split('\n')[1] || '';
    let data = {};
    try { data = JSON.parse(line); } catch (_) {
      const pick = key => { const r = line.match(new RegExp('"' + key + '":\\s*"((?:[^"\\\\]|\\\\.)*)')); return r ? r[1].replace(/\\n/g, ' ').replace(/\\"/g, '"') : ''; };
      data = { advice: pick('advice'), reason: pick('reason') };
    }
    return { job: m[1], status: m[2], advice: String(data.advice || data.error || ''), reason: String(data.reason || ''),
             online: data.need_online === true, seconds: Number(data.elapsed_seconds) || 0 };
  }

  function _hcFredBubble(msg, fred, container) {
    const div = document.createElement('div');
    div._chatMessage = msg;
    div.className = 'hc-bubble hc-fred';
    if (msg.id) div.dataset.messageId = msg.id;
    const apex = Array.from(container.querySelectorAll('.hc-bubble.hc-agent')).reverse()
      .find(el => String(el._chatMessage?.sender || el._chatMessage?.from_agent || '').toLowerCase() === 'apex');
    const asked = apex ? String(apex._chatMessage?.content || '').replace(/\s+/g, ' ').trim().slice(0, 90) : '';
    const took = fred.seconds ? ` · ${fred.seconds >= 60 ? Math.round(fred.seconds / 60) + ' min' : Math.round(fred.seconds) + ' s'}` : '';
    div.innerHTML =
      `<div class="hc-fred-link"${apex && apex.dataset.messageId ? ` data-target="${_hcEsc(apex.dataset.messageId)}" title="Show the APEX message this answers"` : ''}>` +
        `↳ Fred advising APEX${asked ? ': <span class="hc-fred-asked">' + _hcEsc(asked) + (asked.length >= 90 ? '…' : '') + '</span>' : ''}</div>` +
      `<div class="hc-fred-body">${fred.status === 'completed' ? _hcRenderContent(fred.advice || 'No advice returned.') : _hcEsc('Fred could not review this: ' + (fred.advice || fred.status))}</div>` +
      (fred.reason ? `<div class="hc-fred-why">Why: ${_hcEsc(fred.reason)}</div>` : '') +
      `<div class="hc-fred-meta">Fred · local 24B on CPU${took}${fred.online ? ' · thinks online help is needed' : ' · no online help needed'} · ${_hcEsc(fred.job)}` +
        (msg.created_at ? ' · ' + _hcFormatTime(msg.created_at) : '') + `</div>`;
    const link = div.querySelector('.hc-fred-link[data-target]');
    if (link) link.addEventListener('click', () => {
      const target = container.querySelector(`.hc-bubble[data-message-id="${CSS.escape(link.dataset.target)}"]`);
      if (!target) return;
      target.scrollIntoView({ behavior: 'smooth', block: 'center' });
      target.classList.add('hc-fred-target');
      setTimeout(() => target.classList.remove('hc-fred-target'), 1600);
    });
    container.appendChild(div);
    return div;
  }

  // Owner 13 Nov: the chat's top line is not needed. Its conversation dropdown and icons move into the task row
  // (in line with New task / Show all tasks); the top line hides once they have moved.
  function _hcMoveBarTools() {
    const bar = document.getElementById('home-chat-input-tasks');
    const top = document.getElementById('home-chat-bar');
    if (!bar || !top) return;
    let tools = bar.querySelector(':scope > .hb-chat-tools');
    if (!tools) { tools = document.createElement('span'); tools.className = 'hb-chat-tools'; bar.appendChild(tools); }
    ['home-chat-env-badge', 'home-chat-thread-select', 'home-chat-new-btn', 'home-chat-expand-btn', 'home-chat-agents-toggle'].forEach(id => {
      const el = document.getElementById(id);
      if (el && el.parentElement !== tools) tools.appendChild(el);
    });
    const newThread = document.getElementById('home-chat-new-btn');
    if (newThread) { newThread.textContent = '+ Thread'; newThread.title = 'Start a new conversation thread'; }
    top.classList.add('hb-moved');
  }

  // Owner 13 Nov: APEX replies were long text rows. Receipt IDs and backend check notes become small tags; a long reply shows
  // its opening and folds the rest (pasted files, long lists) into "Show the rest".
  function _hcApexTidy(raw) {
    let text = String(raw || '');
    const tags = [];
    text = text.replace(/\s*\[Backend ([a-z ]+?) check: ([^\]]{0,600})\]/gi, (_, kind, note) => {
      tags.push({ label: 'Backend ' + kind.trim() + ' check', title: note.trim() }); return ''; });
    text = text.replace(/\s*\(?\b(?:receipt(?: id)?|action id|id):?\s*([0-9a-f]{32})\)?\.?/gi, (_, id) => {
      tags.push({ label: 'receipt ' + id.slice(0, 6), title: id }); return ''; });
    text = text.replace(/\n{3,}/g, '\n\n').trim();
    let head = text, rest = '';
    if (text.length > 700) {
      const cut = text.indexOf('\n\n', 250);
      const at = cut > 0 && cut < 900 ? cut : Math.max(text.lastIndexOf('. ', 600) + 1, 400);
      head = text.slice(0, at).trim(); rest = text.slice(at).trim();
    }
    return { head, rest, tags };
  }

  function _hcAppendBubble(msg) {
    const container = document.getElementById('home-chat-messages');
    if (!container) return;
    if (msg.id) {
      const existing = container.querySelector(`[data-message-id="${CSS.escape(String(msg.id))}"]`);
      if (existing) {
        existing._chatMessage=msg;
        if(msg.task && typeof hbUpdateContinue==='function') {
          if(!existing.querySelector('.hb-bubble-controls[data-hb-task]'))existing.querySelector('.hc-bubble-body')?.insertAdjacentHTML('beforebegin',hbTaskBadge(msg.task,msg.conversation_id || _hcConvId,msg.reply_to_message_id,msg.id));
          hbUpdateContinue(msg.task);
          if(msg.task.acceptance && typeof hbAcceptanceControl==='function') {
            const row=existing.querySelector('.hb-acceptance-controls');
            if(!row)existing.querySelector('.hc-bubble-body')?.insertAdjacentHTML('beforebegin',hbAcceptanceControl(msg.task));
            else if(!row.querySelector('button:disabled') || msg.task.acceptance.state!=='pending')row.innerHTML=hbAcceptanceInner(msg.task.acceptance);
          }
        }
        if(msg.request_control && typeof hbRequestControl==='function') {
          if(!existing.querySelector('.hb-request-controls'))existing.querySelector('.hc-bubble-body')?.insertAdjacentHTML('beforebegin',hbRequestControl(msg.request_control,msg.conversation_id || _hcConvId));
          hbUpdateApproval(msg.request_control);
        }
        return existing;
      }
    } else if (Number.isFinite(msg._afterId)) {
      const existing = Array.from(container.querySelectorAll('.hc-bubble[data-message-id]')).find(el =>
        Number(el.dataset.messageId) > msg._afterId && el._chatMessage?.content === msg.content
        && String(el._chatMessage.sender || el._chatMessage.from_agent).toLowerCase()
          === String(msg.sender || msg.from_agent).toLowerCase());
      if (existing) return existing;
    }
    _hcShowWelcome(false);
    const fred = _hcFredAdvice(msg);
    if (fred) return _hcFredBubble(msg, fred, container);

    const sender = (msg.sender || msg.from_agent || '').toLowerCase();
    const isUser = sender === 'user' || sender === 'you' || msg.message_type === 'user';
    const isSystem = msg.message_type === 'system';
    const type = isUser ? 'hc-user' : isSystem ? 'hc-system' : 'hc-agent';
    const agentLabel = isUser ? 'You' : _hcAgentDisplayName(sender);

    const time = msg.created_at ? _hcFormatTime(msg.created_at) : '';
    let content = !isUser && typeof renderHummingbirdChatBody === 'function'
      ? renderHummingbirdChatBody(msg.content || '', msg.message_type, _hcRenderContent)
      : _hcRenderContent(msg.content || '');
    if (sender === 'hummingbird' && !/^\s*[\[{]/.test(String(msg.content || ''))) {
      // Owner 13 Nov: HB's messages read plainly; ids, checks and commands sit folded under Details.
      const raw = String(msg.content || '');
      const at = raw.indexOf('\nDetails: ');
      if (at > 0) content = _hcRenderContent(raw.slice(0, at)) +
        `<details class="hc-hb-details"><summary>Details</summary><div>${_hcEsc(raw.slice(at + 10))}</div></details>`;
    }
    if (sender === 'apex' && !isSystem && !/^\s*[\[{]/.test(String(msg.content || ''))) {
      const tidy = _hcApexTidy(msg.content);
      const restLines = tidy.rest ? tidy.rest.split('\n').length : 0;
      content = `<div class="hc-apex-lead">${_hcRenderContent(tidy.head)}</div>` +
        (tidy.rest ? `<details class="hc-apex-rest"><summary>Show the rest (${restLines} line${restLines === 1 ? '' : 's'})</summary>${_hcRenderContent(tidy.rest)}</details>` : '') +
        (tidy.tags.length ? `<div class="hc-apex-tags">${tidy.tags.map(t => `<span class="hc-apex-tag" title="${_hcEsc(t.title)}">${_hcEsc(t.label)}</span>`).join('')}</div>` : '');
    }
    const rawText = _hcEsc(String(msg.content || '').trim().slice(0, 4000));
    const msgId = msg.id || '';
    const convId = msg.conversation_id || _hcConvId || '';
    const hasIds = msgId && convId;

    const captureBtn = `<button class="hc-action-btn hc-capture-btn" data-conv="${_hcEsc(String(convId))}" data-msg="${_hcEsc(String(msgId))}" data-text="${rawText}" onclick="hcCaptureWork(this)">Capture</button>`;

    // Action buttons for user messages
    let actionHtml = '';
    if (isUser) {
      actionHtml = `<div class="hc-actions">` +
        captureBtn +
        `<button class="hc-action-btn" data-text="${rawText}" onclick="hcResend(this.dataset.text)">Resend</button>` +
        (hasIds
          ? `<button class="hc-action-btn" data-conv="${Number(convId)}" data-msg="${Number(msgId)}" onclick="hcEditInline(this)">Change</button>` +
            `<button class="hc-action-btn" data-conv="${Number(convId)}" data-msg="${Number(msgId)}" onclick="hcDelete(${Number(convId)}, ${Number(msgId)})">Delete</button>`
          : `<button class="hc-action-btn" data-text="${rawText}" onclick="hcRevise(this.dataset.text)">Change Text</button>`) +
        `</div>`;
    } else if (!isSystem && hasIds) {
      actionHtml = `<div class="hc-actions">` +
        captureBtn +
        `<button class="hc-action-btn" data-conv="${Number(convId)}" data-msg="${Number(msgId)}" onclick="hcDelete(${Number(convId)}, ${Number(msgId)})">Delete</button>` +
        `</div>`;
    } else if (!isSystem) {
      actionHtml = `<div class="hc-actions">${captureBtn}</div>`;
    }

    const div = document.createElement('div');
    div._chatMessage = msg;
    div.className = `hc-bubble ${type}`;
    if (hasIds) div.dataset.messageId = msgId;
    if (msg._placeholderId) div.dataset.ph = msg._placeholderId;
    div.innerHTML =
      `<div class="hc-bubble-header">` +
        `<span class="hc-bubble-sender">${_hcEsc(agentLabel)}</span>` +
        (time ? `<span class="hc-bubble-time">${time}</span>` : '') +
      `</div>` +
      (typeof hbTaskBadge==='function' ? hbTaskBadge(msg.task,convId,msg.reply_to_message_id,msg.id) : '') +
      (typeof hbRequestControl==='function' ? hbRequestControl(msg.request_control,convId) : '') +
      (!isUser && String(sender).toLowerCase()!=='hummingbird' && typeof hbUsageLabel==='function' ? `<span class="hb-usage">${_hcEsc(hbUsageLabel(msg.usage,msg.tokens_used))}</span>` : '') +
      `<div class="hc-bubble-body">${content}</div>` +
      (String(sender).toLowerCase()==='hummingbird' && typeof hbCommandButtons==='function' ? hbCommandButtons(msg.content) : '') +
      actionHtml;

    if(msg.task)div.dataset.hbTaskId=msg.task.task_id;
    if(typeof hbTaskBar==='function'){hbTaskBar('home-chat-input',convId);_hcMoveBarTools();}
    container.appendChild(div);
    return div;
  }

  // ── Home-chat action handlers (global) ─────────────────────────────────
  window.hcResend = function (text) {
    const input = document.getElementById('home-chat-input');
    if (!input) return;
    input.value = String(text || '').trim();
    input.focus();
    _hcSend();
  };

  window.hcRevise = function (text) {
    const input = document.getElementById('home-chat-input');
    if (!input) return;
    input.value = String(text || '').trim();
    input.focus();
    if (typeof showToast === 'function') showToast('Prompt loaded — edit and send again.', 'info');
  };

  window.hcEditInline = function (btn) {
    const convId = Number(btn.dataset.conv);
    const msgId = Number(btn.dataset.msg);
    const bubble = btn.closest('.hc-bubble');
    if (!bubble) return;
    const body = bubble.querySelector('.hc-bubble-body');
    if (!body || body.querySelector('.hc-inline-edit')) return;

    const currentText = body.textContent || '';
    body.innerHTML = '';
    const ta = document.createElement('textarea');
    ta.className = 'hc-inline-edit';
    ta.value = currentText;
    ta.rows = Math.min(6, Math.max(2, currentText.split('\n').length));
    body.appendChild(ta);

    const bar = document.createElement('div');
    bar.className = 'hc-inline-edit-bar';
    bar.innerHTML = '<button class="hc-action-btn hc-save-btn">Save</button><button class="hc-action-btn hc-cancel-btn">Cancel</button>';
    body.appendChild(bar);
    ta.focus();

    const cancel = () => {
      body.innerHTML = _hcRenderContent(currentText);
    };
    const save = async () => {
      const newText = ta.value.trim();
      if (!newText) { if (typeof showToast === 'function') showToast('Cannot be empty', 'error'); return; }
      if (newText === currentText.trim()) { cancel(); return; }
      try {
        const r = await fetch(`/api/conversations/${convId}/messages/${msgId}`, {
          method: 'PATCH', headers: {'Content-Type':'application/json'},
          body: JSON.stringify({ content: newText })
        });
        const d = await r.json().catch(() => ({}));
        if (!r.ok || !d.ok) throw new Error(d.error || `HTTP ${r.status}`);
        if (typeof showToast === 'function') showToast('Updated', 'success');
        _hcLoadMessages(convId);
      } catch (e) {
        if (typeof showToast === 'function') showToast('Update failed: ' + (e.message || e), 'error');
      }
    };
    bar.querySelector('.hc-save-btn').addEventListener('click', save);
    bar.querySelector('.hc-cancel-btn').addEventListener('click', cancel);
    ta.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') cancel();
      if (e.key === 'Enter' && e.ctrlKey) save();
    });
  };

  window.hcDelete = async function (convId, msgId) {
    try {
      const r = await fetch(`/api/conversations/${convId}/messages/${msgId}`, { method: 'DELETE' });
      const d = await r.json().catch(() => ({}));
      if (!r.ok || !d.ok) throw new Error(d.error || `HTTP ${r.status}`);
      if (typeof showToast === 'function') showToast('Deleted', 'success');
      _hcLoadMessages(convId);
    } catch (e) {
      if (typeof showToast === 'function') showToast('Delete failed: ' + (e.message || e), 'error');
    }
  };

  function _hcLatestCaptureCandidate() {
    const input = document.getElementById('home-chat-input');
    const typed = String((input && input.value) || '').trim();
    if (typed) {
      return {
        text: typed,
        conversation_id: _hcConvId || '',
        message_id: ''
      };
    }
    const bubbles = Array.from(document.querySelectorAll('#home-chat-messages .hc-bubble'))
      .filter(b => !b.classList.contains('hc-system'));
    const last = bubbles.length ? bubbles[bubbles.length - 1] : null;
    if (!last) return { text: '', conversation_id: _hcConvId || '', message_id: '' };
    const body = last.querySelector('.hc-bubble-body');
    return {
      text: String((body && body.textContent) || '').trim(),
      conversation_id: _hcConvId || '',
      message_id: last.dataset.messageId || ''
    };
  }

  window.hcCaptureWork = async function (btn) {
    const fromButton = btn && btn.dataset && btn.dataset.text
      ? {
          text: String(btn.dataset.text || '').trim(),
          conversation_id: btn.dataset.conv || _hcConvId || '',
          message_id: btn.dataset.msg || ''
        }
      : _hcLatestCaptureCandidate();
    const text = fromButton.text;
    if (!text) {
      if (typeof showToast === 'function') showToast('Type something or wait for a chat reply to capture.', 'error');
      return;
    }
    const firstLine = text.split(/\r?\n/).find(Boolean) || 'Captured chat work';
    const suggested = firstLine.length > 90 ? firstLine.slice(0, 87) + '...' : firstLine;
    const title = prompt('Capture as Studio task:', suggested);
    if (title === null) return;
    const cleanTitle = String(title || '').trim() || suggested;
    btn.disabled = true;
    btn.textContent = 'Capturing';
    try {
      const payload = {
        title: cleanTitle,
        content: text,
        conversation_id: fromButton.conversation_id,
        message_id: fromButton.message_id
      };
      const r = await fetch('/api/knowledge/chat-capture', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok || !d.ok) throw new Error(d.error || `HTTP ${r.status}`);
      if (typeof showToast === 'function') {
        showToast(`Captured to ${d.project_name || d.project_id}: ${d.step_id}`, 'success');
      }
	      if (typeof window.dispatchEvent === 'function') {
	        window.dispatchEvent(new CustomEvent('fridays:studio-step-captured', { detail: d }));
	      }
	      _hcLoadProofTrail();
	    } catch (e) {
      if (typeof showToast === 'function') showToast('Capture failed: ' + (e.message || e), 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Capture';
    }
	  };

	  function _hcProofSummary(data) {
	    const counts = data && data.counts ? data.counts : {};
	    const docs = Number(counts.project_docs || 0);
	    const steps = Number(counts.project_steps || 0);
	    const evidence = Number(counts.project_step_evidence || 0);
	    return `${evidence} evidence rows · ${steps} steps · ${docs} KC docs`;
	  }

	  function _hcProofItem(row) {
	    const kind = String(row.source_type || row.title || 'evidence');
	    const status = String(row.status || 'ok');
	    const text = String(row.summary || row.step_title || row.source_ref || 'Evidence row').trim();
	    const ref = [row.project_id, row.step_id, row.source_ref].filter(Boolean).join(' · ');
	    const statusClass = status.toLowerCase().replace(/[^a-z0-9_-]/g, '');
	    return `<div class="proof-trail-item" title="${_hcEsc(text)}">` +
	      `<div class="proof-trail-item-top">` +
	        `<span class="proof-trail-kind">${_hcEsc(kind)}</span>` +
	        `<span class="proof-trail-status ${_hcEsc(statusClass)}">${_hcEsc(status)}</span>` +
	      `</div>` +
	      `<div class="proof-trail-text">${_hcEsc(text)}</div>` +
	      `<div class="proof-trail-ref">${_hcEsc(ref)}</div>` +
	    `</div>`;
	  }

	  function _hcLoadProofTrail() {
	    const itemsEl = document.getElementById('home-proof-trail-items');
	    const summaryEl = document.getElementById('home-proof-trail-summary');
	    if (!itemsEl || !summaryEl) return;
	    fetch('/api/knowledge/evidence')
	      .then(r => r.json())
	      .then(data => {
	        if (!data || !data.ok) throw new Error((data && data.error) || 'Evidence unavailable');
	        const rows = (((data.latest || {}).project_step_evidence) || []).slice(0, 3);
	        summaryEl.textContent = _hcProofSummary(data);
	        itemsEl.innerHTML = rows.length
	          ? rows.map(_hcProofItem).join('')
	          : '<div class="proof-trail-empty">No step evidence has been written yet.</div>';
	      })
	      .catch(err => {
	        summaryEl.textContent = 'Evidence unavailable';
	        itemsEl.innerHTML = `<div class="proof-trail-empty">Proof trail failed: ${_hcEsc(String(err.message || err))}</div>`;
	      });
	  }

	  window.homeLoadProofTrail = _hcLoadProofTrail;

	  function _hcAgentDisplayName(name) {
    if (name === 'apex' || name === 'codex-instructor' || name === 'copilot-instructor' || name === 'gemini-advisor' || name === 'claude-code' || name === 'peer-bridge') {
      return _chatAgentLabel(name);
    }
    const agents = _hcAgentOptions();
    const match = agents.find(a => a.value === name || a.label?.toLowerCase() === name);
    return match ? match.label : (name.charAt(0).toUpperCase() + name.slice(1));
  }

  function _hcRenderContent(text) {
    if (typeof window !== 'undefined' && typeof window.agentEnvelopeToMarkdown === 'function') {
      text = window.agentEnvelopeToMarkdown(text);
    }
    // Use shared safeMarkdown (marked + DOMPurify) when available to prevent XSS.
    if (typeof window !== 'undefined' && typeof window.safeMarkdown === 'function') {
      return window.safeMarkdown(text);
    }
    if (typeof marked !== 'undefined' && marked.parse) {
      try { return marked.parse(String(text || ''), { gfm: true, breaks: false }); } catch (e) { /* fall through */ }
    }
    return _hcEsc(text).replace(/\n/g, '<br>');
  }

  function _hcFormatTime(ts) {
    try {
      // DB timestamps are UTC but lack 'Z' suffix — normalise so Date parses as UTC
      let s = String(ts || '');
      if (/^\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}/.test(s) && !/[Z+]/.test(s.slice(-6))) s = s.replace(' ', 'T') + 'Z';
      const d = new Date(s);
      if (isNaN(d)) return '';
      return d.toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit' });
    } catch (e) {
      return '';
    }
  }

  function _hcScrollBottom() {
    const container = document.getElementById('home-chat-messages');
    if (container) {
      requestAnimationFrame(() => {
        container.scrollTop = container.scrollHeight;
      });
    }
  }

  // ── Follow-up #2: prune stale per-thread agent toggles ──────────────────
  // HC_AGENT_TOGGLE_PREFIX keys grow unbounded. Every 24 h we look up the
  // current conversation list and delete any toggle whose conv id is no
  // longer present. Runs at most once a day (stamped in localStorage).
  function _hcPruneStaleAgentToggles() {
    try {
      const STAMP_KEY = 'fridays-chat-toggle-prune-stamp';
      const last = Number(localStorage.getItem(STAMP_KEY) || 0);
      if (Date.now() - last < 86400 * 1000) return;
      fetch('/api/conversations').then(r => r.json()).then(list => {
        const known = new Set((Array.isArray(list) ? list : []).map(c => String(c.id)));
        const toDelete = [];
        for (let i = 0; i < localStorage.length; i++) {
          const k = localStorage.key(i);
          if (!k || !k.startsWith(HC_AGENT_TOGGLE_PREFIX)) continue;
          const convId = k.slice(HC_AGENT_TOGGLE_PREFIX.length);
          if (!known.has(convId)) toDelete.push(k);
        }
        toDelete.forEach(k => { try { localStorage.removeItem(k); } catch (_) {} });
        try { localStorage.setItem(STAMP_KEY, String(Date.now())); } catch (_) {}
      }).catch(() => {});
    } catch (_) { /* non-fatal */ }
  }

  // ── Agent pills ──────────────────────────────────────────────────────────
  // P4-M29: persist user's drag-drop ordering of pills
  const HC_PILL_ORDER_KEY = 'fridays-chat-pill-order';
  function _hcGetPillOrder() {
    try { return JSON.parse(localStorage.getItem(HC_PILL_ORDER_KEY) || '[]'); }
    catch (_) { return []; }
  }
  function _hcSavePillOrder(order) {
    try { localStorage.setItem(HC_PILL_ORDER_KEY, JSON.stringify(order)); } catch (_) {}
  }
  function _hcAgentNumberFor(name) {
    // Pull number from agents-config registry if present
    try {
      const reg = (window.__agentsData || []);
      const a = reg.find(x => x.name === name || x.label === name);
      if (a && Number.isFinite(Number(a.number))) return Number(a.number);
    } catch (_) {}
    return null;
  }
  function _hcRenderAgentPills() {
    const host = document.getElementById('home-chat-agents');
    if (!host) return;
    let agents = _hcAgentOptions();
    if (agents.length === 0) {
      // Retry once after agent registry loads
      setTimeout(() => {
        const a2 = _hcAgentOptions();
        if (a2.length > 0) _hcRenderAgentPills();
      }, 1500);
      return;
    }

    // Apply persisted drag-drop order: any agent listed in saved order comes first,
    // in that order. Anything new (not yet in saved order) appears at the end.
    const savedOrder = _hcGetPillOrder();
    if (savedOrder.length) {
      const idx = new Map(savedOrder.map((v, i) => [v, i]));
      agents = [...agents].sort((a, b) => {
        const ai = idx.has(a.value) ? idx.get(a.value) : 999;
        const bi = idx.has(b.value) ? idx.get(b.value) : 999;
        return ai - bi;
      });
    }

    const enabled = _hcGetEnabledAgents();
    host.innerHTML = agents.map(a => {
      const active = enabled.includes(a.value) ? ' active' : '';
      const tierClass = (a.tier === 'paid' || a.tier === 'online') ? 'paid' : 'local';
      const num = _hcAgentNumberFor(a.value);
      const numBadge = (num !== null)
        ? `<span class="agent-num-badge" style="font-size:9px;font-weight:700;background:rgba(0,0,0,0.35);color:#fff;border-radius:8px;padding:1px 5px;margin-right:4px;">${num}</span>`
        : '';
      return `<button class="home-chat-agent-pill${active}" draggable="true" data-agent="${_hcEsc(a.value)}" title="${_hcEsc(a.label)}">` +
        `${numBadge}<span class="agent-dot ${tierClass}"></span>${_hcEsc(a.label)}` +
        `<small role="status" data-agent-load-status="${_hcEsc(a.value)}" style="display:block;font-size:10px;white-space:normal;">${_hcEsc(window.agentLoadState(a.value)?.text || '')}</small></button>`;
    }).join('');

    host.querySelectorAll('.home-chat-agent-pill').forEach(btn => {
      btn.addEventListener('click', () => {
        const wasAuto = localStorage.getItem(HC_MANUAL_KEY) !== '1';
        if (wasAuto) {
          host.querySelectorAll('.home-chat-agent-pill').forEach(p => p.classList.remove('active'));
          btn.classList.add('active');
          const manual = document.getElementById('home-chat-manual-override');
          if (manual) manual.checked = true;
          localStorage.setItem(HC_MANUAL_KEY, '1');
          window.onHomeChatManualOverrideToggle();
        } else {
          btn.classList.toggle('active');
        }
        _hcSaveEnabledAgents();
        _hcUpdateMeta();
        if (btn.classList.contains('active')) window.warmChatAgent(btn.dataset.agent);
      });
      // P4-M29: HTML5 drag-and-drop reorder
      btn.addEventListener('dragstart', e => {
        e.dataTransfer.setData('text/plain', btn.dataset.agent);
        e.dataTransfer.effectAllowed = 'move';
        btn.style.opacity = '0.5';
      });
      btn.addEventListener('dragend', () => { btn.style.opacity = ''; });
      btn.addEventListener('dragover', e => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        btn.style.outline = '2px dashed var(--accent)';
      });
      btn.addEventListener('dragleave', () => { btn.style.outline = ''; });
      btn.addEventListener('drop', e => {
        e.preventDefault();
        btn.style.outline = '';
        const src = e.dataTransfer.getData('text/plain');
        const dst = btn.dataset.agent;
        if (!src || src === dst) return;
        const all = Array.from(host.querySelectorAll('.home-chat-agent-pill')).map(p => p.dataset.agent);
        const from = all.indexOf(src);
        const to = all.indexOf(dst);
        if (from < 0 || to < 0) return;
        all.splice(from, 1);
        all.splice(to, 0, src);
        _hcSavePillOrder(all);
        _hcRenderAgentPills();
      });
    });
    _hcUpdateMeta();
  }

  function _hcGetEnabledAgents() {
    // Per-thread agents first, then global fallback
    if (_hcConvId) {
      const perThread = localStorage.getItem(HC_AGENT_TOGGLE_PREFIX + _hcConvId);
      if (perThread) {
        try { return JSON.parse(perThread); } catch (e) { /* fall through */ }
      }
    }
    const agents = _hcAgentOptions();
    if (!_hcConvId) {
      const hasSeven = agents.some(a => a && a.value === 'seven');
      if (hasSeven) return ['seven'];
    }
    const global = localStorage.getItem(HC_GLOBAL_AGENTS_KEY);
    if (global) {
      try { return JSON.parse(global); } catch (e) { /* fall through */ }
    }
    // Default: first local agent
    return agents.length > 0 ? [agents[0].value] : [];
  }

  function _hcSaveEnabledAgents() {
    const pills = document.querySelectorAll('#home-chat-agents .home-chat-agent-pill.active');
    const enabled = Array.from(pills).map(p => p.dataset.agent);
    // Save both per-thread and global
    if (_hcConvId) {
      localStorage.setItem(HC_AGENT_TOGGLE_PREFIX + _hcConvId, JSON.stringify(enabled));
    }
    localStorage.setItem(HC_GLOBAL_AGENTS_KEY, JSON.stringify(enabled));
    // Sync floating chat agent state
    if (typeof renderChatAgentToggles === 'function') {
      try { renderChatAgentToggles(); } catch (e) { /* ignore */ }
    }
  }

  function _hcUpdateMeta() {
    const countEl = document.getElementById('home-chat-agent-count');
    if (countEl) {
      countEl.textContent = `To: ${chatRecipientSummary(document.getElementById('home-chat-input')?.value, _chatAgentLabel)}`;
    }
  }

  // Live token counter under the chat input. Estimate = chars/4 (Qwen/Llama).
  function _hcUpdateTokenCount(input) {
    const el = document.getElementById('home-chat-token-count');
    if (!el) return;
    const text = (input && input.value) || '';
    const chars = text.length;
    const words = text.trim() ? text.trim().split(/\s+/).length : 0;
    const est = Math.ceil(chars / 4);
    el.textContent = `${chars} c · ${words} w · ~${est} t`;
  }

  // ── Seven Ask helper — leading "?" in chat short-circuits to /api/seven.
  function _hcAskSeven(query) {
    const trimmed = (query || '').trim();
    let intent = 'status';
    if (/\b(next|todo|what.*should|do.*now|start)\b/i.test(trimmed)) intent = 'next';
    else if (/\b(remember|recall|remind|told)\b/i.test(trimmed))     intent = 'remember';
    else if (/\b(status|state|how.*going|vital|pulse)\b/i.test(trimmed)) intent = 'status';
    // Detect a record id token to set focus.
    let focus = null;
    const tokens = trimmed.split(/\s+/);
    for (const tok of tokens) {
      if (/^(B|S|P|PR|T|TC|TR|D|TH)-[0-9A-F]{4,}$/i.test(tok)) {
        focus = tok.toUpperCase();
        break;
      }
    }
    const explainQs = focus ? '?focus=' + encodeURIComponent(focus) : '';
    const decideQs = focus
      ? '?intent=' + encodeURIComponent(intent) + '&focus=' + encodeURIComponent(focus)
      : '?intent=' + encodeURIComponent(intent);
    // Thinking placeholder.
    const placeholderId = 'seven-think-' + Date.now();
    _hcAppendBubble({
      sender: 'seven', message_type: 'agent', agent: 'seven',
      content: '_thinking…_', created_at: new Date().toISOString(),
      _placeholderId: placeholderId
    });
    _hcScrollBottom();

    Promise.all([
      fetch('/api/seven/explain' + explainQs).then(r => r.json()).catch(() => ({})),
      fetch('/api/seven/decide' + decideQs).then(r => r.json()).catch(() => ({})),
    ]).then(([explainData, decideData]) => {
      const lines = (explainData && explainData.lines) || [];
      const proposals = (decideData && decideData.proposals) || [];
      const partsBody = [];
      if (lines.length) partsBody.push(lines.join('\n\n'));
      if (proposals.length) {
        partsBody.push('\n**Suggestions** _(propose-only)_');
        proposals.slice(0, 3).forEach((p) => {
          const t = p.target || null;
          const tgt = t ? ` · \`${t.kind}:${t.id}\`` : '';
          const conf = (typeof p.confidence === 'number')
            ? ` · ${(p.confidence * 100) | 0}%` : '';
          partsBody.push(`- **[${(p.action || 'review').toUpperCase()}]** ${p.label || ''}${tgt}${conf}\n  _${p.rationale || ''}_`);
        });
      }
      if (decideData && decideData.refused) {
        partsBody.push('\n_' + (decideData.refused_reason || 'propose-only') + '_');
      }
      const bodyText = partsBody.join('\n') ||
        '_Seven has nothing to add yet — try `?status`, `?next`, or include a record id like `?S-7D7677C6E2`._';
      // Replace placeholder with real bubble.
      const msgs = document.getElementById('home-chat-messages');
      if (msgs) {
        const ph = msgs.querySelector('[data-ph="' + placeholderId + '"]');
        if (ph) ph.remove();
      }
      _hcAppendBubble({
        sender: 'seven', message_type: 'agent', agent: 'seven',
        content: bodyText, created_at: new Date().toISOString(),
        meta: { intent: intent, focus: focus, authority: 'propose-only' }
      });
      _hcScrollBottom();
    });
  }

  // ── Send message ─────────────────────────────────────────────────────────
  function _hcSend() {
    if (_hcSending) return;
    const input = document.getElementById('home-chat-input');
    const sendBtn = document.getElementById('home-chat-send-btn');
    if (!input) return;
    const text = input.value.trim();
    if (!text) return;
    const viewVersion = _hcViewVersion;

    // Seven Ask short-circuit — leading "?" routes to /api/seven/explain +
    // /decide, renders a Seven assistant bubble inline, no agent fan-out.
    if (text.charAt(0) === '?') {
      // User bubble first.
      _hcAppendBubble({
        sender: 'user', message_type: 'user',
        content: text, created_at: new Date().toISOString()
      });
      _hcScrollBottom();
      input.value = '';
      input.style.height = 'auto';
      _hcUpdateTokenCount(input);
      _hcAskSeven(text.replace(/^\?+\s*/, ''));
      return;
    }

    const enabled = getChatDispatchAgents(text);
    if (!enabled.length) {
      if (typeof showToast === 'function') showToast('No local agent is available. Check the local runtime in Agents.', 'error');
      return;
    }
    const sendAfterId = Math.max(0, ...Array.from(
      document.querySelectorAll('#home-chat-messages .hc-bubble[data-message-id]'),
      el => Number(el.dataset.messageId)));
    _hcSendVersion += 1;

    // Show user bubble immediately
    _hcAppendBubble({
      sender: 'user',
      message_type: 'user',
      content: text,
      created_at: new Date().toISOString()
    });
    _hcScrollBottom();

    // Workstream J / Phase 4 — shared action pill pipeline. Same Siri-style
    // detection as main chat; compact layout for the tile. Fires in parallel
    // with the /api/chat send below.
    try {
      var _hcMsgEl = document.getElementById('home-chat-messages');
      if (_hcMsgEl && window.SwarmChat && typeof window.SwarmChat.maybeShowActionPill === 'function') {
        window.SwarmChat.maybeShowActionPill(_hcMsgEl, text, { compact: true });
      }
    } catch (_) { /* non-fatal */ }

    input.value = '';
    input.style.height = 'auto';
    _hcUpdateTokenCount(input);
    _hcSending = true;
    if (sendBtn) sendBtn.classList.add('sending');
    sendBtn && (sendBtn.disabled = true);

    const statusEl = document.getElementById('home-chat-status');
    if (statusEl) statusEl.textContent = 'Sending…';

    // Show a thinking bubble immediately — removed/replaced when real response arrives
    const _hcTempJobId = 'hc-tmp-' + Date.now();
    _hcUpsertThinkingBubble({ job_id: _hcTempJobId, agent: enabled[0] || 'agent', stage: 'thinking', status: 'running' });
    _hcScrollBottom();

    const body = {
      message: text,
      agents: enabled,
      local_only: true,
      conversation_id: _hcConvId || null,
      task_id:typeof hbTaskSelection==='function' ? hbTaskSelection(_hcConvId) : null,
      new_thread: !_hcConvId,
      history_mode: 'recent',
      history_limit: 12,
      auto_relay: false
    };

    fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })
      .then(r => r.json())
      .then(data => {
        if (viewVersion !== _hcViewVersion) return;
        // Only the explicit Continue button/picker selects a task for later messages.
        if (data.conversation_id && String(data.conversation_id) !== String(_hcConvId)) {
          _hcConvId = data.conversation_id;
          localStorage.setItem(HC_ACTIVE_THREAD_KEY, String(_hcConvId));
          _hcSaveEnabledAgents();
          // Refresh thread dropdown only — must NOT reset _hcConvId or wipe
          // messages here (Y.58 fix for the "Hi disappears" race).
          _hcLoadThreadsListOnly();
          _hcStartLiveSync();
          // Session 28: notify other chat surfaces.
          try {
            window.dispatchEvent(new CustomEvent('swarm:conversation-changed', {
              detail: { type: 'created', conversation_id: _hcConvId, source: 'home-chat' }
            }));
          } catch (_) { /* non-fatal */ }
        }

        // Split responses into done-now vs pending-acknowledgement
        const allResponses = Array.isArray(data.responses) ? data.responses : [];
        const immediate    = allResponses.filter(r => !r.pending);
        const pendingAcks  = allResponses.filter(r =>  r.pending && r.job_id);
        // Backend returns pending_jobs as array of job id strings.
        const pendingJobIds = Array.isArray(data.pending_jobs) ? data.pending_jobs.filter(Boolean) : [];

        // If first pending ack exists, reuse the placeholder bubble for its job_id
        // instead of removing-then-recreating (prevents the "thinking bubble flashes and dies").
        const _hcTmpBubble = document.getElementById('home-chat-messages')?.querySelector(`.hc-bubble[data-pending-job-id="${CSS.escape(_hcTempJobId)}"]`);
        if (pendingAcks.length && _hcTmpBubble) {
          const firstAck = pendingAcks[0];
          _hcTmpBubble.dataset.pendingJobId = String(firstAck.job_id);
          _hcJobHistory[firstAck.job_id] = _hcJobHistory[_hcTempJobId] || [];
        } else if (_hcTmpBubble) {
          _hcTmpBubble.remove();
        }
        delete _hcJobHistory[_hcTempJobId];

        // Lane state from the backend: Offline/Error short-circuit into a system bubble.
        if (!_hcApplyLaneResponse(data)) {
          _hcScrollBottom();
          return;
        }

        // Render completed (non-pending) agent responses
        (Array.isArray(data.tool_receipts) ? data.tool_receipts : []).forEach(receipt => {
          _hcAppendBubble({
            _afterId: sendAfterId,
            sender: 'apex', message_type: 'tool_result',
            content: `[tool:${receipt.tool}] ${receipt.status} (receipt ${receipt.id})\n` +
              JSON.stringify(receipt.arguments) + '\n' + receipt.output +
              (receipt.truncated ? '\n[output truncated]' : ''),
            created_at: new Date().toISOString()
          });
        });
        if (immediate.length > 0) {
          immediate.forEach(resp => {
            _hcAppendBubble({
              _afterId: sendAfterId,
              task:resp.task||data.task,usage:resp.usage,tokens_used:resp.tokens,conversation_id:data.conversation_id,
              sender: resp.agent || 'agent',
              message_type: 'agent',
              content: resp.response || resp.text || '(empty response)',
              created_at: new Date().toISOString()
            });
          });
        } else if (!pendingAcks.length && !pendingJobIds.length && data.response) {
          _hcAppendBubble({
            _afterId: sendAfterId,
            sender: data.agent || 'agent',
            message_type: 'agent',
            content: data.response,
            created_at: new Date().toISOString()
          });
        } else if (!pendingAcks.length && !pendingJobIds.length) {
          // Y.58 safety net: backend returned no responses, no pending jobs,
          // and no top-level response. Surface SOMETHING instead of leaving the
          // user staring at a blank chat (\"Hi disappears\" symptom).
          _hcAppendBubble({
            sender: 'system',
            message_type: 'system',
            content: data.error || data.response_error || 'No response from agent. Try again or pick a different agent.',
            created_at: new Date().toISOString()
          });
        }

        // Spawn / upsert thinking bubbles from the ack records (carries real job_id + agent)
        pendingAcks.forEach(ack => {
          _hcUpsertThinkingBubble({
            job_id: ack.job_id,
            agent: ack.agent,
            stage: 'queued',
            status: 'running',
          });
        });

        (Array.isArray(data.peer_statuses) ? data.peer_statuses : []).forEach(_hcApplyPeerProgress);

        if (pendingJobIds.length) {
          _hcPollJobs(pendingJobIds);
        }

        _hcScrollBottom();
      })
      .catch(err => {
        if (viewVersion !== _hcViewVersion) return;
        // Remove pre-send placeholder thinking bubble on error
        const _hcTmpBubbleErr = document.getElementById('home-chat-messages')?.querySelector(`.hc-bubble[data-pending-job-id="${CSS.escape(_hcTempJobId)}"]`);
        if (_hcTmpBubbleErr) _hcTmpBubbleErr.remove();
        delete _hcJobHistory[_hcTempJobId];

        // A transport failure between the browser and the backend is Offline.
        _hcSetLaneState('offline', err && err.message);
        _hcAppendBubble({
          sender: 'system',
          message_type: 'system',
          content: `Offline: ${err.message || 'Send failed'}`,
          created_at: new Date().toISOString()
        });
        _hcScrollBottom();
      })
      .finally(() => {
        _hcSending = false;
        if (sendBtn) {
          sendBtn.classList.remove('sending');
          sendBtn.disabled = false;
        }
        // Keep Offline/Recovery visible; only a healthy lane reads "Ready".
        if (statusEl && _hcLaneState === 'ok') statusEl.textContent = 'Ready';
        if (viewVersion === _hcViewVersion && _hcConvId) _hcSilentRefresh(_hcConvId, true);
      });
  }

  // ── Stage history per job ────────────────────────────────────────────────
  const _hcJobHistory = {};

  // ── Verbose thinking bubble (matches chat tile behaviour) ─────────────────
  function _hcUpsertThinkingBubble(job) {
    const container = document.getElementById('home-chat-messages');
    if (!container || !job || !job.job_id) return;
    _hcShowWelcome(false);

    const stage = String(job.stage || '').trim();
    if (!_hcJobHistory[job.job_id]) _hcJobHistory[job.job_id] = [];
    if (stage) {
      const hist = _hcJobHistory[job.job_id];
      if (!hist.length || hist[hist.length - 1] !== stage) {
        hist.push(stage);
        _hcJobHistory[job.job_id] = hist.slice(-16);
      }
    }

    let bubble = container.querySelector(`.hc-bubble[data-pending-job-id="${CSS.escape(String(job.job_id))}"]`);
    if (!bubble) {
      bubble = document.createElement('div');
      bubble.className = 'hc-bubble hc-agent hc-pending';
      bubble.dataset.pendingJobId = String(job.job_id);
      bubble.innerHTML =
        `<div class="hc-bubble-header">` +
          `<span class="hc-bubble-sender">${_hcEsc(_hcAgentDisplayName(String(job.agent || 'agent')))}</span>` +
        `</div>` +
        `<div class="hc-bubble-body"></div>`;
      container.appendChild(bubble);
    }

    const body = bubble.querySelector('.hc-bubble-body');
    if (!body) return;

    const hist = _hcJobHistory[job.job_id] || [];
    const progressPct = Math.min(4 + hist.length * 7, 88);

    const doneItems = hist.slice(0, -1).map(s =>
      `<div class="hc-think-item done"><span class="hc-think-done">✓</span><span class="hc-think-text">${_hcEsc(s)}</span></div>`
    ).join('');
    const currentItem = hist.length
      ? `<div class="hc-think-item current"><span class="hc-think-bird" aria-hidden="true"><svg viewBox="0 0 32 32" width="16" height="16"><path class="hb-beak" d="M2 13.5 L11 15" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/><circle cx="13" cy="15" r="3" fill="currentColor"/><ellipse cx="19" cy="18" rx="6" ry="3.4" fill="currentColor" transform="rotate(22 19 18)"/><path d="M23.5 21 L30 27 L26.5 21.5 L31 22.5 Z" fill="currentColor"/><path class="hb-wing" d="M17 16 Q21 4 28 6 Q23 12 19 17 Z" fill="currentColor" opacity=".8"/></svg></span><span class="hc-think-text">${_hcEsc(hist[hist.length - 1])}</span></div>`
      : `<div class="hc-think-item current"><span class="hc-think-bird" aria-hidden="true"><svg viewBox="0 0 32 32" width="16" height="16"><path class="hb-beak" d="M2 13.5 L11 15" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/><circle cx="13" cy="15" r="3" fill="currentColor"/><ellipse cx="19" cy="18" rx="6" ry="3.4" fill="currentColor" transform="rotate(22 19 18)"/><path d="M23.5 21 L30 27 L26.5 21.5 L31 22.5 Z" fill="currentColor"/><path class="hb-wing" d="M17 16 Q21 4 28 6 Q23 12 19 17 Z" fill="currentColor" opacity=".8"/></svg></span><span class="hc-think-text">initializing…</span></div>`;

    body.innerHTML =
      `<div class="hc-think-checklist">${doneItems}${currentItem}</div>` +
      `<div class="hc-think-progress"><div class="hc-think-progress-fill" style="width:${progressPct}%"></div></div>`;
  }

  // ── Pending jobs (SSE-driven; no timer loop) ─────────────────────────────
  // Each `sse:chat` event for a tracked job triggers exactly one status fetch.
  // The APEX lane answers synchronously, so this only matters for legacy
  // pending acknowledgements.
  function _hcPollJobs(jobIds) {
    if (!jobIds || jobIds.length === 0) return;
    const convId = _hcConvId;
    const viewVersion = _hcViewVersion;
    const tracked = new Set(jobIds.map(String));
    const finishedJobs = new Set();
    const statusEl = document.getElementById('home-chat-status');

    const settle = (job) => {
      finishedJobs.add(job.job_id);
      const container = document.getElementById('home-chat-messages');
      if (container) {
        const pending = container.querySelector(`.hc-bubble[data-pending-job-id="${CSS.escape(String(job.job_id))}"]`);
        if (pending) pending.remove();
      }
      delete _hcJobHistory[job.job_id];
    };

    const refresh = () => {
      if (_hcConvId !== convId || _hcViewVersion !== viewVersion) return;
      fetch('/api/chat/jobs/status?job_ids=' + encodeURIComponent(jobIds.join(',')) + (_hcConvId ? '&conversation_id=' + encodeURIComponent(_hcConvId) : ''))
        .then(r => r.json())
        .then(data => {
          if (_hcConvId !== convId || _hcViewVersion !== viewVersion) return;
          const jobs = data.jobs || [];
          let allDone = true;

          jobs.forEach(job => {
            if (finishedJobs.has(job.job_id)) return;
            if (job.status === 'completed' && job.response) {
              settle(job);
              _hcAppendBubble({
                sender: job.agent,
                message_type: 'agent',
                content: job.response,
                created_at: new Date().toISOString()
              });
              _hcScrollBottom();
            } else if (job.status === 'failed') {
              settle(job);
              _hcAppendBubble({
                sender: job.agent || 'system',
                message_type: 'system',
                content: `${job.agent || 'Agent'} failed: ${job.error || 'unknown error'}`,
                created_at: new Date().toISOString()
              });
              _hcScrollBottom();
            } else if (job.status === 'running' || job.status === 'queued') {
              allDone = false;
              _hcUpsertThinkingBubble(job);
            }
          });

          if (!allDone) {
            if (statusEl) statusEl.textContent = 'Agents working…';
          } else {
            document.removeEventListener('sse:chat', onSse);
            if (statusEl && _hcLaneState === 'ok') statusEl.textContent = 'Ready';
            _hcSilentRefresh(convId, true);
          }
        })
        .catch(() => {
          _hcSetLaneState('offline', 'job status fetch failed');
        });
    };

    const onSse = (e) => {
      const d = (e && e.detail) || {};
      if (_hcConvId !== convId || _hcViewVersion !== viewVersion) {
        document.removeEventListener('sse:chat', onSse);
        return;
      }
      if (d.conversation_id && String(d.conversation_id) !== String(convId)) return;
      if (d.job_id && !tracked.has(String(d.job_id))) return;
      refresh();
    };
    document.addEventListener('sse:chat', onSse);
    // One immediate fetch covers the window between the ack and SSE attach.
    refresh();
  }

  // ── Utilities ────────────────────────────────────────────────────────────
  // Phase 4: delegate to the shared SwarmChat.esc so every chat surface uses
  // one escape implementation. Kept as a local wrapper because this file has
  // dozens of call sites and we want a single swap point if the contract
  // changes.
  function _hcEsc(v) {
    if (window.SwarmChat && typeof window.SwarmChat.esc === 'function') {
      return window.SwarmChat.esc(v);
    }
    return String(v == null ? '' : v)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // Expose for cross-module refresh (agent registry reload)
  window._hcRenderAgentPills = _hcRenderAgentPills;

  // ── Agents panel toggle ──────────────────────────────────────────────────
  const HC_PANEL_KEY = 'fridays-home-chat-agents-panel';
  const HC_MANUAL_KEY = 'fridays-home-chat-manual-override';

  window.toggleHomeChatAgents = function () {
    const panel = document.getElementById('home-chat-agents-panel');
    const btn = document.getElementById('home-chat-agents-toggle');
    if (!panel) return;
    const collapsed = !panel.classList.contains('collapsed');
    panel.classList.toggle('collapsed', collapsed);
    if (btn) btn.classList.toggle('panel-open', !collapsed);
    localStorage.setItem(HC_PANEL_KEY, collapsed ? 'collapsed' : 'open');
  };

  window.onHomeChatManualOverrideToggle = function () {
    const cb = document.getElementById('home-chat-manual-override');
    const label = document.getElementById('hc-auto-label');
    const isManual = cb && cb.checked;
    localStorage.setItem(HC_MANUAL_KEY, isManual ? '1' : '0');
    if (label) {
      label.textContent = isManual ? 'Manual selection active' : 'Auto-routing active';
      label.classList.toggle('manual-mode', isManual);
    }
    // When in auto mode, dim agent pills; when manual, brighten them
    const pills = document.querySelectorAll('#home-chat-agents .home-chat-agent-pill');
    pills.forEach(p => {
      p.style.opacity = isManual ? '1' : '0.6';
      p.style.pointerEvents = isManual ? 'auto' : 'auto'; // always clickable
    });
  };

  // Restore panel state on init
  function _hcRestorePanelState() {
    const panel = document.getElementById('home-chat-agents-panel');
    const btn = document.getElementById('home-chat-agents-toggle');
    const saved = localStorage.getItem(HC_PANEL_KEY);
    if (panel && saved === 'collapsed') {
      panel.classList.add('collapsed');
      if (btn) btn.classList.remove('panel-open');
    } else if (panel) {
      panel.classList.remove('collapsed');
      if (btn) btn.classList.add('panel-open');
    }
    // Restore manual override
    const cb = document.getElementById('home-chat-manual-override');
    const isManual = localStorage.getItem(HC_MANUAL_KEY) === '1';
    if (cb) cb.checked = isManual;
    window.onHomeChatManualOverrideToggle();
  }

  // ── Greeting ─────────────────────────────────────────────────────────────
  function _hcSetGreeting() {
    const el = document.getElementById('home-welcome-greeting');
    if (!el) return;
    const h = new Date().getHours();
    const period = h < 5 ? 'Late night' : h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : h < 21 ? 'Good evening' : 'Late night';
    el.textContent = period;
  }

  // ── Interests fetch & render ─────────────────────────────────────────────
  function _hcFetchInterests() {
    window.fridayInterestUsername().then(username => fetch('/api/interests?limit=8&username=' + encodeURIComponent(username)))
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(data => {
        if (data.onboarding && data.onboarding_categories && data.onboarding_categories.length > 0) {
          // Empty state — show onboarding questionnaire
          _hcShowOnboarding(data.onboarding_categories);
        } else {
          _hcRenderInterestCards(data.interests || []);
          _hcRenderResearchTopics(data.research_topics || []);
        }
      })
      .catch(error => {
        console.error('Unable to load interests', error);
        if (typeof showToast === 'function') showToast('Unable to load your interests', 'error');
      });
  }

  // ── Onboarding flow ──────────────────────────────────────────────────────
  let _hcSelectedTopics = new Set();

  function _hcShowOnboarding(categories) {
    const panel = document.getElementById('home-onboarding');
    const catHost = document.getElementById('home-onboarding-categories');
    if (!panel || !catHost) return;

    // Update welcome messaging for onboarding state
    const greeting = document.getElementById('home-welcome-greeting');
    const tagline = document.querySelector('.home-welcome-tagline');
    const subtitle = document.querySelector('.home-welcome-subtitle');
    if (greeting) greeting.textContent = 'Welcome to Friday';
    if (tagline) tagline.textContent = "Let's get to know you";
    if (subtitle) subtitle.textContent = "I'm your AI assistant. Tell me what you're interested in and I'll personalise your experience.";

    // Build category cards
    catHost.innerHTML = categories.map(cat => {
      const topicPills = cat.topics.map(t =>
        `<button class="home-onboarding-topic" data-topic="${_hcEsc(t)}">${_hcEsc(t)}</button>`
      ).join('');
      return `<div class="home-onboarding-cat">` +
        `<div class="home-onboarding-cat-label"><span class="cat-icon">${cat.icon}</span> ${_hcEsc(cat.label)}</div>` +
        `<div class="home-onboarding-topics">${topicPills}</div>` +
        `</div>`;
    }).join('');

    // Custom topic input
    const selectedHost = document.getElementById('home-onboarding-selected');
    if (selectedHost) {
      selectedHost.innerHTML =
        '<div class="home-onboarding-custom">' +
        '<input id="home-onboarding-custom-input" type="text" placeholder="Or type your own interest..." maxlength="100">' +
        '<button id="home-onboarding-custom-add">Add</button>' +
        '</div>' +
        '<div class="home-onboarding-selected-count" id="home-onboarding-count"></div>';
    }

    // Bind topic pill clicks
    catHost.querySelectorAll('.home-onboarding-topic').forEach(pill => {
      pill.addEventListener('click', () => {
        const topic = pill.dataset.topic;
        if (_hcSelectedTopics.has(topic)) {
          _hcSelectedTopics.delete(topic);
          pill.classList.remove('selected');
        } else {
          _hcSelectedTopics.add(topic);
          pill.classList.add('selected');
        }
        _hcUpdateOnboardingCount();
      });
    });

    // Custom topic add
    const customInput = document.getElementById('home-onboarding-custom-input');
    const customAdd = document.getElementById('home-onboarding-custom-add');
    if (customInput && customAdd) {
      const addCustom = () => {
        const val = customInput.value.trim();
        if (val && val.length <= 100) {
          _hcSelectedTopics.add(val);
          customInput.value = '';
          _hcUpdateOnboardingCount();
        }
      };
      customAdd.addEventListener('click', addCustom);
      customInput.addEventListener('keydown', e => {
        if (e.key === 'Enter') { e.preventDefault(); addCustom(); }
      });
    }

    // Save button
    const saveBtn = document.getElementById('home-onboarding-save');
    if (saveBtn) {
      saveBtn.addEventListener('click', () => _hcSaveOnboarding());
    }

    // Skip button
    const skipBtn = document.getElementById('home-onboarding-skip');
    if (skipBtn) {
      skipBtn.addEventListener('click', () => {
        panel.style.display = 'none';
        // Restore normal greeting
        _hcSetGreeting();
      });
    }

    panel.style.display = 'block';
  }

  function _hcUpdateOnboardingCount() {
    const countEl = document.getElementById('home-onboarding-count');
    const saveBtn = document.getElementById('home-onboarding-save');
    const n = _hcSelectedTopics.size;
    if (countEl) {
      countEl.innerHTML = n > 0
        ? `<strong>${n}</strong> interest${n === 1 ? '' : 's'} selected`
        : '';
    }
    if (saveBtn) saveBtn.disabled = n === 0;
  }

  function _hcSaveOnboarding() {
    const topics = Array.from(_hcSelectedTopics);
    if (topics.length === 0) return;

    const saveBtn = document.getElementById('home-onboarding-save');
    if (saveBtn) {
      saveBtn.disabled = true;
      saveBtn.textContent = 'Saving...';
    }

    window.fridayInterestUsername().then(username => fetch('/api/interests/seed', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ topics: topics, username: username }),
    }))
    .then(r => r.json())
    .then(data => {
      if (data.ok) {
        // Transition: hide onboarding, re-fetch interests to show cards
        const panel = document.getElementById('home-onboarding');
        if (panel) panel.style.display = 'none';
        _hcSetGreeting();
        _hcSelectedTopics.clear();
        // Re-fetch to show the new interest cards
        window.fridayInterestUsername().then(username => fetch('/api/interests?limit=8&username=' + encodeURIComponent(username)))
          .then(r => r.ok ? r.json() : Promise.reject())
          .then(d => {
            _hcRenderInterestCards(d.interests || []);
            _hcRenderResearchTopics(d.research_topics || []);
          })
          .catch(error => {
            console.error('Unable to refresh interests', error);
            if (typeof showToast === 'function') showToast('Unable to refresh your interests', 'error');
          });
      }
    })
    .catch(error => {
      console.error('Unable to save interests', error);
      if (typeof showToast === 'function') showToast('Unable to save your interests', 'error');
      if (saveBtn) {
        saveBtn.disabled = false;
        saveBtn.textContent = 'Save my interests';
      }
    });
  }

  function _hcRenderInterestCards(interests) {
    const row = document.getElementById('home-interests-row');
    if (!row || interests.length === 0) return;

    const icons = { memory: '🧠', patterns: '📊', conversations: '💬', saved: '⭐' };
    // Phase 5: agent-sourced interests get a provenance badge so the user can
    // see which local agent suggested a topic (Librarian/Scholar/Seeker).
    const agentBadge = { librarian: '📚', scholar: '🔭', seeker: '🌐' };
    row.innerHTML = interests.map(item => {
      const topSrc = item.sources[item.sources.length - 1] || 'conversations';
      const icon = icons[topSrc] || '💬';
      const sa = (item.source === 'agent' && item.source_agent)
        ? String(item.source_agent).toLowerCase() : '';
      const badge = sa
        ? `<span class="home-interest-agent" title="Suggested by ${_hcEsc(sa)}" data-agent="${_hcEsc(sa)}">${agentBadge[sa] || '🤖'}</span>`
        : '';
      return `<button class="home-interest-card" data-suggestion="${_hcEsc(item.suggestion)}" title="${_hcEsc(item.suggestion)}">` +
        `<span class="home-interest-icon">${icon}</span>` +
        `<span>${_hcEsc(item.topic)}</span>` +
        badge +
        `<span class="home-interest-source" data-src="${topSrc}">${topSrc}</span>` +
        `</button>`;
    }).join('');

    row.querySelectorAll('.home-interest-card').forEach(card => {
      card.addEventListener('click', () => {
        const suggestion = card.dataset.suggestion;
        if (!suggestion) return;
        const input = document.getElementById('home-chat-input');
        if (input) {
          input.value = suggestion;
          input.focus();
          input.dispatchEvent(new Event('input'));
        }
      });
    });
  }

  function _hcRenderResearchTopics(topics) {
    const row = document.getElementById('home-research-row');
    if (!row || topics.length === 0) return;

    row.innerHTML = '<span style="font-size:9px;color:var(--text-dim);opacity:0.6;text-transform:uppercase;letter-spacing:0.5px;font-weight:700;">Research:</span> ' +
      topics.map(t => {
        const status = (t.status || '').toLowerCase();
        return `<button class="home-research-tag" data-status="${status}" data-topic="${_hcEsc(t.topic)}" title="Research: ${_hcEsc(t.topic)}">` +
          `${_hcEsc(t.topic)}</button>`;
      }).join('');

    row.querySelectorAll('.home-research-tag').forEach(tag => {
      tag.addEventListener('click', () => {
        const topic = tag.dataset.topic;
        if (!topic) return;
        const input = document.getElementById('home-chat-input');
        if (input) {
          input.value = `What did the research on "${topic}" find?`;
          input.focus();
        }
      });
    });
  }

  // ── Mini memory landscape (ambient background) ───────────────────────────
  let _hcMiniLandscapeActive = false;
  let _hcMiniAnimFrame = null;

  function _hcInitMiniLandscape() {
    const canvas = document.getElementById('home-mini-landscape');
    if (!canvas) return;

    // Fetch memory data if not cached
    if (!window.__memoryCache || window.__memoryCache.length === 0) {
      fetch('/api/memory?limit=300&min=1')
        .then(r => r.ok ? r.json() : Promise.reject())
        .then(data => {
          // Flatten results into cache format
          const flat = [];
          const results = data.results || {};
          for (const [agent, entries] of Object.entries(results)) {
            entries.forEach(e => flat.push({ ...e, _agent: agent }));
          }
          if (flat.length > 0) {
            window.__memoryCache = flat;
            _hcStartMiniLandscape(canvas);
          }
        })
        .catch(() => {});
    } else {
      _hcStartMiniLandscape(canvas);
    }
  }

  function _hcStartMiniLandscape(canvas) {
    if (_hcMiniLandscapeActive) return;
    _hcMiniLandscapeActive = true;

    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const cache = window.__memoryCache || [];
    if (!cache.length) return;

    // Build simplified node data
    const agentCounts = {};
    const agentTags = {};
    const globalTags = {};

    cache.forEach(m => {
      const agent = m._agent || m.agent || 'unknown';
      agentCounts[agent] = (agentCounts[agent] || 0) + 1;
      if (!agentTags[agent]) agentTags[agent] = {};
      const tags = String(m.tags || '').split(',').map(t => t.trim().toLowerCase()).filter(Boolean);
      tags.forEach(t => {
        agentTags[agent][t] = (agentTags[agent][t] || 0) + 1;
        globalTags[t] = (globalTags[t] || 0) + 1;
      });
    });

    const agents = Object.keys(agentCounts);
    const topTags = Object.entries(globalTags)
      .filter(([tag]) => {
        let cnt = 0;
        for (const at of Object.values(agentTags)) { if (at[tag]) cnt++; }
        return cnt >= 2;
      })
      .sort((a, b) => b[1] - a[1]).slice(0, 12).map(([t]) => t);

    // Create nodes
    const nodes = [];
    const palette = ['#ff6b6b','#ffa500','#ffc800','#4caf50','#00bcd4','#2563eb','#9333ea','#ec4899','#6cb6ff','#00d084','#f59e0b','#8b5cf6'];
    let ci = 0;

    agents.forEach((agent, i) => {
      const angle = (i / agents.length) * Math.PI * 2;
      const r = 100 + Math.random() * 60;
      nodes.push({
        id: 'a:' + agent, label: agent, type: 'agent',
        x: 300 + Math.cos(angle) * r, y: 200 + Math.sin(angle) * r,
        vx: 0, vy: 0,
        size: Math.min(5 + Math.sqrt(agentCounts[agent]) * 2, 16),
        color: palette[ci++ % palette.length],
      });
    });

    topTags.forEach((tag, i) => {
      const angle = (i / topTags.length) * Math.PI * 2 + 0.5;
      const r = 50 + Math.random() * 30;
      nodes.push({
        id: 't:' + tag, label: tag, type: 'tag',
        x: 300 + Math.cos(angle) * r, y: 200 + Math.sin(angle) * r,
        vx: 0, vy: 0, size: 3, color: 'rgba(108,182,255,0.4)',
      });
    });

    // Build links
    const links = [];
    const nodeMap = {};
    nodes.forEach(n => { nodeMap[n.id] = n; });
    agents.forEach(agent => {
      topTags.forEach(tag => {
        if (agentTags[agent] && agentTags[agent][tag]) {
          links.push({ source: 'a:' + agent, target: 't:' + tag, weight: agentTags[agent][tag] });
        }
      });
    });

    // Gentle animation loop — low CPU
    function tick() {
      if (!_hcMiniLandscapeActive) return;

      const rect = canvas.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) {
        _hcMiniAnimFrame = requestAnimationFrame(tick);
        return;
      }
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const w = rect.width, h = rect.height;

      // Very gentle physics
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i], b = nodes[j];
          let dx = b.x - a.x, dy = b.y - a.y;
          let dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = 400 / (dist * dist);
          const fx = (dx / dist) * force, fy = (dy / dist) * force;
          a.vx -= fx; a.vy -= fy;
          b.vx += fx; b.vy += fy;
        }
      }
      links.forEach(l => {
        const a = nodeMap[l.source], b = nodeMap[l.target];
        if (!a || !b) return;
        let dx = b.x - a.x, dy = b.y - a.y;
        let dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const force = (dist - 80) * 0.003;
        const fx = (dx / dist) * force, fy = (dy / dist) * force;
        a.vx += fx; a.vy += fy;
        b.vx -= fx; b.vy -= fy;
      });
      nodes.forEach(n => {
        n.vx += (w / 2 - n.x) * 0.0003;
        n.vy += (h / 2 - n.y) * 0.0003;
        n.vx *= 0.92; n.vy *= 0.92;
        n.x += n.vx; n.y += n.vy;
      });

      // Render
      ctx.clearRect(0, 0, w, h);
      links.forEach(l => {
        const a = nodeMap[l.source], b = nodeMap[l.target];
        if (!a || !b) return;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.strokeStyle = 'rgba(255,255,255,0.04)';
        ctx.lineWidth = 1;
        ctx.stroke();
      });
      nodes.forEach(n => {
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.size, 0, Math.PI * 2);
        ctx.fillStyle = n.type === 'agent' ? (n.color + '22') : 'rgba(108,182,255,0.08)';
        ctx.fill();
        ctx.strokeStyle = n.type === 'agent' ? (n.color + '44') : 'rgba(108,182,255,0.15)';
        ctx.lineWidth = 0.8;
        ctx.stroke();
      });

      _hcMiniAnimFrame = requestAnimationFrame(tick);
    }
    tick();

    // Stop animation when welcome state is hidden
    const observer = new MutationObserver(() => {
      const welcome = document.querySelector('.home-chat-welcome');
      if (welcome && welcome.style.display === 'none') {
        _hcMiniLandscapeActive = false;
        if (_hcMiniAnimFrame) cancelAnimationFrame(_hcMiniAnimFrame);
      }
    });
    const welcome = document.querySelector('.home-chat-welcome');
    if (welcome) observer.observe(welcome, { attributes: true, attributeFilter: ['style'] });
  }

  // ── MD-FEATURE-060FE8D72E64 — Favourites star next to chat input ────────
  // Stores user-curated quick prompts in localStorage. Click the star to save
  // the current input; if the input is empty, the star opens a picker so the
  // user can paste a saved prompt back into the textarea.
  const HC_FAVOURITES_KEY = 'fridays-chat-favourites';
  function _hcLoadFavs() {
    try { return JSON.parse(localStorage.getItem(HC_FAVOURITES_KEY) || '[]'); }
    catch (_e) { return []; }
  }
  function _hcSaveFavs(list) {
    localStorage.setItem(HC_FAVOURITES_KEY, JSON.stringify(list.slice(0, 50)));
  }
  function homeChatToggleFavourite() {
    const input = document.getElementById('home-chat-input');
    const text = (input && input.value || '').trim();
    if (text) {
      const favs = _hcLoadFavs();
      if (!favs.includes(text)) {
        favs.unshift(text);
        _hcSaveFavs(favs);
        if (typeof window.showToast === 'function') window.showToast('Saved to favourites', 'success');
      } else {
        if (typeof window.showToast === 'function') window.showToast('Already in favourites', 'info');
      }
      return;
    }
    _hcShowFavouritesPicker();
  }
  function _hcShowFavouritesPicker() {
    const favs = _hcLoadFavs();
    let modal = document.getElementById('home-chat-favs-modal');
    if (modal) modal.remove();
    modal = document.createElement('div');
    modal.id = 'home-chat-favs-modal';
    modal.style.cssText = 'position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center;';
    const items = favs.length
      ? favs.map((f, i) => `
          <div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border);">
            <button data-fav-idx="${i}" class="hc-fav-use" style="flex:1;text-align:left;background:transparent;border:none;color:var(--text);font-size:12px;cursor:pointer;">${(f || '').replace(/[<>]/g, '').slice(0, 140)}</button>
            <button data-fav-del="${i}" class="hc-fav-del" title="Remove" style="background:transparent;border:1px solid var(--border);border-radius:3px;color:var(--text-dim);font-size:11px;cursor:pointer;padding:2px 6px;">×</button>
          </div>`).join('')
      : '<div style="font-size:11px;color:var(--text-dim);padding:6px 0;">No favourites yet. Type something into the chat input and click the star to save it.</div>';
    modal.innerHTML = `
      <div style="background:var(--card);border:1px solid var(--border);border-radius:10px;padding:18px 20px;width:min(520px,90vw);max-height:70vh;overflow:auto;box-shadow:0 14px 40px rgba(0,0,0,.4);">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
          <div style="font-size:13px;font-weight:700;color:var(--accent);">Chat favourites</div>
          <button onclick="document.getElementById('home-chat-favs-modal').remove()" aria-label="Close" style="background:transparent;border:none;color:var(--text-dim);font-size:18px;cursor:pointer;">×</button>
        </div>
        <div>${items}</div>
      </div>`;
    modal.addEventListener('click', (e) => {
      if (e.target === modal) { modal.remove(); return; }
      const useIdx = e.target.closest('[data-fav-idx]')?.getAttribute('data-fav-idx');
      const delIdx = e.target.closest('[data-fav-del]')?.getAttribute('data-fav-del');
      if (useIdx !== undefined && useIdx !== null) {
        const list = _hcLoadFavs();
        const v = list[Number(useIdx)];
        if (v) {
          const input = document.getElementById('home-chat-input');
          if (input) { input.value = v; input.focus(); }
        }
        modal.remove();
      } else if (delIdx !== undefined && delIdx !== null) {
        const list = _hcLoadFavs();
        list.splice(Number(delIdx), 1);
        _hcSaveFavs(list);
        modal.remove();
        _hcShowFavouritesPicker();
      }
    });
    const escH = (e) => { if (e.key === 'Escape') { const m = document.getElementById('home-chat-favs-modal'); if (m) m.remove(); document.removeEventListener('keydown', escH); } };
    document.addEventListener('keydown', escH);
    document.body.appendChild(modal);
  }
  window.homeChatToggleFavourite = homeChatToggleFavourite;

})();
