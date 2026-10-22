# System summary (written after reading the repo, 2026-10-19)

## Agent-led maintenance training (2026-10-22)

- Project `P-64B2C1CBF6` records the improvement backlog, role assignments,
  dependencies, acceptance cases and actual local-model teaching results.
  Gemma coordinates, Apex implements after readiness, Fred maintains/recovery,
  Qwen verifies, LLaMA documents and Librarian curates. Seven remains read-only;
  Ghost retains human approval authority.
- Initial ordinary-Chat exercises exposed malformed commands, unsupported
  claims and a Qwen transport timeout. Fred did execute `free -h` and correctly
  explain the service-operation approval boundary. Permissions alone do not
  establish maintenance competence. No source edit or proposal claimed by the
  failed Apex exercise actually succeeded.
- Ghost approved repairing the teaching safeguards before further delegation.
  `run_skill_loop(..., allowed_skill_names=..., strict_skill_allowlist=True)`
  now requires an explicit allowlist, disables implicit lookup exemptions and
  synthesized commands, enforces the tool-round budget, includes actual
  receipts and flags missing/failed execution. This is opt-in; ordinary callers
  retain existing behaviour. Explicit combined "do not approve or edit" and
  read-only-exercise wording also activate the existing read-only turn policy.
- `SKILL maintenance_check skills` runs only the fixed skill/training regression
  files; `SKILL maintenance_check interests` runs only the fixed interest
  provenance/isolation and executable frontend identity files. No arbitrary paths, shell strings or pytest flags
  are accepted. Runs use a temporary default Swarm database, a 120-second
  timeout, bounded output and the real exit code. They are focused checks,
  not a full-suite certification or a general-purpose execution sandbox.
  The runner prefers the existing project virtualenv without resolving its
  Python symlink, falling back to the calling interpreter only if that
  environment is absent. The UI regression requires Node, or the existing
  VS Code bundled Node at `/usr/share/code/code`; absence fails rather than
  silently skipping the check.
- Run a real local lesson with
  `.venv/bin/python3 scripts/maintenance_training.py --agent apex --exercise lesson --project P-64B2C1CBF6`.
  Other exercises are `source`, `safeguards`, `tests` and `recall`. Each invocation
  starts with fresh model context and uses the canonical enabled-local model
  assignment. The script does not change models, grants or services.
  Successful exercises require backend receipts; lesson/recall also check actual
  own-sandpit bytes. Only verified exercises enter authorized private memory;
  successes and failures both enter the project blackboard.
- Apex persisted an own-sandpit lesson, retrieved it in a fresh invocation and
  ran the fixed regression suite. A later source teach-back was incorrect and
  was rejected rather than retained as verified. Qwen passed the constrained
  source check but failed note-writing exercises; Gemma failed note readback.
  These are bounded teaching observations, not team-wide readiness.
- GPU residency unification, complete
  KC retrieval/learning, peer-handoff hardening and reliable team-wide teach-back
  remain project work. Ghost separately approved a terminal-only restart;
  `swarm-terminal.service` was restarted through systemd and project HTTP
  readiness returned 200. Ollama was not restarted and Fred remained CPU-only.
  Ordinary Chat 2767 then executed Qwen's `maintenance_check skills` and
  reported its actual zero exit code. No automatic background rollout was added.

### Human-interest profile increment (2026-10-22)

- Ghost approved Qwen proposal `INTERNAL-QWEN-2398` for the bounded identity
  repair. Qwen and Apex applied the application patches through real scoped
  skill calls with receipts. The coach supplied executable regression coverage
  and corrections; this is supervised work, not independent agent readiness.
- Home's initial GET, seed POST and refresh GET and Knowledge Center's GET and
  seed POST now explicitly use the shared `fridayInterestUsername()` helper.
  It uses authenticated in-memory state, otherwise awaits `/api/auth/me` to
  avoid the bootstrap race. Successful no-user or blank identity uses `ghost`.
  Proxy/acting identity in localStorage is not used. Auth HTTP/network/JSON
  errors stop interest requests instead of selecting another user's profile;
  Home reports failures using the existing error toast.
- The backend legacy GET default remains `seven`; explicit username queries
  still select saved interests. This fixes human saved-interest selection,
  not all-user signal mining, privacy isolation of every interest source,
  automatic learning, or knowledge sharing.
- `tests/test_interest_identity_frontend.py` executes the actual three JS files
  with mocked fetch and DOM, covering identity before/after bootstrap, delayed
  auth, anonymous/blank fallback, encoded usernames, both views' reads/writes,
  Home refresh, and failures without production writes. The backend provenance
  and isolation suites remain part of `maintenance_check interests`.
- Qwen retained a procedure in its own `interest_profile_maintenance.txt` note
  and retrieved it in a fresh context, correctly naming the regression command
  and Ghost's approval boundary. Initial truncated-note and command-selection
  failures remain project evidence. A successful maintenance receipt proves
  execution and exit code, not correctness of every sentence in model prose.
  Qwen also added the executable failed-refresh regression under coaching.
  Fred wrote and retrieved its own handover and successfully practised the
  fixed interest check after correction. Its subsequent fresh recall still
  substituted an unauthorized tool, which was denied. Fred is not cleared for
  unattended maintenance.
- Browser reload verified `ghost` selection, explicit-user requests in Home
  and Knowledge Center, and eight rendered Home interest cards. Static JS is
  live without a restart. Ghost separately approved a terminal-only restart
  to activate the Python skill changes. Systemd PID changed from 23426 to
  59505; HTTP readiness returned 200 after startup. Ordinary Qwen Chat 2768
  then ran the expanded interest suite with exit code zero, confirmed by
  backend audit receipt 6675. Ollama and model residency were not changed.
  The focused training, skill, provenance, isolation and UI tests passed:
  97 tests, not a full-suite or team-readiness certification.

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

## Memory and Local Ticket Verification (2026-10-21)

- Private memory reads now filter by agent identity, including agents sharing the legacy memory table. Historical rows were not wiped or reassigned.
- Normal local prose can be retained as unverified chat memory. Errors and explicitly memory-disabled turns are excluded. Qwen saved a fresh diagnostic fact through real Chat and recalled it in a new conversation after a PROD restart; the failed first recall is preserved separately.
- Qwen and LLaMA use compact current-turn prompts and bounded private recall. Utility agents retain separate local models and restricted own-note tools. Repository context has a bounded, sanitized fallback when ripgrep is missing.
- `POST /api/tickets` creates a real local ticket and queue entry. `POST /api/tickets/<number>/process` claims that entry, runs local Gemma triage, local analyst findings, and Duck review. Every stage and the backend observations are recorded as ticket notes; the report is visible in ticket detail. This report-only path cannot execute tools or send email, and does not close the ticket or approve remediation.
- Live ticket `LOCAL-1DF52DA9D528` completed Gemma -> Nineteen -> Duck with a saved report. The first malformed review was rejected and retained. Queue completion means the analysis finished, not that the underlying system backlog was resolved.
- `runtime/local_team_verified_latest.json` consolidates the latest completed real-model checks for all 14 local roles: 13 exact own-sandpit writes and Seven's observer/no-write check. This combines full and targeted reruns, not one flawless uninterrupted run. Failed and interrupted reports remain available.
- Acceptance now requires both actual file bytes and a completed Chat request. Explicit-note readback mismatches request correction from the model and cannot be hidden by an unsupported success claim.
- Focused verification: 220 tests passed. This is not a full-suite certification or a guarantee that arbitrary natural-language requests always succeed.
- Apex is agent 21 and remains enabled. Fred remains enabled; his false sole-agent identity was replaced with a maintenance/admin fallback description. No memories or grants were removed.
- Still outstanding: scheduler/listener recovery, stale Studio owners and proof links, remaining identity cards, KC historical-version cleanup, and older test/memory debris. Legacy background jobs have not been released or external model providers enabled.

## Fred CPU/RAM Backup (2026-10-21)

- Fred uses `fred-cpu:24b`, a separate Ollama alias over the installed Mistral Small 24B weights. The alias defaults to `num_gpu=0`, six CPU threads and an 8192-token context; no model download or duplicate weight copy was required.
- Both interactive Fred Chat and orchestrated ticket calls enforce zero GPU layers. Apex's direct model and Mistral's separate assignment are unchanged.
- Only the explicitly named CPU alias with zero-GPU options may request indefinite keep-alive through the gateway. Idle orphan reconciliation preserves this intentional RAM resident; other models retain finite TTLs.
- Ollama placement was measured at about 15.1 GiB loaded with `size_vram=0`. Residency lasts while Ollama remains running; restarting Ollama itself clears RAM and the model loads again when requested.
- A real CPU request exposed hidden 120-second chat and 60-second fallback transport caps. The CPU backup now uses the caller's finite idle/absolute budget, and Fred compacts unrelated wrapper history before inference. This does not add automatic failover or silently replay failed mutations.
- The pre-change registry backup is outside the repository under `~/swarm-backups/before-fred-cpu-*.db`. The local alias and registry update are machine state, not transported by a source-only checkout.

## Ticketed 20B Recheck (2026-10-21)

- Ticket `LOCAL-D4F63C10AA67` now contains actual Seven Runtime diagnostics, not only historical summaries. Both `gpt-oss:20b` and `apex-direct:20b` passed strict exact-marker roll-calls and clean unload checks.
- A real direct-20B skill-loop probe failed with a 384-token completion budget: no final answer was accepted and no write was executed. The failed receipt is retained.
- A bounded retry with `num_predict=2048` and a 120-second timeout completed model-generated `file_write` and `file_read` calls. The exact fresh file was `sandpits/apex/ticket_20b_5e859079ce.txt`; 671 generated tokens, about 46.53 seconds including cleanup. Proof: `runtime/local_model_ticket_20b_tool_probe.json`.
- No hidden reasoning was exposed or executed. No paid fallback, model download, retraining, automatic mutation replay, or live Apex model reassignment occurred. A basic passing tool task does not certify arbitrary requests.
- The ticket processor can recheck an open ticket when a fresh diagnostic arrives after its last review. It includes parsed diagnostic receipts in the local analyst and Duck inputs. Its streaming gateway now has the same 8192-token default context as the legacy chat helper; explicit caller overrides remain intact.
- The latest same-ticket review ran Gemma triage -> Nineteen findings -> Duck YES and included the functional pass as well as the older failed-budget test. Full review and history: `runtime/local_model_handling_ticket_final.json`. The broader model-handling policy remains reviewable work; this is bounded execution evidence, not automatic deployment approval.

## Intent
Fridays is a local-first swarm that **does** things rather than reports them (`docs/the-standard.md`). The founding design (Studio doc "What We Are Building" and "Constraints That Must Never Be Broken") sets the rules agents work under:

- **Agents propose, Ghost approves.** No agent action reaches the real system without Ghost's sign-off (constraint 14).
- **Trust ladder.** Agents start in their own sandpit (`sandpits/<name>/`). They earn write access to real paths by reliable behaviour (constraint 22). Nothing leaves a sandpit for the real system without a check (23). Real-system writes are logged to `ghost_circle` (24).
- **Honesty and proof.** Work counts only when a real result shows it.

The local team and Seven have been restored. Apex (agent 21) is the direct local coder; Fred remains a separate local identity, not the only worker. DEOS (Decides, Executes, Operates, Sustains) remains the governance framework. PROD (5050) is the only running application environment; DEV/UAT remain off.

## The wrapper (what agents are asked to change)
- Flask app `frontend/terminal.py`; main page `frontend/templates/terminal_base.html` (3,324 lines): home page (`#home-page`), tiles, proof trail, the home chat (`#home-chat-body`, `#home-chat-input-area`) and a floating taskbar (`#taskbar`).
- Styles in `frontend/static/css/` (`taskbar.css`, `home-chat.css`, `windows.css`, `views/chat.css`...); behaviour in `frontend/static/js/views/` (`home-chat.js`, `chat.js`, `studio.js`...).

## The known wrapper bug (chat bar covered)
`#taskbar` is `position: fixed; bottom: 14px; left: 14px; z-index: 200` (`taskbar.css`). `.home-chat-section` sets `padding-bottom: 0 !important` and `margin-bottom: 0 !important` (`home-chat.css`), and the chat input is its last element. Nothing reserves room under the chat, so the floating taskbar sits over the input. Seen in a screenshot of the live page at a narrow width; not yet measured at Ghost's screen size. (`#terminal-shortcuts-panel` is the Terminal window's side panel, not this bug.)

## How a chat message becomes work
Browser posts `/api/chat` and polls by conversation; a job takes the single model slot; `agents/<name>/<name>_agent.py` builds the prompt (`utils/worker.py` picks the worker seat); `agents/skills_loop.py` runs `SKILL` lines through `fridays/skills.py` (read-before-patch, backups in `runtime/backups/fs/`, every call logged to `ghost_circle`). Studio steps owned by the worker are handed out by the `fred_work_cycle` task; changes to the real system go through proposals (`frontend/blueprints/proposals.py`, ALM gate in `frontend/services/alm.py`).
