"""
Pure VectorBT backtest engine for comparison purposes.

Differences from the custom Simulator:
  - Uses VectorBT's native sl_stop / tp_stop / sl_trail parameters
    → fills at the EXACT stop price (ideal execution, no overnight gaps)
  - No custom position management loop (no max_positions cap, no ranking)
  - No same-day risk exit injection into exits_df
  - This intentionally produces "optimistic" risk management results
    so users can see the gap between ideal and realistic execution.
"""

import vectorbt as vbt
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional


class VectorBTNativeEngine:
    """Run a pure VectorBT backtest with native risk management."""

    def run(
        self,
        price_df: pd.DataFrame,
        exec_price_df: pd.DataFrame,
        entries_df: pd.DataFrame,
        exits_df: pd.DataFrame,
        risk_params: Dict[str, Any],
        options: Dict[str, Any],
    ) -> vbt.Portfolio:
        init_cash_raw = risk_params.get('init_cash')
        pos_size_raw = risk_params.get('position_size_pct')
        init_cash = float(init_cash_raw) if init_cash_raw is not None else 10_000_000.0
        pos_size_pct = float(pos_size_raw) if pos_size_raw is not None else 100.0
        max_pos = risk_params.get('max_positions')

        fee_rate_raw = options.get('fee_rate')
        slippage_raw = options.get('slippage_rate')
        fee_rate = float(fee_rate_raw) if fee_rate_raw is not None else 0.0015
        slippage_val = float(slippage_raw) if slippage_raw is not None else 0.0020

        skip_pos = risk_params.get('skip_position_setting', False)

        # Size per position
        if risk_params.get('allocation_type') == 'equal':
            size_per_pos = 1.0 / max_pos if max_pos and max_pos > 0 else 1.0 / len(entries_df.columns)
        else:
            size_per_pos = pos_size_pct / 100.0
            if max_pos and max_pos > 0:
                max_allowed_size = 1.0 / max_pos
                if size_per_pos > max_allowed_size:
                    size_per_pos = max_allowed_size

        # Risk management — use VBT native parameters
        sl_pct = float(risk_params.get('stop_loss_pct') or 0)
        tp_pct = float(risk_params.get('take_profit_pct') or 0)
        ts_pct = float(risk_params.get('trailing_stop_pct') or 0)
        use_risk = not risk_params.get('skip_risk_management', False)

        vbt_kwargs: Dict[str, Any] = dict(
            size=size_per_pos,
            size_type='Percent',
            init_cash=init_cash,
            fees=fee_rate,
            slippage=slippage_val,
            freq='D',
            allow_partial=False,
            direction='longonly',
            accumulate=False,
            group_by=True,
            cash_sharing=True,
        )

        # Inject native VBT risk stops (ideal execution at exact stop price)
        if use_risk:
            if sl_pct > 0:
                vbt_kwargs['sl_stop'] = sl_pct / 100.0
            if tp_pct > 0:
                vbt_kwargs['tp_stop'] = tp_pct / 100.0
            if ts_pct > 0:
                vbt_kwargs['sl_trail'] = ts_pct / 100.0

        pf = vbt.Portfolio.from_signals(
            close=price_df,
            price=exec_price_df,
            entries=entries_df,
            exits=exits_df,
            **vbt_kwargs,
        )

        return pf

    @staticmethod
    def extract_metrics(pf: vbt.Portfolio, common_index, init_cash: float) -> Dict[str, Any]:
        """Extract key metrics from a VBT Portfolio into a flat dict."""

        def safe(val):
            try:
                if val is None:
                    return 0.0
                if isinstance(val, (pd.Series, pd.Index, np.ndarray)):
                    if len(val) == 0:
                        return 0.0
                    m = val.mean()
                    return float(m)
                if isinstance(val, (int, float, np.number)):
                    if np.isnan(val) or np.isinf(val):
                        return 0.0
                    return float(val)
                return float(val)
            except Exception:
                return 0.0

        total_trades = len(pf.trades)
        win_count = len(pf.trades.winning)
        win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0.0

        avg_win = safe(pf.trades.winning.pnl.mean())
        avg_loss = abs(safe(pf.trades.losing.pnl.mean()))

        max_consecutive_wins = int(safe(pf.trades.winning_streak.max()))
        max_consecutive_losses = int(safe(pf.trades.losing_streak.max()))

        total_return_decimal = safe(pf.total_return())
        n_days = len(common_index)
        n_years = n_days / 252.0
        if n_years >= 1.0 and total_return_decimal > -1:
            cagr_val = ((1 + total_return_decimal) ** (1 / n_years) - 1) * 100
        else:
            cagr_val = total_return_decimal * 100

        # Benchmark
        bench_rets = pf.benchmark_returns()
        if isinstance(bench_rets, pd.DataFrame):
            bench_mean_rets = bench_rets.mean(axis=1)
        else:
            bench_mean_rets = bench_rets
        bench_cum = (1 + bench_mean_rets).cumprod()
        bench_total = bench_cum.iloc[-1] - 1 if len(bench_cum) > 0 else 0.0

        # Profit factor
        raw_pf = safe(pf.trades.profit_factor())
        if total_trades < 30 and raw_pf > 10.0:
            raw_pf = min(raw_pf, 10.0)

        def to_list(obj):
            if isinstance(obj, (pd.DataFrame, pd.Series)):
                return np.nan_to_num(obj.values.flatten(), nan=0.0, posinf=0.0, neginf=0.0).tolist()
            return [safe(x) for x in obj]

        equity_list = to_list(pf.value())
        final_equity = equity_list[-1] if equity_list else init_cash
        mdd_val = safe(pf.max_drawdown()) * 100
        calmar_val = cagr_val / abs(mdd_val) if mdd_val != 0 else 0.0

        avg_holding_days = 0.0
        try:
            if total_trades > 0 and 'entry_idx' in pf.trades.records and 'exit_idx' in pf.trades.records:
                avg_holding_days = float(np.mean(
                    pf.trades.records['exit_idx'].values.astype(float) -
                    pf.trades.records['entry_idx'].values.astype(float)
                ))
        except Exception:
            pass

        return {
            "totalReturn": safe(pf.total_return()) * 100,
            "cagr": cagr_val,
            "buyAndHoldReturn": safe(bench_total) * 100,
            "maxDrawdown": mdd_val,
            "winRate": win_rate,
            "profitFactor": raw_pf,
            "sharpe": safe(pf.sharpe_ratio()),
            "sortino": safe(pf.sortino_ratio()),
            "calmar": calmar_val,
            "avgHoldingDays": avg_holding_days,
            "volatility": float(np.nan_to_num(pf.returns(group_by=True).std() * np.sqrt(252), nan=0.0)) * 100,
            "trades": total_trades,
            "avgProfit": avg_win,
            "avgLoss": avg_loss,
            "maxConsecutiveWins": max_consecutive_wins,
            "maxConsecutiveLosses": max_consecutive_losses,
            "equity": equity_list,
            "benchmark_equity": to_list(init_cash * bench_cum),
            "dates": [d.strftime('%Y-%m-%d') for d in common_index],
            "finalEquity": final_equity,
            "initialCapital": init_cash,
        }
