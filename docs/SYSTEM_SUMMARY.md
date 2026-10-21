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

## Local Write Access Verification (2026-10-21)

- The initial restore did not grant filesystem skills consistently: capability names and executable skill names had been conflated in the schema seeder. These now have separate maps.
- Run `.venv/bin/python3 ops/seed_agent_permissions.py --verify-local-writes` to back up the DB outside the repo, grant file skills only to enabled local agents, and exercise the real dispatcher.
- Working agents have file-write and edit grants. Duck, Librarian and Sniffles have own-sandpit note writes. Seven remains read-only. No shell permissions or online-agent enablement is added.
- Run `66df20c97b2a` passed for all 14 roles: 13 actual create/read/update/read operations, one expected Seven write denial, and cross-sandpit `file_write` denials. All 14 were rechecked after a PROD restart without re-granting permissions.
- Receipts and paths: `runtime/local_write_access_report.json`. Proof files: `write_access_probe_66df20c97b2a.txt` in each writing agent's sandpit. Permission/trust regression coverage: 84 tests passed.
- This proves execution/authorization, not autonomous command selection by every model. Apex's separate browser round-trip proof is chat 2683.

## Live Model and Email Acceptance (2026-10-21)

- `runtime/local_team_end_to_end_report.json` records the latest verified result for every enabled local role, with original run IDs. All 14 models returned fresh nonce responses. Thirteen writing roles created exact own-sandpit notes through Chat; Seven passed the observer/no-write task. This is a bounded live check, not a reliability guarantee for arbitrary tasks.
- Failed runs are preserved as `runtime/local_model_acceptance.*_run.json`. Earlier permission-only probes are not substituted for model-driven results.
- Repairs included missing skills loops in Eight/Twenty and utility chat, keyword forwarding in the frontend compatibility shim, obsolete tool instructions, inadequate default context, placeholder paths and repeated rewrites after verified completion.
- Mistral now uses the installed Mistral Small 24B model, Nineteen uses installed Qwen 2.5 14B, and Thirteen retains Llama 3.2 with a compact developer contract. Other agent roles remain separate.
- Ticket `TICKET-LOCAL-MAIL-20261021-012900` passed Librarian intake, Gemma triage, operator assignment, local Apex file creation/read-back, Duck model review, an approved Apex mail-skill invocation, SMTP acceptance and Librarian closure.
- The sender's Gmail Sent-folder copy was fetched by its exact Message-ID. Its text attachment bytes matched the local SHA256. Recipient inbox delivery was not independently verified.
- The existing mail route now accepts small own-sandpit text attachments. The `email_ticket_reply` skill binds the recipient to the ticket, requires the caller's approved proposal, and suppresses repeat sends once a matching SMTP receipt exists. Only Apex received this explicit mail-skill grant for the acceptance task.
- This was a controlled live pipeline exercise. It does not establish unattended inbox processing by an inactive listener service. Online model providers remain disabled.

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
