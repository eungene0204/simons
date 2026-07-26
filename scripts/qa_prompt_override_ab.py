"""결정적 프롬프트 보정 ON/OFF A/B — 자연어 해석 계약 마이그레이션 계측기.

`STRATEGY_PROMPT_OVERRIDE_MODE`(on/off)를 뒤집어가며 primary(LLM-first) 경로를
qa_complex_llm_parse.py의 103케이스에 통과시키고, 원문 정규식 보정을 제거했을 때
무엇이 깨지는지 필드 단위로 센다. docs/nl_interpretation_contract.md § 11의
2+1b 단계(=보정 제거)가 언제 안전한지 판정하는 게이트다.

    cd backend && python ../scripts/qa_prompt_override_ab.py [--limit N] [--out report.json]

사전 조건: 로컬 Ollama(`ollama serve`) + .env의 NL_OLLAMA_MODEL.
LLM 응답은 프롬프트 단위로 캐시하므로 ON/OFF가 같은 응답을 공유한다(측정 시간 절반).
"""
from __future__ import annotations

import os

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("POLARS_MAX_THREADS", "1")
os.environ["STRATEGY_INTERPRETER_MODE"] = "primary"

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from qa_complex_llm_parse import CASES, check_case  # noqa: E402

from strategy_conversation import config, primary  # noqa: E402
from strategy_conversation.interpreter.llm_strategy_interpreter import (  # noqa: E402
    StrategyInterpreter,
)

# ON/OFF는 컴파일 이후 단계만 다르므로 LLM 응답은 동일하다(temperature 0).
# 같은 프롬프트를 두 번 부르지 않도록 chat 레이어에서 캐시한다 — 측정 시간 절반.
_CHAT_CACHE: dict[tuple[str, str], str] = {}
_orig_init = StrategyInterpreter.__init__


def _cached_init(self, *a, **kw):
    _orig_init(self, *a, **kw)
    inner = self._chat

    def chat(system_prompt: str, user_message: str) -> str:
        key = (system_prompt, user_message)
        if key not in _CHAT_CACHE:
            _CHAT_CACHE[key] = inner(system_prompt, user_message)
        return _CHAT_CACHE[key]

    self._chat = chat


StrategyInterpreter.__init__ = _cached_init

# 비교 대상 필드 — 기본값이 항상 같은 필드(description 등)는 제외한다.
FIELDS = [
    "universe", "sector", "target_symbols", "etf_theme",
    "fundamental_filters", "entry_signals", "exit_signals",
    "ranking_metric", "ranking_lookback_days",
    "max_positions", "hold_period_days", "rebalancing_period",
    "stop_loss_pct", "take_profit_pct", "trailing_stop_pct", "max_mdd_limit_pct",
    "backtest_period", "backtest_start_date", "backtest_end_date",
    "initial_capital", "fee_rate", "slippage_rate", "execution_timing",
]


def run(prompt: str, overrides: bool) -> dict | None:
    os.environ["STRATEGY_PROMPT_OVERRIDE_MODE"] = "on" if overrides else "off"
    assert config.prompt_overrides_enabled() is overrides
    try:
        result = primary.run_primary_parse(prompt)
    except Exception as exc:  # noqa: BLE001
        return {"__error__": repr(exc)[:200]}
    if result is None:
        return None
    return result["parsed"].model_dump()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default="ab_overrides.json")
    args = ap.parse_args()

    cases = CASES[: args.limit] if args.limit else CASES
    rows = []
    started = time.perf_counter()
    for i, case in enumerate(cases, 1):
        prompt = case["prompt"]
        on = run(prompt, True)
        off = run(prompt, False)
        row = {"i": i, "prompt": prompt}
        if on is None or off is None or "__error__" in (on or {}) or "__error__" in (off or {}):
            row["status"] = "unusable"
            row["on"] = on if on is None or "__error__" in on else "ok"
            row["off"] = off if off is None or "__error__" in off else "ok"
        else:
            diff = {f: [on.get(f), off.get(f)] for f in FIELDS if on.get(f) != off.get(f)}
            row["status"] = "same" if not diff else "diff"
            row["diff_fields"] = sorted(diff)
            row["diff"] = json.loads(json.dumps(diff, ensure_ascii=False, default=str))
            row["fail_on"] = check_case(on, case["expect"])
            row["fail_off"] = check_case(off, case["expect"])
        rows.append(row)
        print(f"[{i}/{len(cases)}] {row['status']:8} {row.get('diff_fields', '')} "
              f"| {prompt[:44]}", flush=True)

    Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    same = sum(r["status"] == "same" for r in rows)
    diff = sum(r["status"] == "diff" for r in rows)
    unusable = sum(r["status"] == "unusable" for r in rows)
    pass_on = sum(1 for r in rows if r.get("fail_on") == [])
    pass_off = sum(1 for r in rows if r.get("fail_off") == [])
    field_counts: dict[str, int] = {}
    for r in rows:
        for f in r.get("diff_fields", []):
            field_counts[f] = field_counts.get(f, 0) + 1
    print("\n=== 요약 ===")
    print(f"케이스 {len(rows)} | 동일 {same} | 상이 {diff} | 사용불가 {unusable}")
    print(f"기대 충족: ON {pass_on}/{len(rows)}  OFF {pass_off}/{len(rows)}")
    print(f"소요 {time.perf_counter() - started:.0f}s")
    print("\n필드별 차이 횟수(많은 순):")
    for f, c in sorted(field_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {c:3}  {f}")


if __name__ == "__main__":
    main()
