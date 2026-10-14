# KR 예시 게이트 — 2026-10-14

2026-10-15 후속: 사용자가 “실모델 게이트를 시작해”로 예상 호출 수를 승인했다. 아래 NOT_RUN/승인 대기는 최초 고정 재생 보고 시점의 기록이다. 현재 실행은 [실모델 게이트 기록](interpretation-stability-live-gate-2026-10-15.md)을 따른다.

Task:
현재 격리 구현의 KR 예시를 고정 재생하고 예시 게이트의 실패 및 실행 상태를 기록한다.

Boundary:
W 검사/실행 오류 수정 이후 별도 G 문서 반영. 이 문서는 G 산출물이다.

Files allowed:
- W: 기존 `scripts/qa_template_detect.py`, `backend/tests/interpretation*`, 관련 하네스 회귀 실행; `backend/main.py`의 실행 오류 수정.
- G: 이 문서, `docs/PROJECT_PLAN.md`, `docs/software_architecture.md`, `docs/SRS.md`.

Do not:
- 사람 기대값 완화, 원문 의미 regex 추가, 모델 설정 변경, 운영 데이터 갱신, 원래 backend 수정, 커밋/배포.
- US 게이트 실행 또는 KR/US·live/replay 결과 합산.
- 최초 요청문 §10의 예상 호출 수 사전 승인 없이 live 실행.

Requirements:
- 현재 코드의 구조화 결과·API 후처리·표시와 고정 사람 기대값을 대조한다.
- PASS / FAIL / HARNESS_INVALID / INFRA_BLOCKED / NOT_RUN을 구분한다.
- 고정 재생의 PASS를 실제 모델 해석 품질 통과로 표시하지 않는다.

Run:
- 작업트리 루트: `UV_CACHE_DIR=/tmp/simons-uv-cache HF_HUB_OFFLINE=1 AGENT_TRACE_LOCAL=0 LANGSMITH_TRACING=false uv run --frozen python scripts/qa_template_detect.py --replay /tmp/simons-example-gate-20261014-kr-fixtures.json --out /tmp/simons-example-gate-20261014-kr-replay.json`
- 작업트리 backend: `PYTHONPATH=/tmp UV_CACHE_DIR=/tmp/simons-uv-cache uv run --frozen pytest -p simons_stage2_guard tests/test_interpretation_replay.py tests/test_qa_template_detect_verdict.py tests/test_qa_interpretation_harness.py -k 'not positions-us' -q`
- 작업트리 backend: `PYTHONPATH=/tmp UV_CACHE_DIR=/tmp/simons-uv-cache uv run --frozen pytest -p simons_stage2_guard tests/ --ignore=tests/test_backtest_engine.py --ignore=tests/test_engine_ai.py --ignore=tests/test_ai_sell.py --ignore=tests/test_api_isolation.py -k 'not us' -q`

Deliver:
- 고정 재생 결과, 실행 오류 원인과 수정, live 사전 승인 상태 및 검사 제한.

## 실행 결과

- 코드 위치: `/Users/eugene/nullalgo/simons-wt/interpretation-replay-stage2` 미커밋 작업트리.
- 최초 재생은 기존 10건 묶음의 US 1건까지 실행됐다. 이후 지역 KR의 9건만 원문·기대값·판정 tape를 그대로 임시 파일에 선택해 실행했으며 영구 corpus는 바꾸지 않았다. 초기 혼합 결과를 KR 게이트 통과 지표로 쓰지 않는다.
- 최초 10건은 API 후처리 import에서 `NameError: name 'Field' is not defined`로 FAIL. 새 revision 요청 스키마가 쓰는 `pydantic.Field`의 import 누락이다. `backend/main.py`의 기존 import에 Field만 추가했다. 최초 하네스 회귀는 65 PASS / 11 FAIL이었다.
- 수정 후 KR 고정 재생: **9 PASS**, 생성 5 / 수정 3 / 빈칸 답변 1. 최종 API 및 프런트 표시도 모두 PASS. 북극항로 안내 모순, 부분 해소/미해결 테마, 정성 수익률, 보유기간, 독립 수량 변경, 조건 교체 보존을 포함한다. 기존 기대값은 완화하지 않았다.
- 수정 후 하네스 회귀: **75 PASS / 1 deselected**, 12.42초. US 재생 케이스 하나 제외. 외부 연결 차단 플러그인을 사용했다.
- 실행 pipeline 콘텐츠 hash: `c37d152a9e89ae6eacd0bda14ae71ae1e1772e7db3d506b9739bafd2c936c8b1`. 모델 synthetic-fixture, schema 1.0, engine 16.40.0, 기반 commit 4e048137. 이전 단계의 PASS 숫자와 별개다.
- backend 회귀: **FAIL — 4,552 passed / 470 failed / 11 errors / 3 skipped / 839 deselected**, 210.39초。검사 종료 시점은 2026-10-15 KST다. 이름에 `us`가 포함된 테스트를 제외하므로 KR만 완전히 분리한 검사 또는 저장소 전체 검사라고 표현하지 않는다. 이름 필터를 통과한 일부 영문 관련 단위 테스트도 포함된다. US live 게이트는 실행하지 않았다.
- 확인한 실패 유형: (1) 기존 rule-based 해석·deterministic 토글을 기대하는 테스트와 KR 의미 권위 이관의 충돌, (2) `_step_semantic`에서 주입 interpreter의 RuntimeError가 처리되지 않는 실제 실행 오류, (3) `engine/nl_parser.py::_detect_qualitative_metrics`의 KR 분기에서 미정의 `parsed`를 반환하는 실제 NameError, (4) 새 notice/revision 테스트가 필수 description 없는 ParsedStrategy를 만드는 fixture 오류, (5) 캐시/스트림 및 다른 계약 기대 불일치. 전부 기존 테스트 문제라고 처리하지 않는다. 각각의 470건을 모두 원인 분류/수리한 상태는 아니다.
- 사용자 이번 요청은 예시 게이트 실행이다. import 누락만 좁게 수리했고 나머지 실제 오류·테스트 이관은 미수리 상태로 보고한다. 앞선 구현 작성 완료 답변이 현재 정상 동작 또는 검증 완료를 의미하지 않는다.
- `git diff --check -- backend/main.py` 및 이번 G 문서 대상 diff 공백 확인 PASS. 프런트 코드 수정 없음.
- **live KR 81예시: NOT_RUN, 사전 승인 대기.** 과거 약 430회 호출에 신규 의미 대조가 최대 81회 추가될 수 있다는 예산을 알리고 승인을 요청했다. 실제 호출 수/응답 모델/지연은 미측정이다. 외부 유료 호출·커밋·운영 적용 없음.
- 프런트 전체 검사 및 신규 남은 구현 전체에 대한 검증 완료로 일반화하지 않는다.

## 결과 파일

- `/tmp/simons-example-gate-20261014-replay.json`: 최초 혼합 재생 실패.
- `/tmp/simons-example-gate-20261014-kr-fixtures.json`: 기존 corpus에서 KR만 선택한 임시 입력.
- `/tmp/simons-example-gate-20261014-kr-replay.json` 및 `.log`: 수정 후 KR 고정 재생.
- `/tmp/simons-example-gate-20261014-harness.log`: 수정 후 하네스 회귀.
- `/tmp/simons-example-gate-20261014-backend.log`: backend 회귀.
