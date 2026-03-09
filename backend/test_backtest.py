from schemas import BacktestRequest, ConditionGroup, Condition, RiskManagement
from backtest_engine import BacktestEngine

def main():
    engine = BacktestEngine()
    req = BacktestRequest(
        symbols=["005930"], # Samsung Electronics
        entry=ConditionGroup(
            logic="AND",
            conditions=[
                Condition(
                    type="indicator",
                    id="ma_cross",
                    params={"ma1_period": 5, "ma2_period": 20, "type": "Golden Cross"}
                )
            ]
        ),
        exit=ConditionGroup(
            logic="AND",
            conditions=[
                Condition(
                    type="indicator",
                    id="ma_cross",
                    params={"ma1_period": 5, "ma2_period": 20, "type": "Dead Cross"}
                )
            ]
        ),
        risk=RiskManagement(
            position_size_pct=100.0,
            max_positions=10,
            init_cash=10_000_000,
            allocation_type="equal"
        ),
        period="5Y"
    )
    res = engine.run_backtest(req.model_dump())
    print("Total Return:", res["totalReturn"])
    print("CAGR:", res["cagr"])
    print("Win Rate:", res["winRate"])
    print("Max Drawdown:", res["maxDrawdown"])

if __name__ == "__main__":
    main()
