import vectorbt as vbt
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional


class Simulator:
    def run(self,
            price_df: pd.DataFrame,
            exec_price_df: pd.DataFrame,
            entries_df: pd.DataFrame,
            exits_df: pd.DataFrame,
            risk_params: Dict[str, Any],
            options: Dict[str, Any],
            rank_df: Optional[pd.DataFrame] = None) -> vbt.Portfolio:

        # 1. Copy Signal Inputs to avoid side effects
        entries_df = entries_df.copy()
        exits_df = exits_df.copy()

        init_cash = float(risk_params.get('init_cash') or 10000000.0)
        pos_size_pct = float(risk_params.get('position_size_pct') or 100.0)
        max_pos = risk_params.get('max_positions')

        sl_pct = float(risk_params.get('stop_loss_pct') or 0)
        tp_pct = float(risk_params.get('take_profit_pct') or 0)
        ts_pct = float(risk_params.get('trailing_stop_pct') or 0)  # Fix 1
        max_hold = int(risk_params.get('max_holding_days') or 0)

        fee_rate = float(options.get('fee_rate') or 0.0015)
        slippage_val = float(options.get('slippage_rate') or 0.0020)

        skip_pos = risk_params.get('skip_position_setting', False)
        use_risk_mgmt = not risk_params.get('skip_risk_management', False)

        # Determine size per position (relative to FULL portfolio NAV)
        if risk_params.get('allocation_type') == 'equal':
            size_per_pos = 1.0 / max_pos if max_pos and max_pos > 0 else 1.0 / len(entries_df.columns)
        else:
            size_per_pos = pos_size_pct / 100.0
            if max_pos and max_pos > 0:
                max_allowed_size = 1.0 / max_pos
                if size_per_pos > max_allowed_size:
                    size_per_pos = max_allowed_size

        if skip_pos:
            eff_max_pos = len(entries_df.columns)
        else:
            eff_max_pos = max_pos if max_pos is not None else len(entries_df.columns)

        # Fix 1: ts_pct now included so trailing stop triggers the custom loop
        has_custom_loop = (not skip_pos) or (
            use_risk_mgmt and (max_hold > 0 or sl_pct > 0 or tp_pct > 0 or ts_pct > 0)
        )

        if has_custom_loop:
            symbols = entries_df.columns.tolist()
            num_symbols = len(symbols)

            price_values = price_df.values
            exec_price_values = exec_price_df.values
            entries_values = entries_df.values
            exits_values = exits_df.values.copy()
            filtered_entries_values = entries_values.copy()

            active_mask = np.zeros(num_symbols, dtype=bool)
            entry_day = np.full(num_symbols, -1, dtype=np.int64)
            entry_price = np.zeros(num_symbols, dtype=np.float64)
            peak_price = np.zeros(num_symbols, dtype=np.float64)   # Fix 1: trailing stop tracking
            active_count = 0
            EPS = 1e-6

            for i in range(len(entries_df)):
                # Fix 5: Vectorized step 1 — process deferred exits from previous day
                exited = active_mask & exits_values[i].astype(bool)
                if exited.any():
                    active_mask[exited] = False
                    peak_price[exited] = 0.0   # Fix 1: reset peak on exit
                    active_count -= int(exited.sum())

                # Fix 5: Vectorized step 2 — evaluate same-day risk exits
                # 당일 close로 조건을 감지하고 당일 exits_values[i]에 주입한다.
                # Step 1이 이미 실행된 이후이므로 중복 처리 없음.
                # VectorBT는 exits_df[i]=True 를 보고 당일 exec_price로 청산 실행.
                if active_mask.any():
                    active_prices = price_values[i]

                    # Fix 1: Update peak prices for all currently-held positions
                    if ts_pct > 0:
                        peak_price = np.where(active_mask, np.maximum(peak_price, active_prices), peak_price)

                    should_exit = np.zeros(num_symbols, dtype=bool)

                    # Max holding days (vectorized)
                    if max_hold > 0:
                        should_exit |= active_mask & ((i - entry_day) >= max_hold)

                    # SL / TP / Trailing stop (vectorized, no re-exit if already flagged)
                    if use_risk_mgmt and (sl_pct > 0 or tp_pct > 0 or ts_pct > 0):
                        safe_entry = np.where(entry_price > 0, entry_price, 1.0)
                        pct_ret = (active_prices - safe_entry) / safe_entry * 100

                        if sl_pct > 0:
                            should_exit |= active_mask & ~should_exit & (pct_ret <= (-sl_pct + EPS))
                        if tp_pct > 0:
                            should_exit |= active_mask & ~should_exit & (pct_ret >= (tp_pct - EPS))

                        # Fix 1: Trailing stop — exit when drawdown from peak exceeds ts_pct
                        if ts_pct > 0:
                            safe_peak = np.where(peak_price > 0, peak_price, 1.0)
                            drawdown = (active_prices - safe_peak) / safe_peak * 100
                            should_exit |= active_mask & ~should_exit & (drawdown <= (-ts_pct + EPS))

                    if should_exit.any():
                        exits_values[i] |= should_exit

                # Step 3: Process new entries after exits freed slots
                candidate_indices = np.where(entries_values[i] & ~active_mask)[0]

                if len(candidate_indices) > 0:
                    if rank_df is not None:
                        today_ranks = rank_df.iloc[i].values
                        candidate_indices = candidate_indices[np.argsort(-today_ranks[candidate_indices])]

                    for s_idx in candidate_indices:
                        if active_count < eff_max_pos:
                            ep = exec_price_values[i, s_idx]
                            active_mask[s_idx] = True
                            active_count += 1
                            entry_day[s_idx] = i
                            entry_price[s_idx] = ep
                            peak_price[s_idx] = ep   # Fix 1: init peak at entry price
                        else:
                            filtered_entries_values[i, s_idx] = False

            entries_df = pd.DataFrame(filtered_entries_values, index=entries_df.index, columns=entries_df.columns)
            exits_df = pd.DataFrame(exits_values, index=exits_df.index, columns=exits_df.columns)

        # NOTE: sl_stop/tp_stop/sl_trail are intentionally NOT passed to VectorBT.
        # Our custom simulation loop above already injects exit signals into exits_df
        # when SL/TP/trailing stop conditions are met. VectorBT's built-in mechanism
        # fills at the EXACT stop price (ignoring overnight gaps and real market
        # execution), which creates artificially perfect risk management and inflates
        # the Profit Factor. By relying solely on exits_df, exits happen at the
        # next available market price (exec_price_df), which is realistic.
        vbt_kwargs = dict(
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
            cash_sharing=True
        )

        pf = vbt.Portfolio.from_signals(
            close=price_df,
            price=exec_price_df,
            entries=entries_df,
            exits=exits_df,
            **vbt_kwargs
        )

        return pf
