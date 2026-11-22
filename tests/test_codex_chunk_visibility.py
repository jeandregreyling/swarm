import json
import subprocess
from contextlib import nullcontext
from pathlib import Path

from core import agent_identity, apex_routing, apex_tools, hb_chunks
from scripts import hummingbird_peer_worker as worker


def test_directive_constraints_are_not_work_chunks_and_later_steps_are_not_lost():
    directive = ('# Mission\n- Live capital: A$0. No trading.\n- Never ingest full reports.\n'
                 '1. Procurement: tender awards\n2. Financial filings\n'
                 '## Immediate step\nBefore ingestion, reply with a comprehension check.')
    assert hb_chunks.plan(directive) == []
    assert hb_chunks.plan('1. read the file\n2. change the label\n3. run the test') == [
        'read the file', 'change the label', 'run the test']
    assert hb_chunks.plan('Do: ' + ', then '.join('read file ' + str(i) for i in range(9))) == []
    assert hb_chunks.plan('Do: read ' + 'x' * 501 + ', then report') == []


def test_explicit_immediate_step_is_not_replaced_by_inferred_homework(monkeypatch):
    from core import hb_homework
    monkeypatch.setattr(hb_homework, 'latest', lambda *_: {'plan': ['Read mission', 'Search sources']})
    source = '# Mission\n- No trading\n## 5. IMMEDIATE EXECUTION STEP\nReply with JSON, then await confirmation.'
    assert hb_chunks._parts(None, {}, source) == []
    assert hb_chunks._parts(None, {}, 'Do: ' + ', then '.join('read file ' + str(i) for i in range(9))) == []


def test_peer_turn_publishes_real_model_progress(monkeypatch):
    monkeypatch.setattr(apex_routing, 'choose_local_model', lambda _: apex_routing.LocalRoute('test', 'general', 16384, 'test'))
    monkeypatch.setattr(agent_identity, 'execution', lambda *_a, **_k: nullcontext())
    def run(*_a, **_k):
        apex_routing.report_model_progress({'stage': 'step', 'text': 'APEX thinking - round 2'})
        return 'done', 1, []
    monkeypatch.setattr(apex_tools, 'run_apex_tools', run)
    events = []
    class API:
        def call(self, path, body):
            events.append((path, body))
            return {'ok': True}
    worker.local_turn(API(), {'id': 42, 'conversation_id': 1, 'body': 'Inspect'}, [], [])
    assert any(path.endswith('/progress') and body.get('stage') == 'APEX thinking - round 2' for path, body in events)


def test_live_view_shows_task_stage_and_real_chunk_shape():
    script = Path(__file__).resolve().parents[1] / 'frontend/static/js/hb-live.js'
    snap = {'lanes': [{'id': 'gpu', 'items': [{'title': 'Build <card>', 'last_step': 'reading file',
             'chunks': {'total': 3, 'doing': {'n': 2, 'text': 'edit <view>'}}}]}],
            'master': {'items': [{'state': 'now', 'title': 'Build',
              'chunks': {'total': 3, 'doing': {'n': 2, 'text': 'edit <view>'}}}]}}
    code = f"const R=require({json.dumps(str(script))}); const s={json.dumps(snap)}; console.log(JSON.stringify([R.renderActive(s,1),R.renderList(s)]));"
    active, board = json.loads(subprocess.check_output(['node', '-e', code], text=True))
    assert 'Build &lt;card&gt; · reading file' in active
    assert 'chunk 2/3: edit &lt;view&gt;' in active and 'chunk 2/3: edit &lt;view&gt;' in board
    assert ' · 2/3' in board
