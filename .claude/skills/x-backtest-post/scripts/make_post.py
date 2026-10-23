"""녹화 결과(result.json)로 게시용 해석 글 post1.txt를 만든다 — 사람이 쓰지 않는다(2026-10-19: 같은 입력이면 같은 글).
수치는 화면 텍스트·백테스트 로그에서 그대로 옮기고, 계산한 값은 세 가지뿐이다: 최종 자산, 벤치마크와의 차이(%p), 상위 2종목의 총 수익 비중.
평가·전망·권유 표현을 쓰지 않는다(규제 원칙). 면책 문구도 넣지 않는다(2026-10-05 사용자 상시 지시).

사용: uv run python make_post.py <결과 폴더> [--copy]      폴더에 result.json, spec.json({"prompt", "post_name"})이 있어야 한다.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_plan import summary_parts  # noqa: E402

num = lambda t: float(re.sub(r"[^\d.\-]", "", t))   # noqa: E731  "+3,894,378원" → 3894378.0
won = lambda v: f"{int(round(v)):,}원"              # noqa: E731


def man(v: float) -> str:
    """10,000,000원 → 1,000만원(앱의 칩 표기와 같게). 만 단위로 안 떨어지면 원 단위 그대로."""
    return f"{int(v // 10000):,}만원" if v % 10000 == 0 else won(v)



def log_find(log: list[str], pattern: str, group: int = 1) -> str:
    for line in log:
        m = re.search(pattern, line)
        if m:
            return m.group(group)
    return ""


def allocation_lines(items: list[str]) -> list[str]:
    """자금 배분 칸 항목 → 글 줄. 앱이 그래프에 적은 표기(`최대 10종목 보유`·`종목당 비중 10%`·`비중 방식: 동일 비중`)를 그대로 옮긴다."""
    held = next((m.group(1) for i in items if (m := re.fullmatch(r"최대 (\d+)종목 보유", i))), "")
    weight = next((m.group(1) for i in items if (m := re.fullmatch(r"종목당 비중 ([\d.]+%)", i))), "")
    method = next((m.group(1) for i in items if (m := re.fullmatch(r"비중 방식:\s*(.+)", i))), "")
    if not (held or weight or method):
        return []
    detail = ", ".join(x for x in (f"종목당 비중 {weight}" if weight else "", method) if x)
    return [f"최대 보유 종목: {held}종목" + (f"({detail})" if detail else "")] if held else [f"자금 배분: {detail}"]


def settings_lines(parts: dict, answered: list[str], log: list[str]) -> list[str]:
    lines = []
    if parts["buy"]:
        lines.append(f"매수 조건: {parts['buy']}")
    if parts["sell"]:
        lines.append(f"매도 조건: {parts['sell']}")
    # 손절·익절은 칩 답변에서 읽는다("손절 안 함" / "손절 -15%") — 칩 글자는 앱이 정한 고정 문구라 정규화일 뿐이다
    risk = [(m.group(1), m.group(2).strip()) for a in answered if (m := re.match(r"^(손절|익절)\s*(.*)$", a))]
    nones = [n for n, v in risk if v == "안 함"]
    if nones:
        lines.append(f"{'·'.join(nones)} 기준: 두지 않음")
    lines += [f"{n} 기준: {v}" for n, v in risk if v != "안 함"]
    lines += allocation_lines(parts["allocation_items"])
    if parts["rebalance"]:
        lines.append("리밸런싱: 하지 않음" if "없음" in parts["rebalance"] else f"리밸런싱: {parts['rebalance']}")
    period = log_find(log, r"기간:\s*(\d{4}-\d{2}-\d{2}) ~ (\d{4}-\d{2}-\d{2})", 0)
    d = re.search(r"기간:\s*(\d{4}-\d{2}-\d{2}) ~ (\d{4}-\d{2}-\d{2})", period)
    if parts["period"]:
        lines.append(f"백테스트 기간: 최근 {parts['period']}" + (f"({d.group(1)} ~ {d.group(2)})" if d else ""))
    if parts["capital"]:
        lines.append(f"초기 자본: {man(num(parts['capital']))}")
    cost = re.search(r"수수료\s*([\d.]+%)\s*/\s*슬리피지\s*([\d.]+%)\s*/\s*거래세\s*([\d.]+%)(?:\s*→\s*([\d.]+%))?", "\n".join(log))
    if cost:
        tax = f"{cost.group(3)}(시행일 기준 {cost.group(4)})" if cost.group(4) else cost.group(3)
        lines.append(f"비용: 수수료 {cost.group(1)}, 슬리피지 {cost.group(2)}, 거래세 {tax}")
    return lines


def build(folder: Path) -> str:
    r = json.loads((folder / "result.json").read_text())
    spec = json.loads((folder / "spec.json").read_text())
    m, log = r["metrics"], r["log"]
    parts = summary_parts(r["summary"])
    name = spec.get("post_name") or re.sub(r"\s*전략.*$", "", r["prompt"]).strip()
    uni = re.search(r"'(.+?)'은\(는\) 관련 상장사 (\d+)곳", r["summary"])

    capital = num(parts["capital"]) if parts["capital"] else None
    profit = num(m["total_profit"])
    diff = num(m["roi"]) - num(m["benchmark"])
    tops = [re.search(r"TOP\d\s+(.+?)\(\d+\):\s*([+\-][\d,]+)원\s*/.*?/\s*(\d+)거래", l) for l in log if l.startswith("TOP")]
    tops = [t for t in tops if t and num(t.group(2)) > 0][:2]
    win10 = round(num(m["win_rate"]) / 10)
    avg = re.search(r"평균수익:\s*([+\-][\d.]+%)\s*/\s*평균손실:\s*([+\-][\d.]+%)", "\n".join(log))
    streak = re.search(r"최대 연속수익:\s*(\d+)회\s*/\s*최대 연속손실:\s*(\d+)회", "\n".join(log))
    hold = log_find(log, r"평균보유일:\s*(\d+)일")
    rf = log_find(log, r"무위험수익률\s*([\d.]+%)")

    out = [f"{name} 전략을 백테스트 해봤습니다.", "", "널스탁에 이렇게 입력 했습니다", f"“{r['prompt']}”", ""]
    out.append((f"널스탁은 '{uni.group(1)}'을 관련 상장사 {uni.group(2)}곳으로 해석해 지정 종목에 담았습니다. " if uni else f"투자 대상: {', '.join(parts['universe_items']) or parts['universe']}. ")
               + "문장에 없던 설정은 버튼으로 골랐습니다.")
    out += [f"- {l}" for l in settings_lines(parts, r["answered"], log)]
    out += ["", "결과 (과거 데이터 기준)"]
    if capital:
        out.append(f"- 투자 수익률 {m['roi']}. {man(capital)}이 {won(capital + profit)}이 됐고 총 수익은 {m['total_profit']}입니다.")
    else:
        out.append(f"- 투자 수익률 {m['roi']}. 총 수익은 {m['total_profit']}입니다.")
    out += [f"- 연평균수익률(CAGR) {m['cagr']}",
            f"- 같은 기간 {m['benchmark_name']}는 {m['benchmark']}였습니다. 전략과의 차이는 {diff:+.2f}%p입니다.",
            f"- 최대 낙폭 {m['mdd']}. 자산이 고점에서 가장 많이 내려간 폭입니다.",
            f"- 승률 {m['win_rate']}. 총 {m['trades']} 거래 중 이익으로 끝난 거래의 비율이며, 10번 거래하면 약 {win10}번 수익이 났습니다.",
            f"- 손익비 {m['profit_factor']}. 총이익을 총손실로 나눈 값입니다."]
    if avg:
        out.append(f"- 평균 수익 {avg.group(1)}, 평균 손실 {avg.group(2)}")
    risk_adj = f"- 샤프 비율 {m['sharpe']}, 소티노 지수 {m['sortino']}" + (f". 무위험수익률({rf}) 대비 감수한 변동성 단위당 수익을 나타냅니다." if rf else "")
    out.append(risk_adj)
    tail = [f"최대 연속 수익 {streak.group(1)}회, 최대 연속 손실 {streak.group(2)}회" if streak else "", f"평균 보유일 {hold}일" if hold else ""]
    if any(tail):
        out.append("- " + ", ".join(t for t in tail if t))
    if len(tops) == 2:
        share = sum(num(t.group(2)) for t in tops) / profit * 100
        out += ["", "종목별로 보면 수익 상위 2개는 "
                + f"{tops[0].group(1)}({tops[0].group(2)}원, {tops[0].group(3)}거래), {tops[1].group(1)}({tops[1].group(2)}원, {tops[1].group(3)}거래)입니다. "
                + f"두 종목 합계 {won(sum(num(t.group(2)) for t in tops))}은 총 수익의 약 {share:.1f}%입니다."]
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    folder = Path(sys.argv[1])
    text = build(folder)
    (folder / "post1.txt").write_text(text)
    if "--copy" in sys.argv:
        subprocess.run(["pbcopy"], input=text.encode(), check=True)
    print(text)
