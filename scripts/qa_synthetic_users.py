#!/usr/bin/env python3
"""가상 사용자 QA — 실제 사용자 대신 AI 손님이 전략 대화를 걸고, 받아 온 전략을 정답지와 대조한다.

실제 사용자가 없으면 시험지 밖의 말투(초보 표현·구어체·나눠 말하기·말 바꾸기)로 들어오는 입력이
없다. 이 하니스는 미스터리 쇼퍼처럼 동작한다:

1. **숨은 의도(정답지)** — 가상 사용자 모델(Gemini, 해석기와 다른 계열)이 원하는 전략을
   `qa_template_expectations.json`과 같은 형식으로 먼저 정한다. 스크립트가 허용 키만 남긴다.
2. **페르소나 발화** — 같은 모델이 그 정답지를 페르소나 말투의 첫 발화로 옮긴다. 일부 항목은
   일부러 아껴 두었다가 되묻기 답변이나 추가 턴에서 말한다.
3. **실제 경로로 대화** — `/strategy/parse`에 프론트 무상태 에코 계약(qa_multiturn_binding과
   같음)으로 여러 턴을 보낸다. 되묻기가 오면 가상 사용자가 자기 정답지를 보고 답한다.
4. **대조** — 마지막 응답을 예시 게이트의 판정(`qa_template_detect.analyze`)으로 정답지와
   대조하고, 턴 사이 결속 신호(같은 질문 반복·확정 필드 소실·해석 실패)를 구조 필드로 센다.

판정 입력은 정답지(구조화 데이터)와 응답의 구조 필드뿐이다 — 가상 사용자 발화를 정규식으로
읽지 않는다(대원칙 1). 정답지와 발화가 어긋난 생성 오류가 있을 수 있으므로, 결함 후보는 사람이
대화를 읽고 확정한다(스킬 `synthetic-user-test` 3단계).

    uv run python scripts/qa_synthetic_users.py --n 6            # 6개 대화
    uv run python scripts/qa_synthetic_users.py --n 3 --seed 7   # 재현용 시드

결과: backend/logs/synthetic_users/<날짜>/<시각>.jsonl + .md (git 미추적).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import qa_template_detect as gate  # noqa: E402  — 판정 정본 재사용

BACKEND = os.environ.get("QA_BACKEND", "http://localhost:8000")
TIMEOUT = int(os.environ.get("QA_TIMEOUT", "300"))
# 2.5-flash 무료 등급은 하루 20건이라 대화 2~3개면 끝난다(2026-11-13 실측) — 기본은 flash-lite.
GEMINI_MODEL = os.environ.get("SYNTH_USER_MODEL", "gemini-3.1-flash-lite")
MAX_TURNS = 8
OUT_DIR = ROOT / "backend/logs/synthetic_users"

PERSONAS = {
    "초보": "주식 투자를 막 시작한 사람. 지표 이름을 정확히 모르고 풀어서 말한다"
            "('RSI가 30 밑' 대신 '많이 떨어져서 과매도일 때, RSI 30 아래'처럼). 존댓말.",
    "구어체": "카톡 치듯 짧고 편하게 말한다. 띄어쓰기를 자주 틀리고 오타가 한두 개 섞인다. 반말.",
    "툭툭": "핵심만 한두 개 던지고 나머지는 되묻기를 받아야 조금씩 말한다. 아주 짧게 말한다.",
    "경험자": "퀀트 용어에 익숙해 한 번에 조건을 많이 나열한다. 약어(PBR·ROE·SL)를 쓴다.",
    "말바꾸기": "처음에 값 하나를 다르게 말했다가 다음 턴에 '아 그거 말고'라며 정답지 값으로 고친다.",
}
FOCUS = ["기술적 지표 위주", "재무 지표 위주", "기술적+재무 혼합", "랭킹(상위 N종목) 포함"]

ALLOWED_SCALAR = {"stop_loss_pct", "take_profit_pct", "hold_period_days", "trailing_stop_pct"}
FUND_TO_COVERAGE = {"pbr": "PBR", "per": "PER", "roe_or_gpa": "ROE", "debt_ratio": "부채비율",
                    "market_cap": "시가총액", "trading_value": "거래대금"}

SPEC_PROMPT = """너는 한국 주식 백테스트 서비스를 시험하는 가상 사용자 시나리오 작성기다.
한국 시장(코스피·코스닥) 전략 하나를 정하고, 그 전략을 아래 페르소나 말투로 처음 말하는 문장을 써라.

페르소나: {persona} — {persona_desc}
전략 성격: {focus}

정답지(spec) 형식 — 아래 키만 쓴다. 쓰는 값은 전부 사용자가 대화 중 **반드시 말할** 값이다.
- "coverage": 쓰는 조건 종류 목록. 허용: {coverage}
- "fundamental": 재무 임계값 {{지표: [값]}}. 지표 허용: pbr, per, roe_or_gpa(ROE %), debt_ratio(%),
  market_cap(단위 억원 — 1조=10000), trading_value(단위 억원). 값만 숫자로.
- "scalar": {{"stop_loss_pct": 7, "take_profit_pct": 20, "hold_period_days": 20, "trailing_stop_pct": 10}} 중 일부. 퍼센트는 7처럼 숫자.
- "signal_numbers": {{"설명": [숫자]}} — 이동평균 기간·RSI 기준값·신고가 룩백일 같은 신호 수치.
- "positions": 보유 종목 수(정수) 또는 생략.
- "exit": 손절·익절·보유기간과 별개인 **매도 신호**(데드크로스·RSI 70 이상·20일선 이탈 등)를 발화에 넣을 때만 true.
조건은 2~5개, 현실적인 값으로. 시장 전망·추천을 묻는 말은 넣지 않는다.
발화에는 정답지 키 이름(exit·coverage·scalar 등)이나 JSON 표기를 쓰지 않는다 — 사람 말로만 쓴다.

출력 JSON:
{{"spec": {{...}},
  "items": ["정답지 항목 키 목록 — 예: coverage:RSI, fundamental.per, scalar.stop_loss_pct, signal_numbers.RSI 기준값, positions, exit"],
  "opening": "첫 발화(페르소나 말투)",
  "mentioned": ["opening에서 정답지 값 그대로 전달한 항목 키"]}}
페르소나가 '툭툭'이면 첫 발화에 항목 1~2개만, '말바꾸기'면 한 항목을 다른 값으로 말하고 그 항목은 mentioned에서 뺀다.
나머지 페르소나도 항목 1개 정도는 첫 발화에서 아껴 둬도 된다."""

REPLY_PROMPT = """너는 한국 주식 백테스트 서비스를 쓰는 가상 사용자다. 페르소나: {persona} — {persona_desc}
네가 원하는 전략(정답지): {spec}
항목 키: {items}
아직 정답지 값대로 전달하지 않은 항목: {pending}

지금까지 대화:
{history}

서비스의 마지막 응답:
- 질문: {question}
- 선택지: {chips}
- 안내: {notices}

다음 사용자 발화를 써라. 규칙:
- 질문이 정답지에 있는 항목이면 정답지 값으로 답한다(선택지에 같은 값이 있으면 그 문구를 그대로 써도 된다).
- 질문이 정답지에 없는 항목이면 선택지 하나를 그대로 고르거나 '그건 안 해도 돼' 식으로 답한다.
- 질문이 없으면 아직 전달하지 않은 항목을 덧붙여 말한다.
- 페르소나 말투를 유지한다. 정답지에 없는 새 조건을 지어내지 않는다.
- 정답지 키 이름(exit·coverage·scalar 등)이나 JSON 표기를 쓰지 않는다. 이미 반영된 조건을 매 턴 되풀이하지 않는다.
출력 JSON: {{"reply": "발화", "mentioned": ["이번 발화에서 정답지 값 그대로 전달한 항목 키"]}}"""


def load_api_key() -> str:
    key = os.environ.get("GOOGLE_API_KEY")
    if key:
        return key
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("GOOGLE_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("GOOGLE_API_KEY가 없습니다(.env 또는 환경변수)")


class QuotaExhausted(RuntimeError):
    """가상 사용자 모델의 일일 한도 소진 — 남은 대화를 시도하지 않고 멈춘다."""


def gemini_json(prompt: str, key: str, temperature: float = 1.0) -> dict:
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{GEMINI_MODEL}:generateContent?key={key}")
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json",
                                 "temperature": temperature}}
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as res:
                data = json.loads(res.read())
            break
        except urllib.error.HTTPError as exc:
            if exc.code != 429:
                raise
            # 분당 한도는 잠깐 기다리면 풀리고, 일일 한도(retryDelay가 몇 시간)는 기다려도 소용없다.
            detail = json.loads(exc.read() or b"{}").get("error", {})
            delay = next((int(float(d["retryDelay"].rstrip("s"))) for d in detail.get("details", [])
                          if "retryDelay" in d), 60)
            if delay > 120 or attempt == 2:
                raise QuotaExhausted(f"{GEMINI_MODEL} 한도 소진(재시도 {delay}s 뒤)") from exc
            time.sleep(delay + 1)
    parts = data["candidates"][0]["content"]["parts"]
    return json.loads("".join(p.get("text", "") for p in parts if not p.get("thought")))


def clean_spec(raw: dict) -> dict:
    """생성된 정답지에서 판정기가 아는 키·형식만 남긴다(형식 정규화, 의미 판정 아님)."""
    spec: dict = {}
    coverage = [c for c in raw.get("coverage") or [] if c in gate._COVERAGE_BY_NAME]
    fund = {m: [float(v) for v in vals if isinstance(v, (int, float))]
            for m, vals in (raw.get("fundamental") or {}).items()
            if m in FUND_TO_COVERAGE and isinstance(vals, list)}
    fund = {m: v for m, v in fund.items() if v}
    for m in fund:
        if FUND_TO_COVERAGE[m] not in coverage:
            coverage.append(FUND_TO_COVERAGE[m])
    scalar = {k: v for k, v in (raw.get("scalar") or {}).items()
              if k in ALLOWED_SCALAR and isinstance(v, (int, float))}
    signals = {k: [float(v) for v in vals if isinstance(v, (int, float))]
               for k, vals in (raw.get("signal_numbers") or {}).items() if isinstance(vals, list)}
    signals = {k: v for k, v in signals.items() if v}
    if coverage:
        spec["coverage"] = coverage
    if fund:
        spec["fundamental"] = fund
    if scalar:
        spec["scalar"] = scalar
    if signals:
        spec["signal_numbers"] = signals
    if isinstance(raw.get("positions"), int) and raw["positions"] > 0:
        spec["positions"] = raw["positions"]
    if raw.get("exit") is True:
        spec["exit"] = True
    return spec


def spec_items(spec: dict) -> list[str]:
    # 재무 지표의 coverage는 fundamental 항목과 같은 말이라 따로 세지 않는다.
    fund_cov = {FUND_TO_COVERAGE[m] for m in spec.get("fundamental", {})}
    items = [f"coverage:{c}" for c in spec.get("coverage", []) if c not in fund_cov]
    items += [f"fundamental.{m}" for m in spec.get("fundamental", {})]
    items += [f"scalar.{k}" for k in spec.get("scalar", {})]
    items += [f"signal_numbers.{k}" for k in spec.get("signal_numbers", {})]
    items += [k for k in ("positions", "exit") if k in spec]
    return items


def post_parse(payload: dict) -> dict:
    req = urllib.request.Request(f"{BACKEND}/strategy/parse", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
        return json.loads(res.read())


def echo_payload(prompt: str, state: dict) -> dict:
    """프론트(page.tsx) 무상태 에코 계약 — qa_multiturn_binding.run_scenario와 같다."""
    payload = {"prompt": prompt, "backend": "ollama"}
    if state.get("parsed"):
        payload["previous_parsed"] = state["parsed"]
        if state.get("pending_ask"):
            payload["pending_ask"] = state["pending_ask"]
        if state.get("question"):
            payload["pending_question"] = state["question"]
        payload["previous_explicit_fields"] = state.get("explicit_fields") or []
        payload["previous_field_metadata"] = state.get("field_metadata") or {}
        payload["previous_artifacts"] = state.get("artifacts") or {}
        payload["previous_declined_fields"] = state.get("declined_fields") or []
    return payload


def run_conversation(idx: int, persona: str, focus: str, key: str) -> dict:
    sid = f"SU{idx:02d}"
    gen = gemini_json(SPEC_PROMPT.format(
        persona=persona, persona_desc=PERSONAS[persona], focus=focus,
        coverage=", ".join(gate._COVERAGE_BY_NAME)), key)
    spec = clean_spec(gen.get("spec") or {})
    items = spec_items(spec)
    record = {"id": sid, "persona": persona, "focus": focus, "spec": spec,
              "turns": [], "findings": [], "fatal": [], "missing": [], "unmatched": []}
    if not items or not gen.get("opening"):
        record["skipped"] = "정답지 생성 실패"
        return record
    pending = [i for i in items if i not in set(gen.get("mentioned") or [])]
    utterance = gen["opening"]
    state: dict = {}
    asked: list[str] = []
    res: dict = {}
    print(f"\n[{sid}] {persona} · {focus} · 항목 {len(items)}개")

    for turn in range(1, MAX_TURNS + 1):
        started = time.perf_counter()
        try:
            res = post_parse(echo_payload(utterance, state))
        except (urllib.error.URLError, TimeoutError) as exc:
            record["findings"].append(f"T{turn} 요청 실패: {exc}")
            break
        q = res.get("clarification_question")
        record["turns"].append({
            "user": utterance, "question": q,
            "chips": res.get("clarification_suggestions") or [],
            "notices": res.get("notices") or [],
            "priority": res.get("clarification_priority"),
            "summary": gate.summarize(res.get("parsed") or {}),
            "elapsed_s": round(time.perf_counter() - started, 1)})
        print(f"  T{turn} 사용자: {utterance[:70]}")
        print(f"       질문  : {(q or '(없음)')[:70]}")

        # 턴 사이 결속 — 응답 구조 필드만 본다(qa_multiturn_binding과 같은 계약).
        if res.get("clarification_priority") == "interpretation_failed":
            record["findings"].append(f"T{turn} 해석 실패")
        if q and not res.get("pending_ask"):
            record["findings"].append(f"T{turn} 질문에 결속(pending_ask) 없음")
        if q and state.get("question") == q:
            record["findings"].append(f"T{turn} 답한 뒤에도 같은 질문 반복: {q[:50]}")
        elif q and q in asked:
            record["findings"].append(f"T{turn} 이전 질문으로 되돌아감: {q[:50]}")
        explicit = res.get("explicit_fields") or []
        lost = sorted(set(state.get("explicit_fields") or []) - set(explicit))
        if lost:
            record["findings"].append(f"T{turn} 확정 필드 소실: {lost}")
        if q:
            asked.append(q)
        state = {"parsed": res.get("parsed"), "pending_ask": res.get("pending_ask"),
                 "question": q, "explicit_fields": explicit,
                 "field_metadata": res.get("field_metadata"), "artifacts": res.get("artifacts"),
                 "declined_fields": res.get("declined_fields") or state.get("declined_fields") or []}

        if not q and not pending:
            break
        if turn == MAX_TURNS:
            record["findings"].append(f"{MAX_TURNS}턴 안에 대화가 끝나지 않음")
            break
        history = "\n".join(f"사용자: {t['user']}\n서비스: {t['question'] or '(질문 없음)'}"
                            for t in record["turns"])
        try:
            nxt = gemini_json(REPLY_PROMPT.format(
            persona=persona, persona_desc=PERSONAS[persona],
            spec=json.dumps(spec, ensure_ascii=False), items=items, pending=pending,
            history=history, question=q or "(없음)", chips=res.get("clarification_suggestions") or [],
            notices=res.get("notices") or []), key, temperature=0.7)
        except QuotaExhausted as exc:
            # 진행 중이던 대화 기록은 남기고, 중간에 끊긴 대화는 대조하지 않는다.
            record["aborted"] = str(exc)
            break
        utterance = str(nxt.get("reply") or "").strip()
        if not utterance:
            record["findings"].append(f"T{turn} 가상 사용자 답변 생성 실패")
            break
        pending = [i for i in pending if i not in set(nxt.get("mentioned") or [])]

    # 가상 사용자의 '전달함' 자기 보고는 자주 빠진다(첫 실행 실측: 말한 ROE를 미전달로 표시해
    # ROE 소실이 대조에서 빠졌다). 그래서 항상 정답지 전체와 대조하고, 미전달로 남은 항목은
    # 리포트에 '확인 필요'로 표시해 사람이 대화를 읽고 가린다.
    record["unsent_items"] = pending
    if res.get("parsed") is not None and not record.get("aborted"):
        tpl = gate.Template("synthetic", "합성", sid, record["turns"][0]["user"], expect=spec)
        flags = gate.analyze(tpl, res)
        record["fatal"], record["missing"], record["unmatched"] = flags.fatal, flags.missing, flags.unmatched
        if flags.position:
            record["findings"].append(flags.position)
    record["final_summary"] = gate.summarize(res.get("parsed") or {})
    return record


def write_report(records: list[dict], stamp: str) -> Path:
    day_dir = OUT_DIR / stamp[:10]
    day_dir.mkdir(parents=True, exist_ok=True)
    base = day_dir / stamp[11:].replace(":", "")
    with open(base.with_suffix(".jsonl"), "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    lines = [f"# 가상 사용자 QA {stamp}", "", f"가상 사용자 모델: {GEMINI_MODEL} · 대화 {len(records)}개", ""]
    for r in records:
        problems = r["fatal"] + [f"미탐지 {m}" for m in r["missing"]] \
            + [f"값 소실 {u}" for u in r["unmatched"]] + r["findings"]
        mark = "건너뜀" if r.get("skipped") else "중단(대조 안 함)" if r.get("aborted") else ("결함 후보 %d" % len(problems) if problems else "이상 없음")
        lines += [f"## {r['id']} · {r['persona']} · {r['focus']} — {mark}", "",
                  f"- 정답지: `{json.dumps(r['spec'], ensure_ascii=False)}`",
                  f"- 최종 전략: {r.get('final_summary', '')}"]
        if r.get("unsent_items"):
            lines.append(f"- 확인 필요 — 가상 사용자가 전달했다고 표시하지 않은 항목: {r['unsent_items']}")
        lines += [f"- ⚠️ {p}" for p in problems]
        lines.append("")
        for i, t in enumerate(r["turns"], 1):
            lines.append(f"  {i}. 사용자: {t['user']}")
            lines.append(f"     서비스: {t['question'] or '(질문 없음)'}  [{t['elapsed_s']}s]")
            for n in t["notices"]:
                lines.append(f"     안내: {n}")
        lines.append("")
    base.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")
    return base


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=6, help="대화 수")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--persona", choices=list(PERSONAS), help="한 페르소나만")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    key = load_api_key()
    names = list(PERSONAS)
    records = []
    for i in range(1, args.n + 1):
        persona = args.persona or names[(i - 1) % len(names)]
        try:
            records.append(run_conversation(i, persona, rng.choice(FOCUS), key))
            if records[-1].get("aborted"):
                break
        except QuotaExhausted as exc:
            print(f"  [SU{i:02d}] {exc} — 남은 대화를 멈춘다")
            records.append({"id": f"SU{i:02d}", "persona": persona, "focus": "", "spec": {},
                            "turns": [], "findings": [], "fatal": [], "missing": [],
                            "unmatched": [], "skipped": str(exc)})
            break
        except (urllib.error.URLError, KeyError, json.JSONDecodeError) as exc:
            print(f"  [SU{i:02d}] 가상 사용자 생성 오류: {exc}")
            records.append({"id": f"SU{i:02d}", "persona": persona, "focus": "", "spec": {},
                            "turns": [], "findings": [], "fatal": [], "missing": [],
                            "unmatched": [], "skipped": f"생성 오류: {exc}"})

    stamp = dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    base = write_report(records, stamp)
    flagged = [r for r in records if r["fatal"] or r["missing"] or r["unmatched"] or r["findings"]]
    print(f"\n대화 {len(records)}개 · 결함 후보 {len(flagged)}개 · "
          f"건너뜀 {sum(1 for r in records if r.get('skipped'))}개")
    print(f"리포트: {base.with_suffix('.md')}")
    if records and records[-1].get("aborted"):
        print(f"  {records[-1]['aborted']} — 남은 대화를 멈췄다")
    judged = [r for r in records if not r.get("skipped") and not r.get("aborted")]
    if not judged:
        print("대조한 대화가 없다 — 점검 실패로 끝낸다")
        return 2
    return 1 if flagged else 0


if __name__ == "__main__":
    raise SystemExit(main())
