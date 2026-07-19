"""
Backfill delisted-ETF membership + OHLCV — removes ETF-universe survivorship bias.

Why: the ETF master (build_etf_master.py) draws from FDR 'ETF/KR', which lists
*currently listed* ETFs only. FDR KRX-DELISTING does not carry ETFs (its 수익증권
group is legacy listed funds), and data.krx.co.kr now requires a login, so the
delisted-ETF list must come from one of two authenticated KRX channels:

  A) KRX Open API (data-dbg.krx.co.kr, AUTH_KEY=.env KRX_API_KEY):
     증권상품 일별매매정보 `etp/etf_bydd_trd`를 거래일마다 훑어 그날 존재한 모든
     ETF(코드·이름·OHLCV)를 수집한다 — 상폐 목록과 가격을 한 번에 얻는다.
     ※ openapi.krx.co.kr에서 해당 API '이용신청(승인)'이 되어 있어야 한다(401=미승인).
  B) data.krx.co.kr 로그인 세션(KRX_ID/KRX_PW — pykrx 세션 재사용):
     'ETF 전종목 시세'(MDCSTAT04301)를 거래일마다 훑는다. 이 화면만이 진짜
     point-in-time이다 — pykrx get_etf_ticker_list(과거일)는 '현재 상장 종목 중'
     그날 존재한 것만 반환해 상폐분이 안 잡힌다(2020-02-28 실측: 시세 화면 451
     vs 멤버십 350 — 차이 101이 당시 거래되던 지금은-상폐 ETF).

Both paths are resumable (per-day/per-month cache under data/cache/krx-etf-daily/)
and idempotent. Outputs:
  - data/ohlcv/{symbol}.parquet  (delisted symbols only; existing files untouched)
  - data/etf-delisted.json       (symbol, name, delistingDate, dataStart, dataEnd)
Then re-run build_etf_master.py to fold the delisted entries into etf-master.json.

Run:
    cd backend && python scripts/backfill_delisted_etf.py [--start 2015-01-01]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_OHLCV_DIR = _PROJECT_ROOT / "data" / "ohlcv"
_CACHE_DIR = _PROJECT_ROOT / "data" / "cache" / "krx-etf-daily"
_OUT_DELISTED = _PROJECT_ROOT / "data" / "etf-delisted.json"
_ETF_MASTER = _PROJECT_ROOT / "data" / "etf-master.json"

_DEFAULT_START = "2015-01-01"   # 주식 유니버스 하한(_DEFAULT_START_FLOOR)과 정렬
_SLEEP_SECONDS = 0.35


def _load_env_key(name: str) -> str:
    val = os.getenv(name, "").strip()
    if val:
        return val
    env_path = _PROJECT_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _current_etf_symbols() -> set[str]:
    """현재 상장 ETF(정본=FDR ETF/KR). 네트워크 실패 시 로컬 etf-master로 폴백."""
    try:
        import FinanceDataReader as fdr
        listing = fdr.StockListing("ETF/KR")
        return {str(r.Symbol).zfill(6) for r in listing.itertuples()}
    except Exception as exc:
        print(f"[warn] FDR ETF/KR 조회 실패({exc}) — 로컬 etf-master로 폴백")
        data = json.loads(_ETF_MASTER.read_text(encoding="utf-8"))
        return {e["symbol"] for e in data.get("etfs", []) if not e.get("delistingDate")}


def _norm_symbol(raw: str) -> str:
    """KRX 코드 정규화 — 12자리 표준코드(KR7069500007)면 단축 6자리를 뽑는다."""
    raw = (raw or "").strip()
    if len(raw) == 12 and raw[:3].isalnum() and raw[3:9].isdigit():
        return raw[3:9]
    return raw.zfill(6) if raw.isdigit() and len(raw) < 6 else raw


def _num(val) -> float | None:
    try:
        return float(str(val).replace(",", ""))
    except (TypeError, ValueError):
        return None


# ─── Source A: KRX Open API 일별 스윕 ─────────────────────────────────────────

def _krx_open_api_fetch(day: str, auth_key: str) -> list[dict]:
    import requests
    resp = requests.get(
        "http://data-dbg.krx.co.kr/svc/apis/etp/etf_bydd_trd",
        params={"basDd": day}, headers={"AUTH_KEY": auth_key}, timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("OutBlock_1", [])


def probe_krx_open_api(auth_key: str) -> bool:
    if not auth_key:
        return False
    try:
        probe_day = (date.today() - timedelta(days=4)).strftime("%Y%m%d")
        _krx_open_api_fetch(probe_day, auth_key)
        return True
    except Exception:
        return False


def _slim_rows(rows: list[dict]) -> list[dict]:
    return [
        {
            "s": _norm_symbol(r.get("ISU_SRT_CD") or r.get("ISU_CD") or ""),
            "n": (r.get("ISU_NM") or r.get("ISU_ABBRV") or "").strip(),
            "o": _num(r.get("TDD_OPNPRC")), "h": _num(r.get("TDD_HGPRC")),
            "l": _num(r.get("TDD_LWPRC")), "c": _num(r.get("TDD_CLSPRC")),
            "v": _num(r.get("ACC_TRDVOL")),
        }
        for r in rows
    ]


def sweep_daily(start: date, end: date, fetch_fn, label: str) -> None:
    """거래일별 응답을 캐시(JSON)로 저장한다. 이미 있는 날짜는 건너뛴다(재개 가능).

    fetch_fn(yyyymmdd) -> 원시 row 목록. 일시 오류는 1회 재시도 후 중단한다
    (캐시 덕분에 재실행 시 이어서 진행).
    """
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    day = start
    fetched = 0
    while day <= end:
        if day.weekday() < 5:  # 주말 제외(공휴일은 빈 응답이 캐시됨)
            key = day.strftime("%Y%m%d")
            cache = _CACHE_DIR / f"{key}.json"
            if not cache.exists():
                try:
                    rows = fetch_fn(key)
                except Exception:
                    time.sleep(3)
                    rows = fetch_fn(key)  # 1회 재시도 — 또 실패하면 예외로 중단(재개 가능)
                cache.write_text(
                    json.dumps({"d": key, "rows": _slim_rows(rows)}, ensure_ascii=False)
                )
                fetched += 1
                if fetched % 100 == 0:
                    print(f"  … {key}까지 신규 {fetched}일 수집", flush=True)
                time.sleep(_SLEEP_SECONDS)
        day += timedelta(days=1)
    print(f"[{label}] 스윕 완료(신규 {fetched}일, 캐시 {len(list(_CACHE_DIR.glob('*.json')))}일)")


def build_from_cache(current: set[str]) -> dict[str, dict]:
    """캐시된 일별 스냅샷에서 '현재 목록에 없는' 심볼의 시계열·이름을 조립한다."""
    series: dict[str, list] = {}
    names: dict[str, str] = {}
    for f in sorted(_CACHE_DIR.glob("*.json")):
        payload = json.loads(f.read_text())
        d = payload["d"]
        dt = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        for r in payload["rows"]:
            sym = r["s"]
            if not sym or sym in current:
                continue
            if r.get("c") in (None, 0):
                continue
            names[sym] = r.get("n") or names.get(sym, "")
            series.setdefault(sym, []).append(
                (dt, r.get("o"), r.get("h"), r.get("l"), r["c"], r.get("v") or 0.0)
            )
    return {
        sym: {"name": names.get(sym, ""), "rows": rows}
        for sym, rows in series.items()
    }


# ─── Source B: data.krx.co.kr 로그인 세션(일별 전종목 시세) ─────────────────────

def make_krx_web_fetcher():
    """pykrx 로그인 세션으로 'ETF 전종목 시세'(MDCSTAT04301)를 일자별 조회한다.

    주의: pykrx get_etf_ticker_list(과거일)는 현재 상장 종목의 부분집합만 반환해
    상폐 ETF가 절대 잡히지 않는다 — 반드시 이 시세 화면을 써야 point-in-time이다.
    """
    from pykrx.website.krx.krxio import KrxWebIo

    class _EtfAllPrices(KrxWebIo):
        @property
        def bld(self):
            return "dbms/MDC/STAT/standard/MDCSTAT04301"

        def fetch(self, trdDd: str):
            return self.read(trdDd=trdDd, share="1", money="1")

    api = _EtfAllPrices()

    def fetch(day: str) -> list[dict]:
        return api.fetch(day).get("output") or []

    return fetch


# ─── 산출물 쓰기 ─────────────────────────────────────────────────────────────

def write_outputs(delisted: dict[str, dict]) -> None:
    written, skipped = 0, 0
    entries = []
    for sym, info in sorted(delisted.items()):
        rows = sorted(info["rows"])
        if len(rows) < 5:  # 하루짜리 노이즈(신규상장 직후 이관 등) 제외
            continue
        data_start, data_end = rows[0][0], rows[-1][0]
        entries.append({
            "symbol": sym, "name": info["name"],
            "dataStart": data_start, "dataEnd": data_end,
            "delistingDate": data_end, "hasOhlcv": True,
        })
        out_path = _OHLCV_DIR / f"{sym}.parquet"
        if out_path.exists():
            skipped += 1
            continue
        closes = [r[4] for r in rows]
        changes = [0.0] + [
            (closes[i] - closes[i - 1]) / closes[i - 1] if closes[i - 1] else 0.0
            for i in range(1, len(closes))
        ]
        pl.DataFrame({
            "date": [datetime.fromisoformat(r[0]) for r in rows],
            "open": [r[1] or r[4] for r in rows],
            "high": [r[2] or r[4] for r in rows],
            "low": [r[3] or r[4] for r in rows],
            "close": closes,
            "volume": [r[5] for r in rows],
            "change": changes,
        }).write_parquet(out_path)
        written += 1

    _OUT_DELISTED.write_text(
        json.dumps({
            "generatedAt": datetime.now().isoformat(),
            "counts": {"delisted": len(entries)},
            "etfs": entries,
        }, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"상폐 ETF {len(entries)}종목 — parquet 신규 {written}·기존유지 {skipped}"
          f" → {_OUT_DELISTED}")
    print("다음 단계: python scripts/build_etf_master.py 재실행으로 마스터에 병합")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=_DEFAULT_START)
    args = parser.parse_args()
    start = date.fromisoformat(args.start)
    end = date.today() - timedelta(days=1)

    current = _current_etf_symbols()
    print(f"현재 상장 ETF {len(current)}종목 기준, {start}~{end} 관측분과 대조")

    auth_key = _load_env_key("KRX_API_KEY")
    if probe_krx_open_api(auth_key):
        print("[source] KRX Open API (etp/etf_bydd_trd)")
        sweep_daily(start, end, lambda d: _krx_open_api_fetch(d, auth_key), "open-api")
        delisted = build_from_cache(current)
    elif _load_env_key("KRX_ID") and _load_env_key("KRX_PW"):
        print("[source] data.krx.co.kr 로그인 세션 — ETF 전종목 시세 일별 스윕")
        os.environ.setdefault("KRX_ID", _load_env_key("KRX_ID"))
        os.environ.setdefault("KRX_PW", _load_env_key("KRX_PW"))
        sweep_daily(start, end, make_krx_web_fetcher(), "krx-web")
        delisted = build_from_cache(current)
    else:
        print(
            "사용 가능한 KRX 데이터 접근 수단이 없습니다. 둘 중 하나가 필요합니다:\n"
            "  A) openapi.krx.co.kr 로그인 → 이용신청에서 '증권상품 일별매매정보(ETF)'\n"
            "     API 승인 (.env KRX_API_KEY 그대로 사용)\n"
            "  B) data.krx.co.kr(정보데이터시스템) 계정을 .env에 KRX_ID/KRX_PW로 추가\n"
            "승인/추가 후 이 스크립트를 다시 실행하세요."
        )
        sys.exit(2)

    write_outputs(delisted)


if __name__ == "__main__":
    main()
