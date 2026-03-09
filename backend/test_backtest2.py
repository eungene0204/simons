from schemas import BacktestRequest
from backtest_engine import BacktestEngine

def main():
    engine = BacktestEngine()
    
    # We'll use a simple RSI condition that triggers often
    req = {
        "symbols": ["005930", "000660"], # Samsung, Hynix
        "entry": {
            "logic": "AND",
            "conditions": [
                {"type": "indicator", "id": "rsi", "params": {"period": 14, "condition": "Crosses Over", "value": 30}}
            ]
        },
        "exit": {
            "logic": "AND",
            "conditions": [
                {"type": "indicator", "id": "rsi", "params": {"period": 14, "condition": "Crosses Under", "value": 70}}
            ]
        },
        "risk": {
            "position_size_pct": 100.0,
            "max_positions": 2,
            "init_cash": 10000000.0,
            "allocation_type": "equal",
            "skip_risk_management": True,
            "skip_position_setting": False
        },
        "period": "10Y"
    }

    res = engine.run_backtest(req)
    print("Total Return:", res.get("totalReturn"))
    print("CAGR:", res.get("cagr"))
    print("Win Rate:", res.get("winRate"))
    print("Max Drawdown:", res.get("maxDrawdown"))

if __name__ == "__main__":
    main()
