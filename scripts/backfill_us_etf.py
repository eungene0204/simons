"""backfill_us_etf.py — 미국 ETF OHLCV+배당 파케이 백필 (무료 소스: yfinance).

미국 개별주 파이프라인(backfill_us_stocks.py)의 프레임 빌드·증분 로직을 그대로 재사용한다.
ETF는 기업 재무제표가 없으므로 재무 컬럼은 전부 NaN이다 — ETF 유니버스에 기업 재무
지표를 노출하지 않는 계약(engine/universe_capabilities.py)과 데이터 단계에서 같은 의미.

- 파케이: data/ohlcv-us/{SYM}.parquet — 개별주와 **같은 디렉터리·같은 59컬럼 스키마**.
  실시간 레인(engine/providers/toss_us.py의 전일종가 조회)과 향후 백테스트 US 레인이
  경로 하나로 읽는다. 개별주 증분(backfill_us_stocks.py --update)은 us-stocks.json
  마스터 종목만 돌므로 ETF 파일과 충돌하지 않는다.
- 마스터: data/us-etf-master.json — 한국 ETF 마스터(data/etf-master.json)와 같은 골격
  {generatedAt, counts, etfs:[...]}에 name_kr·category를 더한다. 카탈로그는 이 파일이
  아니라 아래 CATALOG 상수가 정본이다(마스터는 수집 결과 기록).
- 채우는 컬럼: OHLCV·change·dividends(배당락일 주당 배당)·dividend_yield/growth·
  market_cap(주식수 실측이 있는 경우). 배당 규약은 개별주와 동일 — engine/dividends.py가
  롤링 합으로 TTM을 만들어 총수익 역조정에 쓴다.

사용:
  python scripts/backfill_us_etf.py                    # 카탈로그 전체 (기존 파일 스킵)
  python scripts/backfill_us_etf.py --symbols SPY,QQQ --force
  python scripts/backfill_us_etf.py --update           # 일일 증분 (scheduler_us.py가 실행)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

# 개별주 파이프라인 재사용 (scripts/는 패키지가 아니므로 파일 경로로 로드)
_spec = importlib.util.spec_from_file_location(
    "simons_backfill_us_stocks", ROOT / "scripts" / "backfill_us_stocks.py")
stocks = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(stocks)

OUT_DIR = ROOT / "data" / "ohlcv-us"
MASTER_PATH = ROOT / "data" / "us-etf-master.json"

# 수집 대상 카탈로그(정본). category: 지수 | 섹터 | 산업 | 테마 | 배당 | 자산
CATALOG: list[dict] = [
    # 지수
    {"symbol": "SPY", "name": "SPDR S&P 500 ETF Trust", "name_kr": "S&P500", "category": "지수"},
    {"symbol": "QQQ", "name": "Invesco QQQ Trust", "name_kr": "나스닥100", "category": "지수"},
    {"symbol": "DIA", "name": "SPDR Dow Jones Industrial Average ETF Trust", "name_kr": "다우존스30", "category": "지수"},
    {"symbol": "IWM", "name": "iShares Russell 2000 ETF", "name_kr": "러셀2000 중소형주", "category": "지수"},
    {"symbol": "VTI", "name": "Vanguard Total Stock Market ETF", "name_kr": "미국 전체 시장", "category": "지수"},
    # 섹터 (SPDR 11종)
    {"symbol": "XLK", "name": "Technology Select Sector SPDR Fund", "name_kr": "기술 섹터", "category": "섹터"},
    {"symbol": "XLV", "name": "Health Care Select Sector SPDR Fund", "name_kr": "헬스케어 섹터", "category": "섹터"},
    {"symbol": "XLF", "name": "Financial Select Sector SPDR Fund", "name_kr": "금융 섹터", "category": "섹터"},
    {"symbol": "XLE", "name": "Energy Select Sector SPDR Fund", "name_kr": "에너지 섹터", "category": "섹터"},
    {"symbol": "XLI", "name": "Industrial Select Sector SPDR Fund", "name_kr": "산업재 섹터", "category": "섹터"},
    {"symbol": "XLU", "name": "Utilities Select Sector SPDR Fund", "name_kr": "유틸리티 섹터", "category": "섹터"},
    {"symbol": "XLY", "name": "Consumer Discretionary Select Sector SPDR Fund", "name_kr": "경기소비재 섹터", "category": "섹터"},
    {"symbol": "XLP", "name": "Consumer Staples Select Sector SPDR Fund", "name_kr": "필수소비재 섹터", "category": "섹터"},
    {"symbol": "XLB", "name": "Materials Select Sector SPDR Fund", "name_kr": "소재 섹터", "category": "섹터"},
    {"symbol": "XLRE", "name": "Real Estate Select Sector SPDR Fund", "name_kr": "부동산 섹터", "category": "섹터"},
    {"symbol": "XLC", "name": "Communication Services Select Sector SPDR Fund", "name_kr": "커뮤니케이션 섹터", "category": "섹터"},
    # 산업
    {"symbol": "SMH", "name": "VanEck Semiconductor ETF", "name_kr": "반도체", "category": "산업"},
    {"symbol": "SOXX", "name": "iShares Semiconductor ETF", "name_kr": "반도체", "category": "산업"},
    {"symbol": "IBB", "name": "iShares Biotechnology ETF", "name_kr": "바이오테크", "category": "산업"},
    {"symbol": "ITA", "name": "iShares U.S. Aerospace & Defense ETF", "name_kr": "방산·항공우주", "category": "산업"},
    # 테마
    {"symbol": "URA", "name": "Global X Uranium ETF", "name_kr": "우라늄·원자력", "category": "테마"},
    {"symbol": "HACK", "name": "Amplify Cybersecurity ETF", "name_kr": "사이버보안", "category": "테마"},
    {"symbol": "BOTZ", "name": "Global X Robotics & Artificial Intelligence ETF", "name_kr": "로봇·인공지능", "category": "테마"},
    {"symbol": "ICLN", "name": "iShares Global Clean Energy ETF", "name_kr": "클린에너지", "category": "테마"},
    {"symbol": "ARKK", "name": "ARK Innovation ETF", "name_kr": "혁신 성장주", "category": "테마"},
    # 배당
    {"symbol": "SCHD", "name": "Schwab U.S. Dividend Equity ETF", "name_kr": "미국 배당주", "category": "배당"},
    {"symbol": "VYM", "name": "Vanguard High Dividend Yield ETF", "name_kr": "미국 고배당주", "category": "배당"},
    # 자산
    {"symbol": "GLD", "name": "SPDR Gold Shares", "name_kr": "금", "category": "자산"},
    {"symbol": "SLV", "name": "iShares Silver Trust", "name_kr": "은", "category": "자산"},
    {"symbol": "TLT", "name": "iShares 20+ Year Treasury Bond ETF", "name_kr": "미국 장기국채(20년+)", "category": "자산"},
    {"symbol": "IEF", "name": "iShares 7-10 Year Treasury Bond ETF", "name_kr": "미국 중기국채(7-10년)", "category": "자산"},
]


def fetch_etf(symbol: str):
    """한 ETF의 (hist, shares_actual)을 가져온다.

    개별주의 fetch_symbol과 달리 재무제표·EDGAR를 아예 조회하지 않는다 — ETF에는
    기업 재무가 없고, 조회 시도는 시간과 오류 로그만 만든다.
    """
    import yfinance as yf

    t = yf.Ticker(symbol)
    hist = t.history(period="max", auto_adjust=False)
    if hist is None or hist.empty:
        raise RuntimeError("empty history")
    try:
        shares = t.get_shares_full(start="1990-01-01")
        if shares is not None and not shares.empty:
            idx = shares.index
            shares = pd.Series(
                shares.astype(float).to_numpy(),
                index=pd.DatetimeIndex(idx.tz_localize(None) if idx.tz else idx).normalize(),
            )
        else:
            shares = None
    except Exception:
        shares = None
    return hist, shares


def build_etf_frame(hist: pd.DataFrame, shares: pd.Series | None) -> pd.DataFrame:
    """ETF 일별 프레임 — 개별주 build_daily_frame에 빈 재무를 넣어 재무 컬럼을 NaN으로 둔다."""
    return stocks.build_daily_frame(hist, pd.DataFrame(), shares, sector="", adf=None)


def refresh_master(catalog: list[dict], data_dir: Path = OUT_DIR) -> dict:
    """카탈로그 + 파케이 실측(dataStart/dataEnd/hasOhlcv)으로 마스터 dict를 만든다."""
    etfs = []
    with_ohlcv = 0
    for item in catalog:
        entry = dict(item)
        entry["delistingDate"] = None
        path = data_dir / f"{item['symbol']}.parquet"
        if path.exists():
            dates = pd.read_parquet(path, columns=["date"])["date"]
            entry["hasOhlcv"] = True
            entry["dataStart"] = str(pd.Timestamp(dates.iloc[0]).date())
            entry["dataEnd"] = str(pd.Timestamp(dates.iloc[-1]).date())
            with_ohlcv += 1
        else:
            entry["hasOhlcv"] = False
            entry["dataStart"] = entry["dataEnd"] = None
        etfs.append(entry)
    return {
        "generatedAt": datetime.now(timezone.utc).astimezone().isoformat(),
        "counts": {"total": len(etfs), "hasOhlcv": with_ohlcv},
        "etfs": etfs,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--symbols", help="쉼표 구분 티커 (기본: 카탈로그 전체)")
    ap.add_argument("--limit", type=int, help="앞에서 N종목만")
    ap.add_argument("--force", action="store_true", help="기존 파케이 덮어쓰기")
    ap.add_argument("--update", action="store_true",
                    help="일일 증분: 기존 파케이에 최근 시세만 이어 붙인다")
    ap.add_argument("--sleep", type=float, default=0.6, help="종목 간 대기(초)")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    by_symbol = {c["symbol"]: c for c in CATALOG}

    symbols = [s.strip().upper() for s in args.symbols.split(",")] \
        if args.symbols else [c["symbol"] for c in CATALOG]
    unknown = [s for s in symbols if s not in by_symbol]
    if unknown:
        print(f"카탈로그에 없는 티커: {', '.join(unknown)} — CATALOG에 먼저 등록하세요")
        return 1
    if args.limit:
        symbols = symbols[: args.limit]

    if args.update:
        # 분할·소급 수정 감지 시 update_existing이 _full_refresh(fetch_symbol)로
        # 전량 재수집한다 — ETF는 재무 조회가 빈 프레임으로 떨어져 결과가 같다.
        rc = stocks.update_existing(symbols, by_symbol, args.sleep)
        MASTER_PATH.write_text(json.dumps(refresh_master(CATALOG), ensure_ascii=False, indent=1))
        return rc

    ok = skip = fail = 0
    failed: list[str] = []
    for i, sym in enumerate(symbols, 1):
        out_path = OUT_DIR / f"{sym}.parquet"
        if out_path.exists() and not args.force:
            skip += 1
            continue
        for attempt in range(3):
            try:
                hist, shares = fetch_etf(sym)
                df = build_etf_frame(hist, shares)
                df.to_parquet(out_path, index=False)
                ok += 1
                print(f"[{i}/{len(symbols)}] {sym}: {len(df)}행 "
                      f"({df['date'].iloc[0].date()}~{df['date'].iloc[-1].date()})")
                break
            except Exception as exc:
                wait = 30 * (attempt + 1)
                print(f"[{i}/{len(symbols)}] {sym}: 실패({exc}) — {wait}초 후 재시도 {attempt + 1}/3")
                time.sleep(wait)
        else:
            fail += 1
            failed.append(sym)
        time.sleep(args.sleep)

    MASTER_PATH.write_text(json.dumps(refresh_master(CATALOG), ensure_ascii=False, indent=1))
    print(f"\n완료: 성공 {ok} · 스킵 {skip} · 실패 {fail}")
    if failed:
        print("실패 종목:", ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
