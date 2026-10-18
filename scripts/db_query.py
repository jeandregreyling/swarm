#!/usr/bin/env python3
"""Read-only query helper for agents: python3 scripts/db_query.py "SELECT ..." [db]

db is one of: swarm (default), mind. Opens the file read-only, accepts one
SELECT statement, prints at most MAX_ROWS rows.
"""
import os
import re
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DBS = {'swarm': 'swarm_memory.db', 'mind': 'mind.db'}
MAX_ROWS = 50


def main(argv):
    if len(argv) < 2:
        print('usage: db_query.py "SELECT ..." [swarm|mind]')
        return 2
    sql = argv[1].strip().rstrip(';').strip()
    name = argv[2] if len(argv) > 2 else 'swarm'
    if name not in DBS:
        print(f'unknown db {name!r}; use swarm or mind')
        return 2
    if not re.match(r'(?is)^select\b', sql) or ';' in sql:
        print('Refused: one SELECT statement only.')
        return 2
    path = os.path.join(ROOT, DBS[name])
    conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    try:
        cur = conn.execute(sql)
        cols = [d[0] for d in cur.description or []]
        print(' | '.join(cols))
        for i, row in enumerate(cur):
            if i >= MAX_ROWS:
                print(f'... truncated at {MAX_ROWS} rows')
                break
            print(' | '.join(str(v) for v in row))
    except sqlite3.Error as exc:
        print(f'SQL error: {exc}')
        return 1
    finally:
        conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
