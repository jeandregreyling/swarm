"""Practice 265: Done reports need real receipts."""
from core.apex_tools import doer_ok

REAL = [{'tool': 'propose_patch', 'status': 'succeeded', 'id': 'a04f3c75a22945e0853ed204fa25a8a8'}]


def test_invented_receipt_is_sent_back():
    assert not doer_ok('Done: Sent a flower to Claude (receipt 12345). Is it working?', [])
    assert not doer_ok('Done: patched core/x.py (receipt 99999999). Is it working?', REAL)


def test_real_receipt_passes():
    assert doer_ok('Done: patched core/x.py (receipt a04f3c75a22945e0853ed204fa25a8a8). Is it working?', REAL)


def test_done_without_any_action_is_sent_back():
    assert not doer_ok('Done: everything is fixed. Is it working?', [{'tool': 'read_file', 'status': 'succeeded', 'id': 'x1234'}])
