# Comprehensive Test Plan and Execution Log

Last updated: 2026-04-01
Owner: Copilot (Ghost Layer)
Status: ACTIVE
Purpose: Deliberate end-to-end validation plan and execution evidence for chat, proposals, memory, tickets, email, terminal, and Discord/Telegram notification paths.

---

## Scope

This run validates:
- Service health and system reachability
- Chat runtime and multi-agent fanout
- ALM-governed API behavior
- Proposal lifecycle visibility
- Memory and ticket endpoints
- Terminal command execution path
- Email/Discord/Telegram notification routing and delivery

---

## Execution Sequence (Deliberate Order)

1. Baseline prechecks
2. Core API + ALM regression suites
3. Chat and agent runtime suites
4. Channel command/trust smoke suites
5. Terminal execution under ALM constraints
6. Notification diagnostics and live send tests
7. Consolidated daily gate
8. Fix + re-test loop for any failures

---

## Step-by-Step Results

## 1) Baseline Prechecks

Commands:
- systemctl is-active swarm-terminal swarm-listener swarm-discord swarm-telegram
- curl http://127.0.0.1:5050/
- python3 -m compileall -q frontend core lib fridays utils tests agents

Results:
- PASS: All four services active
- PASS: API root returned HTTP 200
- PASS: Syntax compile completed clean

## 2) Core API + ALM Regression

Commands:
- python3 tests/test_e2e_fridays.py
- python3 tests/run_uat_gate.py

Results:
- PASS: 21/21 E2E tests passed
- PASS: UAT gate passed (compile, e2e, telegram_trust, manager_onboarding, alm_gate_endpoints)

## 3) Chat + Agent Runtime

Command:
- CHAT_PING_ENABLE=1 CHAT_PING_AGENTS=gemma,llama,qwen,eight,librarian,duck,sniffles,nine,ten,eleven,twelve CHAT_MEMORY_AGENT=duck python3 tests/test_chat_quality.py

Results:
- PASS: 16 PASS, 0 FAIL, 0 SKIP
- PASS: Memory persistence requirement satisfied
- PASS: Agent ping stage log artifact generated

## 4) Channel + Trust Smoke

Commands:
- python3 tests/test_telegram_trust.py
- python3 tests/test_channel_smoke.py
- python3 tests/test_direct_agent_commands.py

Results:
- PASS: 18/18 telegram trust tests
- PASS: 7/7 channel smoke tests
- PASS: 6/6 direct command tests

## 5) Terminal Execution Path (ALM-Aware)

Checks:
- /api/hands/run without proposal_id returned HTTP 428 (expected under ALM gate)
- /api/hands/run with executed proposal_id and whitelisted command succeeded

Result:
- PASS: Governance and whitelist behavior both verified

## 6) Notification Diagnostics + Live Delivery

Diagnostics performed:
- Inspected trusted_senders, notification_senders, moderators tables
- Reviewed activity_log for listener/telegram/discord events
- Reviewed listener journal for push fallback and send/notify failures

Live delivery test:
- send_reply diagnostic to jeandre.greyling@gmail.com -> True
- send_reply diagnostic to jeandre.greyling@outlook.com -> True

Findings:
- Root reliability bug found: unknown-sender notification paths could log success even when send_reply returned False.
- Historical Gmail Push invalid_grant observed; listener fallback to IMAP polling maintained service continuity.

Fixes applied:
- core/pipeline/listener.py: notification sends now use checked send path and log notify_sent/notify_failed explicitly.
- fridays/telegram_bot.py: unknown-user notify now logs failure when send_reply returns False.
- fridays/discord_bot.py: unknown-user notify now logs failure when send_reply returns False.

Revalidation:
- All channel/trust suites passed after fix.
- Services restarted and healthy.

## 7) Consolidated Gate

Command:
- python3 ops/daily_gate.py --quick

Result:
- PASS: FULLY OPERATIONAL

---

## Current Status

- System readiness: GREEN
- Core workflows: GREEN
- Notification path (SMTP): GREEN
- Notification observability/logging: IMPROVED and VERIFIED
- Remaining improvement: Re-authorize Gmail Push OAuth token for instant push behavior

---

## Operator Follow-up (Minimal)

For real-time push (instead of IMAP fallback), run:
- python3 lib/email/gmail_auth.py
- sudo systemctl restart swarm-listener

Then verify listener journal no longer emits new invalid_grant push errors.
