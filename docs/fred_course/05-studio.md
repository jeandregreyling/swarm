FRED-COURSE-05-STUDIO — Projects, steps, the work cycle and the status line

WHAT STUDIO IS
Ghost's task board (the Studio view). A project holds ordered steps, plus test cases, notes and documents. There are about 2,000 steps in total. Almost all are finished or skipped.

A STEP HAS
step_id (like S-8F154CDB81), title, description, status, owner, owner_route, residual_risk, and evidence.
Statuses: todo, doing, blocked, partial, done, skipped.
Owner: who does it. Steps owned by fred are yours. Seven is the default owner of unclaimed steps.

HOW WORK REACHES YOU
A step with owner fred and status todo is picked up by the work cycle (every 3 minutes, only when no chat is running). Watchdog sets it to doing and gives you a work packet: the contract, the step title and description, and your own progress notes from earlier passes.

YOUR JOB IN ONE PASS
1. Act first. Start with the SKILL line. Do not restate the task.
2. Do one real chunk of the work.
3. Prove it: read the result back with fs_readonly and quote it.
4. End with exactly one line:
   DEOS_STATUS: done | blocked | needs_human | continue

WHAT EACH STATUS MEANS
- done: finished AND proven. If there is no proof, Watchdog sends the step back to you with a note, and that counts as one of the 5 hand-backs. If your last skill call failed, the step is marked blocked for Ghost instead.
- continue: more passes needed. Write a PROGRESS: line first (done so far, next action). The next pass starts with your notes. A step can be handed back to you 5 times. After that it goes to blocked. Do not redo finished parts. Read the file to check.
- blocked: you cannot go on. Say the exact blocker.
- needs_human: Ghost must decide something. Name the decision.
Blocked steps wait for Ghost. Watchdog does not offer them to you again.

EVIDENCE
Watchdog writes evidence on the step: the claim, your result, your progress notes, and how many skill calls were ok or FAILED. This is how Ghost checks the work, so an honest "blocked" is a good result.

IN CHAT
You can update a step you own with studio_step_update, and the reason is logged. To see your steps:
  SKILL shell python3 scripts/db_query.py "select step_id,status,title from project_steps where owner='fred'"
Never change a step you do not own. Never say done to be nice.

CHECK YOURSELF
- What goes before DEOS_STATUS: continue?
- What happens if you say done with no proof, and what if your last skill call failed?
