"""Practice 158 (owner 18 Nov 2026): the card reset at 13:36:56; APEX said /health ok but answered nothing until JD restarted it by hand.
The GPU guard now reads the kernel log itself and restarts APEX only when a test answer fails (and only while APEX is idle)."""
import sqlite3

from core import hb_gpu_guard as g

LINE = 'amdgpu 0000:08:00.0: [drm] device wedged, but recovered through reset'


def db():
    return sqlite3.connect(':memory:')


def test_practice_158_reset_and_no_answer_restarts():
    c, said, calls = db(), [], []
    answers = iter([False, True])
    out = g.reset_tick(c, now=10_000, resets=lambda since: [LINE], idle=lambda: True, answers=lambda: next(answers),
                       restart=lambda: calls.append('restart') or True, say=said.append)
    assert calls == ['restart'] and said and 'A test answer works again' in said[0] and out == said[0]


def test_practice_158_reset_but_answers_does_nothing():
    c, calls = db(), []
    assert g.reset_tick(c, now=10_000, resets=lambda since: [LINE], idle=lambda: True, answers=lambda: True,
                        restart=lambda: calls.append('restart') or True, say=print) is None
    assert calls == []


def test_practice_158_busy_apex_is_left_alone_and_checked_later():
    c, calls = db(), []
    assert g.reset_tick(c, now=10_000, resets=lambda since: [LINE], idle=lambda: False, answers=lambda: False,
                        restart=lambda: calls.append('restart') or True, say=print) is None
    assert calls == [] and c.execute('SELECT COUNT(*) FROM hb_gpu_reset_watch').fetchone()[0] == 0


def test_practice_158_no_reset_no_probe_and_rate_limited():
    c = db()
    probe = lambda: (_ for _ in ()).throw(AssertionError('no probe'))
    assert g.reset_tick(c, now=10_000, resets=lambda since: [], idle=lambda: True, answers=probe, restart=probe, say=print) is None
    assert g.reset_tick(c, now=10_030, resets=lambda since: [LINE], idle=lambda: True, answers=probe, restart=probe, say=print) is None


def test_practice_158_kernel_sign():
    assert g.RESET_SIGN.search('amdgpu 0000:08:00.0: Starting comp_1.0.1 ring reset')
    assert g.RESET_SIGN.search(LINE) and not g.RESET_SIGN.search('amdgpu: power state changed')
