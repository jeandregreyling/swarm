// Conversations — load chat data, conversation detail, rename/delete
// Extracted from terminal_base.html
//
// Hard-refresh behaviour summary (MD-FEATURE-32DFD66D8BA4 / -9792296AF505 /
// -A138E31DED58):
//   * On hard refresh, friday-auth.js fires `_authCheck()` from
//     DOMContentLoaded → GET /api/auth/me. If the session cookie is valid the
//     login overlay is suppressed (correct & intentional — see the
//     "Hard refresh: no login prompt" investigation note in
//     docs/FEATURES_TODO.md).
//   * The chat tile does NOT auto-restore on hard refresh (no window
//     persistence layer yet). When the user opens the Chat tile,
//     loadChatData() runs below and ALWAYS defaults to a fresh thread unless
//     the caller explicitly handed us `__fridaysChatOpenWithConvId`.
//   * Locked by tests/test_hard_refresh_behavior.py.

function loadChatData(win) {
  const messages = win.el.querySelector('#chat-messages');
  if (!messages) return;

  initializeChatPanel();
  // Clear stale render signature so messages always render fresh on open
  window.__fridaysChatLastRenderSig = '';

  // Session 28 fix: main chat window always opens on a fresh thread unless
  // the caller explicitly handed us a conversation id to resume
  // (e.g. home-chat "expand" button sets __fridaysChatOpenWithConvId).
  // Previously we auto-resumed the most-recent thread from localStorage or
  // fell back to the first conversation, which made it impossible to start
  // a new chat just by opening the window.
  const explicitOpenId = window.__fridaysChatOpenWithConvId || null;
  window.__fridaysChatOpenWithConvId = null; // one-shot

  if (explicitOpenId) {
    refreshChatThreadList(explicitOpenId).then(() => {
      const convId = window.__fridaysChatConversationId;
      if (convId) {
        loadConversationMessages(convId).then(() => {
          startChatLiveSyncService && startChatLiveSyncService();
        });
      } else {
        startChatLiveSyncService && startChatLiveSyncService();
      }
    });
    return;
  }

  // No explicit resume — start a new thread, but still populate the thread
  // picker so the user can jump to any existing conversation.
  window.__fridaysChatConversationId = null;
  window.__fridaysChatForceNewThread = true;
  refreshChatThreadList(null).then(() => {
    _renderWelcome && _renderWelcome();
    startChatLiveSyncService && startChatLiveSyncService();
  });
}

function _escHtml(v) {
  if (typeof window !== 'undefined' && window.SwarmChat && typeof window.SwarmChat.esc === 'function') {
    return window.SwarmChat.esc(v);
  }
  return String(v ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function _jsStr(v) {
  return JSON.stringify(String(v ?? ''));
}

function openConversationDetail(convId) {
  let modal = document.getElementById('chat-detail-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'chat-detail-modal';
    modal.className = 'modal';
    modal.onclick = e => { if (e.target === modal) modal.classList.remove('open'); };
    modal.innerHTML = `
      <div class="modal-content" style="width:92%;max-width:980px;max-height:88vh;display:flex;flex-direction:column;">
        <div style="display:flex;justify-content:space-between;align-items:center;padding:14px 16px;border-bottom:1px solid var(--border);flex-shrink:0;">
          <h3 id="chat-det-title" style="margin:0;font-size:14px;display:flex;align-items:center;gap:6px;"><svg viewBox="0 0 16 16" width="14" height="14" fill="none"><path d="M2.5 3h11a1 1 0 011 1v6a1 1 0 01-1 1h-3l-3 2.5V11h-5a1 1 0 01-1-1V4a1 1 0 011-1z" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg> Conversation</h3>
          <button onclick="document.getElementById('chat-detail-modal').classList.remove('open')"
                  style="background:none;border:none;color:var(--text);font-size:18px;cursor:pointer;">✕</button>
        </div>
        <div id="chat-det-toolbar" style="display:flex;gap:8px;align-items:center;padding:10px 16px;border-bottom:1px solid var(--border);flex-shrink:0;"></div>
        <div id="chat-det-body" style="overflow-y:auto;padding:16px;flex:1;font-size:12px;"></div>
      </div>`;
    document.body.appendChild(modal);
  }

  const body = document.getElementById('chat-det-body');
  const titleNode = document.getElementById('chat-det-title');
  const toolbar = document.getElementById('chat-det-toolbar');
  if (!body || !titleNode || !toolbar) return;

  body.innerHTML = '<div style="color:var(--text-dim);text-align:center;padding:24px;">Loading conversation…</div>';
  modal.classList.add('open');

  fetch(`/api/conversations/${convId}/messages`)
    .then(r => r.json())
    .then(data => {
      if (data.error) throw new Error(data.error);
      const conv = data.conv || {};
      const rows = data.messages || [];
      const linkedProposals = data.proposals || [];
      const convTitle = conv.title || '(untitled)';
      titleNode.innerHTML = `<svg viewBox="0 0 16 16" width="14" height="14" fill="none"><path d="M2.5 3h11a1 1 0 011 1v6a1 1 0 01-1 1h-3l-3 2.5V11h-5a1 1 0 01-1-1V4a1 1 0 011-1z" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg> ${_escHtml(convTitle)}`;

      const proposalBadges = linkedProposals.map(p => {
        const pc = p.status === 'approved' || p.status === 'done' ? '#4caf50' : p.status === 'pending' ? '#ffa500' : '#888';
        return `<span onclick="openProposalDetail(${JSON.stringify(p.proposal_id).replace(/'/g,'&#39;')})" style="padding:3px 10px;border-radius:12px;background:${pc}20;color:${pc};font-size:11px;cursor:pointer;border:1px solid ${pc}40;">${_escHtml(p.proposal_id)}</span>`;
      }).join('');

      toolbar.innerHTML = `
        <button id="chat-det-tab-msgs" onclick="openConversationDetail.showTab('messages',${conv.id})"
          style="padding:6px 10px;background:var(--accent);border:1px solid var(--accent);border-radius:4px;color:#fff;font-size:11px;cursor:pointer;">Messages</button>
        <button id="chat-det-tab-tl" onclick="openConversationDetail.showTab('timeline',${conv.id})"
          style="padding:6px 10px;background:var(--card);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:11px;cursor:pointer;">Timeline</button>
        <button onclick="renameConversation(${conv.id})" style="padding:6px 10px;background:var(--card);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:11px;cursor:pointer;">Edit Title</button>
        <button onclick="deleteConversation(${conv.id}, event)" style="padding:6px 10px;background:#f4433620;border:1px solid #f4433660;border-radius:4px;color:#f44336;font-size:11px;cursor:pointer;">Delete</button>
        <button onclick="window.openRecord && window.openRecord('thread', ${conv.id})" title="Open this thread in Studio Records" style="padding:6px 10px;background:var(--card);border:1px solid var(--border);border-radius:4px;color:var(--text-dim);font-size:11px;cursor:pointer;">In Records</button>
        <button onclick="window.revealInFiles && window.revealInFiles('thread', ${conv.id})" title="Reveal this thread in the Files tile" style="padding:6px 10px;background:var(--card);border:1px solid var(--border);border-radius:4px;color:var(--text-dim);font-size:11px;cursor:pointer;">In Files</button>
        ${proposalBadges}
        <span style="margin-left:auto;color:var(--text-dim);font-size:11px;">${(function(s){ if(!s)return''; if(/^\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}/.test(s)&&!/[Z+]/.test(s.slice(-6))) s=s.replace(' ','T')+'Z'; const d=new Date(s); return isNaN(d)?s.slice(0,16):d.toLocaleString('en-AU',{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}); })(conv.created_at||'')} · ${(conv.source || 'unknown')}</span>
      `;

      if (!rows.length) {
        body.innerHTML = '<div style="color:var(--text-dim);text-align:center;padding:24px;">No messages in this conversation.</div>';
        openConversationDetail._msgsHtml = '';
        openConversationDetail._convId = conv.id;
        return;
      }

      const msgsHtml = rows.map(m => {
        const sender = _escHtml(m.sender || 'agent');
        const to = _escHtml(m.to_agent || '—');
        const ts = _escHtml((function(s){ if(!s)return''; if(/^\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}/.test(s)&&!/[Z+]/.test(s.slice(-6))) s=s.replace(' ','T')+'Z'; const d=new Date(s); return isNaN(d)?s.slice(0,16):d.toLocaleString('en-AU',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}); })(m.created_at||''));
        const type = _escHtml(m.message_type || 'text');
        const isFridays = (m.sender || '').toLowerCase() === 'fridays';
        const isUser = (m.sender || '').toLowerCase() === 'user';
        // skill/system output: pre-wrap; user: pre-wrap; agents: markdown
        const contentHtml = (isFridays || isUser)
          ? `<div style="white-space:pre-wrap;line-height:1.55;">${_escHtml(m.content || '')}</div>`
          : `<div class="chat-text" style="line-height:1.55;">${(typeof window !== 'undefined' && typeof window.safeMarkdown === 'function' ? window.safeMarkdown(m.content || '') : (typeof marked !== 'undefined' ? marked.parse(String(m.content || ''), {gfm:true,breaks:false}) : _escHtml(m.content || '')))}</div>`;
        return `<div style="margin-bottom:10px;padding:10px 12px;background:var(--card);border:1px solid var(--border);border-radius:6px;">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:6px;">
            <div style="font-size:11px;"><strong>${sender}</strong> → <span style="color:var(--text-dim);">${to}</span></div>
            <div style="font-size:10px;color:var(--text-dim);">${type} · ${ts}</div>
          </div>
          ${contentHtml}
        </div>`;
      }).join('');

      openConversationDetail._msgsHtml = msgsHtml;
      openConversationDetail._convId = conv.id;
      body.innerHTML = msgsHtml;
    })
    .catch(e => {
      body.innerHTML = `<div style="color:#f77;padding:20px;">Error loading conversation: ${_escHtml(e.message)}</div>`;
    });
}

// Tab switcher — attached to openConversationDetail so it shares scope
openConversationDetail.showTab = function(tab, convId) {
  const body = document.getElementById('chat-det-body');
  const btnMsgs = document.getElementById('chat-det-tab-msgs');
  const btnTl = document.getElementById('chat-det-tab-tl');
  if (!body) return;

  const activeStyle = 'padding:6px 10px;background:var(--accent);border:1px solid var(--accent);border-radius:4px;color:#fff;font-size:11px;cursor:pointer;';
  const inactiveStyle = 'padding:6px 10px;background:var(--card);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:11px;cursor:pointer;';

  if (tab === 'messages') {
    if (btnMsgs) btnMsgs.style.cssText = activeStyle;
    if (btnTl)   btnTl.style.cssText   = inactiveStyle;
    body.innerHTML = openConversationDetail._msgsHtml || '<div style="color:var(--text-dim);text-align:center;padding:24px;">No messages.</div>';
  } else {
    if (btnMsgs) btnMsgs.style.cssText = inactiveStyle;
    if (btnTl)   btnTl.style.cssText   = activeStyle;
    body.innerHTML = '<div style="color:var(--text-dim);text-align:center;padding:24px;">Loading timeline…</div>';
    loadConversationTimeline(convId || openConversationDetail._convId);
  }
};

function loadConversationTimeline(convId) {
  const body = document.getElementById('chat-det-body');
  if (!body) return;

  fetch(`/api/conversations/${convId}/timeline`)
    .then(r => r.json())
    .then(data => {
      const events = data.events || [];
      if (!events.length) {
        body.innerHTML = '<div style="color:var(--text-dim);text-align:center;padding:24px;">No timeline events yet for this conversation.<br><span style="font-size:11px;">Events are written as the agent works — check back once a task is running.</span></div>';
        return;
      }

      const _TYPE_STYLE = {
        stage:        'background:#1a3a5c;color:#7dc0ff;',
        skill_call:   'background:#1a3a1a;color:#7dca7d;',
        skill_result: 'background:#2a2a1a;color:#c0b060;',
        response:     'background:#2a1a3a;color:#c07dff;',
        final:        'background:#1a2a3a;color:#7dffca;',
        proposal:     'background:#3a1a2a;color:#ff7dca;',
        health:       'background:#2a3a1a;color:#c0ff7d;',
      };

      body.innerHTML = `
        <div style="font-size:11px;color:var(--text-dim);margin-bottom:10px;">${events.length} event(s) — oldest first</div>
        ${events.map(ev => {
          const typeStyle = _TYPE_STYLE[ev.event_type] || 'background:var(--card);color:var(--text);';
          const ts = (function(s){ if(!s)return''; if(/^\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}/.test(s)&&!/[Z+]/.test(s.slice(-6))) s=s.replace(' ','T')+'Z'; const d=new Date(s); return isNaN(d)?s.slice(11,19):d.toLocaleTimeString('en-AU',{hour:'2-digit',minute:'2-digit',second:'2-digit'}); })(ev.created_at||'');
          const agentBadge = `<span style="font-weight:600;color:var(--text);">${_escHtml(ev.agent || '')}</span>`;
          const typeBadge = `<span style="padding:1px 5px;border-radius:3px;font-size:10px;${typeStyle}">${_escHtml(ev.event_type || '')}</span>`;
          const payload = _escHtml(ev.payload || '');
          return `<div style="margin-bottom:6px;padding:8px 10px;background:var(--card);border:1px solid var(--border);border-radius:5px;">
            <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;flex-wrap:wrap;">
              <span style="font-size:10px;color:var(--text-dim);font-family:monospace;">${ts}</span>
              ${agentBadge}
              ${typeBadge}
            </div>
            <div style="white-space:pre-wrap;word-break:break-word;font-size:11px;line-height:1.5;color:var(--text);">${payload}</div>
          </div>`;
        }).join('')}`;
    })
    .catch(e => {
      if (body) body.innerHTML = `<div style="color:#f77;padding:20px;">Timeline load error: ${_escHtml(e.message)}</div>`;
    });
}

function renameConversation(convId) {
  const current = (window._chatConversations || []).find(c => c.id === convId);
  const nextTitle = prompt('New conversation title:', current?.title || '');
  if (nextTitle == null) return;
  const title = nextTitle.trim();
  if (!title) {
    showToast('Title cannot be empty', 'error');
    return;
  }
  fetch(`/api/conversations/${convId}`, {
    method: 'PATCH',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({title})
  })
    .then(r => r.json())
    .then(data => {
      if (!data.ok) throw new Error(data.error || 'update failed');
      showToast('Conversation updated', 'success');
      const chatWin = winManager.windows.get('chat');
      if (chatWin) loadChatData(chatWin);
      openConversationDetail(convId);
    })
    .catch(e => showToast('Error: ' + e.message, 'error'));
}

function deleteConversation(convId, event) {
  // Session 28 Workstream A: inline two-click arm-to-confirm on the button
  // when we have the triggering event; fall back to native confirm for any
  // programmatic callers that don't supply one.
  var btn = event && event.currentTarget;
  var fire = function () {
    fetch(`/api/conversations/${convId}`, { method: 'DELETE' })
      .then(r => r.json())
      .then(data => {
        if (!data.ok) throw new Error(data.error || 'delete failed');
        showToast('Conversation deleted', 'success');
        document.getElementById('chat-detail-modal')?.classList.remove('open');
        const chatWin = winManager.windows.get('chat');
        if (chatWin) loadChatData(chatWin);
      })
      .catch(e => showToast('Error: ' + e.message, 'error'));
  };
  if (btn && window.SwarmChat && typeof window.SwarmChat.armToConfirm === 'function') {
    window.SwarmChat.armToConfirm(btn, fire, { confirmLabel: 'Confirm', timeoutMs: 4000 });
    return;
  }
  if (!confirm('Delete this conversation and all of its messages?')) return;
  fire();
}

