from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import polars as pl

from engine.indicators import IndicatorEngine


_DATA_DIR = Path(__file__).resolve().parents[2] / "data"

# 저장된 전략마다 유니버스 표기가 달라 정본 id 로 모은다. 별칭을 두지 않으면
# KOR_KOSPI200 이 "kospi200" 정확일치를 비껴가 KOSPI 전체로 해석된다.
_UNIVERSE_ALIASES = {
    "kor_kospi200": "kospi200",
    "kospi_200": "kospi200",
    "kor_kosdaq150": "kosdaq150",
    "kosdaq_150": "kosdaq150",
}

# 지수 유니버스 → 구성종목 명부 파일. 명부가 없거나 깨졌으면 시장 전체로 넓히지 않고
# 폴백(모니터링 목록)으로 떨어진다 — 인식 못 한 유니버스를 임의 확대하지 않는다.
_INDEX_ROSTERS = {
    "kospi200": "kospi200-cache.json",
    "kosdaq150": "kosdaq150-cache.json",
}


def _normalize_date(value: Any) -> pd.Timestamp | None:
    if value is None:
        return None
    try:
        return pd.to_datetime(value).normalize()
    except Exception:
        return None


def _flatten_conditions(conditions: list[dict] | None) -> list[dict]:
    return [c for c in (conditions or []) if isinstance(c, dict)]


def uses_ai_conditions(*condition_groups: list[dict] | None) -> bool:
    for group in condition_groups:
        for cond in _flatten_conditions(group):
            if cond.get("id") in {"ai_model", "ai_drop_model"}:
                return True
    return False


def apply_realtime_quote(df_pl: pl.DataFrame, quote: Any) -> pl.DataFrame:
    if df_pl is None or len(df_pl) == 0 or quote is None:
        return df_pl

    pdf = df_pl.to_pandas()
    if len(pdf) == 0:
        return df_pl

    last_row = pdf.iloc[-1].copy()
    quote_date = _normalize_date(getattr(quote, "date", None) if not isinstance(quote, dict) else quote.get("date"))
    last_date = _normalize_date(last_row.get("date")) if "date" in pdf.columns else None
    date_value: Any = quote_date
    if "date" in pdf.columns and quote_date is not None:
        current_date_value = pdf.iloc[-1]["date"]
        if isinstance(current_date_value, str):
            date_value = quote_date.strftime("%Y-%m-%d")

    price_fields = ("open", "high", "low", "close", "volume")
    fundamental_fields = ("per", "pbr", "eps", "bps")
    target_idx = len(pdf) - 1
    if quote_date is not None and last_date is not None and quote_date > last_date:
        target_idx = len(pdf)

    if target_idx == len(pdf):
        new_row = last_row.copy()
        if "date" in pdf.columns and date_value is not None:
            new_row["date"] = date_value
        pdf = pd.concat([pdf, pd.DataFrame([new_row])], ignore_index=True)

    def _get_value(field: str) -> Any:
        if isinstance(quote, dict):
            return quote.get(field)
        return getattr(quote, field, None)

    for field in price_fields:
        if field in pdf.columns:
            value = _get_value(field)
            if value is not None:
                pdf.at[target_idx, field] = value

    # 실시간 PER/PBR/EPS/BPS 반영 (KIS API 등에서 제공 시)
    for field in fundamental_fields:
        value = _get_value(field)
        if value is not None:
            pdf[field] = pdf.get(field, float("nan"))
            pdf.at[target_idx, field] = value

    if "date" in pdf.columns and date_value is not None:
        pdf.at[target_idx, "date"] = date_value

    return pl.from_pandas(pdf)


def prepare_signal_dataframe(
    df_pl: pl.DataFrame,
    quote: Any,
    entry_conditions: list[dict] | None,
    exit_conditions: list[dict] | None,
    ai_engine: Any = None,
) -> pl.DataFrame:
    if df_pl is None or len(df_pl) == 0:
        return df_pl

    live_df = apply_realtime_quote(df_pl, quote)
    all_conditions = _flatten_conditions(entry_conditions) + _flatten_conditions(exit_conditions)
    tech_conditions = [c for c in all_conditions if c.get("id") not in {"ai_model", "ai_drop_model"}]

    if tech_conditions:
        live_df = IndicatorEngine.calculate(live_df, tech_conditions)

    if uses_ai_conditions(entry_conditions, exit_conditions):
        zeros = [0.0] * len(live_df)
        ai_probs = zeros
        ai_drop_probs = zeros
        if ai_engine is not None:
            pdf_for_ai = live_df.to_pandas()
            ai_probs_raw, ai_drop_probs_raw = ai_engine.predict_signals(pdf_for_ai)
            ai_probs = list(ai_probs_raw) if not isinstance(ai_probs_raw, list) else ai_probs_raw
            ai_drop_probs = list(ai_drop_probs_raw) if not isinstance(ai_drop_probs_raw, list) else ai_drop_probs_raw
        live_df = live_df.with_columns([
            pl.Series("ai_score", ai_probs),
            pl.Series("ai_drop_score", ai_drop_probs),
        ])

    return live_df


def evaluate_live_strategy_signals(
    data_loader: Any,
    symbols: list[str],
    quotes: dict[str, Any],
    entry_group: dict[str, Any] | None,
    exit_group: dict[str, Any] | None,
    risk: dict[str, Any] | None,
    ai_engine: Any = None,
    execution_date: str | None = None,
) -> list[dict[str, Any]]:
    """Evaluate the latest executable strategy row across a symbol universe."""
    from engine.signals import SignalEngine

    entry_group = entry_group if isinstance(entry_group, dict) else {}
    exit_group = exit_group if isinstance(exit_group, dict) else {}
    risk = risk if isinstance(risk, dict) else {}
    entry_conditions = _flatten_conditions(entry_group.get("conditions"))
    exit_conditions = _flatten_conditions(exit_group.get("conditions"))
    execution_timing = risk.get("execution_timing") or "next_open"
    ranking_metric = risk.get("ranking_metric")
    lookback = max(1, int(risk.get("ranking_lookback_days") or 60))
    max_positions = max(1, int(risk.get("max_positions") or 5))
    rebalancing_period = risk.get("rebalancing_period") or "none"
    signal_engine = SignalEngine()
    results: list[dict[str, Any]] = []
    rebalance_due = rebalancing_period == "daily"

    for symbol in symbols:
        result: dict[str, Any] = {
            "symbol": symbol,
            "entry_signal": False,
            "exit_signal": False,
            "entry_reason": None,
            "exit_reason": None,
            "ranking_return": None,
        }
        df = data_loader.load_symbol_data(symbol)
        if df is None or len(df) == 0:
            results.append(result)
            continue

        live_df = prepare_signal_dataframe(
            df, quotes.get(symbol), entry_conditions, exit_conditions, ai_engine
        )
        evaluation_offset = (
            -1
            if execution_timing != "next_open" or (
                execution_date is not None and quotes.get(symbol) is None
            )
            else -2
        )
        row_index = len(live_df) + evaluation_offset
        if rebalancing_period not in ("none", "daily") and len(live_df) >= 2:
            dates = live_df["date"]
            current_date = execution_date or dates[-1]
            previous_date = dates[row_index]
            rebalance_due = rebalance_due or _period_key(
                current_date, rebalancing_period
            ) != _period_key(previous_date, rebalancing_period)
        if row_index < 0:
            results.append(result)
            continue

        if entry_conditions:
            values, reasons = signal_engine.generate_signals(live_df, entry_group)
            result["entry_signal"] = bool(values[row_index])
            result["entry_reason"] = reasons[row_index]
        if exit_conditions:
            values, reasons = signal_engine.generate_signals(live_df, exit_group)
            result["exit_signal"] = bool(values[row_index])
            result["exit_reason"] = reasons[row_index]

        if ranking_metric == "return" and row_index - lookback >= 0:
            current = live_df["close"][row_index]
            previous = live_df["close"][row_index - lookback]
            if current is not None and previous not in (None, 0):
                result["ranking_return"] = float(current) / float(previous) - 1.0
        results.append(result)

    if ranking_metric != "return":
        return results

    candidates = [
        result for result in results
        if result["ranking_return"] is not None
        and (not entry_conditions or result["entry_signal"])
    ]
    candidates.sort(key=lambda result: result["ranking_return"], reverse=True)
    candidate_count = len(candidates)
    selected = candidates[:max_positions] if (
        rebalancing_period == "none" or rebalance_due
    ) else []
    for rank, result in enumerate(selected, start=1):
        top_pct = max(1, round((rank - 1) / candidate_count * 100))
        result["entry_signal"] = True
        result["entry_reason"] = (
            f"최근 {lookback}거래일 수익률 상위 {top_pct}% "
            f"({rank}/{candidate_count}위)"
        )

    selected_symbols = {result["symbol"] for result in selected}
    ranking_ready = any(result["ranking_return"] is not None for result in results)
    for result in results:
        result["rebalance_due"] = rebalance_due
        result["ranking_ready"] = ranking_ready
        if result["symbol"] not in selected_symbols:
            result["entry_signal"] = False
            result["entry_reason"] = None
    return sorted(
        results,
        key=lambda result: (
            result["ranking_return"] is not None,
            result["ranking_return"]
            if result["ranking_return"] is not None
            else float("-inf"),
        ),
        reverse=True,
    )


def _period_key(value: Any, period: str) -> tuple[int, ...]:
    date = pd.Timestamp(value)
    if period == "weekly":
        iso = date.isocalendar()
        return int(iso.year), int(iso.week)
    if period == "monthly":
        return date.year, date.month
    if period == "bimonthly":
        return date.year, (date.month - 1) // 2
    if period == "quarterly":
        return date.year, (date.month - 1) // 3
    if period == "semiannual":
        return date.year, (date.month - 1) // 6
    if period == "yearly":
        return (date.year,)
    return ()


def resolve_live_universe(
    strategy: dict[str, Any] | None,
    fallback_symbols: list[str],
) -> list[str]:
    """Resolve the current listed universe without using historical winners.

    상장폐지 종목은 어떤 경로로 해석됐든 마지막에 제외한다 — korea-stocks.json 에는
    상장 상태 필드가 없어 상폐 종목이 섞여 들어오고, Stock 테이블에 행이 없으면
    체결 직전 게이트도 NORMAL 로 통과시킨다.
    """
    return _exclude_delisted(_resolve_universe_symbols(strategy, fallback_symbols))


def _resolve_universe_symbols(
    strategy: dict[str, Any] | None,
    fallback_symbols: list[str],
) -> list[str]:
    strategy = strategy if isinstance(strategy, dict) else {}
    target_symbols = strategy.get("target_symbols")
    if isinstance(target_symbols, list) and target_symbols:
        return _unique_symbols(target_symbols)

    raw_universe = strategy.get("universe_id")
    universe_config = strategy.get("universe")
    filters: dict[str, Any] = {}
    if raw_universe is None and isinstance(universe_config, dict):
        raw_universe = universe_config.get("id")
        filters = universe_config.get("filters") or {}
    elif raw_universe is None:
        raw_universe = universe_config

    if isinstance(raw_universe, list):
        universe_id = "_".join(sorted(str(item).lower() for item in raw_universe))
    else:
        universe_id = str(raw_universe or "").strip().lower()
    universe_id = _UNIVERSE_ALIASES.get(universe_id, universe_id)
    sector = strategy.get("sector") or filters.get("selectedSectors")

    try:
        if universe_id == "etf":
            payload = json.loads((_DATA_DIR / "etf-master.json").read_text(encoding="utf-8"))
            etfs = [
                item for item in payload.get("etfs", [])
                if item.get("hasOhlcv") and not item.get("delistingDate")
            ]
            theme = strategy.get("etf_theme") or filters.get("theme")
            if theme:
                key = str(theme).replace(" ", "").lower()
                exact = [
                    item for item in etfs
                    if str(item.get("name", "")).replace(" ", "").lower() == key
                ]
                etfs = exact or [
                    item for item in etfs
                    if key in str(item.get("name", "")).replace(" ", "").lower()
                ]
            return _unique_symbols([item.get("symbol") for item in etfs])

        if universe_id in _INDEX_ROSTERS:
            roster = _DATA_DIR / _INDEX_ROSTERS[universe_id]
            payload = json.loads(roster.read_text(encoding="utf-8"))
            symbols = _unique_symbols(payload.get("symbols", []))
            if not sector:
                return symbols
            stocks = _load_current_stocks()
            sectors = set(sector if isinstance(sector, list) else [sector])
            return [
                symbol for symbol in symbols
                if stocks.get(symbol, {}).get("sector") in sectors
            ]

        # 부분일치는 KOR_KOSPI200 을 "KOSPI 전체"로 넓히므로 토큰 단위로만 맞춘다.
        tokens = set(universe_id.split("_"))
        markets = set()
        if "kospi" in tokens:
            markets.add("KOSPI")
        if "kosdaq" in tokens:
            markets.add("KOSDAQ")
        if markets:
            stocks = _load_current_stocks()
            sectors = set(sector if isinstance(sector, list) else [sector]) if sector else set()
            return [
                symbol for symbol, item in stocks.items()
                if item.get("market") in markets
                and (not sectors or item.get("sector") in sectors)
            ]
    except (OSError, ValueError, TypeError):
        pass
    return _unique_symbols(fallback_symbols)


def _load_delisted_symbols() -> set[str]:
    """DelistedSymbolStore 가 쓰는 상장폐지 원장. 읽기 실패 시 빈 집합."""
    try:
        payload = json.loads((_DATA_DIR / "delisted-stocks.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return set()
    return {
        str(symbol).split(".")[0]  # 152550.KS / .KQ 접미사 정규화
        for symbol in payload.get("symbols", [])
        if symbol
    }


def _exclude_delisted(symbols: list[str]) -> list[str]:
    delisted = _load_delisted_symbols()
    if not delisted:
        return symbols
    return [symbol for symbol in symbols if symbol not in delisted]


def _load_current_stocks() -> dict[str, dict[str, Any]]:
    stocks = json.loads((_DATA_DIR / "korea-stocks.json").read_text(encoding="utf-8"))
    return {
        str(item["symbol"]): item
        for item in stocks
        if item.get("symbol")
    }


def _unique_symbols(symbols: list[Any]) -> list[str]:
    return list(dict.fromkeys(str(symbol).strip() for symbol in symbols if symbol))


def count_holding_sessions(
    data_loader: Any,
    symbol: str,
    opened_at: Any,
    through_date: str,
    quote: Any = None,
) -> int:
    """Count KRX data rows after the entry session through the current session."""
    df = data_loader.load_symbol_data(symbol)
    if df is None or len(df) == 0 or "date" not in df.columns:
        return 0
    live_df = apply_realtime_quote(df, quote)
    dates = pd.to_datetime(live_df["date"].to_list(), errors="coerce")
    opened = pd.Timestamp(opened_at)
    if opened.tzinfo is not None:
        opened = opened.tz_convert("Asia/Seoul")
    opened_date = opened.tz_localize(None).normalize()
    through = pd.Timestamp(through_date).normalize()
    return int(((dates > opened_date) & (dates <= through)).sum())
