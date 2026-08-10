"""전 종목 전 구간 market_cap을 KRX 실측 일별 시가총액으로 재구축한다 (엔진 v13.0).

Motivation: parquet의 market_cap은 '수정종가 × 현재 상장주식수' 근사여서(삼성전자
실측: 2000~2026 전 구간 내재 주식수 5.8463B 상수) 증자·소각·우선주 등 주식수가
변한 종목의 과거 시총이 어긋났고, PCR(=시총/영업CF)·시총 필터도 같은 오차를
공유했다. KRX 일별 전 시장 스냅샷(pykrx get_market_cap_by_ticker, 당시 실제
상장주식수 기준)으로 재구축한다 — 상폐 종목도 당시 스냅샷에 있으면 커버된다(PIT).

두 단계로 나뉘며 각각 재개 가능하다:

Phase 1 (harvest): 모든 parquet의 date 합집합(=거래일 달력)을 만들고, 날짜마다
  전 시장 스냅샷 1콜을 받아 data/fundamentals/market_cap_daily/{year}.parquet
  (date, symbol, cap_won)로 누적한다. 이미 저장된 날짜는 건너뛴다. 스냅샷이 빈
  날짜는 .empty_dates.json에 기록해 재조회하지 않는다.

Phase 2 (apply): 저장소를 종목별 시계열로 뒤집어 각 parquet에
  apply_real_market_cap(실측 우선, 미커버 날짜만 기존 근사 보존) + recompute_pcr
  적용 후 원자적(tmp→rename) 교체. 스냅샷에 전혀 없는 심볼(ETF 등)은 손대지
  않는다. 몇 번을 다시 돌려도 결과가 같다(멱등).

Usage:
  cd backend && python3 scripts/rebuild_market_cap.py                  # harvest + apply
  cd backend && python3 scripts/rebuild_market_cap.py --harvest-only
  cd backend && python3 scripts/rebuild_market_cap.py --apply-only
  cd backend && python3 scripts/rebuild_market_cap.py --symbols 005930,000660 --apply-only
  cd backend && python3 scripts/rebuild_market_cap.py --limit-dates 30 # 시험 수확

주의: KRX 로그인(.env의 KRX_ID/KRX_PW)이 필요하다. 21:00 KST 스케줄러 sync와 같은
parquet을 쓰므로 apply는 그 시간대를 피해서 돌린다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.fundamental_backfill import apply_real_market_cap  # noqa: E402
from engine.fundamental_fetcher import recompute_pcr  # noqa: E402

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_OHLCV_DIR = _PROJECT_ROOT / "data" / "ohlcv"
_STORE_DIR = _PROJECT_ROOT / "data" / "fundamentals" / "market_cap_daily"
_EMPTY_DATES_PATH = _STORE_DIR / ".empty_dates.json"

_FLUSH_EVERY = 50   # harvest 중 N개 날짜마다 저장소에 반영 (크래시 시 재작업 상한)
_SLEEP = 0.25       # KRX 스냅샷 호출 간격


def _load_calendar() -> list[pd.Timestamp]:
    """모든 parquet의 date 합집합 — 재구축이 커버해야 할 거래일 달력."""
    dates: set = set()
    files = sorted(_OHLCV_DIR.glob("*.parquet"))
    for f in files:
        try:
            col = pd.read_parquet(f, columns=["date"])["date"]
            dates.update(pd.to_datetime(col).dt.normalize())
        except Exception as e:
            print(f"[WARN] {f.name}: date 읽기 실패 — {e}")
    print(f"[INFO] 달력 구성 완료: parquet {len(files)}개, 거래일 {len(dates)}개")
    return sorted(dates)


def _stored_dates() -> set:
    stored: set = set()
    for f in _STORE_DIR.glob("*.parquet"):
        try:
            stored.update(pd.to_datetime(pd.read_parquet(f, columns=["date"])["date"]).unique())
        except Exception as e:
            print(f"[WARN] 저장소 {f.name} 읽기 실패 — {e}")
    return stored


def _load_empty_dates() -> set:
    if _EMPTY_DATES_PATH.exists():
        return {pd.Timestamp(d) for d in json.loads(_EMPTY_DATES_PATH.read_text())}
    return set()


def _save_empty_dates(empty: set) -> None:
    _EMPTY_DATES_PATH.write_text(json.dumps(sorted(d.strftime("%Y-%m-%d") for d in empty)))


def _flush_rows(rows: list[dict]) -> None:
    """수확한 (date, symbol, cap_won) 행들을 연도별 저장소 parquet에 원자적으로 병합."""
    if not rows:
        return
    new = pd.DataFrame(rows)
    for year, chunk in new.groupby(new["date"].dt.year):
        path = _STORE_DIR / f"{year}.parquet"
        if path.exists():
            old = pd.read_parquet(path)
            chunk = pd.concat([old, chunk], ignore_index=True)
            chunk = chunk.drop_duplicates(subset=["date", "symbol"], keep="last")
        tmp = path.with_suffix(".tmp")
        chunk.sort_values(["date", "symbol"]).to_parquet(tmp, index=False)
        os.replace(tmp, path)


def harvest(limit_dates: int | None, sleep_s: float) -> None:
    import pykrx.stock as pykrx  # .env 로드 후 임포트 (임포트 시점에 KRX 로그인)

    _STORE_DIR.mkdir(parents=True, exist_ok=True)
    calendar = _load_calendar()
    stored = _stored_dates()
    empty = _load_empty_dates()
    todo = [d for d in calendar if d not in stored and d not in empty]
    if limit_dates:
        todo = todo[:limit_dates]
    print(f"[INFO] harvest 대상: {len(todo)}개 날짜 (저장 {len(stored)}, 빈 날짜 {len(empty)})")

    buffer: list[dict] = []
    t0 = time.time()
    for i, d in enumerate(todo, 1):
        try:
            snap = pykrx.get_market_cap_by_ticker(d.strftime("%Y%m%d"), market="ALL")
        except Exception as e:
            print(f"[WARN] {d.date()} 스냅샷 실패 — {e} (다음 실행에서 재시도)")
            time.sleep(sleep_s)
            continue
        if snap is None or snap.empty or "시가총액" not in snap.columns:
            empty.add(d)
        else:
            caps = snap["시가총액"]
            caps = caps[caps > 0]
            buffer.extend(
                {"date": d, "symbol": str(sym), "cap_won": int(won)}
                for sym, won in caps.items()
            )
        if i % _FLUSH_EVERY == 0:
            _flush_rows(buffer)
            buffer = []
            _save_empty_dates(empty)
            rate = i / (time.time() - t0)
            eta_min = (len(todo) - i) / rate / 60 if rate > 0 else 0
            print(f"[INFO] {i}/{len(todo)} ({d.date()}) — {rate:.1f} d/s, ETA {eta_min:.0f}분")
        time.sleep(sleep_s)
    _flush_rows(buffer)
    _save_empty_dates(empty)
    print(f"[INFO] harvest 완료: {len(todo)}개 날짜 처리, 빈 날짜 {len(empty)}개")


def _load_store_by_symbol() -> dict[str, pd.Series]:
    """저장소 전체를 {symbol: Series(억원, 날짜 인덱스)}로 뒤집는다."""
    frames = [pd.read_parquet(f) for f in sorted(_STORE_DIR.glob("*.parquet"))]
    if not frames:
        return {}
    store = pd.concat(frames, ignore_index=True)
    store["date"] = pd.to_datetime(store["date"]).dt.normalize()
    out: dict[str, pd.Series] = {}
    for sym, g in store.groupby("symbol"):
        out[str(sym)] = pd.Series(g["cap_won"].values / 1e8, index=g["date"].values)
    print(f"[INFO] 저장소 로드: {len(store)}행, {len(out)}종목, "
          f"{store['date'].min().date()}~{store['date'].max().date()}")
    return out


def apply(symbols: list[str] | None) -> None:
    by_symbol = _load_store_by_symbol()
    if not by_symbol:
        print("[ERROR] 저장소가 비어 있다 — harvest를 먼저 실행할 것")
        sys.exit(1)

    files = sorted(_OHLCV_DIR.glob("*.parquet"))
    if symbols:
        wanted = set(symbols)
        files = [f for f in files if f.stem in wanted]

    applied, no_data, unchanged_err = 0, 0, 0
    coverage_sum, coverage_n = 0.0, 0
    for f in files:
        sym = f.stem
        caps = by_symbol.get(sym)
        if caps is None:
            no_data += 1  # 스냅샷에 전혀 없는 심볼(ETF 등) — 기존 근사 유지
            continue
        try:
            pdf = pd.read_parquet(f)
            out = apply_real_market_cap(pdf, caps)
            out = recompute_pcr(out)
            covered = pd.to_datetime(out["date"]).dt.normalize().isin(caps.index).mean()
            coverage_sum += covered
            coverage_n += 1
            tmp = f.with_suffix(".tmp")
            out.to_parquet(tmp)
            os.replace(tmp, f)
            applied += 1
        except Exception as e:
            unchanged_err += 1
            print(f"[WARN] {sym}: 적용 실패 — {e}")
        if applied % 500 == 0 and applied:
            print(f"[INFO] apply 진행: {applied}/{len(files)}")

    avg_cov = coverage_sum / coverage_n * 100 if coverage_n else 0.0
    print(f"[INFO] apply 완료: 적용 {applied}, 스냅샷 미커버(유지) {no_data}, "
          f"실패 {unchanged_err}, 평균 날짜 커버리지 {avg_cov:.1f}%")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--harvest-only", action="store_true")
    parser.add_argument("--apply-only", action="store_true")
    parser.add_argument("--symbols", help="apply 대상 심볼 제한 (쉼표 구분)")
    parser.add_argument("--limit-dates", type=int, help="harvest 날짜 수 제한 (시험용)")
    parser.add_argument("--sleep", type=float, default=_SLEEP)
    args = parser.parse_args()

    load_dotenv(_PROJECT_ROOT / ".env")

    if not args.apply_only:
        harvest(args.limit_dates, args.sleep)
    if not args.harvest_only:
        apply(args.symbols.split(",") if args.symbols else None)


if __name__ == "__main__":
    main()
