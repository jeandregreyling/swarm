FRED-COURSE-08-FINDING-THINGS — Where files really are, and how to find them without guessing

THE RULE
Never type a file path from imagination. A path you did not see in a skill result probably does not exist, and the read fails with "Invalid file". Docs are not safe to guess either: docs/ARCHITECTURE.md, docs/FILE_STRUCTURE.md, docs/AGENTS.md and docs/DEVELOPER_GUIDE.md are 6-line stubs. The old Studio docs and the KC "fact" entries describe layouts from March and April 2026, so their file names are history.

HOW TO FIND A THING (in this order, one skill at a time)
1. SKILL search_landscape <word>   a generated index: UI element ids, JS views, blueprints, tables, skills, each with its file.
   Try the exact word from the request: SKILL search_landscape home-chat
2. SKILL system_index <word>   the same idea as a file list with sizes. It is rebuilt each time you call it.
3. SKILL fs_readonly ls <directory>   see what is really there.
4. SKILL fs_readonly grep <file> <text>   find the lines you mean, then read only those with lines <file> <start> <end>.
If a read says "Invalid file", do SKILL fs_readonly ls on the parent folder. Do not try another guess.

THE MAP (every path below exists)
- `frontend/terminal.py` the web app. `frontend/templates/terminal_base.html` the main page: home, chat bar, taskbar, modals.
- `frontend/static/js/views/` one JS file per tile: `home-chat.js` the chat bar on the home page, `chat.js` the chat tile, `studio.js`, `access.js`, `skills.js`.
- `frontend/static/css/` styles: `home-chat.css` chat bar, `taskbar.css`, `windows.css`, `views.css`, `responsive.css`, `core.css`, `themes.css`.
- `frontend/blueprints/` HTTP routes: `chat.py`, `proposals.py`, `docs.py`. `frontend/services/` helpers: `chat_history.py` is your routing block, `chat_jobs.py` the job tracking.
- `agents/fred/fred_agent.py` you. `agents/seven/seven_agent.py` Seven. `agents/skills_loop.py` runs your SKILL lines.
- `fridays/skills.py` every skill. `fridays/task_runner.py` and `fridays/scheduler.py` the scheduled tasks.
- `utils/watchdog_deos.py` Watchdog's work cycle. `utils/config.py` your system prompt. `utils/db/` database helpers. `core/knowledge/projects.py` Studio projects and steps.
- `docs/FRED_OPERATIONS.md` and `docs/ONE_MODEL_AND_MIND.md` are real guides. `swarm_docs/SYSTEM_INDEX.md` and `swarm_docs/SYSTEM_LANDSCAPE.json` are the generated indexes.
- `sandpits/fred/` is yours. `tests/` the tests. `runtime/backups/fs/` your file backups.

WORKED EXAMPLE
Request: "the chat bar is covered by shortcut buttons."
1. SKILL search_landscape home-chat shows home-chat.js and ids like home-chat-send-btn in frontend/templates/terminal_base.html.
2. SKILL fs_readonly grep frontend/static/css/home-chat.css position finds where it is placed.
3. Read those lines and quote them. Ask Ghost before changing anything.

CHECK YOURSELF
Without guessing, how would you find which file styles the taskbar? Show the first skill you would run.
