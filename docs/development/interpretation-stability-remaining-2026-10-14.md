# 전략 해석 안정화 — KR 잔여 구현

Task:
US와 게이트·검증 실행을 제외하고 KR 생성·수정·fill의 잔여 고지 정합성, 도메인 그룹 보류, primary 의미 어휘 판정을 마무리한다.

Boundary:
W. 경계·명세 등록과 완료 문서는 각각 별도 G 작업으로 처리한다.

Files allowed:
- backend/strategy_conversation/primary.py
- backend/strategy_conversation/interpreter/**
- backend/strategy_conversation/conversation/patch_approval.py
- backend/strategy_conversation/response/notice_assembly.py
- backend/main.py
- backend/tests/**
- components/admin/AgentsTab.tsx (흐름 동기화만)

Do not:
- US 전용 분기 변경, 엔진·컴파일러·provider·DB·데이터·프론트 턴 중재 변경
- 원문 의미 regex/어휘 추가, 공개 State·Agent·DSL 추가
- 테스트·재생·게이트 실행, 외부 모델/검색 호출, 커밋·푸시·배포
- 원래 checkout backend 변경, 타 세션 변경 덮어쓰기

Requirements:
- 실제 validator를 사용해 문제를 유발한 패치 그룹을 보류하고 기존 조건과 독립 변경 보존
- 미해결 KR 테마 질문에서도 독립 변경 유지하고 질문 큐 결속 유지
- 최종 반영 receipt 기준으로 KR 생성·수정·fill·ETF 고지 조립, 진단 원본 보존
- primary의 매수 역할·EMA 선택·보유기간 의미 어휘 판정을 구조화 LLM 출력으로 이관
- 회귀 테스트 코드는 추가하되 실행하지 않으며 결과를 NOT_RUN으로 기록
- 작은 단위(각 1~5파일)로 구현, 마지막 별도 G 문서 갱신

Run:
- 사용자 지시 “게이트/검증 빼고”로 모든 검증 실행 생략
- 추후 명령: cd <worktree>/backend && uv run --frozen pytest tests/test_remaining_interpretation_domains.py tests/test_remaining_interpretation_notices.py tests/test_remaining_interpretation_semantics.py
- 추후 전체 backend/frontend 명령은 5단계 보고의 Run과 동일

Deliver:
- 기존 /Users/eugene/nullalgo/simons-wt/interpretation-replay-stage2의 미커밋 구현
- 변경 동작·추가 runtime 호출·NOT_RUN·범위 밖 부채 보고

## 승인

사용자: “us는 신경쓰지마. 게이트/검증 빼고 남은 작업을 마무리 해”. 잔여 KR 범위 확장과 검증 실행 생략에 대한 직접 지시다. 구현 코드와 회귀 작성은 W, 문서는 G로 분리한다.


## 구현 결과 — 검증 실행 없음

KR 잔여 구현을 기존 격리 작업트리에 반영했다. 구현 작성 상태와 검증 통과 상태를 구분한다. 원래 checkout의 backend에는 복사하지 않았다.

1. 문제 서류를 한 장씩 되돌려 어느 서류가 오류를 만드는지 확인하는 절차처럼, `interpreter/domain_approval.py`는 기존 실제 validator의 결과를 그룹별 되돌림 후보와 비교한다. 의미 문구를 regex로 분류하지 않고 errors의 개수와 구조화 question.field를 대조한다. 생성·수정·fill의 문제 그룹을 보류하며 이전 조건과 독립 패치를 유지한다. KR sector catalog 진단은 지식 조회 체인이 소유하므로 이 오류 격리에서 제외한다. 어느 그룹에도 귀속할 수 없는 오류는 기존 전역 안전 거절을 유지한다. validator를 여러 번 호출하지만 모델/검색 호출은 없다.
2. 테마 선택을 기다리는 동안 다른 수정 서류를 버리지 않듯, KR 테마 범위 질문은 universe 그룹만 되돌린 뒤 선택한 나머지 상태를 다시 검증·컴파일한다. 같은 턴의 독립 종목 수 등을 유지하고 질문·칩·기존 큐를 함께 전달한다. 시장 소속이 0곳인 경우도 universe 그룹을 보류하며 실제 제안 목록과 최종 상태 차분을 맞춘다.
3. 안내문을 최종 물건 목록과 맞추듯, `response/notice_assembly.py`는 KR 생성·수정·fill·ETF의 실제 적용 receipt와 마지막 ParsedStrategy를 대조한다. 부분 컴파일에서 빠진 조건의 원래 인용만으로 반영됐다고 취급하지 않고 실제 컴파일 결과의 포함을 확인한다. 범위 선택 대기와 미지원 신고를 구분하고, 복합 신고의 나머지 표현이 지원됐다고 추정하지 않는다. API `_finalize_parse_result`에서 후처리 뒤 다시 조립하고 내부 `_notice_context`를 제거한다. 진단 원본과 적용 근거는 기존 로컬 Trace에 남으며 공개 스키마는 추가하지 않는다. 근거가 없는 기존 비차단 notices는 보존하고 중복만 제거한다.
4. 인용 속 낱말을 자동 규칙이 읽어 의미를 바꾸던 KR 매수 역할·EMA 선택·명시 기간·미지원 보유기간 보정을 비활성화했다. 자유 미지원 인용을 낱말로 손절/익절에 귀속하던 고지 필터도 제거하고, 인용 수량과 percent 단위를 동반한 LLM kind로 해당 설정을 대조한다. `interpreter/semantic_reconciliation.py`의 한 배치 LLM 대조가 인용·항목 ID·정형 필드·수량/단위를 반환한다. 결정론은 해당 출력의 표기·인용·enum·숫자만 검증한다. 실패·불명확하면 원래 메인 LLM 출력을 유지하며 어휘 보정으로 돌아가지 않는다. 기존 필수 보류/명시 거부는 되살리지 않는다. 정본 개념 기본값과 수량 단위 환산은 기존 registry 계약을 사용한다. KR에서 설정으로 다시 켤 수 있던 원문 `_apply_prompt_overrides`도 호출하지 않는다. 제외된 US 호환 분기는 보존했다.

## 변경 파일과 작업 단위

경로는 `/Users/eugene/nullalgo/simons-wt/interpretation-replay-stage2` 기준이다.

- 도메인 단위: `interpreter/domain_approval.py`, `conversation/patch_approval.py`, `primary.py`. 반복 승인 과정에서 새 사본 조건의 정체성을 이월한다.
- 고지 단위: `response/notice_assembly.py`, `primary.py`, `backend/main.py`. 내부 근거 handoff는 최종 응답에서 소비·제거한다.
- 의미 이관 단위: `interpreter/semantic_reconciliation.py`, `primary.py`. 새 Agent·State·DSL 없이 보조 대조를 추가한다.
- 회귀 작성 단위: `backend/tests/test_remaining_interpretation_domains.py`, `test_remaining_interpretation_notices.py`, `test_remaining_interpretation_semantics.py`. 도메인 오류 두 그룹과 독립 변경, 잘못된 교체, 생성 부분 보류, primary 수정·테마 질문·값 누락, ETF 최종 상태 변경·dict 응답·중복·부분 컴파일, 구조화 EMA/역할/보유기간·실패·잘못된 수량 근거를 다룬다.
- 흐름 단위: `components/admin/AgentsTab.tsx`의 KR 보류·테마 질문·최종 고지·의미 대조 설명.
- 마지막 별도 G: 이 보고와 PROJECT_PLAN·software_architecture·SRS·nl_interpretation_contract의 현재 상태. 경계 등록은 선행 G 작업이다. 누적 변경은 200줄을 넘으며 하나의 작은 diff라고 표현하지 않는다.

## 행동 계약 변경과 호출

- 도메인 오류·새 패치 값 누락·테마 범위 질문 때문에 독립 변경까지 무효화하던 KR 경로가 그룹 보류로 바뀐다. 분리 근거가 없는 파괴적 목록 재작성 등은 보수적으로 함께 보류한다.
- 역할/EMA/기간을 인용 낱말로 교정하던 경로는 구조화 LLM 대조로 바뀐다. 확인 가능한 신규 MA/breakout 인용 또는 미지원 신고 대상이 있는 KR 생성/수정 요청에 **런타임 모델 호출 최대 1회 추가**다. 기존 필수 판정으로 이미 보류된 대상에는 이 추가 대조를 하지 않으며 기존 구체 breakout 복구 대상은 구분한다. 대상이 없으면 추가 호출은 0회다. 운영 지연/비용·의미 정확도는 미측정이다.
- 작업 중 외부 모델/검색 호출은 **0회**다. 새 보조 출력 형태를 구현했으며 초기 메인 해석 프롬프트·모델 ID는 변경하지 않았다. §11의 구조 정비 뒤 전면 프롬프트 조정은 수행하지 않았다.

## 검사 상태와 한계

사용자가 “게이트/검증 빼고”라고 직접 지시했으므로 단위·통합·전체 backend/frontend 테스트, 결정론 replay, 문법/빌드 검사, diff 검사, live 게이트를 **모두 NOT_RUN**으로 남긴다. 회귀 코드는 작성했으며 실행/통과로 보고하지 않는다. 앞선 5단계의 594 PASS·전체 backend/프론트·10건 replay 수치는 **이번 변경 전 상태의 결과**이며 현재 코드의 검증 결과로 재사용하지 않는다.

US의 구현·게이트·기존 parquet 컬럼 불일치는 이번 완료 대상에서 제외했다. 다른 boundary의 프론트 턴 중재·레거시 엔진/빌더 원문 패턴 매칭은 여전히 **미이관 위반**이다. 해당 아키텍처 부채 전체를 없앴다고 표현하지 않는다. 실제 요청 간 DB 버전 충돌, 모든 지식 체인의 필수 대조 승격, US 고지 통합도 이 KR 잔여 구현의 대상이 아니다. 최종 assembler는 반영 근거가 있는 고지를 다시 투영하며 근거 없는 모든 자유 문구의 의미를 추측해 삭제하지 않는다.

커밋·푸시·배포·운영 DB/어휘집/parquet 변경·기존 backend 복사 없이 미커밋 구현을 전달한다. 사용자 지시에서 제외한 검증을 실행 완료로 바꾸지 않는다.
