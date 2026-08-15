"""인터프리터 LLM 원출력 수집 — 형식 준수 baseline 측정 + LoRA 학습 데이터 원천.

왜 필요한가
-----------
인터프리터의 원출력(`InterpreterResult.raw_output`)은 런타임에만 존재하고 **어디에도
저장되지 않는다**. 저장 코드는 `strategy_conversation/shadow.py`에 있지만
`STRATEGY_INTERPRETER_MODE=shadow`일 때만 돌고, 현재는 `primary`다. 기존 QA 캐시
(`qa_complex_llm_parse.json`, `qa_unsupported_shadow.jsonl`)도 전부 **수리가 끝난 뒤**의
구조화 결과만 갖고 있다. 즉 "모델이 서식을 어떻게 깨뜨렸는가"의 증거가 0건이다.

이 하니스는 그 증거를 만든다. 기존 QA 입력 코퍼스를 인터프리터에 그대로 흘려
원출력을 JSONL로 적재하고, 각 출력이 **어느 수준의 수리를 필요로 했는지** 분류한다.

왜 `repair_attempts`만으로는 부족한가
--------------------------------------
`extract_json_object`(output_repair.py)가 코드펜스·꼬리 토큰·연산자 붕괴·닫는 괄호
누락을 **조용히** 고쳐서 넘긴다. 그래서 재생성 횟수(`repair_attempts`)만 세면 형식
실패의 대부분이 0으로 보인다. 지금 파이프라인이 멀쩡해 보이는 이유가 185줄짜리 수리
코드라면, 그 개입률이 곧 LoRA로 없앨 수 있는 몫이다 — 그래서 4단계로 나눈다.

  L0_clean    원출력이 그대로 StrategyIntent 검증 통과 (수리 불필요)
  L1_repaired extract_json_object 수리를 거쳐야 통과  ← 조용히 메워지던 몫
  L2_regen    수리로도 안 되어 재생성 요청까지 가서 통과
  L3_fail     재생성 후에도 실패 (사용자에게 해석 실패로 나감)

실행
----
    python scripts/qa_interpreter_raw_capture.py             # 미수집분만 이어서
    python scripts/qa_interpreter_raw_capture.py --limit 20  # 소량 시험
    python scripts/qa_interpreter_raw_capture.py --refresh   # 전체 재수집
    python scripts/qa_interpreter_raw_capture.py --report    # 수집 없이 집계만

사전 조건: 로컬 Ollama(`ollama serve`)에 인터프리터 모델이 떠 있어야 한다.
결과는 scripts/.cache/qa_interpreter_raw_capture.jsonl 에 누적된다(모델·프롬프트
버전이 레코드에 박히므로 버전이 바뀌면 자동으로 재수집 대상이 된다).

수집 범위는 **초기 생성(draft 없음) 경로**로 한정한다. 수정 모드(patches 출력)는
서식이 다르고 초안 상태에 의존하므로 별도 수집이 필요하다.
"""

from __future__ import annotations

# 데드락/세그폴트 가드 — 다른 QA 하니스와 동일(반드시 import 전에).
import os

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("POLARS_MAX_THREADS", "1")

import argparse  # noqa: E402
import ast  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from collections import Counter  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any, Optional  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(SCRIPTS))

# 모델 슬롯은 .env에 있다. 서버를 거치지 않는 스크립트는 직접 로드해야 한다 —
# 안 하면 StrategyInterpreter가 "모델 슬롯 미설정"으로 즉시 실패한다(의도된 가드).
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from pydantic import ValidationError  # noqa: E402

from engine.nl_parser import _trim_model_trailing_tokens  # noqa: E402
from strategy_conversation import config  # noqa: E402
from strategy_conversation.interpreter.llm_strategy_interpreter import (  # noqa: E402
    StrategyInterpreter,
)
from strategy_conversation.interpreter.models import StrategyIntent  # noqa: E402
from strategy_conversation.interpreter.output_repair import (  # noqa: E402
    _repair_operator_token_drift,
    build_repair_prompt,
    extract_json_object,
)
from strategy_conversation.interpreter.prompts import (  # noqa: E402
    PROMPT_VERSION,
    build_user_prompt,
)

OUT = SCRIPTS / ".cache" / "qa_interpreter_raw_capture.jsonl"

LEVELS = ["L0_clean", "L1_repaired", "L2_regen", "L3_fail"]


# ── 입력 코퍼스 ──────────────────────────────────────────────────────────────
def _assign_targets(node: ast.stmt) -> list[ast.expr]:
    if isinstance(node, ast.Assign):
        return node.targets
    if isinstance(node, ast.AnnAssign):
        return [node.target]
    return []


def _cases(path: Path, name: str, keys: tuple[str, ...]) -> list[dict]:
    """케이스 리스트에서 **지정한 키의 값만** 꺼낸다(모듈 임포트 없이).

    QA 하니스는 임포트만으로 무거운 의존성을 끌어오므로(엔진·urllib 등) AST로 읽는다.
    `expect` 같은 기대값 필드에는 수식·상수 참조가 섞여 있는데 여기서는 쓰지 않는다 —
    필요한 키만 풀어서 그런 노드에 걸려 넘어지지 않게 한다. 발화 자체가 상수 참조인
    경우가 있어(`qa_redteam_validation.SETUP`) 최상위 문자열 상수는 미리 모은다.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))

    env: dict[str, str] = {}
    for node in tree.body:
        for tgt in _assign_targets(node):
            value = getattr(node, "value", None)
            if isinstance(tgt, ast.Name) and isinstance(value, ast.Constant) \
                    and isinstance(value.value, str):
                env[tgt.id] = value.value

    def resolve(node: ast.expr) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, (ast.List, ast.Tuple)):
            return [resolve(e) for e in node.elts]
        if isinstance(node, ast.Name):
            return env[node.id]
        raise ValueError(f"unsupported node {type(node).__name__}")

    target: Optional[ast.expr] = None
    for node in tree.body:
        for tgt in _assign_targets(node):
            if isinstance(tgt, ast.Name) and tgt.id == name:
                target = getattr(node, "value", None)
    if not isinstance(target, (ast.List, ast.Tuple)):
        raise KeyError(f"{name} not found (or not a list) in {path.name}")

    out: list[dict] = []
    for element in target.elts:
        if not isinstance(element, ast.Dict):
            continue
        case: dict[str, Any] = {}
        for key_node, val_node in zip(element.keys, element.values):
            if not isinstance(key_node, ast.Constant) or key_node.value not in keys:
                continue
            try:
                case[key_node.value] = resolve(val_node)
            except (ValueError, KeyError):
                pass  # 이 키는 리터럴로 풀리지 않는다 — 해당 케이스만 건너뛴다
        out.append(case)
    return out


def load_corpus() -> list[dict]:
    """기존 QA 입력을 한 자리에 모은다(중복 발화는 첫 출처만 남긴다)."""
    items: list[dict] = []

    complex_cases = _cases(SCRIPTS / "qa_complex_llm_parse.py", "CASES", ("prompt",))
    for i, case in enumerate(complex_cases):
        if case.get("prompt"):
            items.append({"source": "complex", "id": f"complex-{i + 1}",
                          "user_input": case["prompt"]})

    # 레드팀은 멀티턴이지만 첫 턴만 쓴다 — 2턴 이후는 수정 모드(draft 필요)라
    # 출력 서식 자체가 다르다(patches). 수집 범위 밖.
    for case in _cases(SCRIPTS / "qa_redteam_validation.py", "CASES", ("id", "turns")):
        turns = case.get("turns") or []
        if turns and isinstance(turns[0], str):
            items.append({"source": "redteam", "id": case.get("id", "?"),
                          "user_input": turns[0]})

    from qa_template_detect import load_templates  # 최상위 임포트가 stdlib뿐이라 안전

    for tpl in load_templates():
        items.append({"source": "template", "id": tpl.title, "user_input": tpl.prompt})

    seen: set[str] = set()
    unique: list[dict] = []
    for item in items:
        text = item["user_input"].strip()
        if not text or text in seen:
            continue
        seen.add(text)
        item["user_input"] = text
        unique.append(item)
    return unique


# ── 형식 진단 ────────────────────────────────────────────────────────────────
def repair_marks(raw: str) -> list[str]:
    """원출력이 **어떤 수리를 필요로 했는지** 표시한다(진단 전용 — 동작을 바꾸지 않는다).

    호출 전제: 원출력이 그대로는 검증을 통과하지 못한 경우에만 부른다. 수리 단계의
    텍스트 차이만 보면 안 되기 때문이다 — `_repair_operator_token_drift`는 정상
    JSON의 공백까지 정규화하므로(`"operator": ">=", ` → `"operator":">=",`) 차이가
    나도 수리가 필요했다는 뜻이 아니다. 실측에서 L0_clean 5건 전부에 오탐으로
    떴다. 그래서 판정 기준은 텍스트 차이가 아니라 **그 단계를 거쳐야 파싱이
    되는가**로 둔다.
    """
    marks: list[str] = []

    # JSON 문법 자체는 맞는데 스키마가 틀린 경우 — 형식 붕괴가 아니라 내용 오류다.
    try:
        json.loads(raw)
        return ["valid_json_bad_schema"]
    except (ValueError, json.JSONDecodeError):
        pass

    trimmed = _trim_model_trailing_tokens(raw)
    if trimmed != raw and _parses(trimmed):
        marks.append("trailing_tokens")

    text = trimmed.strip()
    if text.startswith("```"):
        marks.append("code_fence")

    drifted = _repair_operator_token_drift(text)
    if drifted != text and not _parses(text) and _parses(drifted):
        marks.append("operator_drift")

    try:
        extracted = extract_json_object(raw)
    except ValueError:
        marks.append("no_json_object")
        return marks

    # 수리기가 없던 괄호를 **삽입**했다면 추출본은 원문의 부분문자열이 아니다.
    # 부분문자열이면서 원문과 다르다면 JSON 앞뒤에 설명 산문이 붙은 것이다.
    if extracted not in drifted:
        marks.append("unbalanced_close")
    elif extracted != drifted and "code_fence" not in marks:
        marks.append("prose_wrap")  # 코드펜스는 이미 별도로 셌다 — 중복 표시하지 않는다

    return marks


def _parses(text: str) -> bool:
    try:
        json.loads(text)
        return True
    except (ValueError, json.JSONDecodeError):
        return False


def _validate(text: str) -> Optional[str]:
    """StrategyIntent 검증. 통과하면 None, 실패하면 오류 문자열."""
    try:
        StrategyIntent.model_validate_json(text)
        return None
    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
        return f"{type(exc).__name__}: {str(exc)[:400]}"


# ── 수집 ─────────────────────────────────────────────────────────────────────
def capture_one(interp: StrategyInterpreter, user_input: str) -> dict:
    """한 발화에 대해 원출력을 받고 수리 수준을 판정한다(운영 복구 루프를 그대로 모사)."""
    started = time.perf_counter()
    raw = interp._chat(interp._system_prompt, build_user_prompt(user_input))

    record: dict[str, Any] = {
        "raw_output": raw,
        "repair_marks": [],
        "repair_attempts": 0,
        "regen_raw_outputs": [],
    }

    # L0 — 원출력 그대로 통과? (통과했으면 수리 진단은 의미가 없다)
    if _validate(raw) is None:
        record.update(level="L0_clean", final_ok=True, error=None)
        record["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
        return record

    record["repair_marks"] = repair_marks(raw)

    # L1 — 결정론 수리를 거치면 통과?
    error: Optional[str]
    try:
        error = _validate(extract_json_object(raw))
    except ValueError as exc:
        error = f"ValueError: {exc}"
    if error is None:
        record.update(level="L1_repaired", final_ok=True, error=None)
        record["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
        return record

    # L2/L3 — 재생성 요청(운영과 동일하게 MAX_REPAIR_ATTEMPTS까지)
    current = raw
    attempts = 0
    while attempts < config.MAX_REPAIR_ATTEMPTS:
        attempts += 1
        regen = interp._chat(
            interp._system_prompt,
            build_repair_prompt(user_input, current, error or ""),
        )
        record["regen_raw_outputs"].append(regen)
        current = regen
        try:
            error = _validate(extract_json_object(regen))
        except ValueError as exc:
            error = f"ValueError: {exc}"
        if error is None:
            break

    record["repair_attempts"] = attempts
    record.update(
        level="L2_regen" if error is None else "L3_fail",
        final_ok=error is None,
        error=error,
    )
    record["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
    return record


def load_existing() -> list[dict]:
    if not OUT.exists():
        return []
    rows = []
    for line in OUT.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def run(limit: Optional[int], refresh: bool) -> list[dict]:
    corpus = load_corpus()
    existing = [] if refresh else load_existing()
    if refresh and OUT.exists():
        OUT.unlink()

    interp = StrategyInterpreter()
    # 모델·프롬프트 버전이 다른 기록은 다른 실험이다 — 이어받지 않는다.
    done = {
        r["user_input"]
        for r in existing
        if r.get("model") == interp.model_name and r.get("prompt_version") == PROMPT_VERSION
    }
    pending = [c for c in corpus if c["user_input"] not in done]
    if limit is not None:
        pending = pending[:limit]

    print(f"코퍼스 {len(corpus)}건 · 기수집 {len(done)}건 · 이번 수집 {len(pending)}건")
    print(f"모델 {interp.model_name} · 프롬프트 v{PROMPT_VERSION}\n", flush=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    collected = list(existing)
    with open(OUT, "a", encoding="utf-8") as f:
        for i, case in enumerate(pending, 1):
            try:
                result = capture_one(interp, case["user_input"])
            except Exception as exc:  # noqa: BLE001 — 한 건 실패가 수집 전체를 끝내면 안 된다
                result = {
                    "raw_output": "", "repair_marks": [], "repair_attempts": 0,
                    "regen_raw_outputs": [], "level": "L3_fail", "final_ok": False,
                    "error": f"{type(exc).__name__}: {str(exc)[:400]}", "latency_ms": 0.0,
                }
            record = {
                **case,
                **result,
                "model": interp.model_name,
                "prompt_version": PROMPT_VERSION,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            f.flush()
            collected.append(record)
            marks = ",".join(record["repair_marks"]) or "-"
            print(f"[{i}/{len(pending)}] {record['level']:<11} {marks:<24} "
                  f"{record['latency_ms']:>7.0f}ms  {case['user_input'][:44]}", flush=True)
    return collected


# ── 집계 ─────────────────────────────────────────────────────────────────────
def report(rows: list[dict]) -> None:
    """모델·프롬프트 버전별로 나눠 집계한다.

    한 파일에 여러 모델의 기록이 쌓이므로(9B baseline vs 4B 비교) 합산하면 서로 다른
    실험이 한 수치로 뭉개진다.
    """
    if not rows:
        print("수집된 기록이 없습니다.")
        return

    groups: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        key = (row.get("model", "?"), row.get("prompt_version", "?"))
        groups.setdefault(key, []).append(row)

    for (model, version), group in sorted(groups.items()):
        _report_group(model, version, group)


def _report_group(model: str, version: str, rows: list[dict]) -> None:
    total = len(rows)
    levels = Counter(r["level"] for r in rows)

    print("\n" + "=" * 68)
    print(f"인터프리터 형식 준수 baseline — {total}건")
    print(f"모델 {model} · 프롬프트 v{version}")
    print("=" * 68)
    for level in LEVELS:
        n = levels.get(level, 0)
        print(f"  {level:<12} {n:>5}건  {n / total * 100:>5.1f}%")

    repaired = total - levels.get("L0_clean", 0)
    print(f"\n  수리 개입률(L1+L2+L3)  {repaired:>5}건  {repaired / total * 100:>5.1f}%"
          "   ← LoRA로 없앨 수 있는 상한")
    fails = levels.get("L3_fail", 0)
    print(f"  최종 실패율(L3)        {fails:>5}건  {fails / total * 100:>5.1f}%"
          "   ← 지금 사용자에게 나가는 해석 실패")

    marks = Counter(m for r in rows for m in r["repair_marks"])
    if marks:
        print("\n  발동한 수리 종류")
        for mark, n in marks.most_common():
            print(f"    {mark:<20} {n:>5}건")

    print("\n  출처별 수리 개입률")
    by_source: dict[str, list[dict]] = {}
    for r in rows:
        by_source.setdefault(r.get("source", "?"), []).append(r)
    for source, group in sorted(by_source.items()):
        dirty = sum(1 for r in group if r["level"] != "L0_clean")
        print(f"    {source:<12} {dirty:>4}/{len(group):<4} {dirty / len(group) * 100:>5.1f}%")

    lat = sorted(r["latency_ms"] for r in rows if r["latency_ms"])
    if lat:
        print(f"\n  지연 중앙값 {lat[len(lat) // 2]:.0f}ms · "
              f"p95 {lat[int(len(lat) * 0.95)]:.0f}ms")
    print(f"\n  원출력 코퍼스: {OUT.relative_to(ROOT)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, help="이번 실행에서 수집할 최대 건수")
    ap.add_argument("--refresh", action="store_true", help="기존 기록을 버리고 전체 재수집")
    ap.add_argument("--report", action="store_true", help="수집 없이 기존 기록만 집계")
    args = ap.parse_args()

    rows = load_existing() if args.report else run(args.limit, args.refresh)
    report(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
