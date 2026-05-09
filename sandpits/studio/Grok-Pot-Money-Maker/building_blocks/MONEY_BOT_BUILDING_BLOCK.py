import yfinance as yf
import pandas as pd
from datetime import datetime

def run_daily_money_scan(tickers=['VOO', 'SPY', 'AAPL', 'MSFT']):
    '''Safe stock scanner - no crypto, no leverage, small $ friendly.'''
    data = {}
    for t in tickers:
        stock = yf.Ticker(t)
        hist = stock.history(period='5d')
        if not hist.empty:
            data[t] = {
                'Current Price': round(hist['Close'].iloc[-1], 2),
                '5d Change %': round(((hist['Close'].iloc[-1] / hist['Close'].iloc[0]) - 1) * 100, 2),
                'Volume Trend': 'Up' if hist['Volume'].iloc[-1] > hist['Volume'].mean() else 'Stable'
            }
    report = pd.DataFrame(data).T
    print(f"\n=== Daily Money Scan - {datetime.now().date()} ===")
    print(report)
    return report

# Test run
if __name__ == "__main__":
    run_daily_money_scan()