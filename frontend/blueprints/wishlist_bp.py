"""Wishlist blueprint (S-45064ED6C5).

Read-only surface that exposes the WISHLIST epic items so the front-end
tiles (Business / Financial / Trading / Cyber Security) can render
'capture-only' placeholders without us inventing copy in the template.

The pillar lookup is keyed by step_id so the tiles stay deterministic
even if titles get edited later. The shape stays simple on purpose —
these are placeholders, not features.

Source of truth:
  project_steps where step_id IN (
    'S-4697ECA1EC',  # Cyber Security as Diamond Layer
    'S-98CF85A8C4',  # Financial Analytics — IB-oriented
    'S-D618CF4B7A',  # Business Operational Centre
    'S-25AFB74A4D',  # Business: Accounting + Payroll
    'S-642D6439DE',  # Business: Manage People
    'S-B6D5701E4F',  # Business: Policies + Legal & Compliance
    'S-5393AEF947',  # Business: Stock + Vendor Management
    'S-2B6BC7A021',  # Business: Products + Sales Portal
    'S-03A241D177',  # Online Trading / Crypto
  )
  parent epic step_id = 'S-45064ED6C5'.
"""
from __future__ import annotations

import os
import sqlite3
from typing import Iterable

from flask import Blueprint, jsonify

wishlist_bp = Blueprint('wishlist_bp', __name__)

# Status moved from 'capture-only' to 'active-v0' once each pillar shipped
# a working backend (cybersecurity_bp, financial_bp, trading_bp, business_bp).
# The view templates still call /api/wishlist/pillars/<slug> for the step
# context, but they now ALSO render live data from the per-pillar APIs.
PILLAR_STATUS = 'active-v0'


# Pillar -> step IDs. Keep this as the single client-facing grouping.
PILLARS: dict[str, dict] = {
    'cyber-security': {
        'tile_title': 'Cyber Security',
        'tile_subtitle': 'Diamond layer · Wishlist',
        'description': (
            "Diamond-tier governance pillar. Threat model, hardening "
            "checklist, intrusion detection, audit log review, dependency "
            "scanning, secret rotation cadence, sandbox boundaries."
        ),
        'step_ids': ['S-4697ECA1EC'],
    },
    'financial': {
        'tile_title': 'Financial Analytics',
        'tile_subtitle': 'Investment banking · Wishlist',
        'description': (
            "IB-oriented (NOT consumer-finance). Equity / fixed-income / "
            "derivatives, M&A pipeline view, portfolio risk metrics, deal "
            "flow, league tables, data-room pattern."
        ),
        'step_ids': ['S-98CF85A8C4'],
    },
    'trading': {
        'tile_title': 'Online Trading',
        'tile_subtitle': 'Crypto / market data · Wishlist',
        'description': (
            "Online trading placeholder. Market data, order routing, P&L, "
            "risk. User prefers the framing 'online trading' over 'crypto'."
        ),
        'step_ids': ['S-03A241D177'],
    },
    'business': {
        'tile_title': 'Business Centre',
        'tile_subtitle': 'Run-the-company · Wishlist',
        'description': (
            "Operational centre for setting up an online business. "
            "Accounting + Payroll is the spine; everything else (People, "
            "Policies, Stock, Vendors, Products/Sales) hangs off it."
        ),
        'step_ids': [
            'S-D618CF4B7A',  # parent
            'S-25AFB74A4D',  # accounting+payroll
            'S-642D6439DE',  # manage people
            'S-B6D5701E4F',  # policies+legal
            'S-5393AEF947',  # stock+vendors
            'S-2B6BC7A021',  # products+sales
        ],
    },
}

EPIC_STEP_ID = 'S-45064ED6C5'


def _db_path() -> str:
    """Return active swarm DB path. Honours both env vars used elsewhere."""
    return (
        os.environ.get('SWARM_MEMORY_DB')
        or os.environ.get('SWARM_DB_PATH')
        or os.path.join(
            os.environ.get(
                'SWARM_ROOT',
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            ),
            'swarm_memory.db',
        )
    )


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _fetch_steps(step_ids: Iterable[str]) -> list[dict]:
    ids = list(step_ids)
    if not ids:
        return []
    placeholders = ','.join('?' for _ in ids)
    try:
        conn = _connect()
    except sqlite3.Error:
        return []
    try:
        cur = conn.execute(
            f"SELECT step_id, title, description, status "
            f"FROM project_steps WHERE step_id IN ({placeholders})",
            ids,
        )
        rows = cur.fetchall()
    except sqlite3.Error:
        rows = []
    finally:
        conn.close()
    by_id = {r['step_id']: dict(r) for r in rows}
    # Preserve declared order; fill missing IDs with stub so the UI is
    # resilient to a fresh DB that doesn't have the epic seeded yet.
    out: list[dict] = []
    for sid in ids:
        if sid in by_id:
            out.append(by_id[sid])
        else:
            out.append({
                'step_id': sid,
                'title': '(not yet captured)',
                'description': '',
                'status': 'todo',
            })
    return out


@wishlist_bp.route('/api/wishlist/pillars', methods=['GET'])
def list_pillars():
    """Return the four pillars with their underlying step records."""
    out = []
    for slug, meta in PILLARS.items():
        out.append({
            'slug': slug,
            'tile_title': meta['tile_title'],
            'tile_subtitle': meta['tile_subtitle'],
            'description': meta['description'],
            'steps': _fetch_steps(meta['step_ids']),
        })
    return jsonify({
        'ok': True,
        'epic_step_id': EPIC_STEP_ID,
        'status': PILLAR_STATUS,
        'pillars': out,
        'count': len(out),
    })


@wishlist_bp.route('/api/wishlist/pillars/<slug>', methods=['GET'])
def get_pillar(slug: str):
    if slug not in PILLARS:
        return jsonify({'ok': False, 'error': 'unknown pillar'}), 404
    meta = PILLARS[slug]
    return jsonify({
        'ok': True,
        'slug': slug,
        'status': PILLAR_STATUS,
        'tile_title': meta['tile_title'],
        'tile_subtitle': meta['tile_subtitle'],
        'description': meta['description'],
        'steps': _fetch_steps(meta['step_ids']),
    })


@wishlist_bp.route('/api/wishlist/summary', methods=['GET'])
def pillar_summary():
    """Aggregate snapshot Seven uses to answer 'how are the pillars doing?'.

    Imports each pillar's summary lazily so a missing/broken pillar module
    never takes down the whole endpoint.
    """
    snapshots: dict[str, dict] = {}
    loaders = (
        ('cyber-security', 'blueprints.cybersecurity_bp'),
        ('financial',      'blueprints.financial_bp'),
        ('trading',        'blueprints.trading_bp'),
        ('business',       'blueprints.business_bp'),
    )
    for slug, dotted in loaders:
        try:
            mod = __import__(dotted, fromlist=['summary_for_seven'])
            snapshots[slug] = mod.summary_for_seven()
        except Exception as exc:  # noqa: BLE001 - degrade, don't 500
            snapshots[slug] = {'pillar': slug, 'ok': False, 'error': str(exc)}
    return jsonify({
        'ok': True,
        'epic_step_id': EPIC_STEP_ID,
        'status': PILLAR_STATUS,
        'pillars': snapshots,
    })
