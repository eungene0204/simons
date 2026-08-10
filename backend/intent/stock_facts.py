"""종목 지표 사실 조회 — 판단 요청과 분리된 '값 묻기' 레인.

[규제 안전] CLAUDE.md는 **객관적인 과거 데이터 표시와 재무 지표 제공을 명시적으로
허용**하고, 금지하는 것은 추천·전망·매수 시점 제안이다. 그런데 라벨 하나
(`STOCK_ANALYSIS`)가 "삼성전자 사도 될까?"(금지)와 "삼성전자 PER 얼마야?"(허용)를
같은 거절 문구로 묶고 있었다(2026-08-11 커버리지 프로브: 사실 조회 6건 전부 차단).

이 모듈이 그 둘을 가르는 축이다. 설계의 핵심은 **축이 답변 자유도를 열지 않는다**는 것:

    LLM은 "어떤 지표를 물었나"만 닫힌 목록에서 고르고(clarify_target과 같은 계약),
    답변 문장은 이 모듈이 데이터에서 읽어 정해진 틀에 채운다.

그래서 축이 오판돼도 최악은 "숫자를 보여준다"이지 "사도 된다고 말한다"가 아니다 —
LLM이 판단 문장을 지어낼 자리 자체가 없다.

데이터 정본은 백테스트 엔진이 쓰는 종목별 parquet(`data/ohlcv/<symbol>.parquet`)이다.
KIS 실시간 조회를 쓰지 않는 이유는 두 가지다: 엔진 결과와 같은 값을 보여야 하고,
외부 호출 실패가 답변을 좌우하면 안 된다.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, NamedTuple, Optional

logger = logging.getLogger(__name__)

_OHLCV_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "ohlcv")


class MetricSpec(NamedTuple):
    """지표 하나의 표시 계약. 컬럼이 없으면 조회 자체가 성립하지 않는다.

    `window`가 있으면 그 거래일 수만큼의 최근 구간에서 `reduce`로 집계한다
    (52주 최고가처럼 저장된 값이 아니라 계산해야 하는 지표).
    """

    key: str
    label: str
    column: str
    format: Callable[[float], str]
    window: Optional[int] = None
    reduce: Optional[str] = None  # "max" | "min"


def _plain(unit: str = "", digits: int = 2) -> Callable[[float], str]:
    return lambda v: f"{v:,.{digits}f}{unit}"


def _won(value: float) -> str:
    """parquet의 market_cap 단위는 억원이다(project_market_cap_eok_unit)."""
    if value >= 10_000:
        return f"{value / 10_000:,.2f}조원"
    return f"{value:,.0f}억원"


# LLM이 고를 수 있는 지표의 **닫힌 목록**. 여기 없는 표기는 None으로 강등된다 —
# 모르는 지표를 조회로 승격하지 않는다(clarify_target과 같은 안전 방향).
METRICS: tuple[MetricSpec, ...] = (
    MetricSpec("per", "PER(주가수익비율)", "per", _plain("배")),
    MetricSpec("pbr", "PBR(주가순자산비율)", "pbr", _plain("배")),
    MetricSpec("psr", "PSR(주가매출비율)", "psr", _plain("배")),
    MetricSpec("pcr", "PCR(주가현금흐름비율)", "pcr", _plain("배")),
    MetricSpec("ev_ebitda", "EV/EBITDA", "ev_ebitda", _plain("배")),
    MetricSpec("roe", "ROE(자기자본이익률)", "roe_or_gpa", _plain("%")),
    MetricSpec("roa", "ROA(총자산이익률)", "roa", _plain("%")),
    MetricSpec("debt_ratio", "부채비율", "debt_ratio", _plain("%")),
    MetricSpec("current_ratio", "유동비율", "current_ratio", _plain("%")),
    MetricSpec("operating_margin", "영업이익률", "operating_margin", _plain("%")),
    MetricSpec("net_margin", "순이익률", "net_margin", _plain("%")),
    MetricSpec("gross_margin", "매출총이익률", "gross_margin", _plain("%")),
    MetricSpec("dividend_yield", "배당수익률", "dividend_yield", _plain("%")),
    MetricSpec("payout_rate", "배당성향", "payout_rate", _plain("%")),
    MetricSpec("eps", "EPS(주당순이익)", "eps", _plain("원", 0)),
    MetricSpec("bps", "BPS(주당순자산)", "bps", _plain("원", 0)),
    MetricSpec("market_cap", "시가총액", "market_cap", _won),
    MetricSpec("revenue_growth", "매출 증가율", "revenue_growth", _plain("%")),
    MetricSpec("operating_income_growth", "영업이익 증가율", "operating_income_growth", _plain("%")),
    MetricSpec("net_income_growth", "당기순이익 증가율", "net_income_growth", _plain("%")),
    MetricSpec("price", "종가", "close", _plain("원", 0)),
    # 52주 = 약 252거래일. 저장된 값이 아니라 최근 구간에서 계산한다.
    MetricSpec("week52_high", "52주 최고가", "high", _plain("원", 0), window=252, reduce="max"),
    MetricSpec("week52_low", "52주 최저가", "low", _plain("원", 0), window=252, reduce="min"),
)

_BY_KEY = {spec.key: spec for spec in METRICS}


def prompt_metric_lines() -> str:
    """LLM 프롬프트에 넣을 지표 목록. 목록 밖은 고를 수 없다.

    사용자 표기(한국어 라벨)를 앞에, 출력할 키를 뒤에 둔다 — 키를 앞에 두면 9B가
    '영업이익률' 같은 한국어 지표명을 키로 잇지 못했다(실측 2026-08-11: 5/5 미추출,
    온도 무관. 표기 순서를 뒤집자 추출됨 — 모델은 목록을 '입력 표기 → 출력'으로 읽는다).
    """
    return "\n".join(f"{spec.label} → {spec.key}" for spec in METRICS)


def normalize_metric(value: object) -> Optional[str]:
    """LLM이 고른 지표 키를 정규화한다. 목록 밖·비문자열은 None(강등)."""
    if not isinstance(value, str):
        return None
    key = value.strip().lower().replace("-", "_").replace(" ", "_")
    return key if key in _BY_KEY else None


class MetricReading(NamedTuple):
    label: str
    value: str
    as_of: str
    # 구간 집계 지표인가. 그렇다면 as_of는 '관측 기준일'이 아니라 **그 값이 나온 날**이다 —
    # 문장에서 다르게 표기해야 오해가 없다.
    windowed: bool = False


def read_metric(symbol: str, metric_key: str) -> Optional[MetricReading]:
    """종목 parquet에서 지표의 최신 유효값을 읽는다. 없으면 None(지어내지 않는다).

    최신 행이 결측일 수 있으므로(재무는 분기마다 갱신) 뒤에서부터 유효값을 찾는다.
    그 값이 실제로 관측된 날짜를 함께 돌려준다 — 오늘 값인 것처럼 보이면 안 된다.
    """
    spec = _BY_KEY.get(metric_key)
    if spec is None:
        return None

    path = os.path.join(_OHLCV_DIR, f"{symbol}.parquet")
    if not os.path.exists(path):
        return None

    try:
        import polars as pl

        frame = pl.read_parquet(path, columns=["date", spec.column])
    except Exception:  # noqa: BLE001 — 조회 실패가 대화를 깨뜨리면 안 된다
        logger.debug("지표 조회 실패 | symbol=%s metric=%s", symbol, metric_key, exc_info=True)
        return None

    frame = frame.drop_nulls()
    if frame.height == 0:
        return None

    if spec.window:
        # 구간 집계 지표(52주 최고·최저) — 값이 실제로 나온 날짜를 함께 돌려준다.
        recent = frame.tail(spec.window)
        target = recent[spec.column].max() if spec.reduce == "max" else recent[spec.column].min()
        if target is None:
            return None
        hit = recent.filter(recent[spec.column] == target).tail(1).to_dicts()[0]
        raw, as_of = hit.get(spec.column), hit.get("date")
    else:
        row = frame.tail(1).to_dicts()[0]
        raw, as_of = row.get(spec.column), row.get("date")

    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None

    return MetricReading(
        label=spec.label,
        value=spec.format(value),
        as_of=as_of.strftime("%Y-%m-%d") if hasattr(as_of, "strftime") else str(as_of),
        windowed=bool(spec.window),
    )


def _topic_particle(word: str) -> str:
    """받침 유무로 은/는을 고른다. 판정 불가(괄호·영문 끝)면 '은(는)'로 병기한다."""
    last = word[-1] if word else ""
    if not ("가" <= last <= "힣"):
        return "은(는)"
    return "은" if (ord(last) - ord("가")) % 28 else "는"


def metric_answer(stock_name: str, reading: MetricReading) -> str:
    """사실 문장. **LLM이 짓지 않는다** — 값과 기준일만 틀에 채운다.

    [규제 안전] 서술은 관측된 사실에서 끝난다. 높다·낮다·싸다·비싸다 같은 해석은
    붙이지 않는다(CLAUDE.md 안전한 표현 원칙: "과거 데이터 기준 CAGR은 12.4%였습니다").
    """
    when = (
        f"{reading.as_of}에 기록, 플랫폼 보유 데이터"
        if reading.windowed
        else f"{reading.as_of} 기준, 플랫폼 보유 데이터"
    )
    return (
        f"{stock_name}의 {reading.label}{_topic_particle(reading.label)} "
        f"**{reading.value}**입니다. ({when})\n\n"
        "이 값은 과거 데이터를 그대로 보여드리는 것이며, 매수·매도 판단이나 종목 추천은 "
        "제공하지 않습니다. 이 지표를 조건으로 삼는 전략을 만들어 과거 데이터에서 "
        "검증해보실 수 있어요."
    )


def metric_unavailable(stock_name: str, metric_key: str) -> Optional[str]:
    """지표는 알겠는데 그 종목의 값이 없을 때. 지어내지 않고 없다고 밝힌다."""
    spec = _BY_KEY.get(metric_key)
    if spec is None:
        return None
    return (
        f"{stock_name}의 {spec.label} 데이터를 플랫폼에서 찾지 못했습니다. "
        "값을 추정해 알려드리지는 않습니다.\n\n"
        "다른 지표를 물어보시거나, 관심 있는 조건으로 전략을 만들어 과거 데이터에서 "
        "검증해보실 수 있어요."
    )
