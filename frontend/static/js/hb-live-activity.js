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
  function tick() {
    if (document.hidden) return;
    fetch('/api/peer/v1/hb/activity', { credentials: 'same-origin' }).then(function (r) { return r.ok ? r.json() : null; }).then(function (data) {
      var node = ensure();
      if (!data || !data.running) { node.style.display = 'none'; return; }
      node.textContent = data.lines.join('\n');
      place(node);
      node.style.display = 'block';
    }).catch(function () {});
  }
  setInterval(tick, 3000);
  tick();
})();
