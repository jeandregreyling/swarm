"""Disciplined $500-Cap Paper-Trading Risk Engine & Scorecard for Hummingbird Money Hub.

STRICT PAPER-ONLY MODE:
- Never places live brokerage orders or risks real capital.
- Enforces max 2.0% risk per trade (default 1.5%), mandatory stop-loss,
  15% max-drawdown circuit breaker, and honest 30-trade live-readiness gates.
"""
from __future__ import annotations

import math
from typing import Any

PAPER_ONLY = True
DEFAULT_STARTING_CAPITAL = 500.0
DEFAULT_RISK_PCT = 0.015       # 1.5% risk per trade ($7.50 on $500)
MAX_RISK_PCT = 0.02            # Hard ceiling: 2.0% ($10.00 on $500)
MAX_DRAWDOWN_HALT_PCT = 0.15   # Auto-halt trading at 15% drawdown
DEFAULT_GPU_GOAL_USD = 2400.0  # Target 32 GB GPU upgrade milestone


def size_position(
    equity: float,
    entry_price: float,
    stop_loss_price: float,
    side: str = 'buy',
    risk_pct: float = DEFAULT_RISK_PCT,
    take_profit_price: float | None = None,
) -> dict[str, Any]:
    """Calculate risk-capped position size with mandatory stop-loss validation."""
    eq = float(equity)
    entry = float(entry_price)
    stop = float(stop_loss_price)
    side_norm = str(side or 'buy').strip().lower()
    if eq <= 0:
        raise ValueError('equity must be positive')
    if entry <= 0 or stop <= 0:
        raise ValueError('entry_price and stop_loss_price must be positive')
    if side_norm not in ('buy', 'sell'):
        raise ValueError("side must be 'buy' or 'sell'")
    if side_norm == 'buy' and stop >= entry:
        raise ValueError('for buy trades, stop_loss_price must be strictly below entry_price')
    if side_norm == 'sell' and stop <= entry:
        raise ValueError('for sell trades, stop_loss_price must be strictly above entry_price')

    requested_risk = float(risk_pct)
    if requested_risk <= 0:
        raise ValueError('risk_pct must be positive')
    clamped_risk = min(requested_risk, MAX_RISK_PCT)
    risk_dollars = round(eq * clamped_risk, 4)
    stop_distance = abs(entry - stop)
    raw_qty = risk_dollars / stop_distance
    # Never exceed 100% cash equity (no margin/leverage on $500 seed capital)
    max_cash_qty = eq / entry
    qty = round(min(raw_qty, max_cash_qty), 6)
    notional = round(qty * entry, 2)
    actual_risk = round(qty * stop_distance, 2)

    rr_ratio = None
    if take_profit_price is not None:
        tp = float(take_profit_price)
        reward_dist = (tp - entry) if side_norm == 'buy' else (entry - tp)
        if reward_dist <= 0:
            raise ValueError('take_profit_price must be on the profitable side of entry_price')
        rr_ratio = round(reward_dist / stop_distance, 2)

    return {
        'paper_only': PAPER_ONLY,
        'side': side_norm,
        'equity': round(eq, 2),
        'entry_price': entry,
        'stop_loss_price': stop,
        'take_profit_price': float(take_profit_price) if take_profit_price is not None else None,
        'risk_pct_applied': round(clamped_risk, 4),
        'risk_clamped': requested_risk > MAX_RISK_PCT,
        'quantity': qty,
        'notional_usd': notional,
        'max_loss_usd': actual_risk,
        'reward_to_risk': rr_ratio,
    }


def evaluate_portfolio_scorecard(
    closed_trades: list[dict[str, Any]],
    starting_capital: float = DEFAULT_STARTING_CAPITAL,
    gpu_goal: float = DEFAULT_GPU_GOAL_USD,
) -> dict[str, Any]:
    """Compute equity curve, win rate, profit factor, max drawdown, Sharpe, and live-readiness verdict."""
    start = max(1.0, float(starting_capital))
    equity = start
    peak = start
    max_dd = 0.0
    pnls: list[float] = []
    wins = 0
    gross_win = 0.0
    gross_loss = 0.0

    for t in closed_trades or []:
        pnl = float(t.get('pnl') or 0.0)
        pnls.append(pnl)
        equity += pnl
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
        if pnl > 0:
            wins += 1
            gross_win += pnl
        elif pnl < 0:
            gross_loss += abs(pnl)

    n = len(pnls)
    total_pnl = round(equity - start, 2)
    return_pct = round((total_pnl / start) * 100.0, 2)
    win_rate = round((wins / n) * 100.0, 2) if n else 0.0
    expectancy = round(total_pnl / n, 2) if n else 0.0
    if gross_loss > 0:
        profit_factor = round(gross_win / gross_loss, 2)
    elif gross_win > 0:
        profit_factor = 99.0
    else:
        profit_factor = 0.0

    sharpe = 0.0
    if n >= 2:
        mean_r = sum(pnls) / n
        var = sum((x - mean_r) ** 2 for x in pnls) / (n - 1)
        std = math.sqrt(var)
        if std > 1e-9:
            sharpe = round((mean_r / std) * math.sqrt(n), 2)

    circuit_breaker = max_dd >= MAX_DRAWDOWN_HALT_PCT or equity <= start * (1.0 - MAX_DRAWDOWN_HALT_PCT)
    gpu_progress = round(max(0.0, min(100.0, (max(0.0, total_pnl) / max(1.0, float(gpu_goal))) * 100.0)), 2)

    gates = {
        'min_30_closed_paper_trades': n >= 30,
        'profit_factor_gte_1_3': profit_factor >= 1.3,
        'max_drawdown_under_10pct': max_dd < 0.10,
        'positive_expectancy': expectancy > 0,
        'circuit_breaker_clear': not circuit_breaker,
    }
    ready_for_owner_review = all(gates.values())
    verdict = (
        'READY_FOR_OWNER_REVIEW (still paper-only until owner explicitly signs off)'
        if ready_for_owner_review
        else 'STAY_IN_PAPER_LAB (collect >=30 disciplined paper trades with PF>=1.3 and DD<10%)'
    )

    return {
        'paper_only': PAPER_ONLY,
        'starting_capital_usd': round(start, 2),
        'current_equity_usd': round(equity, 2),
        'total_pnl_usd': total_pnl,
        'return_pct': return_pct,
        'closed_trades': n,
        'win_rate_pct': win_rate,
        'profit_factor': profit_factor,
        'expectancy_usd': expectancy,
        'max_drawdown_pct': round(max_dd * 100.0, 2),
        'sharpe_ratio': sharpe,
        'circuit_breaker_tripped': circuit_breaker,
        'gpu_goal_usd': round(float(gpu_goal), 2),
        'gpu_goal_progress_pct': gpu_progress,
        'gates': gates,
        'live_readiness_verdict': verdict,
    }
