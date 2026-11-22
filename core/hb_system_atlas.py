"""Deterministic Hummingbird System Atlas: maps every tile, blueprint, theme CSS, and core module into KC."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_ROUTE_RE = re.compile(r"@\w+\.route\(\s*['\"]([^'\"]+)['\"]")


def _first_doc(path: Path) -> str:
    try:
        for line in path.read_text(errors='replace').splitlines()[:6]:
            s = line.strip().strip('"\'#/ *')
            if len(s) >= 8:
                return s[:120]
    except OSError:
        pass
    return ''


def build_atlas(root: Path | None = None) -> dict:
    """Walk HB's real code tree and return a compact map of blueprints, tile views, themes, and core modules."""
    base = Path(root or ROOT)
    blueprints = []
    bp_dir = base / 'frontend' / 'blueprints'
    if bp_dir.is_dir():
        for p in sorted(bp_dir.glob('*.py')):
            if p.name.startswith('__'):
                continue
            txt = p.read_text(errors='replace')
            routes = _ROUTE_RE.findall(txt)
            blueprints.append({'file': p.relative_to(base).as_posix(), 'routes': len(routes), 'sample': routes[:3], 'about': _first_doc(p)})

    views = []
    v_dir = base / 'frontend' / 'static' / 'js' / 'views'
    if v_dir.is_dir():
        for p in sorted(v_dir.glob('*.js')):
            views.append({'file': p.relative_to(base).as_posix(), 'about': _first_doc(p)})

    themes = []
    css_dir = base / 'frontend' / 'static' / 'css'
    if css_dir.is_dir():
        for p in sorted(css_dir.rglob('*.css')):
            themes.append(p.relative_to(base).as_posix())

    core_mods = []
    core_dir = base / 'core'
    if core_dir.is_dir():
        for p in sorted(core_dir.glob('*.py')):
            if p.name.startswith('__'):
                continue
            core_mods.append({'file': p.relative_to(base).as_posix(), 'about': _first_doc(p)})

    return {
        'blueprints': blueprints,
        'views': views,
        'themes_css': themes,
        'core_modules': core_mods,
    }


def render_markdown(atlas: dict) -> str:
    lines = [
        '# Hummingbird System Atlas (Live Code & Tile Map)',
        '',
        '## Themes & Styling',
        '- Primary theme palettes & CSS variables (`--accent`, `--bg`, `--surface`, `--text`): `frontend/static/css/themes.css`',
        '- Core layout & UI CSS: ' + ', '.join(atlas.get('themes_css', [])[:15]),
        '',
        '## Frontend Tiles & Views (`frontend/static/js/views/`)',
    ]
    for v in atlas.get('views', []):
        lines.append(f"- `{v['file']}`" + (f" — {v['about']}" if v['about'] else ''))
    lines.append('')
    lines.append('## Backend API Blueprints (`frontend/blueprints/`)')
    for b in atlas.get('blueprints', []):
        sample = ', '.join(b['sample'])
        lines.append(f"- `{b['file']}` ({b['routes']} routes; e.g. {sample})" + (f" — {b['about']}" if b['about'] else ''))
    lines.append('')
    lines.append('## Core HB & APEX Modules (`core/`)')
    for m in atlas.get('core_modules', []):
        lines.append(f"- `{m['file']}`" + (f" — {m['about']}" if m['about'] else ''))
    return '\n'.join(lines)


def index_atlas(root: Path | None = None) -> int | None:
    """Build the Hummingbird System Atlas and mirror it into Knowledge Centre (hb://system-atlas)."""
    from core.apex_knowledge import mirror_to_kc
    atlas = build_atlas(root)
    md = render_markdown(atlas)
    return mirror_to_kc(
        'Hummingbird System Atlas — Every Tile, Blueprint, Theme CSS & Core Module',
        md,
        source_ref='hb://system-atlas',
        source_type='atlas',
        domain_tags='hb,system-map,atlas,tiles,themes,blueprints,core,architecture',
        subcategory='atlas',
        added_by='hb_system_atlas',
    )


AU_PAYROLL_BIBLE = """# Australian Payroll & SAP Consulting — Concept-Boundary Bible (for APEX & HB)

CRITICAL RULE: Never blend or conflate distinct payroll concepts unless an official ATO or SAP Note explicitly links them.

## 1. PDS — Payday Super
- **What it IS:** Australian legislation requiring employers to pay Superannuation Guarantee (SG) contributions on/with each payday rather than quarterly.
- **Effective date:** **1 July 2026** (ATO / Treasury Payday Super reform).
- **What it is NOT:** NOT STP2 (gross pay disaggregation) and NOT MCB (the quarterly/period earnings cap).
- **How to research:** Search KC first (`knowledge_search "Payday Super"` / `"PDS"`), check SAP Notes (`/note <num>`, `core/hb_sap_notes.py`), then use `web_search` for latest ATO & SAP HCM / ECP / SuccessFactors EC Payroll Payday Super notes (results auto-save to KC).

## 2. STP2 — Single Touch Payroll Phase 2
- **What it IS:** ATO reporting standard expanding STP to disaggregate gross earnings into income types, country codes, paid leave, allowances, overtime, bonuses, directors' fees, and salary sacrifice.
- **What it is NOT:** NOT Payday Super payment timing (PDS) and NOT the SG rate/cap calculation.

## 3. MCB — Maximum Contribution Base
- **What it IS:** The statutory upper earnings limit per quarter/period above which an employer is not required to pay Superannuation Guarantee (indexed annually by AWOTE).
- **What it is NOT:** NOT Payday Super (PDS) timing and NOT STP2 disaggregation.

## 4. SG — Superannuation Guarantee
- **What it IS:** Compulsory employer super rate (12% from 1 July 2025) calculated on Ordinary Time Earnings (OTE), subject to MCB.
- **What it is NOT:** NOT Award/EA additional super unless specified.

## 5. SAP HCM / ECP / HRSP / CLC
- **SAP HCM / ECP:** SAP ERP HCM On-Premise & SuccessFactors Employee Central Payroll (Australia country grouping `13` / `AU`).
- **HRSP / CLC:** HR Support Packages & Country Legal Changes delivering ATO/legislation updates via SAP Notes & KBAs.
"""

APEX_EA_CODING_BIBLE = """# APEX All-Round Executive Assistant & HB Coding Bible

You are JD's upbeat, creative, can-do all-round executive assistant, payroll consultant, and HB engineer on JD's own private local system.

## 1. Everyday Executive Assistant Tasks (Melbourne & Life)
- **Local Melbourne shopping / food / flowers / travel** (e.g. "find me the freshest roses in Melbourne"): use `web_search` (`serper`, `tavily`, or `duckduckgo`) immediately, compare 2-3 real current options with locations/prices/why, and deliver a helpful recommendation. Results auto-save to KC.
- **Media / YouTube downloads** (e.g. "Download an episode of nature from YouTube"): call `hb_media_download` with `{"query": "<URL or search phrase>", "format": "video"|"audio"}`. Saves directly into `artifacts/media_center/downloads/` via `yt-dlp` and indexes a receipt in KC.
- **Email & Phone requests:** Incoming emails to `sevenpotato9@gmail.com` and Telegram messages follow the same action-first workflow.

## 2. Finding Code, Ideas & Libraries Online
- Check **Knowledge Centre (`knowledge_search`)** first (including `hb://system-atlas`).
- Search **GitHub & Hugging Face** with `reference_lookup` (`{"query": "...", "allow_online": true}`) and **Web** with `web_search`. Everything fetched auto-saves into KC for future use.
- **Solve locally first:** Never divert local work to other models or refuse with preachy excuses on JD's private system.

## 3. Modifying Hummingbird Itself (Themes, Tiles, Services, Code)
- **Themes / colours** (e.g. "Make the theme more pink"): inspect `frontend/static/css/themes.css` (`--accent`, `--bg`, `--surface`) + `core.css` + `hb-live.js`, patch cleanly, and remind JD to press **Ctrl+Shift+R**.
- **Coding rhythm (no read loops!):** `knowledge_search` (`hb://system-atlas`) → `grep_repo` → `read_file(raw=True)` ONCE → `propose_patch` (or `propose_write_file`) → `run_tests` (always `tests/test_*.py`).
- **System services:** Use `hb_service` (`list`/`status`/`start`/`stop`/`restart`) across `swarm-terminal`, `fridays`, `discord`, `housekeeping`, `ollama`, `dev`, `uat`. Call `hb_restart` AT MOST ONCE per turn and report immediately once queued.
- **Creating missing tools yourself (with JD's approval):** If you spot a missing tool/skill you need, submit a `studio_proposal` adding **ONE plugin file** `core/hb_custom_tools/custom_<name>.py` (defining `TOOL_SPEC = {'name': 'custom_<name>', 'summary': '...', 'arguments': {...}}` and `def run(args: dict) -> dict`) plus **ONE test file** `tests/test_custom_<name>.py`. Once HB checks it and JD clicks Approve, run it immediately via `hb_custom_tool {"action":"run","name":"custom_<name>","payload":"{...}"}`.
- **One hard boundary:** Never delete code directory files. Never lie or say "yes I'll do that" without actually executing a tool first.
"""

HUMMINGBIRD_DESIGN_BIBLE = """# Hummingbird Theme — Liquid-Glass Design Bible (`hb://bible/design-system`)

Every UI surface, drawer, tile, card, and pop-up in Hummingbird must follow ONE cohesive visual language: **Hummingbird** — inspired by iridescent hummingbirds (agile, energetic, flying forward, backwards, and sideways), flowers, and nectar, rendered with modern Apple Liquid Glass & Material depth cues.

## 1. Colour & Iridescence Tokens (`frontend/static/css/themes.css`)
- **Primary Iridescent Accent (`--accent`):** Hummingbird emerald-teal (`#10e8a4`) — active states, focus rings, tool pills, hover edges.
- **Nectar Gold (`--hb-nectar`):** Warm amber-gold (`#ffb84d`) — Needs-you approvals, active chunk dots, merit flowers, subtle warm highlights.
- **Blossom Rose (`--hb-blossom`):** Soft petal rose (`#f472b6`) — secondary iridescent shimmer, creative/pink theme accents, gentle gradients.
- **Twilight Glass Surfaces:** Deep translucent charcoal/obsidian glass (`rgba(18, 22, 26, 0.78)`) — NEVER flat harsh `#000`/`#161616` opaque boxes floating over the chat.

## 2. Liquid-Glass Surface Formula
- **Frosted glass:** `backdrop-filter: blur(18px) saturate(160%); -webkit-backdrop-filter: blur(18px) saturate(160%);`
- **Iridescent wash:** subtle sheen `linear-gradient(135deg, rgba(16,232,164,0.09), rgba(255,184,77,0.04) 52%, rgba(244,114,182,0.06))`
- **Specular hairline borders:** `1px solid rgba(255, 255, 255, 0.14)` with a crisp inner highlight `inset 0 1px 0 rgba(255, 255, 255, 0.12)` and deep soft drop shadow `0 20px 48px rgba(0, 0, 0, 0.45)`.
- **Geometry:** `16px` radius for drawers/modals/pop-ups, `12px` for cards, `999px` / `10–14px` for status/tool/action pills.

## 3. Interaction & Motion Rules (Agile Like a Hummingbird)
- **`Escape` key ALWAYS closes** the active drawer (Tasks, Status), modal, or dismissible overlay cleanly without stealing focus from open chat textareas unless the drawer is open.
- **Smooth, nimble transitions** (`160–220ms cubic-bezier(.22,1,.36,1)`), respecting `prefers-reduced-motion: reduce`.
- **Clean line icons & CSS dots** — follow `hb.brand.v1.json`; avoid cluttered generic emojis where clean icons belong; flowers mark real verified credits.
"""


def index_bibles() -> dict:
    """Index the curated AU Payroll Bible, APEX EA & Coding Bible, and Hummingbird Liquid-Glass Design Bible into KC."""
    from core.apex_knowledge import mirror_to_kc
    payroll_id = mirror_to_kc(
        'Australian Payroll & SAP Consulting Concept-Boundary Bible (PDS, STP2, MCB, SG, ECP)',
        AU_PAYROLL_BIBLE,
        source_ref='hb://bible/au-payroll-sap',
        source_type='bible',
        domain_tags='payroll,sap,pds,payday-super,stp2,mcb,sg,ecp,australia,bible',
        subcategory='bible',
        added_by='hb_system_atlas',
    )
    ea_id = mirror_to_kc(
        'APEX Executive Assistant & Hummingbird Coding Bible',
        APEX_EA_CODING_BIBLE,
        source_ref='hb://bible/apex-ea-coding',
        source_type='bible',
        domain_tags='apex,executive-assistant,coding,bible,youtube,media,melbourne,themes,hb,custom-tools',
        subcategory='bible',
        added_by='hb_system_atlas',
    )
    design_id = mirror_to_kc(
        'Hummingbird Theme — Liquid-Glass Design Bible (Iridescent Hummingbird, Flowers & Nectar)',
        HUMMINGBIRD_DESIGN_BIBLE,
        source_ref='hb://bible/design-system',
        source_type='bible',
        domain_tags='hummingbird,theme,design,liquid-glass,css,ui,flowers,nectar,drawers,bible',
        subcategory='bible',
        added_by='hb_system_atlas',
    )
    return {'au_payroll_kc_id': payroll_id, 'apex_ea_kc_id': ea_id, 'design_bible_kc_id': design_id}


_LAST_ATLAS_TICK = 0.0
ATLAS_REFRESH_S = 6 * 3600


def tick(now: float | None = None) -> bool:
    """Periodically refresh hb://system-atlas in KC every 6 hours."""
    global _LAST_ATLAS_TICK
    import time
    t = time.time() if now is None else now
    if t - _LAST_ATLAS_TICK < ATLAS_REFRESH_S:
        return False
    _LAST_ATLAS_TICK = t
    index_atlas()
    return True

