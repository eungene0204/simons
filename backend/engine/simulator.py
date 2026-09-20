import vectorbt as vbt
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional

from engine.rebalance import compute_rebalance_dates
from engine import trade_reason as tr
from engine.transaction_tax import CURRENT_KR_SELL_TAX_RATE, kr_sell_tax_rates

# ── 거래 비용 기본값 ──────────────────────────────────────────────────────────
# 매수/매도 수수료는 legacy 'fee_rate'(대칭)를 상속하고, 증권거래세는 매도측에만
# 부과한다. 'sell_tax_rate'를 명시하지 않으면 매도 봉의 날짜에 맞는 **시행일 기준
# 법정 세율**(engine/transaction_tax.py, 0.30%→0.15%)을 쓴다 — 과거 매도에 현행
# 세율을 일괄 적용하면 장기 결과가 실제보다 유리해진다. 명시(0 포함)하면 고정 세율.
DEFAULT_FEE_RATE = 0.0015
DEFAULT_SELL_TAX_RATE = CURRENT_KR_SELL_TAX_RATE   # 현행(2025~) 세율 — 가상계좌 정산과 공유
DEFAULT_SLIPPAGE_RATE = 0.0020


def resolve_cost_rates(options: Dict[str, Any], index: pd.Index) -> tuple:
    """옵션에서 (매수 수수료율, 매도 수수료율, 봉별 거래세율 벡터)를 해석한다 — 시뮬레이터와
    결과 로그의 '적용 거래 비용' 동봉이 같은 해석을 본다.

    - buy_fee_rate / sell_fee_rate: 명시 시 legacy fee_rate보다 우선.
    - sell_tax_rate: 증권거래세(매도측). 명시하지 않으면 봉 날짜의 시행일 기준
      법정 세율(engine/transaction_tax.py), 명시(0 포함)하면 전 구간 고정.
    """
    fee_rate_raw = options.get('fee_rate')
    fee_rate = float(fee_rate_raw) if fee_rate_raw is not None else DEFAULT_FEE_RATE

    buy_raw = options.get('buy_fee_rate')
    sell_raw = options.get('sell_fee_rate')
    tax_raw = options.get('sell_tax_rate')

    buy_fee = float(buy_raw) if buy_raw is not None else fee_rate
    sell_fee = float(sell_raw) if sell_raw is not None else fee_rate
    if tax_raw is not None:
        sell_tax = np.full(len(index), float(tax_raw))
    else:
        sell_tax = kr_sell_tax_rates(index)
    return buy_fee, sell_fee, sell_tax


def resolve_slippage_rate(options: Dict[str, Any]) -> float:
    slippage_raw = options.get('slippage_rate')
    return float(slippage_raw) if slippage_raw is not None else DEFAULT_SLIPPAGE_RATE


def applied_trading_costs(options: Dict[str, Any], index: pd.Index) -> Dict[str, Any]:
    """결과에 동봉하는 '이 결과가 실제로 적용한 거래 비용'(소수 비율).

    sellTaxRate는 고정 세율(명시값)일 때만 값이고, 시행일 기준 법정 세율 스케줄을 썼으면
    None이며 그 구간의 [최저, 최고]를 sellTaxRateRange에 싣는다.
    """
    buy_fee, sell_fee, sell_tax = resolve_cost_rates(options, index)
    tax_raw = options.get('sell_tax_rate')
    if tax_raw is not None:
        tax_rate, tax_range = float(tax_raw), None
    else:
        tax_rate = None
        tax_range = [float(sell_tax.min()), float(sell_tax.max())] if len(sell_tax) else None
    return {
        'buyFeeRate': buy_fee,
        'sellFeeRate': sell_fee,
        'slippageRate': resolve_slippage_rate(options),
        'sellTaxRate': tax_rate,
        'sellTaxRateRange': tax_range,
    }

# 리밸런싱일에 목표 집합에서 빠져(조건 미충족·랭킹 이탈) 매도되는 청산의 정밀 사유.
# 신호/리스크 청산이 아니므로 결과 라벨이 추상적인 '전략 매도 조건 충족'으로 뭉개지지
# 않도록 시뮬레이터가 직접 사유를 기록한다.
REBALANCE_EXIT_REASON = tr.encode([tr.part(tr.REBALANCE_DROPOUT)])

# 리밸런싱일에 목표 비중을 넘어선 보유를 덜어내는 부분 매도(트림)의 사유 — 방식과 무관하다.
# 종목 교체·비중 유지 둘 다 동일가중으로 비중을 리셋하므로 오른 종목이 목표 비중까지 잘리고,
# 라벨이 없으면 result_handler의 일반 추론이 '전략 매도 조건 충족'으로 적어 **매도 조건을
# 하나도 말하지 않은 전략**의 거래 내역에 존재하지 않는 매도 조건이 사유로 찍힌다.
REBALANCE_TRIM_REASON = tr.encode([tr.part(tr.REBALANCE_TRIM)])


def stop_loss_refill_reserve(cand_sorted, sel_band):
    """손절 종목을 대신할 후보의 랭킹 순서(v16.12) — 리밸런싱일 선정과 같은 범위.

    반환 (후보 배열, 첫 후보의 리밸런싱일 순위 - 1). 상위 K·상위 X%는 리밸런싱일 후보 전체
    (선정 밖 = 다음 순위부터), 분위 그룹은 자기 구간 안(그룹당 상한 밖 종목)만 — 다음 그룹
    종목을 끌어오면 그룹 비교가 섞인다. 순위는 구간 기준이 아니라 후보 전체 기준이다.
    """
    if sel_band:
        n = len(cand_sorted)
        g, groups = int(sel_band[0]), int(sel_band[1])
        lo = round((g - 1) * n / groups)
        hi = n if g >= groups else round(g * n / groups)
        return cand_sorted[lo:hi], lo
    return cand_sorted, 0


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


def _fmt_g(x: float) -> str:
    return str(int(x)) if x == int(x) else f"{x:g}"


def regime_condition_args(market_regime: Dict[str, Any]) -> tuple:
    """시장 국면 판정 조건의 (종류, 템플릿 인자) — 종류는 'ma'|'vol'|'any'.

    매매 사유(trade_reason)와 결과 경고(result_warnings)가 같은 인자 순서를 쓴다."""
    from engine.market_index import REGIME_VOL_DEFAULT_PERIOD

    triggers = market_regime.get('triggers') or ['below_ma']
    index = str(market_regime.get('index') or 'KOSPI')
    ma_args = (int(market_regime.get('ma_period') or 0),)
    if 'volatility_spike' not in triggers:
        return 'ma', (index, *ma_args)
    vol_args = (int(market_regime.get('volatility_period') or REGIME_VOL_DEFAULT_PERIOD),
                _fmt_g(float(market_regime.get('volatility_multiple') or 0.0)))
    if 'below_ma' not in triggers:
        return 'vol', (index, *vol_args)
    return 'any', (index, *ma_args, *vol_args)


_REGIME_REDUCE_TEMPLATES = {
    'ma': tr.MARKET_REGIME_REDUCE,
    'vol': tr.MARKET_REGIME_REDUCE_VOL,
    'any': tr.MARKET_REGIME_REDUCE_ANY,
}


def _regime_label(market_regime: Optional[Dict[str, Any]]) -> Optional[tuple]:
    """시장 국면 사유 (템플릿, 인자…) — 판정 조건 인자 뒤에 목표 노출 %. 없으면 None."""
    if not market_regime:
        return None
    kind, args = regime_condition_args(market_regime)
    pct = float(market_regime.get('exposure_pct') or 0.0)
    return (_REGIME_REDUCE_TEMPLATES[kind], *args, _fmt_g(pct))


def _inverse_vol_values(vol_df: Optional[pd.DataFrame]) -> Optional[np.ndarray]:
    """연환산 변동성 패널 → 1/σ 배열(σ가 없거나 0 이하면 NaN)."""
    if vol_df is None:
        return None
    vol = vol_df.values.astype(float)
    with np.errstate(divide='ignore', invalid='ignore'):
        return np.where(vol > 0, 1.0 / vol, np.nan)


def _weight_cap(risk_params: Dict[str, Any]) -> Optional[float]:
    """종목당 비중 상한(v16.18, ``max_position_weight_pct``) → 비율. 없거나 100% 이상이면 None.

    상한은 편입·리밸런싱 시점의 **목표 비중**에 건다(min). 잘린 몫은 다른 종목에 재배분하지 않고
    현금으로 남는다 — 동일가중은 재배분할 곳이 없고(전 종목이 같은 상한에 걸린다), 역변동성도 같은
    규칙으로 둔다. 보유 중 주가 상승으로 비중이 상한을 넘는 것은 다음 리밸런싱의 비중 리셋이 되돌린다.
    """
    raw = risk_params.get('max_position_weight_pct')
    if raw is None:
        return None
    cap = float(raw) / 100.0
    return cap if 0.0 < cap < 1.0 else None


def _entry_base_size(cur_size: float, inv_vals: Optional[np.ndarray],
                     inv_norm: Optional[float], i: int, s_idx: int,
                     cap: Optional[float] = None) -> float:
    """노출 100% 기준 종목 비중 — 동일가중 × (1/σ_i ÷ 기간 정규화 기준). 역비중이 아니거나
    σ·기준이 없으면 동일가중 그대로. ``cap``(종목당 비중 상한)이 있으면 그 값으로 자른다."""
    size = cur_size
    if inv_vals is not None and inv_norm:
        iv = inv_vals[i, s_idx]
        if np.isfinite(iv):
            size = cur_size * float(iv) / inv_norm
    return min(size, cap) if cap is not None else size


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
            available_df: Optional[pd.DataFrame] = None,
            vol_df: Optional[pd.DataFrame] = None,
            exposure: Optional[np.ndarray] = None) -> vbt.Portfolio:
        """vol_df(v16.14): 변동성 역비중용 연환산 변동성 패널(엔진이 신호와 같은 지연으로 맞춰
        넘긴다) — 있으면 목표 종목 비중을 1/σ에 비례시킨다. exposure(v16.14): 거래일별 목표
        노출 비율(0~1, 시장 국면 필터) — 있으면 목표 비중에 곱하고, 국면이 바뀐 날 보유 비중을
        다시 맞춘다. 둘 다 None이면 종전 동작 그대로다."""

        # {symbol: {날짜문자열: 정밀 청산 사유}} — 신호/리스크로 설명되지 않는 청산
        # (리밸런싱 편출 등)의 사유를 체결일 기준으로 남겨 result_handler가 우선 적용한다.
        self.exit_reason_overrides: Dict[str, Dict[str, str]] = {}
        # {symbol: {체결일: 매수 사유}} — 랭킹 사유 배열로 설명되지 않는 매수(손절 종목 대체
        # 편입, v16.12)의 사유. result_handler가 신호 사유보다 우선 적용한다.
        self.entry_reason_overrides: Dict[str, Dict[str, str]] = {}
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

        buy_fee, sell_fee = self._resolve_fee_rates(options, entries_df.index)
        slippage_val = resolve_slippage_rate(options)
        exec_type = options.get('execution_type', 'same_close')

        skip_pos = risk_params.get('skip_position_setting', False)
        use_risk_mgmt = not risk_params.get('skip_risk_management', False)
        weight_cap = _weight_cap(risk_params)

        # Determine size per position (진입 시점 포트폴리오 NAV 대비 비중)
        equal_base = risk_params.get('allocation_type') in ('equal', 'inverse_volatility')
        if equal_base:
            # 변동성 역비중도 기준 비중은 동일가중이다 — 종목별로 1/σ 상대값을 곱해 나눈다.
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
        regime_label = _regime_label(risk_params.get('market_regime'))
        # 리밸런싱 방식(FR-BT-067) — 사용자가 고른다. 'weights_only'는 종목을 교체하지
        # 않고 비중만 균등으로 되돌린다(오른 종목 일부 매도 → 내린 종목 추가 매수).
        # 기본은 종전 동작(reconstitute = 리밸런싱일마다 목표 종목 재선정)이다.
        weights_only = str(risk_params.get('rebalance_method') or 'reconstitute') == 'weights_only'
        rebalance_mode = (not skip_pos) and bool(max_pos or sel_pct or sel_band) and bool(rebalance_dates.any())
        has_position_risk = use_risk_mgmt and (sl_pct > 0 or tp_pct > 0 or ts_pct > 0 or max_hold > 0)
        # 매수 조건이 있는 전략은 순수 경로로 보내지 않는다(v16.3) — 그 경로는 매도 신호를
        # 읽지 않고 리밸런싱일이 아닌 날의 매수 신호도 버린다(순수 랭킹 회전 전용).
        if rebalance_mode and not has_position_risk and not entry_signal_driven:
            return self._run_target_rebalance(
                price_df, exec_price_df, entries_df, rank_df, rebalance_dates,
                eff_max_pos, init_cash, buy_fee, sell_fee, slippage_val,
                sel_pct=sel_pct, sel_band=sel_band, band_cap=band_cap,
                weights_only=weights_only, vol_df=vol_df, exposure=exposure,
                regime_label=regime_label, weight_cap=weight_cap,
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
        sl_reason = tr.encode([tr.part(tr.STOP_LOSS_PCT, _fmt_pct(sl_pct)) if sl_pct > 0
                               else tr.part(tr.STOP_LOSS)])
        tp_reason = tr.encode([tr.part(tr.TAKE_PROFIT_PCT, _fmt_pct(tp_pct)) if tp_pct > 0
                               else tr.part(tr.TAKE_PROFIT)])
        ts_reason = tr.encode([tr.part(tr.TRAILING_STOP_EXEC_PCT, _fmt_pct(ts_pct)) if ts_pct > 0
                               else tr.part(tr.TRAILING_STOP_EXEC)])

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
            fees_values[i, mask] = sell_fee[i]
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
        # 주의: 이 경로의 **종목 교체(reconstitution) 방식**은 유지 종목의 비중 리셋을 하지
        # 않는다 — 엔진이 경고로 고지한다. 비중 유지 방식(weights_only)은 반대로 교체 없이
        # 비중만 되돌리므로 리밸런싱일마다 보유 전체에 목표비중을 다시 준다.
        current_target_mask = np.zeros(num_symbols, dtype=bool)
        rank_values_all = rank_df.values if rank_df is not None else None
        # 손절 종목 대체 편입(v16.12, 사용자 결정): 순위가 있는 달력 회전(선정=진입)에서 손절로
        # 청산된 종목은 **그 리밸런싱 기간의 목표에서 빠지고**, 빈자리는 그 리밸런싱일 랭킹의
        # 다음 순위 후보가 채운다. 종전엔 목표 집합에 남아 다음 거래일에 같은 종목을 다시 샀다
        # (2026-09-17 실측: 아티스트컴퍼니 2024-01 손절→재매수 3회). 다음 리밸런싱일엔 다시
        # 정상 후보다. 익절·트레일링·보유 기간 만료·매수 조건 전략은 대상이 아니다(미결정).
        stop_refill = rebalance_mode and not entry_signal_driven and rank_values_all is not None
        refill_reserve = np.empty(0, dtype=np.int64)    # 리밸런싱일 랭킹 순서(선정 범위)
        refill_offset = 0                                # refill_reserve[0]의 리밸런싱일 순위 - 1
        refill_rank = np.zeros(num_symbols, dtype=np.int64)   # 대체 편입 후보의 리밸런싱일 순위(0=아님)
        stopped_this_period = np.zeros(num_symbols, dtype=bool)
        # 비율/분위 선정 모드에선 목표 종목 수가 리밸런싱일마다 달라진다 — 슬롯 상한과
        # 동일가중 비중을 그때그때 갱신한다(기본 모드에선 기존 정적 값 유지).
        cur_cap = eff_max_pos
        cur_size = size_per_pos

        # 변동성 역비중(v16.14): 1/σ 패널과 이번 리밸런싱 기간의 정규화 기준(목표 종목 1/σ 평균).
        inv_vals = _inverse_vol_values(vol_df)
        inv_norm: Optional[float] = None
        # 시장 국면 노출(v16.14): 종목별 '노출 100% 기준 비중'을 들고 있다가 국면이 바뀌면
        # 기준 비중 × 새 노출로 다시 맞춘다.
        exp_vals = np.asarray(exposure, dtype=float) if exposure is not None else None
        pos_base = np.zeros(num_symbols, dtype=np.float64)
        prev_exp = 1.0
        regime_reason = (tr.encode([tr.part(*regime_label)])
                         if regime_label else REBALANCE_TRIM_REASON)

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
            stop_loss_hit = None
            if active_mask.any():
                closes = price_values[i]
                highs = high_values[i]
                lows = low_values[i]

                # Fix 1: 보유 종목 고점 갱신 (장중 고가 기준)
                if ts_pct > 0:
                    peak_price = np.where(active_mask, np.maximum(peak_price, highs), peak_price)

                should_exit = np.zeros(num_symbols, dtype=bool)
                stop_loss_hit = np.zeros(num_symbols, dtype=bool)
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
                        stop_loss_hit = hit
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
                if weights_only:
                    # 비중 유지 리밸런싱(FR-BT-067): 종목 교체가 없다 — 보유는 목표에서
                    # 빠지지 않고(편출 0), 목표 종목 수에 미달하는 빈 자리만 후보로 채운다.
                    keep = active_mask | pending_exit
                    current_target_mask |= keep
                    free = max(0, len(sel) - int(keep.sum()))
                    if free > 0:
                        fills = [c for c in sel if not keep[c]][:free]
                        current_target_mask[fills] = True
                else:
                    current_target_mask[sel] = True
                if stop_refill:
                    # 새 기간 — 손절 이력·대체 후보 표식을 비우고 이번 리밸런싱일 순위로 갈아 끼운다.
                    refill_reserve, refill_offset = stop_loss_refill_reserve(cand, sel_band)
                    refill_rank[:] = 0
                    stopped_this_period[:] = False
                if sel_pct or sel_band:
                    cur_cap = max(len(sel), 1)
                    if equal_base:
                        cur_size = 1.0 / cur_cap
                if inv_vals is not None:
                    # 이번 기간 역변동성 정규화 기준 — 목표 종목 1/σ의 평균. 종목 비중 =
                    # cur_size × (1/σ_i) / 평균 → 목표 종목이 모두 담기면 합이 100%다.
                    _iv = inv_vals[i][current_target_mask]
                    _iv = _iv[np.isfinite(_iv)]
                    if len(_iv):
                        inv_norm = float(_iv.mean())

                if weights_only:
                    # 비중 리셋 — 보유 종목에 동일가중 목표비중을 다시 준다(오른 종목은
                    # 일부 매도, 내린 종목은 추가 매수). 오늘 청산이 예정·체결된 종목과
                    # 거래 불가일 종목은 제외한다(같은 셀에 상반된 주문을 낼 수 없다).
                    # 트림(소량 매도)의 매도 비용은 _run_orders가 실현 주문을 보고 적용한다.
                    reset = active_mask & ~pending_exit & avail_values[i]
                    if reset.any():
                        if inv_vals is None and exp_vals is None:
                            target_values[i, reset] = (
                                cur_size if weight_cap is None else min(cur_size, weight_cap))
                        else:
                            for s_idx in np.where(reset)[0]:
                                pos_base[s_idx] = _entry_base_size(
                                    cur_size, inv_vals, inv_norm, i, s_idx, weight_cap)
                            target_values[i, reset] = pos_base[reset] * (
                                exp_vals[i] if exp_vals is not None else 1.0)
                        # 트림(목표 비중 초과분 매도) 사유 — 오늘 청산이 확정된 종목은
                        # 위 Step 1·2에서 active_mask가 이미 꺼져 여기 들어오지 않는다
                        # (리스크 청산 사유를 덮어쓰지 않는다).
                        for s_idx in np.where(reset)[0]:
                            self.exit_reason_overrides.setdefault(
                                symbols[s_idx], {}
                            )[date_strs[i]] = REBALANCE_TRIM_REASON
                    dropouts = np.zeros(num_symbols, dtype=bool)
                else:
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

            # 손절 종목 대체(v16.12): 오늘 손절이 결정된 종목을 이번 기간 목표에서 빼고, 리밸런싱일
            # 랭킹의 다음 순위(목표·보유·청산 대기·이번 기간 손절 종목 제외)로 채운다. 리밸런싱
            # 단계 뒤에 두는 이유: 리밸런싱일 장중에 손절된 종목은 새 기간의 손절이다.
            # 후보 풀은 리밸런싱일 선정과 같은 마스크(가용·유동성·시총)를 이미 통과한 목록이고,
            # 체결 가능 여부는 원래 목표 종목과 똑같이 아래 Step 3이 거래일마다 판정한다.
            if stop_refill and stop_loss_hit is not None and stop_loss_hit.any():
                for s_idx in np.where(stop_loss_hit & current_target_mask)[0]:
                    current_target_mask[s_idx] = False
                    stopped_this_period[s_idx] = True
                    refill_rank[s_idx] = 0
                    for pos, c in enumerate(refill_reserve):
                        if (current_target_mask[c] or stopped_this_period[c]
                                or active_mask[c] or pending_exit[c]):
                            continue
                        current_target_mask[c] = True
                        refill_rank[c] = refill_offset + pos + 1
                        break

            # 시장 국면 전환(v16.14): 노출 비율이 바뀐 날 보유 비중을 기준 비중 × 새 노출로 다시
            # 맞춘다. 노출 0%는 전량 현금화(청산으로 부기 — 이후 손절 감시 대상이 아니다).
            # 판정 근거(지수 종가)는 엔진이 신호와 같은 지연으로 넘기므로 당일 체결한다.
            cur_exp = float(exp_vals[i]) if exp_vals is not None else 1.0
            if exp_vals is not None and cur_exp != prev_exp:
                movable = active_mask & ~pending_exit & avail_values[i] & ~exits_values[i].astype(bool)
                if cur_exp <= 0.0:
                    stuck = active_mask & ~pending_exit & ~movable
                    exit_reason_pending[movable | stuck] = regime_reason
                    pending_exit |= stuck & ~avail_values[i]
                    if movable.any():
                        exits_values[i] |= movable
                        _book_exit(i, movable)
                elif movable.any():
                    target_values[i, movable] = pos_base[movable] * cur_exp
                    label = regime_reason if cur_exp < prev_exp else REBALANCE_TRIM_REASON
                    for s_idx in np.where(movable)[0]:
                        self.exit_reason_overrides.setdefault(
                            symbols[s_idx], {})[date_strs[i]] = label
                prev_exp = cur_exp

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
            if exp_vals is not None and cur_exp <= 0.0:
                candidate_indices = candidate_indices[:0]   # 노출 0% 국면 — 신규 편입 없음
            if inv_vals is not None and inv_norm is None and len(candidate_indices) > 0:
                _iv = inv_vals[i][candidate_indices]
                _iv = _iv[np.isfinite(_iv)]
                if len(_iv):
                    inv_norm = float(_iv.mean())

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
                        if inv_vals is None and exp_vals is None:
                            # 상한은 최종 비중에만 건다 — 기준 비중(cur_size)을 자르면 역변동성에서
                            # 상한에 걸리지 않은 종목까지 같이 줄어든다.
                            target_values[i, s_idx] = (
                                cur_size if weight_cap is None else min(cur_size, weight_cap))
                        else:
                            pos_base[s_idx] = _entry_base_size(
                                cur_size, inv_vals, inv_norm, i, s_idx, weight_cap)
                            target_values[i, s_idx] = pos_base[s_idx] * cur_exp
                        fees_values[i, s_idx] = buy_fee
                        if refill_rank[s_idx] > 0:
                            self.entry_reason_overrides.setdefault(symbols[s_idx], {})[date_strs[i]] = (
                                tr.encode([tr.part(tr.STOP_LOSS_REFILL, int(refill_rank[s_idx]))])
                            )
                            refill_rank[s_idx] = 0

        target_df = pd.DataFrame(target_values, index=entries_df.index, columns=entries_df.columns)

        # NOTE: sl_stop/tp_stop/sl_trail은 의도적으로 vbt에 넘기지 않는다. 위 루프가
        # 감지한 청산을 목표비중 0 주문으로 주입하며, 체결은 exec_price(시장가)로
        # 이뤄진다. vbt 내장 스탑은 '정확히 스탑 가격 체결'(갭 무시)을 가정해
        # 리스크 관리를 인위적으로 완벽하게 만들기 때문.
        return self._run_orders(price_df, exec_price_df, target_df, fees_values,
                                buy_fee, sell_fee, slippage_val, init_cash)

    @staticmethod
    def _resolve_fee_rates(options: Dict[str, Any], index: pd.Index) -> tuple:
        """(매수 수수료율, 봉별 매도 수수료율+거래세율 벡터)를 옵션에서 해석한다."""
        buy_fee, sell_fee, sell_tax = resolve_cost_rates(options, index)
        return buy_fee, sell_fee + sell_tax

    @staticmethod
    def _run_orders(price_df: pd.DataFrame,
                    exec_price_df: pd.DataFrame,
                    target_df: pd.DataFrame,
                    fees_values: np.ndarray,
                    buy_fee: float,
                    sell_fee: np.ndarray,
                    slippage_val: float,
                    init_cash: float) -> vbt.Portfolio:
        """목표비중 주문을 체결하고, 양수 목표 셀에서 **실현된 매도**(비중 리셋 트림)에
        매도 비용(수수료+거래세)을 물려 다시 체결한다.

        vbt from_orders의 수수료는 셀 단위라 주문 방향을 미리 모른다 — 트림은 목표비중이
        양수인 셀에서 나오는 매도이므로 1차 체결의 주문 기록(side)으로 셀을 찾아 매도
        비용으로 바꾼 뒤 재실행한다(트림이 없으면 1회로 끝난다). 재실행으로 NAV가 미세하게
        달라져 방향이 뒤집히는 셀은 2회차에서 한 번 더 잡는다.
        """
        from vectorbt.portfolio.enums import OrderSide

        def _run(fees: np.ndarray) -> vbt.Portfolio:
            return vbt.Portfolio.from_orders(
                close=price_df,
                size=target_df,
                size_type='targetpercent',
                price=exec_price_df,
                fees=fees,
                slippage=slippage_val,
                init_cash=init_cash,
                cash_sharing=True,
                group_by=True,
                call_seq='auto',          # 매도 → 매수 순서: 청산 현금으로 신규 편입
                direction='longonly',
                size_granularity=1.0,     # 정수 주식 단위 (소수점 주식 금지)
                freq='D',
            )

        pf = _run(fees_values)
        for _ in range(2):
            rec = pf.orders.records_arr
            sells = rec[rec['side'] == OrderSide.Sell]
            if len(sells) == 0:
                break
            idx, col = sells['idx'], sells['col']
            under = fees_values[idx, col] < sell_fee[idx]
            if not under.any():
                break
            fees_values[idx[under], col[under]] = sell_fee[idx[under]]
            pf = _run(fees_values)
        return pf

    def _run_target_rebalance(self,
                              price_df: pd.DataFrame,
                              exec_price_df: pd.DataFrame,
                              entries_df: pd.DataFrame,
                              rank_df: Optional[pd.DataFrame],
                              rebalance_dates: np.ndarray,
                              eff_max_pos: int,
                              init_cash: float,
                              buy_fee: float,
                              sell_fee: np.ndarray,
                              slippage_val: float,
                              sel_pct: Optional[float] = None,
                              sel_band: Optional[list] = None,
                              band_cap: Optional[int] = None,
                              weights_only: bool = False,
                              vol_df: Optional[pd.DataFrame] = None,
                              exposure: Optional[np.ndarray] = None,
                              regime_label: Optional[tuple] = None,
                              weight_cap: Optional[float] = None) -> vbt.Portfolio:
        """순수 리밸런싱 경로 — vbt 네이티브 from_orders(목표비중)로 비중 리셋까지 수행.

        리밸런싱일마다 후보(entries=True)를 rank 상위 K로 골라 동일가중 목표비중을 주고,
        목표에서 빠진 보유는 비중 0으로 청산한다. 비리밸런싱일은 NaN(주문 없음 = 보유 유지).
        call_seq='auto'로 매도→매수 순서를 보장해 청산 현금으로 신규 편입을 채운다.

        ``weights_only``(비중 유지 리밸런싱, FR-BT-067)면 종목 교체를 하지 않는다 —
        보유 종목은 그대로 두고 동일가중으로 비중만 되돌리며(오른 종목 일부 매도,
        내린 종목 추가 매수), 목표 종목 수에 미달하는 빈 자리만 후보로 채운다.

        수수료: 목표비중 0 셀은 매도 비용(수수료+거래세), 양수 셀은 매수 수수료로 시작하고,
        유지 종목의 비중 리셋 트림(양수 셀의 실현 매도)은 _run_orders가 주문 기록으로
        찾아 매도 비용을 적용한다.
        """
        num_rows, num_syms = entries_df.shape
        entries_values = entries_df.values
        rank_values = rank_df.values if rank_df is not None else None

        symbols = entries_df.columns.tolist()
        date_strs = [pd.Timestamp(d).strftime('%Y-%m-%d') for d in entries_df.index]
        held = np.zeros(num_syms, dtype=bool)   # 직전 리밸런싱에서 목표비중을 받은 보유 종목

        target = np.full((num_rows, num_syms), np.nan)
        inv_vals = _inverse_vol_values(vol_df)
        exp_vals = np.asarray(exposure, dtype=float) if exposure is not None else None
        if exp_vals is None and inv_vals is None:
            rows = np.where(rebalance_dates)[0]
        else:
            rows = np.where(rebalance_dates)[0] if exp_vals is None else np.where(
                rebalance_dates | np.r_[False, exp_vals[1:] != exp_vals[:-1]])[0]
        base = np.zeros(num_syms)               # 노출 100% 기준 목표비중(시장 국면 전환 시 재사용)
        prev_exp = 1.0
        regime_reason = (tr.encode([tr.part(*regime_label)])
                         if regime_label else REBALANCE_TRIM_REASON)
        for i in rows:
            if not rebalance_dates[i]:
                # 시장 국면 전환일(v16.14) — 종목은 그대로, 비중만 기준 비중 × 새 노출로 맞춘다.
                cur_exp = float(exp_vals[i])
                row = base * cur_exp
                label = regime_reason if cur_exp < prev_exp else REBALANCE_TRIM_REASON
                for s_idx in np.where(held)[0]:
                    self.exit_reason_overrides.setdefault(
                        symbols[s_idx], {})[date_strs[i]] = label
                prev_exp = cur_exp
                held = row > 0.0
                target[i, :] = row
                continue
            cand = np.where(entries_values[i])[0]
            if rank_values is not None and len(cand) > 0:
                cand = cand[np.argsort(-rank_values[i][cand])]
            sel = select_ranked_targets(cand, eff_max_pos, sel_pct, sel_band, band_cap)
            if len(sel) < len(cand):
                self.overflow_days += 1
            if weights_only:
                # 비중 유지: 보유는 목표에서 빠지지 않는다. 목표 종목 수(sel 길이 =
                # 상한·비율·분위 규칙이 정한 수)에 미달하는 만큼만 후보로 채운다.
                free = max(0, len(sel) - int(held.sum()))
                fills = [c for c in sel if not held[c]][:free]
                sel = np.concatenate((np.where(held)[0], np.asarray(fills, dtype=int)))
            row = np.zeros(num_syms)            # 0 = 목표에서 빠진 보유는 전량 청산
            if len(sel) > 0:
                row[sel] = 1.0 / len(sel)        # 동일가중 목표비중 (비중 리셋)
                if weight_cap is not None:
                    row = np.minimum(row, weight_cap)   # 종목당 비중 상한(v16.18) — 잘린 몫은 현금
            if inv_vals is not None or exp_vals is not None:
                sel_arr = np.asarray(sel, dtype=int)
                if inv_vals is not None and len(sel_arr) > 0:
                    iv = inv_vals[i][sel_arr]
                    if np.isfinite(iv).all() and iv.sum() > 0:
                        row[sel_arr] = iv / iv.sum()    # 변동성 역비중 — 1/σ에 비례
                if weight_cap is not None:
                    row = np.minimum(row, weight_cap)   # 종목당 비중 상한(v16.18) — 잘린 몫은 현금
                base = row.copy()
                if exp_vals is not None:
                    prev_exp = float(exp_vals[i])
                    row = base * prev_exp
            # 보유 중이던 종목이 목표에서 빠지면(비중 0) 리밸런싱 편출로 매도된다.
            dropouts = np.where(held & (row == 0.0))[0]
            for s_idx in dropouts:
                self.exit_reason_overrides.setdefault(
                    symbols[s_idx], {}
                )[date_strs[i]] = REBALANCE_EXIT_REASON
            # 목표에 남은 보유의 부분 매도(트림) 사유 — **두 방식 모두**에 붙인다. 이
            # 경로는 종목 교체에서도 리밸런싱일마다 동일가중으로 비중을 리셋하므로(위 row)
            # 오른 종목이 목표 비중까지 잘린다. 라벨이 없으면 result_handler의 일반 추론이
            # '전략 매도 조건 충족'으로 적어, 매도 조건을 하나도 말하지 않은 전략의 거래
            # 내역에 존재하지 않는 매도 조건이 사유로 찍힌다(2026-08-26 실측·사용자 지시로 정리).
            # 매수로 끝난 종목엔 그날 매도 기록이 없어 이 예약은 쓰이지 않는다(사유는 매도에만 붙는다).
            for s_idx in np.where(held & (row > 0.0))[0]:
                self.exit_reason_overrides.setdefault(
                    symbols[s_idx], {}
                )[date_strs[i]] = REBALANCE_TRIM_REASON
            held = row > 0.0
            target[i, :] = row

        # 여기서 next_open을 다시 shift하지 않는다 — 엔진(backtest_engine)이 next_open일 때
        # 신호·랭킹을 이미 1일 shift해 넘기므로(row i = 전일 종가 정보 = 체결일), 추가 shift는
        # 체결을 하루 더 늦추는 이중 지연이었다(커스텀 루프 경로와 체결일이 어긋나던 버그).
        target_df = pd.DataFrame(target, index=entries_df.index, columns=entries_df.columns)

        fees_values = np.where(target_df.values == 0.0, sell_fee[:, None], buy_fee)

        return self._run_orders(price_df, exec_price_df, target_df, fees_values,
                                buy_fee, sell_fee, slippage_val, init_cash)
