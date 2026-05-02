# Fridays Model Runtime Gateway — Design

> **Story**: STEP-FRIDAYS-MODEL-RUNTIME-GATEWAY-20260430 (PACKET-07)
> **Status**: shipped (slice 1) — `core/model_runtime_gateway.py` + integrations.

## Why a gateway

Local model calls (Ollama) historically reached chat / media / agents via three
unrelated client paths. Each path reinvented timeout handling, JSON cleanup,
token-heartbeat tracking, and "is the runner stuck" logic. The result was:

- Inconsistent absolute-vs-idle timeout semantics (some callers timed out the
  whole call, others only the request socket).
- Media-side JSON consumers crashed on harmless markdown-fenced output.
- No single place to classify "Ollama is loading", "Ollama is stuck", or
  "Ollama is stopping".
- No structured event stream — callers either got a final string or nothing,
  with no way to surface progress to the UI.

The runtime gateway is the Fridays-owned control layer that sits above
Ollama and gives every caller the same primitives.

## Surface (slice 1)

`core.model_runtime_gateway` exposes four top-level functions:

| Function | Purpose |
|---|---|
| `chat(model, messages, *, on_token=None, on_event=None, idle_timeout_s, absolute_timeout_s, ...)` | Stream a chat completion. Emits `RuntimeEvent` markers for `connect`, `first_token`, `complete`, `idle_timeout`, `absolute_timeout`, `error`. Returns a `RuntimeResult`. |
| `ollama_health(base_url, *, ps_payload=None)` | Returns `{state, detail, models}` where `state ∈ {ok, idle, loading, stuck, stopping, down}`. Used by `/api/ollama/health`. |
| `force_unload(model, *, base_url=...)` | Issues `keep_alive=0` to evict a stuck model. Used by `/api/ollama/force-unload`. |
| `normalize_model_json(text)` | Extracts a JSON object/array from raw model output, tolerating markdown fences, single-item list wrappers, and truncated tails. Returns `{ok, data, error, truncated}`. Used by media and structured-output callers. |

### Data classes

- `RuntimeEvent(stage, at, detail, tokens)` — single point on the streaming
  timeline. Always JSON-serializable via `as_dict()`.
- `RuntimeResult(ok, model, content, tokens, elapsed_s, error, events)` —
  returned by every `chat()` call. Carries the full event timeline so callers
  can render badges or export traces without re-instrumenting.

## Integration points

| Caller | Path | Use |
|---|---|---|
| `core/llm.py` (`stream_local_chat`) | `from core import model_runtime_gateway as _gw` | Default streaming path for any Fridays-side local LLM call. |
| `frontend/blueprints/ollama.py` | `ollama_health`, `normalize_model_json`, `force_unload` | `/api/ollama/health`, `/api/ollama/show/<model>`, `/api/ollama/force-unload`. |
| `frontend/blueprints/media_bp.py` | `normalize_model_json` | Defends media JSON producers against fenced/unbalanced output. |

## Timeout semantics

The gateway separates two clocks per call:

- **idle_timeout_s** — restart-on-token. Resets every time a new token arrives.
  Catches "model is alive but generating slowly" vs "model is wedged".
- **absolute_timeout_s** — wall clock. Hard upper bound on the whole request.
  Catches "first token never arrives" and "tokens trickle forever".

When either fires, the gateway emits the matching event (`idle_timeout` /
`absolute_timeout`) and closes the underlying HTTP stream. Callers see
`ok=False` with a typed `error` string, never an unbounded hang.

## Health classification

`ollama_health()` is the single source of truth for "is the local runner
healthy?". It composes:

1. `GET /api/tags` reachability → `down` if it fails.
2. `GET /api/ps` (or caller-supplied `ps_payload`) for loaded models.
3. Per-model `expires_at` window → `loading` while pulling, `stopping` when
   `keep_alive` has expired but the runner hasn't yet released.
4. CPU/heartbeat heuristic from `model_health` rows → `stuck` when a runner
   is pinned and not progressing.

The output shape is stable and consumed by:

- the runtime health badges in the Studio header,
- the Monitor home tile,
- the architecture self-test (invariant: `ollama_health.state != 'stuck'`).

## Why these primitives and not more

Slice 1 is intentionally narrow. The remaining roadmap (NOT in this packet):

- **Slice 2**: queue + cancel API (drain on shutdown, cancel-by-request-id).
- **Slice 3**: per-tenant quotas and fairness.
- **Slice 4**: multi-runner federation (Ollama + LM Studio + remote Ollama).

Anything that needs those should propose a follow-up step under PACKET-07.
This document captures slice 1 as the locked design.

## Tests

- `tests/test_model_runtime_gateway.py` — primitives (normalize, chat happy
  path, both timeouts, error paths).
- `tests/test_chat_via_runtime_gateway.py` — `core.llm` callers see the same
  callbacks the gateway emits.
- `tests/test_runtime_health_badges.py` — `ollama_health` state machine
  including stuck/stopping classification.
- `tests/test_runtime_force_unload.py` — `force_unload` round-trips through
  the blueprint.

## Operational rules

- Never call Ollama HTTP directly from blueprints or agents; always go
  through `model_runtime_gateway`. New direct `requests.post(...11434...)`
  call sites are a regression and should be migrated.
- Never silently catch a `RuntimeResult.ok == False`. Callers must surface
  the typed error to the audit ledger so health monitoring can react.
- `normalize_model_json` is the only sanctioned "clean up model JSON"
  helper. Local cleanup re-implementations are forbidden; extend the helper
  instead.
