"""미지원 개념 섀도 대조 하니스 — 정규식 게이트 vs LLM 레인 커버리지.

목적
----
원문 정규식 게이트(`nl_parser._UNSUPPORTED_CONCEPT_PATTERNS`, 대원칙 1 미이관 부채)를
primary 레인에서 강등해도 안전한지 판정할 성적표를 만든다. 실사용 입력을 기다리지
않고, **정규식이 울리는 조건이 유한하다는 점**을 이용해 개념별 발화 코퍼스를 직접
만들어 전수 대조한다(사용자 결정 2026-08-12).

케이스마다:
  정답지  = `_mentioned_unsupported_concepts(prompt)` (게이트가 울리는 개념들)
  LLM 레인 = `run_primary_parse(prompt)` 실행 + `validate_intent` 리포트의 원시
            `unsupported_features` 캡처(call_tool 래핑 — 프로덕션 코드 무변경)
  판정    = 대상 개념이 다음 중 하나로 다뤄졌는가:
    reported  LLM이 unsupported_features로 보고 (강등 후 잔여 미지원 안내가 잇는다)
    pending   값-대기 조건으로 이해 (concepts_covered_by_pending)
    asked     되묻기 질문/이월 큐가 그 개념을 다룸
    expressed 전략에 실제 반영 (concepts_expressed_in_strategy)
    noticed   다른 안내(notices)가 그 개념을 언급
    SILENT    위 전부 아님 — 강등하면 침묵이 되는 격차

판정에 쓰는 문자열은 전부 LLM 출력·우리 응답이다(개념 정규식을 원문이 아니라
그 문자열들에 돌린다 — `concepts_covered_by_pending`과 같은 계약).

'sector'는 측정 대상이 아니다 — primary 레인은 term-in 체인(§ 11-3)이 단일 권위라
게이트가 이미 항상 제외한다(강등해도 잃을 것이 없다).

실행
----
    python scripts/qa_unsupported_shadow.py [--check-corpus] [--only 개념1,개념2]
        [--out scripts/.cache/qa_unsupported_shadow.jsonl] [--refresh]

사전 조건: 로컬 Ollama(`ollama serve`) 가동. 결과는 케이스 단위로 증분 기록되며
재실행 시 완료된 케이스는 건너뛴다(--refresh 로 초기화).
"""

from __future__ import annotations

# 데드락/세그폴트 가드 — 다른 QA 하니스와 동일(반드시 import 전에).
import os
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("POLARS_MAX_THREADS", "1")

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# 루트 .env 로드(setdefault — 이미 export된 값 우선). 서버와 같은 모델 슬롯을 쓴다.
_env = ROOT / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

from engine.nl_parser import (  # noqa: E402
    _UNSUPPORTED_CONCEPT_RE,
    _compact,
    _mentioned_unsupported_concepts,
    concepts_covered_by_pending,
    concepts_expressed_in_strategy,
)

# ─── 개념별 발화 코퍼스 ───────────────────────────────────────────────────────
# 각 발화는 해당 개념의 정규식이 실제로 울려야 한다(--check-corpus 가 검증).
# 전략 요청 형태로 쓴다 — primary 레인은 전략 파이프라인 대상 intent만 처리한다.
CORPUS: dict[str, list[str]] = {
    "volatility": [
        "변동성 낮은 종목 위주로 담는 전략 만들어줘",
        "주가 변동성이 작은 안정적인 종목 20개 매수",
    ],
    "cash_flow": [
        "잉여현금흐름 좋은 회사만 골라서 투자하는 전략",
        "영업활동현금흐름이 흑자인 기업 위주로 사줘",
    ],
    "cash_weight": [
        "주식 70%만 사고 현금 비중 30% 유지하는 전략",
        "하락장엔 현금 유지 비중을 늘리는 식으로 운용해줘",
    ],
    "dividend": [
        "배당 잘 주는 회사를 오래 들고 가는 전략 만들어줘",
        "배당이 꾸준히 성장하는 기업에 투자하고 싶어",
    ],
    "roic": [
        "ROIC 높은 기업만 골라 담는 전략",
        "투하자본이익률이 우수한 회사 위주로 매수해줘",
    ],
    "beta": [
        "베타 낮은 종목으로 방어적인 전략 만들어줘",
        "시장 베타 0.8 이하인 종목만 매수",
    ],
    "interest_coverage": [
        "이자보상배율 3배 이상인 재무 건전 기업만 사줘",
        "이자보상배률 높은 회사 위주 전략",
    ],
    "quality_score": [
        "피오트로스키 점수 높은 종목 전략 만들어줘",
        "알트만 Z-score로 부실기업 걸러내고 매수",
    ],
    "turnover_ratio": [
        "재고 회전율 좋은 제조업체 위주로 담아줘",
        "매출채권 회전율 높은 기업만 골라 전략 구성",
    ],
    "buyback": [
        "자사주 매입하는 기업 위주로 사는 전략",
        "자사주 소각 발표한 종목에 투자하고 싶어",
    ],
    "valuation_exit": [
        "밸류에이션이 비싸지면 파는 전략 만들어줘",
        "목표 밸류에이션 도달 시 청산하는 식으로",
    ],
    "relative_to_market": [
        "시장보다 수익률 좋은 종목만 골라 담는 전략",
        "시장평균 대비 저평가된 종목 매수",
    ],
    "earnings": [
        "실적 좋아지는 기업 위주로 사는 전략 만들어줘",
        "컨센서스 상회하는 종목에 투자하고 싶어",
    ],
    "news": [
        "PER 10 이하인데 최근 뉴스 기반 분위기도 좋은 종목 매수",
        "RSI 30 이하이면서 호재 있는 종목만 골라줘",
    ],
    "supply_demand": [
        "외국인 순매수 들어오는 종목 위주 전략",
        "공매도 잔고 적은 종목만 골라 매수해줘",
    ],
    "profitability_transition": [
        "흑자전환한 기업에 투자하는 전략 만들어줘",
        "3년 연속 흑자인 회사만 골라 담아줘",
    ],
    "ema_alignment": [
        "이동평균선 정배열인 종목 매수 전략",
        "역배열로 꺾인 종목은 제외하고 사줘",
    ],
    "min_hold_period": [
        "한번 사면 최소 3개월은 보유하는 전략",
        "최소 6개월은 들고 가는 장기 전략 만들어줘",
    ],
    "partial_exit": [
        "수익 나면 절반 익절하고 나머지는 계속 들고 가는 전략",
        "10% 오르면 일부 청산하는 식으로 만들어줘",
    ],
    "new_low": [
        "52주 신저가 근처 종목을 줍는 전략",
        "신저가 찍고 반등하는 종목 매수",
    ],
    "atr_stop": [
        "ATR 2배로 손절선 잡는 전략 만들어줘",
        "손절은 ATR 기준으로 유동적으로",
    ],
    "averaging_down": [
        "떨어지면 물타기로 추가매수하는 전략",
        "상승 추세면 피라미딩으로 불려가는 식으로 만들어줘",
    ],
    "intraday": [
        "장중 실시간으로 매매하는 전략 만들어줘",
        "분봉 보고 단타 대응하는 전략",
    ],
    "overseas": [
        "나스닥 기술주 위주로 투자하는 전략 만들어줘",
        "애플이랑 엔비디아 담는 전략 짜줘",
    ],
    "preferred_stock": [
        "삼성전자 우선주만 사는 전략 만들어줘",
        "우선주 위주로 배당 노리는 전략",
    ],
    "volume_multiple": [
        "거래량이 평소보다 3배 터진 종목 매수 전략",
        "거래대금 2배 급증한 종목만 골라줘",
    ],
    "ichimoku": [
        "일목균형표 구름대 위로 올라온 종목 매수",
        "이치모쿠 기준으로 추세 확인해서 사는 전략",
    ],
    "vwap": [
        "VWAP 위에서 매수하는 전략 만들어줘",
        "브이왑 아래로 떨어지면 파는 식으로",
    ],
    "peg": [
        "PEG 1 이하인 성장주 담는 전략",
        "peg 낮은 종목 위주로 매수해줘",
    ],
    "fibonacci": [
        "피보나치 되돌림 61.8%에서 사는 전략",
        "fibonacci 레벨로 지지 확인하고 매수",
    ],
    "elliott": [
        "엘리엇 파동 3파에 올라타는 전략 만들어줘",
        "파동이론 기준으로 저점 잡아서 사줘",
    ],
    "candle_pattern": [
        "망치형 캔들 나온 종목 매수 전략",
        "장대 양봉 뜬 다음날 사는 식으로 만들어줘",
    ],
}

# 정상 전략 대조군 — 과잉 보고(지원 지표를 미지원으로 보고)·해석 실패 회귀 감시.
# 프롬프트에 미지원 규칙을 늘리다 복합 정상 입력의 JSON이 조기 종료된 실측
# (2026-08-13, 'PER 10 이하이고 ROE 15%…' 바깥 객체 미닫힘) 재발 방지.
CONTROLS: list[str] = [
    "PER 10 이하이고 ROE 15% 이상인 종목 20개 매수, 손절 5%",
    "골든크로스에 사고 데드크로스에 팔아줘",
    "RSI 30 이하에서 매수, 70 이상에서 매도, 월간 리밸런싱",
    "배당수익률 3% 이상 종목으로 전략 만들어줘",
]

CONCEPT_RX = dict(_UNSUPPORTED_CONCEPT_RE)


def check_corpus() -> int:
    """LLM 없이 정답지만 검증 — 각 발화에서 대상 개념 정규식이 실제로 울리는가."""
    bad = 0
    for concept, prompts in CORPUS.items():
        for prompt in prompts:
            hits = _mentioned_unsupported_concepts(prompt)
            if concept not in hits:
                print(f"✗ [{concept}] 게이트 미발화: {prompt} (발화={hits})")
                bad += 1
    total = sum(len(v) for v in CORPUS.values())
    print(f"코퍼스 {total}건 중 정답지 불일치 {bad}건")
    return 1 if bad else 0


def _match_concept(concept: str, *texts) -> bool:
    """개념 정규식을 LLM 출력·응답 문자열에 돌린다(원문이 아니다 — § 3-1 대조)."""
    rx = CONCEPT_RX[concept]
    return any(rx.search(_compact(str(t))) for t in texts if t)


def run_case(concept: str, prompt: str) -> dict:
    from strategy_conversation import tools as sc_tools
    from strategy_conversation.primary import run_primary_parse

    captured: list = []
    original_call = sc_tools.call

    def capturing_call(name, **kwargs):
        result = original_call(name, **kwargs)
        if name == "validate_intent":
            captured.append(list(result.report.unsupported_features or []))
        return result

    sc_tools.call = capturing_call
    t0 = time.time()
    try:
        payload = run_primary_parse(prompt)
    finally:
        sc_tools.call = original_call
    elapsed = round(time.time() - t0, 1)

    row = {
        "concept": concept,
        "prompt": prompt,
        "gate_hits": _mentioned_unsupported_concepts(prompt),
        "elapsed_s": elapsed,
    }
    if payload is None:
        row["verdict"] = "CONTROL_FAIL" if concept == "_control" else "LANE_FAIL"
        return row

    parsed = payload.get("parsed")
    notices = payload.get("notices") or []
    question = payload.get("clarification_question") or ""
    queue_texts = [
        q.get("question") or "" for q in ((payload.get("pending_ask") or {}).get("queue") or [])
    ]
    raw_features = [f for group in captured for f in group]
    pending = payload.get("pending_conditions") or []

    if concept == "_control":
        # 정상 전략 대조군 — 해석 성공 + 미지원 보고/안내가 없어야 한다.
        overreport = bool(raw_features) or any("지원하지 않아" in n for n in notices)
        row.update({
            "verdict": "CONTROL_OVERREPORT" if overreport else "CONTROL_OK",
            "raw_unsupported_features": raw_features,
            "notices": notices,
        })
        return row

    covered_by = []
    if _match_concept(concept, *raw_features):
        covered_by.append("reported")
    if concept in concepts_covered_by_pending(pending):
        covered_by.append("pending")
    if _match_concept(concept, question, *queue_texts):
        covered_by.append("asked")
    if parsed is not None and concept in concepts_expressed_in_strategy(parsed, prompt):
        covered_by.append("expressed")
    if _match_concept(concept, *notices):
        covered_by.append("noticed")

    row.update({
        "verdict": covered_by[0] if covered_by else "SILENT",
        "covered_by": covered_by,
        "raw_unsupported_features": raw_features,
        "notices": notices,
        "question": question[:160],
        "queue": [q[:100] for q in queue_texts],
        "pending_labels": [c.get("label") for c in pending],
    })
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-corpus", action="store_true", help="정답지 검증만(LLM 미호출)")
    ap.add_argument("--only", default=None, help="쉼표 구분 개념 이름만 실행")
    ap.add_argument("--out", default=str(ROOT / "scripts/.cache/qa_unsupported_shadow.jsonl"))
    ap.add_argument("--refresh", action="store_true", help="기존 결과 무시하고 전체 재실행")
    args = ap.parse_args()

    if args.check_corpus:
        return check_corpus()

    corpus = CORPUS
    if args.only:
        wanted = {c.strip() for c in args.only.split(",")}
        corpus = {k: v for k, v in CORPUS.items() if k in wanted}

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done: set = set()
    if out.exists() and not args.refresh:
        for line in out.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                done.add((r["concept"], r["prompt"]))
    elif args.refresh and out.exists():
        out.unlink()

    cases = [(c, p) for c, prompts in corpus.items() for p in prompts]
    if not args.only:
        cases = [("_control", p) for p in CONTROLS] + cases
    with out.open("a") as fh:
        for i, (concept, prompt) in enumerate(cases, 1):
            if (concept, prompt) in done:
                print(f"[{i}/{len(cases)}] {concept} — skip(완료)", flush=True)
                continue
            row = run_case(concept, prompt)
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            print(f"[{i}/{len(cases)}] {concept} → {row['verdict']} ({row['elapsed_s']}s)",
                  flush=True)

    # 성적표
    rows = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
    tally = Counter(r["verdict"] for r in rows)
    print("\n=== 판정 총량 ===")
    for k, v in tally.most_common():
        print(f"  {k:10s} {v}")
    silent = [r for r in rows if r["verdict"] == "SILENT"]
    fails = [r for r in rows if r["verdict"] == "LANE_FAIL"]
    print(f"\n=== SILENT 격차 {len(silent)}건 ===")
    for r in silent:
        print(f"  [{r['concept']}] {r['prompt']}")
        print(f"    LLM 보고={r['raw_unsupported_features']} notices={r['notices']}")
    if fails:
        print(f"\n=== LANE_FAIL {len(fails)}건 ===")
        for r in fails:
            print(f"  [{r['concept']}] {r['prompt']}")
    covered = sum(v for k, v in tally.items() if k not in ("SILENT", "LANE_FAIL"))
    total = len(rows)
    if total:
        print(f"\n커버리지: {covered}/{total} ({covered / total * 100:.0f}%) — "
              f"SILENT {len(silent)}·LANE_FAIL {len(fails)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
