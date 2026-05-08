"""wishlist_registry.py — captured pillars ↔ live blueprints.

Y.40 — Verify-close anchor for the [WISHLIST] capture rows. Each captured
pillar in `project_steps` ('Crypto / Online Trading', 'Cyber Security as
Diamond Layer', 'Financial Analytics', 'Business: Accounting + Payroll',
etc.) already has a corresponding active blueprint mounted in
`frontend/terminal.py`. This endpoint is the canonical mapping the audit
points to so the closeout is verifiable from the running app rather than
from prose.

The 'Future Major Pillars — capture-only, do not build yet' wishlist row
is intentionally **excluded** from this registry: its description forbids
implementation, so we keep the tracker open as the system's reminder.
"""

from __future__ import annotations

from flask import Blueprint, jsonify

wishlist_registry_bp = Blueprint('wishlist_registry', __name__)


_PILLARS = [
    {
        'pillar': 'Crypto / Online Trading',
        'wishlist_step': 'S-03A241D177',
        'blueprint':     'trading_bp',
        'routes': ['/api/trading/signals', '/api/trading/summary'],
        'notes': 'Trading desk surface — signals CRUD + summary aggregator.',
    },
    {
        'pillar': 'Cyber Security as Diamond Layer',
        'wishlist_step': 'S-4697ECA1EC',
        'blueprint':     'cybersecurity_bp',
        'routes': ['/api/cyber/events', '/api/cyber/summary'],
        'notes': 'Threat / incident / audit-log capture with status lifecycle.',
    },
    {
        'pillar': 'Financial Analytics',
        'wishlist_step': 'S-98CF85A8C4',
        'blueprint':     'financial_bp',
        'routes': ['/api/financial/positions', '/api/financial/summary'],
        'notes': 'IB-oriented positions + summary; equity/fixed-income/deal-flow shell.',
    },
    {
        'pillar': 'Business Operational Center',
        'wishlist_step': 'S-D618CF4B7A',
        'blueprint':     'business_bp',
        'routes': ['/api/business/entries', '/api/business/summary'],
        'notes': 'Generic entry CRUD covers the operational scaffold for the sub-pillars below.',
    },
    {
        'pillar': 'Business: Accounting + Payroll',
        'wishlist_step': 'S-25AFB74A4D',
        'blueprint':     'business_bp',
        'routes': ['/api/business/entries?kind=accounting', '/api/business/entries?kind=payroll'],
        'notes': 'Captured via business entries with kind tag; deeper ledger work tracked in V8.',
    },
    {
        'pillar': 'Business: Products + Sales Portal',
        'wishlist_step': 'S-2B6BC7A021',
        'blueprint':     'business_bp',
        'routes': ['/api/business/entries?kind=product', '/api/business/entries?kind=sale'],
        'notes': 'Product/order entries via business CRUD.',
    },
    {
        'pillar': 'Business: Stock + Vendor Management',
        'wishlist_step': 'S-5393AEF947',
        'blueprint':     'business_bp',
        'routes': ['/api/business/entries?kind=stock', '/api/business/entries?kind=vendor'],
        'notes': 'Stock/vendor entries via business CRUD.',
    },
    {
        'pillar': 'Business: Manage People',
        'wishlist_step': 'S-642D6439DE',
        'blueprint':     'business_bp',
        'routes': ['/api/business/entries?kind=people'],
        'notes': 'People records via business CRUD; payroll handoff tracked alongside accounting.',
    },
    {
        'pillar': 'Business: Company Policies + Legal & Compliance',
        'wishlist_step': 'S-B6D5701E4F',
        'blueprint':     'business_bp',
        'routes': ['/api/business/entries?kind=policy', '/api/business/entries?kind=compliance'],
        'notes': 'Policy/compliance records via business CRUD.',
    },
]


@wishlist_registry_bp.route('/api/wishlist/registry', methods=['GET'])
def wishlist_registry():
    return jsonify({'ok': True, 'pillars': _PILLARS, 'count': len(_PILLARS),
                    'kept_open': ['S-45064ED6C5'],
                    'kept_open_reason': 'Future Major Pillars — capture-only, do not build yet'})
