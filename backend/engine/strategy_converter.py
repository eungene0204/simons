"""
ParsedStrategy → BacktestRequest 변환기

LLM이 파싱한 ParsedStrategy를 기존 Back테스트 엔진이 이해하는
BacktestRequest 형식으로 변환한다.
"""

from __future__ import annotations

import json
import time
import logging
import re
from pathlib import Path
from typing import List, Optional

from engine.nl_parser import ParsedStrategy, TechnicalSignal

logger = logging.getLogger(__name__)

# ─── 유니버스 심볼 로딩 ───────────────────────────────────────────────────────

_STOCKS_PATH = Path(__file__).parent.parent.parent / "data" / "korea-stocks.json"
_KOSPI200_CACHE_PATH = Path(__file__).parent.parent.parent / "data" / "kospi200-cache.json"
_CACHE_TTL_SECONDS = 7 * 24 * 3600  # 1주일
_NAVER_SYMBOL_RE = re.compile(r"code=([0-9A-Z]{6})(?:&|$)")
# Naver KOSPI200 page may omit recently listed alphanumeric symbols even when they are
# already treated as K200 constituents by downstream market data vendors.
_KOSPI200_SUPPLEMENTAL_SYMBOLS = {"0126Z0"}


def _extract_naver_symbol(href: str) -> Optional[str]:
    """네이버 종목 링크에서 6자리 영숫자 코드를 추출한다."""
    match = _NAVER_SYMBOL_RE.search(href or "")
    return match.group(1) if match else None


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


def _load_kospi200() -> List[str]:
    """KOSPI200 구성종목 반환 (캐시 우선, 만료 시 재조회, 실패 시 KOSPI 전체 fallback)"""
    # 캐시 확인
    if _KOSPI200_CACHE_PATH.exists():
        try:
            cache = json.loads(_KOSPI200_CACHE_PATH.read_text(encoding="utf-8"))
            age = time.time() - cache.get("fetched_at", 0)
            if age < _CACHE_TTL_SECONDS and len(cache.get("symbols", [])) >= 150:
                symbols = _normalize_kospi200_symbols(cache["symbols"])
                logger.info(f"[KOSPI200] 캐시 사용 ({len(symbols)}종목, {age/3600:.1f}h 전)")
                return symbols
        except Exception:
            pass

    # 네이버에서 실시간 조회
    logger.info("[KOSPI200] 네이버 금융에서 구성종목 조회 중...")
    symbols = _fetch_kospi200_from_naver()

    if symbols:
        symbols = _normalize_kospi200_symbols(symbols)
        _KOSPI200_CACHE_PATH.write_text(
            json.dumps({"fetched_at": time.time(), "symbols": symbols}, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info(f"[KOSPI200] {len(symbols)}종목 조회 완료, 캐시 저장")
        return symbols

    # fallback: KOSPI 전체
    logger.warning("[KOSPI200] 조회 실패 — KOSPI 전체로 fallback")
    with open(_STOCKS_PATH, encoding="utf-8") as f:
        all_stocks = json.load(f)
    return [s["symbol"] for s in all_stocks if s.get("market") == "KOSPI"]


def _load_universe(markets: List[str]) -> List[str]:
    """universe 설정에 맞는 종목 코드 목록 반환"""
    symbols: set[str] = set()

    if "KOSPI200" in markets:
        symbols.update(_load_kospi200())

    remaining = [m for m in markets if m != "KOSPI200"]
    if remaining:
        with open(_STOCKS_PATH, encoding="utf-8") as f:
            all_stocks = json.load(f)
        target_markets = set(remaining)
        symbols.update(s["symbol"] for s in all_stocks if s.get("market") in target_markets)

    return sorted(symbols)


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

    elif sig.indicator == "ema":
        if sig.short_period and sig.long_period:
            params["shortPeriod"] = sig.short_period
            params["longPeriod"] = sig.long_period
        else:
            params["period"] = sig.period or 20

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

    elif sig.indicator in ("cci", "adx"):
        if sig.period:
            params["period"] = sig.period
        if sig.operator:
            params["operator"] = sig.operator
        if sig.value is not None:
            params["value"] = sig.value

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

def to_backtest_request(strategy: ParsedStrategy) -> dict:
    """
    ParsedStrategy → BacktestRequest dict 변환.
    반환값은 BacktestRequest(**result) 또는 engine.run_backtest(result)에 바로 사용 가능.
    """

    # 1. 심볼 목록
    symbols = _load_universe(strategy.universe)

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

    # 3. 청산 조건 구성
    exit_conditions = [_tech_signal_to_condition(sig) for sig in strategy.exit_signals]

    # 4. 리스크 관리 설정
    position_size_pct = round(100.0 / strategy.max_positions, 2)

    risk = {
        "position_size_pct": position_size_pct,
        "max_positions": strategy.max_positions,
        "stop_loss_pct": strategy.stop_loss_pct,
        "take_profit_pct": strategy.take_profit_pct,
        "trailing_stop_pct": strategy.trailing_stop_pct,
        "max_mdd_limit_pct": strategy.max_mdd_limit_pct,
        "max_holding_days": strategy.hold_period_days,
        "rebalancing_period": strategy.rebalancing_period,
        "init_cash": strategy.initial_capital,
        "ranking_enabled": True,
        "ranking_weight_value": 0.5,
        "ranking_weight_quality": 0.5,
        "execution_timing": strategy.execution_timing,
        "allocation_type": "equal",
    }

    return {
        "symbols": symbols,
        "entry": {"conditions": entry_conditions},
        "exit": {"conditions": exit_conditions},
        "risk": risk,
        "period": strategy.backtest_period,
        "options": {
            "fee_rate": strategy.fee_rate,
            "slippage_rate": strategy.slippage_rate,
        },
    }
