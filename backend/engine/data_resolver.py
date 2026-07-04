"""
DataResolver — 임기응변 데이터 해결 엔진.

백테스트 실행 시 전략 조건에 필요한 데이터가 DataFrame에 없으면,
API 조회 · 기존 컬럼 계산 등으로 즉시 보충하고 모든 과정을 로그로 남긴다.
"""

import logging
import time
from typing import Dict, List, Any, Optional, Tuple

import numpy as np
import pandas as pd
import polars as pl

from .signals import FUNDAMENTAL_CIDS, FUNDAMENTAL_LABELS

logger = logging.getLogger(__name__)


class ResolutionLog:
    """해결 과정 로그 항목."""
    def __init__(self, level: str, message: str):
        self.level = level  # INFO, WARN, ERROR, SUCCESS
        self.message = message

    def to_dict(self) -> Dict[str, str]:
        return {"level": self.level, "message": self.message}


# ── 조건 ID → 필요한 컬럼 매핑 ───────────────────────────────────────────
# 각 조건이 signal evaluation에서 참조하는 컬럼을 정의.
# 파라미터에 따라 동적으로 결정되는 컬럼은 _get_required_columns에서 처리.

FUNDAMENTAL_IDS = set(FUNDAMENTAL_CIDS)

# 기술적 지표: IndicatorEngine이 계산해야 할 것들
TECHNICAL_IDS = {
    'ma_crossover', 'rsi', 'ema', 'macd', 'stochastic',
    'cci', 'adx', 'bollinger_bands', 'volume_spike', 'breakout',
}

# 계산 가능한 파생 지표
COMPUTABLE_IDS = {'trading_value', 'per', 'pbr'}


def _collect_all_conditions(group: Optional[Dict]) -> List[Dict]:
    """조건 그룹에서 모든 리프 조건을 재귀적으로 수집."""
    if not group:
        return []
    result = []
    for c in group.get('conditions', []):
        if 'conditions' in c:
            result.extend(_collect_all_conditions(c))
        else:
            result.append(c)
    return result


def _get_required_columns(cond: Dict) -> List[str]:
    """조건 하나가 signal evaluation에서 참조하는 컬럼 이름 목록."""
    cid = cond.get('id', '')
    p = cond.get('params', {})

    if cid == 'ma_crossover':
        short = p.get('shortMA', p.get('short_period', p.get('short', 5)))
        long_ = p.get('longMA', p.get('long_period', p.get('long', 20)))
        return [f'close_{short}_sma', f'close_{long_}_sma']
    elif cid == 'rsi':
        period = p.get('period', p.get('rsi_period', 14))
        return [f'rsi_{period}']
    elif cid == 'ema':
        short_p = p.get('shortPeriod', p.get('short'))
        long_p = p.get('longPeriod', p.get('long'))
        if short_p is not None and long_p is not None:
            return [f'close_{int(short_p)}_ema', f'close_{int(long_p)}_ema']
        period = p.get('period', 20)
        return [f'close_{period}_ema', 'close']
    elif cid == 'macd':
        return ['macd', 'macds']
    elif cid == 'stochastic':
        return ['kdjk', 'kdjd']
    elif cid == 'cci':
        period = p.get('period', 14)
        return [f'cci_{period}']
    elif cid == 'adx':
        return ['adx']
    elif cid == 'bollinger_bands':
        return ['boll_ub', 'boll_lb', 'close']
    elif cid == 'volume_spike':
        period = p.get('period', 20)
        return ['obv', f'obv_{period}_sma']
    elif cid == 'breakout':
        period = p.get('lookbackPeriod', 20)
        return [f'high_{period}_max', f'low_{period}_min']
    elif cid == 'trading_value':
        return ['trading_value_20_sma']  # fallback: close, volume
    elif cid in FUNDAMENTAL_IDS:
        return [cid]
    elif cid in ('ai_model', 'ai_drop_model'):
        return ['ai_score'] if cid == 'ai_model' else ['ai_drop_score']
    elif cid in ('price_level', 'price'):
        return ['close']
    elif cid == 'price_limit_exit':
        return ['close']
    return []


class DataResolver:
    """
    전략 조건에 필요한 데이터 컬럼이 DataFrame에 없으면 즉시 해결한다.

    해결 전략:
    1. 기술적 지표 → IndicatorEngine이 이미 계산했어야 함. 없으면 에러 로그.
    2. 펀더멘털 (per/pbr/roe_or_gpa/debt_ratio) → fundamental_fetcher로 즉시 보충.
    3. market_cap → KRX/Naver API로 시가총액 조회.
    4. trading_value_20_sma → close * volume 20일 이동평균으로 직접 계산.
    5. per/pbr → eps/bps가 있으면 close에서 직접 계산.
    """

    def __init__(self):
        self._logs: List[ResolutionLog] = []

    def _log(self, level: str, message: str):
        self._logs.append(ResolutionLog(level, message))
        # WARN → warning, SUCCESS → info for Python logging
        py_level = {"WARN": "warning", "SUCCESS": "info"}.get(level, level.lower())
        log_fn = getattr(logger, py_level, logger.info)
        log_fn(f"[DataResolver] {message}")

    def resolve(
        self,
        symbol: str,
        df_pl: pl.DataFrame,
        entry_group: Optional[Dict],
        exit_group: Optional[Dict],
    ) -> Tuple[pl.DataFrame, List[Dict[str, str]]]:
        """
        전략 조건에 필요한 모든 데이터를 확인하고 누락분을 해결한다.

        Returns:
            (enriched_df, resolution_logs)
        """
        self._logs = []

        # 1. 모든 조건에서 필요한 컬럼 수집
        all_conditions = _collect_all_conditions(entry_group) + _collect_all_conditions(exit_group)
        if not all_conditions:
            return df_pl, []

        existing_cols = set(df_pl.columns)
        needed_map: Dict[str, List[Dict]] = {}  # column → [conditions that need it]

        for cond in all_conditions:
            for col in _get_required_columns(cond):
                needed_map.setdefault(col, []).append(cond)

        # 2. 누락 컬럼 식별
        missing_cols = {col for col in needed_map if col not in existing_cols}

        # 컬럼이 존재하지만 전부 null인 경우도 "누락"으로 처리
        for col in needed_map:
            if col in existing_cols and col not in missing_cols:
                try:
                    if df_pl[col].is_null().all():
                        missing_cols.add(col)
                except Exception:
                    pass

        if not missing_cols:
            self._log("INFO", f"[{symbol}] 모든 데이터 컬럼 확인 완료 — 추가 조회 불필요")
            return df_pl, [l.to_dict() for l in self._logs]

        self._log("INFO", f"[{symbol}] 누락 데이터 감지: {', '.join(sorted(missing_cols))}")

        # 3. 해결 시도
        df_pl = self._resolve_trading_value(symbol, df_pl, missing_cols)
        df_pl = self._resolve_fundamentals(symbol, df_pl, missing_cols)
        df_pl = self._resolve_market_cap(symbol, df_pl, missing_cols)
        df_pl = self._resolve_computable_ratios(symbol, df_pl, missing_cols)

        # 4. 최종 미해결 항목 보고
        still_missing = {col for col in missing_cols if col not in df_pl.columns or self._is_all_null(df_pl, col)}
        if still_missing:
            # 조건 ID로 변환하여 사용자 친화적 메시지 생성
            cond_labels = {**FUNDAMENTAL_LABELS, 'trading_value_20_sma': '거래대금(20일평균)'}
            readable = [cond_labels.get(c, c) for c in sorted(still_missing)]
            self._log("WARN", f"[{symbol}] 미해결 데이터: {', '.join(readable)} — 검증 불가로 해당 종목은 이 필터에서 제외됩니다")

        return df_pl, [l.to_dict() for l in self._logs]

    # ── 해결 전략 구현 ──────────────────────────────────────────────────

    def _resolve_trading_value(self, symbol: str, df_pl: pl.DataFrame, missing: set) -> pl.DataFrame:
        """trading_value_20_sma: close * volume의 20일 이동평균으로 계산."""
        if 'trading_value_20_sma' not in missing:
            return df_pl

        if 'close' not in df_pl.columns or 'volume' not in df_pl.columns:
            self._log("ERROR", f"[{symbol}] 거래대금 계산 불가 — close/volume 컬럼 없음")
            return df_pl

        self._log("INFO", f"[{symbol}] 거래대금(20일평균) 계산 중 — close × volume → 20일 SMA")
        try:
            pdf = df_pl.to_pandas()
            tv = pdf['close'].astype(float) * pdf['volume'].astype(float)
            tv_sma = tv.rolling(window=20, min_periods=1).mean()
            df_pl = df_pl.with_columns(
                pl.Series("trading_value_20_sma", tv_sma.values)
            )
            missing.discard('trading_value_20_sma')
            self._log("SUCCESS", f"[{symbol}] 거래대금(20일평균) 계산 완료 ✓")
        except Exception as e:
            self._log("ERROR", f"[{symbol}] 거래대금 계산 실패: {e}")

        return df_pl

    def _resolve_fundamentals(self, symbol: str, df_pl: pl.DataFrame, missing: set) -> pl.DataFrame:
        """연간 펀더멘털(roe/부채비율/roa/유동비율/성장률…)과 per/pbr/psr를 즉시 보충."""
        from .fundamental_fetcher import (
            fetch_fundamentals, enrich_ohlcv_with_fundamentals, ANNUAL_FUNDAMENTAL_KEYS,
        )
        resolvable = set(ANNUAL_FUNDAMENTAL_KEYS) | {'per', 'pbr', 'psr', 'eps', 'bps'}
        needed_fund = missing & resolvable
        if not needed_fund:
            return df_pl

        readable = [FUNDAMENTAL_LABELS.get(c, c) for c in sorted(needed_fund)]
        self._log("INFO", f"[{symbol}] 펀더멘털 데이터({', '.join(readable)}) 조회 시작...")

        try:
            t0 = time.time()
            fundamentals = fetch_fundamentals(symbol)
            elapsed = time.time() - t0

            if not fundamentals:
                self._log("WARN", f"[{symbol}] 펀더멘털 데이터 조회 실패")
                return df_pl

            self._log("INFO", f"[{symbol}] 펀더멘털 원시 데이터 수신 ({len(fundamentals)}개 연도, {elapsed:.1f}s)")

            pdf_enriched = enrich_ohlcv_with_fundamentals(df_pl.to_pandas(), fundamentals)

            enriched_cols = []
            for col in sorted(needed_fund):
                if col in pdf_enriched.columns and pdf_enriched[col].notna().any():
                    df_pl = df_pl.with_columns(pl.Series(col, pdf_enriched[col].values))
                    enriched_cols.append(FUNDAMENTAL_LABELS.get(col, col))
                    missing.discard(col)

            if enriched_cols:
                self._log("SUCCESS", f"[{symbol}] 펀더멘털 보충 완료: {', '.join(enriched_cols)} ✓")
            else:
                self._log("WARN", f"[{symbol}] 펀더멘털 데이터 수신했으나 유효값 없음 (기간 밖이거나 NaN)")

        except Exception as e:
            self._log("ERROR", f"[{symbol}] 펀더멘털 보충 실패: {e}")

        return df_pl

    def _resolve_market_cap(self, symbol: str, df_pl: pl.DataFrame, missing: set) -> pl.DataFrame:
        """market_cap: 상장주식수 × close로 계산 (주식수는 KRX/Naver에서 조회)."""
        if 'market_cap' not in missing:
            return df_pl

        self._log("INFO", f"[{symbol}] 시가총액 데이터 조회 시작...")

        shares = self._fetch_shares_outstanding(symbol)
        if shares is None or shares <= 0:
            self._log("WARN", f"[{symbol}] 상장주식수 조회 실패 — 시가총액 계산 불가")
            return df_pl

        try:
            close_arr = df_pl['close'].to_numpy().astype(float)
            # 시가총액 = 종가 × 상장주식수 (억 원 단위)
            market_cap_arr = (close_arr * shares) / 1e8
            df_pl = df_pl.with_columns(
                pl.Series("market_cap", market_cap_arr)
            )
            missing.discard('market_cap')
            self._log("SUCCESS", f"[{symbol}] 시가총액 계산 완료 (상장주식수: {shares:,.0f}주) ✓")
        except Exception as e:
            self._log("ERROR", f"[{symbol}] 시가총액 계산 실패: {e}")

        return df_pl

    def _resolve_computable_ratios(self, symbol: str, df_pl: pl.DataFrame, missing: set) -> pl.DataFrame:
        """per/pbr를 eps/bps + close에서 직접 계산 (fundamental_fetcher 이후 fallback)."""
        cols = set(df_pl.columns)

        if 'per' in missing and 'eps' in cols:
            try:
                close = df_pl['close'].to_numpy().astype(float)
                eps = df_pl['eps'].to_numpy().astype(float)
                with np.errstate(divide='ignore', invalid='ignore'):
                    per = np.where((eps != 0) & np.isfinite(eps), close / eps, np.nan)
                per[~np.isfinite(per)] = np.nan
                df_pl = df_pl.with_columns(pl.Series("per", per))
                missing.discard('per')
                self._log("SUCCESS", f"[{symbol}] PER 직접 계산 완료 (close ÷ EPS) ✓")
            except Exception as e:
                self._log("ERROR", f"[{symbol}] PER 직접 계산 실패: {e}")

        if 'pbr' in missing and 'bps' in cols:
            try:
                close = df_pl['close'].to_numpy().astype(float)
                bps = df_pl['bps'].to_numpy().astype(float)
                with np.errstate(divide='ignore', invalid='ignore'):
                    pbr = np.where((bps != 0) & np.isfinite(bps), close / bps, np.nan)
                pbr[~np.isfinite(pbr)] = np.nan
                df_pl = df_pl.with_columns(pl.Series("pbr", pbr))
                missing.discard('pbr')
                self._log("SUCCESS", f"[{symbol}] PBR 직접 계산 완료 (close ÷ BPS) ✓")
            except Exception as e:
                self._log("ERROR", f"[{symbol}] PBR 직접 계산 실패: {e}")

        return df_pl

    # ── 유틸리티 ────────────────────────────────────────────────────────

    @staticmethod
    def _is_all_null(df_pl: pl.DataFrame, col: str) -> bool:
        try:
            return col not in df_pl.columns or df_pl[col].is_null().all()
        except Exception:
            return True

    @staticmethod
    def _fetch_shares_outstanding(symbol: str) -> Optional[int]:
        """상장주식수를 KRX 또는 Naver에서 조회."""
        # 1순위: Naver Finance 메인페이지에서 상장주식수 파싱
        try:
            import requests
            from bs4 import BeautifulSoup
            url = f"https://finance.naver.com/item/main.naver?code={symbol}"
            headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                # "상장주식수" 텍스트를 포함하는 td 옆의 값
                for td in soup.find_all("td"):
                    text = td.get_text(strip=True)
                    if "상장주식수" in text:
                        # 같은 행의 다음 td에서 숫자 추출
                        next_td = td.find_next_sibling("td")
                        if next_td:
                            num_text = next_td.get_text(strip=True).replace(",", "").replace("주", "")
                            return int(num_text)
                # 대안: "aside" 영역의 시가총액/주식수 정보
                # em.stock_market_total → 상장주식수
                for em in soup.find_all("em"):
                    eid = em.get("id", "")
                    if "stock_info" in eid or "listed" in eid:
                        num_text = em.get_text(strip=True).replace(",", "")
                        if num_text.isdigit():
                            return int(num_text)
        except Exception as e:
            logger.debug("[%s] Naver shares fetch failed: %s", symbol, e)

        # 2순위: pykrx
        try:
            from pykrx import stock as pykrx_stock
            today = pd.Timestamp.now().strftime("%Y%m%d")
            cap_df = pykrx_stock.get_market_cap_by_date(today, today, symbol)
            if cap_df is not None and not cap_df.empty:
                shares = int(cap_df.iloc[0].get("상장주식수", 0))
                if shares > 0:
                    return shares
        except Exception as e:
            logger.debug("[%s] pykrx shares fetch failed: %s", symbol, e)

        return None
