"""File audit (owner 16 Nov 2026): "one of the bigger models can actually start going through all the files, there's a lot of files with
things that don't work really well, look weird, the old icons still show before the SVG style is applied".

HB's reviewer model (role 'review': Fred, Mistral Small 24B in system RAM - never the GPU) reads the interface files in the background,
one block of CHUNK numbered lines at a time, only when the CPU is free (the same check homework uses) and no other CPU model is working.
It reports only concrete problems it can point to on a line it was shown: code that cannot work, things that look wrong to JD, coloured
emoji used as icons instead of HB's SVG line icons, hard-coded colours instead of the theme variables, dead or duplicated code. A finding
whose line is not in the block is dropped. When a file is finished and has findings, main chat gets one line and Studio gets one step
("Audit fix: <file>") owned by claude-code - homework then writes its spec and hands it to APEX (Practice 113). A file is audited again
only after it changes. /audit on|off|status controls it.
"""
import glob
import hashlib
import json
import re
import threading
import time
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCOPE = ('frontend/static/js/**/*.js', 'frontend/static/css/*.css', 'frontend/templates/*.html')
CHUNK = 160
MAX_FINDINGS = 4
EVERY_S = 60
KINDS = ['cannot-work', 'looks-wrong', 'old-icon', 'hard-coded-colour', 'dead-code', 'duplicate', 'other']
SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['findings'], 'properties': {'findings': {
    'type': 'array', 'maxItems': MAX_FINDINGS, 'items': {'type': 'object', 'additionalProperties': False,
                                                         'required': ['line', 'kind', 'problem', 'fix'],
                                                         'properties': {'line': {'type': 'integer'}, 'kind': {'type': 'string', 'enum': KINDS},
                                                                        'problem': {'type': 'string', 'maxLength': 240},
                                                                        'fix': {'type': 'string', 'maxLength': 240}}}}}}
_RUNNING = threading.Lock()
_LAST = [0.0]


def ensure_schema(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS hb_file_audit(path TEXT PRIMARY KEY, sha TEXT, next_line INTEGER, findings TEXT, at REAL, step_id TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS hb_file_audit_state(name TEXT PRIMARY KEY, value TEXT)')


def enabled(conn):
    ensure_schema(conn)
    row = conn.execute("SELECT value FROM hb_file_audit_state WHERE name='enabled'").fetchone()
    return row is None or row[0] == 'on'


def files(root=None):
    root = Path(root or ROOT)
    found = set()
    for pattern in SCOPE:
        found.update(str(Path(p).relative_to(root)) for p in glob.glob(str(root / pattern), recursive=True))
    return sorted(found)


def _sha(text):
    return hashlib.sha256(text.encode('utf-8', 'replace')).hexdigest()


def next_block(conn, root=None):
    """(path, lines, start) for the next block to audit, or None when every file is audited at its current version."""
    root = Path(root or ROOT)
    ensure_schema(conn)
    for rel in files(root):
        try:
            text = (root / rel).read_text(errors='replace')
        except OSError:
            continue
        sha = _sha(text)
        row = conn.execute('SELECT sha, next_line FROM hb_file_audit WHERE path=?', (rel,)).fetchone()
        lines = text.splitlines()
        if row is None or row[0] != sha:
            conn.execute('INSERT INTO hb_file_audit(path, sha, next_line, findings, at, step_id) VALUES (?,?,1,?,?,NULL) ON CONFLICT(path) DO UPDATE SET '
                         'sha=excluded.sha, next_line=1, findings=excluded.findings, at=excluded.at, step_id=NULL', (rel, sha, '[]', time.time()))
            start = 1
        else:
            start = row[1]
        if start <= len(lines):
            return rel, lines, start
    return None


def prompt(rel, lines, start):
    from core.hb_master_prompt import for_role
    end = min(len(lines), start + CHUNK - 1)
    shown = '\n'.join(f'{n}: {lines[n - 1]}' for n in range(start, end + 1))
    system = (for_role('fred') + "\nYou are HB's file reviewer. You get a block of one file of HB's interface, with line numbers. Report ONLY "
              "concrete problems you can point to on a line shown: code that cannot work (an undefined name, a wrong selector or id, a "
              "broken reference), something that will look wrong to the owner, a coloured emoji used as an icon in the interface instead of "
              "HB's SVG line icons (HBIcons.svg(name) / data-hb-icon), a hard-coded colour where the theme variables (var(--accent), "
              "var(--text), var(--card)...) belong, dead or duplicated code. No style opinions, no guesses about code you cannot see. "
              f"At most {MAX_FINDINGS} findings, each with its line number, the problem in plain words and the fix. If nothing is clearly "
              "wrong, return an empty list. JSON only.")
    return [{'role': 'system', 'content': system}, {'role': 'user', 'content': f'File: {rel} (lines {start}-{end} of {len(lines)})\n{shown}'}]


def call_model(messages):
    from core import llm
    from core.hb_roles import model_for
    text, _ = llm.chat_via_gateway(model_for('review'), messages, temperature=0.1, absolute_timeout_s=1200, idle_timeout_s=400,
                                   queue_timeout_s=10, keep_alive=600,
                                   options={'num_ctx': 16384, 'num_predict': 900, 'timeout': 1200, 'startup_timeout': 300,
                                            'require_complete_output': True},
                                   response_format={'type': 'json_schema', 'json_schema': {'name': 'hb_file_audit', 'strict': True, 'schema': SCHEMA}})
    return json.loads(text)


# Practice 117 (monitoring 16 Nov 22:27): on components.css the reviewer called 23 lines "hard-coded colour" - among them "filter: blur(0.2px)",
# "opacity: 0.18" and a line that already uses var(--accent). Sent on, APEX would have "fixed" lines that are fine. What HB can check
# itself is now checked: a colour finding needs a colour literal on the line (not a theme variable's own definition), an icon finding
# needs an emoji on the line. At most PER_KIND findings of one kind per file; the rest become one "and N more like it" line.
_COLOUR = re.compile(r'#[0-9a-fA-F]{3,8}\b|\b(?:rgb|hsl)a?\(\s*\d', re.I)   # Practice 118: rgba(var(--accent-rgb), .06) is themed
_EMOJI = re.compile('[\U0001F300-\U0001FAFF☀-➿⬀-⯿]')
PER_KIND = 5


def verified(f):
    code = str(f.get('code') or '')
    if f.get('kind') == 'hard-coded-colour':
        return bool(_COLOUR.search(code)) and not code.lstrip().startswith('--')
    if f.get('kind') == 'old-icon':
        return bool(_EMOJI.search(code))
    return True


def keep(findings):
    """Confirmed findings, at most PER_KIND of each kind, plus one summary line per kind that had more."""
    out, count, extra = [], {}, {}
    for f in findings or []:
        if not verified(f) or not f.get('line'):
            continue
        k = f.get('kind')
        count[k] = count.get(k, 0) + 1
        if count[k] <= PER_KIND:
            out.append(f)
        else:
            extra[k] = extra.get(k, 0) + 1
    for k, n in extra.items():
        out.append({'line': 0, 'kind': k, 'problem': f'and {n} more like it in this file', 'fix': 'the same fix', 'code': ''})
    return out


def clean(found, lines, start):
    """Only findings that point at a non-empty line inside the block, once each."""
    end = min(len(lines), start + CHUNK - 1)
    out, seen = [], set()
    for f in (found or {}).get('findings') or []:
        try:
            n = int(f.get('line'))
        except (TypeError, ValueError):
            continue
        problem = ' '.join(str(f.get('problem') or '').split())
        if not (start <= n <= end) or not lines[n - 1].strip() or len(problem) < 12 or (n, problem) in seen:
            continue
        seen.add((n, problem))
        out.append({'line': n, 'kind': f.get('kind') if f.get('kind') in KINDS else 'other', 'problem': problem[:240],
                    'fix': ' '.join(str(f.get('fix') or '').split())[:240], 'code': lines[n - 1].strip()[:160]})
    return [f for f in out if verified(f)][:MAX_FINDINGS]       # Practice 117


def audit_block(conn, root=None, model=call_model, add_step=None):
    """Audit one block now. Returns (path, findings added) or None when there is nothing left."""
    block = next_block(conn, root)
    if not block:
        return missed(conn, add_step)
    rel, lines, start = block
    # Practice 118 (monitoring 16 Nov 23:02): this connection used to keep its write open while the model thought for minutes, so
    # Studio's add_step (its own connection) hit "database is locked", caught it and returned None - three files were reported in chat
    # as "Studio step None" and never reached homework or APEX; the peer inbox hit the same lock. Small writes are committed at once.
    conn.commit()
    try:
        found = clean(model(prompt(rel, lines, start)), lines, start)
    except Exception:
        found = []                                       # a failed block is skipped, not retried in a loop
    row = conn.execute('SELECT findings FROM hb_file_audit WHERE path=?', (rel,)).fetchone()
    findings = json.loads(row[0] or '[]') + found
    nxt = start + CHUNK
    conn.execute('UPDATE hb_file_audit SET next_line=?, findings=?, at=? WHERE path=?', (nxt, json.dumps(findings), time.time(), rel))
    conn.commit()                                        # Practice 118: free the database before Studio writes
    if nxt > len(lines) and keep(findings):                       # Practice 117: only confirmed findings go to Studio
        _report(conn, rel, keep(findings), add_step)
    return rel, len(found)


def missed(conn, add_step=None):
    """Practice 118: finished files with confirmed findings whose Studio step was never created get it now (one per call)."""
    for rel, findings, next_line in conn.execute('SELECT path, findings, next_line FROM hb_file_audit WHERE step_id IS NULL').fetchall():
        kept = keep(json.loads(findings or '[]'))
        try:
            total = len((ROOT / rel).read_text(errors='replace').splitlines())
        except OSError:
            continue
        if kept and next_line > total:
            return rel, len(kept) if _report(conn, rel, kept, add_step) else 0
    return None


def _report(conn, rel, findings, add_step=None):
    from core import hb_plan_workflow as wf
    from core.hb_chat import owner_chat
    from core.hb_plain import message
    if add_step is None:
        from core.knowledge.projects import add_step
    listing = '\n'.join(f"- line {f['line']} ({f['kind']}): {f['problem']} Fix: {f['fix']}  [{f['code']}]" for f in findings)
    desc = (f'Found by HB\'s file audit (owner 16 Nov 2026: "go through all the files ... things that don\'t work, look weird, the old icons '
            f'still show"). Reviewer: the review role on the CPU. Check each finding against the file before changing anything - the '
            f'reviewer can be wrong.\nFile: {rel}\n{listing}\n')
    step_id = add_step(wf.DEFAULT_PROJECT, f'Audit fix: {rel} ({len(findings)} finding{"s" if len(findings) != 1 else ""})',
                       description=desc, owner='claude-code')
    if not step_id:
        return None                                      # Practice 118: no step, no 'Studio step None' line - missed() retries
    conn.commit()
    conn.execute('UPDATE hb_file_audit SET step_id=? WHERE path=?', (step_id, rel))
    conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (?,'hummingbird','user',?,'response',0)",
                 (owner_chat(conn), message(f'🔎 File audit: {rel} - {len(findings)} thing(s) to fix. Homework writes the spec, then APEX takes it.',
                                            details=[f'Studio step {step_id}', *[f"line {f['line']}: {f['problem'][:120]}" for f in findings[:4]]])))
    return step_id


def tick(conn, every=EVERY_S, now=None):
    """Coordinator: audit one block in its own thread when the audit is on and the CPU is free."""
    now = time.time() if now is None else now
    if now - _LAST[0] < every or not enabled(conn):
        return None
    _LAST[0] = now
    try:
        from core import hb_homework
        if hb_homework._RUNNING.locked() or not hb_homework.can_run(conn)[0]:
            return None
    except Exception:
        return None
    if not _RUNNING.acquire(blocking=False):
        return None

    def work():
        try:
            from utils.db._connection import get_connection
            with closing(get_connection()) as own, own:
                audit_block(own)
        except Exception:
            import logging
            logging.getLogger('hb.file_audit').exception('file audit block failed')
        finally:
            _RUNNING.release()
    threading.Thread(target=work, name='hb-file-audit', daemon=True).start()
    return True


def command(conn, args):
    """/audit status | on | off"""
    ensure_schema(conn)
    word = (args[0].lower() if args else 'status')
    if word in ('on', 'off'):
        conn.execute("INSERT INTO hb_file_audit_state(name, value) VALUES ('enabled', ?) ON CONFLICT(name) DO UPDATE SET value=excluded.value", (word,))
        return f'File audit is {word}.' + (' It reads one block at a time when the CPU is free.' if word == 'on' else '')
    total = len(files())
    done = conn.execute('SELECT COUNT(*) FROM hb_file_audit WHERE next_line > 0 AND findings IS NOT NULL').fetchone()[0]
    steps = conn.execute('SELECT COUNT(*) FROM hb_file_audit WHERE step_id IS NOT NULL').fetchone()[0]
    return (f"File audit is {'on' if enabled(conn) else 'off'}: {done} of {total} files started, {steps} sent to Studio as fixes. "
            '/audit off pauses it.')
