/* Live activity (owner 14 Nov 2026): plain text under the thinking bubble - who is running, the stage, each tool call and its
   result, and how long it has run. Reads /api/peer/v1/hb/activity every 3 s while the page is visible; hidden when nothing runs. */
(function () {
  var box = null;
  function ensure() {
    if (box && document.body.contains(box)) return box;
    box = document.createElement('pre');
    box.id = 'hb-live-activity';
    box.style.cssText = 'margin:4px 12px 8px;padding:6px 10px;font:11.5px/1.45 ui-monospace,monospace;white-space:pre-wrap;' +
      'color:var(--text-dim,#888);border-left:2px solid var(--accent,#0f9);max-height:160px;overflow:auto;display:none;';
    return box;
  }
  function place(node) {
    var bubbles = document.querySelectorAll('.chat-bubble[data-pending-job-id]');
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
    pill.textContent = 'HB now: ' + (lines.length ? String(lines[0]).replace(/\s+/g, ' ') : 'idle');
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
      node.textContent = data.lines.join('\n');
      place(node);
      node.style.display = 'block';
    }).catch(function () {});
  }
  setInterval(tick, 3000);
  tick();
})();
