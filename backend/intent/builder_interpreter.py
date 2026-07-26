"""빌더 자유 서술 LLM 해석기 — 자연어 해석 계약 단계 3, C안 (2026-07-26 사용자 결정).

경계: 칩 클릭·현재 질문에 대한 값 답변("10프로")은 빌더의 결정적 형식 정규화가 즉답하고
(제한된 답의 형식 검증 — 계약 위반 아님), **결정적 레이어가 해석하지 못한 자유 서술만**
이 모듈이 LLM으로 해석한다. 미인식 표현에 regex를 추가하는 것은 금지
([feedback_nl_parser_hybrid]) — 긴 꼬리의 해석 책임은 이 레인에 있다.

구조(계약 § 3): LLM이 제한된 ops JSON을 출력 → 결정적 검증이 형식만 판정
(필드 화이트리스트·enum·값 범위·수치는 입력 수치와 대조·source_text 인용 실재·
삭제는 채워진 필드만) → 기존 BuilderState patch 계약으로 변환. 검증 탈락 op는
조용히 버리지 않고 안내 노트로 알린다. LLM 실패·해석 불가는 None(호출부의 기존
미인식 안내 유지 — 원문 재해석 폴백 없음).

롤백: BUILDER_FREETEXT_MODE=deterministic (라우트가 해석기 주입을 생략).
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Callable, List, Optional

from intent.strategy_builder import (
    _SINGLE_ASSET_BLOCKED_TYPES,
    _TYPE_PARAM_RESET,
    _risk_value_valid,
    _valid_count,
    BuilderState,
    RISK_FIELDS,
    STRATEGY_PARAM_STEPS,
)

logger = logging.getLogger("builder_interpreter")


def freetext_llm_enabled() -> bool:
    """자유 서술 LLM 레인 사용 여부. 롤백=BUILDER_FREETEXT_MODE=deterministic."""
    mode = os.environ.get("BUILDER_FREETEXT_MODE", "llm_first").strip().lower()
    return mode != "deterministic"


_ENUM_FIELDS = {
    "universe": {"KOSPI", "KOSDAQ", "KOSPI200", "KOSPI_KOSDAQ", "ETF"},
    "strategy_type": {
        "momentum", "golden_cross", "macd", "bollinger", "breakout", "stochastic",
        "cci", "volume_spike", "rsi", "mean_reversion", "value", "custom",
    },
    "rebalance_cycle": {"daily", "weekly", "monthly", "quarterly", "yearly", "none"},
    "ma_kind": {"sma", "ema"},
    "macd_mode": {"crossover", "zero"},
}

# 정수(양수) 필드와 실수(양수) 필드 — 값은 반드시 입력의 숫자와 대조된다(환각 게이트).
_INT_FIELDS = {
    "holding_count", "lookback_days", "hold_period_days", "rsi_period",
    "ma_short", "ma_long", "cci_period", "volume_period", "trend_filter_ma",
}
_FLOAT_FIELDS = {
    "stop_loss_pct", "take_profit_pct", "trailing_stop_pct",
    "rsi_oversold", "rsi_overbought", "rsi_filter", "cci_threshold",
    "value_pbr", "value_roe", "liquidity_min",
}
# 거래일 필드는 단위 환산(주=5·개월=21·년=252)을 인정한다 — "3개월"의 63은 입력에 없다.
_TRADING_DAY_FIELDS = {"lookback_days", "hold_period_days"}
_DAY_MULTS = (1, 5, 21, 252)

# 삭제 가능한 필드 → 삭제 patch(채워져 있을 때만). 리밸런싱 삭제는 '안 함' 명시값으로
# (_parse_removal과 동일 계약 — 필수 항목이라 비우는 대신 none).
_REMOVABLE_PATCH = {
    "stop_loss_pct": {"stop_loss_pct": None},
    "take_profit_pct": {"take_profit_pct": None},
    "trailing_stop_pct": {"trailing_stop_pct": None},
    "hold_period_days": {"hold_period_days": None},
    "trend_filter_ma": {"trend_filter_ma": None},
    "liquidity_min": {"liquidity_min": None},
    "rsi_filter": {"rsi_filter": None},
    "holding_count": {"holding_count": None},
    "sector": {"sector": None, "sector_unresolved": False, "sector_hint": None},
    "theme_symbols": {"theme_symbols": None, "theme_label": None},
    "rebalance_cycle": {"rebalance_cycle": "none"},
}

_NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", (text or "")).lower()


def _build_system_prompt() -> str:
    return (
        "너는 주식 전략 빌더 대화의 자유 서술 해석기다. 사용자의 입력 문장을 ops JSON으로만 "
        "변환한다.\n"
        "허용 op:\n"
        '- "set": 필드에 새 값 설정(value 필수)\n'
        '- "remove": 이미 설정된 조건의 삭제 요청(빼줘/없애줘/제거/취소)\n'
        '- "reopen": 값 없이 바꾸고 싶다는 의사만 밝힘("시장 바꿔줘") — 그 항목을 다시 묻게 한다\n'
        "필드(값 형식):\n"
        '- universe: "KOSPI"|"KOSDAQ"|"KOSPI200"|"KOSPI_KOSDAQ"(양시장)|"ETF"\n'
        '- strategy_type: "momentum"(상승률 상위)|"golden_cross"|"macd"|"bollinger"|'
        '"breakout"(신고가/박스권 돌파)|"stochastic"|"cci"|"volume_spike"(거래량 급증)|'
        '"rsi"|"mean_reversion"(과매도 반등)|"value"(저평가 가치)|"custom"(직접 서술)\n'
        '- rebalance_cycle: "daily"|"weekly"|"monthly"|"quarterly"|"yearly"|"none"\n'
        "- holding_count: 보유 종목 수(정수)\n"
        "- lookback_days·hold_period_days: 거래일 수(1주=5, 1개월=21, 1년=252로 환산)\n"
        "- stop_loss_pct·take_profit_pct·trailing_stop_pct: 퍼센트 숫자\n"
        "- sector: 업종/테마 표현(사용자가 말한 그대로)\n"
        "- trend_filter_ma(일)·liquidity_min(억 원)·rsi_filter·rsi_period·rsi_oversold·"
        "rsi_overbought·ma_short·ma_long·cci_period·cci_threshold·volume_period·"
        "value_pbr·value_roe: 숫자\n"
        '- ma_kind: "sma"|"ema" / macd_mode: "crossover"|"zero"\n'
        "규칙:\n"
        '1. JSON만 출력한다: {"ops":[{"op":"set","field":"stop_loss_pct","value":10,'
        '"source_text":"10프로 빠지면 팔아"}]}\n'
        "2. source_text는 입력 문장에서 그대로 인용한다. 인용할 수 없는 op는 내지 않는다.\n"
        "3. 사용자가 말하지 않은 숫자를 지어내지 않는다. 값 없이 변경 의사만 있으면 "
        'op="reopen"으로 낸다.\n'
        '4. 해석할 수 없으면 {"ops":[]}.\n'
    )


def _state_summary(state: BuilderState) -> str:
    filled = []
    for field in ("universe", "sector", "strategy_type", "lookback_label", "holding_count",
                  "rebalance_cycle", "stop_loss_pct", "take_profit_pct", "trailing_stop_pct",
                  "hold_period_days", "trend_filter_ma", "liquidity_min", "rsi_filter"):
        value = getattr(state, field, None)
        if value is not None:
            filled.append(f"{field}={value}")
    return ", ".join(filled) or "(없음)"


def _extract_ops(raw: str) -> Optional[list]:
    m = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except (ValueError, TypeError):
        return None
    ops = data.get("ops") if isinstance(data, dict) else None
    return ops if isinstance(ops, list) else None


def _number_matches(value: float, field: str, text_nums: set[float]) -> bool:
    if value in text_nums:
        return True
    if field in _TRADING_DAY_FIELDS:
        return any(n * mult == value for n in text_nums for mult in _DAY_MULTS)
    return False


def _validate_set(field: str, value, state: BuilderState, text_nums: set[float]) -> Optional[dict]:
    """set op 하나를 검증해 patch로 변환한다(탈락=None). 형식·범위 판정만 — 의미 해석 없음."""
    if field in _ENUM_FIELDS:
        if not isinstance(value, str) or value not in _ENUM_FIELDS[field]:
            return None
        if field == "strategy_type":
            # 기존 결정적 경로와 동일 가드: ETF 유니버스엔 가치 전략 불가(BF-12),
            # 단일 종목 모드엔 종목 선별형 유형 불가(FR-STR-068b).
            if value == "value" and state.universe == "ETF":
                return None
            if state.single_symbol is not None and value in _SINGLE_ASSET_BLOCKED_TYPES:
                return None
            patch: dict = {"strategy_type": value}
            if state.strategy_type and value != state.strategy_type:
                patch.update(_TYPE_PARAM_RESET)
            return patch
        return {field: value}
    if field == "sector":
        from engine.universe_pit import normalize_sector

        canonical = normalize_sector(value) if isinstance(value, str) else None
        return {"sector": canonical, "sector_unresolved": False, "sector_hint": None} \
            if canonical else None
    if field in _INT_FIELDS or field in _FLOAT_FIELDS:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            return None
        value = float(value)
        if not _number_matches(value, field, text_nums):
            return None  # 입력에 없는 수치 — 환각 게이트(§ 3-1 수치 대조)
        if field in RISK_FIELDS:  # hold_period_days 포함 — 하나라도 채워지면 청산 완료
            if not _risk_value_valid(field, value):
                return None
            coerced = int(value) if field == "hold_period_days" else value
            return {field: coerced, "risk_done": True}
        if field == "holding_count":
            return {"holding_count": int(value)} if _valid_count(int(value)) else None
        if field == "lookback_days":
            return {"lookback_days": int(value), "lookback_label": f"{int(value)}일"}
        return {field: int(value) if field in _INT_FIELDS else value}
    return None


def _reopen_patch(field: str, state: BuilderState) -> Optional[dict]:
    """값 없는 변경 의사 → 그 질문으로 자연 복귀시키는 patch(_parse_valueless_change와 동일 계약)."""
    if field in RISK_FIELDS or field == "hold_period_days":
        return {"risk_done": False} if state.risk_done else None
    if field == "holding_count":
        return {"holding_count": None} if state.holding_count is not None else None
    if field == "filters_asked" or field in ("trend_filter_ma", "liquidity_min", "rsi_filter"):
        if state.filters_asked and "filters" in STRATEGY_PARAM_STEPS.get(state.strategy_type or "", ()):
            return {"filters_asked": False}
        return None
    if field == "rebalance_cycle":
        return {"rebalance_cycle": None} if state.rebalance_cycle is not None else None
    if field == "universe":
        if state.universe is not None and state.single_symbol is None:
            return {"universe": None}
        return None
    if field == "lookback_days":
        if state.lookback_days is not None:
            return {"lookback_days": None, "lookback_label": None}
        return None
    if field == "strategy_type":
        if state.strategy_type is not None:
            return {"strategy_type": None, **_TYPE_PARAM_RESET}
        return None
    return None


def interpret_utterance(
    text: str, state: BuilderState, chat: Callable[..., str],
) -> Optional[tuple[dict, List[str]]]:
    """자유 서술 한 문장을 LLM으로 해석해 (patch, 안내 노트)로 변환한다.

    반환 None = 해석 실패/무의미(호출부가 기존 미인식 안내 유지). patch가 비고 노트만
    있는 경우는 없다 — 전 op 탈락이면 탈락 안내 노트와 함께 빈 patch를 반환하지 않고
    None을 준다(무근거 출력에 상태를 바꾸지 않고, 미인식 흐름 유지).
    """
    expecting_label = "(없음)"
    try:
        from intent.strategy_builder import required_missing

        expecting_label = required_missing(state) or "(없음)"
    except Exception:  # noqa: BLE001 — 컨텍스트 라벨 실패가 해석을 막지 않는다
        pass
    user_msg = (
        f"현재 설정: {_state_summary(state)}\n"
        f"지금 묻는 항목: {expecting_label}\n"
        f"사용자 입력: {text}"
    )
    raw = chat(_build_system_prompt(), user_msg, max_tokens=300)
    ops = _extract_ops(raw)
    if not ops:
        return None

    compact_input = _compact(text)
    text_nums = {float(n) for n in _NUM_RE.findall(text or "")}
    patch: dict = {}
    dropped: List[str] = []
    for op in ops[:6]:  # 상한 — 한 문장이 6개 넘는 조작을 담지 않는다(과잉 출력 가드)
        if not isinstance(op, dict):
            continue
        kind, field = op.get("op"), op.get("field")
        source = op.get("source_text")
        label = str(source or field or "요청")
        # 출처 인용 실재 확인(§ 3-1 (b)) — LLM이 인용한 조각이 실제 입력에 있어야 한다.
        if not isinstance(source, str) or _compact(source) not in compact_input:
            dropped.append(label)
            continue
        entry: Optional[dict] = None
        if kind == "set":
            entry = _validate_set(str(field), op.get("value"), state, text_nums)
        elif kind == "remove":
            template = _REMOVABLE_PATCH.get(str(field))
            filled = getattr(state, str(field), None) is not None if template else False
            if field == "rebalance_cycle":
                filled = state.rebalance_cycle not in (None, "none")
            if template and filled:
                entry = dict(template)
        elif kind == "reopen":
            entry = _reopen_patch(str(field), state)
        if entry is None:
            dropped.append(label)
            continue
        patch.update(entry)

    if not patch:
        return None
    # 청산 값 삭제로 청산이 전부 비면 청산 단계를 다시 연다(청산 필수 — FR-SA-002e와 동일).
    removed_risk = any(field in patch and patch[field] is None for field in RISK_FIELDS)
    if removed_risk and not any(
        patch.get(field, getattr(state, field)) is not None for field in RISK_FIELDS
    ):
        patch["risk_done"] = False
    notes: List[str] = []
    if dropped:
        quoted = ", ".join(f"'{d}'" for d in dict.fromkeys(dropped))
        notes.append(f"{quoted} 부분은 해석하지 못해 반영하지 않았어요. 값과 함께 다시 알려주시면 반영할게요.")
    return patch, notes
