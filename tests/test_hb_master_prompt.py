"""Owner 13 Nov: one master protocol for every agent in HB (DOES replaces DEOS), from a versioned pack; thinking is recorded;
models may propose changes to their instructions, which become plan steps for the owner. Claude Code is exempt for now."""
import json
import sqlite3
from pathlib import Path

from core import hb_master_prompt as mp

ROOT = Path(__file__).resolve().parents[1]


def test_every_agent_gets_the_protocol_with_its_own_role_and_claude_is_exempt():
    for agent, words in [('apex', 'primary local executor'), ('fred', 'senior local reviewer'), ('codex-instructor', 'Codex'),
                         ('gemini-advisor', 'Gemini'), ('nanny', 'nanny bot'), ('some-new-model', 'a local model working in HB')]:
        text = mp.for_role(agent)
        assert 'DOES' in text and 'replaces the older DEOS' in text and words in text and '[Final Verdict & Action]' in text
    assert mp.for_role('claude-code') == ''
    small = mp.for_role('nanny', compact=True)
    assert len(small) < 900 and 'DOES' in small


def test_the_four_blocks_are_read_from_a_reply():
    reply = ('Patched home-chat.js; practice 11 passes.\n[KC & Git State] read lines 100-126.\n[Pragmatic Analysis]: risk is low.\n'
             '[Evolution & Alternative] none.\n[Final Verdict & Action] run_tests practice_11.')
    blocks = mp.reasoning_blocks(reply)
    assert list(blocks) == list(mp.BLOCKS) and blocks['Pragmatic Analysis'] == 'risk is low.'
    assert mp.reasoning_blocks('done') == {}


def test_thinking_is_recorded_and_a_prompt_change_proposal_becomes_a_plan_step():
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE project_steps(step_id TEXT PRIMARY KEY, project_id TEXT, title TEXT, description TEXT, status TEXT, '
                 'owner TEXT, order_idx REAL, created_at REAL, updated_at REAL, residual_risk TEXT)')
    events = []
    from core import hb_tasks
    original = hb_tasks.event
    hb_tasks.event = lambda conn, task, agent, kind, payload, **k: events.append((agent, kind, payload))
    try:
        result = mp.record(conn, {'task_id': 'T-000000000001'}, 'apex',
                           'Stuck.\n[KC & Git State] x\n[Final Verdict & Action] y\n[Prompt change proposal] Allow two patches per turn because ...')
    finally:
        hb_tasks.event = original
    assert result['blocks'] == 2 and events[0][1] == 'reasoning' and events[0][2]['blocks']['Final Verdict & Action'] == 'y'
    step = conn.execute('SELECT title, owner, status FROM project_steps WHERE step_id=?', (result['proposal_step'],)).fetchone()
    assert step[0].startswith('Prompt change proposal from apex') and step[1] == 'jd' and step[2] == 'todo'


def test_every_prompt_builder_uses_the_protocol():
    assert "for_role('apex')" in (ROOT / 'scripts' / 'hummingbird_peer_worker.py').read_text()
    assert "for_role('apex')" in (ROOT / 'core' / 'chat_continuity.py').read_text()
    assert "for_role('fred')" in (ROOT / 'core' / 'hb_local_review.py').read_text()
    assert "for_role('nanny', compact=True)" in (ROOT / 'core' / 'hb_nanny_bot.py').read_text()
    assert "for_role('gemini-advisor')" in (ROOT / 'scripts' / 'hummingbird_gemini_peer.py').read_text()
    bridge = (ROOT / 'core' / 'peer_bridge.py').read_text()
    assert "routing['hb_protocol']=protocol" in bridge and 'record_thinking(conn,task,author,text,cur.lastrowid)' in bridge


def test_pack_is_valid_json_with_a_version():
    data = json.loads((ROOT / 'core' / 'capability_packs' / 'hb.master.protocol.v1.json').read_text())
    assert data['version'] in ('1.0.0', '1.1.0', '1.2.0', '1.3.0', '1.4.0', '1.5.0', '1.6.0', '1.7.0', '1.8.0', '1.9.0') and set(data['roles']) >= {'apex', 'fred', 'nanny', 'codex-instructor', 'gemini-advisor', 'default'}
