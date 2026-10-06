# 분기 영업이익 YoY 근사 안내 조사 (2026-10-06)

- Task: “최근 분기 영업이익이 전년 동기 대비 증가하고”의 근사 안내 원인 조사.
- Boundary: G — Governance / Policy Docs.
- Files allowed: 이 문서.
- Do not: 애플리케이션 코드, 데이터, 모델 설정 변경.
- Requirements: 지표 지원 여부와 안내 발생 조건을 분리해 재현한다.
- Run: `UV_CACHE_DIR=/tmp/simons-uv-cache PYTHONPATH=backend uv run --no-sync python`으로 아래 코드를 실행.
- Deliver: 원인 및 검증 한계 기록.

## 결과

`fundamental.operating_income_growth_yoy`는 registry에 등록되어 있다.
하지만 `factor_ids_named_in`은 원문에서 `fundamental.ebit`만 추출한다.
`primary._substituted_factor`는 이 금액 지표와 선택된 성장률 지표를 서로 다른
지표로 판단해 true를 반환한다. `_approximation_notices`는 이 결과만으로도
“정확히 표현할 수 없어 … 가깝게 반영했어요”를 만든다.
따라서 LLM이 `approximated=False`를 출력해도 첨부 화면의 안내가 재현된다.

```python
from types import SimpleNamespace
from strategy_conversation.primary import _approximation_notices, _substituted_factor
from strategy_conversation.registry import indicator_registry as registry

condition = SimpleNamespace(
    factor="fundamental.operating_income_growth_yoy",
    source_text="최근 분기 영업이익이 전년 동기 대비 증가하고",
    approximated=False,
)
strategy = SimpleNamespace(entry_conditions=[condition], exit_conditions=[], ranking=[])
print(registry.factor_ids_named_in(condition.source_text))
print(_substituted_factor(condition, registry.resolve(condition.factor), registry))
print(_approximation_notices(strategy))
```

실행 성공: named는 `{'fundamental.ebit'}`, substituted는 `True`, 안내는 첨부 화면과 동일했다.
`approximated=True`에서도 동일 안내가 나왔다. 최초 uv 실행은 기본 캐시 접근 제한으로
실패해 `/tmp` 캐시와 기존 환경(`--no-sync`)으로 재실행했다.

별도의 실제 지원 제약도 있다. `quarterly_earnings.quarterly_growth_events`는 전년
동기 값이 0 이하이면 성장률을 생성하지 않는다. 양수 기준 분기에서는 YoY > 0이
영업이익 증가를 표현하지만, 적자 축소·흑자 전환까지 모두 포괄하지는 못한다.
이 제약은 이번 안내 함수가 검사하는 내용이 아니다.

실제 요청의 LLM 원본 응답은 확보하지 않았으며 실모델 호출은 수행하지 않았다.
재현은 안내 생성 경로의 오탐을 확인한 것으로, 당시 연산자·임계값까지 검증한 것은 아니다.
첫 조사 시점에는 코드를 변경하지 않았다. PROJECT_PLAN, SRS,
software_architecture의 관련 문서를 검토했다.

## 수정 작업 범위 (후속 요청)

`docs/architecture/boundaries.md`에 Boundary U를 추가했다. 첫 수정에서는
YoY 영업이익 **성장률** 조건의 `fundamental.ebit` 명칭을 대체 판단 근거에서 제외했다.
아래 직접 비교 지표를 구현하면서 이 예외를 제거했다. 성장률은 전년 적자·0일 때
원문의 '증가'와 같지 않으므로, 성장률을 선택한 경우에는 이제 근사 안내가 다시 나온다.
직접 비교 지표에는 같은 명칭 대조의 오탐이 없다. 명시적 `approximated=True`
신고와 다른 지표명 대체 검사는 유지된다.

회귀 테스트는 원래 문구와 정확한 YoY 지표, 명시적인 근사 신고, 기존의 다른 지표 대체
사례를 확인한다. `test_strategy_conversation.py` 전체 321건은 통과했다.
`pytest backend/tests`는 두 sync 테스트의 `pykrx` import가 외부 KRX DNS 접속에서
실패해 수집 단계에서 중단됐다. 이를 제외한 재시도에서도 로컬 PostgreSQL 연결이
허용되지 않아 전체 통과는 확인하지 못했다. 실제 LLM 출력과 실모델 결과는 검증하지 않았다.

## 정확한 비교 의미 지원 요청

- Task: 최근 발표 분기 영업이익이 전년 같은 분기보다 큰 조건을 적자·0 기준을 포함해 해석하고 실행한다.
- Boundary: V — Quarterly Operating Income Comparison (엔진·해석·표시를 작은 독립 단계로 나눔).
- Files allowed: Boundary V의 명시 경로만 단계별 3~5개씩.
- Do not: 기존 `operating_income_growth_yoy`의 백분율 의미·계산을 바꾸거나 원문 정규식을 추가하지 않는다.
- Requirements: 발표일 기준 가용 데이터만 쓰고, 비교 분기가 없으면 조건을 미충족으로 처리한다. 정확한 비교 지표와 백분율 성장률을 구분한다.
- Run: 관련 회귀 테스트, `uv run pytest backend/tests`, 프론트 변경 시 `npm run test:frontend`.
- Deliver: 작은 단계별 변경, 검증 결과, 데이터 커버리지와 실모델 검증 한계.

## 후속 구현·검증 결과

- 새 지표 `operating_income_yoy_direction`(-1/0/1)을 등록했다. `> 0`은 최근 발표 분기 영업이익이 전년 같은 분기보다 클 때만 참이다. 기존 백분율 성장률의 계산·이름은 유지했다.
- 엔진은 공시일 순으로 알려진 자료를 갱신한다. 적자 축소, 0에서 흑자 전환, 동일, 비교 분기 부재, 늦은 전년 공시가 도착한 뒤의 재계산을 테스트했다. 결측은 NaN으로 남아 필터가 통과시키지 않는다.
- 프롬프트가 '증가 여부'와 'N% 성장률'을 구분하고, 새 지표의 컴파일 및 사용자 표시 라벨을 연결했다. 온톨로지 분류·polarity도 등록했다. 관련 백엔드 344건, 프론트 전체 2,361건 통과. 백엔드 전체는 `pykrx`가 외부 KRX DNS에 닿지 못해 수집 단계에서 중단됐다.
- 로컬 분기 캐시 498개 중 영업이익이 들어 있는 파일은 0개였다. 따라서 이 작업공간에서 실제 종목을 판정할 수 없다. 운영 캐시 상태는 확인하지 못했다. 캐시가 채워질 때까지 종목은 결측으로 처리된다.
- 로컬 9B 실모델의 첫 호출은 온톨로지 누락 상태에서 기존 백분율 성장률 `>= 0`을 골랐다. 이때 온톨로지 무결성 경고 2건을 확인해 시드에 새 지표를 등록했다(등록 후 무결성 위반 0). 앱 기본 200초 재호출은 시간 초과였다. 같은 9B 모델·시스템/사용자 프롬프트·`temperature=0`·JSON 옵션으로 진단 제한 시간을 330초까지 허용한 호출은 약 45초 만에 `fundamental.operating_income_yoy_direction`, `>`, `0`, `approximated=false`를 반환했다. 실제 모델의 해당 문장 해석은 확인됐으나 앱 기본 시간 제한에서 항상 응답하는지는 미검증이다.

## 원문 요청의 내부 API 재검증

2026-10-06 후속 확인에서 스크린샷의 전체 원문을 로컬 Next API
`/api/strategy/parse/stream`으로 전송했다. 새 전략의 `parsed_final`은
`operating_income_yoy_direction > 0`, `notices=[]`를 반환했다. 처음에는
같은 영업이익 표현을 별도의 값 미정 `ebit` 조건으로 중복 출력해 금액 기준값을
다시 물었다. Boundary V의 인터프리터 지시에서 이 중복을 금지하고
`PROMPT_VERSION`을 `8.7`로 올려 기존 응답 캐시를 무효화했다. 수정 후 같은
원문을 실제 로컬 API로 재요청한 결과 `pending_conditions`에는 별개 표현인
영업이익률만 남았고 영업이익 금액 질문은 사라졌다.

기존 전략의 옛 `operating_income_growth_yoy > 0`을 포함한 `previous_parsed`와
명시적인 교체 요청도 로컬 API로 테스트했다. 반환된 `fundamental_filters`는
`operating_income_yoy_direction > 0`으로 교체됐고 `notices=[]`였다. 단순히
전체 원문을 같은 대화에 다시 보내는 요청은 수정 의도가 불분명해 기존 조건을
보존하고 되물었다. 과거 대화 메시지 자체는 재작성되지 않는다.

관련 백엔드 테스트 331건 통과. `uv run --no-sync pytest backend/tests -q`는
`test_sync_data_status.py`, `test_sync_fundamental_enrichment_gate.py` 수집 중
`pykrx`의 KRX DNS 조회 실패로 중단됐다. 이번 검증은 로컬 실행 환경에 한정되며
배포 환경 반영은 확인하지 않았다.
