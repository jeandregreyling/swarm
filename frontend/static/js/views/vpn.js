// VPN / Tailscale status view
// Shows network status, self node, and peer list.

function loadVpnData(win) {
  const root = win.el.querySelector('#vpn-content');
  if (!root) return;
  root.innerHTML = '<div style="color:var(--text-dim);font-size:12px;padding:20px;text-align:center;">Loading VPN status…</div>';

  fetch('/api/vpn/status')
    .then(r => r.json())
    .then(data => {
      if (!data.ok) {
        root.innerHTML = `<div style="padding:20px;">
          <div style="color:#f77;font-size:12px;margin-bottom:8px;">VPN status unavailable</div>
          <div style="color:var(--text-dim);font-size:11px;">${_escHtml(data.error || 'Unknown error')}</div>
        </div>`;
        return;
      }

      const self = data.self || {};
      const peers = data.peers || [];
      const stateColor = data.backend_state === 'Running' ? '#4caf50' : '#ffa500';

      root.innerHTML = `
        <div style="padding:14px;display:flex;flex-direction:column;gap:14px;">
          <!-- Self node + summary -->
          <div style="display:flex;gap:14px;flex-wrap:wrap;">
            <div style="flex:1;min-width:200px;padding:12px;background:var(--card);border:1px solid var(--border);border-radius:6px;">
              <div style="font-size:11px;font-weight:700;color:var(--text-dim);text-transform:uppercase;margin-bottom:8px;">This Node</div>
              <div style="font-size:13px;font-weight:700;margin-bottom:4px;">${_escHtml(self.hostname)}</div>
              <div style="font-size:11px;color:var(--text-dim);font-family:monospace;">${_escHtml(self.ip)}</div>
              <div style="font-size:10px;color:var(--text-dim);margin-top:4px;">${_escHtml(self.dns_name)}</div>
              <div style="font-size:10px;color:var(--text-dim);">OS: ${_escHtml(self.os)}</div>
            </div>
            <div style="flex:1;min-width:200px;padding:12px;background:var(--card);border:1px solid var(--border);border-radius:6px;">
              <div style="font-size:11px;font-weight:700;color:var(--text-dim);text-transform:uppercase;margin-bottom:8px;">Network</div>
              <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;">
                <span style="width:8px;height:8px;border-radius:50%;background:${stateColor};display:inline-block;"></span>
                <span style="font-size:12px;font-weight:600;">${_escHtml(data.backend_state)}</span>
              </div>
              <div style="font-size:11px;color:var(--text-dim);">Tailnet: ${_escHtml(data.tailnet_name)}</div>
              <div style="font-size:11px;color:var(--text-dim);">Peers: ${data.online_count} online / ${data.peer_count} total</div>
            </div>
          </div>

          <!-- Peer list -->
          <div>
            <div style="font-size:11px;font-weight:700;color:var(--text-dim);text-transform:uppercase;margin-bottom:8px;">Peers</div>
            <div style="display:flex;flex-direction:column;gap:6px;">
              ${peers.length ? peers.map(p => {
                const onColor = p.online ? '#4caf50' : '#888';
                return `<div style="display:flex;align-items:center;gap:10px;padding:8px 10px;background:var(--card);border:1px solid var(--border);border-radius:4px;">
                  <span style="width:8px;height:8px;border-radius:50%;background:${onColor};flex-shrink:0;"></span>
                  <div style="flex:1;min-width:0;">
                    <div style="font-size:11px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_escHtml(p.hostname)}</div>
                    <div style="font-size:10px;color:var(--text-dim);font-family:monospace;">${_escHtml(p.ip)}</div>
                  </div>
                  <div style="font-size:10px;color:var(--text-dim);text-align:right;flex-shrink:0;">
                    <div>${_escHtml(p.os)}</div>
                    <div>${p.online ? 'online' : 'offline'}${p.relay ? ' via ' + _escHtml(p.relay) : ''}</div>
                  </div>
                </div>`;
              }).join('') : '<div style="color:var(--text-dim);font-size:12px;">No peers found</div>'}
            </div>
          </div>
        </div>`;
    })
    .catch(e => {
      root.innerHTML = `<div style="color:#f77;font-size:12px;padding:20px;">VPN error: ${_escHtml(e.message)}</div>`;
    });
}
