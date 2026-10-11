---
name: trace-triage
description: 널스탁 에이전트 Trace(backend/logs/agent_traces)에서 최근 실패 후보를 구조 신호로 묶어 보고, 묶음별로 원인 레이어를 짚어 수리 스킬로 넘기고, 반복되는 실패 유형을 훅·스킬·테스트로 승격하는 일일 실패 루프. 사용자가 "/trace-triage", "어제 뭐가 실패했어", "트레이스 실패 정리해줘", "실패 후보 봐줘", "triage 돌려줘", "요즘 해석 실패 뭐 있어"라고 하거나, 세션 시작 시 [trace-triage] 요약 줄이 결함 후보를 알렸을 때 반드시 이 스킬을 쓴다. 특정 사고 한 건을 고치는 일은 strategy-interpretation-fix가 맡고, 이 스킬은 그 앞단(무엇을 고칠지 고르기)과 뒷단(반복 유형 고정)을 맡는다.
---

# Trace 실패 루프

실패는 매일 Trace에 쌓이지만, 사람이 화면에서 우연히 보기 전까지 아무도 읽지 않았다. 이 스킬은 그 고리를
닫는다: **① 묶어 보기 → ② 고를 묶음 정하기 → ③ 레이어 짚고 수리 스킬로 넘기기 → ④ 반복 유형 승격.**

## 먼저 지킬 것

- **대원칙 1**: 실패 판정은 구조 신호(span 오류·검증기 보고·compile dropped·clarification_priority·질문 문장
  동일성)로만 한다. 리포트의 `입력:` 줄은 표본일 뿐이다. 원문을 정규식으로 읽어 새 신호를 만들지 않는다.
  새 신호가 필요하면 **시스템이 그 사실을 구조 필드로 남기게** 계측을 고친다.
- **대원칙 2**: 어떤 묶음을 고칠지, 무엇을 승격할지는 사용자가 정한다. ②에서 묻는다.
- **원문 보관 3일**: 리포트(`backend/logs/triage/`)에도 원문이 들어가므로 같은 기한으로 지워진다. 원문을
  메모리·문서·커밋 메시지로 옮기지 않는다(필요하면 구조 사실과 trace_id만).
- **운영 Trace**: backend 컨테이너의 `logs/agent_traces/`만 호스트에 마운트된다(2026-10-11 — 그 전 배포분은
  재배포 때 사라졌다). 박스에서 `docker compose exec backend python scripts/triage_traces.py --no-write`(리포트 파일을 쓰지 않음).

## 1. 묶어 보기

```bash
cd backend && uv run --frozen python scripts/triage_traces.py            # 보관 중 전체(최대 3일)
cd backend && uv run --frozen python scripts/triage_traces.py --days 1   # 오늘만
cd backend && uv run --frozen python scripts/triage_traces.py --json     # 기계 처리용
```

등급은 넷이다: **결함 후보**(우리 코드 실패) · **확인 필요**(의도된 거절일 수 있음) · **제품 공백**(엔진에 자리
없음) · **인프라**(상류 429·취소·느린 턴 — 코드 수리 아님). 묶음 하나 = 신호 × 판별 키.

## 2. 고를 묶음 정하기

결함 후보를 건수·세션 수 순으로 보여 주고, 묶음마다 아래 표의 기호로 첫 진단을 붙여 사용자에게 고르게 한다.
같은 문장이 반복되는 묶음(QA 하니스 반복 실행)은 세션 수로 실제 무게를 본다.

| 신호 | 첫 진단 (strategy-interpretation-fix 2단계 표 기호) | 먼저 볼 곳 |
|---|---|---|
| `interpreter_error` InterpreterError | **B**/**R** 형식 위반 | LLM span 원출력 → `output_repair` |
| `planner_error` TurnBudgetExhausted·NoProgress | 플래너 수렴 실패 | Planner span의 DAG 반복 — `planner/dag_planner.py` |
| `modify_unapplied` · `ask_repeat` | **A** 되묻기 답 미반영 / **Q** | 같은 질문 동일성 라우팅, 패치 경로가 실제 필드에 닿는지 |
| `dropped_condition` | **S** 칸 누락 / **E** 엔진 부재 | compile `dropped` 라벨 ↔ 검증기 `errors`·`unsupported` |
| `validation_error` | **C** 또는 의도된 거절 | 오류가 지역 격리·규제 거절이면 정상 — 결함 아님 |
| `approximated` | **N** 근사 안내 | 근사가 정당한지(엔진에 정확한 자리가 있는지) |
| `sector_unresolved` | 업종·테마 결속 | 정본에 섹터는 있는데 동의어만 없는지 먼저 |
| `unsupported` | **E** 제품 공백 | 규제 금지(수익 보장·추천)는 의도된 거절 — 공백 아님 |
| `infra_error` · `slow_turn` | **L** 레인 | 수리 아님. 한도·폴백 시간대인지 확인 |

## 3. 수리 스킬로 넘기기

골라진 묶음마다 대표 trace_id 상세를 보고 `strategy-interpretation-fix` 스킬의 1단계부터 진행한다:

```bash
python .claude/skills/strategy-interpretation-fix/scripts/trace_turn.py --trace-id <id> --full
```

- 묶음 하나 = 수리 하나. 여러 묶음을 한 변경으로 섞지 않는다(원인이 겹칠 때만 묶고 그 근거를 보고).
- 수리는 격리 워크트리에서 한다(병렬 세션의 `--reload`·미커밋 작업과 섞이지 않게):
  `scripts/worktree.sh new <slug>` — 데이터·의존성·`.env`·logs를 원본 링크로 붙여 준다(맨 `git worktree add`는
  이것들이 없어 테스트가 돌지 않는다).
- 수리 뒤 같은 묶음의 대표 입력을 재표본해 그 신호가 사라졌는지 이 스크립트로 다시 센다.

## 4. 반복 유형 승격

같은 **신호 종류**가 메모리(`MEMORY.md`)의 과거 사고와 겹치거나 두 번째 리포트에도 남으면, 수리로 끝내지
말고 다음 중 하나로 고정하자고 **제안**한다(실행은 승인 후):

| 반복 형태 | 고정 장치 |
|---|---|
| 같은 실수를 코드 작성 중 반복 | `.claude/hooks/` 가드 훅(PreToolUse 차단 또는 PostToolUse 리마인드) |
| 같은 진단 절차를 반복 | 스킬 참조 파일 갱신(`failure-patterns.md`) 또는 새 스킬 |
| 같은 결과 결함이 재발 | 회귀 테스트(트레이스 LLM 원출력 고정 재생) |
| 새 신호가 필요한데 구조 필드가 없음 | 계측 추가(span outputs/metadata에 판정 결과를 남기게) |

승격하면 이 스킬의 표(2단계)와 `triage_traces.py`의 `SIGNALS`를 함께 갱신한다.

## 보고 형식

CLAUDE.md 설명 스타일(결론 한 줄 → 번호 단계 → "한 줄로: …"). 묶음 목록은 등급·신호·건수·세션 수·첫 진단만
표로. 원문 표본은 필요한 것만 짧게. 무엇을 고르지 않았는지(인프라·의도된 거절)와 그 이유도 적는다.
