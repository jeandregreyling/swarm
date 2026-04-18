#!/usr/bin/env python3
"""
scripts/setup_node.py — Interactive setup wizard for a new Swarm node (A.6.2)
═══════════════════════════════════════════════════════════════════════════════
Prompts for: node name, API key, DB path, agents to enable.
Creates config, initialises DB, seeds default agents.

Usage:
    python3 scripts/setup_node.py           # interactive mode
    python3 scripts/setup_node.py --yes     # accept all defaults (non-interactive)
"""

import hashlib
import json
import os
import secrets
import sqlite3
import sys

SWARM_ROOT = os.environ.get('SWARM_ROOT',
                            os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, SWARM_ROOT)


# ── Default agent roster ──────────────────────────────────────────────────────

DEFAULT_AGENTS = [
    # (number, name, label, model, temperature, role, tier)
    (0,  'ghost',     'Ghost',     'external',           0.0, 'operator',    'human'),
    (1,  'gemma',     'Gemma3',    'gemma3:latest',      0.3, 'director',    'local'),
    (2,  'llama',     'LlaMA',     'llama3.2:latest',    0.6, 'researcher',  'local'),
    (3,  'mistral',   'Mistral',   'mistral:latest',     0.7, 'analyst',     'local'),
    (4,  'qwen',      'Qwen',      'qwen2.5:latest',     0.7, 'analyst',     'local'),
    (5,  'librarian', 'Vortex',    'qwen:latest',          0.1, 'gatekeeper',  'local'),
    (6,  'duck',      'Duck',      'qwen:latest',          0.1, 'reviewer',    'local'),
    (7,  'sniffles',  'Sniffles',  'deepseek-r1:7b',     0.2, 'inspector',   'local'),
    (8,  'eight',     'Eight',     'gemma4:26b',          0.5, 'specialist',  'local'),
]


# ── Config file template ──────────────────────────────────────────────────────

CONFIG_TEMPLATE = {
    'node_name': '',
    'node_role': 'owner',
    'db_path': '',
    'api_key_hash': '',
    'swarm_root': '',
    'host': '0.0.0.0',
    'port': 5050,
    'agents_enabled': [],
    'created_at': '',
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _prompt(msg, default=''):
    suffix = f' [{default}]' if default else ''
    answer = input(f'{msg}{suffix}: ').strip()
    return answer or default


def _prompt_yes_no(msg, default=True):
    hint = 'Y/n' if default else 'y/N'
    answer = input(f'{msg} [{hint}]: ').strip().lower()
    if not answer:
        return default
    return answer in ('y', 'yes')


def _hash_key(api_key):
    return hashlib.sha256(api_key.encode()).hexdigest()


def _create_db(db_path):
    """Create fresh database with full schema."""
    print(f'  Creating database at {db_path} ...', end=' ')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # Import and apply the full schema
    from utils.db._schema import SCHEMA, _migrate_schema
    conn.executescript(SCHEMA)
    _migrate_schema(conn)
    conn.commit()
    conn.close()
    print('done.')


def _seed_agents(db_path, agents):
    """Insert selected agents into the database."""
    print(f'  Seeding {len(agents)} agents ...', end=' ')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    for number, name, label, model, temp, role, tier in agents:
        conn.execute(
            """INSERT OR IGNORE INTO agents
               (number, name, label, model, temperature, role, tier, enabled)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
            (number, name, label, model, temp, role, tier)
        )
    conn.commit()
    conn.close()
    print('done.')


def _write_config(config_path, config):
    """Write node config JSON."""
    print(f'  Writing config to {config_path} ...', end=' ')
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    print('done.')


# ── Main setup flow ───────────────────────────────────────────────────────────

def setup(auto=False):
    """Run the interactive (or auto) setup wizard."""
    import datetime

    print()
    print('═══════════════════════════════════════════════════════════')
    print("  Seven's Swarm — Node Setup Wizard")
    print('═══════════════════════════════════════════════════════════')
    print()

    # 1. Node name
    default_name = os.environ.get('HOSTNAME', 'swarm-node-1')
    if auto:
        node_name = default_name
    else:
        node_name = _prompt('Node name', default_name)

    # 2. API key
    api_key = secrets.token_urlsafe(32)
    if not auto:
        custom = _prompt('API key (leave empty for auto-generated)', '')
        if custom:
            api_key = custom
    print(f'  API key: {api_key}')
    print('  (save this — it will not be displayed again)')

    # 3. DB path
    default_db = os.path.join(SWARM_ROOT, 'swarm_memory.db')
    if auto:
        db_path = default_db
    else:
        db_path = _prompt('Database path', default_db)

    # 4. Port
    default_port = 5050
    if auto:
        port = default_port
    else:
        port_str = _prompt('HTTP port', str(default_port))
        port = int(port_str) if port_str.isdigit() else default_port

    # 5. Agent selection
    if auto:
        selected_agents = list(DEFAULT_AGENTS)
    else:
        print()
        print('Available agents:')
        for i, (num, name, label, model, _, role, tier) in enumerate(DEFAULT_AGENTS):
            print(f'  [{i+1}] {label:12s} ({name:10s}) — {role:12s} [{tier}]')
        print()
        choice = _prompt('Agents to enable (comma-separated numbers, or "all")', 'all')
        if choice.lower() == 'all':
            selected_agents = list(DEFAULT_AGENTS)
        else:
            indices = [int(x.strip()) - 1 for x in choice.split(',') if x.strip().isdigit()]
            selected_agents = [DEFAULT_AGENTS[i] for i in indices if 0 <= i < len(DEFAULT_AGENTS)]
            if not selected_agents:
                print('  No valid selection. Using all agents.')
                selected_agents = list(DEFAULT_AGENTS)

    # 6. Confirmation
    print()
    print('─── Setup Summary ───')
    print(f'  Node name:  {node_name}')
    print(f'  DB path:    {db_path}')
    print(f'  Port:       {port}')
    print(f'  Agents:     {len(selected_agents)}')
    print()

    if not auto:
        if not _prompt_yes_no('Proceed with setup?'):
            print('Setup cancelled.')
            return False

    # 7. Create DB
    db_exists = os.path.exists(db_path)
    if db_exists:
        if auto:
            print(f'  Database already exists at {db_path} — skipping creation.')
        elif not _prompt_yes_no(f'Database already exists at {db_path}. Reinitialise?', False):
            print('  Keeping existing database.')
        else:
            _create_db(db_path)
            _seed_agents(db_path, selected_agents)
    else:
        _create_db(db_path)
        _seed_agents(db_path, selected_agents)

    # 8. Write config
    config_path = os.path.join(SWARM_ROOT, 'node_config.json')
    config = dict(CONFIG_TEMPLATE)
    config['node_name'] = node_name
    config['db_path'] = db_path
    config['api_key_hash'] = _hash_key(api_key)
    config['swarm_root'] = SWARM_ROOT
    config['port'] = port
    config['agents_enabled'] = [a[1] for a in selected_agents]
    config['created_at'] = datetime.datetime.now().isoformat()
    _write_config(config_path, config)

    # 9. Write env hints
    print()
    print('─── Environment Variables ───')
    print(f'  export SWARM_ROOT="{SWARM_ROOT}"')
    print(f'  export SWARM_DB_PATH="{db_path}"')
    print(f'  export SWARM_NODE_NAME="{node_name}"')
    print(f'  export SWARM_PORT="{port}"')
    print()
    print('Setup complete. Start the swarm with:')
    print(f'  cd {SWARM_ROOT} && python3 frontend/terminal.py')
    print()

    return True


if __name__ == '__main__':
    auto = '--yes' in sys.argv or '--auto' in sys.argv or '-y' in sys.argv
    try:
        setup(auto=auto)
    except KeyboardInterrupt:
        print('\nSetup cancelled.')
        sys.exit(1)
