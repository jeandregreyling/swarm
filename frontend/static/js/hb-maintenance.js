// Owner 13 Nov: when HB is taken down for a restart or a foundation change, show "Maintenance in progress"
// (with the reason when one was announced) instead of a sign-in screen. The session is kept. When HB is back:
// if new code was loaded, reload the page (only when the message box is empty; otherwise offer a Reload button).
(function () {
  let shown = false, timer = null, wasDown = false;
  const loadedVersion = String(window.HB_ASSET_VERSION || '');

  function overlay() {
    let el = document.getElementById('hb-maintenance');
    if (el) return el;
    el = document.createElement('div');
    el.id = 'hb-maintenance';
    el.setAttribute('role', 'status');
    el.setAttribute('aria-live', 'polite');
    el.style.cssText = 'position:fixed;inset:0;z-index:100000;display:none;align-items:center;justify-content:center;'
      + 'background:color-mix(in srgb, var(--bg, #0b1220) 88%, transparent);backdrop-filter:blur(3px);font-family:inherit;';
    el.innerHTML = '<div style="max-width:440px;padding:26px 30px;border-radius:14px;border:1px solid var(--border,#334);'
      + 'background:var(--card,#141c2b);color:var(--text,#e8eef8);text-align:center;box-shadow:0 18px 50px rgba(0,0,0,.45)">'
      + '<div style="margin-bottom:6px;color:var(--accent,#6aa9ff)" aria-hidden="true">' + ((window.HBIcons && window.HBIcons.svg) ? window.HBIcons.svg('sleeping') : '<span data-hb-icon="sleeping"></span>') + '</div>'
      + '<div style="font-size:17px;font-weight:700;margin-bottom:6px">Maintenance in progress</div>'
      + '<div data-hb-maint-reason style="font-size:13px;opacity:.85;margin-bottom:10px"></div>'
      + '<div style="font-size:12px;opacity:.7">HB is being updated. You stay signed in and your draft is kept; this page comes back by itself.</div>'
      + '<div data-hb-maint-reload style="display:none;margin-top:14px"><button type="button" style="padding:7px 14px;border-radius:8px;'
      + 'border:1px solid var(--accent,#4a8);background:var(--accent,#4a8);color:#000;font-weight:700;cursor:pointer">Reload to load the update</button></div>'
      + '</div>';
    el.querySelector('[data-hb-maint-reload] button').addEventListener('click', () => location.reload());
    (document.body || document.documentElement).appendChild(el);
    return el;
  }

  function draftEmpty() {
    const box = document.getElementById('home-chat-input') || document.getElementById('chat-input');
    return !box || !String(box.value || '').trim();
  }

  function show(reason) {
    const el = overlay();
    // Owner 14 Nov: never a bare "restarting" - when HB is already down, show the last reason it announced.
    if (reason) { try { sessionStorage.setItem('hb-maint-reason', reason); } catch (_) {} }
    let last = ''; try { last = sessionStorage.getItem('hb-maint-reason') || ''; } catch (_) {}
    el.querySelector('[data-hb-maint-reason]').textContent = reason || (last ? last + ' (still loading)' : 'HB is restarting.');
    el.querySelector('[data-hb-maint-reload]').style.display = 'none';
    el.style.display = 'flex';
    shown = true; wasDown = true;
    if (!timer) timer = setInterval(probe, 3000);
  }

  function back(data) {
    if (timer) { clearInterval(timer); timer = null; }
    const updated = data && data.asset_version && loadedVersion && data.asset_version !== loadedVersion;
    if (updated && wasDown) {
      if (draftEmpty()) { location.reload(); return; }
      overlay().style.display = 'none';           // a draft is being written: keep it visible, offer the reload in a small bar
      shown = false; wasDown = false;
      if (!document.getElementById('hb-maint-updated')) {
        const bar = document.createElement('div');
        bar.id = 'hb-maint-updated';
        bar.setAttribute('role', 'status');
        bar.style.cssText = 'position:fixed;top:10px;left:50%;transform:translateX(-50%);z-index:100000;padding:8px 14px;border-radius:10px;'
          + 'border:1px solid var(--accent,#4a8);background:var(--card,#141c2b);color:var(--text,#e8eef8);font-size:13px;box-shadow:0 8px 24px rgba(0,0,0,.35)';
        bar.innerHTML = 'HB was updated. <button type="button" style="margin-left:8px;padding:3px 10px;border-radius:7px;border:1px solid var(--accent,#4a8);'
          + 'background:var(--accent,#4a8);color:#000;font-weight:700;cursor:pointer">Reload</button> <span style="opacity:.7">(send or copy your draft first)</span>';
        bar.querySelector('button').addEventListener('click', () => location.reload());
        document.body.appendChild(bar);
      }
      return;
    }
    if (shown) overlay().style.display = 'none';
    shown = false; wasDown = false;
    try { sessionStorage.removeItem('hb-maint-reason'); } catch (_) {}
    try { window.dispatchEvent(new Event('hummingbird:auth-required')); } catch (_) {}   // friday-auth re-checks the session
  }

  function probe() {
    return fetch('/api/hb/maintenance', { cache: 'no-store', credentials: 'same-origin' })
      .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(data => { if (data.on) show(data.reason); else if (shown || wasDown) back(data); return data; })
      .catch(() => { show(''); return null; });
  }

  // friday-auth.js calls this when the session check cannot reach HB (true) or succeeds again (false).
  window.hbMaintenance = function (on, reason) {
    if (on) show(reason); else probe();
  };
  window.hbMaintenanceProbe = probe;

  // Announced maintenance shows a few seconds before HB goes down (the restart helper waits for this).
  setInterval(() => { if (!document.hidden && !timer) probe(); }, 5000);
})();
