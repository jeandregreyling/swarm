"""Practice 182: the translator runs only when wanted."""
import sqlite3
import subprocess
from pathlib import Path

from core import hb_translator as t

ROOT = Path(__file__).resolve().parents[1]


class Ctl:
    def __init__(self, active=False):
        self.active, self.calls = active, []

    def __call__(self, cmd, **kw):
        verb = cmd[2]
        self.calls.append(verb)
        if verb == 'start':
            self.active = True
        if verb == 'stop':
            self.active = False
        return subprocess.CompletedProcess(cmd, 0, stdout='active' if self.active else 'inactive', stderr='')


def test_button_starts_and_stops():
    c, ctl = sqlite3.connect(':memory:'), Ctl()
    assert t.switch(c, True, run=ctl) == (True, True) and t.mode(c)[0] == 'manual'
    assert t.switch(c, False, run=ctl) == (True, False) and 'disable' in ctl.calls and t.mode(c)[0] == 'off'


def test_asian_language_reply_starts_it_and_it_stops_when_quiet():
    c, ctl, said = sqlite3.connect(':memory:'), Ctl(), []
    assert t.on_reply(c, 'apex', 'The cap is annual.' * 3, run=ctl) is None
    zh = '最高缴款基数是年度上限，超出部分记入工资类型 XQE，不计入养老金缴款基数。'
    assert t.on_reply(c, 'qwen-cn', zh, run=ctl, say=said.append, now=1000) == 'started'
    assert ctl.active and 'Chinese' in said[0] and t.languages(c) == [{'model': 'qwen-cn', 'lang': 'zh'}]
    assert not t.idle_tick(c, now=1000 + 60, run=ctl)
    assert t.idle_tick(c, now=1000 + t.AUTO_IDLE_S + 1, run=ctl) and not ctl.active


def test_manual_start_is_not_stopped_by_idle():
    c, ctl = sqlite3.connect(':memory:'), Ctl()
    t.switch(c, True, run=ctl, now=1)
    assert not t.idle_tick(c, now=10 ** 6, run=ctl) and ctl.active


def test_language_detection():
    assert t.language_of('こんにちは、元気ですか') == 'ja' and t.language_of('안녕하세요 반갑습니다') == 'ko' and t.language_of('你好') == 'zh'


def test_page_defaults_off_and_syncs_the_service():
    js = (ROOT / 'frontend/static/js/hb-translate-bubble.js').read_text()
    assert "localStorage.getItem(KEY_ON) === '1'" in js and "localStorage.getItem(KEY_IN) === '1'" in js
    assert "/api/peer/v1/hb/translator" in js and 'syncServer(any)' in js
    assert '_translator_watch(from_agent, content)' in (ROOT / 'utils/db/chat.py').read_text()
