import vectorbt as vbt
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional

from engine.rebalance import compute_rebalance_dates


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

        init_cash_raw = risk_params.get('init_cash')
        pos_size_raw = risk_params.get('position_size_pct')
        init_cash = float(init_cash_raw) if init_cash_raw is not None else 10000000.0
        pos_size_pct = float(pos_size_raw) if pos_size_raw is not None else 100.0
        max_pos = risk_params.get('max_positions')

        sl_pct = float(risk_params.get('stop_loss_pct') or 0)
        tp_pct = float(risk_params.get('take_profit_pct') or 0)
        ts_pct = float(risk_params.get('trailing_stop_pct') or 0)  # Fix 1
        max_hold = int(risk_params.get('max_holding_days') or 0)

        fee_rate_raw = options.get('fee_rate')
        slippage_raw = options.get('slippage_rate')
        fee_rate = float(fee_rate_raw) if fee_rate_raw is not None else 0.0015
        slippage_val = float(slippage_raw) if slippage_raw is not None else 0.0020
        exec_type = options.get('execution_type', 'same_close')

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

        # ── 달력 기준 리밸런싱 라우팅 (하이브리드) ──
        # 순수 리밸런싱(개별 SL/TP/트레일링/보유기간 없음)은 vbt 네이티브 from_orders
        # 목표비중으로 처리해 '비중 리셋'까지 정확히 수행한다. 봉중간 리스크가 섞이면
        # 아래 from_signals 커스텀 루프(reconstitution)로 처리한다(현실 체결 유지).
        rebalance_dates = compute_rebalance_dates(
            entries_df.index, str(risk_params.get('rebalancing_period') or 'none')
        )
        rebalance_mode = (not skip_pos) and bool(max_pos) and bool(rebalance_dates.any())
        has_position_risk = use_risk_mgmt and (sl_pct > 0 or tp_pct > 0 or ts_pct > 0 or max_hold > 0)
        if rebalance_mode and not has_position_risk:
            return self._run_target_rebalance(
                price_df, exec_price_df, entries_df, rank_df, rebalance_dates,
                eff_max_pos, exec_type, init_cash, fee_rate, slippage_val,
            )

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

            # ── 달력 기준 리밸런싱 (reconstitution) ──
            # 여기는 '리밸런싱 + 봉중간 리스크(SL/TP 등)'가 섞인 경우다(순수 리밸런싱은
            # 위에서 from_orders로 분기됨). 리밸런싱일에만 목표 집합(후보 상위 K)을 재구성한다:
            # 목표 밖 보유는 매도, 목표 신규는 매수, 유지 종목은 그대로. 비리밸런싱일엔 신규 진입 차단.
            # rebalance_dates / rebalance_mode 는 run() 상단에서 이미 계산됨.
            current_target_mask = np.zeros(num_symbols, dtype=bool)
            rank_values_all = rank_df.values if rank_df is not None else None

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
                        if exec_type == 'next_open' and i + 1 < len(entries_df):
                            exits_values[i + 1] |= should_exit
                        else:
                            exits_values[i] |= should_exit

                # Rebalance step: 리밸런싱일에 목표 집합(후보 상위 K)을 다시 정하고,
                # 목표에서 빠진 보유 종목을 매도한다(청산 타이밍은 리스크 청산과 동일).
                if rebalance_mode and rebalance_dates[i]:
                    cand = np.where(entries_values[i])[0]
                    if rank_values_all is not None and len(cand) > 0:
                        cand = cand[np.argsort(-rank_values_all[i][cand])]
                    current_target_mask = np.zeros(num_symbols, dtype=bool)
                    current_target_mask[cand[:eff_max_pos]] = True

                    dropouts = active_mask & ~current_target_mask
                    if dropouts.any():
                        if exec_type == 'next_open' and i + 1 < len(entries_df):
                            exits_values[i + 1] |= dropouts
                        else:
                            exits_values[i] |= dropouts
                            # 당일(same_close) 청산은 vbt가 같은 날 처리하므로, 같은 날
                            # 빈 슬롯에 신규 편입이 들어갈 수 있도록 부기도 즉시 갱신한다.
                            # (Step 1은 이번 반복에서 이미 실행되어 갱신 기회가 없음 — 그대로
                            # 두면 active_count가 한 박자 늦어 신규 편입이 막힌다.)
                            active_mask[dropouts] = False
                            peak_price[dropouts] = 0.0
                            active_count -= int(dropouts.sum())

                # Step 3: Process new entries after exits freed slots.
                # 리밸런싱 모드에서는 '현재 목표 집합'만 진입 후보로 본다(목표가 채워질 때까지
                # 후속 거래일에도 빈 슬롯을 메운다). 비리밸런싱 모드는 기존처럼 진입 신호를 따른다.
                if rebalance_mode:
                    filtered_entries_values[i, :] = False  # 명시적으로 진입한 종목만 True
                    entry_pool = current_target_mask & ~active_mask
                else:
                    entry_pool = entries_values[i] & ~active_mask
                candidate_indices = np.where(entry_pool)[0]

                if len(candidate_indices) > 0:
                    if rank_values_all is not None:
                        today_ranks = rank_values_all[i]
                        candidate_indices = candidate_indices[np.argsort(-today_ranks[candidate_indices])]

                    for s_idx in candidate_indices:
                        if active_count < eff_max_pos:
                            ep = exec_price_values[i, s_idx]
                            active_mask[s_idx] = True
                            active_count += 1
                            entry_day[s_idx] = i
                            entry_price[s_idx] = ep
                            peak_price[s_idx] = ep   # Fix 1: init peak at entry price
                            filtered_entries_values[i, s_idx] = True
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

    def _run_target_rebalance(self,
                              price_df: pd.DataFrame,
                              exec_price_df: pd.DataFrame,
                              entries_df: pd.DataFrame,
                              rank_df: Optional[pd.DataFrame],
                              rebalance_dates: np.ndarray,
                              eff_max_pos: int,
                              exec_type: str,
                              init_cash: float,
                              fee_rate: float,
                              slippage_val: float) -> vbt.Portfolio:
        """순수 리밸런싱 경로 — vbt 네이티브 from_orders(목표비중)로 비중 리셋까지 수행.

        리밸런싱일마다 후보(entries=True)를 rank 상위 K로 골라 동일가중 목표비중을 주고,
        목표에서 빠진 보유는 비중 0으로 청산한다. 비리밸런싱일은 NaN(주문 없음 = 보유 유지).
        call_seq='auto'로 매도→매수 순서를 보장해 청산 현금으로 신규 편입을 채운다.
        """
        num_rows, num_syms = entries_df.shape
        entries_values = entries_df.values
        rank_values = rank_df.values if rank_df is not None else None

        target = np.full((num_rows, num_syms), np.nan)
        for i in np.where(rebalance_dates)[0]:
            cand = np.where(entries_values[i])[0]
            if rank_values is not None and len(cand) > 0:
                cand = cand[np.argsort(-rank_values[i][cand])]
            sel = cand[:eff_max_pos]
            row = np.zeros(num_syms)            # 0 = 목표에서 빠진 보유는 전량 청산
            if len(sel) > 0:
                row[sel] = 1.0 / len(sel)        # 동일가중 목표비중 (비중 리셋)
            target[i, :] = row

        target_df = pd.DataFrame(target, index=entries_df.index, columns=entries_df.columns)
        if exec_type == 'next_open':
            # 결정일 i의 주문을 다음 거래일(open)에 체결한다.
            target_df = target_df.shift(1)

        return vbt.Portfolio.from_orders(
            close=price_df,
            size=target_df,
            size_type='targetpercent',
            price=exec_price_df,
            fees=fee_rate,
            slippage=slippage_val,
            init_cash=init_cash,
            cash_sharing=True,
            group_by=True,
            call_seq='auto',
            direction='longonly',
            freq='D',
        )
