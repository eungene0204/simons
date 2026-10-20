# 전략 온톨로지 그래프 (읽기 전용) — 계약·boundary·작업 명세

> **상태 (2026-10-15): X-1~X-7 구현 완료, 문서는 구현 결과(§10)에 맞춰 갱신됨.** 설계 근거(§1~§9)는
> 구현 전에 코드와 대조해 쓴 것이며, 구현 중 확인된 정정 사항은 §10에 따로 적었다. 이 문서의 코드 경로·타입·
> 호출 관계는 2026-10-15 현재 코드와 대조했다.

## 1. 목적과 범위

사용자가 "서비스가 내 전략을 어떻게 이해했는지"를 구조로 확인한다. 표시 대상은 투자 대상·종목 선정 필터·순위
선정·매수 규칙·매도 규칙·자금 배분·리밸런싱·위험 관리 중 **스냅샷에 실제 존재하는 항목**이다. 존재하지만 값이
정해지지 않은 항목은 숨기지 않고 "미정"으로 보인다.

핵심 흐름: **"이 전략으로 확정" 성공 → 같은 응답의 확정 스냅샷으로 대화 안에 "확정된 전략" 그래프 카드를 자동 표시**
(별도 열기 버튼 없음). 보조 진입점은 확정 카드의 "전략 그래프" 다시 열기, 백테스트 결과 화면, 저장된 결과 상세.

제외: 백테스트 이력 그래프, 성과 비교, 추천·전망, 자동 개선, 그래프 편집으로 전략 변경, 그래프 DB.
planner State DAG(`planner_dag_contract.md`)와 이 그래프는 다른 개념이며 실행 단계·대화 순서를 섞지 않는다.
생성·조회·확장 어디에서도 **LLM·검색·자연어 재해석을 호출하지 않는다.** 미국(US) 전용 검사는 사용자 지시로 제외한다.

## 2. 실제 코드 추적 결과 (문서 설명이 아닌 현재 코드 기준)

### 2.1 "이 전략으로 확정" 경로

1. 칩 문구는 `app/analytics/new/page.tsx`의 `CONFIRM_STRATEGY_CHIP`("이 전략으로 확정"). 칩은 되묻기 카드가 아니라
   **`strategyConfirmation: true`인 어시스턴트 메시지의 선택지**이며, `handleSuggestionClick`이
   `latestAssistant?.strategyConfirmation && text === CONFIRM_STRATEGY_CHIP`일 때만 `confirmDeterministicStrategy`로 보낸다
   (문구 비교 단독이 아니라 메시지 플래그와 함께 판정 — 이 구조를 유지한다).
2. `confirmDeterministicStrategy`는 누적된 `latestParsedRef.current`를 `POST /api/strategy/compile`
   (→ 백엔드 `/strategy/compile`, `backend/api/intent_routes.py::strategy_compile`)에 보낸다. LLM 재파싱 없음.
   응답 계약: `{parsed: ParsedStrategy.model_dump(), backtest_request: to_backtest_request(parsed), notices: string[]}`.
   `enforce_strategy_minimums`가 보정한 **정규화 후** parsed가 돌아오므로 클릭 시점 초안과 다를 수 있다.
3. 응답은 `applyBuilderConfirmedStrategy(data)`가 받는다. 여기서 `getNextMissingBacktestCondition`이 남은 조건을 찾으면
   **확정되지 않고** 되묻기 카드(`clarification`)가 된다. 남은 조건이 없을 때만 `updateLastAssistant({parsed,
   confirmedSummaryItems, notices})`를 실행한다 → **이 성공 가지가 "확정 성공"의 유일한 지점**이다.
4. 같은 함수가 특화 빌더의 `status === "confirmed"` 응답(`handleSendTurn`의 빌더 턴과 시드 적용 경로 `requestBuilderStep`; `parsed`+`backtest_request`를 직접 수신)에서도
   불린다. 두 경로 모두 확정 카드(`confirmedSummaryItems`)를 만들므로 그래프도 같은 지점에 한 번만 연결한다.
5. 실패 시 `updateLastAssistant({error})`. 오류·추가 질문 경로에는 확정 스냅샷이 없다.

### 2.2 타입 구분 (하나로 취급하지 않는다)

| 대상 | 실제 위치 | 성격 |
|---|---|---|
| StrategySpec | `backend/strategy_conversation/interpreter/models.py`, `compiler/strategy_decompiler.py` | 인터프리터 초안. 값 출처·미정 상태를 가진다. 프론트로 나가지 않는다 |
| ParsedStrategy | `backend/engine/nl_parser.py` → 프론트 `ParsedSummary`(`lib/strategy-summary.ts`) | 검증·컴파일 결과(정규화 후). 미정(예: `cash_pool.reserve_stated`, 불완전 `macro_filters`)이 보존된다. **조건별 원문 인용(`source_text`)은 없다** |
| BacktestRequest(실행 DSL) | `engine/strategy_converter.py::to_backtest_request` | 엔진이 실제 읽는 값. 미정 설정은 **싣지 않는다**(예: 값 대기 국면 필터). `entry.logic`·`exit`·`risk` 포함 |
| 저장 결과의 실행 요청 | `BacktestHistory.result.executedRequest` (`lib/server/backtestCache.ts::pickExecutedRequest`, 키: symbols·universe_id·backtest_mode·target_stocks·sector·etf_theme·listing_*·entry·exit·risk·period·startDate·endDate·options) | **엔진 요청만** — parsed·미정·인용 없음. `/api/backtest/history/[id]`가 `result`에 그대로 싣는다 |
| Strategy 행 settings | `/api/backtest/history/[id]`의 `settings` (원천 Strategy 조회, id 우선·이름 폴백) | **현재 전략** — 실행 당시 값이 아닐 수 있다 |
| 표시용 summaryItems | `app/analytics/new/builderProgressPresentation.ts` 등 | 표시 문자열. **역파싱 금지** |

### 2.3 결과 화면 생명주기

- `app/analytics/new/page.tsx`: `executedReq`는 결과 이벤트(`event.type === "result"`)에서 `setExecutedReq(effectiveReq)`로만 채워진다.
  그러나 `BacktestDashboard`에는 `strategySummary={buildStrategySummaryFromRequest(executedReq ?? backtestReq)}`,
  `backtestDsl={backtestReq}`, `parsedStrategy={latestParsed}`가 전달된다 — **`backtestReq`·`latestParsed`는 편집으로 바뀌는
  현재 상태**이므로 그래프 입력으로 쓰지 않는다. 그래프에는 `executedReq`만 쓰고, 없으면 "스냅샷 없음".
- `app/backtest/[id]/page.tsx`: 요약은 `result.executedRequest ?? item.settings`(실행 우선), 재실행 DSL은 `item.settings ?? result.executedRequest`
  (**settings 우선**). 그래프는 `result.executedRequest`만 사용한다. `item.settings` fallback을 재사용하지 않는다.
  `executedRequest`가 없으면 "이 실행의 전략 스냅샷이 저장되어 있지 않습니다"를 보이고 현재 전략으로 대체하지 않는다.

### 2.4 실행 의미 (코드로 확인, 실행 코드는 수정하지 않는다)

| 항목 | 확인 결과 (파일) |
|---|---|
| 진입 결합 | `to_backtest_request`는 `entry: {conditions, logic: strategy.entry_logic}`을 항상 명시(AND/OR) |
| `entry_logic` 적용 범위 | `SignalEngine.generate_signals`가 조건을 `type == "filter"`와 그 외로 나눈다. **logic은 filter가 아닌 신호 조건에만** 적용, filter는 **항상 AND**로 별도 결합 후 `signals & filters`. 재무 필터(`fundamental_filters`)와 `entry_filters`는 `type: "filter"` |
| 청산 결합 | `to_backtest_request`는 `exit: {conditions}`만 싣고 `logic`이 없다 → `generate_signals` 기본값 **OR**. **진입 logic을 청산에 적용하지 않는다.** 청산 조건 간 결합은 "하나라도 성립 시(엔진 기본 OR)"로 표시하되, 스냅샷의 `exit.logic`이 명시돼 있으면 그 값을 쓴다 |
| 중첩 조건 | 현재 스키마는 **평면 조건 목록 + 단일 logic**뿐이다. 재귀 그룹 스키마는 없으며 만들지 않는다 |
| 크로스 vs 비교 | MA: `mode`가 `above/below`면 지속 상태(추세), 없으면 크로스오버. RSI: `mode: rebound`면 임계선 재돌파, 없으면 단순 비교. 연산자는 `operator`로 구분 |
| 손절·익절 | 시뮬레이터: 기준가 = **매수가(`entry_price`)**, 손절은 장중 저가, 익절은 장중 고가로 판정 |
| 트레일링 | 기준 = 보유 중 **장중 고가의 최고점**, 장중 저가 낙폭이 `trailing_stop_pct` 이상이면 청산. `trailing_stop_activation_pct`가 있으면 고점이 매수가 대비 그 % 이상일 때만 작동 |
| 최대 보유 | `(i - entry_day) >= max_holding_days` — 인덱스가 거래일 배열이므로 **거래일** 기준. 리밸런싱 주기가 있으면 컨버터가 `max_holding_days`를 null로 끈다 |
| 위험 청산 우선순위 | 최대 보유(최우선) → 손절 → 익절 → 트레일링 순으로 이미 청산 표시된 종목은 건너뛴다. **OR 묶음으로 평탄화하지 않고** 우선순위를 상세에 표시 |
| 포지션 크기 | `position_size_pct = 100 / max_positions`(최대 비중 상한 `max_position_weight_pct` 적용). 시뮬레이터가 `size_per_pos = pos_size_pct/100`을 쓰며 코드 주석이 "진입 시점 포트폴리오 NAV 대비 비중"이라 밝힌다 → **총자산(평가액) 기준**으로 표시한다(`simulator.py` 646행 부근). 동일 비중·변동성 역비중 방식은 `1/max_positions`가 기준 비중이다 |
| 랭킹 | `risk.ranking_*`: `ranking_metric`, `ranking_lookback_days`, `ranking_skip_days`, `ranking_direction`, `ranking_components[*].(metric,direction,lookback_days,skip_days,weight,group)` 등 스키마에 있는 필드만 |
| 지원 기능 | 분할 매수(`entry_tranches`)·분할 익절(`partial_take_profits`)·조건부 납입(`contribution_rules`)·현금 풀(`cash_pool`)·시장 국면(`market_regime`)·매크로(`macro_filters`)·목표 변동성·계절 필터는 스냅샷에 설정돼 있을 때만 노드로 만든다 |

## 3. 정본 데이터와 스냅샷 출처표

| 용도 | 정본 | 그래프의 사용 방식 |
|---|---|---|
| 지표 잎(이름·단위·연산자·파라미터 정의·지원 상태·엔진 연결) | `registry/indicator_registry.py` `REGISTRY`/`IndicatorSpec` | 공개 메타데이터 응답으로 전달 |
| 분류·소속·합성 개념 | `registry/concept_ontology.py`(`get_ontology`) + `data/indicator-ontology.json` | 동일 |
| 영어 표시명 | `registry/display_labels.py` (`_EN_LABELS`) | 공개 메타데이터가 id별 `name`·`name_en`으로 전달 |
| 한국어 표시 문구(요약) | `lib/strategy-summary.ts`, `i18n/en.ts`의 `t()` | UI 문구만 `t()` — 지표 이름·단위 사전을 프론트에 **복제하지 않는다** |
| 사용자 전략 구조 | 확정 응답 `{parsed, backtest_request, notices}` / 실행 `executedReq` / 저장 `result.executedRequest` | 아래 입력 래퍼 |

| 진입점 | 입력 origin | 입력 schema | sourceRef | 보존되는 상태 |
|---|---|---|---|---|
| 확정 카드(자동·다시 열기) | `confirmed` | `parsed+request` | 메시지 id + 확정 건 일련번호 | 정규화 후 parsed의 미정 + notices(별도 안내 채널 같은 턴) + 요청 DSL |
| 결과 화면(현재 세션) | `executed` | `request` | 결과 `cacheKey` / 실행 시점 사본 | 요청 DSL만. 확정 스냅샷으로 **대체하지 않는다** |
| 저장된 결과 상세 | `executed` | `request` | 기록 id + `result.executedRequest` | 요청 DSL만. 없으면 `none` |
| 아직 확정 전 | `draft` | `parsed` | 메시지 id | 그래프 자동 표시 대상 아님 |
| 데이터 없음 | `none` | — | — | "스냅샷 없음" 상태 |

원문 인용: ParsedStrategy·BacktestRequest 어디에도 조건별 원문 인용이 없다. 따라서 **인용은 표시하지 않고** 상세
패널에 "저장된 원문 인용 없음"으로만 구분한다(생성·추정 금지). 별도 안내 채널(`notices`)은 같은 턴 스냅샷에 실린 문장만 연결한다.

### 입력 래퍼 (신규, 기존 공개 계약 불변)

```ts
type StrategyGraphInput = {
  origin: "draft" | "confirmed" | "executed" | "none";
  schema: "parsed+request" | "parsed" | "request" | "none";
  sourceRef: string;             // 안정 문자열 (예: "confirmed:<messageId>#<n>", "history:<id>")
  parsed?: ParsedSummary;        // origin이 draft·confirmed일 때만
  request?: BacktestRequestLike; // 엔진 요청(executed·confirmed)
  notices?: string[];            // 같은 턴에 보존된 안내만
};
```

변환은 **request를 실행 의미의 정본**으로(결합 방식·위험·랭킹·조건 파라미터), parsed를 **미정·부가 정보의 정본**으로 쓴다.
둘이 충돌하면 어느 쪽 값을 표시했는지 `details.valueSource`에 남긴다. 어느 쪽에도 없는 의미는 "확인 필요"로 표시한다.

## 4. 공개 메타데이터 계약

`GET /api/strategy/graph-meta` (Next 프록시) → 백엔드 `GET /strategy/graph-meta`. 응답은 레지스트리·온톨로지에서
결정론적으로 추출하고, 관리자 `/ontology/graph`(issues·description 전문 포함)와 분리한다.

```ts
type GraphMeta = {
  version: string;               // 응답 내용 해시 (렌더 간 안정)
  indicators: Record<string, {   // canonical id → 공개 필드만
    name: string; nameEn: string; category: string;
    supported: "SUPPORTED" | "PARTIALLY_SUPPORTED" | "UNSUPPORTED";
    dataPending: boolean; partialData: boolean;
    unit: string | null;          // IndicatorSpec.value_type (percent/ratio/억원/point/event)
    operators: string[];
    parameters: Record<string, { minimum: number|null; maximum: number|null; required: boolean }>;
    classId: string | null;
    alternatives: string[];
  }>;
  /** "kind:field" engine binding -> canonical indicator id (how an engine condition finds its leaf). */
  bindings: Record<string, string>;
  classes: Array<{ id: string; name: string; parent: string | null; description: string }>;
  concepts: Array<{ id: string; name: string; supported: string; expandsTo: string | null; requires: string[] }>;
};
```

- 한 엔진 조건을 여러 잎이 공유하면(볼린저 밴드 지정 변형 8개가 `technical_signal:bollinger_bands`를 공유) `bindings`는 잎 ID 꼬리가 필드와 같은 일반 잎(`technical.bollinger_bands`)을 대표로 둔다 — 변형 구분은 조건 파라미터(`band`·`cross`)가 하며 색인이 고르지 않는다.
- `ParamSpec.default`·`recommended_value`는 **포함하지 않는다** — 미정인 사용자 값을 채우는 데 쓰이지 않게 한다.
- 제외: `issues`, `notes`(내부 메모), `synonyms`, 사용자 전략·조건·원문·다른 사용자 데이터.
- 인증: 응답에 사용자 데이터가 없으므로 `/api/strategy/compile`과 같은 수준(세션 불필요)으로 두고 인증 로직은 건드리지 않는다.
  전략·백테스트 소유권 검사(`/api/backtest/history/[id]`)는 변경하지 않는다.
- `/api/admin/ontology/graph`는 사용자 화면에서 호출하지 않는다. 테스트로 호출 0을 고정한다.
- LLM·검색 호출 없음. 단위 테스트가 모듈 import 그래프에 LLM 클라이언트가 없음을 확인한다.

## 5. 순수 그래프 변환 모델

`lib/strategy-graph/` (React·fetch 의존 없음). 입력 `(StrategyGraphInput, GraphMeta | null)` → 출력:

```ts
type GraphNode = { id; kind; label; status; sourceRef; details };
type GraphEdge = { id; source; target; kind; label };
type StrategyGraph = { origin; schema; sourceRef; nodes; edges; notes: string[]; metaState: "ok" | "unavailable" };
```

- 노드 kind: `strategy`, `section`(투자 대상·종목 선정 필터·순위 선정·매수 규칙·매도 규칙·자금 배분·리밸런싱·위험 관리),
  `group`(AND/OR/결합 방식 확인 필요), `condition`, `risk`, `setting`, `indicator`(지표 개념), `class`(분류).
- 엣지 kind: 전략 인스턴스 관계(`has_section`, `contains`, `combined_by`, `uses_indicator`) /
  온톨로지 개념 관계(`is_a`, `expands_to`). 둘은 `kind`와 선 스타일로 구분한다.
- status: `ok` / `pending`(값 필요한데 없음) / `not_applicable`(교차처럼 기준값 불필요) / `unsupported` / `partial` / `data_pending` /
  `check_needed`(결합·기준 확인 필요). **0·false는 유효 값**, null=미정 단정 금지.
- ID는 결정론적: 스냅샷 안의 섹션 경로(`entry/cond/2`)에서 만든다. 이 경로는 해당 스냅샷 안의 참조일 뿐 버전 간 영구 조건 ID가 아니다.
  난수·현재 시각·원본 변경 없음(입력은 `structuredClone` 없이 읽기만, 테스트에서 deep-freeze로 불변 확인).
- 같은 지표를 매수·매도에서 쓰면 조건 노드는 각각 두고 `indicator` 노드를 공유한다. 기간·역할·위치가 다르면 합치지 않는다.
- 분류 계층은 기본 접힘. 접어도 조건 인스턴스는 숨기지 않는다(접힘은 `class` 노드와 그 엣지의 가시성만 바꾼다).
- 메타데이터가 없으면 `metaState: "unavailable"`로 구조 그래프만 만들고 이름은 canonical id 대신 "지표 이름 확인 불가"로 구분한다
  (그래프 생성 실패와 메타데이터 실패를 구분).

## 6. UI 설계

- 렌더링: **자체 SVG + 결정론적 계층 배치**(신규 의존성 없음). 근거: (a) 관리자 `IndicatorOntologyView`는 Canvas+물리 레이아웃으로
  관리자 데이터 조회와 결합돼 있고 키보드·DOM 접근이 불가, (b) `@visx` 계열은 선언돼 있으나 노드 그래프 컴포넌트가 아니며 필요 기능
  (확대·맞춤·선택)이 SVG 수십 줄이면 충분, (c) DOM 노드라 키보드 포커스·테스트가 쉽다. 대안(react-flow 등)은 의존성·번들 증가로 기각.
  *새 의존성이 필요해지면 구현 전에 이 문서와 boundary를 먼저 갱신한다.*
- 기능: 확대·축소·화면에 맞추기, 노드 선택(방향키·Enter), 직접 관계 강조, 상세 패널, 관련 개념 펼치기·접기, 범례,
  그래프/텍스트 전환, 크게 보기(모달: 포커스 진입·복귀·Escape), 빈/미정/오류/스냅샷 없음 상태.
- 디자인: `docs/UI_GUIDELINES.md` 토큰, 종류별 장식색 없음(도형·아이콘·라벨·중립 배지), `t()` + `lib/i18n/en.ts`.
- 모바일: 그래프 아래에 상세. hover 시 일반 면책 문구 반복 금지(AGENTS.md hover 원칙).
- 확정 카드: 제목 "확정된 전략", 확정 건마다 독립 카드(스냅샷 불변), 같은 확정 건 중복 생성 방지(건 일련번호 키),
  그래프 오류 시 카드 안에 오류+재시도(동일 스냅샷으로 변환·메타 조회만 재실행, 확정·LLM 재호출 없음).
- "확정된 전략"과 "백테스트에 실행된 전략"은 라벨로 구분한다(실행 전에는 "실행 스냅샷"이라 쓰지 않는다).
- 규제 안전: 분류·상태로 성과·시장 적합성을 말하지 않는다. 문구 점검 대상.

## 7. Boundary 판단

기존 boundary로는 수용할 수 없다.

- 백엔드 공개 메타데이터: Boundary W의 `intent_routes.py`는 "existing LLM builder wiring only"라 신규 경로를 허용하지 않고,
  `registry/**`는 W에서 특정 항목만 허용된다. Boundary K·D도 해당 없음.
- 공용 순수 변환 `lib/strategy-graph/**`: Boundary B의 `lib/strategy/**`는 백테스트 요청 변환용으로 목적이 다르다.
- UI 진입점 3곳이 A(`app/analytics/**`, `components/strategy/**`)·E(`app/backtest/**`)에 걸치고, `app/api/strategy/**`는 I·P 소유다.

따라서 이 기능 전용 **Boundary X: Strategy Ontology Graph**(`docs/architecture/boundaries.md`)를 추가한다.
Boundary X는 확인된 수정 파일과 새 파일을 열거하며, 해석·검증·컴파일·실행·인증·DB 스키마 변경은 허용하지 않는다.
한 작업은 Boundary X 안에서 3~5개 파일로 나눈다(아래 7개 구현 작업).

## 8. 작업 명세 (각 작업 = Boundary X, 별도 작업으로 진행)

모든 작업의 공통 Do not: 전략 해석·검증·컴파일·실행·인증·소유권·DB 스키마 변경, 실행 스키마 확장, 원문 정규식 판정,
LLM 호출 추가, 관리자 엔드포인트 호출, 지표 사전 복제. 공통 Deliver: 작은 diff·변경 파일 요약·실행한 검증 명령과 결과.

### X-1 공개 메타데이터 백엔드
- Files: `backend/strategy_conversation/registry/public_metadata.py`(신규), `backend/api/strategy_graph_meta_routes.py`(신규),
  `backend/main.py`(라우터 등록 한 줄), `backend/tests/test_strategy_graph_meta.py`(신규)
- Requirements: §4 DTO를 REGISTRY·온톨로지에서 결정론 추출, default/recommended 제외, 사용자 데이터·issues 미포함, LLM import 없음, 해시 안정.
- Run: `cd backend && uv run --frozen pytest tests/test_strategy_graph_meta.py -v` + 백엔드 전체 스위트(CLAUDE.md 명령).

### X-2 Next 프록시 + 클라이언트 메타 조회
- Files: `app/api/strategy/graph-meta/route.ts`, `app/api/strategy/graph-meta/route.test.ts`, `lib/strategy-graph/meta.ts`, `lib/strategy-graph/meta.test.ts`
- Requirements: `fetchBackend` 프록시(경로 고정, `backendPathSegment` 불필요), 실패 시 502 + 구분 가능한 오류, 클라이언트 캐시·재시도 가능, 관리자 경로 미호출 테스트.
- Run: `npx vitest run app/api/strategy/graph-meta lib/strategy-graph/meta.test.ts`, `npm run test:frontend`.

### X-3 입력 래퍼와 스냅샷 선택 규칙
- Files: `lib/strategy-graph/types.ts`, `lib/strategy-graph/snapshot.ts`, `lib/strategy-graph/snapshot.test.ts`
- Requirements: §3 입력 래퍼, `fromConfirmed`/`fromExecuted`/`fromSavedHistory` 순수 함수(저장 기록은 `result.executedRequest`만, settings 미사용),
  none 상태, sourceRef 규칙.
- Run: 해당 vitest + `npm run test:frontend`.

### X-4 순수 변환 ① 구조 인스턴스
- Files: `lib/strategy-graph/transform.ts`, `lib/strategy-graph/transformSections.ts`, `lib/strategy-graph/transform.test.ts`, `lib/strategy-graph/fixtures.ts`
- Requirements: §2.4·§5. 투자 대상·필터·랭킹·매수/매도(결합 방식)·자금 배분·리밸런싱·위험(우선순위). 회귀 1·2·5·6·7·8·10·11 (스냅샷 A/B 포함).
- Run: 해당 vitest + `npm run test:frontend`.

### X-5 순수 변환 ② 개념 연결과 텍스트 구조
- Files: `lib/strategy-graph/concepts.ts`, `lib/strategy-graph/textOutline.ts`, `lib/strategy-graph/concepts.test.ts`, `lib/strategy-graph/textOutline.test.ts`
- Requirements: 지표 개념 공유·분류 접힘(조건 인스턴스 보존), 메타 없음 상태, 텍스트 보기가 같은 모델 소비, 회귀 3·4·9·12.
- Run: 해당 vitest + `npm run test:frontend`.

### X-6 그래프 UI 컴포넌트
- Files: `components/strategy/graph/StrategyGraphView.tsx`(SVG·줌·선택·강조), `components/strategy/graph/StrategyGraphDetail.tsx`,
  `components/strategy/graph/StrategyGraphCard.tsx`(카드·텍스트 전환·크게 보기·오류/재시도), `lib/i18n/en.ts`(신규 문구), `components/strategy/graph/StrategyGraphCard.test.tsx`
- Requirements: §6 전부. 키보드·모달 포커스·모바일 순서.
- Run: 해당 vitest + `npm run test:frontend` + `npm run lint` + 실제 브라우저 데스크톱·모바일 확인.

### X-7 진입점 연결
- Files: `app/analytics/new/page.tsx`(확정 성공 가지에 스냅샷 보존·카드 렌더, 실행 시점 사본), `components/strategy/backtest/BacktestDashboard.tsx`(전략 설명 영역 진입점),
  `app/backtest/[id]/page.tsx`(저장 결과 스냅샷 전달), `app/analytics/new/page.confirm.test.tsx`(확정 자동 표시·중복·실패 사례)
- Requirements: 추가 검증 1~9, 기존 확정·백테스트 흐름 불변, `latestParsed`·`backtestReq` 직접 참조 금지. 변경이 5파일을 넘으면 연결 대상별로 분리.
- Run: `npm run test:frontend`, `npm run lint`, 브라우저 확인.

### X-8 Governance 마무리 (Boundary G)
- Files: `docs/development/strategy-ontology-graph.md`, `docs/architecture/boundaries.md`, `docs/development/codex-rules.md`(boundary 목록에 X 추가), `docs/software_architecture.md`, `docs/SRS.md`, `docs/PROJECT_PLAN.md`(5개 중 해당분)
- Requirements: 실제 구현 상태만 "완료"로 갱신, 제한 사항 기록. Run: `git diff --check`.

## 9. 제한 사항 (설계 시점에 이미 아는 것)

- 중첩 조건 그룹은 현재 실행 스키마에 없다 → 표현하지 않는다.
- 저장된 결과에 `executedRequest`가 없는 과거 기록은 그래프를 만들 수 없다("스냅샷 없음"). 새 DB 스키마를 도입하지 않는다.
- 저장·실행 스냅샷은 엔진 요청뿐이라 **미정 상태·조건별 원문 인용·값 출처(explicit/default)는 복구할 수 없다.** 확정 카드만 parsed의 미정을 보인다.
- `ParsedStrategy`에는 `source_text`가 없다. 조건별 원문 인용은 표시하지 않는다.
- 분류는 구조 설명이다. 성과·시장 적합성 판단에 쓰지 않는다.
- 합성 개념 노드(`concept.golden_cross` 등)는 만들지 않는다 — 컴파일된 조건에는 개념 ID가 남지 않고 전개된 지표 잎만 남는다. 분류는 지표 잎 위로만 연결한다.
- 영어 UI에서 지표 분류(class) 이름은 한국어로 남는다 — 온톨로지 시드에 영어 이름이 없다. 지표 이름은 `nameEn`을 쓴다.
- 거래 비용·체결 시점·벤치마크 같은 실행 가정은 그래프 범위 밖이다(결과 화면 요약에 있다).
- 볼린저 밴드 지정 변형(상단 돌파·하단 반등 등)은 모두 일반 "볼린저 밴드" 지표 노드로 연결되고 세부(밴드·방향)는 조건식에 적는다.

## 10. 구현 결과 (2026-10-15)

### 10.1 완료한 작업과 파일

| 작업 | 상태 | 파일 |
|---|---|---|
| X-1 공개 메타데이터 백엔드 | ✅ | `backend/strategy_conversation/registry/public_metadata.py`, `backend/api/strategy_graph_meta_routes.py`, `backend/main.py`(라우터 등록 1줄), `backend/tests/test_strategy_graph_meta.py` |
| X-2 Next 프록시·조회 | ✅ | `app/api/strategy/graph-meta/route.ts`·`route.test.ts`, `lib/strategy-graph/meta.ts`·`meta.test.ts`·`useGraphMeta.ts` |
| X-3 입력 래퍼·스냅샷 규칙 | ✅ | `lib/strategy-graph/types.ts`·`snapshot.ts`·`snapshot.test.ts` |
| X-4 변환 ① 구조 인스턴스 | ✅ | `lib/strategy-graph/conditions.ts`·`graphBuilder.ts`·`transformSections.ts`·`transform.ts`·`fixtures.ts`·`__fixtures__/*.json`·`transform.test.ts` |
| X-5 변환 ② 개념 연결·텍스트 구조 | ✅ | `lib/strategy-graph/concepts.ts`·`textOutline.ts`·`layout.ts`·`layout.test.ts` |
| X-6 UI | ✅ | `components/strategy/graph/StrategyGraphView.tsx`·`StrategyGraphDetail.tsx`·`StrategyGraphText.tsx`·`StrategyGraphCard.tsx`·`graphLabels.ts`·`StrategyGraphCard.test.tsx`, `lib/i18n/en.ts` |
| X-7 진입점 연결 | ✅ | `app/analytics/new/page.tsx`, `components/strategy/backtest/BacktestDashboard.tsx`·`BacktestDashboard.strategyGraph.test.tsx`, `app/backtest/[id]/page.tsx`·`page.test.tsx`, `app/analytics/new/page.confirm.test.tsx` |

실행 코드·해석·검증·컴파일·인증·소유권·DB 스키마는 변경하지 않았다. `types/strategy.ts`와 기존 응답 계약도 그대로다.

### 10.2 사용자 화면 위치와 스냅샷 출처

| 진입점 | 위치 | 입력 | 출처 |
|---|---|---|---|
| 확정 직후 자동 | 전략연구소 대화 — "이 전략으로 확정" 성공 메시지 아래 "확정된 전략" 카드 | `fromConfirmed` | `/api/strategy/compile` 응답의 `parsed`+`backtest_request`+`notices`를 **그 확정 건의 메시지에 독립 보존**(`ChatMessage.confirmedGraph`) |
| 확정 카드 다시 열기 | 같은 카드의 "접기" / "전략 그래프 열기" | 동일 | 동일 |
| 결과 화면(현재 세션) | 백테스트 결과 상단 "전략 그래프" 버튼 → "실행된 전략" | `fromExecuted` | 결과 이벤트 시점에 채워지는 `executedReq`만(`backtestReq`·`latestParsed` 미사용) |
| 저장된 결과 상세 | `/backtest/[id]` 같은 버튼 | `fromSavedHistory` | `result.executedRequest`만. 없으면 "이 실행의 전략 스냅샷이 저장되어 있지 않습니다."(`item.settings` 미사용) |

연결 지점은 `applyBuilderConfirmedStrategy`의 **성공 가지 한 곳**이다(남은 조건이 있어 되묻기로 가는 가지에는 연결하지 않는다). 특화 빌더의
`confirmed` 응답도 같은 함수를 쓰므로 같은 카드가 나온다. 확정 건마다 별도 메시지 카드라 이후 수정·재확정(B)이 이전 확정 그래프(A)를 바꾸지 않는다.

### 10.3 구현 중 확인·정정한 사항

- **확정 중복 방지**: `confirmDeterministicStrategy`는 `isSending` 상태만 막아 같은 틱의 연속 클릭을 걸러내지 못했다. `confirmInFlightRef` 단일 비행 가드를 추가했다(확정 호출 1회, 카드 1장).
- **공개 메타 색인 결함 수리**: 볼린저 밴드 변형 8개가 같은 엔진 바인딩을 공유해 색인이 임의의 잎을 가리켰다 → 일반 잎을 대표로 고정, 회귀 테스트 추가.
- **0의 의미**: 실제 컴파일러는 `stop_loss_pct=0`을 `None`으로 정규화한다. 그래서 "0은 유효 값" 검증은 0 임계값 필터(`영업이익증가율 >= 0`)와 저장된 요청의 `stop_loss_pct=0`(비활성 표시), `ranking_enabled=false`로 한다.
- **확정 카드만 미정을 보인다**: 미정(값 대기) 설정은 요청에 실리지 않으므로 `parsed`가 있는 확정 스냅샷에서만 "값 미정"으로 표시한다. 실행/저장 스냅샷은 이를 복구할 수 없다(카드에 그렇게 적는다).
- **실브라우저 점검에서 발견한 UI 결함 3건 수리**: 기본 맞춤 배율이 40~54%라 글자가 읽히지 않음(→ 첫 화면은 85% 이상, "화면에 맞추기"가 전체 보기), 개념을 펼쳐도 오른쪽 열이 화면 밖(→ 선택 시 자동 스크롤), 범례에 아이콘 없음.
- **그래프 표현 방식(2026-10-15 사용자 지시)**: 박스 없이 대화 폭을 넓게 쓰고(`min(94vw,1280px)`), 위→아래 트리로 그린다. 구분(투자 대상·매수 규칙 등)과 관계 이름(AND·기간·연산자·기준값·사용 지표)은 선 위의 알약, 조건은 "조건 N + 조건식" 상자이며 펼치면 파라미터·지표가 잎 노드로 붙는다. 구분마다 가로 띠로 쌓고 왼쪽 줄기선으로 전략에 연결하며, 하위 항목이 없는 설정 3개 이상은 세로로 쌓는다. 작은 전략(잎 24개 이하)은 조건을 모두 펼쳐 시작하고, 큰 전략은 접힌 채 시작해 선택한 조건만 펼친다. 노드는 한 계열의 파랑으로 통일하고 종류는 위치·라벨·형태로 구분한다. 그래프 모델과 변환은 그대로다.
- **초안 그래프(2026-10-16 사용자 지시)**: 되묻기 중 "현재까지 이해한 전략입니다" 카드는 텍스트 목록 대신 초안 그래프다(`DraftStrategyView`). 입력은 그 카드의 `parsed`를 결정론 컴파일(`/api/strategy/compile`, LLM 없음)에 보낸 한 쌍으로 `origin: draft`. 근거: 칩 답변 턴(`applyDeterministicConditionChoice`)은 `parsed`만 갱신하고 요청은 갱신하지 않아, 낡은 요청과 새 `parsed`를 섞지 않기 위해서다. 초안 컴파일은 `X-Graph-Draft: 1` 헤더로 실제 확정 호출과 구분된다. 컴파일이 안 되면 텍스트 요약으로 대체한다. 턴마다 호출이 한 번 늘어난다(지표 메타데이터는 캐시).
- **애니메이션(2026-10-16 사용자 지시)**: 노드는 위로 살짝 떠오르며 나타나고(깊이순 시차), 기존 노드는 CSS transform으로 새 자리까지 부드럽게 이동하며, 새로 생기거나 경로가 바뀐 엣지는 노드가 자리 잡은 뒤 선이 그려지고 화살표 머리가 마지막에 나타난다. 감속 설정(`prefers-reduced-motion`)에서는 모두 꺼진다. 위치는 SVG 속성이 아니라 CSS transform이다.
- **"크게 보기" 제거(2026-10-16 사용자 지시)**: 카드의 "크게 보기" 버튼과 확대 대화창(`GraphDialog`)을 삭제했다. 그래프는 카드 안에서 줌 버튼으로 크기를 조절한다. §6의 "크게 보기(모달: 포커스 진입·복귀·Escape)" 요구는 이로써 폐기됐다.
- **노드 상세는 툴팁(2026-10-16 사용자 지시)**: 선택한 노드의 상세(조건식·값·출처)는 그래프 아래 고정 패널이 아니라 노드 아래(펼쳐진 하위 항목 아래)에 뜨는 툴팁으로 보인다. 선택하지 않으면 아무것도 보이지 않는다(빈 상태 문구 없음). 툴팁 바깥을 누르면 닫히고(닫기 버튼은 없다), 같은 노드를 다시 클릭하거나 Escape로도 닫힌다.
- **툴팁 내용(2026-10-16 사용자 지시)**: 툴팁은 "값의 출처"와 "저장된 원문 인용이 없습니다" 같은 항상 같은 문구를 빼고, 대신 **쓰이는 자리**(구분 · 결합 그룹, 예: "매도 규칙 · 하나라도 충족 (OR)")와 **같은 지표를 쓰는 다른 조건**(매수·매도에서 같은 지표를 쓰는 경우 그 조건식)을 보여준다. 원문 인용은 실제로 있을 때만 표시한다.
- **노드 상세 툴팁 제거(2026-10-16 사용자 지시)**: 노드를 누르면 상세 툴팁(`StrategyGraphDetail`)을 띄우던 기능을 삭제했다. 선택은 연결된 항목을 강조하고 조건의 하위 항목을 펼칠 뿐이다. 지표 분류 계층을 여는 UI도 함께 없어져 분류 노드는 그래프에 나타나지 않는다. 텍스트 보기(`StrategyGraphText`)에서는 지표·분류 경로를 그대로 볼 수 있다.
- **매매 흐름도(2026-10-18 사용자 지시)**: 트리 배치를 왼쪽→오른쪽 흐름도로 바꿨다. 칸은 `투자 대상 → 매수 규칙 → 자금 배분 → 매도 규칙`(종목 선정 필터·순위 선정은 첫 칸, 리밸런싱은 자금 배분 칸, 위험 관리는 매도 칸)이고, 구분 제목 알약에서 항목이 나란한 가지로 갈라진다. 선은 실제 관계만 뜻한다: 구분 → 다음 구분(같은 칸 안에서는 위→아래 화살표, 칸 사이는 가로 화살표), 구분 → 항목, 항목 → 하위 항목(복합 순위 구성요소 등). 같은 구분의 형제 항목끼리는 잇지 않는다. 확정 AND/OR 결합 그룹은 구분 제목에 합쳐 표시하고(`매수 규칙 · 모두 충족 (AND)`), 결합 방식을 확인할 수 없을 때만 노드로 남긴다. 조건 번호("조건 N")와 분류 노드는 없앴다. 모든 항목은 처음엔 접혀 있고, 선택하면 "라벨: 값"과 사용 지표 잎이 그 항목 아래에 붙는다. 처음 열 때와 "화면에 맞추기"는 카드 너비에 맞춘 배율(최대 100%)이며, 직접 확대·축소하면 자동 맞춤이 꺼지고 펼침으로는 배율이 바뀌지 않는다. 구분 제목은 한 줄이고 줄 수에 맞춰 높이가 늘어난다. 테스트: `lib/strategy-graph/layout.test.ts`(칸 순서, 형제 비연결, 떠 있는 항목 없음, 제목 한 줄), `StrategyGraphCard.test.tsx`(자동 맞춤·펼침 불변·확대 시 자동 맞춤 해제). 이 절이 위의 "트리" 설명을 대체한다.
- **백테스트 기간 노드(2026-10-16)**: 자금 배분 구분에 "백테스트 기간"(상대 기간 또는 시작·종료일)을 추가했다. 초안 그래프는 컴파일러가 채우는 기본값(기간·초기 자본·보유 수·리밸런싱 "없음")을 사용자가 말한 값처럼 그리지 않도록 백엔드 provenance(`explicit_fields`)에 있는 항목만 그린다. 확정·실행 스냅샷은 항상 그린다.

- **추가 노드 하이라이트(2026-10-20 사용자 지시)**: 이미 그려진 그래프에 조건·구분이 새로 더해지면 그 노드(와 구분 제목 알약)만 팝인 직후 테두리 링이 두 번 깜빡이고 사라진다(`StrategyGraphView`의 `sg-added`, `data-testid="graph-added-highlight"`). 첫 그리기(그릴 것이 전부 새 것)·`instant`·펼침으로 생기는 세부 잎(leaf)은 대상이 아니다. 판정은 기존 `GraphSeen`(이미 그린 키) 대조만 쓰며 새 입력·LLM 호출은 없다. `prefers-reduced-motion`에서는 숨긴다.
