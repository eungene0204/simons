# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

사용자가 자신만의 주식 투자 전략을 **설계 → 검증 → 최적화 → 실전 시뮬레이션**까지 원스톱으로 수행할 수 있는 종합 투자 시뮬레이션 플랫폼.

## 규제 안전 원칙 (유사투자자문업 회피)

### 핵심 원칙

- 우리 서비스는 투자 연구 및 시뮬레이션 플랫폼이다.
- 본 서비스는 투자 자문, 투자 추천, 개인 맞춤형 금융 조언을 제공하지 않는다.
- 모든 투자 판단은 사용자가 직접 수행한다.
- 시스템은 계산, 백테스트, 시뮬레이션 및 객관적인 과거 데이터 표시만 수행한다.

### 허용되는 기능

#### 전략 연구

- 사용자가 직접 전략 생성
- 조건 블록 조합
- 전략 수정 및 저장
- 전략 비교

#### 백테스트

- 과거 데이터 시뮬레이션
- CAGR
- MDD
- 샤프 비율
- Profit Factor
- 거래 통계
- 수익곡선

#### 가상계좌

- 모의투자만 제공
- 가상 체결
- 포트폴리오 추적
- 거래 내역 조회

#### 데이터 제공

- 차트
- 기술적 지표
- 재무 지표
- 과거 통계 정보

### 절대 구현하면 안 되는 기능

#### 투자 추천

다음 기능은 절대 제공하지 않는다.

- 전략 추천
- 종목 추천
- 섹터 추천
- ETF 추천
- 포트폴리오 추천

금지 예시:

- ❌ “이 전략을 추천합니다.”
- ❌ “전략 A를 사용하는 것이 좋습니다.”
- ❌ “현재는 가치 전략이 유리합니다.”
- ❌ “반도체 업종이 유망합니다.”

#### 시장 전망

다음 기능은 절대 제공하지 않는다.

- 시장 예측
- 시장 전망
- 매수 시점 제안
- 매도 시점 제안

금지 예시:

- ❌ “지금 매수하기 좋은 시기입니다.”
- ❌ “시장이 상승할 가능성이 높습니다.”
- ❌ “계속 보유하는 것이 좋습니다.”

#### 개인 맞춤형 조언

다음 기능은 절대 제공하지 않는다.

- 나이 기반 추천
- 자산 규모 기반 추천
- 소득 기반 추천
- 위험 성향 기반 추천

금지 예시:

- ❌ “40대라면 배당 전략이 적합합니다.”
- ❌ “1억 원이라면 성장주 비중을 늘리는 것이 좋습니다.”

#### AI 코치 기능

다음 기능은 절대 제공하지 않는다.

- 전략 자동 추천
- 전략 자동 개선
- 전략 우열 판단
- 사용자 행동 제안

금지 예시:

- ❌ “이 전략이 더 우수합니다.”
- ❌ “전략 B로 변경하는 것을 추천합니다.”
- ❌ “현재 시장에서는 전략 A가 더 적합합니다.”

### 안전한 표현 원칙

허용:

- ✅ “과거 데이터 기준 CAGR은 12.4%였습니다.”
- ✅ “최대 낙폭은 -18%였습니다.”
- ✅ “총 53회의 거래가 발생했습니다.”
- ✅ “결과는 과거 데이터 기반 시뮬레이션 결과입니다.”
- ✅ “미래 수익은 보장되지 않습니다.”

금지:

- ❌ “이 전략은 앞으로도 잘 작동할 것입니다.”
- ❌ “높은 성과가 기대됩니다.”
- ❌ “좋은 투자 전략입니다.”
- ❌ “추천 전략입니다.”
- ❌ “사용을 권장합니다.”

### UI 및 마케팅에서 금지되는 표현

절대 사용하지 않는다.

- ❌ AI 투자 코치
- ❌ 추천 전략 TOP 10
- ❌ 최고의 전략
- ❌ 2026년 유망 전략
- ❌ 지금 사야 할 종목
- ❌ 지금 팔아야 할 종목
- ❌ 고객 맞춤 전략
- ❌ 수익률 보장

### 권장 표현

사용 가능:

- ✅ 전략 연구소
- ✅ 투자 연구 플랫폼
- ✅ 백테스트 플랫폼
- ✅ 시뮬레이션 플랫폼
- ✅ 사용자 생성 전략
- ✅ 공개 전략
- ✅ 과거 성과 분석
- ✅ 연구 도구


## 개발 명령어

### 테스트
```bash
# 백엔드 (test_backtest_engine, test_engine_ai, test_ai_sell, test_api_isolation 제외 — 서버/AI 모델 필요)
cd backend && pytest tests/ --ignore=tests/test_backtest_engine.py --ignore=tests/test_engine_ai.py --ignore=tests/test_ai_sell.py --ignore=tests/test_api_isolation.py

# 단일 백엔드 테스트 파일
cd backend && pytest tests/test_engine_signals.py -v

# 단일 테스트 함수
cd backend && pytest tests/test_engine_signals.py::test_function_name -v

# 프론트엔드 (Vitest + jsdom)
npm run test:frontend
```


## 아키텍처

아키텍처 상세 내용은 [`docs/software_architecture.md`](docs/software_architecture.md)를 참고한다.

## 코드 설계 원칙

코드를 작성하거나 수정할 때 반드시 [`docs/coding_rules.md`](docs/coding_rules.md)의 원칙들을 준수한다.
(SOLID, DRY, KISS, YAGNI, SoC, LoD, Composition Over Inheritance, Boy Scout Rule, Fail Fast)

## 자연어 해석 구조 원칙

**자연어의 의미는 LLM만 해석한다. Regex는 LLM이 생성한 제한된 구조화 출력의 형식만 검증·정규화한다.**

Regex Parser가 사용자의 자연어를 직접 분석하거나 의미를 추론해서는 안 된다.

```text
사용자 자연어 입력
    ↓
LLM 의미 해석          (동의어·정성 표현·오타·문맥)
    ↓
제한된 구조화 출력      StrategyIntent JSON (schema_version 1.0)
    ↓
형식 검증·정규화        Regex / Pydantic field_validator
    ↓
Schema 검증            Pydantic StrategyIntent
    ↓
Domain 검증            Registry + validation/ (지표 지원 여부·범위·충돌·완결성)
    ↓
컴파일 → ParsedStrategy → 백테스트 엔진
```

### 역할 분담

| 레이어 | 책임 |
|---|---|
| **LLM** | 자연어 이해, 의도 분류, 동의어·정성 표현 매핑, 조건 변환, 수정 요청 인식, 누락 정보 탐지 |
| **Regex / 형식 정규화** | LLM 출력의 JSON 경계 추출, 코드펜스·꼬리 토큰 제거, 값·enum 표기 정규화 |
| **Schema Validator** | 필드 타입·필수 필드·허용 enum 검증 |
| **Domain Validator** | 지표 지원 여부, canonical 매핑, 값 범위·단위, 유니버스 호환성, 조건 충돌, 완결성·되묻기 |

### 판정 기준

> **입력이 사용자 원문이면 그것은 해석이다 → LLM.
> 입력이 LLM 출력이고 표기만 보면 결정 가능하면 그것은 정규화다 → 결정론 코드.**

### 금지 사항

- 사용자 원문(`user_input`)을 패턴 매칭해 지표·업종·의도·수치를 추출
- Regex로 동의어를 매핑하거나 누락 조건을 추론
- 검증 실패 시 Regex·후처리 코드가 문자열을 임의 보정 (→ 오류를 LLM에 전달해 재생성)
- 사용자가 말하지 않은 값을 질문 없이 기본값으로 확정 (→ 질문 / 추천값+확인 / 명시 허용 시에만 기본값)
- 지식 조회(업종·종목 정본 매핑)를 원문에서 수행 (→ LLM이 뽑은 짧은 문자열을 입력으로 받는 registry로)

상세 계약·출력 형식·코드 리뷰 체크리스트·현행 격차는 [`docs/nl_interpretation_contract.md`](docs/nl_interpretation_contract.md)를 따른다.
`engine/nl_parser.py`·`intent/strategy_builder.py`는 아직 이 계약을 위반한 상태이며 단계적으로 이관 중이다 —
**새로 작성하거나 수정하는 코드는 예외 없이 이 계약을 따른다.**

## 필수 규칙

### 코드 수정 후 유닛 테스트 전체 실행
코드를 수정할 때마다 반드시 모든 유닛 테스트를 실행하여 기존 기능이 깨지지 않았는지 확인한다.
- 테스트 실패 시 반드시 원인 파악 후 수정할 것 — 기존 버그라도 그냥 넘기지 말 것
- 사용자가 별도로 요청하지 않아도 자동으로 실행할 것

### 버그 수정 시 유닛 테스트 자동 추가
버그나 문제를 발견하고 수정한 경우, 해당 버그를 재현하는 유닛 테스트를 자동으로 추가한다.
- 이미 동일한 케이스를 검증하는 테스트가 있으면 추가하지 않는다
- 백엔드: `backend/tests/` 내 적절한 파일에 추가
- 프론트엔드: `components/__tests__/` 또는 `tests/`에 추가
- 사용자가 별도로 요청하지 않아도 자동으로 실행할 것

### 전략 예시(EXAMPLES) 추가·수정 시 파싱 검증 필수
`components/strategy/StrategyExampleTabs.tsx`의 예시를 추가하거나 문구를 바꾸면 **반드시 실제 파싱까지 돌려서 확인한다.**
```bash
python scripts/qa_template_detect.py --category <카테고리> --refresh   # 치명 0이어야 함(종료 코드 0)
```
- 어휘·상품명·업종이 정본에 매칭되는지 확인하는 것만으로는 부족하다 — 2026-07-27 사고: 매칭만 확인하고 파싱을 돌리지 않아 재무+랭킹 복합 예시가 빈 전략으로 나가는 것을 사용자가 먼저 발견했다
- 예시가 조건을 잃거나 되묻기로 빠지면 **예시 문구를 바꾸기 전에 파서 쪽 원인을 먼저 규명한다**(엔진이 표현할 수 없는 문구일 때만 예시를 고친다)

### 계획서 완료 표시 자동 업데이트
작업 완료 시 `docs/PROJECT_PLAN.md`의 해당 항목을 자동으로 `✅ 완료`로 업데이트한다.

### 작업 완료 후 관련 문서 자동 업데이트
작업이 끝날 때마다 작업 내용을 관련 문서에 반영한다. 최소한 아래 문서들 중 해당되는 문서를 검토하고 업데이트한다.
- `docs/PROJECT_PLAN.md`
- `docs/software_architecture.md`
- `docs/SRS.md`

### UI 가이드라인 준수
새 페이지나 컴포넌트 작성 시 반드시 `docs/UI_GUIDELINES.md`를 참고한다.
 기존 페이지 수정 시도 가이드라인과 불일치하는 부분이 있으면 맞춰서 수정할 것

---

# Behavioral Guidelines

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
