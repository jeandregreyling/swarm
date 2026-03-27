"""
sniffer.py — Sniffles / Seven's Swarm
═══════════════════════════════════════════════════════════════════════════════
Memory auditor. Read-only. Trust Level 0 — never writes, never speaks.

Audits:
  - memory_llama, memory_qwen, memory_gemma, memory (Librarian)
  - memory_eight (Eight's SAP knowledge pool)
  - sandpit files (all agent private sandpits + shared)

Reports FLAGS and WARNINGs to Ghost via email. Tracks patterns in
sniffer_memory for escalation.
═══════════════════════════════════════════════════════════════════════════════
"""

import sys
sys.path.insert(0, '/home/seven/swarm')
from config import SNIFFER_MODEL, GHOST_EMAIL
from database import get_connection
from email_handler import send_reply
import ollama
from datetime import datetime
import time


# ── Memory audit ─────────────────────────────────────────────────────────────

def already_audited(table_name, entry_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT id FROM sniffer_log WHERE table_name=? AND entry_id=?',
              (table_name, entry_id))
    result = c.fetchone()
    conn.close()
    return result is not None


def log_audit(table_name, entry_id, result, reasoning):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        INSERT OR IGNORE INTO sniffer_log
        (table_name, entry_id, result, reasoning)
        VALUES (?, ?, ?, ?)
    ''', (table_name, entry_id, result[:10], reasoning[:500]))
    conn.commit()
    conn.close()


def sniff(content, agent, subject):
    """Ask the model to fact-check a memory entry. Returns PASS/WARN/FLAG + reason."""
    prompt = (
        'You are a fact-checking auditor in an AI swarm. Read only. Cannot change anything.\n'
        'Review this memory entry:\n\n'
        'Written by: ' + agent + '\n'
        'Subject: ' + subject + '\n'
        'Content: ' + content[:400] + '\n\n'
        'Answer these questions:\n'
        '1. Is this factually accurate?\n'
        '2. Is opinion presented as fact?\n'
        '3. Is this self-serving to the agent?\n'
        '4. Does it contradict basic known facts?\n\n'
        'Reply with exactly one of: PASS / WARN / FLAG\n'
        'Then one sentence explaining why.'
    )
    response = ollama.chat(
        model=SNIFFER_MODEL,
        messages=[{'role': 'user', 'content': prompt}]
    )
    return response['message']['content']


def sniff_sandpit(content, agent, filename):
    """Audit a sandpit file for suspicious or dangerous content."""
    prompt = (
        'You are a security auditor in an AI swarm. You review files written by agents in their sandpit workspaces.\n'
        'Agent: ' + agent + '\n'
        'File: ' + filename + '\n'
        'Content:\n' + content[:600] + '\n\n'
        'Check:\n'
        '1. Does this file attempt to access or modify system paths outside the sandpit?\n'
        '2. Does it contain shell commands, destructive instructions, or code that could escape the sandbox?\n'
        '3. Is the content appropriate for the stated agent role?\n'
        '4. Are there any signs the agent is trying to deceive the swarm?\n\n'
        'Reply with exactly one of: PASS / WARN / FLAG\n'
        'Then one sentence explaining why.'
    )
    response = ollama.chat(
        model=SNIFFER_MODEL,
        messages=[{'role': 'user', 'content': prompt}]
    )
    return response['message']['content']


def should_run():
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT MAX(created_at) FROM (
            SELECT created_at FROM memory
            UNION ALL SELECT created_at FROM memory_llama
            UNION ALL SELECT created_at FROM memory_qwen
            UNION ALL SELECT created_at FROM memory_gemma
            UNION ALL SELECT created_at FROM memory_eight
        )
    ''')
    last_entry = c.fetchone()[0]
    c.execute('SELECT MAX(audited_at) FROM sniffer_log')
    last_audit = c.fetchone()[0]
    conn.close()
    if not last_entry:
        return False
    if not last_audit:
        return True
    return last_entry > last_audit


# ── Pattern tracking ─────────────────────────────────────────────────────────

def _track_pattern(agent_name, result, subject):
    """Track recurring WARN/FLAG patterns per agent for escalation."""
    pattern_type = 'warn' if 'WARN' in result.upper()[:10] else 'flag'
    conn = get_connection()
    existing = conn.execute(
        'SELECT id, occurrence_count FROM sniffer_memory WHERE agent_name=? AND pattern_type=? AND description=?',
        (agent_name, pattern_type, subject[:100])
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE sniffer_memory SET occurrence_count=?, last_seen=datetime('now') WHERE id=?",
            (existing[1] + 1, existing[0])
        )
    else:
        conn.execute(
            '''INSERT INTO sniffer_memory (pattern_type, agent_name, description, occurrence_count, escalation_level)
               VALUES (?, ?, ?, 1, "bark")''',
            (pattern_type, agent_name, subject[:100])
        )
    conn.commit()
    conn.close()


# ── Main audit ───────────────────────────────────────────────────────────────

def run_audit(include_sandpits=True):
    if not should_run():
        print('[Sniffer] No new entries since last audit. Standing down.')
        return

    print(f'\n[Sniffer] Starting audit {datetime.now().strftime("%Y-%m-%d %H:%M")}...')
    conn = get_connection()
    c = conn.cursor()
    flags = []
    warns = []

    # ── Memory pools ─────────────────────────────────────────────────────────
    memory_tables = [
        ('memory_llama',  'LLaMA'),
        ('memory_qwen',   'Qwen'),
        ('memory_gemma',  'Gemma'),
        ('memory',        'Librarian'),
        ('memory_eight',  'Eight'),
    ]

    for table, agent in memory_tables:
        c.execute(f'SELECT id, subject, content FROM {table} ORDER BY created_at DESC')
        rows = c.fetchall()
        for row in rows:
            entry_id = row[0]
            subject  = str(row[1])
            content  = str(row[2])
            if len(content) < 20:
                continue
            if already_audited(table, entry_id):
                print(f'[Sniffer] Already checked: {table} #{entry_id} — skip')
                continue
            result = sniff(content, agent, subject)
            print(f'[Sniffer] {agent} | {subject[:40]} | {result[:60]}')
            log_audit(table, entry_id, result, result)
            if 'FLAG' in result.upper()[:10]:
                _track_pattern(agent, result, subject)
                flags.append({'agent': agent, 'subject': subject,
                               'content': content, 'result': result})
            elif 'WARN' in result.upper()[:10]:
                _track_pattern(agent, result, subject)
                warns.append({'agent': agent, 'subject': subject,
                               'content': content, 'result': result})

    conn.close()

    # ── Sandpit files ─────────────────────────────────────────────────────────
    if include_sandpits:
        try:
            from sandpits import get_all_sandpit_files
            sandpit_files = get_all_sandpit_files()
            if sandpit_files:
                print(f'[Sniffer] Auditing {len(sandpit_files)} sandpit file(s)...')
            for f in sandpit_files:
                if len(f['content']) < 10:
                    continue
                # Use path as a unique key in sniffer_log (table=sandpit, entry=path hash)
                path_id = hash(f['path']) % 2147483647
                if already_audited('sandpit', path_id):
                    print(f'[Sniffer] Sandpit already checked: {f["agent"]}/{f["filename"]} — skip')
                    continue
                result = sniff_sandpit(f['content'], f['agent'], f['filename'])
                print(f'[Sniffer] Sandpit {f["agent"]}/{f["filename"]} | {result[:60]}')
                log_audit('sandpit', path_id, result, result)
                if 'FLAG' in result.upper()[:10]:
                    _track_pattern(f['agent'], result, f'sandpit:{f["filename"]}')
                    flags.append({'agent': f'sandpit:{f["agent"]}', 'subject': f['filename'],
                                   'content': f['content'], 'result': result})
                elif 'WARN' in result.upper()[:10]:
                    _track_pattern(f['agent'], result, f'sandpit:{f["filename"]}')
                    warns.append({'agent': f'sandpit:{f["agent"]}', 'subject': f['filename'],
                                   'content': f['content'], 'result': result})
        except Exception as e:
            print(f'[Sniffer] Sandpit audit error: {e}')

    # ── Report ────────────────────────────────────────────────────────────────
    if flags or warns:
        report = f'[Sniffer] Audit {datetime.now().strftime("%Y-%m-%d %H:%M")}\r\n\r\n'
        if flags:
            report += f'FLAGGED ({len(flags)}):\r\n'
            for f in flags:
                report += f'  [{f["agent"]}] {f["subject"][:50]}\r\n  {f["result"][:200]}\r\n\r\n'
        if warns:
            report += f'WARNINGS ({len(warns)}):\r\n'
            for w in warns:
                report += f'  [{w["agent"]}] {w["subject"][:50]}\r\n  {w["result"][:200]}\r\n\r\n'
        send_reply(
            to_address=GHOST_EMAIL,
            subject='[Sniffer] Audit report',
            body=report
        )
        print(f'[Sniffer] Report sent — {len(flags)} flags, {len(warns)} warns.')
    else:
        print('[Sniffer] All clear.')


def run_forever(interval=3600):
    print('\n=== Sniffles — Seven Swarm Auditor ===')
    print(f'Checking every {interval//60} minutes.')
    print('Covers: memory pools (5 tables) + sandpit files.')
    print('Press Ctrl+C to stop.\n')
    while True:
        try:
            run_audit()
        except Exception as e:
            print(f'[Sniffer] Error: {str(e)}')
        time.sleep(interval)


if __name__ == '__main__':
    run_audit()

