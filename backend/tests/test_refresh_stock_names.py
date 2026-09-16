"""종목명 제자리 갱신(scripts/refresh_stock_names.py) 회귀.

사고(2026-09-16): 유니버스 목록에 '세기상사 (002420)'가 나갔다 — 회사는 우양피앤엘로 사명을
바꿨는데(종목코드 그대로) 이름 정본 `korea-stocks.json`이 전체 동기화로만 갱신됐고, 그
동기화는 손질한 섹터·영문명을 날려서 아무도 돌리지 않았다. 갱신은 이름만 바꿔야 하고,
옛 이름은 구 사명 별칭으로 남아 계속 인식돼야 한다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts.build_stock_name_history as history_builder  # noqa: E402
from scripts.refresh_stock_names import (  # noqa: E402
    SuspiciousListingError,
    apply_official_names,
    merge_history,
)


def _row(symbol: str, name: str, **extra) -> dict:
    return {"symbol": symbol, "name": name, "market": "KOSPI", "sector": "유통/상사",
            "industry": "연료 소매업", **extra}


def _stocks(n: int = 40) -> list[dict]:
    rows = [_row("002420", "세기상사", name_en="Century"), _row("007700", "F&F 홀딩스")]
    rows += [_row(f"9{i:05d}", f"종목{i}") for i in range(n - len(rows))]
    return rows


def _official(stocks: list[dict], **overrides) -> dict[str, str]:
    return {**{r["symbol"]: r["name"] for r in stocks}, **overrides}


def test_rename_replaces_only_name_and_keeps_curated_fields():
    stocks = _stocks()
    updated, events = apply_official_names(
        stocks, _official(stocks, **{"002420": "우양피앤엘"}), "2026-09-16")

    row = next(r for r in updated if r["symbol"] == "002420")
    assert row == {**stocks[0], "name": "우양피앤엘"}   # sector·industry·market·name_en 보존
    assert events == [{"symbol": "002420", "from": "세기상사", "to": "우양피앤엘",
                       "observedOn": "2026-09-16", "source": "KIND"}]


def test_spacing_only_difference_updates_name_without_rename_event():
    stocks = _stocks()
    updated, events = apply_official_names(
        stocks, _official(stocks, **{"007700": "F&F홀딩스"}), "2026-09-16")

    assert next(r for r in updated if r["symbol"] == "007700")["name"] == "F&F홀딩스"
    assert events == []


def test_symbols_missing_from_listing_are_left_untouched():
    stocks = _stocks()
    official = _official(stocks)
    del official["002420"]   # KIND에 없는 행(상폐 등) — 추가·삭제는 이 스크립트 몫이 아니다
    updated, events = apply_official_names(stocks, official, "2026-09-16")
    assert updated == stocks and events == []


def test_truncated_listing_aborts():
    stocks = _stocks()
    official = dict(list(_official(stocks).items())[:10])
    with pytest.raises(SuspiciousListingError):
        apply_official_names(stocks, official, "2026-09-16")


def test_mass_rename_aborts_as_garbled_response():
    stocks = _stocks()
    garbled = {r["symbol"]: r["name"] + "?" for r in stocks}
    with pytest.raises(SuspiciousListingError):
        apply_official_names(stocks, garbled, "2026-09-16")


def test_merge_history_registers_former_name_and_dedups(tmp_path, monkeypatch):
    stocks_path = tmp_path / "korea-stocks.json"
    stocks_path.write_text(json.dumps([_row("002420", "우양피앤엘")], ensure_ascii=False),
                           encoding="utf-8")
    monkeypatch.setattr(history_builder, "_STOCKS_JSON", stocks_path)
    event = {"symbol": "002420", "from": "세기상사", "to": "우양피앤엘",
             "observedOn": "2026-09-16", "source": "KIND"}
    history = {"generatedAt": "2026-08-29T09:37:17", "renames": [], "formerNames": {}}

    once = merge_history(history, [event], "2026-09-16T21:00:00+09:00")
    twice = merge_history(once, [event], "2026-09-17T21:00:00+09:00")

    assert once["formerNames"] == {"세기상사": "002420"}
    assert once["generatedAt"] == "2026-08-29T09:37:17"   # 스냅샷 빌드 메타는 보존
    assert twice["renames"] == [event]                     # 같은 사건은 한 번만


def test_snapshot_rebuild_keeps_daily_events(tmp_path, monkeypatch):
    out = tmp_path / "stock-name-history.json"
    daily = {"symbol": "002420", "from": "세기상사", "to": "우양피앤엘",
             "observedOn": "2026-09-16", "source": "KIND"}
    snapshot = {"symbol": "070300", "from": "엑스큐어", "to": "퀀텀레일",
                "lastSeenFrom": "202607", "firstSeenTo": "202608"}
    out.write_text(json.dumps({"renames": [snapshot, daily]}, ensure_ascii=False),
                   encoding="utf-8")
    monkeypatch.setattr(history_builder, "_OUT_PATH", out)

    assert history_builder.kept_daily_events() == [daily]
