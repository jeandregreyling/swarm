// memory-landscape.js — Force-directed graph of agent memory relationships
// Nodes: agents (large) + top tags (small)
// Links: agent → tag when the agent has memories with that tag

let _mlActive = false;
let _mlAnimFrame = null;
let _mlNodes = [];
let _mlLinks = [];
let _mlDrag = null;
let _mlPan = { x: 0, y: 0 };
let _mlScale = 1;

function _memToggleLandscape() {
  const canvas = document.getElementById('memory-landscape-canvas');
  const list = document.getElementById('memory-list');
  const detail = document.getElementById('mem-detail');
  const btn = document.getElementById('memory-landscape-btn');
  if (!canvas || !list) return;

  _mlActive = !_mlActive;
  canvas.style.display = _mlActive ? 'block' : 'none';
  canvas.style.flex = _mlActive ? '1' : '';
  list.style.display = _mlActive ? 'none' : '';
  if (detail) detail.style.display = _mlActive ? 'none' : detail.style.display;
  if (btn) btn.classList.toggle('active', _mlActive);

  if (_mlActive) {
    _mlBuildGraph();
    _mlStartAnimation(canvas);
  } else {
    if (_mlAnimFrame) cancelAnimationFrame(_mlAnimFrame);
    _mlAnimFrame = null;
  }
}

function _mlBuildGraph() {
  const cache = window.__memoryCache || [];
  if (!cache.length) return;

  // Count memories per agent and collect tag frequencies
  const agentCounts = {};
  const agentTags = {};   // {agent: {tag: count}}
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

  // Top 20 tags that appear across multiple agents
  const multiAgentTags = Object.entries(globalTags)
    .filter(([tag]) => {
      let count = 0;
      for (const at of Object.values(agentTags)) {
        if (at[tag]) count++;
      }
      return count >= 2;
    })
    .sort((a, b) => b[1] - a[1])
    .slice(0, 20)
    .map(([tag]) => tag);

  // Build nodes
  _mlNodes = [];
  const agents = Object.keys(agentCounts);
  const cx = 400, cy = 250;

  agents.forEach((agent, i) => {
    const angle = (i / agents.length) * Math.PI * 2;
    const r = 120 + Math.random() * 40;
    _mlNodes.push({
      id: 'a:' + agent,
      label: agent,
      type: 'agent',
      x: cx + Math.cos(angle) * r,
      y: cy + Math.sin(angle) * r,
      vx: 0, vy: 0,
      size: Math.min(8 + Math.sqrt(agentCounts[agent]) * 3, 24),
      count: agentCounts[agent],
    });
  });

  multiAgentTags.forEach((tag, i) => {
    const angle = (i / multiAgentTags.length) * Math.PI * 2 + 0.3;
    const r = 60 + Math.random() * 30;
    _mlNodes.push({
      id: 't:' + tag,
      label: tag,
      type: 'tag',
      x: cx + Math.cos(angle) * r,
      y: cy + Math.sin(angle) * r,
      vx: 0, vy: 0,
      size: Math.min(4 + Math.sqrt(globalTags[tag]) * 1.5, 12),
      count: globalTags[tag],
    });
  });

  // Build links: agent ↔ tag
  _mlLinks = [];
  agents.forEach(agent => {
    multiAgentTags.forEach(tag => {
      if (agentTags[agent] && agentTags[agent][tag]) {
        _mlLinks.push({
          source: 'a:' + agent,
          target: 't:' + tag,
          weight: agentTags[agent][tag],
        });
      }
    });
  });

  _mlPan = { x: 0, y: 0 };
  _mlScale = 1;
}

function _mlStartAnimation(canvas) {
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;

  function resize() {
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  resize();

  // Mouse interaction
  let mouseDown = false, lastMouse = null, hoverNode = null;

  canvas.onmousedown = (e) => {
    const pos = _mlScreenToWorld(e, canvas);
    const hit = _mlHitTest(pos.x, pos.y);
    if (hit) {
      _mlDrag = hit;
      hit.vx = 0; hit.vy = 0;
    } else {
      mouseDown = true;
      lastMouse = { x: e.clientX, y: e.clientY };
    }
    canvas.style.cursor = hit ? 'grabbing' : 'grabbing';
  };
  canvas.onmousemove = (e) => {
    if (_mlDrag) {
      const pos = _mlScreenToWorld(e, canvas);
      _mlDrag.x = pos.x;
      _mlDrag.y = pos.y;
    } else if (mouseDown && lastMouse) {
      _mlPan.x += e.clientX - lastMouse.x;
      _mlPan.y += e.clientY - lastMouse.y;
      lastMouse = { x: e.clientX, y: e.clientY };
    } else {
      const pos = _mlScreenToWorld(e, canvas);
      hoverNode = _mlHitTest(pos.x, pos.y);
      canvas.style.cursor = hoverNode ? 'pointer' : 'grab';
    }
  };
  canvas.onmouseup = () => {
    _mlDrag = null;
    mouseDown = false;
    lastMouse = null;
    canvas.style.cursor = 'grab';
  };
  canvas.onwheel = (e) => {
    e.preventDefault();
    const factor = e.deltaY > 0 ? 0.92 : 1.08;
    _mlScale = Math.max(0.3, Math.min(3, _mlScale * factor));
  };

  const agentColors = {};
  const palette = ['#ff6b6b','#ffa500','#ffc800','#4caf50','#00bcd4','#2563eb','#9333ea','#ec4899','#6cb6ff','#00d084','#f59e0b','#8b5cf6','#ef4444'];
  let ci = 0;

  function tick() {
    if (!_mlActive) return;
    resize();
    const w = canvas.getBoundingClientRect().width;
    const h = canvas.getBoundingClientRect().height;

    // Physics: repulsion + spring + damping
    const nodes = _mlNodes;
    const links = _mlLinks;
    const nodeMap = {};
    nodes.forEach(n => { nodeMap[n.id] = n; });

    // Repulsion between all nodes
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j];
        let dx = b.x - a.x, dy = b.y - a.y;
        let dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const force = 800 / (dist * dist);
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        if (a !== _mlDrag) { a.vx -= fx; a.vy -= fy; }
        if (b !== _mlDrag) { b.vx += fx; b.vy += fy; }
      }
    }

    // Spring attraction along links
    links.forEach(l => {
      const a = nodeMap[l.source], b = nodeMap[l.target];
      if (!a || !b) return;
      let dx = b.x - a.x, dy = b.y - a.y;
      let dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const idealDist = 100;
      const force = (dist - idealDist) * 0.005;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      if (a !== _mlDrag) { a.vx += fx; a.vy += fy; }
      if (b !== _mlDrag) { b.vx -= fx; b.vy -= fy; }
    });

    // Center gravity
    nodes.forEach(n => {
      if (n === _mlDrag) return;
      n.vx += (w / 2 - n.x) * 0.0005;
      n.vy += (h / 2 - n.y) * 0.0005;
    });

    // Damping + position update
    nodes.forEach(n => {
      if (n === _mlDrag) return;
      n.vx *= 0.9;
      n.vy *= 0.9;
      n.x += n.vx;
      n.y += n.vy;
    });

    // Render
    ctx.clearRect(0, 0, w, h);
    ctx.save();
    ctx.translate(_mlPan.x, _mlPan.y);
    ctx.scale(_mlScale, _mlScale);

    // Draw links
    links.forEach(l => {
      const a = nodeMap[l.source], b = nodeMap[l.target];
      if (!a || !b) return;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.strokeStyle = 'rgba(255,255,255,0.08)';
      ctx.lineWidth = Math.min(l.weight * 0.5, 3);
      ctx.stroke();
    });

    // Draw nodes
    nodes.forEach(n => {
      if (n.type === 'agent') {
        if (!agentColors[n.label]) agentColors[n.label] = palette[ci++ % palette.length];
        const color = agentColors[n.label];
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.size, 0, Math.PI * 2);
        ctx.fillStyle = color + '44';
        ctx.fill();
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.5;
        ctx.stroke();
        // Label
        ctx.fillStyle = color;
        ctx.font = 'bold 10px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(n.label, n.x, n.y + n.size + 12);
        // Count badge
        ctx.fillStyle = 'rgba(255,255,255,0.5)';
        ctx.font = '8px sans-serif';
        ctx.fillText(n.count + ' memories', n.x, n.y + n.size + 22);
      } else {
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.size, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(108,182,255,0.2)';
        ctx.fill();
        ctx.strokeStyle = 'rgba(108,182,255,0.5)';
        ctx.lineWidth = 1;
        ctx.stroke();
        if (n.size > 5 || n === hoverNode) {
          ctx.fillStyle = 'rgba(108,182,255,0.7)';
          ctx.font = '8px sans-serif';
          ctx.textAlign = 'center';
          ctx.fillText(n.label, n.x, n.y + n.size + 10);
        }
      }
    });

    // Hover tooltip
    if (hoverNode) {
      const tipX = hoverNode.x + hoverNode.size + 8;
      const tipY = hoverNode.y - 8;
      const text = hoverNode.type === 'agent'
        ? `${hoverNode.label}: ${hoverNode.count} memories`
        : `#${hoverNode.label}: used ${hoverNode.count} times`;
      ctx.fillStyle = 'rgba(0,0,0,0.8)';
      const tw = ctx.measureText(text).width + 12;
      ctx.fillRect(tipX, tipY - 10, tw, 18);
      ctx.fillStyle = '#fff';
      ctx.font = '10px sans-serif';
      ctx.textAlign = 'left';
      ctx.fillText(text, tipX + 6, tipY + 2);
    }

    ctx.restore();
    _mlAnimFrame = requestAnimationFrame(tick);
  }

  tick();
}

function _mlScreenToWorld(e, canvas) {
  const rect = canvas.getBoundingClientRect();
  return {
    x: (e.clientX - rect.left - _mlPan.x) / _mlScale,
    y: (e.clientY - rect.top - _mlPan.y) / _mlScale,
  };
}

function _mlHitTest(wx, wy) {
  for (let i = _mlNodes.length - 1; i >= 0; i--) {
    const n = _mlNodes[i];
    const dx = wx - n.x, dy = wy - n.y;
    if (dx * dx + dy * dy <= (n.size + 4) * (n.size + 4)) return n;
  }
  return null;
}
