# 해석 실패 유형별 사고 이력

SKILL.md 2단계 표의 기호별 상세. 각 절은 **식별 신호 → 실제 원인 → 통한 수리 → 기각된 수리** 순서다.
괄호 안 파일명은 메모리(`~/.claude/projects/-Users-eugene-nullalgo-simons/memory/`)의 원본 기록이다.
새 사고가 기존 유형에 맞으면 해당 절에 한 줄 덧붙이고, 맞지 않으면 절을 새로 만든다.

## 목차
- L 레인 문제 · B 빈 라벨/붕괴 출력 · C 조립 예외 · R 수리 턴 목록 소실 · N 거짓 안내
- S 칸 오배정/누락 · E 엔진 부재 · A 되묻기 답 미반영 · Q 되묻기 사라짐 · F 프론트 덮어쓰기

---

## L — 레인 문제(코드 결함이 아님)

- **신호**: LLM span model이 120B가 아니거나 `provider=None`이다. 같은 입력인데 input_tokens가 다르다.
  "해석 안 됨"이 한 시간대에 몰린다. 9B는 복합 전략에서 257초가 걸려 프록시 타임아웃이 난다.
- **원인**: OpenRouter 무료 한도가 소진되어(09:00 KST 초기화) 9B로 조용히 폴백했거나, 상류 502, 또는 로컬 Ollama 미기동
  (`curl localhost:11434/api/tags` 000).
- **대응**: 먼저 레인부터 복구하고 다시 잰다. 9B에서만 나는 결함은 따로 적어 두고 "운영 레인 결과"로 보고하지 않는다.
  한도 확인은 1토큰 요청을 보내 429의 `X-RateLimit-Reset`을 보면 된다.
  (project_llm_lane_quota_exhaustion_9b_fallback.md, project_llm_down_looks_like_parse_regression.md)

## B — 빈 라벨·붕괴 출력

- **신호**: Interpreter의 LLM 출력이 ≈11토큰(`{"intent":"UNSUPPORTED_REQUEST"}`)이다. 화면에는 "해석하지 못했어요"가 뜬다.
- **원인**: 미지원 개념이 많은 서술이 들어오면 120B가 라벨만 낸다. "미지원이어도 CREATE_STRATEGY"라는 프롬프트 규칙이 이미 있는데도 그랬다.
- **통한 수리**: 이것을 형식 위반으로 판정하고(`output_repair.is_bare_unsupported_request`) 오류를 LLM에 되돌려
  1회 재생성한다. 재생성 오류 문구에 "옮길 수 있는 표현은 필드에"를 넣어야 한다. "무엇이 미지원인지 적어라"만 주면
  여섯 문장을 통째로 미지원으로 보내고 주기·비중·체결·수수료까지 버린다.
- **같은 계열**: 입력 전체를 인용하는 경우(`whole_input_quote_fields`), 금액 표현을 거래대금 조건으로 지어내는 경우(`misfiled_trading_value_fields`).
- **기각**: 규칙 줄 추가만으로는 빈 라벨이 없어지지 않았다. (project_bare_unsupported_request_regeneration.md)

## C — 조립(compile) 예외

- **신호**: `Tool · compile_strategy ❌ ValidationError`가 난다. 그런데 해석 결과를 보면 사용자 뜻대로 칸이 다 차 있다.
- **원인**: 인터프리터 모델은 느슨하고 ParsedStrategy는 엄격하다(gt/lt). LLM이 범위 밖 값을 내면 되묻기가 아니라
  **요청 전체가 해석 실패**가 된다. 예: '+100% 전량 매도'가 `partial_take_profits {100,100}`로 들어왔는데 `sell_pct`는 lt=100이다.
- **통한 수리**: 끝값에 뜻이 있으면 모델 validator로 정규화한다(매도 100% → take_profit으로 이동, 0% → 제거).
  뜻이 없는 범위 위반은 capability_validator에서 오류로 잡고 그 조건만 제외한 뒤 안내한다.
- **예방**: 새 스펙 칸을 만들 때 ParsedStrategy 제약 범위를 capability_validator에 **먼저** 옮긴다. (project_tranche_ladder_v16_36.md)

### C' — 전략 검증 패널의 화이트리스트 드리프트("지원하지 않는 필드")

- **신호**: `compile_strategy`는 예외 없이 통과했는데(`gate: "ok"`), 확정 후 "전략 검증" 패널에 "현재 시스템에서
  지원하지 않는 필드입니다"가 뜬다. 채팅 에이전트 트레이스(`agent_traces/*.jsonl`)에는 이 턴이 아예 안 잡힌다 —
  `/api/strategy/compile`·`/api/strategy/coach`는 별도 HTTP 경로라 트레이서가 안 본다. 프론트 dev 로그의
  `POST /api/strategy/compile 200`만 남는다.
- **원인**: `backend/ai/strategy_validation_agent.py::_TECHNICAL_CONDITIONS`가 `strategy_conversation/registry/
  indicator_registry.py::REGISTRY`(지표 지원 여부의 정본, "단일 진실 소스"라고 모듈 docstring에 명시)의 **수동
  하드코딩 사본**이고, 새 지표를 레지스트리에 추가해도 이 사본은 갱신되지 않는다. 2026-09-15 `volume_ratio`
  사고와 같은 모양이며, 2026-10-08 실측 때는 `consecutive_up`(5거래일 연속 상승)과 캔들 패턴 10종·`volatility`
  까지 15개가 한꺼번에 빠져 있었다 — 엔진·인터프리터·레지스트리 전부 지원하는데 검증 패널만 모른다.
  같은 파일이 참조하던 회귀 테스트(`test_engine_supported_metrics_are_not_flagged_unsupported`)도
  `engine/data_resolver.py::TECHNICAL_IDS`라는 **세 번째, 더 좁고 아무 데서도 안 쓰이는 사본**을 기준으로 돌아
  이 드리프트를 못 잡았다.
- **통한 수리**: `_TECHNICAL_CONDITIONS`를 `indicator_registry.REGISTRY`에서 `technical.*` id를 걸러 **derive**하도록
  바꿨다(레지스트리에 없는 `price`·`price_level`·`price_limit_exit`는 리스크/청산 식별자라 별도 유지). 회귀
  테스트도 `TECHNICAL_IDS` 대신 같은 레지스트리를 SOT로 전수 대조하도록 같이 고쳤다 — 그렇지 않으면 다음 신규
  지표도 같은 구멍으로 샌다.
- **진단 팁**: 이 유형은 agent_traces 그라운딩만으로는 안 잡힌다. "확정 직후 떴다"·"백엔드 에러 로그 없음"이면
  바로 `grep -rn "지원하지 않는 필드\|지원하지 않는" backend/ai/*.py`로 화이트리스트 소스를 찾는다.
- **예방**: "엔진/레지스트리는 지원하는데 어딘가 차단된다" 유형을 다시 만나면, 그 차단 지점의 화이트리스트가
  `indicator_registry.REGISTRY`·`engine.signals.FUNDAMENTAL_CIDS` 같은 SOT를 **참조**하는지 먼저 확인한다.
  수동 리터럴 집합이면 그 자체가 의심 1순위다. (project_strategy_validation_whitelist_drift_2026_10_08.md)

## R — 수리(재생성) 턴의 목록 필드 소실

- **신호**: Interpreter LLM 호출이 2회 이상이고, 1차 원출력의 `unsupported_features`·`clarification_questions`가 최종 결과에 없다.
  사용자 조건이 안내 없이 사라진다.
- **원인**: 재생성본이 목록을 `[]`로 비운다. "삭제하지 마세요"라는 문구는 9B도 120B도 지키지 않는다.
- **통한 수리**: 원출력에서 배열 경계만 형식 추출해 병합한다(`output_repair._salvage_array`, `salvage_*`).
  질문 복원은 형식 재생성에는 적용하지 않는다(지어낸 조건에 대한 질문일 수 있어서다).
- **재생 방법**: 트레이스의 Interpreter 하위 LLM 응답 두 개를 fake chat_fn으로 `StrategyInterpreter.interpret`에 넣는다. (project_repair_turn_list_field_loss.md)

## N — 거짓 안내(값은 제 칸에 있음)

- **신호**: 컴파일 결과를 보면 값이 다 들어가 있는데 화면에 "지원하지 않아요"·"가깝게 반영"이 나간다.
  **"표현 못 했다"는 화면을 보면 트레이스의 컴파일 결과부터 확인한다.**
- **원인들**:
  - LLM이 반영한 문구를 `unsupported_features`에도 중복으로 적었다(PEAD: 체결 시점·수수료).
  - 조건 회수 패스(`condition_recall`)가 유니버스 칸이나 랭킹 재료에 이미 쓰인 구절을 다시 꺼냈다. 인용이 없는 칸은 '이미 쓰인 근거' 대조에 걸리지 않는다.
  - 계열 껍데기 `class.*`+approximated가 라벨 없이 노출됐다.
  - 값 대기 라벨(내부 표기)이 안내에 그대로 나갔다. 안내는 사용자가 한 말(source_text)을 인용해야 한다.
- **통한 수리**: 안내 레인의 결정론 대조 표를 넓힌다(`indicator_registry.RANKING_INGREDIENTS`·`_RANKING_BUILT_IN_PROCESSING`·
  `condition_recall._UNIVERSE_FIELD_TWINS`, 내부 식별자를 담은 보고는 버림). **새 합성 랭킹·새 유니버스 칸을 만들면 이 세 표에도 추가한다.**
- **10-07 추가**: 랭킹 칸의 접두어 없는 `relative_return`은 `resolve`가 조건 지표(`technical.*`)로 돌려준다 —
  안내 라벨 판정은 `capability_validator._ranking_id`(정본 랭킹 ID)로 한다. 출력 형태 예시 조건
  (`_OUTPUT_SHAPE`의 '20일선을 상향 돌파하면' ma_crossover)을 120B가 기술 조건 없는 전략에 복사하면 출처 가드가
  빼면서 사용자가 말하지 않은 문구로 "반영하지 않았어요" 안내가 나간다(예시 57·70, 5/6).
- **기각**: `reflected_quotes` 채널로 출력 형태를 바꿔 고치려던 시도. 120B가 3/3 빈 배열을 냈고, 부작용으로
  '익일 시가'가 current_close로 뒤집혔다. (project_pead_earnings_surprise_v16_19.md, project_leftover_unsupported_notice_revived.md,
  project_dca_plan_loss_net_2026_09_21.md)

## S — 칸 오배정·누락(엔진 자리는 있음)

- **신호**: 엔진이 지원하는 개념인데 LLM이 비우거나, 옆 칸(position_sizing, trading_value, entry 대신 exit)에 적는다.
- **확인 순서와 사례**:
  1. **출력 형태에 키가 있나** — `_OUTPUT_SHAPE`에 `etf_theme`이 없어서 ETF 예시 7개 중 6개에서 테마가 사라졌다. 키 한 줄로 해결했다.
  2. **모순 예시** — 예시 4-3의 "평균 거래대금은 언제나 fundamental"이 새 규칙을 이겼다. 그 문장을 좁히니 3/4로 정착했다.
     예시 4-3의 "먼저→그중은 모두 entry" 서술 때문에 "20일선 이탈 시 청산"이 매수 조건으로 옮겨 갔다.
  3. **칸 위치** — `backtest.entry_tranches`에 두면 사다리를 옆 칸 ATR에 적었다(1/4). 대칭 칸인
     `risk_management.scale_in_buys`로 옮기니 5/5가 됐다. **LLM이 헷갈리는 칸은 의미가 가까운 칸 옆으로 옮기고, 검증기가 엔진 자리로 옮긴다.**
  4. **특정 턴 유형 전용** — 적립식 조건부 금액은 메인 프롬프트에 넣으면 4/4였지만 되묻기 하니스가 회귀했다
     ("2020년 1월부터 2024년 12월까지"→`2024-12-12-31`). 전용 판정(`contribution_amount_check`)으로 옮겼다.
  5. **값 흔들림** — 옮겨 적기 형태로 바꾼다("10년"→full 사고 이후 `<N>y` + `BacktestSpec._normalize_period`).
- **같은 인용의 값 없는 쌍둥이**(10-07 예시 46): 한 구절을 값 있는 조건+값 없는 조건으로 쪼개 내면 말한 값을
  되묻는다 → `capability_validator._drop_valueless_quote_twins`(지표·인용 표기 대조).
- **재심 금지**: LLM이 고른 칸을 원문 어휘 정규식으로 다시 읽어 뒤집으면 안 된다(`_mentions_volume_surge` 삭제 사례).
  뒤집어야 하면 LLM 대조(quote_check 계열)로 한다. 그때 제거는 가장 좁은 판정(no+other)에서만 한다.
  (project_interpreter_output_shape_authority.md, project_trading_value_ratio_indicator.md,
  project_openrouter_gate_flake_vs_defect.md, project_interpreter_prompt_volume_regression.md, project_quote_check_120b_false_drop.md)

## E — 엔진 부재(진짜 미지원)

- **신호**: LLM이 정직하게 `unsupported_features`로 신고했고 capability_validator도 같은 판단을 냈다.
- **절차**: (1) 재료 데이터가 있는지 센다(parquet 컬럼 non-null, DART·KIS 가용 연도). (2) 정의·기본값·칩·결합 방식(OR/AND)을
  사용자에게 받는다. (3) 엔진 구현은 최소 접점으로 한다(예: 국면 필터는 `_market_regime_exposure` 한 곳에 OR로 얹음).
  (4) 해석 배선은 wiring-checklists.md를 따른다. (5) 모르는 값의 처리(fail-open/closed)를 데이터 실태로 정한다.
- **사례**: 변동성 급등 v16.16, FCF 수익률·연속 배당 v16.15(재료가 있어 백필 없이 켬), 잔차 반전 v16.17,
  PEAD v16.19, 적립식 v16.20~22, 사다리 v16.36. **재료가 없음이 확정된 것(QoQ·NCAV·수급 — v16.26 메모)은 다시 조사하지 않는다.**

- **엔진은 있는데 방향을 버리는 하류**(2026-10-10 볼린저 v16.39): 컴파일러가 연산자를 읽지 않으면 '상단 돌파 매수'가
  정반대로 백테스트된다. 이동평균처럼 **검증기+컴파일러 양쪽**에 역할-방향 가드를 둔다(검증기가 없으면 READY 전량
  컴파일이 전략 전체를 던진다). 새 표현 자리를 만들 때 방향을 연산자로 받지 말고 **개념 ID 이름에 담는다** —
  120B는 '하단에 닿으면 청산'을 bollinger_lower+crosses_above로 냈다(2/2). '닿다'는 방향이 아니라 사건이다.
- **같은 별칭을 공유하는 새 잎**은 `_SAME_NAME_VARIANTS`에 등록한다 — 빠지면 정확히 반영한 조건에 근사 안내가 붙고
  (`_substituted_factor`), 조건 회수가 레거시 정본을 매수 칸에 되살린다(`condition_recall`의 known 대조).
- **같은 날 성립 불가한 AND 조합**(하단 터치+중심선 상향 돌파)은 차례 신호를 쪼갠 흔적이다 — 결정론으로 합치지 말고
  output_repair 판별 → 오류를 LLM에 되돌려 1회 재생성(실측 3/3 복구).

## A — 되묻기 답이 반영되지 않음

- **신호**: 답 턴에서 패치가 거부되거나 엉뚱한 칸에 들어가 "해석하지 못했어요"가 뜬다.
  "어떤 종목을 적립식으로?"에 "TIGER 미국S&P500"이라고 답했더니 120B가 6/6으로 `/backtest/contribution_amount`에 넣었다.
- **원인**: 일반 수정 LLM은 답의 자리를 질문 맥락으로 추론하는데, 메인 프롬프트가 모르는 칸이 초안에 있으면 귀속이 흔들린다.
- **통한 수리**: 질문 문구를 상수로 빼고, **우리가 낸 질문 문장과 같은지**(`pending_question in QUESTION`)로 전용 답변 판정에
  라우팅한다. LLM은 값·표현만 옮겨 적고, 패치 하나짜리 InterpreterResult로 일반 수정 파이프라인에 태운다
  (`_cash_reserve_answer_result`, `_contribution_symbol_answer_result`, `tranche_check`). 메인 프롬프트가 모르는 칸은
  `_draft_for_interpreter`에서 가린다.
- **기각**: 프롬프트에 슬롯을 명시하는 방식(08-26).
- **검증**: T1 응답을 파일로 저장하고 T2를 N회 반복한다(답 문자열을 조금씩 바꿔 캐시를 피한다). (project_dca_cash_pool_v16_22.md)

## Q — 되묻기 질문이 사라지거나 반복됨

- **규제 가드**: 질문에 '분할 매수'·'매수 시점' 같은 문구가 있으면 `stock_analysis.guardrails._FORBIDDEN`
  (`response/output_guard.guard_text`)이 **문장째 지운다**. 질문이 사라지고 값이 조용히 빠진다.
  새 질문 문구마다 `guard_text(q) == q` 테스트를 붙인다.
- **프론트 게이트 선점**: 백엔드 되묻기에 우선순위 마커가 없으면 프론트 explicit 게이트(골격 칸 칩 질문)가 먼저 돌아
  백엔드 질문을 삼킨다. 골격이 다 찬 뒤에는 백엔드를 아예 부르지 않는다(트레이스에 1턴만 남음). 골격 밖의 값 대기는
  백엔드 main 게이트와 프론트 `getNextMissingBacktestCondition` 양쪽에 넣고, 문구는 `export_slot_prompts.py` 픽스처로 공유한다.
- **새 검증 규칙이 정당한 답을 거부**: '합 ≤ 100%' 규칙이 '100% 사자'를 거부해 같은 질문이 조용히 반복됐다.
- **질문 큐 상한**: 한 턴에 `MAX_QUESTIONS_PER_TURN=3`개까지다. 넘치는 질문은 다음 턴으로 가는 것이 설계다(결함 아님).
  (project_tranche_ladder_v16_36.md)

## F — 프론트가 덮어씀

- **신호**: 백엔드 응답의 `parsed`는 맞는데 화면 값이 다르다. 또는 트레이스에 Strategy span이 없는데 되묻기가 떴다.
- **사례**: `risk_overrides`의 원문 정규식이 "-5% 하락하면 그대로 보유"를 손절 5%로 지어냈다. 프론트
  `resolveStrategyAssumptions`는 원문의 '단기'를 보고 LLM보다 먼저 보유 기간을 되묻거나 63일로 확정했다.
- **대응**: 대원칙 1 위반으로 보고하고, 사용자 승인 후 제거한다. 정본은 백엔드 인터프리터와 completeness_validator다.
  CLAUDE.md 현행 격차 표를 갱신한다. (project_frontend_holding_horizon_prejudgment_removed.md)
