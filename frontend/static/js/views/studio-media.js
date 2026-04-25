(function () {
  'use strict';

  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  window.loadStudioMediaPanel = async function () {
    const body = document.getElementById('studio-media-body');
    const summary = document.getElementById('studio-media-summary');
    if (!body) return;
    body.innerHTML = '<div style="padding:8px 0;">Loading Media Center context…</div>';
    try {
      const response = await fetch('/api/media-center/state');
      const data = await response.json();
      if (!data.ok) throw new Error(data.error || 'failed');

      if (summary) {
        summary.innerHTML = `${data.counts?.projects || 0} media projects linked into Studio · `
          + `${data.interests?.relevant?.length || 0} relevant interests · `
          + `${data.feeds?.subscriptions?.length || 0} connected feeds · `
          + `${data.spine?.items?.length || 0} recent spine events`;
      }

      const linkedProjects = (data.studio?.linked_projects || []).map(project => `
        <div style="padding:10px 12px;border:1px solid var(--border);border-radius:8px;background:var(--card);">
          <div style="display:flex;justify-content:space-between;gap:8px;align-items:center;">
            <div>
              <div style="font-size:12px;font-weight:700;color:var(--text);">${esc(project.name)}</div>
              <div style="font-size:10px;color:var(--text-dim);font-family:monospace;">media: ${esc(project.id)} · studio: ${esc(project.studio_project_id || 'pending')}</div>
            </div>
            <div style="font-size:10px;color:var(--accent);text-transform:uppercase;font-weight:700;">${esc(project.status || 'draft')}</div>
          </div>
        </div>
      `).join('') || '<div style="color:var(--text-dim);">No Media Center projects yet.</div>';

      const interests = (data.interests?.relevant || []).map(item => `
        <div style="padding:7px 10px;border:1px solid var(--border);border-radius:999px;background:color-mix(in srgb,var(--accent) 9%, var(--card));display:inline-flex;gap:6px;align-items:center;">
          <span style="font-weight:700;color:var(--text);">${esc(item.topic)}</span>
          <span style="font-size:10px;color:var(--text-dim);">${esc(item.category || 'general')}</span>
        </div>
      `).join('') || '<div style="color:var(--text-dim);">No linked interests yet.</div>';

      const feedSubs = (data.feeds?.subscriptions || []).map(feed => `
        <div style="padding:10px 12px;border:1px solid var(--border);border-radius:8px;background:var(--card);">
          <div style="font-size:11px;font-weight:700;color:var(--text);">${esc(feed.title || feed.kind || 'feed')}</div>
          <div style="font-size:10px;color:var(--text-dim);margin-top:4px;">${esc(feed.kind)} · ${esc(feed.status || 'pending')}</div>
          <div style="font-size:10px;color:var(--text-dim);margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${esc(feed.url || '')}</div>
        </div>
      `).join('') || '<div style="color:var(--text-dim);">No connected feeds yet.</div>';

      const feedSuggestions = (data.feeds?.suggestions || []).map(item => `
        <div style="padding:10px 12px;border:1px dashed color-mix(in srgb,var(--accent) 30%, var(--border));border-radius:8px;background:color-mix(in srgb,var(--accent) 5%, var(--card));">
          <div style="font-size:11px;font-weight:700;color:var(--text);">${esc(item.title)}</div>
          <div style="font-size:10px;color:var(--text-dim);margin-top:4px;">${esc(item.reason)}</div>
        </div>
      `).join('') || '<div style="color:var(--text-dim);">No feed suggestions yet.</div>';

      const spine = (data.spine?.items || []).map(item => `
        <div style="padding:10px 12px;border:1px solid var(--border);border-radius:8px;background:var(--card);">
          <div style="display:flex;justify-content:space-between;gap:8px;">
            <div style="font-size:11px;font-weight:700;color:var(--text);">${esc(item.kind || 'event')}</div>
            <div style="font-size:10px;color:var(--text-dim);">${esc(item.severity || 'info')}</div>
          </div>
          <div style="font-size:10px;color:var(--text-dim);margin-top:5px;">${esc(item.message || '')}</div>
        </div>
      `).join('') || '<div style="color:var(--text-dim);">No media spine events yet.</div>';

      body.innerHTML = `
        <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;">
          <section style="border:1px solid var(--border);border-radius:10px;background:var(--card);padding:12px;">
            <div style="font-size:10px;font-weight:700;color:var(--text-dim);text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px;">Linked Studio Projects</div>
            <div style="display:flex;flex-direction:column;gap:8px;">${linkedProjects}</div>
          </section>
          <section style="border:1px solid var(--border);border-radius:10px;background:var(--card);padding:12px;">
            <div style="font-size:10px;font-weight:700;color:var(--text-dim);text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px;">Interest Signals</div>
            <div style="display:flex;flex-wrap:wrap;gap:8px;">${interests}</div>
          </section>
          <section style="border:1px solid var(--border);border-radius:10px;background:var(--card);padding:12px;">
            <div style="font-size:10px;font-weight:700;color:var(--text-dim);text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px;">Connected Feeds</div>
            <div style="display:flex;flex-direction:column;gap:8px;">${feedSubs}</div>
          </section>
          <section style="border:1px solid var(--border);border-radius:10px;background:var(--card);padding:12px;">
            <div style="font-size:10px;font-weight:700;color:var(--text-dim);text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px;">Recommended Feed Inputs</div>
            <div style="display:flex;flex-direction:column;gap:8px;">${feedSuggestions}</div>
          </section>
        </div>
        <section style="border:1px solid var(--border);border-radius:10px;background:var(--card);padding:12px;margin-top:12px;">
          <div style="font-size:10px;font-weight:700;color:var(--text-dim);text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px;">Media Spine</div>
          <div style="display:flex;flex-direction:column;gap:8px;">${spine}</div>
        </section>
      `;
    } catch (err) {
      body.innerHTML = `<div style="color:var(--danger,#f77);">Media panel failed to load: ${esc(err.message || err)}</div>`;
    }
  };
})();
