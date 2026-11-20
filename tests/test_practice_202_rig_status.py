"""Practice 202: APEX's runtime_status carries the whole rig."""
import subprocess

from core import hb_workflow


def test_rig_status_has_every_part(monkeypatch):
    from core import hb_live
    monkeypatch.setattr(hb_live, 'telemetry', lambda: {'gpu': {'busy_pct': 40, 'temp_c': 55}, 'cpu': {'load1': 2.0}, 'ram': {}})
    monkeypatch.setattr(hb_live, 'apex_live', lambda: {'up': True, 'busy': False, 'prompt_tokens': 100})
    monkeypatch.setattr(hb_live, 'snapshot', lambda conn, tele=None: {'lanes': [{'id': 'gpu', 'items': [{'actor': 'apex', 'title': 'APEX: q', 'last_step': 'round 1'}]},
                                                                                  {'id': 'fred', 'items': []}], 'unexplained': []})
    monkeypatch.setattr('core.hb_gpu_guard.vram_free_gb', lambda: 2.8)
    run = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, stdout='active\n', stderr='')
    out = hb_workflow.rig_status(run=run)
    assert out['telemetry']['gpu']['temp_c'] == 55 and out['apex_live']['up']
    assert out['workers'] == {'gpu': [{'actor': 'apex', 'title': 'APEX: q', 'last_step': 'round 1'}]}
    assert out['services'] == {'apex-server': 'active', 'hummingbird-apex-peer': 'active', 'hb-translate': 'active'}
    assert out['ghost_reserve'] == {'free_gb': 2.8, 'keeps_gb': 2.0, 'ok': True}


def test_runtime_history_includes_the_rig():
    src = open('core/hb_workflow.py').read()
    assert "result['rig']=rig_status()" in src
