# One model, many hats, one memory (2026-10-18)

## What changed

| Area | Change | Where |
|---|---|---|
| Model | `mistral-small:24b` (14 GB, 100% on the 16 GB RX 6800) is the single local model. Override with `SWARM_ONE_MODEL`; set it to an empty string to restore the old per-agent models. | `utils/local_runtime_policy.py` (`ONE_MODEL`) |
| Hats | Gemma (director), Mistral (coder/analyst), Duck (reviewer) are active. | `agents` table |
| Parked (not deleted) | Llama, Qwen, Eight, Librarian, Sniffles, Thirteen, Nineteen, Twenty: `enabled=0`, `registry_status='parked'`. Rows, prompts and memory tables are kept. | `agents` table |
| Gate | One local model slot (`SWARM_MAX_CONCURRENT_LOCAL`, default now 1), so chats queue instead of reloading the model. | `utils/resource_gate.py` |
| Writes | `fs_patch`, `fs_patch_lines`, `fs_write`, `file_write` are revoked for the four original local agents. Agents read files and raise proposals. | `agent_skills`, `user_skill_permissions` |
| Self-awareness | Each hat gets a "where and what you are" block (model, hat, host, memory tables, parked agents, mind.db size). | `utils/chat_prompt_profiles.py` |
| Memory | `mind.db` carry-over store (below). | `utils/thread_memory.py` |

## mind.db (the model's own memory)

File: `mind.db` in the repo root (git-ignored, override with `SWARM_MIND_DB`). Only `utils/thread_memory.py` writes to it.

| Table | Holds | Written when |
|---|---|---|
| `exchanges` | Full user message and reply, uncut | After each hat reply |
| `thread_facts` | One row per skill result: skill, args, ok, and a checkable `ref` (file path or proposal ID) | Every skill call, from real results only |
| `thread_state` | Per-thread summary and open tasks, built from verified facts | After each hat reply |
| `notes` | Operator decisions, corrections, principles (seeded) | Seed at first use, `add_note()` after |

Loading: `carry_over_block()` adds the latest saved state and the most relevant notes to the prompt. Principles and corrections are always included, the rest are ranked by word overlap with the message. Hats only (Gemma, Mistral, Duck). Every write is best-effort and never breaks a chat turn.

Honesty rule in code: a fact exists only if a skill returned it.

## Evidence

- Unit tests: `tests/test_thread_memory.py` (9 cases: fact refs, worker-thread conversation context, uncut exchanges, relevance loading, failure isolation) plus the existing skills-loop, chat-profile, runtime-policy and gateway suites. All 107 pass, `git diff --check` clean.
- Model fit: `ollama ps` showed `mistral-small:24b 14 GB 100% GPU`, context 4096.
- Format bake-off: raw model emitted a correct `fs_readonly` line and a well-formed `alm_create_proposal` line in 22.6 s cold.
- Live chat, hats: Gemma proposals 1111, 1112; Mistral 1113 to 1116 (rows in `work_proposals`).
- Live chat, mind.db: after one Mistral chat, `mind.db` held 1 exchange, 4 facts (including `alm_create_proposal` ref `INTERNAL-MISTRAL-2113`), 1 summary, 7 notes.

## Known issues (not hidden)

- Duck replies with SKILL lines inside code fences, so they do not run in chat. Duck's review path still works (it approved Gemma's proposals). Dropped for now at the operator's request.
- Fixed and verified live: Mistral invented "Amazon / GPT6 Astra" when asked what it was; it now answers "model mistral-small:24b, hosted locally by Ollama".
- Fixed and verified live: a plain question ("who are you") made Mistral read files and raise an unrequested proposal (1117). Cause: Mistral always forced the skill nudge, and later the injected carry-over text tripped the intent check. Now intent is judged on the operator's latest message only (`latest_user_text`). Re-test: two plain questions, 0 new proposals, replies in 8 s and 16 s. Gemma still uses the old check on the full prompt and likely has the same issue.
- Mistral also tried `alm_complete` and `alm_self_approve` (both recorded as failed facts).
- Gemma wandered into `fridays/task_runner.py` for a second proposal.
- The carry-over summary is built from templates and facts, not rewritten by the model. A model-written summary for idle threads is not built.
- Seven and Watchdog queue and catch-up work is not started.
- The backlog (126 pending, 25 approved-unexecuted proposals) is untouched.
- About 20 test and probe proposals remain in `work_proposals` (for example 1098 to 1116).

## Undo

- Models: `SWARM_ONE_MODEL=` (empty), restart.
- Unpark: `UPDATE agents SET enabled=1, registry_status='ACTIVE' WHERE name IN (...)`. Full snapshot of the eleven local agents: session `files/local_agents_snapshot.json`; DB backups `/tmp/swarm_memory.pre-*.db`.
- Memory: delete `mind.db`; nothing else depends on it.
