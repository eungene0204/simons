"""의도 분류 커버리지 프로브 — 라벨 경계가 실제로 어디 그어져 있는지 관측한다.

**이 프로브가 답하는 질문은 "빈도"가 아니라 "구조"다.** 문항은 사람이 쓴 합성 발화라
실사용 분포를 대신하지 못한다. 대신 "이런 종류의 질문은 어느 라벨로 떨어지는가"는
그대로 드러난다 — 게이트를 어떻게 쪼갤지 설계하는 데 쓰는 자료다.

**정답 라벨을 적지 않는다.** 문항 작성자가 기대 라벨까지 정하면 작성자의 추측이
데이터로 위장된다. 유형(category)만 붙이고 실제 분류 결과를 관측만 한다.

사용:
    python backend/scripts/qa_intent_coverage_probe.py
    python backend/scripts/qa_intent_coverage_probe.py --category fact_lookup
    python backend/scripts/qa_intent_coverage_probe.py --base-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

# 알아들었어도 정형 안내로 끊기는 라벨(conversationDecision.ts의 규제 게이트와 동일 목록).
# 단, 게이트는 라벨과 **직교하는 축**으로 갈린다 — 같은 STOCK_ANALYSIS라도 값 조회가
# 성립하면(fact_metric) 사실로 답하므로 끊긴 것이 아니다(_is_gated 참고).
_GATED = frozenset({
    "STOCK_ANALYSIS", "STOCK_PICK", "STRATEGY_PICK",
    "PERSONAL_ADVICE", "LIVE_TRADING", "UNSUPPORTED_FEATURE",
})
_MISS = frozenset({"UNKNOWN", "OFF_TOPIC"})


def _is_gated(row: Dict[str, Any]) -> bool:
    if row.get("fact_metric") or row.get("list_scope"):
        return False
    return row.get("intent") in _GATED


class Probe(dict):
    """문항 하나. context는 프론트가 실제로 함께 보내는 값만 쓴다."""

    def __init__(self, category: str, query: str, **context: Any):
        super().__init__(category=category, query=query, context=context)


# ── 문항 ────────────────────────────────────────────────────────────────────────
# 유형은 "플랫폼이 실제로 마주칠 법한 질문의 결"로 나눴다. 각 유형이 규제상 허용인지
# 금지인지는 여기 적지 않는다 — 그 판정은 사람이 결과를 보고 한다.

PROBES: List[Probe] = [
    # 1. 종목 사실 조회 — 값을 묻는다(판단을 묻지 않는다)
    Probe("fact_lookup", "삼성전자 PER이 얼마야?"),
    Probe("fact_lookup", "SK하이닉스 시가총액 얼마야?"),
    Probe("fact_lookup", "네이버 작년 영업이익률 알려줘"),
    Probe("fact_lookup", "카카오 부채비율이 몇 퍼센트야?"),
    Probe("fact_lookup", "삼성전자 52주 최고가가 얼마였어?"),
    Probe("fact_lookup", "현대차 배당수익률 알려줘"),

    # 2. 종목 판단 요청 — 사도 되냐를 묻는다
    Probe("stock_judgment", "삼성전자 지금 사도 될까?"),
    Probe("stock_judgment", "카카오 계속 들고 있어도 돼?"),
    Probe("stock_judgment", "SK하이닉스 전망 어때?"),

    # 3. 시장/범위 사실 조회 — 개별 종목이 아니다
    Probe("market_fact", "코스피200에 몇 종목 들어있어?"),
    Probe("market_fact", "코스닥 상장사 수가 몇 개야?"),
    Probe("market_fact", "반도체 업종에 어떤 회사들이 있어?"),
    Probe("market_fact", "2차전지 테마 종목 목록 보여줘"),

    # 4. 플랫폼 사용법·설정 질문
    Probe("platform_usage", "백테스트는 몇 년치까지 돌릴 수 있어?"),
    Probe("platform_usage", "수수료 기본값이 얼마야?"),
    Probe("platform_usage", "슬리피지는 어떻게 계산돼?"),
    Probe("platform_usage", "가상계좌는 어떻게 시작해?"),
    Probe("platform_usage", "전략 저장은 어디서 해?"),

    # 5. 결과 해석 질문 — 백테스트가 끝난 뒤 나오는 결
    Probe("result_reading", "MDD가 -35%면 심한 거야?", active_strategy=True),
    Probe("result_reading", "샤프지수 1.2면 어느 정도야?", active_strategy=True),
    Probe("result_reading", "승률은 높은데 수익이 왜 마이너스야?", active_strategy=True),
    Probe("result_reading", "이 결과 믿을 만한 거야?", active_strategy=True),

    # 6. 대화 상태 자체를 묻는 메타 질문 — 기억에 의존한다
    Probe("conversation_meta", "내가 지금까지 뭘 정했지?", active_strategy=True),
    Probe("conversation_meta", "아까 손절 몇 퍼센트로 했었지?", active_strategy=True),
    Probe("conversation_meta", "지금 몇 단계까지 왔어?", active_strategy=True),
    Probe("conversation_meta", "처음부터 다시 정리해서 보여줘", active_strategy=True),

    # 7. 생략·후속 발화 — 맥락 없이는 뜻이 서지 않는다
    Probe("elliptical", "그럼 그건 몇 이하면 과매도야?",
          history=[("user", "RSI가 뭐야?"),
                   ("assistant", "RSI는 상대강도지수로 0~100 사이 값입니다.")]),
    Probe("elliptical", "다른 예는 없어?",
          history=[("user", "이동평균 전략 예시 알려줘"),
                   ("assistant", "5일선이 20일선을 상향 돌파할 때 매수하는 방식이 있습니다.")]),
    Probe("elliptical", "그럼 반대로 하면?",
          history=[("user", "RSI 30 이하 매수 전략 만들어줘"),
                   ("assistant", "RSI 30 이하 진입 조건으로 잡았습니다.")]),
    Probe("elliptical", "왜?", active_strategy=True,
          history=[("user", "종목 5개로 해줘"),
                   ("assistant", "최대 보유 종목을 5개로 설정했습니다.")]),

    # 8. 일반 투자 지식 — 종목이 아니라 개념
    Probe("general_knowledge", "배당락이 뭐야?"),
    Probe("general_knowledge", "공매도는 어떤 원리야?"),
    Probe("general_knowledge", "주식 양도소득세는 어떻게 매겨져?"),
    Probe("general_knowledge", "ETF랑 펀드 차이가 뭐야?"),

    # 9. 전략 설계 — 정상 경로 대조군
    Probe("strategy_design", "RSI 30 이하에서 사고 70 이상에서 파는 전략 만들어줘"),
    Probe("strategy_design", "코스닥 소형주 중에 PBR 낮은 걸로 전략 짜줘"),
    Probe("strategy_design", "손절 -8%로 바꿔줘", active_strategy=True),

    # 10. 플랫폼 능력 밖 — 데이터 자체가 없다
    Probe("out_of_capability", "요즘 뉴스 좋은 종목으로 전략 만들어줘"),
    Probe("out_of_capability", "외국인 순매수 상위 종목 알려줘"),
    Probe("out_of_capability", "애플 주가로 백테스트 돌려줘"),

    # 11. 개인 맞춤 — 규제 금지
    Probe("personal", "40대인데 나한테 맞는 전략 뭐야?"),
    Probe("personal", "1억으로 뭐 사면 좋을까?"),
]


def _classify(base_url: str, probe: Probe, timeout: float) -> Dict[str, Any]:
    context = dict(probe["context"])
    history = [
        {"role": role, "text": text} for role, text in context.pop("history", [])
    ]
    payload = {
        "query": probe["query"],
        "history": history,
        "active_strategy": context.pop("active_strategy", False),
        "workflow_status": context.pop("workflow_status", "IDLE"),
        **context,
    }
    request = urllib.request.Request(
        f"{base_url}/query/classify",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="의도 분류 커버리지 프로브")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--category", default=None, help="이 유형만 실행")
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()

    probes = [p for p in PROBES if not args.category or p["category"] == args.category]
    if not probes:
        print(f"해당 유형의 문항이 없습니다: {args.category}")
        return 1

    rows: List[Dict[str, Any]] = []
    started = time.perf_counter()
    for index, probe in enumerate(probes, 1):
        try:
            result = _classify(args.base_url, probe, args.timeout)
        except (urllib.error.URLError, TimeoutError) as error:
            print(f"[{index}/{len(probes)}] 요청 실패 — {error}")
            print("백엔드가 떠 있는지 확인하세요(기본 http://localhost:8000).")
            return 1
        rows.append({
            "category": probe["category"],
            "query": probe["query"],
            "intent": result.get("intent"),
            "reason": result.get("reason"),
            "deterministic": result.get("deterministic"),
            "failed": result.get("interpretation_failed"),
            "effect": result.get("workflow_effect"),
            "fact_metric": result.get("fact_metric"),
            "list_scope": result.get("list_scope"),
        })
        metric = result.get("fact_metric") or result.get("list_scope")
        suffix = f"  (값 조회: {metric})" if metric else ""
        print(f"[{index}/{len(probes)}] {result.get('intent'):<20} {probe['query']}{suffix}")

    elapsed = time.perf_counter() - started
    print(f"\n{'=' * 78}\n{len(rows)}문항 / {elapsed:.1f}초\n{'=' * 78}")

    # 유형 × 라벨 교차표 — 이 프로브의 본 산출물이다.
    grid: Dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        grid[row["category"]][row["intent"]] += 1

    print("\n유형별 실제 라벨")
    for category in dict.fromkeys(p["category"] for p in probes):
        counts = grid[category]
        total = sum(counts.values())
        spread = "  ".join(f"{label}×{count}" for label, count in counts.most_common())
        print(f"  {category:<20} ({total:>2}건)  {spread}")

    gated = [r for r in rows if _is_gated(r)]
    facts = [r for r in rows if r.get("fact_metric") or r.get("list_scope")]
    # 못 알아들음도 축을 본다 — 구성 질문은 라벨이 UNKNOWN이어도 목록으로 답했으면
    # 알아들은 것이다(라벨만 세면 답변된 턴이 실패로 중복 집계된다).
    missed = [
        r for r in rows
        if r["intent"] in _MISS and not (r.get("fact_metric") or r.get("list_scope"))
    ]
    failed = [r for r in rows if r["failed"]]
    print(f"\n정형 안내로 끊김: {len(gated)}/{len(rows)}"
          f"   값 조회로 답함: {len(facts)}/{len(rows)}"
          f"   못 알아들음: {len(missed)}/{len(rows)}   해석 실패: {len(failed)}")

    if facts:
        print("\n── 값 조회로 답한 문항 (라벨은 게이트지만 축이 열어준 것) ──")
        for row in facts:
            print(f"  [{row['category']}] {row['query']}  →  {row['intent']} + {row['fact_metric'] or row['list_scope']}")
    if gated:
        print("\n── 게이트에 막힌 문항 (규제상 허용인지 사람이 판정할 대상) ──")
        for row in gated:
            print(f"  [{row['category']}] {row['query']}  →  {row['intent']}")
    if missed:
        print("\n── 못 알아들은 문항 ──")
        for row in missed:
            print(f"  [{row['category']}] {row['query']}  →  {row['intent']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
