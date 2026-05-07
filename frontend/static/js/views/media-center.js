/* media-center.js — DAW-first Media Center workspace */

let _mediaCenterState = null;
let _mediaCenterSelectedProjectId = null;
const _mediaCenterPanelDefaults = {
  'new-project': true,
  'project-rack': false,
  'composer-outline': false,
  'research-center': false,
  'bottom-dock': false,
};

function _mediaCenterPanelKey(key) {
  return `fridays.mediaCenter.v3.panel.${key}`;
}

function _mediaCenterTabKey(kind) {
  return `fridays.mediaCenter.v3.tab.${kind}`;
}

function _mediaCenterPanelCollapsed(key) {
  try {
    const saved = localStorage.getItem(_mediaCenterPanelKey(key));
    if (saved == null) return !!_mediaCenterPanelDefaults[key];
    return saved === '1';
  } catch (e) {
    return !!_mediaCenterPanelDefaults[key];
  }
}

function _mediaCenterSetPanelCollapsed(key, collapsed) {
  try {
    localStorage.setItem(_mediaCenterPanelKey(key), collapsed ? '1' : '0');
  } catch (e) {}
}

function _mediaCenterGetTab(kind, fallback) {
  try {
    return localStorage.getItem(_mediaCenterTabKey(kind)) || fallback;
  } catch (e) {
    return fallback;
  }
}

function _mediaCenterSetTab(kind, value) {
  try {
    localStorage.setItem(_mediaCenterTabKey(kind), value);
  } catch (e) {}
}

function _mediaCenterFocusModeEnabled() {
  try {
    return localStorage.getItem('fridays.mediaCenter.v3.focusMode') === '1';
  } catch (e) {
    return false;
  }
}

function _mediaCenterSetFocusMode(enabled) {
  try {
    localStorage.setItem('fridays.mediaCenter.v3.focusMode', enabled ? '1' : '0');
  } catch (e) {}
}

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
  const projects = state.projects || [];
  const project = projects.find((item) => item.id === _mediaCenterSelectedProjectId) || projects[0] || null;
  if (project) _mediaCenterSelectedProjectId = project.id;

  const counts = state.counts || {};
  const topline = document.getElementById('media-center-topline');
  if (topline) {
    topline.innerHTML = `
      <span class="media-pill">${counts.projects || 0} projects</span>
      <span class="media-pill">${counts.queued_jobs || 0} queued</span>
      <span class="media-pill">${counts.completed_jobs || 0} completed</span>
      <span class="media-pill">${state.knowledge?.indexed_count || 0} indexed refs</span>
      <span class="media-pill">${state.tracking?.progress?.done_steps || 0}/${state.tracking?.progress?.step_count || 0} plan steps</span>
    `;
  }

  const projectList = document.getElementById('media-center-project-list');
  if (projectList) {
    projectList.innerHTML = projects.length
      ? projects.map((item) => {
        const active = item.id === _mediaCenterSelectedProjectId ? ' is-active' : '';
        return `<button class="media-project-card${active}" onclick="mediaCenterSelectProject(${JSON.stringify(item.id)})">
          <div class="media-project-title">${_mcEsc(item.name)}</div>
          <div class="media-project-meta">${_mcEsc(item.medium)} · ${_mcEsc(item.status)} · ${item.duration_sec || 0}s</div>
          <div class="media-project-prompt">${_mcEsc(item.prompt || 'No prompt yet')}</div>
        </button>`;
      }).join('')
      : '<div class="media-empty">No projects yet. Create one to start the editor.</div>';
  }

  const structureDock = document.getElementById('media-center-structure-dock');
  if (structureDock) {
    structureDock.innerHTML = project ? _mediaCenterStructureDock(project) : '<div class="media-empty">Pick a project to see its composition outline.</div>';
  }

  const editor = document.getElementById('media-center-editor-stage');
  if (editor) {
    editor.innerHTML = project ? _mediaCenterEditorStage(project) : '<div class="media-empty">Create or select a project to open the composer.</div>';
  }

  const research = document.getElementById('media-center-research-body');
  if (research) {
    research.innerHTML = project ? _mediaCenterResearchDock(state, project) : '<div class="media-empty">Research Center loads once a project is selected.</div>';
  }

  const bottom = document.getElementById('media-center-bottom-body');
  if (bottom) {
    bottom.innerHTML = project ? _mediaCenterBottomDock(state, project) : '<div class="media-empty">Review Dock loads once a project is selected.</div>';
  }

  _mediaCenterApplyPanelState();
  _mediaCenterApplyFocusMode();
  _mediaCenterApplyDockTabState();
}

function _mediaCenterApplyPanelState() {
  document.querySelectorAll('#media-center-view [data-panel-key]').forEach((panel) => {
    const key = String(panel.dataset.panelKey || '').trim();
    if (!key) return;
    const collapsed = _mediaCenterPanelCollapsed(key);
    panel.classList.toggle('is-collapsed', collapsed);
    const toggle = panel.querySelector('.media-panel-toggle');
    if (toggle) toggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
  });
}

function _mediaCenterApplyFocusMode() {
  const root = document.getElementById('media-center-view');
  if (!root) return;
  root.classList.toggle('is-focus-mode', _mediaCenterFocusModeEnabled());
}

function _mediaCenterApplyDockTabState() {
  const researchTab = _mediaCenterGetTab('research', 'references');
  const bottomTab = _mediaCenterGetTab('bottom', 'queue');
  document.querySelectorAll('#media-center-research-tabs .media-dock-tab').forEach((button) => {
    button.classList.toggle('is-active', button.textContent?.trim().toLowerCase() === researchTab);
  });
  document.querySelectorAll('#media-center-bottom-tabs .media-dock-tab').forEach((button) => {
    button.classList.toggle('is-active', button.textContent?.trim().toLowerCase() === bottomTab);
  });
}

function mediaCenterTogglePanel(key) {
  if (!key) return;
  _mediaCenterSetPanelCollapsed(key, !_mediaCenterPanelCollapsed(key));
  _mediaCenterApplyPanelState();
}

function mediaCenterExpandAll() {
  Object.keys(_mediaCenterPanelDefaults).forEach((key) => _mediaCenterSetPanelCollapsed(key, false));
  _mediaCenterSetFocusMode(false);
  _mediaCenterApplyPanelState();
  _mediaCenterApplyFocusMode();
}

function mediaCenterCollapseToFocus() {
  _mediaCenterSetPanelCollapsed('new-project', true);
  _mediaCenterSetPanelCollapsed('project-rack', false);
  _mediaCenterSetPanelCollapsed('composer-outline', false);
  _mediaCenterSetPanelCollapsed('research-center', false);
  _mediaCenterSetPanelCollapsed('bottom-dock', false);
  _mediaCenterSetFocusMode(true);
  _mediaCenterApplyPanelState();
  _mediaCenterApplyFocusMode();
}

function mediaCenterSetResearchTab(tab) {
  _mediaCenterSetTab('research', tab);
  _renderMediaCenter();
}

function mediaCenterOpenResearch(tab) {
  _mediaCenterSetPanelCollapsed('research-center', false);
  if (tab) _mediaCenterSetTab('research', tab);
  _renderMediaCenter();
}

function mediaCenterSetBottomTab(tab) {
  _mediaCenterSetTab('bottom', tab);
  _renderMediaCenter();
}

function _mediaCenterStructureDock(project) {
  const scenes = (project.scenes || []).map((scene) => `
    <div class="media-mini-row"><strong>${_mcEsc(scene.name)}</strong><span>${_mcEsc(scene.duration_sec)}s</span><span>${_mcEsc(scene.goal)}</span></div>
  `).join('') || '<div class="media-empty">No scenes yet.</div>';
  const tracks = (project.tracks || []).map((track) => `
    <div class="media-mini-row"><strong>${_mcEsc(track.name)}</strong><span>${_mcEsc(track.role)}</span><span>${_mcEsc(track.model_hint)}</span></div>
  `).join('') || '<div class="media-empty">No tracks yet.</div>';
  const deliverables = (project.deliverables || []).map((item) => `
    <div class="media-mini-row"><strong>${_mcEsc(item.type)}</strong><span>${_mcEsc(item.format)}</span><span>${_mcEsc(item.target)}</span></div>
  `).join('') || '<div class="media-empty">No deliverables yet.</div>';
  return `
    <div class="media-outline-card">
      <div class="media-outline-title">Scene / Section Map</div>
      ${scenes}
    </div>
    <div class="media-outline-card">
      <div class="media-outline-title">Track Roles</div>
      ${tracks}
    </div>
    <div class="media-outline-card">
      <div class="media-outline-title">Deliverables</div>
      ${deliverables}
    </div>
  `;
}

function _mediaCenterEditorStage(project) {
  const lanes = project.timeline?.lanes || [];
  const clips = project.timeline?.clips || [];
  const synths = _mediaCenterState?.synths?.registry || [];
  const laneOptions = lanes.map((lane) => `<option value="${_mcEsc(lane.id)}">${_mcEsc(lane.name)} · ${_mcEsc(lane.kind)}</option>`).join('');
  const synthOptions = synths.map((synth) => `<option value="${_mcEsc(synth.id)}">${_mcEsc(synth.name)} · ${_mcEsc(synth.status)}</option>`).join('');
  const rulerMarks = Array.from({ length: Math.max(4, Math.min(16, Math.ceil((project.duration_sec || 30) / 4))) }).map((_, index) => {
    const sec = Math.round(((project.duration_sec || 30) / Math.max(1, Math.max(4, Math.min(16, Math.ceil((project.duration_sec || 30) / 4))))) * index);
    return `<span>${sec}s</span>`;
  }).join('');
  const timelineLanes = lanes.map((lane) => {
    const laneClips = clips.filter((clip) => clip.lane_id === lane.id);
    const clipBlocks = laneClips.map((clip) => {
      const width = Math.max(6, Math.min(100, ((Number(clip.duration_sec) || 1) / Math.max(1, Number(project.duration_sec) || 30)) * 100));
      const offset = Math.max(0, Math.min(94, ((Number(clip.start_sec) || 0) / Math.max(1, Number(project.duration_sec) || 30)) * 100));
      return `<button class="media-clip-block media-clip-kind-${_mcEsc(clip.kind || lane.kind || 'audio')}" type="button" style="left:${offset}%;width:${width}%;">
        <span class="media-clip-title">${_mcEsc(clip.name)}</span>
        <span class="media-clip-meta">${_mcEsc(clip.status || 'planned')}</span>
      </button>`;
    }).join('');
    return `
      <div class="media-lane-row">
        <div class="media-lane-label">
          <strong>${_mcEsc(lane.name)}</strong>
          <span>${_mcEsc(lane.kind)} · ${_mcEsc(lane.role || 'lane')}</span>
        </div>
        <div class="media-lane-track">
          ${clipBlocks || '<div class="media-lane-empty">No clips yet on this lane.</div>'}
        </div>
      </div>
    `;
  }).join('');
  return `
    <div class="media-editor-header">
      <div>
        <div class="media-detail-title">${_mcEsc(project.name)}</div>
        <div class="media-detail-meta">${_mcEsc(project.medium)} · ${_mcEsc(project.style || 'style not set')} · ${project.duration_sec || 0}s · ${_mcEsc(project.timeline?.tempo_bpm || 120)} bpm · ${_mcEsc(project.timeline?.time_signature || '4/4')}</div>
      </div>
      <div class="media-detail-actions">
        <button class="media-inline-btn" onclick="mediaCenterOpenStudioProject(${JSON.stringify(project.studio_project_id || '')})">Open in Studio</button>
        <button class="media-inline-btn" onclick="mediaCenterOpenResearch('knowledge')">Open Knowledge</button>
        <button class="media-inline-btn" onclick="mediaCenterOpenResearch('advisors')">Ask Advisors</button>
      </div>
    </div>
    <div class="media-detail-prompt">${_mcEsc(project.prompt || '')}</div>
    <div class="media-architecture-strip">
      <div class="media-architecture-step"><strong>Compose</strong><span>The editor is the main screen. Scenes, stems, synths, references, and video cuts all live here.</span></div>
      <div class="media-architecture-step"><strong>Research</strong><span>References, accounts, feeds, Knowledge docs, and advisor roles stay in the right dock.</span></div>
      <div class="media-architecture-step"><strong>Queue</strong><span>Audio, video, and compile jobs move through the bottom dock instead of competing with the editor.</span></div>
      <div class="media-architecture-step"><strong>Route</strong><span>Models and swarms decide ownership without taking over the composer.</span></div>
      <div class="media-architecture-step"><strong>Review</strong><span>Studio plan, tests, and handoff are attached to the same project.</span></div>
    </div>
    <section class="media-editor-card media-composer-surface">
      <div class="media-composer-head">
        <div>
          <div class="media-panel-title">Composer Timeline</div>
          <div class="media-panel-summary">DAW-first layout: scenes, stems, synth takes, references, and cuts stay visible as horizontal lanes.</div>
        </div>
      </div>
      <div class="media-ruler">${rulerMarks}</div>
      <div class="media-lane-stack">${timelineLanes || '<div class="media-empty">No lanes yet.</div>'}</div>
    </section>
    <div class="media-editor-tools">
      <section class="media-editor-card">
        <div class="media-panel-title">Add Clip</div>
        <div class="media-panel-summary">Stage a clip, stem, cue, caption, or reference marker directly into the timeline.</div>
        <div class="media-timeline-form">
          <select id="media-center-clip-lane">${laneOptions}</select>
          <input id="media-center-clip-name" placeholder="Clip / cue name">
          <input id="media-center-clip-start" type="number" min="0" step="0.25" value="0" title="Start seconds">
          <input id="media-center-clip-duration" type="number" min="0.25" step="0.25" value="4" title="Duration seconds">
          <input id="media-center-clip-prompt" placeholder="Prompt / source note">
          <button class="media-inline-btn media-inline-btn-primary" onclick="mediaCenterAddClip()">Add clip</button>
        </div>
      </section>
      <section class="media-editor-card">
        <div class="media-panel-title">Create Synth Take</div>
        <div class="media-panel-summary">Generate a music or video take and attach it to a lane/clip in the editor.</div>
        <div class="media-timeline-form">
          <select id="media-center-synth-id">${synthOptions}</select>
          <select id="media-center-synth-lane">${laneOptions}</select>
          <input id="media-center-synth-start" type="number" min="0" step="0.25" value="0" title="Start seconds">
          <input id="media-center-synth-duration" type="number" min="0.25" step="0.25" value="4" title="Duration seconds">
          <input id="media-center-synth-prompt" placeholder="Synth prompt">
          <button class="media-inline-btn media-inline-btn-primary" onclick="mediaCenterCreateSynthTake()">Create take</button>
        </div>
      </section>
      <section class="media-editor-card">
        <div class="media-panel-title">Mark Scene</div>
        <div class="media-panel-summary">Drop a scene / section marker without leaving the main workspace.</div>
        <div class="media-timeline-form">
          <input id="media-center-scene-name" placeholder="Scene / section name">
          <input id="media-center-scene-start" type="number" min="0" step="0.25" value="0" title="Start seconds">
          <input id="media-center-scene-duration" type="number" min="0.25" step="0.25" value="8" title="Duration seconds">
          <input id="media-center-scene-goal" placeholder="Goal / transition note">
          <button class="media-inline-btn media-inline-btn-primary" onclick="mediaCenterMarkScene()">Mark scene</button>
        </div>
      </section>
    </div>
  `;
}

function _mediaCenterResearchDock(state, project) {
  const tab = _mediaCenterGetTab('research', 'references');
  const accounts = state.accounts?.registry || [];
  const accountOptions = accounts.map((account) => `<option value="${_mcEsc(account.id)}">${_mcEsc(account.name)} · ${_mcEsc(account.status)}</option>`).join('');
  const activeProjectReferences = (project.media_refs || []).slice(0, 12).map((ref) => `
    <div class="media-mini-row"><strong>${_mcEsc(ref.title)}</strong><span>${_mcEsc(ref.account_name || ref.account_id)}</span><span>${_mcEsc(ref.knowledge_status || ref.status)}</span></div>
  `).join('');
  const accountRows = accounts.map((account) => `
    <div class="media-mini-row"><strong>${_mcEsc(account.name)}</strong><span>${_mcEsc(account.kind)}</span><span>${_mcEsc(account.status)}</span><button class="media-inline-btn" onclick="mediaCenterLinkAccount(${JSON.stringify(account.id)})">Link</button></div>
  `).join('');
  const feedRows = (state.feeds?.subscriptions || []).map((feed) => `
    <div class="media-mini-row"><strong>${_mcEsc(feed.title || feed.kind)}</strong><span>${_mcEsc(feed.kind)}</span><span>${_mcEsc(feed.status || 'pending')}</span></div>
  `).join('');
  const knowledgeDocs = (state.knowledge?.project_docs || []).map((doc) => `
    <div class="media-mini-row"><strong>${_mcEsc(doc.doc_name)}</strong><span>${_mcEsc(doc.tags || '')}</span><span>${_mcEsc(doc.source || 'knowledge')}</span></div>
  `).join('');
  const knowledgeRefs = (state.knowledge?.references || []).slice(0, 8).map((ref) => `
    <div class="media-mini-row"><strong>${_mcEsc(ref.title)}</strong><span>${_mcEsc(ref.project_name || ref.project_id)}</span><span>${_mcEsc(ref.account_name || ref.account_id)}</span></div>
  `).join('');
  const agents = state.models?.agents || [];
  const swarms = state.linked_swarms?.nodes || [];
  const agentOptions = '<option value="">auto</option>' + agents.map((agent) => `<option value="${_mcEsc(agent.agent)}">${_mcEsc(agent.label || agent.agent)} · ${_mcEsc(agent.model || 'model')}</option>`).join('');
  const swarmOptions = '<option value="">local</option>' + swarms.map((node) => `<option value="${_mcEsc(node.node_id)}">${_mcEsc(node.name || node.node_id)} · ${node.media_relevant ? 'media-ready' : _mcEsc(node.role || 'node')}</option>`).join('');
  const advisors = (state.advisors?.roles || []).map((advisor) => `
    <div class="media-advisor-card">
      <div class="media-advisor-head"><strong>${_mcEsc(advisor.agent_id)}</strong><span>${_mcEsc(advisor.title)}</span></div>
      <div class="media-project-prompt">${_mcEsc(advisor.focus)}</div>
      <div class="media-runtime-grid-mini">
        <span class="media-runtime-chip is-on">${_mcEsc(advisor.role)}</span>
        <span class="media-runtime-chip">${_mcEsc(advisor.availability || 'unknown')}</span>
        <span class="media-runtime-chip">${_mcEsc(advisor.surfaces || 'Media Center')}</span>
      </div>
      <div class="media-panel-summary">${_mcEsc(advisor.how_to_use)}</div>
    </div>
  `).join('');
  if (tab === 'references') {
    return `
      <div class="media-dock-section">
        <div class="media-panel-title">Project References</div>
        <div class="media-panel-summary">Attach source tracks, clips, notes, and URLs. The right dock keeps research close without taking over the editor.</div>
        ${activeProjectReferences || '<div class="media-empty">No references attached yet.</div>'}
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
          <button class="media-inline-btn media-inline-btn-primary" onclick="mediaCenterAddReference()">Attach reference</button>
        </div>
      </div>
    `;
  }
  if (tab === 'accounts') {
    return `<div class="media-dock-section"><div class="media-panel-title">Linked Accounts</div><div class="media-panel-summary">Accounts can become feed inputs and provenance anchors.</div>${accountRows || '<div class="media-empty">No accounts available.</div>'}</div>`;
  }
  if (tab === 'feeds') {
    const suggestions = (state.feeds?.suggestions || []).map((item) => `
      <div class="media-mini-row"><strong>${_mcEsc(item.title)}</strong><span>${_mcEsc(item.kind)}</span><span>${_mcEsc(item.reason)}</span></div>
    `).join('');
    return `
      <div class="media-dock-section">
        <div class="media-panel-title">Connected Feeds</div>
        <div class="media-panel-summary">Research feeds and taste signals stay docked, not center-stage.</div>
        ${feedRows || '<div class="media-empty">No connected feeds yet.</div>'}
        <div class="media-outline-card">
          <div class="media-outline-title">Feed Suggestions</div>
          ${suggestions || '<div class="media-empty">No feed suggestions yet.</div>'}
        </div>
      </div>
    `;
  }
  if (tab === 'knowledge') {
    return `
      <div class="media-dock-section">
        <div class="media-panel-title">Knowledge Docs</div>
        <div class="media-panel-summary">Fridays composition and video guidance is seeded into Knowledge Center and surfaced here.</div>
        ${knowledgeDocs || '<div class="media-empty">No Fridays docs discovered yet.</div>'}
        <div class="media-outline-card">
          <div class="media-outline-title">Indexed References</div>
          ${knowledgeRefs || '<div class="media-empty">No indexed references yet.</div>'}
        </div>
      </div>
    `;
  }
  if (tab === 'routing') {
    return `
      <div class="media-dock-section">
        <div class="media-panel-title">Model / Swarm Routing</div>
        <div class="media-panel-summary">Set ownership without forcing routing tools into the main composer.</div>
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
      </div>
    `;
  }
  return `
    <div class="media-dock-section">
      <div class="media-panel-title">Assistive Advisors</div>
      <div class="media-panel-summary">Agents 10, 17, and 19 help with composition, production workflow, and critique without becoming permanent editor lanes.</div>
      <div class="media-advisor-grid">${advisors || '<div class="media-empty">No advisor roles advertised yet.</div>'}</div>
    </div>
  `;
}

function _mediaCenterBottomDock(state, project) {
  const tab = _mediaCenterGetTab('bottom', 'queue');
  if (tab === 'queue') {
    const rows = (state.jobs || []).filter((job) => job.project_id === project.id).map((job) => {
      const action = job.status === 'queued' || job.status === 'ready'
        ? `<button class="media-inline-btn media-inline-btn-primary" onclick="mediaCenterRunJob(${JSON.stringify(job.id)})">Run local</button>
           <button class="media-inline-btn" onclick="mediaCenterSimulateJob(${JSON.stringify(job.id)})">Simulate</button>`
        : '<span class="media-inline-hint">artifact ready</span>';
      const artifacts = (job.artifacts || []).map((artifact) => _mediaCenterArtifactView(artifact)).join('');
      return `<div class="media-job-row">
        <div class="media-job-main">
          <div class="media-job-title">${_mcEsc(job.project_name || job.project_id)} <span class="media-job-type">${_mcEsc(job.job_type)}</span></div>
          <div class="media-job-meta">${_mcEsc(job.status)} · ${_mcEsc(job.engine)} · ${_mcEsc(job.mode)}</div>
          <div class="media-job-notes">${_mcEsc(job.notes || '')}</div>
          ${artifacts ? `<div class="media-artifact-list">${artifacts}</div>` : ''}
        </div>
        <div class="media-job-actions">${action}</div>
      </div>`;
    }).join('');
    return rows || '<div class="media-empty">No queued jobs yet for this project.</div>';
  }
  if (tab === 'runtime') {
    const runtimeCards = _mediaCenterRuntimeCards(state.runtime || {});
    const presets = (state.presets || []).map((preset) => `
      <div class="media-preset-card">
        <div class="media-preset-title">${_mcEsc(preset.name)}</div>
        <div class="media-preset-summary">${_mcEsc(preset.summary)}</div>
        <div class="media-preset-meta">${_mcEsc((preset.music_models || []).join(', ') || 'No music model')} | ${_mcEsc((preset.video_models || []).join(', ') || 'No video model')}</div>
      </div>
    `).join('');
    const synthRows = (state.synths?.registry || []).slice(0, 6).map((synth) => `
      <div class="media-mini-row"><strong>${_mcEsc(synth.name)}</strong><span>${_mcEsc(synth.kind)}</span><span>${_mcEsc(synth.status)}</span></div>
    `).join('');
    const spine = (state.spine?.items || []).slice(0, 6).map((item) => `
      <div class="media-mini-row"><strong>${_mcEsc(item.kind || 'event')}</strong><span>${_mcEsc(item.severity || 'info')}</span><span>${_mcEsc(item.message || '')}</span></div>
    `).join('');
    return `
      <div class="media-bottom-grid">
        <div class="media-outline-card">
          <div class="media-outline-title">Runtime Scan</div>
          <div class="media-runtime-grid">${runtimeCards}</div>
        </div>
        <div class="media-outline-card">
          <div class="media-outline-title">Pipeline Presets</div>
          <div class="media-preset-list">${presets}</div>
        </div>
        <div class="media-outline-card">
          <div class="media-outline-title">Synth Registry</div>
          ${synthRows || '<div class="media-empty">No synth registry loaded yet.</div>'}
        </div>
        <div class="media-outline-card">
          <div class="media-outline-title">Spine Trail</div>
          ${spine || '<div class="media-empty">No media spine events yet.</div>'}
        </div>
      </div>
    `;
  }
  const trackingProjectId = state.studio?.tracking_project_id || '';
  const trackingProgress = state.tracking?.progress || {};
  const trackingSteps = (state.tracking?.steps || []).slice(0, 10).map((step) => `
    <div class="media-mini-row"><strong>${_mcEsc(step.title)}</strong><span>${_mcEsc(step.owner || 'seven')}</span><span>${_mcEsc(step.status || 'todo')}</span></div>
  `).join('');
  const trackingRuns = (state.tracking?.recent_runs || []).slice(0, 6).map((run) => `
    <div class="media-mini-row"><strong>${_mcEsc(run.status || 'run')}</strong><span>${_mcEsc(run.script_id || '')}</span><span>${_mcEsc(run.duration_ms != null ? run.duration_ms + 'ms' : run.run_id)}</span></div>
  `).join('');
  const modelRows = (state.models?.agents || []).slice(0, 6).map((agent) => `
    <div class="media-mini-row"><strong>${_mcEsc(agent.label || agent.agent)}</strong><span>${_mcEsc(agent.agent)}</span><span>${_mcEsc(agent.model || 'model pending')}</span></div>
  `).join('');
  const swarmRows = (state.linked_swarms?.nodes || []).slice(0, 6).map((node) => `
    <div class="media-mini-row"><strong>${_mcEsc(node.name || node.node_id)}</strong><span>${_mcEsc(node.role || 'node')}</span><span>${node.media_relevant ? 'media-ready' : _mcEsc((node.capabilities || []).join(', ') || 'registered')}</span></div>
  `).join('');
  const chatActions = (state.chat?.actions || []).map((action) => `
    <span class="media-runtime-chip is-on">${_mcEsc(action.phrase)}</span>
  `).join('');
  return `
    <div class="media-bottom-grid">
      <div class="media-outline-card">
        <div class="media-outline-title">Studio Review Plan</div>
        <div class="media-runtime-grid-mini">
          <span class="media-runtime-chip is-on">${trackingProgress.done_steps || 0}/${trackingProgress.step_count || 0} steps done</span>
          <span class="media-runtime-chip">${trackingProgress.case_count || 0} cases</span>
          <span class="media-runtime-chip">${trackingProgress.recent_passes || 0} recent passes</span>
          <span class="media-runtime-chip">${trackingProgress.recent_failures || 0} recent failures</span>
        </div>
        <div class="media-mini-row"><strong>${_mcEsc(state.studio?.tracking_project_name || 'Media Center + Studio Integration')}</strong><span>${_mcEsc(trackingProjectId)}</span><button class="media-inline-btn" onclick="mediaCenterOpenStudioProject(${JSON.stringify(trackingProjectId)})">Open</button></div>
        ${trackingSteps || '<div class="media-empty">No tracking steps yet.</div>'}
        <div class="media-outline-title media-outline-title-gap">Recent verification</div>
        ${trackingRuns || '<div class="media-empty">No verification runs recorded yet.</div>'}
      </div>
      <div class="media-outline-card">
        <div class="media-outline-title">Handoff Manifest</div>
        <div class="media-mini-row"><strong>${_mcEsc(project.name || 'No project')}</strong><span>${_mcEsc(project.medium || '')}</span><span>${_mcEsc(project.routing?.handoff_mode || 'local-first')}</span></div>
        <button class="media-inline-btn media-inline-btn-primary" onclick="mediaCenterCopyHandoff()">Copy manifest</button>
        <div class="media-outline-title media-outline-title-gap">Chat Actions</div>
        <div class="media-runtime-grid-mini">${chatActions || '<span class="media-runtime-chip">No actions</span>'}</div>
      </div>
      <div class="media-outline-card">
        <div class="media-outline-title">Model Candidates</div>
        ${modelRows || '<div class="media-empty">No media-relevant model candidates found yet.</div>'}
      </div>
      <div class="media-outline-card">
        <div class="media-outline-title">Linked Swarms</div>
        ${swarmRows || '<div class="media-empty">No linked swarms registered yet.</div>'}
      </div>
    </div>
  `;
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
        ${keys.map((key) => {
          const on = !!block?.[key];
          return `<span class="media-runtime-chip ${on ? 'is-on' : ''}">${_mcEsc(key.replace(/_/g, ' '))}: ${on ? 'on' : 'off'}</span>`;
        }).join('')}
      </div>
    </div>
  `).join('');
}

function _mediaCenterArtifactView(artifact) {
  const label = _mcEsc(artifact.label || artifact.path || 'Artifact');
  const url = artifact.url || '';
  const mime = artifact.mime_type || '';
  if (url && mime.startsWith('audio/')) {
    return `<div class="media-artifact-row">
      <span>${label}</span>
      <audio controls preload="none" src="${_mcEsc(url)}"></audio>
    </div>`;
  }
  if (url && mime.startsWith('video/')) {
    return `<div class="media-artifact-row">
      <span>${label}</span>
      <video controls preload="metadata" src="${_mcEsc(url)}"></video>
    </div>`;
  }
  if (url) {
    return `<div class="media-artifact-row"><span>${label}</span><a href="${_mcEsc(url)}" target="_blank" rel="noreferrer">Open</a></div>`;
  }
  return `<div class="media-artifact-row"><span>${label}</span><span>${_mcEsc(artifact.status || 'planned')}</span></div>`;
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
    body: JSON.stringify({ job_type: jobType, mode: 'real-local', notes: 'Queued from Media Center shell.' }),
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

async function mediaCenterMarkScene() {
  if (!_mediaCenterSelectedProjectId) {
    if (typeof showToast === 'function') showToast('Choose a project first.', 'info');
    return;
  }
  const project = (_mediaCenterState?.projects || []).find((item) => item.id === _mediaCenterSelectedProjectId);
  const name = document.getElementById('media-center-scene-name')?.value?.trim();
  if (!name) {
    document.getElementById('media-center-scene-name')?.focus();
    return;
  }
  const laneId = _mediaCenterFindLane(project, ['scene', 'section'], 'marker')?.id || project?.timeline?.lanes?.[0]?.id || '';
  const startSec = parseFloat(document.getElementById('media-center-scene-start')?.value || '0');
  const durationSec = parseFloat(document.getElementById('media-center-scene-duration')?.value || '8');
  const prompt = document.getElementById('media-center-scene-goal')?.value?.trim() || '';
  const response = await fetch(`/api/media-center/projects/${encodeURIComponent(_mediaCenterSelectedProjectId)}/clips`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name,
      lane_id: laneId,
      start_sec: startSec,
      duration_sec: durationSec,
      prompt,
      kind: 'marker',
      source: 'scene-marker',
      status: 'planned',
    }),
  });
  const data = await response.json();
  if (!data.ok) {
    if (typeof showToast === 'function') showToast(data.error || 'Scene marker failed.', 'error');
    return;
  }
  if (typeof showToast === 'function') showToast('Scene marker added to the composer.', 'success');
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
    if (window.__SWARM_DEBUG) console.debug('Media handoff manifest', data.manifest);
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

async function mediaCenterRunJob(jobId) {
  const response = await fetch(`/api/media-center/jobs/${encodeURIComponent(jobId)}/run`, { method: 'POST' });
  const data = await response.json();
  if (!data.ok) {
    if (typeof showToast === 'function') showToast(data.error || 'Local run failed.', 'error');
    return;
  }
  if (typeof showToast === 'function') showToast('Real local artifact rendered.', 'success');
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

function mediaCenterOpenReviewPlan() {
  const trackingProjectId = _mediaCenterState?.studio?.tracking_project_id || '';
  if (!trackingProjectId) {
    if (typeof showToast === 'function') showToast('Review plan not ready yet. Try Refresh once Media Center state loads.', 'info');
    return;
  }
  mediaCenterOpenStudioProject(trackingProjectId);
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

window.mediaCenterTogglePanel = mediaCenterTogglePanel;
window.mediaCenterExpandAll = mediaCenterExpandAll;
window.mediaCenterCollapseToFocus = mediaCenterCollapseToFocus;
window.mediaCenterOpenReviewPlan = mediaCenterOpenReviewPlan;
window.mediaCenterSetResearchTab = mediaCenterSetResearchTab;
window.mediaCenterOpenResearch = mediaCenterOpenResearch;
window.mediaCenterSetBottomTab = mediaCenterSetBottomTab;
window.mediaCenterMarkScene = mediaCenterMarkScene;

function _mediaCenterFindLane(project, roleHints, kindHint) {
  const lanes = project?.timeline?.lanes || [];
  return lanes.find((lane) => roleHints.includes(String(lane.role || '').toLowerCase()))
    || lanes.find((lane) => String(lane.kind || '').toLowerCase() === String(kindHint || '').toLowerCase())
    || lanes[0]
    || null;
}

function _mcEsc(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
