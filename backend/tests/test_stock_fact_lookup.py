"""종목 지표 사실 조회 레인 — 규제 게이트 분리의 안전 계약.

[규제 안전] CLAUDE.md는 객관적 과거 데이터·재무 지표 제공을 허용하고 추천·전망·매수
시점 제안을 금지한다. `STOCK_ANALYSIS` 라벨 하나가 둘을 같은 거절로 묶던 것을,
라벨과 직교하는 `fact_metric` 축으로 갈랐다(2026-08-11).

이 설계의 안전은 **축이 답변 자유도를 열지 않는다**는 데서 나온다 — LLM은 닫힌
목록에서 지표만 고르고, 문장은 `stock_facts`가 데이터에서 읽어 정해진 틀에 채운다.
그래서 축이 오판돼도 최악은 '숫자를 보여준다'이지 '사도 된다고 말한다'가 아니다.
아래 테스트는 그 성질을 **LLM 없이** 고정한다.
"""

from __future__ import annotations

import pytest

from intent import classifier, interpreter, stock_facts
from intent.schemas import QueryIntent, WorkflowStatus
from stock_analysis.symbol_resolver import StockRef

_SAMSUNG = StockRef(symbol="005930", name="삼성전자", market="KOSPI", sector="반도체")
_APPLE = StockRef(symbol="AAPL", name="애플", overseas=True)


def _interp(**kwargs) -> interpreter.IntentInterpretation:
    kwargs.setdefault("intent", QueryIntent.STOCK_ANALYSIS)
    return interpreter.IntentInterpretation(**kwargs)


# ── 닫힌 목록 계약 ────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("per", "per"),
        ("PER", "per"),
        ("operating-margin", "operating_margin"),
        ("  Market_Cap  ", "market_cap"),
    ],
)
def test_metric_normalization(raw, expected):
    assert stock_facts.normalize_metric(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["목표주가", "적정가치", "매수의견", "sentiment", "", None, 12, "per; drop table"],
)
def test_unknown_metrics_are_rejected(raw):
    """목록 밖은 None — 모르는 지표를 조회로 승격하지 않는다."""
    assert stock_facts.normalize_metric(raw) is None


# ── 게이트 성립 조건 ──────────────────────────────────────────────────────

def test_fact_lane_requires_stock_analysis_label():
    """전략 설계 발화는 지표가 실려도 조회 레인이 아니다 — 그건 스크리닝 조건이다."""
    metric, answer = classifier._resolve_stock_fact(
        _interp(intent=QueryIntent.STRATEGY_ADVICE, fact_metric="per"), _SAMSUNG
    )

    assert metric is None and answer is None


def test_fact_lane_requires_a_metric():
    """지표가 없으면 판단 요청이다 — 기존 거절 그대로."""
    metric, answer = classifier._resolve_stock_fact(_interp(fact_metric=None), _SAMSUNG)

    assert metric is None and answer is None


def test_fact_lane_requires_a_resolved_domestic_stock():
    """종목 정본 매핑이 없거나 해외 종목이면 보유 데이터가 없다."""
    assert classifier._resolve_stock_fact(_interp(fact_metric="per"), None) == (None, None)
    assert classifier._resolve_stock_fact(_interp(fact_metric="per"), _APPLE) == (None, None)


# ── 판단 요청이 거절로 남는가 (가장 중요한 계약) ──────────────────────────

def test_judgment_request_still_gets_the_refusal():
    """지표 없는 종목 질문은 종전대로 '추천 불가 안내 + 전략 전환'이다."""
    result = classifier._apply_domain_policy(
        _interp(stock_name="삼성전자"),
        last_symbol=None,
        query="삼성전자 지금 사도 될까?",
        active_strategy=False,
        workflow_status=WorkflowStatus.IDLE,
    )

    assert result.fact_metric is None
    assert "매수·매도 판단이나 종목 추천은 제공하지 않아요" in (result.suggested_reply or "")


def test_fact_answer_never_evaluates_even_if_axis_misfires():
    """축이 오판해도 답변은 사실 제시에서 끝난다 — 이 설계의 안전 근거.

    판단을 요구하는 발화에 LLM이 실수로 지표를 실었다고 가정한다. 그래도 나가는
    문장은 값·기준일·'판단은 제공하지 않는다'뿐이고, 평가·권유·전망 어휘가 없다.
    """
    reading = stock_facts.read_metric("005930", "per")
    if reading is None:
        pytest.skip("로컬에 005930 parquet이 없다")

    answer = stock_facts.metric_answer("삼성전자", reading)

    assert "매수·매도 판단이나 종목 추천은 제공하지 않습니다" in answer
    for banned in ("추천", "유망", "좋은 종목", "사세요", "매수하세요", "전망", "기대"):
        if banned == "추천":
            # '추천은 제공하지 않습니다'는 부정문이므로 허용 — 권유 표현만 금지한다.
            continue
        assert banned not in answer


# ── 값이 없을 때 지어내지 않는가 ──────────────────────────────────────────

def test_missing_symbol_data_reports_absence():
    """parquet이 없는 종목은 값을 지어내지 않고 없다고 밝힌다."""
    ghost = StockRef(symbol="999999", name="없는회사", market="KOSPI")

    metric, answer = classifier._resolve_stock_fact(_interp(fact_metric="per"), ghost)

    assert metric == "per"
    assert "찾지 못했습니다" in (answer or "")
    assert "추정해 알려드리지는 않습니다" in (answer or "")


def test_read_metric_returns_none_for_unknown_key():
    assert stock_facts.read_metric("005930", "목표주가") is None


# ── 프롬프트 계약 ─────────────────────────────────────────────────────────

def test_prompt_separates_value_questions_from_judgment():
    """프롬프트가 '값만 묻는 경우'와 '조건으로 쓰는 경우'를 모두 배제 규칙으로 갖는다.

    이 두 규칙이 게이트가 새지 않게 하는 유일한 장치다(축 판정은 LLM 소관).
    """
    prompt = interpreter.SYSTEM_PROMPT

    assert "fact_metric" in prompt
    assert "16." in prompt and "17." in prompt
    # 닫힌 목록이 프롬프트에 실제로 실려야 LLM이 목록 밖을 덜 고른다.
    # 표기는 '사용자 표기(한국어 라벨) → 키' 순이다 — 키를 앞에 두면 9B가 '영업이익률'
    # 같은 한국어 지표명을 키로 잇지 못했다(2026-08-11 실측 5/5 미추출 → 뒤집고 예시
    # 추가 후 10/10).
    assert "PER(주가수익비율) → per" in prompt
    assert "영업이익률 → operating_margin" in prompt
