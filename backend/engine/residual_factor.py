"""시장·섹터 중립 잔차 반전 시그널 — 랭킹 지표 ``residual_reversal``(엔진 v16.17).

정의 (2026-09-20 사용자 확정)
-----------------------------
종목 i, 거래일 t에 대해
1. 직전 L거래일(회귀 룩백) 일간 수익률을 **자기 상장 시장 지수 수익률 + 소속 섹터 평균 수익률**
   (+절편)에 회귀한다. 섹터 평균은 **전체 상장 종목** 동일가중, **자기 제외**(leave-one-out)다.
2. 그 회귀의 잔차 중 최근 K거래일(누적 기간)을 더하고, **회귀 구간(L일) 잔차 표준편차**로 나눈다
   → 종목별 원점수(유니버스와 무관).
3. 전략 유니버스 횡단면에서 상하위 1% 윈저라이즈 → z-score → 부호 반전. 값이 클수록
   '시장·섹터로 설명되지 않는 최근 낙폭이 큰 종목'이다.

개방 파라미터는 이산값만 허용한다 — L ∈ {60, 120, 250}, K ∈ {3, 5, 10, 20}, 기본 (60, 5).
윈저라이즈 비율·정규화·부호 반전·설명변수는 고정이다(노출하지 않는다).

계약
----
- **fail-closed**: 시장(지수)·섹터를 모르는 종목(미국·ETF·마스터 밖), 회귀 구간에 결측이
  하나라도 있는 날, 시장·섹터 수익률이 공선인 날, 섹터에 다른 종목이 없는 날은 NaN → 랭킹
  후보에서 빠진다(0이나 중립값으로 위장하지 않는다 — relative_return과 같은 계약).
- **지표 전용 가격**: 백테스트 옵션(배당 반영 여부·기간 절단)과 무관하게 파일 전체 이력에
  ``DataLoader.preprocess_data(apply_dividends=True)``(수정주가 + 배당 토탈리턴 + 기업행위
  정제)를 적용한 종가다. 옵션마다 시그널이 달라지면 사전계산 캐시를 공유할 수 없다.
- **캐시는 답을 바꾸지 않는다**: 원점수는 종목(열) 단위로 독립인 누적합 연산이고 항상 같은
  달력(코스피 지수 거래일 전체)의 첫 행에서 시작하므로, 어떤 종목 묶음으로 계산해도 값이
  1비트까지 같다. 디스크 캐시(``<data>/factor_cache``)는 데이터 지문(파일명·크기·mtime +
  섹터 소속)이 일치할 때만 쓰고, 다르면 같은 함수로 다시 계산한다.
  · ``returns.parquet``·``sector_returns.parquet`` — 모든 (L, K) 조합의 공통 재료. 없거나
    낡으면 그 자리에서 만들고 원자적으로 기록한다(write-through).
  · ``score_60_5.parquet`` — 기본 조합 원점수. ``scripts/build_residual_factor_cache.py``
    (야간 동기화)만 만든다. 없거나 낡으면 필요한 종목만 온디맨드로 계산한다.
- 한계: 섹터 소속은 현재 시점 분류다(과거 시점 소속 이력 없음).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import warnings
from collections import OrderedDict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import polars as pl

_logger = logging.getLogger(__name__)

RESIDUAL_REVERSAL_ID = "residual_reversal"
REGRESSION_LOOKBACKS: Tuple[int, ...] = (60, 120, 250)
ACCUMULATION_DAYS: Tuple[int, ...] = (3, 5, 10, 20)
DEFAULT_LOOKBACK = 60
DEFAULT_ACCUMULATION = 5
WINSOR_PCT = 0.01                 # 고정 — 상하위 1%
_REGRESSORS = 3                   # 절편 + 시장 + 섹터 (잔차 표준편차 자유도)
_COLLINEAR_EPS = 1e-10            # 시장·섹터 수익률 공선 판정(상대 행렬식)
_CHUNK = 256                      # 회귀 계산의 열 묶음(메모리 상한용 — 결과와 무관)
_CACHE_DIR_NAME = "factor_cache"
_CACHE_VERSION = 1                # 계산식·전처리가 바뀌면 올린다(낡은 캐시 무효화)
_PRICE_COLS = ("date", "close", "adj_close", "dividends", "volume")


def validate_params(lookback: int, accumulation: int) -> None:
    """허용 조합이 아니면 ValueError — 엔진 최종 관문(검증기를 우회한 요청 방어)."""
    if lookback not in REGRESSION_LOOKBACKS:
        raise ValueError(f"잔차 회귀 룩백은 {REGRESSION_LOOKBACKS} 중 하나여야 합니다: {lookback}")
    if accumulation not in ACCUMULATION_DAYS:
        raise ValueError(f"잔차 누적 기간은 {ACCUMULATION_DAYS} 중 하나여야 합니다: {accumulation}")
    if lookback < accumulation:
        raise ValueError(f"회귀 룩백({lookback})은 누적 기간({accumulation})보다 짧을 수 없습니다")


# ─── 순수 계산 ────────────────────────────────────────────────────────────────

def _rolling_sum(values: np.ndarray, window: int) -> np.ndarray:
    """열 방향 누적합 차분 — 행 i는 (i-window, i] 구간 합. 앞쪽 window-1행은 부분합(호출부가 마스크)."""
    csum = np.cumsum(values, axis=0)
    out = csum.copy()
    out[window:] = csum[window:] - csum[:-window]
    return out


def raw_scores(y: np.ndarray, m: np.ndarray, s: np.ndarray,
               lookback: int, accumulation: int) -> np.ndarray:
    """(T×N) 수익률 y·시장 m·섹터 s → (T×N) 원점수(float32). 열마다 독립이다.

    원점수 = Σ(최근 K일 잔차) ÷ sqrt(SSE/(L−3)). 잔차는 t 시점 회귀(직전 L일) 계수 기준.
    """
    validate_params(lookback, accumulation)
    L, K = lookback, accumulation
    ok = np.isfinite(y) & np.isfinite(m) & np.isfinite(s)
    y0, m0, s0 = (np.where(ok, a, 0.0) for a in (y, m, s))
    full = _rolling_sum(ok.astype(np.float64), L) == L
    full[:L - 1] = False

    sy, sm, ss = _rolling_sum(y0, L), _rolling_sum(m0, L), _rolling_sum(s0, L)
    cmm = _rolling_sum(m0 * m0, L) - sm * sm / L
    css = _rolling_sum(s0 * s0, L) - ss * ss / L
    cms = _rolling_sum(m0 * s0, L) - sm * ss / L
    cym = _rolling_sum(y0 * m0, L) - sy * sm / L
    cys = _rolling_sum(y0 * s0, L) - sy * ss / L
    cyy = _rolling_sum(y0 * y0, L) - sy * sy / L

    with np.errstate(divide="ignore", invalid="ignore"):
        det = cmm * css - cms * cms
        solvable = full & (det > _COLLINEAR_EPS * cmm * css)
        beta_m = (cym * css - cys * cms) / det
        beta_s = (cys * cmm - cym * cms) / det
        alpha = (sy - beta_m * sm - beta_s * ss) / L
        sse = cyy - beta_m * cym - beta_s * cys
        sigma = np.sqrt(np.maximum(sse, 0.0) / (L - _REGRESSORS))
        cum = (_rolling_sum(y0, K) - K * alpha
               - beta_m * _rolling_sum(m0, K) - beta_s * _rolling_sum(s0, K))
        score = cum / sigma
    score[~(solvable & (sigma > 0.0)) | ~np.isfinite(score)] = np.nan
    return score.astype(np.float32)


def leave_one_out_sector_return(y: np.ndarray, sector_sum: np.ndarray,
                                sector_cnt: np.ndarray) -> np.ndarray:
    """자기 제외 섹터 평균 — (섹터 합 − 자기) ÷ (섹터 수 − 자기 유효 여부). 남는 종목이 없으면 NaN."""
    own_ok = np.isfinite(y)
    others = sector_cnt - own_ok
    with np.errstate(divide="ignore", invalid="ignore"):
        out = (sector_sum - np.where(own_ok, y, 0.0)) / others
    out[others < 1] = np.nan
    return out


def cross_sectional_signal(raw: pd.DataFrame) -> pd.DataFrame:
    """행(거래일)마다 상하위 1% 윈저라이즈 → z-score → **부호 반전**.

    반전은 잔차 반전 시그널의 정의('설명되지 않는 낙폭이 클수록 높은 점수')이지 표준화의
    일부가 아니다 — 높을수록 좋은 지표(PEAD 등)는 `winsorized_zscore`를 그대로 쓴다.
    """
    return -winsorized_zscore(raw)


def winsorized_zscore(raw: pd.DataFrame) -> pd.DataFrame:
    """행(거래일)마다 상하위 1% 윈저라이즈 → z-score. 유효 종목 2개 미만인 날은 NaN."""
    arr = raw.to_numpy(dtype=np.float64, copy=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)   # 전부 NaN인 행
        lo, hi = np.nanquantile(arr, [WINSOR_PCT, 1.0 - WINSOR_PCT], axis=1, keepdims=True)
        clipped = np.clip(arr, lo, hi)
        mean = np.nanmean(clipped, axis=1, keepdims=True)
        std = np.nanstd(clipped, axis=1, ddof=1, keepdims=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        score = (clipped - mean) / std
    score[~np.isfinite(score)] = np.nan
    return pd.DataFrame(score, index=raw.index, columns=raw.columns)


# ─── 재료: 달력·수익률·섹터 ───────────────────────────────────────────────────

def cache_dir_for(data_dir: str | os.PathLike) -> Path:
    """OHLCV 디렉터리(data/ohlcv)의 형제 `data/factor_cache`."""
    return Path(os.path.dirname(os.path.normpath(str(data_dir)))) / _CACHE_DIR_NAME


def _calendar(data_dir: str | os.PathLike) -> Optional[pd.DatetimeIndex]:
    """코스피 지수 거래일 전체 — 모든 경로가 같은 첫 행에서 누적합을 시작하게 하는 공통 달력."""
    from engine.market_index import load_index_frame

    frame = load_index_frame("KOSPI", data_dir)
    if frame is None or len(frame) == 0:
        return None
    return pd.DatetimeIndex(frame["date"].to_pandas())


def _sector_by_symbol() -> Dict[str, str]:
    from engine.universe_pit import _load_sector_map

    return _load_sector_map()


def factor_symbols(data_dir: str | os.PathLike) -> List[str]:
    """지표가 정의되는 전 종목 — 섹터·상장 시장을 알고 가격 파일이 있는 한국 종목(정렬)."""
    from engine.market_index import market_for_symbol

    return sorted(
        sym for sym in _sector_by_symbol()
        if market_for_symbol(sym) and os.path.exists(os.path.join(str(data_dir), f"{sym}.parquet"))
    )


def _symbol_returns(loader, data_dir: str, symbol: str,
                    calendar: pd.DatetimeIndex) -> Optional[np.ndarray]:
    """지표 전용 일간 수익률(달력 정렬). 상장 전·상폐 후는 NaN, 그 사이 결측일은 전진 충전(수익률 0)."""
    path = os.path.join(data_dir, f"{symbol}.parquet")
    if not os.path.exists(path):
        return None
    schema = pl.read_parquet_schema(path)
    frame = pl.read_parquet(path, columns=[c for c in _PRICE_COLS if c in schema])
    if len(frame) == 0:
        return None
    close = loader.preprocess_data(frame, apply_dividends=True)["close"].astype(float)
    close = close[~close.index.duplicated(keep="last")]
    first, last = close.first_valid_index(), close.last_valid_index()
    if first is None:
        return None
    aligned = close.reindex(calendar).ffill()
    aligned[(calendar < first) | (calendar > last)] = np.nan
    return aligned.pct_change(fill_method=None).to_numpy()


def _market_returns(data_dir: str | os.PathLike, calendar: pd.DatetimeIndex) -> Dict[str, np.ndarray]:
    from engine.market_index import INDEX_CLOSE_COL, INDEX_MARKETS, load_index_frame

    out: Dict[str, np.ndarray] = {}
    for market in INDEX_MARKETS:
        frame = load_index_frame(market, data_dir)
        if frame is None:
            continue
        ser = frame.to_pandas().set_index("date")[INDEX_CLOSE_COL].astype(float)
        ser.index = pd.DatetimeIndex(ser.index)
        out[market] = ser.reindex(calendar).pct_change(fill_method=None).to_numpy()
    return out


# ─── 디스크 캐시 ──────────────────────────────────────────────────────────────

def data_fingerprint(data_dir: str | os.PathLike) -> str:
    """지표 입력 전체의 지문 — 가격 파일(이름·크기·mtime)·지수 파일·섹터 소속·계산식 버전."""
    from engine.market_index import INDEX_MARKETS, index_path

    digest = hashlib.sha256(f"v{_CACHE_VERSION}".encode())
    sectors = _sector_by_symbol()
    for sym in factor_symbols(data_dir):
        st = os.stat(os.path.join(str(data_dir), f"{sym}.parquet"))
        digest.update(f"{sym}:{sectors[sym]}:{st.st_size}:{st.st_mtime_ns};".encode())
    for market in INDEX_MARKETS:
        path = index_path(market, data_dir)
        if path.exists():
            st = path.stat()
            digest.update(f"{market}:{st.st_size}:{st.st_mtime_ns};".encode())
    return digest.hexdigest()


def _meta_path(data_dir) -> Path:
    return cache_dir_for(data_dir) / "meta.json"


def _read_meta(data_dir) -> Dict[str, str]:
    try:
        return json.loads(_meta_path(data_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_atomic(path: Path, writer) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        writer(tmp)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _stamp(data_dir, key: str, fingerprint: str) -> None:
    meta = _read_meta(data_dir)
    meta[key] = fingerprint
    _write_atomic(_meta_path(data_dir),
                  lambda p: p.write_text(json.dumps(meta, indent=2), encoding="utf-8"))


def _cache_valid(data_dir, key: str, fingerprint: str, filename: str) -> bool:
    return (_read_meta(data_dir).get(key) == fingerprint
            and (cache_dir_for(data_dir) / filename).exists())


def _write_panel(path: Path, calendar: pd.DatetimeIndex, columns: Sequence[str],
                 values: np.ndarray) -> None:
    frame = pl.DataFrame({"date": pl.Series(calendar.to_numpy()).cast(pl.Datetime("us")),
                          **{col: values[:, j] for j, col in enumerate(columns)}})
    _write_atomic(path, lambda p: frame.write_parquet(p))


def _read_panel(path: Path, columns: Sequence[str]) -> Tuple[pd.DatetimeIndex, Dict[str, np.ndarray]]:
    have = set(pl.read_parquet_schema(path))
    picked = [c for c in columns if c in have]
    frame = pl.read_parquet(path, columns=["date", *picked])
    dates = pd.DatetimeIndex(frame["date"].to_pandas())
    return dates, {c: frame[c].to_numpy() for c in picked}


def _build_materials(data_dir: str, fingerprint: str) -> None:
    """전 종목 수익률 + 섹터 합·개수를 계산해 기록한다(모든 조합의 공통 재료)."""
    from engine.loader import DataLoader

    calendar = _calendar(data_dir)
    loader = DataLoader(data_dir)
    sectors = _sector_by_symbol()
    symbols, cols = [], []
    for sym in factor_symbols(data_dir):
        ret = _symbol_returns(loader, data_dir, sym, calendar)
        if ret is not None:
            symbols.append(sym)
            cols.append(ret)
    returns = np.column_stack(cols) if cols else np.empty((len(calendar), 0))
    names = sorted({sectors[sym] for sym in symbols})
    col_of = {name: j for j, name in enumerate(names)}
    sec_sum = np.zeros((len(calendar), len(names)))
    sec_cnt = np.zeros((len(calendar), len(names)))
    for j, sym in enumerate(symbols):       # 종목 순서(정렬) 고정 — 합산 순서가 곧 결과다
        ok = np.isfinite(returns[:, j])
        k = col_of[sectors[sym]]
        sec_sum[:, k] += np.where(ok, returns[:, j], 0.0)
        sec_cnt[:, k] += ok
    cache = cache_dir_for(data_dir)
    _write_panel(cache / "returns.parquet", calendar, symbols, returns)
    _write_panel(cache / "sector_returns.parquet", calendar,
                 [f"sum::{n}" for n in names] + [f"cnt::{n}" for n in names],
                 np.column_stack([sec_sum, sec_cnt]))
    _stamp(data_dir, "materials", fingerprint)
    _logger.info("[RESIDUAL-FACTOR] 재료 캐시 기록 | 종목=%d 섹터=%d 거래일=%d",
                 len(symbols), len(names), len(calendar))


_BUILD_LOCK = threading.Lock()


def _ensure_materials(data_dir: str, fingerprint: str) -> None:
    if _cache_valid(data_dir, "materials", fingerprint, "returns.parquet"):
        return
    with _BUILD_LOCK:
        if not _cache_valid(data_dir, "materials", fingerprint, "returns.parquet"):
            _build_materials(data_dir, fingerprint)


def _compute_raw(data_dir: str, symbols: Sequence[str], lookback: int,
                 accumulation: int) -> Tuple[pd.DatetimeIndex, Dict[str, np.ndarray]]:
    """재료 캐시에서 필요한 종목만 읽어 원점수를 계산한다(열 묶음 단위)."""
    cache = cache_dir_for(data_dir)
    sectors = _sector_by_symbol()
    from engine.market_index import market_for_symbol

    calendar, rets = _read_panel(cache / "returns.parquet", symbols)
    market_ret = _market_returns(data_dir, calendar)
    wanted = [s for s in symbols if s in rets and market_for_symbol(s) in market_ret]
    sector_cols = sorted({sectors[s] for s in wanted})
    _, sec = _read_panel(cache / "sector_returns.parquet",
                         [f"{kind}::{n}" for n in sector_cols for kind in ("sum", "cnt")])
    out: Dict[str, np.ndarray] = {}
    for start in range(0, len(wanted), _CHUNK):
        chunk = wanted[start:start + _CHUNK]
        y = np.column_stack([rets[s] for s in chunk])
        m = np.column_stack([market_ret[market_for_symbol(s)] for s in chunk])
        s_ret = leave_one_out_sector_return(
            y,
            np.column_stack([sec[f"sum::{sectors[s]}"] for s in chunk]),
            np.column_stack([sec[f"cnt::{sectors[s]}"] for s in chunk]),
        )
        scores = raw_scores(y, m, s_ret, lookback, accumulation)
        out.update({sym: scores[:, j] for j, sym in enumerate(chunk)})
    return calendar, out


def build_default_score_cache(data_dir: str | os.PathLike) -> int:
    """기본 조합(60/5) 원점수를 전 종목에 대해 계산해 기록한다. 반환: 기록한 종목 수."""
    data_dir = str(data_dir)
    if _calendar(data_dir) is None:
        raise RuntimeError("코스피 지수 시계열이 없습니다 — data/index/KOSPI.parquet")
    fingerprint = data_fingerprint(data_dir)
    _ensure_materials(data_dir, fingerprint)
    calendar, scores = _compute_raw(data_dir, factor_symbols(data_dir),
                                    DEFAULT_LOOKBACK, DEFAULT_ACCUMULATION)
    symbols = sorted(scores)
    values = (np.column_stack([scores[s] for s in symbols])
              if symbols else np.empty((len(calendar), 0), dtype=np.float32))
    _write_panel(cache_dir_for(data_dir) / _default_score_file(), calendar, symbols, values)
    _stamp(data_dir, "score_default", fingerprint)
    return len(symbols)


def _default_score_file() -> str:
    return f"score_{DEFAULT_LOOKBACK}_{DEFAULT_ACCUMULATION}.parquet"


# ─── 엔진 진입점 ──────────────────────────────────────────────────────────────

_MEMO: "OrderedDict[Tuple, pd.DataFrame]" = OrderedDict()
_MEMO_MAX = 4
_MEMO_LOCK = threading.Lock()


def raw_score_panel(data_dir: str | os.PathLike, symbols: Iterable[str],
                    lookback: int, accumulation: int) -> Optional[pd.DataFrame]:
    """(달력 × 종목) 원점수 패널. 지수 시계열이 없으면 None(호출부가 경고로 드러낸다).

    기본 조합은 사전계산 캐시가 유효하면 그것을 읽고, 아니면(다른 조합 포함) 같은 계산 함수로
    온디맨드 계산한다 — 두 경로의 값은 같다(모듈 docstring의 계약).
    """
    validate_params(lookback, accumulation)
    data_dir = str(data_dir)
    symbols = list(symbols)
    if _calendar(data_dir) is None:
        return None
    fingerprint = data_fingerprint(data_dir)
    key = (fingerprint, lookback, accumulation, tuple(symbols))
    with _MEMO_LOCK:
        if key in _MEMO:
            _MEMO.move_to_end(key)
            return _MEMO[key]
    is_default = (lookback, accumulation) == (DEFAULT_LOOKBACK, DEFAULT_ACCUMULATION)
    if is_default and _cache_valid(data_dir, "score_default", fingerprint, _default_score_file()):
        calendar, scores = _read_panel(cache_dir_for(data_dir) / _default_score_file(), symbols)
        source = "사전계산 캐시"
    else:
        _ensure_materials(data_dir, fingerprint)
        calendar, scores = _compute_raw(data_dir, symbols, lookback, accumulation)
        source = "온디맨드"
    panel = pd.DataFrame(
        {s: scores.get(s, np.full(len(calendar), np.nan, dtype=np.float32)) for s in symbols},
        index=calendar, columns=symbols, dtype=np.float32,
    )
    _logger.info("[RESIDUAL-FACTOR] 원점수 패널 | L=%d K=%d 종목=%d(정의 %d) 경로=%s",
                 lookback, accumulation, len(symbols), len(scores), source)
    with _MEMO_LOCK:
        _MEMO[key] = panel
        while len(_MEMO) > _MEMO_MAX:
            _MEMO.popitem(last=False)
    return panel


def return_materials(
    data_dir: str | os.PathLike, symbols: Iterable[str]
) -> Optional[Tuple[pd.DatetimeIndex, Dict[str, np.ndarray], Dict[str, np.ndarray]]]:
    """지표 공통 재료 — (달력, 종목별 일간 수익률, 시장별 일간 수익률). 지수가 없으면 None.

    잔차 반전과 실적 서프라이즈(`engine/earnings_factor.py`)가 공유한다 — 둘 다 '지표 전용
    전체 이력'(배당 반영 수정주가, 백테스트 창과 무관) 계약이라 재료가 같다. 같은 재료를
    쓰므로 두 지표의 값은 백테스트 창·워밍업 길이에 흔들리지 않는다.
    """
    if _calendar(data_dir) is None:
        return None
    data_dir = str(data_dir)
    fingerprint = data_fingerprint(data_dir)
    _ensure_materials(data_dir, fingerprint)
    calendar, returns = _read_panel(
        cache_dir_for(data_dir) / "returns.parquet", list(symbols)
    )
    return calendar, returns, _market_returns(data_dir, calendar)


def residual_reversal_panel(raw_price_df: pd.DataFrame, lookback: int, accumulation: int,
                            data_dir: str | os.PathLike) -> Optional[pd.DataFrame]:
    """엔진 랭킹 입력 — raw_price_df와 같은 모양의 시그널 패널(클수록 상위). 계산 불가면 None.

    횡단면(윈저라이즈·z-score)은 그날 가격이 있는 패널 종목 안에서 매긴다(상장 전 구간 제외).
    """
    raw = raw_score_panel(data_dir, raw_price_df.columns, lookback, accumulation)
    if raw is None:
        return None
    aligned = raw.reindex(index=pd.DatetimeIndex(raw_price_df.index)).astype(np.float64)
    aligned.index = raw_price_df.index
    aligned = aligned.where(raw_price_df.ffill().notna())
    return cross_sectional_signal(aligned)
