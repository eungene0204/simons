"""해석 에이전트(실험 레인) vs 고정 파이프라인 — 같은 예시를 두 서버에 보내 같은 채점기로 대조한다.

채점은 예시 게이트의 정본(`qa_template_detect.analyze` + 사람이 검토한 정답표)을 그대로 쓴다.
두 서버는 같은 코드·같은 모델이고 `STRATEGY_INTERPRETATION_AGENT_MODE`만 다르다.

    QA_PIPELINE=http://127.0.0.1:8020 QA_AGENT=http://127.0.0.1:8021 \\
    QA_PIPELINE_LOG=<서버 로그> QA_AGENT_LOG=<서버 로그> \\
        uv run python scripts/qa_agent_vs_pipeline.py --n 10

LLM 호출 수는 서버 로그의 호출 기록 줄 수 차이로 센다(순차 실행 전제). 로그에 무료 한도 소진·예비
모델 전환이 보이면 그 문항부터 멈춘다 — 다른 모델로 잰 값을 섞지 않는다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qa_template_detect as gate  # noqa: E402

SIDES = {
    "pipeline": (os.environ.get("QA_PIPELINE", "http://127.0.0.1:8020"), os.environ.get("QA_PIPELINE_LOG")),
    "agent": (os.environ.get("QA_AGENT", "http://127.0.0.1:8021"), os.environ.get("QA_AGENT_LOG")),
}
_CALL_MARK = "openrouter chat |"
_OFF_LANE_MARKS = ("per-day", "lane=ollama", "exaone")


def _log_state(path: str | None) -> tuple[int, bool]:
    if not path or not Path(path).exists():
        return 0, False
    text = Path(path).read_text(errors="ignore")
    return text.count(_CALL_MARK), any(mark in text.lower() for mark in _OFF_LANE_MARKS)


def run_side(side: str, tpl) -> dict:
    url, log = SIDES[side]
    gate.BACKEND = url
    before, _ = _log_state(log)
    started = time.time()
    try:
        res = gate.parse_strategy(tpl.parse_input())
    except Exception as exc:  # noqa: BLE001 — 호출 실패는 치명으로 센다
        return {"error": str(exc)[:200], "fatal": ["파싱 호출 실패"], "missing": [], "unmatched": [],
                "seconds": round(time.time() - started, 1), "calls": 0, "off_lane": False}
    after, off_lane = _log_state(log)
    flags = gate.analyze(tpl, res)
    return {"fatal": list(flags.fatal), "missing": list(flags.missing), "unmatched": list(flags.unmatched),
            "position": flags.position or None, "question": res.get("clarification_question"),
            "summary": gate.summarize(res.get("parsed", {})), "seconds": round(time.time() - started, 1),
            "calls": after - before, "off_lane": off_lane,
            "agent": (res.get("interpreter") or {}).get("agent")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--out", default=None)
    ap.add_argument("--hard", action="store_true",
                    help="고정 파이프라인이 과거에 틀린 문항만(scripts/qa_agent_hard_cases.json)")
    args = ap.parse_args()
    templates = gate.load_templates("kr", "kr")
    if args.hard:
        hard = json.loads((Path(__file__).resolve().parent / "qa_agent_hard_cases.json").read_text())
        picked = [templates[number - 1] for number in hard["example_numbers"]] + [
            gate.Template("hard", "결함 사례", case["title"], case["prompt"], expect=case["expect"])
            for case in hard["cases"]]
    else:
        step = len(templates) / args.n
        picked = [templates[int(i * step)] for i in range(args.n)]
    rows = []
    for i, tpl in enumerate(picked, 1):
        row = {"title": tpl.title, "category": tpl.category}
        for side in SIDES:
            row[side] = run_side(side, tpl)
        if row["pipeline"].get("off_lane") or row["agent"].get("off_lane"):
            print(f"[{i}] 한도 소진·레인 전환 감지 — 여기서 멈춘다(이 문항은 버린다)", file=sys.stderr)
            break
        rows.append(row)
        print(f"[{i}/{len(picked)}] {tpl.title} | 파이프라인 치명={row['pipeline']['fatal']} 미탐지={row['pipeline']['missing']} "
              f"{row['pipeline']['calls']}건 {row['pipeline']['seconds']}s | 에이전트 치명={row['agent']['fatal']} "
              f"미탐지={row['agent']['missing']} {row['agent']['calls']}건 {row['agent']['seconds']}s", file=sys.stderr)
        if args.out:
            Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    print(json.dumps({side: {
        "문항": len(rows),
        "치명 있는 문항": sum(bool(r[side]["fatal"]) for r in rows),
        "미탐지 있는 문항": sum(bool(r[side]["missing"]) for r in rows),
        "미대조 수치 문항": sum(bool(r[side]["unmatched"]) for r in rows),
        "LLM 호출 합": sum(r[side]["calls"] for r in rows),
        "소요 초 합": round(sum(r[side]["seconds"] for r in rows), 1),
    } for side in SIDES}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
