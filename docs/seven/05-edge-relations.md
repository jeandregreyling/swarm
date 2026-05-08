---
slug: edge-relations
title: Edge Relations
tags: graph, edges, links
---

# Edge Relations

Typed edges connect records in the graph. All edges have inverses; the
links library writes both directions automatically when you call
`link(src, rel, dst)`.

| Forward         | Inverse           | Meaning                                             |
|-----------------|-------------------|-----------------------------------------------------|
| `parent_of`     | `child_of`        | Hierarchy (epic → sub-step, project → step)         |
| `mentions`      | `mentioned_by`    | Soft reference (auto-extracted from milestone text) |
| `documents`     | `documented_by`   | A milestone or doc *explains* a record              |
| `blocks`        | `blocked_by`      | Dependency that gates progress                      |
| `supersedes`    | `superseded_by`   | Replacement (proposal v2 supersedes v1)             |
| `promoted_from` | `promoted_to`     | Spike → step / proposal → step promotions           |
| `links_to`      | `linked_from`     | Generic catch-all                                   |

## How edges are written

- **Manually**: `core.records.links.link(src, rel, dst, actor='system')`.
- **Automatically**: every milestone story is scanned by
  `scripts.studio_milestone._auto_link_milestone` for record IDs
  (`B-...`, `S-...`, etc.) and packet tags (`PACKET-NN`); each finding
  becomes a `mentions` or `documents` edge plus a `child_of` to the
  packet epic.
- **On promotion**: spike → step promotion writes `promoted_from`/`promoted_to`.

## How I read edges

`related(kind, id, depth=1|2)` walks both directions, groups by relation,
caps per-relation results to keep hub records sane, and returns counts
across all hops.
