/* Daily grounding (owner 14 Nov 2026): the sundial title shows the real current day name - an anchor to stay in the present.
   The full date is in its tooltip. Refreshed every minute, so it is right after midnight too. */
(function () {
  function showDay() {
    var title = document.getElementById('sundial-title');
    if (!title) return;
    var now = new Date();
    title.textContent = now.toLocaleDateString('en-AU', { weekday: 'long' });
    title.title = now.toLocaleDateString('en-AU', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', showDay); else showDay();
  setInterval(showDay, 60000);
})();
