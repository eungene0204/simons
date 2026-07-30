# 자연어 해석 계약 — LLM 의미 해석 / 결정론 형식 검증

> 대상: `backend/strategy_conversation/` (LLM Strategy Interpreter 파이프라인)
> 원칙: **자연어의 의미는 LLM만 해석한다. 결정론 코드(Regex 포함)는 LLM이 생성한
> 제한된 구조화 출력의 형식만 검증·정규화한다.**

---

## 0. 이 문서의 위치

우리 시스템에서 "LLM이 생성하는 제한된 구조화 문자열"은 별도 DSL이 아니라
**`StrategyIntent` JSON (schema_version 1.0)** 이다
([interpreter/models.py](../backend/strategy_conversation/interpreter/models.py)).

`UNIVERSE(...);BUY(...)` 같은 괄호 DSL을 새로 만들지 않는 이유:

- 컴파일러(`compiler/strategy_compiler.py`), 검증 4단계(`validation/`), 되묻기 채널,
  프론트 `previous_parsed` 상태가 전부 이 JSON 스키마 위에 서 있다.
- JSON은 Pydantic이 형식을 검증하므로 Regex가 괄호·구분자를 셀 필요가 없다 —
  "Regex를 자연어에서 떼어낸다"는 목표에 더 가까운 표현이다.
- DSL은 문법 검증기·파서·역직렬화기를 새로 만들어야 하고, 그 파서가 다시
  자연어 해석 코드로 비대해지는 경로(현 `nl_parser.py`)를 반복할 위험이 있다.

따라서 아래 계약은 원문 스펙의 원칙을 **우리 기존 계약 위에** 재표현한 것이다.

### 원문 스펙 ↔ 우리 구조 매핑

| 원문 스펙 | 우리 구조 |
|---|---|
| 제한된 구조화 문자열 | `StrategyIntent` JSON |
| `UNIVERSE(...)` | `strategy.universe` (`markets` / `sectors` / `etf_theme`) |
| `BUY(...)` / `SELL(...)` | `strategy.entry_conditions[]` / `exit_conditions[]` |
| `RISK(...)` | `strategy.risk_management` |
| `PORTFOLIO(...)` / `REBALANCE(...)` | `strategy.portfolio` |
| `PERIOD(...)` / `CAPITAL(...)` | `strategy.backtest` |
| `UPDATE(field=,value=)` | `intent="MODIFY_STRATEGY"` + `patches[]` (JSON Patch) |
| `NEED_CLARIFICATION(field=)` | 값을 `null`로 둔다 → 검증 계층이 `missing_fields[]` + `clarification_questions[]` 산출 |
| `UNSUPPORTED(reason=)` | `intent="UNSUPPORTED_REQUEST"` 또는 `unsupported_features[]` |
| `OUT_OF_SCOPE(reason=)` | `intent="NON_STRATEGY_REQUEST"` |
| Regex 형식 검증 | `output_repair.extract_json_object` + Pydantic `field_validator` |
| Schema Validator | Pydantic `StrategyIntent` |
| Domain Validator | `validation/pipeline.run_validation` (4단계) + `registry/` |

---

## 1. 처리 구조

```text
사용자 자연어 입력
    ↓
LLM 의미 해석                     interpreter/llm_strategy_interpreter.py
    ↓
StrategyIntent JSON 생성          프롬프트 계약: interpreter/prompts.py
    ↓
형식 추출·정규화 (결정론)          interpreter/output_repair.py, models.py field_validator
    ↓
스키마 검증 (Pydantic)             interpreter/models.py
    ↓  실패 시 → 오류 원문을 LLM에 전달해 재생성 (MAX_REPAIR_ATTEMPTS회)
도메인 검증 (결정론)               validation/pipeline.py
    ├ capability_validator   지원 지표인가 (registry/indicator_registry)
    ├ parameter_validator    값·파라미터 범위/단위가 유효한가
    ├ conflict_validator     조건이 서로 모순되는가
    └ completeness_validator 필수값이 누락됐는가 → 되묻기 질문 생성
    ↓
컴파일                            compiler/strategy_compiler.py → ParsedStrategy
    ↓
백테스트 엔진
```

---

## 2. LLM의 책임

LLM은 사용자 입력에서 다음을 **의미로** 해석한다. 오타·구어체·문법 파괴가 있어도
글자가 아니라 뜻으로 읽는다.

- 투자 대상: 시장, 업종/테마, ETF 테마, 지정 종목
- 진입 조건 / 청산 조건
- 랭킹 선정(모멘텀 등) 기준과 기간
- 보유 종목 수, 리밸런싱 주기, 보유 기간
- 손절·익절·트레일링·MDD 한도
- 백테스트 기간, 초기 자본금, 수수료·슬리피지
- 기존 전략에 대한 수정 요청인지 신규 전략인지
- 명시되지 않은 필수 정보
- 서로 충돌하거나 해석 불가능한 조건
- 전략 요청이 아닌 입력(설명 질문·추천 요청·잡담)

동의어·정성 표현·관용구의 매핑은 **전적으로 LLM의 몫**이다.

```text
"작년에 흑자였던 종목"
  → {"factor": "fundamental.eps", "operator": ">", "value": 0,
     "source_text": "작년에 흑자였던"}

"삼성전자가 20일선 넘으면 사고 다시 밑으로 내려가면 팔아줘"
  → universe.symbols = ["005930"]        ※ 아직 미구현 — § 11-4 참조
     entry_conditions = [{"factor": "technical.ema",
                          "operator": "crosses_above",
                          "parameters": {"short_period": 20}}]
     exit_conditions  = [{"factor": "technical.ema",
                          "operator": "crosses_below",
                          "parameters": {"short_period": 20}}]

"20일선이 60일선을 골든크로스하면 매수"
  → entry_conditions = [{"factor": "technical.ma_crossover",
                         "operator": "crosses_above",
                         "value": null,
                         "parameters": {"short_period": 20, "long_period": 60}}]
```

`factor`는 반드시 Registry의 canonical ID로 출력한다
(`supported_factor_lines()`가 시스템 프롬프트에 주입한다). 목록에 없는 개념은
비슷한 지표로 조용히 대체하지 말고 `unsupported_features`에 원문 표현을 넣는다.

---

## 3. 결정론 코드(Regex)의 책임

Regex가 수행할 수 있는 작업은 **LLM 출력 문자열에 대한 다음 조작뿐**이다.

- 응답에서 최상위 JSON 오브젝트 경계 추출 (`extract_json_object`)
- 코드펜스(` ```json `)·모델 꼬리 토큰 제거
- 토큰 붕괴 구문 복구 — 올바른 JSON에는 no-op(멱등)인 기계적 치환만
  (실측 드리프트: `"operator">="value"` → `"operator":">=",`)
- 값 표기 정규화: `"10%"`·`"12배"`·`"1,000"` → `float` (`_coerce_number`)
- enum 표기 정규화: 대소문자, `"코스피"`→`"KOSPI"`, `"매월"`→`"monthly"`
- 단일 값 ↔ 배열 드리프트 교정, 0~100 스케일 confidence 정규화

이들의 공통 성질: **입력이 LLM 출력이고, 판단 근거가 표기 형식뿐이며,
의미를 새로 만들어내지 않는다.**

### Regex가 해서는 안 되는 것

- 사용자 원문(`user_input`)을 패턴 매칭하는 모든 행위
- "흑자"가 순이익 0 초과임을 판단
- "저평가주"·"우량주"가 어떤 재무 조건인지 판단
- "장기 투자"가 몇 개월인지 추론
- "많이 떨어지면 매도"의 기준을 결정
- 동의어·업종명·테마어 매핑
- 문장의 의도(신규/수정/취소/질문) 분류
- 누락된 조건을 추론해 채우기
- LLM이 생성한 조건의 **의미**를 수정하거나 삭제
- 검증 실패 시 문자열을 임의 보정

경계 판정 기준 한 줄:

> **입력이 사용자 원문이면 그것은 해석이다 → LLM.
> 입력이 LLM 출력이고 표기만 보면 결정 가능하면 그것은 정규화다 → 결정론 코드.**

### § 3-1. 예외: 대조(reconciliation)

원문을 읽되 **해석하지 않는** 검사는 허용한다. 사례는 둘이다.

**(a) 수치 반영 대조** — `validation/recall_validator.py`. 입력의 수치가 출력 어딘가에
반영됐는지 대조하고, 누락이면 LLM에 재생성을 요청한다(§ 8-1).

허용 조건은 **넷 다** 충족해야 한다.

1. 토큰의 **의미를 결정하지 않는다** — "80이 부채비율의 임계값"이라고 판단하지 않는다.
   숫자가 출력에 나타나는지만 본다(단위 환산은 표기 변환이므로 허용).
2. 출력을 **생성하거나 수정하지 않는다** — 누락된 값을 채우지 않는다.
3. 실패 시 동작이 **LLM 재생성 요청뿐**이다.
4. 재요청 예산이 유한하고, 소진 후에도 남으면 **요청을 실패시키지 않는다**
   (누락은 스키마 오류가 아니다).

재요청 결과의 취급 규칙(2026-07-27 사고로 명문화).

- **재요청은 해석을 개선만 할 수 있고 잃을 수는 없다.** 재요청 출력이 비면(초기 파스에서
  `strategy=null`, 수정 턴에서 `strategy`·`patches` 모두 없음) 그 출력을 폐기하고 재요청
  직전 해석을 유지한다 — 9B가 초기 파스 재요청에 수정 턴처럼 patches만 돌려주자 정상
  해석이 통째로 교체되고, 적용할 초안이 없어 요청 전체가 해석 실패로 끝났다. 재요청
  프롬프트는 턴 종류에 맞는 출력 형식(초기=strategy 전체, 수정=patches)을 명시한다.
- **끝까지 남은 누락은 조용히 버리지 않고 안내한다.** 인터프리터는 잔존 누락 표현을
  결과에 실어 보내고(`InterpreterResult.unreflected_numbers`), 호출부는 컴파일·결정적
  보정까지 끝난 전략으로 한 번 더 걸러(`labels_absent_from`, 되살아난 값 제외) 비차단
  notices로 알린다. 값을 만들어 채우지 않는다는 원칙(2)과 침묵 금지를 함께 지키는 방식이다.
- **되묻기는 반영으로 인정하지 않는다.** 이 검사가 보는 수치는 입력에 이미 있는 값이므로
  그것을 되묻는 것은 처리가 아니다. 검증 파이프라인은 READY 상태에서 LLM 자체 질문을
  폐기하므로(잉여·자기회의 질문 차단) 하류 채널도 없다 — 실측: "거래대금 50억 이상"을
  조건 대신 "추가해 드릴까요?" 질문으로 돌려주자 대조는 반영으로 인정하고 질문은 폐기돼
  조건이 사라졌다. `unsupported_features`만 정당한 처리 결과로 인정한다.

**(b) 패치 출처 대조(환각 게이트)** — `primary._patch_provenance_supported`(2026-07-26,
필드별 한국어 어휘 큐 스캔을 대체). 수정 패치가 발화에 근거하는지를 대조한다 —
"다른 예는 없어?"라는 후속 질문에 인터프리터가 손절·리밸런싱 패치를 지어내 전략을
임의 변형한 실측 사고(레드팀 QA 20-3)의 방어선이다. 판정 근거는 셋뿐이다.

1. **출처 인용 대조** — LLM이 `patch.source_text`로 인용한 원문 조각이 입력에 실재하는지
   표기 정규화 후 문자열 포함으로 확인한다. 어휘도 의미도 판단하지 않는다 — LLM의 출처
   주장이 실재하는지만 본다(인용은 프롬프트 규칙 10의 출력 계약).
2. **수치 대조** — 패치 값의 숫자가 입력의 숫자 표기(단위 환산 포함)와 일치하면 근거
   있음. (a)와 같은 성격이다.
3. **지정 종목 해석 가능성** — § 3-2 지식 조회(마스터에 없는 이름은 환각).

실패 시 동작은 그 패치의 **거부와 미해석 안내**다(값을 고치거나 채우지 않는다).
어느 근거로도 통과하지 못한 패치를 적용하는 것이 곧 환각 반영이므로, 거부는 출력
수정이 아니라 반영 보류다.

이 경계는 좁게 유지한다. **사용자 발화 전체를 어휘 목록으로 훑는 것은 허용하지 않는다** —
"골든크로스"가 원문 어디에 있는지 코드가 찾아 대조하려면 "어떤 표현이 그 지표인가"를
판단해야 하고, 그것이 동의어 매핑 곧 해석이다. 숫자는 표기가 곧 값이라 대조가 성립하지만
발화 전체를 대상으로 한 어휘 스캔은 그렇지 않다.

단, **범위가 다르면 성격도 다르다** — § 3-2 참조.

### § 3-2. 지식 조회(knowledge lookup)

LLM이 **"이 문자열이 무엇을 가리킨다"고 이미 판정해 넘긴 짧은 값**을 정본으로 푸는 것은
해석이 아니라 사전 조회다. 의미 판단은 LLM이 끝냈고, 코드는 매핑만 한다.

```text
❌ 해석    : 원문 "마운자로 관련주에 투자하는 전략"을 코드가 훑어 '마운자로'를 찾아낸다
✅ 지식조회 : LLM이 universe.sectors=["마운자로"]로 넘긴 값을 코드가 '바이오/제약'으로 푼다
```

이 계층이 필요한 이유는 **LLM이 대체할 수 없기 때문**이다. 4B든 9B든 '마운자로'가 어떤
상장사와 연결되는지 모른다. 지표명을 canonical ID로 푸는 `indicator_registry`와 정확히 같은
성격이며, 다음이 모두 여기 속한다.

| 대상 | 모듈 | 입력(LLM 산출) → 출력 |
|---|---|---|
| 지표명 | `registry/indicator_registry.py` | "골든크로스" → `technical.ma_crossover` |
| 업종·테마 | `registry/universe_resolver.py` | "2차전지" → "이차전지" |
| 개념·테마 | `engine/knowledge_graph.py` | "마운자로" → 바이오/제약, "HBM 장비 회사" → 반도체 |
| 테마 상장사 | `engine/concept_universe.py` | 개념 노드 → 심볼 + 근거 점수 |
| 미지 용어 학습 | `engine/term_grounding.py` | 용어 → 검색 → 노드 |
| 종목명·코드 | `stock_analysis/symbol_resolver.py` | "삼성전자" → `005930` |

**입력 계약: 이 계층은 `term`을 받는다. 원문(`text`)을 받지 않는다.**
LLM이 넘긴 짧은 값 안에서 정본을 식별하는 것(예: "HBM 장비 회사"에서 HBM 개념 인식)은
범위가 그 값으로 한정되므로 허용한다 — 발화 전체 스캔과 구분되는 지점이 이 **범위**다.

해석하지 못한 값은 조용히 버리지 않는다. 학습(검색 그라운딩)을 시도하고, 그래도 실패하면
되묻기·미지원 안내로 사용자에게 알린다(§ 5).

---

## 4. 출력 계약

LLM은 JSON 오브젝트 **하나만** 출력한다. 설명·마크다운·주석·자연어 문장을 섞지 않는다.

```jsonc
{
  "schema_version": "1.0",
  "intent": "CREATE_STRATEGY",
  "strategy": {
    "name": null,
    "universe": {"markets": ["KOSPI", "KOSDAQ"], "sectors": [], "etf_theme": null},
    "entry_conditions": [
      {"factor": "fundamental.per", "operator": "<=", "value": 10,
       "unit": "ratio", "source_text": "PER이 10보다 낮은"},
      {"factor": "technical.ma_crossover", "operator": "crosses_above", "value": null,
       "parameters": {"short_period": 1, "long_period": 20},
       "source_text": "20일선을 상향 돌파하면"}
    ],
    "exit_conditions": [],
    "ranking": [],
    "portfolio": {"selection_count": null, "weighting": null,
                  "rebalance_frequency": null, "hold_period_days": null},
    "risk_management": {"stop_loss": null, "take_profit": null,
                        "trailing_stop": null, "max_mdd_limit": null},
    "backtest": {"period": null, "start_date": null, "end_date": null,
                 "initial_capital": null, "fee_rate": null, "slippage_rate": null}
  },
  "patches": [],
  "unsupported_features": [],
  "clarification_questions": [],
  "confidence": 0.9
}
```

> `status`·`missing_fields`·`assumptions`는 **LLM 출력 계약이 아니다**(2026-07-30 제거).
> 셋 다 파이프라인이 읽지 않는 죽은 채널이었다 — 상태는 `validation/pipeline.py`가
> 오류·누락으로 재판정하고(`report.status`), 누락 필드는 `validate_completeness`가
> 결정론으로 산출하며, `assumptions`는 어디에서도 소비되지 않는다(recall 검사도 제외).
> `StrategyIntent` 모델에는 기본값으로 남아 있어 구버전 출력도 그대로 검증된다.
> `clarification_questions`는 살아 있다 — 수정·되묻기 답변 경로(`primary.py`)가 읽는다.

> **형태에 없는 키는 규칙 문장으로 이길 수 없다.** 조건 예시에 `parameters`가 빠져 있으면
> 9B는 규칙 5-3의 상세한 매핑을 무시하고 `parameters: null`을 낸다 — 사용자가 말한 기간
> ("20일선")이 사라져 시스템이 되묻는 사고로 이어진다(2026-07-30, `etf_theme` 2026-07-27과
> 같은 실패 방식). 그래서 형태에 크로스오버 조건을 `parameters`와 함께 싣는다.
> 새 필드를 계약에 추가할 때는 규칙 문장만 쓰지 말고 **형태에도 반드시 넣는다**.

### intent (하나 선택)

`CREATE_STRATEGY` / `MODIFY_STRATEGY` / `EXPLAIN_INDICATOR` / `RUN_BACKTEST` /
`COMPARE_STRATEGIES` / `CLARIFY_STRATEGY` / `CONFIRM_RECOMMENDATION` /
`CANCEL_OPERATION` / `UNSUPPORTED_REQUEST` / `NON_STRATEGY_REQUEST`

### status

`READY` / `NEEDS_CLARIFICATION` / `UNSUPPORTED` / `REJECTED`

### 허용 연산자

- 비교: `<` `<=` `>` `>=`
- 이벤트: `crosses_above` `crosses_below` (이때 `value`는 null, 기간은 `parameters`)

허용 연산자는 지표마다 다르며 `IndicatorSpec.allowed_operators`가 최종 판정한다.

### 조건 결합

같은 역할(진입/청산) 안의 조건들은 **AND**로 결합된다(엔진 의미론).
OR 결합은 현재 계약에 없다 — OR가 필요한 요청은 `unsupported_features`에 넣는다.

---

## 5. 값을 만들어내지 않는다

사용자가 말하지 않은 값을 임의로 확정하지 않는다. 가능한 동작은 셋뿐이다.

1. **질문한다** — LLM은 값을 `null`로 두기만 한다. 누락 필드 산출과 되묻기 질문 생성은
   결정론 검증 계층(`validate_completeness`)의 책임이다(LLM이 낸 `missing_fields`는
   읽지 않는다 — § 4 참고).
2. **추천값을 제시한다** — `recommended_value` + `requires_confirmation=true`.
   확정값(`value`)에는 넣지 않는다. `value_source`는 `SYSTEM_RECOMMENDED`.
3. **사용자가 자동 설정을 명시 허용한 경우에만** 기본값을 쓴다.

```text
"많이 떨어지면 팔아줘"
  → risk_management.stop_loss = null            (LLM 출력)
  → missing_fields = ["strategy.risk_management.stop_loss"]   (검증 계층 산출)
     clarification_questions = [{"field": "strategy.risk_management.stop_loss",
                                 "question": "몇 % 하락 시 손절할까요?",
                                 "recommended_value": 10}]
     report.status = "NEEDS_CLARIFICATION"

"영업이익률이 높은 기업"
  → entry_conditions = [{"factor": "fundamental.operating_margin",
                         "operator": ">=", "value": null,
                         "recommended_value": 10, "requires_confirmation": true,
                         "source_text": "영업이익률이 높은"}]
```

방향만 있고 수치가 없는 표현("RSI가 낮은", "부채비율이 높은")도 `value=null`이다.
반대로 수치가 명시된 근사 표현("8종목 정도", "10개쯤")은 그 수치로 확정하고
질문하지 않는다.

---

## 6. 규제 안전 (유사투자자문업 회피)

이 계약은 [CLAUDE.md](../CLAUDE.md)의 규제 원칙에 종속된다.

- 종목 추천·전략 추천·섹터 추천·시장 전망·매매 시점 제안 요청은
  `intent="UNSUPPORTED_REQUEST"`로 분류한다. 조건으로 변환하지 않는다.
- 나이·자산 규모·소득·위험 성향 기반 맞춤 제안 요청도 동일하다.
- `clarification_questions`의 `recommended_value`는 **파라미터 시작값 제안**이지
  투자 판단이 아니다. 질문 문구에 우열·전망·권유 표현을 쓰지 않는다.
  - ✅ "몇 % 하락 시 손절할까요?"
  - ❌ "손절은 10%를 권장합니다"
- "좋은 주식을 사줘"처럼 조건 없는 요청은 추천으로 답하지 않고
  `NEEDS_CLARIFICATION`(진입 조건 질문)으로 되묻는다.

---

## 7. 수정 요청

현재 전략 초안(`draft`)이 함께 주어진 경우에만 `MODIFY_STRATEGY`를 선택한다.
초안이 없으면 `CREATE_STRATEGY`다.

수정은 `strategy` 전체 재출력이 아니라 **`patches`(JSON Patch 부분집합)로만**
표현한다. 언급되지 않은 필드는 패치하지 않는다.

```text
"종목 수를 10개로 바꿔줘"
  → patches = [{"op": "replace", "path": "/portfolio/selection_count", "value": 10}]

"PER 조건은 빼줘"           (초안 entry_conditions[0]이 PER)
  → patches = [{"op": "remove", "path": "/entry_conditions/0"}]

"PBR 1 이하도 추가해줘"      (초안에 PBR 없음)
  → patches = [{"op": "add", "path": "/entry_conditions/-",
                "value": {"factor": "fundamental.pbr", "operator": "<=", "value": 1}}]
```

- `op`는 `replace` / `add` / `remove`만 허용한다.
- 배열 전체 remove(`/entry_conditions`)는 금지 — 언급하지 않은 조건까지 삭제된다.
- 없는 인덱스에 `replace` 금지 — 새 조건은 `add`로 배열 끝(`/-`)에 붙인다.
- **값 없는 변경 요청**("시장 바꿔줘", "손절 조정해줘")은 패치를 만들지 말고
  `NEEDS_CLARIFICATION`으로 되묻는다.
- 초안이 있어도 "PBR이 뭐야?" 같은 용어 질문은 수정이 아니라 `EXPLAIN_INDICATOR`다.

패치 경로가 현재 전략에 실제로 존재하는지는 LLM이 아니라
`conversation/patch_applier.py`(상태 관리 계층)가 검증한다.

---

## 8. 검증 실패 처리

### 8-1. 스키마 검증 실패 → LLM 재생성

결정론 코드는 실패한 출력을 **의미적으로 수정하지 않는다**. 원래 입력·잘못된 출력·
Pydantic 오류 원문만 담아 재생성을 요청한다
([output_repair.build_repair_prompt](../backend/strategy_conversation/interpreter/output_repair.py)).

```text
LLM 출력
    ↓
extract_json_object / Pydantic 검증 실패
    ↓
build_repair_prompt(user_input, bad_output, error_message, draft)
    ↓
LLM 재생성
    ↓
재검증  (최대 MAX_REPAIR_ATTEMPTS회, 기본 1 — 무한 재시도 금지)
    ↓
그래도 실패 → InterpreterError
```

`InterpreterError`는 삼키지 않는다. 상위(`primary.py`)가 `None`을 반환하면 호출부가
기존 경로로 폴백하며, 이때 **폴백은 자연어 재해석이 아니라 실패 보고여야 한다.**

### 8-2. 도메인 검증 실패 → 사용자에게 알림

`validation/pipeline.py`는 문제를 발견해도 조용히 고치지 않는다.

- 미지원 지표: `unsupported_features`에 넣고, 대체 후보가 있으면
  `suggested_fixes`로 **제안만** 한다(조용한 대체 금지).
- 값 범위 위반: `errors`에 기록하고 임의로 clamp하지 않는다.
  (`enforce_strategy_minimums` 같은 명시적 하한선 정책은 예외 — `notices`로 통지)
- 조건 충돌: 임의 수정 없이 `errors`/`warnings`로 알린다.
- 필수값 누락: `clarification_questions`를 생성한다.

유일하게 허용되는 결정론 변경은 **canonical 정규화**다
(`capability_validator`가 factor를 canonical ID로, 주기를 엔진 enum으로).

---

## 9. 금지 사항 (코드 리뷰 체크리스트)

아래 중 하나라도 해당하면 그 코드는 이 계약을 위반한다.

- [ ] 결정론 함수가 `user_input`/`prompt`를 인자로 받아 정규식을 적용한다
- [ ] 한국어 지표·업종·테마 어휘를 하드코딩한 정규식이 있다
- [ ] LLM 출력을 사용자 원문 기준으로 덮어쓰거나 보강한다
- [ ] 사용자 원문에서 의도(신규/수정/취소/질문)를 정규식으로 분류한다
- [ ] 검증 실패 시 LLM에 되돌리지 않고 코드가 값을 채운다
- [ ] 누락값을 질문 없이 기본값으로 확정한다
- [ ] LLM이 Registry에 없는 factor·연산자·블록을 생성한다
- [ ] 구조화 출력에 자연어 설명이 섞인다

허용되는 유일한 정규식 대상: **LLM 출력 문자열**, 그리고 판단 근거가 **표기 형식뿐**일 것.

---

## 10. 역할 분담 요약

| 레이어 | 파일 | 책임 |
|---|---|---|
| **LLM Interpreter** | `interpreter/llm_strategy_interpreter.py`, `prompts.py` | 자연어 이해, 의도 분류, 동의어 처리, 조건 변환, 수정 인식, 누락 탐지, StrategyIntent 생성 |
| **형식 정규화** | `interpreter/output_repair.py`, `models.py` field_validator | JSON 경계 추출, 코드펜스·꼬리 토큰 제거, 토큰 드리프트 복구, 값·enum 표기 정규화 |
| **Schema Validator** | `interpreter/models.py` (Pydantic) | 필드 타입·필수 필드·허용 enum·구조 검증 |
| **Capability / Domain Validator** | `validation/`, `registry/` | 지표 지원 여부, canonical 매핑, 값 범위·단위, 유니버스 호환성(ETF↔재무지표), 조건 충돌, 완결성·되묻기 생성 |
| **State Layer** | `conversation/patch_applier.py`, `strategy_draft.py` | 패치 대상 존재 검증, 초안 상태 소유 |
| **Compiler** | `compiler/strategy_compiler.py` | StrategyIntent → ParsedStrategy(엔진 DSL) |

---

## 11. 현행 코드와의 격차

이 계약은 `strategy_conversation/` 파이프라인에는 이미 대체로 성립하지만,
전체 시스템은 아직 충족하지 않는다. 알려진 위반은 다음과 같다(2026-07-26 기준).

1. **`engine/nl_parser.py` (5,444줄, 원문 대상 정규식 ~159곳)**
   `_parse_rule_based_strategy` / `_extract_sector` / `_extract_technical_signals` /
   `_extract_fundamental_filters` / `_assign_sl_tp` 등이 사용자 원문을 직접 해석한다.
   § 3·§ 9 정면 위반.

2. ~~**`primary.py`의 결정론 재해석**~~ — **해소(2026-07-26)**
   `STRATEGY_PROMPT_OVERRIDE_MODE` 기본값을 `off`로 전환해, 인터프리터 경로에서
   `_apply_prompt_overrides`가 더 이상 LLM 해석을 덮어쓰지 않는다(§ 11-2).
   함수 자체는 남아 있다 — 레거시 `nl_parser.parse()`가 아직 쓰므로 삭제는 1c 이후다.
   롤백은 `STRATEGY_PROMPT_OVERRIDE_MODE=on`이며, 그 경로가 썩지 않도록
   `test_strategy_conversation.py`에 롤백 가드 테스트를 둔다.
   ~~남은 항목: `_fill_deterministic_condition_params(intent, user_input)`도 원문을 읽는다.~~
   → **해소(2026-07-26, § 11-4)**: 조건 `source_text`(LLM 인용)만 읽는다 — 원문 폴백 제거.

3. **`intent/strategy_builder.py` (원문 대상 정규식 ~108곳)** — **C안으로 재정의(2026-07-26 사용자 결정)**
   빌더 단계 진행·삭제·정정 판정이 전부 결정적 정규식이다.
   사용자 결정(C안): **칩 클릭·현재 질문에 대한 값 답변("10프로")의 결정적 처리는
   제한된 답의 형식 정규화로 보고 목표 상태에 포함한다(위반 아님)** — 자유 서술
   해석만 LLM으로 점진 이관한다.
   **Phase 1 완료(2026-07-26)**: `intent/builder_interpreter.py` — 결정적 레이어가
   아무것도 해석하지 못한 자유 서술을 LLM이 제한된 ops JSON(set/remove/reopen)으로
   해석 → 결정적 검증(필드 화이트리스트·enum·값 범위·수치 대조·source_text 인용
   실재·삭제=채워진 필드만) → 기존 patch 계약 적용. LLM 실패·검증 전탈락은 기존
   미인식 안내 유지(원문 재해석 폴백 없음). **미인식 표현에 regex를 추가하는 것은
   금지 — 긴 꼬리의 해석 책임은 이 레인에 있다.** 롤백=`BUILDER_FREETEXT_MODE=deterministic`.
   잔여(Phase 2, 후속): 기존 결정적 자유 서술 큐 레이어(삭제·정정·SET-ahead 등
   FR-SA-002e)의 해석 권한 역전 — LLM 레인 실사용·QA 축적 후 판정.

4. ~~**StrategyIntent에 지정 종목 필드 부재**~~ — **해소(2026-07-26, 1a+4)**
   `UniverseSpec.symbols` 신설 + `registry/universe_resolver.py`가 LLM이 뽑은
   업종/종목 표현을 정본 값으로 해석하고, 컴파일러가 `sector`·`target_symbols`에
   배선한다. 단 `_apply_prompt_overrides`가 아직 원문 정규식으로 같은 필드를
   덮어쓰므로(2번), 원문 정규식이 침묵할 때만 LLM 경로가 확정한다.

5. **모드 게이팅**
   ~~`.env`의 `STRATEGY_INTERPRETER_MODE=primary`는 dev 전용이며, 기본값은 `off`~~
   → **해소(2026-07-26, 로드맵 5번)**: 코드 기본값을 `primary`로 승격. 명시적 env가
   계속 우선하므로 prod는 `.env`의 `shadow`가 유지된다(prod primary 전환은 Modal
   콜드스타트·keep-warm 검토와 함께 별도 결정). 롤백=env를 `off`로.

### § 11-2. 보정 제거(2+1b) — 2026-07-26 전환 완료

`scripts/qa_prompt_override_ab.py`로 103케이스(LLM이 실제로 개입하는 복잡 전략)를
ON/OFF 통과시킨 결과. 기준은 `qa_complex_llm_parse.py`의 `expect`.

| 회차 | 조치 | ON | OFF |
|---|---|---|---|
| v2 | 미러 청산 가드 수정 후 | 87/103 | 36/103 |
| v3 | + 표준값 파라미터 조건 보존, 오실레이터 연산자 규칙 | 87/103 | 47/103 |
| v4 | + 경계 연산자·가격 vs MA 인코딩·조건 누락 방지 규칙 | 85/103 | 51/103 |
| v5 | + **수치 반영 대조**(§ 3-1 recall_validator) | 87/103 | 58/103 |

9B 승격 후 회차(94~92개 공통 채점 기준):

| 회차 | 조치 | ON | OFF |
|---|---|---|---|
| v6 | 인터프리터 9B 승격 | 83 | 57 |
| v7 | Registry `notes` 주입, `assumptions` 우회 차단 | 87 | 62 |
| v8 | `ema` 노트 교정, JSON 큰따옴표 규칙 | 86 | **64** |
| v9 | AI 노트 추가 → **후퇴**, 되돌림 | 84 | 62 |

**결론: 기본값을 `off`로 전환한다(2026-07-26).** 근거는 점수가 아니라 두 가지다.

1. **사용자 결정** — "어떤 경우라도 regex가 자연어를 해석/이해 하려는 시도는 없어야 한다."
   품질은 인터프리터·프롬프트·검증 레이어로 해결하고, 원문 정규식으로 되돌리지 않는다.
2. **A/B를 전환 기준으로 쓸 수 없다** — 잔여 26건 중 7건이 하니스 `expect`가 **정규식의
   인코딩 관례**를 기대값으로 담은 것이다(예: '주가가 20일선 위' → `ma_crossover(short=1,
   long=20)`). LLM이 `ema(mode=above)`로 낸 것이 틀린 게 아니다. 즉 ON 점수는 '정답'이
   아니라 '정규식과 일치하는 정도'이며, OFF를 그 점수까지 올리는 것은 정규식 흉내를
   잘 내게 만드는 일이다. **이후 개선은 실사용에서 나온 케이스로 진행한다.**

또한 모델 승격(4B→9B)은 OFF를 58→57로 **움직이지 못했다** — 잔여 격차는 모델 recall이
아니라 계약 정밀도 문제였고, 실제로 그 뒤 계약 결함을 닫자 57→64로 올랐다.
프롬프트 규칙 추가는 v9에서 순감으로 돌아서 한계 수익이 소진됐다.

**보정이 하던 일의 대체**

| 보정이 하던 일 | 대체 |
|---|---|
| 지정 종목 원문 추출 | LLM `universe.symbols` → `universe_resolver` (§ 3-2) |
| 명시 날짜 덮어쓰기 | LLM `backtest.start_date/end_date` (프롬프트 규칙 12 + 오늘 날짜 주입) |
| 누락 수치 채우기 | 수치 반영 대조 → LLM 재생성 (§ 3-1, 발동분 잔존 0건) |
| 업종·테마 정본화 | LLM `universe.sectors` → `universe_resolver`(사전→지식그래프) |
| 체결 시점 | `BacktestSpec.execution_timing` 신설 |

**전환 중 막은 구멍**: `/universe/symbols` 패치가 환각 게이트의 키워드 큐에 걸려
거부되고 있었다(FR-STR-068 회귀 지점). 종목명은 열린 집합이라 큐로 열거할 수 없고 원문
스캔은 § 3-1 위반이므로, **해석 가능성**으로 거르도록 바꿨다(§ 3-2) — 마스터에 없는
이름을 LLM이 지어내면 거부, 실재 종목이면 통과.

**막은 구멍 2 — symbols 패치 값의 조건형 객체 드리프트(2026-07-26 실측 사고)**:
"제주반도체도 추가해줘"에 인터프리터가 의미는 정확히 해석하고도(`add /universe/symbols/-`)
값을 조건형 객체(`{"factor":null,…,"source_text":"제주반도 semiconductor"}`)로 냈고,
이 항목이 3중으로 **조용히 소실**됐다 — ① `UniverseSpec._coerce_str_list`가 비문자열을
무언 드롭, ② `resolve_symbols`가 비문자열을 무언 skip(자기 docstring 위반),
③ 컴파일러가 unresolved를 로그로만 남기고 사용자에게 미노출. 결과: '변경 없음' 재렌더링.
수정(전부 LLM 출력 정규화·형식 검증 — § 3 허용 범위): 프롬프트 규칙 10-1(symbols 패치
값=사용자 표기 문자열 그대로, 객체·번역 금지, PROMPT_VERSION 1.6) + 스키마 정규화가
객체의 `source_text` 인용을 구제 + resolver가 비문자열을 unresolved로 보고 + 검증
파이프라인이 미해석 종목 표현을 warning(→ notices 채널)으로 노출. 회귀:
`test_symbol_add_patch_compiles_to_target_union` 외 4건. 이 계열 사고의 교훈:
**미해석 표현의 조용한 소실 지점(스키마 드롭·resolver skip·로그-only)이 곧 계약 위반이다.**

**막은 구멍 3 — 수정 레거시 폴백 제거(2026-07-26 실측 사고)**:
"제주반도체 종목도 추가해줘"가 라운드트립 가드 오폭(기간 None 신호 ↔ Registry 표준값
채움 불일치)으로 레거시 수정 레인에 떨어졌고, 레거시 결정론은 추가/교체를 구분하지
않으므로(합집합 의미론=LLM 소유) 테마 유니버스가 언급 종목 하나로 교체됐다. 수정:
① `compiler/engine_defaults.py::materialize_engine_defaults` — None 파라미터를 엔진
실효값(signals.py SOT)으로 명시 채워 의미 불변으로 라운드트립 성립(Registry 표준값과
엔진 기본값의 이원화가 원인 — ma 20/60 vs 5/20). ② **llm_first에서 레거시 수정 폴백
자체를 제거(사용자 지시)** — 인터프리터가 처리 못 한 수정은 원문 regex 해석 레인으로
떨어지지 않고 전략 보존+되묻기(FR-STR-019h)로 끝난다. LLM 연결 장애는 되묻기로 위장하지
않고 503 경로로 던진다. 롤백=`STRATEGY_MODIFY_INTERPRETER_MODE=fast_path_first`.
§ 11 격차의 '레거시 수정 레인 이관'이 llm_first 기준으로 사실상 완료됐다(레거시 코드는
롤백 모드 전용으로 존치). 회귀: `test_modify_roundtrip_migration.py` 7건.

**롤백**: `STRATEGY_PROMPT_OVERRIDE_MODE=on`. 탈출구가 조용히 썩지 않도록
`test_strategy_conversation.py`에 롤백 가드 테스트를 유지한다.

**프로덕션 영향 없음**: 당시 `STRATEGY_INTERPRETER_MODE` 코드 기본값이 `off`라
prod는 레거시 파서 경로였다. 이번 전환은 dev(primary)에서 즉시 체감된다.
(기본값은 2026-07-26 로드맵 5번에서 `primary`로 승격 — prod는 명시적 `shadow` env가
계속 우선한다.)

**부수 성과** — 보정이 가리고 있던 결함 4종을 찾아 양쪽 경로 모두에서 수정했다
(미러 청산 가드 오폭, 표준값 파라미터 조건 드롭, `execution_timing` 스키마 공백,
오실레이터 연산자 미스매치). 원문 정규식이 이것들을 덮어 쓰고 있어 드러나지 않았다.

### § 11-3. KG 입력 계약 전환 (1c′) — 2026-07-26 결정

지식그래프·용어 그라운딩의 **모든 공개 진입점이 원문(`text`)을 받는다**. `find_concepts(text)`가
어휘 인덱스로 발화 전체를 훑는 구조라 § 3-1이 금지하는 발화 스캔에 해당한다. KG 자체는
§ 3-2의 정당한 지식 조회 계층이므로 **제거가 아니라 입력 계약을 뒤집는다**.

**전환 대상 (text → term)**
`knowledge_graph`: `resolve_sector_from_text` · `theme_listed_companies` ·
`theme_backtest_companies` · `related_universe` · `KnowledgeGraph.find_concepts`
`term_grounding`: `resolve_sector` · `_scan_lexicon` · `lexicon_entry` · `learn_sector_term`

**폐기 대상 (원문 스캔 트리거)**
`nl_parser`: `_KG_SECTOR_CUE_RE` · `_THEME_UNIVERSE_CUE_RE` · `apply_theme_universe(parsed, user_prompt)` ·
`detect_unresolved_sector_clarification` / `intent/strategy_builder.py`의 `theme_backtest_companies` 호출부

**유니버스 해석 위치 이동**: 현재 컴파일러(`_build_parsed`)에서 수행하나, 미해결 테마가
되묻기를 만들어야 하므로 검증 단계로 옮긴다 — `clarification_questions` 표준 채널을 타야 한다.

**선행 조건**: 1c(구 파서 폴백 차단). 폐기 대상 함수를 `nl_parser`가 아직 쓰고 있어,
폴백이 살아 있는 동안 지우면 그 경로가 깨진다.

**실측 근거(2026-07-26, 9B)**: 프롬프트 규칙 6-0-2("모르는 고유명사도 테마 맥락이면 sectors에,
규칙 3보다 우선") 추가 전 테마 추출 1/3 → 추가 후 **3/3**. 리졸버가 그 용어를 실제로 푼다
(마운자로→바이오/제약, HBM 장비 회사→반도체, 2차전지→이차전지). 미해결은 복합 테마구
가드('2차전지 소부장')와 검색 실패 테마('리센즈')로, 둘 다 의도된 동작이다.

**전환 실행(2026-07-26) — primary 초기 파스 레인 완료**:
`primary._resolve_sector_terms_term_in` — 컴파일 후 리졸버가 못 푼 `universe.sectors`
표현만 입력으로 받아 ① KG 테마 상장사(`apply_theme_companies`, `apply_theme_universe`에서
큐 게이트 없이 분리한 코어) 자동 적용 ② 검색 그라운딩 학습(`ground_term` 도구,
`_ground_sector_term` — 원문 큐 게이트 없음: '미해결 표현' 판정은 리졸버가 이미 내림)
후 테마 재조회→섹터 병합 ③ 끝까지 미해결이면 되묻기(검색 소진 테마는 THEME_NOT_FOUND
종결 안내), `clarification_priority=sector_unresolved` 유지. 이에 따라 primary 초기
파스는 `_build_parse_result`의 원문 스캔(`apply_theme_universe`·
`detect_unresolved_sector_clarification`, `scan_prompt_for_sector=False`)과 파싱 전
어휘집 학습(`_learn_unknown_sector_term`)을 타지 않는다. 해석 실패 보고에도 원문 테마
스캔을 적용하지 않는다(실패가 전략처럼 위장 방지). 회귀:
`tests/test_sector_term_in_chain.py`.

**입력 스냅샷 계약(2026-07-26 회귀 수정)**: 체인 입력은 capability validator **검증 전**의
`universe.sectors` 스냅샷이다. 검증기는 정본 목록 밖 섹터 표현을 미지원으로 판정하며
목록에서 제거하므로, 검증 후 값을 읽으면 미지 테마('이재명 관련주')가 체인에 도달하지
못하고 '지원되지 않아 반영되지 않았어요' 안내로 조용히 소실된다(테마 유니버스 전면 불능).
ETF 유니버스는 예외 — 검증기가 테마를 `etf_theme`로 승격하므로 체인을 생략한다. 체인이
표현을 전부 해석했으면 검증기의 해당 미지원 항목도 프루닝한다(반영된 전략과 안내 모순 방지).
회귀: `test_strategy_conversation.py::test_primary_unknown_theme_sector_reaches_term_in_chain`.

**잔여(의도적)**: 폐기 대상 함수·큐 정규식은 레거시 레인이 off/shadow의 기본 경로인
동안 유지(1d 재정의 — 삭제 아님·사용 중지, 코드는 롤백용 보존). 수정(modify) 레인·빌더(`strategy_builder`)의 원문 학습·테마
조회는 단계 3에서 같은 패턴으로 이관.

### § 11-4. `strategy_conversation/` 잔여 원문 해석 제거 — 2026-07-26 완료

계약 수립 후 재감사에서 새 파이프라인 안에 남아 있던 원문 정규식/어휘 판정 5곳을
LLM 해석(또는 § 3-1 대조 / § 3-2 지식 조회)으로 이관했다.

| 지점 | 이전(위반) | 이후 |
|---|---|---|
| 패치 환각 게이트 | `_PATCH_FIELD_CUES` 필드별 한국어 어휘 목록으로 발화 전체 스캔 | 출처 대조(§ 3-1 (b)): `PatchOp.source_text` 인용 실재 + 수치 대조 + 종목 해석 가능성. 프롬프트 규칙 10이 패치별 인용을 계약화(PROMPT_VERSION 1.5) |
| 질문 여부 판정 | `is_definition_question`·`is_default_question`·질문 정규식(`[?？]$` 등)으로 원문 의도 분류 | 인터프리터 LLM 라벨(`EXPLAIN_INDICATOR`)만 신뢰. 라벨 드리프트는 프롬프트 규칙 10 소관 |
| 조건 교정(`_fill_deterministic_condition_params`) | breakout 기간·거래량 급증 재분류에 원문 폴백 | 조건 `source_text`(LLM 인용)만 입력(§ 3-2 범위 한정). 인용이 없으면 되묻기 |
| ETF 테마 | 컴파일러가 LLM `etf_theme` 공백 시 `extract_etf_theme(user_input)` 원문 추출 폴백 | LLM `universe.etf_theme`만(프롬프트 규칙 6-1). 공백이면 테마 제한 없음 |
| 수정 fast-path 상담 | llm_first에서도 패치 부재·전량 거부 시 `_modify_rule_based`(원문 정규식)에 처리 가능 여부를 상담 | llm_first는 원문 파서를 상담하지 않는다 — LLM의 되묻기/설명이 그대로 전달되고, 미해석은 None 폴백(레거시 계층 처리 여부는 호출부 소관). 롤백 모드(`STRATEGY_MODIFY_INTERPRETER_MODE=fast_path_first`)에만 잔존 |

의도적으로 남긴 것: 롤백 knob 2종(`STRATEGY_PROMPT_OVERRIDE_MODE=on`,
`fast_path_first`)과 레거시 폴백 계층(§ 11 격차 1·3 — 1c에서 차단).

### § 11-5. 정규식 폴백 차단 (1c) — 2026-07-26 완료

"폴백은 자연어 재해석이 아니라 실패 보고"(§ 8-1)를 초기 파스 레인까지 적용해,
LLM 실패 시 원문 정규식이 재해석자로 나서던 폴백을 모두 차단했다.

| 지점 | 이전(위반) | 이후 |
|---|---|---|
| 초기 파스 인터프리터 실패 | primary 모드에서 `run_primary_parse`가 None이면 `parser.parse()`(규칙 하이브리드)로 폴백 — LLM 실패가 원문 정규식 재해석으로 이어짐 | 실패 보고(`interpretation_failed` 되묻기)로 종결. 규칙 하이브리드는 primary가 꺼진 환경(off/shadow)의 기본 경로로만 동작 |
| 인터프리터 전송 오류 | 연결 장애도 None으로 삼켜 규칙 파서 폴백 → LLM 폴백 재시도 끝에 503 | None으로 위장하지 않고 그대로 던진다 — main의 503 경로(`_is_llm_connection_error`)가 처리(수정 레인 llm_first와 동일 계약) |
| LLM 구조화 출력 불량 | `parse()`가 ValidationError/JSON 부재 시 `_build_fallback_strategy`(원문 정규식 전체 추출)로 전략을 조립 — LLM 해석 폐기+조용한 오해석의 근원 | 예외를 그대로 올려 호출부가 실패 보고(되묻기) 또는 503으로 변환. `_build_fallback_strategy` 함수 삭제(부활 방지 테스트 포함) |

수정(modify) 레인의 동형 차단은 § 11-4 "막은 구멍 3"에서 선완료. 회귀 가드:
`tests/test_parse_fallback_blocked.py`.

의도적으로 남긴 것(폴백이 아니라 primary/롤백):
- primary가 꺼진 환경(off/shadow)의 규칙 하이브리드 — 기본 경로(5번 승격·1d 이관 전까지)
- 롤백 knob 2종과 그 안의 결정적 원문 해석(`fast_path_first`의 `_modify_rule_based` 선점,
  `STRATEGY_PROMPT_OVERRIDE_MODE=on`의 `_apply_prompt_overrides`)
- 룰 파스 LLM 검증 미가용 시 룰 파스 원본 유지(graceful degrade) — 규칙이 primary인
  경로의 검증 강등이지 정규식 재해석 폴백이 아님

### § 11-6. 프론트 되묻기 게이트의 원문 정규식 폐지 (2026-07-29 완료)

계약은 백엔드만의 것이 아니다. 프론트 되묻기 게이트(`app/analytics/new/backtestReadiness.ts`)가
"사용자가 이 설정을 말했나"를 판정하려고 원문을 정규식으로 재분석하고 있었다(`hasExplicit*` 5종).
이는 § 판정 기준상 명백한 해석이며, 실제로 **양방향으로** 사고를 냈다.

| 방향 | 사고 | 결과 |
|---|---|---|
| 미탐 | '최대 보유 종목은 10개' — 조사·'수'가 낀 어순 | 진행률 미체크 + 요약 카드 누락 |
| 오탐 | '거래대금 20억 원' — 금액 표기를 초기 자본 명시로 오인 | 초기 자본 되묻기를 통째로 삼킴 |

정규식 어휘를 넓히는 보정은 같은 사고를 되풀이할 뿐이라(§ 3 금지) 채널 자체를 교체했다 —
판정은 인터프리터 LLM의 구조화 출력에서만 나오고(`response/provenance.py`), 프론트는 그 결과를
읽기만 한다(`explicit_fields` / `previous_explicit_fields` 무상태 에코).

| 지점 | 이전(위반) | 이후 |
|---|---|---|
| 되묻기 게이트 판정 | 프론트가 사용자 원문을 정규식 5종으로 스캔 | 백엔드 `explicit_fields`(LLM StrategySpec의 필드 유무)만 |
| 유니버스 기본값 | LLM이 `markets=["KOSPI200"]`을 채워 미언급과 구분 불가 | LLM은 비워 두고 컴파일러가 기본값 부여 — provenance 보존(프롬프트 v2.1) |
| 진행률·요약 표시 | `prompt` 문자열을 넘겨 표시 여부 판정 | `explicitFields` 목록으로 판정 |

LLM 레인 밖의 답변에는 그 레인의 기록을 쓴다(원문 재해석 아님) — 칩 답변은 프론트가 그 필드를
기록하고, 빌더 레인은 슬롯 자체가 답변 기록이다. 빌더 슬롯이 없는 기간·초기 자본은 빌더 단독
진입 시 출처가 없으므로 **묻는다**(기본값 조용한 확정 금지). 상세는 SRS FR-STR-019k.

### § 11-7. 종목명 오타 되묻기의 term-in 이관 (2026-07-29 완료)

섹터/테마는 § 11-3에서 term-in으로 옮겼는데 **종목명만 원문 스캔으로 남아 있었다**.
`detect_symbol_typo_clarification`이 원문의 3자 이상 한글 토큰을 전부 종목 마스터에
자모 근접 매칭했고, 실측에서 이렇게 터졌다.

| 원문 어절 | 오탐된 종목 |
|---|---|
| "20일 고점을 **넘기는** 날 매수" | 삼기 |
| "다시 박스 **안으로** 내려오면 매도" | 알트 |

칩은 원문에서 그 토큰만 치환한 재제출 프롬프트라, 사용자 문장이 통째로 오염된 채
선택지로 제시됐다("…20일 고점을 **삼기** 날 매수하고…").

| 지점 | 이전(위반) | 이후 |
|---|---|---|
| 오타 후보 수집 | 원문 전체를 토큰으로 쪼개 마스터에 근접 매칭 | LLM이 `universe.symbols`로 뽑았는데 리졸버가 못 푼 표현만(`terms=` 인자) |
| 레인 배치 | 모든 레인이 원문 스캔 | primary는 term-in(`primary._symbol_typo_term_in`), 원문 스캔은 레거시 레인 전용(`scan_prompt_for_sector`) |
| 칩 생성 | 원문 치환 결과를 무조건 사용 | 원문에 그 토큰이 없으면(LLM이 표기를 다듬은 경우) 종목명만 — 치환 없는 원문을 칩으로 내면 같은 질문이 반복된다 |

term-in으로 좁혀도 진짜 오타는 그대로 잡는다(실측: "삼서전자에 …골든크로스…" →
"혹시 '삼성전자'를 말씀하신 건가요?"). 회귀 가드: `tests/test_symbol_resolver.py`의
term-in 3건(오탐 없음·진짜 오타 검출·칩 폴백).

### § 11-7. 의도 분류 레인 이관 (2026-07-30 완료)

계약 수립 이후에도 **`intent/classifier.py`·`intent/scope.py`는 격차 목록에 오른 적이 없었다.**
§ 11-3~11-6이 전부 파이프라인 *내부*를 다루는 동안, 파이프라인에 진입할지를 정하는 상류
게이트가 원문 정규식 31개(classifier 14 + scope 17)로 남아 있었다.

발견 경위 — 2026-07-30 사용자 제보. 전략 카드가 떠 있는 상태에서 "원자력 업종만 테스트
하고 싶어"가 정형 거절(`OFFTOPIC_REFUSAL`)로 끝났다. 3단 실패:

1. `_classify_deterministic`의 규칙이 하나도 안 걸림(`_STRATEGY_KEYWORDS`에 '테스트' 없음,
   `_THEME_INVEST_CUE`에 '업종' 없음) → LLM 폴백으로 이월
2. 소형 분류 모델이 `OFF_TOPIC` 반환(진행 중인 전략 맥락을 받지 못한 상태)
3. `_FINANCE_CUE`에 '업종'이 없어 안전망이 판정을 못 뒤집음 → 거절 확정

이 레인의 실패 모드는 '틀린 전략'이 아니라 **'인터프리터 미도달'** 이다 — 파이프라인보다
앞에 있어서, 오판이 조용한 침묵으로 나타난다.

| 지점 | 이전(위반) | 이후 |
|---|---|---|
| 의도 판정 | `_classify_deterministic` — 원문에 정규식 14종을 걸어 의도·지표·업종·수정 여부 추출 | `intent/interpreter.py` — 원문은 LLM만 읽고 제한된 구조화 출력(`IntentInterpretation`: intent + stock_name + refers_to_last_stock) 생성 |
| LLM 출력 처리 | 라벨 1개를 정규식으로 긁어냄 | JSON 경계 추출 → 코드펜스/`<think>` 제거 → 라벨 표기 정규화 → Pydantic 검증(입력이 LLM 출력이므로 정규화 레인) |
| 안전망 | `has_finance_cue(원문)`이 LLM의 `OFF_TOPIC` 판정을 재심해 뒤집음 — 정규식이 의미 판정의 상급심 | 폐지. 대신 `active_strategy` 맥락을 LLM 입력에 넣어 **판정 단계에서** 오판을 줄인다 |
| 종목 인식 | `find_in_text(user_input)` — 원문 전체 스캔(금지 사항 5) | LLM이 뽑은 `stock_name` 문자열만 registry에 조회. 지시어는 LLM의 `refers_to_last_stock` + `last_symbol` |
| 규제 안전 안내 | 원문 정규식 예측자(`is_personal_advice_request`·`is_live_trading_request` 등)가 판정 | LLM 라벨(`PERSONAL_ADVICE`·`LIVE_TRADING` 신설)로 승격 → 라벨 키 도메인 정책이 확정 문구 선택 |
| 폴백 | 규칙 미스 → LLM → 실패 시 UNKNOWN(+원문 스캔) | LLM 미가용·출력 불량 = **실패 보고**(UNKNOWN, canned 없음). 연결 오류는 그대로 전파(503). 정규식 재해석 없음 |

프론트도 함께: `decideConversationTurn`이 `OFF_TOPIC`을 즉시 정형 응답으로 끝내는 분기는
**유지**한다 — 분류 LLM이 `active_strategy`를 알고 판정하므로, 그 위에 프론트가 조건으로
뒤집으면 "결정론이 LLM의 의미 판정을 재심"하는 같은 역전이 프론트에 재발한다.

**롤백**: `INTENT_CLASSIFIER_MODE=legacy` — 이전 레인 전체가 살아 있다(코드 삭제 아님·사용
중지, 1d와 같은 관례). 회귀 가드: `tests/test_intent_interpreter.py`(계약 레인),
`tests/test_intent_classifier.py`·`test_redteam_validation_fixes.py`(레거시 레인 — autouse
fixture로 legacy 고정).

**남은 격차**: `api/coach_routes.py::_coach_scope_guard`가 `intent/scope.py`의 원문 예측자를
그대로 호출한다(동일 위반의 두 번째 인스턴스). `intent/platform_defaults.py`는 `/query/general`
경로에서 원문으로 설정 항목을 추출한다. 둘 다 미이관.

### § 11-8. 수정 레인의 지식 조회 이관 (2026-07-30 완료)

§ 11-3이 "수정(modify) 레인·빌더의 테마 조회는 단계 3에서 같은 패턴으로 이관"이라고
남겨 둔 잔여분 중 **수정 레인**을 이관했다.

발견 경위 — 2026-07-30 사용자 제보. 토스 관련주 6종목으로 만든 전략에 "쿠팡 관려주로
수정해줘"를 넣자 전략이 토스 그대로 유지됐다. 인터프리터 로그는 의미를 제대로 읽고
있었다(`MODIFY_STRATEGY`, source_text="쿠팡 관려주로") — 그런데 패치 값이 **기존 토스
6종목 코드의 복사본**이었다. 수정 레인에는 지식 조회 체인이 없어서, 모델이 "쿠팡
관련주의 종목코드"를 스스로 알아내야 하는 처지였기 때문이다. 그래서 모델은 초안의
코드를 그대로 베끼고 사용자에게 "종목 코드가 무엇인가요?"를 되물었다 — **지식 조회를
사용자에게 떠넘긴 형태**(§ 3-2 위반)이며, 그 되묻기마저 프론트 게이트에 삼켜졌다.

| 지점 | 이전(위반/부재) | 이후 |
|---|---|---|
| 테마 표현 해석 | 수정 레인에 체인 자체가 없음 — 종목코드를 LLM이 알아내야 함 | `primary._resolve_theme_change` — 생성 경로와 같은 계약(카탈로그 후보 ≥2 범위 되묻기 / 1개 확인 칩 / 0개 KG→검색→되묻기) |
| 검증기 통과 | 미지 테마('쿠팡')가 '지원 섹터 아님' 오류 → 레인 전체 폴백 → 무변경 | 이번 턴이 새로 넣은 미해결 표현은 검증 전에 떼어 체인으로 보낸다(§ 11-3 입력 스냅샷 계약과 동형) |
| 종목 출처 | 테마 적용 시 테마명을 지움(`sector=None`) — 초안에 출처가 없음 | `ParsedStrategy.theme_universe`(+`UniverseSpec.theme`)로 왕복 — "이 종목들이 어느 테마에서 왔는가" |
| 테마 교체 | `apply_theme_companies`가 `target_symbols` 있으면 무조건 거부 | `replace_theme_universe` — **테마에서 온** 종목만 비우고 재조회, 사용자 직접 지정은 그대로(가드 유지), 실패 시 원상복구 |
| 무변경 되묻기 | 마커 없음 → 프론트 explicit 게이트의 조건 질문이 덮어씀 | `clarification_priority`(`sector_unresolved` / `modify_unapplied`)로 선행 표시 |

**트리거는 `universe.sectors`다** — 별도 필드(`universe.theme`)를 LLM에게 채우게 하려던
1차 설계는 실측에서 폐기했다. 9B는 테마 교체를 생성 규칙 6-0-2와 같은 형태
(`replace /universe/sectors = ["쿠팡"]`)로 내며, 출력 형태(`_OUTPUT_SHAPE`)에 없는 키는
채우지 않는다(§ 출력 형태 권위). `theme`은 시스템이 채우고 시스템이 읽는 **출처 표기**로만
남긴다 — 형태에서 뺀 이유는 `test_output_shape_objects_expose_all_live_fields`의
`_SHAPE_OMISSIONS`에 등록돼 있다(생성 턴에 테마가 여기로 가면 해석 체인을 우회한다).

회귀: `tests/test_modify_roundtrip_migration.py`의 테마 6건.
**잔여**: 빌더(`strategy_builder`) 레인의 원문 학습·테마 조회는 여전히 단계 3 대상.

### § 11-9. 워크플로 제어 축 추가 (2026-07-30 완료)

State-Aware Strategy Agent 설계 스펙 § 4(Conversation Mode / Workflow Effect 분리)의
구현. 이전에는 **"이 발화가 진행 중인 전략 작성을 어떻게 제어하는가"를 표현할 자리가
없었다** — "잠깐 멈춰"·"그만할래"·"처음부터 다시"·"아까 바꾼 거 되돌려"는 전부 일반
전략 발화로 흘러 조건 수정으로 해석되거나 조용히 무시됐다.

**축을 하나 늘리되 레인은 늘리지 않는다.** 스펙의 conversation_mode 8종 중 4종
(TASK/EXPLANATION/CASUAL/UNSUPPORTED)은 이미 `QueryIntent`와 중복이라 새 필드로 받지
않는다 — 같은 원문을 두 축으로 두 번 판정하면 `intent=OFF_TOPIC` + `mode=TASK` 같은
모순 조합을 조정하는 규칙이 필요해진다. 실제로 없던 것은 workflow_effect 하나이고,
이것은 라벨과 직교하므로(한 발화가 전략 요청이면서 동시에 취소일 수 없다) 중복이
생기지 않는다. REVIEW/CORRECTION 등 나머지 4종이 필요해지면 `QueryIntent` 라벨로
추가한다(라벨 체계는 하나로 유지).

| 지점 | 처리 |
|---|---|
| 판정 | `intent/interpreter.py` — 기존 의도 분류 LLM의 **출력 형태에 `workflow_effect` 키 1개 추가**. LLM 호출은 늘지 않는다. 원문 정규식은 여전히 0 |
| 형식 정규화 | `normalize_workflow_effect` — LLM 출력에만 동작. 목록 밖 표기·미출력은 `NONE`(모르는 값을 제어 동작으로 승격하지 않는다). 효과 파싱 실패가 라벨 분류를 실패로 만들지 않는다 |
| 성립 검증 | `classifier._resolve_workflow` — LLM은 제안만 하고 성립 여부는 결정론 코드가 정한다(스펙 § 18). ① 규제 게이트 라벨 9종은 제어 거부 ② 진행 중인 전략이 없으면 PAUSE/CANCEL/RESTART/ROLLBACK 불성립 ③ 직전 상태가 PAUSED가 아니면 RESUME 불성립. 불성립은 거부가 아니라 **NONE 강등**(제어가 사라져도 기존 흐름은 이어진다) |
| 상태 보관 | 백엔드 무상태 유지 — `IntentRequest.workflow_status`를 프론트가 매 요청에 에코한다(`previous_explicit_fields`·`pending_ask`와 같은 계약). 분류 실패 시에도 이 값을 잃지 않는다 |
| 실행 | 프론트 `decideConversationTurn` → `action: "control_workflow"`. CANCEL/RESTART만 전략 초안을 비우고(`clearStrategyDraft` — 대화 기록은 유지), PAUSE는 보존, RESUME은 진행, ROLLBACK은 미실행 |

**스펙 내부 모순 1건을 § 21 쪽으로 해소했다.** 스펙 § 4의 예시는 "PER이 뭐야?"를
`workflow_effect=PAUSE`로 적었지만, 같은 스펙 § 21은 "부가 질문은 기존 워크플로를
유지한다"고 규정한다. 설명마다 워크플로가 멈추면 명시적 RESUME 없이는 진행되지
않으므로 § 21을 따랐다 — **PAUSE는 사용자가 명시적으로 요청했을 때만** 쓰고, 용어
질문·잡담은 `NONE`이다.

**ROLLBACK은 감지하되 실행하지 않는다.** 변경 이력(Event Sourcing, 스펙 § 19)이 없어
되돌릴 대상을 특정할 수 없다. 거절로 끝내지 않고 지원 가능한 가장 가까운 형태를
안내한다(스펙 § 28). § 19 구현 시 `_EFFECT_TRANSITIONS`와 프론트 실행부만 배선하면
된다 — 판정·검증 레인은 그대로다.

회귀: `tests/test_intent_interpreter.py`의 워크플로 제어 11건(규제 게이트 우회 차단
9라벨 파라미터 포함), `app/analytics/new/conversationDecision.test.ts` 4건.

### § 11-10. 필드 상태 축 (2026-07-30 완료)

State-Aware Strategy Agent 설계 스펙 § 5(Field Status 7종)의 구현. 진행 골격 판정이
`filled: bool` 하나였고, 그 불리언이 **서로 다른 세 가지를 같은 값으로 뭉갰다**:

| 실제 사실 | 이전 표현 | 증상 |
|---|---|---|
| 사용자가 말한 값 | `filled=True` | — |
| 기본값이 물질화된 값(미확인) | `filled=True`(require_explicit=False 레인) | 빈 전략이 채워진 것처럼 보임 |
| 물을 대상이 아닌 항목 | `filled=True` | **단일 종목 전략의 리밸런싱 칸에 완료 체크가 켜짐** |

`strategy_slots.py`의 도입 배경 주석이 이미 같은 진단을 남겨 뒀다 — "판정을 한 곳에
모으는 것만으로는 부족하고, **그 곳이 표현할 수 있는 축이 실제 사례를 모두 덮어야
한다**". 이번 작업은 그 축을 늘린 것이다.

**스키마를 감싸지 않았다.** 스펙 § 5는 모든 필드를 `{value, status, source, ...}`로
감싸라고 하지만, 그러면 컴파일러·디컴파일러·patch_applier·엔진 변환기·프론트가 전부
깨진다. 값의 표현은 그대로 두고 **상태만 옆에 다는 사이드카**로 만들었다.

| 상태 | 산출 위치 | 근거 |
|---|---|---|
| UNKNOWN / CONFIRMED / PROVISIONAL | `engine/strategy_slots.py`(SOT) | 기존 3축(`_decided`·`_has_value`·`_explicit_ok`)을 그대로 재사용 — 새 판정을 만들지 않았다 |
| NOT_APPLICABLE | 같음 + `_status_only_not_applicable` | 단독 종목의 리밸런싱, 지정 종목의 최대 보유 |
| INVALID / NOT_APPLICABLE(조건) | `validation/field_state.py` | 검증 후 spec에서 구조적으로 재판정 — 지표 미해석·미지원은 INVALID, ETF×기업 재무지표는 NOT_APPLICABLE(해결책이 다르다: 전자는 지표를 바꾸고 후자는 유니버스를 바꾼다) |
| CONFLICTED | `conflict_validator` → `ValidationReport.conflicted_slots` | 오류 문장만으로는 어느 필드가 모순인지 알 수 없어 **판정한 자리에서** 슬롯을 함께 기록 |

**`filled` 판정은 한 줄도 바뀌지 않았다.** 상태 축은 표시 전용이고, 되묻기 게이트·
백테스트 실행 버튼·planner의 `filled_slots`는 이전과 동일하게 동작한다. 계약 픽스처
(`__fixtures__/slot-judgments.json`)를 재생성해 **무변동**임을 확인했다 — 이것이
회귀 없음의 근거다. `status_overrides`도 상태만 덮으며 `filled`를 건드리지 않고,
값이 없는 필드(UNKNOWN)는 덮지 않는다(모순일 수 없다).

소비자는 진행률 카드 하나다: '해당 없음'을 분모에서 빼고(`countProgress`) 흐리게
표시한다. 이전에는 완료로 세어 진행률이 실제보다 높게 보였다.

**남은 격차(스펙 § 5 대비)**: `source`·`confidence`·`updated_at`·`dependencies`·
`invalidated_by` 메타데이터는 미구현(현행 `ValueSource`·provenance가 source의 부분
집합을 이미 담당). INFERRED는 열거형에 정의만 하고 산출하지 않는다 —
`ConditionValue.value_source`가 조건 단위로 갖고 있으나 슬롯 단위로 롤업하는
소비자가 없다(없는 소비자를 위해 미리 만들지 않는다).

회귀: `tests/test_strategy_slots.py` 상태 축 12건, `tests/test_field_state.py` 11건,
`app/analytics/new/builderProgressPresentation.test.ts` 7건.

### § 11-11. 되돌리기 — 변경 이력과 대상 판정 (2026-07-30 완료)

설계 스펙 § 19(Event-Sourced State Management)의 구현. § 11-9가 `ROLLBACK` 효과를
**감지만 하고 실행하지 않던** 것을 닫았다.

**이벤트 소싱의 전체 구현이 아니다.** 상태 재구성(replay)이 아니라 **스냅샷 되감기**이며,
그것이 이 대화 모델에 필요한 전부다 — 각 턴의 ParsedStrategy 전체가 이미 스냅샷이라
이벤트를 되감아 상태를 만들 필요가 없다. 문서에 "이벤트 소싱"이라고 적지 않는 이유다.

| 레인 | 담당 |
|---|---|
| 변경 산출 | `conversation/change_log.py::changed_field_names` — 수정 턴마다 값이 달라진 최상위 필드 **이름**. 기존 `_diff_fields`는 "max_positions: 10 → 5" 같은 로그 문장이라 되돌리기 대상으로 쓸 수 없다 |
| 보관 | **프론트**(`changeLogRef`) + 세션 스냅샷. 백엔드에 세션이 없다는 계약을 유지한다 — `pending_ask`·`explicit_fields`·`workflow_status`와 같은 에코 |
| 대상 판정 | **LLM**(`conversation/rollback.py`, `/strategy/rollback/resolve`). "아까 바꾼 거"·"ETF로 바꾸기 전으로"·"PER 조건 지운 것만"은 전부 원문 해석이다 |
| 대조 | 결정론 — LLM이 고른 턴 번호가 이력에 있는지, 필드가 **그 턴의 변경 목록**에 있는지. 어긋나면 임의 보정 없이 되묻기 강등 |
| 복원 | **프론트**(`rollback.ts`) — 스냅샷을 들고 있는 쪽이 한다. 턴 단위는 그 변경 직전 스냅샷 전체, 필드 단위는 그 필드만 |

**임의 보정을 금지한 이유가 이 기능의 핵심이다.** 지어낸 턴 번호를 "가장 최근 턴"으로
떨어뜨리면 사용자가 의도하지 않은 변경이 조용히 사라진다 — 되돌리기는 작업을 지우는
동작이라 다른 레인보다 폴백이 더 보수적이어야 한다. 모든 실패는 되묻기로 끝난다.

**provenance도 함께 되돌린다.** 남겨두면 되돌아온 질문을 이미 답한 것으로 보고
건너뛴다 — 조건 옵션 되돌리기(`previousStepState`)가 이미 겪은 함정이다. 필드 단위
복원은 되돌린 필드의 provenance만 맞추고 나머지는 유지한다(이후 턴의 답변은 여전히
유효하다).

**실측이 설계를 두 번 고쳤다**(2026-07-30, 로컬 Ollama):

1. **모델 슬롯** — 처음엔 분류기와 같은 4B 슬롯(`_mlx_llm`)을 썼는데 **1/7**이었다.
   이 판정은 라벨 분류가 아니라 이력 목록 위의 추론이다. 9B(인터프리터 슬롯)로 옮겨
   5/7 → 최종 7/7. 4B도 아래 ②③ 수정 후 5/7까지 올랐지만 슬롯은 9B로 둔다 —
   잘못 고른 턴은 사용자가 쌓아온 전략을 지운다.
2. **필드 라벨** — 이력에 영문 필드명만 실었더니 "손절 바꾼 거 되돌려"가
   `stop_loss_pct`와 이어지지 않아 9B가 재무 조건 턴을 골랐다. 이력을
   `stop_loss_pct(손절)` 형태로 싣는다(`change_log._FIELD_LABELS`) — 라벨을 키로 정해진
   문구를 고르는 결정론 매핑이며 원문 해석이 아니다.
3. **대상 없는 요청** — "되돌려"에 모델이 임의의 중간 턴을 골랐다. 규칙 4로
   "가리키는 대상이 없으면 가장 큰 번호"를 명시했다(Ctrl+Z와 같은 의미).

회귀: `tests/test_rollback.py` 19건, `app/analytics/new/rollback.test.ts` 13건.

### § 11-12. 개념↔종목 관계의 근거·관련도 (2026-07-30 완료)

설계 스펙 § 8.5("Concept와 종목의 관계에는 반드시 근거와 관련도를 저장한다",
"직접적인 사업 관계와 단순 테마성 관계를 구분한다")의 구현.

**대부분 이미 있었고, 런타임에 도달하지 못하고 있었다.** 조사 원장
(`data/kg-research/*.json`, 129건)에는 `relation_type`·`relevance`·`relevance_score`·
`reason`·`business_evidence`·`sources`·`verified`가 이미 적혀 있다. 그런데 시드 그래프로
옮길 때 **관계 종류(엣지 타입)와 한 줄 `note`만 남고 나머지가 사라졌다** —
`grep kg-research engine/` 결과가 0이었다(원장은 런타임에서 한 번도 읽히지 않았다).

| 지점 | 이전 | 이후 |
|---|---|---|
| 원장 | 사람이 조사해 Core/Strong만 손으로 시드에 옮김. 런타임 미사용 | `engine/kg_research.py`가 mtime 캐시로 읽어 `(concept, symbol) → 관계 메타` 인덱스 |
| 엣지 | `{source, target, type, note}` | 원장이 있으면 `relation` 부착(없으면 부착하지 않음 — 근거를 지어내지 않는다) |
| 런타임 | `listed_companies`가 symbol·name·support만 반환 | `relation`·`direct`·`evidence_source` 추가 |
| 점수 산출 | `concept_universe`가 note 문자열에서 정규식으로 `"(Core 95)"` 되파싱 | 원장의 `relevance_score`를 그대로 사용(원장 없을 때만 기존 되파싱) |

**어휘를 정하고 데이터를 맞추지 않았다.** 처음엔 스펙의 10개 관계 유형을 그대로 상수로
적었는데, 원장 전수 확인 결과 실제 어휘는 `Producer 104·Supplier 15·Related 6·
Investor 3·Infrastructure 1`이었다. 목록을 데이터에 맞춰 고쳤다 — 원장이 정본이다.
목록 밖 유형도 버리지 않고 `relation_known=False`로 표시만 한다(걸러내면 새 유형을
추가할 때 관계가 조용히 사라진다).

**§ 8.5의 핵심 구분**은 `direct` 하나로 표현했다: `Producer`·`Supplier`만 직접 사업
관계이고, `Investor`·`Infrastructure`·`Related`는 사실이되 직접 생산·공급이 아니다.
출처는 `evidence_source`로 나눈다 — `research`(원장 근거) / `seed`(큐레이션이나 근거
미기재) / `catalog`(네이버 테마 수록) / `learned`(검색 학습). **출처는 빌드 시점에
표기한다** — 읽는 시점에 추론했더니 근거 없는 시드 엣지(HBM)가 카탈로그로 잘못
표기됐다.

**[규제 안전] 도입하지 않은 것.** 스펙 § 8.5의 관계 유형 중 **'정책 수혜 가능성'은
구현하지 않는다.** 미래 전망이라 근거로 표기하는 순간 객관적 데이터 표시가 아니라
전망 제공이 된다(CLAUDE.md 규제 안전 원칙 — 시장 전망 금지). 회귀 테스트가 전망성
어휘(Policy·Beneficiary·Expected·Outlook·Forecast)의 유입을 막고, 별도 테스트가 배포된
원장의 관계 유형이 전부 등록된 사실 유형인지 상시 확인한다.

**하지 않은 것 하나 더**: 관련도 기반 종목 절단·정렬은 넣지 않았다 —
"테마 유니버스 종수 상한 절단 금지"가 이미 선 사용자 결정이다.

회귀: `tests/test_kg_research.py` 16건(원장 읽기·직접 관계 구분·규제 어휘 가드·
그래프/유니버스 배선).

### § 11-13. 정정과 Action 메타데이터 (2026-07-30 완료)

설계 스펙 § 20(사용자 정정)과 § 12.1·12.2(Action 메타데이터·상태)의 구현.

**정정(CORRECT)** — `workflow_effect`에 값 하나를 더했다. ROLLBACK과의 경계는
**올바른 지시가 함께 있는가**다: "아까 바꾼 거 취소해"는 되돌리고 끝(ROLLBACK),
"아니 ETF로 바꾸라는 게 아니라 관련 ETF를 후보에 추가하라는 거야"는 되돌린 자리에
새 해석을 적용해야 한다(CORRECT). 되돌릴 지점은 **LLM에 묻지 않는다** — 정정은 언제나
방금 한 해석을 겨냥하므로 직전 변경으로 결정론이 정해진다(과거 어느 지점이든 가리킬 수
있는 ROLLBACK과 다른 점). 스펙 § 20의 "잘못 해석한 내용을 변명하지 마라"에 따라 사과·
해명 문구를 붙이지 않는다 — 되돌린 자리의 재해석 결과가 그대로 답이다(분류기에 CORRECT
canned 문구를 두지 않은 이유). 실측(4B): CORRECT·ROLLBACK·UPDATE 경계 포함 17/17.

**Action 메타데이터** — `requires`/`produces`/`invalidated_by`를 노드에 더했다.
**LLM에 묻지 않는다**: "kg_theme_companies가 무엇을 만들고 언제 무효가 되는가"는 도구의
정적 성질이지 이번 턴의 판단이 아니다. 프롬프트 출력 형태에 필드를 늘리면 9B가 그 자리를
채우려 잡음을 내고 prefill 예산만 먹는다(§ FR-STR-019o·019p) — `dag._TOOL_EFFECTS`
정적 표가 채우고, LLM이 실어 보내도 알려진 도구면 표가 이긴다.

**Action 상태 8종** — 완료 집합(done_ids)만으로는 "왜 이 노드가 실행되지 않았나"를
구분할 수 없었다(의존 미완료인지·무효인지·실패인지가 전부 '아직 안 됨'). `node_statuses`가
PENDING/READY/RUNNING/COMPLETED/BLOCKED/INVALIDATED/FAILED/SKIPPED를 계산한다.
**무효 노드는 목록에서 지우지 않고 INVALIDATED로 남긴다**(스펙 § 12.2) — 지우면 무엇이
왜 취소됐는지 추적할 수 없고 LLM이 같은 노드를 다시 발행한다.

무효화 씨앗은 **이미 완료된** 노드뿐이다. 실행 전 노드까지 씨앗으로 삼으면 정상 선행
실행이 무효로 잡힌다 — `classify_universe`(produces `universe.type`)가 먼저 돌면 그 값에
기대는 `kg_theme_companies`가 시작도 전에 무효가 된다. 무효화는 의존 방향으로 연쇄한다.

**`preconditions`는 구현하지 않았다.** 스펙 § 12.1의 `"universe.type == etf"` 형식을
평가하려면 표현식 미니 DSL이 필요한데, LLM이 그 문법을 지어낼 여지가 크고 평가 실패는
전부 '무시'로 떨어져 장식용 필드가 된다. 같은 제약은 이미 `depends_on` 사슬과
`validate_intent`/`compile_strategy` 게이트가 구조로 강제한다.

**적용 범위의 한계**: DAG는 파스 1회 안에서만 산다(턴 간 영속 아님). 따라서 무효화가
다루는 것은 한 파스 안에서 도구 관찰이 앞선 관찰의 전제를 깨는 경우다.

회귀: `tests/test_dag_planner.py` 8건, `tests/test_intent_interpreter.py` 5건,
`app/analytics/new/rollback.test.ts` 3건.

### § 11-14. 확정(CONFIRM) — 값이 아니라 상태를 바꾸는 답 (2026-07-30 완료)

설계 스펙 § 7(State Patch 연산)의 구현. 스펙은 `ADD`·`REPLACE`·`REMOVE` 위에
`CONFIRM`·`INVALIDATE`·`MARK_CONFLICT`·`MARK_NOT_APPLICABLE`·`REVALIDATE`·`ROLLBACK`
여섯을 더 요구하지만, **이 코드베이스에서 새 능력인 것은 `CONFIRM` 하나다.**

| 스펙 연산 | 현행 | 판단 |
|---|---|---|
| `CONFIRM` | 없음 | **구현** — 아래 |
| `INVALIDATE` | `validate_capability`가 매 턴 전략 전체에 재실행 | 저장하면 **판정의 두 번째 구현** |
| `MARK_CONFLICT` | `validate_conflicts` → `report.conflicted_slots` 매 턴 | 〃 |
| `MARK_NOT_APPLICABLE` | `field_state.slot_status_overrides` 매 턴 | 〃 |
| `REVALIDATE` | 파이프라인이 매 턴 무조건 재검증 | 지시할 것이 없다(무동작) |
| `ROLLBACK` | § 11-11에서 턴·필드 단위로 구현 | 표기만 다른 같은 것 |

상태는 이 코드베이스에서 **저장되지 않고 계산된다**(`strategy_slots.evaluate`,
`field_state.slot_status_overrides`). 상태를 패치로 기록하면 같은 판정이 두 곳에서
갈라지고, 그것이 `strategy_slots`를 SOT로 모은 이유 자체를 되돌린다
(`field_state.py` 머리주석: "같은 규칙의 두 번째 구현을 만들면 반드시 갈라진다").
스펙이 `MARK_*`를 요구하는 것은 스펙의 State가 상태를 **저장**하기 때문이며,
계산하는 구조에서 그 연산의 등가물은 "값 패치 적용 → 상태 재산출"로 이미 매 턴 돈다.

**CONFIRM만 다른 이유**: 확정은 값에서 **유도되지 않는다**. 물질화된 기본값
(`max_positions=10`)과 사용자가 10을 골라 확정한 값은 값이 같고 상태만 다르다
(PROVISIONAL vs CONFIRMED). 그 차이를 나르는 축이 `explicit_fields`(provenance)이고,
확정은 값을 그대로 둔 채 그 축만 올리는 연산이다.

**실측 결함(구현 동기)** — 확정 경로가 없어서 `_bind_chips`가 현재값과 같은 칩을
"표현할 수 없어 노출 제외"로 **탈락**시키고 있었다. 우리가 물어놓고 화면에 보여준 값을
사용자가 선택할 방법이 없었다는 뜻이다:

| 질문 | 사라진 선택지 | 현재값 |
|---|---|---|
| 최대 몇 종목을 담을까요? | `최대 10종목` | 10 |
| 초기 투자 자금은? | `1,000만원` | 10,000,000 |
| 어느 기간으로 백테스트할까요? | `최근 5년 데이터` | `5y` |

**두 레인**

- **결정론(칩)** — `_confirm_target`. 값이 안 바뀌는 칩에는 ①표현 불가와 ②현재값 지시가
  섞여 있어, 구분을 **프로브**로 한다: 그 필드를 현재값이 아닌 값으로 바꿔 둔 State에
  칩을 적용해 현재값으로 되돌아오면 ②다. "패치가 비었으니 topic의 확정"으로 추정하지
  않는다 — 그 추정은 아무 뜻도 결속되지 않은 칩을 사용자 확정으로 둔갑시켜 되묻기를
  삼킨다(말하지 않은 값 확정 금지). 확정 칩은 `pending_ask.chip_confirms`로 값 결속과
  **채널을 나눠** 에코한다(섞으면 무변경 패치가 되어 '반영 없음'으로 떨어진다).
- **LLM(자유 서술)** — `CONFIRM_RECOMMENDATION`. 라벨은 `IntentType`과 프롬프트에
  이미 있었으나 **어디서도 처리되지 않아** "응 그걸로"가 patches 없는 의도로 떨어져
  "해석하지 못했어요"로 끝났다(선언만 있고 배선이 없는 라벨). 확정이라는 판정은 원문
  해석이므로 LLM이 하고, **무엇을 확정했는지는 묻지 않는다** — 확정은 언제나 우리가
  방금 던진 질문에 대한 답이므로 `pending_ask.topic`으로 결정론이 정한다(§ 11-13의
  정정이 되돌림 지점을 LLM에 묻지 않는 것과 같은 이유). 물어본 적이 없으면 임의로
  고르지 않고 기존 경로로 넘긴다.

**확정 가능 필드는 4개**(`strategy_slots.CONFIRMABLE_FIELDS`): 최대 보유·리밸런싱·
백테스트 기간·초기 자본. 물질화 기본값이 없는 필드(진입·청산·손절·익절)에는 확정할
대상이 없고, `universe`는 시장·업종·종목 여러 속성의 합이라 '그 값 그대로'가 하나로
정해지지 않는다(유니버스 범위 칩은 `_apply_universe_chip`의 값 적용 레인).

**미해결 잔여**: 리밸런싱의 `리밸런싱 안 함` 칩은 여전히 탈락한다 — 결정적 칩 추출기가
그 문구를 인식하지 못하는데, 인식시키려면 `_extract_rebalancing_period`(**사용자 원문**에
쓰이는 추출기)의 어휘를 넓혀야 하고 그것은 대원칙 1 위반이다. 올바른 해법은 칩 문구
재추출이 아니라 planner가 칩 발행 시 값을 함께 선언하는 구조다.

회귀: `tests/test_chip_answer.py` 7건, `tests/test_modify_roundtrip_migration.py` 2건.

### § 11-15. 하이브리드 상태 모델 — 영속·계산·산출물 (2026-07-30 완료)

설계 스펙 § 5·§ 7의 재정의. 스펙은 모든 필드 상태를 State에 저장하라고 요구하지만,
**저장할 것과 계산할 것을 나눈다**(2026-07-30 사용자 결정).

| 종류 | 상태 값 | 정본(SOT) | 저장? |
|---|---|---|---|
| **Persisted User State** | `ValueStatus` 4종 | `ParsedStrategy`(값) + `explicit_fields`(provenance) | ✅ |
| **Derived Runtime State** | `DerivedStatus` 4종 | `validation/pipeline.py` → `field_state.py` → `strategy_slots.evaluate` | ❌ 매 턴 계산 |
| **Persisted Artifact State** | `ArtifactStatus` 4종 | `conversation/artifacts.py` | ✅ 근거만 |

**나누는 기준은 재계산 비용이다.** 파생 상태는 전략을 보면 공짜로 다시 나온다(실측
0.12ms) — 저장하면 판정이 두 곳에서 갈라질 뿐 얻는 것이 없다. Artifact는 지식그래프
조회·외부 검색이 필요해 "아직 맞나"를 재실행으로 확인할 수 없다 — 그래서 **무엇을
근거로 만들었는지**(`source_key`)를 남기고 근거만 대조한다.

**가역성이 이 설계의 시험대다.** 유니버스를 ETF로 바꾸면 기존 PER 조건은
NOT_APPLICABLE로 계산되지만 원본 값은 그대로 보존되고, 다시 코스피로 되돌리면
**역방향 패치 없이** APPLICABLE로 돌아온다. 상태를 저장했다면 그 되돌림을 LLM이
발행해야 하고, 빠뜨리면 멀쩡한 조건에 '적용 불가'가 영구히 남는다
(회귀: `test_derived_status_is_reversible_without_a_reverse_patch`).

**타입을 가른 이유**: 기존 `FieldStatus` 7종은 두 축이 섞여 있어 "값은 확정인데 지금
유니버스에서 못 쓴다"를 표현할 수 없었다. 이제 `SlotStatus`가 두 필드를 갖고,
`field_states` 페이로드는 슬롯 → `{value, derived}`다. `NodeStatus`(작업을 실행했나)와
`ArtifactStatus`(그 결과가 아직 유효한가)도 이름을 겹치지 않게 분리했다.

**파이프라인 불변조건**: 파생 상태 계산은 planner·인터프리터 출력과 무관하게 매 턴 돈다
(`main._finalize_parse_result` — 모든 반환 지점이 여기를 지난다). 이전에는 계산하는
레인이 초기 파스와 수정 성공 **둘뿐**이어서, 칩 답변·확정·유니버스 칩·설명·되묻기
레인에서는 프론트가 직전 턴 사본을 계속 썼다(전략이 바뀐 턴에서는 틀린 표시).

**Patch 허용목록**: `add`/`replace`/`remove`(JSON Patch wire format 유지 — 수정 RAG
코퍼스와 프롬프트 예시가 이 어휘를 가르친다). `MARK_NOT_APPLICABLE`·`MARK_INVALID`·
`MARK_CONFLICT`·`REVALIDATE`는 **추가하지 않는 것이 계약**이며 `ALLOWED_PATCH_OPS`와
`patch_applier._reject_state_ops`가 그것을 코드에 남긴다. `REVALIDATE`는 파이프라인이
무조건 하는 일이라 지시할 대상이 없다 — 필드를 만들면 LLM이 그것을 **빠뜨릴 수 있게**
되어 없을 때보다 나빠진다.

**비권위 메타데이터**: `field_metadata`(`source`·`updated_at`·`confidence`)는 저장하되
판정에 쓰지 않는다. `explicit_fields`와 채널을 섞지 않은 이유는, 게이트가 읽는 권위
축에 비권위 값을 넣으면 언젠가 판정에 새어 들기 때문이다(회귀 테스트가 판정 경로 4개
파일에 이 이름이 등장하지 않음을 확인한다). **`confidence`는 필드별 producer가 없다** —
인터프리터는 턴 하나에 값 하나를 내므로, 여기 실리는 것은 '이 필드를 마지막으로 바꾼
해석의 확신도'이지 필드 자체의 확신도가 아니다.

**`INFERRED`는 producer가 없다** — enum과 스키마에만 유지한다. 정성 표현 매핑·암시적
유니버스 추론을 이 상태로 잇는 것은 별도 단계다(이번 작업의 목표는 상태 모델 정리이지
새 추론 기능 추가가 아니다).

**Artifact 대조의 한계**: STALE 판정은 "요구한 테마"와 "산출물이 만들어진 테마"가 각각
저장돼 있을 때만 가능하다. 정본 업종('반도체')은 `parsed.sector`에 남지만 미지
테마('쿠팡 관련주')는 `sector` 검증을 통과하지 못해 요청이 어디에도 남지 않는다 —
그 경우 VALID는 '확인했다'가 아니라 '반증이 없다'는 뜻이며 `basis_verified=False`로
드러낸다. 드러내지 않으면 검증되지 않은 산출물이 검증된 것처럼 보인다.

회귀: `tests/test_field_state.py` 27건, `tests/test_strategy_slots.py`,
`app/analytics/new/builderProgressPresentation.test.ts`.

### 마이그레이션 순서

1번(`nl_parser.py`)은 독립 순번이 없다 — 나머지가 끝나면 남는 잔여물이며, 성격이 다른
세 가지(엔진 DSL 스키마 / 지식 조회 / 자연어 해석 정규식)가 한 파일에 있어 단계마다
쪼개진다. 유일하게 앞으로 당기는 조각은 지식 조회 분리(1a)다.

```text
1a + 4   지식 조회 레이어 분리 + UniverseSpec.symbols            ✅ 완료 (2026-07-26)
2'a      수치 반영 대조(recall_validator)                        ✅ 완료 (2026-07-26)
2'b      인터프리터 모델 슬롯 + 9B 승격                          ✅ 완료 (2026-07-26)
2  + 1b  인터프리터 경로에서 보정 제거(기본값 off)               ✅ 완료 (2026-07-26)
         함수 삭제는 레거시 파서가 쓰는 한 불가 — 1c 이후
5        STRATEGY_INTERPRETER_MODE 기본값 primary 승격            ✅ 완료 (2026-07-26 — 명시적 env 우선, prod=shadow 유지)
   (관찰) prod 지연·드리프트 실측 → prod primary 전환 판정        ⬜ ← 다음 (keep-warm 검토 포함)
1c       _parse_rule_based_strategy·_modify_rule_based 폴백 차단  ✅ 완료 (2026-07-26, § 11-5 — 5번보다 먼저 랜딩)
1c'      KG 입력 계약 text-in → term-in (§ 11-3)                  ✅ 완료 (2026-07-26 — primary 초기 파스 레인. 폐기 대상 삭제·수정/빌더 레인은 1d·3에서)
1c''     수정 레인 지식 조회 이관 (§ 11-8)                        ✅ 완료 (2026-07-30 — 테마 교체 체인+출처 보존. 빌더 레인은 3에 남음)
3        strategy_builder.py 동일 패턴 반복 (C안 재정의)          🔶 Phase 1 완료 (2026-07-26 — 미해석 자유 서술 LLM 레인. 권한 역전은 실사용 후)
1d       레거시 해석 경로 '사용 중지' (2026-07-26 재정의)          ⬜ ← prod .env를 primary로 전환하면 완료
         · 사용자 결정: 레거시 파서 코드는 **삭제하지 않고 보존**한다(롤백 전용 —
           off/shadow 모드로만 도달). "코드는 그대로 두고 사용만 하지 않는다."
         · Modal scale-to-zero 유지(테스트 단계 — 콜드스타트 첫 파스 ~2분 수용,
           keep-warm 불요). 구 계획의 'ParsedStrategy 분리+잔여 삭제'는 폐기.
```

이 문서는 **새로 작성·수정하는 코드가 따라야 할 기준선**이며, § 9 체크리스트가 그 게이트다.
