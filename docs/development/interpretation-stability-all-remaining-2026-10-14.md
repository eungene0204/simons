# KR 전략 해석의 남은 구현 전체

사용자 승인: “이번엔 모든 작업을 다 마무리 해.” 직전 대화에서 명시한 세 항목 전체를 구현한다. US와 게이트/검증 실행 제외는 유지한다. 아래는 각 별도 작업의 실행 명세이며 동시에 두 boundary를 수정하지 않는다. 기존 격리 작업트리를 사용한다.

Task:
프론트 턴 중재의 원문 의미 분기를 기존 LLM 분류의 구조화 축으로 옮긴다.
Boundary:
A
Files allowed:
- app/analytics/new/conversationDecision.ts
- app/analytics/new/page.tsx
- app/analytics/new/*test.ts*
- app/api/strategy/parse/stream/route.ts
Do not:
- 원문 regex 추가, US 전용 변경, UI 재설계
Requirements:
- 확인·연구 지표·후속 질문·기간 비교를 LLM 축으로 전달
- 분류 실패에서 원문 규칙 복구 금지
- 서버 revision 전달, 오래된 응답의 적용 차단
Run:
- 사용자 지시로 검증 실행 NOT_RUN; 추후 npm run test:frontend
Deliver:
- 미커밋 코드와 회귀 작성

Task:
KR 분류 축/빌더 레인, 고지 근거, 서버 요청간 CAS를 연결한다.
Boundary:
W
Files allowed:
- backend/intent/interpreter.py, schemas.py, classifier.py
- backend/intent/strategy_builder.py, builder_interpreter.py
- backend/api/intent_routes.py
- backend/strategy_conversation/response/notice_assembly.py, notice_evidence.py
- backend/strategy_conversation/conversation/versioning.py
- backend/strategy_conversation/primary.py, backend/main.py
- backend/tests/**
Do not:
- 새 Agent/DSL/전략 State 모델, DB/market data/schema 변경
- 외부 호출·커밋·배포·원래 backend 복사
Requirements:
- 빌더는 정본 칩의 정확 일치 외 자유 입력을 기존 LLM 레인으로 해석
- 모든 KR 고지 후보를 구조화 기록으로 전달하고 최종 값과 대조
- 서버가 보관한 revision/hash를 시작·반영 시 비교, stale/중복 경쟁 거절
- 회귀 코드는 작성하고 검증은 실행하지 않음
Run:
- NOT_RUN; 추후 backend/tests의 관련 회귀와 전체 기존 명령
Deliver:
- 각 1~5파일 독립 단위로 미커밋 구현, 최종 문서 G 별도

Task:
KR 레거시 파서의 자연어 패턴 경로를 기존 primary 레인으로 라우팅한다.
Boundary:
B
Files allowed:
- backend/engine/nl_parser.py
- backend/tests/**
Do not:
- 엔진 알고리즘·US 전용 동작·데이터 변경
Requirements:
- KR parse/modify/rule entry에서 원문 regex 해석 재활성화 금지
- 실패 시 기존 의미 보존/해석 실패 계약 사용
- 레거시 함수는 호환 정의만 보존, 활성 KR 해석기로 사용하지 않음
Run:
- NOT_RUN; 추후 관련 회귀와 기존 전체 backend 명령
Deliver:
- 미커밋 변경

Task:
전체 구현 상태와 제외한 검증을 기록한다.
Boundary:
G
Files allowed:
- docs/development/interpretation-stability-all-remaining-2026-10-14.md
- docs/PROJECT_PLAN.md, software_architecture.md, SRS.md, nl_interpretation_contract.md
- CLAUDE.md
Do not:
- 애플리케이션 코드 수정
Requirements:
- 현재 구현과 과거 검사 수치를 구분
- 이번 세 항목을 다시 잔여로 넘기지 않음
Run:
- 검증 실행 제외
Deliver:
- 완료 기록


## 완료 기록

앞서 남겼던 세 구현 항목을 모두 기존 격리 작업트리에 반영했다. US·게이트/검증 실행은 사용자 지시로 제외한다. 코드 작성 완료와 검증 통과는 구분하며, 원래 checkout의 backend에 복사하거나 운영에 적용한 상태가 아니다.

### 1. KR 원문 의미 분기의 활성 경로 이관

- 기존 의도 분류 LLM에 `turn_action`, `research_metric`, 인용된 `backtest_period_years` 축을 추가했다. 정형 축만 닫힌 enum/수치/인용으로 검증하고 API에서 전달한다. 분류 출력 예산은 280→400 tokens다. 별도 분류 Agent나 호출은 추가하지 않는다.
- 프론트 `decideConversationTurn`의 실행 확인·연구 지표·기간 비교·후속 질문은 이 축을 소비한다. 사용자 낱말을 정규식으로 재판정하지 않으며, 분류 장애는 실패로 표시한다. 규제 라벨을 연구 목표나 실행 축으로 우회하지 않고, UPDATE와 실행 확인의 구조화 충돌도 실행하지 않는다. 스트림 skeleton도 프롬프트에서 시장/지표/수량을 추출하지 않는다.
- KR 빌더의 시드·자유 답변·취소/재시작/확인·종목 지정은 기존 `builder_interpreter` ops로 처리한다. 정본 진입 칩은 실제 제시된 선택지의 정확 일치만 결속한다. LLM 실패·전량 거부에서 원문 규칙을 호출하거나 기존 완성 전략을 자동 확정하지 않는다. 미해결 투자 대상은 질문으로 남긴다. 수치/인용/정수/enum/정본 종목 lookup만 결정론으로 검사한다.
- KR `NLStrategyParser.parse/parse_modification`은 기존 primary로 보낸다. KR rule 진입과 원문 override는 비활성화한다. 환경 설정의 `legacy`/off/shadow가 KR 원문 패턴 경로를 다시 열지 않도록 primary와 classifier의 활성 선택도 연결했다. 레거시 함수 정의와 제외한 US 호환 분기는 보존하며 활성 KR 해석기로 쓰지 않는다.

### 2. 기존 고지 생산자의 구조화와 정합성 처리

- `notice_evidence.py`의 내부 receipt는 모든 고지에 ID·생산자·kind·소유 필드/값을 붙인다. 전용 생산자 근거가 없는 루트 문자열도 실제 관측 결과에 결속한다. 아무 근거 없는 자유 문자열을 무조건 최종 안내로 넘기는 경로를 없앴다.
- 기존 최소값 보정의 수치 계산은 바꾸지 않았다. `NoticeList`가 각 append 직전 실제로 변경된 필드를 따로 기록하므로 독립 종목 수 변경이 초기 자금 고지를 지우지 않는다. 지정종목 조정/리뷰·별칭·근사·랭킹·준비 중 데이터·조건 거부의 근거도 연결한다.
- 거부·보류의 사건 설명(TRANSITION)은 현재 값 설명과 구분한다. 최종 API 상태에서 소유 필드가 달라진 고지는 STALE로 제외하고 이유를 Trace에 기록한다. 되묻기/지원/근사 등 다시 조립한 고지는 현재 값으로 재결속한다. 내부 `_notice_context`와 `_notice_evidence`는 응답 전에 제거한다. 기존 문자열 반환형은 유지한다.

### 3. 실제 서버 요청 사이의 버전 충돌 검사

- `conversation/versioning.py`는 draft ID별 서버 revision/상태 hash/최신 요청 lease를 보관한다. 같은 파일 저장소의 process 간 `flock`과 임시 파일→원자적 교체를 사용해 여러 worker·서버 재시작에도 비교를 이어간다. 저장 값은 hash와 counter·시각·lease이며 사용자 원문/전략 본문/인증 정보를 저장하지 않는다. DB schema·market data 변경은 없다.
- 모델 처리 시작 전에 요청 revision·hash·실제 `previous_parsed`의 정규화 hash를 대조한다. Responder 직전에도 CAS로 대조하며, 같은 기준 상태의 새 요청이 먼저 시작됐다면 이전 요청의 늦은 결과는 반영하지 않는다. stale은 409, ledger I/O 실패는 503이며 추정/메모리 fail-open으로 적용하지 않는다. 취소는 반영 전에 전파한다.
- 옵션 요청 필드 `draft_id`, `expected_revision`, `expected_state_hash`와 옵션 응답 `strategy_version`을 추가했다. 기존 필드 이름/의미는 바꾸지 않는다. 식별자를 주지 않은 구형 단독 요청에는 새 draft를 발급하고 응답한다. 그 응답의 version을 에코하는 같은 draft의 후속 요청은 필수 대조 대상이다. 복원/새로고침한 채팅도 기존 메시지의 version과 원본 parsed를 에코한다. 명시적인 로컬 되돌림·새 대화는 새 draft 분기로 다룬다.
- 프론트는 표시용 병합본 대신 서버 원본 parsed와 version을 전달한다. 순서가 지난 응답의 값·진행 이벤트·오류가 최신 화면을 덮어쓰지 않게 한다. SSE와 비-SSE는 같은 서버 CAS 코어를 사용하며, SSE proxy가 version을 전달한다.

## 변경 파일

`/Users/eugene/nullalgo/simons-wt/interpretation-replay-stage2` 기준:

- A: `app/analytics/new/conversationDecision.ts`, `page.tsx`, `parsedStrategyMerge.ts`, `conversationDecision.authority.test.ts`; `app/api/strategy/parse/stream/route.ts`.
- W: `backend/intent/interpreter.py`, `schemas.py`, `classifier.py`, `strategy_builder.py`, `builder_interpreter.py`, `backend/api/intent_routes.py`; `backend/strategy_conversation/conversation/versioning.py`; `response/notice_evidence.py`, `notice_assembly.py`; `interpreter/domain_approval.py`; `primary.py`, `backend/main.py`; `components/admin/AgentsTab.tsx`의 흐름 설명.
- B: `backend/engine/nl_parser.py`의 KR 진입 라우팅·고지 receipt. 엔진/시뮬레이션 알고리즘은 수정하지 않는다.
- 회귀 작성: `backend/tests/test_strategy_revision_cas.py`, `test_semantic_builder_authority.py`, `test_notice_producer_evidence.py`, `test_turn_axes_authority.py` 및 위 프론트 회귀. stale/중복/동시 요청/재시작/잘못된 기준 상태, raw fallback 차단, 구조화 빌더 제어·분류 축, 독립 필드 고지·내부 근거 제거·규제 축 우선순위를 다룬다.
- G: 이 명세/완료 기록, 경계 등록, PROJECT_PLAN·software_architecture·SRS·nl_interpretation_contract·CLAUDE 현재 상태. 각 코드 단위는 별도 A/W/B로 처리하고 문서는 G로 분리했다. 누적 diff는 200줄을 넘으며 작은 단일 변경으로 표현하지 않는다.

## 검사·실행 상태

- 단위/통합/전체 backend/frontend 검사, replay, 문법/빌드/diff 검사, live 게이트: **전부 NOT_RUN**. 사용자 “게이트/검증 빼고” 지시를 유지했다. 회귀 코드는 작성했으며 실행/통과로 표시하지 않는다.
- 실제 모델/검색 호출, runtime ledger 생성·갱신, 운영 DB/data 갱신, 커밋·푸시·배포: **실행하지 않음**. 미래 runtime의 모델 호출 비용/지연은 미측정이다. 앞선 5단계 PASS 수치는 현재 코드를 검증한 결과가 아니다.
- KR 턴 분류는 기존 한 호출의 출력 형태 변경이다. 빌더 자유 입력은 기존 LLM 호출이 권위 있는 경로가 되므로 과거 regex 즉답과 호출/지연이 달라진다. 정본 진입 칩 결속은 호출 없이 유지하며, 시드와 답변이 함께 오는 턴은 각각 해석한다. 직전 KR 잔여 작업에서 추가한 의미 대조 최대 1회와 구분한다.
- 미커밋 구현과 문서를 전달한다. US와 검증을 제외한 이번 세 구현 항목을 후속 잔여 작업으로 다시 넘기지 않는다.
