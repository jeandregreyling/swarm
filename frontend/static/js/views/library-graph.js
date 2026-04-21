'use strict';

/* ──────────────────────────────────────────────────────────────────────────
   library-graph.js — Knowledge Graph for the Library
   Force-directed graph: source nodes (large, category-coloured) + tag nodes
   (small connectors). Sources sharing tags cluster together naturally.

   Exposes: libGraphInit(sources), libGraphHighlight(q), libGraphReset()
────────────────────────────────────────────────────────────────────────── */

const _LG_CAT_COLORS = {
  sap_corner:  '#f7b84b',
  programming: '#5bc0de',
  fridays:     '#5cb85c',
  general:     '#9b9b9b',
};

let _lgNodes   = [];
let _lgLinks   = [];
let _lgCanvas  = null;
let _lgCtx     = null;
let _lgRaf     = null;
let _lgDrag    = null;
let _lgHover   = null;
let _lgPan     = { x: 0, y: 0 };
let _lgScale   = 1;
let _lgPanStart= null;
let _lgFilter  = '';   // highlighted query
let _lgOnClick = null; // callback(sourceObj)

function libGraphInit(sources, canvas, onClickCb) {
  _lgCanvas  = canvas;
  _lgOnClick = onClickCb || null;
  _lgFilter  = '';
  _lgPan     = { x: 0, y: 0 };
  _lgScale   = 1;

  if (_lgRaf) { cancelAnimationFrame(_lgRaf); _lgRaf = null; }

  _lgBuildGraph(sources);
  _lgAttachEvents(canvas);
  _lgAnimate();
}

function libGraphHighlight(q) {
  _lgFilter = (q || '').toLowerCase();
}

function libGraphReset() {
  _lgFilter = '';
}

function libGraphDestroy() {
  if (_lgRaf) { cancelAnimationFrame(_lgRaf); _lgRaf = null; }
}

/* ── Graph construction ─────────────────────────────────────────────────── */

function _lgBuildGraph(sources) {
  const W = _lgCanvas.width;
  const H = _lgCanvas.height;
  const cx = W / 2, cy = H / 2;

  _lgNodes = [];
  _lgLinks = [];
  const nodeMap = {};

  // Source nodes
  sources.forEach(s => {
    const tags = _lgParseTags(s.domain_tags);
    const id   = `src-${s.source_id}`;
    const r    = 14 + Math.min(tags.length, 6) * 2;
    const angle = Math.random() * Math.PI * 2;
    const dist  = 80 + Math.random() * 160;
    const node = {
      id, type: 'source', source: s,
      label: s.title.length > 22 ? s.title.slice(0, 20) + '…' : s.title,
      color: _LG_CAT_COLORS[s.category] || '#9b9b9b',
      r,
      x: cx + Math.cos(angle) * dist,
      y: cy + Math.sin(angle) * dist,
      vx: 0, vy: 0,
    };
    _lgNodes.push(node);
    nodeMap[id] = node;
  });

  // Tag nodes (unique tags)
  const tagSet = new Set();
  sources.forEach(s => _lgParseTags(s.domain_tags).forEach(t => tagSet.add(t)));

  tagSet.forEach(tag => {
    const id    = `tag-${tag}`;
    const angle = Math.random() * Math.PI * 2;
    const dist  = 40 + Math.random() * 120;
    const node = {
      id, type: 'tag', label: tag,
      color: '#666', r: 7,
      x: cx + Math.cos(angle) * dist,
      y: cy + Math.sin(angle) * dist,
      vx: 0, vy: 0,
    };
    _lgNodes.push(node);
    nodeMap[id] = node;
  });

  // Edges: source → each of its tags
  sources.forEach(s => {
    _lgParseTags(s.domain_tags).forEach(tag => {
      _lgLinks.push({
        source: nodeMap[`src-${s.source_id}`],
        target: nodeMap[`tag-${tag}`],
      });
    });
  });
}

/* ── Physics ────────────────────────────────────────────────────────────── */

function _lgTick() {
  const nodes = _lgNodes;
  const links = _lgLinks;
  const n = nodes.length;

  // Repulsion between all node pairs
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      const a = nodes[i], b = nodes[j];
      const dx = b.x - a.x, dy = b.y - a.y;
      const dist2 = dx * dx + dy * dy || 0.001;
      const dist  = Math.sqrt(dist2);
      const force = 900 / dist2;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      a.vx -= fx; a.vy -= fy;
      b.vx += fx; b.vy += fy;
    }
  }

  // Spring attraction along edges
  links.forEach(lk => {
    const a = lk.source, b = lk.target;
    if (!a || !b) return;
    const dx   = b.x - a.x, dy = b.y - a.y;
    const dist = Math.sqrt(dx * dx + dy * dy) || 0.001;
    const ideal = a.r + b.r + 30;
    const stretch = dist - ideal;
    const k = 0.006;
    const fx = (dx / dist) * stretch * k;
    const fy = (dy / dist) * stretch * k;
    a.vx += fx; a.vy += fy;
    b.vx -= fx; b.vy -= fy;
  });

  // Weak center gravity
  const W = _lgCanvas ? _lgCanvas.width  : 800;
  const H = _lgCanvas ? _lgCanvas.height : 600;
  const cx = W / 2, cy = H / 2;
  nodes.forEach(nd => {
    nd.vx += (cx - nd.x) * 0.0008;
    nd.vy += (cy - nd.y) * 0.0008;
  });

  // Integrate + damp
  nodes.forEach(nd => {
    if (nd === _lgDrag) return;
    nd.vx *= 0.88; nd.vy *= 0.88;
    nd.x  += nd.vx; nd.y  += nd.vy;
  });
}

/* ── Rendering ──────────────────────────────────────────────────────────── */

function _lgDraw() {
  const canvas = _lgCanvas;
  const ctx    = _lgCtx;
  if (!canvas || !ctx) return;

  const W = canvas.width, H = canvas.height;
  ctx.clearRect(0, 0, W, H);

  ctx.save();
  ctx.translate(_lgPan.x, _lgPan.y);
  ctx.scale(_lgScale, _lgScale);

  const hasFilter = _lgFilter.length > 0;

  // Draw edges
  _lgLinks.forEach(lk => {
    const a = lk.source, b = lk.target;
    if (!a || !b) return;
    const dimA = hasFilter && !_lgNodeMatches(a);
    const dimB = hasFilter && !_lgNodeMatches(b);
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.strokeStyle = (dimA && dimB) ? 'rgba(128,128,128,0.08)' : 'rgba(128,128,128,0.22)';
    ctx.lineWidth = 1;
    ctx.stroke();
  });

  // Draw nodes
  _lgNodes.forEach(nd => {
    const isHover  = nd === _lgHover;
    const matches  = !hasFilter || _lgNodeMatches(nd);
    const alpha    = matches ? 1 : 0.18;

    ctx.save();
    ctx.globalAlpha = alpha;

    // Shadow / glow on hover or match
    if (isHover || (hasFilter && matches && nd.type === 'source')) {
      ctx.shadowColor = nd.color;
      ctx.shadowBlur  = 14;
    }

    // Circle
    ctx.beginPath();
    ctx.arc(nd.x, nd.y, nd.r, 0, Math.PI * 2);
    ctx.fillStyle = nd.type === 'source' ? nd.color : '#555';
    ctx.fill();

    // Stroke
    ctx.lineWidth   = isHover ? 2.5 : 1;
    ctx.strokeStyle = isHover ? '#fff' : 'rgba(255,255,255,0.2)';
    ctx.stroke();

    ctx.shadowBlur = 0;

    // Label
    if (nd.type === 'source') {
      ctx.font         = `bold ${Math.min(10, nd.r * 0.55)}px system-ui,sans-serif`;
      ctx.fillStyle    = '#fff';
      ctx.textAlign    = 'center';
      ctx.textBaseline = 'middle';
      ctx.shadowColor  = 'rgba(0,0,0,0.7)';
      ctx.shadowBlur   = 3;
      // Wrap label inside circle
      const maxW = nd.r * 1.7;
      const words = nd.label.split(' ');
      let line = '', lines = [];
      words.forEach(w => {
        const test = line ? line + ' ' + w : w;
        if (ctx.measureText(test).width > maxW && line) { lines.push(line); line = w; }
        else line = test;
      });
      lines.push(line);
      const lineH = 11;
      const startY = nd.y - (lines.length - 1) * lineH / 2;
      lines.forEach((l, i) => ctx.fillText(l, nd.x, startY + i * lineH));
      ctx.shadowBlur = 0;
    } else {
      // Tag node: just the tag name small
      ctx.font         = `500 8px system-ui,sans-serif`;
      ctx.fillStyle    = 'rgba(255,255,255,0.75)';
      ctx.textAlign    = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(nd.label, nd.x, nd.y + nd.r + 8);
    }

    ctx.restore();
  });

  // Hover tooltip for source nodes
  if (_lgHover && _lgHover.type === 'source') {
    const nd  = _lgHover;
    const tip = nd.source.title;
    const cat = nd.source.category || '';
    const tags = _lgParseTags(nd.source.domain_tags).join(', ') || '—';
    const tx = nd.x + nd.r + 10;
    const ty = nd.y - 10;

    ctx.save();
    ctx.font = 'bold 11px system-ui,sans-serif';
    const tw = Math.max(ctx.measureText(tip).width, ctx.measureText(tags).width) + 20;
    ctx.fillStyle = 'rgba(20,20,30,0.92)';
    ctx.beginPath();
    ctx.roundRect(tx, ty, tw, 46, 6);
    ctx.fill();
    ctx.strokeStyle = 'rgba(255,255,255,0.1)';
    ctx.lineWidth = 1;
    ctx.stroke();

    ctx.fillStyle = '#fff';
    ctx.fillText(tip, tx + 10, ty + 14);
    ctx.font = '10px system-ui,sans-serif';
    ctx.fillStyle = _LG_CAT_COLORS[cat] || '#888';
    ctx.fillText(cat.replace('_', ' '), tx + 10, ty + 28);
    ctx.fillStyle = 'rgba(255,255,255,0.5)';
    ctx.fillText(tags.slice(0, 40), tx + 10, ty + 40);
    ctx.restore();
  }

  ctx.restore();
}

function _lgAnimate() {
  _lgTick();
  _lgDraw();
  _lgRaf = requestAnimationFrame(_lgAnimate);
}

/* ── Events ─────────────────────────────────────────────────────────────── */

function _lgAttachEvents(canvas) {
  // Resize canvas to parent
  function resize() {
    const rect = canvas.parentElement.getBoundingClientRect();
    canvas.width  = rect.width  || 600;
    canvas.height = rect.height || 400;
    _lgCtx = canvas.getContext('2d');
  }
  resize();
  const ro = new ResizeObserver(resize);
  ro.observe(canvas.parentElement);

  // Mouse move — hover + drag
  canvas.addEventListener('mousemove', e => {
    const [wx, wy] = _lgWorld(e, canvas);
    _lgHover = _lgHitTest(wx, wy);
    canvas.style.cursor = _lgHover ? 'pointer' : (_lgPanStart ? 'grabbing' : 'grab');

    if (_lgDrag) {
      _lgDrag.x = wx; _lgDrag.y = wy;
      _lgDrag.vx = 0; _lgDrag.vy = 0;
    } else if (_lgPanStart) {
      _lgPan.x = _lgPanStart.panX + (e.clientX - _lgPanStart.mx);
      _lgPan.y = _lgPanStart.panY + (e.clientY - _lgPanStart.my);
    }
  });

  canvas.addEventListener('mousedown', e => {
    const [wx, wy] = _lgWorld(e, canvas);
    const hit = _lgHitTest(wx, wy);
    if (hit) {
      _lgDrag = hit;
    } else {
      _lgPanStart = { mx: e.clientX, my: e.clientY, panX: _lgPan.x, panY: _lgPan.y };
    }
  });

  canvas.addEventListener('mouseup', e => {
    if (_lgDrag) {
      // Click (not drag) — fire callback
      const [wx, wy] = _lgWorld(e, canvas);
      const still = Math.abs(_lgDrag.x - wx) < 5 && Math.abs(_lgDrag.y - wy) < 5;
      if (still && _lgDrag.type === 'source' && _lgOnClick) {
        _lgOnClick(_lgDrag.source, _lgGetRelated(_lgDrag));
      }
      _lgDrag = null;
    }
    _lgPanStart = null;
  });

  canvas.addEventListener('mouseleave', () => {
    _lgDrag = null; _lgPanStart = null; _lgHover = null;
  });

  canvas.addEventListener('wheel', e => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    _lgScale = Math.min(3, Math.max(0.25, _lgScale * delta));
  }, { passive: false });
}

/* ── Helpers ────────────────────────────────────────────────────────────── */

function _lgWorld(e, canvas) {
  const rect = canvas.getBoundingClientRect();
  const mx = (e.clientX - rect.left - _lgPan.x) / _lgScale;
  const my = (e.clientY - rect.top  - _lgPan.y) / _lgScale;
  return [mx, my];
}

function _lgHitTest(wx, wy) {
  for (let i = _lgNodes.length - 1; i >= 0; i--) {
    const nd = _lgNodes[i];
    const dx = nd.x - wx, dy = nd.y - wy;
    if (dx * dx + dy * dy <= nd.r * nd.r) return nd;
  }
  return null;
}

function _lgGetRelated(sourceNode) {
  // Find all source nodes sharing at least one tag with this node
  const myTags = new Set(_lgParseTags(sourceNode.source.domain_tags));
  return _lgNodes.filter(nd => {
    if (nd === sourceNode || nd.type !== 'source') return false;
    return _lgParseTags(nd.source.domain_tags).some(t => myTags.has(t));
  }).map(nd => nd.source);
}

function _lgNodeMatches(nd) {
  if (!_lgFilter) return true;
  if (nd.type === 'source') {
    const s = nd.source;
    return s.title.toLowerCase().includes(_lgFilter) ||
           (s.category || '').includes(_lgFilter) ||
           (_lgParseTags(s.domain_tags).some(t => t.includes(_lgFilter)));
  }
  return nd.label.toLowerCase().includes(_lgFilter);
}

function _lgParseTags(raw) {
  if (!raw) return [];
  try { return JSON.parse(raw); } catch { return []; }
}
