"""Trace 보관 정책 — 원문 3일 보관, 집계 후 폐기 (사용자 결정 2026-08-11).

Trace JSONL에는 사용자 발화 원문이 들어 있다. 원문의 용도(커버리지 분석·사고 조사)는
최근 며칠이면 충분하므로 **딱 3일**만 보관한다. 폐기 전에 원문이 없는 집계(라벨 분포·
게이트/사실 조회 건수)만 요약 파일에 남긴다 — 장기 추이는 집계로, 원문은 단기로.

동작 방식: 별도 cron 없이 **Trace가 기록될 때마다 하루 한 번** 스윕이 돈다(local_trace
._emit 훅). Trace가 쓰이는 곳(dev·prod)이면 어디서든 자동으로 정리되고, Trace가 꺼진
환경(AGENT_TRACE_LOCAL=0)에는 정리할 파일도 생기지 않는다.

계약은 관찰 계층과 같다: 정리 실패가 실행을 깨뜨리지 않는다. 단, 집계 실패는 폐기를
막지 않는다 — 보관 기한이 정책이고 집계는 부가물이다(원문을 더 들고 있는 쪽이 위반).
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import threading
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

logger = logging.getLogger("observability.retention")

# 보관 일수(당일 포함). 3 = 오늘·어제·그제 파일만 남는다.
RETENTION_DAYS = 3

# 원문 없는 일별 집계가 쌓이는 파일(하루 한 줄). 날짜 형식 이름이 아니라 스윕 대상에서
# 자연히 제외된다.
SUMMARY_FILENAME = "coverage-summary.jsonl"

_sweep_lock = threading.Lock()
_last_sweep_date: Optional[_dt.date] = None


def maybe_sweep(trace_dir: Path, today: Optional[_dt.date] = None) -> None:
    """하루 한 번(프로세스 기준) 보관 기한을 넘긴 Trace 파일을 집계 후 폐기한다."""
    global _last_sweep_date
    today = today or _dt.date.today()
    with _sweep_lock:
        if _last_sweep_date == today:
            return
        _last_sweep_date = today
    try:
        sweep(trace_dir, today)
    except Exception:  # noqa: BLE001 — 정리 실패가 실행을 막지 않는다
        logger.debug("trace 보관 정리 실패", exc_info=True)


def sweep(trace_dir: Path, today: _dt.date) -> list[Path]:
    """기한(오늘 포함 RETENTION_DAYS일)을 넘긴 날짜 파일을 집계 후 삭제한다."""
    if not trace_dir.exists():
        return []
    cutoff = today - _dt.timedelta(days=RETENTION_DAYS - 1)
    removed: list[Path] = []
    for path in sorted(trace_dir.glob("*.jsonl")):
        try:
            file_date = _dt.date.fromisoformat(path.stem)
        except ValueError:
            continue  # coverage-summary 등 날짜 형식이 아닌 파일은 대상이 아니다
        if file_date >= cutoff:
            continue
        summary = None
        try:
            summary = _summarize(path, file_date)
        except Exception:  # noqa: BLE001 — 집계 실패가 폐기를 막지 않는다
            logger.debug("trace 집계 실패 — 집계 없이 폐기 | %s", path.name, exc_info=True)
        if summary is not None:
            try:
                with open(trace_dir / SUMMARY_FILENAME, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(summary, ensure_ascii=False) + "\n")
            except Exception:  # noqa: BLE001
                logger.debug("trace 집계 기록 실패 | %s", path.name, exc_info=True)
        path.unlink(missing_ok=True)
        removed.append(path)
        logger.info("trace 원문 폐기(3일 보관 정책) | %s", path.name)
    return removed


def _walk(node: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
    yield node
    for child in node.get("children") or []:
        yield from _walk(child)


def _summarize(path: Path, file_date: _dt.date) -> Dict[str, Any]:
    """원문 없는 일별 집계 — report_intent_coverage와 같은 축(라벨·게이트·사실 조회).

    사용자 텍스트(query·답변)는 어떤 필드에도 싣지 않는다. 여기서 세는 것은 개수뿐이다.
    """
    traces = 0
    roots: Counter = Counter()
    intents: Counter = Counter()
    fact_metrics = 0
    list_scopes = 0
    failures = 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            traces += 1
            roots[str(record.get("root"))] += 1
            span = record.get("span")
            if not isinstance(span, dict):
                continue
            for node in _walk(span):
                if node.get("name") != "Classifier · 의도 분류":
                    continue
                outputs = node.get("outputs") or {}
                intents[str(outputs.get("intent"))] += 1
                fact_metrics += bool(outputs.get("fact_metric"))
                list_scopes += bool(outputs.get("list_scope"))
                failures += bool(outputs.get("interpretation_failed"))
    return {
        "date": file_date.isoformat(),
        "traces": traces,
        "roots": dict(roots),
        "classify_intents": dict(intents),
        "fact_metric_answers": fact_metrics,
        "list_scope_answers": list_scopes,
        "interpretation_failures": failures,
    }
