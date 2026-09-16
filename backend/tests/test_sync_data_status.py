import json
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from scripts import sync_data


def test_symbols_only_returns_nonzero_when_symbol_refresh_falls_back(tmp_path, monkeypatch):
    data_dir = tmp_path / "data" / "ohlcv"
    data_dir.mkdir(parents=True)
    stocks_path = tmp_path / "data" / "korea-stocks.json"
    stocks_path.write_text(
        json.dumps([{"symbol": "005930", "name": "삼성전자", "market": "KOSPI"}], ensure_ascii=False),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sync_data, "_notify_backend", lambda *args, **kwargs: None)
    monkeypatch.setattr(sync_data, "sync_symbols", lambda path: ([], [], []))
    monkeypatch.setattr(sync_data, "validate_stock_list", lambda stocks: [])
    monkeypatch.setattr(
        sync_data,
        "record_universe_sync",
        lambda **kwargs: {
            "date": kwargs["date"],
            "totalCount": kwargs["total_count"],
            "addedCount": len(kwargs["added"]),
            "delistedCount": len(kwargs["delisted"]),
        },
    )

    assert sync_data.main(["--symbols-only"]) == 2


def test_symbols_only_returns_zero_when_symbol_refresh_succeeds(tmp_path, monkeypatch):
    data_dir = tmp_path / "data" / "ohlcv"
    data_dir.mkdir(parents=True)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sync_data, "_notify_backend", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        sync_data,
        "sync_symbols",
        lambda path: ([{"symbol": "005930", "name": "삼성전자", "market": "KOSPI"}], [], []),
    )
    monkeypatch.setattr(sync_data, "validate_stock_list", lambda stocks: [])
    monkeypatch.setattr(
        sync_data,
        "record_universe_sync",
        lambda **kwargs: {
            "date": kwargs["date"],
            "totalCount": kwargs["total_count"],
            "addedCount": len(kwargs["added"]),
            "delistedCount": len(kwargs["delisted"]),
        },
    )

    assert sync_data.main(["--symbols-only"]) == 0


def _scaffold(monkeypatch, tmp_path, stocks, delisted, marked):
    """sync_data.main(--symbols-only)을 네트워크 없이 돌리는 공통 배선."""
    (tmp_path / "data" / "ohlcv").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sync_data, "_notify_backend", lambda *args, **kwargs: None)
    monkeypatch.setattr(sync_data, "sync_symbols", lambda path: (stocks, [], delisted))
    monkeypatch.setattr(sync_data, "validate_stock_list", lambda s: [])
    monkeypatch.setattr(
        sync_data,
        "record_universe_sync",
        lambda **kwargs: {
            "date": kwargs["date"],
            "totalCount": kwargs["total_count"],
            "addedCount": len(kwargs["added"]),
            "delistedCount": len(kwargs["delisted"]),
        },
    )
    # DART 경로는 상장 상태(listingStatus)만 갱신한다 — 원장 등록은 여기서 하지 않는다.
    monkeypatch.setattr(sync_data, "_sync_listing_status_from_dart", lambda *a, **k: None)
    monkeypatch.setattr(sync_data, "_mark_delisted", lambda sym: marked.append(sym) or True)


def test_krx_exit_registers_delisting_ledger(tmp_path, monkeypatch):
    """원장 자동 등록의 정본은 KRX 명부 이탈(= 폐지 완료)이다.

    공시가 말하는 '상장폐지 결정'·'정리매매'는 아직 상장 상태라 원장에 올리면 안 된다 —
    원장은 시세 조회를 통째로 끊고 가상계좌 평가를 0원으로 만드는 표식이다(FR-VM-068b).
    """
    marked: list[str] = []
    _scaffold(
        monkeypatch, tmp_path,
        stocks=[{"symbol": "005930", "name": "삼성전자", "market": "KOSPI"}],
        delisted=[{"symbol": "900110", "name": "이스트아시아홀딩스", "market": "KOSDAQ"}],
        marked=marked,
    )

    assert sync_data.main(["--symbols-only"]) == 0
    assert marked == ["900110"]


def test_mass_disappearance_skips_ledger_registration(tmp_path, monkeypatch):
    """한 번에 상한을 넘겨 사라지면 상폐가 아니라 KRX 조회 누락으로 보고 등록하지 않는다."""
    marked: list[str] = []
    bulk = [{"symbol": f"9001{i:02d}", "name": f"종목{i}", "market": "KOSDAQ"}
            for i in range(sync_data.MAX_AUTO_DELIST_PER_SYNC + 1)]
    _scaffold(
        monkeypatch, tmp_path,
        stocks=[{"symbol": "005930", "name": "삼성전자", "market": "KOSPI"}],
        delisted=bulk,
        marked=marked,
    )

    assert sync_data.main(["--symbols-only"]) == 0
    assert marked == []


def test_failed_symbol_sync_does_not_register_ledger(tmp_path, monkeypatch):
    """종목 목록 갱신이 실패해 기존 파일로 폴백한 회차에는 이탈 판정 자체가 성립하지 않는다."""
    marked: list[str] = []
    stocks_path = tmp_path / "data" / "korea-stocks.json"
    _scaffold(monkeypatch, tmp_path, stocks=[], delisted=[], marked=marked)
    stocks_path.write_text(
        json.dumps([{"symbol": "005930", "name": "삼성전자", "market": "KOSPI"}], ensure_ascii=False),
        encoding="utf-8",
    )

    assert sync_data.main(["--symbols-only"]) == 2
    assert marked == []
