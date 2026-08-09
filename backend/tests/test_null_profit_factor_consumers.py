"""손익비 null(손실 거래 0건 = ∞) 소비처 회귀 테스트.

엔진 v12.0부터 무손실 백테스트의 profitFactor는 None으로 내려온다. None을 0으로
접으면 전승 전략이 '최악'으로 뒤집힌다 — 리서치 게이트와 최적화 리포트가 그 사고를
겪은 소비처다.
"""

from ai.local_optimization_agent import LocalOptimizationAgent
from research.safeguards import PrescreenGates


def _passing_result(**overrides):
    base = {
        "trades": 40,
        "cagr": 0.10,
        "profitFactor": 1.5,
        "maxDrawdown": 0.2,
    }
    base.update(overrides)
    return base


def test_safeguards_null_pf_passes_min_gate():
    # 회귀: `or 0`이 None을 0으로 접어 전승 전략이 '손익비 미달'로 탈락했다
    ok, reason = PrescreenGates().passes(_passing_result(profitFactor=None), years=3.0)
    assert ok, reason


def test_safeguards_low_pf_still_fails():
    ok, reason = PrescreenGates().passes(_passing_result(profitFactor=0.8), years=3.0)
    assert not ok
    assert "profitFactor" in reason


def test_optimization_report_shows_infinity_for_null_pf():
    assert LocalOptimizationAgent._fmt_pf(None) == "∞"
    assert LocalOptimizationAgent._fmt_pf(1.234) == "1.23"
