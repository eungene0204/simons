# 전략 해석 안정화 — 5단계 승인 정책 구현

Task:
사용자가 승인한 9개 필수 판정 정책을 기존 호출 대상에 적용하고 미해결 신규/교체 그룹 보류·기존 상태/독립 변경 보존을 검증한다.

Boundary:
W. 명세·경계·완료 문서는 별도 G 작업이다.

Files allowed:
- backend/strategy_conversation/interpreter/** (existing checks, decisions, internal required-verdict policy)
- backend/strategy_conversation/conversation/patch_approval.py
- backend/strategy_conversation/primary.py
- backend/tests/**
- components/admin/AgentsTab.tsx (flow sync only)

Do not:
- 사용자 원문 의미 regex/키워드 추가, 새 모델/프롬프트/호출 대상 확장
- State·DSL·공개 스키마 변경, 엔진/컴파일러/DB/어휘집/parquet 변경
- 커밋·푸시·배포·외부 모델/검색 호출

Requirements:
- Q/T/R/N/M/C/P/H/G의 기존 적용 대상별 필수 근거 및 후보/그룹 연결
- 일/월/년과 한글 수량은 LLM 출력 근거·정본 환산으로 확인; 원문 어휘 해석 금지
- REJECT/UNRESOLVED 신규 변경을 보류하고 교체 전체·기존 조건·독립 승인 변경 보존
- 보류와 미지원 구분, 필요한 질문 우선·기존 큐 결속, 정성 수익률 0 확정 제거
- 공개 계약 및 기존 검사 대상/호출 예산 유지, 현재 재현 gold 완화 금지

Run:
- 관련 regression을 먼저 변경 전/후 대조
- cd <worktree>/backend && PYTHONPATH=/tmp UV_CACHE_DIR=/tmp/simons-uv-cache uv run --frozen pytest -p simons_stage2_guard tests/ --ignore=tests/test_backtest_engine.py --ignore=tests/test_engine_ai.py --ignore=tests/test_ai_sell.py --ignore=tests/test_api_isolation.py
- npm run test:frontend
- UV_CACHE_DIR=/tmp/simons-uv-cache uv run --frozen python scripts/qa_template_detect.py --replay backend/tests/fixtures/interpretation_replay.json --out /tmp/simons-stage5-replay.json
- git diff --check; 성공 조건 ALL PASS, 범위 밖 기존 데이터 FAIL은 원인과 미수리 이유 보고

Deliver:
- /Users/eugene/nullalgo/simons-wt/interpretation-replay-stage2의 미커밋 변경, 기존 단계·타 세션 보존
- 각 1~5파일 독립 단위로 구현/회귀, 마지막 G 문서 갱신
- 전후 재생·전체 검사·미실행 운영 범위·잔여 제한 보고 후 5단계 게이트 정지

## 승인과 구현 결과

2026-10-14 사용자의 “구현 진행 해”로 [5단계 정책안](interpretation-stability-stage5-policy-2026-10-14.md)이 승인됐다. 코드 반영·로컬 검증은 끝났으며 전체 ALL PASS 및 운영 검증은 미충족이다.

1. 검수표에 “이 항목에 필요한 검사인가”를 먼저 적듯, `interpreter/required_checks.py`의 요청별 계획은 기존 검사 대상과 REQUIRED/NOT_APPLICABLE을 구분한다. 의미 판정의 ACCEPT와 현재 적용 정책을 혼동하지 않고 Q/T/R/N/M/C/P/H/G의 실제 결과·누락을 후보/그룹과 연결한다. 기존 State·공개 스키마·검사 프롬프트·모델은 유지했다.
2. 확정하지 못한 새 서류만 보류하듯, 생성은 미해결 새 조건을 실행 상태에서 제외하고 필요한 질문을 우선한다. 수정/fill은 사본의 미해결 조건을 제외한 뒤 기존 조건을 복원한다. 시장/조건 scope·수치·실제 보유기간 대조의 미해결 패치도 보류하며 독립 수량·다른 확인된 조건을 유지한다. 같은 조건의 형제 패치와 확인된 remove/add 교체를 반쪽으로 적용하지 않는다.
3. 정성 수익률 분류 None/unclear/형식 오류는 `relative_return > 0` 확정을 막고 수익률 질문을 우선한다. 의미가 확인되고 수치만 없으면 기존 missing/pending_conditions로 이어진다. 보류를 “미지원”으로 표시하거나 LLM 장애를 사용자 표현 오류로 바꾸지 않는다.
4. 단위가 붙은 숫자 서류를 환산하듯, 기존 holding 대조가 실제 호출된 대상에서 LLM의 number_text·단위·인용을 확인하고 1/21/252 거래일로 환산한다. 한글 수량은 **LLM 수량 출력 필드만** 숫자 표기로 정규화하거나 LLM이 제공한 count를 검증한다. 사용자 문장에 새 regex/어휘 매칭을 추가하지 않았다. 정상 일·월·년과 한글 수량은 기존 1회 호출로 처리하고, 확인 실패가 추가 numeric 호출을 만들지 않는다. residual 대조 대상 밖에 호출을 새로 만들지 않았다.
5. 지역 분류는 실제 universe 후보·패치 그룹에 연결했다. 지역이 KR/OTHER라는 분류만으로 정본 종목 해소를 승인하지 않는다. 실제 보조 지역 대상의 미해결/US 거부는 수정에서 이전 universe를 유지하고 독립 수량을 적용한다. 대상 밖의 기존 지역 격리 거절은 유지한다. 다른 universe 필드와의 독립성을 증명하지 못하면 해당 universe 후보를 함께 보류한다.
6. 검증된 복구는 원 서류를 덮는 대신 새 서류 번호를 남기듯, breakout과 적립식 상태 연산자 복구는 새 candidate와 부모/근거를 기록한다. 확인된 상태 연산자 변환으로 원 MA 후보의 미해결을 해소할 수 있지만, 명시적 REJECT는 되살리지 않는다. 승계된 이전 후보는 상태 계산에서 제외하고 과거 충돌·superseded 후보는 추적에 남긴다. contribution 검사를 새 필수 검사로 확대하지 않고 기존 확인 결과의 정당한 복구만 연결했다.
7. 순차 JSON Pointer 정체성·기준 초안 해시와 실제 차분은 4단계 모듈을 재사용한다. 미해결 whole-list 재작성의 다른 파괴적 목록 쓰기가 독립적이라고 증명되지 않으면 양쪽 기존 목록을 보존한다. 최종 질문은 하나만 발행하고 기존 질문 큐를 이월한다. 사본의 승인 결과는 기존 스키마·도메인 검증·컴파일을 거친다.

### 5단계 변경 파일

- 새 정책/회귀: `backend/strategy_conversation/interpreter/required_checks.py`, `backend/tests/test_required_verdict_policy.py`, `test_required_verdict_dependencies.py`.
- 적용/기록: `backend/strategy_conversation/primary.py`, `interpreter/decisions.py`, `holding_period_check.py`, `relative_return_check.py`, `contribution_plan_check.py`, `conversation/patch_approval.py`.
- 재생: `backend/tests/interpretation_replay.py`는 완료 Interpreter 안에서 실행된 holding 요청/응답을 interpreter_recordings tape로 복원한다. 원래 후보 값·요청을 복원해 실제 기존 체크를 실행하며 요청/후보 불일치는 HARNESS_INVALID다. 새 모델 호출은 없다. `test_interpretation_replay.py`의 알려진 FAIL 상태 표시는 실제 수리 뒤 PASS로 바꿨지만 **corpus의 사람 기대값·원문·출력/tape는 완화하거나 변경하지 않았다**.
- 기존 회귀의 확인 근거: `test_strategy_conversation.py`, `test_agent_audit3_fixes.py`, `test_cross_period_clarification.py`, `test_modify_roundtrip_migration.py`, `test_relative_return_indicator.py`. 의미 대조가 아닌 정상 안내·기간 옵션·시장/테마·변환을 검사하는 케이스에 명시적인 성공 판정 fixture를 공급했다. 실패/불명확 자체는 새 실제 checker 회귀에서 별도로 검증한다.
- `components/admin/AgentsTab.tsx`의 생성·수정 흐름과 실패/보류 설명을 동기화했다. 문서는 별도 G에서 W의 승인된 예외·자연어 계약·정책 상태·PROJECT_PLAN·software_architecture·SRS를 반영한다. 원래 checkout의 backend는 변경하지 않았다.
- 작은 단위는 정책과 기록(2파일), 기존 검사 연결(각 1~5파일), 사본 승인/복원(2파일), 정책 회귀(각 1파일), 재생/회귀(2파일), 기존 확인 fixture(4파일), 흐름도(1파일), 문서 G로 나눴다. 누적 변경은 200줄을 넘으며 한 작은 diff라고 표현하지 않는다. 이전 2~4단계 변경을 보존했다.

## 재현·전후 비교

- 최초 `test_required_verdict_policy.py` → **8 FAIL·1 PASS**, 0.29s. 수익률 0 확정, 미해결 조건 교체·시장 변경 적용, 월·년/한글 수량 확인 누락을 재현했다. 기존 명시적 day 환산 1건은 통과했다. `/tmp/simons-stage5-before.txt`.
- 신규 회귀는 총 **31건**이다. 기존 조건·독립 수량 보존, 거래대금 실패와 remove/add 교체, scope 누락, numeric 실패, KR/US/OTHER/누락 지역 판정, 일/월/년/한글 수량, 호출 예산, whole-list 삭제 보호, 취소 전파, 완료 Interpreter holding 재생, 복구 후보 정체성과 REJECT 비부활을 확인한다.
- 4단계와 같은 10건의 합성 primary→실제 API 후처리→프런트 표시 재생은 **9 PASS·1 FAIL → 10 PASS**다. qualitative-unresolved의 실행 신호는 `[]`, 질문은 “수익률은 시장과 비교할까요, 종목 간 순위로 정할까요?”, notices는 `[]`다. 기존 9 PASS를 유지했다.
- 보조 거부/미해결의 보류 사례는 같은 10건 안에서 2→3건이며, 질문 있는 사례는 10→10건이다. 정성 수익률의 무관한 익절 질문 1건을 필요한 수익률 확인으로 바꿨다. 운영 보류율·불필요한 질문율·전체 오류율 개선으로 일반화하지 않는다.
- 모델은 synthetic-fixture, schema 1.0, 엔진 16.40.0, 기반 코드 4e048137이며 최종 pipeline 콘텐츠 해시는 `2cd1555c9b96f55f0ca12e50b18ed3e98d4ae2fb871b370279bbc9fdd8f4d59c`다. 외부 모델/검색 호출 **0회**다. replay는 시간을 고정하므로 운영 지연은 측정하지 않았다.

## 실행한 검사와 중간 실패

- 관련 최종 명령: `cd <worktree>/backend && PYTHONPATH=/tmp UV_CACHE_DIR=/tmp/simons-uv-cache uv run --frozen pytest -p simons_stage2_guard tests/test_required_verdict_policy.py tests/test_required_verdict_dependencies.py tests/test_contributions.py tests/test_cross_period_clarification.py tests/test_agent_audit3_fixes.py tests/test_modify_roundtrip_migration.py tests/test_relative_return_indicator.py tests/test_strategy_conversation.py tests/test_interpretation_decisions.py tests/test_patch_group_approval.py tests/test_interpretation_replay.py -q` → **594 PASS**, 11 warnings, 11.46s. `/tmp/simons-stage5-related-repair-complete.txt`.
- 앞선 관련 9 FAIL·443 PASS는 새 필수 판정 근거가 없는 정상 회귀 fixture, 명확한 거부에 불필요한 질문을 붙인 새 처리, 원 모델의 구체 질문을 가린 새 처리, 수리된 replay의 FAIL 상태 표시에 기인했다. 거부는 기존 안내로 처리하고 미해결만 질문하며 원 모델의 구체 질문을 보존했다. 수정 후 관련 452/487/494/535/537건 묶음이 통과했다. 한 번의 추가 1 FAIL·493 PASS는 대조 테스트가 사전 recall 호출을 quote 호출로 센 잘못된 고정 응답 순서였다. 해당 단위에서 recall을 비활성화해 실제 quote 두 판정을 고정했다.
- 처음 전체 backend → **10 FAIL·5,814 PASS·5 skipped**, 19 warnings, 250.86s. 기존 parquet 실패 1건 외에 정상 보조 판정 fixture 누락 8건, 적립식 상태 연산자 복구가 원 MA 미해결 때문에 제거된 실제 회귀 1건을 발견했다. fixture는 원래 의미 기대를 보존하고 성공 판정을 명시했다. 적립식은 별도 확인된 복구 후보·근거/정체성 승계로 수리했다. `/tmp/simons-stage5-backend-final.txt`.
- 최종 전체 backend: 위 Run의 정확한 4개 ignore 명령, 외부 네트워크 차단 pytest 플러그인 → **FAIL: 5,828 passed·5 skipped·1 failed**, 19 warnings, 190.36s. 단일 실패 `test_backfill_us_stocks.py::test_columns_match_korean_schema`는 이전 단계와 같은 KR parquet와 US COLUMNS 불일치다. KR에 fcf_margin부터 5개 컬럼이 더 있으며 수집/데이터 코드·parquet는 금지 범위여서 수정하지 않았다. **ALL PASS는 미충족**이다. `/tmp/simons-stage5-backend-complete.txt`.
- `npm run test:frontend` → **PASS: 333 files·2,430 tests**, 1 file/2 tests skipped, 77.34s. `/tmp/simons-stage5-frontend-final.txt`. 이후 UI/프런트 코드는 변경하지 않았으며 backend 수리는 최종 API/표시 replay로 확인했다.
- 최종 replay: 위 Run 명령의 out 경로를 `/tmp/simons-stage5-replay-complete.json`으로 지정 → **10 PASS**, exit 0. `/tmp/simons-stage5-replay-complete.log`. 중간 최종 파일 `/tmp/simons-stage5-replay.json`도 10 PASS였으며 마지막 복구 수리 이후 결과와 구분한다.
- 작업트리 `git diff --check`와 새 정책/회귀 3파일 공백 확인 **PASS**다. 별도 G 문서의 diff·새 보고/정책 문서 공백·상대 링크·허용 경계 검사도 **PASS**다. 원래 checkout의 backend 코드 변경이 없고 타 세션의 기존 myth_series 변경을 보존했음을 확인했다.

## 지원 한계와 단계 게이트

- 기존 대상 밖의 조건을 새로 검사하거나 모든 UNRESOLVED를 전역 취소로 바꾸지 않았다. contribution/liquidity·일반 recall/planner/지식 조회·전체 ETF/US 체인·전역 도메인 결과의 그룹 분리는 확장 범위다. 기존 도메인 오류와 실제 보조 판정 밖의 지역 격리 거절은 안전 동작을 유지한다.
- 파괴적 목록 재작성 및 새 universe의 독립성을 증명하지 못하면 보수적으로 함께 보류한다. 모든 독립 삭제/전면 필드 재작성의 부분 승인을 보장하지 않는다. 실제 서버 요청 간 버전 충돌 검사는 4단계의 요청 내부 해시 대조와 구분한다.
- 모든 안내 생산자를 공통 최종 조립기로 이관한 것은 아니다. 생성 KR sector/theme은 3단계 조립을 유지하고 이번 보류 질문/안내를 연결했다. 기존 원문 의미 패턴 매칭은 **미이관 위반**이며 이번에 정상으로 승인하거나 확대하지 않았다.
- **NOT_RUN**: KR/US 운영 120B/9B 생성·수정·fill, 새 KR 81예시, 실제 `/us` 영문 페이지, 운영 변동성·지연·보류/불필요한 질문율. positions-us backend 재생과 기본 한국어 페이지 문맥의 표시 helper를 실제 영문 페이지 검증으로 읽지 않는다. 2단계의 옛 저장 안내 enum FAIL은 캐시 재작성이나 새 해석으로 바꾸지 않았다.
- 구현은 `/Users/eugene/nullalgo/simons-wt/interpretation-replay-stage2`의 미커밋 상태다. 커밋·푸시·배포·운영 DB/어휘집/parquet 변경 및 원래 backend 복사는 하지 않았다. 사용자 §11의 5단계 구현 보고에서 멈춘다. 다음 6단계 추가 회귀/운영 게이트는 별도 범위이며 live는 예상 호출 수 승인 후 실행한다.
