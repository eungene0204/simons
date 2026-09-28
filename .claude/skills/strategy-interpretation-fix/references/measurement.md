# 실측 기법과 함정

해석 수리는 LLM 출력에 달려 있어서 유닛 테스트만으로는 끝나지 않는다. 반대로 LLM을 마구 부르면 한도가 바닥나고,
120B는 같은 입력에도 흔들리므로 1회 측정으로는 인과를 판정할 수 없다. 이 문서는 싸고 믿을 만한 측정 순서를 정리한다.

## 비용 순서 (싼 것부터)

1. **오프라인 재생 (LLM 0회)**: 트레이스에 기록된 LLM 응답을 스텁으로 물린다.
2. **부분 재생 (LLM 몇 회)**: 1차 출력은 고정하고 바꾼 보조 판정만 실제 LLM으로 돌린다.
3. **메모리 대조군 (LLM 2×2회)**: 프롬프트 파일을 고치지 않고 문자열만 잘라 A/B를 만든다.
4. **실서버 재표본 (LLM 3~5회)**: 캐시를 우회해 사고 원문을 반복한다.
5. **하니스·게이트 (LLM 수십~수백 회)**: 사용자에게 알린 뒤 돌린다.

## 1. 오프라인 재생

- 트레이스 줄의 LLM span `outputs.response`를 꺼낸다(`trace_turn.py --trace-id <id> --full`).
- 인터프리터만 재생: 응답 N개를 순서대로 돌려주는 fake `chat_fn`을 `StrategyInterpreter.interpret`에 넣는다. 수리 턴이면 응답 두 개가 필요하다.
- 전체 파이프라인 재생: 해석·구절 나열·기간 등 LLM span 전부를 스텁으로 물려 `primary.run_primary_parse`를 돌린다.
- 이 재생을 그대로 회귀 테스트로 굳힌다. 사고 원출력이 테스트 고정 입력이 된다.

## 2. 부분 재생 (보조 판정만 바꿨을 때)

인터프리터 `_chat`을 감싸 **메인 시스템 프롬프트의 첫 호출만** 기록 응답으로 돌려준다(재생성 호출은 실제로 보낸다).
이것을 `primary._interpreter_singleton`에 주입하고, 트레이스 줄 번호를 인자로 받아 여러 출력 형태에서 돌린다.
1회에 5~7건을 쓴다. 1차 해석의 흔들림과 보조 판정의 결함이 분리된다.

## 3. 프롬프트 A/B

- **메모리 대조군** (파일 무수정, `--reload` 안 건드림):
  `full = prompts.build_system_prompt(); without = full.replace(ADDED, "")`로 만들고
  `interp._chat(system, prompts.build_user_prompt(text))`를 각 2회 돌린다. 대조군은 캐시 미스라 느리다.
  `_LLM_CALL_TIMEOUT_S`와 `_OLLAMA_*_MAX_ATTEMPT_TIMEOUT_S`를 모듈 속성으로 올려 둔다.
- **주의**: `_chat` 경로는 실경로가 아니다. 운영 `interpret()`은 `ui_language.append_directive`를 덧붙이고, 그 한 줄로 판단이
  갈린 적이 있다. 원인 찾기는 `_chat`으로 해도 되지만 **결론은 `interpret()`으로 확인**한다.
- **별도 포트 사본** (게이트 규모 A/B): 워킹트리를 rsync로 복사하고 사본의 `prompts.py`만 이전 버전으로 되돌린다.
  8001 포트로 띄우고 `_nl_parse_cache` 조회를 끈 뒤 같은 하니스를 `QA_BACKEND=http://localhost:8001`로 돌린다.
  공유 워킹트리를 건드리지 않으면서 단일 변수 비교가 된다.
- 파일을 직접 교체해야 한다면: 백업 → 교체 → reload 대기 → 측정 → 복원 → `git diff`가 0인지 확인한다.

## 4. 실서버 재표본

- `POST localhost:8000/strategy/parse` body `{"prompt": …, "backend": "ollama", "model": "r1"}`로 보낸다. 회차마다 `model` 접미사를 바꿔
  파스 캐시 키를 비튼다. 파서 인스턴스가 이미 있으면 `model`은 실제 모델 선택에 쓰이지 않는다. `--reload` 직후에는 model 없이 워밍업을 1회 한다.
- /us 경로는 `"language": "en"`을 싣는다. 빠지면 한국 요청으로 처리된다.
- 매 회 확인할 것: 응답 `runtime.cache_hit=False`, `runtime.interpreter.model_name`(9B 폴백 여부), 트레이스에 Interpreter span이 있는지.
  **캐시 적중을 성공으로 센 사고가 있었다**("3/3 성공"이 사실은 재사용).
- 멀티턴(되묻기 답): T1 응답을 파일로 저장하고 T2만 N회 반복한다. 답 문자열을 조금씩 바꿔 캐시를 피한다.
- 실패 응답은 캐시되지 않는다. 같은 요청을 다시 보내면 새 호출이 된다.

## 5. 하니스·게이트

| 바꾼 것 | 돌릴 것 | 비고 |
|---|---|---|
| `prompts.py`, LLM 레인·모델 | `uv run python scripts/qa_free_input.py modify` / `fill` | 전후 대조. 결과에 측정 모델을 적는다. `QA_TIMEOUT`(기본 600) |
| 예시 문구, 온톨로지·어휘, 프롬프트 | `uv run python scripts/qa_template_detect.py --category <카테고리>` → 표시 전수 조사 | 치명 0(종료 코드 0). 매번 백엔드에 다시 묻는다. `--use-cache`는 게이트용이 아니다 |
| 화면 라벨 | `QA_DISPLAY_SWEEP=1 npx vitest run scripts/qa_kr_display_sweep.test.ts` | 결함 0 |
| /us 파싱·분류·되묻기 | `qa_redteam_validation.py`·`qa_free_input.py modify`·`qa_multiturn_binding.py` 모두 `--lang en` | 파서 입력만 영어 |
| US 예시·en.ts | `qa_template_detect.py --source us` 와 `--source us --lang en` | 두 게이트 모두 |
| phase1·prep_cache·wfa 등 성능 경로 | `uv run python scripts/qa_backtest_equivalence.py --wfa` | 불일치 0 |

- **flake와 결함 나누기**: 치명 항목마다 재표본 3회. 일시 실패(빈 전략, `interpretation_failed`)는 재파싱하면 정상으로 나온다.
- **회귀인지 판정**: 같은 실패가 프롬프트만 되돌린 대조군에서도 같은 비율로 나오면 기존 결함이다. 되묻기 하니스의
  '60일 신고가 뚫을때'(교체 vs 추가)는 같은 프롬프트에서도 갈리는 알려진 노이즈다.
- **되묻기는 실패가 아니다**: 값이 빠진 팩터를 묻는 것은 정상 동작이다.
- 게이트 도중 `backend/`(tests 포함)를 편집하면 `--reload`가 요청을 끊는다. 이 증상은 타임아웃과 비슷해서 오진하기 쉽다.
- 비용 감각: KR 예시 게이트 1회 ≈ 430건, 되묻기 하니스 2계열 + 실측 몇 건이면 하루 남은 한도를 다 쓴다(같은 날 다른 세션 사용분 포함).

## 테스트 스위트 함정

- `tests/test_sync_data_status.py`, `test_sync_fundamental_enrichment_gate.py`는 수집 시점에 외부 HTTP를 읽어서 간헐적으로 스위트를 중단시킨다.
  이럴 때는 `--continue-on-collection-errors`로 돌리고, 해당 파일은 단독으로 재실행해 확인한다.
- 테스트가 도는 중에 `git stash`를 하면 안 된다(병렬 세션 작업이 섞인다).
- 실패가 내 변경과 무관해 보이면 워킹트리 스냅샷(병렬 세션의 미커밋 변경) 때문인지 먼저 확인하고, 그 판단을 보고에 적는다.
