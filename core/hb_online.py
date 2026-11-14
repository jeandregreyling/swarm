"""Online providers (Codex, Gemini, Claude): one global answer to "may HB use it right now?".

usable = switched Auto or On by the owner AND currently available.
Availability comes from real records, not guesses:
  * HB's own check, at startup and every few minutes (owner 14 Nov): a free metadata call for Gemini, the rate-limit probe for Codex,
    the worker for others - a fresh check beats an old failure;
  * otherwise the newest finished request to that provider (completed = available, failed = unavailable with the actual stage text).
Owner-sent requests are never blocked here: a direct @codex / @gemini is both authorisation and a retest. Automatic requests (APEX,
HB continuations and reviews) are held while a provider is Off or unavailable, so APEX is told before it tries.
"""
import time

PROVIDERS = {'codex': 'codex-instructor', 'gemini': 'gemini-advisor', 'claude': 'claude-code'}
OWNER_SENDERS = {'user', 'ghost', 'owner'}
MODES = ('auto', 'on', 'off')
LABELS = {'claude': 'Claude Code', 'codex': 'Codex', 'gemini': 'Gemini (Flash)'}
PROBE_EVERY_S = 600
PROBES_SQL = ('CREATE TABLE IF NOT EXISTS hb_provider_probes(provider TEXT PRIMARY KEY, last_probe REAL, observed TEXT, accepted REAL, '
              'outcome TEXT, detail TEXT)')


def ensure_schema(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS hb_online_settings(provider TEXT PRIMARY KEY, authorised INTEGER NOT NULL,"
                 " actor TEXT, updated_at REAL)")
    conn.execute("CREATE TABLE IF NOT EXISTS hb_online_modes(provider TEXT PRIMARY KEY, mode TEXT NOT NULL, actor TEXT, updated_at REAL)")


def provider_for(recipient):
    return next((p for p, r in PROVIDERS.items() if r == recipient), None)


def mode(conn, provider):
    """auto / on / off. Never set: 'auto' if JD authorised it the older way (/online x on), else 'off' (online costs tokens)."""
    ensure_schema(conn)
    row = conn.execute('SELECT mode FROM hb_online_modes WHERE provider=?', (provider,)).fetchone()
    if row:
        return row[0]
    old = conn.execute('SELECT authorised FROM hb_online_settings WHERE provider=?', (provider,)).fetchone()
    return 'auto' if old and old[0] else 'off'


def set_mode(conn, provider, value, actor):
    if provider not in PROVIDERS:
        raise ValueError(f'Unknown online agent {provider!r}; known: {", ".join(PROVIDERS)}')
    if value not in MODES:
        raise ValueError('mode must be auto, on or off')
    ensure_schema(conn)
    conn.execute('INSERT INTO hb_online_modes VALUES(?,?,?,?) ON CONFLICT(provider) DO UPDATE SET mode=excluded.mode, '
                 'actor=excluded.actor, updated_at=excluded.updated_at', (provider, value, actor, time.time()))
    return {'model': provider, 'mode': value}


def authorise(conn, provider, allowed, actor):
    """The older /online x on|off: the same as switching it Auto / Off."""
    if provider not in PROVIDERS:
        raise ValueError(f'Unknown online provider {provider!r}; known: {", ".join(PROVIDERS)}')
    ensure_schema(conn)
    conn.execute("INSERT INTO hb_online_settings VALUES(?,?,?,?) ON CONFLICT(provider) DO UPDATE SET "
                 "authorised=excluded.authorised, actor=excluded.actor, updated_at=excluded.updated_at",
                 (provider, int(bool(allowed)), actor, time.time()))
    set_mode(conn, provider, 'auto' if allowed else 'off', actor)
    return status(conn, provider)


def status(conn, provider):
    ensure_schema(conn)
    recipient = PROVIDERS[provider]
    current = mode(conn, provider)
    authorised = current in ('auto', 'on')
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    available, reason, since = True, 'not checked yet', None
    if {'hb_peer_work', 'peer_messages'} <= tables:
        last = conn.execute("SELECT w.state, w.stage, w.updated_at FROM hb_peer_work w JOIN peer_messages p ON p.id=w.request_id "
                            "WHERE p.recipient=? AND w.state IN ('completed','failed') ORDER BY w.updated_at DESC LIMIT 1",
                            (recipient,)).fetchone()
        if last:
            available = last[0] == 'completed'
            reason = 'last request completed' if available else f'last request failed: {str(last[1])[:160]}'
            since = last[2]
    if 'hb_provider_probes' in tables:   # owner 14 Nov: a fresh check beats an old failure (or success)
        row = conn.execute('SELECT last_probe, outcome, detail FROM hb_provider_probes WHERE provider=?', (provider,)).fetchone()
        if row and row[0] and (since is None or row[0] > since) and row[1] in ('verified_available', 'unavailable', 'limited'):
            available = row[1] == 'verified_available'
            reason = (f"checked {time.strftime('%H:%M', time.localtime(row[0]))}: " + str(row[2] or ('available' if available else 'not available')))[:200]
            since = row[0]
    if 'hb_peer_workers' in tables:
        worker = conn.execute('SELECT state FROM hb_peer_workers WHERE principal=?', (recipient,)).fetchone()
        if worker and worker[0] not in ('running', 'starting'):
            available, reason = False, f'worker is {worker[0]}'
    return {'provider': provider, 'authorised': authorised, 'mode': current, 'available': available,
            'usable': authorised and available, 'reason': reason, 'since': since}


def usable(conn, provider):
    return status(conn, provider)['usable']


def may_dispatch(conn, recipient, sender):
    """Gate for automatic online requests. Returns (allowed, reason)."""
    provider = provider_for(recipient)
    if not provider or sender in OWNER_SENDERS:
        return True, ''
    s = status(conn, provider)
    if not s['authorised']:
        return False, f'{provider} is not authorised: it is switched Off in Live status (Auto or On lets HB use it)'
    if not s['available']:
        return False, f'{provider} unavailable: {s["reason"]}'
    from core import hb_budget          # owner 14 Nov: online agents cost real money; HB keeps each one inside its daily budget
    return hb_budget.check(conn, recipient, sender)


# ---- owner 14 Nov: checked at startup and every few minutes, so JD and APEX know before anything is sent -------------
def _check_gemini():
    """A free check: the selected Flash model's metadata (no tokens spent)."""
    import config
    from google import genai
    from google.genai import types
    if not getattr(config, 'GEMINI_API_KEY', None):
        return False, 'no API key configured'
    from scripts.hummingbird_gemini_peer import selected_provider_model
    model = selected_provider_model(getattr(config, 'GEMINI_AGENT_MODEL', 'gemini-2.5-flash'))
    client = genai.Client(api_key=config.GEMINI_API_KEY, http_options=types.HttpOptions(timeout=8000))
    try:
        info = client.models.get(model=model)
        return True, f'{getattr(info, "name", model)} answers'
    finally:
        try:
            client.close()
        except Exception:
            pass


def _check_worker(provider):
    def check():
        from core.peer_coordination import worker_alive
        return (True, 'its worker is running') if worker_alive(PROVIDERS[provider]) else (False, 'its worker is not running')
    return check


def probe(conn, provider, checker=None, now=None):
    """Check one online agent now and save the result. Codex keeps its own rate-limit probe (core/hb_provider_conditions.py)."""
    now = time.time() if now is None else now
    conn.execute(PROBES_SQL)
    checker = checker or {'gemini': _check_gemini}.get(provider) or _check_worker(provider)
    try:
        ok, detail = checker()
    except Exception as exc:
        ok, detail = False, f'check failed: {type(exc).__name__}: {str(exc)[:120]}'
    conn.execute('INSERT INTO hb_provider_probes(provider,last_probe,outcome,detail) VALUES(?,?,?,?) ON CONFLICT(provider) DO UPDATE SET '
                 'last_probe=excluded.last_probe, outcome=excluded.outcome, detail=excluded.detail',
                 (provider, now, 'verified_available' if ok else 'unavailable', str(detail)[:200]))
    return ok


def tick(conn, now=None):
    """Coordinator: check each online agent at startup and every PROBE_EVERY_S (Codex has its own probe)."""
    now = time.time() if now is None else now
    conn.execute(PROBES_SQL)
    checked = []
    for provider in PROVIDERS:
        if provider == 'codex':
            continue
        row = conn.execute('SELECT last_probe FROM hb_provider_probes WHERE provider=?', (provider,)).fetchone()
        if not row or not row[0] or now - row[0] >= PROBE_EVERY_S:
            probe(conn, provider, now=now)
            checked.append(provider)
    return checked


def mention_items(conn):
    """The @ list: online agents that are not Off and were found available."""
    out = []
    for provider in PROVIDERS:
        s = status(conn, provider)
        if s['mode'] != 'off' and s['available']:
            out.append({'key': provider, 'label': LABELS.get(provider, provider), 'tier': 'online',
                        'note': ('online · ' + s['mode'] + ' · ' + s['reason'])[:120]})
    # 14 Nov: the attached VS Code instructor (@git/@github) is listed while its link is live
    # (its token used the peer API in the last 15 minutes). No switch: it is JD's own session.
    try:
        row = conn.execute("SELECT last_used_at FROM service_tokens WHERE principal_id='copilot-instructor' AND revoked_at IS NULL AND last_used_at IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
        if row and time.time() - row[0] < 900:
            out.append({'key': 'github', 'label': 'Git (VS Code Instructor)', 'tier': 'online',
                        'note': 'attached Copilot session · live'})
    except Exception:
        pass
    try:   # owner 14 Nov: every onboarded inbox agent's handles (e.g. @claude, @git) - data in hb_agents
        from core import hb_agents
        keys = {o['key'] for o in out}
        out += [m for m in hb_agents.mention_items(conn) if m['key'] not in keys]
    except Exception:
        pass
    return out


def catalogue(conn):
    """Rows for the Live status models card (same shape as local models): online agents with their switch."""
    rows = []
    for provider in PROVIDERS:
        s = status(conn, provider)
        rows.append({'model': provider, 'role': 'online builder' if provider == 'claude' else 'online advisor', 'where': 'online',
                     'size_gb': 0.0, 'loaded': bool(s['available']), 'installed': True, 'mode': s['mode'], 'note': s['reason']})
    return rows
