#!/usr/bin/env python3
"""전략 해석 한 턴의 트레이스를 레이어별로 요약한다 — "어느 단계에서 틀어졌나"를 1분 안에.

    python .claude/skills/strategy-interpretation-fix/scripts/trace_turn.py --grep "분할 매수"
    python .claude/skills/strategy-interpretation-fix/scripts/trace_turn.py --last 3
    python .claude/skills/strategy-interpretation-fix/scripts/trace_turn.py --trace-id f5c65fd654c0 --full

읽는 곳: backend/logs/agent_traces/<날짜>.jsonl (로컬 백엔드가 남긴 것만 — 운영 트레이스는 박스에 있다).
`--grep`은 트레이스 안의 문자열 검색(사람이 고른 문구로 턴 찾기)이며 사용자 원문의 의미를 판정하지 않는다.
'진단 힌트'는 LLM 출력·파이프라인 산출물(토큰 수·오류·모델명)만 보고 낸다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
TRACE_DIR = ROOT / "backend" / "logs" / "agent_traces"
STRATEGY_ROOT = "NullStock Strategy Agent"
BARE_LABEL_TOKENS = 40  # 빈 UNSUPPORTED_REQUEST 라벨은 ~11토큰으로 끝난다


def _load(dates: list[str]) -> list[dict]:
    rows = []
    for d in dates:
        path = TRACE_DIR / f"{d}.jsonl"
        if not path.exists():
            continue
        for line in path.open(encoding="utf-8"):
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _walk(span: dict, depth: int = 0):
    yield span, depth
    for child in span.get("children") or []:
        yield from _walk(child, depth + 1)


def _short(value, limit: int = 400) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + f"…(+{len(text) - limit})"


def _non_null_leaves(obj, prefix: str = ""):
    """전략 JSON에서 채워진 칸만 경로=값으로 — 값이 어느 칸에 들어갔는지 보는 용도."""
    if isinstance(obj, dict):
        for key, val in obj.items():
            yield from _non_null_leaves(val, f"{prefix}.{key}" if prefix else key)
    elif isinstance(obj, list):
        if not obj:
            return
        if all(not isinstance(v, (dict, list)) for v in obj):
            yield prefix, obj
            return
        for i, val in enumerate(obj):
            yield from _non_null_leaves(val, f"{prefix}[{i}]")
    elif obj not in (None, False, "", 0) or (obj == 0 and prefix.endswith(("value", "pct", "percent"))):
        yield prefix, obj


def _print_strategy(label: str, strategy, indent: str = "  ") -> None:
    if not isinstance(strategy, dict):
        return
    print(f"{indent}{label}:")
    for path, val in _non_null_leaves(strategy):
        if path.endswith(("entry_logic",)) and val == "AND":
            continue
        print(f"{indent}  {path} = {_short(val, 160)}")


def _llm_response_json(span: dict):
    resp = (span.get("outputs") or {}).get("response")
    if not isinstance(resp, str):
        return None
    start, end = resp.find("{"), resp.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(resp[start:end + 1])
    except json.JSONDecodeError:
        return None


def summarize(row: dict, full: bool) -> None:
    root = row["span"]
    hints: list[str] = []
    print("=" * 100)
    print(f"[{row['ts']}] trace_id={row['trace_id']}  root={row['root']}  total={row.get('total_ms')}ms")
    inputs = root.get("inputs") or {}
    md = root.get("metadata") or {}
    out = root.get("outputs") or {}
    for key in ("user_input", "query", "pending_question", "pending_ask"):
        if inputs.get(key):
            print(f"  {key}: {_short(inputs[key], 600)}")
    if md:
        print(f"  turn_kind={md.get('turn_kind')} cache_hit={md.get('cache_hit')} version={md.get('version')} "
              f"llm_calls={md.get('llm_calls')} retry={md.get('retry_count')} failure={md.get('failure_count')}")
        if md.get("cache_hit"):
            hints.append("cache_hit=True — 이 턴은 파스 캐시 재사용이다. 재표본으로 세지 말 것(model 접미사·키 비틀기).")
    if out:
        print(f"  ▶ outcome={out.get('outcome')}  symbol_count={out.get('symbol_count')}")
        if out.get("clarification_question"):
            print(f"  ▶ 되묻기: {_short(out['clarification_question'], 300)}")
        for notice in out.get("notices") or []:
            print(f"  ▶ 안내: {_short(notice, 300)}")

    models = set()
    for span, depth in _walk(root):
        name = span.get("name", "")
        smd = span.get("metadata") or {}
        sout = span.get("outputs") or {}
        if span is root:
            continue
        indent = "  " * depth
        if name.startswith("LLM"):
            models.add((smd.get("model"), smd.get("provider")))
            print(f"{indent}· {name}  provider={smd.get('provider')} in={smd.get('input_tokens')} "
                  f"out={smd.get('output_tokens')} max={smd.get('max_tokens')} {span.get('duration_ms')}ms")
            if full:
                print(f"{indent}  response: {_short(sout.get('response'), 4000)}")
            continue
        err = span.get("error") or smd.get("error")
        print(f"{indent}- {name}  {span.get('duration_ms')}ms" + (f"  ❌ {smd.get('error_kind') or ''}" if err else ""))
        if err:
            print(f"{indent}  error: {_short(err, 800)}")
        if name.startswith("Interpreter"):
            print(f"{indent}  prompt_version={smd.get('prompt_version')} mode={smd.get('mode')} "
                  f"retry={smd.get('retry_count')} label={sout.get('intent')}")
            llm_children = [c for c in span.get("children") or [] if c.get("name", "").startswith("LLM")]
            for c in llm_children:
                toks = (c.get("metadata") or {}).get("output_tokens")
                if toks is not None and toks < BARE_LABEL_TOKENS:
                    hints.append(f"인터프리터 LLM 출력 {toks}토큰 — 빈 라벨/붕괴 출력 의심(output_repair 재생성 계열).")
                if (c.get("metadata") or {}).get("output_tokens") == (c.get("metadata") or {}).get("max_tokens"):
                    hints.append("인터프리터 출력이 max_tokens에 닿았다 — 잘린 JSON 의심.")
            if len(llm_children) > 1:
                hints.append(f"인터프리터 LLM 호출 {len(llm_children)}회 — 수리(재생성) 턴 발생. 목록 필드 소실 여부를 원출력과 대조.")
                first = _llm_response_json(llm_children[0])
                if isinstance(first, dict):
                    uf = first.get("unsupported_features")
                    if uf:
                        print(f"{indent}  1차 원출력 unsupported_features: {_short(uf, 400)}")
            _print_strategy("해석 결과(채워진 칸)", sout.get("strategy"), indent + "  ")
        elif name == "Tool · validate_intent":
            report = (sout.get("observation") or {}).get("report") or {}
            print(f"{indent}  status={report.get('status')} valid={report.get('is_valid')}")
            for key in ("errors", "missing_fields", "unsupported_features", "preparing_features", "conflicted_slots"):
                if report.get(key):
                    print(f"{indent}  {key}: {_short(report[key], 500)}")
            for q in report.get("clarification_questions") or []:
                print(f"{indent}  질문[{q.get('field')}]: {_short(q.get('question'), 200)} (추천={q.get('recommended_value')})")
        elif name == "Tool · compile_strategy":
            if err:
                hints.append("조립(compile) 예외 — 인터프리터 모델과 ParsedStrategy 제약 범위 불일치 의심. "
                             "요청 전체가 '해석하지 못했어요'로 떨어진다.")
        elif name.startswith(("Planner", "Ask", "Tool · ", "Action")) and not full:
            keys = {k: sout.get(k) for k in ("outcome", "question", "topic", "gate", "bound", "lane") if sout.get(k) is not None}
            if keys:
                print(f"{indent}  {_short(keys, 300)}")
        elif sout:
            print(f"{indent}  out: {_short(sout, 600 if not full else 4000)}")
            if span.get("inputs") and full:
                print(f"{indent}  in:  {_short(span['inputs'], 1500)}")

    if models:
        print(f"  레인 모델: {sorted(str(m) for m in models)}")
        if any(m and "120b" not in str(m).lower() for m, _ in models) or any(p is None for _, p in models):
            hints.append("120B(OpenRouter) 밖의 모델/provider=None 호출이 있다 — 9B 폴백·한도 소진 레인인지 먼저 확인.")
    if row["root"] == STRATEGY_ROOT and not any(n.get("name", "").startswith("Interpreter") for n, _ in _walk(root)):
        hints.append("Interpreter span 없음 — 캐시 적중이거나 되묻기 답 전용 판정/프론트 게이트가 처리한 턴.")
    if hints:
        print("  진단 힌트:")
        for h in dict.fromkeys(hints):
            print(f"    ! {h}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--grep", help="트레이스 JSON 안에서 찾을 문구(사용자 문장 일부 등)")
    ap.add_argument("--trace-id")
    ap.add_argument("--date", action="append", help="YYYY-MM-DD (여러 번 가능, 기본=오늘·어제)")
    ap.add_argument("--last", type=int, default=0, help="조건에 맞는 마지막 N개만")
    ap.add_argument("--all-roots", action="store_true", help="전략 에이전트 말고 분류기 등 다른 루트도")
    ap.add_argument("--full", action="store_true", help="LLM 원출력·보조 판정 입력까지 출력")
    args = ap.parse_args()

    today = dt.date.today()
    dates = args.date or [str(today - dt.timedelta(days=1)), str(today)]
    rows = _load(dates)
    if args.trace_id:
        rows = [r for r in rows if r["trace_id"] == args.trace_id]
    else:
        if not args.all_roots and not args.grep:
            rows = [r for r in rows if r["root"] == STRATEGY_ROOT]
        if args.grep:
            rows = [r for r in rows if args.grep in json.dumps(r, ensure_ascii=False)]
    if args.last:
        rows = rows[-args.last:]
    if not rows:
        print(f"일치하는 트레이스 없음 (dir={TRACE_DIR}, dates={dates})", file=sys.stderr)
        return 1
    for row in rows:
        summarize(row, args.full)
    return 0


if __name__ == "__main__":
    sys.exit(main())
