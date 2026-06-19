"""ParsedStrategy → 한국어 전략 설명 렌더러 (코퍼스 임베딩 텍스트).

문장 템플릿 + 요소별 문구 뱅크 + 동의어/접속 변형으로 사용자가 입력할 법한
자연어 전략 설명을 결정적으로 생성한다(전략 해시로 시드 고정 → 재현 가능).
LLM 없이 동작한다.
"""

from __future__ import annotations

import random

from engine.nl_parser import FundamentalFilter, ParsedStrategy, TechnicalSignal
from vector_memory.identity import strategy_hash_for

_UNIVERSE_PHRASES = {
    "KOSPI200": ["코스피200", "코스피200 종목", "코스피 대형주", "코스피200 우량주"],
    "KOSPI": ["코스피", "코스피 전체 종목", "코스피 시장"],
    "KOSDAQ": ["코스닥", "코스닥 종목", "코스닥 시장"],
    "KOSPI_KOSDAQ": ["코스피·코스닥 전체", "전체 시장", "코스피와 코스닥 모두"],
}


def _universe_phrase(rng: random.Random, universe: list[str]) -> str:
    key = "_".join(sorted(universe)) if universe else "KOSPI200"
    if key == "KOSDAQ":
        bank = _UNIVERSE_PHRASES["KOSDAQ"]
    elif key in ("KOSPI_KOSDAQ", "KOSDAQ_KOSPI"):
        bank = _UNIVERSE_PHRASES["KOSPI_KOSDAQ"]
    elif key == "KOSPI":
        bank = _UNIVERSE_PHRASES["KOSPI"]
    else:
        bank = _UNIVERSE_PHRASES["KOSPI200"]
    return rng.choice(bank)


def _filter_phrase(rng: random.Random, f: FundamentalFilter) -> str:
    v = int(f.value) if float(f.value).is_integer() else f.value
    if f.metric == "per":
        return rng.choice([f"PER {v}배 이하", f"PER이 {v}배보다 낮은", f"저PER({v}배 이하)"])
    if f.metric == "pbr":
        return rng.choice([f"PBR {v}배 이하 저평가", f"PBR이 {v}배 이하인", f"저PBR({v}배 이하) 가치주"])
    if f.metric == "roe_or_gpa":
        return rng.choice([f"ROE {v}% 이상 우량", f"자기자본이익률이 {v}%를 넘는", f"수익성 높은(ROE {v}%+)"])
    if f.metric == "debt_ratio":
        return rng.choice([f"부채비율 {v}% 이하 재무 안정", f"부채비율이 {v}%보다 낮은"])
    if f.metric == "market_cap":
        return rng.choice([f"시가총액 {v}억원 이상 대형주", f"시총 {v}억 넘는 대형"])
    if f.metric == "trading_value":
        return rng.choice([f"일평균 거래대금 {v}억원 이상", f"거래대금이 {v}억 이상으로 유동성 좋은"])
    return f"{f.metric} {f.operator} {v}"


def _signal_phrase(rng: random.Random, sig: TechnicalSignal, *, is_exit: bool) -> str:
    verb = rng.choice(["매도", "청산"]) if is_exit else "매수"
    ind = sig.indicator
    if ind == "ma_crossover":
        s, l = sig.short_period or 5, sig.long_period or 20
        if is_exit:
            return rng.choice([f"{s}일선이 {l}일선을 하향 돌파(데드크로스)하면 {verb}", f"데드크로스가 나오면 {verb}"])
        return rng.choice([f"{s}일선이 {l}일선을 상향 돌파(골든크로스)하면 {verb}", f"{s}/{l}일 골든크로스에서 {verb}"])
    if ind == "rsi":
        p, v = sig.period or 14, sig.value
        if is_exit:
            return rng.choice([f"RSI가 {v} 이상으로 과매수되면 {verb}", f"RSI({p})가 {v}을 넘으면 {verb}"])
        return rng.choice([f"RSI({p})가 {v} 이하로 과매도되면 {verb}", f"RSI가 {v} 밑으로 떨어지면 {verb}"])
    if ind == "macd":
        if sig.mode == "zero":
            return rng.choice([f"MACD가 0선을 {'하향' if is_exit else '상향'} 돌파하면 {verb}"])
        return rng.choice([f"MACD가 시그널선을 {'하향' if is_exit else '상향'} 돌파하면 {verb}", f"MACD {'데드' if is_exit else '골든'}크로스에서 {verb}"])
    if ind == "bollinger_bands":
        band = "상단" if is_exit else "하단"
        return rng.choice([f"주가가 볼린저밴드 {band}에 닿으면 {verb}", f"볼린저밴드 {band} 터치 시 {verb}"])
    if ind == "breakout":
        lb = sig.lookback_period or 20
        return rng.choice([f"최근 {lb}일 신고가를 돌파하면 {verb}", f"{lb}일 박스권 상단을 뚫으면 {verb}"])
    if ind == "stochastic":
        return rng.choice([f"스토캐스틱 {'매도' if is_exit else '매수'} 교차가 나오면 {verb}"])
    if ind == "cci":
        return rng.choice([f"CCI가 {'+100 이상이면' if is_exit else '-100 이하면'} {verb}"])
    if ind == "adx":
        v = sig.value or 25
        return rng.choice([f"ADX가 {v} 이상으로 추세가 강할 때 {verb}", f"추세 강도(ADX {v}+)가 확인되면 {verb}"])
    if ind == "volume_spike":
        return rng.choice([f"거래량이 평소보다 급증하면 {verb}", f"거래량 급증 시 {verb}"])
    if ind == "ema":
        s, l = sig.short_period or 5, sig.long_period or 20
        return rng.choice([f"{s}일·{l}일 지수이동평균이 정배열이면 {verb}"])
    return f"{ind} 신호에서 {verb}"


def _hold_phrase(rng: random.Random, days: int) -> str:
    months = round(days / 21)
    if months >= 12:
        unit = f"{round(days / 252)}년"
    elif months >= 1:
        unit = f"{months}개월"
    else:
        unit = f"{days}거래일"
    return rng.choice([f"한 번 사면 최소 {unit}은 보유", f"{unit} 정도 들고 가는", f"보유기간은 {unit}"])


_REBALANCE_PHRASES = {
    "weekly": ["매주 리밸런싱", "주간 단위로 종목 교체"],
    "monthly": ["매월 리밸런싱", "월 1회 종목 재선정"],
    "quarterly": ["분기마다 리밸런싱", "분기 단위 재구성"],
    "yearly": ["매년 리밸런싱"],
    "daily": ["매일 리밸런싱"],
    "bimonthly": ["두 달에 한 번 리밸런싱"],
}


def render_description(strategy: ParsedStrategy) -> str:
    """전략 → 자연어 한국어 설명. 전략 해시로 시드를 고정해 재현 가능하다."""
    rng = random.Random(strategy_hash_for(strategy.model_dump()))
    clauses: list[str] = []

    universe = _universe_phrase(rng, strategy.universe)

    # 선정(펀더멘털 + 랭킹)
    select_bits: list[str] = []
    for f in strategy.fundamental_filters:
        select_bits.append(_filter_phrase(rng, f))
    if strategy.ranking_metric == "return":
        lb = strategy.ranking_lookback_days or 60
        select_bits.append(rng.choice([f"최근 {lb}일 수익률 상위", f"{lb}일 모멘텀이 강한 상위"]))

    if select_bits:
        joined = rng.choice([", ", "이고 ", " 그리고 "]).join(select_bits)
        clauses.append(rng.choice([
            f"{universe}에서 {joined} 종목을 고르고",
            f"{universe} 중 {joined} 종목만 골라서",
        ]))
    else:
        clauses.append(rng.choice([f"{universe}에서", f"{universe}를 대상으로"]))

    # 진입 신호
    for sig in strategy.entry_signals:
        clauses.append(_signal_phrase(rng, sig, is_exit=False))

    # 포트폴리오
    n = strategy.max_positions
    clauses.append(rng.choice([f"최대 {n}종목으로 분산", f"{n}종목에 나눠 담고", f"동시 보유는 {n}종목"]))

    # 청산 신호
    for sig in strategy.exit_signals:
        clauses.append(_signal_phrase(rng, sig, is_exit=True))

    # 회전(리밸런싱/보유기간)
    if strategy.rebalancing_period and strategy.rebalancing_period != "none":
        clauses.append(rng.choice(_REBALANCE_PHRASES.get(strategy.rebalancing_period, ["정기 리밸런싱"])))
    elif strategy.hold_period_days:
        clauses.append(_hold_phrase(rng, strategy.hold_period_days))

    # 리스크
    risk_bits: list[str] = []
    if strategy.stop_loss_pct is not None:
        v = int(strategy.stop_loss_pct)
        risk_bits.append(rng.choice([f"-{v}% 손절", f"{v}% 손실에서 손절"]))
    if strategy.take_profit_pct is not None:
        v = int(strategy.take_profit_pct)
        risk_bits.append(rng.choice([f"{v}% 익절", f"수익 {v}%에서 익절"]))
    if strategy.trailing_stop_pct is not None:
        v = int(strategy.trailing_stop_pct)
        risk_bits.append(rng.choice([f"최고가 대비 {v}% 하락 시 트레일링 청산"]))
    if strategy.max_mdd_limit_pct is not None:
        v = int(strategy.max_mdd_limit_pct)
        risk_bits.append(rng.choice([f"전체 낙폭이 {v}%를 넘으면 전량 청산"]))
    if risk_bits:
        clauses.append("리스크 관리로 " + ", ".join(risk_bits) + "을 둔다")

    # 조립: 절들을 자연스럽게 잇는다.
    body = clauses[0]
    for clause in clauses[1:]:
        body += rng.choice([", ", ". ", " "]) + clause
    if not body.rstrip().endswith(("다", ".")):
        body += rng.choice([" 전략.", " 전략입니다.", "."])
    return body
