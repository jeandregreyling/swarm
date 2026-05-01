---
slug: api
title: My HTTP Surface
tags: api, http, endpoints
---

# My HTTP Surface

All endpoints are GET unless noted. All are read-only or propose-only.

## Perception

| Endpoint                                         | Returns                                |
|--------------------------------------------------|----------------------------------------|
| `GET /api/seven/observe?focus=<id>`              | One-shot snapshot                      |
| `GET /api/seven/related/<kind>/<id>?depth=1\|2`  | Graph neighbours                       |
| `GET /api/seven/stats`                           | Vital signs                            |
| `GET /api/seven/suggest`                         | Propose-only nudges                    |

## Memory

| Endpoint                                          | Returns                                |
|---------------------------------------------------|----------------------------------------|
| `GET /api/seven/episodes?limit=&kind=&record_id=` | Recent episodes                        |
| `GET /api/seven/beliefs?subject=&predicate=`      | Beliefs (subject-predicate-object)     |
| `GET /api/seven/concepts`                         | All semantic concepts (KC index)       |
| `GET /api/seven/concepts/<slug>`                  | One concept (full markdown body)       |
| `GET /api/seven/attention`                        | Working memory: hot records            |
| `GET /api/seven/memory`                           | Memory store summary                   |

## Reasoning

| Endpoint                                  | Returns                                       |
|-------------------------------------------|-----------------------------------------------|
| `GET /api/seven/explain?focus=<id>`       | Narrative + grounded references               |
| `GET /api/seven/decide?intent=...`        | Ranked proposals (`status\|next\|do\|remember`) |

## Liveness

| Endpoint                                  | Returns                                       |
|-------------------------------------------|-----------------------------------------------|
| `GET /api/seven/heartbeat`                | Continuous learner state + counters           |

## Maintenance (POST)

| Endpoint                              | Effect                                          |
|---------------------------------------|-------------------------------------------------|
| `POST /api/seven/concepts/reload`     | Re-read `docs/seven/*.md` into `seven_concepts` |
| `POST /api/seven/consolidate`         | Re-derive `is_stale` / `is_hub` / `is_active`   |

## Conventions

- IDs use the prefix scheme: `B-` note, `S-` step, `P-` project,
  `PR-` proposal, `T-` ticket, `TC-` case, `TR-` test_run, `D-` doc,
  `TH-` thread.
- All responses are JSON with `{"ok": true, ...}`.
- All read endpoints are safe to poll (`stats` and `heartbeat` are cheapest).
