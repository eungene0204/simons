"""연구노트 — 유명 기법 백테스트 결과 JSON(research_classic_techniques.py 출력)을 노트 숫자 파일로 옮긴다.

글의 숫자는 손으로 옮기지 않는다 — 이 스크립트가 만든 `lib/notes/classicResults.ts`만 읽는다.
연도별 수익률은 일별 자산(전략·벤치마크)의 연말 값으로 계산한다(첫해·마지막 해는 부분 연도).

실행:  python3 scripts/research_classic_to_ts.py <결과 JSON> > lib/notes/classicResults.ts
"""

from __future__ import annotations

import json
import sys
from collections import Counter

MINUS = "−"


def pct(value: float, digits: int = 1, sign: bool = True) -> str:
    text = f"{abs(value):,.{digits}f}%"
    if value < 0 and round(abs(value), digits) != 0:
        return MINUS + text
    return ("+" if sign and round(value, digits) > 0 else "") + text


def num(value: float, digits: int = 2) -> str:
    text = f"{abs(value):.{digits}f}"
    return (MINUS + text) if value < 0 and round(abs(value), digits) != 0 else text


def cagr(total: float, days: int) -> float:
    years = days / 365.25
    return ((1 + total) ** (1 / years) - 1) * 100


def yearly(dates: list[str], equity: list[float], start_value: float) -> dict[str, float]:
    out: dict[str, float] = {}
    prev = start_value
    for i, day in enumerate(dates):
        last_of_year = i == len(dates) - 1 or dates[i + 1][:4] != day[:4]
        if last_of_year:
            out[day[:4]] = (equity[i] / prev - 1) * 100
            prev = equity[i]
    return out


def exit_kind(condition: str) -> str:
    for key, label in (("상장폐지", "상장폐지 정산"), ("백테스트 종료", "기간 종료 정산"), ("데이터 종료", "데이터 종료 정산"),
                       ("보유기간", "보유 기간 만료"), ("리밸런싱", "리밸런싱")):
        if key in condition:
            return label
    return "매도 신호"


def main() -> int:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
    from datetime import date

    rows = {}
    for name, row in data["rows"].items():
        r = row["result"]
        init = r["initialCapital"]
        dates, eq, bench = r["dates"], r["equity"], r["benchmark_equity"]
        days = (date.fromisoformat(dates[-1]) - date.fromisoformat(dates[0])).days + 1
        bench_total = bench[-1] / init - 1
        ys, yb = yearly(dates, eq, init), yearly(dates, bench, init)
        sells = [s for s in r["signals"] if s["type"] == "sell"]
        exits = Counter(exit_kind(s.get("condition") or "") for s in sells)
        rows[name] = {
            "start": dates[0],
            "end": dates[-1],
            "tradingDays": f"{len(dates):,}거래일",
            "endValue": f"{round(eq[-1]):,}원",
            "ret": pct(r["totalReturn"], 2),
            "cagr": pct(r["cagr"], 2),
            "mdd": pct(r["maxDrawdown"], 2),
            "sharpe": num(r["sharpe"]),
            "win": f"{r['winRate']:.1f}%",
            "pf": num(r["profitFactor"]),
            "trades": f"{r['trades']:,}회",
            "hold": f"{r['avgHoldingDays']:.0f}일",
            "benchLabel": r.get("benchmark_label") or "",
            "benchRet": pct(bench_total * 100, 2),
            "benchCagr": pct(cagr(bench_total, days), 2),
            "below": r["cagr"] < cagr(bench_total, days),
            "yearly": [[y, pct(ys[y]), pct(yb.get(y, float("nan")))] for y in ys],
            "exits": [[k, f"{v:,}회"] for k, v in exits.most_common()],
            "strategyId": row["request"].get("strategy_id", ""),
        }
        # 시작일 민감도 — 기준 실행(위)과 sensitivity의 시작일들을 합쳐 범위를 싣는다.
        runs = [(dates[0], r["totalReturn"], r["cagr"])] + [
            (start, by[name]["totalReturn"], by[name]["cagr"])
            for start, by in sorted((data.get("sensitivity") or {}).items()) if name in by
        ]
        if len(runs) > 1:
            rows[name]["startRuns"] = [[start, pct(ret, 2), pct(cg, 2)] for start, ret, cg in sorted(runs)]
            rows[name]["retRange"] = [pct(min(x[1] for x in runs), 2), pct(max(x[1] for x in runs), 2)]
    print("// 자동 생성 파일 — 손으로 고치지 않는다.")
    print("// 원천: scripts/research_classic_techniques.py 결과 JSON → scripts/research_classic_to_ts.py")
    print(f"// 널스탁 백테스트 엔진 v{data['engine_version']}.")
    print()
    print(f'export const CLASSIC_ENGINE_VERSION = "{data["engine_version"]}";')
    print()
    print("export const CLASSIC_RESULTS = " + json.dumps(rows, ensure_ascii=False, indent=2) + " as const;")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
