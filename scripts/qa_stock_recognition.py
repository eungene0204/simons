"""종목 인식 검증 하니스 — KOSPI+KOSDAQ 전 종목 batch.

종목분석 Agent의 '종목 인식' 단계(symbol_resolver.find_in_text + intent.classify)를
정답 마스터(stock_master)에 대해 일괄 검증한다. 서버/LLM/parquet 불필요(순수 파이썬).

검사 항목
  1. 인식(Recognition): 종목별 입력 패턴 생성 → 자기 티커로 '유일하게' 인식되는가
     · 패턴: '{name} 분석해줘', '{name} 전망 알려줘', '{name} 지금 어때?',
             '{ticker} 분석해줘', '{alias} 분석해줘'
     · 성공 = 자기 티커가 유일 매칭 + (행동질문 패턴은) intent=STOCK_ANALYSIS·conf≥0.85
  2. 충돌(Collision): 유사 종목명 그룹에서 서로 혼동하지 않는가
  3. 애매(Ambiguous): 등록명이 아닌 접두어('삼성','현대')는 임의로 한 종목을 고르지 않는가
     (무매칭 또는 복수후보 = 재질문 가능 = 성공)

실행:
  python scripts/qa_stock_recognition.py [--out docs/stock_recognition_qa_report.md]
                                         [--json scripts/.stock_recognition_results.json]
종료코드: KPI 미달 시 1 (CI 게이트).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from intent.classifier import classify  # noqa: E402
from stock_analysis.stock_master import MasterEntry, load_master  # noqa: E402
from stock_analysis.symbol_resolver import find_in_text  # noqa: E402

# KPI 임계값(과제 정의)
KPI_RECOGNITION = 0.99
KPI_TICKER = 0.995
KPI_AMBIGUOUS = 0.95
CONF_MIN = 0.85

# 행동 질문이 들어간 패턴은 intent=STOCK_ANALYSIS·conf 검사 대상.
_ACTION_PATTERNS = ["{q} 분석해줘", "{q} 전망 알려줘", "{q} 지금 어때?"]

# 과제가 명시한 유사 종목명 충돌 그룹(등록명 기준).
COLLISION_GROUPS = [
    ["SK하이닉스", "이닉스"],
    ["삼성전자", "삼성전기", "삼성SDI"],
    ["카카오", "카카오뱅크", "카카오페이"],
    ["LG전자", "LG화학", "LG이노텍"],
    ["현대모비스", "현대오토에버", "현대자동차"],
    ["NAVER"],
]

# 등록명이 아닌 모호한 접두어 — 임의 선택 금지(무매칭/복수후보가 정답).
AMBIGUOUS_INPUTS = ["삼성", "현대", "닉스", "하이", "카카", "엘지", "에스케이"]


@dataclass
class PromptResult:
    prompt: str
    expected_ticker: str
    actual_ticker: str | None
    match: bool
    confidence: float
    intent: str
    action: bool  # 행동질문 패턴인가(intent 검사 대상)


def _resolve_unique(prompt: str) -> str | None:
    """유일하게 인식된 티커. 0개 또는 2개 이상이면 None(모호)."""
    refs = find_in_text(prompt)
    tickers = {r.symbol for r in refs}
    return next(iter(tickers)) if len(tickers) == 1 else None


def _eval_prompt(prompt: str, expected: str, *, action: bool) -> PromptResult:
    actual = _resolve_unique(prompt)
    res = classify(prompt) if action else None
    return PromptResult(
        prompt=prompt,
        expected_ticker=expected,
        actual_ticker=actual,
        match=(actual == expected),
        confidence=res.confidence if res else 1.0,
        intent=res.intent.value if res else "n/a",
        action=action,
    )


def run_recognition(master: tuple[MasterEntry, ...]) -> list[PromptResult]:
    results: list[PromptResult] = []
    for e in master:
        for pat in _ACTION_PATTERNS:
            results.append(_eval_prompt(pat.format(q=e.stock_name), e.ticker, action=True))
        results.append(_eval_prompt(f"{e.ticker} 분석해줘", e.ticker, action=True))
        for alias in e.aliases:
            results.append(_eval_prompt(f"{alias} 분석해줘", e.ticker, action=True))
    return results


def run_collision(master: tuple[MasterEntry, ...]) -> list[str]:
    """그룹 내 각 종목이 자기 티커로만 인식되고 형제로 새지 않는지 검사. 실패 메시지 목록 반환."""
    by_name = {e.stock_name: e.ticker for e in master}
    fails: list[str] = []
    for group in COLLISION_GROUPS:
        tickers = {n: by_name.get(n) for n in group}
        for name in group:
            expected = tickers[name]
            if expected is None:
                fails.append(f"[충돌] '{name}' 마스터에 없음(그룹 정의 점검)")
                continue
            actual = _resolve_unique(f"{name} 분석해줘")
            if actual != expected:
                fails.append(f"[충돌] '{name}' → {actual} (기대 {expected}, 그룹 {group})")
            # 형제 티커로 잘못 새는지
            for sib, sib_t in tickers.items():
                if sib != name and actual is not None and actual == sib_t:
                    fails.append(f"[충돌] '{name}' 이 형제 '{sib}'({sib_t})로 혼동됨")
    return fails


def run_ambiguous() -> tuple[list[str], int, int]:
    """모호 입력이 임의로 한 종목을 고르지 않는지. (실패목록, 통과수, 전체수)."""
    fails: list[str] = []
    ok = 0
    for token in AMBIGUOUS_INPUTS:
        prompt = f"{token} 분석해줘"
        actual = _resolve_unique(prompt)
        if actual is None:
            ok += 1  # 무매칭/복수후보 → 재질문 가능 → 안전
        else:
            fails.append(f"[애매] '{prompt}' 가 단일 종목 {actual} 로 임의 선택됨")
    return fails, ok, len(AMBIGUOUS_INPUTS)


def _pct(n: int, d: int) -> float:
    return (n / d) if d else 1.0


def build_report(
    rec: list[PromptResult],
    collision_fails: list[str],
    amb_fails: list[str],
    amb_ok: int,
    amb_total: int,
) -> tuple[str, bool, dict]:
    n = len(rec)
    recog_ok = sum(1 for r in rec if r.match)
    # 티커 정확도: 무언가 인식했을 때 그게 맞았는가(인식 못 한 건 제외)
    resolved = [r for r in rec if r.actual_ticker is not None]
    ticker_ok = sum(1 for r in resolved if r.match)
    # 행동패턴 intent/conf 통과율
    actions = [r for r in rec if r.action and r.match]
    conf_ok = sum(1 for r in actions if r.intent == "STOCK_ANALYSIS" and r.confidence >= CONF_MIN)

    recog_rate = _pct(recog_ok, n)
    ticker_rate = _pct(ticker_ok, len(resolved))
    amb_rate = _pct(amb_ok, amb_total)
    conf_rate = _pct(conf_ok, len(actions))

    passed = (
        recog_rate >= KPI_RECOGNITION
        and ticker_rate >= KPI_TICKER
        and amb_rate >= KPI_AMBIGUOUS
        and not collision_fails
    )

    metrics = {
        "prompts": n,
        "recognition_rate": round(recog_rate, 5),
        "ticker_rate": round(ticker_rate, 5),
        "ambiguous_requestion_rate": round(amb_rate, 5),
        "intent_confidence_rate": round(conf_rate, 5),
        "collision_failures": len(collision_fails),
    }

    def status(rate: float, kpi: float) -> str:
        return "✅" if rate >= kpi else "❌"

    lines = [
        "# 종목 인식 검증 리포트 (전 종목 batch)\n",
        f"- 대상 프롬프트: **{n}개** (종목 {n and ''}마스터 기반)\n",
        "## KPI 요약\n",
        "| 지표 | 값 | 목표 | 상태 |",
        "|---|---|---|---|",
        f"| 종목 인식 정확도 | {recog_rate:.3%} | ≥{KPI_RECOGNITION:.0%} | {status(recog_rate, KPI_RECOGNITION)} |",
        f"| 티커 정확도 | {ticker_rate:.3%} | ≥{KPI_TICKER:.1%} | {status(ticker_rate, KPI_TICKER)} |",
        f"| 애매 입력 재질문 성공률 | {amb_rate:.1%} | ≥{KPI_AMBIGUOUS:.0%} | {status(amb_rate, KPI_AMBIGUOUS)} |",
        f"| intent=STOCK_ANALYSIS·conf≥{CONF_MIN} | {conf_rate:.3%} | (참고) | {'✅' if conf_rate >= CONF_MIN else '⚠️'} |",
        f"| 유사명 충돌 실패 | {len(collision_fails)}건 | 0건 | {'✅' if not collision_fails else '❌'} |",
        "",
    ]

    recog_fails = [r for r in rec if not r.match]
    lines.append(f"## 인식 실패 ({len(recog_fails)}건)\n")
    if recog_fails:
        for r in recog_fails[:50]:
            lines.append(f"- `{r.prompt}` → {r.actual_ticker} (기대 {r.expected_ticker})")
        if len(recog_fails) > 50:
            lines.append(f"- … 외 {len(recog_fails) - 50}건")
    else:
        lines.append("- 없음")

    lines.append(f"\n## 유사명 충돌 실패 ({len(collision_fails)}건)\n")
    lines += [f"- {m}" for m in collision_fails] or ["- 없음"]

    lines.append(f"\n## 애매 입력 ({amb_ok}/{amb_total} 안전)\n")
    lines += [f"- {m}" for m in amb_fails] or ["- 전부 무매칭/복수후보(재질문 가능) — 안전"]

    lines.append("\n---\n")
    lines.append(f"최종 판정: **{'PASS ✅' if passed else 'FAIL ❌'}**")
    return "\n".join(lines), passed, metrics


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/stock_recognition_qa_report.md")
    ap.add_argument("--json", default=None, help="전체 프롬프트 결과(JSON) 덤프 경로")
    ap.add_argument("--limit", type=int, default=0, help="종목 수 제한(스모크 테스트용)")
    args = ap.parse_args()

    master = load_master()
    if args.limit:
        master = master[: args.limit]
    print(f"마스터 종목 수: {len(master)}", file=sys.stderr)

    rec = run_recognition(master)
    collision_fails = run_collision(load_master())  # 충돌은 항상 전체 마스터로
    amb_fails, amb_ok, amb_total = run_ambiguous()

    report, passed, metrics = build_report(rec, collision_fails, amb_fails, amb_ok, amb_total)

    out = ROOT / args.out
    out.write_text(report, encoding="utf-8")
    print(f"리포트 저장: {out}", file=sys.stderr)

    if args.json:
        jp = ROOT / args.json
        jp.write_text(
            json.dumps([r.__dict__ for r in rec], ensure_ascii=False), encoding="utf-8"
        )
        print(f"결과 덤프: {jp}", file=sys.stderr)

    print(json.dumps(metrics, ensure_ascii=False), file=sys.stderr)
    print(f"=== {'PASS' if passed else 'FAIL'} ===", file=sys.stderr)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
