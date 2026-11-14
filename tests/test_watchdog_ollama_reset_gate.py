"""Owner 14 Nov 2026: the watchdog only hard-resets ollama when ollama actually serves the
timed-out agent's model (llama.cpp serves most models now), and every reset or skip is said
in main chat with the agent named."""
import utils.watchdog_does as wd


def test_no_ollama_reset_when_ollama_does_not_serve_the_model(monkeypatch):
    monkeypatch.setitem(wd.WORK_AGENT_MODELS, 'tester', 'qwen2.5:14b-instruct')
    monkeypatch.setattr(wd, '_direct_model', lambda model: '')      # not llama.cpp-direct
    monkeypatch.setattr(wd, '_ollama_serves', lambda model: False)  # ollama has no such model
    def forbidden(*a, **k):
        raise AssertionError('subprocess must not run when ollama does not serve the model')
    monkeypatch.setattr(wd.subprocess, 'run', forbidden)
    said = []
    monkeypatch.setattr(wd, '_announce', said.append)
    note = wd._hard_reset_ollama_after_timeout('tester', 'micro')
    assert 'no ollama reset' in note and 'tester' in note and said


def test_ollama_reset_fires_and_is_announced_when_ollama_serves_it(monkeypatch):
    monkeypatch.setitem(wd.WORK_AGENT_MODELS, 'tester', 'mistral-small:24b')
    monkeypatch.setattr(wd, '_direct_model', lambda model: '')
    monkeypatch.setattr(wd, '_ollama_serves', lambda model: True)
    class R:
        returncode = 0
        stderr = stdout = ''
    calls = []
    monkeypatch.setattr(wd.subprocess, 'run', lambda *a, **k: (calls.append(a[0]), R())[1])
    said = []
    monkeypatch.setattr(wd, '_announce', said.append)
    note = wd._hard_reset_ollama_after_timeout('tester', 'micro')
    assert 'ollama hard reset after tester micro timeout' in note
    assert any('kill' in part for cmd in calls for part in cmd)   # kill then start
    assert said
