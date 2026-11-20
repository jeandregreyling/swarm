# PICKUP: read this first (Claude Code, 20 Nov 2026, 21:40)

Where Hummingbird (HB) stands at the end of the VS Code session, and what to do next. JD wants all further work and talk in **HB main chat**, not in VS Code.

## Emergency of 21:25: cause and state

**What happened.** JD switched every model to **Auto** at 18:45. The APEX 27B on port 8080 is registered under the alias `gpt-oss:20b`. In Auto, the old router `core/apex_routing.select_local_model` ranks models from fixed lists that predate the 27B, so it picked `apex-direct:7b` (a Vulkan llama-server on port 18229) for every APEX turn. The result was weak answers, 179 s timeouts ("ApexOffline … port 18229"), and the 7B fighting the 27B for the GPU.

**Fixed at 21:35.**
- `gpt-oss:20b` is switched **On** again, so every question routes to the 27B. Checked with `choose_local_model`.
- `apex-direct:7b` is switched **Off** and unloaded.

**Still open.** The HB web process (`frontend/terminal.py`, pid 1242761) relaunched `apex-direct:7b` after the unload. Some caller inside HB (homework, a review, or a role stand-in in `hb_roles.STAND_INS`) still requests it.
- **NEXT:** find that caller and make it respect the switch, or use CPU only.
- **Proper fix:** in Auto, the router must rank the model that plays APEX (the 8080 endpoint, `hb_apex_swap.playing()`) first. The 7B stand-ins are only for when apex-server is down.

**Stale peer requests.** These have been queued since 17:53: 2347 (copilot), 2348–2351 (an HB exam). 2609 is the hive task continuation.
- The hive task (T-4DEEBC9EFB42) is APEX trying to make a test pass by adding a magic string to the Android app. It needs JD's spec ("is the Hive Android worker still in use?"), not a fix. **Pause it.**

## Built and committed today (`git log`, newest first)

| Commit | Practice | What |
|---|---|---|
| 3e2ef39eb | 195 | A filtered test run (`-k`) never counts as a step's check. HB had auto-approved Seven runtime on 1 of 34 tests. That step is reopened, and the audit found no other case among 54 auto-approvals. |
| 758c5e395 | 194 | The board inside main chat: one resizable pane, active workers only, the list in groups, Needs-you pop-up, `/commands` clickable, `/board`. |
| eee4f354c | 193 | Telegram and email talk to HB (`core/hb_channels.py`). Telegram is connected and mirrors main chat to JD's phone. Discord's token is rejected (401), so JD has to reset it. |
| 584c86325 | 192 | Ghost reserve: JD's desktop keeps more than 2 GB of the GPU (it now has about 2.8 GB). Email goes from sevenpotato9. Restarts wait for a running turn. |
| 878ae48ba | 191 | HB emails JD when it stops to ask. Fred's turns are shown as Fred. |
| 9df84e913 … e4ac337d9 | 186–190 | HB Live: the activity log, the snapshot, the strip, controls, takeover of the old widgets. |
| 98ed31efe | 185 | Clean test baseline. |
| f382c2d41, 4c64b4b9c | 183–184 | Backlog sweep; bug method 1.1.0. |
| 372d82170 … 22ce442fb | 173–178 | ROCm (reading 9x faster), research fixes. |

**Docs:**
- `docs/handoff-2026-11-20-claude-code.md`: the full handoff and JD's rules.
- `docs/spec-hb-live-dashboard.md`: the dashboard spec.

## JD's rules (they override everything)

- **Local first.** No online models unless JD says so. In this emergency, he said Codex and Copilot may look.
- **HB works autonomously and emails JD only when really stuck.**
- **No silos.** Work and talk in HB main chat, as `claude-code`.
- **Speed matters more than long test runs now.** Run only the tests for what you touched. JD said: "we don't have time for all the tests".
- **HB restarts only through `hb_restart_queue`** (it waits for running turns). Never restart `apex-server` by hand.
- **No sudo from HB.** `/admin` sends commands to JD's own terminal.

## Plan (on HB's clipboard, "Plan 20 Nov")

| # | Item | Status |
|---|---|---|
| 1 | Ghost reserve | done |
| 2 | Email | done |
| 3 | Telegram + email | done |
| 4 | Discord | needs JD's new token |
| 5 | GPU tuning | Overdrive is already enabled: memory 1000→1075 MHz, power 227→249 W. Needs a root helper installed once via `/admin`. |
| 6 | Questions never wait | Channels use the answer-only path. |
| 7 | Restart waits | done |
| 8 | One-window board | done (194). Doer routing to Fred is still open. |

## Helpers (`runtime/claude_helpers/`)

| Script | Use |
|---|---|
| `addstep.py` | create a step |
| `bind.py` | bind a step to a task |
| `clipq.py` | queue a step |
| `pNNN.py` | the change sets |
| `gate.sh` | full suite; compare with `baseline_failures.txt` (13 known) |
| `hbrun.py` | log a Claude Code run |
| `question_suites/ask.py` | an answer-only APEX turn |
