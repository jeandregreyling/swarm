/* pillar_live.js — render live summaries and quick-add forms inside the
 * four wishlist pillar views (cyber-security, financial, trading,
 * business).
 *
 * The view template provides an empty <div class="wishlist-pillar-live"
 * data-live-slug="…"></div>. This script:
 *   1. Detects the slug
 *   2. Calls /api/<slug>/summary
 *   3. Renders a tight summary card + recent items list + a single-line
 *      "quick add" form. Submit POSTs the matching create endpoint.
 *
 * Designed to be UI-only — no wishlist.js coupling. Both files cooperate
 * through the DOM, not through globals.
 */
(function () {
  'use strict';

  const PILLARS = {
    'cyber-security': {
      summaryUrl: '/api/cyber/summary',
      createUrl:  '/api/cyber/events',
      listUrl:    '/api/cyber/events?limit=5',
      headline: function (s) {
        const sev = s.by_severity || {};
        return [
          ['critical', sev.critical || 0],
          ['high',     sev.high || 0],
          ['medium',   sev.medium || 0],
          ['low',      sev.low || 0],
          ['info',     sev.info || 0],
        ];
      },
      itemsKey: 'events',
      renderItem: function (it) {
        return (it.severity || 'info').toUpperCase() + ' · ' + (it.summary || '(no summary)');
      },
      form: {
        label: 'Log audit event',
        placeholder: 'e.g. dependency-vulnerability in requests<2.32',
        bodyFn: function (text) { return { summary: text, severity: 'medium', source: 'manual' }; },
      },
    },
    'financial': {
      summaryUrl: '/api/financial/summary',
      createUrl:  '/api/financial/positions',
      listUrl:    '/api/financial/positions?limit=5',
      headline: function (s) {
        const cls = s.by_class || {};
        const out = [];
        Object.keys(cls).forEach(function (c) {
          const ccys = cls[c] || {};
          let n = 0;
          Object.keys(ccys).forEach(function (k) { n += (ccys[k].count || 0); });
          out.push([c, n]);
        });
        return out.length ? out : [['no positions', 0]];
      },
      itemsKey: 'positions',
      renderItem: function (it) {
        return (it.ticker || '?') + ' · ' + (it.asset_class || 'equity') + ' · ' + (it.conviction || 'medium');
      },
      form: {
        label: 'Log idea (ticker, optional thesis)',
        placeholder: 'e.g. AAPL: long, AI capex re-rate',
        bodyFn: function (text) {
          const parts = text.split(':');
          return {
            ticker: (parts[0] || text).trim(),
            thesis: parts.slice(1).join(':').trim() || null,
            asset_class: 'equity',
            conviction: 'medium',
          };
        },
      },
    },
    'trading': {
      summaryUrl: '/api/trading/summary',
      createUrl:  '/api/trading/signals',
      listUrl:    '/api/trading/signals?limit=5',
      headline: function (s) {
        const bs = s.by_side || {};
        const out = [['buy', bs.buy || 0], ['sell', bs.sell || 0]];
        if (typeof s.realised_pnl === 'number') out.push(['realised P&L', s.realised_pnl.toFixed(2)]);
        return out;
      },
      itemsKey: 'signals',
      renderItem: function (it) {
        return (it.symbol || '?') + ' · ' + (it.side || '?').toUpperCase() + ' · conf ' + (it.confidence != null ? it.confidence : '-');
      },
      form: {
        label: 'Log signal (symbol side strategy)',
        placeholder: 'e.g. BTC-USD buy breakout',
        bodyFn: function (text) {
          const parts = text.trim().split(/\s+/);
          return {
            symbol: parts[0] || text,
            side: (parts[1] || 'buy').toLowerCase(),
            strategy: parts.slice(2).join(' ') || null,
            confidence: 0.5,
          };
        },
      },
    },
    'business': {
      summaryUrl: '/api/business/summary',
      createUrl:  '/api/business/entries',
      listUrl:    '/api/business/entries?limit=5',
      headline: function (s) {
        const bk = s.by_kind || {};
        const out = [];
        Object.keys(bk).forEach(function (k) { out.push([k, bk[k]]); });
        if (typeof s.unreconciled === 'number') out.push(['unreconciled', s.unreconciled]);
        return out.length ? out : [['no entries', 0]];
      },
      itemsKey: 'entries',
      renderItem: function (it) {
        return (it.kind || 'expense') + ' · ' + (it.amount != null ? it.amount : 0) + ' ' + (it.currency || 'USD') + ' · ' + (it.counterparty || '');
      },
      form: {
        label: 'Log entry (kind amount currency counterparty)',
        placeholder: 'e.g. expense 49.99 USD anthropic',
        bodyFn: function (text) {
          const parts = text.trim().split(/\s+/);
          return {
            kind: (parts[0] || 'expense').toLowerCase(),
            amount: parseFloat(parts[1]) || 0,
            currency: (parts[2] || 'USD').toUpperCase(),
            counterparty: parts.slice(3).join(' ') || null,
          };
        },
      },
    },
  };

  function escape(text) {
    if (text == null) return '';
    return String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function renderHeadline(pairs) {
    return pairs.map(function (p) {
      return (
        '<span style="display:inline-block;padding:3px 8px;margin:2px 4px 2px 0;border:1px solid var(--border);border-radius:10px;font-size:10px;background:var(--bg);">'
        + '<span style="color:var(--text-dim);">' + escape(p[0]) + ':</span> '
        + '<strong>' + escape(p[1]) + '</strong>'
        + '</span>'
      );
    }).join('');
  }

  function renderItems(items, conf) {
    if (!items || !items.length) {
      return '<div style="font-size:11px;color:var(--text-dim);padding:6px 0;">No recent items.</div>';
    }
    return (
      '<ul style="list-style:none;padding:0;margin:6px 0 0;">'
      + items.slice(0, 5).map(function (it) {
        return '<li style="padding:4px 6px;font-size:11px;border-bottom:1px dashed var(--border);">' + escape(conf.renderItem(it)) + '</li>';
      }).join('')
      + '</ul>'
    );
  }

  function renderForm(conf) {
    return (
      '<form class="wishlist-quickadd" style="margin-top:10px;display:flex;gap:6px;" novalidate>'
      + '<label class="sr-only" for="wq-' + escape(conf.createUrl) + '" style="position:absolute;left:-9999px;">' + escape(conf.form.label) + '</label>'
      + '<input id="wq-' + escape(conf.createUrl) + '" type="text" name="quick" autocomplete="off" '
      +   'placeholder="' + escape(conf.form.placeholder) + '" aria-label="' + escape(conf.form.label) + '" '
      +   'style="flex:1;padding:6px 8px;font-size:11px;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:4px;" />'
      + '<button type="submit" aria-label="Add entry" '
      +   'style="padding:6px 12px;font-size:11px;background:var(--accent);color:#000;border:none;border-radius:4px;font-weight:600;cursor:pointer;">Add</button>'
      + '</form>'
      + '<div class="wishlist-quickadd-status" role="status" aria-live="polite" style="font-size:10px;color:var(--text-dim);margin-top:4px;min-height:13px;"></div>'
    );
  }

  function paint(panel, summary, items, conf) {
    const headline = conf.headline(summary || {});
    const slug = panel.dataset.liveSlug;
    const populated = items && items.length;
    panel.setAttribute('role', 'region');
    panel.setAttribute('aria-label', slug + ' live snapshot');
    panel.innerHTML = (
      '<div style="border:1px solid var(--border);border-radius:6px;padding:10px 12px;background:var(--card);">'
      + '<div style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center;">'
      +   '<span>Live snapshot</span>'
      +   '<button type="button" class="wishlist-pillar-refresh" aria-label="Refresh ' + escape(slug) + ' snapshot" '
      +     'style="font-size:10px;background:transparent;color:var(--text-dim);border:1px solid var(--border);border-radius:4px;padding:2px 8px;cursor:pointer;">refresh</button>'
      + '</div>'
      + '<div>' + renderHeadline(headline) + '</div>'
      + '<div style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;margin:10px 0 4px;">Recent</div>'
      + renderItems(items, conf)
      + (populated ? '' :
          '<div style="font-size:11px;color:var(--text-dim);padding:4px 0 0;">'
          + 'No entries yet — use the form below to log the first one.</div>')
      + '<div style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;margin:10px 0 4px;">' + escape(conf.form.label) + '</div>'
      + renderForm(conf)
      + '</div>'
    );

    const form = panel.querySelector('.wishlist-quickadd');
    const status = panel.querySelector('.wishlist-quickadd-status');
    const refresh = panel.querySelector('.wishlist-pillar-refresh');
    if (refresh) {
      refresh.addEventListener('click', function () {
        panel.dataset.livePopulated = '';
        populate(panel);
      });
    }
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      const input = form.querySelector('input[name="quick"]');
      const button = form.querySelector('button');
      const text = (input.value || '').trim();
      if (!text) {
        status.textContent = 'Type something first.';
        input.focus();
        return;
      }
      button.disabled = true;
      button.style.opacity = '0.6';
      status.textContent = 'Saving…';
      fetch(conf.createUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(conf.form.bodyFn(text)),
      })
        .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
        .then(function (res) {
          if (res.ok && res.body && res.body.ok) {
            status.textContent = 'Saved.';
            input.value = '';
            panel.dataset.livePopulated = '';
            populate(panel);
          } else {
            const err = (res.body && res.body.error) || 'failed';
            status.textContent = 'Error: ' + err;
          }
        })
        .catch(function (e) { status.textContent = 'Error: network'; })
        .then(function () { button.disabled = false; button.style.opacity = '1'; });
    });
  }

  function paintError(panel, msg) {
    const slug = panel.dataset.liveSlug;
    panel.innerHTML = (
      '<div role="alert" style="border:1px solid var(--accent,#e88);border-radius:6px;padding:10px 12px;background:var(--card);">'
      + '<div style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;">Live snapshot · error</div>'
      + '<div style="font-size:11px;color:var(--text);">Could not load <strong>' + escape(slug) + '</strong>: ' + escape(msg) + '</div>'
      + '<button type="button" class="wishlist-pillar-retry" '
      +   'style="margin-top:8px;font-size:11px;background:var(--accent);color:#000;border:none;border-radius:4px;padding:6px 12px;cursor:pointer;font-weight:600;">Retry</button>'
      + '</div>'
    );
    const btn = panel.querySelector('.wishlist-pillar-retry');
    if (btn) btn.addEventListener('click', function () {
      panel.dataset.livePopulated = '';
      populate(panel);
    });
  }

  function paintLoading(panel) {
    panel.innerHTML = (
      '<div role="status" aria-live="polite" style="border:1px solid var(--border);border-radius:6px;padding:10px 12px;background:var(--card);">'
      + '<div style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;">Live snapshot</div>'
      + '<div style="font-size:11px;color:var(--text-dim);">Reading…</div>'
      + '</div>'
    );
  }

  function populate(panel) {
    if (!panel || panel.dataset.livePopulated === '1') return;
    const slug = panel.dataset.liveSlug;
    const conf = PILLARS[slug];
    if (!conf) return;
    panel.dataset.livePopulated = '1';
    paintLoading(panel);
    Promise.all([
      fetch(conf.summaryUrl).then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); }),
      fetch(conf.listUrl).then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); }),
    ]).then(function (results) {
      const summary = results[0] || {};
      const items = (results[1] && results[1][conf.itemsKey]) || [];
      paint(panel, summary, items, conf);
    }).catch(function (err) {
      paintError(panel, (err && err.message) || 'unknown');
    });
  }

  function scan() {
    document.querySelectorAll('.wishlist-pillar-live').forEach(populate);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', scan);
  } else {
    scan();
  }

  const observer = new MutationObserver(function (muts) {
    let need = false;
    for (const m of muts) {
      for (const node of m.addedNodes) {
        if (node.nodeType !== 1) continue;
        if (node.classList && node.classList.contains('wishlist-pillar-live')) { need = true; break; }
        if (node.querySelector && node.querySelector('.wishlist-pillar-live')) { need = true; break; }
      }
      if (need) break;
    }
    if (need) scan();
  });
  observer.observe(document.body || document.documentElement, { childList: true, subtree: true });

  window.pillarLivePopulateAll = scan;
})();
