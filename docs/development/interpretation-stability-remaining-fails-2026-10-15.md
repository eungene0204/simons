# KR 남은 예시 실패 수리 — 2026-10-15

사용자 “두 번째부터 끝까지 … 모두 고치도록 해” 지시로 남은 실패 예시를 별도 지시 없이 이어 수리한다. 기존 작업트리와 미커밋 변경을 보존한다. 각 구현은 아래 독립 단위별 한 경계 안에서 처리하고 문서는 G에서 별도로 반영한다.

## 단위 1: 두 번째 실패의 저가 이탈

Task:
예시 #6의 기존 엔진 지원인 buy-high/sell-low breakout을 레지스트리·검증·컴파일 역할 계약에 일치시킨다.

Boundary:
W.

Files allowed:
- registry/indicator_registry.py의 기존 breakout 연산자/설명.
- validation/capability_validator.py의 기존 역할/방향 검사.
- compiler/strategy_compiler.py의 기존 역할/방향 검사.
- backend/tests/test_remaining_live_examples.py의 breakout 회귀.

Do not:
- 새 엔진/팩터/데이터·원문 어휘 규칙·모델 변경, 역할에 맞지 않는 방향을 조용히 뒤집기.

Requirements:
- 20일 고점 매수/20일 저점 매도를 각각 지원한다. 반대 역할의 방향은 validator/compiler에서 거부한다.
- 기존 engine.signals의 high/low와 signalType 의미를 읽고 확인하며 알고리즘은 수정하지 않는다.

Run:
- backend에서 `PYTHONPATH=/tmp UV_CACHE_DIR=/tmp/simons-uv-cache uv run --frozen pytest -p simons_stage2_guard tests/test_remaining_live_examples.py -q`.

Deliver:
- 전후 재현, 구조화/실행 요청/표시의 고저·역할·20일 보존.

## 단위 2: EMA quote 불일치 뒤 검증된 기간 복구

Task:
예시 #80에서 quote 재확인의 지표 근거를 보존하고 기존 semantic 배치의 검증된 기간 수정만 별도 후보로 적용한다.

Boundary:
W.

Files allowed:
- interpreter/quote_check.py, semantic_reconciliation.py.
- backend/tests/test_remaining_live_examples.py의 EMA·반대 판정/누락 대조 회귀.
- components/admin/AgentsTab.tsx의 기존 단계 설명.

Do not:
- quote 불일치를 바로 ACCEPT로 전환, REJECT 부활, 추가 단독 모델 호출, 원문 어휘 재판정.

Requirements:
- 불일치는 UNRESOLVED를 유지한다. 재확인이 MA를 확인한 경우에만 기존 semantic 배치에서 복구를 시도한다.
- source/역할/수량 근거가 있는 실제 기간 변화만 새 candidate를 만들고 이전 미해결을 승계한다.
- unclear/실패/동일 값/명시 거부는 기존 보류를 유지한다. 20일 EMA 이탈은 종가와 EMA 20의 교차이고 20/60의 교차로 남기지 않는다.

Run:
- 위 신규 회귀 및 `tests/test_quote_check.py tests/test_required_verdict_dependencies.py tests/test_remaining_interpretation_semantics.py`.

Deliver:
- 새 후보의 근거/정체성 및 fail-closed 보존 확인.

## 단위 3: 화면 표시와 공통 데드크로스 가족

Task:
실패 #47/#49/#52/#61/#74를 첫 번째 수리로 검증하고 parameter conflict 고지의 내부 factor 노출을 정본 표시 이름으로 바꾼다.

Boundary:
W.

Files allowed:
- validation/conflict_validator.py의 메시지 factor 라벨.
- backend/tests/test_remaining_live_examples.py의 가족/고지 회귀.

Do not:
- 지표 기간 순서 오류를 통과시키기, 수치/의미를 바꾸거나 잘못된 고지를 단순 삭제.

Requirements:
- 실제 conflict 판정은 유지하면서 사용자 안내에 technical.ema 같은 식별자를 내보내지 않는다.
- 원래 실모델의 최소 초기 구조화 필드로 각 가족의 매도 역할과 독립 설정을 검증한다.

Run:
- 신규 회귀, 정본·조건 승인 관련 검사와 이번 응답의 표시 스윕.

Deliver:
- 가족별 결과 및 미검증과 실모델 결과 구분.

## 통합 검증과 문서

Task:
남은 예시의 실제 요청/표시 경로 검증을 마무리하고 각 결과를 기록한다.

Boundary:
코드 단위 종료 후 G. 프런트의 기존 metric 중복 선언으로 실제 경로 검증이 막히면 별도 A 단위에서 conversationDecision.ts 및 관련 회귀만 수정한다.

Files allowed:
- G: 이 문서, PROJECT_PLAN, software_architecture, SRS, nl_interpretation_contract, 경계 문서.
- A 후속 필요 시: app/analytics/new/conversationDecision.ts와 authority 회귀, 기존 parse stream 회귀 기대 계약.

Do not:
- 운영 DB/어휘집/데이터 변경, US 게이트, 커밋/배포, 전체 기존 테스트 실패를 기대값 완화로 숨기기.

Requirements:
- 필수 backend/프런트 검사 및 KR 고정 재생을 실행하며 이번 변경의 회귀와 기존 범위 밖 실패를 구분한다.
- 필요 실모델 재검증은 이미 승인된 511회 예산 중 사용한 312회를 제외한 199회 안에서 남은 사례만 한 번씩 확인한다. 예상 추가 40~65회이며 무료 모델/실제 응답 모델을 기록한다. 실패를 재호출해 성공으로 교체하지 않는다.
- 소규모 실행의 통과를 81개 재실행·US·전체 구현 통과로 표현하지 않는다.

Run:
- backend에서 기존 4개 ignore + `-k 'not us'` 필수 pytest 명령.
- `npm run test:frontend`, KR 고정 replay, 변경 범위 `git diff --check`.

Deliver:
- 현재 작업트리 미커밋 수리와 사례별 결과, 잔여 제약/실패.

## 추가 수리 기록 — #47·#49·#52·#61·#74·#80 (2026-10-15, 워크트리 미커밋)

- **#47/#49/#52/#61/#74 데드크로스 가족**: 선언된 매도 개념은 보유 기간 복구 대상이 아니라는 기존 수리로 보유 기간 질문이 사라졌음을 현재 코드에서 확인했다. 회귀: `tests/test_create_concept_holding_scope.py`(#47 원문 재생, 실제 매도 문구 5종 파라미터화).
- **#74 이중 골든크로스(새로 발견)**: 독립 추출 구절 "골든크로스가 나오면 매수하고"가 기존 조건 출처와 경계가 어긋나 누락 회수 패스가 `concept.golden_cross`를 기간 없는 `technical.ma_crossover`로 한 번 더 되살려 20/60 기간 되묻기가 나갔다. `condition_recall.recover_missing_conditions`의 `known`에 개념 전개 잎을 추가했다(입력은 LLM이 낸 factor ID).
- **#80 EMA 이탈 청산**: 실서버 5/5에서 "20일 EMA 이탈"이 진입 쌍 20/60으로 복사됐다(4회 보류, 1회는 틀린 청산이 조용히 통과). 프롬프트 8.14에 예시 1개를 추가해 청산을 종가와 EMA 20(1/20)으로 고정했다. 수정 후 5/5 청산 `ema 1/20`, 되묻기 없음.
- **실서버 재표본**(워크트리 코드, 전용 포트, nemotron-3-super-120b:free): #80 전 5·후 5, #47·#49·#52·#61 각 3, #74 전 3·후 3, 볼린저 #16 7. 기술분석 카테고리 게이트 16건 중 치명 1(볼린저 청산 소실)은 이후 재표본 7회 모두 정상이라 flake로 분류했으나 수정 전 대조군은 측정하지 않았다.
- **되묻기 하니스**: `qa_free_input.py modify` PASS 41·NOT_RUN 2(고지 기대값 미검토), `fill` PASS 10·HARNESS_INVALID 32("초안이 이미 질문 슬롯을 채움")로 fill은 사실상 미측정이다. 수정 전 대조(전후 비교)는 하지 않았다.
- **전체 백엔드 pytest**: 503 failed·5377 passed·12 errors(`intent/`·`nl_parser`·`strategy_builder` 등 이번에 만지지 않은 영역이 대부분). 제 수정 2곳을 되돌린 대조에서 인접 5개 파일의 실패 21건이 수정 유무와 동일해 새 실패는 만들지 않았다. 나머지 기존 실패의 원인 규명은 남아 있다.
- **미실행**: 표시 스윕, 81개 전수, US 게이트, 커밋.
