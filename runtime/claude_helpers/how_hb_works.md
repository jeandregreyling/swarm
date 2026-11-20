# How HB works (Hummingbird) - current as of 19 Nov 2026

Written by Claude Code from the Studio practice records (P-2AB8250A87, Practices 128-168) and the code. Newer than older code comments.

## Roles, not names
- APEX is a ROLE: the main worker on the GPU (port 8080, systemd user service apex-server). Any model can play it.
- Fred is the deep thinker on the CPU (fred-cpu:24b = mistral-small 24B). It takes over a step when APEX gets stuck, in a CPU lane, while APEX starts the next step.
- Homework: a small CPU model writes spec cards. Counsel/review: Fred.
- /roles shows who plays which role. core/hb_roles.py.

## Which model plays APEX, and how HB chooses (core/hb_apex_swap.py, Practices 152-161, 165)
- /apex shows the model playing APEX; /apex models lists candidates that fit the 16 GB card; /apex model <name> swaps; /apex back returns.
- A swap edits only the model file (-m), chat template and per-model batch sizes in HB's drop-in
  ~/.config/systemd/user/apex-server.service.d/gpu-offload.conf, backs it up as gpu-offload.conf.before-swap, restarts apex-server,
  proves a test answer works, and rolls back if not. Announced in main chat.
- Before every main-chat APEX turn (frontend/blueprints/chat.py -> hb_apex_swap.route_for):
  1. JD's own pick wins: an @model in the message, or a model switched On in Live status. A model switched Off is never swapped in.
  2. Otherwise HB REVIEWS the question (review()): kind (research or default), its topic words, and how well the Knowledge Centre covers it
     (quick search). It posts one line in main chat: "HB review: research question (...) - <plan> - <model>".
  3. Research questions go to the preferred research model (/apex prefer research <model>; default swift-qwen3.8-27b). HB never swaps back
     by itself, so models do not ping-pong.
- Per-model settings: turn time (27B: 600 s), tool rounds (27B: 9), GPU batch sizes (27B: -b 512 -ub 256 - smaller jobs stop the card's
  compute-ring timeouts). settings_tick() reloads APEX by itself, while idle, when its prescribed settings changed.
- Older code: core/apex_routing.py choose_local_model picks the model NAME for a request by keyword category; the model actually on the card
  is decided by hb_apex_swap as above.
- Benchmark (18 Nov): swift-qwen3.8-27b answered SAP research far better than gpt-oss:20b, at 2-9 minutes per answer.

## GPU guard (core/hb_gpu_guard.py)
- tick(): background-worker requests that failed with ErrorDeviceLost -> restart apex-server (max once per 5 min), prove it answers,
  resume the interrupted tasks.
- spill_tick(): if APEX's buffers spill to system RAM (GTT >= 2 GB), raise the --fit margin and restart while idle.
- reset_tick() (Practice 158): reads the kernel log every minute for "ring reset" / "device wedged"; after one, waits until APEX is idle,
  asks a test answer, and restarts apex-server only if that fails.

## Research (SAP questions)
- Knowledge Centre: 6,074+ SAP notes (sap://note/N), indexed two ways: keywords (core/hb_note_index.py, FTS5) and meaning
  (core/hb_note_vectors.py: ~800-char chunks embedded with nomic-embed-text on the CPU, built in a background thread). knowledge_search
  fuses both (reciprocal rank fusion); each match line carries [document_id N] and, when the title lacks the question's words, the
  passage that says it ("says: ...").
- knowledge_read with a focus shows the paragraphs that mention the question's words (HB fills focus in).
- Research method (core/capability_packs/research.method.v1.json) on APEX's clipboard. HB checks every research answer
  (core/apex_tools.py _grounded): research (two wordings), read (notes actually opened; exact-title note read), KC (held notes not called
  missing), coverage (whole component family, e.g. PY-AU-STP; HB appends what is still missing), content (not titles only), topic (no
  imported topic words), online (search public SAP pages when the notes do not cover it), citation (a note must contain the wage type /
  table it is credited with). These SAP checks run for SAP/payroll questions only (sap_question), not HB or code questions.
- A new research question starts without earlier chat, memory or pinned instructions (chat_continuity.fresh_research); follow-ups keep them.
- Online: web_search (serper first, tavily). core/hb_web_research keeps the SAP pages found (help.sap.com, SAP Community) in the KC
  (subcategory sap-web; Tavily extract, navigation stripped) and queues the SAP notes they cite in the S-user notes job.

## Studio workflow and practices
- Plan P-2AB8250A87. HB drives one GPU step at a time (core/hb_plan_workflow.py) plus a CPU lane for Fred.
- "Practice" steps: Claude Code prepares a tested change set (core/hb_change_sets.py); APEX runs change_set show/apply and run_tests;
  HB auto-accepts on a passing check and commits locally. Every step has "Done when: python -m pytest ..." (a runnable check).
- "Bug:" steps: APEX finds and fixes the bug itself with the bug-fix method (core/capability_packs/bugfix.method.v1.json, Practice 166):
  reproduce, find the cause, check history, failing test first, smallest patch, run the tests, report.
- run_tests auto-creates a Studio case for a step without one; it is not a done criterion (Practice 168).

## Main chat UI
- Live activity: /api/peer/v1/hb/activity returns the task chains AND the plain-text "what the models are doing" lines (Practice 164).
- Thinking bubble shows HB's progress stages; the model's own reasoning is collected while streaming but not displayed.
- A page left open through an HB restart can stop sending: reload it.
