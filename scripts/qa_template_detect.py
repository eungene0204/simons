"""한국어 전략 예시의 파싱 결과를 사람이 작성한 의미 기대값과 대조한다.

예시 원문을 정규식으로 읽어 기대값을 만들지 않는다. 예시가 수정되면
`qa_template_expectations.json`의 기대값과 원문 해시를 함께 검토해야 한다.

repo 루트에 둔다(uvicorn --reload-dir backend 감시 대상이 아니므로 편집해도 파스
캐시가 날아가지 않는다). 코칭은 호출하지 않는다(초판에서 코칭 문제 0건).

실행: python scripts/qa_template_detect.py [--out docs/template_detect_report.md]
      python scripts/qa_template_detect.py --category ETF,테마 --refresh   # 예시 추가 후 검증
미국 예시 정답표는 아직 작성되지 않아 `--source us` 실행은 명시 중단한다.

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
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import urllib.request

# 기본은 로컬 개발 백엔드. 8000이 다른 앱에 점유된 환경에서는 QA_BACKEND로 바꿔 띄운다
# (예: QA_BACKEND=http://localhost:8010).
BACKEND = os.environ.get("QA_BACKEND", "http://localhost:8000")
# 테마 예시는 KG 전개가 붙어 180초를 넘길 수 있다 — 필요 시 QA_TIMEOUT으로 상향.
TIMEOUT = int(os.environ.get("QA_TIMEOUT", "180"))
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))


TSX_PATH = ROOT / "components/strategy/StrategyExampleTabs.tsx"
RAW_CACHE = ROOT / "scripts/.template_parse_cache.json"
EXPECTATIONS_PATH = ROOT / "scripts/qa_template_expectations.json"
KR_EXPECTATIONS: dict[str, dict] = json.loads(EXPECTATIONS_PATH.read_text(encoding="utf-8"))


@dataclass
class Template:
    level: str
    category: str
    title: str
    prompt: str
    # 파서에 실제로 보내는 텍스트. 기본은 prompt(한국어 원문)와 같고, --lang en이면
    # en.ts 번역이 실린다 — /us는 t(example.prompt)를 전송하므로(StrategyExampleTabs:597)
    # 번역이 곧 파서 입력이다. 판정 기대값은 사람이 작성한 예시별 데이터다.
    input: str = ""
    expect: dict = field(default_factory=dict)

    def parse_input(self) -> str:
        return self.input or self.prompt


# 예시 소스 — kr: 한국 예시(StrategyExampleTabs), us: 미국 예시(usExamples, US 레인 Phase 4)
_SOURCES = {
    "kr": (TSX_PATH, "export const EXAMPLES"),
    "us": (ROOT / "components/strategy/usExamples.ts", "export const US_EXAMPLES"),
}

# 판정에 쓰는 현재 소스(main이 설정) — 미국 예시는 ETF=티커 지정 계약, 달러 금액 등
# 한국 전제 판정이 오탐을 낸다(2026-08-25 실측: ETF 유니버스 18건·초기자본 3건 오탐).
SOURCE = "kr"
# 파서 입력 언어(main이 설정). "en"이면 되묻기·안내(asked)가 영어로 오므로
# asked 대조는 대소문자 무시로 한다(한국어 판정은 영향 없음 — 지표명만 라틴 문자).
LANG = "kr"

_US_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")

EN_TS_PATH = ROOT / "lib/i18n/en.ts"


def load_en_map() -> dict[str, str]:
    """lib/i18n/en.ts의 한국어 원문→영어 사전을 읽는다(키·값 모두 이중따옴표 리터럴)."""
    text = EN_TS_PATH.read_text(encoding="utf-8")
    pair_re = re.compile(
        r'^\s*"(?P<key>(?:[^"\\]|\\.)*)":\s*"(?P<val>(?:[^"\\]|\\.)*)",?\s*$', re.MULTILINE
    )
    unescape = lambda s: s.replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")  # noqa: E731
    return {unescape(m.group("key")): unescape(m.group("val")) for m in pair_re.finditer(text)}


def load_templates(source: str = "kr", lang: str = "kr") -> list[Template]:
    path, anchor = _SOURCES[source]
    text = path.read_text(encoding="utf-8")
    start = text.index(anchor)
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
        title = m.group("title")
        expectation = KR_EXPECTATIONS.get(title) if source == "kr" else None
        if source == "kr" and expectation is None:
            raise ValueError(f"한국어 예시 기대값이 없습니다: {title}")
        if source == "kr" and expectation.get("prompt_sha256") != hashlib.sha256(
            prompt.encode("utf-8")
        ).hexdigest():
            raise ValueError(f"한국어 예시 원문 변경 — 기대값 재검토 필요: {title}")
        out.append(Template(m.group("level"), m.group("category"), title, prompt,
                            expect=expectation or {}))
    if source == "kr":
        stale = KR_EXPECTATIONS.keys() - {t.title for t in out}
        if stale:
            raise ValueError(f"사라진 예시의 기대값이 남았습니다: {sorted(stale)}")
    if lang == "en":
        # en.ts 번역이 파서 입력이다. 누락이면 t()가 한국어 원문을 그대로 보내므로
        # 이 게이트는 영어를 검증하지 못한다 — 조용히 폴백하지 않고 즉시 실패한다
        # (i18n 커버리지 게이트와 같은 계약, Fail Fast).
        en_map = load_en_map()
        missing = [t.title for t in out if t.prompt not in en_map]
        if missing:
            raise SystemExit(
                f"en.ts에 번역 없는 예시 {len(missing)}개 — 파서 입력이 성립하지 않음: "
                + ", ".join(missing)
            )
        for t in out:
            t.input = en_map[t.prompt]
    return out


def parse_strategy(prompt: str) -> dict:
    # dev/배포 기본값은 ollama. mlx는 로컬 dev에 모델이 로드돼 있지 않아 503이 난다.
    # **지역 신호**(2026-08-27): /us는 지역이 곧 표시 언어다(lib/geo/region → 프록시가
    # X-UI-Language를 실어 보내고 백엔드가 요청 컨텍스트에 묶는다). 이걸 안 실으면
    # 백엔드는 한국 요청으로 응대한다 — 지역 격리 가드가 발동하지 않고 시장 미언급의
    # 기본 유니버스가 한국 기본값(KOSPI200)이 된다(실측: /us ETF 예시가 KOSPI200으로
    # 파스). 아래 asked 대조가 "--lang en에서는 영어로 온다"를 전제하고 있었는데
    # 전송이 빠져 있어 하니스가 스스로와 어긋나 있었다.
    # 지역 신호는 **입력 언어가 아니라 예시의 소속**을 따른다(2026-09-21): KR 레인은
    # 한국 시장 전용이라 미국 시장 요청을 거절한다(primary._kr_region_us_market_refusal).
    # `--source us`를 한국어 원문으로 돌릴 때 지역 신호를 빼면 미국 예시 100건이 전부
    # 그 거절에 걸려, 한국어 원문 게이트가 파싱 품질을 못 본다.
    body = {"prompt": prompt, "backend": "ollama"}
    if LANG == "en" or SOURCE == "us":
        body["language"] = "en"
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BACKEND}/strategy/parse", data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


# ── 검출 술어 ────────────────────────────────────────────────────────────
def _has_fund(p: dict, metric: str) -> bool:
    return any(f.get("metric") == metric for f in p.get("fundamental_filters", []))


def _has_rank(p: dict, metric: str) -> bool:
    """랭킹 축에 그 지표가 쓰였는가 — 재무 **필터**와 다른 자리다(FR-STR-074 축 구분).

    "시총 상위 10종목"은 필터가 아니라 **정렬 기준**이라 ranking_metric/ranking으로
    착지한다. 필터만 보면 정상 반영된 전략이 '미탐지'로 잡힌다(2026-08-27 실측 #5:
    ranking_metric=market_cap으로 반영됐는데 시가총액 미탐지로 보고됐다)."""
    if p.get("ranking_metric") == metric:
        return True
    return any(r.get("metric") == metric for r in p.get("ranking") or []
               if isinstance(r, dict))


def _has_sig(p: dict, ind: str) -> bool:
    return any(s.get("indicator") == ind for s in p.get("entry_signals", []) + p.get("exit_signals", []))


def _has_any(p: dict, inds: list[str]) -> bool:
    return any(_has_sig(p, i) for i in inds)


def duplicated_conditions(items: list[dict]) -> list[str]:
    """한 목록 안에서 **모든 필드가 같은** 조건이 반복되면 그 조건의 표기를 돌려준다.

    None 필드는 없는 것으로 보고 비교한다(파스 결과 직렬화가 빈 필드를 null로 채운다).
    지표·기간·연산자·값이 하나라도 다르면 다른 조건이다(EMA 5/20과 20/60은 둘 다 정당).
    """
    seen: set[str] = set()
    dups: list[str] = []
    for item in items:
        key = json.dumps({k: v for k, v in item.items() if v is not None},
                         sort_keys=True, ensure_ascii=False)
        if key in seen:
            name = item.get("indicator") or item.get("metric") or "?"
            if name not in dups:
                dups.append(name)
        seen.add(key)
    return dups


# These patterns inspect only generated questions and notices, never example input.
COVERAGE_CHECKS: list[tuple[str, str, Any]] = [
    ("PBR", r"PBR|P/B", lambda p: _has_fund(p, "pbr")),
    ("PER", r"PER|P/E", lambda p: _has_fund(p, "per")),
    ("ROE", r"ROE", lambda p: _has_fund(p, "roe_or_gpa")),
    ("부채비율", r"부채비율|debt", lambda p: _has_fund(p, "debt_ratio")),
    ("시가총액", r"시가총액|시총|market\s*cap",
     lambda p: _has_fund(p, "market_cap") or _has_rank(p, "market_cap")),
    ("거래대금", r"거래대금|trading\s*value|dollar\s*volume|turnover",
     lambda p: _has_fund(p, "trading_value") or _has_sig(p, "trading_value")
     or _has_sig(p, "trading_value_ratio") or _has_rank(p, "trading_value")),
    # 이동평균/EMA 상하 관계('20일선 위에 있는', '5일 EMA가 20일 EMA 위')는 crossover 표기로
    # 반영돼야 한다. 2026-07-27: 이 검사가 없어 4개 예시가 조건을 잃은 채 통과했다
    # (기준값 되묻기로 조건 드롭 — 인터프리터가 value 요구 연산자를 쓴 드리프트).
    ("이동평균", r"이동평균선|\d+일선|moving\s*average|\d+[- ]?day\s*(?:MA|SMA|line|average)",
     lambda p: _has_any(p, ["ma_crossover", "ema"])),
    ("EMA", r"EMA|exponential\s*moving", lambda p: _has_any(p, ["ema", "ma_crossover"])),
    ("RSI", r"RSI", lambda p: _has_sig(p, "rsi")),
    ("MACD", r"MACD", lambda p: _has_sig(p, "macd")),
    ("볼린저", r"볼린저|Bollinger", lambda p: _has_sig(p, "bollinger_bands")),
    ("ADX", r"ADX", lambda p: _has_sig(p, "adx")),
    ("스토캐스틱", r"스토캐스틱|Stochastic", lambda p: _has_sig(p, "stochastic")),
    ("CCI", r"CCI", lambda p: _has_sig(p, "cci")),
    # 신고가/박스권만 breakout으로 본다(EMA/볼린저 '상향 돌파'와 구분).
    ("신고가돌파", r"신고가|박스권|new\s+high|\d+[- ]?day\s+high|box\s*range|breakout",
     lambda p: _has_sig(p, "breakout")),
    ("거래량", r"거래량|volume",
     lambda p: _has_any(p, ["volume_spike", "volume_ratio"]) or _has_fund(p, "trading_value")),
    ("랭킹", r"순위|수익률|상대강도|ranking|return", lambda p: bool(p.get("ranking_metric") or p.get("ranking"))),
]

_COVERAGE_BY_NAME = {name: (pattern, check) for name, pattern, check in COVERAGE_CHECKS}
_FUND_METRIC_LABELS = {
    "pbr": "PBR", "per": "PER", "roe_or_gpa": "ROE", "debt_ratio": "부채비율",
    "market_cap": "시가총액", "trading_value": "거래대금",
}
_SCALAR_LABELS = {
    "hold_period_days": "보유기간", "rebalancing_period": "리밸런싱",
    "stop_loss_pct": "손절", "take_profit_pct": "익절",
}
_SIGNAL_PARAM_KEYS = ("short_period", "long_period", "period", "lookback_period", "value")


@dataclass
class Flags:
    missing: list[str] = field(default_factory=list)
    position: Optional[str] = None
    notes: list[str] = field(default_factory=list)
    # 예시가 아예 전략이 되지 못한 경우 — 리포트가 아니라 실패로 다뤄야 하는 항목.
    fatal: list[str] = field(default_factory=list)
    # 프롬프트에 있는데 전략 어디에도 나타나지 않은 수치(위 값 대조의 그물 밖 catch-all).
    unmatched: list[str] = field(default_factory=list)


def unmatched_numbers(expect: dict, p: dict, asked: str) -> list[str]:
    """Compare only human-authored numeric expectations with the parsed result."""
    from strategy_conversation.validation.recall_validator import labels_absent_from

    values = [v for numbers in expect.get("fundamental", {}).values() for v in numbers]
    values += [v for v in expect.get("scalar", {}).values() if isinstance(v, (int, float))]
    values += [v for numbers in expect.get("signal_numbers", {}).values() for v in numbers]
    values += list(expect.get("other_numbers", []))
    if expect.get("positions") is not None:
        values.append(expect["positions"])
    labels = [str(v) for v in values if str(v) not in asked]
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
    # A pending label is interpreter output; its source_text is the original input.
    for pc in res.get("pending_conditions") or []:
        parts.append(str(pc.get("label") or ""))
    return " ".join(parts)


# 백엔드 잔여 미지원 안내의 정본 문구(primary.py leftover_features) — 한/영 두 판.
_UNSUPPORTED_NOTICE_RE = re.compile(
    r"지원하지 않아 전략에 반영하지 못했어요"
    # 컴파일 불가 탈락 안내(primary.py uncompilable_drops) — 조건이 통째로 빠진 것.
    r"|조건은 전략에 반영하지 못했어요"
    r"|not supported, so it was not reflected"
    r"|not supported and were not reflected"
)


# 볼린저 예시별 기대 신호 — 사람이 정한 정답표(예시 제목 키, 원문을 해석하지 않는다).
# 커버리지 검사(`_has_sig`)는 볼린저가 **있는지**만 봐서, '상단 돌파 매수·하단 닿으면 청산'이
# 하단 매수·상단 청산으로 정반대 컴파일돼도 통과했다(2026-10-10). 항목은 (역할, 밴드, 교차 방향,
# 하단 터치 이력 여부)이며 밴드가 None이면 역할 고정 레거시다. 되묻는 중(값 대기)인 신호는 제외한다.
BOLLINGER_EXPECTED: dict[str, set[tuple[str, Optional[str], Optional[str], bool]]] = {
    "볼린저밴드 상단 돌파 + 거래량 확인": {("entry", "upper", "above", False), ("exit", "lower", "below", False)},
    "볼린저 하단 반등 스윙": {("entry", "middle", "above", True), ("exit", "upper", "above", False)},
    "볼린저 상단 돌파 거래량 확인": {("entry", "upper", "above", False), ("exit", "lower", "below", False)},
    "나스닥 볼린저 하단 반등": {("entry", "lower", "above", False)},
    "다우 볼린저 상단 돌파 추세": {("entry", "upper", "above", False)},
    "다우 저PBR 볼린저 반등": {("entry", "lower", "above", False)},
    "반도체 ETF 볼린저 반등 역추세": {("entry", "lower", "above", False), ("exit", "upper", "above", False)},
}


def bollinger_mismatches(title: str, p: dict, asked: str) -> list[str]:
    """정답표가 있는 예시의 볼린저 신호가 기대와 다르면 그 차이를 돌려준다."""
    want = BOLLINGER_EXPECTED.get(title)
    if want is None:
        return []
    got = {
        (role, s.get("band"), s.get("cross"), bool(s.get("touch_lookback")))
        for role, key in (("entry", "entry_signals"), ("exit", "exit_signals"))
        for s in (p.get(key) or []) if s.get("indicator") == "bollinger_bands"
    }
    # 하단 터치 인정 기간을 되묻는 중이면 그 신호는 값 대기라 parsed에 없다 — 소실이 아니다.
    waiting = "하단 터치" in asked or "lower-band touch" in asked
    missing = [w for w in want if w not in got and not (w[3] and waiting)]
    extra = [g for g in got if g not in want]
    out = []
    if missing:
        out.append(f"볼린저 기대 신호 없음({sorted(missing, key=str)})")
    if extra:
        out.append(f"볼린저 기대 밖 신호({sorted(extra, key=str)})")
    return out


def analyze(tpl: Template, res: dict) -> Flags:
    f = Flags()
    p = res.get("parsed", {})
    expect = tpl.expect
    if not expect:
        raise ValueError(f"예시 기대값이 없습니다: {tpl.title}")
    asked = asked_about(res)
    # asked(되묻기·안내·pending source_text) 대조 — 미국 예시는 입력 언어와 무관하게
    # 지역 신호(en)를 싣고 돌리므로(parse_strategy) 영어로 올 수 있다. 대소문자를
    # 무시한다("stop loss"·"p/e"). 기대 항목은 고정 정답표에서 읽는다.
    asked_has = lambda pat: re.search(  # noqa: E731
        pat, asked, re.IGNORECASE if (LANG == "en" or SOURCE == "us") else 0)

    # ── 치명 항목: 해석 실패·유니버스 오류·진입 규칙 공백
    # 2026-07-27 사고: '반도체 업종 ROE·부채비율+모멘텀' 예시가 interpretation_failed로
    # 끝나 빈 전략(KOSPI200 기본값)이 나갔는데도 리포트상 '되물음' 참고 표시뿐이었다.
    if res.get("clarification_priority") == "interpretation_failed":
        f.fatal.append("해석 실패(빈 전략)")
    # 미지원 안내("'X' 조건은 지원하지 않아 전략에 반영하지 못했어요")는 사용자 화면에서
    # '전략을 이해하지 못했다'로 읽힌다. 우리가 내보내는 예시가 이 안내를 내면 예시가 엔진
    # 밖 개념을 약속했거나 파서가 지원 개념을 미지원으로 오판한 것이다 — 어느 쪽이든
    # 결함이라 치명으로 센다(2026-09-14: "KOSPI 중형주" 예시가 "섹터 '중형주' 미지원"
    # 안내를 내는데도 '안내됨=조용한 소실 아님'으로만 처리돼 게이트가 초록이었다).
    # 근사 반영 안내("…(으)로 가깝게 반영했어요")는 조건이 전략에 남으므로 여기 들지 않는다.
    # 판정 입력은 백엔드가 만든 안내 문구(정본 템플릿)이지 사용자 원문이 아니다.
    for notice in res.get("notices") or []:
        if _UNSUPPORTED_NOTICE_RE.search(str(notice)):
            f.fatal.append(f"미지원 안내({str(notice).strip()})")
    if tpl.category == "ETF":
        if SOURCE == "us":
            # 미국 ETF 예시의 계약: 상품 **티커 지정**(target_symbols, 단일/복수) 또는
            # 미국 ETF 전체 유니버스(US_ETF). KR ETF 유니버스·etf_theme(KR 마스터 정본)
            # 판정은 적용하지 않는다.
            tgt = p.get("target_symbols") or []
            # 예시가 티커를 짚었으면 US_ETF 전체는 정답이 아니다 — 상품 지정이 유니버스
            # 전체로 벌어지는 것이 정확히 잡아야 할 결함이다(2026-08-27).
            want = expect.get("tickers", [])
            if want:
                missing = [t for t in want if t not in tgt]
                if missing:
                    f.fatal.append(
                        f"미국 ETF 상품 지정 소실({','.join(missing)} → "
                        f"uni={p.get('universe')}, tgt={tgt})")
            else:
                us_ok = (tgt and all(_US_TICKER_RE.fullmatch(str(s or "")) for s in tgt)) \
                    or p.get("universe") == ["US_ETF"]
                if not us_ok:
                    f.fatal.append(
                        f"미국 ETF 지정/유니버스 아님(uni={p.get('universe')}, tgt={tgt})")
        else:
            if p.get("universe") != ["ETF"]:
                f.fatal.append(f"ETF 유니버스 아님({p.get('universe')})")
            # 테마·상품명을 잃으면 전체 ETF(1,300여 종목) 전략으로 왜곡된다. 기대값은 ETF 마스터
            # 자기검증 추출기(정본)로 얻는다 — QA 대조용 ground truth, 파스 경로가 아니다.
            expected_theme = expect.get("theme")
            if expected_theme and not p.get("etf_theme"):
                f.fatal.append(f"ETF 테마 소실(기대 '{expected_theme}')")
        # ETF엔 기업 재무제표가 없다(universe_capabilities) — 조건이 붙으면 예시가 잘못됐다.
        # trading_value는 가격·거래량 파생이라 ETF에서도 허용되므로 제외한다.
        etf_illegal = [x.get("metric") for x in p.get("fundamental_filters", [])
                       if x.get("metric") != "trading_value"]
        if etf_illegal:
            f.fatal.append(f"ETF에 재무 조건({','.join(etf_illegal)})")
    # 업종/테마는 세 축 중 하나로 착지한다(FR-STR-074): 한국 섹터=sector,
    # 테마·회사 앵커=target_symbols, 미국 분류=us_industry(유니버스 **필터**라 종목
    # 목록으로 펼치지 않는다 — 2026-08-27 필터 승격). us_industry를 보지 않으면
    # 멀쩡히 반영된 미국 업종 전략이 '미반영'으로 잡힌다.
    if (tpl.category == "테마" and not p.get("sector")
            and not p.get("target_symbols") and not p.get("us_industry")):
        f.fatal.append("업종/테마 미반영")
    # 명시적 청산 규칙('N일선 이탈 시 청산', '데드크로스면 매도')은 신호로 남아야 한다 —
    # 손절·보유기간만 남으면 전략의 성격이 바뀐다(2026-07-27 실측: 예시 3의 청산 소실).
    if expect.get("exit") and not p.get("exit_signals"):
        f.fatal.append("명시 청산 규칙 소실")

    # 미탐지 판정에서 '되묻고 있는 팩터'는 제외한다 — 값 없이 언급된 조건('부채비율과 ROE
    # 조건을 충족하는 종목')을 되묻는 것은 정상 동작이지 소실이 아니다.
    for name in expect.get("coverage", []):
        pat, check = _COVERAGE_BY_NAME[name]
        if not check(p) and not asked_has(pat):
            f.missing.append(name)
    # 볼린저 방향·밴드 대조(정답표 예시만) — 뒤집힘은 소실보다 나쁘므로 치명이다.
    f.fatal.extend(bollinger_mismatches(tpl.title, p, asked))

    # ── 값 대조: "있는지"가 아니라 "얼마인지"를 본다 ────────────────────────────
    # 위 커버리지 검사는 `_has_fund`/`_has_sig`로 **지표 존재만** 본다. 2026-08-18 사고
    # ("시가총액 1조"→100000억=10조)가 08-14 전수 검증을 치명 0으로 통과한 자리이며,
    # 자릿수 오차는 금액만의 문제가 아니라 모든 임계값·설정에서 같은 모양으로 난다.
    # 세 층 모두 **반영된 경우에만** 값을 본다 — 부재·값대기·되묻기는 위 미탐지 레인
    # 소관이고, 두 레인이 같은 결손을 세면 되묻기 예외가 무력해진다.
    unit = lambda m: "억" if m in {"market_cap", "trading_value"} else ""  # noqa: E731

    # ① 재무 임계값(금액·비율 전부)
    for metric, wants in expect.get("fundamental", {}).items():
        got = [x.get("value") for x in p.get("fundamental_filters", []) if x.get("metric") == metric]
        got = [float(g) for g in got if isinstance(g, (int, float)) and not isinstance(g, bool)]
        if not got:
            continue
        for want in wants:
            if not any(abs(g - want) < 1e-6 for g in got):
                label = _FUND_METRIC_LABELS.get(metric, metric)
                f.fatal.append(f"{label} 임계값 오차(기대 {want:g}{unit(metric)} vs 파싱 "
                               f"{','.join(f'{g:g}' for g in got)}{unit(metric)})")

    # ② 스칼라 설정(손절·익절·종목수·리밸런싱·보유기간·기간·자본·트레일링·MDD)
    for key, want in expect.get("scalar", {}).items():
        label = _SCALAR_LABELS.get(key, key)
        got = p.get(key)
        if got is None:
            # 결손도 치명이다(2026-08-18). 종전에는 값이 통째로 사라진 경우를 건너뛰어,
            # 사용자가 말한 '보유 기간 상한 40거래일'이 파싱에서 없어져도 게이트가 초록이었다
            # — 값 오차는 잡고 소실은 침묵하는 그물이었다. 기대값 목록에는 **사용자가 말한
            # 값만** 오르므로(값 없는 항목은 애초에 제외) 여기서 비어 있으면 소실이다.
            f.fatal.append(f"{label} 소실(기대 {want} vs 파싱 없음)")
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
        # 되묻기·값-대기에 오른 숫자는 소실이 아니다 — "ADX 20 하향 이탈"을 값 대기(pending
        # source_text)로 제외하고 기준값을 묻는 중이면 20은 조용히 사라진 게 아니다(2026-09-03:
        # 컴파일러 침묵 왜곡 수리 뒤 정상 되묻기를 이 검사가 계속 치명으로 세던 오탐).
        # asked_about과 같은 계약(되묻는 팩터는 치명·미탐지 어느 쪽으로도 세지 않는다).
        asked_numbers = {float(x) for x in re.findall(r"\d+(?:\.\d+)?", asked)}
        pending_labels = [str(pc.get("label") or "").strip().lower()
                          for pc in res.get("pending_conditions") or []]
        for label, wants in expect.get("signal_numbers", {}).items():
            if any(pending and label.lower().startswith(pending) for pending in pending_labels):
                continue
            lost = [w for w in wants if not any(abs(u - w) < 1e-6 for u in used)
                    and not any(abs(a - w) < 1e-6 for a in asked_numbers)]
            if lost:
                f.fatal.append(f"{label} 소실(말한 값 {','.join(f'{w:g}' for w in lost)}이 "
                               f"신호 어디에도 없음 — 파싱 {sorted(used)})")

    # ④ 잉여 — 같은 역할 안에 **완전히 같은 조건이 두 번** 실리면 치명. 위 검사들은 전부
    # 결손 방향(빠졌나·값이 틀렸나)이라 "남는 게 붙었나"를 보지 않았고, 2026-08-18 사고
    # (예시 51 'EMA 데드크로스 청산'이 exit_signals에 2개 — 9B가 청산을 두 조각으로 내고
    # 결정론 교정이 둘을 같은 신호로 수렴)가 08-17 전수 검증을 치명 0으로 통과했다 —
    # 리포트 요약엔 '청산=ema,ema'로 찍혀 있었지만 판정 항목이 아니었다.
    for label, key in (("진입 신호", "entry_signals"), ("청산 신호", "exit_signals"),
                       ("재무 조건", "fundamental_filters")):
        dup = duplicated_conditions(p.get(key) or [])
        if dup:
            f.fatal.append(f"{label} 중복(같은 조건 {len(dup)}건 반복: "
                           f"{', '.join(dup)})")

    want = expect.get("positions")
    got = p.get("max_positions")
    if want is not None and got is not None and want != got:
        f.position = f"종목수: 프롬프트 {want} vs 파싱 {got}"
    elif got == 100 and want is None:
        # 명시 없이 100이면 기본값 폴백(미반영) 의심
        f.position = "종목수: 파싱 100(기본값 폴백 의심)"

    # 진입 규칙 공백은 **되묻지도 않고** 비어 있을 때만 치명이다. 값 없이 언급된 조건을
    # 되묻는 중이면 전략은 아직 완성 전일 뿐 조용히 빈 전략으로 나가는 게 아니다
    # (해석 실패로 빈 전략이 나가는 경우는 위 clarification_priority 검사가 잡는다).
    if (not p.get("fundamental_filters") and not p.get("entry_signals")
            and not p.get("ranking_metric") and not asked):
        f.fatal.append("진입 규칙 없음(되묻기도 없음)")
    f.unmatched = unmatched_numbers(expect, p, asked)
    if res.get("clarification_question"):
        f.notes.append("clarification 되물음")
    f.notes.extend(expect.get("notes", []))
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
    ap.add_argument("--use-cache", action="store_true",
                    help="백엔드를 부르지 않고 저장된 원시 파스 캐시만 읽는다(판정 로직만 손볼 때). "
                         "**게이트 용도로 쓰지 말 것** — 낡은 답으로 '치명 0'이 나온다")
    ap.add_argument("--category", default=None,
                    help="카테고리 필터(콤마 구분). 예: --category ETF,테마")
    ap.add_argument("--refresh", action="store_true",
                    help="(폐지 — 이제 기본 동작이다. 기존 명령 호환을 위해 받기만 한다)")
    ap.add_argument("--source", default="kr", choices=sorted(_SOURCES),
                    help="예시 소스: kr(한국, 기본) | us(미국 — usExamples.ts)")
    ap.add_argument("--lang", default="kr", choices=["kr", "en"],
                    help="파서 입력 언어: kr(원문, 기본) | en(en.ts 번역 — /us 전송 경로 재현)")
    args = ap.parse_args()
    if args.source == "us":
        ap.error("US 예시 기대값은 아직 작성되지 않았습니다. 이 하니스는 한국어 예시만 검증합니다")
    if args.lang == "en" and args.source != "us":
        # /us만 번역을 파서에 보낸다(지역=URL 경로, KR 페이지는 항상 한국어 전송).
        ap.error("--lang en은 --source us에서만 의미가 있다")

    global SOURCE, LANG
    SOURCE = args.source
    LANG = args.lang
    templates = load_templates(args.source, args.lang)
    if args.category:
        wanted = {c.strip() for c in args.category.split(",") if c.strip()}
        templates = [t for t in templates if t.category in wanted]
    # 원시 파스 캐시는 **기록**이지 근거가 아니다 — 기본 경로는 매번 백엔드에 다시 묻는다.
    # 종전엔 캐시에 있으면 무조건 재사용했고(--refresh를 붙여야만 재파싱), CLAUDE.md가
    # 지정한 US 게이트 명령 두 개에는 그 플래그가 없다 → **"치명 0"이라는 합격선이 임의로
    # 낡은 백엔드의 답 위에서 나올 수 있었다**(2026-08-29 발견. 같은 트랩이 qa_free_input의
    # 기준 전략 캐시에서 실제 사고로 터졌다 — 원화 기본값이 박힌 사본을 4일간 기준선으로 썼다).
    # 표식(git 커밋·소스 해시)으로는 못 막는다: 하니스는 답을 HTTP로 **남의 프로세스**에
    # 물어보므로 로컬 파일은 그 서버의 빌드를 증명하지 못하고, LLM 모델·프롬프트 교체는
    # 어떤 파일 목록으로도 안 덮인다. 답이 현행인지 아는 유일한 방법은 현행에 다시 묻는 것이다.
    cache: dict[str, dict] = {}
    if RAW_CACHE.exists():
        cache = json.loads(RAW_CACHE.read_text())
    if args.use_cache:
        # 남은 재사용 경로(판정 로직만 손볼 때)는 **조용하지 않게** 만든다 — 무엇을 보고
        # 판정하는지 사람이 알아야 한다.
        age_h = (time.time() - RAW_CACHE.stat().st_mtime) / 3600 if RAW_CACHE.exists() else 0.0
        print(f"⚠️  --use-cache: 백엔드를 부르지 않는다. 캐시 {len(cache)}건, "
              f"마지막 기록 {age_h:.1f}시간 전 — 현행 백엔드의 답이 아니다.", file=sys.stderr)

    lines = ["# 전략 템플릿 파싱 검출 리포트 (정제판)\n",
             f"- 대상: {len(templates)}개 (source={args.source}, lang={args.lang})\n"]
    problems: list[str] = []
    n_missing = n_pos = n_fatal = n_unmatched = 0

    for i, tpl in enumerate(templates, 1):
        # 캐시 키=파서 입력 텍스트. --lang en이면 영어 번역이 키가 되므로 한국어 실행과
        # 캐시가 섞이지 않고, 번역 문구가 바뀌면 자연히 새로 파싱한다.
        text = tpl.parse_input()
        if args.use_cache:
            res = cache.get(text)
            if res is None:
                print(f"[{i}] 캐시 없음, 건너뜀", file=sys.stderr)
                continue
        else:
            try:
                res = parse_strategy(text)
            except Exception as e:
                # 호출 자체가 죽으면(백엔드 미기동·포트 선점 501 등) 검증이 성립하지 않는다 —
                # 치명으로 세워 게이트를 붉게 만든다(2026-08-14: 81건 전부 501인데 exit 0으로 통과).
                n_fatal += 1
                lines.append(f"\n## {i}. {tpl.title}\n- ❌ 파싱 오류: {e}")
                problems.append(f"{i}. {tpl.title} — 치명[파싱 호출 실패: {e}]")
                continue
            cache[text] = res
            RAW_CACHE.write_text(json.dumps(cache, ensure_ascii=False))
        print(f"[{i}/{len(templates)}] {tpl.title}", file=sys.stderr)

        p = res.get("parsed", {})
        f = analyze(tpl, res)
        lines.append(f"\n## {i}. [{tpl.category}/{tpl.level}] {tpl.title}\n")
        lines.append(f"> {tpl.prompt}\n")
        if tpl.input and tpl.input != tpl.prompt:
            lines.append(f"> (파서 입력 EN) {tpl.input}\n")
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
