# 전략 해석 안정화 — 4단계 판정 통합·조건 교체 원자성

Task:
기존 보조 판정을 공통 내부 결과로 기록·소비하고 거부/관계 미확정 교체 그룹과 독립 변경을 분리한다.

Boundary:
W. 명세·경계 정의·완료 문서는 별도 G 작업이다.

Files allowed:
- backend/strategy_conversation/interpreter/decisions.py 및 기존 *_check.py의 결과 어댑터
- backend/strategy_conversation/conversation/patch_approval.py
- backend/strategy_conversation/primary.py
- backend/tests/** (unit and synthetic replay)
- components/admin/AgentsTab.tsx (flow sync only)

Do not:
- 사용자 원문 regex/키워드 의미 추론, 새 Agent/State/DSL/공개 스키마
- 기존 판정 프롬프트/모델·호출 수 변경, 미해결 보조 판정 일괄 보류(5단계)
- 엔진·DB·어휘집·parquet 수정, 외부 모델/검색 호출, 커밋·푸시·배포

Requirements:
- candidate_id/change_group_id/status/reason_code/evidence_ref/stage를 공통 내부 결과로 저장
- ACCEPT/REJECT/UNRESOLVED와 실제 적용 정책을 구분하고 충돌 우선순위·근거를 추적
- 원자적 그룹 거부 시 기존 조건 유지, 독립 스칼라/다른 조건 변경 보존
- JSON Patch 순차 인덱스의 원래 대상을 식별해 일부 그룹 제외 후 정확히 재배치
- 적용 직전 기준 상태 대조, 스키마 재검증, 실제 승인 패치/최종 상태/미반영 안내 검증
- invalid auxiliary의 기존 fail-open 유지를 명시하고 5단계 보류 정책을 선행하지 않음

Run:
- 관련 재현/회귀 먼저 (PYTHONPATH=/tmp UV_CACHE_DIR=/tmp/simons-uv-cache uv run --frozen pytest -p simons_stage2_guard ...)
- cd <worktree>/backend && PYTHONPATH=/tmp UV_CACHE_DIR=/tmp/simons-uv-cache uv run --frozen pytest -p simons_stage2_guard tests/ --ignore=tests/test_backtest_engine.py --ignore=tests/test_engine_ai.py --ignore=tests/test_ai_sell.py --ignore=tests/test_api_isolation.py
- npm run test:frontend
- UV_CACHE_DIR=/tmp/simons-uv-cache uv run --frozen python scripts/qa_template_detect.py --replay backend/tests/fixtures/interpretation_replay.json --out /tmp/simons-stage4-replay.json
- 성공 조건 ALL PASS. 범위 밖 기존 실패도 원인과 미수리 사유를 보고한다.

Deliver:
- 같은 격리 작업트리의 미커밋 변경, 이전 단계와 타 세션 변경 보존
- 결과 공통화·개별 어댑터·그룹 계획/적용·주경로/도표·회귀를 1~5파일 독립 단위로 분리
- 변경 전후·검사·실모델 NOT_RUN·잔여 범위를 보고하고 4단계 게이트에서 멈춘다.

## 구현 결과와 원인

조건 교체는 한 묶음으로 보류하고, 별도로 확인된 변경은 남기는 경로를 구현했다. 전체 안정화 완료와 운영 검증을 뜻하지 않는다.

1. 검수표를 하나로 모으듯, 기존 보조 검사 반환값을 유지하면서 공통 판정 기록으로 감쌌다. `decisions.py`의 요청별 기록은 후보·변경 그룹·세 상태·이유·근거 참조·단계를 연결한다. `decision_adapters.py`와 기존 8개 검사 모듈을 통해 quote, trading value, numeric, market/condition scope, pair, return, holding recovery, market region을 기록한다. holding days 조정의 확인 여부도 기록하며 check_batch는 기존 검사 호출을 재사용한다. 프롬프트·모델·보조 호출을 추가하지 않았다.
2. 같은 검수 항목의 마지막 결과를 사용하고, 다른 단계가 충돌하면 `REJECT > UNRESOLVED > ACCEPT` 순서로 그룹 상태를 계산한다. 충돌의 과거 상태와 모든 근거는 함께 남긴다. 분류기 ACCEPT와 `LEGACY_ELIGIBLE`은 각각 유효한 분류·기존 적용 정책의 결과이지, 변경 전체의 의미 정확성을 보증하지 않는다. 숫자 confidence를 새로 만들지 않았다.
3. 서류 번호를 고정하듯, `patch_approval.py`는 순차 배열 경로를 조건의 내부 정체성에 연결한다. 같은 조건의 형제 필드 패치와 기존 LLM이 확인한 remove/add 교체를 묶고, 일부 그룹 제외 후 원래 대상을 가리키도록 JSON Pointer를 재배치한다. 동일한 값의 별도 조건과 없는 인덱스의 승격도 별도 그룹으로 유지한다. 외부 조건 ID·State·DSL은 추가하지 않았다.
4. 기존 검사가 새 조건을 제외하면 공통 REJECT 행을 그룹 승인에서 소비해 해당 교체 전체를 보류한다. 기존 조건을 복원하되 종목 수 및 식별 가능한 다른 조건 수정은 남긴다. 추가·삭제 관계 미확정과 모델이 특정 필드를 되묻는 경우에도 독립 변경을 적용하고 해당 질문을 유지한다. 기존에는 이런 경로에서 이전 전략 전체로 돌아가 독립 변경도 사라질 수 있었다.
5. 사본에 후보 패치를 적용해 검사하고, 보류 그룹을 제외한 사본을 기존 스키마·도메인 파이프라인으로 재검증한다. 같은 요청의 원래 초안 해시가 달라지면 적용을 중단한다. 선택된 제안·검증 후 실제 StrategySpec 차분·최종 ParsedStrategy 해시/응답을 따로 남긴다. 이는 JSON 제안이 선택됐다는 것과 실제 상태가 바뀌었다는 것을 구분하기 위한 기록이다.

### 변경 파일과 행동 계약

- 새 공통 결과/어댑터: `backend/strategy_conversation/interpreter/decisions.py`, `decision_adapters.py`.
- 기존 결과 감싸기: 같은 디렉터리의 `quote_check.py`, `trading_value_check.py`, `numeric_patch_check.py`, `patch_scope_check.py`, `patch_pair_check.py`, `relative_return_check.py`, `holding_period_check.py`, `market_region_check.py`. 기존 반환 객체·판정 요청은 유지한다.
- 원자성 계획/승인: `backend/strategy_conversation/conversation/patch_approval.py`, `backend/strategy_conversation/primary.py`.
- 회귀/재생 근거: `backend/tests/test_interpretation_decisions.py`, `test_patch_group_approval.py`, `interpretation_replay.py`, `fixtures/interpretation_replay.json`.
- 처리 흐름: `components/admin/AgentsTab.tsx`의 공통 판정·그룹 승인과 후보/최종 차분 설명을 동기화했다.
- **행동이 바뀐 범위**: 기존 명시적 조건 거부·교체 관계 불명확·모델의 특정 필드 질문에서 전체 수정 취소 대신 독립 변경을 보존한다. 거부된 조건 변경은 이전 조건 유지 안내를 제공한다. 보조 판정 실패 시 일괄 보류하는 행동 계약은 바꾸지 않았다.
- 독립 단위는 공통 기록(1~2파일), 검사 어댑터(각 1~5파일), 정체성 계획+회귀(2파일), 주경로+흐름도(2파일), 재생 근거+corpus(2파일), 문서 G로 나눴다. 누적 코드는 200줄을 넘으며, 이를 하나의 작은 diff라고 주장하지 않는다. 이전 2·3단계 변경을 보존했다.

## 재현과 변경 전후

`test_patch_group_approval.py::test_quote_rejected_replacement_keeps_independent_position_change`에서 “한 달 지나면 정리”를 MA 청산으로 잘못 출력하고 기존 quote 판정이 no/other로 거부하는 고정 결과를 사용한다. 기존 청산·PER를 유지하면서 종목 수는 12여야 한다.

- 비교 대조: 새 그룹 분기만 기존 전체 복귀 동작으로 임시 대체했을 때 **1 FAIL**, 기대 12·실제 15였다. 현재 소스는 finally에서 복구하고 일치 여부를 확인했다. 이는 특정 이전 가드 동작의 대조 실험이며, 이전 코드 전체 스냅샷의 측정으로 부르지 않는다. `/tmp/simons-stage4-rollback-baseline.txt`.
- 현재 해당 회귀와 순차 인덱스·묶음 거부·중복 승격·기준 초안 변조·실제 차분 재적용 검사가 통과한다. 관계 불명확한 매수 교체와 ETF 범위 질문도 기존 조건을 유지하고 수량 12와 원래 질문을 함께 반환한다.
- 합성 API/표시 재생은 기존 8건 **7 PASS·1 FAIL**을 유지했고, `rejected-replace-independent`, `unclear-pair-independent` 2건이 추가 PASS다. 최종 **9 PASS·1 FAIL**이다. 기대값은 사람이 지정한 상태·안내·표시 조건이며 공통 판정 구현을 복제한 채점으로 만들지 않았다.
- `qualitative-unresolved`의 FAIL은 `/parsed/entry_signals`, `clarification_question`이다. 보조 결과 None인 정성 수익률의 임의 0 확정 결함을 계속 탐지한다. gold를 완화하지 않았다. 북극항로의 3단계 안내 수리는 PASS로 유지됐다.
- 모두 `synthetic-fixture`, schema 1.0, 엔진 16.40.0, 기반 코드 4e048137이며 실제 재생 코드 콘텐츠 해시는 `6b2a5606e23a3ac766b06ed5a4ec853b9e74f6624c723c946f53cb335af70f30`이다. 신규 모델/검색 호출 **0회**다. 합성 모델·고정 판정/지식의 결과를 운영 120B/9B 품질이나 오류율 추정으로 사용하지 않는다.

## 검증 기록

- 관련 회귀 명령: `cd <worktree>/backend && PYTHONPATH=/tmp UV_CACHE_DIR=/tmp/simons-uv-cache uv run --frozen pytest -p simons_stage2_guard tests/test_patch_group_approval.py tests/test_interpretation_decisions.py tests/test_strategy_conversation.py tests/test_interpretation_replay.py tests/test_interpretation_trace_fixture.py tests/test_quote_check.py tests/test_check_batch.py tests/test_interpretation_authority.py -q` → **490 PASS**, 10 warnings, 12.05s. `/tmp/simons-stage4-related-complete.txt`.
- 중간 실패: 처음 393 PASS·31 FAIL은 기존 조건에 그룹 소유자가 없을 때 None을 문자열과 결합한 새 binding 결함이었다. 기존 조건의 정체성을 기본 그룹으로 사용해 해결했다. 그 뒤 관련 묶음 424·456·484·487건이 각각 통과했고, 최종 위 490건을 확인했다. 잘못된 테스트 파일명으로 한 번 수집 0건이 발생한 실행은 PASS로 세지 않는다.
- 프런트 전체 `npm run test:frontend` → **PASS: 333 files·2,430 tests**, 1 file/2 tests skipped, 78.70s. `/tmp/simons-stage4-frontend-final.txt`.
- 위 Run의 최종 replay → **9 PASS·1 FAIL**, exit 1. `/tmp/simons-stage4-replay.json`에 primary/API/표시·공통 판정/충돌·선택 제안/실제 차분이 있다. `/tmp/simons-stage4-replay.log`.
- 백엔드 전체는 위 Run의 정확한 4개 ignore 명령에 외부 네트워크 차단 pytest 플러그인을 적용했다 → **FAIL: 5,797 passed·5 skipped·1 failed**, 19 warnings, 248.75s. `/tmp/simons-stage4-backend-final.txt`. 단일 실패 `test_backfill_us_stocks.py::test_columns_match_korean_schema`는 이전 2·3단계와 같은 KR parquet와 US COLUMNS 불일치다. KR에 `fcf_margin`부터 5개 컬럼이 더 있으며 이번에는 해당 코드·데이터를 수정하지 않았다. 금지된 수집/데이터 범위를 고쳐 통과시키지 않았고 **ALL PASS는 미충족**이다.
- `git diff --check`와 새 5개 Python 파일의 공백 확인은 PASS다. 문서는 별도 G에서 이 결과·PROJECT_PLAN·software_architecture·SRS와 자연어 해석 계약을 갱신한다. CLAUDE 현행 격차의 기존 원문 의미 판정 부채는 미수리 상태를 유지한다.

## 잔여 범위와 단계 게이트

- 공통 결과는 위 기존 보조 가족과 수정의 선택/제외 경로를 연결한다. contribution/liquidity 검사, 전역 도메인 검증 결과 전체의 후보별 공통화와 교차 슬롯 오류·값 누락의 독립 그룹 분리는 남아 있다. 모든 검사기가 하나의 공통 승인 정책만 소비한다고 주장하지 않는다.
- 거부된 add와 같은 목록의 remove 관계가 증명되지 않으면 해당 삭제를 보수적으로 함께 보류한다. 식별 가능한 다른 replace는 보존하지만, 모든 독립 삭제 보존을 보장하지 않는다. holding 복구는 기존 별도 후보 경로를 유지하며 그 근거를 기록한다. 검증기 내부의 복구·이동은 아직 모든 경우에 새 candidate lineage로 연결되지 않는다.
- 해시 대조는 요청 안의 로컬 초안 검사다. DB/서버의 요청 간 상태 버전 충돌 검사는 구현하지 않았다. 검증 후 StrategySpec 차분과 이후 유니버스 후처리가 반영된 ParsedStrategy는 별도로 기록하며 서로 같다고 가정하지 않는다.
- **5단계 미착수**: 필수 검사의 실패/불명확을 신규·교체 변경 보류로 바꾸는 정책은 필수 판정 목록·보류/질문 영향 보고와 사용자 승인 이후다. 현재 `UNRESOLVED` 기록과 `APPLY_LEGACY_POLICY`를 구분해 기존 fail-open이 승인 근거로 오인되지 않게 했다.
- 전체 안내 채널의 최종 단일 조립은 여전히 3단계의 생성 KR sector 범위를 넘지 않는다. 수정의 기존 안내 생산자·ETF·US의 전 안내 정합성을 완료로 표시하지 않는다. 기존 원문 의미 정규식/어휘 부채는 미이관 **위반**이며 이번에 추가·확장하지 않았다.
- **NOT_RUN**: 새 KR 81예시 파싱, KR/US 실모델 생성·수정·fill, `/us` 영문 실제 페이지, 운영 품질 변동·응답 지연·보류율/불필요한 질문율. US 수량 fixture의 backend 보존과 기본 한국어 페이지 문맥의 표시 helper 재생을 실제 `/us` 검증과 구분한다. 2단계 저장 표시 81건의 옛 안내 enum 1 FAIL은 이번에 다시 돌리거나 캐시를 수정하지 않았다.
- 구현은 `/Users/eugene/nullalgo/simons-wt/interpretation-replay-stage2`의 미커밋 변경이다. 원래 backend에 복사하지 않았으며 커밋·푸시·배포·운영 DB/어휘집/parquet 갱신을 하지 않았다. 사용자 §11에 따라 4단계 결과 보고에서 멈추고, 다음은 5단계 정책안 검토다.
