/* Practice 181 (owner 20 Nov 2026: "the thinking bubbles disappear completely after the thought is done ... this needs to be saved"):
   under each APEX reply in main chat, a closed "How APEX got here (N steps)" list - the steps HB recorded while APEX worked. */
(function () {
  var done = new Set(), busy = false;
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function apexBubbles() {
    return Array.prototype.filter.call(document.querySelectorAll('#home-chat-messages .hc-bubble.hc-agent[data-message-id]'), function (el) {
      var m = el._chatMessage || {};
      return String(m.sender || m.from_agent || '').toLowerCase() === 'apex' && !done.has(el.dataset.messageId);
    });
  }
  function took(t) { t = Math.max(0, Math.round(Number(t) || 0)); return t >= 60 ? Math.floor(t / 60) + ' min ' + (t % 60) + ' s' : t + ' s'; }
  function attach(el, steps) {
    if (el.querySelector('.hb-turn-steps')) return;
    var d = document.createElement('details');
    d.className = 'hb-turn-steps';
    d.style.cssText = 'margin:0 0 8px;padding:6px 10px;border-radius:10px;border:1px solid var(--border,rgba(255,255,255,.12));background:rgba(16,24,30,.45);backdrop-filter:blur(10px);font-size:12px;color:var(--text-dim,#a8bfb7);';
    d.innerHTML = '<summary style="cursor:pointer;user-select:none;font-weight:600;color:var(--accent,#10e8a4);">💭 Thinking · How APEX got here (' + steps.length + ' steps, ' +
      took(steps[steps.length - 1].t) + ')</summary><ol style="margin:6px 0 2px 18px;padding:0;line-height:1.5;">' +
      steps.map(function (s) { return '<li><span style="opacity:.6;font-variant-numeric:tabular-nums;">' + took(s.t) + '</span> ' + esc(s.text) + '</li>'; }).join('') +
      '</ol>';
    var host = el.querySelector('.hc-bubble-body') || el;
    host.prepend ? host.prepend(d) : host.insertBefore(d, host.firstChild);
  }
  function tick() {
    if (busy || document.hidden) return;
    var els = apexBubbles();
    if (!els.length) return;
    busy = true;
    var ids = els.map(function (el) { return el.dataset.messageId; });
    fetch('/api/peer/v1/hb/turn-steps?ids=' + ids.join(','), { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data || !data.ok) return;
        els.forEach(function (el) {
          var steps = data.steps[el.dataset.messageId];
          if (steps && steps.length) attach(el, steps);
          done.add(el.dataset.messageId);
        });
      }).catch(function () {}).finally(function () { busy = false; });
  }
  setInterval(tick, 2500);
  tick();
})();
