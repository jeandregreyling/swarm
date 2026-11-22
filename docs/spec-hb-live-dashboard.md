# HB Live: main chat as the one dashboard

Owner request, 20 Nov 2026:

> "Rule number 1 is that everything should always be visible in main chat: system telemetry, APEX and HB thinking, including Fred and even
> online models. It should be a live display pulling everything together so I can have one view of everything going on."
> "HB is the orchestrator and all models should go through the clipboard already built. 'Needs you' and 'HB Driving' still seem
> disconnected. Main chat is the main dashboard: different windows can open as bubbles on top of the main chat, and HB keeps track of it
> all, in real time."

This document is the contract. Every Practice in the build is checked against it, and the acceptance tests at the end must pass.

## 1. Why the current view is fragmented

**What is recorded, and where.** Each kind of work keeps its own record:
- APEX workflow turns: `hb_executions` + `hb_peer_work` stage + `hb_task_events`;
- main-chat APEX turns: only SSE stage pushes, plus saved steps since Practice 181;
- Fred and the online peers (Codex, Gemini, Claude Code): `hb_peer_work` + lane events;
- background jobs: `hb_background`, in memory;
- admin steps: `hb_admin_requests`;
- the translator: `hb_translator`;
- direct model calls outside a task: nowhere;
- Claude Code's own sessions and harness runs: nowhere unless posted.

**What is displayed, and where.** Main chat has at least eight widgets, each fetching from its own endpoint on its own timer:
- `hb-needs-you.js`, `hb-approval-popup.js` and `hb-queue.js` (HB Driving);
- `hb-activity.js` and `hb-live-activity.js`;
- `hb-turn-steps.js`, `hb-maintenance.js` and `hb-network.js`;
- plus the thinking bubble.

Each fix this week joined one record to one widget. Work on any other path stays invisible, which is the "fans spinning, nothing shown" case.

## 2. Principles

1. **One read model.** `core/hb_live.py: snapshot(conn)` is the only place that decides what is going on. Every widget renders from it.
2. **One endpoint, one client.**
   - `GET /api/peer/v1/hb/live` returns the snapshot plus a version.
   - `frontend/static/js/hb-live.js` fetches it every 2 s while the page is visible, and at once when an SSE `chat` or `hb_live` event arrives.
   - The older widgets are retired as their parts move in.
3. **Database first.** Workers run in several processes (the web app, Fred and the peers, admin terminals, Claude Code). The database is the truth, and SSE is only a "changed, fetch now" nudge.
4. **HB orchestrates through the clipboard.** The master list *is* the clipboard (plan steps plus `hb_clipboard`), with live state attached. Every model works on a clipboard row or is logged as an unplanned call. The doers are extended to `hb | small | apex | fred | codex | gemini | claude`. HB picks the doer; JD can change it.
5. **Write once at the choke points.**
   - **Model calls:** `core/llm.chat_via_gateway` writes every call, local or online, to `hb_activity_log`. It records start and finish, the model, the device, the task if known and the purpose.
   - **The task lifecycle:** writes in `hb_tasks.event` (already central).
   - **Adapters** cover everything outside both: admin, background jobs, the translator, telemetry and Claude Code.
6. **Nothing disappears.** Finished work moves into history with its step trail (the "How APEX got here" list, for every lane).
7. **Guards keep it whole:**
   - the unexplained-activity watchdog (§6);
   - the visibility acceptance test (§8);
   - the full-suite gate after every Practice.

## 3. Data

### `hb_activity_log` (new, append-only, pruned after 7 days)

| column | meaning |
|---|---|
| `id` | row id |
| `at` | epoch seconds |
| `run_id` | groups the events of one run: a model call, a turn, an admin step |
| `lane` | `gpu`, `cpu`, `online`, `hb`, `admin`, `claude-code`, `system` |
| `actor` | `apex`, `fred`, `small`, `codex`, `gemini`, `claude`, `hb`, `jd` |
| `model` | the real model name (`swift-qwen3.8-27b`), never a server alias |
| `device` | `ROCm`, `Vulkan`, `CPU` or `online` |
| `task_id`, `step_id` | when known |
| `kind` | `start`, `step`, `tool`, `check`, `finish` or `error` |
| `text` | one plain line |
| `purpose` | why the call happened: `main-chat turn`, `workflow step`, `review`, `homework`, `research digest`, ... |

### The read model: `snapshot(conn)`

```
{
  version,
  lanes: [
    {id, label, device, state: idle|busy|waiting|off,
     now:   {run_id, actor, model, task_id, step_id, title, since, last_step},
     trail: [last 12 events of the current run]}
  ],
  telemetry: {gpu: {busy_pct, vram_used_gb, vram_total_gb, temp_c, junction_temp_c,
                    clock_mhz, clock_limit_mhz, fan_rpm, power_w, power_cap_w, performance_mode},
              cpu: {load1, cores, temp_c, clock_mhz, max_clock_mhz, governor}, ram: {used_gb, total_gb}},
  needs_you: [... core/hb_commands.waiting_items (same as /approvals)],
  master: [
    clipboard rows: {step_id, task_id, title, state, doer, lane, importance, ready, check,
                     live: {run_id, since, last_step} | null, parked, why}
  ],
  history: [last 20 finished runs: {run_id, actor, model, title, took_s, outcome, steps_count}],
  unexplained: [{lane, since, evidence}]
}
```

## 4. Lanes

| Lane | What runs there | Source |
|---|---|---|
| GPU · APEX | APEX turns: main chat and workflow | activity log (gateway) + executions + turn steps |
| CPU · Fred | Fred turns, lane steps, counsel | activity log + `hb_peer_work` (fred) |
| CPU · small | homework, translator, embeddings | activity log + `hb_background` + `hb_translator` |
| Online | Codex, Gemini, Claude (as doers) | `hb_peer_work` for peer recipients + activity log |
| HB | the workflow driver, checks, reviews, settings and GPU guard ticks | task events + activity log |
| Admin | sudo steps in JD's terminal | `hb_admin_requests` |
| Claude Code | sweeps, suite runs, change sets prepared or applied | activity log, written by `runtime/claude_helpers/hbrun.py` |
| System | GPU, CPU, RAM, temperatures | sysfs and `/proc` (no model) |

## 5. Main chat as the dashboard

**The top strip (always visible, one line).** One chip per lane: an icon, the lane name, and a state dot (idle grey, busy green pulse, waiting amber, error red). Each chip also shows the current activity in a few words, plus the Needs-you count and the master-list count. The strip replaces the "HB now" line, the HB Driving header and the Needs-you bar.

A routine restart-interruption warning is not an owner action when the same task
and recipient already have a newer queued, running or completed attempt and Continue is
effectively On. Keep the interrupted receipt in history, but omit its stale
Needs-you entry. Genuine owner holds and unresolved reviews remain visible.
An open Needs-you card closes when its item disappears, unless a decision is
being saved or an unsaved approval comment is present. Preserve that comment,
explain that the decision is no longer pending, and disable its obsolete actions.

**Windows.** These are floating cards over the chat, like a console overlay:
- Clicking a chip opens that lane's **live window**: who and what, the model and device, the elapsed time, and the step trail updating as it happens. Finished runs appear below it with their steps.
- **The master window** holds the clipboard as one list:
  - Needs-you items are pinned at the top.
  - Then come now, next, waiting, parked and blocked.
  - Each row shows its doer and its live step.
  - The controls are: pause, continue, cancel, approve, up/down/top, importance, and the doer (including codex, gemini and claude).
- **The system window** shows GPU, CPU and RAM with temperatures, and any unexplained activity.
  It also shows actual GPU clocks and the applied clock limit, hotspot, fan RPM,
  power/cap and mode, plus CPU0 clock/governor. These are live sysfs readings,
  not a prediction of task progress. The status line includes clocks, limit and governor.
  The agent `runtime_status` tool exposes the same canonical `telemetry` object.
  Missing readings remain absent; telemetry does not raise clocks or voltages.

**Window behaviour:**
- Windows can be dragged.
- They minimise into a bubble on the right edge, which still shows a pulse and the latest line.
- Several can be open at once.
- The set of open windows is remembered per viewer in `localStorage`, as a per-viewer convenience.
- Nothing is lost when a window closes: the snapshot is the truth.

**The messages themselves** stay chat. APEX replies keep "How APEX got here". HB's posts link to the window they belong to.

## 6. Guards

- **Unexplained activity** (HB tick, every 60 s): HB raises a line in main chat once per episode when:
  - the GPU is more than 30% busy for 2 minutes, or a model server's slot is processing, *and* no `start` without a `finish` exists in the activity log for that lane;
  - or the CPU is busy in the same way.

  The line reads: *"HB: the GPU is busy but nothing HB knows about is running - <evidence>"*. The episode also appears in the snapshot's `unexplained`.
- **Gateway coverage test:** fails if code under `core/`, `frontend/` or `scripts/` calls a model endpoint (`/completion`, `/v1/chat/completions`, `/api/chat`, the online SDKs) without going through `chat_via_gateway`. Known exceptions (health probes, benchmarks) are listed explicitly in the test.
- **Full-suite gate:** after each applied Practice, HB runs the full suite in the background. It compares the result with the last baseline and posts new failures with the Practice that caused them.

## 7. Build order (Practices)

| # | Practice | Done when |
|---|---|---|
| L1 | `hb_activity_log` plus the gateway hook (start and finish of every model call, with a purpose and the real model name) and `hbrun.py` for Claude Code | a gateway call in tests writes start and finish; `hbrun` writes a run |
| L2 | `core/hb_live.py` snapshot: lanes from all sources, telemetry, needs-you, master (clipboard plus live state), history; the `/hb/live` endpoint | the snapshot test covers every lane with fake records |
| L3 | `hb-live.js` top strip plus windows (lane, master, system); the SSE nudge | a Node test renders the strip and windows from a fixed snapshot; the page loads it |
| L4 | Master window controls through the existing routes (`/hb/queue` task and clip), plus the online doers in the clipboard (`codex`, `gemini`, `claude` route to peer requests) | the controls test; a doer change is recorded with who made it |
| L5 | Retire the widgets replaced by the strip (HB-now pill, HB Driving header, Needs-you bar, live strip): they stay as code until L5, then are removed with their tests updated | full suite green; the page has one HB widget |
| L6 | Guards: unexplained-activity watchdog, gateway coverage test, full-suite gate | the guard tests; the watchdog posts once per episode |

## 8. Acceptance (`tests/test_hb_live_acceptance.py`)

Start fake records for each of these, then call `snapshot()`:
- an APEX main-chat turn;
- an APEX workflow step;
- a Fred lane step;
- a Codex peer request;
- an admin step;
- a homework job;
- a translator start;
- a Claude Code `hbrun`;
- an unplanned gateway call.

Every one must appear in its lane with the right actor, model, task and last step. After each finishes, it must appear in `history` with its step count. A busy GPU with no running record must appear in `unexplained`.
