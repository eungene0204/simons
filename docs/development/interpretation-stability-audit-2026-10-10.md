# 널스탁 primary 해석 레인 안정화 진단 — 2026-10-10

**회귀는 LLM 출력 뒤에서도 재현된다. 조건을 서로 다른 기준으로 합치거나 삭제하는 여러 계층과, 그 손실을 놓치는 측정이 핵심 원인이다.**

> **후속 실행(같은 날):** 아래 본문은 승인 전 진단 시점의 구조·재현 결과다. 승인 후 조건 정체성·패치·재생성 보존·위험 값 조립 실패를 각각 작은 변경으로 고쳤다. 정확한 변경·검증·미검증 상태는 맨 아래의 후속 실행 절을 따른다.

1. 장바구니에 물건을 하나 더 넣었는데 기존 물건이 빠지는 경우가 있다. 같은 지표라는 이유만으로 서로 다른 기간의 매수·매도 조건을 하나로 취급한다(조건 정체성 충돌).
2. 잘못 쓴 주소 한 칸을 다시 받으면서 주문서 전체를 갈아 끼운다. 재생성 결과에서 정상 조건이 빠져도, 현재 보존 장치는 질문·미지원 목록만 복구한다(재생성 경계).
3. 주문서 검사보다 포장 단계의 제약이 더 엄격하다. 일부 잘못된 값은 검사를 지나 조립 단계에서 예외를 내며, 다른 정상 조건까지 결과를 받지 못하게 한다(실패 단위).
4. 검수표는 물건 종류가 있는지는 보지만 같은 종류 두 개가 모두 남았는지는 잘 보지 못한다. 수정 정확도 도구 중 하나는 현재 primary가 아니라 레거시 경로를 검사한다(측정 사각지대).

## 조사 상태와 범위

- 요청의 §8에 따라 **진단·오프라인 재현까지 완료하고 수정 승인 전에 정지**한다. 아래는 수정 완료 보고가 아니다.
- 실제 LLM 신규 호출 **0회**. 네트워크 연결을 차단한 고정 JSON 재생과 기존 트레이스 읽기만 수행했다. 실서버 재표본, 게이트, 데이터 갱신, 커밋, 배포는 하지 않았다.
- 저장소 소스·테스트·문서에 내가 만든 변경은 없다. 진단 스크립트와 결과는 `/tmp`에 있다. 첫 스텁 실행에서 기존 추적기가 로컬 트레이스 `46277cea7b90`을 자동 기록했다. 실제 LLM 호출이 없으며 이후 재생은 추적을 껐다.
- 조사 시작 시 사용자 고지보다 넓은 미커밋 변경이 있었다. 조사 종료 시 HEAD는 `b73a6576`(2026-10-10 16:47:41 KST), `git status --short`는 비어 있다. 해당 커밋은 내가 만들지 않았다. 볼린저 v16.39·미국 ETF 수정은 기존 공유 작업이다.
- 아래 파일 경로는 저장소 루트 기준이다. `SC`는 `backend/strategy_conversation`, `I`는 `SC/interpreter`, `V`는 `SC/validation`, `C`는 `SC/compiler`의 약자다. 라인은 조사 시점 기준이다.
- 표의 **로그**는 사용자 `notices`가 아니며, 로그만으로 사용자에게 설명된 것으로 세지 않았다. **미확인**인 도입 날짜는 추측하지 않았다. 표는 현재 호출 경로에서 확인한 조건·전략 필드 변경 지점을 묶어 기록한다. 투자 엔진 전체의 모든 값 대입을 감사한 것은 아니다.

## 1. 현재 구조

```text
사용자 입력
  → 프론트 conversationDecision 사전 분기(일부 원문 판정)
  → main.py 생성/수정 분기
      수정: chip 바인딩 → full_rewrite_clarification → primary modification
            → 일부 coach risk 후처리 → 결과 조립
      생성: primary parse → 결과 조립

primary parse
  → 설정에 따라 Parse Evidence/Planner 선행·병렬 실행
  → LLM interpreter
      JSON 추출 → StrategyIntent 검증(이 단계에도 삭제·이동 validator 존재)
      → 형식 판별 → 공유 예산 내 재생성 → 숫자 대조/기간 제거
  → quote/trading/contribution batch 및 별도 liquidity 판정
  → contribution 적용 → 지표·기간·위험 필드 정규화
      → size-class 정규화 → relative-return dedupe
      → recall/누락 필드 회수 → fabricated condition 제거
  → validation pipeline
  → compile_strategy 또는 compile_partial
  → Planner 결과/유니버스 병합·질문 결정
  → main._build_parse_result(추가 최소값/단일자산/변환/overrides 처리)
  → 프론트 parsed/request 병합 및 일부 원문 기반 재심

primary modification
  → 기존 parsed 기본값 구체화 → decompile → compile 왕복 확인
  → [fast_path_first 설정일 때만] legacy rule-based fast path
    또는 pending-question 전용 판정/LLM patches
  → patch provenance 검증 → apply_patches → StrategySpec 재검증
  → 새 조건의 보조 판정 → 전체 patched spec 후처리 → validation
  → compile + 왕복 불가 필드 carry → 질문 재계산 → 프론트 병합
```

### 단계별 입출력·손실·실패 단위

| 단계 | 입력 → 출력 | 조건/값 변경·기본값 | 알림과 실패 단위 |
|---|---|---|---|
| API/프론트 사전 분기 | 원문+기존 초안 → 라우트/질문 | 원문으로 수정 유형 선판정 | 해석 레인 진입 자체를 막을 수 있음 |
| Evidence/Planner | 원문 → 근거/계획 | LLM 추출·계획, 설정별 선택 | 직렬 필수 단계가 아님; Planner 실패와 interpreter 실패를 구분해야 함 |
| Interpreter/repair | LLM JSON → StrategyIntent | schema validator가 삭제·이동; 재생성본 전체 교체 | 질문·미지원 목록 일부 salvage, 정상 조건 보존 보장 없음 |
| 보조 판정 | 원문/LLM 인용/조건 → 판정 | 역할·factor·비율·납입 구조 변경 가능 | 실패 시 판정 없음이 기본; 실제 제거는 후속 소비자에서 발생 |
| primary 후처리 | spec+판정 → spec | 이동·값 보충·조건 삭제, 레지스트리 개념 기본값 | 함수마다 notice/log/무알림이 다름 |
| validation | intent → 정규화 intent+report | 조건/랭킹/전략 필드 제거·기본값/별칭 변환 | 일부 errors/unsupported/questions, 일부 로그만; missing은 보류 가능 |
| patch 적용 | draft+patches → 새 spec | 경로 적용, 없는 조건 승격, 전체 schema 재실행 | 일반 오류는 PatchError; 혼합 승격에는 조용한 누락 재현 |
| compiler | spec+report → ParsedStrategy | 랭킹 병합, 엔진 기본값, 조건 변환 | 일부 조건별 StrategyCompileError 처리; Pydantic ValidationError는 전체 반환 중단 |
| API 결과 조립 | parsed → API 결과/request | 최소값·단일자산 조정·위험 override | 조건별 안내도 있으나 모든 변경이 개별 notice를 갖지는 않음 |
| 프론트 병합 | API parsed/request+이전값 → 화면/실행 상태 | risk override, 누락 시 이전값 사용, 원문 기반 필터 제거 | 이 원문 재심 제거에는 별도 사용자 안내 없음 |

### 수정 경로의 실제 분기

- 기본 코드 설정은 primary interpreter, `modify_strategy=llm_first`다. 현재 실행 중 환경변수 전체를 읽어 확인한 것은 아니므로, 코드 기본값을 실제 모든 요청의 설정으로 단정하지 않는다.
- `primary.fast_path_can_handle` 및 `_modify_rule_based`는 `fast_path_first` 롤백 설정에서 사용한다(`primary.py:1830,4819`). 기본 LLM-first에서 primary가 `None`이면 `main.py`는 기존 초안을 보존하는 해석 실패 응답으로 간다. 무조건 레거시 폴백한다는 설명은 현재 코드와 다르다.
- primary 비활성/레거시 설정에서는 `NLStrategyParser.parse_modification` 경로가 살아 있다.
- LLM-first라도 `full_rewrite_clarification`과 결과 이후 `resolve_coach_context_risk`가 원문을 판정하므로, 레거시 의미 판정이 모두 격리된 상태는 아니다(`main.py:4040,4099`).
- `change_log`는 변경 필드 기록, `impact`는 파생 상태 영향 계산이다. 여기서 독립 조건을 factor별로 합치는 경로는 확인하지 못했다. rollback은 별도 이벤트/스냅샷 복원 흐름이며 apply_patches와 같은 단계가 아니다.

### 문서와 코드의 차이

1. 숫자 대조 계약은 값을 고치지 않고 LLM에 오류를 반환한다고 설명하지만, 현재 interpreter는 근거 없는 기간을 지운다(`llm_strategy_interpreter.py:486–500`).
2. 계약 §7은 없는 대상 replace를 거부하는데, patch applier는 없는 인덱스 필드들을 add로 승격한다. 잘못된 패치 시 재생성 설명도 실제 `PatchError → None` 경로와 다르다.
3. 계약의 AND-only 설명과 달리 `StrategySpec.entry_logic`와 프롬프트는 OR를 지원한다.
4. 아키텍처의 9B shadow 단계 설명을 현재 운영 모델로 읽으면 안 된다. 실제 조사한 정상 트레이스는 120B이며, 별도 실패 트레이스에는 120B 429와 Planner 9B가 함께 있다.
5. Parse Evidence → interpreter → compiler → Planner의 단순 직렬 지도는 실제 선행/병렬/재계획 분기를 빠뜨린다.

## 2. 조건·필드가 사라지거나 바뀌는 지점 목록

### 추출·스키마·보조 판정

| 지점(파일:함수) | 제거/교체 대상 | 발동 조건 | 판정 입력 | 사용자 알림 | 도입 사고·날짜 |
|---|---|---|---|---|---|
| I/output_repair.py:extract_json_object | 응답 바깥 텍스트/코드펜스 | JSON 경계 추출 | LLM 출력 | 없음; 형식 추출 | 이력 미확인 |
| I/output_repair.py:salvage_* 및 interpreter repair loop | 질문/미지원만 회수; 나머지는 새 출력으로 교체 | 형식/스키마 재생성 | LLM 출력 | 질문·미지원은 노출; 정상 조건 누락 전용 안내 없음 | 유형 R; 현 함수별 날짜 미확인 |
| I/output_repair.py:whole_input_quote_fields | 전체 출력 재생성 | 다른 칸도 채웠는데 조건이 원문 전체 인용 | LLM 출력+**원문 대조** | 재시도 로그; 손실 차이 안내 없음 | 전체 인용 사고; 미확인 |
| I/output_repair.py:misfiled_trading_value_fields | 전체 출력 재생성 | 거래대금 factor와 인용 속 등록 지표 이름 불일치 | LLM 인용+registry | 재시도 로그 | 미확인 |
| I/output_repair.py:split_bollinger_recovery_fields | 전체 출력 재생성 | AND에서 하단 터치+중심선 회복으로 분리 | LLM 구조/factor | 재시도 로그 | 기존 공유 v16.39 작업, 10-10 |
| I/output_repair.py:is_bare_unsupported_request | 전체 출력 재생성 | 미지원 표기의 빈 구조 | LLM 출력 | 재시도 로그 | 미확인 |
| I/llm_strategy_interpreter.py:drop_ungrounded_condition_periods 호출 | 기간 parameter를 비움 | 원문 숫자 근거 미대조 | LLM 출력+**원문 숫자** | 대조/로그; 조건별 사용자 설명 보장 없음 | 08-07 이후 현재 방식; 계약 불일치 |
| I/models.py:StrategySpec._drop_factorless_conditions | factor 없는 조건 제거 | 조건 dict에 factor 없음 | LLM 구조 | **없음** | 미확인 |
| I/models.py:StrategySpec._drop_mirrored_valueless_exits | 값 없는 exit 제거 | entry 같은 factor·방향; 일부 예외 | LLM 출력, 인용 일부 | **없음** | 07-21 도입, 07-26/08-05/09-30 예외 누적 |
| I/models.py:StrategySpec._absorb_scalar_slot_conditions | 조건 제거, risk/portfolio/backtest로 이동 | scalar slot에 해당하는 factor/parameter | LLM 출력 | **없음**; 기존 scalar가 있으면 조건 값은 소실 | 미확인 |
| I/models.py:RiskSpec._normalize_partial_stages | 분할익절 삭제/전량익절 이동 | 매도비율≤0 또는 ≥100 | LLM 수치 | **없음** | 미확인 |
| I/models.py:_relocate_scale_in_buys | 위험 칸 매수 사다리 이동/중복 정리 | 구형 scale-in 형식 | LLM 구조 | **없음** | 미확인 |
| I/models.py:seasonality/macro/declined 정규화 | 유효하지 않은 월/항목 제거 | 형식 부적합/인용 없음 | LLM 구조 | **없음** | 미확인 |
| I/quote_check.py:check_quotes → primary._drop_fabricated_conditions | 조건 삭제에 쓰일 verdict | 인용이 조건 뜻이 아니라는 LLM 판정 | 원문·인용을 **LLM이** 판정 | 소비 분기마다 다름, 아래 참조 | 유형 S, 09-19 120B false-drop; 현재 확인 호출/MA 제한 있음 |
| I/trading_value_check.py:apply_* | factor/unit/value/period/operator 교체 | LLM 비율 판정 | 보조 LLM 출력 | 로그 위주; op 없으면 `>` | 미확인 |
| I/contribution_plan_check.py:apply_* | 납입 칸 비우기/회수, 같은 인용 거래대금 제거, 매수금액 규칙 교체 | allocation/contribution/cash-pool 판정 | 보조 LLM 출력+인용 키 | 로그 위주 | 미확인 |
| I/liquidity_exclusion_check.py:apply_* | 미지원 항목 제거, 값 없는 거래대금 조건 추가 | 유동성 제외 판정 | 보조 LLM 출력 | 후속 되묻기 | 미확인 |

**재생성 예산:** whole-input → bare-unsupported → trading-value → Bollinger 판별은 같은 `MAX_REPAIR_ATTEMPTS`를 쓴다. 기본 1회이므로 앞선 판별이 기회를 쓰면 다른 형식 문제는 다시 고칠 수 없다. invalid schema fallback은 있어도, 정상 schema이면서 조건 하나 빠진 결과는 fallback되지 않는다.

### primary 후처리

| 지점(파일:함수) | 제거/교체 대상 | 발동 조건 | 판정 입력 | 사용자 알림 | 도입 사고·날짜 |
|---|---|---|---|---|---|
| primary.py:_normalize_size_class_labels:1232 | size label→시총 질문, 관련 sector/unsupported 정리 | LLM label이 정해진 분류와 일치 | LLM label/registry | 질문+로그 | 미확인 |
| primary.py:_dedupe_relative_return_against_ranking:1278 | null/0 상대수익 조건 제거 | return 계열 rank와 기간 일치 또는 한쪽 없음 | LLM 출력 | 짧은 인용만 notice; 나머지는 **로그만** | 미확인 |
| primary.py:_fill_deterministic_condition_params:1352 | 근사 MA 제거 | 미지원 인용과 겹침 | LLM 출력/인용 | 미지원 목록은 남음, 개별 제거 안내 없음 | 미확인 |
| 같은 함수: entry→exit 이동 | 조건 역할 교체 | sell 판정+entry 인용에 buy cue 없음 | LLM 판정+**인용 어휘 재심** | 로그 위주 | 미확인 |
| 같은 함수: _quotes_ema | SMA 개념→EMA 및 개념 parameter | EMA 인용 어휘 | **LLM 인용의 의미 판정** | 개별 notice 없음 | 계약 §11 기존 부채 |
| 같은 함수: _explicit_ma_periods/_explicit_breakout_lookback | 기간 덮어쓰기/비우기, breakout factor 변경 | 인용에서 기간·표현 검출, 보조 판정 | LLM 인용/판정 | 로그 위주 | 계약 §11 기존 부채 |
| 같은 함수: 금액 단위 정규화 | value/unit 교체 | 인용에 단일 금액 토큰 | 인용의 수치·단위 | 개별 notice 없음 | 순수 단위 변환과 의미 판정은 구분 필요 |
| 같은 함수: _SL_QUOTE_RE/_TP_QUOTE_RE | 일반 조건→risk, 원래 조건 제거 | 인용 선두 위험 표현 | **LLM 인용의 의미 판정** | **없음**; 기존 risk 있으면 충돌 값 소실 가능 | 미확인 |
| primary.py:_hold_days_from_unsupported_feature:1582 | unsupported→보유기간, unsupported 제거 | 보유 표현과 최소 조건 제외 | **LLM 인용의 의미 판정** | 개별 제거 안내 없음 | 미확인 |
| primary.py:_drop_fabricated_conditions:1641 ranking mirror | 선정 조건 제거 | rank와 겹친다고 판단 | LLM 구조/인용 | 로그; approximation만 carry, lookback은 여기서 미회수 | 미확인 |
| 같은 함수: 전체 입력 인용 | 조건 제거 | 다른 칸 추출+whole quote | **원문과 인용의 대조** | **트레이스/로그만** | 미확인 |
| 같은 함수: 인용 근거 없음 | 조건 제거 | literal/부분 echo 불일치 | **원문과 인용의 대조** | 일반 notice; 예시 누출 분기는 **로그만** | 예시 코퍼스 누출 08-14 관련 |
| 같은 함수: quote verdict false | 조건 제거 | 인용 대조 실패/랭킹 대체/다른 조건 대체 | LLM 판정+원문 literal/조건 | 일부 notice, literal 없음/대체 표현은 **없음 또는 로그만** | 유형 S |
| primary.py:modify provenance gate:5060 | patch 거부/턴 전체 보류 | 근거 대조 실패/자기 의심 판정 | LLM 출력+**원문 대조** | 거부 notice/질문 | 계약상 provenance 예외, 의미 재해석과 구분 |
| primary.py:수정 후 normalization | 언급 안 한 기존 조건도 변경 가능 | apply 후 전체 spec에 fill/validation | 기존+신규 LLM 구조 | 함수별 상이 | 수정 전 왕복 가드만으로 수정 후 보존 불충분 |

### 도메인 검증

| 지점(파일:함수) | 제거/교체 대상 | 발동 조건 | 판정 입력 | 사용자 알림 | 도입 사고·날짜 |
|---|---|---|---|---|---|
| V/pipeline.py:_strip_data_pending | condition/rank 제거 | 데이터 준비중 factor | registry+LLM 출력 | preparing_features | 미확인 |
| V/pipeline.py:질문 정리 | LLM 질문 제거/최대3개 | missing과 무관/중복/READY | 검증 결과 | 필요한 질문만 유지, 나머지 개별 안내 없음 | 미확인 |
| V/capability_validator.py:_dedupe_identical_conditions:72 | 두 번째 조건 제거 | factor/op/value/unit/params 일치 | LLM 구조 | **로그만**; buy_amount/mode가 key에 없음 | 08-18, 09-23 key 보완 |
| 같은 파일:_drop_valueless_quote_twins:100 | null-value 조건 제거 | 같은 factor·겹친 인용의 valued 조건 존재 | LLM 구조/인용 | **로그만**, op/params 불구별 | 10-07 사고 #46 |
| 같은 파일:concept/canonical 정규화 | factor/operator/default params 덮어쓰기 | 레지스트리 개념/별칭 | registry+LLM 출력 | 일부 버린 parameter warning, 기본값 전용 notice 없음 | 여러 사고 누적 |
| 같은 파일:timeframe/oscillator 정규화 | timeframe 제거, crosses→부등호 | 지원 주기/역할 제약 | LLM 구조 | invalid 주기 unsupported, 정규 변환은 없음 | 미확인 |
| 같은 파일:거래대금/volume 변환 | factor/operator 교체 | 기간/배수 구조 | LLM 출력 | 대체로 정규화 로그 | 미확인 |
| 같은 파일:ranking-bound 조건 | 조건 제거, rank/percentile로 이동 | 정렬형 factor | LLM 구조 | **기존 ranking 있으면 새 rank를 넣지 않고 조건 제거 가능** | 미확인 |
| 같은 파일:mirrored fundamental exit | 값/인용 없는 exit 제거 | entry와 대응 | LLM 구조 | **없음/로그** | 미확인 |
| 같은 파일:ranking_mirrored_by:151 | entry 제거, 일부 lookback carry | 같은 metric/direction, 이름 계열 일치 | LLM 구조/인용 | **로그만**; 첫 metric 선택, 다른 lookback 검증 없음 | 기존 랭킹 중복 제거 사고 |
| 같은 파일:rank unsupported/unrankable 정리 | rank 제거 | 미지원 인용/지원 불가 metric | LLM 출력+registry | errors/unsupported, 일부 중복 정리 로그 | 미확인 |
| 같은 파일:ETF/US capability | rank/조건/IPO/국내 symbol/sector 삭제 | 자산군·시장 지원 범위 | 구조+catalog | 주로 errors/warnings/unsupported | US ETF 정규화는 기존 10-10 공유 변경 |
| 같은 파일:ETF sector→theme | 모든 sector 제거, 첫 sector theme | ETF 분류 | 구조 | 개별 추가 sector 소실 안내 불명확 | 미확인 |
| 같은 파일:weighting/TAA | 잘못된 method/lookback 삭제, fixed 전환 | 지원 방법/target_weights 존재 | 구조+registry | 일부 errors/unsupported | 미확인 |
| 같은 파일:current_close 제한 | limit/tranche 필드 제거 | 체결모드 충돌 | 구조 | errors | 미확인 |
| 같은 파일:entry_tranches:955 부근 | **사다리 전체 제거** | 한 단계라도 불완전/잘못된 값 | 구조 | errors | 미확인 |
| 같은 파일:slippage/rank skip/복합rank | 모델/계수/skip/rank 제거 | 지원 조합 위반 | 구조 | errors/unsupported | 미확인 |
| 같은 파일:market filter | 필터 전체 제거/노출값 비우기 | US 또는 exposure≥100 | 구조 | errors/질문 | 미확인 |
| 같은 파일:macro/seasonality | 시리즈/노출/모드/전체 조건 정리 | 미등록/잘못된 비교/0 또는12개월 등 | 구조+registry | unsupported/질문, 일부 mode 정규화는 없음 | 미확인 |
| 같은 파일:volatility/rebalance/frequency/benchmark | 잘못된 필드 비움 | 지원 범위 위반 | 구조 | errors/질문 | 미확인 |
| 같은 파일:contribution/withdrawal | 조건 규칙·금액 삭제, 납입 쌍 전체 비움 | 중복/일반조건 혼합/고아 cashpool | 구조 | 중복은 무알림, 그 외 errors/unsupported | 미확인 |

검증기는 일괄적으로 조건 목록 전체를 지우는 구조는 아니다. 상당수는 해당 조건/칸만 제거하고 report를 남긴다. 그러나 사다리·납입쌍 등 묶음 제거와 무알림 dedupe가 섞여 있으며, `errors` 문자열만으로 어느 정상 조건을 보존해야 하는지 compiler가 일관되게 알 수 없다.

### 패치·조립·프론트

| 지점(파일:함수) | 제거/교체 대상 | 발동 조건 | 판정 입력 | 사용자 알림 | 도입 사고·날짜 |
|---|---|---|---|---|---|
| SC/conversation/patch_applier.py:_resolve_parent | 다른 배열 항목 접근 | 중간 token `-1` 등 음수 | LLM patch path | **없음**, Python 음수 인덱스로 처리 | 현재 재현, 도입 미확인 |
| 같은 파일:_promote_patches_on_absent_condition | 없는 인덱스 replace→add; 불완전 그룹 소실 | 유효 승격 그룹과 factor 없는 그룹 혼합 | LLM patches | **없음**; 모든 그룹을 absorbed 처리 | 08-01, 07-31 9B 드리프트 대응 |
| 같은 파일:apply_patches | index remove/replace, `replace /-` append, dict remove→null | patch op/path | LLM patches | 정상 patch 변경 기록; 오류 PatchError | append 허용 07-17 드리프트 대응 |
| 같은 파일:_drop_stale_parameters | 새 factor에 없는 parameter 제거 | factor 변경 | patch+registry | 개별 notice 없음 | 지식 조회 예외에 해당 |
| 같은 파일:StrategySpec.model_validate | 앞의 모델 validator 재실행 | 모든 patch 적용 후 | 전체 draft | 모델별 silent drop 반복 가능 | 위 모델 행과 같음 |
| C/strategy_compiler.py:_compile_technical:77 | parameter 기본값/엔진 형태 변환 | registry 기본값/기술조건 | LLM spec+registry | dropped/pending 또는 기본값 무알림 | 지표별 확인 필요 |
| 같은 파일:_build_parsed:510 | 동일 metric rank 두 번째 제거 | metric/direction/skip/group 동일 | LLM ranking | **없음**; lookback/weight가 key에 없음 | 08-17 도입, 09-20 key 변경 |
| 같은 파일:_build_parsed | 미등록 rank 건너뜀, symbol weight alias 충돌, 첫 sector | 변환/중복 canonical key | spec+registry/catalog | 일부 **로그만/없음** | 미확인 |
| 같은 파일:_build_parsed | 종목수/기간/원금/비중/체결/비용 기본값 | 해당 칸 없음 | spec/정책 기본값 | 일부 명시여부 flag, 모두 확정값이라는 뜻은 아님 | 기존 정책 |
| 같은 파일:compile_strategy/compile_partial | 정상 조건 포함 요청 결과 반환 중단 | nested Pydantic ValidationError | typed spec→엔진 schema | 상위 실패 처리; 조건 단위 회복 없음 | 유형 C, 현재 재현 |
| C/strategy_decompiler.py + primary 왕복 가드 | 비왕복 필드 carry, 불일치 시 수정 종료 | compile/decompile 차이 | 기존 ParsedStrategy | 수정 실패/되묻기 경로 | 가드는 이미 소실된 정보 복구 못 함 |
| backend/main.py:_build_parse_result:3490 이후 | 최소값·단일자산/변환 조정 | parsed 구조 | parsed; legacy 일부 원문 | 일부 dropped 안내, 전체 정규화 단일 기준 아님 | 기존 경로 |
| backend/main.py → nl_parser.resolve_coach_context_risk:5965 | backend parsed risk 덮어쓰기 | 원문 금액/퍼센트/위험 표현+이전 coach | **원문 의미 판정** | 전용 재심 안내 없음 | 레거시 부채 |
| app/analytics/new/parsedStrategyMerge.ts:mergeParsedSummary:324 | risk 3칸 덮어쓰기 | risk_overrides 존재 | backend override | 변경값 표시, 별도 설명 없음 | 현재 override 생성은 parsed diff |
| 같은 파일:mergeBacktestRequest | override 모든 키/이전값 fallback | backend override/다음값 없음 | backend/이전 상태 | 별도 설명 없음 | 미확인 |
| 같은 파일:shouldRemoveHallucinatedProfitGrowth:341 | net_income_growth 필터 전부 제거 | 원문 흑자/성장표현 판정+eps>0 | **원문 의미 재심** | **없음** | 07-24, 0f79e0117; 유형 F |
| SC/output_guard.py:응답 가드 | 응답 문장/질문 표시 제거 가능 | 출력 문구 규칙 | 생성된 응답 텍스트 | 자체 안내 없음 | 조건 데이터 삭제와 별도 관측 문제 |

**기각한 과장:** `remove /entry_conditions`는 이번 재현에서 PatchError였다. 정상 index add/remove/replace가 일반적으로 무관 필드를 깨뜨리는 것은 아니었다. quote verdict key도 factor 하나가 아니라 조건 객체 identity이며, check_batch는 ID와 개수를 검증한다. `risk_overrides` 생성 자체는 현재 parsed 차이 기반이다. 이 부분을 원문 재심이라고 보고하지 않는다.

## 3. 구조적 원인: 가설 판정

| 가설 | 판정 | 코드·이력·재현 근거 |
|---|---|---|
| 1 특례 누적 | **확인** | 같은 목적의 mirror/dedupe가 모델·primary·validator·compiler에 각각 존재. 기간/방향/인용/금액을 보는 범위가 다르다. MA exit mirror에 방향/부등호/Bollinger 예외가 순차 추가됨. 없는 patch 승격이 다른 불완전 그룹을 삼킴. 단, 각 과거 커밋이 다른 실제 사용자 요청을 깨뜨렸다는 인과 전체를 새 실험으로 입증한 것은 아님 |
| 2 프롬프트 분량/예시/shape | **현재 모순+역사적 실측 확인, 최신 모델 인과 미측정** | 979줄, 렌더 약66,153자. `prompts.py:303–304` 최소보유 미지원 vs `:526` min_hold_period_days 기록이 직접 충돌. shape PER strict-below 인용에 `<=` 예시. 07-27 etf_theme shape 누락 6/7 손실, 08-26 17케이스 분량 실험, 09-03 거래대금 문구→다른 지표 누출 이력. 최신 v8.9의 9B 빈 전략 빈도는 재측정하지 않음 |
| 3 조건 identity 충돌 | **결정론 재현으로 확인** | 모델: 기간 다른 entry 추가시 exit1→0. validator: 금액 다른 동일 RSI 규칙2→1. compiler: return20/60일 중 첫 항목만 남아 순서에 따라 결과 달라짐. quote_check 객체 key와 일반 decompiler factor dictionary 충돌 가설은 확인되지 않음 |
| 4 재생성 경계 | **구조·합성 재생으로 확인, 조사한 실제 6건의 무관 조건 손실은 미확인** | 질문/미지원 salvage만 있고 조건 대조 없음. 스텁 2조건→1조건 정상 schema가 수용됨. 실제 BB6건은 두 entry 의미를 하나로 합치고 exit 보존; 개수 감소 자체를 결함으로 세지 않음 |
| 5 실패 단위 큼 | **결정론 재현으로 확인** | risk partial profit=-5, kelly_fraction=2는 domain errors[] 후 compile_partial에서 ValidationError. 개별 StrategyCompileError만 잡으므로 정상 PER/PBR까지 결과 반환 중단 |
| 6 측정 사각지대 | **확인** | evaluator factor set/last-wins dict, current primary patch 미실행; qa_modify_accuracy는 legacy parser; UI sweep은 캐시 표시 검사. 여러 기존 테스트가 있지만 같은-factor 기간/금액·배열순서·혼합 patch 승격을 통합 보장하지 못함 |

### 특례의 영향 범위

- whole-input 판별은 특정 지표에 한정되지 않는다. 조건 외 칸이 채워지는 순간 같은 인용이 삭제/재생성 대상이 된다. **독립 칸 추가가 기존 조건의 운명을 바꿀 수 있다.**
- mirrored exit는 여러 기술 지표에 적용하며 Bollinger만 별도 인용 예외가 있다. 기간이 다른 MA에도 적용된다.
- trading-value/Bollinger repair는 발동 factor는 좁지만 교체 단위가 전체 intent라 영향 범위는 넓다.
- MA 기간 보정·EMA/위험/보유기간 어휘 판별은 LLM이 선택한 역할/값을 다시 바꾼다. 동의어를 더 넣는 방식은 해결책으로 제시하지 않는다.
- ranking dedupe는 선정 조건뿐 아니라 compiler 복합랭킹에도 따로 있다. 앞 단계에서 살아남았어도 뒤 단계의 다른 key 때문에 소실된다.
- absent-condition patch 승격은 9B 형식 드리프트 대응이지만 모든 조건 배열 그룹에 적용된다. 한 정상 그룹의 존재가 다른 잘못된 그룹의 실패 처리를 바꾼다.

### 프롬프트 이력의 해석 한계

메모리의 과거 숫자는 이번 측정 결과가 아니다. 08-26 기록은 17개 momentum 케이스에서 기존 치명2/빈0, 6줄+shape 변경 치명5/빈5, 1줄+shape 치명1/빈0을 보고한다. 09-19 quote-check 기록은 120B false drop 개선과 9B 제거 성능 감소를 함께 기록한다. 이는 분량·모델별 영향이 있다는 근거이며, 오늘 v8.9를 120B/9B로 재표본한 증거는 아니다.

## 4. 대원칙 1 위반 및 계약 예외 구분

**의미 재심 위반과 이관 부채 — 10-13 현재 상태:**

1. 레거시 `engine/nl_parser.py`의 `_modify_rule_based`는 원문을 규칙으로 해석한다. Primary의 `fast_path_can_handle` 선제 호출과 실패 폴백은 후속 실행 16에서 제거했으나 함수 정의와 다른 레거시 경로는 별도 부채다.
2. `resolve_coach_context_risk`의 원문 위험값 재판정 호출은 후속 실행 16에서 Primary 뒤 경로에서 제거했다. 함수 정의 자체는 남아 있으므로 재연결하면 같은 위반이 된다. `full_rewrite_clarification`의 Primary 앞 호출도 후속 실행 4에서 제거했다.
3. 프론트 `conversationDecision` 일부 요청 분기는 여전히 원문으로 라우팅을 선판정한다. `parsedStrategyMerge.shouldRemoveHallucinatedProfitGrowth`의 원문 기반 조건 제거는 후속 작업에서 제거했다.
4. primary의 EMA/매수 cue/손절·익절/보유기간 등 **인용 문장 의미 재해석**. 인용이 LLM 산출물이라는 이유만으로 지식 조회 예외가 되지 않음. 기존 계약 이력도 인용 의미 정규식 부채를 별도로 남김.
5. `scripts/qa_template_detect.py`의 예시 원문 정규식 기대값 생성은 후속 실행 16에서 사람 작성 기대값 파일로 교체했다. 현재 게이트의 정답 생성 경로에는 남아 있지 않다.

**원문을 읽지만 곧바로 의미 해석 위반으로 단정하지 않을 것:**

- literal quote 포함/echo 대조와 patch provenance는 계약 §3-1에 허용된 대조다. 원문 접근 사실과 silent-drop 위험은 표에 모두 적되, 의미 판정과 구분했다.
- 숫자 대조 자체도 예외다. 다만 대조 결과로 기간을 지우는 현재 동작은 계약의 “오류 반환/재생성, 임의 보정 금지”와 다르다.
- LLM이 뽑은 짧은 지표명·symbol을 registry/catalog에서 찾는 것은 §3-2 예외다. 사용자 문장에서 지표 의미를 새로 결정하는 어휘 매칭은 예외가 아니다.

**남은 이관 방향:** 의미 판정은 기존 메인 interpreter 또는 기존 전용 LLM check 계열로 옮겨야 한다. 이 문서의 후속 실행은 일부 원문 재심 호출을 제거했지만 레거시·코치 위험·일부 프론트 분기는 남겼다. 어휘 확장, 새 agent/parser/state/DSL은 도입하지 않았다.

## 5. 재현 및 Before / After

여기서 Before/After는 **수정 전후가 아니라 입력 조합·처리 단계 전후**다. 제품 코드를 고치지 않았다.

| 사례 | Before | After | 증거/측정 모델 |
|---|---|---|---|
| 같은 factor 다른 기간 entry/exit | MA `>20/60` exit 단독1개 | MA `>5/20` entry 추가시 exit0개 | 고정 StrategySpec, 모델 검증 단계, LLM0 |
| 랭킹 순서 | return lookback `[20,60]` | 단일20일; 뒤집으면 단일60일 | compiler, LLM0 |
| 금액 다른 동일 지표 | RSI<30/14, 매수10만과20만 | 첫10만만 보존 | capability validator, LLM0 |
| 혼합 없는-index patch | 정상 entry factor/value 그룹+factor 없는 exit value 그룹 | entry만 성공, exit patch는 실패도 안내도 없이 사라짐 | apply_patches, LLM0 |
| 음수 중간 index | PER10/PBR1, `/entry_conditions/-1/value=15` | PBR15로 변경 | apply_patches, LLM0 |
| 형식 재생성 경계 | 정상 의미 PER/PBR 두 조건, whole-input 형식 문제 | 재생성 PER만 있어도 채택; unreflected에는 숫자1만 남음 | fake chat 2응답, LLM0; 합성 위험 재현 |
| 실패 단위 | 정상 PER/PBR+partial profit=-5 또는 Kelly2 | compile_partial ValidationError | LLM0; API 응답까지의 실서버 재현은 아님 |
| A 재무2개 | KOSPI PER≤10/PBR≤1/10종목/월간 | 두 조건 유지; primary notices[] | fake primary, LLM0 |
| B 재무3개 | ROE≥15/PER≤10/거래대금≥50억 | 3개 유지, ROE canonical id 정규화 | validate/compile, LLM0 |
| C 같은 계열 entry2개 | MA5/20 교차+MA20/60 정배열 | entry2개 유지 | validate/compile, LLM0; 모든 같은-family가 깨지는 것은 아님 |
| D entry+exit | RSI<30 매수/RSI>70 매도 | 각각 유지 | validate/compile, LLM0 |
| E 부분수정 | PER10/PBR1 등 기존 초안 | PER15만 변경, 무관 fields dump 동일 | apply 및 fake primary, LLM0 |
| F patch 연산 | 정상 add/index remove/value replace | 가산/삭제/교체, 무관필드 유지 | apply, LLM0; 표현을 LLM이 올바른 op로 내는지는 미측정 |
| F 전체배열 remove | `/entry_conditions` remove | PatchError | LLM0; 조용한 전체삭제 가설 기각 |
| G 값 없는 손절수정 | patches[]+CLARIFY+질문 | 기존 parsed 동일, 손절 질문, patch0 | fake primary, LLM0 |

### 기존 실측 트레이스와 원출력 재생

- `76344db91101`, 10-10 14:58:31: cache_hit=False, prompt8.8, 실제 기록 모델 **nvidia/nemotron-3-super-120b-a12b:free**, 기록상 총 LLM3호출. PBR1.3/PER10/ROE14 세 조건 보존. 이번에는 interpreter 원출력1개를 fake chat으로 재생했으며 신규 호출0회다.
- `885e95f128b1`: 같은 120B의 원출력2개를 재생. 볼린저 recovery는 필수 기간 부족으로 `pending_conditions`에 남고 exit upper_breakout은 조립된다. **보류/되묻기는 손실로 세지 않았다.**
- 10-08~10-10의 관련 repair 트레이스6건을 구조적으로 비교했다. 확인한 것은 볼린저 두 표현→단일 recovery 및 exit 보존이며, 무관 조건 소실의 실제 사례를 찾았다고 주장하지 않는다.
- `044fab988bfe`: interpreter 429/약320초 실패, 별도 Planner span은 Qwen3.5-9B. 이를 성공한120B 측정 또는 전체9B 정상 결과로 합산하지 않았다.
- fake primary 재생에서는 planner/recall 등 외부 호출 가능 경로를 비활성화하고 보조 동작을 스텁했다. 따라서 “실제 full primary 모든 판정 통과”가 아니라 해당 결정론 흐름 재현이다.

재현 파일:

- `/tmp/simons-offline-audit.py`
- `/tmp/simons-interpretation-audit-results.json`
- `/tmp/simons-trace-replay-results.json`
- `/tmp/simons-primary-replay-results.json`

## 6. 측정 자산과 누락

| 자산 | 보는 것 | 못 보는 것/이번 확인 |
|---|---|---|
| parse_cases.json 42개 | 표현 변형·정해진 필드 기대 | draft 포함5개, multiple_conditions 분류1개; 기대값 자체에 복수 identity 불변식 부족 |
| evaluation/evaluator.py | interpret→validation→READY compile | primary aux/patch_applier/프론트 미통과; draft 있다고 patch 적용 결과를 검사하지 않음 |
| evaluation/metrics.py | factor 존재·threshold | entry/exit factor set 합침, threshold factor dict last-wins; 개수/역할/동일factor 복수값 손실 탐지 약함. compile_error가 failure 판정에 일관되게 포함되지 않음 |
| qa_modify_accuracy.py | legacy 수정 정확도/overreach | main이 NLStrategyParser.parse_modification 호출; 현재 primary patches 품질의 대리검증 불가 |
| qa_multiturn_binding.py | 실서버 연속 질문/답 바인딩 | 선택된 시나리오, 전체 조건 조합 불변식 아님 |
| 81개 template gate | 예시 전략 주요 기대 지표/일부 필드 | 모든 수치·역할·중복 조건의 보존 보장은 아님 |
| display sweep | 캐시 결과의 프론트 표시 | 새 백엔드 의미 정확도나 아직 갱신 안 된 응답은 검증하지 않음; 자체 LLM0 |
| 기존 unit tests | 여러 patch/quote/repair/왕복 개별 회귀 | 이번 기간다른 exit·금액다른 동일조건·순서·혼합승격 조합의 빈틈 재현 |

10-07 기준선 메모리는 81개 전체에서 치명2건(#18/#23)을 기록하고, 후속 수정 후 전수는 한도 때문에 미실행이라고 적는다. 이를 “전체 녹색 기준선”으로 사용하면 안 된다.

## 7. 수정 제안과 승인 범위

**가장 작은 첫 수정은 compiler의 랭킹 중복 key에서 서로 다른 lookback을 보존하는 것이다.** 이미 LLM JSON이 맞고, 원문/프롬프트/되묻기 정책을 건드릴 필요가 없다. 재현 테스트를 먼저 고정하고 첫 범위가 끝나면 멈춘다. 나머지 확인된 버그는 별도 변경으로 나누는 편이 회귀 원인 추적에 유리하다.

승인받을 실행 명세:

- **Task:** 같은 return metric의 서로 다른 lookback 랭킹이 조립 단계에서 소실되지 않도록 안정화.
- **Boundary:** 현 `boundaries.md`에 compiler/patch_applier 안정화를 정확히 포괄하는 단일 경계가 없다. 기존 Boundary B(Backtest Transform)에 **이번 compiler 파일의 좁은 예외와 관련 문서 갱신**을 명시적으로 승인받거나, 먼저 Governance 변경으로 경계를 정리해야 한다. 여러 경계를 임의로 함께 쓰지 않는다.
- **Files allowed:** `backend/strategy_conversation/compiler/strategy_compiler.py`, `backend/tests/test_strategy_conversation.py`; 완료 기록용 `docs/PROJECT_PLAN.md`, `docs/SRS.md`, `docs/software_architecture.md`는 위 경계 예외 승인에 포함할지 확정 필요. 총5파일.
- **Do not:** prompts/models/primary/validator/patch_applier/원문규칙/데이터/실서버 설정 변경, 새 agent/parser/state/DSL, 커밋·배포 금지.
- **Requirements:** 동일 metric·다른 lookback이 모두 보존; 순서만 바꾸면 의미상 같은 복합랭킹; 무관 랭킹 필드 보존; 기존 완전 중복 처리 유지. weight 등 다른 key 누락은 추가 분석하되 정책 변화가 필요하면 별도 승인.
- **Run:** 먼저 회귀 테스트 실패 확인→최소 수정→해당 테스트→사용자 지정 backend 전체 명령 및 frontend 전체. 실LLM 게이트는 대상 카테고리/호출상한을 계산해 별도 승인받은 뒤 시행. category당 실제 check/retry 수에 따라 달라지므로 현 단계에서 근거 없는 고정 건수를 약속하지 않음. 전수 KR게이트는 사용자 기준 약430호출; display sweep 자체0호출.
- **Deliver:** 내 diff와 기존 작업 구분, 테스트/모델/호출수/미실행 게이트, 문서 기록. 아직 이 명세의 실행 승인을 받지 않음.

다음 후보는 별도 승인 단위다: 모델 mirrored-exit의 parameter identity, buy_amount dedupe identity, patch 혼합승격 소실/음수 경로, compiler 실패 단위, 재생성 보존. 원문 규칙 이전과 프롬프트 최소보유 모순 정리는 추가 승인 사항이다. 조건을 무조건 합쳐 복구하면 정당한 Bollinger 교체를 되살릴 수 있으므로 **재생성 전후 배열 단순 union은 제안하지 않는다.**

## 8. 수정 파일·테스트·게이트 상태

| 항목 | 상태 |
|---|---|
| 저장소 변경/회귀 테스트 추가 | **없음** — 진단 후 승인 checkpoint |
| 트레이스 읽기 | 실행, 위 모델/ID 기록 |
| 고정 JSON 오프라인 재생 | 실행, 신규 LLM0, 실패 사례와 정상 대조군 기록 |
| backend 전체 unit | **미실행** — 아직 수정 전 진단 단계 |
| `npm run test:frontend` | **미실행** — 아직 수정 전 진단 단계 |
| 실제 3~5회 재표본 | **미실행** — 비용 승인 없음 |
| qa_free_input modify/fill | **미실행** — 프롬프트/레인 변경 없음, 비용 승인 없음 |
| category/template gate | **미실행** — 수정 범위·비용 승인 전 |
| 81개 전수/10-07 diff | **미실행** — 비용 승인 전; baseline 자체도 위 한계 있음 |
| display sweep | **미실행** — 현재는 진단, 변경 결과 캐시 없음 |
| /us 영어 하니스3종 | **미실행** — 범위·비용 승인 전 |
| AgentsTab/CLAUDE/프로젝트 문서 갱신 | **미실행** — 구현 및 단일 경계 승인 후 필요한 기록. 새 원문 재심 구체 지점은 CLAUDE 격차표에 반영 필요 |

## 9. 남은 위험과 승인 대기

- 확인한 결정론 실패의 실제 사용자 발생 빈도는 아직 모른다. synthetic 조건은 계약 구조로 만들었으며 운영 LLM이 그 JSON을 내는 확률을 측정하지 않았다.
- 120B/9B의 분량·quote-check tradeoff는 역사적 근거가 있으나 현재 v8.9에서 다시 재지 않았다.
- 전체 primary 보조 판정, 수정→프론트→실행까지 한 요청의 무손실 보장은 아직 검증되지 않았다.
- source quote 없는 조건을 대조로 제거할지, 값을 되물을지, scalar 충돌을 어떻게 처리할지는 사용자 결정이 필요한 정책이다. 이번에는 변경하지 않았다.
- 공유 작업의 새 커밋 때문에 구현 승인 후 시작할 때 해당 함수 diff와 HEAD를 다시 확인해야 한다.
- **승인 요청:** 위 compiler 한정 첫 수정과 정확한 경계 예외/문서 범위를 승인할지 결정이 필요하다. 실제 LLM 실행은 이 승인에 묶지 않고 건수와 함께 별도로 요청한다.

## 후속 실행 — 승인 후 변경 및 검증

사용자는 2026-10-10에 모든 작업을 승인했다. 코드 변경은 재현 테스트가 먼저 실패한 네 독립 문제를 대상으로 했다. 프롬프트·원문 규칙·새 모델/파서/DSL은 변경하지 않았다.

| 지점 | 수정 전 | 수정 후 | 회귀 확인 |
|---|---|---|---|
| `strategy_compiler._build_parsed` | 20/60일 return 랭킹이 첫 기간 하나로 줄어듦 | lookback이 다른 두 component 유지; 완전 중복은 하나 | 검증→조립→역변환→재조립·순서 대조 |
| `models.StrategySpec._drop_mirrored_valueless_exits` | MA5/20 entry를 추가하면 MA20/60 exit 소실 | 양쪽에 명시된 parameter가 다르면 기존 exit 유지 | schema→validation→ParsedStrategy, 기존 미러 제거 테스트 유지 |
| `patch_applier` | 정상 승격 그룹이 불완전한 다른 그룹까지 흡수; `/entry_conditions/-1/value`가 끝 항목 변경 | 승격된 그룹만 흡수; 중간 배열 음수 인덱스 거부 | 두 테스트 모두 수정 전 실패·수정 후 통과 |
| `capability_validator._condition_identity` | RSI 동일 신호의 set12만/add2만 중 뒤 규칙 소실 | 금액·모드를 identity에 포함, 두 납입 규칙 조립 | validation→ParsedStrategy.contribution_rules |

저장소 변경: `compiler/strategy_compiler.py`, `interpreter/models.py`, `conversation/patch_applier.py`, `validation/capability_validator.py`, 기존 `backend/tests/test_strategy_conversation.py`, `CLAUDE.md`, `docs/PROJECT_PLAN.md`, `docs/SRS.md`, `docs/software_architecture.md`. 경계가 다른 코드는 작은 작업으로 순차 수정했다. 공유 세션의 `.claude/skills/x-backtest-post/scripts/*` 미추적 파일은 내 작업이 아니며 수정하지 않았다. 커밋·배포·시장 데이터 갱신은 하지 않았다.

검증: `test_strategy_conversation.py` **334 passed**, 여기에 `test_quote_check.py`·`test_recall_validator.py`·`test_interpretation_authority.py`를 포함한 교차 검증 **392 passed**. `npm run test:frontend` **2397 passed, 1 skipped**. `QA_DISPLAY_SWEEP=1 npx vitest run scripts/qa_kr_display_sweep.test.ts`는 기존 캐시 **81/81 표시 결함0**. `git diff --check` 통과. 사용자 지정 백엔드 전체 명령은 `test_sync_data_status.py`·`test_sync_fundamental_enrichment_gate.py`가 `data.krx.co.kr` DNS 오류를 내 수집 단계에서 중단됐다. 두 파일 제외 재실행은 로컬 PostgreSQL fixture 연결 오류와 기존 무관 실패(`test_backfill_us_stocks`, `test_delisted_stock_names`)를 보였고 38%에서 장시간 정체되어 중단했다. 따라서 전체 통과로 보고하지 않는다.

실모델 게이트: `qa_template_detect.py --category 복합전략`은 18개 요청, 내부 LLM 호출 예상 18~90회로 고지 후 시작했다. 첫 요청에서 OpenRouter 한도 소진 폴백이 기록됐고 실제 선택 모델은 `hf.co/unsloth/Qwen3.5-9B-GGUF:Q4_K_M`이었다. 이 로컬 모델 호출이 연속 HTTP 429를 반환해 첫 유효 응답 전에 중단했다. **유효 실모델 결과0건, 운영120B 결과0건**이므로 게이트 통과·전후 성능을 주장하지 않는다. 프롬프트/레인 변경이 없어 qa_free_input modify/fill은 대상이 아니며, /us 경로를 바꾸지 않아 영어 3종은 대상이 아니다.

남은 확인된 위험: 형식 재생성의 정상 조건 손실, `compile_partial`의 Pydantic ValidationError로 인한 전체 실패, 원문/인용 의미 재심 경로, 프롬프트의 최소 보유 기간 모순. 이들은 단순 배열 union이나 값 보정으로 고치면 또 다른 회귀를 만들 수 있어, 이번 작은 수리의 동작 범위에 포함하지 않았다. 구조 진단 목록은 `CLAUDE.md` 현행 격차에도 추가했다.

## 후속 실행 2 — 형식 재생성 및 위험 값의 실패 단위

위 마지막 문단의 두 결정론 위험(재생성 손실·부분 조립 예외)은 이후 사용자 요청에 따라 다음처럼 수리했다. 원문/인용 의미 재심과 프롬프트 모순은 여전히 아래 남은 위험에 해당한다.

| 재현(LLM 호출 0회) | 수정 전 | 수정 후 |
|---|---|---|
| 전체 입력 인용을 고친 재생성본이 PER만 내고 원출력의 PBR≤1을 빠뜨림 | 유효 JSON이라는 이유로 PBR 조건 소실 | 오류 대상 밖 PBR 조건을 원출력 그대로 복원; PER 인용 수리는 채택 |
| 같은 PER의 별도 조건을 재생성본이 20→25로 바꿈 | 값 25로 교체, 원래 값 소실 | 조건 identity가 모호하면 원출력으로 돌아가 20 보존 |
| PER 인용 수리 중 60일 수익률 랭킹을 빠뜨림 | 랭킹 전체 소실 | 무관 전략 칸 변경을 감지해 원출력으로 돌아감 |
| PER·PBR과 함께 `partial_take_profits.profit_percent=-5` 또는 `position_sizing.kelly_fraction=2` | 중첩 Pydantic `ValidationError`가 요청 전체를 중단 | 범위 오류·누락 질문, 해당 값 미확정, PER·PBR 초안 유지 |
| 분할 매수 회차 1회·간격 50%·미완성 단계의 하락 폭 100% | 중첩 `EntryTranches`/`TrancheLevel` 검증 예외 또는 범위 오류 누락 | 해당 값만 미정으로 내려 되묻고 다른 PER 조건 유지 |
| 볼린저 하단 터치가 두 조각으로 중복되고 중심선 상향이 한 조각 | 첫 하단 터치만 오류 대상으로 표시되어 다른 하단 터치가 무관 조건 복원에 포함될 위험 | 같은 오류 조각의 모든 경로를 대상으로 표시 |

재생성 수리는 `interpreter/llm_strategy_interpreter.py`에서 이미 검증된 JSON 객체만 비교한다. 인용의 의미를 원문 정규식으로 새로 판정하지 않는다. 볼린저 중복 조각 경로는 `output_repair.py`에서 모두 보고한다. 범위 수리는 `validation/parameter_validator.py`가 엔진 모델의 수치 범위와 맞춰 해당 값만 비우며 `primary.py`가 검증 오류를 `notices`에 싣는다. 새 가드의 설명은 `components/admin/AgentsTab.tsx`에도 반영했다. 회귀는 기존 `test_strategy_conversation.py`·`test_bollinger_band_cross.py`에 추가했다. 현재 교차 검증(이 둘과 `test_quote_check.py`·`test_recall_validator.py`·`test_interpretation_authority.py`) **444 통과**; 프론트 전체 **2,397 통과·1 skip**(상장폐지 종목명 캐시 1건이 한 차례 실패했으나 단독·전체 재실행 통과); 캐시 기반 KR 표시 **81/81 결함 0**. 백엔드 전체는 `pykrx` 수집 과정의 `data.krx.co.kr` DNS 실패 2건으로 테스트 실행 전에 중단됐다. 실LLM 카테고리 게이트의 앞선 시도는 운영 120B 한도 소진, 로컬 9B 연속 429로 **유효 응답 0건**이었다. 이 수정 뒤 재측정은 불가능했으므로 실모델 성능 통과로 보고하지 않는다.

남은 위험: `whole_input_quote_fields` 자체는 원문과 인용을 대조하고, `primary._fill_deterministic_condition_params`, 레거시 fast-path, 프론트 `parsedStrategyMerge` 등에는 원문/인용 의미 재심이 남아 있다(위 전수 표와 `CLAUDE.md` 현행 격차). quote-check의 과거 120B false-drop은 이번 재현 입력에서 신규 실모델 표본을 얻지 못했다. 프롬프트의 최소 보유 기간 모순은 메인 프롬프트 수정과 modify/fill 전후 하니스가 함께 필요한 별도 범위이며, 현재 120B/9B 429로 검증할 수 없다. 전체 백엔드와 실LLM 게이트의 미통과 상태도 해소되지 않았다. 커밋·배포·데이터 갱신은 하지 않았다.

## 후속 실행 3 — 로컬 9B 레인 복구 후 복합전략 게이트

로컬 Ollama의 모델 목록과 짧은 추론 요청이 정상 응답한 뒤, 같은 코드 상태에서 `uv run python scripts/qa_template_detect.py --category 복합전략`을 캐시 없이 다시 실행했다. 18개 예시 모두 완료되어 **치명 0·미탐지 0·종목수 이슈 0·미대조 수치 0**이었다. 트레이스 18건 전부 `cache_hit=False`; LLM span `metadata.model` 기준 실제 호출 **81회 모두 `hf.co/unsloth/Qwen3.5-9B-GGUF:Q4_K_M`**였다. 첫 두 span의 이름에는 요청 모델인 120B가 남아 있으나 실제 실행 모델은 metadata의 9B이므로 120B 표본으로 세지 않는다. 응답은 `ask` 12건, `answer` 6건이며 되묻기는 계약상 실패가 아니다. `QA_DISPLAY_SWEEP=1 npx vitest run scripts/qa_kr_display_sweep.test.ts`도 기존 81개 표시 캐시에서 **81/81 결함 0**으로 통과했다.

이 측정으로 앞선 로컬 9B 연속 429 장애가 현재 복합전략 경로에서 재현되지 않는다는 점과 해당 18개 예시의 하니스 합격만 확인했다. 운영 120B의 이번 수정 후 성능, 81개 KR 파싱 전수, 수정 턴·되묻기 하니스, 전체 백엔드 테스트는 이 실행에서 다시 측정하지 않았다. 하니스의 정규식 기대값과 개별 의미 단위 커버리지에는 기존 사각지대가 있으므로 치명 0을 모든 전략 표현의 정확성으로 확대하지 않는다. 코드·프롬프트·모델 설정·시장 데이터는 변경하지 않았다.

## 후속 실행 4 — 원문 선차단 제거와 최소·최대 보유 기간 실측 (2026-10-11)

`main._run_nl_parse_impl`의 `full_rewrite_clarification(request.prompt)` 선차단은 primary 수정 앞에서 원문 정규식으로 요청 유형을 판정했다. 이 호출을 제거하고 기존 LLM patches 레인에 전체 발화를 보냈다. 회귀 테스트는 변경 전 `run_primary_modification` 호출 0회를 확인해 실패, 변경 후 1회를 확인해 통과했다. 실서버 "그거 말고 완전 다르게 해줘" 3회는 실제 `hf.co/unsloth/Qwen3.5-9B-GGUF:Q4_K_M`에서 원전략을 보존하고 매수 방향을 되물었다(총 LLM 6회, 캐시 우회). 의미를 대신 정하는 새 코드나 기본값은 없다. 레거시 함수 정의와 `resolve_coach_context_risk` 호출은 별개 미이관 부채로 남는다.

프롬프트 v8.9는 `portfolio.min_hold_period_days`를 형태·다른 규칙에서 지원하면서도 §5에서 "최소 보유 미지원"이라고 모순되게 지시했다. `코스피에서 PER 10 이하인 종목을 매수하고 최소 10거래일은 보유해줘. 최대 보유 기간은 20거래일로 해줘. 종목은 10개, 월간 리밸런싱으로 해줘.`의 캐시 우회 실서버 v8.9/로컬9B 3회는 최초 LLM 출력부터 최소가 비고 최대가 10일로 잘못 채워졌다. 미지원 모순을 없앤 v8.11 3회는 최대20일은 맞췄지만 최소는 여전히 비었다. 출력 형태에서 최소 키를 최대 키 옆에 둔 v8.12 완료 표본 3회(`3dd0a4478859`, `31803f6768b0`, `9b1494e654e8`)는 모두 `min_holding_days=10`, `hold_period_days=20`, `cache_hit=False`; 실제 LLM은 전부 로컬9B였다. 첫 v8.12 클라이언트는 210초에 타임아웃됐고 뒤에 서버 트레이스가 성공으로 완료된 별도 요청만 표본으로 셌다. 프롬프트에 새 동의어·예시·기본값은 추가하지 않았다.

프롬프트 변경 게이트 `qa_free_input.py modify` 43건은 `PASS=39, ASK=2, COLLATERAL=1, FAIL=1`, `fill` 43건은 `PASS=39, ASK=3, FAIL=1`이다. 86턴 모두 캐시 미스, LLM span의 실제 모델은 로컬9B **92회 전부**다. 되묻기 자체는 항상 실패가 아니지만 "여덟 종목"과 "두 배"는 이미 값이 제시됐는데 다시 물었으므로 값 보존 결함이다. 수정 답변 `per 10 이하인 저평가 종목`은 기준 유니버스를 KOSPI200에서 KOSPI+KOSDAQ으로 바꾸는 침범을 보였고, 빈칸 답변에서는 PER을 반영하지 않고 재질문했다. "20일 보유 후 청산"은 두 하니스 모두 `hold_period_days=21`로 틀렸다. 트레이스 `016eb32f03fb`의 1차 LLM patch부터 값이 21이므로 하류 보정 문제가 아니다. 같은 9B의 v8.9/v8.12 시스템 프롬프트 메모리 대조는 각 3회 모두 21을 냈다. 2026-10-10 운영 120B의 v8.9 트레이스 `7d9e00d0504c`·`42c622232872`는 20이었지만 **다른 모델**이므로 이번 변경의 인과 대조군이 아니다. 이 값 오류를 고치려고 결정론 코드가 원문 숫자를 재해석하게 하지 않는다.

`qa_template_detect.py --category 복합전략`은 v8.12 새 파싱 18/18 완료, 치명·미탐지·종목수·미대조 수치 모두 0이었다. 18트레이스 전부 캐시 미스, 실제 LLM span 81회 전부 로컬9B다. `QA_DISPLAY_SWEEP=1 npx vitest run scripts/qa_kr_display_sweep.test.ts`는 **기존 81개 표시 캐시** 81/81 결함 0이며 새 파싱 전수를 뜻하지 않는다. 관련 백엔드 446 passed, 프론트 전체 2,398 passed·1 skipped. 사용자가 지정한 백엔드 전체 명령은 `test_sync_data_status.py`·`test_sync_fundamental_enrichment_gate.py`의 외부 KRX DNS 실패로 수집 중단됐다. 두 파일 제외 재실행은 DB 의존 오류와 약 38% 정체로 중단했으므로 전체 통과가 아니다. 운영120B·81개 KR 새 파싱 전수·/us 영어 3종은 미실행이다. 커밋·배포·시장 데이터 갱신 없음.

## 후속 실행 5 — 수정 패치의 보유 거래일 오변환 대조 (2026-10-11)

로컬 9B의 기존 결함은 사고 당시 초안·대기 질문을 그대로 쓰면 재현된다. `20일 보유 후 청산`을 1차 LLM이 `/portfolio/hold_period_days=21`로 출력했고, 이전 코드는 20일을 미반영 진단 로그에만 남겨 최종 21일 패치를 확정했다. 이번에는 **수정/되묻기 턴에서 기존 수치 대조가 누락을 보고하고, 숫자 값이 있는 보유 기간 패치가 있을 때만** 작은 전용 LLM 대조를 호출한다. 대조 LLM은 원문 구절·숫자 표기·단위를 옮겨 적고, 코드는 인용이 발화와 기존 `source_text`에 실재하는지 및 출력 형식만 검증한다. `day`/`일`의 출력 enum 표기만 정규화한다. 모호한 단위·누락·형식 오류는 원래 패치를 유지한다. 숫자 예시를 넣으면 9B가 그 숫자를 모방할 위험이 있어 출력 형태에는 null만 둔다. 원문 정규식이나 새 파서·State·DSL은 없다.

회귀 테스트는 변경 전 21일 오변환으로 실패한 뒤 수정 후 통과했다. 무관한 종목 수 패치 보존, 이미 맞는 값에서 추가 호출 없음, 잘못된 대조 결과의 fail-open, 최소·최대 보유 기간의 별도 identity와 응답 순서 독립성을 함께 검사한다. 최종 대조기에서 사고 맥락의 로컬 `hf.co/unsloth/Qwen3.5-9B-GGUF:Q4_K_M` 3회는 1차 patch가 **모두 21**, 최종 patch가 **모두 20**이었다. 독립 15일·30일 오변환 입력도 각 1회 같은 모델에서 15·30으로 복원됐다. 빈 초안의 3회는 1차부터 20이므로 사고 재현 표본으로 세지 않는다. 중간 실험에서 `unit=day`만 받자 9B가 `일`로 답해 3회 모두 fail-open 된 사실도 최종 정규화의 근거다.

최종 코드의 관련 백엔드 교차 테스트는 **453 passed**, 프론트 전체는 **2,398 passed·1 skipped**, `git diff --check` 통과다. 필수 백엔드 전체 명령은 다시 실행했으나 `test_sync_data_status.py`·`test_sync_fundamental_enrichment_gate.py`가 외부 `data.krx.co.kr` DNS 오류를 내 5,586개 테스트 수집 후 실행 전에 중단됐다. KR 표시 스윕은 기존 캐시 81/81 결함 0이다. 복합전략 게이트는 새 파싱 18/18, 치명·미탐지·종목수·미대조 모두 0이며 트레이스 18건의 실제 LLM 호출 **64회 모두 운영 `nvidia/nemotron-3-super-120b-a12b:free`**였다.

`qa_free_input.py modify` 43건은 PASS41·ASK2, `fill` 43건은 PASS39·ASK2·FAIL2였다. 이 실행의 실제 LLM 호출 **94회 모두 운영 120B**다. 실행 시 CLI의 `LLM_PROVIDER=ollama`는 이미 실행 중인 백엔드 서버 설정을 바꾸지 못했다. 따라서 이 86턴을 로컬 9B 전후 대조로 쓰지 않는다. `20일 보유 후 청산`은 두 계열 모두 20일로 통과했지만, `여덟 종목`·`두 배`는 명시값을 다시 물었다. fill의 `60일 신고가`와 `한 달 지나면 정리`는 붉었고, 운영 120B 재표본 3회씩에서 전자는 모두 60일 진입 조건을 포함하되 1회 기존 20일도 남겼고 후자는 3회 모두 보유 기간으로 반영되지 않았다. 두 케이스의 1차 출력은 보유 기간 patch가 아니므로 이번 전용 대조가 발동하지 않았으며, 이번 보정의 인과 회귀로 볼 수 없다. **월 표현 해석 실패와 기존 조건 잔존은 해결되지 않았다.** /us 영어 3종과 KR 81개 새 파싱 전수는 미실행이다. 커밋·배포·시장 데이터 갱신은 하지 않았다.

### 후속 원인 분리 — 명시값 재질문과 교체 패치의 부분 적용

- 로컬 9B의 `여덟 종목` 트레이스 `fd591847e94f`·`9638e7047a1b`는 1차 출력에서 이미 `/portfolio/selection_count=8`을 냈다. `두 배` 트레이스 `2658fb479ae5`·`ba7d1b289acb`도 `/risk_management/take_profit=100`을 냈다. 입력 인용에 아라비아 숫자가 없으면 `primary._patch_provenance_supported`의 숫자 스칼라 출처 게이트가 인용을 인정하지 않고, `_input_number_candidates`의 숫자 대조도 일치하지 않아 **정답 패치가 하류에서 거부**된다. 이 두 ASK를 9B의 의미 해석 실패로 분류하면 원인 레이어를 잘못 고친다. 원문 어휘/숫자 정규식 확장이 아니라, LLM이 낸 수사·값의 출처를 검증하는 판정 레인과 환각 게이트의 접속 범위를 별도 설계해야 한다.
- 운영 120B `60일 신고가 뚫을때` 트레이스 `d2fe9948423a`의 1차 출력은 `add /entry_conditions/-` 60일 조건과 `remove /entry_conditions/0`을 함께 냈다. 추가에는 출처 인용이 있고 삭제에는 없어 환각 게이트가 **삭제만 거부**한다. `primary.run_primary_modification`은 통과한 추가를 단독 적용해 기존 20일과 새 60일을 모두 남겼고 사용자 `notices`는 비었다. 이 경우는 LLM 단독 오해석이 아니라 **서로 의존하는 패치의 부분 적용과 silent change**다. 출처 없는 삭제를 무작정 수락하면 진짜 추가 요청에서 기존 조건이 지워질 수 있으므로, 그룹의 원자성 또는 전용 LLM 교체 판정이 필요하다.
- 운영 120B `한 달 지나면 정리` 트레이스 `af83c6d74b28`은 1차에서 보유 기간이 아닌 이동평균 청산 조건을 만들었고 quote-check가 제거했다. 이 턴에는 보유 기간 patch가 없어 새 수치 대조기가 동작하지 않는다. 로컬 9B의 같은 표현 `d2dc5b0d7b94`·`0588bf682cdc`는 1차에서 `hold_period_days=21`을 냈으므로 레인 모델에 따라 최초 손실 계층이 다르다.

`docs/architecture/boundaries.md`의 K 경계는 보조 LLM 검사 배선은 허용하지만 기존 검증·적용 규칙 보존을 strict rule로 둔다. 현재 `primary`의 출처 게이트 변경과 조건 patch 병합 규칙은 해당 경계 목적을 벗어나므로 이 후속 실행에서 수정하지 않았다. 적용할 범위를 별도 경계에 명시하는 작업이 선행되어야 한다. `.agents/skills/strategy-interpretation/SKILL.md`의 “경로가 포함된다는 이유만으로 런타임 조정 boundary K를 일반 해석 기능 확장에 사용하지 않는다” 원칙도 같은 제한이다.

## 후속 실행 6 — 수정 패치 출처·조건 교체 원자성 및 인용 판정 소비 (2026-10-11)

사용자가 허락한 경계 조정을 Boundary G 문서 작업으로 먼저 반영해 `docs/architecture/boundaries.md`에 **W: Strategy Interpretation Stabilization**을 추가하고 `docs/development/codex-rules.md`의 허용 목록을 맞췄다. 이후 코드·테스트는 W만 선택해 변경했다. 앞 절의 K 경계 제한은 당시 진단 기록이며 이 후속 구현에 사용한 경계가 아니다.

| 실제 최초 손실 | 변경 전 | 변경 후 |
|---|---|---|
| 로컬 9B가 `여덟 종목`→8, `두 배`→익절 100을 맞게 냈지만 숫자 출처 게이트가 거부 | 명시값을 다시 묻고 기존 값 유지 | 보조 LLM이 패치 경로별 수량 표현·값·단위를 독립적으로 옮겨 적고, 인용이 입력과 패치 출처 양쪽에 실재하며 값이 일치할 때만 수락. 근거 없는 `리스크 관리`는 계속 거부 |
| LLM이 `add` 새 조건 + 인용 없는 `remove` 기존 조건을 한 교체로 냄 | `remove`만 거부하고 두 조건 공존 | 보조 LLM이 직전 질문과 발화로 교체/추가/불명확을 분류. 교체는 둘 다, 추가는 add만, 불명확은 둘 다 보류하고 관계를 질문 |
| 120B가 `한 달 지나면 정리`를 MA 매도로 오해석하고 quote-check가 두 번 `no/other` 판정 | 수정 레인이 판정을 소비하지 않아 잘못된 조건이 붙거나 요청이 무변경·무안내로 종료 | 이번에 추가한 조건에만 기존 생성 레인의 인용 제거를 적용하고 미반영을 안내. 교체의 새 조건이 거부되면 짝 삭제도 함께 보류. 기존 이월 조건은 이번 원문으로 재심하지 않음 |

새 회귀 테스트는 각각 수정 전 실패를 확인한 뒤 고쳤다. 이번 후속의 관련 백엔드 테스트(`test_strategy_conversation.py`·`test_quote_check.py`·`test_interpretation_authority.py`·`test_recall_validator.py`)는 **417 passed**, 프론트 전체는 **2,398 passed·1 skipped**였다. 새 질문은 출력 가드에서 유지됨을 검사했다. 지정 백엔드 전체 명령은 다시 실행했으나 `test_sync_data_status.py`와 `test_sync_fundamental_enrichment_gate.py`가 테스트 수집 중 외부 `data.krx.co.kr` DNS 오류를 내 중단됐다. 전체 통과로 세지 않는다.

실서버 게이트: KR `qa_template_detect.py --category 복합전략`은 새 요청 **18/18, 치명·미탐지·종목수·미대조 모두 0**. `qa_free_input.py modify`는 **PASS43/43**, `fill`은 **PASS41·FAIL2/43**. 실패 둘은 `60일 신고가 뚫을때`와 `한 달 지나면 정리`다. 전자는 하니스가 기존 20일 진입을 초안에 둔 채 “매수 조건이 빠져 있다”고 묻고, 120B가 60일을 `add`만 냈다. 이 질문 아래 추가가 교체 오류라는 근거는 약하므로 기대값을 결과에 맞춰 바꾸지 않고 하니스 모순으로 표시한다. 후자는 120B의 1차 출력부터 MA 조건이라 quote-check가 두 번 부정·제거해 잘못된 신호는 막았지만 21일 보유 기간은 복구되지 않았다. 120B가 수정 질문에서는 21일을 낸 사례가 있으므로 질문 맥락 민감성이 남는다. KR 화면 표시 스윕은 **기존 응답 캐시 81/81, 결함 0**이며 새 KR 파싱 81개 전수의 성적은 아니다.

영어 `/us` 레드팀 **51케이스 실행 완료**(하니스는 개별 판정 없이 결과 JSONL을 기록), `qa_free_input.py modify --lang en`은 **PASS31·ASK1·FAIL3/35**, `qa_multiturn_binding.py --lang en`은 **6시나리오 중 5개 무경고, ETF 질문의 부적절한 재무 칩 2건**으로 종료 코드 1이었다. 영어 수정 FAIL의 RSI `below 30`→`<30`, `above 70`→`>70`은 LLM 출력 자체가 그렇게 나왔고 하니스는 `≤/≥`를 기대한다. `3x the average`는 LLM이 `technical.volume_ratio >= 3`으로 냈지만 하니스는 `volume_spike`를 기대한다. 모두 이번 인용·출처 코드가 만든 변환이 아니며, 기대 의미를 독립적으로 재판정할 필요가 있다. `close it out after a month`는 120B가 1차에 신고가 청산을 만든 별도 ASK로, 월 보유 기간의 같은 모델 약점이다. ETF 칩 문제도 이번 수정 경로가 아닌 질문 후보 구성에서 발생했다. 실패를 통과로 바꾸지 않았다.

10:00–10:09 KST의 트레이스 106턴에서 실제 LLM span **169회 모두 `nvidia/nemotron-3-super-120b-a12b:free`**, 캐시 적중 1턴이었다. 10:09–10:20 KST의 162턴에서는 LLM span **344회 모두 같은 운영 120B**, 캐시 적중 5턴이었다. 후자의 다수는 `/us` 레드팀과 영어 하니스다. 정확한 게이트별 LLM span 분할 집계 대신 시간 구간 집계로 기록하며, 캐시 적중 턴은 새 모델 표본으로 세지 않는다. 로컬 9B 직접 판정 표본에서는 숫자 출처 3건(여덟/두 배/무수치)과 조건 교체 3건(수정/빈칸/명시적 추가)을 확인했다. 9B 결과를 운영 120B 결과로 섞지 않았다.

**남은 결함:** 월 보유 표현을 120B가 다른 지표로 내는 최초 의미 오류는 형식·출처·검증의 결정론 수리만으로 21일을 만들 수 없다. 원문 어휘 특례나 값 주입으로 고치지 않았고, 잘못된 조건 적용 방지·안내까지만 완료했다. 영어 하니스의 비교 연산자·거래량 배수 기대와 ETF 칩은 별도 계약 판정이 필요하다. 레거시 `engine/nl_parser.py`·primary fast-path 및 다른 원문 재심 경로는 위 위반 목록에 남는다. 새 Agent·파서·State·DSL, 커밋·배포·시장 데이터 갱신은 없다.

붉은 KR 두 항목은 같은 기준 초안·질문으로 각 **3회 추가 재표본**했다(모두 캐시 미스, 응답 모델 운영 120B). 신고가는 3/3에서 최종 60일 진입 조건 **하나만** 남아 하니스 1회 실패가 안정적으로 재현되지 않았다. 월 보유는 3/3에서 21일이 비고, quote-check가 잘못 만든 매도 조건을 제거했다는 안내가 나왔다. 따라서 월 보유는 지속되는 최초 LLM 의미 오류이며, 신고가의 add/replace는 질문과 초안의 불일치 및 표본 흔들림을 함께 조사해야 한다. 영어 거래량 배수의 `volume_ratio >= 3`은 `prompts.py` 규칙 5-2가 명시한 바로 그 지표라, 하니스의 `volume_spike` 기대가 계약과 어긋난다. 영어 `below/above`의 엄격 부등호 역시 하니스의 비엄격 부등호 기대와 별도 대조가 필요하다. 이 기대값은 이번 작업에서 바꾸지 않았다.

## 후속 실행 7 — 운영 120B 재해석 실험과 거부된 교체의 원자성 (2026-10-11)

최초 손실은 운영 120B의 `MODIFY_STRATEGY` 원출력이 `한 달 지나면 정리`를 `/portfolio/hold_period_days=21` 대신 이동평균 청산 조건으로 낸 단계다. 기존 `quote_check`의 두 번 연속 `no/other`는 그 조건을 제거했지만 보유 기간을 새로 해석하지 못했다. 같은 인터프리터의 긴 프롬프트에 거부된 조건을 알려 한 번 다시 해석하는 v8.13 후보를 만들었다. 고정 스텁은 재해석 응답을 21일로 주면 통과했지만, 이는 120B가 실제로 그렇게 답한다는 증거가 아니었다.

사용자가 합성 전략 초안·예문을 OpenRouter 운영 120B로 보내는 데 명시 동의한 뒤, 같은 공개 테스트 fixture로 기본 해석 2회와 후보 피드백 2회를 비교했다. LLM span의 실제 `metadata.model`은 네 번 모두 `nvidia/nemotron-3-super-120b-a12b:free`, 캐시 없이 완료됐다. 기본 해석은 MA 청산 1회·`hold_period_days=21` 1회였다. 피드백 2회는 **모두 MA 청산**을 다시 냈고, 하나는 20일선을 21일선으로 바꾼 `replace /exit_conditions/0`였다. 따라서 이 후보는 **0/2 회복**으로 기각하고 코드·테스트·v8.13을 되돌려 최종 프롬프트 v8.12를 유지했다. 잘못된 이동평균 내용을 다시 보여주는 피드백이 모델을 그 조건에 묶어 둔다는 해석은 이 표본에 근거한 추론이며, 아직 다른 문장 전체에 대한 인과 증명은 아니다.

그 실측 출력은 별도의 하류 결함을 드러냈다. 기존 RSI 매도를 `replace`로 덮어쓴 잘못된 MA 조건을 quote-check가 제거하면, 조건 목록이 빈 채 조립돼 **원래 RSI 매도까지 사라졌다**. 이 경로를 고정한 테스트는 수정 전 실패를 확인했다. `primary.run_primary_modification`의 조건 교체 보류 가드에 `replace`를 포함해, 인용 거부된 새 조건이 기존 조건을 덮어쓴 경우 수정 전체를 적용하지 않고 원전략·미반영 안내를 유지하도록 고쳤다. 최종 결과에 새 Agent/파서/State/DSL, 원문 어휘 분기, 21일 자동 주입은 없다.

첫 후보 상태의 관련 백엔드 네 파일은 **420 passed**, 프론트 전체는 **2,398 passed·1 skipped**였다. 후보를 되돌리고 원자성 가드만 남긴 최종 상태의 관련 백엔드 네 파일은 **418 passed**, 프론트 전체는 **2,398 passed·1 skipped**였다. 지정 백엔드 전체 명령은 `test_sync_data_status.py`·`test_sync_fundamental_enrichment_gate.py`의 `data.krx.co.kr` DNS 오류로 수집 중단됐다. 두 파일을 제외한 확장 실행도 38%에서 **2,139 passed·4 skipped·3 failed·27 errors**로 중단했다. 로컬 PostgreSQL 접속은 샌드박스에서 `Operation not permitted`였고 외부 모델 관련 테스트는 장시간 대기했다. 3개 실패의 원인은 분리하지 못했으므로 전체 통과로 세지 않는다.

추가로 잘못된 조건 문구를 보여주지 않는 일반 피드백을 운영 120B에서 3회 비교하려 했으나 OpenRouter 무료 한도가 **0/1000**으로 소진돼 첫 호출이 429 후 로컬 9B로 폴백했다. 9B 응답을 120B 증거로 쓰지 않으려고 즉시 중단했으며 유효한 추가 120B 표본은 **0회**다. 월 보유 기간의 최초 의미 오류는 여전히 미해결이다. 새 재해석 방식은 운영 120B로 modify/fill 전후를 검증할 수 있을 때까지 코드에 남기지 않는다. 커밋·배포·데이터 갱신은 하지 않았다.

## 후속 실행 8 — 거부된 조건의 명시 보유 기간 복구 후보 (2026-10-11)

**범위:** Boundary W의 `interpreter/holding_period_check.py`, `primary.py`, 기존 백엔드 회귀 테스트, `AgentsTab.tsx` 흐름 표기. 메인 프롬프트 v8.12, 원문 정규식, 새 파서·상태 모델·DSL은 건드리지 않았다. 문서 반영은 별도 Boundary G 작업이다.

**최초 손실과 수정:** 운영 120B가 `한 달 지나면 정리`를 `add /exit_conditions/-` 또는 `replace /exit_conditions/0`의 MA 신호로 낸 기존 원출력을 각각 고정했다. 인용 대조는 MA 신호를 거부하지만 보유 기간을 만들지 못해 원래 63일이 유지됐다. 두 회귀는 수정 전에 각각 실패했다. 수정 뒤에는 이번 턴의 유일한 patch가 새 조건 추가 또는 교체이고 그 조건이 인용 대조로 제거된 경우에만 기존 보유 기간 보조 레인에 짧은 판정을 요청한다. LLM이 `max_hold`/`min_hold`, 원문 속 짧은 인용, 수량 표기, 수량과 단위를 함께 반환해야 한다. 결정론은 출처 포함·정수·단위 형식만 확인하고, 기존 계약의 1일=1·1개월=21·1년=252거래일 환산을 적용한다. 판정이 유효하면 **원본 초안**에 보유 기간 patch 하나를 적용해 교체 전 조건도 복원한다. 판정 불명확·오류·patch 실패 시 원전략과 미반영 안내를 유지한다. 거부된 `remove`/`replace`의 원자성 가드도 유지한다. 조건 내용이나 원문 어휘를 결정론으로 재판정하지 않는다.

**재현과 측정:** 고정 회귀에서 최초의 MA 청산 조건은 거부되고 최대 보유 기간 **63→21거래일**로 바뀌며 기존 MA 진입·RSI 청산은 그대로 남았다. 3개월=63일, 최소 20일, 무관/불완전한 판정, 인용 부재, 숫자 불일치를 유닛 테스트로 대조했다. 실제 로컬 LLM 짧은 판정은 5회(`한 달`, `3개월`, `최소 20일`, `20일선`, 손절 -8%) 실행했고 span의 실제 모델은 모두 `hf.co/unsloth/Qwen3.5-9B-GGUF:Q4_K_M`였다. 기간 3건은 올바른 종류·수량을 냈고 비보유 2건은 `none`이었다. 이것은 **보조 판정 5회**일 뿐 운영 120B의 전체 수정 성공률이 아니다.

최종 상태 관련 백엔드 네 파일 **427 passed**, 프론트 전체 **2,398 passed·1 skipped**, 캐시 기반 KR 표시 스윕 **81/81 결함 0**, `git diff --check` 통과. 지정 백엔드 전체 명령은 `test_sync_data_status.py`와 `test_sync_fundamental_enrichment_gate.py` 수집 중 KRX DNS 오류로 중단됐다. `qa_template_detect.py --category 복합전략 --refresh`는 처음에는 샌드박스의 localhost 연결 금지로 18건 모두 파싱 요청 전에 실패했다. localhost 권한을 주고 다시 시작했으나 개발 서버가 `/health`에도 5초간 응답하지 않아 게이트를 중단했다. 이 시도에서 새 LLM span은 확인되지 않았으며 **예시 게이트 통과로 세지 않는다**. 운영 120B는 무료 한도 소진으로 이 후보에 대해 0회 측정했다. `modify`/`fill` 및 영어 3종도 이 후보 상태에서는 미실행이다. 운영 120B 재표본과 해당 하니스 전후 대조가 남아 있으므로 월 표현의 운영 레인 해결을 선언하지 않는다.

## 후속 실행 9 — 120B 회복률과 수정 답변의 독립 조건 보존 (2026-10-12)

**범위와 원인:** Boundary W의 `interpreter/output_repair.py`, `interpreter/patch_scope_check.py`, `interpreter/numeric_patch_check.py`, `primary.py`, 기존 백엔드 회귀 테스트, `AgentsTab.tsx` 흐름 설명을 손봤다. 문서 반영은 별도 Boundary G 작업이다. 로컬 9B의 `per 10 이하인 저평가 종목` 수정 답변은 올바른 PER≤10과 함께 요청하지 않은 KOSPI+KOSDAQ 시장 변경을 냈고, 빈칸 답변은 PER 외에 값 없는 시가총액 조건과 그 질문을 만들었다. 각각 캐시 우회 3/3에서 반복됐다. 출처 인용이 발화 전체라는 사실만으로 두 patch가 같은 의미인지는 알 수 없는데, 기존 게이트는 이를 구분하지 않았고 자기 의심 질문 하나가 독립 PER patch까지 보류했다. 빈칸 사례의 원출력은 최상위 JSON `}` 하나만 빠져 재생성까지 실패했다. 수정 전 고정 회귀에서 두 결과는 각각 시장 침범과 PER 전체 누락으로 실패했다.

**최소 수리:** 완성된 배열/객체 뒤 최상위 `}` 하나만 추가하는 형식 수리를 `output_repair`에 넣었다. 다른 잘림은 종전처럼 재생성한다. `patch_scope_check`의 짧은 LLM 판정은 시장 변경의 독립 출처를 확인하고, 한 조건 목록에 여러 add와 특정 add의 질문이 함께 있을 때 조건별 출처를 묶어 확인한다. 분명한 `no`일 때만 해당 patch와 그 질문을 제외하고 안내한다. 형식 오류·애매함·호출 실패는 기존 동작 유지다. 원문 어휘 분기나 값 생성은 없다. 운영 120B의 영어 `close it out after a month`는 다른 실패였다: 최초 LLM은 이미 `/portfolio/hold_period_days=21`을 맞게 냈지만 숫자 출처 보조 프롬프트가 기간 단위를 허용하지 않아 `a month`를 `total_multiplier`로 분류하고 패치를 버렸다. `numeric_patch_check`의 단위 선택지에 day/month/year를 넣고 **보유 기간 경로에서만** 기존 1/21/252거래일 표로 대조한다. 이 재현 테스트도 수정 전 63일 유지로 실패했고 수정 후 21일이 됐다. 다른 경로에 기간 단위를 적용하지 않는 테스트를 추가했다. 메인 프롬프트는 v8.12 그대로다.

**실측 모델과 전후:** 최종 코드의 로컬 9B 단일 실서버 표본에서 PER 수정은 KOSPI200을 지키며 PER≤10을 추가했고, 빈칸 답변도 근거 없는 시가총액 조건만 안내와 함께 제외했다. 두 응답의 `runtime.interpreter.model_name`은 `hf.co/unsloth/Qwen3.5-9B-GGUF:Q4_K_M`였다. 09:00 KST 한도 초기화 뒤 운영 120B의 `한 달 지나면 정리` 캐시 미스 **5/5**는 최초 MA 청산을 quote-check가 두 번 거부하고 짧은 기간 판정이 21일로 복구했다. 각 턴의 LLM span 4개, 총 20개 모두 `nvidia/nemotron-3-super-120b-a12b:free`였다. 기존 매도 조건은 5/5 보존됐다. 영어 월 답변은 수정 전 120B가 올바른 21일 patch를 냈는데 보조 판정이 `total_multiplier`로 답해 ASK가 됐다(`92fdd02265cd`). 수정 후 같은 합성 초안 캐시 미스 **3/3**에서 최초 patch=21, 보조 판정 `month`, 최종 보유=21이었고 총 LLM span 6개 모두 운영 120B였다.

시장 출처 판정의 양성 대조 `코스피와 코스닥으로 바꾸고 PER 10 이하를 추가해줘`는 운영 120B 캐시 미스 **3/3**에서 시장 KOSPI+KOSDAQ과 PER≤10을 모두 반영했다. 각 턴의 메인 해석+시장 보조 판정, 총 LLM span 6개 모두 운영 120B였다. 따라서 PER만 말한 로컬 9B의 무관 시장 변경을 막는 수리가 명시적 시장 변경까지 차단하지는 않았다.

**게이트:** 운영 120B 복합전략 새 파싱은 18/18, 치명·미탐지·종목수·미대조 수치 0(캐시 미스 18, LLM span 61 전부 120B). 최종 숫자 단위 수정 뒤 KR `qa_free_input.py modify`는 PASS43/43(44턴, span 49 전부 120B), `fill`은 PASS42·FAIL1/43(44턴 중 기준 초안 1회 캐시 적중, span 48 전부 120B)이다. 붉은 `60일 신고가 뚫을때`는 기준 초안에 이미 20일 신고가 매수가 있는데 질문은 매수 조건이 빠졌다고 말한다. 운영 120B 추가 3회는 기존 20일+새 60일 공존 2회, 60일 교체 1회였다. 하니스는 첫 진입 신호가 60일이기를 기대해 공존을 실패로 센다. 초안·질문이 충돌하고 모델도 add/replace가 흔들리므로 기대값을 고치거나 기존 조건을 무단 삭제하지 않았다. 기존 81개 KR 화면 표시 캐시는 81/81 결함 0이며 새 KR 파싱 81개 전수는 아니다.

영어 `/us` 수정 하니스는 단위 수정 전 PASS31·ASK1·FAIL3/35였고, 최종 코드에서 **PASS32·FAIL3/35**(36턴, span 43 전부 운영 120B)이다. 월 답변 ASK가 PASS로 바뀌었다. 세 FAIL은 기존 `below 30`·`above 70`의 엄격 부등호와 `3x`의 `volume_ratio`를 하니스가 다르게 기대하는 항목이며, 이번 코드가 바꾼 경로가 아니다. 영어 레드팀 51케이스는 결과 JSONL 수집을 완료했으나 개별 정답 채점기가 없어 합격률을 주장하지 않는다. 영어 멀티턴 6시나리오는 이전과 같이 ETF 재무 칩 2건 경고, 나머지 5시나리오 무경고였다. 단위 수정 전 이 영어 3종의 150개 root trace에서 LLM span 217개는 모두 운영 120B였고 cache hit 5건이었다. 수정 후 영어 35개 답변 턴은 별도로 위 span 43개를 확인했다.

관련 백엔드 다섯 파일 **467 passed**, 프론트 전체 **2,398 passed·1 skipped**, `git diff --check` 통과. 지정 백엔드 전체 명령은 `test_sync_data_status.py`·`test_sync_fundamental_enrichment_gate.py` 수집 단계의 KRX DNS 실패 2건으로 두 번 중단됐다. 두 파일을 제외한 앞선 확장 실행은 2,177 passed·4 skipped·2 failed·27 errors 상태에서 중단했다. 로컬 PostgreSQL 접속 금지 오류가 다수였고, 별도 실패는 `test_backfill_us_stocks` 스키마 칸 목록과 `test_delisted_stock_names`의 `scripts.sync_data` import였다. 전체 통과로 세지 않는다. 새 KR 81개 파싱 전수는 미실행이다. 레거시 원문 정규식·fast-path와 위 전수 표의 남은 원문 재심은 이번 경계에서 지우지 않았다. 다른 세션의 미커밋 변경을 되돌리지 않았고 커밋·배포·시장 데이터 갱신도 하지 않았다.


## 후속 실행 10 — KR 신고가 fill 대조와 백엔드 전체 실행 (2026-10-12)

**신고가 fill의 판정 범위:** 기존 `qa_free_input.py`의 기준 초안에는 20일 고점 돌파 매수 조건이 이미 있지만 질문은 매수 조건이 비었다고 말한다. 이어진 `60일 신고가 뚫을때`는 기존 조건의 교체인지 추가인지 지정하지 않는다. 하니스의 `sig_entry`는 같은 지표의 첫 진입 신호만 읽으므로 20일과 60일이 공존해도 20일을 보고 실패로 센다. 이를 제품의 조건 소실로 고치면 요청하지 않은 기존 조건 삭제가 된다. 이 입력은 기대값이 정해진 회귀 사례로 쓰지 않고, 초안과 질문을 일치시킨 별도 대조로 판정했다. 하니스·제품 코드는 이번 실행에서 수정하지 않았다.

**운영 레인 대조:** 매수 조건이 실제로 빈 초안과 fill 질문에 `60일 신고가 뚫을때`를 답한 결과는 3/3에서 60일 조건 하나였다. 20일 조건이 있는 초안에 `기존 20일 신고가 매수 조건을 60일로 바꿔줘`라고 명시하면 3/3에서 60일 조건 하나, `60일 신고가 매수 조건도 추가해줘`라고 명시하면 3/3에서 20일과 60일 조건이 공존했다. 아홉 턴은 모두 캐시를 우회했고 각 턴의 LLM span 1개, 총 9개 `metadata.model`이 `nvidia/nemotron-3-super-120b-a12b:free`였다. 이는 일관된 입력에서의 의미 보존 대조이며 기존 모순된 하니스의 PASS42/43을 PASS43/43으로 고쳐 세는 근거는 아니다.

**전체 백엔드:** 지정 명령(`uv run --frozen pytest tests/ --ignore=tests/test_backtest_engine.py --ignore=tests/test_engine_ai.py --ignore=tests/test_ai_sell.py --ignore=tests/test_api_isolation.py`)을 KRX DNS와 로컬 `simons_test` PostgreSQL에 접근 가능한 환경에서 끝까지 실행했다. 결과는 **5,672 passed·5 skipped·1 failed**(323.54초)다. 유일한 실패 `test_backfill_us_stocks.py::test_columns_match_korean_schema`는 `scripts/backfill_us_stocks.py`의 미국 데이터 열 목록이 현재 한국 parquet 표본보다 5개 적은 별도 데이터 파이프라인 스키마 불일치다. 이전 부분 실행의 `scripts.sync_data` import 오류는 이 전체 실행에서 재현되지 않았다. 전체 백엔드 합격으로 보고하지 않는다. `scripts/**`는 Codex 규칙상 금지 경로이고 이 후속은 해석 경계의 검증이므로 스크립트·데이터를 바꾸지 않았다. 프론트·새 KR 81개 파싱 전수는 이번 후속에서 재실행하지 않았으며 앞선 결과를 현재 새 측정으로 세지 않는다.


## 후속 실행 11 — KR fill 하니스 정합성과 월 보유 최초 해석 보류 (2026-10-12)

**범위:** Boundary G에서 `scripts/qa_free_input.py`를 W의 기존 QA 자산으로 좁게 추가한 뒤, 별도 Boundary W 작업에서 이 스크립트와 `backend/tests/test_strategy_conversation.py`만 최종 변경했다. `fill`의 진입·청산 질문에는 기준 `ParsedStrategy`의 해당 신호 목록을 비우고, 제거한 신호를 다시 암시하는 `description`도 비운 사본을 보낸다. 다른 슬롯과 원본 기준 전략은 유지한다. 이전에는 기준 전략에 이미 20일 고점 매수가 있으면서 “매수 조건이 빠져 있습니다”라고 물었다. `sig_entry`·`sig_exit`는 같은 indicator의 첫 신호에서 멈추지 않고 모든 신호를 검사한다. 회귀 테스트는 수정 전 helper 부재로 실패했고 수정 후 실제 `run("fill")`의 전송 초안과 판정을 포함해 통과했다. 사용자 원문에서 어휘를 읽는 판정은 추가하지 않았다.

**월 보유 최초 해석(후속 실행 14에서 측정 오류 정정):** 과거 운영 120B 트레이스의 사용자 프롬프트에는 “직전 질문이 묻는 필드의 패치”라는 지시가 있어, 청산 조건 질문의 답 `한 달 지나면 정리`를 `exit_conditions`에 넣도록 끌 가능성을 검토했다. 한 줄을 “답변의 의미에 맞는 필드”로 바꾼 후보와 기존 문구를 로컬 9B에서 각 3회 비교했지만, **트레이스의 잘린 시스템 프롬프트**를 사용했다. 따라서 30일 청산 조건이 나온 결과는 운영 프롬프트의 전후 성능 증거가 아니다. 후보와 PROMPT_VERSION 변경은 되돌려 v8.12를 유지했다. 당시 온전한 내부 프롬프트의 OpenRouter 전송은 자동 승인 검토가 거절했다. 기존 최종 보유 기간 5/5 복구는 유효하지만 최초 LLM 출력 오류 해결을 뜻하지 않는다.

**검증:** 최종 코드의 관련 백엔드 다섯 파일 **482 passed**(이는 후보 프롬프트를 잠시 적용한 상태의 중간 실행), 프론트 전체 **2,398 passed·1 skipped**, 저장된 응답의 KR 표시 **81/81 결함 0**. 프롬프트를 v8.12로 되돌린 최종 코드에서 미국 백필 테스트 파일만 제외한 백엔드 전체는 **5,634 passed·5 skipped·0 failed**였다(415.98초). 원래 지정 명령은 같은 날 미국 백필 열 목록 불일치 1건으로 **5,674 passed·5 skipped·1 failed**였고, 이 실패는 한국어 해석 변경과 별개다. `qa_free_input.py modify/fill`, 복합전략 새 파싱, 한국어 81개 새 파싱은 이번 최종 코드에서 **미실행**(내부 프롬프트 외부 전송 승인 대기)이다. 표시 81/81을 새 파싱 81/81로 세지 않는다. `git diff --check` 통과, 커밋·배포·시장 데이터 갱신 없음.

## 후속 실행 12 — 운영 120B 월 보유 A/B의 입력 결함 (2026-10-12, 후속 실행 14에서 정정)

사용자의 후속 승인 뒤 질문 귀속 문구만 바꾼 A/B를 각각 3회 실행했다. 응답의 실제 `data.model`은 여섯 건 모두 `nvidia/nemotron-3-super-120b-a12b:free`, provider는 Nvidia였다. 기존·후보 각 3회 모두 미등록 30일 청산 조건을 냈다. **그러나 스크립트가 `StrategyInterpreter()._system_prompt` 대신 트레이스의 `inputs.system_prompt`를 전달했고, 이 기록은 4,005자로 잘려 있었다.** 당시 “온전한 현재 시스템 프롬프트” 및 “최초 출력 0/6”이라는 성능 결론은 잘못이다. 운영 프롬프트 66,033자의 A/B가 아니므로 후보의 효과·무효를 이 여섯 응답으로 판정하지 않는다. 초안에 청산 조건이 있으면서 비었다고 묻는 문맥 충돌도 있었다. 코드에는 후보를 적용하지 않았고 PROMPT_VERSION은 v8.12다.

그다음 청산 조건과 설명을 비운 일관된 초안에 내부 프롬프트 전체를 보내 운영 120B 3회 대조를 시도했으나 자동 승인 검토가 **내부 시스템 프롬프트의 OpenRouter 전송**을 거부했다. 차단을 우회하지 않았고, 운영 120B의 일관된 초안 재표본·최종 `modify`/`fill`·한국어 81개 새 파싱은 미실행이다. 이 절의 6회는 실제 120B 모델 응답이지만 **잘린 프롬프트를 사용한 무효 측정**이다.

## 후속 실행 13 — 일관된 청산 빈칸의 로컬 9B 잘린 프롬프트 대조 (2026-10-12, 후속 실행 14에서 정정)

운영 120B의 내부 프롬프트 외부 전송이 차단된 상태에서 localhost Ollama의 기존 `hf.co/unsloth/Qwen3.5-9B-GGUF:Q4_K_M`를 사용했다. 기준 초안의 청산 조건과 설명을 비운 뒤 실제 fill 질문과 답 `한 달 지나면 정리`를 넣어 3회 호출했다. `data.model`은 모두 위 로컬 9B였고, 세 출력은 미등록 `time.hold_period > 30 days` 조건이었다. **하지만 이 호출도 트레이스의 잘린 4,005자 시스템 프롬프트를 썼다.** 당시 “온전한 프롬프트” 및 “모순을 없애도 최초 오류가 남는다”는 결론은 철회한다. 운영 120B 결과로도 세지 않는다.

이 무효 출력의 patch는 `PatchOp` 스키마에는 유효하지만 `primary._patch_provenance_supported`는 false를 반환했다. 인용이 배열 안 조건에만 있고 패치 자체나 단일 조건 객체에는 없어 기존 출처 게이트가 거부한다는 단계별 대조 자체는 사실이다. 다만 운영 프롬프트의 회귀 사례로 채택하지 않는다. 전체 요청 end-to-end 재생은 하지 않았다.

## 후속 실행 14 — 실제 시스템 프롬프트 길이 확인과 로컬 9B 재측정 (2026-10-12)

측정 스크립트를 재검토하니 §11~13의 직접 호출은 모두 트레이스의 `inputs.system_prompt`를 사용했다. 이를 현재 `StrategyInterpreter()._system_prompt`와 길이로 대조한 결과 **4,005자 대 66,033자**, 동일하지 않았다. 따라서 §12의 120B 여섯 응답, §11·13의 로컬 9B 오류 응답은 모델이나 실제 운영 프롬프트의 성능 판단에서 제외한다. 이 정정은 사용자에게도 즉시 알렸다.

외부 전송 없이 localhost Ollama에 **실제 66,033자 시스템 프롬프트**를 보내 로컬 `hf.co/unsloth/Qwen3.5-9B-GGUF:Q4_K_M`를 재측정했다. 질문과 초안이 일치하도록 청산 조건·설명을 비운 경우 3/3, 기존처럼 청산 조건이 있으면서 “비었다”고 묻는 경우 3/3 모두 최초 출력이 `replace /portfolio/hold_period_days=21`, `source_text="한 달"`이었다. 따라서 **이 로컬 표본에서 월 보유 최초 해석 오류는 재현되지 않았다.** 직접 LLM 응답을 본 것이므로 최종 `ParsedStrategy` 게이트 통과로 확대하지 않는다. 운영 120B의 일관된 초안 결과 및 최종 한국어 하니스·81개 새 파싱은 미측정 상태다. 제품 코드·프롬프트는 수정하지 않았고 문서의 성능 주장을 바로잡았다.

같은 일관된 초안을 실제 `StrategyInterpreter.interpret`에 넣은 로컬 한 턴은 수리 0회로 위 21일 패치를 냈고, `apply_patches` 뒤 `portfolio.hold_period_days`가 null→21로 바뀌면서 기존 진입 조건 수 1개와 청산 조건 수 0개가 유지됐다. trace `2aa1b47ba503`의 LLM span `meta.model`도 같은 로컬 9B다. 이것은 **인터프리터와 패치 적용 단계**의 확인이며 validation·compiler·실서버 최종 응답까지 통과했다는 뜻은 아니다. 앞으로 직접 재측정할 때는 관찰용 trace의 `inputs.system_prompt`가 아니라 실제 인터프리터의 프롬프트 생성값을 쓰고, 길이 또는 해시를 비교해야 한다.

이어 기존 KR fill 하니스의 `ParsedStrategy`에서 청산 신호와 설명을 비운 초안을 `run_primary_modification`에 넣은 로컬 한 턴은 라운드트립·해석·출처 대조·패치·검증·조립을 통과했다. 최종 응답은 `mode=primary_modify`, `hold_period_days=21`, 진입 신호 1개 보존, 청산 신호 0개, notices·clarification 없음이었다. interpreter span `af5e2f8db38e`의 실제 모델은 같은 로컬 9B다. 따라서 **로컬 9B의 한 한국어 fill 턴은 최종 ParsedStrategy까지 통과**했으나 운영 120B 게이트 및 43개 fill 전수 통과로 세지 않는다.

## 후속 실행 15 — KR fill의 독립 PER 조건 보존 (2026-10-13)

로컬 9B 한국어 fill 전수의 첫 실행은 PASS42·ASK1/43이었다. `per 10 이하인 저평가 종목` trace `886fa3ac8d42`의 1차 LLM 출력에는 근거 있는 `fundamental.per <= 10` 추가와 함께 값이 없는 `fundamental.market_cap <= null` 추가가 있었다. 모델은 질문 필드를 두 번째 조건의 값이 아닌 `universe.market_cap_top_n`으로 적었다. 기존 `primary.run_primary_modification`은 질문 필드가 추가 조건의 배열 인덱스를 가리킬 때만 조건 출처 보조 판정을 호출했으므로, 이 불완전한 조건이 검증까지 내려가 전체 수정이 ASK가 되고 PER도 최종 결과에서 사라졌다. 최초 의미 손실은 **LLM 출력 뒤 primary의 조건 후보 판정 누락과 큰 검증 실패 단위**에 있다. 값이 없는 독립 조건을 채우거나 원문 어휘 규칙을 추가하지 않았다.

Boundary W에서 기존 조건 출처 LLM 대조의 호출 범위만 좁게 늘렸다. 같은 조건 목록에 복수 add가 있을 때 `value=None`인 add도 질문 필드와 무관하게 대조하고, 보조 판정이 명시적으로 `no`인 후보만 제외한다. 판정 실패·불명확은 기존처럼 fail-open이다. 제외 시 `요청에서 확인되지 않은 추가 조건은 반영하지 않았어요.` 안내를 남기고 나머지 PER patch를 적용한다. 질문 필드가 조건 인덱스인 기존 사례와 `universe.market_cap_top_n`인 실측 사례를 한 회귀 테스트로 매개변수화해, 새 사례의 red와 수정 후 green을 확인했다. 관련 테스트 439 passed, 백엔드 전체(원래 제외 4개와 미국 백필 파일 제외) **5,635 passed·5 skipped**였다. 미국 백필 파일의 별도 기존 실패는 이 한국 주식 범위에 포함하지 않았다.

수정 후 동일 입력의 실서버 **캐시 미스 1회**는 `fundamental_filters=[PER<=10]`, 되묻기 없음, 근거 없는 시가총액 조건 없음, 위 안내 1건이었다(trace `934673ac5e83`). 실제 `runtime.interpreter.model_name`과 LLM span의 모델은 `hf.co/unsloth/Qwen3.5-9B-GGUF:Q4_K_M`이다. 이어 한국어 `qa_free_input.py fill` 43건은 **PASS43/43**이었다. 기준 초안 포함 44 root 턴 중 캐시 미스 43, 적중 1(PER 사례), LLM span 52개 모두 같은 로컬 9B였다. 따라서 fill에서 PER의 독립 새 표본은 위 캐시 미스 1회이며 게이트의 적중을 두 번째 LLM 표본으로 세지 않는다. 변경 전 같은 모델의 fill은 PASS42·ASK1, modify는 PASS43/43이었다. 저장된 KR 화면 표시 81/81은 결함 0건이며 이는 새 파싱 81건이 아니다.

이 보수적 수리는 조건이 여러 개 추가되고 한 후보가 불완전할 때만 출처 판정 범위를 늘린다. 보조 LLM이 `no`를 잘못 내거나 불명확하게 내는 표본 변동은 남아 있고, 운영 120B에서 일관된 초안의 월 보유 최초 출력 및 이번 PER 경로는 재측정하지 못했다. 내부 전체 시스템 프롬프트의 OpenRouter 전송은 자동 승인 검토가 차단했으므로 외부 전송을 우회하지 않았다. 커밋·배포·시장 데이터 갱신은 하지 않았다.

추가로 수정 후 한국어 `qa_free_input.py modify` **PASS43/43**을 확인했다. 기준 초안 포함 44 root 턴 모두 캐시 미스, LLM span 52개 모두 같은 로컬 9B였다. 이 게이트의 PER 항목도 새 서버에서 캐시 없이 통과했다. 신규 파싱의 영향 카테고리 `qa_template_detect.py --category 가치투자` **15/15**는 치명·미탐지·종목 수·미대조 수치가 각각 0건이었다. 15 root 턴 모두 캐시 미스, LLM span 37개 모두 로컬 9B였다. 두 하니스 모두 원본은 손대지 않고 `/tmp` 사본으로 실행해 결과 캐시도 `/tmp`에만 기록했다. 새 KR 81개 전수와 운영 120B 게이트는 여전히 미실행이며, 저장된 81개 화면 표시 캐시 대조만 통과한 것이다.

## 후속 실행 16 — 활성 수정 재판정 제거와 한국어 측정 정본 (2026-10-13)

**범위와 최초 손실:** Boundary W에서 primary 수정의 `fast_path_first` 선제 분기와 실패 시 레거시 `parse_modification` 호출을 제거하고, 설정값은 `llm_first`로 정규화했다. 종전에는 이 분기가 사용자 원문을 `_modify_rule_based`의 정규식으로 다시 해석했다. `main.py`의 수정 후 `resolve_coach_context_risk` 호출도 제거했다. 이 호출은 LLM 패치 적용 뒤 사용자 입력과 이전 코치 문장을 정규식으로 읽어 위험 값을 덮어썼다. 이제 되묻기 질문이 없는 경우에만 직전 코치 문구를 수정 인터프리터의 참고 문맥으로 전달한다. `pending_question`이 있으면 그 질문이 우선한다. 코치 문맥 값은 LLM 패치·출처 검증·병합을 거친다. 수정 이전의 레거시 함수 자체와 primary 인용 어휘 재판정, 프론트 중재기의 원문 판정은 별도 부채로 남는다.

**측정:** 격리한 로컬 서버의 실제 interpreter/LLM span 모델은 모두 `hf.co/unsloth/Qwen3.5-9B-GGUF:Q4_K_M`였다. 한국어 `qa_free_input.py modify`는 PASS 43/43(기준 초안 포함 44 root, 전부 cache miss, LLM span 52), `fill`은 PASS 43/43(44 root 중 cache miss 43·hit 1, LLM span 51)이었다. 직전 코치 질문을 손절 변경으로 둔 합성 초안의 `8%`·`8퍼센트`·`8프로` 3회는 모두 cache miss였고 손절 6→8%, 익절 30% 불변, 되묻기 없음이었다(각 1 LLM span, 동일 모델). 이 결과는 로컬 9B 한국어 수정·답변 레인의 증거이며 운영 120B 첫 해석의 증거가 아니다.

**QA 기준 변경:** `scripts/qa_template_detect.py`가 한국어 예시 원문을 정규식으로 읽어 값 기대치를 생성하던 경로를 없앴다. 81개 예시의 사람이 검토한 의미 기대값을 `scripts/qa_template_expectations.json`에 고정하고, 예문이 바뀐 채 제목만 유지돼 오래된 기대값이 적용되는 경우를 재현 테스트로 먼저 확인했다. 각 예문의 SHA-256을 대조해 정답표 재검토 없이는 게이트가 시작되지 않게 했다. 미국 예시의 정답표는 아직 없어서 `--source us` 게이트는 명시 중단한다. 저장된 과거 한국어 81개 캐시의 새 기준 판정은 치명 2·미탐지 1이었다: 20번 보유 10거래일 소실·미지원 안내, 50번 볼린저 방향 오류, 11번 거래량 미탐지. 새 LLM 파싱 81건을 실행한 결과가 아니다.

**검증 한계:** 관련 백엔드 6개 테스트 파일은 최종 506 passed, 프론트 전체 2,398 passed·1 skipped, 저장된 한국어 화면 표시 81/81 결함 0, `git diff --check` 통과. 지정 백엔드 전체 명령은 KRX 사이트 DNS 오류가 난 두 파일의 수집 단계에서 중단됐다. 그 둘과 미국 백필 파일을 제외한 실행은 `test_modify_rag`의 임베더 초기화가 장시간 정체돼 중단했고, 이를 추가로 제외한 실행도 로컬 PostgreSQL `Operation not permitted`로 해석과 무관한 테스트의 setup 오류가 발생해 중단했다. 어느 중단도 전체 통과로 세지 않는다. 120B의 월 보유 기간 첫 해석 재표본은 전체 내부 프롬프트 외부 전송에 대한 자동 승인 검토 차단으로 수행하지 않았다. 커밋·배포·시장 데이터 갱신은 하지 않았다.

## 후속 실행 17 — 운영 120B 첫 해석 재표본과 fill 질문 정본 (2026-10-13)

**원인 대조:** 내부 전체 시스템 프롬프트의 OpenRouter 전송을 사용자가 명시 승인한 뒤, 같은 합성 초안과 `한 달 지나면 정리`를 운영 `nvidia/nemotron-3-super-120b-a12b:free`로 다시 측정했다. `qa_free_input.py`의 옛 fill 질문 `청산 조건이 빠져 있습니다. 어떤 조건에서 청산할까요?`에서는 최초 출력이 3/3 MA 데드크로스 추가로 틀렸다. 질문 없이 보내면 3/3 보유 기간 21거래일 patch만 나왔다. 실제 UI 질문 `이제 언제 매도할지 정해볼까요?`에서는 3/3 최초 출력이 보유 기간 21거래일 patch만 냈다. 질문 문구를 빼거나 범용 의미 우선 문장을 넣는 임시 후보도 각각 2/3·3/3 실패해 제품 프롬프트에는 반영하지 않았다. 옛 QA 질문으로 생긴 오류를 현재 UI의 최초 해석 오류라고 일반화할 수 없으며, 질문 문맥이 의미를 흔들 수 있다는 위험은 남는다. 모든 직접 호출은 전체 프롬프트, 캐시 없음, 실제 120B LLM span으로 확인했다.

**최소 수정:** 기존 `qa_free_input.py`의 fill 질문 8칸 중 UI 정본 `app/analytics/new/__fixtures__/slot-prompts.json`과 달랐던 5칸(entry, exit, rebalancing, stop_loss, take_profit)을 정본 문장에 맞췄다. 이 불일치를 먼저 실패로 재현한 뒤, 기존 `test_strategy_conversation.py`에 질문 문구 일치 회귀 테스트를 추가해 통과시켰다. 제품 해석기·프롬프트·검증·패치 병합 코드는 이번 실행에서 바꾸지 않았다.

**운영 게이트:** 캐시를 비운 독립 서버에서 한국어 fill 43/43, modify 43/43을 통과했다. 각 게이트의 기준 초안 1턴+검사 43턴은 모두 cache miss였고, Interpreter span의 model은 전부 `nvidia/nemotron-3-super-120b-a12b:free`였다. LLM span은 fill 50개·modify 50개로 모두 같은 120B였다. 두 게이트의 `한 달 지나면 정리`는 최종 `hold_period_days=21`이었다. 질문 정본 변경 뒤 기존 전략 대화 테스트 382개가 통과했다. 미국 경로 게이트는 사용자가 범위에서 제외해 실행하지 않았다.

**백엔드 전체 검증:** 지정 명령은 90% 지점의 `test_sync_data_status.py`가 외부 DART 알림 HTTP 응답에서 정체돼 중단했다. 중단 전 `test_backfill_us_stocks.py::test_columns_match_korean_schema`의 기존 미국 스키마 실패 1건이 있었다. 외부 동기화 2개 파일과 미국 백필을 제외한 재실행은 **5,628 passed·5 skipped·1 failed**였다. 유일한 실패 `test_delisted_stock_names.py::test_sync_passes_the_removed_stock_name`는 해석과 무관한 `from scripts import sync_data` ImportError였다. 따라서 전체 통과로 표기하지 않는다. KR 81개 신규 파싱은 별도 실행해 아래에 기록한다.

## 후속 실행 18 — 한국 81개 새 파싱과 최초 의미 손실 수리 (2026-10-13)

**새 기준선:** 캐시를 비운 운영 120B 한국 81개 예시 게이트는 치명 1·미탐지 2·종목 수 0·미대조 수치 0이었다. 과거 캐시의 볼린저 방향 오류는 이번 출력에서 재현되지 않았다. 남은 세 항목의 최초 손실은 모두 LLM 원출력에서 확인했다. 예시 20의 `진입 후 10거래일 경과`는 `portfolio.hold_period_days`가 아닌 미지원 `concept.time_based_exit` 조건으로 3/3 나왔다(한 번은 `portfolio.hold_period_days`를 조건 factor로 출력). 예시 11의 정성적 거래량은 3/3 값 없는 `fundamental.trading_value`로 나왔다. 예시 25의 정성적 60일 수익률은 3회 중 2회 `technical.relative_return > 0` 진입 필터, 1회 `ranking.return(60일)`로 흔들렸다. 이 재표본은 모두 전체 프롬프트의 운영 `nvidia/nemotron-3-super-120b-a12b:free`였으며 로컬 9B 결과가 아니다.

**가장 싼 레이어의 수리:** 새 전략에서 정본 등록에 없는 청산 조건 하나가 입력 속 짧은 인용을 가질 때만 기존 `holding_period_check.recover_misfiled_holding_period`의 LLM 판정을 재사용한다. 수량·단위·인용이 일치하고 보유 칸이 비었을 때 조건을 옮겨 놓고 안내하며, 원래의 다른 청산 조건은 보존한다. 판정 없음은 기존 미지원 결과를 유지한다. 거래대금 비교 보조 판정은 `volume`을 별도 enum으로 받는다. 생성 턴에서만 거래량으로 판정된 잘못된 금액 조건을 제외하고 사용자에게 미반영 안내를 남긴다. 절대 거래량 임계 지표나 값을 새로 만들지 않는다. 유동성 미지원 회수 단계를 거래대금·거래량 대조 **앞**에 두어 제거한 조건이 다시 거래대금으로 생기지 않게 했다. 통합 보조 호출의 거래대금 응답이 `unclear`이면 해당 검사만 기존 단독 LLM 판정으로 재시도한다. 단독 120B는 거래량을 3/3 `volume`으로 판정했지만 통합 응답은 `unclear`로 바뀐 실측을 반영했다. 수정 턴의 거래량 조건은 패치 원자성을 해칠 수 있어 이번 생성 전용 제외 경로에 넣지 않았다.

**전후:** 최종 primary 레인을 캐시 없이 운영 120B로 각 3회 재표본했을 때, 예시 20은 3/3 최대 보유 10거래일로 반영하고 다른 20일선 청산을 보존했다. 예시 11은 3/3 거래대금 조건·거래대금 값 질문 없이 잘못된 대체를 안내했다. 모멘텀 17개+기술분석 16개 영향 카테고리 새 게이트는 **치명 0·미탐지 0·종목 수 0·미대조 수치 0**이었다. 33개 모두 cache miss, Interpreter span 33개와 LLM span 108개 모두 운영 120B였다. 생성 보유 기간·거래량 배치·질문 인덱스·단독 재검사 회귀는 각각 수정 전 실패와 수정 후 통과를 확인했다. 제품 메인 프롬프트 v8.13과 스키마·DSL·엔진은 바꾸지 않았다.

**남은 범위(후속 실행 19 전 상태):** 예시 25는 `수익률이 양호한`의 수치 기준과 `상위 10종목`의 정렬 기준을 사용자가 특정하지 않아, 무조건 랭킹이나 임계값으로 정하는 것은 계약 §5의 값 생성 금지와 충돌할 수 있다. 81개 게이트의 이 미탐지는 현재 수리하지 않았고, 정성적 표현의 되묻기·순위 선택 계약을 별도로 정해야 한다. 이 시점에는 한국 81개 **수정 후 전수**와 미국 경로를 실행하지 않았다. 영향 카테고리 33개만 수정 후 새로 측정했다. 커밋·배포·시장 데이터 갱신은 하지 않았다.

**최종 테스트:** 생성 조건·단독 재검사 관련 백엔드 테스트를 수정 전 실패로 재현한 뒤 수정 후 통과시켰다. 지정 백엔드 전체 명령은 위 후속 실행 17의 외부 DART 대기 때문에 완료되지 않았고, 무관한 미국 백필·외부 동기화·`scripts.sync_data` import 실패 파일을 제외한 한국 범위 전체 재실행은 **5,622 passed·5 skipped**였다. 프론트 전체 `npm run test:frontend`는 **2,398 passed·1 skipped**였다. `QA_DISPLAY_SWEEP=1 npx vitest run scripts/qa_kr_display_sweep.test.ts`는 저장된 표시 캐시 81/81에서 결함 0건이었다(새 LLM 파싱 아님). 내 변경 경로의 `git diff --check`는 통과했다. 작업트리 전체의 같은 명령은 다른 세션이 수정 중인 `.claude/skills/x-backtest-post/references/myth_series.md`의 후행 공백 때문에 실패했으며 그 파일은 손대지 않았다.

## 후속 실행 19 — 반대 역할 이동평균 조건 환각과 인용 대조 보강 (2026-10-13)

**수정 후 한국 81개 전수:** 새 서버·캐시 미스 81건, 운영 `nvidia/nemotron-3-super-120b-a12b:free` LLM span 291개에서 치명 0·미탐지 1·종목 수 0·미대조 수치 0이었다. 유일한 미탐지는 예시 25의 정성적 수익률/랭킹 경계다. 이 전수는 아래 인용 대조 보강 **전** 결과다. 실행 기록은 `/tmp/simons-120b-final81-gate-20261013.log`, `/tmp/simons-120b-final81-report-20261013.md`다. 전후 ParsedStrategy 최상위 비교에서 보유 기간 1건이 의도대로 10일로 채워졌고, 매수 신호 3건 등에는 표본 간 차이가 있었다. 모든 차이를 수정 인과로 단정하지 않는다.

**추가로 발견한 회귀:** 복합전략 예시 `멀티팩터(퀄리티+모멘텀+밸류) 결합`은 `20일선 이탈 시 청산`만 요청했는데 120B 첫 출력이 존재하지 않는 `20일선 위에 있는 동안`을 인용으로 단 이동평균 매수 조건까지 만들었다. 인용이 원문과 `20일선` 네 글자를 공유해 느슨한 표기 에코 검사를 통과했고, 통합 인용 대조 LLM도 `yes/moving_average`로 답했다. 따라서 원문↔인용의 부분 표기 대조가 역할 반전의 근거가 된 것이 아니라, **거짓 인용을 검출할 기회를 놓친 것**이다. 생성 위치는 후처리 이전 Interpreter 첫 JSON이다(트레이스 `d0ae4da3747c`). 81개 게이트의 존재 위주 기대값은 이 **불필요한 추가 조건**을 치명으로 세지 않았다.

**좁은 수리:** 기존 `quote_check.check_quotes`의 '원문에 그대로 없는 인용 + 반대 역할에 같은 정본 지표가 있는 조건' 독립 LLM 재확인을 매도 후보뿐 아니라 매수 후보에도 적용했다. 인용을 후보 질문에서 빼고 **원문과 조건 역할**만 두 차례 묻는다. 둘 다 `no`일 때만 제거하며 불일치·형식 오류·호출 실패는 조건을 보존한다. 실제 인용이 그대로 있는 정상 매수·매도 쌍에는 추가 호출이 없다. 원문 어휘 정규식이나 새 파서·지표별 예외는 만들지 않았다. 보조 판정 프롬프트만 바뀌었고 메인 인터프리터 v8.13은 그대로다. 조작 매수/정상 청산 쌍의 운영 120B 직접 표본은 3/3에서 각각 `no/other`와 `yes/moving_average`였으며 총 9회 호출, 로컬 9B 0회였다. `test_quote_check.py`에서 기존 동작 실패를 먼저 확인했고, 통합 판정 경로와 정상 리터럴 인용을 포함한 회귀 20건이 통과했다.

**게이트 한계:** 기술분석 16+복합전략 18=34개 새 파싱을 시작했지만 23개 완료 후 OpenRouter 429가 발생해 중단했다. 완료된 23건은 캐시 미스였고 성공한 LLM 응답 82개는 모두 운영 120B였다. 23개 저장 응답의 기존 의미 정답표 오프라인 판정은 치명 0·미탐지 1(같은 예시 25)이었다. 24~34번은 **미실행**이며 34개 게이트 통과로 쓰지 않는다. 전체 81개 전수와 화면 표시 스윕은 위 보강 이후 재실행하지 않았다. LLM 한도 초기화 뒤 새 34개 또는 81개 검증이 필요하다.

**테스트·범위:** 지정 백엔드 전체 명령의 무관한 외부 DART 대기·미국 백필·`scripts.sync_data` 문제는 여전하다. 해당 외부/미국 파일을 제외하고 권한을 바로잡아 재실행한 한국 범위 백엔드는 **5,627 passed·5 skipped**였다. 프론트는 후속 실행 18의 **2,398 passed·1 skipped** 이후 제품 프론트 코드를 다시 수정하지 않았다. 이 후속 실행의 제품 변경은 Boundary W의 `interpreter/quote_check.py`, `backend/tests/test_quote_check.py` 두 파일이다. 문서는 별도 Boundary G로 반영한다. 남은 미해결: 예시 25의 정성적 기준 정책, 수정 턴 거래량 패치 원자성, 미국 경로(사용자 지정 범위 밖), 운영 120B 보강 후 전수 게이트. 커밋·배포·시장 데이터 갱신 없음.

## 후속 실행 20 — 정성적 수익률과 수정 거래량 오분류 (2026-10-13)

**최초 손실:** 예시 25의 운영 120B 첫 JSON은 `최근 60거래일 수익률도 양호한`을 `technical.relative_return > 0`으로 확정했다(기존 3회 중 2회, 나머지 1회는 기간 수익률 랭킹). 원문에는 시장 대비 비교나 0% 기준이 없다. 이는 하류 조건 삭제가 아니라 최초 의미 판정 오류다. 수정 턴에서는 `최근 거래량도 너무 적지 않은`을 값 없는 `fundamental.trading_value` add로 낸 뒤 보조 판정이 `volume`을 답해도, 생성 전용 가드가 수정 조건을 남겼다. 그 금액 기준 되묻기가 독립적인 종목 수 패치를 막거나, 잘못된 add와 짝인 remove가 기존 조건을 없앨 수 있었다.

**Boundary W 수리:** 첫째, `technical.relative_return > 0`의 인용이 있는 조건만 전용 LLM 대조에 보낸다. 응답 enum은 명시적 시장 초과수익, 절대/상대 수익률 상위 선정, 임계값 없는 정성적 절대/상대 수익률, 불명확이다. 인용을 정확히 복사한 유효 판정에서만 조건을 유지하거나 랭킹으로 옮기거나 절대 ROC/상대수익률의 값 대기 조건으로 바꾼다. 정성적 조건의 임계값을 만들지 않고 검증기의 질문을 낸다. 일반적인 `상위 N종목`만으로 특정 수익률 랭킹을 확정하지 않도록 대조기에 명시했다. 판정 실패·불명확은 기존 출력 유지다. 메인 프롬프트·스키마·지표 정의는 바꾸지 않았다. 둘째, 수정 턴의 새 거래대금 조건이 `volume` 판정을 받으면 조건과 해당 add patch를 함께 제외하고 인용 안내를 남긴다. 같은 목록의 기존 조건 remove/replace도 원자적으로 보류한 다음 원본 초안에 남은 독립 패치를 다시 적용한다. 수정 초안에서 기존 조건 및 무관 필드를 보존한다.

**재현·검증:** 고정 Interpreter JSON과 보조 판정 스텁으로 수익률 정성 조건, 명시적 상대수익률 보존, 수익률 순위 이동, 인용 없는 판정 거부, 거래량 add+종목 수, 거래량 교체+기존 조건, 거래량 교체+독립 종목 수를 재현했다. 새 테스트는 수정 전 실패를 확인했고, 전략 대화 파일 **392 passed**. 운영 120B 새 재표본과 해석 결과 게이트는 OpenRouter 429/09:00 KST 초기화 전이라 **미실행**이다. 따라서 이번 수리가 운영 모델에서 예시 25를 실제로 회복했다고 주장하지 않는다. `components/admin/AgentsTab.tsx`의 흐름 설명에도 두 보조 판정과 수정 패치 보류를 반영했고, 프론트 전체 테스트를 그 변경 후 다시 통과시켰다.

**전체 검증:** 한국 범위 백엔드(외부 DART 대기·기존 미국 백필·`scripts.sync_data` import 문제가 있는 파일 제외)는 로컬 DB 연결 허용 환경에서 **5,633 passed·5 skipped**였다. 기본 샌드박스 실행은 PostgreSQL `Operation not permitted`로 33건 뒤 중단됐고, 같은 범위를 연결 허용 환경에서 재실행해 통과했다. 프론트 전체는 **2,412 passed·1 skipped**다. 저장 캐시를 표시한 KR 81개 스윕은 **80/81 무결, 1건 실패**: 기존 `박스권 상단 돌파 따라가기` 캐시의 검증 안내에 `crosses_below/crosses_above` 원시 enum이 노출됐다. 이 캐시는 이번 새 LLM 출력이 아니며, 수익률·거래량 수리의 인과 증거로 쓰지 않는다. 표시 실패도 합격으로 보고하지 않는다. 운영 120B 영향 카테고리/전수 파싱은 OpenRouter 한도 때문에 미실행, 미국 경로는 사용자 지정 범위 밖이다. 커밋·배포·시장 데이터 갱신 없음.

## 후속 실행 21 — 검증 안내의 교차 연산자 표시 (2026-10-13)

**증상과 경계:** 한국 예시 81개 저장 캐시의 `박스권 상단 돌파 따라가기` 안내가 `crosses_below/crosses_above`를 사용자에게 그대로 보였다. 생성 지점은 `validation/capability_validator.py`의 허용 연산자 오류 문구다. 기존 Boundary W는 이 파일을 허용하지 않아 먼저 별도 Boundary G에서 오류 안내 문구만 대상으로 파일 범위를 좁게 추가한 뒤, Boundary W에서 코드와 회귀 테스트를 수정했다.

**수정:** 검증기의 지원/거부 판정과 조건 목록은 그대로 두고, 사용자 안내의 교차 enum만 `상향 돌파`·`하향 돌파`로 표기한다. 허용 목록과 역할 방향 오류도 같은 표기를 쓴다. 알 수 없는 연산자는 내부 문자열 대신 `선택한 연산자`로 나타낸다. 기존 오류 안내의 `연산자` 용어는 유지한다. 고정 출력에서 검증 오류와 최종 primary `notices` 양쪽에 내부 enum이 없는지 확인한다. 테스트를 먼저 실패시켰고 수정 뒤 관련 테스트 3건과 전략 대화 파일 **394건**이 통과했다. 전체 회귀 첫 실행은 기존 테스트가 `연산자` 문구를 기대해 4,579건 뒤 실패했으므로 문구를 복원하고 재실행했다.

**게이트 해석:** 프론트 전체는 **2,412 passed·1 skipped**였다. `QA_DISPLAY_SWEEP=1`은 수정 뒤에도 **80/81, 1건 실패**다. 이 스윕은 백엔드를 다시 호출하지 않고 수정 전 저장 캐시의 옛 안내를 읽는다. 캐시를 손으로 고쳐 합격 처리하지 않았다. 새 응답의 결정론 재생은 통과했으며, 운영 120B로 예시를 새 파싱하고 캐시를 갱신한 표시 스윕은 OpenRouter 429 한도 회복 뒤 필요하다. 미국 경로는 사용자 범위 밖, 커밋·배포·시장 데이터 갱신 없음.

**최종 검증:** 오류가 나온 운영 120B 트레이스 `4726079d9262`의 저장된 Interpreter 출력(`technical.breakout crosses_below` 청산)을 현재 `run_validation`에 오프라인 재생했다. 기존처럼 오류는 1건이고 안내는 `하향 돌파`·`상향 돌파`를 사용하며 내부 enum은 0건이었다. 트레이스의 실측 모델은 `nvidia/nemotron-3-super-120b-a12b:free`지만 **새 모델 호출은 0회**다. 최종 한국 범위 백엔드 회귀(기존 외부 DART 대기·미국 백필·`scripts.sync_data` 오류 파일 제외)는 로컬 PostgreSQL 접근 환경에서 **5,635 passed·5 skipped**. 이 수치는 fresh 120B 파싱 81개 게이트 통과를 뜻하지 않는다.
