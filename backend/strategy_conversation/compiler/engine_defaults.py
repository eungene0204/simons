"""엔진 실효 기본값 — 신호 파라미터가 None일 때 백테스트 엔진이 실제로 쓰는 값.

SOT는 engine/signals.py(+engine/indicator_columns.py)의 `p.get(..., 기본값)` 체인이다.
Registry 표준값(indicator_registry ParamSpec.default)과 **다른 값이 여럿 있다**
(ma_crossover 5/20 vs 20/60, breakout 20 vs 60, stochastic 9 vs 20 등).

수정 이관 라운드트립(decompile→compile)은 Registry 표준값을 채우므로, 파라미터 None
신호를 가진 전략은 '원본 ≠ 복원본'이 되어 LLM 레인 진입이 막혔다 — 2026-07-26
"제주반도체 종목도 추가해줘"가 레거시 레인으로 떨어져 유니버스가 교체된 사고의 직접
원인. 왕복 전에 None을 **엔진이 어차피 쓰는 값**으로 명시 채우면(materialize) 백테스트
의미는 1비트도 변하지 않으면서 라운드트립이 성립하고, 요약 카드에도 실제 적용 기간이
드러난다(칩 "골든크로스 발생 시 매수"가 기간 없이 저장되던 불투명성 해소).

의도적 제외:
- ema — 듀얼 크로스 기간이 None이면 엔진이 가격-EMA(기간 20) 모드로 **동작을 전환**
  하므로(signals.py), 어떤 기간을 채워도 의미가 바뀐다. 라운드트립 차단(되묻기)이 옳다.
- adx의 period는 엔진이 읽지 않지만(고정 'adx' 컬럼) 라운드트립 성립을 위해 엔진과
  무관한 Registry 값 대신 14를 명시한다(결과 불변).
"""

from __future__ import annotations

from typing import Dict

from engine.nl_parser import ParsedStrategy

ENGINE_EFFECTIVE_PARAM_DEFAULTS: Dict[str, Dict[str, float]] = {
    "ma_crossover": {"short_period": 5, "long_period": 20},
    "rsi": {"period": 14},
    "stochastic": {"period": 9},
    "cci": {"period": 14},
    "adx": {"period": 14},
    "williams_r": {"period": 14},
    "mfi": {"period": 14},
    "roc": {"period": 12},
    "bollinger_bands": {"period": 20},
    "volume_spike": {"period": 20},
    "breakout": {"lookback_period": 20},
}


def materialize_engine_defaults(parsed: ParsedStrategy) -> ParsedStrategy:
    """entry/exit 신호의 None 파라미터를 엔진 실효값으로 명시 채운 사본을 반환한다.

    값이 이미 있는 파라미터는 절대 건드리지 않는다. 채울 것이 없으면 원본을 그대로
    반환한다(사본·변형 없음).
    """
    def _fill(signals):
        out, changed = [], False
        for sig in signals:
            defaults = ENGINE_EFFECTIVE_PARAM_DEFAULTS.get(sig.indicator) or {}
            updates = {
                name: value for name, value in defaults.items()
                if hasattr(sig, name) and getattr(sig, name) is None
            }
            if updates:
                sig = sig.model_copy(update=updates)
                changed = True
            out.append(sig)
        return out, changed

    entry, entry_changed = _fill(parsed.entry_signals)
    exits, exit_changed = _fill(parsed.exit_signals)
    if not (entry_changed or exit_changed):
        return parsed
    return parsed.model_copy(update={"entry_signals": entry, "exit_signals": exits})
