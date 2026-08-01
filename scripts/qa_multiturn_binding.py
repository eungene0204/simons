#!/usr/bin/env python3
"""멀티턴 결속 QA — "직전 질문과 이번 답변이 이어지는가"를 실제 파스 레인에서 확인한다.

기존 QA 하니스(qa_free_input·qa_parse_accuracy 등)는 전부 **한 턴**을 본다. 그런데
반복 신고되는 증상 — 직전 질문과 답변의 연결 소실, 이미 결정한 값 재질문, 수정 시
흐름 깨짐 — 은 전부 턴과 턴 **사이**에서 난다. 한 턴짜리 하니스로는 재현되지 않는다.

이 스크립트는 프론트(app/analytics/new/page.tsx)의 무상태 에코 계약을 그대로 흉내낸다:
previous_parsed·pending_ask·pending_question·previous_explicit_fields를 턴마다 이어
보내고, 턴 사이에 무엇이 끊겼는지 기록한다.

    python scripts/qa_multiturn_binding.py            # 전체 시나리오
    python scripts/qa_multiturn_binding.py --only S1  # 하나만

되묻기는 실패가 아니다(CLAUDE.md) — 이 하니스는 "물었나"가 아니라 **"물은 것을
기억하나"**를 본다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE_URL = os.environ.get("QA_BACKEND_URL", "http://localhost:8000") + "/strategy/parse"
TIMEOUT = int(os.environ.get("QA_TIMEOUT", "300"))

# 시나리오: (id, 설명, [사용자 발화...])
# 각 발화는 직전 턴의 응답을 프론트 계약대로 에코하며 이어진다.
SCENARIOS = [
    ("S1", "질문 → 답변 연결", [
        "코스피에서 PER 10 이하 종목 전략 만들어줘",
        "매월 리밸런싱",
        "최대 5종목",
    ]),
    ("S2", "결정한 값 재질문 여부", [
        "코스피200에서 20일 고점 돌파하면 매수, 데드크로스에서 매도",
        "손절 7%",
        "최근 3년",
    ]),
    ("S3", "이전 결정 수정 후 흐름", [
        "코스피에서 PER 10 이하 매수 전략",
        "매월 리밸런싱",
        "아니 PER은 15로 바꿔줘",
    ]),
    ("S4-ETF", "ETF 유니버스 질문 적합성", [
        "반도체 ETF로 전략 만들어줘",
    ]),
    ("S4-단일", "단일 종목 질문 적합성", [
        "삼성전자만으로 전략 만들어줘",
    ]),
    ("S4-코스피", "일반 유니버스 질문(대조군)", [
        "코스피 종목으로 전략 만들어줘",
    ]),
    ("S5", "짧은 답의 귀속", [
        "코스닥에서 거래량 급증하면 매수",
        "3개",
    ]),
]

# 유니버스별로 **물으면 안 되는** 것 — dataset.py의 forbidden_terms와 같은 계약.
FORBIDDEN = {
    "S4-ETF": ["PER", "PBR", "ROE", "EPS", "영업이익", "순이익", "매출"],
    "S4-단일": ["최대 몇 종목", "몇 종목을", "리밸런싱 주기"],
}


def post(payload: dict) -> dict:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        BASE_URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
        return json.loads(res.read().decode())


def question_of(res: dict) -> str | None:
    return res.get("clarification_question")


def run_scenario(sid: str, desc: str, turns: list[str]) -> dict:
    print(f"\n{'='*78}\n[{sid}] {desc}\n{'='*78}")
    state: dict = {}          # 프론트가 들고 있는 것(previous_* 에코원)
    asked: list[str] = []     # 지금까지 나간 질문
    findings: list[str] = []

    for i, prompt in enumerate(turns, 1):
        payload = {"prompt": prompt, "backend": "ollama"}
        if state.get("parsed"):
            # 프론트 계약(page.tsx): currentParsed가 있을 때만 맥락을 에코한다.
            payload["previous_parsed"] = state["parsed"]
            if state.get("pending_ask"):
                payload["pending_ask"] = state["pending_ask"]
            if state.get("question"):
                payload["pending_question"] = state["question"]
            payload["previous_explicit_fields"] = state.get("explicit_fields") or []
            payload["previous_field_metadata"] = state.get("field_metadata") or {}
            payload["previous_artifacts"] = state.get("artifacts") or {}

        started = time.perf_counter()
        try:
            res = post(payload)
        except urllib.error.HTTPError as exc:
            print(f"  T{i} ❌ HTTP {exc.code} — {exc.read().decode()[:200]}")
            findings.append(f"T{i} 요청 실패")
            break
        elapsed = time.perf_counter() - started

        q = question_of(res)
        chips = res.get("clarification_suggestions") or []
        pending = res.get("pending_ask")
        explicit = res.get("explicit_fields") or []

        print(f"\n  T{i} 입력: {prompt!r}   ({elapsed:.1f}s)")
        print(f"     질문   : {(q or '(없음)')[:88]}")
        print(f"     칩     : {chips if chips else '(없음)'}")
        print(f"     결속   : {'있음 topic=' + str(pending.get('topic')) if pending else '없음 ← 다음 턴 귀속 근거 없음'}")
        print(f"     우선순위: {res.get('clarification_priority') or '(없음)'}")
        print(f"     확정필드: {explicit}")

        # ── 판정 ────────────────────────────────────────────────────────────
        if q and not pending:
            findings.append(f"T{i} 질문에 결속 없음 — 다음 답변이 새 발화로 분류됨")
        # 직전 질문에 **답한** 턴에서만 질문 반복을 결함으로 센다. 사용자가 다른 것을
        # 말했으면(손절을 물었는데 "최대 5종목") 그 질문이 남아 있는 것이 정상이다 —
        # 이걸 결함으로 세면 정상 동작을 버그로 오독한다.
        answered_prior = bool(
            state.get("pending_ask")
            and prompt.strip() in {str(c).strip() for c in
                                   (state["pending_ask"].get("chips") or [])}
        )
        if answered_prior and q and q == state.get("question"):
            findings.append(f"T{i} 답했는데 같은 질문 유지 — 답이 반영되지 않음: {q[:50]}")
        elif q and q in asked and q != state.get("question"):
            findings.append(f"T{i} 이전에 했던 질문으로 되돌아감: {q[:50]}")
        for term in FORBIDDEN.get(sid, []):
            haystack = (q or "") + " " + " ".join(chips)
            if term in haystack:
                findings.append(f"T{i} 이 유니버스에 물으면 안 되는 항목: {term!r}")
        if i > 1 and state.get("explicit_fields") and not (
                set(explicit) >= set(state["explicit_fields"])):
            lost = sorted(set(state["explicit_fields"]) - set(explicit))
            findings.append(f"T{i} 확정 필드 소실: {lost}")

        if q:
            asked.append(q)
        state = {
            "parsed": res.get("parsed"),
            "pending_ask": pending,
            "question": q,
            "explicit_fields": explicit,
            "field_metadata": res.get("field_metadata"),
            "artifacts": res.get("artifacts"),
        }

    print()
    if findings:
        for f in findings:
            print(f"  ⚠️  {f}")
    else:
        print("  ✅ 이상 없음")
    return {"id": sid, "desc": desc, "findings": findings}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", help="시나리오 id 하나만 실행")
    args = parser.parse_args()

    targets = [s for s in SCENARIOS if not args.only or s[0] == args.only]
    if not targets:
        print(f"시나리오 없음: {args.only}", file=sys.stderr)
        return 2

    results = [run_scenario(*s) for s in targets]

    print(f"\n{'='*78}\n요약\n{'='*78}")
    total = 0
    for r in results:
        mark = "✅" if not r["findings"] else f"⚠️ {len(r['findings'])}건"
        print(f"  [{r['id']}] {r['desc']:<22} {mark}")
        total += len(r["findings"])
    print(f"\n총 {total}건")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
