"""
ParsedStrategy → BacktestRequest 변환기

LLM이 파싱한 ParsedStrategy를 기존 Back테스트 엔진이 이해하는
BacktestRequest 형식으로 변환한다.
"""

from __future__ import annotations

import hashlib
import json
import time
import logging
import re
from pathlib import Path
from typing import Any, List, Optional

from engine.nl_parser import ParsedStrategy, TechnicalSignal
from engine.selection_scope import SelectionScope, selection_scope

logger = logging.getLogger(__name__)

# ─── 유니버스 심볼 로딩 ───────────────────────────────────────────────────────

_STOCKS_PATH = Path(__file__).parent.parent.parent / "data" / "korea-stocks.json"
_KOSPI200_CACHE_PATH = Path(__file__).parent.parent.parent / "data" / "kospi200-cache.json"
_KOSDAQ150_CACHE_PATH = Path(__file__).parent.parent.parent / "data" / "kosdaq150-cache.json"
_CACHE_TTL_SECONDS = 7 * 24 * 3600  # 1주일
_NAVER_SYMBOL_RE = re.compile(r"code=([0-9A-Z]{6})(?:&|$)")
# Naver KOSPI200 page may omit recently listed alphanumeric symbols even when they are
# already treated as K200 constituents by downstream market data vendors.
_KOSPI200_SUPPLEMENTAL_SYMBOLS = {"0126Z0"}


def _extract_naver_symbol(href: str) -> Optional[str]:
    """네이버 종목 링크에서 6자리 영숫자 코드를 추출한다."""
    match = _NAVER_SYMBOL_RE.search(href or "")
    return match.group(1) if match else None


def _unique_sorted(symbols: List[str]) -> List[str]:
    return sorted({symbol for symbol in symbols if symbol})


def _normalize_kospi200_symbols(symbols: List[str]) -> List[str]:
    """스크래핑 결과에 누락되기 쉬운 보정 종목을 포함해 정렬 반환한다."""
    normalized = {symbol for symbol in symbols if symbol}
    normalized.update(_KOSPI200_SUPPLEMENTAL_SYMBOLS)
    return sorted(normalized)


def _fetch_kospi200_from_naver() -> Optional[List[str]]:
    """네이버 금융에서 KOSPI200 구성종목 200개 조회"""
    try:
        import requests
        from bs4 import BeautifulSoup

        codes: set[str] = set()
        for page in range(1, 22):
            url = "https://finance.naver.com/sise/entryJongmok.nhn"
            params = {"code": "KPI200", "page": str(page)}
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://finance.naver.com",
            }
            r = requests.get(url, params=params, headers=headers, timeout=10)
            r.encoding = "euc-kr"
            soup = BeautifulSoup(r.text, "html.parser")
            links = soup.find_all("a", href=True)
            page_codes = [
                code for a in links
                if "code=" in a.get("href", "") and "main.naver" in a["href"]
                for code in [_extract_naver_symbol(a["href"])]
                if code is not None
            ]
            if not page_codes:
                break
            codes.update(page_codes)

        return _normalize_kospi200_symbols(list(codes)) if len(codes) >= 150 else None
    except Exception as e:
        logger.warning(f"[KOSPI200] 네이버 조회 실패: {e}")
        return None


def _fetch_index_from_kis(index_id: str) -> Optional[List[str]]:
    """KIS 종목마스터에서 지수 구성종목 조회. 검증 실패·네트워크 실패 시 None."""
    try:
        from engine.kis_master import fetch_index_members

        return sorted(symbol for symbol, _ in fetch_index_members(index_id))
    except Exception as e:
        logger.warning(f"[{index_id}] KIS 마스터 조회 실패: {e}")
        return None


def _load_index_roster(index_id: str, cache_path: Path, min_size: int) -> Optional[List[str]]:
    """지수 명부 반환 (캐시 우선, 만료 시 KIS 마스터 재조회). 실패 시 None."""
    if cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            age = time.time() - cache.get("fetched_at", 0)
            if age < _CACHE_TTL_SECONDS and len(cache.get("symbols", [])) >= min_size:
                symbols = _unique_sorted(cache["symbols"])
                logger.info(f"[{index_id}] 캐시 사용 ({len(symbols)}종목, {age/3600:.1f}h 전)")
                return symbols
        except Exception:
            pass

    logger.info(f"[{index_id}] KIS 종목마스터에서 구성종목 조회 중...")
    symbols = _fetch_index_from_kis(index_id)
    if not symbols:
        return None

    cache_path.write_text(
        json.dumps({"fetched_at": time.time(), "symbols": symbols}, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(f"[{index_id}] {len(symbols)}종목 조회 완료, 캐시 저장")
    return symbols


def _load_kospi200() -> List[str]:
    """KOSPI200 구성종목 반환 (KIS 마스터 → 네이버 → KOSPI 전체 순 폴백)"""
    symbols = _load_index_roster("kospi200", _KOSPI200_CACHE_PATH, 150)
    if symbols:
        return _normalize_kospi200_symbols(symbols)

    # KIS 마스터가 막히면 기존 네이버 경로로 폴백한다(영숫자 코드 누락분은 보정 목록이 메운다).
    logger.info("[KOSPI200] 네이버 금융에서 구성종목 조회 중...")
    naver_symbols = _fetch_kospi200_from_naver()
    if naver_symbols:
        naver_symbols = _normalize_kospi200_symbols(naver_symbols)
        _KOSPI200_CACHE_PATH.write_text(
            json.dumps({"fetched_at": time.time(), "symbols": naver_symbols}, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info(f"[KOSPI200] {len(naver_symbols)}종목 조회 완료, 캐시 저장")
        return naver_symbols

    # fallback: KOSPI 전체
    logger.warning("[KOSPI200] 조회 실패 — KOSPI 전체로 fallback")
    with open(_STOCKS_PATH, encoding="utf-8") as f:
        all_stocks = json.load(f)
    return [
        s["symbol"] for s in all_stocks
        if s.get("market") == "KOSPI" and "스팩" not in (s.get("name") or "")
    ]


def _load_kosdaq150() -> List[str]:
    """KOSDAQ150 구성종목 반환. 명부를 못 얻으면 빈 목록.

    KOSPI200 과 달리 "KOSDAQ 전체"로 폴백하지 않는다 — 150종목 지수를 1,700종목
    시장으로 넓히는 것은 조용한 유니버스 확대이고, 그게 FR-VM-073 이 막는 사고다.
    """
    symbols = _load_index_roster("kosdaq150", _KOSDAQ150_CACHE_PATH, 100)
    if not symbols:
        logger.warning("[KOSDAQ150] 명부를 얻지 못했다 — 빈 유니버스를 반환한다")
    return symbols or []


def _load_universe(markets: List[str]) -> List[str]:
    """universe 설정에 맞는 종목 코드 목록 반환"""
    symbols: set[str] = set()

    # ETF 유니버스는 주식 시장과 혼합하지 않는다 — ETF 마스터만 조회한다.
    if "ETF" in markets:
        from engine.universe_pit import _load_etf_master
        return sorted(e["symbol"] for e in _load_etf_master() if e.get("hasOhlcv"))

    if "KOSPI200" in markets:
        symbols.update(_load_kospi200())
    if "KOSDAQ150" in markets:
        symbols.update(_load_kosdaq150())

    remaining = [m for m in markets if m not in ("KOSPI200", "KOSDAQ150")]
    if remaining:
        with open(_STOCKS_PATH, encoding="utf-8") as f:
            all_stocks = json.load(f)
        target_markets = set(remaining)
        symbols.update(
            s["symbol"] for s in all_stocks
            if s.get("market") in target_markets and "스팩" not in (s.get("name") or "")
        )

    return sorted(symbols)


# ─── Canonical Strategy DSL / Strategy ID ────────────────────────────────────

def _drop_none(value: Any) -> Any:
    """Recursively remove null fields from canonical payloads."""
    if isinstance(value, list):
        return [_drop_none(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _drop_none(item)
            for key, item in value.items()
            if item is not None
        }
    return value


def _canonical_sort_key(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _canonicalize_technical_signal(sig: TechnicalSignal) -> dict:
    return _drop_none({
        "indicator": sig.indicator,
        "signal_type": sig.signal_type,
        "short_period": sig.short_period,
        "long_period": sig.long_period,
        "period": sig.period,
        "operator": sig.operator,
        "value": sig.value,
        "mode": sig.mode,
        "lookback_period": sig.lookback_period,
        "threshold": sig.threshold,
    })


def to_canonical_strategy_dsl(strategy: ParsedStrategy) -> dict:
    """
    Build a content-addressed strategy payload.

    The original prompt text is excluded so semantically identical strategies
    hash to the same strategy_id.
    """
    canonical = _drop_none({
        "universe": sorted(strategy.universe),
        # 지정 종목(단일 종목 백테스트) — 빈 배열이면 None→_drop_none 제거로 기존
        # 유니버스 전략의 해시가 변하지 않는다. 종목이 다르면 다른 전략(다른 해시)이다.
        "target_symbols": sorted(strategy.target_symbols) if strategy.target_symbols else None,
        # None이면 _drop_none이 제거하므로 섹터 없는 기존 전략의 해시는 변하지 않는다.
        # 단일 섹터는 정규형이 str이라 기존 해시와 동일하고, 복수(list)만 정렬해
        # 순서 무관 동일 해시를 보장한다(FR-STR-066 ⑦).
        "sector": sorted(strategy.sector) if isinstance(strategy.sector, list) else strategy.sector,
        # ETF 테마 필터 — None이면 _drop_none이 제거하므로 기존 전략 해시는 변하지 않는다.
        "etf_theme": strategy.etf_theme,
        # 신규 상장 유니버스(FR-STR-073). None이면 _drop_none이 제거 → 기존 해시 불변.
        "listing_from": strategy.listing_from,
        "listing_to": strategy.listing_to,
        "fundamental_filters": sorted(
            [
                {
                    "metric": item.metric,
                    "operator": item.operator,
                    "value": item.value,
                }
                for item in strategy.fundamental_filters
            ],
            key=_canonical_sort_key,
        ),
        "entry_signals": sorted(
            [_canonicalize_technical_signal(sig) for sig in strategy.entry_signals],
            key=_canonical_sort_key,
        ),
        "exit_signals": sorted(
            [_canonicalize_technical_signal(sig) for sig in strategy.exit_signals],
            key=_canonical_sort_key,
        ),
        "entry_filters": sorted(
            [_canonicalize_technical_signal(sig) for sig in strategy.entry_filters],
            key=_canonical_sort_key,
        ),
        # 신호가 2개 이상일 때만 결합 방식이 실행 결과를 바꾸므로, 그 경우에만 해시에
        # 반영한다 — 신호 0~1개인 기존 전략의 strategy_id를 불필요하게 바꾸지 않는다.
        "entry_logic": strategy.entry_logic if len(strategy.entry_signals) > 1 else None,
        "ranking_metric": strategy.ranking_metric,
        "ranking_lookback_days": strategy.ranking_lookback_days,
        # None이면 _drop_none이 제거 → 방향 미지정 기존 전략의 해시 불변.
        "ranking_direction": strategy.ranking_direction,
        # 분위 그룹·비율 선정(FR-BT-060) — None이면 _drop_none이 제거 → 기존 해시 불변.
        "ranking_quantile_groups": strategy.ranking_quantile_groups,
        "ranking_group_cap": strategy.ranking_group_cap,
        # 복합 순위 합산(FR-BT-063) 구성 지표 — 순서가 곧 의미는 아니지만(동일 가중 평균)
        # 해시는 표기에 민감하므로 지표명으로 정렬해 같은 구성이 같은 strategy_id를 갖게 한다.
        # None이면 _drop_none이 제거 → 단일 랭킹 기존 전략의 해시 불변.
        "ranking_components": (
            sorted(
                [c.model_dump() for c in strategy.ranking_components],
                key=lambda c: (c["metric"], c["direction"], c.get("lookback_days") or 0),
            )
            if strategy.ranking_components else None
        ),
        "max_positions_pct": strategy.max_positions_pct,
        "max_positions": strategy.max_positions,
        "hold_period_days": strategy.hold_period_days,
        "rebalancing_period": strategy.rebalancing_period,
        "stop_loss_pct": strategy.stop_loss_pct,
        "take_profit_pct": strategy.take_profit_pct,
        "trailing_stop_pct": strategy.trailing_stop_pct,
        "max_mdd_limit_pct": strategy.max_mdd_limit_pct,
        "backtest_period": strategy.backtest_period,
        "backtest_start_date": strategy.backtest_start_date,
        "backtest_end_date": strategy.backtest_end_date,
        "initial_capital": strategy.initial_capital,
        "execution_timing": strategy.execution_timing,
        "fee_rate": strategy.fee_rate,
        "slippage_rate": strategy.slippage_rate,
    })
    return canonical


def canonical_strategy_json(strategy: ParsedStrategy) -> str:
    return json.dumps(
        to_canonical_strategy_dsl(strategy),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def compute_strategy_id(strategy: ParsedStrategy) -> str:
    canonical_json = canonical_strategy_json(strategy)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def _percent_to_rate(value: float | None) -> float | None:
    if value is None:
        return None
    return float(value) / 100.0


# ─── 기술 신호 → Condition dict 변환 ─────────────────────────────────────────

def _tech_signal_to_condition(sig: TechnicalSignal) -> dict:
    """TechnicalSignal → SignalEngine이 이해하는 Condition dict"""
    params: dict = {"signalType": sig.signal_type}

    if sig.indicator == "ma_crossover":
        params["shortMA"] = sig.short_period or 5
        params["longMA"] = sig.long_period or 20

    elif sig.indicator == "rsi":
        params["period"] = sig.period or 14
        params["operator"] = sig.operator or ("<" if sig.signal_type == "buy" else ">")
        params["value"] = sig.value if sig.value is not None else (30 if sig.signal_type == "buy" else 70)
        if sig.mode:  # rebound=임계선 재돌파(crossover). 없으면 단순 임계값 비교(기존 동작).
            params["mode"] = sig.mode

    elif sig.indicator == "ema":
        if sig.short_period and sig.long_period:
            params["shortPeriod"] = sig.short_period
            params["longPeriod"] = sig.long_period
        else:
            params["period"] = sig.period or 20
        if sig.mode:  # 'above'/'below'=추세 필터(지속 상태). 없으면 크로스오버(기존).
            params["mode"] = sig.mode

    elif sig.indicator == "macd":
        params["mode"] = sig.mode or "crossover"

    elif sig.indicator == "bollinger_bands":
        pass  # signalType 만으로 충분

    elif sig.indicator == "breakout":
        params["lookbackPeriod"] = sig.lookback_period or 20

    elif sig.indicator == "volume_spike":
        params["period"] = sig.period or 20

    elif sig.indicator == "stochastic":
        params["mode"] = sig.mode or "crossover"
        if sig.operator:
            params["operator"] = sig.operator
        if sig.value is not None:
            params["value"] = sig.value

    elif sig.indicator in ("cci", "adx", "williams_r", "mfi", "roc", "volatility"):
        if sig.period:
            params["period"] = sig.period
        if sig.operator:
            params["operator"] = sig.operator
        if sig.value is not None:
            params["value"] = sig.value

    elif sig.indicator == "trading_value":
        params["value"] = sig.value if sig.value is not None else 100  # 억 단위 거래대금 하한
        params["operator"] = sig.operator or ">="

    elif sig.indicator in ("ai_model", "ai_drop_model"):
        params["threshold"] = sig.threshold if sig.threshold is not None else 70
        if sig.indicator == "ai_drop_model":
            params["targetType"] = "down"

    return {
        "type": "indicator",
        "id": sig.indicator,
        "params": params,
        "weight": 1.0,
    }


# ─── 변환 함수 ────────────────────────────────────────────────────────────────

def _estimate_universe_symbol_count(markets: List[str]) -> Optional[int]:
    """Return cheap counts when available without resolving full symbol lists."""
    if markets == ["KOSPI200"] or set(markets) == {"KOSPI200"}:
        return 200
    return None


def to_backtest_request(strategy: ParsedStrategy, resolve_symbols: bool = True) -> dict:
    """
    ParsedStrategy → BacktestRequest dict 변환.
    반환값은 BacktestRequest(**result) 또는 engine.run_backtest(result)에 바로 사용 가능.

    resolve_symbols=False is the lightweight parse-mode path. It avoids full
    universe IO and symbol payload serialization until the backtest actually runs.
    """

    strategy_id = compute_strategy_id(strategy)
    canonical_strategy_dsl = to_canonical_strategy_dsl(strategy)

    # 1. 심볼 목록 — 지정 종목(단일 종목 백테스트)이면 유니버스를 해석하지 않고 그 종목만
    # 쓴다. universe_id=None이라 엔진의 PIT 재해석(생존편향 보정)도 목록을 건드리지 않는다.
    target_symbols = list(strategy.target_symbols or [])
    if target_symbols:
        symbols = target_symbols
    else:
        symbols = _load_universe(strategy.universe) if resolve_symbols else []

    # 2. 진입 조건 구성
    entry_conditions = []

    # 재무 필터 → type="filter" 조건
    for f in strategy.fundamental_filters:
        entry_conditions.append({
            "type": "filter",
            "id": f.metric,
            "params": {"operator": f.operator, "value": f.value},
            "weight": 1.0,
        })

    # 기술적 진입 신호 → type="indicator" 조건
    for sig in strategy.entry_signals:
        entry_conditions.append(_tech_signal_to_condition(sig))

    # 진입 게이트 필터(추세·RSI 결합·거래대금) → type="filter"로 진입 신호와 AND 결합.
    for sig in strategy.entry_filters:
        cond = _tech_signal_to_condition(sig)
        cond["type"] = "filter"
        entry_conditions.append(cond)

    # 3. 청산 조건 구성
    exit_conditions = [_tech_signal_to_condition(sig) for sig in strategy.exit_signals]

    # 4. 리스크 관리 설정
    position_size_pct = round(100.0 / strategy.max_positions, 2)

    # 리밸런싱 주기가 있으면 회전은 엔진의 달력 기준 리밸런싱이 구동한다(reconstitution).
    # 이때 max_holding_days(보유기간 만료)는 중복 회전을 막기 위해 끈다. SL/TP/트레일링은 그대로.
    max_holding_days = strategy.hold_period_days
    if strategy.rebalancing_period and strategy.rebalancing_period != "none":
        max_holding_days = None

    # 지정 종목 모드: 종목 선정(횡단면 랭킹)이 없고, 자금은 지정 종목 수만큼 균등 배분한다
    # (단일 종목이면 100%). max_positions 기본값(10)을 그대로 두면 1종목에 10%만 투자된다.
    #
    # **후보군 모드는 여기서 갈린다**(설계 스펙 § 6 selection_scope): 테마 조회가 채운
    # 종목에 사용자가 선정 기준(랭킹)을 얹었으면 그 목록은 지정이 아니라 고를 대상이다.
    # 구분하지 않으면 사용자가 말한 랭킹과 보유 수가 **동시에 조용히 사라진다** —
    # 실측: "이차전지 관련주 중 최근 60일 수익률 상위 10종목"이 랭킹 없이 36종목
    # 전부 매수로 나갔다(ranking_enabled=False, max_positions=36).
    scope = selection_scope(strategy)
    explicit_symbols = scope is SelectionScope.EXPLICIT
    if explicit_symbols:
        position_size_pct = round(100.0 / len(target_symbols), 2)

    risk = {
        "position_size_pct": position_size_pct,
        "max_positions": len(target_symbols) if explicit_symbols else strategy.max_positions,
        "stop_loss_pct": strategy.stop_loss_pct,
        "take_profit_pct": strategy.take_profit_pct,
        "trailing_stop_pct": strategy.trailing_stop_pct,
        "max_mdd_limit_pct": strategy.max_mdd_limit_pct,
        "max_holding_days": max_holding_days,
        "rebalancing_period": strategy.rebalancing_period,
        "init_cash": strategy.initial_capital,
        "ranking_enabled": not explicit_symbols,
        "ranking_weight_value": 0.5,
        "ranking_weight_quality": 0.5,
        "ranking_metric": strategy.ranking_metric,
        # lookback은 가격 산출 랭킹('return'·'volatility') 전용 — 재무 팩터 랭킹은 연간 결산값 순위라 기간이 없다.
        "ranking_lookback_days": strategy.ranking_lookback_days or (60 if strategy.ranking_metric in ("return", "volatility") else None),
        "ranking_direction": strategy.ranking_direction,
        # 분위 그룹 비교·비율 선정(FR-BT-060) — 엔진이 그룹 반복 실행/동적 종목 수로 처리.
        "ranking_quantile_groups": strategy.ranking_quantile_groups,
        "ranking_group_cap": strategy.ranking_group_cap,
        # 복합 순위 합산(FR-BT-063) — 엔진이 구성 지표별 백분위 순위를 동일 가중 평균한다.
        "ranking_components": (
            [c.model_dump() for c in strategy.ranking_components]
            if strategy.ranking_components else None
        ),
        "max_positions_pct": strategy.max_positions_pct,
        "execution_timing": strategy.execution_timing,
        "allocation_type": "equal",
    }

    # universe 리스트 → universe_id 문자열 변환
    # ["KOSDAQ"] → "kosdaq", ["KOSPI", "KOSDAQ"] → "kospi_kosdaq", ["KOSPI200"] → "kospi200"
    universe_id = "_".join(m.lower() for m in sorted(strategy.universe)) if strategy.universe else "kospi200"

    # 지정 종목 표시용 이름 해석(코드→등록명). 표시 메타데이터일 뿐 엔진은 symbols만 쓴다.
    target_stocks = None
    if target_symbols:
        from stock_analysis.symbol_resolver import resolve_by_symbol

        target_stocks = []
        for code in target_symbols:
            ref = resolve_by_symbol(code)
            target_stocks.append({"symbol": code, "name": ref.name if ref else code})

    return {
        "strategy_id": strategy_id,
        "canonical_strategy_dsl": canonical_strategy_dsl,
        "symbols": symbols,
        "symbol_count": len(symbols) if (resolve_symbols or target_symbols) else _estimate_universe_symbol_count(strategy.universe),
        "symbols_resolved": bool(resolve_symbols or target_symbols),
        # 지정 종목 모드에서는 유니버스/섹터/ETF 테마가 적용되지 않는다 — universe_id=None이면
        # 엔진이 심볼 목록을 그대로 쓴다(PIT 재해석·섹터 필터 미적용).
        "universe_id": None if target_symbols else universe_id,
        "backtest_mode": "single_asset" if target_symbols else "universe",
        "target_stocks": target_stocks,
        # 섹터 제한 — 엔진이 PIT 유니버스 해석 후 심볼을 이 섹터로 필터링한다.
        "sector": None if target_symbols else strategy.sector,
        # ETF 테마/상품명 필터 — universe_id="etf"일 때 엔진이 이름 키워드로 좁힌다.
        "etf_theme": None if target_symbols else strategy.etf_theme,
        # 신규 상장 제한 — 엔진이 상장일이 이 구간에 속하는 종목만 남긴다.
        # 지정 종목 모드는 사용자가 종목을 직접 고른 것이므로 적용하지 않는다.
        "listing_from": None if target_symbols else strategy.listing_from,
        "listing_to": None if target_symbols else strategy.listing_to,
        # logic 미지정 시 엔진(SignalEngine.generate_signals)의 기본값은 OR이라
        # entry_signals가 2개 이상이면 명시하지 않으면 "동시에"가 조용히 "또는"으로
        # 실행된다(실측 2026-08-03) — 항상 명시한다.
        "entry": {"conditions": entry_conditions, "logic": strategy.entry_logic},
        "exit": {"conditions": exit_conditions},
        "risk": risk,
        "period": strategy.backtest_period,
        # 명시적 연도 범위가 있으면 엔진이 상대 기간 대신 이 창으로 백테스트한다.
        **({"startDate": strategy.backtest_start_date} if strategy.backtest_start_date else {}),
        **({"endDate": strategy.backtest_end_date} if strategy.backtest_end_date else {}),
        "options": {
            "fee_rate": _percent_to_rate(strategy.fee_rate),
            "slippage_rate": _percent_to_rate(strategy.slippage_rate),
        },
    }
