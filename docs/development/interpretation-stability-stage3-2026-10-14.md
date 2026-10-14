# 전략 해석 안정화 — 3단계 생성 업종·테마 안내 정합성

Task:
생성 턴의 KR 업종·테마 검증 결과를 최종 반영 근거와 대조해 모순 안내를 막는다.

Boundary:
W. 경계 정의·명세와 완료 문서 갱신은 각각 별도 G 작업이다.

Files allowed:
- backend/strategy_conversation/validation/capability_validator.py (KR sector findings)
- backend/strategy_conversation/validation/pipeline.py (evidence handoff)
- backend/strategy_conversation/interpreter/models.py (internal ValidationReport evidence only)
- backend/strategy_conversation/response/notice_assembly.py
- backend/strategy_conversation/primary.py (create KR resolution evidence and notice assembly)
- backend/tests/** (regression and synthetic replay)
- components/admin/AgentsTab.tsx (flow diagram sync only)

Do not:
- 사용자 원문 regex/키워드 의미 추론, 모델/프롬프트 변경
- 수정·ETF·US 안내 방식 개편, 공통 승인/원자성/보조 실패 보류 정책 구현
- 공개 API/StrategySpec/JSON Patch 변경, 엔진·provider·DB·어휘집·parquet 수정
- live 모델·검색 호출, 커밋·푸시·배포

Requirements:
- 검증기의 이중 errors/unsupported를 하나의 표현·필드·reason·stage 근거에 연결
- 표현별 실제 반영과 최종 상태가 모두 뒷받침할 때만 앞 단계 안내 해소
- 일부 표현 성공이 다른 표현 실패 안내를 지우지 않음
- 미해결·상태에서 소실된 표현은 안내/기존 질문으로 노출
- 관련 없는 조건 오류와 안내 보존, 공개 응답 계약 유지
- 북극항로 재생 FAIL→PASS, 정성 수익률 기존 FAIL 유지

Run:
- 관련 회귀를 외부 연결 차단 상태에서 먼저 실행
- cd <worktree>/backend && PYTHONPATH=/tmp UV_CACHE_DIR=/tmp/simons-uv-cache uv run --frozen pytest -p simons_stage2_guard tests/ --ignore=tests/test_backtest_engine.py --ignore=tests/test_engine_ai.py --ignore=tests/test_ai_sell.py --ignore=tests/test_api_isolation.py
- npm run test:frontend
- UV_CACHE_DIR=/tmp/simons-uv-cache uv run --frozen python scripts/qa_template_detect.py --replay backend/tests/fixtures/interpretation_replay.json --out /tmp/simons-stage3-replay.json
- 합격 조건 ALL PASS. 기존 데이터 실패도 숨기지 않고 원인을 보고한다.

Deliver:
- 같은 격리 작업트리의 미커밋 변경. 2단계 변경을 보존한다.
- 구조 근거 전달, 표현별 해소, 최종 조립, 회귀/도표를 1~5파일 독립 단위로 나눈다.
- 변경 전후 결과·실행/미실행·확장 필요 범위·잔여 위험을 보고하고 3단계 게이트에서 멈춘다.


## 결과와 원인

**북극항로 테마가 실제 반영된 뒤 목록 밖 안내가 남던 생성 KR 경로를 수리했다. 전체 안정화와 운영 검증의 완료는 아니다.**

1. 서류 심사에서 나온 거절 사유를 바로 배송 안내에 복사했다(검증 errors→notices). 같은 표현은 unsupported에도 들어가 두 복사본이 생겼다.
2. 뒤의 테마 조회가 북극항로 종목을 반영했지만 한 복사본만 지웠다(term-in/planner-first의 unsupported pruning). errors 복사본은 남아 화면의 유니버스와 모순됐다.
3. 이제 해당 검증 결과에 표현·필드·reason_code·단계를 붙여 마지막까지 보관한다(KR catalog finding). errors/unsupported 원본과 검증 상태는 진단 근거로 유지하고, 생성 사용자 안내에 복사하는 시점만 늦춘다.
4. 실제 적용 시점마다 표현별 값과 출처 단계를 기록하고 마지막 값에 남아 있는지 대조한다(resolution receipt / final-state check). 하나가 성공해도 다른 표현이 미해결이면 그 안내는 남고, 뒤에서 값이 덮어써졌으면 먼저 반영했다는 이유로 안내를 숨기지 않는다.
5. 마지막에 해당 업종·테마 안내를 조립한다(notice_assembly). 범위 선택 질문은 성공으로 세지 않으며 기존 질문을 유지한다. LLM 미지원 라벨에 성공·미해결 표현이 함께 있으면 전체 라벨을 숨기거나 전부 실패로 말하지 않고 보고 원문과 표현별 상태를 함께 보여준다.

## 실제 변경과 한계

- `models.py`의 `ValidationReport._universe_findings`는 PrivateAttr다. 외부 serialization/schema는 확장하지 않았다. `capability_validator.py`의 KR sector 분기는 기존 오류/미지원 결정을 유지하며 한 구조 근거로 연결하고, `pipeline.py`가 이를 전달한다. 튜플 반환 계약도 유지한다.
- `response/notice_assembly.py`는 초기 복사를 예약하고 최종 사용자 projection을 만든다. 조회 기록과 마지막 값이 모두 일치해야 해소이며, 원문을 다시 해석하거나 임계값을 만들지 않는다.
- `primary.py`의 생성 KR 경로만 이를 소비한다. 고정 term-in·mini-planner·planner-first 적용 직후 근거를 기록하고, 정본 후보에서 원 표현으로 전파하는 경우에는 해당 정본의 기록을 상속한다. shared 함수의 새 인자는 선택 사항으로, 수정/US/ETF 호출의 기존 동작은 유지한다. 공개 notices 배열과 질문·칩 계약은 그대로다.
- `AgentsTab.tsx`의 흐름도를 컴파일·유니버스 적용→최종 안내 조립→상태 표시→출력 순서로 동기화했다.
- 테스트 도구는 universe_notice_assembly의 입력·결과를 재생 단계 증거에 추가했다. 합성 corpus는 부분 성공/전체 미해결 2건을 추가해 8건이며 gold를 느슨하게 바꾸지 않았다. 첫 북극항로의 원본 LLM 출력과 기대 상태/안내는 유지했고, 사라진 legacy unsupported 라벨 조회 `_extract_sector`의 **합성** tape 항목 1개만 제거했다. 과거 전체 tape를 자동으로 건너뛰는 규칙은 만들지 않았으며, 이전 결과는 `/tmp/simons-stage3-before.json`에 남긴다.
- 작은 독립 단위: 검증 근거 전달(3파일), 순수 조립과 회귀(2파일, 약 200줄), 생성 적용·흐름도 동기화(2파일), 재생 증거·corpus·회귀(3파일). 누적 변경을 한 작은 diff라고 주장하지 않는다. 기존 2단계 변경은 그대로 보존했다.
- 일반 warnings·조건 오류와 그 밖의 안내 생산자는 기존 경로다. LLM 자유서술 라벨의 표현 연결에는 **기존 LLM 출력 간 literal containment**를 유지하고 최종 상태 근거를 추가했다. 이것이 모든 조건 역할의 정체성을 증명하는 것은 아니다. 공통 candidate/change_group 판정·전체 채널 provenance는 4단계 대상이다.
- 정성 수익률 0 확정과 보조 판정 fail-open은 바꾸지 않았다. 새로운 자연어 regex·키워드·의미 추론을 추가하지 않았다. 1단계에서 보고한 기존 원문 해석 위반/격차도 수리 완료로 설명하지 않는다.

## 재생 결과와 검증

| 사례 | 변경 전 | 현재 | 확인한 기대 |
|---|---|---|---|
| arctic-notice | FAIL | PASS | 테마/2개 합성 종목 반영, 목록 밖 모순 안내 없음 |
| qualitative-unresolved | FAIL | FAIL | relative_return 0 확정 결함은 그대로 탐지 |
| holding-create | PASS | PASS | 10거래일 최대 보유, 청산 역할 보존 |
| positions-kr / positions-us | PASS | PASS | 보유 8과 기존 PER·손절 보존 |
| entry-fill | PASS | PASS | 실제 빈 매수 칸에 PER≤10 추가 |
| arctic-partial | 신규 | PASS | 북극항로 반영 유지, 미확인테마 안내·질문 보존 |
| theme-unresolved | 신규 | PASS | 임의 종목 확정 없이 안내·질문 제공 |

기존 같은 6건은 **4 PASS·2 FAIL→5 PASS·1 FAIL**이다. 추가 2건 포함 **7 PASS·1 FAIL**이며 API/표시까지 동일한 결과다. 모두 synthetic-fixture 모델·수동 버전 라벨의 합성 사례다. 운영 테마 명부/운영 120B·9B 품질/일반 오류율로 읽지 않는다. 신규 모델·검색 호출은 **0회**다.

- 수정 전 조립 회귀: `PYTHONPATH=/tmp UV_CACHE_DIR=/tmp/simons-uv-cache uv run --frozen pytest -p simons_stage2_guard tests/test_universe_notice_assembly.py -q` → **4 FAIL**(조립기 미구현). 구현 후 마지막 파일 검사 **8 PASS**. 실제 planner 덮어쓰기·mini-planner 적용도 포함한다.
- 관련 검사: `PYTHONPATH=/tmp UV_CACHE_DIR=/tmp/simons-uv-cache uv run --frozen pytest -p simons_stage2_guard backend/tests/test_universe_notice_assembly.py backend/tests/test_sector_term_in_chain.py backend/tests/test_planner_primary_mode.py backend/tests/test_planner_first.py backend/tests/test_strategy_conversation.py backend/tests/test_interpretation_replay.py backend/tests/test_interpretation_trace_fixture.py backend/tests/test_recall_validator.py backend/tests/test_strategy_compile.py -q` → **534 PASS**, 12 warnings, 10.77s. 이후 추가한 실제 적용 근거 2건은 위 8건과 최종 전체에 포함한다.
- 중간 실패를 숨기지 않는다: 최초 관련 465 PASS·1 FAIL은 기존 생명보험 라벨 연결을 너무 좁혔기 때문이었다. 기존 LLM 라벨 관계를 보존하고 최종 근거를 요구해 해결했다. 새 corpus 이후 관련 531 PASS·3 FAIL과 소규모 28 PASS·3 FAIL은 빈칸 invalid-fixture 회귀가 배열 마지막 사례를 가정한 하네스 오류였다. entry-fill case_id로 선택하도록 고쳤다.
- 최종 전체 backend: 위 Run의 정확한 명령 → **FAIL: 5,779 passed·5 skipped·1 failed**, 19 warnings, 235.98s. 단일 실패 `test_backfill_us_stocks.py::test_columns_match_korean_schema`는 기존 KR parquet와 US COLUMNS 불일치다. 소스·데이터는 이번에 수정하지 않았으며 금지된 엔진/데이터를 바꿔 통과시키지 않았다. ALL PASS는 미충족이다. 로그 `/tmp/simons-stage3-backend-final.txt`.
- 최종 frontend: `npm run test:frontend` → **PASS: 333 files·2,430 tests**, 1 file/2 tests skipped, 53.48s. opt-in 표시 두 검사는 별도 replay 실행과 구분한다. 로그 `/tmp/simons-stage3-frontend-last.txt`.
- 최종 replay: 위 Run 명령 → **7 PASS·1 FAIL**, exit 1. FAIL은 제품 결함이며 하네스 자체의 실패가 아니다. `/tmp/simons-stage3-replay.json`은 합성 API/표시/해소 근거를 담는다.
- `git diff --check`와 신규 파일 공백 확인 **PASS**. `docs/nl_interpretation_contract.md`도 검토했으며 공개 StrategyIntent/StrategySpec/JSON Patch와 기존 auxiliary 실패 계약은 변경하지 않았다. 문서 반영은 별도 G에서 이 보고·PROJECT_PLAN·software_architecture·SRS에 수행한다.

## 남은 지원 범위와 단계 게이트

- 표시 helper의 Vitest 기본 한국어 페이지 문맥과 실제 `/us` 영문 페이지 렌더링은 구분한다. positions-us의 backend US 필드/기존 조건 보존은 재생했지만 해당 fixture 표시를 실제 `/us` 페이지 검증으로 부르지 않는다. 3단계 제품 변경은 KR 생성 범위다.
- **NOT_RUN**: 운영 모델 KR/US의 새 생성·수정·fill, 새 KR 81예시 live 게이트, 실모델 변동성·지연 측정. 약 430모델 호출의 예시 게이트를 승인 없이 실행하지 않았다. 2단계의 오래된 저장 81예시 안내 enum 1건 FAIL을 새 해석 결과로 바꾸지 않았다.
- 수정 턴·ETF 테마 승격·US 업종/테마·지정 종목 warning 전체의 안내 단일 조립은 확장 범위다. 이번 변경은 생성 KR sector 검증에서 나온 소스만 소유하며, 모든 notices가 하나의 공통 승인 결과를 소비한다고 주장하지 않는다.
- 4단계에서는 각 보조 판정의 candidate_id/change_group_id/status/reason/evidence/stage를 공통 내부 결과로 연결하고 기존 조건·독립 변경 보존과 그룹 원자성을 검증해야 한다. 기존 patch_applier/primary/interpreter/tests는 W 허용이며, 새 공통 승인 모듈과 pipeline의 일반 판정 전달 범위는 구현 전 정확히 선택·등록해야 한다. 5단계의 필수 판정 보류 정책은 별도 승인 전 유지한다.
- 코드는 `/Users/eugene/nullalgo/simons-wt/interpretation-replay-stage2`의 미커밋 변경이다. 원래 backend에 복사하지 않았고 커밋·푸시·배포·운영 DB/어휘집/parquet 갱신을 하지 않았다. 사용자 §11 단계 게이트에 따라 여기서 멈춘다.
