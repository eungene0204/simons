# -*- coding: utf-8 -*-
"""Strategy Builder QA & Conversation Fuzzing Harness (in-process, deterministic).

대상: backend/intent/classifier.py, backend/intent/strategy_builder.py,
      engine/nl_parser(rule-based), ai/strategy_validation_agent, DSL 파이프라인.

LLM 없이 결정적으로 도달 가능한 모든 경로를 퍼징한다. LLM 폴백 경로는 별도
라이브 API 스크립트가 샘플링한다.

실행:
    python scripts/qa_builder_fuzz.py
결과: scripts/qa_builder_fuzz_results.json + 콘솔 요약.
리포트: docs/builder_fuzz_qa_report.md (2026-07-24 첫 실행 — 고유 결함 19건 BF-01~19).
알려진 결함(BF-*)은 수정 전까지 실패로 계속 잡힌다 — 수정 후 재실행해 회귀 게이트로 쓴다.
"""
from __future__ import annotations

import json
import os
import random
import re
import sys
import traceback
from collections import Counter, defaultdict

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("POLARS_MAX_THREADS", "1")

from pathlib import Path

BACKEND = str(Path(__file__).resolve().parent.parent / "backend")
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

from intent import strategy_builder as sb  # noqa: E402
from intent.classifier import classify, is_definition_question  # noqa: E402
from intent.schemas import QueryIntent  # noqa: E402

FAILURES: list[dict] = []
STATS: Counter = Counter()


def record(suite: str, case_id: str, user_input, expected: str, actual: str,
           category: str, severity: str, note: str = ""):
    FAILURES.append({
        "suite": suite, "id": case_id,
        "input": user_input if isinstance(user_input, str) else json.dumps(user_input, ensure_ascii=False),
        "expected": expected, "actual": actual,
        "category": category, "severity": severity, "note": note,
    })


def guard(suite: str, case_id: str, user_input, fn):
    """예외를 CRASH 실패로 기록하는 래퍼."""
    try:
        return fn()
    except Exception:
        record(suite, case_id, user_input, "no exception", "CRASH:\n" + traceback.format_exc()[-800:],
               "Backend Logic", "Critical")
        return None


# 규제 금지 표현(긍정 추천/보장/전망). 부정("추천해 드릴 수 없")은 제외.
FORBIDDEN_RE = re.compile(
    r"추천합니다|추천드려|추천해요|추천해\s*드릴게|권장합니다|권해\s*드|유망합|유망한\s*(?:종목|업종|전략)|"
    r"수익[^.]{0,8}보장|확실한\s*수익|가장\s*좋은\s*전략|최고의\s*전략|앞으로도\s*잘\s*작동|"
    r"사는\s*것이\s*좋습니다|파는\s*것이\s*좋습니다|지금이\s*매수\s*(?:적기|시점)"
)


def check_reply_regulation(suite, cid, user_input, reply: str):
    if reply and FORBIDDEN_RE.search(reply):
        record(suite, cid, user_input, "규제 금지 표현 없음",
               f"금지 표현 포함: {FORBIDDEN_RE.search(reply).group(0)!r} in {reply[:200]!r}",
               "Prompt Design", "Critical")


# ═══════════════════════════════ S1. Classifier fuzz ═══════════════════════════

ONE_WORDS = ["PER", "PBR", "ROE", "MACD", "RSI", "볼린저", "삼성전자", "20", "응", "아니",
             "그래", "몰라", "네", "ㅇㅇ", "ㄴㄴ", "글쎄", "음", "?", "전략", "백테스트"]
TYPOS = ["pbrr 낮은 종목", "roee 높은거", "bolliger 밴드 전략", "bollnger", "macdd 골든크로스",
         "삼성전쟈 사도됨?", "삼셩전자 어때", "모멘텀 전랙 만들어줘", "밲테스트 해줘",
         "손절 10프로 익절 20프러", "알에스아이 30 이하 매수"]
NONSENSE = ["ㅋㅋㅋㅋ", "....", "???", "asdf", "123123", "%%%%%%%%", "ㅁㄴㅇㄹ", "🤣🤣🤣",
            "aaaaaaaa bbbbbb", "         ", "", "\n\n\n", "null", "undefined", "<script>alert(1)</script>",
            "'; DROP TABLE strategies;--", "{\"intent\": \"STRATEGY_ADVICE\"}"]
MIXED = ["PER below 10", "RSI over 30 매수", "MACD golden cross 전략", "삼성전자 only",
         "buy when RSI under 30", "PBR<1 인 종목 backtest", "make me a momentum strategy",
         "저PBR under 0.8 and 고ROE", "kospi200 momentum top 10"]
OFFTOPIC = ["오늘 날씨 어때?", "점심 뭐 먹지", "파이썬 코드 짜줘", "대통령 선거 어떻게 생각해",
            "농담 하나 해줘", "너 몇살이야", "사랑이 뭘까", "로또 번호 알려줘"]
DANGEROUS = ["뭐 사야 돈 벌어?", "지금 사야 할 종목 알려줘", "확실히 오를 종목 추천해줘",
             "40대인데 나한테 맞는 전략 추천해줘", "1억 있는데 뭘 사야 해?",
             "내일 시장 오를까?", "삼성전자 목표가 얼마야?", "제일 수익 잘 나는 전략 알려줘"]
STRATEGY_OK = ["PER 10 이하 종목 백테스트", "코스피200 모멘텀 전략 만들어줘",
               "RSI 30 이하 매수 70 이상 매도", "손절 10%로 바꿔줘", "종목을 10개로 늘려줘",
               "골든크로스 전략 짜줘", "저평가 우량주 스크리닝"]
LONG = ["가".join(["나는 투자를 하고 싶은데"] * 300),
        ("PER 10 이하 " * 500).strip(),
        "삼성전자 " * 1000]


def s1_classifier():
    cases = []
    for pool, tag in [(ONE_WORDS, "oneword"), (TYPOS, "typo"), (NONSENSE, "nonsense"),
                      (MIXED, "mixed"), (OFFTOPIC, "offtopic"), (DANGEROUS, "dangerous"),
                      (STRATEGY_OK, "strategy"), (LONG, "long")]:
        for i, q in enumerate(pool):
            cases.append((f"{tag}-{i}", q, tag))

    for cid, q, tag in cases:
        STATS["S1_total"] += 1
        res = guard("S1-classify", cid, q, lambda: classify(q, llm=None))
        if res is None:
            continue
        check_reply_regulation("S1-classify", cid, q, res.suggested_reply or "")
        # 오라클
        if tag == "offtopic" and res.intent in (QueryIntent.STRATEGY_ADVICE, QueryIntent.STOCK_ANALYSIS):
            record("S1-classify", cid, q, "OFF_TOPIC/GREETING/UNKNOWN",
                   f"{res.intent} (reason={res.reason})", "Intent Recognition", "Medium")
        if tag == "strategy" and res.intent not in (QueryIntent.STRATEGY_ADVICE,):
            record("S1-classify", cid, q, "STRATEGY_ADVICE",
                   f"{res.intent} (reason={res.reason})", "Intent Recognition", "High")
        if tag == "dangerous":
            # 열린 추천/맞춤 조언은 절대 일반 LLM 답변·전략 파싱으로 흘러가면 안 된다.
            if res.intent in (QueryIntent.GENERAL_INVESTMENT,) and not res.suggested_reply:
                record("S1-classify", cid, q, "STOCK_PICK/STRATEGY_PICK + 안내",
                       f"{res.intent} (reason={res.reason})", "Intent Recognition", "High")
        if tag == "nonsense" and res.intent in (QueryIntent.STRATEGY_ADVICE, QueryIntent.STOCK_ANALYSIS):
            record("S1-classify", cid, q, "OFF_TOPIC/UNKNOWN",
                   f"{res.intent} (reason={res.reason})", "Intent Recognition", "Medium")
        STATS[f"S1_intent_{res.intent.value if hasattr(res.intent,'value') else res.intent}"] += 1

    # 메타모픽: 동일 의미 변형은 동일 intent여야 한다(결정적 레이어에서 UNKNOWN이면 비교 제외)
    groups = [
        ["PER 10 이하 종목", "PER가 10보다 낮은 종목", "PER 10 밑인 종목", "per<=10 종목", "PER 열 이하 종목"],
        ["삼성전자 지금 사도 돼?", "삼성전자 매수해도 될까", "삼성전자 들어가도 괜찮아?"],
        ["모멘텀 전략 만들어줘", "모멘텀전략만들어줘", "모멘텀 전략 하나 짜줘"],
    ]
    for gi, group in enumerate(groups):
        results = {}
        for q in group:
            r = guard("S1-metamorphic", f"g{gi}", q, lambda: classify(q, llm=None))
            if r is not None:
                results[q] = r.intent
        vals = set(results.values())
        vals.discard(QueryIntent.UNKNOWN)
        if len(vals) > 1:
            record("S1-metamorphic", f"g{gi}", json.dumps(results, ensure_ascii=False, default=str),
                   "동일 의미 → 동일 intent", f"불일치: { {k: str(v) for k, v in results.items()} }",
                   "Intent Recognition", "Medium")


# ═══════════════════════════════ S2. Builder random-walk fuzz ═══════════════════

COOP_ANSWERS = {
    "universe": ["코스피", "코스닥", "코스피200", "코스피·코스닥 전체", "ETF", "코스피요",
                 "코스닥으로 해줘", "kospi", "대형주로"],
    "strategy_type": ["모멘텀", "골든크로스", "MACD", "돌파", "거래량 급증", "과매도 반등",
                      "저평가 가치주", "RSI 전략", "볼린저", "스토캐스틱", "CCI"],
    "lookback_days": ["3개월", "6개월", "1개월", "60일", "20일", "3", "6"],
    "rsi_period": ["14일 (기본)", "14", "9일", "기본"],
    "rsi_bounds": ["30 / 70 (기본)", "30 70", "25 / 75", "기본"],
    "ma_kind": ["단순(SMA)", "지수(EMA)", "단순", "지수"],
    "ma_periods": ["5일 / 20일 (기본)", "5 20", "10일 / 60일", "기본"],
    "macd_mode": ["시그널선 교차 (기본)", "제로선 돌파", "교차"],
    "cci_params": ["±100 (기본)", "100", "14 150", "기본"],
    "volume_period": ["20일 (기본)", "20", "60일", "기본"],
    "value_params": ["PBR 1 이하 · ROE 10 이상 (기본)", "PBR 0.8 ROE 15", "기본"],
    "filters": ["없음", "EMA200 위에서만", "거래대금 100억 이상", "EMA200 위 + 거래대금 100억"],
    "entry_rule": ["RSI가 30 이하로 떨어지면 매수", "20일선이 60일선을 상향 돌파하면 매수"],
    "holding_count": ["10개", "5개", "20종목", "10"],
    "rebalance_cycle": ["매월", "매주", "분기마다", "안 함", "리밸런싱 안 할래"],
    "risk": ["10% 손절", "10% 손절·20% 익절", "최고가 대비 10% 하락 시 청산",
             "20일 보유 후 청산", "손절 8% 익절 25%"],
}

ADVERSARIAL = [
    "ㅋㅋㅋㅋ", "....", "asdf", "몰라 그런거", "?", "뭐라고?", "음...",
    "오늘 날씨 어때?", "농담 하나 해줘", "점심 뭐먹지", "야 너 누구야",
    "PER below 10", "whatever", "1번", "첫번째", "위에 거", "아까 그거",
    "삼성전자", "삼성전자로 해줘", "테슬라만 하고 싶은데",
    "빨리 좀 해", "아 짜증나네", "제대로 좀 해봐", "왜 자꾸 물어봐",
]
GLOSSARY_QS = ["손절이 뭐야?", "익절이 뭔가요", "리밸런싱이 뭐야", "모멘텀이 뭐야?",
               "골든크로스가 뭐야", "PBR이 뭐야", "PER이 뭐야?", "볼린저가 뭐야?",
               "스토캐스틱이 뭐야?", "CCI가 뭐야?", "돌파가 뭐야", "RSI가 뭐야"]
CONTRADICT = ["코스닥으로 바꿔줘", "아니다 모멘텀 말고 골든크로스로", "유니버스를 코스피로 변경",
              "3개월 말고 6개월", "전략을 볼린저로 바꿔줘"]
WEIRD_NUM = ["0개", "0개월", "0", "99999개", "손절 0%", "손절 200%", "RSI 0 0", "-5개",
             "500", "0.5개"]

QUESTION_CUES = {
    "universe": re.compile(r"어떤 시장"),
    "holding_count": re.compile(r"몇 개 종목|몇 종목"),
    "rebalance_cycle": re.compile(r"리밸런싱\)?할까요|얼마나 자주"),
}


def make_persona(rng: random.Random, kind: str):
    """kind에 따라 (expecting)->답변 을 생성하는 함수."""
    def answer(expecting, turn):
        pool = COOP_ANSWERS.get(expecting or "risk", ["몰라"])
        if kind == "normal":
            return rng.choice(pool), True
        if kind == "impatient":  # 성급: 가끔 재촉/복합 답
            if rng.random() < 0.3:
                return rng.choice(["빨리 좀", "그냥 아무거나 해줘", "알아서 해"]), False
            return rng.choice(pool), True
        if kind == "confused":  # 용어 질문 섞기
            if rng.random() < 0.35:
                return rng.choice(GLOSSARY_QS), False
            return rng.choice(pool), True
        if kind == "drifter":  # 딴소리 후 복귀
            if rng.random() < 0.35:
                return rng.choice(["오늘 날씨 어때?", "농담 해줘", "뉴스 좀 알려줘"]), False
            return rng.choice(pool), True
        if kind == "changer":  # 중간에 조건 변경 시도
            if rng.random() < 0.3:
                return rng.choice(CONTRADICT), False
            return rng.choice(pool), True
        if kind == "typo":
            ans = rng.choice(pool)
            if rng.random() < 0.5:
                squashed = ans.replace(" ", "")
                # 숫자 두 개가 붙어 한 수가 되면('5 20'→'520') 사람도 구분 불가한 모호
                # 입력이다 — 협조적 답변으로 기대하지 않는다(시스템은 힌트로 되물으면 됨).
                import re as _re
                ambiguous = bool(_re.search(r"\d\s+\d", ans))
                return squashed, not ambiguous
            return ans, True
        if kind == "hostile":
            if rng.random() < 0.4:
                return rng.choice(["아 짜증나", "왜이렇게 느려", "제대로 해라 좀"]), False
            return rng.choice(pool), True
        if kind == "weird_numbers":
            if rng.random() < 0.35:
                return rng.choice(WEIRD_NUM), False
            return rng.choice(pool), True
        if kind == "english":
            eng = {"universe": ["kospi", "KOSDAQ please"],
                   "strategy_type": ["momentum", "MACD", "breakout strategy"],
                   "risk": ["stop loss 10%", "take profit 20%"]}
            return rng.choice(eng.get(expecting, ["I don't know"])), expecting in eng
        return rng.choice(pool), True
    return answer


PERSONA_KINDS = ["normal", "impatient", "confused", "drifter", "changer", "typo",
                 "hostile", "weird_numbers", "english"]

SEEDS = ["", "뭐 사야 돼?", "코스피 모멘텀 전략", "반도체 주도주로 전략 만들어줘",
         "저평가 우량주 찾고 싶어", "손절 10% 익절 20%로 골든크로스", "원자로 관련주 전략",
         "ETF로 돌파 전략", "코스닥 거래량 급증"]


def run_conversation(user_id: int, kind: str, seed_text: str, max_turns: int = 40):
    rng = random.Random(user_id * 7919 + 13)
    answer_fn = make_persona(rng, kind)
    suite = "S2-builder"
    cid = f"u{user_id}-{kind}"

    state = sb.seed_state(seed_text) if seed_text else sb.BuilderState()
    # 첫 질문(빈 입력)
    res = guard(suite, cid + "-t0", "", lambda: sb.step(state, ""))
    if res is None:
        return
    state = res.state
    coop_fail_streak = 0
    escalated = False  # 미인식 연속 시 시스템이 이해 실패를 안내했는지(BF-15 수정 후 기대 동작)
    transcript = []

    def _core(s: sb.BuilderState) -> sb.BuilderState:
        return s.model_copy(update={"miss_streak": 0})

    for turn in range(1, max_turns + 1):
        if res.status == "confirmed":
            verify_confirmed(suite, cid, state, transcript)
            STATS["S2_confirmed"] += 1
            return
        if res.status == "exited":
            STATS["S2_exited"] += 1
            return
        expecting = sb.required_missing(state)
        text, is_coop = answer_fn(expecting, turn)
        transcript.append((expecting, text))
        prev_state = state
        res = guard(suite, f"{cid}-t{turn}", text,
                    lambda: sb.step(prev_state, text))
        if res is None:
            return
        check_reply_regulation(suite, f"{cid}-t{turn}", text, res.reply)
        state = res.state
        if sb.UNRECOGNIZED_HINT in (res.reply or ""):
            escalated = True
        if is_coop and res.status == "collecting":
            new_expecting = sb.required_missing(state)
            if new_expecting == expecting and _core(state) == _core(prev_state):
                coop_fail_streak += 1
                if coop_fail_streak >= 2:
                    record(suite, f"{cid}-t{turn}", text,
                           f"협조적 답변이 필드({expecting})를 채워야 함",
                           f"인식 실패 — 같은 질문 반복 (reply={res.reply[:80]!r})",
                           "Slot Filling", "Medium",
                           note=f"transcript={transcript[-3:]}")
                    return
            else:
                coop_fail_streak = 0
    # 페르소나가 끝까지 비협조(영어 등)여서 미완이어도, 시스템이 이해 실패를 안내했다면
    # 시스템 측 기대 동작(BF-15)은 충족 — 실패로 기록하지 않는다.
    if escalated:
        STATS["S2_escalated_incomplete"] += 1
        return
    record(suite, cid, seed_text, f"{max_turns}턴 내 완료/진행(또는 미인식 안내)",
           f"{max_turns}턴 초과 — 마지막 expecting={sb.required_missing(state)}",
           "State Machine", "Medium", note=f"transcript_tail={transcript[-5:]}")


def verify_confirmed(suite, cid, state: sb.BuilderState, transcript):
    """confirmed 시 DSL·요청 생성이 깨지지 않고 값이 유효한지."""
    def build():
        parsed = sb.build_parsed_strategy(state)
        if parsed is None:  # custom → prompt 재파싱 경로
            prompt = sb.synthesize_prompt(state)
            assert prompt.strip(), "empty synthesized prompt"
            return None
        from engine.nl_parser import enforce_strategy_minimums
        from engine.strategy_converter import to_backtest_request
        notices = enforce_strategy_minimums(parsed)
        req = to_backtest_request(parsed)
        return parsed, req, notices
    out = guard(suite, cid + "-dsl", str(transcript[-3:]), build)
    if out is None:
        return
    parsed, req, notices = out if isinstance(out, tuple) else (None, None, None)
    if parsed is None:
        return
    # 값 유효성
    d = parsed.model_dump()
    mp = d.get("max_positions")
    if not isinstance(mp, int) or mp < 1:
        record(suite, cid + "-dsl", str(transcript[-3:]), "max_positions>=1",
               f"max_positions={mp}", "DSL Generation", "High")
    if state.rsi_oversold is not None and state.rsi_overbought is not None:
        if state.rsi_oversold >= state.rsi_overbought:
            record(suite, cid + "-dsl", str(transcript[-3:]), "과매도<과매수",
                   f"oversold={state.rsi_oversold}, overbought={state.rsi_overbought}",
                   "Validation", "High")
    if state.ma_short is not None and state.ma_long is not None and state.ma_short >= state.ma_long:
        record(suite, cid + "-dsl", str(transcript[-3:]), "단기<장기 이동평균",
               f"short={state.ma_short}, long={state.ma_long}", "Validation", "High")
    if not (d.get("entry_signals") or d.get("fundamental_filters") or d.get("ranking_metric")):
        record(suite, cid + "-dsl", str(transcript[-3:]), "진입 조건 존재",
               f"entry 없음: {sorted(k for k, v in d.items() if v)}", "DSL Generation", "Critical")


def s2_builder_fuzz(n_users: int = 1200):
    uid = 0
    for i in range(n_users):
        kind = PERSONA_KINDS[i % len(PERSONA_KINDS)]
        seed = SEEDS[i % len(SEEDS)]
        run_conversation(uid, kind, seed)
        uid += 1
        STATS["S2_total"] += 1


# ═══════════════════════════════ S3. Directed slot/state probes ════════════════


def fresh(**kw):
    return sb.BuilderState(**kw)


def s3_directed():
    suite = "S3-directed"

    # (1) '됐어' 등 취소어 오인 — 확정/긍정 의미의 입력이 빌더를 통째로 날리는지
    for cid, text in [("cancel-1", "됐어, 손절 10%로 해줘"),
                      ("cancel-2", "이제 됐어 백테스트 돌려줘"),
                      ("cancel-3", "그만 물어보고 그냥 진행해"),
                      ("cancel-4", "취소하지 말고 계속해")]:
        st = fresh(universe="KOSPI", strategy_type="momentum", lookback_days=63,
                   lookback_label="3개월", holding_count=10, rebalance_cycle="monthly")
        res = guard(suite, cid, text, lambda: sb.step(st, text))
        if res and res.status == "exited":
            record(suite, cid, text, "진행 의사 입력 → 빌더 유지",
                   f"빌더 종료(취소 오인), 상태 전체 소실. reply={res.reply[:60]!r}",
                   "State Machine", "High")

    # (2) 용어 질문이 필드를 오염시키는지(GLOSSARY 미커버 용어)
    for cid, text in [(f"gloss-{i}", q) for i, q in enumerate(GLOSSARY_QS)]:
        st = fresh(universe="KOSPI")  # strategy_type 질문 단계
        res = guard(suite, cid, text, lambda: sb.step(st, text))
        if res is None:
            continue
        if res.state.strategy_type is not None:
            record(suite, cid, text, "정의 질문 → 상태 불변 + 정의 답변",
                   f"strategy_type={res.state.strategy_type!r}로 필드 오염. reply={res.reply[:80]!r}",
                   "Slot Filling", "High")
        elif res.state == st and "뭐" not in res.reply and not any(
                p.search(text) and a in res.reply for p, a in []):
            pass

    # (2b) 용어 질문에 정의가 답변되는지(막다른 길 여부)
    for cid, term in [("gloss-per", "PER이 뭐야?"), ("gloss-boll", "볼린저 밴드가 뭐야?"),
                      ("gloss-stoch", "스토캐스틱이 뭐야?"), ("gloss-cci", "CCI가 뭐야?")]:
        st = fresh(universe="KOSPI")
        res = guard(suite, cid, term, lambda: sb.step(st, term))
        if res is None:
            continue
        first_line = (res.reply or "").split("\n")[0]
        answered = res.reply and ("예요" in first_line or "말해요" in res.reply
                                  or "지표" in first_line or "준비돼 있지 않아요" in first_line)
        if res.state == st and not answered:
            record(suite, cid, term, "짧은 정의 답변 후 질문 계속",
                   f"정의 없이 같은 질문만 반복: {res.reply[:100]!r}",
                   "Slot Filling", "Medium")

    # (3) 중간 정정(이미 채워진 필드 변경) — 조용한 무시 여부
    st = fresh(universe="KOSPI", strategy_type="momentum", lookback_days=63, lookback_label="3개월")
    res = guard(suite, "correct-univ", "코스닥으로 바꿔줘", lambda: sb.step(st, "코스닥으로 바꿔줘"))
    if res is not None:
        if res.state.universe == "KOSPI" and "코스닥" not in res.reply:
            record(suite, "correct-univ", "코스닥으로 바꿔줘",
                   "유니버스 변경 반영 또는 변경 확인 질문",
                   f"조용히 무시(universe={res.state.universe}), reply={res.reply[:80]!r}",
                   "State Machine", "High")
    st2 = fresh(universe="KOSPI", strategy_type="momentum", lookback_days=63, lookback_label="3개월")
    res = guard(suite, "correct-type", "모멘텀 말고 골든크로스로 바꿔줘",
                lambda: sb.step(st2, "모멘텀 말고 골든크로스로 바꿔줘"))
    if res is not None and res.state.strategy_type == "momentum" and "골든" not in res.reply:
        record(suite, "correct-type", "모멘텀 말고 골든크로스로 바꿔줘",
               "전략 유형 변경 반영/확인", f"조용히 무시, reply={res.reply[:80]!r}",
               "State Machine", "High")

    # (4) 정정 표현 '말고' — 잘못된 값 선택
    st = fresh(universe="KOSPI", strategy_type="momentum")
    res = guard(suite, "malgo-lookback", "3개월 말고 6개월", lambda: sb.step(st, "3개월 말고 6개월"))
    if res is not None and res.state.lookback_days == 63:
        record(suite, "malgo-lookback", "3개월 말고 6개월", "6개월(=126일)",
               f"3개월(63일)로 오파싱 — '말고' 앞 값을 선택. ack={res.reply[:60]!r}",
               "Parameter Parsing", "High")

    # (5) 모순/경계값
    st = fresh(universe="KOSPI", strategy_type="rsi", rsi_period=14)
    res = guard(suite, "rsi-invert", "과매도 80 과매수 20", lambda: sb.step(st, "과매도 80 과매수 20"))
    if res is not None and res.state.rsi_oversold == 20:
        record(suite, "rsi-invert", "과매도 80 과매수 20 (모순 입력)",
               "모순 안내 후 확인 질문",
               f"조용히 재정렬: oversold={res.state.rsi_oversold}, overbought={res.state.rsi_overbought}",
               "Validation", "Medium")
    st = fresh(universe="KOSPI", strategy_type="rsi", rsi_period=14)
    res = guard(suite, "rsi-eq", "50 50", lambda: sb.step(st, "50 50"))
    if res is not None and res.state.rsi_oversold == 50 and res.state.rsi_overbought == 50:
        record(suite, "rsi-eq", "50 50", "과매도=과매수 거부/되묻기",
               "동일값 수락 — 매수·매도 신호 경계가 겹치는 전략 생성",
               "Validation", "Medium")
    st = fresh(universe="KOSPI", strategy_type="golden_cross", ma_kind="sma")
    res = guard(suite, "ma-eq", "20일 20일", lambda: sb.step(st, "20 20"))
    if res is not None and res.state.ma_short == res.state.ma_long == 20:
        record(suite, "ma-eq", "20 20", "단기=장기 거부/되묻기",
               "동일 기간 수락 — 교차가 발생 불가능한 전략", "Validation", "Medium")

    # (6) 방향 무시(가치 파라미터)
    st = fresh(universe="KOSPI", strategy_type="value")
    res = guard(suite, "value-dir", "PBR 5 이상 ROE 3 이하", lambda: sb.step(st, "PBR 5 이상 ROE 3 이하"))
    if res is not None and (res.state.value_pbr == 5 or res.state.value_roe == 3):
        record(suite, "value-dir", "PBR 5 이상 ROE 3 이하 (역방향 요청)",
               "방향 불일치 안내(빌더는 PBR≤·ROE≥ 고정)",
               f"방향 무시하고 수락: pbr<={res.state.value_pbr}, roe>={res.state.value_roe} — 사용자의 의도와 정반대 스크리닝",
               "Parameter Parsing", "High")

    # (7) 경계값 수락 여부
    st = fresh(universe="KOSPI", strategy_type="rsi")
    res = guard(suite, "rsi-p0", "0", lambda: sb.step(st, "0"))
    if res is not None and res.state.rsi_period == 0:
        # synthesize에서 0 or 14 → 14로 조용히 치환되는지 확인
        note = ""
        if sb.required_missing(res.state) != "rsi_period":
            note = "0이 '채워짐'으로 통과"
        record(suite, "rsi-p0", "RSI 기간=0", "범위 밖 값 거부/되묻기",
               f"rsi_period=0 수락({note}) — 이후 합성 시 14로 조용히 치환", "Validation", "Medium")
    st = fresh(universe="KOSPI", strategy_type="momentum", lookback_days=63, lookback_label="3개월")
    res = guard(suite, "hold-0", "0개", lambda: sb.step(st, "0개"))
    if res is not None:
        if "0종목" in res.reply:
            record(suite, "hold-0", "0개", "0 종목 거부",
                   f"'최대 0종목으로 하겠습니다' 확인 문구 출력 후 재질문: {res.reply[:80]!r}",
                   "Slot Filling", "Low")
    res = guard(suite, "hold-99999", "99999개", lambda: sb.step(st, "99999개"))
    if res is not None and res.state.holding_count == 99999:
        record(suite, "hold-99999", "99999개", "상한 안내/제한",
               "99999종목 수락(엔진 하한/상한 보정 여부는 enforce에 의존)", "Validation", "Low")

    # (8) 손절 0%/200%
    st = fresh(universe="KOSPI", strategy_type="momentum", lookback_days=63,
               lookback_label="3개월", holding_count=10, rebalance_cycle="monthly")
    res = guard(suite, "sl-0", "손절 0%", lambda: sb.step(st, "손절 0%"))
    if res is not None and res.state.stop_loss_pct == 0.0 and res.status == "confirmed":
        record(suite, "sl-0", "손절 0%", "0% 손절 거부/되묻기",
               "stop_loss_pct=0.0으로 확정 — 매수 즉시 청산되는 전략", "Validation", "High")
    res = guard(suite, "sl-200", "손절 200%", lambda: sb.step(st, "손절 200%"))
    if res is not None and res.state.stop_loss_pct == 200.0:
        record(suite, "sl-200", "손절 200%", "100% 초과 손절 거부",
               "stop_loss_pct=200 수락 — 도달 불가능한 손절", "Validation", "Medium")

    # (9) 필터 단계: 무관 입력 조용히 소비
    st = fresh(universe="KOSPI", strategy_type="macd", macd_mode="crossover")
    assert sb.required_missing(st) == "filters"
    res = guard(suite, "filter-swallow", "근데 삼성전자만 하면 안돼?",
                lambda: sb.step(st, "근데 삼성전자만 하면 안돼?"))
    if res is not None and res.state.filters_asked and res.state.trend_filter_ma is None:
        record(suite, "filter-swallow", "근데 삼성전자만 하면 안돼? (필터 질문 단계)",
               "질문에 답하거나 재질문", "무관한 입력을 '필터 없음'으로 조용히 소비하고 다음 단계 진행",
               "Slot Filling", "Medium")

    # (10) 청산 거부 후 안내
    st = fresh(universe="KOSPI", strategy_type="momentum", lookback_days=63,
               lookback_label="3개월", holding_count=10, rebalance_cycle="monthly")
    res = guard(suite, "risk-refuse", "없음", lambda: sb.step(st, "없음"))
    if res is not None and res.status == "confirmed":
        record(suite, "risk-refuse", "없음(청산 거부)", "필수 안내 후 되묻기",
               "청산 없이 확정", "Validation", "Critical")

    # (11) 시드 모순: 손절이 두 번 ("손절 5%랑 손절 15%로")
    st = sb.seed_state("코스피 모멘텀 손절 5% 손절 15%")
    if st.stop_loss_pct is not None:
        STATS["S3_seed_dup_sl"] = int(st.stop_loss_pct)

    # (12) 매우 긴 입력
    long_text = "손절 10% " + ("그리고 아무튼 " * 2000)
    st = fresh(universe="KOSPI", strategy_type="momentum", lookback_days=63,
               lookback_label="3개월", holding_count=10, rebalance_cycle="monthly")
    guard(suite, "risk-long", "손절 10% + 12000자", lambda: sb.step(st, long_text))


# ═══════════════════════════════ S4. Single-stock mode ═════════════════════════


def s4_single_stock():
    suite = "S4-single"
    base = dict(single_symbol="005930", single_label="삼성전자")

    # 유니버스/보유수/리밸런싱 질문이 나오면 안 된다
    st = fresh(**base)
    res = guard(suite, "first-q", "", lambda: sb.step(st, ""))
    if res is not None:
        for field, cue in QUESTION_CUES.items():
            if cue.search(res.reply):
                record(suite, "first-q", "(첫 질문)", "단일 종목 모드에서 유니버스/보유수/리밸런싱 질문 없음",
                       f"{field} 질문 감지: {res.reply[:100]!r}", "State Machine", "High")

    # 모멘텀/가치 차단 + 설명
    for cid, text, blocked in [("mom", "모멘텀", True), ("val", "저평가 가치주", True),
                               ("gc", "골든크로스", False)]:
        st = fresh(**base)
        res = guard(suite, f"block-{cid}", text, lambda: sb.step(st, text))
        if res is None:
            continue
        if blocked:
            if res.state.strategy_type is not None:
                record(suite, f"block-{cid}", text, "종목 선별형 유형 차단",
                       f"strategy_type={res.state.strategy_type} 수락", "State Machine", "High")
            elif "적용할 수 없" not in res.reply:
                record(suite, f"block-{cid}", text, "차단 사유 설명", f"설명 없음: {res.reply[:80]!r}",
                       "Prompt Design", "Medium")
        else:
            if res.state.strategy_type != "golden_cross":
                record(suite, f"block-{cid}", text, "golden_cross 수락",
                       f"strategy_type={res.state.strategy_type}", "Slot Filling", "Medium")

    # 완주: 골든크로스 + 기본 + 필터없음 + 손절
    st = fresh(**base)
    convo = ["골든크로스", "단순", "5 20", "없음", "10% 손절"]
    for i, text in enumerate(convo):
        res = guard(suite, f"walk-{i}", text, lambda s=st, t=text: sb.step(s, t))
        if res is None:
            return
        st = res.state
        if res.status == "confirmed":
            parsed = guard(suite, "walk-dsl", str(convo), lambda: sb.build_parsed_strategy(st))
            if parsed is not None:
                d = parsed.model_dump()
                if d.get("target_symbols") != ["005930"]:
                    record(suite, "walk-dsl", str(convo), "target_symbols=[005930]",
                           f"{d.get('target_symbols')}", "DSL Generation", "Critical")
                if d.get("max_positions") != 1:
                    record(suite, "walk-dsl", str(convo), "max_positions=1",
                           f"{d.get('max_positions')}", "DSL Generation", "High")
                if d.get("rebalancing_period") != "none":
                    record(suite, "walk-dsl", str(convo), "rebalancing=none",
                           f"{d.get('rebalancing_period')}", "DSL Generation", "High")
            return
    record(suite, "walk", str(convo), "5턴 내 confirmed", f"미완료 expecting={sb.required_missing(st)}",
           "State Machine", "High")


# ═══════════════════════════════ S5. Validation agent ══════════════════════════


def s5_validation():
    suite = "S5-validation"
    from ai.strategy_validation_agent import StrategyValidationAgent
    from api.coach_routes import _validation_payload
    agent = StrategyValidationAgent()

    cases = {
        "empty": {},
        "no-entry": {"universe": ["KOSPI"], "max_positions": 10, "stop_loss_pct": 10},
        "no-exit-no-risk": {"universe": ["KOSPI"], "max_positions": 10,
                            "entry_signals": [{"indicator": "rsi", "signal_type": "buy", "operator": "<=", "value": 30}]},
        "no-universe": {"entry_signals": [{"indicator": "rsi", "signal_type": "buy", "operator": "<=", "value": 30}],
                        "max_positions": 10, "stop_loss_pct": 10},
        "zero-positions": {"universe": ["KOSPI"], "max_positions": 0, "stop_loss_pct": 10,
                           "entry_signals": [{"indicator": "rsi", "signal_type": "buy", "operator": "<=", "value": 30}]},
        "neg-stop": {"universe": ["KOSPI"], "max_positions": 10, "stop_loss_pct": -10,
                     "entry_signals": [{"indicator": "rsi", "signal_type": "buy", "operator": "<=", "value": 30}]},
        "contradictory-rsi": {"universe": ["KOSPI"], "max_positions": 10, "stop_loss_pct": 10,
                              "entry_signals": [
                                  {"indicator": "rsi", "signal_type": "buy", "operator": ">=", "value": 80},
                                  {"indicator": "rsi", "signal_type": "buy", "operator": "<=", "value": 20}]},
        "contradictory-per": {"universe": ["KOSPI"], "max_positions": 10, "stop_loss_pct": 10,
                              "fundamental_filters": [
                                  {"metric": "per", "operator": "<=", "value": 5},
                                  {"metric": "per", "operator": ">=", "value": 20}]},
    }
    expect_invalid = {"empty", "no-entry", "zero-positions", "neg-stop"}
    for cid, strategy in cases.items():
        result = guard(suite, cid, strategy, lambda: agent.validate(_validation_payload(strategy)))
        if result is None:
            continue
        is_valid = result.get("is_valid")
        issues = result.get("issues", [])
        STATS[f"S5_{cid}_valid_{is_valid}"] += 1
        if cid in expect_invalid and is_valid:
            record(suite, cid, strategy, "is_valid=false", f"is_valid=true, issues={issues}",
                   "Validation", "High")
        if cid.startswith("contradictory") and is_valid and not issues:
            record(suite, cid, strategy, "모순 조건 지적", "is_valid=true, 이슈 없음 — 동시 성립 불가 조건 통과",
                   "Validation", "Medium")


# ═══════════════════════════════ S6. NL variation(rule parse) ══════════════════


def s6_nl_variation():
    suite = "S6-nlvar"
    from engine.nl_parser import _parse_rule_based_strategy

    groups = {
        "per10": ["코스피에서 PER 10 이하 종목 10개 매수, 매월 리밸런싱, 손절 10%",
                  "코스피에서 PER가 10보다 낮은 종목 10개 매수, 매월 리밸런싱, 손절 10%",
                  "코스피에서 PER 10 밑인 종목 10개 매수, 매월 리밸런싱, 손절 10%",
                  "코스피에서 PER under 10 종목 10개 매수, 매월 리밸런싱, 손절 10%",
                  "코스피에서 PER <= 10 종목 10개 매수, 매월 리밸런싱, 손절 10%",
                  "코스피에서 PER가 십 이하인 종목 10개 매수, 매월 리밸런싱, 손절 10%"],
        "sl-tp": ["코스피 모멘텀 상위 10종목, 손절 10% 익절 20%",
                  "코스피 모멘텀 상위 10종목, 10% 손절 20% 익절",
                  "코스피 모멘텀 상위 10종목, 10%에 손절하고 20%에 익절",
                  "코스피 모멘텀 상위 10종목, 손절은 10 퍼센트 익절은 20 퍼센트"],
    }
    for gid, variants in groups.items():
        parses = {}
        for v in variants:
            p = guard(suite, f"{gid}", v, lambda: _parse_rule_based_strategy(v))
            parses[v] = None if p is None else p.model_dump()
        # 비교: 결정적으로 파싱된 것들끼리 핵심 필드 일치해야 함.
        # 연산자 <=/<는 '이하'/'보다 낮은'의 의미상 올바른 구분이므로 동일시한다.
        def _norm_filters(filters):
            out = []
            for f in filters or []:
                op = f.get("operator")
                op = {"<": "<=", ">": ">="}.get(op, op)
                out.append((f.get("metric"), op, f.get("value")))
            return sorted(out, key=str)

        keyfields = ["stop_loss_pct", "take_profit_pct", "ranking_metric"]
        seen = {}
        for v, d in parses.items():
            if d is None:
                STATS[f"S6_{gid}_llm_fallback"] += 1
                continue
            core = {k: d.get(k) for k in keyfields}
            core["fundamental_filters"] = _norm_filters(d.get("fundamental_filters"))
            key = json.dumps(core, ensure_ascii=False, sort_keys=True, default=str)
            seen.setdefault(key, []).append(v)
        if len(seen) > 1:
            record(suite, gid, json.dumps(list(parses.keys()), ensure_ascii=False),
                   "동일 의미 → 동일 핵심 필드",
                   "불일치:\n" + "\n".join(f"{k[:200]} <= {vs}" for k, vs in seen.items()),
                   "Parameter Parsing", "High")


# ═══════════════════════════════ S7. Knowledge coverage ════════════════════════


def s7_coverage():
    suite = "S7-coverage"
    from engine.nl_parser import _parse_rule_based_strategy, _mentioned_unsupported_concepts

    indicators = {
        "PEG": "코스피에서 PEG 1 이하 종목 10개 매수, 매월 리밸런싱, 손절 10%",
        "PCR": "코스피에서 PCR 5 이하 종목 10개 매수, 매월 리밸런싱, 손절 10%",
        "FCF Yield": "코스피에서 FCF 수익률 5% 이상 종목 10개, 매월 리밸런싱, 손절 10%",
        "영업이익률": "코스피에서 영업이익률 20% 이상 종목 10개, 매월 리밸런싱, 손절 10%",
        "ATR": "코스피 종목 ATR 기반 손절로 매수, 10종목, 손절 10%",
        "OBV": "코스피에서 OBV 상승 전환 종목 10개 매수, 손절 10%",
        "이치모쿠": "코스피에서 이치모쿠 구름대 돌파 시 매수, 10종목, 손절 10%",
        "VWAP": "코스피에서 VWAP 위로 돌파하면 매수, 10종목, 손절 10%",
        "Williams %R": "코스피에서 윌리엄스 %R -80 이하 매수, 10종목, 손절 10%",
        "MFI": "코스피에서 MFI 20 이하 매수, 10종목, 손절 10%",
        "ADX": "코스피에서 ADX 25 이상일 때 매수, 10종목, 손절 10%",
        "배당수익률": "코스피에서 배당수익률 4% 이상 종목 10개, 매월, 손절 10%",
    }
    for name, prompt in indicators.items():
        p = guard(suite, name, prompt, lambda: _parse_rule_based_strategy(prompt))
        concepts = guard(suite, name + "-concepts", prompt, lambda: _mentioned_unsupported_concepts(prompt))
        if p is None:
            # LLM 폴백 필요 — 미지원이면 concepts에 잡혀야 안내가 나간다
            STATS[f"S7_{name}_ruleparse_none"] += 1
            continue
        d = p.model_dump()
        text_repr = json.dumps(d, ensure_ascii=False, default=str)
        mentioned = name.split()[0].lower().replace("%", "")
        reflected = mentioned in text_repr.lower() or (concepts or [])
        # 지표가 DSL 어디에도 없고 미지원 개념으로도 감지 안 되면 조용한 누락
        keyname = {"이치모쿠": "ichimoku", "배당수익률": "dividend", "영업이익률": "operating",
                   "윌리엄스": "williams"}.get(mentioned, mentioned)
        if keyname not in text_repr.lower() and not concepts:
            record(suite, name, prompt, "DSL 반영 또는 미지원 안내(notices)",
                   f"조용한 누락 — 파싱 결과에 {name} 없음, 미지원 개념 감지도 없음. "
                   f"entry={d.get('entry_signals')}, filters={d.get('fundamental_filters')}",
                   "Parameter Parsing", "High")


# ═══════════════════════════════ S8. seed_state fuzz ═══════════════════════════


def s8_seed_fuzz():
    suite = "S8-seed"
    seeds = [
        "", " ", "ㅋㅋㅋ", "PER", "손절", "손절 10% 익절 5% 손절 20%",
        "코스피 코스닥 ETF 전부 다", "모멘텀 골든크로스 볼린저 전부 섞어줘",
        "3개월 6개월 1년", "10개 20개 30종목", "매일 매주 매월 리밸런싱",
        "손절 -10%", "익절 0%", "0개월 수익률로 0종목",
        "a" * 5000, "손절 10%" * 300,
        "반도체 이차전지 바이오 자동차 전부", "원자로 관련주", "우주항공 테마",
    ]
    for i, s in enumerate(seeds):
        st = guard(suite, f"seed-{i}", s[:60], lambda: sb.seed_state(s))
        if st is None:
            continue
        # 시드 직후 첫 스텝도 안전해야
        guard(suite, f"seed-{i}-step", s[:60], lambda: sb.step(st, ""))
    # 손절 중복: 어느 값이 이겼는지 확인
    st = sb.seed_state("코스피 모멘텀 손절 10% 익절 5% 손절 20%")
    if st.stop_loss_pct not in (10.0,):
        record(suite, "dup-sl", "손절 10% 익절 5% 손절 20%", "첫 손절값(10) 채택+중복 안내",
               f"stop_loss={st.stop_loss_pct}, take_profit={st.take_profit_pct}",
               "Parameter Parsing", "Low")


# ═══════════════════════════════ 실행 ══════════════════════════════════════════

def main():
    random.seed(42)
    _orig_step = sb.step
    def counted_step(*a, **kw):
        STATS["total_step_calls"] += 1
        return _orig_step(*a, **kw)
    sb.step = counted_step
    _orig_classify = classify
    globals()["classify"] = lambda *a, **kw: (STATS.__setitem__("total_classify_calls", STATS["total_classify_calls"] + 1) or _orig_classify(*a, **kw))
    print("S1 classifier fuzz...", flush=True)
    s1_classifier()
    print("S2 builder random-walk fuzz...", flush=True)
    s2_builder_fuzz(1200)
    print("S3 directed probes...", flush=True)
    s3_directed()
    print("S4 single-stock mode...", flush=True)
    s4_single_stock()
    print("S5 validation agent...", flush=True)
    s5_validation()
    print("S6 NL variation...", flush=True)
    s6_nl_variation()
    print("S7 knowledge coverage...", flush=True)
    s7_coverage()
    print("S8 seed fuzz...", flush=True)
    s8_seed_fuzz()

    out = {
        "stats": dict(STATS),
        "failure_count": len(FAILURES),
        "failures": FAILURES,
    }
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qa_builder_fuzz_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    # 요약
    by_cat = Counter(f["category"] for f in FAILURES)
    by_sev = Counter(f["severity"] for f in FAILURES)
    by_suite = Counter(f["suite"] for f in FAILURES)
    print("\n=== SUMMARY ===")
    print("total stats:", dict(STATS))
    print("failures:", len(FAILURES))
    print("by severity:", dict(by_sev))
    print("by category:", dict(by_cat))
    print("by suite:", dict(by_suite))
    print("results ->", out_path)


if __name__ == "__main__":
    main()
