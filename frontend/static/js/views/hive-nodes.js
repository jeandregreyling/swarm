'use strict';

/* ──────────────────────────────────────────────────────────────────────────
   hive-nodes.js — Standalone Hive Nodes popout.
   Watered-down library graph showing the 20 most recently touched sources.
   Uses the same libGraphInit engine from library-graph.js.
────────────────────────────────────────────────────────────────────────── */

const HIVE_RECENT_LIMIT = 20;

async function hiveNodesBoot() {
  const status = document.getElementById('hive-status');
  const canvas = document.getElementById('hive-graph-canvas');
  if (!canvas) return;

  // Size canvas to its container
  const resize = () => {
    const rect = canvas.parentElement.getBoundingClientRect();
    canvas.width  = Math.max(400, rect.width);
    canvas.height = Math.max(300, rect.height);
  };
  resize();
  window.addEventListener('resize', resize);

  try {
    status.textContent = 'Loading recent nodes…';
    const r = await fetch(`/api/library/sources?recent=${HIVE_RECENT_LIMIT}`);
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'load failed');
    const sources = d.sources || [];
    if (!sources.length) {
      status.textContent = 'No library sources yet — add some in the Library window.';
      return;
    }
    status.textContent = `Hive Nodes · ${sources.length} most recently touched`;
    if (typeof libGraphInit === 'function') {
      libGraphInit(sources, canvas, (src) => {
        // Click through: open the source in the Library modal via opener window.
        try {
          if (window.opener && !window.opener.closed
              && typeof window.opener._libNodeClick === 'function') {
            window.opener._libNodeClick(src, []);
            window.opener.focus();
            return;
          }
        } catch (_) {}
        // Fallback: navigate this window to the library deep-link.
        window.location.href = '/library';
      });
    } else {
      status.textContent = 'Graph engine unavailable.';
    }
  } catch (e) {
    status.textContent = 'Error: ' + (e.message || e);
  }
}

function hiveNodesPopout() {
  // Open this page in a new browser window from the main UI.
  const feat = 'width=900,height=700,menubar=no,toolbar=no,location=no,status=no';
  window.open('/hive-nodes', 'hive-nodes-popout', feat);
}

window.hiveNodesBoot   = hiveNodesBoot;
window.hiveNodesPopout = hiveNodesPopout;

document.addEventListener('DOMContentLoaded', () => {
  if (document.getElementById('hive-graph-canvas')) hiveNodesBoot();
});
