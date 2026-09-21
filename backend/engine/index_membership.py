"""지수 구성종목의 시점별 명단(KOSPI200·KOSDAQ150) — 저장·조회.

과거분의 정본은 KRX 지수구성종목이고(수집 `scripts/backfill_index_membership.py`), 그 뒤는 매일 받는
KIS 현재 명단을 직전 명단과 비교해 덧붙인다(`record_observed_roster` — 야간 동기화가 부른다).
**정본은 프로덕션**이다: 박스의 야간 동기화가 매일 쓰므로 git으로 추적하지 않고(추적하면 배포의
`reset --hard`가 박스에서 쌓은 이력을 되돌린다) 로컬은 `mirror_data.py --membership`으로 받는다.
파일은 첫 스냅샷과
변경 이력(편입·편출)만 담는다 — 구성 변경이 드물어(정기 연 2회 + 수시) 매일의 명단을 통째로
두는 것보다 작고, git diff로 무엇이 바뀌었는지 읽힌다::

    {"index": "kospi200", "coverage_from": "2014-05-02", "updated_through": "2026-09-18",
     "initial": ["000020", ...],
     "changes": [{"date": "2014-06-13", "added": [...], "removed": [...]}, ...]}

가용 구간은 KOSPI200 **2014-05-02**·KOSDAQ150 **2015-07-13**(지수 출범일)부터다. 그 이전 날짜는
None을 돌려준다 — 없는 명단을 지어내지 않는다(호출부가 시가총액 상위 N 근사로 폴백한다).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DIR = _PROJECT_ROOT / "data" / "index-membership"

# 지수별로 KRX 지수구성종목이 응답을 시작하는 날(실측 2026-09-21). KOSPI200은 KRX가 2014-05-01
# 이전 데이터를 주지 않아서이고, KOSDAQ150은 지수 자체가 2015-07-13에 나왔다(그 전날은 빈 응답).
COVERAGE_START = {"kospi200": "2014-05-02", "kosdaq150": "2015-07-13"}

INDEX_IDS = tuple(COVERAGE_START)


def history_path(index_id: str) -> Path:
    return _DIR / f"{index_id}.json"


def load_history(index_id: str) -> Optional[dict]:
    try:
        payload = json.loads(history_path(index_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) and payload.get("initial") else None


def save_history(index_id: str, history: dict) -> None:
    path = history_path(index_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, ensure_ascii=False, indent=1), encoding="utf-8")


def members_on(index_id: str, day: str, *, history: Optional[dict] = None) -> Optional[List[str]]:
    """`day`(YYYY-MM-DD) 시점의 구성종목(정렬). 수집 전이거나 가용 구간 이전이면 None.

    `updated_through` 이후 날짜는 마지막으로 아는 명단이다 — 그 뒤의 변경은 아직 모른다.
    """
    history = history if history is not None else load_history(index_id)
    if history is None or day < history["coverage_from"]:
        return None
    members = set(history["initial"])
    for change in history["changes"]:
        if change["date"] > day:
            break
        members |= set(change["added"])
        members -= set(change["removed"])
    return sorted(members)


def record_observed_roster(index_id: str, symbols: List[str], day: str) -> Optional[dict]:
    """오늘 받은 **현재 명단**(KIS 종목마스터)을 이력에 덧붙인다. 바뀐 것이 있으면 그 변경을 돌려준다.

    과거분은 KRX에서 한 번 받고, 그 뒤는 매일의 현재 명단을 직전 명단과 비교해 쌓는다
    (2026-09-21 사용자 결정 — KIS·토스는 과거 시점 명단을 주지 않고, KRX는 연속 조회를 막는다).
    변경일은 **관측한 날**이다: 수집이 며칠 멈췄다면 실제 변경은 `after`(직전 관측일)와 `date`
    사이 어느 날이다 — 그 구간은 KRX 수집기(`scripts/backfill_index_membership.py --refine`)가
    정확한 날짜로 바로잡는다. 이력이 없으면 오늘을 시작으로 만든다(과거는 수집기가 앞에 붙인다).
    같은 날·과거 날짜로는 다시 쓰지 않는다(재실행 안전).
    """
    members = sorted({str(symbol) for symbol in symbols if symbol})
    if not members:
        return None                                   # 빈 명단은 '전 종목 편출'이 아니라 조회 실패다
    history = load_history(index_id)
    if history is None:
        save_history(index_id, {
            "index": index_id, "source": "KIS 종목마스터 일일 관측(과거분은 KRX 지수구성종목)",
            "coverage_from": day, "updated_through": day, "initial": members, "changes": [],
        })
        return None
    if day <= history["updated_through"]:
        return None
    previous = set(members_on(index_id, history["updated_through"], history=history) or [])
    change = None
    if previous != set(members):
        change = {
            "date": day, "after": history["updated_through"], "observed_by": "kis",
            "added": sorted(set(members) - previous), "removed": sorted(previous - set(members)),
        }
        history["changes"].append(change)
    history["updated_through"] = day
    save_history(index_id, history)
    return change


def latest_members(index_id: str) -> Optional[List[str]]:
    """마지막으로 아는 명단(현재 명단 조회가 실패했을 때의 폴백)."""
    history = load_history(index_id)
    if history is None:
        return None
    return members_on(index_id, history["updated_through"], history=history)


def membership_intervals(index_id: str) -> Optional[Dict[str, List[List[str]]]]:
    """종목별 편입 구간 ``{symbol: [[from, to], ...]}`` (to는 편출 전날이 아니라 편출일 — 반열림).

    마지막 구간이 아직 편입 중이면 to는 빈 문자열이다. 백테스트가 날짜×종목 마스크를 만들 때 쓴다.
    """
    history = load_history(index_id)
    if history is None:
        return None
    intervals: Dict[str, List[List[str]]] = {
        symbol: [[history["coverage_from"], ""]] for symbol in history["initial"]
    }
    for change in history["changes"]:
        for symbol in change["removed"]:
            spans = intervals.get(symbol)
            if spans and spans[-1][1] == "":
                spans[-1][1] = change["date"]
        for symbol in change["added"]:
            intervals.setdefault(symbol, []).append([change["date"], ""])
    return intervals
