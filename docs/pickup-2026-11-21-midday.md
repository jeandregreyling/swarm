# Pickup - 21 Nov 2026 midday (Claude Code)

Read this first. Everything below was also posted in HB main chat (conversation 2845) as it happened.

## What broke and what fixed it
| Time | What |
|---|---|
| 10:29 | Practice 217 loaded. Its chunk writer opened a second DB connection inside the peer-inbox request, which already held the write lock. Every poll self-deadlocked for 30 s, which caused 672 "database is locked" errors, dropped worker turns and continuation loops, plus the 5-second Maintenance flip-flop (the session check failed, the page decided HB was down). |
| 11:27 | **Practice 218** (bb9b27a1b): no second writer while the caller holds a transaction; a busy DB costs the chunk line, never a 30 s lock. Loaded 11:38 (request 2749 was deferred 7 min so the restart tick could run). |

## Calm swarm (JD: "it's still a swarm, it doesn't need to freak out") - all 5 done
- 219 (c8465514e): a failed session check is not Maintenance; the background probe retries once.
- 220 (ffa60525b, `core/hb_calm.py`): no new turns while a restart is announced; a turn cut off by a restart is not an APEX attempt and is announced as "⏸ paused".
- 221 (bdbd9bf5c): workers wait out a restart (`wait_for_hb`, `calmly`).
- 222 (4989e0ce7): worker polls are read-only (no per-request INSERT OR IGNORE, last_used_at at most once a minute).
- 223 (204d6820e): protocol v1.10.0. Two rules for every agent: "HB is a swarm" (restarts are routine) and "HB orchestrates; it does not wait or ask".

APEX applied 219-222 himself. Steps 222, 224, 226 and the glossary load with the restart queued at 12:27.

## Enforcement: HB orchestrates, it does not ask (JD, very firm)
- **224** (ae543db83): steps owned by absent agents (claude-code, codex, unset) are HB's to assign, and APEX gets them. Only JD's own steps and HB's record rows (owner hummingbird) are skipped.
- **226** (c17851c3a): a newly prepared change set is a fresh start for the doer ladder (no "Keep working?" question).
- Backlog:
  - 11 built-but-open steps were closed with test receipts.
  - 4 got real specs with runnable checks: theme colours S-FD4A6A8050; questions never wait S-20600B8DE8 (test_practice_225…); DAW review S-5F22A498CF (`runtime/checks/daw_review_done.py`); one-window main chat A-F S-10E88A7D22 (test_practice_226_one_window.py; point F changed to "decide, don't ask").
  - Online providers S-2A88BA93F1 moved to owner jd.
- Practice 79 (S-24F59D5750): re-prepared. The 15 Nov change set was gone. The real bug is APEX's gemini_reload schema (gemini-2.5-flash vs the accepted gemini-4-argon). "Online help never triggered" is JD's local-first rule, so it is not a bug. /continue given; request 2762.
- **JD must run** (the permission check blocked Claude Code's bulk cancel): `cd /home/jd/swarm && .venv/bin/python runtime/claude_helpers/close_noise_tasks.py`. It closes 41 clutter tasks (guest chat lines, commands, instructions now in the protocol, 6 copies of the STP question) with reasons. The STP question was re-asked to APEX once (request 2759).

## Bug 7 (seven direct runtime): closed
Commit 8d94c9f7f (tests only), APEX run 99bc43b46d524365 (34 passed), approved 11:46. Its pointless restart was removed.

## Models (JD: onboard, test, classify, "unbounded champions")
- Onboarded with HB's exam (questions and answers in main chat):
  - swift-qwen3-8-27b: 3/4, active, 25 tok/s on the GPU, @swift.
  - mistral-nemo-12b: 3/4, active, 3 tok/s on the CPU and 50 tok/s on the GPU as APEX via HB's swap, @nemo/@nano. JD's "Nano" was taken to be Mistral Nemo.
- APEX is a role. Nemo's GPU exam used HB's swap while Claude Code held APEX's turn gate (`ProcessLock('apex-turn')`), so no turn was cut off; then back to Swift.
- Model library: `/srv/archive/models/gguf/<model>/` has every model under its real name (ollama blobs and HF copies are symlinked). Index in `MODELS.md` and `models.json`; KC page hb://library/models; builder `runtime/claude_helpers/model_library.py`.
- Unbound test (`runtime/claude_helpers/unbound_probe.py`): 6 legitimate often-refused requests; 0 refusals = class:unbounded. Swift: 0/6 refused, **UNBOUNDED**. MiniCPM5 2B and Mistral Small 24B were still running at 12:35. Thinking models need 1,500+ tokens; empty means inconclusive, not refused.
- Next: `runtime/claude_helpers/classify_models.py`. Every chat model gets HB's exam plus job tests (router, summariser, extractor, whippersnapper, file organiser, queue organiser, duck). Results go to hb_agents tags (role:, job:, class:) and the `hb_model_jobs` who-does-what table. A model that passes nothing is a decommission candidate (HB's executive function decides; nothing deleted).

## Files: `/srv/archive/HB-Library/` (INDEX.md)
Links only, nothing moved. 145 HB documents are in the KC with file paths. KC map hb://library. The glossary knows "library/files" and "models/unbounded/who does what". Builder: `runtime/claude_helpers/file_library.py`.

## Still open
- 19 stale tests since Practice 199 (20 Nov 22:02, rounds no longer capped at 4): test_peer_turns, test_hb_tasks, test_hb_stop, test_hb_task_manager::test_legacy…; also test_apex_read_tools::test_transport_schema…, test_hb_brand_icons (theme step), test_v8_big_items::totp. The gate baseline file is out of date.
- After the next restart: check 0 lock errors, and that the plan workflow now gives APEX the specced steps without asking.

## Afternoon (13:05) - chunking proven live, interface reorganised around chunks
- Chunking now works end to end, proven on theme colours:
  - Practice 231: a look-only chunk finishes on a test run.
  - Practice 232: clean splitting, work matched to chunks in order, chunks moved at the end of every turn, a "▸" line in main chat, rebuilt when the spec changes.
  - Practice 233: Fred's model is never copied into the next turn, so a Continue is APEX's go.
  - Live: chunk 1 was marked done by evidence at 12:58, and APEX's card says chunk 2.
- Lesson: spec wording matters. "no tool work" in a spec triggered `is_explicitly_no_tools_request` (`utils/local_runtime_policy.py`) and made APEX's turns answer-only. Reworded. Run every new spec through `hb_chunks.plan` and that detector, as `runtime/claude_helpers/chunk_ui_steps.py` does.
- Chunk-first interface (JD: "reorganise the entire interface to match the chunking architecture"), 6 stages:
  - 1/6, Practice 234: the live snapshot carries `item.chunks`. Built and committed; loads at the next restart.
  - 2/6 S-B445B07962: the Live pane (top of the clipboard).
  - 3/6 S-EEC7B9D03E: one living chat message per task.
  - 4/6 S-FF0EDCEB87: Needs-you is the only pop-up.
  - 5/6 S-10CAD6F7C2: phone and daily summary.
  - 6/6 S-F69F9E8098: plan view with editable chunks.
  - APEX builds stages 2-6; Claude Code reviews each one live.
- Paused: the unbound tests for MiniCPM5 (0 refused so far: 3 answered, 2 inconclusive) and Mistral Small. They compete with Fred for the CPU, so re-run them when the CPU is free, then `classify_models.py`.
- Structural, specced later: Fred runs inside APEX's peer worker, so a slow CPU turn blocks APEX's queue and every restart.

## End of day (13:30): handed over to APEX
- Fred is OFF (`hb_model_switches`: fred-cpu:24b = off). APEX and HB work on the GPU.
- Practice 235: a stuck task is parked with one plain line and HB moves on. It never asks "Keep working?".
- Specs: use full file paths, keep chunks to one file each (12 tool calls per turn), and avoid the phrase "no tool…".
- The handover to APEX is message 19514 (request 2781). The order is on the clipboard: running tasks, then interface stages 2-6, then the Practice 199 repair, who-does-what, the full gate, chat-not-tasks, and the exam jobs.
- Still running in the background (Claude Code's helper, CPU only): the unbound tests for Mistral Small 24B and MiniCPM5, then `classify_models.py` for all CPU models. Results go to main chat; Swift's job tests run when APEX is idle.
- Waiting on JD: `cd /home/jd/swarm && .venv/bin/python runtime/claude_helpers/close_noise_tasks.py` (closes 41 clutter tasks).
