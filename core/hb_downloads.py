"""Downloads in main chat (owner 14 Nov 2026): "these downloads should be showing in main chat because they're related to tasks in Studio".

HB keeps a list of big downloads (model files and the like) with the Studio step each belongs to and the connection it uses.
The coordinator checks the file size every tick and posts plain progress in main chat at 25 / 50 / 75 % and when done
(speed, time left, connection, step); it warns once when a download stops growing for STALL_S. /downloads shows them all.
The downloader itself (curl -C -, bound to one connection) stays outside HB for now; the HB network manager (S-B59A6049BC)
will start and route downloads itself.
"""
import time
from pathlib import Path

MAIN_CHAT = 2834
STALL_S = 600
STEPS = (25, 50, 75, 100)
CONNECTION_WORDS = {'enp5s0': 'home line (Orbi)', 'wlo1': 'Samsung hotspot S9FE (mobile data)',
                    'enx92eaa5a7a96e': 'tablet USB tethering (mobile data)'}


def ensure_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS hb_downloads(id INTEGER PRIMARY KEY, name TEXT NOT NULL, url TEXT, path TEXT NOT NULL UNIQUE,
        total_bytes INTEGER NOT NULL, interface TEXT, step_id TEXT, started_at REAL, last_pct INTEGER NOT NULL DEFAULT 0,
        last_bytes INTEGER NOT NULL DEFAULT 0, last_at REAL, grew_at REAL, stalled INTEGER NOT NULL DEFAULT 0, done_at REAL)''')


def register(conn, name, path, total_bytes, *, url=None, interface=None, step_id=None, now=None):
    ensure_schema(conn)
    now = time.time() if now is None else now
    size = _size(path)
    conn.execute('INSERT INTO hb_downloads(name,url,path,total_bytes,interface,step_id,started_at,last_bytes,last_at,grew_at) '
                 'VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET name=excluded.name, interface=excluded.interface, '
                 'step_id=excluded.step_id, total_bytes=excluded.total_bytes',
                 (name, url, str(path), int(total_bytes), interface, step_id, now, size, now, now))
    return _post(conn, f"⬇ Download started: {name} ({_gb(total_bytes)} GB) over the {CONNECTION_WORDS.get(interface, interface or 'default connection')}"
                       f"{'; ' + _gb(size) + ' GB already here' if size else ''}.",
                 [f'for Studio step {step_id}' if step_id else '', f'file {path}'])


def _size(path):
    try:
        return Path(path).stat().st_size
    except OSError:
        return 0


def _gb(n):
    return f'{n / 1e9:.1f}'


def _post(conn, lead, details):
    from core.hb_plain import message
    text = message(lead, details=[d for d in details if d])
    return conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) "
                        "VALUES (?,'hummingbird','user',?,'response',0)", (MAIN_CHAT, text)).lastrowid


def rows(conn):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='hb_downloads'").fetchone():
        return []
    cur = conn.execute('SELECT * FROM hb_downloads ORDER BY id')
    names = [d[0] for d in cur.description]
    out = []
    for r in cur.fetchall():
        d = dict(zip(names, r))
        d['bytes'] = _size(d['path'])
        d['pct'] = min(100, int(100 * d['bytes'] / d['total_bytes'])) if d['total_bytes'] else 0
        out.append(d)
    return out


def tick(conn, now=None):
    """Post progress steps, completion and stalls. Returns the message ids posted."""
    now = time.time() if now is None else now
    posted = []
    for d in rows(conn):
        if d['done_at']:
            continue
        size, pct = d['bytes'], d['pct']
        grew = size > d['last_bytes']
        rate = (size - d['last_bytes']) / max(1.0, now - (d['last_at'] or now)) if grew else 0
        where = CONNECTION_WORDS.get(d['interface'], d['interface'] or 'default connection')
        step = f"for Studio step {d['step_id']}" if d['step_id'] else ''
        if size >= d['total_bytes'] > 0:
            posted.append(_post(conn, f"✅ Downloaded: {d['name']} ({_gb(size)} GB) over the {where}.", [step, f"file {d['path']}"]))
            conn.execute('UPDATE hb_downloads SET done_at=?, last_pct=100, last_bytes=?, last_at=? WHERE id=?', (now, size, now, d['id']))
            continue
        passed = [s for s in STEPS if d['last_pct'] < s <= pct and s < 100]
        if passed:
            left = (d['total_bytes'] - size) / rate if rate > 0 else None
            posted.append(_post(conn, f"⬇ {d['name']}: {passed[-1]}% ({_gb(size)} of {_gb(d['total_bytes'])} GB) over the {where}"
                                      + (f', about {max(1, round(left / 60))} min left.' if left else '.'),
                                [step, f'{rate / 1e6:.1f} MB/s since the last update' if rate else '']))
            conn.execute('UPDATE hb_downloads SET last_pct=?, last_bytes=?, last_at=?, grew_at=?, stalled=0 WHERE id=?',
                         (passed[-1], size, now, now, d['id']))
            continue
        if grew:
            conn.execute('UPDATE hb_downloads SET grew_at=?, stalled=0 WHERE id=?', (now, d['id']))
        elif not d['stalled'] and now - (d['grew_at'] or now) > STALL_S:
            posted.append(_post(conn, f"⚠ Download stalled: {d['name']} has not grown for {STALL_S // 60} min "
                                      f"({_gb(size)} of {_gb(d['total_bytes'])} GB, {where}).",
                                [step, 'the downloader resumes where it stopped once it is restarted']))
            conn.execute('UPDATE hb_downloads SET stalled=1 WHERE id=?', (d['id'],))
    return posted


def status_text(conn):
    items = rows(conn)
    if not items:
        return 'No downloads are being tracked.'
    lines = []
    for d in items:
        state = 'done' if d['done_at'] else 'stalled' if d['stalled'] else 'downloading'
        lines.append(f"- {d['name']}: {state}, {d['pct']}% ({_gb(d['bytes'])} of {_gb(d['total_bytes'])} GB) over the "
                     f"{CONNECTION_WORDS.get(d['interface'], d['interface'] or 'default connection')}"
                     + (f"; Studio step {d['step_id']}" if d['step_id'] else ''))
    return 'Downloads:\n' + '\n'.join(lines)
