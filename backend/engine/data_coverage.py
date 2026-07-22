"""백테스트 데이터 커버리지 추적 (FR-BT: 데이터 품질 투명성).

전략 조건이 참조하는 '데이터 의존 지표'(펀더멘털·거래대금)가 백테스트 창에서 실제로
얼마나 존재했는지를 종목·기간 두 축으로 집계한다. 목적은 데이터 부족을 숨기지 않고
결과 로그에 투명하게 드러내는 것이다.

기술적 지표(RSI·MA·MACD 등)는 OHLCV에서 항상 계산되므로 커버리지 변동이 없어
추적 대상에서 제외한다(웜업 구간 NaN은 별도 warmup 로직이 관리). 추적 대상은 값의
존재 여부가 종목·기간에 따라 달라지는 펀더멘털 지표다.

설계:
  - ``tracked_metrics``: 조건에서 참조된 데이터 의존 지표 키 목록(순서 보존).
  - ``symbol_stats``: 한 종목의 창(window) DataFrame에서 지표별 (전체행/유효행/최초·최종
    유효일)을 산출하는 순수 함수 — 스레드 안에서 호출해 결과에 실어 보낸다.
  - ``CoverageAccumulator``: 종목별 stats를 단일 스레드에서 접어 최종 리포트를 만든다.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from .signals import FUNDAMENTAL_CIDS, FUNDAMENTAL_LABELS

# 값의 존재가 종목/기간에 따라 달라지는 데이터 의존 지표 = 펀더멘털 지표.
_DATA_DEPENDENT_METRICS = set(FUNDAMENTAL_CIDS)

# 커버리지가 이 값 미만이면 '부분 사용'으로 분류하고 경고 후보로 본다.
_PARTIAL_PERIOD_THRESHOLD = 95.0
# 필터 조건인데 이 값 미만이면 결과 해석 주의 경고를 낸다.
_LOW_COVERAGE_WARN_THRESHOLD = 60.0
# 음수(적자·자본잠식) 제외 비중이 이 값 이상이면 결측과 구분한 팩트 라인을 낸다.
_NEGATIVE_EXCLUSION_WARN_THRESHOLD = 10.0

# fundamental_fetcher는 적자·자본잠식이면 비율 자체가 금융적으로 무의미해 값을 null 처리한다
# (per: EPS≤0, pbr: BPS≤0, roe: 자기자본≤0). 그 결과가 커버리지에서 '데이터 결측'과 뭉개지지
# 않도록, 여기서 분모의 부호로 '음수 제외' 행을 재구성해 결측과 분리 집계한다.
# 판정: metric 값이 NaN & 분모 컬럼 존재 & 분모 ≤ 0 (fetcher의 null 규칙과 동일).
# roe_or_gpa는 total_equity 우선, 없으면 BPS로 근사 — fetcher와 동일한 폴백.
_NEGATIVE_EXCLUSION_RULES: Dict[str, Dict[str, Any]] = {
    "per": {"denoms": ("eps",), "reason": "적자(EPS ≤ 0)"},
    "pbr": {"denoms": ("bps",), "reason": "자본잠식(BPS ≤ 0)"},
    "roe_or_gpa": {"denoms": ("total_equity", "bps"), "reason": "자본잠식(자기자본 ≤ 0)"},
}


def _collect_leaf_conditions(group: Optional[Dict]) -> List[Dict]:
    if not group:
        return []
    out: List[Dict] = []
    for c in group.get("conditions", []):
        if "conditions" in c:
            out.extend(_collect_leaf_conditions(c))
        else:
            out.append(c)
    return out


def tracked_metrics(entry_group: Optional[Dict], exit_group: Optional[Dict]) -> List[str]:
    """조건에서 참조된 데이터 의존 지표 키를 순서 보존해 반환한다(중복 제거)."""
    seen: Dict[str, None] = {}
    for cond in _collect_leaf_conditions(entry_group) + _collect_leaf_conditions(exit_group):
        cid = cond.get("id", "")
        if cid in _DATA_DEPENDENT_METRICS and cid not in seen:
            seen[cid] = None
    return list(seen)


def symbol_stats(pdf: pd.DataFrame, metrics: List[str]) -> Dict[str, Dict[str, Any]]:
    """한 종목 창 DataFrame에서 지표별 커버리지 원자료를 산출한다(순수 함수).

    Returns: {metric: {"rows_total", "rows_valid", "first_valid", "last_valid"}}.
    컬럼이 아예 없으면 rows_valid=0 (백필 안 된 과거 parquet 대응).
    """
    rows_total = int(len(pdf))
    # preprocess_data 이후 date는 인덱스로 이동한다 — 컬럼이 없으면 인덱스를 날짜로 쓴다.
    if "date" in pdf.columns:
        dates = pd.Series(pdf["date"].values)
    elif isinstance(pdf.index, pd.DatetimeIndex):
        dates = pd.Series(pdf.index)
    else:
        dates = None
    out: Dict[str, Dict[str, Any]] = {}
    for metric in metrics:
        stat: Dict[str, Any] = {
            "rows_total": rows_total,
            "rows_valid": 0,
            # NaN 중 '적자·자본잠식이라 fetcher가 null 처리한' 행 수 — 진짜 결측과 구분.
            "rows_excluded_negative": 0,
            "first_valid": None,
            "last_valid": None,
        }
        if metric in pdf.columns and rows_total > 0:
            na_mask = pdf[metric].isna()
            valid_mask = ~na_mask
            valid_count = int(valid_mask.sum())
            stat["rows_valid"] = valid_count
            if valid_count > 0 and dates is not None:
                valid_dates = dates[valid_mask.values]
                stat["first_valid"] = str(pd.Timestamp(valid_dates.min()).date())
                stat["last_valid"] = str(pd.Timestamp(valid_dates.max()).date())
            stat["rows_excluded_negative"] = _count_negative_excluded(pdf, metric, na_mask)
        out[metric] = stat
    return out


def _count_negative_excluded(pdf: pd.DataFrame, metric: str, na_mask: pd.Series) -> int:
    """metric이 NaN인 행 중, 분모가 비양수(적자·자본잠식)여서 제외된 행 수를 센다.

    fetcher가 값을 null 처리한 사유를 커버리지 시점에 분모 부호로 재구성한다. 분모 컬럼이
    없으면(백필 안 된 과거 parquet) 0을 반환해 안전하게 퇴화한다.
    """
    rule = _NEGATIVE_EXCLUSION_RULES.get(metric)
    if not rule:
        return 0
    denom_col = next((d for d in rule["denoms"] if d in pdf.columns), None)
    if denom_col is None:
        return 0
    denom = pdf[denom_col]
    excluded = na_mask & denom.notna() & (denom <= 0)
    return int(excluded.sum())


class CoverageAccumulator:
    """종목별 symbol_stats를 단일 스레드에서 접어 최종 리포트를 만든다."""

    def __init__(self, metrics: List[str]):
        self.metrics = metrics
        self._agg: Dict[str, Dict[str, Any]] = {
            m: {
                "rows_total": 0,
                "rows_valid": 0,
                "rows_excluded_negative": 0,
                "symbols_total": 0,
                "symbols_with_data": 0,
                "first_valid": None,
                "last_valid": None,
            }
            for m in metrics
        }

    def fold(self, per_symbol: Dict[str, Dict[str, Any]]) -> None:
        for metric, stat in per_symbol.items():
            agg = self._agg.get(metric)
            if agg is None:
                continue
            agg["rows_total"] += stat["rows_total"]
            agg["rows_valid"] += stat["rows_valid"]
            agg["rows_excluded_negative"] += stat.get("rows_excluded_negative", 0)
            agg["symbols_total"] += 1
            if stat["rows_valid"] > 0:
                agg["symbols_with_data"] += 1
                if stat["first_valid"] is not None:
                    agg["first_valid"] = (
                        stat["first_valid"]
                        if agg["first_valid"] is None
                        else min(agg["first_valid"], stat["first_valid"])
                    )
                    agg["last_valid"] = (
                        stat["last_valid"]
                        if agg["last_valid"] is None
                        else max(agg["last_valid"], stat["last_valid"])
                    )

    def build(self) -> Dict[str, Any]:
        """구조화된 커버리지 리포트 + 사용자 경고 목록을 반환한다."""
        metric_reports: List[Dict[str, Any]] = []
        used, partial, unused = [], [], []
        warnings: List[str] = []

        for metric in self.metrics:
            agg = self._agg[metric]
            label = FUNDAMENTAL_LABELS.get(metric, metric.upper())
            rows_total = agg["rows_total"]
            symbols_total = agg["symbols_total"]
            period_pct = round(agg["rows_valid"] / rows_total * 100.0, 1) if rows_total else 0.0
            symbol_pct = (
                round(agg["symbols_with_data"] / symbols_total * 100.0, 1) if symbols_total else 0.0
            )
            neg_rows = agg["rows_excluded_negative"]
            neg_pct = round(neg_rows / rows_total * 100.0, 1) if rows_total else 0.0
            neg_reason = _NEGATIVE_EXCLUSION_RULES.get(metric, {}).get("reason", "적자·자본잠식")

            if agg["symbols_with_data"] == 0:
                status = "unused"
                unused.append(label)
            elif period_pct < _PARTIAL_PERIOD_THRESHOLD or symbol_pct < 100.0:
                status = "partial"
                partial.append(label)
            else:
                status = "used"
                used.append(label)

            metric_reports.append({
                "key": metric,
                "label": label,
                "status": status,
                "periodCoveragePct": period_pct,
                "symbolCoveragePct": symbol_pct,
                "symbolsWithData": agg["symbols_with_data"],
                "symbolsTotal": symbols_total,
                # 결측이 아니라 적자·자본잠식이라 비율 산정 불가로 제외된 행(진짜 결측과 분리).
                "negativeExcludedRows": neg_rows,
                "negativeExcludedPct": neg_pct,
                "availableFrom": agg["first_valid"],
                "availableTo": agg["last_valid"],
            })

            if status == "unused":
                if neg_rows > 0:
                    # 값이 존재했으나 전부 비율 산정 불가 — '데이터 없음'으로 오인되지 않게 정정.
                    warnings.append(
                        f"⚠ {label} 조건은 이번 백테스트에서 적용되지 않았습니다 — 유효한 비율 값이 "
                        f"없었고, 이 중 {neg_rows}개 시점은 데이터 결측이 아니라 {neg_reason}으로 "
                        f"비율 산정이 불가한 경우였습니다."
                    )
                else:
                    warnings.append(
                        f"⚠ {label} 데이터가 현재 데이터셋(대상 종목·기간)에 존재하지 않아 "
                        f"이번 백테스트의 해당 조건은 적용되지 않았습니다."
                    )
            elif period_pct < _LOW_COVERAGE_WARN_THRESHOLD:
                warnings.append(
                    f"⚠ 본 백테스트는 {label} 데이터가 전체 기간의 {period_pct}%만 존재하여 "
                    f"결과 해석에 주의가 필요합니다."
                )
            elif symbol_pct < 100.0:
                warnings.append(
                    f"일부 종목({agg['symbols_with_data']}/{symbols_total})만 {label} 데이터가 있어 "
                    f"나머지 종목에는 해당 조건이 적용되지 않았습니다."
                )

            # 음수(적자·자본잠식) 제외가 유의미하면, 위 결측 경고와 별개로 사유를 명시한다.
            # (unused 경로는 이미 위에서 음수 사유를 반영했으므로 중복 고지하지 않는다.)
            if status != "unused" and neg_pct >= _NEGATIVE_EXCLUSION_WARN_THRESHOLD:
                warnings.append(
                    f"{label}은(는) 대상 종목·기간 중 {neg_rows}개 시점({neg_pct}%)이 {neg_reason}으로 "
                    f"비율 산정이 불가해 해당 조건 판정에서 제외됐습니다(데이터 결측과는 별개입니다)."
                )

        return {
            # 항상 존재하는 기반 데이터(참고용) — 사용자가 '무엇으로 계산됐는지' 한눈에 보도록.
            "baseData": ["시가", "고가", "저가", "종가", "거래량"],
            "metrics": metric_reports,
            "usedData": used,
            "partialData": partial,
            "unusedData": unused,
            "warnings": warnings,
        }
