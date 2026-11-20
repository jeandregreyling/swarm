# Handoff: Claude Code (VS Code session) to Claude Code in HB main chat, 20 Nov 2026

Read this first. It is the state of the work when the conversation moved from the VS Code session into HB's main chat.

## How we work

**Changes are HB change sets.** Use `core/hb_change_sets.prepare(...)` with edits, new files and a test list, so the tests pass before anything is applied.

**Practices (JD's requests) take one of two paths:**
- **Through APEX:** add a step (`runtime/claude_helpers/addstep.py`), bind it (`bind.py`), queue it (`clipq.py`), and APEX applies it.
- **Directly, when JD asks for speed:** run `cs.apply` → the targeted tests → `cs.commit` → `update_step_status(step, 'done')`.

**The full-suite gate runs after every change:** `runtime/claude_helpers/gate.sh`. It compares the run with `baseline_failures.txt` and reports only NEW failures. The baseline is 11 known failures:
- 4 old `test_chat_continuity` tests (they already failed before Practice 140);
- 6 Seven runtime tests and 1 Android test, waiting for JD's spec.

**Log your own work so it shows in the Claude Code lane:**
```
python runtime/claude_helpers/hbrun.py start|step|finish
```

**HB restarts through its own path:** add a row to `hb_restart_queue` and HB's tick does one announced restart after 60 s of quiet. Never restart `apex-server` yourself.

**Security rules:**
- No sudo from HB's shell; `/admin` sends the command to JD's own terminal.
- JD's email and credentials stay private.
- Don't probe SAP internal endpoints.

## Done today

**ROCm.** ROCm 10.2 is installed, llama.cpp `build-rocm` works, and APEX runs on ROCm:
- reading 309 tok/s against 34 on Vulkan;
- writing 25 tok/s against 15.

You can compare or switch with `/apex bench rocm|vulkan` and `/apex backend rocm|vulkan`.

**Research Practices 174–178.** Running out of tool calls keeps the best answer; web searches have their own allowance; APEX's steps show in the thinking bubble; answers don't mention drafts JD never saw. The suite now gets 11 of 12 answers right; /001 and /002 still say "gross pay" where SAP uses basic pay (processing class 01, rule X010).

**UI Practices 179–182.** The jump arrow glows and can lock; "How APEX got here" is saved under each reply; parked tasks are labelled "parked by HB"; the translator runs on demand, or automatically for Asian-language replies.

**Backlog sweep (183–184).** Eight old bugs closed. 6 of the 8 were stale tests; the bug method is now version 1.1.0, with the step "decide whether the code or the test is out of date". Old modules no longer add the retired root `/home/seven/swarm` to the import path.

**Practice 185.** A clean baseline: fixed the older tests this week's Practices had broken.

**HB Live (spec `docs/spec-hb-live-dashboard.md`):**

| Practice | Part | What it does |
|---|---|---|
| 186 | L1 | `hb_activity_log`, written by `chat_via_gateway` and `run_apex_tools` (both thin wrappers) |
| 187 | L2 | `core/hb_live.snapshot` and `/api/peer/v1/hb/live` |
| 188 | L3 | `hb-live.js`: the strip and windows |
| 189 | L4a | Tasks controls; codex, gemini and claude are doers |
| 190 | L5 | the strip takes over main chat's old HB widgets; `hbLive.classic(true)` brings them back |

Tested end to end: an APEX question showed live in the GPU lane, then in history with its trail.

## JD's feedback on HB Live (20 Nov, after seeing it): this is the next pass

> "The top banner actually becomes the main chat window output and this should be resizable; instead of just popping open new windows
> these should all be visible in main chat which becomes more of the communication logging layer of what is happening in the clipboard.
> I like that I can see who is doing what in the main banner but I don't care about the idle ones. Anything that is 'needs you' needs to
> still pop up as a window for me or any other actor to pick up, and I should see one list with HB orchestrating. More one-click, one
> window to rule them all. HB hasn't posted the task list in main chat with options for me to guide or automate the tasks. Everything
> should be going through main chat: what they think and ask and how they are managing the system - and the local actors should be the
> ones asking the questions of what to do and how to do it."

**Proposed design** (also sent to Codex and Copilot as requests 2597 and 2598 for their suggestions; their replies arrive in main chat):

- **A.** Main chat is one column with two panes and a drag divider. The top pane, **Live**, shows only active workers, each with its live trail. The bottom pane is the chat log.
- **B.** Under the active workers sits the one list, the clipboard. Each row has ONE primary button for its state (Start, Approve, Try again or Pause) and a "…" menu for the rest.
- **C.** Needs-you is the only pop-up. It appears when a decision is needed, gives one-click answers, can be taken by any actor, and closes itself when answered.
- **D.** The chat log is the communication layer. Each run (APEX, Fred, Codex, HB) is one compact message that updates in place: question, then plan, then result, with HB's choices as one-click buttons.
- **E.** HB posts the task list in chat when the day starts and whenever it changes: "Here is the plan - Let HB drive / Pick one / Pause".
- **F.** APEX and Fred ask first. When a step is unclear, they post the question in chat with one-click options before working.

**Seen just after JD switched every agent to Auto:** the resumed tasks were posted into main chat as raw JSON (`{"task_type": "hb_owner_resumed", ...}`). They should be one readable line, which is part of D.

## Still open

1. **The next pass, A–F.** Fold in Codex's and Copilot's suggestions first.
2. **L4b: make the doer route work.**
   - Today the clipboard doer is recorded but not used; the workflow always gives a step to APEX.
   - `fred`: at the step's start, call `hb_task_manager.local_help`, then `hb_plan_workflow._to_cpu_lane`.
   - `codex`, `gemini`, `claude`: the online model plans the step (reusing the review/instructor ladder in `hb_task_manager._queue`), then APEX carries it out with that plan.
   - Save the online model's method as a learning note in the KC. That is the learning loop JD wants: big models teach once, APEX reasons with the method next time.
3. **L6 guards.**
   - The unexplained-activity watchdog posts in main chat once per episode.
   - A gateway coverage test.
   - HB runs the full-suite gate itself after each Practice.
4. **JD's spec questions.**
   - Is the Seven direct runtime still in use (6 tests)?
   - Is the Hive Android worker still in use (1 test)?
   - The Media Center DAW review has no "done when".
   - Practice 79's test file is gone.
   - /pause: APEX is working on this now, but `tests/test_hb_queue.py` does not exist yet.
5. **Order-dependent test.** `test_chat_continuity::test_explicit_codex_address_bypasses_local_model_even_from_local_ui` fails when run alone and passes in the full run.
6. **The separate Chat window** still has its own board. Remove the hidden widget code once JD has lived with the new view.
