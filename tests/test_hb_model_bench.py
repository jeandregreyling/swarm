"""Owner 14 Nov: a clean record of every local model - GPU fit and programmer / researcher / social / useless, scored by HB's rules."""
from core import hb_model_bench as mb

GOOD_CODE = "```python\ndef merge_intervals(intervals):\n    out=[]\n    for s,e in sorted(intervals):\n        if out and s<=out[-1][1]:\n            out[-1][1]=max(out[-1][1],e)\n        else:\n            out.append([s,e])\n    return out\n```"


def test_scores_are_hbs_rules_not_a_models_opinion():
    assert mb.score_code(GOOD_CODE)[0] and not mb.score_code("```python\ndef merge_intervals(x):\n    return x\n```")[0]
    assert mb.score_tools('{"tool": "read_file", "arguments": {"path": "core/hb_rename.py", "start": 1, "end": 40}}')[0]
    assert not mb.score_tools('Sure! {"tool": "read_file", "arguments": {"path": "hb_rename.py"}}')[0]
    good = '1. Do, Operate, Execute, Sustain\n2. core/hb_rename.py\n3. scripts/hb_restart.py\n4. not in the text'
    assert mb.score_research(good)[0]
    made_up = good.replace('not in the text', '$500 a month')
    assert not mb.score_research(made_up)[0] and 'made up the budget' in mb.score_research(made_up)[1]
    assert mb.score_social("I'm sorry, that's really frustrating. Let me look into what broke and fix it properly this time.")[0]
    assert not mb.score_social('As an AI language model I cannot feel frustration.')[0]


def test_tags_and_gpu_fit():
    p = lambda *names: {n: {'passed': True} for n in names}
    assert mb.tags(p('programmer', 'tools')) == ['programmer']
    assert mb.tags(p('programmer')) == ['useless']                             # code without exact tool calls is not enough
    assert mb.tags(p('researcher', 'social')) == ['researcher', 'social', 'generalist']
    assert mb.gpu_fit(9.0) == (True, 10.5) and mb.gpu_fit(19.9)[0] is False and mb.gpu_fit(14.3)[0] is False


def test_one_model_run_records_every_test_and_says_each_result():
    answers = iter([GOOD_CODE, '{"tool": "read_file", "arguments": {"path": "core/hb_rename.py", "start": 1, "end": 40}}',
                    '1. Do, Operate, Execute, Sustain 2. core/hb_rename.py 3. hb_restart.py 4. not in the text', 'As an AI I cannot help.'])
    said = []
    rec = mb.run_model({'label': 'test-model', 'aliases': ['test-model'], 'size_gb': 4.7, 'path': '/x', 'endpoint': 'http://e'},
                       say=said.append, asker=lambda base, prompt, n: (next(answers), 5.0, 2.0))
    assert rec['tags'] == ['programmer', 'researcher', 'generalist'] and rec['gpu_fit'] and rec['tok_s'] == 5.0
    assert [s[0] for s in said[1:]] == ['✔', '✔', '✔', '✘'] and 'robotic' in said[-1]
