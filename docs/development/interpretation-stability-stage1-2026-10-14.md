# 전략 해석 안정화 — 1단계 조사, 2026-10-14

**해석 오류를 일부 교정하는 장치는 있지만, 판정 실패를 승인과 구분하지 못하고 안내를 중간에 복사하는 구조 때문에 잘못된 조건 확정과 모순 안내가 남는다.**

1. 주문서를 처음 잘못 작성하는 경우가 있다(Interpreter 의미 오류). 과거 원출력과 현재 후처리를 구분해야 한다.
2. 여러 심사자가 서로 다른 양식으로 결과를 전달한다(보조 판정). 실패·불명확을 종종 후보 유지로 소비하며 공통 승인 기록은 없다.
3. 심사 중 발급한 거절서를 배송 안내에 복사한다(검증 오류→notices). 나중에 테마를 해소해도 복사본은 남는다.
4. 검수표 자체도 두 번째 조건이나 모순 안내를 놓친다(하네스 채점). 제품 결함과 검수 결함을 별도로 고쳐야 한다.

한 줄로: 최초 의미 오류, 후처리·승인 오류, 안내 오류, 측정 오류를 분리해 단계별로 수리해야 한다.

## 명세·상태

- Task: 사용자 요청 §11의 1단계, 실패 재현·호출 경로·안내 조립 위치 조사 후 정지.
- Boundary: G — Governance / Policy Docs. 제품 코드 수정 없음.
- Files allowed: 이 문서, `docs/PROJECT_PLAN.md`, `docs/software_architecture.md`, `docs/SRS.md`.
- Do not: 외부 모델 호출, 운영 DB/어휘집/parquet 변경, 보관 기간 연장, 커밋·푸시·배포, 2단계 구현 선행.
- Requirements: 증상 1~9의 현재 근거, 최초 오류와 전파, 생성/수정/빈칸 답변 경로, 안내 쓰기·삭제 지점, 다음 단계 범위 기록.
- Run: 아래 triage·네트워크 차단 재현·기존 관련 테스트·문서 diff 검사.
- Deliver: 조사 보고와 관련 문서 갱신. 전체 안정화는 미완료, 다음 단계 승인 대기.
- 기준 HEAD `4e048137`, 시작 `git status --short` 비어 있음. 코드 prompt `8.13`, schema `1.0`, engine `16.40.0`. 운영 환경 설정을 읽거나 변경하지 않았으므로 코드 기본값을 운영 설정으로 단정하지 않는다.
- CLAUDE/AGENTS, 개발 규칙·boundaries·자연어 계약·DAG 계약, 아키텍처/SRS/계획서의 관련 절, 10-10 감사 및 후속 기록을 검토했다. 과거 통과 숫자는 이번 검증으로 사용하지 않았다.

## 증상 1~9의 현재 근거

| 번호 | 현재 확인 | 최초 오류 및 후속 전파 | 이번 근거 / 한계 |
|---|---|---|---|
| 1 보유 기간→MA/신고가 | 과거 원출력 오류 확인, 기존 수리의 고정 출력 검증 PASS | Interpreter 오분류→quote/holding 판정→조건 제외·기간 복구 | `test_modify_rejected_quote_does_not_apply_invented_exit`, `test_modify_rejected_replace_recovers_explicit_holding_period` 등 통과. 실제 UI 질문과 옛 QA 질문을 구분. 새 모델 재현 NOT_RUN |
| 2 거래량→거래대금 | 유효 volume 판정의 생성·수정 수리 PASS | Interpreter 오분류→trading 판정→조건 제거·교체 삭제 회수 | `test_primary_create_reports_volume_instead_of_asking_for_money`, 수정 volume 3개 회귀 통과. 판정 실패는 후보 유지; live NOT_RUN |
| 3 청산에서 미요청 매수 | 저장 Trace `d0ae4da3747c`의 과거 최초 오류 확인, 현재 역할 재확인 회귀 PASS | Interpreter가 조작 매수 인용 생성→4자 에코·통합 yes 판정 통과 | `test_fabricated_ma_entry_from_exit_needs_independent_role_confirmation` 계열 통과. 같은 모델 두 번의 no는 독립 정확성 보장 아님. 현재 live 발생률 NOT_RUN |
| 4 정성 수익률→0/랭킹 혼동 | 유효 판정 수리 PASS, 판정 None 시 잘못된 확정 **재현 FAIL** | relative_return > 0 후보→판정 없음으로 유지→validation READY→컴파일 확정 | 인용 `최근 60거래일 수익률도 양호한`, period=60, value=0, classifier=None 고정 시 buy relative_return > 0, notices=[], 질문=None. 유효 qualitative/랭킹 회귀 통과. 랭킹이 이미 있으면 전용 대조를 건너뛰는 범위도 있음 |
| 5 거부된 교체의 삭제만 적용 | 알려진 quote/volume 거부 회귀 PASS, 일반 보장 미완료 | 후보 적용 사본→후처리 거부→목록 단위 destructive patch 회수/기존 전략 반환 | `test_modify_rejected_replace_keeps_existing_exit`, `test_modify_volume_rejected_pair_keeps_independent_scalar_patch` 통과. 공통 변경 그룹 없음; 같은 목록의 무관 remove/replace까지 보류 가능 |
| 6 채워진 초안에 빈칸 QA 질문 | entry/exit 비우기·UI 질문 일치 PASS, 다른 fill 슬롯 충돌 **확인** | 하네스가 질문을 고르면서 완성 PREV를 그대로 전달 | `_case_previous_parsed`는 entry/exit만 비움. 현재 KR base의 max_positions=3, stop_loss=6, take_profit=30, period=5y, capital=10000000은 그대로. 빈칸 모드 기준 HARNESS_INVALID 대상; 사전 분류 없음. 실제 사용자 대화 오류로 세지 않음 |
| 7 첫 조건만 검사 | signals 전체 검색 수리 PASS, 재무 필터 첫 항목 실패 **재현 FAIL** | `qa_free_input.filt`가 같은 metric 첫 불일치에서 False 반환 | PER >=5 뒤 PER <=10 목록은 <=10 기대에도 실패. signal 전체 검색 회귀 통과. 의미 전체/중복/AND·OR 판정은 별도 과제 |
| 8 모델·캐시·중단 합산 | 측정 메타·완료 검증 부족 확인, 모든 과거 합산 오류는 단정하지 않음 | 저장 입력 잘림+하네스별 메타 결손→비교 불가능한 지표 | 아래 Trace 집계 참조. free-input 행에 실제 모델/캐시/완료 manifest 없음. template --use-cache는 경고하므로 live 위장으로 단정하지 않음. 중단 재현 NOT_RUN |
| 9 안내와 최종 상태 모순 | 생성 term-in **재현 FAIL**; planner-first에도 같은 복사 경로 | capability 이중 기록→errors를 notices 복사→체인 성공→unsupported만 정리 | 북극항로 고정 JSON+합성 10종목 결과에서 theme 반영과 목록 밖 안내 공존. 원본 사건의 실제 10종목/모델 출력은 보관 Trace에 없음. 합성 재현은 운영 원본 replay가 아님 |

## 실제 호출·상태 전달

| 단계 | 입력·참조 상태 → 후보/근거 | 상태 변경 시점 | 안내·실패·다음 단계 |
|---|---|---|---|
| 프론트 중재 | 원문·분류 라벨·현재 parsed·질문 | 서버 요청/로컬 질문 분기 | conversationDecision 원문 정규식 부채 활성. LLM 진입 전 차단 가능 |
| API 진입 | `_run_nl_parse_impl`, previous_parsed 유무, pending_ask/question/coach/explicit/declined | chip 정확 일치면 결속값 적용; 나머지는 수정/생성 | primary 실패는 초안 보존+해석 실패 질문. primary 비활성만 레거시 해석. main.py:4005–4103 |
| 생성 선행 | 원문→Planner-first/Parse Evidence/조건 구절 추출; 설정별 선행·병렬·지연 | 관찰값 보관, 최종 전략 아님 | Planner 실패/미해결은 기존 체인·질문. primary.py:2072–2180, runtime/planner_gate.py |
| Interpreter | 원문 또는 수정 초안+직전 질문/코치→strategy/patches | JSON repair·Pydantic·유한 재생성·수치/기간 대조에서 후보 변경 | InterpreterError→실패, 연결 장애 전파. models validator도 삭제/이동. 최초 JSON과 intent 구분 |
| 생성 보조·회수 | quote/liquidity/trading/contribution, ETF/holding/relative, 조건 회수 | 검증 전 intent 직접 변경 | repair_notices 문자열 즉시 생성. 실패 시 후보 유지/복구 없음. 회수 후 일부 검사 재소비. primary.py:2180–2270 |
| 수정 후보 | 기존 parsed→실효 기본값→decompile→roundtrip; LLM patches | provenance/numeric/market scope/pair/condition scope 후 apply_patches 사본 | 무패치·전량 거부 등 조기 반환별 안내. pair 모호성은 독립 변경까지 prev 반환. primary.py:4848–5366 |
| 수정 후처리 | patched spec·새 조건·보조 enum/출처 | 테마 검증 전 분리; quote/trading/param/drop 후 일부 patch 재적용 | volume/quote 원자성 가드 별개. 기존 전체 조건 후처리도 수행. primary.py:5367–5570 |
| 검증 | intent deep copy→capability→parameters→conflicts→completeness | copy 정본화·지원 밖 제거·data pending 제거 | errors/warnings/unsupported/missing/questions/preparing 분산 report. READY에서 LLM 질문 삭제; confidence는 판정 안 함 |
| 컴파일 | validated spec+report→ParsedStrategy | 전체/부분 컴파일; 값 미정 제외 | dropped+pending 반환. 수정 own-field 질문/검증 오류는 prev, 다른 슬롯 질문만 있으면 부분 적용. compiler:341, primary:5571–5684 |
| 지식 체인 | 생성 검증 전 sectors/Planner 관찰값, 수정 변경 theme terms | 컴파일 뒤 parsed의 symbols/sector/theme 변경 | 근사 notice·미해결 질문. 수정 실패는 prev 복귀. 정식 replay는 조회/검색/어휘집 결과 고정 필요 |
| 질문·응답 | parsed+report+Planner/queue/pending/provenance | 질문 프루닝·재계획·메타/변경 이력 | primary finalize는 규제/질문·칩 결속 가드이며 최종 상태 대조기가 아님 |
| API 최종 조립 | parsed→최소값·지정종목·profile·실행 요청, primary meta | primary 뒤에도 parsed/안내 변경 | `_build_parse_result`+`apply_primary_meta`+`_flag_unresolved_universe_ask`. 프론트 후속 질문/표시 |

## 안내 생성·정리 위치 목록

primary/API의 안내 소유 함수 및 구조 결과 생산자를 묶은 목록이다. 줄 번호는 조사 HEAD 기준.

| 소유 위치 | 생성/정리 |
|---|---|
| primary `_preparing_notice`:597, `pending_value_notices`:627, `_approximation_notices`:669, `_renamed_symbol_notices`:1059 | 준비 중·값 대기·근사·구 사명 문자열 |
| `_normalize_size_class_labels`:1232, `_dedupe_relative_return_against_ranking`:1278, `_fill_deterministic_condition_params`:1352 | unsupported 정리·랭킹 안내·보유기간 복구 후 unsupported 삭제 |
| `_drop_fabricated_conditions`, `_resolve_trading_value_comparisons` | 출처/의미 거부 안내. 입력 전체 인용 위반은 Trace만 남겨 무안내 삭제하는 경로 존재 |
| 생성:2187–2270,2352–2369 | 보조·회수 repair_notices 누적→warnings+errors 복사→preparing/사명 추가 |
| 생성:2409,2481,2491 | Planner 범위 질문·테마 성공·ETF 반영 후 **unsupported만** 삭제. errors/notices 복사본 잔존 |
| `_prune_clarifications_filled_by_overrides`:48, 생성:2499–2630 | 반영 entry/exit/sector·지정종목·순위·Planner 기준 질문 삭제/교체·큐 |
| 생성:2641–2746 | dropped/pending·근사·잔여 unsupported 안내. 이미 질문/큐/인용/정본에 포함된 항목 텍스트 대조 제외 |
| `_append_sector_notice`:3778, `_apply_planner_first_universe`:3790 | 업종 근사 안내/중복 제거. 종목 복구·테마 상장사 성공 문구는 사용자 notice로 내지 않음 |
| `_apply_universe_chip`:4276, `_resolve_sector_terms_term_in`:4342, `_resolve_sector_terms_planner_primary`:4404 | 학습 업종 근사·Planner 미지원 안내, 체인 실패 폴백 및 미해결/검색 소진 질문 |
| `_resolve_sector_terms_us`:3510, `_resolve_us_universe_change`:4598, `_resolve_theme_change`:4654 | US 미해결·테마 범위·검색 소진 질문, KR 학습 notice; parsed 변경 또는 질문 |
| `_build_clarification`:360, `_modify_clarification`:385, `_reattach_open_question`:421, `_capability_conflict_clarification`:468 | report/기존 질문에서 문장·칩·pending 구성/되붙임 |
| `run_chip_answer`:4127–4274 | 결속 적용·확정/거부·다음 질문; 조기 반환 notices=[] |
| 수정:4984–5359 | 무패치 설명·미지원·provenance 거부·시장/조건 scope·pair 모호성별 안내/질문 |
| 수정:5446–5569 | volume/quote 거부·교체 보류 notice 누적; 일부 복구 분기 repair_notices 재대입 |
| 수정:5587–5648,5685–5760 | own-field/검증 오류를 질문으로 내며 notices=[]+prev; 성공 시 warnings+repair+preparing→체인→시장 복귀→사명·근사 |
| validation capability:863–876 / pipeline:94–176 | sector errors+unsupported 이중 기록. 기타 capability/parameter/conflict/completeness/preparing 결과; 종목 해소 실패 warning |
| compiler:341–430 | dropped/pending 구조 결과, 문장은 primary 소관 |
| response/responses.py:39,62,75 / provenance.py | 질문·미지원·요약 helper / 필드 출처 메타. 공통 최종 정합성 조립기는 아님 |
| response/output_guard.py:67–103 | 규제 문장 제거·질문/칩/결속 동기화. 반영된 대상의 미지원 안내는 통과 |
| main `_build_parse_result`:3510–3693 | 최소값·제외 재무·단일종목·profile·레거시 미지원 notice, 슬롯 질문, 기간종료 안내 삭제 |
| main `_complete_deferred_validation`:3748, `_interpretation_failure_result`:3852, `_run_nl_parse_impl`:4147 | 후행 안내 연결·실패 질문·grounding notice 선두 추가 |
| primary `apply_primary_meta`:5837 / main `_flag_unresolved_universe_ask`:3323 | 질문/결속 채택·억제, 두 notices 배열 연결, 사라진 유니버스 질문 미반영 notice |

생성 term-in과 planner-first는 같은 errors 복사 결함을 공유한다. ETF sectors 승격은 sector 검증 전에 비우므로 동일 오류 문구 발생을 재현한 것은 아니다. ETF 자기 보고 정리·지정종목 warnings·수정 체인도 중간 문자열 생성 구조이지만 각각 최종 상태 모순의 별도 재현이 필요하다. 북극항로와 같은 확정 결함으로 일괄 집계하지 않는다.

## 판정·원자성·계약 격차

- quote는 QuoteVerdicts/객체 참조, trading은 조건/enum 쌍, holding은 patch/수량·단위, numeric은 승인 인덱스 집합, pair는 replace/add/None, scope는 bool/None 또는 인덱스별 bool, region은 term→enum, relative는 enum/None이다. 공통 candidate_id/change_group_id/status/reason/evidence/stage나 충돌 기록이 없다.
- check_batch의 quote:1/trading:1은 배치 내 귀속이며 승인/변경 그룹이 아니다. 무효 section은 단독 호출로 돌아간다. 개별 소비 순서 가드는 있으나 최종 공통 승인 단계는 없다.
- quote/trading/relative/scope 무효·불명확은 대체로 후보 유지, holding 실패는 복구 없음, numeric 실패는 승인 추가 없음, pair 미해결은 **턴 전체 유지+질문**이다. 일괄 fail-open이라는 설명도 부정확하다.
- apply_patches는 deepcopy+전체 schema 검증이다. 범위 밖/음수 index 거부·없는 조건 field patch 승격 수리는 존재한다. add/remove/replace만 허용; 안정적 조건 ID·상태 버전·기대 이전 값 검사 없음. 순차 Pointer 의미를 따르므로 생성 시점 대상 보존의 일반 보장은 없다.
- 기존 quote/volume 목록 단위 삭제 회수는 다시 구현하지 않는다. 독립 변경까지 막는 pair 모호성·같은 목록 과잉 보류를 변경 그룹별로 나누는 것이 후속 과제다.
- **계약 위반:** primary 매수 cue·EMA·보유기간 등 인용 의미 재해석과 `conversationDecision.ts:253–312` 원문 패턴 판정은 활성 부채다. literal provenance/숫자 표기 대조와 canonical lookup 자체는 계약 예외다. 어휘/regex 보강을 수정안으로 삼지 않는다.
- **문서 충돌:** SRS의 정성 수익률 0 금지와 실패 시 후보 유지 문장이 공존하며 실제 None 재현은 후자를 따른다. 아키텍처의 독립 패치 불간섭 설명은 같은 목록 단위 보류의 보장보다 넓다. 요구와 실제의 격차를 후속 메모에 명시한다.

## Trace·하네스 기준선과 실행

- Triage **PASS**: `cd backend && UV_CACHE_DIR=/tmp/simons-uv-cache uv run --frozen python scripts/triage_traces.py`. 기본 uv cache 쓰기는 INFRA_BLOCKED 후 임시 cache로 재실행. 10-12~14 JSONL 1,153 레코드·30그룹. 결함 후보 30건/8그룹, 확인 필요 16/8, 제품 공백 15/12, 인프라 20/2. 배타적 실패율이 아니며 레코드=사용자 턴으로 단정하지 않는다. 리포트는 기존 backend/logs/triage/ 3일 정책 유지.
- Trace 재귀 조사: LLM span 1,907개, 라벨 120B 1,537개·9B 370개. 오류/재시도/별도 probe 포함이며 성공 실응답 분포가 아니다. 응답 model/provider 기록 코드는 있지만 성공 여부 확인 없이 실응답으로 세면 안 된다.
- tracing.py:55,91–100,213은 **JSONL 이전에** 문자열 4,000자·배열/객체 80항목으로 자른다. LLM 입력 system_prompt 1,189개·user_prompt 13개에 생략 표지. 버전만으로 과거 registry/질문/설정을 복원할 수 없으며 콘텐츠 주소 복원 계약도 없다. 잘린 입력을 실행하지 않았다.
- free-input entry/exit 수리는 검증됨. 재무필터 첫 불일치·다른 fill 슬롯 충돌·실제 모델/캐시/완료 manifest 결손은 남는다. notices를 기록하지만 verdict에 쓰지 않아 max_positions=8과 “기존 전략 유지” 안내가 공존해도 PASS.
- template은 사람 작성 KR 기대값과 --use-cache 경고를 사용하며 후처리 replay가 아니다. display sweep은 notices도 검사하지만 enum/빈값/영문 잔존 검사이며 상태 모순 검사가 아니다. missing cache를 출력해도 covered>0만 요구해 전수 coverage gate도 아니다. multiturn은 질문/pending/explicit을 이어 보내나 공통 replay/manifest 없음.
- 고정 출력 재현: `cd backend && UV_CACHE_DIR=/tmp/simons-uv-cache uv run --frozen python /tmp/simons-stage1-reproduce.py`. 결과 `/tmp/simons-stage1-reproduce.txt`. socket 연결 차단·tracing 비활성·Planner/override/condition recall off·Interpreter stub. 북극항로 조회는 합성 10코드 성공으로, `_extract_sector`도 고정해 공유 어휘집을 사용하지 않았다. 정식 replay 도구/운영 사건 원본 replay는 **미구현/NOT_RUN**.
- 기존 관련 테스트 **PASS**: `cd backend && PYTHONPATH=/tmp UV_CACHE_DIR=/tmp/simons-uv-cache uv run --frozen pytest -p simons_stage1_guard tests/test_strategy_conversation.py tests/test_quote_check.py -q`. 414 passed, 10 warnings, 11.44s. 임시 plugin `/tmp/simons_stage1_guard.py`는 socket 연결 차단·tracing 비활성. 선별 34 passed·380 deselected 뒤 두 파일 전체 확인. 제품 코드/새 회귀 테스트 수정 없음.
- 현재 결함 기준선: 북극항로 합성 1건 모순 안내, qualitative/None 합성 1건 잘못된 0 확정, 필터 합성 1건 오FAIL, 안내 합성 1건 오PASS. 작은 목적 표본이며 발생률 추정에 쓰지 않는다. 코드 수정 전후 비교는 **NOT_RUN**.
- 외부 모델 신규 호출 **0회**. live KR/US 생성/수정/fill, 운영 latency/보류율/질문율/잘못된 조건 반영률, 프론트 suite/display sweep/백엔드 전체 suite는 **NOT_RUN**. 문서 변경만이므로 전체 코드 suite는 이번 단계 필수 검사가 아니다. 과거 DNS/DB/DART 실패를 이번 실행 결과로 재사용하지 않는다.

## 다음 단계의 승인 범위

1. 2단계는 W의 `scripts/qa_free_input.py`, `scripts/qa_template_detect.py`, `backend/tests/**`에서 fixture 사전검사·전체 조건/안내 채점·결과 상태를 작은 작업으로 나눈다. 제품 행동 계약을 바꾸지 않는다. 장기 fixture는 사람이 검토한 최소 합성 사례로만 보관한다.
2. 정식 replay의 check/knowledge 고정·복원 가능한 요청 원본·모델/완료 manifest는 W 밖 관찰 계층이 필요할 수 있다. 범위 후보는 `backend/observability/tracing.py`, `backend/observability/agent_trace.py`, replay 전용 파일/fixture이며 정확한 이름은 2단계 명세에서 확정. Trace 3일과 장기 최소 fixture를 분리. 승인 전 경계 수정 없음.
3. 3단계 생성 테마/업종 최종 안내 조립은 primary, 내부 response 조립 모듈, capability의 sector 결과, pipeline 결과 전달 범위가 필요하다. W는 capability **operator 문구만** 허용하므로 선행 범위 승인 필요. 수정·ETF·지정종목 확장은 3단계 보고 후 별도 승인.
4. 5단계 필수 판정 목록·보류율/질문율 영향안은 아직 확정하지 않았다. W fail-open·자연어 계약과 함께 바꿔야 하는 행동 계약이다. 승인 전 신규 미해결 보류는 구현하지 않는다.

**사용자 요청 §11의 단계 게이트에 따라 정지한다. 1단계 조사만 마쳤으며 전체 안정화는 미완료다. **
