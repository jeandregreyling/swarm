// Conversations — load chat data, conversation detail, rename/delete
// Extracted from terminal_base.html

function loadChatData(win) {
  const messages = win.el.querySelector('#chat-messages');
  if (!messages) return;

  initializeChatPanel();
  const savedThread = localStorage.getItem('fridays-chat-active-thread');
  const preferred = window.__fridaysChatConversationId || (savedThread ? Number(savedThread) : null);
  refreshChatThreadList(preferred).then(() => {
    if (window.__fridaysChatConversationId) {
      loadConversationMessages(window.__fridaysChatConversationId);
      return;
    }
    const first = (window._chatConversations || [])[0];
    if (first && first.id) {
      switchChatThread(String(first.id));
    }
  });
}

function _escHtml(v) {
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
          <h3 id="chat-det-title" style="margin:0;font-size:14px;">💬 Conversation</h3>
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
      const convTitle = conv.title || '(untitled)';
      titleNode.textContent = `💬 ${convTitle}`;

      toolbar.innerHTML = `
        <button onclick="renameConversation(${conv.id})" style="padding:6px 10px;background:var(--card);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:11px;cursor:pointer;">✎ Edit Title</button>
        <button onclick="deleteConversation(${conv.id})" style="padding:6px 10px;background:#f4433620;border:1px solid #f4433660;border-radius:4px;color:#f44336;font-size:11px;cursor:pointer;">🗑 Delete Conversation</button>
        <span style="margin-left:auto;color:var(--text-dim);font-size:11px;">${(conv.created_at || '').slice(0,16)} · ${(conv.source || 'unknown')}</span>
      `;

      if (!rows.length) {
        body.innerHTML = '<div style="color:var(--text-dim);text-align:center;padding:24px;">No messages in this conversation.</div>';
        return;
      }

      body.innerHTML = rows.map(m => {
        const sender = _escHtml(m.sender || 'agent');
        const to = _escHtml(m.to_agent || '—');
        const ts = _escHtml((m.created_at || '').slice(0,16));
        const type = _escHtml(m.message_type || 'text');
        const isFridays = (m.sender || '').toLowerCase() === 'fridays';
        const isUser = (m.sender || '').toLowerCase() === 'user';
        // skill/system output: pre-wrap; user: pre-wrap; agents: markdown
        const contentHtml = (isFridays || isUser)
          ? `<div style="white-space:pre-wrap;line-height:1.55;">${_escHtml(m.content || '')}</div>`
          : `<div class="chat-text" style="line-height:1.55;">${(typeof marked !== 'undefined' ? marked.parse(String(m.content || ''), {gfm:true,breaks:false}) : _escHtml(m.content || ''))}</div>`;
        return `<div style="margin-bottom:10px;padding:10px 12px;background:var(--card);border:1px solid var(--border);border-radius:6px;">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:6px;">
            <div style="font-size:11px;"><strong>${sender}</strong> → <span style="color:var(--text-dim);">${to}</span></div>
            <div style="font-size:10px;color:var(--text-dim);">${type} · ${ts}</div>
          </div>
          ${contentHtml}
        </div>`;
      }).join('');
    })
    .catch(e => {
      body.innerHTML = `<div style="color:#f77;padding:20px;">Error loading conversation: ${_escHtml(e.message)}</div>`;
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

function deleteConversation(convId) {
  if (!confirm('Delete this conversation and all of its messages?')) return;
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
}

