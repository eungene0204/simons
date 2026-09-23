"""IndicatorRegistry — 지표 지원 여부의 단일 진실 소스(시스템 계약).

LLM에게 금융 용어를 가르치는 사전이 아니다. LLM은 지표명을 자유롭게 추출하고,
실제 지원 여부·canonical ID·허용 연산자·파라미터 범위는 이 Registry가 최종
판정한다. 항목은 백테스트 엔진의 실지원(FundamentalFilter.metric,
TechnicalSignal.indicator Literal)과 1:1로 유지해야 한다 — 엔진에 지표를
추가/제거하면 여기도 함께 갱신할 것.

지원 상태 3단계:
  SUPPORTED           — 엔진 연결 + 전체 기간 데이터
  PARTIALLY_SUPPORTED — 엔진 연결 + 일부 종목/기간 데이터(실측 커버리지는
                        engine/data_coverage.py 런타임 로그가 정본)
  UNSUPPORTED         — LLM이 개념은 이해하지만 엔진/데이터 파이프라인 미지원
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import re
from typing import Dict, Iterable, List, Literal, Optional, Tuple

SupportStatus = Literal["SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED"]

_COMPARISON_OPS = ("<", "<=", ">", ">=")


@dataclass(frozen=True)
class ParamSpec:
    default: Optional[float] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    required: bool = False


@dataclass(frozen=True)
class IndicatorSpec:
    id: str                         # canonical ID (예: fundamental.per)
    display_name: str
    category: str                   # valuation/profitability/stability/growth/technical/...
    supported: SupportStatus
    data_source: str                # financial_statements / ohlcv / ai_model / none
    value_type: Optional[str] = None  # percent / ratio / 억원 / point / event
    allowed_operators: Tuple[str, ...] = ()
    parameters: Dict[str, ParamSpec] = field(default_factory=dict)
    value_range: Optional[Tuple[float, float]] = None  # 임계값(value) 유효 범위
    recommended_value: Optional[float] = None          # 되묻기 시 제시할 시작값
    engine_binding: Optional[Tuple[str, str]] = None   # (종류, 엔진 필드값)
    available_from: Optional[str] = None               # 데이터 시작일(알려진 경우)
    partial_data: bool = False                         # 종목/기간별 커버리지 편차 존재
    # 기능은 완성됐지만 **데이터 적재가 끝나지 않은** 지표 — 사용자에게 '준비 중'으로 알리고
    # 조건·랭킹에서 뺀다(그대로 두면 fail-closed로 거래 0건 백테스트가 나간다).
    # 값은 아래 DATA_PENDING_METRICS가 정본이며, 적재가 끝나면 그 집합에서 지우는 것으로 켠다.
    data_pending: bool = False
    alternatives: Tuple[str, ...] = ()                 # UNSUPPORTED 시 제안 가능한 대체 지표
    notes: Optional[str] = None


def _fundamental(
    metric: str, name: str, category: str, value_type: str,
    recommended: Optional[float] = None, value_range: Optional[Tuple[float, float]] = None,
    notes: Optional[str] = None, parameters: Optional[Dict[str, "ParamSpec"]] = None,
) -> IndicatorSpec:
    # 재무 데이터는 KIS 백필 기반으로 종목·기간별 커버리지 편차가 있다 —
    # 정확한 결측은 데이터 커버리지 로그(FR-BT-016)가 실측으로 알린다.
    return IndicatorSpec(
        id=f"fundamental.{metric}",
        display_name=name,
        category=category,
        supported="PARTIALLY_SUPPORTED",
        data_source="financial_statements",
        value_type=value_type,
        allowed_operators=_COMPARISON_OPS,
        value_range=value_range,
        recommended_value=recommended,
        engine_binding=("fundamental_filter", metric),
        partial_data=True,
        notes=notes,
        **({"parameters": parameters} if parameters else {}),
    )


def _technical(
    indicator: str, name: str, value_type: Optional[str],
    operators: Tuple[str, ...], params: Dict[str, ParamSpec],
    value_range: Optional[Tuple[float, float]] = None,
    recommended: Optional[float] = None, notes: Optional[str] = None,
) -> IndicatorSpec:
    return IndicatorSpec(
        id=f"technical.{indicator}",
        display_name=name,
        category="technical",
        supported="SUPPORTED",
        data_source="ohlcv",
        value_type=value_type,
        allowed_operators=operators,
        parameters=params,
        value_range=value_range,
        recommended_value=recommended,
        engine_binding=("technical_signal", indicator),
        notes=notes,
    )


def _unsupported(
    key: str, name: str, category: str,
    alternatives: Tuple[str, ...] = (), notes: Optional[str] = None,
) -> IndicatorSpec:
    return IndicatorSpec(
        id=f"unsupported.{key}",
        display_name=name,
        category=category,
        supported="UNSUPPORTED",
        data_source="none",
        alternatives=alternatives,
        notes=notes,
    )


# ── 데이터 적재 대기 지표(2026-09-19 신설, 사용자 결정 09-20) ──────────────────
# 지표 정의·엔진 배선·해석은 끝났고 **과거 데이터만 아직 없는** 항목. DART 재수집
# (scripts/backfill_roic_fcf_margin.py)이 운영 데이터까지 반영되면 이 집합에서 지운다 —
# 그 순간 조건·랭킹·칩이 모두 살아난다(다른 곳에 사본을 두지 않는 이유).
# 유료라서 못 하는 것이 아니다(DART 오픈API는 무료, 일일 호출 한도만 있음) — 계획이 없는
# 개념(실적 추정치 등)은 여기가 아니라 UNSUPPORTED로 남긴다: 지키지 못할 약속 금지.
#
# 2026-09-21 **비웠다**: ROIC·FCF 마진 백필 완료(3,001/3,001종목)와 운영 반영이 끝났다 —
# 운영 parquet에 ROIC 2,423·FCF 마진 2,617종목의 값이 있고, 쓰기 전후 전수 대조에서 기존
# 값 변화 0을 확인했다. 값이 없는 종목은 다른 재무 지표와 같은 부분 커버리지(PARTIALLY_
# SUPPORTED·partial_data)로 다뤄져 그날 후보에서 빠진다.
DATA_PENDING_METRICS: frozenset = frozenset()


_SPECS: Tuple[IndicatorSpec, ...] = (
    # ── 재무 지표 (엔진 FundamentalFilter.metric과 1:1) ──────────────────────
    _fundamental("per", "PER(주가수익비율)", "valuation", "ratio", recommended=10, value_range=(0, 1000)),
    _fundamental("pbr", "PBR(주가순자산비율)", "valuation", "ratio", recommended=1, value_range=(0, 100)),
    _fundamental("psr", "PSR(주가매출비율)", "valuation", "ratio", recommended=1, value_range=(0, 100)),
    _fundamental("pcr", "PCR(주가현금흐름비율)", "valuation", "ratio", recommended=10, value_range=(0, 500),
                 notes="시가총액/영업활동현금흐름. 영업현금흐름<=0인 연도는 값이 없을 수 있음"),
    _fundamental("ev_ebitda", "EV/EBITDA", "valuation", "ratio", recommended=8, value_range=(0, 500)),
    _fundamental("ev_ebit", "EV/EBIT", "valuation", "ratio", recommended=10, value_range=(0, 500),
                 notes="EBITDA<=0인 연도는 EV 자체를 역산할 수 없어 값이 없을 수 있음"),
    _fundamental("roe_or_gpa", "ROE(자기자본이익률)", "profitability", "percent", recommended=15, value_range=(-100, 200)),
    _fundamental("roa", "ROA(총자본순이익률)", "profitability", "percent", recommended=5, value_range=(-100, 100)),
    _fundamental("debt_ratio", "부채비율", "stability", "percent", recommended=100, value_range=(0, 10000)),
    _fundamental("current_ratio", "유동비율", "stability", "percent", recommended=150, value_range=(0, 10000)),
    _fundamental("quick_ratio", "당좌비율", "stability", "percent", recommended=100, value_range=(0, 10000)),
    _fundamental("reserve_ratio", "유보율", "stability", "percent", recommended=500, value_range=(0, 100000)),
    _fundamental("net_margin", "순이익률", "profitability", "percent", recommended=5, value_range=(-100, 100)),
    _fundamental("gross_margin", "매출총이익률", "profitability", "percent", recommended=20, value_range=(-100, 100)),
    _fundamental("operating_margin", "영업이익률", "profitability", "percent", recommended=10, value_range=(-100, 100)),
    _fundamental("revenue_growth", "매출액증가율", "growth", "percent", recommended=10, value_range=(-100, 1000)),
    _fundamental("operating_income_growth", "영업이익증가율", "growth", "percent", recommended=10, value_range=(-1000, 1000)),
    _fundamental("net_income_growth", "순이익증가율", "growth", "percent", recommended=10, value_range=(-1000, 1000)),
    _fundamental("eps_growth", "EPS증가율", "growth", "percent", recommended=10, value_range=(-1000, 1000),
                 notes="적자↔흑자 전환기에는 증가율 대신 상태코드(턴어라운드 등)로 표현될 수 있음"),
    _fundamental("ebitda_growth", "EBITDA증가율", "growth", "percent", recommended=10, value_range=(-1000, 1000),
                 notes="적자↔흑자 전환기에는 증가율 대신 상태코드(턴어라운드 등)로 표현될 수 있음"),
    _fundamental("ocf_growth", "영업활동현금흐름증가율", "growth", "percent", recommended=10, value_range=(-1000, 1000),
                 notes="적자↔흑자 전환기에는 증가율 대신 상태코드(턴어라운드 등)로 표현될 수 있음"),
    _fundamental("fcf_growth", "잉여현금흐름증가율", "growth", "percent", recommended=10, value_range=(-1000, 1000),
                 notes="적자↔흑자 전환기에는 증가율 대신 상태코드(턴어라운드 등)로 표현될 수 있음"),
    # v16.14(2026-09-19) 지원 승격 — DART 재무상태표·손익계산서 원재료로 계산(fundamental_fetcher).
    _fundamental("roic", "ROIC(투하자본이익률)", "profitability", "percent", recommended=10,
                 value_range=(-100, 200),
                 notes="영업이익×(1−유효세율) ÷ (자본총계+이자부부채−현금). 연간 결산 기준. "
                       "ROA·ROE로 바꿔 넣지 말 것(다른 지표)"),
    _fundamental("fcf_margin", "FCF 마진(잉여현금흐름÷매출액)", "profitability", "percent", recommended=5,
                 value_range=(-500, 500),
                 notes="잉여현금흐름(영업현금흐름−CAPEX) ÷ 매출액. 연간 결산 기준. "
                       "'FCF 증가율'(fcf_growth)·'FCF 수익률'(fcf_yield, 시총 대비)과 다른 지표"),
    # v16.15(2026-09-20) 지원 승격 — 잉여현금흐름(raw)과 일별 시가총액이 parquet에 이미 있어
    # 백필 없이 런타임 계산된다(fundamental_fetcher.recompute_fcf_yield, PCR과 같은 자리).
    _fundamental("fcf_yield", "FCF 수익률(잉여현금흐름÷시가총액)", "valuation", "percent", recommended=5,
                 value_range=(-100, 100),
                 notes="잉여현금흐름(영업현금흐름−CAPEX, 최근 연간 결산) ÷ 시가총액(일별). "
                       "'잉여현금흐름수익률'·'FCF Yield'가 이것. 'FCF 마진'(매출 대비)·'FCF 증가율'과 다른 지표"),
    _fundamental("market_cap", "시가총액", "size", "억원", recommended=5000, value_range=(0, 10_000_000)),
    _fundamental("trading_value", "일평균거래대금", "liquidity", "억원", recommended=10, value_range=(0, 1_000_000),
                 notes="유동성 스크리닝용 기본값. '거래대금 N억 이상 종목만/으로 거른' 처럼 "
                       "**종목 선정 기준**이면 technical.trading_value가 아니라 이것. "
                       "'일평균·최근 N일 평균 거래대금 N억'처럼 **기간 평균의 금액 임계**면 항상 이것이다 "
                       "(technical은 당일 거래대금만 본다). 억원 금액 없이 '거래대금이 N일 평균보다 "
                       "높은'처럼 **자기 평균과 비교**하면 technical.trading_value_ratio. "
                       "평균 기간을 말했으면('최근 60일 평균') parameters.period에 담는다(없으면 20일)",
                 parameters={"period": ParamSpec(minimum=1, maximum=250)}),
    _fundamental("dividend_yield", "배당수익률", "dividend", "percent", recommended=3, value_range=(0, 100)),
    _fundamental("payout_rate", "배당성향", "dividend", "percent", recommended=30, value_range=(0, 1000)),
    _fundamental("dividend_growth", "배당성장률", "dividend", "percent", recommended=5, value_range=(-100, 1000)),
    # v16.15(2026-09-20) — ex-date별 주당배당(dividends) 달력 연도 합으로 계산(engine.dividends).
    _fundamental("dividend_streak_years", "연속 배당 연수", "dividend", "년", recommended=3,
                 value_range=(0, 50),
                 notes="직전 달력 연도부터 끊기지 않고 현금배당을 지급한 연도 수(진행 중인 올해 제외). "
                       "'N년 연속 배당(지급)'·'N년 이상 배당을 이어온' = >= N. 배당수익률·배당성향·배당성장률과 다른 지표"),
    # v16.25(2026-09-23) — 총자산(자본총계×(1+부채비율/100))·순이익·영업현금흐름이 parquet에 있어 백필 없이
    # 런타임 계산된다(data_resolver._resolve_computable_ratios). 퀀트 퀄리티 팩터의 표준 정의(자산성장 이상현상·
    # 발생액 이상현상) — 둘 다 **낮을수록** 선호.
    _fundamental("asset_growth", "자산성장률(총자산 전년 대비)", "growth", "percent", recommended=20,
                 value_range=(-100, 1000),
                 notes="총자산의 전년 대비 증가율. '자산성장률이 낮은'·'자산이 급증하지 않은' 기업 = <= N. "
                       "매출·이익 증가율과 다른 지표(자산 규모의 성장)"),
    _fundamental("accruals_ratio", "발생액 비율((순이익−영업현금흐름)÷총자산)", "quality", "percent", recommended=5,
                 value_range=(-100, 100),
                 notes="(당기순이익 − 영업활동현금흐름) ÷ 총자산. 낮을수록 이익이 현금으로 뒷받침됨(이익의 질). "
                       "'발생액이 낮은'·'현금흐름 대비 이익이 과대하지 않은' = <= N"),
    # v16.26(2026-09-23) — 피오트로스키 F-score(0~9점). 9항목 재료(ROA·영업현금흐름·순이익·부채비율·유동비율·
    # 매출총이익률·매출·총자산·시가총액÷종가)가 parquet에 있어 런타임 계산(fundamental_fetcher.recompute_f_score).
    _fundamental("f_score", "F-score(피오트로스키 9항목 점수)", "quality", "점", recommended=7,
                 value_range=(0, 9),
                 notes="수익성(ROA>0·영업CF>0·ΔROA>0·영업CF>순이익)+안정성(Δ부채비율<0·Δ유동비율>0·신주 발행 없음)"
                       "+효율성(Δ매출총이익률>0·Δ자산회전율>0) 각 1점, 0~9. 'F-score 7점 이상'·'피오트로스키 점수가 높은'. "
                       "알트만 Z-score와 다른 지표(그쪽은 미지원)"),
    # v16.27(2026-09-23) — NCAV(DART 유동자산·부채총계 백필 → parquet ncav)·분기 손익 3항목(data/quarterly-earnings
    # 수집 확장 → 런타임 성장률). 수집이 끝나지 않은 종목은 값이 없어 조건에서 빠진다(fail-closed).
    _fundamental("ncav_ratio", "시가총액/NCAV 비율(시총÷순유동자산)", "valuation", "percent", recommended=67,
                 value_range=(0, 100000),
                 notes="시가총액 ÷ (유동자산 − 부채총계) × 100. 그레이엄 NCAV 전략 '시총이 순유동자산의 2/3 이하' = <= 67. "
                       "NCAV가 0 이하인 회사는 값이 없다. PBR·PCR과 다른 지표"),
    _fundamental("revenue_growth_qoq", "매출 분기성장률(QoQ)", "growth", "percent", recommended=10, value_range=(-1000, 10000),
                 notes="분기 손익계산서 3개월 값의 직전 분기 대비 증가율. 연간 증가율(revenue_growth)과 다른 지표 — "
                       "'분기'·'QoQ·전분기'를 말했을 때만. 기준 분기가 적자·0이면 값이 없다"),
    _fundamental("revenue_growth_yoy", "매출 분기성장률(YoY)", "growth", "percent", recommended=10, value_range=(-1000, 10000),
                 notes="분기 손익계산서 3개월 값의 전년 동기 대비 증가율. 연간 증가율(revenue_growth)과 다른 지표 — "
                       "'분기'·'YoY·전년 동기 분기'를 말했을 때만. 기준 분기가 적자·0이면 값이 없다"),
    _fundamental("operating_income_growth_qoq", "영업이익 분기성장률(QoQ)", "growth", "percent", recommended=10, value_range=(-1000, 10000),
                 notes="분기 손익계산서 3개월 값의 직전 분기 대비 증가율. 연간 증가율(operating_income_growth)과 다른 지표 — "
                       "'분기'·'QoQ·전분기'를 말했을 때만. 기준 분기가 적자·0이면 값이 없다"),
    _fundamental("operating_income_growth_yoy", "영업이익 분기성장률(YoY)", "growth", "percent", recommended=10, value_range=(-1000, 10000),
                 notes="분기 손익계산서 3개월 값의 전년 동기 대비 증가율. 연간 증가율(operating_income_growth)과 다른 지표 — "
                       "'분기'·'YoY·전년 동기 분기'를 말했을 때만. 기준 분기가 적자·0이면 값이 없다"),
    _fundamental("net_income_growth_qoq", "순이익 분기성장률(QoQ)", "growth", "percent", recommended=10, value_range=(-1000, 10000),
                 notes="분기 손익계산서 3개월 값의 직전 분기 대비 증가율. 연간 증가율(net_income_growth)과 다른 지표 — "
                       "'분기'·'QoQ·전분기'를 말했을 때만. 기준 분기가 적자·0이면 값이 없다"),
    _fundamental("net_income_growth_yoy", "순이익 분기성장률(YoY)", "growth", "percent", recommended=10, value_range=(-1000, 10000),
                 notes="분기 손익계산서 3개월 값의 전년 동기 대비 증가율. 연간 증가율(net_income_growth)과 다른 지표 — "
                       "'분기'·'YoY·전년 동기 분기'를 말했을 때만. 기준 분기가 적자·0이면 값이 없다"),
    _fundamental("eps", "EPS(주당순이익)", "profitability", "원", recommended=0,
                 value_range=(-1_000_000, 10_000_000),
                 notes="흑자 기업=eps>0, 적자 기업=eps<0 부호 필터로 주로 사용(최근 연간 결산 기준)"),
    _fundamental("ebit", "영업이익", "profitability", "억원", recommended=0,
                 value_range=(-10_000_000, 10_000_000),
                 notes="영업이익 흑자=ebit>0, 영업이익 적자=ebit<0 부호 필터로 주로 사용(최근 연간 결산 기준)"),
    _fundamental("net_income", "당기순이익", "profitability", "억원", recommended=100,
                 value_range=(-10_000_000, 10_000_000),
                 notes="당기순이익 절대 금액(억원, 최근 연간 결산 기준). **비지배지분이 포함된 "
                       "연결 전체** 당기순이익이다 — 사용자가 '지배주주'를 명시하면 "
                       "owner_net_income. 흑자/적자 부호 필터는 eps를 사용"),
    _fundamental("owner_net_income", "지배주주순이익", "profitability", "억원", recommended=100,
                 value_range=(-10_000_000, 10_000_000),
                 notes="지배기업 소유주에게 귀속되는 당기순이익 절대 금액(억원, 최근 연간 결산 "
                       "기준). '지배주주순이익·지배주주지분 순이익·연결지배순이익'처럼 귀속 주체를 "
                       "밝힌 표현일 때만 이것을 쓰고, 그냥 '당기순이익'이면 net_income"),
    _fundamental("operating_cf_amount", "영업활동현금흐름", "cashflow", "억원", recommended=100,
                 value_range=(-10_000_000, 10_000_000),
                 notes="영업활동으로 벌어들인 현금 절대 금액(억원, 최근 연간 결산 기준). "
                       "본업 현금창출이 흑자=operating_cf_amount>0. 증가율은 ocf_growth"),
    _fundamental("investing_cf_amount", "투자활동현금흐름", "cashflow", "억원", recommended=0,
                 value_range=(-10_000_000, 10_000_000),
                 notes="투자활동 순현금흐름 절대 금액(억원, 최근 연간 결산 기준). 설비·자산을 "
                       "취득하면 음수라 통상 <0 — 부호가 살아 있는 값을 그대로 비교한다"),
    _fundamental("financing_cf_amount", "재무활동현금흐름", "cashflow", "억원", recommended=0,
                 value_range=(-10_000_000, 10_000_000),
                 notes="재무활동 순현금흐름 절대 금액(억원, 최근 연간 결산 기준). 차입 상환·배당 "
                       "지급이 많으면 음수, 자금을 조달하면 양수"),

    # ── 기술적 지표 (엔진 TechnicalSignal.indicator와 1:1) ───────────────────
    _technical("ma_crossover", "이동평균 크로스오버", "event",
               ("crosses_above", "crosses_below", ">", "<"),
               {"short_period": ParamSpec(default=20, minimum=1, maximum=250, required=True),
                "long_period": ParamSpec(default=60, minimum=3, maximum=500, required=True)},
               notes="crosses_above=골든크로스, crosses_below=데드크로스. "
                     "short_period=1은 '가격(종가) 대비 N일선' 정본 표기 — "
                     "'종가가 20일선 이탈'=short 1·long 20·crosses_below "
                     "(엔진 close_1_sma=종가, 레거시 파서와 동일 표기). "
                     ">/< 는 EMA와 같은 **머무는 상태** 필터(mode above/below) — "
                     "'종가가 60일선 위에 있는 동안'=short 1·long 60·'>'. 상태를 "
                     "교차로 옮기면 조건이 교차 당일 하루로 좁아진다(2026-09-10)"),
    _technical("ema", "지수이동평균(EMA)", "event",
               ("crosses_above", "crosses_below", ">", "<"),
               {"short_period": ParamSpec(default=20, minimum=1, maximum=250),
                "long_period": ParamSpec(default=60, minimum=3, maximum=500)},
               notes="'20일선이 60일선 위로 올라서면'처럼 **교차 시점**이면 "
                     "crosses_above/crosses_below. >/< 는 **머무는 상태** 필터"
                     "(mode above/below — 기간이 둘이면 두 EMA의 정배열/역배열, "
                     "하나면 가격 vs EMA). short_period=1은 ma_crossover와 같은 "
                     "'가격(종가) 대비 N일 EMA' 정본 표기 — 최소값 2는 종가 표기를 "
                     "검증 오류로 만들어 조용한 부분 컴파일을 냈다(2026-08-18)"),
    _technical("rsi", "RSI", "point", _COMPARISON_OPS,
               {"period": ParamSpec(default=14, minimum=2, maximum=250)},
               value_range=(0, 100), recommended=30),
    _technical("macd", "MACD", "event",
               ("crosses_above", "crosses_below"),
               {},
               notes="엔진은 fast/slow/signal 기간 커스텀을 지원하지 않음(12/26/9 고정). "
                     "crosses_above/below=시그널선 교차"),
    _technical("bollinger_bands", "볼린저 밴드", "event",
               ("crosses_above", "crosses_below"),
               {"period": ParamSpec(default=20, minimum=5, maximum=250)}),
    _technical("breakout", "신고가 돌파", "event", ("crosses_above",),
               {"lookback_period": ParamSpec(default=60, minimum=5, maximum=500, required=True)}),
    # 캔들 패턴(엔진 v16.29) — 잎마다 패턴 하나. 엔진 조건 id는 candle_pattern+pattern 파라미터(컨버터가 옮긴다).
    _technical("candle_hammer", "망치형 캔들 패턴", "event", (), {},
               notes="캔들 패턴 — 완성 봉에 신호(연산자·값 없음). 주봉·월봉은 parameters.timeframe"),
    _technical("candle_hanging_man", "교수형 캔들 패턴", "event", (), {},
               notes="캔들 패턴 — 완성 봉에 신호(연산자·값 없음). 주봉·월봉은 parameters.timeframe"),
    _technical("candle_inverted_hammer", "역망치형 캔들 패턴", "event", (), {},
               notes="캔들 패턴 — 완성 봉에 신호(연산자·값 없음). 주봉·월봉은 parameters.timeframe"),
    _technical("candle_shooting_star", "유성형 캔들 패턴", "event", (), {},
               notes="캔들 패턴 — 완성 봉에 신호(연산자·값 없음). 주봉·월봉은 parameters.timeframe"),
    _technical("candle_doji", "도지 캔들 패턴", "event", (), {},
               notes="캔들 패턴 — 완성 봉에 신호(연산자·값 없음). 주봉·월봉은 parameters.timeframe"),
    _technical("candle_bullish_engulfing", "상승 장악형 캔들 패턴", "event", (), {},
               notes="캔들 패턴 — 완성 봉에 신호(연산자·값 없음). 주봉·월봉은 parameters.timeframe"),
    _technical("candle_bearish_engulfing", "하락 장악형 캔들 패턴", "event", (), {},
               notes="캔들 패턴 — 완성 봉에 신호(연산자·값 없음). 주봉·월봉은 parameters.timeframe"),
    _technical("candle_piercing_line", "관통형 캔들 패턴", "event", (), {},
               notes="캔들 패턴 — 완성 봉에 신호(연산자·값 없음). 주봉·월봉은 parameters.timeframe"),
    _technical("candle_dark_cloud_cover", "먹구름형 캔들 패턴", "event", (), {},
               notes="캔들 패턴 — 완성 봉에 신호(연산자·값 없음). 주봉·월봉은 parameters.timeframe"),
    _technical("candle_morning_star", "샛별형 캔들 패턴", "event", (), {},
               notes="캔들 패턴 — 완성 봉에 신호(연산자·값 없음). 주봉·월봉은 parameters.timeframe"),
    _technical("candle_evening_star", "저녁별형 캔들 패턴", "event", (), {},
               notes="캔들 패턴 — 완성 봉에 신호(연산자·값 없음). 주봉·월봉은 parameters.timeframe"),
    _technical("candle_three_white_soldiers", "적삼병 캔들 패턴", "event", (), {},
               notes="캔들 패턴 — 완성 봉에 신호(연산자·값 없음). 주봉·월봉은 parameters.timeframe"),
    _technical("candle_three_black_crows", "흑삼병 캔들 패턴", "event", (), {},
               notes="캔들 패턴 — 완성 봉에 신호(연산자·값 없음). 주봉·월봉은 parameters.timeframe"),
    _technical("volume_spike", "거래량 급증(OBV)", "event", ("crosses_above",),
               {"period": ParamSpec(default=20, minimum=2, maximum=250)},
               notes="OBV 크로스오버 기반 — 배수 없이 '거래량이 급증/늘어난/터진'이라고만 말했을 때. "
                     "'평소보다 N배'처럼 배수를 말했으면 technical.volume_ratio(value=배수)"),
    _technical("volume_ratio", "거래량 배수(평균 대비)", "ratio", _COMPARISON_OPS,
               {"period": ParamSpec(default=20, minimum=2, maximum=250)},
               value_range=(0.1, 100), recommended=2,
               notes="당일 거래량 ÷ 직전 N일 평균 거래량(배). '평소보다 3배'·'20일 평균의 1.5배 이상' "
                     "→ operator \">=\", value=3/1.5, 평균 기간을 말했으면 parameters.period=20. "
                     "배수를 unsupported_features로 보내지 마세요"),
    _technical("trading_value_ratio", "거래대금 배수(평균 대비)", "ratio", _COMPARISON_OPS,
               {"period": ParamSpec(default=20, minimum=2, maximum=250)},
               value_range=(0.1, 100), recommended=1,
               notes="당일 거래대금 ÷ 직전 N일 평균 거래대금(배). '거래대금이 30일 평균보다 높은' → "
                     "operator \">\", value=1, parameters.period=30. '20일 평균의 2배 이상' → \">=\", value=2. "
                     "억원 금액 임계('거래대금 100억 이상')는 이것이 아니라 trading_value"),
    _technical("stochastic", "스토캐스틱", "point", _COMPARISON_OPS,
               {"period": ParamSpec(default=14, minimum=2, maximum=250)},
               value_range=(0, 100), recommended=20),
    _technical("cci", "CCI", "point", _COMPARISON_OPS,
               {"period": ParamSpec(default=20, minimum=2, maximum=250)},
               value_range=(-500, 500), recommended=-100),
    _technical("adx", "ADX", "point", _COMPARISON_OPS,
               {"period": ParamSpec(default=14, minimum=2, maximum=250)},
               value_range=(0, 100), recommended=25),
    _technical("williams_r", "Williams %R", "point", _COMPARISON_OPS,
               {"period": ParamSpec(default=14, minimum=2, maximum=250)},
               value_range=(-100, 0), recommended=-80),
    _technical("mfi", "MFI(자금흐름지표)", "point", _COMPARISON_OPS,
               {"period": ParamSpec(default=14, minimum=2, maximum=250)},
               value_range=(0, 100), recommended=20),
    _technical("roc", "ROC(변화율/모멘텀)", "percent", _COMPARISON_OPS,
               {"period": ParamSpec(default=20, minimum=2, maximum=250)},
               value_range=(-100, 1000), recommended=0),
    _technical("relative_return", "시장 대비 초과수익률", "percent", _COMPARISON_OPS,
               {"period": ParamSpec(default=60, minimum=2, maximum=250)},
               value_range=(-100, 1000), recommended=0,
               notes="종목 N거래일 수익률 − 상장 시장 지수(코스피·코스닥) N거래일 수익률(%p). "
                     "'시장보다 덜 떨어진/강한/웃도는'은 > 0, '시장보다 더 떨어진'은 < 0. "
                     "period=거래일(3개월=63). 미국 시장은 지수 시계열이 없어 미지원. "
                     "'상대강도 상위 N%'는 이 지표가 아니라 ranking.return(수익률 랭킹)이다 — "
                     "그 표현으로 이 조건을 함께 만들지 않는다"),
    _technical("volatility", "변동성(연환산)", "percent", _COMPARISON_OPS,
               {"period": ParamSpec(default=60, minimum=5, maximum=250)},
               value_range=(0, 500), recommended=30,
               notes="일수익률 롤링 표준편차×√246(연환산 %, KRX 실측 계수). '변동성 30% 이하 종목'처럼 임계값 "
                     "필터일 때만. '변동성 낮은 종목 N개' 순위 선정은 ranking.volatility"),
    _technical("trading_value", "거래대금 신호", "억원", _COMPARISON_OPS, {},
               value_range=(0, 1_000_000),
               notes="**당일 하루치** 거래대금이 임계를 넘는 매매 시점 트리거일 때만"
                     "('거래대금이 N억을 넘으면 매수'). 기간 평균('일평균·최근 N일 평균')이거나 "
                     "종목 선정 기준이면 fundamental.trading_value"),
    IndicatorSpec(
        id="technical.ai_model", display_name="AI 상승 예측", category="ai",
        supported="SUPPORTED", data_source="ai_model", value_type="percent",
        allowed_operators=(">", ">="),
        parameters={"threshold": ParamSpec(default=70, minimum=50, maximum=100)},
        value_range=(0, 100), engine_binding=("technical_signal", "ai_model"),
        notes="상승 확률 임계는 percent(0~100) — '상승 확률 80% 이상'이면 value=80"),
    IndicatorSpec(
        id="technical.ai_drop_model", display_name="AI 하락 예측 청산", category="ai",
        supported="SUPPORTED", data_source="ai_model", value_type="percent",
        allowed_operators=(">", ">="),
        parameters={"threshold": ParamSpec(default=70, minimum=50, maximum=100)},
        value_range=(0, 100), engine_binding=("technical_signal", "ai_drop_model")),

    # ── 랭킹 지표 ─────────────────────────────────────────────────────────────
    IndicatorSpec(
        id="ranking.return", display_name="기간 수익률 랭킹(모멘텀)", category="ranking",
        supported="SUPPORTED", data_source="ohlcv", value_type="percent",
        parameters={"lookback_days": ParamSpec(default=60, minimum=5, maximum=500)},
        engine_binding=("ranking", "return")),
    IndicatorSpec(
        id="ranking.relative_return", display_name="시장 대비 초과수익률 랭킹", category="ranking",
        supported="SUPPORTED", data_source="ohlcv", value_type="percent",
        parameters={"lookback_days": ParamSpec(default=60, minimum=5, maximum=500)},
        engine_binding=("ranking", "relative_return"),
        notes="종목 N거래일 수익률 − 상장 시장 지수 N거래일 수익률 순위 선정. '시장 대비 수익률 상위 "
              "N종목'·'초과수익률 상위'처럼 **시장 대비**를 말한 순위 선정만. '상대강도 상위'·'수익률 "
              "상위'는 ranking.return. 미국 시장은 지수 시계열이 없어 미지원"),
    IndicatorSpec(
        id="ranking.residual_reversal", display_name="잔차 반전 시그널 랭킹", category="ranking",
        supported="SUPPORTED", data_source="ohlcv", value_type="point",
        parameters={"lookback_days": ParamSpec(default=60, minimum=60, maximum=250),
                    "accumulation_days": ParamSpec(default=5, minimum=3, maximum=20)},
        engine_binding=("ranking", "residual_reversal"),
        notes="종목 일간 수익률을 시장 수익률·소속 섹터 평균 수익률에 회귀한 **잔차**의 최근 누적을 "
              "잔차 변동성으로 나눠 표준화하고 부호를 뒤집은 시그널 순위 선정(통계적 차익거래·잔차 "
              "반전·시장/섹터 중립 단기 반전). lookback_days=회귀 기간(60·120·250 중 말한 값), "
              "accumulation_days=잔차 누적 기간(3·5·10·20 중 말한 값). 윈저라이즈·z-score·부호 반전은 "
              "지표에 포함돼 있다. 단순 '낙폭 과대'·'수익률 하위'는 ranking.return(direction bottom)"),
    IndicatorSpec(
        id="ranking.pead", display_name="실적 서프라이즈 시그널 랭킹", category="ranking",
        supported="SUPPORTED", data_source="fundamental", value_type="point",
        parameters={"entry_delay_days": ParamSpec(default=2, minimum=0, maximum=20),
                    "expiry_days": ParamSpec(default=60, minimum=5, maximum=250)},
        engine_binding=("ranking", "pead"),
        notes="분기 EPS의 전년 동기 대비 서프라이즈를 직전 8개 분기 표준편차로 나눈 SUE와, 실적 "
              "발표일 전후(직전 거래일~발표 2거래일 후) 시장 대비 초과수익률을 각각 횡단면 "
              "z-score로 표준화해 평균한 시그널 순위 선정(실적 발표 후 표류·PEAD·어닝 서프라이즈). "
              "entry_delay_days=발표 후 편입까지 기다리는 거래일, expiry_days=발표 후 제외까지의 "
              "거래일. 윈저라이즈·z-score·평균은 지표에 포함돼 있다. 분기 실적을 수집한 종목만 "
              "후보이며 2016년 이후 구간에서만 값이 선다"),
    IndicatorSpec(
        id="ranking.volatility", display_name="변동성 랭킹(저변동성)", category="ranking",
        supported="SUPPORTED", data_source="ohlcv", value_type="percent",
        parameters={"lookback_days": ParamSpec(default=60, minimum=5, maximum=500)},
        engine_binding=("ranking", "volatility"),
        notes="N일 일수익률 표준편차(연환산 %) 순위 선정. '변동성 낮은 종목 N개'는 "
              "direction bottom(방향 미지정 시 온톨로지 lower_better가 bottom을 채움)"),

    # ── 개념은 이해하지만 엔진/데이터 미지원 (조용한 대체 금지 — 명시 제안만) ──
    # 3분류 절대 금액은 2026-08-05 지원 승격 — 여기 남은 미지원은 FCF/PCF '배율' 계열뿐이다.
    # 항목 자체를 지우지 않는 이유: 어느 분류인지 특정되지 않은 맨 '현금흐름' 언급은 여전히
    # 결정적으로 고를 수 없어 LLM 위임 신호가 필요하다(PCR 승격 때와 같은 판단).
    _unsupported("cash_flow", "현금흐름 배율(FCF/PCF) 조건", "valuation",
                 alternatives=("fundamental.operating_cf_amount", "fundamental.pcr"),
                 notes="영업·투자·재무활동 현금흐름 절대 금액(억원)은 "
                       "operating_cf_amount/investing_cf_amount/financing_cf_amount로 지원됨"),
    _unsupported("beta", "베타(시장 민감도)", "risk"),
    _unsupported("interest_coverage", "이자보상배율", "stability",
                 alternatives=("fundamental.debt_ratio", "fundamental.current_ratio")),
    _unsupported("quality_score", "알트만 Z-score(파산 예측 점수)", "quality"),
    _unsupported("turnover_ratio", "회전율(재고·매출채권)", "efficiency"),
    _unsupported("buyback", "자사주 매입", "event"),
    _unsupported("news", "뉴스/공시/재료 조건", "event"),
    _unsupported("supply_demand", "수급(외국인·기관·공매도)", "flow"),
    # 흑자/적자 '여부'는 fundamental.eps 부호 필터로 승격(2026-07-24) — 전환·연속만 미지원.
    _unsupported("profitability_transition", "흑자/적자 전환·연속(턴어라운드, N년 연속 흑자)", "profitability",
                 alternatives=("fundamental.eps",),
                 notes="단일 시점 흑자/적자 여부는 fundamental.eps(>0/<0)로 표현 가능"),
    _unsupported("ema_alignment", "정배열/역배열", "technical"),
    _unsupported("new_low", "신저가 조건", "technical"),
    _unsupported("earnings_estimate", "실적 컨센서스/추정치", "fundamental"),
    _unsupported("moat", "경제적 해자 등 정성 평가", "quality"),
)

REGISTRY: Dict[str, IndicatorSpec] = {
    spec.id: (
        replace(spec, data_pending=True) if spec.id in DATA_PENDING_METRICS else spec
    )
    for spec in _SPECS
}

# ── 이름 해석(alias → canonical ID) ─────────────────────────────────────────
# LLM이 추출한 지표명을 canonical ID로 매핑한다. 여기의 alias는 '동의어 사전'이
# 아니라 canonical 표기 변형(영문/한글 공식 명칭)만 담는다 — 구어체 긴 꼬리
# ("이익에 비해 싼")의 해석은 LLM의 몫이고, LLM은 아래 canonical 이름 중 하나로
# 출력하도록 프롬프트로 계약한다.
_ALIASES: Dict[str, str] = {
    "per": "fundamental.per", "주가수익비율": "fundamental.per",
    "pbr": "fundamental.pbr", "주가순자산비율": "fundamental.pbr",
    "psr": "fundamental.psr", "주가매출비율": "fundamental.psr",
    "pcr": "fundamental.pcr", "주가현금흐름비율": "fundamental.pcr",
    "ev/ebitda": "fundamental.ev_ebitda", "ev_ebitda": "fundamental.ev_ebitda",
    "ev/ebit": "fundamental.ev_ebit", "ev_ebit": "fundamental.ev_ebit",
    "roe": "fundamental.roe_or_gpa", "자기자본이익률": "fundamental.roe_or_gpa",
    "roa": "fundamental.roa", "총자본순이익률": "fundamental.roa", "총자산이익률": "fundamental.roa",
    "부채비율": "fundamental.debt_ratio", "debt_ratio": "fundamental.debt_ratio",
    "유동비율": "fundamental.current_ratio", "current_ratio": "fundamental.current_ratio",
    "당좌비율": "fundamental.quick_ratio", "quick_ratio": "fundamental.quick_ratio",
    "유보율": "fundamental.reserve_ratio", "reserve_ratio": "fundamental.reserve_ratio",
    "순이익률": "fundamental.net_margin", "net_margin": "fundamental.net_margin",
    "매출총이익률": "fundamental.gross_margin", "gross_margin": "fundamental.gross_margin",
    "영업이익률": "fundamental.operating_margin", "operating_margin": "fundamental.operating_margin",
    "매출액증가율": "fundamental.revenue_growth", "매출증가율": "fundamental.revenue_growth",
    "revenue_growth": "fundamental.revenue_growth",
    "영업이익증가율": "fundamental.operating_income_growth",
    "operating_income_growth": "fundamental.operating_income_growth",
    "순이익증가율": "fundamental.net_income_growth", "net_income_growth": "fundamental.net_income_growth",
    "eps증가율": "fundamental.eps_growth", "eps_growth": "fundamental.eps_growth",
    "ebitda증가율": "fundamental.ebitda_growth", "ebitda_growth": "fundamental.ebitda_growth",
    "영업현금흐름증가율": "fundamental.ocf_growth", "영업활동현금흐름증가율": "fundamental.ocf_growth",
    "ocf_growth": "fundamental.ocf_growth",
    # 9B 레인이 금액 지표(operating_cf_amount)와 증가율을 섞어 내는 표기 — 2026-09-15 운영
    # 실측: "최근 4개 분기 영업활동현금흐름 증가율이 10% 이상"이 operating_cf_growth로 나와
    # 알 수 없는 지표로 탈락하고 "조건은 전략에 반영하지 못했어요" 안내가 나갔다.
    "operating_cf_growth": "fundamental.ocf_growth",
    "operating_cash_flow_growth": "fundamental.ocf_growth",
    "operatingcashflowgrowth": "fundamental.ocf_growth",
    "잉여현금흐름증가율": "fundamental.fcf_growth", "fcf_growth": "fundamental.fcf_growth",
    "시가총액": "fundamental.market_cap", "market_cap": "fundamental.market_cap",
    "거래대금": "fundamental.trading_value", "trading_value": "fundamental.trading_value",
    "배당수익률": "fundamental.dividend_yield", "dividend_yield": "fundamental.dividend_yield",
    "배당성향": "fundamental.payout_rate", "payout_rate": "fundamental.payout_rate",
    "배당성장률": "fundamental.dividend_growth", "dividend_growth": "fundamental.dividend_growth",
    "연속배당연수": "fundamental.dividend_streak_years", "dividend_streak_years": "fundamental.dividend_streak_years",
    "연속배당": "fundamental.dividend_streak_years", "연속배당지급": "fundamental.dividend_streak_years",
    "배당연속연수": "fundamental.dividend_streak_years", "dividend_streak": "fundamental.dividend_streak_years",
    "consecutive_dividend_years": "fundamental.dividend_streak_years",
    "consecutivedividendyears": "fundamental.dividend_streak_years",
    # 자산성장률·발생액 비율(v16.25).
    "자산성장률": "fundamental.asset_growth", "총자산증가율": "fundamental.asset_growth",
    "자산증가율": "fundamental.asset_growth", "총자산성장률": "fundamental.asset_growth",
    "asset_growth": "fundamental.asset_growth", "assetgrowth": "fundamental.asset_growth",
    "totalassetgrowth": "fundamental.asset_growth",
    "발생액": "fundamental.accruals_ratio", "발생액비율": "fundamental.accruals_ratio",
    "총발생액": "fundamental.accruals_ratio", "accruals": "fundamental.accruals_ratio",
    "accrual": "fundamental.accruals_ratio", "accruals_ratio": "fundamental.accruals_ratio",
    "accrualsratio": "fundamental.accruals_ratio", "accrualratio": "fundamental.accruals_ratio",
    "ma_crossover": "technical.ma_crossover", "이동평균크로스오버": "technical.ma_crossover",
    "골든크로스": "technical.ma_crossover", "데드크로스": "technical.ma_crossover",
    "이동평균": "technical.ma_crossover",
    "ema": "technical.ema", "지수이동평균": "technical.ema",
    "rsi": "technical.rsi",
    "macd": "technical.macd",
    "볼린저밴드": "technical.bollinger_bands", "bollinger": "technical.bollinger_bands",
    "bollinger_bands": "technical.bollinger_bands", "볼린저": "technical.bollinger_bands",
    "breakout": "technical.breakout", "신고가돌파": "technical.breakout", "신고가": "technical.breakout",
    "volume_spike": "technical.volume_spike", "거래량급증": "technical.volume_spike",
    "volume_ratio": "technical.volume_ratio", "거래량배수": "technical.volume_ratio",
    "volume_multiple": "technical.volume_ratio",
    "trading_value_ratio": "technical.trading_value_ratio",
    "거래대금배수": "technical.trading_value_ratio",
    "스토캐스틱": "technical.stochastic", "stochastic": "technical.stochastic",
    "cci": "technical.cci",
    "adx": "technical.adx",
    "망치형": "technical.candle_hammer", "망치형": "technical.candle_hammer", "hammer": "technical.candle_hammer", "candle_hammer": "technical.candle_hammer",
    "교수형": "technical.candle_hanging_man", "교수형": "technical.candle_hanging_man", "hanging man": "technical.candle_hanging_man", "candle_hanging_man": "technical.candle_hanging_man",
    "역망치형": "technical.candle_inverted_hammer", "역망치형": "technical.candle_inverted_hammer", "inverted hammer": "technical.candle_inverted_hammer", "candle_inverted_hammer": "technical.candle_inverted_hammer",
    "유성형": "technical.candle_shooting_star", "유성형": "technical.candle_shooting_star", "shooting star": "technical.candle_shooting_star", "candle_shooting_star": "technical.candle_shooting_star",
    "도지": "technical.candle_doji", "도지": "technical.candle_doji", "doji": "technical.candle_doji", "candle_doji": "technical.candle_doji",
    "상승장악형": "technical.candle_bullish_engulfing", "상승 장악형": "technical.candle_bullish_engulfing", "bullish engulfing": "technical.candle_bullish_engulfing", "candle_bullish_engulfing": "technical.candle_bullish_engulfing",
    "하락장악형": "technical.candle_bearish_engulfing", "하락 장악형": "technical.candle_bearish_engulfing", "bearish engulfing": "technical.candle_bearish_engulfing", "candle_bearish_engulfing": "technical.candle_bearish_engulfing",
    "관통형": "technical.candle_piercing_line", "관통형": "technical.candle_piercing_line", "piercing line": "technical.candle_piercing_line", "candle_piercing_line": "technical.candle_piercing_line",
    "먹구름형": "technical.candle_dark_cloud_cover", "먹구름형": "technical.candle_dark_cloud_cover", "dark cloud cover": "technical.candle_dark_cloud_cover", "candle_dark_cloud_cover": "technical.candle_dark_cloud_cover",
    "샛별형": "technical.candle_morning_star", "샛별형": "technical.candle_morning_star", "morning star": "technical.candle_morning_star", "candle_morning_star": "technical.candle_morning_star",
    "저녁별형": "technical.candle_evening_star", "저녁별형": "technical.candle_evening_star", "evening star": "technical.candle_evening_star", "candle_evening_star": "technical.candle_evening_star",
    "적삼병": "technical.candle_three_white_soldiers", "적삼병": "technical.candle_three_white_soldiers", "three white soldiers": "technical.candle_three_white_soldiers", "candle_three_white_soldiers": "technical.candle_three_white_soldiers",
    "흑삼병": "technical.candle_three_black_crows", "흑삼병": "technical.candle_three_black_crows", "three black crows": "technical.candle_three_black_crows", "candle_three_black_crows": "technical.candle_three_black_crows",
    "williams_r": "technical.williams_r", "williams%r": "technical.williams_r",
    "윌리엄스": "technical.williams_r",
    "mfi": "technical.mfi", "자금흐름지표": "technical.mfi",
    "roc": "technical.roc", "모멘텀": "technical.roc",
    "relative_return": "technical.relative_return", "초과수익률": "technical.relative_return",
    "시장대비초과수익률": "technical.relative_return", "시장대비수익률": "technical.relative_return",
    "ai_model": "technical.ai_model", "ai상승예측": "technical.ai_model",
    "ai_drop_model": "technical.ai_drop_model", "ai하락예측": "technical.ai_drop_model",
    "return": "ranking.return", "수익률랭킹": "ranking.return", "기간수익률": "ranking.return",
    "초과수익률랭킹": "ranking.relative_return", "시장대비수익률랭킹": "ranking.relative_return",
    "pead": "ranking.pead", "실적서프라이즈": "ranking.pead",
    "실적서프라이즈시그널": "ranking.pead", "실적서프라이즈시그널랭킹": "ranking.pead",
    "어닝서프라이즈": "ranking.pead", "sue": "ranking.pead",
    "residual_reversal": "ranking.residual_reversal", "잔차반전": "ranking.residual_reversal",
    "잔차반전시그널": "ranking.residual_reversal", "잔차반전시그널랭킹": "ranking.residual_reversal",
    # FCF 수익률(v16.15 지원 승격 — 종전 unsupported.fcf_yield). 맨 'fcf'·'잉여현금흐름'은
    # 관용상 수익률(시총 대비)을 뜻하는 표기로 남긴다(마진·증가율은 각자 별칭이 있다).
    "fcf": "fundamental.fcf_yield", "fcf_yield": "fundamental.fcf_yield",
    "fcfyield": "fundamental.fcf_yield", "fcf수익률": "fundamental.fcf_yield",
    "잉여현금흐름": "fundamental.fcf_yield", "잉여현금흐름수익률": "fundamental.fcf_yield",
    "잉여현금흐름수익률(fcfyield)": "fundamental.fcf_yield", "freecashflowyield": "fundamental.fcf_yield",
    # 미지원 개념의 canonical 표기(LLM이 이 이름으로 출력하면 UNSUPPORTED로 판정된다)
    "현금흐름": "unsupported.cash_flow", "pcf": "unsupported.cash_flow",
    "변동성": "technical.volatility", "volatility": "technical.volatility",
    "저변동성": "ranking.volatility", "변동성랭킹": "ranking.volatility",
    "roic": "fundamental.roic", "투하자본이익률": "fundamental.roic",
    "estimate_revision": "unsupported.earnings_estimate",
    "earnings_revision": "unsupported.earnings_estimate",
    "earnings_estimate": "unsupported.earnings_estimate",
    "실적추정치": "unsupported.earnings_estimate", "컨센서스": "unsupported.earnings_estimate",
    "fcf_margin": "fundamental.fcf_margin", "fcf마진": "fundamental.fcf_margin",
    "잉여현금흐름마진": "fundamental.fcf_margin", "freecashflowmargin": "fundamental.fcf_margin",
    "잉여현금흐름(fcf)마진": "fundamental.fcf_margin", "fcf(잉여현금흐름)마진": "fundamental.fcf_margin",
    "베타": "unsupported.beta", "beta": "unsupported.beta",
    "이자보상배율": "unsupported.interest_coverage",
    # F-score(v16.26 지원 승격 — 종전 unsupported.quality_score). 알트만은 미지원으로 남는다.
    "피오트로스키": "fundamental.f_score", "f-score": "fundamental.f_score",
    "fscore": "fundamental.f_score", "f_score": "fundamental.f_score",
    "피오트로스키점수": "fundamental.f_score", "피오트로스키f-score": "fundamental.f_score",
    "f점수": "fundamental.f_score", "피오트로스키fscore": "fundamental.f_score",
    "알트만": "unsupported.quality_score", "z-score": "unsupported.quality_score",
    # NCAV·분기 성장률(v16.27).
    "ncav": "fundamental.ncav_ratio", "ncav_ratio": "fundamental.ncav_ratio", "순유동자산": "fundamental.ncav_ratio",
    "청산가치": "fundamental.ncav_ratio", "시총/ncav": "fundamental.ncav_ratio", "ncav비율": "fundamental.ncav_ratio",
    "그레이엄ncav": "fundamental.ncav_ratio", "순유동자산가치": "fundamental.ncav_ratio",
    "분기매출성장률": "fundamental.revenue_growth_yoy", "분기매출액증가율": "fundamental.revenue_growth_yoy",
    "매출분기성장률": "fundamental.revenue_growth_yoy", "매출qoq": "fundamental.revenue_growth_qoq",
    "매출yoy": "fundamental.revenue_growth_yoy", "revenue_growth_qoq": "fundamental.revenue_growth_qoq",
    "revenue_growth_yoy": "fundamental.revenue_growth_yoy",
    "분기영업이익성장률": "fundamental.operating_income_growth_yoy", "영업이익qoq": "fundamental.operating_income_growth_qoq",
    "영업이익yoy": "fundamental.operating_income_growth_yoy", "operating_income_growth_qoq": "fundamental.operating_income_growth_qoq",
    "operating_income_growth_yoy": "fundamental.operating_income_growth_yoy",
    "분기순이익성장률": "fundamental.net_income_growth_yoy", "순이익qoq": "fundamental.net_income_growth_qoq",
    "순이익yoy": "fundamental.net_income_growth_yoy", "net_income_growth_qoq": "fundamental.net_income_growth_qoq",
    "net_income_growth_yoy": "fundamental.net_income_growth_yoy",
    "회전율": "unsupported.turnover_ratio",
    "자사주매입": "unsupported.buyback", "자사주": "unsupported.buyback",
    "뉴스": "unsupported.news", "공시": "unsupported.news",
    "수급": "unsupported.supply_demand", "외국인순매수": "unsupported.supply_demand",
    "eps": "fundamental.eps", "주당순이익": "fundamental.eps",
    "흑자": "fundamental.eps", "적자": "fundamental.eps",
    "당기순이익": "fundamental.net_income", "net_income": "fundamental.net_income",
    # 지배주주순이익 — 귀속 주체('지배')를 밝힌 표기만 매핑한다. resolve()는 정확 일치라
    # 위 "당기순이익"을 잠식하지 않는다.
    "지배주주순이익": "fundamental.owner_net_income",
    "지배주주지분순이익": "fundamental.owner_net_income",
    "지배주주귀속순이익": "fundamental.owner_net_income",
    "지배기업소유주지분순이익": "fundamental.owner_net_income",
    "지배기업소유주귀속당기순이익": "fundamental.owner_net_income",
    "지배순이익": "fundamental.owner_net_income",
    "연결지배순이익": "fundamental.owner_net_income",
    "owner_net_income": "fundamental.owner_net_income",
    # 현금흐름 3분류 절대 금액(억원). '…증가율' 별칭은 위 ocf_growth/fcf_growth로 따로
    # 잡혀 있고 resolve()는 정확 일치라 서로 잠식하지 않는다.
    "영업활동현금흐름": "fundamental.operating_cf_amount",
    "영업현금흐름": "fundamental.operating_cf_amount",
    "영업활동으로인한현금흐름": "fundamental.operating_cf_amount",
    "operating_cf_amount": "fundamental.operating_cf_amount",
    "ocf": "fundamental.operating_cf_amount",
    "투자활동현금흐름": "fundamental.investing_cf_amount",
    "투자현금흐름": "fundamental.investing_cf_amount",
    "투자활동으로인한현금흐름": "fundamental.investing_cf_amount",
    "investing_cf_amount": "fundamental.investing_cf_amount",
    "재무활동현금흐름": "fundamental.financing_cf_amount",
    "재무현금흐름": "fundamental.financing_cf_amount",
    "재무활동으로인한현금흐름": "fundamental.financing_cf_amount",
    "financing_cf_amount": "fundamental.financing_cf_amount",
    "ebit": "fundamental.ebit", "영업이익": "fundamental.ebit",
    "영업이익흑자": "fundamental.ebit", "영업이익적자": "fundamental.ebit",
    "흑자전환": "unsupported.profitability_transition",
    "턴어라운드": "unsupported.profitability_transition",
    "정배열": "unsupported.ema_alignment", "역배열": "unsupported.ema_alignment",
    "신저가": "unsupported.new_low",
    "경제적해자": "unsupported.moat",
}


def contains_factor_term(text: str) -> bool:
    """LLM이 뽑은 표현에 한글 지표 어휘가 들어있는지 — 유니버스 오분류 백스톱.

    planner가 재무·기술 지표 조건 구("당기순이익과, 영업이익률이 높은 종목")를 유니버스
    표현으로 넘기면 CONCEPT 판정 → KG 조회·검색 학습 체인이 턴 예산을 소진한다
    (2026-08-03 실측 10.7초). 입력은 LLM 구조화 출력이라 결정론 대조가 계약에 맞는다.
    라틴 약칭(per·roe 등)은 테마·상품명 오탐 위험이 있어 한글 어휘(4자 이상)만 본다.
    """
    normalized = (text or "").replace(" ", "").lower()
    if not normalized:
        return False
    return any(
        len(alias) >= 4 and not alias.isascii() and alias in normalized
        for alias in _ALIASES
    )


def factor_ids_named_in(text: str) -> set:
    """짧은 문자열이 **이름으로 부른** 지표의 canonical ID 집합.

    입력은 LLM이 스스로 낸 인용(source_text)이다(§ 3-2 지식 조회) — 사용자 원문을 훑지
    않는다. `contains_factor_term`이 '어휘가 있나'만 보는 데 비해 이쪽은 '어느 지표인가'를
    돌려준다. 라틴 약칭(per·pbr·roe)은 단어 경계를 요구해 상품명·영문 조각의 우연한
    포함을 막는다.
    """
    if not text:
        return set()
    normalized = text.replace(" ", "").lower()
    out = set()
    for alias, canonical in _ALIASES.items():
        if alias.isascii():
            if re.search(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", normalized):
                out.add(canonical)
        elif alias in normalized:
            out.add(canonical)
    return out


# 같은 이름('거래대금')을 공유하는 지표 변형 — 금액 임계(일평균·당일)와 자기 평균 대비 배수는
# 모두 '거래대금'으로 불린다. 별칭 표는 이름 하나를 정본 하나로만 잇기 때문에(조건 회수가 이
# 결과로 조건을 되살린다), 대체 감지만 이 표로 변형을 같은 지표로 본다.
_SAME_NAME_VARIANTS: Dict[str, frozenset] = {
    "fundamental.trading_value": frozenset({"technical.trading_value",
                                            "technical.trading_value_ratio"}),
}


def with_same_name_variants(factor_ids: set) -> set:
    """factor_ids_named_in 결과에 같은 이름을 공유하는 변형 지표를 더한다."""
    out = set(factor_ids)
    for factor_id in factor_ids:
        out |= _SAME_NAME_VARIANTS.get(factor_id, frozenset())
    return out


# 합성 시그널 랭킹이 **계산 안에 이미 품은 것** — ① 재료 지표 ② 내장 처리의 이름.
# 사용자가 시그널의 계산 과정을 풀어 말하면("EPS 데이터가 있는 종목… 초과수익률을 구한다…
# 상하위 1% 윈저라이즈") 인터프리터가 랭킹을 제대로 고르고도 같은 구절을 계열 껍데기 조건·
# 미지원 보고로 한 번 더 낸다(2026-09-21 실측 9B: pead 랭킹이 반영된 턴에 "어떤 재무 지표를
# 사용할까요?" 되묻기와 "'윈저라이즈 처리' 조건은 지원하지 않아" 안내가 함께 나갔다).
# 대조 입력은 LLM이 낸 짧은 문자열(인용·보고 조각)이다(§ 3-2 지식 조회 — 원문을 훑지 않는다).
RANKING_INGREDIENTS: Dict[str, frozenset] = {
    "ranking.pead": frozenset({"fundamental.eps", "technical.relative_return"}),
}
_RANKING_BUILT_IN_PROCESSING: Dict[str, Tuple[str, ...]] = {
    "ranking.pead": ("윈저라이즈", "winsoriz", "winzoriz", "z-score", "zscore", "표준화"),
    "ranking.residual_reversal": (
        "윈저라이즈", "winsoriz", "winzoriz", "z-score", "zscore", "표준화", "부호반전"),
}


def ranking_covers(text: str, ranking_ids: Iterable[str]) -> bool:
    """짧은 문자열이 **전략에 있는 랭킹이 이미 품은 것만** 말하는가.

    이름으로 부른 지표가 전부 그 랭킹 자신이거나 재료 지표이고, 그런 이름이 하나도 없으면
    내장 처리 이름을 담고 있어야 한다. 다른 지표를 하나라도 부르면("PER 윈저라이즈") 그
    랭킹이 품은 말이 아니다.
    """
    ranked = set(ranking_ids)
    if not ranked or not text:
        return False
    inside = set(ranked)
    for ranking_id in ranked:
        inside |= RANKING_INGREDIENTS.get(ranking_id, frozenset())
    named = factor_ids_named_in(text)
    if not named <= inside:
        return False
    if named:
        return True
    normalized = text.replace(" ", "").lower()
    return any(
        term in normalized
        for ranking_id in ranked
        for term in _RANKING_BUILT_IN_PROCESSING.get(ranking_id, ())
    )


def resolve(name: str) -> Optional[IndicatorSpec]:
    """지표명(canonical ID/공식 명칭)을 IndicatorSpec으로 해석한다. 미지 시 None."""
    if not name:
        return None
    key = name.strip()
    if key in REGISTRY:
        return REGISTRY[key]
    normalized = key.replace(" ", "").lower()
    canonical = _ALIASES.get(normalized)
    if canonical:
        return REGISTRY[canonical]
    # 네임스페이스만 틀린 ID('fundamental.adx' — 2026-09-14 실측: ADX 진입·청산 조건이
    # '알 수 없는 지표'로 통째로 빠졌다). 잎 이름이 레지스트리에서 유일하면 그 지표다 —
    # LLM 출력의 표기 정규화이지 해석이 아니다. 잎이 둘 이상에 있으면 종전대로 None.
    if "." in normalized:
        leaf = normalized.split(".", 1)[1]
        # 미지원 항목(unsupported.beta)은 대상이 아니다 — 그 조건의 안내는 사용자 표현
        # (source_text) 인용 경로가 맡는다(내부명 노출 금지 회귀와 같은 계약).
        matches = [
            spec_id for spec_id, spec in REGISTRY.items()
            if spec_id.split(".", 1)[1] == leaf and spec.supported != "UNSUPPORTED"
        ]
        if len(matches) == 1:
            return REGISTRY[matches[0]]
        # 잎이 정본 ID가 아니라 **별칭**인 경우도 같은 표기 정규화다
        # ("fundamental.operating_cf_growth" → ocf_growth, 2026-09-15 운영 실측).
        canonical_leaf = _ALIASES.get(leaf)
        if canonical_leaf and REGISTRY[canonical_leaf].supported != "UNSUPPORTED":
            return REGISTRY[canonical_leaf]
    return None


# 프롬프트 지표 어휘 생성은 concept_ontology.ontology_prompt_sections로 이관됐다
# (2026-08-06, PROMPT_VERSION 2.8) — 잎 한 줄 표기는 concept_ontology._leaf_line이
# 동일 형식을 유지한다(notes 포함 — 선택 기준을 가르는 정보라 주입 필수).
