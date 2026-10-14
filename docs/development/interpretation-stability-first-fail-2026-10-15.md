# 첫 번째 실모델 FAIL 수리 — 이평선 골든크로스 따라가기

Task:
예시 #1에서 이미 추출된 데드크로스 매도 조건이 보유기간 확인 실패로 소실되는 오류를 수리한다.

Boundary:
W 코드/검사 완료 후 별도 G 보고 문서 작업. 이 문서는 G 산출물이다.

Files allowed:
- W: `backend/strategy_conversation/interpreter/holding_period_check.py`, `backend/tests/test_create_concept_holding_scope.py`, `components/admin/AgentsTab.tsx`의 기존 검사 대상 설명.
- G: 이 문서, PROJECT_PLAN, software_architecture, SRS, nl_interpretation_contract.

Do not:
- 다른 예시 실패·프런트 턴 중재·레거시 파서 오류를 함께 수정하지 않는다.
- 원문 어휘/regex, 모델·프롬프트·정본 데이터·컴파일러·엔진·API 스키마·필수 실패 보류 정책을 바꾸지 않는다.
- 추가 live 호출, 운영 데이터 쓰기, 원래 backend 수정, 커밋/배포를 하지 않는다.

Requirements:
- 지표 잎 목록 밖이라는 이유만으로 정본 전개를 가진 개념을 잘못된 청산 후보로 분류하지 않는다.
- 매수/매도 역할, 기존 정본 전개의 교차 기간, 종목 수 10, 손절 8%, 미지정 보유기간을 보존한다.
- 실제 알 수 없는 시간 조건은 기존 근거 확인/복구 또는 미해결 보류를 유지한다.
- 변경 전 실패, 변경 후 primary 및 API 출력, 관련 회귀와 저장소 필수 검사 결과를 구분한다.

Run:
- 작업트리 backend: `PYTHONPATH=/tmp UV_CACHE_DIR=/tmp/simons-uv-cache uv run --frozen pytest -p simons_stage2_guard tests/test_create_concept_holding_scope.py -q`.
- 직접 관련 검사: `PYTHONPATH=/tmp UV_CACHE_DIR=/tmp/simons-uv-cache uv run --frozen pytest -p simons_stage2_guard tests/test_create_concept_holding_scope.py tests/test_required_verdict_policy.py tests/test_required_verdict_dependencies.py tests/test_concept_ontology.py tests/test_strategy_conversation.py::test_create_unknown_time_exit_recovers_explicit_hold_without_losing_other_exit tests/test_strategy_conversation.py::test_rejected_condition_holding_check_requires_quoted_duration -q`.
- 넓은 인접 검사: 위 네 파일 및 `tests/test_strategy_conversation.py` 전체.
- 저장소 backend: `PYTHONPATH=/tmp UV_CACHE_DIR=/tmp/simons-uv-cache uv run --frozen pytest -p simons_stage2_guard tests/ --ignore=tests/test_backtest_engine.py --ignore=tests/test_engine_ai.py --ignore=tests/test_ai_sell.py --ignore=tests/test_api_isolation.py -k 'not us' -q`.
- 작업트리 루트: `npm run test:frontend`; 코드/문서 범위 `git diff --check`.

Deliver:
- 작고 미커밋인 수정, 첫 예시의 관측 근거/전후 검사, 범위 밖 실패와 live 미실행 상태.

## 관측과 원인

2026-10-15 KR 81예시 실모델 게이트의 #1 “이평선 골든크로스 따라가기”, Trace `e5b83b9624d8`을 대상으로 했다. 기존 사람 기대값은 골든크로스 매수, 데드크로스 매도, 최대 10종목, 손절 8%이며 명시된 보유기간은 없다.

| 원문 근거 | 기대 의미 | 실제 FAIL 결과 | 최초 손실 |
|---|---|---|---|
| 골든크로스가 나오면 매수 | 매수 교차 신호 | 최초 해석에 있음 | 이번 수리 대상의 손실 없음 |
| 데드크로스가 나오면 매도 | 매도 교차 신호 | exit_signals=[] | 보유기간 복구 후보 선정/필수 보류 |
| 최대 10개, 손절 -8% | 10종목 / 손절 8% | 유지됨 | 없음 |
| 보유기간 미지정 | 보유기간 확정·관련 질문 없음 | 무관한 최대·최소 보유기간 질문 | required_holding 보류의 전파 |

1. 메인 해석기는 `concept.golden_cross`와 `concept.dead_cross`를 각각 entry/exit에 추출했다. 조건 인용 대조도 두 후보를 ACCEPT했다.
2. `recover_create_misfiled_holding_period`는 factor가 잎 `REGISTRY`에 없으면 알 수 없는 청산 조건으로 보았다. 개념 정본은 별도 ontology에 있어 정상 데드크로스가 이 복구 대상으로 잘못 들어갔다.
3. 보유기간 대조는 `kind=none`을 반환했다. 기존 필수 보류 정책이 이를 holding 미해결로 기록해 exit 후보를 제거하고 보유기간 질문을 만들었다. 정상 조건을 잘못된 검사에 보낸 것이 원인이다.

## 수정

- 보유기간 복구 대상 선정 시 기존 `concept_spec(factor).expansion`도 조회한다. 정본 전개가 있으면 이 복구 검사를 건너뛰고 기존 quote/도메인/컴파일 검증으로 보낸다. validator가 이미 쓰는 같은 전개 계약을 재사용한다.
- 원문 문장별 예외나 데드크로스 ID 목록을 추가하지 않았다. 입력은 LLM이 제공한 factor이며 기존 정본 선언만 조회한다. quote 거부/미해결을 우회하거나 필수 holding 실패를 ACCEPT로 바꾸지 않는다.
- 미지 시간 조건의 근거 확인과 실패 시 UNRESOLVED 정책은 그대로다. 이 사례에서 잘못 실행되던 holding 호출은 없어지고 새로운 호출은 추가되지 않는다.
- AgentsTab의 기존 보유기간 복구 단계 설명을 실제 검사 대상으로 동기화했다. 구조/새 단계는 추가하지 않았다.

## 검증 상태

- 신규 회귀 5개: 변경 전 **3 FAIL / 2 PASS**, 수정 후 **5 PASS**. 관측된 첫 Interpreter의 최소 구조화 필드와 실제 quote/holding/semantic 응답을 고정한다. 정본 데드크로스·MACD 데드크로스의 비대상 처리와 미지 시간 조건의 성공/실패를 대조한다.
- API 후처리까지 확장한 동일 5개 회귀 **PASS**, 45.96초. 최종 exit에는 sell ma_crossover(정본 5/20)가 있으며, entry의 buy 역할·10종목·손절 8%를 유지하고 hold_period_days=None이다. 무관한 보유기간 질문이 없다.
- **직접 관련 검사 53 PASS**, 14.96초. 기존 quote·필수 보류·시간 수량/단위·온톨로지 계약을 포함한다.
- 넓은 인접 검사: **429 PASS / 10 FAIL**, 67.35초. 실패 10개는 모두 직전 live 게이트의 backend 검사에도 있던 동일 테스트 이름이며 새 실패 이름은 없다. 기존 override/롤백 기대, ETF/고지, 수정 패치 및 재생성 관련 항목이다. 이번 대상 밖 실패를 성공으로 바꾸지 않았다.
- frontend 전체 **FAIL: 302 files PASS / 32 files FAIL / 1 skipped; 2,215 tests PASS / 2 FAIL / 2 skipped**, 156.73초. 31파일은 이번에 변경하지 않은 conversationDecision.ts의 `metric` 중복 선언으로 수집이 막혔다. 나머지 SSE 2건은 이전 원문 기반 skeleton 기대와 구조화 경로의 충돌이다. 이번 흐름 설명 수정과 별개의 기존 코드/계약 실패다.
- backend 필수 검사: **4,559 PASS / 469 FAIL / 11 ERROR / 3 skipped / 839 deselected**, 424.94초. 직전 4,553 PASS / 470 FAIL보다 신규 5개가 통과했고 기존 실패 1개도 통과했다. 실패 이름 집합을 대조해 새 실패 항목이 없음을 확인했다. 기존 통과로 전환된 항목은 `test_parse_stream_emits_thinking_stage_when_parser_falls_back`이며 이 단일 차이를 다른 예시 실모델 개선으로 일반화하지 않는다. `not us`는 이름 기반 제외이며 지역을 완전히 분리한 전체 검사라고 표현하지 않는다.
- 변경한 코드 범위의 `git diff --check`와 신규 회귀/보고서의 공백 확인 PASS. 전체 검사 ALL PASS는 미충족이다.
- 신규 원격 모델/검색 호출 **0회**, live 재검증 **NOT_RUN**. 최소 재현에서는 무관한 planner/recall을 끄고 손실 계층을 격리했다. 최초 실모델 Trace 전체를 동일 tape로 재생한 결과 또는 81예시 재실행 결과라고 표현하지 않는다. 해당 raw Trace는 기존 3일 보관 정책 밖으로 승격하지 않았다.

## 변경 위치와 제한

코드는 `/Users/eugene/nullalgo/simons-wt/interpretation-replay-stage2`에만 미커밋으로 반영했다. 이번 변경은 세 파일이며 나머지 예시/표시/전체 검사 실패의 수리는 남아 있다. 이전 live 게이트의 8 FAIL 숫자를 새 실측 결과로 덮어쓰지 않는다.

전후와 전체 검사 로그는 `/tmp/simons-first-fail-20261015/`의 `before.log`, `after.log`, `after-api.log`, `focused.log`, `related.log`, `backend.log`, `frontend.log`이다.
