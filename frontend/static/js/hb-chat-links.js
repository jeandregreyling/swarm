/* Practice 137 (owner 17 Nov 2026): SAP note links in answers (HB's Knowledge Centre copy at /kc/..., or the online original) open in a new tab, so main chat
   stays where it is. Any web link in a chat message does the same. */
(function () {
  document.addEventListener('click', function (e) {
    var a = e.target && e.target.closest ? e.target.closest('a[href]') : null;
    if (!a || !a.closest('.chat-bubble, #home-chat-messages, #chat-messages')) return;
    var href = a.getAttribute('href') || '';
    if (/^https?:\/\//i.test(href) || href.indexOf('/kc/') === 0) {
      e.preventDefault();
      window.open(href, '_blank', 'noopener');
    }
  }, true);
})();
