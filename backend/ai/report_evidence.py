"""전략 검증 전문가 리포트용 결정론 근거(evidence) 계산.

AI 리포트가 '화면의 숫자 반복'을 넘어 '숫자의 의미'를 서술하도록, 엔진이 이미
계산해 내려주는 확장 지표(monthlyReturns/yearlyReturns/maxDrawdownDuration/
expectancy/perAssetStats 등)에서 해석된 fact 문장과 판정 플래그를 만든다.

이 모듈은 순수 함수(dict in / dict out)로 구성해 LLM 없이도 검증 로드맵·개선
우선순위·전략 성향을 결정론적으로 도출한다. LLM은 이 근거 위에서 서술만 한다.
숫자 그 자체보다 '의미'를 담은 문장을 생성하는 것이 목적이다.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


# ── 공통 헬퍼 ────────────────────────────────────────────────────────────────

def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> Optional[int]:
    f = _to_float(value)
    return int(f) if f is not None else None


def _period_years(metrics: Dict[str, Any]) -> Optional[float]:
    """periodStart~periodEnd(YYYY-MM-DD)에서 백테스트 연수를 추정한다."""
    start = str(metrics.get("periodStart") or "")[:10]
    end = str(metrics.get("periodEnd") or "")[:10]
    from datetime import date

    def _parse(s: str) -> Optional[date]:
        try:
            y, m, d = (int(x) for x in s.split("-")[:3])
            return date(y, m, d)
        except (ValueError, TypeError):
            return None

    a, b = _parse(start), _parse(end)
    if a is None or b is None or b <= a:
        return None
    return (b - a).days / 365.25


# ── 수익 집중도 (monthlyReturns / yearlyReturns) ─────────────────────────────

def _return_concentration(returns: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """구간별 수익률 맵에서 집중도 지표를 계산한다.

    - positive_ratio: 플러스 구간 비율
    - top_share: 전체 플러스 수익 합에서 단일 최고 구간이 차지하는 비율(단위 무관)
    """
    values = [v for v in (_to_float(x) for x in (returns or {}).values()) if v is not None]
    if len(values) < 3:
        return {"positive_ratio": None, "top_share": None, "count": len(values)}

    positives = [v for v in values if v > 0]
    positive_ratio = len(positives) / len(values)
    top_share: Optional[float] = None
    total_positive = sum(positives)
    if total_positive > 0:
        top_share = max(positives) / total_positive
    return {"positive_ratio": positive_ratio, "top_share": top_share, "count": len(values)}


def _symbol_concentration(per_asset: Any) -> Optional[float]:
    """수익을 낸 종목들 중 최상위 종목이 차지하는 이익 비율(0~1)."""
    if not isinstance(per_asset, dict) or not per_asset:
        return None
    profits = [
        f for f in (_to_float((stat or {}).get("profit")) for stat in per_asset.values())
        if f is not None and f > 0
    ]
    total = sum(profits)
    if not profits or total <= 0:
        return None
    return max(profits) / total


# ── evidence pack ────────────────────────────────────────────────────────────

def build_evidence_pack(metrics: Dict[str, Any], parsed_strategy: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """해석된 fact 문장 목록 + 하위 로직용 판정 플래그(signals)를 반환한다."""
    metrics = metrics or {}
    facts: List[str] = []
    signals: Dict[str, Any] = {}

    years = _period_years(metrics)
    trades = _to_int(metrics.get("trades"))

    # 1) 수익의 시간 집중도 — 성과가 특정 국면에 쏠렸는지
    monthly = _return_concentration(metrics.get("monthlyReturns"))
    yearly = _return_concentration(metrics.get("yearlyReturns"))
    time_concentrated = False
    if monthly["top_share"] is not None and monthly["count"] >= 6 and monthly["top_share"] >= 0.4:
        time_concentrated = True
        facts.append(
            f"전체 플러스 성과의 약 {round(monthly['top_share'] * 100)}%가 단일 최고 성과 월에 집중되어, "
            "수익이 특정 국면에 쏠린 구조입니다."
        )
    elif yearly["top_share"] is not None and yearly["count"] >= 3 and yearly["top_share"] >= 0.6:
        time_concentrated = True
        facts.append(
            f"전체 플러스 성과의 약 {round(yearly['top_share'] * 100)}%가 특정 한 해에 집중되어, "
            "성과가 특정 연도 시장 환경에 의존했을 가능성이 있습니다."
        )
    if monthly["positive_ratio"] is not None and monthly["count"] >= 6 and monthly["positive_ratio"] < 0.4:
        facts.append(
            f"수익이 발생한 월의 비율이 약 {round(monthly['positive_ratio'] * 100)}%에 그쳐, "
            "소수의 강한 구간이 전체 성과를 견인한 형태입니다."
        )
    signals["time_concentrated"] = time_concentrated

    # 2) 수중(손실 미회복) 지속 — MDD 깊이가 아니라 '얼마나 오래 잠겼나'
    underwater = _to_int(metrics.get("maxDrawdownDuration"))
    signals["underwater_days"] = underwater
    if underwater is not None and underwater >= 120:
        facts.append(
            f"최장 수중(고점 미회복) 기간이 약 {underwater}거래일에 달해, 손실 구간이 길게 이어진 이력이 있습니다. "
            "이는 실제 운용 시 심리적으로 버티기 어려운 구간이 존재했음을 뜻합니다."
        )

    # 3) 승률 vs 기대수익 — 높은 승률이 성과를 보장하지 않음
    win_rate = _to_float(metrics.get("winRate"))
    expectancy = _to_float(metrics.get("expectancy"))
    high_winrate_low_expectancy = (
        win_rate is not None and win_rate >= 55
        and expectancy is not None and expectancy < 0.5
    )
    signals["high_winrate_low_expectancy"] = high_winrate_low_expectancy
    if high_winrate_low_expectancy:
        facts.append(
            "승률은 높은 편이지만 거래당 기대수익이 낮아, 소수의 큰 손실이 다수의 작은 이익을 상쇄할 수 있는 구조입니다."
        )

    # 4) 표본 적정성 — 과최적화·신뢰도 판단의 핵심 근거
    low_sample = trades is not None and trades < 20
    signals["low_sample"] = low_sample
    signals["trade_count"] = trades
    if low_sample:
        facts.append(
            f"총 거래가 {trades}회로 표본이 적어, 성과가 우연의 산물일 가능성을 통계적으로 배제하기 어렵습니다."
        )

    # 5) 회전율 — 성향 및 비용 민감도
    trades_per_year = (trades / years) if (trades is not None and years and years > 0) else None
    avg_holding = _to_float(metrics.get("avgHoldingDays"))
    high_turnover = (trades_per_year is not None and trades_per_year >= 120) or (
        avg_holding is not None and 0 < avg_holding < 5
    )
    low_turnover = (trades_per_year is not None and trades_per_year <= 6) or (
        avg_holding is not None and avg_holding > 60
    )
    signals["high_turnover"] = bool(high_turnover)
    signals["low_turnover"] = bool(low_turnover)
    if high_turnover:
        facts.append(
            "거래 빈도가 높아 실제 운용 시 거래 비용·슬리피지의 영향이 커질 수 있는 고회전 구조입니다."
        )
    elif low_turnover:
        facts.append(
            "거래 빈도가 낮은 저회전 구조로, 개별 거래의 결과가 전체 성과에 크게 작용합니다."
        )

    # 6) 종목 집중 — 결과가 소수 종목에 좌우됐는지
    symbol_top_share = _symbol_concentration(metrics.get("perAssetStats"))
    symbol_concentrated = symbol_top_share is not None and symbol_top_share >= 0.5
    signals["symbol_concentrated"] = symbol_concentrated
    if symbol_concentrated:
        facts.append(
            f"수익의 약 {round(symbol_top_share * 100)}%가 단일 종목에서 발생해, 결과가 특정 종목 성과에 크게 의존했습니다."
        )

    # 7) 검증 기간 — 로드맵 판단 근거
    short_period = years is not None and years < 3
    signals["short_period"] = short_period
    signals["years"] = years
    if short_period and years is not None:
        facts.append(
            f"검증 기간이 약 {years:.1f}년으로 짧아, 상승·하락·횡보 등 다양한 시장 국면을 충분히 포함하지 못했을 수 있습니다."
        )

    # 8) 유니버스/종목 수 — 시장·다양성 확대 검증 판단 근거
    signals.update(_universe_signals(parsed_strategy))

    if not facts:
        facts.append("추가로 해석할 만한 구조적 특이점은 발견되지 않았습니다.")

    return {"facts": facts, "signals": signals}


def _universe_signals(parsed_strategy: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """parsed_strategy에서 단일 시장/소수 종목 여부를 best-effort로 판정한다."""
    out: Dict[str, Any] = {"single_market": False, "few_symbols": False}
    if not isinstance(parsed_strategy, dict):
        return out

    market = parsed_strategy.get("market") or parsed_strategy.get("universe")
    if isinstance(market, str) and market.upper() in {"KOSPI", "KOSDAQ", "KOSPI200"}:
        out["single_market"] = True

    targets = parsed_strategy.get("target_symbols") or parsed_strategy.get("symbols")
    if isinstance(targets, (list, tuple)) and 0 < len(targets) <= 3:
        out["few_symbols"] = True

    max_positions = _to_float(parsed_strategy.get("max_positions"))
    if max_positions is not None and max_positions < 5:
        out["few_symbols"] = True
    return out


# ── 전략 성향 분류 ───────────────────────────────────────────────────────────

_TREND_INDICATORS = {"ma_crossover", "ema", "macd", "adx", "breakout", "dmi"}
_MEANREV_INDICATORS = {"rsi", "bollinger_band", "stochastic", "cci", "williams_r"}
_MOMENTUM_INDICATORS = {"roc", "momentum", "trading_value"}


def classify_strategy_profile(parsed_strategy: Optional[Dict[str, Any]], metrics: Dict[str, Any]) -> List[str]:
    """복합 성향 태그를 결정론적으로 도출한다(하나로 단정하지 않음)."""
    metrics = metrics or {}
    tags: List[str] = []

    indicators: set[str] = set()
    if isinstance(parsed_strategy, dict):
        try:
            from advisor.similarity import extract_structural_features
            indicators = set(extract_structural_features(parsed_strategy).indicators)
        except Exception:
            indicators = set()

    # 신호 계열
    if indicators & _TREND_INDICATORS:
        tags.append("추세추종형")
    if indicators & _MEANREV_INDICATORS:
        tags.append("평균회귀형")
    rebalancing = str((parsed_strategy or {}).get("rebalancing_period") or "")
    if (indicators & _MOMENTUM_INDICATORS) or (rebalancing and rebalancing != "none"):
        tags.append("모멘텀형")

    # 회전율 — evidence signals와 동일 기준
    ev = build_evidence_pack(metrics, parsed_strategy)["signals"]
    if ev.get("high_turnover"):
        tags.append("고회전")
    elif ev.get("low_turnover"):
        tags.append("저회전")

    # 변동성
    vol = _to_float(metrics.get("volatility"))
    if vol is not None:
        if vol >= 25:
            tags.append("고변동성")
        elif vol > 0 and vol < 12:
            tags.append("저변동성")

    # 리스크 태세
    if isinstance(parsed_strategy, dict):
        try:
            from advisor.corpus_insights import _has_stop, _has_take_profit, _is_diversified
            if _has_stop(parsed_strategy) or _has_take_profit(parsed_strategy):
                tags.append("리스크관리 적용")
            else:
                tags.append("공격형(손절·익절 미설정)")
            tags.append("분산형" if _is_diversified(parsed_strategy) else "집중형")
        except Exception:
            pass

    # 중복 제거(순서 보존)
    seen: set[str] = set()
    return [t for t in tags if not (t in seen or seen.add(t))]


# ── 검증 로드맵 (결정론 규칙) ────────────────────────────────────────────────

def build_validation_roadmap(
    metrics: Dict[str, Any],
    evidence: Dict[str, Any],
    advisor: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """현재 결과 근거로 어떤 추가 검증이 왜 우선인지 규칙 기반으로 도출한다.

    각 항목: {title, reason, priority}. priority가 낮을수록 시급.
    투자·전략 추천이 아니라 '검증 행위'만 제시한다.
    """
    signals = (evidence or {}).get("signals", {})
    items: List[Dict[str, Any]] = []

    if signals.get("low_sample"):
        items.append({
            "title": "몬테카를로 시뮬레이션",
            "reason": "거래 표본이 적어 성과가 우연일 가능성이 있으므로, 거래 순서를 재표본해 결과 분포와 안정성을 먼저 확인해야 합니다.",
            "priority": 1,
        })
    if signals.get("time_concentrated"):
        items.append({
            "title": "워크포워드 검증",
            "reason": "성과가 특정 기간에 집중되어 있어, 구간을 나눠 시점별로 재학습·재검증했을 때도 견고한지 확인해야 합니다.",
            "priority": 1,
        })
    if signals.get("short_period"):
        items.append({
            "title": "장기간 백테스트",
            "reason": "검증 기간이 짧아 다양한 시장 국면을 포함하지 못했으므로, 기간을 늘려 국면 전반에서의 거동을 확인해야 합니다.",
            "priority": 2,
        })
    if signals.get("single_market"):
        items.append({
            "title": "다른 시장(KOSPI/KOSDAQ) 검증",
            "reason": "단일 시장에서만 검증되어, 다른 시장에서도 동일한 특성이 재현되는지 교차 확인이 필요합니다.",
            "priority": 3,
        })
    if signals.get("few_symbols") or signals.get("symbol_concentrated"):
        items.append({
            "title": "종목 수 확대 검증",
            "reason": "결과가 소수 종목에 좌우되어, 대상 종목을 넓혀도 성과 특성이 유지되는지 확인해야 합니다.",
            "priority": 3,
        })

    # 파라미터가 존재하면 민감도 분석은 항상 후보(중복 시 생략).
    # advisor.suggested_experiments 는 특정 파라미터 값('손절 8~10%' 등)을 담을 수 있어
    # 로드맵(검증 유형)에는 병합하지 않는다 — 규제상 구체적 DSL 값 제안 회피.
    has_params = _strategy_has_parameters(advisor)
    if has_params and not any(i["title"] == "파라미터 민감도 분석" for i in items):
        items.append({
            "title": "파라미터 민감도 분석",
            "reason": "특정 파라미터 값에 성과가 얼마나 의존하는지 확인해, 값을 조금 바꿔도 결과가 유지되는 견고한 전략인지 점검해야 합니다.",
            "priority": 2,
        })

    if not items:
        items.append({
            "title": "파라미터 민감도 분석",
            "reason": "뚜렷한 취약점은 발견되지 않았으나, 파라미터 의존도를 점검하면 결과의 견고성을 한층 확실히 확인할 수 있습니다.",
            "priority": 2,
        })

    items.sort(key=lambda i: i["priority"])
    return items[:5]


def _strategy_has_parameters(advisor: Optional[Dict[str, Any]]) -> bool:
    # advisor 진단이 있으면 대체로 파라미터화된 전략 — 민감도 분석 후보로 둔다.
    return advisor is not None


# ── 개선 우선순위 (점수 인지형·검증 중심·전략 수준) ──────────────────────────

def build_improvement_priorities(
    score: Optional[int],
    advisor: Optional[Dict[str, Any]],
    evidence: Dict[str, Any],
) -> List[str]:
    """전략 점수·근거에 따라 다음 단계를 제시한다.

    핵심 원칙(규제·스펙): 구체적 DSL 수정(손절/익절 값, 지표 추가/삭제, 파라미터
    변경, 신규 매수/매도 조건)은 절대 제시하지 않는다. 점수가 높으면 추가 검증을,
    낮거나 구조적 문제가 명확하면 전략 수준의 방향성을 권한다.
    """
    signals = (evidence or {}).get("signals", {})
    s = score if score is not None else 50
    items: List[str] = []

    if s >= 70:
        # 신뢰도가 충분 — 수정보다 검증을 우선
        items.append("현재 성과를 확정하기 전에 워크포워드·몬테카를로 등 추가 검증으로 견고성을 먼저 확인하십시오.")
        items.append("파라미터 민감도를 점검해 특정 값에 성과가 과도하게 의존하지 않는지 확인하십시오.")
        if signals.get("time_concentrated"):
            items.append("성과가 특정 기간에 집중되어 있으므로, 구간을 나눠 시점별 견고성을 검증하십시오.")
        if signals.get("single_market") or signals.get("symbol_concentrated"):
            items.append("동일한 특성이 다른 시장·더 넓은 종목군에서도 재현되는지 교차 검증하십시오.")
    elif s <= 45:
        # 구조적 문제가 명확 — 검증 반복보다 전략 수준 재검토
        items.append("전략 구조가 복잡하다면 단순화를 고려한 뒤 다시 검토하는 것이 효율적입니다.")
        items.append("현재 전략 아이디어 자체가 목표에 부합하는지 근본적으로 재검토해 보십시오.")
        if signals.get("time_concentrated") or signals.get("single_market"):
            items.append("특정 시장 환경이나 구간에 지나치게 의존하는 구조인지 확인해 보십시오.")
        items.append("전략을 새로 구성한 뒤 다시 백테스트하는 접근이 더 효율적일 수 있습니다.")
    else:
        # 중간대 — 검증을 우선하되 구조적 주의 한 가지 병기
        items.append("추가 검증(워크포워드·몬테카를로)으로 현재 성과가 특정 조건에 치우쳐 있지 않은지 확인하십시오.")
        items.append("파라미터 민감도를 점검해 결과의 견고성을 확인하십시오.")
        if signals.get("low_sample"):
            items.append("거래 표본이 적으므로 검증 기간·대상을 넓혀 표본을 확보한 뒤 재평가하십시오.")
        else:
            items.append("성과가 특정 시장 환경에 의존하는 구조는 아닌지 점검해 보십시오.")

    # 중복 제거(순서 보존) 후 3~5개
    seen: set[str] = set()
    deduped = [t for t in items if not (t in seen or seen.add(t))]
    return deduped[:5]
