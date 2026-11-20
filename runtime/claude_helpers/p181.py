"""Prepare Practice 181: APEX's thinking steps are saved with each reply - 'How APEX got here (N steps)' under every APEX answer."""
import subprocess
import sys
sys.path.insert(0, '/home/jd/swarm')
from core import hb_change_sets as cs

STEP = sys.argv[1]
C = 'frontend/blueprints/chat.py'
PB = 'frontend/blueprints/peer_bridge.py'
TB = 'frontend/templates/terminal_base.html'

module = '''"""Practice 181 (owner 20 Nov 2026: "the thinking bubbles also disappear completely after the thought is done, I can't see what was the
process unless it's running actively, this needs to be saved"): the step lines APEX reports during a turn (Practice 176) are stored with
the reply message, and main chat shows them under the answer as "How APEX got here (N steps)".

save(conn, conversation_id, message_id, steps)   steps: [{'t': seconds since the turn started, 'text': line}]
for_messages(conn, ids) -> {message_id: steps}"""
import json
import time


def ensure(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS hb_turn_steps(message_id INTEGER PRIMARY KEY, conversation_id INTEGER, steps TEXT, created_at REAL)')


def save(conn, conversation_id, message_id, steps):
    steps = [s for s in (steps or []) if isinstance(s, dict) and str(s.get('text') or '').strip()][-200:]
    if not message_id or not steps:
        return False
    ensure(conn)
    conn.execute('INSERT OR REPLACE INTO hb_turn_steps VALUES (?,?,?,?)', (int(message_id), conversation_id, json.dumps(steps), time.time()))
    return True


def for_messages(conn, ids):
    ids = [int(i) for i in ids if str(i).isdigit()][:200]
    if not ids:
        return {}
    ensure(conn)
    rows = conn.execute(f"SELECT message_id, steps FROM hb_turn_steps WHERE message_id IN ({','.join('?' * len(ids))})", ids).fetchall()
    out = {}
    for mid, raw in rows:
        try:
            out[int(mid)] = json.loads(raw)
        except (TypeError, ValueError):
            pass
    return out
'''

js = r'''/* Practice 181 (owner 20 Nov 2026: "the thinking bubbles disappear completely after the thought is done ... this needs to be saved"):
   under each APEX reply in main chat, a closed "How APEX got here (N steps)" list - the steps HB recorded while APEX worked. */
(function () {
  var done = new Set(), busy = false;
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function apexBubbles() {
    return Array.prototype.filter.call(document.querySelectorAll('#home-chat-messages .hc-bubble.hc-agent[data-message-id]'), function (el) {
      var m = el._chatMessage || {};
      return String(m.sender || m.from_agent || '').toLowerCase() === 'apex' && !done.has(el.dataset.messageId);
    });
  }
  function took(t) { t = Math.max(0, Math.round(Number(t) || 0)); return t >= 60 ? Math.floor(t / 60) + ' min ' + (t % 60) + ' s' : t + ' s'; }
  function attach(el, steps) {
    if (el.querySelector('.hb-turn-steps')) return;
    var d = document.createElement('details');
    d.className = 'hb-turn-steps';
    d.style.cssText = 'margin-top:6px;font-size:12px;color:var(--text-dim,#999);';
    d.innerHTML = '<summary style="cursor:pointer;user-select:none;">How APEX got here (' + steps.length + ' steps, ' +
      took(steps[steps.length - 1].t) + ')</summary><ol style="margin:4px 0 0 18px;padding:0;line-height:1.5;">' +
      steps.map(function (s) { return '<li><span style="opacity:.6;font-variant-numeric:tabular-nums;">' + took(s.t) + '</span> ' + esc(s.text) + '</li>'; }).join('') +
      '</ol>';
    (el.querySelector('.hc-bubble-body') || el).appendChild(d);
  }
  function tick() {
    if (busy || document.hidden) return;
    var els = apexBubbles();
    if (!els.length) return;
    busy = true;
    var ids = els.map(function (el) { return el.dataset.messageId; });
    fetch('/api/peer/v1/hb/turn-steps?ids=' + ids.join(','), { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data || !data.ok) return;
        els.forEach(function (el) {
          var steps = data.steps[el.dataset.messageId];
          if (steps && steps.length) attach(el, steps);
          done.add(el.dataset.messageId);
        });
      }).catch(function () {}).finally(function () { busy = false; });
  }
  setInterval(tick, 2500);
  tick();
})();
'''

edits = [
    {'path': C, 'old': '''            def model_progress(event):
                # Practice 176: APEX's own step lines go to the thinking bubble as they are
                stage = str(event.get('text') or '') or (str(event.get('stage') or 'running').replace('_', ' ') + ': ' + selected_model)''',
     'new': '''            turn_steps, turn_started = [], time.monotonic()   # Practice 181: kept with the reply

            def model_progress(event):
                # Practice 176: APEX's own step lines go to the thinking bubble as they are
                stage = str(event.get('text') or '') or (str(event.get('stage') or 'running').replace('_', ' ') + ': ' + selected_model)
                if event.get('text'):
                    turn_steps.append({'t': round(time.monotonic() - turn_started, 1), 'text': stage[:200]})'''},
    {'path': C, 'old': '''                log_message(conv_id, APEX_AGENT['name'], response_text, to_agent='user',
                            message_type='response', tokens_used=tokens_used)
                if operator:
                    _share_apex_exchange(conv_id, operator_message_id, message, response_text,''', 'new': '''                log_message(conv_id, APEX_AGENT['name'], response_text, to_agent='user',
                            message_type='response', tokens_used=tokens_used)
                try:                                        # Practice 181: the steps stay with the reply
                    from core import hb_turn_steps
                    with __import__('contextlib').closing(get_connection()) as steps_conn, steps_conn:
                        reply_id = steps_conn.execute("SELECT MAX(id) FROM messages WHERE conversation_id=? AND from_agent=?",
                                                      (conv_id, APEX_AGENT['name'])).fetchone()[0]
                        hb_turn_steps.save(steps_conn, conv_id, reply_id, turn_steps)
                except Exception:
                    pass
                if operator:
                    _share_apex_exchange(conv_id, operator_message_id, message, response_text,'''},
    {'path': PB, 'old': "@peer_bridge_bp.route('/api/peer/v1/hb/queue',methods=['GET','POST'])\n", 'new': '''@peer_bridge_bp.route('/api/peer/v1/hb/turn-steps',methods=['GET'])
@require_owner
def hb_turn_steps_view(current_user=None):
    """Practice 181: the saved steps of APEX replies, for "How APEX got here" under each answer. ?ids=1,2,3"""
    from contextlib import closing
    from core import hb_turn_steps
    ids=[i for i in str(request.args.get('ids','')).split(',') if i.strip().isdigit()][:200]
    with closing(get_connection()) as conn:
        steps=hb_turn_steps.for_messages(conn,ids)
    return jsonify(ok=True,steps={str(k):v for k,v in steps.items()})


@peer_bridge_bp.route('/api/peer/v1/hb/queue',methods=['GET','POST'])
'''},
    {'path': TB, 'old': '<script src="/static/js/hb-live-activity.js?v={{ ASSET_VERSION }}"></script>\n',
     'new': '<script src="/static/js/hb-live-activity.js?v={{ ASSET_VERSION }}"></script>\n<script src="/static/js/hb-turn-steps.js?v={{ ASSET_VERSION }}"></script>\n'},
]

test = '''"""Practice 181: APEX's steps are saved with the reply and shown under it."""
import sqlite3
from pathlib import Path

from core import hb_turn_steps

ROOT = Path(__file__).resolve().parents[1]


def test_save_and_read_steps():
    c = sqlite3.connect(':memory:')
    steps = [{'t': 0.1, 'text': 'APEX thinking - round 1'}, {'t': 2.5, 'text': 'searching our notes: "MCB"'}, {'t': 3, 'text': ' '}]
    assert hb_turn_steps.save(c, 1, 42, steps)
    assert hb_turn_steps.for_messages(c, ['42', '43', 'x']) == {42: steps[:2]}
    assert not hb_turn_steps.save(c, 1, None, steps) and not hb_turn_steps.save(c, 1, 44, [])


def test_chat_records_and_page_shows_steps():
    chat = (ROOT / 'frontend/blueprints/chat.py').read_text()
    assert 'turn_steps.append(' in chat and 'hb_turn_steps.save(steps_conn, conv_id, reply_id, turn_steps)' in chat
    assert "/api/peer/v1/hb/turn-steps" in (ROOT / 'frontend/blueprints/peer_bridge.py').read_text()
    js = (ROOT / 'frontend/static/js/hb-turn-steps.js').read_text()
    assert 'How APEX got here' in js and "'<details" not in js and "createElement('details')" in js
    assert 'hb-turn-steps.js' in (ROOT / 'frontend/templates/terminal_base.html').read_text()
'''


def run(cmd):
    out = subprocess.run(cmd, cwd='/home/jd/swarm', capture_output=True, text=True, timeout=900)
    if out.returncode:
        print(out.stdout[-6000:])
    return out


out = cs.prepare(STEP, why=("Owner 20 Nov: \"the thinking bubbles also disappear completely after the thought is done, I can't see what was the "
                            "process unless it's running actively, this needs to be saved\". New core/hb_turn_steps (table hb_turn_steps); "
                            "chat.py collects APEX's step lines during the turn (Practice 176) and saves them with the reply message; "
                            "GET /api/peer/v1/hb/turn-steps?ids=...; new frontend/static/js/hb-turn-steps.js adds a closed 'How APEX got "
                            "here (N steps, time)' list under each APEX reply in main chat, also after a reload or HB restart."),
                 edits=edits, new_files={'core/hb_turn_steps.py': module, 'frontend/static/js/hb-turn-steps.js': js,
                                         'tests/test_practice_181_saved_steps.py': test},
                 test={'tests': ['tests/test_practice_181_saved_steps.py', 'tests/test_practice_176_see_apex_work.py',
                                 'tests/test_practice_165_routing_import.py', 'tests/test_practice_164_activity_route.py'], 'keyword': ''}, run=run)
print(out['verified'])
