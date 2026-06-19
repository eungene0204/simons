"""다양한 비-AI 전략 DSL 생성기.

지원 신호 공간(engine/signals.py·nl_parser.py 단일 소스)에서 제어된 랜덤 샘플링으로
서로 다른 ParsedStrategy를 만든다. strategy_hash로 dedup해 고유 전략만 반환한다.

설계 원칙:
- AI 모델 신호(ai_model/ai_drop_model)는 절대 생성하지 않는다(하드 가드).
- 시드 고정 시 결정적으로 동일한 코퍼스를 재현한다.
- 생성물은 to_backtest_request로 100% 변환 가능해야 한다(완결성: 진입+회전요건).
"""

from __future__ import annotations

import random
from typing import Callable, List

from engine.nl_parser import FundamentalFilter, ParsedStrategy, TechnicalSignal
from vector_memory.identity import strategy_hash_for

# AI 신호는 코퍼스에서 제외한다. 생성기가 실수로라도 만들지 않도록 명시.
FORBIDDEN_INDICATORS = frozenset({"ai_model", "ai_drop_model"})

UNIVERSES: List[List[str]] = [
    ["KOSPI200"],
    ["KOSPI"],
    ["KOSDAQ"],
    ["KOSPI", "KOSDAQ"],
]
# 유니버스 가중치 — KOSPI200 전용. KOSPI200(200종목)은 펀더멘털(per/pbr/roe/부채비율)이
# 로컬 캐시·parquet에 100% 완비돼 네트워크 호출 없이 빠르고 정확하게 백테스트된다.
# 비-KOSPI200(KOSDAQ/KOSPI 전체)은 캐시 누락 종목을 KIS 라이브로 조회해야 해 느리고(레이트리밋·
# 차단) 펀더멘털 필터가 degrade될 수 있어 코퍼스 품질을 해친다. 코치의 현실 유니버스(대형주)와도
# 부합한다. 다양성은 신호·필터·리스크·포트폴리오 차원에서 확보한다.
UNIVERSE_WEIGHTS: List[float] = [1.0, 0.0, 0.0, 0.0]

# ── 기술 신호 샘플러 ──────────────────────────────────────────────────────────
# 각 샘플러는 (buy 진입 신호, 그에 대응하는 옵셔널 sell 청산 신호)를 반환한다.
# 청산이 없는(None) 신호는 보유기간/리밸런싱/리스크가 회전을 담당한다.


def _ma_crossover(rng: random.Random) -> tuple[TechnicalSignal, TechnicalSignal | None]:
    short, long = rng.choice([(5, 20), (10, 60), (20, 120), (5, 60), (20, 60)])
    entry = TechnicalSignal(indicator="ma_crossover", signal_type="buy", short_period=short, long_period=long)
    exit_ = TechnicalSignal(indicator="ma_crossover", signal_type="sell", short_period=short, long_period=long)
    return entry, (exit_ if rng.random() < 0.6 else None)


def _rsi(rng: random.Random) -> tuple[TechnicalSignal, TechnicalSignal | None]:
    period = rng.choice([9, 14, 21])
    buy_val = rng.choice([25, 30, 35])
    entry = TechnicalSignal(indicator="rsi", signal_type="buy", period=period, operator="<", value=buy_val)
    sell_val = rng.choice([65, 70, 75])
    exit_ = TechnicalSignal(indicator="rsi", signal_type="sell", period=period, operator=">", value=sell_val)
    return entry, (exit_ if rng.random() < 0.6 else None)


def _macd(rng: random.Random) -> tuple[TechnicalSignal, TechnicalSignal | None]:
    mode = rng.choice(["crossover", "zero"])
    entry = TechnicalSignal(indicator="macd", signal_type="buy", mode=mode)
    exit_ = TechnicalSignal(indicator="macd", signal_type="sell", mode=mode)
    return entry, (exit_ if rng.random() < 0.5 else None)


def _bollinger(rng: random.Random) -> tuple[TechnicalSignal, TechnicalSignal | None]:
    entry = TechnicalSignal(indicator="bollinger_bands", signal_type="buy")
    exit_ = TechnicalSignal(indicator="bollinger_bands", signal_type="sell")
    return entry, (exit_ if rng.random() < 0.5 else None)


def _breakout(rng: random.Random) -> tuple[TechnicalSignal, TechnicalSignal | None]:
    lookback = rng.choice([20, 60, 120, 252])
    entry = TechnicalSignal(indicator="breakout", signal_type="buy", lookback_period=lookback)
    return entry, None


def _stochastic(rng: random.Random) -> tuple[TechnicalSignal, TechnicalSignal | None]:
    entry = TechnicalSignal(indicator="stochastic", signal_type="buy", mode="crossover")
    exit_ = TechnicalSignal(indicator="stochastic", signal_type="sell", mode="crossover")
    return entry, (exit_ if rng.random() < 0.5 else None)


def _cci(rng: random.Random) -> tuple[TechnicalSignal, TechnicalSignal | None]:
    period = rng.choice([14, 20])
    entry = TechnicalSignal(indicator="cci", signal_type="buy", period=period, operator="<", value=-100)
    exit_ = TechnicalSignal(indicator="cci", signal_type="sell", period=period, operator=">", value=100)
    return entry, (exit_ if rng.random() < 0.5 else None)


def _adx(rng: random.Random) -> tuple[TechnicalSignal, TechnicalSignal | None]:
    # ADX는 추세 강도 필터로 자주 쓰여 진입 보조에 적합. 단독 진입으로도 둔다.
    entry = TechnicalSignal(indicator="adx", signal_type="buy", period=14, operator=">", value=rng.choice([20, 25]))
    return entry, None


def _volume_spike(rng: random.Random) -> tuple[TechnicalSignal, TechnicalSignal | None]:
    entry = TechnicalSignal(indicator="volume_spike", signal_type="buy", period=20)
    return entry, None


def _ema(rng: random.Random) -> tuple[TechnicalSignal, TechnicalSignal | None]:
    short, long = rng.choice([(5, 20), (10, 60), (20, 120)])
    entry = TechnicalSignal(indicator="ema", signal_type="buy", short_period=short, long_period=long)
    return entry, None


_ENTRY_SIGNAL_SAMPLERS: List[Callable[[random.Random], tuple[TechnicalSignal, TechnicalSignal | None]]] = [
    _ma_crossover, _rsi, _macd, _bollinger, _breakout,
    _stochastic, _cci, _adx, _volume_spike, _ema,
]


# ── 펀더멘털 필터 샘플러 ──────────────────────────────────────────────────────

def _fundamental_filter(rng: random.Random, metric: str) -> FundamentalFilter:
    spec = {
        "per": ("<=", [8, 10, 12, 15]),
        "pbr": ("<=", [0.8, 1.0, 1.5]),
        "roe_or_gpa": (">=", [10, 15, 20]),
        "debt_ratio": ("<=", [50, 100, 150]),
        "market_cap": (">=", [1000, 5000, 10000]),
        "trading_value": (">=", [10, 50, 100]),
    }[metric]
    operator, values = spec
    return FundamentalFilter(metric=metric, operator=operator, value=float(rng.choice(values)))


_FUNDAMENTAL_METRICS = ["per", "pbr", "roe_or_gpa", "debt_ratio", "market_cap", "trading_value"]


# ── 리스크/포트폴리오 샘플러 ──────────────────────────────────────────────────

def _apply_risk(rng: random.Random, fields: dict) -> None:
    """전략 dict에 리스크 필드를 확률적으로 채운다(과반은 일부만 설정)."""
    if rng.random() < 0.55:
        fields["stop_loss_pct"] = float(rng.choice([5, 7, 10, 12, 15]))
    if rng.random() < 0.45:
        fields["take_profit_pct"] = float(rng.choice([10, 15, 20, 30]))
    if rng.random() < 0.25:
        fields["trailing_stop_pct"] = float(rng.choice([8, 10, 15]))
    if rng.random() < 0.15:
        fields["max_mdd_limit_pct"] = float(rng.choice([15, 20, 25]))


def _apply_turnover(rng: random.Random, fields: dict, *, has_exit: bool) -> None:
    """회전 요건(리밸런싱 또는 보유기간)을 채운다.

    청산 신호가 없는 전략은 회전 동력이 반드시 필요하므로 둘 중 하나를 강제한다.
    """
    use_rebalance = rng.random() < (0.5 if has_exit else 0.65)
    if use_rebalance:
        fields["rebalancing_period"] = rng.choice(["weekly", "monthly", "monthly", "quarterly"])
    elif not has_exit:
        fields["hold_period_days"] = rng.choice([21, 63, 126, 252])
    elif rng.random() < 0.4:
        fields["hold_period_days"] = rng.choice([63, 126, 252])


# ── 전략 아키타입 빌더 ────────────────────────────────────────────────────────

def _base_fields(rng: random.Random) -> dict:
    return {
        "description": "",
        "universe": rng.choices(UNIVERSES, weights=UNIVERSE_WEIGHTS, k=1)[0],
        "fundamental_filters": [],
        "entry_signals": [],
        "exit_signals": [],
        "max_positions": rng.choice([5, 8, 10, 15, 20, 30]),
        "backtest_period": rng.choice(["5y", "5y", "3y", "full"]),
    }


def _build_technical(rng: random.Random) -> dict:
    fields = _base_fields(rng)
    n = rng.choice([1, 1, 2])
    samplers = rng.sample(_ENTRY_SIGNAL_SAMPLERS, k=min(n, len(_ENTRY_SIGNAL_SAMPLERS)))
    has_exit = False
    for sampler in samplers:
        entry, exit_ = sampler(rng)
        fields["entry_signals"].append(entry)
        if exit_ is not None:
            fields["exit_signals"].append(exit_)
            has_exit = True
    _apply_turnover(rng, fields, has_exit=has_exit)
    _apply_risk(rng, fields)
    return fields


def _build_fundamental(rng: random.Random) -> dict:
    fields = _base_fields(rng)
    n = rng.choice([1, 1, 2, 3])
    for metric in rng.sample(_FUNDAMENTAL_METRICS, k=n):
        fields["fundamental_filters"].append(_fundamental_filter(rng, metric))
    _apply_turnover(rng, fields, has_exit=False)
    _apply_risk(rng, fields)
    return fields


def _build_hybrid(rng: random.Random) -> dict:
    fields = _base_fields(rng)
    for metric in rng.sample(_FUNDAMENTAL_METRICS, k=rng.choice([1, 2])):
        fields["fundamental_filters"].append(_fundamental_filter(rng, metric))
    entry, exit_ = rng.choice(_ENTRY_SIGNAL_SAMPLERS)(rng)
    fields["entry_signals"].append(entry)
    has_exit = False
    if exit_ is not None and rng.random() < 0.5:
        fields["exit_signals"].append(exit_)
        has_exit = True
    _apply_turnover(rng, fields, has_exit=has_exit)
    _apply_risk(rng, fields)
    return fields


def _build_ranking(rng: random.Random) -> dict:
    fields = _base_fields(rng)
    fields["ranking_metric"] = "return"
    fields["ranking_lookback_days"] = rng.choice([20, 60, 120, 252])
    # 랭킹 전략은 정기 리밸런싱으로 재선정한다.
    fields["rebalancing_period"] = rng.choice(["weekly", "monthly", "monthly", "quarterly"])
    if rng.random() < 0.4:
        for metric in rng.sample(_FUNDAMENTAL_METRICS, k=1):
            fields["fundamental_filters"].append(_fundamental_filter(rng, metric))
    _apply_risk(rng, fields)
    return fields


_ARCHETYPES: List[tuple[Callable[[random.Random], dict], float]] = [
    (_build_technical, 0.35),
    (_build_fundamental, 0.25),
    (_build_hybrid, 0.25),
    (_build_ranking, 0.15),
]


def _sample_strategy(rng: random.Random) -> ParsedStrategy:
    builders, weights = zip(*_ARCHETYPES)
    fields = rng.choices(builders, weights=weights, k=1)[0](rng)
    strategy = ParsedStrategy(**fields)
    _assert_no_ai(strategy)
    return strategy


def _assert_no_ai(strategy: ParsedStrategy) -> None:
    for sig in [*strategy.entry_signals, *strategy.exit_signals]:
        if sig.indicator in FORBIDDEN_INDICATORS:
            raise ValueError(f"AI 신호는 코퍼스에서 금지됨: {sig.indicator}")


def generate_strategies(count: int, *, seed: int = 0, max_attempts_factor: int = 200) -> List[ParsedStrategy]:
    """고유 전략 count개를 생성한다(strategy_hash 기준 dedup, 시드 결정적).

    아키타입 조합 공간이 유한하므로 max_attempts 안에 count를 못 채우면 가능한 만큼 반환한다.
    """
    rng = random.Random(seed)
    seen: set[str] = set()
    out: List[ParsedStrategy] = []
    max_attempts = count * max_attempts_factor
    attempts = 0
    while len(out) < count and attempts < max_attempts:
        attempts += 1
        strategy = _sample_strategy(rng)
        h = strategy_hash_for(strategy.model_dump())
        if h in seen:
            continue
        seen.add(h)
        out.append(strategy)
    return out
