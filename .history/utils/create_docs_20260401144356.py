"""
create_docs.py — generate swarm_docs/*.docx with real content.
Run once: python3 create_docs.py
"""
import os
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

DOCS_DIR = os.path.join(os.path.dirname(__file__), 'swarm_docs')
os.makedirs(DOCS_DIR, exist_ok=True)


def doc(filename, title, sections):
    """sections = list of (heading, body_text_or_list_of_strings)"""
    d = Document()
    # Title
    h = d.add_heading(title, level=0)
    h.alignment = WD_ALIGN_PARAGRAPH.LEFT
    for heading, body in sections:
        d.add_heading(heading, level=1)
        if isinstance(body, list):
            for line in body:
                if line.startswith('• '):
                    d.add_paragraph(line[2:], style='List Bullet')
                elif line.startswith('  – '):
                    p = d.add_paragraph(line[4:], style='List Bullet 2')
                else:
                    d.add_paragraph(line)
        else:
            d.add_paragraph(body)
    d.save(os.path.join(DOCS_DIR, filename))
    print(f'  wrote {filename}')


# ── 00_overview.docx ─────────────────────────────────────────────────────────
doc('00_overview.docx', 'Seven\'s Swarm — Overview', [
    ('What is it?', [
        'Seven\'s Swarm is a personal AI assistant running entirely on local hardware in Melbourne, Australia.',
        'It receives questions via email (Gmail) and Telegram, routes them through a pipeline of specialised AI agents, and replies with synthesised answers.',
        'There is no cloud dependency — all models run locally via Ollama. The Anthropic API (Ghost Circle) is the only optional external call, used only when Gemma escalates.',
    ]),
    ('Hardware — seven-potato', [
        '• Dell OptiPlex 7090 — hostname: seven-potato',
        '• CPU: Intel Core i5-10500 (6 cores, 12 threads)',
        '• RAM: 32 GB DDR4 + 128 GB swap on fast NVMe = ~160 GB effective memory',
        '• nvme0n1p3 (232 GB, 31.6 GB/s): swap + all Ollama models (symlinked from here)',
        '• nvme1n1p1 (469 GB, 15.8 GB/s): Linux Mint 22.3 OS + all swarm code at /home/seven/swarm/',
        '• nvme0n1p1: EFI partition — NEVER TOUCH',
        '• OS: Linux Mint 22.3, kernel 6.17',
        '• Tailscale: private network access to dashboard on port 5050',
    ]),
    ('The Vision', [
        'A functional, always-on personal AI assistant that knows its owner, remembers everything, can act in the world, and gets smarter over time.',
        '',
        'Long-term goals:',
        '• Agents with idle curiosity — proactive research and surfacing insights without being asked',
        '• Premium API connections — Ghost Circle (Claude), optionally GPT-4 for comparison',
        '• Mobile dashboard — a clean mobile interface for Ghost on the go',
        '• Discord integration (RL-023)',
        '• More skills: calendar, reminders, smart home',
    ]),
    ('How it was built', [
        'Collaboratively between Ghost and Nine (Claude Sonnet 4.6) over a series of sessions.',
        'The VS Code Claude extension and browser Claude are the same model with no shared memory — Ghost is the continuity between sessions.',
        'Each session has a PROJECT.md update and a memory update to carry context forward.',
    ]),
    ('Services', [
        '• swarm-listener — Gmail Push + email pipeline (systemd)',
        '• swarm-telegram — @Seven_FridaysBot Telegram bot (systemd)',
        '• swarm-terminal — dashboard web UI on port 5050 (systemd)',
    ]),
])

# ── 01_agents.docx ───────────────────────────────────────────────────────────
doc('01_agents.docx', 'Agents', [
    ('Overview', [
        'Seven\'s Swarm has seven named agents, each running a different Ollama model with its own role, temperature, and system prompt.',
        'Agents are not separate processes — they are function calls to ollama.chat() inside orchestrator.py, each with their own model and prompt.',
    ]),
    ('Gemma — Director (gemma3:latest, temp 0.3)', [
        'Role: Orchestrator. Reads the outputs of all other agents and makes the final verdict.',
        'Responsibilities:',
        '• FL-001 routing: classifies every question (NEEDS_WEB, IS_SAP, IS_SYSTEM, IS_IDENTITY, NEEDS_BROWSER, NEEDS_SHELL, AGENTS, MODE)',
        '• Final synthesis: reads LLaMA and Qwen answers, writes the definitive Gemma response',
        '• Debate judging: when MODE=debate, Gemma reads both challenge rounds and declares a winner',
        '• SAP synthesis: reads Eight\'s three-voice pipeline output and writes a clean answer',
        'Temperature 0.3: low for reliable, consistent routing and synthesis.',
    ]),
    ('LLaMA — Researcher (llama3.2:latest, temp 0.6)', [
        'Role: Fast first-pass researcher.',
        'Responsibilities:',
        '• Stage 1: first agent called, gives a quick answer using web results and memory',
        '• Debate R1: states its position in debate mode',
        '• Debate R2: challenge round — reads Qwen\'s position and responds',
        'Temperature 0.6: medium, useful and coherent without hallucinating.',
    ]),
    ('Qwen — Analyst (qwen2.5:latest, temp 0.7)', [
        'Role: Deep analyst. Called in Stage 2 alongside Gemma.',
        'Responsibilities:',
        '• Provides a deeper, more analytical take than LLaMA',
        '• Debate R1: states its position',
        '• Debate R2: challenge round — reads LLaMA\'s position and responds',
        'Temperature 0.7: higher for more original, exploratory analysis.',
    ]),
    ('Librarian — Archivist (qwen:latest, temp 0.1)', [
        'Role: Gatekeeper, tagger, triage agent.',
        'Responsibilities:',
        '• Email triage: auto-decides ANSWER or IGNORE for unknown email senders',
        '• Ticket close: tags closed tickets with 3-5 keyword tags',
        '• IS_SYSTEM routing: answers system health questions using injected live context',
        'Temperature 0.1: very low for consistent, precise classification and tagging.',
    ]),
    ('Duck — Sanity Checker (qwen:latest, temp 0.1)', [
        'Role: Post-ticket quality gate.',
        'Responsibilities:',
        '• Runs after every ticket close',
        '• Reads the question and Gemma\'s final answer',
        '• Returns YES (answer addressed the question) or NO (did not)',
        '• Result stored in duck_log and shown on every ticket',
        'Temperature 0.1: strict binary verdict — no creativity needed.',
    ]),
    ('Sniffles — Auditor (deepseek-r1:7b, temp 0.1)', [
        'Role: Pattern detective. Watches sandpit operations for anomalies.',
        'Responsibilities:',
        '• Audits sandpit_log entries for suspicious patterns',
        '• Writes to sniffer_memory table with pattern_type and escalation_level',
        '• Never interrupts an active pipeline',
        'Temperature 0.1: analytical, not creative.',
    ]),
    ('Eight — SAP Specialist (qwen2.5:latest, temp 0.7)', [
        'Role: Deep SAP HCM/ABAP expert. Activated when IS_SAP=yes.',
        'Responsibilities:',
        '• Three-voice pipeline: Functional Consultant → Technical Consultant → Devil\'s Advocate',
        '• Each voice is a separate qwen2.5 call with a specialised system prompt',
        '• Gemma reads the three voices and writes the final SAP answer',
        '• Has its own memory table (memory_eight) and Tavily web search',
        'Pipeline duration: 8-12 minutes on this hardware (4 sequential qwen2.5 calls).',
        'Temperature 0.7: higher for nuanced, domain-specific reasoning.',
    ]),
])

# ── 02_pipeline.docx ─────────────────────────────────────────────────────────
doc('02_pipeline.docx', 'Pipeline Flows', [
    ('Email Pipeline (listener.py)', [
        'Trigger: Gmail Push Notification (Pub/Sub) or 5-minute safety-net poll.',
        '',
        'Step 1 — Classification:',
        '• Sender looked up in trusted_senders and notification_senders tables',
        '• Trusted: full pipeline fires immediately',
        '• Notification: silent filing only (no response)',
        '• Unknown: Librarian triage — qwen:latest decides ANSWER or IGNORE in ~2s',
        '  – ANSWER: falls through to full pipeline',
        '  – IGNORE: Ghost gets a brief "ignored" email with reason',
        '',
        'Step 2 — Queue intake:',
        '• queue_manager.intake() creates a queue entry and returns position',
        '',
        'Step 3 — Ticket creation:',
        '• ticket.create() creates a ticket record',
        '• conv_id from new_conversation() used as ticket base',
        '',
        'Step 4 — Stage 1 (orchestrator.consult_stage1):',
        '• Gemma runs FL-001 routing',
        '• If NEEDS_WEB: internet.search_web() fires (DDG for LLaMA)',
        '• LLaMA answers with web context',
        '',
        'Step 5 — Stage 2 (orchestrator.consult_stage2):',
        '• If is_sap: Eight three-voice pipeline fires',
        '• Else: Qwen analyses, optional debate round if MODE=debate',
        '• Gemma synthesises final verdict',
        '',
        'Step 6 — Close:',
        '• librarian_close(): Librarian tags the ticket, writes to memory',
        '• Duck runs on_queue_clear() after queue empties',
        '',
        'Reply: send_reply() sends the answer back to the sender\'s email.',
    ]),
    ('Terminal / Dashboard Pipeline', [
        'Same pipeline as email but initiated from the web UI.',
        'No email send at the end — answer streamed back to browser via SSE.',
        'Source field on conversation set to "terminal" instead of "email".',
        'ticket_number format: TICKET-{conv_id}',
    ]),
    ('Telegram Pipeline (fridays/telegram_bot.py)', [
        'Trigger: message received by @Seven_FridaysBot via polling.',
        '• Trusted user: full pipeline, intermediate LLaMA result sent mid-pipeline',
        '• Unknown user: pipeline fires directly (no trust gate — bot URL is private)',
        '• SKILL command: intercepted before pipeline, fridays/skills.py handles it',
        '• SCHEDULE command: intercepted before pipeline, fridays/scheduler.py handles it',
        'ticket_number format: TG-{conv_id}',
    ]),
    ('Eight SAP Pipeline', [
        'Triggered when Gemma routing returns IS_SAP=yes.',
        '',
        'Voice 1 — Functional Consultant:',
        '• Answers from a business/functional perspective',
        '• Uses eight\'s memory (memory_eight) and Tavily SAP search',
        '',
        'Voice 2 — Technical Consultant:',
        '• Answers from a technical/ABAP perspective',
        '• Reads Voice 1 output as context',
        '',
        'Voice 3 — Devil\'s Advocate:',
        '• Challenges both voices, identifies gaps and risks',
        '• Reads Voice 1 and Voice 2 as context',
        '',
        'Synthesis:',
        '• Gemma reads all three voices and writes the definitive SAP answer',
        '• Answer sent back via email/Telegram/terminal',
        '',
        'Duration: 8-12 minutes on seven-potato (4 × qwen2.5 calls).',
    ]),
    ('Scheduled Tasks (fridays/scheduler.py)', [
        'check_due() called every listener loop.',
        'Action types: QUESTION (fires full pipeline), SHELL (runs shell skill), REMIND (sends email).',
        'Schedules: daily HH:MM, weekly DAY HH:MM, hourly, interval N (minutes), once DATE TIME.',
        'Tasks stored in scheduled_tasks table.',
    ]),
])

# ── 03_database.docx ─────────────────────────────────────────────────────────
doc('03_database.docx', 'Database — All 22 Tables', [
    ('Overview', [
        'Single SQLite database at /home/seven/swarm/swarm_memory.db.',
        'All access through database.py helper functions.',
        'Row factory: sqlite3.Row — all rows accessible as dicts.',
        '49 tables across 5 functional areas.',
    ]),
    ('Conversation & Message Tables', [
        '• conversations — one row per question session. Fields: id, title, source (email/terminal/telegram), sender, created_at.',
        '• messages — every agent utterance. Fields: id, conversation_id, from_agent, to_agent, content, message_type (chat/debate_r1/debate_r2), created_at.',
    ]),
    ('Ticket Tables', [
        '• tickets — one per pipeline run. Fields: ticket_number, status (open/closed/failed), duck_result, gemma_routing (JSON), question, tags, sender_email, final_answer, sniffles_result, created_at, closed_at.',
        '• ticket_notes — agent notes attached to tickets. Fields: ticket_id, agent, note_type, content, created_at.',
    ]),
    ('Memory Tables', [
        '• memory — shared verified memory pool. All agents can write here. Fields: id, agent, subject, content, tags, importance (1-10), archived, created_at.',
        '• memory_llama — LLaMA\'s private memory. Same schema as memory.',
        '• memory_qwen — Qwen\'s private memory. Same schema as memory.',
        '• memory_gemma — Gemma\'s private memory. Note: no archived column.',
        '• memory_eight — Eight\'s SAP knowledge base. Same schema as memory.',
        '',
        'Memory design principles:',
        '• Importance 1-10: 9-10 = critical facts, 7-8 = important, 5-6 = useful, 3-4 = context, 1-2 = ephemeral',
        '• Librarian writes tags and importance on ticket close',
        '• Archived = 1 means soft-deleted (not shown in searches)',
    ]),
    ('Queue & Trust Tables', [
        '• queue — pending questions. Fields: id, sender, display_name, question, status (pending/processing/completed/failed), position, created_at.',
        '• trusted_senders — full pipeline access. Format: email address or telegram:{chat_id}.',
        '• notification_senders — silent filing only, no response.',
        '• pending_emails — emails held awaiting action.',
        '• approval_tokens — one-click action tokens for Ghost approval links.',
    ]),
    ('Logging & Audit Tables', [
        '• duck_log — every Duck verdict. Fields: ticket_number, question, answer, result (YES/NO), reason, created_at.',
        '• sniffer_memory — Sniffles patterns. Fields: agent_name, pattern_type, description, occurrence_count, escalation_level.',
        '• sandpit_log — every file/shell/browser operation by Fridays agents.',
        '• ghost_circle — swarm-wide event log. Fields: entry_type, source, content, ticket_ref, severity (info/warning/critical).',
        '• claude_log — every Ghost Circle (Claude API) call. Fields: ticket_id, ticket_number, problem_type, query_sent, response, model_used, tokens_used.',
        '• activity_log — live event bus. Fields: service, event, detail, created_at. Drives the Monitor tab.',
    ]),
    ('SAP & System Tables', [
        '• agents — agent registry (name, model, role, status).',
        '• system_stats — periodic hardware snapshots.',
        '• project_docs — project documentation entries.',
        '• scheduled_tasks — scheduled tasks. Fields: name, schedule, action_type, action_data, created_by, next_run, enabled.',
    ]),
])

# ── 04_files.docx ─────────────────────────────────────────────────────────────
doc('04_files.docx', 'File Reference', [
    ('Core Files (/home/seven/swarm/)', [
        '• config.py — all secrets and configuration. TELEGRAM_TOKEN, GHOST_EMAIL, API keys. Never commit or share.',
        '• database.py — all DB access functions. 600+ lines. Single source of truth for schema (SCHEMA constant).',
        '• orchestrator.py — the brain. AGENTS dict, TEMPERATURES dict, SYSTEM_PROMPTS. ask_agent(), consult_stage1(), consult_stage2(), run_debate().',
        '• listener.py — email loop. Gmail Push handler, IMAP sweep, librarian_triage(), process_emails(), handle_moderator_command().',
        '• terminal.py — Flask web UI server on port 5050. All /api/* endpoints. Kill switches, temperature overrides.',
        '• duck.py — on_queue_clear() fires Duck after every completed ticket.',
        '• sniffer.py — Sniffles audit loop.',
        '• monitor.py — get_system_status() using psutil.',
        '• internet.py — web search. search_web() calls DDG/Serper/Tavily based on agent.',
        '• claude_api.py — Ghost Circle. ask_claude(), build_ghost_circle_context(), _log_call().',
        '• email_handler.py — send_reply(), parse Gmail messages.',
        '• gmail_push.py — Gmail Pub/Sub push listener.',
        '• gmail_auth.py — OAuth2 credentials refresh.',
        '• queue_manager.py — intake(), get_queue_depth(), mark_processing().',
        '• ticket.py — create(), librarian_close(), set_routing().',
        '• sandpits.py — get_sandpit_stats(), sandpit directory management.',
        '• eight.py — SAP three-voice pipeline.',
    ]),
    ('Fridays Action Layer (/home/seven/swarm/fridays/)', [
        '• file_agent.py — sandpit file operations. Levels 0-3. create, read, write, delete, list.',
        '• browser_agent.py — Playwright headless browser. browse(url). 8000 char cap. Sandpit logged.',
        '• shell_agent.py — whitelisted shell commands. ~30 regex patterns. Levels 0/2/4 trust. 30s timeout.',
        '• scheduler.py — task scheduler. parse_schedule_command(), add_task(), list_tasks(), disable_task(), check_due().',
        '• skills.py — central skill registry and dispatcher. 8 skills: shell, browse, file_read, file_write, search, remind, schedule, list.',
        '• telegram_bot.py — @Seven_FridaysBot. Full pipeline + SKILL + SCHEDULE commands.',
    ]),
    ('Templates (/home/seven/swarm/frontend/templates/)', [
        '• terminal_base.html — THE single active UI template. All CSS, HTML, and JS in one file. Served via theme_engine.py. All views: Chat, Terminal, Memory, Monitor, Docs, Skills, Tickets, Studio, Vortex, Access.',
    ]),
    ('Services (/etc/systemd/system/)', [
        '• swarm-listener.service — runs listener.py. Auto-restart on failure.',
        '• swarm-telegram.service — runs fridays/telegram_bot.py.',
        '• swarm-terminal.service — runs terminal.py (Flask). Port 5050.',
    ]),
    ('Data (/home/seven/swarm/)', [
        '• swarm_memory.db — the SQLite database. 49 tables.',
        '• swarm_docs/ — this document repository. 12 .docx reference files.',
        '• sandpits/ — agent workspace directories (L0-L4 trust levels).',
        '• credentials/ — Gmail OAuth2 credentials (never commit).',
    ]),
])

# ── 05_access_control.docx ───────────────────────────────────────────────────
doc('05_access_control.docx', 'Access Control', [
    ('Email Trust Levels', [
        'trusted_senders: full pipeline. Question → queue → Stage 1 → Stage 2 → reply.',
        'notification_senders: silent filing. Email received, filed, no response sent.',
        'Unknown sender: Librarian triage (qwen:latest, temp 0.1). Decision:',
        '  – ANSWER: full pipeline fires immediately',
        '  – IGNORE: Ghost receives brief "ignored" email with reason',
        '',
        'Format in trusted_senders: plain email address (e.g. ghost@example.com)',
    ]),
    ('Telegram Trust', [
        'trusted_senders: format telegram:{chat_id} (e.g. telegram:8735763890)',
        'Unknown Telegram user: pipeline fires directly (no trust gate).',
        '  Rationale: knowing the bot URL is already a gate. Anyone who finds it is presumed to have a reason.',
        '  Ghost gets a notify email about unknown users (with TRUST/NOTIFY/IGNORE links).',
    ]),
    ('Ghost Commands (email reply to swarm)', [
        'TRUST <email> — add to trusted_senders',
        'NOTIFY <email> — add to notification_senders',
        'IGNORE <email> — no action, sender stays unknown',
        'SCHEDULE <schedule> <action> <data> — create a scheduled task',
        'SCHEDULE LIST — list all scheduled tasks',
        'SCHEDULE CANCEL <id> — disable a scheduled task',
        'SKILL <name> <args> — run a skill from email',
    ]),
    ('Sandpit Trust Ladder (Fridays)', [
        'Level 0 — Read-only. List and read files in sandpit. No writes.',
        'Level 1 — Write to sandpit/L1/ only.',
        'Level 2 — Write to sandpit/L2/. Can execute whitelisted shell commands.',
        'Level 3 — Write to sandpit/L3/. Can browse web.',
        'Level 4 — Write to sandpit/L4/. Full whitelisted shell + elevated commands.',
        '',
        'All sandpit operations logged to sandpit_log. Sniffles audits for anomalies.',
    ]),
    ('Dashboard Access', [
        'Port 5050 — accessible via Tailscale only (private network).',
        'No authentication — Tailscale network membership is the gate.',
        'Ghost Circle (Claude API) calls are logged to ghost_circle and claude_log.',
    ]),
])

# ── 06_ghost_circle.docx ─────────────────────────────────────────────────────
doc('06_ghost_circle.docx', 'Ghost Circle — Claude API Advisor', [
    ('What is Ghost Circle?', [
        'Ghost Circle is the advisor layer that connects Seven\'s Swarm to the Anthropic Claude API (claude-sonnet-4-6).',
        'It is called by Gemma when the local models cannot reach a confident answer.',
        'Claude acts as mentor, not driver — it advises Gemma, who makes the final call.',
        'Claude never speaks directly to email senders or Telegram users.',
    ]),
    ('When is it triggered?', [
        '• conflicting_agent_outputs — LLaMA and Qwen contradict each other significantly',
        '• factual_uncertainty — Gemma flags low confidence in a factual claim',
        '• sap_escalation — Eight\'s pipeline produces an uncertain or contradictory result',
        '• routing_unclear — FL-001 routing is ambiguous',
        '• identity_question — question about the swarm itself or its capabilities',
        '• ethical_edge_case — question touches on sensitive or ambiguous ethical territory',
        '• connection_test — test call to verify the API key is working',
    ]),
    ('Caching', [
        'Gemma checks claude_log for a recent answer to the same problem_type before calling the API.',
        'If a recent answer exists, it is reused without an API call.',
        'This prevents redundant API calls and controls cost.',
    ]),
    ('Implementation (claude_api.py)', [
        '• ask_claude(problem_type, question, ticket_number, additional_context)',
        '• build_ghost_circle_context() — injects full swarm state: ghost_circle entries, Duck stats, Sniffles patterns, ticket detail',
        '• _log_call() — writes to both claude_log and ghost_circle tables',
        '• CLAUDE_MODEL = "claude-sonnet-4-6"',
        '• Max tokens: 1024 per call',
    ]),
    ('Database Tables', [
        '• claude_log — every API call. Fields: ticket_id, ticket_number, problem_type, query_sent, response, model_used, tokens_used, created_at.',
        '• ghost_circle — swarm-wide event log. Claude advisories written here with entry_type="claude_advisory".',
    ]),
    ('Setup', [
        '1. Add ANTHROPIC_API_KEY to /etc/environment',
        '2. Source: source /etc/environment',
        '3. Test: python3 ~/swarm/claude_api.py',
        '4. Should print: Ghost Circle connected + response',
        '',
        'Cost: claude-sonnet-4-6 at ~$3/M tokens. A typical Ghost Circle call uses ~500-800 tokens.',
    ]),
])

# ── 07_sessions.docx ─────────────────────────────────────────────────────────
doc('07_sessions.docx', 'Build Log — Sessions 1–10', [
    ('Sessions 1–3: Foundation', [
        'Session 1: Project inception. Database schema. Basic email loop. Gemma + LLaMA wired.',
        'Session 2: Qwen added. Debate mode. FL-001 routing first version.',
        'Session 3: Librarian (tagger). Duck (sanity checker). Sniffles (auditor). Memory tables.',
    ]),
    ('Sessions 4–6: Pipeline hardening', [
        'Session 4: Eight SAP specialist. Three-voice pipeline. memory_eight.',
        'Session 5: Independent web search per agent (DDG/Serper/Tavily). Eight Tavily SAP search.',
        'Session 6: RL-015 independent search fully wired. RL-016 debate wired. RL-017 sandpits.',
    ]),
    ('Sessions 7–8: Access & Infrastructure', [
        'RL-011: Gmail Push Notifications. pull-based Pub/Sub + startup IMAP sweep + 5-min safety net.',
        'RL-012: Swarm Terminal. Flask on port 5050. SSE streaming. Dark UI. All current views.',
        'RL-025: One-click approval links (mailto: format). Ghost replies TRUST/NOTIFY/IGNORE.',
        'RL-017b: IS_SYSTEM routing. librarian_health_summary() injected as live context.',
        'RL-017c: Swarm awareness block injected into every build_shared_context() call.',
    ]),
    ('Session 9: Bug Fixes & UAT', [
        '6 bugs patched, 3 missing wires added.',
        'Foundation UAT passed: simulate.py 4/4, 12 emails processed correctly.',
        'SIMULATE=true flag added to listener.py for safe testing.',
    ]),
    ('Session 10: Fridays — The Action Layer', [
        'RL-018: File + browser agent. fridays/file_agent.py (L0-3 sandpit ops). fridays/browser_agent.py (Playwright headless).',
        'RL-019: Shell agent. fridays/shell_agent.py. ~30 whitelisted regex patterns. L0/2/4 trust.',
        'RL-020: Scheduler. Human-readable schedules. SCHEDULE command wired into listener + Telegram.',
        'RL-021: Skills framework. 8 skills. Dashboard Skills tab. /api/skills and /api/skills/run.',
        'RL-022: Telegram bot. @Seven_FridaysBot. Full pipeline + SKILL + SCHEDULE from Telegram.',
        'Dashboard: Ticket detail panel. Monitor tab (SSE activity feed). Memory agent filter.',
        'Librarian triage: unknown email senders auto-answered or ignored by qwen in ~2s.',
        'Telegram unknown sender: trust gate removed, pipeline fires directly.',
        'activity_log table: central event bus driving the Monitor tab.',
        'Agents screen: kill switches + temperature sliders per agent.',
        'Dashboard help modals, ticket/memory delete, Docs tab: this session.',
    ]),
])

# ── 08_roadmap.docx ──────────────────────────────────────────────────────────
doc('08_roadmap.docx', 'Roadmap', [
    ('Done — Phases 1 & 2', [
        '✓ RL-010: SIMULATE=true flag',
        '✓ RL-011: Gmail Push Notifications',
        '✓ RL-012: Swarm Terminal (dashboard)',
        '✓ RL-013: Eight SAP specialist',
        '✓ RL-014: Eight knowledge loader',
        '✓ RL-015: Independent search per agent',
        '✓ RL-016: Debate mode',
        '✓ RL-017: Sandpits + trust levels',
        '✓ RL-017b: IS_SYSTEM routing',
        '✓ RL-017c: Swarm awareness context',
        '✓ RL-018: File + browser agent',
        '✓ RL-019: Shell agent',
        '✓ RL-020: Scheduler',
        '✓ RL-021: Skills framework',
        '✓ RL-022: Telegram bot',
        '✓ RL-025: One-click approval links',
        '✓ Ghost Circle (claude_api.py built, API key activated)',
        '✓ Dashboard: ticket detail, monitor, memory agent filter, agents kill switches + temp sliders',
        '✓ Dashboard: help modals, ticket/memory delete, Docs tab',
    ]),
    ('Pending — Phase 3', [
        '• RL-023: Discord bot — third platform connector',
        '• RL-024: WhatsApp — deferred ("wait till we have friends to share it with")',
        '• Ghost Circle wiring — trigger escalation from orchestrator.py on uncertainty',
        '• BUG-001: mailto: approval links — pending live end-to-end confirmation',
        '• BUG-002: TRUST/NOTIFY/IGNORE email approval flow — broken pipe, deferred',
        '• Mobile dashboard — clean mobile interface for Ghost on the go',
        '• Idle curiosity — agents proactively surface insights without being asked',
        '• Proactive briefing — daily morning summary pushed to Ghost',
    ]),
    ('Long-term Vision', [
        '• Agents with genuine idle curiosity that research topics and surface insights',
        '• A personal knowledge graph that grows with every conversation',
        '• Smart home integration via shell skills',
        '• A mobile app for Ghost (not just a browser view)',
        '• Multi-user support — controlled sharing with selected people',
    ]),
])

# ── 09_constraints.docx ──────────────────────────────────────────────────────
doc('09_constraints.docx', 'The 27 Rules — Constraints That Must Never Be Broken', [
    ('Hardware Rules', [
        '1. NEVER touch nvme0n1p1 — this is the EFI partition. Damage = unbootable machine.',
        '2. Keep OLLAMA_HOST=0.0.0.0 — required for Ollama to accept connections from all interfaces.',
        '3. Swap lives on nvme0n1p3 — do not move or resize without planning for the 128 GB swap.',
        '4. Ollama models live on nvme0n1p3 via symlink — do not break the symlink at /usr/share/ollama/.ollama.',
    ]),
    ('Security Rules', [
        '5. Never commit config.py — it contains TELEGRAM_TOKEN, API keys, and GHOST_EMAIL.',
        '6. Never share config.py contents in any log or output.',
        '7. Dashboard is Tailscale-only — do not expose port 5050 to the public internet.',
        '8. Sandpit operations must be logged — every file/shell/browser action goes to sandpit_log.',
        '9. Shell whitelist must be maintained — shell_agent.py only runs pre-approved regex patterns.',
    ]),
    ('Agent Behaviour Rules', [
        '10. Librarian only receives content to tag — never give Librarian questions that require reasoning.',
        '11. Sniffles never interrupts an active pipeline — it runs only when the queue is clear.',
        '12. Duck runs after every ticket close — it is the quality gate and must not be skipped.',
        '13. Gemma makes the final call — no other agent\'s output goes directly to the user.',
        '14. Claude (Ghost Circle) never speaks to users — its advice is for Gemma only.',
        '15. Eight only fires on IS_SAP=yes — do not route non-SAP questions to Eight.',
    ]),
    ('Database Rules', [
        '16. All DB access through database.py — no raw SQLite calls from other modules.',
        '17. Always use get_connection() — never create a bare sqlite3.connect() call.',
        '18. The schema lives in database.py SCHEMA — do not create tables manually.',
        '19. Never delete from memory directly — use archived=1 for soft delete.',
        '20. claude_log and ghost_circle are append-only — never delete from these tables.',
    ]),
    ('Pipeline Rules', [
        '21. Queue must be managed — stale entries (>2h processing) should be cleaned on startup.',
        '22. Every pipeline call must write to activity_log — the Monitor tab depends on this.',
        '23. ticket_number format: TICKET-{conv_id} for email/terminal, TG-{conv_id} for Telegram.',
        '24. SSE timeout is 900s — Eight pipeline (8-12 min) is within this limit.',
        '25. SIMULATE=true on listener.py — used for safe testing. Never run SIMULATE=true in production.',
    ]),
    ('Build Rules', [
        '26. PROJECT.md must be updated at the end of every session — it is the continuity document.',
        '27. Memory must be updated at the end of every session — swarm_docs/ supplements this.',
    ]),
])

# ── 10_bugs.docx ─────────────────────────────────────────────────────────────
doc('10_bugs.docx', 'Bug Log', [
    ('Active Bugs', [
        'BUG-001: One-click approval links (mailto: format)',
        '  Status: pending live end-to-end confirmation',
        '  Description: Ghost receives an email with TRUST/NOTIFY/IGNORE mailto: links.',
        '  The link pre-fills a reply. Ghost sends the reply. listener.py parses the reply.',
        '  Not yet confirmed working end-to-end in production.',
        '  Priority: Low — Librarian triage (ANSWER/IGNORE) handles unknown senders for now.',
        '',
        'BUG-002: TRUST/NOTIFY/IGNORE email approval flow — broken pipe',
        '  Status: Deferred',
        '  Description: The full TRUST/NOTIFY/IGNORE flow for unknown email senders had a broken',
        '  pipe somewhere between Ghost\'s reply and listener.py parsing it.',
        '  Resolution: Replaced with Librarian auto-triage for email. TRUST/NOTIFY/IGNORE',
        '  commands remain available for manual list management.',
        '  Priority: Low — triage is working well as a replacement.',
    ]),
    ('Fixed Bugs (Session 9)', [
        '6 bugs patched in foundation UAT session. Details in SESSION 9 notes.',
        '3 missing pipeline wires added.',
        'Foundation UAT: simulate.py 4/4, 12 emails processed correctly.',
    ]),
    ('Fixed Bugs (Session 10)', [
        'search skill: No module named search — fixed, uses internet.search_web()',
        'browse skill: too many values to unpack — fixed, browser_agent.browse() returns str not tuple',
        'Memory LLaMA: no results — fixed, _memory_search queries memory_llama table per agent',
        'memory_gemma: no archived column — handled with conditional SQL clause',
        'Telegram unknown sender: still showing TRUST gate — removed gate entirely',
        'Telegram queue position inflation — cleared stale queue entries from prior test sessions',
        'database.py duplicate get_ghost_circle_entries() — second broken definition removed',
    ]),
    ('Known Limitations', [
        'Eight pipeline: 8-12 minutes on this hardware. Users informed via Telegram mid-pipeline message.',
        'Ghost Circle: API key needs credits loaded. Test with: ANTHROPIC_API_KEY=... python3 claude_api.py',
        'Scheduler: no persistence of next_run across service restarts (recalculated from schedule string).',
        'Activity log: no auto-pruning. Will grow indefinitely — add a cleanup job eventually.',
    ]),
])

# ── 00_index.docx ─────────────────────────────────────────────────────────────
doc('00_index.docx', 'Master Index', [
    ('Document Index', [
        '00_overview.docx    — What Seven\'s Swarm is. Hardware. The vision. How it was built.',
        '01_agents.docx      — All 7 agents. Personalities. Models. Temperatures. Responsibilities.',
        '02_pipeline.docx    — Email, Terminal, Telegram, and Eight pipeline flows step by step.',
        '03_database.docx    — All 22 tables. Schema. Memory design principles.',
        '04_files.docx       — Complete file reference. Every .py file and its purpose.',
        '05_access_control.docx — Trust levels. Ghost commands. Sandpit trust ladder.',
        '06_ghost_circle.docx   — Claude API advisor. When triggered. Caching. Setup.',
        '07_sessions.docx    — Build history. Sessions 1-10 chronological.',
        '08_roadmap.docx     — What\'s done. What\'s next. Long-term vision.',
        '09_constraints.docx — 27 rules that must never be broken.',
        '10_bugs.docx        — Active bugs. Fixed bugs. Known limitations.',
    ]),
    ('Quick Reference', [
        'Dashboard: http://seven-potato:5050 (Tailscale)',
        'Telegram bot: @Seven_FridaysBot',
        'DB location: /home/seven/swarm/swarm_memory.db',
        'Services: swarm-listener | swarm-telegram | swarm-terminal',
        'Ollama models: gemma3:latest | llama3.2:latest | qwen2.5:latest | qwen:latest | deepseek-r1:7b',
        'Docs: /home/seven/swarm/swarm_docs/',
    ]),
])

print('\nAll docs created in swarm_docs/')
