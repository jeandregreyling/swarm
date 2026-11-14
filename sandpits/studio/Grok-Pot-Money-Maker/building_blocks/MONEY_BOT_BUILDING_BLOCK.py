from collections.abc import Iterable
from datetime import datetime

import pandas as pd
import yfinance as yf


DEFAULT_TICKERS = ("VOO", "SPY", "AAPL", "MSFT")


def run_daily_money_scan(tickers: Iterable[str] | None = None) -> pd.DataFrame:
    """Print a read-only summary of recent daily market data."""
    if tickers is None:
        tickers = DEFAULT_TICKERS
    elif isinstance(tickers, str):
        raise TypeError("tickers must be an iterable of ticker symbols, not a string")

    data = {}
    for ticker in tickers:
        symbol = ticker.strip().upper()
        if not symbol:
            raise ValueError("ticker symbols must not be empty")

        stock = yf.Ticker(symbol)
        hist = stock.history(period='5d')
        if not hist.empty:
            closes = hist['Close'].dropna()
            volumes = hist['Volume'].dropna()
            if closes.empty:
                continue

            if len(volumes) < 2:
                volume_trend = 'Unavailable'
            elif volumes.iloc[-1] > volumes.iloc[:-1].mean():
                volume_trend = 'Up'
            else:
                volume_trend = 'Stable'

            data[symbol] = {
                'Latest Close': round(closes.iloc[-1], 2),
                '5d Change %': (
                    round(((closes.iloc[-1] / closes.iloc[0]) - 1) * 100, 2)
                    if len(closes) > 1
                    else None
                ),
                'Volume Trend': volume_trend,
            }

    report = pd.DataFrame.from_dict(data, orient='index')
    print(f"\n=== Daily Money Scan - {datetime.now().date()} ===")
    print(report)
    return report


# Test run
if __name__ == "__main__":
    run_daily_money_scan()
