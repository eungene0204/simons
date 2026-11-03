"""뉴스 전략 테스트 결과(result.json)로 해설 note.txt를 만든다 — 같은 입력이면 같은 글.

사용: python3 make_note.py <전략 폴더>     폴더에 result.json, spec.json({"prompt", "post_name", "news": {"title", "link", "published"}, "why"})
note.txt와 함께 link.txt(같은 문장으로 널스탁을 여는 링크 한 줄)를 남긴다.
수치는 앱 화면·백테스트 로그에서 그대로 옮긴다. 계산은 벤치마크와의 차이(%p)뿐이다.
평가·전망·권유 표현을 쓰지 않는다(규제 원칙) — "과거 데이터 기준" 사실만 적는다.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SITE_URL = "https://www.nullstock.im"
MAX_OPEN_LINK_PROMPT_LENGTH = 1000  # 앱(lib/strategy/strategyOpenLink.ts) 한도와 같다


def open_link(prompt: str) -> str:
    """같은 문장을 널스탁 입력창에 채워 여는 링크 — 홈(/)이어야 비로그인 방문자도 쿼리를 잃지 않는다
    (x-backtest-post의 post_to_x.strategy_open_url과 같은 규칙, 유입 출처만 news)."""
    prompt = prompt.strip()
    if not prompt or len(prompt) > MAX_OPEN_LINK_PROMPT_LENGTH:
        sys.exit(f"[중단] 링크에 넣을 전략 문장이 비었거나 {MAX_OPEN_LINK_PROMPT_LENGTH}자를 넘는다")
    # 한글은 그대로 두고(퍼센트 인코딩하면 글자당 9자) 주소·마크다운을 깨는 글자만 인코딩한다. 공백은 '+'.
    # 브라우저가 열 때 알아서 인코딩하고, 앱은 URLSearchParams로 읽으므로 '+'는 공백으로 돌아온다.
    unsafe = {" ": "+", "%": "%25", "&": "%26", "#": "%23", "+": "%2B", "(": "%28", ")": "%29",
              "<": "%3C", ">": "%3E", "\"": "%22", "'": "%27", "[": "%5B", "]": "%5D", "?": "%3F", "=": "%3D"}
    query = "".join(unsafe.get(c, c) for c in " ".join(prompt.split()))
    return f"{SITE_URL}/?prompt={query}&utm_source=news"


num = lambda t: float(re.sub(r"[^\d.\-]", "", t))  # noqa: E731  "+3,894,378원" → 3894378.0


def card_pairs(summary: str) -> list[tuple[str, str]]:
    """'현재까지 이해한 전략입니다' 카드 → (칸 이름, 값) 목록. 카드는 이름 줄과 값 줄이 번갈아 나온다(앱 출력의 표기 정규화)."""
    lines = [l.strip() for l in summary.splitlines() if l.strip()]
    body = lines[1:] if lines and lines[0].startswith("현재까지 이해한") else lines
    return list(zip(body[0::2], body[1::2]))


def log_find(log: list[str], pattern: str) -> re.Match | None:
    return next((m for line in log if (m := re.search(pattern, line))), None)


def interpretation(m: dict, log: list[str]) -> list[str]:
    """결과 숫자가 어떻게 나왔는지 푸는 '해석' 절 — 로그·지표에서 옮긴 값과 산술만 쓴다.
    평가·전망·권유, 기사와의 인과 단정은 쓰지 않는다(규제 원칙). 숫자를 못 찾은 항목은 건너뛴다."""
    trades = int(num(m["trades"]))
    lines = ["", "해석 (과거 데이터 기준, 사실과 계산만)"]
    avg = log_find(log, r"평균수익:\s*([+\-][\d.]+%)\s*/\s*평균손실:\s*([+\-][\d.]+%)")
    if trades and avg:
        wins = round(trades * num(m["win_rate"]) / 100)
        aw, al = num(avg.group(1)), abs(num(avg.group(2)))
        size = f"수익 거래 평균이 손실 거래 평균의 {aw / al:.2f}배" if al else "손실 거래 평균 0%"
        lines.append(f"- 손익 구조: 거래 {trades}회 중 약 {wins}회가 수익, 약 {trades - wins}회가 손실이었다. "
                     f"수익 거래 평균 {avg.group(1)}, 손실 거래 평균 {avg.group(2)}({size}). "
                     f"총이익이 총손실의 {m['profit_factor']}배라 투자 수익률은 {m['roi']}로 나왔다.")
    diff = num(m["roi"]) - num(m["benchmark"])
    lines.append(f"- 벤치마크 비교: 같은 기간 {m['benchmark_name']}의 수익률은 {m['benchmark']}였고, "
                 f"이 전략은 {m['roi']}로 {diff:+.2f}%p 차이였다. 벤치마크는 이 전략의 종목 구성과 다른 지수 상품이다.")
    period = log_find(log, r"기간:\s*\d{4}-\d{2}-\d{2} ~ \d{4}-\d{2}-\d{2}\s*\((\d+)일\)")
    hold = log_find(log, r"평균보유일:\s*(\d+)일")
    if period and hold:
        per_year = trades / (int(period.group(1)) / 365)
        lines.append(f"- 회전·보유: 거래 {trades}회는 연 평균 약 {per_year:.1f}회이고, 한 번 잡은 종목을 평균 {hold.group(1)}일 보유했다.")
    lines.append(f"- 낙폭: 최대 낙폭 {m['mdd']}는 기간 중 자산이 직전 고점에서 가장 크게 내려간 폭이다(최종 수익률 {m['roi']}와는 따로 측정).")
    pnl = lambda p: [(t.group(1), num(t.group(2))) for l in log if l.startswith(p)  # noqa: E731
                     if (t := re.search(rf"{p}\d\s+(.+?)\(\d+\):\s*(\+?-?[\d,]+)원", l))]
    ups = [x for x in pnl("TOP") if x[1] > 0][:2]
    downs = [x for x in pnl("BOT") if x[1] < 0][:2]
    if ups and downs:
        total, up_sum = num(m["total_profit"]), sum(v for _, v in ups)
        concentration = (f" 상위 {len(ups)}종목 합계가 총 수익 {total:+,.0f}원보다 {up_sum - total:,.0f}원 컸고, 그 밖 종목 손익은 합쳐 {total - up_sum:+,.0f}원이었다."
                         if up_sum > total > 0 else "")
        lines.append("- 종목별: 수익 상위 " + ", ".join(f"{n} {v:+,.0f}원" for n, v in ups) + " / 손실 하위 "
                     + ", ".join(f"{n} {v:+,.0f}원" for n, v in downs) + "." + concentration)
    if trades < 30:
        lines.append(f"- 표본: 거래 {trades}건이라 승률·손익비 같은 통계는 표본이 작다.")
    lines.append("- 한계: 위 수치는 하나의 기간(백테스트 구간)에서 한 번 돌린 시뮬레이션 결과이며, 미래 수익은 보장되지 않는다.")
    return lines


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
        out.append(f"- 문장에 없던 나머지 설정: {' · '.join(r['answered'])}")
    out += ["", f"널스탁에서 같은 전략으로 열기: {open_link(r['prompt'])}"]

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
    out += interpretation(m, log)
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    folder = Path(sys.argv[1])
    text = build(folder)
    (folder / "note.txt").write_text(text)
    (folder / "link.txt").write_text(open_link(json.loads((folder / "result.json").read_text())["prompt"]) + "\n")
    print(text)
