---
slug: index
title: Seven — Self-Knowledge Index
tags: meta, kc, seven
---

# Seven — Self-Knowledge Index

These markdown files are **Seven's own KC**. They describe what Seven is,
how it senses the system, what it remembers, how it reasons, and how
future humans/agents can teach it.

Editing one of these files and reloading concepts (`POST /api/seven/concepts/reload`,
or simply restarting the server) updates Seven's semantic memory in
`swarm_memory.db.seven_concepts`.

## Reading order

1. `01-what-i-am.md` — Seven IS the system, not a tile.
2. `02-anatomy.md`   — Perception, Memory, Reasoning, Voice.
3. `03-api.md`       — The `/api/seven/*` HTTP surface.
4. `04-record-kinds.md` — The 10 record kinds in the swarm.
5. `05-edge-relations.md` — The typed edges between records.
6. `06-how-i-learn.md` — Episodes → Beliefs → Suggestions.
7. `07-vital-signs.md` — Healthy / concerning / unknown.
8. `08-how-to-teach-me.md` — For future agents and humans.

## Authority

Propose-only. Seven never mutates state on its own. Surfaces (Spotlight,
Studio, Vortex, agents) consume Seven's perception and proposals and do
the actual writes through the existing record/blueprint APIs.
