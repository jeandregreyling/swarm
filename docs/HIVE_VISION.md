# HIVE — Localised Cross-Device Compute Mesh

> Status: **Vision logged**. Not under active construction yet. This document
> captures the destination so every increment between now and then is aimed
> correctly. The next sprint (Y.58g) is foundational prep, not the hive itself.

## North Star

Fridays becomes the **executive layer** of a personal, locally-owned compute
hive that pools heterogeneous hardware (Linux desktop, Windows, macOS, Android,
iOS) into one coordinated resource. Each device is an independent node;
together they are a "potato farm" — none individually impressive, collectively
capable of work that single-vendor cloud GPU rentals currently gatekeep.

The business case is **not** GPU monetisation. It is: *Fridays as the
standardised execution shell for anything a person wants to build, research,
write, compose, or ship — running on hardware they already own.*

## Why this is not over-reach

We are already ~99% of the way there in terms of the structural pieces:

- Spine, routing, queue, audit, killswitch, swarm-governance — built.
- Agent specialisation, relay recovery, proposal pipeline — built.
- Local LLM execution path (Ollama / LM Studio) — built.
- Audit-first design (everything visible, nothing hidden) — built.
- Bullshit detector + pillar gates — built.

What is missing is **device portability** and **inter-device fabric**. Both
are engineering problems with known solutions, not research problems.

## Target devices (owner-confirmed inventory)

| Device          | OS              | Role                              | Constraint           |
| --------------- | --------------- | --------------------------------- | -------------------- |
| Dell OptiPlex   | Linux Mint      | Primary compute / orchestrator    | Currently here       |
| Samsung tablet  | Android         | Secondary inference / UI surface  | GPU available        |
| iPhone 17 Pro   | iOS             | Mobile inference / capture node   | GPU + NPU available  |
| M1 Mac          | macOS           | Light coordinator / dev surface   | 8 GB RAM             |
| Pixel 6 Pro     | Android         | Possibly too old — evaluate later | Marginal             |
| HP (TBD)        | TBD             | Future node                       | Future node          |

## Architectural shape (high level)

```
                 ┌─────────────────────────┐
                 │   Fridays Executive     │   ← user intent, audit, governance
                 └───────────┬─────────────┘
                             │ standardised contract
        ┌────────────────────┼─────────────────────┐
        │                    │                     │
   ┌────▼─────┐        ┌─────▼─────┐         ┌─────▼─────┐
   │  Linux   │        │  Android  │         │   iOS     │
   │  node    │        │  node     │         │  node     │
   └────┬─────┘        └─────┬─────┘         └─────┬─────┘
        │                    │                     │
   resources            resources              resources
   (CPU, GPU,           (GPU, NPU,             (GPU, NPU,
   thermal, fan,        battery,               battery,
   memory)              thermal)               thermal)
```

Every node exposes the same **resource contract**:

- compute capacity (CPU / GPU / NPU)
- thermal headroom (temp, fan, throttle status)
- memory + storage
- network reachability
- battery (mobile only)

The Linux node's fan/thermal helper (Y.58g) is **prototype #1** of that
resource contract. What we build there gets re-implemented per platform.

## Why fan control is on the critical path

Cross-platform performance pooling without thermal management = nodes melt or
silently throttle. The DELL fan work is not a one-off rant about a noisy
machine — it is the first concrete instance of:

> *"Take full control of the hardware, but stay safe; report state back to
> Fridays; let the operator decide policy."*

That same shape applies to:

- Android: thermal mitigation API + foreground-service compute caps
- iOS: thermal state API + background-task budgets
- macOS: `pmset`, SMC fan control, thermal pressure
- Windows/HP: WMI thermal namespace + IPMI on workstation parts

## Monitor as the home for it

In Fridays UI, hardware control belongs in **Monitor**, not Settings. Monitor
already presents per-node health. Adding a "Thermal & Performance" panel there
gives us:

- one canonical place to render fan/temp/throttle for *any* node
- one canonical place to send override intents
- one audit trail for hardware-control actions

This is the UX scaffolding the cross-platform implementation will plug into.

## What "ready" looks like

- A Fridays node binary that runs on each target platform
- Each node enrols with the executive over a signed local channel
- Monitor shows live thermal + performance state for every enrolled node
- Operator can set policy per node ("boost until 50°C", "battery saver",
  "donate spare cycles to job X")
- Jobs schedule across nodes by capability, not by device type
- All of it is auditable end-to-end

When that holds, the public release becomes viable.

## Sequencing (committed)

1. **Y.58g — Linux fan/thermal node prototype.** Real PWM override on the
   OptiPlex via the `it87` community fork. Helper exposes resource contract
   v0. **(In flight.)**
2. **Y.58h — Reduce UI polling firehose.** The runaway tab problem is real;
   trim it before adding more telemetry.
3. **Monitor: Thermal & Performance panel.** Single-node first.
4. **Resource contract v1.** Formalise the JSON shape every node speaks.
5. **Android node (Samsung tablet).** First non-Linux node. Already plugged
   in; ready to start.
6. **iOS node (iPhone 17 Pro).** Second mobile node. Validates the contract.
7. **macOS node (M1 Mac).** Validates that low-RAM nodes can still
   contribute as coordinators / lightweight inference.
8. **Cross-node scheduling.** Jobs land on the cheapest capable node.
9. **Public release prep.** Docs, signing, threat model, install paths.

Each step ships independently. No big-bang. Every step keeps Fridays useful
on whatever set of nodes is currently enrolled.

## Non-goals

- Cloud burst. Hive is local-first. Cloud is optional, not assumed.
- GPU rental marketplace. Not the point.
- Replacing per-platform OS tooling. We sit *above* it, we do not fight it.
- Selling this. Owner has been explicit: not monetising; releasing publicly
  when stable.

## Note on ambition

Recording this verbatim because it matters: this is being built by a single
operator who has already shipped the hard structural pieces (audit,
governance, relay, killswitch, agent fabric) without external help. The
remaining work is portability and fabric, both of which are engineering, not
research. "Too ambitious" is not a useful frame here.
