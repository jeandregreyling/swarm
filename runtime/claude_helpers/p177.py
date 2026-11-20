"""Prepare Practice 177: the live activity box grows with its text and stays readable (it was squeezed to half a line)."""
import subprocess
import sys
sys.path.insert(0, '/home/jd/swarm')
from core import hb_change_sets as cs

STEP = sys.argv[1]
J = 'frontend/static/js/hb-live-activity.js'
edits = [
    {'path': J, 'old': '''    box.style.cssText = 'margin:4px 12px 8px;padding:6px 10px;font:11.5px/1.45 ui-monospace,monospace;white-space:pre-wrap;' +
      'color:var(--text-dim,#888);border-left:2px solid var(--accent,#0f9);max-height:160px;overflow:auto;display:none;';''',
     'new': '''    // Practice 177 (owner 20 Nov 2026: "a very thin line at the bottom of the chat ... the top of the first sentence cut in half"): the chat
    // list is a flex column, so this scrollable box was shrunk to a sliver. It no longer shrinks, grows with its text up to 40% of the
    // screen, and is plain readable text.
    box.style.cssText = 'flex:0 0 auto;min-height:min-content;margin:4px 12px 8px;padding:8px 12px;font:12.5px/1.5 ui-monospace,monospace;' +
      'white-space:pre-wrap;word-break:break-word;color:var(--text,#ddd);background:var(--surface-2,rgba(127,127,127,.08));' +
      'border-left:3px solid var(--accent,#0f9);border-radius:4px;max-height:40vh;overflow:auto;display:none;';'''},
    {'path': J, 'old': "    var bubbles = document.querySelectorAll('.chat-bubble[data-pending-job-id]');",
     'new': "    var bubbles = document.querySelectorAll('.chat-bubble[data-pending-job-id], .hc-bubble[data-pending-job-id]');   // Practice 177: main chat too"},
    {'path': J, 'old': '''      node.textContent = data.lines.join('\\n');
      place(node);
      node.style.display = 'block';''', 'new': '''      var host = node.parentNode;
      var atBottom = !host || host.scrollHeight - host.scrollTop - host.clientHeight < 80;   // Practice 177: follow only if JD is at the bottom
      var text = data.lines.join('\\n');
      if (node.textContent !== text) node.textContent = text;
      place(node);
      node.style.display = 'block';
      host = node.parentNode;
      if (host && atBottom) host.scrollTop = host.scrollHeight;'''},
]

test = '''"""Practice 177: the live activity box grows with its text and stays readable."""
from pathlib import Path

JS = (Path(__file__).resolve().parents[1] / 'frontend/static/js/hb-live-activity.js').read_text()


def test_box_does_not_shrink_and_grows_with_text():
    assert 'flex:0 0 auto' in JS and 'max-height:40vh' in JS and 'max-height:160px' not in JS
    assert 'color:var(--text-dim' not in JS.split('box.style.cssText', 1)[1].split(';\\n', 1)[0]


def test_box_sits_under_the_main_chat_bubble_and_follows_the_bottom():
    assert ".hc-bubble[data-pending-job-id]" in JS
    assert 'atBottom' in JS and 'host.scrollTop = host.scrollHeight' in JS
'''


def run(cmd):
    out = subprocess.run(cmd, cwd='/home/jd/swarm', capture_output=True, text=True, timeout=900)
    if out.returncode:
        print(out.stdout[-6000:])
    return out


out = cs.prepare(STEP, why=("Owner 20 Nov: the live activity under the chat is \"a very thin line ... the top of the first sentence cut in half\" - "
                            "#home-chat-messages is a flex column and the scrollable <pre> shrank to a sliver; it was also dim and capped at "
                            "160px, and in main chat it never found the .hc-bubble so it sat at the end of the list. hb-live-activity.js: "
                            "flex:0 0 auto, grows to 40vh, readable colours, placed under main chat's pending bubble, keeps the bottom in "
                            "view only when JD is already at the bottom."),
                 edits=edits, new_files={'tests/test_practice_177_activity_box.py': test},
                 test={'tests': ['tests/test_practice_177_activity_box.py', 'tests/test_practice_164_activity_route.py'], 'keyword': ''}, run=run)
print(out['verified'])
