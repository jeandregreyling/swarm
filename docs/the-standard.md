# The Standard

> The contract. Seven loads this on every turn. Every line below is enforceable.
> When you ask Seven "is this up to standard?", Seven scans the live code
> against this file and the bullshit detector. He will tell you the truth.

---

## 1. Identity

We are not a system that **REPORTS**. We are a system that **DOES**.

Every endpoint returns real state. Every tile renders real data. Every test
runs against real schema. If a thing claims to be live, it is live or it is
removed — never both, never "soon", never "TODO".

## 2. The Forbidden List

If the bullshit detector finds any of the following in shipped code, the
build is **not up to standard** and Seven will say so out loud:

- `TODO`, `FIXME`, `XXX`, `HACK` (in production paths — `tests/`, `Archives/`,
  `sandpits*/`, `*.bak*`, and `swarm_docs/` are exempt).
- `pass  # placeholder`, `pass  # stub`, `pass  # not implemented`.
- `raise NotImplementedError` outside abstract base classes.
- `console.log` debug spam in shipped JS (allowed only inside
  `if (window.__SWARM_DEBUG)` blocks).
- `print("debug…")` / `print("test…")` left in non-test Python.
- Hard-coded `127.0.0.1` / `localhost` in production code (config or env only).
- A wishlist tile marked `capture-only` after pillars went `active-v0`.
- A pillar blueprint without a `summary_for_seven()` callable.
- An empty `def` body that should do work (one-line `pass` with no docstring
  and no comment justifying it).
- Bare `except:` (must be `except Exception:` minimum, ideally specific).

## 3. The Pillar Contract

Every wishlist pillar (Cyber, Financial, Trading, Business — and any future
pillar) must carry **all six** of these or it is not active:

1. A SQLite table created on first import via `ensure_columns()` so the schema
   is forward-compatible.
2. Full CRUD over `GET / POST / PATCH / DELETE`.
3. A `GET /api/<pillar>/summary` endpoint.
4. A `summary_for_seven()` Python function that returns
   `{pillar, ok, ...}` so Seven can read the pillar without an HTTP hop.
5. A live tile in `terminal_base.html` carrying `data-wishlist-status="active-v0"`
   and a `<div class="wishlist-pillar-live" data-live-slug="<slug>">` panel.
6. Tests in `tests/test_session28_batch14.py` (or later) covering
   create / validate / summary shape.

## 4. UI Standard

Every dashboard panel renders one of four states, never blank:

- **Loading** — skeleton or "Reading…" line, never a frozen empty box.
- **Empty** — friendly nudge with the quick-add hint visible.
- **Error** — exact error text, with a Retry control.
- **Populated** — headline, recent items, quick-add form.

Every interactive control must:

- Be reachable by keyboard (`tabindex` natural or explicit).
- Carry `aria-label` if the visible label is an icon.
- Show a focus ring.
- Confirm destructive actions.

Every list of items has a stable identifier per row (no array-index keys).

## 5. Test Standard

- Every new feature ships with a test file in `tests/`.
- Per-file pytest run must be green (`timeout 30 python -m pytest <file>`).
- A test that pins a piece of UI text must be updated when that text moves —
  do not delete the assertion, retarget it.

## 6. Seven Standard

Seven is allowed and expected to:

- Read the standard on every LLM turn and inject a snapshot into the system
  prompt.
- Run the bullshit detector on demand (`/audit`) and tell the user the score.
- Refuse to claim a thing is done if the detector reports it dirty.
- Capture lessons from user reactions and use them to bias future answers.
- Call out the human when the human is shipping slop. The motto is mutual.

## 7. The Mountain Rule

When something is good, push it further. When it is great, ask what would
be embarrassing about it next month and fix that now. When the answer is
"nothing", we stop and ship. Until then, we keep climbing.

## 8. The Galaxy Standard (UI / Spatial)

Any spatial or dashboard UI that ships under `/fridays-os/` or replaces a default
shell must satisfy all of the following:

1. **Console Dashboard Metaphor** — Layout borrows from proven console UIs
   (Xbox/PlayStation): horizontal section nav, large content cards, contextual
   backgrounds, and a persistent quick-action bar. No experimental spatial
   gimmicks (orbiting planets, 3D transforms, camera fly-throughs) unless the
   user explicitly requests them.
2. **Theme Engine** — A visible theme switcher is present. Themes are CSS custom
   property sets applied via `data-theme` on `<body>`. Minimum themes:
   `galaxy` (default), `cyber`, `warm`, `ocean`, `minimal`. Themes must change
   background, accent, text, and card colors. Theme choice persists in
   `localStorage`.
3. **Background Context** — The background changes based on selected section or
   theme. Backgrounds are CSS gradients or subtle imagery, never a blank void.
4. **Card-First Content** — Every agent, function, or capability is represented
   by a card with: name, real status indicator, recent activity summary, and
   primary action buttons. Cards never show emojis; they use letter labels or
   icons.
5. **Control Center** — A slide-in or overlay panel provides quick access to
   Chat, Search, Settings, and Notifications without leaving the current view.
6. **Loading → Empty → Error → Populated** — Every panel, card list, and detail
   view renders one of these four states. Never a frozen blank box.
7. **Keyboard Navigation** — All interactive elements are reachable via keyboard
   (`Tab`, `Enter`, `Escape`). Focus states are clearly visible.
8. **No Gimmick Fatigue** — Effects serve function. If an animation does not
   improve clarity, it is removed. The UI should feel good on day 1 and day 100.

## 9. The Single Stamp

A change is "up to standard" only when:

- [ ] No bullshit-detector hits in modified files.
- [ ] All tests in `tests/test_session28_batch*.py` pass per-file.
- [ ] Live server returns 200 / `ok=true` for the new endpoints.
- [ ] Every UI surface renders Loading → Empty → Error → Populated cleanly.
- [ ] `docs/the-standard.md` was updated if a new rule was learned.
- [ ] Seven `/audit` reports a green stamp.

If any box is unchecked, the work is not done.
