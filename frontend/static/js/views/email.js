// Email tile — inbox view for sevenpotato9@gmail.com and ninepotato7@gmail.com
// Shows swarm-processed emails with agent handling audit trail.

const _EMAIL_ACCOUNTS = ['sevenpotato9@gmail.com', 'ninepotato7@gmail.com'];
let _emailActiveAccount = '';   // '' = all
let _emailCurrentThread = null; // ticket_number of open thread

function loadEmailData(win) {
  const content = win.el.querySelector('#email-content');
  if (!content) return;
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
          style="padding:8px 14px;font-size:11px;background:transparent;color:var(--text-dim);border:none;border-left:1px solid var(--border);cursor:pointer;">📊 Stats</button>
      </div>

      <!-- Split: list + thread -->
      <div style="display:flex;flex:1;min-height:0;">

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

async function _loadEmailInbox(account) {
  const inner = document.getElementById('email-list-inner');
  if (!inner) return;
  inner.innerHTML = '<div style="color:var(--text-dim);font-size:12px;padding:20px;text-align:center;">Loading…</div>';

  const url = `/api/email/inbox?limit=80${account ? '&account='+encodeURIComponent(account) : ''}`;
  try {
    const resp = await fetch(url);
    const data = await resp.json();
    const emails = data.emails || [];

    if (!emails.length) {
      inner.innerHTML = '<div style="color:var(--text-dim);font-size:12px;padding:20px;text-align:center;">No emails found</div>';
      return;
    }

    inner.innerHTML = emails.map(e => {
      const st        = e.status || 'queued';
      const stColor   = st === 'processing' ? '#2196f3' : st === 'done' || st === 'closed' ? '#4caf50' : st === 'abandoned' ? '#888' : '#ffa500';
      const hasTicket = e.ticket_number;
      const from      = (e.from_addr || '').replace(/agent:/, '').slice(0, 40);
      const subj      = (e.subject || '(no subject)').slice(0, 60);
      const ts        = (e.created_at || '').slice(0, 16);
      const acct      = (e.swarm_account || '').split('@')[0];
      return `<div class="email-row" onclick="_emailOpenThread('${_escAttr(e.ticket_number || '')}', '${_escAttr(e.id || '')}')"
        style="padding:10px;border-radius:4px;margin-bottom:6px;cursor:pointer;border-left:3px solid ${stColor};background:var(--card);transition:background 0.15s;">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:6px;">
          <span style="font-size:10px;font-family:monospace;color:${stColor};font-weight:700;">${_escHtml(st.toUpperCase())}</span>
          ${hasTicket ? `<span style="font-size:9px;color:#2196f3;font-family:monospace;">${_escHtml(e.ticket_number)}</span>` : ''}
          <span style="font-size:9px;color:var(--text-dim);">${_escHtml(acct)}</span>
        </div>
        <div style="font-size:11px;font-weight:600;margin:3px 0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_escHtml(subj)}</div>
        <div style="font-size:10px;color:var(--text-dim);">${_escHtml(from)} · ${_escHtml(ts)}</div>
      </div>`;
    }).join('');

    // Hover highlight
    inner.querySelectorAll('.email-row').forEach(el => {
      el.addEventListener('mouseenter', () => el.style.background = 'var(--hover, #ffffff10)');
      el.addEventListener('mouseleave', () => el.style.background = 'var(--card)');
    });
  } catch (e) {
    inner.innerHTML = `<div style="color:#f44;font-size:12px;padding:12px;">Error: ${_escHtml(e.message)}</div>`;
  }
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
            style="padding:4px 12px;font-size:11px;background:#2196f31a;border:1px solid #2196f344;border-radius:4px;color:#2196f3;cursor:pointer;">💬 Open in Chat</button>
          <button onclick="openTicketDetail(${tnJs})"
            style="padding:4px 12px;font-size:11px;background:var(--card);border:1px solid var(--border);border-radius:4px;color:var(--text-dim);cursor:pointer;">🎫 Full Ticket</button>
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
      msgs.filter(m => m.error).map(m => `<div style="font-size:11px;color:#f44;padding:6px;">⚠️ ${_escHtml(m.account)}: ${_escHtml(m.error)}</div>`).join('');
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
        <div style="font-size:13px;font-weight:700;margin-bottom:14px;">📊 Email Stats</div>

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
        ${(data.accounts||[]).map(a => `<div style="font-size:12px;padding:4px 0;font-family:monospace;">📧 ${_escHtml(a)}</div>`).join('')}

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
