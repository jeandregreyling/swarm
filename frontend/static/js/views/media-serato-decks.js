/* media-serato-decks.js — Liquid-Glass Serato-Inspired Dual-Deck Waveform, Auto-Tune DSP & YouTube Visualizer UI */
(function () {
  const _state = {
    assets: [],
    decks: { A: null, B: null },
    audio: { A: null, B: null },
    crossfader: 0.5,
    lastVideo: null,
    collapsed: false,
  };

  function _esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function _toast(msg, kind) {
    if (typeof window.showToast === 'function') window.showToast(msg, kind || 'info');
  }

  function _drawWaveform(deckKey) {
    const canvas = document.getElementById(`serato-wave-${deckKey}`);
    const asset = _state.decks[deckKey];
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width = canvas.clientWidth || 360;
    const h = canvas.height = 74;
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = 'rgba(4, 8, 15, 0.96)';
    ctx.fillRect(0, 0, w, h);

    const analysis = asset && asset.analysis ? asset.analysis : null;
    const peaks = (analysis && analysis.peaks) || [];
    const lows = (analysis && analysis.low_peaks) || [];
    const mids = (analysis && analysis.mid_peaks) || [];
    const highs = (analysis && analysis.high_peaks) || [];

    if (!peaks.length) {
      ctx.fillStyle = 'rgba(148, 163, 184, 0.55)';
      ctx.font = '11px system-ui, sans-serif';
      ctx.fillText(`Load an audio track onto Deck ${deckKey} to view Serato RGB waveform`, 12, h / 2 + 4);
      return;
    }

    const midY = h / 2;
    const barW = Math.max(1.5, w / peaks.length);
    for (let i = 0; i < peaks.length; i++) {
      const x = (i / peaks.length) * w;
      const amp = Math.max(0.04, Number(peaks[i] || 0));
      const bh = amp * (h * 0.44);
      // Serato-style RGB frequency tinting: Bass=red/amber, Mid=emerald/gold, High=cyan
      const r = Math.min(255, Math.round(40 + 215 * Number(lows[i] || 0)));
      const g = Math.min(255, Math.round(70 + 185 * Number(mids[i] || 0)));
      const b = Math.min(255, Math.round(90 + 165 * Number(highs[i] || 0)));
      ctx.fillStyle = `rgb(${r},${g},${b})`;
      ctx.fillRect(x, midY - bh, Math.max(1, barW - 0.6), bh * 2);
    }

    // Playhead cursor
    const audioEl = _state.audio[deckKey];
    const dur = (asset && asset.probe && asset.probe.duration_sec) || (audioEl && audioEl.duration) || 0;
    if (audioEl && dur > 0) {
      const frac = Math.max(0, Math.min(1, audioEl.currentTime / dur));
      const px = frac * w;
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(px - 1, 0, 2, h);
    }
  }

  function _applyCrossfader() {
    const xf = _state.crossfader;
    const volA = Math.min(1, Math.cos(xf * Math.PI * 0.5) * 1.15);
    const volB = Math.min(1, Math.sin(xf * Math.PI * 0.5) * 1.15);
    if (_state.audio.A) _state.audio.A.volume = Math.max(0, Math.min(1, volA));
    if (_state.audio.B) _state.audio.B.volume = Math.max(0, Math.min(1, volB));
  }

  function _renderDeckHtml(deckKey) {
    const asset = _state.decks[deckKey];
    const bpm = asset && asset.analysis ? asset.analysis.bpm : '--';
    const rms = asset && asset.analysis ? asset.analysis.rms_db : '--';
    const dur = asset && asset.probe ? `${Number(asset.probe.duration_sec || 0).toFixed(1)}s` : '0.0s';
    const cues = (asset && asset.analysis && asset.analysis.cue_points) || [];
    const title = asset ? (asset.title || asset.filename) : `Empty Deck ${deckKey}`;
    return `
      <div class="serato-deck" data-deck="${deckKey}">
        <div class="serato-deck-top">
          <div class="serato-deck-title">Deck ${deckKey}: ${_esc(title)}</div>
          <span class="serato-bpm-pill">${_esc(bpm)} BPM · ${_esc(dur)}</span>
        </div>
        <canvas id="serato-wave-${deckKey}" class="serato-wave-canvas" title="Click waveform to seek"></canvas>
        <div style="display:flex;flex-wrap:wrap;align-items:center;gap:6px;">
          <button class="serato-btn serato-btn-emerald" type="button" onclick="window.seratoTogglePlay('${deckKey}')">▶ Play / ⏸</button>
          <button class="serato-btn" type="button" onclick="window.seratoStopDeck('${deckKey}')">■ Cue 0</button>
          <span style="font-size:10px;color:#94a3b8;margin-left:auto;">RMS ${_esc(rms)} dB</span>
        </div>
        <div class="serato-cues">
          ${cues.map((c) => `<button type="button" class="serato-cue-pad" style="border-color:${_esc(c.color || '#38bdf8')}" onclick="window.seratoSeekDeck('${deckKey}', ${Number(c.time_sec || 0)})">${_esc(c.label)} ${Number(c.time_sec || 0).toFixed(1)}s</button>`).join('') || '<span style="font-size:10px;color:#64748b;">Auto cues appear once track loads</span>'}
        </div>
        <div class="serato-controls-row">
          <label>Tempo <span id="serato-tempo-val-${deckKey}">1.00x</span>
            <input id="serato-tempo-${deckKey}" type="range" min="0.7" max="1.4" step="0.02" value="1.00" oninput="window.seratoSetTempo('${deckKey}', this.value)">
          </label>
          <label>Pitch <span id="serato-pitch-val-${deckKey}">0 st</span>
            <input id="serato-pitch-${deckKey}" type="range" min="-6" max="6" step="1" value="0" oninput="document.getElementById('serato-pitch-val-${deckKey}').textContent=this.value+' st'">
          </label>
          <label>Auto-Tune <span id="serato-at-val-${deckKey}">0%</span>
            <input id="serato-at-${deckKey}" type="range" min="0" max="1" step="0.05" value="0" oninput="document.getElementById('serato-at-val-${deckKey}').textContent=Math.round(this.value*100)+'%'">
          </label>
        </div>
        <div class="serato-controls-row">
          <label>Low EQ <input id="serato-low-${deckKey}" type="range" min="-12" max="12" step="1" value="0"></label>
          <label>Mid EQ <input id="serato-mid-${deckKey}" type="range" min="-12" max="12" step="1" value="0"></label>
          <label>High EQ <input id="serato-high-${deckKey}" type="range" min="-12" max="12" step="1" value="0"></label>
        </div>
        <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:2px;">
          <button class="serato-btn serato-btn-emerald" type="button" onclick="window.seratoApplyDsp('${deckKey}')">✨ Render DSP / Auto-Tune</button>
          <button class="serato-btn serato-btn-gold" type="button" onclick="window.seratoRenderVideo('${deckKey}', '16:9')">🎬 YouTube 16:9</button>
          <button class="serato-btn serato-btn-gold" type="button" onclick="window.seratoRenderVideo('${deckKey}', '9:16')">📱 Shorts 9:16</button>
        </div>
      </div>
    `;
  }

  function _renderStudio() {
    const host = document.getElementById('media-serato-studio');
    if (!host) return;
    host.classList.toggle('is-collapsed', _state.collapsed);
    const crateHtml = (_state.assets || []).map((a) => {
      const dur = a.probe ? `${Number(a.probe.duration_sec || 0).toFixed(1)}s` : '';
      const bpm = a.bpm ? `${a.bpm} BPM` : (a.kind === 'video' ? 'MP4' : '');
      return `
        <div class="serato-crate-item">
          <div style="min-width:0;overflow:hidden;">
            <div style="font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${_esc(a.title || a.filename)}</div>
            <div style="font-size:10px;color:#94a3b8;">${_esc(a.kind)} · ${_esc(bpm)} · ${_esc(dur)} · ${_esc(a.source || '')}</div>
          </div>
          <div style="display:flex;gap:4px;flex-shrink:0;">
            ${a.kind === 'audio' ? `
              <button class="serato-btn" type="button" onclick="window.seratoLoadDeck('A','${_esc(a.id)}')">A</button>
              <button class="serato-btn" type="button" onclick="window.seratoLoadDeck('B','${_esc(a.id)}')">B</button>
            ` : `<a class="serato-btn serato-btn-gold" href="${_esc(a.url)}" target="_blank" rel="noopener">Play MP4</a>`}
          </div>
        </div>
      `;
    }).join('') || '<div style="font-size:11px;color:#64748b;">No tracks in Media Library yet — upload an MP3/WAV/FLAC or email a song to Hummingbird!</div>';

    const videoBox = _state.lastVideo ? `
      <div class="serato-video-preview">
        <video controls src="${_esc(_state.lastVideo.url)}"></video>
        <div style="flex:1;min-width:220px;font-size:11px;">
          <div style="font-weight:700;color:#6ef7c8;margin-bottom:4px;">🎬 Ready for YouTube: ${_esc((_state.lastVideo.youtube_draft && _state.lastVideo.youtube_draft.title) || _state.lastVideo.title)}</div>
          <div style="color:#cbd5e1;white-space:pre-line;margin-bottom:6px;">${_esc((_state.lastVideo.youtube_draft && _state.lastVideo.youtube_draft.description) || '')}</div>
          <div style="font-size:10px;color:#94a3b8;">Tags: ${_esc(((_state.lastVideo.youtube_draft && _state.lastVideo.youtube_draft.tags) || []).join(', '))}</div>
        </div>
      </div>
    ` : '';

    host.innerHTML = `
      <div class="serato-header">
        <div class="serato-brand">
          <span>🎛️ Hummingbird Serato Dual-Deck & YouTube Studio</span>
          <span class="serato-badge">${_state.assets.length} tracks in crate</span>
        </div>
        <div class="serato-upload-bar">
          <label class="serato-btn serato-btn-emerald" style="display:inline-flex;align-items:center;gap:5px;">
            ⬆ Upload Audio/Video
            <input id="serato-file-input" type="file" accept=".mp3,.wav,.flac,.m4a,.ogg,.mp4,.webm" style="display:none;" onchange="window.seratoUploadFromInput(this)">
          </label>
          <button class="serato-btn" type="button" onclick="window.seratoRefreshLibrary()">↻ Refresh Crate</button>
          <button class="serato-btn" type="button" onclick="window.seratoToggleStudio()">${_state.collapsed ? 'Expand Decks' : 'Collapse Decks'}</button>
        </div>
      </div>
      <div class="serato-body">
        <div class="serato-decks-grid">
          ${_renderDeckHtml('A')}
          <div class="serato-mixer">
            <div style="font-weight:700;color:#e9d5ff;text-align:center;">🎚️ Mixer & Auto-Tune Key</div>
            <label>Crossfader (A ◀──▶ B)
              <input type="range" min="0" max="1" step="0.01" value="${_state.crossfader}" oninput="window.seratoSetCrossfader(this.value)">
            </label>
            <label>Auto-Tune Scale
              <select id="serato-scale-select" style="width:100%;margin-top:3px;background:rgba(15,23,42,0.9);color:#e2e8f0;border:1px solid rgba(255,255,255,0.16);border-radius:7px;padding:4px;">
                <option value="chromatic">Chromatic (All Notes)</option>
                <option value="C_major">C Major</option>
                <option value="A_minor">A Minor</option>
                <option value="G_major">G Major</option>
                <option value="D_minor">D Minor</option>
                <option value="F_major">F Major</option>
              </select>
            </label>
            <label style="display:flex;align-items:center;gap:6px;margin-top:2px;">
              <input id="serato-norm-check" type="checkbox" checked> -14 LUFS YouTube Loudness Norm
            </label>
            <button class="serato-btn serato-btn-emerald" type="button" onclick="window.seratoMixDecks('crossfade')">🔀 Mix A → B (Crossfade)</button>
            <button class="serato-btn serato-btn-gold" type="button" onclick="window.seratoMixDecks('mashup')">⚡ Layer A + B (Mashup)</button>
            <div id="serato-status-line" style="font-size:10px;color:#94a3b8;margin-top:auto;">FFmpeg/NumPy engine ready</div>
          </div>
          ${_renderDeckHtml('B')}
        </div>
        ${videoBox}
        <div class="serato-crate">
          <div style="font-size:11px;font-weight:700;color:#94a3b8;">Crate · Ingested Email Songs, Uploads, DSP Masters & YouTube Visualizers</div>
          <div class="serato-crate-list">${crateHtml}</div>
        </div>
      </div>
    `;

    ['A', 'B'].forEach((k) => {
      _drawWaveform(k);
      const canvas = document.getElementById(`serato-wave-${k}`);
      if (canvas) {
        canvas.onclick = (ev) => {
          const rect = canvas.getBoundingClientRect();
          const frac = Math.max(0, Math.min(1, (ev.clientX - rect.left) / Math.max(1, rect.width)));
          const asset = _state.decks[k];
          const dur = (asset && asset.probe && asset.probe.duration_sec) || 0;
          if (dur > 0) window.seratoSeekDeck(k, frac * dur);
        };
      }
    });
  }

  async function seratoRefreshLibrary() {
    try {
      const res = await fetch('/api/media-center/library');
      const data = await res.json();
      if (data && data.ok) {
        _state.assets = data.assets || [];
        _renderStudio();
      }
    } catch (e) {
      // ignore if offline
    }
  }

  async function seratoLoadDeck(deckKey, assetId) {
    try {
      const res = await fetch(`/api/media-center/library/${encodeURIComponent(assetId)}`);
      const data = await res.json();
      if (!data.ok || !data.asset) throw new Error(data.error || 'failed to load asset');
      _state.decks[deckKey] = data.asset;
      if (_state.audio[deckKey]) {
        try { _state.audio[deckKey].pause(); } catch (e) {}
      }
      const audio = new Audio(data.asset.url);
      audio.ontimeupdate = () => _drawWaveform(deckKey);
      audio.onended = () => _drawWaveform(deckKey);
      _state.audio[deckKey] = audio;
      _applyCrossfader();
      _renderStudio();
      _toast(`Loaded "${data.asset.title}" onto Deck ${deckKey}`, 'success');
    } catch (err) {
      _toast('Deck load failed: ' + (err.message || err), 'error');
    }
  }

  function seratoTogglePlay(deckKey) {
    const a = _state.audio[deckKey];
    if (!a) return _toast(`Load a track onto Deck ${deckKey} first`, 'info');
    if (a.paused) a.play().catch(() => {});
    else a.pause();
  }

  function seratoStopDeck(deckKey) {
    const a = _state.audio[deckKey];
    if (!a) return;
    a.pause();
    a.currentTime = 0;
    _drawWaveform(deckKey);
  }

  function seratoSeekDeck(deckKey, sec) {
    const a = _state.audio[deckKey];
    if (!a) return;
    a.currentTime = Math.max(0, Number(sec || 0));
    _drawWaveform(deckKey);
  }

  function seratoSetTempo(deckKey, val) {
    const num = Number(val || 1);
    const lbl = document.getElementById(`serato-tempo-val-${deckKey}`);
    if (lbl) lbl.textContent = num.toFixed(2) + 'x';
    if (_state.audio[deckKey]) _state.audio[deckKey].playbackRate = num;
  }

  function seratoSetCrossfader(val) {
    _state.crossfader = Number(val || 0.5);
    _applyCrossfader();
  }

  async function seratoUploadFromInput(input) {
    const file = input && input.files && input.files[0];
    if (!file) return;
    const status = document.getElementById('serato-status-line');
    if (status) status.textContent = `Analyzing ${file.name}…`;
    try {
      const fd = new FormData();
      fd.append('file', file);
      const res = await fetch('/api/media-center/library/upload', { method: 'POST', body: fd });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || 'upload failed');
      await seratoRefreshLibrary();
      if (data.asset && data.asset.kind === 'audio') {
        await seratoLoadDeck(_state.decks.A ? 'B' : 'A', data.asset.id);
      }
      _toast(`Ingested & analyzed ${file.name}`, 'success');
    } catch (err) {
      _toast('Upload failed: ' + (err.message || err), 'error');
    } finally {
      input.value = '';
    }
  }

  async function seratoApplyDsp(deckKey) {
    const asset = _state.decks[deckKey];
    if (!asset) return _toast(`Load a track onto Deck ${deckKey} first`, 'info');
    const status = document.getElementById('serato-status-line');
    if (status) status.textContent = `Rendering DSP/Auto-Tune on Deck ${deckKey}…`;
    try {
      const body = {
        low_db: Number(document.getElementById(`serato-low-${deckKey}`)?.value || 0),
        mid_db: Number(document.getElementById(`serato-mid-${deckKey}`)?.value || 0),
        high_db: Number(document.getElementById(`serato-high-${deckKey}`)?.value || 0),
        tempo: Number(document.getElementById(`serato-tempo-${deckKey}`)?.value || 1),
        pitch_semitones: Number(document.getElementById(`serato-pitch-${deckKey}`)?.value || 0),
        autotune_strength: Number(document.getElementById(`serato-at-${deckKey}`)?.value || 0),
        autotune_key: document.getElementById('serato-scale-select')?.value || 'chromatic',
        normalize: !!document.getElementById('serato-norm-check')?.checked,
        label: `Deck ${deckKey} Master`,
      };
      const res = await fetch(`/api/media-center/library/${encodeURIComponent(asset.id)}/dsp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || 'DSP render failed');
      await seratoRefreshLibrary();
      await seratoLoadDeck(deckKey, data.asset.id);
      _toast(`Rendered DSP master for Deck ${deckKey}`, 'success');
    } catch (err) {
      _toast('DSP render failed: ' + (err.message || err), 'error');
    }
  }

  async function seratoMixDecks(mode) {
    if (!_state.decks.A || !_state.decks.B) {
      return _toast('Load tracks onto both Deck A and Deck B first', 'info');
    }
    const status = document.getElementById('serato-status-line');
    if (status) status.textContent = `Mixing Deck A + Deck B (${mode})…`;
    try {
      const res = await fetch('/api/media-center/decks/mix', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          deck_a_id: _state.decks.A.id,
          deck_b_id: _state.decks.B.id,
          mode: mode || 'crossfade',
          crossfade_sec: 3.0,
        }),
      });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || 'Deck mix failed');
      await seratoRefreshLibrary();
      await seratoLoadDeck('A', data.asset.id);
      _toast(`Mixed Deck A + B (${mode}) and loaded onto Deck A`, 'success');
    } catch (err) {
      _toast('Deck mix failed: ' + (err.message || err), 'error');
    }
  }

  async function seratoRenderVideo(deckKey, aspect) {
    const asset = _state.decks[deckKey];
    if (!asset) return _toast(`Load a track onto Deck ${deckKey} first`, 'info');
    const status = document.getElementById('serato-status-line');
    if (status) status.textContent = `Rendering ${aspect} YouTube visualizer…`;
    try {
      const res = await fetch(`/api/media-center/library/${encodeURIComponent(asset.id)}/render-video`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ aspect: aspect || '16:9', title: asset.title }),
      });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || 'Video render failed');
      _state.lastVideo = data.asset;
      await seratoRefreshLibrary();
      _toast(`Rendered ${aspect} YouTube MP4 Visualizer!`, 'success');
    } catch (err) {
      _toast('Visualizer render failed: ' + (err.message || err), 'error');
    }
  }

  function seratoToggleStudio() {
    _state.collapsed = !_state.collapsed;
    _renderStudio();
  }

  window.initSeratoDecks = function () { _renderStudio(); return seratoRefreshLibrary(); };
  window.seratoRefreshLibrary = seratoRefreshLibrary;
  window.seratoLoadDeck = seratoLoadDeck;
  window.seratoTogglePlay = seratoTogglePlay;
  window.seratoStopDeck = seratoStopDeck;
  window.seratoSeekDeck = seratoSeekDeck;
  window.seratoSetTempo = seratoSetTempo;
  window.seratoSetCrossfader = seratoSetCrossfader;
  window.seratoUploadFromInput = seratoUploadFromInput;
  window.seratoApplyDsp = seratoApplyDsp;
  window.seratoMixDecks = seratoMixDecks;
  window.seratoRenderVideo = seratoRenderVideo;
  window.seratoToggleStudio = seratoToggleStudio;

  // Hook smoothly after initMediaCenter so decks populate whenever Media Center opens
  const _origInit = window.initMediaCenter;
  if (typeof _origInit === 'function') {
    window.initMediaCenter = function () {
      const res = _origInit.apply(this, arguments);
      setTimeout(() => window.initSeratoDecks(), 60);
      return res;
    };
  }
})();
