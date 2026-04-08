from __future__ import annotations

from typing import Any

import pandas as pd
import polars as pl

from engine.indicators import IndicatorEngine


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
