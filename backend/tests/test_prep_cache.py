"""Phase1 산출물 캐시(engine/prep_cache.py) — 최적화·워크포워드 재계산 제거.

계약: 캐시 유무와 무관하게 백테스트 결과는 동일하다. 키는 지표 컬럼을 결정하는
'구조 파라미터'만 보므로 임계값·손절 같은 값만 바뀐 시도는 적중한다.
"""

import copy
import json
import re
from pathlib import Path

import pandas as pd
import pytest

from backtest_engine import BacktestEngine
from engine.prep_cache import STRUCTURAL_PARAM_KEYS, SymbolPrepCache, structural_signature
from engine.grid_optimizer import StrategyOptimizer, optimization_session


# ── 구조 서명 ────────────────────────────────────────────────────────

def _entry(**params):
    return {"logic": "AND", "conditions": [{"id": "rsi", "type": "entry", "params": params}]}


def test_signature_ignores_non_structural_params():
    a = structural_signature(_entry(period=14, threshold=30, direction="below"), None)
    b = structural_signature(_entry(period=14, threshold=25, direction="above"), None)
    assert a == b


def test_signature_changes_with_structural_params():
    a = structural_signature(_entry(period=14, threshold=30), None)
    b = structural_signature(_entry(period=12, threshold=30), None)
    assert a != b


def test_signature_preserves_condition_order_and_nesting():
    ma = {"id": "ma_crossover", "params": {"shortMA": 5, "longMA": 20}}
    rsi = {"id": "rsi", "params": {"period": 14}}
    nested = {"logic": "AND", "conditions": [{"logic": "OR", "conditions": [ma]}, rsi]}
    flat = {"logic": "AND", "conditions": [ma, rsi]}
    swapped = {"logic": "AND", "conditions": [rsi, ma]}
    assert structural_signature(nested, None) == structural_signature(flat, None)
    assert structural_signature(flat, None) != structural_signature(swapped, None)


def test_structural_whitelist_covers_every_param_read_by_indicator_code():
    """IndicatorEngine·DataResolver가 params에서 읽는 이름이 화이트리스트 밖이면
    캐시가 서로 다른 지표를 같은 키로 묶는다 — 새 파라미터는 반드시 여기에 등록한다."""
    engine_dir = Path(__file__).resolve().parents[1] / "engine"
    read_names = set()
    # params dict를 읽는 문법 전부를 잡는다: p.get('x') · p['x'] · params.get('x') · params['x'] · cond['params']['x']
    patterns = (
        r"""\b(?:p|params)\.get\(\s*['"]([A-Za-z_]+)['"]""",
        r"""\b(?:p|params)\[\s*['"]([A-Za-z_]+)['"]\s*\]""",
        r"""\[\s*['"]params['"]\s*\]\s*\[\s*['"]([A-Za-z_]+)['"]\s*\]""",
        r"""\[\s*['"]params['"]\s*\]\s*\.get\(\s*['"]([A-Za-z_]+)['"]""",
    )
    for fname in ("indicators.py", "indicator_columns.py", "data_resolver.py"):
        src = (engine_dir / fname).read_text(encoding="utf-8")
        for pat in patterns:
            read_names.update(re.findall(pat, src))
    read_names.discard("conditions")  # 그룹 재귀용 — 지표 파라미터가 아니다
    missing = read_names - STRUCTURAL_PARAM_KEYS
    assert not missing, f"STRUCTURAL_PARAM_KEYS에 없는 지표 파라미터: {sorted(missing)}"


# ── LRU 캐시 ────────────────────────────────────────────────────────

def _entry_dict(rows: int):
    pdf = pd.DataFrame({"close": range(rows)}, index=pd.RangeIndex(rows))
    return {"outcome": "ok", "pdf": pdf, "df_pl": None, "res_logs": [{"level": "INFO", "message": "x"}]}


def test_cache_returns_copies_isolated_from_mutation():
    cache = SymbolPrepCache(budget_bytes=10_000_000)
    cache.put(("A",), _entry_dict(10))
    got = cache.get(("A",))
    got["pdf"].loc[0, "close"] = 999
    got["res_logs"][0]["message"] = "mutated"
    again = cache.get(("A",))
    assert again["pdf"].loc[0, "close"] == 0
    assert again["res_logs"][0]["message"] == "x"
    assert cache.stats()["hits"] == 2


def test_cache_evicts_least_recently_used_within_budget():
    one = SymbolPrepCache._estimate_bytes(_entry_dict(1000))
    cache = SymbolPrepCache(budget_bytes=one * 2 + 10)
    cache.put(("A",), _entry_dict(1000))
    cache.put(("B",), _entry_dict(1000))
    assert cache.get(("A",)) is not None      # A를 최근 사용으로
    cache.put(("C",), _entry_dict(1000))      # 예산 초과 → 가장 오래된 B 퇴출
    assert cache.get(("B",)) is None
    assert cache.get(("A",)) is not None
    assert cache.get(("C",)) is not None


def test_oversized_entry_is_not_stored():
    cache = SymbolPrepCache(budget_bytes=10)
    cache.put(("A",), _entry_dict(1000))
    assert len(cache) == 0


# ── 엔진 통합: 결과 동일성 + 적중 ───────────────────────────────────

def _req(symbols, period=14, threshold=45, stop_loss=0.05):
    return {
        "symbols": symbols,
        "universe_id": None,
        "period": "full",
        "startDate": "2023-04-01",
        "endDate": "2023-12-15",
        "entry": {"logic": "AND", "conditions": [
            {"id": "rsi", "type": "entry", "params": {"period": period, "operator": "<", "value": threshold}},
        ]},
        "exit": {"logic": "OR", "conditions": [
            {"id": "rsi", "type": "exit", "params": {"period": period, "operator": ">", "value": 55}},
        ]},
        "risk": {"init_cash": 10_000_000, "stop_loss": stop_loss, "take_profit": None, "max_positions": 3},
        "options": {"execution_type": "next_open"},
    }


# mock_data_dir의 합성 시세는 hash(symbol)에 좌우돼 실행마다 다르다 — 거래가 흔히 나는 넓은 RSI 임계값(45/55)을 쓴다.
def _comparable(res):
    r = dict(res)
    r.pop("timing", None)
    # 결과 화면 전용 부가 산출물 — 세션 안에서는 의도적으로 만들지 않는다(별도 테스트)
    r.pop("rebalanceComparison", None)
    r["warnings"] = sorted(r.get("warnings") or [])
    # 종목별 스레드 완료 순서에 따라 원래부터 순서가 바뀌는 항목 — 집합으로 비교
    r["resolution_logs"] = sorted(json.dumps(x, sort_keys=True) for x in (r.get("resolution_logs") or []))
    return json.dumps(r, sort_keys=True, default=str)


def test_cached_results_identical_and_hits_on_value_only_changes(mock_data_dir):
    symbols = ["ALPHA", "BETA", "GAMMA"]
    engine = BacktestEngine(data_dir=mock_data_dir)
    cases = [
        _req(symbols, 14, 45, 0.05),
        _req(symbols, 14, 40, 0.05),   # 임계값만 변경 → 지표 동일 → 적중
        _req(symbols, 14, 45, 0.10),   # 손절만 변경 → Phase1 무관 → 적중
        _req(symbols, 10, 45, 0.05),   # 기간 변경 → 지표 다름 → 미적중
    ]
    plain_raw = [engine.run_backtest(copy.deepcopy(c)) for c in cases]
    plain = [_comparable(r) for r in plain_raw]
    assert all((r.get("trades") or 0) > 0 for r in plain_raw), "거래가 있는 전략이어야 동일성 검증이 의미 있다"
    assert engine._prep_cache is None
    assert all(isinstance(r.get("rebalanceComparison"), dict) for r in plain_raw), \
        "세션 밖(결과 화면용 단일 백테스트)에서는 리밸런싱 비교를 동봉한다"

    with engine.optimization_session() as cache:
        cached_raw = [engine.run_backtest(copy.deepcopy(c)) for c in cases]
        cached = [_comparable(r) for r in cached_raw]
        stats = cache.stats()
    assert engine._prep_cache is None, "세션이 끝나면 캐시가 내려가야 한다"
    assert all(r.get("rebalanceComparison") is None for r in cached_raw), \
        "세션 안(지표만 쓰는 반복)에서는 결과 화면 전용 재시뮬레이션을 만들지 않는다"

    assert plain == cached
    # 4회 × 3종목 = 12회 조회 중 2·3번째 케이스(6회)가 적중, 1·4번째(6회)가 미적중
    assert stats["hits"] == 6 and stats["misses"] == 6

    # 세션 밖(단일 백테스트)에서는 캐시가 개입하지 않는다
    assert _comparable(engine.run_backtest(copy.deepcopy(cases[0]))) == plain[0]


def test_grid_optimizer_opens_optimization_session(mock_data_dir):
    symbols = ["ALPHA", "BETA", "GAMMA"]
    engine = BacktestEngine(data_dir=mock_data_dir)
    seen = {}
    real_session = engine.optimization_session

    def spy_session():
        cm = real_session()
        seen["opened"] = True
        return cm
    engine.optimization_session = spy_session

    result = StrategyOptimizer(engine).optimize(
        base_request=_req(symbols),
        ranges={"risk.stop_loss": [0.05, 0.10, 0.15]},
        target_metric="cagr",
    )
    assert seen.get("opened") is True
    assert result.get("best_parameters") is not None
    assert engine._prep_cache is None


def test_optimization_session_helper_is_noop_for_engines_without_it():
    class Stub:
        pass
    with optimization_session(Stub()):
        pass
