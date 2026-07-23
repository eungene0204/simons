"""단일 종목 연구 프로파일 — StockProfileService (FR-STR-068b).

단일 종목 백테스트에서 종목을 '티커 문자열'로만 다루지 않기 위한 결정론 사전 분석 계층.
종목이 지정되면 그 종목의 실제 데이터(OHLCV·PIT 재무·거래대금)를 읽어 구조화된
StockResearchProfile을 생성·캐시한다. LLM(코치/파서)은 이 프로파일의 직렬화 결과만 읽고
원시 시계열을 직접 계산하지 않는다.

설계 원칙:
  - 모든 수치는 여기서 결정론적으로 계산한다. 계산 불가 필드는 None(임의 추정 금지).
  - 프로파일은 '설명적 통계 + 신호 발생 빈도'만 담는다 — 수익률 기준 사후 최적
    파라미터(best value)는 계산하지도, 저장하지도 않는다(과최적화 방지).
  - 데이터가 파이프라인에 없는 피처(수급·공매도·실적발표일 등)는 unsupported로
    정직하게 노출한다 — 가짜 값 생성 금지.
  - 재무 지표는 parquet에 이미 PIT-safe(OpenDART available_from, 폴백 결산일+90일)로
    병합돼 있다(fundamental_fetcher.enrich_ohlcv_with_fundamentals) → point_in_time_safe=True.

캐시: data/cache/stock_profiles/{symbol}.json. 무효화 기준은 소스 parquet의
fingerprint(mtime+size)와 PROFILE_VERSION. 섹션(technical/signals/financial)별 fingerprint를
따로 기록해, 향후 소스가 분리되면 바뀐 섹션만 재계산할 수 있다(현재는 단일 parquet라
함께 갱신된다).
"""
from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# 프로파일 계산 로직 버전 — 통계·스키마가 바뀌면 올린다(캐시 전체 무효화).
PROFILE_VERSION = 1

_DATA_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "data")
_OHLCV_DIR = os.path.join(_DATA_ROOT, "ohlcv")
_CACHE_DIR = os.path.join(_DATA_ROOT, "cache", "stock_profiles")

# 신호 통계로 인정할 최소 이력(거래일) — 이보다 짧으면 통계 자체를 신뢰하기 어렵다.
_MIN_HISTORY_ROWS = 60
# 재무 지표를 '사용 가능'으로 분류할 최소 유효 행 수·비율.
_FUND_MIN_ROWS = 250
_FUND_MIN_RATIO = 0.15
# 갭 판정 임계(전일 종가 대비 시가 ±3%).
_GAP_THRESHOLD = 0.03
# 결측 경고 임계(주말 제외 예상 거래일 대비).
_MISSING_WARN_RATIO = 0.10

# 파이프라인에 존재하지 않는 데이터 피처 — 프로파일이 항상 미지원으로 선언한다.
PIPELINE_UNSUPPORTED_FEATURES: frozenset[str] = frozenset({
    "foreign_flow",        # 외국인 순매수
    "institution_flow",    # 기관 순매수
    "short_interest",      # 공매도
    "earnings_events",     # 실적 발표일
    "dividend_events",     # 배당 발표일(발표일 캘린더 — 배당수익률 지표와 별개)
    "news_events",         # 뉴스 이벤트(백테스트 파이프라인 미배선)
    "disclosure_events",   # 공시 이벤트
    "market_index",        # 시장지수 시계열(백테스트 데이터셋에 없음)
    "sector_index",        # 업종지수 시계열
    "intraday",            # 분/틱 데이터
})

# 단일 종목 시계열 신호로 지원하는 재무 지표(파케이 컬럼 → 피처 키).
_FUNDAMENTAL_FEATURE_COLS: tuple[str, ...] = (
    "per", "pbr", "psr", "roe_or_gpa", "debt_ratio", "dividend_yield",
    "operating_margin", "revenue_growth",
)


@dataclass(frozen=True)
class DataCoverage:
    available: bool
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    missing_ratio: Optional[float] = None
    point_in_time_safe: Optional[bool] = None


@dataclass(frozen=True)
class StockResearchProfile:
    profile_version: int
    mode: str                      # "single_stock"
    symbol: str
    name: str
    market: str
    sector: Optional[str]
    generated_at: str              # ISO-8601
    source_updated_at: Dict[str, Optional[str]]
    data_coverage: Dict[str, DataCoverage]
    historical_characteristics: Dict[str, Optional[float]]
    signal_statistics: Dict[str, Optional[float]]
    supported_features: frozenset[str]
    supported_strategy_categories: frozenset[str]
    unsupported_features: frozenset[str]
    data_quality_warnings: tuple[str, ...] = ()
    agent_guidance: tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["supported_features"] = sorted(self.supported_features)
        d["supported_strategy_categories"] = sorted(self.supported_strategy_categories)
        d["unsupported_features"] = sorted(self.unsupported_features)
        d["data_quality_warnings"] = list(self.data_quality_warnings)
        d["agent_guidance"] = list(self.agent_guidance)
        d["data_coverage"] = {k: asdict(v) for k, v in self.data_coverage.items()}
        return d

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "StockResearchProfile":
        return StockResearchProfile(
            profile_version=d["profile_version"],
            mode=d.get("mode", "single_stock"),
            symbol=d["symbol"],
            name=d["name"],
            market=d["market"],
            sector=d.get("sector"),
            generated_at=d["generated_at"],
            source_updated_at=dict(d.get("source_updated_at") or {}),
            data_coverage={
                k: DataCoverage(**v) for k, v in (d.get("data_coverage") or {}).items()
            },
            historical_characteristics=dict(d.get("historical_characteristics") or {}),
            signal_statistics=dict(d.get("signal_statistics") or {}),
            supported_features=frozenset(d.get("supported_features") or ()),
            supported_strategy_categories=frozenset(
                d.get("supported_strategy_categories") or ()
            ),
            unsupported_features=frozenset(d.get("unsupported_features") or ()),
            data_quality_warnings=tuple(d.get("data_quality_warnings") or ()),
            agent_guidance=tuple(d.get("agent_guidance") or ()),
        )


# ─── 파일 캐시 저장소 ─────────────────────────────────────────────────────────────

class StockProfileRepository:
    """프로파일 JSON 파일 캐시. fingerprint(소스 parquet mtime+size)로 무효화한다."""

    def __init__(self, cache_dir: str = _CACHE_DIR):
        self.cache_dir = cache_dir

    def _path(self, symbol: str) -> str:
        return os.path.join(self.cache_dir, f"{symbol}.json")

    def get(self, symbol: str, fingerprints: Dict[str, str]) -> Optional[StockResearchProfile]:
        path = self._path(symbol)
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, ValueError):
            return None
        if payload.get("profile_version") != PROFILE_VERSION:
            return None
        if payload.get("fingerprints") != fingerprints:
            return None
        try:
            return StockResearchProfile.from_dict(payload["profile"])
        except (KeyError, TypeError):
            return None

    def save(self, profile: StockResearchProfile, fingerprints: Dict[str, str]) -> None:
        os.makedirs(self.cache_dir, exist_ok=True)
        payload = {
            "profile_version": PROFILE_VERSION,
            "fingerprints": fingerprints,
            "profile": profile.to_dict(),
        }
        tmp = self._path(profile.symbol) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, self._path(profile.symbol))


# ─── 결정론 통계 계산(순수 함수) ────────────────────────────────────────────────────

def _round(value, digits: int = 4) -> Optional[float]:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(v):
        return None
    return round(v, digits)


def _years(pdf: pd.DataFrame) -> float:
    if len(pdf) < 2:
        return 0.0
    span_days = (pdf.index[-1] - pdf.index[0]).days
    return max(span_days / 365.25, 1e-9)


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    return rsi.fillna(100.0).where(avg_gain.notna(), np.nan)


def _cross_below_count(series: pd.Series, threshold: float) -> int:
    below = series < threshold
    return int((below & ~below.shift(1, fill_value=False)).sum())


def _cross_above_count(series: pd.Series, threshold: float) -> int:
    above = series > threshold
    return int((above & ~above.shift(1, fill_value=False)).sum())


def _upcross_count(fast: pd.Series, slow: pd.Series) -> int:
    above = fast > slow
    valid = fast.notna() & slow.notna()
    return int((above & ~above.shift(1, fill_value=False) & valid & valid.shift(1, fill_value=False)).sum())


def compute_technical_stats(pdf: pd.DataFrame) -> Dict[str, Optional[float]]:
    """가격·변동성·추세·유동성 설명 통계(수익률 기반 최적화 산출물 없음)."""
    out: Dict[str, Optional[float]] = {
        "annualized_volatility": None,
        "up_day_ratio": None,
        "avg_daily_return": None,
        "return_skew": None,
        "return_kurtosis": None,
        "gap_frequency_per_year": None,
        "avg_abs_gap": None,
        "maximum_drawdown": None,
        "average_drawdown": None,
        "median_recovery_days": None,
        "median_daily_turnover_krw": None,
        "trend_up_ratio": None,
        "market_correlation": None,   # 시장지수 시계열이 데이터셋에 없어 계산 불가(None 유지)
        "sector_correlation": None,
    }
    if len(pdf) < _MIN_HISTORY_ROWS or "close" not in pdf.columns:
        return out

    close = pdf["close"].astype(float)
    ret = close.pct_change().dropna()
    if len(ret) < 2:
        return out
    years = _years(pdf)

    out["annualized_volatility"] = _round(ret.std() * np.sqrt(252.0))
    out["up_day_ratio"] = _round((ret > 0).mean())
    out["avg_daily_return"] = _round(ret.mean(), 6)
    out["return_skew"] = _round(ret.skew())
    out["return_kurtosis"] = _round(ret.kurtosis())

    if "open" in pdf.columns:
        gap = (pdf["open"].astype(float) / close.shift(1) - 1.0).dropna()
        gap_events = int((gap.abs() > _GAP_THRESHOLD).sum())
        out["gap_frequency_per_year"] = _round(gap_events / years, 2)
        out["avg_abs_gap"] = _round(gap.abs().mean())

    # 낙폭: 전고점 대비 하락률 시계열에서 MDD·평균 낙폭·회복 기간을 계산한다.
    peak = close.cummax()
    drawdown = close / peak - 1.0
    out["maximum_drawdown"] = _round(drawdown.min())
    out["average_drawdown"] = _round(drawdown[drawdown < 0].mean())

    # 회복 기간: 낙폭 구간(전고점 붕괴~회복)별 길이의 중앙값(거래일). 미회복 마지막 구간 제외.
    in_dd = drawdown < 0
    if in_dd.any():
        group = (in_dd != in_dd.shift(1, fill_value=False)).cumsum()
        lengths = [len(g) for key, g in drawdown.groupby(group) if (g < 0).all() and len(g) > 0]
        closed = lengths[:-1] if in_dd.iloc[-1] and lengths else lengths
        if closed:
            out["median_recovery_days"] = _round(float(np.median(closed)), 1)

    if "volume" in pdf.columns:
        turnover = (close * pdf["volume"].astype(float)).replace(0.0, np.nan).dropna()
        if len(turnover):
            out["median_daily_turnover_krw"] = _round(float(turnover.median()), 0)

    sma20 = close.rolling(20).mean()
    sma60 = close.rolling(60).mean()
    valid = sma60.notna()
    if valid.any():
        out["trend_up_ratio"] = _round((sma20 > sma60)[valid].mean())
    return out


def compute_signal_stats(pdf: pd.DataFrame) -> Dict[str, Optional[float]]:
    """대표 신호의 발생 횟수·연간 빈도(고정 파라미터 격자 — 설명 목적, 최적화 아님).

    격자는 빌더/파서가 실제로 만드는 신호 유형을 덮는다. 여기서 수익률 기준으로 파라미터를
    고르는 계산은 하지 않는다(과최적화 방지 — best_value 없음).
    """
    out: Dict[str, Optional[float]] = {}
    keys = [
        "rsi_below_20", "rsi_below_25", "rsi_below_30",
        "rsi_above_70", "rsi_above_75", "rsi_above_80",
        "golden_cross_5_20", "golden_cross_10_60", "golden_cross_20_120",
        "macd_buy_cross", "bollinger_lower_touch", "bollinger_upper_touch",
        "breakout_20d", "breakout_60d", "breakout_120d",
        "volume_spike_3x", "drop_10pct_from_60d_high", "cci_below_minus_100",
        "stochastic_buy_cross",
    ]
    for k in keys:
        out[f"{k}_count"] = None
        out[f"{k}_per_year"] = None
    if len(pdf) < _MIN_HISTORY_ROWS or "close" not in pdf.columns:
        return out

    close = pdf["close"].astype(float)
    years = _years(pdf)

    def put(key: str, count: int) -> None:
        out[f"{key}_count"] = int(count)
        out[f"{key}_per_year"] = _round(count / years, 2)

    rsi = _rsi(close, 14)
    for thr in (20, 25, 30):
        put(f"rsi_below_{thr}", _cross_below_count(rsi, float(thr)))
    for thr in (70, 75, 80):
        put(f"rsi_above_{thr}", _cross_above_count(rsi, float(thr)))

    for short, long_ in ((5, 20), (10, 60), (20, 120)):
        put(
            f"golden_cross_{short}_{long_}",
            _upcross_count(close.rolling(short).mean(), close.rolling(long_).mean()),
        )

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    put("macd_buy_cross", _upcross_count(macd, signal))

    mid = close.rolling(20).mean()
    std = close.rolling(20).std()
    lower, upper = mid - 2 * std, mid + 2 * std
    below = (close < lower) & lower.notna()
    above = (close > upper) & upper.notna()
    put("bollinger_lower_touch", int((below & ~below.shift(1, fill_value=False)).sum()))
    put("bollinger_upper_touch", int((above & ~above.shift(1, fill_value=False)).sum()))

    for lb in (20, 60, 120):
        prior_high = close.shift(1).rolling(lb).max()
        brk = (close > prior_high) & prior_high.notna()
        put(f"breakout_{lb}d", int((brk & ~brk.shift(1, fill_value=False)).sum()))

    if "volume" in pdf.columns:
        vol = pdf["volume"].astype(float)
        avg20 = vol.shift(1).rolling(20).mean()
        spike = (vol > 3.0 * avg20) & avg20.notna() & (avg20 > 0)
        put("volume_spike_3x", int((spike & ~spike.shift(1, fill_value=False)).sum()))

    high60 = close.shift(1).rolling(60).max()
    dd60 = close / high60 - 1.0
    put("drop_10pct_from_60d_high", _cross_below_count(dd60.dropna(), -0.10))

    if {"high", "low"}.issubset(pdf.columns):
        tp = (pdf["high"].astype(float) + pdf["low"].astype(float) + close) / 3.0
        tp_ma = tp.rolling(14).mean()
        # CCI 정의의 mean deviation(평균절대편차). rolling.apply는 느리므로 근사로
        # rolling std × 0.7979(정규분포 가정) 대신 정확 계산을 유지한다 — 5천 행 수준에서 충분.
        md = tp.rolling(14).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
        cci = (tp - tp_ma) / (0.015 * md.replace(0.0, np.nan))
        put("cci_below_minus_100", _cross_below_count(cci.dropna(), -100.0))

        low14 = pdf["low"].astype(float).rolling(14).min()
        high14 = pdf["high"].astype(float).rolling(14).max()
        k = 100.0 * (close - low14) / (high14 - low14).replace(0.0, np.nan)
        d = k.rolling(3).mean()
        put("stochastic_buy_cross", _upcross_count(k, d))
    return out


def compute_fundamental_coverage(pdf: pd.DataFrame) -> Dict[str, DataCoverage]:
    """재무 지표별 커버리지. parquet 병합이 PIT-safe(available_from 기준)이므로
    존재하는 지표는 point_in_time_safe=True로 표시한다."""
    out: Dict[str, DataCoverage] = {}
    total = len(pdf)
    for col in _FUNDAMENTAL_FEATURE_COLS:
        if col not in pdf.columns or total == 0:
            out[col] = DataCoverage(available=False)
            continue
        valid = pdf[col].notna()
        n = int(valid.sum())
        if n < _FUND_MIN_ROWS or (n / total) < _FUND_MIN_RATIO:
            out[col] = DataCoverage(available=False)
            continue
        dates = pdf.index[valid]
        out[col] = DataCoverage(
            available=True,
            start_date=str(dates.min().date()),
            end_date=str(dates.max().date()),
            missing_ratio=_round(1.0 - n / total),
            point_in_time_safe=True,
        )
    return out


def compute_ohlcv_coverage(pdf: pd.DataFrame) -> DataCoverage:
    if len(pdf) == 0:
        return DataCoverage(available=False)
    start, end = pdf.index[0], pdf.index[-1]
    expected = np.busday_count(start.date(), end.date()) + 1
    missing = max(0.0, 1.0 - len(pdf) / expected) if expected > 0 else None
    return DataCoverage(
        available=True,
        start_date=str(start.date()),
        end_date=str(end.date()),
        missing_ratio=_round(missing),
    )


# ─── 프로파일 조립 ───────────────────────────────────────────────────────────────

_AGENT_GUIDANCE: tuple[str, ...] = (
    "이 프로파일의 통계는 과거 데이터의 설명적 요약이다 — 미래 성과를 보장하거나 예측하지 않는다.",
    "신호 발생 횟수가 10회 미만인 조건은 통계적으로 신뢰하기 어렵다 — 기준 완화나 기간 연장을 되물어라.",
    "연간 수십 회 이상 발생하는 신호는 거래비용·슬리피지 영향을 경고하라.",
    "과거 수익률이 가장 높았던 파라미터를 기본값으로 추천하지 마라 — 탐색 범위만 제안한다.",
    "재무 지표 조건은 공시 시점(available_from) 이후 값만 사용된다 — 결산 기간으로 소급 적용된다고 설명하지 마라.",
    "unsupported_features에 있는 데이터는 존재하지 않는다 — 지원하는 것처럼 표현하지 마라.",
    "단일 종목 모드에서는 '어떤 종목을 살까'가 아니라 '언제 사고 언제 팔까'를 물어라.",
)


def _load_master_entry(symbol: str) -> dict:
    try:
        from .universe_pit import _load_master
        for s in _load_master():
            if s.get("symbol") == symbol:
                return s
    except Exception:
        logger.debug("stock master 조회 실패: %s", symbol, exc_info=True)
    return {}


def _resolve_name(symbol: str, master: dict) -> str:
    if master.get("name"):
        return master["name"]
    try:
        from stock_analysis.symbol_resolver import resolve_by_symbol
        ref = resolve_by_symbol(symbol)
        if ref is not None:
            return ref.name
    except Exception:
        pass
    return symbol


class StockProfileService:
    """종목 프로파일 생성·캐시 서비스(결정론). Agent는 이 결과의 직렬화본만 읽는다."""

    def __init__(self, data_dir: str = _OHLCV_DIR,
                 repository: Optional[StockProfileRepository] = None):
        self.data_dir = data_dir
        self.repository = repository or StockProfileRepository()
        self._memory: dict[str, tuple[Dict[str, str], StockResearchProfile]] = {}
        self._lock = threading.Lock()

    # 소스 fingerprint. 섹션별로 기록해 향후 소스 분리 시 부분 갱신이 가능하도록 한다
    # (현재 technical/signals/financial 모두 동일 parquet → 함께 무효화된다).
    def _fingerprints(self, symbol: str) -> Optional[Dict[str, str]]:
        path = os.path.join(self.data_dir, f"{symbol}.parquet")
        try:
            st = os.stat(path)
        except OSError:
            return None
        fp = f"{st.st_mtime_ns}:{st.st_size}:v{PROFILE_VERSION}"
        return {"technical": fp, "signals": fp, "financial": fp}

    def get_profile(self, symbol: str) -> Optional[StockResearchProfile]:
        """캐시 우선 조회. 소스가 없으면 None(가짜 프로파일 생성 금지)."""
        fingerprints = self._fingerprints(symbol)
        if fingerprints is None:
            return None
        with self._lock:
            cached = self._memory.get(symbol)
            if cached and cached[0] == fingerprints:
                return cached[1]
        profile = self.repository.get(symbol, fingerprints)
        if profile is None:
            profile = self.build_profile(symbol)
            if profile is None:
                return None
            try:
                self.repository.save(profile, fingerprints)
            except OSError:
                logger.warning("프로파일 캐시 저장 실패: %s", symbol, exc_info=True)
        with self._lock:
            self._memory[symbol] = (fingerprints, profile)
        return profile

    def build_profile(self, symbol: str) -> Optional[StockResearchProfile]:
        """프로파일을 소스에서 새로 계산한다(캐시 미사용)."""
        pdf = self._load_ohlcv(symbol)
        if pdf is None or len(pdf) == 0:
            return None

        master = _load_master_entry(symbol)
        sector = None
        if "sector" in pdf.columns:
            tail = pdf["sector"].dropna()
            if len(tail):
                sector = str(tail.iloc[-1]) or None

        ohlcv_cov = compute_ohlcv_coverage(pdf)
        fund_cov = compute_fundamental_coverage(pdf)
        technical = compute_technical_stats(pdf)
        signals = compute_signal_stats(pdf)

        supported = {
            "ohlcv", "moving_average", "rsi", "macd", "bollinger", "stochastic",
            "cci", "breakout", "volume", "trading_value",
        }
        categories = {"trend_following", "mean_reversion", "breakout", "volume"}
        for col, cov in fund_cov.items():
            if cov.available:
                supported.add(col)
        if any(fund_cov[c].available for c in ("per", "pbr", "psr")):
            categories.add("valuation_timeseries")
        if fund_cov.get("dividend_yield", DataCoverage(False)).available:
            categories.add("dividend_yield_timeseries")

        warnings: list[str] = []
        years = _years(pdf)
        if years < 3.0:
            warnings.append(
                f"과거 데이터가 약 {years:.1f}년으로 짧아 장기 전략 검증의 신뢰도가 낮을 수 있습니다."
            )
        if ohlcv_cov.missing_ratio is not None and ohlcv_cov.missing_ratio > _MISSING_WARN_RATIO:
            warnings.append(
                f"거래일 대비 데이터 누락 비율이 {ohlcv_cov.missing_ratio:.0%}로 높습니다"
                " — 거래정지·데이터 공백 구간이 결과에 영향을 줄 수 있습니다."
            )
        if "volume" in pdf.columns:
            halt_ratio = float((pdf["volume"].astype(float) <= 0).mean())
            if halt_ratio > 0.02:
                warnings.append(
                    f"거래량 0(거래정지 추정) 구간이 전체의 {halt_ratio:.0%}입니다"
                    " — 해당 구간은 체결이 불가능해 백테스트에서 제외됩니다."
                )
        if master.get("delistingDate"):
            warnings.append(
                f"이 종목은 {master['delistingDate']}에 상장폐지되었습니다"
                " — 백테스트는 상장폐지 시점에 강제 청산됩니다."
            )
        fund_available = [c for c, cov in fund_cov.items() if cov.available]
        if fund_available and ohlcv_cov.start_date:
            starts = [fund_cov[c].start_date for c in fund_available if fund_cov[c].start_date]
            if starts and min(starts) > ohlcv_cov.start_date:
                warnings.append(
                    f"재무 지표는 {min(starts)}부터 존재합니다 — 그 이전 구간에는"
                    " 재무 조건이 적용되지 않습니다."
                )

        source_ts = None
        try:
            st = os.stat(os.path.join(self.data_dir, f"{symbol}.parquet"))
            source_ts = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()
        except OSError:
            pass

        return StockResearchProfile(
            profile_version=PROFILE_VERSION,
            mode="single_stock",
            symbol=symbol,
            name=_resolve_name(symbol, master),
            market=master.get("market") or "UNKNOWN",
            sector=sector,
            generated_at=datetime.now(tz=timezone.utc).isoformat(),
            source_updated_at={
                "ohlcv": source_ts, "financials": source_ts, "investor_flow": None,
            },
            data_coverage={"ohlcv": ohlcv_cov, **fund_cov},
            historical_characteristics=technical,
            signal_statistics=signals,
            supported_features=frozenset(supported),
            supported_strategy_categories=frozenset(categories),
            unsupported_features=frozenset(PIPELINE_UNSUPPORTED_FEATURES),
            data_quality_warnings=tuple(warnings),
            agent_guidance=_AGENT_GUIDANCE,
        )

    def _load_ohlcv(self, symbol: str) -> Optional[pd.DataFrame]:
        """수정주가·기업행사 보정이 적용된 DataFrame(DataLoader.preprocess_data 재사용)."""
        from .loader import DataLoader

        loader = DataLoader(self.data_dir)
        df = loader.load_symbol_data(symbol)
        if df is None:
            return None
        try:
            return loader.preprocess_data(df)
        except Exception:
            logger.warning("프로파일용 전처리 실패: %s", symbol, exc_info=True)
            return None


# 프로세스 전역 서비스(엔드포인트·파서·코치가 공유 — 메모리 캐시 일원화).
_default_service: Optional[StockProfileService] = None
_default_service_lock = threading.Lock()


def get_default_service() -> StockProfileService:
    global _default_service
    with _default_service_lock:
        if _default_service is None:
            _default_service = StockProfileService()
        return _default_service


def get_stock_profile(symbol: str) -> Optional[StockResearchProfile]:
    """편의 함수 — 기본 서비스에서 프로파일을 조회한다(실패 시 None, 예외 없음)."""
    try:
        return get_default_service().get_profile(symbol)
    except Exception:
        logger.warning("stock profile 조회 실패: %s", symbol, exc_info=True)
        return None
