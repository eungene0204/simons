# 미국 주식 부분 지원 안내 (2026-09-28)

Task:
미국 주식 지원 질문에 사용자가 지정한 안내문을 반환하고 내부 작성 지시 노출을 막는다.

Boundary:
AI / XAI Layer (Boundary D). 사용자가 이번 작업에 한해 아래 API 파일과 작업 기록 문서를 허용했다.

Files allowed:
- `backend/api/intent_routes.py`
- `backend/tests/test_general_answer_glossary_lane.py`
- `docs/development/us-market-support-guidance.md`

Do not:
- 데이터 수집, 백테스트 엔진, 시장별 전략 처리 로직을 변경하지 않는다.
- API 응답 형식이나 LLM 모델을 변경하지 않는다.

Requirements:
- "네, 미국 주식도 지원합니다"로 시작하고 일부 상장폐지 종목의 데이터 부족과 추후 데이터 추가 계획을 안내한다.
- AAPL·MSFT·TSLA 예시, 과거 데이터 백테스트와 채팅 조건 입력 안내를 포함한다.
- 사용자 답변에 내부 작성 지시나 프롬프트 태그를 노출하지 않는다.
- 이전 대화의 잘못된 안내보다 현재 지원 범위를 우선한다.
- 확인되지 않은 개별 종목 지원 여부와 데이터 보완 일정을 단정하지 않는다.

Run:
- `UV_CACHE_DIR=/private/tmp/simons-uv-cache uv run --no-sync pytest backend/tests/test_general_answer_glossary_lane.py -q`
- `UV_CACHE_DIR=/private/tmp/simons-uv-cache uv run --no-sync pytest backend/tests`
- `KRX_ID= KRX_PW= UV_CACHE_DIR=/private/tmp/simons-uv-cache uv run --no-sync pytest backend/tests`
- `KRX_ID= KRX_PW= UV_CACHE_DIR=/private/tmp/simons-uv-cache uv run --no-sync pytest backend/tests/test_general_answer_glossary_lane.py backend/tests/test_llm_adapter_split.py backend/tests/test_platform_defaults.py backend/tests/test_observability_intent_lane.py -q`
- 후속 수정의 전체 테스트: `KRX_ID= KRX_PW= UV_CACHE_DIR=/private/tmp/simons-uv-cache uv run --no-sync pytest backend/tests --maxfail=1`
- 성공 기준: 모두 통과. 실패 시 원인과 검증 한계를 기록한다.

Deliver:
- 작은 diff, 변경 파일 요약, 테스트 결과.

## 변경 내용

첫 수정에서 `_GENERAL_SYSTEM_PROMPT`에 추가한 작성 지시가 실제 사용자 답변에 그대로 노출됐다.
후속 수정은 사용자가 지정한 안내문을 `_US_MARKET_SUPPORT_ANSWER`로 분리했다.
"미국 주식도 지원해?" 등 정해진 독립 질문은 공백·끝 문장부호만 정규화해 정확히 대조하고 한국어 UI에서 안내문을 직접 반환한다.
LLM 미가용 여부와 이전 대화의 잘못된 안내에 영향을 받지 않는다. 호출부가 결과 사실을 전달한 질문은 기존 결과 설명 경로를 유지한다.
목록 밖 표현과 영어 UI는 기존 LLM 경로를 사용하되 `user_facing_answer` 태그 안에 안내문을 분리해 넣는다.
`/query/general`과 전략 대화의 일반 질문 백스톱은 같은 함수를 공유한다.

안내 예시:

> 네, 미국 주식도 지원합니다. 다만 일부 상장폐지 종목은 데이터가 충분하지 않아 지원하지 않습니다. 추후 데이터를 추가해 지원할 예정입니다. 미국 주요 거래소에 상장된 종목(예: AAPL, MSFT, TSLA 등)에 대한 전략을 작성하고 과거 데이터로 백테스트를 수행할 수 있습니다. 전략 조건을 채팅에 입력해 주시면 해당 조건으로 백테스트를 진행해 드립니다.

## 문서 검토

`docs/PROJECT_PLAN.md`, `docs/software_architecture.md`, `docs/SRS.md`의 시장 지원 및 일반 질문 경로를 검토했다.
기존 [상장폐지 데이터 점검](delisted-data-audit.md)은 미국 상장폐지 가격 파일 부재와 티커 재사용에 따른 식별 한계를 기록한다.
이번 작업의 승인된 문서 범위에 맞춰 안내 요구사항과 구현 내역을 이 문서에 기록한다.

## 검증 결과

후속 수정:
- 관련 테스트 52개 통과. 직접 질문 3종은 LLM 호출 없이 지정 문구를 반환하며, 이전 대화의 작성 지시가 답변으로 전달되지 않음을 검증한다.
- 유사 질문 4종은 사용자 안내문과 작성 지시가 구분된 프롬프트를 전달하는지 확인한다.
- 전체 테스트(`--maxfail=1`): 33개 통과 후 `test_advisor_memory_bootstrap.py::test_load_advisor_memory_bootstraps_latest_backtest_results`에서 로컬 PostgreSQL 접근 제한으로 오류 1개가 발생해 중단됐다. 전체 통과가 아니다. 로그는 `/private/tmp/simons-us-support-followup-tests.log`.
- 직접 질문의 고정 응답은 단위 테스트로 검증했다. 목록 밖 표현의 실제 LLM 출력과 운영 배포는 검증하지 않았다.

첫 수정의 검증 이력:
- 수정 전: 기존 6개 테스트 통과, 추가된 지원 안내 회귀 4개 실패. 실제 답변 생성 호출에 데이터 제한 지침이 없음을 확인했다.
- 수정 후: 관련 테스트 10개 통과. 한국어·영어 질문, 상장폐지 종목 질문, 잘못된 기존 답변을 포함한 후속 질문에 지침이 전달됨을 확인했다.
- 일반 답변, LLM 어댑터, 플랫폼 기본값, 일반 답변 관찰 경로의 관련 테스트 49개 통과.
- 백엔드 전체 테스트: 첫 실행은 `data.krx.co.kr` DNS/연결 오류로 수집 단계에서 2개 오류 발생.
- KRX 로그인 설정을 비운 재실행은 5,402개를 수집했으나 `test_modify_rag.py`에서 진행이 멈춰 중단했다. 중단 시 집계는 2,062개 통과, 5개 건너뜀, 1개 실패, 24개 오류다. 전체 통과가 아니다.
- 24개 오류는 로컬 테스트 PostgreSQL(`localhost:5432`) 연결이 샌드박스에서 허용되지 않아 발생했다. 실패 1개는 `test_backfill_us_stocks.py::test_columns_match_korean_schema`로, 국내 표본 가격 파일에 미국 컬럼 목록보다 5개 많은 컬럼이 있었다(`fcf_margin` 등). 이번 안내 변경 범위 밖이다.
- 전체 실행 로그: `/private/tmp/simons-us-support-backend-tests.log`.
- 기존 가상환경을 사용했다. 기본 uv 캐시 경로는 샌드박스에서 접근할 수 없어 임시 캐시 경로와 `--no-sync`를 사용했다.
- 회귀 테스트는 LLM 호출을 대체하여 프롬프트 전달과 응답 계약을 검증한다. 실제 모델의 문구 준수와 운영 배포는 검증하지 않았다.
