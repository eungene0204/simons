# Software Requirements Specification (SRS)
# Simons — 종합 투자 시뮬레이션 플랫폼

> **문서 버전:** v1.7
> **작성일:** 2026-04-01
> **최종 갱신일:** 2026-06-28
> **프로젝트명:** Simons
> **상태:** 작성 중

---

## 목차

1. [소개](#1-소개)
2. [전체 시스템 설명](#2-전체-시스템-설명)
3. [기능 요구사항](#3-기능-요구사항)
   - 3.0 [종목정보 프로필 저장 원칙](#30-종목정보-프로필-저장-원칙)
   - 3.1 [전략 설계](#31-전략-설계)
   - 3.2 [백테스트 엔진](#32-백테스트-엔진)
   - 3.3 [AI/ML 시스템](#33-aiml-시스템)
   - 3.4 [가상 매매 시스템](#34-가상-매매-시스템)
   - 3.4b [Strategy Research Agent (Premium)](#34b-strategy-research-agent-premium)
   - 3.5 [포트폴리오 관리](#35-포트폴리오-관리)
   - 3.6 [뉴스 Impact AI Agent](#36-뉴스-impact-ai-agent)
   - 3.6b [종목 질문 의도 분류·전략 전환 (구 Stock Analysis Agent)](#36b-종목-질문-의도-분류전략-전환-구-stock-analysis-agent)
   - 3.7 [시장 데이터 및 분석](#37-시장-데이터-및-분석)
   - 3.8 [사용자 관리](#38-사용자-관리)
4. [비기능 요구사항](#4-비기능-요구사항)
5. [데이터베이스 설계](#5-데이터베이스-설계)
6. [API 명세](#6-api-명세)
7. [인터페이스 요구사항](#7-인터페이스-요구사항)
8. [제약 사항](#8-제약-사항)

---

## 1. 소개

### 1.1 목적

이 문서는 Simons 플랫폼의 소프트웨어 요구사항을 정의한다. 개발팀이 구현해야 할 기능, 동작, 품질 속성의 기준을 명시한다.

### 1.2 범위

Simons는 사용자가 자신만의 주식 투자 전략을 **설계 → 검증 → 최적화 → 가상 실전 매매**까지 원스톱으로 수행할 수 있는 종합 투자 시뮬레이션 플랫폼이다. 한국 주식 시장(KOSPI, KOSDAQ)을 주 대상으로 하며, 향후 글로벌 시장으로 확장한다.

### 1.3 용어 정의

| 용어 | 정의 |
|------|------|
| 전략 (Strategy) | 진입/청산 조건, 리스크 관리, 포지션 규칙의 집합 |
| 백테스트 (Backtest) | 과거 데이터로 전략의 수익성을 사후 검증하는 과정 |
| 가상계좌 (VirtualAccount) | 실제 자금 없이 매매를 연습하는 페이퍼 트레이딩 계좌 |
| 시그널 (Signal) | 매수 또는 매도 조건이 충족되었음을 나타내는 이벤트 |
| 유니버스 (Universe) | 전략이 대상으로 삼는 종목 집합 (예: KOSPI200) |
| ParsedStrategy | 자연어 전략을 LLM이 파싱한 구조화된 전략 객체 |
| OHLCV | Open/High/Low/Close/Volume — 일봉 시가/고가/저가/종가/거래량 |
| MDD | Maximum Drawdown — 최고점 대비 최대 낙폭 |
| CAGR | Compound Annual Growth Rate — 연평균 복리 수익률 |
| SL/TP/TS | Stop Loss / Take Profit / Trailing Stop |
| XAI | Explainable AI — 설명 가능 인공지능 |
| Strategy Skeleton | 파싱 완료 전 사용자에게 즉시 표시하는 임시 전략 카드 |
| AI Runtime Metrics | parse, coach, summary 등 로컬 LLM 경로의 latency/queue wait 계측값 |
| Experience Memory | 과거 전략 조언의 전/후 성과, 성공/실패 평가, 재사용 가능한 lesson 저장소 |
| RAG | 현재 전략과 유사한 과거 프롬프트/DSL/조언 사례를 검색해 답변 컨텍스트로 사용하는 방식 |
| ListingStatus | 종목의 상장 상태 — NORMAL/WARNING/RISK/TRADING_SUSPENDED/DELISTING_REVIEW/DELISTING_SCHEDULED/DELISTED 7단계 |
| DelistingPolicy | 가상계좌의 상장폐지 처리 정책 — AUTO_LIQUIDATE / HOLD_AS_WORTHLESS / HOLD_WITH_MANUAL_REVIEW |
| DelistingAuditLog | 거래 차단·강제청산·상태 변경 이벤트를 기록하는 감사 로그 |
| News Raw DB | 수집된 원본 뉴스 저장소. title, url, source, published_at, raw_content, created_at 저장 |
| News Analysis | news_id 기준 뉴스 요약, 감성, 중요도, 영향도 분석 결과 |
| StockNewsCache | 종목 뉴스탭이 즉시 읽는 최종 캐시 저장소 |
| News Priority Engine | 사용자 행동과 시장 데이터를 조합해 종목별 뉴스 수집 우선순위를 계산하는 엔진 |
| Hot/Warm/Cold Queue | 뉴스 수집 주기를 우선순위별로 분리한 queue 계층 |

### 1.4 개요

이 문서는 다음 순서로 구성된다:
- **섹션 2:** 시스템 개요 및 아키텍처
- **섹션 3:** 모듈별 기능 요구사항 (FR)
- **섹션 4:** 비기능 요구사항 (NFR)
- **섹션 5:** 데이터베이스 설계
- **섹션 6:** API 명세
- **섹션 7:** UI/UX 인터페이스 요구사항

---

## 2. 전체 시스템 설명

### 2.1 기술 스택

| 레이어 | 기술 |
|--------|------|
| **프론트엔드** | Next.js 14 (App Router), React 18, TypeScript, Tailwind CSS, Recharts |
| **API 레이어** | Next.js API Routes (70개+), FastAPI (Python) |
| **백엔드 엔진** | Python FastAPI, Polars/Pandas, vectorbt |
| **AI/ML** | PyTorch (Transformer), XGBoost, SHAP, Optuna |
| **DB** | SQLite + Prisma ORM |
| **데이터** | Parquet (4,052 종목 OHLCV), KRX Open API, Naver Finance, yfinance |

### 2.2 시스템 아키텍처

```
[브라우저]
    │
    ▼
┌──────────────────────────────┐
│  Next.js 14 (App Router)     │
│  - 페이지 라우팅              │
│  - API Routes (Prisma 직접)  │
└──────────────┬───────────────┘
               │ HTTP
               ▼
┌──────────────────────────────┐
│  FastAPI Backend             │
│  - /backtest (SSE 스트림)    │
│  - /strategy/parse (NLP)     │
│  - /virtual-market           │
└──────────────┬───────────────┘
               │
    ┌──────────┼──────────┐
    ▼          ▼          ▼
[DataLoader] [SignalEngine] [AIEngine]
    │          │              │
    └──────────┴──────────────┘
               │
            [Simulator]
               │
          [ResultHandler]
```

### 2.3 타겟 사용자

| 사용자 유형 | 특성 | 주요 기능 |
|------------|------|-----------|
| 초급 투자자 | 투자 방법론 미보유 | 프롬프트 기반 전략 생성, 백테스트 결과 시각화 |
| 중급 트레이더 | 기술적 분석 활용 | 자연어 전략 설계, 대화형 파라미터 조정 |
| 고급 퀀트 | 알고리즘 트레이딩 연구 | AI 모델 결합, Optuna 최적화, XAI 분석 |

---

## 3. 기능 요구사항

### 3.0 종목정보 프로필 저장 원칙

**FR-SIP-001** 시스템은 `/stock-order` 종목정보 탭에서 사용하는 비실시간 종목정보를 DB에 저장해야 한다.

**FR-SIP-002** 저장 대상은 다음 필드로 제한해야 한다:
- 종목 기본 정보: `symbol`, `name`, `listingDate`, `sector`
- 회사 기본 정보: `establishmentDate`, `representativeName`, `employeeCount`, `homepageUrl`, `englishName`, `disclosureName`, `businessRegistrationNumber`, `settlementMonth`, `address`, `mainBusiness`
- 재무 요약 정보: `businessYear`, `statementType`, `sales`, `operatingProfit`, `netIncome`, `totalAssets`, `totalLiabilities`, `totalEquity`, `debtRatio`
- 밸류에이션 정보: `pe`, `pbr`

**FR-SIP-003** 시스템은 전체 종목에 대해 위 종목정보를 선적재할 수 있어야 한다.

**FR-SIP-004** `/api/stock/[symbol]/detail` 는 종목정보 탭 필드에 대해 DB를 우선 조회해야 한다.

**FR-SIP-005** DB 값이 존재하지 않는 경우에만 외부 종목정보 조회를 수행하고, 성공 시 즉시 DB에 저장해야 한다.

**FR-SIP-006** 시스템은 실시간 시세(`currentPrice`, `changePercent`, `change`, `open`, `high`, `low`, `volume`)를 종목정보 프로필 저장 대상에 포함하면 안 된다.

**FR-SIP-007** 시스템은 `52주 고저`, 차트 시계열, 캔들 데이터처럼 종목정보 탭에서 사용하지 않는 필드를 종목정보 프로필 저장 대상에 포함하면 안 된다.

### 3.1 전략 설계

#### 3.1.1 자연어 프롬프트 기반 전략 생성

**FR-STR-001** 시스템은 사용자의 한국어 자연어 입력을 받아 구조화된 투자 전략으로 자동 변환해야 한다.

**FR-STR-002** LLM 파싱 결과는 다음 항목을 포함해야 한다:

| 필드 | 타입 | 설명 |
|------|------|------|
| `universe` | `List[str]` | 투자 유니버스 (KOSPI / KOSDAQ / KOSPI200) |
| `fundamental_filters` | `List[FundamentalFilter]` | PBR, PER, ROE, 부채비율, 시총, 거래대금 |
| `entry_signals` | `List[TechnicalSignal]` | 매수 조건 (MA, RSI, MACD, 볼린저 등) |
| `exit_signals` | `List[TechnicalSignal]` | 매도 조건 |
| `max_positions` | `int` | 최대 동시 보유 종목 수 |
| `hold_period_days` | `Optional[int]` | 보유 기간 (일). 랭킹 전략에서 `rebalancing_period`가 활성화되면 회전이 리밸런싱으로 구동되므로 `None` 처리 |
| `ranking_metric` | `Optional[Literal["return"]]` | 종목 선정 기준 (현재 "최근 N일 수익률 상위" 모멘텀 랭킹만 지원) |
| `ranking_lookback_days` | `Optional[int]` | 모멘텀 랭킹 수익률 계산 기간 (일). 미지정 시 60일 기본 |
| `rebalancing_period` | `Literal["none","daily","monthly","quarterly","yearly"]` | 달력 기준 리밸런싱 주기. `none`이 아니면 매 주기 첫 거래일에 목표 집합(상위 K)을 재구성(reconstitution)한다 |
| `stop_loss_pct` | `Optional[float]` | 손절선 (%) |
| `take_profit_pct` | `Optional[float]` | 익절선 (%) |
| `backtest_period` | `str` | 백테스트 기간 (`1y` / `3y` / `5y` / `full`) |
| `backtest_start_date` / `backtest_end_date` | `Optional[str]` | 명시적 연·월·일 범위(`"2002년부터 2005년까지"`, `"2020년 1월부터 2025년 12월까지"`)에서 결정적으로 추출한 `YYYY-MM-DD`(종료 월은 말일, 불가능한 날짜는 미인식 처리). 있으면 상대 기간 대신 이 창으로 백테스트(엔진 `startDate`/`endDate`). LLM 인터프리터 primary 경로에서도 결정적 추출이 최종 덮어쓴다(오늘 날짜를 모르는 모델의 미래 오판·누락 방어, 2026-07-17) |
| `initial_capital` | `int` | 초기 투자금 (원) |

**FR-STR-003** 사용자는 파싱된 전략을 대화형으로 수정할 수 있어야 한다 (점진적 수정 모드).

**FR-STR-004** 시스템은 파싱 결과 요약 (유니버스, 필터, 시그널, 리스크 설정)을 사용자가 확인할 수 있도록 표시해야 한다.

**FR-STR-005** 지원 LLM 백엔드:
- MLX (Apple Silicon 최적, 기본값): `mlx-community/Qwen3.5-4B-4bit`
- Ollama (범용): `hf.co/unsloth/Qwen3.5-4B-GGUF:Q4_K_M`

**FR-STR-013** 시스템은 자연어 전략 파싱 요청을 SSE로 처리할 수 있어야 하며, 파싱 완료 전 `accepted` 및 `skeleton` 이벤트를 반환해야 한다.

**FR-STR-014** 시스템은 명확한 정량 조건(PBR/PER/ROE, 보유 기간, 포지션 수, 손절/익절/트레일링 스탑 등)을 deterministic extractor로 우선 파싱하여 불필요한 LLM 호출을 줄여야 한다.

**FR-STR-015** 시스템은 LLM이 tail-truncated JSON을 반환한 경우 가능한 범위에서 JSON을 복구해야 하며, 복구 실패 시 500 오류 대신 안전한 fallback ParsedStrategy를 반환해야 한다.

**FR-STR-016** 시스템은 파싱 직후 백테스트를 자동 실행하면 안 된다. 백테스트는 사용자가 명시적으로 실행 버튼을 누른 경우에만 시작해야 한다.

**FR-STR-017** 시스템은 파싱 응답 생성 시 불필요한 전체 유니버스 심볼 해석을 지연하고, 실제 백테스트 실행 시점에 필요한 종목 해석을 수행해야 한다.

**FR-STR-018** 시스템은 "박스권을 위로 돌파", "N일 고점/신고가 돌파" 등 서술형 돌파 표현을 `breakout` 진입/청산 신호로 인식하고, 표현에서 lookback 기간(N일, 명시 없으면 박스권 기본 20일/52주는 252일)을 추출해야 한다.

**FR-STR-019** 자연어 표현/키워드 대응은 케이스별 정규식을 무한정 추가하는 방식이 아니라 하이브리드로 처리해야 한다: 핵심·빈출 시그널(`ma_crossover`, `breakout`, `volume_spike` 등 서술형 지표)은 결정적 규칙으로 빠르게 처리하고, 긴 꼬리 표현은 LLM 프롬프트의 few-shot 예시로 위임한다. 이때 LLM 환각 방지 키워드 검증은 서술형 지표에 대해서는 건너뛰고 모델 출력을 신뢰해야 한다 (과도한 검증이 올바른 서술형 파싱 결과를 거부하는 것을 방지).

**FR-STR-019b** 수정 모드 환각 게이트(`_gate_modification_hallucinations`)의 리스크 필드(손절/익절/트레일링/MDD) 판정은 '결정적 추출 성공 여부'가 아니라 '프롬프트 내 필드 cue 존재 여부'를 기준으로 해야 한다. 결정적 추출의 침묵은 "요청 없음"과 "정규식이 못 푼 구어체"(예: "50% 이상 수익이 나면 주식을 파는 걸로 하자")를 구분하지 못하므로, 추출 실패를 근거로 LLM diff의 올바른 해석을 이전 값으로 되돌리면 안 된다. cue가 없으면 환각으로 차단하고, cue는 있는데 값을 못 풀었으면 LLM을 신뢰한다(FR-STR-019의 하이브리드 원칙을 게이트에도 적용).

**FR-STR-019c** [수정 경로 펀더멘털 필터, 2026-07-14] 수정 요청의 펀더멘털 필터 변경은 두 층으로 처리해야 한다. ① 값이 명시된 요청("영업이익률 15% 이상 조건 추가해줘")은 결정론 fast-path(`_modify_rule_based`)가 `_extract_fundamental_filters`+`_merge_fundamental_filters`(같은 지표 갱신·새 지표 추가·기존 보존)로 LLM 없이 즉답한다. ② 값이 없거나 복합인 요청("영업이익률을 추가해 볼까?")은 LLM diff 경로로 위임하되, LLM diff의 `fundamental_filters`는 통째 대체 의미론이고 few-shot이 새 필터만 출력하는 경향이 있어 언급 안 된 기존 필터가 소실될 수 있으므로, **제거 의도(`_REMOVE_INTENT_RE`)가 없는 발화에서는 결정적 병합 보정(`_merge_fundamental_filters`)이 LLM diff에 우선**해야 한다(섹터 보정과 동형). 제거/해제 발화는 LLM이 낸 전체 목록(빠진 항목=삭제 의도)을 존중해 병합으로 삭제 항목을 되살리지 않는다. 수정 LLM의 지식원(modify RAG knowledge)에는 지원 metric 전체 목록과 "미지원 지표는 diff에 넣지도 유사 지표로 대체하지도 않는다" 규칙을 명시한다(미지원 안내는 FR-STR-023d의 notices가 담당).

**FR-STR-019d** [수정 경로 재무 팩터 추가 되묻기, 2026-07-14] 기존 전략 요약 카드에 값(operator·threshold) 없이 재무 팩터를 추가하려는 발화("영업이익률을 추가해 볼까?")는 LLM 수정 파서로 넘겨 임의 기준값을 환각하게 두지 말고, `parse_modification` 호출 **전에** 결정적으로 가로채 그 지표의 기준을 되묻아야 한다(`intent/condition_builder.clarification_for_add` — 추가 cue + 지원 재무 지표(21종) 감지 + 값 없음 판정, 정의 질문·값 명시·복합 발화는 제외). 되묻기는 전략을 변경하지 않고(`previous_parsed` 그대로) `clarification_question`("영업이익률 몇% 이상일 때 진입할까요?")과 `clarification_suggestions`(관례 방향의 추천 4칩)만 응답에 실어 반환한다. 칩은 클릭 시 그대로 수정 메시지로 재전송되므로 **라벨이 붙은 완결 지시문**("영업이익률 15% 이상")이어야 하며(`handleSuggestionClick→handleSend`), "직접 입력" 칩은 프론트가 자동으로 덧붙인다(백엔드 무상태 — 칩 답변은 FR-STR-019c ①의 결정론 fast-path가 기존 필터를 보존한 채 병합해 완성). 이 되묻기를 결정론 fast-path가 유지하려면 수정 잔여 검사(`_modify_residual_is_clean`)의 펀더멘털 cue 목록(`_MODIFY_FIELD_CUES["fundamental_filters"]`)이 지원 지표 어휘(배당수익률·배당성향·배당성장률·EV/EBITDA·마진/성장률 변형 철자 포함)를 `_FUNDAMENTAL_PATTERN_SPECS`와 동기화해야 한다(누락 시 추출은 되나 잔여 오판으로 fast-path가 LLM으로 샘). 기존 `detect_missing_entry_clarification`(정성 표현 7종, 최초 파싱 경로)과 별개로 수정 경로에서만 적용한다.

**FR-STR-019e** [코치 맥락 리스크 해석 백엔드 이관, 2026-07-15] 코치가 특정 리스크 필드 설정을 권한 뒤("익절 비율 설정을 추천드립니다") 사용자가 필드를 밝히지 않고 "10%"처럼 답하면, 그 값을 코치가 물은 리스크 필드로 귀속해야 한다. 이 판단은 **백엔드**가 수행한다(`resolve_coach_context_risk`) — 파스 요청에 직전 코치 문장(`previous_coach_text`)을 실어 보내고, 백엔드가 ① 프롬프트가 이미 리스크 필드를 명시했으면(결정적 추출이 잡음) 건너뛰고 ② 필드 없는 퍼센트 답변이면 코치 문장에서 지목된 필드(하나만 언급 시 그것, 여럿이면 미설정 필드가 하나일 때 그것)로 귀속해 `parsed`에 반영한다(그러면 `synthesize_risk_overrides`가 `parsed` vs `previous` 차이로 `risk_overrides`에도 담아 단일 진실 소스로 흐른다). [원칙: 프론트는 백엔드 판단을 재판정하지 않는다] 예전에는 프론트가 코치 텍스트를 정규식으로 재판정해(`inferPendingRiskChange`) 백엔드 파스 결과에 값을 얹었으나, 이는 프론트가 백엔드 출력에 자기 판단을 덧대는 안티패턴이라 백엔드로 이관했다. 함께, 소비처 없이 백엔드 되묻기를 재판정하던 죽은 로직(`shouldReusePreviousClarification`/`clarificationLooksLikeEntryRegression`)도 제거했다. 프론트의 `mergeStrategyModification`은 백엔드가 병합·환각필터링·코치맥락해석을 마친 `parsed`와 `risk_overrides`를 그대로 신뢰하며, 유일하게 남은 후처리는 `risk_overrides`를 명시적으로 재적용해 일관성을 보장하는 것뿐이다(재판정 아님).

**FR-STR-020** 시스템은 규칙 기반 파서가 수락한 파싱 결과에 대해, 원문 입력과 파싱된 전략 객체를 LLM으로 비교 검증해야 한다(Parse Fidelity Validator, `engine/parse_validator.py`). 검증은 구조화된 리포트(`parse_validation`: `isValid`, `confidence`, `issues[]`, `missingFields[]`, `clarificationQuestions[]`, `correctedStrategy`, `userFacingMessage`)를 `/strategy/parse` 응답에 포함해야 하며, 누락 필드·모호한 조건·실행 불가능한 조건·원문에 없는 과잉 추론 여부를 점검해야 한다. 검증기는 새 전략을 만들거나 성능을 위해 전략을 개선하거나 투자 자문·추천을 하지 않아야 하며, 검증·명백한 파싱 오류 교정·명확화 질문만 수행해야 한다. LLM 출력 계약은 검증 시간 최소화를 위해 diff 형식이어야 한다: 파스가 충실하면 `{isValid, confidence}`만 출력하고, 명백한 파싱 오류는 `correctedFields`(바뀌어야 하는 필드만)로 출력하며 서버가 원본 파스와 병합해 `correctedStrategy`(전체 객체, 하류 계약)를 구성한다. 검증 LLM에 보내는 파싱 JSON은 null 필드를 생략한다(프롬프트에 '누락=null' 명시). 병합 교정본은 `ParsedStrategy` 스키마 검증을 통과할 때만 적용하고(미지 필드는 병합 전 필터) 원문 `description`은 보존해야 한다. LLM에 도달할 수 없거나(서버 없음/콜드스타트) 검증이 실패하면 빠른 경로(규칙 기반 즉답)를 막지 않도록 즉시 graceful degrade하여 원본 파싱 결과를 그대로 반환해야 한다. 검증 발화 시 룰 파스가 설명하지 못한 잔여 어휘를 로그로 남겨야 한다(빈출 무해 토큰을 어휘집에 보강해 검증 호출 빈도를 줄이는 운영 루프의 입력). 검증 전용 경량 모델은 `NL_VALIDATOR_MODEL`(env)로 opt-in 지정할 수 있다.

**FR-STR-020b** `correctedStrategy` 자동 교정은 스키마 검증만으로 적용해서는 안 되며, 교정본의 진입/청산 신호를 LLM 파싱 본경로와 동일한 환각 방지 키워드 검증(`_validate_signals`: 이름 고정 지표는 원문에 해당 키워드가 있어야 인정)으로 재검증해야 한다. 검증에 실패한 환각 신호(예: 원문에 AI 언급이 없는데 주입된 `ai_model` 'AI 매수 예측')만 떨구고 나머지 정상 교정 필드는 유지한다. (실사례 2026-07-03: KOSDAQ 모멘텀 랭킹 프롬프트에 교정 LLM이 `ai_model` 진입 신호를 환각 주입 → 스키마 검증만 통과해 적용 → 비활성화된 AI 백테스트가 실행되며 무한 대기.)

**FR-STR-020c** `correctedStrategy`의 `universe` 필드는 원문 기준 결정적 추출(`_extract_explicit_universe`)과 다르면 항상 결정적 추출값으로 되돌려야 한다. 유니버스는 KOSPI/KOSDAQ/KOSPI200 어휘 매핑일 뿐이라 교정 LLM이 개선할 여지가 없고, 되돌리지 않으면 유니버스 확대로 인한 심각한 성능 저하만 남는다(단, `max_positions` 등 숫자 필드의 정당한 교정은 그대로 존중한다). (실사례 2026-07-05: "KOSPI 대형주 중에서 PBR이 1배 이하인 종목..." 프롬프트가 룰 파싱 잔여 미해석으로 LLM 검증을 타고, 교정본이 유니버스를 KOSPI200→KOSPI로 되돌려 200종목이 전체 코스피(800+ 종목)로 확대 → 백테스트가 크게 느려져 전략연구소 화면이 멈춘 것처럼 보임.)

**FR-STR-020d** SSE 파싱 경로(`/strategy/parse-stream`)에서 LLM 검증은 비차단(후행)이어야 한다: 룰 파스 결과를 먼저 `result` 이벤트로 전송하고, 검증은 스트림을 연 채 후행 실행하며(`_run_nl_parse`의 defer_holder → `_complete_deferred_validation`), 교정이 적용된 경우에만 `result_update` 이벤트로 갱신본을 후속 전송한다. 파싱 캐시도 교정본으로 갱신해 동일 프롬프트 재요청이 교정 전 결과를 반환하지 않아야 한다. 후행 검증 중에는 `validating` stage 이벤트를 보내지 않아야 하며(프론트가 로딩 표시로 되돌아가 요약이 사라지는 회귀 방지), 프론트(`parsed_updated` 이벤트)는 사용자가 이미 백테스트를 실행/완료한 뒤 도착한 교정은 무시해야 한다(실행 스냅샷 일관성). 후행 검증 대기는 프록시 스트림 예산(120s) 미만으로 상한을 두고 초과 시 결과를 폐기한 채 스트림을 닫는다. 비스트림 `/strategy/parse`는 인라인 검증을 유지한다.

**FR-STR-021** 시스템은 "최근 N일/N거래일/N개월 수익률이 높은 종목 상위 K개"와 같은 상대강도(모멘텀) 랭킹 표현을 인식하여 `ranking_metric="return"`과 `ranking_lookback_days`(미지정 시 60일 기본)를 추출해야 하며, 랭킹 전략에 리밸런싱 주기가 명시되지 않은 경우 `monthly`를 기본값으로 적용해야 한다. 단, 회전 수단이 없는 펀더멘털 스크리닝 전략의 기본 월간 리밸런싱은 사용자가 리밸런싱을 명시적으로 거부한 경우("리밸런싱 없이 계속 보유")에는 주입하지 않고 `none`(매수 후 계속 보유)으로 보존해야 한다 — 랭킹 전략은 회전이 달력 리밸런싱으로만 동작하므로(엔진 제약) 거부 표현이 있어도 유지한다.

**FR-STR-022** 시스템은 진입 의도가 있는 자연어 입력에서 파싱 결과에 진입 신호/펀더멘털 필터/랭킹 기준이 모두 비어 조용히 누락된 경우, 사용자에게 명확화 질문과 대안 제안(클릭 가능한 칩)을 표시해야 한다. 이때 일반적인 누락 사례와 "엔진이 아직 지원하지 않는 상대강도 랭킹 표현" 사례를 구분하여 각각 다른 안내 문구와 대안을 제공해야 한다 (서로 다른 원인이므로 동일한 메시지로 뭉뚱그리면 안 됨). 첫 파싱에서는 백엔드가 보낸 구체적 안내를 우선 사용한다. [2026-07-19 확장] ETF 유니버스 전략("etf를 사는 전략은 어때?")도 별도 사례로 구분한다 — ETF에는 개별 기업 재무지표(PER·PBR·ROE)가 없으므로 재무 필터 예시 칩(일반 안내)을 그대로 보여주면 오답이며, ETF에 통용되는 가격·추세 기반 방식(이동평균 추세추종·모멘텀/신고가 돌파·RSI 평균회귀·MACD·정기 리밸런싱)의 예시 칩으로 진입 조건을 묻는다(`nl_parser._ETF_PRODUCT_QUESTION`). 임계값 되묻기("PER은 몇 이하로 할까요?")보다 이 안내가 우선하며, 기술 신호가 이미 추출된 경우에는 되묻지 않고 그대로 실행한다(ETF는 정식 지원 유니버스 — FR-STR-067). ETF 전략에 기업 재무지표가 실제로 섞인 경우는 FR-STR-067 ④의 충돌 되묻기가 먼저 가로챈다.

**FR-STR-023** 시스템은 매수(종목 선정) 기준이 전혀 없는 전략(진입 신호·펀더멘털 필터·랭킹 기준이 모두 비어 백테스트가 0매매로 끝나는 경우)에 대해 백테스트 실행을 막아야 한다. 이 판정은 실제 백테스트로 전달되는 병합된 전략을 기준으로 하므로 최초 파싱뿐 아니라 점진적 수정 이후에도 적용되어야 하며, 매수 기준이 빠진 상태에서는 "백테스트 실행" 버튼을 노출하지 않고 최소 조건을 입력하도록 명확화 안내를 표시해야 한다. (청산·리스크 설정만으로는 살 종목을 선정할 수 없으므로 매수 기준으로 인정하지 않는다.)

**FR-STR-023b** 백테스트 결과 화면의 "프롬프트" 배지(진입 신호 / 청산 신호)는 사용자가 정의한 전략 요약을 그대로 표시해야 한다 — 진입 신호 섹션은 `entryBlocks`(진입 신호·펀더멘털 필터)만 렌더링하고, 비어 있으면 섹션을 숨긴다. 진입 신호·청산 신호가 섞인 `blockNames` 폴백으로 떨어져선 안 된다(매수 기준 없이 익절만 있는 전략에서 청산 배지가 진입에 누출되던 버그 방지). 이는 표시 전용이며 백테스트 엔진은 진입 조건을 `fundamental_filters`+`entry_signals`로, 청산 조건을 `exit_signals`로 분리해 구성하므로(`strategy_converter.to_backtest_request`) 실행 DSL에는 누출이 없다.

**FR-STR-023c** 시스템은 전략 설정값의 하한선을 강제해야 한다(`enforce_strategy_minimums`, 규칙/LLM/수정 모드 무관 모든 파싱 경로 뒤에서 적용). 하한 미만 입력은 자동 보정/제거하고, 사용자에게 보정 내용을 전략 요약과 함께 비차단(non-blocking) 방식으로 안내해야 한다. 안내는 매수 기준 명확화(`clarification`)와 달리 전략 요약 카드를 숨기지 않는다(`notices` 채널).

**FR-STR-023d** 시스템은 스키마(`ParsedStrategy`)가 표현할 수 없는 미지원 개념(배당·섹터·변동성·수급·분할매도·거래량 배수("평소 대비 N배" — `volume_spike`는 OBV 크로스오버라 배수 임계값 표현 불가) 등, `nl_parser._UNSUPPORTED_CONCEPT_PATTERNS`)이 프롬프트에 언급되면, LLM 폴백 위임(부분 파싱 침묵 누락 방지)과 별개로 사용자에게 해당 조건이 "아직 직접 지원되지 않아 반영되지 않았거나 다르게 해석됐을 수 있다"는 안내를 `notices` 채널로 제공해야 한다(`build_unsupported_concept_notice`). LLM 폴백조차 스키마 제약으로 이 개념들을 정확히 표현할 수 없으므로, 조용한 유사 해석 대신 명시적으로 알리고 전략 요약 확인을 유도한다. [2026-07-14 확장] 데이터 파이프라인이 없는 흔한 퀀트 팩터도 같은 채널로 안내한다: ROIC(투하자본이익률), 베타, 이자보상배율, 피오트로스키/알트만 점수, 회전율(재고·매출채권 등), 자사주 매입, PCF/주가현금흐름(기존 cash_flow 항목 확장). (ETF/ETN은 2026-07-19 같은 날 잠시 `etf_product` 항목으로 이 목록에 추가되었다가 ETF 정식 유니버스 승격(FR-STR-067)으로 즉시 제거되었다 — 개념 구현 시 목록에서 제거하는 원칙의 적용 사례.) **단 EV/EBITDA(에비타)는 KIS other-major-ratios 배선(2026-07-14)으로, 배당수익률·배당성향·배당성장률은 KIS 예탁원 배당 API 배선(2026-07-14)으로 데이터가 확보되어 지원 지표로 승격되었으므로 미지원 목록에서 제거되었다**(수치 있는 배당수익률/배당성향/배당성장률 필터가 추출되면 `배당` 안내를 억제하는 조건부 제외 방식 — 수치 없는 막연한 '배당주/배당 성장주' 언급만 미지원 안내 유지) — 데이터 파이프라인 구현 시 목록에서 제거하는 원칙의 실제 적용 사례. 이 안내는 최초 파싱과 수정 요청 모두에 적용된다(`_build_parse_result` 공유). 지원 지표(영업이익률·순이익률·매출총이익률 등 마진류)는 절대 미지원 목록에 넣지 않는다(오폴백 방지) — 해당 팩터의 데이터 파이프라인을 구현하면 목록에서 제거해야 한다.
- **초기자금:** 최소 100만원. 미만이면(예: "초기자금 300으로"가 300원으로 해석) 100만원으로 보정 후 "최소 초기자금은 100만원입니다" 안내. 단위 없는 맨숫자는 자본금 cue에 인접한 경우에만 만원 단위로 해석한다("초기자금 300"=300만원).
- **보유기간:** 최소 1일. 0/음수면 1일로 보정.
- **모멘텀/랭킹 기준 기간:** 최소 10일. 미만이면(예: "최근 3일 수익률") 10일로 보정(너무 짧으면 노이즈).
- **손절·익절·트레일링 스탑·MDD 비율:** 0%면 적용하지 않음(드롭) — 양수 하한이 자연스럽지 않아 비현실적 값만 제거. 음수 입력("손절 -8%")은 하락 폭의 크기를 뜻하므로 드롭 대상이 아니라 모델 검증(`ParsedStrategy`/`ParsedStrategyDiff` field validator)이 절댓값으로 정규화한다 — LLM이 사용자의 부호를 그대로 옮겨도 "0%보다 커야" 오탐 안내가 나가지 않는다.
- **투자 종목 수:** 추출기(0종목→1)와 스키마(`ge=1, le=100`)가 이미 1로 바닥을 깔아 별도 보정 불필요.

#### 3.1.1b AI 전략 코치

**FR-STR-006** 시스템은 전략 파싱 완료 이후 전략 코치 응답을 채팅 흐름 안의 말풍선으로 표시해야 하며, 파싱 응답의 critical path를 막으면 안 된다.

**FR-STR-007** 코치 응답은 다음 두 정보를 컨텍스트로 활용해야 한다:
1. `advisor_insight` — rule-based 전략 진단 (전략 점수, 리스크 점수, 주요 이슈, 추천)
2. `news_agent_insight` — 뉴스 Impact Agent 분석 결과 (종목별 alpha, risk_alert_level)

**FR-STR-008** `news_agent_insight`가 존재하면 advisor_insight보다 우선 반영해야 한다. `risk_alert_level`이 high인 종목이 전략에 포함되면 리스크 경고를 최우선 조언으로 제시해야 한다.

**FR-STR-009** 코치 응답은 비동기 요청으로 전달되어야 하며, 분석 중에는 대화창에 로딩 상태를 표시하고 결과 도착 시 같은 말풍선을 최종 조언으로 갱신해야 한다.

**FR-STR-010** 코치 응답은 300자 내외의 핵심 조언 또는 구조화된 advice list를 사용자용 짧은 문장으로 변환해 표시해야 한다.

**FR-STR-011** 코치는 조언을 길게 나열하지 않아야 하며, 화면에는 우선순위 상위 3개까지만 표시해야 한다.

**FR-STR-012** 시스템은 rule-based clarification 텍스트를 채팅에 표시하지 않아야 한다. 모든 사용자 안내 텍스트는 AI 코치 응답으로만 제공된다.

**FR-STR-024** 전략 요약은 일반 말풍선이 아니라 별도 카드로 표시해야 한다. 카드는 라운드 처리된 노란색 테두리만 사용하고 배경색을 넣지 않아야 한다.

**FR-STR-025** 전략 만들기 화면은 오른쪽 고정 전략 코치 패널을 표시하지 않아야 한다. 코칭 결과는 대화창 말풍선에서만 제공되어야 한다.

**FR-STR-026** 코치 말풍선은 사용자에게 RAG, Experience Memory, 유사 전략, 과거 사례 같은 내부 근거 출처를 직접 설명하지 않아야 한다. 최종 문구는 성과 신호, 비교 후보, 리스크 관리 조치 중심의 조언이어야 한다.

**FR-STR-027** 코치 말풍선은 우선순위 상위 조언 최대 3개만 표시해야 한다. 추가 조언은 백테스트 결과 확인 후 필요한 항목만 이어서 본다는 짧은 안내로 접어야 한다.

**FR-STR-028** 코치 말풍선은 `백테스트 학습 사례 N건 기준`, `CAGR 중앙값`, `Sharpe 중앙값`, `MDD 중앙값`, `Profit Factor 중앙값`, `거래 수 중앙값`, `각각 바꿔 테스트`, `MDD와 Sharpe가 동시에 좋아지는 설정` 같은 과거 learning 템플릿 문구를 사용자에게 표시하면 안 된다.

**FR-STR-029** 코치 시스템은 advisor_result 또는 LLM 출력에 과거 learning 템플릿 문구가 포함되더라도 이를 그대로 인용하거나 요약하면 안 되며, 최종 응답에서는 같은 기간과 비용 조건으로 백테스트하고 변경은 한 번에 하나씩 비교하라는 실행 가능한 안내로 대체해야 한다.

**FR-STR-018** 시스템은 동일한 전략/프롬프트에 대한 코치 응답을 캐시하고, 동시에 들어온 동일 요청은 in-flight dedupe로 하나의 LLM 호출을 공유해야 한다.

**FR-STR-019** 시스템은 코치 SSE 응답을 replay 가능한 형태로 캐시하여 동일 요청의 반복 스트림에서 중복 LLM 추론을 피해야 한다.

#### 3.1.1c RAG + Experience Memory 전략 Advisor

**FR-ADV-001** 시스템은 사용자 전략 프롬프트와 ParsedStrategy를 기반으로 Strategy DSL JSON을 생성하고 canonical string으로 직렬화해야 한다.

**FR-ADV-002** 시스템은 canonical Strategy DSL의 SHA-256 hash를 `strategy_id`로 사용해야 한다.

**FR-ADV-003** 동일 `strategy_id`의 백테스트 결과가 이미 저장되어 있으면 불필요한 백테스트 재실행 없이 기존 결과를 재사용해야 한다.

**FR-ADV-004** Advisor는 조언 생성 전에 현재 프롬프트, 현재 DSL, 현재 `strategy_id`, 현재 백테스트 결과를 컨텍스트로 포함해야 한다.

**FR-ADV-005** Advisor는 텍스트 기반 유사도 검색을 수행해야 한다. 검색 대상은 `user_prompt`, `strategy_summary`, indicator 이름, entry/exit/risk 설명, 과거 `agent_advice_text`를 포함한다.

**FR-ADV-006** Advisor는 DSL 구조 기반 유사도 검색을 수행해야 한다. 검색 대상은 indicators, entry/exit rules, filters, position sizing, stop loss, take profit, rebalance rule, universe, timeframe, parameter values를 포함한다.

**FR-ADV-007** 텍스트가 유사하더라도 DSL 구조가 다르면 낮은 유사도로 취급해야 하며, 표현이 달라도 DSL 구조가 유사하면 유사 전략으로 취급해야 한다.

**FR-ADV-008** Advisor는 Experience Memory에서 과거 유사 전략의 before/after metrics, 조언 내용, 성공 여부, lesson을 검색해야 한다.

**FR-ADV-009** Advisor는 현재 전략의 백테스트 결과와 내부 learning evidence를 비교하여 핵심 문제점을 진단해야 한다.

**FR-ADV-010** Advisor는 현재 전략에 적용 가능한 개선 후보 Strategy DSL을 생성할 수 있어야 한다.

**FR-ADV-011** 가능하면 개선 후보를 동일 조건으로 재백테스트하고, 개선 전/후 결과를 비교해야 한다.

**FR-ADV-012** Advisor는 조언 성공 여부를 CAGR만으로 판단하면 안 되며, CAGR, MDD, Sharpe, Sortino, Calmar, Profit Factor, win rate, trade count, turnover, 비용/슬리피지, OOS/WFA 결과를 종합 평가해야 한다.

**FR-ADV-013** Advisor는 초기자금, 포지션 크기, 유동성 조건, 거래비용, 슬리피지를 고려해 개인 투자자에게 비현실적인 조언을 피해야 한다.

**FR-ADV-014** Advisor는 모든 조언 결과를 `AdviceExperience`에 저장해야 한다. 저장 정보는 전략, 문제점, 조언, 조언 전/후 성과, 개선/악화 지표, 성공 여부, 실패 이유, 재사용 가능한 lesson을 포함해야 한다.

**FR-ADV-015** Advisor 답변은 내부 근거 출처를 나열하지 않고 사용자가 바로 실행할 수 있는 조언으로 압축되어야 한다. 권장 순서는 성과 신호 요약 → 비교할 후보 조건 → 리스크 관리 기준 → 다음 백테스트 판단 기준이다.

**FR-ADV-016** 유사 사례가 부족하면 Advisor는 데이터 부족을 명확히 표시하고, 일반 퀀트 원칙 기반의 낮은/중간 신뢰도 조언으로 제한해야 한다.

**FR-ADV-017** Advisor는 10,000건 이상 규모의 대표 smoke sample 백테스트 결과를 learning artifact로 사용할 수 있어야 한다. artifact는 sample_id 기준으로 source/resume run을 병합해 중복 없이 생성되어야 한다.

**FR-ADV-018** Advisor는 `CAGR`, `Sharpe`, `MDD`뿐 아니라 `Profit Factor`, 거래 수, 유사도 품질을 함께 고려해 confidence를 조정해야 한다.

**FR-ADV-019** Advisor는 성과 중앙값이 모두 0에 가까운 flat evidence를 낮은 신뢰도 신호로 처리하고, 현재안을 그대로 반복하지 말고 조건을 하나씩 바꿔 비교하도록 안내해야 한다.

**FR-ADV-020** Advisor는 learning artifact의 표본 수, 성과 중앙값, Profit Factor 중앙값, 거래 수 중앙값을 사용자 조언 본문에 직접 나열하면 안 된다. 해당 값은 내부 confidence, 위험 판단, evidence 품질 보정에만 사용해야 한다.

**FR-ADV-021** Advisor는 여러 파라미터 후보를 한 문장에 나열하며 `각각 바꿔 테스트`하라는 방식의 조언을 생성하면 안 된다. 변경 제안은 한 번에 하나씩만 비교하도록 제한하고, 사용자가 바로 백테스트할 수 있음을 함께 안내해야 한다.

**FR-ADV-022** Advisor와 AI 전략 코치는 AI 예측 모델(`ai_model`/`ai_drop_model`) 사용을 추천·제안하면 안 된다 (검증 결과 FR-AI-004 참고). `ai_model_recommendation`은 항상 `recommended=false`이며 코치 LLM 컨텍스트에 전달되지 않아야 하고, AI 예측 신호 추가를 실험 후보로 제안하면 안 된다. 사용자가 AI 모델을 먼저 언급하더라도 사용을 권하지 말고 검증된 재무·기술·리스크 대안으로 안내해야 한다.

#### 3.1.2 지원 시그널·지표

> 전략 설계는 자연어 채팅으로만 이뤄지며, UI 블록 조합 5단계 위자드 빌더는 제거되었다. 아래 조건들은 NL 파서가 출력하고 백테스트 엔진·DSL이 평가하는 시그널/필터다.

**FR-STR-020** 시스템은 다음 34종 시그널·필터 조건을 인식·평가해야 한다.

**기술적 지표 (20개)**

| 조건 ID | 이름 | 핵심 파라미터 |
|---------|------|--------------|
| `ma_crossover` | 이동평균 골든/데드크로스 | shortMA, longMA, crossType |
| `rsi` | RSI 과매수/과매도 | period, operator, value |
| `macd` | MACD 크로스오버 | fastPeriod, slowPeriod, signalPeriod |
| `bollinger_bands` | 볼린저밴드 이탈/반등 | period, stdDev, signalType |
| `volume_spike` | OBV 기반 거래량 급증 | period, signalType |
| `breakout` | 52주 신고가/신저가 돌파 | lookbackPeriod, signalType |
| `ema` | 지수이동평균 | period |
| `stochastic` | 스토캐스틱 | kPeriod, dPeriod |
| `cci` | 상품채널지수 | period |
| `adx` | 추세 강도 | period, threshold |
| `williams_r` | Williams %R (−100~0, 과매도/과매수) | period, operator, value |
| `mfi` | MFI 자금흐름지표 (0~100) | period, operator, value |
| `roc` | ROC/모멘텀 (변화율 %) | period, operator, value |
| `dividend_yield` | 배당수익률 (%, TTM DPS/종가, KIS 예탁원 배당 API 기반) | operator, value |
| `payout_rate` | 배당성향 (%, TTM DPS/EPS) | operator, value |
| `dividend_growth` | 배당성장률 (%, TTM DPS 전년比 증가율) | operator, value |
| `revenue_growth` | 매출 성장률 | operator, value |
| `operating_margin` | 영업이익률 | operator, value |
| `beta` | 시장 베타 | operator, value |
| `ev_ebitda` | EV/EBITDA | operator, value |

**필터 (7개)**

| 조건 ID | 이름 | 핵심 파라미터 |
|---------|------|--------------|
| `trading_value` | 거래대금 필터 | operator, value (억원) |
| `market_cap` | 시가총액 필터 | operator, value |
| `per` | PER 필터 | operator, value |
| `pbr` | PBR 필터 | operator, value |
| `roe_or_gpa` | ROE/GPA 필터 | metric, operator, value |
| `debt_ratio` | 부채비율 필터 | operator, value |
| `trading_suspension` | 거래정지 제외 | exclude |

**수급 (1개)**

| 조건 ID | 이름 | 핵심 파라미터 |
|---------|------|--------------|
| `investor_net_buy` | 기관/외인 순매수 | investorType, period, minAmount |

**리스크 (4개)**

| 조건 ID | 이름 | 핵심 파라미터 |
|---------|------|--------------|
| `price_limit_exit` | 손절/익절 | stopLossPct, takeProfitPct |
| `max_holding_days` | 최대 보유기간 | value |
| `trailing_stop` | 트레일링 스탑 | percentage |

**AI/ML (1개)**

| 조건 ID | 이름 | 핵심 파라미터 |
|---------|------|--------------|
| `ai_model` | AI 상승 예측 | threshold, direction |

#### 3.1.3 리스크 관리 설정

**FR-STR-030** 전략은 다음 리스크 파라미터를 포함해야 한다:

```typescript
RiskManagement {
  position_size_pct: number         // 종목당 투자 비중 (기본 10%)
  max_positions: number             // 최대 동시 보유 종목 수
  stop_loss_pct?: number            // 손절선 (%)
  take_profit_pct?: number          // 익절선 (%)
  trailing_stop_pct?: number        // 트레일링 스탑 (%)
  max_holding_days?: number         // 최대 보유 기간 (일)
  max_mdd_limit_pct?: number        // 전략 MDD 한도 (%)
  execution_timing: "next_open" | "current_close"
  allocation_type: "equal" | "fixed_pct"
  init_cash: number                 // 초기 투자금 (기본 10,000,000원)
}
```

#### 3.1.4 전략 저장 및 관리

**FR-STR-040** 사용자는 전략을 저장하고 이름 및 설명을 부여할 수 있어야 한다.

**FR-STR-041** 시스템은 전략의 타입을 자동 분류해야 한다 (가치투자 / 모멘텀 / 기술적분석 / AI 혼합 / 기타).

**FR-STR-042** 사용자는 저장된 전략을 불러와 편집하거나 재실행할 수 있어야 한다.

**FR-STR-042b** 저장된 전략 DSL에는 `symbols`가 없으므로(유니버스는 `universe_id`로 저장, 엔진이 PIT 마스터로 종목을 재해석) 저장 DSL 기반 백엔드 요청은 `symbols: []`를 채워 백엔드 스키마(필수 필드)를 통과시켜야 한다 — 워크포워드는 단일 통로인 `buildWalkForwardRequest`(parsedStrategyMerge.ts)에서, 재실행은 `/analytics/[id]`의 `buildEffectiveBacktestRequest`에서 채운다. 워크포워드 실행 진입점 3곳(`/analytics/new`, `/analytics/[id]`, 전략 기록 상세 `/backtest/[id]`)은 모두 SSE 스트림 클라이언트(`runWalkForwardStream`)를 사용해야 한다(비스트림 `/api/backtest/walk-forward` 직접 호출 금지 — 진행률·취소·장시간 타임아웃 보호 없음). 또한 백엔드 검증 실패(pydantic 422)의 `detail` 객체 배열은 그대로 노출하면 "[object Object]"로 보이므로 `formatApiErrorDetail`(walkForwardStream.ts)로 `경로: 메시지` 형태의 읽을 수 있는 문자열로 변환해 표시해야 한다.

**FR-STR-066** 시스템은 전략 채팅(`/analytics/chat`) 진입 직전에 전략연구소(`/analytics`)를 브라우저 히스토리에 포함해야 하며, 채팅에서 뒤로가기를 실행하면 직전 방문 페이지와 관계없이 전략연구소로 돌아가야 한다.

#### 3.1.5 독립형 배치 테스트

**FR-STR-043** 시스템은 `/analytics/new` 전략 만들기 채팅 페이지 상단 메인 액션 영역에 `모두 테스트` 버튼을 제공해야 한다.

**FR-STR-044** 사용자는 미리 준비한 다수의 전략 프롬프트를 데이터셋으로 입력해 하나의 배치 실행으로 시작할 수 있어야 한다.

**FR-STR-045** 시스템은 각 프롬프트를 개별 Strategy DSL로 생성하고, 각 전략에 대해 자동으로 백테스트를 실행해야 한다.

**FR-STR-046** 배치 실행은 queue + worker 방식으로 처리되어야 하며, 동시 실행 개수는 제한 가능한 concurrency 설정을 가져야 한다.

**FR-STR-047** 배치 실행 UI는 다음 정보를 실시간에 가깝게 표시해야 한다:
- 전체 진행률(%)
- 현재 실행 전략 이름
- 완료/실패/스킵/대기 개수
- 실행 로그

**FR-STR-048** 시스템은 모든 배치 결과를 `CAGR` 기본 내림차순으로 정렬한 leaderboard를 제공해야 하며, 다음 항목을 표시해야 한다:
- 순위
- 전략 이름
- `strategy_id`
- CAGR
- Total Return
- Sharpe
- MDD
- Profit Factor
- Trades

**FR-STR-049** 시스템은 최고 성과 전략을 시각적으로 강조해야 한다.

**FR-STR-050** 일부 전략 생성 또는 백테스트가 실패하더라도 전체 배치 실행은 중단되지 않아야 하며, 실패/스킵 항목을 별도로 표시해야 한다.

**FR-STR-051** 시스템은 배치 실행 이력을 영구 저장하고, 사용자가 과거 run을 다시 조회할 수 있어야 한다.

#### 3.1.6 Content-addressed Strategy ID

**FR-STR-060** 시스템은 `strategy_id = SHA-256(canonical_strategy_dsl)` 규칙을 사용해야 한다.

**FR-STR-061** `Strategy.id`에는 UUID, CUID, surrogate key를 사용해서는 안 되며, `strategy_id`를 Primary Key로 사용해야 한다.

**FR-STR-062** canonicalization은 stable JSON key ordering을 사용하고, 의미 없는 metadata를 제외해야 하며, 의미 있는 배열 순서는 유지해야 한다.

**FR-STR-063** 동일한 Strategy DSL은 항상 동일한 `strategy_id`를 생성해야 한다.

**FR-STR-064** 시스템은 `strategy_id`를 deduplication key, backtest cache key, result lookup key로 재사용해야 한다.

**FR-STR-065** 동일 `strategy_id`가 이미 존재할 경우 시스템은 불필요한 백테스트 재실행을 피하고 기존 결과를 `Cache Hit` 상태로 재사용해야 한다.

**FR-STR-066** [섹터/업종 유니버스, 2026-07-10] 시스템은 "반도체 관련주", "2차전지 업종" 같은 업종 제한을 전략 조건(`ParsedStrategy.sector`)으로 지원해야 한다. ① 섹터 분류의 SOT는 `korea-stocks.json`의 `sector` 필드(39개 정본 섹터, `engine/universe_pit.py::CANONICAL_SECTORS`)이며, 사용자·LLM의 자유 표현("배터리", "제약주", "AI 관련주")은 동의어 맵(`normalize_sector`)으로 정본명에 정규화한다(정규화 불가 시 None). '로봇'(2026-07-13 신설, 27종목)은 KSIC 공식 분류에 로봇 업종이 없어('특수 목적용 기계 제조업' 등으로 등록) **사명(로봇/로보틱스/로보) 기준**으로 분류하는 독립 정본 섹터다 — `MAPPING_RULES["로봇"]`이 우선순위 최상단(사명 부분매칭 오분류 선점: 해성에'어로'보틱스가 수산 '어로'에 걸리던 버그 수정), 사명에 로봇이 없는 로봇 전문기업(뉴로메카)은 `OVERRIDDEN_SYMBOLS`, 상폐 경로(`get_sector_from_krx_industry`)도 단축명 오버라이드보다 사명 판정을 먼저 거친다. 일반 자동화 설비·공작기계('공장자동화' 포함)는 기계/장비에 남는다. ①-1 [동의어 파생 구조, 2026-07-13] 동의어 맵은 두 어휘집의 드리프트를 구조적으로 차단하도록 파생된다: 종목 분류 어휘(`sector_mapper.MAPPING_RULES`)에는 '투자'·'금속'·'설비' 같은 일반어가 섞여 있어 통째로 NL 인식에 쓰면 거짓 양성('투자금 1억'→증권/보험)이 나므로, 사용자가 섹터를 부를 때 실제로 쓰는 모호하지 않은 산업어만 명시적으로 opt-in한 화이트리스트(`sector_mapper.NL_SAFE_TERMS` — 로봇/공장자동화/태양광/원전/웹툰 등)에서 정본 섹터를 자동 파생하고(`universe_pit._derive_mapper_nl_synonyms`, 각 용어의 단일-정본 매핑을 import 시점 검증), 여기에 분류 어휘엔 없는 사용자 전용 통칭(2차전지·리츠·AI)을 오버라이드로 얹는다(`_SECTOR_SYNONYM_OVERRIDES`). 정본명을 손으로 중복 기입하지 않아 종목 분류와 NL 인식이 서로 다른 섹터를 가리킬 수 없으며, 가드 테스트(`test_sector_nl_synonyms`)가 "어떤 산업어든 NL이 인식하면 반드시 분류와 같은 섹터"를 강제한다 — '로봇'이 분류상 기계/장비인데 NL 동의어엔 없어 '지원 목록에 없는 섹터'로 안내되던 드리프트의 근본 차단(회귀: test_robot_sector_now_resolves_without_unsupported_notice). ② 결정적 추출(`nl_parser._extract_sector`)은 섹터명 + 업종 큐('관련/테마/업종/섹터/분야/종목/주식/주' + 범위 후치 표현 '중심/위주', 2026-07-11)가 붙은 명시적 표현만 잡고, '주가'는 큐에서 배제한다. '관련/테마'는 맨 형태로 본다(2026-07-12 — '관련주' 어순만 보면 "반도체 관련 전략"·"로봇주 관련 전략"을 놓쳐 안내 없이 전체 시장으로 백테스트된다). 목록 밖 업종("로봇 관련주")은 룰 파서가 수락하지 않고 LLM에 위임하며, 최종적으로도 표현 불가하면 미지원 개념 안내(notices)를 남긴다(침묵 누락 방지). 단, "업종 상관없이/모든 업종" 같은 무관 표현은 섹터 언급으로 치지 않는다(오탐 방지). ②-1 [LLM 폴백 드리프트 복구, 2026-07-12] 업종 큐가 없는 표현("2차전지에 투자하는 전략")은 LLM 폴백이 섹터를 캐치하는 유일한 층이므로, LLM 산출물의 흔한 스키마 드리프트(sector를 universe 필드에 기입, description 누락)를 ValidationError로 통째로 폐기하지 않고 결정적으로 복구해야 한다(`ParsedStrategy._repair_llm_schema_drift` — universe의 비시장 값을 정본 업종으로 sector 이동·한글 시장명 정규화, 빈 description은 다른 전략 내용이 있을 때만 허용 후 `_apply_prompt_overrides`가 원문으로 채움). LLM이 sector를 냈지만 universe가 스키마 기본(KOSPI200)이고 시장 언급이 없으면 ③의 양시장 기본을 LLM 폴백 경로에서도 강제한다(수정 경로 제외 — 기존 universe 보존). ③ 시장 언급 없는 섹터 전략의 유니버스 기본값은 KOSPI200이 아니라 양시장(KOSPI+KOSDAQ)이다 — '그 업종 전체'가 자연스러운 해석이며 KOSPI200 기본값은 시총 상위 200 ∩ 섹터로 과도하게 좁아진다. ④ 엔진은 PIT 유니버스 해석 후 심볼을 섹터로 필터링하고(`universe_pit.filter_by_sector`), 해당 종목이 없으면 명시적 에러로 fail-fast한다. ④-1 [상폐 종목 섹터 백필, 2026-07-12] 섹터 분류는 현재 상장(korea-stocks.json, 우선) + PIT 마스터(stock-master.json)의 상폐 종목 `sector` 백필을 병합해 기간 중 상폐된 종목도 섹터 유니버스에 포함해야 한다(생존 편향 제거). 상폐 종목 섹터는 FDR KRX-DELISTING의 KRX 구 산업분류 단축명을 `sector_mapper.get_sector_from_krx_industry`(단축 어휘 전용 오버라이드 `KRX_SHORT_INDUSTRY_OVERRIDES` — '전기·전자'→IT 하드웨어, '기계·장비'→기계/장비, '금융'(대부분 스팩)→증권/보험 등 — 후 공통 키워드 매퍼 폴백)로 분류하며, `scripts/backfill_delisted_sectors.py`(제자리 패치, 멱등)와 `build_stock_master.py`(재빌드) 양쪽이 같은 로직으로 생성한다. 우선주(끝자리≠0)는 모주(prefix+'0')의 섹터를 물려받는다(korea-stocks.json은 보통주만 담음). 생존 편향 경고는 무조건 출력하지 않고, 업종 분류가 없어 필터에서 빠진 '상장폐지' 종목(`sector_unknown_delisted`)이 실제로 있을 때만 개수와 함께 고지한다 — 현재 상장 종목의 분류 공백(신규 상장 등)은 생존 편향이 아니므로 경고 대상이 아니다. `data/stock-master.json`은 git 추적 파일이고 프로덕션 compose가 `./data`를 마운트하므로 백필 결과는 커밋·배포로 프로덕션에 반영된다. ⑤ `sector`는 canonical DSL(해시)과 `BacktestRequest` 스키마에 포함해 캐시 충돌·스키마 누수(extra=ignore 드롭)를 막는다. 섹터 없는 기존 전략의 해시는 변하지 않는다. ⑥ [수정 경로 섹터 반영, 2026-07-13] 완성된 전략에 대한 후속 수정 요청("반도체 섹터 종목만 테스트 해줘")도 섹터를 반영해야 한다 — 결정론 fast-path(`_modify_rule_based`)가 `_extract_sector`로 섹터를 추출하고, LLM diff 경로는 diff가 sector를 놓치면 결정적 추출로 보정한다(파스 경로 보정과 동형). `MODIFY_PROMPT`에는 지원 업종 목록·매핑 지침·섹터 예시를 포함한다. 수정 경로는 기존 universe를 보존한다(③의 양시장 기본 확장은 최초 파싱 전용 — `_apply_prompt_overrides(preserve_universe=True)`; 시장을 넓히려면 "전체 시장으로" 등 명시 수정으로). '업종/섹터'+삭제어 인접 표현("업종 제한 빼줘", "섹터 필터 지워줘")은 섹터 제한을 해제하되, '업종에서 삼성전자 빼줘'(종목 제외 요청)로는 오발동하지 않는다(`_SECTOR_REMOVE_RE` 인접 조건). ⑦ [다중 섹터, 2026-07-13] `sector`는 정규형 None/str(단일 — 기존 해시·직렬화 하위 호환)/list(복수)를 가지며(`normalize_sector_value`), 복수면 엔진이 합집합으로 필터링한다(`filter_by_sector` 리스트 지원). 수정 요청의 네 의도는 결정적 통합 판정(`_sector_change_from_utterance`)이 LLM diff보다 우선한다: **추가**("로봇 섹터도 추가해줘" — '도' 조사+업종 명사 또는 추가/포함 동사 인접)는 기존 목록과 합집합, **교체**(추가 표지 없는 언급)는 덮어쓰기, **개별 삭제**("반도체 업종은 빼줘")는 그 항목만 제거(목록에 없는 대상이면 전체 해제로 오폭하지 않고 판단 유보), **전체 해제**는 기존 `_SECTOR_REMOVE_RE`. 이 판정은 rule-based fast-path·LLM diff 병합·`_apply_prompt_overrides` 세 지점에 동일하게 배선된다 — 종전에는 삭제 발화가 `_extract_sector` 재추출로 되살아나는 재주입 버그가 양 경로에 있었다(회귀: test_modify_sector_removal_not_reinjected). '도' 단독 조사는 짧은 용어 오발동("ai도입")이 있어 업종 명사 동반 또는 추가 동사 인접일 때만 추가 의도로 본다. canonical DSL은 단일=str 그대로, 복수만 정렬 list로 직렬화해 기존 전략 해시 불변+순서 무관 동일 해시를 보장한다. 반도체를 기계/장비로 교체해버리던 "로봇 섹터도 추가해줘" 실측 사고의 근본 수정(회귀: test_modify_sector_additive_union).

---

### 3.2 백테스트 엔진

#### 3.2.1 엔진 파이프라인

**FR-BT-001** 백테스트 엔진은 다음 단계를 순서대로 실행해야 한다:

```
1. DataLoader     → Parquet → Polars DataFrame
2. Indicators     → 기술적 지표 계산 (MA, RSI, MACD, BBands, 스토캐스틱, CCI, ADX, OBV)
3. DataResolver   → 누락 데이터 즉시 해결 (펀더멘털 API 조회, 계산 보완, 해결 로그 수집)
4. SignalEngine   → 벡터화 시그널 평가 (진입 OR 조합, 필터 AND 조합)
5. AIEngine       → (선택적) Transformer+XGBoost 예측
6. Simulator      → 매매 시뮬레이션
7. ResultHandler  → 메트릭 계산 및 리포트 생성
```

**FR-BT-002** 백테스트는 SSE(Server-Sent Events) 스트림으로 진행률과 중간 결과를 실시간으로 전달해야 한다.

**FR-BT-002b** [생존편향 — 진행 문구] 백테스트 진행 상황 문구에는 '현재 상장 종목 수'를 표기하지 않아야 한다. 요청에 담기는 심볼 목록은 현재 상장 종목(예: 코스피 836종목)일 뿐이고, 엔진은 생존편향 제거를 위해 각 시점에 실제 상장돼 있던 종목(상장폐지분 포함)을 point-in-time으로 다시 구성해 백테스트하므로(FR-STR-066·PIT 유니버스), 고정 종목 수("836종목 × 5년")를 보여주면 사용자가 '현재 상장 종목만 테스트한다'고 오해한다. 정확한 과거 종목 수는 기간·시점마다 달라 단일 숫자로 표현할 수 없으므로, 숫자 대신 "각 시점에 상장돼 있던 종목 기준(상장폐지 종목 포함)"임을 알린다(`stream_progress.simulation_phase_label`, 데이터 로딩 문구도 종목 수 미표기).

#### 3.2.2 시뮬레이터 규칙

**FR-BT-010** 리스크 종료(SL/TP/트레일링)는 장중 저가/고가(low/high)로 감지해야 한다 — 종가만으로 감지하면 장중 급락 후 회복하는 봉의 리스크가 누락된다. 체결은 체결 방식 타이밍(same_close=당일 종가, next_open=익일 시가)의 시장가로 수행하며, 스탑 가격 '정확 체결' 가정(갭 무시)은 사용하지 않는다. (2026-07 감사 C5)

**FR-BT-010b** 모든 주문은 진입 시점 포트폴리오 NAV 대비 목표비중(`from_orders(size_type='targetpercent')`)으로 체결해야 하며, 잔여 현금 비중(vbt `Percent`) 방식은 금지한다 — 동시 진입 종목 간 비중이 기하급수적으로 감소하고 현금이 영구 유휴되는 왜곡을 만든다. 체결 수량은 정수 주 단위(`size_granularity=1`)여야 한다. (감사 C1/C2)

**FR-BT-010c** 거래 불가일에는 체결하지 않고 청산을 다음 거래 가능일로 이월(`pending_exit`)해야 한다. 거래 불가일은 두 가지로 판정한다: ① 원본 가격 데이터가 아예 없는 날(상장 전·상장폐지 후 — `available_df = raw_price_df.notna()`), ② **과거 시점 거래정지 추정**(2026-07-20) — 봉은 존재하나 당일 거래량이 0인 날. 과거 매매거래정지 종목은 데이터 피드에 '거래량 0 + 가격 동결' 봉으로 남아 가격이 NaN이 아니므로 ①만으로는 걸러지지 않는다. 거래대금(=종가×거래량, 정제 후 종가>0이므로 거래량 0 ⇔ 거래대금 0)이 0인 봉을 `available_df`에서 제외해, 유동성 게이트가 꺼진 경로(`skip_risk_management`·`liquidity_limit_pct=0`)에서도 정지 기간 동결가로 진입·청산되는 낙관 편향을 차단한다. 정지 봉은 진입·청산 이월뿐 아니라 대형주(시가총액 상위)·랭킹 후보 풀에서도 자동 제외된다. NaN(거래대금 미수집·미상장 구간)은 정지로 간주하지 않아 기존 동작을 유지한다. (감사 C6)

**FR-BT-010d** 거래 비용은 매수 수수료 / 매도 수수료 / 매도 증권거래세(기본 0.15%, `sell_tax_rate` 옵션으로 제어)를 분리 적용해야 한다. (감사 H3)

**FR-BT-011** 처리 순서는 반드시 이월 청산 방출 → Exit → Risk Evaluation → Rebalance → Entry 순서를 지켜야 한다 (벡터화 단계). 청산이 예정된 종목은 같은 날 재진입할 수 없다(동일 셀 매수·매도 주문 충돌 금지).

**FR-BT-012** 트레일링 스탑은 `peak_price` 배열로 추적하며(고점 갱신은 장중 고가 기준), 진입 시 초기화하고 청산 시 리셋해야 한다.

**FR-BT-013** 다중 종목 동시 진입 시그널 발생 시 스코어 기반 랭킹으로 우선순위를 결정해야 한다 (PBR/ROE 복합 스코어 또는 `ranking_metric="return"` 모멘텀 — 최근 N일 수익률 상위 K종목 선정). 진입 조건 없는 모멘텀 랭킹의 후보 풀은 유동성 게이트와 대형주(시가총액 상위) 마스크를 반드시 보존해야 한다. (감사 C4)

**FR-BT-014** 시스템은 `rebalancing_period`(daily/monthly/quarterly/yearly)가 지정된 전략에 대해 달력 기준 리밸런싱(reconstitution)을 수행해야 한다: 각 주기의 첫 거래일에 후보를 랭킹 상위 K로 재선정하고, 목표 집합에서 빠진 보유 종목은 매도, 신규 편입 종목은 매수, 유지 종목은 그대로 둬야 한다.

**FR-BT-015** 리밸런싱 실행 방식은 전략의 봉중간 리스크 관리(SL/TP/트레일링 스탑/최대 보유기간) 사용 여부에 따라 분기해야 한다: 봉중간 리스크가 없는 순수 리밸런싱은 비중 리셋까지 수행하는 네이티브 목표비중 방식으로 처리하고, 봉중간 리스크가 혼재하면 현실적 체결을 보존하는 커스텀 reconstitution 루프로 처리하되 유지 종목의 비중이 리셋되지 않음을 경고로 고지해야 한다. (감사 H8)

**FR-BT-015b** 매도 거래의 청산 사유 라벨은 실제 청산 트리거를 구분해 표시해야 한다: 손절/익절/트레일링 스탑/보유기간 만료/상장폐지/데이터 종료/백테스트 종료는 각각의 정밀 라벨로 표시하고, 리밸런싱일에 목표 집합에서 빠져(조건 미충족·랭킹 이탈) 매도된 종목은 "리밸런싱 제외 (목표 종목 이탈)"로 표시해야 한다. 신호·리스크로 설명되지 않는 리밸런싱 편출을 추상적 "전략 매도 조건 충족"으로 뭉개지 않도록, 시뮬레이터(순수·커스텀 루프 두 경로)가 체결일 기준 정밀 사유를 기록하고 결과 처리기가 이를 우선 적용한다. 결과 요약 카드에는 `rebalancing_period`가 `none`이 아니면 리밸런싱 주기 배지를 노출해야 한다. 손절/익절/트레일링 스탑 라벨은 시뮬레이터가 청산을 감지한 시점의 확정 사유(exit_reason_overrides)를 정본으로 사용해야 하며, 실현수익률 크기로 사유를 사후 추론(예: `수익률 ≈ -손절%±1%`)해서는 안 된다 — 봉중간 스탑은 종가(same_close)·익일 시가(next_open)·갭 체결로 실현수익률이 스탑 기준선과 어긋나므로 크기 추론은 진짜 손절을 누락하거나 무관한 매도를 손절로 오귀속한다. (프런트엔드 `resolveTradeReason`도 손실률 기반 재라벨을 하지 않고 백엔드 정본 라벨을 그대로 표시한다.)

**FR-STR-067** [ETF 유니버스, 2026-07-19] 시스템은 ETF(상장지수펀드)를 백테스트 가능한 독립 유니버스(`universe=["ETF"]`, `universe_id="etf"`)로 지원해야 한다. ① **데이터**: ETF 마스터는 `data/etf-master.json`(FDR ETF/KR 목록 ∩ 로컬 OHLCV 커버리지, `backend/scripts/build_etf_master.py`로 생성·멱등, git 추적이라 커밋·배포로 prod 반영)이며, 엔진은 창 안에서 가격 데이터가 존재하는 ETF만 as-of로 해석한다(`universe_pit.resolve_etf_symbols`). 상폐 ETF는 `backend/scripts/backfill_delisted_etf.py`로 백필됐다(2026-07-19 완료) — FDR KRX-DELISTING엔 ETF가 없고(수익증권 그룹=구식 공모펀드), openapi.krx.co.kr Open API는 증권상품 엔드포인트 미승인(401)이라, data.krx.co.kr 로그인 세션(.env KRX_ID/KRX_PW)으로 'ETF 전종목 시세'(MDCSTAT04301)를 2015-01~현재 전 거래일(3,012거래일) 스윕해 수집했다. **주의**: pykrx의 `get_etf_ticker_list(과거일)`는 현재 상장 종목의 부분집합만 반환해 상폐분을 못 잡는다(2020-02-28 실측: 시세 화면 451종목 vs 멤버십 350종목) — 반드시 일별 전종목 시세 화면을 직접 스윕해야 point-in-time이 된다. 재개 가능 캐시=data/cache/krx-etf-daily/(gitignore, 3,012개 파일), 산출물=data/etf-delisted.json(git 추적, 244종목) → build_etf_master.py가 병합(코드 재사용 시 현재 상장분 우선). 상폐 244종목 중 다수(30종목)는 만기매칭형 채권 ETF(설계상 목표 만기에 자동 상환)였다. 상폐 ETF의 강제청산은 주식과 동일하게 "상장폐지"로 라벨된다(`get_delisting_dates` ETF 마스터 병합). 마스터에 상폐분이 백필된 후로는 ETF 백테스트가 생존 편향 경고를 남기지 않는다(`etf_master_includes_delisted`). **부수 발견**: 백필 후 전체 ETF 유니버스 E2E 검증 중 `DataLoader.load_symbol_data`가 ETF에도 무조건 재무 enrichment(ROE 등)를 시도해 종목마다 KIS 재무비율 API가 헛되이 실패(500)하는 것을 발견 — ETF는 재무제표가 없어 이 데이터가 애초에 쓰이지 않으므로(④의 유니버스별 팩터 레지스트리) `is_etf_symbol` 판정으로 건너뛰게 수정, 전체 ETF 백테스트 Phase1이 16.1s→7.4s로 단축되고 로그 소음이 사라졌다. ② **미혼합**: ETF 유니버스는 주식 시장(KOSPI/KOSDAQ/KOSPI200)과 절대 혼합하지 않는다 — 파서·인터프리터 스키마가 ["ETF"] 단독으로 정규화하고("코스피 ETF"도 ETF — 상품 유형이 시장 언급보다 우선), 엔진은 ETF 마스터만 조회한다. 종목 섹터 분류(sector)는 ETF에 적용되지 않아 비운다. ③ **테마/상품명 필터**(`ParsedStrategy.etf_theme` → `BacktestRequest.etf_theme`, canonical DSL 포함 — None이면 키 제거로 기존 해시 불변): "반도체 ETF"→"반도체", "KODEX 200"→상품명을 결정적으로 추출하되, 어휘집 유지 대신 **ETF 마스터 이름과의 자기검증 매칭**으로 판정한다(`universe_pit.extract_etf_theme` — 상품명 전체 매칭 우선, 'ETF' 직전 토큰의 접미사 중 마스터 이름과 매칭되는 것만 테마로 인정; "사는 ETF"의 '사는'은 매칭 0이라 무시). 엔진 필터(`filter_etf_by_theme`)는 정확한 상품명 일치가 있으면 그 종목만, 없으면 이름 포함 매칭 전체를 대상으로 하고, 매칭 0이면 전체 ETF 유지+warnings 안내(조용한 왜곡 방지). ④ **유니버스별 팩터 검증**(`engine/universe_capabilities.py` — 단일 진실 소스): ETF는 여러 기업을 묶은 상품이라 기업 재무지표(PER·PBR·ROE·부채비율·배당성향 등 재무제표 파생 전부와 시가총액 — ETF에선 AUM이라 의미가 다름)를 전략 조건으로 쓸 수 없고, 가격·거래량 파생 지표(기술 지표 전부, 거래대금)만 허용한다. ETF 전략에 재무지표가 섞이면 **조용히 무시하지 않고** 이유 설명("ETF는 개별 기업이 아니라 여러 종목을 묶은 상품이므로 …을 조건으로 사용할 수 없습니다")+기술 지표 대안 제안 칩으로 되묻는다 — 최초 파싱 경로는 `nl_parser.detect_etf_factor_conflict`(정성 언급 "PER 낮은 ETF" 포함, 진입 누락 되묻기보다 우선), LLM 인터프리터 경로는 `capability_validator`(오류+suggested_fixes)가 담당한다. LLM 프롬프트(인터프리터 규칙 6-1, SYSTEM_PROMPT/MODIFY_PROMPT, 수정 RAG knowledge)에도 동일 계약을 명시해 임의 생성·조용한 제거를 금지한다. ⑤ **체결 비용**: ETF 매도에는 증권거래세가 부과되지 않으므로 명시 옵션이 없으면 `sell_tax_rate=0`으로 시뮬레이션한다. ⑥ **빌더/프론트**: 전략 빌더 시장 선택지에 ETF를 포함하고, ETF 유니버스에서는 가치 전략(PBR/ROE) 선택지를 제시·수락하지 않는다. 전략 요약 유니버스 배지는 "ETF"(+테마 배지 "반도체 테마"/"KODEX 200")로 표시한다. ⑦ **향후 확장**: 유니버스별 지원 팩터는 `universe_capabilities`에서 독립 관리한다(미국주식·채권 등 신규 유니버스는 항목 추가로 확장).

**FR-STR-068** [단일/지정 종목 백테스트, 2026-07-20] 시스템은 사용자가 특정 종목과 전략을 함께 언급하면("삼성전자에 골든크로스 전략을 적용해줘", "005930에 MACD 전략", "하이닉스에 RSI 과매도 전략") 유니버스(종목 선정) 백테스트와 분리된 **단일/지정 종목 백테스트**로 실행해야 한다. ① **모드 분리**: `ParsedStrategy.target_symbols`(종목코드 목록)가 비어 있으면 기존 유니버스 모드, 채워져 있으면 지정 종목 모드다. 변환기(`to_backtest_request`)는 지정 종목 모드에서 `symbols=[지정 코드]`, `universe_id=None`(엔진이 PIT 재해석·섹터 필터를 적용하지 않고 목록을 그대로 사용 — 기존 엔진 계약 재사용), `sector/etf_theme=None`, `backtest_mode="single_asset"`, 표시용 `target_stocks`(코드→등록명)를 만든다. 자금 배분은 지정 종목 수 기준 균등(단일이면 100%, `position_size_pct=100/n`, `max_positions=n`)이며 횡단면 랭킹(`ranking_enabled`)은 끈다. ② **결정적 종목 해석**: 종목명·통칭 별칭·6자리 코드→정규 종목코드 변환은 LLM이 아니라 `stock_analysis/symbol_resolver`(korea-stocks.json 정본) 기반 결정적 추출(`nl_parser._extract_target_symbols`)이 담당하고, LLM은 이 필드를 출력하지 않는다(스키마 설명으로 금지). LLM Interpreter Primary 경로(`STRATEGY_INTERPRETER_MODE=primary`)에서도 컴파일 후 같은 결정적 추출로 채운다(`primary._override_target_symbols` — 날짜 오버라이드와 동형; StrategySpec에 지정 종목 개념이 없어 누락 시 유니버스 전략으로 조용히 넓어지는 사고 방지). 이때 지정 종목이면 유니버스형 청산 누락 되묻기(정기 리밸런싱 추천)는 억제하고 ⑤의 보정이 처리한다. 또한 종목명+'테스트' 발화("삼성전자 단일 종목만 테스트 해보자")는 분류기 결정 규칙이 전략 설계로 라우팅한다(LLM 폴백의 STOCK_ANALYSIS 리다이렉트 오분류 방지). 조사 결합 표기("삼성전자에"/"하이닉스로"/"삼성전자만")와 코드+조사("005930에")를 인식하도록 경계 판정을 확장했다(유니코드 \b 함정 — 한글은 단어문자라 코드 뒤 조사에서 경계 실패). ③ **문맥 가드(오폭 방지)**: 예시("삼성전자 같은/처럼"), 업종 서술("~가 속한 반도체 업종", 업종/섹터/관련주/테마/주도주), 제외·부정("빼고/제외/말고")이 섞인 발화에서는 종목 추출을 포기한다 — 종목질문 리다이렉트(FR-SA-006)·전략 빌더가 합성하는 업종 전략 문구가 단일 종목으로 오폭되면 유니버스 전략이 조용히 바뀌는 사고가 된다. 부정·비교 등 모호 발화는 LLM/되묻기에 위임된다(보수적 실패 = 기존 유니버스 의미론 유지). ④ **복수 종목 되묻기**: 여러 종목이 함께 언급되면 임의로 하나를 고르지 않고 기존 clarification 채널로 되묻는다(`detect_symbol_ambiguity` — "한 종목만 테스트하려면 골라 주세요", 종목별 선택 칩; 그대로 진행하면 전체를 함께 테스트). ⑤ **청산 누락 추천 보정**: 지정 종목 전략에 청산 조건(청산 신호·보유기간·손절/익절/트레일링/MDD·리밸런싱)이 전혀 없으면 조용히 임의 실행하지 않는다 — 크로스오버 계열 진입(ma_crossover/ema/macd)은 반대 신호 청산을 추천 기본값으로 적용하고 notices로 알리며, 그 외 진입은 자동 주입 없이 "기간 종료까지 보유" 사실과 추가 옵션을 notices로 안내한다(`apply_single_asset_adjustments`, `_build_parse_result` 공유 — 최초 파싱·수정·후행 검증 교정 모두 적용). 이 보정 덕에 지정 종목+기술 진입 단독 프롬프트는 룰 fast-path에 남는다(유니버스 전략의 '진입만 있으면 LLM 위임' 게이트 면제). ⑥ **수정 경로**: 종목 교체("SK하이닉스로 바꿔줘" — 별칭 표면형을 잔여 판정에서 차감해 fast-path 유지)·명시적 시장 전환 시 지정 해제("코스닥 전체로")·업종 전환 시 지정 해제("반도체 업종으로")를 결정적 통합 판정(`_target_change_from_utterance`)이 LLM diff보다 우선 처리하며, 무관 수정("손절 5%로")은 지정을 보존한다(섹터 FR-STR-066 ⑥/⑦과 동형 — rule fast-path·LLM diff 병합·`_apply_prompt_overrides` 세 지점 배선). ⑦ **해시/스키마 관통**: `target_symbols`는 canonical DSL(정렬, 빈 값은 키 제거로 기존 해시 불변)에 포함돼 종목별로 다른 strategy_id(캐시 충돌 방지)를 가지며, `BacktestRequest`에 `backtest_mode`/`target_stocks`를 선언해 pydantic extra=ignore 드롭 함정을 막는다. ⑧ **표시**: 전략 요약의 유니버스 배지 대신 "삼성전자 (005930)" 종목 배지("대상 종목" 라벨), 포트폴리오 배지는 "최대 N종목" 대신 "단일 종목 집중 투자"(복수면 "지정 종목 N개 균등 투자")로 표기한다(파싱 카드·실행 요청 요약·저장 DSL 요약 모두). ⑨ **비용/기본값**: 수수료·슬리피지·초기자금·기간·체결 시점은 기존 플랫폼 기본값과 시장별 비용 모델(증권거래세 포함)을 그대로 사용하고, 상장폐지 종목 강제청산 등 PIT 의미론도 유니버스 모드와 동일하게 적용된다. 한계: 현재 상장 종목명만 해석된다(상폐 종목명 지정은 미지원 — korea-stocks.json 정본), 해외 종목 별칭은 데이터가 없어 지정으로 승격하지 않는다.

**FR-BT-016** [데이터 커버리지 투명성, 2026-07-14] 백테스트 결과는 전략이 참조한 데이터 의존 지표(펀더멘털 필터: PER/PBR/PSR/EV-EBITDA/ROE/ROA/마진·성장률/시가총액/배당수익률·배당성향 등)가 백테스트 창에서 실제로 얼마나 존재했는지를 종목·기간 두 축으로 집계한 `dataCoverage` 리포트를 포함해야 한다(`engine/data_coverage.py`). 각 지표에 대해 (기간 커버리지 %, 종목 커버리지 %, 데이터 존재 종목 수, 사용 가능 시작·종료일, used/partial/unused 분류)를 산출하고, 데이터 부족은 숨기지 않고 결과 로그에 투명하게 드러내야 한다. 데이터가 전혀 없으면(unused) "해당 조건은 적용되지 않았다", 기간 커버리지가 60% 미만이면 "결과 해석에 주의가 필요하다", 일부 종목만 데이터가 있으면 "나머지 종목에는 조건이 적용되지 않았다"는 경고를 `warnings` 채널에 합류시켜 사용자가 결과를 오해하지 않게 한다. 기술적 지표(OHLCV에서 항상 계산)는 커버리지 변동이 없어 추적 대상에서 제외한다. (스키마가 표현할 수 없는 진짜 미지원 개념은 파싱 시점 FR-STR-023d의 notices가 담당하고, '지원되지만 데이터가 희소한' 경우를 이 리포트가 담당한다 — 둘이 함께 데이터 부족 전 구간을 정직하게 커버한다.)

#### 3.2.3 성능 메트릭

**FR-BT-020** 백테스트 결과는 다음 메트릭을 포함해야 한다:

| 메트릭 | 설명 |
|--------|------|
| Total Return | 총 수익률 (%) |
| CAGR | 연평균 복리 수익률 (%) |
| Buy & Hold Return | 단순 매수 보유 수익률 (벤치마크 비교) |
| Max Drawdown (MDD) | 최대 낙폭 (%) |
| Sharpe Ratio | 위험 조정 수익률 |
| Sortino Ratio | 하방 위험 조정 수익률 |
| Win Rate | 승률 (%) |
| Profit Factor | 총이익 / 총손실 |
| Kelly Criterion | 켈리 기준 최적 베팅 비율 |
| Volatility | 연 환산 변동성 (%) |
| Exposure | 포지션 보유일 비율 (%) |
| Max Drawdown Duration | 최장 수중(underwater) 기간 (거래일) |
| Expectancy | 평균 거래 수익률 (%) |
| Recovery Factor | 순이익 / 최대 낙폭 금액 |
| 월별/연도별 수익률 | 기간별 수익 분해 |
| 종목별 통계 | 개별 종목 성과 분석 |

**FR-BT-020b** Profit Factor 등 통계는 계산값을 조작 없이 그대로 보고해야 한다(클램프·조건부 재정의 금지). 소표본(거래 30건 미만)은 값 조작 대신 경고로 고지한다. Sortino의 하방편차는 전체 기간에 대한 목표 미달분 RMS(표준 정의)로 계산하며, Sharpe/Sortino는 연 무위험수익률 옵션(`risk_free_rate`, 기본 0)을 지원해야 한다. (감사 C3/H4/M7)

**FR-BT-020c** 시스템은 결과 신뢰성에 영향을 주는 요인을 경고 채널로 공시해야 한다: 매도 거래세 반영 여부, 소표본 통계, 벤치마크 ETF 상장 이전 구간, 벤치마크 분배금 미반영(전략만 토탈리턴), 대형주 판정의 정적 주식수 근사, AI 모델 학습기간과 백테스트 기간의 중첩(인샘플 편향), 리밸런싱 비중 미리셋, 전일 거래대금 한도를 초과한 매수 체결(시장충격 위험). (감사 H1/H2/H5/H7/H8)

**FR-BT-021** 백테스트 결과는 에퀴티커브(자산 가치 추이), 거래 내역(매수/매도 시점, 가격, 수익), 종목별 기여도를 시각화해야 한다.

#### 3.2.4 백테스트 이력 관리

**FR-BT-030** 시스템은 백테스트 실행 이력을 저장하고 조회할 수 있어야 한다.

**FR-BT-031** 백테스트 이력은 전략명, 유니버스, 조건, 핵심 메트릭(CAGR, MDD, Sharpe), 실행 일시를 포함해야 한다.

**FR-BT-032** 백테스트 이력은 가능하면 `strategy_id`를 참조해야 하며, 캐시 히트 시 `hitCount`를 누적할 수 있어야 한다.

**FR-BT-033** 배치 실행 중 생성된 전략 결과도 일반 단일 백테스트와 동일한 저장 경로로 `Strategy`, `BacktestResult`, `BacktestHistory`에 영구 저장되어야 한다.

#### 3.2.5 DataResolver — 누락 데이터 즉시 해결

**배경:** 사용자가 PBR, PER, ROE, 부채비율, 시가총액 등 펀더멘털 지표나 거래대금 기반 조건을 포함한 전략을 설계할 때, 해당 종목의 로컬 Parquet 파일에 해당 컬럼이 없거나 전체 null인 경우가 발생한다. 기존 시스템은 이를 무시하고 신호를 all-True로 통과시켜 조건이 사실상 무력화되는 문제가 있었다.

**FR-BT-040** DataResolver는 지표 계산(IndicatorEngine) 직후, 신호 평가(SignalEngine) 직전에 실행되어야 한다.

**FR-BT-041** DataResolver는 전략 조건에서 요구하는 컬럼 목록을 추출하고, 누락(컬럼 없음 또는 전체 null) 여부를 판단해야 한다.

**FR-BT-042** 누락 데이터 해결 우선순위:

| 우선순위 | 방법 | 대상 |
|---------|------|------|
| 1 | 기존 데이터에서 직접 계산 | `trading_value_20_sma` = close × volume → 20일 SMA |
| 2 | 기존 데이터에서 비율 계산 | `per` = close ÷ eps, `pbr` = close ÷ bps (컬럼 존재 시) |
| 3 | 외부 API 조회 후 시계열 보강 | 펀더멘털 (EPS/BPS/ROE/부채비율): KIS API → Naver Finance 스크래핑 → 로컬 캐시(90일 TTL) |
| 4 | 외부 API로 상장주식수 조회 후 계산 | `market_cap` = close × 상장주식수 ÷ 1억 (Naver Finance → pykrx 폴백) |

**FR-BT-043** 펀더멘털 데이터 보강 시 look-ahead bias를 방지하기 위해 공시 지연 90일(`_PUBLISH_DELAY_DAYS = 90`)을 적용하여 각 날짜에 실제로 사용 가능했던 데이터만 매핑해야 한다.

**FR-BT-044** 데이터 해결 과정의 모든 단계(감지, 시도, 성공, 실패)를 `resolution_logs`로 기록하고, 백테스트 응답 JSON에 포함해야 한다.

```json
{
  "resolution_logs": [
    { "level": "INFO",    "message": "[005930] 누락 데이터 감지: per" },
    { "level": "INFO",    "message": "[005930] 펀더멘털 데이터 조회 중..." },
    { "level": "SUCCESS", "message": "[005930] 펀더멘털 보강 완료 (100/100 행)" },
    { "level": "SUCCESS", "message": "[005930] per 계산 완료 (eps 기반)" }
  ]
}
```

**FR-BT-045** 프론트엔드 백테스트 터미널 UI는 `resolution_logs`를 동일 메시지 기준으로 중복 제거하여 최대 20건까지 표시해야 한다. 종목 코드(`[005930]`)는 종목명으로 치환하여 표시한다 (`[삼성전자(005930)]`).

**FR-BT-046** 데이터 해결 실패 시 해당 컬럼 없이 진행하고 `WARN` 또는 `ERROR` 로그를 남기며, 백테스트 전체를 중단하지 않아야 한다.

**FR-BT-047** 백테스트 실행 요청(`/backtest`, `/strategy/backtest-stream`)은 엔진이 행(hang)에 빠지더라도 벽시계 제한 시간(`BACKTEST_TIMEOUT_S`, 기본 600초) 안에 반드시 종료되어야 한다(`engine/watchdog.py`). 제한 시간 초과 시 `/backtest`는 504, SSE 스트림은 `error` 이벤트 후 `[DONE]`으로 명확한 한국어 안내와 함께 종료한다(무한 상태 메시지 금지). 워커 스레드는 강제 종료할 수 없으므로 데몬으로 유기하되 로그로 경고한다.

**FR-BT-048** AI 예측 신호(`ai_model`/`ai_drop_model`)가 포함된 백테스트는 엔진 최종 관문에서 fail-fast로 처리해야 한다: ① 운영 스위치 `AI_SIGNALS_ENABLED=0`(기본 활성)이면 즉시 명확한 에러로 거절하고, ② AI 모델 로드가 불가능하면 0점 처리(0거래 침묵 진행)나 추론 대기 대신 즉시 에러를 반환해야 한다. 파싱·캐시 등 어떤 경로로 AI 신호가 유입되어도 이 관문이 적용된다.

**FR-BT-049** 워크포워드 검증(`engine/walk_forward.py`, `POST /walk-forward`, `POST /walk-forward/stream`):
- 최적화 대상 파라미터 공간은 현재 전략 DSL에서 **엔진(`engine/signals.py` + `engine/indicator_columns.py`)이 실제로 읽는 파라미터만** 자동 추출해 구성해야 한다(`buildWalkForwardParameterRanges`의 지표별 화이트리스트). 엔진이 무시하는 파라미터(예: 스토캐스틱 crossover 모드의 value)는 UI에 표시되거나 탐색되어서는 안 된다.
- 모든 창에서 IS(학습) 구간 종료일 < OOS(검증) 구간 시작일이어야 하며(look-ahead 금지), 학습된 파라미터는 해당 OOS 창에만 적용하고 다음 창에서 재학습한다. OOS 창의 지표 워밍업은 엔진이 startDate 이전으로 동적 프리로드(`_max_indicator_period` × 1.6 + 40 캘린더일, 최소 400일)해 보장한다.
- UI가 표시한 학습/검증 거래일 수는 `is_bars`/`oos_bars`로 백엔드에 그대로 전달되어 창 분할에 사용된다(표시 = 실행). 창 수 상한 24개 초과·데이터 부족 시 명확한 에러를 반환한다.
- 최적화 대상 파라미터 UI 칩은 배지 텍스트가 아니라 **실제 탐색 공간의 경로(path)에서 직접 생성**한다(`buildWalkForwardParameterDescriptors` — 한글 라벨: "MACD 단기", "볼린저 표준편차" 등, 진입/청산 중복 시 구간 접미사). 오버라이드/제외/step 설정은 경로 키로 정확히 해당 파라미터에만 적용된다(레거시 라벨 키는 폴백 지원).
- 사용자가 수정한 파라미터 탐색 범위(min/max/step)는 자동 생성 범위로 재클램프하지 않고 그대로 적용하며, 파라미터별 최적화 제외(`excluded_parameters`)를 지원한다.
- 그리드·베이지안 최적화 모두 의미 제약(단기 < 장기: `shortMA<longMA`, `fastPeriod<slowPeriod`, `shortPeriod<longPeriod`)을 강제한다.
- 집계는 NaN/Infinity를 표본에서 제외하고 CAGR·총수익·MDD·Sharpe·Calmar·승률·손익비·거래수·평균 거래손익(expectancy)을 제공한다. IS 평균 수익 ≤ 0이면 `wfe_valid=false`로 WFE 해석 불가를 알린다. 모든 창이 실패하면 부분 결과 대신 에러를 반환한다(Fail Fast).
- 오래 걸리는 작업이므로 **예상 소요 시간을 실행 전에 미리 안내**해야 한다. 총 백테스트 수 = 구간 수 × (구간당 백테스트 + OOS 1회)이며, 구간당 백테스트는 그리드=조합 수·베이지안=시도 수다. 백테스트 1회당 소요는 기준 백테스트(전체 기간) 실측 시간(`result.executionTime`)을 **스케일 없이 그대로** 사용하고(실측상 1회 비용은 구간 길이와 거의 무관 — 종목별 데이터 로드+지표 계산 고정비가 지배적이라, 구간 길이 비율로 선형 스케일하면 수 배 과소추정되어 실행 중 라이브 ETA와 크게 어긋난다), 오차를 감안해 범위(0.7~1.4배)로 표시한다(기준 실측이 없으면 폴백 상수). 실행이 시작되면 SSE로 스트리밍되는 실측 `timing.total`의 지수이동평균으로 남은 백테스트 수를 곱해 **남은 시간(라이브 ETA)을 계속 갱신**한다(`WalkForwardPanel`).
- `POST /walk-forward/stream`은 SSE로 창 단위 진행률(`{type:progress, window, total, is_period, oos_period}`)을 스트리밍하고, 클라이언트 연결 종료(취소 버튼 포함) 시 **시도/조합(=백테스트 1회) 단위로** 협조적으로 취소한다 — `should_cancel` 훅이 창 경계뿐 아니라 그리드 조합 루프(`grid_optimizer`)와 베이지안 trial 콜백(`optuna_optimizer`의 `study.stop()`), OOS 실행 직전까지 배선되어, 취소 후 진행 중이던 백테스트 1회만 마치고 즉시 중단된다(창 전체를 기다리지 않음). 벽시계 제한은 전용 `WALK_FORWARD_TIMEOUT_S`(기본 3600초, 창×시도만큼 백테스트를 반복하므로 단일 백테스트 제한 600초보다 커야 함) 초과 시 error 이벤트로 종료하며, 진행 이벤트가 없는 침묵 구간에는 15초 간격 SSE keep-alive 주석을 내보낸다. Next 프록시(`/api/backtest/walk-forward/stream`)의 안전망 타임아웃은 반드시 백엔드 제한보다 커야 한다(같거나 작으면 프록시가 먼저 끊어 사용자에게 "연결 끊김"으로 보인다). 프론트는 `runWalkForwardStream`으로 소비한다.

**FR-BT-049b** 지표 기간 파라미터화(`engine/indicator_columns.py`): MACD(fastPeriod/slowPeriod/signalPeriod), 스토캐스틱(period), 볼린저밴드(period/stdDev)는 전략 DSL에 명시된 값으로 계산해야 한다. 기본값(12/26/9, KDJ 9, BOLL 20±2σ)이면 기존 stockstats 컬럼을 그대로 사용해 과거 백테스트 결과와의 동일성을 보존하고, 파라미터 지정 시 파라미터화 컬럼(`macd_f,s,g` / `kdjk_n` / `boll_ub_n[_kpX]`)을 계산한다. 워밍업 산정(`_max_indicator_period`)도 동일 파라미터를 반영해야 한다.

**FR-BT-050** 몬테카를로 시뮬레이션(프론트 `OptimizationPage.tsx`, in-browser 실행):
- 방식은 ① equity curve 일별 로그수익률의 **고정 블록** 부트스트랩 — 블록 1일(독립 재표본)/5·10·21일(자기상관 보존) —, ② **가변 블록(Stationary bootstrap, `blockMethod:"stationary"`)** — 평균 블록 길이(5·10·21일)만 맞춰 기하분포 가변 블록으로 고정 블록의 경계 효과를 완화 —, ③ 거래 재표본(trade bootstrap) 중 사용자가 선택하고 UI에 방식을 명시한다. seed 고정으로 재현 가능해야 한다.
- **방식 추천**: 전략의 평균 보유기간(`avgHoldingDays`)을 근거로 기본 블록 길이를 추천해(1/5/10/21일) 한 번에 적용할 수 있는 힌트를 제공한다(검증 방식 선택을 돕는 통계적 제안일 뿐 투자 판단 추천이 아니며, 사용자가 자유롭게 다른 방식을 선택할 수 있다).
- 거래 재표본은 체결 기록(tradesList, 폴백 signals)에서 종목별 **수량 기반 FIFO** 매칭으로 완결 거래를 복원하고, 각 거래를 **자본 대비 기여도(손익금 ÷ 진입시점 계좌자산 = return-on-equity)**로 환산해 복원추출한다. 이로써 실제 포지션 사이징(전액이 아닌 일부만 투입, 동시 다종목 보유)이 반영되어 거래 재표본 복리가 다종목 전략의 CAGR·MDD를 과장하지 않는다. 체결 수량·일별 자산곡선이 없어 사이징을 복원할 수 없으면 가격수익률로 강등하고 그 사실을 결과에 표시(`tradeSizing`)한다. 완결 거래 20건 미만이면 명확한 에러를 반환하고, MDD가 거래 단위 경로 기준(거래 도중 낙폭 미반영)임을 UI에 명시한다.
- 결과는 CAGR·Sharpe·MDD 각각에 대해 최소/5%/25%/중앙값/75%/95%/최대/표준편차(표 형태)와 CAGR·MDD 분포 히스토그램, 양수 CAGR 확률, MDD 30% 초과 확률을 제공한다. 단일 표본 최소/최대는 반복 횟수에 따라 불안정하므로 대표 지표(스탯 카드)로는 사용하지 않는다.
- **관측(원래 순서) 위치 표시**: 재표본하지 않은 실제 백테스트 순서의 CAGR·MDD를 시뮬레이션과 동일한 기준으로 재구성하고(`observed`), 스탯 카드·분포 히스토그램 기준선·쉬운 설명 문장으로 분포 내 백분위 위치를 제공한다(실제 결과가 분포 상단에 치우칠수록 특정 순서 의존 가능성을 시사). 구버전 저장 결과(`observed` 없음)는 종전 최소/최대 카드로 폴백한다.
- 일별 독립 재표본(blockSize 1)은 자기상관·변동성 군집·추세가 깨진다는 한계를 UI 설명과 쉬운 설명 문장에 명시한다.
- **회복(낙폭 지속) 지표**: 각 시나리오의 최장 언더워터(고점 회복까지의 스텝 수 — returns 모드는 거래일, trades 모드는 거래 건) 분포(`underwater`)를 산출해 쉬운 설명 문장으로 중앙값·상위 5% 회복 소요를 제공한다.
- **표본 충분성**(`sufficiency`): 근사 독립 표본 수(returns=포인트수÷블록길이, trades=완결 거래 수)가 임계치(30) 미만이면 결과 화면 경고 배너와 쉬운 설명 문장으로 "분포는 참고용"임을 고지한다.
- **실행 설정 표시**: 결과 화면에 이 결과를 만든 실행 파라미터(방식 라벨·반복 횟수·seed, 거래 재표본이면 완결 거래 수·사이징 방식)를 노출한다. 값은 실행 결과 객체(`nIterations`/`blockMethod`/`blockSize`/`mode`/`seed`/`tradeCount`/`tradeSizing`)에서 직접 읽어, 실행 후 설정을 바꿔도 결과와 어긋나지 않게 한다(`seed`는 결과·저장 스냅샷에 포함해 불러오기 시 복원).
- **검증 대상 전략 표시**: 몬테카를로 화면 상단에 이 검증이 대상으로 삼는 전략의 구성(유니버스·진입 조건·청산 조건·포지션/리밸런싱/리스크)을 사람이 읽는 라벨(PBR≤1·MACD 골든크로스 등)로 노출한다. 라벨은 `BacktestDashboard`가 이미 만든 `strategySummary`(entryBlocks/exitBlocks/…)를 그대로 전달받아 렌더하며 별도 파싱을 하지 않는다. 구조화 요약이 없으면 `promptText`로 폴백한다. (표시는 현재 대시보드의 백테스트 전략 기준이며, 다른 전략의 저장 결과를 불러온 경우 요약은 현재 전략을 가리킨다.)
- 실행은 청크 단위로 진행률을 표시하고 취소 가능해야 하며, 유효 equity 포인트가 최소 요구치(max(30, blockSize×3)) 미만이면 명확한 에러를 반환한다.
- 모든 문구는 서술적 통계 표현만 사용하고 투자 추천·미래 성과 보장 표현을 금지한다(규제 안전 원칙).

**FR-BT-051b** 검증 결과 쉬운 설명 섹션(`ResultPlainSummary.tsx`): 전략 최적화(워크포워드·몬테카를로) 결과 화면에는 결과 수치를 일상 언어 문장으로 풀어 주는 "쉽게 이해하기" 섹션을 항상 표시해야 한다. 문장은 결과 데이터에서 결정적으로 생성하며(LLM 미사용), 검증 방법 요약·검증 구간/시나리오 성과·승패 구간 수(또는 수익/손실 시나리오 비중)·WFE(계산 불가/음수 포함) 또는 낙폭 분포·과거 데이터 기반 면책 문구를 포함한다. 모든 문장은 과거 서술형 통계 표현만 사용하고 추천·전망 표현을 금지한다(규제 안전 원칙).

**FR-BT-051** 검증 결과 저장·불러오기(`SavedValidation` 모델, `app/api/validation`, `lib/validation-storage.ts`): 워크포워드·몬테카를로 결과 화면 각각에 '결과 저장' 버튼을 제공해 실행 결과 스냅샷(모델 종류, 전략명·프롬프트·`cacheKey`, 실행 설정, 결과 전체 JSON, 목록 표시용 요약)을 DB에 영구 저장해야 한다. 저장은 로그인 사용자 본인 소유로 격리하며(`userId`, 비인증은 `userId IS NULL` 폴백), 목록 조회는 전체 결과 JSON을 제외한 경량 요약만 반환하고 불러오기 시 `GET /api/validation/[id]`로 전체 결과를 조회한다. '전략 최적화'(`OptimizationPage.tsx`) 사이드바의 '저장된 검증 결과 불러오기' 버튼이 저장 목록 모달을 열고, 항목 선택 시 해당 모델 화면으로 전환해 저장된 결과를 재렌더한다(워크포워드는 `WalkForwardPanel`에 `loadedResult` 주입, 몬테카를로는 결과·설정 복원). 목록에서 항목 삭제를 지원한다.

**FR-BT-051c** 전략 최적화 결과 닫기(`OptimizationPage.tsx`): 몬테카를로 **실행 결과가 표시된 화면에만** '결과 닫기' 버튼을 결과 헤더의 저장 버튼 옆에 노출한다(설정/실행 전 화면에는 노출하지 않는다). 결과가 나온 뒤에도 사용자가 이 버튼을 명시적으로 클릭하기 전까지는 결과 화면을 유지하며, 클릭 시에만 백테스트 결과 탭 화면으로 돌아간다(`BacktestDashboard`의 `isOptimizationPageOpen`을 false로 전환). 워크포워드 결과 화면은 별도 '결과 닫기'를 두지 않고 '재설정'(설정 화면 복귀)만 제공한다 — 최적화 뷰 자체는 검증 탭 전환·'전략 최적화' 토글로 닫는다.

**구현 파일:**
- `backend/engine/data_resolver.py` — `DataResolver` 클래스, `_collect_all_conditions()`, `_get_required_columns()`
- `backend/tests/test_data_resolver.py` — 유닛 테스트 20건

---

### 3.3 AI/ML 시스템

#### 3.3.1 하이브리드 예측 모델 v2

**FR-AI-001** AI 모델은 45개 피처를 입력으로 받아 10일 내 상승/하락 확률을 각각 독립적으로 예측해야 한다.

**FR-AI-002** 모델 아키텍처:

```
입력: 45개 피처 (멀티타임프레임 모멘텀, 변동성, 거래패턴, 캔들 패턴)
  │
  ├─ Conv1D Stem (3일/7일 멀티스케일 로컬 패턴 추출)
  │
  ├─ Advanced Transformer Encoder
  │   ├─ 128~256차원 임베딩 (Optuna 최적화)
  │   ├─ Rotary Positional Encoding (RoPE)
  │   ├─ Pre-LayerNorm + Stochastic Depth
  │   ├─ 4~8 Head Attention, 4~8 Encoder Layers
  │   ├─ Learnable [CLS] Token (전역 집계)
  │   └─ 256~1024차원 FFN
  │
  ├─ XGBoost UP Model (상승 예측 전용)
  │   └─ Transformer 임베딩 + 통계 피처 → P(7%+ 상승)
  │
  └─ XGBoost DOWN Model (하락 예측 전용)
      └─ Transformer 임베딩 + 통계 피처 → P(7%+ 하락)
```

**FR-AI-003** AI 시그널 조건(`ai_model`)은 임계값(threshold)과 방향(direction)을 파라미터로 받아 전략 시그널로 통합되어야 한다.

**FR-AI-004** (2026-06-09 검증) AI 예측 모델은 백테스트 검증 결과 전략 도구로서 알파를 내지 못하므로 시스템이 능동적으로 추천·노출하지 않아야 한다.
- 검증 범위: per-stock 진입/청산(워크포워드 2018~2025 8구간), 포트폴리오 breadth 위험 오버레이. 전 구간 평균에서 바이앤홀드(+15.2%/년)를 절대수익·CAGR·Sharpe 모두에서 하회.
- 모델 출력 점수는 보정되지 않은 좁은 분포(상승 0.20~0.30, 하락 0.33~0.40)에 밀집하여 기본 threshold=70은 신호를 생성하지 못한다.
- 시그널 블록(`ai_model`/`ai_drop_model`)과 DSL/엔진은 하위 호환을 위해 유지하며, 사용자가 직접 명시하면 동작한다. 단 조언/코치/전략연구소 예시는 AI 모델을 추천·노출하지 않는다 (FR-ADV-022).
- AI 조건이 포함된 백테스트를 in-process로 실행할 때는 polars rayon 데드락 방지를 위해 `POLARS_MAX_THREADS=1` 환경에서 실행해야 한다.

#### 3.3.2 설명 가능 AI (XAI)

**FR-AI-010** 시스템은 SHAP(SHapley Additive exPlanations)을 사용하여 매매 판단의 피처 기여도를 설명해야 한다.

**FR-AI-011** XAI 결과는 다음을 포함해야 한다:
- 매매별 피처 기여도 (어떤 지표가 매수/매도 판단에 기여했는지)
- Force Plot (개별 예측 분해)
- Bar Plot (전체 피처 중요도 순위)

#### 3.3.3 전략 최적화 (Optuna)

**FR-AI-020** 시스템은 Optuna TPE 기반 베이지안 최적화로 전략 파라미터를 자동 튜닝해야 한다.

**FR-AI-021** 최적화 타겟 메트릭은 사용자가 선택할 수 있어야 한다: CAGR / Sharpe / Profit Factor / Win Rate / Total Return.

**FR-AI-022** 최적화 결과는 최적 파라미터, Top-N 결과, 파라미터 중요도, 마크다운 리포트를 포함해야 한다.

**FR-AI-023** 최적화 파라미터에는 의미적 순서 제약이 적용되어야 한다 (예: `shortMA < longMA`).

---

### 3.4 가상 매매 시스템

#### 3.4.1 가상계좌 관리

**FR-VM-001** 사용자는 복수의 가상계좌를 생성하고 관리할 수 있어야 한다.

**FR-VM-002** 가상계좌 생성 시 다음 정보를 설정해야 한다:
- 계좌명
- 초기 투자금 (원)
- 연결 전략 (선택)
- 매매 모드: `manual` (수동) / `auto` (자동매매) / `signal` (신호 알림)

**FR-VM-003** 가상계좌는 현재 잔고, 총 평가금액, 수익률, 보유 포지션을 실시간으로 표시해야 한다.

#### 3.4.2 추적 종목 자동 선정

**FR-VM-010** 가상계좌에 전략이 연결된 경우, 시스템은 해당 전략의 백테스트 결과에서 **수익률 상위 10개 종목**을 자동으로 추적 종목으로 설정해야 한다.

**FR-VM-011** 추적 종목 선정 기준:
- 연결 전략의 최신 백테스트 결과 기준
- 개별 종목 총 수익률 기준 내림차순 정렬
- 상위 10개 종목 자동 선택
- 전략 변경 또는 재백테스트 시 자동 갱신

**FR-VM-012** 사용자는 자동 선정된 추적 종목을 수동으로 추가/제거할 수 있어야 한다.

**FR-VM-013** 추적 종목은 `VirtualMarketState.symbols`에 저장되며, 가상 시장 엔진이 이 종목들에 대해 시그널을 감시해야 한다.

#### 3.4.3 주문 처리

**FR-VM-020** 시스템은 시장가 주문과 지정가 주문을 지원해야 한다.

**FR-VM-021** 지정가 주문은 지정 가격 도달 시 자동으로 체결(`filled`) 처리해야 한다 (`PENDING` → `FILLED`).

**FR-VM-022** 체결 시 수수료(기본 0.015%)와 거래세(매도 시 0.20%)를 차감해야 한다.

**FR-VM-023** 중복 매매를 방지해야 한다: 동일 계좌에서 동일 종목에 대한 미체결 주문이 존재하면 신규 매수 주문을 거부해야 한다.

#### 3.4.4 포지션 관리

**FR-VM-030** 시스템은 보유 포지션별로 다음 정보를 추적해야 한다:
- 종목코드 / 종목명
- 보유 수량
- 평균 매수가
- 현재가
- 평가 손익 (금액, %)
- 최고가 (`peakPrice`, 트레일링 스탑 계산용)

**FR-VM-031** 포지션 현재가는 가상 시장 엔진이 주기적으로 갱신해야 한다.

#### 3.4.5 가상 시장 엔진 (자동매매)

**FR-VM-040** 자동매매 모드에서 가상 시장 엔진은 추적 종목에 대해 연결된 전략의 시그널을 평가하고, 조건 충족 시 자동으로 주문을 생성해야 한다.

**FR-VM-041** 리스크 관리 규칙(SL/TP/TS/MaxHold)은 자동매매에서도 동일하게 적용되어야 한다.

**FR-VM-042** 시그널 알림 모드에서는 자동 주문 없이 사용자에게 매수/매도 시그널을 알림으로 제공해야 한다.

**FR-VM-043** 가상 시장 엔진은 다음 데이터 소스를 우선순위 순으로 사용해야 한다:
1. KIS (한국투자증권) WebSocket (실시간)
2. Naver Finance API
3. yfinance
4. pykrx

**FR-VM-044** 가상 시장 갱신 이력은 `VirtualMarketLog`에 기록되어야 한다 (날짜, 종목코드, 종목명, 시그널 유형, 가격, 액션).

**FR-VM-045** 자동 실행과 시그널 알림은 계좌·종목·시그널 유형별로 **하루 1회**만 기록/실행되어야 한다 (30초 평가 틱마다 중복 알림 금지).

**FR-VM-046** PENDING 지정가 주문 체결은 두 경로(백엔드 VirtualTrader 루프, 브라우저 fill 라우트) 어느 쪽에서든 `status = 'PENDING'` 조건부 갱신으로 **원자적으로 선점**해야 하며, 동일 주문이 두 번 체결되어서는 안 된다. 매도 체결 시 보유 수량이 부족하면 주문을 `CANCELLED` 처리한다.

**FR-VM-047** 가상계좌 거래 비용 모델은 백테스트 엔진과 정합해야 한다: 수수료 0.015%, 증권거래세(매도) 0.15%(백테스트 기본값과 동일), 시장가 슬리피지 0.05%, KRX 호가단위(2023-01 개편 기준).

**FR-VM-048** 백엔드(Python)가 Prisma 관리 테이블의 DateTime 컬럼에 기록할 때는 Prisma와 동일한 **epoch ms 정수** 포맷을 사용해야 한다 (포맷 혼재 시 SQLite 정렬이 왜곡됨). 읽기는 epoch ms 정수와 ISO 문자열(레거시)을 모두 허용한다.

**FR-VM-049** 자동매매는 **당일(KST) 날짜의 시세만** 사용해야 한다. 시세의 `date`가 오늘이 아니거나 없으면(평일 공휴일의 KRX 휴장, 데이터 소스 장애) 해당 종목의 진입·청산·리스크 청산·지정가 체결을 모두 보류한다. 별도의 휴장일 캘린더 없이 이 가드가 휴장일 매매를 방지한다.

#### 3.4.6 거래 내역

**FR-VM-050** 시스템은 모든 체결 내역을 저장하고 조회할 수 있어야 한다.

**FR-VM-051** 거래 내역은 매수/매도 구분, 체결 가격, 수량, 수수료, 실현 손익, 체결 시각을 포함해야 한다.

#### 3.4.7 상장폐지 리스크 대응 ✅ 완료

**FR-VM-060** 시스템은 종목의 상장 상태를 다음 7단계로 추적해야 한다:
`NORMAL` → `WARNING` → `RISK` → `TRADING_SUSPENDED` → `DELISTING_REVIEW` → `DELISTING_SCHEDULED` → `DELISTED`

**FR-VM-061** 각 상태의 거래 허용 규칙:
| 상태 | 매수 | 매도 | 비고 |
|------|------|------|------|
| NORMAL / WARNING / RISK | ✅ | ✅ | |
| TRADING_SUSPENDED | ❌ | ❌ | 거래소 정지 |
| DELISTING_REVIEW | ❌ | ✅ | 청산만 허용 |
| DELISTING_SCHEDULED | ❌ | ✅ | 정리매매 허용 |
| DELISTED | ❌ | ❌ | 0원 평가 |

**FR-VM-062** DART 공시 `report_nm`을 수신하면 키워드 기반으로 ListingStatus를 자동 분류하여 Stock 테이블에 반영해야 한다.

**FR-VM-063** 주문 API(`orders/route.ts`)는 주문 전 Stock.listingStatus를 확인하고, 허용되지 않는 상태이면 HTTP 403과 차단 사유 메시지를 반환해야 한다. 차단 이벤트는 `DelistingAuditLog`에 기록해야 한다.

**FR-VM-064** 포지션 조회 API는 DELISTED 종목의 `currentPrice`를 0으로 반환하고 `totalValue = 0`으로 계산해야 한다.

**FR-VM-065** 가상계좌는 `delistingPolicy` 설정을 가져야 한다 (기본값: `AUTO_LIQUIDATE`).
- `AUTO_LIQUIDATE`: 강제청산 이벤트 발생 시 마지막 시세로 매도 또는 0원 제거
- `HOLD_AS_WORTHLESS`: 청산 없이 0원으로 보유
- `HOLD_WITH_MANUAL_REVIEW`: 수동 처리 대기

**FR-VM-066** VirtualTrader 매매 사이클은 매 반복마다 보유/추적 종목의 상장 상태를 확인하고, 비정상 상태에 따라 매수 차단 / 강제청산 신호를 주입해야 한다.

**FR-VM-067** 백테스트 엔진은 생존자 편향(survivorship bias)을 제거하기 위해 **시점 기준(point-in-time) 유니버스**를 사용해야 한다.
- `data/stock-master.json`(FDR 현행상장 + KRX-DELISTING 병합: 시장·상장일·상폐일·상장주식수·상폐사유)을 진실 소스로 사용한다.
- `engine/universe_pit.resolve_symbols(universe_id, start, end)`는 백테스트 구간에 **실제 상장·거래되던** 종목을 반환한다(상폐일이 구간 내인 종목 포함). 규칙: `market 일치 AND hasOhlcv AND dataStart ≤ end AND dataEnd ≥ start`.
- 상폐 종목의 OHLCV는 `scripts/backfill_delisted_ohlcv.py`로 FDR에서 백필한다(정리매매 종가까지).
- 상폐 종목의 펀더멘털(EPS/BPS/PER/PBR/ROE/부채비율)은 `scripts/backfill_delisted_fundamentals.py`로 DART(전자공시) 연간 재무(자본총계/부채총계/당기순이익 ÷ 상장주식수)에서 도출해 OHLCV에 baked-in한다. 이로써 PBR≤1 등 펀더멘털 필터가 상폐 가치주(예: 락앤락 PBR 0.75)도 정상 선택한다.
- 보유 중 상폐된 종목은 마지막 거래일에 강제청산되며(`_close_at_last_available_row`), 청산 사유는 "상장폐지"로 기록된다.
- "대형주"/KOSPI200은 정적 현재 명부 대신 **매 시점 시총 상위 N**(close×상장주식수, `LARGE_CAP_TOP_N=200`)으로 재정의하여 지수편입 멤버십 편향도 제거한다.
- (※ 구 명세: `delisted_store.is_delisted`로 상폐 종목을 *제외* — 이는 생존편향을 오히려 유발했고 백테스트 엔진에 미구현 상태였음. 위 시점 유니버스 방식으로 대체.)

**FR-VM-068** `/virtual-account/[id]` 페이지는 비정상 상장 상태 종목에 대해 `DelistingRiskBanner`를 표시해야 한다. 배너는 상태 배지, D-N 카운트다운, 강제청산 버튼을 포함해야 한다. 단, `TRADING_SUSPENDED`는 목록 행의 '거래정지' 배지로만 표시하고 배너는 띄우지 않는다.

**FR-VM-069** 모든 자동 처리 이벤트(청산, 차단, 상태변경)는 `DelistingAuditLog`에 기록되어야 한다.

**FR-VM-070** 백테스트 엔진은 **수정주가(adjusted price)**를 연속적으로 반영해야 한다. 소스 데이터는 정방향 액면분할만 조정돼 있고 역분할·감자·정지후재개·단일 오류프린트는 미조정이라 ±30% 가격제한을 넘는 불가능한 일간 점프가 남는다(가짜 손절·수익 유발). `loader._sanitize_corporate_actions`(`preprocess_data` 내)가 이를 처리한다:
- 단일 오류프린트(다음 바 반등) → 양옆 보간 중립화.
- 지속 레벨변화(역분할/감자/정지재개) → 점프 비율로 과거 전체를 역조정(OHLC 동일 스케일).
- 정리매매(시계열 끝 하락 크래시, `_CA_TAIL_GUARD`바 내)는 역조정하지 않는다 — 상장폐지 손실이 수익곡선에 남아야 한다.

**FR-VM-071** 가상계좌 모니터링(추적) 종목 목록은 상장폐지(`DELISTED`) 및 매매거래정지(`TRADING_SUSPENDED`) 종목을 포함하지 않아야 한다. 모든 모니터링 종목 진입 경로(전략 백테스트 상위 종목, 유니버스 기본 종목, 사용자 수동 지정)는 `filterMonitorableSymbols`(`lib/strategy-tracked-symbols.ts`)를 거쳐야 한다.

**FR-VM-072** DART 공시 폴링(FR-VM-062)이 놓친 거래정지 종목을 보정하기 위해, 시세 수신 경로에서 거래정지 상태를 자동 동기화해야 한다. KIS `inquire-price` 응답의 종목상태구분코드(`iscd_stat_cls_code`, 58=거래정지)를 `StockQuote.trading_halted`로 파싱하고, VirtualTrader 매매 사이클이 `sync_trading_halt`(`engine/listing_status.py`)로 Stock 테이블에 반영한다:
- `True`: NORMAL/WARNING/RISK → TRADING_SUSPENDED (Stock 행이 없으면 생성)
- `False`: TRADING_SUSPENDED → NORMAL (거래 재개 복원)
- DELISTING_REVIEW / DELISTING_SCHEDULED / DELISTED는 덮어쓰지 않는다 (DART 분류 우선)
- VirtualTrader의 시세 조회 대상은 **추적 종목 ∪ 보유 포지션 종목**이다 — 추적 목록에서 빠진(FR-VM-071 필터 등) 보유 종목도 현재가 갱신·리스크 청산·상장 상태 체크·재개 감지가 계속 동작해야 한다.
- 어느 계좌도 추적/보유하지 않는 TRADING_SUSPENDED 종목은 장중 주기 스윕(`_sweep_suspended_resume`, `HALT_RESUME_SWEEP_INTERVAL`=600초)이 시세를 조회해 재개를 복원한다 — FR-VM-071 필터로 모니터링에서 제외된 종목이 영구 정지 상태로 남는 것을 방지.

---

### 3.4b Strategy Research Agent (Premium)

#### 3.4b.1 개요

**FR-RA-001** Strategy Research Agent는 PREMIUM 플랜 사용자만 사용할 수 있어야 한다 (`User.planTier == 'PREMIUM'`, HTTP 헤더 `X-User-Id` 검증).

**FR-RA-002** 에이전트는 다음 단계를 순서대로 실행해야 한다:

```
1. generate   — DSL 블록 조합으로 후보 전략 생성 (SHA256 dedup)
2. prescreen  — 50종목 샘플 백테스트로 기초 필터링 (CircuitBreaker 연동)
3. robustness — MC + WFA 견고성 검증
4. optimize   — Optuna 파라미터 최적화 (n_trials ≤ √cardinality)
5. holdout    — 잠금 홀드아웃 구간 검증 (h_sharpe ≥ 0.3 AND sign(h_cagr)==sign(b_cagr))
6. finalize   — DB 저장 + VirtualAccount 승격 (사용자 명시적 시작 필요)
```

**FR-RA-003** 에이전트 실행은 BackgroundTask로 비동기 처리되어야 하며, SSE 스트림(`GET /research/runs/{id}/stream`)으로 실시간 진행 상황을 전달해야 한다.

#### 3.4b.2 안전 장치

**FR-RA-010** HoldoutGuard: 모든 백테스트 요청의 `endDate`를 홀드아웃 시작일 전날로 클램핑해야 한다. 이미 홀드아웃 기간을 침범한 요청은 `HoldoutViolation` 예외로 거부해야 한다.

**FR-RA-011** CircuitBreaker: N회 연속 zero-trade 프리스크린 시 자동 차단하여 불필요한 백테스트 실행을 방지해야 한다.

**FR-RA-012** AIModelLeakGuard: `ai_model`/`ai_drop_model` 블록을 포함한 전략의 학습 기간이 AI 모델 훈련 데이터 기간과 겹치면 거부해야 한다.

**FR-RA-013** PrescreenGates: 최소 거래 횟수(30회), 최소 Profit Factor(1.0), 최대 MDD(50%) 기준을 충족하지 못하는 후보는 탈락시켜야 한다.

#### 3.4b.3 스코어링

**FR-RA-020** 복합 점수는 다음 가중치로 계산해야 한다 (robustness+mdd_penalty = 0.50 > 수익 관련 = 0.50):

```
score = tanh(cagr/0.3)×0.15 + tanh(sharpe/2)×0.20 + tanh(pf/2)×0.10
      + tanh(wr/0.6)×0.05 - tanh(mdd/0.3)×0.30 + robustness_score×0.20
```

**FR-RA-021** Deflated Sharpe Ratio(Bailey-López de Prado)를 적용하여 다중 테스팅 편향을 보정해야 한다.

**FR-RA-022** regime_consistency: 에퀴티 커브를 4분위 구간으로 분할하여 최악 분기 / 최선 분기 비율을 계산하고 스코어에 반영해야 한다.

#### 3.4b.4 일일 예산 및 제한

| 항목 | 값 |
|------|----|
| 일일 후보 예산 | 5,000건/사용자/일 (`RESEARCH_DAILY_BUDGET`) |
| 승격 상한 | 활성 auto 계좌 5개 (`RESEARCH_PROMOTION_CAP`) |
| 에이전트 비활성화 | `RESEARCH_AGENT_DISABLED=true` 환경변수 → 503 |

---

### 3.5 포트폴리오 관리

#### 3.5.1 홈 대시보드

**FR-PF-001** 홈 대시보드는 다음 위젯을 포함해야 한다:
- WelcomeSection: 사용자 인사, 전체 수익률 요약
- StrategyOverview: 저장된 전략 목록 및 최근 백테스트 성과
- BacktestHistory: 최근 백테스트 이력 5건
- VirtualAccountSummary: 가상계좌 전체 현황 (총 자산, 수익률)
- MarketSnapshot: KOSPI/KOSDAQ 지수, 상승/하락 종목 수

#### 3.5.2 포트폴리오 대시보드

**FR-PF-010** 전체 가상계좌를 통합한 포트폴리오 현황을 제공해야 한다.

**FR-PF-011** 종목별 비중을 파이차트와 섹터별 분산도로 시각화해야 한다.

**FR-PF-012** 총 자산 추이를 차트로 표시해야 한다.

#### 3.5.2a 요금제 & 플랜 제한 (가상계좌 초기 투자금)

플랜 정의(`lib/plans.ts`): Free(초기 투자금 1,000만원·계좌 1개·전략 3개·월 백테스트 30회),
Pro(5,000만원·10개·50개·500회), Premium(1억원·30개·무제한·1,000회). 기본 가입자는 Free.

**FR-PLAN-001** 각 가상계좌는 사용자의 현재 플랜에 정의된 **계좌당 초기 투자금**으로 생성되어야 하며,
초기 투자금은 서버가 플랜 기준으로 결정한다(클라이언트가 보낸 금액은 무시). 이 금액이 계좌의
`initialCash`와 `currentCash`로 설정되어야 한다.

**FR-PLAN-002** 활성 가상계좌 수가 플랜의 `maxVirtualAccounts` 이상이면 신규 계좌 생성을 거부해야 한다
(Free 2개째, Pro 11개째, Premium 31개째 차단).

**FR-PLAN-003** 저장된 전략 수가 플랜의 `maxStrategies` 이상이면 신규 전략 저장을 거부해야 한다
(Free 4개째, Pro 51개째 차단). Premium은 전략 수 무제한.

**FR-PLAN-004** 월 백테스트 실행 횟수를 기록하고 초기화하며, 한도를 초과하면 실행을 막고 업그레이드
안내를 표시해야 한다. 기존 전략 업데이트(동일 id 재저장)는 한도에 포함하지 않는다. 초기화 기준은
FR-PLAN-010 참고(구독 이력이 있으면 구독 시작일, 없으면 가입일 기준 롤링 1개월 주기).

**FR-PLAN-005** 플랜 변경은 `planTier`만 변경하며, 이미 생성된 계좌의 초기 투자금과 잔고는 소급 변경하지
않아야 한다. 변경 이후 생성되는 계좌부터 새 플랜의 초기 투자금이 적용된다.

**FR-PLAN-010** 유료 플랜(PRO/PREMIUM) 구독이 시작되면 그 시점을 `User.planStartDate`로 기록해야
하며, "내 플랜" 모달의 플랜 종료 날짜는 `planStartDate` 기준 롤링 1개월 후로 계산해 표시해야 한다
(여러 달이 경과했으면 현재 시점을 포함하는 주기까지 자동으로 굴러간다). FREE로 전환하면
`planStartDate`는 null로 초기화된다. 구독 이력이 없는 사용자(FREE)는 가입일(`User.createdAt`)을
주기 앵커로 사용해, "내 플랜" 모달의 시작/종료 날짜에 현재 주기(가입일 기준 롤링 1개월)의
시작일/종료일을 표시해야 한다. 월 백테스트 사용량 리셋은 이 롤링 주기를 따른다. "내 플랜" 모달의
백테스트 횟수 아래에는 리셋까지 남은 시간을 표시해야 하며, 24시간 이하면 시간 단위("Reset in 5h"),
그 외에는 일 단위("Reset in 3 days")로 표시한다. 가상계좌 수·저장 전략 수 한도는
주기 리셋 대상이 아니며 상시 캡으로 유지된다.

**FR-PLAN-011** 유료 플랜(PRO/PREMIUM) 구독은 토스페이먼츠 자동결제(빌링)를 통한 카드 등록 +
첫 달 결제 승인으로만 시작되어야 한다.
- 결제 주문(`POST /api/payment/order`)의 금액은 서버의 플랜 정의(`lib/plans.ts`)에서만 계산하고
  `PaymentOrder`에 기록해야 하며, 클라이언트가 보낸 금액은 신뢰하지 않아야 한다.
- 체크아웃은 카드 등록창(`payment.requestBillingAuth`, method=CARD)을 사용하고, 결제 전 화면에
  월 자동갱신 결제 조건(상품명·금액·자동 청구·해지 방법)을 고지해야 한다(약관 제12조 1·7항).
- 구독 승인(`POST /api/payment/confirm`)은 successUrl로 돌아온 `customerKey`를 서버 저장
  `User.tossCustomerKey`와 대조해 불일치 시 거부해야 하고, `authKey`로 빌링키를 발급
  (`/v1/billing/authorizations/issue`)한 뒤 첫 달 이용료를 서버 저장 주문 금액으로 즉시 청구
  (`/v1/billing/{billingKey}`)해야 한다. 청구 성공 시에만 `planTier`·`planStartDate`·
  `tossBillingKey`·`subscriptionPlanId`·`nextBillingAt`(+1개월)을 갱신한다.
- 동일 주문의 승인 재요청(성공 페이지 새로고침 등)은 중복 승인 없이 기존 결과를 반환해야 한다
  (멱등키=orderId).
- `POST /api/user/plan`은 FREE 전환(다운그레이드)만 허용해 결제 없는 유료 전환을 차단해야 하며,
  FREE 전환 시 빌링키·구독 상태를 모두 해제해 이후 자동 청구가 발생하지 않아야 한다.
- 시크릿 키(`TOSS_SECRET_KEY`)와 빌링키(`User.tossBillingKey`)는 서버 전용이며 클라이언트에 노출되지
  않아야 한다. `customerKey`는 이메일·회원번호 등 유추 가능한 값이 아닌 사용자당 1회 생성된
  UUID(`User.tossCustomerKey`)를 사용해야 한다.
- 인증 실패/취소(failUrl)는 승인 API를 호출하지 않고 오류 코드에 따른 안내와 재시도 경로만 제공해야
  한다.

**FR-PLAN-011a** 구독은 해지 전까지 매월 자동 갱신 결제되어야 한다.
- 인-프로세스 스케줄러가 매시 정각(주말 포함) 갱신 잡(`processDueBillingRenewals`)을 실행해
  `nextBillingAt`이 지난 구독을 빌링키로 청구하고, 성공 시 `nextBillingAt`을 예정 시각 기준
  +1개월로 굴려야 한다(재시도 지연으로 결제 주기가 밀리지 않아야 한다). 갱신 결제도
  `PaymentOrder`에 기록한다.
- 청구 실패 시 1일 후 재시도하고, 연속 3회 실패하면 FREE로 전환하며 빌링 상태를 해제해야 한다.
  한 구독의 처리 실패가 다른 구독의 갱신을 막지 않아야 한다.
- 해지(`POST /api/payment/billing/cancel`)는 즉시 FREE 전환이 아니라 해지 예약
  (`subscriptionCanceledAt`)으로 처리해야 한다 — 이미 결제된 기간에는 유료 플랜을 유지하고, 다음
  결제일에 청구 없이 FREE로 전환한다(약관 제12조 8항). 해지 재요청은 멱등 처리한다.
- 요금제 페이지는 자동갱신 중인 현재 플랜에 다음 결제일과 해지 수단을, 해지 예약 시 만료일을
  표시해야 한다.

**FR-PLAN-006** 가상계좌 해지 요청은 포지션 강제 매도와 계좌 `CLOSED` 전환을 하나의 트랜잭션으로 처리하되,
남은 현금·평가금액을 다른 계좌나 사용자 자산으로 **이전하지 않아야 한다**. 해지 후 계좌 슬롯은 다시
사용 가능해야 한다.

**FR-PLAN-006a** 가상계좌 카드의 해지 버튼을 누르면 해지 전 확인 모달을 표시해야 하며, 모달은
"남은 현금과 보유 종목은 다른 계좌로 이전되지 않습니다"를 명확히 알려야 한다.

**FR-PLAN-007** 계좌 정산값은 `AssetLedger`의 `ACCOUNT_LIQUIDATION_RETURN` 원장에 기록되어 닫힌 계좌의
최종 평가금액/수익률 계산에 사용해야 한다(공유 자산 풀로의 반환은 수행하지 않음).

**FR-PLAN-008** `CLOSED` 계좌는 신규 주문과 재해지 요청을 거부해야 한다.

**FR-PLAN-009** 사용자 노출 문구에서 "자산/충전/포인트/크레딧/지급/리워드/캐시" 표현을 사용하지 않고
"초기 투자금/계좌당 초기 투자금/가상계좌/저장 가능 전략/월 백테스트/사용 중인 계좌/이번 달 백테스트
사용량" 용어를 사용해야 한다.

**FR-ASSET-009** 사용자는 프로필 메뉴의 `자산` 항목에서 총 자산, 사용 가능 자산, 가상계좌 운용 중 자산, 총 수익/손실을 모달로 조회할 수 있어야 한다. 전용 자산 화면에서는 자산 이동 내역까지 조회할 수 있어야 한다.

#### 3.5.3 관심 종목

**FR-PF-020** 사용자는 종목을 관심 목록에 추가/삭제하고 그룹으로 관리할 수 있어야 한다.

**FR-PF-021** 관심 종목 데이터는 SQLite DB에 영구 저장되어야 한다.

**FR-PF-022** 관심 종목 목록은 현재가, 등락률, 거래량을 실시간으로 표시해야 한다.

#### 3.5.4 분석 페이지 (Strategy Lab)

**FR-PF-030** Analytics 페이지는 저장된 전략들의 성과를 비교 분석할 수 있어야 한다.

**FR-PF-031** 전략 유형별 필터링 및 정렬 기능을 제공해야 한다.

---

### 3.6 뉴스 Impact AI Agent

> 뉴스·공시 데이터를 실시간 수집·분류하여 종목별 Alpha 시그널을 생성하는 시스템.

#### 3.6.1 뉴스 수집

**FR-NEWS-001** 시스템은 다음 뉴스 공급자에서 자동으로 뉴스를 수집해야 한다:

| 공급자 | 유형 | 데이터 |
|--------|------|--------|
| Naver Finance RSS | Primary | 4개 피드 (시장전망, 경제, 기업, 글로벌) — API 키 불요 |
| 한국경제 RSS | Secondary | 경제/증권 뉴스 |
| 연합뉴스 RSS | Secondary | 시황/기업 뉴스 |
| 매일경제 RSS | Secondary | 증권/기업 뉴스 |

**FR-NEWS-002** 수집된 뉴스는 `NormalizedArticle` 스키마로 정규화되어야 한다 (id, title, summary, url, source, published_at, body_hash, category, symbols, scope, sector 포함).

#### 3.6.2 뉴스 중복 제거

**FR-NEWS-010** 시스템은 다음 기준으로 중복 뉴스를 제거해야 한다:

| 우선순위 | 방법 | 설명 |
|---------|------|------|
| 1 | Body hash 일치 | 동일 본문 해시 → 즉시 dup 처리 |
| 2 | 제목 Jaccard 유사도 | 24h 내 유사도 ≥ 0.5 → dup 처리 |

**FR-NEWS-011** 10자 미만 짧은 제목은 유사도 검사를 건너뛰어야 한다.

**FR-NEWS-012** 동일 배치 내 중복(intra-batch dedup)도 처리해야 한다.

#### 3.6.3 뉴스 임팩트 분석

**FR-NEWS-020** 시스템은 수집된 뉴스 아이템을 분석하여 다음 정보를 생성해야 한다:

| 필드 | 설명 |
|------|------|
| `event_type` | 이벤트 유형 (earnings_beat / analyst_upgrade / share_buyback / guidance_down / large_contract 등) |
| `sentiment` | 감성 분류 (positive / negative / neutral) |
| `impact_direction` | 예상 주가 방향 (up / down / neutral) |
| `impact_score` | 영향 강도 (-1.0 ~ 1.0) |
| `confidence_score` | 신뢰도 (0.0 ~ 1.0) |
| `expected_alpha_1d` | 예상 1일 Alpha (%) |

**FR-NEWS-021** 시스템은 종목별 최신 Alpha 시그널(`latest_alpha`)과 위험 경보 수준(`risk_alert_level`)을 제공해야 한다.

#### 3.6.4 뉴스 API

**FR-NEWS-030** 시스템은 다음 API 엔드포인트를 제공해야 한다:

| 엔드포인트 | 설명 |
|-----------|------|
| `GET /api/news/symbol/[symbol]` | 종목별 뉴스 목록 (page, page_size, as_of 파라미터) |
| `GET /api/news/impact/[symbol]` | 종목 Alpha 시그널 (latest_alpha, risk_alert_level) |
| `GET /api/news/top` | 주요 시장 뉴스 피드 |
| `GET /api/news/fetch-body` | 기사 본문 일부 추출 프록시 |

**FR-NEWS-031** 백엔드 미가동 시 Next.js API Route는 seed 데이터를 폴백으로 반환해야 한다 (개발/테스트 환경 지원).

**FR-NEWS-032** 기사 본문 fetch 기능은 `http`/`https` URL만 허용해야 하며, localhost, private IP, loopback, link-local, multicast, reserved, unspecified, non-global IP, userinfo URL을 거부해야 한다.

**FR-NEWS-033** 기사 본문 fetch 기능은 redirect를 자동 추종하기 전에 `Location` URL을 재검증해야 하며, redirect 후 최종 URL도 동일한 SSRF 방어 규칙을 통과해야 한다.

#### 3.6.5 뉴스 UI — NewsImpactPanel

**FR-NEWS-040** `NewsImpactPanel` 컴포넌트는 다음을 표시해야 한다:
- 최신 Alpha 시그널 배지 (방향, 신뢰도, 이벤트 유형)
- 위험 경보 수준 (low / medium / high)
- 뉴스 목록 (제목, 출처, 시각, 감성, 임팩트 점수)

**FR-NEWS-041** `app/stock-order/page.tsx`의 "뉴스·공시" 탭은 `NewsImpactPanel`을 사용해야 한다.

#### 3.6.6 종목 상세 뉴스탭 캐시 API

**FR-NEWS-050** 종목 상세 뉴스탭은 조회 전용 UI여야 한다. 사용자가 뉴스탭을 클릭할 때 크롤링, 외부 뉴스 검색, scraper, LLM summarizer, news agent 분석을 실행하면 안 된다.

**FR-NEWS-051** 시스템은 `GET /api/stocks/{symbol}/news?limit=30` API를 제공해야 한다.

**FR-NEWS-052** `GET /api/stocks/{symbol}/news`는 `stock_news_cache` 또는 동등한 캐시 저장소만 조회해야 하며, API 내부에서 news agent, crawler, scraper, LLM summarizer를 직접 실행하면 안 된다.

**FR-NEWS-053** `GET /api/stocks/{symbol}/news` 응답은 다음 필드를 포함해야 한다:

| 필드 | 설명 |
|------|------|
| `symbol` | 조회 종목 코드 |
| `items[].newsId` | 뉴스 고유 ID |
| `items[].title` | 뉴스 제목 |
| `items[].url` | 원문 URL |
| `items[].source` | 언론사 |
| `items[].publishedAt` | 발행 시각 |
| `items[].summary` | 분석 또는 raw fallback 요약 |
| `items[].sentiment` | positive / neutral / negative |
| `items[].impactScore` | 0~1 범위 영향도 점수 |
| `items[].importance` | high / medium / low |
| `lastUpdatedAt` | 캐시 마지막 갱신 시각 |
| `isStale` | 캐시 stale 여부 |

**FR-NEWS-054** 캐시가 없는 경우 API는 즉시 빈 `items` 배열을 반환하고, 해당 symbol refresh job을 queue에 넣어야 한다. API 요청은 수집/분석 완료까지 blocking하면 안 된다.

**FR-NEWS-055** 뉴스탭 프론트엔드는 종목 상세 페이지 진입 시 React Query로 `["stock-news", symbol]` query를 prefetch해야 한다. 기본 설정은 `staleTime=60초`, `refetchOnWindowFocus=false`, `enabled=!!symbol`이어야 한다.

**FR-NEWS-056** 뉴스탭 UI는 최신 뉴스가 위에 오도록 정렬하고, 각 뉴스 카드에 제목, 언론사, 발행 시간, 요약, 감성, 영향도 점수, 중요도를 표시해야 한다.

**FR-NEWS-057** 뉴스탭 UI는 loading, empty, stale, error 상태를 구분해야 하며, 캐시가 없으면 "최근 뉴스가 준비 중입니다" 또는 "최근 뉴스가 없습니다" 상태를 표시해야 한다.

#### 3.6.7 뉴스 수집 백그라운드 파이프라인

**FR-NEWS-060** 시스템은 다음 파이프라인으로 뉴스를 처리해야 한다:

```
News Collector
→ Raw News DB
→ Deduplication
→ Symbol Mapping
→ News Agent Analysis
→ StockNewsCache
→ News Tab API
```

**FR-NEWS-061** 원본 뉴스 저장소는 최소 `title`, `url`, `source`, `published_at`, `raw_content`, `created_at` 필드를 저장해야 한다.

**FR-NEWS-062** 분석 결과 저장소는 `news_id` 기준으로 `sentiment`, `impact_score`, `importance`, `summary`, `analyzed_at`을 저장해야 한다.

**FR-NEWS-063** 종목 뉴스 캐시는 `symbol`, `news_id`, `published_at`, `rank_score`, `cached_at`을 저장해야 한다.

**FR-NEWS-064** 동일 URL은 중복 저장하면 안 된다.

**FR-NEWS-065** URL이 달라도 제목이 거의 같은 뉴스는 title hash 또는 normalized title 기준으로 중복 제거해야 한다.

**FR-NEWS-066** 중복 뉴스가 여러 언론사에 존재하면 `published_at`, source priority, content quality 기준으로 대표 뉴스를 선택해야 한다.

**FR-NEWS-067** Symbol Mapping은 뉴스 제목과 본문에서 종목명, 종목코드, 별칭, 섹터성 표현을 기준으로 관련 종목을 매핑해야 한다.

**FR-NEWS-068** 하나의 뉴스는 여러 종목에 연결될 수 있어야 한다.

**FR-NEWS-069** news agent는 scheduler 또는 queue worker 같은 백그라운드 작업에서만 실행되어야 한다.

**FR-NEWS-070** news agent 분석 실패 시 raw news만이라도 cache에 노출할 수 있어야 하며, 실패는 로그와 retry queue에 기록해야 한다.

#### 3.6.8 News Collection Priority Engine

**FR-NEWS-080** 시스템은 모든 종목의 뉴스를 동일 주기로 수집하지 않고, 사용자 수요 기반으로 종목별 priority score를 계산해야 한다.

**FR-NEWS-081** priority score는 현재 조회 종목, 관심종목, 가상계좌 보유 종목, 최근 조회 수, 검색 수, 거래대금, 뉴스 velocity, 시장 지수 편입, 시가총액을 조합해야 한다.

**FR-NEWS-082** 현재 보고 있는 종목은 가장 높은 우선순위를 가져야 한다.

**FR-NEWS-083** 관심종목과 가상계좌 보유 종목은 시가총액보다 높은 우선순위를 가져야 한다.

**FR-NEWS-084** 사용자 행동 데이터는 시장 데이터보다 우선해야 한다.

**FR-NEWS-085** 시스템은 다음 사용자 행동 이벤트를 수집할 수 있어야 한다:
- 종목 페이지 진입
- 관심종목 추가
- 관심종목 제거
- 가상계좌 보유 종목 변화
- 종목 검색
- 종목 상세 조회

**FR-NEWS-086** Priority Engine은 5분 단위 또는 설정 가능한 주기로 score를 재계산해야 한다.

**FR-NEWS-087** 시스템은 score에 따라 종목을 Hot Queue, Warm Queue, Cold Queue로 자동 배치해야 한다.

**FR-NEWS-088** Hot Queue는 현재 조회 중 종목, 관심종목, 보유종목, 최근 조회 급증 종목을 대상으로 1~5분 주기로 수집해야 한다.

**FR-NEWS-089** Warm Queue는 거래대금 상위, 시가총액 상위, 주요 지수 편입 종목을 대상으로 10~30분 주기로 수집해야 한다.

**FR-NEWS-090** Cold Queue는 나머지 전체 종목을 대상으로 1~6시간 주기로 순회 수집해야 한다.

**FR-NEWS-091** News Velocity Score는 최근 1시간 뉴스 수를 최근 24시간 평균 뉴스 수와 비교해 계산해야 한다.

**FR-NEWS-092** 조회 수 급증, 뉴스 발생량 급증, 거래대금 급증, 관심종목 추가 급증 중 하나 이상을 만족하는 종목은 trending stock으로 분류하고 Hot Queue로 승격해야 한다.

**FR-NEWS-093** 사용자 데이터가 충분하지 않은 경우 KOSPI200, KOSDAQ150, 거래대금 상위, 시가총액 상위 순서로 fallback 수집 대상을 선정해야 한다.

**FR-NEWS-094** 백엔드 news scheduler가 시작되면 설정에 따라 Celery worker를 자동 기동할 수 있어야 한다.

**FR-NEWS-095** worker autostart는 중복 worker 방지를 위해 pid lock file과 broker active queue inspect를 사용해야 한다.

**FR-NEWS-096** 운영 환경에서 별도 worker manager를 사용하는 경우 `NEWSV2_WORKER_AUTOSTART_ENABLED=false`로 내장 autostart를 비활성화할 수 있어야 한다.

---

### 3.6b 종목 질문 의도 분류·전략 전환 (구 Stock Analysis Agent)

> 사용자의 개별 종목 질문("삼성전자 사볼까?", "005930 어때?")을 의도 분류로 식별하는 모듈. **개별 종목 분석 기능(지표 패널·상태 등급·`/stock/analyze`)은 2026-07-10 제거됐다** — 플랫폼 목적(전략 만들기)에 기여하지 않고 규제 리스크만 키우기 때문. 종목 질문에는 분석 대신 '추천 불가 안내 + 그 종목에서 출발한 전략 설계 전환'으로 응답한다(FR-SA-006).

**FR-SA-001** 시스템은 사용자 입력을 `STRATEGY` / `STOCK_ANALYSIS` / `GENERAL` 의도로 분류해야 하며, 분류는 결정적 규칙을 우선 적용하고 모호한 경우에만 LLM으로 폴백해야 한다 (`backend/intent/classifier.py`).

**FR-SA-002** 펀더멘털 스크리닝 표현("PBR 1 이하 저평가 종목 찾아줘")은 `STOCK_ANALYSIS`가 아니라 `STRATEGY`로 분류해야 한다 (조건으로 종목을 고르는 것은 스크리닝이므로). 반대로 종목명 + 행동/판단 질문에서 전략 증거가 리스크 단어(손절/익절/트레일링)뿐이면("삼성전자 지금 손절해야 할까?") 전략 설계가 아니라 `STOCK_ANALYSIS`로 분류해야 한다 — 수정 명령·스크리닝·구성 동사·다른 전략 키워드가 함께 있으면 전략 설계 유지.

**FR-SA-002b** 특정 종목명·정량 조건 없이 매수 대상을 골라 달라는 **열린 추천 요청**("어떤 주식을 사야 하나요?", "추천 종목 있나요?", "수익 날 종목 있나요?")은 특정 종목을 추천하지 않고, 투자 아이디어를 전략으로 정의·백테스트하도록 대화를 전환하는 안내(`QueryIntent.STOCK_PICK` + `suggested_reply`)로 응답해야 한다 (규제 안전 — 유사투자자문업 회피). 결정적 감지는 입력 게이트(`intent/classifier.py`)와 코치 가드(`coach_routes._coach_scope_guard`)가 공유하며(`intent/scope.py::is_stock_pick_request`), 정량 스크리닝·전략 키워드·특정 종목명이 섞이면 가로채지 않는다.

**FR-SA-002c** 열린 추천 전환(FR-SA-002b) 직후에는 **전략 빌더 모드**로 진입해, 사용자의 짧은 답변("일단 코스피", "모멘텀", "3개월")을 역할 밖 거절 없이 전략 필드로 누적해야 한다. 전환 안내를 보낸 직후에는 사용자의 후속 입력을 기다리지 않고 곧바로 빌더의 첫 질문(시장 선택)을 능동적으로 띄워 전략 구성을 시작한다(빈 입력으로 `step`을 호출하면 상태를 바꾸지 않고 현재 질문을 반환하는 계약을 이용 — 질문·옵션 칩의 단일 출처는 백엔드 빌더). 필수 필드(유니버스 → 전략유형 → 기준기간/진입조건 → 보유 종목 수 → 리밸런싱 → 청산 조건) 우선순위 중 가장 먼저 빈 필드 하나만 질문하고, 마지막 청산 조건 단계에서는 손절·익절·트레일링 스탑·보유기간을 한 번에 받는다(청산 조건은 **필수** — 하나 이상 인식되어야 완료되며, 없으면 같은 질문을 다시 한다. 단, 사용자가 청산 조건 자체를 거부하면("없음"·"필요 없어") 같은 질문을 그대로 반복하지 않고 청산 조건이 왜 필요한지 설명하며 되묻는다). 유니버스 해석은 메인 NL 파서와 동일한 의미론을 따른다 — "코스피 전체"는 코스피 전 종목(KOSPI)이지 양시장이 아니며, 시장명 없는 "전체/모두"만 코스피·코스닥 양시장으로 해석한다. 모두 채워지면 별도 텍스트 요약 단계 없이 곧바로 검증된 한국어 프롬프트로 합성해 기존 파싱 파이프라인으로 넘긴 뒤 전략 요약 카드 + 검증 + "백테스트 실행" 버튼을 보여준다(그 버튼이 최종 확인 역할). "취소/그만"은 일반 모드로 복귀하고, "처음부터/새 전략"은 상태를 초기화한 뒤 빌더를 유지하며, "다른 질문 할게"는 일반 모드로 종료한다. 결정적 상태 머신(`intent/strategy_builder.py`)이 parser·state-transition·response-generation을 분리해 처리하고(LLM 불필요), 무상태 라우트 `POST /strategy/builder/step`로 노출한다. 빌더 모드에서는 일반 out-of-scope 거절보다 빌더 파서를 먼저 실행하며, 파싱 실패 시 거절하지 않고 같은 질문을 다시 한다. 빌더 진행 중 용어 정의 질문("손절이 뭐야?")은 필드 답변으로 오인하지 않고, 빌더가 제시하는 어휘(손절·익절·트레일링·리밸런싱·모멘텀·골든크로스·RSI·PBR 등)에 한해 짧은 객관적 정의를 답한 뒤 현재 질문을 이어간다(상태 불변, LLM 불필요, 추천·권유 없음). UI 측면에서, 빌더가 옵션 칩을 보여주는 동안에는 채팅 입력창을 숨겨 사용자가 선택에 집중하도록 한다(칩=`infoSuggestions`는 빌더 전용). 전략 유형 질문에는 가장 오른쪽에 "직접 설명하기" 칩을 두며, 선택 시 자유 서술(custom) 진입 조건 질문(칩 없음)으로 넘어가 채팅 입력창이 다시 나타나 사용자가 자신의 전략을 직접 입력할 수 있다. 청산 조건처럼 자유 서술을 인라인으로 받는 칩-only 단계에는 가장 오른쪽에 "직접 입력" 칩을 두며, 이 칩은 빌더 답변으로 전송하지 않고 채팅 입력창만 다시 띄워(프론트 토글) 사용자가 커스텀 값("15% 손절" 등)을 직접 타이핑하게 한다.

**FR-SA-002c-1** [규제 안전 — 전략 추천 금지] 구체적인 지표·전략 유형 없이 어떤 전략이 우수한지 골라 달라는 **열린 전략 추천 요청**("지금 어떤 전략이 좋을까?", "전략 추천해줘", "무슨 전략을 써야 하나요?")은 전략 우열을 판단·추천하지 않고, 함께 전략을 만들어 백테스트하는 **전략 빌더**로 대화를 전환하는 안내(`QueryIntent.STRATEGY_PICK` + `suggested_reply`)로 응답해야 한다. 전환 안내("어떤 전략이 더 좋은지 판단하거나 추천해 드리지는 않지만, 관심 있는 아이디어를 함께 전략으로 만들어 … 백테스트해 볼 수 있어요") 직후에는 STOCK_PICK(FR-SA-002b/c)과 동일하게 곧바로 빌더 모드로 진입해 첫 질문(시장 선택)을 능동적으로 띄운다. 결정적 감지(`intent/scope.py::is_strategy_pick_request`)는 '전략' 키워드가 있어 STRATEGY_ADVICE로 새기 전에 먼저 잡되, 구체적인 전략 유형·지표(모멘텀·RSI·MACD 등)나 기존 전략 지시어("이 전략"), 정량 스크리닝·수정 명령·특정 종목명이 섞이면 설계 요청이므로 가로채지 않고 일반 전략 흐름에 맡긴다.

**FR-SA-002c-2** [기능 범위 — 미제공 기능 안내] 뉴스·공시·SNS 여론처럼 플랫폼이 제공하지 않는 데이터 분석을 근거로 종목을 고르거나 전략을 만들어 달라는 요청("최근 뉴스가 좋은 종목을 사는 전략을 만들어줘", "호재 있는 종목 골라줘")은 전략 빌더로 진입하지 않고, 해당 기능을 제공하지 않는다는 안내와 함께 다른 투자 아이디어를 유도하는 응답(`QueryIntent.UNSUPPORTED_FEATURE` + `suggested_reply`)으로 답해야 한다(2026-07-12 — '전략' 키워드로 STRATEGY_ADVICE에 새서 빈 전략 파싱→빌더 자동 전환으로 이어지던 사고의 재발 방지). 결정적 감지(`intent/scope.py::is_unsupported_feature_request`)는 뉴스 단어(뉴스·공시·호재·악재·풍문·루머·기사·여론·SNS)가 종목 선정/전략의 근거로 쓰인 경우만 잡되, ① 지원 지표·재무 신호(RSI·이동평균·PBR 등)가 섞인 혼합 요청은 가로채지 않고 일반 전략 흐름에 맡기고(파서가 지원 부분을 살리고 미지원 개념 notice — `engine.nl_parser` "news" 항목 — 로 알림), ② 순수 정의형 질문("공시가 뭐야?")과 ③ 종목명(또는 anaphora)+행동 질문("삼성전자 악재 떴는데 팔까?" → FR-SA-006 종목 질문 전환)은 기존 규칙에 맡긴다. 긴 꼬리 phrasing은 LLM 폴백 분류가 `UNSUPPORTED_FEATURE`로 잡으면 동일 안내를 채운다. 프론트(`maybeRouteNonStrategyQuery`)는 이 intent에서 빌더 스텝·전략 파싱을 호출하지 않고 안내만 표시한 뒤 후속 입력을 기다린다.

**FR-SA-002c-3** [대화 맥락 기반 후속 질문 분류] "다른 예는 없어?", "더 알려줘"처럼 직전 챗봇 답변에 이어지는 **후속 질문**은 문장만 보면 투자 신호가 없어 역할 밖(OFF_TOPIC) 거절로 새면 안 된다(2026-07-12 사고 — 종목 질문 전환 안내가 전략 예시를 보여준 직후 "다른 예는 없어?"가 거절됨). 프론트(`app/analytics/new/chatHistory.ts::selectClassifierHistory`)는 분류(`/query/classify`)와 일반 답변(`/query/general`) 호출에 최근 대화 턴(기본 6턴, 로딩 자리표시자·빈 메시지 제외)을 `history`로 함께 보내고, 백엔드 LLM 폴백 분류(`intent/classifier.py::_classify_with_llm`)는 이를 `[대화 맥락]`/`[최신 입력]`으로 구분해 넘겨 직전 주제의 연속으로 분류한다(직전 주제가 투자면 OFF_TOPIC 금지, 예시·설명 추가 요청은 GENERAL_INVESTMENT). `/query/general`도 같은 맥락(`format_history_context`, 턴당 240자 절단)을 받아 직전 답변과 겹치지 않게 이어서 답한다. 결정적 규칙은 현재 입력만 본다 — 투자 맥락이 있어도 명백한 역할 밖 질문("오늘 날씨 어때?")은 여전히 거절된다.

**FR-SA-002c-4** [활성 전략 중 정의형 질문] 전략 요약이 이미 만들어진 대화에서도 용어 정의·일반 지식 질문("pbr이 뭐야?")은 전략 수정 파싱이 아니라 일반 지식 답변(`/query/general`, history 포함)으로 응답해야 한다(2026-07-17 사고 — `GENERAL_INVESTMENT` 분류가 `hasCurrentStrategy` 게이트에 막혀 수정 파싱으로 흘렀고, 바꿀 필드가 없어 무변경 전략 요약만 다시 렌더링되고 질문은 답변되지 않음). 프론트 대화 결정(`app/analytics/new/conversationDecision.ts::decideConversationTurn`)은 `GENERAL_INVESTMENT`면 활성 전략 여부와 무관하게 `answer_general`로 라우팅하고, `UNKNOWN`은 기존대로 활성 전략이 있으면 전략 입력으로 본다. 전략 카드·백테스트 준비 상태는 답변 후에도 그대로 유지된다(전략을 건드리지 않는 경로). **백엔드 2차 방어선**: 그래도 질문이 수정 파싱 경로로 흘러 인터프리터가 CLARIFY_STRATEGY(패치 없음)+질문으로 응답하면, `strategy_conversation/primary.py::run_primary_modification`은 폴백으로 질문을 버리는 대신 — 단, 결정적 fast-path(`_modify_rule_based`)가 처리할 수 있는 단순 수정은 기존대로 폴백(되묻기가 단순 수정을 가로막지 않게) — 전략을 그대로 유지한 채 질문을 기존 clarification 채널로 전달해 사용자가 무변경 요약 대신 되묻기를 받게 한다. 인터프리터가 질문 대신 `EXPLAIN_INDICATOR`나 `unsupported_features`(패치 없음)로만 보고하는 경우(2026-07-17 실측: `unsupported_features=["PBR 개념 설명 요청"]`)도 침묵 폴백하지 않고 전략을 유지하며, **정의형 질문(결정적 cue `intent.classifier.is_definition_question` — 4B 라벨이 아니라 입력 기준)이면 `/query/general`과 동일한 생성기(`api.intent_routes.generate_general_answer`)로 실제 용어 설명을 만들어 notices 채널로 답한다**(`primary_modify_explain`, 2026-07-19 — "변경하지 않았어요" 안내만 주면 질문이 답변되지 않는다는 사용자 교정). 설명 LLM 미가용이면 준비하지 못했다는 정직한 안내, 정의형 질문이 아닌 진짜 미지원 개념 요청은 미반영 안내를 준다(`primary_modify_unsupported`). 인터프리터 프롬프트(1.2)는 초안이 있어도 용어·개념 설명 질문은 MODIFY가 아니라 EXPLAIN_INDICATOR이며 unsupported_features에 넣지 않도록 계약한다.

**FR-SA-002c-5** [백테스트 설정 기본값 정확 답변] "슬리피지는 몇 %가 기본 값이지?", "현재 셋팅된 슬리피지 값은?"처럼 백테스트 설정(슬리피지·수수료·증권거래세·초기자금·체결 시점)의 기본값·현재값을 묻는 질문에는 LLM 일반답변이 값을 지어내게 두지 않고(2026-07-20 사고 — 전략 분석실이 "기본값은 0%"라고 오답) 코드의 실제 기본값으로 정확히 답해야 한다. 결정적 감지(`intent/platform_defaults.py::is_default_question` — 설정 용어+값 질문 cue, "0.1%로 설정해줘" 같은 값 변경 명령형은 제외)가 분류기 결정 규칙(전략 키워드 게이트보다 먼저)으로 `GENERAL_INVESTMENT`에 라우팅하고, `generate_general_answer`가 LLM 호출 전에 결정적 답변(`platform_defaults.reply`)을 반환한다(LLM 미가용에도 동작). 답변 값은 하드코딩하지 않고 SOT에서 읽는다 — ParsedStrategy 필드 default(수수료 0.015%·슬리피지 0.05%·초기자금 1,000만원·체결 다음 날 시가), `MIN_INITIAL_CAPITAL`(100만원 하한), 시뮬레이터 `DEFAULT_SELL_TAX_RATE`(매도 거래세 0.15%, ETF 유니버스는 0%). 수수료 질문에는 매도 거래세를 동반 안내해 총비용 오해를 막고, 설정 패널에서 변경 가능함(변경 시 그 값 적용)을 함께 알린다. 설정 용어가 언급된 개념 질문("슬리피지가 뭐야?")은 LLM이 설명하되 실제 기본값 사실 블록(`facts_block`)을 프롬프트에 주입해 값 환각을 막는다. 수정 파싱 경로로 오라우팅된 경우의 백스톱(`run_primary_modification`, FR-SA-002c-4)도 이 cue를 질문으로 인정한다.

**FR-SA-002c-6** [레드팀 검증 — 규제·안전·정확성 강화, 2026-07-20] 레드팀 QA 하니스(`scripts/qa_redteam_validation.py`, 145케이스·24유형; 리포트 `docs/qa_redteam_validation_report.md`; 회귀 `backend/tests/test_redteam_validation_fixes.py`)에서 발견한 결함들을 다음과 같이 방어해야 한다. ① [개인 맞춤형 조언 금지] 나이·자산·직업 등 개인 상황에 맞춘 전략·종목 추천 요청("40대인데 나한테 맞는 전략 뭐야?")은 LLM 일반답변으로 흘리지 않고(맞춤 조언 생성 사고 방지) 결정적 감지(`intent/scope.py::is_personal_advice_request`)로 `STRATEGY_PICK`+맞춤 추천 불가 안내로 가로챈다. `/query/general` 시스템 프롬프트도 개인 맞춤 추천을 금지한다. ② [금융 오개념 교정] 오개념을 단정·확인하는 발화("PER이 높을수록 싸다는 거지?", "무조건 사면 된대")는 파싱 경로(교정 기회 없음) 대신 지식 답변 경로(`GENERAL_INVESTMENT`, `is_misconception_assertion`)로 보내 먼저 바로잡는다(구성·수정 동사 동반 시 제외). ③ [실전 매매 미제공] 실계좌 자동매매·대리 투자 요청("자동으로 실전 매매까지 해줘", "내 돈 대신 투자해줘")은 `is_live_trading_request`로 `UNSUPPORTED_FEATURE`+가상계좌 모의투자 안내(가상/모의 언급 시 통과). ④ [해외 종목] 해외 종목 매수·매도 질문은 그 종목의 백테스트를 예시로 제안하지 않고(기능 환각 방지) 국내 시장 대상만 안내하며(`stock_question_redirect(overseas=True)`), 파싱 경로에서도 해외 개별 종목·해외 시장·우선주는 미지원 개념 안내(`_UNSUPPORTED_CONCEPT_PATTERNS`의 overseas/preferred_stock)로 조용히 드롭하지 않는다. ⑤ [기초 용어 정의 정확성] `/query/general` 답변에 PER·PBR·ROE·RSI·MACD·부채비율 등 표준 정의 사실 블록(`intent/glossary_facts.py::facts_block`)을 주입해 소형 LLM의 정의 오류를 막는다. ⑥ [지표 발음 표기] '맥디'→MACD, '알에스아이'→RSI를 분류기·파서 `_compact` 양쪽에서 정규화한다(종목·ai_model 오인 방지).

**FR-STR-023e** [설정값 상한·타당성 방어, 2026-07-20] `enforce_strategy_minimums`(FR-STR-023c의 하한 방어와 대칭)는 상한·타당성도 강제해야 한다. ① 손절/익절/트레일링/MDD 비율이 100%를 초과하면(매수 포지션 손실률 한계 -100%) 반영하지 않고 안내한다. ② 수수료·슬리피지가 상식 상한(10%)을 넘으면 기본값(0.015%/0.05%)으로 복원하고 안내한다. ③ 수수료·거래세·슬리피지보다 작은 극소 손절/익절 폭은 경고를 남긴다(무언 드롭 금지). ④ 백테스트 시작일이 데이터 가용 시점(대략 1996년) 이전이면 커버리지 안내를 남긴다(날짜는 유지, 엔진이 가용 구간부터 시작). ⑤ `max_positions`는 스키마 상한(`le=100`)을 넘는 입력("500종목")이 ValidationError로 파싱 전체를 실패시키지 않도록 `_clamp_max_positions` 검증기가 범위로 클램프한다. 모순 필터(PER ≤10 AND PER ≥20)는 검증 agent(`_validate_logical_conflicts`, `LOGICAL_CONFLICT`)가 검출한다.

**FR-STR-019f** [수정 경로 결정성·환각 방어, 2026-07-20] 완성된 전략의 수정 요청은 다음을 보장해야 한다. ① [지표 삭제] "RSI 조건 빼줘"는 언급된 지표의 진입/청산 신호만 제거하고 다른 필드(펀더멘털 필터·리스크)를 보존한다(`_extract_signal_removals` — LLM 수정이 요청과 반대로 다른 조건을 지우던 사고 방지). ② [전면 재작성] "완전 다르게 해줘"처럼 정보 없는 재작성 요청은 임의의 새 전략을 만들지 않고 방향을 되묻는다(`full_rewrite_clarification`). ③ [패치 환각 게이트] LLM 인터프리터(primary 모드)가 낸 패치 중, 발화에 해당 필드의 cue조차 없는 패치는 환각으로 거부한다(`strategy_conversation/primary.py::_patch_cue_supported` — 후속 질문 "다른 예는 없어?"에 손절·리밸런싱·날짜가 임의 주입되던 사고 방지). 전량 환각이면 전략을 유지하고 질문성 입력이면 지식 답변으로 응답한다. ④ [내부명 비노출] 미지원 안내 문구에 내부 식별자(`strategy_evaluation` 등)를 노출하지 않고 사람이 읽는 라벨로 치환한다(`_humanize_features` — 매핑된 내부명만 대상, FCF·technical.beta 등 사용자 어휘는 유지). ⑤ [LLM 수치 드리프트 교정] primary 모드의 초기·수정 파스는 결정적 추출 보정(`engine.nl_parser._apply_prompt_overrides`) 전체를 적용해 인터프리터 LLM의 수치 오귀속(예: "최근 3년"→MA 기간, "시총 100조"→100억, "PER 낮은 상위"→모멘텀 랭킹)을 결정적으로 교정한다.

**FR-SA-002d** [전략별 특화 빌더 — STATE_SPECIFIC_STRATEGY_BUILDER] 사용자가 특정 전략명(볼린저·RSI·MACD·이동평균(골든크로스)·돌파·모멘텀·거래량·스토캐스틱·CCI·가치·과매도 반등)을 이름으로 지목하면, 시드(`seed_state`→`_parse_strategy_type`)가 그 유형을 미리 채워 첫 질문에서 확인하고 일반 종목 선정 메뉴("어떤 방식으로 종목을 고를까요?")를 다시 띄우지 않는다(지목된 전략 유실 방지). 유형이 정해지면 하드코딩된 고정 순서 대신 **전략별 파라미터 스텝 레지스트리**(`STRATEGY_PARAM_STEPS`)를 구동해 그 전략의 핵심 파라미터만 묻는다 — RSI: 기간·과매도/과매수; 이동평균: SMA/EMA·단기/장기; MACD: 크로스오버/제로선; 돌파/모멘텀: 기준일; CCI: 기간·기준값; 거래량: 평균 기간; 가치: PBR/ROE. 초보자는 각 스텝에서 '기본값'으로 표준값을 채울 수 있다.

시드는 업종/섹터도 기억한다(2026-07-11) — 종목 질문 전환(FR-SA-006) 뒤 "반도체 주도주로 전략을 만들어줘"처럼 사용자가 업종을 말하면 `seed_state`가 NL 파서의 결정적 섹터 추출(`_extract_sector`, FR-STR-066)로 `BuilderState.sector`를 미리 채우고("주도주"는 모멘텀 유형으로 인식), 종목 고르는 질문을 다시 묻지 않고 빠진 필드만 질문한다. 기억한 업종은 첫 질문 도입부에서 확인되며 합성 프롬프트("코스피 반도체 업종 종목 중 …")와 직접 조립 DSL(`ParsedStrategy.sector`)까지 흐른다. 섹터는 질문으로 묻지 않는다(시드 전용).

업종/테마 언급을 결정적으로 매핑하지 못한 경우("원자로 관련주 전략을 만들자")에도 조용히 버리지 않아야 한다(2026-07-12) — 시드와 대화 중 입력 모두에서 목록 밖 업종 언급을 감지하면(`BuilderState.sector_unresolved`+원문 `sector_hint`, NL 파서의 미지원 섹터 감지 재사용) ① 먼저 **LLM 해석기**(`llm_extract_sector` — 지원 업종 전체 목록(39개)을 담은 매핑 프롬프트, 라우트가 `_llm_available()`일 때 주입)가 정본 업종으로 매핑을 시도한다('원자로'→'에너지/원자력', 'K뷰티'→'화장품/패션'). 목록은 `universe_pit.sectors_for_llm_prompt()`(단일 출처, 메인 파싱 COMPACT 프롬프트와 공유)를 쓰며, 이름만으로 분류 관례를 오해하기 쉬운 업종에는 짧은 주석을 붙인다 — '전력설비 관련주'가 이름 연상('전력→유틸리티')으로 통신/유틸리티(실제: 통신사·한전 등 사업자)에 매핑되던 사고의 재발 방지(변압기·전력설비 제조=에너지/원자력, 전선 제조=IT 하드웨어). 출력은 반드시 `normalize_sector`로 재검증하며(목록 밖 이름 지어내기 무시), 성공 시 `sector`로 반영해 확인 문장("○○ 업종 대상(으)로 이해했어요")과 요약 배지까지 관통한다(안내 없음). ② 매핑 불가(null)·LLM 미가용·예외 시에만 "말씀하신 업종/테마는 아직 지원 목록에 없어 업종 제한 없이 진행돼요 + 지원 업종 예시" 안내를 **한 번만** 표시하고(표시 후 플래그 소비, 즉시 confirmed되는 경우엔 `notices` 채널) 현재 질문을 이어간다. 사용자가 대화 중 지원 업종을 말하면("기계/장비 업종으로") `parse_input`이 캐치해 `sector`로 반영하고 확인 문장으로 응답한다. 안내 없이 전체 시장으로 백테스트되던 침묵 유실의 회귀 방지(test_seed_unsupported_sector_notice_shown_once, test_unresolved_sector_resolved_by_llm_resolver).

결정적 시드가 못 잡는 긴 꼬리 표현은 regex를 늘리지 않고 **파싱 파이프라인의 LLM 레이어가 해결한다**(2026-07-11, 하이브리드 원칙): 빈 전략으로 빌더에 전환될 때(FR-SA-002c의 빈 전략 전환) 프론트가 룰 파스→LLM 검증 교정(FR-STR-019~020)→LLM 폴백이 이미 해석한 최종 `ParsedStrategy` dump를 `BuilderStepRequest.seed_parsed`로 함께 넘기고, 빌더는 `apply_parsed_seed`로 결정적 시드가 놓친 필드를 이어받는다. 이어받는 필드는 ParsedStrategy 기본값과 사용자 언급을 구분할 수 있는 None-기본 필드(sector — 정본명 재정규화, 미지원 업종은 무시 — 와 청산 조건 손절/익절/트레일링/보유기간)로 한정하며(universe·max_positions·rebalancing_period는 기본값 오염 위험으로 제외), 결정적 시드가 이미 채운 값이 항상 우선한다. 검증 레이어 프롬프트에는 업종 제한 누락("반도체 중심으로" 등)을 sector 교정으로 채우되 사용자가 말하지 않은 업종은 지어내지 못하게 하는 규칙을 명시한다.

완성 시 **한국어 프롬프트 재파싱 왕복 없이 `build_parsed_strategy`가 `ParsedStrategy`(entry/exit `TechnicalSignal` + 랭킹/재무필터/리스크)를 직접 조립**하고 기존 `to_backtest_request`로 요청을 만든다(라우트가 confirmed 시 `parsed`+`backtest_request`+`notices`를 내려주고, 프론트는 `applyBuilderConfirmedStrategy`로 그대로 소비 — 파라미터 유실 방지). custom(자유 서술)만 DSL을 만들 수 없어 `prompt` 재파싱 경로로 폴백한다.

파라미터·신호는 **엔진(`engine/signals.py`·`_tech_signal_to_condition`)이 실제 반영하는 것만** 묻고 조립한다(답을 조용히 버리는 것 방지): 볼린저는 하단/상단 밴드 터치만(기간·표준편차·중심선 변형 미반영), 스토캐스틱은 크로스오버만(level 모드는 `TechnicalSignal.mode` literal로 표현 불가), MACD fast/slow/signal·히스토그램 미반영. **ATR는 엔진 전무이므로 빌더 유형으로 제공하지 않는다.** '볼린저'는 breakout('돌파')보다, 'RSI'는 mean_reversion(과매도 반등)보다 먼저 판정한다.

**[Tier 2 — 옵션 진입 필터]** 기술적 진입 전략(momentum·value·custom 제외)에는 핵심 파라미터 뒤 옵션 "필터" 스텝 1개를 둔다. 진입 신호와 **AND로 결합되는 게이트**를 `ParsedStrategy.entry_filters`(빌더 전용 채널)로 담아 `to_backtest_request`가 `type='filter'` 조건으로 내보내면, 엔진(`generate_signals`)이 signal 버킷과 분리해 항상 AND 결합한다. 지원 필터: ① 추세("EMA200 위에서만") — `ema` 평가자에 지속 상태 `mode='above'/'below'` 신설(크로스오버가 아니라 매 봉 close vs EMA 판정), ② 거래대금(유동성) — 기존 `trading_value`(≥ N억) 재사용, ③ RSI 결합("RSI 30 이하일 때만") — 기존 `rsi` compare 재사용. "없음"·무매치도 옵션이라 완료 처리하며, 자유 입력으로 복수 필터 동시 지정 가능. `entry_filters`는 canonical DSL 해시에 포함해 필터만 다른 전략의 캐시 충돌을 막는다. 원시 "평균 거래량 이상" 전용 평가자는 미구현(거래대금 유동성 필터로 대체).

**FR-SA-003 / FR-SA-004 / FR-SA-005** [제거됨 2026-07-10] 개별 종목 분석 파이프라인(종목 해석→parquet 분석→객관적 상태 등급→LLM 설명, `/stock/analyze`·`StockAnalysisPanel`)은 삭제됐다. 종목명 해석(`symbol_resolver`·`stock_master`)은 의도 분류용으로, `guardrails`(금지 표현 필터)는 `/query/general`용으로, `news_service`는 advisor 뉴스 보강용으로 유지된다.

**FR-SA-006** [규제 안전 — 유사투자자문업 회피] 특정 종목명 + 매수·매도·보유·전망 질문(`STOCK_ANALYSIS` 의도)에는 분석·판단·추천을 제공하지 않고, 다음을 담은 전환 안내(`suggested_reply`, `intent/scope.py::stock_question_redirect`)로 응답해야 한다: ① 매수·매도 판단과 종목 추천을 제공하지 않는다는 명시, ② 언급된 종목에서 출발한 **전략 설계 예시**로의 유도. 예시는 엔진이 실제 실행할 수 있는 개념만 사용해야 한다. 언급 종목의 섹터를 알면(예: 삼성전자→반도체) '그 종목이 속한 업종 종목만 대상으로 최근 3개월 수익률 상위 5종목 매수' 전략을 첫 예시로 쓴다(FR-STR-066 섹터 유니버스 지원). 섹터를 모르면 종목의 시장에 맞춘 예시를 쓴다(KOSPI→코스피200 대형주 모멘텀, KOSDAQ→코스닥 모멘텀). 공통 예시: 저평가 우량주 가치 스크리닝, RSI 과매도 반등. 예시 문구는 실제로 파싱·실행 가능해야 한다(회귀: test_stock_question_redirect_sector_example_is_parseable). 안내 문구 자체가 행동 지시 표현(`guardrails._FORBIDDEN`)을 포함해서는 안 된다. 프론트는 전환 안내 후 **전략 빌더 모드로 자동 진입하지 않고 사용자의 후속 답변을 기다린다**(2026-07-11) — 안내가 이미 그 종목 기반의 구체적 전략 예시를 제시하므로 빌더의 첫 질문("어떤 시장을 대상으로 할까요?")이 예시를 덮으면 안 된다(STOCK_PICK의 즉시 빌더 진입과 의도적으로 다름, 회귀: page.stock-redirect.test.tsx). 사용자가 예시를 골라 답하면 일반 전략 파싱 흐름이 처리한다. 이미 전략을 작성 중이면 안내만 표시하고 기존 전략을 유지한다.

---

### 3.7 시장 데이터 및 분석

#### 3.7.1 시장 지수

**FR-MKT-001** KOSPI, KOSDAQ 실시간 지수를 표시해야 한다 (현재값, 등락률, 거래량).

#### 3.7.2 종목 상세

**FR-MKT-010** 종목 상세 페이지는 다음을 포함해야 한다:
- 가격 차트 (일봉/주봉/월봉)
- 기본 정보 (시총, PER, PBR, ROE, 부채비율)
- 재무 요약 (매출, 영업이익, 당기순이익 추이)
- 거래량 차트

#### 3.7.3 종목 검색

**FR-MKT-020** 사용자는 종목명 또는 종목코드로 검색할 수 있어야 한다.

**FR-MKT-021** 검색 결과는 자동완성 형태로 실시간 표시되어야 한다.

---

### 3.8 사용자 관리

**FR-USR-001** 사용자는 이메일과 비밀번호로 회원가입 및 로그인할 수 있어야 한다.



**FR-USR-002** 비밀번호는 bcrypt 등의 알고리즘으로 해시하여 저장해야 한다.

**FR-USR-003** 사용자 세션은 JWT 또는 세션 쿠키로 관리되어야 한다.

**FR-USR-004** 정지(SUSPENDED)·삭제(DELETED) 상태의 계정은 로그인이 거부(403)되어야 하며, 이미 발급된 유효 토큰으로도 세션이 인정되지 않아야 한다(`getCurrentUser`가 null 반환). 로그인 성공 시 `lastLoginAt`을 기록한다.

**FR-USR-005** 사용자는 프로필 메뉴의 설정 모달(사이드바: 계정/결제/사용량 탭, 검색 필터)에서 본인
계정을 직접 삭제할 수 있어야 한다(`DELETE /api/user/account`, soft delete — `status=DELETED`).
자동갱신 구독이 활성 상태이면 삭제를 거부하고 먼저 구독 취소를 안내해야 하며, 삭제 시 빌링
상태(빌링키·다음 결제일·해지 예약 등)를 모두 초기화해 이후 자동 청구가 발생하지 않아야 한다. 삭제
성공 시 즉시 로그아웃 처리한다. 결제 탭에서는 현재 요금제와 다음 갱신/만료일, 청구서
목록(`GET /api/payment/orders` — 본인 주문만, 승인 전 이탈(PENDING) 주문 제외)을 표시하고 자동갱신
해지(요금제 취소, `POST /api/payment/billing/cancel` 재사용)를 제공한다. 사용량 탭은 계좌/전략/월
백테스트 사용량과 리셋 카운트다운을 표시한다.

### 3.9 관리자 콘솔 (Admin Console)

**FR-ADM-001** 관리자 콘솔은 `/console` 단일 URL 하나만 존재해야 하며(하위 페이지 없음), 내부 탭(Overview/Users/Backtests/Virtual Accounts/Strategies/Plans/Audit Logs) 전환으로 모든 기능을 제공해야 한다.

**FR-ADM-002** 모든 관리자 페이지·API는 서버에서 `requireAdmin()`(JWT + `User.role='ADMIN'` + `status='ACTIVE'`)으로 권한을 검증해야 한다. 검증 실패 시 404를 반환해 콘솔의 존재 자체를 숨긴다. UI 숨김만으로는 보안으로 인정하지 않는다.

**FR-ADM-003** ADMIN 권한은 관리자 화면/API로 부여·변경할 수 없어야 하며, 초기에는 데이터베이스에서만 변경한다.

**FR-ADM-004** 관리자의 모든 변경 작업은 `AdminAuditLog`에 관리자·시간·대상·작업 종류·변경 전/후 값·IP를 기록해야 하며, 감사 로그 삭제 기능은 제공하지 않는다.

**FR-ADM-005** 관리자는 사용자 관리(플랜 변경·정지·활성화·삭제(soft)·백테스트 사용량 조정), 가상계좌 관리(일시 중지·재개·초기화·삭제), 전략 관리(비활성화·삭제(soft)), 플랜 한도 오버라이드(`PlanConfig` — 월 백테스트/전략 수/가상계좌 수, null=기본값 복원, 전략 -1=무제한)를 수행할 수 있어야 한다. 자기 자신에 대한 정지·삭제는 차단된다.

**FR-ADM-006** 관리자 화면·API 응답에는 비밀번호, OAuth/Access/Refresh Token, Secret Key, API Key 등 민감 정보를 포함하지 않아야 한다.

---

## 4. 비기능 요구사항

### 4.1 성능

| ID | 요구사항 |
|----|---------|
| NFR-PERF-001 | 백테스트 실행 시간: 1년치 데이터 기준 단일 종목 1초 이내, 100 종목 포트폴리오 30초 이내 |
| NFR-PERF-002 | SSE 스트림 첫 진행률 이벤트: 백테스트 시작 후 2초 이내 |
| NFR-PERF-003 | 페이지 초기 로드: LCP 3초 이내 (Next.js SSR/SSG 활용) |
| NFR-PERF-004 | 가상 시장 시세 갱신: 30초 이내 |
| NFR-PERF-005 | SignalEngine 벡터화: 전체 시계열을 단일 Polars 연산으로 처리 (루프 없음) |
| NFR-PERF-006 | 배치 실행 worker는 시스템 자원 고갈을 막기 위해 concurrency 제한을 지원해야 한다 |
| NFR-PERF-007 | 자연어 전략 생성 first response는 `/api/strategy/parse/stream` 기준 100~300ms를 목표로 한다 |
| NFR-PERF-008 | parse, coach, summary는 하나의 blocking pipeline으로 묶지 않고 parse를 먼저 완료한 뒤 coach/summary를 지연 실행해야 한다 |
| NFR-PERF-009 | 로컬 MLX 추론은 priority lock을 사용해 parse(0), coach(1), summary/preload(2) 순서로 latency-sensitive 작업을 보호해야 한다 |
| NFR-PERF-010 | AI 요약 API는 동일 `metrics + strategySummary` payload에 대해 LRU cache 및 in-flight dedupe를 적용해야 한다 |
| NFR-PERF-011 | 종목 뉴스탭 API는 캐시 조회만 수행해야 하며, 정상 캐시 hit 기준 300ms 이하 응답을 목표로 해야 한다 |
| NFR-PERF-012 | `stock_news_cache`는 `symbol + published_at` 기준 index를 가져야 한다 |
| NFR-PERF-013 | 뉴스 수집/분석/LLM 실행 시간은 뉴스탭 API 응답 시간에 포함되면 안 된다 |
| NFR-PERF-014 | 뉴스 수집 priority engine은 3,000개 이상 종목에서도 동작해야 하며, 사용자 관심 종목에 수집 리소스를 집중해 외부 API 비용을 줄여야 한다 |

### 4.2 신뢰성

| ID | 요구사항 |
|----|---------|
| NFR-REL-001 | 백테스트 엔진은 개별 종목 오류 발생 시 해당 종목을 건너뛰고 전체 실행을 지속해야 한다 |
| NFR-REL-002 | 가상 시장 데이터 소스 장애 시 다음 우선순위 소스로 자동 폴백해야 한다 |
| NFR-REL-003 | DB 트랜잭션 실패 시 롤백 처리해야 한다 |
| NFR-REL-004 | 배치 실행 상태는 `BatchRun`/`BatchRunCandidate`에 체크포인트 저장되어야 한다 |
| NFR-REL-005 | 서버 재시작 후 다음 `batch-runs` 요청이 들어오면 incomplete batch를 복구해 재개할 수 있어야 한다 |
| NFR-REL-006 | LLM JSON 출력이 불완전하거나 schema parsing에 실패해도 자연어 전략 생성 API는 가능한 fallback 결과 또는 사용자 안내 가능한 오류를 반환해야 한다 |
| NFR-REL-007 | 외부 뉴스 수집 실패 시 기존 `stock_news_cache`를 유지해야 한다 |
| NFR-REL-008 | news agent 분석 실패 시 raw news 기반 fallback cache를 제공하고 실패 내용을 로그와 retry queue에 기록해야 한다 |
| NFR-REL-009 | 백엔드 startup worker autostart는 pid lock file과 broker active queue inspect로 중복 worker 생성을 방지해야 한다 |

### 4.2a 관측성

| ID | 요구사항 |
|----|---------|
| NFR-OBS-001 | 시스템은 AI runtime phase별 `elapsed_ms`, `queue_wait_ms`, `status`를 in-memory로 기록해야 한다 |
| NFR-OBS-002 | 시스템은 개발/운영 진단을 위해 AI runtime metrics 조회 API를 제공해야 한다 |
| NFR-OBS-003 | AI runtime metrics reset API는 production 환경에서 비활성화되어야 한다 |

### 4.3 유지보수성

| ID | 요구사항 |
|----|---------|
| NFR-MNT-001 | 백엔드 테스트 커버리지: pytest 기준 핵심 엔진 모듈 80% 이상 |
| NFR-MNT-002 | 프론트엔드 테스트: Vitest 기반 주요 컴포넌트 단위 테스트 |
| NFR-MNT-003 | 새 시그널 조건 추가 시 엔진 평가(`backend/engine/signals.py`)와 DSL 타입(`types/strategy.ts`) 정의만 수정하면 되는 구조 유지 |

### 4.4 보안

| ID | 요구사항 |
|----|---------|
| NFR-SEC-001 | API 키 등 민감 정보는 `.env` 파일로 관리하며 소스코드에 하드코딩 금지 |
| NFR-SEC-002 | 사용자 입력(자연어 전략 프롬프트 포함)은 서버 전달 전 길이 제한(최대 2,000자) 적용 |
| NFR-SEC-003 | SQL Injection 방지: Prisma ORM의 파라미터화된 쿼리 사용 |
| NFR-SEC-004 | 외부 URL을 fetch하는 API는 SSRF 방어를 위해 scheme, hostname, DNS 해석 IP, redirect target을 검증해야 한다 |
| NFR-SEC-005 | 뉴스 본문 fetch API는 private/loopback/link-local/non-global IP와 localhost를 직접 또는 redirect 경유로 호출하면 안 된다 |

### 4.5 확장성

| ID | 요구사항 |
|----|---------|
| NFR-EXT-001 | 데이터 소스(종목 데이터 제공자)를 Provider 인터페이스로 추상화하여 신규 소스 추가 용이 |
| NFR-EXT-002 | 전략 DSL 구조는 글로벌 시장(NASDAQ 등) 확장을 고려한 `universe` 타입 확장 지원 |

---

## 5. 데이터베이스 설계

### 5.1 ERD 개요

```
User ─────────────────────────────────────── (계정)
Strategy ──── BacktestResult ──── Stock        (전략·백테스트)
Strategy ──── BacktestHistory                 (전략 캐시/이력)
Strategy ──── BacktestRun                     (strategy_id 단위 백테스트 실행 캐시)
Strategy ──── StrategyEmbedding               (RAG 검색 문서/임베딩)
Strategy ──── AdviceExperience                (조언 경험 메모리)
BatchRun ──── BatchRunCandidate ──── Strategy (배치 실행)
Strategy ──── VirtualAccount                   (전략-가상계좌 연결)
VirtualAccount ──── VirtualPosition            (가상 포지션)
VirtualAccount ──── VirtualOrder               (가상 주문)
VirtualAccount ──── VirtualMarketState         (가상 시장 상태)
VirtualAccount ──── DelistingAuditLog          (상장폐지 감사 로그)
VirtualMarketLog                               (시장 갱신 로그)
Stock                                          (상장 상태 + listingStatus 필드)
WatchlistGroup ──── WatchlistSymbol            (관심종목)
BacktestHistory                                (백테스트 이력)
```

### 5.2 스키마 정의

#### User
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | Int PK | 자동 증가 |
| email | String UNIQUE | 이메일 (로그인 ID) |
| name | String | 사용자 이름 |
| password | String | bcrypt 해시 |
| createdAt | DateTime | 가입일 |
| updatedAt | DateTime | 수정일 |

#### Strategy
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | String PK | `strategy_id = SHA-256(canonical_strategy_dsl)` |
| name | String | 전략명 |
| description | String? | 전략 설명 |
| settings | String | JSON (StrategyDSL 직렬화) |
| strategyType | String | 전략 유형 (기본값: "기타") |
| createdAt | DateTime | 생성일 |
| updatedAt | DateTime | 수정일 |

#### BacktestResult
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | String PK | CUID |
| strategyId | String FK | Strategy.id |
| stockId | Int? FK | Stock.id (null = 전략 전체 결과) |
| summary | String | JSON (메트릭 전체) |
| trades | String? | JSON (거래 내역) |
| createdAt | DateTime | 생성일 |

#### BacktestHistory
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | String PK | CUID |
| strategyId | String? FK | Strategy.id |
| strategyName | String | 전략명 |
| universe | String | 유니버스 |
| conditions | String | JSON (조건 요약) |
| metrics | String | JSON (핵심 메트릭) |
| result | String? | JSON (전체 결과 스냅샷) |
| cacheKey | String? UNIQUE | 캐시 조회 키 |
| isVisible | Boolean | 사용자 노출 여부 |
| hitCount | Int | cache hit 누적 수 |
| createdAt | DateTime | 실행일 |

#### BacktestRun
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | String PK | 실행 ID |
| strategyId | String FK | Strategy.id |
| strategyHash | String | canonical DSL SHA-256 |
| canonicalDsl | String | canonical Strategy DSL JSON |
| request | String | JSON 백테스트 요청 |
| result | String | JSON 백테스트 결과 |
| metrics | String | JSON 핵심 성과 지표 |
| market | String? | 시장 구분 |
| universe | String? | 종목 유니버스 |
| initialCapital | Float? | 초기자금 |
| timeframe | String? | 봉 주기 |
| costModel | String? | 수수료/슬리피지 JSON |
| createdAt | DateTime | 생성일 |
| updatedAt | DateTime | 수정일 |

#### StrategyEmbedding
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | String PK | 임베딩 레코드 ID |
| strategyId | String FK | Strategy.id |
| embeddingModel | String | 임베딩 모델명 또는 검색 방식 |
| embeddingVector | String? | JSON/Text 벡터 저장값 |
| textDocument | String | 텍스트 검색 문서 |
| structureDocument | String | DSL 구조 검색 문서 |
| createdAt | DateTime | 생성일 |

#### AdviceExperience
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | String PK | 경험 메모리 ID |
| strategyId | String FK | Strategy.id |
| market | String? | KOSPI/KOSDAQ/US/Crypto 등 |
| universe | String? | 선택 유니버스 |
| initialCapital | Float | 초기자금 |
| timeframe | String | 봉 주기 |
| userPrompt | String | 원본 사용자 전략 프롬프트 |
| strategySummary | String? | 전략 요약 |
| strategyDsl | String | JSON Strategy DSL |
| canonicalDsl | String | canonical DSL string |
| strategyHash | String | SHA-256 strategy hash |
| similarStrategyIds | String | JSON 유사 전략 ID 배열 |
| retrievedCases | String | JSON RAG 검색 사례 |
| agentAdvice | String | JSON 조언 요약/변경/경고/가정 |
| beforeBacktest | String | JSON 조언 전 백테스트 지표 |
| afterBacktest | String? | JSON 조언 후 백테스트 지표 |
| evaluation | String | JSON 성공 여부, 개선/악화 지표, overfitting risk |
| lesson | String | 재사용 가능한 교훈 |
| confidence | String | low / medium / high |
| dataCoverage | String? | 데이터 부족/충분 상태 |
| createdAt | DateTime | 생성일 |

#### BatchRun
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | String PK | run_id |
| createdAt | DateTime | 실행 생성 시각 |
| totalPrompts | Int | 입력 프롬프트 수 |
| completedCount | Int | 성공 완료 수 (`computed` + `cache_hit`) |
| failedCount | Int | 실패 수 |
| skippedCount | Int | 스킵 수 |
| rankingSnapshot | String | JSON leaderboard 스냅샷 |
| logs | String? | JSON 로그 배열 |

#### BatchRunCandidate
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | String PK | 후보 레코드 ID |
| runId | String FK | BatchRun.id |
| strategyId | String? FK | Strategy.id |
| prompt | String | 원본 프롬프트 |
| strategyName | String | 생성된 전략 이름 |
| status | String | waiting / running / computed / cache_hit / failed / skipped |
| errorMessage | String? | 실패 원인 |
| metrics | String? | JSON 메트릭 |
| rank | Int? | 최종 leaderboard 순위 |
| createdAt | DateTime | 생성 시각 |

#### Stock (상장 상태 관련 필드)
| 컬럼 | 타입 | 설명 |
|------|------|------|
| listingStatus | String | 상장 상태 (기본값: `NORMAL`) |
| suspensionReason | String? | 거래정지/상폐 사유 |
| delistingDate | String? | 상장폐지 예정일 |
| lastTradableDate | String? | 마지막 거래 가능일 |
| riskFlags | String? | JSON 리스크 플래그 배열 |
| statusUpdatedAt | DateTime? | 상태 마지막 갱신 시각 |

> `@@index([listingStatus])` — 상태별 종목 조회 최적화

#### DelistingAuditLog
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | String PK | CUID |
| accountId | String FK | VirtualAccount.id |
| symbol | String | 종목 코드 |
| actionType | String | AUTO_LIQUIDATE / TRADE_BLOCKED / STATUS_CHANGE / FORCED_HOLD |
| previousStatus | String? | 이전 상태 |
| newStatus | String? | 새 상태 |
| quantity | Int? | 처리 수량 |
| executionPrice | Float? | 체결 가격 |
| reason | String? | 처리 사유 |
| createdAt | DateTime | 기록 시각 |

#### VirtualAccount
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | String PK | |
| userId | Int? FK | User.id |
| name | String | 계좌명 |
| initialCash | Float | 초기 투자금 |
| currentCash | Float | 현재 잔고 |
| status | String | ACTIVE / CLOSED |
| strategyId | String? | 연결된 전략 ID |
| strategyName | String? | 연결된 전략명 |
| tradingMode | String | manual / auto / signal |
| delistingPolicy | String | AUTO_LIQUIDATE / HOLD_AS_WORTHLESS / HOLD_WITH_MANUAL_REVIEW (기본값: AUTO_LIQUIDATE) |
| closedAt | DateTime? | 정산 완료 시각 |
| createdAt | DateTime | |
| updatedAt | DateTime | |

#### UserAsset
| 컬럼 | 타입 | 설명 |
|------|------|------|
| userId | Int PK/FK | User.id |
| availableCash | Decimal | 가상계좌에 아직 배정하지 않은 사용 가능 자산 |
| initialGrantAmount | Decimal | 최초 지급 가상 자산 |
| createdAt | DateTime | 생성 시각 |
| updatedAt | DateTime | 갱신 시각 |

#### AssetLedger
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | String PK | CUID |
| userId | Int FK | User.id |
| accountId | String? FK | VirtualAccount.id |
| type | String | INITIAL_GRANT / ACCOUNT_ALLOCATION / ACCOUNT_LIQUIDATION_RETURN / BUY / SELL / FORCE_SELL |
| amount | Decimal | 자산 이동 금액. 배정 차감은 음수, 반환/지급은 양수 |
| balanceAfter | Decimal | 거래 후 사용자 availableCash |
| createdAt | DateTime | 기록 시각 |

#### VirtualMarketState
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | String PK | |
| accountId | String UNIQUE FK | VirtualAccount.id |
| startDate | String | 가상매매 시작일 |
| status | String | running / stopped / paused |
| symbols | String | JSON 배열 — 추적 종목 코드 목록 (전략 수익률 상위 10개) |
| lastRefreshed | String? | 마지막 갱신 시각 |
| createdAt | DateTime | |
| updatedAt | DateTime | |

> **symbols 선정 규칙:** 연결 전략의 최신 `BacktestResult`에서 종목별 수익률 기준 상위 10개 자동 선정. 전략 미연결 시 사용자가 수동 입력.

#### VirtualPosition
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | String PK | |
| accountId | String FK | VirtualAccount.id |
| symbol | String | 종목코드 |
| name | String | 종목명 |
| quantity | Int | 보유 수량 |
| avgPrice | Float | 평균 매수가 |
| currentPrice | Float? | 현재가 |
| peakPrice | Float? | 최고가 (트레일링 스탑용) |
| openedAt | DateTime | 매수 시각 |
| updatedAt | DateTime | |
| (unique) | accountId + symbol | |

#### VirtualOrder
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | String PK | |
| accountId | String FK | VirtualAccount.id |
| symbol | String | 종목코드 |
| name | String? | 종목명 |
| side | String | BUY / SELL |
| type | String | MARKET / LIMIT |
| quantity | Int | 수량 |
| price | Float | 주문 가격 |
| filledPrice | Float? | 체결 가격 |
| status | String | PENDING / FILLED / CANCELLED |
| avgBuyPrice | Float? | 평균 매수가 (매도 시) |
| fee | Float? | 수수료 |
| tax | Float? | 거래세 |
| realizedPnl | Float? | 실현 손익 |
| filledAt | DateTime? | 체결 시각 |
| createdAt | DateTime | |

#### VirtualMarketLog
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | String PK | |
| accountId | String | 계좌 ID |
| date | String | 날짜 (YYYY-MM-DD) |
| symbol | String | 종목코드 |
| signalType | String | entry / exit / risk_sl / risk_tp / risk_ts |
| reason | String? | 시그널 이유 설명 |
| price | Float | 당시 가격 |
| action | String | BUY / SELL / HOLD / SKIP |
| orderId | String? | 생성된 주문 ID |
| createdAt | DateTime | |

#### Stock
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | Int PK | 자동 증가 |
| symbol | String UNIQUE | 종목코드 (예: "005930") |
| name | String? | 종목명 |
| market | String? | KOSPI / KOSDAQ / NASDAQ |
| updatedAt | DateTime | |

#### WatchlistGroup / WatchlistSymbol
| WatchlistGroup 컬럼 | 타입 | 설명 |
|---------------------|------|------|
| id | String PK | |
| name | String | 그룹명 |
| color | String | 그룹 색상 (기본 #3B82F6) |
| createdAt | DateTime | |

| WatchlistSymbol 컬럼 | 타입 | 설명 |
|----------------------|------|------|
| id | String PK | |
| symbol | String UNIQUE | 종목코드 |
| name | String | 종목명 |
| addedAt | DateTime | 추가일 |
| groupId | String? FK | WatchlistGroup.id |

---

## 6. API 명세

### 6.1 FastAPI 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/backtest` | 백테스트 실행 (일반) |
| POST | `/backtest-stream` | 백테스트 실행 (SSE 스트림) |
| POST | `/strategy/parse` | 자연어 전략 파싱 (NLParser) |
| POST | `/advisor/review` | RAG + Experience Memory 전략 리뷰/개선 조언 |
| GET | `/news/fetch-body` | 기사 본문 일부 추출 (SSRF 방어 적용) |
| GET | `/v2/news/{symbol}` | 종목 뉴스탭 캐시 조회. 수집/분석을 실행하지 않고 cache only로 응답 |
| POST | `/v2/news/events` | 종목 조회/검색/관심/보유 등 뉴스 priority event 기록 |
| GET | `/v2/news/priority` | 종목별 priority score와 Hot/Warm/Cold queue 상태 조회 |
| GET | `/ai/runtime/metrics` | AI 런타임 latency 메트릭 조회 |
| POST | `/ai/runtime/metrics/reset` | AI 런타임 메트릭 초기화 |
| GET | `/market/listing-status` | 전체 상장 상태 조회 (DART + DelistedSymbolStore + DB) |
| POST | `/market/listing-status/sync` | 수동 상장 상태 동기화 트리거 |
| POST | `/virtual-account/{account_id}/force-liquidate/{symbol}` | 강제청산 실행 |
| GET | `/health` | 서버 헬스체크 |

### 6.2 Next.js API Routes

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET/POST | `/api/strategy` | 전략 목록 조회 / 저장 |
| GET/PUT/DELETE | `/api/strategy/[id]` | 전략 상세 조회 / 수정 / 삭제 |
| POST | `/api/strategy/parse` | 자연어 전략 파싱 프록시 |
| POST | `/api/strategy/parse/stream` | 자연어 전략 파싱 SSE 프록시 (`accepted`, `skeleton`, `parsed_final`, `dsl_ready`) |
| POST | `/api/strategy/backtest-stream` | 단일 전략 백테스트 실행 (SSE) |
| POST | `/api/strategy/save-with-backtest` | 전략 저장 + 백테스트 결과 함께 저장 |
| GET/POST | `/api/strategy/batch-runs` | 배치 실행 시작 / 최근 이력 조회 / 상세 조회 / 취소 |
| POST | `/api/strategy/coach` | AI 전략 코치 응답 생성 (단건) |
| POST | `/api/strategy/coach/stream` | AI 전략 코치 SSE 스트리밍 |
| POST | `/api/advisor/review` | RAG + Experience Memory 전략 리뷰/개선 조언 프록시 |
| GET | `/api/ai/runtime/metrics` | AI 런타임 latency 메트릭 조회 프록시 |
| POST | `/api/ai/runtime/metrics/reset` | AI 런타임 메트릭 초기화 프록시(production 비활성화) |
| GET | `/api/user/assets` | 내 사용 가능 자산, 활성 계좌 평가금액 합계, 총 자산, 활성 계좌 목록 조회 |
| GET | `/api/user/assets/ledger` | 내 자산 이동 내역 조회 |
| GET/POST | `/api/virtual-account` | 가상계좌 목록 조회 / 생성 |
| GET/PUT/DELETE | `/api/virtual-account/[id]` | 가상계좌 상세 / 수정 / 정산 후 CLOSED 처리 |
| GET/POST | `/api/virtual-market/[accountId]` | 가상 시장 상태 조회 / 시작 |
| POST | `/api/virtual-market/[accountId]/refresh` | 가상 시장 수동 갱신 |
| GET | `/api/dashboard/strategy-list` | 대시보드용 전략 목록 |
| GET/POST | `/api/watchlist` | 관심종목 조회 / 추가 |
| DELETE | `/api/watchlist/[id]` | 관심종목 삭제 |
| GET | `/api/news/symbol/[symbol]` | 종목별 뉴스 목록 (page, page_size, as_of) |
| GET | `/api/news/impact/[symbol]` | 종목 Alpha 시그널 (latest_alpha, risk_alert_level) |
| GET | `/api/news/top` | 주요 시장 뉴스 피드 |
| GET | `/api/news/fetch-body` | 기사 본문 일부 추출 프록시 (SSRF 방어 적용) |
| GET | `/api/stocks/[symbol]/news` | 종목 상세 뉴스탭용 캐시 전용 뉴스 목록 (`limit`, stale 상태 포함) |
| GET | `/api/market/delisting-status` | 통합 상장 상태 조회 (backend + DB, 5개 배열 + details) |
| POST | `/api/virtual-account/[id]/liquidate` | 강제청산 프록시 |

---

## 7. 인터페이스 요구사항

### 7.1 페이지 구조

| 경로 | 페이지 | 설명 |
|------|--------|------|
| `/` | 홈 대시보드 | 전략/백테스트/가상계좌 허브 |
| `/analytics` | Strategy Lab | 전략 분석 및 비교 |
| `/analytics/new` | 새 전략 | 자연어 프롬프트 전략 생성 + `모두 테스트` 배치 실행 |
| `/analytics/[id]` | 전략 상세 | 백테스트 결과 및 수정 |
| `/virtual-account/[id]` | 가상계좌 상세 | 포지션, 주문, 가상매매 |
| `/kospi` | 시장 현황 | KOSPI/KOSDAQ 지수, 종목 |
| `/stock-order` | 종목 거래 | 5탭 구조: 차트·호가 / 종목정보 / 뉴스·공시(NewsImpactPanel) / 거래현황 / 커뮤니티 |
| `/watchlist` | 관심종목 | 관심종목 목록 관리 |

### 7.2 디자인 시스템

**색상 팔레트 (Nature Palette)**

| 역할 | 색상명 | HEX |
|------|--------|-----|
| 주요 강조 (수익, 매수) | Iguana Green | `#73B682` |
| 보조 강조 (정보, 차트) | Blue-Gray | `#62A8CB` |
| 경고 (알림, 주의) | Deep Saffron | `#FF9933` |
| 배경 다크 | Dark Slate Gray | `#2A4954` |
| 베이스 배경 | Raisin Black | `#272626` |

**공통 컴포넌트**
- TopMenuBar: 전역에서 한 번 렌더링되는 상단 앱 셸
- TopNavigation: 전략연구소, 가상계좌, 백테스트, 대시보드 상단 네비게이션
- OrderAccountContext: 주문 페이지에서 공유하는 선택 계좌 상태
- BacktestDashboard: 백테스트 결과 시각화 전용 컴포넌트
- RunAllTestsModal: 독립형 배치 백테스트 실행 및 leaderboard/로그 표시 모달

---

## 8. 제약 사항

### 8.1 기술 제약

| 항목 | 제약 |
|------|------|
| 데이터베이스 | SQLite (단일 사용자/소규모 — 멀티유저 확장 시 PostgreSQL 마이그레이션 고려) |
| OHLCV 데이터 | 로컬 Parquet 파일 기반 (4,052 종목) — 실시간 데이터는 외부 API 의존 |
| AI 모델 | 로컬 추론 (Apple Silicon MLX / GPU 없이 느릴 수 있음) |
| LLM 파싱 | 로컬 LLM 필요 (MLX 또는 Ollama 설치 요구) |

### 8.2 법적/규제 제약

| 항목 | 내용 |
|------|------|
| 면책 | 모의 투자 전용 서비스. 실제 투자 조언 또는 금융 서비스 미해당 |
| 데이터 이용 | KRX, Naver Finance 등 외부 API 이용 약관 준수 필요 |
| 실시간 데이터 | 상용 서비스 제공 시 KIS API 계약 및 데이터 라이선스 검토 필요 |
| 이용약관 | `docs/architecture/terms-of-service.md`의 약관 초안을 기준으로 서비스 범위, 청약철회, 환불, 면책, 분쟁 처리, 개인정보처리방침 분리 고지를 운영 전 확정해야 함 |

#### 이용약관 요구사항

- 이용약관은 약관 게시와 개정 고지, 회원/계정(만 14세 미만 가입 제한), 서비스 범위, 가상계좌, AI 분석 기능 고지, 플랜 및 이용 한도, 유료서비스(정기결제 자동 갱신·해지 포함), 청약철회와 환불, 금지행위, 책임 제한, 손해배상, 분쟁 해결, 준거법 조항을 포함해야 한다.
- 약관은 널스페이스가 제공하는 nullStock이 투자 연구 및 시뮬레이션 플랫폼이라는 점을 명시하고, 자본시장법상 금융투자업(투자자문업·투자일임업·투자매매업·투자중개업) 및 유사투자자문업을 영위하지 않으며 유료서비스의 대가가 소프트웨어 이용 대가일 뿐 투자조언 대가가 아니라는 고지, 개인 맞춤형 금융 조언 미제공 고지를 포함해야 한다.
- 약관은 AI 분석 기능의 산출물이 과거 데이터·통계 모델 기반 참고용 정보이며 오류가 포함될 수 있고 투자 추천이 아니라는 고지를 포함해야 한다.
- 약관의 핵심 용어 정의는 `"전략"=이용자가 직접 입력하거나 구성한 조건, 지표, 필터, 리스크 설정의 조합`, `"백테스트"=이용자가 입력한 전략을 과거 데이터 기준으로 계산하는 시뮬레이션 기능`, `"가상계좌"=실제 금전, 주문, 체결, 예탁 또는 출금 없이 모의 거래 기록을 관리하는 기능`으로 일관되게 유지해야 한다.
- 개인정보 처리 목적, 보유 기간, 제3자 제공, 처리 위탁, 이용자 권리 행사, 개인정보 보호책임자는 이용약관이 아니라 별도 개인정보처리방침에서 고지해야 한다.

#### 개인정보처리방침 요구사항

- 개인정보처리방침은 개인정보 보호법 제30조의 필수 기재사항(처리 목적, 항목, 보유 기간, 파기, 정보주체 권리, 안전성 확보 조치, 보호책임자, 권익침해 구제 방법)을 포함해야 한다. 초안은 `docs/architecture/privacy-policy.md`, 배포본은 `components/landing/PrivacyPolicyPage.tsx`로 동일하게 유지한다.
- 수집 항목은 실제 구현과 일치해야 한다: 회원가입·로그인은 Supabase Google OAuth 단일 경로이며 회사는 이용자의 비밀번호를 직접 수집·저장하지 않는다(이메일/비밀번호 라우트는 UI 미연결 고아 코드로 라이브 미사용). AI 분석 기능에 입력한 대화 메시지도 수집 항목에 포함한다.
- 방침은 실제로 구현하지 않은 처리·기능을 서술하면 안 된다. 2026-07-08 감사에서 미구현으로 제거한 항목: 일반 이용자 IP·브라우저/기기 정보 수집, 문의 내용·답변 이력·공지 수신 여부, 접속 로그 3개월 보관, 쿠키 기반 이용 통계 산출, "서비스 내 계정 기능"을 통한 회원 탈퇴. 해당 기능을 구현하면 방침에 다시 반영해야 한다(대응표는 `docs/architecture/privacy-policy.md` 참조).
- AI 분석 기능의 입력 텍스트가 국외(미국 등) AI 연산 인프라에서 처리되므로 개인정보 보호법 제28조의8에 따른 국외 이전 고지(이전받는 자, 국가, 항목, 목적, 거부 방법)를 포함해야 한다.
- 이용자 입력 텍스트는 별도 동의 없이 AI 모델 학습에 사용하지 않는다는 원칙을 방침에 명시하고, 학습 활용이 필요해지면 방침 개정과 별도 동의 절차를 선행해야 한다.
- 만 14세 미만 가입 불허 원칙은 이용약관 제4조와 개인정보처리방침 제8조에서 일관되게 유지해야 한다.
- 유료서비스 출시 전 사업자 정보, 통신판매업 신고번호, 가격, 정기결제 주기, 청약철회 제한 사유, 환불 산식, 고객센터 정보를 확정해야 한다.

#### 규제 안전 원칙 (유사투자자문업 회피)

- 본 서비스는 투자 연구 및 시뮬레이션 플랫폼이며, 투자 자문, 투자 추천, 개인 맞춤형 금융 조언을 제공하지 않는다.
- 모든 투자 판단은 사용자가 직접 수행하며 시스템은 계산, 백테스트, 시뮬레이션 및 객관적인 과거 데이터 표시만 수행한다.
- 허용 범위는 사용자 생성 전략 연구, 과거 데이터 기반 백테스트, 모의투자 가상계좌, 차트/기술적 지표/재무 지표/과거 통계 정보 제공으로 제한한다.
- 전략 추천, 종목 추천, 섹터 추천, ETF 추천, 포트폴리오 추천 기능은 제공하지 않는다.
- 시장 예측, 시장 전망, 매수/매도 시점 제안 기능은 제공하지 않는다.
- 나이, 자산 규모, 소득, 위험 성향을 근거로 한 개인 맞춤형 조언은 제공하지 않는다.
- AI 코치 및 Advisor 계열 기능은 전략 자동 추천, 전략 자동 개선, 전략 우열 판단, 사용자 행동 제안을 제공하지 않는다.
- 시스템 문구와 UI/마케팅 카피는 "추천", "유망", "최고", "지금 사야 할", "수익률 보장", "AI 투자 코치"와 같은 표현을 사용하지 않는다.
- 허용되는 표현은 "전략 연구소", "투자 연구 플랫폼", "백테스트 플랫폼", "시뮬레이션 플랫폼", "과거 성과 분석", "연구 도구" 등 비권유적 표현으로 제한한다.
- 성과 관련 설명은 과거 데이터 기준 수치와 사실 진술만 허용하며, 미래 성과 기대나 사용 권장 표현을 포함하면 안 된다.

### 8.3 개발 제약

| 항목 | 내용 |
|------|------|
| 테스트 | 코드 수정 시 반드시 전체 유닛 테스트 통과 확인 |
| 하위 호환 | `BacktestRequest` / `BacktestResponse` 스키마 변경 시 프론트엔드와 동시 수정 |
| DB 마이그레이션 | Prisma 스키마 변경 시 `npx prisma migrate dev` 실행 및 기존 데이터 호환성 검토 |
