"""Prepare Practice 179: the jump/auto-scroll arrow floats and glows; the 'HB now' line says what last ran when idle."""
import subprocess
import sys
sys.path.insert(0, '/home/jd/swarm')
from core import hb_change_sets as cs

STEP = sys.argv[1]
HC = 'frontend/static/js/views/home-chat.js'
CSS = 'frontend/static/css/home-chat.css'
LA = 'core/hb_live_activity.py'
PB = 'frontend/blueprints/peer_bridge.py'
LJ = 'frontend/static/js/hb-live-activity.js'

edits = [
    {'path': HC, 'old': '''    btn.addEventListener('dblclick', () => {
      auto = !auto;
      localStorage.setItem('hc-auto-follow', auto ? '1' : '0');
      btn.classList.toggle('auto', auto);
      if (auto) list.scrollTop = list.scrollHeight;
    });''', 'new': '''    // Practice 179 (owner 20 Nov 2026: "it's a white bar completely at the bottom of the chat type box and it doesn't glow ... it's not
    // really useful unless you know it's there"): the arrow floats over the messages; it glows while you are scrolled up, shows a red
    // dot when something new arrived below, and is amber while auto scroll is locked off. The tooltip says what a double-click does now.
    const label = () => {
      btn.title = auto ? 'Auto scroll ON: the chat follows the latest. Double-click to lock it where you are. Click: jump to the latest.'
                       : 'Auto scroll LOCKED: the chat stays where you are. Double-click to follow the latest again. Click: jump to the latest.';
      btn.classList.toggle('locked', !auto);
    };
    btn.addEventListener('dblclick', () => {
      auto = !auto;
      try { localStorage.setItem('hc-auto-follow', auto ? '1' : '0'); } catch (e) {}
      btn.classList.toggle('auto', auto);
      label();
      if (auto) list.scrollTop = list.scrollHeight;
    });
    label();'''},
    {'path': HC, 'old': '''      btn.classList.toggle('show', true);
      btn.classList.toggle('idle', !(away || auto));
      const input = document.getElementById('home-chat-input-area');
      btn.style.bottom = ((input ? input.offsetHeight : 0) + 14) + 'px';''', 'new': '''      btn.classList.toggle('show', true);
      btn.classList.toggle('idle', !(away || auto));
      btn.classList.toggle('away', away);                 // Practice 179: glow while scrolled up
      if (!away) btn.classList.remove('fresh');
      const input = document.getElementById('home-chat-input-area');
      btn.style.bottom = ((input ? input.offsetHeight : 0) + 28) + 'px';'''},
    {'path': HC, 'old': '''    new MutationObserver(() => {
      if (auto && Date.now() - (list._hcPrependAt || 0) > 400) list.scrollTop = list.scrollHeight;
      update();''', 'new': '''    new MutationObserver(() => {
      if (auto && Date.now() - (list._hcPrependAt || 0) > 400) list.scrollTop = list.scrollHeight;
      else if (!auto && Date.now() - (list._hcPrependAt || 0) > 400
               && list.scrollHeight - list.scrollTop - list.clientHeight > 120) btn.classList.add('fresh');   // Practice 179
      update();'''},
    {'path': CSS, 'old': "#hc-jump-bottom:hover::after { opacity: 1; }\n", 'new': '''#hc-jump-bottom:hover::after { opacity: 1; }
/* Practice 179 (owner 20 Nov 2026): a floating arrow you notice - glows while scrolled up, red dot for new messages below, amber when
   auto scroll is locked off. Never stretched into a bar. */
#hc-jump-bottom { flex: none; width: 40px; height: 40px; min-width: 40px; max-width: 40px; right: 26px; padding: 0; }
#hc-jump-bottom.show.idle { opacity: .6; }
#hc-jump-bottom.auto:not(.away) { box-shadow: 0 0 10px rgba(67,160,71,.75); }
#hc-jump-bottom.locked { background: var(--card); color: #ffb300; border: 2px solid #ffb300; box-shadow: 0 0 10px rgba(255,179,0,.55); opacity: .95; }
#hc-jump-bottom.away { opacity: 1; animation: hcJumpGlow 1.6s ease-in-out infinite; }
#hc-jump-bottom.away:not(.locked) { background: var(--accent, #00e08a); color: #000; border-color: transparent; }
#hc-jump-bottom.fresh::before { content: ''; position: absolute; top: -3px; right: -3px; width: 11px; height: 11px; border-radius: 50%;
  background: #ff5252; box-shadow: 0 0 6px #ff5252; }
#hc-jump-bottom.locked::after { content: 'Auto scroll locked - double-click to follow the latest'; }
@keyframes hcJumpGlow { 0%, 100% { box-shadow: 0 0 5px var(--accent, #00e08a); } 50% { box-shadow: 0 0 20px var(--accent, #00e08a); } }
'''},
    {'path': LA, 'old': "    return {'running': bool(lines), 'lines': lines}\n", 'new': '''    last = None
    if not lines and {'hb_executions', 'hb_tasks'} <= tables:   # Practice 179: when idle, what ran last and when it finished
        row = conn.execute("SELECT e.agent, t.title, e.updated_at FROM hb_executions e JOIN hb_tasks t ON t.task_id=e.task_id "
                           "WHERE e.state!='running' ORDER BY e.updated_at DESC LIMIT 1").fetchone()
        if row:
            last = {'agent': row[0], 'title': str(row[1])[:90], 'at': row[2]}
    return {'running': bool(lines), 'lines': lines, 'last': last}
'''},
    {'path': PB, 'old': "                       live=bool(live.get('running')),lines=live.get('lines') or [])",
     'new': "                       live=bool(live.get('running')),lines=live.get('lines') or [],last=live.get('last'))"},
    {'path': LJ, 'old': "    pill.textContent = 'HB now: ' + (lines.length ? String(lines[0]).replace(/\\s+/g, ' ') : 'idle');",
     'new': '''    var last = data && data.last, idle = 'idle';
    if (!lines.length && last && last.at) {     // Practice 179: "idle since 16:50 - last: APEX, Practice 178 ..."
      var t = new Date(last.at * 1000);
      idle = 'idle since ' + String(t.getHours()).padStart(2, '0') + ':' + String(t.getMinutes()).padStart(2, '0') +
        ' - last: ' + String(last.agent || '').toUpperCase() + ', ' + String(last.title || '');
    }
    pill.textContent = 'HB now: ' + (lines.length ? String(lines[0]).replace(/\\s+/g, ' ') : idle);'''},
]

test = '''"""Practice 179: the jump arrow floats and glows; the HB-now line says what last ran when idle."""
import sqlite3
from pathlib import Path

from core import hb_live_activity

ROOT = Path(__file__).resolve().parents[1]


def test_jump_arrow_states():
    js = (ROOT / 'frontend/static/js/views/home-chat.js').read_text()
    css = (ROOT / 'frontend/static/css/home-chat.css').read_text()
    assert "btn.classList.toggle('away', away)" in js and "btn.classList.add('fresh')" in js and "classList.toggle('locked', !auto)" in js
    assert 'Auto scroll LOCKED' in js and 'Auto scroll ON' in js
    assert '@keyframes hcJumpGlow' in css and '#hc-jump-bottom.fresh::before' in css and 'max-width: 40px' in css


def test_idle_line_names_what_ran_last():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE hb_tasks(task_id TEXT, title TEXT)')
    c.execute('CREATE TABLE hb_executions(execution_id TEXT, task_id TEXT, request_id TEXT, agent TEXT, kind TEXT, identity TEXT, state TEXT, started_at REAL, updated_at REAL)')
    c.execute("INSERT INTO hb_tasks VALUES ('T-1', 'Practice 178 (owner): answers do not talk about drafts')")
    c.execute("INSERT INTO hb_executions VALUES ('E-1','T-1','R-1','apex','turn','x','completed',100,200)")
    s = hb_live_activity.snapshot(c, now=300, background=[])
    assert s['running'] is False and s['last'] == {'agent': 'apex', 'title': 'Practice 178 (owner): answers do not talk about drafts', 'at': 200}
    js = (ROOT / 'frontend/static/js/hb-live-activity.js').read_text()
    assert "'idle since '" in js and "last=live.get('last')" in (ROOT / 'frontend/blueprints/peer_bridge.py').read_text()
'''


def run(cmd):
    out = subprocess.run(cmd, cwd='/home/jd/swarm', capture_output=True, text=True, timeout=900)
    if out.returncode:
        print(out.stdout[-6000:])
    return out


out = cs.prepare(STEP, why=("Owner 20 Nov: the auto-scroll arrow is \"a white bar completely at the bottom of the chat type box and it doesn't glow\", "
                            "and with the fans going \"there's nothing in the main chat letting me know what is happening\". home-chat.js/.css: "
                            "a 40px floating arrow that glows while scrolled up, shows a red dot when new messages arrive below, is amber when "
                            "auto scroll is locked off, with a tooltip for the current double-click action. hb_live_activity + activity route + "
                            "hb-live-activity.js: when idle the HB-now line says 'idle since HH:MM - last: APEX, <task>'."),
                 edits=edits, new_files={'tests/test_practice_179_arrow_and_idle.py': test},
                 test={'tests': ['tests/test_practice_179_arrow_and_idle.py', 'tests/test_practice_177_activity_box.py',
                                 'tests/test_practice_164_activity_route.py', 'tests/test_practice_172_admin_progress.py'], 'keyword': ''}, run=run)
print(out['verified'])
