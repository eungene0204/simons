# KR 81예시 실모델 게이트 — 2026-10-15

Task:
사용자가 승인한 KR 81개 예시를 현재 격리 구현과 실제 무료 모델로 한 번씩 실행하고 모델·호출·실패·표시 결과를 분리해 기록한다.

Boundary:
W 실행/하네스 수리 이후 별도 G 결과 문서 작업. 이 문서 및 아래 프로젝트 문서는 G에서만 변경한다.

Files allowed:
- W: 기존 `scripts/qa_template_detect.py`와 `backend/tests/test_qa_template_detect_verdict.py`의 live 요약 함수 충돌 수리 및 회귀.
- 실행: 기존 예시/기대값과 표시 스윕을 사용하며 임시 launcher, 모델 관측, 결과, 학습 어휘집과 revision ledger는 `/tmp/simons-live-gate-20261015/`.
- G: 이 문서, 직전 고정 게이트 기록, PROJECT_PLAN, software_architecture, SRS.

Do not:
- 제품 의미 해석 코드·모델 ID·프롬프트·사람 기대값 변경, US 게이트, 유료 모델 호출, 운영 어휘집/DB/데이터 쓰기, 원래 backend 수정, 기존 서버 재시작, 커밋/배포.
- 과거 캐시·재생 응답을 live PASS로 합산하거나 서로 다른 실제 응답 모델 결과를 합산.

Requirements:
- 사용자는 약 430~511회 호출 추정 안내 후 “실모델 게이트를 시작해”로 실행을 승인했다. 전송 재시도를 포함한 상한 511회로 제한한다.
- 처음 실행하는 예시마다 현재 서버를 호출한다. 실패를 다시 호출해 통과 결과로 교체하지 않는다.
- 기존 모델 폴백 정책을 유지하고 각 요청의 실제 응답 모델을 관측한다. 완료/캐시/전송 오류/미실행을 구분한다.
- 구조화 결과와 기존 사람이 작성한 기대값을 대조한다. 표시 스윕은 이번 실행 응답만 사용한다.

Run:
- 작업트리 `/Users/eugene/nullalgo/simons-wt/interpretation-replay-stage2`에서 `UV_CACHE_DIR=/tmp/simons-uv-cache uv run --frozen python /tmp/simons-live-gate-20261015/server.py`.
- 같은 작업트리에서 `QA_BACKEND=http://127.0.0.1:8017 QA_TIMEOUT=900 UV_CACHE_DIR=/tmp/simons-uv-cache uv run --frozen python /tmp/simons-live-gate-20261015/run.py`.
- backend에서 `PYTHONPATH=/tmp UV_CACHE_DIR=/tmp/simons-uv-cache uv run --frozen pytest -p simons_stage2_guard tests/test_qa_template_detect_verdict.py tests/test_qa_interpretation_harness.py tests/test_interpretation_replay.py -k 'not positions-us' -q`.
- backend에서 `PYTHONPATH=/tmp UV_CACHE_DIR=/tmp/simons-uv-cache uv run --frozen pytest -p simons_stage2_guard tests/ --ignore=tests/test_backtest_engine.py --ignore=tests/test_engine_ai.py --ignore=tests/test_ai_sell.py --ignore=tests/test_api_isolation.py -k 'not us' -q`.
- 이번 응답만 격리 입력으로 연결한 뒤 `QA_DISPLAY_SWEEP=1 node_modules/.bin/vitest run scripts/qa_kr_display_sweep.test.ts`.

Deliver:
- 각 사례의 PASS / FAIL / HARNESS_INVALID / INFRA_BLOCKED / NOT_RUN, 실제 응답 모델별 결과, 호출/지연, 하네스 수리 및 회귀, 미수리 제품 실패와 한계.

## 실행 조건과 격리

- 현재 configured provider는 OpenRouter, 모델은 `nvidia/nemotron-3-super-120b-a12b:free`. API 키의 존재만 확인했으며 키를 출력하거나 저장하지 않았다. 현재 무료 슬러그를 그대로 사용하고 유료 모델 전송을 차단한다.
- 8017 포트에 현재 작업트리 전용 서버를 기동했다. 다른 8000/8100 서버는 건드리지 않았다. 새 프로세스로 API 캐시를 비운 상태에서 시작했다.
- 불필요한 모의계좌/시세 background 작업을 시작하지 않도록 lifespan을 껐다. parse API 코어·검증·후처리·CAS는 그대로 실행한다. 이는 전체 운영 서버 기동 검증과 구분한다.
- 운영 DB 어휘집 47항목을 읽기 전용 snapshot으로 가져온 뒤 임시 파일에 복사했다. 최초 hash `969061199d67babfe9c39ad31e7b9ab268f8046f4487658ac87f3e7c85128a0c`. 이후 검색 학습과 네이버 카탈로그 편입은 임시 저장소만 변경한다. 같은 실행에서 축적되는 임시 학습은 뒤 사례에 보일 수 있다.
- revision ledger와 로컬 Trace도 임시 경로로 연결했다. 외부 LangSmith 전송은 껐다. 완전한 요청/판정 원본은 기존 local Trace의 3일 보존 정책으로 기록하며 결과 요약에는 모델/필드 관측만 사용한다.
- 임시 관측 wrapper는 전송 payload의 model, 실제 응답 model/provider, 종료 이유/토큰, 오류 코드와 지연만 기록한다. 전략 의미를 새로 판단하거나 HTTP 응답을 바꾸지 않는다.

## 발견한 하네스 오류와 수리

첫 예시는 실제 모델 5회 호출 후 응답을 저장했지만 CLI가 `UnboundLocalError: summarize`로 중단됐다. replay 분기의 함수 내 `summarize` import가 live 분기의 기존 전역 요약 함수까지 가린 것이다. replay용 import를 `summarize_replay`로 명시하여 분리했다. 이 오류는 고정 replay만 실행했을 때는 드러나지 않았다.

- 실제 live CLI 경로를 단일 고정 응답으로 실행하는 신규 회귀는 변경 전 **1 FAIL**, 변경 후 관련 묶음 **76 PASS / 1 deselected**, 11.57초다. 외부 호출 차단 상태다.
- 이미 저장한 첫 사례 응답과 원래 측정을 같은 실행의 보고서 생성에 이어 사용했다. 첫 사례를 재호출하거나 과거 실행 캐시를 가져오지 않았다. 이후 80개는 각각 처음 서버를 호출한다.
- 수정 파일은 하네스와 회귀 두 개이며 제품의 의미 해석/정책 코드는 바꾸지 않았다. 작업트리 두 파일의 `git diff --check` PASS.

## 최종 결과 — FAIL

- **81/81 실행 완료, 71 PASS / 8 FAIL / 2 INFRA_BLOCKED**, HARNESS_INVALID·NOT_RUN 0. 캐시 히트 0. 기존 하네스는 치명 8 / 미탐지 경고 2 / 종목수 문제 0 / 미대조 수치 0으로 exit 1이다. 두 미탐지 경고를 별도 치명으로 승격하거나 사람 기대값을 바꾸지 않았다.
- 무료 모델 전송 **312회**, 실제 완료 모델 응답 **310개**. 모든 응답은 `nvidia/nemotron-3-super-120b-a12b:free`이고 9B 폴백·다른 모델 응답·유료 모델 전송 0. 511회 상한 아래에서 완료했다. 실제 운영 일일 잔여 한도/과금 총액을 측정한 것은 아니다.
- 두 INFRA 사례는 #40 대형주 PBR·ROE 월간 조건(HTTP 502 1회), #66 멀티팩터 주간 로테이션(URLError 1회)이다. 기존 전송 재시도로 최종 API 응답은 완료되고 구조화 채점에는 치명이 없었지만, 전송 오류가 있었으므로 안정적인 PASS 집계에서 분리했다. 사례 전체를 다시 실행해 결과를 교체하지 않았다.
- 요청 지연 중앙값 **8.966초**, p95 **16.481초**, 최대 **31.195초**. 최초 요청부터 마지막 완료까지 887.73초이며 중간 하네스 수리 시간도 포함한다. 각 요청 지연에는 API/관측 처리 시간이 포함된다. 관측 토큰 합계 입력 2,899,783 / 출력 76,006. 단일 실행이므로 변동성 안정성 보장이나 이전 코드보다 개선됐다는 증거로 쓰지 않는다.
- **표시 게이트 FAIL: 81/81 대조, 캐시 없음 0, 결함 2개(한 예시의 한 문구).** “이중 이동평균 추세 유지”의 안내에 `'technical.ema'의 단기 기간(60)이 장기 기간(20) 이상입니다…`가 나와 내부 식별자 노출과 영문 잔존으로 각각 검출됐다. 기존 표시 캐시를 잠시 이번 응답으로 연결한 뒤 원본 바이트/mtime을 복원했고 원본 일치도 확인했다.
- backend 필수 검사: **4,553 PASS / 470 FAIL / 11 ERROR / 3 skipped / 839 deselected**, 199.98초, exit 1. `not us`는 이름 기반 제외로 KR만 완전히 격리한 검사가 아니다. 기존 실행 오류·fixture·계약 기대 충돌을 이번 게이트 작업에서 일괄 수리하지 않았다. 프런트 전체 검사는 NOT_RUN이며 프런트 코드 수정은 없다.
- 전용 8017 서버 종료 완료. 기존 서비스 서버·운영 DB/학습 어휘집·원래 backend 소스는 변경하지 않았다. 제품 의미 해석 코드는 이번 실행 중 고정했다. US·modify/fill 실모델 게이트와 전체 안정화 검증 완료를 주장하지 않는다.

## 제품 실패 8개와 최초 손실 계층

모든 치명은 사람이 지정한 매도 조건이 최종 exit_signals에서 사라진 실패다. HTTP 200이나 다른 질문이 있다는 이유로 통과시키지 않았다. 원본 입력과 기대값은 기존 예시·정답표 그대로다.

| 예시 번호 | 예시 제목 | 관찰된 손실 계층 / Trace ID |
|---|---|---|
| 1 | 이평선 골든크로스 따라가기 | 초기 concept.dead_cross 추출 후 required_holding에서 보류 / e5b83b9624d8 |
| 6 | 박스권 상단 돌파 따라가기 | 초기 technical.breakout 청산 후보의 하향 연산자 도메인 오류, 그룹 보류 / a67c255cdfc2 |
| 47 | 단기 골든크로스 추종 | 초기 concept.dead_cross 추출 후 required_holding에서 보류 / e9d7bbbe6afa |
| 49 | MACD + 추세 필터 매매 | 초기 concept.macd_dead_cross 추출 후 required_holding에서 보류 / 2f163e79de40 |
| 52 | RSI·MACD 이중 확인 진입 | 초기 concept.macd_dead_cross 추출 후 required_holding에서 보류 / 5c0e5c7400a9 |
| 61 | ROE·골든크로스 조건 | 초기 concept.dead_cross 추출 후 required_holding에서 보류 / 525f6ead8a40 |
| 74 | 반도체 업종 골든크로스 | 초기 concept.dead_cross 추출 후 required_holding에서 보류 / f0ae95b22432 |
| 80 | 조선 업종 EMA 정배열 + 거래대금 | 초기 technical.ema 청산 후보의 quote 판정 미해결 및 required_quote 보류 / ba0fd6074d2c |

1. 데드크로스 6건은 메인 해석기가 매도 개념을 처음에는 추출했다. 첫 사례의 quote 판정도 ACCEPT였다. 이후 보유기간 오배치 대조가 `kind=none`을 반환했는데 required_holding이 REQUIRED_RESULT_MISSING으로 다루어 exit 그룹을 UNRESOLVED로 보류했다. 마지막에 무관한 최대·최소 보유기간 질문이 나온다. 처음부터 모델이 매도 조건을 누락했다고 보고하지 않는다.
2. #6은 초기 청산 후보가 이미 technical.breakout이며 crosses_below 연산자의 지원 계약과 맞지 않았다. 도메인 그룹 보류는 Trace에 남았지만 예시가 요구한 청산 신호는 반영되지 않았다. 원문 예외나 정답 완화로 덮지 않았다.
3. #80은 초기 청산 후보가 있었지만 quote 판정이 UNRESOLVED여서 required_quote에서 보류했다. 원본 대조 결과를 보존하며 임의로 해당 변경을 ACCEPT로 바꾸지 않았다.

이 실행은 실패를 식별한 게이트이며 위 제품 실패 및 표시 결함의 수리는 미완료다. 새 구현 작성 완료와 정상 동작 확인을 구분한다.

## 산출물

`/tmp/simons-live-gate-20261015/`의 `identity.json`, `model_events.jsonl`, `cases.jsonl`, `responses.json`, `summary.json`, `measurements.json`, `failures.json`, `template-report.md`, `display-result.json`, `display.log`, `server.log`, `gate-resumed.log`, `harness-tests.log`, `backend-tests.log` 및 local `traces/`. 원문 Trace의 장기 회귀 fixture 승격은 이번 범위에 없다. Trace 원본의 기존 3일 보관 범위를 늘리지 않는다.
