"""신규 펀더멘털 지표(ROA/PSR/유동비율/성장률 등)의 결정적 파싱·엔진 라벨 회귀 테스트."""
import pytest

from engine.nl_parser import _extract_fundamental_filters, _default_operator_for_metric
from engine.signals import FUNDAMENTAL_CIDS, FUNDAMENTAL_LABELS


@pytest.mark.parametrize("text,metric,operator,value", [
    ("ROA 5% 이상", "roa", ">=", 5.0),
    ("PSR 2 이하", "psr", "<=", 2.0),
    ("유동비율 150 이상", "current_ratio", ">=", 150.0),
    ("당좌비율 100 이상", "quick_ratio", ">=", 100.0),
    ("유보율 500 이상", "reserve_ratio", ">=", 500.0),
    ("순이익률 10% 이상", "net_margin", ">=", 10.0),
    ("매출총이익률 30% 이상", "gross_margin", ">=", 30.0),
    ("영업이익률 15% 이상", "operating_margin", ">=", 15.0),
    ("매출액증가율 20% 이상", "revenue_growth", ">=", 20.0),
    ("영업이익증가율 15% 이상", "operating_income_growth", ">=", 15.0),
    ("순이익증가율 12% 이상", "net_income_growth", ">=", 12.0),
])
def test_new_metric_extraction(text, metric, operator, value):
    filters = _extract_fundamental_filters(text)
    match = [f for f in filters if f.metric == metric]
    assert match, f"{metric} not extracted from {text!r}"
    assert match[0].operator == operator
    assert match[0].value == pytest.approx(value)


def test_growth_not_confused_with_margin():
    # '순이익증가율'이 '순이익률'(net_margin)로 오인되면 안 된다.
    filters = _extract_fundamental_filters("순이익증가율 10% 이상")
    metrics = {f.metric for f in filters}
    assert "net_income_growth" in metrics
    assert "net_margin" not in metrics


def test_operating_margin_not_confused_with_growth():
    # '영업이익률'(operating_margin)과 '영업이익증가율'(operating_income_growth)은 서로 오인되면 안 된다.
    margin = {f.metric for f in _extract_fundamental_filters("영업이익률 15% 이상")}
    assert "operating_margin" in margin
    assert "operating_income_growth" not in margin

    growth = {f.metric for f in _extract_fundamental_filters("영업이익증가율 15% 이상")}
    assert "operating_income_growth" in growth
    assert "operating_margin" not in growth


def test_lower_is_better_default_operators():
    for m in ("per", "pbr", "psr", "debt_ratio"):
        assert _default_operator_for_metric(m) == "<="
    for m in ("roa", "roe_or_gpa", "current_ratio", "revenue_growth", "net_margin"):
        assert _default_operator_for_metric(m) == ">="


def test_new_metrics_are_engine_filterable_with_labels():
    for m in ("roa", "psr", "current_ratio", "quick_ratio", "reserve_ratio",
              "net_margin", "gross_margin", "operating_margin", "revenue_growth",
              "operating_income_growth", "net_income_growth"):
        assert m in FUNDAMENTAL_CIDS
        assert m in FUNDAMENTAL_LABELS


@pytest.mark.parametrize("text,operator,value", [
    ("EV/EBITDA 8 이하", "<=", 8.0),
    ("ev/ebitda 8배 이하", "<=", 8.0),
    ("EV EBITDA 10 미만", "<", 10.0),
    ("에비타 6배 이하", "<=", 6.0),
])
def test_ev_ebitda_extraction(text, operator, value):
    filters = _extract_fundamental_filters(text)
    match = [f for f in filters if f.metric == "ev_ebitda"]
    assert match, f"ev_ebitda not extracted from {text!r}"
    assert match[0].operator == operator
    assert match[0].value == pytest.approx(value)


def test_ev_ebitda_is_supported_not_flagged_unsupported():
    # EV/EBITDA는 이제 데이터가 있어 지원된다 — 미지원 안내가 뜨면 안 된다.
    from engine.nl_parser import build_unsupported_concept_notice
    assert build_unsupported_concept_notice("EV/EBITDA 8배 이하 종목") is None
    assert _default_operator_for_metric("ev_ebitda") == "<="
    assert "ev_ebitda" in FUNDAMENTAL_CIDS
    assert FUNDAMENTAL_LABELS["ev_ebitda"] == "EV/EBITDA"


def test_ev_ebitda_forward_fill_and_sentinel_drop():
    # ev_ebitda가 결산 스냅샷으로 전진충전되고, 0(센티널)은 채워지지 않아야 한다.
    import pandas as pd
    from engine.fundamental_fetcher import enrich_ohlcv_with_fundamentals
    df = pd.DataFrame({
        "date": pd.to_datetime(["2023-06-01", "2024-06-01", "2025-06-01"]),
        "open": [100.0, 110.0, 120.0], "high": [100.0, 110.0, 120.0],
        "low": [100.0, 110.0, 120.0], "close": [100.0, 110.0, 120.0],
        "volume": [1000.0, 1000.0, 1000.0],
    })
    funds = [
        {"year_end": "2022-12-31", "ev_ebitda": 5.0},
        {"year_end": "2023-12-31", "ev_ebitda": 7.0},
        # 2024는 ev_ebitda 없음(센티널 제거된 상태) → 2023 값이 유지돼야 함
        {"year_end": "2024-12-31", "eps": 1000.0},
    ]
    en = enrich_ohlcv_with_fundamentals(df, funds)
    assert "ev_ebitda" in en.columns
    # 2023-06(2022 결산 반영, 90일 지연) = 5.0, 2024-06(2023 결산) = 7.0, 2025-06(2024엔 없음→7.0 유지)
    vals = en["ev_ebitda"].tolist()
    assert vals[0] == pytest.approx(5.0)
    assert vals[1] == pytest.approx(7.0)
    assert vals[2] == pytest.approx(7.0)


@pytest.mark.parametrize("text,metric,operator,value", [
    ("배당수익률 3% 이상", "dividend_yield", ">=", 3.0),
    ("시가배당률 4% 이상 매수", "dividend_yield", ">=", 4.0),
    ("배당성향 30% 이상", "payout_rate", ">=", 30.0),
])
def test_dividend_metric_extraction(text, metric, operator, value):
    filters = _extract_fundamental_filters(text)
    match = [f for f in filters if f.metric == metric]
    assert match, f"{metric} not extracted from {text!r}"
    assert match[0].operator == operator
    assert match[0].value == pytest.approx(value)


def test_dividend_yield_supported_but_growth_still_unsupported():
    from engine.nl_parser import build_unsupported_concept_notice
    # 배당수익률/배당성향은 지원 → 미지원 안내 없음
    assert build_unsupported_concept_notice("배당수익률 3% 이상 고배당주") is None
    assert "dividend_yield" in FUNDAMENTAL_CIDS
    assert FUNDAMENTAL_LABELS["dividend_yield"] == "배당수익률"
    # 배당 성장/증가는 여전히 미지원 → 안내 유지
    assert build_unsupported_concept_notice("배당 성장주 위주로 담아줘") is not None


@pytest.mark.parametrize("text,value", [
    ("배당성장률 10% 이상", 10.0),
    ("배당증가율 15% 이상 종목", 15.0),
])
def test_dividend_growth_extraction(text, value):
    filters = _extract_fundamental_filters(text)
    match = [f for f in filters if f.metric == "dividend_growth"]
    assert match, f"dividend_growth not extracted from {text!r}"
    assert match[0].operator == ">="
    assert match[0].value == pytest.approx(value)


def test_dividend_growth_supported_no_unsupported_notice():
    from engine.nl_parser import build_unsupported_concept_notice
    assert build_unsupported_concept_notice("배당성장률 10% 이상 종목 매수") is None
    assert "dividend_growth" in FUNDAMENTAL_CIDS
