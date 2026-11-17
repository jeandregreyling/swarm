/* Network bar (Practice 132, owner 17 Nov 2026): "the network status call and select and control".
   Main chat's bar shows the connection HB is on ("Net: enp5s0 wired · ORBI16 Wi-Fi"); a click opens a panel with every connection
   (up or down, IPv4/IPv6, main route, last measured speed, mobile data), which one HB uses for downloads (auto or JD's choice), a
   speed test, mobile-data marks, the saved Wi-Fi networks in range (connect), and disconnect for a side connection. Every action is
   JD's click, owner only (/api/network/action); HB never disconnects the main route or the VPN. Same as /net in the chat. */
(function () {
  var pill = null, panel = null, open = false, last = null, note = '';
  function css() {
    if (document.getElementById('hb-net-style')) return;
    var s = document.createElement('style');
    s.id = 'hb-net-style';
    s.textContent =
      '.hb-net-pill{margin-left:10px;font-size:11px;color:var(--text-dim);background:none;border:1px solid var(--border);border-radius:10px;' +
      'padding:1px 8px;cursor:pointer;white-space:nowrap;max-width:30vw;overflow:hidden;text-overflow:ellipsis;vertical-align:middle}' +
      '.hb-net-pill:hover{color:var(--accent);border-color:var(--accent)}' +
      '.hb-net-panel{position:fixed;z-index:60;max-width:min(560px,92vw);max-height:70vh;overflow:auto;background:var(--card);color:var(--text);' +
      'border:1px solid var(--border);border-radius:10px;padding:10px 12px;font-size:12px;line-height:1.5}' +
      '.hb-net-panel h4{margin:8px 0 4px;font-size:12px;color:var(--accent)}' +
      '.hb-net-row{display:flex;flex-wrap:wrap;gap:6px;align-items:center;padding:4px 0;border-bottom:1px solid var(--border)}' +
      '.hb-net-row .what{flex:1 1 240px}.hb-net-dim{color:var(--text-dim)}' +
      '.hb-net-panel button{font-size:11px;background:none;color:var(--text);border:1px solid var(--border);border-radius:8px;padding:1px 8px;cursor:pointer}' +
      '.hb-net-panel button:hover{border-color:var(--accent);color:var(--accent)}' +
      '.hb-net-panel button.on{background:var(--accent);color:var(--text-on-accent);border-color:var(--accent)}' +
      '.hb-net-note{margin-top:6px;color:var(--text-dim);white-space:pre-wrap}';
    document.head.appendChild(s);
  }
  function ensurePill() {
    var bar = document.querySelector('#home-chat-bar .home-chat-bar-left');
    if (!bar) return null;
    pill = document.getElementById('hb-net');
    if (!pill) {
      css();
      pill = document.createElement('button');
      pill.id = 'hb-net'; pill.type = 'button'; pill.className = 'hb-net-pill';
      pill.addEventListener('click', toggle);
      bar.appendChild(pill);
    }
    return pill;
  }
  function name(c) { return c.name + ' ' + (c.label || c.kind); }
  function summary(d) {
    var up = (d.links || []).filter(function (c) { return c.up && c.kind !== 'vpn'; });
    return 'Net: ' + (up.length ? up.map(name).join(' · ') : 'offline') + (d.choice ? ' (downloads: ' + d.choice + ')' : '');
  }
  function button(text, fn, on) {
    var b = document.createElement('button');
    b.type = 'button'; b.textContent = text; if (on) b.className = 'on';
    b.addEventListener('click', function (e) { e.stopPropagation(); fn(); });
    return b;
  }
  function row(parent, text, dim) {
    var r = document.createElement('div'); r.className = 'hb-net-row';
    var w = document.createElement('span'); w.className = 'what' + (dim ? ' hb-net-dim' : ''); w.textContent = text;
    r.appendChild(w); parent.appendChild(r); return r;
  }
  function render(d) {
    if (!panel) return;
    panel.textContent = '';
    var h = document.createElement('h4'); h.textContent = 'Connections'; panel.appendChild(h);
    (d.links || []).forEach(function (c) {
      var bits = [name(c), c.up ? 'up' : 'down'];
      if (c.ipv4) bits.push(c.ipv6 ? 'IPv4+IPv6' : 'IPv4'); else if (c.ipv6) bits.push('IPv6 only');
      if (c.name === d.main) bits.push('main route'); else if (c['default']) bits.push('backup route');
      if (c.speed != null) bits.push(c.speed + ' MB/s');
      if (c.mobile) bits.push('mobile data');
      var r = row(panel, bits.join(' · '), !c.up);
      if (!c.up || c.kind === 'vpn') return;
      r.appendChild(button(d.choice === c.name ? 'Downloads use this' : 'Use for downloads', function () { act('use', d.choice === c.name ? 'auto' : c.name); }, d.choice === c.name));
      r.appendChild(button('Speed test', function () { note = 'Measuring ' + c.name + ' (about 10 s)…'; render(d); act('bench', c.name); }));
      r.appendChild(button(c.mobile ? 'Mobile data ✓' : 'Mobile data?', function () { act('mobile', c.name, !c.mobile); }, c.mobile));
      if (c.name !== d.main) r.appendChild(button('Disconnect', function () {
        if (window.confirm('Disconnect ' + name(c) + '?')) act('disconnect', c.name);
      }));
    });
    var b = d.budget || {};
    row(panel, 'Mobile data: ' + (b.set ? b.left_gb + ' GB left, HB used ' + b.used_gb + ' GB, floor ' + b.floor_gb + ' GB' + (b.warn ? ' - over 80% used' : '')
      : 'no figure set (/net budget <GB left> <floor GB>)') + ' · downloads: ' + (d.choice || 'HB picks (auto)'), true);
    var wifi = (d.wifi || []).filter(function (w) { return w.in_range || w.active; });
    if (wifi.length) {
      h = document.createElement('h4'); h.textContent = 'Saved Wi-Fi in range'; panel.appendChild(h);
      wifi.forEach(function (w) {
        var r = row(panel, w.network + ' · signal ' + w.signal + '%' + (w.active ? ' · connected' : ''));
        if (!w.active) r.appendChild(button('Connect', function () { note = 'Connecting to ' + w.network + '…'; render(d); act('connect', w.name); }));
      });
    }
    if (note) { var n = document.createElement('div'); n.className = 'hb-net-note'; n.textContent = note; panel.appendChild(n); }
  }
  function place() {
    var r = pill.getBoundingClientRect();
    panel.style.left = Math.max(8, Math.min(r.left, window.innerWidth - panel.offsetWidth - 8)) + 'px';
    panel.style.bottom = Math.max(8, window.innerHeight - r.top + 6) + 'px';
  }
  function toggle(e) {
    if (e) e.stopPropagation();
    open = !open;
    if (!open) { if (panel) panel.remove(); panel = null; return; }
    panel = document.createElement('div'); panel.className = 'hb-net-panel'; panel.id = 'hb-net-panel';
    panel.addEventListener('click', function (ev) { ev.stopPropagation(); });
    document.body.appendChild(panel);
    if (last) render(last);
    place();
    load(true);
  }
  document.addEventListener('click', function () { if (open) toggle(); });
  function act(action, target, on) {
    fetch('/api/network/action', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: action, name: target, on: !!on }) })
      .then(function (r) { return r.json(); })
      .then(function (out) { note = out.text || out.error || ''; load(true); })
      .catch(function () { note = 'HB did not answer.'; if (last) render(last); });
  }
  function load(withWifi) {
    if (!ensurePill()) return;
    fetch('/api/network' + (withWifi ? '?wifi=1' : ''), { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d) { pill.style.display = 'none'; return; }
        last = d; pill.style.display = '';
        pill.textContent = summary(d);
        pill.title = 'Click for connections, speed tests, mobile data and Wi-Fi';
        if (open) { render(d); place(); }
      }).catch(function () {});
  }
  setInterval(function () { if (!document.hidden) load(open); }, 30000);
  load(false);
})();
