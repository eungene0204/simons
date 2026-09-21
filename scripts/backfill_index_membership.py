"""지수 구성종목의 **시점별 명단**(KOSPI200·KOSDAQ150) 수집 — KRX 지수구성종목.

배경(2026-09-21, 사용자 결정): 새로 받은 명단이 정본이고, 과거를 백테스트하려면 그 시점의
명단이 있어야 한다. 그때까지는 현재 명단 하나(`data/kospi200-cache.json`, 7일 TTL)만 있었고
과거 구간은 '그 시점 시가총액 상위 N'으로 근사했다(engine/universe_pit.py).

KRX는 **2014-05-01 이후**(KOSDAQ150은 지수 출범일 2015-07-13 이후) 임의 날짜의 구성종목을 돌려준다(실측: 2016·2020·2024 모두 200종목,
호출당 0.2초. 그 이전은 "does NOT provide data prior to 2014/05/01"). 구성 변경은 드물어서
(정기 변경 연 2회 + 수시) 매 거래일을 받지 않는다 — **5거래일 간격으로 훑고, 앞뒤 명단이 다른
구간만 이분 탐색으로 변경일을 찾는다**. 저장은 첫 스냅샷 + 변경 이력(편입·편출)이라 어느
날짜의 명단이든 재구성된다(`engine.index_membership`).

재개 가능·자기 치유: `updated_through` 다음 거래일부터 오늘까지만 이어 받고, 100거래일마다
저장한다(KRX는 빠른 연속 조회를 막는다 — 호출 간격 0.7초, 막히면 받은 데까지 남기고 멈춘다). 배포의
`git reset --hard`가 박스의 파일을 되돌려도 다음 실행이 빈 구간을 KRX에서 다시 채운다.
빈 응답은 '전 종목 편출'이 아니라 조회 실패다 — 재시도 후에도 비면 기록하지 않고 멈춘다.

역할 분담(2026-09-21 사용자 결정): **과거분은 여기서(KRX) 한 번** 받고, 그 뒤는 야간 동기화가 매일
받는 KIS 현재 명단의 변화로 쌓는다(`engine.index_membership.record_observed_roster`). 이력이 일일
관측으로 먼저 시작됐으면 그 앞에 과거분을 붙이고, `--refine`은 관측이 며칠 멈췄던 구간의 변경일을
KRX로 바로잡는다. **정본은 프로덕션**이라 박스에서 돌린다(로컬은 `mirror_data.py --membership`).

Usage:
  python scripts/backfill_index_membership.py                 # 두 지수 모두, 이어 받기
  python scripts/backfill_index_membership.py --index kospi200
  python scripts/backfill_index_membership.py --report
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_REPO_ROOT / ".env")
sys.path.insert(0, str(_REPO_ROOT / "backend"))

from engine import index_membership as im  # noqa: E402

_KRX_TICKERS = {"kospi200": "1028", "kosdaq150": "2203"}
_CHECK_EVERY = 5          # 거래일 간격 — 이 안에서 편입 후 편출이 함께 일어나는 일은 없다고 본다
_SAVE_EVERY = 100         # 거래일 — 이 구간마다 저장한다(막혀도 받은 데까지는 남는다)
_RETRIES = 3
# KRX는 빠른 연속 조회를 막는다(2026-09-21 실측: 0.05초 간격 수백 회 뒤 빈 응답 → 로그인 거부).
_PAUSE_SECONDS = 0.7
_calls = 0


def trading_days(start: str) -> list[str]:
    """지수 시계열의 거래일(YYYY-MM-DD). 지수 파일이 거래일 달력의 정본이다."""
    frame = pd.read_parquet(_REPO_ROOT / "data" / "index" / "KOSPI.parquet", columns=["date"])
    days = pd.to_datetime(frame["date"]).dt.strftime("%Y-%m-%d")
    return sorted(day for day in days.unique() if day >= start)


def fetch_members(index_id: str, day: str) -> frozenset[str]:
    global _calls
    from pykrx import stock

    for attempt in range(_RETRIES):
        _calls += 1
        members = stock.get_index_portfolio_deposit_file(_KRX_TICKERS[index_id], day.replace("-", ""))
        if len(members):
            return frozenset(str(symbol) for symbol in members)
        time.sleep(20 * (attempt + 1))
    raise RuntimeError(f"{index_id} {day}: KRX가 빈 명단을 돌려줬다(재시도 {_RETRIES}회) — 기록하지 않는다")


def find_changes(index_id: str, days: list[str], known: frozenset[str]) -> list[dict]:
    """days[0]의 **직전** 명단이 known일 때, days 구간의 변경 이력(날짜 오름차순)."""
    cache: dict[int, frozenset[str]] = {}

    def snap(i: int) -> frozenset[str]:
        if i not in cache:
            cache[i] = fetch_members(index_id, days[i])
            time.sleep(_PAUSE_SECONDS)
        return cache[i]

    changes: list[dict] = []

    def walk(lo_members: frozenset[str], lo: int, hi: int) -> None:
        """lo 직전 명단이 lo_members일 때 (lo..hi] 안의 변경을 찾는다. lo는 첫 미확인 인덱스."""
        if snap(hi) == lo_members:
            return
        if lo == hi:
            changes.append({
                "date": days[hi],
                "added": sorted(snap(hi) - lo_members),
                "removed": sorted(lo_members - snap(hi)),
            })
            return
        mid = (lo + hi) // 2
        walk(lo_members, lo, mid)
        walk(snap(mid), mid + 1, hi)

    current = known
    for start in range(0, len(days), _CHECK_EVERY):
        end = min(start + _CHECK_EVERY, len(days)) - 1
        walk(current, start, end)
        current = snap(end)
    return changes


def _collect(tag: str, index_id: str, days: list[str], history: dict) -> dict:
    """history(tag 이름으로 저장)를 days 끝까지 KRX로 이어 받는다 — 100거래일마다 저장."""
    remaining = [day for day in days if day > history["updated_through"]]
    known = frozenset(im.members_on(tag, history["updated_through"], history=history))
    for start in range(0, len(remaining), _SAVE_EVERY):
        chunk = remaining[start:start + _SAVE_EVERY]
        history["changes"].extend(find_changes(index_id, chunk, known))
        history["updated_through"] = chunk[-1]
        im.save_history(tag, history)
        known = frozenset(im.members_on(tag, chunk[-1], history=history))
        print(f"  [{tag}] {chunk[-1]} 까지 저장 · 변경 {len(history['changes'])}건 · KRX {_calls}회",
              flush=True)
    return history


def _new_history(index_id: str, day: str) -> dict:
    return {
        "index": index_id,
        "source": "KRX 지수구성종목(pykrx get_index_portfolio_deposit_file)",
        "coverage_from": day, "updated_through": day,
        "initial": sorted(fetch_members(index_id, day)), "changes": [],
    }


def prepend_past(index_id: str, history: dict, days: list[str]) -> dict:
    """KIS 일일 관측으로 시작된 이력 앞에 KRX 과거분을 붙인다(재개 가능 — 임시 이력 `<id>.past`)."""
    tag = f"{index_id}.past"
    past_days = [day for day in days if day <= history["coverage_from"]]
    past = im.load_history(tag) or _new_history(index_id, past_days[0])
    past = _collect(tag, index_id, past_days, past)
    junction = im.members_on(tag, history["coverage_from"], history=past)
    if junction != sorted(history["initial"]):
        # 같은 날의 두 출처가 다르면 KRX를 따른다 — 뒤의 관측 변경은 증분이라 그대로 이어진다.
        print(f"  [{index_id}] {history['coverage_from']} 명단이 출처끼리 다르다 — KRX를 따른다: "
              f"KRX에만 {sorted(set(junction) - set(history['initial']))}, "
              f"관측에만 {sorted(set(history['initial']) - set(junction))}")
    stitched = {**past, "changes": past["changes"] + history["changes"],
                "updated_through": history["updated_through"]}
    im.save_history(index_id, stitched)
    im.history_path(tag).unlink(missing_ok=True)
    return stitched


def refine_observed_changes(index_id: str, history: dict, days: list[str]) -> dict:
    """일일 관측이 며칠 멈췄던 구간의 변경(`after`~`date`가 2거래일 이상)을 KRX로 정확한 날짜에 옮긴다."""
    refined: list[dict] = []
    for change in history["changes"]:
        span = [day for day in days if change.get("after", change["date"]) < day <= change["date"]]
        if change.get("observed_by") != "kis" or len(span) < 2:
            refined.append(change)
            continue
        known = frozenset(im.members_on(index_id, change["after"], history={**history, "changes": refined}))
        exact = find_changes(index_id, span, known)
        print(f"  [{index_id}] {change['after']}~{change['date']} 관측 변경 → {[c['date'] for c in exact]}")
        refined.extend(exact)
    history["changes"] = refined
    im.save_history(index_id, history)
    return history


def backfill(index_id: str, refine: bool = False) -> None:
    days = trading_days(im.COVERAGE_START[index_id])
    history = im.load_history(index_id)
    if history is None:
        history = _new_history(index_id, days[0])
    elif history["coverage_from"] > days[0]:
        print(f"[{index_id}] 과거분({days[0]} ~ {history['coverage_from']}) 수집")
        history = prepend_past(index_id, history, days)
    if refine:
        history = refine_observed_changes(index_id, history, days)
    if days[-1] > history["updated_through"]:
        print(f"[{index_id}] {history['updated_through']} 이후 ~ {days[-1]} 수집")
        history = _collect(index_id, index_id, days, history)
    print(f"[{index_id}] 완료 — {history['coverage_from']} ~ {history['updated_through']}, 변경 "
          f"{len(history['changes'])}건, 현재 "
          f"{len(im.members_on(index_id, history['updated_through'], history=history))}종목, KRX {_calls}회")


def report() -> None:
    for index_id in _KRX_TICKERS:
        history = im.load_history(index_id)
        if history is None:
            print(f"[{index_id}] 수집 전")
            continue
        print(f"[{index_id}] {history['coverage_from']} ~ {history['updated_through']} · "
              f"변경 {len(history['changes'])}건 · 현재 "
              f"{len(im.members_on(index_id, history['updated_through'], history=history))}종목")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--index", choices=sorted(_KRX_TICKERS))
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--refine", action="store_true",
                        help="일일 관측이 멈췄던 구간의 변경일을 KRX로 정확히 바로잡는다")
    args = parser.parse_args()
    if args.report:
        report()
        return 0
    for index_id in ([args.index] if args.index else sorted(_KRX_TICKERS)):
        backfill(index_id, refine=args.refine)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
