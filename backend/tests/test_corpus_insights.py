"""AI 리포트 코퍼스 비교(advisor/corpus_insights.py) 테스트.

총평이 '결과 읽기'에 그치지 않도록, 동일 엔진 시뮬레이션 코퍼스 대비
백분위·구조 장치 유무별 과거 통계를 결정론적으로 만드는지 검증한다.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

import advisor.corpus_insights as ci
from advisor.similarity import extract_structural_features


def _row(dsl: dict, metrics: dict) -> dict:
    return {"metrics": metrics, "dsl": dsl, "features": extract_structural_features(dsl)}


def _pbr_dsl(stop_loss=None, max_positions=10):
    return {
        "universe": ["KOSPI200"],
        "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1.0}],
        "entry_signals": [],
        "exit_signals": [],
        "stop_loss_pct": stop_loss,
        "max_positions": max_positions,
        "rebalancing_period": "none",
    }


def _rsi_dsl():
    return {
        "universe": ["KOSPI200"],
        "fundamental_filters": [],
        "entry_signals": [{"indicator": "rsi", "operator": "<", "threshold": 30, "period": 14}],
        "exit_signals": [{"indicator": "rsi", "operator": ">", "threshold": 70, "period": 14}],
        "stop_loss_pct": None,
        "max_positions": 10,
        "rebalancing_period": "none",
    }


def _install_corpus(monkeypatch, rows):
    monkeypatch.setattr(ci, "_corpus_cache", rows)
    monkeypatch.setattr(ci, "_MIN_COHORT", 4)
    monkeypatch.setattr(ci, "_MIN_CONTRAST_GROUP", 2)


def test_returns_none_without_cagr_or_corpus(monkeypatch):
    _install_corpus(monkeypatch, [])
    assert ci.build_corpus_comparison(None, {"cagr": 10.0}) is None

    _install_corpus(monkeypatch, [_row(_pbr_dsl(), {"cagr": 0.1, "mdd": -0.1})] * 10)
    assert ci.build_corpus_comparison(None, {"maxDrawdown": -10.0}) is None


def test_percentile_lines_against_full_corpus(monkeypatch):
    # CAGR 분포: 1%~10% (10개). 사용자 9.5% → 9개를 이김 → 상위 10%.
    rows = [
        _row(_pbr_dsl(), {"cagr": (i + 1) / 100.0, "mdd": -0.10 - i / 100.0, "sharpe": 0.5 + i / 10.0, "win_rate": 0.40 + i / 100.0})
        for i in range(10)
    ]
    _install_corpus(monkeypatch, rows)

    cmp = ci.build_corpus_comparison(None, {"cagr": 9.5, "maxDrawdown": -20.93, "sharpe": 0.71, "winRate": 42.72})

    assert cmp is not None
    assert cmp["cohort_size"] == 10
    assert "상위 10%" in cmp["lines"][0]  # CAGR
    assert "9.50%" in cmp["lines"][0]
    # MDD -20.93%는 -0.10~-0.19 분포보다 깊음 → 방어력 최하위(하위 1%) + '깊은 낙폭' 명시
    assert any("최대 낙폭" in line and "하위 1%" in line and "깊은 낙폭" in line for line in cmp["lines"])
    # parsed_strategy 없이는 전체 코퍼스 라벨
    assert "과거 전략 시뮬레이션 10개" in cmp["cohort_label"]


def test_similar_cohort_selected_when_structure_matches(monkeypatch):
    # PBR 계열 6개 + RSI 계열 6개 — PBR 전략 질의 시 유사 코호트만 선택돼야 한다.
    pbr_rows = [_row(_pbr_dsl(stop_loss=8.0), {"cagr": 0.05 + i / 100.0, "mdd": -0.10, "sharpe": 0.8, "win_rate": 0.5}) for i in range(6)]
    rsi_rows = [_row(_rsi_dsl(), {"cagr": 0.50, "mdd": -0.50, "sharpe": 2.0, "win_rate": 0.9}) for _ in range(6)]
    _install_corpus(monkeypatch, pbr_rows + rsi_rows)

    cmp = ci.build_corpus_comparison(_pbr_dsl(stop_loss=10.0), {"cagr": 8.0, "maxDrawdown": -12.0})

    assert cmp is not None
    assert cmp["cohort_size"] == 6  # RSI 계열 제외
    assert "구조가 유사한" in cmp["cohort_label"]


def test_contrast_lines_only_for_missing_knobs(monkeypatch):
    # 손절 있는 그룹(MDD 얕음) vs 없는 그룹(깊음) — 손절 없는 사용자에게만 대조 통계 제공.
    with_stop = [_row(_pbr_dsl(stop_loss=8.0), {"cagr": 0.08, "mdd": -0.10, "sharpe": 0.9, "win_rate": 0.5}) for _ in range(3)]
    without_stop = [_row(_pbr_dsl(stop_loss=None), {"cagr": 0.09, "mdd": -0.22, "sharpe": 0.7, "win_rate": 0.5}) for _ in range(3)]
    _install_corpus(monkeypatch, with_stop + without_stop)

    no_stop_user = _pbr_dsl(stop_loss=None)
    cmp = ci.build_corpus_comparison(no_stop_user, {"cagr": 8.0, "maxDrawdown": -20.0})
    assert cmp is not None
    assert any("손절" in line and "-10.00%" in line and "-22.00%" in line for line in cmp["contrast_lines"])

    # 이미 손절을 갖춘 사용자는 손절 대조가 나오지 않는다.
    with_stop_user = _pbr_dsl(stop_loss=10.0)
    cmp2 = ci.build_corpus_comparison(with_stop_user, {"cagr": 8.0, "maxDrawdown": -20.0})
    assert cmp2 is not None
    assert not any("손절" in line for line in cmp2["contrast_lines"])


def test_shipped_corpus_artifact_loads_and_compares():
    """커밋된 corpus_insights_data.jsonl.gz가 실제로 로드·비교 가능해야 한다(프로덕션 동작 보증)."""
    ci._corpus_cache = None  # 실제 파일 로드 강제
    try:
        corpus = ci._load_corpus()
        assert len(corpus) >= 1000, "코퍼스 아티팩트가 없거나 손상됨 — scripts/export_corpus_insights.py 재실행 필요"

        cmp = ci.build_corpus_comparison(
            _pbr_dsl(stop_loss=None),
            {"cagr": 13.8, "maxDrawdown": -20.93, "sharpe": 0.71, "winRate": 42.72},
        )
        assert cmp is not None
        assert cmp["lines"], "비교 문장이 비어 있음"
        # 모든 문장에 오독 불가능한 순위(상위/하위)와 중앙값 대비 방향이 있어야 한다
        assert all(("상위" in line or "하위" in line) and "중앙값" in line for line in cmp["lines"])
    finally:
        ci._corpus_cache = None
