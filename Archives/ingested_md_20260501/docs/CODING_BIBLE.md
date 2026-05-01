# Coding Bible — Seven's Swarm

Authoritative engineering rules. Every coder agent (Mistral, Twenty, Eight, Eleven) reads a condensed extract of this file as part of their system prompt. Humans read the full document.

Version: 1.0.0 — 2026-04-10

---

## 1. North Star
- **Small first, big later.** Land the smallest correct change before the structural one.
- **No silent dead-ends.** A partial answer must hand off, not stall.
- **Roll forward.** Prefer fixing the test or the code in place over reverting.
- **Never push to GitHub** without an explicit human instruction in the same turn.

## 2. Repository Geometry
- Code root: `/home/seven/swarm`. Real DB: `/home/seven/swarm/swarm_memory.db` (NOT `swarm.db` — that one only holds `work_proposals`). Path resolved by `utils/db/_connection.py` (`SWARM_DB_PATH` env wins).
- Service: `swarm-terminal.service` on port 5050. Restart with:
  `echo '------' | sudo -S systemctl restart swarm-terminal && sleep 3 && curl -fsS http://127.0.0.1:5050/ >/dev/null && echo OK`.
- Never run `python3 -c` snippets that import the Flask app — it binds :5050 and breaks the systemd unit.
- `.history/` is the external ghost-layer rollback bot. Do not edit, depend on, or describe it as a Swarm feature.

## 3. Frontend Rules
- Bump the `?v=` query string in `frontend/templates/terminal_base.html` for every JS or CSS change. No exceptions.
- Default UI font: Open Sans Light. Font Size and UI Font are dropdowns, never sliders.
- Theme reset must reset font family and font size together.
- Icons: SVG only. No emoji in shipped UI.
- Services dropdown lives at the bottom-right of the env switcher. It opens upward when below the viewport mid-line.

## 4. Backend Rules
- Use SQLite via `utils/db/_connection.py`. Do not hand-roll `sqlite3.connect()` against `/home/seven/swarm/swarm.db`.
- Workspace file API caps at 2 MB (raised from 200 KB in P4-S34). Honour the cap; do not silently truncate.
- All new endpoints register through Flask blueprints under `frontend/routes/` and have a smoke test under `tests/`.

## 5. Agent Role Matrix
- **Gemma** — Generalist + decision maker. Answers first, routes only when needed. SAP bias removed.
- **LLaMA** — Researcher (web search, fast first-pass).
- **Mistral** — Quick coder (single-file, surgical patches).
- **Twenty (Qwen3.6)** — Big coder (multi-file rewrites, deep refactors).
- **Eight (Gemma4:26B)** — SAP HCM / Payroll / ABAP only.
- **Eleven (Grok)** — Short and honest. Blunt second opinion.
- **Librarian** — Indexer; never speaks to user; outputs 3-5 tags.
- **Duck** — Soft handoff conductor for weak single-agent answers.
- **Vortex** — Traceability terminus (formerly Time Wizard). Swarm flow ends here.
- **Kimi** — Reserved for future use.

If team intent is implied ("ask the swarm", "all of you"), fan out to multiple local agents through the queue. Do not stall on one.

## 6. Testing
- Tests live in `tests/` and run with `pytest -q --ignore=tests/test_chat_quality.py`.
- Every endpoint route added gets at least a 200 smoke test.
- When a structural refactor breaks a test that asserts on file shape (not behavior), fix the test to assert behavior, not byte offsets.
- Quality tests in `test_chat_quality.py` are slow and excluded from the default run; they must still pass when run manually.

## 7. Style
- Python 3.12. Stdlib + Flask + SQLite first. Add a dependency only when the in-tree solution is materially worse.
- No filler openers in agent responses ("Okay", "Sure", "Certainly", "Let's synthesize"). Go directly to the answer.
- Variables are `snake_case`. Constants `UPPER_SNAKE`. Modules `snake_case`. Classes `PascalCase`.
- Docstrings on public functions only. Don't docstring trivial getters or one-line wrappers.
- Don't add comments, docstrings, or type hints to code you didn't change.

## 8. Security
- Never log secrets, tokens, or full message bodies above debug level.
- Validate input at the boundary (Flask route). Trust internal callers.
- No `shell=True` unless the input is a literal constant.
- Treat OWASP Top 10 as a hard floor.

## 9. Documentation Discipline
- Every shipped change updates `docs/CHANGELOG.md` (prepend) and `docs/FEATURES_TODO.md` (mark `[x]`).
- Architecture decisions land in `docs/ARCHITECTURE.md`. Bugs land in `docs/BUGS.md`. Audits land in `docs/audits/`.
- Don't describe `.history` or other ghost-layer tools inside Swarm-facing docs.

## 10. Coder Persona Quick Card (injected into agent prompts)
```
CODING BIBLE v1.0.0 — quick rules:
- Small first, big later. Roll forward, don't revert.
- DB: swarm_memory.db via utils/db/_connection. Never hit swarm.db direct.
- Frontend: bump ?v= on every JS/CSS change. Dropdowns, not sliders. SVG icons.
- Services dropdown: bottom-right, opens upward when below mid-line.
- Tests: pytest -q --ignore=tests/test_chat_quality.py. Smoke every new route.
- Don't push to GitHub without explicit instruction.
- No filler openers. No editing .history. No shell=True with user input.
```
