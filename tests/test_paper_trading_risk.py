"""Tests for Phase 3B $500-Cap Paper-Trading Risk Engine & Scorecard."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.paper_trading_risk import (
    DEFAULT_STARTING_CAPITAL,
    MAX_RISK_PCT,
    PAPER_ONLY,
    evaluate_portfolio_scorecard,
    size_position,
)


def test_position_sizer_enforces_2pct_risk_cap_and_stop_loss():
    assert PAPER_ONLY is True
    sized = size_position(equity=500.0, entry_price=100.0, stop_loss_price=95.0, side='buy', risk_pct=0.10, take_profit_price=115.0)
    # 10% requested risk must be hard-clamped to 2.0% ($10 max loss on $500)
    assert sized['risk_clamped'] is True
    assert sized['risk_pct_applied'] == MAX_RISK_PCT
    assert sized['max_loss_usd'] == 10.0
    assert sized['quantity'] == 2.0
    assert sized['reward_to_risk'] == 3.0

    with pytest.raises(ValueError):
        size_position(equity=500.0, entry_price=100.0, stop_loss_price=105.0, side='buy')


def test_scorecard_circuit_breaker_and_live_readiness_gates():
    # Losing streak trips 15% drawdown circuit breaker
    bad = evaluate_portfolio_scorecard([{'pnl': -40.0}, {'pnl': -45.0}], starting_capital=DEFAULT_STARTING_CAPITAL)
    assert bad['circuit_breaker_tripped'] is True
    assert bad['live_readiness_verdict'].startswith('STAY_IN_PAPER_LAB')

    # 30 disciplined winning paper trades clear all paper gates
    good_trades = [{'pnl': 12.0} if i % 3 != 0 else {'pnl': -5.0} for i in range(30)]
    good = evaluate_portfolio_scorecard(good_trades, starting_capital=500.0, gpu_goal=2400.0)
    assert good['circuit_breaker_tripped'] is False
    assert good['profit_factor'] >= 1.3
    assert good['gates']['min_30_closed_paper_trades'] is True
    assert good['live_readiness_verdict'].startswith('READY_FOR_OWNER_REVIEW')


def test_trading_blueprint_paper_lifecycle(tmp_path: Path, monkeypatch):
    import frontend.blueprints.trading_bp as tbp
    db_file = tmp_path / 'paper_test.db'

    def _conn():
        c = sqlite3.connect(db_file)
        c.row_factory = sqlite3.Row
        return c

    monkeypatch.setattr(tbp, 'connect', _conn)
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(tbp.trading_bp)
    client = app.test_client()

    r_open = client.post('/api/trading/paper/open', json={
        'symbol': 'VOO',
        'side': 'buy',
        'strategy': 'breakout',
        'entry_price': 500.0,
        'stop_loss_price': 490.0,
        'take_profit_price': 525.0,
    })
    assert r_open.status_code == 201
    tid = r_open.get_json()['trade_id']
    assert r_open.get_json()['paper_only'] is True

    r_close = client.post(f'/api/trading/paper/{tid}/close', json={'exit_price': 520.0})
    assert r_close.status_code == 200
    assert r_close.get_json()['pnl'] > 0

    r_card = client.get('/api/trading/paper/scorecard')
    assert r_card.status_code == 200
    assert r_card.get_json()['scorecard']['closed_trades'] == 1
    assert r_card.get_json()['scorecard']['current_equity_usd'] > 500.0
