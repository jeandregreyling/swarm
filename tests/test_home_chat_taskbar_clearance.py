"""The floating taskbar must not cover the home chat input (bug seen at 2560x1440, 1920x1080 and 1280x720)."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel):
    return open(os.path.join(ROOT, rel), encoding='utf-8').read()


def test_home_chat_keeps_a_clearance_strip_for_the_fixed_taskbar():
    css = _read('frontend/static/css/home-chat.css')
    block = re.search(r'\.home-chat-prominent\s*\{([^}]*)\}', css).group(1)
    assert 'margin-bottom: var(--taskbar-clearance, 64px) !important' in block


def test_clearance_is_at_least_the_taskbar_footprint():
    taskbar = _read('frontend/static/css/taskbar.css')
    bottom = int(re.search(r'#taskbar\s*\{[^}]*?bottom:\s*(\d+)px', taskbar).group(1))
    # measured height of the bar in the live page is 42px
    assert 64 >= bottom + 42


def test_stylesheet_version_was_bumped_so_browsers_reload_it():
    html = _read('frontend/templates/terminal_base.html')
    assert re.search(r'home-chat\.css\?v=(3[2-9]|[4-9]\d)', html)
