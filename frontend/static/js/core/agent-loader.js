/* Shared by the home tile and the full chat agent selectors. */
(function () {
  const states = new Map();
  const pending = new Map();

  function publish(agent, state) {
    states.set(agent, state);
    document.querySelectorAll('[data-agent-load-status]').forEach(el => {
      if (el.dataset.agentLoadStatus !== agent) return;
      el.textContent = state.text;
      el.title = state.text;
      el.setAttribute('role', 'status');
    });
  }

  function placementText(event) {
    if (event.placement === 'ram') return 'normal RAM / CPU';
    if (event.placement_source === 'kernel') {
      return `${event.vram_gb} GiB GPU VRAM + ${event.gpu_host_ram_gb} GiB normal RAM (GPU-accessible)`;
    }
    if (event.placement === 'gpu+ram') return `GPU + normal RAM (${event.gpu_layers}/${event.total_layers} GPU layers)`;
    if (event.placement === 'gpu') return `GPU (${event.gpu_layers}/${event.total_layers} layers)`;
    return 'placement not reported by runtime';
  }

  window.agentLoadState = agent => states.get(agent);
  window.warmChatAgent = function (agent) {
    if (pending.has(agent)) return pending.get(agent);
    const config = (window.__agentsData || []).find(a => a.name === agent);
    if (!config || !config.enabled) {
      const error = new Error('Agent registry is not ready or the agent is disabled');
      publish(agent, { text: error.message, error: true });
      if (typeof showToast === 'function') showToast(error.message, 'error');
      return Promise.resolve();
    }
    if (config.tier !== 'local') {
      publish(agent, { text: 'Online agent — no local model to load' });
      return Promise.resolve();
    }
    const started = Date.now();
    let stage = 'Requesting model load';
    let ready = false;
    const update = () => publish(agent, { text: `${stage} · ${Math.floor((Date.now() - started) / 1000)}s`, loading: true });
    update();
    const timer = setInterval(update, 1000);
    const task = (async () => {
      try {
        const response = await fetch(`/api/agents/${encodeURIComponent(agent)}/load`, { method: 'POST' });
        if (!response.ok) {
          const data = await response.json();
          throw new Error(data.error || `Model load failed (HTTP ${response.status})`);
        }
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        function event(line) {
          if (!line.trim()) return;
          const data = JSON.parse(line);
          if (data.stage === 'error') throw new Error(data.error || 'Model load failed');
          if (data.stage === 'ready') {
            ready = true;
            clearInterval(timer);
            publish(agent, { text: `Ready · ${placementText(data)}`, ready: true });
          } else if (data.stage !== 'waiting') {
            const names = { requested: 'Requesting model load', queued: 'Waiting for model slot', checking_memory: 'Checking GPU and RAM' };
            stage = names[data.stage] || 'Loading model';
            if (data.stage === 'loading') {
              stage = data.placement_estimate === 'ram' ? 'Loading into normal RAM / CPU'
                : data.placement_estimate === 'gpu+ram' ? 'Loading · limited GPU space, using normal RAM too (estimated)'
                  : data.placement_estimate === 'gpu' ? 'Loading · GPU preferred (estimated)'
                    : 'Loading model · placement not yet known';
            }
            update();
          }
        }
        while (true) {
          const chunk = await reader.read();
          buffer += decoder.decode(chunk.value || new Uint8Array(), { stream: !chunk.done });
          let newline;
          while ((newline = buffer.indexOf('\n')) >= 0) {
            event(buffer.slice(0, newline));
            buffer = buffer.slice(newline + 1);
          }
          if (chunk.done) break;
        }
        if (buffer.trim()) event(buffer);
        if (!ready) throw new Error('Model load ended without runtime readiness confirmation');
      } catch (error) {
        publish(agent, { text: `Load failed: ${error.message}`, error: true });
        if (typeof showToast === 'function') showToast(`${agent}: ${error.message}`, 'error');
      } finally {
        clearInterval(timer);
        pending.delete(agent);
      }
    })();
    pending.set(agent, task);
    return task;
  };
})();
