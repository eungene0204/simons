"""DART 지분 엣지 수집 스크립트(scripts/build_equity_edges) — 파서·가드 검증(FR-STR-072b).

핵심 계약:
  - 법인명 정규화는 정확 일치만(부분 매칭 오탐 차단), ㈜·괄호 병기 제거.
  - 양쪽 상장사 + 지분율 >= min_ratio만 엣지로.
  - 지분율 >= 90%는 동명 비상장 법인 오탐으로 드롭(상장사 유통주식 요건상 불가능 —
    실측: 'DS단석→하이브 100%' 등 7건).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "build_equity_edges.py"
spec = importlib.util.spec_from_file_location("build_equity_edges", _SCRIPT)
bee = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bee)

_NAME_TO_SYMBOL = {"하이브": "352820", "코웨이": "021240"}
_SYMBOL_TO_NAME = {"352820": "하이브", "021240": "코웨이"}


def _edge(row):
    return bee._row_to_edge(row, "251270", _NAME_TO_SYMBOL, _SYMBOL_TO_NAME, "2025", 5.0)


def test_normalize_name_strips_corp_markers():
    assert bee._normalize_name("(주)하이브") == "하이브"
    assert bee._normalize_name("㈜하이브 ") == "하이브"
    assert bee._normalize_name("주식회사 하이브(HYBE)") == "하이브"


def test_parse_ratio_variants():
    assert bee._parse_ratio("18.2") == 18.2
    assert bee._parse_ratio("1,234.5 %") == 1234.5
    assert bee._parse_ratio("-") is None
    assert bee._parse_ratio(None) is None


def test_row_to_edge_contract():
    ok = _edge({"inv_prm": "㈜하이브 (주1)", "trmend_blce_qota_rt": "9.2"})
    assert ok == {
        "source": "company:251270", "type": "invests_in", "target": "company:352820",
        "ratio": 9.2, "note": "하이브 지분 9.2% 보유(사업보고서 타법인출자현황 2025)",
    }
    # 표시명은 DART 원문(각주 찌꺼기)이 아니라 정본 종목명
    assert "주1" not in ok["note"]
    # 비상장 피출자사(마스터 밖)·기준 미달·기말 결측은 기초잔액 폴백
    assert _edge({"inv_prm": "비상장회사", "trmend_blce_qota_rt": "50"}) is None
    assert _edge({"inv_prm": "하이브", "trmend_blce_qota_rt": "4.9"}) is None
    assert _edge({"inv_prm": "하이브", "trmend_blce_qota_rt": "-",
                  "bsis_blce_qota_rt": "7.0"})["ratio"] == 7.0
    # 동명 비상장 법인 오탐 가드 — 상장사 90%+ 보유는 불가능
    assert _edge({"inv_prm": "하이브", "trmend_blce_qota_rt": "100.0"}) is None
    # 자기 자신 출자는 무시
    assert bee._row_to_edge({"inv_prm": "코웨이", "trmend_blce_qota_rt": "10"},
                            "021240", _NAME_TO_SYMBOL, _SYMBOL_TO_NAME, "2025", 5.0) is None
