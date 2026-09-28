---
name: strategy-interpretation-fix
description: 널스탁 전략 해석(자연어→전략) 실패를 진단하고 해석 가능하게 고치는 절차. 사용자가 "해석하지 못했어요"·"요청을 전략 조건으로 해석하지 못했어요" 화면, 엉뚱한 되묻기, 거짓 미지원/근사 안내, 조건이 조용히 사라짐, 값이 다른 칸에 들어감, 되묻기 답이 반영 안 됨 같은 스크린샷이나 문장을 주면서 "이거 해석하게 해줘", "왜 못 알아들어", "이 전략 지원하게 해줘", "이 조건이 빠졌어"라고 할 때 반드시 이 스킬을 쓴다. 인터프리터 프롬프트(prompts.py)·output_repair·전용 판정(*_check.py)·capability/completeness validator·compiler 수정, 새 지표/랭킹/유니버스 칸/엔진 기능을 해석 경로에 배선하는 작업, 해석 사고의 트레이스 분석(backend/logs/agent_traces)에도 쓴다.
---

# 전략 해석 수리

사용자 전략 문장이 해석되지 않을 때마다 같은 순서로 같은 함정을 다시 밟아 왔다. 이 스킬은 그 순서를
고정한다: **① 사고 턴 찾기 → ② 어느 레이어에서 틀어졌는지 분류 → ③ 사용자 결정 받기 → ④ 가장 싼
레이어에서 수리 → ⑤ 실측 검증 → ⑥ 마무리.**

가장 흔한 실수는 ②를 건너뛰고 곧장 프롬프트나 엔진을 고치는 것이다. 과거 사고의 절반 이상은 LLM이
이미 맞게 해석했는데 하류(조립·검증·안내·프론트)가 망친 경우였다. 트레이스로 레이어를 먼저 확정한다.

## 먼저 지킬 것

- **대원칙 1**: 사용자 원문을 정규식·어휘 목록으로 판정하는 코드를 추가·확장하지 않는다. "어휘가 모자라서"로
  보이면 레인 문제다 — 판정을 LLM(메인 인터프리터 또는 전용 판정)으로 옮긴다. 결정론 코드는 LLM 출력의 형식만
  다룬다. 기존 코드가 원문을 읽고 있으면 먼저 **위반이라고 보고**한다(수정안으로 제시하지 않는다).
- **대원칙 2**: 전략의 뜻을 정하는 결정(지표 정의, 기본값 vs 되묻기, 칩 값, 근사 허용 여부)은 사용자 몫이다.
  ③단계 목록을 보고 묻는다.
- **LLM 호출 비용**: OpenRouter 무료 한도(1000건/일, 09:00 KST 초기화)를 쓴다. 하니스·게이트·N회 재표본은
  실행 전에 사용자에게 대략의 건수를 알린다(예시 KR 게이트 1회 ≈ 430건).
- **공유 워킹트리**: 병렬 세션이 같은 디렉터리를 쓴다. `backend/` 아래를 고치면 uvicorn `--reload`가 진행 중
  요청·게이트를 끊는다. `git add -A`·`git stash` 금지.

## 1단계 — 사고 턴을 찾는다

로컬에서 난 사고면 트레이스 요약 스크립트부터 돌린다:

```bash
python .claude/skills/strategy-interpretation-fix/scripts/trace_turn.py --grep "<사용자 문장 일부>"
python .claude/skills/strategy-interpretation-fix/scripts/trace_turn.py --last 3          # 최근 전략 턴
python .claude/skills/strategy-interpretation-fix/scripts/trace_turn.py --trace-id <id> --full  # LLM 원출력까지
```

레이어별(Parse Evidence → Interpreter → 보조 판정 → Planner → validate_intent → compile_strategy → Responder)로
채워진 칸·오류·안내·되묻기·레인 모델을 보여 주고, 확실한 신호(조립 예외, 빈 라벨 토큰 수, 캐시 적중, 9B 폴백,
재생성 턴)는 '진단 힌트'로 짚는다.

- 로컬 트레이스는 최근 며칠 치만 남는다. 오래된 사고라면 재현부터 한다.
- 스크린샷만 있고 트레이스가 없으면 로컬 백엔드에 같은 문장을 보내 재현한다:
  `curl -s localhost:8000/strategy/parse -H 'Content-Type: application/json' -d '{"prompt":"…","backend":"ollama","model":"x1"}'`
  — `model` 접미사를 바꿔 파스 캐시(`main._nl_parse_cache`)를 우회한다. 트레이스에 `cache_hit=True`거나
  Interpreter span이 없으면 **LLM을 부르지 않은 턴**이다. 재표본으로 세지 않는다.
- 운영 사고면 운영 박스의 `backend/logs/agent_traces/`에서 해당 줄을 가져와 `--date`로 읽는다(읽기 전용).
- 응답을 볼 때 `parsed`만 보지 말고 `risk_overrides`·`notices`·`clarification`도 본다. 프론트가 `risk_overrides`로
  덮어쓴다.
- 결과를 읽기 전에 **레인 모델**부터 확인한다. `runtime.interpreter.model_name` / LLM span의 model·provider가 기준이다.
  한도 소진 시간대에는 9B 폴백이 조용히 돈다. 9B 결과를 운영 레인 결과로 보고하지 않는다.

## 2단계 — 어느 레이어에서 틀어졌나

트레이스 신호로 아래 표에서 하나를 고른다. 각 유형의 사고 이력·세부 함정은
[references/failure-patterns.md](references/failure-patterns.md)의 같은 기호 절에 있다.

| 기호 | 트레이스 신호 | 실제 원인 | 검증된 수리 레이어 |
|---|---|---|---|
| **L** 레인 | 모델이 120B가 아님·provider=None·Ollama 000·429 | 한도 소진/서버 다운 | 코드 수리 아님. 레인 복구 후 재측정 |
| **B** 빈 라벨/붕괴 | Interpreter LLM out ≈ 11토큰, 라벨만 | 형식 위반 | `output_repair`에 판별+오류 문구 → 1회 재생성 |
| **C** 조립 예외 | `compile_strategy` ❌ ValidationError | 인터프리터 모델(느슨)↔ParsedStrategy(엄격) 범위 불일치 | 모델 validator 정규화(끝값 이동) 또는 capability_validator가 먼저 오류+제외 |
| **R** 수리 턴 소실 | Interpreter LLM 2회+, 1차에 있던 목록이 최종에 없음 | 재생성본이 목록 필드를 비움 | `output_repair._salvage_array` 결정적 병합 |
| **N** 거짓 안내 | 값은 제 칸에 있는데 안내·근사 문구가 나감 | 안내 레인 가드(회수 패스·잔여 미지원·근사) | 안내 레인 대조 표(RANKING_INGREDIENTS 등) 확장. 프롬프트 불변 |
| **S** 칸 오배정/누락 | 엔진 자리는 있는데 LLM이 비우거나 옆 칸에 씀 | 출력 형태에 키 없음, 모순 예시, 칸 위치 | 형태 키 → 모순 예시 제거 → 칸 자리 이동 → 전용 판정 |
| **E** 엔진 부재 | LLM이 정직하게 `unsupported_features`로 신고 | 엔진에 표현 자리가 없음 | 사용자 결정 → 엔진 기능 + 배선 체크리스트 |
| **A** 되묻기 답 미반영 | 답 턴에서 패치 거부·엉뚱한 칸·"해석하지 못했어요" | 일반 수정 LLM이 답의 자리를 못 찾음 | 질문 문장 동일성으로 라우팅하는 전용 답변 판정 |
| **Q** 되묻기 사라짐 | 검증기 질문은 있는데 화면에 없음·같은 질문 반복 | 규제 출력 가드가 문장 삭제 / 프론트 게이트가 삼킴 / 새 검증 규칙이 정당한 답 거부 | `guard_text(q)==q` 확인, 백엔드+프론트 게이트 양쪽 배선 |
| **F** 프론트 덮어쓰기 | 백엔드 `parsed`는 맞는데 화면 값이 다름, Strategy span 없음 | 프론트 원문 정규식(conversationDecision·risk_overrides) | 대원칙 1 위반으로 보고 → 승인 후 제거 |

여러 유형이 한 사고에 겹치는 일이 흔하다(09-28 사다리: C+E+Q+F). 표를 끝까지 대조한다.

## 3단계 — 사용자에게 물을 것

아래는 내가 정하면 안 되는 것들이다. 트레이스 근거와 선택지(데이터 실측 포함)를 붙여 한 번에 묻는다.

- 새 개념의 **정의**(예: '변동성 급등' = 20일 변동성 ÷ 1년 평균 N배; '잔차 반전'의 회귀 대상·정규화)
- 값이 없을 때 **되묻기 vs 고정 기본값**(파라미터마다 계약이 다르다 — 잔차 반전은 60/5 기본, 가격 랭킹 기간은 되묻기).
  말하지 않은 값을 조용히 확정하거나 역산하지 않는다("첫 회차 65%" 역산은 "전략에 없는 내용"으로 지적받았다)
- 되묻기 **칩 값**(예: 1.5·2·2.5배, 10·20·30%)
- **근사로 둘지, 엔진을 새로 만들지**, 미지원 안내로 둘지
- 데이터가 없는 경우(수집·백필은 프로덕션에서 — parquet 방향은 프로덕션→로컬뿐)
- 기존 원문 정규식 제거(대원칙 1 위반 코드의 삭제는 사용자 승인 후)
- 사용자 답을 **거부하는** 도메인 검증 추가(그 답이 화면에서 어떻게 되는지까지 확인해 함께 보고)

## 4단계 — 가장 싼 레이어에서 고친다

아래 순서로 내려가며 **처음 통하는 곳**에서 고친다. 위로 갈수록 파급이 작다.

1. **LLM 출력이 이미 맞다** → 하류 결정론 수리(조립 정규화, 검증기, 안내 대조 표, provenance, 프론트 배선).
   메인 프롬프트는 건드리지 않는다.
2. **LLM 출력이 형식을 어겼다** (빈 라벨, 입력 전체 인용, 목록 소실, 형태가 다른 목록) → `output_repair`의
   형식 판별 + 오류를 LLM에 되돌려 재생성(`MAX_REPAIR_ATTEMPTS` 공유), 또는 원출력에서 형식 추출 후 병합.
   오류 문구도 실측으로 고른다("옮길 수 있는 표현은 필드에" 줄이 없으면 전부 미지원으로 던진다).
3. **특정 턴 유형에서만 필요한 의미** → 메인 프롬프트가 아니라 그 턴에만 도는 **전용 판정 패스**
   (`interpreter/*_check.py` 패턴: 조건·인용을 보여 주고 enum/옮겨 적기만 받기, 실패=판정 없음, fail-open).
   같은 턴의 다른 판정과 묶을 수 있으면 `check_batch.py`에 편입한다. 새 전략 유형이면 덧대는 판정 N개가 아니라
   **그 유형의 판정 하나 + 일반 보정의 명시적 가드**로 만든다. 발동 조건이 1차 해석의 한 칸에 걸려 있으면
   그 칸이 빠질 때의 그물도 같이 설계한다.
4. **메인 인터프리터 프롬프트 변경**(최후) — `prompts.py`:
   - 필드를 안 채우면 규칙을 늘리기 전에 `_OUTPUT_SHAPE`에 **키가 있는지** 먼저 본다(형태 > 규칙). 목록 항목에
     새 키를 더하면 **모든 예시 항목**에 넣는다(120B는 형태를 자리별로 흉내 낸다).
   - 규칙이 안 먹으면 문구를 늘리기 전에 프롬프트 안의 **모순 예시 문장**을 찾는다.
   - 규칙은 **한 줄**. 동의어 나열·금지 문구·"왜"를 넣지 않는다. 분량이 늘면 9B가 빈 전략을 낸다.
   - 조건부 규칙("넷 중 아니면 계산하라") 대신 **옮겨 적기 형태**(`<N>y`) + 결정론 변환.
   - 형태 키 추가는 다른 칸을 흔들 수 있다(reflected_quotes 채널이 체결 시점을 뒤집은 사례). **전후 A/B 필수.**
   - `PROMPT_VERSION`을 올린다.
   - 메인 프롬프트가 모르는 칸은 수정 턴 초안에서도 가린다(`primary._draft_for_interpreter`).
5. **엔진 기능 신설** → [references/wiring-checklists.md](references/wiring-checklists.md)의 해당 체크리스트를
   **전부** 돈다(재무 지표 ≈13곳, 랭킹 파라미터 ≈15곳, 유니버스 칸, ParsedStrategy 필드, 되묻기 질문, 결과 경고).
   빠뜨린 접점은 대개 "값은 들어갔는데 화면에 안 보임" 또는 "되묻기가 엉뚱함"으로 돌아온다. 새 지표를 만들기 전에
   재료 컬럼이 parquet에 있는지(`data/ohlcv/005930.parquet` non-null 수) 먼저 센다. 있으면 백필 없이 런타임 계산으로 켤 수 있다.

## 5단계 — 실측 검증

유닛 테스트는 LLM 출력을 못 본다. 해석 수리는 **실제 LLM 경로에서 N회**로 확인해야 끝난다.
세부 기법·함정은 [references/measurement.md](references/measurement.md)에 있다.

1. **회귀 테스트**: 사고를 재현하는 유닛 테스트(가능하면 트레이스의 LLM 원출력을 고정 입력으로)를 추가하고
   CLAUDE.md의 백엔드 pytest 전체 + `npm run test:frontend`를 돌린다. 되묻기 문구를 새로 썼으면
   `guard_text(q) == q` 테스트를 붙인다.
2. **오프라인 재생**(LLM 0회): 트레이스 LLM span 응답을 fake chat_fn으로 물려 `run_primary_parse`/`interpret`를 재생한다.
   보조 판정만 바꿨으면 1차 출력을 고정하고 보조 판정만 실제 LLM으로 돌린다.
3. **사고 원문 실서버 재표본**: 캐시를 우회해 3~5회 돌린다. 매 회 트레이스로 Interpreter span 존재와 레인 모델을 확인한다.
   120B는 같은 프롬프트에서도 흔들린다. 1회 성공이나 1회 A/B로 인과를 단정하지 않는다.
4. **게이트**(사용자에게 한도 알린 뒤). 무엇을 바꿨느냐로 고른다:
   - `prompts.py`·레인·모델 변경 → `uv run python scripts/qa_free_input.py modify` + `fill`(전후 대조, 측정 모델 기록)
   - 예시 문구·어휘·온톨로지(프롬프트 어휘가 생성됨) 변경 → `uv run python scripts/qa_template_detect.py --category <카테고리>` → `QA_DISPLAY_SWEEP=1 npx vitest run scripts/qa_kr_display_sweep.test.ts`
   - /us 경로 → `--lang en` 하니스 3종
   - 성능 경로(phase1·prep_cache 등) → `uv run python scripts/qa_backtest_equivalence.py --wfa`
   - 게이트가 붉으면 치명 항목을 재표본 3회로 flake와 결함으로 나누고, 프롬프트만 되돌린 대조군과 비교해 회귀인지 판정한다.
5. 새 필드·안내·칸이 **화면에 실제로** 나오는지(요약 카드·진행 카드·결과 타일)까지 확인한다. 식별자가 그대로 노출되면 결함이다.

## 6단계 — 마무리

- 엔진 결과값·요청이 바뀌면 `backend/engine/version.py` MINOR, 프롬프트면 `PROMPT_VERSION`.
- 새 ParsedStrategy 필드 → `python scripts/export_slot_judgments.py`, 새 되묻기 문구 → `export_slot_prompts.py`,
  칩 → `export_clarification_chips.py` 재실행(픽스처 신선도 테스트가 잡는다).
- 처리 흐름 구조(단계·분기·가드)가 바뀌면 `components/admin/AgentsTab.tsx` 흐름도 갱신.
- 원문 정규식을 제거했거나 새로 발견했으면 CLAUDE.md "현행 격차" 표를 갱신.
- `docs/PROJECT_PLAN.md`(✅ 완료)·`docs/SRS.md`·`docs/software_architecture.md` 반영.
- 메모리: 새로 배운 함정만 기존 파일에 덧붙이거나 새로 쓴다(사용자 결정·실측 수치·미실행 게이트 포함).
  이 스킬의 failure-patterns/checklists에 없는 새 유형이면 **스킬 참조 파일도 함께 갱신**한다.
- 보고에는 **미실행 게이트와 이유**(한도·승인 대기)를 명시한다. 돌리지 않은 것을 통과로 쓰지 않는다.

## 보고 형식

CLAUDE.md 설명 스타일을 따른다: 결론 한 줄 → 번호 단계(일상 비유 먼저, 용어는 괄호) → 근거 파일:라인은 뒤에 →
"한 줄로: …". 여기에 **무엇을 실측했고(모델·횟수) 무엇을 못 돌렸는지**를 덧붙인다.
