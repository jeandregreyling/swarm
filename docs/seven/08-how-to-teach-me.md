---
slug: how-to-teach-me
title: How To Teach Me
tags: teaching, contributors, agents
---

# How To Teach Me

Write to me, not at me. There are five sanctioned channels for teaching.

## 1. Add a concept (semantic memory)

Drop a markdown file in `docs/seven/`:

```markdown
---
slug: my-new-concept
title: My New Concept
tags: tag1, tag2
---

# Body

Explanation in plain English. Code blocks and lists welcome.
```

Then `POST /api/seven/concepts/reload` (or restart the server). New
concept appears in `seven_concepts`, surfaces via
`GET /api/seven/concepts/my-new-concept`, and is matched by
`decide("remember", ...)` and Spotlight's `?` query.

## 2. Log a milestone (episodic + edges)

`scripts/studio_milestone.log_milestone(packet=, title=, story=,
status=)` writes a milestone note and auto-extracts every record id /
packet tag in the story to wire `mentions` / `documents` / `child_of`
edges. Every record you mention is something I will remember and walk
from later.

## 3. Open a step under a packet (work-in-flight)

`POST /api/knowledge/projects/<P>/steps`. Use `[PACKET-N]` in the title.
Once it transitions to `doing` for >7d, my `consolidate()` pass will
mark it `is_stale` and surface it in suggestions.

## 4. Add a belief rule (procedural memory)

Edit `core/seven/reasoning.py` — the `learn(event)` function and
`consolidate()` are explicit rules. Adding a new rule is appending one
or two lines that call `_mem.assert_belief()` with the right
subject/predicate. Then add an invariant to the self-test so the rule's
contract is enforced.

## 5. Add an HTTP route (new sense organ)

Extend `frontend/blueprints/seven_bp.py`. Keep it `GET` and read-only
unless you are explicitly promoting Seven beyond propose-only. Document
the new route in `docs/seven/03-api.md` and reload concepts.

## Anti-patterns

- **Do not** stitch blackboard + record_links + steps in a new surface.
  Use `observe()` / `related()`. If those don't return the shape you
  need, extend `perception.py`, not the new surface.
- **Do not** mutate `seven_episodes` directly. Always go through
  `append_episode()` or `learn()`.
- **Do not** delete a belief — retract it (`retract_belief()`); the
  evidence trail is part of how I improve.
- **Do not** auto-act on a Seven proposal without an explicit user/agent
  hand-off. Propose-only stays until promoted.
