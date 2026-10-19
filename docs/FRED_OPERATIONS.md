# Fred's operations guide

You asked for clear instructions, procedures for proposals and priorities, and documentation on the architecture and roles. This is that. Every number below was read from the live database on 2026-10-19; re-check before you rely on one (`SKILL fs_readonly` cannot read the DB, so ask for a skill or use the admin skills you hold).

## 1. The system in one page
- **Fridays / Seven's Swarm** is a harness around language models. The Flask app is `frontend/terminal.py`; PROD is port 5050, DEV 5051, UAT 5053.
- **Shared database**: `swarm_memory.db`. **Your own memory**: `mind.db` (exchanges, thread_state, thread_facts, notes).
- **You (fred)** are the only active local agent. Other agents still active: `seven` (the orchestrator), `ten`, `scholar`, `gemini`. Parked (not deleted, rows and memory intact): gemma, mistral, qwen, llama, duck, eight, nineteen, twenty, thirteen, sniffles, librarian.
- **Orphaned or out of scope** (leave alone, report only): eleven, twelve, ghost_coder (dead host), seeker, ghost, duck_ddg.

## 2. Your roles and hats
- Roles held: system_administrator, chat_bot, coder, director, analyst, researcher, auditor.
- Hats (one at a time): system administrator, chat bot, coder. The routing layer (`core/routing.py`) groups work into seven categories: voice, coder, researcher, orchestrator, memory, auditor, messenger. `ROLE_DEFAULT_AGENTS` lists you first for each.
- A hat changes how you answer; it does not change what you are allowed to do.

## 3. Proposals
- A proposal (`work_proposals`) is how a change to the real system is requested and recorded. Statuses seen: pending, approved, in_progress, executed, done, closed, rejected.
- Live counts: 128 pending, 53 approved, 2 in_progress, 352 closed, 5 rejected, 1 executed, 1 done.
- Procedure for a real change: look first (read the file), write the smallest proposal that says what, where and why, wait for approval, then make the change, then read it back and report exactly what the read-back shows.
- Inside `sandpits/fred/` you may write freely; git tracks it.
- Your own open items: INTERNAL-MISTRAL-2083 and INTERNAL-GEMMA-2096 are in progress and inherited. 24 pending ones titled "Media job · musicgen", one "Probe do not approve" and one "Update fridays/task_runner.py" are the rest. Report on them; do not close any without being told.

## 4. The queue and priorities
- Table `queue`: 133 queued, 589 completed, 1389 abandoned. Lower number means more urgent.
- Priority counts across all rows: 1 = 230, 2 = 31, 3 = 72, 4 = 105, 5 = 1663, 7 = 10. Most work is the default, 5.
- Handle priority 1 and 2 first, then 3 and 4, then the rest. A queued item with no clear owner is a question to ask, not something to guess at.

## 5. Skills quick reference
- Read: `fs_readonly` (lines, grep, list). Always give the full path from the repo root.
- Write: `fs_write` for a new file (plain text only), `fs_patch` and `fs_patch_lines` to change part of a file.
- Proposals: `alm_create_proposal`; approval and completion have their own gates.
- If a skill errors, quote the error, say what you do not know, and retry with the full path.

## 6. How to report
- Say what you did, then what the read-back shows, in that order.
- Quote counts and names exactly. If you did not check, say "unverified".
- If a request has several parts, answer each one.

## 7. Where things are
- `agents/` agent code (`agents/fred/` is yours). `core/` routing and workflow. `frontend/blueprints/` the HTTP routes (`chat.py`, `agents.py`). `utils/` config, prompts and DB helpers. `tests/` the test suite. `docs/` documentation. `sandpits/fred/` your playground.
- Still thin and worth improving: `docs/ARCHITECTURE.md` and `docs/AGENTS.md` are only 6 lines each. Writing them properly, from the code, is a good first real job for you.

## Reading the database

Use the shell skill: `SKILL shell python3 scripts/db_query.py "select status, count(*) from project_steps group by status"`.
One SELECT in double quotes, optional second argument `swarm` (default) or `mind`. The file is opened read-only and output is capped at 50 rows. Never open or patch a `.db` with the file skills.

## Memory, Knowledge Center and Studio steps

- Fred's context is small on purpose. She looks things up instead of carrying them: `SKILL memory_search <query>` covers her own memory, `mind.db` notes and the shared pool; `SKILL swarm_knowledge_search <query>` covers the Knowledge Center (falls back to single words).
- Both lookups are allowed on read-only turns.
- `SKILL studio_step_update <step_id> <doing|done|blocked|skipped> <reason>` changes a Studio step she owns. The reason is required and logged to `ghost_circle` (`entry_type='step_update'`).
- Verify her reports from `ghost_circle` (`source='fred'`) and the DB, not from her reply.
- Prompts containing close/skip/mark/claim are treated as actions, not read-only questions.

## Editing files (no markers)

The SKILL line is plain text; content goes in ``` fenced blocks right after it. Block content is exactly what lands in the file (no diff markers, no line numbers).

| Skill | Blocks |
|---|---|
| `fs_write <path>` | 1: the full file (overwrites) |
| `fs_append <path>` | 1: text added to the end |
| `fs_patch <path>` | 2: exact old text, new text |
| `fs_insert_after <path>` | 2: exact anchor text, text to insert |
| `fs_patch_lines <path> <start> <end>` | 1: replacement lines |
| `fs_diff <a> <b>` | none (read-only) |

Every change keeps the previous version in `runtime/backups/fs/` (gitignored) and names it in the result. The old OLD/NEW/END angle-bracket markers are gone. The design came from Fred's own answers. `fs_append` and `fs_insert_after` are granted to her in `user_skill_permissions` (Access tile).
