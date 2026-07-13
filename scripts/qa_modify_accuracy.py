"""수정(modify) 경로 정확도 실측 하니스.

목적
----
modify_examples.json / modify_knowledge.json 은 **수정 요청이 결정론 fast-path
(_modify_rule_based)를 못 뚫고 LLM(_modify_ollama → build_dynamic_modify_prompt)까지
내려갔을 때만** 쓰인다. 따라서 "이 두 파일을 개선하면 오류가 줄어드는가"의 답은:
  (1) 수정 요청이 애초에 얼마나 자주 LLM 경로까지 가는가 (라우팅 분포)
  (2) LLM 경로의 정확도가 얼마인가 (=두 파일이 영향을 주는 슬라이스)
를 실측해야 나온다.

각 케이스마다:
  - route  = RULE(fast-path가 처리) / LLM(위임)  ← _modify_rule_based로 판정
  - correct = 기대한 변경 필드가 모두 맞았는가
  - overreach = 요청하지 않은 필드를 건드렸는가 (diff-contract 위반)

실행:
    cd backend && python ../scripts/qa_modify_accuracy.py
사전 조건: 로컬 Ollama(qwen3:8b) 가동.
"""
from __future__ import annotations

import os
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("POLARS_MAX_THREADS", "1")

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from engine.nl_parser import NLStrategyParser, _modify_rule_based, ParsedStrategy  # noqa: E402


def base() -> dict:
    return ParsedStrategy(
        description="테스트 전략",
        universe=["KOSPI200"],
        fundamental_filters=[],
        entry_signals=[],
        exit_signals=[],
        max_positions=10,
        hold_period_days=None,
        rebalancing_period="none",
        stop_loss_pct=None,
        take_profit_pct=None,
        trailing_stop_pct=None,
        max_mdd_limit_pct=None,
        backtest_period="5y",
        initial_capital=10000000.0,
        execution_timing="next_open",
        fee_rate=0.015,
        slippage_rate=0.05,
    ).model_dump()


# (req, prev_overrides, expect)  — expect: 특수키로 필드 유형별 검증
#   scalar/str/enum/None → 직접 비교
#   "universe" → 집합 비교
#   "filter:metric" → 해당 metric 필터가 (op,value)로 존재
#   "entry:indicator" / "exit:indicator" → 해당 indicator 신호가 존재
CASES: list[tuple[str, dict, dict]] = [
    # ── A. 단순 필드 (fast-path 기대) ─────────────────────────────
    ("손절 -5%로 바꿔줘", {}, {"stop_loss_pct": 5.0}),
    ("익절 20%로 설정해줘", {}, {"take_profit_pct": 20.0}),
    ("트레일링 스탑 10%로 해줘", {}, {"trailing_stop_pct": 10.0}),
    ("종목 15개로 늘려줘", {}, {"max_positions": 15}),
    ("초기자금 1억으로 바꿔줘", {}, {"initial_capital": 100000000.0}),
    ("코스닥으로 바꿔줘", {}, {"universe": ["KOSDAQ"]}),
    ("전체 시장으로 바꿔줘", {}, {"universe": ["KOSPI", "KOSDAQ"]}),
    ("6개월 보유로 설정해", {}, {"hold_period_days": 126}),
    ("분기마다 리밸런싱하게 바꿔", {}, {"rebalancing_period": "quarterly"}),
    ("백테스트 3년으로 바꿔줘", {}, {"backtest_period": "3y"}),
    ("PBR 1 이하로 바꿔줘", {}, {"filter:pbr": ("<=", 1.0)}),
    ("최대 낙폭 20%로 제한해줘", {}, {"max_mdd_limit_pct": 20.0}),
    ("손절 5% 익절 20%로 같이 설정", {}, {"stop_loss_pct": 5.0, "take_profit_pct": 20.0}),
    ("ROE 15% 이상으로 바꿔줘", {}, {"filter:roe_or_gpa": (">=", 15.0)}),
    ("종목 수는 8개로 줄여", {}, {"max_positions": 8}),

    # ── B. 복합/모호 (LLM 경로 기대 — 두 파일이 영향) ──────────────
    ("반도체 종목만 남기고 테스트해줘", {}, {"sector": "반도체"}),
    ("2차전지 관련주로 바꿔줘", {}, {"sector": "이차전지"}),
    ("15% 선절 30% 익절로 해줘", {}, {"stop_loss_pct": 15.0, "take_profit_pct": 30.0}),  # 오타 선절→손절
    ("익졀 25%로 바꿔줘", {}, {"take_profit_pct": 25.0}),  # 오타 익졀→익절
    ("최고가에서 8% 밀리면 청산하게", {}, {"trailing_stop_pct": 8.0}),
    ("골든크로스 나면 사도록 추가해줘", {}, {"entry:ma_crossover": True}),
    ("RSI 30 이하에서 매수하게 바꿔줘", {}, {"entry:rsi": True}),
    ("손절만 빼줘", {"stop_loss_pct": 8.0}, {"stop_loss_pct": None}),  # 삭제 의도
    ("리밸런싱은 끄고 익절만 25%로", {"rebalancing_period": "quarterly"},
     {"rebalancing_period": "none", "take_profit_pct": 25.0}),
    ("종목 수는 그대로 두고 익절만 30%로 해줘", {"max_positions": 12},
     {"take_profit_pct": 30.0, "max_positions": 12}),  # diff-contract: max_positions 유지
    ("데드크로스에 팔게 청산조건 추가", {}, {"exit:ma_crossover": True}),
    ("변동성 큰 종목 위주로 바꿔줘", {}, {}),  # 정성 표현 — 확실한 정답 없음(되묻기/무변경 허용)
]


def approx(a, b, tol=1e-6):
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return a == b


def check_field(key, exp, result: ParsedStrategy) -> tuple[bool, str]:
    if key == "universe":
        got = result.universe or []
        return (set(got) == set(exp), f"universe={got}")
    if key.startswith("filter:"):
        metric = key.split(":", 1)[1]
        op, val = exp
        for f in (result.fundamental_filters or []):
            fm = f.metric if hasattr(f, "metric") else f.get("metric")
            fo = f.operator if hasattr(f, "operator") else f.get("operator")
            fv = f.value if hasattr(f, "value") else f.get("value")
            if fm == metric and fo == op and approx(fv, val):
                return (True, f"{metric}{op}{val} ✓")
        return (False, f"filters={[getattr(f,'metric',None) for f in (result.fundamental_filters or [])]}")
    if key.startswith("entry:") or key.startswith("exit:"):
        ind = key.split(":", 1)[1]
        sigs = result.entry_signals if key.startswith("entry:") else result.exit_signals
        inds = [getattr(s, "indicator", None) for s in (sigs or [])]
        return (ind in inds, f"{key.split(':')[0]}_signals={inds}")
    # scalar / str / enum / None
    got = getattr(result, key)
    if exp is None:
        return (got is None, f"{key}={got}")
    return (approx(got, exp), f"{key}={got}")


# diff-contract 과다변경 감시 대상(스칼라/enum/유니버스)
TRACKED = ["universe", "sector", "max_positions", "hold_period_days", "rebalancing_period",
           "stop_loss_pct", "take_profit_pct", "trailing_stop_pct", "max_mdd_limit_pct",
           "backtest_period", "initial_capital"]


def overreach(prev: dict, result: ParsedStrategy, expect: dict) -> list[str]:
    touched_ok = set()
    for k in expect:
        base_k = k.split(":", 1)[0] if ":" in k else k
        touched_ok.add("fundamental_filters" if base_k == "filter" else
                       "entry_signals" if base_k == "entry" else
                       "exit_signals" if base_k == "exit" else base_k)
    bad = []
    for f in TRACKED:
        if f in touched_ok:
            continue
        before, after = prev.get(f), getattr(result, f)
        if f == "universe":
            if set(before or []) != set(after or []):
                bad.append(f"{f}:{before}->{after}")
        elif before != after:
            bad.append(f"{f}:{before}->{after}")
    return bad


def main():
    parser = NLStrategyParser(backend="ollama")
    rows = []
    for req, ov, expect in CASES:
        prev = base()
        prev.update(ov)
        route = "RULE" if _modify_rule_based(req, prev) is not None else "LLM"
        try:
            result = parser.parse_modification(req, dict(prev))
        except Exception as e:  # noqa: BLE001
            rows.append((req, route, False, [f"EXC:{e}"], [], expect))
            continue
        details = []
        ok = True
        for k, v in expect.items():
            passed, msg = check_field(k, v, result)
            details.append(("✓" if passed else "✗") + " " + msg)
            ok = ok and passed
        over = overreach(prev, result, expect)
        rows.append((req, route, ok, details, over, expect))

    # ── 집계 ──
    def acc(subset):
        graded = [r for r in subset if r[5]]  # expect 비어있으면 정답 없음 → 등급 제외
        if not graded:
            return (0, 0)
        return (sum(1 for r in graded if r[2]), len(graded))

    all_rows = rows
    rule_rows = [r for r in rows if r[1] == "RULE"]
    llm_rows = [r for r in rows if r[1] == "LLM"]

    print("=" * 70)
    print("수정(modify) 경로 정확도 실측")
    print("=" * 70)
    print(f"총 케이스: {len(all_rows)}  |  RULE(fast-path): {len(rule_rows)}  |  LLM 위임: {len(llm_rows)}")
    oc, ot = acc(all_rows); rc, rt = acc(rule_rows); lc, lt = acc(llm_rows)
    print(f"\n정확도(등급 케이스 기준):")
    print(f"  전체     : {oc}/{ot}  ({100*oc/ot if ot else 0:.0f}%)")
    print(f"  RULE 경로: {rc}/{rt}  ({100*rc/rt if rt else 0:.0f}%)")
    print(f"  LLM 경로 : {lc}/{lt}  ({100*lc/lt if lt else 0:.0f}%)   ← 두 파일이 영향을 주는 슬라이스")

    overreach_rows = [r for r in rows if r[4]]
    print(f"\ndiff-contract 과다변경(요청 안 한 필드 건드림): {len(overreach_rows)}건")

    print("\n" + "-" * 70)
    print("실패/과다변경 상세")
    print("-" * 70)
    for req, route, ok, details, over, expect in rows:
        graded = bool(expect)
        if graded and ok and not over:
            continue
        tag = "PASS" if (ok or not graded) else "FAIL"
        print(f"[{route:4}] [{tag}] {req}")
        for d in details:
            if d.startswith("✗"):
                print(f"        {d}")
        if over:
            print(f"        ⚠ overreach: {over}")


if __name__ == "__main__":
    main()
