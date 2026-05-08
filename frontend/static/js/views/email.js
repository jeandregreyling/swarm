// Email tile — inbox view for sevenpotato9@gmail.com and ninepotato7@gmail.com
// Shows swarm-processed emails with agent handling audit trail.

const _EMAIL_ACCOUNTS = ['sevenpotato9@gmail.com', 'ninepotato7@gmail.com'];
// V8 S-C505B1DB76: folder structure. Gmail label sync lives under the BIG
// step (S-5695672E4C); this SMALL step introduces the client-side folder
// dimension so the UI can route messages by folder without waiting for the
// backend rewrite.
const _EMAIL_FOLDERS = [
  { key: 'inbox',  label: 'Inbox',  icon: '📥' },
  { key: 'sent',   label: 'Sent',   icon: '📤' },
  { key: 'drafts', label: 'Drafts', icon: '📝' },
  { key: 'trash',  label: 'Trash',  icon: '🗑' },
];
let _emailActiveFolder = 'inbox';
let _emailActiveAccount = '';   // '' = all
let _emailCurrentThread = null; // ticket_number of open thread

function loadEmailData(win) {
  const content = win.el.querySelector('#email-content');
  if (!content) return;
  // V8 S-C505B1DB76: restore persisted folder selection.
  try {
    const saved = localStorage.getItem('fridays-email-folder');
    if (saved && _EMAIL_FOLDERS.some(f => f.key === saved)) _emailActiveFolder = saved;
  } catch (e) {}
  _renderEmailShell(win);
  _loadEmailInbox('');
}

function _renderEmailShell(win) {
  const root = win.el.querySelector('#email-content');
  if (!root) return;
  root.innerHTML = `
    <div style="display:flex;flex-direction:column;height:100%;gap:0;">

      <!-- Account tabs -->
      <div style="display:flex;gap:0;border-bottom:1px solid var(--border);flex-shrink:0;background:var(--card);">
        <button id="email-tab-all" onclick="_emailSetAccount('')"
          style="padding:8px 16px;font-size:12px;background:var(--accent);color:#fff;border:none;cursor:pointer;font-family:monospace;">All</button>
        ${_EMAIL_ACCOUNTS.map(a => `
          <button id="email-tab-${_escHtml(a)}" onclick="_emailSetAccount('${_escAttr(a)}')"
            style="padding:8px 14px;font-size:11px;background:transparent;color:var(--text-dim);border:none;border-right:1px solid var(--border);cursor:pointer;font-family:monospace;white-space:nowrap;"
            title="${_escAttr(a)}">${a.split('@')[0]}</button>`).join('')}
        <div style="flex:1;"></div>
        <button onclick="_emailRefreshLive()" title="Fetch live from Gmail"
          style="padding:8px 14px;font-size:11px;background:transparent;color:var(--text-dim);border:none;border-left:1px solid var(--border);cursor:pointer;">⟳ Live</button>
        <button onclick="_loadEmailStats()"
          style="padding:8px 14px;font-size:11px;background:transparent;color:var(--text-dim);border:none;border-left:1px solid var(--border);cursor:pointer;"><svg viewBox="0 0 16 16" width="11" height="11" fill="none" style="vertical-align:-1px;"><path d="M3 3h10v10H3z" stroke="currentColor" stroke-width="1.3"/><path d="M6 8h4M8 3v10" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg> Stats</button>
        <button id="email-manage-accounts" onclick="_emailOpenAccountManager()"
          title="Manage email accounts (add / remove / change)"
          style="padding:8px 14px;font-size:11px;background:transparent;color:var(--text-dim);border:none;border-left:1px solid var(--border);cursor:pointer;">⚙ Accounts</button>
        <button onclick="_emailToggleCompose()"
          style="padding:8px 14px;font-size:11px;background:var(--accent);color:#fff;border:none;border-left:1px solid var(--border);cursor:pointer;font-weight:700;">+ Compose</button>
      </div>

      <!-- Split: folder sidebar + list + thread -->
      <div style="display:flex;flex:1;min-height:0;">

        <!-- V8 S-C505B1DB76: Folder sidebar (Inbox / Sent / Drafts / Trash) -->
        <nav id="email-folder-nav" style="width:130px;flex-shrink:0;border-right:1px solid var(--border);padding:8px 0;background:var(--card);overflow-y:auto;">
          ${_EMAIL_FOLDERS.map(f => `
            <button id="email-folder-${f.key}" data-email-folder="${f.key}"
              onclick="_emailSetFolder('${f.key}')"
              style="display:flex;align-items:center;gap:8px;width:100%;padding:8px 12px;background:${f.key===_emailActiveFolder?'var(--accent)':'transparent'};color:${f.key===_emailActiveFolder?'#fff':'var(--text)'};border:none;border-left:3px solid ${f.key===_emailActiveFolder?'var(--accent)':'transparent'};cursor:pointer;font-size:12px;text-align:left;font-family:inherit;">
              <span style="font-size:14px;">${f.icon}</span>
              <span>${f.label}</span>
            </button>`).join('')}
        </nav>

        <!-- Email list -->
        <div id="email-list-panel" style="width:45%;min-width:220px;border-right:1px solid var(--border);overflow-y:auto;flex-shrink:0;">
          <div id="email-list-inner" style="padding:8px;">
            <div style="color:var(--text-dim);font-size:12px;padding:20px;text-align:center;">Loading…</div>
          </div>
        </div>

        <!-- Thread / detail panel -->
        <div id="email-thread-panel" style="flex:1;overflow-y:auto;padding:14px;">
          <div style="color:var(--text-dim);font-size:12px;text-align:center;padding:40px 20px;">
            Select an email to view agent handling
          </div>
        </div>

      </div>

      <!-- Compose drawer (hidden by default) -->
      <div id="email-compose-drawer" style="display:none;border-top:2px solid var(--accent);padding:14px;background:var(--card);flex-shrink:0;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
          <span style="font-size:12px;font-weight:700;">New Email</span>
          <button onclick="_emailToggleCompose()" style="background:none;border:none;color:var(--text-dim);cursor:pointer;font-size:14px;">&times;</button>
        </div>
        <div style="display:flex;flex-direction:column;gap:8px;">
          <div style="display:flex;gap:8px;align-items:center;">
            <label style="font-size:11px;color:var(--text-dim);min-width:50px;">From:</label>
            <select id="email-compose-from" style="flex:1;padding:5px 8px;background:var(--window-header);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:11px;">
              ${_EMAIL_ACCOUNTS.map(a => '<option value="'+a+'">'+a+'</option>').join('')}
            </select>
          </div>
          <div style="display:flex;gap:8px;align-items:center;">
            <label style="font-size:11px;color:var(--text-dim);min-width:50px;">To:</label>
            <input id="email-compose-to" type="email" placeholder="recipient@example.com" style="flex:1;padding:5px 8px;background:var(--window-header);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:11px;">
          </div>
          <div style="display:flex;gap:8px;align-items:center;">
            <label style="font-size:11px;color:var(--text-dim);min-width:50px;">Subject:</label>
            <input id="email-compose-subject" type="text" placeholder="Subject" style="flex:1;padding:5px 8px;background:var(--window-header);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:11px;">
          </div>
          <textarea id="email-compose-body" rows="6" placeholder="Message body…" style="padding:8px;background:var(--window-header);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:11px;resize:vertical;font-family:monospace;"></textarea>
          <div style="display:flex;gap:8px;justify-content:flex-end;">
            <button onclick="_emailToggleCompose()" style="padding:6px 14px;background:var(--card);border:1px solid var(--border);border-radius:4px;color:var(--text-dim);font-size:11px;cursor:pointer;">Cancel</button>
            <button id="email-compose-send-btn" onclick="_emailSendCompose()" style="padding:6px 14px;background:var(--accent);border:none;border-radius:4px;color:#fff;font-size:11px;cursor:pointer;font-weight:700;">Send</button>
          </div>
        </div>
      </div>
    </div>`;
}

function _emailSetAccount(account) {
  _emailActiveAccount = account;
  // Update tab styles
  document.querySelectorAll('[id^="email-tab-"]').forEach(btn => {
    btn.style.background = 'transparent';
    btn.style.color = 'var(--text-dim)';
  });
  const activeId = account ? `email-tab-${account}` : 'email-tab-all';
  const activeBtn = document.getElementById(activeId);
  if (activeBtn) { activeBtn.style.background = 'var(--accent)'; activeBtn.style.color = '#fff'; }
  _loadEmailInbox(account);
}

// V8 S-C505B1DB76: folder selector. Persists choice to localStorage so it
// survives reloads while the backend label sync is still under construction.
function _emailSetFolder(folder) {
  if (!_EMAIL_FOLDERS.some(f => f.key === folder)) return;
  _emailActiveFolder = folder;
  try { localStorage.setItem('fridays-email-folder', folder); } catch (e) {}
  document.querySelectorAll('[data-email-folder]').forEach(btn => {
    const active = btn.dataset.emailFolder === folder;
    btn.style.background = active ? 'var(--accent)' : 'transparent';
    btn.style.color = active ? '#fff' : 'var(--text)';
    btn.style.borderLeft = '3px solid ' + (active ? 'var(--accent)' : 'transparent');
  });
  _loadEmailInbox(_emailActiveAccount);
}

async function _loadEmailInbox(account) {
  const inner = document.getElementById('email-list-inner');
  if (!inner) return;
  inner.innerHTML = '<div style="color:var(--text-dim);font-size:12px;padding:20px;text-align:center;">Loading…</div>';

  const url = `/api/email/inbox?limit=80${account ? '&account='+encodeURIComponent(account) : ''}${_emailActiveFolder ? '&folder='+encodeURIComponent(_emailActiveFolder) : ''}`;
  try {
    const resp = await fetch(url);
    const data = await resp.json();
    const emails = data.emails || [];

    if (!emails.length) {
      inner.innerHTML = '<div style="color:var(--text-dim);font-size:12px;padding:20px;text-align:center;">No emails found</div>';
      return;
    }

    // Session 29.2 — multi-select toolbar + per-row checkbox.
    const toolbar = `<div id="email-bulk-toolbar" style="position:sticky;top:0;z-index:2;display:flex;align-items:center;gap:8px;padding:6px 8px;margin-bottom:6px;background:var(--bg);border-bottom:1px solid var(--border);font-size:11px;">
      <label style="display:flex;align-items:center;gap:5px;cursor:pointer;color:var(--text-dim);">
        <input type="checkbox" id="email-select-all" onclick="_emailToggleSelectAll(this)" style="cursor:pointer;"/>
        <span id="email-select-count">0 selected</span>
      </label>
      <span style="flex:1;"></span>
      <button onclick="_emailBulkClose()" title="Close tickets for selected emails"
        style="padding:3px 10px;font-size:10px;background:#f443361a;border:1px solid #f4433644;border-radius:3px;color:#f44336;cursor:pointer;">Close selected</button>
      <button onclick="_emailBulkClearSelection()" title="Clear selection"
        style="padding:3px 10px;font-size:10px;background:var(--card);border:1px solid var(--border);border-radius:3px;color:var(--text-dim);cursor:pointer;">Clear</button>
    </div>`;

    const rows = emails.map(e => {
      const st        = e.status || 'queued';
      const stColor   = st === 'processing' ? '#2196f3' : st === 'done' || st === 'closed' ? '#4caf50' : st === 'abandoned' ? '#888' : '#ffa500';
      const hasTicket = e.ticket_number;
      const from      = (e.from_addr || '').replace(/agent:/, '').slice(0, 40);
      const subj      = (e.subject || '(no subject)').slice(0, 60);
      const ts        = (e.created_at || '').slice(0, 16);
      const acct      = (e.swarm_account || '').split('@')[0];
      const ticketAttr = hasTicket ? _escAttr(e.ticket_number) : '';
      return `<div class="email-row" data-ticket="${ticketAttr}" data-qid="${_escAttr(e.id || '')}"
        style="display:flex;align-items:stretch;border-radius:4px;margin-bottom:6px;border-left:3px solid ${stColor};background:var(--card);transition:background 0.15s;overflow:hidden;">
        <label style="display:flex;align-items:center;padding:0 8px;cursor:pointer;border-right:1px solid var(--border);" onclick="event.stopPropagation();">
          <input type="checkbox" class="email-row-check" data-ticket="${ticketAttr}" onchange="_emailOnRowCheck()" ${hasTicket ? '' : 'disabled title="No ticket"'} style="cursor:pointer;"/>
        </label>
        <div style="flex:1;padding:10px;cursor:pointer;" onclick="_emailOpenThread('${ticketAttr}', '${_escAttr(e.id || '')}')">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:6px;">
            <span style="font-size:10px;font-family:monospace;color:${stColor};font-weight:700;">${_escHtml(st.toUpperCase())}</span>
            ${hasTicket ? `<span style="font-size:9px;color:#2196f3;font-family:monospace;">${_escHtml(e.ticket_number)}</span>` : ''}
            <span style="font-size:9px;color:var(--text-dim);">${_escHtml(acct)}</span>
          </div>
          <div style="font-size:11px;font-weight:600;margin:3px 0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_escHtml(subj)}</div>
          <div style="font-size:10px;color:var(--text-dim);">${_escHtml(from)} · ${_escHtml(ts)}</div>
        </div>
      </div>`;
    }).join('');

    inner.innerHTML = toolbar + rows;

    // Hover highlight
    inner.querySelectorAll('.email-row').forEach(el => {
      el.addEventListener('mouseenter', () => el.style.background = 'var(--hover, #ffffff10)');
      el.addEventListener('mouseleave', () => el.style.background = 'var(--card)');
    });
    _emailOnRowCheck();
  } catch (e) {
    inner.innerHTML = `<div style="color:#f44;font-size:12px;padding:12px;">Error: ${_escHtml(e.message)}</div>`;
  }
}

// ── Session 29.2 — multi-select helpers ───────────────────────────────────
function _emailCheckedTickets() {
  return Array.from(document.querySelectorAll('.email-row-check:checked'))
    .map(cb => cb.getAttribute('data-ticket'))
    .filter(Boolean);
}

function _emailOnRowCheck() {
  const count = _emailCheckedTickets().length;
  const total = document.querySelectorAll('.email-row-check:not(:disabled)').length;
  const countEl = document.getElementById('email-select-count');
  if (countEl) countEl.textContent = `${count} selected`;
  const allBox = document.getElementById('email-select-all');
  if (allBox) allBox.checked = count > 0 && count === total;
}

function _emailToggleSelectAll(cb) {
  const checked = !!cb.checked;
  document.querySelectorAll('.email-row-check:not(:disabled)').forEach(box => { box.checked = checked; });
  _emailOnRowCheck();
}

function _emailBulkClearSelection() {
  document.querySelectorAll('.email-row-check:checked').forEach(box => { box.checked = false; });
  const allBox = document.getElementById('email-select-all');
  if (allBox) allBox.checked = false;
  _emailOnRowCheck();
}

async function _emailBulkClose() {
  const tickets = _emailCheckedTickets();
  if (!tickets.length) { if (typeof showToast === 'function') showToast('No emails selected', 'info'); return; }
  if (!confirm(`Close ${tickets.length} ticket${tickets.length === 1 ? '' : 's'}?`)) return;
  let ok = 0, fail = 0;
  for (const tn of tickets) {
    try {
      const r = await fetch(`/api/tickets/${encodeURIComponent(tn)}/close`, { method: 'POST' });
      const data = await r.json().catch(() => ({}));
      if (r.ok && data.ok !== false) ok++; else fail++;
    } catch (_) { fail++; }
  }
  if (typeof showToast === 'function') {
    showToast(`Closed ${ok}${fail ? ` · ${fail} failed` : ''}`, fail ? 'error' : 'success');
  }
  _loadEmailInbox(_emailActiveAccount);
}

async function _emailOpenThread(ticketNumber, queueId) {
  const panel = document.getElementById('email-thread-panel');
  if (!panel) return;

  if (!ticketNumber) {
    panel.innerHTML = `<div style="color:var(--text-dim);font-size:12px;padding:20px;">
      <div style="font-weight:700;margin-bottom:8px;">Queue entry #${_escHtml(queueId)}</div>
      <div>No ticket created for this email yet.</div>
    </div>`;
    return;
  }

  panel.innerHTML = '<div style="color:var(--text-dim);font-size:12px;padding:20px;text-align:center;">Loading thread…</div>';
  _emailCurrentThread = ticketNumber;

  try {
    const resp = await fetch(`/api/email/thread/${encodeURIComponent(ticketNumber)}`);
    const data = await resp.json();
    if (!data.ok) { panel.innerHTML = `<div style="color:#f44;padding:20px;">${_escHtml(data.error)}</div>`; return; }

    const t = data.ticket || {};
    const notes = data.notes || [];
    const activity = data.activity || [];
    const stColor = t.status === 'closed' ? '#4caf50' : t.status === 'open' ? '#ffa500' : '#888';
    const tnJs = JSON.stringify(ticketNumber);

    panel.innerHTML = `
      <!-- Header -->
      <div style="border-bottom:1px solid var(--border);padding-bottom:12px;margin-bottom:14px;">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">
          <div>
            <div style="font-size:13px;font-weight:700;margin-bottom:4px;">${_escHtml(t.question || '(no subject)').slice(0, 120)}</div>
            <div style="font-size:11px;color:var(--text-dim);">From: ${_escHtml(t.sender_email||'—')} · ${_escHtml((t.created_at||'').slice(0,16))}</div>
          </div>
          <span style="padding:3px 10px;border-radius:12px;background:${stColor}22;color:${stColor};font-size:11px;font-weight:700;white-space:nowrap;border:1px solid ${stColor}44;">${_escHtml(t.status||'?')}</span>
        </div>
        <div style="display:flex;gap:6px;margin-top:8px;flex-wrap:wrap;">
          <button onclick="sendTicketToChat(${tnJs}, ${JSON.stringify((t.question||'').slice(0,80))})"
            style="padding:4px 12px;font-size:11px;background:#2196f31a;border:1px solid #2196f344;border-radius:4px;color:#2196f3;cursor:pointer;"><svg viewBox="0 0 16 16" width="11" height="11" fill="none" style="vertical-align:-1px;"><path d="M2.5 3h11a1 1 0 011 1v6a1 1 0 01-1 1h-3l-3 2.5V11h-5a1 1 0 01-1-1V4a1 1 0 011-1z" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg> Open in Chat</button>
          <button onclick="openTicketDetail(${tnJs})"
            style="padding:4px 12px;font-size:11px;background:var(--card);border:1px solid var(--border);border-radius:4px;color:var(--text-dim);cursor:pointer;"><svg viewBox="0 0 16 16" width="10" height="10" fill="none" style="vertical-align:-1px;"><rect x="2" y="3" width="12" height="10" rx="1.5" stroke="currentColor" stroke-width="1.3"/><path d="M2 7h12" stroke="currentColor" stroke-width="1.3"/></svg> Full Ticket</button>
          ${t.status !== 'closed'
            ? `<button onclick="closeTicketFromModal(${tnJs})"
                style="padding:4px 12px;font-size:11px;background:#f443361a;border:1px solid #f4433644;border-radius:4px;color:#f44336;cursor:pointer;">Close</button>`
            : ''}
        </div>
      </div>

      <!-- Agent audit trail -->
      <div style="margin-bottom:14px;">
        <div style="font-size:11px;font-weight:700;color:var(--text-dim);text-transform:uppercase;margin-bottom:8px;">Agent Handling</div>
        ${_emailAuditTimeline(t, notes, activity)}
      </div>

      <!-- Final answer -->
      ${t.final_answer ? `
      <div style="margin-bottom:14px;">
        <div style="font-size:11px;font-weight:700;color:var(--text-dim);text-transform:uppercase;margin-bottom:6px;">Final Answer</div>
        <div style="background:var(--card);padding:12px;border-radius:4px;font-size:12px;white-space:pre-wrap;max-height:300px;overflow-y:auto;line-height:1.5;">${_escHtml(t.final_answer)}</div>
      </div>` : ''}

      <!-- Notes -->
      ${notes.length ? `
      <div>
        <div style="font-size:11px;font-weight:700;color:var(--text-dim);text-transform:uppercase;margin-bottom:6px;">Notes (${notes.length})</div>
        ${notes.map(n => `<div style="padding:8px 10px;background:var(--card);border-radius:4px;border-left:2px solid var(--accent);margin-bottom:5px;font-size:12px;">
          <div style="font-size:10px;color:var(--text-dim);margin-bottom:3px;">${_escHtml(n.agent||'agent')} · ${_escHtml((n.created_at||'').slice(0,16))}</div>
          <div style="white-space:pre-wrap;">${_escHtml(n.content||'')}</div>
        </div>`).join('')}
      </div>` : ''}`;
  } catch (err) {
    panel.innerHTML = `<div style="color:#f44;padding:20px;">Error loading thread: ${_escHtml(err.message)}</div>`;
  }
}

function _emailAuditTimeline(ticket, notes, activity) {
  const steps = [];

  // Extract key pipeline events from activity log
  const piped = activity.filter(a => ['listener','email'].includes(a.service) ||
    (a.detail && a.detail.includes(ticket.ticket_number || '??')));

  if (ticket.created_at) {
    steps.push({ ts: ticket.created_at, agent: 'Listener', color: '#2196f3', label: 'Email received & queued' });
  }
  if (ticket.tags) {
    steps.push({ ts: ticket.created_at, agent: 'LLaMA', color: '#9c27b0', label: `Tags: ${ticket.tags.slice(0, 60)}` });
  }
  if (ticket.gemma_routing) {
    steps.push({ ts: ticket.created_at, agent: 'Gemma', color: '#ff9800', label: `Routing: ${ticket.gemma_routing.slice(0, 80)}` });
  }
  if (ticket.duck_result) {
    const ok = !(ticket.duck_result || '').toLowerCase().includes('fail');
    steps.push({ ts: ticket.updated_at || ticket.created_at, agent: 'Duck', color: ok ? '#4caf50' : '#f44336', label: ticket.duck_result.slice(0, 80) });
  }
  notes.forEach(n => {
    steps.push({ ts: n.created_at, agent: n.agent || 'agent', color: '#607d8b', label: (n.content || '').slice(0, 80) });
  });
  if (ticket.status === 'closed' || ticket.final_answer) {
    steps.push({ ts: ticket.updated_at || ticket.closed_at || '', agent: 'Librarian', color: '#4caf50', label: 'Ticket closed — answer delivered' });
  }

  if (!steps.length) return '<div style="color:var(--text-dim);font-size:11px;font-style:italic;">No audit events recorded</div>';

  return `<div style="border-left:2px solid var(--border);padding-left:12px;margin-left:6px;">
    ${steps.map(s => `<div style="position:relative;margin-bottom:10px;">
      <div style="position:absolute;left:-17px;top:3px;width:8px;height:8px;border-radius:50%;background:${s.color};"></div>
      <div style="font-size:10px;color:var(--text-dim);">${_escHtml((s.ts||'').slice(0,16))} · <span style="color:${s.color};font-weight:700;">${_escHtml(s.agent)}</span></div>
      <div style="font-size:11px;color:var(--text);">${_escHtml(s.label)}</div>
    </div>`).join('')}
  </div>`;
}

async function _emailRefreshLive() {
  const inner = document.getElementById('email-list-inner');
  if (!inner) return;
  inner.innerHTML = '<div style="color:var(--text-dim);font-size:12px;padding:20px;text-align:center;">Fetching from Gmail…</div>';
  try {
    const resp = await fetch(`/api/email/live?limit=20${_emailActiveAccount ? '&account='+encodeURIComponent(_emailActiveAccount) : ''}`);
    const data = await resp.json();
    if (!data.ok) { showToast(data.error || 'Live fetch failed', 'error'); _loadEmailInbox(_emailActiveAccount); return; }

    const msgs = data.messages || [];
    if (!msgs.length) { inner.innerHTML = '<div style="color:var(--text-dim);font-size:12px;padding:20px;text-align:center;">Inbox empty</div>'; return; }

    inner.innerHTML = `<div style="font-size:10px;color:var(--text-dim);margin-bottom:8px;">Live from Gmail — ${msgs.length} messages</div>` +
      msgs.filter(m => !m.error).map(m => `
        <div style="padding:10px;border-radius:4px;margin-bottom:6px;background:var(--card);border-left:3px solid #2196f3;">
          <div style="font-size:11px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_escHtml((m.subject||'(no subject)').slice(0,60))}</div>
          <div style="font-size:10px;color:var(--text-dim);">${_escHtml((m.from||'').slice(0,40))} · ${_escHtml(m.date||'')}</div>
          <div style="font-size:9px;color:#888;font-family:monospace;">${_escHtml(m.account)}</div>
        </div>`).join('') +
      msgs.filter(m => m.error).map(m => `<div style="font-size:11px;color:#f44;padding:6px;"><svg viewBox="0 0 16 16" width="11" height="11" fill="none" style="vertical-align:-1px;"><path d="M8 2l6.5 11H1.5z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M8 7v2.5M8 11.5v0" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg> ${_escHtml(m.account)}: ${_escHtml(m.error)}</div>`).join('');
  } catch (e) {
    showToast('Live fetch error: ' + e.message, 'error');
    _loadEmailInbox(_emailActiveAccount);
  }
}

async function _loadEmailStats() {
  const panel = document.getElementById('email-thread-panel');
  if (!panel) return;
  panel.innerHTML = '<div style="color:var(--text-dim);font-size:12px;padding:20px;text-align:center;">Loading stats…</div>';
  try {
    const resp = await fetch('/api/email/stats');
    const data = await resp.json();
    const byStatus = data.by_status || {};
    const activity = data.recent_activity || [];

    panel.innerHTML = `
      <div style="padding:4px 0;">
        <div style="font-size:13px;font-weight:700;margin-bottom:14px;"><svg viewBox="0 0 16 16" width="13" height="13" fill="none" style="vertical-align:-2px;"><path d="M3 3h10v10H3z" stroke="currentColor" stroke-width="1.3"/><path d="M6 8h4M8 3v10" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg> Email Stats</div>

        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:8px;margin-bottom:16px;">
          <div style="background:var(--card);border-radius:6px;padding:12px;text-align:center;">
            <div style="font-size:22px;font-weight:700;">${data.total_emails||0}</div>
            <div style="font-size:10px;color:var(--text-dim);">Total Received</div>
          </div>
          ${Object.entries(byStatus).map(([s,c]) => `
            <div style="background:var(--card);border-radius:6px;padding:12px;text-align:center;">
              <div style="font-size:20px;font-weight:700;">${c}</div>
              <div style="font-size:10px;color:var(--text-dim);">${_escHtml(s)}</div>
            </div>`).join('')}
        </div>

        <div style="font-size:11px;font-weight:700;color:var(--text-dim);text-transform:uppercase;margin-bottom:8px;">Accounts</div>
        ${(data.accounts||[]).map(a => `<div style="font-size:12px;padding:4px 0;font-family:monospace;"><svg viewBox="0 0 16 16" width="11" height="11" fill="none" style="vertical-align:-1px;"><rect x="2" y="3.5" width="12" height="9" rx="1.5" stroke="currentColor" stroke-width="1.3"/><path d="M2 5.5l6 4 6-4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg> ${_escHtml(a)}</div>`).join('')}

        ${activity.length ? `
        <div style="margin-top:16px;">
          <div style="font-size:11px;font-weight:700;color:var(--text-dim);text-transform:uppercase;margin-bottom:8px;">Recent Activity</div>
          ${activity.map(a => `<div style="font-size:11px;padding:4px 0;border-bottom:1px solid var(--border);">
            <span style="color:var(--text-dim);">${_escHtml((a.created_at||'').slice(0,16))}</span>
            <span style="margin:0 6px;color:#888;">[${_escHtml(a.service||'')}]</span>
            <span>${_escHtml((a.detail||'').slice(0,80))}</span>
          </div>`).join('')}
        </div>` : ''}
      </div>`;
  } catch (e) {
    panel.innerHTML = `<div style="color:#f44;padding:20px;">Stats error: ${_escHtml(e.message)}</div>`;
  }
}

// ── Compose (Tier 3.1) ────────────────────────────────────────────────────────
function _emailToggleCompose() {
  const drawer = document.getElementById('email-compose-drawer');
  if (!drawer) return;
  drawer.style.display = drawer.style.display === 'none' ? 'block' : 'none';
  if (drawer.style.display === 'block' && !drawer.dataset.kbBound) {
    drawer.dataset.kbBound = '1';
    // Ctrl+Enter (or Cmd+Enter on Mac) anywhere in the compose drawer = send.
    drawer.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        _emailSendCompose();
      }
    });
  }
}

async function _emailSendCompose() {
  const from_account = document.getElementById('email-compose-from')?.value || '';
  const to = (document.getElementById('email-compose-to')?.value || '').trim();
  const subject = (document.getElementById('email-compose-subject')?.value || '').trim();
  const body = (document.getElementById('email-compose-body')?.value || '').trim();

  if (!to || !subject) {
    showToast('To and Subject are required', 'error');
    return;
  }

  const btn = document.getElementById('email-compose-send-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Sending…'; }

  try {
    const resp = await fetch('/api/email/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ from_account, to, subject, body }),
    });
    const data = await resp.json();
    if (!resp.ok || data.ok === false) throw new Error(data.error || `HTTP ${resp.status}`);
    showToast('Email sent', 'success');
    _emailToggleCompose();
    // Clear fields
    const toEl = document.getElementById('email-compose-to');
    const subjEl = document.getElementById('email-compose-subject');
    const bodyEl = document.getElementById('email-compose-body');
    if (toEl) toEl.value = '';
    if (subjEl) subjEl.value = '';
    if (bodyEl) bodyEl.value = '';
  } catch (e) {
    showToast(`Send failed: ${e.message}`, 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Send'; }
  }
}

// V7C-A09: Account management modal. Read-only discovery for now (backend
// account list lives in utils/config.py + swarm-sniffles.service credentials).
// Lets the user see which accounts are active, flag one for removal, and
// request an addition via a Settings deep-link. No silent writes.
function _emailOpenAccountManager() {
  let modal = document.getElementById('email-accounts-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'email-accounts-modal';
    modal.style.cssText = 'position:fixed;inset:0;z-index:99990;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.55);backdrop-filter:blur(4px);';
    modal.addEventListener('mousedown', (ev) => { if (ev.target === modal) modal.remove(); });
    document.body.appendChild(modal);
  }
  // MD-FEATURE-1260A5EFA63E — pull live from /api/email/accounts so the
  // modal reflects both config-managed and runtime accounts. Remove + add
  // now persist to the runtime registry; the in-memory _EMAIL_ACCOUNTS list
  // is updated so the inbox tab strip refreshes immediately.
  modal.innerHTML = `
    <div style="background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px 16px 12px;width:min(560px, 94vw);display:flex;flex-direction:column;gap:10px;box-shadow:0 14px 44px rgba(0,0,0,0.45);">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px;">
        <div>
          <div style="font-size:13px;font-weight:700;">Email accounts</div>
          <div style="font-size:10px;color:var(--text-dim);margin-top:2px;">Config-managed accounts come from <code>utils/config.py</code> and need a host edit to remove. Runtime accounts you add here persist to the swarm DB and the Email tile picks them up immediately. IMAP/SMTP credentials still live with sniffles.</div>
        </div>
        <button onclick="document.getElementById('email-accounts-modal')?.remove()"
          style="background:none;border:1px solid var(--border);border-radius:6px;color:var(--text-dim);cursor:pointer;width:24px;height:24px;flex:0 0 auto;line-height:1;">✕</button>
      </div>
      <div id="email-accounts-rows" style="display:flex;flex-direction:column;gap:6px;min-height:60px;">
        <div style="font-size:10px;color:var(--text-dim);text-align:center;padding:14px;">Loading accounts…</div>
      </div>
      <div style="display:flex;flex-direction:column;gap:6px;border-top:1px solid var(--border);padding-top:8px;">
        <div style="font-size:10px;color:var(--text-dim);font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">Add a runtime account</div>
        <div style="display:flex;gap:6px;align-items:center;">
          <input id="email-accounts-add-input" type="email" placeholder="user@example.com"
            style="flex:1;padding:6px 9px;background:var(--window-header);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:11px;outline:none;">
          <button onclick="_emailAddAccountSubmit()"
            style="background:var(--accent);color:#000;border:none;border-radius:4px;padding:6px 14px;font-size:11px;font-weight:700;cursor:pointer;">Add</button>
        </div>
        <div style="font-size:9px;color:var(--text-dim);">After adding, restart sniffles to start fetching mail for the new account.</div>
      </div>
    </div>`;
  modal.style.display = 'flex';
  _emailRefreshAccountsList();
}

function _emailRefreshAccountsList() {
  const host = document.getElementById('email-accounts-rows');
  if (!host) return;
  fetch('/api/email/accounts').then(r => r.json()).then(d => {
    const list = (d && Array.isArray(d.accounts)) ? d.accounts : [];
    if (!list.length) {
      host.innerHTML = '<div style="font-size:10px;color:var(--text-dim);text-align:center;padding:14px;">No accounts configured.</div>';
      return;
    }
    host.innerHTML = list.map(a => {
      const safe = _escAttr(a.email || '');
      const isConfig = (a.source === 'config');
      const removeBtn = isConfig
        ? `<span title="Edit utils/config.py to remove" style="font-size:10px;color:var(--text-dim);padding:4px 8px;">config-managed</span>`
        : `<button onclick="_emailRemoveAccountReal('${safe}')" title="Remove from runtime registry"
            style="background:none;border:1px solid var(--border);border-radius:4px;color:var(--danger);padding:4px 8px;font-size:10px;cursor:pointer;">Remove</button>`;
      const note = a.note ? `<div style="font-size:9px;color:var(--text-dim);margin-top:2px;">${_escHtml(a.note)}</div>` : '';
      const tag = isConfig
        ? `<span style="font-size:9px;color:#7ad6c8;font-weight:700;">CONFIG</span>`
        : `<span style="font-size:9px;color:#d8a032;font-weight:700;">RUNTIME</span>`;
      return `
        <div style="display:flex;align-items:center;gap:8px;padding:8px 10px;border:1px solid var(--border);border-radius:6px;background:var(--card);">
          <div style="flex:1;min-width:0;">
            <div style="display:flex;align-items:center;gap:6px;">
              ${tag}
              <span style="font-size:12px;color:var(--text);font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${_escHtml(a.email || '')}</span>
            </div>
            ${note}
          </div>
          <button onclick="_emailOpenAccountPrefs('${safe}')" title="Per-account prefs (SMTP-from, signature, default folder, auto-file rules)"
            style="background:transparent;border:1px solid var(--border);border-radius:4px;color:var(--text-dim);padding:4px 8px;font-size:10px;cursor:pointer;">⚙ Prefs</button>
          ${removeBtn}
        </div>`;
    }).join('');
  }).catch(() => {
    host.innerHTML = '<div style="font-size:10px;color:#ef4444;">Could not load accounts.</div>';
  });
}

function _emailAddAccountSubmit() {
  const input = document.getElementById('email-accounts-add-input');
  const email = (input && input.value || '').trim().toLowerCase();
  if (!email || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
    if (typeof showToast === 'function') showToast('Enter a valid email address', 'error');
    return;
  }
  fetch('/api/email/accounts', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, note: 'added via Email tile' }),
  }).then(r => r.json()).then(d => {
    if (d && d.ok) {
      if (typeof showToast === 'function') showToast(`Added ${email}`, 'success');
      if (input) input.value = '';
      _emailMergeRuntimeAccount(email);
      _emailRefreshAccountsList();
    } else {
      if (typeof showToast === 'function') showToast(d && d.error || 'Add failed', 'error');
    }
  }).catch(() => {
    if (typeof showToast === 'function') showToast('Add failed (network)', 'error');
  });
}

function _emailRemoveAccountReal(email) {
  if (!email) return;
  if (typeof confirm === 'function' && !confirm(`Remove ${email} from the runtime registry?`)) return;
  fetch(`/api/email/accounts/${encodeURIComponent(email)}`, { method: 'DELETE' })
    .then(r => r.json()).then(d => {
      if (d && d.ok) {
        if (typeof showToast === 'function') showToast(`Removed ${email}`, 'success');
        const idx = _EMAIL_ACCOUNTS.indexOf(email);
        if (idx >= 0) _EMAIL_ACCOUNTS.splice(idx, 1);
        _emailRefreshAccountsList();
      } else {
        if (typeof showToast === 'function') showToast(d && d.error || 'Remove failed', 'error');
      }
    }).catch(() => {
      if (typeof showToast === 'function') showToast('Remove failed (network)', 'error');
    });
}

function _emailMergeRuntimeAccount(email) {
  if (!email || _EMAIL_ACCOUNTS.indexOf(email) >= 0) return;
  _EMAIL_ACCOUNTS.push(email);
}

function _emailRequestAccountAdd() { _emailOpenAccountManager(); }
function _emailRequestAccountRemove(addr) { _emailRemoveAccountReal(addr); }

window._emailOpenAccountManager = _emailOpenAccountManager;
window._emailRefreshAccountsList = _emailRefreshAccountsList;
window._emailAddAccountSubmit = _emailAddAccountSubmit;
window._emailRemoveAccountReal = _emailRemoveAccountReal;
window._emailRequestAccountAdd = _emailRequestAccountAdd;
window._emailRequestAccountRemove = _emailRequestAccountRemove;

// MD-FEATURE-95057B9D58B8 — per-account prefs modal (SMTP-from, default
// folder, signature, auto-file rules). Backed by /api/email/accounts/<e>/prefs.
function _emailOpenAccountPrefs(email) {
  if (!email) return;
  let modal = document.getElementById('email-account-prefs-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'email-account-prefs-modal';
    modal.style.cssText = 'position:fixed;inset:0;z-index:99991;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.55);backdrop-filter:blur(4px);';
    modal.addEventListener('mousedown', (ev) => { if (ev.target === modal) modal.remove(); });
    document.body.appendChild(modal);
  }
  modal.innerHTML = `
    <div style="background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px 16px 12px;width:min(560px, 94vw);max-height:88vh;overflow-y:auto;display:flex;flex-direction:column;gap:10px;box-shadow:0 14px 44px rgba(0,0,0,0.45);">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px;">
        <div>
          <div style="font-size:13px;font-weight:700;">Account preferences · ${_escHtml(email)}</div>
          <div style="font-size:10px;color:var(--text-dim);margin-top:2px;">SMTP-from override, default folder, signature, and auto-file rules. These drive compose defaults and inbox routing — IMAP/SMTP credentials still belong to sniffles.</div>
        </div>
        <button onclick="document.getElementById('email-account-prefs-modal')?.remove()"
          style="background:none;border:1px solid var(--border);border-radius:6px;color:var(--text-dim);cursor:pointer;width:24px;height:24px;flex:0 0 auto;line-height:1;">✕</button>
      </div>
      <div id="email-account-prefs-body" style="font-size:11px;color:var(--text-dim);">Loading…</div>
    </div>`;
  modal.style.display = 'flex';
  fetch(`/api/email/accounts/${encodeURIComponent(email)}/prefs`).then(r => r.json()).then(d => {
    const p = (d && d.prefs) || {};
    _emailRenderAccountPrefsForm(email, p);
  }).catch(() => {
    const body = document.getElementById('email-account-prefs-body');
    if (body) body.innerHTML = '<div style="color:#ef4444;">Could not load prefs.</div>';
  });
}

function _emailRenderAccountPrefsForm(email, prefs) {
  const body = document.getElementById('email-account-prefs-body');
  if (!body) return;
  const folders = ['inbox', 'sent', 'drafts', 'trash'];
  const rules = (prefs.auto_file_rules || []).map((r, i) => `
    <div style="display:flex;gap:6px;align-items:center;" data-rule-row="${i}">
      <input class="email-prefs-rule-match" data-i="${i}" type="text" placeholder="match (e.g. subject:.*invoice)" value="${_escAttr(r.match || '')}"
        style="flex:1;padding:5px 8px;background:var(--window-header);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:11px;outline:none;">
      <select class="email-prefs-rule-folder" data-i="${i}"
        style="padding:5px 8px;background:var(--window-header);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:11px;outline:none;">
        ${folders.map(f => `<option value="${f}" ${r.folder === f ? 'selected' : ''}>${f}</option>`).join('')}
      </select>
      <button onclick="_emailRemoveRuleRow(${i})" style="background:none;border:1px solid var(--border);border-radius:4px;color:var(--danger);padding:5px 8px;font-size:10px;cursor:pointer;">✕</button>
    </div>`).join('');
  body.innerHTML = `
    <div style="display:flex;flex-direction:column;gap:10px;">
      <label style="display:flex;flex-direction:column;gap:4px;">
        <span style="font-size:10px;color:var(--text-dim);font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">SMTP-from override</span>
        <input id="email-prefs-smtp-from" type="email" placeholder="${_escAttr(email)}" value="${_escAttr(prefs.smtp_from || '')}"
          style="padding:6px 9px;background:var(--window-header);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:11px;outline:none;">
        <span style="font-size:9px;color:var(--text-dim);">Leave blank to send From: the account address itself.</span>
      </label>
      <label style="display:flex;flex-direction:column;gap:4px;">
        <span style="font-size:10px;color:var(--text-dim);font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">Default folder</span>
        <select id="email-prefs-default-folder"
          style="padding:6px 9px;background:var(--window-header);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:11px;outline:none;">
          ${folders.map(f => `<option value="${f}" ${prefs.default_folder === f ? 'selected' : ''}>${f}</option>`).join('')}
        </select>
      </label>
      <label style="display:flex;flex-direction:column;gap:4px;">
        <span style="font-size:10px;color:var(--text-dim);font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">Signature</span>
        <textarea id="email-prefs-signature" rows="4"
          style="padding:7px 9px;background:var(--window-header);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:11px;outline:none;font-family:inherit;resize:vertical;"
          placeholder="-- &#10;Seven · sevenpotato9@gmail.com">${_escHtml(prefs.signature || '')}</textarea>
      </label>
      <div style="display:flex;flex-direction:column;gap:4px;">
        <span style="font-size:10px;color:var(--text-dim);font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">Auto-file rules</span>
        <div id="email-prefs-rules" style="display:flex;flex-direction:column;gap:5px;">
          ${rules || '<div style="font-size:10px;color:var(--text-dim);opacity:0.7;">No rules. Add one below.</div>'}
        </div>
        <button onclick="_emailAddRuleRow()" style="align-self:flex-start;background:transparent;border:1px solid var(--border);color:var(--text);border-radius:4px;padding:4px 10px;font-size:10px;cursor:pointer;">+ Add rule</button>
        <span style="font-size:9px;color:var(--text-dim);">Match strings are matched as regex against subject/from/body — see KC manual for full syntax.</span>
      </div>
      <div style="display:flex;justify-content:flex-end;gap:6px;border-top:1px solid var(--border);padding-top:10px;">
        <button onclick="document.getElementById('email-account-prefs-modal')?.remove()"
          style="background:transparent;border:1px solid var(--border);color:var(--text-dim);border-radius:4px;padding:6px 12px;font-size:11px;cursor:pointer;">Cancel</button>
        <button onclick="_emailSaveAccountPrefs('${_escAttr(email)}')"
          style="background:var(--accent);color:#000;border:none;border-radius:4px;padding:6px 14px;font-size:11px;font-weight:700;cursor:pointer;">Save</button>
      </div>
    </div>`;
  // stash current rules array on the modal for add/remove operations
  document.getElementById('email-account-prefs-modal')._rules = (prefs.auto_file_rules || []).slice();
}

function _emailAddRuleRow() {
  const modal = document.getElementById('email-account-prefs-modal');
  if (!modal) return;
  const rules = (modal._rules || []).slice();
  rules.push({ match: '', folder: 'inbox' });
  modal._rules = rules;
  // Snapshot current input values then re-render
  _emailSnapshotRules(modal);
  _emailRenderRulesOnly(modal);
}

function _emailRemoveRuleRow(i) {
  const modal = document.getElementById('email-account-prefs-modal');
  if (!modal) return;
  _emailSnapshotRules(modal);
  const rules = (modal._rules || []).slice();
  rules.splice(i, 1);
  modal._rules = rules;
  _emailRenderRulesOnly(modal);
}

function _emailSnapshotRules(modal) {
  const matches = modal.querySelectorAll('.email-prefs-rule-match');
  const folders = modal.querySelectorAll('.email-prefs-rule-folder');
  const out = [];
  matches.forEach((m, i) => {
    out.push({ match: (m.value || '').trim(), folder: (folders[i] && folders[i].value) || 'inbox' });
  });
  modal._rules = out;
}

function _emailRenderRulesOnly(modal) {
  const host = modal.querySelector('#email-prefs-rules');
  if (!host) return;
  const folders = ['inbox', 'sent', 'drafts', 'trash'];
  const rules = modal._rules || [];
  if (!rules.length) {
    host.innerHTML = '<div style="font-size:10px;color:var(--text-dim);opacity:0.7;">No rules. Add one below.</div>';
    return;
  }
  host.innerHTML = rules.map((r, i) => `
    <div style="display:flex;gap:6px;align-items:center;" data-rule-row="${i}">
      <input class="email-prefs-rule-match" data-i="${i}" type="text" placeholder="match (e.g. subject:.*invoice)" value="${_escAttr(r.match || '')}"
        style="flex:1;padding:5px 8px;background:var(--window-header);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:11px;outline:none;">
      <select class="email-prefs-rule-folder" data-i="${i}"
        style="padding:5px 8px;background:var(--window-header);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:11px;outline:none;">
        ${folders.map(f => `<option value="${f}" ${r.folder === f ? 'selected' : ''}>${f}</option>`).join('')}
      </select>
      <button onclick="_emailRemoveRuleRow(${i})" style="background:none;border:1px solid var(--border);border-radius:4px;color:var(--danger);padding:5px 8px;font-size:10px;cursor:pointer;">✕</button>
    </div>`).join('');
}

function _emailSaveAccountPrefs(email) {
  const modal = document.getElementById('email-account-prefs-modal');
  if (!modal) return;
  _emailSnapshotRules(modal);
  const smtpFrom = (document.getElementById('email-prefs-smtp-from') || {}).value || '';
  const defaultFolder = (document.getElementById('email-prefs-default-folder') || {}).value || 'inbox';
  const signature = (document.getElementById('email-prefs-signature') || {}).value || '';
  const rules = (modal._rules || []).filter(r => r && r.match);
  fetch(`/api/email/accounts/${encodeURIComponent(email)}/prefs`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      smtp_from: smtpFrom.trim(),
      default_folder: defaultFolder,
      signature: signature,
      auto_file_rules: rules,
    }),
  }).then(r => r.json()).then(d => {
    if (d && d.ok) {
      if (typeof showToast === 'function') showToast('Account prefs saved', 'success');
      modal.remove();
    } else {
      if (typeof showToast === 'function') showToast(d && d.error || 'Save failed', 'error');
    }
  }).catch(() => {
    if (typeof showToast === 'function') showToast('Save failed (network)', 'error');
  });
}

window._emailOpenAccountPrefs = _emailOpenAccountPrefs;
window._emailAddRuleRow = _emailAddRuleRow;
window._emailRemoveRuleRow = _emailRemoveRuleRow;
window._emailSaveAccountPrefs = _emailSaveAccountPrefs;
