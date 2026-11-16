"""Change impact (owner 13 Nov 2026): HB classifies every change by rules (no model) and orders the queue by it.

  cosmetic    CSS, wording, layout, documents only
  behaviour   interface or harness logic (JS, Python) that does not change data or services
  structural  database schema, core harness modules (task manager, peer bridge, tool approval), services, security and logins

Default importance when nobody set one: structural 4, behaviour 3, cosmetic 2 (owner priority and pins always win - core/hb_clipboard.py).
The owner corrects a class with /clip impact S-xxxx <class>; rule result and correction are both kept in hb_change_impact, so the
corrections are training examples for a later small-model suggester. `decided` is False when the rules had nothing to go on."""
import re
import time

CLASSES = ('cosmetic', 'behaviour', 'structural')
IMPORTANCE = {'structural': 4, 'behaviour': 3, 'cosmetic': 2}
_STRUCTURAL_PATH = re.compile(r'(^|/)(hb_task_manager|peer_bridge|peer_coordination|peer_turns|apex_tools|hb_agent_tools|agent_identity|'
                              r'hb_owner_sessions|session_auth|service_accounts|hb_change_sets)\.py$|(^|/)(auth|login)[^/]*\.py$|'
                              r'\.(service|timer|sql)$|^deploy/|^utils/db/')
_COSMETIC_PATH = re.compile(r'\.(css|md|txt|svg|png)$|^docs/')
_STRUCTURAL_TEXT = re.compile(r'\b(schema|database|CREATE TABLE|ALTER TABLE|migration|systemd|service unit|logins?|security|tokens?|passwords?|permissions?)\b', re.I)
_COSMETIC_TEXT = re.compile(r'\b(css|wording|layout|colou?r|label|typo|spacing|icon|cosmetic)\b', re.I)


def classify(paths=(), text=''):
    """(class, decided, why) from the files a change touches and its description. Tests never raise the class."""
    paths = [p for p in paths if p and not p.startswith('tests/')]
    text = str(text or '')
    hit = [p for p in paths if _STRUCTURAL_PATH.search(p)]
    if hit:
        return 'structural', True, 'touches ' + ', '.join(hit[:3])
    if paths and re.search(r'CREATE TABLE|ALTER TABLE', text):
        return 'structural', True, 'changes the database schema'
    if paths and all(_COSMETIC_PATH.search(p) for p in paths):
        return 'cosmetic', True, 'documents / styling only'
    if paths:
        return 'behaviour', True, 'code logic: ' + ', '.join(paths[:3])
    if _STRUCTURAL_TEXT.search(text):
        return 'structural', True, 'its description names ' + _STRUCTURAL_TEXT.search(text).group(0)
    if _COSMETIC_TEXT.search(text):
        return 'cosmetic', True, 'its description names ' + _COSMETIC_TEXT.search(text).group(0)
    return 'behaviour', False, 'no files and no telling words yet'


def ensure_schema(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS hb_change_impact(step_id TEXT PRIMARY KEY, rule_class TEXT, rule_why TEXT, decided INTEGER, "
                 "suggested_class TEXT, owner_class TEXT, corrected_by TEXT, updated_at REAL)")


def _paths(step_id):
    try:
        from core import hb_change_sets
        cs = hb_change_sets.load(step_id)
    except Exception:
        cs = None
    return sorted({e['path'] for e in cs.get('edits', [])} | set(cs.get('new_files', {}))) if cs else []


def for_step(conn, step_id, paths=None):
    """{'impact', 'impact_why', 'decided', 'importance'} for a Studio step: the owner's correction wins over the rules. Records the rule result."""
    ensure_schema(conn)
    row = conn.execute('SELECT title, description FROM project_steps WHERE step_id=?', (step_id,)).fetchone() \
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='project_steps'").fetchone() else None
    cls, decided, why = classify(_paths(step_id) if paths is None else paths, ' '.join(str(x or '') for x in (row or ())))
    old = conn.execute('SELECT rule_class, owner_class, corrected_by FROM hb_change_impact WHERE step_id=?', (step_id,)).fetchone()
    if not old:
        conn.execute('INSERT INTO hb_change_impact(step_id, rule_class, rule_why, decided, updated_at) VALUES (?,?,?,?,?)',
                     (step_id, cls, why, int(decided), time.time()))
    elif old[0] != cls:
        conn.execute('UPDATE hb_change_impact SET rule_class=?, rule_why=?, decided=?, updated_at=? WHERE step_id=?', (cls, why, int(decided), time.time(), step_id))
    if old and old[1]:
        cls, why, decided = old[1], f'set by {old[2]}', True
    return {'impact': cls, 'impact_why': why, 'decided': bool(decided), 'importance': IMPORTANCE[cls]}


def correct(conn, step_id, cls, actor):
    """The owner's correction: kept next to the rule result (a training example)."""
    if cls not in CLASSES:
        return 'Use cosmetic, behaviour or structural.'
    was = for_step(conn, step_id)
    conn.execute('UPDATE hb_change_impact SET owner_class=?, corrected_by=?, updated_at=? WHERE step_id=?', (cls, str(actor)[:80], time.time(), step_id))
    return f"impact: {cls} (the rules said {was['impact']})"


def examples(conn):
    """[(step_id, rule_class, owner_class)] - every correction, for training the suggester."""
    ensure_schema(conn)
    return conn.execute('SELECT step_id, rule_class, owner_class FROM hb_change_impact WHERE owner_class IS NOT NULL ORDER BY updated_at').fetchall()
