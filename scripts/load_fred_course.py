"""Load docs/fred_course/*.md into the Knowledge Center as FRED-COURSE-* entries.

Idempotent: an entry with the same key is updated in place, new keys are inserted.
Usage: .venv/bin/python3 scripts/load_fred_course.py
"""
import datetime
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from utils.db._connection import get_connection  # noqa: E402
from utils.db.knowledge import write_knowledge  # noqa: E402

COURSE_DIR = os.path.join(ROOT, 'docs', 'fred_course')


def main():
    loaded = []
    conn = get_connection()
    try:
        for name in sorted(os.listdir(COURSE_DIR)):
            if not name.endswith('.md'):
                continue
            text = open(os.path.join(COURSE_DIR, name), encoding='utf-8').read().strip()
            match = re.match(r'(FRED-COURSE-[A-Z0-9-]+)\s+—', text)
            if not match:
                print(f'skip {name}: first line must start with FRED-COURSE-NN-NAME —')
                continue
            key = match.group(1)
            now = datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%d %H:%M:%S')
            row = conn.execute('SELECT id FROM swarm_knowledge WHERE key=?', (key,)).fetchone()
            if row:
                conn.execute(
                    'UPDATE swarm_knowledge SET content=?, updated_at=?, importance=10 WHERE id=?',
                    (text, now, row[0]),
                )
                loaded.append((key, 'updated', len(text)))
            else:
                write_knowledge(key, text, 'ghost', category='lesson', importance=10, conn=conn)
                loaded.append((key, 'added', len(text)))
        conn.commit()
    finally:
        conn.close()
    for key, action, size in loaded:
        print(f'{action:8} {key} ({size} chars)')


if __name__ == '__main__':
    main()
