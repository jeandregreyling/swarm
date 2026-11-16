#!/usr/bin/env python3
"""HB local NMT translation micro-service (owner request, 15 Nov 2026).

Detects the language of a text, compares it with the reader's preferred language(s) and,
when they differ, translates it with a local OPUS-MT (MarianMT) model on the CPU.
Runs offline: no API calls, no GPU, nothing sent anywhere. APEX (port 8080) is not involved.

Install (once, into its own folder so HB's environment is untouched):
    pip install --target /srv/archive/models/opus-mt/site torch --index-url https://download.pytorch.org/whl/cpu
    pip install --target /srv/archive/models/opus-mt/site "transformers>=4.40,<5" sentencepiece sacremoses langdetect

Fetch models (once per language pair, about 300 MB each; the only step that uses the network):
    hb_nmt_translate.py --download zh-en en-fr

Use:
    hb_nmt_translate.py --target en "构建又挂了，回滚上次提交。"
    echo "text" | hb_nmt_translate.py --user ghost          # targets = that user's HB account languages
    hb_nmt_translate.py --serve 8082                         # POST {"text": ..., "targets": ["en"]} or {"user": "ghost"}

Output (one JSON object per target language; a list when there are several targets):
    {"original_text", "translated_text", "detected_source_lang", "target_lang", "translated", "model", "seconds"}

Limits worth knowing:
  - One model per language pair. A pair with no direct model goes through English (two models, two passes).
  - A pair with no model at all returns "translated": false and an "error"; nothing is invented.
  - Fenced code blocks are passed through unchanged; inline `code` stays inside its sentence.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

HOME = Path(os.environ.get('HB_NMT_HOME', '/srv/archive/models/opus-mt'))
SITE = HOME / 'site'
MODELS = HOME / 'models'
HB_DB = Path(os.environ.get('HB_DB', '/srv/archive/projects/swarm/swarm_memory.db'))
if SITE.is_dir() and str(SITE) not in sys.path:
    sys.path.insert(0, str(SITE))

# Direct models whose name is not simply opus-mt-<src>-<tgt>. None = known to be missing.
MODEL_NAMES = {
    ('en', 'ja'): 'Helsinki-NLP/opus-mt-en-jap',
    ('en', 'ko'): 'Helsinki-NLP/opus-mt-tc-big-en-ko',
    ('en', 'pt'): 'Helsinki-NLP/opus-mt-tc-big-en-pt',
    ('pt', 'en'): 'Helsinki-NLP/opus-mt-ROMANCE-en',
    ('en', 'tr'): 'Helsinki-NLP/opus-mt-tc-big-en-tr',
    ('en', 'th'): None,
    ('en', 'pl'): None,
}
PIVOT = 'en'
MAX_CHARS = 400          # per segment sent to the model
_loaded: dict = {}


# ── language detection ───────────────────────────────────────────────────────────────────────
_CODE = re.compile(r'```.*?(?:```|\Z)|`[^`\n]*`', re.S)
_SCRIPTS = (('ja', re.compile(r'[぀-ヿ]')), ('ko', re.compile(r'[가-힯]')),
            ('zh', re.compile(r'[㐀-鿿]')), ('th', re.compile(r'[฀-๿]')),
            ('ru', re.compile(r'[Ѐ-ӿ]')), ('ar', re.compile(r'[؀-ۿ]')),
            ('hi', re.compile(r'[ऀ-ॿ]')))


def detect_language(text: str) -> str | None:
    """Language code of the text ('en', 'zh', 'ja', ...) or None when there is too little to tell."""
    plain = re.sub(r'https?://\S+|[\w.-]*[/\\][\w./\\-]+', ' ', _CODE.sub(' ', text or ''))
    counts = {code: len(rx.findall(plain)) for code, rx in _SCRIPTS}
    latin = len(re.findall(r'[A-Za-zÀ-ɏḀ-ỿ]', plain))
    dense = (counts['zh'] + counts['ja'] + counts['ko']) * 3 + counts['th'] + counts['ru'] + counts['ar'] + counts['hi']
    if sum(counts.values()) >= 4 and dense >= latin * 0.6:
        if counts['ja'] >= 3 and counts['ja'] * 6 >= counts['zh']:
            return 'ja'
        return max((c for c in counts if c != 'ja'), key=lambda c: counts[c])
    if latin < 12:
        return None
    try:
        from langdetect import DetectorFactory, detect_langs
        DetectorFactory.seed = 0                      # same text, same answer
        best = detect_langs(plain)[0]
    except Exception:
        return None
    if best.prob < 0.80:
        return None
    return best.lang.split('-')[0].lower()


# ── HB account languages ─────────────────────────────────────────────────────────────────────
def preferred_languages(username: str, default=('en',)) -> list[str]:
    """The user's preferred languages from the HB database (table user_language_prefs)."""
    try:
        conn = sqlite3.connect(f'file:{HB_DB}?mode=ro', uri=True, timeout=10)
        try:
            row = conn.execute('SELECT languages FROM user_language_prefs WHERE username=?', (username,)).fetchone()
        finally:
            conn.close()
        langs = [str(c) for c in json.loads(row[0])] if row else []
    except (sqlite3.Error, ValueError, TypeError):
        langs = []
    return [c for c in langs if not c.startswith('x:')] or list(default)


# ── models ───────────────────────────────────────────────────────────────────────────────────
def _base(code: str) -> str:
    return code.split('-')[0].lower()


def model_name(src: str, tgt: str) -> str | None:
    key = (_base(src), _base(tgt))
    return MODEL_NAMES[key] if key in MODEL_NAMES else f'Helsinki-NLP/opus-mt-{key[0]}-{key[1]}'


def _local_dir(name: str) -> Path:
    return MODELS / name.replace('/', '__')


def download(pairs: list[str]) -> None:
    """Fetch models for pairs like 'zh-en'. The only function that touches the network."""
    from huggingface_hub import snapshot_download
    for pair in pairs:
        src, tgt = pair.split('-', 1)
        name = model_name(src, tgt)
        if not name:
            print(f'{pair}: no OPUS-MT model exists for this pair', file=sys.stderr)
            continue
        target = _local_dir(name)
        snapshot_download(name, local_dir=target, allow_patterns=['*.json', '*.spm', '*.txt', 'pytorch_model.bin', '*.safetensors'])
        print(f'{pair}: {name} -> {target}')


def _load(src: str, tgt: str):
    """Tokenizer and model for one direction, from disk only. None when it is not on disk."""
    key = (_base(src), _base(tgt))
    if key in _loaded:
        return _loaded[key]
    name = model_name(*key)
    path = _local_dir(name) if name else None
    if not path or not path.is_dir():
        _loaded[key] = None
        return None
    os.environ.setdefault('HF_HUB_OFFLINE', '1')
    os.environ.setdefault('TRANSFORMERS_OFFLINE', '1')
    import torch
    from transformers import MarianMTModel, MarianTokenizer
    torch.set_num_threads(int(os.environ.get('HB_NMT_THREADS', '6')))
    tokenizer = MarianTokenizer.from_pretrained(path, local_files_only=True)
    model = MarianMTModel.from_pretrained(path, local_files_only=True).eval()
    _loaded[key] = (tokenizer, model, name)
    return _loaded[key]


def _route(src: str, tgt: str):
    """[(tokenizer, model, name), ...] to get from src to tgt: direct, else through English. None if impossible."""
    direct = _load(src, tgt)
    if direct:
        return [direct]
    if PIVOT in (_base(src), _base(tgt)):
        return None
    first, second = _load(src, PIVOT), _load(PIVOT, tgt)
    return [first, second] if first and second else None


# ── translation ──────────────────────────────────────────────────────────────────────────────
_FENCE = re.compile(r'```.*?(?:```|\Z)', re.S)      # inline `code` stays in its sentence: the model copies it
_SENTENCE_END = re.compile(r'(?<=[。！？!?；;])|(?<=[.])\s+')


def _segments(text: str) -> list[tuple[bool, str]]:
    """(translate?, piece) list. Fenced code, blank lines and line breaks are kept exactly."""
    out: list[tuple[bool, str]] = []
    last = 0
    for m in _FENCE.finditer(text):
        if m.start() > last:
            out += _split_plain(text[last:m.start()])
        out.append((False, m.group(0)))
        last = m.end()
    if last < len(text):
        out += _split_plain(text[last:])
    return out


def _split_plain(text: str) -> list[tuple[bool, str]]:
    out: list[tuple[bool, str]] = []
    for line in re.split(r'(\n)', text):
        if not line.strip():
            if line:
                out.append((False, line))
            continue
        lead = line[:len(line) - len(line.lstrip())]
        tail = line[len(line.rstrip()):]
        if lead:
            out.append((False, lead))
        # One sentence per piece: these models are trained on single sentences and drop
        # the end of a longer passage.
        first = True
        for sentence in (x for x in _SENTENCE_END.split(line.strip()) if x and x.strip()):
            if not first:
                out.append((False, ' '))
            first = False
            while len(sentence) > MAX_CHARS:
                out.append((True, sentence[:MAX_CHARS]))
                sentence = sentence[MAX_CHARS:]
            out.append((True, sentence.strip()))
        if tail:
            out.append((False, tail))
    return out


def _run(step, pieces: list[str]) -> list[str]:
    import torch
    tokenizer, model, _ = step
    out: list[str] = []
    for i in range(0, len(pieces), 8):
        batch = tokenizer(pieces[i:i + 8], return_tensors='pt', padding=True, truncation=True, max_length=512)
        with torch.no_grad():
            generated = model.generate(**batch, num_beams=4, max_new_tokens=512)
        out += tokenizer.batch_decode(generated, skip_special_tokens=True)
    return out


def translate(text: str, target: str, source: str | None = None) -> dict:
    """Translate text into target unless it is already in that language. Always returns the JSON-ready dict."""
    started = time.time()
    source = source or detect_language(text)
    result = {'original_text': text, 'translated_text': text, 'detected_source_lang': source,
              'target_lang': target, 'translated': False, 'model': None}
    if not source:
        result['error'] = 'language not recognised'
    elif _base(source) == _base(target):
        pass                                           # same language: nothing to do
    else:
        route = _route(source, target)
        if not route:
            wanted = model_name(source, target) or f'{_base(source)}-{PIVOT} + {PIVOT}-{_base(target)}'
            result['error'] = f'no local model for {_base(source)}->{_base(target)} (wanted {wanted}; fetch with --download)'
        else:
            segments = _segments(text)
            pieces = [piece for keep, piece in segments if keep]
            for step in route:
                pieces = _run(step, pieces)
            it = iter(pieces)
            result['translated_text'] = ''.join(next(it) if keep else piece for keep, piece in segments)
            result['translated'] = True
            result['model'] = ' -> '.join(step[2] for step in route)
    result['seconds'] = round(time.time() - started, 2)
    return result


def translate_for(text: str, targets: list[str]) -> list[dict]:
    """One result per preferred language. Empty when the text is already in one of them."""
    source = detect_language(text)
    if source and any(_base(t) == _base(source) for t in targets):
        return []
    return [translate(text, target, source) for target in targets]


# ── optional local HTTP service ──────────────────────────────────────────────────────────────
def serve(port: int) -> None:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading
    lock = threading.Lock()                            # one translation at a time on the CPU

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, payload) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Access-Control-Allow-Origin', self.headers.get('Origin') or '*')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):                          # noqa: N802
            self._send(200, {})

        def do_GET(self):                              # noqa: N802
            self._send(200, {'status': 'ok', 'loaded': [f'{a}-{b}' for (a, b), v in _loaded.items() if v]})

        def do_POST(self):                             # noqa: N802
            try:
                data = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'{}')
                text = str(data.get('text') or '')[:20000]
                targets = data.get('targets') or (preferred_languages(str(data['user'])) if data.get('user') else ['en'])
                if not text.strip() or not isinstance(targets, list):
                    return self._send(400, {'error': 'text and targets (list) or user required'})
                with lock:
                    results = translate_for(text, [str(t) for t in targets][:5])
                self._send(200, {'detected_source_lang': detect_language(text), 'results': results})
            except Exception as exc:                   # keep the service alive on a bad request
                self._send(500, {'error': f'{type(exc).__name__}: {exc}'})

        def log_message(self, *args):                  # quiet
            pass

    ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()


def main() -> None:
    ap = argparse.ArgumentParser(description='HB local NMT translation (offline OPUS-MT on CPU).')
    ap.add_argument('text', nargs='*', help='text to translate (or stdin)')
    ap.add_argument('--target', action='append', help='target language code; repeat for several')
    ap.add_argument('--user', help="HB username: targets are that account's preferred languages")
    ap.add_argument('--download', nargs='+', metavar='SRC-TGT', help='fetch models, e.g. zh-en en-fr')
    ap.add_argument('--serve', type=int, metavar='PORT', help='run as a local HTTP service on 127.0.0.1')
    args = ap.parse_args()
    if args.download:
        return download(args.download)
    if args.serve:
        return serve(args.serve)
    text = ' '.join(args.text) if args.text else sys.stdin.read()
    targets = args.target or (preferred_languages(args.user) if args.user else ['en'])
    if len(targets) == 1:
        print(json.dumps(translate(text, targets[0]), ensure_ascii=False, indent=2))
    else:
        source = detect_language(text)
        print(json.dumps([translate(text, t, source) for t in targets], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
