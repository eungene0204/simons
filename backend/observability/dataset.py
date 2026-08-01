"""Evaluation Dataset — 전략 대화 Agent의 대표 입력 묶음(스펙 § Dataset).

여기 있는 것은 **입력과 그 입력에 기대하는 구조적 성질**뿐이다. 정답 전략(reference
output)은 담지 않는다 — 되묻기는 실패가 아니라 정상 동작이고(값 없는 팩터를 묻는 것이
Agent의 계약), "이 입력엔 이 전략이 정답"이라고 못 박으면 그 계약을 어기는 쪽이 통과한다.

대신 각 예시는 evaluators.py가 검사할 수 있는 성질만 선언한다:

- ``expects_universe``: 이 턴이 유니버스를 확정해야 하는가
- ``expects_ask``:      되묻기로 끝나는 것이 정상인가(정보가 모자란 입력)
- ``forbidden_tools``:  이 입력에 불려서는 안 되는 도구(예: ETF에 재무 조회)
- ``turn_kind``:        create | modify — modify 예시는 직전 전략이 있어야 성립한다
"""

from __future__ import annotations

from typing import Any, Dict, List

DATASET_NAME = "nullstock-strategy-agent"

# 스펙 § Dataset의 21개 대표 입력. category는 LangSmith에서 묶어 보기 위한 축이다.
EXAMPLES: List[Dict[str, Any]] = [
    # ── 유니버스별 전략 생성 ────────────────────────────────────────────────
    {"input": "PER 10 이하인 코스피 전략 만들어줘", "category": "생성/코스피",
     "turn_kind": "create", "expects_universe": True, "expects_ask": True},
    {"input": "코스닥 종목으로 모멘텀 전략 만들어줘", "category": "생성/코스닥",
     "turn_kind": "create", "expects_universe": True, "expects_ask": True},
    {"input": "반도체 ETF 투자 전략", "category": "생성/ETF",
     "turn_kind": "create", "expects_universe": True, "expects_ask": True,
     # ETF는 개별 기업 재무를 쓸 수 없다 — 재무 조건 질문·칩이 나오면 계약 위반.
     "forbidden_terms": ["PER", "PBR", "ROE", "EPS", "영업이익", "순이익", "매출"]},
    {"input": "삼성전자만으로 전략 만들어줘", "category": "생성/단일종목",
     "turn_kind": "create", "expects_universe": True, "expects_ask": True,
     # 종목이 정해졌으므로 종목 수·리밸런싱을 묻는 것은 계약 위반.
     "forbidden_terms": ["최대 몇 종목", "리밸런싱 주기"]},

    # ── 수정 ────────────────────────────────────────────────────────────────
    {"input": "RSI 조건 추가해줘", "category": "수정/조건추가", "turn_kind": "modify",
     "expects_ask": True},
    {"input": "그 조건 빼줘", "category": "수정/조건삭제", "turn_kind": "modify"},
    {"input": "매수 조건만 수정", "category": "수정/부분수정", "turn_kind": "modify",
     "expects_ask": True},
    {"input": "리밸런싱 분기로 바꿔줘", "category": "수정/리밸런싱", "turn_kind": "modify"},
    {"input": "종목 바꿀래", "category": "수정/유니버스교체", "turn_kind": "modify",
     "expects_ask": True},
    {"input": "ETF로 해줘", "category": "수정/유니버스교체", "turn_kind": "modify",
     "expects_universe": True},
    {"input": "10%는 너무 높아", "category": "수정/값조정", "turn_kind": "modify",
     "expects_ask": True},
    {"input": "그건 유지", "category": "수정/유지", "turn_kind": "modify"},

    # ── 대화 제어 ───────────────────────────────────────────────────────────
    {"input": "이 전략 취소", "category": "제어/취소", "turn_kind": "modify"},
    {"input": "다시 처음부터", "category": "제어/초기화", "turn_kind": "modify"},

    # ── 규제 게이트(추천 요청) — 되묻기가 아니라 안내로 끝나야 한다 ──────────
    {"input": "알아서 추천해줘", "category": "규제/추천요청", "turn_kind": "create",
     "expects_recommendation_refusal": True},

    # ── 테마·개념 유니버스(지식그래프·검색 학습 경로) ────────────────────────
    {"input": "삼성전자 관련 ETF", "category": "테마/모호성", "turn_kind": "create",
     "expects_universe": True, "expects_ask": True},
    {"input": "이재명 관련주", "category": "테마/정책", "turn_kind": "create",
     "expects_universe": True},
    {"input": "HBM 전략", "category": "테마/기술", "turn_kind": "create",
     "expects_universe": True, "expects_ask": True},
    {"input": "ESS 관련주", "category": "테마/기술", "turn_kind": "create",
     "expects_universe": True},
    {"input": "AI 반도체", "category": "테마/기술", "turn_kind": "create",
     "expects_universe": True},
    {"input": "2차전지 소재 관련주로 전략 만들어줘", "category": "테마/복합",
     "turn_kind": "create", "expects_universe": True, "expects_ask": True},
]


def as_langsmith_examples() -> List[Dict[str, Any]]:
    """LangSmith Dataset 업로드 형태 {inputs, outputs, metadata}로 바꾼다.

    outputs(기대 산출물)는 비운다 — 위 docstring의 이유로 정답 전략을 두지 않는다.
    검사할 성질은 metadata로 넘겨 evaluator가 읽는다.
    """
    rows: List[Dict[str, Any]] = []
    for example in EXAMPLES:
        metadata = {k: v for k, v in example.items() if k != "input"}
        rows.append({
            "inputs": {"user_input": example["input"]},
            "outputs": {},
            "metadata": metadata,
        })
    return rows
