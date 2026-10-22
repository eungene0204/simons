"""Replace primary's lexical role/EMA/holding decisions with quoted LLM fields."""
import json
import math
import re

from .decisions import record
from .holding_period_check import _COUNT_ALIASES
from .output_repair import extract_json_object
from .models import _SINO_DIGITS
from .quote_check import MA_FACTORS

_SYSTEM = """대조 대상은 메인 해석기가 이미 추출한 조건과 미지원 신고입니다.
원문과 각 인용을 대조하여 오배치 또는 옮겨 적기 오류가 확실한 항목만 correction으로 출력하세요.
정상 항목은 unchanged, 불명확하면 unclear입니다. 사용자의 새 조건을 만들어 내지 마세요.
condition: requested_role은 실제 요청된 entry/exit 역할, factor는 이동평균 조건의
technical.ema/technical.ma_crossover 선택만 수정할 수 있습니다. 매수하는 하향교차를
매도 조건으로 추론하지 마세요. parameters에는 명시된 short_period/long_period 또는
lookback_period만 넣으세요. 선 하나와 종가를 비교할 때 short_period는 null입니다.
기간 항목은 {number_text:원문 수량 표기,count:수량,unit:day/week/month/year}입니다.
미지원 신고가 최대 보유 기간이라면 kind=max_hold, 최소라면 min_hold, 그 외 unchanged입니다.
holding: number_text/count/unit(day/month/year)을 출력하며 단위 환산은 하지 마세요.
미지원 신고가 손절 또는 익절 설정이면 kind=stop_loss/take_profit, number_text/count/unit=percent로
그 명시 비율을 옮기세요. 지표 청산 신호를 고정 손실률로 바꾸지 마세요.
quote는 주어진 source_text 전체를 정확히 복사합니다. id를 빠짐없이 정확히 복사합니다.
JSON만: {"items":[{"id":"c:0","quote":"인용","status":"unchanged"},
{"id":"c:1","quote":"인용","status":"corrected","requested_role":"exit","factor":"technical.ma_crossover",
"parameters":{"short_period":null,"long_period":{"number_text":"60","count":60,"unit":"day"}}},
{"id":"f:0","quote":"인용","status":"corrected","kind":"max_hold",
"number_text":"한","count":1,"unit":"month"}]}"""


def _quantity(value, quote, *, holding=False):
    if not isinstance(value, dict):
        return None
    text, count, unit = value.get("number_text"), value.get("count"), value.get("unit")
    multipliers = {"day": 1, "week": 5, "month": 21, "year": 252}
    if (not isinstance(text, str) or not text or text not in quote or isinstance(count, bool)
            or not isinstance(count, (int, float)) or not math.isfinite(count)
            or count <= 0 or not float(count).is_integer() or unit not in multipliers
            or holding and unit == "week"):
        return None
    # Normalize only the extracted numeric field; never classify the utterance.
    # number_text는 LLM이 옮겨 적은 칸이라 단위가 붙어 올 수 있다("60일") — 앞쪽 숫자 표기만 읽는다.
    aliases = {**_SINO_DIGITS, **_COUNT_ALIASES}
    digits = re.match(r"[\d,]+(?:\.\d+)?", text)
    written = (aliases[text] if text in aliases
               else float(digits.group().replace(",", "")) if digits else None)
    if written is None or written != count:
        return None
    return 252 if unit == "week" and count == 52 else int(count) * multipliers[unit]


def reconcile_semantic_fields(intent, utterance, chat, *, only=None):
    strategy = intent.strategy
    if strategy is None or not callable(chat):
        return
    from .required_checks import policy
    checks = policy()

    def recoverable_failures(condition):
        failures = [i for i in checks.items if i["subject"] is condition and i["status"] != "ACCEPT"] if checks else []
        return failures and all(
            i["kind"] == "quote"
            and getattr(i["evidence"], "describes", None) == "moving_average"
            and i["status"] == "UNRESOLVED"
            for i in failures
        )

    def eligible(condition):
        failures = [i for i in checks.items if i["subject"] is condition and i["status"] != "ACCEPT"] if checks else []
        return (not failures or recoverable_failures(condition)
                or condition.factor == "technical.breakout" and all(
                    i["kind"] == "quote" and getattr(i["evidence"], "describes", None) == "new_high_breakout"
                    for i in failures))

    targets = [(c, role) for role in ("entry", "exit") for c in getattr(strategy, role + "_conditions")
        if (c.factor in MA_FACTORS or c.factor == "technical.breakout") and c.source_text
        and c.source_text in utterance and eligible(c) and (only is None or any(c is item for item in only))]
    features = [(i, f) for i, f in enumerate(intent.unsupported_features)
                if isinstance(f, str) and f and f in utterance] if only is None else []
    subjects = {f"c:{i}": (c, role, c.source_text) for i, (c, role) in enumerate(targets)}
    subjects.update({f"f:{i}": (None, i, f) for i, f in features})
    if not subjects:
        return
    request = {"utterance": utterance, "items": [{"id": key, "source_text": quote,
        **({"role": role, "condition": c.model_dump(mode="json")} if c is not None else
           {"unsupported_feature": quote})} for key, (c, role, quote) in subjects.items()]}
    try:
        from observability import span
        with span("Semantic field reconciliation", "chain", inputs=request) as trace:
            raw = chat(_SYSTEM, json.dumps(request, ensure_ascii=False), max_tokens=128 + 128 * len(subjects))
            payload = json.loads(extract_json_object(raw))
            items = payload.get("items") if isinstance(payload, dict) else None
            if not isinstance(items, list) or len(items) != len(subjects):
                return
            by_id = {item.get("id"): item for item in items if isinstance(item, dict)}
            if set(by_id) != set(subjects) or len(by_id) != len(items):
                return
            trace.local_evidence(verdicts=items)
        removed_features = set()
        for key, (condition, role, quote) in subjects.items():
            item = by_id[key]
            if item.get("quote") != quote or item.get("status") != "corrected":
                unchanged = item.get("quote") == quote and item.get("status") == "unchanged"
                record("semantic_reconciliation", condition or quote, "ACCEPT" if unchanged else "UNRESOLVED",
                       "NO_CORRECTION_NEEDED" if unchanged else "NO_CONFIRMED_CORRECTION", value=item)
                continue
            if condition is None:
                kind = item.get("kind")
                if kind in ("stop_loss", "take_profit"):
                    text, count = item.get("number_text"), item.get("count")
                    if (item.get("unit") != "percent" or not isinstance(text, str) or not text
                            or text not in quote or isinstance(count, bool)
                            or not isinstance(count, (int, float)) or not math.isfinite(count)):
                        continue
                    try:
                        ratio = abs(float(text.replace(",", "")))
                    except ValueError:
                        continue
                    if not math.isfinite(ratio) or ratio <= 0 or abs(count) != ratio:
                        continue
                    existing = getattr(strategy.risk_management, kind)
                    if existing is None or existing == ratio:
                        setattr(strategy.risk_management, kind, ratio)
                        removed_features.add(role)
                        record("semantic_reconciliation", quote, "ACCEPT", "QUOTED_RISK_FIELD", value=item)
                    continue
                days = _quantity(item, quote, holding=True)
                if kind not in ("max_hold", "min_hold") or days is None:
                    continue
                field = "hold_period_days" if kind == "max_hold" else "min_hold_period_days"
                if getattr(strategy.portfolio, field) is None:
                    setattr(strategy.portfolio, field, days)
                    removed_features.add(role)
                    record("semantic_reconciliation", quote, "ACCEPT", "QUOTED_HOLDING_FIELD", value=item)
                continue
            requested_role = item.get("requested_role", role)
            factor = item.get("factor", condition.factor)
            if condition.factor == "technical.ema" and factor == "technical.ma_crossover":
                # 메인 인터프리터가 EMA로 낸 조건을 보정 LLM이 ma_crossover로 되돌리는 방향은 막는다 —
                # 같은 문장·같은 1차 출력에서 8턴 중 6턴이 EMA 매도를 SMA로 뒤집었다(2026-10-23).
                # 역할·기간 교정은 그대로 받는다. 반대 방향(ma_crossover→ema)은 기존 계약대로 둔다.
                factor = condition.factor
            if requested_role not in ("entry", "exit") or factor not in (
                    condition.factor, "technical.ema", "technical.ma_crossover"):
                continue
            if factor != condition.factor and condition.factor not in MA_FACTORS:
                continue
            parameters = item.get("parameters", {})
            allowed = {"lookback_period"} if factor == "technical.breakout" else {"short_period", "long_period"}
            if not isinstance(parameters, dict) or not set(parameters) <= allowed:
                continue
            normalized = {name: None if value is None else _quantity(value, quote)
                          for name, value in parameters.items()}
            if any(value is not None and normalized[name] is None for name, value in parameters.items()):
                continue
            if factor == "technical.ma_crossover" and normalized.get("short_period", 0) is None:
                # 단순이동평균의 '종가 vs 선 하나'는 컴파일러 정본 표기가 short_period=1이라, 보정이
                # null로 덮으면 기간 누락 되묻기가 난다(2026-10-21). 값을 새로 정하지 않고 기존 칸을 둔다.
                del normalized["short_period"]
            from .required_checks import policy
            checks = policy()
            failures = [i for i in checks.items if i["subject"] is condition and i["status"] != "ACCEPT"] if checks else []
            verified_ma_recovery = failures and condition.factor in MA_FACTORS and recoverable_failures(condition)
            breakout_recovery = condition.factor == "technical.breakout" and failures and all(
                i["kind"] == "quote" and getattr(i["evidence"], "describes", None) == "new_high_breakout"
                for i in failures)
            if failures and not (verified_ma_recovery or breakout_recovery):
                continue
            before = condition.model_dump()
            changed = factor != condition.factor or role != requested_role or any(
                condition.parameters.get(name) != value for name, value in normalized.items())
            if not changed:
                continue
            from strategy_conversation.registry.concept_ontology import concept_spec
            concept = concept_spec(condition.factor)
            expansion = concept.expansion if concept is not None else None
            if factor != condition.factor and expansion:
                condition.operator = expansion.get("operator") or condition.operator
                for name, value in (expansion.get("default_parameters") or {}).items():
                    if condition.parameters.get(name) is None and name not in normalized:
                        condition.parameters[name] = float(value)
            condition.factor = factor
            condition.parameters.update(normalized)
            if role != requested_role:
                getattr(strategy, role + "_conditions").remove(condition)
                getattr(strategy, requested_role + "_conditions").append(condition)
            if checks:
                checks.recover(condition, {"original": before, "confirmed_fields": item})
            record("semantic_reconciliation", condition, "ACCEPT", "QUOTED_CONDITION_FIELDS", value=item)
        intent.unsupported_features = [f for i, f in enumerate(intent.unsupported_features) if i not in removed_features]
    except Exception:
        # The main LLM output remains the authority; no lexical repair fallback.
        return
