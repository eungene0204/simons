"""AI 리포트용 코퍼스 비교 통계.

동일 엔진으로 실행된 과거 전략 시뮬레이션 코퍼스(corpus_insights_data.jsonl.gz,
scripts/export_corpus_insights.py 산출물)와 현재 백테스트 결과를 결정론적으로 비교한다.

- 구조 유사 전략 코호트(structural_similarity) 내 백분위(CAGR/MDD/샤프/승률)
- 사용자 전략에 없는 리스크/구조 장치의 유무별 코호트 중앙값 대조(과거 통계 서술)

LLM은 여기서 만든 수치·문장만 인용해 총평을 서술한다(환각 방지). 코퍼스 파일이
없거나 손상되면 None을 반환해 리포트는 기존 형태로 동작한다.
"""

from __future__ import annotations

import gzip
import json
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .similarity import StructuralFeatures, extract_structural_features, structural_similarity

_DATA_PATH = Path(__file__).resolve().parent / "corpus_insights_data.jsonl.gz"

# 유사 코호트 성립 조건 — 미달 시 전체 코퍼스와 비교한다.
_SIMILARITY_THRESHOLD = 0.5
_MIN_COHORT = 30
# 조건부 대조는 양쪽 그룹이 이만큼은 있어야 중앙값 비교가 의미 있다.
_MIN_CONTRAST_GROUP = 30

_corpus_cache: Optional[List[Dict[str, Any]]] = None


def _load_corpus() -> List[Dict[str, Any]]:
    """코퍼스 로드(프로세스 1회). 각 행: metrics + strategy_dsl + 미리 계산한 features."""
    global _corpus_cache
    if _corpus_cache is not None:
        return _corpus_cache

    rows: List[Dict[str, Any]] = []
    if _DATA_PATH.exists():
        try:
            with gzip.open(_DATA_PATH, "rt", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    metrics = row.get("metrics") or {}
                    if metrics.get("cagr") is None or metrics.get("mdd") is None:
                        continue
                    dsl = row.get("strategy_dsl") or {}
                    rows.append({
                        "metrics": metrics,
                        "dsl": dsl,
                        "features": extract_structural_features(dsl),
                    })
        except OSError:
            rows = []
    _corpus_cache = rows
    return rows


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct_to_fraction(value: Any) -> Optional[float]:
    f = _to_float(value)
    return f / 100.0 if f is not None else None


def _beat_share(user_value: float, cohort_values: List[float], higher_is_better: bool) -> Optional[float]:
    """코호트에서 사용자가 이긴 비율(0~1)."""
    values = [v for v in cohort_values if v is not None]
    if not values:
        return None
    if higher_is_better:
        beaten = sum(1 for v in values if user_value > v)
    else:
        beaten = sum(1 for v in values if user_value < v)
    return beaten / len(values)


def _rank_phrase(beat_share: float) -> str:
    """오독 불가능한 순위 표현 — 중앙값 위면 '상위 X%', 아래면 '하위 X%'.

    '상위 79%' 같은 표현은 LLM이 '높은 순위'로 오독한다(실측). 백분위가 중앙값
    아래일 때는 반드시 '하위'로 서술해 해석 여지를 없앤다.
    """
    pct = round(beat_share * 100)
    if pct >= 50:
        return f"상위 {max(1, 100 - pct)}%"
    return f"하위 {max(1, pct)}%"


def _median(values: List[Optional[float]]) -> Optional[float]:
    cleaned = [v for v in values if v is not None]
    return statistics.median(cleaned) if cleaned else None


def _has_stop(dsl: Dict[str, Any]) -> bool:
    return _to_float(dsl.get("stop_loss_pct")) is not None or _to_float(dsl.get("trailing_stop_pct")) is not None


def _has_take_profit(dsl: Dict[str, Any]) -> bool:
    return _to_float(dsl.get("take_profit_pct")) is not None


def _has_rebalancing(dsl: Dict[str, Any]) -> bool:
    period = dsl.get("rebalancing_period")
    return bool(period) and str(period) != "none"


def _is_diversified(dsl: Dict[str, Any]) -> bool:
    positions = _to_float(dsl.get("max_positions"))
    return positions is not None and positions >= 5


# (라벨, 판정 함수, 대조 지표 키, 지표 라벨, 지표 포맷터)
_CONTRAST_KNOBS: List[Tuple[str, Any, str, str]] = [
    ("손절(또는 트레일링 스탑)", _has_stop, "mdd", "최대 낙폭(MDD) 중앙값"),
    ("익절", _has_take_profit, "cagr", "CAGR 중앙값"),
    ("정기 리밸런싱", _has_rebalancing, "cagr", "CAGR 중앙값"),
    ("5종목 이상 분산", _is_diversified, "mdd", "최대 낙폭(MDD) 중앙값"),
]


def _fmt_pct(fraction: Optional[float]) -> str:
    return f"{fraction * 100:.2f}%" if fraction is not None else "N/A"


def _build_contrast_lines(parsed_strategy: Dict[str, Any], cohort: List[Dict[str, Any]]) -> List[str]:
    """사용자 전략에 '없는' 장치에 한해, 코호트 내 유무별 중앙값 대조 통계를 만든다.

    과거 데이터 서술만 한다("~였습니다") — 추천/전망 표현은 프롬프트 규칙이 별도로 금지한다.
    """
    lines: List[str] = []
    for label, predicate, metric_key, metric_label in _CONTRAST_KNOBS:
        if predicate(parsed_strategy):
            continue  # 이미 갖춘 장치는 대조 불필요
        with_group = [r["metrics"].get(metric_key) for r in cohort if predicate(r["dsl"])]
        without_group = [r["metrics"].get(metric_key) for r in cohort if not predicate(r["dsl"])]
        if len(with_group) < _MIN_CONTRAST_GROUP or len(without_group) < _MIN_CONTRAST_GROUP:
            continue
        with_median = _median(with_group)
        without_median = _median(without_group)
        if with_median is None or without_median is None:
            continue
        lines.append(
            f"이 전략처럼 {label} 없이 운용된 비교군 {len(without_group)}개의 {metric_label}은 "
            f"{_fmt_pct(without_median)}, {label}을 둔 비교군 {len(with_group)}개는 "
            f"{_fmt_pct(with_median)}였습니다."
        )
        if len(lines) >= 2:
            break
    return lines


def build_corpus_comparison(
    parsed_strategy: Optional[Dict[str, Any]],
    metrics: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """현재 백테스트 지표를 코퍼스 분포와 비교한 결정론적 통계를 반환한다.

    metrics 는 프론트 리포트 지표(퍼센트 단위: cagr=12.3, maxDrawdown=-20.9, winRate=54.0).
    반환값의 lines 는 LLM 프롬프트에 그대로 주입 가능한 완성 문장 목록이다.
    """
    metrics = metrics or {}
    user_cagr = _pct_to_fraction(metrics.get("cagr"))
    if user_cagr is None:
        return None

    corpus = _load_corpus()
    if len(corpus) < _MIN_COHORT:
        return None

    user_mdd = _pct_to_fraction(metrics.get("maxDrawdown"))
    if user_mdd is not None and user_mdd > 0:
        user_mdd = -user_mdd
    user_sharpe = _to_float(metrics.get("sharpe"))
    user_win_rate = _pct_to_fraction(metrics.get("winRate"))

    # ── 코호트 선정: 구조 유사 전략, 부족하면 전체 코퍼스 ─────────────────────
    cohort = corpus
    cohort_label = f"동일 엔진으로 실행된 과거 전략 시뮬레이션 {len(corpus)}개"
    if parsed_strategy:
        try:
            user_features: StructuralFeatures = extract_structural_features(parsed_strategy)
            similar = [
                row for row in corpus
                if structural_similarity(user_features, row["features"]) >= _SIMILARITY_THRESHOLD
            ]
            if len(similar) >= _MIN_COHORT:
                cohort = similar
                cohort_label = f"구조가 유사한 과거 전략 시뮬레이션 {len(similar)}개(전체 {len(corpus)}개 중)"
        except Exception:
            pass  # 특징 추출 실패 시 전체 코퍼스 비교로 진행

    lines: List[str] = []

    cagr_values = [row["metrics"].get("cagr") for row in cohort]
    cagr_beat = _beat_share(user_cagr, cagr_values, higher_is_better=True)
    cagr_median = _median(cagr_values)
    if cagr_beat is not None and cagr_median is not None:
        direction = "높음" if user_cagr >= cagr_median else "낮음"
        lines.append(
            f"CAGR {_fmt_pct(user_cagr)}는 비교군 {_rank_phrase(cagr_beat)} 수준 (비교군 중앙값 {_fmt_pct(cagr_median)} 대비 {direction})."
        )

    if user_mdd is not None:
        mdd_values = [row["metrics"].get("mdd") for row in cohort]
        mdd_beat = _beat_share(user_mdd, mdd_values, higher_is_better=True)  # 덜 깊을수록(큰 값) 우수
        mdd_median = _median(mdd_values)
        if mdd_beat is not None and mdd_median is not None:
            depth = "얕은" if user_mdd >= mdd_median else "깊은"
            lines.append(
                f"최대 낙폭 {_fmt_pct(user_mdd)}의 방어력은 비교군 {_rank_phrase(mdd_beat)} 수준 (비교군 중앙값 {_fmt_pct(mdd_median)}보다 {depth} 낙폭)."
            )

    if user_sharpe is not None:
        sharpe_values = [row["metrics"].get("sharpe") for row in cohort]
        sharpe_beat = _beat_share(user_sharpe, sharpe_values, higher_is_better=True)
        sharpe_median = _median(sharpe_values)
        if sharpe_beat is not None and sharpe_median is not None:
            direction = "높음" if user_sharpe >= sharpe_median else "낮음"
            lines.append(
                f"샤프 지수 {user_sharpe:.2f}는 비교군 {_rank_phrase(sharpe_beat)} 수준 (비교군 중앙값 {sharpe_median:.2f} 대비 {direction})."
            )

    if user_win_rate is not None:
        win_values = [row["metrics"].get("win_rate") for row in cohort]
        win_beat = _beat_share(user_win_rate, win_values, higher_is_better=True)
        win_median = _median(win_values)
        if win_beat is not None and win_median is not None:
            direction = "높음" if user_win_rate >= win_median else "낮음"
            lines.append(
                f"승률 {_fmt_pct(user_win_rate)}는 비교군 {_rank_phrase(win_beat)} 수준 (비교군 중앙값 {_fmt_pct(win_median)} 대비 {direction})."
            )

    if not lines:
        return None

    contrast_lines = _build_contrast_lines(parsed_strategy or {}, cohort) if parsed_strategy else []

    return {
        "cohort_label": cohort_label,
        "cohort_size": len(cohort),
        "corpus_size": len(corpus),
        "lines": lines,
        "contrast_lines": contrast_lines,
    }
