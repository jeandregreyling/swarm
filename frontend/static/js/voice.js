'use strict';

/* ──────────────────────────────────────────────────────────────────────────
   voice.js — Server-side Whisper + Piper voice helpers with browser fallback.

   Exports:
     voiceRecordToggle(btnEl, onTranscript)  — toggle mic recording; calls
                                               onTranscript(text) when done.
     voiceSpeak(text, voice?)                — synthesize + play via Piper,
                                               falling back to speechSynthesis.
     voiceStatus()                           — cached Promise<{stt,tts}>.
────────────────────────────────────────────────────────────────────────── */

let _voiceStatus = null;
let _recorder    = null;
let _recorderBtn = null;
let _recorderCb  = null;
let _recorderChunks = [];

function voiceStatus() {
  if (_voiceStatus) return _voiceStatus;
  _voiceStatus = fetch('/api/voice/status')
    .then(r => r.json())
    .catch(() => ({ ok: false, stt: { available: false }, tts: { available: false } }));
  return _voiceStatus;
}

async function voiceRecordToggle(btnEl, onTranscript) {
  if (_recorder && _recorder.state === 'recording') {
    _recorder.stop();
    return;
  }
  _recorderBtn = btnEl || null;
  _recorderCb  = typeof onTranscript === 'function' ? onTranscript : null;
  _recorderChunks = [];

  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (e) {
    console.warn('[voice] mic permission denied', e);
    _voiceSetBtnState(btnEl, 'error', 'Mic denied');
    return;
  }

  const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
    ? 'audio/webm;codecs=opus' : '';
  _recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
  _recorder.ondataavailable = (e) => { if (e.data && e.data.size) _recorderChunks.push(e.data); };
  _recorder.onstop = async () => {
    stream.getTracks().forEach(t => t.stop());
    _voiceSetBtnState(btnEl, 'busy', 'Transcribing…');
    const blob = new Blob(_recorderChunks, { type: mime || 'audio/webm' });
    await _voiceSendForTranscription(blob, btnEl);
  };
  _recorder.start();
  _voiceSetBtnState(btnEl, 'recording', 'Listening…');
}

async function _voiceSendForTranscription(blob, btnEl) {
  const fd = new FormData();
  fd.append('audio', blob, 'mic.webm');
  try {
    const r = await fetch('/api/voice/stt', { method: 'POST', body: fd });
    if (r.status === 503) {
      // Whisper not installed — fall back to browser SpeechRecognition if
      // available, otherwise tell the user.
      _voiceSetBtnState(btnEl, 'error', 'Whisper not installed');
      if (_browserSpeechRecognize && typeof _browserSpeechRecognize === 'function') {
        _browserSpeechRecognize(_recorderCb);
      }
      return;
    }
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'STT failed');
    _voiceSetBtnState(btnEl, 'idle', '');
    if (_recorderCb && d.text) _recorderCb(d.text);
  } catch (e) {
    console.warn('[voice] STT error', e);
    _voiceSetBtnState(btnEl, 'error', 'STT error');
  }
}

function _voiceSetBtnState(btn, state, label) {
  if (!btn) return;
  btn.dataset.voiceState = state;
  btn.title = label || 'Hold to talk';
  btn.classList.toggle('voice-recording', state === 'recording');
  btn.classList.toggle('voice-busy', state === 'busy');
  btn.classList.toggle('voice-error', state === 'error');
}

async function voiceSpeak(text, voice) {
  if (!text) return;
  const status = await voiceStatus();
  if (status && status.tts && status.tts.available) {
    try {
      const r = await fetch('/api/voice/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, voice: voice || undefined }),
      });
      if (r.ok) {
        const ab = await r.arrayBuffer();
        const url = URL.createObjectURL(new Blob([ab], { type: 'audio/wav' }));
        const a = new Audio(url);
        a.onended = () => URL.revokeObjectURL(url);
        a.play();
        return;
      }
    } catch (e) {
      console.warn('[voice] Piper error, falling back', e);
    }
  }
  // Browser fallback — speechSynthesis.
  if ('speechSynthesis' in window) {
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 1.0;
    u.pitch = 1.0;
    window.speechSynthesis.speak(u);
  }
}

// Optional browser SpeechRecognition fallback for environments without Whisper.
let _browserSpeechRecognize = null;
if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
  _browserSpeechRecognize = (cb) => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    const rec = new SR();
    rec.lang = 'en-GB';
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    rec.onresult = (ev) => {
      const text = ev.results[0][0].transcript;
      if (cb) cb(text);
    };
    rec.onerror = () => {};
    rec.start();
  };
}

window.voiceRecordToggle = voiceRecordToggle;
window.voiceSpeak        = voiceSpeak;
window.voiceStatus       = voiceStatus;
