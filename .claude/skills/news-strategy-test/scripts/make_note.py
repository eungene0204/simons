"""뉴스 전략 테스트 결과(result.json)로 해설 note.txt를 만든다 — 같은 입력이면 같은 글.

사용: python3 make_note.py <전략 폴더>     폴더에 result.json, spec.json({"prompt", "post_name", "news": {"title", "link", "published"}, "why"})
수치는 앱 화면·백테스트 로그에서 그대로 옮긴다. 계산은 벤치마크와의 차이(%p)뿐이다.
평가·전망·권유 표현을 쓰지 않는다(규제 원칙) — "과거 데이터 기준" 사실만 적는다.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

num = lambda t: float(re.sub(r"[^\d.\-]", "", t))  # noqa: E731  "+3,894,378원" → 3894378.0


def card_pairs(summary: str) -> list[tuple[str, str]]:
    """'현재까지 이해한 전략입니다' 카드 → (칸 이름, 값) 목록. 카드는 이름 줄과 값 줄이 번갈아 나온다(앱 출력의 표기 정규화)."""
    lines = [l.strip() for l in summary.splitlines() if l.strip()]
    body = lines[1:] if lines and lines[0].startswith("현재까지 이해한") else lines
    return list(zip(body[0::2], body[1::2]))


def log_find(log: list[str], pattern: str) -> re.Match | None:
    return next((m for line in log if (m := re.search(pattern, line))), None)


def build(folder: Path) -> str:
    r = json.loads((folder / "result.json").read_text())
    spec = json.loads((folder / "spec.json").read_text())
    m, log = r["metrics"], r["log"]
    news = spec.get("news", {})
    out = []
    if news:
        out += [f"[뉴스] {news.get('title', '')} ({news.get('published', '')[:16].replace('T', ' ')})", news.get("link", "")]
        if spec.get("why"):
            out.append(f"→ {spec['why']}")
        out.append("")
    out += [f"{spec.get('post_name') or r['prompt']} 전략 백테스트", "", f"입력 문장: “{r['prompt']}”", "", "널스탁 해석"]
    out += [f"- {k}: {v}" for k, v in card_pairs(r["summary"])]
    cost = log_find(log, r"수수료\s*([\d.]+%)\s*/\s*슬리피지\s*([\d.]+%)\s*/\s*거래세\s*([\d.]+%)(?:\s*→\s*([\d.]+%))?")
    if cost:
        tax = f"{cost.group(3)}(시행일 기준 {cost.group(4)})" if cost.group(4) else cost.group(3)
        out.append(f"- 비용: 수수료 {cost.group(1)}, 슬리피지 {cost.group(2)}, 거래세 {tax}")
    period = log_find(log, r"기간:\s*(\d{4}-\d{2}-\d{2}) ~ (\d{4}-\d{2}-\d{2})")
    if period:
        out.append(f"- 실제 데이터 구간: {period.group(1)} ~ {period.group(2)}")
    if r.get("answered"):
        out.append(f"- 문장에 없어 버튼으로 고른 값: {' · '.join(r['answered'])}")

    diff = num(m["roi"]) - num(m["benchmark"])
    out += ["", "결과 (과거 데이터 기준)",
            f"- 투자 수익률 {m['roi']} (총 수익 {m['total_profit']}), 연평균 {m['cagr']}",
            f"- 같은 기간 {m['benchmark_name']} {m['benchmark']} — 차이 {diff:+.2f}%p",
            f"- 최대 낙폭 {m['mdd']}",
            f"- 거래 {m['trades']}, 승률 {m['win_rate']}, 손익비 {m['profit_factor']}(총이익÷총손실)",
            f"- 샤프 {m['sharpe']}, 소티노 {m['sortino']}"]
    avg = log_find(log, r"평균수익:\s*([+\-][\d.]+%)\s*/\s*평균손실:\s*([+\-][\d.]+%)")
    if avg:
        out.append(f"- 거래당 평균 수익 {avg.group(1)}, 평균 손실 {avg.group(2)}")
    hold = log_find(log, r"평균보유일:\s*(\d+)일")
    if hold:
        out.append(f"- 평균 보유 {hold.group(1)}일")
    tops = [t for l in log if l.startswith("TOP") and (t := re.search(r"TOP\d\s+(.+?)\(\d+\):\s*([+\-][\d,]+)원\s*/.*?/\s*(\d+)거래", l))]
    tops = [t for t in tops if num(t.group(2)) > 0][:2]
    if tops:
        out.append("- 수익 상위 종목: " + ", ".join(f"{t.group(1)} {t.group(2)}원({t.group(3)}거래)" for t in tops))
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    folder = Path(sys.argv[1])
    text = build(folder)
    (folder / "note.txt").write_text(text)
    print(text)
