# System summary (written after reading the repo, 2026-10-19)

## Intent
Fridays is a local-first swarm that **does** things rather than reports them (`docs/the-standard.md`). The founding design (Studio doc "What We Are Building" and "Constraints That Must Never Be Broken") sets the rules agents work under:

- **Agents propose, Ghost approves.** No agent action reaches the real system without Ghost's sign-off (constraint 14).
- **Trust ladder.** Agents start in their own sandpit (`sandpits/<name>/`). They earn write access to real paths by reliable behaviour (constraint 22). Nothing leaves a sandpit for the real system without a check (23). Real-system writes are logged to `ghost_circle` (24).
- **Honesty and proof.** Work counts only when a real result shows it.

Since then the build changed: one worker agent (Fred, now Apex) wears the hats, DEOS (Decides, Executes, Operates, Sustains) is the governance framework Watchdog enforces, Seven and DEV/UAT are removed, and PROD (5050) is the only environment.

## The wrapper (what agents are asked to change)
- Flask app `frontend/terminal.py`; main page `frontend/templates/terminal_base.html` (3,324 lines): home page (`#home-page`), tiles, proof trail, the home chat (`#home-chat-body`, `#home-chat-input-area`) and a floating taskbar (`#taskbar`).
- Styles in `frontend/static/css/` (`taskbar.css`, `home-chat.css`, `windows.css`, `views/chat.css`...); behaviour in `frontend/static/js/views/` (`home-chat.js`, `chat.js`, `studio.js`...).

## The known wrapper bug (chat bar covered)
`#taskbar` is `position: fixed; bottom: 14px; left: 14px; z-index: 200` (`taskbar.css`). `.home-chat-section` sets `padding-bottom: 0 !important` and `margin-bottom: 0 !important` (`home-chat.css`), and the chat input is its last element. Nothing reserves room under the chat, so the floating taskbar sits over the input. Seen in a screenshot of the live page at a narrow width; not yet measured at Ghost's screen size. (`#terminal-shortcuts-panel` is the Terminal window's side panel, not this bug.)

## How a chat message becomes work
Browser posts `/api/chat` and polls by conversation; a job takes the single model slot; `agents/<name>/<name>_agent.py` builds the prompt (`utils/worker.py` picks the worker seat); `agents/skills_loop.py` runs `SKILL` lines through `fridays/skills.py` (read-before-patch, backups in `runtime/backups/fs/`, every call logged to `ghost_circle`). Studio steps owned by the worker are handed out by the `fred_work_cycle` task; changes to the real system go through proposals (`frontend/blueprints/proposals.py`, ALM gate in `frontend/services/alm.py`).
