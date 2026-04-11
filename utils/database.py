"""
database.py — Seven's Swarm  (backward-compatible shim)
All public symbols now live in utils/db/ domain modules.
This file re-exports everything so existing callers are unchanged.
Run: python3 database.py to initialise.
"""

import logging
from db import *          # noqa: F401,F403  — re-export every public symbol
from db import get_connection, initialise_database   # explicit for __main__
from db._schema import _migrate_schema  # noqa: F401 — private but imported by listener.py


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s')
    print("\n  Initialising Seven's Swarm database...")
    initialise_database()
    conn = get_connection()
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    conn.close()
    print(f"  {len(tables)} tables ready:")
    for t in tables:
        print(f"    ✓ {t[0]}")
    print()
