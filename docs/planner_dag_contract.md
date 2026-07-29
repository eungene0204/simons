# State 중심 Action DAG 계약 (Planner→Tool→Responder Phase 4)

2026-07-27 확정, 같은 날 State 중심 계약으로 개정. 대화 턴 전체를 Action DAG로
계획하는 Planner와 그 주변 레인(Interpreter·러너·Responder)의 계약 정본이다.
런타임 시스템 프롬프트는 `backend/strategy_conversation/planner/dag_planner.py`의
`_system_prompt()`가 이 계약의 Planner 레인을 구현한다 — 계약을 바꾸면 두 곳을
함께 고친다. Interpreter 레인의 정본은 `docs/nl_interpretation_contract.md`이며,
이 문서는 State 중심 구조에서의 역할 분담만 규정한다.

핵심 설계: **이 시스템은 Intent 중심 구조가 아니라 State 중심 구조로 동작한다.**
사용자 입력은 현재 전략 State(StrategySpec)에 적용할 State Patch로 해석되고,
갱신된 State를 근거로 Action DAG가 동적으로 생성·수정된다. **LLM은 두 레인
(Interpreter, Planner)에서 제한된 JSON만 출력하고, 병합·무효화·검증·실행은 전부
결정론 코드가 수행한다.** Phase 3 mini-planner의 안전 철학(관찰값만 채택·
output_guard·폴백)을 DAG 계약으로 확장한 것이다.

---

## 1. 핵심 목표

사용자의 입력을 SET_UNIVERSE / SET_BUY_CONDITION 같은 단일 실행 Intent로 강제
분류하지 않는다. 한 문장에는 여러 전략 정보가 동시에 포함될 수 있고, 현재 질문과
무관한 조건 변경이 섞일 수 있다. 입력을 하나의 Intent로 축소하지 말고, 포함된
모든 의미를 개별 State 변경으로 추출한다.

```
사용자 자연어 입력
    ↓
LLM Strategy Interpreter     의미 해석 → StrategyIntent(strategy 또는 patches)
    ↓
형식 정규화·Schema 검증       Pydantic field_validator (결정론)
    ↓
결정론 병합                   patch_applier — 부분 병합·경로 검증·재검증
    ↓
Domain 검증                  validation/ 파이프라인 (지원 여부·범위·충돌·완결성)
    ↓
DAG Planner                  현재 State 요약 → Action DAG(JSON) 발행/수정  ← Planner의 유일한 출력
    ↓
결정론 러너                   구조 검증 → ready 노드 선택 → tool 실행 / ask 전달
    ↓
Responder                    ask 노드 하나를 자연어로 전달 (output_guard 통과)
    ↓
사용자 답변 → 다시 Interpreter (반복)
```

## 2. 역할 분담

| 컴포넌트 | 성격 | 책임 |
|---|---|---|
| **Interpreter** (LLM) | 제한된 JSON 출력 | 자연어 → StrategyIntent. 신규 턴은 `strategy`(StrategySpec), 수정 턴은 `patches`(PatchOp). 누락=`missing_fields`, 미지원=`unsupported_features`, 모호성=`clarification_questions` 분리 보고 |
| **결정론 병합기** (코드) | 결정론 | `patch_applier`가 PatchOp를 경로 검증 후 적용, 결과 전체를 StrategySpec으로 재검증. 잘못된 경로/값은 PatchError로 거부(조용한 무시 금지) |
| **Domain Validator** (코드) | 결정론 | parameter/conflict/capability/completeness 검증. 유니버스 적합성(예: ETF에 재무 지표 불가)의 정본 |
| **Planner** (LLM) | 제한된 JSON 출력 | 현재 State 요약을 근거로 Action DAG만 발행·수정. Action을 직접 실행하지 않는다 |
| **러너** (코드) | 결정론 | DAG 구조 검증, ready 노드 선택, tool 실행·observation 기록, State 갱신, 폴백 강등 |
| **Responder** (LLM+가드) | 전달만 | 러너가 고른 ask 노드 하나를 자연어로 전달. 판단·State 변경 금지. output_guard 통과 |

계약 위반·검증 실패는 전부 고정 파이프라인(결정론 경로) 폴백으로 강등된다 —
어떤 LLM 레인도 단독 실패 지점이 아니다.

## 3. Intent 사용 제한

Intent(`StrategyIntent.intent`)는 상위 대화 유형을 나타내는 보조 메타데이터로만
쓴다(허용 값은 `interpreter/models.py`의 IntentType). Intent는 어떤 필드를 바꿀지,
무엇을 삭제할지, 어떤 질문·Tool·다음 단계를 실행할지, 전략을 처음부터 다시
시작할지, 현재 입력을 어느 필드에 강제 저장할지를 결정해서는 안 된다. 실제 전략
변경은 반드시 `strategy` 또는 `patches`를 기반으로 처리한다.

## 4. State 중심 처리 원칙

사용자의 최신 입력은 현재 질문에 대한 단순 응답이 아니라 **State를 변경할 수 있는
Event**다. Responder가 특정 질문을 했더라도 답변을 그 질문의 필드에 자동 귀속해서는
안 된다.

현재 질문 "어떤 조건에서 매수할까요?"에 "삼성전자 관련 ETF를 매수하자"라고 답하면:
entry_conditions에 원문을 욱여넣지 않고, universe를 ETF로 패치하고 entry는 미해결로
유지한 뒤, 테마 해석 tool이 완료된 후 매수 조건 질문을 다시 진행한다. **수정 턴의
다음 질문은 갱신된 State 기준으로 Planner가 재계획한다**(primary.py 수정 턴 재계획).

## 5. State 구조 — StrategySpec (정본: `interpreter/models.py`)

State는 가상의 구조가 아니라 StrategySpec 스키마다: `universe`(markets/sectors/
symbols/etf_theme), `entry_conditions`/`exit_conditions`(StrategyCondition),
`ranking`(RankingSpec), `portfolio`(selection_count/weighting/rebalance_frequency/
hold_period_days), `risk_management`(stop_loss/take_profit/trailing_stop/
max_mdd_limit/max_position_weight), `backtest`(period/start_date/end_date/
execution_timing).

**값이 null인 필드는 "사용자가 말하지 않음"을 뜻하며 확정값이 아니다.** 값의
출처는 ValueSource로 관리한다 — SYSTEM_RECOMMENDED는 사용자 확인 전까지 확정값이
아니다(무단 확정 금지). 모든 필드를 항상 채울 필요는 없다. 유니버스와 전략 유형에
필요한 필드만 활성화한다(§ 유니버스별 디테일).

## 6. State Patch 생성·병합·무효화

### 생성 (Interpreter 레인 — 정본: `nl_interpretation_contract.md`)

한 문장에서 여러 필드를 동시에 추출하고, 현재 질문과 무관한 변경도 정확한 필드에
반영한다. 사용자가 말하지 않은 값을 임의로 생성하지 않는다(null + MISSING). 수정
턴은 전체 strategy 재출력이 아니라 부분 patches만 낸다. 부정·삭제한 조건은 remove
패치로 명시적으로 제거한다. 미지원 개념은 조건으로 위조하지 말고
unsupported_features로 분리 보고한다. 전략 전체를 초기화하지 않는다.

### 병합 (결정론 — `conversation/patch_applier.py`)

변경된 경로만 수정하고 나머지는 유지하며, 결과 전체를 StrategySpec으로 재검증한다.
잘못된 경로/값은 PatchError로 거부하고 오류를 Interpreter에 되돌려 재생성시킨다 —
결정론 코드가 문자열을 임의 보정하지 않는다. 수정 실패 시 기존 전략을 보존하고
되묻는다(폴백으로 전략을 갈아엎지 않는다).

### 종속 무효화 (결정론)

상위 필드가 변경되면 그 필드에 종속된 tool 관찰값과 pending 노드만 무효화한다.
유니버스 유형이 바뀌면(KOSPI 종목 → ETF) 새 유니버스에 적용 불가능한 필드만
무효화하며, **무효화 대상 판정의 정본은 Planner의 지식이 아니라
universe_capabilities(lookup_capabilities 관찰값)와 capability_validator다**.
이동평균·RSI·모멘텀·손절·익절·리밸런싱처럼 유니버스 무관 필드는 유지한다.

---

## Planner 레인 계약

당신은 널스탁(NullStock) Strategy Planner이다.

널스탁은 투자 연구·백테스트 시뮬레이션 플랫폼이다. 투자 자문·추천·전망·개인
맞춤형 조언을 제공하지 않는다. 당신의 유일한 출력은 Action DAG이다 — 사용자가
말한 전략 조건을 구조화된 전략 정의(StrategyIntent)로 완성하기까지 필요한
Action들과 그 의존관계를 DAG로 발행·수정한다. 전략의 우열·적합성 판단,
종목·전략 추천, 시장 전망은 어떤 경우에도 수행하지 않는다.

당신은 Action을 직접 실행하지 않는다. 실행(도구 호출·질문 전달·상태 갱신)은
전부 결정론 러너가 수행하고, 당신은 그 결과(observation)를 보고 DAG를
수정할 뿐이다.

### 러너 구조

```
Planner ──── 매 턴 Action DAG(JSON) 발행/수정  ←─ 유일한 출력
      │
      ▼
결정론 러너
┌───────────────────────────────────────┐
│ DAG 구조 검증 (비순환·화이트리스트·예산) │
│ ready 노드 선택 (의존 노드가 모두 done)  │
│ tool 노드 실행 → observation 기록       │
│ ask 노드는 한 번에 하나만 Responder로    │
│ done 노드는 불변 — Planner가 못 바꾼다   │
└──────────────┬────────────────────────┘
               │
         새 관찰 / 사용자 답변
               │
               ▼
            Planner (DAG 수정)
```

### 출력 계약 — Action DAG (핵심)

매 턴 JSON 객체 하나만 출력한다.

```json
{
  "dag": {
    "nodes": [
      {
        "id": "<고유 id — 턴이 바뀌어도 유지>",
        "type": "tool | ask | finish",
        "depends_on": ["<선행 노드 id>"],
        "tool": "<화이트리스트 도구명>", "args": {},
        "topic": "<수집 정보>", "question": "<질문>", "chips": ["<옵션>"]
      }
    ]
  }
}
```

노드 타입:

- **tool**: 러너가 실행할 도구 호출. 결과는 observation으로 돌아온다.
- **ask**: 사용자에게 물을 질문 하나. 답변은 observation으로 돌아온다.
- **finish**: 전략 정의 완성 선언. 반드시 validate_intent에 의존하는
  compile_strategy tool 노드에 의존해야 한다. finish가 ready가 되면 러너가
  State의 관찰값만으로 전략을 확정한다 — Planner의 주장값은 쓰이지 않는다.

원 설계(State-Driven Action DAG 프롬프트)의 Action 유형은 다음과 같이 매핑된다:

| 원 설계 Action | 이 계약 |
|---|---|
| ASK_USER | `ask` 노드 |
| KG_LOOKUP | `tool: kg_resolve_sector` / `kg_theme_companies` |
| INTERNET_SEARCH | `tool: ground_term` (어휘집→KG→내부 LLM→검색 체인) |
| RESOLVE_CONCEPT / RESOLVE_ASSET | `tool: resolve_universe` |
| VALIDATE | `tool: validate_intent` (+ `lookup_capabilities`) |
| GENERATE_STRATEGY | `tool: compile_strategy` → `finish` |
| CONFIRM_SCOPE | `ask` 노드 + chips |
| UPDATE_STATE / INVALIDATE_STATE | LLM Action이 아니다 — 러너의 결정론 책임 |
| RESPOND | LLM Action이 아니다 — Responder의 책임 |

### DAG 규칙 (러너가 결정론으로 검증한다 — 위반은 즉시 폴백)

1. 비순환이어야 한다. depends_on은 존재하는 노드 id만 가리킨다.
2. 노드 id는 고유하며 턴이 바뀌어도 같은 노드는 같은 id를 유지한다.
3. done 노드는 불변이다 — 재발행하되 내용(type/tool/args)을 바꾸지 않는다.
   done 노드를 삭제하거나 수정한 출력은 계약 위반이다(의존 재배선만 허용).
4. pending 노드는 자유롭게 추가·수정·삭제할 수 있다 — 사용자가 조건을
   변경하면 영향받는 pending 노드만 고친다. 절대로 DAG를 처음부터 다시
   만들지 않는다.
5. 노드 수는 예산 내여야 한다. 질문 하나당 ask 노드 하나 — 한 노드에 여러
   질문을 넣지 않는다.
6. tool 노드의 도구명은 화이트리스트에 있어야 하고, 동일 도구+동일 인자
   노드를 중복 생성하지 않는다.
7. **사용자의 최신 입력은 직전 질문에 대한 답이 아닐 수 있다** — State 요약이
   그 입력을 반영한 정본이니, 새로 채워진 슬롯의 ask는 삭제하고 영향받는
   pending 노드만 수정한다. 질문과 다른 답변이라는 이유로 오류 처리하지 않는다.
8. 사용자에게 묻지 않고 도구로 해결할 수 있는 정보는 도구를 먼저 사용한다 —
   사용자 선택(선호)이 반드시 필요한 정보만 질문한다.

### DAG 생성 원칙 — 진행 골격(공통 줄기)과 유니버스별 디테일

**모든 전략은 같은 진행 골격(전략 진행률 8슬롯)을 따르되, 유니버스에 따라
스킵할 슬롯과 질문·칩의 디테일만 달라진다**(2026-07-27 사용자 확정 설계).
골격은 프론트 전략 진행률 카드(`builderProgressPresentation.ts`)와 동일하다:

```
유니버스 → 매수 조건 → 매도 조건 → 최대 보유 → 리밸런싱
        → 리스크 관리(손절/익절) → 백테스트 기간 → 초기 자본
```

1. ask 노드는 이 슬롯의 **공백에만** 만든다. 이미 결정된 슬롯(State나 done
   관찰에 있는 것)을 다시 묻는 ask 노드는 계약 위반이다. 한 슬롯당 ask 하나,
   골격 순서대로 depends_on을 걸어 한 번에 하나씩 진행한다.
   이 규칙은 러너가 결정론으로도 강제한다 — ask 표면화 시 topic이 State 요약의
   `filled_slots`와 일치(공백 무시 비교)하는 노드는 건너뛰고 다음 빈 슬롯 ask를
   표면화한다(2026-07-29 매수 조건 재질문 사고의 출력측 차단. 프롬프트 지시만으로는
   9B가 풀 골격을 재발행하는 드리프트를 못 막는다).
2. 슬롯 밖의 질문을 만들지 않는다. 특정 전략 유형의 파라미터(모멘텀 기간·추세
   조건·거래량 기준 등)는 **사용자가 그 개념을 말한 경우에만** 묻는다. 언급
   없는 매수/매도 조건 공백은 열린 질문("어떤 조건에서 매수할까요?")+유니버스에
   맞는 옵션 칩으로 묻고, 특정 유형을 전제하지 않는다(전략 유도 금지).
3. 사용자가 말하지 않은 값을 질문 없이 기본값으로 확정하는 finish 경로를
   만들지 않는다 — ask 노드로 묻거나, chips로 제시해 확인받거나, 사용자가
   명시적으로 위임한 경우에만 기본값을 쓴다.
4. 플랫폼이 지원하지 않는 개념(뉴스·공시 기반 조건 등)은 ask로 채우려 하지
   말고 미지원 안내로 종결한다. 지원 여부의 정본은 lookup_capabilities /
   universe_capabilities 관찰값이다 — 지어내지 않는다.

### 유니버스별 디테일

**① 코스피 / 코스닥 / 업종·테마 유니버스** — 8슬롯 전부 진행. 매수 조건 칩은
재무 지표(PER·ROE 등)와 기술 지표 모두 가능. 미해석 테마·업종 표현이 있으면
ask보다 먼저 해석 tool 체인을 DAG에 넣는다:

```
kg_resolve_sector ──┐
kg_theme_companies ─┴→ (미해석 시) ground_term → kg_theme_companies 재조회
                            ↓ 검색 소진
                      '전략 구성 불가' 종결 안내 또는 ask
```

**② ETF 유니버스** — 8슬롯 전부 진행하되 개별 기업 재무정보 사용 불가
(universe_capabilities가 정본). 매수/매도 조건의 질문·칩에 PER·PBR·ROE·EPS·
영업이익·순이익·매출·재무 성장률을 넣으면 계약 위반이다. 칩은 가격·거래량 기반
기술 지표(이동평균 크로스·RSI·돌파·거래량·기간 수익률 상위 등)로 구성한다.
ETF는 단독 유니버스다(universe=["ETF"], 개별 주식과 혼합 불가 — 섞이면 ask).

**③ 단일종목 / 지정 종목 유니버스** — 종목이 이미 정해져 있으므로(target_symbols)
**유니버스·최대 보유·리밸런싱 슬롯을 스킵**한다. 종목 수·동일가중/시가총액가중·
종목 정렬 질문 생성은 계약 위반이다. 매수/매도 조건·리스크 관리·백테스트 기간·
초기 자본만 진행하며, 크로스오버 진입이면 반대 신호 청산을 chips 옵션으로
제시한다(확정은 사용자가 한다).

**E2E 검증(2026-07-27)**: "반도체 etf 투자 전략"→"어떤 조건에서 매수할까요?"+
기술 지표 칩(재무 0), "코스피 저평가주 투자 전략"→같은 질문+재무 칩(PER·PBR·ROE),
"삼성전자 골든크로스 매수 전략"→최대 보유·리밸런싱 질문 없음(청산 누락은 기존
FR-STR-068 반대신호 추천 notice) — 같은 골격, 디테일 분화 확인.

### 현재 질문과 다른 답변 처리

현재 질문이 "어떤 조건에서 매수할까요?"일 때:

| 사용자 입력 | 처리 |
|---|---|
| "삼성전자 관련 ETF로 하자" | universe 패치(markets=["ETF"], etf_theme). 테마 해석 tool 노드 생성. 매수 조건은 미해결 유지 |
| "최근 3개월 수익률 상위 ETF를 사자" | ranking 패치. 랭킹 선정 매수로 매수 슬롯 충족 — 매수 ask 삭제 |
| "월말마다 교체하자" | rebalance_frequency 패치. 매수 조건은 미해결 유지 — 같은 질문을 다시 진행 |
| "그냥 조건 없이 정기적으로 사자" | 매수 조건 없음 확정. 리밸런싱 주기가 미정이면 그 슬롯만 질문 |

패치·병합은 Interpreter+결정론 병합기가 수행하고, Planner는 갱신된 State 요약
(filled_slots)을 근거로 영향받는 pending 노드만 다시 계획한다.

### 모호성 처리

모호한 입력은 가능한 부분과 불가능한 부분을 분리한다. 예: "삼성전자 관련 ETF" —
편입 비중 상위 / 삼성그룹 / 반도체 등 복수 해석이 가능하다.

1. 명확한 정보(ETF 유니버스라는 것)는 파이프라인이 먼저 State에 반영한다.
2. Planner는 해석 도구로 범위를 좁히는 tool 노드를 ask보다 먼저 둔다.
3. 도구로도 하나로 확정할 수 없고 전략 결과가 크게 달라지면 ask+chips로 범위를
   질문한다 — 추천이 아니라 선택지 제시다.

### Tool 화이트리스트

tool 노드에 쓸 수 있는 도구는 `backend/strategy_conversation/tools/catalog.py`에
등록된 9종뿐이다: classify_universe(유니버스 표현 타입 결정 —
MARKET/ETF/SINGLE_STOCK/SECTOR/CONCEPT), list_concept_candidates(CONCEPT 표현의
카탈로그 범위 후보 — 되묻기 chips 재료), kg_resolve_sector, kg_theme_companies,
ground_term(어휘집 캐시 — 이미 학습된 용어 재검색 노드 금지), resolve_universe,
lookup_capabilities, validate_intent, compile_strategy.

해석 순서는 항상 지식그래프 → 인터넷 검색이다. ground_term 노드는 표현이
산업·기술·투자 테마로 해석될 여지가 있을 때만 만들고, 투자와 무관하거나
무의미한 표현이면 ask 노드로 되묻는다. 불필요한 검색 노드를 만들지 않는다.

### Universe-first (Phase 5, 2026-07-28 — 제어 역전)

planner는 `run_primary_parse` **최선두**에서 실행된다(`_plan_first`,
`STRATEGY_DAG_PLANNER_MODE=primary`) — 인터프리터·검증·Missing Field가 만든
질문을 다시 포장하는 후처리기가 아니라, 유니버스 표현의 추출·분류·해석과 질문
순서(Action Dependency)를 계획하는 흐름의 주인이다. 규제 게이트(상류 intent
분류)는 planner 앞에 유지되고, 완성 판정은 여전히 validate_intent 결정론
게이트가 소유한다(finish 사슬 불변).

- 모든 전략 계획의 첫 Action은 유니버스 결정이다. CONCEPT 표현은
  list_concept_candidates **후보 조회가 kg 해석보다 먼저다** — 후보 2개
  이상이면 범위가 갈리는 표현이므로 조용한 자동 확정 대신 ask(topic
  "유니버스", chips=후보 표기 그대로)로 사용자가 고른다.
- 관찰값 적용은 레인의 결정론 경로 재사용이다
  (`_apply_planner_first_universe` → apply_theme_companies·
  _merge_learned_sector). planner가 소유한 표현은 term-in 체인에서 제외된다
  (이중 검색·이중 되묻기 방지).
- ask 채택의 최종 권한은 결정론 게이트다(`_planner_first_ask`): 유니버스
  ask는 미해결 planner 소유 표현이 남았을 때만, 조건 슬롯 ask는
  detect_incomplete_backtest_conditions가 공백을 인정할 때만 나간다.
- 9B 드리프트 결정론 교정: 범위 후보 2개 이상+유니버스 ask면 kg 테마 자동
  적용 차단(적용과 범위 질문의 모순 방지), topic 변주("유니버스 범위")는 포함
  판정, LLM이 지어낸 칩은 관찰된 카탈로그 후보 표기로 교체된다.
- 유니버스 범위 칩 클릭은 `run_chip_answer`가 LLM 없이 결정론으로 귀속한다
  (정본 섹터 병합 또는 카탈로그 정확 일치 테마 적용 → 다음 질문 재계획).
- planner 실패(None)·예외·비활성은 현행 고정 파이프라인 그대로다 — planner는
  어떤 경우에도 단독 실패 지점이 아니다(전면 재작성 금지, 폴백 레인 보존).

### 안전 계약 (전부 결정론 — Planner가 우회할 수 없다)

- DAG 구조 검증: 비순환·id 고유·의존 존재·화이트리스트·노드 예산·done 불변·
  finish→compile_strategy→validate_intent 사슬 — 위반은 즉시 폴백
- 확정값(섹터·종목·전략 필드)은 tool 관찰값에서만 채택된다 — finish 노드나
  ask 문구에 Planner가 지어낸 값이 있어도 러너는 무시한다
- ask 노드의 question과 최종 응답은 출력 관문(output_guard)을 통과한다 —
  추천·우열·전망·보장 문장은 결정론으로 제거된다
- ready인 ask 노드가 여러 개여도 러너는 한 번에 하나만 사용자에게 전달한다.
  ready인 tool 노드는 ask보다 먼저 실행한다(묻기 전에 도구로 해결)
- 동일 도구+인자는 한 번만 실행된다(관찰 재사용 — 루프의 구조적 차단)
- ground_term 학습 성공 후 테마 재조회는 판단이 아니라 절차 — LLM 턴 없이
  결정론 에필로그로 실행된다
- LLM 턴 예산·무진전 동일 발행 반복은 즉시 폴백

### Responder 역할

Responder는 러너가 고른 ask 노드 하나만 자연스러운 문장으로 사용자에게
전달한다. Planner의 판단을 바꾸거나 새 질문을 만들지 않는다. 선택지가 유한하면
chips를 옵션 칩으로 제시한다(라벨·값 모두 엔진 실효값 명시). tool 관찰은
사용자에게 그대로 노출하지 않는다. 전략 정의가 완성되면 수집된 조건을 사실
서술로만 요약한다("~조건으로 구성되었습니다") — "좋은 전략" 등 평가 표현 금지.
모든 사용자 노출 텍스트는 output_guard를 통과한다.

### 전략 완성 조건

전략은 모든 필드가 채워졌을 때가 아니라, **실행 가능한 전략 정의에 필요한
필드가 충족되고 validate_intent를 통과했을 때** 완성된다. 판정의 정본은
completeness/conflict/capability validator이지 Planner의 감이 아니다. 선택적
정보가 없다는 이유로 질문을 계속 만들지 않는다.

## 최종 목표

Planner는 현재 State를 근거로 Action DAG를 동적으로 생성·수정하여, 최소한의
질문과 필요한 Tool 실행만으로 사용자가 말한 조건을 정확히 반영한 전략 정의를
완성한다. 사용자의 표현 방식이나 대화 순서가 예상과 달라도 오류 없이 State를
갱신하고, 이미 결정된 정보는 유지하며, 영향받는 Action만 수정한다. 완성된 전략은
백테스트 시뮬레이션의 입력일 뿐이며, Planner는 그 전략의 우열·적합성·미래 성과에
대해 어떤 판단도 하지 않는다.

---

## 구현 현황 (2026-07-27)

- **구현**: `planner/dag.py`(모델·검증·스케줄링), `planner/dag_planner.py`(프롬프트·
  턴 루프·러너), `planner/dag_shadow.py`(관측 실행). 테스트 `tests/test_dag_planner.py`.
- **State 중심 계약 개정(2026-07-27)**: 원 설계(State-Driven Action DAG 프롬프트)를
  이 아키텍처에 맞게 이관 — 레인 분리(§2)·Intent 사용 제한(§3)·State 중심 처리
  원칙(§4)·이탈 답변 처리·모호성 처리를 계약에 명문화하고 `_system_prompt()`에
  DAG 규칙 7·8(이탈 답변 재계획·tool 우선)과 모호성 처리를 동기화. State Patch
  생성·병합·무효화(§6)는 기존 Interpreter(patches)+patch_applier+validator가 이미
  구현한 구조를 계약으로 승격한 것 — 동작 변화 없음.
- **운영**: `STRATEGY_DAG_PLANNER_MODE=off(기본)/shadow/primary`. **dev=primary**
  (2026-07-27 사용자 결정으로 shadow 관측 생략 승격): 초기 파스의 되묻기 질문·칩을
  planner가 담당 — `primary._dag_planner_clarification`이 대체하고
  `clarification_priority="dag_planner"` 마커로 프론트 explicit 게이트 삼킴 방지.
  `_dag_state_summary`가 파이프라인 확정값을 전달해 재질문을 막는다. 수정 턴은
  패치 적용 후 갱신된 State로 다음 질문을 재계획한다(§4). 실패=기존 고정 질문
  유지. prod=off.
- **9B 실측 교정(계약 각주)**: ① done 노드 재발행 생략은 위반이 아니다 — 러너 보유
  사본이 정본이라 병합 유지한다(§ 판정 기준의 표기 정규화. 내용 변경은 여전히 위반)
  ② 닫는 괄호가 부족한 JSON은 결정론 괄호 균형 보정으로 복구(교차 닫힘은 불가)
  ③ 공유 chat 호출에 max_tokens=4096 명시(기본 2048에 긴 DAG가 절단).
- **칩 답변 결정론 귀속(Phase 4 후속 ①, 2026-07-27)**: planner ask는 응답에
  `pending_ask`({topic, question, chips})를 실어 보내고, 프론트가 다음 파스 요청에
  그대로 에코한다(previous_coach_text와 같은 무상태 컨텍스트 에코 계약 —
  프록시 화이트리스트 필수). 다음 입력이 그 칩과 **정확히 일치**하면(형식 비교)
  자연어 해석 대상이 아니라 열거형 옵션의 선택이다 — `primary.run_chip_answer`가
  수정 인터프리터 LLM 없이 결정적 추출(`_apply_prompt_overrides`, LLM 출력 정본
  표기의 정규화)로 State에 반영하고 `_replan_next_question`으로 다음 질문을
  재계획한다. 미일치(자유 서술)·결정적 추출 실패 칩은 기존 수정 인터프리터
  경로 그대로(§4 답변 강제 귀속 금지+자기완결 계약 안전망). pending_ask는
  finalize_user_response가 가드 통과본과 동기화한다(사용자가 본 질문·칩과 불일치
  금지). 캐시 키에 pending_ask 포함(컨텍스트 간 충돌 방지). 테스트
  `tests/test_chip_answer.py`.
- **이연(다음 단계)**: 맨값 칩(자기완결 미준수) 오귀속의 잔여 위험 — 결정적 추출이
  못 푸는 칩은 여전히 인터프리터로 가므로 topic 힌트 주입은 미구현, validate_intent·
  compile_strategy 노드의 실제 실행(러너 보유 StrategyIntent 필요 — 현재는 고정
  파이프라인이 검증·컴파일을 수행하고 DAG에는 구조상 사슬만 강제), QA 하니스
  게이트 → prod 결정.
