"""독립 스크리너(엔진 v16.33) — 사용자가 만든 전략의 조건을 **오늘 데이터**에 적용한 결과.

백테스트가 '과거에 어떻게 됐나'를 계산한다면 스크리너는 같은 조건을 최신 봉에 한 번 적용해
'지금 이 조건을 충족하는 종목이 무엇인가'를 보여 준다. 추천이 아니라 사용자가 정의한 계산의
결과이며, 시점 명부(PIT)가 아니라 **현재 상장 종목**을 본다(오늘을 묻는 화면이므로).

계산은 자동매매가 쓰는 평가기를 그대로 재사용한다 — 화면마다 조건 해석이 갈리면 같은 전략이
자리마다 다른 종목을 고른다:
  · 유니버스: engine/live_signal_utils.resolve_live_universe (상장폐지 제외)
  · 신호:     engine/live_signal_utils.evaluate_live_strategy_signals (지표·조건·수익률 랭킹)
여기서 더하는 것은 표시용 보강(종목명·섹터·종가·등락률·거래대금)과 **재무 팩터 랭킹 정렬**뿐이다
(평가기는 'return' 랭킹만 정렬한다 — 재무 랭킹 컬럼은 최신 행에서 읽어 여기서 정렬한다).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from engine import trade_reason as tr
from engine.live_signal_utils import evaluate_live_strategy_signals, resolve_live_universe

# 가격에서 직접 계산하는 랭킹 — 컬럼이 없으므로 표에서 읽지 않는다(평가기가 'return'을 맡는다).
PRICE_RANKING_METRICS = frozenset({
    "return", "relative_return", "volatility", "composite", "residual_reversal", "taa", "pead",
})

DEFAULT_LIMIT = 100
MAX_LIMIT = 300


def _last_valid(frame: pd.DataFrame, column: str) -> Optional[float]:
    if column not in frame.columns:
        return None
    series = frame[column].dropna()
    if len(series) == 0:
        return None
    try:
        return float(series.iloc[-1])
    except (TypeError, ValueError):
        return None


def _enrich(loader, symbol: str, rank_column: Optional[str]) -> Dict[str, Any]:
    """최신 봉의 표시값 — 종가·등락률·거래대금과 (요청 시) 랭킹 지표 값."""
    out: Dict[str, Any] = {"close": None, "changePct": None, "tradingValue": None, "rankValue": None,
                           "date": None}
    frame = loader.load_symbol_data(symbol)
    if frame is None or len(frame) == 0:
        return out
    pdf = frame.to_pandas() if hasattr(frame, "to_pandas") else frame
    if len(pdf) == 0:
        return out
    last = pdf.iloc[-1]
    close = last.get("close")
    out["close"] = float(close) if close is not None and pd.notna(close) else None
    if len(pdf) >= 2:
        prev = pdf["close"].iloc[-2]
        if prev not in (None, 0) and pd.notna(prev) and out["close"] is not None:
            out["changePct"] = (out["close"] / float(prev) - 1.0) * 100.0
    volume = last.get("volume")
    if out["close"] is not None and volume is not None and pd.notna(volume):
        out["tradingValue"] = float(out["close"]) * float(volume)
    date_val = last.get("date")
    if date_val is not None:
        out["date"] = pd.Timestamp(date_val).strftime("%Y-%m-%d")
    if rank_column:
        out["rankValue"] = _last_valid(pdf, rank_column)
    return out


def _display_name(symbol: str) -> Optional[str]:
    try:
        from stock_analysis.symbol_resolver import resolve_by_symbol
    except Exception:  # noqa: BLE001 — 이름 해석 실패가 스크린을 막지 않는다
        return None
    try:
        ref = resolve_by_symbol(symbol)
        return ref.name if ref else None
    except Exception:  # noqa: BLE001
        return None


def _sector(symbol: str) -> Optional[str]:
    try:
        from engine.ksic_sectors import sector_for_symbol
        return sector_for_symbol(str(symbol))
    except Exception:  # noqa: BLE001
        return None


def run_screen(loader, dsl: Dict[str, Any], *, limit: int = DEFAULT_LIMIT,
               ai_engine: Any = None) -> Dict[str, Any]:
    """전략 DSL(저장된 전략의 settings와 같은 모양) → 오늘 조건을 충족하는 종목 목록.

    반환: {asOf, scanned, matched, truncated, rankingMetric, rankingDirection, rows[...]}.
    조건이 하나도 없으면 매수 기준이 없는 전략이라 빈 결과와 사유를 돌려준다(빈 표를
    '해당 종목 없음'으로 위장하지 않는다).
    """
    entry = dsl.get("entry") if isinstance(dsl.get("entry"), dict) else {}
    exit_ = dsl.get("exit") if isinstance(dsl.get("exit"), dict) else {}
    risk = dsl.get("risk") if isinstance(dsl.get("risk"), dict) else {}
    metric = risk.get("ranking_metric")
    has_conditions = bool((entry or {}).get("conditions"))
    if not has_conditions and not metric:
        return {"asOf": None, "scanned": 0, "matched": 0, "truncated": False,
                "rankingMetric": None, "rankingDirection": None, "rows": [],
                "reason": "no_buy_criteria"}

    symbols = resolve_live_universe(dsl, [])
    if not symbols:
        return {"asOf": None, "scanned": 0, "matched": 0, "truncated": False,
                "rankingMetric": metric, "rankingDirection": risk.get("ranking_direction"),
                "rows": [], "reason": "empty_universe"}

    signals = evaluate_live_strategy_signals(loader, symbols, {}, entry, exit_, risk, ai_engine, None)
    # 조건이 있으면 조건 충족 종목, 조건 없이 랭킹만 있으면 전 종목이 후보다(랭킹이 곧 선정 기준).
    matched = [s for s in signals if s.get("entry_signal")] if has_conditions else list(signals)

    rank_column = metric if (metric and metric not in PRICE_RANKING_METRICS) else None
    limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))

    rows: List[Dict[str, Any]] = []
    as_of: Optional[str] = None
    for item in matched:
        symbol = item["symbol"]
        extra = _enrich(loader, symbol, rank_column)
        if extra["date"] and (as_of is None or extra["date"] > as_of):
            as_of = extra["date"]
        reason = item.get("entry_reason")
        rows.append({
            "symbol": symbol,
            "name": _display_name(symbol) or symbol,
            "sector": _sector(symbol) or "-",
            "close": extra["close"],
            "changePct": extra["changePct"],
            "tradingValue": extra["tradingValue"],
            "date": extra["date"],
            "rankValue": extra["rankValue"],
            "rankingReturnPct": (None if item.get("ranking_return") is None
                                 else float(item["ranking_return"]) * 100.0),
            # 사유는 세그먼트(템플릿+인자)와 한국어 정본을 함께 싣는다 — 표시 번역은 프론트 소관.
            "conditionParts": tr.decode(reason) if reason else None,
            "condition": tr.text(reason) if reason else None,
        })

    if rank_column:
        ascending = str(risk.get("ranking_direction") or "top") == "bottom"
        # 값이 없는 종목은 순위를 매길 수 없다 — 뒤로 보내고 그대로 둔다(0으로 위장하지 않는다).
        rows.sort(key=lambda r: (r["rankValue"] is None,
                                 (r["rankValue"] if ascending else -r["rankValue"])
                                 if r["rankValue"] is not None else 0.0))
    elif metric == "return":
        rows.sort(key=lambda r: (r["rankingReturnPct"] is None, -(r["rankingReturnPct"] or 0.0)))
    else:
        rows.sort(key=lambda r: (r["tradingValue"] is None, -(r["tradingValue"] or 0.0)))

    return {
        "asOf": as_of,
        "scanned": len(symbols),
        "matched": len(rows),
        "truncated": len(rows) > limit,
        "rankingMetric": metric,
        "rankingDirection": risk.get("ranking_direction"),
        "rows": rows[:limit],
    }
