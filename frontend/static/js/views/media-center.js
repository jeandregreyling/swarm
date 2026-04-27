/* media-center.js — Media Center tile framework */

let _mediaCenterState = null;
let _mediaCenterSelectedProjectId = null;

function initMediaCenter() {
  _mediaCenterWireResizer();
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
  const lanes = project.timeline?.lanes || [];
  const clips = project.timeline?.clips || [];
  const synths = _mediaCenterState?.synths?.registry || [];
  const accounts = _mediaCenterState?.accounts?.registry || _mediaCenterState?.media_accounts || [];
  const agents = _mediaCenterState?.models?.agents || [];
  const swarms = _mediaCenterState?.linked_swarms?.nodes || [];
  const laneOptions = lanes.map(lane => `<option value="${_mcEsc(lane.id)}">${_mcEsc(lane.name)} · ${_mcEsc(lane.kind)}</option>`).join('');
  const synthOptions = synths.map(synth => `<option value="${_mcEsc(synth.id)}">${_mcEsc(synth.name)} · ${_mcEsc(synth.status)}</option>`).join('');
  const accountOptions = accounts.map(account => `<option value="${_mcEsc(account.id)}">${_mcEsc(account.name)} · ${_mcEsc(account.status)}</option>`).join('');
  const agentOptions = '<option value="">auto</option>' + agents.map(agent => `<option value="${_mcEsc(agent.agent)}">${_mcEsc(agent.label || agent.agent)} · ${_mcEsc(agent.model || 'model')}</option>`).join('');
  const swarmOptions = '<option value="">local</option>' + swarms.map(node => `<option value="${_mcEsc(node.node_id)}">${_mcEsc(node.name || node.node_id)} · ${node.media_relevant ? 'media-ready' : _mcEsc(node.role || 'node')}</option>`).join('');
  const clipRows = clips.map(clip => {
    const lane = lanes.find(item => item.id === clip.lane_id);
    const width = Math.max(6, Math.min(100, ((Number(clip.duration_sec) || 1) / Math.max(1, Number(project.duration_sec) || 30)) * 100));
    const offset = Math.max(0, Math.min(92, ((Number(clip.start_sec) || 0) / Math.max(1, Number(project.duration_sec) || 30)) * 100));
    return `<div class="media-timeline-clip">
      <div class="media-mini-row"><strong>${_mcEsc(clip.name)}</strong><span>${_mcEsc(lane?.name || clip.lane_id)}</span><span>${_mcEsc(clip.kind)} · ${_mcEsc(clip.status)}</span></div>
      <div class="media-timeline-track"><span style="left:${offset}%;width:${width}%;"></span></div>
      ${clip.prompt ? `<div class="media-project-prompt">${_mcEsc(clip.prompt)}</div>` : ''}
    </div>`;
  }).join('');
  const synthRows = (project.synth_runs || []).slice(0, 5).map(take => `
    <div class="media-mini-row"><strong>${_mcEsc(take.synth_name || take.synth_id)}</strong><span>${_mcEsc(take.status)}</span><span>${_mcEsc(take.duration_sec)}s</span></div>
  `).join('');
  const referenceRows = (project.media_refs || []).slice(0, 6).map(ref => `
    <div class="media-mini-row"><strong>${_mcEsc(ref.title)}</strong><span>${_mcEsc(ref.account_name || ref.account_id)}</span><span>${_mcEsc(ref.knowledge_status || ref.status)}</span></div>
  `).join('');

  return `
    <div class="media-detail-head">
      <div>
        <div class="media-detail-title">${_mcEsc(project.name)}</div>
        <div class="media-detail-meta">${_mcEsc(project.medium)} · ${_mcEsc(project.style || 'style not set')} · ${project.duration_sec || 0}s · studio ${_mcEsc(project.studio_project_id || 'pending')}</div>
      </div>
      <div class="media-detail-actions">
        ${studioLink}
        <button class="media-inline-btn" onclick="mediaCenterCopyHandoff()">Copy handoff</button>
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
      <section class="media-detail-panel">
        <div class="media-panel-title">Editor Timeline</div>
        <div class="media-project-meta">${_mcEsc(project.timeline?.tempo_bpm || 120)} bpm · ${_mcEsc(project.timeline?.time_signature || '4/4')} · ${clips.length} clips</div>
        ${clipRows || '<div class="media-empty">No clips yet.</div>'}
        <div class="media-timeline-form">
          <select id="media-center-clip-lane">${laneOptions}</select>
          <input id="media-center-clip-name" placeholder="Clip/take name">
          <input id="media-center-clip-start" type="number" min="0" step="0.25" value="0" title="Start seconds">
          <input id="media-center-clip-duration" type="number" min="0.25" step="0.25" value="4" title="Duration seconds">
          <input id="media-center-clip-prompt" placeholder="Prompt / source note">
          <button class="media-inline-btn media-inline-btn-primary" onclick="mediaCenterAddClip()">Add clip</button>
        </div>
      </section>
      <section class="media-detail-panel">
        <div class="media-panel-title">AI Synth Takes</div>
        ${synthRows || '<div class="media-empty">No synth takes yet.</div>'}
        <div class="media-timeline-form">
          <select id="media-center-synth-id">${synthOptions}</select>
          <select id="media-center-synth-lane">${laneOptions}</select>
          <input id="media-center-synth-start" type="number" min="0" step="0.25" value="0" title="Start seconds">
          <input id="media-center-synth-duration" type="number" min="0.25" step="0.25" value="4" title="Duration seconds">
          <input id="media-center-synth-prompt" placeholder="Synth prompt">
          <button class="media-inline-btn media-inline-btn-primary" onclick="mediaCenterCreateSynthTake()">Create take</button>
        </div>
      </section>
      <section class="media-detail-panel">
        <div class="media-panel-title">Media References</div>
        ${referenceRows || '<div class="media-empty">No account imports or feed references yet.</div>'}
        <div class="media-timeline-form">
          <select id="media-center-ref-account">${accountOptions}</select>
          <select id="media-center-ref-type">
            <option value="music">music</option>
            <option value="video">video</option>
            <option value="feed">feed</option>
            <option value="local">local</option>
          </select>
          <input id="media-center-ref-title" placeholder="Reference title">
          <input id="media-center-ref-url" placeholder="URL or local path">
          <input id="media-center-ref-notes" placeholder="Notes / indexing hint">
          <button class="media-inline-btn media-inline-btn-primary" onclick="mediaCenterAddReference()">Index</button>
        </div>
      </section>
      <section class="media-detail-panel">
        <div class="media-panel-title">Model / Swarm Routing</div>
        <div class="media-project-meta">music ${_mcEsc(project.routing?.music_agent || 'auto')} · video ${_mcEsc(project.routing?.video_agent || 'auto')} · ${_mcEsc(project.routing?.handoff_mode || 'local-first')}</div>
        <div class="media-timeline-form">
          <select id="media-center-route-music">${agentOptions}</select>
          <select id="media-center-route-video">${agentOptions}</select>
          <select id="media-center-route-swarm">${swarmOptions}</select>
          <select id="media-center-route-mode">
            <option value="local-first">local-first</option>
            <option value="swarm-assisted">swarm-assisted</option>
            <option value="model-directed">model-directed</option>
          </select>
          <button class="media-inline-btn media-inline-btn-primary" onclick="mediaCenterUpdateRouting()">Save route</button>
        </div>
      </section>
    </div>
  `;
}

function _mediaCenterContextPanels(state) {
  const trackingProjectId = state.studio?.tracking_project_id || '';
  const trackingProgress = state.tracking?.progress || {};
  const trackingSteps = (state.tracking?.steps || []).slice(0, 8).map(step => `
    <div class="media-mini-row"><strong>${_mcEsc(step.title)}</strong><span>${_mcEsc(step.owner || 'seven')}</span><span>${_mcEsc(step.status || 'todo')}</span></div>
  `).join('');
  const trackingRuns = (state.tracking?.recent_runs || []).slice(0, 5).map(run => `
    <div class="media-mini-row"><strong>${_mcEsc(run.status || 'run')}</strong><span>${_mcEsc(run.script_id || '')}</span><span>${_mcEsc(run.duration_ms != null ? run.duration_ms + 'ms' : run.run_id)}</span></div>
  `).join('');
  const tracking = trackingProjectId ? `
    <div class="media-runtime-grid-mini">
      <span class="media-runtime-chip is-on">${trackingProgress.done_steps || 0}/${trackingProgress.step_count || 0} steps done</span>
      <span class="media-runtime-chip">${trackingProgress.case_count || 0} cases</span>
      <span class="media-runtime-chip">${trackingProgress.recent_passes || 0} recent passes</span>
      <span class="media-runtime-chip">${trackingProgress.recent_failures || 0} recent failures</span>
    </div>
    <div class="media-mini-row">
      <strong>${_mcEsc(state.studio?.tracking_project_name || 'Media Center + Studio Integration')}</strong>
      <span>${_mcEsc(trackingProjectId)}</span>
      <button class="media-inline-btn" onclick="mediaCenterOpenStudioProject(${JSON.stringify(trackingProjectId)})">Open</button>
    </div>
    <div style="margin-top:8px;">${trackingSteps || '<div class="media-empty">No tracking steps yet.</div>'}</div>
    <div style="margin-top:8px;">${trackingRuns || '<div class="media-empty">No verification runs recorded yet.</div>'}</div>
  ` : '<div class="media-empty">Tracking project has not been seeded yet.</div>';

  const chatActions = (state.chat?.actions || []).map(action => `
    <span class="media-runtime-chip is-on">${_mcEsc(action.phrase)}</span>
  `).join('') || '<div class="media-empty">No chat actions advertised yet.</div>';

  const modelRows = (state.models?.agents || []).slice(0, 8).map(agent => `
    <div class="media-mini-row"><strong>${_mcEsc(agent.label || agent.agent)}</strong><span>${_mcEsc(agent.agent)}</span><span>${_mcEsc(agent.model || 'model pending')}</span></div>
  `).join('') || '<div class="media-empty">No media-relevant model candidates found yet.</div>';

  const synthRows = (state.synths?.registry || []).slice(0, 8).map(synth => `
    <div class="media-mini-row"><strong>${_mcEsc(synth.name)}</strong><span>${_mcEsc(synth.kind)}</span><span>${_mcEsc(synth.status)}</span></div>
  `).join('') || '<div class="media-empty">No synth registry loaded yet.</div>';

  const takeRows = (state.synths?.recent_takes || []).slice(0, 6).map(take => `
    <div class="media-mini-row"><strong>${_mcEsc(take.synth_name || take.synth_id)}</strong><span>${_mcEsc(take.project_name || take.project_id)}</span><span>${_mcEsc(take.status)}</span></div>
  `).join('') || '<div class="media-empty">No synth takes yet.</div>';

  const swarmRows = (state.linked_swarms?.nodes || []).slice(0, 8).map(node => `
    <div class="media-mini-row"><strong>${_mcEsc(node.name || node.node_id)}</strong><span>${_mcEsc(node.role || 'node')}</span><span>${node.media_relevant ? 'media-ready' : _mcEsc((node.capabilities || []).join(', ') || 'registered')}</span></div>
  `).join('') || '<div class="media-empty">No linked swarms registered yet.</div>';

  const routeRows = (state.routing?.active_routes || []).slice(0, 8).map(route => `
    <div class="media-mini-row"><strong>${_mcEsc(route.project_name || route.project_id)}</strong><span>${_mcEsc(route.handoff_mode)}</span><span>${_mcEsc(route.music_agent || route.video_agent || route.swarm_node_id)}</span></div>
  `).join('') || '<div class="media-empty">No project-specific media routes saved yet.</div>';
  const activeProject = (state.projects || []).find(project => project.id === _mediaCenterSelectedProjectId) || (state.projects || [])[0] || {};

  const interests = (state.interests?.relevant || []).map(item => `
    <span class="media-runtime-chip is-on">${_mcEsc(item.topic)} · ${_mcEsc(item.category || 'general')}</span>
  `).join('') || '<div class="media-empty">No media-linked interests yet.</div>';

  const feeds = (state.feeds?.subscriptions || []).map(feed => `
    <div class="media-mini-row"><strong>${_mcEsc(feed.title || feed.kind)}</strong><span>${_mcEsc(feed.kind)}</span><span>${_mcEsc(feed.status || 'pending')}</span></div>
  `).join('') || '<div class="media-empty">No connected feeds yet.</div>';

  const accountRows = (state.accounts?.registry || []).map(account => `
    <div class="media-mini-row"><strong>${_mcEsc(account.name)}</strong><span>${_mcEsc(account.kind)}</span><span>${_mcEsc(account.status)}</span><button class="media-inline-btn" onclick="mediaCenterLinkAccount(${JSON.stringify(account.id)})">Link</button></div>
  `).join('') || '<div class="media-empty">No media account manifests loaded yet.</div>';

  const knowledgeRows = (state.knowledge?.references || []).slice(0, 8).map(ref => `
    <div class="media-mini-row"><strong>${_mcEsc(ref.title)}</strong><span>${_mcEsc(ref.project_name || ref.project_id)}</span><span>${_mcEsc(ref.account_name || ref.account_id)}</span></div>
  `).join('') || '<div class="media-empty">No indexed media references yet.</div>';

  const suggestions = (state.feeds?.suggestions || []).map(item => `
    <div class="media-mini-row"><strong>${_mcEsc(item.title)}</strong><span>${_mcEsc(item.kind)}</span><span>${_mcEsc(item.reason)}</span></div>
  `).join('') || '<div class="media-empty">No feed suggestions yet.</div>';

  const spine = (state.spine?.items || []).map(item => `
    <div class="media-mini-row"><strong>${_mcEsc(item.kind || 'event')}</strong><span>${_mcEsc(item.severity || 'info')}</span><span>${_mcEsc(item.message || '')}</span></div>
  `).join('') || '<div class="media-empty">No media spine events yet.</div>';

  return `
    <section class="media-detail-panel">
      <div class="media-panel-title">Projects Tracker</div>
      ${tracking}
    </section>
    <section class="media-detail-panel">
      <div class="media-panel-title">Chat Actions</div>
      <div class="media-runtime-grid-mini">${chatActions}</div>
    </section>
    <section class="media-detail-panel">
      <div class="media-panel-title">Model Candidates</div>
      ${modelRows}
    </section>
    <section class="media-detail-panel">
      <div class="media-panel-title">Synth Registry</div>
      ${synthRows}
      <div style="margin-top:8px;">${takeRows}</div>
    </section>
    <section class="media-detail-panel">
      <div class="media-panel-title">Linked Swarms</div>
      ${swarmRows}
    </section>
    <section class="media-detail-panel">
      <div class="media-panel-title">Saved Routes</div>
      ${routeRows}
    </section>
    <section class="media-detail-panel">
      <div class="media-panel-title">Handoff Manifest</div>
      <div class="media-mini-row"><strong>${_mcEsc(activeProject.name || 'No project')}</strong><span>${_mcEsc(activeProject.medium || '')}</span><span>${_mcEsc(activeProject.routing?.handoff_mode || 'local-first')}</span></div>
      <button class="media-inline-btn media-inline-btn-primary" onclick="mediaCenterCopyHandoff()">Copy manifest</button>
    </section>
    <section class="media-detail-panel">
      <div class="media-panel-title">Interest Signals</div>
      <div class="media-runtime-grid-mini">${interests}</div>
    </section>
    <section class="media-detail-panel">
      <div class="media-panel-title">Connected Feeds</div>
      ${feeds}
    </section>
    <section class="media-detail-panel">
      <div class="media-panel-title">Media Accounts</div>
      ${accountRows}
    </section>
    <section class="media-detail-panel">
      <div class="media-panel-title">Knowledge Index</div>
      ${knowledgeRows}
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

async function mediaCenterAddClip() {
  if (!_mediaCenterSelectedProjectId) {
    if (typeof showToast === 'function') showToast('Choose a project first.', 'info');
    return;
  }
  const name = document.getElementById('media-center-clip-name')?.value?.trim();
  if (!name) {
    document.getElementById('media-center-clip-name')?.focus();
    return;
  }
  const laneId = document.getElementById('media-center-clip-lane')?.value || '';
  const startSec = parseFloat(document.getElementById('media-center-clip-start')?.value || '0');
  const durationSec = parseFloat(document.getElementById('media-center-clip-duration')?.value || '4');
  const prompt = document.getElementById('media-center-clip-prompt')?.value?.trim() || '';
  const response = await fetch(`/api/media-center/projects/${encodeURIComponent(_mediaCenterSelectedProjectId)}/clips`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, lane_id: laneId, start_sec: startSec, duration_sec: durationSec, prompt, source: 'manual-editor' }),
  });
  const data = await response.json();
  if (!data.ok) {
    if (typeof showToast === 'function') showToast(data.error || 'Clip add failed.', 'error');
    return;
  }
  if (typeof showToast === 'function') showToast('Timeline clip added.', 'success');
  mediaCenterRefresh();
}

async function mediaCenterCreateSynthTake() {
  if (!_mediaCenterSelectedProjectId) {
    if (typeof showToast === 'function') showToast('Choose a project first.', 'info');
    return;
  }
  const prompt = document.getElementById('media-center-synth-prompt')?.value?.trim();
  if (!prompt) {
    document.getElementById('media-center-synth-prompt')?.focus();
    return;
  }
  const synthId = document.getElementById('media-center-synth-id')?.value || 'local-tone';
  const laneId = document.getElementById('media-center-synth-lane')?.value || '';
  const startSec = parseFloat(document.getElementById('media-center-synth-start')?.value || '0');
  const durationSec = parseFloat(document.getElementById('media-center-synth-duration')?.value || '4');
  const response = await fetch(`/api/media-center/projects/${encodeURIComponent(_mediaCenterSelectedProjectId)}/synth-takes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ synth_id: synthId, lane_id: laneId, start_sec: startSec, duration_sec: durationSec, prompt }),
  });
  const data = await response.json();
  if (!data.ok) {
    if (typeof showToast === 'function') showToast(data.error || 'Synth take failed.', 'error');
    return;
  }
  if (typeof showToast === 'function') showToast('Synth take added to timeline.', 'success');
  mediaCenterRefresh();
}

async function mediaCenterAddReference() {
  if (!_mediaCenterSelectedProjectId) {
    if (typeof showToast === 'function') showToast('Choose a project first.', 'info');
    return;
  }
  const title = document.getElementById('media-center-ref-title')?.value?.trim();
  if (!title) {
    document.getElementById('media-center-ref-title')?.focus();
    return;
  }
  const accountId = document.getElementById('media-center-ref-account')?.value || 'custom-feed';
  const mediaType = document.getElementById('media-center-ref-type')?.value || 'media';
  const url = document.getElementById('media-center-ref-url')?.value?.trim() || '';
  const notes = document.getElementById('media-center-ref-notes')?.value?.trim() || '';
  const response = await fetch(`/api/media-center/projects/${encodeURIComponent(_mediaCenterSelectedProjectId)}/references`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, account_id: accountId, media_type: mediaType, url, notes }),
  });
  const data = await response.json();
  if (!data.ok) {
    if (typeof showToast === 'function') showToast(data.error || 'Reference indexing failed.', 'error');
    return;
  }
  if (typeof showToast === 'function') showToast('Media reference indexed into Knowledge.', 'success');
  mediaCenterRefresh();
}

async function mediaCenterUpdateRouting() {
  if (!_mediaCenterSelectedProjectId) {
    if (typeof showToast === 'function') showToast('Choose a project first.', 'info');
    return;
  }
  const musicAgent = document.getElementById('media-center-route-music')?.value || '';
  const videoAgent = document.getElementById('media-center-route-video')?.value || '';
  const swarmNodeId = document.getElementById('media-center-route-swarm')?.value || '';
  const handoffMode = document.getElementById('media-center-route-mode')?.value || 'local-first';
  const response = await fetch(`/api/media-center/projects/${encodeURIComponent(_mediaCenterSelectedProjectId)}/routing`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ music_agent: musicAgent, video_agent: videoAgent, swarm_node_id: swarmNodeId, handoff_mode: handoffMode }),
  });
  const data = await response.json();
  if (!data.ok) {
    if (typeof showToast === 'function') showToast(data.error || 'Route update failed.', 'error');
    return;
  }
  if (typeof showToast === 'function') showToast('Model and swarm route saved.', 'success');
  mediaCenterRefresh();
}

async function mediaCenterLinkAccount(accountId) {
  if (!accountId) return;
  const account = (_mediaCenterState?.accounts?.registry || []).find(item => item.id === accountId) || {};
  const source = prompt(`Feed URL, handle, or local path for ${account.name || accountId}:`, account.source || '');
  if (source === null) return;
  const response = await fetch(`/api/media-center/accounts/${encodeURIComponent(accountId)}/link`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url: source, title: account.name || accountId }),
  });
  const data = await response.json();
  if (!data.ok) {
    if (typeof showToast === 'function') showToast(data.error || 'Account link failed.', 'error');
    return;
  }
  if (typeof showToast === 'function') showToast('Media account linked into Feeds.', 'success');
  mediaCenterRefresh();
}

async function mediaCenterCopyHandoff() {
  if (!_mediaCenterSelectedProjectId) {
    if (typeof showToast === 'function') showToast('Choose a project first.', 'info');
    return;
  }
  const response = await fetch(`/api/media-center/projects/${encodeURIComponent(_mediaCenterSelectedProjectId)}/handoff`);
  const data = await response.json();
  if (!data.ok) {
    if (typeof showToast === 'function') showToast(data.error || 'Handoff manifest failed.', 'error');
    return;
  }
  const text = JSON.stringify(data.manifest, null, 2);
  try {
    await navigator.clipboard.writeText(text);
    if (typeof showToast === 'function') showToast('Media handoff manifest copied.', 'success');
  } catch (_) {
    console.log('Media handoff manifest', data.manifest);
    if (typeof showToast === 'function') showToast('Clipboard unavailable; manifest printed to console.', 'info');
  }
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

function _mediaCenterWireResizer() {
  const grid = document.getElementById('media-center-grid');
  const sidebar = document.querySelector('#media-center-view .media-sidebar');
  const grip = document.getElementById('media-center-resizer');
  if (!grid || !sidebar || !grip || grip.__mediaCenterWired) return;
  grip.__mediaCenterWired = true;

  const storageKey = 'fridays.mediaCenter.sidebarWidth';
  const applyWidth = (width) => {
    const shellWidth = grid.getBoundingClientRect().width || window.innerWidth;
    const max = Math.max(320, Math.min(620, shellWidth - 420));
    const next = Math.max(280, Math.min(max, Math.round(width)));
    grid.style.setProperty('--media-center-sidebar-width', next + 'px');
    return next;
  };

  const saved = parseInt(localStorage.getItem(storageKey) || '', 10);
  if (Number.isFinite(saved)) applyWidth(saved);

  const start = (event) => {
    if (event.button != null && event.button !== 0) return;
    event.preventDefault();
    const pointerId = event.pointerId;
    const startX = event.clientX;
    const startWidth = sidebar.getBoundingClientRect().width;
    grid.classList.add('is-resizing');
    if (pointerId != null) grip.setPointerCapture(pointerId);

    const move = (ev) => {
      const width = applyWidth(startWidth + (ev.clientX - startX));
      localStorage.setItem(storageKey, String(width));
    };
    const stop = () => {
      grid.classList.remove('is-resizing');
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', stop);
      window.removeEventListener('pointercancel', stop);
    };

    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', stop);
    window.addEventListener('pointercancel', stop);
  };

  grip.addEventListener('pointerdown', start);
  grip.addEventListener('dblclick', () => {
    localStorage.removeItem(storageKey);
    applyWidth(340);
  });
  grip.addEventListener('keydown', (event) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home'].includes(event.key)) return;
    event.preventDefault();
    const current = sidebar.getBoundingClientRect().width || 340;
    const next = event.key === 'Home' ? 340 : current + (event.key === 'ArrowRight' ? 24 : -24);
    localStorage.setItem(storageKey, String(applyWidth(next)));
  });
}

function _mcEsc(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
