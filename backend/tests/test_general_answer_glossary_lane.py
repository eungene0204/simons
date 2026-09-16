"""일반 지식 답변(/query/general)의 용어 정의 주입 레인과 외국 문자 누출 가드.

[회귀 2026-09-17] "PER과 PBR이 정확히 무슨 뜻인가요?" — 원문 정규식 `\\bper\\b`가 "PER과"를
놓쳐(한글도 단어 문자) 정의가 주입되지 않았고, 답변이 PER을 '예상 순이익' 기준으로 설명하며
한자("一株당")를 섞었다. 용어 판정은 LLM 추출로 옮기고, 한자·가나가 섞인 답변은 오류를 알려
다시 생성한다(후처리로 문자열을 고치지 않는다).
"""

import json

from api import intent_routes
from intent import glossary_facts


def test_extract_terms_reads_llm_json_and_registry_maps_aliases():
    calls = []

    def chat(system, user, **kwargs):
        calls.append((system, user))
        return '```json\n{"terms": ["PER", "주가순자산비율"]}\n```'

    terms = glossary_facts.extract_terms("PER과 PBR이 정확히 무슨 뜻인가요?", chat)
    assert terms == ["PER", "주가순자산비율"]
    assert calls and calls[0][0] == glossary_facts.TERM_EXTRACT_PROMPT

    block = glossary_facts.facts_block(terms)
    assert "PER(주가수익비율) = 주가 ÷ 주당순이익(EPS)" in block
    assert "PBR(주가순자산비율) = 주가 ÷ 주당순자산(BPS)" in block


def test_registry_normalizes_llm_notation_only():
    assert "주가수익비율" in glossary_facts.facts_block(["per (주가수익비율)"])
    assert glossary_facts.facts_block(["배당수익률"]) is None
    assert glossary_facts.facts_block([]) is None


def test_extract_terms_tolerates_malformed_output():
    assert glossary_facts.extract_terms("질문", lambda *a, **k: "모르겠습니다") == []
    assert glossary_facts.extract_terms("질문", lambda *a, **k: '{"terms": "PER"}') == []


def _wire(monkeypatch, prose_replies, extracted=("PER", "PBR")):
    monkeypatch.setattr(intent_routes, "_llm_available", lambda: True)
    monkeypatch.setattr(intent_routes.platform_defaults, "reply", lambda q: None)
    monkeypatch.setattr(intent_routes.platform_defaults, "facts_block", lambda q: None)
    monkeypatch.setattr(
        intent_routes, "_mlx_llm_structured",
        lambda system, user, **k: json.dumps({"terms": list(extracted)}),
    )
    import engine.term_grounding as tg
    monkeypatch.setattr(tg, "general_facts_block", lambda *a, **k: None)
    prompts = []
    replies = list(prose_replies)

    def prose(system, user, **k):
        prompts.append(user)
        return replies.pop(0)

    monkeypatch.setattr(intent_routes, "_mlx_llm_prose", prose)
    return prompts


def test_general_answer_injects_definitions_for_terms_with_particles(monkeypatch):
    prompts = _wire(monkeypatch, ["PER은 주가를 주당순이익으로 나눈 값입니다."])
    answer = intent_routes.generate_general_answer("PER과 PBR이 정확히 무슨 뜻인가요?")
    assert answer == "PER은 주가를 주당순이익으로 나눈 값입니다."
    assert "주가 ÷ 주당순이익(EPS)" in prompts[0]
    assert "주가 ÷ 주당순자산(BPS)" in prompts[0]


def test_foreign_script_answer_is_regenerated_not_patched(monkeypatch):
    prompts = _wire(monkeypatch, [
        "PER(주가수익비율)은 주가가一株당 순이익을 몇 배인지 보여줍니다.",
        "PER은 주가를 주당순이익으로 나눈 값입니다.",
    ])
    answer = intent_routes.generate_general_answer("PER과 PBR이 정확히 무슨 뜻인가요?")
    assert answer == "PER은 주가를 주당순이익으로 나눈 값입니다."
    assert len(prompts) == 2 and "一株" in prompts[1] and "[형식 오류]" in prompts[1]


def test_foreign_script_twice_returns_none(monkeypatch):
    _wire(monkeypatch, ["一株당 순이익", "株価 기준"])
    assert intent_routes.generate_general_answer("PER이 뭐야?") is None
