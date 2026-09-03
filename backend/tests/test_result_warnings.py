"""결과 경고 구조화(engine/result_warnings.py) 회귀.

사고(2026-09-03): /us 백테스트 결과 로그에 리밸런싱 고지가 한국어로 나왔다. 경고가 값을 박은
완성 문장이라 사전 키가 될 수 없었다. 경고는 한국어 정본 템플릿+인자(warningParts)로 나르고
한국어 문장(warnings)은 종전과 바이트 동일해야 한다.
"""
from __future__ import annotations

import pathlib
import re

from engine import data_coverage
from engine import result_warnings as rw
from engine import trade_reason as tr

_BACKEND = pathlib.Path(__file__).resolve().parents[1]


def test_single_template_renders_legacy_sentence():
    encoded = rw.warning(rw.FEW_TRADES, 12)
    assert tr.text(encoded) == "거래 수가 12건으로 30건 미만입니다 — 승률·Profit Factor 등 통계의 표본 신뢰도가 낮습니다."
    assert tr.decode(encoded) == [{"t": rw.FEW_TRADES, "a": [12]}]


def test_no_trades_liquidity_detail_matches_legacy_format():
    symbols = ["005930", "000660", "035420", "051910", "006400"]
    excluded = [tr.literal(", ".join(symbols[:3])), tr.part(rw.MORE_SYMBOLS, 2)]
    encoded = rw.compose(
        tr.part(rw.NO_TRADES),
        tr.part(rw.NO_TRADES_LIQUIDITY_DETAIL, 5, excluded),
    )
    assert tr.text(encoded) == (
        "매매 기록이 생성되지 않았습니다. 매수 조건 또는 유동성/포지션 설정을 확인해 주세요."
        " (유동성 기준 미달로 제외된 종목 5개: 005930, 000660, 035420 외 2종목"
        " — 포지션 크기를 줄이거나 유동성 한도를 낮추면 포함될 수 있습니다)"
    )


def test_nested_label_list_renders_and_keeps_labels_translatable():
    encoded = rw.warning(rw.COMPOSITE_RANK_DATA_MISSING, rw.label_list(["PER", "배당수익률"]))
    assert tr.text(encoded) == "복합 순위 구성 지표 'PER, 배당수익률' 데이터가 대상 종목에 없어 랭킹 선정이 적용되지 않았습니다."
    (segment,) = tr.decode(encoded)
    # 라벨은 사전 키라 번역 세그먼트로 중첩된다(프론트가 라벨도 t()로 옮긴다).
    assert segment["a"][0] == [{"t": "PER"}, {"s": ", "}, {"t": "배당수익률"}]


def test_symbol_of_reads_symbol_warning():
    assert rw.symbol_of(rw.warning(rw.SYMBOL_LIQUIDITY_BELOW, "005930")) == "005930"
    assert tr.first_template(rw.warning(rw.SYMBOL_LIQUIDITY_BELOW, "005930")) == rw.SYMBOL_LIQUIDITY_BELOW
    assert rw.symbol_of("평문 경고") is None


def test_finalize_aligns_texts_and_parts_sorted_with_plain_passthrough():
    raw = {
        rw.warning(rw.FEW_TRADES, 3),
        rw.warning(rw.ZERO_COST),
        "외부 라이브러리 평문 경고",
    }
    texts, parts = rw.finalize(raw)
    assert len(texts) == len(parts) == 3
    assert texts == sorted(texts)
    for text, segs in zip(texts, parts):
        assert tr.render_kr(segs) == text
    assert [tr.literal("외부 라이브러리 평문 경고")] in parts


def test_data_coverage_report_carries_aligned_parts():
    acc = data_coverage.CoverageAccumulator(["per", "market_cap"])
    acc.fold({
        "per": {"rows_total": 10, "rows_valid": 4, "first_valid": "2015-01-01", "last_valid": "2020-01-01",
                "rows_excluded_negative": 0},
        "market_cap": {"rows_total": 10, "rows_valid": 0, "first_valid": None, "last_valid": None,
                       "rows_excluded_negative": 0},
    })
    report = acc.build()
    assert len(report["warnings"]) == len(report["warningParts"]) >= 2
    for text, segs in zip(report["warnings"], report["warningParts"]):
        assert tr.render_kr(segs) == text
    # 지표 라벨은 중첩 세그먼트(사전 키)로 실린다.
    assert any({"t": "시가총액"} in seg.get("a", []) for parts in report["warningParts"] for seg in parts)


def test_engine_sources_have_no_plain_warning_literals():
    """새 경고를 f-string으로 완성해 넣으면 /us에서 다시 한국어가 새어 나간다 — 정본 모듈을 거치게 강제."""
    # f-string 또는 한국어가 든 문자열 리터럴만 잡는다(("warning", "success") 같은 상태 튜플은 대상 아님).
    literal = r'(?:f"|"[^"]*[가-힣])'
    plain = re.compile(r'warnings\.add\(\s*' + literal + r'|\("warning",\s*' + literal + r'|"warning":\s*' + literal)
    for rel in ("backtest_engine.py", "engine/phase1.py", "engine/data_coverage.py"):
        source = (_BACKEND / rel).read_text(encoding="utf-8")
        hits = [m.group(0) for m in plain.finditer(source)]
        assert not hits, f"{rel}: 평문 경고 리터럴 {hits} — engine/result_warnings.py 템플릿으로 옮길 것"
