// Tickets view — ticket list, detail
// Extracted from terminal_base.html

function loadTicketsData(win) {
  const content = win.el.querySelector('#tickets-content');
  if (!content) return;
  
  fetch('/api/tickets')
    .then(r => r.json())
    .then(data => {
      const tickets = Array.isArray(data) ? data : (data.tickets || []);
      if (tickets.length > 0) {
        content.innerHTML = tickets.slice(0, 30).map(t => {
          const num   = t.number || t.ticket_number || '?';
          const title = (t.title || t.question || 'Untitled').slice(0, 100);
          const ts    = t.timestamp || t.created_at || '';
          const st    = t.status || 'unknown';
          const stColor = st === 'open' ? '#4caf50' : st === 'in_progress' ? '#ffa500' : '#888';
          const stBg    = st === 'open' ? 'rgba(76,175,80,0.15)' : st === 'in_progress' ? 'rgba(255,165,0,0.15)' : 'rgba(136,136,136,0.15)';
          return `<div class="ticket-row" style="background:var(--card);padding:12px;border-radius:4px;margin-bottom:8px;border-left:3px solid ${stColor};cursor:pointer;" onclick="openTicketDetail(${JSON.stringify(num)})">
            <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
              <strong style="font-size:12px;font-family:monospace;">${_escHtml(num)}</strong>
              <span style="font-size:10px;padding:2px 7px;border-radius:3px;background:${stBg};color:${stColor};font-weight:600;">${_escHtml(st)}</span>
            </div>
            <div style="margin-top:5px;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_escHtml(title)}</div>
            <div style="margin-top:3px;font-size:10px;color:var(--text-dim);">${_escHtml(ts.slice(0,16))}</div>
          </div>`;
        }).join('');
      } else {
        content.innerHTML = '<div style="padding:20px;color:var(--text-dim);text-align:center;font-size:12px;">No tickets found.</div>';
      }

      // Wire search input after content is rendered (guard against double-registration)
      const searchInput = win.el.querySelector('#ticket-search');
      if (searchInput && !searchInput.dataset.bound) {
        searchInput.dataset.bound = '1';
        searchInput.addEventListener('input', (e) => {
          const q = e.target.value.toLowerCase();
          content.querySelectorAll('.ticket-row').forEach(el => {
            el.style.display = el.textContent.toLowerCase().includes(q) ? 'block' : 'none';
          });
        });
      }
    })
    .catch(e => { content.innerHTML = `<div style="padding:20px;color:#f77;font-size:12px;">Error loading tickets: ${e.message}</div>`; });
}

