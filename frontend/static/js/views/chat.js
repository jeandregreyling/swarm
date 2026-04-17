// Chat engine — bubbles, relay, dispatch, compose, threads
// Extracted from terminal_base.html

// ═══════════════════════════════════════════════════════════════════════════
// MESSAGE FUNCTIONS
// ═══════════════════════════════════════════════════════════════════════════

// Agent options — internal `value` keys never change.
// `label` and `number` are data not code — fetched from DB on load via _loadAgentRegistry().
// Fallback labels below are already correct; the fetch keeps them in sync if DB changes.
// To rename an agent or swap its model: UPDATE agents SET label=... WHERE name=... in the DB.
let CHAT_AGENT_OPTIONS = [
  { value: 'gemma',    label: '1 · Gemma3',   number: 1,  tier: 'local', hasTemp: true  },
  { value: 'llama',    label: '2 · LlaMA',    number: 2,  tier: 'local', hasTemp: true  },
  { value: 'mistral',  label: '3 · Mistral',  number: 3,  tier: 'local', hasTemp: true  },
  { value: 'qwen',     label: '4 · Qwen',     number: 4,  tier: 'local', hasTemp: true  },
  { value: 'librarian',label: '5 · Vortex',   number: 5,  tier: 'local', hasTemp: false },
  { value: 'duck',     label: '6 · Duck',     number: 6,  tier: 'local', hasTemp: true  },
  { value: 'sniffles', label: '7 · Sniffles', number: 7,  tier: 'local', hasTemp: true  },
  { value: 'eight',    label: '8 · Eight',    number: 8,  tier: 'local', hasTemp: true  },
  { value: 'nine',     label: '9 · Groq',     number: 9,  tier: 'paid',  hasTemp: false },
  { value: 'ten',      label: '10 · Github',  number: 10, tier: 'paid',  hasTemp: true  },
  { value: 'eleven',   label: '11 · Grok',    number: 11, tier: 'paid',  hasTemp: false },
  { value: 'twelve',   label: '12 · Claude',  number: 12, tier: 'paid',  hasTemp: false },
  { value: 'thirteen', label: '13 · HF', number: 13, tier: 'free', hasTemp: false },
];

// Fetch agent registry from DB and update CHAT_AGENT_OPTIONS to only include enabled agents.
function _loadAgentRegistry() {
  fetch('/api/agents/config')
    .then(r => r.ok ? r.json() : null)
    .catch(() => null)
    .then(data => {
      if (!Array.isArray(data)) return;
      // Only include agents with enabled: true
      const enabledAgents = data.filter(a => a.enabled);
      const byValue = {};
      enabledAgents.forEach(a => { if (a.name) byValue[a.name.toLowerCase()] = a; });
      // Filter and update CHAT_AGENT_OPTIONS
      CHAT_AGENT_OPTIONS = CHAT_AGENT_OPTIONS.filter(opt => byValue[opt.value.toLowerCase()]);
      let changed = false;
      CHAT_AGENT_OPTIONS.forEach(opt => {
        const reg = byValue[opt.value.toLowerCase()];
        if (!reg) return;
        const num = reg.number != null ? reg.number : opt.number;
        const lbl = reg.label || opt.label;
        const newLabel = num != null ? `${num} · ${lbl}` : lbl;
        if (opt.label !== newLabel) { opt.label = newLabel; changed = true; }
        if (num != null) opt.number = num;
      });
      if (changed) {
        if (typeof renderChatAgentToggles === 'function') renderChatAgentToggles();
      }
    });
}

const CHAT_CUSTOM_DICTIONARY_KEY = 'fridays-chat-custom-dictionary-v1';
const CHAT_DESKTOP_NOTIFY_KEY = 'fridays-chat-desktop-notify-v1';
const CHAT_THREAD_AGENT_KEY = 'fridays-chat-thread-agents-v1';
const CHAT_HISTORY_MODE_KEY = 'fridays-chat-history-mode-v1';
const CHAT_HISTORY_LIMIT_KEY = 'fridays-chat-history-limit-v1';
const CHAT_THREAD_WIDTH_KEY = 'fridays-chat-thread-width-v1';
const CHAT_THREAD_COLLAPSED_KEY = 'fridays-chat-thread-collapsed-v1';
const CHAT_DOCK_WIDTH_KEY = 'fridays-chat-dock-width-v1';
const CHAT_DOCK_COLLAPSED_KEY = 'fridays-chat-dock-collapsed-v1';
const CHAT_UI_SCALE_KEY = 'fridays-chat-ui-scale-v1';
const CHAT_UI_SCALE_DEFAULT = 0.95;
const CHAT_UI_SCALE_OPTIONS = [0.80, 0.85, 0.90, 0.95, 1.00, 1.05, 1.10, 1.15, 1.20, 1.30];
const CHAT_RUNTIME_PANEL_HIDDEN_KEY = 'fridays-chat-runtime-hidden-v1';
const CHAT_RUNTIME_PIN_KEY = 'fridays-chat-runtime-pin-v1';
const CHAT_ACTOR_BUBBLE_COLORS_KEY = 'fridays-chat-actor-bubble-colors-v1';
const CHAT_RELAY_AUTO_KEY = 'fridays-chat-relay-auto-v1';
const CHAT_RELAY_MAX_KEY = 'fridays-chat-relay-max-v1';
const CHAT_RELAY_FORCE_FULL_KEY = 'fridays-chat-relay-force-full-v1';
const CHAT_RELAY_RULES_KEY = 'fridays-chat-relay-rules-v1';
const CHAT_FLOW_MODE_KEY = 'fridays-chat-flow-mode-v1';
const CHAT_LEGACY_PARALLEL_MODE_KEY = 'fridays-chat-parallel-mode-v1';
const CHAT_EXEC_MODE_KEY = 'fridays-chat-exec-mode-v1';   // 'sequential' | 'parallel'
const CHAT_ATTACH_MAX_FILES = 6;
const CHAT_ATTACH_MAX_SIZE_BYTES = 10 * 1024 * 1024;
const CHAT_ATTACH_MAX_TEXT_CHARS_PER_FILE = 8000;
const CHAT_ATTACH_MAX_TOTAL_INLINE_CHARS = 24000;
const CHAT_TYPO_SUGGESTIONS = {
  teh: 'the',
  recieve: 'receive',
  reciever: 'receiver',
  seperat: 'separate',
  definately: 'definitely',
  occured: 'occurred',
  untill: 'until',
  adress: 'address',
  enviroment: 'environment',
  becuase: 'because',
  wierd: 'weird',
  langauge: 'language',
  udpate: 'update',
  reponse: 'response',
  reponses: 'responses',
  promt: 'prompt',
  promts: 'prompts',
};

function _loadInitialChatFlowMode() {
  const stored = String(localStorage.getItem(CHAT_FLOW_MODE_KEY) || '').trim().toLowerCase();
  if (stored === 'both_seq' || stored === 'local_only' || stored === 'online_only') {
    return stored;
  }
  const legacyParallel = localStorage.getItem(CHAT_LEGACY_PARALLEL_MODE_KEY) === '1';
  return legacyParallel ? 'online_only' : 'both_seq';
}

window.__fridaysChatConversationId = window.__fridaysChatConversationId || null;
window.__fridaysChatEnabledAgents = window.__fridaysChatEnabledAgents || { gemma: true };
window.__fridaysReplyTargets = Array.isArray(window.__fridaysReplyTargets) ? window.__fridaysReplyTargets : [];
window.__fridaysChatForceNewThread = window.__fridaysChatForceNewThread || false;
window.__fridaysChatPendingJobIds = window.__fridaysChatPendingJobIds || [];
window.__fridaysChatPendingConversationId = window.__fridaysChatPendingConversationId || null;
window.__fridaysChatPendingPollTimer = window.__fridaysChatPendingPollTimer || null;
window.__fridaysChatCustomDictionary = window.__fridaysChatCustomDictionary || new Set();
window.__fridaysChatAttachments = window.__fridaysChatAttachments || [];
window.__fridaysBubbleAttachmentStore = window.__fridaysBubbleAttachmentStore || {};
window.__fridaysChatHistoryMode = window.__fridaysChatHistoryMode || localStorage.getItem(CHAT_HISTORY_MODE_KEY) || 'full';
window.__fridaysChatHistoryLimit = Number(window.__fridaysChatHistoryLimit || localStorage.getItem(CHAT_HISTORY_LIMIT_KEY) || 8);
window.__fridaysChatThreadWidth = Number(window.__fridaysChatThreadWidth || localStorage.getItem(CHAT_THREAD_WIDTH_KEY) || 280);
window.__fridaysChatThreadCollapsed = window.__fridaysChatThreadCollapsed ?? (localStorage.getItem(CHAT_THREAD_COLLAPSED_KEY) === '1');
window.__fridaysChatDockWidth = Number(window.__fridaysChatDockWidth || localStorage.getItem(CHAT_DOCK_WIDTH_KEY) || 420);
window.__fridaysChatDockCollapsed = window.__fridaysChatDockCollapsed ?? (localStorage.getItem(CHAT_DOCK_COLLAPSED_KEY) === '1');
window.__fridaysChatUiScale = Number(window.__fridaysChatUiScale || localStorage.getItem(CHAT_UI_SCALE_KEY) || CHAT_UI_SCALE_DEFAULT);
window.__fridaysChatRuntimeHidden = false;
window.__fridaysChatRuntimePinned = true;
window.__fridaysChatRelayAuto = window.__fridaysChatRelayAuto ?? (localStorage.getItem(CHAT_RELAY_AUTO_KEY) !== '0');
window.__fridaysChatFlowMode = window.__fridaysChatFlowMode || _loadInitialChatFlowMode();
window.__fridaysChatExecMode = window.__fridaysChatExecMode || (localStorage.getItem(CHAT_EXEC_MODE_KEY) || 'sequential');
window.__fridaysChatRelayInfinite = window.__fridaysChatRelayInfinite ?? (localStorage.getItem(CHAT_RELAY_MAX_KEY) === 'inf');
window.__fridaysChatRelayMaxPerTurn = Number(window.__fridaysChatRelayMaxPerTurn || localStorage.getItem(CHAT_RELAY_MAX_KEY) || 2);
window.__fridaysChatRelayForceFull = window.__fridaysChatRelayForceFull ?? (localStorage.getItem(CHAT_RELAY_FORCE_FULL_KEY) !== '0');
window.__fridaysChatRelayBudget = Number(window.__fridaysChatRelayBudget || 0);
window.__fridaysChatRelayQueue = Array.isArray(window.__fridaysChatRelayQueue) ? window.__fridaysChatRelayQueue : [];
window.__fridaysChatRelayBusy = !!window.__fridaysChatRelayBusy;
window.__fridaysChatRelayProcessing = !!window.__fridaysChatRelayProcessing;
window.__fridaysChatRelayActive = !!window.__fridaysChatRelayActive;
window.__fridaysChatRelayRetryTimer = window.__fridaysChatRelayRetryTimer || null;
window.__fridaysChatRelayHoldReason = String(window.__fridaysChatRelayHoldReason || '');
window.__fridaysChatRelayHoldStamp = Number(window.__fridaysChatRelayHoldStamp || 0);
window.__fridaysChatRelayLastHoldKey = String(window.__fridaysChatRelayLastHoldKey || '');
window.__fridaysChatRelayResource = window.__fridaysChatRelayResource || { cpuPercent: null, ramPercent: null, sampledAt: 0, source: 'init' };
window.__fridaysChatRelayAllowedAgents = Array.isArray(window.__fridaysChatRelayAllowedAgents) ? window.__fridaysChatRelayAllowedAgents : [];
window.__fridaysChatRelaySeen = window.__fridaysChatRelaySeen || {};
window.__fridaysChatTimeline = Array.isArray(window.__fridaysChatTimeline) ? window.__fridaysChatTimeline : [];
window.__fridaysChatTimelineFilter = String(window.__fridaysChatTimelineFilter || 'all').toLowerCase();
window.__fridaysChatRelayRules = Array.isArray(window.__fridaysChatRelayRules) ? window.__fridaysChatRelayRules : (() => {
  try {
    const raw = JSON.parse(localStorage.getItem(CHAT_RELAY_RULES_KEY) || '[]');
    return Array.isArray(raw) ? raw : [];
  } catch (_) {
    return [];
  }
})();
window.__fridaysActorBubbleColors = window.__fridaysActorBubbleColors || (() => {
  try {
    const raw = JSON.parse(localStorage.getItem(CHAT_ACTOR_BUBBLE_COLORS_KEY) || '{}');
    return raw && typeof raw === 'object' ? raw : {};
  } catch (_) {
    return {};
  }
})();
window.__fridaysDesktopNotificationsEnabled = window.__fridaysDesktopNotificationsEnabled ?? (localStorage.getItem(CHAT_DESKTOP_NOTIFY_KEY) === '1');
window.__fridaysThreadAgentSelections = window.__fridaysThreadAgentSelections || _loadThreadAgentSelections();
window.__fridaysThreadRuntimePollTimer = window.__fridaysThreadRuntimePollTimer || null;
window.__fridaysThreadRuntimeSnapshot = window.__fridaysThreadRuntimeSnapshot || { jobs: [], updatedAt: null };
window.__fridaysChatLiveSyncTimer = window.__fridaysChatLiveSyncTimer || null;
window.__fridaysChatLiveSyncThreadRefreshTimer = window.__fridaysChatLiveSyncThreadRefreshTimer || null;
window.__fridaysChatLastRenderSig = String(window.__fridaysChatLastRenderSig || '');
window.__fridaysLastMentionedAgents = Array.isArray(window.__fridaysLastMentionedAgents) ? window.__fridaysLastMentionedAgents : [];
window.__fridaysMentionState = window.__fridaysMentionState || { open: false, start: -1, end: -1, active: 0, items: [] };

function _threadSelectionKey(convId) {
  return convId ? String(convId) : 'new';
}

function _loadThreadAgentSelections() {
  try {
    const raw = JSON.parse(localStorage.getItem(CHAT_THREAD_AGENT_KEY) || '{}');
    return raw && typeof raw === 'object' ? raw : {};
  } catch (_) {
    return {};
  }
}

function _saveThreadAgentSelections() {
  localStorage.setItem(CHAT_THREAD_AGENT_KEY, JSON.stringify(window.__fridaysThreadAgentSelections || {}));
}

function persistThreadAgentSelection(convId = window.__fridaysChatConversationId) {
  const key = _threadSelectionKey(convId);
  const selected = {};
  CHAT_AGENT_OPTIONS.forEach(agent => {
    if (window.__fridaysChatEnabledAgents[agent.value]) selected[agent.value] = true;
  });
  window.__fridaysThreadAgentSelections[key] = selected;
  _saveThreadAgentSelections();
}

function applyThreadAgentSelection(convId = window.__fridaysChatConversationId) {
  const key = _threadSelectionKey(convId);
  const saved = (window.__fridaysThreadAgentSelections || {})[key];
  if (!saved || typeof saved !== 'object' || !Object.keys(saved).length) return;
  const next = {};
  CHAT_AGENT_OPTIONS.forEach(agent => {
    next[agent.value] = !!saved[agent.value];
  });
  if (!Object.values(next).some(Boolean)) next.gemma = true;
  window.__fridaysChatEnabledAgents = next;
}

function onChatAgentToggleChange(input) {
  if (!input) return;
  window.__fridaysChatEnabledAgents[input.value] = !!input.checked;
  // Update slider row for this agent when toggled
  const row = document.querySelector(`[data-temp-row="${input.value}"]`);
  if (row) {
    row.style.opacity = input.checked ? '1' : '0.3';
    row.style.pointerEvents = input.checked ? 'auto' : 'none';
  }
  persistThreadAgentSelection();
  updateComposerMeta();
}

function _setActiveThreadId(convId) {
  window.__fridaysChatConversationId = convId;
  if (convId) {
    window.__fridaysChatForceNewThread = false;
    localStorage.setItem('fridays-chat-active-thread', String(convId));
  } else {
    localStorage.removeItem('fridays-chat-active-thread');
  }
  updateChatStatusPills();
}

function updateChatStatusPills() {
  document.querySelectorAll('[id="chat-dictionary-inline"]').forEach(dictInline => {
    const size = Array.from(window.__fridaysChatCustomDictionary || []).length;
    dictInline.textContent = 'Dictionary: ' + size;
  });
}

function updateChatMiniSystemStats(cpuPercent, ramPercent) {
  const cpu = Number(cpuPercent);
  const ram = Number(ramPercent);
  const cpuText = Number.isFinite(cpu) ? `${Math.round(cpu)}%` : '--%';
  const ramText = Number.isFinite(ram) ? `${Math.round(ram)}%` : '--%';
  const cpuClass = Number.isFinite(cpu) && cpu >= 80 ? 'hot' : (Number.isFinite(cpu) && cpu >= 65 ? 'warn' : '');
  const ramClass = Number.isFinite(ram) && ram >= 85 ? 'hot' : (Number.isFinite(ram) && ram >= 70 ? 'warn' : '');
  document.querySelectorAll('.chat-mini-system').forEach(node => {
    node.innerHTML = `CPU <span class="${cpuClass}">${_escapeHtml(cpuText)}</span> · RAM <span class="${ramClass}">${_escapeHtml(ramText)}</span>`;
  });
}

function _chatRuntimeStateLabel(job) {
  const status = String((job && job.status) || 'running');
  const stage = String((job && job.stage) || '').trim();
  if (status === 'running') return stage || 'running';
  if (status === 'failed') return 'failed';
  if (status === 'cancelled') return 'cancelled';
  return 'completed';
}

function _chatRuntimeSortWeight(status) {
  const s = String(status || 'running');
  if (s === 'running') return 0;
  if (s === 'failed') return 1;
  if (s === 'cancelled') return 2;
  return 3;
}

function _updateThreadRuntimeLoading() {
  const snapshotJobs = Array.isArray(window.__fridaysThreadRuntimeSnapshot?.jobs) ? window.__fridaysThreadRuntimeSnapshot.jobs : [];
  _renderThreadRuntimePanel(snapshotJobs, 'live');
}

function _chatRuntimeStatusClass(job) {
  if (!job) return 'initializing';
  if (job.status === 'completed') return 'completed';
  if (job.status === 'failed' || job.status === 'cancelled') return 'failed';
  if (job.stage === 'thinking' || job.stage === 'processing') return 'compiling';
  return 'initializing';
}

function _renderThreadRuntimeChip(agent, state, statusClass, timeLabel) {
  return `
    <div class="chat-thread-runtime-row ${statusClass}" data-agent="${_escapeHtml(String(agent || '').toLowerCase())}">
      <span class="chat-thread-runtime-light ${statusClass}"></span>
      <div class="chat-thread-runtime-row-agent">${_chatAgentIdentityHtml(agent, false)}</div>
      <div class="chat-thread-runtime-stage">${_escapeHtml(state)}</div>
      <div class="chat-thread-runtime-row-time">${_escapeHtml(timeLabel || '')}</div>
    </div>
  `;
}

function _renderThreadRuntimePanel(jobs, sourceLabel = 'poll') {
  const hosts = Array.from(document.querySelectorAll('[id="chat-thread-runtime"]'));
  if (!hosts.length) return;

  // Guard: treat 0, NaN, null, undefined all as "no active thread".
  const convId = window.__fridaysChatConversationId;
  const convIdNum = Number(convId);
  if (!convId || !Number.isFinite(convIdNum) || convIdNum <= 0) {
    // Keep bar visible but show idle state instead of hiding it
    hosts.forEach(host => {
      host.innerHTML = '<div class="chat-thread-runtime-head"><div class="chat-thread-runtime-title" style="opacity:0.45;">Thread Runtime · idle</div></div>';
    });
    window.__fridaysThreadRuntimeSnapshot = { jobs: [], updatedAt: new Date().toISOString() };
    window.__fridaysRuntimeLastCompletedJobs = null;
    window.__fridaysRuntimeLastCompletedAt = 0;
    updateChatStatusPills();
    return;
  }

  const list = Array.isArray(jobs) ? jobs.slice() : [];
  list.sort((a, b) => {
    const d = _chatRuntimeSortWeight(a.status) - _chatRuntimeSortWeight(b.status);
    if (d !== 0) return d;
    return String(a.agent || '').localeCompare(String(b.agent || ''));
  });

  // When jobs finish, remember them for a 12-second cooldown so the bar doesn't snap
  // to "No runtime jobs" immediately — gives users continuity between rounds.
  const RUNTIME_COOLDOWN_MS = 12000;
  const now = Date.now();
  const running = list.filter(j => String(j.status || 'running') === 'running');
  const completed = list.filter(j => String(j.status || '') === 'completed');
  const failed = list.filter(j => String(j.status || '') === 'failed');
  const loadingAgents = Array.isArray(window.__fridaysRuntimeLoadingAgents) ? window.__fridaysRuntimeLoadingAgents : [];
  const hasPendingJobs = Array.isArray(window.__fridaysChatPendingJobIds) && window.__fridaysChatPendingJobIds.length > 0;
  const relayActive = (Number(window.__fridaysChatRelayInFlight || 0) > 0) || !!window.__fridaysChatRelayActive || ((window.__fridaysChatRelayQueue || []).length > 0);

  // Keep the last set of completed jobs for the cooldown window.
  if (completed.length > 0 && running.length === 0 && !hasPendingJobs && !loadingAgents.length) {
    window.__fridaysRuntimeLastCompletedJobs = completed.slice();
    window.__fridaysRuntimeLastCompletedAt = now;
  }
  const cooldownActive = !running.length && !hasPendingJobs && !loadingAgents.length &&
    Array.isArray(window.__fridaysRuntimeLastCompletedJobs) &&
    window.__fridaysRuntimeLastCompletedJobs.length > 0 &&
    (now - Number(window.__fridaysRuntimeLastCompletedAt || 0)) < RUNTIME_COOLDOWN_MS;
  const displayList = (running.length || hasPendingJobs || loadingAgents.length)
    ? list
    : (cooldownActive ? window.__fridaysRuntimeLastCompletedJobs : list);

  const canStop = running.length > 0 || loadingAgents.length > 0 || hasPendingJobs;
  const headline = running.length
    ? (running.length === 1 ? '1 agent running' : running.length + ' agents running')
    : (loadingAgents.length || hasPendingJobs
      ? 'Dispatching' + (loadingAgents.length ? ' · ' + loadingAgents.map(a => a).join(', ') : '') + '…'
      : (failed.length ? ('Last run: ' + failed.length + ' failure' + (failed.length > 1 ? 's' : '')) : (cooldownActive ? 'Round complete' : (list.length ? 'Idle' : 'No jobs'))));

  // Bar is always visible — no open/close toggling needed.
  // (Previously: const shouldShow = true; host.classList.toggle('open', shouldShow))

  const chips = [];
  const seen = new Set();
  displayList.forEach(job => {
    const agent = String(job.agent || 'agent');
    const key = agent.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    const eta = Number(job.eta_remaining_seconds || 0);
    const elapsed = Number(job.elapsed_ms || 0);
    const elapsedS = Number.isFinite(elapsed) ? Math.max(0, Math.round(elapsed / 1000)) : 0;
    const chipClass = cooldownActive ? _chatRuntimeStatusClass(job) + ' cooldown' : _chatRuntimeStatusClass(job);
    chips.push(_renderThreadRuntimeChip(
      agent,
      _chatRuntimeStateLabel(job),
      chipClass,
      eta > 0 ? ('~' + eta + 's') : ('+' + elapsedS + 's')
    ));
  });
  loadingAgents.forEach(agent => {
    const key = String(agent || '').toLowerCase();
    if (!key || seen.has(key)) return;
    seen.add(key);
    chips.push(_renderThreadRuntimeChip(agent, 'queued', 'initializing', ''));
  });

  const panelHtml = `
    <div class="chat-thread-runtime-head">
      <div style="display:flex;align-items:center;gap:6px;min-width:0;">
        <div class="chat-thread-runtime-title">Thread Runtime · #${Number(convId)}</div>
        ${canStop ? '<button class="chat-action-btn" onclick="stopPendingAgents()" title="Stop active agent runs">Stop</button>' : ''}
      </div>
      <div class="chat-thread-runtime-meta">${_escapeHtml(sourceLabel)} · ${_escapeHtml(headline)}</div>
    </div>
    ${(chips.length || hasPendingJobs) ? `<div class="chat-thread-runtime-grid">${chips.join('')}</div>` : ''}
  `;
  hosts.forEach(host => {
    host.innerHTML = panelHtml;
  });

  window.__fridaysThreadRuntimeSnapshot = { jobs: list, updatedAt: new Date().toISOString() };
  updateChatStatusPills();
}

function toggleRuntimePin() {
  window.__fridaysChatRuntimePinned = true;
  pollActiveThreadRuntime(true);
}

function pollActiveThreadRuntime(force = false) {
  const convId = window.__fridaysChatConversationId;
  const convIdNum = Number(convId);
  if (!convId || !Number.isFinite(convIdNum) || convIdNum <= 0) {
    _renderThreadRuntimePanel([], 'idle');
    _syncThinkingBubbles([]);
    return Promise.resolve();
  }
  const snapshotJobs = Array.isArray(window.__fridaysThreadRuntimeSnapshot?.jobs)
    ? window.__fridaysThreadRuntimeSnapshot.jobs
    : [];
  const loadingAgents = Array.isArray(window.__fridaysRuntimeLoadingAgents)
    ? window.__fridaysRuntimeLoadingAgents
    : [];
  const hasPendingJobs = Array.isArray(window.__fridaysChatPendingJobIds) && window.__fridaysChatPendingJobIds.length > 0;
  const relayActive = (Number(window.__fridaysChatRelayInFlight || 0) > 0) || !!window.__fridaysChatRelayActive || ((window.__fridaysChatRelayQueue || []).length > 0);
  const hasActiveSnapshot = snapshotJobs.some(j => String(j.status || 'running') === 'running');
  if (!force && window.__fridaysChatPendingPollTimer) {
    return Promise.resolve();
  }
  return fetch('/api/chat/jobs/status?conversation_id=' + encodeURIComponent(convId))
    .then(r => r.json())
    .then(data => {
      const jobs = (data && Array.isArray(data.jobs)) ? data.jobs : [];
      _renderThreadRuntimePanel(jobs, force ? 'sync' : 'poll');
      _syncThinkingBubbles(jobs);
    })
    .catch(() => {
      // Keep existing panel state on transient polling errors.
    });
}

// Thread runtime polling — intentional SSE fallback.
// The swarm uses polling (not SSE/WebSockets) for thread runtime status because:
// 1. Polling is simpler and more reliable behind reverse proxies and on mobile.
// 2. The 2-second interval is sufficient for the relay queue UI.
// 3. SSE connections would need per-conversation multiplexing — complexity with no UX gain.
// This is a deliberate architecture choice, not a TODO.
function startThreadRuntimePolling() {
  if (window.__fridaysThreadRuntimePollTimer) {
    clearInterval(window.__fridaysThreadRuntimePollTimer);
    window.__fridaysThreadRuntimePollTimer = null;
  }
  pollActiveThreadRuntime(true);
  window.__fridaysThreadRuntimePollTimer = setInterval(() => {
    pollActiveThreadRuntime(false);
  }, 2000);
}

function _humanBytes(bytes) {
  const n = Number(bytes || 0);
  if (!Number.isFinite(n) || n <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let idx = 0;
  let val = n;
  while (val >= 1024 && idx < units.length - 1) {
    val /= 1024;
    idx += 1;
  }
  return `${val >= 10 ? val.toFixed(0) : val.toFixed(1)} ${units[idx]}`;
}

function _isTextLikeAttachment(file) {
  if (!file) return false;
  const type = String(file.type || '').toLowerCase();
  if (type.startsWith('text/')) return true;
  const name = String(file.name || '').toLowerCase();
  return /\.(txt|md|markdown|json|csv|log|xml|html|css|js|ts|tsx|jsx|py|sh|yml|yaml|ini|toml|conf|cfg|sql)$/i.test(name);
}

async function _readAttachmentText(file) {
  try {
    const raw = await file.text();
    const trimmed = String(raw || '');
    if (trimmed.length <= CHAT_ATTACH_MAX_TEXT_CHARS_PER_FILE) {
      return { text: trimmed, truncated: false };
    }
    return { text: trimmed.slice(0, CHAT_ATTACH_MAX_TEXT_CHARS_PER_FILE), truncated: true };
  } catch (_) {
    return { text: '', truncated: false };
  }
}

function pickChatAttachments() {
  openChatAttachmentPicker(false);
}

function changeChatAttachments() {
  openChatAttachmentPicker(true);
}

function openChatAttachmentPicker(replaceExisting) {
  const input = document.getElementById('chat-attachment-input');
  if (!input) return;
  input.dataset.replaceMode = replaceExisting ? '1' : '0';
  input.click();
}

async function handleChatAttachmentInput(event) {
  const input = event?.target || document.getElementById('chat-attachment-input');
  if (!input) return;
  const replaceMode = input.dataset.replaceMode === '1';
  input.dataset.replaceMode = '0';
  if (!input.files || !input.files.length) {
    input.value = '';
    return;
  }
  if (replaceMode) {
    clearChatAttachments();
  }
  await ingestChatAttachments(input.files);
  input.value = '';
}

function _revokeAttachmentPreview(att) {
  if (!att) return;
  if (att.previewUrl && att.previewUrl.startsWith('blob:')) {
    try { URL.revokeObjectURL(att.previewUrl); } catch (_) {}
  }
}

async function ingestChatAttachments(fileList) {
  if (!fileList || !fileList.length) return;
  const current = Array.isArray(window.__fridaysChatAttachments) ? window.__fridaysChatAttachments : [];
  const incoming = Array.from(fileList);
  const availableSlots = Math.max(0, CHAT_ATTACH_MAX_FILES - current.length);
  const picked = incoming.slice(0, availableSlots);
  if (incoming.length > picked.length) {
    showToast(`Attachment limit is ${CHAT_ATTACH_MAX_FILES} files`, 'info');
  }

  for (const file of picked) {
    if (Number(file.size || 0) > CHAT_ATTACH_MAX_SIZE_BYTES) {
      showToast(`${file.name}: exceeds 10 MB limit`, 'error');
      continue;
    }
    const duplicate = current.find(a => a.name === file.name && Number(a.size || 0) === Number(file.size || 0));
    if (duplicate) continue;
    const isText = _isTextLikeAttachment(file);
    const isImage = String(file.type || '').toLowerCase().startsWith('image/');
    const parsed = isText ? await _readAttachmentText(file) : { text: '', truncated: false };
    current.push({
      id: Date.now().toString(36) + Math.random().toString(36).slice(2, 8),
      name: String(file.name || 'attachment'),
      type: String(file.type || 'application/octet-stream'),
      size: Number(file.size || 0),
      isText,
      isImage,
      inlineText: parsed.text,
      truncated: !!parsed.truncated,
      previewUrl: isImage ? URL.createObjectURL(file) : '',
    });
  }

  window.__fridaysChatAttachments = current.slice(0, CHAT_ATTACH_MAX_FILES);
  renderChatAttachments();
  updateComposerMeta();
}

function removeChatAttachment(attachmentId) {
  const before = Array.isArray(window.__fridaysChatAttachments) ? window.__fridaysChatAttachments : [];
  const removed = before.find(a => a.id === attachmentId);
  const after = before.filter(a => a.id !== attachmentId);
  if (after.length === before.length) return;
  _revokeAttachmentPreview(removed);
  window.__fridaysChatAttachments = after;
  renderChatAttachments();
  updateComposerMeta();
}

function clearChatAttachments() {
  (window.__fridaysChatAttachments || []).forEach(_revokeAttachmentPreview);
  window.__fridaysChatAttachments = [];
  renderChatAttachments();
  updateComposerMeta();
}

function renderChatAttachmentInlineState() {
  const host = document.getElementById('chat-attach-inline-state');
  if (!host) return;
  const attachments = Array.isArray(window.__fridaysChatAttachments) ? window.__fridaysChatAttachments : [];
  if (!attachments.length) {
    host.innerHTML = '';
    host.classList.remove('visible');
    return;
  }

  const first = attachments[0];
  const firstLabel = `${first.name} (${_humanBytes(first.size)})`;
  const summary = attachments.length === 1
    ? firstLabel
    : `${attachments.length} files attached · ${firstLabel}`;

  host.innerHTML = `<span class="chat-attach-inline-name" title="${_escapeHtml(summary)}">${_escapeHtml(summary)}</span><span class="chat-attach-inline-actions"><button type="button" class="chat-attach-inline-btn" onclick="changeChatAttachments()">Change</button><button type="button" class="chat-attach-inline-btn" onclick="clearChatAttachments()">Remove</button></span>`;
  host.classList.add('visible');
}

function renderChatAttachments() {
  const host = document.getElementById('chat-attachments');
  if (!host) return;
  const attachments = Array.isArray(window.__fridaysChatAttachments) ? window.__fridaysChatAttachments : [];
  renderChatAttachmentInlineState();
  if (!attachments.length) {
    host.innerHTML = '';
    host.style.display = 'none';
    return;
  }
  host.style.display = 'flex';
  host.innerHTML = attachments.map(att => {
    const icon = att.isText ? '<svg viewBox="0 0 16 16" width="12" height="12" fill="none" style="vertical-align:-2px;"><path d="M4.5 1.5h4.59L12.5 5v9.5h-8z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M9 1.5v4h3.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>' : '<svg viewBox="0 0 16 16" width="12" height="12" fill="none" style="vertical-align:-2px;"><path d="M2.5 4.5h11v8h-11z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M5.5 4.5V2.5h5v2" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>';
    const label = `${icon} ${att.name} (${_humanBytes(att.size)})${att.truncated ? ' • clipped' : ''}`;
    const thumb = att.isImage && att.previewUrl
      ? `<img class="chat-attachment-thumb" src="${_escapeHtml(att.previewUrl)}" alt="${_escapeHtml(att.name)}">`
      : '';
    return `<span class="chat-attachment-chip">${thumb}<span class="chat-attachment-label" title="${_escapeHtml(label)}">${_escapeHtml(label)}</span><button type="button" class="chat-attachment-remove" onclick="removeChatAttachment('${_escapeHtml(att.id)}')">✕</button></span>`;
  }).join('');
}

function _rememberBubbleAttachment(att) {
  const id = 'att_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  window.__fridaysBubbleAttachmentStore[id] = {
    name: String(att?.name || 'attachment'),
    type: String(att?.type || 'application/octet-stream'),
    size: Number(att?.size || 0),
    sizeLabel: String(att?.sizeLabel || ''),
    inlineText: String(att?.inlineText || ''),
    previewUrl: String(att?.previewUrl || ''),
    truncated: !!att?.truncated,
    source: String(att?.source || 'composer'),
  };
  return id;
}

function openBubbleAttachment(attachmentId) {
  const att = (window.__fridaysBubbleAttachmentStore || {})[String(attachmentId || '')];
  if (!att) {
    showToast('Attachment preview is unavailable', 'error');
    return;
  }
  if (att.previewUrl) {
    window.open(att.previewUrl, '_blank', 'noopener');
    return;
  }
  if (att.inlineText) {
    const blob = new Blob([att.inlineText], { type: att.type || 'text/plain' });
    const url = URL.createObjectURL(blob);
    window.open(url, '_blank', 'noopener');
    setTimeout(() => {
      try { URL.revokeObjectURL(url); } catch (_) {}
    }, 15000);
    return;
  }
  showToast('No preview content stored for this attachment', 'info');
}

function downloadBubbleAttachment(attachmentId) {
  const att = (window.__fridaysBubbleAttachmentStore || {})[String(attachmentId || '')];
  if (!att) {
    showToast('Attachment download is unavailable', 'error');
    return;
  }
  let blob = null;
  if (att.inlineText) {
    blob = new Blob([att.inlineText], { type: att.type || 'text/plain' });
  } else if (att.previewUrl && att.previewUrl.startsWith('blob:')) {
    const link = document.createElement('a');
    link.href = att.previewUrl;
    link.download = att.name || 'attachment';
    link.click();
    return;
  }
  if (!blob) {
    showToast('No downloadable content stored for this attachment', 'info');
    return;
  }
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = att.name || 'attachment';
  link.click();
  setTimeout(() => {
    try { URL.revokeObjectURL(url); } catch (_) {}
  }, 15000);
}

function _renderBubbleAttachments(attachments) {
  if (!Array.isArray(attachments) || !attachments.length) return '';
  const rows = attachments.map(att => {
    const normalized = {
      name: String(att?.name || 'attachment'),
      type: String(att?.type || 'application/octet-stream'),
      size: Number(att?.size || 0),
      sizeLabel: String(att?.sizeLabel || ''),
      inlineText: String(att?.inlineText || ''),
      previewUrl: String(att?.previewUrl || ''),
      truncated: !!att?.truncated,
      isImage: !!att?.isImage,
      isText: att?.isText !== false,
      source: String(att?.source || 'composer'),
    };
    const icon = normalized.isImage ? '<svg viewBox="0 0 16 16" width="12" height="12" fill="none" style="vertical-align:-2px;"><rect x="2" y="2.5" width="12" height="11" rx="1.5" stroke="currentColor" stroke-width="1.3"/><circle cx="5.5" cy="6" r="1.5" stroke="currentColor" stroke-width="1.1"/><path d="M2 10.5l3-3 2.5 2L10 7l4 4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>' : (normalized.isText ? '<svg viewBox="0 0 16 16" width="12" height="12" fill="none" style="vertical-align:-2px;"><path d="M4.5 1.5h4.59L12.5 5v9.5h-8z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M9 1.5v4h3.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>' : '<svg viewBox="0 0 16 16" width="12" height="12" fill="none" style="vertical-align:-2px;"><path d="M2.5 4.5h11v8h-11z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M5.5 4.5V2.5h5v2" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>');
    const sizeText = normalized.sizeLabel || _humanBytes(normalized.size);
    const meta = `${normalized.type || 'unknown'} · ${sizeText}${normalized.truncated ? ' · clipped' : ''}`;
    const attachmentId = _rememberBubbleAttachment(normalized);
    const canOpen = !!(normalized.previewUrl || normalized.inlineText);
    const canDownload = !!(normalized.inlineText || normalized.previewUrl);
    const actions = `<div class="chat-bubble-attachment-actions">${canOpen ? `<button type="button" class="chat-bubble-attachment-btn" onclick="openBubbleAttachment('${_escapeHtml(attachmentId)}')">Open</button>` : ''}${canDownload ? `<button type="button" class="chat-bubble-attachment-btn" onclick="downloadBubbleAttachment('${_escapeHtml(attachmentId)}')">Download</button>` : ''}</div>`;
    return `<div class="chat-bubble-attachment-row"><span class="chat-bubble-attachment-icon">${icon}</span><div class="chat-bubble-attachment-main"><div class="chat-bubble-attachment-name" title="${_escapeHtml(normalized.name)}">${_escapeHtml(normalized.name)}</div><div class="chat-bubble-attachment-meta">${_escapeHtml(meta)}</div>${actions}</div></div>`;
  }).join('');
  return `<div class="chat-bubble-attachments">${rows}</div>`;
}

function _extractAttachmentsFromMessage(content) {
  const raw = String(content || '');
  const marker = '\n\n[Attachments]\n';
  const idx = raw.indexOf(marker);
  if (idx < 0) {
    return { text: raw, attachments: [] };
  }

  const baseText = raw.slice(0, idx).trimEnd();
  const block = raw.slice(idx + 2);
  const lines = block.split(/\r?\n/);
  const attachments = [];
  let i = 0;

  while (i < lines.length) {
    const line = String(lines[i] || '');
    const infoMatch = line.match(/^-\s+(.+?)\s+\((.+?),\s*([^)]+)\)(.*)$/);
    if (infoMatch) {
      const flags = String(infoMatch[4] || '');
      attachments.push({
        name: String(infoMatch[1] || 'attachment').trim(),
        type: String(infoMatch[2] || 'application/octet-stream').trim(),
        sizeLabel: String(infoMatch[3] || '0 B').trim(),
        isText: !flags.includes('[binary metadata only]'),
        isImage: String(infoMatch[2] || '').toLowerCase().startsWith('image/'),
        truncated: flags.includes('[clipped]'),
        inlineText: '',
        source: 'history',
      });
      i += 1;
      continue;
    }

    const fileStart = line.match(/^--- FILE:\s+(.+?)\s+---$/);
    if (fileStart) {
      const fileName = String(fileStart[1] || 'attachment').trim();
      const payload = [];
      i += 1;
      while (i < lines.length && !/^--- END FILE:/.test(String(lines[i] || ''))) {
        payload.push(String(lines[i] || ''));
        i += 1;
      }
      const endLine = i < lines.length ? String(lines[i] || '') : '';
      const clipped = /\(clipped\)/i.test(endLine);
      const existing = attachments.find(a => a.name === fileName) || null;
      if (existing) {
        existing.inlineText = payload.join('\n');
        existing.truncated = existing.truncated || clipped;
      } else {
        attachments.push({
          name: fileName,
          type: 'text/plain',
          sizeLabel: 'inline',
          isText: true,
          isImage: false,
          truncated: clipped,
          inlineText: payload.join('\n'),
          source: 'history',
        });
      }
      i += 1;
      continue;
    }

    i += 1;
  }

  return { text: baseText, attachments };
}

function initChatAttachmentDnD() {
  const wrapper = document.getElementById('input-wrapper');
  if (!wrapper || wrapper.dataset.attachDndBound === '1') return;
  wrapper.dataset.attachDndBound = '1';

  const onDragOver = (event) => {
    event.preventDefault();
    wrapper.classList.add('attachment-drag-over');
  };
  const onDragLeave = (event) => {
    if (!event.relatedTarget || !wrapper.contains(event.relatedTarget)) {
      wrapper.classList.remove('attachment-drag-over');
    }
  };
  const onDrop = async (event) => {
    event.preventDefault();
    wrapper.classList.remove('attachment-drag-over');
    const files = event.dataTransfer && event.dataTransfer.files ? event.dataTransfer.files : null;
    if (!files || !files.length) return;
    await ingestChatAttachments(files);
    showToast('Attachment added from drag and drop', 'success');
  };

  wrapper.addEventListener('dragenter', onDragOver);
  wrapper.addEventListener('dragover', onDragOver);
  wrapper.addEventListener('dragleave', onDragLeave);
  wrapper.addEventListener('drop', onDrop);
}

function _buildAttachmentPayload() {
  const attachments = Array.isArray(window.__fridaysChatAttachments) ? window.__fridaysChatAttachments : [];
  if (!attachments.length) return { wireBlock: '', bubbleSummary: '', bubbleAttachments: [] };

  let remaining = CHAT_ATTACH_MAX_TOTAL_INLINE_CHARS;
  const wireLines = ['[Attachments]'];
  const bubbleLines = [];
  const bubbleAttachments = [];

  attachments.forEach(att => {
    const info = `${att.name} (${att.type || 'unknown'}, ${_humanBytes(att.size)})`;
    const infoFlags = `${att.truncated ? ' [clipped]' : ''}${att.isText ? '' : ' [binary metadata only]'}`;
    bubbleLines.push(`- ${info}${infoFlags}`);
    wireLines.push(`- ${info}${infoFlags}`);
    bubbleAttachments.push({
      name: att.name,
      type: att.type,
      size: Number(att.size || 0),
      isText: !!att.isText,
      isImage: !!att.isImage,
      inlineText: String(att.inlineText || ''),
      truncated: !!att.truncated,
      previewUrl: String(att.previewUrl || ''),
      source: 'composer',
    });

    if (att.isText && att.inlineText && remaining > 0) {
      const nextText = String(att.inlineText || '');
      const clipped = nextText.length > remaining;
      const slice = clipped ? nextText.slice(0, remaining) : nextText;
      remaining -= slice.length;
      wireLines.push(`--- FILE: ${att.name} ---`);
      wireLines.push(slice);
      wireLines.push(`--- END FILE: ${att.name}${att.truncated || clipped ? ' (clipped)' : ''} ---`);
    }
  });

  return {
    wireBlock: '\n\n' + wireLines.join('\n'),
    bubbleSummary: '\n\nAttached files:\n' + bubbleLines.join('\n'),
    bubbleAttachments,
  };
}

function _saveDesktopNotificationPreference(enabled) {
  localStorage.setItem(CHAT_DESKTOP_NOTIFY_KEY, enabled ? '1' : '0');
}

function updateNotificationControls() {
  const btn = document.getElementById('chat-notify-toggle-btn');
  const available = typeof Notification !== 'undefined';
  const enabled = !!window.__fridaysDesktopNotificationsEnabled;
  if (btn) {
    let text = enabled ? 'Notifications On' : 'Notifications Off';
    if (available && Notification.permission === 'denied') text = 'Notifications Blocked';
    btn.textContent = text;
  }
  updateChatStatusPills();
}

async function toggleDesktopNotifications() {
  const available = typeof Notification !== 'undefined';
  if (!available) {
    showToast('Desktop notifications are not supported in this browser', 'error');
    return;
  }

  const currentlyEnabled = !!window.__fridaysDesktopNotificationsEnabled;
  if (currentlyEnabled) {
    window.__fridaysDesktopNotificationsEnabled = false;
    _saveDesktopNotificationPreference(false);
    updateNotificationControls();
    showToast('Desktop notifications turned off', 'info');
    return;
  }

  if (Notification.permission === 'denied') {
    showToast('Notifications are blocked in browser settings', 'error');
    updateNotificationControls();
    return;
  }

  if (Notification.permission !== 'granted') {
    const permission = await Notification.requestPermission();
    if (permission !== 'granted') {
      showToast('Notification permission not granted', 'info');
      updateNotificationControls();
      return;
    }
  }

  window.__fridaysDesktopNotificationsEnabled = true;
  _saveDesktopNotificationPreference(true);
  updateNotificationControls();
  showToast('Desktop notifications enabled', 'success');
}

function notifyDesktop(title, body, opts = {}) {
  if (!window.__fridaysDesktopNotificationsEnabled) return;
  if (typeof Notification === 'undefined') return;
  if (Notification.permission !== 'granted') return;
  const shouldNotify = opts.force || document.hidden || (typeof document.hasFocus === 'function' && !document.hasFocus());
  if (!shouldNotify) return;
  try {
    const n = new Notification(String(title || 'Fridays Chat'), {
      body: String(body || '').slice(0, 200),
      tag: opts.tag || 'fridays-chat',
      renotify: false,
      silent: false,
    });
    n.onclick = () => {
      try { window.focus(); } catch (_) {}
      n.close();
    };
  } catch (_) {
    // Ignore browser notification failures.
  }
}

function _normalizeDictionaryWord(word) {
  return String(word || '')
    .trim()
    .toLowerCase()
    .replace(/^[^a-z]+|[^a-z]+$/g, '');
}

function _loadChatCustomDictionary() {
  try {
    const raw = JSON.parse(localStorage.getItem(CHAT_CUSTOM_DICTIONARY_KEY) || '[]');
    if (!Array.isArray(raw)) return new Set();
    return new Set(raw.map(_normalizeDictionaryWord).filter(Boolean));
  } catch (_) {
    return new Set();
  }
}

function _saveChatCustomDictionary() {
  const sorted = Array.from(window.__fridaysChatCustomDictionary || []).filter(Boolean).sort();
  localStorage.setItem(CHAT_CUSTOM_DICTIONARY_KEY, JSON.stringify(sorted));
  updateChatStatusPills();
}

function addWordToCustomDictionary(word) {
  const normalized = _normalizeDictionaryWord(word);
  if (!normalized) return false;
  window.__fridaysChatCustomDictionary.add(normalized);
  _saveChatCustomDictionary();
  return true;
}

function removeWordFromCustomDictionary(word) {
  const normalized = _normalizeDictionaryWord(word);
  if (!normalized) return false;
  const removed = window.__fridaysChatCustomDictionary.delete(normalized);
  if (removed) _saveChatCustomDictionary();
  return removed;
}

function _extractCurrentInputWord() {
  const input = document.getElementById('question-input');
  if (!input) return '';
  const cursor = Number.isFinite(input.selectionStart) ? input.selectionStart : input.value.length;
  const before = String(input.value || '').slice(0, cursor);
  const m = before.match(/([A-Za-z][A-Za-z'-]{1,})$/);
  return m ? m[1] : '';
}

function _replaceCurrentInputWord(replacement) {
  const input = document.getElementById('question-input');
  if (!input) return;
  const cursor = Number.isFinite(input.selectionStart) ? input.selectionStart : input.value.length;
  const before = String(input.value || '').slice(0, cursor);
  const after = String(input.value || '').slice(cursor);
  const next = String(replacement || '');
  const replaced = before.replace(/([A-Za-z][A-Za-z'-]{1,})$/, next);
  input.value = replaced + after;
  const pos = replaced.length;
  input.focus();
  input.setSelectionRange(pos, pos);
}

function updateChatSpellHelper() {
  const helper = document.getElementById('chat-spell-helper');
  if (!helper) return;
  const word = _extractCurrentInputWord();
  const normalized = _normalizeDictionaryWord(word);
  if (!normalized) {
    helper.style.display = 'none';
    helper.innerHTML = '';
    return;
  }
  if ((window.__fridaysChatCustomDictionary || new Set()).has(normalized)) {
    helper.style.display = 'none';
    helper.innerHTML = '';
    return;
  }

  const suggestion = CHAT_TYPO_SUGGESTIONS[normalized];
  if (!suggestion) {
    helper.style.display = 'none';
    helper.innerHTML = '';
    return;
  }

  helper.style.display = 'block';
  helper.innerHTML = `Possible typo: <strong>${_escapeHtml(word)}</strong> → <strong>${_escapeHtml(suggestion)}</strong>
    <button class="chat-action-btn" style="margin-left:8px;" onclick="applySpellSuggestion('${_escapeHtml(suggestion)}')">Apply</button>
    <button class="chat-action-btn" style="margin-left:4px;" onclick="keepCurrentWord()">Keep</button>`;
}

function applySpellSuggestion(word) {
  _replaceCurrentInputWord(word);
  updateChatSpellHelper();
}

function keepCurrentWord() {
  const word = _extractCurrentInputWord();
  if (!word) return;
  if (addWordToCustomDictionary(word)) {
    showToast(`Saved "${word}" in your dictionary`, 'success');
  }
  updateChatSpellHelper();
}

function openChatDictionaryManager() {
  const current = Array.from(window.__fridaysChatCustomDictionary || []).sort();
  const hint = current.length ? current.join(', ') : '(empty)';
  const raw = prompt(
    'Dictionary editor\nAdd words with commas. Prefix a word with - to remove.\nCurrent: ' + hint,
    ''
  );
  if (raw === null) return;
  const tokens = String(raw || '')
    .split(',')
    .map(t => t.trim())
    .filter(Boolean);
  if (!tokens.length) return;

  let added = 0;
  let removed = 0;
  tokens.forEach(t => {
    if (t.startsWith('-')) {
      if (removeWordFromCustomDictionary(t.slice(1))) removed += 1;
    } else {
      if (addWordToCustomDictionary(t)) added += 1;
    }
  });
  updateChatSpellHelper();
  showToast(`Dictionary updated: +${added} / -${removed}`, 'success');
}

async function exportChatDictionary() {
  const words = Array.from(window.__fridaysChatCustomDictionary || []).sort();
  const payload = JSON.stringify(words);
  try {
    if (navigator && navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(payload);
      showToast(`Dictionary copied (${words.length} word${words.length === 1 ? '' : 's'})`, 'success');
      return;
    }
  } catch (_) {
    // Fallback to prompt below.
  }
  prompt('Copy your dictionary JSON:', payload);
}

function importChatDictionary() {
  const raw = prompt('Paste dictionary JSON array or comma-separated words:');
  if (raw === null) return;
  let words = [];
  const trimmed = String(raw || '').trim();
  if (!trimmed) return;

  try {
    const parsed = JSON.parse(trimmed);
    if (Array.isArray(parsed)) {
      words = parsed.map(v => String(v || '').trim());
    }
  } catch (_) {
    words = trimmed.split(',').map(v => v.trim());
  }

  let added = 0;
  words.forEach(w => {
    if (addWordToCustomDictionary(w)) added += 1;
  });
  updateChatSpellHelper();
  showToast(`Imported ${added} word${added === 1 ? '' : 's'}`, 'success');
}

function clearChatDictionary() {
  const current = Array.from(window.__fridaysChatCustomDictionary || []);
  if (!current.length) {
    showToast('Dictionary already empty', 'info');
    return;
  }
  if (!confirm(`Clear custom dictionary (${current.length} words)?`)) return;
  window.__fridaysChatCustomDictionary = new Set();
  _saveChatCustomDictionary();
  updateChatSpellHelper();
  showToast('Dictionary reset', 'success');
}

function _chatSectionElement(sectionKey) {
  return document.getElementById('chat-section-' + String(sectionKey || '').trim());
}

function _syncChatSectionAria(sectionKey) {
  const section = _chatSectionElement(sectionKey);
  if (!section) return;
  const header = section.querySelector('.chat-section-header');
  if (!header) return;
  const expanded = !section.classList.contains('collapsed');
  header.setAttribute('aria-expanded', expanded ? 'true' : 'false');
}

function toggleChatSection(sectionKey) {
  if (String(sectionKey || '').trim() === 'main') {
    return;
  }
  const section = _chatSectionElement(sectionKey);
  if (!section) return;
  section.classList.toggle('collapsed');
  _syncChatSectionAria(sectionKey);
}

function _applyMainRuntimePanelState() {
  const sections = Array.from(document.querySelectorAll('[id="chat-section-main"]'));
  if (!sections.length) return;
  sections.forEach(section => {
    section.classList.remove('runtime-hidden');
    const header = section.querySelector('.chat-section-header');
    if (header) {
      header.setAttribute('aria-expanded', 'true');
    }
  });
}

function toggleMainRuntimePanel(forceVisible = null) {
  window.__fridaysChatRuntimeHidden = false;
  window.__fridaysChatRuntimePinned = true;
  _applyMainRuntimePanelState();
  pollActiveThreadRuntime(true);
}

function _clampChatDockWidth(width) {
  const n = Number(width || 420);
  if (!Number.isFinite(n)) return 420;
  return Math.max(280, Math.min(760, Math.round(n)));
}

function _clampChatThreadWidth(width) {
  const n = Number(width || 280);
  if (!Number.isFinite(n)) return 280;
  return Math.max(220, Math.min(520, Math.round(n)));
}

function _normalizeChatUiScale(scale) {
  const n = Number(scale);
  const fallback = Number(window.__fridaysChatUiScale || CHAT_UI_SCALE_DEFAULT);
  const base = Number.isFinite(n) ? n : fallback;
  let best = CHAT_UI_SCALE_OPTIONS[0];
  let bestDistance = Math.abs(base - best);
  CHAT_UI_SCALE_OPTIONS.forEach(opt => {
    const distance = Math.abs(base - opt);
    if (distance < bestDistance) {
      best = opt;
      bestDistance = distance;
    }
  });
  return Number(best.toFixed(2));
}

function _chatUiScaleOptionValue(scale) {
  return _normalizeChatUiScale(scale).toFixed(2);
}

function _syncChatUiScaleControls(scale) {
  const value = _chatUiScaleOptionValue(scale);
  document.querySelectorAll('[id="chat-font-size-select"]').forEach(select => {
    if (select) select.value = value;
  });
  const themeSelect = document.getElementById('theme-font-size-select');
  if (themeSelect) themeSelect.value = value;
}

function resetThemeAndFontDefaults() {
  try {
    const settings = JSON.parse(localStorage.getItem('fridays-settings') || '{}');
    settings.time = 'auto';
    settings.atmosphereMode = 'auto';
    settings.foundationMode = 'auto';
    settings.atmosphereValue = 38;
    settings.accentValue = 50;
    settings.hueValue = 50;
    settings.contrastValue = 58;
    settings.glowValue = 52;
    settings.scene = 'beach';
    settings.sceneEffect = 'on';
    settings.opacity = 5;
    localStorage.setItem('fridays-settings', JSON.stringify(settings));
    localStorage.setItem('fridays_theme_mode', 'auto');
    localStorage.setItem('fridays_foundation_mode', 'auto');
    localStorage.setItem('fridays_atmosphere_value', '38');
    localStorage.setItem('fridays_accent_value', '50');
    localStorage.setItem('fridays_hue_value', '50');
    localStorage.setItem('fridays_contrast_value', '58');
    localStorage.setItem('fridays_glow_value', '52');
    localStorage.setItem('fridays_scene', 'beach');
    localStorage.setItem('fridays_scene_effect', 'on');
  } catch (_) {}
  applyTimeTheme('auto');
  if (typeof applyScene === 'function') applyScene('beach');
  document.documentElement.style.setProperty('--glass-opacity', '0.95');
  setChatUiScale(CHAT_UI_SCALE_DEFAULT);
  showToast('Atmosphere and font reset to system defaults', 'success');
}

function _applyChatDockLayoutState() {
  const threadCollapsed = !!window.__fridaysChatThreadCollapsed;
  const threadWidth = _clampChatThreadWidth(window.__fridaysChatThreadWidth);
  const collapsed = !!window.__fridaysChatDockCollapsed;
  const width = _clampChatDockWidth(window.__fridaysChatDockWidth);
  const scale = _normalizeChatUiScale(window.__fridaysChatUiScale || CHAT_UI_SCALE_DEFAULT);

  document.querySelectorAll('[id="chat-layout"]').forEach(layout => {
    const rail = layout.querySelector('[id="chat-thread-rail"]');
    const dock = layout.querySelector('[id="chat-right-dock"]');
    const fontSelect = layout.querySelector('[id="chat-font-size-select"]');
    if (!rail || !dock) return;

    layout.classList.toggle('threads-collapsed', threadCollapsed);
    rail.classList.toggle('collapsed', threadCollapsed);
    if (!threadCollapsed) {
      rail.style.width = `${threadWidth}px`;
      window.__fridaysChatThreadWidth = threadWidth;
    }

    layout.classList.toggle('dock-collapsed', collapsed);
    dock.classList.toggle('collapsed', collapsed);
    if (!collapsed) {
      dock.style.width = `${width}px`;
      window.__fridaysChatDockWidth = width;
    }

    layout.style.setProperty('--chat-ui-scale', String(scale));
    if (fontSelect) fontSelect.value = _chatUiScaleOptionValue(scale);
  });
  _syncChatUiScaleControls(scale);
}

function toggleThreadRail(forceExpanded = null) {
  const shouldExpand = forceExpanded === true;
  const shouldCollapse = forceExpanded === false;
  if (shouldExpand) {
    window.__fridaysChatThreadCollapsed = false;
  } else if (shouldCollapse) {
    window.__fridaysChatThreadCollapsed = true;
  } else {
    window.__fridaysChatThreadCollapsed = !window.__fridaysChatThreadCollapsed;
  }
  localStorage.setItem(CHAT_THREAD_COLLAPSED_KEY, window.__fridaysChatThreadCollapsed ? '1' : '0');
  _applyChatDockLayoutState();
}

function toggleChatDock(forceExpanded = null) {
  const shouldExpand = forceExpanded === true;
  const shouldCollapse = forceExpanded === false;
  if (shouldExpand) {
    window.__fridaysChatDockCollapsed = false;
  } else if (shouldCollapse) {
    window.__fridaysChatDockCollapsed = true;
  } else {
    window.__fridaysChatDockCollapsed = !window.__fridaysChatDockCollapsed;
  }
  localStorage.setItem(CHAT_DOCK_COLLAPSED_KEY, window.__fridaysChatDockCollapsed ? '1' : '0');
  _applyChatDockLayoutState();
}

function setChatUiScale(scale) {
  const next = _normalizeChatUiScale(scale);
  window.__fridaysChatUiScale = next;
  localStorage.setItem(CHAT_UI_SCALE_KEY, String(next));
  _applyChatDockLayoutState();
}

function startChatDockResize(event) {
  if (window.__fridaysChatDockCollapsed) return;
  const dock = document.getElementById('chat-right-dock');
  if (!dock) return;
  event.preventDefault();

  const onMove = (ev) => {
    const width = window.innerWidth - Number(ev.clientX || 0);
    const next = _clampChatDockWidth(width);
    window.__fridaysChatDockWidth = next;
    dock.style.width = `${next}px`;
  };

  const onUp = () => {
    localStorage.setItem(CHAT_DOCK_WIDTH_KEY, String(window.__fridaysChatDockWidth));
    window.removeEventListener('mousemove', onMove);
    window.removeEventListener('mouseup', onUp);
  };

  window.addEventListener('mousemove', onMove);
  window.addEventListener('mouseup', onUp);
}

function startChatThreadResize(event) {
  if (window.__fridaysChatThreadCollapsed) return;
  const rail = document.getElementById('chat-thread-rail');
  if (!rail) return;
  event.preventDefault();

  const onMove = (ev) => {
    const width = Number(ev.clientX || 0);
    const next = _clampChatThreadWidth(width);
    window.__fridaysChatThreadWidth = next;
    rail.style.width = `${next}px`;
  };

  const onUp = () => {
    localStorage.setItem(CHAT_THREAD_WIDTH_KEY, String(window.__fridaysChatThreadWidth));
    window.removeEventListener('mousemove', onMove);
    window.removeEventListener('mouseup', onUp);
  };

  window.addEventListener('mousemove', onMove);
  window.addEventListener('mouseup', onUp);
}

function initChatDockLayout() {
  window.__fridaysChatThreadWidth = _clampChatThreadWidth(window.__fridaysChatThreadWidth);
  window.__fridaysChatDockWidth = _clampChatDockWidth(window.__fridaysChatDockWidth);
  window.__fridaysChatUiScale = _normalizeChatUiScale(window.__fridaysChatUiScale || CHAT_UI_SCALE_DEFAULT);
  _applyChatDockLayoutState();
}

function initChatSections() {
  const defaults = {
    main: true,
    threads: true,
    meta: false,
    agents: true,   // auto-expand agents panel when chat tile opens
    attachments: false,
  };
  Object.entries(defaults).forEach(([key, expanded]) => {
    const section = _chatSectionElement(key);
    if (!section) return;
    section.classList.toggle('collapsed', !expanded);
    _syncChatSectionAria(key);
  });
  _applyMainRuntimePanelState();
}

function updateComposerMeta() {
  const input = document.getElementById('question-input');
  const left = document.getElementById('chat-composer-left');
  const right = document.getElementById('chat-composer-right');
  if (!left || !right || !input) return;
  const txt = String(input.value || '');
  const chars = txt.length;
  const words = (txt.trim().match(/\S+/g) || []).length;
  const enabled = getEnabledChatAgents().length;
  const attached = (window.__fridaysChatAttachments || []).length;
  const mode = String(window.__fridaysChatHistoryMode || 'full');
  const limit = Number(window.__fridaysChatHistoryLimit || 8);
  const modeLabel = mode === 'none' ? 'this message only' : (mode === 'recent' ? `last ${limit}` : 'full thread');
  const flowLabel = _chatFlowModeLabel(window.__fridaysChatFlowMode, true);
  left.textContent = `${chars} chars · ${words} words`;
  right.textContent = `${enabled} agent${enabled === 1 ? '' : 's'} on · ${flowLabel} · ${attached} file${attached === 1 ? '' : 's'} · ${modeLabel}`;
}

function _normalizeMentionKey(raw) {
  return String(raw || '').toLowerCase().trim().replace(/^@+/, '').replace(/\s+/g, '');
}

function _agentFromMentionToken(token) {
  const key = _normalizeMentionKey(token);
  if (!key) return null;
  return CHAT_AGENT_OPTIONS.find(opt => {
    const value = _normalizeMentionKey(opt.value);
    const label = _normalizeMentionKey(opt.label);
    return value === key || label === key;
  }) || null;
}

function _extractMentionedAgents(text) {
  const raw = String(text || '');
  const out = [];
  const seen = new Set();
  const re = /(^|\s)@([a-zA-Z0-9_.\- ]{1,40})/g;
  let m;
  while ((m = re.exec(raw)) !== null) {
    const token = String(m[2] || '').trim();
    const opt = _agentFromMentionToken(token);
    if (!opt) continue;
    const key = String(opt.value || '').toLowerCase();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push(key);
  }
  return out;
}

function _enableMentionedAgents(agentKeys) {
  const keys = Array.isArray(agentKeys) ? agentKeys : [];
  if (!keys.length) return;
  let changed = false;
  keys.forEach(k => {
    const key = String(k || '').toLowerCase();
    if (!key || !Object.prototype.hasOwnProperty.call(window.__fridaysChatEnabledAgents || {}, key)) return;
    if (!window.__fridaysChatEnabledAgents[key]) {
      window.__fridaysChatEnabledAgents[key] = true;
      // Mark as auto-selected (green pulse) unless already manually or relay-selected
      const cur = _getAgentSelectionState(key);
      if (!cur || cur === 'auto') _setAgentSelectionState(key, 'auto');
      changed = true;
    }
  });
  if (!changed) return;
  persistThreadAgentSelection();
  renderChatAgentToggles();
  updateComposerMeta();
}

function _mentionContextAtCursor(input) {
  if (!input) return null;
  const value = String(input.value || '');
  const end = Number(input.selectionStart || 0);
  const prefix = value.slice(0, end);
  const match = prefix.match(/(^|\s)@([a-zA-Z0-9_.\- ]*)$/);
  if (!match) return null;
  return {
    query: String(match[2] || '').trim(),
    start: end - String(match[2] || '').length - 1,
    end,
  };
}

function _closeMentionMenu() {
  const menu = document.getElementById('chat-mention-menu');
  if (menu) {
    menu.style.display = 'none';
    menu.innerHTML = '';
  }
  window.__fridaysMentionState = { open: false, start: -1, end: -1, active: 0, items: [] };
}

function _renderMentionMenu(input, ctx) {
  const menu = document.getElementById('chat-mention-menu');
  if (!menu || !input || !ctx) return;
  const query = _normalizeMentionKey(ctx.query);
  const enabled = window.__fridaysChatEnabledAgents || {};
  const items = CHAT_AGENT_OPTIONS
    .map(opt => ({
      key: String(opt.value || '').toLowerCase(),
      label: String(opt.label || opt.value || ''),
      tier: String(opt.tier || 'local'),
      icon: _chatAgentMeta(opt.value).icon || '<svg viewBox="0 0 16 16" width="12" height="12" fill="none" aria-hidden="true"><circle cx="8" cy="5.5" r="2.5" stroke="currentColor" stroke-width="1.3"/><path d="M3 13.5c0-2.5 2.2-4.5 5-4.5s5 2 5 4.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
    }))
    .filter(item => !query || _normalizeMentionKey(item.key).includes(query) || _normalizeMentionKey(item.label).includes(query))
    .slice(0, 12);

  if (!items.length) {
    _closeMentionMenu();
    return;
  }

  const prev = window.__fridaysMentionState || { active: 0 };
  const active = Math.max(0, Math.min(items.length - 1, Number(prev.active || 0)));
  window.__fridaysMentionState = { open: true, start: ctx.start, end: ctx.end, active, items };
  menu.style.display = 'block';
  menu.innerHTML = items.map((item, idx) => `
    <button class="chat-mention-item ${idx === active ? 'active' : ''}" data-mention-idx="${idx}" type="button">
      <span class="agent-icon-chip-sm">${item.icon}</span><span>${_escapeHtml(item.label)}</span>
      <span class="chat-mention-meta">${enabled[item.key] ? 'enabled' : item.tier}</span>
    </button>
  `).join('');

  menu.querySelectorAll('.chat-mention-item').forEach(btn => {
    btn.onclick = () => {
      const idx = Number(btn.dataset.mentionIdx || 0);
      _selectMentionItem(input, idx);
    };
  });
}

function _selectMentionItem(input, idxOverride = null) {
  const state = window.__fridaysMentionState || {};
  if (!state.open || !Array.isArray(state.items) || !state.items.length || !input) return false;
  const idx = idxOverride === null
    ? Math.max(0, Math.min(state.items.length - 1, Number(state.active || 0)))
    : Math.max(0, Math.min(state.items.length - 1, Number(idxOverride || 0)));
  const chosen = state.items[idx];
  if (!chosen) return false;
  const value = String(input.value || '');
  const before = value.slice(0, Math.max(0, Number(state.start || 0)));
  const after = value.slice(Math.max(0, Number(state.end || 0)));
  const insertion = '@' + chosen.key + ' ';
  input.value = before + insertion + after;
  const caret = (before + insertion).length;
  input.focus();
  input.setSelectionRange(caret, caret);
  _enableMentionedAgents([chosen.key]);
  window.__fridaysLastMentionedAgents = [chosen.key];
  _closeMentionMenu();
  updateComposerMeta();
  updateChatSpellHelper();
  return true;
}

function _handleMentionInput(input) {
  const ctx = _mentionContextAtCursor(input);
  if (!ctx) {
    _closeMentionMenu();
    return;
  }
  _renderMentionMenu(input, ctx);
}

function _handleMentionKeydown(event, input) {
  const state = window.__fridaysMentionState || {};
  if (!state.open) return false;
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault();
    const delta = event.key === 'ArrowDown' ? 1 : -1;
    const next = Math.max(0, Math.min((state.items || []).length - 1, Number(state.active || 0) + delta));
    state.active = next;
    window.__fridaysMentionState = state;
    const ctx = _mentionContextAtCursor(input);
    if (ctx) _renderMentionMenu(input, ctx);
    return true;
  }
  if (event.key === 'Enter' || event.key === 'Tab') {
    event.preventDefault();
    return _selectMentionItem(input);
  }
  if (event.key === 'Escape') {
    event.preventDefault();
    _closeMentionMenu();
    return true;
  }
  return false;
}

function handleQuestionInputKeydown(event) {
  const input = document.getElementById('question-input');
  if (!input) return;
  if (_handleMentionKeydown(event, input)) return;
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
}

function _normalizeChatHistoryMode(mode) {
  const val = String(mode || '').trim().toLowerCase();
  if (val === 'recent' || val === 'none') return val;
  return 'full';
}

function _normalizeChatHistoryLimit(limit) {
  const n = Number(limit || 8);
  if (!Number.isFinite(n)) return 8;
  return Math.max(1, Math.min(30, Math.round(n)));
}

function getChatContextConfig() {
  return {
    historyMode: _normalizeChatHistoryMode(window.__fridaysChatHistoryMode),
    historyLimit: _normalizeChatHistoryLimit(window.__fridaysChatHistoryLimit),
  };
}

function _renderChatHistoryControls() {
  const modeSel = document.getElementById('chat-history-mode');
  const limitSel = document.getElementById('chat-history-limit');
  const wrap = document.getElementById('chat-history-limit-wrap');
  if (!modeSel || !limitSel || !wrap) return;
  const cfg = getChatContextConfig();
  modeSel.value = cfg.historyMode;
  limitSel.value = String(cfg.historyLimit);
  wrap.classList.toggle('visible', cfg.historyMode === 'recent');
}

function onChatHistoryModeChange() {
  const modeSelectors = document.querySelectorAll('.chat-history-mode');
  const val = modeSelectors.length > 0 ? modeSelectors[0].value : 'full';
  window.__fridaysChatHistoryMode = _normalizeChatHistoryMode(val);
  localStorage.setItem(CHAT_HISTORY_MODE_KEY, window.__fridaysChatHistoryMode);
  // Sync all selectors
  modeSelectors.forEach(sel => {
    sel.value = window.__fridaysChatHistoryMode;
  });
  _renderChatHistoryControls();
  updateComposerMeta();
}

function onChatHistoryLimitChange() {
  const limitSelectors = document.querySelectorAll('.chat-history-limit');
  const val = limitSelectors.length > 0 ? limitSelectors[0].value : '4';
  window.__fridaysChatHistoryLimit = _normalizeChatHistoryLimit(val);
  localStorage.setItem(CHAT_HISTORY_LIMIT_KEY, String(window.__fridaysChatHistoryLimit));
  // Sync all selectors
  limitSelectors.forEach(sel => {
    sel.value = String(window.__fridaysChatHistoryLimit);
  });
  _renderChatHistoryControls();
  updateComposerMeta();
}

function initChatHistoryControls() {
  window.__fridaysChatHistoryMode = _normalizeChatHistoryMode(window.__fridaysChatHistoryMode);
  window.__fridaysChatHistoryLimit = _normalizeChatHistoryLimit(window.__fridaysChatHistoryLimit);
  _renderChatHistoryControls();
}

function _chatMessagesEl() {
  return document.getElementById('chat-messages');
}

function _escapeHtml(v) {
  return String(v ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function _renderMarkdown(text) {
  if (typeof marked === 'undefined') return _escapeHtml(text);
  try {
    return marked.parse(String(text || ''), { gfm: true, breaks: false });
  } catch (_) {
    return _escapeHtml(text);
  }
}

function _parseSkillEvents(rawText) {
  const text = String(rawText || '');
  const marker = '\n---\nExecuted skill output:\n';
  let displayText = text;
  let parseSource = '';

  if (text.includes(marker)) {
    const idx = text.indexOf(marker);
    displayText = text.slice(0, idx).trim();
    parseSource = text.slice(idx + marker.length);
  } else if (text.trim().startsWith('[skill:')) {
    displayText = '';
    parseSource = text;
  }

  if (!parseSource.trim()) {
    return { text: displayText, events: [] };
  }

  const events = [];
  const lines = parseSource.split(/\r?\n/);
  let current = null;
  const flush = () => {
    if (!current) return;
    current.output = current.output.join('\n').trim();
    events.push(current);
    current = null;
  };

  for (const line of lines) {
    const m = line.match(/^\[skill:([a-z0-9_\-]+)\]\s+(OK|FAILED)\s*$/i);
    if (m) {
      flush();
      current = { name: m[1], ok: m[2].toUpperCase() === 'OK', output: [] };
      continue;
    }
    if (current) current.output.push(line);
  }
  flush();

  return { text: displayText, events };
}

async function requestSkillApproval(agent, skillName, outputText) {
  const owner = String(agent || 'agent').toLowerCase();
  const summary = String(outputText || '').slice(0, 500);
  const title = `Permission request: ${skillName}`;
  const description = [
    `Agent: ${owner}`,
    `Conversation: ${window.__fridaysChatConversationId || 'new-thread'}`,
    `Request: enable/approve action for skill ${skillName}.`,
    '',
    'Failure evidence:',
    summary || '(no output)',
  ].join('\n');

  try {
    const resp = await fetch('/api/queue', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        agent: owner,
        title,
        description,
        priority: 4,
        ..._authPayload(),
      })
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok || !data.ok) {
      throw new Error((data && (data.error || data.response)) || `HTTP ${resp.status}`);
    }
    showToast(`Approval request created (${data.proposal_id || data.queue_id})`, 'success');
  } catch (e) {
    showToast('Could not create approval request: ' + (e.message || e), 'error');
  }
}

function _renderSkillEvents(events, sender) {
  if (!Array.isArray(events) || !events.length) return '';
  const cards = events.map((ev) => {
    const status = ev.ok ? 'OK' : 'FAILED';
    const cls = ev.ok ? 'ok' : 'failed';
    const out = _escapeHtml(String(ev.output || '').slice(0, 2600));
    const actionHtml = ev.ok ? '' : `
      <div class="skill-event-actions">
        <button class="skill-event-btn" onclick="requestSkillApproval('${_escapeHtml(String(sender || 'agent').toLowerCase())}','${_escapeHtml(ev.name)}','')">✓ Request approval</button>
      </div>
    `;
    return `
      <div class="skill-event-card ${cls}">
        <div class="skill-event-head">
          <span class="skill-event-name">skill: ${_escapeHtml(ev.name)}</span>
          <span class="skill-event-status">${status}</span>
        </div>
        <div class="skill-event-body">${out || '(no output)'}</div>
        ${actionHtml}
      </div>
    `;
  }).join('');
  return `<div class="skill-events">${cards}</div>`;
}

const _CHAT_AGENT_META = {
  // Internal key → icon, purpose, runtime. Label comes from CHAT_AGENT_OPTIONS (DB-driven).
  gemma:     { icon: '<svg viewBox="0 0 16 16" width="12" height="12" fill="none" aria-hidden="true"><circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="1.3"/><path d="M8 5v3l2 2" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>', purpose: '1 · Gemma3. Director — routes, synthesises, speaks last.',                   runtime: 'local', tier: 'local' },
  llama:     { icon: '<svg viewBox="0 0 16 16" width="12" height="12" fill="none" aria-hidden="true"><path d="M5 13V9c0-2.5 6-2.5 6 0v4M5 13h6M8 6.5c0-1.1-.9-2-2-2s-2 .9-2 2" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>', purpose: '2 · LlaMA. Correspondent — web search, fast first response.',                runtime: 'local', tier: 'local' },
  mistral:   { icon: '<svg viewBox="0 0 16 16" width="12" height="12" fill="none" aria-hidden="true"><path d="M8 2.5l5.5 9.5H2.5z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>', purpose: '3 · Mistral. Analyst — deep reasoning, debates, challenges Two.',            runtime: 'local', tier: 'local' },
  librarian: { icon: '<svg viewBox="0 0 16 16" width="12" height="12" fill="none" aria-hidden="true"><path d="M4.5 3.5v9M4.5 3.5h5a2 2 0 010 4h-5M4.5 7.5h5.5a2 2 0 010 4H4.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>', purpose: '5 · Vortex. Gatekeeper + time machine checkpoints.',                         runtime: 'local', tier: 'local' },
  duck:      { icon: '<svg viewBox="0 0 16 16" width="12" height="12" fill="none" aria-hidden="true"><path d="M4 9.5c0 2 1.8 3 4 3s4-1 4-3c0-1.5-1-2.5-3-2.5H8c1 0 2-1 2-2S9 3 8 3C6.5 3 5.5 4 5.5 5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/><path d="M12 7.5l2 1" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>', purpose: '6 · Duck. Sanity checker — YES/NO after every ticket.',                      runtime: 'local', tier: 'local' },
  sniffles:  { icon: '<svg viewBox="0 0 16 16" width="12" height="12" fill="none" aria-hidden="true"><path d="M6 2h4M5.5 2v4.5L3 11.5a1 1 0 00.9 1.5h8.2a1 1 0 00.9-1.5L10.5 6.5V2" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>', purpose: '7 · Sniffles. Inspector — memory auditor, read only.',                       runtime: 'local', tier: 'local' },
  eight:     { icon: '<svg viewBox="0 0 16 16" width="12" height="12" fill="none" aria-hidden="true"><path d="M8 2C6.3 2 5 3.1 5 4.5S6.3 7 8 7s3 1.1 3 2.5S9.7 12 8 12s-3-1-3-2.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/><path d="M8 2v2M8 12v2" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>', purpose: '8 · Eight. SAP specialist — Functional/Technical/Devil three-voice debate.', runtime: 'local', tier: 'local' },
  nine:      { icon: '<svg viewBox="0 0 16 16" width="12" height="12" fill="none" aria-hidden="true"><path d="M8 2l1.5 4h4L10 8.5l1.5 4L8 10l-3.5 2.5 1.5-4-3.5-2.5h4z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>', purpose: '9 · Groq. LlaMA 3.3 70B via Groq — fast, high-capacity reasoning.',        runtime: 'paid',  tier: 'paid' },
  ten:       { icon: '<svg viewBox="0 0 16 16" width="12" height="12" fill="none" aria-hidden="true"><path d="M4 8h8M10 5l3 3-3 3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 5l-3 3 3 3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>', purpose: '10 · Github. Engineering advisor — code quality, implementation clarity.',   runtime: 'paid',  tier: 'paid' },
  eleven:    { icon: '<svg viewBox="0 0 16 16" width="12" height="12" fill="none" aria-hidden="true"><path d="M9 2L5 9h4l-2 5 6-8H9z" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>', purpose: '11 · Grok. Lateral thinking advisor — creative synthesis, alternatives.',     runtime: 'paid',  tier: 'paid' },
  twelve:    { icon: '<svg viewBox="0 0 16 16" width="12" height="12" fill="none" aria-hidden="true"><path d="M8 3C5.5 3 4 5 4 7c0 1.5 1 2.5 2 3l-.5 3h5L10 10c1-.5 2-1.5 2-3 0-2-1.5-4-4-4z" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/><path d="M6.5 10.5h3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>', purpose: '12 · Claude. System architect — Ghost Layer, Ghost Briefs, proposals.',       runtime: 'paid',  tier: 'paid' },
  thirteen:  { icon: '<svg viewBox="0 0 16 16" width="12" height="12" fill="none" aria-hidden="true"><path d="M3 5h10M3 8h10M3 11h6" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/><circle cx="12" cy="11" r="2" stroke="currentColor" stroke-width="1.3"/></svg>', purpose: '13 · HF. Hugging Face inference — open-source models, free tier.',              runtime: 'free',  tier: 'free' },
  you:       { icon: '<svg viewBox="0 0 16 16" width="12" height="12" fill="none" aria-hidden="true"><circle cx="8" cy="5.5" r="2.5" stroke="currentColor" stroke-width="1.3"/><path d="M3 13.5c0-2.5 2.2-4.5 5-4.5s5 2 5 4.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>', purpose: 'Human operator input.',                                                       runtime: 'human', tier: 'human' },
};

function _chatAgentLabel(sender) {
  const normalized = String(sender || '').trim().toLowerCase().replace(/\[.*?\]/g, '').trim();
  if (!normalized) return 'Agent';
  if (normalized === 'you' || normalized === 'user') return 'You';
  const option = CHAT_AGENT_OPTIONS.find(a => a.value === normalized);
  if (option && option.label) return option.label;
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

function _chatAgentIdentity(sender) {
  const normalized = String(sender || '').trim().toLowerCase().replace(/\[.*?\]/g, '').trim();
  const meta = _chatAgentMeta(normalized);
  return {
    key: normalized,
    label: _chatAgentLabel(normalized),
    icon: meta.icon || '<svg viewBox="0 0 16 16" width="12" height="12" fill="none" aria-hidden="true"><circle cx="8" cy="5.5" r="2.5" stroke="currentColor" stroke-width="1.3"/><path d="M3 13.5c0-2.5 2.2-4.5 5-4.5s5 2 5 4.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
    meta,
  };
}

function _chatAgentIdentityHtml(sender, includeTitle = true) {
  const identity = _chatAgentIdentity(sender);
  const titleText = includeTitle
    ? `${identity.label} · ${identity.meta.runtime} · ${identity.meta.purpose}`
    : `${identity.label}`;
  return `<span class="agent-icon-chip" title="${_escapeHtml(titleText)}">${identity.icon}</span><span class="agent-name-chip">${_escapeHtml(identity.label)}</span>`;
}

function _chatAgentListText(agentKeys) {
  return (agentKeys || [])
    .map(key => {
      const identity = _chatAgentIdentity(key);
      return identity.label;
    })
    .join(', ');
}

function _chatTargetsPrefixFromRaw(rawTargets) {
  const agents = _chatTargetAgentsFromRaw(rawTargets);
  if (!agents.length) return '';
  return '[' + _chatAgentListText(agents) + '] ';
}

function _chatTargetAgentsFromRaw(rawTargets) {
  const raw = String(rawTargets || '').trim();
  if (!raw) return [];
  const agents = raw
    .split(',')
    .map(a => String(a || '').trim().toLowerCase())
    .filter(Boolean)
    .filter(a => _isKnownChatAgent(a));
  return agents;
}

function _chatAgentMeta(sender) {
  const raw = String(sender || '').trim().toLowerCase();
  const normalized = raw.replace(/\[.*?\]/g, '').trim();
  return _CHAT_AGENT_META[normalized] || { icon: '<svg viewBox="0 0 16 16" width="12" height="12" fill="none" aria-hidden="true"><circle cx="8" cy="5.5" r="2.5" stroke="currentColor" stroke-width="1.3"/><path d="M3 13.5c0-2.5 2.2-4.5 5-4.5s5 2 5 4.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>', purpose: `Agent: ${normalized || 'unknown'}.`, runtime: 'unknown' };
}

function _chatRelayConfig() {
  const max = Math.max(1, Math.min(12, Number(window.__fridaysChatRelayMaxPerTurn || 2)));
  return {
    auto: !!window.__fridaysChatRelayAuto,
    infinite: !!window.__fridaysChatRelayInfinite,
    maxPerTurn: window.__fridaysChatRelayInfinite ? Number.POSITIVE_INFINITY : max,
    forceFullContext: !!window.__fridaysChatRelayForceFull,
  };
}

const CHAT_RELAY_RESOURCE_LIMITS = {
  queueCap: 20,
  monitorTtlMs: 4500,
  maxRunningJobs: 1,
  softCpuPercent: 82,
  softRamPercent: 96,   // raised from 86 — NVMe-swap system keeps RAM at 87-95% normally
  retryMsNormal: 1300,
  retryMsHot: 2600,
};

function _relayQueueCap() {
  return Math.max(6, Number(CHAT_RELAY_RESOURCE_LIMITS.queueCap || 20));
}

function _relayRunningJobsCount() {
  const jobs = Array.isArray(window.__fridaysThreadRuntimeSnapshot?.jobs)
    ? window.__fridaysThreadRuntimeSnapshot.jobs
    : [];
  const running = jobs.filter(j => String(j?.status || 'running') === 'running').length;
  const pending = Array.isArray(window.__fridaysChatPendingJobIds) ? window.__fridaysChatPendingJobIds.length : 0;
  return Math.max(running, pending);
}

function _relayClearRetryTimer() {
  if (window.__fridaysChatRelayRetryTimer) {
    clearTimeout(window.__fridaysChatRelayRetryTimer);
    window.__fridaysChatRelayRetryTimer = null;
  }
}

function _relayScheduleRetry(delayMs = CHAT_RELAY_RESOURCE_LIMITS.retryMsNormal) {
  if (window.__fridaysChatRelayRetryTimer) return;
  const delay = Math.max(350, Number(delayMs || CHAT_RELAY_RESOURCE_LIMITS.retryMsNormal));
  window.__fridaysChatRelayRetryTimer = setTimeout(() => {
    window.__fridaysChatRelayRetryTimer = null;
    _processRelayQueue();
  }, delay);
}

function _relayMonitorFresh(ttlMs = CHAT_RELAY_RESOURCE_LIMITS.monitorTtlMs) {
  const snap = window.__fridaysChatRelayResource || {};
  const ts = Number(snap.sampledAt || 0);
  return ts > 0 && (Date.now() - ts) <= Math.max(1000, Number(ttlMs || CHAT_RELAY_RESOURCE_LIMITS.monitorTtlMs));
}

function _refreshRelayResourceSnapshot(force = false) {
  if (!force && _relayMonitorFresh()) {
    return Promise.resolve(window.__fridaysChatRelayResource || {});
  }
  if (window.__fridaysChatRelayResourceFetchPromise) {
    return window.__fridaysChatRelayResourceFetchPromise;
  }
  window.__fridaysChatRelayResourceFetchPromise = fetch('/api/monitor')
    .then(r => r.json())
    .then(data => {
      const parseStat = (val) => {
        if (val == null) return null;
        const n = Number(val);
        if (Number.isFinite(n)) return n;
        const m = String(val).match(/\d+\.?\d*/);
        return m ? Number(m[0]) : null;
      };
      const cpu = data && data.cpu_percent != null ? Number(data.cpu_percent) : parseStat(data && data.system_load);
      const ram = data && data.ram_percent != null ? Number(data.ram_percent) : parseStat(data && data.memory_usage);
      if (Number.isFinite(cpu) || Number.isFinite(ram)) {
        updateChatMiniSystemStats(cpu, ram);
      }
      window.__fridaysChatRelayResource = {
        cpuPercent: Number.isFinite(cpu) ? cpu : null,
        ramPercent: Number.isFinite(ram) ? ram : null,
        sampledAt: Date.now(),
        source: 'monitor',
      };
      return window.__fridaysChatRelayResource;
    })
    .catch(() => window.__fridaysChatRelayResource || {})
    .finally(() => {
      window.__fridaysChatRelayResourceFetchPromise = null;
    });
  return window.__fridaysChatRelayResourceFetchPromise;
}

/* ── Librarian relay monitor ────────────────────────────────────────────────
   Librarian runs AFTER the regex relay to catch implicit handoffs the pattern
   matcher missed. Fires async/debounced so it never blocks bubble rendering.
   Relies on /api/chat/librarian/review (backend qwen:latest at temp 0.05).
   Results are fed back into the normal relay queue machinery.
   ────────────────────────────────────────────────────────────────────────── */

async function _librarianReviewResponse(text, fromAgent, convId) {
  if (!text || !window.__fridaysChatRelayAuto) return;
  const cleanText = String(text || '').trim();
  if (cleanText.length < 20) return;

  try {
    const resp = await fetch('/api/chat/librarian/review', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: cleanText.slice(0, 2000),
        from_agent: String(fromAgent || 'agent').toLowerCase(),
        conversation_id: convId || null,
      }),
      signal: AbortSignal.timeout ? AbortSignal.timeout(22000) : undefined,
    });
    if (!resp.ok) return;
    const data = await resp.json().catch(() => ({}));
    const candidates = Array.isArray(data.candidates) ? data.candidates : [];
    if (!candidates.length) return;

    // De-duplicate against whatever is already in the relay queue
    const queuedTargets = new Set(
      (window.__fridaysChatRelayQueue || []).map(x => String(x.target || '').toLowerCase())
    );
    // Also dedup against recently-fired seen signatures (by target, ignoring from — prevents
    // 'agent' fallback from bypassing dedup when data-sender wasn't available).
    const recentlySeen = window.__fridaysChatRelaySeen || {};
    const _now = Date.now();
    const recentTargets = new Set(
      Object.entries(recentlySeen)
        .filter(([, ts]) => _now - Number(ts || 0) < 8 * 60 * 1000)
        .map(([sig]) => sig.split('|')[1] || '')
    );
    let newCount = 0;
    for (const c of candidates) {
      const target = String(c.target || '').toLowerCase().trim();
      const question = String(c.question || '').trim();
      if (!target || !question) continue;
      if (!_isAutoRelayTargetEnabled(target)) continue;
      if (queuedTargets.has(target)) continue;      // already queued by regex relay
      if (recentTargets.has(target)) continue;      // already fired recently (any from)
      if (target === String(fromAgent || '').toLowerCase()) continue; // don't re-route to sender
      queueRelayHandoff({ from: fromAgent, target, question }, true);
      queuedTargets.add(target);
      newCount++;
    }
    if (newCount > 0) {
      _appendInfoLogEntry('librarian',
        `Implicit relay detected \u2192 ${candidates.map(c => c.target).join(', ')} (${newCount} queued)`);
    } else {
      _appendInfoLogEntry('librarian', 'Relay review: no new implicit handoffs found.');
    }
  } catch (err) {
    // Non-critical — don't surface to user
    console.debug('[Librarian] relay review error:', err);
  }
}

// Debounce state for _librarianReviewResponse
window.__librarianReviewTimer = null;

function _librarianReviewDebounced(text, fromAgent, convId, delayMs = 350) {
  // Mark the current last bubble as pending review so the watchdog won't re-trigger it.
  const _lrBubbles = document.querySelectorAll('.chat-bubble:not(.user)');
  if (_lrBubbles.length) {
    const _lrLast = _lrBubbles[_lrBubbles.length - 1];
    if (_lrLast.id) window.__librarianLastReviewedBubbleId = _lrLast.id;
  }
  if (window.__librarianReviewTimer) clearTimeout(window.__librarianReviewTimer);
  window.__librarianReviewTimer = setTimeout(() => {
    window.__librarianReviewTimer = null;
    _librarianReviewResponse(text, fromAgent, convId);
  }, delayMs);
}

// Watchdog — runs every 10 s while chat is active.
// If the relay queue is empty and the last non-user message hasn't been
// Librarian-reviewed yet, trigger a review of that last message.
window.__librarianWatchdogTimer = null;
window.__librarianLastReviewedBubbleId = null;

function _librarianQueueWatchdog() {
  if (!window.__fridaysChatRelayAuto) return;
  const queue = Array.isArray(window.__fridaysChatRelayQueue) ? window.__fridaysChatRelayQueue : [];
  if (queue.length > 0) return;  // queue busy — regex relay is handling things

  // Find last agent bubble (user bubbles have class 'user', not 'user-bubble')
  const bubbles = document.querySelectorAll('.chat-bubble:not(.user)');
  if (!bubbles.length) return;
  const last = bubbles[bubbles.length - 1];
  const bubbleId = last.id || null;
  if (!bubbleId || bubbleId === window.__librarianLastReviewedBubbleId) return;
  window.__librarianLastReviewedBubbleId = bubbleId;

  const textEl = last.querySelector('.chat-text');
  const text = textEl ? (textEl.innerText || textEl.textContent || '') : '';
  // Skip error bubbles (0 tokens) — they must not trigger relays.
  if (Number(last.dataset.tokens || 0) === 0) {
    _appendInfoLogEntry('librarian', 'Watchdog: skipping error/zero-token bubble.');
    return;
  }
  // Skip relay chain responses — librarian only reviews initial direct responses.
  if (Number(last.dataset.chainDepth ?? -1) >= 0) {
    _appendInfoLogEntry('librarian', 'Watchdog: skipping relay chain response.');
    return;
  }
  const fromAgent = String(last.dataset.sender || last.dataset.agent || 'agent').toLowerCase();
  const convId = last.dataset.conversationId || window.__fridaysActiveChatConvId || null;

  _appendInfoLogEntry('librarian', 'Watchdog: checking last response for implicit relay…');
  _librarianReviewResponse(text, fromAgent, convId);
}

function _librarianStartWatchdog() {
  if (window.__librarianWatchdogTimer) clearInterval(window.__librarianWatchdogTimer);
  window.__librarianWatchdogTimer = setInterval(_librarianQueueWatchdog, 10000);
}

async function _relayDispatchGate(item) {
  const relayItem = item || {};
  const queue = Array.isArray(window.__fridaysChatRelayQueue) ? window.__fridaysChatRelayQueue : [];
  const budget = Number(window.__fridaysChatRelayBudget || 0);
  const _chainDepth = Number(relayItem.chainDepth ?? -1);
  const _hasChainBudget = _chainDepth >= 0;
  // Chain-budget relays bypass the global turn budget but have their own per-chain depth limit.
  if (relayItem.auto && !_hasChainBudget && budget === 0) {
    return {
      allow: false,
      reason: 'turn budget exhausted',
      retryMs: CHAT_RELAY_RESOURCE_LIMITS.retryMsNormal,
      deferToBack: true,
    };
  }
  if (relayItem.auto && _hasChainBudget && _chainDepth === 0) {
    return {
      allow: false,
      reason: 'chain budget exhausted',
      retryMs: CHAT_RELAY_RESOURCE_LIMITS.retryMsNormal,
      deferToBack: false,
    };
  }

  const runningJobs = Math.max(_relayRunningJobsCount(), Number(window.__fridaysChatRelayInFlight || 0));
  if (runningJobs >= Number(CHAT_RELAY_RESOURCE_LIMITS.maxRunningJobs || 3)) {
    return {
      allow: false,
      reason: `runtime busy (${runningJobs} jobs active)`,
      retryMs: CHAT_RELAY_RESOURCE_LIMITS.retryMsHot,
      deferToBack: false,
    };
  }

  await _refreshRelayResourceSnapshot(false);
  const sample = window.__fridaysChatRelayResource || {};
  const cpu = Number(sample.cpuPercent);
  const ram = Number(sample.ramPercent);
  const cpuHot = Number.isFinite(cpu) && cpu >= Number(CHAT_RELAY_RESOURCE_LIMITS.softCpuPercent || 82);
  const ramHot = Number.isFinite(ram) && ram >= Number(CHAT_RELAY_RESOURCE_LIMITS.softRamPercent || 86);
  if (cpuHot || ramHot) {
    const reason = cpuHot && ramHot
      ? `resource hold (cpu ${Math.round(cpu)}%, ram ${Math.round(ram)}%)`
      : (cpuHot ? `resource hold (cpu ${Math.round(cpu)}%)` : `resource hold (ram ${Math.round(ram)}%)`);
    return {
      allow: false,
      reason,
      retryMs: CHAT_RELAY_RESOURCE_LIMITS.retryMsHot,
      deferToBack: false,
    };
  }

  if (queue.length > _relayQueueCap()) {
    return {
      allow: false,
      reason: `queue pressure (${queue.length}/${_relayQueueCap()})`,
      retryMs: CHAT_RELAY_RESOURCE_LIMITS.retryMsNormal,
      deferToBack: false,
    };
  }

  return { allow: true };
}

function _renderChatRelayControls() {
  const autoEl = document.getElementById('chat-relay-auto');
  const maxEl = document.getElementById('chat-relay-turns-slider');
  const maxValueEl = document.getElementById('chat-relay-turns-value');
  const infEl = document.getElementById('chat-relay-infinite');
  const forceFullEl = document.getElementById('chat-relay-force-full');
  const statusEl = document.getElementById('chat-relay-status');
  if (autoEl) autoEl.checked = !!window.__fridaysChatRelayAuto;
  const sliderVal = String(Math.max(1, Math.min(12, Number(window.__fridaysChatRelayMaxPerTurn || 2))));
  if (maxEl) maxEl.value = sliderVal;
  if (infEl) infEl.checked = !!window.__fridaysChatRelayInfinite;
  if (forceFullEl) forceFullEl.checked = !!window.__fridaysChatRelayForceFull;
  if (maxValueEl) maxValueEl.textContent = window.__fridaysChatRelayInfinite ? 'inf' : sliderVal;
  if (statusEl) {
    const queued = Array.isArray(window.__fridaysChatRelayQueue) ? window.__fridaysChatRelayQueue.length : 0;
    const rawBudget = Number(window.__fridaysChatRelayBudget || 0);
    const budget = rawBudget < 0 ? 'inf' : String(Math.max(0, rawBudget));
    const hold = String(window.__fridaysChatRelayHoldReason || '').trim();
    const flowLabel = _chatFlowModeLabel(window.__fridaysChatFlowMode, true);
    statusEl.textContent = queued
      ? `Relay queue: ${queued} · ${flowLabel} · budget ${budget}${hold ? ` · hold ${hold}` : ''}`
      : `Relay ${window.__fridaysChatRelayAuto ? 'auto-on' : 'manual-only'} · ${flowLabel} · budget ${budget}${hold ? ` · ${hold}` : ''}`;
  }
}

function onChatRelayAutoToggle() {
  const autoEls = document.querySelectorAll('.chat-relay-auto');
  const val = autoEls.length > 0 ? autoEls[0].checked : false;
  window.__fridaysChatRelayAuto = !!val;
  localStorage.setItem(CHAT_RELAY_AUTO_KEY, window.__fridaysChatRelayAuto ? '1' : '0');
  // Sync all windows
  autoEls.forEach(el => {
    el.checked = val;
  });
  _renderChatRelayControls();
}

function _chatAgentOption(agentKey) {
  const key = String(agentKey || '').toLowerCase().trim();
  return CHAT_AGENT_OPTIONS.find(opt => opt.value === key) || null;
}

function _chatAgentTier(agentKey) {
  const option = _chatAgentOption(agentKey);
  if (!option) return 'unknown';
  return option.tier === 'local' ? 'local' : 'online';
}

function _chatFlowModeLabel(mode, compact = false) {
  const key = String(mode || 'both_seq').toLowerCase();
  if (key === 'local_only') return compact ? 'local only' : 'Local Only';
  if (key === 'online_only') return compact ? 'online only' : 'Online Only';
  return compact ? 'both seq' : 'Both Seq';
}

function _chatFlowModeTitle(mode) {
  const key = String(mode || 'both_seq').toLowerCase();
  if (key === 'local_only') {
    return 'Local Only: keep the chat on local agents and ignore online handoffs. Click to switch to online only.';
  }
  if (key === 'online_only') {
    return 'Online Only: keep the chat on online agents and ignore local handoffs. Click to switch to both sequential.';
  }
  return 'Both Seq: selected local and online agents can participate, but relay runs one speaker at a time. Click to switch to local only.';
}

function _chatFlowModeAllowsAgent(agentKey, mode = window.__fridaysChatFlowMode) {
  const tier = _chatAgentTier(agentKey);
  const flow = String(mode || 'both_seq').toLowerCase();
  if (flow === 'local_only') return tier === 'local';
  if (flow === 'online_only') return tier === 'online';
  return tier === 'local' || tier === 'online';
}

function _chatFlowModeNext(mode = window.__fridaysChatFlowMode) {
  const current = String(mode || 'both_seq').toLowerCase();
  if (current === 'both_seq') return 'local_only';
  if (current === 'local_only') return 'online_only';
  return 'both_seq';
}

function onChatParallelModeToggle() {
  window.__fridaysChatFlowMode = _chatFlowModeNext(window.__fridaysChatFlowMode);
  localStorage.setItem(CHAT_FLOW_MODE_KEY, window.__fridaysChatFlowMode);
  _updateParallelModeBtn();
  _renderChatRelayControls();
  updateComposerMeta();
}

function _updateParallelModeBtn() {
  const btn = document.getElementById('chat-parallel-mode-btn');
  if (!btn) return;
  const mode = String(window.__fridaysChatFlowMode || 'both_seq').toLowerCase();
  btn.textContent = _chatFlowModeLabel(mode);
  btn.title = _chatFlowModeTitle(mode);
  if (mode === 'local_only') {
    btn.style.background = 'color-mix(in oklab, #2563eb 18%, var(--card))';
    btn.style.color = 'var(--text)';
    btn.style.borderColor = '#3b82f6';
  } else if (mode === 'online_only') {
    btn.style.background = 'color-mix(in oklab, #f97316 18%, var(--card))';
    btn.style.color = 'var(--text)';
    btn.style.borderColor = '#f97316';
  } else {
    btn.style.background = 'color-mix(in oklab, var(--accent) 14%, var(--card))';
    btn.style.color = 'var(--text)';
    btn.style.borderColor = 'var(--accent)';
  }
}

// ── Execution mode: sequential (one at a time, relay queue) vs parallel (all at once) ──
function onChatExecModeToggle() {
  const current = String(window.__fridaysChatExecMode || 'sequential');
  const next = current === 'sequential' ? 'parallel' : 'sequential';
  window.__fridaysChatExecMode = next;
  localStorage.setItem(CHAT_EXEC_MODE_KEY, next);
  _updateExecModeBtn();
  _renderChatRelayControls();
  updateComposerMeta();
}

function _updateExecModeBtn() {
  const btn = document.getElementById('chat-exec-mode-btn');
  if (!btn) return;
  const mode = String(window.__fridaysChatExecMode || 'sequential');
  if (mode === 'parallel') {
    btn.innerHTML = '<svg viewBox="0 0 16 16" width="12" height="12" fill="none" style="vertical-align:-2px;margin-right:3px;"><path d="M9 2L5 9h4l-2 5 6-8H9z" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>Parallel';
    btn.title = 'Parallel: all selected agents answer at once (talking queue OFF). Click to switch to sequential.';
    btn.style.background = 'color-mix(in oklab, #f59e0b 18%, var(--card))';
    btn.style.color = 'var(--text)';
    btn.style.borderColor = '#f59e0b';
  } else {
    btn.innerHTML = '<svg viewBox="0 0 16 16" width="12" height="12" fill="none" style="vertical-align:-2px;margin-right:3px;"><path d="M4 8h8" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/><circle cx="4" cy="8" r="1.5" stroke="currentColor" stroke-width="1.3"/><circle cx="12" cy="8" r="1.5" stroke="currentColor" stroke-width="1.3"/></svg>Sequential';
    btn.title = 'Sequential: one agent speaks at a time via relay queue. Click to switch to parallel.';
    btn.style.background = 'color-mix(in oklab, var(--accent) 14%, var(--card))';
    btn.style.color = 'var(--text)';
    btn.style.borderColor = 'var(--accent)';
  }
}

function _isSequentialExecMode() {
  return String(window.__fridaysChatExecMode || 'sequential') === 'sequential';
}

function onChatRelayMaxChange() {
  onChatRelayTurnsSliderChange();
}

function onChatRelayTurnsSliderChange() {
  const sliders = document.querySelectorAll('.chat-relay-turns-slider');
  const maxEl = sliders.length > 0 ? sliders[0] : null;
  const next = Math.max(1, Math.min(12, Number(maxEl && maxEl.value || 2)));
  window.__fridaysChatRelayMaxPerTurn = next;
  if (!window.__fridaysChatRelayInfinite) {
    localStorage.setItem(CHAT_RELAY_MAX_KEY, String(next));
  }
  // Sync all sliders and values
  sliders.forEach(slider => {
    slider.value = next;
  });
  document.querySelectorAll('.chat-relay-turns-value').forEach(val => {
    val.textContent = next;
  });
  _renderChatRelayControls();
}

function onChatRelayInfiniteToggle() {
  const infEls = document.querySelectorAll('.chat-relay-infinite');
  const val = infEls.length > 0 ? infEls[0].checked : false;
  window.__fridaysChatRelayInfinite = !!val;
  if (window.__fridaysChatRelayInfinite) {
    localStorage.setItem(CHAT_RELAY_MAX_KEY, 'inf');
  } else {
    localStorage.setItem(CHAT_RELAY_MAX_KEY, String(Math.max(1, Math.min(12, Number(window.__fridaysChatRelayMaxPerTurn || 2)))));
  }
  // Sync all checkboxes
  infEls.forEach(el => {
    el.checked = val;
  });
  _renderChatRelayControls();
}

function onChatRelayForceFullContextToggle() {
  const chks = document.querySelectorAll('.chat-relay-force-full');
  const val = chks.length > 0 ? chks[0].checked : false;
  window.__fridaysChatRelayForceFull = !!val;
  localStorage.setItem(CHAT_RELAY_FORCE_FULL_KEY, window.__fridaysChatRelayForceFull ? '1' : '0');
  // Sync all checkboxes
  chks.forEach(el => {
    el.checked = val;
  });
  _renderChatRelayControls();
}

function _isKnownChatAgent(agentKey) {
  const key = String(agentKey || '').toLowerCase().trim();
  return CHAT_AGENT_OPTIONS.some(a => a.value === key);
}

function _isAutoRelayTargetEnabled(agentKey) {
  const key = String(agentKey || '').toLowerCase().trim();
  if (!key) return false;
  if (!_chatFlowModeAllowsAgent(key)) return false;
  const allowed = Array.isArray(window.__fridaysChatRelayAllowedAgents) ? window.__fridaysChatRelayAllowedAgents : [];
  if (allowed.length > 0) return allowed.includes(key);
  return !!(window.__fridaysChatEnabledAgents && window.__fridaysChatEnabledAgents[key]);
}

function _relayEncode(value) {
  try {
    return btoa(unescape(encodeURIComponent(String(value || ''))));
  } catch (_) {
    return '';
  }
}

function _relayDecode(value) {
  try {
    return decodeURIComponent(escape(atob(String(value || ''))));
  } catch (_) {
    return '';
  }
}

function _relayRules() {
  window.__fridaysChatRelayRules = Array.isArray(window.__fridaysChatRelayRules) ? window.__fridaysChatRelayRules : [];
  return window.__fridaysChatRelayRules;
}

function _saveRelayRules() {
  localStorage.setItem(CHAT_RELAY_RULES_KEY, JSON.stringify(_relayRules()));
}

function _applyManualRelayRules(text, fromKey, seen, out) {
  const raw = String(text || '');
  const lower = raw.toLowerCase();
  _relayRules().forEach((rule) => {
    const pattern = String(rule?.pattern || '').trim();
    const target = String(rule?.target || '').toLowerCase().trim();
    const template = String(rule?.template || '').trim();
    if (!pattern || !target || !_isKnownChatAgent(target) || target === fromKey) return;
    const idx = lower.indexOf(pattern.toLowerCase());
    if (idx === -1) return;
    const matched = raw.slice(idx, idx + pattern.length).trim() || pattern;
    const question = _normalizeRelayQuestion(template ? template.replace(/\{match\}/gi, matched) : matched);
    if (!question) return;
    const sig = `${target}|${question.toLowerCase()}`;
    if (seen.has(sig)) return;
    seen.add(sig);
    out.push({ from: fromKey || 'agent', target, question, source: 'manual-rule' });
  });
}

function _relayQuestionKey(question) {
  return String(question || '')
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 180);
}

// ── Paid-agent session continuation ────────────────────────────────────────
function _detectUnfinishedAgentAction(text) {
  if (!text) return { unfinished: false, tasks: [], prompt: '' };
  const trimmed = text.trim();
  // If response contains code blocks or strong completion signals → done
  const doneSignals = [
    /```[\s\S]{20,}/,
    /\bHere (?:is|are) (?:the )?(?:fix|result|code|change|patch|update)/i,
    /\bI(?:'ve| have) (?:made|fixed|updated|changed|added|removed|patched|corrected)\b/i,
    /\b(?:The )?(?:fix|patch|change|correction)(?:es)? (?:is|are) applied\b/i,
    /\bDone[.!]?\s*$/m,
  ];
  for (const sig of doneSignals) {
    if (sig.test(trimmed)) return { unfinished: false, tasks: [], prompt: '' };
  }
  // Action patterns indicating the agent is starting work but hasn't delivered a result
  const patterns = [
    { re: /Reading\s+([\w/\\.]+(?:\.\w+)?)\s*\.\.\./, label: m => `Reading ${m[1]}` },
    { re: /Checking\s+([\w\s/\\.]+?)\s*\.\.\./, label: m => `Checking ${m[1].trim()}` },
    { re: /(?:I(?:'ll| will)|Let me)\s+(?:now\s+)?(?:read|check|review|analyze|fix|update|inspect|fetch|audit|look at|examine)\s+([\w\s/\\.'"-]+?)(?:[.,]|$)/i, label: m => `Working on ${m[1].trim()}` },
    { re: /\bI(?:'ll| will)\s+need to\s+(.{8,60})(?:[.,]|$)/i, label: m => m[1].trim() },
    { re: /(?:^|\n)\s*(?:Step \d+|Next:|Now:)\s+(.{10,80})\.\.\./im, label: m => m[1].trim() },
    { re: /\.\.\.\s*$/, label: () => 'In progress' },
  ];
  const tasks = [];
  const seen = new Set();
  for (const { re, label } of patterns) {
    const m = trimmed.match(re);
    if (m) {
      const t = label(m).slice(0, 80);
      if (!seen.has(t)) { seen.add(t); tasks.push(t); }
    }
  }
  if (!tasks.length) return { unfinished: false, tasks: [], prompt: '' };
  const prompt = `Please continue and deliver the actual result now — show the code fix, findings, or changes directly. Do not describe what you plan to do; just do it. (Task: ${tasks[0]})`;
  return { unfinished: true, tasks, prompt };
}

function _renderAgentSessionBar(agentKey, tasks, continuePrompt) {
  const encoded = _relayEncode(continuePrompt);
  const agentLabel = _chatAgentLabel(agentKey);
  const taskItems = tasks.map(t => `<span class="chat-session-task">${_escapeHtml(t)}</span>`).join('');
  return `<div class="chat-session-bar">
    <div class="chat-session-header">
      <span class="chat-session-pulse"></span>
      <span class="chat-session-label">Session open · ${_escapeHtml(agentLabel)}</span>
      <div class="chat-session-tasks">${taskItems}</div>
    </div>
    <div class="chat-session-footer">
      <span style="font-size:9px;color:var(--text-dim);">Agent declared action but hasn't delivered result yet</span>
      <button class="chat-action-btn chat-session-continue-btn" data-agent="${_escapeHtml(agentKey)}" data-prompt="${_escapeHtml(encoded)}" onclick="continueAgentSession(this.dataset.agent,this.dataset.prompt,this)">Continue →</button>
    </div>
  </div>`;
}

function continueAgentSession(agentKey, encodedPrompt, btn) {
  const question = _relayDecode(encodedPrompt);
  if (!question || !agentKey) return;
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Sending…';
    btn.closest('.chat-session-bar')?.classList.add('active');
  }
  _applySingleAgentSelection(agentKey);
  const input = document.getElementById('question-input');
  if (!input) return;
  input.value = question;
  Promise.resolve(sendMessage('relay', { from: agentKey, target: agentKey, question, chainDepth: -1 }));
}
// ─────────────────────────────────────────────────────────────────────────────

function _extractAgentDirectedQuestions(text, fromAgent) {
  const raw = String(text || '');
  if (!raw) return [];
  const fromKey = String(fromAgent || '').toLowerCase().trim();
  const lines = raw.split(/\r?\n/).map(l => l.trim()).filter(Boolean);
  const out = [];
  const seen = new Set();

  const resolveAgentName = (name) => {
    const probe = String(name || '').trim().toLowerCase().replace(/^@+/, '');
    if (!probe) return '';
    const normalized = probe.replace(/[^a-z0-9]/g, '');
    const found = CHAT_AGENT_OPTIONS.find(a => {
      const key = String(a.value || '').toLowerCase();
      const label = String(a.label || '').toLowerCase();
      const labelNormalized = label.replace(/[^a-z0-9]/g, '');
      return key === probe || label === probe || key.replace(/[^a-z0-9]/g, '') === normalized || labelNormalized === normalized;
    });
    return found ? String(found.value || '').toLowerCase() : '';
  };

  // Support grouped directives like "GEMMA, LLaMA, QWEN: <request>".
  const groupedTargets = raw.match(/(^|\n)\s*([A-Za-z0-9_.\- ]+(?:\s*,\s*[A-Za-z0-9_.\- ]+)+)\s*:\s*([\s\S]{8,320})/);
  if (groupedTargets) {
    const targetChunk = String(groupedTargets[2] || '');
    const firstBodyLine = String(groupedTargets[3] || '').split(/\r?\n/).map(s => s.trim()).filter(Boolean)[0] || '';
    const normalizedBody = _normalizeRelayQuestion(
      firstBodyLine.replace(/^could\s+you\s+/i, '').replace(/^please\s+/i, '')
    );
    const names = targetChunk.split(',').map(n => String(n || '').trim().toLowerCase()).filter(Boolean);
    names.forEach(name => {
      const opt = CHAT_AGENT_OPTIONS.find(a => {
        const key = String(a.value || '').toLowerCase();
        const label = String(a.label || '').toLowerCase();
        return key === name || label === name || label.replace(/\s+/g, '') === name.replace(/\s+/g, '');
      });
      if (!opt || !normalizedBody) return;
      const target = String(opt.value || '').toLowerCase();
      if (!target || target === fromKey) return;
      const sig = `${target}|${_relayQuestionKey(normalizedBody)}`;
      if (seen.has(sig)) return;
      seen.add(sig);
      out.push({ from: fromKey || 'agent', target, question: normalizedBody });
    });
  }

  // Catch multi-directive narration in a single paragraph:
  // "LLaMA, inspect logs... Qwen, prioritize likely causes..."
  if (!groupedTargets) {
    const markers = [];
    const markerSeen = new Set();
    CHAT_AGENT_OPTIONS.forEach(opt => {
      const variants = [String(opt.value || '').toLowerCase()];
      const label = String(opt.label || '').toLowerCase();
      if (label && !variants.includes(label)) variants.push(label);
      variants.forEach(variant => {
        const safeVariant = variant.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const re = new RegExp(`(?:^|[\\n.;!?]\\s*|\\s)(@?${safeVariant})\\s*[:,]`, 'gim');
        let addressMatch;
        while ((addressMatch = re.exec(raw)) !== null) {
          const token = String(addressMatch[1] || '').trim();
          const target = resolveAgentName(token);
          if (!target || target === fromKey) continue;
          const tokenStart = addressMatch.index + String(addressMatch[0] || '').indexOf(token);
          const key = `${target}|${tokenStart}`;
          if (markerSeen.has(key)) continue;
          markerSeen.add(key);
          markers.push({
            target,
            bodyStart: re.lastIndex,
            matchStart: tokenStart,
          });
        }
      });
    });
    markers.sort((a, b) => a.matchStart - b.matchStart);
    // Only honour relay directives in the last 300 chars of the response (terminal relay format).
    // Mid-body mentions like "Mistral: Can you..." inside a narrative are NOT relays.
    const relayZoneStart = Math.max(0, raw.length - 300);
    markers.forEach((marker, index) => {
      if (marker.matchStart < relayZoneStart) return; // mid-body — ignore
      const nextStart = index + 1 < markers.length ? markers[index + 1].matchStart : raw.length;
      const body = String(raw.slice(marker.bodyStart, nextStart) || '').trim();
      if (!body || /^@?[A-Za-z][A-Za-z0-9_.\- ]{1,24}\s*[:,]/.test(body)) return;
      const normalizedQ = _normalizeRelayQuestion(body);
      if (!normalizedQ) return;
      const sig = `${marker.target}|${_relayQuestionKey(normalizedQ)}`;
      if (seen.has(sig)) return;
      seen.add(sig);
      out.push({ from: fromKey || 'agent', target: marker.target, question: normalizedQ });
    });
  }

  const sentenceChunks = raw
    .split(/\r?\n|(?<=[.!?])\s+/)
    .map(s => String(s || '').trim())
    .filter(Boolean);

  sentenceChunks.forEach(sentence => {
    const assistMatch = sentence.match(/([A-Za-z][A-Za-z0-9_.\- ]{1,24}(?:\s*(?:,|and)\s*[A-Za-z][A-Za-z0-9_.\- ]{1,24})+)\s+(?:will|can|should)\s+(.{6,220})/i);
    if (assistMatch) {
      const names = String(assistMatch[1] || '')
        .split(/\s*(?:,|and)\s*/i)
        .map(n => resolveAgentName(n))
        .filter(Boolean);
      let task = String(assistMatch[2] || '').trim()
        .replace(/^assist\s+in\s+/i, '')
        .replace(/^assist\s+with\s+/i, '')
        .replace(/^help\s+with\s+/i, '')
        .replace(/^help\s+/i, '');
      const normalizedQ = _normalizeRelayQuestion(task);
      if (normalizedQ) {
        names.forEach(target => {
          if (!target || target === fromKey) return;
          const sig = `${target}|${_relayQuestionKey(normalizedQ)}`;
          if (seen.has(sig)) return;
          seen.add(sig);
          out.push({ from: fromKey || 'agent', target, question: normalizedQ });
        });
      }
    }

    // Delegation patterns: "direct LLaMA to X", "ask Qwen to Y", "have Eight check Z"
    const delegationRe = /(?:direct(?:ing)?|ask(?:ing)?|hav(?:ing|e)|send(?:ing)?)\s+([A-Za-z][A-Za-z0-9_. \-]{1,24}?)\s+to\s+(.{4,200}?)(?=[.;!?\n]|$)/gi;
    let delMatch;
    while ((delMatch = delegationRe.exec(sentence)) !== null) {
      const target = resolveAgentName(delMatch[1]);
      if (!target || target === fromKey) continue;
      const normalizedQ = _normalizeRelayQuestion(String(delMatch[2] || '').trim());
      if (!normalizedQ) continue;
      const sig = `${target}|${_relayQuestionKey(normalizedQ)}`;
      if (seen.has(sig)) continue;
      seen.add(sig);
      out.push({ from: fromKey || 'agent', target, question: normalizedQ });
    }

    const assignmentMatch = sentence.match(/assign(?:ing|ed)?\s+(.{3,120}?)\s+to\s+([A-Za-z][A-Za-z0-9_.\- ]{1,24})\s+(?:for|to)\s+(.{4,180})/i);
    if (assignmentMatch) {
      const target = resolveAgentName(assignmentMatch[2]);
      const task = `${String(assignmentMatch[1] || '').trim()} ${String(assignmentMatch[3] || '').trim()}`;
      const normalizedQ = _normalizeRelayQuestion(task);
      if (target && target !== fromKey && normalizedQ) {
        const sig = `${target}|${_relayQuestionKey(normalizedQ)}`;
        if (!seen.has(sig)) {
          seen.add(sig);
          out.push({ from: fromKey || 'agent', target, question: normalizedQ });
        }
      }
    }

    if (/\bteam\b/i.test(sentence)) {
      const teamTask = String(sentence)
        .replace(/.*?\bteam\b\s+(?:for|to|will)?\s*/i, '')
        .trim();
      const normalizedQ = _normalizeRelayQuestion(teamTask || sentence);
      if (normalizedQ) {
        ['gemma', 'llama', 'mistral', 'qwen'].forEach(target => {
          if (!_isKnownChatAgent(target) || target === fromKey) return;
          const sig = `${target}|${_relayQuestionKey(normalizedQ)}`;
          if (seen.has(sig)) return;
          seen.add(sig);
          out.push({ from: fromKey || 'agent', target, question: normalizedQ });
        });
      }
    }
  });

  const patternsFor = (target) => ([
    new RegExp(`^@?${target}\\b[\\s,:-]+(.{6,260})$`, 'i'),
    new RegExp(`(?:^|\\s)@${target}\\b[\\s,:-]+(.{6,260})$`, 'i'),
    new RegExp(`(?:ask|question\\s+for|for)\\s+${target}\\b[\\s,:-]+(.{6,260}\\?)$`, 'i'),
    new RegExp(`${target}\\s*[:,]\\s*(.{6,260})$`, 'i'),
    // Match target-directed clause after a prior sentence, with or without question mark.
    new RegExp(`(?:^|[.!?]\\s+)${target}\\s*[:,]\\s*(.{6,260}?)(?:[.!?]|$)`, 'i'),
  ]);

  for (const line of lines) {
    if (/([A-Za-z][A-Za-z0-9_.\- ]{1,24}(?:\s*(?:,|and)\s*[A-Za-z][A-Za-z0-9_.\- ]{1,24})+)\s+(?:will|can|should)\s+/i.test(line)) continue;
    if (/^\s*[A-Za-z0-9_.\- ]+(?:\s*,\s*[A-Za-z0-9_.\- ]+)+\s*:/.test(line)) continue;
    if (/^\s*@?[A-Za-z][A-Za-z0-9_.\- ]{1,24}\s*[:,]/.test(line)) continue;
    for (const opt of CHAT_AGENT_OPTIONS) {
      const target = String(opt.value || '').toLowerCase();
      if (!target || target === fromKey) continue;
      const alt = String(opt.label || '').toLowerCase();
      const variants = [target];
      if (alt && alt !== target) variants.push(alt.replace(/\s+/g, ''));

      let captured = '';
      for (const variant of variants) {
        const safeVariant = variant.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const rules = patternsFor(safeVariant);
        for (const re of rules) {
          const m = line.match(re);
          if (m && m[1]) {
            captured = String(m[1] || '').trim();
            break;
          }
        }
        if (captured) break;
      }
      if (!captured) continue;

      const normalizedQ = _normalizeRelayQuestion(captured);
      if (!normalizedQ) continue;
      const sig = `${target}|${_relayQuestionKey(normalizedQ)}`;
      if (seen.has(sig)) continue;
      seen.add(sig);
      out.push({
        from: fromKey || 'agent',
        target,
        question: normalizedQ,
      });
    }
  }
  _applyManualRelayRules(raw, fromKey, seen, out);
  // Maximum one Route button per target agent — deduplicate across all branches
  const seenTargets = new Set();
  return out.filter(entry => {
    if (seenTargets.has(entry.target)) return false;
    seenTargets.add(entry.target);
    return true;
  }).slice(0, 6);
}

function _normalizeRelayQuestion(raw) {
  let q = String(raw || '').replace(/\s+/g, ' ').trim();
  q = q.replace(/^["'`\-:\s]+/, '').replace(/["'`\s]+$/, '');
  if (/^if\s+/i.test(q)) {
    q = q.replace(/^if\s+/i, '').trim();
  }
  q = q
    .replace(/^he\s+is\b/i, 'you are')
    .replace(/^he's\b/i, 'you are')
    .replace(/^she\s+is\b/i, 'you are')
    .replace(/^she's\b/i, 'you are');
  if (!q) return '';
  if (!/[?!.]$/.test(q)) q += '?';
  return q.slice(0, 260);
}

function _extractUserRequestedHandoffs(message, selectedAgents) {
  const text = String(message || '');
  if (!text) return [];
  const sender = (selectedAgents && selectedAgents.length) ? String(selectedAgents[0]).toLowerCase() : 'user';
  const handoffs = [];
  const seen = new Set();

  const resolveAgent = (rawName) => {
    const name = String(rawName || '').trim().toLowerCase();
    if (!name) return '';
    const normalizedName = name.replace(/[^a-z0-9]/g, '');
    const found = CHAT_AGENT_OPTIONS.find(opt => {
      const key = String(opt.value || '').toLowerCase();
      const label = String(opt.label || '').toLowerCase();
      const labelNormalized = label.replace(/[^a-z0-9]/g, '');
      return key === name || label === name || labelNormalized === normalizedName;
    });
    return found ? String(found.value || '').toLowerCase() : '';
  };

  const queueRegex = /(?:\b(?:ask|get|have|getting|then\s+ask|then\s+get|then\s+have|and\s+then\s+ask)\s+)([A-Za-z][A-Za-z0-9_.\- ]{1,40})\s+to\s+(.{4,260}?)(?=(?:\s+(?:before\s+then|and\s+then|then|after\s+that)\s+(?:ask|get|have|getting)\s+[A-Za-z][A-Za-z0-9_.\- ]{1,40}\s+to\b)|(?:\s+or\s+to\s+ask\s+[A-Za-z][A-Za-z0-9_.\- ]{1,40}\s+to\b)|$)/ig;
  let queueMatch;
  while ((queueMatch = queueRegex.exec(text)) !== null) {
    const target = resolveAgent(queueMatch[1]);
    if (!target || target === sender) continue;
    const question = _normalizeRelayQuestion(queueMatch[2]);
    if (!question) continue;
    const sig = `${target}|${_relayQuestionKey(question)}`;
    if (seen.has(sig)) continue;
    seen.add(sig);
    handoffs.push({ from: sender, target, question, source: 'user-queue' });
  }

  const localCoreTargets = ['gemma', 'llama', 'mistral', 'qwen'].filter(a => _isKnownChatAgent(a));
  const teamworkSignal = /\b(team|swarm|everyone|all\s+agents?|rest\s+of\s+the\s+team)\b/i.test(text);
  if (teamworkSignal && Array.isArray(selectedAgents) && selectedAgents.length === 1 && localCoreTargets.length) {
    const lead = String(selectedAgents[0] || '').toLowerCase();
    const teamQuestion = _normalizeRelayQuestion(text);
    if (teamQuestion) {
      localCoreTargets.forEach(target => {
        if (target === lead) return;
        const sig = `${target}|${_relayQuestionKey(teamQuestion)}`;
        if (seen.has(sig)) return;
        seen.add(sig);
        handoffs.push({ from: lead || sender, target, question: teamQuestion, source: 'team-intent' });
      });
    }
  }
  const localFanoutMatch = text.match(/(?:^|\b)ask\s+(?:the\s+)?local\s+agents?\s+(.{6,260})$/i);
  if (localFanoutMatch && localCoreTargets.length) {
    const question = _normalizeRelayQuestion(localFanoutMatch[1]);
    if (question) {
      localCoreTargets.forEach(target => {
        const sig = `${target}|${_relayQuestionKey(question)}`;
        if (seen.has(sig)) return;
        seen.add(sig);
        handoffs.push({ from: sender, target, question, source: 'user-intent' });
      });
    }
  }

  const impliedTargetMatch = text.match(/(?:^|\b)ask\s+(?:that|this|the)\s+agent\s+(.{4,260})$/i);
  if (impliedTargetMatch) {
    const impliedQuestion = _normalizeRelayQuestion(impliedTargetMatch[1]);
    const impliedTargets = (window.__fridaysLastMentionedAgents || []).slice(0, 1);
    const fallbackTarget = (selectedAgents || []).length ? String(selectedAgents[0] || '').toLowerCase() : '';
    if (!impliedTargets.length && fallbackTarget) impliedTargets.push(fallbackTarget);
    impliedTargets.forEach(target => {
      if (!target || !_isKnownChatAgent(target) || !impliedQuestion) return;
      const sig = `${target}|${_relayQuestionKey(impliedQuestion)}`;
      if (seen.has(sig)) return;
      seen.add(sig);
      handoffs.push({ from: sender, target, question: impliedQuestion, source: 'user-intent' });
    });
  }

  for (const opt of CHAT_AGENT_OPTIONS) {
    const target = String(opt.value || '').toLowerCase();
    if (!target) continue;

    const escaped = target.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const rules = [
      new RegExp(`(?:^|\\b)ask\\s+${escaped}\\s+to\\s+(.{6,260})$`, 'i'),
      new RegExp(`(?:^|\\b)ask\\s+${escaped}[\\s,:-]+(.{6,260})$`, 'i'),
      new RegExp(`(?:^|\\b)have\\s+${escaped}\\s+(.{6,260})$`, 'i'),
      new RegExp(`(?:^|\\b)can\\s+${escaped}\\s+(.{6,260})$`, 'i'),
      new RegExp(`(?:^|\\b)if\\s+${escaped}\\s+(?:is|\\'s|is\\s+currently)\\s+online\\b`, 'i'),
    ];

    for (const re of rules) {
      const m = text.match(re);
      if (!m) continue;
      const derived = m[1] ? m[1] : `are you online`;
      const question = _normalizeRelayQuestion(derived);
      if (!question) continue;
      const sig = `${target}|${_relayQuestionKey(question)}`;
      if (seen.has(sig)) continue;
      seen.add(sig);
      handoffs.push({ from: sender, target, question, source: 'user-intent' });
    }
  }

  return handoffs.slice(0, 4);
}

function _applySingleAgentSelection(agentKey) {
  const target = String(agentKey || '').toLowerCase().trim();
  if (!target) return;
  Object.keys(window.__fridaysChatEnabledAgents || {}).forEach(k => {
    window.__fridaysChatEnabledAgents[k] = (k === target);
  });
  // Always ensure the target is enabled — even if it was never in the dict
  window.__fridaysChatEnabledAgents[target] = true;
  persistThreadAgentSelection();
  renderChatAgentToggles();
  updateComposerMeta();
  updateChatStatusPills();
}

function _relayPromptText(handoff) {
  const fromLabel = _chatAgentLabel(handoff.from || 'agent');
  const targetLabel = _chatAgentLabel(handoff.target || 'agent');
  const depth = Number(handoff.chainDepth ?? -1);
  const chainTag = depth >= 0 ? ` [⛓${depth}]` : '';
  return `${fromLabel} to ${targetLabel}${chainTag}: ${String(handoff.question || '').trim()}`;
}

function populateRelayRuleTargetOptions() {
  const select = document.getElementById('relay-rule-target');
  if (!select) return;
  const current = select.value;
  select.innerHTML = '<option value="">Target agent</option>' + CHAT_AGENT_OPTIONS.map(opt =>
    `<option value="${_escapeHtml(opt.value)}">${_escapeHtml(opt.label)}</option>`
  ).join('');
  if (current) select.value = current;
}

function renderRelayRuleList() {
  const host = document.getElementById('chat-relay-rules-list');
  if (!host) return;
  const rules = _relayRules();
  if (!rules.length) {
    host.innerHTML = '<div style="padding:8px 10px;font-size:10px;color:var(--text-dim);border:1px dashed var(--border);border-radius:6px;">No manual relay rules yet.</div>';
    return;
  }
  host.innerHTML = rules.map((rule, index) => `
    <div style="padding:8px 10px;border:1px solid var(--border);border-radius:6px;background:var(--card);display:flex;gap:8px;align-items:flex-start;">
      <div style="flex:1;min-width:0;">
        <div style="font-size:11px;color:var(--text);"><strong>Match:</strong> ${_escapeHtml(rule.pattern || '')}</div>
        <div style="font-size:10px;color:var(--text-dim);margin-top:3px;"><strong>Target:</strong> ${_escapeHtml(_chatAgentLabel(rule.target || 'agent'))}</div>
        <div style="font-size:10px;color:var(--text-dim);margin-top:3px;"><strong>Rewrite:</strong> ${_escapeHtml(rule.template || '{match}')}</div>
      </div>
      <button class="chat-action-btn" onclick="removeRelayRule(${index})">Remove</button>
    </div>
  `).join('');
}

function addRelayRule() {
  const patternEl = document.getElementById('relay-rule-pattern');
  const targetEl = document.getElementById('relay-rule-target');
  const templateEl = document.getElementById('relay-rule-template');
  const pattern = String(patternEl?.value || '').trim();
  const target = String(targetEl?.value || '').toLowerCase().trim();
  const template = String(templateEl?.value || '').trim();
  if (!pattern || !target) {
    showToast('Relay rule pattern and target are required', 'error');
    return;
  }
  const rules = _relayRules();
  rules.push({ pattern, target, template });
  _saveRelayRules();
  if (patternEl) patternEl.value = '';
  if (templateEl) templateEl.value = '';
  if (targetEl) targetEl.value = '';
  renderRelayRuleList();
  showToast('Relay rule added', 'success');
}

function removeRelayRule(index) {
  const rules = _relayRules();
  if (index < 0 || index >= rules.length) return;
  rules.splice(index, 1);
  _saveRelayRules();
  renderRelayRuleList();
  showToast('Relay rule removed', 'info');
}

function _relaySignature(handoff) {
  const normalizeQuestionSig = (question) => String(question || '')
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 140);
  return [
    String(handoff.from || '').toLowerCase(),
    String(handoff.target || '').toLowerCase(),
    normalizeQuestionSig(handoff.question || ''),
  ].join('|');
}

function sendProposalToDuck(proposalId, conversationId) {
  if (!proposalId) return;
  const convId = conversationId || window.__fridaysChatConvId;
  const msg = `Check proposal ${proposalId} — review and approve or reject.`;
  // Send directly to Duck in the current conversation
  const payload = {
    message: msg,
    agents: ['duck'],
    conversation_id: convId || undefined,
    relay_from: 'user',
    auto_relay: false,
  };
  fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...(typeof _authPayload === 'function' ? _authPayload() : {}), ...payload }),
  })
    .then(r => r.json())
    .then(data => {
      if (data.ok) {
        showToast(`Sent ${proposalId} to Duck`, 'success');
      } else {
        showToast('Send to Duck failed: ' + (data.error || data.response || 'unknown'), 'error');
      }
    })
    .catch(e => showToast('Send to Duck error: ' + e.message, 'error'));
}

function queueRelayHandoffFromButton(btn) {
  if (!btn) return;
  const handoff = {
    from: String(btn.dataset.relayFrom || '').toLowerCase(),
    target: String(btn.dataset.relayTarget || '').toLowerCase(),
    question: _relayDecode(btn.dataset.relayQuestion || ''),
    auto: false,
  };
  queueRelayHandoff(handoff, false);
}

function queueRelayHandoff(handoff, autoMode = false) {
  const target = String(handoff && handoff.target || '').toLowerCase().trim();
  const question = String(handoff && handoff.question || '').trim();
  if (!target || !question || !_isKnownChatAgent(target)) return;
  if (autoMode && !_isAutoRelayTargetEnabled(target)) return;

  const item = {
    from: String(handoff.from || 'agent').toLowerCase().trim(),
    target,
    question,
    auto: !!autoMode,
    // chainDepth >= 0 means this relay has its own per-chain budget (independent of global turn budget).
    // -1 means fall back to the global turn budget.
    chainDepth: Number.isFinite(Number(handoff.chainDepth)) ? Math.max(0, Number(handoff.chainDepth)) : -1,
  };
  const sig = _relaySignature(item);
  const now = Date.now();
  const seen = window.__fridaysChatRelaySeen || {};
  if (seen[sig] && (now - Number(seen[sig] || 0) < 8 * 60 * 1000)) {
    return;
  }

  const queue = Array.isArray(window.__fridaysChatRelayQueue) ? window.__fridaysChatRelayQueue : [];
  if (queue.some(q => _relaySignature(q) === sig)) {
    return;
  }

  if (item.auto && !window.__fridaysChatRelayAuto) return;

  const cap = _relayQueueCap();
  if (queue.length >= cap) {
    if (item.auto) {
      _appendInfoLogEntry('librarian', `Backpressure: relay queue full (${queue.length}/${cap}).`, true);
    }
    window.__fridaysChatRelayHoldReason = `queue full (${queue.length}/${cap})`;
    window.__fridaysChatRelayHoldStamp = Date.now();
    _renderChatRelayControls();
    return;
  }

  seen[sig] = now;
  window.__fridaysChatRelaySeen = seen;
  window.__fridaysChatRelayQueue = queue;
  window.__fridaysChatRelayQueue.push(item);
  window.__fridaysChatRelayActive = true;
  window.__fridaysChatRelayHoldReason = '';
  window.__fridaysChatRelayHoldStamp = 0;
  if (item.auto) {
    const _chainTag = item.chainDepth >= 0 ? ` Chain ⛓${item.chainDepth}.` : '';
    _appendInfoLogEntry('librarian', `Queued relay ticket for ${_chatAgentLabel(item.target)}.${_chainTag}`, true);
    const libSeen = window.__fridaysLibrarianRelayAudit || {};
    if (!libSeen[sig] || (now - Number(libSeen[sig] || 0) > 8 * 60 * 1000)) {
      _appendInfoLogEntry('librarian', `Audit captured: ${_chatAgentLabel(item.from)} assigned ${_chatAgentLabel(item.target)}.`, true);
      libSeen[sig] = now;
      window.__fridaysLibrarianRelayAudit = libSeen;
    }
  }
  _renderChatRelayControls();
  _processRelayQueue();
}

async function _processRelayQueue() {
  if (window.__fridaysChatRelayProcessing) return;
  // In parallel exec mode, relay queue is disabled — all agents answer at once
  if (!_isSequentialExecMode()) {
    window.__fridaysChatRelayQueue = [];
    window.__fridaysChatRelayActive = false;
    window.__fridaysChatRelayHoldReason = '';
    _renderChatRelayControls();
    return;
  }
  window.__fridaysChatRelayProcessing = true;
  try {
  const queue = Array.isArray(window.__fridaysChatRelayQueue) ? window.__fridaysChatRelayQueue : [];
  window.__fridaysChatRelayActive = queue.length > 0;
  if (!queue.length) {
    window.__fridaysChatRelayHoldReason = '';
    window.__fridaysChatRelayHoldStamp = 0;
    _relayClearRetryTimer();
    _renderChatRelayControls();
    return;
  }
  const next = queue[0];
  if (!next || !next.target || !next.question) {
    queue.shift();
    window.__fridaysChatRelayQueue = queue;
    _renderChatRelayControls();
    setTimeout(() => _processRelayQueue(), 0);
    return;
  }

  const gate = await _relayDispatchGate(next);
  if (!gate || !gate.allow) {
    const reason = String((gate && gate.reason) || 'resource hold').trim();
    if (reason === 'turn budget exhausted') {
      const before = queue.length;
      const kept = queue.filter(item => !item?.auto);
      const dropped = Math.max(0, before - kept.length);
      window.__fridaysChatRelayQueue = kept;
      window.__fridaysChatRelayActive = kept.length > 0;
      window.__fridaysChatRelayHoldReason = dropped > 0
        ? `turn budget exhausted (${dropped} deferred)`
        : 'turn budget exhausted';
      window.__fridaysChatRelayHoldStamp = Date.now();
      const deferKey = `turn-budget-deferred:${dropped}`;
      const shouldLog = window.__fridaysChatRelayLastHoldKey !== deferKey;
      window.__fridaysChatRelayLastHoldKey = deferKey;
      _relayClearRetryTimer();
      if (dropped > 0 && shouldLog) {
        _appendInfoLogEntry('librarian', `Turn budget exhausted; deferred ${dropped} auto relay ticket${dropped === 1 ? '' : 's'} until the next user turn.`, true);
      }
      _renderChatRelayControls();
      return;
    }
    window.__fridaysChatRelayHoldReason = reason;
    window.__fridaysChatRelayHoldStamp = Date.now();
    const holdKey = `${next.from || 'agent'}>${next.target || 'agent'}:${reason}`;
    if (window.__fridaysChatRelayLastHoldKey !== holdKey) {
      window.__fridaysChatRelayLastHoldKey = holdKey;
      _appendInfoLogEntry('librarian', `Relay hold: ${reason}.`, true);
    }
    if (gate && gate.deferToBack && queue.length > 1) {
      queue.push(queue.shift());
      window.__fridaysChatRelayQueue = queue;
    }
    _renderChatRelayControls();
    _relayScheduleRetry((gate && gate.retryMs) || CHAT_RELAY_RESOURCE_LIMITS.retryMsNormal);
    return;
  }

  window.__fridaysChatRelayHoldReason = '';
  window.__fridaysChatRelayHoldStamp = 0;
  window.__fridaysChatRelayLastHoldKey = '';
  _relayClearRetryTimer();

  queue.shift();
  window.__fridaysChatRelayQueue = queue;
  // Chain-budget relays manage their own depth — don't deplete the global turn budget.
  if (next.auto && Number(next.chainDepth ?? -1) < 0 && Number(window.__fridaysChatRelayBudget || 0) > 0) {
    window.__fridaysChatRelayBudget = Math.max(0, Number(window.__fridaysChatRelayBudget || 0) - 1);
  }
  window.__fridaysChatRelayInFlight = (window.__fridaysChatRelayInFlight || 0) + 1;
  window.__fridaysChatRelayBusy = true;
  window.__fridaysChatRelayActive = true;
  pollActiveThreadRuntime(true);
  const input = document.getElementById('question-input');
  if (!input) {
    window.__fridaysChatRelayInFlight = Math.max(0, (window.__fridaysChatRelayInFlight || 1) - 1);
    window.__fridaysChatRelayBusy = (window.__fridaysChatRelayInFlight || 0) > 0;
    window.__fridaysChatRelayActive = false;
    _renderChatRelayControls();
    return;
  }
  // Mark relay-activated agent as 'relay' state (red indicator)
  Object.keys(window.__fridaysChatAgentSelectionState || {}).forEach(k => {
    if (window.__fridaysChatAgentSelectionState[k] === 'relay') window.__fridaysChatAgentSelectionState[k] = null;
  });
  _setAgentSelectionState(next.target, 'relay');
  input.value = _relayPromptText(next);
  if (next.auto) {
    const _dispatchChainTag = Number(next.chainDepth ?? -1) >= 0 ? ` ⛓${next.chainDepth} remaining.` : '';
    _appendInfoLogEntry('librarian', `Dispatching ${_chatAgentLabel(next.target)} relay ticket.${_dispatchChainTag}`, true);
  }
  showToast(`${_chatAgentLabel(next.from)} → ${_chatAgentLabel(next.target)}`, next.auto ? 'info' : 'success');
  Promise.resolve(sendMessage('relay', next))
    .finally(() => {
      window.__fridaysChatRelayInFlight = Math.max(0, (window.__fridaysChatRelayInFlight || 1) - 1);
      window.__fridaysChatRelayBusy = (window.__fridaysChatRelayInFlight || 0) > 0;
      window.__fridaysChatRelayActive = Array.isArray(window.__fridaysChatRelayQueue) && window.__fridaysChatRelayQueue.length > 0;
      _renderChatRelayControls();
      pollActiveThreadRuntime(true);
      setTimeout(() => _processRelayQueue(), 0);
    });
  } finally {
    window.__fridaysChatRelayProcessing = false;
  }
}

function _chatThinkingHistoryState() {
  window.__fridaysChatJobHistory = window.__fridaysChatJobHistory || {};
  return window.__fridaysChatJobHistory;
}

function _timelineTextSnippet(text) {
  return String(text || '').replace(/\s+/g, ' ').trim().slice(0, 140);
}

function _chatLogTimeLabel(ts = Date.now()) {
  const d = new Date(Number(ts || Date.now()));
  return d.toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true });
}

function _appendInfoLogEntry(actor, text, relay = false) {
  const messages = _chatMessagesEl();
  if (!messages) return;
  const key = String(actor || 'system').toLowerCase().trim();
  const label = _chatAgentLabel(key);
  const _infoSvg = {
    duck:      '<svg viewBox="0 0 16 16" width="11" height="11" fill="none" aria-hidden="true"><path d="M4 9.5c0 2 1.8 3 4 3s4-1 4-3c0-1.5-1-2.5-3-2.5H8c1 0 2-1 2-2S9 3 8 3C6.5 3 5.5 4 5.5 5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/><path d="M12 7.5l2 1" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
    librarian: '<svg viewBox="0 0 16 16" width="11" height="11" fill="none" aria-hidden="true"><path d="M4.5 3.5v9M4.5 3.5h5a2 2 0 010 4h-5M4.5 7.5h5.5a2 2 0 010 4H4.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    default:   '<svg viewBox="0 0 16 16" width="11" height="11" fill="none" aria-hidden="true"><circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="1.3"/><path d="M8 7v4M8 5.5v.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
  };
  const icon = _infoSvg[key] || _infoSvg.default;
  const ts = Date.now();
  const timeLabel = _chatLogTimeLabel(ts);
  const row = document.createElement('div');
  row.className = 'chat-info-log';
  row.dataset.logTs = String(ts);
  const msgId = Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
  row.id = 'chat-bubble-' + msgId;
  row.innerHTML = `<span class="chat-info-log-head"><strong>${icon} ${_escapeHtml(label)} Log</strong><span class="chat-info-log-time">${_escapeHtml(timeLabel)}</span></span><span>${_escapeHtml(String(text || ''))}</span>`;
  messages.appendChild(row);
  _recordTimelineEvent({
    bubbleId: row.id,
    sender: key,
    label,
    text: String(text || ''),
    ts,
    relay: !!relay,
  });
  messages.scrollTop = messages.scrollHeight;
}

function setRelayTimelineFilter(filter = 'all') {
  window.__fridaysChatTimelineFilter = String(filter || 'all').toLowerCase();
  renderChatRelayTimeline();
}

function showRelayLogs(filter = 'all') {
  const key = String(filter || 'all').toLowerCase();
  setRelayTimelineFilter(key);
  const metaSection = _chatSectionElement('meta');
  if (metaSection) {
    metaSection.classList.remove('collapsed');
    _syncChatSectionAria('meta');
  }
  const timeline = document.getElementById('chat-relay-timeline');
  if (timeline) timeline.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function _recordTimelineEvent(entry) {
  if (!entry || !entry.bubbleId) return;
  window.__fridaysChatTimeline = Array.isArray(window.__fridaysChatTimeline) ? window.__fridaysChatTimeline : [];
  const eventTs = Number(entry.ts || Date.now());
  window.__fridaysChatTimeline.push({
    bubbleId: String(entry.bubbleId),
    sender: String(entry.sender || 'agent').toLowerCase(),
    label: String(entry.label || _chatAgentLabel(entry.sender || 'agent')),
    text: _timelineTextSnippet(entry.text || ''),
    ts: Number.isFinite(eventTs) ? eventTs : Date.now(),
    relay: !!entry.relay,
  });
  if (window.__fridaysChatTimeline.length > 220) {
    window.__fridaysChatTimeline = window.__fridaysChatTimeline.slice(-220);
  }
  renderChatRelayTimeline();
}

function clearRelayTimeline() {
  window.__fridaysChatTimeline = [];
  renderChatRelayTimeline();
}

function renderChatRelayTimeline() {
  const host = document.getElementById('chat-relay-timeline');
  if (!host) return;
  const mode = String(window.__fridaysChatTimelineFilter || 'all').toLowerCase();
  const rows = (Array.isArray(window.__fridaysChatTimeline) ? window.__fridaysChatTimeline : [])
    .filter(row => {
      if (mode === 'all') return true;
      return String(row?.sender || '').toLowerCase() === mode;
    })
    .slice(-120);
  if (!rows.length) {
    host.innerHTML = '<div style="padding:8px 10px;font-size:10px;color:var(--text-dim);">No matching relay log events.</div>';
    return;
  }
  host.innerHTML = rows.map(row => {
    const t = new Date(Number(row.ts || Date.now()));
    const hh = t.toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit', hour12: true });
    const chip = row.relay ? 'relay' : 'msg';
    return `<div class="chat-relay-item">
      <span class="chat-relay-item-time">${_escapeHtml(hh)}</span>
      <span class="chat-relay-item-label" title="${_escapeHtml(row.label + ': ' + row.text)}">[${_escapeHtml(chip)}] ${_escapeHtml(row.label)} · ${_escapeHtml(row.text || '(no text)')}</span>
      <button class="chat-relay-item-jump" onclick="jumpToChatBubble('${_escapeHtml(row.bubbleId)}')">Jump</button>
    </div>`;
  }).join('');
  host.scrollTop = host.scrollHeight;
}

function jumpToChatBubble(bubbleId) {
  const id = String(bubbleId || '').trim();
  if (!id) return;
  const node = document.getElementById(id);
  if (!node) return;
  node.scrollIntoView({ behavior: 'smooth', block: 'center' });
  node.classList.add('reply-targeted');
  setTimeout(() => node.classList.remove('reply-targeted'), 900);
}

function _dismissRelayBar(barEl, targetKey) {
  // Remove this bar from the DOM
  if (barEl && barEl.parentNode) barEl.parentNode.removeChild(barEl);
  // If we know the target, drop matching ticket(s) from the live queue
  if (targetKey) {
    const tKey = String(targetKey).toLowerCase();
    if (Array.isArray(window.__fridaysChatRelayQueue)) {
      window.__fridaysChatRelayQueue = window.__fridaysChatRelayQueue.filter(
        t => String(t.target || '').toLowerCase() !== tKey
      );
    }
    _renderChatRelayControls();
  }
}

function clearRelayQueue() {
  window.__fridaysChatRelayQueue = [];
  window.__fridaysChatRelayActive = false;
  _renderChatRelayControls();
  pollActiveThreadRuntime(true);
}

function _formatPendingElapsed(ms) {
  const totalSeconds = Math.max(0, Math.round(Number(ms || 0) / 1000));
  if (totalSeconds < 60) return totalSeconds + 's';
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return minutes + 'm ' + String(seconds).padStart(2, '0') + 's';
}

function _thinkingBubbleNode(jobId) {
  if (!jobId) return null;
  return document.querySelector(`.chat-bubble[data-pending-job-id="${String(jobId)}"]`);
}

function _renderThinkingBubble(job, history) {
  const identity = _chatAgentIdentityHtml(job.agent, true);
  const runtimeClass = job.runtime_class
    ? `<span style="font-size:9px;color:var(--text-dim);opacity:0.55;">[${_escapeHtml(job.runtime_class)}]</span>`
    : '';
  const dotClass = job.status === 'failed' ? 'red' : (job.status === 'completed' ? 'green' : 'amber');
  const currentStage = String(job.stage || 'running').trim() || 'running';
  const etaRemaining = Number(job.eta_remaining_seconds || 0);
  const etaSeconds = Number(job.eta_seconds || 0);
  const elapsedMs = Number(job.elapsed_ms || 0);
  const targetMs = Math.max(1000, Number((job.eta_seconds || 12) * 1000));
  const pct = job.status === 'completed'
    ? 100
    : (job.status === 'failed' ? 100 : Math.min(98, Math.max(4, Math.floor((elapsedMs / targetMs) * 100))));
  const metaBits = [];
  if (etaRemaining > 0) metaBits.push('ETA ~' + etaRemaining + 's');
  else if (etaSeconds > 0 && job.status === 'running') metaBits.push('ETA ~' + etaSeconds + 's');
  if (elapsedMs > 0) metaBits.push('elapsed ' + _formatPendingElapsed(elapsedMs));
  if (job.status && job.status !== 'running') metaBits.push(String(job.status));
  const ts = new Date().toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit', hour12: true });
  const stopBtn = job.status === 'running'
    ? '<button class="chat-action-btn" style="padding:1px 7px;font-size:10px;" onclick="stopPendingAgents()">Stop</button>'
    : '';
  // Build task checklist from stage trace history
  const steps = Array.isArray(history) ? history : [];
  let checklistHtml = '';
  if (steps.length > 0) {
    const rows = steps.map((step, i) => {
      const isLast = i === steps.length - 1;
      const isCurrent = isLast && job.status === 'running';
      const icon = isCurrent
        ? '<span class="think-checklist-spinner"></span>'
        : '<span class="think-checklist-done">&#10003;</span>';
      const cls = isCurrent ? 'think-checklist-item current' : 'think-checklist-item done';
      return `<div class="${cls}">${icon}<span class="think-checklist-text">${_escapeHtml(String(step))}</span></div>`;
    });
    checklistHtml = `<div class="think-checklist">${rows.join('')}</div>`;
  }
  return `
    <div class="chat-meta icon-meta" style="display:flex;align-items:center;gap:5px;margin-bottom:3px;">
      <span>${identity}</span>
      <span class="think-status-dot ${dotClass}"></span>
      ${runtimeClass}
      <span style="font-size:9px;color:var(--text-dim);opacity:0.55;margin-left:auto;">${ts}</span>
    </div>
    <div class="chat-pending-stage">${_escapeHtml(currentStage)}</div>
    ${checklistHtml}
    <div class="chat-pending-progress"><div class="chat-pending-progress-fill" style="width:${pct}%"></div></div>
    <div class="chat-pending-meta">${metaBits.map(bit => `<span>${_escapeHtml(bit)}</span>`).join('')}</div>
    <div class="chat-pending-footer" style="display:flex;align-items:center;justify-content:space-between;gap:8px;">${stopBtn}</div>`;
}

function _upsertThinkingBubble(job) {
  const messages = _chatMessagesEl();
  if (!messages || !job || !job.job_id) return;
  const histories = _chatThinkingHistoryState();
  const currentStage = String(job.stage || '').trim();
  if (!histories[job.job_id]) histories[job.job_id] = [];
  if (currentStage) {
    const items = histories[job.job_id];
    if (!items.length || items[items.length - 1] !== currentStage) {
      items.push(currentStage);
      histories[job.job_id] = items.slice(-16);
    }
  }

  let bubble = _thinkingBubbleNode(job.job_id);
  const isNew = !bubble;
  if (!bubble) {
    bubble = document.createElement('div');
    bubble.className = 'chat-bubble pending';
    bubble.dataset.pendingJobId = String(job.job_id);
    bubble.dataset.thinkingAgent = String(job.agent || 'agent');
    messages.appendChild(bubble);
  }
  bubble.innerHTML = _renderThinkingBubble(job, histories[job.job_id]);
  if (isNew) messages.scrollTop = messages.scrollHeight;
}

function _syncThinkingBubbles(jobs) {
  const messages = _chatMessagesEl();
  if (!messages) return;
  const list = Array.isArray(jobs) ? jobs : [];
  const active = list.filter(job => String(job.status || 'running') === 'running' && job.job_id);
  const wanted = new Set(active.map(job => String(job.job_id)));

  messages.querySelectorAll('.chat-bubble[data-pending-job-id]').forEach(node => {
    const jobId = String(node.dataset.pendingJobId || '');
    if (!wanted.has(jobId)) node.remove();
  });

  const histories = _chatThinkingHistoryState();
  Object.keys(histories).forEach(jobId => {
    if (!wanted.has(String(jobId))) delete histories[jobId];
  });

  active.forEach(_upsertThinkingBubble);
}

function _appendThinkingBubble(agent, runtimeClass, job = {}) {
  _upsertThinkingBubble({
    job_id: job.job_id || ('pending-' + String(agent || 'agent')),
    agent: agent || 'agent',
    runtime_class: runtimeClass || job.runtime_class || '',
    status: job.status || 'running',
    stage: job.stage || 'queued',
    eta_seconds: Number(job.eta_seconds || 0),
    eta_remaining_seconds: Number(job.eta_remaining_seconds || job.eta_seconds || 0),
    elapsed_ms: Number(job.elapsed_ms || 0),
  });
}

function _hexToRgba(hex, alpha) {
  const raw = String(hex || '').trim();
  const normalized = raw.replace('#', '');
  if (!/^[0-9a-fA-F]{6}$/.test(normalized)) return '';
  const intVal = Number.parseInt(normalized, 16);
  const r = (intVal >> 16) & 255;
  const g = (intVal >> 8) & 255;
  const b = intVal & 255;
  const a = Math.max(0, Math.min(1, Number(alpha || 1)));
  return `rgba(${r}, ${g}, ${b}, ${a})`;
}

function _getActorBubbleColor(actorKey) {
  const key = String(actorKey || '').trim().toLowerCase();
  if (!key) return '';
  return String((window.__fridaysActorBubbleColors || {})[key] || '').trim();
}

function _saveActorBubbleColors() {
  localStorage.setItem(CHAT_ACTOR_BUBBLE_COLORS_KEY, JSON.stringify(window.__fridaysActorBubbleColors || {}));
}

function applyBubbleColorOverrideToNode(node) {
  if (!node) return;
  const className = String(node.className || '');
  const m = className.match(/\bsender-([a-z0-9_-]+)\b/);
  const key = m ? m[1] : '';
  const color = _getActorBubbleColor(key);
  if (!color) {
    node.style.removeProperty('background');
    node.style.removeProperty('border-color');
    return;
  }
  const bg = _hexToRgba(color, 0.14);
  const border = _hexToRgba(color, 0.36);
  if (bg) node.style.background = bg;
  if (border) node.style.borderColor = border;
}

function _applyBubbleColorOverrides() {
  document.querySelectorAll('.chat-bubble').forEach(applyBubbleColorOverrideToNode);
}

function setActorBubbleColor(actorKey, colorValue) {
  const key = String(actorKey || '').trim().toLowerCase();
  if (!key) return;
  const color = String(colorValue || '').trim();
  if (!/^#[0-9a-fA-F]{6}$/.test(color)) return;
  window.__fridaysActorBubbleColors = window.__fridaysActorBubbleColors || {};
  window.__fridaysActorBubbleColors[key] = color;
  _saveActorBubbleColors();
  _applyBubbleColorOverrides();
}

function _appendChatBubble(sender, text, opts = {}) {
  const messages = _chatMessagesEl();
  if (!messages) return;
  const isUser = sender === 'you';
  const senderIdentity = _chatAgentIdentity(sender);
  const senderKey = String((isUser ? 'you' : senderIdentity.key) || 'agent')
    .toLowerCase()
    .replace(/[^a-z0-9_-]/g, '');
  const bubble = document.createElement('div');
  bubble.className = 'chat-bubble' + (isUser ? ' user' : '') + ' sender-' + senderKey;
  const safeSender = _escapeHtml(sender);
  const senderMetaHtml = isUser ? 'you' : _chatAgentIdentityHtml(sender, true);
  const msgId = opts.msgId || (Date.now().toString(36) + Math.random().toString(36).slice(2, 7));
  const quotedItems = Array.isArray(opts.quoted)
    ? opts.quoted
    : (opts.quoted ? [opts.quoted] : []);
  const quoted = quotedItems.length
    ? `<div class="chat-meta">${quotedItems.map(q => `↳ replying to ${_escapeHtml(q.sender)}: ${_escapeHtml(q.preview)}`).join('<br>')}</div>`
    : '';
  const extracted = _extractAttachmentsFromMessage(text);
  const parsedSkill = isUser ? { text: extracted.text, events: [] } : _parseSkillEvents(extracted.text);
  const visibleText = parsedSkill.text || (parsedSkill.events.length ? 'Executed skill run(s):' : extracted.text);
  const bubbleAttachments = Array.isArray(opts.attachments) && opts.attachments.length ? opts.attachments : extracted.attachments;
  // User messages: plain escaped text. Agent messages: rendered markdown.
  const bodyHtml = isUser ? `<span style="white-space:pre-wrap;">${_escapeHtml(visibleText)}</span>` : _renderMarkdown(visibleText);
  const attachmentsHtml = _renderBubbleAttachments(bubbleAttachments);
  const eventsHtml = isUser ? '' : _renderSkillEvents(parsedSkill.events, sender);
  const relayCandidates = isUser ? [] : _extractAgentDirectedQuestions(visibleText, senderIdentity.key);
  // When Auto Relay is disabled, suppress relay buttons — agents should not route mid-task
  const relayButtonsHtml = (relayCandidates.length && window.__fridaysChatRelayAuto)
    ? `<div class="chat-handoff-actions">${relayCandidates.map(c => `<span class="chat-handoff-btn" role="button" tabindex="0" data-relay-from="${_escapeHtml(senderIdentity.key)}" data-relay-target="${_escapeHtml(c.target)}" data-relay-question="${_escapeHtml(_relayEncode(c.question))}" onclick="queueRelayHandoffFromButton(this)">Route to ${_escapeHtml(_chatAgentLabel(c.target))}</span>`).join('')}</div>`
    : '';
  // "Send to Duck" button — shown whenever an agent response mentions a proposal ID.
  // Works regardless of relay state so Ghost can always trigger Duck review manually.
  const _proposalIdMatch = !isUser && visibleText.match(/\b(INTERNAL-[A-Z]+-\d+)\b/);
  const duckRelayBtnHtml = (_proposalIdMatch && senderIdentity.key !== 'duck')
    ? `<div class="chat-handoff-actions"><span class="chat-handoff-btn" role="button" tabindex="0"
        onclick="sendProposalToDuck('${_escapeHtml(_proposalIdMatch[1])}', '${_escapeHtml(opts.conversationId || '')}')">
        <svg viewBox="0 0 16 16" width="11" height="11" fill="none" style="vertical-align:-1px;margin-right:2px;"><path d="M4 9.5c0 2 1.8 3 4 3s4-1 4-3c0-1.5-1-2.5-3-2.5H8c1 0 2-1 2-2S9 3 8 3C6.5 3 5.5 4 5.5 5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/><path d="M12 7.5l2 1" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg> Send ${_escapeHtml(_proposalIdMatch[1])} to Duck</span></div>`
    : '';
  const replayText = _escapeHtml(String(visibleText || '').replace(/\s+/g, ' ').trim().slice(0, 1800));
  const localText = _escapeHtml(String(opts.localPromptText || visibleText || '').slice(0, 4000));
  const selectedAgentsRaw = Array.isArray(opts.selectedAgents) ? opts.selectedAgents : [];
  const selectedAgentsCsv = _escapeHtml(selectedAgentsRaw.map(a => String(a || '').toLowerCase().trim()).filter(Boolean).join(','));
  const userActionRow = isUser
    ? `<div class="chat-actions">
      <button class="chat-action-btn" data-resend-text="${localText}" data-resend-agents="${selectedAgentsCsv}" onclick="resendUserMessage(this.dataset.resendText, this.dataset.resendAgents)">Resend</button>
      ${opts.editable && opts.messageId && opts.conversationId
        ? `<button class="chat-action-btn" onclick="editOwnPrompt(${Number(opts.conversationId)}, ${Number(opts.messageId)})">Change</button>
           <button class="chat-action-btn" onclick="deleteOwnPrompt(${Number(opts.conversationId)}, ${Number(opts.messageId)})">Delete</button>`
        : `<button class="chat-action-btn" data-revise-text="${localText}" onclick="revisePromptDraft(this.dataset.reviseText)">Change Text</button>`}
    </div>`
    : '';
  const actionRow = isUser ? userActionRow : `
    <div class="chat-actions">
      <button class="chat-action-btn" onclick="reactToMessage('${msgId}','👍')">👍</button>
      <button class="chat-action-btn" onclick="reactToMessage('${msgId}','🤔')">🤔</button>
      <button class="chat-action-btn" data-reply-sender="${safeSender}" data-reply-preview="${_escapeHtml(text).slice(0, 120)}" data-reply-msgid="${_escapeHtml(String(opts.messageId || ''))}" onclick="setReplyTarget(this.dataset.replySender, this.dataset.replyPreview, this.dataset.replyMsgid)">Reply</button>
      <button class="chat-action-btn" data-suggest-sender="${safeSender}" data-suggest-preview="${_escapeHtml(text).slice(0, 160)}" onclick="showAgentPickerDropdown(this, this.dataset.suggestSender, this.dataset.suggestPreview)">Ask another</button>
      <button class="chat-action-btn" data-agent="${_escapeHtml(senderIdentity.key)}" data-text="${replayText}" data-msgid="${_escapeHtml(String(msgId))}" onclick="reprocessAgentMessage(this.dataset.agent, this.dataset.text, this.dataset.msgid)">Reprocess</button>
      ${opts.messageId && opts.conversationId
        ? `<button class="chat-action-btn" onclick="deleteChatMessage(${Number(opts.conversationId)}, ${Number(opts.messageId)})">Delete</button>`
        : ''}
    </div>`;

  const _now = new Date();
  const _tsTime = _now.toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit', hour12: true });
  const _tsDate = _now.toLocaleDateString('en-AU', { day: 'numeric', month: 'short' });
  const _tsToday = new Date().toDateString() === _now.toDateString();
  const _tsLabel = _tsTime + (_tsToday ? '' : ' · ' + _tsDate);
  const _tokCount = !isUser ? (Number(opts.tokens || 0).toLocaleString() + ' tok') : '';
  const _traceItems = (!isUser && Array.isArray(opts.stageTrace) && opts.stageTrace.length) ? opts.stageTrace : null;
  const traceHtml = _traceItems
    ? `<details class="chat-bubble-trace"><summary>Trace &middot; ${_traceItems.length} step${_traceItems.length !== 1 ? 's' : ''}</summary><div class="chat-bubble-trace-body">${_traceItems.map((s, i) => `<div class="chat-bubble-trace-step"><span class="chat-bubble-trace-num">${i + 1}</span><span class="chat-bubble-trace-text">${_escapeHtml(String(s && s.text != null ? s.text : s))}</span></div>`).join('')}</div></details>`
    : '';

  // ── Paid agent session tracker ──────────────────────────────────────────
  const _PAID_AGENT_KEYS = new Set(['nine','ten','eleven','twelve','thirteen']);
  const isPaidAgent = _PAID_AGENT_KEYS.has(senderKey);
  const sessionState = (!isUser && isPaidAgent) ? _detectUnfinishedAgentAction(visibleText) : { unfinished: false };
  const sessionBarHtml = sessionState.unfinished ? _renderAgentSessionBar(senderKey, sessionState.tasks, sessionState.prompt) : '';

  bubble.innerHTML = `
    <div class="chat-meta ${isUser ? '' : 'icon-meta'}" style="display:flex;align-items:center;gap:8px;">
      <span>${senderMetaHtml}</span>
      <span style="font-size:9px;color:var(--text-dim);opacity:0.7;margin-left:auto;white-space:nowrap;">${_tokCount ? `<span style="opacity:0.55;margin-right:5px;">${_escapeHtml(_tokCount)}</span>` : ''}${_tsLabel}${!isUser && Number(opts.chainDepth) > 0 ? `<span class="chat-bubble-chain-badge" title="Relay chain: ${Number(opts.chainDepth)} hop${Number(opts.chainDepth) !== 1 ? 's' : ''} remaining">\u26d3${Number(opts.chainDepth)}</span>` : ''}</span>
    </div>
    ${quoted}
    <div class="chat-text">${bodyHtml}</div>
    ${attachmentsHtml}
    ${eventsHtml}
    ${sessionBarHtml}
    ${relayButtonsHtml}
    ${duckRelayBtnHtml}
    ${traceHtml}
    ${actionRow}
  `;

  bubble.dataset.msgId = msgId;
  bubble.dataset.sender = senderKey;
  bubble.dataset.tokens = String(Number(opts.tokens || 0));
  bubble.dataset.chainDepth = String(Number.isFinite(Number(opts.chainDepth)) ? Number(opts.chainDepth) : -1);
  bubble.id = 'chat-bubble-' + String(msgId).replace(/[^a-zA-Z0-9_-]/g, '');
  if (opts.messageId) bubble.dataset.messageId = String(opts.messageId);
  if (opts.conversationId) bubble.dataset.conversationId = String(opts.conversationId);
  applyBubbleColorOverrideToNode(bubble);
  messages.appendChild(bubble);
  if (!isUser && relayCandidates.length && window.__fridaysChatRelayAuto && !opts.fromHistory && Number(opts.tokens || 0) > 0) {
    // If this bubble is itself a relay response, propagate chain depth (decrement by 1).
    // For direct user→agent responses (no chainDepth), assign the initial chain depth.
    const _parentDepth = Number.isFinite(Number(opts.chainDepth)) ? Number(opts.chainDepth) : -1;
    const _outDepth = _parentDepth >= 0
      ? Math.max(0, _parentDepth - 1)
      : Math.min(3, Math.max(1, Number(window.__fridaysChatRelayMaxPerTurn || 2)));
    relayCandidates.forEach(c => {
      if (!_isAutoRelayTargetEnabled(c.target)) return;
      queueRelayHandoff({ from: senderIdentity.key, target: c.target, question: c.question, chainDepth: _outDepth }, true);
    });
  }
  // Librarian review — fires async/debounced to catch implicit handoffs the regex missed.
  // Only runs when auto-relay is on, fresh (non-history) agent bubble, non-zero tokens,
  // AND the regex found no explicit relay candidates (librarian is the fallback, not a supplement),
  // AND this is not a relay chain response (chainDepth < 0 = initial direct response only).
  if (!isUser && window.__fridaysChatRelayAuto && !opts.fromHistory && Number(opts.tokens || 0) > 0 && relayCandidates.length === 0 && Number(opts.chainDepth ?? -1) < 0) {
    _librarianReviewDebounced(visibleText, senderIdentity.key, opts.conversationId || null);
  }
  _recordTimelineEvent({
    bubbleId: bubble.id,
    sender: senderKey,
    label: _chatAgentLabel(senderKey),
    text: visibleText,
    relay: !!(opts.relayMeta || /^\[Relay\s/i.test(String(visibleText || ''))),
  });
  _applyReplyTargetHighlights();
  messages.scrollTop = messages.scrollHeight;
}

async function editOwnPrompt(convId, msgId) {
  const currentBubble = document.querySelector(`[data-message-id="${msgId}"] .chat-text`);
  const currentText = currentBubble ? currentBubble.textContent : '';
  const edited = prompt('Edit your prompt:', currentText || '');
  if (edited === null) return;
  const nextText = String(edited || '').trim();
  if (!nextText) {
    showToast('Prompt cannot be empty', 'error');
    return;
  }
  if (nextText === String(currentText || '').trim()) {
    showToast('No changes detected', 'info');
    return;
  }
  try {
    const resp = await fetch(`/api/conversations/${convId}/messages/${msgId}`, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ content: nextText })
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok || !data.ok) {
      throw new Error((data && data.error) || `HTTP ${resp.status}`);
    }
    showToast('Prompt updated', 'success');
    loadConversationMessages(convId);
  } catch (e) {
    showToast('Failed to update prompt: ' + (e.message || e), 'error');
  }
}

function revisePromptDraft(text) {
  const input = document.getElementById('question-input');
  if (!input) return;
  input.value = String(text || '').trim();
  input.focus();
  input.setSelectionRange(input.value.length, input.value.length);
  showToast('Prompt loaded for correction. Edit and send again.', 'info');
}

async function deleteOwnPrompt(convId, msgId) {
  return deleteChatMessage(convId, msgId);
}

async function deleteChatMessage(convId, msgId) {
  try {
    const resp = await fetch(`/api/conversations/${convId}/messages/${msgId}`, {
      method: 'DELETE',
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok || !data.ok) {
      throw new Error((data && data.error) || `HTTP ${resp.status}`);
    }
    showToast('Message deleted', 'success');
    loadConversationMessages(convId);
    refreshChatThreadList(convId);
  } catch (e) {
    showToast('Failed to delete message: ' + (e.message || e), 'error');
  }
}

function reactToMessage(msgId, emoji) {
  const el = document.querySelector('[data-msg-id="' + msgId + '"] .chat-actions');
  if (!el) return;
  const badge = document.createElement('span');
  badge.className = 'chat-action-btn';
  badge.textContent = emoji;
  badge.style.cursor = 'default';
  el.appendChild(badge);
}

function resendUserMessage(previousText, targetAgentsCsv = '') {
  const seed = String(previousText || '').trim();
  if (!seed) {
    showToast('No message text available to resend', 'error');
    return;
  }
  const input = document.getElementById('question-input');
  if (!input) return;
  input.value = seed;

  const targetAgents = String(targetAgentsCsv || '')
    .split(',')
    .map(a => String(a || '').trim().toLowerCase())
    .filter(a => a && _isKnownChatAgent(a));
  if (targetAgents.length) {
    window.__fridaysChatEnabledAgents = window.__fridaysChatEnabledAgents || {};
    Object.keys(window.__fridaysChatEnabledAgents).forEach(k => {
      window.__fridaysChatEnabledAgents[k] = targetAgents.includes(k);
    });
    persistThreadAgentSelection();
    renderChatAgentToggles();
    updateComposerMeta();
    updateChatStatusPills();
  }

  input.focus();
  input.setSelectionRange(input.value.length, input.value.length);
  sendMessage('user');
}

function reprocessAgentMessage(agentKey, previousText, bubbleMsgId = '') {
  const target = String(agentKey || '').toLowerCase().trim();
  if (!target || !_isKnownChatAgent(target)) {
    showToast('Cannot reprocess: unknown agent', 'error');
    return;
  }
  const input = document.getElementById('question-input');
  if (!input) return;
  const seed = String(previousText || '').trim();
  if (!seed) {
    showToast('No previous message text available to reprocess', 'error');
    return;
  }

  input.value = `Reprocess and replace your previous answer using latest context. Keep it concise and corrected.\n\nPrevious answer:\n${seed}`;
  window.__fridaysReplaceBubbleId = String(bubbleMsgId || '');
  window.__fridaysReplaceAgentKey = target;

  window.__fridaysChatEnabledAgents = window.__fridaysChatEnabledAgents || {};
  Object.keys(window.__fridaysChatEnabledAgents).forEach(k => {
    window.__fridaysChatEnabledAgents[k] = (k === target);
  });
  persistThreadAgentSelection();
  renderChatAgentToggles();
  updateComposerMeta();
  updateChatStatusPills();

  input.focus();
  input.setSelectionRange(input.value.length, input.value.length);
  sendMessage('user');
}

function _applyReplyTargetHighlights() {
  document.querySelectorAll('.chat-bubble.reply-targeted').forEach(n => n.classList.remove('reply-targeted'));
  const targets = Array.isArray(window.__fridaysReplyTargets) ? window.__fridaysReplyTargets : [];
  targets.forEach(t => {
    const msgId = String(t && t.messageId || '').trim();
    if (!msgId) return;
    const node = document.querySelector('.chat-bubble[data-message-id="' + msgId + '"]');
    if (node) node.classList.add('reply-targeted');
  });
}

function setReplyTarget(sender, preview, messageId) {
  const normalizedSender = String(sender || 'agent').toLowerCase().trim();
  const trimmedPreview = String(preview || '').replace(/\s+/g, ' ').trim().slice(0, 180);
  const normalizedMsgId = String(messageId || '').trim();
  if (!trimmedPreview) return;

  const next = Array.isArray(window.__fridaysReplyTargets) ? window.__fridaysReplyTargets.slice() : [];
  const existingIdx = next.findIndex(t => t && t.sender === normalizedSender && t.preview === trimmedPreview && String(t.messageId || '') === normalizedMsgId);
  const target = { sender: normalizedSender, preview: trimmedPreview, messageId: normalizedMsgId };
  if (existingIdx >= 0) next.splice(existingIdx, 1);
  next.push(target);
  window.__fridaysReplyTargets = next;

  const senderTargets = new Set(
    next
      .map(t => String(t && t.sender || '').toLowerCase())
      .filter(s => Object.prototype.hasOwnProperty.call(window.__fridaysChatEnabledAgents || {}, s))
  );
  if (senderTargets.size) {
    const allAgentKeys = Object.keys(window.__fridaysChatEnabledAgents || {});
    allAgentKeys.forEach(k => {
      window.__fridaysChatEnabledAgents[k] = senderTargets.has(k);
    });
    persistThreadAgentSelection();
    renderChatAgentToggles();
    updateComposerMeta();
    updateChatStatusPills();
  }

  const input = document.getElementById('question-input');
  if (input && !String(input.value || '').trim()) {
    const tags = next.map(t => '@' + _chatAgentLabel(t.sender)).join(' ');
    const quotes = next.map(t => `> [${_chatAgentLabel(t.sender)}] ${t.preview}`).join('\n');
    input.value = `${tags}\n${quotes}\n\n`;
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);
  }

  renderReplyBanner();
  _applyReplyTargetHighlights();
  updateChatSpellHelper();
}

function clearReplyTarget() {
  window.__fridaysReplyTargets = [];
  renderReplyBanner();
  _applyReplyTargetHighlights();
}

function clearReplyTargetAt(index) {
  const idx = Number(index);
  if (!Number.isFinite(idx) || idx < 0) return;
  const next = Array.isArray(window.__fridaysReplyTargets) ? window.__fridaysReplyTargets.slice() : [];
  if (idx >= next.length) return;
  next.splice(idx, 1);
  window.__fridaysReplyTargets = next;
  renderReplyBanner();
  _applyReplyTargetHighlights();
}

function renderReplyBanner() {
  const wrapper = document.getElementById('input-wrapper');
  if (!wrapper) return;
  let banner = document.getElementById('chat-reply-banner');
  if (!banner) {
    banner = document.createElement('div');
    banner.id = 'chat-reply-banner';
    banner.className = 'reply-banner';
    wrapper.prepend(banner);
  }
  const targets = Array.isArray(window.__fridaysReplyTargets) ? window.__fridaysReplyTargets : [];
  if (!targets.length) {
    banner.style.display = 'none';
    return;
  }
  banner.style.display = 'flex';
  const targetNames = Array.from(new Set(targets.map(t => _chatAgentLabel(t.sender))));
  banner.innerHTML = `
    <span>Replying to <strong>${targets.length}</strong> message(s) · ${_escapeHtml(targetNames.join(', '))}</span>
    <span style="display:inline-flex;align-items:center;gap:4px;flex-wrap:wrap;">
      ${targets.map((t, idx) => `<span style="display:inline-flex;align-items:center;gap:4px;padding:2px 6px;border:1px solid var(--border);border-radius:999px;font-size:10px;max-width:240px;">
        <span style="white-space:nowrap;color:var(--text-dim);">${_escapeHtml(_chatAgentLabel(t.sender))}:</span>
        <span style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:140px;">${_escapeHtml(t.preview)}</span>
        <button class="reply-clear-btn" style="padding:0 4px;line-height:1.2;" onclick="clearReplyTargetAt(${idx})">x</button>
      </span>`).join('')}
    </span>
    <button class="reply-clear-btn" onclick="clearReplyTarget()">Clear all</button>
  `;
}

function showAgentPickerDropdown(triggerBtn, sender, preview) {
  const existing = document.getElementById('ask-another-picker');
  if (existing) { existing.remove(); return; }

  const picker = document.createElement('div');
  picker.id = 'ask-another-picker';
  picker.style.cssText = 'position:fixed;z-index:9100;background:var(--bg-card,#1e1e2e);border:1px solid var(--border,#444);border-radius:8px;box-shadow:0 4px 20px rgba(0,0,0,0.55);min-width:190px;padding:6px 0;font-size:13px;';

  const rect = triggerBtn.getBoundingClientRect();
  picker.style.top = Math.min(rect.bottom + 4, window.innerHeight - 280) + 'px';
  picker.style.left = Math.min(rect.left, window.innerWidth - 200) + 'px';

  const normalized = String(sender || '').toLowerCase();
  const sourceLabel = _chatAgentLabel(normalized);
  const selected = new Set();

  const header = document.createElement('div');
  header.style.cssText = 'padding:7px 13px 6px;font-size:11px;color:var(--text-dim);border-bottom:1px solid var(--border,#333);margin-bottom:3px;';
  header.innerHTML = `Ask another agent <span style="opacity:0.55;font-size:10px;">(Ctrl+click = multi)</span>`;
  picker.appendChild(header);

  CHAT_AGENT_OPTIONS.forEach(agent => {
    if (agent.value === normalized) return;
    const item = document.createElement('div');
    item.style.cssText = 'padding:7px 13px;cursor:pointer;display:flex;align-items:center;gap:8px;';
    item.dataset.agentValue = agent.value;

    const check = document.createElement('input');
    check.type = 'checkbox';
    check.style.pointerEvents = 'none';
    check.style.accentColor = 'var(--accent,#7c3aed)';

    const lbl = document.createElement('span');
    lbl.textContent = agent.label;
    lbl.style.flex = '1';

    item.appendChild(check);
    item.appendChild(lbl);

    const updateStyle = () => {
      item.style.background = selected.has(agent.value) ? 'var(--bg-hover,rgba(122,80,220,0.15))' : '';
    };
    item.addEventListener('mouseenter', () => { if (!selected.has(agent.value)) item.style.background = 'var(--bg-hover,rgba(255,255,255,0.06))'; });
    item.addEventListener('mouseleave', updateStyle);

    item.addEventListener('click', (e) => {
      if (e.ctrlKey || e.metaKey) {
        if (selected.has(agent.value)) { selected.delete(agent.value); check.checked = false; }
        else { selected.add(agent.value); check.checked = true; }
        updateStyle();
      } else {
        _applyAskAnotherAgents([agent.value], normalized, preview);
        picker.remove();
        document.removeEventListener('mousedown', outsideClick, true);
      }
    });
    picker.appendChild(item);
  });

  const confirmBtn = document.createElement('button');
  confirmBtn.textContent = 'Ask selected';
  confirmBtn.style.cssText = 'display:block;width:calc(100% - 24px);margin:8px 12px 6px;padding:6px 10px;background:var(--accent,#7c3aed);color:#fff;border:none;border-radius:5px;cursor:pointer;font-size:12px;font-weight:600;';
  confirmBtn.addEventListener('click', () => {
    if (selected.size === 0) { showToast('Pick at least one agent', 'warning'); return; }
    _applyAskAnotherAgents([...selected], normalized, preview);
    picker.remove();
    document.removeEventListener('mousedown', outsideClick, true);
  });
  picker.appendChild(confirmBtn);

  document.body.appendChild(picker);

  function outsideClick(e) {
    if (!picker.contains(e.target) && e.target !== triggerBtn) {
      picker.remove();
      document.removeEventListener('mousedown', outsideClick, true);
    }
  }
  document.addEventListener('mousedown', outsideClick, true);
}

function _applyAskAnotherAgents(agentValues, senderKey, preview) {
  const sourceLabel = _chatAgentLabel(String(senderKey || ''));
  agentValues.forEach(agentKey => {
    const checkbox = document.querySelector('.chat-agent-toggle[value="' + agentKey + '"]');
    if (checkbox) {
      checkbox.checked = true;
      if (window.__fridaysChatEnabledAgents) window.__fridaysChatEnabledAgents[agentKey] = true;
    }
  });
  persistThreadAgentSelection();
  renderChatAgentToggles();
  updateComposerMeta();
  updateChatStatusPills();

  const targetLabels = agentValues.map(v => _chatAgentLabel(v)).join(' & ');
  const input = document.getElementById('question-input');
  if (input && !input.value.trim()) {
    if (agentValues.length === 1) {
      input.value = `[Thought from ${sourceLabel}] ${String(preview || '').slice(0, 130)}\n\n${_chatAgentLabel(agentValues[0])}, what is your take?`;
    } else {
      const names = agentValues.map(v => _chatAgentLabel(v)).join(', ');
      input.value = `[Thought from ${sourceLabel}] ${String(preview || '').slice(0, 130)}\n\n${names} — what are your takes?`;
    }
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);
  }
  showToast('Asking ' + targetLabels, 'info');
}

function _getLatencyProfile() {
  const defaults = {
    gemma: 16000,
    llama: 11000,
    qwen: 18000,
    duck: 8000,
    sniffles: 32000,
    nine: 14000,
    ten: 14000,
    eleven: 14000,
    twelve: 14000,
    librarian: 10000
  };
  try {
    const saved = JSON.parse(localStorage.getItem('fridays-agent-latency-ms') || '{}');
    return { ...defaults, ...saved };
  } catch (_) {
    return defaults;
  }
}

function _saveLatencyProfile(profile) {
  localStorage.setItem('fridays-agent-latency-ms', JSON.stringify(profile));
}

function _estimateBatchMs(agents) {
  const profile = _getLatencyProfile();
  const perAgent = agents.map(a => Number(profile[a] || 14000));
  const peak = perAgent.length ? Math.max(...perAgent) : 12000;
  return Math.max(4000, peak + 1200);
}

function _createLoadingPanel(agents) {
  // Runtime status now displays in thread runtime panel instead of in-chat
  // Store agents to display with loading/initializing state
  window.__fridaysRuntimeLoadingAgents = Array.isArray(agents) ? agents.slice() : [];
  
  // Trigger thread runtime panel to show loading indicators
  const host = document.querySelector('[id="chat-thread-runtime"]');
  if (host) {
    const snapshotJobs = (window.__fridaysThreadRuntimeSnapshot && window.__fridaysThreadRuntimeSnapshot.jobs) || [];
    _renderThreadRuntimePanel(snapshotJobs, 'send');
    _updateThreadRuntimeLoading();
    // Note: host.classList.add('open') removed — display:block !important in CSS, open class is redundant
  }
  
  // Return a detached dummy div for API compatibility with _startLoadingTicker.
  // Do NOT return the real host element — _startLoadingTicker.stop() calls panel.remove(),
  // which would permanently delete #chat-thread-runtime from the DOM.
  return document.createElement('div');
}

function _startLoadingTicker(panel, agents, estimateMs) {
  if (!panel) return { stop: () => {} };
  const shared = window.__fridaysSharedLoadingState || {
    timer: null,
    started: Date.now(),
    activeRequests: 0,
    perAgentTargetMs: {},
  };
  window.__fridaysSharedLoadingState = shared;
  shared.activeRequests += 1;
  shared.started = shared.started || Date.now();
  const etaEl = panel.querySelector('#chat-progress-eta');
  const headEl = panel.querySelector('#chat-progress-head');
  let stickyPending = false;
  agents.forEach(a => {
    shared.perAgentTargetMs[a] = Math.max(1000, Number(shared.perAgentTargetMs[a] || estimateMs || 12000));
  });
  if (!shared.timer) {
    shared.timer = setInterval(() => {
      const elapsed = Date.now() - shared.started;
      Object.keys(shared.perAgentTargetMs || {}).forEach(a => {
        const target = Math.max(1000, Number(shared.perAgentTargetMs[a] || estimateMs || 12000));
        const pct = Math.min(95, Math.max(4, Math.floor((elapsed / target) * 100)));
        const fill = panel.querySelector('[data-fill="' + a + '"]');
        if (fill) fill.style.width = pct + '%';
      });
      const etaMs = Math.max(0, Number(estimateMs || 12000) - elapsed);
      if (etaEl) {
        etaEl.textContent = stickyPending
          ? 'Still running. Tracking live model progress...'
          : ('ETA ~ ' + (etaMs / 1000).toFixed(1) + 's');
      }
      if (headEl && !stickyPending) headEl.textContent = 'Waiting for agent acknowledgement...';
    }, 140);
  }

  const ctl = {
    _stopped: false,
    setPending: (jobs) => {
      stickyPending = true;
      if (headEl) headEl.textContent = 'Long-running response detected. Live stage updates enabled.';
      if (Array.isArray(jobs)) {
        jobs.forEach(j => {
          if (!j || !j.agent) return;
          const etaSeconds = Number(j.eta_seconds || 0);
          if (etaSeconds > 0) shared.perAgentTargetMs[j.agent] = etaSeconds * 1000;
          const state = panel.querySelector('[data-state="' + j.agent + '"]');
          if (state) {
            const runtimeClass = j.runtime_class ? ('[' + j.runtime_class + '] ') : '';
            const etaSuffix = etaSeconds > 0 ? (' · ETA ~' + etaSeconds + 's') : '';
            state.textContent = 'alive · ' + runtimeClass + (j.stage || 'running') + etaSuffix;
          }
          const fill = panel.querySelector('[data-fill="' + j.agent + '"]');
          if (fill) fill.style.width = '96%';
        });
      }
    },
    updateJobs: (jobs) => {
      if (!Array.isArray(jobs)) return;
      let running = 0;
      jobs.forEach(j => {
        if (!j || !j.agent) return;
        const etaRemaining = Number(j.eta_remaining_seconds || 0);
        const etaSeconds = Number(j.eta_seconds || 0);
        if (etaSeconds > 0) shared.perAgentTargetMs[j.agent] = etaSeconds * 1000;
        const state = panel.querySelector('[data-state="' + j.agent + '"]');
        if (state) {
          const runtimeClass = j.runtime_class ? ('[' + j.runtime_class + '] ') : '';
          if (j.status === 'completed') state.textContent = 'alive · completed';
          else if (j.status === 'failed') state.textContent = 'alive · failed';
          else {
            const etaSuffix = etaRemaining > 0 ? (' · ~' + etaRemaining + 's left') : '';
            state.textContent = 'alive · ' + runtimeClass + (j.stage || j.status || 'running') + etaSuffix;
          }
        }
        const fill = panel.querySelector('[data-fill="' + j.agent + '"]');
        if (!fill) return;
        if (j.status === 'completed') {
          fill.style.width = '100%';
        } else if (j.status === 'failed') {
          fill.style.width = '100%';
          fill.style.background = '#f44336';
        } else {
          running += 1;
          const target = Math.max(1000, Number(shared.perAgentTargetMs[j.agent] || estimateMs || 12000));
          const pct = Math.min(98, Math.max(35, Math.floor((Number(j.elapsed_ms || 0) / target) * 100)));
          fill.style.width = pct + '%';
        }
      });
      if (headEl) {
        headEl.textContent = running > 0
          ? ('Model still working (' + running + ' active) — keeping context alive...')
          : 'Model run complete.';
      }
      if (etaEl && running > 0) {
        const runningEtas = jobs
          .filter(j => (j.status || 'running') === 'running')
          .map(j => Number(j.eta_remaining_seconds || 0))
          .filter(v => Number.isFinite(v) && v > 0);
        if (runningEtas.length) {
          etaEl.textContent = 'Running in background. Next completions ~' + Math.min(...runningEtas) + 's';
        } else {
          etaEl.textContent = 'Running in background. Waiting for final answer...';
        }
      }
    },
    stop: (responses) => {
      if (ctl._stopped) return;
      ctl._stopped = true;
      shared.activeRequests = Math.max(0, Number(shared.activeRequests || 0) - 1);
      if (Array.isArray(responses)) {
        const profile = _getLatencyProfile();
        responses.forEach(r => {
          const ms = Number(r && r.elapsed_ms);
          if (!Number.isFinite(ms) || ms <= 0) return;
          const prev = Number(profile[r.agent] || ms);
          profile[r.agent] = Math.round(prev * 0.65 + ms * 0.35);
        });
        _saveLatencyProfile(profile);
      }
      if (shared.activeRequests > 0 || (window.__fridaysChatPendingJobIds || []).length) {
        if (headEl) headEl.textContent = 'Waiting for remaining request(s)...';
        return;
      }
      if (shared.timer) {
        clearInterval(shared.timer);
      }
      shared.timer = null;
      shared.started = Date.now();
      shared.perAgentTargetMs = {};
      window.__fridaysRuntimeLoadingAgents = [];
      if (etaEl) etaEl.textContent = 'Completed';
      setTimeout(() => panel.remove(), 320);
    }
  };

  return ctl;
}

function _pollPendingChatJobs(conversationId, jobIds, loadingCtl) {
  if (!conversationId || !Array.isArray(jobIds) || !jobIds.length) return;
  const sameConv = Number(window.__fridaysChatPendingConversationId || 0) === Number(conversationId || 0);
  if (!sameConv && window.__fridaysChatPendingPollTimer) {
    clearInterval(window.__fridaysChatPendingPollTimer);
    window.__fridaysChatPendingPollTimer = null;
    window.__fridaysChatPendingJobIds = [];
    window.__fridaysChatPendingLoadCtls = [];
  }
  window.__fridaysChatPendingConversationId = conversationId;
  const merged = Array.from(new Set([...(window.__fridaysChatPendingJobIds || []), ...jobIds]));
  window.__fridaysChatPendingJobIds = merged;
  window.__fridaysChatPendingLoadCtls = Array.isArray(window.__fridaysChatPendingLoadCtls) ? window.__fridaysChatPendingLoadCtls : [];
  if (loadingCtl && !window.__fridaysChatPendingLoadCtls.includes(loadingCtl)) {
    window.__fridaysChatPendingLoadCtls.push(loadingCtl);
  }
  if (window.__fridaysChatPendingPollTimer) return;

  let ticks = 0;
  const maxTicks = 180; // ~6 minutes at 2s interval
  const timer = setInterval(() => {
    ticks += 1;
    const ids = (window.__fridaysChatPendingJobIds || []).slice();
    if (!ids.length) return;
    const q = encodeURIComponent(ids.join(','));
    fetch('/api/chat/jobs/status?conversation_id=' + encodeURIComponent(conversationId) + '&job_ids=' + q)
      .then(r => r.json())
      .then(data => {
        const jobs = (data && Array.isArray(data.jobs)) ? data.jobs : [];
        (window.__fridaysChatPendingLoadCtls || []).forEach(ctl => {
          try { ctl.updateJobs(jobs); } catch (_) {}
        });
        _renderThreadRuntimePanel(jobs, 'live');
        _syncThinkingBubbles(jobs);
        const done = jobs.every(j => j.status === 'completed' || j.status === 'failed' || j.status === 'cancelled');
        if (done || ticks >= maxTicks) {
          clearInterval(timer);
          if (window.__fridaysChatPendingPollTimer === timer) {
            window.__fridaysChatPendingPollTimer = null;
            window.__fridaysChatPendingJobIds = [];
            window.__fridaysChatPendingConversationId = null;
            const loadCtls = (window.__fridaysChatPendingLoadCtls || []).slice();
            window.__fridaysChatPendingLoadCtls = [];
            loadCtls.forEach(ctl => {
              try { ctl.stop([]); } catch (_) {}
            });
          }
          // Extract relay candidates from completed async responses.
          // `_appendChatBubble` uses fromHistory:true for loaded history so the relay
          // auto-fire guard is skipped; process relay here before the history reload.
          const completedNow = jobs.filter(j => j.status === 'completed');
          // Store stage traces so renderChatMessages can inject them into the freshly-loaded bubbles.
          if (completedNow.length) {
            window.__fridaysPendingBubbleTraces = window.__fridaysPendingBubbleTraces || {};
            completedNow.forEach(j => {
              const tr = j.stage_trace;
              if (Array.isArray(tr) && tr.length) {
                window.__fridaysPendingBubbleTraces[String(j.agent || '').toLowerCase()] = tr;
              }
            });
          }
          if (completedNow.length && window.__fridaysChatRelayAuto) {
            // Budget may be 0 if the page was loaded/refreshed while the job was
            // running — the user's original sendMessage() never set it this session.
            // Re-initialise so the relay chain can fire from this async completion.
            if (Number(window.__fridaysChatRelayBudget || 0) === 0) {
              const asyncRelayCfg = _chatRelayConfig();
              window.__fridaysChatRelayBudget = asyncRelayCfg.infinite ? -1 : asyncRelayCfg.maxPerTurn;
            }
            fetch('/api/conversations/' + conversationId + '/messages')
              .then(r => r.json())
              .then(d => {
                const rows = (d && Array.isArray(d.messages)) ? d.messages : [];
                const agentRows = rows.filter(r => r.sender && r.sender !== 'user' && r.message_type === 'response');
                agentRows.slice(-completedNow.length).forEach(row => {
                  const from = String(row.sender || '').toLowerCase();
                  _extractAgentDirectedQuestions(String(row.content || ''), from).forEach(c => {
                    queueRelayHandoff({ from: c.from, target: c.target, question: c.question }, true);
                  });
                });
              })
              .catch(() => {});
          }
          loadConversationMessages(conversationId);
          refreshChatThreadList(conversationId);
          window.__fridaysRuntimeLoadingAgents = [];
          pollActiveThreadRuntime(true);
          const failed = jobs.filter(j => j.status === 'failed');
          const cancelled = jobs.filter(j => j.status === 'cancelled');
          if (failed.length) {
            let failMsg;
            if (failed.length === 1) {
              const who = _chatAgentLabel(failed[0].agent || 'agent');
              const why = String(failed[0].error || '').trim();
              failMsg = why ? `${who} failed — ${why}` : `${who} failed (check logs for details)`;
            } else {
              const parts = failed.map(j => {
                const who = _chatAgentLabel(j.agent || 'agent');
                const why = String(j.error || '').trim();
                return why ? `${who}: ${why}` : who;
              });
              failMsg = `${failed.length} agents failed — ${parts.join('; ')}`;
            }
            _appendChatBubble('system', failMsg);
            notifyDesktop('Fridays Chat', `${failed.length} long-running response(s) failed.`, {
              tag: 'fridays-chat-status-' + String(conversationId || 'none')
            });
          } else if (cancelled.length) {
            notifyDesktop('Fridays Chat', `${cancelled.length} run(s) were cancelled.`, {
              tag: 'fridays-chat-status-' + String(conversationId || 'none')
            });
          } else {
            notifyDesktop('Fridays Chat', 'Background agent response completed.', {
              tag: 'fridays-chat-status-' + String(conversationId || 'none')
            });
          }
        }
      })
      .catch(() => {
        if (ticks >= maxTicks) {
          clearInterval(timer);
          if (window.__fridaysChatPendingPollTimer === timer) {
            window.__fridaysChatPendingPollTimer = null;
            window.__fridaysChatPendingJobIds = [];
            window.__fridaysChatPendingConversationId = null;
            const loadCtls = (window.__fridaysChatPendingLoadCtls || []).slice();
            window.__fridaysChatPendingLoadCtls = [];
            loadCtls.forEach(ctl => {
              try { ctl.stop([]); } catch (_) {}
            });
          }
          _appendChatBubble('system', 'Stopped waiting for background response status (timeout).');
          window.__fridaysRuntimeLoadingAgents = [];
          pollActiveThreadRuntime(true);
          notifyDesktop('Fridays Chat', 'Background run timed out while polling status.', {
            tag: 'fridays-chat-timeout-' + String(conversationId || 'none')
          });
        }
      });
  }, 2000);
  window.__fridaysChatPendingPollTimer = timer;
}

async function stopPendingAgents() {
  const runtimeJobs = Array.isArray(window.__fridaysThreadRuntimeSnapshot?.jobs)
    ? window.__fridaysThreadRuntimeSnapshot.jobs
    : [];
  const runtimeRunningIds = runtimeJobs
    .filter(j => String(j?.status || 'running') === 'running' && j?.job_id)
    .map(j => String(j.job_id));
  const jobIds = Array.from(new Set([...(window.__fridaysChatPendingJobIds || []).slice(), ...runtimeRunningIds]));
  const convId = window.__fridaysChatPendingConversationId || window.__fridaysChatConversationId;
  if (!jobIds.length) {
    showToast('No long-running agents to stop right now', 'info');
    return;
  }
  try {
    const resp = await fetch('/api/chat/jobs/cancel', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ job_ids: jobIds, conversation_id: convId || null, hard_kill: true })
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok || !data.ok) {
      throw new Error((data && data.error) || `HTTP ${resp.status}`);
    }
    const count = Number(data.count || 0);
    const hardKills = Array.isArray(data.hard_kill_results) ? data.hard_kill_results : [];
    const hardKillOk = hardKills.filter(item => item && item.ok).length;
    const suffix = hardKillOk > 0 ? ` · hard-killed ${hardKillOk} local runtime${hardKillOk === 1 ? '' : 's'}` : '';
    showToast(count > 0 ? `Stopped ${count} agent run(s)${suffix}` : 'No running jobs were stoppable', count > 0 ? 'success' : 'info');
    if (window.__fridaysChatPendingPollTimer) {
      clearInterval(window.__fridaysChatPendingPollTimer);
      window.__fridaysChatPendingPollTimer = null;
    }
    const loadCtls = (window.__fridaysChatPendingLoadCtls || []).slice();
    window.__fridaysChatPendingLoadCtls = [];
    loadCtls.forEach(ctl => {
      try { ctl.stop([]); } catch (_) {}
    });
    window.__fridaysChatPendingJobIds = [];
    window.__fridaysChatPendingConversationId = null;
    window.__fridaysRuntimeLoadingAgents = [];
    _syncThinkingBubbles([]);
    _renderThreadRuntimePanel([], 'stopped');
    if (convId) {
      loadConversationMessages(convId);
      refreshChatThreadList(convId);
      pollActiveThreadRuntime(true);
    }
  } catch (e) {
    showToast('Failed to stop agents: ' + (e.message || e), 'error');
  }
}

function getEnabledChatAgents() {
  const toggles = document.querySelectorAll('.chat-agent-toggle');
  const enabled = [];
  toggles.forEach(toggle => {
    if (toggle.checked && _chatFlowModeAllowsAgent(toggle.value)) enabled.push(toggle.value);
  });
  return enabled;
}

// Selection state tracking: 'auto' | 'manual' | 'relay' | null (off)
window.__fridaysChatAgentSelectionState = window.__fridaysChatAgentSelectionState || {};

function _setAgentSelectionState(agentKey, state) {
  // state: 'auto' | 'manual' | 'relay' | null
  window.__fridaysChatAgentSelectionState[agentKey] = state || null;
}

function _getAgentSelectionState(agentKey) {
  return window.__fridaysChatAgentSelectionState[agentKey] || null;
}

function renderChatAgentToggles() {
  const hosts = Array.from(document.querySelectorAll('.chat-agent-toggles'));
  if (!hosts.length) return;
  const userColor = _getActorBubbleColor('you') || '#42a5f5';

  // You row — no checkbox, just identity
  const youMeta = _chatAgentMeta('you');
  const userRow = `
    <div class="agent-sel-row agent-sel-row--you">
      <span class="agent-sel-main" style="cursor:default;">
        <span class="agent-sel-pip agent-sel-pip--you"></span>
        <span class="agent-sel-icon">${youMeta.icon}</span>
        <span class="agent-sel-name">You</span>
      </span>
      <input class="agent-sel-swatch" type="color" value="${_escapeHtml(userColor)}"
        title="Your bubble color" oninput="setActorBubbleColor('you', this.value)">
    </div>`;

  const agentRows = CHAT_AGENT_OPTIONS.map(agent => {
    const isOn = !!window.__fridaysChatEnabledAgents[agent.value];
    const checked = isOn ? 'checked' : '';
    const tierLabel = agent.tier === 'local' ? 'Local' : 'Online';
    const temp = agent.hasTemp ? (window.__agentTemps[agent.value] ?? 0.7).toFixed(2) : null;
    const bubbleColor = _getActorBubbleColor(agent.value) || (agent.tier === 'paid' ? '#ff7043' : '#4caf50');
    const vid = 'atv-' + agent.value;
    const selState = _getAgentSelectionState(agent.value);
    const agentIcon = _chatAgentMeta(agent.value).icon;

    // Row state drives the pip glow via CSS class
    let rowState = '';
    if (isOn) {
      if (selState === 'relay')      rowState = ' agent-sel-row--relay';
      else if (selState === 'auto')  rowState = ' agent-sel-row--auto';
      else                           rowState = ' agent-sel-row--on';
    }

    const tempPart = temp !== null ? `
      <div class="agent-sel-temp${isOn ? '' : ' agent-sel-temp--off'}">
        <input type="range" min="0" max="1" step="0.05" value="${temp}"
          class="agent-sel-slider" data-temp-row="${agent.value}"
          onmousedown="event.stopPropagation()" onclick="event.stopPropagation()"
          oninput="document.getElementById('${vid}').textContent=parseFloat(this.value).toFixed(2);_setAgentTemp('${agent.value}',this.value)">
        <span id="${vid}" class="agent-sel-tval">${temp}</span>
      </div>` : `<div class="agent-sel-temp agent-sel-temp--placeholder"></div>`;

    return `
      <div class="agent-sel-row${rowState}" title="${_escapeHtml(agent.label)} · ${tierLabel}">
        <label class="agent-sel-main">
          <input class="agent-sel-check chat-agent-toggle" type="checkbox" value="${agent.value}" ${checked}
            onchange="onChatAgentToggleChange(this);_setAgentSelectionState('${agent.value}',this.checked?'manual':null);renderChatAgentToggles();">
          <span class="agent-sel-pip"></span>
          <span class="agent-sel-icon">${agentIcon}</span>
          <span class="agent-sel-name">${_escapeHtml(agent.label)}</span>
        </label>
        ${tempPart}
        <input class="agent-sel-swatch" type="color" value="${_escapeHtml(bubbleColor)}"
          title="${_escapeHtml(agent.label)} bubble color" oninput="setActorBubbleColor('${agent.value}',this.value)">
      </div>`;
  }).join('');

  hosts.forEach(host => { host.innerHTML = userRow + agentRows; });
  renderRelayMonitorCard();
}

window.__agentTemps = window.__agentTemps || {};

function _setAgentTemp(agentName, value) {
  const temp = Math.round(parseFloat(value) * 100) / 100;
  window.__agentTemps[agentName] = temp;
  fetch('/api/agents/' + encodeURIComponent(agentName) + '/temperature', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ temperature: temp })
  }).catch(() => {});
}

function _loadAgentTemps() {
  fetch('/api/agents')
    .then(r => r.json())
    .then(agents => {
      window.__agentTemps = window.__agentTemps || {};
      (Array.isArray(agents) ? agents : []).forEach(a => {
        if (a.name && a.temperature != null) window.__agentTemps[a.name.toLowerCase()] = a.temperature;
      });
      renderChatAgentToggles();
    })
    .catch(() => {});
}

function renderRelayManagerCard() {
  const hosts = Array.from(document.querySelectorAll('.chat-relay-manager-host'));
  if (!hosts.length) return;
  
  const duckAgent = CHAT_AGENT_OPTIONS.find(a => a.value === 'duck');
  if (!duckAgent) return;
  
  const isOn = !!window.__fridaysChatEnabledAgents[duckAgent.value];
  const checked = isOn ? 'checked' : '';
  const bubbleColor = _getActorBubbleColor(duckAgent.value) || '#4caf50';
  const vid = 'atv-' + duckAgent.value;
  const temp = (window.__agentTemps[duckAgent.value] ?? 0.7).toFixed(2);
  
  // Show queue status
  const queueLen = (window.__fridaysChatRelayQueue || []).length;
  const queueStatus = queueLen > 0 ? `queue: ${queueLen}` : 'idle';
  const queueColor = queueLen > 0 ? 'var(--accent)' : 'var(--text-dim)';
  
  const sliderRow = `
    <div data-temp-row="${duckAgent.value}" style="display:flex;align-items:center;gap:3px;padding:0 1px;opacity:${isOn ? '1' : '0.3'};pointer-events:${isOn ? 'auto' : 'none'};transition:opacity 0.15s;">
      <input type="range" min="0" max="1" step="0.05" value="${temp}"
        style="flex:1;height:2px;accent-color:var(--accent);cursor:pointer;"
        onmousedown="event.stopPropagation()" onclick="event.stopPropagation()"
        oninput="document.getElementById('${vid}').textContent=parseFloat(this.value).toFixed(2);_setAgentTemp('${duckAgent.value}',this.value)">
      <span id="${vid}" style="font-size:8px;color:var(--text-dim);width:20px;text-align:right;font-variant-numeric:tabular-nums;">${temp}</span>
    </div>`;
  
  const managerCard = `<div style="display:flex;flex-direction:column;gap:3px;padding:4px 8px 5px;border:1px solid var(--accent);border-radius:8px;background:color-mix(in oklab, var(--accent) 12%, var(--card));min-width:100px;">
    <label style="display:inline-flex;align-items:center;gap:4px;font-size:10px;cursor:pointer;line-height:1;white-space:nowrap;" title="${duckAgent.label} · Relay Manager">
      <input class="chat-agent-toggle" type="checkbox" value="${duckAgent.value}" ${checked} onchange="onChatAgentToggleChange(this)" style="width:10px;height:10px;margin:0;accent-color:var(--accent);">
      <span class="agent-tier-dot" style="width:5px;height:5px;flex-shrink:0;background:${_escapeHtml(bubbleColor)};"></span>
      <span style="font-weight:600;color:var(--accent);"><svg viewBox="0 0 16 16" width="11" height="11" fill="none" style="vertical-align:-1px;margin-right:1px;"><path d="M4 9.5c0 2 1.8 3 4 3s4-1 4-3c0-1.5-1-2.5-3-2.5H8c1 0 2-1 2-2S9 3 8 3C6.5 3 5.5 4 5.5 5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/><path d="M12 7.5l2 1" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg> Duck</span>
      <input class="agent-bubble-color" type="color" value="${_escapeHtml(bubbleColor)}" title="Choose ${duckAgent.label} bubble color" oninput="setActorBubbleColor('${duckAgent.value}', this.value)">
    </label>
    ${sliderRow}
    <div style="font-size:8px;color:${queueColor};padding:0 4px;margin-top:2px;font-variant-numeric:tabular-nums;">${queueStatus}</div>
    <div style="display:flex;justify-content:flex-end;padding:0 2px;">
      <button class="chat-action-btn" style="padding:1px 6px;font-size:9px;" onclick="showRelayLogs('duck')">Duck Log</button>
    </div>
  </div>`;
  
  hosts.forEach(host => {
    host.innerHTML = managerCard;
  });
}

function renderRelayMonitorCard() {
  const hosts = Array.from(document.querySelectorAll('.chat-relay-monitor-host'));
  if (!hosts.length) return;
  
  const librarianConfig = {value: 'librarian', label: 'Librarian', tier: 'local', hasTemp: false};
  const bubbleColor = _getActorBubbleColor(librarianConfig.value) || '#7c7cba';
  
  // Show relay timeline count
  const timelineLen = (window.__fridaysChatTimeline || []).length;
  const monitorStatus = timelineLen > 0 ? `${timelineLen} event${timelineLen !== 1 ? 's' : ''}` : 'no activity';
  
  const monitorCard = `<div style="display:flex;flex-direction:column;gap:3px;padding:4px 8px 5px;border:1px solid var(--border);border-radius:8px;background:color-mix(in oklab, var(--card) 92%, transparent);min-width:100px;opacity:0.85;">
    <label style="display:inline-flex;align-items:center;gap:4px;font-size:10px;line-height:1;white-space:nowrap;" title="${librarianConfig.label} · Relay Monitor (read-only)">
      <span class="agent-tier-dot" style="width:5px;height:5px;flex-shrink:0;background:${_escapeHtml(bubbleColor)};"></span>
      <span style="font-weight:600;color:var(--text-dim);"><svg viewBox="0 0 16 16" width="11" height="11" fill="none" style="vertical-align:-1px;margin-right:1px;"><path d="M4.5 3.5v9M4.5 3.5h5a2 2 0 010 4h-5M4.5 7.5h5.5a2 2 0 010 4H4.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg> Librarian</span>
    </label>
    <div style="font-size:8px;color:var(--text-dim);padding:0 4px;font-style:italic;">${monitorStatus}</div>
    <div style="display:flex;justify-content:flex-end;padding:0 2px;">
      <button class="chat-action-btn" style="padding:1px 6px;font-size:9px;" onclick="showRelayLogs('librarian')">Librarian Log</button>
    </div>
  </div>`;
  
  hosts.forEach(host => {
    host.innerHTML = monitorCard;
  });
}

function _renderWelcome() {
  const messages = _chatMessagesEl();
  if (!messages) return;
  _syncThinkingBubbles([]);
  window.__fridaysChatTimeline = [];
  renderChatRelayTimeline();
  messages.innerHTML = '';
  _renderTicketBanner(null, null);
}

function _renderTicketBanner(ticket, conv) {
  // Show or clear the linked ticket banner above the chat messages
  let banner = document.getElementById('chat-ticket-banner');
  const messages = _chatMessagesEl();
  if (!messages) return;

  if (!ticket) {
    if (banner) banner.remove();
    return;
  }

  const ch = ticket.channel || ticket.source_type || 'email';
  const chIcon = ch === 'telegram' ? '<svg viewBox="0 0 16 16" width="13" height="13" fill="none" style="vertical-align:-2px;"><path d="M2 8l12-5-3 12-4-3.5L2 8zm5 3.5V14l1.5-2" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    : ch === 'discord' ? '<svg viewBox="0 0 16 16" width="13" height="13" fill="none" style="vertical-align:-2px;"><path d="M5.5 3C4 3.5 3 4.5 2.5 6c1.5 5 4 7 5.5 7.5C9.5 13 12 11 13.5 6 13 4.5 12 3.5 10.5 3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/><circle cx="6" cy="8" r="1" fill="currentColor"/><circle cx="10" cy="8" r="1" fill="currentColor"/></svg>'
    : '<svg viewBox="0 0 16 16" width="13" height="13" fill="none" style="vertical-align:-2px;"><rect x="2" y="3.5" width="12" height="9" rx="1.5" stroke="currentColor" stroke-width="1.3"/><path d="M2 5.5l6 4 6-4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  const chLabel = ch.charAt(0).toUpperCase() + ch.slice(1);
  const status = ticket.status || 'open';
  const statusColor = status === 'closed' ? '#4caf50' : status === 'failed' ? '#f44336' : '#ffa726';
  const tn = _escapeHtml(ticket.ticket_number || '');
  const sender = _escapeHtml(ticket.sender_email || '');
  const subject = _escapeHtml(ticket.subject || ticket.question || '');

  const html = `
    <div id="chat-ticket-banner" style="
      display:flex;align-items:center;gap:8px;padding:6px 12px;
      background:color-mix(in srgb,var(--card) 85%,var(--accent) 15%);
      border-bottom:1px solid var(--border);font-size:11px;flex-shrink:0;
      position:sticky;top:0;z-index:10;
    ">
      <span style="font-size:15px;line-height:1;">${chIcon}</span>
      <span style="font-weight:700;color:var(--accent);">${tn}</span>
      <span style="color:var(--text-dim);">·</span>
      <span style="color:var(--text-dim);">${chLabel}</span>
      <span style="color:var(--text-dim);">·</span>
      <span style="color:var(--text);">${sender}</span>
      ${subject ? `<span style="color:var(--text-dim);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;max-width:300px;">${subject.slice(0,80)}</span>` : ''}
      <span style="margin-left:auto;background:${statusColor}22;color:${statusColor};border:1px solid ${statusColor}44;border-radius:4px;padding:1px 7px;font-size:10px;font-weight:700;">${status.toUpperCase()}</span>
      <button onclick="this.parentElement.remove()" style="background:none;border:none;color:var(--text-dim);cursor:pointer;font-size:13px;padding:0 2px;line-height:1;">✕</button>
    </div>`;

  if (banner) {
    banner.outerHTML = html;
  } else {
    // Insert before messages container
    const parent = messages.parentElement;
    if (parent) {
      parent.insertAdjacentHTML('afterbegin', html);
    }
  }
}

function renderChatThreadRail() {
  const rail = document.getElementById('chat-thread-list');
  if (!rail) return;
  const search = (document.getElementById('chat-thread-search')?.value || '').trim().toLowerCase();
  const convs = (window._chatConversations || []).filter(conv => {
    if (!search) return true;
    const title = String(conv.title || '').toLowerCase();
    const id = String(conv.id || '').toLowerCase();
    return title.includes(search) || id.includes(search);
  });
  if (!convs.length) {
    rail.innerHTML = '<div style="padding:12px;color:var(--text-dim);font-size:11px;">No matching threads.</div>';
    updateChatStatusPills();
    return;
  }

  rail.innerHTML = convs.slice(0, 80).map(conv => {
    const active = Number(window.__fridaysChatConversationId) === Number(conv.id) ? ' active' : '';
    const ts = (conv.timestamp || conv.created_at || '').slice(0, 16);
    const title = _escapeHtml(conv.title || '(untitled)');
    const src = String(conv.source || '').toLowerCase();
    const srcIcon = src === 'telegram' ? '<span title="Telegram" style="opacity:0.75;line-height:1;"><svg viewBox="0 0 16 16" width="11" height="11" fill="none"><path d="M2 8l12-5-3 12-4-3.5L2 8zm5 3.5V14l1.5-2" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg></span>'
                  : src === 'discord'  ? '<span title="Discord" style="opacity:0.75;line-height:1;"><svg viewBox="0 0 16 16" width="11" height="11" fill="none"><path d="M5.5 3C4 3.5 3 4.5 2.5 6c1.5 5 4 7 5.5 7.5C9.5 13 12 11 13.5 6 13 4.5 12 3.5 10.5 3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/><circle cx="6" cy="8" r="1" fill="currentColor"/><circle cx="10" cy="8" r="1" fill="currentColor"/></svg></span>'
                  : src === 'email'    ? '<span title="Email" style="opacity:0.55;line-height:1;"><svg viewBox="0 0 16 16" width="11" height="11" fill="none"><rect x="2" y="3.5" width="12" height="9" rx="1.5" stroke="currentColor" stroke-width="1.3"/><path d="M2 5.5l6 4 6-4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg></span>'
                  : '';
    return `
      <div class="thread-item${active}" onclick="switchChatThread('${conv.id}')" style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">
        <div style="min-width:0;flex:1;">
          <div style="font-size:12px;color:var(--text);font-weight:600;line-height:1.3;overflow:hidden;text-overflow:ellipsis;display:flex;align-items:center;gap:4px;">${srcIcon}<span>${title}</span></div>
          <div style="font-size:10px;color:var(--text-dim);margin-top:4px;">#${conv.id}${ts ? ' · ' + ts : ''}</div>
        </div>
        <div style="display:flex;gap:4px;">
          <button class="chat-action-btn" onclick="threadActionRename(event, ${Number(conv.id)});" title="Rename thread"><svg viewBox="0 0 16 16" width="11" height="11" fill="none"><path d="M11.5 2.5l2 2M5 9l-1 3 3-1 7-7-2-2-7 7z" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
          <button class="chat-action-btn" onclick="threadActionDelete(event, ${Number(conv.id)});" title="Delete thread"><svg viewBox="0 0 16 16" width="11" height="11" fill="none"><path d="M3 4.5h10M6.5 4.5V3a1 1 0 011-1h1a1 1 0 011 1v1.5M5 4.5l.5 8a1 1 0 001 1h3a1 1 0 001-1l.5-8" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
        </div>
      </div>
    `;
  }).join('');
  updateChatStatusPills();
}

function threadActionRename(event, convId) {
  if (event) {
    event.preventDefault();
    event.stopPropagation();
  }
  renameThread(convId);
}

function threadActionDelete(event, convId) {
  if (event) {
    event.preventDefault();
    event.stopPropagation();
  }
  deleteThread(convId);
}

function renderChatMessages(rows) {
  const messages = _chatMessagesEl();
  if (!messages) return;
  if (!rows || !rows.length) {
    _renderWelcome();
    return;
  }
  window.__fridaysChatTimeline = [];
  renderChatRelayTimeline();
  messages.innerHTML = '';
  rows.forEach(row => {
    const sender = (row.sender || 'agent').toString().toLowerCase();
    const content = row.content || '';
    const msgId = Number(row.id || 0);
    const convId = Number(window.__fridaysChatConversationId || 0);
    if (row.message_type === 'relay') {
      const _rFromLabel = _chatAgentLabel(sender);
      const _rToLabel = _chatAgentLabel(String(row.to_agent || '').split(',')[0].trim());
      const _rDiv = document.createElement('div');
      _rDiv.className = 'chat-relay-dispatch';
      _rDiv.innerHTML = `<span class="relay-from">${_escapeHtml(_rFromLabel)}</span><span class="relay-arrow">→</span><span class="relay-to">${_escapeHtml(_rToLabel)}</span>: <span>${_escapeHtml(String(content).slice(0, 160))}</span><span class="relay-stop" title="Dismiss this relay">✕</span>`;
      _rDiv.querySelector('.relay-stop').addEventListener('click', () => _dismissRelayBar(_rDiv, null));
      messages.appendChild(_rDiv);
    } else if (sender === 'user') {
      const extracted = _extractAttachmentsFromMessage(content);
      const rawTargetAgents = _chatTargetAgentsFromRaw(row.to_agent);
      const prefix = _chatTargetsPrefixFromRaw(row.to_agent);
      const renderedText = /^\s*\[[^\]]+\]\s/.test(String(content || ''))
        ? content
        : (prefix ? (prefix + content) : content);
      _appendChatBubble('you', renderedText, {
        messageId: msgId,
        conversationId: convId,
        editable: true,
        selectedAgents: rawTargetAgents,
        localPromptText: extracted.text,
        attachments: extracted.attachments,
        fromHistory: true,
      });
    } else {
      _appendChatBubble(sender, content, {
        messageId: msgId,
        conversationId: convId,
        tokens: Number(row.tokens_used || 0),
        fromHistory: true,
      });
    }
  });
  const snapshotJobs = Array.isArray(window.__fridaysThreadRuntimeSnapshot?.jobs)
    ? window.__fridaysThreadRuntimeSnapshot.jobs
    : [];
  _syncThinkingBubbles(snapshotJobs);

  // Inject Route-to buttons on the last agent bubble rendered from history.
  // _appendChatBubble skips relay extraction when fromHistory=true, so we do it here.
  // This lets the user manually route if auto-relay didn't fire yet.
  const allBubbles = (messages || document).querySelectorAll('.chat-bubble:not(.user)');
  const lastAgentBubble = allBubbles.length ? allBubbles[allBubbles.length - 1] : null;
  if (lastAgentBubble && !lastAgentBubble.querySelector('.chat-handoff-actions')) {
    const textEl = lastAgentBubble.querySelector('.chat-text');
    const visibleText = textEl ? (textEl.innerText || textEl.textContent || '') : '';
    const senderClass = Array.from(lastAgentBubble.classList).find(c => c.startsWith('sender-'));
    const fromKey = senderClass ? senderClass.replace('sender-', '') : 'agent';
    const relayCandidates = _extractAgentDirectedQuestions(visibleText, fromKey);
    if (relayCandidates.length) {
      const buttonsDiv = document.createElement('div');
      buttonsDiv.className = 'chat-handoff-actions';
      buttonsDiv.innerHTML = relayCandidates.map(c =>
        `<span class="chat-handoff-btn" role="button" tabindex="0" data-relay-from="${_escapeHtml(fromKey)}" data-relay-target="${_escapeHtml(c.target)}" data-relay-question="${_escapeHtml(_relayEncode(c.question))}" onclick="queueRelayHandoffFromButton(this)">Route to ${_escapeHtml(_chatAgentLabel(c.target))}</span>`
      ).join('');
      const actionsRow = lastAgentBubble.querySelector('.chat-actions');
      if (actionsRow) actionsRow.insertAdjacentElement('beforebegin', buttonsDiv);
      else lastAgentBubble.appendChild(buttonsDiv);
    }
  }

  // Inject pending stage traces into the most recent bubble for each agent.
  // Populated by _pollPendingChatJobs when async jobs complete.
  const pendingTraces = window.__fridaysPendingBubbleTraces;
  if (pendingTraces && typeof pendingTraces === 'object') {
    Object.entries(pendingTraces).forEach(([agentKey, trace]) => {
      if (!Array.isArray(trace) || !trace.length) return;
      const sel = '.chat-bubble.sender-' + agentKey.replace(/[^a-z0-9_-]/g, '');
      const agentBubbles = messages.querySelectorAll(sel);
      const targetBubble = agentBubbles.length ? agentBubbles[agentBubbles.length - 1] : null;
      if (!targetBubble || targetBubble.querySelector('.chat-bubble-trace')) return;
      const traceEl = document.createElement('details');
      traceEl.className = 'chat-bubble-trace';
      traceEl.innerHTML = `<summary>Trace \u00b7 ${trace.length} step${trace.length !== 1 ? 's' : ''}</summary><div class="chat-bubble-trace-body">${trace.map((s, i) => `<div class="chat-bubble-trace-step"><span class="chat-bubble-trace-num">${i + 1}</span><span class="chat-bubble-trace-text">${_escapeHtml(String(s && s.text != null ? s.text : s))}</span></div>`).join('')}</div>`;
      const actionsEl = targetBubble.querySelector('.chat-actions');
      if (actionsEl) actionsEl.insertAdjacentElement('beforebegin', traceEl);
      else targetBubble.appendChild(traceEl);
    });
    window.__fridaysPendingBubbleTraces = {};
  }
}

function _chatRowsSignature(rows) {
  const list = Array.isArray(rows) ? rows : [];
  if (!list.length) return 'empty';
  const last = list[list.length - 1] || {};
  const lastId = Number(last.id || 0);
  const sender = String(last.sender || '').toLowerCase().trim();
  const len = String(last.content || '').length;
  return `${list.length}:${lastId}:${sender}:${len}`;
}

function loadConversationMessages(convId, options = {}) {
  if (!convId) {
    _renderWelcome();
    window.__fridaysChatLastRenderSig = '';
    return Promise.resolve(false);
  }
  const requestedConvId = Number(convId);
  const force = !!options.force;
  const allowStale = !!options.allowStale;
  return fetch('/api/conversations/' + convId + '/messages')
    .then(r => r.json())
    .then(data => {
      const activeConvId = Number(window.__fridaysChatConversationId || 0);
      if (!allowStale && activeConvId && activeConvId !== requestedConvId) {
        return false;
      }
      const rows = data.messages || [];
      const nextSig = `${requestedConvId}:${_chatRowsSignature(rows)}`;
      if (!force && window.__fridaysChatLastRenderSig === nextSig) {
        return false;
      }
      window.__fridaysChatLastRenderSig = nextSig;
      renderChatMessages(rows);
      // Render linked ticket banner if present
      _renderTicketBanner(data.ticket, data.conv);
      return true;
    })
    .catch(e => {
      if (!options.silent) {
        _appendChatBubble('system', 'Error loading thread: ' + e.message);
      }
      return false;
    });
}

function startChatLiveSyncService() {
  if (window.__fridaysChatLiveSyncTimer) {
    clearInterval(window.__fridaysChatLiveSyncTimer);
    window.__fridaysChatLiveSyncTimer = null;
  }
  if (window.__fridaysChatLiveSyncThreadRefreshTimer) {
    clearInterval(window.__fridaysChatLiveSyncThreadRefreshTimer);
    window.__fridaysChatLiveSyncThreadRefreshTimer = null;
  }

  const syncNow = () => {
    const convId = Number(window.__fridaysChatConversationId || 0);
    if (!convId) return;
    loadConversationMessages(convId, { silent: true, force: false, allowStale: false });
  };

  syncNow();
  window.__fridaysChatLiveSyncTimer = setInterval(syncNow, 1800);
  window.__fridaysChatLiveSyncThreadRefreshTimer = setInterval(() => {
    const convId = Number(window.__fridaysChatConversationId || 0);
    if (!convId) return;
    refreshChatThreadList(convId);
  }, 15000);
}

function refreshChatThreadList(preferredId = null) {
  const threadSelect = document.getElementById('chat-thread-select');
  if (!threadSelect) return Promise.resolve();
  return fetch('/api/conversations')
    .then(r => r.json())
    .then(data => {
      const convs = Array.isArray(data) ? data : (data.recent || data.conversations || []);
      window._chatConversations = convs;

      threadSelect.innerHTML = '<option value="">New Thread</option>';
      convs.slice(0, 50).forEach(conv => {
        const opt = document.createElement('option');
        opt.value = String(conv.id);
        const ts = (conv.timestamp || conv.created_at || '').slice(0, 16);
        opt.textContent = '#' + conv.id + ' · ' + (conv.title || '(untitled)') + (ts ? ' · ' + ts : '');
        threadSelect.appendChild(opt);
      });

      let targetId = preferredId || window.__fridaysChatConversationId;
      if (!targetId && !window.__fridaysChatForceNewThread && convs.length) {
        targetId = convs[0].id;
      }
      if (targetId) {
        threadSelect.value = String(targetId);
        _setActiveThreadId(Number(targetId));
      } else {
        threadSelect.value = '';
        _setActiveThreadId(null);
      }
      applyThreadAgentSelection(window.__fridaysChatConversationId);
      renderChatAgentToggles();
      updateComposerMeta();
      renderChatThreadRail();
    })
    .catch(e => {
      console.error('Failed to load conversation list:', e);
    });
}

function switchChatThread(convIdValue) {
  const convId = convIdValue ? Number(convIdValue) : null;
  _setActiveThreadId(Number.isFinite(convId) ? convId : null);
  applyThreadAgentSelection(window.__fridaysChatConversationId);
  renderChatAgentToggles();
  updateComposerMeta();
  const threadSelect = document.getElementById('chat-thread-select');
  if (threadSelect) threadSelect.value = convId ? String(convId) : '';
  renderChatThreadRail();
  loadConversationMessages(window.__fridaysChatConversationId);
  pollActiveThreadRuntime(true);
}

async function renameThread(convId) {
  const convs = window._chatConversations || [];
  const row = convs.find(c => Number(c.id) === Number(convId));
  const currentTitle = (row && row.title) ? String(row.title) : '';
  const nextTitle = prompt('Rename thread:', currentTitle || '');
  if (nextTitle === null) return;
  const cleaned = String(nextTitle || '').trim();
  if (!cleaned) {
    showToast('Title cannot be empty', 'error');
    return;
  }
  try {
    const resp = await fetch('/api/conversations/' + convId, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ title: cleaned })
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok || !data.ok) {
      throw new Error((data && data.error) || `HTTP ${resp.status}`);
    }
    showToast('Thread renamed', 'success');
    refreshChatThreadList(window.__fridaysChatConversationId || convId);
  } catch (e) {
    showToast('Failed to rename thread: ' + (e.message || e), 'error');
  }
}

function _confirmDelete(message, onConfirm) {
  const SKIP_KEY = 'fridays_skip_del_confirm';
  if (localStorage.getItem(SKIP_KEY) === '1') { 
    Promise.resolve().then(() => onConfirm());
    return; 
  }
  const overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.55);z-index:9999;display:flex;align-items:center;justify-content:center;';
  overlay.innerHTML = `
    <div style="background:var(--card);border:1px solid var(--border);border-radius:10px;padding:20px 22px;max-width:340px;width:90%;box-shadow:0 16px 48px rgba(0,0,0,0.4);">
      <div style="font-size:13px;font-weight:700;margin-bottom:6px;">Confirm Delete</div>
      <div style="font-size:12px;color:var(--text-dim);margin-bottom:14px;">${_escHtml(message)}</div>
      <label style="display:flex;align-items:center;gap:7px;font-size:11px;color:var(--text-dim);margin-bottom:16px;cursor:pointer;user-select:none;">
        <input type="checkbox" id="_del_skip" style="accent-color:var(--accent);cursor:pointer;">
        Don't confirm future deletions
      </label>
      <div style="display:flex;gap:8px;justify-content:flex-end;">
        <button id="_del_cancel" style="padding:6px 14px;background:transparent;border:1px solid var(--border);border-radius:6px;color:var(--text-dim);font-size:12px;cursor:pointer;">Cancel</button>
        <button id="_del_ok" style="padding:6px 14px;background:#ef4444;border:none;border-radius:6px;color:#fff;font-size:12px;font-weight:600;cursor:pointer;">Delete</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);
  const close = () => { if (overlay.parentNode) overlay.parentNode.removeChild(overlay); };
  overlay.querySelector('#_del_ok').onclick = () => {
    const skipCheckbox = overlay.querySelector('#_del_skip');
    if (skipCheckbox && skipCheckbox.checked) {
      localStorage.setItem(SKIP_KEY, '1');
    }
    close();
    Promise.resolve().then(() => onConfirm());
  };
  overlay.querySelector('#_del_cancel').onclick = close;
  overlay.onclick = e => { if (e.target === overlay) close(); };
}

async function deleteThread(convId) {
  _confirmDelete('Delete this chat thread and all messages?', async () => {
    try {
      const resp = await fetch('/api/conversations/' + convId, { method: 'DELETE' });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok || !data.ok) throw new Error((data && data.error) || `HTTP ${resp.status}`);
      window._chatConversations = (window._chatConversations || []).filter(c => Number(c.id) !== Number(convId));
      const threadSelect = document.getElementById('chat-thread-select');
      if (threadSelect) {
        const dead = Array.from(threadSelect.options).find(o => Number(o.value) === Number(convId));
        if (dead) dead.remove();
      }
      if (Number(window.__fridaysChatConversationId) === Number(convId)) {
        createNewThread();
      } else {
        renderChatThreadRail();
      }
      showToast('Thread deleted', 'success');
      refreshChatThreadList(window.__fridaysChatConversationId || null);
    } catch (e) {
      showToast('Failed to delete thread: ' + (e.message || e), 'error');
    }
  });
}

function renameCurrentThread() {
  const convId = window.__fridaysChatConversationId;
  if (!convId) {
    showToast('Select a thread first', 'info');
    return;
  }
  renameThread(convId);
}

function deleteCurrentThread() {
  const convId = window.__fridaysChatConversationId;
  if (!convId) {
    showToast('Select a thread first', 'info');
    return;
  }
  deleteThread(convId);
}

async function clearAllChatHistory() {
  const convs = (window._chatConversations || []).slice();
  if (!convs.length) { showToast('No chat history to clear', 'info'); return; }
  _confirmDelete(`Delete all ${convs.length} chat thread(s)? This cannot be undone.`, async () => {
    let deleted = 0;
    for (const conv of convs) {
      try {
        const resp = await fetch('/api/conversations/' + conv.id, { method: 'DELETE' });
        const data = await resp.json().catch(() => ({}));
        if (resp.ok && data.ok) deleted += 1;
      } catch (_) {}
    }
    createNewThread();
    refreshChatThreadList(null);
    showToast(`Deleted ${deleted} thread(s)`, 'success');
  });
}

function _chatMoreMenu() {
  const menu = document.getElementById('chat-more-menu');
  if (!menu) return;
  const open = menu.style.display !== 'none';
  menu.style.display = open ? 'none' : 'block';
  if (!open) {
    // Close on next outside click
    setTimeout(() => document.addEventListener('click', _chatMoreClose, { once: true }), 0);
  }
}
function _chatMoreClose() {
  const menu = document.getElementById('chat-more-menu');
  if (menu) menu.style.display = 'none';
}

function createNewThread() {
  window.__fridaysChatForceNewThread = true;
  _setActiveThreadId(null);
  applyThreadAgentSelection(null);
  renderChatAgentToggles();
  updateComposerMeta();
  const threadSelect = document.getElementById('chat-thread-select');
  if (threadSelect) threadSelect.value = '';
  renderChatThreadRail();
  _renderWelcome();
  pollActiveThreadRuntime(true);
  showToast('Started a new thread', 'success');
}

function initializeChatPanel() {
  applyThreadAgentSelection(window.__fridaysChatConversationId);
  renderChatAgentToggles();
  _loadAgentTemps();
  initChatDockLayout();
  initChatSections();
  renderReplyBanner();
  renderChatAttachments();
  initChatHistoryControls();
  initChatAttachmentDnD();
  renderChatThreadRail();
  initChatSpellHelper();
  _renderChatRelayControls();
  renderChatRelayTimeline();
  _updateParallelModeBtn();
  _updateExecModeBtn();
  updateComposerMeta();
  updateNotificationControls();
  updateChatStatusPills();
  _applyBubbleColorOverrides();
  startThreadRuntimePolling();
  if (!window.__fridaysChatConversationId) {
    _renderWelcome();
  }
}

function initChatSpellHelper() {
  window.__fridaysChatCustomDictionary = _loadChatCustomDictionary();
  const input = document.getElementById('question-input');
  const search = document.getElementById('chat-thread-search');
  if (!input) {
    updateChatSpellHelper();
    updateChatStatusPills();
    return;
  }

  if (input.dataset.spellBound !== '1') {
    input.dataset.spellBound = '1';
    input.addEventListener('keydown', (ev) => {
      if (_handleMentionKeydown(ev, input)) return;
    });
    input.addEventListener('input', () => _handleMentionInput(input));
    input.addEventListener('click', () => _handleMentionInput(input));
    input.addEventListener('input', updateChatSpellHelper);
    input.addEventListener('input', updateComposerMeta);
    input.addEventListener('keyup', updateChatSpellHelper);
    input.addEventListener('keyup', updateComposerMeta);
    input.addEventListener('click', updateChatSpellHelper);
    input.addEventListener('click', updateComposerMeta);

    if (document.body && document.body.dataset.chatMentionBound !== '1') {
      document.body.dataset.chatMentionBound = '1';
      document.addEventListener('click', (ev) => {
        const wrapper = document.getElementById('input-wrapper');
        if (!wrapper) return;
        if (wrapper.contains(ev.target)) return;
        _closeMentionMenu();
      });
    }

    if (search && search.dataset.bound !== '1') {
      search.dataset.bound = '1';
      search.addEventListener('input', renderChatThreadRail);
    }
  }

  updateChatSpellHelper();
  updateComposerMeta();
  updateChatStatusPills();
}

function autoGrowTextarea(el) {
  if (!el) return;
  el.style.height = 'auto';
  const maxH = 200; // ~10 lines
  const newH = Math.min(el.scrollHeight, maxH);
  el.style.height = newH + 'px';
  el.style.overflowY = newH >= maxH ? 'auto' : 'hidden';
}

function _triggerSendGlow() {
  const wrapper = document.getElementById('input-wrapper');
  if (!wrapper) return;
  wrapper.classList.remove('compose-sending');
  void wrapper.offsetWidth; // reflow to restart animation
  wrapper.classList.add('compose-sending');
  wrapper.addEventListener('animationend', () => wrapper.classList.remove('compose-sending'), { once: true });
}

function sendMessage(source = 'user', relayMeta = null) {
  const input = document.getElementById('question-input');
  const messages = _chatMessagesEl();
  if (!input || !messages) return Promise.resolve(false);
  const msg = input.value.trim();
  let selectedAgents = (source === 'relay' && relayMeta?.target)
    ? [String(relayMeta.target).toLowerCase()]
    : getEnabledChatAgents();
  let convId = window.__fridaysChatConversationId || null;
  if (!convId && !window.__fridaysChatForceNewThread) {
    const first = (window._chatConversations || [])[0];
    if (first && first.id) {
      convId = Number(first.id);
      _setActiveThreadId(convId);
    }
  }

  const hasAttachments = (window.__fridaysChatAttachments || []).length > 0;
  const contextCfg = getChatContextConfig();
  const mentionedAgents = source === 'user' ? _extractMentionedAgents(msg) : [];
  if (mentionedAgents.length) {
    // If user explicitly mentions agents, deselect all others
    window.__fridaysChatEnabledAgents = {};
    mentionedAgents.forEach(agent => {
      window.__fridaysChatEnabledAgents[agent] = true;
    });
    renderChatAgentToggles();
    window.__fridaysLastMentionedAgents = mentionedAgents.slice(0, 4);
    persistThreadAgentSelection();
    selectedAgents = getEnabledChatAgents();
    window.__fridaysLastMentionedAgents = mentionedAgents.slice(0, 4);
  }
  const userIntentRelayHandoffs = source === 'user'
    ? _extractUserRequestedHandoffs(msg, selectedAgents)
    : [];
  if (source === 'relay' && window.__fridaysChatRelayForceFull) {
    contextCfg.historyMode = 'full';
    contextCfg.historyLimit = 30;
  }
  if (!msg && !hasAttachments) return Promise.resolve(false);
  if (!selectedAgents.length) {
    showToast('Turn on at least one agent toggle', 'error');
    return Promise.resolve(false);
  }
  if (source === 'user') {
    const relayCfg = _chatRelayConfig();
    window.__fridaysChatRelayAllowedAgents = selectedAgents.slice();
    window.__fridaysChatRelayBudget = relayCfg.infinite ? -1 : relayCfg.maxPerTurn;
    window.__fridaysChatRelayQueue = [];
    window.__fridaysChatRelayBusy = false;
    window.__fridaysChatRelayInFlight = 0;
    window.__fridaysChatRelayActive = false;
    window.__fridaysChatRelaySeen = {};
    window.__fridaysChatRelayHoldReason = '';
    window.__fridaysChatRelayHoldStamp = 0;
    window.__fridaysChatRelayLastHoldKey = '';
    _relayClearRetryTimer();
    if (window.__fridaysReplaceBubbleId) {
      const oldNode = document.getElementById('chat-bubble-' + String(window.__fridaysReplaceBubbleId || '').replace(/[^a-zA-Z0-9_-]/g, ''));
      if (oldNode) oldNode.remove();
    }
    _renderChatRelayControls();
  }

  const replyTargets = Array.isArray(window.__fridaysReplyTargets) ? window.__fridaysReplyTargets : [];
  const wireMsg = replyTargets.length
    ? `[Reply to ${Array.from(new Set(replyTargets.map(t => t.sender))).join(', ')}]\nQuoted:\n${replyTargets.map(t => `- ${t.sender}: "${t.preview}"`).join('\n')}\n\n${msg}`
    : msg;
  const attachmentPayload = _buildAttachmentPayload();
  const wireMsgWithAttachments = wireMsg + (attachmentPayload.wireBlock || '');
  
  const userBubbleText = msg
    ? '[' + _chatAgentListText(selectedAgents) + '] ' + msg
    : '[' + _chatAgentListText(selectedAgents) + '] (attachment)';
  if (source === 'relay') {
    const _rFromKey = String(relayMeta?.from || 'agent').toLowerCase();
    const _rToKey = String(relayMeta?.target || selectedAgents[0] || 'agent').toLowerCase();
    const _rFromLabel = _chatAgentLabel(_rFromKey);
    const _rToLabel = _chatAgentLabel(_rToKey);
    const _rMessages = _chatMessagesEl();
    if (_rMessages) {
      const _rDiv = document.createElement('div');
      _rDiv.className = 'chat-relay-dispatch';
      _rDiv.innerHTML = `<span class="relay-from">${_escapeHtml(_rFromLabel)}</span><span class="relay-arrow">→</span><span class="relay-to">${_escapeHtml(_rToLabel)}</span>: <span>${_escapeHtml(String(msg || '').slice(0, 160))}</span>${Number.isFinite(Number(relayMeta?.chainDepth)) && Number(relayMeta.chainDepth) >= 0 ? `<span class="relay-chain-badge">⛓${Number(relayMeta.chainDepth)}</span>` : ''}<span class="relay-stop" title="Stop this relay">✕</span>`;
      _rDiv.querySelector('.relay-stop').addEventListener('click', () => _dismissRelayBar(_rDiv, _rToKey));
      _rMessages.appendChild(_rDiv);
      _rMessages.scrollTop = _rMessages.scrollHeight;
    }
    _appendInfoLogEntry('librarian', `↳ Relay: ${_rFromLabel} → ${_rToLabel}`, true);
  } else {
    _appendChatBubble('you', userBubbleText, {
      quoted: replyTargets.length ? replyTargets : null
      , selectedAgents: selectedAgents
      , localPromptText: msg || ''
      , attachments: attachmentPayload.bubbleAttachments || []
      , relayMeta: relayMeta || null
    });
  }

  const estMs = _estimateBatchMs(selectedAgents);
  const loadingPanel = _createLoadingPanel(selectedAgents);
  const loadingCtl = _startLoadingTicker(loadingPanel, selectedAgents, estMs);

  persistThreadAgentSelection(convId);
  
  _triggerSendGlow();
  input.value = '';
  input.style.height = '';
  input.style.overflowY = 'hidden';
  clearReplyTarget();
  clearChatAttachments();
  updateComposerMeta();
  updateChatSpellHelper();
  
  return fetch('/api/chat', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      message: wireMsgWithAttachments,
      agents: selectedAgents,
      conversation_id: convId,
      new_thread: !!window.__fridaysChatForceNewThread,
      history_mode: contextCfg.historyMode,
      history_limit: contextCfg.historyMode === 'recent' ? contextCfg.historyLimit : undefined,
      auto_relay: !!window.__fridaysChatRelayAuto,
      parallel_mode: !_isSequentialExecMode(),
      exec_mode: String(window.__fridaysChatExecMode || 'sequential'),
      flow_mode: String(window.__fridaysChatFlowMode || 'both_seq'),
      ...(source === 'relay' && relayMeta?.from ? { relay_from: String(relayMeta.from).toLowerCase() } : {}),
      ..._authPayload(),
    })
  })
  .then(r => r.json())
  .then(data => {
    if (!data || data.ok === false) {
      loadingCtl.stop([]);
      window.__fridaysChatPendingJobIds = [];
      window.__fridaysChatPendingConversationId = null;
      const err = (data && (data.error || data.response)) || 'Request failed.';
      _appendChatBubble('system', err);
      messages.scrollTop = messages.scrollHeight;
      return;
    }
    if (data && data.conversation_id) {
      _setActiveThreadId(data.conversation_id);
      window.__fridaysChatForceNewThread = false;
      persistThreadAgentSelection(data.conversation_id);
      applyThreadAgentSelection(data.conversation_id);
      renderChatAgentToggles();
      updateComposerMeta();
      refreshChatThreadList(data.conversation_id);
      pollActiveThreadRuntime(true);
    }

    const allResponses = Array.isArray(data.responses) ? data.responses : [];
    const immediateResponses = allResponses.filter(entry => !entry.pending);
    const pendingResponses = allResponses.filter(entry => entry.pending);
    const pendingJobs = Array.isArray(data.pending_jobs) ? data.pending_jobs : [];
    const discovered = [];

    if (immediateResponses.length) {
      immediateResponses.forEach(entry => {
        _appendChatBubble(entry.agent || 'agent', entry.response || '...', {
          tokens: entry.tokens || 0,
          stageTrace: entry.stage_trace || [],
          ...(source === 'relay' && relayMeta ? { chainDepth: Number(relayMeta.chainDepth ?? -1) } : {}),
        });
        if (source === 'user' && window.__fridaysReplaceBubbleId && window.__fridaysReplaceAgentKey && String(entry.agent || '').toLowerCase() === String(window.__fridaysReplaceAgentKey || '').toLowerCase()) {
          const oldNode = document.getElementById('chat-bubble-' + String(window.__fridaysReplaceBubbleId || '').replace(/[^a-zA-Z0-9_-]/g, ''));
          if (oldNode) oldNode.remove();
          window.__fridaysReplaceBubbleId = '';
          window.__fridaysReplaceAgentKey = '';
        }
      });

      immediateResponses.forEach(entry => {
        const from = String(entry.agent || 'agent').toLowerCase();
        _extractAgentDirectedQuestions(entry.response || '', from).forEach(h => discovered.push(h));
      });

      const first = immediateResponses[0];
      notifyDesktop(
        'Fridays · ' + _chatAgentLabel(first.agent || 'agent'),
        String(first.response || '').replace(/\s+/g, ' ').slice(0, 180),
        { tag: 'fridays-chat-reply-' + String(data.conversation_id || convId || 'none') }
      );
    } else if (!pendingJobs.length) {
      _appendChatBubble(data.agent || selectedAgents[0], data.response || '...', {
        ...(source === 'relay' && relayMeta ? { chainDepth: Number(relayMeta.chainDepth ?? -1) } : {}),
      });
      notifyDesktop(
        'Fridays · ' + _chatAgentLabel(data.agent || selectedAgents[0]),
        String(data.response || '').replace(/\s+/g, ' ').slice(0, 180),
        { tag: 'fridays-chat-reply-' + String(data.conversation_id || convId || 'none') }
      );
    }

    // If the user explicitly asked to route to an agent, honor that intent first.
    const mergedHandoffs = [];
    const mergedSeen = new Set();
    [...userIntentRelayHandoffs, ...discovered].forEach((h) => {
      const key = [
        String(h?.from || '').toLowerCase(),
        String(h?.target || '').toLowerCase(),
        String(h?.question || '').toLowerCase().slice(0, 260),
      ].join('|');
      if (!key || mergedSeen.has(key)) return;
      mergedSeen.add(key);
      mergedHandoffs.push(h);
    });
    if (mergedHandoffs.length) {
      mergedHandoffs.forEach(h => {
        const isUserDirected = String(h?.source || '').toLowerCase() === 'user-intent';
        if (isUserDirected) {
          // Explicit user-directed handoffs should run even when auto relay budget is exhausted.
          queueRelayHandoff(h, false);
          return;
        }
        if (window.__fridaysChatRelayAuto && _isAutoRelayTargetEnabled(h?.target)) {
          queueRelayHandoff(h, true);
        }
      });
    }

    if (pendingResponses.length) {
      pendingResponses.forEach(entry => {
        _appendThinkingBubble(entry.agent || 'agent', entry.runtime_class || '', {
          job_id: entry.job_id,
          status: 'running',
          stage: 'queued',
          eta_seconds: entry.eta_seconds || 0,
          eta_remaining_seconds: entry.eta_seconds || 0,
          elapsed_ms: 0,
        });
      });
    }

    if (pendingJobs.length) {
      loadingCtl.setPending(allResponses.filter(r => r.pending));
      _pollPendingChatJobs(data.conversation_id, pendingJobs, loadingCtl);
      pollActiveThreadRuntime(true);
    } else {
      loadingCtl.stop(allResponses);
      window.__fridaysChatPendingJobIds = [];
      window.__fridaysChatPendingConversationId = null;
      if (window.__fridaysChatPendingPollTimer) {
        clearInterval(window.__fridaysChatPendingPollTimer);
        window.__fridaysChatPendingPollTimer = null;
      }
      if (data && data.conversation_id) {
        loadConversationMessages(data.conversation_id);
      }
      pollActiveThreadRuntime(true);
    }

    messages.scrollTop = messages.scrollHeight;
  })
  .catch(e => {
    loadingCtl.stop([]);
    window.__fridaysChatPendingJobIds = [];
    window.__fridaysChatPendingConversationId = null;
    if (window.__fridaysChatPendingPollTimer) {
      clearInterval(window.__fridaysChatPendingPollTimer);
      window.__fridaysChatPendingPollTimer = null;
    }
    _appendChatBubble('system', 'Error: ' + e.message);
  })
  .finally(() => {
    _renderChatRelayControls();
    _processRelayQueue();
  });
}

// ── SSE real-time chat updates ──────────────────────────────────────────────
// When an async job status changes via SSE, trigger an immediate poll so the
// UI updates without waiting for the next 2s tick.
document.addEventListener('sse:chat', function(e) {
  try {
    const d = e.detail || {};
    const convId = window.__fridaysChatPendingConversationId;
    if (!convId) return;
    // Only react if this event is for the active conversation
    if (d.conversation_id && String(d.conversation_id) !== String(convId)) return;
    const pendingIds = window.__fridaysChatPendingJobIds || [];
    if (!pendingIds.length) return;
    // If we have a job_id, check it's one we're tracking
    if (d.job_id && !pendingIds.includes(d.job_id)) return;
    // Trigger an immediate status fetch (reuses the existing poll endpoint)
    const q = encodeURIComponent(pendingIds.join(','));
    fetch('/api/chat/jobs/status?conversation_id=' + encodeURIComponent(convId) + '&job_ids=' + q)
      .then(r => r.json())
      .then(data => {
        const jobs = (data && Array.isArray(data.jobs)) ? data.jobs : [];
        (window.__fridaysChatPendingLoadCtls || []).forEach(ctl => {
          try { ctl.updateJobs(jobs); } catch (_) {}
        });
        _renderThreadRuntimePanel(jobs, 'live');
        _syncThinkingBubbles(jobs);
      })
      .catch(() => {});
  } catch (_) {}
});
