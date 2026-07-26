"""Universe Resolver — LLM이 추출한 유니버스 표현을 정본 값으로 해석한다.

indicator_registry가 지표명을 canonical ID로 푸는 것과 같은 역할을 유니버스에 대해
수행한다. 입력은 **LLM이 뽑아낸 짧은 문자열**(업종/테마명, 종목명 또는 종목코드)이며,
사용자 원문을 다시 읽지 않는다 — 자연어 해석은 LLM, 정본 매핑은 이 모듈의 몫이다
(docs/nl_interpretation_contract.md § 3).

'반도체'→정본 섹터명, 'HBM'→지식그래프 개념, '삼성전자'→005930 같은 매핑은 LLM이
대체할 수 없는 지식 조회다(4B든 9B든 종목코드를 환각한다). 따라서 이 레이어는 제거 대상이
아니라, 원문 정규식에서 떼어내 LLM 출력을 입력으로 받도록 재배치된 것이다.
"""

from __future__ import annotations

import re
from typing import List, Optional, Sequence, Tuple, Union

_SYMBOL_CODE_RE = re.compile(r"^\d{6}$")

SectorValue = Optional[Union[str, List[str]]]


def resolve_sectors(terms: Sequence[str]) -> Tuple[SectorValue, List[str]]:
    """업종/테마 표현 목록 → (ParsedStrategy.sector 정규형, 해석 실패 표현 목록).

    해석 순서:
      ① 정본 섹터 사전(normalize_sector) — 동의어·표기 변형 포함
      ② 지식그래프(resolve_sector_from_text) — 시드 개념(HBM·SMR)과 검색 학습 용어

    정규형은 없음=None / 단일=str / 복수=list(순서 보존 dedup)로, 기존 sector 필드
    계약(FR-STR-066 ⑦)과 동일하다. 해석하지 못한 표현은 조용히 버리지 않고 반환한다.
    """
    from engine.universe_pit import normalize_sector, normalize_sector_value

    resolved: List[str] = []
    unresolved: List[str] = []
    for term in terms or []:
        if not isinstance(term, str) or not term.strip():
            continue
        term = term.strip()
        canonical = normalize_sector(term) or _resolve_via_knowledge_graph(term)
        if canonical is None:
            if term not in unresolved:
                unresolved.append(term)
        elif canonical not in resolved:
            resolved.append(canonical)
    return normalize_sector_value(resolved), unresolved


def _resolve_via_knowledge_graph(term: str) -> Optional[str]:
    """지식그래프에서 테마어의 정본 섹터를 찾는다. 그래프 실패가 컴파일을 막지 않는다."""
    try:
        from engine.knowledge_graph import resolve_sector_from_text

        return resolve_sector_from_text(term)
    except Exception:  # noqa: BLE001 — 그래프 장애는 유니버스 해석 실패로만 강등
        return None


def resolve_symbols(refs: Sequence[str]) -> Tuple[List[str], List[str]]:
    """지정 종목 표현 목록 → (6자리 종목코드 목록, 해석 실패 표현 목록).

    국내 상장 종목만 대상으로 한다 — 해외 종목은 백테스트 OHLCV가 없어 지정해도
    실행할 수 없으므로 해석 실패로 돌린다(조용히 통과시키면 0거래로 끝난다).
    """
    try:
        from stock_analysis.symbol_resolver import find_in_text, resolve_by_symbol
    except Exception:  # noqa: BLE001 — 마스터 로드 실패 시 지정 없음으로 강등
        return [], list(refs or [])

    codes: List[str] = []
    unresolved: List[str] = []
    for ref in refs or []:
        # 비문자열 항목도 조용히 버리지 않는다(계약 § 3: 해석 실패는 반환·기록) — 스키마
        # 정규화(_coerce_str_list)가 구제하지 못한 형태는 unresolved로 보고해 상류가 알린다.
        if not isinstance(ref, str):
            if ref is not None and str(ref) not in unresolved:
                unresolved.append(str(ref))
            continue
        if not ref.strip():
            continue
        ref = ref.strip()
        resolved = (
            resolve_by_symbol(ref) if _SYMBOL_CODE_RE.match(ref)
            else next((r for r in find_in_text(ref) if not r.overseas), None)
        )
        if resolved is None or resolved.overseas:
            if ref not in unresolved:
                unresolved.append(ref)
        elif resolved.symbol not in codes:
            codes.append(resolved.symbol)
    return codes, unresolved
