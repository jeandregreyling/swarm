# DOES Sovereign Node

## Architectural Philosophy

Do not trust the intelligence of the model; trust the structure of the gateway.

DOES (Diversifying Operations Executional Sharing) treats models as disposable workers and treats state as the source of truth. Instead of one heavyweight model carrying huge context windows, execution is split into focused roles and coordinated through a persistent SQL layer.

## Problem Statement

Conventional AI stacks often assume:
- cloud dependency,
- expensive GPUs,
- large always-hot model memory,
- and brittle prompt-only control.

That approach fails on constrained hardware and produces hidden failure modes: formatting drift, state corruption, and memory pressure spikes.

## DOES Solution

DOES uses structural gates, not model intuition:
- Builder node generates raw structural output.
- Villain node audits and challenges output.
- Harness enforces phase boundaries and persistence.
- SQL state is canonical across iterations.

## Sandbox Infrastructure

- Orchestration engine: custom local Python harness
- Compute node: Dell OptiPlex 7090 (CPU-only)
- Storage: Samsung SSD (optimized local DB/file cache)
- Runtime topology: one active model per handoff edge

## Quantized Stack

- Builder: Qwen-2.5-1.5B (fast generation)
- Villain: Gemma-3-4B-Instruct (adversarial audit)

## State Machine

1. Generation
- Builder emits candidate code/logic.
- Harness stores payload in `does_state`.

2. Handoff
- Harness records Builder -> Villain edge in `does_handoff`.
- Studio milestone note can be emitted for trace continuity.

3. Audit
- Villain returns structured objections and recommendations.
- Harness stores results in `does_audit`.

4. Resolution
- Builder revises from critique.
- Loop continues until `PASS` with zero structural flaws or max iterations.

## Reliability Guards

- Output containment: explicit structural boundaries (no markdown/chat wrapper)
- SQL safety: parameterized inserts for payload and audit records
- Memory reset: model invocation with immediate unload semantics
- Handoff traceability: persisted edge log in `does_handoff`

## Observability Contract

Execution history must always include:
- generations (`does_state`),
- audits (`does_audit`),
- handoff edges (`does_handoff`).

This keeps runtime behavior inspectable and avoids detached reasoning chains.

## Current Potato Phase -> Future Scale Phase

Current potato phase:
- local CPU inference,
- quantized local models,
- SQL-backed orchestration loop.

Future scale phase:
- swap local model runtime endpoints for Nvidia NIM microservices,
- preserve harness contract and DB schema,
- scale throughput without rewriting orchestration logic.

The harness is runtime-agnostic: model endpoints can change while state-machine semantics stay fixed.

## Enterprise Audit Positioning

DOES is not a prompt demo. It is a deterministic orchestration pattern with:
- explicit phase transitions,
- persisted evidence,
- replayable execution IDs,
- and bounded failure domains.

That makes it suitable for open-source transparency and enterprise audit reviews.
