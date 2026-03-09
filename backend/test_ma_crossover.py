from schemas import BacktestRequest
from backtest_engine import BacktestEngine
import traceback

def main():
    try:
        engine = BacktestEngine()
        
        req = {
            "symbols": ["005930", "000660", "035420", "035720", "068270"], 
            "entry": {
                "logic": "AND",
                "conditions": [
                    {
                        "type": "indicator", 
                        "id": "ma_crossover", 
                        "params": {"short_period": 5, "long_period": 20, "signalType": "buy"}
                    }
                ]
            },
            "exit": {
                "logic": "AND",
                "conditions": [
                    {
                        "type": "indicator", 
                        "id": "ma_crossover", 
                        "params": {"short_period": 5, "long_period": 20, "signalType": "sell"}
                    }
                ]
            },
            "risk": {
                "position_size_pct": 100.0,
                "max_positions": 5,
                "init_cash": 10000000.0,
                "allocation_type": "equal",
                "skip_risk_management": False,
                "skip_position_setting": False,
                "execution_timing": "next_open",
                "stop_loss_pct": 5.0,  # 5% SL
                "take_profit_pct": 10.0, # 10% TP
                "ranking_enabled": True
            },
            "period": "10Y"
        }

        res = engine.run_backtest(req)
        print("--- SUMMARY (SL 5% / TP 10%) ---")
        print(f"Total Return: {res.get('totalReturn', 0):.2f}%")
        print(f"CAGR: {res.get('cagr', 0):.2f}%")
        print(f"Profit Factor: {res.get('profitFactor', 0):.2f}")
        print(f"Win Rate: {res.get('winRate', 0):.2f}%")
        print(f"Trades Count: {res.get('trades', 0)}")
        
    except Exception as e:
        traceback.print_exc()

if __name__ == "__main__":
    main()
