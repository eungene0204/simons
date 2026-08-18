import vectorbt as vbt
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional

from engine.rebalance import compute_rebalance_dates

# ── 거래 비용 기본값 ──────────────────────────────────────────────────────────
# 매수/매도 수수료는 legacy 'fee_rate'(대칭)를 상속하고, 증권거래세는 매도측에만
# 부과한다(2025년 기준 0.15%). 'sell_tax_rate' 옵션으로 명시 제어(0 포함) 가능.
DEFAULT_FEE_RATE = 0.0015
DEFAULT_SELL_TAX_RATE = 0.0015
DEFAULT_SLIPPAGE_RATE = 0.0020

# 리밸런싱일에 목표 집합에서 빠져(조건 미충족·랭킹 이탈) 매도되는 청산의 정밀 사유.
# 신호/리스크 청산이 아니므로 결과 라벨이 추상적인 '전략 매도 조건 충족'으로 뭉개지지
# 않도록 시뮬레이터가 직접 사유를 기록한다.
REBALANCE_EXIT_REASON = "리밸런싱 제외 (목표 종목 이탈)"


def select_ranked_targets(cand_sorted, eff_max_pos, sel_pct, sel_band, band_cap=None):
    """랭킹 내림차순 후보 배열에서 목표 종목을 고른다 (FR-BT-060).

    - sel_band=[g, G]: 후보를 종목 수 기준 G등분했을 때 g번째 구간(1=랭킹 최상위 구간).
      분위(퀀타일) 그룹 백테스트가 사용한다. 경계는 round((g-1)*n/G)~round(g*n/G)로
      G개 그룹의 합집합이 전체 후보와 일치한다(누락·중복 없음).
    - band_cap: 그룹당 보유 상한(FR-BT-060b) — 밴드 구간에서 랭킹 상위 N종목만.
      모든 그룹에 동일 적용되어 그룹 간 비교 규칙이 같다. 없으면 구간 전체.
    - sel_pct: 상위 비율(%) 선정 — '상위 10% 편입'. count = max(1, round(n*pct/100)).
    - 둘 다 없으면 기존 상위 K(eff_max_pos) 선정.
    """
    n = len(cand_sorted)
    if n == 0:
        return cand_sorted
    if sel_band:
        g, groups = int(sel_band[0]), int(sel_band[1])
        lo = round((g - 1) * n / groups)
        hi = n if g >= groups else round(g * n / groups)
        band = cand_sorted[lo:hi]
        if band_cap and int(band_cap) > 0:
            band = band[: int(band_cap)]
        return band
    if sel_pct:
        return cand_sorted[: max(1, round(n * float(sel_pct) / 100.0))]
    return cand_sorted[:eff_max_pos]


class Simulator:
    """신호 → 주문 변환 시뮬레이터.

    설계 원칙(감사 C1/C2/C5/C6/C7 반영):
    - 파이썬 루프가 '의도'(슬롯·스탑·리밸런싱)를 결정하고, vectorbt ``from_orders``
      가 목표비중(targetpercent) 주문으로 '체결'만 수행한다. from_signals의
      ``Percent``(잔여 현금 비중) 의미론이 만들던 기하급수 비중 감소·현금 드래그를
      제거하고, 진입 시점 NAV 대비 동일 비중을 보장한다.
    - ``size_granularity=1``: 한국 주식은 1주 단위 — 소수점 주식 체결 금지.
    - 스탑(SL/TP/트레일링)은 장중 low/high로 감지하고(종가 감지는 장중 리스크를
      누락), 체결은 기존 타이밍(same_close=당일 종가, next_open=익일 시가)의
      시장가로 수행한다 — 스탑 가격 '정확 체결' 가정(과대평가)을 배제.
    - 거래 불가일(available=False, 거래정지 등)에는 체결하지 않고 다음 거래
      가능일로 청산을 이월한다.
    """

    def run(self,
            price_df: pd.DataFrame,
            exec_price_df: pd.DataFrame,
            entries_df: pd.DataFrame,
            exits_df: pd.DataFrame,
            risk_params: Dict[str, Any],
            options: Dict[str, Any],
            rank_df: Optional[pd.DataFrame] = None,
            high_df: Optional[pd.DataFrame] = None,
            low_df: Optional[pd.DataFrame] = None,
            available_df: Optional[pd.DataFrame] = None) -> vbt.Portfolio:

        # {symbol: {날짜문자열: 정밀 청산 사유}} — 신호/리스크로 설명되지 않는 청산
        # (리밸런싱 편출 등)의 사유를 체결일 기준으로 남겨 result_handler가 우선 적용한다.
        self.exit_reason_overrides: Dict[str, Dict[str, str]] = {}
        # 매수 조건 충족 종목이 빈 자리(슬롯)보다 많아 순위가 골라야 했던 날 수(v16.3) —
        # 엔진이 "무엇이 골랐는지" 고지할지 판정하는 근거(랭킹을 말하지 않은 전략의 넘친 날).
        self.overflow_days: int = 0
        # 매수 조건이 후보를 정하는 전략(신호·재무 필터, 엔진이 표시). 리밸런싱을 켜도
        # 달력 회전이 아니라 조건이 진입·청산을 이끈다 — 순수 랭킹(선정=진입)과 구분.
        entry_signal_driven = bool(risk_params.get('entry_signal_driven', False))

        init_cash_raw = risk_params.get('init_cash')
        pos_size_raw = risk_params.get('position_size_pct')
        init_cash = float(init_cash_raw) if init_cash_raw is not None else 10000000.0
        pos_size_pct = float(pos_size_raw) if pos_size_raw is not None else 100.0
        max_pos = risk_params.get('max_positions')
        # 비율/분위 선정(FR-BT-060) — 있으면 상위 K(max_positions) 대신 후보 수 기준으로
        # 리밸런싱일마다 목표 종목 수를 동적으로 정한다.
        sel_pct = risk_params.get('max_positions_pct')
        sel_band = risk_params.get('ranking_band')
        band_cap = risk_params.get('ranking_group_cap')

        sl_pct = float(risk_params.get('stop_loss_pct') or 0)
        tp_pct = float(risk_params.get('take_profit_pct') or 0)
        ts_pct = float(risk_params.get('trailing_stop_pct') or 0)  # Fix 1
        max_hold = int(risk_params.get('max_holding_days') or 0)

        buy_fee, sell_fee = self._resolve_fee_rates(options)
        slippage_raw = options.get('slippage_rate')
        slippage_val = float(slippage_raw) if slippage_raw is not None else DEFAULT_SLIPPAGE_RATE
        exec_type = options.get('execution_type', 'same_close')

        skip_pos = risk_params.get('skip_position_setting', False)
        use_risk_mgmt = not risk_params.get('skip_risk_management', False)

        # Determine size per position (진입 시점 포트폴리오 NAV 대비 비중)
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
        # 아래 커스텀 루프(reconstitution)로 처리한다(현실 체결 유지).
        rebalance_dates = compute_rebalance_dates(
            entries_df.index, str(risk_params.get('rebalancing_period') or 'none')
        )
        rebalance_mode = (not skip_pos) and bool(max_pos or sel_pct or sel_band) and bool(rebalance_dates.any())
        has_position_risk = use_risk_mgmt and (sl_pct > 0 or tp_pct > 0 or ts_pct > 0 or max_hold > 0)
        # 매수 조건이 있는 전략은 순수 경로로 보내지 않는다(v16.3) — 그 경로는 매도 신호를
        # 읽지 않고 리밸런싱일이 아닌 날의 매수 신호도 버린다(순수 랭킹 회전 전용).
        if rebalance_mode and not has_position_risk and not entry_signal_driven:
            return self._run_target_rebalance(
                price_df, exec_price_df, entries_df, rank_df, rebalance_dates,
                eff_max_pos, init_cash, buy_fee, sell_fee, slippage_val,
                sel_pct=sel_pct, sel_band=sel_band, band_cap=band_cap,
            )

        symbols = entries_df.columns.tolist()
        num_symbols = len(symbols)
        n_rows = len(entries_df)

        price_values = price_df.values
        exec_price_values = exec_price_df.values
        entries_values = entries_df.values
        exits_values = exits_df.values.copy()
        # 장중 감지용 저가/고가. 미제공 시(레거시 호출·테스트) 종가로 폴백해
        # 기존 종가 감지와 동일하게 동작한다.
        high_values = high_df.values if high_df is not None else price_values
        low_values = low_df.values if low_df is not None else price_values
        # 거래 가능 마스크. 미제공 시 전일 거래 가능으로 간주.
        avail_values = (
            available_df.values.astype(bool)
            if available_df is not None
            else np.ones((n_rows, num_symbols), dtype=bool)
        )

        active_mask = np.zeros(num_symbols, dtype=bool)
        entry_day = np.full(num_symbols, -1, dtype=np.int64)
        entry_price = np.zeros(num_symbols, dtype=np.float64)
        peak_price = np.zeros(num_symbols, dtype=np.float64)   # Fix 1: trailing stop tracking
        pending_exit = np.zeros(num_symbols, dtype=bool)       # 거래정지 등으로 이월된 청산
        active_count = 0
        EPS = 1e-6

        # 체결일 라벨링용 날짜 문자열 + 예약된 정밀 청산 사유(리밸런싱 편출 등).
        # 사유는 청산이 '결정'된 시점에 예약하고, 실제 '체결'(_book_exit)될 때 그 날짜로
        # 남긴다(익일 시가·거래정지 이월로 결정일과 체결일이 다를 수 있으므로).
        date_strs = [pd.Timestamp(d).strftime('%Y-%m-%d') for d in entries_df.index]
        exit_reason_pending = np.empty(num_symbols, dtype=object)
        exit_reason_pending[:] = ""

        # 리스크 청산 사유는 시뮬레이터가 '왜 나갔는지'를 정확히 알고 있으므로 여기서
        # 확정해 exit_reason_overrides로 넘긴다. result_handler의 수익률-크기 추론은
        # same_close 체결(종가 청산)에서 실현수익률이 -sl%와 거의 항상 어긋나 진짜 손절을
        # '전략 매도 조건 충족'으로 오분류하던 문제가 있었다(라벨을 사유의 정답 소스로 통일).
        def _fmt_pct(v: float) -> str:
            return str(int(v)) if v == int(v) else str(v)
        sl_reason = f"손절매 실행 (-{_fmt_pct(sl_pct)}%)" if sl_pct > 0 else "손절매 실행"
        tp_reason = f"익절매 실행 (+{_fmt_pct(tp_pct)}%)" if tp_pct > 0 else "익절매 실행"
        ts_reason = f"트레일링 스탑 실행 (-{_fmt_pct(ts_pct)}%)" if ts_pct > 0 else "트레일링 스탑 실행"

        # from_orders 입력: NaN=주문 없음, 양수=진입 목표비중(NAV 대비), 0=전량 청산
        target_values = np.full((n_rows, num_symbols), np.nan)
        # 셀 단위 수수료: 매수 셀=매수 수수료, 매도 셀=매도 수수료+거래세
        fees_values = np.full((n_rows, num_symbols), buy_fee)

        def _book_exit(i: int, mask: np.ndarray) -> None:
            """보유 종목 mask를 i일에 청산: 주문(target 0)·수수료·부기를 동시 갱신.

            부기를 즉시 갱신해야 같은 날 빈 슬롯에 신규 편입이 가능하다(과거
            same_close 청산이 한 박자 늦게 반영되던 이중 부기 버그의 수정).
            """
            nonlocal active_count
            target_values[i, mask] = 0.0
            fees_values[i, mask] = sell_fee
            active_mask[mask] = False
            peak_price[mask] = 0.0
            active_count -= int(mask.sum())
            # 예약된 정밀 청산 사유가 있으면 체결일(i)에 기록하고 예약을 비운다.
            for s_idx in np.where(mask)[0]:
                r = exit_reason_pending[s_idx]
                if r:
                    self.exit_reason_overrides.setdefault(symbols[s_idx], {})[date_strs[i]] = r
                    exit_reason_pending[s_idx] = ""

        # ── 달력 기준 리밸런싱 (reconstitution) ──
        # '리밸런싱 + 봉중간 리스크(SL/TP 등)'가 섞인 경우와 매수 조건이 있는 전략의 리밸런싱
        # (순수 랭킹 리밸런싱은 위에서 from_orders 목표비중으로 분기됨). 리밸런싱일에 목표
        # 집합(후보 상위 K)을 재구성한다. 비리밸런싱일의 신규 진입은 순수 랭킹 회전에서만
        # 차단하고, 매수 조건 전략(entry_signal_driven)은 그날 신호도 빈 자리만큼 담는다(v16.3).
        # 주의: 이 경로는 유지 종목의 비중 리셋은 하지 않는다(reconstitution only) — 엔진이
        # 경고로 고지한다.
        current_target_mask = np.zeros(num_symbols, dtype=bool)
        rank_values_all = rank_df.values if rank_df is not None else None
        # 비율/분위 선정 모드에선 목표 종목 수가 리밸런싱일마다 달라진다 — 슬롯 상한과
        # 동일가중 비중을 그때그때 갱신한다(기본 모드에선 기존 정적 값 유지).
        cur_cap = eff_max_pos
        cur_size = size_per_pos

        for i in range(n_rows):
            # Step 0: 이월된 청산을 거래 가능일에 방출
            if pending_exit.any():
                releasable = pending_exit & avail_values[i]
                if releasable.any():
                    exits_values[i] |= releasable
                    pending_exit &= ~releasable

            # Step 1: 오늘 예정된 청산 처리 (신호 청산 + 방출된 이월 청산)
            exited = active_mask & exits_values[i].astype(bool)
            if exited.any():
                _book_exit(i, exited)

            # Step 2: 당일 리스크 평가 — 장중 low/high로 감지(종가 감지는 장중
            # 급락/급등을 놓친다), 체결은 exec_type 타이밍의 시장가.
            if active_mask.any():
                closes = price_values[i]
                highs = high_values[i]
                lows = low_values[i]

                # Fix 1: 보유 종목 고점 갱신 (장중 고가 기준)
                if ts_pct > 0:
                    peak_price = np.where(active_mask, np.maximum(peak_price, highs), peak_price)

                should_exit = np.zeros(num_symbols, dtype=bool)
                # 이미 청산 예약된 종목은 재평가/사유 덮어쓰기에서 제외한다.
                base = active_mask & ~pending_exit

                # Max holding days (vectorized) — 우선순위 최상위(보유기간 만료).
                # 사유 라벨은 result_handler가 실제 보유일수(exit_idx-entry_idx)로 정확히
                # 붙이므로(수익률 크기 무관) 여기서 override하지 않는다 — next_open 체결 시
                # 플래그일과 체결일이 달라 보유일수가 1 어긋나는 것을 피한다.
                if max_hold > 0:
                    should_exit |= base & ~should_exit & ((i - entry_day) >= max_hold)

                # SL / TP / Trailing stop (vectorized, no re-exit if already flagged)
                if use_risk_mgmt and (sl_pct > 0 or tp_pct > 0 or ts_pct > 0):
                    safe_entry = np.where(entry_price > 0, entry_price, 1.0)

                    if sl_pct > 0:
                        low_ret = (lows - safe_entry) / safe_entry * 100
                        hit = base & ~should_exit & (low_ret <= (-sl_pct + EPS))
                        exit_reason_pending[hit] = sl_reason
                        should_exit |= hit
                    if tp_pct > 0:
                        high_ret = (highs - safe_entry) / safe_entry * 100
                        hit = base & ~should_exit & (high_ret >= (tp_pct - EPS))
                        exit_reason_pending[hit] = tp_reason
                        should_exit |= hit

                    # Fix 1: Trailing stop — 고점 대비 낙폭(장중 저가)이 ts_pct 초과
                    if ts_pct > 0:
                        safe_peak = np.where(peak_price > 0, peak_price, 1.0)
                        drawdown = (lows - safe_peak) / safe_peak * 100
                        hit = base & ~should_exit & (drawdown <= (-ts_pct + EPS))
                        exit_reason_pending[hit] = ts_reason
                        should_exit |= hit
                if should_exit.any():
                    if exec_type == 'next_open' and i + 1 < n_rows:
                        # 익일 시가 체결 — 거래 가능일 도달 시 Step 0에서 방출
                        pending_exit |= should_exit
                    else:
                        # same_close(또는 마지막 봉): 당일 체결, 불가하면 이월
                        exec_now = should_exit & avail_values[i] & active_mask
                        pending_exit |= should_exit & ~avail_values[i]
                        if exec_now.any():
                            exits_values[i] |= exec_now
                            _book_exit(i, exec_now)

            # Rebalance step: 리밸런싱일에 목표 집합(후보 상위 K)을 다시 정하고,
            # 목표에서 빠진 보유 종목을 매도한다.
            if rebalance_mode and rebalance_dates[i]:
                cand = np.where(entries_values[i])[0]
                if rank_values_all is not None and len(cand) > 0:
                    cand = cand[np.argsort(-rank_values_all[i][cand])]
                sel = select_ranked_targets(cand, eff_max_pos, sel_pct, sel_band, band_cap)
                if len(sel) < len(cand):
                    self.overflow_days += 1
                current_target_mask = np.zeros(num_symbols, dtype=bool)
                current_target_mask[sel] = True
                if sel_pct or sel_band:
                    cur_cap = max(len(sel), 1)
                    if risk_params.get('allocation_type') == 'equal':
                        cur_size = 1.0 / cur_cap

                dropouts = active_mask & ~current_target_mask & ~pending_exit
                if dropouts.any():
                    # 정밀 사유 예약 — 즉시/이월 어느 경로로 체결되든 _book_exit이 남긴다.
                    exit_reason_pending[dropouts] = REBALANCE_EXIT_REASON
                    # 편출 결정의 근거(신호·랭킹)는 next_open이면 엔진이 이미 1일 shift해 둔
                    # 전일 정보이므로, 당일 intraday 정보로 결정되는 리스크 청산(다음 시가 체결)과
                    # 달리 당일 체결한다 — 신규 편입(같은 날)과 체결일이 하루 어긋나던 비대칭 제거.
                    # 거래 불가일만 이월한다.
                    exec_now = dropouts & avail_values[i]
                    pending_exit |= dropouts & ~avail_values[i]
                    if exec_now.any():
                        exits_values[i] |= exec_now
                        _book_exit(i, exec_now)

            # Step 3: Process new entries after exits freed slots.
            # 리밸런싱 모드에서는 '현재 목표 집합'만 진입 후보로 본다(목표가 채워질
            # 때까지 후속 거래일에도 빈 슬롯을 메운다). 같은 날 청산이 예정/실행된
            # 종목은 재진입 금지(동일 셀에 매수·매도 주문이 겹칠 수 없음).
            blocked = active_mask | exits_values[i].astype(bool) | pending_exit | ~avail_values[i]
            if rebalance_mode and not entry_signal_driven:
                # 순수 랭킹 회전: 목표 집합만 채운다(리밸런싱일 사이엔 신규 진입 없음).
                entry_pool = current_target_mask & ~blocked
            else:
                # 매수 조건이 후보를 정한다 — 리밸런싱일이 아닌 날의 신호도 빈 자리만큼
                # 담는다(v16.3). 리밸런싱일에는 위에서 편출을 끝낸 뒤 그날 후보로 다시 채운다.
                entry_pool = entries_values[i] & ~blocked
            candidate_indices = np.where(entry_pool)[0]

            if len(candidate_indices) > 0:
                free_slots = cur_cap - active_count
                if 0 < free_slots < len(candidate_indices) and not (rebalance_mode and rebalance_dates[i]):
                    # 리밸런싱일은 위 Rebalance step에서 이미 셌다 — 이중 계수 방지.
                    self.overflow_days += 1
                if rank_values_all is not None:
                    today_ranks = rank_values_all[i]
                    candidate_indices = candidate_indices[np.argsort(-today_ranks[candidate_indices])]

                for s_idx in candidate_indices:
                    if active_count < cur_cap:
                        ep = exec_price_values[i, s_idx]
                        active_mask[s_idx] = True
                        active_count += 1
                        entry_day[s_idx] = i
                        entry_price[s_idx] = ep
                        peak_price[s_idx] = ep   # Fix 1: init peak at entry price
                        target_values[i, s_idx] = cur_size
                        fees_values[i, s_idx] = buy_fee

        target_df = pd.DataFrame(target_values, index=entries_df.index, columns=entries_df.columns)

        # NOTE: sl_stop/tp_stop/sl_trail은 의도적으로 vbt에 넘기지 않는다. 위 루프가
        # 감지한 청산을 목표비중 0 주문으로 주입하며, 체결은 exec_price(시장가)로
        # 이뤄진다. vbt 내장 스탑은 '정확히 스탑 가격 체결'(갭 무시)을 가정해
        # 리스크 관리를 인위적으로 완벽하게 만들기 때문.
        return vbt.Portfolio.from_orders(
            close=price_df,
            size=target_df,
            size_type='targetpercent',
            price=exec_price_df,
            fees=fees_values,
            slippage=slippage_val,
            init_cash=init_cash,
            cash_sharing=True,
            group_by=True,
            call_seq='auto',          # 매도 → 매수 순서: 청산 현금으로 신규 편입
            direction='longonly',
            size_granularity=1.0,     # 정수 주식 단위 (소수점 주식 금지)
            freq='D',
        )

    @staticmethod
    def _resolve_fee_rates(options: Dict[str, Any]) -> tuple:
        """(매수 수수료율, 매도 수수료율+거래세율)을 옵션에서 해석한다.

        - buy_fee_rate / sell_fee_rate: 명시 시 legacy fee_rate보다 우선.
        - sell_tax_rate: 증권거래세(매도측). 기본 0.15%, 0으로 명시 시 미부과.
        """
        fee_rate_raw = options.get('fee_rate')
        fee_rate = float(fee_rate_raw) if fee_rate_raw is not None else DEFAULT_FEE_RATE

        buy_raw = options.get('buy_fee_rate')
        sell_raw = options.get('sell_fee_rate')
        tax_raw = options.get('sell_tax_rate')

        buy_fee = float(buy_raw) if buy_raw is not None else fee_rate
        sell_fee = float(sell_raw) if sell_raw is not None else fee_rate
        sell_tax = float(tax_raw) if tax_raw is not None else DEFAULT_SELL_TAX_RATE
        return buy_fee, sell_fee + sell_tax

    def _run_target_rebalance(self,
                              price_df: pd.DataFrame,
                              exec_price_df: pd.DataFrame,
                              entries_df: pd.DataFrame,
                              rank_df: Optional[pd.DataFrame],
                              rebalance_dates: np.ndarray,
                              eff_max_pos: int,
                              init_cash: float,
                              buy_fee: float,
                              sell_fee: float,
                              slippage_val: float,
                              sel_pct: Optional[float] = None,
                              sel_band: Optional[list] = None,
                              band_cap: Optional[int] = None) -> vbt.Portfolio:
        """순수 리밸런싱 경로 — vbt 네이티브 from_orders(목표비중)로 비중 리셋까지 수행.

        리밸런싱일마다 후보(entries=True)를 rank 상위 K로 골라 동일가중 목표비중을 주고,
        목표에서 빠진 보유는 비중 0으로 청산한다. 비리밸런싱일은 NaN(주문 없음 = 보유 유지).
        call_seq='auto'로 매도→매수 순서를 보장해 청산 현금으로 신규 편입을 채운다.

        수수료: 목표비중 0 셀은 매도 비용(수수료+거래세), 양수 셀은 매수 수수료를
        적용한다. 유지 종목의 비중 리셋 트림(소량 매도)에는 매수 수수료가 적용되는
        근사가 남는다(트림 규모가 작아 영향 미미).
        """
        num_rows, num_syms = entries_df.shape
        entries_values = entries_df.values
        rank_values = rank_df.values if rank_df is not None else None

        symbols = entries_df.columns.tolist()
        date_strs = [pd.Timestamp(d).strftime('%Y-%m-%d') for d in entries_df.index]
        held = np.zeros(num_syms, dtype=bool)   # 직전 리밸런싱에서 목표비중을 받은 보유 종목

        target = np.full((num_rows, num_syms), np.nan)
        for i in np.where(rebalance_dates)[0]:
            cand = np.where(entries_values[i])[0]
            if rank_values is not None and len(cand) > 0:
                cand = cand[np.argsort(-rank_values[i][cand])]
            sel = select_ranked_targets(cand, eff_max_pos, sel_pct, sel_band, band_cap)
            if len(sel) < len(cand):
                self.overflow_days += 1
            row = np.zeros(num_syms)            # 0 = 목표에서 빠진 보유는 전량 청산
            if len(sel) > 0:
                row[sel] = 1.0 / len(sel)        # 동일가중 목표비중 (비중 리셋)
            # 보유 중이던 종목이 목표에서 빠지면(비중 0) 리밸런싱 편출로 매도된다.
            dropouts = np.where(held & (row == 0.0))[0]
            for s_idx in dropouts:
                self.exit_reason_overrides.setdefault(
                    symbols[s_idx], {}
                )[date_strs[i]] = REBALANCE_EXIT_REASON
            held = row > 0.0
            target[i, :] = row

        # 여기서 next_open을 다시 shift하지 않는다 — 엔진(backtest_engine)이 next_open일 때
        # 신호·랭킹을 이미 1일 shift해 넘기므로(row i = 전일 종가 정보 = 체결일), 추가 shift는
        # 체결을 하루 더 늦추는 이중 지연이었다(커스텀 루프 경로와 체결일이 어긋나던 버그).
        target_df = pd.DataFrame(target, index=entries_df.index, columns=entries_df.columns)

        fees_values = np.where(target_df.values == 0.0, sell_fee, buy_fee)

        return vbt.Portfolio.from_orders(
            close=price_df,
            size=target_df,
            size_type='targetpercent',
            price=exec_price_df,
            fees=fees_values,
            slippage=slippage_val,
            init_cash=init_cash,
            cash_sharing=True,
            group_by=True,
            call_seq='auto',
            direction='longonly',
            size_granularity=1.0,     # 정수 주식 단위
            freq='D',
        )
