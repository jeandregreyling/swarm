# KC Seeds — Declarative Knowledge Centre Pipeline

Each YAML file under this directory is a **seed topic** that the Knowledge
Centre ingests on startup and on-demand via the `/api/knowledge/seed/reload`
endpoint. The framework is intentionally lightweight: a seed declares
*sources* (URLs, local files, prompts), *tags*, and a *refresh cadence*. The
loader walks the folder, merges duplicates by `topic_id`, and writes entries
to `knowledge.db` under the KC schema.

## File shape

```yaml
topic_id: huggingface
title: Hugging Face ecosystem
cadence: weekly          # daily | weekly | monthly | manual
tags: [ml, models, datasets]
sources:
  - kind: url
    url: https://huggingface.co/docs
    selector: main
  - kind: url
    url: https://huggingface.co/docs/transformers
  - kind: prompt
    title: PEFT overview
    text: |
      Explain PEFT in 3 bullets.
```

## Loader

See `ops/kc_seeds/_loader.py`. Called by `ops/seed_agent_permissions.py` and
the KC blueprint's reload endpoint. Tests: `tests/test_kc_seeds_framework.py`.
