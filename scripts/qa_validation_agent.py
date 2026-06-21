"""검증(validation) agent QA 하니스.

components/strategy/StrategyExampleTabs.tsx 의 모든 백테스트 예시(EXAMPLES)를
백엔드 파서(/strategy/parse)에 흘려보낸 뒤, 그 결과를 실제 검증 엔드포인트
(/strategy/coach/sessions, _STRATEGY_AGENT_MODE="validation")에 보내 검증 agent의
판정({is_valid, issues})을 받아낸다.

의도:
- 예시 전략들은 "완성되어 백테스트 가능한" 큐레이션 전략이다.
- 따라서 검증 agent는 이들을 통과(is_valid=true)시켜야 한다.
- error severity 이슈가 뜨면 = 파서가 필수 필드를 누락했거나 검증이 오탐(false
  positive)이라는 신호 → 점검 대상.
- 손절/익절 미설정 경고(warning)는 예시 다수에서 정상적으로 기대되는 값이라
  별도로 집계만 한다.

사전 조건: 백엔드가 떠 있고(/model/status == ok) 검증 모드여야 한다.

실행:
    python scripts/qa_validation_agent.py [--out docs/validation_agent_qa_report.md] [--refresh]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import urllib.request
import urllib.error

# 같은 디렉터리의 템플릿 로더를 재사용한다.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qa_template_detect import BACKEND, RAW_CACHE, Template, load_templates  # noqa: E402

# 예시 전략에서 정상적으로 기대되는(점검 불필요) 경고 코드.
ACCEPTABLE_WARNINGS = {"MISSING_STOP_LOSS", "MISSING_TAKE_PROFIT"}

# 파서 백엔드. dev/배포 기본값은 ollama(qa_template_detect는 mlx를 하드코딩하지만
# 로컬 dev에는 mlx 파서가 로드돼 있지 않아 즉시 503이 난다).
PARSE_BACKEND = "ollama"


def parse_strategy(prompt: str) -> dict:
    body = json.dumps({"prompt": prompt, "backend": PARSE_BACKEND}).encode()
    req = urllib.request.Request(
        f"{BACKEND}/strategy/parse",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read())


def run_validation(prompt: str, parsed: dict) -> dict:
    """실제 검증 엔드포인트(coach/sessions, validation 모드)를 호출한다."""
    body = json.dumps({"user_prompt": prompt, "parsed_strategy": parsed}).encode()
    req = urllib.request.Request(
        f"{BACKEND}/strategy/coach/sessions",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        payload = json.loads(r.read())
    # validation 모드에서는 message 가 검증 JSON 문자열이다.
    return json.loads(payload["message"])


def run_validation_local(parsed: dict) -> dict:
    """검증을 인-프로세스로 평가한다(결정론적). 백엔드 이벤트 루프가 긴 파싱
    호출로 막혀 결정론적 검증마저 타임아웃 나는 문제를 우회한다. 백엔드 경로와
    동일하게 _validation_payload 기본값 보강을 먼저 적용한다."""
    backend_dir = str(Path(__file__).resolve().parent.parent / "backend")
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)
    from ai.strategy_validation_agent import StrategyValidationAgent
    from api.coach_routes import _validation_payload
    return StrategyValidationAgent().validate(_validation_payload(parsed))


def classify(result: dict) -> tuple[str, list[dict], list[dict]]:
    issues = result.get("issues", [])
    errors = [i for i in issues if i.get("severity") == "error"]
    warnings = [i for i in issues if i.get("severity") == "warning"]
    if errors:
        return "FAIL", errors, warnings
    unexpected = [w for w in warnings if w.get("code") not in ACCEPTABLE_WARNINGS]
    if unexpected:
        return "WARN", errors, warnings
    return "PASS", errors, warnings


def fmt_issues(issues: list[dict]) -> str:
    return ", ".join(f"`{i.get('code')}`({i.get('field')})" for i in issues) or "—"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    ap.add_argument("--refresh", action="store_true", help="캐시 무시하고 전부 재파싱")
    ap.add_argument("--local", action="store_true",
                    help="검증을 인-프로세스로 평가(백엔드 검증 엔드포인트 미호출). 파싱은 캐시만 사용")
    args = ap.parse_args()

    templates = load_templates()
    cache: dict[str, dict] = {}
    if RAW_CACHE.exists() and not args.refresh:
        cache = json.loads(RAW_CACHE.read_text())

    rows: list[dict[str, Any]] = []
    error_codes: Counter[str] = Counter()
    warn_codes: Counter[str] = Counter()
    status_count: Counter[str] = Counter()

    for i, tpl in enumerate(templates, 1):
        # ── 파싱 ──
        if tpl.prompt in cache:
            res = cache[tpl.prompt]
        elif args.local:
            rows.append({"i": i, "tpl": tpl, "status": "PARSE_ERROR", "detail": "캐시 없음(--local은 캐시만 사용)"})
            status_count["PARSE_ERROR"] += 1
            print(f"[{i}/{len(templates)}] {tpl.title} — 캐시 없음(--local)", file=sys.stderr)
            continue
        else:
            try:
                res = parse_strategy(tpl.prompt)
                cache[tpl.prompt] = res
                RAW_CACHE.write_text(json.dumps(cache, ensure_ascii=False))
            except Exception as e:  # noqa: BLE001
                rows.append({"i": i, "tpl": tpl, "status": "PARSE_ERROR", "detail": str(e)})
                status_count["PARSE_ERROR"] += 1
                print(f"[{i}/{len(templates)}] {tpl.title} — PARSE_ERROR: {e}", file=sys.stderr)
                continue
        parsed = res.get("parsed", {})

        # 파서가 되물음(clarification)을 반환하면 실제 프론트 흐름에서는 검증에
        # 도달하지 않는다(되물음 박스를 띄우고 멈춤). 이는 모호한 조건을 임의로
        # 추측하지 않으려는 의도된 동작이므로 CLARIFY로 분류한다.
        clarification = res.get("clarification_question")
        if clarification:
            rows.append({"i": i, "tpl": tpl, "status": "CLARIFY",
                         "clarification": clarification, "parsed": parsed})
            status_count["CLARIFY"] += 1
            print(f"[{i}/{len(templates)}] {tpl.title} — CLARIFY", file=sys.stderr)
            continue

        # ── 검증 ──
        try:
            result = run_validation_local(parsed) if args.local else run_validation(tpl.prompt, parsed)
        except Exception as e:  # noqa: BLE001
            rows.append({"i": i, "tpl": tpl, "status": "VALIDATE_ERROR", "detail": str(e), "parsed": parsed})
            status_count["VALIDATE_ERROR"] += 1
            print(f"[{i}/{len(templates)}] {tpl.title} — VALIDATE_ERROR: {e}", file=sys.stderr)
            continue

        status, errors, warnings = classify(result)
        for e in errors:
            error_codes[e.get("code")] += 1
        for w in warnings:
            warn_codes[w.get("code")] += 1
        status_count[status] += 1
        rows.append({
            "i": i, "tpl": tpl, "status": status, "errors": errors,
            "warnings": warnings, "parsed": parsed, "is_valid": result.get("is_valid"),
        })
        print(f"[{i}/{len(templates)}] {tpl.title} — {status}", file=sys.stderr)

    # ── 리포트 ──
    L: list[str] = []
    L.append("# 검증(Validation) Agent QA 리포트\n")
    L.append(f"- 대상 예시: **{len(templates)}개**")
    L.append(f"- PASS(통과): **{status_count['PASS']}** · "
             f"CLARIFY(파서 되물음=의도됨): **{status_count.get('CLARIFY', 0)}** · "
             f"WARN(예상 밖 경고): **{status_count['WARN']}** · "
             f"FAIL(에러=차단): **{status_count['FAIL']}**")
    if status_count.get("PARSE_ERROR") or status_count.get("VALIDATE_ERROR"):
        L.append(f"- 파싱 실패: {status_count.get('PARSE_ERROR', 0)} · "
                 f"검증 호출 실패: {status_count.get('VALIDATE_ERROR', 0)}")
    L.append("")

    if error_codes:
        L.append("## ❌ 에러 코드 빈도 (검증 차단 — 점검 필요)\n")
        for code, n in error_codes.most_common():
            L.append(f"- `{code}`: {n}건")
        L.append("")
    if warn_codes:
        L.append("## ⚠️ 경고 코드 빈도\n")
        for code, n in warn_codes.most_common():
            tag = " (예상됨)" if code in ACCEPTABLE_WARNINGS else " ← 점검"
            L.append(f"- `{code}`: {n}건{tag}")
        L.append("")

    # 파서 되물음(의도된 동작) 목록.
    clarifies = [r for r in rows if r["status"] == "CLARIFY"]
    if clarifies:
        L.append("## 💬 파서 되물음(CLARIFY — 의도된 동작)\n")
        L.append("모호한 조건을 임의 추측하지 않고 사용자에게 숫자를 되묻는 케이스. "
                 "실제 프론트에서는 검증 단계에 도달하지 않는다.\n")
        for r in clarifies:
            tpl = r["tpl"]
            L.append(f"- **{r['i']}. {tpl.title}** — {r['clarification'].splitlines()[0]}")
        L.append("")

    # FAIL / WARN 먼저 자세히.
    flagged = [r for r in rows if r["status"] in {"FAIL", "WARN", "PARSE_ERROR", "VALIDATE_ERROR"}]
    if flagged:
        L.append("## 🔎 점검 대상 상세\n")
        for r in flagged:
            tpl: Template = r["tpl"]
            L.append(f"### {r['i']}. [{tpl.category}/{tpl.level}] {tpl.title} — **{r['status']}**\n")
            L.append(f"> {tpl.prompt}\n")
            if r["status"] in {"PARSE_ERROR", "VALIDATE_ERROR"}:
                L.append(f"- detail: {r['detail']}")
            else:
                if r.get("errors"):
                    L.append(f"- ❌ errors: {fmt_issues(r['errors'])}")
                if r.get("warnings"):
                    L.append(f"- ⚠️ warnings: {fmt_issues(r['warnings'])}")
                L.append(f"- parsed keys: {sorted(k for k, v in r['parsed'].items() if v not in (None, [], {}))}")
            L.append("")

    # 전체 표.
    L.append("## 전체 결과\n")
    L.append("| # | 카테고리/레벨 | 제목 | 판정 | errors | warnings |")
    L.append("|---|---|---|---|---|---|")
    for r in rows:
        tpl = r["tpl"]
        if r["status"] in {"PARSE_ERROR", "VALIDATE_ERROR"}:
            L.append(f"| {r['i']} | {tpl.category}/{tpl.level} | {tpl.title} | {r['status']} | {r.get('detail','')} | |")
        elif r["status"] == "CLARIFY":
            L.append(f"| {r['i']} | {tpl.category}/{tpl.level} | {tpl.title} | CLARIFY | 파서 되물음 | |")
        else:
            L.append(f"| {r['i']} | {tpl.category}/{tpl.level} | {tpl.title} | {r['status']} "
                     f"| {fmt_issues(r.get('errors', []))} | {fmt_issues(r.get('warnings', []))} |")

    report = "\n".join(L)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"저장: {args.out}", file=sys.stderr)
    else:
        print(report)
    print(f"\n=== PASS {status_count['PASS']} · CLARIFY {status_count.get('CLARIFY', 0)} · "
          f"WARN {status_count['WARN']} · FAIL {status_count['FAIL']} ===", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
