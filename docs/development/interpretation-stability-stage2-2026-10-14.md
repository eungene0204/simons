# 전략 해석 안정화 — 2단계 로컬 하네스·API·표시 replay, 2026-10-14

**잘못된 검수 입력과 불완전한 재생을 통과로 세던 길을 막았으며, 미수리 제품 결함을 동일한 고정 출력으로 다시 드러낼 수 있다.**

1. 질문지와 주문서가 맞는지 먼저 확인한다(하네스 사전검사). 이미 채운 칸을 빈칸이라고 묻는 사례는 모델에 보내지 않는다.
2. 녹화된 심사 결과와 조회 결과만 사용한다(replay). 녹화가 없거나 요청이 다르면 실행을 중단하며, 운영 모델·검색·공유 어휘집으로 보충하지 않는다.
3. 최종 배송 목록과 안내를 사람이 정한 기대값에 대조한다(상태·조건·안내 판정). 북극항로 안내와 정성 수익률 0 확정은 아직 FAIL이다.
4. 다른 모델·캐시·지역·대화 모드·미완료 실행은 별도 집계한다(측정 manifest). 합성 결과를 운영 해석 품질로 읽지 않는다.

한 줄로: 검수와 재생 도구를 만들었고, 제품 수리와 운영 검증은 남아 있다.

## 초기 구현 기록 — 후속 승인 전

아래는 primary 반환까지만 지원했던 첫 구현 당시 기록이다. 현행 관찰·API·표시 지원과 최종 검사 결과는 마지막 후속 절을 따른다. 과거 검사 결과를 지우거나 현재 결과로 합산하지 않는다.

## 초기 명세와 작업 위치

- Task: 승인된 2단계의 하네스 입력 검증·결정론 primary replay 구현 및 로컬 검증.
- Boundary: 코드 작업은 W, 이 보고와 관련 문서 반영은 별도 G 작업. 경계 정의를 임의로 확장하지 않았다.
- Files allowed / 실제 코드 변경: `scripts/qa_free_input.py`, `scripts/qa_template_detect.py`, `backend/tests/test_qa_template_detect_verdict.py`, `backend/tests/interpretation_replay.py`, `backend/tests/interpretation_replay_contract.py`, `backend/tests/test_interpretation_replay.py`, `backend/tests/test_qa_interpretation_harness.py`, `backend/tests/fixtures/interpretation_replay.json`.
- 작은 작업 단위: 자유입력 하네스·회귀, replay 실행기, fixture 계약·판정기, CLI·최소 corpus·회귀. 각 단위는 1~5파일로 나눴다. 전체 단계의 누적 변경을 한 작은 diff라고 주장하지 않는다.
- Do not: 제품 의미 해석·보조 판정 실패 정책·API 응답 계약 변경, 원문 regex 추가, 운영 DB/어휘집/parquet 변경, 모델·검색 신규 호출, 커밋·푸시·배포.
- Requirements: 실행 전 모순 검사, 전체 조건 검사, 안내 채점, 저장 결과 누락 시 재생 중단, 실행 완료·모델·캐시·지역·모드 분리.
- Run: 아래 정확한 명령과 상태를 따른다. 전체 suite의 합격 조건 ALL PASS는 현재 충족하지 못했다.
- Deliver: 격리 작업트리의 미커밋 구현·fixture, 현재 결과와 한계. 전체 안정화 및 전체 2단계 지원 범위는 미완료다.
- 코드 작업트리: `/Users/eugene/nullalgo/simons-wt/interpretation-replay-stage2`, 브랜치 `wt/interpretation-replay-stage2`, 기준 HEAD `4e048137`. 요청대로 `scripts/worktree.sh new interpretation-replay-stage2`로 생성했다. 원래 작업공간의 1단계 문서와 다른 세션 변경은 보존했다. 원래 backend에 코드를 복사하지 않았다.

## 구현과 변경 전후

| 항목 | 변경 전 | 변경 후 |
|---|---|---|
| 같은 지표의 두 조건 | 첫 PER 불일치에서 실패 | 목록 전체 검색. >=5 다음 <=10에서도 <=10을 확인 |
| 없는 값과 0 | value=None도 0으로 판정 가능 | 실제 수치가 있는 경우만 비교, bool 제외 |
| 빈칸 QA 입력 | 질문·초안 충돌을 모델로 전달 | 슬롯·질문·UI 정본·pending topic·현재 값을 검사하고 HARNESS_INVALID로 실행 제외 |
| 안내 미검토 | 상태 필드가 맞으면 안내와 무관하게 PASS | live 자유입력에서 미검토 notices는 NOT_RUN. replay는 사람이 적은 채널 기대값으로 PASS/FAIL |
| 타임아웃/응답 없음 | ERROR 또는 처리 중단 | INFRA_BLOCKED로 분리; 제품 실패로 세지 않음 |
| 질문만 있는 미반영 | ASK를 별도 집계 | 기대 질문을 검토하지 않은 legacy 사례는 NOT_RUN. 정당한 질문을 제품 FAIL로 단정하지 않음 |
| 캐시·모델 누락 | 필드가 맞으면 PASS | 실제 runtime이 있으나 캐시이거나 모델 라벨을 확인할 수 없으면 NOT_RUN |
| 실행 중단 | 끝나야 결과 저장, 이전 파일을 오독할 위험 | 기준 전략 호출 전부터 새 run_id와 completed=false를 기록, 사례별 갱신, 종료 후 true |
| 캐시 검증의 응답 누락 | 건너뛰고 치명 0/exit 0 가능 | HARNESS_INVALID로 기록, 실패 exit. 대상 0건도 통과하지 않음 |
| 고정 결과 재생 | 임시 조사 스크립트 | `--replay` CLI, 최소 fixture와 반복 가능한 검사 |

free-input 결과 파일은 기존 행 배열에서 `{execution_mode, family, run_id, completed, rows}` manifest 객체로 바뀌었다. 성공 응답 행에는 reported_model/cache_hit/region/completed 메타를 추가했다. 사용자 API 계약 변경은 아니다. CLI는 미검증·실패·잘못된 입력이 있으면 exit 1이며, 과거 ASK/COLLATERAL 결과를 새 통과 숫자와 직접 비교하지 않는다.

현재 작업트리의 **기존 KR 캐시 초안만 읽은 사전검사**는 43사례 중 11개 유효, 32개 HARNESS_INVALID다. 최대 보유 5·리밸런싱 6·손절 5·익절 5·기간 5·자본 6개가 이미 채워진 칸을 묻는다. 실제 모델 호출이나 제품 실패율이 아니다. 실제 사용자 대화를 고쳐 쓰지 않았으며, 나머지 32사례의 올바른 합성 초안·기대 동작은 별도 사람이 검토해야 한다.

## replay 계약과 관찰 범위

- 입력은 기존 StrategyIntent/ParsedStrategy를 담는 테스트 fixture이며 새 서비스 DSL이나 Agent/State를 만들지 않았다. case_id·mode·region·operation·user_input·previous_parsed·실제 질문/pending·explicit·전체 요청 내용+SHA256·최초 출력·순서 있는 보조/지식 결과·설정·모델/캐시/완료/버전·사람 기대값을 저장한다.
- 외부 녹화는 호출 대상과 **정확한 요청 입력**을 대조한다. 누락·변경·남은 미소비 결과는 HARNESS_INVALID다. 실제 검사기의 broad Exception/fail-open에 삼켜지지 않도록 테스트 전용 중단 예외를 사용한다. 녹화에 실패가 명시돼 있으면 해당 실패를 재생할 수 있으며, 제품 실패 정책은 그대로다.
- 원본 StrategyIntent JSON은 기존 output_repair/Pydantic으로 읽고, primary 후처리·패치·검증·컴파일·primary 최종 응답을 실제 실행한다. 초기 Interpreter의 새 해석·재생성·recall 호출을 측정하는 live 모드는 아니다.
- 테마 적용·업종 조회·검색/어휘집·Planner 결과는 등록한 외부 경계에서 녹화된 결과로 고정한다. 지식 결과의 상태 변경은 유니버스 필드로 제한한다. 공유 KG/어휘집 접근과 socket/DNS 접근은 차단한다. 알려지지 않은 외부 호출도 녹화 없이 통과하지 않는다.
- 검사기 요청/결과, validation/compile 입력·출력, patch 적용 시도와 그 결과, 최종 parsed·notices·clarification·칩·pending/출처 메타를 JSON 리포트로 남긴다. patch_attempt는 최종 승인된 패치라고 부르지 않는다. 변경 그룹 승인 기록과 안내별 공통 provenance는 이후 단계 대상이다.
- 사람 기대값은 전체 목록의 선택 필드를 중복까지 비교할 수 있다. 배열 순서만 바뀐 AND 항목은 동일하게 읽고 중복 추가는 검출한다. 역할은 entry/exit 경로, 연산자·값·기간은 명시 기대값으로 비교한다. 정수/실수의 동등한 값은 동일하게 읽는다. 원문 regex로 기대값을 생성하지 않는다.
- notices/clarification_question/clarification_suggestions의 기대 채널을 요구한다. 규칙은 사람이 작성한 equal/require/forbid이며, 원문에서 미지원 의미를 다시 추론하지 않는다.
- 저장 요청의 생략 표지·해시 불일치·누락 모델/버전·미완료 실행을 사전 거부한다. 기록 모델/캐시/origin/versions뿐 아니라 실제 실행 소스 해시·지역·모드도 집계 키다.

## 최소 corpus와 결과

| case_id | 모드/지역 | 사람 기대 | 최종 상태 |
|---|---|---|---|
| arctic-notice | create/KR | 해소된 테마·종목이 있고 목록 밖 안내는 없음 | FAIL: 테마는 반영됐지만 목록 밖 안내 잔존 |
| qualitative-unresolved | create/KR | 임의 0 조건 확정 없음, 수익률 기준 질문 | FAIL: relative_return > 0 확정, 질문 없음 |
| holding-create | create/KR | 인용·단위에 맞는 최대 보유 10거래일, 잘못된 청산 신호 없음 | PASS |
| positions-kr | modify/KR | 보유 수 8, 기존 PER 조건·손절 보존 | PASS |
| positions-us | modify/US | 보유 수 8, 기존 PER 조건·손절 보존 | PASS |
| entry-fill | fill/KR | 실제 빈 매수 칸에 PER <=10 추가, 다른 설정 보존 | PASS |

전부 **사람 작성 합성 사례**이고 모델 라벨도 synthetic-fixture다. 북극항로 조회는 최소 합성 2코드 결과이며 실제 테마 명부가 아니다. 전체 요청 내용도 합성 fixture의 문맥이며 운영 프롬프트 원본을 대신했다고 주장하지 않는다. 4 PASS·2 FAIL은 운영 120B/9B 품질이나 일반 발생률이 아니다. 반복 테스트는 같은 fixture에서 최종 응답 동일성과 입력 불변을 확인한다. 현재 CLI는 의도적으로 남긴 두 제품 결함 때문에 exit 1이다. 기대값을 느슨하게 고쳐 녹색으로 만들지 않았다.

## 실행 기록

- 수정 전 하네스 회귀: `cd <worktree>/backend && UV_CACHE_DIR=/tmp/simons-uv-cache uv run --frozen pytest tests/test_qa_interpretation_harness.py -q` → **FAIL 8건**. 원래 첫 항목/모순 입력/상태 분류 결함을 재현했다.
- 최초 수리 후 하네스+기존 질문 정본 → **PASS 10건**. 이후 중단·캐시/모델·안내·지역 집계 회귀를 추가했다.
- 관련 최종 검사: `cd <worktree>/backend && PYTHONPATH=/tmp UV_CACHE_DIR=/tmp/simons-uv-cache uv run --frozen pytest -p simons_stage2_guard tests/test_interpretation_replay.py tests/test_qa_interpretation_harness.py tests/test_qa_template_detect_verdict.py tests/test_strategy_conversation.py tests/test_quote_check.py tests/test_template_qa_regressions.py -q` → 513 passed (마지막 지역 집계 1건 추가 전). 해당 추가를 포함한 최종 상태는 아래 전체 suite로 검사했다.
- 최종 전체: `cd <worktree>/backend && PYTHONPATH=/tmp UV_CACHE_DIR=/tmp/simons-uv-cache uv run --frozen pytest -p simons_stage2_guard tests/ --ignore=tests/test_backtest_engine.py --ignore=tests/test_engine_ai.py --ignore=tests/test_ai_sell.py --ignore=tests/test_api_isolation.py` → **FAIL: 5,755 passed·5 skipped·1 failed, 19 warnings, 164.32s**. ALL PASS 아님.
- 유일한 실패는 `test_backfill_us_stocks.py::test_columns_match_korean_schema`: 미국 `COLUMNS`와 한국 parquet 컬럼이 다르며 한국 쪽에 fcf_margin 등 5개가 더 있다. 해당 소스·데이터는 이번 변경에 포함되지 않았다. W의 엔진/데이터 변경 금지와 요청의 데이터 갱신 금지에 따라 수정하지 않았다.
- 첫 전체 시도 5,740 passed·5 skipped·8 failed는 버리지 않는다. socket 전체 차단 가드가 테스트의 자체 로컬 HTTP 서버도 막아 취소 검사 2건을 실패시켰다. 가드를 고쳐 테스트가 스스로 bind한 loopback 포트만 허용해 해결했다. RAG 5건의 외부 HuggingFace 확인 시도는 HF_HUB_OFFLINE=1로 기존 로컬 캐시를 사용해 해결했다. 최종에는 둘 다 통과했다. 임시 검사 가드는 `/tmp/simons_stage2_guard.py`, 로그는 `/tmp/simons-stage2-backend-final2.txt`다.
- 최종 재생: `cd <worktree> && UV_CACHE_DIR=/tmp/simons-uv-cache uv run --frozen python scripts/qa_template_detect.py --replay backend/tests/fixtures/interpretation_replay.json --out /tmp/simons-stage2-replay-final.json` → **제품 기준 FAIL 2·PASS 4**, 모드/지역별 4그룹, 신규 모델 호출 0. 테스트 도구의 정상 결함 탐지와 제품 통과를 구분한다.
- tracked 변경 `git diff --check`와 신규 파일 공백 검사는 **PASS**. 운영 모델·검색 신규 호출 **0회**. 프론트 코드 변경 없음; npm/frontend/display live 게이트는 **NOT_RUN**. 커밋·푸시·배포·운영 DB/어휘집/parquet 갱신 없음.

## 승인된 2단계 후속 — 전체 로컬 관찰·API·표시 연결

사용자가 남은 2단계 진행을 승인했다. 정확한 관찰·표시 경로를 별도 G 작업으로 W에 추가하고 다음 코드 작업을 W 안에서 수행했다.

- Task: 잘리지 않은 앞으로의 로컬 기록을 재생 입력으로 연결하고 실제 API 후처리와 기존 프런트 표시 함수를 실행한다.
- Boundary: W. 문서 갱신은 별도 G 작업이다.
- Files allowed / 실제 후속 변경: `backend/observability/tracing.py`, `backend/observability/agent_trace.py`, `backend/main.py`, `backend/strategy_conversation/primary.py`, `backend/strategy_conversation/interpreter/llm_strategy_interpreter.py`; `backend/tests/interpretation_api_replay.py`, `interpretation_display_replay.py`, `interpretation_trace_fixture.py`, 기존 replay/contract/fixture와 관련 회귀; `scripts/qa_template_detect.py`, `scripts/qa_kr_display_sweep.test.ts`, `tests/interpretationReplayDisplay.test.ts`.
- Do not: 자연어 의미·판정 실패 정책·모델 선택·실행 순서·API 계약 변경, 원문 regex 추가, 운영 데이터·어휘집 변경, 외부 모델/검색 호출, 커밋·푸시·배포.
- Requirements: 원본+해시+완료 식별, 실제 응답 모델·provider·생성 메타, 전 단계 고정 의존 결과, API 변환·출처·field_states·사용자 채널 및 실제 표시 함수 재생, 기록 실패가 실행을 바꾸지 않을 것.
- Run / Deliver: 아래 최종 검사와 한계를 그대로 보고한다. 전체 안정화나 운영 모델 정확성의 완료를 뜻하지 않는다.
- 후속 독립 단위: 전체 snapshot·회귀(2파일), 의존 관찰·API 연결(3파일), Interpreter 관찰(1파일), API replay·회귀(3파일), Trace→fixture 연결·회귀·CLI(3파일), 표시 연결·CLI·합성 기대·coverage·회귀(5파일). 누적 변경은 하나의 작은 diff가 아니다.

### 기록과 재생의 경계

1. 봉투 겉면의 짧은 요약과 내용물 원본을 나눈다(Trace preview / local replay snapshot). 긴 프롬프트·배열·출력은 로컬 metadata의 `replay_inputs/replay_outputs/replay_evidence`에 전체 JSON과 SHA256을 저장한다. preview와 외부 telemetry에는 기존 길이 제한을 유지한다. 자격증명 필드가 가려지거나 직렬화할 수 없으면 complete=false다. 기존 같은 날짜 JSONL과 3일 삭제 정책을 그대로 사용한다.
2. 심사자가 실제 사용한 서류를 함께 기록한다(Interpreter checkpoint / model evidence). 최초 LLM 요청·원본 응답, 복구/recall 이후 intent, unreflected_numbers, 실제 requested/served model·provider와 생성 메타를 기록한다. 재생은 기록된 Interpreter 완료 경계부터 시작한다. 초기 추출·recall·복구 LLM을 다시 실행해 품질을 측정한 것이 아니다. 버전 해시는 당시 디스크 소스 식별이며 메모리에 로드된 빌드의 독립 증명은 아니다.
3. 외부 조회는 저장된 관찰만 소비한다(ordered dependency tape). 지식·테마·Planner 외부 경계의 입력/출력/유니버스 변경을 기록한다. API converter가 소비한 종목 목록과 종목명은 이미 계산된 API 결과의 projection으로 기록하며 다시 조회하지 않는다. `source=converted_universe_checkpoint/consumed_name_projection`이며 전체 stock profile을 녹화했다고 부르지 않는다. 실제 profile review는 기존 호출 결과를 별도로 관찰한다. 누락·다른 요청·알 수 없는 외부 의존은 HARNESS_INVALID로 중단한다.
4. 배송과 진열을 기존 코드로 수행한다(API / frontend). `_build_parse_result` → `apply_primary_meta` → `_finalize_parse_result`를 실행해 백테스트 요청·출처·field_states·artifacts·질문/칩을 얻는다. elapsed time과 출처 갱신 시각은 재생의 테스트용 시계로 고정한다. 기존 `buildBuilderTurnPresentation/listStrategyItems/attachFieldStates`로 요약·설정·진행 표시를 만들며 notices·질문·칩도 표시 증거에 싣는다. 종목 수가 손절 값에서 발견됐다고 통과하지 않도록 해당 표시 행을 검사한다.
5. 사람 정답과 기록을 결합한다(Trace bridge). `--replay-trace <JSONL> --replay-expectations <JSON>`은 trace_id별 사람이 작성한 case_id/mode/operation/expected(빈칸이면 slot 포함)를 필요로 한다. 생략/해시 불일치·미완료·모델 누락·모드 충돌·캐시 실행은 거부한다. fixture와 표시 입력은 메모리/임시 디렉터리에만 두고 삭제한다. captured 모드의 `--out`은 금지하고 콘솔에는 원문 없는 상태·측정 식별만 남긴다. 과거 잘린 Trace를 복구하거나 현재 출력으로 gold를 만들지 않는다.

예시(완전한 기록과 별도 사람 기대가 있는 경우만):

```sh
UV_CACHE_DIR=/tmp/simons-uv-cache uv run --frozen python scripts/qa_template_detect.py \
  --replay-trace backend/logs/agent_traces/YYYY-MM-DD.jsonl \
  --replay-expectations /tmp/reviewed-trace-gold.json
```

현재 capture→replay 테스트도 합성 실행이며, 과거 운영 사건의 전체 녹화 재생이나 신규 live 평가가 아니다. 잘린 과거 원본은 여전히 복구할 수 없다. unknown dependency가 있는 기록은 지원 완료로 세지 않는다. 장기 회귀 corpus는 합성 6건만 유지한다.

### 후속 검증 결과

- API·표시 통합 replay: **PASS 4 / FAIL 2**, 신규 모델·검색 호출 **0**. 북극항로는 테마 표시 자체가 맞아도 모순 notices 때문에 전체 FAIL이다. 정성 수익률은 구조화 조건과 매수 요약의 확정 표시 모두 FAIL이다. 나머지 4건은 구조·보존·안내·해당 행 표시를 통과했다. CLI exit 1은 남은 제품 결함의 정확한 검출이다.
- 통합 관련 검사: `cd <worktree>/backend && PYTHONPATH=/tmp UV_CACHE_DIR=/tmp/simons-uv-cache uv run --frozen pytest -p simons_stage2_guard tests/test_ai_runtime_latency.py tests/test_interpretation_trace_fixture.py tests/test_interpretation_replay.py tests/test_replay_trace_capture.py -q` → **43 passed**, 이후 API 기록 실패 회귀 1건 추가는 전체 검사에 포함한다.
- 저장 응답 표시 전수: `QA_DISPLAY_SWEEP=1 node_modules/.bin/vitest run scripts/qa_kr_display_sweep.test.ts` → **FAIL 1**, 캐시 81/81, 누락 0. '박스권 상단 돌파 따라가기'의 오래된 notices에 crosses_below/crosses_above가 남는다. 현재 코드 재해석 결과가 아니며 캐시를 새 결과로 덮어쓰지 않았다. 요청된 sweep에서 캐시/응답 누락은 이제 HARNESS_INVALID 실패이며, 기본 suite의 opt-in 미실행과 구분한다.
- 중간 실패도 보존한다: 관찰 코드가 `_DummyParsed.target_symbols`를 직접 읽어 기존 API 테스트 2건을 실패시켰다. 관찰 전용 함수로 옮겨 오류를 삼키고 실행과 캐시/SSE를 보존했다. 새 표시 회귀의 universe 없는 테스트 입력 1건은 합성 초안을 보완해 수정했다. 마지막 전 전체 frontend의 별도 `lib/krx-stocks.test.ts` 종목명 캐시 1건 실패는 독립 실행 4/4에서 재현되지 않았다. 해당 코드·테스트·데이터는 변경하지 않았다. 아래 최종 결과와 합산하지 않는다.

- 최종 전체 backend: `cd <worktree>/backend && PYTHONPATH=/tmp UV_CACHE_DIR=/tmp/simons-uv-cache uv run --frozen pytest -p simons_stage2_guard tests/ --ignore=tests/test_backtest_engine.py --ignore=tests/test_engine_ai.py --ignore=tests/test_ai_sell.py --ignore=tests/test_api_isolation.py` → **FAIL: 5,769 passed·5 skipped·1 failed**, 19 warnings, 233.60s. 유일한 실패는 기존 `test_columns_match_korean_schema`의 KR parquet/US COLUMNS 불일치이며 변경 금지된 엔진/데이터를 고치지 않았다. ALL PASS 조건은 미충족이다. 로그 `/tmp/simons-stage2-backend-final.txt`.
- 최종 전체 frontend: `npm run test:frontend` → **PASS: 333 files·2,430 tests**, 1 file/2 tests skipped, 55.95s. skip은 opt-in KR sweep과 별도 데이터 입력 없는 display replay이며, 둘 다 요청 실행 결과는 위와 별도로 기록했다. 마지막 전 종목명 캐시 실패는 전체 재실행에서도 재현되지 않았지만 불안정 이력으로 보존한다. 로그 `/tmp/simons-stage2-frontend-last.txt`.
- 최종 replay 명령: `UV_CACHE_DIR=/tmp/simons-uv-cache uv run --frozen python scripts/qa_template_detect.py --replay backend/tests/fixtures/interpretation_replay.json --out /tmp/simons-stage2-replay-final-complete.json` → 제품 **4 PASS·2 FAIL**, 표시만 5 PASS·1 FAIL, exit 1. 하네스 오류·외부 모델 호출은 0이다. 북극항로 표시 PASS를 모순 안내 전체 PASS로 세지 않는다.
- 초기 후속 전체 3 failed·5,766 passed·5 skipped(253.09s)는 관찰 결함 2건과 데이터 스키마 1건을 포함했다. 수정 후 전체는 데이터 스키마 1건만 남는다. 실패를 제거하려고 검사 범위나 gold를 느슨하게 하지 않았다.
- 최종 bridge 검사 `PYTHONPATH=/tmp UV_CACHE_DIR=/tmp/simons-uv-cache uv run --frozen pytest -p simons_stage2_guard tests/test_interpretation_trace_fixture.py -q`는 **10 passed**, 10 warnings, 9.49s다. tracked `git diff --check`와 신규 파일 공백 검사 결과는 PASS다. 공유 원문 3일 정책 유지, 외부 모델/검색 0회, 커밋·푸시·배포·DB/어휘집/parquet 갱신 없음. 신규 추적 파일은 합성 테스트의 임시 디렉터리에서만 생성했다.

### 남은 범위와 다음 단계 게이트

- Agent 실행 단계·순서·분기·가드를 바꾸지 않았으므로 AgentsTab 흐름도 변경 대상은 아니다. 추가한 span은 관찰 증거만 기록한다.
- 공통 ACCEPT/REJECT/UNRESOLVED 승인, 변경 그룹 최종 승인/provenance, 안내 단일 조립과 보류 정책은 구현하지 않았다. 기록된 patch_attempt를 최종 승인 패치라고 부르지 않는다.
- live KR/US 생성·수정·fill과 실제 모델별 변동성/지연/호출 수 게이트는 **NOT_RUN**이다. 6건 합성과 source hashes로 운영 120B/9B의 정확성을 주장하지 않는다.
- 3단계는 생성 테마/업종의 안내 조립부터다. `response/notice_assembly.py`, `validation/pipeline.py`의 구조 결과 전달, `capability_validator.py`의 sector 결과 범위를 W에 좁게 추가하는 승인이 필요하다. 기존 primary/models/tests/AgentsTab 허용은 재사용한다. 보조 실패의 행동 계약 변경은 5단계 승인 전 유지한다.
- 사용자 요청 §11의 단계 게이트에서 멈춘다. 다음 단계와 커밋·푸시·배포를 선행하지 않는다.
