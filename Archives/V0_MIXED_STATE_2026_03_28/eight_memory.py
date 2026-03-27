"""
eight_memory.py — Eight knowledge loader (RL-014)
═══════════════════════════════════════════════════════════════════════════════
Three modes:
  seed    — load a block of SAP knowledge directly (Ghost pastes content)
  teach   — interactive Q&A loop: Ghost teaches, Eight confirms understanding
  correct — find and archive incorrect memories, replace with corrected version

Usage:
  python3 eight_memory.py seed
  python3 eight_memory.py teach
  python3 eight_memory.py correct
  python3 eight_memory.py list [query]
═══════════════════════════════════════════════════════════════════════════════
"""

import sys
sys.path.insert(0, '/home/seven/swarm')

from database import get_connection, save_agent_memory, get_agent_memory
from orchestrator import tag_content
import ollama

MODEL = 'qwen2.5:latest'


# ── Helpers ─────────────────────────────────────────────────────────────────

def _all_eight_memories(query='', limit=100):
    conn = get_connection()
    like = f'%{query}%'
    rows = conn.execute(
        """SELECT id, subject, content, tags, importance, source, created_at
           FROM memory_eight
           WHERE (subject LIKE ? OR content LIKE ? OR tags LIKE ?)
             AND archived=0
           ORDER BY importance DESC, created_at DESC LIMIT ?""",
        (like, like, like, limit)
    ).fetchall()
    conn.close()
    return rows


def _archive_memory(memory_id):
    conn = get_connection()
    conn.execute("UPDATE memory_eight SET archived=1 WHERE id=?", (memory_id,))
    conn.commit()
    conn.close()


def _save_eight_knowledge(subject, content, tags='', importance=8, source='taught'):
    conn = get_connection()
    conn.execute(
        "INSERT INTO memory_eight (agent,subject,content,tags,importance,source) VALUES (?,?,?,?,?,?)",
        ('eight', subject[:200], content, tags, importance, source)
    )
    conn.commit()
    conn.close()
    print(f'[Eight memory] Saved: {subject[:60]}')


def _eight_confirm(subject, content):
    """Ask Eight to confirm it understood the knowledge just seeded."""
    prompt = (
        'You are Eight, an SAP HCM/Payroll specialist. '
        'The Ghost just taught you the following:\n\n'
        'Subject: ' + subject + '\n\n'
        + content + '\n\n'
        'Confirm in 1-2 sentences that you understood this and state the key takeaway '
        'in your own words using correct SAP terminology.'
    )
    response = ollama.chat(
        model=MODEL,
        messages=[{'role': 'user', 'content': prompt}],
        options={'temperature': 0.2}
    )
    return response['message']['content'].strip()


# ── Mode: seed ────────────────────────────────────────────────────────────────

def mode_seed():
    print('\n[Eight Memory — SEED]')
    print('Paste SAP knowledge for Eight to learn.')
    print('Enter subject first, then content (end with a line containing only END)\n')

    subject = input('Subject (e.g. "Wage type T512W processing class 20"): ').strip()
    if not subject:
        print('Aborted — no subject.')
        return

    importance_str = input('Importance 1-10 [default 8]: ').strip()
    importance = int(importance_str) if importance_str.isdigit() else 8

    print('Content (end with END on its own line):')
    lines = []
    while True:
        line = input()
        if line.strip() == 'END':
            break
        lines.append(line)
    content = '\n'.join(lines).strip()

    if not content:
        print('Aborted — no content.')
        return

    tags = tag_content(content)
    print(f'\n[Tags] {tags}')

    _save_eight_knowledge(subject, content, tags=tags, importance=importance, source='seeded')

    print('\n[Eight confirms understanding]:')
    confirmation = _eight_confirm(subject, content)
    print(confirmation)

    save_correct = input('\nSave Eight\'s confirmation as a linked memory? [y/N]: ').strip().lower()
    if save_correct == 'y':
        _save_eight_knowledge(
            subject + ' [Eight confirmation]',
            confirmation,
            tags=tags + ',confirmed',
            importance=importance - 1,
            source='confirmation'
        )
    print('\nDone.')


# ── Mode: teach ───────────────────────────────────────────────────────────────

def mode_teach():
    print('\n[Eight Memory — TEACH]')
    print('Interactive teaching session. Type EXIT to end.\n')

    session_memories = []

    while True:
        print()
        subject = input('Topic (or EXIT): ').strip()
        if subject.upper() == 'EXIT':
            break

        print('Teach Eight (press Enter twice to finish):')
        lines = []
        blank_count = 0
        while blank_count < 2:
            line = input()
            if line == '':
                blank_count += 1
            else:
                blank_count = 0
            lines.append(line)
        content = '\n'.join(lines).rstrip()

        if not content:
            continue

        # Eight responds
        print('\n[Eight] Processing...')
        confirmation = _eight_confirm(subject, content)
        print(f'\n[Eight says]: {confirmation}')

        save = input('\nSave this to Eight\'s memory? [Y/n]: ').strip().lower()
        if save != 'n':
            tags = tag_content(content)
            importance_str = input('Importance 1-10 [8]: ').strip()
            importance = int(importance_str) if importance_str.isdigit() else 8
            _save_eight_knowledge(subject, content, tags=tags, importance=importance, source='taught')
            session_memories.append(subject)
            print(f'[Saved] {subject}')

    print(f'\nSession complete. {len(session_memories)} memories added:')
    for s in session_memories:
        print(f'  - {s}')


# ── Mode: correct ─────────────────────────────────────────────────────────────

def mode_correct():
    print('\n[Eight Memory — CORRECT]')
    query = input('Search Eight\'s memory (blank = show all): ').strip()
    rows = _all_eight_memories(query=query, limit=50)

    if not rows:
        print('No memories found.')
        return

    for i, row in enumerate(rows):
        print(f'\n[{i}] id={row[0]} importance={row[4]} source={row[5]}')
        print(f'    Subject: {row[1]}')
        print(f'    Content: {row[2][:120]}...' if len(row[2]) > 120 else f'    Content: {row[2]}')
        print(f'    Tags: {row[3]}')

    idx_str = input('\nEnter index to correct (or DONE): ').strip()
    if idx_str.upper() == 'DONE' or not idx_str.isdigit():
        return

    idx = int(idx_str)
    if idx >= len(rows):
        print('Invalid index.')
        return

    row = rows[idx]
    print(f'\nCorrecting: {row[1]}')
    print(f'Old content: {row[2]}\n')
    print('New correct content (end with END on its own line):')
    lines = []
    while True:
        line = input()
        if line.strip() == 'END':
            break
        lines.append(line)
    new_content = '\n'.join(lines).strip()

    if not new_content:
        print('Aborted — no new content.')
        return

    _archive_memory(row[0])
    tags = tag_content(new_content)
    _save_eight_knowledge(row[1], new_content, tags=tags, importance=row[4], source='corrected')
    print(f'[Eight memory] Archived old entry #{row[0]}, saved corrected version.')


# ── Mode: list ────────────────────────────────────────────────────────────────

def mode_list(query=''):
    rows = _all_eight_memories(query=query)
    if not rows:
        print('No Eight memories found.')
        return
    print(f'\n[Eight memory — {len(rows)} entries]\n')
    for row in rows:
        print(f'  [{row[4]}★] [{row[5]}] {row[1]}')
        print(f'       {row[2][:100]}...' if len(row[2]) > 100 else f'       {row[2]}')
        print(f'       Tags: {row[3]}  |  {row[6]}')
        print()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else 'list'

    if mode == 'seed':
        mode_seed()
    elif mode == 'teach':
        mode_teach()
    elif mode == 'correct':
        mode_correct()
    elif mode == 'list':
        query = sys.argv[2] if len(sys.argv) > 2 else ''
        mode_list(query)
    else:
        print(f'Unknown mode: {mode}')
        print('Usage: python3 eight_memory.py [seed|teach|correct|list] [query]')
