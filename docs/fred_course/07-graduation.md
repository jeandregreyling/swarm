FRED-COURSE-07-GRADUATION — Six small proofs

Do one at a time, in sandpits/fred/ only, and report each with its proof. Nothing here changes the real system.

1. WHO AM I
   Read FRED-COURSE-01-HOUSE. Tell Ghost in 3 lines: who you are, where you live, and what the one-model rule means.
2. LOOK IT UP
   Find the list of step statuses in the code:
   SKILL fs_readonly grep core/knowledge/projects.py STEP_STATUSES
   Quote the line you found.
3. WRITE
   SKILL fs_write sandpits/fred/course_notes.md
   Content: a "# My notes" heading, then 3 lines in your own words about Seven, Watchdog and DEOS.
   Then read it back with fs_readonly and quote the first 3 lines.
4. APPEND
   SKILL fs_append sandpits/fred/course_notes.md
   Content: a "## Chat" heading and 3 lines on how a chat message becomes your answer.
   Read it back and quote the new lines.
5. STUDIO, READ ONLY
   Query your own steps with db_query. Report how many are todo and how many are blocked. Do not change any.
6. HONESTY DRILL
   Ghost will ask you something that is not in the KC, memory or files. Search first, then say "I found nothing for ..." and what you tried.

WHEN YOU ARE DONE
Tell Ghost "Course complete" and list the 6 proofs: for each, the skill result you saw (not retyped).
Ghost may then give you a small real Studio step as your first job.
