# System summary (written after reading the repo, 2026-10-19)

## Local Team Restored (2026-10-21)

This section supersedes the single-worker state described below.

- Fourteen local agents are enabled. Paid agents and online service agents remain disabled.
- Seven's perception, memory, reasoning, continuous learner, HTTP blueprint and standalone runtime are restored from the source before commit d57095557.
- Seven starts with PROD and uses `seven-direct:daily`, a surviving Llama 3.2 GGUF on CPU through Fridays' llama-server manager.
- Apex is a developer peer, not the whole team. It uses `apex-direct:7b`, the surviving Qwen 2.5 Coder GGUF on Vulkan through Fridays, without Ollama in its inference path.
- Gemma directs and owns her Studio steps; LLaMA researches; Qwen analyses; Duck audits; Librarian manages knowledge and Vortex. Their restored model assignments still use the local Ollama service.
- The implicit shared-model override is disabled. Agent wrappers consult the canonical registry, except an explicitly configured worker model or shared-model override.
- Home-chat auto mode no longer forces the default selected pill over explicit mentions. Unaddressed messages default to Seven; manual mode still honors selected agents.
- Successful file edits include backend execution receipts in the visible reply. Reasoning-only direct responses are rejected rather than treated as answers or commands.
- A verified direct Apex write/read artifact is `sandpits/apex/restored_team_acceptance.md`. The runtime emitted both skill calls and the file matched both requested lines.
- Browser chat 2683 also passed through PROD: Apex created `sandpits/apex/local_ui_proof.txt`, read it back and returned the backend execution receipts. Its exact content is `Local model writes through Fridays.` Natural-language task reliability is not implied by this bounded acceptance check.
- Focused restoration checks passed: 59 role/runtime/coordination tests, 108 skill-loop/watchdog tests, and two direct-response regression checks. These are not a full-suite pass claim.
- Before roster changes the live database was backed up to `/mnt/archive/backups/swarm-before-local-team-20261021-101346.sqlite3`. Registry enablement and runtime selector files are local state, not transported by a code-only checkout.

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
