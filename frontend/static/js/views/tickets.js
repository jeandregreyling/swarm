// Tickets view — ticket list, detail, cross-referencing
// Phase 1 rewrite — 15 April 2026

function loadTicketsData(win) {
  const content = win.el.querySelector('#tickets-content');
  if (!content) return;

  content.innerHTML = '<div style="padding:20px;color:var(--text-dim);text-align:center;font-size:11px;">Loading tickets…</div>';

  fetch('/api/tickets')
    .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(data => {
      const tickets = Array.isArray(data) ? data : (data.tickets || []);
      if (!tickets.length) {
        content.innerHTML = '<div style="padding:20px;color:var(--text-dim);text-align:center;font-size:12px;">No tickets found.</div>';
        return;
      }

      content.innerHTML = tickets.slice(0, 50).map(t => {
        const num   = t.ticket_number || t.number || '?';
        const title = (t.question || t.title || 'Untitled').slice(0, 100);
        const ts    = t.created_at || t.timestamp || '';
        const st    = t.status || 'unknown';
        const ch    = t.channel || '';
        const convId = t.conv_id || '';
        const notes = t.note_count || 0;
        const stColor = st === 'open' ? '#4caf50' : st === 'in_progress' ? '#ffa500' : st === 'closed' ? '#888' : '#666';
        const stBg    = stColor + '22';
        const chBadge = ch ? `<span style="font-size:9px;padding:1px 5px;border-radius:3px;background:var(--bg);color:var(--text-dim);margin-left:4px;">${_escHtml(ch.toUpperCase())}</span>` : '';
        const notesBadge = notes > 0 ? `<span style="font-size:9px;color:var(--text-dim);"><svg viewBox="0 0 16 16" width="9" height="9" fill="none" style="vertical-align:-1px;"><path d="M3 2h7l3 3v8a1 1 0 01-1 1H3a1 1 0 01-1-1V3a1 1 0 011-1z" stroke="currentColor" stroke-width="1.3"/><path d="M5 8h6M5 11h4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>${notes}</span>` : '';
        const numJs = JSON.stringify(num);
        return `<div class="ticket-row" data-ticket="${_escHtml(num)}" data-conv="${_escHtml(String(convId))}" style="background:var(--card);padding:12px;border-radius:4px;margin-bottom:6px;border-left:3px solid ${stColor};cursor:pointer;" onclick='openTicketDetail(${numJs})'>
          <div style="display:flex;justify-content:space-between;align-items:center;gap:6px;">
            <strong style="font-size:11px;font-family:monospace;">${_escHtml(num)}</strong>
            <div style="display:flex;align-items:center;gap:4px;">
              ${notesBadge}
              ${chBadge}
              <span style="font-size:10px;padding:2px 7px;border-radius:3px;background:${stBg};color:${stColor};font-weight:600;">${_escHtml(st)}</span>
            </div>
          </div>
          <div style="margin-top:5px;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_escHtml(title)}</div>
          <div style="margin-top:3px;font-size:10px;color:var(--text-dim);display:flex;justify-content:space-between;align-items:center;">
            <span>${_escHtml((ts || '').slice(0, 16))}</span>
            ${convId ? `<span style="font-size:9px;opacity:0.6;">conv:${_escHtml(String(convId))}</span>` : ''}
          </div>
        </div>`;
      }).join('');

      // Wire search input (guard against double-registration)
      const searchInput = win.el.querySelector('#ticket-search');
      if (searchInput && !searchInput.dataset.bound) {
        searchInput.dataset.bound = '1';
        searchInput.addEventListener('input', e => {
          const q = e.target.value.toLowerCase();
          content.querySelectorAll('.ticket-row').forEach(el => {
            el.style.display = el.textContent.toLowerCase().includes(q) ? '' : 'none';
          });
        });
      }
    })
    .catch(e => {
      content.innerHTML = `<div style="padding:20px;color:#f77;font-size:12px;">Error loading tickets: ${_escHtml(e.message)}</div>`;
    });
}

function deleteTicket(ticketId) {
  fetch('/api/tickets/' + encodeURIComponent(ticketId), { method: 'DELETE' })
    .then(r => {
      if (r.ok) {
        const win = (window._fridaysWindows || []).find(w => w.id === 'tickets');
        if (win) loadTicketsData(win);
      }
    })
    .catch(e => console.error('Error deleting ticket:', e));
}

function deleteTicketWithConfirm(ticketNumber, btnEl) {
  if (btnEl.dataset.confirming === '1') {
    // Second click — actually delete
    btnEl.disabled = true;
    btnEl.textContent = 'Deleting…';
    fetch('/api/tickets/' + encodeURIComponent(ticketNumber), { method: 'DELETE' })
      .then(r => {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        // Close modal, refresh list, toast
        const modal = document.getElementById('ticket-detail-modal');
        if (modal) modal.classList.remove('open');
        const win = (window._fridaysWindows || []).find(w => w.id === 'tickets');
        if (win) loadTicketsData(win);
        if (typeof showToast === 'function') showToast(ticketNumber + ' deleted', 'success');
      })
      .catch(e => {
        if (typeof showToast === 'function') showToast('Delete failed: ' + e.message, 'error');
        btnEl.disabled = false;
        btnEl.dataset.confirming = '';
        btnEl.innerHTML = '<svg viewBox="0 0 16 16" width="11" height="11" fill="none" style="vertical-align:-1px;"><path d="M5 4V3a1 1 0 011-1h4a1 1 0 011 1v1M3 4h10M4.5 4l.5 9a1 1 0 001 1h4a1 1 0 001-1l.5-9" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg> Delete';
        btnEl.style.background = '#f443361a';
        btnEl.style.borderColor = '#f4433644';
        btnEl.style.color = '#f44336';
      });
  } else {
    // First click — switch to confirm state
    btnEl.dataset.confirming = '1';
    btnEl.innerHTML = 'Confirm Delete?';
    btnEl.style.background = '#f44336';
    btnEl.style.borderColor = '#f44336';
    btnEl.style.color = '#fff';
    // Auto-revert after 3s
    setTimeout(() => {
      if (btnEl.dataset.confirming === '1') {
        btnEl.dataset.confirming = '';
        btnEl.innerHTML = '<svg viewBox="0 0 16 16" width="11" height="11" fill="none" style="vertical-align:-1px;"><path d="M5 4V3a1 1 0 011-1h4a1 1 0 011 1v1M3 4h10M4.5 4l.5 9a1 1 0 001 1h4a1 1 0 001-1l.5-9" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg> Delete';
        btnEl.style.background = '#f443361a';
        btnEl.style.borderColor = '#f4433644';
        btnEl.style.color = '#f44336';
      }
    }, 3000);
  }
}

function filterTicketsByStatus(status) {
  const content = document.getElementById('tickets-content');
  if (!content) return;
  content.querySelectorAll('.ticket-row').forEach(el => {
    if (!status) { el.style.display = ''; return; }
    const text = el.textContent.toLowerCase();
    el.style.display = text.includes(status) ? '' : 'none';
  });
}

