# Seven Runtime — theme doc

_Phase-7 theme. Owner: Swarm platform team._

## Why

Ollama is an excellent baseline gateway but it is not the only way Swarm can
talk to models. The long-term plan is for Swarm to own its model orchestration
so it can:

- run quantised GGUF models in-process (llama.cpp) for cold-latency-critical
  paths;
- delegate cheap/background work to peer hosts (LM Studio, OpenAI-compatible
  endpoints) without lock-in;
- enforce a global RAM ceiling with LRU eviction across all drivers;
- publish a stable per-model TTL + warm-pool API the rest of the Swarm relies
  on regardless of the underlying backend.

Ollama becomes a **peer driver** alongside llama.cpp / LM Studio / OpenAI.

## Components

| Module | Responsibility |
| --- | --- |
| `core/seven_llm/registry.py` | Catalogue (GGUF path, ctx, quant, role, RAM, TTL). Loads from `ops/llm_registry.yaml`. |
| `core/seven_llm/pool.py` | Warm-pool with TTL, RAM ceiling, LRU evict, per-model queue. |
| `core/seven_llm/driver_base.py` | Driver ABC (chat/ps/list_models/unload). |
| `core/seven_llm/driver_ollama.py` | Wraps legacy `core/llm.py` so Ollama is one peer. |
| `core/seven_llm/driver_llamacpp.py` | In-process GGUF via `llama-cpp-python` (optional dep). |
| `core/seven_llm/driver_lmstudio.py` | HTTP driver for LM Studio's OpenAI-compat server. |
| `core/seven_llm/driver_openai.py` | HTTP driver for OpenAI / Azure OpenAI / any compatible endpoint. |
| `ops/seven_trainer.py` | Nightly LoRA on KC + Vortex traces, promote/rollback gate. |

## Feature flag

`SEVEN_RUNTIME=1` enables the new routing. When unset, `core/llm.py`
continues to serve every caller unchanged. Migration plan:

1. Ship registry + pool + drivers (**this phase**).
2. Mirror calls — legacy gateway still serves, but tag a subset of callers
   to run through the new runtime and compare responses.
3. Flip default once parity is confirmed.
4. Remove legacy `core/llm.py` when every caller is on the new path.

## Open items

- Streaming support in the OpenAI / LM Studio drivers (currently block-only).
- RAM ceiling is environment-configurable but we don't yet actually measure
  resident sizes — the limit is a declared upper bound from the registry.
- `seven_trainer` full LoRA loop requires `peft` + `transformers` + GPU; the
  module ships as a dry-run-by-default scaffold.
