"""Practice 164 (owner 18 Nov 2026: "I can't see what agents are working on or thinking anymore"): /api/peer/v1/hb/activity was registered
twice and the live-text view was never served. One view now returns the chains and the live lines."""
import re


def test_practice_164_one_activity_route_with_lines():
    src = open('frontend/blueprints/peer_bridge.py').read()
    assert len(re.findall(r"route\('/api/peer/v1/hb/activity'", src)) == 1
    assert 'lines=live.get' in src and 'chains=act.chains' in src
    js = open('frontend/static/js/hb-live-activity.js').read()
    assert 'data.live' in js and 'data.lines.length' in js


def test_practice_164_snapshot_shape():
    import sqlite3
    from core import hb_live_activity
    out = hb_live_activity.snapshot(sqlite3.connect(':memory:'))
    assert 'lines' in out and 'running' in out
