# Potato Farm Full Rework Plan

Status: active plan for `P-94531FE267`.
Date: 2026-05-28

## Goal

Make the Potato Farm a real shared-runtime layer, not a proof banner. Linux,
Windows, macOS, and Android nodes must share useful state and capacity with the
leader: chats, Knowledge Center, agent availability, node telemetry, App Center
artifacts, and job handoffs.

## Current Truth

- The leader on `:5050` is healthy.
- One Linux node is live and reporting current telemetry.
- `potato-2` exists as stale Android telemetry with historical Samsung GPU
  proof, but it is currently offline/stale and must not be advertised as live.
- Expected `potato-1`, `potato-3`, and `potato-4` rows are placeholders.
- The active Studio plan is `P-94531FE267` with `S-POTATO-00` through
  `S-POTATO-09`; those steps are still todo.

## Architecture

1. Leader API
   - Own node identity, enrolment, sync clocks, and conflict policy.
   - Expose `/api/hive/nodes`, `/api/hive/jobs`, `/api/hive/sync/*`, and
     `/api/hive/artifacts/*` as the stable contract.
   - Store durable evidence in Studio/KC whenever a node changes capability,
     claims work, or publishes an artifact.

2. Shared State
   - Chat sync: conversations, messages, agent selections, attachments, and job
     status must be readable on every enrolled node.
   - KC sync: docs, facts, project evidence, and search indexes must replicate
     enough metadata for offline/edge use.
   - Agent capacity: Chat and Agents must route by live capability, not stale
     proof rows.

3. Platform Clients
   - Linux: current leader/node agent becomes the reference implementation.
   - Windows: packaged desktop launcher must enrol, report telemetry, and open
     the shared Chat/KC surfaces.
   - macOS: same contract as Windows with platform-specific installer/service.
   - Android: APK must run a foreground service, report fresh telemetry, claim
     TFLite/GPU jobs, and sync chat/KC metadata.

4. App Center
   - Every client build is registered as an artifact with version, platform,
     checksum, source commit, and install status.
   - Potato Farm should link directly to the correct current installer/artifact.

5. Operator UI
   - Potato Farm tile shows fresh/live/stale clearly.
   - No permanent proof banners.
   - Historical proof is visible inside the tile as history, not as current
     runtime status.
   - Chat, Agents, Studio, Monitor, and App Center all link back to the same
     node/capability records.

## Execution Steps

1. `S-POTATO-00-INVENTORY`
   - Build a live node/capability/blocker matrix.
   - Mark stale historical proof separately from live capacity.

2. `S-POTATO-01-CONTRACTS`
   - Finalize sync contracts for chats, KC docs/facts, node identity, artifacts,
     and agent capacity.
   - Add contract tests before client rewrites.

3. `S-POTATO-02-SERVER-SYNC`
   - Implement leader sync APIs and conflict handling.
   - Add KC/Studio evidence writes for sync and handoff events.

4. `S-POTATO-03-CHAT-SHARING`
   - Make conversations and active jobs readable across nodes.
   - Preserve thread identity and attachments.

5. `S-POTATO-04-KC-SHARING`
   - Replicate KC metadata and retrieval pointers across nodes.
   - Keep full document bodies leader-owned until storage policy is clear.

6. `S-POTATO-05-AGENT-CAPACITY`
   - Make Chat and Agents consume live farm capacity.
   - Prevent stale/offline nodes from receiving work.

7. `S-POTATO-06-DESKTOP-CLIENT`
   - Finish Linux, Windows, and macOS desktop clients against the same sync
     contract.
   - Package and register artifacts in App Center.

8. `S-POTATO-07-ANDROID-CLIENT`
   - Rework Android foreground service and GPU/TFLite worker.
   - Ensure stale/offline detection is reliable.

9. `S-POTATO-08-APPCENTER`
   - Publish current installers/APKs with checksums and install routes.

10. `S-POTATO-09-E2E-PROOF`
    - Acceptance proof: start a chat on one node, continue on another, retrieve
      KC context, route an agent job to a live capable node, publish artifact
      evidence, and show it in Studio/KC.

## Acceptance Gate

The rework is not done until all of these pass:

- At least two live nodes enrolled at the same time.
- Android telemetry freshness is under 180 seconds while the APK is active.
- Chat state is visible from leader and one client.
- KC evidence created on one surface is discoverable from another.
- Agents and Chat refuse stale/offline capacity.
- App Center shows current platform artifacts.
- Potato Farm tile distinguishes live capacity from historical proof.
- Studio `P-94531FE267` has evidence rows for every completed step.
