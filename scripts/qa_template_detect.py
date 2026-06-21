"""전략 템플릿 파싱 검출 QA (정제판, parse-only).

backend/qa_template_coverage.py 의 초판이 드러낸 휴리스틱 오탐을 제거한 버전.
- SL/TP 퍼센트 '값 불일치' 검사 제거: 파싱 값은 정확했고, 근접 추출이 옆 숫자를
  잘못 집는 오탐만 양산했다.
- 종목수: 유니버스명("KOSPI 200")·"N개 분기"·"업종 최대 N종목" 숫자를 종목수로
  오인하지 않도록 후보를 정제하고, max_positions==100(기본값 의심)을 별도 표시.
- 신고가/돌파: EMA/볼린저 '상향 돌파'를 신고가 돌파로 오인하지 않도록 신고가·박스권만 검사.

repo 루트에 둔다(uvicorn --reload-dir backend 감시 대상이 아니므로 편집해도 파스
캐시가 날아가지 않는다). 코칭은 호출하지 않는다(초판에서 코칭 문제 0건).

실행: python scripts/qa_template_detect.py [--out docs/template_detect_report.md]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import urllib.request

BACKEND = "http://localhost:8000"
ROOT = Path(__file__).resolve().parent.parent
TSX_PATH = ROOT / "components/strategy/StrategyExampleTabs.tsx"
RAW_CACHE = ROOT / "scripts/.template_parse_cache.json"


@dataclass
class Template:
    level: str
    category: str
    title: str
    prompt: str


def load_templates() -> list[Template]:
    text = TSX_PATH.read_text(encoding="utf-8")
    start = text.index("export const EXAMPLES")
    end = text.index("];", start)
    body = text[start:end]
    obj_re = re.compile(
        r"level:\s*\"(?P<level>[^\"]+)\",\s*"
        r"category:\s*\"(?P<category>[^\"]+)\",\s*"
        r"title:\s*\"(?P<title>[^\"]+)\",\s*"
        r"prompt:\s*\"(?P<prompt>(?:[^\"\\]|\\.)*)\",",
        re.DOTALL,
    )
    out: list[Template] = []
    for m in obj_re.finditer(body):
        prompt = m.group("prompt").replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")
        out.append(Template(m.group("level"), m.group("category"), m.group("title"), prompt))
    return out


def parse_strategy(prompt: str) -> dict:
    # dev/배포 기본값은 ollama. mlx는 로컬 dev에 모델이 로드돼 있지 않아 503이 난다.
    data = json.dumps({"prompt": prompt, "backend": "ollama"}).encode()
    req = urllib.request.Request(
        f"{BACKEND}/strategy/parse", data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())


# ── 검출 술어 ────────────────────────────────────────────────────────────
def _has_fund(p: dict, metric: str) -> bool:
    return any(f.get("metric") == metric for f in p.get("fundamental_filters", []))


def _has_sig(p: dict, ind: str) -> bool:
    return any(s.get("indicator") == ind for s in p.get("entry_signals", []) + p.get("exit_signals", []))


def _has_any(p: dict, inds: list[str]) -> bool:
    return any(_has_sig(p, i) for i in inds)


COVERAGE_CHECKS: list[tuple[str, str, Any]] = [
    ("PBR", r"PBR", lambda p: _has_fund(p, "pbr")),
    ("PER", r"PER", lambda p: _has_fund(p, "per")),
    ("ROE", r"ROE", lambda p: _has_fund(p, "roe_or_gpa")),
    ("부채비율", r"부채비율", lambda p: _has_fund(p, "debt_ratio")),
    ("시가총액", r"시가총액|시총", lambda p: _has_fund(p, "market_cap")),
    ("거래대금", r"거래대금", lambda p: _has_fund(p, "trading_value") or _has_sig(p, "trading_value")),
    ("RSI", r"RSI", lambda p: _has_sig(p, "rsi")),
    ("MACD", r"MACD", lambda p: _has_sig(p, "macd")),
    ("볼린저", r"볼린저", lambda p: _has_sig(p, "bollinger_bands")),
    ("ADX", r"ADX", lambda p: _has_sig(p, "adx")),
    ("스토캐스틱", r"스토캐스틱", lambda p: _has_sig(p, "stochastic")),
    ("CCI", r"CCI", lambda p: _has_sig(p, "cci")),
    # 신고가/박스권만 breakout으로 본다(EMA/볼린저 '상향 돌파'와 구분).
    ("신고가돌파", r"신고가|박스권", lambda p: _has_sig(p, "breakout")),
    ("거래량", r"거래량", lambda p: _has_any(p, ["volume_spike"]) or _has_fund(p, "trading_value")),
]

RISK_KEYWORDS = [("손절", "stop_loss_pct", r"손절"), ("익절", "take_profit_pct", r"익절|수익\s*[0-9]+%\s*나면")]
REBAL_WORDS = r"리밸런싱|리밸런스|로테이션|매주\s*.*순위|매월\s*.*순위|순위를\s*다시|점검"


def intended_positions(prompt: str) -> Optional[int]:
    """프롬프트가 명시한 포트폴리오 종목 수를 추정. 유니버스/분기/섹터 숫자는 제외."""
    candidates: list[int] = []
    # 명시적 포지션 표현
    for pat in [
        r"최대\s*(\d+)\s*종목", r"총\s*(\d+)\s*종목", r"동시\s*보유\s*(?:는\s*)?(?:최대\s*)?(\d+)\s*종목",
        r"(\d+)\s*종목\s*(?:동일|집중|동일가중|동일\s*비중|포트폴리오)", r"(\d+)\s*개\s*(?:정도\s*)?나눠",
        r"상위\s*(\d+)\s*종목",
    ]:
        for m in re.finditer(pat, prompt):
            candidates.append(int(m.group(1)))
    if candidates:
        # 섹터당 제한값(작은 값)과 전체값이 섞이면 최댓값을 포트폴리오 크기로 본다.
        return max(candidates)
    return None


@dataclass
class Flags:
    missing: list[str] = field(default_factory=list)
    position: Optional[str] = None
    notes: list[str] = field(default_factory=list)


def analyze(tpl: Template, res: dict) -> Flags:
    f = Flags()
    p = res.get("parsed", {})
    prompt = tpl.prompt

    for name, pat, check in COVERAGE_CHECKS:
        if re.search(pat, prompt) and not check(p):
            f.missing.append(name)

    for name, field_name, pat in RISK_KEYWORDS:
        if re.search(pat, prompt) and p.get(field_name) is None:
            f.missing.append(name)

    if re.search(REBAL_WORDS, prompt) and p.get("rebalancing_period") in (None, "none"):
        f.missing.append("리밸런싱")

    want = intended_positions(prompt)
    got = p.get("max_positions")
    if want is not None and got is not None and want != got:
        f.position = f"종목수: 프롬프트 {want} vs 파싱 {got}"
    elif got == 100 and not re.search(r"100\s*종목", prompt):
        # 명시 없이 100이면 기본값 폴백(미반영) 의심
        f.position = "종목수: 파싱 100(기본값 폴백 의심)"

    if not p.get("fundamental_filters") and not p.get("entry_signals") and not p.get("ranking_metric"):
        f.notes.append("진입 규칙 없음")
    if res.get("clarification_question"):
        f.notes.append("clarification 되물음")
    if re.search(r"상대강도", prompt) and not p.get("ranking_metric"):
        f.notes.append("상대강도(RS) 미반영")
    if re.search(r"변동성", prompt):
        f.notes.append("변동성 표현")
    if re.search(r"현금흐름|영업활동현금흐름|매출\s*성장", prompt):
        f.notes.append("현금흐름/성장 팩터")
    if re.search(r"섹터|업종", prompt):
        f.notes.append("섹터/업종 제약")
    if re.search(r"배당", prompt):
        f.notes.append("배당 표현")
    return f


def summarize(p: dict) -> str:
    parts = []
    if p.get("universe"):
        parts.append("유니버스=" + ",".join(p["universe"]))
    if p.get("fundamental_filters"):
        parts.append("펀더멘털=" + ",".join(f"{x['metric']}{x['operator']}{x['value']}" for x in p["fundamental_filters"]))
    if p.get("entry_signals"):
        parts.append("진입=" + ",".join(s["indicator"] for s in p["entry_signals"]))
    if p.get("exit_signals"):
        parts.append("청산=" + ",".join(s["indicator"] for s in p["exit_signals"]))
    if p.get("ranking_metric"):
        parts.append(f"랭킹={p['ranking_metric']}({p.get('ranking_lookback_days')}d)")
    parts.append(f"max_pos={p.get('max_positions')}")
    if p.get("hold_period_days"):
        parts.append(f"보유={p['hold_period_days']}d")
    if p.get("rebalancing_period") not in (None, "none"):
        parts.append(f"리밸={p['rebalancing_period']}")
    risk = [f"{k}{p[v]}" for k, v in [("SL", "stop_loss_pct"), ("TP", "take_profit_pct"), ("TS", "trailing_stop_pct")] if p.get(v)]
    if risk:
        parts.append("리스크=" + "/".join(risk))
    return " · ".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    ap.add_argument("--use-cache", action="store_true", help="저장된 원시 파스 캐시만 사용(백엔드 미호출)")
    args = ap.parse_args()

    templates = load_templates()
    cache: dict[str, dict] = {}
    if RAW_CACHE.exists():
        cache = json.loads(RAW_CACHE.read_text())

    lines = ["# 전략 템플릿 파싱 검출 리포트 (정제판)\n", f"- 대상: {len(templates)}개\n"]
    problems: list[str] = []
    n_missing = n_pos = 0

    for i, tpl in enumerate(templates, 1):
        if tpl.prompt in cache:
            res = cache[tpl.prompt]
        elif args.use_cache:
            print(f"[{i}] 캐시 없음, 건너뜀", file=sys.stderr)
            continue
        else:
            try:
                res = parse_strategy(tpl.prompt)
            except Exception as e:
                lines.append(f"\n## {i}. {tpl.title}\n- ❌ 파싱 오류: {e}")
                continue
            cache[tpl.prompt] = res
            RAW_CACHE.write_text(json.dumps(cache, ensure_ascii=False))
        print(f"[{i}/{len(templates)}] {tpl.title}", file=sys.stderr)

        p = res.get("parsed", {})
        f = analyze(tpl, res)
        lines.append(f"\n## {i}. [{tpl.category}/{tpl.level}] {tpl.title}\n")
        lines.append(f"> {tpl.prompt}\n")
        lines.append(f"- **요약**: {summarize(p)}")
        if f.missing:
            n_missing += 1
            lines.append(f"- ⚠️ **미탐지**: {', '.join(f.missing)}")
        if f.position:
            n_pos += 1
            lines.append(f"- ⚠️ **{f.position}**")
        for note in f.notes:
            lines.append(f"- ℹ️ {note}")
        tag = []
        if f.missing:
            tag.append(f"미탐지[{','.join(f.missing)}]")
        if f.position:
            tag.append(f.position)
        if tag:
            problems.append(f"{i}. {tpl.title} — {' / '.join(tag)}")

    lines += ["\n---\n## 종합\n", f"- 미탐지 표현: **{n_missing}개**", f"- 종목수 이슈: **{n_pos}개**\n", "### 점검 필요\n", *problems]
    report = "\n".join(lines)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"저장: {args.out}", file=sys.stderr)
    else:
        print(report)
    print(f"\n=== 미탐지 {n_missing} · 종목수 {n_pos} ===", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
