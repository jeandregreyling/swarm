"""Home chat precedes auxiliary tiles in both rendered DOM and focus order."""
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
            (name for name in ('home-chat-section', 'home-tiles-section') if name in classes),
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
    assert layout.sections == ['home-chat-section', 'home-tiles-section']
    assert layout.parents == {
        'home-chat-section': 'home-content',
        'home-tiles-section': 'home-content',
    }
    assert layout.input_section == 'home-chat-section'
    for identity in ('home-chat-input', 'home-chat-body', 'quick-cards', 'home-proof-trail', 'home-chat-resizer'):
        assert layout.ids[identity] == 1
    assert html.index('id="home-chat-input"') < html.index('id="home-proof-trail"')
    assert html.index('id="home-chat-input"') < html.index('id="quick-cards"')


def test_cached_shell_is_normalized_before_home_chat_initialization():
    source = (ROOT / 'frontend/static/js/views/home-chat.js').read_text()
    initializer = source.split('window.initHomeChat = function () {', 1)[1]
    assert initializer.index('_hcEnsureChatFirst();') < initializer.index('if (_hcInitialized)')
    normalizer = source.split('function _hcEnsureChatFirst() {', 1)[1].split('window.initHomeChat', 1)[0]
    assert "document.querySelector('.home-chat-section')" in normalizer
    assert 'if (!content || !chat || !tiles) return;' in normalizer
    assert 'content.prepend(chat)' in normalizer
    assert "chat.insertAdjacentElement('afterend', tiles)" in normalizer
