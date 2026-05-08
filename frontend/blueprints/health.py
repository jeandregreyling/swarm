"""Unified system health aggregator.

GET /api/health returns a single JSON document combining:
  - server uptime
  - blueprint load failures (from app config)
  - wishlist pillar summaries (cyber/financial/trading/business)
  - bullshit detector stamp + score
  - learnings stats
  - composite stamp: GREEN if everything green, AMBER if pillars OK but
    detector amber, RED if detector red or any pillar errored.

This is the single curl every operator needs to know the build is healthy.
"""

import time
from flask import Blueprint, current_app, jsonify

health_bp = Blueprint('health', __name__)

_START_TIME = time.time()


def _detector_summary():
    try:
        from ops import bullshit_detector
        return bullshit_detector.summary_for_seven()
    except Exception as exc:  # noqa: BLE001
        return {'ok': False, 'error': str(exc), 'stamp': 'UNKNOWN', 'score': 0}


def _learnings_summary():
    try:
        from agents.seven import learnings
        return learnings.stats()
    except Exception as exc:  # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


def _witness_summary():
    """Seven the Witness: callouts ledger snapshot.

    Returns enabled flag, total callouts, breakdown by target, last seen,
    and a count of `callout`-severity hits in the last hour (used to nudge
    the composite stamp toward AMBER if Seven is being noisy).
    """
    try:
        from core import witness
        s = witness.stats()
        rows_last_hour = witness.list_callouts(limit=200,
                                               since=time.time() - 3600)
        critical = sum(1 for r in rows_last_hour if r['severity'] == 'callout')
        return {
            'ok': True,
            'enabled': witness.is_enabled(),
            'total': s.get('total', 0),
            'by_target': s.get('by_target', {}),
            'by_rule': s.get('by_rule', {}),
            'last_ts': s.get('last_ts'),
            'callouts_last_hour': len(rows_last_hour),
            'critical_last_hour': critical,
        }
    except Exception as exc:  # noqa: BLE001
        return {'ok': False, 'error': str(exc), 'enabled': False,
                'total': 0, 'critical_last_hour': 0}


def _pillar_summaries():
    out = {}
    for slug, dotted in (
        ('cyber-security', 'blueprints.cybersecurity_bp'),
        ('financial',      'blueprints.financial_bp'),
        ('trading',        'blueprints.trading_bp'),
        ('business',       'blueprints.business_bp'),
    ):
        try:
            mod = __import__(dotted, fromlist=['summary_for_seven'])
            out[slug] = mod.summary_for_seven()
        except Exception as exc:  # noqa: BLE001
            out[slug] = {'ok': False, 'error': str(exc)}
    return out


def _composite_stamp(detector_stamp: str, pillars: dict, blueprint_failures: int,
                     witness_block: dict | None = None) -> str:
    pillar_ok = all(p.get('ok', True) for p in pillars.values())
    if not pillar_ok or blueprint_failures > 0 or detector_stamp == 'RED':
        return 'RED'
    base = 'AMBER' if detector_stamp == 'AMBER' else (
        'GREEN' if detector_stamp == 'GREEN' else 'AMBER')
    # Witness nudge: any critical callouts in the last hour → at least AMBER.
    if witness_block and witness_block.get('critical_last_hour', 0) > 0 and base == 'GREEN':
        return 'AMBER'
    return base


@health_bp.route('/api/health', methods=['GET'])
def health_check():
    """Aggregated green/amber/red across the whole system."""
    detector = _detector_summary()
    pillars = _pillar_summaries()
    learnings_block = _learnings_summary()
    witness_block = _witness_summary()
    failed_bps = current_app.config.get('FAILED_BLUEPRINTS') or []
    composite = _composite_stamp(
        detector.get('stamp', 'UNKNOWN'),
        pillars,
        len(failed_bps),
        witness_block,
    )
    return jsonify({
        'ok': composite != 'RED',
        'stamp': composite,
        'uptime_s': round(time.time() - _START_TIME, 1),
        'build': {
            'detector_stamp': detector.get('stamp', 'UNKNOWN'),
            'detector_score': detector.get('score', 0),
            'critical': detector.get('critical', 0),
            'warnings': detector.get('warnings', 0),
            'info': detector.get('info', 0),
            'files_scanned': detector.get('files_scanned', 0),
        },
        'pillars': pillars,
        'learnings': learnings_block,
        'witness': witness_block,
        'blueprints_failed': [{'name': n, 'error': e} for n, e in failed_bps],
    })


@health_bp.route('/api/_introspect/routes', methods=['GET'])
def introspect_routes():
    """Enumerate every /api/* route. Used by tests/api_wide_probe.py."""
    out = {}
    for rule in current_app.url_map.iter_rules():
        p = str(rule.rule)
        if not p.startswith('/api/'):
            continue
        methods = sorted(m for m in rule.methods if m not in ('HEAD', 'OPTIONS'))
        out.setdefault(p, set()).update(methods)
    return jsonify([
        {'path': p, 'methods': sorted(list(m))}
        for p, m in sorted(out.items())
    ])

