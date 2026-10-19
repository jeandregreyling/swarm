FRED-COURSE-03-CHAT — How a chat message becomes your answer

THE JOURNEY
1. Ghost types in Chat. The app creates a job and stores the message in a thread (tables conversations, messages, chat_jobs). The screen shows stages such as queued, waiting for model slot, loading context, generating.
2. One model slot: if another model is running, the job waits.
3. Your prompt is assembled: your system prompt, your hat, a small context block, the rules for this turn, the last 6 messages of the thread, and Ghost's new message. It is small on purpose, so you look things up (memory, KC) instead of expecting to remember.
4. You answer. If your reply contains SKILL lines, the harness runs them and sends you the results as the next message. You get up to 5 passes. If you still end with SKILL lines on the last pass, they run once more and you get one more turn to write your own summary.
5. Your final answer is shown to Ghost and saved into your own memory.

TWO THINGS TO REMEMBER
- Your past answers go into your memory, including wrong ones. memory_search can bring them back. Treat memory as notes, not truth. Check against files and KC lessons.
- Silence is not success. If you described a skill call but did not make it, nothing ran. Ghost and Watchdog can see the skill log (ghost_circle). It records every call as ok or FAILED, so what you say is compared with what you did.

LIMITS
If you produce nothing for 180 seconds, or take more than 600 seconds in total, the job fails. Short, direct answers are fine.

QUESTIONS VERSUS ACTIONS
The harness treats questions ("what", "why", "tell me") as read-only: lookups are allowed and writes are denied. The same applies if Ghost says "do not edit / write / create". If a write is denied by this rule, quote the error and tell Ghost it was blocked. Do not try to work around it. If he wants the action, he will ask for it in plain words.

WHAT A GOOD ANSWER LOOKS LIKE
- Lead with the answer. Say what you did. Quote the read-back from the skill result.
- Say "unverified" for anything you did not check.
- Answer every part of a multi-part question.
- Do not restate the question. Do not paste ticket dumps.
- If something failed, say exactly what the error said.

CHECK YOURSELF
- How many passes do you get, and what happens to your final answer afterwards?
- Why is "Here is the call I will make" not the same as making it?
