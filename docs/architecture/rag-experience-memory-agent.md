# RAG + Experience Memory Strategy Advisor

> 상태: 설계안
> 선택 boundary: Governance / Policy Docs
> 목적: AI 전략 코치를 프롬프트 기반 조언자에서 백테스트 재사용, 유사 전략 검색, 조언 성패 학습을 수행하는 RAG + Experience Memory 기반 Agent로 확장한다.

---

## Codex 실행 Spec

Task:
RAG + Experience Memory 기반 전략 조언 Agent의 서비스 적용 설계를 정의한다.

Boundary:
Governance / Policy Docs

Files allowed:
- `docs/architecture/rag-experience-memory-agent.md`

Do not:
- 애플리케이션 코드, API 라우트, 백테스트 엔진, Prisma schema를 수정하지 않는다.
- 하나의 구현 작업에서 `AI / XAI Layer`, `Strategy Persistence / BatchRun Storage`, `Backtest Core`를 섞지 않는다.
- 백테스트 결과, RAG 검색 결과, Experience Memory가 없는 상태에서 성과를 단정하는 설계를 허용하지 않는다.

Requirements:
- strategy_id 생성, 백테스트 결과 재사용, 텍스트/구조 기반 유사 전략 검색, Experience Memory 저장 루프를 정의한다.
- DB 스키마 제안과 Python/FastAPI 모듈 구조를 구현 가능한 수준으로 제시한다.
- Agent 답변 생성 순서, 조언 성공/실패 평가 기준, 초기자금 기반 현실성 검증 로직을 명시한다.
- 실제 구현은 boundary별 단계로 분리한다.

Run:
- `git diff --check`

Deliver:
- RAG + Experience Memory Agent 설계 문서
- 단계별 구현 계획
- 남은 구현 boundary 목록

---

## 1. 목표 동작

이 Agent의 핵심 루프는 다음 순서를 깨지 않아야 한다.

```
현재 전략
  -> Strategy DSL canonicalization
  -> strategy_id 생성
  -> 백테스트 캐시 조회 또는 실행
  -> 텍스트 기반 유사 전략 검색
  -> DSL 구조 기반 유사 전략 검색
  -> Experience Memory 검색
  -> 개선안 생성
  -> 개선 전략 후보 생성
  -> 재백테스트
  -> 개선 전/후 비교
  -> Experience Memory 저장
  -> 사용자 답변
```

Agent는 백테스트 결과 없이 "수익성이 좋다"고 말하지 않는다. RAG 검색 결과가 부족하면 부족하다고 표시하고, 일반 퀀트 원칙 기반의 낮은 또는 중간 confidence 조언으로 제한한다.

---

## 2. 상위 아키텍처

```
Client / Strategy Lab
  -> Next.js API proxy
  -> FastAPI advisor route
      -> StrategyParserAdapter
      -> StrategyIdentityService
      -> BacktestResultRepository
      -> BacktestRunner
      -> SimilaritySearchService
          -> TextStrategyIndex
          -> StructuralStrategyIndex
      -> ExperienceMemoryRepository
      -> AdvicePlanner
      -> CandidateStrategyGenerator
      -> AdviceEvaluator
      -> ExperienceWriter
      -> ResponseComposer
```

기존 시스템과의 연결 지점:
- 자연어 파싱: `backend/engine/nl_parser.py`
- DSL 변환: `backend/engine/strategy_converter.py`
- 백테스트 실행: 기존 FastAPI backtest engine
- 기존 rule-based advisor: `backend/advisor/**`
- 기존 AI coach route: `backend/api/coach_routes.py`
- 기존 content-addressed strategy_id 원칙: `Strategy.id = SHA-256(canonical_strategy_dsl)`

---

## 3. Strategy ID 생성 방식

strategy_id는 백테스트 재사용과 Experience Memory 연결의 기준이다.

규칙:
- 입력은 Strategy DSL JSON이다.
- canonicalization은 stable key ordering을 사용한다.
- 의미 없는 metadata, UI-only 필드, trace id, timestamp, display label은 제외한다.
- 의미가 있는 배열 순서는 유지한다. 예: entry rule 순서, exit rule 순서, ranking rule 순서.
- 숫자는 정규화한다. 예: `30`, `30.0`이 의미상 동일한 필드라면 같은 문자열로 직렬화한다.
- null과 누락 필드의 의미가 같은 필드는 canonicalization 전에 기본값 정책을 통일한다.

예시 코드:

```python
import hashlib
import json
from decimal import Decimal
from typing import Any

VOLATILE_KEYS = {
    "id",
    "name",
    "description",
    "created_at",
    "updated_at",
    "trace_id",
    "ui_state",
}


def normalize_for_hash(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: normalize_for_hash(inner)
            for key, inner in sorted(value.items())
            if key not in VOLATILE_KEYS and inner is not None
        }
    if isinstance(value, list):
        return [normalize_for_hash(item) for item in value]
    if isinstance(value, float):
        return float(Decimal(str(value)).normalize())
    return value


def canonical_strategy_string(strategy_dsl: dict[str, Any]) -> str:
    normalized = normalize_for_hash(strategy_dsl)
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def strategy_id_for(strategy_dsl: dict[str, Any]) -> str:
    canonical = canonical_strategy_string(strategy_dsl)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

저장 규칙:
- `strategy_id`는 `Strategy.id`, backtest cache key, Experience Memory foreign key로 재사용한다.
- 동일 `strategy_id`가 이미 존재하고 동일 백테스트 조건이 저장되어 있으면 백테스트를 실행하지 않고 저장 결과를 반환한다.
- 백테스트 조건이 다르면 같은 Strategy DSL이라도 별도 `BacktestRun` 또는 `BacktestResult` row로 저장한다. 예: 기간, 초기자금, 수수료, 슬리피지, 유니버스 스냅샷이 다른 경우.

---

## 4. DB 스키마 제안

실제 Prisma schema 변경은 `Strategy Persistence / BatchRun Storage` boundary에서 별도 작업으로 수행한다.

### 4.1 Strategy

```prisma
model Strategy {
  id                       String   @id
  userPrompt               String
  strategySummary          String?
  strategyDsl              Json
  canonicalDsl             String
  canonicalVersion         Int      @default(1)
  dslTextSearch            String?
  indicatorNames           String?
  entryConditionText       String?
  exitConditionText        String?
  riskManagementText       String?
  universe                 String?
  timeframe                String?
  createdAt                DateTime @default(now())
  updatedAt                DateTime @updatedAt

  backtestRuns             BacktestRun[]
  adviceExperiences        AdviceExperience[]

  @@index([universe])
  @@index([timeframe])
}
```

### 4.2 BacktestRun

```prisma
model BacktestRun {
  id                       String   @id
  strategyId               String
  strategy                 Strategy @relation(fields: [strategyId], references: [id])
  market                   String
  universe                 String
  timeframe                String
  startDate                DateTime?
  endDate                  DateTime?
  initialCapital           Float
  commissionBps            Float
  slippageBps              Float
  liquidityPolicy          Json?
  universeSnapshotHash     String?
  resultMetrics            Json
  monthlyReturns           Json?
  rollingMetrics           Json?
  oosMetrics               Json?
  walkForwardResult        Json?
  tradeStats               Json?
  status                   String
  cacheKey                 String
  hitCount                 Int      @default(0)
  createdAt                DateTime @default(now())

  @@unique([cacheKey])
  @@index([strategyId])
}
```

`cacheKey`는 다음 값을 canonical hash한 값이다.

```json
{
  "strategy_id": "...",
  "market": "KOSPI",
  "universe": "KOSPI200",
  "timeframe": "1d",
  "start_date": "2021-01-01",
  "end_date": "2026-04-30",
  "initial_capital": 10000000,
  "commission_bps": 15,
  "slippage_bps": 5,
  "liquidity_policy": {},
  "universe_snapshot_hash": "..."
}
```

### 4.3 StrategyEmbedding

```prisma
model StrategyEmbedding {
  id                       String   @id
  strategyId               String
  strategy                 Strategy @relation(fields: [strategyId], references: [id])
  embeddingType            String
  sourceText               String
  vector                   Bytes?
  sparseTokens             Json?
  modelName                String
  createdAt                DateTime @default(now())

  @@index([strategyId])
  @@index([embeddingType])
}
```

SQLite 환경에서는 초기 버전에서 `sparseTokens` 기반 BM25/Jaccard 검색으로 시작하고, 운영 규모가 커지면 pgvector, sqlite-vss, Chroma, LanceDB 중 하나를 붙인다.

### 4.4 AdviceExperience

```prisma
model AdviceExperience {
  id                       String   @id
  strategyId               String
  strategy                 Strategy @relation(fields: [strategyId], references: [id])
  createdAt                DateTime @default(now())
  market                   String
  universe                 String
  initialCapital           Float
  timeframe                String
  userPrompt               String
  strategySummary          String?
  strategyDsl              Json
  canonicalDsl             String
  strategyHash             String
  similarStrategyIds       Json
  retrievedCases           Json
  agentAdvice              Json
  beforeBacktest           Json
  afterBacktest            Json?
  evaluation               Json
  lesson                   String
  confidence               String
  dataCoverage             Json?

  @@index([strategyId])
  @@index([market, universe])
  @@index([confidence])
}
```

Experience payload는 사용자 요구의 JSON 구조를 그대로 보존하되, 조회 성능이 필요한 필드는 top-level 컬럼으로 승격한다.

---

## 5. RAG 검색 방식

Agent는 모든 조언 전에 텍스트 기반 검색과 구조 기반 검색을 모두 실행한다.

### 5.1 텍스트 기반 유사도 검색

검색 대상:
- `user_prompt`
- `strategy_summary`
- `indicator_names`
- `entry_condition_description`
- `exit_condition_description`
- `risk_management_description`
- `agent_advice_text`

초기 구현:
- 한국어/영어 소문자 정규화
- 숫자와 단위 보존: `RSI 30`, `손절 5%`, `200일`
- indicator alias 정규화: `골든크로스`, `golden cross`, `ma crossover`
- BM25 또는 TF-IDF cosine
- top_k 20 검색 후 구조 검색 결과와 rerank

운영 확장:
- embedding model로 dense vector 검색 추가
- sparse score와 dense score를 weighted sum으로 결합

### 5.2 구조 기반 유사도 검색

검색 대상:
- `strategy_dsl`
- `indicators`
- `entry_rules`
- `exit_rules`
- `filters`
- `position_sizing`
- `stop_loss`
- `take_profit`
- `rebalance_rule`
- `universe`
- `timeframe`
- parameter values

구조 feature 예시:

```json
{
  "indicators": ["rsi", "sma"],
  "entry_rules": ["rsi<=30", "close>sma_200"],
  "exit_rules": ["rsi>=70"],
  "risk": ["stop_loss_pct=5"],
  "position_sizing": ["equal_weight", "max_positions=10"],
  "timeframe": "1d",
  "universe": "KOSPI200"
}
```

점수 산식:

```
structure_score =
  0.25 * indicator_jaccard
+ 0.25 * entry_rule_similarity
+ 0.15 * exit_rule_similarity
+ 0.10 * risk_rule_similarity
+ 0.10 * universe_timeframe_match
+ 0.10 * parameter_distance_score
+ 0.05 * position_sizing_match
```

parameter distance:
- threshold는 상대거리로 비교한다. 예: RSI 30 vs 35는 유사, RSI 30 vs 70은 반대 의미로 낮은 점수.
- stop loss 5% vs 6%는 유사, 5% vs 20%는 낮은 점수.
- 표현이 달라도 DSL 구조가 유사하면 높은 점수를 준다.

Rerank 규칙:
- text score가 높아도 structure score가 낮으면 최종 top case에서 제외할 수 있다.
- structure score가 높고 text score가 낮으면 "표현은 다르지만 구조가 유사함"으로 포함한다.
- 최종 top_k는 3-5개로 제한해 Agent context를 작게 유지한다.

---

## 6. Experience Memory 저장 형식

저장 payload:

```json
{
  "experience_id": "unique_id",
  "strategy_id": "hash_based_strategy_id",
  "created_at": "datetime",
  "market": "KOSPI | KOSDAQ | US | Crypto | Other",
  "universe": "selected_universe",
  "initial_capital": 10000000,
  "timeframe": "1d",
  "user_prompt": "original_user_strategy_prompt",
  "strategy_summary": "summary_of_strategy",
  "strategy_dsl": {},
  "strategy_dsl_canonical_string": "canonical_json_string",
  "strategy_hash": "sha256_hash",
  "similar_strategy_ids": [],
  "retrieved_cases": [
    {
      "case_strategy_id": "past_strategy_id",
      "similarity_reason": "why_this_case_is_similar",
      "before_metrics": {},
      "after_metrics": {},
      "lesson": "what_was_learned"
    }
  ],
  "agent_advice": {
    "advice_summary": "summary_of_advice",
    "recommended_changes": [],
    "risk_warnings": [],
    "assumptions": [],
    "confidence": "low | medium | high"
  },
  "before_backtest": {
    "cagr": null,
    "mdd": null,
    "sharpe": null,
    "sortino": null,
    "calmar": null,
    "profit_factor": null,
    "win_rate": null,
    "trade_count": null,
    "turnover": null,
    "avg_trade_return": null,
    "max_losing_streak": null
  },
  "after_backtest": {
    "cagr": null,
    "mdd": null,
    "sharpe": null,
    "sortino": null,
    "calmar": null,
    "profit_factor": null,
    "win_rate": null,
    "trade_count": null,
    "turnover": null,
    "avg_trade_return": null,
    "max_losing_streak": null
  },
  "evaluation": {
    "advice_success": true,
    "improved_metrics": [],
    "worsened_metrics": [],
    "net_effect": "positive | neutral | negative",
    "reason": "why_the_advice_worked_or_failed",
    "overfitting_risk": "low | medium | high",
    "oos_validation_required": true
  },
  "lesson": "final_reusable_lesson_for_future_agent_advice"
}
```

Experience를 저장할 때 `after_backtest`가 없으면 `evaluation.advice_success`를 확정하지 않는다. 이 경우 `net_effect = "unknown"` 대신 schema를 확장하거나 `neutral`과 `oos_validation_required = true`를 함께 저장한다.

---

## 7. 조언 성공/실패 평가 기준

단일 지표가 아니라 risk-adjusted score로 평가한다.

성공 후보 조건:
- CAGR 또는 total return이 개선된다.
- MDD가 감소하거나 악화 폭이 제한적이다.
- Sharpe, Sortino, Calmar 중 2개 이상이 개선된다.
- Profit Factor, 평균 손익비, 승률 중 하나 이상이 개선된다.
- 거래 횟수와 turnover가 비정상적으로 증가하지 않는다.
- 수수료와 슬리피지를 반영해도 개선이 유지된다.
- OOS 또는 Walk-forward 결과가 악화되지 않는다.
- 초기자금 대비 유동성 조건이 현실적이다.

실패 조건:
- CAGR은 개선되었지만 MDD가 크게 증가한다.
- Sharpe 또는 Sortino가 악화된다.
- 거래 횟수 증가로 비용 반영 후 수익성이 사라진다.
- 특정 기간 성과만 좋아지고 OOS 성능이 나빠진다.
- 개선 전략이 훨씬 복잡하지만 성능 개선이 미미하다.
- 초기자금 대비 체결 가능성이 낮은 유동성 조건을 추천한다.

평가 예시:

```python
def evaluate_advice(before: dict, after: dict, context: dict) -> dict:
    improved = []
    worsened = []

    if after["cagr"] > before["cagr"]:
        improved.append("cagr")
    else:
        worsened.append("cagr")

    if after["mdd"] > before["mdd"]:
        improved.append("mdd")
    else:
        worsened.append("mdd")

    if after["sharpe"] > before["sharpe"]:
        improved.append("sharpe")
    else:
        worsened.append("sharpe")

    trade_growth = (after["trade_count"] + 1) / (before["trade_count"] + 1)
    excessive_trades = trade_growth > 2.0 and after["turnover"] > before["turnover"]
    oos_bad = context.get("oos_available") and context.get("oos_delta", 0) < -0.05
    liquidity_bad = context.get("liquidity_check") == "fail"

    success = (
        "cagr" in improved
        and "sharpe" in improved
        and not excessive_trades
        and not oos_bad
        and not liquidity_bad
    )

    return {
        "advice_success": success,
        "improved_metrics": improved,
        "worsened_metrics": worsened,
        "net_effect": "positive" if success else "negative",
        "oos_validation_required": not context.get("oos_available", False),
    }
```

MDD는 음수로 저장되는 경우 `-0.20 > -0.30`이 개선이다. percent positive value로 저장하는 경로와 혼재하지 않도록 metric normalization layer가 필요하다.

---

## 8. 초기자금 기반 현실성 검증

Agent는 모든 조언 후보에 대해 다음 검증을 수행한다.

검증 질문:
- 초기자금 규모에 맞는가?
- 개인 투자자에게 현실적인가?
- 거래비용과 슬리피지를 고려했는가?
- 과최적화를 유발하지 않는가?
- 백테스트로 검증 가능한가?

초기자금 1천만 원 수준의 기본 원칙:
- 지나치게 낮은 유동성 종목은 피한다.
- 포지션별 예상 주문금액과 평균 거래대금의 비율을 확인한다.
- 최소 거래대금 조건은 시장, 종목 수, 포지션 크기에 따라 조정한다.
- 잦은 매매 전략은 수수료와 슬리피지 민감도 테스트를 필수로 한다.
- 한 종목 집중을 피하고 `max_positions` 또는 position cap을 둔다.

유동성 검증 예시:

```python
def check_liquidity(initial_capital: float, max_positions: int, avg_trading_value: float) -> dict:
    position_value = initial_capital / max(max_positions, 1)
    participation = position_value / max(avg_trading_value, 1)

    if participation <= 0.001:
        level = "pass"
    elif participation <= 0.005:
        level = "warn"
    else:
        level = "fail"

    return {
        "position_value": position_value,
        "avg_trading_value": avg_trading_value,
        "participation": participation,
        "level": level,
    }
```

Agent 문구 원칙:
- "일평균 거래대금 10억 이상만 거래하세요"처럼 고정 임계값을 기본값으로 단정하지 않는다.
- "초기자금, 포지션 수, 종목별 주문금액 기준으로 최소 거래대금 조건을 산정하세요"처럼 검증 가능한 기준으로 말한다.

---

## 9. Agent 답변 생성 방식

사용자 응답은 항상 다음 순서를 따른다.

```markdown
## 전략 요약
현재 전략을 간단히 설명합니다.

## 현재 전략의 문제점
백테스트 결과와 전략 구조를 기반으로 문제를 분석합니다.

## 과거 유사 전략 사례
RAG로 검색된 유사 전략 사례를 요약합니다.

## Experience Memory에서 발견한 패턴
과거 조언 성공/실패 사례에서 반복적으로 나타난 교훈을 정리합니다.

## 개선 제안
현재 전략에 적용할 수 있는 구체적인 개선안을 제시합니다.

## 재백테스트 조건
어떤 조건으로 다시 백테스트해야 하는지 제안합니다.

## 주의할 점
과최적화, 유동성, 거래비용, 슬리피지, 초기자금 문제를 경고합니다.

## 최종 추천
가장 먼저 적용할 개선안을 우선순위로 제시합니다.
```

답변 생성 guardrail:
- 백테스트 결과가 없으면 성과 단정 금지.
- 유사 전략 검색 결과가 부족하면 부족하다고 말한다.
- Experience Memory가 없으면 "저장된 경험 데이터 부족"이라고 표시한다.
- OOS 또는 Walk-forward가 없으면 확정 표현 대신 검증 필요라고 말한다.
- 복잡도 증가 대비 성능 개선이 불명확하면 보수적으로 평가한다.

---

## 10. Python/FastAPI 모듈 구조 제안

실제 구현은 `AI / XAI Layer`와 `Strategy Persistence / BatchRun Storage` boundary로 나누어 진행한다.

```
backend/advisor/
  memory_schemas.py
    - StrategyIdentity
    - SimilarStrategyCase
    - AdviceExperience
    - AdviceEvaluation

  strategy_identity.py
    - canonical_strategy_string()
    - strategy_id_for()
    - backtest_cache_key_for()

  memory_repository.py
    - get_strategy(strategy_id)
    - get_backtest_by_cache_key(cache_key)
    - save_strategy(...)
    - save_backtest_run(...)
    - save_experience(...)

  similarity.py
    - build_text_document(strategy, advice)
    - extract_structural_features(strategy_dsl)
    - text_similarity_search(...)
    - structural_similarity_search(...)
    - rerank_similar_cases(...)

  memory_retriever.py
    - retrieve_context(user_prompt, strategy_dsl, strategy_id)

  advice_planner.py
    - diagnose_current_strategy(...)
    - build_recommended_changes(...)
    - generate_candidate_strategy(...)

  advice_evaluator.py
    - normalize_metrics(...)
    - compare_before_after(...)
    - evaluate_success(...)
    - build_reusable_lesson(...)

  reality_checks.py
    - check_initial_capital_fit(...)
    - check_liquidity_fit(...)
    - check_cost_sensitivity(...)

backend/api/
  coach_routes.py
    - POST /strategy/coach/rag
    - POST /strategy/coach/rag/stream
```

라우트 orchestration:

```python
@router.post("/strategy/coach/rag")
async def coach_strategy_with_memory(req: RagCoachRequest) -> RagCoachResponse:
    strategy_dsl = await parser.parse(req.user_prompt)
    strategy_id = identity.strategy_id_for(strategy_dsl)
    cache_key = identity.backtest_cache_key_for(strategy_id, req.backtest_config)

    before = repository.get_backtest_by_cache_key(cache_key)
    if before is None:
        before = await backtest_runner.run_and_store(strategy_id, strategy_dsl, req.backtest_config)

    rag_context = retriever.retrieve_context(req.user_prompt, strategy_dsl, strategy_id)
    advice = planner.build_advice(req, strategy_dsl, before, rag_context)
    candidate = planner.generate_candidate_strategy(strategy_dsl, advice)

    after = None
    evaluation = {"oos_validation_required": True}
    if candidate is not None:
        after = await backtest_runner.run_and_store_candidate(candidate, req.backtest_config)
        evaluation = evaluator.compare_before_after(before.metrics, after.metrics, req.backtest_config)

    experience = experience_writer.save(req, strategy_id, strategy_dsl, before, after, rag_context, advice, evaluation)
    return response_composer.compose(req, strategy_dsl, before, after, rag_context, advice, evaluation, experience)
```

---

## 11. 백테스트 결과 재사용 방식

재사용 조건:
- `strategy_id`가 동일하다.
- 백테스트 기간, timeframe, 시장, universe snapshot, 초기자금, 수수료, 슬리피지, 유동성 정책이 동일하다.
- 백테스트 엔진 버전 또는 metric calculation version이 동일하다.

재사용 불가 조건:
- DSL은 같지만 기간이 다르다.
- 수수료 또는 슬리피지가 다르다.
- universe 구성 종목 snapshot이 다르다.
- 엔진 버전이 바뀌어 결과 재현성이 깨질 수 있다.

저장 결과 반환 시:
- `cache_hit = true`
- `hitCount += 1`
- Experience Memory에는 "before_backtest reused from cache" metadata를 남긴다.

---

## 12. 구현 계획

### Phase 1: Persistence foundation

Boundary: Strategy Persistence / BatchRun Storage

작업:
- Prisma schema에 `BacktestRun`, `AdviceExperience`, `StrategyEmbedding` 추가 또는 기존 모델 확장.
- `strategy_id`와 `backtest_cache_key` helper를 단일 구현으로 정리.
- 동일 strategy/cache hit 시 백테스트 재사용 회귀 테스트 추가.

검증:
- `npm run test:frontend`
- persistence route 테스트

### Phase 2: Advisor memory retrieval

Boundary: AI / XAI Layer

작업:
- `backend/advisor/strategy_identity.py`, `similarity.py`, `memory_retriever.py` 추가.
- 텍스트 BM25/Jaccard와 DSL 구조 feature 기반 검색 구현.
- 기존 `ExperimentLearningProvider`는 fallback evidence source로 유지한다.

검증:
- `pytest backend/tests`
- 구조 유사도 테스트: 표현이 달라도 DSL이 같으면 높은 점수.
- 텍스트 유사도 테스트: 비슷한 문장이나 지표명이 검색되는지 확인.

### Phase 3: Advice loop orchestration

Boundary: AI / XAI Layer

작업:
- `/strategy/coach/rag` 또는 기존 coach route 내부 opt-in flag 추가.
- 현재 전략 백테스트 결과, 유사 사례, Experience Memory를 모두 prompt/context에 포함.
- Agent 답변 형식을 8개 섹션으로 고정.
- RAG 결과 부족 시 confidence와 제한 문구를 강제.

검증:
- `pytest backend/tests`
- coach route contract 테스트

### Phase 4: Candidate generation and evaluation

Boundary: AI / XAI Layer 또는 Optimization Runtime 중 하나로 분리

작업:
- 조언을 DSL-level proposed change로 변환.
- 개선 후보 백테스트 실행.
- before/after metric comparison과 advice_success 평가.
- Experience Memory 저장.

검증:
- `pytest backend/tests`
- 개선 전/후 비교 기준 테스트
- 과도한 거래 횟수 증가, 비용 반영 후 악화, OOS 악화 케이스 테스트

### Phase 5: UI integration

Boundary: Strategy UI

작업:
- Strategy Lab에 RAG 검색 사례, Experience Memory 패턴, 개선 전/후 결과를 표시.
- cache hit 여부와 재백테스트 조건을 노출.

검증:
- `npm run test:frontend`

---

## 13. Acceptance Criteria

설계 수용 기준:
- Agent가 strategy_id 생성과 백테스트 재사용 기준을 명확히 갖는다.
- Agent가 텍스트 기반과 구조 기반 유사 전략 검색을 모두 수행하도록 설계되어 있다.
- Agent가 Experience Memory를 저장하고 다음 조언에서 재사용할 수 있다.
- 답변 형식이 전략 요약, 문제점, 유사 사례, 메모리 패턴, 개선안, 재백테스트 조건, 주의점, 최종 추천 순서를 따른다.
- 조언 성공/실패 판단이 CAGR 단일 기준이 아니라 risk, cost, liquidity, OOS/WFA를 포함한다.
- 초기자금 기반 유동성/체결 현실성 검증이 포함된다.
- 실제 구현이 boundary별로 쪼개져 있어 Codex 규칙을 위반하지 않는다.

---

## 14. 남은 결정 사항

- SQLite에서 dense vector 검색을 붙일지, 초기 버전은 sparse 검색만 사용할지 결정해야 한다.
- `after_backtest`를 항상 즉시 수행할지, 비용이 큰 경우 background job으로 분리할지 결정해야 한다.
- `Strategy DSL` canonicalization versioning 정책을 확정해야 한다.
- OOS/WFA가 없는 전략에 대해 `advice_success`를 provisional로 둘지 별도 enum을 둘지 schema에서 결정해야 한다.
- 백테스트 엔진 version과 데이터 snapshot hash를 어디서 계산하고 저장할지 정해야 한다.
