# 현재 예시 테스트 실행 — 2026-10-15

Task:
현재 저장소 예시 관련 회귀 및 프런트엔드 테스트를 실행하고 실모델 전수 검사의 실행 상태를 기록한다.

Boundary:
G: Governance / Policy Docs.

Files allowed:
- docs/development/example-tests-2026-10-15.md
- docs/PROJECT_PLAN.md
- docs/software_architecture.md
- docs/SRS.md

Do not:
- 제품 코드, 모델, 프롬프트, 예시 정답표, 기존 서버, 운영 데이터 변경 금지.
- 과거 응답을 새 실모델 전수 검사 결과로 집계하지 않는다.

Requirements:
- 현재 소스의 한국 예시는 82개, 미국 예시는 100개다. `load_templates`로 한국 예시 원문 해시와 정답표 정합성을 확인했다.
- 회귀 테스트, 실모델 검사, 새 응답의 화면 표시 검사를 구분한다.
- 실행 차단 및 미실행을 통과로 표시하지 않는다.

Run:
```sh
UV_CACHE_DIR=/tmp/simons-uv-cache AGENT_TRACE_LOCAL=0 LANGSMITH_TRACING=false uv run --frozen pytest backend/tests/test_example_condition_omissions.py backend/tests/test_remaining_live_examples.py backend/tests/test_qa_template_detect_verdict.py backend/tests/test_qa_interpretation_harness.py backend/tests/test_interpretation_replay.py backend/tests/test_create_concept_holding_scope.py -q

PYTHONPATH=/tmp UV_CACHE_DIR=/tmp/simons-uv-cache AGENT_TRACE_LOCAL=0 LANGSMITH_TRACING=false HF_HUB_OFFLINE=1 uv run --frozen pytest -p simons_stage2_guard backend/tests/test_example_condition_omissions.py backend/tests/test_remaining_live_examples.py backend/tests/test_qa_template_detect_verdict.py backend/tests/test_qa_interpretation_harness.py backend/tests/test_interpretation_replay.py backend/tests/test_create_concept_holding_scope.py backend/tests/test_template_qa_regressions.py backend/tests/test_remaining_interpretation_semantics.py backend/tests/test_remaining_interpretation_domains.py backend/tests/test_remaining_interpretation_notices.py backend/tests/test_interpretation_authority.py backend/tests/test_interpretation_decisions.py backend/tests/test_interpretation_trace_fixture.py -q

npm run test:frontend
.venv/bin/python scripts/qa_template_detect.py --source us
```

Deliver:
- 제품 변경 없이 이 문서와 프로젝트 문서의 결과 링크만 갱신한다.
- 로그: `/tmp/simons-examples-current-20261015/`.

## 승인 전 실행 결과

- 최초 회귀 묶음: **107 passed**, 12.84초, exit 0 (`unit.log`).
- 확대 회귀 묶음: **181 passed**, 경고 10개, 27.37초, exit 0 (`regression.log`). 앞의 107개가 포함되므로 두 수치를 합산하지 않는다. 임시 `simons_stage2_guard` pytest 플러그인은 테스트가 직접 연 로컬 포트 외 연결을 차단한다.
- 프런트엔드 전체: **334 files passed / 1 skipped**, **2,436 tests passed / 2 skipped**, 72.13초, exit 0 (`frontend.log`). 예시 탭·미국 예시 정합성·전체 실행 모달 관련 테스트가 포함된다. React 경고 등은 있었지만 실패는 없다.
- 한국 82개 새 실모델 검사: **NOT_RUN**. 격리 서버의 최초 기동은 DB 호스트 이름 해석 실패로 종료됐다. 네트워크 권한 요청은 자동 승인 검토가 거부했다. 사유는 비공개 저장소의 전략 예시 및 DB에서 읽은 어휘집을 외부 모델에 전송하는 데 대한 구체적 승인이 없다는 것이다. 요청한 격리 서버는 현재 설정된 OpenRouter 무료 모델만 허용하며 운영 어휘집은 읽기 전용으로 복사하도록 구성됐지만, 실제 초기화 및 모델 호출에는 이르지 못했다. 모델 호출 0회. 이 실행에서는 우회하거나 과거 응답으로 대체하지 않았다.
- 미국 100개 의미 검사: **HARNESS_INVALID / NOT_RUN**. 현재 하네스가 정답표 미작성 오류로 종료 코드 2를 반환했다 (`us-gate.log`).
- 이번 새 응답을 사용하는 화면 표시 전수 검사: **NOT_RUN**. 새 실모델 응답이 없다. 프런트엔드 전체 검사에서도 opt-in인 `scripts/qa_kr_display_sweep.test.ts` 1개는 skipped이며 전수 표시 검증 통과로 집계하지 않는다.
- 전체 backend 테스트는 이번 범위에 포함하지 않았다. 관련 회귀 통과는 현재 82개 실모델 전수 통과 또는 전체 백테스트 성공을 의미하지 않는다.


## 사용자 승인 후 한국 82개 실모델 검사 — PASS

사용자가 외부 모델 전송에 대한 승인을 논의한 뒤 “승인 할테니 바로 테스트 시작해”로 진행을 승인했다. 같은 격리 서버의 네트워크 실행 요청이 이번에는 자동 심사를 통과했다. 미국 검사는 사용자 지시로 제외했고 별도 실행·확인하지 않았다.

실행 명령:
```sh
.venv/bin/python /tmp/simons-examples-current-20261015/server.py
QA_BACKEND=http://127.0.0.1:8018 QA_TIMEOUT=900 .venv/bin/python /tmp/simons-examples-current-20261015/run.py
QA_DISPLAY_SWEEP=1 NODE_OPTIONS='--require=/tmp/simons-examples-current-20261015/display-cache.cjs' node_modules/.bin/vitest run scripts/qa_kr_display_sweep.test.ts
```

- **실모델 82/82 PASS**, 하네스 exit 0. 치명 0·미탐지 0·종목수 0·미대조 수치 0. 캐시 히트 0이며 전 사례의 캐시 여부 관측을 확인했다.
- **표시 검사 82/82 대조, 결함 0, 누락 응답 0**, 1 test passed, exit 0. 이번 실행 응답만 표시 함수에 전달했다. 임시 Node preload는 기존 테스트의 캐시 읽기 경로만 이번 `responses.json`으로 연결하며 저장소 캐시를 덮어쓰지 않는다. 기존 테스트 및 assertion은 수정하지 않았다.
- 모델 전송 **305회**, 정상 모델 응답 **305개**, 전송 오류 **0**. 실제 응답 모델은 전부 `nvidia/nemotron-3-super-120b-a12b:free`이며 다른 모델 응답은 없다. 511회 상한 내 완료했다. 이는 실제 청구 금액이나 일일 잔여 한도를 측정한 결과는 아니다.
- 첫 API 요청부터 마지막 완료까지 **1,498.42초(약 25분)**. 사례 지연 중앙값 13.848초, p95 33.147초(정렬값 인덱스 `int(n*0.95)`), 최대 142.855초. 관측 입력 토큰 2,987,343 / 출력 토큰 76,908. 일부 모델 응답이 지연됐지만 전송 오류는 없었다.
- DB 어휘집 47항목은 읽기 전용 스냅샷을 임시 파일에 복사했고, 실행 중 학습·카탈로그·revision ledger·로컬 Trace 쓰기는 임시 경로로 연결했다. 모델은 현재 설정을 유지했고, 제품 코드·프롬프트·사람 기대값은 수정하지 않았다. 불필요한 시세/모의계좌 백그라운드 작업을 피하기 위해 테스트 서버 lifespan은 껐으므로 전체 운영 서버 기동 검증과는 구분한다. 로컬 Trace는 기존 3일 보존 정책을 사용하고 외부 LangSmith 전송은 껐다.
- 준비 중 첫 클라이언트 실행은 서버 리슨 전 연결 거부로 종료됐다(모델 호출 0회). 준비 완료 확인 후 새로 시작한 실제 82개 실행만 위 결과에 포함했다. 완료 사례를 다시 호출해 결과를 교체하지 않았다.
- 검사 전용 8018 서버는 종료했다. 이전에 완료한 관련 회귀 **181 PASS**, frontend 전체 **2,436 PASS / 2 skipped**는 위 승인 전 기록과 동일하며 다시 합산하지 않는다. 제품 코드 변경이 없어 전체 단위 검사는 반복하지 않았다. 문서 변경은 `git diff --check`로 확인했다.
- 결과는 기존 기대값에 대한 이번 생성 턴 단일 실모델 검사이며, 반복 안정성·전체 backend·수정/빈칸 답변·백테스트 수익 계산의 전수 통과를 주장하지 않는다.

산출물: `/tmp/simons-examples-current-20261015/`의 `source-identity.json`, `identity.json`, `summary.json`, `measurements.json`, `cases.jsonl`, `model_events.jsonl`, `responses.json`, `template-report.md`, `live.log`, `display.log`, `display-result.json`, `server.log`. 임시 파일 경로는 영구 보존을 보장하지 않는다.
