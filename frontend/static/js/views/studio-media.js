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
          + `${data.studio?.tracking_project_id ? 'tracking project ready · ' : ''}`
          + `${data.interests?.relevant?.length || 0} relevant interests · `
          + `${data.feeds?.subscriptions?.length || 0} connected feeds · `
          + `${data.spine?.items?.length || 0} recent spine events`;
      }

      const trackingProjectId = data.studio?.tracking_project_id || '';
      const trackingProgress = data.tracking?.progress || {};
      const trackingProject = trackingProjectId ? `
        <section style="border:1px solid color-mix(in srgb,var(--accent) 38%, var(--border));border-radius:10px;background:color-mix(in srgb,var(--accent) 7%, var(--card));padding:12px;margin-bottom:12px;">
          <div style="display:flex;justify-content:space-between;gap:10px;align-items:center;">
            <div>
              <div style="font-size:10px;font-weight:700;color:var(--text-dim);text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px;">Internal Tracking Project</div>
              <div style="font-size:13px;font-weight:800;color:var(--text);">${esc(data.studio?.tracking_project_name || 'Media Center + Studio Integration')}</div>
              <div style="font-size:10px;color:var(--text-dim);font-family:monospace;margin-top:4px;">${esc(trackingProjectId)}</div>
              <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:8px;">
                <span style="font-size:10px;padding:3px 7px;border:1px solid var(--border);border-radius:999px;background:var(--card);color:var(--text);">${trackingProgress.done_steps || 0}/${trackingProgress.step_count || 0} steps done</span>
                <span style="font-size:10px;padding:3px 7px;border:1px solid var(--border);border-radius:999px;background:var(--card);color:var(--text);">${trackingProgress.case_count || 0} cases</span>
                <span style="font-size:10px;padding:3px 7px;border:1px solid var(--border);border-radius:999px;background:var(--card);color:var(--text);">${trackingProgress.recent_passes || 0} recent passes</span>
              </div>
            </div>
            <button onclick="studioMediaOpenProject('${esc(trackingProjectId)}')" style="background:var(--accent);border:1px solid var(--accent);color:#000;border-radius:7px;padding:7px 11px;font-size:11px;font-weight:700;cursor:pointer;">Open in Projects</button>
          </div>
        </section>
      ` : '';

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

      const remixLab = `
        <section style="border:1px solid color-mix(in srgb,var(--accent) 42%, var(--border));border-radius:12px;background:linear-gradient(135deg,color-mix(in srgb,var(--accent) 12%, var(--card)),var(--card));padding:14px;margin-bottom:12px;box-shadow:0 10px 30px color-mix(in srgb,var(--accent) 8%, transparent);">
          <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap;margin-bottom:10px;">
            <div>
              <div style="font-size:10px;font-weight:800;color:var(--accent);text-transform:uppercase;letter-spacing:.08em;">Remix Lab</div>
              <div style="font-size:15px;font-weight:900;color:var(--text);margin-top:2px;">Two songs in, mashup or new song out</div>
              <div style="font-size:11px;color:var(--text-dim);margin-top:4px;">Creates a local WAV preview, a vocal-guide melody from poems/suggestions, lyrics, and a provider handoff manifest for external generation services.</div>
            </div>
            <button onclick="studioMediaCreateRemix()" style="background:var(--accent);border:1px solid var(--accent);color:#000;border-radius:8px;padding:8px 13px;font-size:11px;font-weight:800;cursor:pointer;">Create Mix</button>
          </div>
          <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-bottom:10px;">
            <label style="display:flex;flex-direction:column;gap:4px;font-size:10px;font-weight:700;color:var(--text-dim);text-transform:uppercase;letter-spacing:.04em;">Song A
              <input id="studio-remix-song-a" placeholder="Title, artist, URL, or local source" style="background:var(--bg);border:1px solid var(--border);border-radius:7px;color:var(--text);padding:8px;font-size:12px;text-transform:none;letter-spacing:0;">
              <input id="studio-remix-song-a-file" type="file" accept="audio/*" style="background:var(--bg);border:1px dashed var(--border);border-radius:7px;color:var(--text-dim);padding:7px;font-size:11px;text-transform:none;letter-spacing:0;">
            </label>
            <label style="display:flex;flex-direction:column;gap:4px;font-size:10px;font-weight:700;color:var(--text-dim);text-transform:uppercase;letter-spacing:.04em;">Song B
              <input id="studio-remix-song-b" placeholder="Title, artist, URL, or local source" style="background:var(--bg);border:1px solid var(--border);border-radius:7px;color:var(--text);padding:8px;font-size:12px;text-transform:none;letter-spacing:0;">
              <input id="studio-remix-song-b-file" type="file" accept="audio/*" style="background:var(--bg);border:1px dashed var(--border);border-radius:7px;color:var(--text-dim);padding:7px;font-size:11px;text-transform:none;letter-spacing:0;">
            </label>
            <label style="display:flex;flex-direction:column;gap:4px;font-size:10px;font-weight:700;color:var(--text-dim);text-transform:uppercase;letter-spacing:.04em;">Mode
              <select id="studio-remix-mode" style="background:var(--bg);border:1px solid var(--border);border-radius:7px;color:var(--text);padding:8px;font-size:12px;text-transform:none;letter-spacing:0;">
                <option value="mashup">Mashup - blend both identities</option>
                <option value="new_song">Something new - use both as DNA</option>
              </select>
            </label>
            <label style="display:flex;flex-direction:column;gap:4px;font-size:10px;font-weight:700;color:var(--text-dim);text-transform:uppercase;letter-spacing:.04em;">Vocal Style
              <input id="studio-remix-vocal-style" placeholder="breathy pop, spoken hook, choir stack..." style="background:var(--bg);border:1px solid var(--border);border-radius:7px;color:var(--text);padding:8px;font-size:12px;text-transform:none;letter-spacing:0;">
            </label>
          </div>
          <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;">
            <label style="display:flex;flex-direction:column;gap:4px;font-size:10px;font-weight:700;color:var(--text-dim);text-transform:uppercase;letter-spacing:.04em;">Poem / Lyrics Seed
              <textarea id="studio-remix-poem" rows="5" placeholder="Paste a poem, chorus idea, loose lines, or nothing at all." style="resize:vertical;background:var(--bg);border:1px solid var(--border);border-radius:7px;color:var(--text);padding:8px;font-size:12px;text-transform:none;letter-spacing:0;"></textarea>
            </label>
            <label style="display:flex;flex-direction:column;gap:4px;font-size:10px;font-weight:700;color:var(--text-dim);text-transform:uppercase;letter-spacing:.04em;">Suggestions
              <textarea id="studio-remix-suggestions" rows="5" placeholder="Tempo, mood, genre, instruments, vocal direction, what to preserve, what to mutate." style="resize:vertical;background:var(--bg);border:1px solid var(--border);border-radius:7px;color:var(--text);padding:8px;font-size:12px;text-transform:none;letter-spacing:0;"></textarea>
            </label>
          </div>
          <div id="studio-remix-result" style="margin-top:10px;border:1px dashed color-mix(in srgb,var(--accent) 35%, var(--border));border-radius:9px;padding:10px;color:var(--text-dim);font-size:11px;background:color-mix(in srgb,var(--accent) 5%, transparent);">Ready. Add two song references, choose mashup or new-song mode, and Studio will produce a preview plus manifest.</div>
        </section>
      `;

      body.innerHTML = `
        ${remixLab}
        ${trackingProject}
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

  window.studioMediaOpenProject = function (projectId) {
    if (!projectId) return;
    if (typeof studioSetTab === 'function') studioSetTab('projects');
    setTimeout(() => {
      if (typeof projectsSelect === 'function') projectsSelect(projectId);
    }, 120);
  };

  function remixValue(id) {
    return document.getElementById(id)?.value?.trim() || '';
  }

  window.studioMediaCreateRemix = async function () {
    const result = document.getElementById('studio-remix-result');
    const fileA = document.getElementById('studio-remix-song-a-file')?.files?.[0] || null;
    const fileB = document.getElementById('studio-remix-song-b-file')?.files?.[0] || null;
    const payload = {
      song_a: remixValue('studio-remix-song-a') || (fileA ? fileA.name : ''),
      song_b: remixValue('studio-remix-song-b') || (fileB ? fileB.name : ''),
      mode: remixValue('studio-remix-mode') || 'mashup',
      poem: remixValue('studio-remix-poem'),
      suggestions: remixValue('studio-remix-suggestions'),
      vocal_style: remixValue('studio-remix-vocal-style') || 'clear guide vocal',
      duration_sec: 16
    };
    if (!payload.song_a || !payload.song_b) {
      if (result) result.innerHTML = '<span style="color:var(--danger,#f77);">Add both Song A and Song B first.</span>';
      return;
    }
    if (result) {
      result.innerHTML = '<span style="color:var(--accent);font-weight:800;">Creating mix...</span> Rendering a local audio preview and vocal guide.';
    }
    try {
      let requestBody = JSON.stringify(payload);
      let headers = { 'Content-Type': 'application/json' };
      if (fileA || fileB) {
        requestBody = new FormData();
        Object.entries(payload).forEach(([key, value]) => requestBody.append(key, value));
        if (fileA) requestBody.append('song_a_file', fileA);
        if (fileB) requestBody.append('song_b_file', fileB);
        headers = {};
      }
      const response = await fetch('/api/media/mix-songs', { method: 'POST', headers, body: requestBody });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || 'mix failed');
      const lyrics = (data.lyrics || []).map(line => `<div>${esc(line)}</div>`).join('');
      const sources = (data.source_layers || []).map(line => `<div>${esc(line)}</div>`).join('');
      const handoff = (data.provider_handoff || []).map(item => `
        <span style="display:inline-flex;border:1px solid var(--border);border-radius:999px;padding:3px 7px;margin:2px;background:var(--card);color:var(--text-dim);">${esc(item.role || 'adapter')}</span>
      `).join('');
      if (result) {
        result.innerHTML = `
          <div style="display:flex;justify-content:space-between;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px;">
            <div style="color:var(--text);font-weight:800;">Mix created: <code>${esc(data.run_id)}</code></div>
            ${data.manifest_url ? `<a href="${esc(data.manifest_url)}" target="_blank" style="color:var(--accent);font-weight:700;">Open manifest</a>` : ''}
          </div>
          ${data.artifact_url ? `<audio controls preload="metadata" src="${esc(data.artifact_url)}" style="width:100%;margin-bottom:8px;"></audio>` : ''}
          <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;">
            <div style="border:1px solid var(--border);border-radius:8px;padding:8px;background:var(--card);">
              <div style="font-size:10px;text-transform:uppercase;letter-spacing:.05em;color:var(--text-dim);font-weight:800;margin-bottom:5px;">Generated Lyrics</div>
              <div style="color:var(--text);line-height:1.45;">${lyrics}</div>
            </div>
            <div style="border:1px solid var(--border);border-radius:8px;padding:8px;background:var(--card);">
              <div style="font-size:10px;text-transform:uppercase;letter-spacing:.05em;color:var(--text-dim);font-weight:800;margin-bottom:5px;">Provider Handoff</div>
              <div>${handoff}</div>
              ${sources ? `<div style="margin-top:7px;color:var(--text);">${sources}</div>` : ''}
              <div style="margin-top:7px;color:var(--text-dim);">${esc(data.log || '')}</div>
            </div>
          </div>
        `;
      }
    } catch (err) {
      if (result) result.innerHTML = `<span style="color:var(--danger,#f77);">Mix failed: ${esc(err.message || err)}</span>`;
    }
  };
})();
