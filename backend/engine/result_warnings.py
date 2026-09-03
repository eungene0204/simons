"""백테스트 결과 경고(warnings)의 한국어 정본 템플릿과 구조화 표현.

결과 로그의 경고는 엔진이 만드는 표시 문구다. 표시 번역은 프론트 t() 소관이라(lib/i18n)
엔진은 **완성 문장 대신 한국어 정본 템플릿과 치환 인자**를 싣는다 — 값이 박힌 문장
("거래 수가 12건으로 30건 미만입니다")은 값마다 사전 키가 달라져 /us에서 번역할 수 없다.
(backend/stream_progress.py의 진행 문구, engine/trade_reason.py의 매매사유와 같은 계약.)

표현은 매매사유와 같은 세그먼트 리스트다(engine/trade_reason.py 참조):

    {"t": "<한국어 정본 템플릿>", "a": [인자...]}   # 번역 대상
    {"s": "<리터럴>"}                                 # 구분자·괄호

인자에는 세그먼트를 중첩할 수 있다 — 재무 지표 라벨(FUNDAMENTAL_LABELS)·음수 제외 사유처럼
그 자체가 사전 키인 낱말은 `tr.part(라벨)`로 싸서 넣는다(프론트가 라벨도 번역한다).

엔진 내부의 경고 채널(`BacktestEngine.warnings` set, phase1 side 채널, 커버리지 리포트)은
문자열 슬롯이라, 세그먼트를 JSON으로 인코딩한 문자열(`tr.encode`)로 그대로 나른다.
밖으로 나갈 때 `finalize()`가 한국어 문장(`warnings`, 종전과 바이트 동일)과 세그먼트
(`warningParts`)를 같은 순서로 만든다.

새 경고를 추가하면 여기 템플릿 상수를 만들고 lib/i18n/en.ts에도 같은 원문을 키로 넣는다
(tests/result-warnings-i18n.test.ts가 이 파일을 스캔해 강제하고,
backend/tests/test_result_warnings.py가 엔진 소스에 평문 f-string 경고가 남지 않게 막는다).
"""

from __future__ import annotations

from typing import Any, Iterable, List, Optional, Sequence, Tuple

from engine import trade_reason as tr

Segment = tr.Segment

# ── 거래 비용·체결 ───────────────────────────────────────────────────────────
ZERO_COST = "수수료와 슬리피지가 모두 0으로 설정되어 있습니다 — 거래 비용이 없는 결과는 실제보다 유리합니다."
SAME_CLOSE_EXECUTION = "체결 방식이 '당일 종가 체결'입니다 — 당일 종가 신호를 당일 종가에 체결하는 비현실적 가정(룩어헤드)입니다. 실거래 판단에는 '익일 시가 체결' 방식 사용을 권장합니다."

# ── 유니버스 구성 ────────────────────────────────────────────────────────────
US_UNIVERSE_SURVIVORSHIP = "미국 유니버스는 현재 상장 종목 기준입니다 — 기간 중 상장폐지된 종목이 빠져 있어 장기 결과가 실제보다 유리하게 나올 수 있습니다(생존 편향)."
INDEX_UNIVERSE_CURRENT_LIST = "지수 유니버스는 현재 구성종목 명부 기준입니다 — 과거의 편입·편출은 반영되지 않습니다."
US_INDUSTRY_CURRENT_CLASSIFICATION = "업종({0}) 필터는 현재 분류 기준입니다 — 기간 중의 업종 재분류는 반영되지 않습니다."
DELISTING_HISTORY_FLOOR = "상장폐지 종목 이력은 {0}부터 반영됩니다 — 그 이전 구간은 현재 생존 종목만으로 구성돼 결과가 실제보다 유리할 수 있습니다(생존 편향)."
ETF_UNIVERSE_SURVIVORSHIP = "ETF 유니버스는 현재 상장 ETF만 포함합니다 — 기간 중 상장폐지된 ETF는 빠져 있어 생존 편향 가능성이 있습니다."
ETF_THEME_NOT_FOUND = "'{0}' 테마와 이름이 일치하는 ETF를 찾지 못해 전체 ETF를 대상으로 백테스트했습니다."
US_SYMBOLS_SURVIVORSHIP = "미국 데이터에는 상장폐지 종목의 가격 이력이 없습니다 — 테마·지정 종목 백테스트도 현재 상장 종목만으로 구성돼 장기 결과가 실제보다 유리하게 나올 수 있습니다(생존 편향)."
SECTOR_MAP_FROM_FILE_CACHE = "섹터({0}) 분류를 정본(지식그래프)이 아니라 파일 캐시에서 읽었습니다 — {1}"
SECTOR_MAP_REASON_UNKNOWN = "사유 불명"
SECTOR_UNKNOWN_DELISTED_EXCLUDED = "섹터({0}) 필터: 업종 분류가 없는 상장폐지 종목 {1}개가 제외되었습니다 — 생존 편향 가능성이 있습니다."
LISTING_DATE_UNKNOWN_EXCLUDED = "신규 상장 필터: 상장일을 확인할 수 없는 종목 {0}개가 제외되었습니다."

# ── 종목 단위 (engine/phase1.py) ─────────────────────────────────────────────
SYMBOL_NO_DATA = "{0}: 데이터 없음 — 백테스트 대상에서 제외되었습니다."
SYMBOL_LIQUIDITY_BELOW = "{0}: 유동성 기준 미달 (거래대금 부족)"
SYMBOL_PROCESSING_ERROR = "{0}: 처리 오류 ({1})"

# ── 지수 유니버스 판정 ───────────────────────────────────────────────────────
INDEX_TOP_N_MEASURED = "지수(시가총액 상위 {0}) 판정은 일별 실측 시가총액 순위입니다 — 실제 {1}의 편입·편출 규칙(유동성·업종 배분 등)과는 다를 수 있습니다."
INDEX_TOP_N_APPROXIMATED = "지수(시가총액 상위 {0}) 판정은 일별 실측 시가총액 순위이며, 실측이 없는 {1}% 구간은 현재 상장주식수 × 과거 주가의 근사입니다 — 근사 구간은 증자·분할 이력이 반영되지 않아 실제 당시 {2} 구성과 다를 수 있습니다."

# ── 랭킹·분위 그룹 ───────────────────────────────────────────────────────────
COMPOSITE_RANK_DATA_MISSING = "복합 순위 구성 지표 '{0}' 데이터가 대상 종목에 없어 랭킹 선정이 적용되지 않았습니다."
RANK_METRIC_DATA_MISSING = "랭킹 지표 '{0}' 데이터가 대상 종목에 없어 랭킹 선정이 적용되지 않았습니다."
QUANTILE_NEEDS_RANKING = "분위 그룹 비교는 랭킹 지표(예: PER 낮은 순)가 있어야 실행됩니다 — 이번 실행에서는 그룹 비교를 계산하지 못했습니다."
QUANTILE_NEEDS_REBALANCE = "분위 그룹 비교는 정기 리밸런싱 주기가 있어야 실행됩니다 — 이번 실행에서는 그룹 비교를 계산하지 못했습니다."
QUANTILE_GROUPS_PURE_REBALANCE = "분위 그룹 비교({0}개 그룹)는 그룹별 순수 리밸런싱 기준으로 계산되었습니다 — 개별 손절/익절/보유기간 제한은 그룹 비교에 적용되지 않습니다. 메인 결과는 1그룹 포트폴리오입니다."
OVERFLOW_TIEBREAK = "매수 조건을 충족한 종목이 빈 자리(최대 보유 {0}종목)보다 많았던 날이 {1}일 있어(리밸런싱일 포함), 그날은 최근 {2}거래일 수익률이 높은 종목부터 우선 담았습니다."

# ── 벤치마크 ─────────────────────────────────────────────────────────────────
BENCHMARK_PARTIAL_PERIOD = "벤치마크({0}) 데이터가 {1}부터 존재합니다 — 그 이전 구간은 비교에서 제외되어, 벤치마크 수익률은 전략보다 짧은 기간을 기준으로 계산됩니다."
BENCHMARK_NO_DIVIDENDS = "벤치마크 ETF에 분배금 데이터가 없어 가격리턴 기준으로 비교됩니다 — 전략(배당 재투자 기본)이 상대적으로 유리하게 보일 수 있습니다."

# ── 거래 없음 ────────────────────────────────────────────────────────────────
NO_TRADES = "매매 기록이 생성되지 않았습니다. 매수 조건 또는 유동성/포지션 설정을 확인해 주세요."
NO_TRADES_LIQUIDITY_DETAIL = " (유동성 기준 미달로 제외된 종목 {0}개: {1} — 포지션 크기를 줄이거나 유동성 한도를 낮추면 포함될 수 있습니다)"
MORE_SYMBOLS = " 외 {0}종목"

# ── 리밸런싱 방식 고지 ───────────────────────────────────────────────────────
REBALANCE_WEIGHTS_ONLY = "리밸런싱일에는 보유 종목을 교체하지 않고 비중만 균등으로 되돌립니다(오른 종목은 일부 매도, 내린 종목은 추가 매수) — 목표 종목 수에 미달하는 빈 자리만 매수 조건 충족 종목으로 채웁니다. 매도 조건·손절/익절은 그대로 적용됩니다."
REBALANCE_RECONSTITUTE = "리밸런싱일에는 그날 매수 조건을 충족한 종목 중에서 포트폴리오를 다시 구성합니다(충족하지 않는 보유 종목은 편출) — 그 사이 날에도 매수 조건 충족 종목을 빈 자리만큼 담고 매도 조건은 그대로 적용합니다. 유지 종목의 비중은 목표 비중으로 리셋되지 않습니다."
REBALANCE_WITH_RISK_EXITS = "리밸런싱과 손절/익절/트레일링/보유기간 제한이 함께 설정되어 리밸런싱일에는 종목 교체만 수행합니다 — 유지 종목의 비중은 목표 비중으로 리셋되지 않습니다."

# ── 증권거래세 ───────────────────────────────────────────────────────────────
SELL_TAX_APPLIED = "매도 체결에 증권거래세 {0}%가 반영되었습니다."
SELL_TAX_APPLIED_WITH_RURAL = "매도 체결에 증권거래세 {0}%(농특세 포함)가 반영되었습니다."
SELL_TAX_SCHEDULE_APPLIED = "매도 체결에 증권거래세를 시행일 기준 세율({0}%→{1}%, 농특세 포함)로 반영했습니다 — 과거 매도에 현행 세율을 일괄 적용하지 않습니다."

# ── 통계 신뢰도·편향 ─────────────────────────────────────────────────────────
SHORT_PERIOD_ANNUALIZED = "백테스트 기간이 약 {0}개월(1년 미만)입니다 — CAGR·샤프·소르티노·변동성은 이 구간을 1년으로 연환산한 값이라 짧은 기간의 우연이 그대로 확대됩니다."
FEW_TRADES = "거래 수가 {0}건으로 30건 미만입니다 — 승률·Profit Factor 등 통계의 표본 신뢰도가 낮습니다."
AI_TRAIN_OVERLAP = "AI 모델 학습 데이터(~{0})와 백테스트 기간이 겹칩니다 — 겹치는 구간의 AI 신호 성과는 인샘플(낙관 편향)일 수 있습니다."
AI_VALIDATION_OVERLAP = "AI 모델 검증 데이터(~{0})와 백테스트 기간이 겹칩니다 — 신호 임계값이 이 구간으로 보정되어 겹치는 구간의 AI 신호 성과는 인샘플(낙관 편향)일 수 있습니다."
LIQUIDITY_LIMIT_EXCEEDED = "매수 {0}건이 전일 거래대금의 {1}%를 초과하는 규모입니다 — 실전에서는 시장충격으로 이 가격에 전량 체결되기 어려울 수 있습니다."

# ── 데이터 커버리지 (engine/data_coverage.py) ────────────────────────────────
COVERAGE_UNUSED_ALL_NEGATIVE = "⚠ {0} 조건은 이번 백테스트에서 적용되지 않았습니다 — 유효한 비율 값이 없었고, 이 중 {1}개 시점은 데이터 결측이 아니라 {2}으로 비율 산정이 불가한 경우였습니다."
COVERAGE_UNUSED_NO_DATA = "⚠ {0} 데이터가 현재 데이터셋(대상 종목·기간)에 존재하지 않아 이번 백테스트의 해당 조건은 적용되지 않았습니다."
COVERAGE_LOW_PERIOD = "⚠ 본 백테스트는 {0} 데이터가 전체 기간의 {1}%만 존재하여 결과 해석에 주의가 필요합니다."
COVERAGE_PARTIAL_SYMBOLS = "일부 종목({0}/{1})만 {2} 데이터가 있어 나머지 종목에는 해당 조건이 적용되지 않았습니다."
COVERAGE_NEGATIVE_EXCLUDED = "{0}은(는) 대상 종목·기간 중 {1}개 시점({2}%)이 {3}으로 비율 산정이 불가해 해당 조건 판정에서 제외됐습니다(데이터 결측과는 별개입니다)."
NEGATIVE_REASON_DEFAULT = "적자·자본잠식"
NEGATIVE_REASON_EPS = "적자(EPS ≤ 0)"
NEGATIVE_REASON_BPS = "자본잠식(BPS ≤ 0)"
NEGATIVE_REASON_EQUITY = "자본잠식(자기자본 ≤ 0)"


# ── 조립 헬퍼 ────────────────────────────────────────────────────────────────
def warning(template: str, *args: Any) -> str:
    """템플릿 하나짜리 경고 — 엔진의 문자열 경고 채널에 실을 인코딩 문자열."""
    return tr.encode([tr.part(template, *args)])


def compose(*segments: Segment) -> str:
    """세그먼트 여러 개로 이루어진 경고(문장 + 꼬리 괄호 등)."""
    return tr.encode(list(segments))


def label_list(labels: Iterable[str], separator: str = ", ") -> List[Segment]:
    """사전 키인 라벨(재무 지표 라벨 등)의 나열 — 각 라벨이 따로 번역되도록 중첩 세그먼트로."""
    return tr.join([[tr.part(label)] for label in labels], [tr.literal(separator)])


def symbol_of(encoded: Any) -> Optional[str]:
    """종목 단위 경고("{0}: …")의 종목 코드 — 첫 세그먼트의 첫 인자."""
    segments = tr.decode(encoded)
    if not segments:
        return None
    for seg in segments:
        if "t" in seg:
            args = seg.get("a") or []
            return str(args[0]) if args else None
    return None


def finalize(raw: Iterable[Any]) -> Tuple[List[str], List[List[Segment]]]:
    """경고 채널의 값들을 (한국어 문장 목록, 세그먼트 목록)으로 — 같은 순서·같은 길이.

    엔진의 경고 채널은 set이라 순서가 없다. 렌더링된 한국어 문장 기준으로 정렬해
    캐시·병렬 경로 사이에서도 결과가 결정적이게 한다. 평문 문자열(외부 라이브러리·구버전
    경로)은 리터럴 한 조각으로 그대로 통과한다.
    """
    pairs = sorted(((tr.text(value), tr.segments_of(value)) for value in raw), key=lambda p: p[0])
    return [text for text, _ in pairs], [segments for _, segments in pairs]
