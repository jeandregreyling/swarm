"""Home order (owner 12 Nov): the collapsible Core Workspace on top, then the chat, then auxiliary tiles
(orientation card), in both rendered DOM and focus order."""
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parents[1]


class HomeLayoutParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.sections = []
        self.ids = Counter()
        self.parents = {}
        self.input_section = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = (attrs.get('class') or '').split()
        identity = attrs.get('id') or ''
        if identity:
            self.ids[identity] += 1
        section = next(
            (name for name in ('home-workspace-section', 'home-chat-section', 'home-tiles-section') if name in classes),
            None,
        )
        if section:
            self.sections.append(section)
            self.parents[section] = self.stack[-1][1] if self.stack else None
        if identity == 'home-chat-input':
            self.input_section = next((entry[2] for entry in reversed(self.stack) if entry[2]), None)
        if tag not in {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}:
            self.stack.append((tag, identity, section))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break


def test_rendered_home_chat_precedes_tiles_inside_content():
    env = Environment(
        loader=FileSystemLoader(ROOT / 'frontend/templates'),
        autoescape=select_autoescape(['html']),
    )
    html = env.get_template('terminal_base.html').render(theme_css='', ASSET_VERSION='test')
    layout = HomeLayoutParser()
    layout.feed(html)
    assert layout.sections == ['home-workspace-section', 'home-chat-section', 'home-tiles-section']
    assert layout.parents == {
        'home-workspace-section': 'home-content',
        'home-chat-section': 'home-content',
        'home-tiles-section': 'home-content',
    }
    assert layout.input_section == 'home-chat-section'
    for identity in ('home-chat-input', 'home-chat-body', 'quick-cards', 'home-chat-resizer'):
        assert layout.ids[identity] == 1
    assert 'id="home-proof-trail"' not in html                                         # owner 12 Nov: removed
    assert html.index('id="quick-cards"') < html.index('id="home-chat-input"')        # workspace sits above chat
    assert 'today-strip' not in html and 'id="lab-cards"' not in html                  # Today bar gone; one tile grid


def test_cached_shell_is_normalized_before_home_chat_initialization():
    source = (ROOT / 'frontend/static/js/views/home-chat.js').read_text()
    initializer = source.split('window.initHomeChat = function () {', 1)[1]
    assert initializer.index('_hcEnsureChatFirst();') < initializer.index('if (_hcInitialized)')
    normalizer = source.split('function _hcEnsureChatFirst() {', 1)[1].split('window.initHomeChat', 1)[0]
    assert "document.querySelector('.home-chat-section')" in normalizer
    assert 'if (!content || !chat || !tiles) return;' in normalizer
    assert 'content.prepend(chat)' in normalizer
    assert "chat.insertAdjacentElement('afterend', tiles)" in normalizer


def test_main_chat_scroll_is_contained_and_has_a_jump_to_latest_arrow():
    """Owner 13 Nov: wheel at the end of main chat must not scroll the page; scrolled up shows an arrow to the latest message."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / 'frontend' / 'static'
    css = (root / 'css' / 'home-chat.css').read_text()
    js = (root / 'js' / 'views' / 'home-chat.js').read_text()
    block = css[css.index('#home-chat-messages {'):]
    assert 'overscroll-behavior: contain' in block[:block.index('}')]
    assert '#hc-jump-bottom.show' in css and '_hcInitJumpButton();' in js and "list.scrollTo({ top: list.scrollHeight" in js


ROOT_STATIC = __import__('pathlib').Path(__file__).resolve().parents[1] / 'frontend' / 'static'


def _rule(css, selector):
    block = css[css.index(selector + ' {'):]
    return block[:block.index('}')]


def test_practice_10_task_list_has_a_resize_grip():
    """Owner 13 Nov (practice 10, APEX): the All tasks list can be pulled bigger or smaller."""
    rule = _rule((ROOT_STATIC / 'css' / 'views' / 'chat.css').read_text(), '.hb-task-list')
    assert 'resize:vertical' in rule.replace(' ', '') and 'overflow-y:auto' in rule.replace(' ', '')


def test_practice_11_double_click_arrow_toggles_auto_scroll_on_by_default():
    """Owner 13 Nov (practice 11, APEX): double-click the jump arrow for auto scroll; on by default; remembered; arrow stays while on."""
    js = (ROOT_STATIC / 'js' / 'views' / 'home-chat.js').read_text()
    fn = js[js.index('function _hcInitJumpButton'):js.index('window.initHomeChat')]
    assert "let auto = localStorage.getItem('hc-auto-follow') !== '0';" in fn
    assert "btn.addEventListener('dblclick'" in fn and "btn.classList.toggle('auto', auto);" in fn
    assert "btn.classList.toggle('show', away || auto);" in fn
    assert 'if (auto) list.scrollTop = list.scrollHeight;' in fn and 'subtree: true' in fn
    # 13 Nov: APEX once put the 'show' line where the 'auto' line belongs; 'away' only exists inside update().
    assert fn.count("btn.classList.toggle('show', away || auto);") == 1
    assert fn.index("btn.classList.toggle('show', away || auto);") > fn.index('const update = () => {')
    _run_in_node(fn)


def _run_in_node(fn):
    """Run the function against a tiny fake page: it must not throw (a text check cannot see a line in the wrong place)."""
    import shutil, subprocess
    node = shutil.which('node')
    if not node:
        return
    harness = ("const els={};const mk=()=>({classList:{toggle(){}},addEventListener(){},setAttribute(){},appendChild(){},style:{},"
               "scrollHeight:100,scrollTop:0,clientHeight:50,offsetHeight:40});"
               "global.document={getElementById:id=>id==='hc-jump-bottom'?null:(els[id]||(els[id]=mk())),createElement:()=>mk()};"
               "global.localStorage={getItem:()=>null,setItem(){}};global.window={};global.MutationObserver=class{observe(){}};"
               + fn + "\n_hcInitJumpButton();")
    result = subprocess.run([node, '-e', harness], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr[-400:]


def test_practice_12_auto_scroll_arrow_is_green_with_a_hint():
    """Owner 13 Nov (practice 12, APEX): green while auto is on, and a hint: double-click for auto scroll."""
    css = (ROOT_STATIC / 'css' / 'home-chat.css').read_text()
    assert 'background' in _rule(css, '#hc-jump-bottom.auto')
    assert 'Double-click for auto scroll' in css


def test_practice_13_apex_replies_have_a_readable_look():
    """Owner 13 Nov (practice 13, APEX): APEX bubbles get a lead line, a folded rest and small muted tags."""
    css = (ROOT_STATIC / 'css' / 'home-chat.css').read_text()
    assert 'font-size' in _rule(css, '.hc-apex-tag') and 'border-radius' in _rule(css, '.hc-apex-tag')
    assert 'cursor' in _rule(css, '.hc-apex-rest > summary')
    js = (ROOT_STATIC / 'js' / 'views' / 'home-chat.js').read_text()
    assert 'function _hcApexTidy' in js and 'hc-apex-rest' in js


def test_practice_14_approval_card_has_a_comment_box_sent_with_approve():
    """Owner 13 Nov (practice 14, APEX): a comment box on the Approve card; its text goes with the approval."""
    js = (ROOT_STATIC / 'js' / 'views' / 'hb-needs-you.js').read_text()
    assert '<textarea class="hb-needs-comment"' in js and "i.kind === 'accept'" in js
    assert "if (decision === 'accept') {" in js and "reason = box ? box.value.trim() : '';" in js
    assert "!(cardEl().querySelector('.hb-needs-comment') || {}).value" in js


def test_practice_15_comment_box_is_styled():
    """Owner 13 Nov (practice 15, APEX): the comment box fits the card."""
    css = (ROOT_STATIC / 'css' / 'views' / 'chat.css').read_text()
    rule = _rule(css, '.hb-needs-comment')
    assert 'width' in rule and 'border-radius' in rule and 'resize' in rule


def test_practice_17_main_chat_opens_with_the_latest_20():
    """Owner 13 Nov (practice 17, APEX): open with the latest 20; the background refresh only fetches what is on screen."""
    js = (ROOT_STATIC / 'js' / 'views' / 'home-chat.js').read_text()
    assert 'fetch(`/api/conversations/${convId}/messages?limit=20`)' in js
    assert "messages?limit=${Math.max(20, document.querySelectorAll('#home-chat-messages .hc-bubble[data-message-id]').length)}" in js


def test_practice_18_scrolling_up_loads_older_messages():
    """Owner 13 Nov (practice 18, APEX): at the top, load the 20 before the first one and keep the reading position."""
    js = (ROOT_STATIC / 'js' / 'views' / 'home-chat.js').read_text()
    assert 'function _hcInitOlderLoader()' in js and '    _hcInitOlderLoader();' in js
    assert 'messages?limit=20&before=${Number(first.dataset.messageId)}' in js
    assert 'list.scrollTop += list.scrollHeight - height;' in js and 'list._hcPrependAt = Date.now();' in js
    assert "if (auto && Date.now() - (list._hcPrependAt || 0) > 400) list.scrollTop = list.scrollHeight;" in js
    _run_older_loader_in_node(js)


def _run_older_loader_in_node(js):
    """13 Nov (lesson B78): run the loader against a fake page and a fake server; text checks cannot see wrong logic."""
    import shutil, subprocess
    node = shutil.which('node')
    if not node:
        return
    start = js.index('  // Owner 13 Nov: main chat shows the latest 20 messages; scrolling to the top loads the 20 before them.')
    code = js[start:js.index('  function _hcInitJumpButton() {')]
    harness = (
        "let _hcConvId = 5; const inserted = []; let asked = '';\n"
        "const first = {dataset: {messageId: '26'}};\n"
        "const list = {dataset: {}, scrollTop: 0, scrollHeight: 1000, addEventListener(t, fn) { this.onscroll = fn; },\n"
        "  querySelector() { return first; }, insertBefore(el, ref) { inserted.push([el.id, ref === first]); this.scrollHeight += 50; }};\n"
        "global.document = {getElementById: id => id === 'home-chat-messages' ? list : null};\n"
        "const _hcAppendBubble = msg => ({id: msg.id});\n"
        "global.fetch = url => { asked = url; return Promise.resolve({ok: true, json: () => Promise.resolve({messages: [{id: 24}, {id: 25}], has_more: false})}); };\n"
        + code +
        "\n_hcInitOlderLoader(); list.onscroll();\n"
        "setTimeout(() => {\n"
        "  if (asked !== '/api/conversations/5/messages?limit=20&before=26') throw new Error('asked ' + asked);\n"
        "  if (JSON.stringify(inserted) !== JSON.stringify([[24, true], [25, true]])) throw new Error('inserted ' + JSON.stringify(inserted));\n"
        "  if (list.scrollTop !== 100) throw new Error('reading position not kept: ' + list.scrollTop);\n"
        "  if (_hcNoOlder !== 5) throw new Error('end of history not remembered');\n"
        "  list.onscroll(); if (asked.includes('before=26') && inserted.length !== 2) throw new Error('asked again after the start');\n"
        "  console.log('ok');\n"
        "}, 50);\n")
    result = subprocess.run([node, '-e', harness], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0 and 'ok' in result.stdout, (result.stdout + result.stderr)[-500:]
