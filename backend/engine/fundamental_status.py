"""재무 비율(PER/PBR/ROE/PCR/EV-EBITDA/EV-EBIT)과 성장률이 금융적으로 무의미한 값
(음수 순이익·자기자본·EBITDA·EBIT, 적자↔흑자 전환 등)일 때 null+상태코드로 판정하는
순수 함수 모음. 필터링·랭킹·API·프론트·LLM 서술이 이 모듈 하나로 동일한 규칙을 쓴다.

호출자는 값 자체를 여기서 계산하지 않는다 — 이미 계산된 비율/드라이버를 넘기면
"이 값을 신뢰해도 되는가(status is None)"만 판정한다. status가 None이 아니면 호출자는
해당 비율을 화면·필터·랭킹에서 null로 취급해야 한다.
"""
from __future__ import annotations

import functools
import json
from pathlib import Path
from typing import Optional, Tuple

NEGATIVE_EARNINGS = "NEGATIVE_EARNINGS"
NEGATIVE_EQUITY = "NEGATIVE_EQUITY"
NEGATIVE_CASHFLOW = "NEGATIVE_CASHFLOW"
NEGATIVE_EBIT = "NEGATIVE_EBIT"
NEGATIVE_EBITDA = "NEGATIVE_EBITDA"
TURNAROUND = "TURNAROUND"
LOSS_TRANSITION = "LOSS_TRANSITION"
LOSS_NARROWED = "LOSS_NARROWED"
LOSS_WIDENED = "LOSS_WIDENED"
DIVIDE_BY_ZERO = "DIVIDE_BY_ZERO"
MISSING_DATA = "MISSING_DATA"

_STATUS_MESSAGES_PATH = Path(__file__).resolve().parents[2] / "data" / "fundamental-status-messages.json"


@functools.lru_cache(maxsize=1)
def _load_status_messages() -> dict:
    return json.loads(_STATUS_MESSAGES_PATH.read_text(encoding="utf-8"))


def status_message(status: Optional[str]) -> Optional[str]:
    """상태코드 → 사용자에게 보여줄 한국어 설명 문구. 정상(None)이면 None."""
    if status is None:
        return None
    return _load_status_messages().get(status)


def per_status(eps: Optional[float]) -> Optional[str]:
    """PER = 시가총액 / 순이익. None이면 원값을 그대로 신뢰해도 된다."""
    if eps is None:
        return MISSING_DATA
    if eps == 0:
        return DIVIDE_BY_ZERO
    if eps < 0:
        return NEGATIVE_EARNINGS
    return None


def pbr_status(equity: Optional[float]) -> Optional[str]:
    """PBR = 시가총액 / 지배주주지분(또는 BPS). equity에는 total_equity 또는 bps를 넘긴다."""
    if equity is None:
        return MISSING_DATA
    if equity == 0:
        return DIVIDE_BY_ZERO
    if equity < 0:
        return NEGATIVE_EQUITY
    return None


def roe_status(equity: Optional[float]) -> Optional[str]:
    """ROE = 순이익 / 자기자본. 분모 판정 기준은 PBR과 동일하다."""
    return pbr_status(equity)


def pcr_status(operating_cash_flow: Optional[float]) -> Optional[str]:
    """PCR = 시가총액 / 영업활동현금흐름."""
    if operating_cash_flow is None:
        return MISSING_DATA
    if operating_cash_flow == 0:
        return DIVIDE_BY_ZERO
    if operating_cash_flow < 0:
        return NEGATIVE_CASHFLOW
    return None


def ev_ebitda_status(ebitda: Optional[float]) -> Optional[str]:
    """EV/EBITDA. ebitda<=0이면 배율 자체가 의미 없다."""
    if ebitda is None:
        return MISSING_DATA
    if ebitda == 0:
        return DIVIDE_BY_ZERO
    if ebitda < 0:
        return NEGATIVE_EBITDA
    return None


def ev_ebit_status(ebitda: Optional[float], ebit: Optional[float]) -> Optional[str]:
    """EV/EBIT. EV는 ev_ebitda(KIS 제공 비율) x ebitda(raw)로 역산하므로, ebitda<=0이면
    EV 자체를 구할 수 없어 ebit 부호와 무관하게 계산 불가하다(데이터 제약에 따른 근사)."""
    if ev_ebitda_status(ebitda) is not None:
        return MISSING_DATA
    if ebit is None:
        return MISSING_DATA
    if ebit == 0:
        return DIVIDE_BY_ZERO
    if ebit < 0:
        return NEGATIVE_EBIT
    return None


def growth_and_status(
    prior: Optional[float], current: Optional[float]
) -> Tuple[Optional[float], Optional[str]]:
    """전년 대비 증가율(%)과 상태코드를 함께 반환한다.

    (growth, None): growth가 일반 증가율 공식으로 유효하게 계산됨.
    (None, status): 부호 전환·적자 지속 등으로 일반 증가율 공식이 의미가 없어 growth 대신
    상태코드로 분류됨. "흑자"는 current/prior > 0, 그 외(0 포함)는 "적자"로 취급한다.
    """
    if prior is None or current is None:
        return None, MISSING_DATA
    if prior == 0:
        return None, DIVIDE_BY_ZERO
    if prior > 0 and current > 0:
        return (current - prior) / prior * 100.0, None
    if prior > 0:  # current <= 0
        return None, LOSS_TRANSITION
    if current > 0:  # prior < 0
        return None, TURNAROUND
    # prior < 0 and current <= 0: 적자 지속 — 규모 개선/악화만 판정
    if abs(current) < abs(prior):
        return None, LOSS_NARROWED
    if abs(current) > abs(prior):
        return None, LOSS_WIDENED
    return None, LOSS_NARROWED
