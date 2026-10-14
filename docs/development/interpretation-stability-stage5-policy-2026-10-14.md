# 전략 해석 안정화 — 5단계 보조 판정 보류 정책안

상태: **정책안 승인됨** — 2026-10-14 사용자의 “구현 진행 해”. 격리 작업트리의 [구현·최종 검증](interpretation-stability-stage5-implementation-2026-10-14.md)을 따른다. 아래 정책안 작성 시점의 추정/검사 기록은 당시 결과로 보존한다.

Task:
기존 보조 판정의 실패 행동을 조사하고 필수 판정·그룹별 보류·안내 및 영향 검증 정책안을 작성한다.

Boundary:
G: Governance / Policy Docs.

Files allowed:
- docs/development/interpretation-stability-stage5-policy-2026-10-14.md
- docs/PROJECT_PLAN.md
- docs/software_architecture.md
- docs/SRS.md

Do not:
- 정책안 승인 전 행동 계약·런타임·테스트 fixture·State·공개 스키마 변경
- 사용자 원문 의미 regex/키워드 재판정, 모든 신규 조건에 보조 호출 추가
- 커밋·푸시·배포·데이터/어휘집 변경·외부 모델/검색 호출

Requirements:
- 현행 적용과 제안 행동을 구분하고 필수 판정의 적용 조건·성공 근거를 명시
- 기존 상태·독립 변경 보존, 교체 전체 보류, 미해결과 미지원 안내 구분
- 고정 합성 자료로 영향의 조건부 추정과 측정 불가 항목을 구분
- 구현 전 승인 대상과 구현 후 정확한 검증 명령·불변 조건을 제공

Run:
- 기존 4단계 코드와 `/tmp/simons-stage4-replay.json`의 판정·최종 상태·질문을 읽기 전용 대조
- `git diff --check -- docs/PROJECT_PLAN.md docs/software_architecture.md docs/SRS.md`
- 새 문서 공백·링크 확인; 문서만 수정하므로 코드 테스트 재실행 없음

Deliver:
- 4파일·200줄 이내 문서 변경, 필수 판정 목록·영향·승인 게이트 보고

## 1. 현재 문제와 제안

검수 결과가 비어 있으면 새 서류를 확정하지 않고, 이미 확정된 서류와 별개의 수정은 보존한다. 이것을 모든 검사의 실패로 전략 전체를 취소하는 규칙으로 만들지 않는다.

1. 현재 수치 보조 확인은 실패하면 이미 거부된 패치를 승인하지 않는다. pair 미확정도 기존 조건을 보존한다. 반면 quote·trading·수익률·시장 범위의 실패/불명확은 일부 후보를 유지한다. “모든 보조 검사가 fail-open”이라는 설명은 정확하지 않다.
2. 4단계의 기록 ACCEPT는 분류 성공 또는 기존 적용 정책을 뜻할 수 있다. 이를 필수 검증 충족으로 그대로 사용하면 안 된다. 필수 검사 적용 여부와 대상 연결을 먼저 확정하고, 각 검사 고유의 성공 근거를 확인한다.
3. **제안**: 이번 턴의 신규·변경 후보에 적용되는 필수 검사가 REJECT 또는 UNRESOLVED이면 해당 그룹만 보류한다. 기존 조건은 재심 실패 때문에 변경·삭제하지 않는다. 독립적으로 승인된 다른 그룹은 기존 검증·컴파일을 거쳐 적용한다.
4. 생성은 보류 후보를 실행 상태에서 제외하고 승인된 부분만 구성한다. 수정·fill은 원래 값을 유지한다. remove/add와 같은 조건의 형제 필드는 한 그룹으로 보류한다. 전체 재작성은 이전 상태와 교체 후보를 함께 소유하는 그룹으로 처리하고 일부 필드만 몰래 삭제하지 않는다.
5. 분류·복구가 새로운 후보를 만들면 원래 후보와 근거를 연결해 해당 복구 후보를 검증한다. 같은 모델의 재확인 두 번을 독립 정확성 보장으로 세지 않는다.

## 2. 필수 판정 목록 — 기존 호출 대상 안에서 적용

검사 적용 여부는 LLM 출력의 factor/역할/경로·기존 대상 선택 결과·정본 지원 정보로 결정한다. 사용자 문장을 새로 패턴 매칭하지 않는다. 아래는 **제안 목록**이며 아직 런타임 계약이 아니다.

| 필수 항목 | 신규·변경 후보의 적용 조건 | 성공으로 인정할 근거 / 보류 처리 |
|---|---|---|
| Q: 조건·역할 인용 대조 | 기존 `quote_check.targets_for_intent`가 고른 MA/볼린저 계열의 인용 있는 조건; 수정은 변경된 조건만 | 기존 정규화 판정의 expresses=yes와 구조/역할 검증. 확정 no/other는 REJECT, 재확인 불일치·unclear·결과 없음은 UNRESOLVED. 성공한 다른 조건의 판정을 공유하지 않음 |
| T: 거래대금 비교 대상 | 기존 `trading_value_check.conditions_to_check` 대상: 값 없는 거래대금 계열·인용 있는 후보 | amount/own_average 분류와 이후 값·파라미터 검증. volume은 기존 거부 유지. unclear/실패는 보류하며, 정상 own_average라도 배수 미정이면 기존 값 질문을 유지 |
| R: 수익률 0의 의미 대조 | 기존 `reconcile_qualitative_return` 대상: ranking 없음, relative_return >/>= 0, 인용 있음 | relative_positive만 해당 0 비교를 확인. 순위 분류는 별도 ranking 후보로 옮겨 필수 기간 검증. 정성 분류는 값 대기. None/unclear는 비교/순위 의미 미해결로 보류; 임의 0·임의 roc·기간을 만들지 않음 |
| N: 수치 패치의 보조 확인 | 기존 출처 대조에서 통과하지 못했고 수치·인용을 가진 기존 numeric 후보 | 기존 확인 인덱스와 인용·수량·경로·정본 단위 환산 근거. 빈 set/누락은 UNRESOLVED이지 자동 REJECT가 아님. 기존에는 미반영되던 항목을 이유·보류 안내로 추적 |
| M: 시장 범위 변경 출처 | 기존 후보 중 이번 턴에 적용하려는 `/universe/markets` 패치 | 기존 yes+유효 인용과 지역 지원. no는 REJECT; None/unclear는 시장 그룹 보류, 기존 시장·종목 유지 |
| C: 질문/추가 조건 출처 | 기존 condition scope 호출 안에서 `scope_targets`로 정한 후보 | 해당 인덱스의 True와 기존 값 검증. False는 REJECT; 키 누락/형식 실패는 UNRESOLVED. 함께 요청에 담겼지만 scope_targets 밖인 조건까지 새 필수 검사로 확대하지 않음 |
| P: 추가·삭제 관계 | 기존 pair 대상: 같은 목록의 add와 근거 미확인 remove | 유효 replace는 같은 그룹, add는 기존 remove 미승인 유지. None/unclear·다대다 관계 미확정은 파괴적 변경 보류. 이미 4단계에 보류·독립 수정 보존이 있음 |
| H: 보유 기간/단위 확인·복구 | 기존 residual 대조가 선택한 quoted hold/min_hold 수치 패치와 기존 misfiled recovery 후보; 호출 대상 확대 없음 | day/month/year와 인용 수량, 정본 1/21/252 거래일 환산을 확인. **정책안 당시 holding_days ACCEPT만으로 필수화 금지**: 월·년·한글 수량이 UNRESOLVED로 섞였음. 기존 LLM의 수량 출력 표기/수치 근거를 보완하고 확인 불가면 보류. recovery None은 원 조건 부활/기간 추정 근거가 아님 |
| G: 미해결 종목 지역 판정 | 기존 KR 지역 guard가 check_markets에 넘긴 이번 턴의 미해결 종목 표현 | 지역 enum을 실제 universe 그룹에 연결한 뒤 지원 여부·정본 종목 해소까지 확인. KR 분류만으로 임의 종목 승인 금지; US/OTHER는 해당 지원 계약 판정, 실패는 새 universe 후보 보류. 이미 확인된 기존 종목은 변경하지 않음 |

스키마·경로·지원 여부·필수값·단위·모순 검사는 계속 필수다. 보조 의미 검사 ACCEPT가 이 검사를 대체하지 않는다. 기존 도메인 오류를 성공으로 바꾸거나 한 그룹 성공으로 다른 실패를 숨기지 않는다.

**이번 정책으로 필수화하지 않는 것**: 기존 검사 대상 밖의 모든 조건, contribution/liquidity·일반 recall·planner/지식 조회·ETF/US 전 체인. 기존 동작을 유지하고 누락된 공통 근거/대상 연결은 별도 확장 범위로 남긴다. 원문 의미 패턴 매칭 부채는 여전히 **미이관 위반**이며 적용 조건의 새로운 근거로 사용하지 않는다.

## 3. 승인·보류·질문의 정확한 계약

- 적용 계획에는 필수 여부와 대상 후보/그룹을 기록한다. 적용 조건 밖은 NOT_APPLICABLE 메타데이터로 표시하며 판정의 세 상태를 늘리지 않는다. 필요한 결과가 없거나 근거를 후보에 연결할 수 없으면 UNRESOLVED다. 성공 JSON·리터럴 인용·LEGACY_ELIGIBLE만으로 필수 검증을 충족했다고 하지 않는다.
- 필요한 모든 근거와 구조·도메인 검증을 만족한 그룹만 적용한다. 서로 다른 검사의 충돌 우선순위는 REJECT > UNRESOLVED > ACCEPT이며 과거 근거를 보존한다. 정당한 복구는 별도 후보의 근거로 처리하고 동일 후보의 거부를 기록 없이 덮지 않는다.
- 사본에서 검증하고 4단계 정체성/기준 상태 검사 후 최종 반영한다. 동일 목록의 관계 불명확 삭제는 계속 보수적으로 보류한다. 교차 슬롯 모순의 관련 범위를 증명하지 못하면 기존 전체 복귀 안전 동작을 유지하고 그 제한을 보고한다. 모든 전역 검증의 독립 그룹화를 완료했다고 주장하지 않는다.
- 의미 판정은 성공했지만 수치가 없으면 기존 missing·value_source=MISSING·pending_conditions로 값 질문을 만든다. 의미/역할 자체가 미해결이면 아직 확정된 factor로 표시하지 않고 기존 clarification/pending_ask와 안내를 사용한다. 수정에서 보류 후보를 실행 가능한 새 조건으로 싣지 않는다.
- 같은 턴의 실행 가능한 기존 전략은 유지하되 “변경 적용 완료”로 보류 항목을 표시하지 않는다. 최종 반영·보류 그룹에서 안내를 조립하고 질문은 한 번에 하나, 나머지는 기존 질문 큐 계약에 연결한다. 보류 때문에 unrelated 다음 슬롯 질문이 필요한 확인을 가리지 않게 한다.
- 판정 실패·불명확은 **미지원**과 구분한다. 예: “조건 확인을 완료하지 못해 해당 변경은 보류했어요. 기존 조건은 유지했어요.” 생성에는 기존 조건 유지 문장을 붙이지 않는다. LLM 연결 장애를 사용자 표현이 잘못됐다고 설명하지 않는다. 명확한 비교/순위 미정에는 “수익률은 시장과 비교할까요, 종목 간 순위로 정할까요?”와 같은 기존 문맥에 맞는 질문을 사용한다.
- reason은 관찰된 경우에만 AUX_UNCLEAR/AUX_UNAVAILABLE/AUX_MALFORMED/EVIDENCE_MISMATCH/REQUIRED_RESULT_MISSING/DEPENDENCY_UNCONFIRMED로 구분한다. 현재 None에는 실패 원인이 섞여 있으므로 근거 없이 timeout 등으로 단정하지 않는다. cancellation은 기존 요청 중단이며 질문으로 바꾸지 않는다.

## 4. 영향 — 합성 자료의 조건부 추정, 운영 비율 아님

읽기 전용 자료: 4단계 코드, 10건의 `/tmp/simons-stage4-replay.json`, 사람이 정한 기존 fixture 기대. 모델은 synthetic-fixture, schema 1.0·엔진 16.40.0·기반 4e048137, 재생 코드 해시 `6b2a5606e23a3ac766b06ed5a4ec853b9e74f6624c723c946f53cb335af70f30`이다. 실제 모델/검색 호출 0회다. 27개 recorded_calls 항목은 LLM과 고정 helper tape가 섞여 있으므로 모델 호출 수로 세지 않는다.

| 지표와 분모 | 4단계 실제 | 정책이 의도대로 구현될 경우의 조건부 영향 |
|---|---|---|
| 10건 중 잘못된 임계값 반영 | qualitative-unresolved 1/10 | 해당 후보를 보류하면 알려진 결함 0/10 목표. 아직 실행·PASS 판정 아님 |
| 보조 거부/미확정 때문에 그룹을 보류한 사례 / 10건 | rejected-replace-independent·unclear-pair-independent 2/10; 테마 질문 등은 별도 | qualitative-unresolved 추가로 3/10, **+1건(+10%p)** 추정. 조건 그룹 수의 비율과 다름 |
| 최종 질문 있는 사례 / 10건 | 10/10 | 계속 10/10 추정. 정성 수익률의 무관한 익절 질문 1건을 수익률 확인으로 교체; 질문 발생률 +10%p라고 계산하면 잘못임 |
| 불필요한 질문율 | 필요/불필요 전수 gold·완결 전략 표본 없음 | 추정 불가. 정상 월·년·한글 수량을 먼저 검증하지 않으면 오보류/질문이 늘어날 위험 |
| 모순 안내·새 모델 호출·지연 | 알려진 북극항로 안내 PASS; 모델 호출 0; replay는 시간을 고정 | 안내/기존 9 PASS 보존 목표, 새 보조 호출 추가 0 목표. 실제 운영 지연·오류율 미측정 |

기존 자료에는 Q/T/H/M/C/G의 실패·불명확 대조 사례가 충분하지 않다. +1건은 이 10건 안의 영향일 뿐 배포 후 보류율 예상이 아니다. 보류로 다음 턴의 대화가 늘어날 수 있지만 종결까지 턴 수를 측정한 자료도 없다. live 결과·지역·실제 응답 모델·캐시 여부가 다른 표본을 합산하지 않는다.

## 5. 승인 후 구현 단위·검증

**제안 구현 범위**는 위 Q/T/R/N/M/C/P/H/G의 기존 대상·호출 예산 안이다. H의 정상 단위 및 G의 실제 universe 그룹 연결, R의 원 조건/복구 후보 연결을 먼저 보완해야 한다. 해석 분기·프롬프트·모델 변경과 모든 신규 조건의 검사 확장은 포함하지 않는다.

1. Boundary W에서 검사 적용 계획·누락 근거·단위/후보 연결을 먼저 보강하고, 보류 정책은 후보/그룹에서 소비한다. 4단계 식별/승인 모듈·primary·기존 검사/회귀를 각 1~5파일 단위로 나눈다. 경계에 없는 일반 validation/response 전달 확장이 필요하면 경로·이유를 보고하고 G의 범위 승인부터 받는다.
2. 새 테스트는 의미별 고정 결과 yes/no/unclear·None·malformed·항목 누락·재확인 불일치, 일/월/년/한글 수량의 정상 사례, 복구 실패·취소, 기존 조건·독립 수량·다른 조건 보존을 포함한다. 특히 실패한 교체의 remove만 적용되거나 옛 조건이 silently 사라지지 않아야 한다. 새 조건 소실은 반드시 보류 안내/질문으로 드러나야 한다.
3. 재현 corpus는 현재 gold를 완화하지 않는다. qualitative-unresolved는 변경 전 FAIL을 재확인하고 구현 후 0 조건 미반영·수익률 질문·표시까지 PASS를 요구한다. 기존 9 PASS는 유지해야 한다. 실제 US/영문 페이지는 별도 검증 대상으로 남긴다.
4. AgentsTab 흐름도 및 자연어 해석 계약/SRS/아키텍처/계획서는 승인된 행동에 맞춰 별도 경계로 갱신한다. public 응답 키·StrategySpec·JSON Patch·State DAG를 새로 설계하지 않는다.

승인 후 실행할 명령:

```sh
cd /Users/eugene/nullalgo/simons-wt/interpretation-replay-stage2/backend
PYTHONPATH=/tmp UV_CACHE_DIR=/tmp/simons-uv-cache uv run --frozen pytest -p simons_stage2_guard tests/test_interpretation_decisions.py tests/test_patch_group_approval.py tests/test_strategy_conversation.py tests/test_interpretation_replay.py tests/test_check_batch.py tests/test_quote_check.py -q
PYTHONPATH=/tmp UV_CACHE_DIR=/tmp/simons-uv-cache uv run --frozen pytest -p simons_stage2_guard tests/ --ignore=tests/test_backtest_engine.py --ignore=tests/test_engine_ai.py --ignore=tests/test_ai_sell.py --ignore=tests/test_api_isolation.py
cd /Users/eugene/nullalgo/simons-wt/interpretation-replay-stage2
npm run test:frontend
UV_CACHE_DIR=/tmp/simons-uv-cache uv run --frozen python scripts/qa_template_detect.py --replay backend/tests/fixtures/interpretation_replay.json --out /tmp/simons-stage5-replay.json
```

코드 변경 시 ALL PASS가 원칙이며 범위 밖 기존 parquet 컬럼 FAIL은 원인·미수리 사유를 별도 보고한다. live KR/US·81예시·변동성·질문/보류율·지연 측정은 호출 수와 실제 모델을 먼저 제시하고 별도 승인 후 수행한다. 정책안 승인을 live 호출 승인으로 사용하지 않는다.

## 6. 정책안 작성 시점의 결과와 승인 지점

- G의 위 4개 문서만 변경했다. 이전 2~4단계 코드는 같은 격리 작업트리에 미커밋 상태로 보존했고 타 세션 문서를 변경하지 않았다. 신규 테스트/fixture·런타임 변경과 외부 호출은 0회다. 문서 diff 공백·새 보고서 공백/길이·링크·명령의 테스트 파일 존재 검사는 **PASS**다. 현재 strategy_conversation 전체 소스 해시도 위 4단계 재생 해시와 동일함을 확인했다. 문서만 변경해 전체 코드 테스트는 재실행하지 않았다.
- 현행 코드 테스트 기준선은 4단계의 관련 490 PASS·backend 5,797 PASS/5 skipped/기존 컬럼 1 FAIL·frontend 2,430 PASS/2 skipped·replay 9 PASS/1 FAIL이다. 이번 정책안의 새 실행 결과가 아니다. 구현 후 동작과 운영 품질은 **NOT_RUN**이다.
- 정책안 단계는 원래 요청 §8의 “어떤 판정을 ‘필수’로 볼지 목록과 영향(보류율·질문율 추정)을 먼저 보고하고 승인을 받은 뒤 구현한다” 및 §11의 “5. 보류 정책안 → 승인 후 구현”에 따라 승인 전에 멈췄다. 위 9개 필수 항목·그룹 보류·기존 상태/독립 변경 보존·보류 안내/질문·호출 확대 없음의 구현은 이후 사용자가 승인했다. 현재 결과는 위 구현 보고를 따른다.
