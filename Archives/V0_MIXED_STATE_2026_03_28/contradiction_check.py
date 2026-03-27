import sys
sys.path.insert(0, '/home/seven/swarm')
from database import get_connection, get_all_memories
from config import GHOST_EMAIL
from email_handler import send_reply
import ollama
from datetime import datetime

def check_contradiction(new_content, verified_content, subject):
    prompt = (
        'You are a fact checker. Compare these two statements about the same topic.\n\n'
        'Statement A (verified): ' + verified_content + '\n\n'
        'Statement B (new): ' + new_content + '\n\n'
        'Do they contradict each other on any factual point?\n'
        'Reply with CONTRADICTION or NO_CONTRADICTION followed by one sentence explaining why.'
    )
    response = ollama.chat(
        model='gemma3:latest',
        messages=[{'role': 'user', 'content': prompt}]
    )
    return response['message']['content']

def run_contradiction_check():
    print(f'\n[BL-008] Contradiction check {datetime.now().strftime("%Y-%m-%d %H:%M")}...')
    conn = get_connection()
    c = conn.cursor()

    # Get verified Gemma facts
    c.execute("SELECT subject, content FROM memory WHERE agent = 'Gemma' AND importance >= 9")
    verified = c.fetchall()

    if not verified:
        print('[BL-008] No verified facts yet to check against.')
        conn.close()
        return

    # Get recent agent memories from last 24 hours
    contradictions = []
    for table, agent in [('memory_llama','LLaMA'),('memory_qwen','Qwen')]:
        c.execute(
            f"SELECT subject, content FROM {table} WHERE created_at > datetime('now','-1 day')",
        )
        recent = c.fetchall()
        for new in recent:
            for verified_fact in verified:
                if new[0] and verified_fact[0]:
                    # Only check same-ish subjects
                    new_words = set(new[0].lower().split())
                    ver_words = set(verified_fact[0].lower().split())
                    if len(new_words & ver_words) > 1:
                        result = check_contradiction(
                            new[1], verified_fact[1], new[0]
                        )
                        if 'CONTRADICTION' in result.upper() and 'NO_CONTRADICTION' not in result.upper():
                            contradictions.append({
                                'agent': agent,
                                'subject': new[0],
                                'new': new[1],
                                'verified': verified_fact[1],
                                'result': result
                            })
                            print(f'[BL-008] CONTRADICTION found: {agent} | {new[0][:50]}')

    conn.close()

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
            body=report
        )
        print(f'[BL-008] Report sent to moderator.')
    else:
        print('[BL-008] No contradictions found.')

if __name__ == '__main__':
    run_contradiction_check()