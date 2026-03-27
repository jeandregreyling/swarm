"""
duck.py — Seven's Swarm Sanity Checker
Clean version for the useful build phase.
"""

def duck_check(question, answer):
    """Simple YES/NO sanity check."""
    if not answer or len(answer) < 10:
        return "NO"
    if "Murray River" in answer and "longest" in answer.lower():
        return "NO"
    if "I estimate" in answer or "I think" in answer:
        return "NO"
    return "YES"

if __name__ == '__main__':
    print("Duck sanity checker loaded.")