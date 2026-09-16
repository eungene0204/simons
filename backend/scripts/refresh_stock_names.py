"""data/korea-stocks.json 종목명 제자리 갱신 — 사명 변경을 매일 반영한다(멱등).

**왜 필요한가**: 유니버스 목록·종목 인식이 읽는 이름의 정본은 `korea-stocks.json`인데, 이
파일은 전체 동기화(`POST /sync-stocks`)로만 갱신됐고 그 동기화는 파일을 통째로 다시 써서
손으로 고친 섹터 분류와 영문명(name_en)을 날린다. 그래서 아무도 돌리지 않았고, 사명이
바뀐 종목이 옛 이름으로 표시됐다(2026-09-16 실측: 세기상사→우양피앤엘 등 25종목).

그래서 이 스크립트는 **이름만** 바꾼다:
  ① 공식 회사명과 종목코드별 대조 — 출처는 DART 기업 고유번호 목록(`stock_analysis/dart_corp_names.py`).
     기준은 KRX KIND 상장법인목록의 '회사명'이지만 프로덕션 박스 IP가 KIND에서 403으로 차단돼,
     KIND와 전 종목 일치(차이 0, 2026-09-16 실측)하는 DART corp_name을 쓴다. DART 목록엔 상장폐지
     법인도 들어 있어 긴 정식 법인명('신영스팩10호'→'신영해피투모로우제10호기업인수목적')을 주므로,
     대상은 종목 마스터(`data/stock-master.json`, 일일 갱신)의 **현재 상장 종목**으로 한정한다
  ② 다르면 name만 교체 — sector·industry·market·name_en은 건드리지 않는다
  ③ 사명이 바뀐 경우 옛 이름을 `data/stock-name-history.json`에 사건으로 남기고 구 사명
     별칭표(formerNames)를 다시 계산한다 — 사용자가 옛 이름으로 불러도 계속 인식된다
신규 상장·상장폐지 행의 추가/삭제는 하지 않는다(섹터 분류가 없는 행이 생기기 때문).

Run:
    cd backend && python scripts/refresh_stock_names.py
    cd backend && python scripts/refresh_stock_names.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_stock_master import _OUT_PATH as _MASTER_PATH  # noqa: E402
from scripts.build_stock_name_history import (  # noqa: E402
    _OUT_PATH as _HISTORY_PATH,
    _STOCKS_JSON,
    _normalize,
    build_former_names,
)

_KST = timezone(timedelta(hours=9))

# 출처 응답 이상(반쪽 목록·인코딩 깨짐)으로 명부를 망가뜨리지 않기 위한 가드.
# 조회 행 수가 명부의 이 비율보다 적거나, 이름이 바뀐 종목이 이 비율을 넘으면 쓰지 않는다
# (평소 하루 사명 변경은 0~수 건, 최초 적용분이 명부의 약 1%였다).
_MIN_LISTING_RATIO = 0.8
_MAX_RENAME_RATIO = 0.05


class SuspiciousListingError(RuntimeError):
    """공식 회사명 조회 결과를 믿을 수 없어 갱신을 중단한다."""


def apply_official_names(stocks: list[dict], official: dict[str, str], listed: set[str],
                         observed_on: str) -> tuple[list[dict], list[dict]]:
    """명부 행의 name을 공식 회사명으로 맞춘 새 목록과 사명 변경 사건 목록을 반환한다.

    현재 상장 종목(`listed`)만 대상이다 — 상장폐지 법인의 등기 법인명은 사명 변경이 아니다.
    공백·대소문자만 다른 경우는 이름은 맞추되 사명 변경 사건으로 세지 않는다.
    """
    official = {symbol: name for symbol, name in official.items() if symbol in listed}
    if len(official) < len(stocks) * _MIN_LISTING_RATIO:
        raise SuspiciousListingError(
            f"공식 회사명 조회 {len(official)}종목 < 명부 {len(stocks)}종목의 {_MIN_LISTING_RATIO:.0%}"
        )
    out: list[dict] = []
    events: list[dict] = []
    for row in stocks:
        name = official.get(row["symbol"])
        if not name or name == row["name"]:
            out.append(row)
            continue
        out.append({**row, "name": name})
        if _normalize(name) != _normalize(row["name"]):
            events.append({
                "symbol": row["symbol"],
                "from": row["name"],
                "to": name,
                "observedOn": observed_on,
                "source": "DART",
            })
    if len(events) > len(stocks) * _MAX_RENAME_RATIO:
        raise SuspiciousListingError(
            f"사명 변경 {len(events)}건 > 명부의 {_MAX_RENAME_RATIO:.0%} — 응답 이상 의심"
        )
    return out, events


def merge_history(history: dict, events: list[dict], updated_at: str) -> dict:
    """사명 변경 사건을 이력에 더하고 구 사명 별칭표를 다시 계산한 새 payload를 반환한다.

    구 사명 가드(모호·현재 등록명 충돌·짧은 이름)는 빌드 스크립트와 같은 함수를 쓴다 —
    이 함수는 `korea-stocks.json`의 현재 이름을 읽으므로 명부를 먼저 쓴 뒤 호출한다.
    """
    seen = {(e["symbol"], _normalize(e["from"]), _normalize(e["to"]))
            for e in history.get("renames", [])}
    renames = list(history.get("renames", []))
    for event in events:
        key = (event["symbol"], _normalize(event["from"]), _normalize(event["to"]))
        if key not in seen:
            seen.add(key)
            renames.append(event)
    former_names, rejected = build_former_names(renames)
    return {
        **history,
        "updatedAt": updated_at,
        "counts": {
            "renames": len(renames),
            "formerNames": len(former_names),
            "rejected": len(rejected),
        },
        "formerNames": dict(sorted(former_names.items())),
        "renames": renames,
        "rejected": rejected,
    }


def _listed_symbols() -> set[str]:
    master = json.loads(_MASTER_PATH.read_text(encoding="utf-8"))
    return {s["symbol"] for s in master.get("stocks", []) if not s.get("delistingDate")}


def _write_json(path: Path, payload, indent: int) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=indent), encoding="utf-8")
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="korea-stocks.json 종목명(공식 회사명) 갱신")
    parser.add_argument("--dry-run", action="store_true", help="파일에 쓰지 않고 변화만 출력")
    args = parser.parse_args(argv)

    from stock_analysis.dart_corp_names import dart_api_key, fetch_dart_corp_names

    key = dart_api_key()
    if not key:
        print("[stock-names] DART_API_KEY가 없습니다 (.env 또는 환경변수)")
        return 2
    stocks = json.loads(_STOCKS_JSON.read_text(encoding="utf-8"))
    official = fetch_dart_corp_names(key)
    now = datetime.now(_KST)
    try:
        updated, events = apply_official_names(
            stocks, official, _listed_symbols(), now.date().isoformat())
    except SuspiciousListingError as exc:
        print(f"[stock-names] 중단: {exc}")
        return 1

    changed = sum(1 for a, b in zip(stocks, updated) if a["name"] != b["name"])
    print(f"[stock-names] 이름 교체 {changed}종목 · 사명 변경 {len(events)}건")
    for event in events:
        print(f"[stock-names]   {event['symbol']} {event['from']} → {event['to']}")
    if args.dry_run or changed == 0:
        if args.dry_run:
            print("[stock-names] --dry-run: 파일을 쓰지 않았습니다")
        return 0

    _write_json(_STOCKS_JSON, updated, indent=2)
    if events:
        history = json.loads(_HISTORY_PATH.read_text(encoding="utf-8"))
        _write_json(_HISTORY_PATH, merge_history(history, events, now.isoformat()), indent=1)
    print(f"[stock-names] wrote {_STOCKS_JSON}" + (f", {_HISTORY_PATH}" if events else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
