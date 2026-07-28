"""Concept Universe Builder(engine/concept_universe) — 결정론 스코어러·선정 규칙(FR-STR-072).

핵심 계약:
  - 관련도는 LLM 자기평가가 아니라 KG 근거에서 결정론 산출(원장 점수·출처 수·거리 감쇠).
  - 업종 전체가 아니라 Concept 관련 검증 종목만 — pending/rejected 엣지 불참.
  - 기본 임계 0.5, 최소 10개 확보 완화(floor 0.30, 후보 없으면 있는 만큼), 상한 30개.
  - 동일 입력엔 항상 동일 출력(정렬 tie-break까지 결정적).
"""

from __future__ import annotations

import json

import engine.knowledge_graph as kg
from engine.concept_universe import (
    BASE_THRESHOLD, MAX_SIZE, MIN_SIZE, _learned_score, _score_from_note, _select,
    _strip_score_suffix, build_concept_universe,
)


def test_score_from_ledger_note():
    assert _score_from_note("국내 최대 K-팝 기획사(Core 95)") == 0.95
    assert _score_from_note("DBO 사업 진출(Producer/Strong 72)") == 0.72
    assert _score_from_note("TC본더 등 HBM 조립장비") == 0.70  # 표기 없음 → 시드 최소 등급
    assert _score_from_note(None) == 0.70
    assert _strip_score_suffix("음반·공연이 사업 전부(Producer/Core 88)") == "음반·공연이 사업 전부"


def test_learned_score_support_scaling():
    assert _learned_score(1) == 0.60
    assert _learned_score(3) == 0.70
    assert _learned_score(10) == 0.80  # 상한
    assert _learned_score(None) == 0.60  # 결측은 출처 1건 취급


def test_select_threshold_relax_and_cap():
    def mk(n, score):
        return {"symbol": f"{n:06d}", "name": f"종목{n}", "score": score, "reason": "r"}

    # 임계 이상이 3개뿐 → floor(0.30) 이상 후보로 10개까지 완화, 임계 미달 저점(0.2)은 제외
    few = [mk(i, 0.9 - i * 0.01) for i in range(3)] + \
          [mk(10 + i, 0.45 - i * 0.02) for i in range(8)] + [mk(99, 0.2)]
    picked, threshold = _select(few)
    assert len(picked) == MIN_SIZE and threshold < BASE_THRESHOLD
    assert all(c["score"] >= 0.30 for c in picked)
    # 후보 자체가 부족하면 있는 만큼만(억지 채움 금지)
    picked2, _ = _select([mk(1, 0.9), mk(2, 0.6)])
    assert len(picked2) == 2
    # 상한 30 — 점수순 상위만
    many = [mk(i, 0.99 - i * 0.001) for i in range(50)]
    picked3, threshold3 = _select(many)
    assert len(picked3) == MAX_SIZE and threshold3 == BASE_THRESHOLD
    # 동점 tie-break는 심볼 오름차순(재현성)
    tie = [mk(5, 0.7), mk(1, 0.7), mk(3, 0.7)]
    assert [c["symbol"] for c in _select(tie)[0]] == ["000001", "000003", "000005"]


def test_select_size_bounds_do_not_split_ties():
    """[회귀 2026-07-28 '비만치료 관련주' 사고] 크기 경계가 동점 그룹을 가르지 않는다 —
    같은 근거 점수(학습 support 동률·카탈로그 동률)의 일부만 심볼 번호순으로 남기는
    절단은 근거 기반 선정이 아니다."""
    def mk(n, score):
        return {"symbol": f"{n:06d}", "name": f"종목{n}", "score": score, "reason": "r"}

    # MAX_SIZE(30) 경계가 0.60 동률 36개 한가운데 → 36개 전부(학습 엣지 동률 시나리오)
    learned_tie = [mk(i, 0.60) for i in range(36)]
    picked, threshold = _select(learned_tie)
    assert len(picked) == 36 and threshold == BASE_THRESHOLD
    # MIN_SIZE(10) 완화 중단 경계가 0.45 동률 36개 한가운데 → 36개 전부(카탈로그 시나리오)
    catalog_tie = [mk(i, 0.45) for i in range(36)]
    picked2, threshold2 = _select(catalog_tie)
    assert len(picked2) == 36 and threshold2 == 0.45
    # 동점 완결은 그 동점 그룹까지만 — 경계 밖 더 낮은 점수는 여전히 제외
    mixed = [mk(i, 0.60) for i in range(31)] + [mk(90 + i, 0.55) for i in range(5)]
    picked3, _ = _select(mixed)
    assert len(picked3) == 31
    assert all(c["score"] == 0.60 for c in picked3)


def test_concept_not_sector_and_deterministic(tmp_path, monkeypatch):
    """HBM은 반도체 업종 전체가 아니라 KG 검증 관계 종목만 — 반복 호출 결과 동일.

    지분 레이어는 빈 경로로 격리한다 — 실제 kg-equity-edges.json은 수집 스윕이
    갱신 중일 수 있어(로컬) 파일 상태에 따라 결과가 달라지면 결정성 검증이 아니다."""
    import engine.concept_universe as cu

    monkeypatch.setattr(cu, "_EQUITY_PATH", tmp_path / "no-equity.json")
    monkeypatch.setattr(cu, "_EQUITY_CACHE", None)
    r1 = build_concept_universe("HBM")
    r2 = build_concept_universe("HBM")
    assert r1 is not None and r1 == r2
    symbols = {s["symbol"] for s in r1["stocks"]}
    assert {"000660", "005930", "042700"} <= symbols  # 생산·장비 핵심
    assert r1["size"] <= MAX_SIZE
    assert all(0.0 <= s["score"] <= 1.0 for s in r1["stocks"])
    # 모르는 개념은 None(억지 생성 금지)
    assert build_concept_universe("존재하지않는신조어테마") is None
    monkeypatch.setattr(cu, "_EQUITY_CACHE", None)


def test_learned_anchor_hop_decay_and_pending_excluded(tmp_path, monkeypatch):
    """'bts 관련주' 시나리오 — 학습 앵커의 직접 verified(출처 기반 점수) + verified 개념
    1홉 경유(원장 점수 × 감쇠)를 병합하고 심볼별 최고 점수만 남긴다. pending은 불참."""
    import engine.concept_universe as cu

    monkeypatch.setattr(cu, "_EQUITY_PATH", tmp_path / "no-equity.json")
    monkeypatch.setattr(cu, "_EQUITY_CACHE", None)
    lexicon = tmp_path / "term_lexicon.json"
    lexicon.write_text(json.dumps({
        "bts": {"term": "BTS", "sector": "미디어/엔터",
                "searched_at": "2026-07-25T10:10:03+00:00",
                "edges": [
                    {"type": "related_to", "target": "kpop-agency",
                     "support": 4, "status": "verified"},
                    {"type": "related_company", "target": "company:352820",
                     "target_name": "하이브", "support": 1, "status": "verified"},
                    {"type": "related_company", "target": "company:228670",
                     "target_name": "레이", "support": 1, "status": "pending"},
                ]},
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(kg, "_LEXICON_PATH", lexicon)
    monkeypatch.setattr(kg, "_CACHED", None)

    result = build_concept_universe("bts")
    assert result is not None and result["concept_id"] == "learned:bts"
    by_symbol = {s["symbol"]: s for s in result["stocks"]}
    # 하이브: 직접 학습(0.60) vs 홉(kpop-agency Core 95 × 0.85 = 0.8075) → 최고 점수 유지
    assert by_symbol["352820"]["score"] > 0.8
    assert "경유" in by_symbol["352820"]["reason"]
    # 홉 경유 기획사들 포함(업종 전체 아님 — Concept 관련 검증 종목만)
    assert "041510" in by_symbol  # 에스엠
    # pending 엣지(레이)는 어느 층에도 불참
    assert "228670" not in by_symbol

    monkeypatch.setattr(kg, "_CACHED", None)  # 다음 테스트가 원본 경로로 재로드하도록


def test_equity_hop_brings_shareholder_with_decay(tmp_path, monkeypatch):
    """지분 관계 회사 홉(FR-STR-072b) — DART 타법인출자현황 엣지로 유니버스 종목의
    주주가 ×0.7 감쇠로 편입된다('넷마블=하이브 지분 9.2%' 실측 시나리오). 저점수
    부모(0.6×0.7=0.42)는 기본 임계 미만이라 완화 단계에서만 나타난다(자기 제한)."""
    import engine.concept_universe as cu

    lexicon = tmp_path / "term_lexicon.json"
    lexicon.write_text(json.dumps({
        "빅히트뮤직": {"term": "빅히트뮤직", "sector": "미디어/엔터",
                  "edges": [{"type": "related_to", "target": "kpop-agency",
                             "support": 4, "status": "verified"}]},
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(kg, "_LEXICON_PATH", lexicon)
    monkeypatch.setattr(kg, "_CACHED", None)

    equity = tmp_path / "kg-equity-edges.json"
    equity.write_text(json.dumps({
        "version": 1, "edges": [
            {"source": "company:251270", "type": "invests_in",
             "target": "company:352820", "ratio": 9.2,
             "note": "하이브 지분 9.2% 보유(사업보고서 타법인출자현황 2025)"},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(cu, "_EQUITY_PATH", equity)
    monkeypatch.setattr(cu, "_EQUITY_CACHE", None)

    result = build_concept_universe("빅히트뮤직 관련주")
    by_symbol = {s["symbol"]: s for s in result["stocks"]}
    # 하이브(0.8075) 주주 넷마블 → 0.8075 × 0.7 = 0.565 (임계 이상)
    assert "251270" in by_symbol
    assert abs(by_symbol["251270"]["score"] - round(0.95 * 0.85 * 0.7, 4)) < 1e-9
    assert "주주(공시 근거)" in by_symbol["251270"]["reason"]
    assert "9.2%" in by_symbol["251270"]["reason"]

    monkeypatch.setattr(cu, "_EQUITY_CACHE", None)
    monkeypatch.setattr(kg, "_CACHED", None)


def test_manual_edge_note_becomes_reason(tmp_path, monkeypatch):
    """콘솔 수동 엣지(FR-STR-070b ⑦) — 로더가 note를 그래프로 운반하고,
    concept universe가 그 근거 문구를 이유로 표시한다(점수는 시드 최소 등급 0.70)."""
    lexicon = tmp_path / "term_lexicon.json"
    lexicon.write_text(json.dumps({
        "빅히트뮤직": {"term": "빅히트뮤직", "sector": "미디어/엔터",
                  "edges": [{"type": "related_company", "target": "company:309960",
                             "target_name": "LB인베스트먼트", "status": "verified",
                             "proposed_by": "manual", "note": "하이브 초기 투자사"}]},
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(kg, "_LEXICON_PATH", lexicon)
    monkeypatch.setattr(kg, "_CACHED", None)

    result = build_concept_universe("빅히트뮤직 관련주")
    by_symbol = {s["symbol"]: s for s in result["stocks"]}
    assert by_symbol["309960"]["score"] == 0.70
    assert by_symbol["309960"]["reason"] == "하이브 초기 투자사"

    monkeypatch.setattr(kg, "_CACHED", None)
