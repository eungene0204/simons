"""'직접 입력' 자유 답변 QA — 되묻기 질문별로 사용자가 칠 법한 표현을 실제 파스 레인에 넣고
어느 필드에 어떤 값으로 귀속되는지 확인한다.

호출은 백엔드 /strategy/parse(= parse-stream과 같은 _run_nl_parse 레인)를 직접 친다.
프론트 턴 중재(되묻기 레인 차단)는 유닛 테스트가 덮으므로, 여기서는 변수가 큰
LLM 귀속·값 환산만 본다.
"""
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

BASE_URL = os.environ.get("QA_BACKEND_URL", "http://localhost:8000") + "/strategy/parse"
# 진행 골격 8칸이 모두 채워진 기준 전략. 파일이 없으면 한 번 파싱해 만들어 캐시한다.
_BASE_PATH = Path(__file__).with_name(".qa_free_input_base.json")
_BASE_PROMPT = (
    "코스피200에서 20일 고점을 돌파하면 매수하고 데드크로스에서 매도, "
    "손절 -6%, 익절 30%, 최대 3종목, 매월 리밸런싱, 최근 5년"
)

# 되묻기 질문 — 정본은 프론트 코드다.
#  fill  = backtestReadiness.ts SLOT_PROMPTS (진행 골격을 채우는 질문)
#  modify= conversationDecision.ts MODIFICATION_CLARIFICATIONS / takeProfitPrompt
QUESTIONS = {
    "entry": {
        "fill": "매수 조건이 빠져 있습니다. 어떤 조건에서 매수할까요?",
        "modify": "어떤 진입 신호로 변경할까요? 아래 옵션을 선택하거나 원하는 조건을 직접 입력해 주세요.",
    },
    "exit": {
        "fill": "청산 조건이 빠져 있습니다. 어떤 조건에서 청산할까요?",
        "modify": "어떤 청산 신호로 변경할까요? 아래 옵션을 선택하거나 원하는 조건을 직접 입력해 주세요.",
    },
    "max_positions": {
        "fill": "포트폴리오에 최대 몇 종목을 담을까요?",
        "modify": "최대 보유 종목 수를 몇 종목으로 변경할까요? 아래에서 선택하거나 원하는 수를 직접 입력해 주세요.",
    },
    "rebalancing": {
        "fill": "리밸런싱 주기가 빠져 있습니다. 포트폴리오를 얼마나 자주 다시 구성할까요?",
        "modify": "리밸런싱 주기를 어떻게 변경할까요? 아래에서 선택하거나 원하는 주기를 직접 입력해 주세요.",
    },
    "stop_loss": {
        "fill": "손절 기준이 빠져 있습니다. 손절 기준을 몇 %로 설정할까요?",
        "modify": "손절 기준을 몇 %로 변경할까요? 아래에서 선택하거나 원하는 값을 직접 입력해 주세요.",
    },
    "take_profit": {
        "fill": "익절 기준이 빠져 있습니다. 익절 기준을 몇 %로 설정할까요?",
        "modify": "익절 기준은 매수가 대비 수익률로 설정합니다. 예시 값은 5%, 10%, 15%입니다. 적용할 익절 기준을 몇 %로 할까요?",
    },
    "backtest_period": {
        "fill": "어느 기간의 과거 데이터로 백테스트할까요?",
        "modify": "백테스트 기간을 어떻게 변경할까요? 아래에서 선택하거나 원하는 기간을 직접 입력해 주세요.",
    },
    "initial_capital": {
        "fill": "초기 투자 자금을 얼마로 설정할까요?",
        "modify": "초기자금을 얼마로 변경할까요? 아래에서 선택하거나 원하는 금액을 직접 입력해 주세요.",
    },
}


def sig_entry(indicator, **kw):
    def check(p):
        for s in p.get("entry_signals") or []:
            if s.get("indicator") != indicator:
                continue
            if all(s.get(k) == v for k, v in kw.items()):
                return True, ""
            return False, f"파라미터 불일치: {json.dumps(s, ensure_ascii=False)}"
        return False, f"entry_signals={json.dumps(p.get('entry_signals'), ensure_ascii=False)}"
    return check


def sig_exit(indicator, **kw):
    def check(p):
        for s in p.get("exit_signals") or []:
            if s.get("indicator") != indicator:
                continue
            if all(s.get(k) == v for k, v in kw.items()):
                return True, ""
            return False, f"파라미터 불일치: {json.dumps(s, ensure_ascii=False)}"
        return False, f"exit_signals={json.dumps(p.get('exit_signals'), ensure_ascii=False)}"
    return check


def filt(metric, operator, value):
    def check(p):
        for f in p.get("fundamental_filters") or []:
            if f.get("metric") == metric:
                if f.get("operator") == operator and abs((f.get("value") or 0) - value) < 1e-6:
                    return True, ""
                return False, f"조건 불일치: {json.dumps(f, ensure_ascii=False)}"
        return False, f"fundamental_filters={json.dumps(p.get('fundamental_filters'), ensure_ascii=False)}"
    return check


def field(name, expected):
    def check(p):
        got = p.get(name)
        if isinstance(expected, (int, float)) and isinstance(got, (int, float)):
            ok = abs(got - expected) < 1e-6
        else:
            ok = got == expected
        return ok, f"{name}={got!r} (기대 {expected!r})"
    return check


def years_window(n):
    """버킷 밖 연수는 오늘 기준 명시 날짜 창으로 변환된다(nl_parser와 같은 정본 정책)."""
    from datetime import date
    def check(p):
        start, end = p.get("backtest_start_date"), p.get("backtest_end_date")
        ok = bool(start) and bool(end) and start.startswith(str(date.today().year - n))
        return ok, f"{start}~{end} (기대 오늘-{n}년 ~ 오늘)"
    return check


def dates(start, end):
    def check(p):
        ok = p.get("backtest_start_date") == start and p.get("backtest_end_date") == end
        return ok, f"{p.get('backtest_start_date')}~{p.get('backtest_end_date')} (기대 {start}~{end})"
    return check


# (슬롯, 사용자가 칠 법한 자유 입력, 기대 판정)
CASES = [
    # ── 매수 조건 ──────────────────────────────────────────────────────────
    ("entry", "RSI 30 이하에서 매수", sig_entry("rsi", operator="<=", value=30)),
    ("entry", "5일선이 20일선을 위로 뚫으면 매수", sig_entry("ma_crossover", short_period=5, long_period=20)),
    ("entry", "거래량이 평소보다 3배 터지면 사자", sig_entry("volume_spike")),
    ("entry", "per 10 이하인 저평가 종목", filt("per", "<=", 10)),
    ("entry", "MACD 골든크로스", sig_entry("macd")),
    ("entry", "60일 신고가 뚫을때", sig_entry("breakout", lookback_period=60)),
    # ── 매도 조건 ──────────────────────────────────────────────────────────
    ("exit", "데드크로스 나오면 팔아", sig_exit("ma_crossover")),
    ("exit", "RSI 70 이상이면 매도", sig_exit("rsi", operator=">=", value=70)),
    ("exit", "20일 보유 후 청산", field("hold_period_days", 20)),
    ("exit", "볼린저밴드 상단 닿으면 매도", sig_exit("bollinger_bands")),
    ("exit", "한 달 지나면 정리", field("hold_period_days", 21)),
    # ── 최대 보유 ──────────────────────────────────────────────────────────
    ("max_positions", "5종목", field("max_positions", 5)),
    ("max_positions", "최대 10개", field("max_positions", 10)),
    ("max_positions", "20개 종목에 나눠서 담을래", field("max_positions", 20)),
    ("max_positions", "여덟 종목", field("max_positions", 8)),
    ("max_positions", "7게", field("max_positions", 7)),          # 오타 '개→게'
    # ── 리밸런싱 ───────────────────────────────────────────────────────────
    ("rebalancing", "매월", field("rebalancing_period", "monthly")),
    ("rebalancing", "분기마다", field("rebalancing_period", "quarterly")),
    ("rebalancing", "3개월에 한 번", field("rebalancing_period", "quarterly")),
    ("rebalancing", "일주일마다 다시 짜줘", field("rebalancing_period", "weekly")),
    ("rebalancing", "리밸런싱 안 함", field("rebalancing_period", "none")),
    ("rebalancing", "1년에 한번", field("rebalancing_period", "yearly")),
    # ── 리스크 관리(손절) ──────────────────────────────────────────────────
    ("stop_loss", "-7%", field("stop_loss_pct", 7)),
    ("stop_loss", "10% 빠지면 손절", field("stop_loss_pct", 10)),
    ("stop_loss", "5퍼센트", field("stop_loss_pct", 5)),
    ("stop_loss", "8프로", field("stop_loss_pct", 8)),
    ("stop_loss", "12", field("stop_loss_pct", 12)),
    # ── 리스크 관리(익절) ──────────────────────────────────────────────────
    ("take_profit", "20%", field("take_profit_pct", 20)),
    ("take_profit", "25퍼", field("take_profit_pct", 25)),
    ("take_profit", "15% 수익나면 팔아줘", field("take_profit_pct", 15)),
    ("take_profit", "두 배", field("take_profit_pct", 100)),
    ("take_profit", "40", field("take_profit_pct", 40)),
    # ── 백테스트 기간 ──────────────────────────────────────────────────────
    ("backtest_period", "3년", field("backtest_period", "3y")),
    ("backtest_period", "최근 1년", field("backtest_period", "1y")),
    ("backtest_period", "전체 기간", field("backtest_period", "full")),
    ("backtest_period", "2020년 1월부터 2024년 12월까지", dates("2020-01-01", "2024-12-31")),
    ("backtest_period", "10년", years_window(10)),
    # ── 초기 자본 ──────────────────────────────────────────────────────────
    ("initial_capital", "3억원", field("initial_capital", 300_000_000)),
    ("initial_capital", "1000만원", field("initial_capital", 10_000_000)),
    ("initial_capital", "5천만원", field("initial_capital", 50_000_000)),
    ("initial_capital", "1억", field("initial_capital", 100_000_000)),
    ("initial_capital", "2억5000만원", field("initial_capital", 250_000_000)),
    ("initial_capital", "30000000", field("initial_capital", 30_000_000)),
]

# 답변이 건드리면 안 되는 필드(다른 슬롯 침범 감시). 해당 슬롯 자신은 제외한다.
GUARDED = {
    "universe": "유니버스",
    "max_positions": "최대 보유",
    "rebalancing_period": "리밸런싱",
    "stop_loss_pct": "손절",
    "take_profit_pct": "익절",
    "backtest_period": "백테스트 기간",
    "initial_capital": "초기 자본",
    "hold_period_days": "보유 기간",
}
OWNED = {
    "entry": set(),
    "exit": {"hold_period_days"},
    "max_positions": {"max_positions"},
    "rebalancing": {"rebalancing_period"},
    "stop_loss": {"stop_loss_pct"},
    "take_profit": {"take_profit_pct"},
    "backtest_period": {"backtest_period"},
    "initial_capital": {"initial_capital"},
}


def _post(payload: dict) -> dict:
    req = urllib.request.Request(
        BASE_URL, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read())


def load_base() -> dict:
    if _BASE_PATH.exists():
        return json.loads(_BASE_PATH.read_text(encoding="utf-8"))
    print("기준 전략 생성 중(1회)...", flush=True)
    base = _post({"prompt": _BASE_PROMPT, "backend": "ollama"})
    _BASE_PATH.write_text(json.dumps(base, ensure_ascii=False), encoding="utf-8")
    return base


def call(prompt, question):
    body = {
        "prompt": prompt, "backend": "ollama",
        "previous_parsed": PREV, "previous_explicit_fields": PREV_EXPLICIT,
        "pending_question": question,
    }
    return _post(body)


def run(family):
    rows = []
    for slot, prompt, check in CASES:
        question = QUESTIONS[slot][family]
        started = time.perf_counter()
        try:
            out = call(prompt, question)
        except Exception as exc:  # noqa: BLE001
            rows.append((slot, prompt, "ERROR", str(exc)[:90], 0))
            print(f"  ERROR {slot} {prompt!r} {exc}", flush=True)
            continue
        took = time.perf_counter() - started
        parsed = out["parsed"]
        ok, detail = check(parsed)
        # 다른 슬롯을 건드렸는지
        collateral = []
        for key, label in GUARDED.items():
            if key in OWNED[slot]:
                continue
            if parsed.get(key) != PREV.get(key):
                collateral.append(f"{label}:{PREV.get(key)!r}→{parsed.get(key)!r}")
        clar = out.get("clarification_question")
        notices = out.get("notices") or []
        # 되묻기는 실패가 아니다 — 값이 빠진 파라미터를 묻는 것은 정상 동작이다
        # (CLAUDE.md: 말하지 않은 값을 기본값으로 확정 금지). 별도 판정으로 센다.
        if ok and not collateral:
            verdict = "PASS"
        elif not ok and clar:
            verdict = "ASK"
        elif not ok:
            verdict = "FAIL"
        else:
            verdict = "COLLATERAL"
        rows.append((slot, prompt, verdict, detail, took, collateral, clar, notices))
        mark = {"PASS": "✅", "FAIL": "❌", "ASK": "❓", "COLLATERAL": "⚠️"}[verdict]
        print(f"  {mark} [{slot}] {prompt!r} → {detail}"
              + (f" | 침범: {', '.join(collateral)}" if collateral else "")
              + (f" | 되묻기: {clar[:40]}" if clar else "")
              + f" ({took:.1f}s)", flush=True)
    return rows


if __name__ == "__main__":
    family = sys.argv[1] if len(sys.argv) > 1 else "modify"
    BASE = load_base()
    PREV = BASE["parsed"]
    PREV_EXPLICIT = BASE.get("explicit_fields") or []
    print(f"=== 질문 계열: {family} / 케이스 {len(CASES)}개 ===", flush=True)
    rows = run(family)
    out_path = str(Path(__file__).with_name(f".qa_free_input_result_{family}.json"))
    json.dump(rows, open(out_path, "w"), ensure_ascii=False, default=str)
    counts = {}
    for r in rows:
        counts[r[2]] = counts.get(r[2], 0) + 1
    print(f"\n요약({family}): " + " ".join(f"{k}={v}" for k, v in sorted(counts.items())), flush=True)
