"""blueprints/curiosity.py — Curiosity organ HTTP surface.

Lets the user (or another agent) see and answer the questions Seven asks
when stuck. Phone-friendly minimal JSON API + a small HTML view.

Endpoints:
- GET  /api/curiosity/open?limit=20&min_salience=0
- GET  /api/curiosity/recent?limit=20&status=
- GET  /api/curiosity/stats
- POST /api/curiosity/answer    {id, answer, answered_by?, promote?}
- POST /api/curiosity/dismiss   {id, reason?}
- POST /api/curiosity/ask       {asked_by, question, salience?, options?, context_kind?, context_ref?}
- GET  /curiosity               → HTML inbox (mobile-friendly)
"""
from __future__ import annotations

import os
import sys

from flask import Blueprint, Response, jsonify, request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from core import curiosity  # type: ignore

curiosity_bp = Blueprint('curiosity_bp', __name__)


@curiosity_bp.route('/api/curiosity/open', methods=['GET'])
def open_questions():
    limit = int(request.args.get('limit', 20))
    min_sal = float(request.args.get('min_salience', 0.0))
    asked_by = request.args.get('asked_by') or None
    rows = curiosity.list_open(limit=limit, min_salience=min_sal, asked_by=asked_by)
    return jsonify({'ok': True, 'count': len(rows), 'questions': rows})


@curiosity_bp.route('/api/curiosity/recent', methods=['GET'])
def recent():
    limit = int(request.args.get('limit', 20))
    status = request.args.get('status') or None
    rows = curiosity.list_recent(limit=limit, status=status)
    return jsonify({'ok': True, 'count': len(rows), 'questions': rows})


@curiosity_bp.route('/api/curiosity/stats', methods=['GET'])
def stats():
    return jsonify({'ok': True, 'stats': curiosity.stats()})


@curiosity_bp.route('/api/curiosity/answer', methods=['POST'])
def answer():
    data = request.get_json(silent=True) or {}
    qid = data.get('id')
    ans = (data.get('answer') or '').strip()
    if not qid or not ans:
        return jsonify({'ok': False, 'error': 'id and answer required'}), 400
    ok = curiosity.answer(
        int(qid), ans,
        answered_by=data.get('answered_by') or 'user',
        promote_to_belief=bool(data.get('promote', True)),
    )
    return jsonify({'ok': ok})


@curiosity_bp.route('/api/curiosity/dismiss', methods=['POST'])
def dismiss():
    data = request.get_json(silent=True) or {}
    qid = data.get('id')
    if not qid:
        return jsonify({'ok': False, 'error': 'id required'}), 400
    ok = curiosity.dismiss(int(qid), reason=data.get('reason'))
    return jsonify({'ok': ok})


@curiosity_bp.route('/api/curiosity/ask', methods=['POST'])
def ask():
    data = request.get_json(silent=True) or {}
    asked_by = (data.get('asked_by') or '').strip()
    q = (data.get('question') or '').strip()
    if not asked_by or not q:
        return jsonify({'ok': False, 'error': 'asked_by and question required'}), 400
    qid = curiosity.ask(
        asked_by, q,
        context_kind=data.get('context_kind'),
        context_ref=data.get('context_ref'),
        options=data.get('options'),
        salience=float(data.get('salience', 0.5)),
    )
    return jsonify({'ok': qid is not None, 'id': qid})


_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Seven · Curiosity Inbox</title>
<style>
:root{color-scheme:dark light}
body{font:15px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
     margin:0;padding:14px;background:#0e0e10;color:#e7e7ea;max-width:820px;margin:0 auto}
h1{font-size:18px;margin:4px 0 12px;color:#9ad}
.q{background:#17171b;border:1px solid #26262c;border-radius:10px;padding:12px;margin:10px 0}
.meta{font-size:12px;color:#888;margin-bottom:6px}
.sal-1{border-left:3px solid #d44}
.sal-9{border-left:3px solid #e80}
.sal-7{border-left:3px solid #ec0}
.q .text{font-weight:600;margin-bottom:8px}
.opts{margin:6px 0;padding:6px 0;border-top:1px dashed #2a2a30;border-bottom:1px dashed #2a2a30;font-size:13px;color:#aab}
textarea{width:100%;background:#0a0a0c;color:#e7e7ea;border:1px solid #26262c;
         border-radius:6px;padding:8px;font:14px ui-monospace,monospace;min-height:60px;box-sizing:border-box}
button{background:#244;color:#cef;border:0;border-radius:6px;padding:8px 14px;
       margin:6px 6px 0 0;cursor:pointer;font-size:14px}
button.dismiss{background:#411;color:#fcc}
.empty{color:#666;padding:30px;text-align:center}
.stats{font-size:12px;color:#789;margin:8px 0 16px}
</style></head><body>
<h1>Seven · Curiosity Inbox</h1>
<div class="stats" id="stats">…</div>
<div id="list"></div>
<script>
async function load(){
  const s = await (await fetch('/api/curiosity/stats')).json();
  document.getElementById('stats').textContent =
    `open=${s.stats.open} · answered=${s.stats.answered} · dismissed=${s.stats.dismissed} · expired=${s.stats.expired}`;
  const r = await (await fetch('/api/curiosity/open?limit=50')).json();
  const list = document.getElementById('list');
  if(!r.questions.length){ list.innerHTML = '<div class="empty">no open questions · Seven knows what he needs to know</div>'; return; }
  list.innerHTML = r.questions.map(q=>{
    const sal = q.salience>=0.95?'sal-1':q.salience>=0.85?'sal-9':q.salience>=0.7?'sal-7':'';
    const opts = (q.options && q.options.length) ? `<div class="opts">${q.options.map(o=>`• ${o}`).join('<br>')}</div>` : '';
    return `<div class="q ${sal}" data-id="${q.id}">
      <div class="meta">#${q.id} · ${q.asked_by} · sal=${q.salience.toFixed(2)} · ${q.context_kind||'-'} · ${q.context_ref||''}</div>
      <div class="text">${q.question.replace(/</g,'&lt;')}</div>
      ${opts}
      <textarea placeholder="answer…"></textarea>
      <div><button onclick="answer(${q.id},this)">answer</button>
           <button class="dismiss" onclick="dismiss(${q.id})">dismiss</button></div>
    </div>`;
  }).join('');
}
async function answer(id, btn){
  const ta = btn.closest('.q').querySelector('textarea');
  const ans = ta.value.trim();
  if(!ans) return ta.focus();
  const r = await fetch('/api/curiosity/answer',{method:'POST',headers:{'content-type':'application/json'},
    body:JSON.stringify({id, answer:ans, answered_by:'user'})});
  if((await r.json()).ok) load();
}
async function dismiss(id){
  if(!confirm('Dismiss #'+id+'?')) return;
  const r = await fetch('/api/curiosity/dismiss',{method:'POST',headers:{'content-type':'application/json'},
    body:JSON.stringify({id, reason:'user dismissed'})});
  if((await r.json()).ok) load();
}
load();
setInterval(load, 30000);
</script></body></html>
"""


@curiosity_bp.route('/curiosity', methods=['GET'])
def inbox():
    return Response(_HTML, mimetype='text/html; charset=utf-8')
