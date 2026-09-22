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

import ui_language

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
    from engine.universe_pit import expand_legacy_sector, normalize_sector_value

    resolved: List[str] = []
    unresolved: List[str] = []
    for term in terms or []:
        if not isinstance(term, str) or not term.strip():
            continue
        term = term.strip()
        # expand_legacy_sector: 정본·동의어는 1개, 분할 전 구 묶음명('증권/보험')은
        # 신규 두 섹터로 편다(저장된 전략의 유니버스가 좁아지지 않게).
        canonical = expand_legacy_sector(term)
        if not canonical:
            via_kg = _resolve_via_knowledge_graph(term)
            canonical = (via_kg,) if via_kg else ()
        if not canonical:
            if term not in unresolved:
                unresolved.append(term)
            continue
        for item in canonical:
            if item not in resolved:
                resolved.append(item)
    return normalize_sector_value(resolved), unresolved


def _resolve_via_knowledge_graph(term: str) -> Optional[str]:
    """지식그래프에서 테마어의 정본 섹터를 찾는다. 그래프 실패가 컴파일을 막지 않는다."""
    try:
        from engine.knowledge_graph import resolve_sector_from_text

        return resolve_sector_from_text(term)
    except Exception:  # noqa: BLE001 — 그래프 장애는 유니버스 해석 실패로만 강등
        return None


def resolve_symbols(refs: Sequence[str]) -> Tuple[List[str], List[str]]:
    """지정 종목 표현 목록 → (종목코드/티커 목록, 해석 실패 표현 목록).

    국내 상장 종목은 6자리 코드로, 미국 종목·ETF는 티커로 해석한다(US 레인,
    2026-08-25). 미국은 파케이 보유분만 인정한다 — 데이터 없는 티커를 조용히
    통과시키면 0거래로 끝난다. 한·미 혼합 지정은 엔진이 명시적으로 거절한다.
    """
    try:
        from stock_analysis.symbol_resolver import find_in_text, resolve_by_symbol
    except Exception:  # noqa: BLE001 — 마스터 로드 실패 시 지정 없음으로 강등
        return [], list(refs or [])

    from engine.universe_pit import resolve_us_ref, us_ticker_with_data

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
        # [지역 격리, 2026-08-26] /us 요청(표시 언어 en — 지역이 곧 언어)에서는 한국
        # 종목을 지정할 수 없다 — 국내 해석을 건너뛰어 KR 이름·6자리 코드는 아래 미국
        # registry에서 못 찾으면 unresolved로 보고된다(조용한 소실 아님 — 상류 미해석
        # 안내 채널이 표면화). 미국 종목의 한글명("애플")은 미국 registry가 해석한다.
        if ui_language.get_ui_language() == "en":
            resolved = None
        else:
            resolved = (
                resolve_by_symbol(ref) if _SYMBOL_CODE_RE.match(ref)
                else next((r for r in find_in_text(ref) if not r.overseas), None)
            )
        if resolved is not None and not resolved.overseas:
            if resolved.symbol not in codes:
                codes.append(resolved.symbol)
            continue
        # 국내 ETF — 종목 마스터에는 ETF가 없다. 상품명 **정확 일치**("TIGER 미국S&P500")나 ETF
        # 코드만 ETF 마스터로 푼다(2026-09-21: 적립식의 지정 종목이 ETF면 영영 미해석이었고, 컴파일
        # 결과의 ETF 코드가 수정 턴 왕복에서 "종목으로 인식되지 않아"로 돌아왔다). 부분 일치는
        # 하지 않는다 — "반도체"는 상품 하나가 아니라 테마 키워드(etf_theme)다. /us는 제외(지역 격리).
        if ui_language.get_ui_language() != "en":
            from engine.universe_pit import is_etf_symbol, resolve_single_etf_product

            product = resolve_single_etf_product(ref)
            etf_code = product["symbol"] if product else (ref if is_etf_symbol(ref) else None)
            if etf_code is not None:
                if etf_code not in codes:
                    codes.append(etf_code)
                continue
        # 국내 해석 실패 → 미국 registry 조회(티커·영문명·한글명 정확 일치).
        # find_in_text의 해외 별칭 판정(애플→AAPL)도 데이터 보유 확인 후 인정한다.
        us_ticker = resolve_us_ref(ref)
        if us_ticker is None:
            alias = next((r for r in find_in_text(ref) if r.overseas), None)
            if alias is not None:
                us_ticker = us_ticker_with_data(alias.symbol)
        if us_ticker is not None:
            if us_ticker not in codes:
                codes.append(us_ticker)
        elif ref not in unresolved:
            unresolved.append(ref)
    return codes, unresolved
