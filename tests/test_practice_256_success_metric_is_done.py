"""Practice 256: a directive's own success metric is its definition of done."""
from core.hb_dream_method import CRITERIA_RE


def test_bulleted_success_metric_is_a_criterion():
    text = "## 1. MISSION\n- Live Capital: A$0.00.\n- Success Metric: Produce verifiable briefs for human grading.\n"
    assert [m.group(1) for m in CRITERIA_RE.finditer(text)] == ['Produce verifiable briefs for human grading.']


def test_the_old_forms_still_work():
    assert CRITERIA_RE.search('Done when: python -m pytest tests/x.py passes').group(1).startswith('python')
    assert CRITERIA_RE.search('* Success criteria: all green').group(1) == 'all green'
