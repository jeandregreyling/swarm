"""Roles, not names (owner 14 Nov 2026): HB, APEX, Fred, Nanny are roles; each is assigned to whatever model is fit for purpose.

Stage 1 (this file): a role register. model_for(role) returns the model that plays a role:
  1. the model set for it in hb_roles (JD or HB: /roles set <role> <model>),
  2. else the role's default,
  3. and if that model is not on this machine any more, the first of the role's stand-ins that is - so HB keeps working when a
     model is removed or renamed, and says which stand-in it took (resolve() returns the reason).
Nothing else decides here: no loading, no benchmarking. Later stages assign from the benchmark and cover connections, disks and ports."""
import time

DEFAULTS = {'apex': 'gpt-oss:20b', 'deep': 'fred-cpu:24b', 'counsel': 'fred-cpu:24b', 'review': 'fred-cpu:24b', 'homework': 'homework-cpu:7b', 'hb': 'homework-cpu:7b'}
STAND_INS = {'apex': ('qwen2.5:7b-instruct', 'apex-direct:7b', 'Qwen2.5:latest', 'gemma3:latest'), 'deep': ('qwen2.5-32b-instruct', 'mistral-small:24b', 'qwen2.5:14b-instruct', 'gemma4:26b', 'Mistral:latest'),
             'counsel': ('mistral-small:24b', 'qwen2.5:14b-instruct', 'homework-cpu:7b', 'Qwen2.5:latest'), 'review': ('mistral-small:24b', 'qwen2.5:14b-instruct', 'Mistral:latest'),
             'homework': ('qwen2.5:7b-instruct', 'apex-direct:7b', 'llama3.2:latest', 'Llama3.2:latest', 'qwen:latest'),
             'hb': ('Llama3.2:latest', 'llama3.2:latest', 'qwen:latest', 'gemma3:latest')}
WORDS = {'apex': 'APEX, the main worker on the GPU', 'deep': 'Fred, the slow deep thinker in RAM', 'counsel': 'the counsel that scopes vague steps',
         'review': 'the local reviewer', 'homework': 'the small CPU model that writes spec cards', 'hb': 'HB, the fast local coordinator'}


def ensure_schema(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS hb_roles(role TEXT PRIMARY KEY, model TEXT NOT NULL, set_by TEXT, updated_at REAL NOT NULL)')


def _known(model):
    try:
        from core.seven_llm import registry
        if registry.get(model) is not None:
            return True
    except Exception:
        return True          # cannot check: trust the name rather than re-assign blindly
    try:
        from core.hive.node_enrollment import enrolled_role_models
        if str(model or '').strip().lower() in {v.lower() for v in enrolled_role_models().values()}:
            return True
    except Exception:
        pass
    try:
        from core.hive.system_profile import collect_system_profile
        models = (collect_system_profile().get('runtimes') or {}).get('models') or []
        if str(model or '').strip().lower() in {str(m.get('name') or '').lower() for m in models}:
            return True
    except Exception:
        pass
    return False


def _assigned(conn, role):
    try:
        if conn is None:
            from contextlib import closing
            from utils.db._connection import get_connection
            with closing(get_connection()) as own:
                return _assigned(own, role)
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='hb_roles'").fetchone():
            return None
        row = conn.execute('SELECT model FROM hb_roles WHERE role=?', (role,)).fetchone()
        return row[0] if row else None
    except Exception:
        return None


def resolve(role, conn=None, known=_known):
    """(model, why) for a role. Unknown roles raise KeyError."""
    default = DEFAULTS[role]
    assigned = _assigned(conn, role)
    enrolled_model = None
    if not assigned:
        try:
            from core.hive.node_enrollment import enrolled_role_models
            enrolled_model = enrolled_role_models().get(role)
        except Exception:
            enrolled_model = None
    first = assigned or enrolled_model or default
    if known(first):
        reason = ('set in the role register' if assigned else
                  'set by node enrollment' if enrolled_model else
                  'the default for this role')
        return first, reason
    for model in ((default,) if (assigned or enrolled_model) else ()) + STAND_INS.get(role, ()):
        if known(model):
            return model, f'{first} is not on this machine; {model} stands in'
    return first, f'{first} is not on this machine and no stand-in is either'


def model_for(role, conn=None):
    return resolve(role, conn)[0]


def assign(conn, role, model, actor, known=_known):
    if role not in DEFAULTS:
        return 'Roles: ' + ', '.join(DEFAULTS) + '.'
    if not known(model):
        return f'{model} is not a model on this machine.'
    ensure_schema(conn)
    conn.execute('INSERT INTO hb_roles(role, model, set_by, updated_at) VALUES (?,?,?,?) ON CONFLICT(role) DO UPDATE SET model=excluded.model, '
                 'set_by=excluded.set_by, updated_at=excluded.updated_at', (role, model, str(actor)[:80], time.time()))
    return f'{role} ({WORDS[role]}) is now played by {model}. It takes effect at the next HB restart.'


def table(conn):
    return 'Roles:\n' + '\n'.join(f'- {role} ({WORDS[role]}): {model} - {why}' for role in DEFAULTS for model, why in [resolve(role, conn)]) \
        + '\nChange one with /roles set <role> <model>.'
