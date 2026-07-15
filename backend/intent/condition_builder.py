"""Condition Builder — 재무 팩터 조건을 '스택'으로 누적하는 결정적 상태 머신.

[설계 의도] 기존 strategy_builder.py는 strategy_type을 하나 고르는 선형 파이프라인이라
"PER도 넣자 + 영업이익률도 추가 + ROE도" 같은 임의 재무 조건 누적을 표현하지 못한다.
이 모듈은 그 갭만 채운다 — 사용자가 언급한 재무 지표마다 Condition을 만들고, 필수
슬롯(operator·threshold)이 비면 Pending 상태로 두어 전략 완료를 막고, 슬롯을 채우도록
'추천 → 선택 → 직접 입력' 흐름으로 인터뷰한다.

[격리 원칙] strategy_builder.py를 건드리지 않는 독립 모듈이다. LLM 없이 결정적으로
동작하고, parser/state-transition/response-generation을 분리한다. 라우트·프론트 배선은
검증 후 별도로 진행한다.

[규제 안전] 조건을 '완성'하도록 도울 뿐, 특정 지표·기준값을 권하지 않는다. 추천값은
금융 교과서·실무 관례에서 널리 알려진 중립적 기준의 나열이며 우열을 말하지 않는다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field


# ─── 재무 지표 레지스트리 ──────────────────────────────────────────────────────────
# [단일 소스] label·unit·direction·recommend는 data/fundamental-factors.json이 정본이며
# 프론트(app/analytics/new/parsedStrategyMerge.ts)와 공유한다 — 두 곳에 하드코딩해 drift하던
# 것을 제거. 지표 언급 인식 pattern만 언어별로 동작이 달라(한글 경계 처리 등) Python 로컬로 둔다.
# direction=관례 연산자(사용자가 방향을 안 밝히면 이 값 사용). key=FundamentalFilter.metric Literal.

@dataclass(frozen=True)
class MetricSpec:
    key: str
    label: str
    unit: str            # 표시 단위: "%", "억", "배", ""
    direction: str       # 관례 연산자: ">=" 또는 "<="
    recommend: tuple[float, ...]
    pattern: "re.Pattern[str]"


def _c(p: str) -> "re.Pattern[str]":
    return re.compile(p, re.IGNORECASE)


# 지표 인식 별칭(Python 로컬). 라틴 약어는 \b 대신 라틴 문자 lookaround로 경계를 잡는다 —
# "PER도"의 '도'(한글=word 문자)가 \b 뒤 경계를 없애 매칭이 실패하던 버그. 'super'의 'per'는
# 앞이 라틴이라 제외된다. 배당 계열은 JSON '순서'로 구체(배당성향/배당성장)를 배당수익률보다 먼저 본다.
_PATTERNS: dict[str, "re.Pattern[str]"] = {
    "per": _c(r"(?<![a-z])per(?![a-z])|피이알|주가수익비율"),
    "pbr": _c(r"(?<![a-z])pbr(?![a-z])|피비알|주가순자산"),
    "psr": _c(r"(?<![a-z])psr(?![a-z])|피에스알|주가매출"),
    "ev_ebitda": _c(r"ev\s*/?\s*ebitda|이브이에비타"),
    "roe_or_gpa": _c(r"(?<![a-z])roe(?![a-z])|자기자본이익|자기자본수익"),
    "roa": _c(r"(?<![a-z])roa(?![a-z])|총자본순이익|총자산이익"),
    "debt_ratio": _c(r"부채비율"),
    "current_ratio": _c(r"유동비율"),
    "quick_ratio": _c(r"당좌비율"),
    "reserve_ratio": _c(r"유보율"),
    "gross_margin": _c(r"매출총이익률?|총이익률|gross\s*margin"),
    "operating_margin": _c(r"영업이익률|영업\s*마진|operating\s*margin"),
    "net_margin": _c(r"순이익률|순\s*마진|net\s*margin"),
    "revenue_growth": _c(r"매출액?\s*증가율|매출\s*성장|revenue\s*growth"),
    "operating_income_growth": _c(r"영업이익\s*증가율|영업이익\s*성장"),
    "net_income_growth": _c(r"순이익\s*증가율|순이익\s*성장"),
    "market_cap": _c(r"시가총액|시총|market\s*cap"),
    "trading_value": _c(r"거래\s*대금"),
    "payout_rate": _c(r"배당\s*성향|payout"),
    "dividend_growth": _c(r"배당\s*성장|배당을?\s*(?:꾸준히\s*)?늘"),
    "dividend_yield": _c(r"배당\s*수익률|배당률|고배당|배당"),
}

# 프론트와 공유하는 정본 데이터(레포 루트 data/). parents[2]=repo root(intent→backend→root).
_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "data" / "fundamental-factors.json"


def _load_registry() -> tuple[MetricSpec, ...]:
    """공유 JSON에서 지표 데이터를 읽어 Python 로컬 패턴과 결합해 레지스트리를 만든다."""
    with open(_REGISTRY_PATH, encoding="utf-8") as f:
        items = json.load(f)
    return tuple(
        MetricSpec(
            key=item["key"], label=item["label"], unit=item["unit"],
            direction=item["direction"], recommend=tuple(item["recommend"]),
            pattern=_PATTERNS[item["key"]],
        )
        for item in items
    )


_REGISTRY: tuple[MetricSpec, ...] = _load_registry()
_BY_KEY: dict[str, MetricSpec] = {m.key: m for m in _REGISTRY}


def _spec(key: str) -> MetricSpec:
    return _BY_KEY[key]


# Vocabulary엔 있으나 현재 데이터셋으로 계산할 수 없는 지표 — 조용히 무시하지 않고 명확히 안내한다.
_UNSUPPORTED: tuple[tuple["re.Pattern[str]", str], ...] = (
    (_c(r"(?<![a-z])peg(?![a-z])"), "PEG(주가수익성장비율)는 예상 성장률 데이터가 없어 현재 사용할 수 없어요."),
    (_c(r"(?<![a-z])pcr(?![a-z])|주가현금흐름"), "PCR(주가현금흐름비율)은 아직 데이터셋에 없어 현재 사용할 수 없어요."),
)


# ─── 상태 모델 ────────────────────────────────────────────────────────────────────

class Condition(BaseModel):
    """재무 조건 하나. operator·value가 모두 채워지면 Complete, 아니면 Pending."""

    metric: str
    operator: Optional[str] = None       # "<", ">", "<=", ">="
    value: Optional[float] = None

    @property
    def complete(self) -> bool:
        return self.operator is not None and self.value is not None


class ConditionState(BaseModel):
    """조건 스택 대화 상태. 프론트가 무상태 step 호출 사이에 보관·재전송한다."""

    conditions: List[Condition] = Field(default_factory=list)
    # 슬롯 인터뷰 단계: None=대기 없음, "choice"=추천 칩 제시 중, "value"=직접 입력값 대기,
    # "duplicate"=중복 지표 처리 대기(dup_metric 참조).
    awaiting: Optional[str] = None
    dup_metric: Optional[str] = None


class ConditionStepResult(BaseModel):
    state: ConditionState
    reply: str = ""
    suggestions: List[str] = Field(default_factory=list)
    # collecting=조건 더 받음, confirmed=완료 조건으로 전략 조립, reset=초기화, exited=빌더 종료
    status: str = "collecting"
    prompt: Optional[str] = None         # confirmed일 때 사람이 읽는 전략 설명
    parsed: Optional[dict] = None        # confirmed일 때 ParsedStrategy dump


def _pending(state: ConditionState) -> Optional[Condition]:
    """아직 완성되지 않은(Pending) 조건을 반환한다. 동시에 하나만 존재한다."""
    for c in state.conditions:
        if not c.complete:
            return c
    return None


def _find_complete(state: ConditionState, metric: str) -> Optional[Condition]:
    for c in state.conditions:
        if c.metric == metric and c.complete:
            return c
    return None


# ─── 파서(연산자·값·지표 인식) ─────────────────────────────────────────────────────

# 순서: 더 구체적(초과/미만)을 이상/이하보다 먼저. '넘'은 초과로 본다.
_OP_WORDS: tuple[tuple["re.Pattern[str]", str], ...] = (
    (_c(r"초과|넘"), ">"),
    (_c(r"미만"), "<"),
    (_c(r"이상|넘게|위로|이상으로"), ">="),
    (_c(r"이하|아래|밑으로|이내"), "<="),
)

_DIRECT_RE = _c(r"직접\s*입력|직접")
_DEFAULT_RE = _c(r"기본|추천|아무거나|알아서|그냥|상관\s*없|몰라")
_NUM_RE = _c(r"\d+(?:\.\d+)?")


def _parse_operator(text: str) -> Optional[str]:
    for pat, op in _OP_WORDS:
        if pat.search(text):
            return op
    return None


def _parse_value(text: str, spec: MetricSpec) -> Optional[float]:
    """숫자 기준값을 뽑는다. 억 단위 지표는 '조'(=10000억)를 함께 인식한다."""
    if spec.unit == "억":
        m = re.search(r"(\d+(?:\.\d+)?)\s*조", text)
        if m:
            return float(m.group(1)) * 10000
    m = _NUM_RE.search(text)
    return float(m.group(0)) if m else None


def detect_metric(text: str) -> Optional[str]:
    """텍스트에서 지원 재무 지표를 인식한다(레지스트리 순서 = 우선순위). 없으면 None."""
    for spec in _REGISTRY:
        if spec.pattern.search(text or ""):
            return spec.key
    return None


def detect_unsupported(text: str) -> Optional[str]:
    for pat, msg in _UNSUPPORTED:
        if pat.search(text or ""):
            return msg
    return None


# ─── 제어어 / 완료 감지 ────────────────────────────────────────────────────────────

# '됐어'는 "다 됐어"(완료)와 겹쳐 취소에서 제외한다 — 완료는 _DONE_RE가 잡는다.
_CANCEL_RE = _c(r"취소|관[두둬둘]|그만둘|그만할|중단")
_RESTART_RE = _c(r"처음부터|새로\s*(?:시작|만들)|다시\s*시작|리셋|초기화")
# 조건 추가를 마치고 백테스트로 넘어가려는 신호. '없어/더 없어/그만 추가'도 완료로 본다(취소 아님).
_DONE_RE = _c(r"이대로|백테스트|완료|다\s*됐|충분|끝(?:내|났|이)|더\s*(?:없|안|추가\s*안)|없어(?:요)?$|그만\s*추가")
# 진행 중인 미완성 조건 하나만 빼고 싶다는 신호(전체 취소 아님) — Pending을 드롭하고 이어간다.
_SKIP_RE = _c(r"빼|생략|건너|그건\s*됐|안\s*할래|넘어가")


def detect_control(text: str) -> Optional[str]:
    t = text or ""
    if _RESTART_RE.search(t):
        return "restart"
    if _CANCEL_RE.search(t):
        return "cancel"
    return None


# ─── 표현(칩·문장·요약) ────────────────────────────────────────────────────────────

def _fmt(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else str(v)


def _op_word(operator: str) -> str:
    return {">=": "이상", ">": "초과", "<=": "이하", "<": "미만"}.get(operator, "")


def _value_label(value: float, spec: MetricSpec) -> str:
    """'1조'처럼 억 단위 큰 값은 조로 축약해 보여준다."""
    if spec.unit == "억" and value >= 10000 and (value / 10000).is_integer():
        return f"{_fmt(value / 10000)}조"
    return f"{_fmt(value)}{spec.unit}"


def _recommend_chips(spec: MetricSpec) -> list[str]:
    word = _op_word(spec.direction)
    chips = [f"{_value_label(v, spec)} {word}" for v in spec.recommend]
    chips.append("직접 입력")
    return chips


def _condition_phrase(c: Condition) -> str:
    spec = _spec(c.metric)
    return f"{spec.label} {_value_label(c.value, spec)} {_op_word(c.operator)}"


def _summary(state: ConditionState) -> str:
    done = [c for c in state.conditions if c.complete]
    if not done:
        return ""
    return "현재 조건: " + ", ".join(_condition_phrase(c) for c in done)


# ─── 질문 생성 ────────────────────────────────────────────────────────────────────

INTRO_REPLY = (
    "어떤 재무 조건부터 넣어볼까요? 지표 이름을 말씀해 주시면 자주 쓰는 기준을 추천해 드릴게요.\n"
    "(예: PER, PBR, ROE, 영업이익률, 배당수익률, 부채비율, 시가총액)"
)
INTRO_CHIPS = ["PER", "PBR", "ROE", "영업이익률", "배당수익률"]


def _choice_question(spec: MetricSpec) -> tuple[str, list[str]]:
    return (
        f"{spec.label} 조건을 추가할게요. 자주 쓰는 기준입니다.",
        _recommend_chips(spec),
    )


def _value_question(spec: MetricSpec, operator: str) -> str:
    unit = spec.unit or ""
    return f"{spec.label}을(를) 몇{unit} {_op_word(operator)}으로 할까요?"


def _add_more_question(state: ConditionState) -> tuple[str, list[str]]:
    used = {c.metric for c in state.conditions}
    chips = [_spec(k).label for k in ("per", "pbr", "roe_or_gpa", "dividend_yield", "operating_margin")
             if k not in used][:4]
    chips.append("이대로 백테스트")
    return ("다른 조건도 추가할까요? 없으면 이대로 백테스트할 수 있어요.", chips)


def _reask(state: ConditionState) -> tuple[str, list[str]]:
    """현재 대기 단계에 맞는 질문을 다시 생성한다(빈 입력·인식 실패 시)."""
    if state.awaiting == "duplicate" and state.dup_metric:
        existing = _find_complete(state, state.dup_metric)
        spec = _spec(state.dup_metric)
        return (
            f"이미 {_condition_phrase(existing)} 조건이 있어요. 어떻게 할까요?",
            ["수정", "삭제", "유지", "다른 조건 추가"],
        )
    pending = _pending(state)
    if pending is not None:
        spec = _spec(pending.metric)
        if state.awaiting == "value":
            operator = pending.operator or spec.direction
            return (_value_question(spec, operator), [])
        return _choice_question(spec)
    if any(c.complete for c in state.conditions):
        return _add_more_question(state)
    return (INTRO_REPLY, INTRO_CHIPS)


# ─── 조립(완료 조건 → ParsedStrategy) ──────────────────────────────────────────────

def build_parsed_strategy(state: ConditionState):
    """완료된 재무 조건으로 스크리닝 전략(ParsedStrategy)을 조립한다. 완료 조건이 없으면 None.

    재무 필터만으로 종목을 거르는 스크리닝 전략이다(진입/청산 기술 신호 없음). 포트폴리오·
    리밸런싱은 중립적 기본값(최대 10종목·매월)을 쓴다 — 조건 스택이 이 모듈의 책임이고,
    보유수·리밸런싱·리스크 상세는 후속(라우트/프론트 배선) 단계에서 확장한다."""
    done = [c for c in state.conditions if c.complete]
    if not done:
        return None
    from engine.nl_parser import ParsedStrategy, FundamentalFilter

    filters = [FundamentalFilter(metric=c.metric, operator=c.operator, value=c.value) for c in done]
    return ParsedStrategy(
        description=synthesize_prompt(state),
        universe=["KOSPI", "KOSDAQ"],
        fundamental_filters=filters,
        max_positions=10,
        rebalancing_period="monthly",
    )


def synthesize_prompt(state: ConditionState) -> str:
    done = [c for c in state.conditions if c.complete]
    conds = ", ".join(_condition_phrase(c) for c in done)
    return f"코스피·코스닥 종목 중 {conds}인 종목을 최대 10종목 매수, 매월 리밸런싱"


# ─── 오케스트레이션 ──────────────────────────────────────────────────────────────

CANCEL_REPLY = "알겠습니다. 조건 구성을 취소했어요. 다른 아이디어가 있으면 언제든 말씀해 주세요."
RESTART_PREFIX = "처음부터 새로 구성해볼게요.\n\n"


def _complete_pending(state: ConditionState, operator: str, value: float) -> ConditionState:
    """Pending 조건의 슬롯을 채워 Complete로 만들고 대기 상태를 해제한다."""
    conditions = [c.model_copy() for c in state.conditions]
    for c in conditions:
        if not c.complete:
            c.operator, c.value = operator, value
            break
    return state.model_copy(update={"conditions": conditions, "awaiting": None})


def _confirm(state: ConditionState) -> ConditionStepResult:
    parsed = build_parsed_strategy(state)
    return ConditionStepResult(
        state=state, status="confirmed",
        prompt=synthesize_prompt(state),
        parsed=parsed.model_dump() if parsed is not None else None,
    )


def _reask_result(state: ConditionState, prefix: str = "") -> ConditionStepResult:
    msg, sug = _reask(state)
    return ConditionStepResult(state=state, reply=prefix + msg, suggestions=sug, status="collecting")


def step(state: ConditionState, text: str) -> ConditionStepResult:
    """조건 빌더의 한 턴을 처리한다.

    빈 입력은 상태를 바꾸지 않고 현재(첫) 질문을 그대로 보여준다 — 빌더 진입 직후 첫 질문을
    능동적으로 띄우는 데 쓴다. LLM 없이 결정적으로 동작한다."""
    if not (text or "").strip():
        return _reask_result(state)

    ctrl = detect_control(text)
    if ctrl == "cancel":
        return ConditionStepResult(state=ConditionState(), reply=CANCEL_REPLY, status="exited")
    if ctrl == "restart":
        fresh = ConditionState()
        return _reask_result(fresh, prefix=RESTART_PREFIX)

    # ── 중복 지표 처리 대기 ──────────────────────────────────────────────────────
    if state.awaiting == "duplicate":
        return _resolve_duplicate(state, text)

    # ── Pending 슬롯 인터뷰(추천 선택 / 직접 입력값) ──────────────────────────────
    pending = _pending(state)
    if pending is not None:
        return _fill_pending(state, pending, text)

    # ── 대기 없음: 완료 신호 또는 새 지표 인식 ────────────────────────────────────
    return _handle_new(state, text)


def _drop_pending(state: ConditionState) -> ConditionState:
    """미완성(Pending) 조건 하나를 제거하고 대기 상태를 해제한다."""
    conditions = [c for c in state.conditions if c.complete]
    return state.model_copy(update={"conditions": conditions, "awaiting": None})


def _fill_pending(state: ConditionState, pending: Condition, text: str) -> ConditionStepResult:
    spec = _spec(pending.metric)

    # 진행 중인 미완성 조건만 빼고 싶다는 신호 → 그 조건을 드롭하고 이어간다(전체 취소 아님).
    if _SKIP_RE.search(text):
        dropped = _drop_pending(state)
        return _reask_result(dropped, prefix=f"{spec.label} 조건은 건너뛸게요.\n\n")

    # 완료 신호("이대로 백테스트")인데 이 조건이 아직 미완성 → 빼고 마무리한다. 다른 완료 조건이
    # 있으면 확정(Pending은 차단하되 명시적 종료 의사는 존중), 없으면 처음 질문으로 돌아간다.
    if _DONE_RE.search(text) and _parse_value(text, spec) is None:
        dropped = _drop_pending(state)
        if any(c.complete for c in dropped.conditions):
            return _confirm(dropped)
        return _reask_result(dropped)

    # "직접 입력" 토글 — 관례 연산자로 값만 묻는 단계로 전환한다(프론트가 채팅창을 다시 띄운다).
    if _DIRECT_RE.search(text) and _parse_value(text, spec) is None:
        operator = pending.operator or spec.direction
        new_state = state.model_copy(update={"awaiting": "value"})
        # pending.operator를 관례값으로 확정해 재질문/완료에서 일관되게 쓴다.
        return _set_pending_operator_and_ask(new_state, operator)

    operator = _parse_operator(text) or pending.operator or spec.direction
    value = _parse_value(text, spec)
    if value is None:
        # 값을 못 뽑음 — 같은 질문을 다시 한다(초보자가 '기본' 선택 시 첫 추천값 사용).
        if _DEFAULT_RE.search(text):
            value = float(spec.recommend[0])
        else:
            return _reask_result(state)

    new_state = _complete_pending(state, operator, value)
    ack = f"좋아요. {_condition_phrase(new_state.conditions[_pending_index(new_state)])} 조건을 추가했어요.\n\n"
    msg, sug = _add_more_question(new_state)
    return ConditionStepResult(state=new_state, reply=ack + msg, suggestions=sug, status="collecting")


def _pending_index(state: ConditionState) -> int:
    """방금 완성된 마지막 조건의 인덱스(ack 문구용)."""
    return len(state.conditions) - 1


def _set_pending_operator_and_ask(state: ConditionState, operator: str) -> ConditionStepResult:
    conditions = [c.model_copy() for c in state.conditions]
    for c in conditions:
        if not c.complete:
            c.operator = operator
            break
    new_state = state.model_copy(update={"conditions": conditions})
    pending = _pending(new_state)
    spec = _spec(pending.metric)
    return ConditionStepResult(
        state=new_state, reply=_value_question(spec, operator), suggestions=[], status="collecting",
    )


def _handle_new(state: ConditionState, text: str) -> ConditionStepResult:
    if _DONE_RE.search(text) and any(c.complete for c in state.conditions):
        return _confirm(state)

    metric = detect_metric(text)
    if metric is None:
        unsupported = detect_unsupported(text)
        if unsupported:
            return _reask_result(state, prefix=unsupported + "\n\n")
        # 지표를 못 알아들음 — 완료 조건이 있으면 '더 추가?'로, 없으면 인트로로 되묻는다.
        return _reask_result(state)

    spec = _spec(metric)

    # 이미 완료된 같은 지표 → 중복 처리 대기로 전환(수정/삭제/유지/추가).
    if _find_complete(state, metric) is not None:
        new_state = state.model_copy(update={"awaiting": "duplicate", "dup_metric": metric})
        return _reask_result(new_state)

    # 새 조건 추가. 인라인으로 값이 함께 오면("PER 10 이하 넣자") 곧바로 완료한다.
    operator = _parse_operator(text)
    value = _parse_value(text, spec)
    conditions = state.conditions + [Condition(metric=metric, operator=operator, value=value)]
    new_state = state.model_copy(update={"conditions": conditions, "awaiting": None})

    if value is not None:
        # 인라인 완료 — 연산자 미언급이면 관례값으로 채운다.
        completed = _complete_pending(new_state, operator or spec.direction, value)
        ack = f"좋아요. {_condition_phrase(completed.conditions[-1])} 조건을 추가했어요.\n\n"
        msg, sug = _add_more_question(completed)
        return ConditionStepResult(state=completed, reply=ack + msg, suggestions=sug, status="collecting")

    # 값 없음 → 추천 칩 제시(choice 단계).
    new_state = new_state.model_copy(update={"awaiting": "choice"})
    msg, sug = _choice_question(spec)
    return ConditionStepResult(state=new_state, reply=msg, suggestions=sug, status="collecting")


_DUP_MODIFY_RE = _c(r"수정|바꿔|변경|고쳐|다시")
_DUP_REMOVE_RE = _c(r"삭제|빼|제거|없애")
_DUP_KEEP_RE = _c(r"유지|그대로|놔둬|둬")
_DUP_ADD_RE = _c(r"추가|다른|새")


def _resolve_duplicate(state: ConditionState, text: str) -> ConditionStepResult:
    metric = state.dup_metric
    spec = _spec(metric) if metric else None

    if metric and _DUP_REMOVE_RE.search(text):
        conditions = [c for c in state.conditions if c.metric != metric]
        new_state = state.model_copy(update={
            "conditions": conditions, "awaiting": None, "dup_metric": None,
        })
        return _reask_result(new_state, prefix=f"{spec.label} 조건을 삭제했어요.\n\n")

    if metric and _DUP_MODIFY_RE.search(text):
        # 기존 조건을 Pending으로 되돌려 추천 흐름을 다시 태운다.
        conditions = [c for c in state.conditions if c.metric != metric]
        conditions.append(Condition(metric=metric))
        new_state = state.model_copy(update={
            "conditions": conditions, "awaiting": "choice", "dup_metric": None,
        })
        msg, sug = _choice_question(spec)
        return ConditionStepResult(state=new_state, reply=msg, suggestions=sug, status="collecting")

    if _DUP_KEEP_RE.search(text):
        new_state = state.model_copy(update={"awaiting": None, "dup_metric": None})
        return _reask_result(new_state, prefix="기존 조건을 그대로 둘게요.\n\n")

    # '다른 조건 추가' 또는 새 지표 언급 → 중복 대기를 풀고 일반 처리로 넘긴다.
    if _DUP_ADD_RE.search(text) or detect_metric(text):
        new_state = state.model_copy(update={"awaiting": None, "dup_metric": None})
        return _handle_new(new_state, text)

    return _reask_result(state)


def is_empty(state: ConditionState) -> bool:
    return state == ConditionState()


# ─── 수정 대화용 되묻기 감지 (무상태) ───────────────────────────────────────────────
# 기존 전략 요약 카드에 "영업이익률을 추가해 볼까?"처럼 팩터를 추가하려는데 operator/value가
# 비면, 수정 파서(parse_modification)로 넘기기 전에 이 함수가 되묻기 페이로드를 만든다.
# [무상태 설계] 프론트는 칩("15% 이상") 클릭 시 f"{label} {chip}"을 일반 수정 메시지로
# 되보내면 된다 — 기존 _merge_fundamental_filters가 기존 필터를 보존한 채 완성한다.

# 팩터를 '추가/설정'하려는 의도 cue. 정의 질문("영업이익률이 뭐야")과 구분하기 위한 최소 신호.
_ADD_CUE_RE = _c(r"추가|넣|더해|더하|포함|고려|볼까|보자|쓰자|써보|적용|반영|걸[어자]|설정")
_DEFINE_RE = _c(r"뭐야|뭐예요|뭔가요|뭐죠|뭐지|무엇|무슨\s*뜻|뜻이|뜻은|의미가|의미는|설명해")


def clarification_for_add(text: str) -> Optional[dict]:
    """수정 대화에서 '재무 팩터 추가' 의도인데 operator/value 슬롯이 비었으면 되묻기 페이로드를
    반환한다. 값이 이미 있거나(기존 modify가 처리)·팩터 미언급·정의 질문이면 None.

    반환: {metric, label, question, suggestions}. suggestions는 추천 칩(+직접 입력)."""
    t = text or ""
    if _DEFINE_RE.search(t) or not _ADD_CUE_RE.search(t):
        return None
    metric = detect_metric(t)
    if metric is None:
        return None
    spec = _spec(metric)
    if _parse_value(t, spec) is not None:
        return None  # 값이 이미 있으면 기존 modify 경로가 완결 처리
    return {
        "metric": metric,
        "label": spec.label,
        "question": f"{spec.label} 몇{spec.unit} {_op_word(spec.direction)}일 때 진입할까요?",
        # 칩은 클릭 시 그대로 수정 메시지로 재전송되므로(handleSuggestionClick→handleSend)
        # 라벨이 붙은 '완결 지시문'이어야 parse_modification이 병합할 수 있다. "직접 입력"은
        # 프론트가 자동으로 덧붙이므로 여기 넣지 않는다.
        "suggestions": [
            f"{spec.label} {_value_label(v, spec)} {_op_word(spec.direction)}"
            for v in spec.recommend
        ],
    }
