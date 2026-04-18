// ═══════════════════════════════════════════════════════════════════════════
// HOME CHAT — lightweight embedded chat on the home page
// Shares conversation data + agent selection with the full Chat window.
// ═══════════════════════════════════════════════════════════════════════════

(function () {
  'use strict';

  // ── State ────────────────────────────────────────────────────────────────
  let _hcConvId = null;
  let _hcConversations = [];
  let _hcSending = false;
  const _hcEnv = (window.ENV_STAGE || 'PROD').toUpperCase();

  // localStorage keys — shared with floating chat (chat.js)
  const HC_ACTIVE_THREAD_KEY = 'fridays-chat-active-thread';
  const HC_AGENT_TOGGLE_PREFIX = 'fridays-chat-thread-agents-';
  const HC_GLOBAL_AGENTS_KEY = 'fridays-chat-enabled-agents';

  // Agent registry — populated from _loadAgentRegistry() in chat.js
  function _hcAgentOptions() {
    return (typeof CHAT_AGENT_OPTIONS !== 'undefined' && Array.isArray(CHAT_AGENT_OPTIONS))
      ? CHAT_AGENT_OPTIONS
      : [];
  }

  // ── Initialization ───────────────────────────────────────────────────────
  window.initHomeChat = function () {
    _hcSetEnvBadge();
    _hcBindEvents();
    _hcRenderAgentPills();
    _hcLoadThreads();
    _hcSetGreeting();
    _hcFetchInterests();
    _hcInitMiniLandscape();
  };

  // ── Environment badge ────────────────────────────────────────────────────
  function _hcSetEnvBadge() {
    const badge = document.getElementById('home-chat-env-badge');
    if (!badge) return;
    const env = _hcEnv.toLowerCase();
    const labels = { prod: 'PROD', dev: 'DEV', uat: 'UAT' };
    badge.textContent = labels[env] || env.toUpperCase();
    badge.setAttribute('data-env', env);
  }

  // ── Event bindings ───────────────────────────────────────────────────────
  function _hcBindEvents() {
    const input = document.getElementById('home-chat-input');
    const sendBtn = document.getElementById('home-chat-send-btn');
    const threadSel = document.getElementById('home-chat-thread-select');
    const newBtn = document.getElementById('home-chat-new-btn');
    const expandBtn = document.getElementById('home-chat-expand-btn');

    if (sendBtn) sendBtn.addEventListener('click', _hcSend);
    if (newBtn) newBtn.addEventListener('click', _hcNewThread);
    if (expandBtn) expandBtn.addEventListener('click', () => {
      if (typeof openWindow === 'function') openWindow('chat', 'Chat', 'view-chat');
    });
    if (threadSel) threadSel.addEventListener('change', (e) => {
      const val = e.target.value;
      if (val) {
        _hcSwitchThread(Number(val));
      } else {
        _hcNewThread();
      }
    });
    if (input) {
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          _hcSend();
        }
      });
      input.addEventListener('input', () => _hcAutoGrow(input));
    }

    // Quick-launch: typing anywhere on home page focuses chat input
    const homePage = document.getElementById('home-page');
    if (homePage && input) {
      homePage.addEventListener('keydown', (e) => {
        // Skip if already in an input/textarea/select, or if modifier keys
        if (e.ctrlKey || e.metaKey || e.altKey) return;
        const tag = (e.target.tagName || '').toLowerCase();
        if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
        if (e.key.length === 1 && !e.target.isContentEditable) {
          input.focus();
          // Let the character flow into the now-focused input naturally
        }
      });
    }
  }

  // ── Auto-grow textarea ───────────────────────────────────────────────────
  function _hcAutoGrow(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
  }

  // ── Load threads ─────────────────────────────────────────────────────────
  function _hcLoadThreads() {
    fetch('/api/conversations')
      .then(r => r.json())
      .then(data => {
        _hcConversations = Array.isArray(data) ? data : [];
        _hcRenderThreadSelect();

        // Restore last active thread
        const saved = localStorage.getItem(HC_ACTIVE_THREAD_KEY);
        const preferred = saved ? Number(saved) : null;
        const match = preferred && _hcConversations.find(c => c.id === preferred);
        if (match) {
          _hcSwitchThread(match.id);
        } else if (_hcConversations.length > 0) {
          _hcSwitchThread(_hcConversations[0].id);
        }
      })
      .catch(() => {});
  }

  function _hcRenderThreadSelect() {
    const sel = document.getElementById('home-chat-thread-select');
    if (!sel) return;
    const current = _hcConvId;
    sel.innerHTML = '<option value="">New conversation</option>' +
      _hcConversations.slice(0, 30).map(c => {
        const title = _hcEsc(c.title || 'Thread #' + c.id).slice(0, 50);
        const sel = c.id === current ? ' selected' : '';
        return `<option value="${c.id}"${sel}>${title}</option>`;
      }).join('');
  }

  // ── Switch thread ────────────────────────────────────────────────────────
  function _hcSwitchThread(convId) {
    _hcConvId = convId;
    localStorage.setItem(HC_ACTIVE_THREAD_KEY, String(convId));
    // Also sync with floating chat
    if (typeof window.__fridaysChatConversationId !== 'undefined') {
      window.__fridaysChatConversationId = convId;
    }
    _hcRenderThreadSelect();
    _hcLoadMessages(convId);
    _hcRenderAgentPills();
  }

  function _hcNewThread() {
    _hcConvId = null;
    localStorage.removeItem(HC_ACTIVE_THREAD_KEY);
    const sel = document.getElementById('home-chat-thread-select');
    if (sel) sel.value = '';
    _hcClearMessages();
    _hcShowWelcome(true);
    _hcRenderAgentPills();
    _hcUpdateMeta();
  }

  // ── Load messages ────────────────────────────────────────────────────────
  function _hcLoadMessages(convId) {
    fetch(`/api/conversations/${convId}/messages`)
      .then(r => r.json())
      .then(data => {
        const msgs = data.messages || [];
        _hcClearMessages();
        if (msgs.length === 0) {
          _hcShowWelcome(true);
          return;
        }
        _hcShowWelcome(false);
        msgs.forEach(m => _hcAppendBubble(m));
        _hcScrollBottom();
      })
      .catch(() => {});
  }

  // ── Render bubbles ───────────────────────────────────────────────────────
  function _hcClearMessages() {
    const container = document.getElementById('home-chat-messages');
    if (!container) return;
    // Remove all bubbles but keep welcome
    container.querySelectorAll('.hc-bubble').forEach(b => b.remove());
  }

  function _hcShowWelcome(show) {
    const w = document.querySelector('.home-chat-welcome');
    if (w) w.style.display = show ? 'flex' : 'none';
  }

  function _hcAppendBubble(msg) {
    const container = document.getElementById('home-chat-messages');
    if (!container) return;
    _hcShowWelcome(false);

    const sender = (msg.sender || msg.from_agent || '').toLowerCase();
    const isUser = sender === 'user' || sender === 'you' || msg.message_type === 'user';
    const isSystem = msg.message_type === 'system';
    const type = isUser ? 'hc-user' : isSystem ? 'hc-system' : 'hc-agent';
    const agentLabel = isUser ? 'You' : _hcAgentDisplayName(sender);

    const time = msg.created_at ? _hcFormatTime(msg.created_at) : '';
    const content = _hcRenderContent(msg.content || '');

    const div = document.createElement('div');
    div.className = `hc-bubble ${type}`;
    div.innerHTML =
      `<div class="hc-bubble-header">` +
        `<span class="hc-bubble-sender">${_hcEsc(agentLabel)}</span>` +
        (time ? `<span class="hc-bubble-time">${time}</span>` : '') +
      `</div>` +
      `<div class="hc-bubble-body">${content}</div>`;

    container.appendChild(div);
  }

  function _hcAgentDisplayName(name) {
    const agents = _hcAgentOptions();
    const match = agents.find(a => a.value === name || a.label?.toLowerCase() === name);
    return match ? match.label : (name.charAt(0).toUpperCase() + name.slice(1));
  }

  function _hcRenderContent(text) {
    // Use marked if available, otherwise basic formatting
    if (typeof marked !== 'undefined' && marked.parse) {
      try { return marked.parse(text); } catch (e) { /* fall through */ }
    }
    return _hcEsc(text).replace(/\n/g, '<br>');
  }

  function _hcFormatTime(ts) {
    try {
      const d = new Date(ts);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch (e) {
      return '';
    }
  }

  function _hcScrollBottom() {
    const container = document.getElementById('home-chat-messages');
    if (container) {
      requestAnimationFrame(() => {
        container.scrollTop = container.scrollHeight;
      });
    }
  }

  // ── Agent pills ──────────────────────────────────────────────────────────
  function _hcRenderAgentPills() {
    const host = document.getElementById('home-chat-agents');
    if (!host) return;
    const agents = _hcAgentOptions();
    if (agents.length === 0) {
      // Retry once after agent registry loads
      setTimeout(() => {
        const a2 = _hcAgentOptions();
        if (a2.length > 0) _hcRenderAgentPills();
      }, 1500);
      return;
    }

    const enabled = _hcGetEnabledAgents();
    host.innerHTML = agents.map(a => {
      const active = enabled.includes(a.value) ? ' active' : '';
      const tierClass = (a.tier === 'paid' || a.tier === 'online') ? 'paid' : 'local';
      return `<button class="home-chat-agent-pill${active}" data-agent="${_hcEsc(a.value)}" title="${_hcEsc(a.label)}">` +
        `<span class="agent-dot ${tierClass}"></span>${_hcEsc(a.label)}</button>`;
    }).join('');

    host.querySelectorAll('.home-chat-agent-pill').forEach(btn => {
      btn.addEventListener('click', () => {
        btn.classList.toggle('active');
        _hcSaveEnabledAgents();
        _hcUpdateMeta();
      });
    });
    _hcUpdateMeta();
  }

  function _hcGetEnabledAgents() {
    // Per-thread agents first, then global fallback
    if (_hcConvId) {
      const perThread = localStorage.getItem(HC_AGENT_TOGGLE_PREFIX + _hcConvId);
      if (perThread) {
        try { return JSON.parse(perThread); } catch (e) { /* fall through */ }
      }
    }
    const global = localStorage.getItem(HC_GLOBAL_AGENTS_KEY);
    if (global) {
      try { return JSON.parse(global); } catch (e) { /* fall through */ }
    }
    // Default: first local agent
    const agents = _hcAgentOptions();
    return agents.length > 0 ? [agents[0].value] : [];
  }

  function _hcSaveEnabledAgents() {
    const pills = document.querySelectorAll('#home-chat-agents .home-chat-agent-pill.active');
    const enabled = Array.from(pills).map(p => p.dataset.agent);
    // Save both per-thread and global
    if (_hcConvId) {
      localStorage.setItem(HC_AGENT_TOGGLE_PREFIX + _hcConvId, JSON.stringify(enabled));
    }
    localStorage.setItem(HC_GLOBAL_AGENTS_KEY, JSON.stringify(enabled));
    // Sync floating chat agent state
    if (typeof renderChatAgentToggles === 'function') {
      try { renderChatAgentToggles(); } catch (e) { /* ignore */ }
    }
  }

  function _hcUpdateMeta() {
    const countEl = document.getElementById('home-chat-agent-count');
    if (countEl) {
      const n = document.querySelectorAll('#home-chat-agents .home-chat-agent-pill.active').length;
      countEl.textContent = `${n} agent${n !== 1 ? 's' : ''} on`;
    }
  }

  // ── Send message ─────────────────────────────────────────────────────────
  function _hcSend() {
    if (_hcSending) return;
    const input = document.getElementById('home-chat-input');
    const sendBtn = document.getElementById('home-chat-send-btn');
    if (!input) return;
    const text = input.value.trim();
    if (!text) return;

    const enabled = [];
    document.querySelectorAll('#home-chat-agents .home-chat-agent-pill.active').forEach(p => {
      enabled.push(p.dataset.agent);
    });
    if (enabled.length === 0) {
      if (typeof showToast === 'function') showToast('Select at least one agent', 'warning');
      return;
    }

    // Show user bubble immediately
    _hcAppendBubble({
      sender: 'user',
      message_type: 'user',
      content: text,
      created_at: new Date().toISOString()
    });
    _hcScrollBottom();

    input.value = '';
    input.style.height = 'auto';
    _hcSending = true;
    if (sendBtn) sendBtn.classList.add('sending');
    sendBtn && (sendBtn.disabled = true);

    const statusEl = document.getElementById('home-chat-status');
    if (statusEl) statusEl.textContent = 'Sending…';

    const body = {
      message: text,
      agents: enabled,
      conversation_id: _hcConvId || null,
      new_thread: !_hcConvId,
      history_mode: 'recent',
      history_limit: 12,
      auto_relay: false
    };

    fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })
      .then(r => r.json())
      .then(data => {
        if (data.conversation_id && !_hcConvId) {
          _hcConvId = data.conversation_id;
          localStorage.setItem(HC_ACTIVE_THREAD_KEY, String(_hcConvId));
          _hcSaveEnabledAgents();
          // Refresh thread list to show the new thread
          _hcLoadThreads();
        }

        // Render agent responses
        if (data.responses && data.responses.length > 0) {
          data.responses.forEach(resp => {
            _hcAppendBubble({
              sender: resp.agent || 'agent',
              message_type: 'agent',
              content: resp.response || resp.text || '(no response)',
              created_at: new Date().toISOString()
            });
          });
        } else if (data.response) {
          _hcAppendBubble({
            sender: data.agent || 'agent',
            message_type: 'agent',
            content: data.response,
            created_at: new Date().toISOString()
          });
        }

        // Handle pending jobs (async agents)
        if (data.pending_jobs && data.pending_jobs.length > 0) {
          data.pending_jobs.forEach(job => {
            _hcAppendBubble({
              sender: job.agent || 'agent',
              message_type: 'system',
              content: `⏳ ${job.agent || 'Agent'} is thinking…`,
              created_at: new Date().toISOString()
            });
          });
          _hcPollJobs(data.pending_jobs.map(j => j.job_id));
        }

        _hcScrollBottom();
      })
      .catch(err => {
        _hcAppendBubble({
          sender: 'system',
          message_type: 'system',
          content: `Error: ${err.message || 'Send failed'}`,
          created_at: new Date().toISOString()
        });
        _hcScrollBottom();
      })
      .finally(() => {
        _hcSending = false;
        if (sendBtn) {
          sendBtn.classList.remove('sending');
          sendBtn.disabled = false;
        }
        if (statusEl) statusEl.textContent = 'Ready';
      });
  }

  // ── Poll pending jobs ────────────────────────────────────────────────────
  function _hcPollJobs(jobIds) {
    if (!jobIds || jobIds.length === 0) return;
    const statusEl = document.getElementById('home-chat-status');

    const poll = () => {
      fetch('/api/chat/jobs/status', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_ids: jobIds })
      })
        .then(r => r.json())
        .then(data => {
          const jobs = data.jobs || [];
          let allDone = true;

          jobs.forEach(job => {
            if (job.status === 'completed' && job.response) {
              // Remove the "thinking" bubble for this agent
              const thinkBubbles = document.querySelectorAll('#home-chat-messages .hc-bubble.hc-system');
              thinkBubbles.forEach(b => {
                if (b.textContent.includes(job.agent) && b.textContent.includes('thinking')) {
                  b.remove();
                }
              });
              _hcAppendBubble({
                sender: job.agent,
                message_type: 'agent',
                content: job.response,
                created_at: new Date().toISOString()
              });
              _hcScrollBottom();
            } else if (job.status === 'failed') {
              _hcAppendBubble({
                sender: job.agent || 'system',
                message_type: 'system',
                content: `${job.agent || 'Agent'} failed: ${job.error || 'unknown error'}`,
                created_at: new Date().toISOString()
              });
              _hcScrollBottom();
            } else if (job.status === 'running' || job.status === 'queued') {
              allDone = false;
              // Update stage in the thinking bubble
              if (job.stage) {
                const thinkBubbles = document.querySelectorAll('#home-chat-messages .hc-bubble.hc-system');
                thinkBubbles.forEach(b => {
                  if (b.textContent.includes(job.agent)) {
                    const body = b.querySelector('.hc-bubble-body');
                    if (body) body.innerHTML = `<span class="hc-thinking-dot"></span> ${_hcEsc(job.agent)} &middot; ${_hcEsc(job.stage)}`;
                  }
                });
              }
            }
          });

          if (!allDone) {
            if (statusEl) statusEl.textContent = 'Agents working…';
            setTimeout(poll, 2000);
          } else {
            if (statusEl) statusEl.textContent = 'Ready';
          }
        })
        .catch(() => {
          if (statusEl) statusEl.textContent = 'Ready';
        });
    };

    setTimeout(poll, 2000);
  }

  // ── Utilities ────────────────────────────────────────────────────────────
  function _hcEsc(v) {
    return String(v ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // Expose for cross-module refresh (agent registry reload)
  window._hcRenderAgentPills = _hcRenderAgentPills;

  // ── Greeting ─────────────────────────────────────────────────────────────
  function _hcSetGreeting() {
    const el = document.getElementById('home-welcome-greeting');
    if (!el) return;
    const h = new Date().getHours();
    const period = h < 5 ? 'Late night' : h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : h < 21 ? 'Good evening' : 'Late night';
    el.textContent = period;
  }

  // ── Interests fetch & render ─────────────────────────────────────────────
  function _hcFetchInterests() {
    fetch('/api/interests?limit=8')
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(data => {
        _hcRenderInterestCards(data.interests || []);
        _hcRenderResearchTopics(data.research_topics || []);
      })
      .catch(() => {}); // Silently degrade if endpoint missing
  }

  function _hcRenderInterestCards(interests) {
    const row = document.getElementById('home-interests-row');
    if (!row || interests.length === 0) return;

    const icons = { memory: '🧠', patterns: '📊', conversations: '💬' };
    row.innerHTML = interests.map(item => {
      const topSrc = item.sources[item.sources.length - 1] || 'conversations';
      const icon = icons[topSrc] || '💬';
      return `<button class="home-interest-card" data-suggestion="${_hcEsc(item.suggestion)}" title="${_hcEsc(item.suggestion)}">` +
        `<span class="home-interest-icon">${icon}</span>` +
        `<span>${_hcEsc(item.topic)}</span>` +
        `<span class="home-interest-source" data-src="${topSrc}">${topSrc}</span>` +
        `</button>`;
    }).join('');

    row.querySelectorAll('.home-interest-card').forEach(card => {
      card.addEventListener('click', () => {
        const suggestion = card.dataset.suggestion;
        if (!suggestion) return;
        const input = document.getElementById('home-chat-input');
        if (input) {
          input.value = suggestion;
          input.focus();
          input.dispatchEvent(new Event('input'));
        }
      });
    });
  }

  function _hcRenderResearchTopics(topics) {
    const row = document.getElementById('home-research-row');
    if (!row || topics.length === 0) return;

    row.innerHTML = '<span style="font-size:9px;color:var(--text-dim);opacity:0.6;text-transform:uppercase;letter-spacing:0.5px;font-weight:700;">Research:</span> ' +
      topics.map(t => {
        const status = (t.status || '').toLowerCase();
        return `<button class="home-research-tag" data-status="${status}" data-topic="${_hcEsc(t.topic)}" title="Research: ${_hcEsc(t.topic)}">` +
          `${_hcEsc(t.topic)}</button>`;
      }).join('');

    row.querySelectorAll('.home-research-tag').forEach(tag => {
      tag.addEventListener('click', () => {
        const topic = tag.dataset.topic;
        if (!topic) return;
        const input = document.getElementById('home-chat-input');
        if (input) {
          input.value = `What did the research on "${topic}" find?`;
          input.focus();
        }
      });
    });
  }

  // ── Mini memory landscape (ambient background) ───────────────────────────
  let _hcMiniLandscapeActive = false;
  let _hcMiniAnimFrame = null;

  function _hcInitMiniLandscape() {
    const canvas = document.getElementById('home-mini-landscape');
    if (!canvas) return;

    // Fetch memory data if not cached
    if (!window.__memoryCache || window.__memoryCache.length === 0) {
      fetch('/api/memory?limit=300&min=1')
        .then(r => r.ok ? r.json() : Promise.reject())
        .then(data => {
          // Flatten results into cache format
          const flat = [];
          const results = data.results || {};
          for (const [agent, entries] of Object.entries(results)) {
            entries.forEach(e => flat.push({ ...e, _agent: agent }));
          }
          if (flat.length > 0) {
            window.__memoryCache = flat;
            _hcStartMiniLandscape(canvas);
          }
        })
        .catch(() => {});
    } else {
      _hcStartMiniLandscape(canvas);
    }
  }

  function _hcStartMiniLandscape(canvas) {
    if (_hcMiniLandscapeActive) return;
    _hcMiniLandscapeActive = true;

    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const cache = window.__memoryCache || [];
    if (!cache.length) return;

    // Build simplified node data
    const agentCounts = {};
    const agentTags = {};
    const globalTags = {};

    cache.forEach(m => {
      const agent = m._agent || m.agent || 'unknown';
      agentCounts[agent] = (agentCounts[agent] || 0) + 1;
      if (!agentTags[agent]) agentTags[agent] = {};
      const tags = String(m.tags || '').split(',').map(t => t.trim().toLowerCase()).filter(Boolean);
      tags.forEach(t => {
        agentTags[agent][t] = (agentTags[agent][t] || 0) + 1;
        globalTags[t] = (globalTags[t] || 0) + 1;
      });
    });

    const agents = Object.keys(agentCounts);
    const topTags = Object.entries(globalTags)
      .filter(([tag]) => {
        let cnt = 0;
        for (const at of Object.values(agentTags)) { if (at[tag]) cnt++; }
        return cnt >= 2;
      })
      .sort((a, b) => b[1] - a[1]).slice(0, 12).map(([t]) => t);

    // Create nodes
    const nodes = [];
    const palette = ['#ff6b6b','#ffa500','#ffc800','#4caf50','#00bcd4','#2563eb','#9333ea','#ec4899','#6cb6ff','#00d084','#f59e0b','#8b5cf6'];
    let ci = 0;

    agents.forEach((agent, i) => {
      const angle = (i / agents.length) * Math.PI * 2;
      const r = 100 + Math.random() * 60;
      nodes.push({
        id: 'a:' + agent, label: agent, type: 'agent',
        x: 300 + Math.cos(angle) * r, y: 200 + Math.sin(angle) * r,
        vx: 0, vy: 0,
        size: Math.min(5 + Math.sqrt(agentCounts[agent]) * 2, 16),
        color: palette[ci++ % palette.length],
      });
    });

    topTags.forEach((tag, i) => {
      const angle = (i / topTags.length) * Math.PI * 2 + 0.5;
      const r = 50 + Math.random() * 30;
      nodes.push({
        id: 't:' + tag, label: tag, type: 'tag',
        x: 300 + Math.cos(angle) * r, y: 200 + Math.sin(angle) * r,
        vx: 0, vy: 0, size: 3, color: 'rgba(108,182,255,0.4)',
      });
    });

    // Build links
    const links = [];
    const nodeMap = {};
    nodes.forEach(n => { nodeMap[n.id] = n; });
    agents.forEach(agent => {
      topTags.forEach(tag => {
        if (agentTags[agent] && agentTags[agent][tag]) {
          links.push({ source: 'a:' + agent, target: 't:' + tag, weight: agentTags[agent][tag] });
        }
      });
    });

    // Gentle animation loop — low CPU
    function tick() {
      if (!_hcMiniLandscapeActive) return;

      const rect = canvas.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) {
        _hcMiniAnimFrame = requestAnimationFrame(tick);
        return;
      }
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const w = rect.width, h = rect.height;

      // Very gentle physics
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i], b = nodes[j];
          let dx = b.x - a.x, dy = b.y - a.y;
          let dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = 400 / (dist * dist);
          const fx = (dx / dist) * force, fy = (dy / dist) * force;
          a.vx -= fx; a.vy -= fy;
          b.vx += fx; b.vy += fy;
        }
      }
      links.forEach(l => {
        const a = nodeMap[l.source], b = nodeMap[l.target];
        if (!a || !b) return;
        let dx = b.x - a.x, dy = b.y - a.y;
        let dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const force = (dist - 80) * 0.003;
        const fx = (dx / dist) * force, fy = (dy / dist) * force;
        a.vx += fx; a.vy += fy;
        b.vx -= fx; b.vy -= fy;
      });
      nodes.forEach(n => {
        n.vx += (w / 2 - n.x) * 0.0003;
        n.vy += (h / 2 - n.y) * 0.0003;
        n.vx *= 0.92; n.vy *= 0.92;
        n.x += n.vx; n.y += n.vy;
      });

      // Render
      ctx.clearRect(0, 0, w, h);
      links.forEach(l => {
        const a = nodeMap[l.source], b = nodeMap[l.target];
        if (!a || !b) return;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.strokeStyle = 'rgba(255,255,255,0.04)';
        ctx.lineWidth = 1;
        ctx.stroke();
      });
      nodes.forEach(n => {
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.size, 0, Math.PI * 2);
        ctx.fillStyle = n.type === 'agent' ? (n.color + '22') : 'rgba(108,182,255,0.08)';
        ctx.fill();
        ctx.strokeStyle = n.type === 'agent' ? (n.color + '44') : 'rgba(108,182,255,0.15)';
        ctx.lineWidth = 0.8;
        ctx.stroke();
      });

      _hcMiniAnimFrame = requestAnimationFrame(tick);
    }
    tick();

    // Stop animation when welcome state is hidden
    const observer = new MutationObserver(() => {
      const welcome = document.querySelector('.home-chat-welcome');
      if (welcome && welcome.style.display === 'none') {
        _hcMiniLandscapeActive = false;
        if (_hcMiniAnimFrame) cancelAnimationFrame(_hcMiniAnimFrame);
      }
    });
    const welcome = document.querySelector('.home-chat-welcome');
    if (welcome) observer.observe(welcome, { attributes: true, attributeFilter: ['style'] });
  }

})();
