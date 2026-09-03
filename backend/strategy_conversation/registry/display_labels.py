"""지표·파라미터의 표시 라벨 — UI 언어(ui_language)에 따라 한국어 정본/영어를 고른다.

정본은 IndicatorSpec.display_name(한국어)이다. /us(en)에서는 값이 섞인 되묻기 질문
("진입 조건의 매출액증가율 기준값을 얼마로 할까요?")을 백엔드가 영어로 만들어야 하므로
(프론트 사전은 완성 문장 정확 일치라 f-string을 옮길 수 없다 — ui_language.msg 레인),
그 문장 안에 들어갈 지표 이름의 영어 표기를 여기서 준다. 표에 없는 id는 canonical id의
꼬리("revenue_growth")를 사람이 읽는 형태로 바꿔 쓴다(조용히 한국어를 내보내지 않는다).
"""
from __future__ import annotations

import ui_language

_EN_LABELS = {
    "fundamental.per": "P/E ratio", "fundamental.pbr": "P/B ratio", "fundamental.psr": "P/S ratio",
    "fundamental.pcr": "P/CF ratio", "fundamental.ev_ebitda": "EV/EBITDA",
    "fundamental.ev_ebit": "EV/EBIT", "fundamental.roe_or_gpa": "ROE", "fundamental.roa": "ROA",
    "fundamental.debt_ratio": "Debt ratio", "fundamental.current_ratio": "Current ratio",
    "fundamental.quick_ratio": "Quick ratio", "fundamental.reserve_ratio": "Reserve ratio",
    "fundamental.net_margin": "Net margin", "fundamental.gross_margin": "Gross margin",
    "fundamental.operating_margin": "Operating margin",
    "fundamental.revenue_growth": "Revenue growth",
    "fundamental.operating_income_growth": "Operating income growth",
    "fundamental.net_income_growth": "Net income growth", "fundamental.eps_growth": "EPS growth",
    "fundamental.ebitda_growth": "EBITDA growth",
    "fundamental.ocf_growth": "Operating cash flow growth",
    "fundamental.fcf_growth": "Free cash flow growth", "fundamental.market_cap": "Market cap",
    "fundamental.trading_value": "Average daily trading value",
    "fundamental.dividend_yield": "Dividend yield", "fundamental.payout_rate": "Payout ratio",
    "fundamental.dividend_growth": "Dividend growth", "fundamental.eps": "EPS",
    "fundamental.ebit": "Operating income", "fundamental.net_income": "Net income",
    "fundamental.owner_net_income": "Net income attributable to owners",
    "fundamental.operating_cf_amount": "Operating cash flow",
    "fundamental.investing_cf_amount": "Investing cash flow",
    "fundamental.financing_cf_amount": "Financing cash flow",
    "technical.ma_crossover": "Moving-average crossover", "technical.ema": "EMA",
    "technical.rsi": "RSI", "technical.macd": "MACD", "technical.bollinger_bands": "Bollinger Bands",
    "technical.breakout": "New-high breakout", "technical.volume_spike": "Volume spike (OBV)",
    "technical.stochastic": "Stochastic", "technical.cci": "CCI", "technical.adx": "ADX",
    "technical.williams_r": "Williams %R", "technical.mfi": "MFI", "technical.roc": "ROC",
    "technical.volatility": "Volatility (annualized)", "technical.trading_value": "Trading value",
    "technical.ai_model": "AI upside prediction", "technical.ai_drop_model": "AI drawdown exit",
    "ranking.return": "Period return ranking (momentum)",
    "ranking.volatility": "Volatility ranking (low volatility)",
}

_EN_PARAM_LABELS = {
    "short_period": "short period", "long_period": "long period", "period": "period",
    "lookback_period": "lookback period", "lookback_days": "lookback days", "threshold": "threshold",
}

# 값 단위 표기 — 한국어 정본(ratio='배', 억원)과 영어 표기가 다르다.
_EN_UNITS = {"percent": "%", "ratio": "x", "억원": " (100M KRW)", "point": ""}


def is_en() -> bool:
    return ui_language.get_ui_language() == "en"


def display_label(spec, ko: str | None = None) -> str:
    """지표 표시명 — en이면 영어, 아니면 한국어 정본(display_name 또는 ko)."""
    if not is_en():
        return ko if ko is not None else spec.display_name
    label = _EN_LABELS.get(spec.id)
    if label:
        return label
    tail = spec.id.split(".", 1)[-1].replace("_", " ")
    return tail[:1].upper() + tail[1:]


def param_label(name: str, ko: str) -> str:
    return _EN_PARAM_LABELS.get(name, name.replace("_", " ")) if is_en() else ko


def unit_label(value_type: str | None, ko_units: dict) -> str:
    if not is_en():
        return ko_units.get(value_type or "", "")
    return _EN_UNITS.get(value_type or "", "")
