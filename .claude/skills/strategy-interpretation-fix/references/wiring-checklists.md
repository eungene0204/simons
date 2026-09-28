# 배선 체크리스트

새 개념을 해석 경로에 올릴 때 **실측으로 드러난 접점** 목록이다. 빠진 접점은 테스트로 잡히는 것도 있지만
(패리티·신선도·i18n·온톨로지 분류 테스트), 대부분은 "값은 들어갔는데 화면에 없음"이나 "엉뚱한 되묻기"로
사용자가 먼저 발견한다. 시작하기 전에 해당 목록을 할 일 목록으로 옮기고 하나씩 지운다.

작업 중에 목록에 없는 접점을 새로 발견하면 이 파일에 추가한다.

## 목차
1. 새 재무 지표 · 2. 새 랭킹 지표·랭킹 파라미터 · 3. 새 유니버스 칸 · 4. 새 ParsedStrategy 필드(공통)
5. 새 되묻기 질문·칩 · 6. 새 결과 경고·매매 사유 · 7. 새 전략 유형 · 8. 새 인터프리터 칸(프롬프트) · 9. 새 전용 판정 패스

---

## 1. 새 재무 지표 (v16.15 실측, ≈13곳)

먼저 **재료가 있는지 확인**한다. `data/ohlcv/005930.parquet` 등의 컬럼 non-null 수를 센다. 재료가 있으면 백필이나 DATA_PENDING 없이
`data_resolver`에서 런타임 계산으로 켤 수 있다.

1. `backend/engine/signals.py` `FUNDAMENTAL_LABELS` (parquet 컬럼명·배지)
2. `backend/engine/nl_parser.py`: `FundamentalFilter.metric` Literal + description, `RankingComponentMetricLiteral`, 라벨 dict, `_FUNDAMENTAL_METRIC_ALIASES`
3. `backend/engine/parse_validator.py` 레거시 프롬프트 목록
4. `backend/strategy_conversation/registry/indicator_registry.py` `_fundamental(...)` + `_ALIASES` (기존에 `_unsupported`였다면 제거하고 별칭 재지정)
5. `data/indicator-ontology.json` class 소속 + polarity — **인터프리터 프롬프트 어휘가 여기서 생성되므로 프롬프트가 바뀐다**(→ 게이트 대상). 빠지면 `test_every_spec_classified_exactly_once`가 실패한다.
6. `backend/strategy_conversation/registry/display_labels.py` 영어 라벨
7. `lib/strategy-summary.ts` + `strategy-summary.labels.test.ts` 목록
8. `lib/i18n/en.ts` 라벨 + 칩 문구
9. `data/fundamental-factors.json` (프론트·레거시 빌더 공유 — **원문 정규식 패턴은 추가하지 않는다**)
10. `scripts/export_clarification_chips.py` 재실행 + 단위 map
11. 백필 쪽(재료를 새로 수집할 때만): `FUND_COLS`, `resync_kis_adjusted._CLOSE_DERIVED_COLS`, 시총 파생이면 `rebuild_market_cap.py` — **백필은 프로덕션에서 `merge_fundamentals`(빈 칸만 채움)로만**
12. `backend/engine/version.py` MINOR
13. 런타임 폴백: `data_resolver._resolve_computable_ratios` / `_resolve_dividend_metrics`

## 2. 새 랭킹 지표·랭킹 파라미터 (v16.17·v16.19 실측, ≈15곳)

- `backend/schemas.py` — **선언하지 않으면 model_dump가 조용히 버린다**
- `nl_parser` ParsedStrategy + `RankingMetricLiteral`
- `engine/strategy_converter.py` 정본 DSL + 요청 두 곳
- `strategy_conversation/interpreter/models.py` `RankingSpec`
- compiler / decompiler(`_canonical_ranking_id`)
- parameter / completeness / capability validator
- registry + aliases, `display_labels`, `indicator-ontology.json`(members + polarity)
- `engine/trade_reason.py` 템플릿 + `en.ts` (`tests/trade-reason-i18n.test.ts`가 잡는다)
- `lib/strategy-summary.ts` (타입·라벨·risk 매핑)
- `scripts/export_slot_judgments.py` 재실행
- `scripts/qa_backtest_equivalence.py` 픽스처
- 새 파라미터 이름을 지표가 읽으면 `engine/prep_cache.py` `STRUCTURAL_PARAM_KEYS` (`tests/test_prep_cache.py`가 강제한다)
- **안내 레인 표**: 합성 시그널이면 `indicator_registry.RANKING_INGREDIENTS`·`_RANKING_BUILT_IN_PROCESSING`. 빠지면 회수 패스와 미지원 안내가 반영된 구절을 다시 끄집어낸다.
- 되묻기 계약을 정한다: 값이 없을 때 되묻기인지 고정 기본값인지(사용자 결정). `strategy.ranking[i].lookback_days` 질문에 붙는 '수익률 산정 기간' 칩을 받을지 예외로 뺄지도 정한다.
- `engine/version.py`

## 3. 새 유니버스 칸 (v16.19·v16.32 실측)

- `response/provenance.py` `explicit_fields_from_spec` 유니버스 목록 — 빠지면 사용자가 유니버스를 말했는데도 시장 질문이 나간다.
- compiler 기본 시장: 시장을 말하지 않았을 때의 기본값과 상호작용을 확인한다(KOSPI200 기본 × 상위 N → 201종목이 된 사례).
- 요약 카드 **두 곳**(요약 카드·진행 카드): 포매터를 정의만 하고 호출하지 않은 사례가 있었다.
- `condition_recall._UNIVERSE_FIELD_TWINS` — 인용이 없는 유니버스 칸은 '이미 쓰인 근거' 대조에 걸리지 않아 조건으로 되살아난다.
- 모르는 값 처리(fail-open / fail-closed)는 데이터 커버리지를 실측해서 정한다(적자 제외=fail-open: 상폐 종목 재무 커버리지가 1%라서).
- 판정 정본은 `engine/universe_prefilters.py`

## 4. 새 ParsedStrategy 필드 (공통)

- `python scripts/export_slot_judgments.py` — 안 하면 `test_frontend_parity_fixture_is_current`가 실패한다.
- 요청·해시: 기본값일 때 요청에서 빠지도록(`exclude_none`, 기본이면 생략) 한다. **기존 전략의 해시·요청이 바뀌면 안 된다.**
- 결과 매퍼: DTO 새 필드는 4곳 전부 배선한다(project_backtest_result_mapper_four_points).
- 레거시 패치 레인 `ParsedStrategyDiff` 반영 여부를 확인한다.
- 인터프리터 모델(느슨)과 ParsedStrategy(엄격) 제약이 다르면 capability_validator에서 먼저 거른다(C 유형 예방).

## 5. 새 되묻기 질문·칩

- 질문 문구는 **상수**로 뺀다(전용 답변 판정이 문장 동일성으로 라우팅한다 — A 유형).
- `guard_text(q) == q` 테스트 — 규제 가드가 '분할 매수' 같은 문구를 문장째 지운다.
- 값 대기 채널: 값이 확정되기 전에는 엔진에 보내지 않는다(`is_complete()` 패턴). 안내에는 내부 라벨 대신 사용자 인용(source_text)을 쓴다.
- 칩: 결정론 정본 값 표(`strategy_slots.*_CHIP_VALUES`, 프론트 옵션 표)로 **값 결속**한다. 복합 칩은 금지다. 문구는
  `export_slot_prompts.py` / `export_clarification_chips.py` 픽스처로 공유한다.
- 골격 밖의 값 대기를 물으려면 백엔드 main 게이트와 프론트 `getNextMissingBacktestCondition` 양쪽에 넣는다(Q 유형).
- 되묻기 답이 일반 수정 LLM의 귀속에 의존하면 전용 답변 판정을 붙인다.

## 6. 새 결과 경고·매매 사유

- 경고는 `engine/result_warnings.py` 세그먼트(템플릿+인자)로 만든다. f-string 완성 문장은 게이트가 금지한다.
- `lib/i18n/en.ts`에 원문 키 번역을 넣는다(`tests/result-warnings-i18n.test.ts`, `tests/trade-reason-i18n.test.ts`).
- 다른 모드의 문구를 재사용할 때는 뜻이 맞는지 본다(납입 방식의 "다음 회차에 합쳐 매수"를 현금 풀에 쓰면 거짓이 된다).

## 7. 새 전략 유형 (적립식처럼 '매수 조건 없이 사는' 유형)

- '매수 기준 있음' 판정 사본 3곳을 함께 고친다: 되묻기 게이트 `isSlotFilled`, 실행 핸들러 `hasBuyCriteria`(`lib/strategy-summary.ts`),
  검증 agent `backend/ai/strategy_validation_agent.py`. 하나라도 빠지면 '백테스트 시작'이 빌더를 재시작하거나 "진입 조건을 입력해 주세요"가 나온다.
- `has_<유형>` 판정을 백엔드·프론트 쌍으로 두고 슬롯 픽스처를 재생성한다.
- completeness가 이 유형에 맞지 않는 질문(청산 규칙 등)을 하지 않게 한다.
- 해석은 덧대는 판정 N개가 아니라 **전용 판정 하나 + 일반 보정의 명시적 가드**로 한다(적립식 재설계 09-22).

## 8. 새 인터프리터 칸 (메인 프롬프트)

- `_OUTPUT_SHAPE`에 키를 추가한다. 목록 항목이면 **모든 예시 항목**에 넣는다.
- 규칙은 1줄로 쓴다. 기존 예시 중 반대로 가르치는 문장이 있는지 찾는다.
- 모델(`interpreter/models.py`) → compiler → decompiler → validator들 → 수정 턴 초안(`_draft_for_interpreter`)에 노출할지 결정한다.
- `PROMPT_VERSION`을 올린다. 되묻기 하니스 modify/fill 전후를 대조한다. 예시 게이트를 돌린다.
- 인터프리터가 모르는 칸(전용 판정이 채우는 칸)은 형태와 수정 초안 **둘 다**에서 가린다.

## 9. 새 전용 판정 패스 (`interpreter/<이름>_check.py`)

- 입력은 LLM 출력(조건·인용 조각)이다. 사용자 원문 전체를 다시 해석시키지 않는다.
- 출력은 enum 또는 옮겨 적기(말한 표기 그대로)로 받는다. 환산은 결정론 코드가 한다.
- 실패·unclear이면 판정 없음(fail-open)으로 둔다. 제거·뒤집기는 가장 좁은 판정에서만 한다(quote_check: no+other).
- 발동 조건(applies_to)이 1차 해석의 한 칸에 걸려 있으면 그 칸이 빠질 때의 회수 그물을 함께 설계한다.
  새 칸을 **만드는** 회수는 엄격한 출처 대조(인용 전체 포함 + 수치 표기 포함)를 쓴다. 4자 조각 에코는 금지다.
- 같은 턴의 다른 판정과 `check_batch.py`로 묶을 수 있는지 본다(호출 수 절감).
- 트레이스 span 이름을 붙인다(`span("<Name> · <설명>", "chain")`). 구조가 바뀌면 `components/admin/AgentsTab.tsx`도 갱신한다.
