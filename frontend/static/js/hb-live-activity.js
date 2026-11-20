/* Live activity (owner 14 Nov 2026): plain text under the thinking bubble - who is running, the stage, each tool call and its
   result, and how long it has run. Reads /api/peer/v1/hb/activity every 3 s while the page is visible; hidden when nothing runs. */
(function () {
  var box = null;
  function ensure() {
    if (box && document.body.contains(box)) return box;
    box = document.createElement('pre');
    box.id = 'hb-live-activity';
    // Practice 177 (owner 20 Nov 2026: "a very thin line at the bottom of the chat ... the top of the first sentence cut in half"): the chat
    // list is a flex column, so this scrollable box was shrunk to a sliver. It no longer shrinks, grows with its text up to 40% of the
    // screen, and is plain readable text.
    box.style.cssText = 'flex:0 0 auto;min-height:min-content;margin:4px 12px 8px;padding:8px 12px;font:12.5px/1.5 ui-monospace,monospace;' +
      'white-space:pre-wrap;word-break:break-word;color:var(--text,#ddd);background:var(--surface-2,rgba(127,127,127,.08));' +
      'border-left:3px solid var(--accent,#0f9);border-radius:4px;max-height:40vh;overflow:auto;display:none;';
    return box;
  }
  function place(node) {
    var bubbles = document.querySelectorAll('.chat-bubble[data-pending-job-id], .hc-bubble[data-pending-job-id]');   // Practice 177: main chat too
    var last = bubbles.length ? bubbles[bubbles.length - 1] : null;
    if (last && last.parentNode) { if (last.nextSibling !== node) last.parentNode.insertBefore(node, last.nextSibling); return; }
    var host = document.getElementById('chat-messages') || document.getElementById('home-chat-messages');
    if (host && node.parentNode !== host) host.appendChild(node);
  }
  // Practice 126 (owner 17 Nov 2026): "I can't really see what HB is busy with at the moment, I just hear the fans". The box below sits at
  // the end of the message list (out of sight when scrolled up, gone for a moment on every redraw) and shows nothing at all when idle.
  // The chat bar now always says what HB is doing: the first line of the activity, or "idle"; hover for every line.
  function now(data) {
    var bar = document.querySelector('#home-chat-bar .home-chat-bar-left');
    if (!bar) return;
    var pill = document.getElementById('hb-now');
    if (!pill) {
      pill = document.createElement('span');
      pill.id = 'hb-now';
      pill.style.cssText = 'margin-left:10px;font-size:11px;color:var(--text-dim,#888);white-space:nowrap;overflow:hidden;' +
        'text-overflow:ellipsis;max-width:46vw;display:inline-block;vertical-align:middle;';
      bar.appendChild(pill);
    }
    var lines = (data && data.running && data.lines) ? data.lines : [];
    var last = data && data.last, idle = 'idle';
    if (!lines.length && last && last.at) {     // Practice 179: "idle since 16:50 - last: APEX, Practice 178 ..."
      var t = new Date(last.at * 1000);
      idle = 'idle since ' + String(t.getHours()).padStart(2, '0') + ':' + String(t.getMinutes()).padStart(2, '0') +
        ' - last: ' + String(last.agent || '').toUpperCase() + ', ' + String(last.title || '');
    }
    pill.textContent = 'HB now: ' + (lines.length ? String(lines[0]).replace(/\s+/g, ' ') : idle);
    pill.title = lines.length ? lines.join('\n') : 'Nothing is running: no APEX turn, no Fred turn, no background job.';
    pill.style.color = lines.length ? 'var(--accent,#0f9)' : 'var(--text-dim,#888)';
  }
  function tick() {
    if (document.hidden) return;
    fetch('/api/peer/v1/hb/activity', { credentials: 'same-origin' }).then(function (r) { return r.ok ? r.json() : null; }).then(function (data) {
      var node = ensure();
      now(data);                                          // Practice 126
      // Practice 164: the shared /hb/activity answer carries the live text in 'lines' (and 'live'); 'running' is the work list
      if (!data || !data.live || !data.lines || !data.lines.length) { node.style.display = 'none'; return; }
      var host = node.parentNode;
      var atBottom = !host || host.scrollHeight - host.scrollTop - host.clientHeight < 80;   // Practice 177: follow only if JD is at the bottom
      var text = data.lines.join('\n');
      if (node.textContent !== text) node.textContent = text;
      place(node);
      node.style.display = 'block';
      host = node.parentNode;
      if (host && atBottom) host.scrollTop = host.scrollHeight;
    }).catch(function () {});
  }
  setInterval(tick, 3000);
  tick();
})();
