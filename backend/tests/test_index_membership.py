"""지수 구성종목의 시점별 명단(2026-09-21) — 저장 형식·시점 조회·변경일 탐색.

KRX에 붙지 않는다: 수집기의 `fetch_members`를 달력 표 대역으로 갈아 끼운다.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from engine import index_membership as im

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "backfill_index_membership.py"

_HISTORY = {
    "index": "kospi200", "coverage_from": "2014-05-02", "updated_through": "2014-12-30",
    "initial": ["A", "B", "C"],
    "changes": [
        {"date": "2014-06-13", "added": ["D"], "removed": ["B"]},
        {"date": "2014-12-12", "added": ["B"], "removed": ["A"]},
    ],
}


def test_members_on_reconstructs_roster_at_each_date():
    assert im.members_on("kospi200", "2014-05-02", history=_HISTORY) == ["A", "B", "C"]
    assert im.members_on("kospi200", "2014-06-12", history=_HISTORY) == ["A", "B", "C"]
    assert im.members_on("kospi200", "2014-06-13", history=_HISTORY) == ["A", "C", "D"]   # 변경일 당일부터
    assert im.members_on("kospi200", "2026-01-02", history=_HISTORY) == ["B", "C", "D"]   # 마지막으로 아는 명단


def test_dates_before_coverage_return_none_instead_of_a_made_up_roster():
    assert im.members_on("kospi200", "2013-12-30", history=_HISTORY) is None


def test_intervals_reopen_for_a_symbol_that_returns(tmp_path, monkeypatch):
    monkeypatch.setattr(im, "_DIR", tmp_path)
    im.save_history("kospi200", _HISTORY)

    intervals = im.membership_intervals("kospi200")

    assert intervals["B"] == [["2014-05-02", "2014-06-13"], ["2014-12-12", ""]]
    assert intervals["A"] == [["2014-05-02", "2014-12-12"]]
    assert intervals["D"] == [["2014-06-13", ""]]
    assert im.latest_members("kospi200") == ["B", "C", "D"]


def _load_script():
    spec = importlib.util.spec_from_file_location("backfill_index_membership", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_change_search_finds_exact_days_without_fetching_every_day(monkeypatch):
    script = _load_script()
    days = [f"2020-01-{d:02d}" for d in range(1, 31)]
    roster = {day: frozenset("ABC") for day in days}
    for day in days[12:]:
        roster[day] = frozenset("ACD")            # 13일: B→D
    for day in days[13:]:
        roster[day] = frozenset("ACDE")           # 14일(바로 다음 날): E 편입
    calls = []

    def fake_fetch(index_id, day):
        calls.append(day)
        return roster[day]

    monkeypatch.setattr(script, "fetch_members", fake_fetch)
    monkeypatch.setattr(script.time, "sleep", lambda seconds: None)

    changes = script.find_changes("kospi200", days, frozenset("ABC"))

    assert changes == [
        {"date": "2020-01-13", "added": ["D"], "removed": ["B"]},
        {"date": "2020-01-14", "added": ["E"], "removed": []},
    ]
    assert len(set(calls)) < len(days)            # 바뀌지 않은 구간은 건너뛴다


def test_empty_krx_answer_is_a_failure_not_a_mass_removal(monkeypatch):
    script = _load_script()
    monkeypatch.setattr(script.time, "sleep", lambda seconds: None)
    fake_stock = type("S", (), {"get_index_portfolio_deposit_file": staticmethod(lambda t, d: [])})
    monkeypatch.setitem(sys.modules, "pykrx", type("P", (), {"stock": fake_stock}))

    with pytest.raises(RuntimeError):
        script.fetch_members("kospi200", "2020-01-02")


# ── 일일 관측(KIS 현재 명단)으로 이력 쌓기 — 2026-09-21 사용자 결정 ─────────────────

def test_daily_observation_appends_a_dated_change_only_when_the_roster_moved(tmp_path, monkeypatch):
    monkeypatch.setattr(im, "_DIR", tmp_path)
    im.save_history("kospi200", {**_HISTORY, "changes": list(_HISTORY["changes"])})

    assert im.record_observed_roster("kospi200", ["B", "C", "D"], "2014-12-31") is None     # 그대로
    change = im.record_observed_roster("kospi200", ["B", "C", "E"], "2015-01-02")

    assert change == {"date": "2015-01-02", "after": "2014-12-31", "observed_by": "kis",
                      "added": ["E"], "removed": ["D"]}
    assert im.members_on("kospi200", "2015-01-01") == ["B", "C", "D"]
    assert im.members_on("kospi200", "2015-01-02") == ["B", "C", "E"]
    assert im.load_history("kospi200")["updated_through"] == "2015-01-02"


def test_observation_is_rerun_safe_and_ignores_an_empty_roster(tmp_path, monkeypatch):
    monkeypatch.setattr(im, "_DIR", tmp_path)
    im.save_history("kospi200", {**_HISTORY, "changes": list(_HISTORY["changes"])})

    assert im.record_observed_roster("kospi200", [], "2015-01-02") is None            # 조회 실패 ≠ 전 종목 편출
    assert im.record_observed_roster("kospi200", ["X"], "2014-12-30") is None         # 같은 날·과거로는 안 쓴다
    assert im.latest_members("kospi200") == ["B", "C", "D"]


def test_first_observation_starts_a_history_that_the_collector_can_extend_backwards(tmp_path, monkeypatch):
    monkeypatch.setattr(im, "_DIR", tmp_path)
    script = _load_script()
    monkeypatch.setattr(script.time, "sleep", lambda seconds: None)

    im.record_observed_roster("kospi200", ["A", "C", "D"], "2020-01-10")               # 과거분 없이 관측부터 시작
    im.record_observed_roster("kospi200", ["A", "C", "E"], "2020-01-13")
    days = [f"2020-01-{d:02d}" for d in range(2, 14)]
    krx = {day: frozenset("ABC") for day in days}
    for day in days[5:]:
        krx[day] = frozenset("ACD")                                                    # 01-07: B→D
    monkeypatch.setattr(script, "fetch_members", lambda index_id, day: krx[day])

    stitched = script.prepend_past("kospi200", im.load_history("kospi200"), days)

    assert stitched["coverage_from"] == "2020-01-02"
    assert [c["date"] for c in stitched["changes"]] == ["2020-01-07", "2020-01-13"]
    assert im.members_on("kospi200", "2020-01-06") == ["A", "B", "C"]
    assert im.members_on("kospi200", "2020-01-13") == ["A", "C", "E"]
    assert not im.history_path("kospi200.past").exists()


def test_refine_moves_a_gapped_observation_to_the_exact_day(tmp_path, monkeypatch):
    monkeypatch.setattr(im, "_DIR", tmp_path)
    script = _load_script()
    monkeypatch.setattr(script.time, "sleep", lambda seconds: None)
    days = [f"2020-02-{d:02d}" for d in range(3, 15)]
    history = {"index": "kospi200", "coverage_from": days[0], "updated_through": days[-1],
               "initial": ["A", "B"],
               "changes": [{"date": days[-1], "after": days[0], "observed_by": "kis",
                            "added": ["C"], "removed": ["B"]}]}
    krx = {day: frozenset("AB") for day in days}
    for day in days[4:]:
        krx[day] = frozenset("AC")                                                     # 실제 변경일은 02-07
    monkeypatch.setattr(script, "fetch_members", lambda index_id, day: krx[day])

    refined = script.refine_observed_changes("kospi200", history, days)

    assert refined["changes"] == [{"date": "2020-02-07", "added": ["C"], "removed": ["B"]}]
