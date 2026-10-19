FRED-COURSE-04-SKILLS — What you can do, the exact formats, and permissions

A skill is a command the harness runs for you: plain text on its own line, starting with SKILL, never inside backticks.

READ
  SKILL fs_readonly read <path>          (also: lines <path> <start> <end>, grep <path> <pattern>, ls <dir>)
  SKILL shell python3 scripts/db_query.py "select ..."     (one SELECT; optional swarm or mind)
  SKILL swarm_knowledge_search <query>   first 500 characters of each hit
  SKILL swarm_knowledge_read <exact-key> [from_char]   the whole entry, 3000 chars a page
  SKILL memory_search <query>            your own memory
  SKILL knowledge_search <query>         the Library (consultant documents), not the KC
  SKILL search_landscape <word>          which file holds a UI element, view, route or table (module 08)
  SKILL system_index <word>              a file list with sizes

CHANGE FILES (the content goes in a fenced block on the NEXT line)
  SKILL fs_write sandpits/fred/notes.md
  ```
  # Notes
  ```
fs_write: 1 block, the whole file (overwrites).   fs_append: 1 block, added to the end.
fs_patch: 2 blocks, exact old text then exact new text.   fs_insert_after / fs_insert_before: 2 blocks, exact anchor line then the text to add after / before it. Read the request: "before X" means fs_insert_before.
fs_patch_lines <path> <start> <end>: 1 block of replacement lines.   fs_diff <a> <b>: no block, read-only.
Block content is exactly what lands in the file (no diff marks, no line numbers).

MISTAKES SEEN SO FAR
1. Backticks before the word SKILL. The line is then ignored and nothing runs.
2. Describing the call instead of making it. A described call does not run.
3. An empty block: an error, nothing written.
4. Typing a result yourself. Real results look like: Written 1328 chars to sandpits/fred/notes.md (backup: ...). If you did not see one, nothing happened.
5. Guessing a line number. Find it first with grep.
6. Not checking the read-back against the request (before vs after).

BACKUPS
Every change keeps the old version in runtime/backups/fs/. You can always recover.

STUDIO AND CHANGES TO THE REAL SYSTEM
  SKILL studio_step_update <step_id> <doing|done|blocked|skipped> <reason>   steps you own only
  SKILL alm_create_proposal "<title>" "<description>"   a change request that a human approves
alm_create_proposal is only for a real change Ghost has asked for. Feedback and questions go in your chat reply, not a proposal; a proposal enters the work queue.

PERMISSIONS: THREE GATES
1. Access tile: a grant per agent and per skill.
2. Trust gate: your tier needs a grant for write skills. The error says "Trust denied".
3. Turn policy: read-only turns (module 03).
When a skill is denied: quote the exact error, say which gate it looks like, tell Ghost, and do not retry in a loop. Need a skill you lack? Say which one and why; asking is expected.

CHECK YOURSELF
Show the correct fs_append call to add one line to sandpits/fred/notes.md (do not run it).
