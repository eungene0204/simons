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


def test_lower_is_better_default_operators():
    for m in ("per", "pbr", "psr", "debt_ratio"):
        assert _default_operator_for_metric(m) == "<="
    for m in ("roa", "roe_or_gpa", "current_ratio", "revenue_growth", "net_margin"):
        assert _default_operator_for_metric(m) == ">="


def test_new_metrics_are_engine_filterable_with_labels():
    for m in ("roa", "psr", "current_ratio", "quick_ratio", "reserve_ratio",
              "net_margin", "gross_margin", "revenue_growth",
              "operating_income_growth", "net_income_growth"):
        assert m in FUNDAMENTAL_CIDS
        assert m in FUNDAMENTAL_LABELS
