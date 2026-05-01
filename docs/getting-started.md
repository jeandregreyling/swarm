# Getting Started — 60-second tour

> Ship a usable Swarm + Seven instance on a fresh machine in under a minute.

## Prereqs

- Python 3.12+
- `git`
- (Optional) [Ollama](https://ollama.com) running locally for the Seven LLM
  layer. Without Ollama, Seven still works in deterministic mode (no
  hallucinations — everything you see is from real DB state).

## 1. Clone and bootstrap

```bash
git clone git@github.com:jeandregreyling/swarm.git
cd swarm
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Seed a demo dataset (optional but recommended)

```bash
python -m ops.seed_demo
```

You should see a one-line dict with row counts across the four pillar
tables.

## 3. Run the bullshit detector

```bash
make excellent
```

This runs the quality scanner *and* the per-batch tests. A green stamp
means the build is up to standard. Red = stop, fix before continuing.

## 4. Start the terminal

```bash
.venv/bin/python frontend/terminal.py
# → http://127.0.0.1:5050
```

Open the URL. You should see four populated wishlist pillar tiles
(Cyber Security, Financial Analytics, Online Trading, Business Centre).
Each tile has a live snapshot, a list of recent items, and a quick-add
form.

## 5. Talk to Seven

Click the **Seven** chat. Try:

- `/help` — list of slash commands.
- `/audit` — Seven runs the bullshit detector and reports the stamp.
- `/standard` — Seven recites the contract he's holding the build to.
- `/pillars` — live snapshot of all four pillars.
- `/learnings` — what Seven has learned from your reactions.
- Just talk: "any cyber issues?", "show me trading P&L", "is this up
  to standard?". Seven answers from real state.

## 6. The feedback loop you actually want

Every turn you give a clear positive or negative signal, Seven captures
a lesson. Negatives bind harder. Over time `/learnings` will fill up
with the things Seven knows you do and do not want.

## What "up to standard" means

See [the-standard.md](the-standard.md). Short version:
**a system that DOES, not a system that REPORTS.**
