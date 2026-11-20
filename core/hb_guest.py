"""Guests on HB's channels (Practice 212; JD 21 Nov 2026: "his view [should be] focussed on his questions not everything, there needs to
be an onboarding for users like that so they can see the system and ask questions ... but don't need to see every thread").

A guest is an identity with role 'user' in hb_channel_identities (/channels trust telegram:<id>). A guest:
  * gets a welcome on Telegram the moment JD enrols him: what HB is, who is on the team, what he can do, what JD can see;
  * sees only his own questions and APEX's answers to them - never main chat, JD's threads, Needs-you or the clipboard
    (the owner mirror goes to owners only; his questions carry no main-chat history - core/hb_channels.work_one);
  * has guest commands: /help, /about, /mine (his last questions and answers), /start (Telegram's first message).
Everything else he types is a question for APEX."""
import time

GUEST_COMMANDS = {'help', 'about', 'mine', 'start'}


def welcome(name=''):
    hi = f"Hi {name}! " if name else "Hi! "
    return (hi + "I'm HB (Hummingbird), JD's AI system, running on his own machine. You're set up as a guest.\n\n"
            "Ask me anything in plain words. APEX, our main model, looks it up and answers right here - research questions can take a few "
            "minutes.\n\n"
            "You see only your own questions and the answers to them, not JD's work threads.\n\n"
            + guide() +
            "\n\nJD can see what you ask, so please don't send passwords or anything private.")


def guide():
    return ("What you can do:\n"
            "- just type a question\n"
            "- /about - what HB is and who works in it\n"
            "- /mine - your last questions and answers\n"
            "- /help - this list")


def about():
    return ("HB (Hummingbird) is JD's own AI workspace. It runs locally, on his PC's graphics card and processor, not in the cloud.\n"
            "Who works in it:\n"
            "- HB - the organiser: keeps the task list, hands out work, keeps everyone visible\n"
            "- APEX - the main model (Qwen 3.8 27B on the GPU): does the research and the building; he answers your questions\n"
            "- Fred - the deep thinker (Mistral Small 24B on the CPU): steps in when APEX is stuck\n"
            "- Codex - coaches APEX on how to work and communicate\n"
            "- Claude Code - trains APEX on code and builds HB itself\n"
            "You talk to APEX through HB; JD is the owner.")


def mine(conn, key, limit=5):
    """The guest's last questions, each with the answer HB sent him after it."""
    rows = conn.execute("SELECT id, at, text FROM hb_channel_log WHERE sender=? AND direction='in' ORDER BY id DESC LIMIT ?",
                        (str(key).lower(), limit)).fetchall()
    if not rows:
        return "You haven't asked anything yet - just type a question."
    out = []
    for lid, at, text in reversed(rows):
        ans = conn.execute("SELECT text FROM hb_channel_log WHERE id>? AND direction='out' AND sender='apex' AND channel=("
                           "SELECT channel FROM hb_channel_log WHERE id=?) ORDER BY id LIMIT 1", (lid, lid)).fetchone()
        when = time.strftime('%d %b %H:%M', time.localtime(at or 0))
        out.append(f"{when} - you: {str(text)[:200]}\n   APEX: {str(ans[0])[:300] if ans else '(still working on it)'}")
    return 'Your last questions:\n' + '\n'.join(out)


def command(conn, key, verb):
    """A guest's /command - only the guest list; anything else is refused politely."""
    verb = verb.lower()
    if verb in ('help', 'start'):
        return guide()
    if verb == 'about':
        return about()
    if verb == 'mine':
        return mine(conn, key)
    return 'Enrolled users can ask questions; commands are for the owner. You can use /help, /about or /mine.'
