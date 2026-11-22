# Potato Farm multi-node and tile-system sweep - spec and checklist

Studio step S-86F22E2948 (plan P-2AB8250A87). Source: POTATO-00..09 and the 15 tile-sweep items in P-94531FE267 (all skipped there, none built).
This is the single checklist. An item is ticked only when its check has been run and recorded as a Studio note on S-86F22E2948.

## Part A - Potato Farm multi-node (build order)

- [ ] **Potato Farm source-of-truth inventory and blocker matrix** (S-POTATO-00-INVENTORY; was: skipped)
  Requirement: Audit live Hive nodes/jobs, chat tables, KC tables, app shells, installers, App Center rows, and stale recovery/job records. Produce a gap matrix that states what is real, what is placeholder, and what blocks shared use across Linux, Android, Windows, and macOS.
  Check: a test in tests/ or a command that shows it working on this machine; none exists yet - write it first.

- [ ] **Design shared sync contracts for chats, KC, agents, and node identity** (S-POTATO-01-CONTRACTS; was: skipped)
  Requirement: Create versioned contracts for node identity, sync cursor, chat thread/message events, KC record events, agent capacity snapshots, and Studio evidence. Define idempotency keys, revision/tombstone behavior, and conflict rules before client implementation.
  Check: a test in tests/ or a command that shows it working on this machine; none exists yet - write it first.

- [ ] **Build leader sync API foundation** (S-POTATO-02-SERVER-SYNC; was: skipped)
  Requirement: Add authenticated leader endpoints for node app bootstrap, sync pull/push, app health, and sync backlog. Store sync events/cursors durably without breaking existing Hive, Chat, KC, or Studio APIs.
  Check: a test in tests/ or a command that shows it working on this machine; none exists yet - write it first.

- [ ] **Make chats usable across potatoes** (S-POTATO-03-CHAT-SHARING; was: skipped)
  Requirement: Expose sync-safe chat thread/message APIs so node apps can list threads, open threads, post messages, receive assistant replies, and continue conversations from another potato. Ensure Studio/project metadata is preserved for tracked work.
  Check: a test in tests/ or a command that shows it working on this machine; none exists yet - write it first.

- [ ] **Make Knowledge Center usable across potatoes** (S-POTATO-04-KC-SHARING; was: skipped)
  Requirement: Expose KC search/read/write through sync-safe APIs with source_node, project_id, provenance, category validation, revisions, and conflict-safe updates. Apps must be able to cite KC in chats and attach records to project steps.
  Check: a test in tests/ or a command that shows it working on this machine; none exists yet - write it first.

- [ ] **Unify Agents, Chat, and Potato Farm routing** (S-POTATO-05-AGENT-CAPACITY; was: skipped)
  Requirement: Publish an agent capacity snapshot that includes model/API readiness, node capability, thermal/power policy, active jobs, and recommended route. Chat should package work for leader, farm worker, API agent, or Studio task based on this snapshot.
  Check: a test in tests/ or a command that shows it working on this machine; none exists yet - write it first.

- [ ] **Overhaul Linux/macOS/Windows desktop client** (S-POTATO-06-DESKTOP-CLIENT; was: skipped)
  Requirement: Turn the desktop app from a thin shell into a usable shared client: login/enrol, connection health, chat sync, KC search, node status, sync backlog, app logs, and update/install hooks. Keep Tauri only if the bridge remains reliable.
  Check: a test in tests/ or a command that shows it working on this machine; none exists yet - write it first.

- [ ] **Overhaul Android potato client** (S-POTATO-07-ANDROID-CLIENT; was: skipped)
  Requirement: Build the Android client as a first-class potato: foreground telemetry/sync service, chat screen, KC screen, node status, QR/deep-link enrolment, background-safe queue, and visible battery/thermal policy.
  Check: a test in tests/ or a command that shows it working on this machine; none exists yet - write it first.

- [ ] **Register Potato clients and artifacts in App Center** (S-POTATO-08-APPCENTER; was: skipped)
  Requirement: Create App Center records and targets for desktop, Android, Windows, macOS, Linux, and installer artifacts. Link builds, APKs, installers, docs, and verification runs to P-94531FE267 evidence.
  Check: a test in tests/ or a command that shows it working on this machine; none exists yet - write it first.

- [ ] **Run multi-potato acceptance proof** (S-POTATO-09-E2E-PROOF; was: skipped)
  Requirement: Prove a full scenario: start chat on leader, continue on another potato, cite/update KC, dispatch a farm-backed job, return result to the same thread, and create Studio evidence. This gates any release claim.
  Check: a test in tests/ or a command that shows it working on this machine; none exists yet - write it first.

## Part B - Tile-system sweep

- [ ] **Chat becomes the routing console for Studio and Potato Farm work** (S-7D73416326; was: skipped)
  Requirement: What is there: home chat and full Chat already support threads, local/online agent selection, relay controls, stage traces, attachments, and handoff deadlines. Missing/change: chat does not yet expose a clear "run this through the Potato Farm" path, does not show whether a selected local agent is backed by an available farm node, and does not promote stalled/expensive chats into Studio/Potato work packets by default. Add/check: add a chat action that can package a prompt/thread tail into a hive job or DOES/Potato Farm run; show node availability next to local agents; ensure handoff failures create visible Studio steps/evidence; verify home-chat and full-chat stay in sync after routing.
  Check: a test in tests/ or a command that shows it working on this machine; none exists yet - write it first.

- [ ] **Potato Farm operational routing and recovery** (S-68FDE2C6DE; was: skipped)
  Requirement: What is there: visible farm map, expected node roster, node telemetry, job history, GPU proof display, manual dispatch, quantum chunk button, Android installer surface, and /api/hive nodes/jobs endpoints. Missing/change: live state currently shows potato-2 stale/offline while the home badge still advertises historic GPU OK; there is an old pending benchmark and no clear cleanup/retry/escalation path. The tile is mostly a dashboard, not yet a dependable worker fabric for chats, media, or Studio tasks. Add/check: make stale-vs-historic proof explicit; add retry/cleanup for pending jobs; restore potato-2 worker heartbeat; add chat->farm dispatch and result return; connect DOES pipeline runs to 
  Check: a test in tests/ or a command that shows it working on this machine; none exists yet - write it first.

- [ ] **Agents and Local AI should reflect farm-backed capacity** (S-84F367B310; was: skipped)
  Requirement: What is there: Agents tile manages roster/skills/local AI links and Local AI exposes Ollama/LM Studio controls and quick prompts. Missing/change: agent availability is not clearly tied to node resources, loaded models, farm policies, thermal state, or whether a local model should run on the leader versus a farm worker. Add/check: group agents by execution backend; show node/model health and keep-warm/unload controls in one place; expose fallback routing when a local agent is unavailable; feed these signals into Chat agent selection and Potato Farm dispatch.
  Check: a test in tests/ or a command that shows it working on this machine; none exists yet - write it first.

- [ ] **Studio project board should be the destination for every tile action** (S-76237F9E88; was: skipped)
  Requirement: What is there: Studio has projects, proposals, Git, media linkage, evidence, Test Lab, and step tracking. This project already has release-readiness rows. Missing/change: many tile actions still feel local-only: App Center, Chat handoffs, Potato jobs, Media renders, watched-topic evidence, and Money Hub checks are not uniformly represented as Studio steps/evidence. Add/check: add a shared helper/API contract for tiles to create/update project steps and evidence; add visible "tracked in Studio" affordances for Chat, Potato Farm, Media Center, Tasker, Money Hub, Feeds, and App Center; verify records/KC mirroring for each.
  Check: a test in tests/ or a command that shows it working on this machine; none exists yet - write it first.

- [ ] **Knowledge, Files, Library, and Tasker need one KC-driven bus** (S-F7C134D9C6; was: skipped)
  Requirement: What is there: Knowledge Center hosts files/docs/memory/library; Tasker is nested from Knowledge; watched-topic APIs and evidence exist; project docs and swarm_knowledge are live tables. Missing/change: KC is not yet the obvious command bus that pushes interests into Tasker, Chat context, Money Hub, Feeds, App Center, and Potato Farm jobs. Add/check: finish the KC interest bus contract; surface watched-topic evidence beside project docs; let Chat cite and update KC records; make Tasker scheduled runs write back to the owning project and KC without loose notes.
  Check: a test in tests/ or a command that shows it working on this machine; none exists yet - write it first.

- [ ] **App Center must have real artifacts and project links** (S-E9821587D0; was: skipped)
  Requirement: What is there: App Center API is loaded and the Studio project already has an App Center artifact-trail step. Missing/change: /api/app-center/projects currently returns count=0, so the tile cannot demonstrate build/install/release value for Seven Android, hive installers, or internal apps. Add/check: register current app artifacts, especially Seven Android/hive installers; link each artifact to Studio project targets and KC docs; show build status, install URL, owner project, and latest verification evidence.
  Check: a test in tests/ or a command that shows it working on this machine; none exists yet - write it first.

- [ ] **Media Center handoffs should use Chat, Studio, KC, and Potato Farm** (S-BAAE9C22D8; was: skipped)
  Requirement: What is there: Media Center has a DAW-style shell, project linkage, queue/review/handoff concepts, and real local preview paths. Missing/change: render/compile routing is not yet visibly choosing between local model, remote swarm, Potato Farm worker, or provider handoff; Chat cannot naturally turn a media idea into a tracked farm-backed media run. Add/check: add chat action intents for media project creation/routing; expose Potato Farm as a render target when suitable; ensure every render queue item writes Studio evidence and KC provenance; verify handoff manifest links back to project steps.
  Check: a test in tests/ or a command that shows it working on this machine; none exists yet - write it first.

- [ ] **Monitor, Trace, Health Digest, and backups need one operator view** (S-B98A4EFF2C; was: skipped)
  Requirement: What is there: Monitor, Trace, Health Digest, trace badges, system health endpoints, and the architecture self-test exist. Missing/change: failures are spread out. Current self-test reports stale backup and tile-loader regressions, but the home tiles do not make those release blockers obvious. Add/check: merge or cross-link Monitor/Trace/Health Digest; surface backup age, failed architecture checks, chat job state, and Potato Farm stale nodes in one operator lane; create/refresh Studio blockers automatically when release checks fail.
  Check: a test in tests/ or a command that shows it working on this machine; none exists yet - write it first.

- [ ] **Hidden wishlist pillar loaders must be fixed or formally retired** (S-35997D7448; was: skipped)
  Requirement: What is there: Cyber/Financial/Trading/Business are hidden marker tiles and their visible UX moved into Vortex or Show Me The Money. Missing/change: architecture self-test reports missing loader branches for wishlist-business, wishlist-cyber, wishlist-financial, and wishlist-trading. Either they still need valid loaders, or the test/contract should understand that they are marker-only. Add/check: decide marker-only versus live tile contract; update loader branches or SELF_INIT_TILES/test allow-list accordingly; verify no dead hidden tile can break window opening, Spotlight, or wishlist registry.
  Check: a test in tests/ or a command that shows it working on this machine; none exists yet - write it first.

- [ ] **Show Me The Money should close the loop with KC, Tasker, and farm signals** (S-1B90B67986; was: skipped)
  Requirement: What is there: Money Hub combines financial, trading, business, NASDAQ/ASX feeds, and a Tasker enablement path; market_watch can include Potato Farm and App Center readiness signals. Missing/change: it is still more of a dashboard/newsletter path than an action loop that can create trades/research tasks, assign analysts, or dispatch compute. Add/check: wire hub findings into KC interests, Tasker watched topics, Studio steps, and Chat prompts; include Potato Farm capacity in daily readiness; verify newsletter provenance uses valid KC categories and project docs.
  Check: a test in tests/ or a command that shows it working on this machine; none exists yet - write it first.

- [ ] **Email, Feeds, and Access should become trusted intake routes** (S-94439A14C3; was: skipped)
  Requirement: What is there: Email tile, Gmail labels, sender trust, feeds, and Access permissions exist. Missing/change: incoming email/feed items are not consistently transformed into project proposals, watched topics, chat context, or farm-backed work. Access controls are not visibly applied to cross-tile actions. Add/check: add intake rules that classify trusted senders/feeds into Studio/KC/Tasker; show why an item is trusted or blocked; let Chat reference intake items; ensure Potato Farm dispatch requires a trusted action path.
  Check: a test in tests/ or a command that shows it working on this machine; none exists yet - write it first.

- [ ] **Vortex and Cyber Security should show state, risk, and recovery paths** (S-F3AC8A3D5C; was: skipped)
  Requirement: What is there: Vortex carries state timeline behavior and Cyber is nested/hidden as part of the wishlist pillar consolidation. Missing/change: risk signals from Trace, Access, Email, Git, Potato Farm, and backups are not yet integrated into an actionable timeline. Add/check: fold cybersecurity/audit events into Vortex with links to Studio blockers; add recovery actions for stale nodes, unsafe Git state, failed backups, and suspicious intake; ensure Chat can explain and update those records.
  Check: a test in tests/ or a command that shows it working on this machine; none exists yet - write it first.

- [ ] **Terminal and Git should create evidence, not invisible side effects** (S-A98FBEC858; was: skipped)
  Requirement: What is there: Terminal tile, Studio Git controls, Git status APIs, and direct shell execution are available. Missing/change: user-visible commands and Git actions do not always leave a project-scoped trail; Potato Farm git.sync exists as a task type but is not clearly tied to guarded Studio Git flows. Add/check: add evidence capture from terminal/Git actions into the active project when launched from a tracked task; route git.sync through safe Studio Git checks; show dirty-worktree and branch state before farm/node sync.
  Check: a test in tests/ or a command that shows it working on this machine; none exists yet - write it first.

- [ ] **Tile shell, Spotlight, Manual, and contextual help need consistency checks** (S-A1D1B58ED8; was: skipped)
  Requirement: What is there: home tile grid, Spotlight launcher, contextual help hooks, hide/restore tile UI, and Manual/Guide surfaces exist. Missing/change: nested/hidden tiles make discovery ambiguous, and complex tiles like Media Center, Money Hub, Potato Farm, and Agents need guided entry without adding clutter. Add/check: verify every visible tile opens, focuses existing windows, has help text, has a clear first action, and is reachable from Spotlight; add menu-stepped entry for dense tiles; update KC/Manual as the single source of tile guidance.
  Check: a test in tests/ or a command that shows it working on this machine; none exists yet - write it first.

- [ ] **Release-readiness checks for the whole tile system** (S-871BF7E9F1; was: skipped)
  Requirement: What is there: /_health is healthy and architecture_self_test runs; P-94531FE267 has a 1 June go/no-go row. Missing/change: release readiness is not yet a single repeatable checklist that covers live served UI, tile loaders, Chat, Potato Farm, App Center artifacts, backups, and KC/Studio evidence. Add/check: build a one-command/readable checklist for /_health, /ui served asset checks, architecture self-test, key tile API probes, hive nodes/jobs, App Center count, chat jobs, backup age, and project evidence counts; attach output to the go/no-go step.
  Check: a test in tests/ or a command that shows it working on this machine; none exists yet - write it first.
