"""전략 템플릿 일괄 QA 하니스.

components/strategy/StrategyExampleTabs.tsx 의 EXAMPLES 50개 프롬프트를 차례로
백엔드 /strategy/parse → /strategy/coach/sessions 에 흘려보내, 전략 요약과
코칭 응답을 받아낸다. 그리고 프롬프트에 등장했지만 파싱 결과에 반영되지 않은
표현(= 미탐지)을 휴리스틱으로 플래그하고, 코칭이 비어있거나 오류인 케이스를
표시해 마크다운 리포트를 출력한다.

사전 조건: 백엔드가 떠 있고 NL 파서 모델이 로드되어 있어야 한다(/model/status == ok).

실행:
    cd backend && python qa_template_coverage.py
    cd backend && python qa_template_coverage.py --out ../docs/template_qa_report.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import urllib.request
import urllib.error

BACKEND = "http://localhost:8000"
TSX_PATH = Path(__file__).resolve().parent.parent / "components/strategy/StrategyExampleTabs.tsx"


# ──────────────────────────────────────────────────────────────────────────
# 템플릿 추출
# ──────────────────────────────────────────────────────────────────────────
@dataclass
class Template:
    level: str
    category: str
    title: str
    prompt: str


def load_templates() -> list[Template]:
    """TSX EXAMPLES 배열에서 level/category/title/prompt 객체를 추출한다."""
    text = TSX_PATH.read_text(encoding="utf-8")
    # EXAMPLES 배열 본문만 잘라낸다.
    start = text.index("export const EXAMPLES")
    end = text.index("];", start)
    body = text[start:end]

    # 각 객체: { level: "...", category: "...", title: "...", prompt: "..." }
    obj_re = re.compile(
        r"level:\s*\"(?P<level>[^\"]+)\",\s*"
        r"category:\s*\"(?P<category>[^\"]+)\",\s*"
        r"title:\s*\"(?P<title>[^\"]+)\",\s*"
        r"prompt:\s*\"(?P<prompt>(?:[^\"\\]|\\.)*)\",",
        re.DOTALL,
    )
    templates: list[Template] = []
    for m in obj_re.finditer(body):
        # JS 문자열 이스케이프만 되돌린다(unicode_escape는 UTF-8 한글을 깨뜨리므로 사용 금지).
        prompt = m.group("prompt").replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")
        templates.append(
            Template(
                level=m.group("level"),
                category=m.group("category"),
                title=m.group("title"),
                prompt=prompt,
            )
        )
    return templates


# ──────────────────────────────────────────────────────────────────────────
# 백엔드 호출
# ──────────────────────────────────────────────────────────────────────────
def _post(path: str, body: dict, timeout: float = 180.0) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{BACKEND}{path}", data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_strategy(prompt: str) -> dict:
    # dev/배포 기본값은 ollama. mlx는 로컬 dev에 모델이 로드돼 있지 않아 503이 난다.
    return _post("/strategy/parse", {"prompt": prompt, "backend": "ollama"})


def coach_strategy(prompt: str, parsed: dict) -> dict:
    return _post(
        "/strategy/coach/sessions",
        {"user_prompt": prompt, "parsed_strategy": parsed},
    )


# ──────────────────────────────────────────────────────────────────────────
# 미탐지 표현 휴리스틱
# ──────────────────────────────────────────────────────────────────────────
# 프롬프트 키워드 → 파싱 결과에서 존재해야 할 요소를 검사하는 술어.
def _has_fund(parsed: dict, metric: str) -> bool:
    return any(f.get("metric") == metric for f in parsed.get("fundamental_filters", []))


def _has_signal(parsed: dict, indicator: str) -> bool:
    sigs = parsed.get("entry_signals", []) + parsed.get("exit_signals", [])
    return any(s.get("indicator") == indicator for s in sigs)


def _has_any_signal(parsed: dict, indicators: list[str]) -> bool:
    return any(_has_signal(parsed, ind) for ind in indicators)


# (이름, 프롬프트 정규식, 검사 함수) — 정규식이 매칭되는데 검사가 False면 미탐지로 플래그.
COVERAGE_CHECKS: list[tuple[str, str, Any]] = [
    ("PBR", r"PBR", lambda p: _has_fund(p, "pbr")),
    ("PER", r"PER", lambda p: _has_fund(p, "per")),
    ("ROE", r"ROE", lambda p: _has_fund(p, "roe_or_gpa")),
    ("부채비율", r"부채비율", lambda p: _has_fund(p, "debt_ratio")),
    ("시가총액", r"시가총액|시총", lambda p: _has_fund(p, "market_cap")),
    ("거래대금", r"거래대금", lambda p: _has_fund(p, "trading_value") or _has_signal(p, "trading_value")),
    ("RSI", r"RSI", lambda p: _has_signal(p, "rsi")),
    ("MACD", r"MACD", lambda p: _has_signal(p, "macd")),
    ("골든크로스/이평선", r"골든크로스|데드크로스|이동평균|이평선", lambda p: _has_any_signal(p, ["ma_crossover", "ema"])),
    ("EMA", r"EMA", lambda p: _has_any_signal(p, ["ema", "ma_crossover"])),
    ("볼린저", r"볼린저", lambda p: _has_signal(p, "bollinger_bands")),
    ("ADX", r"ADX", lambda p: _has_signal(p, "adx")),
    ("스토캐스틱", r"스토캐스틱", lambda p: _has_signal(p, "stochastic")),
    ("CCI", r"CCI", lambda p: _has_signal(p, "cci")),
    ("신고가/돌파", r"신고가|돌파|박스권", lambda p: _has_any_signal(p, ["breakout"])),
    ("거래량", r"거래량", lambda p: _has_any_signal(p, ["volume_spike"]) or _has_fund(p, "trading_value")),
]

# 리스크/포트폴리오 수치 — 프롬프트에 등장하면 해당 필드가 채워졌는지 검사.
RISK_KEYWORDS = [
    ("손절", "stop_loss_pct", r"손절"),
    ("익절", "take_profit_pct", r"익절|수익\s*[0-9]+%|[0-9]+%\s*나면\s*팔"),
    ("트레일링", "trailing_stop_pct", r"트레일링|추적\s*손절"),
]

REBAL_WORDS = r"리밸런싱|리밸런스|교체|점검|로테이션|순위를\s*다시"


def extract_pct(prompt: str, keyword_re: str) -> Optional[float]:
    """키워드 부근의 퍼센트 수치를 추출한다(값 비교용, 근사)."""
    for m in re.finditer(keyword_re, prompt):
        window = prompt[max(0, m.start() - 12): m.end() + 12]
        nums = re.findall(r"-?\d+(?:\.\d+)?\s*%", window)
        if nums:
            return abs(float(nums[0].replace("%", "").strip()))
    return None


@dataclass
class Flags:
    missing_detect: list[str] = field(default_factory=list)   # 미탐지 표현
    value_mismatch: list[str] = field(default_factory=list)   # 값 불일치
    notes: list[str] = field(default_factory=list)            # 기타(clarification 등)
    coach_problem: Optional[str] = None                       # 코칭 비어있음/오류


def analyze(tpl: Template, parse_res: dict, coach_msg: Optional[str], coach_err: Optional[str]) -> Flags:
    flags = Flags()
    parsed = parse_res.get("parsed", {})
    prompt = tpl.prompt

    # 1) 지표/펀더멘털 미탐지
    for name, pat, check in COVERAGE_CHECKS:
        if re.search(pat, prompt) and not check(parsed):
            flags.missing_detect.append(name)

    # 2) 리스크 수치 미탐지 + 값 비교
    for name, field_name, pat in RISK_KEYWORDS:
        if re.search(pat, prompt):
            val = parsed.get(field_name)
            if val is None:
                flags.missing_detect.append(name)
            else:
                expected = extract_pct(prompt, pat)
                if expected is not None and abs(abs(float(val)) - expected) > 0.01:
                    flags.value_mismatch.append(f"{name}: 프롬프트 {expected}% vs 파싱 {val}%")

    # 3) 종목 수 비교
    mpos = re.search(r"(\d+)\s*종목", prompt)
    if mpos:
        want = int(mpos.group(1))
        got = parsed.get("max_positions")
        if got is not None and got != want:
            flags.value_mismatch.append(f"종목수: 프롬프트 {want} vs 파싱 {got}")

    # 4) 리밸런싱 언급되었는데 none
    if re.search(REBAL_WORDS, prompt) and parsed.get("rebalancing_period") in (None, "none"):
        flags.missing_detect.append("리밸런싱")

    # 5) 진입 규칙이 아예 비어있음(펀더멘털도 신호도 없음, 랭킹도 없음)
    if (
        not parsed.get("fundamental_filters")
        and not parsed.get("entry_signals")
        and not parsed.get("ranking_metric")
    ):
        flags.notes.append("진입 규칙 없음(펀더멘털·신호·랭킹 모두 비어있음)")

    # 6) clarification_question — 파서가 못 잡아 되물음
    if parse_res.get("clarification_question"):
        flags.notes.append(f"clarification: {parse_res['clarification_question'][:80]}")

    # 7) 상대강도/변동성 — 현재 미지원 가능성 표현
    if re.search(r"상대강도", prompt) and not parsed.get("ranking_metric"):
        flags.notes.append("상대강도(RS) 표현 — 랭킹 미반영")
    if re.search(r"변동성", prompt):
        flags.notes.append("변동성 표현 — 지원 여부 확인 필요")
    if re.search(r"현금흐름|영업활동현금흐름|매출\s*성장", prompt):
        flags.notes.append("현금흐름/성장 팩터 표현 — 펀더멘털 매핑 확인 필요")
    if re.search(r"섹터|업종", prompt):
        flags.notes.append("섹터/업종 제약 표현 — 지원 여부 확인 필요")
    if re.search(r"배당", prompt):
        flags.notes.append("배당 표현 — 지원 여부 확인 필요")

    # 8) 코칭 문제
    if coach_err:
        flags.coach_problem = f"코칭 오류: {coach_err}"
    elif not coach_msg or not coach_msg.strip():
        flags.coach_problem = "코칭 응답 비어있음"
    elif len(coach_msg.strip()) < 40:
        flags.coach_problem = f"코칭 응답 과도하게 짧음({len(coach_msg.strip())}자)"

    return flags


# ──────────────────────────────────────────────────────────────────────────
# 요약 렌더
# ──────────────────────────────────────────────────────────────────────────
def summarize_parsed(parsed: dict) -> str:
    parts = []
    if parsed.get("universe"):
        parts.append("유니버스=" + ",".join(parsed["universe"]))
    fund = parsed.get("fundamental_filters", [])
    if fund:
        parts.append("펀더멘털=" + ",".join(f"{f['metric']}{f['operator']}{f['value']}" for f in fund))
    ent = parsed.get("entry_signals", [])
    if ent:
        parts.append("진입=" + ",".join(s["indicator"] for s in ent))
    ex = parsed.get("exit_signals", [])
    if ex:
        parts.append("청산=" + ",".join(s["indicator"] for s in ex))
    if parsed.get("ranking_metric"):
        parts.append(f"랭킹={parsed['ranking_metric']}({parsed.get('ranking_lookback_days')}d)")
    parts.append(f"max_pos={parsed.get('max_positions')}")
    if parsed.get("hold_period_days"):
        parts.append(f"보유={parsed['hold_period_days']}d")
    if parsed.get("rebalancing_period") not in (None, "none"):
        parts.append(f"리밸={parsed['rebalancing_period']}")
    risk = []
    if parsed.get("stop_loss_pct"):
        risk.append(f"SL{parsed['stop_loss_pct']}")
    if parsed.get("take_profit_pct"):
        risk.append(f"TP{parsed['take_profit_pct']}")
    if parsed.get("trailing_stop_pct"):
        risk.append(f"TS{parsed['trailing_stop_pct']}")
    if risk:
        parts.append("리스크=" + "/".join(risk))
    return " · ".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=str, default=None, help="마크다운 리포트 출력 경로")
    ap.add_argument("--limit", type=int, default=None, help="앞에서 N개만 실행")
    ap.add_argument("--start", type=int, default=0, help="앞에서 N개 건너뛰고 그 뒤부터 실행(새 템플릿만 돌릴 때)")
    ap.add_argument("--no-coach", action="store_true", help="코칭 호출 생략(파싱만)")
    args = ap.parse_args()

    # 백엔드 헬스체크
    try:
        with urllib.request.urlopen(f"{BACKEND}/model/status", timeout=5) as r:
            status = json.loads(r.read())
        if status.get("status") != "ok":
            print(f"[중단] 모델 상태가 ok가 아님: {status}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"[중단] 백엔드에 연결 불가: {e}", file=sys.stderr)
        return 1

    templates = load_templates()
    if args.start:
        templates = templates[args.start:]
    if args.limit:
        templates = templates[: args.limit]
    print(f"템플릿 {len(templates)}개 로드됨 (start={args.start})\n", file=sys.stderr)

    lines: list[str] = ["# 전략 템플릿 일괄 QA 리포트\n"]
    lines.append(f"- 대상: {len(templates)}개 템플릿")
    lines.append(f"- 백엔드: {BACKEND}\n")

    problem_rows: list[str] = []
    n_missing = n_value = n_coach = 0

    for i, tpl in enumerate(templates, args.start + 1):
        t0 = time.perf_counter()
        parse_err = coach_err = None
        parse_res: dict = {}
        coach_msg: Optional[str] = None
        try:
            parse_res = parse_strategy(tpl.prompt)
        except Exception as e:
            parse_err = str(e)

        if not parse_err and not args.no_coach:
            try:
                coach_res = coach_strategy(tpl.prompt, parse_res.get("parsed", {}))
                coach_msg = coach_res.get("message")
            except urllib.error.HTTPError as e:
                coach_err = f"{e.code} {e.read().decode('utf-8', 'ignore')[:120]}"
            except Exception as e:
                coach_err = str(e)

        dt = time.perf_counter() - t0
        print(f"[{i:>2}/{args.start + len(templates)}] {tpl.title}  ({dt:.1f}s)", file=sys.stderr)

        lines.append(f"\n## {i}. [{tpl.category}/{tpl.level}] {tpl.title}\n")
        lines.append(f"> {tpl.prompt}\n")

        if parse_err:
            lines.append(f"- ❌ **파싱 오류**: {parse_err}")
            problem_rows.append(f"{i}. {tpl.title} — 파싱 오류")
            continue

        parsed = parse_res.get("parsed", {})
        lines.append(f"- **요약**: {summarize_parsed(parsed)}")

        flags = analyze(tpl, parse_res, coach_msg, coach_err)
        if flags.missing_detect:
            n_missing += 1
            lines.append(f"- ⚠️ **미탐지 표현**: {', '.join(flags.missing_detect)}")
        if flags.value_mismatch:
            n_value += 1
            lines.append(f"- ⚠️ **값 불일치**: {'; '.join(flags.value_mismatch)}")
        if flags.notes:
            for note in flags.notes:
                lines.append(f"- ℹ️ {note}")
        if flags.coach_problem:
            n_coach += 1
            lines.append(f"- ❌ **{flags.coach_problem}**")

        if coach_msg:
            preview = coach_msg.strip().replace("\n", " ")
            lines.append(f"- **코칭**: {preview[:400]}{'…' if len(preview) > 400 else ''}")

        if flags.missing_detect or flags.value_mismatch or flags.coach_problem:
            tags = []
            if flags.missing_detect:
                tags.append(f"미탐지[{','.join(flags.missing_detect)}]")
            if flags.value_mismatch:
                tags.append("값불일치")
            if flags.coach_problem:
                tags.append("코칭문제")
            problem_rows.append(f"{i}. {tpl.title} — {' / '.join(tags)}")

    # 요약 섹션
    summary = [
        "\n---\n",
        "## 종합\n",
        f"- 미탐지 표현 있는 템플릿: **{n_missing}개**",
        f"- 값 불일치 템플릿: **{n_value}개**",
        f"- 코칭 문제 템플릿: **{n_coach}개**\n",
    ]
    if problem_rows:
        summary.append("### 점검 필요 목록\n")
        summary.extend(problem_rows)
    else:
        summary.append("문제 없음 ✅")

    report = "\n".join(lines + summary)

    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"\n리포트 저장: {args.out}", file=sys.stderr)
    else:
        print(report)

    # 종합 한 줄 — stderr
    print(
        f"\n=== 미탐지 {n_missing} · 값불일치 {n_value} · 코칭문제 {n_coach} ===",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
