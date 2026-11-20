"""Practice 201: one APEX at a time; run_tests in main chat; APEX's lessons on every card."""
from pathlib import Path

from core import hb_channels, hb_learning

ROOT = Path(__file__).resolve().parents[1]


class Lock:
    def __init__(self, ok):
        self.ok, self.released = ok, False

    def acquire(self, timeout=None, on_wait=None):
        self.timeout = timeout
        return self.ok

    def release(self):
        self.released = True


def test_phone_answers_queue_on_main_chats_lock(monkeypatch):
    held = Lock(False)
    monkeypatch.setattr('core.hb_process_lock.ProcessLock', lambda name: held)
    assert 'finishing a main-chat turn' in hb_channels.answer_only('q?')
    free = Lock(True)
    monkeypatch.setattr('core.hb_process_lock.ProcessLock', lambda name: free)
    monkeypatch.setattr(hb_channels, '_answer_only', lambda q, h=(): 'answered')
    assert hb_channels.answer_only('q?') == 'answered' and free.released and free.timeout == 1260


def test_main_chat_waits_for_the_model():
    src = (ROOT / 'frontend/blueprints/chat.py').read_text()
    assert 'queue_timeout_s=min(240, max(1, remaining // 2))' in src and 'queue_timeout_s=1,' not in src


def test_run_tests_without_a_step_runs_and_says_so():
    src = (ROOT / 'core/hb_agent_tools.py').read_text()
    assert "if not task or not task.get('step_id'):" in src and 'Not recorded against a Studio step' in src


def test_lessons_ride_on_every_card():
    text = hb_learning.apex_lessons()
    assert text.startswith('Your lessons') and 'Check the tools attached to THIS turn' in text and 'four real attempts' in text
    assert 'apex_lessons()' in (ROOT / 'core/hb_dream_method.py').read_text()
