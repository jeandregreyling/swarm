FRED-COURSE-08-FINDING-THINGS — Where files really are, and how to find them without guessing

THE RULE
Never type a path from imagination. A path you did not see in a skill result probably does not exist (the read fails with "Invalid file"). Docs are not safe to guess either: docs/ARCHITECTURE.md, docs/FILE_STRUCTURE.md, docs/AGENTS.md and docs/DEVELOPER_GUIDE.md are 6-line stubs. Old Studio docs and KC "fact" entries describe the March-April 2026 layout, so their file names are history.

HOW TO FIND A THING (in this order, one skill at a time)
1. SKILL search_landscape <word>   a generated index: UI element ids, JS views, blueprints, tables, skills, each with its file.
   Use one code word (home-chat, taskbar); if a phrase finds nothing, try a single word.
2. SKILL system_index <word>   a file list with sizes.
3. SKILL fs_readonly ls <directory>   see what is really there.
4. SKILL fs_readonly grep <folder-or-file> <text>   a folder lists file:line for every match; a file shows the lines around each match. Then read only those lines with lines <file> <start> <end>.
If a read says "Invalid file", run SKILL fs_readonly ls on the parent folder, not another guess.

THE MAP (every path below exists)
- `frontend/terminal.py` the web app. `frontend/templates/terminal_base.html` the main page (home, chat bar, taskbar).
- `frontend/static/js/views/` one JS file per tile: `home-chat.js` the chat bar on the home page, `chat.js` the chat tile, `studio.js`, `access.js`, `skills.js`.
- `frontend/static/css/` styles: `home-chat.css` chat bar, `taskbar.css`, `windows.css`, `views.css`, `responsive.css`, `core.css`, `themes.css`; per-tile styles are in `frontend/static/css/views/` (`chat.css`).
- `frontend/blueprints/` HTTP routes: `chat.py`, `proposals.py`, `docs.py`. `frontend/services/` helpers: `chat_history.py` is your routing block, `chat_jobs.py` the job tracking.
- `agents/fred/fred_agent.py` you. `agents/seven/seven_agent.py` Seven. `agents/skills_loop.py` runs your SKILL lines.
- `fridays/skills.py` every skill. `fridays/task_runner.py` and `fridays/scheduler.py` the scheduled tasks.
- `utils/watchdog_deos.py` Watchdog's work cycle. `utils/config.py` your system prompt. `utils/db/` database helpers. `core/knowledge/projects.py` Studio projects and steps.
- Real guides: `docs/FRED_OPERATIONS.md`, `docs/ONE_MODEL_AND_MIND.md`. Generated indexes: `swarm_docs/SYSTEM_INDEX.md`, `swarm_docs/SYSTEM_LANDSCAPE.json`.
- Yours: `sandpits/fred/`. Your backups: `runtime/backups/fs/`.

WORKED EXAMPLE
"The chat bar is covered by shortcut buttons."
1. SKILL search_landscape home-chat shows home-chat.js and element ids in frontend/templates/terminal_base.html.
2. SKILL fs_readonly grep frontend/static/css shortcut lists every css file and line that mentions it. A folder works, not only a file.
3. Read those lines and quote them. Ask Ghost before changing anything.

CHECK YOURSELF
How would you find which file styles the taskbar, without guessing? Show the first skill.
