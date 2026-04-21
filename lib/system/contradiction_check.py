import sys
import asyncio
sys.path.insert(0, '/home/seven/swarm')
from database import get_connection
from config import GHOST_EMAIL
from email_handler import send_reply
from datetime import datetime


async def _check_async(new_content, verified_content):
    """Single contradiction check via AsyncClient with 30s timeout."""
    import ollama
    client = ollama.AsyncClient()
    prompt = (
        'You are a fact checker. Compare these two statements about the same topic.\n\n'
        'Statement A (verified): ' + verified_content + '\n\n'
        'Statement B (new): ' + new_content + '\n\n'
        'Do they contradict each other on any factual point?\n'
        'Reply with CONTRADICTION or NO_CONTRADICTION followed by one sentence explaining why.'
    )
    try:
        response = await asyncio.wait_for(
            client.chat(model='gemma3:latest', messages=[{'role': 'user', 'content': prompt}]),
            timeout=30.0,
        )
        return response['message']['content']
    except asyncio.TimeoutError:
        return 'NO_CONTRADICTION (timeout — skipped)'
    except Exception as e:
        return f'NO_CONTRADICTION (error: {e})'


def check_contradiction(new_content, verified_content, subject):
    """Synchronous wrapper — runs a single async check."""
    return asyncio.run(_check_async(new_content, verified_content))


def run_contradiction_check():
    print(f'\n[BL-008] Contradiction check {datetime.now().strftime("%Y-%m-%d %H:%M")}...')
    conn = get_connection()
    c = conn.cursor()

    c.execute("SELECT subject, content FROM memory WHERE agent = 'Gemma' AND importance >= 9")
    verified = c.fetchall()

    if not verified:
        print('[BL-008] No verified facts yet to check against.')
        conn.close()
        return

    # Collect all (agent, subject, new_content, verified_content) pairs
    pairs = []
    for table, agent in [('memory_llama', 'LLaMA'), ('memory_qwen', 'Qwen')]:
        c.execute(
            f"SELECT subject, content FROM {table} WHERE created_at > datetime('now','-1 day')",
        )
        recent = c.fetchall()
        for new in recent:
            for verified_fact in verified:
                if new[0] and verified_fact[0]:
                    new_words = set(new[0].lower().split())
                    ver_words = set(verified_fact[0].lower().split())
                    if len(new_words & ver_words) > 1:
                        pairs.append((agent, new[0], new[1], verified_fact[1]))
    conn.close()

    if not pairs:
        print('[BL-008] No overlapping subjects to check.')
        return

    print(f'[BL-008] Running {len(pairs)} checks in parallel...')

    async def _run_all():
        tasks = [_check_async(new_c, ver_c) for _, _, new_c, ver_c in pairs]
        return await asyncio.gather(*tasks, return_exceptions=True)

    results = asyncio.run(_run_all())

    contradictions = []
    for (agent, subject, new_c, ver_c), result in zip(pairs, results):
        if isinstance(result, Exception):
            result = f'NO_CONTRADICTION (exception: {result})'
        result = str(result)
        if 'CONTRADICTION' in result.upper() and 'NO_CONTRADICTION' not in result.upper():
            contradictions.append({
                'agent': agent, 'subject': subject,
                'new': new_c, 'verified': ver_c, 'result': result,
            })
            print(f'[BL-008] CONTRADICTION found: {agent} | {subject[:50]}')

    if contradictions:
        report = f'[Contradiction Check] {len(contradictions)} contradiction(s) found.\r\n\r\n'
        for con in contradictions:
            report += f'Agent: {con["agent"]}\r\n'
            report += f'Subject: {con["subject"]}\r\n'
            report += f'New claim: {con["new"][:200]}\r\n'
            report += f'Conflicts with: {con["verified"][:200]}\r\n'
            report += f'Assessment: {con["result"]}\r\n\r\n'
        send_reply(
            to_address=GHOST_EMAIL,
            subject='[Swarm] Contradiction detected',
            body=report,
        )
        print(f'[BL-008] Report sent to moderator.')
    else:
        print('[BL-008] No contradictions found.')


if __name__ == '__main__':
    run_contradiction_check()
