"""국내 상장 종목의 **사명 변경 이력**을 KRX 월별 스냅샷 대조로 수집한다.

왜 필요한가: `data/korea-stocks.json`은 **현재 등록명만** 담는다. 사용자는 바뀌기 전
이름으로 부르는 일이 흔한데("제이콘텐트리" = 현 콘텐트리중앙), 명부에 없으면 무매칭이고
수정 레인의 환각 게이트는 그것을 '모델이 지어낸 이름'으로 판정해 요청을 통째로 버린다
(2026-08-29 사고). 구 사명을 정본 데이터로 확보해 registry가 해석하게 한다.

수집 방식 — **이력 API가 아니라 스냅샷 대조**다:
  KRX 정보데이터시스템의 '전종목 시세'(MDCSTAT01501)는 조회일 기준 종목명(ISU_ABBRV)을
  준다. 월별로 훑어 같은 단축코드의 이름이 바뀐 지점을 찾으면 그것이 사명 변경이다.
  '변경상장' 통계를 직접 읽지 않는 이유는 그 화면이 사명 변경 외의 변경(액면분할·
  주식병합 등)과 섞여 있고 조회 단위가 달라, 코드 고정 + 이름 변화라는 **관측 사실**이
  더 단순하고 검증 가능하기 때문이다(KISS).

접근 수단: data.krx.co.kr 로그인 세션(.env `KRX_ID`/`KRX_PW`, pykrx 세션 재사용).
KRX Open API(`KRX_API_KEY`)는 주식 서비스 승인이 없으면 401이라 쓸 수 없다.

사용법:
    python scripts/build_stock_name_history.py                 # 2000-01 ~ 현재
    python scripts/build_stock_name_history.py --start 2010-01
    python scripts/build_stock_name_history.py --rebuild-only  # 캐시만으로 재집계(무통신)

산출물: `data/stock-name-history.json`
    · renames     — 관측된 이름 변경 전부(코드·이전 이름·이후 이름·관측 구간)
    · formerNames — 구 사명 → 종목코드. **모호하지 않은 것만** 남긴다(아래 가드).
      registry(`stock_analysis/symbol_resolver.py`)가 이 표만 별칭으로 읽는다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CACHE_DIR = _PROJECT_ROOT / "data" / "cache" / "krx-name-snapshots"
_OUT_PATH = _PROJECT_ROOT / "data" / "stock-name-history.json"
_STOCKS_JSON = _PROJECT_ROOT / "data" / "korea-stocks.json"

_DEFAULT_START = "2000-01"
# 구 사명 최소 길이. 짧은 이름은 사용자 문장 안에서 다른 단어에 얹혀 오탐하기 쉬워
# 별칭으로 내보내지 않는다(_KOREAN_ALIASES가 '삼성'·'LG' 같은 접두어를 뺀 것과 같은 이유).
_MIN_ALIAS_LEN = 3


def _load_env_key(name: str) -> str:
    val = os.getenv(name, "").strip()
    if val:
        return val
    env_path = _PROJECT_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


# ─── 스냅샷 수집 ──────────────────────────────────────────────────────────────

def _months(start: str, end: date) -> List[str]:
    y, m = (int(x) for x in start.split("-"))
    out: List[str] = []
    while (y, m) <= (end.year, end.month):
        out.append(f"{y:04d}{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _last_days_of(month: str) -> List[str]:
    """해당 월의 마지막 날부터 거슬러 최대 7일치 후보(휴장일 회피)."""
    y, m = int(month[:4]), int(month[4:])
    first_next = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    last = first_next - timedelta(days=1)
    return [(last - timedelta(days=i)).strftime("%Y%m%d") for i in range(7)]


def _make_fetcher():
    from pykrx.website.krx.krxio import KrxWebIo

    class _AllPrices(KrxWebIo):
        @property
        def bld(self) -> str:
            return "dbms/MDC/STAT/standard/MDCSTAT01501"

        def fetch(self, trdDd: str):
            return self.read(mktId="ALL", trdDd=trdDd, share="1", money="1")

    api = _AllPrices()

    def fetch(day: str) -> List[dict]:
        return api.fetch(day).get("OutBlock_1") or []

    return fetch


def collect(months: List[str], fetch) -> None:
    """월별 스냅샷을 캐시에 채운다(이미 있으면 통신하지 않는다)."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for i, month in enumerate(months, 1):
        path = _CACHE_DIR / f"{month}.json"
        if path.exists():
            continue
        rows: List[dict] = []
        used = ""
        for day in _last_days_of(month):
            try:
                rows = fetch(day)
            except Exception as exc:  # noqa: BLE001 — 한 달 실패가 전체를 막지 않는다
                print(f"  {month} {day} 조회 실패: {exc}")
                time.sleep(2.0)
                continue
            if rows:
                used = day
                break
            time.sleep(0.3)
        if not rows:
            print(f"  {month} 스냅샷 없음 — 건너뜀")
            continue
        names = {
            str(r["ISU_SRT_CD"]).strip(): str(r.get("ISU_ABBRV") or "").strip()
            for r in rows
            if r.get("ISU_SRT_CD") and str(r.get("ISU_ABBRV") or "").strip()
        }
        path.write_text(
            json.dumps({"tradeDate": used, "names": names}, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"[{i}/{len(months)}] {month} ({used}) — {len(names)}종목")
        time.sleep(0.4)


# ─── 이력 집계 ────────────────────────────────────────────────────────────────

def _normalize(name: str) -> str:
    """표기 흔들림(공백·대소문자)만 흡수한다 — 이름 자체는 바꾸지 않는다."""
    return "".join(name.split()).lower()


def build_renames() -> List[dict]:
    """캐시된 스냅샷을 시간순으로 훑어 같은 코드의 이름 변화를 이벤트로 만든다."""
    files = sorted(_CACHE_DIR.glob("*.json"))
    last_name: Dict[str, str] = {}
    last_month: Dict[str, str] = {}
    renames: List[dict] = []
    for path in files:
        month = path.stem
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        for symbol, name in snapshot["names"].items():
            prev = last_name.get(symbol)
            if prev is not None and _normalize(prev) != _normalize(name):
                renames.append({
                    "symbol": symbol,
                    "from": prev,
                    "to": name,
                    "lastSeenFrom": last_month[symbol],
                    "firstSeenTo": month,
                })
            last_name[symbol] = name
            last_month[symbol] = month
    return renames


def kept_daily_events() -> List[dict]:
    """기존 산출물에 쌓인 일일 사명 변경 사건(`scripts/refresh_stock_names.py`, observedOn 보유).

    재집계는 월별 스냅샷 캐시만으로 renames를 다시 만들기 때문에, 그대로 두면 매일 반영한
    사건이 지워진다. 스냅샷 사건과 겹치지 않게 뒤에 붙인다.
    """
    if not _OUT_PATH.exists():
        return []
    data = json.loads(_OUT_PATH.read_text(encoding="utf-8"))
    return [e for e in data.get("renames", []) if e.get("observedOn")]


def build_former_names(renames: List[dict]) -> tuple[Dict[str, str], List[dict]]:
    """구 사명 → 종목코드 표와, 모호해서 제외한 항목 목록을 만든다.

    제외 가드(전부 '조용한 오해석'을 막기 위한 것 — 애매하면 무매칭이 안전):
      ① 현재 상장 종목이 아닌 코드(상폐) — 유니버스 해석 대상이 아니다.
      ② 지금 다른 회사가 쓰는 이름 — 현재 등록명이 언제나 이긴다.
      ③ 서로 다른 코드가 같은 이름을 쓴 적이 있으면 제외 — **상폐된 쪽까지 포함해서** 센다.
         상장 중인 한 곳만 남는다고 모호함이 사라지지는 않는다('제일모직'은 삼성SDI에
         합병된 001300과 삼성물산이 된 028260이 차례로 썼다 — 사용자가 어느 쪽을 뜻하는지
         알 수 없으므로 무매칭이 안전하다).
      ④ 그 종목의 현재 이름과 같은 경우 — 되돌아온 이름이라 별칭이 필요 없다.
      ⑤ 너무 짧은 이름(_MIN_ALIAS_LEN 미만) — 문장 안에서 오탐한다.
    """
    listed = json.loads(_STOCKS_JSON.read_text(encoding="utf-8"))
    current_by_symbol = {
        str(r["symbol"]).strip(): str(r["name"]).strip()
        for r in listed if r.get("symbol") and r.get("name")
    }
    current_names = {_normalize(n) for n in current_by_symbol.values()}

    # 모호성은 상폐 종목까지 포함해 센다(③) — 상장 여부는 별칭 등재 자격일 뿐,
    # 이름이 누구를 가리키는지의 판단 근거가 아니다.
    bearers: Dict[str, set] = {}
    for event in renames:
        for name in (event["from"], event["to"]):
            bearers.setdefault(_normalize(name), set()).add(event["symbol"])

    candidates: Dict[str, set] = {}
    original: Dict[str, str] = {}
    for event in renames:
        symbol, former = event["symbol"], event["from"]
        if symbol not in current_by_symbol:
            continue  # ①
        key = _normalize(former)
        candidates.setdefault(key, set()).add(symbol)
        original.setdefault(key, former)

    former_names: Dict[str, str] = {}
    rejected: List[dict] = []
    for key, symbols in sorted(candidates.items()):
        name = original[key]
        if len(name) < _MIN_ALIAS_LEN:
            rejected.append({"name": name, "reason": "too_short", "symbols": sorted(symbols)})
            continue
        if key in current_names:  # ②
            rejected.append({"name": name, "reason": "current_name_of_listed",
                             "symbols": sorted(symbols)})
            continue
        if len(bearers.get(key, symbols)) > 1:  # ③
            rejected.append({"name": name, "reason": "ambiguous_multiple_symbols",
                             "symbols": sorted(bearers.get(key, symbols))})
            continue
        symbol = next(iter(symbols))
        if _normalize(current_by_symbol[symbol]) == key:  # ④
            rejected.append({"name": name, "reason": "same_as_current", "symbols": [symbol]})
            continue
        former_names[name] = symbol
    return former_names, rejected


def write_output(renames: List[dict], former_names: Dict[str, str],
                 rejected: List[dict]) -> None:
    snapshots = sorted(p.stem for p in _CACHE_DIR.glob("*.json"))
    _OUT_PATH.write_text(
        json.dumps({
            "generatedAt": datetime.now().isoformat(),
            "source": "data.krx.co.kr MDCSTAT01501 월별 전종목 시세 스냅샷 대조",
            "snapshotRange": [snapshots[0], snapshots[-1]] if snapshots else [],
            "snapshotCount": len(snapshots),
            "counts": {
                "renames": len(renames),
                "formerNames": len(former_names),
                "rejected": len(rejected),
            },
            "formerNames": dict(sorted(former_names.items())),
            "renames": renames,
            "rejected": rejected,
        }, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"이름 변경 관측 {len(renames)}건 · 별칭 등재 {len(former_names)}개 "
          f"· 모호 제외 {len(rejected)}개 → {_OUT_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=_DEFAULT_START, help="YYYY-MM (기본 2000-01)")
    parser.add_argument("--rebuild-only", action="store_true",
                        help="통신 없이 캐시된 스냅샷만으로 재집계")
    args = parser.parse_args()

    if not args.rebuild_only:
        if not (_load_env_key("KRX_ID") and _load_env_key("KRX_PW")):
            print("data.krx.co.kr 계정이 필요합니다 — .env에 KRX_ID/KRX_PW를 설정하세요.")
            sys.exit(2)
        os.environ.setdefault("KRX_ID", _load_env_key("KRX_ID"))
        os.environ.setdefault("KRX_PW", _load_env_key("KRX_PW"))
        months = _months(args.start, date.today())
        print(f"{months[0]} ~ {months[-1]} 월별 스냅샷 {len(months)}개 수집")
        collect(months, _make_fetcher())

    renames = build_renames()
    seen = {(e["symbol"], _normalize(e["from"]), _normalize(e["to"])) for e in renames}
    renames += [e for e in kept_daily_events()
                if (e["symbol"], _normalize(e["from"]), _normalize(e["to"])) not in seen]
    former_names, rejected = build_former_names(renames)
    write_output(renames, former_names, rejected)


if __name__ == "__main__":
    main()
