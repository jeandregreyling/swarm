# ALM Cookbook — Proposal & Approval Workflow

<!-- markdownlint-disable -->

Updated: 2026-04-12

## Overview

The ALM (Application Lifecycle Management) system provides an auditable
change-control pipeline. Every agent-initiated change goes through:

```
Chat (proposal raised) → Duck sanity check → Ghost review → DEV → UAT → PROD
```

Each stage is linked: proposals carry `source_conv_id` so Duck can post
approval/rejection back to the originating chat thread. Status changes at every
stage also notify the same thread automatically.

---

## Skill-Based Flow (agents in Chat)

Agents use skills. Ghost sees the result in the same chat thread.

### 1. Create a proposal

```
SKILL alm_create_proposal "<title>" "<description>"
```

- Creates `INTERNAL-<AGENT>-<NNNN>` proposal in DB
- Duck reviews it immediately (background) and posts verdict to the chat thread
- Dedup: if the same title exists in this conversation within 5 minutes, returns
  the existing proposal ID instead of creating a duplicate

### 2. Self-approve and start work (developer agents only)

```
SKILL alm_self_approve INTERNAL-ELEVEN-0558 [optional-vortex-label]
```

- Advances the proposal from `approved` → `in_progress`
- Creates a Vortex (time machine) checkpoint for rollback
- Works with any ID format: full `INTERNAL-ELEVEN-0558`, numeric `0558`, etc.

### 3. Make the change

```
SKILL fs_patch <path> <<<OLD>>>old text<<<NEW>>>new text
SKILL fs_write <path>
content here
---END---
```

### 4. Mark complete

```
SKILL alm_complete INTERNAL-ELEVEN-0558
```

- Advances `in_progress` → `done`
- Ghost reviews and promotes to `executed` or reopens

---

## API Flow (direct / programmatic)

### Create proposal

```http
POST /api/queue
{"agent": "nine", "title": "...", "description": "...", "priority": 5}
```

Response: `{"ok": true, "proposal_id": "INTERNAL-NINE-0102"}`

### Advance status (Ghost)

```http
PATCH /api/work-proposals/<proposal_id>
{"status": "approved", "actor": "ghost", "note": "optional context"}
```

Valid statuses: `pending → approved → in_progress → done → executed`

Also supports direct rejection: `{"status": "rejected"}`

### Agent self-advance (skills / direct)

```http
POST /api/work-proposals/<proposal_id>/agent-advance
{"agent": "eleven", "action": "start"}   # pending/approved → in_progress
{"agent": "eleven", "action": "complete"} # in_progress → done
```

The endpoint tries the exact ID and multiple normalized variants
(`INTERNAL-ELEVEN-XXXX`, `INTERNAL-XXXX`, numeric) so any format works.

### Edit proposal content

```http
PATCH /api/work-proposals/<proposal_id>/edit
{"title": "...", "description": "...", "notes": "..."}
```

### Attachments

```http
GET    /api/work-proposals/<id>/attachments
POST   /api/work-proposals/<id>/attachments          # multipart/form-data file=
GET    /api/work-proposals/<id>/attachments/<att_id> # download
DELETE /api/work-proposals/<id>/attachments/<att_id>
```

### Agent notes

```http
GET  /api/work-proposals/<id>/notes
POST /api/work-proposals/<id>/notes
{"content": "observation text", "author": "duck"}
```

---

## Duck Auto-Review

Every proposal created via `SKILL alm_create_proposal` is reviewed by Duck
within ~1 second (background thread):

- **Approved**: description ≥ 20 chars, title ≥ 5 chars, no destructive keywords
- **Rejected**: too short, or contains `delete all`, `drop table`, `rm -rf`, etc.

Duck posts the verdict back to `source_conv_id` (the originating chat thread).

---

## Studio UI (Ghost)

Open **Studio** tile → proposals are shown with:
- Colour-coded pipeline progress bar
- Duck review banner (green/red)
- "💬 View in Chat" link back to the originating thread
- Agent notes section (Duck and agents can add notes)
- Attachment upload/download
- Status action buttons appropriate to current stage

---

## Environment Ports

| Environment | Port | Purpose |
|---|---|---|
| PROD (Fridays) | 5050 | Live system |
| DEV (Mondays) | 5051 | Development work |
| UAT (Wednesdays) | 5053 | User acceptance testing |

The ALM skill helper `_alm_api_post` tries all three ports in order so agents
don't need to know which server they're running against.

---

## Failure Modes

| Code | Meaning |
|---|---|
| 404 | Proposal not found (check ID format — all variants tried) |
| 400 | Invalid action (must be `start` or `complete`) |
| 428 | `proposal_id` missing from mutating request |

---

## Daily Self-Audit Checklist

1. `python3 -m py_compile fridays/skills.py` — no syntax errors
2. Pending proposal count in Studio — clear or actioned
3. Sniffles enabled state verified (`/api/alm/status`)
4. Changelog + tracker updated
5. Vortex checkpoint created before any destructive change
