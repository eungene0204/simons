"""KIS 종목마스터 지수 명부 파서 — 레이아웃이 바뀌면 조용히 틀린 명부를 내지 않아야 한다."""
import json

import pytest

from engine import kis_master


def _record(symbol: str, name: str, tail: str) -> str:
    """단축코드 9 + 표준코드 12 + 한글명 + 고정폭 꼬리."""
    return f"{symbol:<9}{'KR' + symbol:<12}{name}{tail}"


def _kosdaq_tail(member: bool) -> str:
    spec = kis_master.INDEX_SPECS["kosdaq150"]
    chars = ["N"] * spec.tail_width
    chars[spec.offset] = "Y" if member else "N"
    return "".join(chars)


def _kospi_tail(member: bool) -> str:
    spec = kis_master.INDEX_SPECS["kospi200"]
    chars = ["0"] * spec.tail_width
    chars[spec.offset] = "3" if member else "0"
    return "".join(chars)


@pytest.fixture
def stub_stocks(monkeypatch, tmp_path):
    path = tmp_path / "korea-stocks.json"
    path.write_text(json.dumps([
        {"symbol": f"{i:06d}", "market": "KOSDAQ"} for i in range(200)
    ] + [
        {"symbol": f"9{i:05d}", "market": "KOSPI"} for i in range(250)
    ]), encoding="utf-8")
    monkeypatch.setattr(kis_master, "_STOCKS_PATH", path)


def test_parses_kosdaq150_membership_flag(stub_stocks):
    spec = kis_master.INDEX_SPECS["kosdaq150"]
    text = "\n".join(
        _record(f"{i:06d}", f"종목{i}", _kosdaq_tail(i < 150)) for i in range(200)
    )

    members = kis_master.parse_members(text, spec)

    assert len(members) == 150
    assert members[0] == ("000000", "종목0")


def test_parses_kospi200_sector_code_flag(stub_stocks):
    spec = kis_master.INDEX_SPECS["kospi200"]
    text = "\n".join(
        _record(f"9{i:05d}", f"대형{i}", _kospi_tail(i < 200)) for i in range(250)
    )

    members = kis_master.parse_members(text, spec)

    assert len(members) == 200


def test_rejects_roster_of_unexpected_size(stub_stocks):
    """레이아웃이 밀려 엉뚱한 컬럼을 읽으면 개수부터 어긋난다 — 조용히 통과시키지 않는다."""
    spec = kis_master.INDEX_SPECS["kosdaq150"]
    text = "\n".join(
        _record(f"{i:06d}", f"종목{i}", _kosdaq_tail(i < 40)) for i in range(200)
    )

    with pytest.raises(kis_master.MasterLayoutError, match="편입 종목 40개"):
        kis_master.parse_members(text, spec)


def test_rejects_members_outside_the_index_market(stub_stocks):
    """KOSDAQ150 인데 KOSPI 종목이 섞이면 플래그 위치를 잘못 읽은 것이다."""
    spec = kis_master.INDEX_SPECS["kosdaq150"]
    rows = [_record(f"{i:06d}", f"종목{i}", _kosdaq_tail(True)) for i in range(149)]
    rows.append(_record("900000", "코스피종목", _kosdaq_tail(True)))

    with pytest.raises(kis_master.MasterLayoutError, match="KOSDAQ 소속이 아닌"):
        kis_master.parse_members("\n".join(rows), spec)
