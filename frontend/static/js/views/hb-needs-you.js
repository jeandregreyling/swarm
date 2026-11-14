/* HB "Needs you" bar (owner 12 Nov).
 *
 * Everything waiting for the owner is pinned at the top of main chat (and the Chat window), right under the
 * team & tasks banner: Studio steps to approve, tasks HB stopped and asked about, HB's /yes-/no questions and
 * agent requests held for review. Same list as /approvals (core/hb_commands.waiting_items).
 *
 *   hover (or focus) a tag  -> a card shows exactly what it is, and the chat message it belongs to lights up
 *   click a tag             -> opens what it points to: the Studio step window, or the message in chat
 *
 * The "Approve Studio S-..." rows on chat bubbles get the same card on hover; their label opens the step.
 */
(function () {
  'use strict';
  if (typeof document === 'undefined' || typeof window === 'undefined') return;

  const KIND = {
    confirm: { icon: 'question', word: 'Confirm' },
    halted: { icon: 'pause', word: 'HB stopped' },
    review: { icon: 'flag', word: 'Review' },
    accept: { icon: 'check', word: 'Approve' },
    plan: { icon: 'plan', word: 'Plan' },
    workflow: { icon: 'play', word: 'Start' },
    status: { icon: 'retry', word: 'Workflow' },
    step: { icon: 'clipboard', word: 'Studio step' },
  };
  const ico = n => (window.HBIcons && window.HBIcons.svg) ? window.HBIcons.svg(n) : `<span data-hb-icon="${n}"></span>`;
  const TRANSCRIPTS = '#home-chat-messages, #chat-messages';
  const ROW = '#home-chat-messages .hb-acceptance-controls[data-hb-step], #chat-messages .hb-acceptance-controls[data-hb-step]';
  const S = { items: [], byKey: new Map(), seen: null, sig: '', busy: false, showTimer: 0, hideTimer: 0,
              current: null, anchor: null, lit: [], pinned: false, hoverRow: null };
  const stepCache = new Map();

  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const toast = (m, t) => { if (typeof window.showToast === 'function') window.showToast(m, t || 'info'); };
  const closest = (el, sel) => (el && el.closest ? el.closest(sel) : null);

  // ── the bar ────────────────────────────────────────────────────────────
  function stripFor(host) {
    let strip = host.nextElementSibling;
    if (!(strip && strip.matches && strip.matches('[data-hb-needs-you]'))) {
      strip = document.createElement('section');
      strip.className = 'hb-needs-you';
      strip.dataset.hbNeedsYou = host.dataset.chatParticipants || 'chat';
      strip.setAttribute('aria-label', 'Waiting for your decision');
      strip.hidden = true;
      host.insertAdjacentElement('afterend', strip);
    }
    return strip;
  }

  function render(strip, items, fresh) {
    if (!items.length) { strip.hidden = true; strip.innerHTML = ''; return; }
    strip.hidden = false;
    const needs = items.filter(i => !i.info).length;      // a workflow status tag is information, not a decision
    strip.innerHTML =
      (needs ? `<span class="hb-needs-head" title="Everything waiting for your decision (same list as /approvals). Hover a tag to see what it is; click it to open it.">Needs you <b>${needs}</b></span>`
             : `<span class="hb-needs-head hb-needs-quiet" title="Nothing is waiting for you. Hover the tag to see what HB is doing.">HB</span>`) +
      `<div class="hb-needs-chips">` + items.map(i => {
        const k = KIND[i.kind] || KIND.review;
        return `<button type="button" class="hb-needs-chip hb-needs-${esc(i.kind)}${i.info ? ' hb-needs-info' : ''}${fresh.has(i.key) && !i.info ? ' hb-needs-new' : ''}" ` +
          `data-needs-key="${esc(i.key)}" aria-haspopup="dialog" aria-expanded="false" aria-controls="hb-needs-card">` +
          `<span class="hb-needs-icon" aria-hidden="true">${ico(k.icon)}</span><span class="hb-needs-word">${esc(k.word)}</span>` +
          `<span class="hb-needs-label">${esc(i.label)}</span></button>`;
      }).join('') + `</div>`;
  }

  function apply(items) {
    const fresh = new Set(S.seen ? items.filter(i => !S.seen.has(i.key)).map(i => i.key) : []);
    S.seen = new Set(items.map(i => i.key));
    S.items = items;
    S.byKey = new Map(items.map(i => [i.key, i]));
    const sig = JSON.stringify(items.map(i => [i.key, i.label, i.why, i.detail && i.detail.length, (i.actions || []).length]));
    document.querySelectorAll('[data-chat-participants]').forEach(host => {
      const strip = stripFor(host);
      if (strip.dataset.sig === sig) return;            // unchanged: keep the DOM (and any hover) as it is
      render(strip, items, fresh);
      strip.dataset.sig = sig;
    });
    S.sig = sig;
    dial(items);
    if (!S.current || S.pinned) return;
    // An open card stays with its tag across re-renders, and shows the latest details.
    if (S.anchor && !S.anchor.isConnected && S.anchor.classList && S.anchor.classList.contains('hb-needs-chip')) {
      const again = [...document.querySelectorAll('.hb-needs-chip')].find(c => c.dataset.needsKey === S.current.key && c.getClientRects().length);
      if (again) { S.anchor = again; again.setAttribute('aria-expanded', 'true'); }
    }
    const latest = S.byKey.get(S.current.key);
    if (latest && JSON.stringify(latest) !== JSON.stringify(S.current) && !cardEl().querySelector('.hb-needs-feedback:not(:empty)') && !(cardEl().querySelector('.hb-needs-comment') || {}).value) {
      S.current = latest; unlight(); light(latest); fillCard(latest);
      if (S.anchor && S.anchor.isConnected) place(cardEl(), S.anchor);
    }
  }

  // The "needs you" dot on the header's control dial: the same count as the bar, one click to it.
  function dial(items) {
    const btn = document.getElementById('dial-needs-you');
    const count = document.getElementById('dial-needs-count');
    if (!btn || !count) return;
    const needs = items.filter(i => !i.info);
    count.textContent = String(needs.length);
    btn.dataset.count = String(needs.length);
    btn.title = needs.length ? 'Waiting for you: ' + needs.slice(0, 6).map(i => (KIND[i.kind] || KIND.review).word + ' ' + i.label).join('; ')
      + (needs.length > 6 ? '; …' : '') + '. Click to see them in main chat.' : 'Nothing is waiting for you.';
  }
  window.hbNeedsFocusBar = function () {
    const strip = document.querySelector('[data-hb-needs-you="home"]');
    if (!strip || strip.hidden || !strip.querySelector('.hb-needs-chip:not(.hb-needs-info)')) {
      toast('Nothing is waiting for you.', 'info');
      return;
    }
    strip.scrollIntoView({ block: 'center', behavior: 'smooth' });
    strip.classList.add('hb-needs-flash');
    setTimeout(() => strip.classList.remove('hb-needs-flash'), 2600);
    const first = strip.querySelector('.hb-needs-chip:not(.hb-needs-info)');
    if (first) setTimeout(() => first.focus(), 350);   // focus shows its card, like hovering
  };

  async function refresh() {
    if (S.busy || document.hidden) return;
    const hosts = [...document.querySelectorAll('[data-chat-participants]')].filter(h => h.getClientRects().length);
    if (!hosts.length) return;
    const conv = Number(hosts[0].dataset.conversationId || 0);
    S.busy = true;
    try {
      const r = await fetch('/api/peer/v1/hb/needs-you' + (conv ? '?conversation_id=' + conv : ''),
        { credentials: 'same-origin', signal: AbortSignal.timeout(5000) });
      if (!r.ok) return;                                  // signed out / HB restarting: keep the last list
      const data = await r.json();
      if (data && data.ok && Array.isArray(data.items)) apply(data.items);
    } catch (_) { /* keep the last list while HB is unreachable */ }
    finally { S.busy = false; }
  }
  let soonTimer = 0;
  function refreshSoon(ms) { clearTimeout(soonTimer); soonTimer = setTimeout(refresh, ms || 300); }

  // ── the card ───────────────────────────────────────────────────────────
  function cardEl() {
    let el = document.getElementById('hb-needs-card');
    if (el) return el;
    el = document.createElement('div');
    el.id = 'hb-needs-card';
    el.className = 'hb-needs-card';
    el.setAttribute('role', 'dialog');
    el.setAttribute('aria-label', 'What this is');
    el.hidden = true;
    document.body.appendChild(el);
    el.addEventListener('mouseenter', () => clearTimeout(S.hideTimer));
    el.addEventListener('mouseleave', e => {
      const to = e.relatedTarget;
      if (closest(to, '.hb-needs-chip') || (S.anchor && to && S.anchor.contains && S.anchor.contains(to))) return;
      scheduleHide();
    });
    el.addEventListener('click', onCardClick);
    return el;
  }

  function fillCard(i) {
    const el = cardEl();
    const k = KIND[i.kind] || KIND.review;
    const ids = [i.step_id, i.task_id, i.project_id].filter(Boolean).map(esc).join(' · ');
    const mid = (i.message_ids || [])[0];
    const where = mid ? (S.lit.length ? `The chat message this belongs to (#${Number(mid)}) is highlighted.`
                                      : `It belongs to message #${Number(mid)}${i.conversation_id ? ' in chat #' + Number(i.conversation_id) : ''}.`) : '';
    const open = i.open ? (i.open.type === 'step' ? 'Open the Studio step ↗' : 'Show in chat ↗') : '';
    el.className = 'hb-needs-card hb-needs-' + (KIND[i.kind] ? i.kind : 'review');
    el.innerHTML =
      `<div class="hb-needs-card-head"><span class="hb-needs-kind">${ico(k.icon)} ${esc(k.word)}</span><span class="hb-needs-ids">${ids}</span>` +
      `<button type="button" class="hb-needs-x" data-act="close" aria-label="Close">×</button></div>` +
      `<strong class="hb-needs-title">${esc(i.title)}</strong>` +
      (i.why ? `<div class="hb-needs-why">${esc(i.why)}</div>` : '') +
      (i.detail ? `<div class="hb-needs-detail" tabindex="0">${esc(i.detail)}</div>` : '') +
      (where ? `<div class="hb-needs-where">${where}</div>` : '') +
      (i.kind === 'accept' ? `<textarea class="hb-needs-comment" rows="2" placeholder="Optional comment for HB and APEX (saved with the approval)"></textarea>` : '') +
      `<div class="hb-needs-actions">` +
      (i.actions || []).map((a, n) => `<button type="button" data-act="action" data-n="${n}"${n === 0 ? ' class="hb-needs-primary"' : ''}>${esc(a.label)}</button>`).join('') +
      (open ? `<button type="button" data-act="open">${open}</button>` : '') +
      (S.lit.length && !(i.open && i.open.type === 'message') ? `<button type="button" data-act="scroll">Show in chat</button>` : '') +
      `</div><div class="hb-needs-feedback" role="status"></div>`;
  }

  function place(el, anchor) {
    const r = anchor.getBoundingClientRect();
    el.style.left = '0px'; el.style.top = '0px'; el.hidden = false;
    const w = el.offsetWidth, h = el.offsetHeight;
    const left = Math.min(Math.max(8, r.left), window.innerWidth - w - 8);
    let top = r.bottom + 6;
    if (top + h > window.innerHeight - 8) top = Math.max(8, r.top - h - 6);
    el.style.left = left + 'px'; el.style.top = top + 'px';
  }

  function bubblesFor(i) {
    const out = new Set();
    (i.message_ids || []).forEach(id => document.querySelectorAll(
      `#home-chat-messages [data-message-id="${Number(id)}"], #chat-messages [data-message-id="${Number(id)}"]`).forEach(b => out.add(b)));
    if (i.step_id && window.CSS && CSS.escape) {
      document.querySelectorAll(`#home-chat-messages .hb-acceptance-controls[data-hb-step="${CSS.escape(i.step_id)}"], ` +
                                `#chat-messages .hb-acceptance-controls[data-hb-step="${CSS.escape(i.step_id)}"]`)
        .forEach(g => { const b = closest(g, '[data-message-id]') || closest(g, '.hc-bubble, .chat-bubble'); if (b) out.add(b); });
    }
    return [...out];
  }
  function light(i) { S.lit = bubblesFor(i); S.lit.forEach(b => { b.dataset.hbNeedsLit = KIND[i.kind] ? i.kind : 'review'; }); }
  function unlight() { S.lit.forEach(b => { delete b.dataset.hbNeedsLit; }); S.lit = []; }

  function show(anchor, item, immediate) {
    clearTimeout(S.hideTimer); clearTimeout(S.showTimer);
    const go = () => {
      if (!anchor.isConnected) return;
      unlight();
      if (S.anchor && S.anchor !== anchor && S.anchor.setAttribute) S.anchor.setAttribute('aria-expanded', 'false');
      S.current = item; S.anchor = anchor;
      light(item);
      fillCard(item);
      place(cardEl(), anchor);
      if (anchor.classList.contains('hb-needs-chip')) anchor.setAttribute('aria-expanded', 'true');
    };
    if (immediate) go(); else S.showTimer = setTimeout(go, 120);
  }
  function scheduleHide() {
    clearTimeout(S.showTimer); clearTimeout(S.hideTimer);
    if (!S.pinned) S.hideTimer = setTimeout(() => hide(false), 280);
  }
  function hide(returnFocus) {
    clearTimeout(S.showTimer); clearTimeout(S.hideTimer);
    const el = document.getElementById('hb-needs-card');
    if (el) el.hidden = true;
    unlight();
    const anchor = S.anchor;
    if (anchor && anchor.setAttribute && anchor.classList.contains('hb-needs-chip')) anchor.setAttribute('aria-expanded', 'false');
    S.current = null; S.anchor = null; S.pinned = false;
    if (returnFocus && anchor && anchor.isConnected && anchor.focus) anchor.focus();
  }

  // ── what a tag points to ───────────────────────────────────────────────
  function openStep(stepId, projectId) {
    hide(false);
    if (typeof window.projectsOpenStep === 'function') { window.projectsOpenStep(stepId); return; }
    if (projectId && typeof window.hbOpenTaskProject === 'function') { window.hbOpenTaskProject(projectId); return; }
    toast('Studio is not loaded on this page.', 'error');
  }
  function openTarget(i) {
    const o = i.open;
    if (!o) { toast('The details are in the card; there is nothing else to open.', 'info'); return; }
    if (o.type === 'step') { openStep(o.id, i.project_id); return; }
    hide(false);
    window.hbNeedsShowMessage(o.conversation_id, o.id);
  }

  // Scroll main chat (or the Chat window) to a message; switches main chat to its conversation if needed.
  window.hbNeedsShowMessage = function (conversationId, messageId) {
    const id = Number(messageId), conv = Number(conversationId);
    if (!Number.isSafeInteger(id) || id < 1) return;
    const find = () => document.querySelector(`#home-chat-messages [data-message-id="${id}"], #chat-messages [data-message-id="${id}"]`);
    const go = el => {
      el.hidden = false;
      el.scrollIntoView({ block: 'center', behavior: 'smooth' });
      el.classList.add('hb-needs-flash');
      setTimeout(() => el.classList.remove('hb-needs-flash'), 2600);
    };
    const el = find();
    if (el) { go(el); return; }
    const sel = document.getElementById('home-chat-thread-select');
    if (sel && Number.isSafeInteger(conv) && conv > 0 && Number(sel.value) !== conv) {
      if (![...sel.options].some(o => Number(o.value) === conv)) sel.add(new Option('#' + conv, String(conv)));
      sel.value = String(conv);
      sel.dispatchEvent(new Event('change'));
      let tries = 0;
      const wait = setInterval(() => {
        const found = find();
        if (found || ++tries > 40) {
          clearInterval(wait);
          if (found) go(found); else toast(`Message #${id} is not in the loaded chat.`, 'info');
        }
      }, 200);
      return;
    }
    toast(`Message #${id} is not in the loaded chat.`, 'info');
  };

  // ── card buttons (also used by the Studio step window: hbNeedsPanel) ───
  function feedback(text) { const fb = cardEl().querySelector('.hb-needs-feedback'); if (fb) fb.textContent = text; }
  function setBusy(on) { cardEl().querySelectorAll('.hb-needs-actions button').forEach(b => { b.disabled = on; }); }
  const CARD_UI = { feedback: t => feedback(t), busy: on => setBusy(on), fill: () => hide(false), home: null };

  async function decide(i, decision, ui = CARD_UI) {
    let reason = '';
    if (decision === 'accept') {
      const box = cardEl().querySelector('.hb-needs-comment');
      reason = box ? box.value.trim() : '';
    }
    if (decision === 'reject') {
      S.pinned = true;
      reason = (window.prompt(`What needs to change in ${i.step_id}? It goes back to its task with your reason.`) || '').trim();
      S.pinned = false;
      if (!reason) return;
    }
    S.pinned = true; ui.busy(true); ui.feedback('Saving…');
    try {
      const r = await fetch('/api/peer/v1/studio/steps/' + encodeURIComponent(i.step_id) + '/decision', {
        method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision, reason }),
      });
      const data = await r.json();
      if (!r.ok || !data.ok) throw new Error(data.error || 'The decision was not saved');
      ui.feedback(data.response || 'Saved.');
      if (data.acceptance && typeof window.hbAcceptanceInner === 'function' && window.CSS && CSS.escape) {
        document.querySelectorAll(`.hb-acceptance-controls[data-hb-step="${CSS.escape(i.step_id)}"]`)
          .forEach(g => { g.innerHTML = window.hbAcceptanceInner(data.acceptance); });
      }
      stepCache.delete(i.step_id);
      refreshSoon(150);
    } catch (err) {
      ui.feedback(err.message || String(err)); ui.busy(false);
    } finally { S.pinned = false; }
  }

  function command(a, ui = CARD_UI) {
    const home = ui.home !== null ? ui.home : (!!closest(S.anchor, '.home-chat-section, #home-chat-main') || !document.getElementById('question-input'));
    const input = document.getElementById(home ? 'home-chat-input' : 'question-input') || document.getElementById('home-chat-input');
    if (!input) { toast('The chat composer is not available.', 'error'); return; }
    input.value = a.command;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    if (a.fill) {                                         // the owner finishes the command text
      ui.fill(); input.focus();
      try { input.setSelectionRange(input.value.length, input.value.length); } catch (_) { /* textarea only */ }
      return;
    }
    if (input.id === 'home-chat-input') document.getElementById('home-chat-send-btn')?.click();
    else input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    ui.busy(true);
    ui.feedback(`Sent ${a.command.trim()}; HB answers in main chat.`);
    refreshSoon(900);
  }

  // The Studio step window (opened by clicking a tag) shows the same question and buttons as the bar
  // (owner 12 Nov: "when opening the task the approve / whatever else buttons aren't there").
  // Steps waiting for acceptance already have their Approve / Send back row in that window.
  window.hbNeedsPanel = async function (stepId, host, note) {
    if (!stepId || !host) return;
    let items = S.items;
    try {
      const r = await fetch('/api/peer/v1/hb/needs-you', { credentials: 'same-origin', signal: AbortSignal.timeout(5000) });
      const data = await r.json();
      if (r.ok && data.ok && Array.isArray(data.items)) items = data.items;
    } catch (_) { /* use the bar's last list */ }
    if (!host.isConnected) return;
    host.querySelectorAll('.hb-needs-panel').forEach(p => p.remove());
    const mine = items.filter(i => i.step_id === stepId && !i.info && i.kind !== 'accept');
    if (!mine.length) {
      if (note) {
        const done = document.createElement('div');
        done.className = 'hb-needs-panel hb-needs-panel-done';
        done.textContent = note;
        (host.firstElementChild || host).insertAdjacentElement(host.firstElementChild ? 'afterend' : 'afterbegin', done);
      }
      return;
    }
    const panel = document.createElement('div');
    panel.className = 'hb-needs-panel';
    panel.innerHTML = mine.map((i, n) => {
      const k = KIND[i.kind] || KIND.review;
      return `<section class="hb-needs-panel-item hb-needs-${esc(KIND[i.kind] ? i.kind : 'review')}" data-n="${n}">` +
        `<div class="hb-needs-kind">${ico(k.icon)} Hummingbird needs you · ${esc(k.word)}</div>` +
        (i.why ? `<div class="hb-needs-why">${esc(i.why)}</div>` : '') +
        (i.detail ? `<div class="hb-needs-detail">${esc(i.detail)}</div>` : '') +
        `<div class="hb-needs-actions">` + (i.actions || []).map((a, m) =>
          `<button type="button" data-m="${m}"${m === 0 ? ' class="hb-needs-primary"' : ''}>${esc(a.label)}</button>`).join('') +
        `</div><div class="hb-needs-feedback" role="status"></div></section>`;
    }).join('');
    const title = host.firstElementChild;
    if (title) title.insertAdjacentElement('afterend', panel); else host.prepend(panel);
    panel.addEventListener('click', e => {
      const btn = closest(e.target, 'button[data-m]');
      const box = closest(btn, '.hb-needs-panel-item');
      if (!btn || !box) return;
      const i = mine[Number(box.dataset.n)];
      const a = (i.actions || [])[Number(btn.dataset.m)];
      if (!a) return;
      const fb = box.querySelector('.hb-needs-feedback');
      const ui = {
        feedback: t => { fb.textContent = t; },
        busy: on => box.querySelectorAll('button').forEach(b => { b.disabled = on; }),
        fill: () => { const m = document.getElementById('alm-detail-modal'); if (m) m.style.display = 'none'; },
        home: true,
      };
      if (a.decision) decide(i, a.decision, ui);
      else if (a.command) {
        command(a, ui);
        if (!a.fill) setTimeout(() => window.hbNeedsPanel(stepId, host, `Sent ${a.command.trim()}; HB answered in main chat.`), 2500);
      }
    });
  };

  function onCardClick(e) {
    const btn = closest(e.target, 'button[data-act]');
    const i = S.current;
    if (!btn || !i) return;
    const act = btn.dataset.act;
    if (act === 'close') { hide(true); return; }
    if (act === 'open') { openTarget(i); return; }
    if (act === 'scroll') { const b = S.lit[0]; if (b) b.scrollIntoView({ block: 'center', behavior: 'smooth' }); return; }
    const a = (i.actions || [])[Number(btn.dataset.n)];
    if (!a) return;
    if (a.decision) decide(i, a.decision);
    else if (a.command) command(a);
  }

  // Inline "Approve Studio S-..." rows: the same card, built from the step itself when it is not in the bar.
  async function stepItem(stepId) {
    if (S.byKey.has('accept:' + stepId)) return S.byKey.get('accept:' + stepId);
    const hit = stepCache.get(stepId);
    if (hit && Date.now() - hit.at < 30000) return hit.item;
    try {
      const r = await fetch('/api/knowledge/steps/' + encodeURIComponent(stepId), { credentials: 'same-origin' });
      const data = await r.json();
      if (!r.ok || !data.ok || !data.step) return null;
      const s = data.step;
      const pending = s.acceptance && s.acceptance.state === 'pending';
      const item = { key: 'step:' + stepId, kind: pending ? 'accept' : 'step', label: s.title, title: s.title || stepId,
                     why: s.residual_risk || ('Status: ' + s.status), detail: s.description || '', step_id: stepId,
                     project_id: s.project_id, message_ids: [], open: { type: 'step', id: stepId },
                     actions: pending ? [{ label: 'Approve', decision: 'accept' }, { label: 'Send back…', decision: 'reject' }] : [] };
      stepCache.set(stepId, { at: Date.now(), item });
      return item;
    } catch (_) { return null; }
  }

  // ── events (delegated, so re-rendered bars and bubbles keep working) ───
  document.addEventListener('mouseover', e => {
    const chip = closest(e.target, '.hb-needs-chip');
    if (chip) {
      const item = S.byKey.get(chip.dataset.needsKey);
      if (!item) return;
      if (S.anchor === chip) clearTimeout(S.hideTimer); else show(chip, item, false);
      return;
    }
    const row = closest(e.target, ROW);
    if (!row || closest(e.target, 'button')) return;     // the row's own buttons stay plain buttons
    S.hoverRow = row;
    if (S.anchor === row) { clearTimeout(S.hideTimer); return; }
    stepItem(row.dataset.hbStep).then(item => { if (item && S.hoverRow === row) show(row, item, false); });
  });
  document.addEventListener('mouseout', e => {
    const from = closest(e.target, '.hb-needs-chip') || closest(e.target, ROW);
    if (!from) return;
    const to = e.relatedTarget;
    if (to && (from.contains(to) || closest(to, '#hb-needs-card'))) return;
    if (from === S.hoverRow) S.hoverRow = null;
    scheduleHide();                                       // a tag entered next cancels this (mouseover follows mouseout)
  });
  document.addEventListener('focusin', e => {
    const chip = closest(e.target, '.hb-needs-chip');
    if (chip && S.anchor !== chip) { const item = S.byKey.get(chip.dataset.needsKey); if (item) show(chip, item, true); }
  });
  document.addEventListener('click', e => {
    const chip = closest(e.target, '.hb-needs-chip');
    if (chip) { const item = S.byKey.get(chip.dataset.needsKey); if (item) openTarget(item); return; }
    const label = closest(e.target, '#home-chat-messages .hb-acceptance-controls[data-hb-step] strong, #chat-messages .hb-acceptance-controls[data-hb-step] strong');
    if (label) { openStep(closest(label, '.hb-acceptance-controls').dataset.hbStep); return; }
    if (S.current && !closest(e.target, '#hb-needs-card') && !S.pinned) hide(false);
  });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && S.current) hide(true); });
  window.addEventListener('resize', () => { if (S.current && S.anchor && S.anchor.isConnected) place(cardEl(), S.anchor); });
  document.addEventListener('scroll', e => {          // the card follows its tag; a scrolled-away tag closes it
    if (!S.current || !S.anchor || closest(e.target, '#hb-needs-card')) return;
    if (!S.anchor.isConnected || !S.anchor.getClientRects().length) hide(false); else place(cardEl(), S.anchor);
  }, true);

  function start() {
    setInterval(refresh, 5000);
    document.addEventListener('sse:chat', () => refreshSoon(400));
    document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshSoon(200); });
    setTimeout(refresh, 900);
  }
  window.hbNeedsRefresh = refreshSoon;
  window.hbNeedsYouItems = () => S.items.slice();
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
