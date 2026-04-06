from ai.summarize import normalize_report_items


def test_normalize_report_items_returns_none_when_empty():
    assert normalize_report_items([]) == ["없음"]
    assert normalize_report_items(None) == ["없음"]
    assert normalize_report_items(["", "   ", None]) == ["없음"]


def test_normalize_report_items_keeps_non_empty_values():
    assert normalize_report_items(["강점 1", "  리스크 1  "]) == ["강점 1", "리스크 1"]
