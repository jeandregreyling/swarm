/* media-center.js — Media Center tile framework */

let _mediaCenterState = null;
let _mediaCenterSelectedProjectId = null;

function initMediaCenter() {
  return mediaCenterRefresh();
}

async function mediaCenterRefresh() {
  const status = document.getElementById('media-center-status');
  if (status) status.textContent = 'loading';
  try {
    const response = await fetch('/api/media-center/state');
    const data = await response.json();
    if (!data.ok) throw new Error(data.error || 'failed to load');
    _mediaCenterState = data;
    if (!_mediaCenterSelectedProjectId && data.projects?.length) {
      _mediaCenterSelectedProjectId = data.projects[0].id;
    }
    _renderMediaCenter();
    if (status) status.textContent = _mediaCenterRuntimeBadge(data.runtime);
  } catch (err) {
    if (typeof showToast === 'function') showToast('Media Center failed to load: ' + (err.message || err), 'error');
    if (status) status.textContent = 'offline';
  }
}

function _mediaCenterRuntimeBadge(runtime) {
  const audioReady = !!(runtime?.audio?.ffmpeg && (runtime?.audio?.ollama || runtime?.audio?.lmstudio));
  const videoReady = !!runtime?.video?.ffmpeg;
  if (audioReady && videoReady) return 'local-ready';
  if (audioReady || videoReady) return 'partial';
  return 'framework';
}

function _renderMediaCenter() {
  const state = _mediaCenterState || {};
  const project = (state.projects || []).find(p => p.id === _mediaCenterSelectedProjectId) || state.projects?.[0] || null;
  if (project) _mediaCenterSelectedProjectId = project.id;

  const counts = state.counts || {};
  const pills = document.getElementById('media-center-topline');
  if (pills) {
    pills.innerHTML = `
      <span class="media-pill">${counts.projects || 0} projects</span>
      <span class="media-pill">${counts.queued_jobs || 0} queued</span>
      <span class="media-pill">${counts.completed_jobs || 0} completed</span>
    `;
  }

  const runtime = document.getElementById('media-center-runtime-grid');
  if (runtime) {
    runtime.innerHTML = _mediaCenterRuntimeCards(state.runtime || {});
  }

  const projectList = document.getElementById('media-center-project-list');
  if (projectList) {
    const projects = state.projects || [];
    projectList.innerHTML = projects.length ? projects.map(project => {
      const active = project.id === _mediaCenterSelectedProjectId ? ' is-active' : '';
      return `<button class="media-project-card${active}" onclick="mediaCenterSelectProject(${JSON.stringify(project.id)})">
        <div class="media-project-title">${_mcEsc(project.name)}</div>
        <div class="media-project-meta">${_mcEsc(project.medium)} · ${_mcEsc(project.status)} · ${project.duration_sec || 0}s</div>
        <div class="media-project-prompt">${_mcEsc(project.prompt || 'No prompt yet')}</div>
      </button>`;
    }).join('') : '<div class="media-empty">No projects yet. Create one on the left to start the pipeline.</div>';
  }

  const detail = document.getElementById('media-center-project-detail');
  if (detail) {
    detail.innerHTML = project ? _mediaCenterProjectDetail(project) : '<div class="media-empty">Pick or create a project to inspect its media graph.</div>';
  }

  const jobs = document.getElementById('media-center-job-list');
  if (jobs) {
    const rows = state.jobs || [];
    jobs.innerHTML = rows.length ? rows.map(job => {
      const action = job.status === 'queued' || job.status === 'ready'
        ? `<button class="media-inline-btn media-inline-btn-primary" onclick="mediaCenterSimulateJob(${JSON.stringify(job.id)})">Simulate run</button>`
        : '<span class="media-inline-hint">ready for real runner</span>';
      return `<div class="media-job-row">
        <div class="media-job-main">
          <div class="media-job-title">${_mcEsc(job.project_name || job.project_id)} <span class="media-job-type">${_mcEsc(job.job_type)}</span></div>
          <div class="media-job-meta">${_mcEsc(job.status)} · ${_mcEsc(job.engine)} · ${_mcEsc(job.mode)}</div>
          <div class="media-job-notes">${_mcEsc(job.notes || '')}</div>
        </div>
        <div class="media-job-actions">${action}</div>
      </div>`;
    }).join('') : '<div class="media-empty">No queued jobs yet.</div>';
  }

  const presets = document.getElementById('media-center-preset-list');
  if (presets) {
    presets.innerHTML = (state.presets || []).map(preset => `
      <div class="media-preset-card">
        <div class="media-preset-title">${_mcEsc(preset.name)}</div>
        <div class="media-preset-summary">${_mcEsc(preset.summary)}</div>
        <div class="media-preset-meta">${_mcEsc((preset.music_models || []).join(', ') || 'No music model')} | ${_mcEsc((preset.video_models || []).join(', ') || 'No video model')}</div>
      </div>
    `).join('');
  }

  const context = document.getElementById('media-center-context-grid');
  if (context) {
    context.innerHTML = _mediaCenterContextPanels(state);
  }
}

function _mediaCenterRuntimeCards(runtime) {
  const rows = [
    ['Audio stack', runtime.audio, ['ffmpeg', 'ollama', 'lmstudio']],
    ['Video stack', runtime.video, ['ffmpeg', 'python', 'comfyui_hint']],
  ];
  return rows.map(([label, block, keys]) => `
    <div class="media-runtime-card">
      <div class="media-runtime-label">${label}</div>
      <div class="media-runtime-grid-mini">
        ${keys.map(key => {
          const on = !!block?.[key];
          return `<span class="media-runtime-chip ${on ? 'is-on' : ''}">${_mcEsc(key.replace(/_/g, ' '))}: ${on ? 'on' : 'off'}</span>`;
        }).join('')}
      </div>
    </div>
  `).join('');
}

function _mediaCenterProjectDetail(project) {
  const studioLink = project.studio_project_id
    ? `<button class="media-inline-btn" onclick="mediaCenterOpenStudioProject(${JSON.stringify(project.studio_project_id)})">Open in Studio</button>`
    : '';
  const scenes = (project.scenes || []).map(scene => `<div class="media-mini-row"><strong>${_mcEsc(scene.name)}</strong><span>${scene.duration_sec}s</span><span>${_mcEsc(scene.goal)}</span></div>`).join('');
  const tracks = (project.tracks || []).map(track => `<div class="media-mini-row"><strong>${_mcEsc(track.name)}</strong><span>${_mcEsc(track.role)}</span><span>${_mcEsc(track.model_hint)}</span></div>`).join('');
  const deliverables = (project.deliverables || []).map(item => `<div class="media-mini-row"><strong>${_mcEsc(item.type)}</strong><span>${_mcEsc(item.format)}</span><span>${_mcEsc(item.target)}</span></div>`).join('');

  return `
    <div class="media-detail-head">
      <div>
        <div class="media-detail-title">${_mcEsc(project.name)}</div>
        <div class="media-detail-meta">${_mcEsc(project.medium)} · ${_mcEsc(project.style || 'style not set')} · ${project.duration_sec || 0}s · studio ${_mcEsc(project.studio_project_id || 'pending')}</div>
      </div>
      <div class="media-detail-actions">
        ${studioLink}
        <button class="media-inline-btn" onclick="mediaCenterQueueSelected('generate-audio')">Queue audio</button>
        <button class="media-inline-btn" onclick="mediaCenterQueueSelected('generate-video')">Queue video</button>
        <button class="media-inline-btn media-inline-btn-primary" onclick="mediaCenterQueueSelected('compile-preview')">Queue compile</button>
      </div>
    </div>
    <div class="media-detail-prompt">${_mcEsc(project.prompt || '')}</div>
    <div class="media-detail-grid">
      <section class="media-detail-panel">
        <div class="media-panel-title">Scene Map</div>
        ${scenes || '<div class="media-empty">No scenes yet.</div>'}
      </section>
      <section class="media-detail-panel">
        <div class="media-panel-title">Audio Lanes</div>
        ${tracks || '<div class="media-empty">No tracks yet.</div>'}
      </section>
      <section class="media-detail-panel">
        <div class="media-panel-title">Deliverables</div>
        ${deliverables || '<div class="media-empty">No deliverables yet.</div>'}
      </section>
    </div>
  `;
}

function _mediaCenterContextPanels(state) {
  const interests = (state.interests?.relevant || []).map(item => `
    <span class="media-runtime-chip is-on">${_mcEsc(item.topic)} · ${_mcEsc(item.category || 'general')}</span>
  `).join('') || '<div class="media-empty">No media-linked interests yet.</div>';

  const feeds = (state.feeds?.subscriptions || []).map(feed => `
    <div class="media-mini-row"><strong>${_mcEsc(feed.title || feed.kind)}</strong><span>${_mcEsc(feed.kind)}</span><span>${_mcEsc(feed.status || 'pending')}</span></div>
  `).join('') || '<div class="media-empty">No connected feeds yet.</div>';

  const suggestions = (state.feeds?.suggestions || []).map(item => `
    <div class="media-mini-row"><strong>${_mcEsc(item.title)}</strong><span>${_mcEsc(item.kind)}</span><span>${_mcEsc(item.reason)}</span></div>
  `).join('') || '<div class="media-empty">No feed suggestions yet.</div>';

  const spine = (state.spine?.items || []).map(item => `
    <div class="media-mini-row"><strong>${_mcEsc(item.kind || 'event')}</strong><span>${_mcEsc(item.severity || 'info')}</span><span>${_mcEsc(item.message || '')}</span></div>
  `).join('') || '<div class="media-empty">No media spine events yet.</div>';

  return `
    <section class="media-detail-panel">
      <div class="media-panel-title">Interest Signals</div>
      <div class="media-runtime-grid-mini">${interests}</div>
    </section>
    <section class="media-detail-panel">
      <div class="media-panel-title">Connected Feeds</div>
      ${feeds}
    </section>
    <section class="media-detail-panel">
      <div class="media-panel-title">Feed Suggestions</div>
      ${suggestions}
    </section>
    <section class="media-detail-panel">
      <div class="media-panel-title">Spine Trail</div>
      ${spine}
    </section>
  `;
}

function mediaCenterSelectProject(projectId) {
  _mediaCenterSelectedProjectId = projectId;
  _renderMediaCenter();
}

async function mediaCenterCreateProject() {
  const name = document.getElementById('media-center-project-name')?.value?.trim();
  const prompt = document.getElementById('media-center-project-prompt')?.value?.trim();
  const medium = document.getElementById('media-center-project-medium')?.value || 'audio-video';
  const style = document.getElementById('media-center-project-style')?.value?.trim();
  const durationSec = parseInt(document.getElementById('media-center-project-duration')?.value || '30', 10);

  if (!name || !prompt) {
    if (typeof showToast === 'function') showToast('Name and prompt are required.', 'info');
    return;
  }

  const response = await fetch('/api/media-center/projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, prompt, medium, style, duration_sec: durationSec, engine_mode: 'local-first' }),
  });
  const data = await response.json();
  if (!data.ok) {
    if (typeof showToast === 'function') showToast(data.error || 'Project creation failed.', 'error');
    return;
  }
  _mediaCenterSelectedProjectId = data.project.id;
  ['media-center-project-name', 'media-center-project-prompt', 'media-center-project-style'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  if (typeof showToast === 'function') showToast('Media project created.', 'success');
  mediaCenterRefresh();
}

async function mediaCenterQueueSelected(jobType) {
  if (!_mediaCenterSelectedProjectId) {
    if (typeof showToast === 'function') showToast('Choose a project first.', 'info');
    return;
  }
  const response = await fetch(`/api/media-center/projects/${encodeURIComponent(_mediaCenterSelectedProjectId)}/jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ job_type: jobType, mode: 'simulate', notes: 'Queued from Media Center shell.' }),
  });
  const data = await response.json();
  if (!data.ok) {
    if (typeof showToast === 'function') showToast(data.error || 'Queue failed.', 'error');
    return;
  }
  if (typeof showToast === 'function') showToast(jobType + ' queued.', 'success');
  mediaCenterRefresh();
}

async function mediaCenterSimulateJob(jobId) {
  const response = await fetch(`/api/media-center/jobs/${encodeURIComponent(jobId)}/simulate`, { method: 'POST' });
  const data = await response.json();
  if (!data.ok) {
    if (typeof showToast === 'function') showToast(data.error || 'Simulation failed.', 'error');
    return;
  }
  if (typeof showToast === 'function') showToast('Simulated local pipeline run complete.', 'success');
  mediaCenterRefresh();
}

function mediaCenterOpenStudioProject(projectId) {
  if (!projectId) return;
  if (typeof openWindow === 'function') openWindow('studio', 'Studio', 'view-studio');
  setTimeout(() => {
    if (typeof studioSetTab === 'function') studioSetTab('projects');
    if (typeof projectsSelect === 'function') projectsSelect(projectId);
  }, 180);
}

function _mcEsc(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
