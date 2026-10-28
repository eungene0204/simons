"""전략 시뮬레이션용 예시 전략 실행 설정 생성(2026-10-28).

예시 문장(components/strategy/strategyExamples.ts)을 백엔드 /strategy/parse로 해석하고, 되묻기가 나오면
사람이 검토한 답변표(scripts/example_simulation_answers.json)의 답을 그대로 보내 최종 엔진 요청을 얻는다.
결과는 lib/strategy/exampleSimulations.json에 고정되며, 전략 시뮬레이션 화면은 이 파일만 읽는다(요청 중 LLM 없음).

공개 조건:
  - 되묻기 없이 끝까지 해석된 예시, 또는
  - 답변표 항목이 reviewed=true이고 기록된 질문이 실제 질문과 순서대로 일치한 예시
말하지 않은 값을 이 스크립트가 정하지 않는다(예외: 사용자가 명시 허용한 --random — 고른 값은 항목마다 random=true로 남기고
출력의 assumptions로 화면에 그대로 보인다) — 초안(--draft)은 칩 선택지 첫 값을 채워 reviewed=false로만 남기고,
사람이 답을 고르고 reviewed=true로 바꿔야 공개 대상이 된다.

  uv run python scripts/build_example_simulations.py            # 검토된 답변표로 실행 설정 생성
  uv run python scripts/build_example_simulations.py --draft    # 답이 없는 되묻기에 초안을 채워 답변표에 추가
  uv run python scripts/build_example_simulations.py --random   # 미검토 예시의 되묻기를 칩 중 무작위로 골라 공개(2026-10-29 사용자 지시)
  uv run python scripts/build_example_simulations.py --only "이평선 골든크로스 따라가기"

LLM 해석(첫 턴)을 예시마다 부르므로 OpenRouter 무료 한도를 쓴다. 칩 답변 턴은 결정론 레인이다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from qa_template_detect import load_templates  # noqa: E402

BACKEND = os.environ.get("QA_BACKEND", "http://localhost:8000")
TIMEOUT = int(os.environ.get("QA_TIMEOUT", "300"))
ANSWERS_PATH = ROOT / "scripts/example_simulation_answers.json"
OUTPUT_PATH = ROOT / "lib/strategy/exampleSimulations.json"
MAX_TURNS = 8

# lib/strategy/executableRequest.ts ENGINE_REQUEST_KEYS와 같은 집합(exampleSimulations.test.ts가 대조한다).
ENGINE_REQUEST_KEYS = (
    "symbols", "universe_id", "backtest_mode", "target_stocks", "sector", "etf_theme",
    "listing_from", "listing_to", "entry", "exit", "risk", "period", "startDate", "endDate", "options",
)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def example_key(title: str) -> str:
    return sha256(title)[:16]


def post(payload: dict) -> dict:
    req = urllib.request.Request(
        f"{BACKEND}/strategy/parse", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


def follow_up(res: dict, question: str, answer: str) -> dict:
    """프론트 계약(page.tsx)과 같은 무상태 에코 — 칩과 정확히 같은 답이면 결정론 칩 답변 레인으로 간다."""
    return {
        "prompt": answer,
        "backend": "ollama",
        "previous_parsed": res.get("parsed"),
        "pending_ask": res.get("pending_ask"),
        "pending_question": question,
        "previous_explicit_fields": res.get("explicit_fields") or [],
        "previous_declined_fields": res.get("declined_fields") or [],
        "previous_field_metadata": res.get("field_metadata") or {},
        "previous_artifacts": res.get("artifacts") or {},
        "previous_field_states": res.get("field_states") or {},
    }


def pick_snapshot(request: dict | None) -> dict | None:
    if not request or not all(isinstance(request.get(k), dict) for k in ("entry", "exit", "risk")):
        return None
    return {k: request[k] for k in ENGINE_REQUEST_KEYS if k in request and request[k] is not None}


def run_example(prompt: str, entry: dict, draft: bool, pick_random: bool = False) -> tuple[str, dict | None, str]:
    """(상태, 스냅샷, 메모). entry["turns"]는 draft면 이 함수가 덧붙인다."""
    turns: list[dict] = entry["turns"]
    res = post({"prompt": prompt, "backend": "ollama"})
    asked = 0
    while True:
        question = res.get("clarification_question")
        if not question:
            break
        if asked >= MAX_TURNS:
            return "too_many_turns", None, question
        if asked < len(turns) and turns[asked]["question"] != question:
            if not draft:
                return "stale_answers", None, f"기록된 질문과 다름: {question}"
            # 앞선 답이 바뀌어 뒤 질문이 달라졌다 — 여기서부터 초안을 다시 쓰고 재검토받는다.
            del turns[asked:]
            entry["reviewed"] = False
        if asked == len(turns):
            if not draft:
                return "unanswered", None, question
            chips = (res.get("pending_ask") or {}).get("chips") or res.get("clarification_suggestions") or []
            if pick_random and chips:
                turns.append({"question": question, "chips": chips, "answer": random.choice(chips), "random": True})
            else:
                turns.append({"question": question, "chips": chips, "answer": chips[0] if chips else None})
        answer = turns[asked]["answer"]
        if not answer:
            return "needs_manual", None, question
        res = post(follow_up(res, question, answer))
        asked += 1
    if asked < len(turns):
        if not draft:
            return "stale_answers", None, "기록된 답이 실제 질문보다 많음"
        del turns[asked:]
        entry["reviewed"] = False
    snapshot = pick_snapshot(res.get("backtest_request"))
    if snapshot is None:
        return "not_executable", None, ""
    return "complete", snapshot, ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--draft", action="store_true", help="답이 없는 되묻기에 칩 첫 값 초안을 채워 답변표에 추가")
    ap.add_argument("--random", action="store_true", help="검토되지 않은 예시의 되묻기 답을 칩 중 무작위로 골라 공개 대상으로 올린다(고른 값은 화면에 표시)")
    ap.add_argument("--only", action="append", default=[], help="이 제목의 예시만 다시 만든다(여러 번 지정 가능)")
    args = ap.parse_args()
    if args.random:
        args.draft = True

    answers: dict = json.loads(ANSWERS_PATH.read_text(encoding="utf-8")) if ANSWERS_PATH.exists() else {}
    output = json.loads(OUTPUT_PATH.read_text(encoding="utf-8")) if OUTPUT_PATH.exists() else {"entries": []}
    entries = {e["key"]: e for e in output["entries"]} if args.only else {}

    templates = [t for t in load_templates("kr") if not args.only or t.title in args.only]
    if args.only and len(templates) != len(set(args.only)):
        print(f"찾지 못한 제목: {sorted(set(args.only) - {t.title for t in templates})}")
        return 2

    summary: dict[str, list[str]] = {}
    for t in templates:
        prompt_sha = sha256(t.prompt)
        entry = answers.get(t.title)
        if not entry or entry.get("prompt_sha256") != prompt_sha:
            # 예시 문구가 바뀌면 옛 답은 다른 질문에 대한 답일 수 있어 버리고 다시 검토받는다.
            entry = {"prompt_sha256": prompt_sha, "reviewed": False, "turns": []}
        if args.random and not entry["reviewed"]:
            entry["turns"] = []          # 아무도 고르지 않은 초안(칩 첫 값)·옛 무작위 값은 버리고 새로 뽑는다
            entry["random"] = True
        try:
            status, snapshot, note = run_example(t.prompt, entry, args.draft, args.random)
        except (urllib.error.URLError, TimeoutError) as exc:
            status, snapshot, note = "request_failed", None, str(exc)
        if entry["turns"]:
            answers[t.title] = entry
        else:
            answers.pop(t.title, None)

        key = example_key(t.title)
        entries.pop(key, None)
        if status == "complete" and (not entry["turns"] or entry["reviewed"] or entry.get("random")):
            assumptions = [
                {"question": turn["question"], "answer": turn["answer"], "random": bool(turn.get("random"))}
                for turn in entry["turns"]
            ]
            entries[key] = {"key": key, "title": t.title, "promptSha256": prompt_sha, "snapshot": snapshot, "assumptions": assumptions}
            status = "published"
        elif status == "complete":
            status = "awaiting_review"
        summary.setdefault(status, []).append(t.title)
        print(f"[{status:>15}] {t.title}{' — ' + note[:80] if note else ''}", flush=True)

    if args.draft or answers:
        ANSWERS_PATH.write_text(json.dumps(dict(sorted(answers.items())), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ordered = sorted(entries.values(), key=lambda e: e["title"])
    OUTPUT_PATH.write_text(json.dumps({"entries": ordered}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("\n요약")
    for status, titles in sorted(summary.items()):
        print(f"  {status}: {len(titles)}")
    print(f"공개 대상 {len(ordered)}개 → {OUTPUT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
