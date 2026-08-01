# Observability — LangSmith Trace 계층

전략 대화 Agent(Planner → Action DAG → Tool → State → Responder)의 실행 과정을
LangSmith Trace로 남긴다. **관찰만 한다** — 실행 경로·분기·되묻기 조건·폴백 판정·
반환값·예외 전파 중 어느 것도 바꾸지 않는다.

구현: [`backend/observability/`](../backend/observability/)

---

## 1. 대원칙

| 원칙 | 의미 |
|---|---|
| **비활성이 기본값** | `LANGSMITH_TRACING`이 참이 아니면 완전한 no-op. langsmith를 import조차 하지 않는다 |
| **반환값·예외 불변** | span은 예외를 기록만 하고 그대로 다시 던진다. 삼키면 폴백 판정이 뒤집힌다 |
| **관찰 실패 ≠ 실행 실패** | langsmith 장애·직렬화 실패는 debug 로그로만 남기고 통과시킨다 |
| **없는 값은 지어내지 않는다** | `user_id`는 요청 계약에 없으므로 `None`. Cost는 self-hosted라 없으므로 싣지 않는다 |

> ⚠ **활성화하면 외부 전송이다.** 사용자 원문(한국어 전략 요청), 전략 State,
> LLM 프롬프트 전문이 LangSmith로 나간다. prod 활성화는 별도 결정 사항이다.

---

## 2. 활성화

```bash
LANGSMITH_TRACING=true                # 이것만이 스위치. 미설정 = 완전 no-op
LANGSMITH_API_KEY=lsv2_pt_...         # 활성 시 필수
LANGSMITH_PROJECT=NullStock           # 선택(기본 "NullStock")
LANGSMITH_ENDPOINT=https://...        # 선택. self-hosted 인스턴스면 여기로
```

롤백 = `LANGSMITH_TRACING` 줄 삭제. 코드 변경 없이 즉시 꺼진다.

---

## 3. Trace 계층

```
Trace  "NullStock Strategy Agent"            ← 사용자 요청 하나 = Trace 하나
├── Interpreter · 전략 해석                    (chain)
│   └── LLM · <model>                        (llm)   토큰·지연·프롬프트 전문
├── Planner · Action DAG                     (chain)
│   ├── out.action_dag / action_dag_ascii    ← 생성된 DAG 전체
│   ├── out.node_statuses / status_counts    ← 노드별 최종 상태(8종)
│   ├── LLM · <model>                        (llm)   DAG 발행 턴마다
│   ├── Action · <node_id>                   (chain) Action 하나
│   │   └── Tool · <tool_name>               (tool)  실제 도구 호출
│   └── State · 무효화                        (chain) State 변경이 깬 Action
├── Tool · validate_intent                   (tool)
├── Tool · compile_strategy                  (tool)
├── Validation · 후행 파스 검증                (chain) SSE 응답 후 단계
└── Responder                                (chain) 사용자에게 나간 것
```

**Action span과 Tool span을 분리한 이유**: 둘을 합치면 "Action은 계획됐는데 도구는
안 불렸다"(`call_cache` 재사용)를 구분할 수 없다. Action span의 `cache_hit`가 그 축이다.

---

## 4. 계측 지점 (chokepoint 5곳)

기존 코드에 계측을 흩지 않았다 — 파이프라인에 이미 있던 단일 통로만 감쌌다.

| 계층 | 위치 | 방식 |
|---|---|---|
| Trace 루트 | `main.py::_run_nl_parse` | 본체를 `_run_nl_parse_traced`로 두고 래퍼가 span만 연다 |
| Tool | `strategy_conversation/tools/base.py::call` | 도구 9개 전부 이 함수를 지난다 |
| LLM | `interpreter/llm_strategy_interpreter.py::_default_ollama_chat` | 공유 `ChatFn` 계약 — interpreter·dag_planner·mini_planner·term_grounding이 전부 소비 |
| Planner | `planner/dag_planner.py::plan_strategy_dag` | 본체를 `_plan_strategy_dag`로 두고 래퍼가 span만 연다 |
| Interpreter | `interpreter/...::StrategyInterpreter.interpret` | 본체를 `_interpret`으로 두고 래퍼가 span만 연다 |

---

## 5. 스레드 경계 — 가장 중요한 함정

**langsmith는 contextvar로 부모 span을 찾는데 contextvar는 스레드를 건너지 않는다.**
이 코드베이스는 스레드를 세 곳에서 쓴다:

| 위치 | 처리 |
|---|---|
| `parse-stream`의 파스 스레드 | 루트 span이 그 스레드 안에서 열리므로 전파 불필요 |
| `dag_shadow` / `planner shadow` | `current_parent()`를 스레드 인자로 넘기고 `use_parent()`로 복원 |
| SSE 후행 검증 (`_complete_deferred_validation`) | `defer_holder["trace_parent"]`로 넘기고 `use_parent()`로 복원 |

전파하지 않으면 **span이 조용히 고아 Trace가 되고 아무도 눈치채지 못한다.**
회귀 테스트: `backend/tests/test_observability_hierarchy.py`
(대조군 테스트 `test_thread_without_parent_starts_its_own_trace`가 이 실패 모드를 고정한다.)

---

## 6. 수집 항목

### Performance Metrics
루트 span 메타데이터에 자동 누적된다 — 실행 코드는 자기 소요 시간을 보고하지 않는다.
`span()`이 종료 시점에 더한다.

`total_duration_ms` · `planner_ms` · `tool_ms` · `llm_ms` · `state_update_ms` ·
`responder_ms` · `action_count` · `tool_count` · `llm_calls` · `retry_count` · `failure_count`

### LLM 호출
System/User Prompt · Model · Temperature · `num_ctx` · Input/Output Token · Latency · Response

토큰 수는 Ollama `/api/chat` 응답의 `prompt_eval_count`/`eval_count`를 읽는다.
**Cost는 싣지 않는다** — self-hosted(Ollama/Modal)라 단가가 없고, 지어낸 비용은 관찰이 아니다.

### Error Trace
예외는 span이 자동으로 잡는다. **예외로 끝나지 않는 실패**(폴백 `None` 반환)는
`trace.error(kind, message)`로 명시 기록한다:

`PlannerOutputParseError` · `DagContractError` · `ToolContractError` · `ToolError` ·
`OutputGuardRejected` · `NoProgress` · `TurnBudgetExhausted` · `EmptyInput`

---

## 7. Metadata — 파생 가능한 것만

스펙은 `user_id`·`session_id`·`strategy_id`를 요구하지만 **백엔드에 셋 다 없다.**
`NLParseRequest`는 무상태 에코 계약이라 사용자·세션 개념을 갖지 않는다. 관찰 계층이
요청 스키마를 늘리는 것은 실행 경로 변경이므로, 가진 값에서만 파생한다.

| 필드 | 값 |
|---|---|
| `strategy_id` | 이 턴이 산출한 전략 State의 내용 해시 |
| `parent_strategy_id` | 이 턴에 들어온 전략(`previous_parsed`)의 내용 해시 |
| `session_id` | `parent_strategy_id` (첫 턴이면 프롬프트 해시) |
| `user_id` | **`None`** — 파생 근거가 없다 |
| `turn_kind` | `create` \| `modify` |
| `version` | `engine/version.py`의 `ENGINE_VERSION` (버전 정본 재사용) |

**대화를 잇는 방법**: 턴 N의 `session_id` == 턴 N-1의 `strategy_id`. 그 사슬을 따라간다.
진짜 세션 키가 아니라서 "한 세션의 모든 턴"을 한 번에 필터할 수는 없다 — 그건 요청
계약에 세션 필드가 생겨야 가능하고, 그때 `observability/identity.py`만 바꾸면 된다.

---

## 8. Dataset & Evaluation

### Dataset
`backend/observability/dataset.py` — 대표 입력 21개(생성/수정/제어/규제/테마).

```bash
python scripts/langsmith_dataset.py --dry-run   # 전송 없이 확인
python scripts/langsmith_dataset.py             # 업로드(멱등)
```

**정답 전략(reference output)을 담지 않는다.** 되묻기는 실패가 아니라 정상 동작이며
(말하지 않은 값을 기본값으로 확정하지 않는 것이 Agent의 계약), "이 입력엔 이 전략이
정답"이라고 못 박으면 계약을 어기는 쪽이 통과한다. 대신 각 예시는 evaluator가 검사할
**구조적 성질**만 라벨로 선언한다(`expects_universe`, `forbidden_terms` 등).

### Evaluators
`backend/observability/evaluators.py` — 전부 결정론. LLM judge를 쓰지 않는다
(채점이 비결정적이면 회귀 테스트로 쓸 수 없다).

| 축 | 검사 |
|---|---|
| `dag_well_formed` | 비순환·의존 존재·`finish→compile→validate` 사슬 |
| `no_wasted_actions` | `BLOCKED`/`INVALIDATED` 비율. **`SKIPPED`는 낭비가 아니다**(재질문 가드 동작) |
| `state_change_declared` | 실제 변경 필드가 어떤 Action의 `produces`로 선언됐는가 |
| `tool_selection_valid` | 금지 도구 호출·중복 호출 |
| `response_contract_kept` | 생성된 질문·칩의 금지 표현(ETF에 PER/ROE 등) |
| `turn_made_progress` | 확정 또는 되묻기로 진전했는가. **되묻기는 만점** |

**판정할 수 없으면 `score=None`**(집계 제외). 근거 없이 0점을 주면 대시보드가 거짓말을 한다 —
planner가 폴백된 턴에 "DAG가 올바른가"를 채점하지 않는 이유다.

---

## 9. 자연어 해석 계약 준수

관찰 계층은 **사용자 원문의 의미를 판정하지 않는다.**

- 입력을 정규식으로 읽어 지표·업종·의도를 추출하는 코드가 없다
- evaluator의 검사 입력은 Agent가 만든 구조화 출력(DAG·노드 상태·생성된 질문 문자열)과
  Dataset이 사람 손으로 붙인 라벨뿐이다
- `identity.py`의 해시는 내용 지문일 뿐 의미 해석이 아니다

`observability/`에 원문 패턴 매칭을 추가해서는 안 된다 —
[자연어 해석 계약](nl_interpretation_contract.md) 참조.

---

## 10. 테스트

```bash
cd backend && pytest tests/test_observability_tracing.py \
                     tests/test_observability_evaluators.py \
                     tests/test_observability_hierarchy.py \
                     tests/test_observability_parse_root.py -v
```

테스트는 `LANGSMITH_ENDPOINT`를 `http://127.0.0.1:1`로 고정해 **외부 전송을 차단한다.**
(추적을 켜는 테스트가 있어 필요하다 — 실제로 `api.smith.langchain.com`으로 POST가
나가는 것을 확인하고 막았다.)
