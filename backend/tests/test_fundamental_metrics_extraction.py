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


def test_pcr_supported_in_engine_and_llm_lane_with_legacy_fallback_cue():
    """PCR 정식 지원 승격(2026-08-03) — parquet pcr 컬럼 + 엔진 라벨 + LLM 레인 스키마.

    결정적 추출기는 PCR을 추출하지 않는다(원문 정규식 어휘 추가 금지 — 대원칙 1).
    따라서 cash_flow 큐는 목록에 남아 규칙 기반 레인을 LLM 폴백으로 위임시키고,
    LLM이 pcr 필터로 반영하면 _CONCEPT_EXPRESSED_PREDICATES가 안내를 뺀다."""
    from engine.nl_parser import FundamentalFilter, _mentioned_unsupported_concepts

    assert "pcr" in FUNDAMENTAL_CIDS
    assert FUNDAMENTAL_LABELS["pcr"] == "PCR"
    assert _default_operator_for_metric("pcr") == "<="
    # LLM 출력 스키마(Literal)가 pcr을 받는다 — 컴파일 통과의 전제.
    assert FundamentalFilter(metric="pcr", operator="<=", value=10.0).metric == "pcr"
    # 큐는 유지 — 규칙 기반 레인은 여전히 자신을 불신하고 LLM에 위임해야 한다(침묵 누락 방지).
    assert "cash_flow" in _mentioned_unsupported_concepts("PCR 10 이하 종목")


def test_expressed_pcr_drops_unsupported_notice():
    """LLM이 PCR을 pcr 필터로 반영했으면 '현금흐름 조건 미지원' 안내를 내지 않는다
    (ocf_growth 오탐 수정과 동형 계약)."""
    from engine.nl_parser import build_unsupported_concept_notice, concepts_expressed_in_strategy

    text = "코스피에서 PCR 10 이하 종목 10개 매수"
    parsed = _parsed(fundamental_filters=[
        {"metric": "pcr", "operator": "<=", "value": 10.0},
    ])
    assert concepts_expressed_in_strategy(parsed, text) == {"cash_flow"}
    assert build_unsupported_concept_notice(
        text, exclude=concepts_expressed_in_strategy(parsed, text)) is None


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


# ── 미지원 안내 오탐(2026-08-01): 전략이 이미 표현한 개념은 안내에서 뺀다 ──────────
def _parsed(**kwargs):
    from engine.nl_parser import ParsedStrategy

    return ParsedStrategy(description="x", universe=["KOSPI"], **kwargs)


def test_expressed_cash_flow_growth_drops_unsupported_notice():
    """'영업활동현금흐름 증가율 10% 이상'은 ocf_growth로 정식 지원된다 — 반영됐는데
    "현금흐름 조건 미지원" 안내가 함께 나가던 오탐(예시 QA 2026-08-01)."""
    from engine.nl_parser import build_unsupported_concept_notice, concepts_expressed_in_strategy

    text = "최근 4개 분기 영업활동현금흐름 증가율이 10% 이상인 기업을 선별해 주세요"
    parsed = _parsed(fundamental_filters=[
        {"metric": "ocf_growth", "operator": ">=", "value": 10.0},
    ])
    assert concepts_expressed_in_strategy(parsed, text) == {"cash_flow"}
    assert build_unsupported_concept_notice(
        text, exclude=concepts_expressed_in_strategy(parsed, text)) is None


def test_invented_growth_threshold_keeps_cash_flow_notice():
    """'현금흐름이 흑자'(수준 조건)를 ocf_growth>=0으로 옮긴 유사 대체는 안내를 남긴다 —
    입력에 없는 임계값이면 표현이 아니라 조용한 의미 변경이다."""
    from engine.nl_parser import build_unsupported_concept_notice, concepts_expressed_in_strategy

    text = "PBR 1.3배 이하이면서 영업활동현금흐름이 최근 분기 기준 흑자인 기업만 보고 싶습니다"
    parsed = _parsed(fundamental_filters=[
        {"metric": "pbr", "operator": "<=", "value": 1.3},
        {"metric": "ocf_growth", "operator": ">=", "value": 0.0},
    ])
    assert concepts_expressed_in_strategy(parsed, text) == set()
    assert "현금흐름" in (build_unsupported_concept_notice(text) or "")


def test_expressed_ma_alignment_drops_unsupported_notice():
    """'20일 EMA가 60일 EMA 위' 같은 정배열은 두 선의 상하 관계로 표현된다 — 전략에
    반영됐는데 "정배열 미지원" 안내가 함께 나가던 오탐."""
    from engine.nl_parser import build_unsupported_concept_notice, concepts_expressed_in_strategy

    text = "20일 EMA가 60일 EMA 위에 있는 정배열 상태에서 종가가 5일 EMA를 회복하면 매수"
    parsed = _parsed(entry_signals=[
        {"indicator": "ema", "short_period": 20, "long_period": 60, "mode": "above"},
    ])
    assert concepts_expressed_in_strategy(parsed, text) == {"ema_alignment"}
    assert build_unsupported_concept_notice(
        text, exclude=concepts_expressed_in_strategy(parsed, text)) is None
    # 이동평균 조건이 하나도 없으면(표현 실패) 안내는 그대로 유지된다.
    assert "정배열" in (build_unsupported_concept_notice(text, exclude=concepts_expressed_in_strategy(
        _parsed(), text)) or "")


def test_pending_dividend_condition_drops_unsupported_notice():
    """회귀: 값 대기 중인 조건을 되묻는 그 응답에 '지원되지 않아요'가 함께 나가면 안 된다.

    2026-08-04 실측 — "고배당률 종목 투자 전략"이 배당수익률 기준값을 되묻으면서
    동시에 "'배당 조건'은 아직 직접 지원되지 않아요"를 냈다. 값이 미정이라 parsed에
    없을 뿐 이해하지 못한 것이 아니다(값-대기 조건은 pending_conditions 채널에 있다).
    """
    from engine.nl_parser import build_unsupported_concept_notice, concepts_covered_by_pending

    text = "고배당률 종목 투자 전략"
    # 값이 없어 컴파일에서 빠졌지만 '배당수익률'로 이해한 상태
    pending = [{"role": "entry", "label": "배당수익률", "source_text": "고배당률"}]

    assert concepts_covered_by_pending(pending) == {"dividend"}
    assert build_unsupported_concept_notice(
        text, exclude=concepts_covered_by_pending(pending)) is None
    # 값 대기 조건이 없으면(=정말 표현하지 못한 경우) 안내는 그대로 유지된다.
    assert build_unsupported_concept_notice(text, exclude=None) is not None


def test_pending_unrelated_condition_keeps_unsupported_notice():
    """값 대기 조건이 있어도 무관한 지표면 미지원 안내를 삼키지 않는다(과잉 억제 방지)."""
    from engine.nl_parser import build_unsupported_concept_notice, concepts_covered_by_pending

    pending = [{"role": "entry", "label": "부채비율", "source_text": "부채"}]
    assert concepts_covered_by_pending(pending) == set()
    assert "배당" in (build_unsupported_concept_notice(
        "배당주 중에 부채 적은 곳", exclude=concepts_covered_by_pending(pending) or None) or "")


def test_concepts_covered_by_pending_handles_empty_and_malformed():
    from engine.nl_parser import concepts_covered_by_pending

    assert concepts_covered_by_pending(None) == set()
    assert concepts_covered_by_pending([]) == set()
    assert concepts_covered_by_pending([{}, {"label": None}]) == set()


# ── 현금흐름 3분류 조건 지표 승격 (2026-08-05) ──

def test_cash_flow_buckets_are_supported_indicators_with_eok_unit():
    """3분류가 정식 지원 지표로 잡히고 단위가 억원이어야 한다 — raw 원(1e8배)로
    노출되면 '1,000억 이상'이 통째로 어긋난다."""
    from strategy_conversation.registry import indicator_registry as reg

    for alias, metric in (
        ("영업활동현금흐름", "fundamental.operating_cf_amount"),
        ("투자활동현금흐름", "fundamental.investing_cf_amount"),
        ("재무활동현금흐름", "fundamental.financing_cf_amount"),
    ):
        spec = reg.resolve(alias)
        assert spec is not None and spec.id == metric
        assert spec.supported != "UNSUPPORTED"
        assert spec.value_type == "억원"


def test_cash_flow_growth_aliases_are_not_cannibalized_by_amount_promotion():
    """'…증가율'은 여전히 성장률 지표로 남아야 한다(절대 금액이 잠식하면 안 된다)."""
    from strategy_conversation.registry import indicator_registry as reg

    assert reg.resolve("영업활동현금흐름증가율").id == "fundamental.ocf_growth"
    assert reg.resolve("잉여현금흐름증가율").id == "fundamental.fcf_growth"


def test_cash_flow_buckets_are_engine_filterable_amount_metrics():
    """엔진 SOT(FUNDAMENTAL_LABELS)에 등록되고 금액 배지 대상이어야 한다."""
    from engine.signals import FUNDAMENTAL_AMOUNT_CIDS

    for cid in ("operating_cf_amount", "investing_cf_amount", "financing_cf_amount"):
        assert cid in FUNDAMENTAL_LABELS
        assert cid in FUNDAMENTAL_AMOUNT_CIDS


def test_cash_flow_amounts_are_derived_in_eok_from_raw_won():
    """저장된 raw 원 값에서 억원 파생본이 만들어지고 raw는 보존돼야 한다."""
    from engine.fundamental_fetcher import _compute_derived_annual_metrics

    out = _compute_derived_annual_metrics([{
        "year_end": "2024-12-31",
        "operating_cash_flow": 72_982_621_000_000.0,
        "investing_cash_flow": -85_381_702_000_000.0,
        "financing_cash_flow": -7_797_243_000_000.0,
    }])[0]

    assert out["operating_cf_amount"] == pytest.approx(729_826.2)
    assert out["investing_cf_amount"] == pytest.approx(-853_817.0)
    assert out["financing_cf_amount"] == pytest.approx(-77_972.4)
    assert out["operating_cash_flow"] == 72_982_621_000_000.0  # PCR 계산 기준 보존


def test_condition_builder_patterns_distinguish_amount_from_growth():
    """'영업활동현금흐름'은 절대 금액, '…증가율'은 성장률로 갈려야 한다."""
    from intent.condition_builder import _PATTERNS

    def hits(text):
        return {k for k, p in _PATTERNS.items() if p.search(text)}

    assert hits("영업활동현금흐름 1000억 이상") == {"operating_cf_amount"}
    assert hits("영업활동현금흐름 증가율 10%") == {"ocf_growth"}
    assert hits("투자활동현금흐름") == {"investing_cf_amount"}
    assert hits("재무활동 현금흐름") == {"financing_cf_amount"}
