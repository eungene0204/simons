"""Trace 실패 분류(triage) — "무엇이 실패했나"를 구조 신호로 묶는다.

관찰 계층이 남긴 Trace(logs/agent_traces/*.jsonl)를 훑어, 실패 후보를 **신호 종류 ×
판별 키**로 묶고 묶음마다 대표 사례(trace_id·발화)를 붙인다. 쓰는 곳은 둘이다 —
CLI(backend/scripts/triage_traces.py, 세션 시작 요약·리포트)와 운영 콘솔 실패 분류 탭
(GET /admin/trace-triage).

판정 계약(CLAUDE.md 대원칙 1):
- 판정은 **시스템이 남긴 구조 필드만** 본다 — span 오류, 검증기 보고(errors·
  unsupported_features), 컴파일러 dropped·pending_conditions, Responder의
  clarification_priority, 우리가 낸 질문 문장의 동일성.
- 사용자 원문(user_input)은 **표본으로 옮겨 적기만** 한다. 원문을 읽어 실패 여부·종류를
  판정하지 않는다(정규식·어휘 목록 금지).
- 오류 문자열에서 예외 클래스명을 떼는 것은 시스템 출력의 표기 정규화다.

이 모듈은 **읽기 전용**이다 — Trace를 고치지도, 실행 경로를 건드리지도 않는다.
"""

from __future__ import annotations

import datetime as dt
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from observability.local_trace import trace_dir as default_trace_dir

_AGENT_ROOT = "NullStock Strategy Agent"
_CLASSIFY_SPAN = "Classifier · 의도 분류"
_INTERPRETER_SPAN = "Interpreter · 전략 해석"
_PLANNER_SPAN = "Planner · Action DAG"
_VALIDATE_SPAN = "Tool · validate_intent"
_COMPILE_SPAN = "Tool · compile_strategy"

# 우리 코드가 아니라 바깥(LLM 상류·네트워크·사용자 취소)에서 온 오류 — 결함과 섞지 않는다.
_INFRA_ERRORS = frozenset({
    "HTTPError", "URLError", "TimeoutError", "ConnectionError", "ReadTimeout",
    "RemoteDisconnected", "OperationCancelled", "KeyboardInterrupt", "CancelledError",
})
# 프록시 타임아웃 근처(9B 폴백 복합 전략 257초 사고) — 사용자는 실패로 본다.
_SLOW_MS = 120_000
# Responder가 "해석은 됐는데 반영을 못 했다"로 끝낸 우선순위 라벨.
_FAILURE_PRIORITIES = frozenset({"modify_unapplied", "sector_unresolved"})

TIERS = ("결함 후보", "확인 필요", "제품 공백", "인프라")

# 신호 → (등급, 설명). 설명은 리포트 머리글이다.
SIGNALS: Dict[str, tuple] = {
    "interpreter_error": ("결함 후보", "인터프리터가 오류로 끝남(스키마 복구 실패 등)"),
    "planner_error": ("결함 후보", "플래너가 결론 없이 끝남(턴 예산 소진·같은 DAG 재발행)"),
    "span_error": ("결함 후보", "그 밖의 단계 오류"),
    "classifier_failed": ("결함 후보", "의도 분류가 해석 실패로 끝남"),
    "modify_unapplied": ("결함 후보", "수정 요청을 반영하지 못하고 되물음"),
    "sector_unresolved": ("결함 후보", "업종·테마를 정본에 결속하지 못함"),
    "ask_repeat": ("결함 후보", "답을 받고도 같은 질문을 다시 함(답 흡수 실패)"),
    "dropped_condition": ("결함 후보", "조건이 컴파일되지 못해 빠짐(미반영 안내는 나감) — 칸 오배정·엔진 부재"),
    "validation_error": ("확인 필요", "검증기 오류로 턴이 끝남(의도된 거절일 수 있음)"),
    "approximated": ("확인 필요", "조건을 근사로 반영함"),
    "unsupported": ("제품 공백", "LLM·검증기가 미지원으로 신고한 개념"),
    "infra_error": ("인프라", "LLM 상류·네트워크·취소 오류"),
    "slow_turn": ("인프라", f"턴이 {_SLOW_MS // 1000}초를 넘김"),
}

_SAMPLE_LIMIT = 3
_TEXT_LIMIT = 100


# ── 읽기 ─────────────────────────────────────────────────────────────────────

def trace_files(trace_dir: Path, days: Optional[int], today: Optional[dt.date] = None) -> List[Path]:
    if not trace_dir.exists():
        return []
    files = []
    for path in sorted(trace_dir.glob("*.jsonl")):
        try:
            dt.date.fromisoformat(path.stem)
        except ValueError:
            continue  # coverage-summary.jsonl 같은 비날짜 파일
        files.append(path)
    if days is None:
        return files
    cutoff = (today or dt.date.today()) - dt.timedelta(days=days - 1)
    return [f for f in files if f.stem >= cutoff.isoformat()]


def iter_records(files: List[Path]) -> Iterator[Dict[str, Any]]:
    for path in files:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(record.get("span"), dict):
                    yield record


def _walk(node: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
    yield node
    for child in node.get("children") or []:
        yield from _walk(child)


def _last(span: Dict[str, Any], name: str) -> Optional[Dict[str, Any]]:
    """같은 이름 span 중 마지막 것 — 턴 안의 재시도·재검증 뒤 최종 상태."""
    found = None
    for node in _walk(span):
        if node.get("name") == name:
            found = node
    return found


def error_class(error: str) -> str:
    """시스템 오류 문자열의 예외 클래스명. '[Kind] 메시지'와 'Class: 메시지' 두 표기."""
    text = (error or "").strip()
    if text.startswith("[") and "]" in text:
        return text[1:text.index("]")]
    return text.split(":", 1)[0].strip() or "Error"


# ── 판정 ─────────────────────────────────────────────────────────────────────

def classify(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Trace 하나에서 실패 신호 목록을 뽑는다. 각 항목은 {signal, key, detail}."""
    span = record["span"]
    findings: List[Dict[str, Any]] = []

    def add(signal: str, key: str, detail: Any = None) -> None:
        findings.append({"signal": signal, "key": key, "detail": detail})

    # ① span 오류 — 인프라와 결함을 예외 클래스로 가른다.
    for node in _walk(span):
        error = node.get("error")
        if not error:
            continue
        cls = error_class(error)
        name = node.get("name") or "?"
        if cls in _INFRA_ERRORS:
            add("infra_error", f"{name} · {cls}", error)
        elif name == _INTERPRETER_SPAN:
            add("interpreter_error", cls, error)
        elif name == _PLANNER_SPAN:
            add("planner_error", cls, error)
        elif node is not span:  # 루트 오류는 자식 오류의 전파라 중복으로 세지 않는다
            add("span_error", f"{name} · {cls}", error)
    if any(f["signal"] == "infra_error" for f in findings):
        # 같은 상류 오류가 LLM·인터프리터·루트로 전파돼 여러 줄이 된다 — 턴당 하나로.
        first = next(f for f in findings if f["signal"] == "infra_error")
        findings = [f for f in findings if f["signal"] != "infra_error"] + [first]

    if (record.get("total_ms") or 0) > _SLOW_MS:
        add("slow_turn", f">{_SLOW_MS // 1000}s", f"{record['total_ms'] / 1000:.0f}초")

    if record.get("root") == _CLASSIFY_SPAN:
        if (span.get("outputs") or {}).get("interpretation_failed"):
            add("classifier_failed", str((span.get("outputs") or {}).get("intent")))
        return findings

    if record.get("root") != _AGENT_ROOT:
        return findings

    inputs = span.get("inputs") or {}
    outputs = span.get("outputs") or {}

    # ② Responder 우선순위 라벨 — 해석 뒤 반영 실패로 끝난 턴.
    priority = outputs.get("clarification_priority")
    if priority in _FAILURE_PRIORITIES:
        add(priority, priority, outputs.get("clarification_question"))

    # ③ 같은 질문 반복 — 우리가 낸 질문 문장의 동일성만 본다(답 내용은 읽지 않는다).
    asked = inputs.get("pending_question")
    if asked and asked == outputs.get("clarification_question"):
        add("ask_repeat", (asked or "")[:60], asked)

    # ④ 컴파일러가 뺀 조건 중 값 대기(pending)로 올라가지 않은 것 — 컴파일 불가로 빠진 조건.
    #    안내(_unexplained_drop_notices)는 항상 나가므로 "조용한" 누락은 아니다. 말한 조건이 빠진 결과가 신호다.
    compiled = _last(span, _COMPILE_SPAN)
    observation = ((compiled or {}).get("outputs") or {}).get("observation") or {}
    pending = {p.get("label") for p in observation.get("pending_conditions") or []
               if isinstance(p, dict)}
    for label in observation.get("dropped") or []:
        if label not in pending:
            add("dropped_condition", str(label))

    # ⑤ 최종 검증 보고 — 오류·미지원.
    validated = _last(span, _VALIDATE_SPAN)
    vobs = ((validated or {}).get("outputs") or {}).get("observation") or {}
    report = vobs.get("report") or {}
    intent = vobs.get("intent") or {}
    if report.get("errors") and outputs.get("outcome") != "answer":
        for err in report["errors"]:
            add("validation_error", str(err)[:_TEXT_LIMIT], err)
    unsupported = {str(u) for u in (report.get("unsupported_features") or [])}
    unsupported |= {str(u) for u in (intent.get("unsupported_features") or [])}
    for feature in sorted(unsupported):
        add("unsupported", feature[:_TEXT_LIMIT])

    # ⑥ 근사 반영 — 인터프리터가 approximated로 신고한 조건.
    interp = _last(span, _INTERPRETER_SPAN)
    strategy = ((interp or {}).get("outputs") or {}).get("strategy") or {}
    for slot in ("entry_conditions", "exit_conditions"):
        for cond in strategy.get(slot) or []:
            if isinstance(cond, dict) and cond.get("approximated"):
                add("approximated", str(cond.get("factor") or cond.get("indicator") or "?"),
                    cond.get("source_text"))

    return findings


# ── 묶기 ─────────────────────────────────────────────────────────────────────

def _clip(text: Any) -> str:
    rendered = "" if text is None else str(text).replace("\n", " ")
    return rendered if len(rendered) <= _TEXT_LIMIT else rendered[:_TEXT_LIMIT] + "…"


def triage(records: Iterator[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """신호 × 판별 키로 묶은 그룹 목록. 등급 순 → 건수 내림차순."""
    groups: Dict[tuple, Dict[str, Any]] = {}
    sessions: Dict[tuple, set] = defaultdict(set)
    for record in records:
        span = record["span"]
        meta = span.get("metadata") or {}
        query = (span.get("inputs") or {}).get("user_input") or (span.get("inputs") or {}).get("query")
        # 루트 metadata.model은 실제 레인 모델이 아니다 — 인터프리터 span이 찍은 모델을 쓴다.
        model = ((_last(span, _INTERPRETER_SPAN) or {}).get("metadata") or {}).get("model")
        for finding in classify(record):
            gkey = (finding["signal"], finding["key"])
            tier, label = SIGNALS[finding["signal"]]
            group = groups.setdefault(gkey, {
                "signal": finding["signal"], "tier": tier, "label": label,
                "key": finding["key"], "count": 0, "environments": set(), "samples": [],
            })
            group["count"] += 1
            group["environments"].add(meta.get("environment") or "?")
            if meta.get("session_id"):
                sessions[gkey].add(meta["session_id"])
            if len(group["samples"]) < _SAMPLE_LIMIT:
                group["samples"].append({
                    "trace_id": record.get("trace_id"),
                    "ts": record.get("ts"),
                    "turn_kind": meta.get("turn_kind"),
                    "model": model,
                    "user_input": _clip(query),
                    "detail": _clip(finding["detail"]) if finding["detail"] is not None else None,
                })
    result = []
    for gkey, group in groups.items():
        group["sessions"] = len(sessions[gkey])
        group["environments"] = sorted(group["environments"])
        result.append(group)
    result.sort(key=lambda g: (TIERS.index(g["tier"]), -g["count"], g["signal"], g["key"]))
    return result


# ── 출력 ─────────────────────────────────────────────────────────────────────


def load(trace_dir: Optional[Path] = None, days: Optional[int] = None) -> Dict[str, Any]:
    """보관 중인 Trace를 묶어 {range, total, groups}로 돌려준다(콘솔·CLI 공용)."""
    files = trace_files(trace_dir or default_trace_dir(), days)
    total = 0

    def counted() -> Iterator[Dict[str, Any]]:
        nonlocal total
        for record in iter_records(files):
            total += 1
            yield record

    groups = triage(counted())
    return {
        "range": [files[0].stem, files[-1].stem] if files else None,
        "total": total,
        "groups": groups,
    }
