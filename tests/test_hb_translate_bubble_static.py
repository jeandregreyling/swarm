"""15 Nov (owner): Mandarin translate bubble above the main chat box, fed by a CPU-only worker on port 8081."""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / 'frontend' / 'static' / 'js' / 'hb-translate-bubble.js'
TEMPLATE = ROOT / 'frontend' / 'templates' / 'terminal_base.html'

HARNESS = r'''
global.window = {}; global.location = {protocol: 'http:', hostname: 'localhost'};
global.localStorage = {getItem: () => null, setItem() {}};
global.document = {readyState: 'complete', getElementById: () => null, addEventListener() {}};
global.setTimeout = () => 0; global.clearTimeout = () => {};
require(process.argv[1]);
const t = window.hbTranslateBubble;
console.log(JSON.stringify({
  cards: t.parseCards('1. [礼貌专业] 请 rebase 到 main。 | Please rebase onto main.\n2. [简明直接] 用 a || b 判断 | Use a || b to check\n3. [技术极客] 又挂'),
  plain: t.splitInput('please check the CI logs'),
  mention: t.splitInput('@apex please check the CI logs'),
  command: t.splitInput('/drive now'),
  chinese: t.splitInput('请检查 CI 日志，谢谢'),
  typingMention: t.splitInput('hello there @ap'),
  detect: {
    en: t.detectLanguage('The build is broken again, can you revert your last commit and check the CI logs?'),
    zh: t.detectLanguage('构建又挂了，回滚上次提交，查一下 CI 日志。请先 rebase 到 main。'),
    zhMixed: t.detectLanguage('我已经修改了 frontend/terminal.py 并运行了 pytest，全部通过。`git status` 显示干净。'),
    ja: t.detectLanguage('ビルドがまた壊れました。最後のコミットを元に戻してください。'),
    fr: t.detectLanguage('Le build est encore cassé, est-ce que vous pouvez annuler le dernier commit et vérifier les logs ?'),
    de: t.detectLanguage('Der Build ist wieder kaputt, kannst du den letzten Commit zurücknehmen und die Logs prüfen?'),
    enWithChineseWord: t.detectLanguage('I sent the message 你好 to the worker and it answered correctly, so the fix works.'),
    th: t.detectLanguage('บิลด์พังอีกแล้ว ช่วยย้อน commit ล่าสุดและตรวจสอบ log ของ CI ด้วย'),
    ko: t.detectLanguage('빌드가 또 깨졌습니다. 마지막 커밋을 되돌려 주세요.'),
    vi: t.detectLanguage('Bản build lại bị lỗi, bạn có thể hoàn tác commit cuối và kiểm tra log của CI không?'),
    code: t.detectLanguage('```\nfor x in y: print(x)\n```\nok'),
    path: t.detectLanguage('frontend/static/js/hb-queue.js 12 passed'),
  },
  parts: t.splitForTranslation('第一段。\n\n```py\nprint(1)\n```\n\n第二段。').map(p => [p.code, p.text.trim()]),
}));
'''


def _run():
    out = subprocess.run(['node', '-e', HARNESS, str(JS)], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_script_parses_and_page_loads_it():
    assert subprocess.run(['node', '--check', str(JS)], capture_output=True).returncode == 0
    assert TEMPLATE.read_text(encoding='utf-8').count('/static/js/hb-translate-bubble.js') == 1


def test_uses_the_cpu_worker_unless_the_owner_allows_the_gpu():
    text = JS.read_text(encoding='utf-8')
    assert ':8081/v1/chat/completions' in text
    # the GPU is used only when the owner switched that on (off unless the stored value is '1')
    assert "localStorage.getItem(KEY_GPU) === '1'" in text and 'if (!gpuAllowed()) return cpu;' in text


def test_reply_lines_become_cards_even_when_unfinished():
    cards = _run()['cards']
    assert cards[0] == {'mandarin': '请 rebase 到 main。', 'back': 'Please rebase onto main.'}
    assert cards[1] == {'mandarin': '用 a || b 判断', 'back': 'Use a || b to check'}
    assert cards[2] == {'mandarin': '又挂', 'back': ''}


def test_only_english_messages_are_translated():
    r = _run()
    assert r['plain'] == {'prefix': '', 'body': 'please check the CI logs'}
    assert r['mention'] == {'prefix': '@apex ', 'body': 'please check the CI logs'}
    assert r['command'] is None and r['chinese'] is None and r['typingMention'] is None


def test_reply_language_is_recognised_and_english_is_left_alone():
    d = _run()['detect']
    assert (d['en'], d['zh'], d['zhMixed'], d['ja'], d['fr'], d['de']) == ('en', 'zh', 'zh', 'ja', 'fr', 'de')
    assert (d['th'], d['ko'], d['vi']) == ('th', 'ko', 'vi')
    assert d['enWithChineseWord'] == 'en'
    assert d['code'] is None and d['path'] is None


def test_code_blocks_are_not_sent_for_translation():
    assert _run()['parts'] == [[False, '第一段。'], [True, '```py\nprint(1)\n```'], [False, '第二段。']]


def test_language_choice_is_cleaned_before_it_is_saved():
    import sys
    sys.path[:0] = [str(ROOT / 'frontend'), str(ROOT / 'utils'), str(ROOT)]
    from blueprints.user_languages import clean
    assert clean(['EN', 'fr', 'fr', '<b>', 'ja', 'Thai', 'Swahili', 'x:swahili']) == ['en', 'fr', 'ja', 'th', 'x:Swahili']
    assert clean(['<script>']) is None and clean('en') is None
    assert len(clean(['en', 'zh', 'ja', 'ko', 'fr', 'de', 'es'])) == 5


def test_account_languages_are_saved_per_signed_in_user(monkeypatch, tmp_path):
    import sqlite3
    import sys
    sys.path[:0] = [str(ROOT / 'frontend'), str(ROOT / 'utils'), str(ROOT)]
    from flask import Flask
    from blueprints import user_languages as ul

    def conn():
        return sqlite3.connect(tmp_path / 't.db')
    who = {'user': None}
    monkeypatch.setattr(ul, 'get_connection', conn)
    monkeypatch.setattr(ul, 'get_current_user', lambda: who['user'])
    app = Flask(__name__)
    app.register_blueprint(ul.user_languages_bp)
    client = app.test_client()
    assert client.get('/api/user/languages').status_code == 401
    assert client.put('/api/user/languages', json={'languages': ['fr']}).status_code == 401
    who['user'] = {'username': 'ghost', 'display_name': 'jeandre'}
    assert client.get('/api/user/languages').get_json()['languages'] == ['en']
    assert client.put('/api/user/languages', json={'languages': ['en', 'fr', 'ja', 'Thai']}).get_json()['languages'] == ['en', 'fr', 'ja', 'th']
    assert client.put('/api/user/languages', json={'languages': []}).status_code == 400
    who['user'] = {'username': 'other', 'display_name': 'Other'}
    assert client.get('/api/user/languages').get_json()['languages'] == ['en']
    who['user'] = {'username': 'ghost', 'display_name': 'jeandre'}
    assert client.get('/api/user/languages').get_json()['languages'] == ['en', 'fr', 'ja', 'th']
    assert "('blueprints.user_languages', 'user_languages_bp')" in (ROOT / 'frontend' / 'terminal.py').read_text(encoding='utf-8')


def test_replies_try_the_offline_nmt_service_first_and_fall_back_to_the_worker():
    text = JS.read_text(encoding='utf-8')
    assert 'const NMT_PORT = 8082;' in text
    assert text.index('const fast = await nmtTranslate(') < text.index('const ask = (temperature) => streamChat(')
    assert "if (String(code).startsWith('x:')) return null;" in text


def test_nmt_script_keeps_code_and_splits_sentences():
    import sys
    sys.path[:0] = [str(ROOT / 'scripts')]
    import hb_nmt_translate as nmt
    assert nmt.detect_language('构建又挂了，回滚上次提交，查一下 CI 日志。') == 'zh'
    assert nmt.detect_language('ok') is None
    parts = nmt._segments('第一句。第二句。\n\n```py\nprint(1)\n```\n')
    assert [p for keep, p in parts if keep] == ['第一句。', '第二句。']
    assert ''.join(p for _, p in parts).replace(' ', '') == '第一句。第二句。\n\n```py\nprint(1)\n```\n'
    assert nmt.model_name('zh', 'en') == 'Helsinki-NLP/opus-mt-zh-en' and nmt.model_name('en', 'th') is None


def test_no_example_sentence_is_sent_and_the_read_back_is_independent():
    """15 Nov: the small model copied the worked example ('请于今日完成该 PR 的代码评审') into a message the owner sent to APEX."""
    text = JS.read_text(encoding='utf-8')
    assert 'EXAMPLE_REPLY' not in text and '代码评审' not in text
    assert "nmtTranslate(mandarin, 'en')" in text and 'Reads back as' in text
