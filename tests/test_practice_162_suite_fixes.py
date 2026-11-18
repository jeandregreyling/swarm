"""Practice 162 (owner 18 Nov 2026, question suite): "...when does payroll create it?" is research; help.sap.com pages are kept in full
(advanced extraction, navigation dropped); an opening reply to HB's own check is dropped from the answer."""
import core.apex_tools as t
import core.hb_web_research as w
from core.hb_agent_tools import drop_check_reply


def test_practice_162_create_inside_a_question_is_research():
    assert t.research_question('What is wage type /XQE and when does payroll create it?')
    assert not t.research_question('Create a new test for core/hb_rename.py')
    assert not t.research_question('Can you fix the STP2 report in core/stp.py?')
    assert not t.research_question('Write a Python function that merges overlapping intervals.')


def test_practice_162_clean_extract_drops_navigation():
    raw = ('*   [Home](https://help.sap.com/docs/)\n*   [HR](https://help.sap.com/docs/HR)\n\n# Personnel calculation rule\n'
           '## Definition\nStatement for the execution of defined tasks in Time Management and Payroll.\n1. [Next](x)\n')
    assert w.clean_extract(raw) == ('# Personnel calculation rule\n## Definition\nStatement for the execution of defined tasks in Time '
                                    'Management and Payroll.')


def test_practice_162_extract_retries_advanced(monkeypatch):
    import io, json
    calls = []

    def fake(req, timeout=0):
        body = json.loads(req.data)
        calls.append(body['extract_depth'])
        res = ([] if body['extract_depth'] == 'basic' else
               [{'url': body['urls'][0], 'raw_content': '*   [Nav](x)\n# Page\n' + 'Real content line. ' * 20}])
        return io.BytesIO(json.dumps({'results': res}).encode())

    class Ctx:
        def __init__(self, f): self.f = f
        def __enter__(self): return self.f
        def __exit__(self, *a): return False
    monkeypatch.setattr(w.urllib.request, 'urlopen', lambda req, timeout=0: Ctx(fake(req, timeout)))
    import config
    monkeypatch.setattr(config, 'TAVILY_API_KEY', 'k', raising=False)
    out = w.extract(['https://help.sap.com/docs/x'])
    assert calls == ['basic', 'advanced'] and out['https://help.sap.com/docs/x'].startswith('# Page')


def test_practice_162_check_reply_dropped():
    assert drop_check_reply("Correcting my previous answer: /001 is a valuation basis.") == '/001 is a valuation basis.'
    assert drop_check_reply("You're right, I left one out. Here is the list: 3713787.") == 'Here is the list: 3713787.'
    assert drop_check_reply('The MCB is an annual cap.') == 'The MCB is an annual cap.'
