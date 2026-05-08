# Media Center Audit — Consolidation Closeout

> **Scope**: closeout for the 41 [P-10F93B5799] / [P-1BAD468675] linker steps imported
> into P-00221285D1 during the 2026-04-30 consolidation sweep.
> **Method**: code/UI review against the live Media Center surface
> (`frontend/static/js/views/media-center.js`, `frontend/static/css/views/media-center.css`,
> `frontend/blueprints/media_center.py`, `core/media_center/framework.py`).
> **Outcome**: every reviewed concern is implemented or out-of-scope; no follow-up
> packets needed.

## DAW-first workspace (S-A81D210F49 / S-AF59A1DE61)

The composer/editor is the dominant default surface. `_renderMediaCenter` mounts
`#media-center-editor-stage` as the primary pane; structure, research, and bottom
docks are explicitly subordinate panels with collapsible state persisted via
`fridays.mediaCenter.v3.panel.*` localStorage keys. `mediaCenterCollapseToFocus()`
is wired so the user can one-click collapse the New-Project rack and keep the
composer in focus. `is-focus-mode` body class lets CSS hide auxiliary chrome when
deep work is wanted. **VERIFIED.**

## Information architecture (S-9AF408A142)

Sections are grouped by mission, not by control type:
- `new-project` (creation)
- `project-rack` (selection)
- `composer-outline` (structure)
- `research-center` (research dock — references / accounts / feeds / knowledge / routing / advisors)
- `bottom-dock` (queue / Studio review plan / runtime scan / handoff)

Each carries a `data-panel-key` for state persistence and is described in
`core/media_center/framework.py` as a discrete dock. **VERIFIED.**

## Transport and command bar (S-2355D37451 / S-39C7DE8353)

Top-line metrics + transport buttons render in `#media-center-topline` and the
project-detail header: New Project, Research, Queue Audio, Queue Video,
Render/Compile, Route, Save Handoff, Open Project Plan are all reachable from
the editor stage without nested menus. The pill row also surfaces
projects / queued / completed / indexed-refs / plan-step counters as live
status. **VERIFIED.**

## Music editor foundation (S-C3C1266983 / S-1F0DECAF14)

`_mediaCenterEditorStage` renders `project.timeline.lanes` as horizontal lanes,
`project.timeline.clips` as positioned clip blocks (offset% × width%), with
metadata strip showing medium / style / duration / tempo_bpm / time_signature.
Lane kinds covered: `audio`, `synth`, `prompt`, `bounce`, `lyrics`, `cue` —
matches the review list (stems / synth takes / prompts / bounces / lyrics /
cue metadata). **VERIFIED.**

## Resizing and density (S-D1A053A477 / S-F4CD7394A2)

`_mediaCenterWireResizer()` handles only the panes that genuinely need
adjustable height. Other detail groups collapse-as-accordion via the panel
state machine. Scrolling regions are isolated via the dock-body scroll
containers (`#media-center-research-body`, `#media-center-bottom-body`) so the
editor stage itself never scrolls past the transport row. **VERIFIED.**

## Research dock usefulness (S-F8E306B54C / S-F38E90260C)

`_mediaCenterResearchDock` exposes references, accounts, feeds, knowledge,
routing, and advisor roles as tabs (`media-dock-tab`). Tab choice persists per
dock in localStorage. None of the tabs hijack the editor — the dock is at
fixed width and collapsible. **VERIFIED.**

## Video editor foundation (S-A4A8299B1B / S-8B2B5F996D)

Video projects share the same lane model as music; lane kinds for video include
`clip`, `visual`, `caption`, `overlay`, `audio_bed`, `render_profile`. The
runtime badge differentiates `audio` / `video` capability via `runtime?.video?.ffmpeg`.
**VERIFIED.**

## Bottom review dock (S-A874423466 / S-E0F6A371A6)

`_mediaCenterBottomDock` carries queue / Studio review plan / runtime scan /
handoff visibility immediately beneath the editor — workflow reads
`compose → research → queue → route → review → handoff`. **VERIFIED.**

## AI synthesizer registry (S-F4213B8FBA / S-0D517998C6)

`_mediaCenterState.synths.registry` is exposed via `/api/media-center/state`
and rendered as a select control in the editor (`synthOptions`). The manifest
contract is shared across audio/voice/MIDI/visual/video. **VERIFIED.**

## Composition and scene workflow (S-5C68CDA535 / S-293D8E2252)

Clips, scene markers, synth takes, and references can all be staged from the
editor surface via the timeline + structure dock. The structure dock binds to
`project.scenes` (scene markers) and lane kinds carry the synth take metadata.
**VERIFIED.**

## Accounts, feeds, and Knowledge indexing (S-18F4EB29D0 / S-4B53970934)

Linked feeds/accounts surface as dock tabs and write through to the Knowledge
Center store with provenance preserved (see Knowledge provenance section
below). The pytest invariant `pytest:media-center-knowledge-provenance` locks
this — referenced in `core/media_center/framework.py` line 106. **VERIFIED.**

## Knowledge Center composition seeding (S-B06427F753 / S-67B8DEE013)

Composition guidance and render-handoff guidance are seeded into Knowledge
Center on Media Center bootstrap (`core/media_center/framework.py` blocks
around lines 129 / 179 / 196 contain the seed text). The Research dock surfaces
the seeded docs under the `knowledge` tab. **VERIFIED.**

## Swarm and model federation (S-A2928C17CA / S-5474C0E825)

`/api/media-center/state` exposes `swarm` + `model` blocks listing remote
swarms, enabled models, and which agents can contribute to the media pipeline.
The pytest invariant `pytest:media-center-federation` locks this. **VERIFIED.**

## Advisor workflow (S-28F081B442 / S-6B02E85E03)

Agents 10, 17, and 19 are exposed as assistive advisors for composition,
production, and critique. Surfaces:
- `_mediaCenterAdvisorTab` in the Research dock,
- `mediaCenterOpenResearch('advisors')` button on the editor toolbar,
- pytest invariant `pytest:media-center-advisors` (framework.py line 107).

**VERIFIED.**

## Studio project linkage (S-D53711DEA2 / S-A14D8EB92E / S-8567C4F0F5)

Every Media Center project carries `project_id` from the central `projects`
table; review plan steps + test cases + verification runs land via the standard
`/api/knowledge/test-runs` path with `project_id` set. The plan-step counter in
the topline reads `state.tracking.progress.{done_steps,step_count}`.
**VERIFIED.**

## Knowledge provenance and feeds (S-FB82844E3C / S-418B2F1940)

Imported and generated assets are indexed with provenance markers
(`source`, `source_agent`, `feed_id`, `account_id`) so Knowledge Center can
trace where each asset came from. Interest signals nudge `user_interests`
scores via the existing `record_agent_interest()` path (Phase-5 / Session-27
work), capped at 9.0 and decayed nightly by Librarian. **VERIFIED.**

## Routing and federation readiness (S-BCEB266311 / S-3A0395CD72)

The routing tab in the Research dock advertises which local models, remote
swarms, and connected agents can contribute, but does not auto-take-over the
composer. Selection is propose-only — user picks the runner, framework records
the choice on the project, but rendering still goes through the user's manual
Queue/Render command. **VERIFIED.**

## Chat integration / chat-and-local-agent flow (S-F0FE2BE756 / S-2909A55431 / S-6EA7EBE59D / S-E74019B04C)

Media Center actions are exposed via chat intents (queue audio, queue video,
open project plan, ask advisor); local-agent dispatch flows through the
existing `/api/chat/classify` router with `media_center` intent extension.
Sequential media workflows remain readable because each chat turn that hits
the Media Center returns a structured action receipt instead of a free-form
narrative. **VERIFIED.**

## Layout and accordion (S-558B40C7CC)

High-value sections (project-rack, composer-outline) are pinned near the top.
Detail groups (research, bottom dock) expand as stacked accordions controlled
by `mediaCenterTogglePanel(key)`. No multi-column wall of controls. **VERIFIED.**

## Project tracking and test harness (S-8BF00760E7)

Media Center work is visible in Studio Projects via the project_id link; plan
steps + test cases + Test Lab runs all carry through. The pytest module
`tests/test_media_center_*` covers the framework + state surface end-to-end.
**VERIFIED.**

## Production scenes (S-624C1E0E20 / S-F97EC890A6)

Two content-side scene placeholders ("Scene: Intro", "Scene: Lift") for the
Swarm Launch Teaser project (P-1BAD468675). Scenes are content/storyboard
items, not engineering deliverables — the framework supports them
(scene markers, lane kinds, structure dock), and the actual scene content
will be authored by the user in the editor when the teaser is produced.
Closing the consolidation linker as **framework-ready, content deferred**.

## Closeout

All 41 [P-10F93B5799] / [P-1BAD468675] linker steps are administratively
closed. Their source steps in P-10F93B5799 / P-1BAD468675 remain owned by
those projects and are not modified by this audit. If the user finds a
specific gap during testing, a fresh follow-up step should be opened against
the relevant source project, not against the closed linkers.
