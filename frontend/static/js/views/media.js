'use strict';

window._mediaState = window._mediaState || { providers: [], items: [], runs: [] };

function loadMediaData() {
  mediaWireResizer();
  fetch('/api/media/state')
    .then(r => r.json())
    .then(d => {
      if (!d.ok) throw new Error(d.error || 'failed');
      window._mediaState = d;
      mediaRender();
      mediaWireResizer();
    })
    .catch(err => {
      const el = document.getElementById('media-run-status');
      if (el) el.textContent = 'Media load error: ' + err.message;
    });
}

function mediaRender() {
  const st = window._mediaState || {};
  const providersEl = document.getElementById('media-providers');
  const itemsEl = document.getElementById('media-items');
  const runsEl = document.getElementById('media-runs');

  if (providersEl) {
    providersEl.innerHTML = (st.providers || []).map(p => `
      <div style="padding:8px;border:1px solid var(--border);border-radius:8px;background:var(--card);display:flex;justify-content:space-between;gap:8px;align-items:center;">
        <div>
          <div style="font-size:12px;font-weight:600;color:var(--text);">${mediaEsc(p.name)}</div>
          <div style="font-size:10px;color:var(--text-dim);">${mediaEsc(p.category || 'mixed')} ${p.base_url ? '· ' + mediaEsc(p.base_url) : ''}</div>
        </div>
        <span style="font-size:10px;padding:2px 8px;border-radius:999px;background:#4caf5020;color:#4caf50;border:1px solid #4caf5060;">on</span>
      </div>`).join('');
  }

  if (itemsEl) {
    itemsEl.innerHTML = (st.items || []).map(i => `
      <div style="padding:8px;border:1px solid var(--border);border-radius:8px;background:var(--card);">
        <div style="font-size:12px;font-weight:600;color:var(--text);">${mediaEsc(i.title || 'Untitled')}</div>
        <div style="font-size:10px;color:var(--text-dim);margin-top:2px;">${mediaEsc(i.artist || '—')} · ${mediaEsc(i.provider_id || 'custom')}</div>
        ${i.source_url ? `<a href="${mediaEsc(i.source_url)}" target="_blank" style="font-size:10px;color:#64b5f6;word-break:break-all;">${mediaEsc(i.source_url)}</a>` : ''}
      </div>`).join('');
  }

  if (runsEl) {
    runsEl.innerHTML = (st.runs || []).map(r => `
      <div style="padding:8px;border:1px solid var(--border);border-radius:8px;background:var(--card);">
        <div style="display:flex;justify-content:space-between;gap:8px;align-items:center;">
          <div style="font-size:11px;color:var(--text);font-weight:600;">${mediaEsc(r.runner_key || '')}</div>
          <span style="font-size:10px;padding:2px 8px;border-radius:999px;${r.status === 'completed' ? 'background:#4caf5020;color:#4caf50;border:1px solid #4caf5060;' : r.status === 'failed' ? 'background:#f4433620;color:#f44336;border:1px solid #f4433660;' : 'background:#29b6f620;color:#29b6f6;border:1px solid #29b6f660;'}">${mediaEsc(r.status || 'unknown')}</span>
        </div>
        <div style="font-size:10px;color:var(--text-dim);margin-top:4px;">${mediaEsc(r.created_at || '')}</div>
        ${r.output_path ? `<div style="font-size:10px;color:#81c784;margin-top:4px;">artifact: ${mediaEsc(r.output_path)}</div>` : ''}
        ${r.log_text ? `<div style="font-size:10px;color:var(--text-dim);margin-top:3px;white-space:pre-wrap;">${mediaEsc(r.log_text)}</div>` : ''}
      </div>`).join('');
  }
}

function mediaAddProvider() {
  const name = (document.getElementById('media-provider-name')?.value || '').trim();
  if (!name) return;
  fetch('/api/media/providers', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, category: 'music' })
  }).then(r => r.json()).then(d => {
    if (!d.ok) throw new Error(d.error || 'failed');
    document.getElementById('media-provider-name').value = '';
    loadMediaData();
  }).catch(err => showToast && showToast('Provider add failed: ' + err.message, 'error'));
}

function mediaAddItem() {
  const title = (document.getElementById('media-item-title')?.value || '').trim();
  const artist = (document.getElementById('media-item-artist')?.value || '').trim();
  const source_url = (document.getElementById('media-item-url')?.value || '').trim();
  if (!title) return;
  fetch('/api/media/items', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, artist, source_url, provider_id: 'rss_custom', media_type: 'music' })
  }).then(r => r.json()).then(d => {
    if (!d.ok) throw new Error(d.error || 'failed');
    document.getElementById('media-item-title').value = '';
    document.getElementById('media-item-artist').value = '';
    document.getElementById('media-item-url').value = '';
    loadMediaData();
  }).catch(err => showToast && showToast('Media add failed: ' + err.message, 'error'));
}

function mediaSeedSong() {
  fetch('/api/media/seed-song', { method: 'POST' })
    .then(r => r.json())
    .then(() => { loadMediaData(); showToast && showToast('Seed song ensured in Media Center + Knowledge.'); })
    .catch(err => showToast && showToast('Seed failed: ' + err.message, 'error'));
}

function mediaProduce(runnerKey) {
  const prompt = (document.getElementById('media-prompt')?.value || '').trim();
  const status = document.getElementById('media-run-status');
  if (status) status.textContent = 'Running local media runner…';
  fetch('/api/media/produce', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ runner_key: runnerKey, prompt })
  }).then(async r => {
    const d = await r.json();
    if (!r.ok || !d.ok) throw new Error(d.error || 'runner failed');
    if (status) status.textContent = `Completed: ${d.output_path}`;
    loadMediaData();
  }).catch(err => {
    if (status) status.textContent = 'Runner error: ' + err.message;
    showToast && showToast('Media run failed: ' + err.message, 'error');
  });
}

function mediaWireResizer() {
  const root = document.getElementById('media-layout');
  const left = document.getElementById('media-consume-panel');
  const grip = document.getElementById('media-resizer');
  if (!root || !left || !grip || grip.__wired) return;
  grip.__wired = true;
  grip.title = 'Drag to resize consume/produce split. Double-click to reset.';
  grip.style.touchAction = 'none';

  const storageKey = 'fridays.media.consumeWidth';
  const applyWidth = (width) => {
    const rootWidth = root.getBoundingClientRect().width || window.innerWidth;
    const max = Math.max(280, rootWidth - 340);
    const next = Math.max(220, Math.min(max, Math.round(width)));
    root.style.gridTemplateColumns = `${next}px 8px minmax(280px,1fr)`;
    return next;
  };
  const saved = parseInt(localStorage.getItem(storageKey) || '', 10);
  if (Number.isFinite(saved)) applyWidth(saved);

  grip.addEventListener('pointerdown', (e) => {
    if (e.button != null && e.button !== 0) return;
    e.preventDefault();
    const startX = e.clientX;
    const startW = left.getBoundingClientRect().width;
    grip.setPointerCapture && grip.setPointerCapture(e.pointerId);
    root.dataset.resizing = 'true';
    const move = (ev) => {
      const next = applyWidth(startW + (ev.clientX - startX));
      localStorage.setItem(storageKey, String(next));
    };
    const up = () => {
      delete root.dataset.resizing;
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      window.removeEventListener('pointercancel', up);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
    window.addEventListener('pointercancel', up);
  });
  grip.addEventListener('dblclick', () => {
    localStorage.removeItem(storageKey);
    root.style.gridTemplateColumns = 'minmax(260px,34%) 8px minmax(340px,1fr)';
  });
}


async function mediaCaptureScreenshot() {
  const status = document.getElementById('media-run-status');
  const setStatus = (msg) => { if (status) status.textContent = msg; };

  if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) {
    setStatus('Screenshot capture unavailable in this browser.');
    showToast && showToast('Browser does not support getDisplayMedia.', 'error');
    return;
  }

  let stream;
  try {
    setStatus('Requesting screen access…');
    stream = await navigator.mediaDevices.getDisplayMedia({ video: { frameRate: 1 }, audio: false });
    const track = stream.getVideoTracks()[0];
    const video = document.createElement('video');
    video.srcObject = stream;
    video.muted = true;
    await video.play();

    const w = video.videoWidth || 1280;
    const h = video.videoHeight || 720;
    const canvas = document.createElement('canvas');
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, w, h);

    const dataUrl = canvas.toDataURL('image/png');
    track.stop();
    stream.getTracks().forEach(t => t.stop());

    setStatus('Uploading screenshot artifact…');
    const resp = await fetch('/api/media/screenshot', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ data_url: dataUrl, label: 'fridays_manual_capture' })
    });
    const data = await resp.json();
    if (!resp.ok || !data.ok) throw new Error(data.error || 'upload failed');
    setStatus(`Screenshot saved: ${data.output_path}`);
    showToast && showToast('Screenshot captured and saved.', 'success');
    loadMediaData();
  } catch (err) {
    setStatus('Screenshot failed: ' + (err.message || err));
    showToast && showToast('Screenshot failed: ' + (err.message || err), 'error');
  } finally {
    if (stream) stream.getTracks().forEach(t => t.stop());
  }
}

function mediaEsc(v) {
  return String(v || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

window.loadMediaData = loadMediaData;
window.mediaAddProvider = mediaAddProvider;
window.mediaAddItem = mediaAddItem;
window.mediaProduce = mediaProduce;
window.mediaSeedSong = mediaSeedSong;
window.mediaCaptureScreenshot = mediaCaptureScreenshot;
