"""Tests for core.hive.enrolment — Y.59."""
from __future__ import annotations

from core.hive.enrolment import (
    list_tokens,
    mint_token,
    revoke_token,
    verify_token,
)


def test_mint_and_verify(tmp_path):
    path = str(tmp_path / 'tokens.jsonl')
    token = mint_token('node-a', label='dev', path=path)
    assert isinstance(token, str) and len(token) > 20
    assert verify_token('node-a', token, path=path) is True
    assert verify_token('node-a', 'wrong', path=path) is False
    assert verify_token('other', token, path=path) is False


def test_revoke(tmp_path):
    path = str(tmp_path / 'tokens.jsonl')
    token = mint_token('n', path=path)
    assert verify_token('n', token, path=path)
    assert revoke_token('n', path=path) is True
    assert verify_token('n', token, path=path) is False
    # Idempotent: revoking absent node returns False.
    assert revoke_token('n', path=path) is False


def test_list_omits_hash(tmp_path):
    path = str(tmp_path / 'tokens.jsonl')
    mint_token('n1', label='one', path=path)
    mint_token('n2', label='two', path=path)
    rows = list_tokens(path=path)
    assert len(rows) == 2
    for r in rows:
        assert 'hash' not in r
        assert 'node_id' in r


def test_rotation_replaces_existing(tmp_path):
    path = str(tmp_path / 'tokens.jsonl')
    t1 = mint_token('n', path=path)
    t2 = mint_token('n', path=path)
    assert t1 != t2
    assert verify_token('n', t1, path=path) is False
    assert verify_token('n', t2, path=path) is True


def test_verify_rejects_empty():
    assert verify_token('', 'x') is False
    assert verify_token('n', '') is False
    assert verify_token('n', None) is False
