"""Tests verifying Homework BA is now Shakira (sassy Lola diva Business Analyst)."""
from core import hb_background, hb_homework as hw


def test_shakira_persona_and_spec_post():
    assert hw.BA_NAME == 'Shakira'
    assert 'Shakira' in hw.BA_METHOD and 'Lola diva' in hw.BA_METHOD
    assert hb_background.ROLE['homework'] == 'Shakira (BA)'
    post = hw.spec_post({'title': 'Build Liquid Glass'}, {'ready': True, 'goal': 'Polish glass UI', 'check': 'pytest tests/x.py'})
    assert '💃 Shakira (BA):' in post
    assert '📝 BA spec: Build Liquid Glass - READY for APEX' in post
