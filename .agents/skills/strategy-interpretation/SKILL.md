---
name: strategy-interpretation
description: Simons 전략 해석 실패, 조건 누락, 잘못된 신규·수정 해석을 재현하고 원인 계층을 찾아 회귀 테스트로 해결하는 개발 skill. 자연어 전략 지원 확장에도 사용한다. 투자 전략 추천이나 백테스트 성과 해설에는 사용하지 않는다.
---

# 전략 해석 실패 대응

사용자의 뜻을 보존하면서 반복되는 해석 실패를 같은 절차로 해결한다. 이 skill은 Codex 개발 작업 지침이며 서비스가 실행 중 읽는 프롬프트나 자동 학습 기능이 아니다.
모든 저장소 경로는 Simons 루트 기준이다. 아래 조사 경로는 읽기용 지도이며 수정 권한 목록이 아니다.

## 작업 범위 확정

1. `AGENTS.md`, `docs/development/codex-rules.md`, `docs/architecture/boundaries.md`, `docs/nl_interpretation_contract.md`를 읽는다. 기존 변경을 확인하고 보존한다.
2. 요청이 실행 명세가 아니면 `.codex/skills/spec-writer/SKILL.md`를 사용해 `Task / Boundary / Files allowed / Do not / Requirements / Run / Deliver`로 구체화한다. 그 skill의 축약 boundary 목록보다 현재 `docs/architecture/boundaries.md`를 우선한다.
3. 최초 의미 손실 지점을 조사한 뒤 정확히 하나의 boundary와 수정 파일을 선택한다. 여러 계층에 문제가 있으면 하나의 독립 검증 가능한 작업으로 좁힌다. 경로가 boundary에 없거나 허용 작업 목적에 맞지 않으면, 필요한 경로·이유를 명시한 범위 조정안을 제시하고 해당 파일은 변경하지 않는다. 경로가 포함된다는 이유만으로 런타임 조정 boundary K를 일반 해석 기능 확장에 사용하지 않는다.

## 실패를 증거로 고정

- 사용자 원문, 생성/수정/되묻기 응답 여부, 수정 전 `previous_parsed`, 실제 결과·오류, 기대한 필드와 원문 근거를 확보한다. 재현 입력이 없으면 관련 테스트·로그부터 찾고 의미를 결정할 수 없을 때만 부족한 정보를 묻는다.
- 실제 활성 진입점과 설정을 확인한다. 초기 해석, 수정, 빌더 자유입력은 호출 경로가 다를 수 있다. 기존 문서나 레거시 함수만 보고 실제 경로를 단정하지 않는다.
- 다음 표를 필요한 조건만큼 작성한다. `미지정`, `기존 값 유지`, `삭제 요청`, `미지원`을 구분하고 기대값을 코드 출력에서 역으로 만들지 않는다.

| 원문 근거 | 기대 의미/필드 | 실제 값 | 처음 달라지는 단계 |
|---|---|---|---|
| 사용자 발화의 해당 부분 | 값·단위·연산자·대상·기간 | 누락/변형/오류 | 추출/검증/병합/컴파일/표시 |

## 최초 손실 계층 찾기

관찰된 경로만 읽고 원문 → LLM 원본 응답 → `StrategyIntent` → 검증 → 병합/컴파일 → `ParsedStrategy` → 백테스트 요청 → 표시를 대조한다.

| 증상 | 우선 조사할 파일/디렉터리 | 수정 판단 |
|---|---|---|
| 요청 분기·해석 실패·서버 오류 | `backend/main.py`, `backend/strategy_conversation/primary.py`, `backend/strategy_conversation/config.py` | 호출 오류와 의미 해석 실패를 분리 |
| 의미·조건·수치 누락 | `backend/strategy_conversation/interpreter/`의 `prompts.py`, `llm_strategy_interpreter.py`, `condition_recall.py`, `parse_evidence.py` | 출력 계약·원문 근거·재시도 결과 확인 |
| JSON·타입·단위 드리프트 | `backend/strategy_conversation/interpreter/`의 `output_repair.py`, `models.py` | 유효 출력은 보존하는 형식 정규화인지 확인 |
| 지원 여부·모순·되묻기 오류 | `backend/strategy_conversation/registry/`, `backend/strategy_conversation/validation/` | 실제 지원과 필수값을 구분 |
| 수정으로 이전 조건 소실 | `backend/strategy_conversation/conversation/patch_applier.py`, `backend/strategy_conversation/compiler/strategy_decompiler.py`, `backend/strategy_conversation/primary.py` | patch 출처·미지정/삭제·왕복 보존 확인 |
| 해석은 맞지만 실행 필드 소실 | `backend/strategy_conversation/compiler/strategy_compiler.py`, `backend/engine/strategy_converter.py`, `backend/engine/nl_parser.py` | 변환 단계의 매핑 손실 확인; 엔진 기능 유무와 구분 |
| 빌더 자유입력에서만 실패 | `backend/api/intent_routes.py`, `backend/intent/builder_interpreter.py`, `backend/intent/condition_builder.py` | 실제 빌더 경로에서 재현 |
| 반환값은 맞지만 요약만 틀림 | `app/analytics/new/`, `lib/strategy-summary.ts` | 표시 문제로 좁히고 해석기를 변경하지 않음 |

관련 테스트를 `rg`로 먼저 찾는다. `backend/tests/`의 시작점: `test_interpretation_authority.py`, `test_strategy_conversation.py`, `test_recall_validator.py`, `test_strategy_compile.py`, `test_modify_roundtrip_migration.py`, `test_builder_freetext_interpreter.py`.

## 수정 결정 원칙

- 자연어 의미는 LLM이 해석한다. 실패 문장별 정규식·키워드 분기를 추가하거나 별도 DSL을 만들지 않는다. 결정론 코드는 구조화 출력의 형식·단위·enum 검증과 기존 계약의 지식 조회·출처/수치 대조에 사용한다. 대조 예외의 정확한 조건은 `docs/nl_interpretation_contract.md` §3을 따른다.
- 문서와 코드가 충돌하면 관찰된 동작과 계약을 함께 보고한다. 레거시 예외를 새로운 의미 추론 규칙의 근거로 삼지 않는다.
- 같은 실패 유형을 기존 프롬프트 계약·스키마·정규화·검증·매핑 중 최초 손실 계층에서 해결한다. 프롬프트 예시는 실패 유형을 설명하는 최소 대조쌍만 추가하고 유사 예시를 계속 누적하지 않는다.
- `저평가`, `안전하게`, `많이 하락`처럼 기준이 불명확하면 임의 임계값이나 지표로 확정하지 않는다. 현재 계약에 따라 되묻는다. 미지원 기능은 유사 지표로 대체하거나 조건을 조용히 삭제하지 않는다.
- 새 개념 지원은 표현 인식, 스키마, registry, 검증, compiler, converter, 엔진 지원 여부를 먼저 확인한다. 파서에서 받는 것만으로 실행 지원 완료를 선언하지 않는다. 경계를 넘는 구현은 별도 범위로 남긴다.
- 생성/수정 출력 계약을 구분한다. 해석 실패·빈 재시도 응답으로 유효한 이전 전략을 덮어쓰지 않는다. 관련 없는 후속 질문이 전략 변경 패치를 만들지 않도록 확인한다.
- 누락된 조건은 현재 계약의 안내/되묻기 채널로 노출한다. LLM 연결 장애를 사용자 표현 문제로 바꾸지 않는다. 재시도는 기존 유한 예산을 유지하고 같은 입력의 무제한 호출로 통과 결과를 고르지 않는다.
- 사용자 정의 전략의 의미만 옮긴다. 전략·종목 추천, 시장 전망, 자동 전략 개선, 우열 판단을 추가하지 않는다.

## 회귀 검증과 재사용

1. 원래 실패 경로를 재현하는 테스트를 먼저 실행해 실패 이유를 확인한다. LLM 응답 fixture/mock은 관찰된 드리프트를 재현하고, 의미 검증 기대값은 사용자 원문에서 독립적으로 정한다.
2. 변경 원인에 필요한 대조 사례를 선택한다: 같은 뜻의 구어체/어순, 반대 비교·부정·제외, 금액/%/거래일 단위, 일부 값 미지정, 기존 전략의 한 필드 수정, 재시도 빈 결과, 연결 장애. 모든 작업에 전체 조합을 강요하지 않는다.
3. 성공 여부는 HTTP 200이나 요약 문구가 아닌 구조화된 필드·값·근거, 미변경 조건 보존, 안내 상태로 판단한다. 지원하지 않는 기능은 명확한 미지원 결과도 올바른 결과다.
4. 테스트 명령을 명세에 정확히 적는다. 관련 backend 테스트를 먼저 실행하고 backend 변경 시 `uv run pytest backend/tests`, frontend 변경 시 `npm run test:frontend`를 실행한다. 둘 다 변경하면 둘 다 실행한다. 문서만 변경하면 코드 테스트는 생략 가능하다.
5. 프롬프트 수정에서 mock 통과는 실제 LLM 해석 개선의 증거가 아니다. 가능한 경우 기존 평가 경로·사용 중인 모델로 실패 원문과 대조 사례를 고정해 전후 결과·호출 수를 기록한다. 외부 호출이 불가하면 실모델 검증 미수행을 명시한다. 모델/운영 설정을 임의로 바꾸지 않는다.
6. 해결 사례는 선택 boundary의 기존 회귀 테스트에 원문, 원인, 기대 결과를 남긴다. 관련 평가 코퍼스는 허용 경로일 때만 갱신한다. 사용자 정보·계정 데이터는 제거하고 실패를 성공 데이터로 기록하지 않는다.
7. 완료 전 관련 프로젝트 문서를 검토한다. 문서 갱신은 G에서만 허용되므로 코드 boundary 밖 문서를 함께 수정하지 않는다. 현재 boundary 안의 관련 문서에 작업 내용을 기록할 수 없다면 G에서 필요한 정확한 후속 문서 변경을 보고하고, 문서 반영까지 완료했다고 주장하지 않는다.

Deliver에는 원문→기대/실제 차이, 원인 계층, 변경 파일, 실행 명령과 결과, 실모델 검증 여부, 남은 지원/범위 제약을 포함한다. 반복 실패에서 검증된 공통 절차가 새로 발견됐을 때만 G 작업으로 이 skill을 갱신한다.

## 호출 예시

`$strategy-interpretation "거래대금 50억 이상" 조건이 누락되는 문제를 재현하고 수정해줘.`

`$strategy-interpretation 보유 종목 수만 바꿨는데 기존 청산 조건이 사라져. 수정 전후 전략을 비교해서 회귀 테스트까지 남겨줘.`
