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


def test_concept_not_sector_and_deterministic():
    """HBM은 반도체 업종 전체가 아니라 KG 검증 관계 종목만 — 반복 호출 결과 동일."""
    r1 = build_concept_universe("HBM")
    r2 = build_concept_universe("HBM")
    assert r1 is not None and r1 == r2
    symbols = {s["symbol"] for s in r1["stocks"]}
    assert {"000660", "005930", "042700"} <= symbols  # 생산·장비 핵심
    assert r1["size"] <= MAX_SIZE
    assert all(0.0 <= s["score"] <= 1.0 for s in r1["stocks"])
    # 모르는 개념은 None(억지 생성 금지)
    assert build_concept_universe("존재하지않는신조어테마") is None


def test_learned_anchor_hop_decay_and_pending_excluded(tmp_path, monkeypatch):
    """'bts 관련주' 시나리오 — 학습 앵커의 직접 verified(출처 기반 점수) + verified 개념
    1홉 경유(원장 점수 × 감쇠)를 병합하고 심볼별 최고 점수만 남긴다. pending은 불참."""
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
