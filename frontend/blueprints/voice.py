"""blueprints/voice.py — Voice I/O endpoints.

POST /api/voice/stt   audio multipart → {text}       (Whisper / faster-whisper)
POST /api/voice/tts   {text, voice?}  → audio/wav    (Piper)
GET  /api/voice/status               → {stt, tts, voices}

Both STT and TTS degrade gracefully: if the backing tool isn't installed the
endpoint returns HTTP 503 with `{ok: false, reason: "…"}` and the client falls
back to the browser's native SpeechRecognition / SpeechSynthesis.
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import tempfile
from typing import Optional

from flask import Blueprint, jsonify, request, Response

voice_bp = Blueprint('voice_bp', __name__)

# ── Backend detection ─────────────────────────────────────────────────────────

_PIPER_BIN = os.environ.get('PIPER_BIN') or shutil.which('piper')
_SWARM_ROOT = os.environ.get('SWARM_ROOT') or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PIPER_VOICES_DIR = os.environ.get('PIPER_VOICES_DIR', os.path.join(_SWARM_ROOT, 'models', 'piper'))
_PIPER_DEFAULT_VOICE = os.environ.get('PIPER_DEFAULT_VOICE', 'en_GB-alba-medium')

_WHISPER_MODEL = os.environ.get('WHISPER_MODEL', 'base.en')
_WHISPER_IMPL: Optional[str] = None
_whisper_singleton = None


def _load_whisper():
    """Lazy-load faster-whisper; fall back to openai-whisper; else None."""
    global _WHISPER_IMPL, _whisper_singleton
    if _whisper_singleton is not None or _WHISPER_IMPL == 'none':
        return _whisper_singleton
    try:
        from faster_whisper import WhisperModel  # type: ignore
        _whisper_singleton = WhisperModel(_WHISPER_MODEL, device='cpu',
                                          compute_type='int8')
        _WHISPER_IMPL = 'faster-whisper'
        return _whisper_singleton
    except Exception:
        pass
    try:
        import whisper  # type: ignore
        _whisper_singleton = whisper.load_model(_WHISPER_MODEL)
        _WHISPER_IMPL = 'openai-whisper'
        return _whisper_singleton
    except Exception:
        pass
    _WHISPER_IMPL = 'none'
    return None


def _list_piper_voices() -> list:
    if not os.path.isdir(_PIPER_VOICES_DIR):
        return []
    return sorted([
        f[:-5] for f in os.listdir(_PIPER_VOICES_DIR)
        if f.endswith('.onnx') and not f.startswith('.')
    ])


# ── Status ────────────────────────────────────────────────────────────────────

@voice_bp.route('/api/voice/status', methods=['GET'])
def voice_status():
    voices = _list_piper_voices()
    return jsonify({
        'ok': True,
        'stt': {
            'available': _WHISPER_IMPL not in (None, 'none') or _load_whisper() is not None,
            'impl': _WHISPER_IMPL or 'none',
            'model': _WHISPER_MODEL,
        },
        'tts': {
            'available': bool(_PIPER_BIN) and bool(voices),
            'binary': _PIPER_BIN,
            'voices': voices,
            'default_voice': _PIPER_DEFAULT_VOICE,
        },
    })


# ── STT ───────────────────────────────────────────────────────────────────────

@voice_bp.route('/api/voice/stt', methods=['POST'])
def voice_stt():
    model = _load_whisper()
    if model is None:
        return jsonify({
            'ok': False,
            'reason': 'whisper-not-installed',
            'hint': 'pip install faster-whisper (or openai-whisper).',
        }), 503

    audio_file = request.files.get('audio')
    if audio_file is None:
        return jsonify({'ok': False, 'error': 'missing "audio" file part'}), 400

    suffix = os.path.splitext(audio_file.filename or 'audio.webm')[1] or '.webm'
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        audio_file.save(tmp.name)
        tmp_path = tmp.name

    try:
        if _WHISPER_IMPL == 'faster-whisper':
            segments, _info = model.transcribe(tmp_path, language='en',
                                               beam_size=1, vad_filter=True)
            text = ' '.join(seg.text.strip() for seg in segments).strip()
        else:  # openai-whisper
            result = model.transcribe(tmp_path, language='en', fp16=False)
            text = (result.get('text') or '').strip()
        return jsonify({'ok': True, 'text': text, 'impl': _WHISPER_IMPL})
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ── TTS ───────────────────────────────────────────────────────────────────────

@voice_bp.route('/api/voice/tts', methods=['POST'])
def voice_tts():
    if not _PIPER_BIN:
        return jsonify({
            'ok': False,
            'reason': 'piper-not-installed',
            'hint': 'Install piper-tts and place voices under models/piper/.',
        }), 503

    data = request.get_json(silent=True) or {}
    text = (data.get('text') or '').strip()
    voice = (data.get('voice') or _PIPER_DEFAULT_VOICE).strip()
    if not text:
        return jsonify({'ok': False, 'error': 'missing text'}), 400
    # Sanity-cap: Piper is slow; never synthesize more than 4000 chars at once.
    text = text[:4000]

    # Reject path traversal in voice name.
    if '/' in voice or '..' in voice or not voice.replace('_', '').replace('-', '').isalnum():
        return jsonify({'ok': False, 'error': 'invalid voice name'}), 400

    voice_path = os.path.join(_PIPER_VOICES_DIR, voice + '.onnx')
    if not os.path.isfile(voice_path):
        return jsonify({
            'ok': False,
            'error': f'voice "{voice}" not installed',
            'available': _list_piper_voices(),
        }), 404

    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as wav_tmp:
        wav_path = wav_tmp.name

    try:
        proc = subprocess.run(
            [_PIPER_BIN, '--model', voice_path, '--output_file', wav_path],
            input=text.encode('utf-8'),
            capture_output=True,
            timeout=60,
        )
        if proc.returncode != 0:
            return jsonify({
                'ok': False,
                'error': 'piper failed',
                'stderr': proc.stderr.decode('utf-8', errors='replace')[:800],
            }), 500
        with open(wav_path, 'rb') as f:
            audio = f.read()
        return Response(audio, mimetype='audio/wav')
    except subprocess.TimeoutExpired:
        return jsonify({'ok': False, 'error': 'piper timeout'}), 504
    finally:
        try:
            os.unlink(wav_path)
        except OSError:
            pass
