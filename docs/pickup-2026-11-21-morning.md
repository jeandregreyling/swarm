# Pickup - 21 Nov 2026 morning (Claude Code -> APEX; Claude Code back ~11:30 AEST)

## Committed this session (Practices, all via change sets)
| # | Commit | What |
|---|---|---|
| 206 | 329d4537b | Peer worker waits out a slow inbox; supervisor retries after a 5-min cool-down (never gives up for good) |
| 207 | 55f5e0c66 | Task packet always fits (APEX improved it in Repair 8, 2695f485d: paginated task_context) |
| 208 | 43c701148 | Real model names on cards/flowers; "Chat with JD" carries only last 3 lines; clipboard first; JSON titles as words |
| 209 | 7aae0d91d | core/hb_announce.py: HB posts ▶/✓/✗ work lines in main chat; ribbon sizes itself (no drag) |
| 210 | d0765af84 | hb.glossary pack: JD's words (ribbon, clipboard, gold window...) -> HB parts + files on APEX's card |
| 211 | 06607fd13 | Workflow gives untasked APEX steps their HB task (the 07:45-08:00 stall); "Start now" works |
| 212 | 2220a3dc8 | core/hb_guest.py: Telegram guests - welcome on enrolment, /help /about /mine /start, own Q&A only |
| 213 | 419172a0f | Guests get APEX's opinion in his own words, never SAP note text |
| 215 | 889f43644 | APEX makes 4 own attempts since last progress before Fred (review threshold 4; no question to JD before that) |

## State at handover (09:05)
- **Practice 215 restart is QUEUED** (hb_restart_queue 'claude-code-p215'), waiting for request 2735 (on Fred). Until it loads, Fred still takes over early. Confirm the web PID changed after it.
- Hari onboarded: telegram:6002578616, role user. JD got the onboarding preview on his Telegram.
- Codex is out of tokens; @git (copilot-instructor) is offline - no HB worker for it; GitHub login cannot be used as a model (models endpoint answers plain "OK").
- Codex's three phone-flow steps are now owned by APEX:
  - S-6BB03F4918 (flow 3, truthful ✓/✗/■ announcements) - PREPARED change set (p214.py, 18 checks), task T-2962A44A3E23, top of clipboard.
  - S-D07EDB3C87 (flow 1, keep question/reply/follow-up together) and S-D71694FFDC (flow 2, truthful phone progress) - NOT prepared; specs + Done-when in the steps.

## Waiting on JD
- /cancel T-9CFF3626DAB6 (plan 3/8 Telegram, already done), /cancel T-4AF257FA78C2 (4/8 Discord, needs new bot token), /cancel T-2C072DC849ED (5/8 GPU tuning, needs /admin root helper). Claude Code's own attempt to close them was blocked by the permission classifier.
- GPU: Radeon AI PRO R9700 32 GB (~AUD 2,700-2,900) recommended; check PSU >= 750 W and case length ~27 cm.

## Next for Claude Code (11:30)
1. Verify 215 loaded; check APEX applied S-6BB03F4918.
2. Peer worker: api.post of a reply failed while the web app restarted (08:49, URLError) - give it the same wait-and-retry as the inbox (Practice 206).
3. Repair tests/test_hb_task_manager.py::test_legacy_decision_failure_is_checkpoint_not_dead_end (fails on HEAD: replies to an APEX decision as Codex; needs MAX_PEER_CHAIN=4 and the APEX author).
4. /train exercises in JD's words (ribbon, gold window) to measure the glossary.
5. Design goal only (not a task): HB for other consultants - per-person space, fair GPU queue.

## Working rules (JD)
Report in HB main chat (conv 2845, from_agent claude-code). Names not roles; pronouns he for Claude Code and APEX. APEX does the work; Fred only after APEX's 4 attempts. No online models unless JD says. Announce restarts; never restart apex-server by hand.
