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
      python scripts/qa_template_detect.py --category ETF,테마 --refresh   # 예시 추가 후 검증

**예시를 추가·수정하면 반드시 이 스크립트로 검증한다**(2026-07-27 사고: ETF·테마 예시
16개를 문구 검증만 하고 파싱은 돌리지 않아, 재무+랭킹 복합 예시가 해석 실패로 빈 전략을
내보내는 것을 사용자가 먼저 발견했다). '치명' 항목(해석 실패·ETF 유니버스 오류·업종
미반영·되묻기 없는 진입 규칙 공백)이 있으면 종료 코드 1 — 게이트로 쓴다. 코칭은 호출하지 않는다.

**되묻기는 실패가 아니다**: 값이 빠진 팩터를 묻는 것은 전략 에이전트의 정상 동작이며
(말하지 않은 값을 기본값으로 확정하지 않는다는 계약), 이 하니스가 잡아야 하는 것은
**조용한** 소실 — 질문도 없이 조건이 사라지거나 빈 전략이 나가는 경우다. 되묻고 있는
팩터는 치명·미탐지 어느 쪽으로도 세지 않는다(2026-07-29 판정 수정).
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
sys.path.insert(0, str(ROOT / "backend"))


def expected_etf_theme(prompt: str) -> Optional[str]:
    """QA 기대값: 프롬프트가 가리키는 ETF 테마/상품명(ETF 마스터 자기검증 추출)."""
    from engine.universe_pit import extract_etf_theme

    return extract_etf_theme(prompt)


# 억원 단위 금액 지표 — 값이 억원이라 자릿수가 하나만 틀려도 전략이 10배 달라진다.
AMOUNT_METRIC_LABELS = {"market_cap": "시가총액", "trading_value": "거래대금"}

# 재무 지표 표시명(임계값 대조 리포트용).
FUND_METRIC_LABELS = {
    "pbr": "PBR", "per": "PER", "psr": "PSR", "ev_ebitda": "EV/EBITDA",
    "roe_or_gpa": "ROE", "roa": "ROA", "debt_ratio": "부채비율",
    "current_ratio": "유동비율", "quick_ratio": "당좌비율", "reserve_ratio": "유보율",
    "gross_margin": "매출총이익률", "net_margin": "순이익률", "operating_margin": "영업이익률",
    "revenue_growth": "매출증가율", "operating_income_growth": "영업이익증가율",
    "net_income_growth": "순이익증가율", "dividend_yield": "배당수익률",
    "payout_rate": "배당성향", "dividend_growth": "배당성장률",
    **AMOUNT_METRIC_LABELS,
}


def expected_fundamental_thresholds(prompt: str) -> list[tuple[str, float]]:
    """QA 기대값: 프롬프트가 명시한 **모든** 재무 임계값 [(metric, value)].

    금액(억원)과 비율(%·배)을 함께 돌려준다 — 자릿수 오차는 금액만의 문제가 아니고,
    'PBR 1배 이하'가 `pbr<=10`으로 파싱돼도 게이트는 값을 안 보면 초록이다.
    """
    from engine.nl_parser import _extract_fundamental_filters

    return [(f.metric, float(f.value)) for f in _extract_fundamental_filters(prompt)]


def expected_amount_thresholds(prompt: str) -> list[tuple[str, float]]:
    """QA 기대값: 프롬프트가 명시한 금액 임계값 [(metric, 억원)] (결정적 합산).

    ETF 테마(`expected_etf_theme`)와 같은 자리의 ground truth다 — 파스 경로가 아니라
    **검사 쪽 정본**이며, 쓰는 것은 조·억 표기의 산술 합산(조×10,000+억)뿐이다
    (`nl_parser._extract_amount_value`). 의미 해석이 아니라 표기 환산이므로 대원칙 1의
    '원문 해석' 금지에 걸리지 않는다 — 프로덕션 파스는 종전대로 LLM 레인이 한다.

    이 검사가 필요한 이유(2026-08-18 사고): 하니스의 커버리지 검사는 `_has_fund`로
    **지표가 있는지만** 보고 임계값은 읽지 않는다. "시가총액 1조 원 이상" 예시가
    `market_cap>=100000`(=10조, 10배)으로 파싱된 채 08-14 전수 검증을 `치명 0`으로
    통과했고, 캐시 이력을 보면 같은 문장이 프롬프트가 바뀔 때마다 10000↔100000을
    오갔다(07-28 정상 → 08-05 오류 → 08-08 정상 → 08-14 오류). 값을 보지 않는 게이트가
    매번 초록불을 켰다.

    정규식은 지표명 바로 뒤 금액 하나만 잡으므로("3000억 이상 3조 이하"에서 3000만
    나온다) 반환값은 **기대값의 부분집합**이다 — 대조도 "기대값이 파싱 결과에 들어
    있는가"로만 하고, 파싱에만 있는 값은 문제 삼지 않는다(부분 추출로 인한 오탐 방지).
    """
    from engine.nl_parser import _AMOUNT_METRICS, _extract_fundamental_filters

    return [(f.metric, float(f.value))
            for f in _extract_fundamental_filters(prompt)
            if f.metric in _AMOUNT_METRICS]


# 손절·익절은 결정적 파서가 다루지 않는 필드라(LLM·슬롯 소관) QA 쪽에서 표기만 읽는다.
# 부호는 보지 않는다 — 필드 의미에 방향이 내장돼 있어 스키마가 절댓값으로 정규화한다
# (`nl_parser._abs_ratio`). 절 경계(쉼표·마침표)를 넘지 않아 옆 절의 %를 집지 않는다.
_RISK_PCT_PATTERNS = {
    "stop_loss_pct": ("손절", r"(?:손절|스탑로스|스톱로스|손실제한)[^,.%]{0,12}?(\d+(?:\.\d+)?)%"),
    "take_profit_pct": ("익절", r"(?:익절|목표수익|수익실현)[^,.%]{0,12}?(\d+(?:\.\d+)?)%"),
}


def expected_scalar_values(prompt: str) -> list[tuple[str, str, Any]]:
    """QA 기대값: 프롬프트가 명시한 스칼라 설정 [(라벨, parsed 키, 기대값)].

    결정적 추출기가 이미 있는 항목은 그대로 쓴다(`engine.nl_parser`) — 이 추출기들은
    파스 경로에서 기본 off인 보정 계층(FR-STR-019j)이라 프로덕션 해석에는 관여하지
    않으며, 여기서는 **검사 쪽 정본**으로만 쓴다(`expected_etf_theme`과 같은 자리).

    값이 없으면(None/none) 목록에 넣지 않는다 — '말하지 않은 값'의 판정은 되묻기 레인
    소관이고, 여기서 기본값을 기대값으로 세우면 정상 되묻기가 실패로 잡힌다.
    """
    from engine import nl_parser as nlp

    compact = nlp._compact(prompt)
    out: list[tuple[str, str, Any]] = []

    hold = nlp._extract_hold_period_days(prompt)
    if hold is not None:
        out.append(("보유기간", "hold_period_days", hold))
    # 종목수는 여기서 다루지 않는다 — 기존 `intended_positions` 검사가 이미 값을 대조하며
    # (경고 등급: 기본값 폴백 의심과 한 버킷), 여기서 또 세면 같은 결손이 두 번 보고된다.
    rebal = nlp._extract_rebalancing_period(prompt, hold)
    if rebal != "none":
        out.append(("리밸런싱", "rebalancing_period", rebal))
    period = nlp._extract_backtest_period(prompt)
    if period is not None:
        out.append(("백테스트기간", "backtest_period", period))
    trailing = nlp._extract_trailing_stop_pct(prompt)
    if trailing is not None:
        out.append(("트레일링스탑", "trailing_stop_pct", trailing))
    mdd = nlp._extract_max_mdd_limit_pct(prompt)
    if mdd is not None:
        out.append(("MDD한도", "max_mdd_limit_pct", mdd))
    capital = nlp._extract_capital_amount(prompt)
    if capital is not None:
        out.append(("초기자본", "initial_capital", capital))

    for key, (label, pattern) in _RISK_PCT_PATTERNS.items():
        m = re.search(pattern, compact)
        if m:
            out.append((label, key, float(m.group(1))))
    return out


# 신호 파라미터가 담기는 칸(지표마다 다르다).
_SIGNAL_PARAM_KEYS = ("short_period", "long_period", "period", "lookback_period", "value")

# 신호 수치는 **지표에 귀속시키지 않고** 단위 어휘에 바로 붙은 숫자만 읽는다.
# 이유: 한 문장에 지표가 둘 이상이면("거래량이 크게 늘고 5일선이 20일선 위에")
# 지표별 추출기가 옆 지표의 숫자를 집어 온다(실측 오탐 — nl_parser._extract_technical_signals
# 가 volume_spike.period=5를 냈다). 하니스 초판이 값 대조를 통째로 걷어낸 이유가 이것이므로,
# 여기서는 **누가 쓰는 숫자인지 판정하지 않고** '이 숫자가 신호 어딘가에 쓰였는가'만 본다.
_MA_PERIOD_RE = re.compile(r"(\d+)일(?:선|이평선?|이동평균선?|ema|지수이동평균)")
_BREAKOUT_RE = re.compile(r"(\d+)일[^,.]{0,4}(?:신고가|신저가|박스권)")
# '20일 평균 거래대금 30억 이상'의 20일은 대조 대상이 **아니다** — 그 창은 지표 정의
# (fundamental.trading_value=일평균거래대금)에 내장돼 있어 파싱 결과에 담길 칸이 없다.
# 규칙으로 넣었다가 예시 3건이 정상인데도 붉어졌다(2026-08-18 실측). 거래량 급증의
# 기간도 마찬가지로 사용자가 창을 지정하는 자리가 아니므로 대조하지 않는다.
_OSC_THRESHOLD_RES = {
    "rsi": re.compile(r"rsi[^,.]{0,8}?(\d+(?:\.\d+)?)"),
    "cci": re.compile(r"cci[^,.]{0,8}?[+-]?(\d+(?:\.\d+)?)"),
    "adx": re.compile(r"adx[^,.]{0,8}?(\d+(?:\.\d+)?)"),
}


def expected_signal_numbers(prompt: str) -> list[tuple[str, list[float]]]:
    """QA 기대값: 신호에 반드시 남아야 하는 수치 [(라벨, [값…])].

    단위 어휘에 붙은 숫자만 읽고(20일선·20일 신고가·30일 평균 거래대금·RSI 30), 그 숫자가
    **파싱된 신호의 기간·임계값 칸 어딘가에** 남았는지만 확인한다(포함 대조). 어느 지표의
    어느 칸인지는 묻지 않는다 — 그 귀속 판정이 오탐의 근원이고, 조용한 소실을 잡는 데는
    포함 여부로 충분하다("20일 EMA가 60일 EMA 위"에서 60이 사라지면 걸린다).
    """
    from engine.nl_parser import _compact

    compact = _compact(prompt)
    out: list[tuple[str, list[float]]] = []
    ma = sorted({float(x) for x in _MA_PERIOD_RE.findall(compact)})
    if ma:
        out.append(("이동평균 기간", ma))
    bo = sorted({float(x) for x in _BREAKOUT_RE.findall(compact)})
    if bo:
        out.append(("신고가 룩백", bo))
    for name, rx in _OSC_THRESHOLD_RES.items():
        found = sorted({float(x) for x in rx.findall(compact)})
        if found:
            out.append((f"{name.upper()} 기준값", found))
    return out


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
    # 이동평균/EMA 상하 관계('20일선 위에 있는', '5일 EMA가 20일 EMA 위')는 crossover 표기로
    # 반영돼야 한다. 2026-07-27: 이 검사가 없어 4개 예시가 조건을 잃은 채 통과했다
    # (기준값 되묻기로 조건 드롭 — 인터프리터가 value 요구 연산자를 쓴 드리프트).
    ("이동평균", r"이동평균선|\d+일선", lambda p: _has_any(p, ["ma_crossover", "ema"])),
    ("EMA", r"EMA", lambda p: _has_any(p, ["ema", "ma_crossover"])),
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
    # 예시가 아예 전략이 되지 못한 경우 — 리포트가 아니라 실패로 다뤄야 하는 항목.
    fatal: list[str] = field(default_factory=list)
    # 프롬프트에 있는데 전략 어디에도 나타나지 않은 수치(위 값 대조의 그물 밖 catch-all).
    unmatched: list[str] = field(default_factory=list)


def unmatched_numbers(prompt: str, p: dict, asked: str) -> list[str]:
    """프롬프트의 수치 중 파싱 결과 **어디에도** 나타나지 않은 것.

    ①~③ 값 대조는 '기대값을 뽑을 수 있는 필드'만 본다 — 추출기가 다루지 않는 표현
    (AI 확률 임계·분위 그룹·비중 등)은 그물 밖이다. 이 층은 필드를 묻지 않고 **숫자가
    전략 어딘가에 남았는지**만 확인해, 어느 그물에도 안 걸리는 값이 없게 한다.
    단위 환산은 대조 쪽이 흡수한다(조→억원, 개월→거래일 등 — `_candidates`).

    되묻는 중이거나 안내한 수치는 조용한 소실이 아니므로 제외한다(`asked_about`과 같은
    계약). 서수·횟수('월 1회'의 1)는 값이 아니라 표현이라 남지 않는 것이 정상이므로,
    이 층은 **참고 표시**로만 쓰고 게이트를 붉히지 않는다.
    """
    from strategy_conversation.validation.recall_validator import (
        input_number_labels,
        labels_absent_from,
    )

    labels = [x for x in input_number_labels(prompt) if x not in asked]
    return labels_absent_from(labels, p)


def asked_about(res: dict) -> str:
    """이번 턴에 에이전트가 되묻거나 **알린** 내용을 한 덩어리 텍스트로 모은다.

    값이 빠진 팩터를 되묻는 것은 전략 에이전트의 정상 동작이다 — 사용자가 말하지 않은
    값을 질문 없이 기본값으로 확정하지 않는다는 계약(CLAUDE.md)의 실행이다. 따라서
    '되묻고 있는 팩터'는 소실도, 빈 전략도 아니므로 실패로 세지 않는다. 이 하니스가
    잡아야 하는 것은 **조용한** 소실(질문도 없이 조건이 사라진 경우)이다.

    안내(notices)도 같은 이유로 포함한다 — 근사 반영·미반영을 사용자에게 알린 조건은
    조용히 사라진 것이 아니다(2026-08-14: '거래대금이 30일 평균보다 높은'을 거래량 급증
    조건으로 반영하며 안내를 냈는데도 미탐지로 세던 오탐). 백엔드 본경로가 제외 조건의
    '설명됨' 판정에 notices를 쓰는 것과 같은 계약이다(primary.unexplained_drops).
    """
    parts = [str(res.get("clarification_question") or "")]
    parts += [str(s) for s in (res.get("clarification_suggestions") or [])]
    parts += [str(n) for n in (res.get("notices") or [])]
    # 값-대기 큐(pending_conditions)에 오른 조건은 순차 되묻기 대상이다 — 이번 턴 질문에
    # 아직 안 나왔어도 소실이 아니다(값-대기 조건 채널: parsed에 없고 pending이 유일 근거).
    # source_text가 사용자 원문 그대로라 COVERAGE_CHECKS 패턴이 그대로 맞는다.
    for pc in res.get("pending_conditions") or []:
        parts += [str(pc.get("label") or ""), str(pc.get("source_text") or "")]
    return " ".join(parts)


def analyze(tpl: Template, res: dict) -> Flags:
    f = Flags()
    p = res.get("parsed", {})
    prompt = tpl.prompt
    asked = asked_about(res)

    # ── 치명 항목: 해석 실패·유니버스 오류·진입 규칙 공백
    # 2026-07-27 사고: '반도체 업종 ROE·부채비율+모멘텀' 예시가 interpretation_failed로
    # 끝나 빈 전략(KOSPI200 기본값)이 나갔는데도 리포트상 '되물음' 참고 표시뿐이었다.
    if res.get("clarification_priority") == "interpretation_failed":
        f.fatal.append("해석 실패(빈 전략)")
    if tpl.category == "ETF":
        if p.get("universe") != ["ETF"]:
            f.fatal.append(f"ETF 유니버스 아님({p.get('universe')})")
        # ETF엔 기업 재무제표가 없다(universe_capabilities) — 조건이 붙으면 예시가 잘못됐다.
        # trading_value는 가격·거래량 파생이라 ETF에서도 허용되므로 제외한다.
        etf_illegal = [x.get("metric") for x in p.get("fundamental_filters", [])
                       if x.get("metric") != "trading_value"]
        if etf_illegal:
            f.fatal.append(f"ETF에 재무 조건({','.join(etf_illegal)})")
        # 테마·상품명을 잃으면 전체 ETF(1,300여 종목) 전략으로 왜곡된다. 기대값은 ETF 마스터
        # 자기검증 추출기(정본)로 얻는다 — QA 대조용 ground truth, 파스 경로가 아니다.
        expected_theme = expected_etf_theme(prompt)
        if expected_theme and not p.get("etf_theme"):
            f.fatal.append(f"ETF 테마 소실(기대 '{expected_theme}')")
    if tpl.category == "테마" and not p.get("sector") and not p.get("target_symbols"):
        f.fatal.append("업종/테마 미반영")
    # 명시적 청산 규칙('N일선 이탈 시 청산', '데드크로스면 매도')은 신호로 남아야 한다 —
    # 손절·보유기간만 남으면 전략의 성격이 바뀐다(2026-07-27 실측: 예시 3의 청산 소실).
    if re.search(r"(이탈|아래로 내려|데드크로스|하단에 닿|중심선 재이탈)[^.]{0,12}"
                 r"(청산|매도|정리)", prompt) and not p.get("exit_signals"):
        f.fatal.append("명시 청산 규칙 소실")

    # 미탐지 판정에서 '되묻고 있는 팩터'는 제외한다 — 값 없이 언급된 조건('부채비율과 ROE
    # 조건을 충족하는 종목')을 되묻는 것은 정상 동작이지 소실이 아니다.
    for name, pat, check in COVERAGE_CHECKS:
        if re.search(pat, prompt) and not check(p) and not re.search(pat, asked):
            f.missing.append(name)

    # ── 값 대조: "있는지"가 아니라 "얼마인지"를 본다 ────────────────────────────
    # 위 커버리지 검사는 `_has_fund`/`_has_sig`로 **지표 존재만** 본다. 2026-08-18 사고
    # ("시가총액 1조"→100000억=10조)가 08-14 전수 검증을 치명 0으로 통과한 자리이며,
    # 자릿수 오차는 금액만의 문제가 아니라 모든 임계값·설정에서 같은 모양으로 난다.
    # 세 층 모두 **반영된 경우에만** 값을 본다 — 부재·값대기·되묻기는 위 미탐지 레인
    # 소관이고, 두 레인이 같은 결손을 세면 되묻기 예외가 무력해진다.
    unit = lambda m: "억" if m in AMOUNT_METRIC_LABELS else ""  # noqa: E731

    # ① 재무 임계값(금액·비율 전부)
    for metric, want in expected_fundamental_thresholds(prompt):
        got = [x.get("value") for x in p.get("fundamental_filters", []) if x.get("metric") == metric]
        got = [float(g) for g in got if isinstance(g, (int, float)) and not isinstance(g, bool)]
        if not got:
            continue
        if not any(abs(g - want) < 1e-6 for g in got):
            label = FUND_METRIC_LABELS.get(metric, metric)
            f.fatal.append(f"{label} 임계값 오차(기대 {want:g}{unit(metric)} vs 파싱 "
                           f"{','.join(f'{g:g}' for g in got)}{unit(metric)})")

    # ② 스칼라 설정(손절·익절·종목수·리밸런싱·보유기간·기간·자본·트레일링·MDD)
    for label, key, want in expected_scalar_values(prompt):
        got = p.get(key)
        if got is None:
            continue
        if isinstance(want, (int, float)) and isinstance(got, (int, float)):
            if abs(float(got) - float(want)) < 1e-6:
                continue
            f.fatal.append(f"{label} 값 오차(기대 {want:g} vs 파싱 {float(got):g})")
        elif str(got) != str(want):
            f.fatal.append(f"{label} 값 오차(기대 {want} vs 파싱 {got})")

    # ③ 신호 수치(이동평균 기간·신고가 룩백·거래량 평균 기간·오실레이터 기준값)
    signals = (p.get("entry_signals") or []) + (p.get("exit_signals") or [])
    if signals:
        used = {float(v) for s in signals for k in _SIGNAL_PARAM_KEYS
                if isinstance((v := s.get(k)), (int, float)) and not isinstance(v, bool)}
        for label, wants in expected_signal_numbers(prompt):
            lost = [w for w in wants if not any(abs(u - w) < 1e-6 for u in used)]
            if lost:
                f.fatal.append(f"{label} 소실(말한 값 {','.join(f'{w:g}' for w in lost)}이 "
                               f"신호 어디에도 없음 — 파싱 {sorted(used)})")

    for name, field_name, pat in RISK_KEYWORDS:
        if re.search(pat, prompt) and p.get(field_name) is None and not re.search(pat, asked):
            f.missing.append(name)

    if (re.search(REBAL_WORDS, prompt) and p.get("rebalancing_period") in (None, "none")
            and not re.search(REBAL_WORDS, asked)):
        f.missing.append("리밸런싱")

    want = intended_positions(prompt)
    got = p.get("max_positions")
    if want is not None and got is not None and want != got:
        f.position = f"종목수: 프롬프트 {want} vs 파싱 {got}"
    elif got == 100 and not re.search(r"100\s*종목", prompt):
        # 명시 없이 100이면 기본값 폴백(미반영) 의심
        f.position = "종목수: 파싱 100(기본값 폴백 의심)"

    # 진입 규칙 공백은 **되묻지도 않고** 비어 있을 때만 치명이다. 값 없이 언급된 조건을
    # 되묻는 중이면 전략은 아직 완성 전일 뿐 조용히 빈 전략으로 나가는 게 아니다
    # (해석 실패로 빈 전략이 나가는 경우는 위 clarification_priority 검사가 잡는다).
    if (not p.get("fundamental_filters") and not p.get("entry_signals")
            and not p.get("ranking_metric") and not asked):
        f.fatal.append("진입 규칙 없음(되묻기도 없음)")
    f.unmatched = unmatched_numbers(prompt, p, asked)
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
    if p.get("etf_theme"):
        parts.append(f"ETF테마={p['etf_theme']}")
    if p.get("sector"):
        parts.append(f"업종={p['sector']}")
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
    ap.add_argument("--category", default=None,
                    help="카테고리 필터(콤마 구분). 예: --category ETF,테마")
    ap.add_argument("--refresh", action="store_true",
                    help="캐시를 무시하고 다시 파싱한다(파서 수정 후 재검증용)")
    args = ap.parse_args()

    templates = load_templates()
    if args.category:
        wanted = {c.strip() for c in args.category.split(",") if c.strip()}
        templates = [t for t in templates if t.category in wanted]
    cache: dict[str, dict] = {}
    if RAW_CACHE.exists():
        cache = json.loads(RAW_CACHE.read_text())

    lines = ["# 전략 템플릿 파싱 검출 리포트 (정제판)\n", f"- 대상: {len(templates)}개\n"]
    problems: list[str] = []
    n_missing = n_pos = n_fatal = n_unmatched = 0

    for i, tpl in enumerate(templates, 1):
        if tpl.prompt in cache and not args.refresh:
            res = cache[tpl.prompt]
        elif args.use_cache:
            print(f"[{i}] 캐시 없음, 건너뜀", file=sys.stderr)
            continue
        else:
            try:
                res = parse_strategy(tpl.prompt)
            except Exception as e:
                # 호출 자체가 죽으면(백엔드 미기동·포트 선점 501 등) 검증이 성립하지 않는다 —
                # 치명으로 세워 게이트를 붉게 만든다(2026-08-14: 81건 전부 501인데 exit 0으로 통과).
                n_fatal += 1
                lines.append(f"\n## {i}. {tpl.title}\n- ❌ 파싱 오류: {e}")
                problems.append(f"{i}. {tpl.title} — 치명[파싱 호출 실패: {e}]")
                continue
            cache[tpl.prompt] = res
            RAW_CACHE.write_text(json.dumps(cache, ensure_ascii=False))
        print(f"[{i}/{len(templates)}] {tpl.title}", file=sys.stderr)

        p = res.get("parsed", {})
        f = analyze(tpl, res)
        lines.append(f"\n## {i}. [{tpl.category}/{tpl.level}] {tpl.title}\n")
        lines.append(f"> {tpl.prompt}\n")
        lines.append(f"- **요약**: {summarize(p)}")
        if f.fatal:
            n_fatal += 1
            lines.append(f"- ❌ **치명**: {', '.join(f.fatal)}")
        if f.missing:
            n_missing += 1
            lines.append(f"- ⚠️ **미탐지**: {', '.join(f.missing)}")
        if f.position:
            n_pos += 1
            lines.append(f"- ⚠️ **{f.position}**")
        if f.unmatched:
            n_unmatched += 1
            lines.append(f"- ℹ️ 미대조 수치(전략 어디에도 없음): {', '.join(f.unmatched)}")
        for note in f.notes:
            lines.append(f"- ℹ️ {note}")
        tag = []
        if f.fatal:
            tag.append(f"치명[{','.join(f.fatal)}]")
        if f.missing:
            tag.append(f"미탐지[{','.join(f.missing)}]")
        if f.position:
            tag.append(f.position)
        if tag:
            problems.append(f"{i}. {tpl.title} — {' / '.join(tag)}")

    lines += ["\n---\n## 종합\n", f"- 치명(예시가 전략이 되지 못함): **{n_fatal}개**",
              f"- 미탐지 표현: **{n_missing}개**", f"- 종목수 이슈: **{n_pos}개**",
              f"- 미대조 수치(참고): **{n_unmatched}개**\n",
              "### 점검 필요\n", *problems]
    report = "\n".join(lines)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"저장: {args.out}", file=sys.stderr)
    else:
        print(report)
    print(f"\n=== 치명 {n_fatal} · 미탐지 {n_missing} · 종목수 {n_pos} · 미대조 {n_unmatched} ===",
          file=sys.stderr)
    # 치명 항목은 게이트로 다룬다 — 예시 추가·파서 수정 후 이 스크립트가 0으로 끝나야 한다.
    return 1 if n_fatal else 0


if __name__ == "__main__":
    raise SystemExit(main())
