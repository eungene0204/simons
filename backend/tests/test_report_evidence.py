"""report_evidence 결정론 근거·성향·로드맵·개선 우선순위 테스트."""

from ai.report_evidence import (
    build_evidence_pack,
    classify_strategy_profile,
    build_validation_roadmap,
    build_improvement_priorities,
)


def _base_metrics(**over):
    m = {
        "cagr": 12.0,
        "maxDrawdown": -18.0,
        "sharpe": 1.1,
        "winRate": 52.0,
        "trades": 40,
        "volatility": 18.0,
        "periodStart": "2018-01-02",
        "periodEnd": "2024-12-30",
        "monthlyReturns": {f"2020-{i:02d}": 1.0 for i in range(1, 13)},
    }
    m.update(over)
    return m


# ── evidence pack ────────────────────────────────────────────────────────────

def test_time_concentration_detected_from_monthly_returns():
    # 한 달이 전체 플러스 수익의 대부분을 차지 → time_concentrated
    monthly = {"2020-01": 0.2, "2020-02": 0.3, "2020-03": 9.5, "2020-04": 0.1,
               "2020-05": -1.0, "2020-06": 0.2}
    ev = build_evidence_pack(_base_metrics(monthlyReturns=monthly))
    assert ev["signals"]["time_concentrated"] is True
    assert any("집중" in f for f in ev["facts"])


def test_low_sample_flagged():
    ev = build_evidence_pack(_base_metrics(trades=8))
    assert ev["signals"]["low_sample"] is True
    assert any("표본" in f for f in ev["facts"])


def test_high_winrate_low_expectancy_detected():
    ev = build_evidence_pack(_base_metrics(winRate=60.0, expectancy=0.2))
    assert ev["signals"]["high_winrate_low_expectancy"] is True


def test_symbol_concentration_from_per_asset_stats():
    per_asset = {"A": {"profit": 900}, "B": {"profit": 50}, "C": {"profit": 50}}
    ev = build_evidence_pack(_base_metrics(perAssetStats=per_asset))
    assert ev["signals"]["symbol_concentrated"] is True


def test_no_special_findings_returns_placeholder_fact():
    # 특이점이 없어도 facts 는 최소 1개(빈 프롬프트 방지).
    ev = build_evidence_pack({"trades": 100})
    assert ev["facts"]


# ── 전략 성향 ────────────────────────────────────────────────────────────────

def test_profile_mean_reversion_and_risk_posture():
    parsed = {
        "entry_signals": [{"indicator": "rsi", "params": {"operator": "<", "value": 30}}],
        "max_positions": 2,
    }
    tags = classify_strategy_profile(parsed, _base_metrics(volatility=30.0))
    assert "평균회귀형" in tags
    assert "고변동성" in tags
    # 손절/익절 미설정 → 공격형, 2종목 → 집중형
    assert "공격형(손절·익절 미설정)" in tags
    assert "집중형" in tags


# ── 검증 로드맵 ──────────────────────────────────────────────────────────────

def test_roadmap_recommends_monte_carlo_for_low_sample():
    ev = build_evidence_pack(_base_metrics(trades=8))
    roadmap = build_validation_roadmap(_base_metrics(trades=8), ev, None)
    titles = [i["title"] for i in roadmap]
    assert "몬테카를로 시뮬레이션" in titles
    # 각 항목은 근거를 동반한다.
    assert all(i["reason"] for i in roadmap if i["title"] == "몬테카를로 시뮬레이션")


def test_roadmap_recommends_walkforward_for_time_concentration():
    monthly = {"2020-01": 0.2, "2020-02": 9.5, "2020-03": 0.1, "2020-04": 0.1,
               "2020-05": 0.1, "2020-06": 0.1}
    metrics = _base_metrics(monthlyReturns=monthly)
    ev = build_evidence_pack(metrics)
    titles = [i["title"] for i in build_validation_roadmap(metrics, ev, None)]
    assert "워크포워드 검증" in titles


# ── 개선 우선순위 (점수 인지형·DSL 금지) ────────────────────────────────────

_DSL_FORBIDDEN = ["손절", "익절", "%", "지표를 추가", "파라미터를", "매수 조건", "매도 조건"]


def test_improvements_high_score_recommends_validation():
    ev = build_evidence_pack(_base_metrics())
    items = build_improvement_priorities(82, {"advisorScore": 82}, ev)
    joined = " ".join(items)
    assert "검증" in joined
    # 구체적 DSL 수정 문구는 없어야 한다.
    assert not any(tok in joined for tok in _DSL_FORBIDDEN)


def test_improvements_low_score_recommends_strategy_level_redirection():
    ev = build_evidence_pack(_base_metrics())
    items = build_improvement_priorities(38, {"advisorScore": 38}, ev)
    joined = " ".join(items)
    # 전략 수준 방향성(재검토/단순화/재구성)
    assert any(kw in joined for kw in ["재검토", "단순화", "새로 구성", "재구성"])
    assert not any(tok in joined for tok in _DSL_FORBIDDEN)


def test_improvements_never_empty():
    ev = build_evidence_pack(_base_metrics())
    assert build_improvement_priorities(None, None, ev)
