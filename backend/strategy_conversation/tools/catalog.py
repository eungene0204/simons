"""도구 카탈로그 — 기존 서비스의 타입드 래퍼(동작 변화 없음).

구현은 전부 기존 모듈에 있다. 여기는 입출력 계약과 등록만 담당한다.
무거운 의존(지식그래프 로딩·엔진 모듈)은 호출 시점에 지연 import한다.
"""

from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict

from strategy_conversation.interpreter.models import StrategyIntent, ValidationReport
from strategy_conversation.tools.base import ToolError, ToolSpec, register


# ── kg_resolve_sector — 지식그래프 시드·학습 개념 → 정본 섹터 ──────────────────
class KgResolveSectorIn(BaseModel):
    text: str


class KgResolveSectorOut(BaseModel):
    sector: Optional[str] = None  # 정본 섹터명, 미해석 시 None


def _kg_resolve_sector(inp: KgResolveSectorIn) -> KgResolveSectorOut:
    from engine.knowledge_graph import resolve_sector_from_text

    return KgResolveSectorOut(sector=resolve_sector_from_text(inp.text))


# ── kg_theme_companies — 테마 관련 상장사(백테스트 대상 제안 뷰, FR-STR-071/072) ──
class KgThemeCompaniesIn(BaseModel):
    text: str


class KgThemeCompaniesOut(BaseModel):
    found: bool
    term: Optional[str] = None
    companies: List[dict] = []
    first_known_date: Optional[str] = None


def _kg_theme_companies(inp: KgThemeCompaniesIn) -> KgThemeCompaniesOut:
    from engine.knowledge_graph import theme_backtest_companies

    hit = theme_backtest_companies(inp.text)
    if not hit:
        return KgThemeCompaniesOut(found=False)
    return KgThemeCompaniesOut(
        found=True,
        term=hit.get("term"),
        companies=hit.get("companies") or [],
        first_known_date=hit.get("first_known_date"),
    )


# ── ground_term — 어휘집→지식그래프→내부 LLM→인터넷 검색 체인(FR-STR-069) ───────
class GroundTermIn(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    text: str
    # 공유 LLM chat(system_prompt, user_msg) -> str — 앱 레이어가 주입하는 런타임
    # 의존성이다(공유 파서+inference lock은 main 소유). planner 노출 스키마가 아니다.
    chat: Any = None


class GroundTermOut(BaseModel):
    sector: Optional[str] = None


def _ground_term(inp: GroundTermIn) -> GroundTermOut:
    if not callable(inp.chat):
        raise ToolError("ground_term은 chat(공유 LLM 호출자) 주입이 필요합니다")
    from engine.term_grounding import resolve_sector

    return GroundTermOut(sector=resolve_sector(inp.text, inp.chat))


# ── classify_universe — 유니버스 표현의 타입 결정(Universe-first, Phase 5) ──────
# 입력은 planner LLM이 원문에서 뽑은 유니버스 표현이다(§ 3-2 지식 조회 — 원문 해석 아님).
_MARKET_CANONICAL = {
    "코스피": "KOSPI", "kospi": "KOSPI", "유가증권": "KOSPI",
    "코스닥": "KOSDAQ", "kosdaq": "KOSDAQ",
    "코스피200": "KOSPI200", "kospi200": "KOSPI200", "대형주": "KOSPI200",
}
_ETF_MARKERS = ("etf", "etn", "상장지수")


class ClassifyUniverseIn(BaseModel):
    text: str


class ClassifyUniverseOut(BaseModel):
    universe_type: str  # MARKET | ETF | SINGLE_STOCK | SECTOR | CONCEPT | NOT_UNIVERSE
    canonical: Optional[str] = None  # MARKET 시장 코드 / SINGLE_STOCK 종목코드 / SECTOR 정본명


def _classify_universe(inp: ClassifyUniverseIn) -> ClassifyUniverseOut:
    from engine.knowledge_graph import catalog_theme_candidates
    from engine.universe_pit import is_narrow_sector_approximation, normalize_sector
    from strategy_conversation.registry.universe_resolver import resolve_symbols

    key = (inp.text or "").replace(" ", "").lower()
    if not key:
        return ClassifyUniverseOut(universe_type="CONCEPT")
    if key in _MARKET_CANONICAL:
        return ClassifyUniverseOut(universe_type="MARKET", canonical=_MARKET_CANONICAL[key])
    if any(marker in key for marker in _ETF_MARKERS):
        return ClassifyUniverseOut(universe_type="ETF")
    symbol_codes, unresolved = resolve_symbols([inp.text])
    if symbol_codes and not unresolved:
        return ClassifyUniverseOut(universe_type="SINGLE_STOCK", canonical=symbol_codes[0])
    sector = normalize_sector(inp.text)
    # 표현이 정본 섹터명 밖으로 나가는 근사(예: '태양광'→'에너지/원자력', 원자력·풍력·석유
    # 등을 한 섹터로 묶은 MAPPING_RULES 버킷에서 파생)일 때만, 더 구체적인 카탈로그 테마가
    # 있는지 먼저 확인한다 — 있으면 근사 섹터보다 테마 판정(되묻기 체인)을 우선한다.
    # '은행'→'은행/금융지주'처럼 표현이 정본명 안에 그대로 들어있는 이름 표기 차이는
    # 대상이 아니다(늘 그대로 섹터 확정). 매번 어휘집에서 개별 용어를 손으로 빼는 대응
    # (2026-07-27 'AI/인공지능')을 구조적으로 대체한다.
    if sector and is_narrow_sector_approximation(inp.text) and catalog_theme_candidates(inp.text):
        return ClassifyUniverseOut(universe_type="CONCEPT")
    if sector:
        return ClassifyUniverseOut(universe_type="SECTOR", canonical=sector)
    # 지표 조건 구가 유니버스 표현으로 넘어온 오라우팅 백스톱 — CONCEPT으로 판정하면
    # planner가 KG 조회·검색 학습 체인을 돌다 턴 예산을 소진한다(2026-08-03
    # '당기순이익과, 영업이익률이 높은 종목' 실측 10.7초). 입력은 planner LLM이 뽑은
    # 표현이므로 결정론 대조가 계약에 맞는다.
    from strategy_conversation.registry.indicator_registry import contains_factor_term

    if contains_factor_term(inp.text):
        return ClassifyUniverseOut(universe_type="NOT_UNIVERSE")
    return ClassifyUniverseOut(universe_type="CONCEPT")


# ── list_concept_candidates — CONCEPT 표현의 카탈로그 테마 후보(되묻기 chips 재료) ──
class ConceptCandidatesIn(BaseModel):
    text: str


class ConceptCandidatesOut(BaseModel):
    candidates: List[dict] = []  # {term: 카탈로그 정본 표기, companies: 상장사 수}


def _list_concept_candidates(inp: ConceptCandidatesIn) -> ConceptCandidatesOut:
    from engine.knowledge_graph import catalog_theme_candidates

    return ConceptCandidatesOut(candidates=catalog_theme_candidates(inp.text))


# ── resolve_universe — 업종/테마 표현·종목 표기 → 정본 값(조용한 소실 금지) ──────
class ResolveUniverseIn(BaseModel):
    sectors: List[str] = []
    symbols: List[str] = []


class ResolveUniverseOut(BaseModel):
    sector_value: Any = None  # None | str | list[str] — sector 필드 계약(FR-STR-066 ⑦)
    unresolved_sectors: List[str] = []
    symbol_codes: List[str] = []
    unresolved_symbols: List[str] = []


def _resolve_universe(inp: ResolveUniverseIn) -> ResolveUniverseOut:
    from strategy_conversation.registry.universe_resolver import (
        resolve_sectors,
        resolve_symbols,
    )

    sector_value, unresolved_sectors = resolve_sectors(inp.sectors)
    symbol_codes, unresolved_symbols = resolve_symbols(inp.symbols)
    return ResolveUniverseOut(
        sector_value=sector_value,
        unresolved_sectors=unresolved_sectors,
        symbol_codes=symbol_codes,
        unresolved_symbols=unresolved_symbols,
    )


# ── lookup_capabilities — 플랫폼이 표현 가능한 값의 정본 목록 ───────────────────
class LookupCapabilitiesIn(BaseModel):
    pass


class LookupCapabilitiesOut(BaseModel):
    markets: List[str]
    rebalance_frequencies: List[str]
    weightings: List[str]
    backtest_periods: List[str]
    max_positions_range: List[int]


def _lookup_capabilities(inp: LookupCapabilitiesIn) -> LookupCapabilitiesOut:
    from strategy_conversation.registry.capability_registry import (
        MAX_POSITIONS_RANGE,
        SUPPORTED_BACKTEST_PERIODS,
        SUPPORTED_MARKETS,
        SUPPORTED_REBALANCE_FREQUENCIES,
        SUPPORTED_WEIGHTINGS,
    )

    return LookupCapabilitiesOut(
        markets=list(SUPPORTED_MARKETS),
        rebalance_frequencies=list(SUPPORTED_REBALANCE_FREQUENCIES),
        weightings=list(SUPPORTED_WEIGHTINGS),
        backtest_periods=list(SUPPORTED_BACKTEST_PERIODS),
        max_positions_range=list(MAX_POSITIONS_RANGE),
    )


# ── validate_intent — Schema 통과한 StrategyIntent의 Domain 검증 ────────────────
class ValidateIntentIn(BaseModel):
    intent: StrategyIntent


class ValidateIntentOut(BaseModel):
    intent: StrategyIntent
    report: ValidationReport


def _validate_intent(inp: ValidateIntentIn) -> ValidateIntentOut:
    from strategy_conversation.validation.pipeline import run_validation

    validated, report = run_validation(inp.intent)
    return ValidateIntentOut(intent=validated, report=report)


# ── compile_strategy — 검증된 intent → ParsedStrategy(부분 컴파일 포함) ──────────
class CompileStrategyIn(BaseModel):
    intent: StrategyIntent
    report: ValidationReport
    # 수정 경로 라운드트립은 prev.description을 넘긴다(None 가능) — 기존 호출 계약 유지
    user_input: Optional[str] = None
    partial: bool = False


class CompileStrategyOut(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    parsed: Any  # engine.nl_parser.ParsedStrategy — 엔진 모듈 순환 의존 회피로 Any
    dropped: List[str] = []
    # 값 미정으로 제외된 조건의 구조화 목록 [{"role","label","source_text"}] —
    # 프론트 요약이 "이해했지만 값 대기"를 표시할 근거(dropped 라벨만으론 불가).
    pending_conditions: List[dict] = []


def _compile_strategy(inp: CompileStrategyIn) -> CompileStrategyOut:
    from strategy_conversation.compiler.strategy_compiler import (
        compile_partial,
        compile_strategy,
    )

    if inp.partial:
        parsed, dropped, pending = compile_partial(inp.intent, inp.report, inp.user_input)
        return CompileStrategyOut(parsed=parsed, dropped=dropped, pending_conditions=pending)
    return CompileStrategyOut(
        parsed=compile_strategy(inp.intent, inp.report, inp.user_input), dropped=[]
    )


for _spec in (
    ToolSpec("kg_resolve_sector", "지식그래프에서 테마·개념 표현의 정본 섹터를 조회한다",
             KgResolveSectorIn, KgResolveSectorOut, _kg_resolve_sector, deterministic=True),
    ToolSpec("kg_theme_companies", "테마 표현의 관련 상장사 목록(백테스트 대상 제안 뷰)을 조회한다",
             KgThemeCompaniesIn, KgThemeCompaniesOut, _kg_theme_companies, deterministic=True),
    ToolSpec("classify_universe", "유니버스 표현의 타입(MARKET/ETF/SINGLE_STOCK/SECTOR/CONCEPT/NOT_UNIVERSE)을 결정한다",
             ClassifyUniverseIn, ClassifyUniverseOut, _classify_universe, deterministic=True),
    ToolSpec("list_concept_candidates", "CONCEPT 표현의 카탈로그 테마 후보 목록(범위 되묻기 선택지)을 조회한다",
             ConceptCandidatesIn, ConceptCandidatesOut, _list_concept_candidates, deterministic=True),
    ToolSpec("ground_term", "미지 테마 용어를 인터넷 검색으로 학습해 정본 섹터로 해석한다(어휘집 캐시)",
             GroundTermIn, GroundTermOut, _ground_term, deterministic=False),
    ToolSpec("resolve_universe", "업종/테마 표현과 종목 표기를 정본 섹터·종목코드로 해석한다",
             ResolveUniverseIn, ResolveUniverseOut, _resolve_universe, deterministic=True),
    ToolSpec("lookup_capabilities", "플랫폼이 지원하는 시장·리밸런싱·비중·기간의 정본 목록을 조회한다",
             LookupCapabilitiesIn, LookupCapabilitiesOut, _lookup_capabilities, deterministic=True),
    ToolSpec("validate_intent", "StrategyIntent의 도메인 검증(지원 여부·범위·충돌·완결성)을 수행한다",
             ValidateIntentIn, ValidateIntentOut, _validate_intent, deterministic=True),
    ToolSpec("compile_strategy", "검증된 StrategyIntent를 ParsedStrategy로 컴파일한다(부분 컴파일 포함)",
             CompileStrategyIn, CompileStrategyOut, _compile_strategy, deterministic=True),
):
    register(_spec)
