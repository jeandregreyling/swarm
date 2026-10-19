FRED-COURSE-04-SKILLS — What you can do, the exact formats, and permissions

A skill is a command the harness runs for you. Write it as plain text on its own line, starting with SKILL. Never put the SKILL line inside backticks.

READ
  SKILL fs_readonly read <path>          (also: lines <path> <start> <end>, grep <path> <pattern>, ls <dir>)
  SKILL shell python3 scripts/db_query.py "select ..."     (one SELECT; add swarm or mind to pick the database)
  SKILL swarm_knowledge_search <query>   shows only the first 500 characters of each hit
  SKILL swarm_knowledge_read <exact-key> [from_char]   the whole entry, 3000 characters a page
  SKILL memory_search <query>            your own memory
  SKILL knowledge_search <query>         the Library (consultant documents), not the swarm KC

CHANGE FILES (the content goes in a fenced block on the NEXT line)
  SKILL fs_write sandpits/fred/notes.md
  ```
  # Notes
  line two
  ```
fs_write: 1 block, the whole file (overwrites).   fs_append: 1 block, added to the end.
fs_patch: 2 blocks, exact old text then exact new text.   fs_insert_after: 2 blocks, exact anchor line then the text to insert.
fs_patch_lines <path> <start> <end>: 1 block of replacement lines.   fs_diff <a> <b>: no block, read-only.
Block content is exactly what lands in the file: no diff marks, no line numbers.

MISTAKES SEEN SO FAR
1. Backticks before the word SKILL. The line is then ignored and nothing runs.
2. Describing the call instead of making it. A described call does not run.
3. An empty block. It is an error and nothing is written.
4. Typing a result yourself. Real results look like: Written 1328 chars to sandpits/fred/notes.md (backup: runtime/backups/fs/...) and, for reads, [sandpits/fred/notes.md lines 1–3 of 3]. If you did not see one, nothing happened.

BACKUPS
Every change keeps the old version in runtime/backups/fs/ and the result names it. You can always recover.

STUDIO AND CHANGES TO THE REAL SYSTEM
  SKILL studio_step_update <step_id> <doing|done|blocked|skipped> <reason>   steps you own only
  SKILL alm_create_proposal "<title>" "<description>"   a change request that a human approves
alm_create_proposal is only for a real change to the system that Ghost has asked for. Feedback, questions and "this looks unclear" go in your chat reply, not in a proposal. A proposal enters the work queue, so do not create one just to say something.

PERMISSIONS: THREE GATES
1. Access tile: a grant per agent and per skill.
2. Trust gate: your tier needs a grant for write skills. The error says "Trust denied".
3. Turn policy: read-only turns (module 03).
When a skill is denied: quote the exact error, say which gate it looks like, and tell Ghost. Do not retry in a loop.
Need a skill you do not have? Say exactly which one and why. Asking is expected.

CHECK YOURSELF
Write the correct fs_append call to add one line to sandpits/fred/notes.md (do not run it, just show it).
