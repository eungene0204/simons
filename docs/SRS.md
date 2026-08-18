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
| `backtest_start_date` / `backtest_end_date` | `Optional[str]` | 명시적 연·월·일 범위(`"2002년부터 2005년까지"`, `"2020년 1월부터 2025년 12월까지"`)에서 결정적으로 추출한 `YYYY-MM-DD`(종료 월은 말일, 불가능한 날짜는 미인식 처리). 있으면 상대 기간 대신 이 창으로 백테스트(엔진 `startDate`/`endDate`). LLM 인터프리터 primary 경로에서도 결정적 추출이 최종 덮어쓴다(오늘 날짜를 모르는 모델의 미래 오판·누락 방어, 2026-07-17). **전송 스키마(`backend/schemas.py::BacktestRequest`)에 `startDate`/`endDate`가 선언돼 있어야 한다**(2026-08-01) — 미선언 시 `model_dump`가 조용히 버려(`extra=ignore`) 엔진이 창을 못 받고 `period` 폴백으로 실행된다. 파싱·요약 카드·`to_backtest_request`가 모두 정상이어도 실행만 어긋나므로 가장 발견이 늦다(실측: '최근 10년'이 2022-01-03~2026-07-31로 실행 = `period="5Y"` 창과 정확히 일치). `ranking_metric`·`sector`·`etf_theme`·`listing_from/to`와 동일한 함정이며, 엔진이 읽는 필드는 예외 없이 스키마에 선언한다. 회귀: `test_backtest_request_schema.py::test_backtest_request_model_dump_keeps_explicit_window`. **표시와 실행의 기간은 하나여야 한다**(2026-08-01): 백테스트 설정 패널은 명시 창이 있으면 그 창을 '직접 입력'으로 열어 보여주고, 패널에서 상대 기간을 고르면 이전 명시 창을 **떼어낸 뒤** 실행한다 (`app/analytics/new/backtestOptions.ts` — 남기면 엔진이 날짜를 우선해 사용자가 고른 기간이 무시된다). 패널은 파싱 정본 버킷(1y/3y/5y/full)을 모두 버튼으로 표현할 수 있어야 한다 — 대응 버튼이 없으면 그 기간의 전략이 아무것도 선택되지 않은 채 열린다. 회귀: `app/analytics/new/backtestOptions.test.ts`. **창의 길이가 딱 떨어지면 배지가 그 길이를 앞세운다**(2026-08-02, `explicitWindowSpanLabel`): 버킷 밖 기간('최근 10년간')은 명시 날짜로 변환돼 저장되므로 창만 표기하면 사용자가 말한 기간이 반영됐는지 알 수 없다 — `백테스트 10년 (2016~2026)`. 시작·종료의 일(日)이 달라 정수 개월이 아닌 창(직접 지정한 연도 범위 등)은 길이로 뭉개지 않고 창 표기를 그대로 쓴다. |
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

**FR-STR-019h** [해석 레이어 권한 계약 — 권한 역전, 2026-07-26] 전략 해석 파이프라인의 어떤 레이어도 요청을 실패시킬 권한을 가지면 안 된다. 각 레이어의 반환값은 "처리했음" 또는 "내 소관 아님(다음 레이어로)"뿐이며, **예외는 "내 소관 아님"으로 강등**해야 한다(`parse_modification`·`primary.fast_path_can_handle`의 fast-path 예외 격리). ① 수정 경로의 최초 해석자는 LLM 인터프리터이고 결정론 fast-path(`_modify_rule_based`)는 **삭제하지 않고 레거시 폴백 계층**으로 둔다 — primary가 "내 소관 아님"(None)으로 넘긴 발화만 호출부의 레거시 경로가 처리한다. primary 내부에서 fast-path를 상담하는 것은 계약 위반이라 제거했다(2026-07-26, nl_interpretation_contract § 11-4) — LLM의 되묻기·설명·미해석 안내는 그대로 사용자에게 전달된다. 순서는 `STRATEGY_MODIFY_INTERPRETER_MODE`(기본 `llm_first`, 롤백 `fast_path_first`)로 전환 가능해야 한다. ② 모든 해석 레이어가 실패하면 HTTP 500이 아니라 기존 clarification 채널로 되묻고(기존 전략 보존 + 예시 칩 + `clarification_priority="interpretation_failed"`), **500/503은 인프라 장애 전용**으로 예약한다(LLM 연결 실패는 503 유지). 근거 사고(2026-07-26): 얕은 결정론이 최초 해석자이면서 실패 권한을 함께 가진 구조에서, 프론트 칩이 심은 `metric:"roe"` 오염 하나가 이후 모든 수정 요청을 500으로 죽여 "무엇을 입력해도 같은 에러"인 영구 교착을 만들었다.

**FR-STR-019i** [스키마 별칭 정규화 + 미지 값 드롭, 2026-07-26] `previous_parsed`는 프론트가 만들어 되돌려주는 **신뢰할 수 없는 입력**으로 규정한다. 관용적·레거시 표기 흡수는 경로별 새니타이저가 아니라 **스키마 진입 지점 한 곳**에서 수행해야 한다 — `FundamentalFilter.metric`의 `BeforeValidator`(`_normalize_metric_alias`, 대소문자·공백·하이픈·슬래시 정규화 + 별칭 표: `roe`→`roe_or_gpa` 등)가 `model_validate`가 불리는 모든 지점(fast-path 병합·LLM diff 병합·compile·저장 전략 로드·primary 라운드트립)을 한 번에 덮는다. 별칭 표에도 없는 값은 ① 요청 전체를 실패시키지 않고 ② 조용히 버리지도 않는다 — 해당 필터만 드롭하고 비차단 `notices`로 "'X' 조건은 해석할 수 없어 전략에서 제외했어요"를 알린다(`coerce_fundamental_filters` + 직렬화 제외 필드 `dropped_filter_notices`, DSL·캐시키·라운드트립 비교 불변). 프론트는 백엔드 정본 값만 상태에 써야 한다(`deterministicConditionFlow.ts`의 칩 → `roe_or_gpa`) — 백엔드 별칭 정규화는 안전망이지 오염원의 면허가 아니다.

**FR-STR-019j** [LLM 해석 결과의 결정론 보정 계약, 2026-07-26] 인터프리터(LLM-first) 경로가 컴파일한 전략을 사용자 원문 기반 결정적 추출(`_apply_prompt_overrides`)로 덮어쓰는 보정은 `STRATEGY_PROMPT_OVERRIDE_MODE`(`on` 기본 / `off`)로 전환 가능해야 하며, 그 비용은 `scripts/qa_prompt_override_ab.py`가 103케이스 A/B로 계측한다. **기본값은 `off`다(2026-07-26 전환)** — 사용자가 'regex는 어떤 경우에도 자연어를 해석하지 않는다'를 확정했고, 합성 코퍼스 A/B는 기대값이 정규식의 인코딩 관례를 담고 있어 전환 기준으로 쓸 수 없다고 판정했다(잔여 26건 중 7건). 이후 개선은 실사용 케이스로 진행하며, `on`은 롤백 경로로만 유지하고 롤백 가드 테스트로 고정한다. 보정 계층은 다음을 가려서는 안 된다 — 보정이 존재하는 동안에도 컴파일 결과 자체가 독립적으로 정확해야 하며, 보정을 꺼서 드러난 결함은 보정이 아니라 **원인 레이어에서** 수정한다: ① 이벤트 지표의 반대 방향 청산(골든/데드크로스, 볼린저 하단/상단)은 factor가 같고 임계값이 없어도 미러 복제가 아니므로 보존한다 ② Registry에 표준값이 있는 **계산 파라미터**(이동평균 기간·신고가 룩백)의 누락은 조건 자체를 제외하는 사유가 될 수 없다 — 표준값으로 컴파일하고 되묻기는 유지한다(임계값 `value` 누락은 전략 의미가 미정이므로 기존대로 제외) ③ 체결 시점(`execution_timing`)은 `BacktestSpec`이 표현하며, 수정 경로에서 이전 값을 무조건 이월해 사용자의 변경을 삼켜서는 안 된다 ④ 오실레이터(RSI·스토캐스틱·CCI·ADX 등)는 임계값 비교 연산자만 사용한다(교차 연산자는 이동평균·MACD·볼린저·신고가 전용). ⑤ 입력의 수치가 출력에 반영됐는지 결정론으로 **대조**하고(해석 아님 — 숫자가 출력에 나타나는지만 확인, 단위 환산·부호는 표기 차이로 인정), 누락 시 값을 채우지 않고 LLM에 재생성을 1회 요청한다(`validation/recall_validator.py`, 롤백 `STRATEGY_RECALL_CHECK=off`). 재요청 후에도 누락이 남으면 요청을 실패시키지 않는다 — 누락은 스키마 오류가 아니다. **잔여 누락을 사용자에게 안내하지 않는다**(2026-08-01, 사용자 판단): 대조가 크기만 보는 수치 비교라 안내가 맥락 없는 숫자 나열이 되고("'1, 20일' 수치는 조건으로 반영하지 못했어요"), 정작 걸리는 것은 '월 1회 리밸런싱'(→`monthly`)·'20일 평균 거래대금'(→`trading_value>=50`)처럼 **표현형이 달라 숫자가 남지 않았을 뿐 이미 반영된** 조건이다 — 사용자가 무엇을 다시 말해야 하는지 알 수 없으므로 정보값이 없다. 잔여는 로그로만 남기며(`△ 미반영(안내 없음)`), 재생성 요청의 증거로서의 쓰임은 그대로다. 대가: 진짜로 값이 조용히 틀리는 경우가 사용자에게 보이지 않는다 — 파스 정합은 `parse_fidelity_validator`와 완결성 되묻기가 맡는다. **발화 전체를 대상으로 한 어휘 스캔은 금지**한다(어떤 표현이 그 지표인지 판정해야 하므로 동의어 매핑=해석). 반면 LLM이 '이 문자열이 무엇을 가리킨다'고 판정해 넘긴 짧은 값을 정본으로 푸는 것은 지식 조회이며 허용된다(업종·테마→지식그래프, 종목명→마스터, 지표명→canonical ID) — 이 계층의 입력은 원문이 아니라 term이어야 한다. 상세 계약은 `docs/nl_interpretation_contract.md`.

**FR-STR-020** 시스템은 규칙 기반 파서가 수락한 파싱 결과에 대해, 원문 입력과 파싱된 전략 객체를 LLM으로 비교 검증해야 한다(Parse Fidelity Validator, `engine/parse_validator.py`). 검증은 구조화된 리포트(`parse_validation`: `isValid`, `confidence`, `issues[]`, `missingFields[]`, `clarificationQuestions[]`, `correctedStrategy`, `userFacingMessage`)를 `/strategy/parse` 응답에 포함해야 하며, 누락 필드·모호한 조건·실행 불가능한 조건·원문에 없는 과잉 추론 여부를 점검해야 한다. 검증기는 새 전략을 만들거나 성능을 위해 전략을 개선하거나 투자 자문·추천을 하지 않아야 하며, 검증·명백한 파싱 오류 교정·명확화 질문만 수행해야 한다. LLM 출력 계약은 검증 시간 최소화를 위해 diff 형식이어야 한다: 파스가 충실하면 `{isValid, confidence}`만 출력하고, 명백한 파싱 오류는 `correctedFields`(바뀌어야 하는 필드만)로 출력하며 서버가 원본 파스와 병합해 `correctedStrategy`(전체 객체, 하류 계약)를 구성한다. 검증 LLM에 보내는 파싱 JSON은 null 필드를 생략한다(프롬프트에 '누락=null' 명시). 병합 교정본은 `ParsedStrategy` 스키마 검증을 통과할 때만 적용하고(미지 필드는 병합 전 필터) 원문 `description`은 보존해야 한다. LLM에 도달할 수 없거나(서버 없음/콜드스타트) 검증이 실패하면 빠른 경로(규칙 기반 즉답)를 막지 않도록 즉시 graceful degrade하여 원본 파싱 결과를 그대로 반환해야 한다. 검증 발화 시 룰 파스가 설명하지 못한 잔여 어휘를 로그로 남겨야 한다(빈출 무해 토큰을 어휘집에 보강해 검증 호출 빈도를 줄이는 운영 루프의 입력). 검증 전용 경량 모델은 `NL_VALIDATOR_MODEL`(env)로 opt-in 지정할 수 있다.

**FR-STR-020b** `correctedStrategy` 자동 교정은 스키마 검증만으로 적용해서는 안 되며, 교정본의 진입/청산 신호를 LLM 파싱 본경로와 동일한 환각 방지 키워드 검증(`_validate_signals`: 이름 고정 지표는 원문에 해당 키워드가 있어야 인정)으로 재검증해야 한다. 검증에 실패한 환각 신호(예: 원문에 AI 언급이 없는데 주입된 `ai_model` 'AI 매수 예측')만 떨구고 나머지 정상 교정 필드는 유지한다. (실사례 2026-07-03: KOSDAQ 모멘텀 랭킹 프롬프트에 교정 LLM이 `ai_model` 진입 신호를 환각 주입 → 스키마 검증만 통과해 적용 → 비활성화된 AI 백테스트가 실행되며 무한 대기.)

**FR-STR-019k** [되묻기 provenance — '사용자가 말했나'의 단일 출처, 2026-07-29] 필수 설정 5종(유니버스·최대 보유·리밸런싱·백테스트 기간·초기 자본)의 되묻기 여부는 **값의 존재가 아니라 사용자가 실제로 말했는지**로 판정해야 하며, 그 판정의 출처는 인터프리터 LLM의 구조화 출력 하나뿐이다 — 어느 레이어도 이 목적으로 사용자 원문을 스캔해서는 안 된다(nl_interpretation_contract § 판정 기준). ① **산출**: `strategy_conversation/response/provenance.py::explicit_fields_from_spec`이 `StrategySpec`의 필드 유무만 보고 `explicit_fields`를 만든다. 따라서 LLM은 사용자가 말하지 않은 필드를 **비워 두어야** 한다 — `UniverseSpec.markets`의 기본값 `["KOSPI200"]`은 컴파일러로 옮겼다(LLM이 기본값을 채우면 출력에서 provenance가 지워져 판정 자체가 불가능해진다). ② **누적**: 대화는 무상태이므로 프론트가 `previous_explicit_fields`로 에코하고 백엔드가 합집합으로 누적한다(`pending_ask`·`previous_coach_text`와 동형 계약). 에코는 신뢰 경계 밖이므로 알려진 5필드 밖 항목은 조용히 버린다. SSE 프록시는 화이트리스트라 `explicit_fields`를 명시적으로 실어야 한다. ③ **LLM 레인 밖의 답변**: 칩 답변은 백엔드 왕복이 없어 프론트가 그 필드를 기록하고(안 하면 같은 질문 무한 반복), 빌더 레인은 슬롯 자체가 답변 기록이므로 슬롯→필드 매핑으로 산출한다(`BUILDER_SLOT_EXPLICIT_FIELDS`). 기간·초기 자본은 빌더 슬롯이 없어 빌더 단독 진입(파스 없는 `start_builder`) 시 provenance 출처가 없다 — 이때는 기본값으로 조용히 확정하지 말고 **묻는다**. ④ **되돌리기·복원**: '돌아가기'는 되돌린 필드의 provenance도 함께 되돌리고(안 하면 되돌아온 질문을 이미 답한 것으로 보고 건너뛴다), 세션 스냅샷은 provenance를 함께 저장·복원한다. ⑤ **금지**: 프론트 게이트가 원문 정규식으로 '말했나'를 판정하는 것(구 `hasExplicit*` 5종). 이 방식은 양방향으로 틀렸다 — 미탐('최대 보유 종목은 10개'를 못 잡아 진행률 미체크)과 오탐('거래대금 20억 원'을 초기 자본 명시로 오인해 되묻기를 삼킴). 어휘를 넓히는 보정은 같은 사고를 되풀이하므로 금지하고, 미탐·오탐은 인터프리터 레인에서 재현·수정한다. ⑥ **수정 턴의 근거는 spec이 아니라 패치다**(2026-08-02): ①의 '필드 유무'는 spec이 **사용자 발화에서 뽑힌 것일 때만** 유효한 근거다. 수정 턴의 spec은 이전 전략을 디컴파일한 초안에 패치를 얹은 것이라 물질화 기본값(`initial_capital=10,000,000`)이 이미 채워져 있고, 값의 존재로 판정하면 사용자가 말한 적 없는 값이 '명시'가 된다 — 실측 2/2: 백테스트 기간만 답한 턴에서 `initial_capital`이 explicit로 올라가 **초기 자금을 아예 묻지 않게 되고** 기본값 1천만원이 조용히 확정됐으며, 그 뒤 사용자가 `10억`만 입력해도 결속할 질문이 없어 발화가 조용히 버려졌다. 따라서 수정 턴은 환각 게이트를 통과한 **패치 경로**에서 산출한다(`explicit_fields_from_patches` — 경로 표기만 보는 정규화이며 원문은 읽지 않는다). 이전 턴 값은 ②의 에코 합집합이 계속 지킨다. 이 사고는 이 문서 서두가 이미 경고한 '왕복이 provenance를 지운다'의 발현이므로, **provenance를 산출하는 새 자리를 만들 때는 그 spec의 출처가 발화인지 상태인지 먼저 확인한다.**

**FR-STR-019m** [빈 슬롯 판정 단일 정본, 2026-07-29] "이 전략에서 무엇이 아직 비었나"의 판정은 `backend/engine/strategy_slots.py` 하나여야 한다. 이전에는 같은 판정이 네 곳에 각자 구현돼 있었고(planner State의 `filled_slots`, 백엔드 되묻기 게이트 `_missing_backtest_conditions`, 프론트 게이트 `backtestReadiness.ts`, 빌더 `required_missing`), 어휘·기본값 취급·세부 규칙이 달라 이음매마다 사고가 났다(2026-07-28 리밸런싱 무질문 확정, 2026-07-29 매수 조건 재질문 2건). ① **판정 단위와 골격의 분리**: 필드 9개(universe·entry·exit·max_positions·rebalancing·stop_loss·take_profit·backtest_period·initial_capital)가 판정 단위이고, 사용자에게 보이는 진행 골격 8칸은 그 그룹이다(리스크 관리 슬롯만 손절·익절 두 필드를 묶으며 **둘 다** 있어야 충족). 어휘가 갈렸던 것이 어긋남의 절반이었다. ② **소비자별 차이는 판정이 아니라 인자로만** 표현한다 — 범위(`fields`)와 provenance 요구(`require_explicit`), 이미 결정된 필드(`rebalancing_declined`). 되묻기 문구·칩도 판정과 같은 모듈에 둔다(떨어져 있으면 슬롯이 늘 때 한쪽만 갱신된다). ③ **기본값 물질화는 충족이 아니다**: `ParsedStrategy`는 유니버스·최대 보유·기간·초기 자본에 기본값을 채우므로 값만 보면 **빈 전략조차 4/8 완료**로 보인다 — planner State는 provenance(FR-STR-019k `explicit_fields`)를 함께 봐야 하며, 그러지 않으면 planner가 그 슬롯을 영영 묻지 않는다. ④ **'안 함' 같은 명시적 거부는 provenance가 아니라 '이미 결정된 필드'로 다룬다** — provenance 쪽에 두면 `require_explicit=False`인 레인이 무시해 같은 질문이 무한 반복된다. ⑤ **프론트는 정본에 고정한다**: 칩 답변을 백엔드 왕복 없이 적용해야 해(대화 지연) 프론트도 로컬 판정을 갖지만, 정본이 생성한 계약 픽스처(`scripts/export_slot_judgments.py` → `app/analytics/new/__fixtures__/slot-judgments.json`)로 두 런타임의 일치를 강제한다 — 프론트 parity 테스트와 픽스처 최신성 테스트가 양쪽에서 잠근다. 픽스처는 손으로 고치지 않는다. ⑥ 빌더(`required_missing`)는 상태 모델(`BuilderState`)이 달라 통합 대상이 아니며 슬롯 라벨만 공유한다. ⑦ **ask 채택은 슬롯 단위로 대조**한다 — "어딘가 비었나"만으로 planner ask를 채택하면 다른 슬롯의 공백을 근거로 이미 채워진 슬롯을 다시 묻는다(`primary._is_filled_slot_topic`). planner-first는 파스보다 먼저 계획해 자기 `filled_slots`를 볼 수 없으므로, 이 대조는 파스 결과가 존재하는 채택 시점에 해야 한다.

**FR-STR-019n** [칩=값 결속 계약, 2026-07-29] 사용자에게 보여주는 선택지 칩은 **우리 agent가 만들어 낸 열거형 옵션**이므로, 그 칩이 뜻하는 전략 값은 칩을 발행하는 순간 이미 확정돼 있어야 하고 클릭은 그 값을 꺼내 쓰는 행위여야 한다 — 칩 문구를 다시 해석(LLM 재파싱·정규식 재추출)해서는 안 된다. ① **발행 시 결속**: 조건 슬롯 ask의 칩은 `primary._bind_chips`가 발행 시점의 State에 적용해 `{필드: 값}` 패치로 확정하고, `pending_ask.chip_bindings`로 프론트에 에코한다(무상태 컨텍스트 에코 계약 — 프론트는 열지 않고 그대로 되돌려 보낸다). ② **결속 실패 = 노출 금지**: 값이 결속되지 않는 칩은 엔진이 표현할 수 없는 조건이므로 사용자에게 **아예 보여주지 않는다**(`clarification_suggestions`도 결속된 칩 목록으로 재구성, 전부 탈락이면 질문만 남기고 자유 서술로 받는다). planner LLM은 칩 문구를 자유롭게 지어내므로 이 게이트가 없으면 미지원 개념이 그대로 선택지로 나간다 — 실측 사고 2026-07-29: `volume_multiple`이 registry에 `_unsupported`이고 거래량 **하락**은 지표 자체가 없는데 '거래량 급감(전일 대비 1/2 이하) 시 매도'가 칩으로 노출됐고, 사용자가 그걸 클릭하자 "요청을 전략 조건으로 해석하지 못했어요"로 끝났다(우리가 제안한 선택지를 우리가 못 알아듣는 자기모순). 결속 성공만으로는 충분하지 않다 — **미지원 개념을 언급하는 칩은 부분 결속에 성공해도 노출하지 않는다**(`_mentioned_unsupported_concepts` 검사 — 칩 텍스트는 planner LLM 출력이므로 결정론 레인이다. 실측 사고 2026-08-02: '거래량 급증(전일 대비 3배) 시 매수'가 '거래량 급증'만 `volume_spike`로 결속돼 게이트를 통과했고, 배수 조건은 조용히 소실된 채 노출 — 클릭하면 `volume_multiple` 미지원 안내로 끝났다). 이 사고를 계기로 **planner 칩 노출 자체를 폐지했다**(2026-08-02 사용자 결정 — 모든 옵션 칩은 하드코딩 정본이어야 지원을 확신할 수 있다): 조건·설정 슬롯 ask의 칩은 `_bound_ask_with_slot_fallback`이 planner 칩을 폐기하고 **항상** 슬롯 SOT 정본(`engine.strategy_slots.suggestions_for_topic` ← `_QUESTIONS`)으로 대체해 발행한다. ETF 유니버스에는 재무 칩(PER·ROE)이 제외되며(`universe_capabilities` — ETF는 기업 재무 사용 불가, 결속 검사는 유니버스 호환성을 보지 않으므로 정본 선별 단계에서 걸러야 한다), topic이 슬롯에 매칭되지 않으면 칩 없이 질문만 남는다(LLM 칩으로 메우지 않는다). 유니버스 범위 칩(④)과 미해결 업종·종목 후보 칩은 관찰된 카탈로그/리졸버 후보 표기 그대로라(결정론 데이터) 이 대체의 대상이 아니다. ③ **description은 값이 아니다**: `description`은 발화 원문 보관 필드라 전략을 바꾸지 않는다 — 이 필드만 달라진 칩은 결속 실패로 판정한다. 이 구분이 없어 `run_chip_answer`가 무변경을 "칩 답변 확정"으로 오보고하던 구멍이 있었다(사용자는 답했는데 아무것도 안 바뀐 화면을 본다). ④ **유니버스 범위 칩은 예외**: 칩이 카탈로그 후보 표기 그대로라 결속이 이미 보장돼 있고(`_planner_scope_ask`), 발행 시 결속을 시도하면 테마 상장사 조회가 칩 수만큼 반복돼 발행 지연이 커진다 — 클릭 시 `_apply_universe_chip`이 결정론으로 적용한다. ⑤ **출력 가드 동기화**: 규제 가드가 칩 문구를 바꾸면 결속 키가 어긋나므로 살아남은 칩의 결속만 남긴다(`output_guard.finalize_user_response`) — 결속을 잃은 칩은 칩 문구 결정적 추출 안전망으로 강등된다. ⑥ **하위 호환**: `chip_bindings` 없는 구 에코는 기존 결정적 추출 경로를 그대로 탄다. 회귀: `test_chip_answer.py`(미결속 칩 미노출·미지원 개념 언급 칩 미노출·전량 탈락 시 칩 제거·description-only 미적용·결속값 직접 적용·재계획 칩 정본 대체), `test_slot_clarification_chips.py`(planner 칩 정본 대체·ETF 재무 칩 제외·정본 칩 결속 실증).

**FR-STR-019o** [전략 파스 지연 예산, 2026-07-29] 전략 파스 1회의 지연은 **LLM 호출 횟수 × (prefill + 생성)** 으로만 결정된다 — 실측(로컬 9B) 결과 테마·KG 조회 등 비-LLM 작업은 전부 합쳐 74ms(0.0%)였고, 나머지 100%가 LLM이었다. 따라서 지연 대책은 **호출 횟수를 줄이거나 prefill을 재사용하는 것**뿐이며, 타임아웃 상향은 대책이 아니다. ① **prefill이 생성보다 비싸다**: 인터프리터 system 프롬프트는 20,470자(~8,900 tok)이고 콜드 prefill 43.6초 vs 캐시 적중 0.4초(총 호출 60.2초 → 7.5초, 109배). 고정 system 프롬프트는 대화마다 바뀌지 않으므로 **startup에 한 번 흘려 KV 프리픽스 캐시를 채운다**(`main._kick_system_prompt_prefill` → `nl_parser._ollama_prefill_system_prompt`, 인터프리터·planner 각 1회, num_predict=1, keep_alive=-1). 모델 가중치 적재(`_kick_local_ollama_model_preload`)로는 해결되지 않는 별개 비용이다 — 가중치가 올라와 있어도 prefill은 호출마다 다시 계산된다. ② **planner 재계획 금지**: planner는 mode=primary인 모든 턴에서 파스 최선두(`_plan_first`)로 이미 돌므로, 그 실패를 근거로 되묻기 단계에서 **다시 계획하면 안 된다**. 예산 소진은 실패가 아니라 검증 리포트 고정 질문으로 폴백하는 정상 경로다 — 재시도 분기를 두면 실패가 비용을 두 배로 만든다(실측: 한 파스에서 planner 6회 호출, 148초 + 84초). ③ **턴 예산 2**(`dag_planner_max_turns`, 롤백 `STRATEGY_DAG_PLANNER_MAX_TURNS=4`): warm 캐시에서도 planner 1턴이 40~56초라 예산이 곧 지연이다. 발행→도구 관찰→수정 발행이 통상 흐름이고 그 이상은 값을 거의 못 얻는다. ④ **측정 규율**: 이 계층의 지연 실측은 머신 부하에 극단적으로 민감하다(같은 인터프리터 호출이 load 11에서 21초, load 90에서 43초). 벽시계 비교는 부하가 안정된 상태에서만 유효하며, 부하와 무관한 정본 지표는 **LLM 호출 횟수와 prefill 토큰 수**다. ⑤ **프롬프트 예산**(2026-07-30): 시스템 프롬프트는 prefill 비용에 직결되므로 **파이프라인이 읽지 않는 출력 채널을 LLM에 요구하지 않는다** — `status`·`missing_fields`·`assumptions`는 각각 `run_validation` 재판정·`validate_completeness` 결정론 산출·소비자 부재로 죽은 채널이어서 형태와 규칙에서 제거했다(20,470자→19,441자). 다만 **형태(`_OUTPUT_SHAPE`)에서 키를 빼는 것과 규칙 문장을 빼는 것은 힘이 다르다** — 형태에 없는 키는 규칙이 아무리 상세해도 9B가 채우지 않으므로, 살아 있는 필드는 반드시 형태에 남긴다(FR-STR-019p). ⑥ **워밍업은 추론과 같은 `num_ctx`로 한다**(2026-07-30, 필수 계약): Ollama 러너는 **적재 시점 옵션으로 뜨고**, 다른 `num_ctx` 요청이 오면 러너를 갈아끼운다. 워밍업(`_ollama_preload_model`·`_ollama_prefill_system_prompt`)은 `keep_alive=-1`로 러너를 **영구 고정**하므로, 워밍업이 추론과 다른 컨텍스트로 적재하면 교체가 끝나지 않고 이후 **모든 추론 호출이 무한 대기**한다 — 지연이 아니라 완전 정지다. 실측 사고: 워밍업이 `num_ctx`를 싣지 않아 러너가 모델 최대 컨텍스트(262144)로 고정 → `num_ctx=16384` 추론이 240초+ 무응답(러너 CPU 0%, 신규 러너 미기동) → 파스 1회 480초 → 프론트 프록시 120초 예산 초과로 `The operation was aborted due to timeout`. 같은 모델·같은 질문이 `num_ctx` 생략 시 0.8초, 지정 시 240초+였고, 워밍업에 `_OLLAMA_NUM_CTX`를 실은 뒤 파스가 19.9초로 복귀했다. 또한 컨텍스트가 다르면 prefill KV 캐시가 **다른 러너에 쌓여** ① 자체가 무효가 된다. 이 규칙은 `parse_validator._VALIDATION_NUM_CTX` 주석이 이미 명문화한 것으로(당시 증상은 '호출마다 콜드 페널티'), `keep_alive=-1` 고정이 더해지며 치명도가 올라갔다. 회귀 가드: `test_ollama_warmup_uses_same_num_ctx_as_inference`. ⑦ **서버 부재는 워밍업 실패와 다른 사건이다**(2026-08-01): 적재·prefill 실패는 "첫 호출 시 lazy 로드"로 복구되므로 무시해도 되지만, 로컬 Ollama **서버 자체가 죽어 있으면** 그 전제가 성립하지 않는다 — 백엔드는 LLM 없이 조용히 기동하고, 사용자에게는 파싱 회귀로 보인다(실측 사고: 전략 문장이 `intent=UNKNOWN`(호출조차 못 해 0.0초)으로 분류돼 프론트가 일반답변 경로로 보내고, 그 LLM도 없어 "해당 주제에 대한 일반적인 설명을 준비하지 못했습니다" 폴백 — 분류·파싱·일반답변 세 레인이 동시에 죽는다). 따라서 startup은 워밍업 **전에** 서버 생사를 확인하고(`main._local_ollama_reachable`: GET `/api/tags`, 3초), 닿지 못하면 적재·prefill을 건너뛰고 조치 방법과 함께 로그로 알린다. 로컬 dev는 `brew services start ollama`로 부팅 시 자동 기동한다(수동 기동 의존이 사고의 배경이었다). 회귀 가드: `test_startup_model_preload.py::test_unreachable_local_ollama_warns_and_skips_preload`.

**FR-STR-019p** [출력 형태 권위 — 살아 있는 필드는 형태에 싣는다, 2026-07-30] 인터프리터 LLM(9B)에게 **출력 형태(`_OUTPUT_SHAPE`)에 없는 키는 규칙 문장으로 요구할 수 없다.** 형태에 없으면 모델은 그 자리를 `null`로 내거나 아예 생략하며, 이는 사용자가 말한 값을 조용히 잃는 사고로 직결된다. ① **실측 사고**: 조건 예시가 재무 조건 하나뿐이라 `parameters` 키가 형태에 없었고, 규칙 5-3이 `short_period=1`/`long_period=N` 매핑을 상세히 규정했음에도 "20일선을 깨고 내려오면 매도"·"주가가 20일선을 상향 돌파"·"20일선이 60일선을 골든크로스"가 1차 출력에서 `parameters=null`로 나왔다 — 사용자가 말한 기간이 사라져 완결성 검증이 "단기 기간을 몇으로 할까요?"라고 되물었다(이미 답한 값 재질문). `etf_theme`(FR-STR-067, 2026-07-27)과 동일한 실패 방식이다. ② **수정**: 형태의 `entry_conditions`에 `parameters`를 채운 크로스오버 조건을 함께 싣고, 단일 이동평균 문장의 worked example(예시 3-1)과 긴 요청 예시(4-2)에 파라미터를 명시한다 — 후자는 이동평균이 하나만 언급됐는데 다른 예시의 20/60을 베껴 **말하지 않은 60을 지어내던** 무단 확정을 차단한다. ③ **형식 정규화**: `parameters: null`은 빈 dict와 같은 뜻이므로 `StrategyCondition._coerce_parameters`가 흡수한다 — 종전에는 `dict_type` ValidationError로 출력 전체가 버려져 복구 재요청 1회(수 초)를 무조건 태웠고, 재요청 결과도 기간을 채워 오지 않았다. ④ **검증 규율**: 프롬프트 규칙만 고치고 형태를 그대로 두는 변경은 이 계층에서 효과를 보증하지 못한다 — 실제 모델로 같은 문장을 반복 실행해 확인한다(수정 검증: 5문장×3회 15/15, `repairs=0`, 기간 되묻기 소멸, 비-이동평균 전략에 유령 크로스오버 조건 유입 없음). ⑤ **같은 교훈이 배포 직후 재발**: 죽은 채널 제거(FR-STR-019o ⑤) 작업에서 예시 1의 clarification_questions worked example(`{"field":"strategy.entry_conditions[0].value", ...}`)을 함께 지웠는데, 그 예시가 프롬프트 전체에서 `ClarificationQuestion` 객체 형태를 보여주는 유일한 자리였다(형태의 `clarification_questions`는 원래도 빈 배열이라 형태 자체는 스키마를 가르치지 못한다). 결과: 9B가 되묻기 항목을 낼 때 필수 필드 `field`를 빠뜨려 StrategyIntent 검증 실패→복구 재시도(`MAX_REPAIR_ATTEMPTS=1`)도 같은 방식으로 실패→`InterpreterError`로 **전략 전체가 버려졌다** — "20일 고점을 넘기는 날 매수"처럼 완전히 파싱 가능한 입력까지 빈 전략(`interpretation_failed`, universe=KOSPI200 기본값)으로 끝났다. 실측: `qa_template_detect.py --category 기술분석 --refresh` 20개 중 5개 치명(모두 동일한 `유니버스=KOSPI200 · max_pos=10` 고정값 — 프롬프트 내용과 무관해 실제 해석 실패가 아니라 스키마 거부로 의심할 신호였다). 수정: 형태의 `clarification_questions`에 `field` 키를 채운 worked example을 다시 싣는다. **검증 함정**: 직접 스크립트로 인터프리터를 호출하는 진단은 `.env`를 로드하지 않는다 — `load_dotenv()`는 `main.py` 임포트에만 걸려 있어, `main.py`를 거치지 않는 스크립트는 `STRATEGY_INTERPRETER_MODEL`이 비어 코드 기본값(`qwen3:8b`, prod 모델과 다른 모델)으로 조용히 폴백한다 — 이 세션에서 그 폴백 때문에 회귀를 놓치고 "9B로 검증됨"이라고 잘못 보고할 뻔했다. 인터프리터를 직접 호출해 검증할 때는 `STRATEGY_INTERPRETER_MODEL`을 명시적으로 export하거나, HTTP `/strategy/parse` 엔드포인트(서버 프로세스는 항상 `.env`를 로드)를 통해 검증한다. ⑥ **구조적 가드**(2026-07-30): 같은 사고가 두 번 난 뒤 회귀 테스트를 개별 필드 단위가 아니라 **불변식**으로 세웠다 — `test_output_shape_objects_expose_all_live_fields`는 형태에 **구체적 객체로** 등장하는 모델(`universe`·`portfolio`·`risk_management`·`backtest`·`entry_conditions[]`·`clarification_questions[]`)의 스키마 필드가 형태에 빠짐없이 노출되는지 검사한다. 스키마에 필드를 추가하고 형태 갱신을 잊으면 실패하며, 일부러 빼는 필드는 `_SHAPE_OMISSIONS`에 **이유와 함께** 등록해야 한다(형태에서 빼는 것을 의식적 결정으로 강제). 검사 대상을 '구체적 객체'로 한정한 근거: `ranking: []`처럼 빈 배열로만 등장하는 자리는 잘못된 키 집합을 각인시키지 않아 규칙·예시만으로 정상 동작한다(실측) — 위험한 것은 **일부 키만 보여준 객체**이며, 모델이 그 키 집합을 완전한 것으로 취급한다. 현재 등록된 의도적 누락: `max_position_weight`(엔진 미지원 — 노출하면 오류 출력을 유도), `value_source`(모델 validator 계산값), `recommended_value`·`requires_confirmation`(Registry가 독립 공급), `recommendation_reason`(선택적 서술). 뮤테이션 검증 완료(신규 필드 주입 시 실패, 원복 시 통과). ⑦ **필수의 경계 — 침묵은 거부, '없음'은 명시적 null**(2026-08-16): ⑤의 가드는 "스키마가 `field` 누락을 거부한다"는 전제 위에 서 있는데, 종전 `field: str`은 **명시적 `null`까지 함께 거부**했다. `intent=NON_STRATEGY_REQUEST`에는 가리킬 전략 필드가 애초에 없어 9B가 정직하게 `field=null`을 내는데, 스키마가 그것을 튕겨 수리 재요청으로 넘어갔고 **재요청이 없는 필드를 지어냈다**. 실측: "내 돈 3천만원 대신 투자해줘"의 1차 출력은 `unsupported_features=["내 돈"]`에 "주식 투자 전략을 구체적으로 설계해 드릴까요?"로 대리투자를 받아주지 않았으나, 재생성본이 `field="backtest.initial_capital"`·`recommended_value=30000000`인 초기자본 질문으로 바꿔 **규제 대상 요청을 전략 설정으로 받아 적었다** — 1차 출력이 더 옳았고 스키마가 그것을 거부한 것이 원인이다(수리 재요청이 원출력의 옳은 판단을 훼손하는 같은 구조: `salvage_clarification_questions`, 2026-08-10). 수정: `field: Optional[str]`을 **기본값 없이** 선언한다(Pydantic v2에서 필수·nullable) — 키 누락은 계속 거부해 ⑤의 가드를 그대로 유지하고, '가리킬 필드 없음'은 명시적 `null`로만 말하게 한다. 소비처 중 `q.field`를 정규식에 직접 넣던 `primary._clarification_items`만 `q.field or ""`로 막았다(나머지는 이미 falsy·None 안전). 발견 경로: 인터프리터 원출력 수집 하니스(`scripts/qa_interpreter_raw_capture.py`)의 319건 baseline — 원출력이 어디에도 저장되지 않아 이 계열 결함이 보이지 않던 상태였다. 회귀: `test_clarification_question_without_a_field_path_validates`, `test_build_clarification_items_survives_a_null_field`(둘 다 `test_interpretation_authority.py`), 기존 `test_clarification_question_missing_field_key_is_rejected`와 공존.
**FR-STR-019q** [필드 상태 축 — '해당 없음'과 '완료'의 분리, 2026-07-30] 진행 골격 필드의 충족 판정은 `filled: bool` 하나로 표현할 수 없다. 그 불리언은 서로 다른 셋을 같은 값으로 뭉갠다 — ① 사용자가 말한 값 ② 기본값이 물질화된 미확인 값 ③ 물을 대상이 아닌 항목. 특히 ③이 '완료'로 표시돼 **단일 종목 전략의 리밸런싱 칸에 체크가 켜지고 진행률이 실제보다 높게** 보였다. 따라서 `engine/strategy_slots.py`(FR-STR-019m의 판정 SOT)는 `filled`와 **독립된 상태 축**(`FieldStatus` 7종: UNKNOWN·CONFIRMED·INFERRED·PROVISIONAL·INVALID·CONFLICTED·NOT_APPLICABLE)을 함께 산출해야 한다. ① **스키마를 감싸지 않는다** — 설계 스펙 § 5의 `{value, status, source, ...}` 래핑은 컴파일러·디컴파일러·patch_applier·엔진 변환기·프론트를 전부 깨뜨린다. 값의 표현은 그대로 두고 상태만 옆에 다는 사이드카여야 한다. ② **새 판정을 만들지 않는다** — UNKNOWN/CONFIRMED/PROVISIONAL/NOT_APPLICABLE은 기존 3축(`_decided`·`_has_value`·`_explicit_ok`)의 재해석이고, INVALID(지표 미해석·미지원)와 조건 단위 NOT_APPLICABLE(ETF×기업 재무지표)은 검증 후 `StrategySpec`에서 구조적으로 재판정하며(`validation/field_state.py`), CONFLICTED만 `conflict_validator`가 판정한 자리에서 슬롯을 함께 기록한다(`ValidationReport.conflicted_slots` — 오류 문장만으로는 어느 필드가 모순인지 알 수 없다). 같은 규칙의 두 번째 구현은 반드시 갈라지므로 금지한다. INVALID와 NOT_APPLICABLE을 나누는 기준은 해결책이다 — 전자는 지표를 바꾸고 후자는 유니버스를 바꾼다. ③ **`filled` 판정을 바꾸지 않는다** — 상태 축은 표시 전용이며 되묻기 게이트·백테스트 실행 버튼·planner의 `filled_slots`는 도입 전과 동일하게 동작해야 한다. `status_overrides`도 상태만 덮고, 값이 없는 필드(UNKNOWN)는 덮지 않는다(모순일 수 없다). 무회귀의 근거는 계약 픽스처(`__fixtures__/slot-judgments.json`) 재생성 시 **무변동**이다. ④ **진행률 표시** — 'NOT_APPLICABLE'은 분자·분모 양쪽에서 뺀다(`countProgress`). 완료로 세면 진행률이 부풀고, 미완료로 세면 영원히 채울 수 없다. INVALID·CONFLICTED는 분모에 남는다(해결해야 할 칸이다). 백엔드 `field_states`는 SSE 프록시 화이트리스트에 실려야 하며, 누락 시 표시만 이전으로 회귀하고 흐름은 그대로다. ⑤ **미구현**: 설계 스펙 § 5의 `source`·`confidence`·`updated_at`·`dependencies`·`invalidated_by` 메타데이터(현행 `ValueSource`·provenance가 source의 부분집합을 담당), INFERRED 산출(열거형 정의만 — 슬롯 단위로 롤업할 소비자가 없어 미리 만들지 않는다). **[2026-08-02 개정 — '최대 보유' NOT_APPLICABLE 경계]**: 지정 종목 모드의 '최대 보유'(진행률 카드 '포트폴리오' 칸)가 종목 수와 무관하게 NOT_APPLICABLE로 계산돼, 다종목 지정(HBM 테마 33곳)에서 요약 카드는 '지정 종목 33개 균등 투자'를 보여주는데 진행률 카드만 '해당 없음'을 표시하는 모순이 있었다. 판정 경계를 리밸런싱과 동일한 단독/다종목 축으로 통일한다(`strategy_slots._status_only_not_applicable`): 단독 종목(지정 1개)만 해당 없음(포트폴리오 자체가 없다), 다종목 지정은 보유 수가 종목 수로 확정된 완료(APPLICABLE·CONFIRMED, 진행률 분모 포함). filled 판정은 불변(③ 계약 유지). 회귀: `test_strategy_slots.py::test_multi_symbol_max_positions_is_applicable_and_confirmed`.

**FR-STR-019r** [유니버스 확인 질문 무응답 소멸 안내, 2026-08-02] Agent Architecture Audit(Planner→Action DAG→State) 재현: 유니버스 범위 확인 질문("'ESS'는 '전력저장장치(ESS)' 테마예요, 이 범위로 바꿀까요?")이 대기 중일 때 사용자가 그 확인과 무관한 답(예: 매수 조건 칩)을 하면, DAG가 그 질문을 재질문·안내 없이 버리고 다음 화제로 넘어갔다 — 유니버스는 이전 값에 그대로 머무는데 사용자는 그 사실을 알 방법이 없었다. `strategy_conversation/planner/dag.py`의 `NodeStatus.INVALIDATED`(§ 12.2 설계 의도: "무효화된 노드는 삭제하지 않고 남긴다")는 실제로는 `_trace_final_statuses`를 통해 관측(trace)에만 쓰이고 사용자 응답에는 배선돼 있지 않았다. `main._flag_unresolved_universe_ask`(모든 반환 지점이 지나는 `_finalize_parse_result`의 마지막 단계)가 최소 보정을 한다: 직전 턴 `pending_ask.topic`이 유니버스 확인이었고, 이번 턴의 `pending_ask.topic`도 유니버스가 아니며, 유니버스 관련 필드(`universe`·`sector`·`theme_universe`·`etf_theme`·`target_symbols`)가 이전 턴과 완전히 동일하면 — 그 질문이 아직 답변되지 않았다는 `notices`를 덧붙인다. 판정은 두 턴의 topic 라벨(LLM/planner 출력)과 필드값 동일성 비교뿐이며 사용자 원문을 다시 읽지 않는다(계약 § 판정 기준). 슬롯 완결성 재질문(예: 매도 조건이 매 턴 반복되는 것)은 대상이 아니다 — 그건 서로 다른 진행 골격 슬롯(EXIT vs STOP_LOSS/TAKE_PROFIT)이 독립적으로 비어 있는 정상 동작이다(`engine/strategy_slots._has_value` 참고). 같은 감사에서 발견된 별개 사고(대원칙 1 위반 — `intent/condition_builder.py::clarification_for_add`가 수정 턴마다 `request.prompt` 원문에 정규식 cue 매칭을 돌려 인터프리터를 아예 호출하지 않고 응답을 확정했다, 예: "ESS 종목 중에서 거래대금 상위만 넣어줘"가 "ESS"·랭킹 요청을 통째로 무시하고 "거래대금 몇억 이상?"만 반환·LLM 호출 0회)는 `main.py`의 그 호출 제거로 수정했다 — 값 없는 조건 추가는 `validate_intent`→`validate_completeness`가 인터프리터의 구조화 출력을 보고 이미 동일한 모양의 되묻기를 낸다(중복 로직 제거, 새 판정 추가 아님). 회귀: `test_modify_roundtrip_migration.py`(`test_add_cue_reaches_interpreter_instead_of_raw_regex_shortcut`, `test_unresolved_universe_ask_is_flagged_when_topic_shifts_without_change`, `test_universe_ask_not_flagged_when_universe_actually_changed`, `test_universe_ask_not_flagged_when_still_the_open_question`).

**FR-STR-019s** [검증 거부의 정직한 보고 + 대조 게이트 단위 공백, 2026-08-02] Agent Architecture Audit #3(멀티턴 에코 하니스 25턴 실측) 결함 8건 수정. 핵심 계약 4개: ① **검증 거부는 해석 실패가 아니다** — 수정 턴에서 패치 적용 후 검증 오류(코스피+PER→ETF의 capability 충돌 등)가 나면 llm_first에서는 폴백("해석하지 못했어요" 오보고) 대신 전략 무변경 + 검증기 오류 문장을 그대로 되묻기로 전달해야 한다(`primary._capability_conflict_clarification`). 유니버스 변경 턴의 해소 칩은 검증기 unsupported 표기와 패치된 State에서 결정론 조립하며, **pending_ask 결속 없이** 내보낸다 — 복합 의미("제거+전환") 칩을 결속 프로브가 절반만 결속시키면 클릭이 결정론 레인에서 부분 적용된다(실측). ② **§ 3-1 수치 대조의 단위 환산표는 복합 수사 단위(천만·백만·십만)를 포함해야 한다** — "5천만원"이 "5천"으로 절단되면 게이트가 정당한 패치를 자릿수 모순으로 거부한다(자릿수 오류 검출력은 유지). ③ **미반영(notices-only) 응답은 답을 기다리던 질문을 되붙인다**(`primary._reattach_open_question` — FR-SA-015의 파스 레인 등가물, 에코된 pending_ask/pending_question 전달만). ④ **planner 턴 예산은 무진전 반복만 막는다** — 직전 턴이 새 관찰을 만들었으면 +2턴 연장하고, list_concept_candidates 후보가 정확히 1개면 그 정본 표기의 kg_theme_companies 조회는 LLM 판단이 아니라 결정론 에필로그다(후보 2개 이상은 범위 ask — 자동 조회 금지). 부수: Artifact 상태 레인(FR-SA-011)·field_metadata는 직렬화된 dict 입력도 수용해야 하며(라이브 경로 모양 — 인스턴스만 주입하는 테스트는 사각), 비-SSE `/strategy/parse` 응답 모델은 `field_states`를 노출해야 한다. 분류 프롬프트 규칙 4-2(작업 제어 발화는 규제 게이트 라벨이 아니다)와 인터프리터 예시 3-0(기간 없는 골든크로스=정본 5/20, 오타 변형 포함)은 라이브 실측으로 검증(15/15·3/3). 회귀: `test_agent_audit3_fixes.py`, `test_dag_planner.py`.


**FR-STR-019t** [손절·익절 단일 표현 + 청산 역할 검증, 2026-08-05] ① **손절·익절은 정본 자리(risk_management)에 한 번만 남긴다** — 인터프리터가 조건 목록에 factor=`risk_management.*`로 실어 보낸 항목은 형식 정규화가 값을 빈 risk_management 필드로 흡수한 뒤 목록에서 제거한다(`interpreter/models.py::_absorb_risk_field_conditions` — 2026-08-06 FR-STR-019v에서 `_absorb_scalar_slot_conditions`로 확장·개명). 손절은 의미상 청산 규칙이 맞으므로(사용자 판정 2026-08-05) 이 중복은 환각이 아니라 표현 자리 문제다. 값도 없고 필드도 비어 있으면 제거하지 않는다(조용한 누락 금지 — 미지원 팩터 안내 레인이 담당). ② **capability 검증은 청산 조건의 역할 호환(기술적 신호만 가능)을 검사해 위반을 에러로 보고해야 한다** — 에러 없이 READY로 통과하면 전량 컴파일이 첫 위반에서 `StrategyCompileError`로 전략 전체를 버리고 "해석하지 못했어요"로 강등된다(2026-08-05 사고: 9B가 손절 -8%를 `fundamental.roe_or_gpa<=-100` 청산 조건으로 미러링 — 현금흐름 3분류 지표 승격이 프롬프트 지표 카탈로그를 바꿔, 미러의 착지 팩터가 미등록(검증 에러→부분 컴파일 드롭으로 생존)에서 등록 팩터(검증 통과→전량 컴파일 폭발)로 이동하며 발현. 온도 0에서 결정적 재현). 검증 에러가 있으면 부분 컴파일이 해당 조건만 제외하고 "'…' 조건은 전략에 반영하지 못했어요" 안내를 붙인다. ③ **미러와 실제 발화를 구분한다** — 역할 위반 청산 조건이 진입에 이미 있는 팩터의 복제이면서 원문 근거(`source_text`)가 없으면 9B 미러 드리프트로 보고 **에러·안내 없이** 검증이 제거한다(진입에 정상 반영된 같은 지표가 "반영하지 못했어요"로 읽히던 실측 혼란, 2026-08-05 2차 수정). 원문 근거가 있거나 진입에 없는 팩터는 사용자가 실제로 말한 청산일 수 있으므로 ②의 에러+안내 경로를 유지한다(조용한 누락 금지). 회귀: `backend/tests/test_strategy_conversation.py`(risk 필드 흡수 2건, 미러 무안내 정규화 1건, 실발화 재무 청산 안내 1건).

**FR-STR-019u** [명시한 매매 규칙의 조용한 소실 차단, 2026-08-05] 전수 예시 QA(81개)가 드러낸 규칙 소실 3종을 각 레인의 원인에서 수정한다. ① **자기 선(線)을 둘 가진 지표의 부등호는 임계값을 요구하지 않는다** — `technical.ema`의 `>`·`<`는 "5일 EMA가 20일 EMA 위/아래"라는 두 선의 관계이고 컴파일러도 값 없이 `mode`(above/below)로 바인딩한다(`_compile_technical`). 완결성 검증이 이를 임계값 누락으로 보면 조건이 값 미정으로 제외돼 사용자가 명시한 진입·청산이 통째로 사라진다. 판정 기준은 spec에 `short_period`·`long_period`가 함께 있는지다. ② **미러 복제 판정은 방향으로 한다** — 반대 방향 청산은 교차(`crosses_*`)뿐 아니라 부등호로도 표현되므로(`>` 진입 / `<` 청산), 예외를 이벤트 연산자에만 열어 두면 정당한 청산이 미러로 오인돼 삭제된다. 연산자를 up/down으로 환산해 진입 방향과 다르면 새 정보로 보존한다(같은 방향 복제는 종전대로 삭제). ③ **되묻기 판정은 값이 담긴 버킷을 모두 본다** — 거래대금은 `fundamental.trading_value`(필터)와 `technical.trading_value`(신호) 두 정본을 가지며 후자로 해석되면 값이 `entry_signals`에 담긴다. 필터 버킷만 조회하면 사용자가 이미 준 값을 다시 묻는다(값이 없는 신호는 종전대로 되묻는다). 부수: LLM이 내는 낱말 연산자(`above`/`below`/`golden_cross`)를 정본 표기로 형식 정규화하고(`_OPERATOR_ALIASES` — 표기만 보고 결정 가능한 동의어), 프롬프트에 예시 4-6(재무 여러 개 뒤에 오는 숫자 없는 기술 신호)·4-7(진입과 반대 방향 청산, 정본 연산자 표기)을 추가해 리콜 누락을 LLM 레인에서 잡는다(PROMPT_VERSION 2.7). 회귀: `test_strategy_conversation.py`(반대 방향 청산 보존, 자기 선 비교 무임계값), `test_nl_parser_overrides.py`(값 있는 신호 인정, 값 없는 신호 되묻기 유지).

**FR-STR-019v** [스칼라 슬롯 미러 흡수 전면화, 2026-08-06] FR-STR-019t ①의 흡수 판정을 risk_management 정확 표기에서 **스칼라 설정 슬롯 전체**로 넓힌다(`interpreter/models.py::_absorb_scalar_slot_conditions` + `_scalar_slot_target`). 배경 사고 2건: 인터프리터가 `portfolio.hold_period_days=25`를 정상 반영하고 **같은 사실을** 조건 목록에 factor=`hold_period_days`(맨 이름)·`portfolio.hold_period_days`로 한 번 더 실어, Registry 부재로 컴파일에서 드롭된 복제가 "'보유는 최대 25거래일' 조건은 전략에 반영하지 못했어요"라는 **거짓 미반영 안내**를 만들었다(40거래일 케이스 동일). 트레이스 전수 조사(4일치 조건 관측 2,366건)에서 Registry 밖 factor는 7종뿐이고 6종이 이 미러였다: `risk_management.stop_loss`(1)·`stop_loss`(8)·`fundamental.stop_loss`(4, 오염 네임스페이스)·`portfolio.hold_period_days`(8)·`hold_period_days`(8)·`time.days_held`(16, 프롬프트 금지에도 출력). 나머지 1종(`technical.beta`)만 진짜 미지원 개념으로 안내가 정당하다. 계약: ① 판정 대상은 risk_management·portfolio·backtest 세 스펙의 필드 — 네임스페이스 정확 표기, 유일한 맨 이름, 그리고 마지막 세그먼트 재조회(오염 네임스페이스 대응. Registry 정본 id 68종의 마지막 세그먼트와 무충돌 확인). 동의어 `days_held`/`max_holding_days`→`portfolio.hold_period_days`는 표기만으로 결정 가능한 형식 정규화다. ② 맨 이름 `period`는 제외 — 지표 파라미터 이름과 겹쳐 흡수하면 사용자가 말한 적 없는 백테스트 창을 지어낸다. ③ 값 흡수는 대상 스펙의 자체 검증(`model_validate`)을 통과할 때만 — RiskSpec 크기 규약·BacktestSpec 버킷 정규화가 그대로 적용되고, 검증 실패 값은 흡수하지 않고 조건으로 남겨 안내 레인으로 보낸다. ④ 값도 없고 슬롯도 비어 있으면 제거하지 않는다(조용한 누락 금지 — 종전과 동일). universe(리스트형)·ranking 미러는 관측 0건 + ranking 정본 팩터는 capability_validator가 이미 ranking 배열로 정규화하므로 이번 범위 밖. 회귀: `test_strategy_conversation.py` 7건(맨 이름·빈 슬롯 흡수·backtest 흡수·`period` 비흡수·무값 보존·`time.days_held`·오염 네임스페이스).

**FR-STR-019w** [되묻기 질문 문구·칩의 단일 정본 + 표현 통일, 2026-08-16 사용자 지시] 사용자에게 던지는 **질문의 문구와 선택지 칩**은 `backend/engine/strategy_slots.py` 하나가 authoring해야 하며(FR-STR-019m이 *판정*을 모은 것과 같은 계약의 문구 판), 질문은 경로와 무관하게 **같은 되묻기 카드(박스)** 로 표시해야 한다. 배경: 같은 유니버스 질문 하나가 네 벌로 갈려 있었다 — ① 정본 표(`_QUESTIONS`, 칩 2개) ② 프론트 게이트 표(`backtestReadiness.SLOT_PROMPTS`, 칩 4개) ③ 빌더(`intent/strategy_builder.next_question`, 칩 5개) ④ 렌더 직전 치환표(`makeBuilderQuestionFriendly` — ①②의 문장을 통째로 다른 문장으로 갈아끼움). ④ 때문에 **표에 적힌 문구가 화면 문구가 아니었고**, 한쪽만 고치면 치환이 조용히 빗나가 낡은 문구가 나갔다. 표시도 갈렸다 — 게이트 질문은 박스 카드(하단 고정·'대화 종료' 포함), 빌더 질문은 맨 텍스트+칩이라, 열린 추천(STRATEGY_PICK)으로 들어온 사용자는 같은 성격의 첫 질문을 다른 모양으로 받았다. 계약: ① **문구 정본은 백엔드 하나** — `_QUESTIONS`(슬롯 9종) + `BUILDER_QUESTIONS`(빌더 세부 질문)가 **화면에 나갈 최종 문구**를 그대로 담고, 상황별 변형(분위 그룹·랭킹의 '최대 보유')도 같은 표의 변형 항목이다(`slot_question(field, variant)`). ② **프론트는 정본이 생성한 픽스처만 읽는다** — `scripts/export_slot_prompts.py` → `app/analytics/new/__fixtures__/slot-prompts.json`, 최신성은 `test_strategy_slots.py::test_frontend_prompt_fixture_is_current`가 잠근다(판정 픽스처 `slot-judgments.json`과 같은 방식). 픽스처는 손으로 고치지 않는다. ③ **칩 어휘는 두 레인의 답 해석기가 모두 읽을 수 있어야 한다** — 빌더 레인(`strategy_builder._parse_*`)과 게이트 레인(프론트 `deterministicConditionFlow`). 한쪽만 읽는 표기를 넣으면 그 레인에서 클릭이 조용히 LLM 왕복으로 떨어진다. 통합 결과 유니버스 칩은 5종(코스피·코스닥·코스피200·코스피·코스닥 전체·ETF), 리밸런싱·손절·익절 거부 칩은 자기완결 표기(`리밸런싱 안 함`·`손절 안 함`·`익절 안 함`)로 통일한다(카드가 하단에 고정되면 질문과 칩이 떨어져 "안 함"만으로는 무엇을 거부하는지 알 수 없다). 이전 표기는 프론트 해석 맵에 별칭으로 남긴다(세션에 남아 있던 이전 질문의 칩도 같은 결과여야 한다). ④ **'직접 입력'은 답이 아니라 UI 토글**이므로 어느 표에도 넣지 않는다 — 프론트 `withBuilderNavigationSuggestions`가 붙이며, 유니버스처럼 선택지가 닫힌 슬롯에는 붙이지 않는다. 되묻기 카드는 빌더 질문에 자유 입력 칩을 **덧붙이지 않는다**(두 판정이 겹치면 닫힌 선택지에 '직접 입력'이 되살아난다). ⑤ **빌더 질문은 되묻기 채널로 나간다** — `clarification`/`clarificationSuggestions`(안내문·연구 지표 도입부 같은 질문 아닌 앞말만 `infoText`). 채널을 모으면 박스·칩 규칙·하단 고정·'대화 종료' 배치가 저절로 같아진다. 되묻기 카드는 `msg.parsed` 유무와 무관하게 그려야 한다(빌더 턴에는 아직 전략이 없다). 부수 효과: 카드는 **지금 답할 질문 하나만** 그리므로 답이 끝난 빌더 질문은 대화에서 사라진다(게이트 레인의 기존 동작과 동일 — 정해진 내용은 '현재까지 이해한 전략입니다' 요약 카드가 잇는다). ⑥ **빌더 질문의 답은 빌더가 받는다** — 두 레인의 칩이 같은 필드에 담기므로 `handleSuggestionClick`이 `builderQuestion`으로 갈라놓지 않으면 게이트의 결정론 적용이 빌더 단계의 답을 가로채 State가 갈라진다. ⑦ **어느 질문인지의 판정은 문구 대조로** 한다 — 문구 안의 낱말("청산 조건"·"리밸런싱")로 보면 정본이 표현을 바꾸는 순간 판정이 조용히 헛돈다(테스트 포함). 회귀: `test_strategy_slots.py`(픽스처 최신성, 빌더·게이트 문구 동일성), `page.strategy-pick-notice.test.tsx`(열린 추천 경로의 첫 질문이 박스 카드로 나가고 안내문은 카드 밖). **[2026-08-16 2차 — 빌더 '전략 유형' 질문 폐지]**: 1차 통합 후에도 빌더는 매수 조건 자리를 자기 질문("어떤 방식으로 종목을 고를까요?" + 유형 설명 불릿 8줄 + 유형 이름 칩)으로 물어, 사용자가 같은 슬롯을 경로에 따라 전혀 다른 화면으로 받았다(불릿과 칩이 같은 목록의 중복 표기이기도 했다). 빌더의 전략 유형 단계를 없애고 ENTRY 슬롯 질문·칩을 그대로 쓴다. ⑧ **칩 어휘 통일이 불가능한 지점을 결속으로 푼다** — 정본 칩을 빌더 정규식에 다시 통과시키면 표기 겹침으로 오분류된다(실측 3종: 'MACD 골든크로스 매수'→golden_cross, '골든크로스(5일/20일)'의 5→모멘텀 기준 기간, 'PER 10 이하'→미인식 무한 재질문). 어휘를 덧붙여 가려내는 것은 대원칙 1이 금지하는 방향이고 겹침도 남는다. 그래서 칩=값 결속 계약대로 **클릭을 재해석하지 않고** 발행 시 정해진 값을 적용한다(`strategy_builder._ENTRY_CHIP_PATCHES`, 정확 일치만·성립하지 않아 내놓지 않은 칩은 결속 거부). 값은 게이트 레인의 결속과 **같은 전략**이 되도록 맞춘다 — 게이트가 엔진 기본값에 맡기는 파라미터(이동평균 종류·RSI 기간·OBV 기간)도 함께 결속해, 같은 칩이 경로에 따라 다른 전략이 되지 않게 하고 빌더가 뒤이어 되묻지도 않게 한다. ⑨ **빌더 상태가 표현할 수 없는 칩은 자유 서술로 넘긴다** — 재무 조건(PER·ROE)은 `BuilderState`에 자리가 없으므로 `strategy_type=custom` + `entry_rule`로 두어 프론트가 파서 레인으로 보낸다(칩을 목록에서 빼면 다시 두 벌이 된다). ⑩ **모멘텀(상위 K)은 정본 목록에 합류한다** — 빌더에만 있던 선택지라 통합 시 사라질 뻔했다. 게이트 레인도 같은 칩을 쓰므로 랭킹 결속(`ranking_metric`·`ranking_lookback_days`)을 프론트 결정론 적용에 추가한다. ⑪ **성립하지 않는 선택지만 정본에서 뺀다**(`strategy_slots.entry_chips` — ETF는 기업 재무 칩 제외, 단일 종목은 횡단면 랭킹 제외). 레인별 목록을 새로 만들지 않는다. ⑫ **되돌아가기는 답이 아니라 컨트롤**이므로 칩 목록에서 빼고 되묻기 카드 우상단 '돌아가기' 버튼으로 통일한다(게이트 레인과 같은 자리). 회귀 추가: 정본 칩 전수 결속·소화 보증(백엔드/프론트 양쪽), ETF·단일 종목 제외 목록, 돌아가기 버튼. **[2026-08-16 3차 — 매도 칩을 매수 칩의 반대로]**: ⑬ 같은 슬롯 쌍(매수·매도)의 선택지는 **서로 뒤집은 짝**이어야 한다(사용자 지시). 매도 칩 3종만 있던 것을 매수 칩과 같은 순서의 미러로 채운다 — 골든크로스→데드크로스, RSI 과매도→과매수, MACD 골든→데드, 볼린저 하단→상단, 고점 돌파→저점 이탈(대응 없는 '20일 보유 후 청산'은 기간 기반 청산이라 끝에). 문구만 맞추면 '반대'라는 설명이 거짓이 될 수 있으므로 **두 칩이 실제로 결속되는 값을 대조**해 지표·기간이 같고 방향만 다른지 회귀로 고정한다. ⑭ **미러를 넣지 못하는 세 경우와 그 이유**: 거래량 급증 — 엔진은 OBV 하락 전환 매도를 지원하나 파서에 그 매도 표현이 없어 칩이 값에 결속되지 않는다(결속 안 되는 칩은 planner ask 경로에서 조용히 사라져 같은 슬롯이 경로마다 다른 선택지를 보인다. 어휘를 덧붙여 결속시키는 것은 대원칙 1 금지 방향이므로 하지 않는다) / 모멘텀 상위 — 랭킹 전략의 청산은 매도 신호가 아니라 리밸런싱 편출이다(FR-BT-015b) / PER·ROE — 재무 지표는 청산 조건이 될 수 없다(역할 검증, FR-STR-019t ②). 노출하는 매도 칩이 **하나도 빠짐없이** 결속되는지를 회귀가 지킨다.

**FR-STR-020c** `correctedStrategy`의 `universe` 필드는 원문 기준 결정적 추출(`_extract_explicit_universe`)과 다르면 항상 결정적 추출값으로 되돌려야 한다. 유니버스는 KOSPI/KOSDAQ/KOSPI200 어휘 매핑일 뿐이라 교정 LLM이 개선할 여지가 없고, 되돌리지 않으면 유니버스 확대로 인한 심각한 성능 저하만 남는다(단, `max_positions` 등 숫자 필드의 정당한 교정은 그대로 존중한다). (실사례 2026-07-05: "KOSPI 대형주 중에서 PBR이 1배 이하인 종목..." 프롬프트가 룰 파싱 잔여 미해석으로 LLM 검증을 타고, 교정본이 유니버스를 KOSPI200→KOSPI로 되돌려 200종목이 전체 코스피(800+ 종목)로 확대 → 백테스트가 크게 느려져 전략연구소 화면이 멈춘 것처럼 보임.)

**FR-STR-020d** SSE 파싱 경로(`/strategy/parse-stream`)에서 LLM 검증은 비차단(후행)이어야 한다: 룰 파스 결과를 먼저 `result` 이벤트로 전송하고, 검증은 스트림을 연 채 후행 실행하며(`_run_nl_parse`의 defer_holder → `_complete_deferred_validation`), 교정이 적용된 경우에만 `result_update` 이벤트로 갱신본을 후속 전송한다. 파싱 캐시도 교정본으로 갱신해 동일 프롬프트 재요청이 교정 전 결과를 반환하지 않아야 한다. 후행 검증 중에는 `validating` stage 이벤트를 보내지 않아야 하며(프론트가 로딩 표시로 되돌아가 요약이 사라지는 회귀 방지), 프론트(`parsed_updated` 이벤트)는 사용자가 이미 백테스트를 실행/완료한 뒤 도착한 교정은 무시해야 한다(실행 스냅샷 일관성). 후행 검증 대기는 프록시 스트림 예산(120s) 미만으로 상한을 두고 초과 시 결과를 폐기한 채 스트림을 닫는다. 비스트림 `/strategy/parse`는 인라인 검증을 유지한다.

**FR-STR-021** 시스템은 "최근 N일/N거래일/N개월 수익률이 높은 종목 상위 K개"와 같은 상대강도(모멘텀) 랭킹 표현을 인식하여 `ranking_metric="return"`과 `ranking_lookback_days`(미지정 시 60일 기본)를 추출해야 하며, 랭킹 전략에 리밸런싱 주기가 명시되지 않은 경우 `monthly`를 기본값으로 적용해야 한다. 단, 회전 수단이 없는 펀더멘털 스크리닝 전략의 기본 월간 리밸런싱은 사용자가 리밸런싱을 명시적으로 거부한 경우("리밸런싱 없이 계속 보유")에는 주입하지 않고 `none`(매수 후 계속 보유)으로 보존해야 한다 — 랭킹 전략은 회전이 달력 리밸런싱으로만 동작하므로(엔진 제약) 거부 표현이 있어도 유지한다.

**FR-STR-022** 시스템은 진입 의도가 있는 자연어 입력에서 파싱 결과에 진입 신호/펀더멘털 필터/랭킹 기준이 모두 비어 조용히 누락된 경우, 사용자에게 명확화 질문과 대안 제안(클릭 가능한 칩)을 표시해야 한다. 이때 일반적인 누락 사례와 "엔진이 아직 지원하지 않는 상대강도 랭킹 표현" 사례를 구분하여 각각 다른 안내 문구와 대안을 제공해야 한다 (서로 다른 원인이므로 동일한 메시지로 뭉뚱그리면 안 됨). 첫 파싱에서는 백엔드가 보낸 구체적 안내를 우선 사용한다. [2026-07-19 확장] ETF 유니버스 전략("etf를 사는 전략은 어때?")도 별도 사례로 구분한다 — ETF에는 개별 기업 재무지표(PER·PBR·ROE)가 없으므로 재무 필터 예시 칩(일반 안내)을 그대로 보여주면 오답이며, ETF에 통용되는 가격·추세 기반 방식(이동평균 추세추종·모멘텀/신고가 돌파·RSI 평균회귀·MACD·정기 리밸런싱)의 예시 칩으로 진입 조건을 묻는다(`nl_parser._ETF_PRODUCT_QUESTION`). 임계값 되묻기("PER은 몇 이하로 할까요?")보다 이 안내가 우선하며, 기술 신호가 이미 추출된 경우에는 되묻지 않고 그대로 실행한다(ETF는 정식 지원 유니버스 — FR-STR-067). ETF 전략에 기업 재무지표가 실제로 섞인 경우는 FR-STR-067 ④의 충돌 되묻기가 먼저 가로챈다. [2026-07-21 확장] `etf_theme`가 특정 ETF 상품명과 정확히 일치하는 경우("kodex 반도체 etf를 매수"→etf_theme="KODEX 반도체")는 "여러 ETF 중 고르는" 뉘앙스의 일반 문구(`_ETF_PRODUCT_QUESTION`의 '정기 리밸런싱' 등) 대신, 상품명·종목코드를 확정해 보여주는 전용 문구(`_ETF_PRODUCT_QUESTION` → `_ETF_SINGLE_PRODUCT_QUESTION`, `universe_pit.resolve_single_etf_product`로 정확 매칭 판정)로 되묻는다 — 이미 단일 상품이 지정됐는데도 열린 테마처럼 되물어 "또 어떤 ETF를 살지 묻는다"고 오인하는 사고를 방지한다("반도체" 같은 열린 테마 키워드는 그대로 일반 문구를 유지).

**FR-STR-023** 시스템은 매수(종목 선정) 기준이 전혀 없는 전략(진입 신호·펀더멘털 필터·랭킹 기준이 모두 비어 백테스트가 0매매로 끝나는 경우)에 대해 백테스트 실행을 막아야 한다. 이 판정은 실제 백테스트로 전달되는 병합된 전략을 기준으로 하므로 최초 파싱뿐 아니라 점진적 수정 이후에도 적용되어야 하며, 매수 기준이 빠진 상태에서는 "백테스트 실행" 버튼을 노출하지 않고 최소 조건을 입력하도록 명확화 안내를 표시해야 한다. (청산·리스크 설정만으로는 살 종목을 선정할 수 없으므로 매수 기준으로 인정하지 않는다.)

**FR-STR-023b** 백테스트 결과 화면의 "프롬프트" 배지(진입 신호 / 청산 신호)는 사용자가 정의한 전략 요약을 그대로 표시해야 한다 — 진입 신호 섹션은 `entryBlocks`(진입 신호·펀더멘털 필터)만 렌더링하고, 비어 있으면 섹션을 숨긴다. 진입 신호·청산 신호가 섞인 `blockNames` 폴백으로 떨어져선 안 된다(매수 기준 없이 익절만 있는 전략에서 청산 배지가 진입에 누출되던 버그 방지). 이는 표시 전용이며 백테스트 엔진은 진입 조건을 `fundamental_filters`+`entry_signals`로, 청산 조건을 `exit_signals`로 분리해 구성하므로(`strategy_converter.to_backtest_request`) 실행 DSL에는 누출이 없다.

**FR-STR-023c** 시스템은 전략 설정값의 하한선을 강제해야 한다(`enforce_strategy_minimums`, 규칙/LLM/수정 모드 무관 모든 파싱 경로 뒤에서 적용). 하한 미만 입력은 자동 보정/제거하고, 사용자에게 보정 내용을 전략 요약과 함께 비차단(non-blocking) 방식으로 안내해야 한다. 안내는 매수 기준 명확화(`clarification`)와 달리 전략 요약 카드를 숨기지 않는다(`notices` 채널).

**FR-STR-023d** 시스템은 스키마(`ParsedStrategy`)가 표현할 수 없는 미지원 개념(배당·섹터·변동성·수급·분할매도·거래량 배수("평소 대비 N배" — `volume_spike`는 OBV 크로스오버라 배수 임계값 표현 불가) 등, `nl_parser._UNSUPPORTED_CONCEPT_PATTERNS`)이 프롬프트에 언급되면, LLM 폴백 위임(부분 파싱 침묵 누락 방지)과 별개로 사용자에게 해당 조건이 "아직 직접 지원되지 않아 반영되지 않았거나 다르게 해석됐을 수 있다"는 안내를 `notices` 채널로 제공해야 한다(`build_unsupported_concept_notice`). LLM 폴백조차 스키마 제약으로 이 개념들을 정확히 표현할 수 없으므로, 조용한 유사 해석 대신 명시적으로 알리고 전략 요약 확인을 유도한다. [2026-07-14 확장] 데이터 파이프라인이 없는 흔한 퀀트 팩터도 같은 채널로 안내한다: ROIC(투하자본이익률), 베타, 이자보상배율, 피오트로스키/알트만 점수, 회전율(재고·매출채권 등), 자사주 매입, PCF/주가현금흐름(기존 cash_flow 항목 확장). (ETF/ETN은 2026-07-19 같은 날 잠시 `etf_product` 항목으로 이 목록에 추가되었다가 ETF 정식 유니버스 승격(FR-STR-067)으로 즉시 제거되었다 — 개념 구현 시 목록에서 제거하는 원칙의 적용 사례.) **단 EV/EBITDA(에비타)는 KIS other-major-ratios 배선(2026-07-14)으로, 배당수익률·배당성향·배당성장률은 KIS 예탁원 배당 API 배선(2026-07-14)으로 데이터가 확보되어 지원 지표로 승격되었으므로 미지원 목록에서 제거되었다**(수치 있는 배당수익률/배당성향/배당성장률 필터가 추출되면 `배당` 안내를 억제하는 조건부 제외 방식 — 수치 없는 막연한 '배당주/배당 성장주' 언급만 미지원 안내 유지) — 데이터 파이프라인 구현 시 목록에서 제거하는 원칙의 실제 적용 사례. 이 안내는 최초 파싱과 수정 요청 모두에 적용된다(`_build_parse_result` 공유). 지원 지표(영업이익률·순이익률·매출총이익률 등 마진류)는 절대 미지원 목록에 넣지 않는다(오폴백 방지) — 해당 팩터의 데이터 파이프라인을 구현하면 목록에서 제거해야 한다. [2026-07-24 확장 — 흑자/적자 승격] 흑자/적자 '여부'(`profitability_sign`)는 parquet의 연간 `eps` 컬럼으로 표현 가능해 지원 지표로 승격되었다: "흑자 기업"·"적자 제외/아닌"→`eps > 0`, "적자 기업만"→`eps < 0`을 값 없는 키워드 조건으로 결정적으로 추출한다(`nl_parser._keyword_profitability_operator` — 흑자 여부를 순이익증가율(net_income_growth)로 바꿔 해석하는 것은 부호 조건≠변화율 조건 오귀속이므로 금지, LLM 폴백 프롬프트에도 명시). 단 ① 흑자전환·적자탈출·N년 연속 흑자 같은 부호 전환/연속(시계열) 표현은 단일 시점 부호 필터로 왜곡되므로 emit하지 않고 미지원 안내로 남기며(목록 제거가 아닌 조건화 — 항목명 `profitability_transition`, 추출 가드와 동일 패턴 공유), ② "영업활동현금흐름이 흑자"·"영업이익 흑자"처럼 순이익이 아닌 항목의 부호 언급은 키워드 직전 문맥 가드로 eps 바꿔치기를 차단하고 LLM에 위임한다. 아울러 백테스트 전 결정적 검증(`ai/strategy_validation_agent.py`)의 지원 조건 화이트리스트는 재무 지표를 하드코딩 사본이 아니라 엔진 SOT(`engine.signals.FUNDAMENTAL_CIDS`)에서 직접 파생해야 한다 — 사본 드리프트로 엔진이 지원하는 순이익증가율이 "지원하지 않는 필드"로 오탐 차단되던 사고의 재발 방지(회귀: `test_engine_supported_metrics_are_not_flagged_unsupported`). [2026-07-29 확장 — 보유 기간 하한] `hold_period_days`는 **만료 시 강제 청산(상한)**만 표현한다. "최소 보유 기간은 3개월"·"최소 6개월은 들고" 같은 **하한**(그 전에는 팔지 않기)은 반대 개념이므로 상한으로 뒤집어 확정하지 않고(`_MIN_HOLD_PERIOD_PATTERN`으로 추출 제외) 미지원 개념(`min_hold_period`)으로 안내한다 — 예시 카드 "부채비율·ROE 보유 조건"의 '최소 보유 기간 3개월'이 요약에 "최대 63일 보유 후 매도"로 표기되던 2026-07-29 사고. 인터프리터 프롬프트(v2.0)에도 같은 계약을 명시했고(하한은 `unsupported_features`), 패턴은 보유 동사·'보유 기간' 명사가 붙은 형태만 잡아 "최근 3개월 이상 상승"(모멘텀 룩백)을 오탐하지 않는다. [2026-08-01 확장 — 표현된 개념은 안내에서 뺀다] 미지원 개념 어휘가 언급됐어도 **컴파일 결과가 그 개념을 실제로 표현했으면** 안내를 내지 않는다(`concepts_expressed_in_strategy` — 섹터·배당의 조건부 제외와 같은 계약, 판정 입력은 컴파일 결과와 입력 **수치**뿐이며 원문 어휘를 다시 읽지 않는다). ① `cash_flow` — 현금흐름 '수준/흑자 여부'는 여전히 미지원이지만 증가율(`ocf_growth`·`fcf_growth`)은 지원 지표이므로, 그 필터의 임계값이 **입력 수치에 있으면**(§ 3-1 수치 대조) 안내를 뺀다. 임계값이 입력에 없으면(예: '현금흐름이 흑자' → `ocf_growth>=0`) 인터프리터가 지어낸 유사 대체이므로 안내를 유지한다 — 조용한 의미 변경 방지. ② `ema_alignment` — '정배열'은 두 선의 상하 관계(crossover 표기, 프롬프트 규칙 5-3)로 표현되므로 전략에 이동평균 비교 신호가 있으면 안내를 뺀다(세 선 이상 나열의 부분 표현은 이 술어가 구분하지 못한다 — 알려진 한계). 아울러 인터프리터의 `unsupported_features`를 그대로 인용하던 **파싱 경로 안내는 폐지**했다(사용자 판단): LLM 자유 서술 채널이라 내부 사정("unsupported_features에 기록합니다")·지원되는 필드명(`risk_management.stop_loss`)·발화 조각이 그대로 노출됐고, 미지원 개념 안내는 이 결정론 게이트가 이미 담당한다. 조용한 누락 방지는 제외 조건 안내(결정론 대조)가 맡는다(미반영 수치 안내는 2026-08-01 폐지 — FR-STR-019j ⑤). 수정 경로의 미반영 안내(FR-SA-019)는 그대로 유지된다 — 그쪽은 전략이 그대로인 이유를 말하는 유일한 채널이다. [2026-08-12 — 잔여 미지원 안내 부활(가드 부착), 사용자 결정] 무필터 인용 폐지 후 **목록 밖 새 개념**(34개 패턴에 없고, LLM이 조건으로 뽑지도 되묻지도 않고 `unsupported_features`로만 보고한 개념)이 어떤 안내도 없이 사라지는 틈이 남았다. 파싱 경로에 수정 레인(FR-SA-019)에서 검증된 가드를 얹어 한정 부활한다(`strategy_conversation/primary.py` 잔여 미지원 안내 블록): ① 발화 전체 에코 오라벨이면 침묵(`_reported_features_echo_input`) ② 내부 식별자는 평이화(`_humanize_features`), 스키마 필드 경로(`technical.beta` 등)는 제외(그 조건의 탈락은 제외 조건 안내가 source_text로 이미 알린다) ③ `_UNSUPPORTED_CONCEPT_PATTERNS`(34개)에 매칭되는 항목은 제외 — 그 목록의 안내와 의도적 억제(이미 반영·값 대기)는 이 결정론 게이트 소관이라 다시 내면 중복이거나 오탐 부활이다. **영문 개념 ID 표기('volatility' 등)도 같은 제외 대상**이다 — LLM이 한글 대신 ID로 보고하면 한글 패턴을 뚫고 결정론 게이트 안내와 중복된다(섀도 대조 실측, 회귀 `test_primary_unsupported_concept_id_token_excluded`) ④ 되묻기 질문·이월 큐·기존 notices·값 대기 라벨이 다루는 항목은 제외(모순 방지). 판정 입력은 전부 LLM 출력·자기 응답 문자열이다(라벨 정규식 매칭은 `concepts_covered_by_pending`과 같은 계약 — 원문을 읽지 않는다). 통과한 잔여 중 이름이 길이 상한(25자, `_QUOTED_FEATURE_MAX_LEN`) 이하인 항목만 "'X' 조건은 지원하지 않아 전략에 반영하지 못했어요"로 지목하고, **상한 초과 발화 조각은 지목 없이 "말씀하신 조건 중 일부는 지원하지 않아 전략에 반영하지 못했어요"로 뭉뚱그린다**(2026-08-12 사용자 결정 — 레드팀 실측 3-4의 자기 말 반 토막 인용 방지, 회귀 `test_primary_unsupported_long_fragment_not_quoted`). [2026-08-13 — 인터프리터 미지원 보고 일관성 + 모순 라벨 강등] 섀도 대조 반복 실측으로 두 가지를 확정했다. ① **프롬프트 v3.5**: 규칙 3에 유사 대체 금지(ROIC→ROA·흑자전환→eps 부호·시장 대비→수익률 랭킹·현금흐름 흑자→증가율·우선주→보통주·일부 익절→전량 take_profit)와 자주 놓치는 미지원 개념 목록을 명시(보고 17→45건/64). 단 **프롬프트 분량 임계 실측**: 규칙을 더 늘리자 복합 정상 입력("PER 10 이하이고 ROE 15%…")의 출력 JSON이 바깥 객체를 닫지 않고 조기 종료했다 — 대조 예시 블록을 제거·압축해 해소했고, 하니스 `_control` 대조군 4건이 재발을 감시한다. ② **UNSUPPORTED_REQUEST 모순 라벨 강등**(`strategy_conversation/primary.py`): 라벨 정의·규칙·대조 예시 세 차례 프롬프트 반복으로도 9B가 미지원 개념 섞인 전략 서술을 UNSUPPORTED_REQUEST로 밀어내는 드리프트가 고정되지 않아(15/64), 구체 미지원 개념 보고(역할 밖 행위 보고 제외 — 종목 추천·시장 전망·전략 우열은 거절 유지)가 있으면 CREATE_STRATEGY로 강등하고 CREATE 레인으로 재검증한다. 전략 골격이 없으면 빈 골격으로 진행해 "지원하지 않아요 안내 + 조건 되묻기" 턴이 된다. 최종 성적(하니스 68케이스): 해석 실패 0(개선 전 8), LLM 레인 잔여 격차 2건(현금흐름 흑자 여부·ROIC — 결정론 게이트가 커버, **게이트 유지 근거**). 회귀 `test_primary_unsupported_request_label_demoted_with_concrete_features` 외 2건, 하니스 `scripts/qa_unsupported_shadow.py`. 회귀: `test_primary_notices_unlisted_unsupported_feature` 외 4건. [2026-08-13 — 이중 기입 허위 신고 수정, 프롬프트 v3.6] 9B가 '최대 보유 기간은 20거래일'을 `hold_period_days=20`에 정상 반영하고도 같은 표현을 `unsupported_features`에 이중 기입해, 잔여 미지원 안내가 "반영됐는데 지원하지 않는다"는 모순 안내를 냈다(temperature 0 결정적 재현). 절제 실험으로 유발원을 확정: 규칙 3 목록·규칙 5 끝의 '**최소** 보유 기간=미지원' 언급에 모델이 사용자의 '최대'를 혼동해 끌려갔다(수치 체크리스트는 원인 아님). 수정은 규칙 4-1에 이중 기입 금지 일반 규칙("이미 필드·조건에 값으로 반영한 표현은 지원된 것 — `unsupported_features`에 다시 넣지 않는다, 한 표현은 한 곳에만")을 추가 — 지원/미지원 근접 쌍 클래스 전체(최대/최소 보유 기간, 신고가/신저가 등)를 커버한다. 실측: 사고 입력 허위 신고 소멸 + '최소 보유 기간' 입력의 미지원 신고·`hold_period_days` 미오염 유지 + 예시 카드 40거래일 복합 입력 정상. 회귀 `test_interpreter_prompt_forbids_double_entry_of_reflected_expressions`. [2026-08-14 — 값-대기 이중 기입 차단] 같은 이중 기입이 **값-대기 조건**에서도 재현됐다(예시 '매출성장·PBR 추세 조건'): LLM이 `pending_conditions`에 올린 조건을 `unsupported_features`에도 **사용자 표현**("매출 성장률이 양호하고")으로 함께 신고해, 라벨("매출액증가율") 기준 제외를 뚫고 "지원하지 않아 전략에 반영하지 못했어요"라는 거짓 안내가 값 확인 대기 중인 조건에 붙었다. 잔여 미지원 안내의 제외 조건에 **`pending_conditions[].source_text` 포함 대조**를 더한다(`_covered_by_pending_texts` — 4자 미만 조각은 우연 일치가 잦아 제외, 판정은 LLM 출력 ↔ 자기 응답 채널의 표기 대조뿐이다). 미반영 **수치** 안내 폐지(FR-STR-019j ⑤)는 그대로 유지된다. [2026-08-10 — 변동성 승격] 변동성은 FR-BT-061(연환산 변동성 필터·저변동성 랭킹, 엔진 v13.1)로 지원 지표로 승격되었다. 다만 결정적 추출기는 여전히 변동성을 표현하지 못하므로 '변동성' 큐는 LLM 위임 신호로 목록에 남기고(PCR과 동형), 전략에 반영되면 `concepts_expressed_in_strategy`의 volatility 술어(ranking_metric='volatility' 또는 volatility 신호 존재)가 안내를 억제한다.
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

**FR-STR-030b** [하락 방향 비율 표기 — 항상 마이너스, 2026-07-30] `stop_loss_pct`·`trailing_stop_pct`는 하락 폭의 **크기**로 저장·검증되지만(양수 정규화, § 손절·익절 검증) **표시는 항상 마이너스 부호를 붙여야 한다**("손절 -8%", "트레일링 스탑 -10%") — 부호 없는 "손절 8%"는 방향이 드러나지 않아 익절과 구분되지 않는다(사용자 지적 2026-07-30: 매도 조건 라벨은 "손절 -8% 하락시 매도"인데 같은 카드의 리스크 관리 라벨만 "손절 8%"였다). ① **표시 경로**: 대화 진행 요약 카드(`builderProgressPresentation`), 파싱 카드 리스크 배지(`/analytics/new`), 결과·저장 요약의 `riskText`(`lib/strategy-summary.ts` 4경로), 빌더 확인·삭제 안내(`intent/strategy_builder.py`), 인터프리터 전략 복창(`strategy_conversation/response/responses.py`). 프론트는 단일 포매터(`formatDownsidePercent`)가 부호를 붙이며 이미 음수인 값에 중복 부호를 붙이지 않는다. ② **선택지 칩도 같은 표기**를 쓴다("손절 -10%", "손절을 -5%로 변경", 빌더 "-10% 손절") — 되묻기 문구와 칩이 어긋나면 사용자가 부호를 값의 일부로 오해한다. **부호는 표기일 뿐 값은 크기다**: 칩 결속(`primary._bind_chips` → `_apply_prompt_overrides`)·프론트 결정론 적용(`deterministicConditionFlow.parseFirstNumber`)·빌더 청산 파서 모두 "-10%"에서 `10.0`을 뽑는다(부호 보존 금지 — 엔진은 크기를 받는다). 칩 정본은 `engine/strategy_slots.py`(슬롯 되묻기), `intent/strategy_builder.py`(빌더 청산 단계), `conversationDecision.ts`(값 없는 수정 되묻기), planner 프롬프트의 칩 예시다. ③ **부호를 붙이지 않는 것**: 익절·MDD 한도·보유기간, 방향이 이미 문구에 있는 라벨("최고가 대비 10% 하락 시 청산"), 그리고 크기 범위를 설명하는 검증 메시지("손절 비율 10%은(는) 0 초과 100 이하여야 합니다"). 회귀: `app/analytics/new/strategySummary.test.ts`, `app/analytics/new/builderProgressPresentation.test.ts`, `app/analytics/new/page.scroll.test.tsx`(칩 클릭→크기 적용), `backend/tests/test_chip_answer.py`, `backend/tests/test_nl_parser_overrides.py`(UI 칩 계약 목록), `backend/tests/test_strategy_builder.py`, `backend/tests/test_builder_modify_rules.py`.

#### 3.1.4 전략 저장 및 관리

**FR-STR-040** 사용자는 전략을 저장하고 이름 및 설명을 부여할 수 있어야 한다.

**FR-STR-041** 시스템은 전략의 타입을 자동 분류해야 한다 (가치투자 / 모멘텀 / 기술적분석 / AI 혼합 / 기타).

**FR-STR-042** 사용자는 저장된 전략을 불러와 편집하거나 재실행할 수 있어야 한다.

**FR-STR-042b** 저장된 전략 DSL에는 `symbols`가 없으므로(유니버스는 `universe_id`로 저장, 엔진이 PIT 마스터로 종목을 재해석) 저장 DSL 기반 백엔드 요청은 `symbols: []`를 채워 백엔드 스키마(필수 필드)를 통과시켜야 한다 — 워크포워드는 단일 통로인 `buildWalkForwardRequest`(parsedStrategyMerge.ts)에서, 재실행은 `/analytics/[id]`의 `buildEffectiveBacktestRequest`에서 채운다. 워크포워드 실행 진입점 3곳(`/analytics/new`, `/analytics/[id]`, 전략 기록 상세 `/backtest/[id]`)은 모두 SSE 스트림 클라이언트(`runWalkForwardStream`)를 사용해야 한다(비스트림 `/api/backtest/walk-forward` 직접 호출 금지 — 진행률·취소·장시간 타임아웃 보호 없음). 또한 백엔드 검증 실패(pydantic 422)의 `detail` 객체 배열은 그대로 노출하면 "[object Object]"로 보이므로 `formatApiErrorDetail`(walkForwardStream.ts)로 `경로: 메시지` 형태의 읽을 수 있는 문자열로 변환해 표시해야 한다.

**FR-STR-066** 시스템은 전략 채팅(`/analytics/chat`) 진입 직전에 전략연구소(`/analytics`)를 브라우저 히스토리에 포함해야 하며, 채팅에서 뒤로가기를 실행하면 직전 방문 페이지와 관계없이 전략연구소로 돌아가야 한다.

**FR-STR-066b** [결과 화면 재실행 표시] 백테스트 결과 화면(`/analytics/new`)을 '결과 닫기'(=뒤로가기)로 닫은 뒤 채팅에서 백테스트를 다시 실행하면, 실행 중에는 채팅 화면의 진행 표시(`BacktestRunningStatus`)만 보여야 하고 직전 결과 화면이 함께 노출돼선 안 된다. 결과 화면을 닫아도 직전 `result`는 대화 복귀 후 결과 유지를 위해 state에 남으므로, 결과 화면 밖에서 시작한 실행은 실행 시작 시점에 이전 결과를 비운다(`handleRunBacktest`). 반대로 결과 화면 안에서의 재실행(설정 변경 후 실행)은 이전 결과를 유지한 채 그 위에 진행 표시를 얹는다 — 사용자가 직전 결과를 보며 기다릴 수 있어야 하기 때문이다.

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

**FR-STR-066** [섹터/업종 유니버스, 2026-07-10] 시스템은 "반도체 관련주", "2차전지 업종" 같은 업종 제한을 전략 조건(`ParsedStrategy.sector`)으로 지원해야 한다. ① 섹터 분류의 SOT는 `korea-stocks.json`의 `sector` 필드(49개 정본 섹터, `engine/universe_pit.py::CANONICAL_SECTORS`)이며, 사용자·LLM의 자유 표현("배터리", "제약주", "AI 관련주")은 동의어 맵(`normalize_sector`)으로 정본명에 정규화한다(정규화 불가 시 None). '로봇'(2026-07-13 신설, 27종목)은 KSIC 공식 분류에 로봇 업종이 없어('특수 목적용 기계 제조업' 등으로 등록) **사명(로봇/로보틱스/로보) 기준**으로 분류하는 독립 정본 섹터다 — `MAPPING_RULES["로봇"]`이 우선순위 최상단(사명 부분매칭 오분류 선점: 해성에'어로'보틱스가 수산 '어로'에 걸리던 버그 수정), 사명에 로봇이 없는 로봇 전문기업(뉴로메카)은 `OVERRIDDEN_SYMBOLS`, 상폐 경로(`get_sector_from_krx_industry`)도 단축명 오버라이드보다 사명 판정을 먼저 거친다. 일반 자동화 설비·공작기계('공장자동화' 포함)는 기계/장비에 남는다. ①-1 [동의어 파생 구조, 2026-07-13] 동의어 맵은 두 어휘집의 드리프트를 구조적으로 차단하도록 파생된다: 종목 분류 어휘(`sector_mapper.MAPPING_RULES`)에는 '투자'·'금속'·'설비' 같은 일반어가 섞여 있어 통째로 NL 인식에 쓰면 거짓 양성('투자금 1억'→증권/보험)이 나므로, 사용자가 섹터를 부를 때 실제로 쓰는 모호하지 않은 산업어만 명시적으로 opt-in한 화이트리스트(`sector_mapper.NL_SAFE_TERMS` — 로봇/공장자동화/태양광/원전/웹툰 등)에서 정본 섹터를 자동 파생하고(`universe_pit._derive_mapper_nl_synonyms`, 각 용어의 단일-정본 매핑을 import 시점 검증), 여기에 분류 어휘엔 없는 사용자 전용 통칭(2차전지·리츠·AI)을 오버라이드로 얹는다(`_SECTOR_SYNONYM_OVERRIDES`). 정본명을 손으로 중복 기입하지 않아 종목 분류와 NL 인식이 서로 다른 섹터를 가리킬 수 없으며, 가드 테스트(`test_sector_nl_synonyms`)가 "어떤 산업어든 NL이 인식하면 반드시 분류와 같은 섹터"를 강제한다 — '로봇'이 분류상 기계/장비인데 NL 동의어엔 없어 '지원 목록에 없는 섹터'로 안내되던 드리프트의 근본 차단(회귀: test_robot_sector_now_resolves_without_unsupported_notice). ② 결정적 추출(`nl_parser._extract_sector`)은 섹터명 + 업종 큐('관련/테마/업종/섹터/분야/종목/주식/주' + 범위 후치 표현 '중심/위주', 2026-07-11)가 붙은 명시적 표현만 잡고, '주가'는 큐에서 배제한다. '관련/테마'는 맨 형태로 본다(2026-07-12 — '관련주' 어순만 보면 "반도체 관련 전략"·"로봇주 관련 전략"을 놓쳐 안내 없이 전체 시장으로 백테스트된다). 목록 밖 업종("로봇 관련주")은 룰 파서가 수락하지 않고 LLM에 위임하며, 최종적으로도 표현 불가하면 미지원 개념 안내(notices)를 남긴다(침묵 누락 방지). 단, "업종 상관없이/모든 업종" 같은 무관 표현은 섹터 언급으로 치지 않는다(오탐 방지). ②-1 [LLM 폴백 드리프트 복구, 2026-07-12] 업종 큐가 없는 표현("2차전지에 투자하는 전략")은 LLM 폴백이 섹터를 캐치하는 유일한 층이므로, LLM 산출물의 흔한 스키마 드리프트(sector를 universe 필드에 기입, description 누락)를 ValidationError로 통째로 폐기하지 않고 결정적으로 복구해야 한다(`ParsedStrategy._repair_llm_schema_drift` — universe의 비시장 값을 정본 업종으로 sector 이동·한글 시장명 정규화, 빈 description은 다른 전략 내용이 있을 때만 허용 후 `_apply_prompt_overrides`가 원문으로 채움). LLM이 sector를 냈지만 universe가 스키마 기본(KOSPI200)이고 시장 언급이 없으면 ③의 양시장 기본을 LLM 폴백 경로에서도 강제한다(수정 경로 제외 — 기존 universe 보존). ③ 시장 언급 없는 섹터 전략의 유니버스 기본값은 KOSPI200이 아니라 양시장(KOSPI+KOSDAQ)이다 — '그 업종 전체'가 자연스러운 해석이며 KOSPI200 기본값은 시총 상위 200 ∩ 섹터로 과도하게 좁아진다. ④ 엔진은 PIT 유니버스 해석 후 심볼을 섹터로 필터링하고(`universe_pit.filter_by_sector`), 해당 종목이 없으면 명시적 에러로 fail-fast한다. ④-1 [상폐 종목 섹터 백필, 2026-07-12] 섹터 분류는 현재 상장(korea-stocks.json, 우선) + PIT 마스터(stock-master.json)의 상폐 종목 `sector` 백필을 병합해 기간 중 상폐된 종목도 섹터 유니버스에 포함해야 한다(생존 편향 제거). 상폐 종목 섹터는 FDR KRX-DELISTING의 KRX 구 산업분류 단축명을 `sector_mapper.get_sector_from_krx_industry`(단축 어휘 전용 오버라이드 `KRX_SHORT_INDUSTRY_OVERRIDES` — '전기·전자'→IT 하드웨어, '기계·장비'→기계/장비, '금융'(대부분 스팩)→증권/보험 등 — 후 공통 키워드 매퍼 폴백)로 분류하며, `scripts/backfill_delisted_sectors.py`(제자리 패치, 멱등)와 `build_stock_master.py`(재빌드) 양쪽이 같은 로직으로 생성한다. 우선주(끝자리≠0)는 모주(prefix+'0')의 섹터를 물려받는다(korea-stocks.json은 보통주만 담음). 생존 편향 경고는 무조건 출력하지 않고, 업종 분류가 없어 필터에서 빠진 '상장폐지' 종목(`sector_unknown_delisted`)이 실제로 있을 때만 개수와 함께 고지한다 — 현재 상장 종목의 분류 공백(신규 상장 등)은 생존 편향이 아니므로 경고 대상이 아니다. `data/stock-master.json`은 git 추적 파일이고 프로덕션 compose가 `./data`를 마운트하므로 백필 결과는 커밋·배포로 프로덕션에 반영된다. ⑤ `sector`는 canonical DSL(해시)과 `BacktestRequest` 스키마에 포함해 캐시 충돌·스키마 누수(extra=ignore 드롭)를 막는다. 섹터 없는 기존 전략의 해시는 변하지 않는다. ⑥ [수정 경로 섹터 반영, 2026-07-13] 완성된 전략에 대한 후속 수정 요청("반도체 섹터 종목만 테스트 해줘")도 섹터를 반영해야 한다 — 결정론 fast-path(`_modify_rule_based`)가 `_extract_sector`로 섹터를 추출하고, LLM diff 경로는 diff가 sector를 놓치면 결정적 추출로 보정한다(파스 경로 보정과 동형). `MODIFY_PROMPT`에는 지원 업종 목록·매핑 지침·섹터 예시를 포함한다. 수정 경로는 기존 universe를 보존한다(③의 양시장 기본 확장은 최초 파싱 전용 — `_apply_prompt_overrides(preserve_universe=True)`; 시장을 넓히려면 "전체 시장으로" 등 명시 수정으로). '업종/섹터'+삭제어 인접 표현("업종 제한 빼줘", "섹터 필터 지워줘")은 섹터 제한을 해제하되, '업종에서 삼성전자 빼줘'(종목 제외 요청)로는 오발동하지 않는다(`_SECTOR_REMOVE_RE` 인접 조건). ⑦ [다중 섹터, 2026-07-13] `sector`는 정규형 None/str(단일 — 기존 해시·직렬화 하위 호환)/list(복수)를 가지며(`normalize_sector_value`), 복수면 엔진이 합집합으로 필터링한다(`filter_by_sector` 리스트 지원). 수정 요청의 네 의도는 결정적 통합 판정(`_sector_change_from_utterance`)이 LLM diff보다 우선한다: **추가**("로봇 섹터도 추가해줘" — '도' 조사+업종 명사 또는 추가/포함 동사 인접)는 기존 목록과 합집합, **교체**(추가 표지 없는 언급)는 덮어쓰기, **개별 삭제**("반도체 업종은 빼줘")는 그 항목만 제거(목록에 없는 대상이면 전체 해제로 오폭하지 않고 판단 유보), **전체 해제**는 기존 `_SECTOR_REMOVE_RE`. 이 판정은 rule-based fast-path·LLM diff 병합·`_apply_prompt_overrides` 세 지점에 동일하게 배선된다 — 종전에는 삭제 발화가 `_extract_sector` 재추출로 되살아나는 재주입 버그가 양 경로에 있었다(회귀: test_modify_sector_removal_not_reinjected). '도' 단독 조사는 짧은 용어 오발동("ai도입")이 있어 업종 명사 동반 또는 추가 동사 인접일 때만 추가 의도로 본다. canonical DSL은 단일=str 그대로, 복수만 정렬 list로 직렬화해 기존 전략 해시 불변+순서 무관 동일 해시를 보장한다. 반도체를 기계/장비로 교체해버리던 "로봇 섹터도 추가해줘" 실측 사고의 근본 수정(회귀: test_modify_sector_additive_union). ⑦-1 [최초 파싱 복수 수집, 2026-07-25] 결정적 추출(②)은 첫 매치만 반환하지 않고 한 발화의 복수 업종 언급("반도체와 로봇관련 종목")을 전부 수집해 발화 순서대로 정규형(단일=str, 2개 이상=list)으로 반환해야 한다 — 큐 매치와 큐리스 매치를 모두 `finditer`로 훑고 dedup하며, 복합 테마구 가드(FR-STR-071b)는 매치별로 판정한다('말고' 정정 발화의 앞 업종도 이 가드가 배제). 종전에는 큐 매치('로봇관련')가 선점해 큐리스 언급(반도체)이 조용히 소실됐다(실측 사고 2026-07-25 — 빌더 시드가 '업종 로봇' 단독 인식, 회귀: test_extract_sector_multiple_mentions). 전략 빌더 상태(`BuilderState.sector`)도 list를 담으며 확인 문장·시드 요약·합성 프롬프트·테마 되묻기 칩은 '·' 연결 라벨로 표기한다("반도체·로봇 업종 대상"). LLM 인터프리터(strategy_conversation) 시스템 프롬프트에도 규칙 6-0으로 같은 계약을 명시한다(PROMPT_VERSION 1.3) — 업종/테마 제한은 지원 기능이며 언급된 업종을 전부 `universe.sectors` 배열에 넣고, unsupported_features 분류·업종 되묻기를 금지한다(4B가 '지원 지표 목록에 없는 개념→unsupported' 규칙을 조건용이 아닌 유니버스에 오적용해 "업종/테마 기반 종목 선택 (반도체, 로봇)"을 미지원 처리하던 실측 드리프트 2026-07-25; sectors 값은 `capability_validator`가 정본 화이트리스트로 재검증하므로 목록 밖 이름은 조용히 왜곡되지 않고 명시적 미지원 안내가 된다. 회귀: test_system_prompt_sector_rule_contract, test_multiple_sectors_normalized_with_spacing_drift — 4B의 글자 사이 공백 드리프트 '2 차 전 지'도 정본화). ⑧ [묶음 섹터 분할 + 구 이름 하위 호환, 2026-07-30] 'A/B' 형태로 두 업종을 한 섹터에 묶어둔 정본명은 **분류 데이터가 두 갈래를 결정적으로 가를 수 있을 때만** 독립 섹터로 분할한다. 2026-07-30 기준 18개 묶음 섹터 중 KSIC 산업분류 또는 외부 큐레이션 카탈로그로 가를 수 있는 8쌍을 분할했다(증권/보험, 은행/금융지주, 조선/해운, 식품/음료, 소프트웨어/플랫폼, 사료/축산, 화장품/패션, 디스플레이/부품 → 16개 독립 섹터, 872종목 재분류, `scripts/split_combined_sectors.py` 멱등 마이그레이션). 화장품/패션은 ⑩의 분류 교정으로 화장품 기업이 실재하게 된 뒤에야 분할이 가능해졌다 — 화장품(29)은 `OVERRIDDEN_SYMBOLS`로 귀속된 '기타 화학제품 제조업', 패션(46+상폐 6)은 전부 섬유·의류 KSIC이라 경계가 확정된다. 나머지 10쌍(에너지/원자력·미디어/엔터·기계/장비·철강/금속·디스플레이/부품·바이오/제약 등)은 분할하지 **않는다** — KSIC에 해당 코드가 없거나(원자력) 최대 코드가 양쪽 어디에도 붙지 않거나(미디어/엔터의 '영화·방송프로그램 제작') 두 낱말이 포함·동의 관계라(철강⊂금속, 기계≈장비) 종목별 귀속을 데이터 없이 지어내야 하기 때문이다. 이 보류는 회귀 테스트(`test_unsplit_combined_sectors_are_untouched`)로 고정해 임의 분할을 막는다. **하위 호환**: 분할 전 구 묶음명이 입력되면 신규 두 섹터의 합집합으로 편다(`expand_legacy_sector`, `LEGACY_COMBINED_SECTORS`) — `filter_by_sector`·`normalize_sector_value`·`universe_resolver.resolve`·`capability_validator` 네 경로에 배선해, 저장된 전략·백테스트 이력·PIT 유니버스 스냅샷이 구 이름을 들고 있어도 같은 종목 집합으로 재현된다(하드 컷 대신 별칭 유지 — 사용자 결정 2026-07-30). 분할된 낱말은 정본명이 되므로 `_SECTOR_SYNONYM_OVERRIDES`에 중복 기입하지 않는다. 마이그레이션은 두 데이터 파일의 industry 어휘 차이(korea-stocks=KSIC 정식명, stock-master=거래소 축약명)를 별도 테이블로 처리해야 한다 — 단일 테이블 사용 시 상폐 보험사가 증권으로 오분류된다(실측). prod DB(`Stock.sector`)는 KIS 프로파일 어휘라 유니버스 선정에 쓰이지 않으므로 마이그레이션 대상이 아니다. 회귀: `tests/test_sector_split.py`. ⑨ [묶음 섹터 구성 고지 + 좁힘 감지 수정, 2026-07-30] 사용자가 묶음 섹터의 **한쪽만** 부르면('원자력 업종만') 그 표현은 정본 섹터가 아니므로 조용히 묶음 전체로 확정해서는 안 된다. `is_narrow_sector_approximation`은 **매핑 결과가 묶음 섹터('A/B')이면 항상 True**를 반환한다 — 종전 판정('표현이 정본명 글자 안에 있으면 이름 표기 차이')은 근거였던 '은행'·'보험'이 ⑧ 분할로 정본명이 되면서 남은 글자-포함 케이스가 전부 진짜 좁힘 요청이 됐고, '원자력'(→72종목, 정유·도시가스 포함)·'미디어'(→111)·'기계'(→217)·'철강'(→76)이 안내 없이 넓어지고 있었다(2026-07-30 제보, ⑧ 분할과 무관한 기존 결함). True가 되면 기존 배선(`classify_universe`)이 섹터 확정 전에 카탈로그 테마를 먼저 확인하므로 '원자력'은 '원자력발전'(50종목)·'원자력발전(SMR)'(11종목) 같은 구체 테마 후보로 이어진다. 카탈로그 후보가 없으면 섹터로 확정하되 **구성 안내**(`sector_composition_notice`)를 함께 낸다 — 묶음 섹터마다 사람이 쓴 한 줄 구성 설명(`SECTOR_COMPOSITION_NOTES`)에 결정론이 종목 수를 채우는 방식으로, KSIC 코드명을 그대로 노출하지 않으면서 LLM이 지어낼 여지도 두지 않는다(`_SECTOR_LLM_GLOSSES`와 같은 관례). 문구는 묶음의 성격에 따라 셋으로 갈린다: 진짜 혼재(에너지/원자력·미디어/엔터 등 7개 — "이 업종에는 ~도 함께 들어 있습니다"), 사실상 한쪽뿐(철강/금속 98% — "이름은 철강/금속이지만 사실상 전부 1차 철강 제조사입니다"), 두 낱말이 같은 분류(기계/장비 — "'장비'가 따로 있는 게 아니라 ~"). 가드: 정본 섹터에 남은 모든 묶음 이름은 구성 안내를 가져야 한다(`test_every_remaining_combined_sector_has_a_note`). 회귀: `tests/test_sector_composition_notice.py`. ⑩ [화장품 분류 교정, 2026-07-30] KSIC에 화장품 코드가 없어 국내 화장품사가 전부 '기타 화학제품 제조업'으로 등록돼 **화학** 섹터에 있었고, 그 결과 '화장품/패션' 46종목에 화장품 기업이 **0개**였다 — 사용자가 '화장품 업종'으로 백테스트하면 섬유·의류만 담긴 유니버스를 받았다. 완제품 브랜드와 ODM/OEM 29종목(아모레퍼시픽·LG생활건강·코스맥스·한국콜마 등)을 `OVERRIDDEN_SYMBOLS`로 화장품/패션에 귀속한다. 경계: 화장품 **원료·소재**사(선진뷰티사이언스·지에프씨생명과학·에이에스텍 등)는 화학에 남긴다 — 납품처가 화장품일 뿐 사업 자체는 화학이다. `OVERRIDDEN_SYMBOLS`(재생성 경로)와 korea-stocks.json(현재 상장 SOT)의 드리프트는 `scripts/apply_sector_overrides.py`(멱등)가 맞추고 `test_sector_overrides_match_stock_data`가 잡는다. 이 교정으로 화장품 기업이 실재하게 되면서 화장품/패션이 ⑧의 분할 대상이 됐다(화장품 31 / 패션 53). ⑪ [디스플레이/부품 교정·분할, 2026-07-30] 이 섹터는 132종목 중 131개가 KSIC '전자부품 제조업' 한 코드라 이름과 내용이 어긋나 있었다 — 디스플레이 부품이 아니라 PCB·MLCC·카메라모듈·커넥터·안테나·반도체 부자재·이차전지 동박까지 담은 전자부품 통짜 바구니였고, 등록 업종이 실제 사업과 어긋난 종목(파미셀=줄기세포, 두산=지주회사, 한화시스템=방산, 알에스오토메이션=로봇, 캐프=와이퍼)까지 섞여 있었다. ⓐ 오등록 5종목을 실제 사업 섹터로 이관하고(겸업·불확실 건은 근거를 만들 수 없어 보류), ⓑ 나머지를 **디스플레이(25) / 전자부품(109)**으로 분할했다. 디스플레이 귀속의 근거는 **외부 큐레이션 카탈로그**(네이버·주달 디스플레이 테마 ∩ 이 섹터 = 20종목)이며, 카탈로그가 놓친 명백한 5종목(비에이치·세경하이테크·파인엠텍·새로닉스·라온텍)만 근거를 적어 보강한다(`scripts/split_combined_sectors.py::DISPLAY_SYMBOLS`). 산업분류가 답을 주지 않을 때 개발자 기억이 아니라 검증 가능한 외부 데이터를 근거로 삼는 관례이며, `test_display_membership_is_catalog_grounded`가 근거 목록과 데이터의 일치를 강제한다. 기존 `IT 하드웨어`와는 겹치지 않는다(그쪽은 통신·방송장비·정밀기기·컴퓨터·전선). ⑫ [여행·레저 섹터 신설, 2026-07-30] `MAPPING_RULES["미디어/엔터"]`에 '관광·여행·숙박·유원지·오락·카지노' 어휘가 섞여 있어 하나투어·강원랜드·아난티가 미디어 업종으로 분류되고 있었다(94종목 중 12개 = 13%). 관광 어휘를 미디어/엔터에서 떼어내 **여행**(여행사 6)·**레저**(숙박 3 + 카지노·유원지 3) 두 독립 섹터로 신설한다. KSIC가 세 갈래를 정확히 가르지만(여행사 및 기타 여행보조 / 일반 및 생활 숙박시설 운영 / 유원지 및 기타 오락관련), 여행사=중개업·숙박+카지노=시설 운영이라는 사업 모델 기준으로 둘로 묶었다(사용자 결정). 데이터 재귀속은 개별 종목 목록이 아니라 **KSIC 코드 단위 규칙**으로 한다(`scripts/reassign_by_industry.py`, 멱등) — 신규 상장 종목도 자동으로 맞게 들어온다. 동의어는 '관광'→여행, '호텔·리조트·숙박'→레저만 등록하고 **'카지노'·'여행사'는 등록하지 않는다** — 지식그래프에 큐레이션 개념(`casino`·`travel-agency`)이 있어 섹터 동의어로 잡으면 KG 스캔 인덱스에서 제외돼(③) 더 구체적인 개념 조회를 가린다. 회귀: `test_curated_kg_concepts_are_not_shadowed_by_sector_synonyms`. ⑬ [섹터 분류 근거를 KSIC 코드로 전환, 2026-07-30] 종전 분류(`sector_mapper.get_sector_from_industry`)는 KRX 업종 **문자열**과 **사명**을 이어붙여(`f"{industry} {name}"`) 키워드 부분 문자열 매칭을 했다. 사명을 넣은 것은 KSIC에 없는 섹터(로봇) 하나를 위한 예외였는데 전체에 적용돼, 메"가스"터디교육이 '가스'에 걸려 에너지/원자력이 되고 사명에 '바이오'만 있으면 동물사료·섬유 회사가 바이오/제약이 되는 사고가 누적됐다(실측 13건). `OVERRIDDEN_SYMBOLS`가 63건까지 늘어난 것도 이 문자열 매칭을 손으로 덮은 결과다. ① **DART 기업개황 `induty_code` 전 종목 백필**(`scripts/backfill_dart_industry.py` → `data/dart-industry.json`, 2,655/2,655 성공). KRX 문자열이 3자리 수준까지만 주는 것과 달리 5자리 세세분류가 온다 — '기타 화학제품 제조업'(204) 안에 **화장품 제조업(20423)**이, '전자부품 제조업'(262) 안에 **표시장치 제조업(2621)**이 별도 코드로 존재한다(⑩·⑪에서 'KSIC에 코드가 없다'고 판단했던 것은 KRX 문자열만 봤기 때문이며, 코드 수준에서는 존재한다). ② **코드→섹터 표**(`engine/ksic_sectors.py`, 190항목, 최장 접두 5→4→3 우선)를 현행 배정에서 도출한 뒤 손으로 검토했다 — 커버리지 98%, 현행과 92% 일치. ③ **판정 순서 전환**: 개별 오버라이드 → 로봇(사명) → **KSIC 코드** → 키워드 폴백. 사명 기준 선점은 **로봇 하나만** 남겼다(산업용 로봇 코드 2928이 있으나 실제 등록 상장사가 1곳뿐이라 실무상 무력). 회귀 `test_name_matching_is_limited_to_robot`이 다른 섹터의 사명 선점 추가를 막는다. ④ **3자 교차 검증**(`scripts/audit_sector_sources.py`) — 현행/DART 코드/네이버 GICS 업종(1,632종목)을 대조해 불일치를 낸다. 어느 소스도 항상 옳지 않다: DART는 **등록** 주업종이라 실제 주력과 다를 수 있고(삼성전자=264 통신·방송장비), 네이버는 커버리지 61%지만 실사업에 가깝다(대한항공='항공사'). 자동 교정하지 않고 목록만 낸다 — 현재 검토 대상 96건. 한계: 표의 190항목 중 60개는 근거 종목이 1개 이하라 현행 배정을 그대로 옮긴 것에 가깝다(교차 검증이 이를 드러낸다). 회귀: `tests/test_ksic_sectors.py`.

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

**FR-BT-010e** [백테스트 창 경계 = 양끝 포함, 2026-08-02] 백테스트 창 필터는 요청한 시작일·종료일을 **모두 포함**해야 한다(`backtest_engine._date_key`). 창 필터가 `date` 컬럼을 통째로 문자열화해 비교하던 구현은 종료 경계를 배타적으로 만들었다 — `"2024-12-30 00:00:00.000000" <= "2024-12-30"`은 접두가 같고 더 긴 쪽이 크므로 거짓이고, 그 결과 **명시 종료일 당일 봉이 매번 통째로 빠졌다**(삼성전자 실측: endDate=2024-12-30 요청 시 마지막 봉이 2024-12-27 — 12-30 봉은 존재). 시작 경계는 같은 규칙이 우연히 맞는 방향이라(`>=`는 더 긴 쪽이 커서 통과) **끝에서만** 하루가 사라지는 비대칭이었고, 종료일이 휴장일이면 증상이 가려져 오래 남았다. 비교는 날짜 부분(YYYY-MM-DD)만으로 한다. 날짜 캐스팅이 아니라 문자열 절단을 쓰는 이유는 `date` 컬럼 타입이 파케이마다 갈리기 때문이다(실측 5,068개 중 Datetime[us] 5,066 · Datetime[ns] 1 · String 1). 결과값이 달라지는 변경이므로 `ENGINE_VERSION` MAJOR(9.0). 워밍업 사전 절단(`_warmup_start_str`)도 같은 술어를 공유해 두 자리가 다시 갈라지지 않게 한다.

**FR-BT-010d** 거래 비용은 매수 수수료 / 매도 수수료 / 매도 증권거래세(기본 0.15%, `sell_tax_rate` 옵션으로 제어)를 분리 적용해야 한다. (감사 H3)

**FR-BT-011** 처리 순서는 반드시 이월 청산 방출 → Exit → Risk Evaluation → Rebalance → Entry 순서를 지켜야 한다 (벡터화 단계). 청산이 예정된 종목은 같은 날 재진입할 수 없다(동일 셀 매수·매도 주문 충돌 금지).

**FR-BT-012** 트레일링 스탑은 `peak_price` 배열로 추적하며(고점 갱신은 장중 고가 기준), 진입 시 초기화하고 청산 시 리셋해야 한다.

**FR-BT-013** 다중 종목 동시 진입 시그널 발생 시 스코어 기반 랭킹으로 우선순위를 결정해야 한다 (PBR/ROE 복합 스코어 또는 `ranking_metric="return"` 모멘텀 — 최근 N일 수익률 상위 K종목 선정). 진입 조건 없는 모멘텀 랭킹의 후보 풀은 유동성 게이트와 대형주(시가총액 상위) 마스크를 반드시 보존해야 한다. (감사 C4)

**FR-BT-014** 시스템은 `rebalancing_period`(daily/monthly/quarterly/yearly)가 지정된 전략에 대해 달력 기준 리밸런싱(reconstitution)을 수행해야 한다: 각 주기의 첫 거래일에 후보를 랭킹 상위 K로 재선정하고, 목표 집합에서 빠진 보유 종목은 매도, 신규 편입 종목은 매수, 유지 종목은 그대로 둬야 한다.

**FR-BT-015** 리밸런싱 실행 방식은 전략의 봉중간 리스크 관리(SL/TP/트레일링 스탑/최대 보유기간) 사용 여부에 따라 분기해야 한다: 봉중간 리스크가 없는 순수 리밸런싱은 비중 리셋까지 수행하는 네이티브 목표비중 방식으로 처리하고, 봉중간 리스크가 혼재하면 현실적 체결을 보존하는 커스텀 reconstitution 루프로 처리하되 유지 종목의 비중이 리셋되지 않음을 경고로 고지해야 한다. (감사 H8)

**FR-BT-015b** 매도 거래의 청산 사유 라벨은 실제 청산 트리거를 구분해 표시해야 한다: 손절/익절/트레일링 스탑/보유기간 만료/상장폐지/데이터 종료/백테스트 종료는 각각의 정밀 라벨로 표시하고, 리밸런싱일에 목표 집합에서 빠져(조건 미충족·랭킹 이탈) 매도된 종목은 "리밸런싱 제외 (목표 종목 이탈)"로 표시해야 한다. 신호·리스크로 설명되지 않는 리밸런싱 편출을 추상적 "전략 매도 조건 충족"으로 뭉개지 않도록, 시뮬레이터(순수·커스텀 루프 두 경로)가 체결일 기준 정밀 사유를 기록하고 결과 처리기가 이를 우선 적용한다. 결과 요약 카드에는 `rebalancing_period`가 `none`이 아니면 리밸런싱 주기 배지를 노출해야 한다. 손절/익절/트레일링 스탑 라벨은 시뮬레이터가 청산을 감지한 시점의 확정 사유(exit_reason_overrides)를 정본으로 사용해야 하며, 실현수익률 크기로 사유를 사후 추론(예: `수익률 ≈ -손절%±1%`)해서는 안 된다 — 봉중간 스탑은 종가(same_close)·익일 시가(next_open)·갭 체결로 실현수익률이 스탑 기준선과 어긋나므로 크기 추론은 진짜 손절을 누락하거나 무관한 매도를 손절로 오귀속한다. (프런트엔드 `resolveTradeReason`도 손실률 기반 재라벨을 하지 않고 백엔드 정본 라벨을 그대로 표시한다.) "백테스트 종료" 라벨은 **사유 없는 기말 강제 정산에만** 붙인다 — 마지막 봉에 발동한 시뮬레이터 확정 사유(손절·익절·트레일링·리밸런싱 편출)와 전략 매도 신호 사유는 마지막 날이라는 이유로 덮어쓰지 않는다(과거에는 마지막 날짜의 모든 매도를 날짜만 보고 "백테스트 종료"로 재라벨했다). 단, 실현수익률-근접 추론은 기말 강제 정산과 우연히 일치하기 쉬워 마지막 봉에서는 채택하지 않는다.

**FR-STR-067** [ETF 유니버스, 2026-07-19] 시스템은 ETF(상장지수펀드)를 백테스트 가능한 독립 유니버스(`universe=["ETF"]`, `universe_id="etf"`)로 지원해야 한다. ① **데이터**: ETF 마스터는 `data/etf-master.json`(FDR ETF/KR 목록 ∩ 로컬 OHLCV 커버리지, `backend/scripts/build_etf_master.py`로 생성·멱등, git 추적이라 커밋·배포로 prod 반영)이며, 엔진은 창 안에서 가격 데이터가 존재하는 ETF만 as-of로 해석한다(`universe_pit.resolve_etf_symbols`). 상폐 ETF는 `backend/scripts/backfill_delisted_etf.py`로 백필됐다(2026-07-19 완료) — FDR KRX-DELISTING엔 ETF가 없고(수익증권 그룹=구식 공모펀드), openapi.krx.co.kr Open API는 증권상품 엔드포인트 미승인(401)이라, data.krx.co.kr 로그인 세션(.env KRX_ID/KRX_PW)으로 'ETF 전종목 시세'(MDCSTAT04301)를 2015-01~현재 전 거래일(3,012거래일) 스윕해 수집했다. **주의**: pykrx의 `get_etf_ticker_list(과거일)`는 현재 상장 종목의 부분집합만 반환해 상폐분을 못 잡는다(2020-02-28 실측: 시세 화면 451종목 vs 멤버십 350종목) — 반드시 일별 전종목 시세 화면을 직접 스윕해야 point-in-time이 된다. 재개 가능 캐시=data/cache/krx-etf-daily/(gitignore, 3,012개 파일), 산출물=data/etf-delisted.json(git 추적, 244종목) → build_etf_master.py가 병합(코드 재사용 시 현재 상장분 우선). 상폐 244종목 중 다수(30종목)는 만기매칭형 채권 ETF(설계상 목표 만기에 자동 상환)였다. 상폐 ETF의 강제청산은 주식과 동일하게 "상장폐지"로 라벨된다(`get_delisting_dates` ETF 마스터 병합). 마스터에 상폐분이 백필된 후로는 ETF 백테스트가 생존 편향 경고를 남기지 않는다(`etf_master_includes_delisted`). **부수 발견**: 백필 후 전체 ETF 유니버스 E2E 검증 중 `DataLoader.load_symbol_data`가 ETF에도 무조건 재무 enrichment(ROE 등)를 시도해 종목마다 KIS 재무비율 API가 헛되이 실패(500)하는 것을 발견 — ETF는 재무제표가 없어 이 데이터가 애초에 쓰이지 않으므로(④의 유니버스별 팩터 레지스트리) `is_etf_symbol` 판정으로 건너뛰게 수정, 전체 ETF 백테스트 Phase1이 16.1s→7.4s로 단축되고 로그 소음이 사라졌다. ② **미혼합**: ETF 유니버스는 주식 시장(KOSPI/KOSDAQ/KOSPI200)과 절대 혼합하지 않는다 — 파서·인터프리터 스키마가 ["ETF"] 단독으로 정규화하고("코스피 ETF"도 ETF — 상품 유형이 시장 언급보다 우선), 엔진은 ETF 마스터만 조회한다. 종목 섹터 분류(sector)는 ETF에 적용되지 않아 비운다. ③ **테마/상품명 필터**(`ParsedStrategy.etf_theme` → `BacktestRequest.etf_theme`, canonical DSL 포함 — None이면 키 제거로 기존 해시 불변): "반도체 ETF"→"반도체", "KODEX 200"→상품명을 결정적으로 추출하되, 어휘집 유지 대신 **ETF 마스터 이름과의 자기검증 매칭**으로 판정한다(`universe_pit.extract_etf_theme` — 상품명 전체 매칭 우선, 'ETF' 직전 토큰의 접미사 중 마스터 이름과 매칭되는 것만 테마로 인정; "사는 ETF"의 '사는'은 매칭 0이라 무시). 엔진 필터(`filter_etf_by_theme`)는 정확한 상품명 일치가 있으면 그 종목만, 없으면 이름 포함 매칭 전체를 대상으로 하고, 매칭 0이면 전체 ETF 유지+warnings 안내(조용한 왜곡 방지). ④ **유니버스별 팩터 검증**(`engine/universe_capabilities.py` — 단일 진실 소스): ETF는 여러 기업을 묶은 상품이라 기업 재무지표(PER·PBR·ROE·부채비율·배당성향 등 재무제표 파생 전부와 시가총액 — ETF에선 AUM이라 의미가 다름)를 전략 조건으로 쓸 수 없고, 가격·거래량 파생 지표(기술 지표 전부, 거래대금)만 허용한다. ETF 전략에 재무지표가 섞이면 **조용히 무시하지 않고** 이유 설명("ETF는 개별 기업이 아니라 여러 종목을 묶은 상품이므로 …을 조건으로 사용할 수 없습니다")+기술 지표 대안 제안 칩으로 되묻는다 — 최초 파싱 경로는 `nl_parser.detect_etf_factor_conflict`(정성 언급 "PER 낮은 ETF" 포함, 진입 누락 되묻기보다 우선), LLM 인터프리터 경로는 `capability_validator`(오류+suggested_fixes)가 담당한다. LLM 프롬프트(인터프리터 규칙 6-1, SYSTEM_PROMPT/MODIFY_PROMPT, 수정 RAG knowledge)에도 동일 계약을 명시해 임의 생성·조용한 제거를 금지한다. ⑤ **체결 비용**: ETF 매도에는 증권거래세가 부과되지 않으므로 명시 옵션이 없으면 `sell_tax_rate=0`으로 시뮬레이션한다. ⑥ **빌더/프론트**: 전략 빌더 시장 선택지에 ETF를 포함하고, ETF 유니버스에서는 가치 전략(PBR/ROE) 선택지를 제시·수락하지 않는다. 전략 요약 유니버스 배지는 "ETF"(+테마 배지 "반도체 테마"/"KODEX 200")로 표시한다. ⑦ **향후 확장**: 유니버스별 지원 팩터는 `universe_capabilities`에서 독립 관리한다(미국주식·채권 등 신규 유니버스는 항목 추가로 확장).

**FR-STR-068** [단일/지정 종목 백테스트, 2026-07-20] 시스템은 사용자가 특정 종목과 전략을 함께 언급하면("삼성전자에 골든크로스 전략을 적용해줘", "005930에 MACD 전략", "하이닉스에 RSI 과매도 전략") 유니버스(종목 선정) 백테스트와 분리된 **단일/지정 종목 백테스트**로 실행해야 한다. ① **모드 분리**: `ParsedStrategy.target_symbols`(종목코드 목록)가 비어 있으면 기존 유니버스 모드, 채워져 있으면 지정 종목 모드다. 변환기(`to_backtest_request`)는 지정 종목 모드에서 `symbols=[지정 코드]`, `universe_id=None`(엔진이 PIT 재해석·섹터 필터를 적용하지 않고 목록을 그대로 사용 — 기존 엔진 계약 재사용), `sector/etf_theme=None`, `backtest_mode="single_asset"`, 표시용 `target_stocks`(코드→등록명)를 만든다. 자금 배분은 지정 종목 수 기준 균등(단일이면 100%, `position_size_pct=100/n`, `max_positions=n`)이며 횡단면 랭킹(`ranking_enabled`)은 끈다. ② **결정적 종목 해석**: 종목명·통칭 별칭·6자리 코드→정규 종목코드 변환은 LLM이 아니라 `stock_analysis/symbol_resolver`(korea-stocks.json 정본) 기반 결정적 추출(`nl_parser._extract_target_symbols`)이 담당하고, LLM은 이 필드를 출력하지 않는다(스키마 설명으로 금지). LLM Interpreter Primary 경로(`STRATEGY_INTERPRETER_MODE=primary`)에서도 컴파일 후 같은 결정적 추출로 채운다(`primary._override_target_symbols` — 날짜 오버라이드와 동형; StrategySpec에 지정 종목 개념이 없어 누락 시 유니버스 전략으로 조용히 넓어지는 사고 방지). 이때 지정 종목이면 유니버스형 청산 누락 되묻기(정기 리밸런싱 추천)는 억제하고 ⑤의 보정이 처리한다. 또한 종목명+'테스트' 발화("삼성전자 단일 종목만 테스트 해보자")는 분류기 결정 규칙이 전략 설계로 라우팅한다(LLM 폴백의 STOCK_ANALYSIS 리다이렉트 오분류 방지). 조사 결합 표기("삼성전자에"/"하이닉스로"/"삼성전자만")와 코드+조사("005930에")를 인식하도록 경계 판정을 확장했다(유니코드 \b 함정 — 한글은 단어문자라 코드 뒤 조사에서 경계 실패). ③ **문맥 가드(오폭 방지)**: 예시("삼성전자 같은/처럼"), 업종 서술("~가 속한 반도체 업종", 업종/섹터/관련주/테마/주도주), 제외·부정("빼고/제외/말고")이 섞인 발화에서는 종목 추출을 포기한다 — 종목질문 리다이렉트(FR-SA-006)·전략 빌더가 합성하는 업종 전략 문구가 단일 종목으로 오폭되면 유니버스 전략이 조용히 바뀌는 사고가 된다. 부정·비교 등 모호 발화는 LLM/되묻기에 위임된다(보수적 실패 = 기존 유니버스 의미론 유지). ④ **복수 종목 처리** [2026-07-26 개정 — 되묻기 폐지(사용자 결정)]: 여러 종목이 함께 지정돼도 '한 종목만 고르기' 칩 되묻기(`detect_symbol_ambiguity`)를 내지 않는다 — 언급된 종목 전체를 함께 백테스트하고, 축소·교체는 채팅 수정 요청("삼성전자만으로 백테스트해줘"·"현대약품은 빼줘"·"SK하이닉스로 바꿔줘")이 ⑥의 수정 경로로 처리한다(실측 사고 2026-07-26: 테마 유니버스 10종목 확정 후 "종목을 교체 할 수 있나?" 질문에 종목 선택 칩 10개가 떠 흐름이 끊김 — LLM 수정 경로가 있으므로 채팅 입력만으로 충분). [2026-07-28 개정 — 다종목=포트폴리오] 복수 지정 종목(테마 유니버스 자동 적용 포함)은 단독 종목이 아니라 포트폴리오이므로 리밸런싱 주기를 되묻는다 — 최소 조건 게이트의 단독 종목 면제는 **지정 종목이 정확히 1개**일 때만 적용한다('지정 종목 존재=단독'으로 판정해 질문 없이 기본값 '설정 안 함'으로 확정되던 사고, '모바일솔루션 관련주'). 백엔드 `_missing_backtest_conditions`·프론트 `getNextMissingBacktestCondition` 동일 규칙이며, 칩에 '리밸런싱 안 함'을 포함해 사용자가 결정하고, 명시 거부는 누적 프롬프트 재파싱에서 같은 질문을 반복하지 않는다(`_mentions_rebalancing_negation` 게이트 인지). 요약 카드도 다종목 지정은 사용자가 답하기 전까지 리밸런싱 기본값을 확정된 것처럼 표시하지 않는다(단독 종목 1개는 교체가 없어 기존대로 '설정 안 함' 표시). ⑤ **청산 누락 추천 보정**: 지정 종목 전략에 청산 조건(청산 신호·보유기간·손절/익절/트레일링/MDD·리밸런싱)이 전혀 없으면 조용히 임의 실행하지 않는다 — 크로스오버 계열 진입(ma_crossover/ema/macd)은 반대 신호 청산을 추천 기본값으로 적용하고 notices로 알리며, 그 외 진입은 자동 주입 없이 "기간 종료까지 보유" 사실과 추가 옵션을 notices로 안내한다(`apply_single_asset_adjustments`, `_build_parse_result` 공유 — 최초 파싱·수정·후행 검증 교정 모두 적용). 이 보정 덕에 지정 종목+기술 진입 단독 프롬프트는 룰 fast-path에 남는다(유니버스 전략의 '진입만 있으면 LLM 위임' 게이트 면제). ⑥ **수정 경로**: 종목 교체("SK하이닉스로 바꿔줘" — 별칭 표면형을 잔여 판정에서 차감해 fast-path 유지)·**개별 삭제**("현대약품은 빼줘" — 기존 지정 목록에서 그 종목만 제거)·명시적 시장 전환 시 지정 해제("코스닥 전체로")·업종 전환 시 지정 해제("반도체 업종으로")를 결정적 통합 판정(`_target_change_from_utterance`)이 LLM diff보다 우선 처리하며, 무관 수정("손절 5%로")은 지정을 보존한다. **개별 추가("제주반도체도 추가해줘"=기존 지정과의 합집합)는 결정론이 판정하지 않는다**(2026-07-26 확정 — 추가/교체 구분은 원문 의미 해석이라 regex 어휘 확장 금지, 사용자 지시로 결정적 추가어 판정 철회): LLM 인터프리터 수정 경로가 `/universe/symbols` add 패치(값=사용자 표기 문자열 그대로, 프롬프트 규칙 10-1)로 처리하고, 스키마 정규화·`universe_resolver`·검증 warning이 조용한 소실을 막는다(계약 문서 § 11-2 '막은 구멍 2', 회귀: test_strategy_conversation.py 종목 패치 3케이스). 레거시 결정론 레인은 추가 발화를 구분하지 못한다 — 이는 § 11 격차 1의 이관 대상이지 regex로 메울 결함이 아니다. 같은 사고의 짝 수정: 섹터 변경 판정(`_sector_change_from_utterance`)은 판정 전에 인식된 종목명 표면형을 가린다(`_mask_stock_name_mentions` — 기존 regex의 오해석을 줄이는 방향) — "제주반도체도 추가해줘"의 종목명 내부 조각('반도체'+'도 추가')이 업종 추가로 오폭해 지정 종목 해제까지 연쇄되던 사고 방지(회귀: test_single_asset_backtest.py 마스킹 케이스)(섹터 FR-STR-066 ⑥/⑦과 동형 — rule fast-path·LLM diff 병합·`_apply_prompt_overrides` 세 지점 배선). [2026-07-26 사고 수정] 삭제 판정은 지정/교체 판정보다 **우선**한다 — 문맥 가드(③)가 '빼고/제외/말고'만 알고 '빼줘/빼조(오타)'류 활용형을 놓쳐, "현대약품은 빼조"의 종목 언급이 '새 지정'으로 오독돼 테마 유니버스 10종목이 현대약품 단일 종목으로 교체되던 사고. 삭제 판정(`_removal_mentioned_target_refs`)은 종목 표면형 바로 뒤(종목/주식 명사·조사 허용)에 삭제어(빼/제외/제거/삭제/지워/없애/없이)가 인접해야 성립한다 — 인접 요구가 "현대약품 손절 빼줘"(청산 조건 삭제)와의 혼동을 막는다(섹터 개별 삭제 패턴과 동형). `_extract_target_symbols`도 삭제어 인접 언급은 지정으로 보지 않는다(초기 파싱의 단일 종목 오폭 방지). 회귀: `test_single_asset_backtest.py` 삭제 6케이스. ⑦ **해시/스키마 관통**: `target_symbols`는 canonical DSL(정렬, 빈 값은 키 제거로 기존 해시 불변)에 포함돼 종목별로 다른 strategy_id(캐시 충돌 방지)를 가지며, `BacktestRequest`에 `backtest_mode`/`target_stocks`를 선언해 pydantic extra=ignore 드롭 함정을 막는다. ⑧ **표시**: 전략 요약의 유니버스 배지 대신 "삼성전자 (005930)" 종목 배지("대상 종목" 라벨), 포트폴리오 배지는 "최대 N종목" 대신 "단일 종목 집중 투자"(복수면 "지정 종목 N개 균등 투자")로 표기한다(파싱 카드·실행 요청 요약·저장 DSL 요약 모두). [2026-07-28 확장] 대화 진행 요약 카드('현재까지 이해한 전략입니다', `builderProgressPresentation`)도 같은 표기를 쓴다 — 지정 종목 모드에서 `parsed.max_positions` 기본값을 "최대 보유 10종목"으로 표시하면 변환기 실행값(①의 max_positions=지정 종목 수 균등)과 다른 정보가 노출된다('모바일솔루션 관련주' 카드-실행 불일치). 유니버스 전략의 "최대 보유 N종목" 표기는 불변. ⑨ **비용/기본값**: 수수료·슬리피지·초기자금·기간·체결 시점은 기존 플랫폼 기본값과 시장별 비용 모델(증권거래세 포함)을 그대로 사용하고, 상장폐지 종목 강제청산 등 PIT 의미론도 유니버스 모드와 동일하게 적용된다. 한계: 현재 상장 종목명만 해석된다(상폐 종목명 지정은 미지원 — korea-stocks.json 정본), 해외 종목 별칭은 데이터가 없어 지정으로 승격하지 않는다. ⑩ **LLM 해석 경로**(2026-07-26, 자연어 해석 계약 1a+4): 인터프리터 파이프라인에서는 LLM이 지목한 종목 표현을 `StrategyIntent.universe.symbols`에 원문 그대로 담고(종목코드 환각 금지), `strategy_conversation/registry/universe_resolver.resolve_symbols`가 마스터 조회로 6자리 코드를 확정해 컴파일러가 `target_symbols`에 배선한다. 업종 표현도 같은 모듈의 `resolve_sectors`(정본 사전→지식그래프)로 정본화되며, 해석하지 못한 표현은 조용히 버리지 않고 반환·기록한다. 사용자 원문을 다시 읽는 결정적 추출(`_extract_target_symbols`)은 이 단계에서 폴백으로 공존한다 — 상세는 `docs/nl_interpretation_contract.md`.

**FR-STR-068b** [단일 종목 연구 프로파일 + 프로파일 기반 대화, 2026-07-24] 시스템은 단일 종목이 지정되면 그 종목을 티커 문자열로만 다루지 않고, 백엔드가 종목의 실제 데이터를 결정론적으로 사전 분석한 **구조화된 종목 프로파일**(`StockResearchProfile`)을 생성·캐시하고, 대화(빌더·코치·파싱 안내)가 이를 근거로 동작해야 한다. ① **프로파일 생성**(`engine/stock_profile.py::StockProfileService`): 수정주가·기업행사 보정이 적용된 OHLCV에서 데이터 커버리지(기간·결측률), 설명 통계(연환산 변동성·상승일 비율·왜도/첨도·갭 빈도·MDD/평균 낙폭/회복 기간·거래대금 중앙값·추세 비율), 대표 신호의 발생 횟수·연간 빈도(고정 격자: RSI 임계 교차, 골든크로스 3조합, MACD, 볼린저 상/하단, 돌파 3기간, 거래량 급증, 고점 대비 하락, CCI, 스토캐스틱)를 계산한다. LLM은 원시 시계열을 읽거나 계산하지 않는다 — 직렬화된 프로파일 요약만 전달된다. ② **정직성**: 계산 불가 필드는 null(임의 추정 금지 — 예: 시장지수 상관은 지수 시계열 부재로 null), 파이프라인에 없는 데이터(외국인/기관 수급·공매도·실적 발표일·배당/공시/뉴스 이벤트·시장/업종지수·분봉)는 `unsupported_features`로 선언하고 지원하는 것처럼 표현하지 않는다. 재무 지표는 parquet 병합이 PIT-safe(공시 접수일 available_from, 폴백 결산일+90일)임을 `point_in_time_safe`로 표시한다. ③ **과최적화 방지**: 프로파일은 설명 통계와 신호 빈도만 담는다 — 수익률 기준 사후 최적 파라미터(best value)는 계산·저장·추천하지 않으며, 파라미터는 해석 가능한 탐색 범위(예: RSI 20~40 step 5)만 제안한다. ④ **캐시**: `data/cache/stock_profiles/{symbol}.json`, 소스 fingerprint(parquet mtime+size)+`PROFILE_VERSION`으로 무효화, 섹션(technical/signals/financial)별 fingerprint 기록으로 향후 부분 갱신 지원. ⑤ **질문 템플릿 필터링**(`engine/stock_question_templates.py`): 템플릿이 필요 데이터 피처·최소 신호 횟수·advanced 여부를 선언하고, 선택 로직이 프로파일 근거로 노출/제외를 결정한다. 제외는 조용히 숨기지 않고 이유를 담는다. 단일 종목 기본 질문에 횡단면(종목 선별) 조건은 없다 — 재무 조건(PBR/PER/배당수익률)은 '그 종목의 당시 값' 시계열 신호(advanced)로만, 명시 요청 시 노출한다. 발생 횟수가 최소 기준(10회) 미만이면 희소 신호 경고("기준 완화/기간 연장"), 연간 빈도가 과다(30회 초과)하면 거래비용·슬리피지 경고를 붙인다. ⑥ **파스 흐름 검증**(`engine/single_asset_review.py`): 파싱된 단일 종목 전략의 진입 신호를 격자에 근사('유사 조건 기준' 명시)해 희소/과다 경고, 재무 조건 데이터 미보유 시 "지원할 수 없습니다"+기술 지표 대안 안내, 보유 시 PIT 적용 사실 안내를 비차단 notices로 전달한다(조건 임의 삭제·실행 차단 없음, 프로파일 실패는 파싱을 깨지 않음). ⑦ **빌더 단일 종목 모드**(`BuilderState.single_symbol`): 종목 선별용 질문(유니버스·보유 종목 수·리밸런싱 주기)을 건너뛰고, 첫 질문을 "언제 사고 언제 팔 것인가"(프로파일 신호 횟수를 근거로 선택지 설명)로 바꾸며, 모멘텀 랭킹·가치 스크리닝 선택은 이유 설명+대안과 함께 되묻는다. 확정 시 target_symbols·max_positions=1·리밸런싱 없음으로 DSL을 직접 조립한다. ⑧ **API**: `GET /stock/{symbol}/research-profile`(include_advanced 토글)이 데이터 기간·가능 전략 카테고리·노출 질문(근거 reason·경고)·제외 질문(이유)을 반환한다. reason은 데이터 사실만 담고 수익 보장·우월 표현을 쓰지 않는다(규제 안전). ⑨ **코치**: 단일 종목 전략 코칭 시 프로파일 압축 JSON과 행동 제약(미보유 데이터 지원 표현 금지, 10회 미만 신호 신뢰 경고, 사후 최적값 추천 금지, 미래 예측·수익 보장 금지, null 추정 금지, 선별 대신 진입/청산 질문)을 주입한다. ⑩ **관측성**: 프로파일 버전·노출/제외 질문 수·경고 수를 구조화 로그로 남긴다.

**FR-STR-069** [용어 그라운딩 — 인터넷 검색 기반 업종/테마 용어 학습, 2026-07-24] 시스템은 사용자가 언급한 업종/테마 용어를 내부 지식(결정적 섹터 어휘 + LLM)으로 해석하지 못하는 경우, 인터넷 검색으로 용어의 의미를 학습해 지원 업종으로 매핑해야 한다(`engine/term_grounding.py`). ① **해석 체인**: 빌더의 sector_resolver는 어휘집 결정적 조회 → 내부 지식 LLM 매핑(`llm_extract_sector`, 기존 경로) → 검색 그라운딩 순으로 동작한다(`resolve_sector`, `api/intent_routes.py` 배선). ② **검색 그라운딩**: 미해결 시 LLM이 문장에서 테마 용어를 추출하고("ess 관련 투자 전략" → "ESS"), 네이버 API 허브 검색(백과사전 + 뉴스 `"{용어} 관련주"`·`"{용어} 수혜주"` 각 8건 + 웹문서, 4쿼리 — '수혜주' 쿼리는 2026-07-25 리콜 보강: 스니펫이 제목+요약 2줄뿐이라 '관련주' 기사 표본만으론 본문 종목 나열이 잘리는 실측(BTS 학습 시 넷마블 미포착), 링크 dedupe로 같은 기사의 교차지지 이중 계산은 차단, 스니펫 상한 24)의 스니펫을 근거로 LLM이 정의 한 문장과 지원 업종 매핑을 산출한다. 출력 업종은 반드시 `normalize_sector` 게이트를 통과해야 하며(목록 밖 이름 → None), 실패 시 기존 업종 되묻기 흐름으로 폴백한다. ③ **어휘집 영속 캐시(같은 용어 재검색 금지)**: 검색이 실제 수행되면 결과(원문 용어·정의·매핑 업종·출처 상위 3건·검색 시각)는 매핑 성공/불가 모두 `data/term_lexicon.json`에 저장되고, 이후 같은 용어는 검색·LLM 없이 어휘집에서 결정적으로 해석된다(라틴 약어는 라틴 문자 lookaround 경계 매칭 — 'process'의 'ess' 오매칭 방지). 단, 검색 호출 자체가 실패(네트워크·쿼터·자격증명 없음)한 경우에는 저장하지 않아 복구 후 재시도할 수 있다. 어휘집은 런타임 학습 산출물로 git에 추적하지 않는다(환경별로 자라남). ④ **안전 장치**: 검색 결과 본문은 신뢰할 수 없는 외부 데이터로 취급해 그라운딩 프롬프트가 본문 내 지시·명령·추천을 무시하고 사실 추출만 수행하도록 명시하며, 검색 자격증명(`NAVER_CLIENT_ID`/`NAVER_CLIENT_SECRET`) 미설정 시 그라운딩 단계는 조용히 비활성화되고 기존 체인만 동작한다. ⑤ **'검색 중...' 진행 표시**: 빌더 스텝은 SSE 엔드포인트(`POST /strategy/builder/step-stream`, parse-stream의 stage_holder 폴링 패턴 재사용)로 처리되며, 그라운딩이 인터넷 검색에 실제 진입하면(`resolve_sector`의 `on_search` 콜백) 결과 전에 `{"type":"stage","stage":"searching"}` 이벤트를 흘리고 프론트 로딩 버블이 '분석 중...' 대신 '검색 중...'을 표시한다. [2026-07-25 확장] 개념 해석 체인(어휘집·지식그래프·내부 LLM) 진입 시에도 `resolve_sector`의 `on_kg_lookup` 콜백이 `{"type":"stage","stage":"kg_lookup"}` 이벤트를 흘려 프론트가 '개념 확인 중...'을 표시한다(검색 진입 시 '검색 중...'으로 교체). parse-stream 경로(`_learn_unknown_sector_term`)도 동일하게 배선되며 체인 종료 후 'parsing'으로 복귀한다. 프록시(`app/api/strategy/builder/step/route.ts`)는 URL 계약을 유지한 채 SSE를 파이프하고, 클라이언트 헬퍼는 응답 content-type으로 SSE/JSON을 분기한다(기존 JSON 계약 호환 — 어휘집/내부 LLM 히트처럼 검색이 없는 턴은 stage 이벤트 없이 기존과 동일하게 동작). 기존 `POST /strategy/builder/step`은 호환용으로 유지된다. [2026-08-05 확장] parse-stream의 LLM 인터프리터 기본 경로는 Ollama 응답을 스트리밍(NDJSON)으로 받아 **생성 중인 StrategyIntent 섹션 키를 진행 단계로 방출**한다 — planner-first 유니버스 해석 진입 시 `universe`, 이후 출력이 도달한 섹션에 따라 `universe`/`entry`/`exit`/`risk`/`settings`(프론트 표시: '유니버스 분석 중...'/'매수 조건 분석 중...'/'매도 조건 분석 중...'/'리스크 관리 분석 중...'/'설정 분석 중...'(포트폴리오·백테스트 섹션)). 판정 입력은 사용자 원문이 아니라 LLM이 생성 중인 JSON의 키 위치다(형식 관찰 — 자연어 해석 아님). 수정 턴(patches 출력, 섹션 순서 없음)과 on_chunk 미지원 chat 주입(테스트 스텁·QA 하니스)에는 적용되지 않고 기존 단계 표시로 동작한다. ⑥ **파싱 경로 사전 학습** [2026-07-25]: 검색 그라운딩은 빌더뿐 아니라 파싱 파이프라인에도 배선된다 — `_run_nl_parse`(main.py)가 파싱 전에 게이트(`nl_parser.mentions_unresolved_sector`: 업종/테마 큐는 있는데 결정적 추출이 실패한 입력, 섹터 되묻기와 동일 판정)를 통과한 입력을 `term_grounding.learn_sector_term`으로 학습한다. 실측 사고: "마운자로 관련주 전략을 만들어보자"가 파싱 경로(인터프리터 primary)로 흘러 검색 없이 미지원 처리 — 그라운딩이 빌더 resolver에만 배선돼 있었음. 학습분 해석은 그래프 단일 경로다 — [2026-07-25 읽기 경로 통합] 학습 노드가 지식그래프 스캔 인덱스에 포함되므로 `_extract_sector`의 KG 폴백(`resolve_sector_from_text`)이 시드·학습 용어를 함께 해석한다(초기 구현의 어휘집 스캔 폴백은 제거됨, FR-STR-070 ③). 해석 성공 시 notices로 해석 사실을 안내하고("'마운자로'은(는) 인터넷 검색으로 확인해 '바이오/제약' 업종 관련으로 해석했어요"), 인터프리터의 업종 질문(`strategy.universe.sectors`)과 같은 테마를 가리키는 미지원 안내는 제거한다(`_prune_clarifications_filled_by_overrides` 확장 — 반영된 전략과 모순되는 되묻기/안내 방지). parse-stream도 검색 진입 시 `stage:"searching"`을 방출하고 프론트가 '검색 중...'을 표시한다. 한계: 현재 버전은 학습한 테마를 기존 지원 업종으로 근사한다 — 종목별 테마 멤버십(시점별 유니버스)은 다루지 않는다. ⑦ **TTL 조건부 재검토** [2026-07-25]: ③의 재검색 금지 계약에 TTL(`TERM_REGROUND_TTL_DAYS`, 기본 90일, 0 이하=영구 캐시)이 적용된다 — `searched_at`이 TTL을 넘긴 **미해결 항목**(매핑 불가 부정 캐시)은 사용자 재언급 시 조건부 재검색을 허용한다(1월에 매핑 불가였던 용어가 7월엔 부상한 테마일 수 있음 — 부정 캐시가 세상 변화에 영영 갇히는 문제 보정). 성공 항목(sector 있음)은 체인 ①에서 즉시 반환되므로 핫패스 재검색이 없고, 배치 재그라운딩(`scripts/kg_relink_audit.py --reground-stale`)이 담당한다. 재학습은 덮어쓰기가 아니라 **병합**(`_merge_entry_edges`)이다 — 기존 엣지의 콘솔 검토 상태(verified/rejected/pending)를 그대로 보존하고 새 제안만 추가한다(rejected 부활·verified 강등 금지). `searched_at`이 없는 레거시 항목은 재검색하지 않는다(보수). ⑧ **검색 소진 시 '전략 불가' 종결 안내** [2026-07-26]: 검색 그라운딩까지 실제 수행됐는데(어휘집 `searched_at` 원장 존재) 업종 매핑도, 테마 유니버스 자동 적용(FR-STR-071 ④)도 실패한 테마 언급('리센즈 관련주')은 오타 정정 되묻기(SECTOR_REASK) 대신 **'관련 상장사를 확인하지 못했고, 관련주를 찾을 수 없어 이 테마로는 전략을 만들 수 없다'는 종결 안내**(사용자 문구 결정 2026-07-26: '인터넷 검색' 표현은 사용자 노출 문구에서 제외 — 판정 조건은 검색 수행 원장 그대로)를 반환해야 한다(`nl_parser.THEME_NOT_FOUND_QUESTION` — 칩에 '업종 상관없음' 미포함: 존재하지 않는 테마를 억지 매핑하거나 테마를 버린 채 조용히 진행하지 않는다). 검색이 아직 수행되지 않았거나 검색 호출 자체가 실패한 용어(어휘집 미저장)는 기존 되묻기를 유지해 정정·재시도 여지를 남긴다. 반대로 테마 유니버스 자동 적용이 관련 상장사를 **찾아 확정한 경우**(parsed.target_symbols 설정)에는 테마 언급이 종목 목록으로 해석 완료된 것이므로 되묻기·종결 안내를 모두 내지 않고 다음 최소 조건 질문으로 전략 만들기를 계속하며, 미지원 개념 안내에서도 'sector'를 제외한다('설정했어요'와 '지원되지 않아요' 공존 모순 방지 — 실측 사고 2026-07-26 '이재명 관련주': 10종목 확정 후에도 업종 되묻기가 떠 흐름이 끊김). 미해결 업종/테마 질문(되묻기·종결 안내 공통)에는 `clarification_priority="sector_unresolved"` 마커가 실리며, 프론트 explicit 설정 게이트와 primary 인터프리터 질문은 priority가 실린 백엔드 질문을 덮어쓰지 않는다(실측 사고 2026-07-26: 백엔드가 섹터 되묻기를 반환했으나 프론트 게이트가 삼켜 일반 시장 질문으로 조용히 강등).

**FR-STR-070** [Investment Knowledge Graph — 투자 지식 그래프 Phase 1, 2026-07-24] 시스템은 투자 개념·산업·공급망·기업·ETF·재무지표·거시경제를 노드(Node)와 관계(Edge)로 잇는 지식 그래프를 유지하고, 자연어 속 개념을 그래프 탐색으로 해석해야 한다(`engine/knowledge_graph.py`, 설계 상세는 `docs/knowledge_graph.md`). ① **그래프 합성(정본 재사용)**: 시드 그래프(`data/knowledge-graph.json`, git 추적·수동 큐레이션 — HBM·SMR·ESS·전력기기·양극재·휴머노이드 로봇 등 개념 30여 개, 관계 100여 개. [2026-07-25] 시드 확장은 Concept–Stock Builder 절차(`docs/kg_concept_builder.md`)를 따른다 — 공식 근거(공시·기업 IR·ETF 공식 자료) 조사 원장을 `data/kg-research/<concept>.json`에 보존하고 Core/Strong 관계만 시드에 편입 — 총 14 Concept: 전고체 배터리·비만치료제·유리기판·액침냉각(기업 엣지 없이 개념 관계만)·폐배터리 리사이클링·우주발사체·탄소배출권(무소속 개념)·전력반도체·CXL·온디바이스 AI(다업종 무소속)·AI 에이전트·양자컴퓨터(기업 엣지 없음)·인공위성·마이크로바이옴)에 섹터 노드(`sector:<정본명>`, `CANONICAL_SECTORS` 자동 생성), 기업 노드(`company:<symbol>`, korea-stocks.json에서 참조 시 자동 생성), ETF 노드(`etf:<symbol>`, etf-master.json), 학습 노드(`learned:<key>`, FR-STR-069의 term_lexicon 오버레이 편입 — 검색 학습이 그래프도 함께 키운다)를 로드 시 합성한다. 정본을 손으로 두 번 적지 않으며, 엣지 끝점·타입은 로드 시 검증되고 시드 무결성 테스트가 위반 0을 단언한다(오타 심볼 fail-fast). ② **관계 어휘**: is_a/part_of/belongs_to/related_to/uses/used_by/used_in/requires/depends_on/supplier/customer/competitor/produced_by/manufactured_by/demanded_by/invests_in/related_company/related_etf/related_metric/related_macro/related_news/related_universe/cause/affected_by/benefits_from/risk_factor/substitute/next_generation/predecessor/successor. ③ **결정적 개념 인식**: 문장 스캔은 개념 노드의 이름·별칭을 대상으로 하되, 자동 생성 노드(sector:/company:/etf:)는 각자 기존 경로(섹터 정규화·종목 인식)가 담당하므로 제외하고, `normalize_sector`가 이미 해석하는 용어(AI·원자력 등)도 인덱스에서 제외해 상류 섹터 어휘와 이중 매칭되지 않는다. [2026-07-25 읽기 경로 통합] **학습 노드(learned:)는 스캔 인덱스에 포함**된다 — 시드·검색 학습 용어를 그래프 단일 경로로 인식하며(어휘집 별도 스캔 폴백 제거), 같은 용어가 시드·학습 양쪽에 있으면 시드가 이긴다(큐레이션 우선). 어휘집(term_lexicon.json)은 지식 저장소가 아니라 **학습 원장**(영속 저장·부정 캐시(매핑 불가 재검색 금지)·pending/rejected 검토 대기열·출처 증거)으로 역할이 한정된다 — 매핑 불가 항목은 노드가 아니므로 스캔에도 없다. 라틴 약어는 lookaround 경계 매칭(FR-STR-069와 동일 관례). ④ **섹터 해석(체인 ①b + 파싱 경로)**: FR-STR-069 해석 체인의 어휘집 조회와 내부 지식 LLM 사이에 그래프 결정적 조회가 배선된다. [2026-07-25 확장] 빌더 resolver뿐 아니라 **파싱 파이프라인의 결정적 섹터 추출(`nl_parser._extract_sector`)**에도 배선된다 — 어휘 밖 테마어(ESS·HBM·SMR)는 업종 큐(섹터/업종/관련/테마) 동반 시 그래프 시드로 해석한다(큐 없는 개념 언급 "금리가 오르면 매수"는 업종 제한으로 오폭하지 않음). `_extract_sector`는 규칙 파스·시드·수정(`_sector_change_from_utterance`)·LLM 폴백 드리프트 복구(`_apply_prompt_overrides`)가 공유하므로 전 경로가 한 번에 커버된다. 실측 사고(2026-07-25): "ess 관련 투자"가 분류는 전략 설계로 됐지만 파싱 경로(빌더 아님)로 흘러 — 인터프리터 UNSUPPORTED_REQUEST 폴백 → 규칙 파서 — KG가 빌더 resolver에만 배선돼 있어 ESS가 조용히 소실되고 빈 전략 최소 조건 게이트로 진입. — 개념에서 소속 엣지(is_a/part_of/belongs_to)만 깊이 3까지 따라 정본 섹터에 닿으면 즉시 반환(시드 개념은 LLM·검색 없이 해석: "SMR" → is_a 원자력 → 에너지/원자력). 서로 다른 섹터 둘 이상에 닿거나(복수 개념 충돌) 데이터센터처럼 의도적으로 다업종인 테마(소속 엣지 없음)는 None으로 기존 되묻기/LLM 폴백을 유지한다. ⑤ **관계 확장 조회**: `related_universe(text)`가 개념 주변을 BFS(기본 깊이 2)로 펼쳐 관련 섹터·상장기업·ETF·개념을 도달 경로(via: "HBM –produced_by→ SK하이닉스")와 함께 반환한다 — 백테스트 유니버스 후보의 객관적 관계 데이터이며 UI 배선은 Phase 2.  ⑦-1 [섹터 노드와 테마 노드의 구분, 2026-07-30] 지식그래프는 **섹터(업종)**와 **테마**를 `category`로 구분한다 — `industry` vs `theme`/`theme_catalog`. 성격이 다르기 때문이다: 섹터는 **전수 분류**(모든 종목이 정확히 하나에 속함)이고 테마는 **큐레이션된 부분집합**(근거 있는 종목만, 없다는 것은 '테마 밖'이라는 올바른 답). 섹터 노드는 `CANONICAL_SECTORS`에서 자동 생성되며 메타를 **정본에서 파생**해 담는다(손으로 두 번 적지 않는다): `synonyms`(`_SECTOR_SYNONYMS` 역방향), `ksic_codes`(`KSIC_SECTOR` 역방향), `member_count`(`_load_sector_map`), `composition_note`(묶음 섹터만), `is_combined`. ⑦-2 [섹터 소속 정본을 KG로, 2026-07-30] 섹터 소속(`company -belongs_to→ sector`)의 정본은 **KG**다. 인터프리터가 지식을 찾는 곳이 KG인데 소속이 `korea-stocks.json`에만 있어 그래프로 "이 섹터에 어떤 종목이 있나"를 답할 수 없었다(`related_universe('원자력')` → `{}`). 소속 데이터는 `data/kg-sector-membership.json` 오버레이에 두고 KG 빌드 시 편입한다 — 3천여 엣지가 손 큐레이션 시드(`knowledge-graph.json`)를 덮지 않게 하는 관례이며 `theme_catalog`·`learned` 오버레이와 동형이다. `universe_pit._load_sector_map`이 그 엣지를 읽고(오버레이 부재 시에만 파일 폴백), `korea-stocks.json`의 `sector` 필드는 **파생 캐시**로 강등됐다(참조부 71곳 호환). 불일치는 `test_stock_file_sector_is_a_derived_cache_of_the_kg`가 잡는다. 주의: 오버레이는 **상폐 종목과 우선주까지** 담아야 한다 — 빼면 섹터 유니버스에 생존 편향·누락이 생긴다(실측 회귀 2건: 상폐 누락 에너지/원자력 72→66, 우선주 상속 누락 72→66). 병합 규칙은 `universe_pit.sector_map_from_files`가 단일 구현을 갖고 오버레이 빌더가 그것을 쓴다. 섹터를 옮기거나 분할하면 개념 엣지도 함께 옮겨야 한다 — 카지노를 레저로 옮겼는데 `casino -part_of→ sector:미디어/엔터` 엣지가 남아 있던 실측 사고를 `test_kg_concept_edges_follow_sector_moves`가 막는다. ⑥ **규제 안전**: 그래프는 생산·공급·소속 등 객관적 관계만 저장·표시하고, 추천·전망·우열 판단을 표현하는 노드/엣지는 만들지 않는다. 한계(Phase 1): 개념→지정 종목/ETF 유니버스 자동 생성, 뉴스 키워드 연결은 미배선 — `docs/knowledge_graph.md`의 Phase 2/3 참조. (검색 그라운딩의 그래프 엣지 자동 생성은 FR-STR-070b로 구현됨.)

**FR-STR-070b** [지식그래프 학습 편입 — 검색 그라운딩의 관계 엣지 자동 생성, 2026-07-25] 검색 그라운딩(FR-STR-069)이 새 용어를 학습할 때 정의·섹터뿐 아니라 기존 시드 개념과의 **관계 엣지**도 함께 학습해 지식그래프를 키워야 한다(`engine/term_grounding.py::_propose_edges`). ① **결정적 후보 탐색(닫힌 세계)**: 후보 앵커는 LLM 탐색이 아니라 검색 스니펫 본문에 실제 등장한 시드 개념(`knowledge_graph.find_concepts` — 자기 자신 제외)만 결정적으로 수집하고, LLM은 그 닫힌 목록 안에서 관계 유형만 고른다(존재하지 않는 노드를 지어내는 환각 차단). 후보 밖 타깃·미허용 유형은 게이트에서 드롭한다. ② **관계 유형 제한**: 학습 엣지는 객관적 관계 서브셋(is_a/part_of/belongs_to/related_to/uses/supplier/competitor)만 허용 — 추천·전망·우열 관계 금지(규제 안전, 프롬프트에도 명시). ③ **자동 승격 + 사후 반려**: 서로 다른 출처(evidence 링크) 2개 이상이 같은 앵커를 지지하면 자동 `verified`, 1개면 `pending`. 신뢰도는 LLM 자기보고가 아니라 출처 수 기반이다. 엣지는 어휘집 엔트리(`edges: [{type, target, support, status, evidence}]`)에 저장되며 git 추적 시드(knowledge-graph.json)에는 쓰지 않는다(시드=수동 큐레이션, 학습분=런타임 산출물 — 출처 분리). ④ **그래프 합성 게이트**: KG 로더는 `verified` 엣지만 그래프에 합성하고(타입·타깃 로더 재검증) pending/rejected는 제외한다. 섹터 매핑 없이 verified 엣지만 있는 용어도 노드로 편입한다. 결정적 섹터 해석(①b)·유니버스 경로에는 시드+verified만 관여한다. ⑤ **관리자 검토**: 운영 콘솔 Knowledge 탭(`/api/admin/knowledge` — requireAdmin 404 은닉·감사 로그)에서 학습 용어·엣지를 검토하고, verified 엣지 사후 반려·pending 수동 승인·잘못 학습된 용어 삭제(삭제 시 다음 언급에 재검색으로 재학습)를 수행한다. 어휘집 파일이 SOT이며 백엔드 로더는 파일 mtime으로 자동 재로드한다. [2026-07-27 UI 정비] 관련 기업 엣지 자동 등록(FR-STR-071 ① 개정) 후 검토 대기열이 아닌 감사·교정 도구로 성격이 바뀌어, 용어 박스는 기본 접힘(헤더에 용어·업종·학습 시각·엣지 수·검토 대기 배지, 클릭 토글)이고 정의·수동 엣지 추가·엣지 목록은 펼침 시에만 표시한다. 검색 입력(용어명·정의·엣지 대상 종목명 부분일치 — "이 종목이 어느 테마로 학습됐나" 역조회)이 목록을 필터링하며 검색 중 일치 항목은 자동으로 펼친다. 실측(2026-07-25): 'CoWoS' 학습 시 LLM이 제안한 'part_of→메모리 반도체'(부정확) 엣지가 출처 1개라 pending으로 억류됨 — 검증 게이트가 의도대로 동작. ⑥ **재연결 감사(역방향 공백 보정)** [2026-07-25]: ①의 후보 탐색은 학습 시점의 그래프만 알므로, **학습 이후 편입된 노드**와의 연결 기회는 영영 없다('bts 관련주' 사고의 역방향 — bts가 kpop-agency 시드보다 먼저 학습됐다면 엣지 부재). `term_grounding.propose_relink_edges`/`relink_lexicon`이 학습 항목의 저장 텍스트(정의+출처 제목)를 현재 그래프로 재스캔해 미연결 개념 노드로 향하는 후보 엣지를 추가한다 — LLM 무관여 결정적 스캔, 저장 텍스트 재해석은 출처 교차지지를 새로 셀 수 없으므로 자동 verified 없이 **전부 pending**(콘솔 승인), rejected 이력 타깃은 부활 금지, company:/etf: 타깃은 제안하지 않음(상장사 매칭은 종목 마스터 기준이라 그래프 성장과 무관 — 학습 시점 수집이 완결), 멱등(재실행 시 무변화). 진입점: 시드 편입 가드 5(`docs/kg_concept_builder.md`) + 주기 감사 `scripts/kg_relink_audit.py`. 실측: 마운자로 → obesity-drug(시드가 학습보다 늦게 편입돼 미연결이었음) pending 제안 확인. ⑦ **수동 엣지 추가** [2026-07-25]: 검색(co-mention)·공시(지분) 어느 경로도 못 잡는 롱테일 관계('LB인베스트먼트=하이브 초기 투자사' — 벤처펀드 경유 초기 투자라 5%룰·출자현황 비노출)는 관리자가 콘솔 Knowledge 탭에서 근거 문구(note)와 함께 직접 추가한다(PATCH addEdge — 허용 유형 화이트리스트·중복 409·감사 로그). 관리자 행위 자체가 사람 검증이므로 즉시 verified(proposed_by=manual, 출처 수 없음 — UI '수동 등록' 표기). KG 로더는 학습 엣지의 note를 그래프로 운반하고 Concept Universe(FR-STR-072)가 그 근거 문구를 이유로, 점수는 시드 최소 등급(0.70)으로 표시한다.

**FR-STR-070c** [KG 시각화 — 운영 콘솔 지식그래프 뷰, 2026-07-25] 관리자는 합성 지식그래프 전체를 운영 콘솔에서 상시 시각적으로 확인할 수 있어야 한다. ① **데이터 경로**: 백엔드 `GET /knowledge/graph`(`api/intent_routes.py`)가 로더 합성 결과(시드+정본 자동 생성 섹터·기업·ETF 노드+verified 학습 오버레이)를 nodes/edges/issues로 덤프하고, Next 프록시 `/api/admin/knowledge/graph`(requireAdmin — 비관리자 404 은닉, 백엔드 미가용 502)가 패스스루한다. 합성 로직의 SOT는 `engine/knowledge_graph.py`이며 프론트는 시드·어휘집 파일을 재합성하지 않는다. ② **표시**: Knowledge 탭의 'KG 시각화' 서브탭(`components/admin/KnowledgeGraphView.tsx`) — 외부 라이브러리 없는 캔버스 포스 레이아웃(반발+링크 스프링+중심 중력, 결정적 나선 초기 배치), 그룹 5종(개념·테마/섹터/학습 용어/상장사/ETF)을 색+도형(원/마름모/사각형)으로 이중 인코딩하고 범례·노드/엣지 카운트를 표시한다(색 단독 식별 금지). 줌/팬/노드 드래그, 호버 툴팁(이름·분류·설명), 노드 클릭 시 이웃 하이라이트+관계 목록("HBM –produced_by→ SK하이닉스") 표시, 로더 검증 경고(issues)가 있으면 노출한다. **테마 레벨 기본 화면(2026-07-27)**: 테마 카탈로그 편입으로 그래프가 노드 3천·엣지 9천 규모(종목이 78%)가 되어, 기본 화면은 종목(상장사) 노드를 숨긴 테마 레벨로 표시한다 — 종목은 노드 선택 시 그 이웃만 연결 노드 곁에서 펼쳐지고(검색으로 숨은 종목을 선택해도 자동 활성), 범례의 '상장사' 칩이 전체 표시 토글을 겸한다. 반발력은 공간 그리드 근사(인접 9칸 정확 계산+원거리 칸 무게중심, 컷오프 400px)로 전체 표시에서도 프레임을 유지하며, 축소 시 라벨은 줌 비례 차수 임계값으로 솎아낸다(학습 용어는 항상 라벨, 노드 크기는 sqrt 차수 스케일). ③ **규제 안전**: 객관적 관계 데이터의 표시일 뿐 추천·전망이 아니다(FR-STR-070 ⑥ 준수).

**FR-STR-070d** [개념↔종목 관계의 근거·관련도, 2026-07-30] 지식그래프의 개념↔상장사 관계는 **왜 연결되는가(근거)**와 **얼마나 직접적인가(관련도)**를 런타임까지 전달해야 한다. ① **원장이 정본**: `data/kg-research/<concept>.json`(FR-STR-070 ①의 조사 원장)에 이미 있는 `relation_type`·`relevance`·`relevance_score`·`reason`·`business_evidence`·`sources`·`verified`를 `engine/kg_research.py`가 읽어 `(concept, symbol)` 인덱스로 만들고, 그래프 빌드가 시드 엣지에 `relation`으로 부착한다. **원장에 없는 관계에는 아무것도 붙이지 않는다** — 근거를 지어내지 않으며, 이 코드가 관계를 새로 판정하지도 않는다. 배선 전에는 원장이 런타임에서 한 번도 읽히지 않아(시드로 옮길 때 엣지 타입과 한 줄 note만 남음) "직접 생산"과 "테마 목록에 함께 있을 뿐"을 구분할 수 없었다. ② **직접 사업 관계의 구분**: `Producer`·`Supplier`만 `direct=true`이고 `Investor`·`Infrastructure`·`Related`는 사실이되 직접 생산·공급이 아니다. 관계 유형 목록은 원장의 실제 어휘에서 도출하며(목록을 먼저 정하고 데이터를 맞추지 않는다), 목록 밖 유형도 버리지 않고 `relation_known=false`로 표시만 한다(걸러내면 새 유형 추가 시 관계가 조용히 사라진다). ③ **근거 출처 구분**: `evidence_source`는 `research`(원장 근거)·`seed`(큐레이션이나 근거 미기재)·`catalog`(테마 카탈로그 수록)·`learned`(검색 학습)이며 **그래프 빌드 시점에 표기**한다 — 읽는 시점에 추론하면 근거 없는 시드 엣지가 카탈로그로 잘못 표기된다(실측). ④ **점수 산출**: Concept Universe(FR-STR-072)는 원장이 있으면 `relevance_score`를 그대로 쓰고, 없을 때만 기존 note 문자열 되파싱(`"(Core 95)"`)으로 폴백한다. ⑤ **[규제 안전] 전망성 관계 금지**: 관계 유형은 과거·현재의 **사실**만 담는다. 설계 스펙이 나열한 '정책 수혜 가능성'은 미래 전망이므로 도입하지 않는다 — 근거로 표기하는 순간 객관적 데이터 표시가 아니라 전망 제공이 된다(FR-STR-070 ⑥). 회귀 테스트가 전망성 어휘(Policy·Beneficiary·Expected·Outlook·Forecast)의 유입을 막고, 별도 테스트가 배포된 원장의 관계 유형이 전부 등록된 사실 유형인지 상시 확인한다. ⑥ **금지**: 관련도 기반 종목 절단·정렬은 하지 않는다(테마 유니버스 종수 상한 절단 금지 — FR-STR-070 계열의 선행 결정). 회귀: `backend/tests/test_kg_research.py`.

**FR-STR-071** [테마 관련 상장사 학습 + 테마 유니버스 되묻기, 2026-07-25] 검색 그라운딩이 테마 용어를 학습할 때 **함께 언급된 국내 상장사**도 관계 엣지로 학습하고, 파싱이 그 목록으로 백테스트 대상을 좁힐 수 있게 해야 한다("마운자로 관련주 전략"이 업종 근사(바이오/제약 전체)로만 실행되던 한계 보정). ① **관련 기업 엣지(결정적 수집)**: `term_grounding._propose_company_edges` — 검색 스니펫 본문에 등장한 상장사를 정본 종목 마스터 매칭(`symbol_resolver.find_in_text`, 해외 제외)으로 수집해 `related_company` 엣지(target=`company:<symbol>`)를 만든다. '출처에 함께 언급됨'은 관계 유형 판단이 필요 없는 객관적 사실이므로 개념 엣지(FR-STR-070b)와 달리 **LLM 무관여**(환각 원천 차단). 신뢰도는 동일 계약: 서로 다른 출처 ≥2 자동 verified / 1개 pending(콘솔 검토·승인). 검색 쿼리에 `"{용어} 관련주"` 뉴스 8건이 추가된다(4건에선 교차지지가 실측 불가 — 전부 pending). ② **first_known_date(시점 편향 1단계 가드)**: 각 기업 엣지에 그 기업이 언급된 **뉴스 보도일(pubDate) 최솟값**을 ISO로 기록한다(뉴스 아닌 출처뿐이면 None, 테마 대표값 폴백은 학습일). 이는 '관련주로 확인된 최초 시점'의 근사일 뿐 정식 시점별 테마 멤버십(DART 공시 기반 검증)이 아니다 — 정식 구현은 별도 프로젝트. ③ **KG 합성**: verified 기업 엣지의 `company:` 타깃은 로더가 정본 노드로 자동 생성한다(정본에 없는 심볼은 issues 없이 조용히 스킵 — 학습 데이터는 시드 무결성 단언 대상이 아님). ④ **테마 유니버스 되묻기**: `nl_parser.detect_theme_universe_clarification` — 테마 큐(관련/테마) 동반 + 종목 미지정 + verified 관련 기업 존재 시, 자동 적용하지 않고 목록·출처 교차 확인 사실·시점 편향 경고를 담아 되묻는다(객관적 관계 데이터 표시, 추천 아님). [2026-07-25 읽기 경로 통합] 조회는 `knowledge_graph.theme_listed_companies` 그래프 단일 경로(깊이 1, `KnowledgeGraph.listed_companies`) — 학습 테마·시드 개념 공통이며, 로더가 학습 엣지의 support/first_known_date를 그래프 엣지에 실어 나르고 verified만 합성되므로 결과는 자동으로 검증분이다. [2026-07-25 개념 1홉 폴백] **학습 앵커**의 직접 상장사 엣지가 하나도 검증되지 않았으면 verified 개념 엣지 1홉 너머 개념의 직접 상장사로 후보를 채운다(`KnowledgeGraph.listed_companies_via_concepts` — 'bts 관련주' 실측 사고: 직접 엣지는 출처 1건 pending인데 verified 개념 엣지(K-팝 기획사, 출처 4건) 너머에 하이브가 있었는데도 업종 근사(미디어/엔터 전체)로 확정됨). 직접 verified 상장사가 있으면 홉은 발동하지 않으며(정밀 목록 우선 — 이웃 개념 상장사로 희석 금지), 시드·카탈로그 앵커는 폴백 대상이 아니다(큐레이션이 직접 엣지를 책임). 뉴스 보도일 없는 홉 상장사의 first_known_date 대표값은 기존 계약대로 학습일(searched_at)로 폴백한다(시점 편향 보수 유지). 칩 왕복 계약: 종목 칩은 "종목명 나열 + '종목 전체를 함께' + 'YYYY년부터'" 형태 — '관련주/테마/업종' 단어를 넣으면 `_TARGET_SYMBOL_CONTEXT_GUARD_RE`가 종목 추출을 차단하므로 금지, '전체를 함께'는 다종목 모호성 되묻기(`detect_symbol_ambiguity`, 집합 의도 큐로 억제 — FR-STR-068 확장)를 잠재우고, 'YYYY년부터'는 명시적 시작일로 해석돼 first_known_date 이전 구간을 배제한다. 업종 칩("… 업종 전체로 백테스트")은 기존 섹터 어휘로 재해석된다. **[2026-07-25 ④ 개정 — 되묻기 폐지·자동 적용(사용자 결정)]**: '이 종목들로만 vs 업종 전체' 되묻기(+Phase 2 공급망 확장 칩)를 폐지하고 `nl_parser.apply_theme_universe`가 되묻기 없이 `target_symbols`를 자동 설정한다(DSL 변환 전 실행 — 지정 종목 모드로 심볼 해석). 설정은 조회된 관련 상장사 **전체**다 — 종수 상한 절단 금지(2026-07-28 '비만치료 관련주' 사고: 안내문 나열용 상한 10이 target_symbols까지 잘라 동률 36곳 중 심볼 앞 10곳만 유니버스가 됨), 안내문의 종목명 나열만 10곳+«외 N곳»으로 축약한다. 빌더 레인(`_theme_patch`)도 동일 계약(theme_label은 synthesize_prompt 재파싱용 전체 이름). 업종 근사(sector)는 해제한다(관련 종목엔 타업종(넷마블·신세계)이 섞여 sector 필터가 남으면 방금 설정한 종목을 도로 걸러냄). 무엇이 어떤 근거로 설정됐는지는 **비차단 notices**로 투명하게 알린다(목록·출처 유형·first_known_date 시점 정보 — 침묵 적용 방지, 객관적 관계 데이터 표시이며 추천 아님). **[2026-08-02 개정 — 적용 안내 비노출(사용자 지시)]**: 이 안내문은 사용자 notices에 싣지 않는다 — 요약 카드('현재까지 이해한 전략')가 설정된 유니버스 종목 전체를 이미 표시해 배너가 중복이다. `apply_theme_companies`/`replace_theme_universe`의 반환 문구(근거 등급·시점 편향 문구 포함)는 적용 성공 신호·진단용으로 구성만 유지하고(회귀: test_theme_universe_autoapply), 모든 호출부(레거시 main·인터프리터 체인·planner·유니버스 칩·테마 교체)가 notices 적재를 중단한다. 시작일은 자르지 않는다(시점 편향은 notice 고지만 — 조용한 기간 축소 방지). 자동 설정된 다종목은 `detect_symbol_ambiguity`를 건너뛴다(집합 의도 자명). ⑤ **우선순위 보호**: ~~테마 되묻기는 유니버스 범위 질문이므로 `clarification_priority="theme_universe"`로 표시되고, 인터프리터 primary의 조건 질문이 이를 덮어쓰지 않는다(`apply_primary_meta` 가드)~~ — ④ 개정으로 되묻기가 사라져 미발동. 필드·프록시 passthrough·프론트 우선 게이트는 스키마 호환으로 유지(항상 None). 실측(2026-07-25): "마운자로 관련주" → 한미약품 verified(출처 2건)·펩트론 pending(1건, 콘솔 승인 대상), 칩 클릭 → symbols=[128940]·startDate=2026-01-01로 결정적 왕복 확인. 한계: 목록 품질은 뉴스 표본에 의존(누락된 관련주는 pending 승인 또는 직접 종목 지정으로 보완), first_known_date는 근사치. **[① 개정 — 관련 기업 엣지는 네이버 금융 분류 기반·자동 등록, 2026-07-27 사용자 지시]** 뉴스 동시언급 수집(`_propose_company_edges`)은 무관 종목 노이즈('다이어트'에 삼성SDI·신한지주·KB금융 등 21개 pending 실측 사고)가 커서 폐기한다. 대체(`_naver_company_edges`): ⓐ 검색 레인이 수집한 네이버 금융 분류 목록(테마+업종, ④a 표기 정합과 공유)에서 LLM이 용어에 대응하는 분류를 **이름 닫힌 목록 안에서만** 고르고(최대 3개, 목록 밖·스코프 제외(인물·정치 등) 이름 드롭), ⓑ 종목은 그 분류의 수록 목록(`naver_theme_live.fetch_group_stocks`, 정본 필터)에서 결정적으로 수집한다. 분류 수록은 객관적 사실이므로 **자동 verified 등록**(콘솔 사후 반려 가능) — support=수록 분류 수, evidence=분류 상세 URL, first_known_date=None. 가드 2겹: 개별 상장사명 용어는 결정적 차단(종목 마스터 정확 일치 — '삼성전자'가 '반도체 대표주'로 확장 방지), 인물·연예 그룹·고유명은 단일 과제 LLM 판별(`_naver_term_is_industry`)이 매핑 전에 차단(분류 매핑 프롬프트에 규칙을 섞으면 소형 모델이 무시하는 실측 — BTS·리센느). 대응 분류 없음·목록 수집 실패면 기업 엣지 없음(뉴스 폴백 없음). 뉴스 쿼리는 정의 그라운딩·개념 엣지(FR-STR-070b) 원천으로 유지. 기존 학습 항목은 `scripts/rebuild_learned_company_edges.py`로 재구축(pending 뉴스 엣지 제거·verified/rejected 보존·네이버 편입 — 2026-07-27 10항목 적용: '다이어트' 21→86 전부 verified, 인물·그룹 4건은 편입 0). **[⑥ 테마 출처 보존 + 수정 턴 테마 교체, 2026-07-30]** 테마로 설정된 지정 종목은 **출처 테마 표기**를 함께 저장한다(`ParsedStrategy.theme_universe`, 수정 초안까지 왕복하도록 `UniverseSpec.theme`). 사고: 토스 관련주 전략에 "쿠팡 관려주로 수정해줘"가 무변경으로 끝났다 — ⓐ 테마 적용이 종목만 남기고 테마명을 지워(`sector=None`) 초안에 출처가 없었고 ⓑ 수정 레인에는 지식 조회 체인이 없어 인터프리터가 종목코드를 직접 알아내야 했으며(실제로는 기존 코드를 복사한 무변경 패치+"종목 코드가 무엇인가요?" 되묻기 — 지식 조회를 사용자에게 떠넘김) ⓒ 그 되묻기는 우선순위 마커가 없어 프론트 설정 게이트의 조건 질문에 덮여 사라졌다. 수정: ⓐ 출처 표기 왕복 ⓑ `primary._resolve_theme_change` — 수정 턴이 새로 넣은 미해결 유니버스 표현을 **검증 전에 떼어** 생성 경로와 같은 체인(카탈로그 후보 2개 이상=범위 되묻기 / 1개=정본 표기 확인 칩(자동 확정 금지) / 0개=KG 직접 조회→검색 학습→되묻기)에 넘긴다. 미지 테마를 검증기에 그대로 넘기면 '지원 섹터 아님' 오류로 수정 레인 전체가 폴백해 요청이 무변경으로 끝난다 ⓒ 적용은 `nl_parser.replace_theme_universe` — **이전 테마에서 온 종목만** 비우고 재조회하며, 사용자가 직접 지목한 종목은 건드리지 않는다(기존 가드 유지), 새 테마 조회 실패 시 원상복구. 정본 섹터로 바꾸는 턴('2차전지 업종으로')도 같은 출처 판정으로 이전 테마 종목을 해제한다(종목 지정이 우선이라 그대로 두면 새 업종이 삼켜짐). 트리거는 `universe.sectors` 패치다 — 별도 필드를 LLM이 채우게 하는 1차 설계는 실측(9B가 생성 규칙 6-0-2와 같은 형태로 낸다)에서 폐기했다. ⓓ 전략 무변경 되묻기(테마 범위·자기 의심·값 없는 수정·개념 질문)는 `clarification_priority`를 달아 프론트 게이트가 삼키지 않게 한다. 회귀: `test_modify_roundtrip_migration.py` 테마 6건. **[⑦ 시장 제약 결정론 반영, 2026-08-02]** 지정 종목 모드는 universe 시장이 실행에 반영되지 않는다(변환기가 target_symbols 우선) — 테마 지정 종목 전략(HBM 33곳)에 "코스피에만 속한 종목으로 변경" 요청 시 인터프리터가 `/universe/markets=[KOSPI]` 패치를 정확히 내고 검증·컴파일을 통과해도 종목 목록이 그대로라 무변경으로 보이던 사고. `nl_parser.filter_target_symbols_by_market`: 유니버스가 단일 시장(KOSPI 또는 KOSDAQ 단독)으로 확정돼 있으면 **테마 유래**(theme_universe 보유) 지정 종목을 종목 마스터(korea-stocks.json) 정본 소속으로 결정론 필터링한다(시장 소속은 지식 조회 — 원문 해석 아님). 가드: 직접 지목 종목(theme_universe=None)은 불변(⑥ ⓒ와 동일 원칙), 필터 결과 0곳이면 미적용(조용한 빈 전략 방지), 마스터에 없는 종목(상폐 등)은 소속 미확인으로 제외. 배선 2곳 — 수정 레인(run_primary_modification 패치 적용 후)과 생성 체인(apply_theme_companies 테마 적용 직후: "코스피에 상장된 HBM 관련주")·테마 교체(replace_theme_universe 경유 시 시장 제약 유지). theme_universe는 보존된다(이후 테마 교체 판정 근거). 회귀: `test_modify_roundtrip_migration.py::test_market_only_patch_filters_theme_symbols`·`test_theme_universe_autoapply.py` 시장 필터 5건. **[⑦-1 시장 전환 재도출 + 미반영 안내, 2026-08-02 2차]** 사고: 코스피로 좁힌 6곳 상태에서 "미안해 코피닥 종목만 선택 해줘" — 인터프리터는 오타를 코스닥으로 정확히 해석해 markets=[KOSDAQ] 패치를 냈으나, 현재 목록에 코스닥이 0곳이라 필터의 빈 목록 가드가 적용을 거부했고 universe만 KOSDAQ으로 뒤집힌 채 안내 없이 끝나 사용자가 '오타 미해석'으로 오인했다. 수정 2겹: ⓐ **테마 전체 재도출** — 현재 목록에 해당 시장 종목이 0이면 목록의 출처인 테마 전체 구성(theme_backtest_companies)에서 다시 좁힌다(시장 전환의 단방향 손실 방지, 코스피 6곳→"코스닥만"=테마 27곳). 현재 목록에 해당 시장 종목이 남아 있으면 재조회하지 않는다 — 수동으로 줄인 목록을 필터가 도로 되살리지 않는다. ⓑ **이해-후-미반영 침묵 금지** — 테마 전체에도 해당 시장 종목이 없으면(`nl_parser.unapplied_market_constraint`) 시장 패치까지 되돌려 전략을 원상 유지하고 "…소속을 찾지 못해 요청을 반영하지 못했어요. 기존 전략을 그대로 유지했어요"를 notices로 알린다(반쪽 상태·무안내 금지). 해석 자체가 실패한 경우(패치 전량 폐기)의 유지 안내는 기존 문구가 담당한다. 회귀: `test_market_switch_rederives_from_full_theme`·`test_unmet_market_constraint_keeps_strategy_and_notifies`.

**FR-STR-071b** [복합 테마구 가드 + 빌더 테마 유니버스 되묻기, 2026-07-25] 시스템은 알려진 테마어에 미지의 수식어가 붙은 **복합 테마구**("반도체 소부장")를 앞 테마어만 잘라 업종으로 단독 확정해서는 안 되며, 빌더 경로에서도 학습·검증된 관련 상장사로 대상을 좁힐 수 있어야 한다(실측 사고 2026-07-25: "반도체 소부장 전략을 만들자"가 업종=반도체로 확정돼 수식어가 조용히 소실됨). ① **복합 테마구 가드**(`nl_parser._compound_theme_hint`): 큐리스 테마어(`_CUE_LESS_SECTOR_TERMS`) 매치 직후의 한글 토큰이 '아는 어휘'(전략 어휘 `_RULE_GUARD_KNOWN_VOCAB`+보강 목록(주도주·수혜주·소재 등)+섹터어+종목명)가 아니면 복합구로 판정 — `_extract_sector`는 단독 확정 대신 그래프(시드·학습) 해석을 시도하고 실패 시 None, `_mentioned_unsupported_concepts`가 업종 큐 없이도 'sector' 미해결로 플래그해 되묻기·검색 학습 게이트(FR-STR-069 ⑥)를 연다. 복합구는 `detect_theme_universe_clarification`의 테마 큐(관련/테마)와도 동급으로 인정된다. 알려진 후속어("반도체 주도주"·"바이오 헬스케어")는 기존 단독 확정을 유지하고, 공백 없는 붙여쓰기는 기존과 동일하게 미감지. ② **큐 없는 미지 테마어(약한 힌트)**(`nl_parser._weak_theme_candidate` + `BuilderState.sector_hint_weak`): 머리명사(전략/종목/주식/투자/포트폴리오) 앞의 미지 한글 명사("소부장 전략")를 빌더 시드에서만 약한 테마 힌트로 그라운딩 체인에 넘긴다. 오탐 여지(수식어)가 있으므로 형용사꼴(ㄴ받침 종결)·아는 어휘는 제외하고, 해석 실패 시 되묻기·안내 없이 조용히 해제한다(강한 힌트(업종 큐·복합구)는 기존대로 되묻기). ③ **검색 학습 우선 순서**(`term_grounding._prefers_search_first`): 복합구·약한 힌트 텍스트는 해석 체인에서 내부 지식 LLM(②)보다 검색 그라운딩(④)을 먼저 시도한다 — LLM이 머리 테마어(반도체)로 근사해 버리면 하위 테마의 정의·관련 상장사가 영영 학습되지 않는 공백 차단. 검색이 업종 매핑에 실패하면 LLM 폴백. 용어 추출 프롬프트는 복합 표현 전체 추출을 지시하고("반도체 소부장"), 추출된 용어가 이미 정본 섹터어면 검색·학습하지 않는다(어휘집 오염 방지 — '반도체' 항목이 학습되면 모든 반도체 언급이 어휘집 히트로 단락). ④ **빌더 테마 유니버스 자동 확정** [2026-07-25 개정 — 되묻기 폐지(사용자 결정)]: 그라운딩/그래프가 테마의 verified 관련 상장사를 알면 빌더는 되묻기 없이 지정 종목 목록으로 즉시 확정한다(`_theme_patch`가 `theme_symbols`·`theme_label` 설정+업종 근사 해제+`theme_reask_done`, 시드 경로·`_consume_sector_notice` 해석 경로 공통). 유니버스 질문은 생략되고 `build_parsed_strategy`가 `target_symbols`로 직접 조립하며(시작일 클램프 없음 — 시점 편향은 파싱 경로 notices가 고지), 합성 프롬프트는 종목명 나열("동진쎄미켐, 원익IPS 종목 중 …" — '업종/테마' 단어 금지, TARGET 가드 함정)로 만든다. 프론트 요약 카드는 `theme_label`을 '대상 종목'으로 표시한다. (종전 `_theme_reask_prompt`/`_answer_theme_reask` 되묻기 기계장치는 제거됨.) 한계: 관련 상장사 목록은 뉴스 co-mention 표본에 의존하며 pending 엣지는 콘솔 승인 전까지 되묻기에 나타나지 않는다(그때까지는 verified 개념 엣지 1홉 폴백(FR-STR-071 ④)이 닿으면 그 개념의 상장사로, 아니면 업종 근사로 동작).

**FR-STR-071c** [테마 카탈로그 표기 정합 우선, 2026-07-27] 관련 종목 조회의 1순위 정본은 외부 카탈로그(네이버 금융 업종별·테마별 종목 — 사용자 지정 1순위 신뢰 소스, 차순위 주달)이며, 뉴스 동시언급 학습 엣지는 카탈로그 미보유 테마의 폴백이어야 한다(실측 사고 2026-07-27: "LCD 부품 관련주"가 카탈로그 'LCD 부품/소재' 44곳 대신 학습 엣지 uses→pcb의 개념 홉(심텍·대덕전자)+지분 홉(심텍홀딩스·대덕)+동시언급(SK하이닉스) 등 무관 종목 5곳으로 왜곡). ① **슬래시 별칭**: 카탈로그 테마명의 슬래시 병기("LCD 부품/소재")는 부분 문자열 스캔에 걸리지 않는 도달 불가 이름이므로, 로더가 결정적 표기 변형("LCD 부품"·"LCD 소재")을 동의어로 생성한다(`knowledge_graph._slash_aliases` — 괄호 안 슬래시 제외, 섹터 어휘·테스트 정본 용어 가드 유지, 의미 해석이 아닌 표기 정규화). ② **학습 앵커 카탈로그 정합**: 검색 학습 노드가 스캔 키를 선점했더라도 표기가 **정확히 일치**(부분·접두 매칭 금지 — FR-STR-071b 가드와 동일 원칙)하는 카탈로그 테마가 있으면(`catalog_theme_nodes`), `theme_listed_companies`는 학습 엣지 대신 카탈로그 수록 종목을 반환하고 `theme_backtest_companies`는 Concept Universe 확장을 생략한다. 카탈로그 정합은 큐레이션 분류라 시점 편향 경고(first_known_date) 대상이 아니다. ③ **네이버 금융 카탈로그 수집**(`scripts/ingest_naver_themes.py`): 업종별·테마별 종목을 주달 카탈로그와 동일한 기계적 가드(정본 심볼·섹터 어휘·시드 중복·테스트 정본 용어)+스코프 제외(인물·정치·이벤트·시장분류 키워드)로 수집해 `data/kg-naver-theme-catalog.json`에 저장하며, 로더는 네이버를 주달보다 먼저 합성한다(같은 표기 겹치면 네이버 승). ④ **게이트 판정 기준 통일**(사고 2차, 2026-07-27): primary 레인의 미해결 섹터 표현 게이트(`primary._sector_terms_for_chain`)는 검증기(capability_validator)와 동일하게 정본 사전(normalize_sector)만으로 판정한다 — 게이트가 KG 층(resolve_sectors)까지 '해석 성공'으로 치면, 검증기가 이미 sectors에서 제거한 표현이 체인에 도달하지 못하고 해석값도 폐기돼 유니버스가 통째로 소실된다. 정본 사전이 못 푸는 표현은 KG가 섹터를 해석할 수 있어도 체인으로 보낸다(테마 상장사 적용이 섹터 근사보다 우선). ⑤ **별칭 일반어 차단**: 슬래시 별칭이 만드는 단독 일반어 조각('카메라모듈/부품'→'부품')은 스캔 어휘가 되면 그 단어를 포함한 모든 질의에 오매칭되므로 차단한다(`_ALIAS_STOPWORDS` — 부품·소재·장비·제품·기기·재료, 수식어 붙은 별칭은 통과). **[2026-07-27 개정 — 전 앵커 확장+라이브 편입(사용자 지시: KG에 없으면 네이버를 항상 우선 검색해 KG에 넣는다)]**: ⑥ ②의 카탈로그 표기 정합을 학습 앵커 한정에서 **전 앵커(시드 포함)**로 확장한다 — 표기가 정확히 일치하는 카탈로그 테마가 있으면 시드 큐레이션 직접 엣지 대신 카탈로그 수록 종목이 유니버스 정의('온디바이스 AI' 시드 2곳 vs 네이버 24곳), 표기 불일치 개념(HBM vs "HBM(고대역폭메모리)")은 시드 직접 엣지 유지. 이에 따라 ③의 네이버 수집에서 시드 중복 가드를 폐지한다(시드와 같은 이름의 테마도 수집 — 스캔 인식은 여전히 시드 우선). ⑦ **네이버 라이브 편입**(`engine/naver_theme_live.py`): KG가 해석하지 못한 테마 용어의 검색 레인(`term_grounding` ④)은 뉴스 검색 학습 전에 네이버 금융 테마·업종 목록을 라이브 조회해 표기 정합(원명·괄호 제거 본체·슬래시 변형, 정확 일치만)을 찾고, 정합 시 수록 종목을 네이버 카탈로그 파일에 병합 저장한다(그래프 mtime 재로드로 즉시 결정적 해석 — 같은 용어 재검색 없음). 정합 없음·수집 실패는 기존 뉴스 검색 학습으로 폴백하며, 배치 수집과 파서·스코프 가드를 공유한다. **[2026-08-02 개정 — 괄호 표기 변형 파생 키]**: ⑧ 정합 인덱스(`_build_catalog_index`)는 괄호 병기 테마명("HBM(고대역폭메모리)")의 결정적 표기 변형 — 괄호 제거 본체("HBM")와 괄호 안 토큰("고대역폭메모리") — 을 파생 키로 더한다(`knowledge_graph._paren_variants`). ingest의 괄호 동의어 승격(make_synonyms)이 시드 중복 토큰을 스캔 어휘 오염 방지로 버려, 시드 앵커(HBM)가 같은 개념의 카탈로그 테마와 영영 정합하지 못하던 공백 보정(실측 사고 2026-08-02: 'HBM 관련주'가 시드 직접 엣지 6곳으로 확정 — 네이버 'HBM(고대역폭메모리)' 33곳 미도달). 등록 규칙: ⓐ 정확 표기 키 항상 우선 — 파생 키가 다른 테마의 정확 표기('전기차')를 가로채지 않는다 ⓑ 카탈로그 간 충돌은 먼저 합성된 네이버 승(_catalog_paths 순서 계약과 동일 — 'hbm': 네이버 'HBM(고대역폭메모리)' vs 주달 '반도체 제품(HBM/HBM3E)') ⓒ 같은 카탈로그 안 다의 파생 키('보안주(정보)'/'보안주(물리)' → 보안주, '원자재(리튬)' 등 9종 → 원자재)는 미등록 — 부분 매칭 자동 확정 금지(FR-STR-071b)와 동일 원칙, 되묻기 선택지(catalog_theme_candidates)로만 남는다 ⓓ 괄호 토큰은 ingest와 동일 일반어 가드(라틴/숫자 포함 또는 한글 4자 이상 — '정보'·'충전소' 같은 조각 차단)+별칭 일반어·테스트 정본 용어·섹터 어휘 가드. 파생 키는 정합 인덱스 전용이며 스캔 어휘에는 영향이 없다(앵커 인식 불변). ⑥의 "표기 불일치 개념(HBM)은 시드 직접 엣지 유지"는 파생 키 정합이 닿는 범위에서 폐지된다. 회귀: `test_knowledge_graph.py::test_catalog_paren_derived_keys`·`test_hbm_real_catalog_universe_composed`.

**FR-STR-072** [Concept Universe Builder — 개념 중심 유니버스 결정론 생성, 2026-07-25] 시스템은 Concept(테마·기술·제품·인물 IP 등) 입력에 대해 업종(Sector) 전체가 아니라 **해당 Concept와 사업적 관련이 검증된 종목 집합**을 결정론적으로 생성해야 한다(`engine/concept_universe.py::build_concept_universe`). ① **관련도 산출(LLM 자기평가 금지)**: score(0~1)는 KG에 축적된 근거에서만 결정론 산출한다 — 시드 엣지는 note의 원장 점수 "(Core 95)"/"(Producer/Strong 72)" 파싱(표기 없으면 0.70 — 시드 편입 규약상 최소 등급), 학습 verified related_company는 출처 수 기반(0.55+0.05×support, 상한 0.80), verified 개념 1홉 경유는 해당 종목 점수 ×0.85(거리 감쇠), 카탈로그 테마는 0.45(기본 임계 미만 — 완화 단계에서만). 심볼 중복은 최고 점수 경로만 유지하고 pending/rejected 엣지는 어느 층에도 불참한다(FR-STR-070b 검증 게이트와 동일). ② **선정 규칙**: score ≥ 0.5 기본, 결과가 10개 미만이면 점수순으로 floor 0.30까지 완화하되 **후보 자체가 부족하면 있는 만큼만 반환**한다('최소 10개 보장'을 위한 억지 채움은 억지 테마주 제외 원칙과 모순 — 스펙 대비 의도적 완화). 30개 초과분은 점수순 상위 30개. 크기 경계(완화 중단·상한)가 동점 그룹 한가운데를 지나면 동점 전체를 포함한다 — 같은 근거 점수의 종목 일부만 심볼 번호순으로 남기는 절단은 근거 기반 선정이 아니다(2026-07-28 '비만치료 관련주' 사고: 학습 동률 0.60 36곳이 상한·상한 하류 절단으로 10곳까지 줄어 유니버스가 됨). 정렬은 점수 내림차순+심볼 오름차순 tie-break로 동일 입력에 항상 동일 출력(재현성). 적용 임계는 `threshold_used`/`relaxed` 메타데이터로 투명하게 기록한다. ③ **이유(reason)**: 시드=원장 note(점수 괄호 제거), 학습="검색 출처 N건 함께 언급", 홉="{개념명} 경유 — …" — 전부 저장된 근거의 표시이며 생성이 아니다. ④ **진입점**: `GET /knowledge/concept-universe?q=`(읽기 전용)+CLI `scripts/concept_universe.py`. **테마 되묻기 통합**(2026-07-25 — 'bts 관련 종목' 사고 2차): 전략 대화의 테마 유니버스 되묻기(FR-STR-071)·빌더(`strategy_builder._theme_companies`)는 정밀 목록 대신 확장 뷰 `knowledge_graph.theme_backtest_companies`를 소비한다 — **학습 앵커 한정**으로 Concept Universe 선정(기본 임계 0.5 이상만 — 완화 편입은 백테스트 제안에 불참)으로 후보를 확장하고(직접 학습 엣지 2곳이 컨셉을 대표하지 못하던 문제), 시드·카탈로그 앵커는 큐레이션 직접 엣지 그대로(지분 홉 노이즈 차단 — HBM 되묻기에 지주·계열 편입 방지), 직접 학습 엣지의 뉴스 보도일은 심볼 매칭 이월(시점 편향 경고 유지). `theme_listed_companies`(정밀 목록 — 직접 엣지 우선·이웃 개념 희석 금지) 계약은 불변. 프론트는 `clarification_priority=theme_universe` 되묻기를 explicit 설정 게이트(시장 질문)보다 먼저 표시한다 — 게이트가 이 질문을 삼키면 컨셉 종목 제한 선택지가 사라지고 업종 전체로 조용히 강등된다(실측 회귀, `page.scroll.test.tsx` 가드). ⑤ **규제 안전**: score·이유·정렬은 공시·IR·검색 출처 등 객관적 관계 근거의 표시일 뿐 추천·전망·우열 판단이 아니다. 모르는 개념은 found=false(생성 거부 — 검색 그라운딩 학습 경로로 유도). 실측: BTS→6종목(하이브 0.81 최상위, 미디어/엔터 업종 전체 아님), HBM→6종목(생산 2+장비·소켓 4).

**FR-STR-072b** [지분 관계 레이어 — DART 타법인출자현황 기반 회사 홉, 2026-07-25] Concept Universe는 검색 co-mention이 확률적으로만 잡는 지분 관계('넷마블=하이브 주요 주주')를 **공시 데이터에서 결정론 수집**해 반영해야 한다. ① **수집**(`scripts/build_equity_edges.py`): DART 사업보고서 '타법인 출자현황'(otrCprInvstmntSttus)을 전 상장사 대상으로 스윕해, 피출자 법인명을 정본 종목 마스터에 정규화 매칭(㈜·괄호 병기 제거, 정확 일치만 — 부분 매칭 오탐 차단)하고 **양쪽 모두 상장사 + 기말 지분율 ≥ 5%**인 관계만 `invests_in` 엣지로 `data/kg-equity-edges.json`(git 추적 — 커밋·배포로 prod 반영)에 저장한다. 재개 가능(진행 파일 gitignore)·`--symbols` 부분 수집은 기존 산출물에 병합. 표시명은 DART 원문('㈜하이브 (주1)')이 아니라 정본 종목명. ② **소비 범위 한정**: 이 엣지는 KG 그래프 본체에 합성하지 않고 Concept Universe만 읽는다(mtime 캐시) — related_universe 확장·테마 되묻기 등 기존 그래프 소비자의 의미 변화를 차단한다. ③ **회사 홉**: 유니버스 후보의 주주/피출자사를 후보 점수 ×0.70 감쇠로 1단계만 편입한다(체이닝 금지). 감쇠 0.70이면 부모 점수 0.72 이상만 기본 임계(0.5)를 넘으므로 재벌 지주 관계가 모든 유니버스로 번지지 않는다(자기 제한 — 저점수 부모의 지분 이웃은 완화 단계에서만). 이유는 "{부모명} 주주(공시 근거) — {지분율 note}"로 공시 출처를 명시한다. 실측: 넷마블→하이브 9.2%(2025 사업보고서) 수집, BTS 유니버스에 넷마블 0.57 편입. 한계: 사업연도 시점 기준(연 1회 갱신 권장), 벤처펀드 경유 간접 투자(LB인베스트먼트→하이브)는 공시 비노출 — 수동 엣지(FR-STR-070b ⑦)가 담당.

**FR-STR-073** [신규 상장(IPO) 유니버스, 2026-07-29] 시스템은 "2026년 신규 상장 종목 투자 전략", "2025년 이후 상장한 종목"처럼 **상장 시기로 대상을 좁히는 유니버스 제한**을 지원해야 한다. ① **의미론 — 코호트**: "2026년 신규 상장 종목"은 **상장일이 그 구간에 속하는 종목 집합**이다(양끝 포함). 종목의 상장일 하나로 결정되므로 정적 심볼 필터로 충분하며, 섹터 필터와 같은 자리에서 같은 방식으로 걸러진다(`universe_pit.filter_by_listing_window`). 코호트 소속은 시간이 지나도 만료되지 않는다 — 2026년 상장 종목은 2027년에도 '2026년 상장 종목'이다. 상장 이전 구간은 애초에 가격 데이터가 없어(available_df) look-ahead가 생기지 않는다. **롤링('상장 후 N일 이내')로 구현하지 말 것** — 2026-07-29 실측: 롤링 마스크는 유니버스 목록을 전 시장으로 남겨 사용자에게 "코스피·코스닥 전체"로 보였고, 사용자가 요구한 것은 코호트였다. ② **상장일 SOT**: `data/stock-master.json`의 `listingDate`. 상폐 종목은 FDR `KRX-DELISTING`이 상장일을 함께 주므로 이미 채워져 있었고, 현행 상장 종목은 FDR `StockListing("KOSPI"/"KOSDAQ")`에 상장일 컬럼이 없어 null이었다 — FDR `KRX-DESC`(KIND 상장법인목록, 무료·인증 불필요)에서 백필한다(`scripts/backfill_listing_dates.py` 제자리 패치·멱등, `build_stock_master.py::load_kind_listing_dates`가 재빌드 시 같은 소스로 직접 채움). 실측 커버리지(2026-07-29): 현행 상장 보통주 2,642종목, 미커버 126종목은 우선주 113 + KIND 미등재 구종목 13(모두 유니버스에서 이미 배제되거나 상장일이 충분히 오래됐다). KRX Open API `sto/stk_isu_base_info`의 `LIST_DD`도 같은 값을 주지만 서비스 승인이 필요해 현재 401이다. ③ **최초 상장일 = min(listingDate, dataStart)**: KIND 상장일은 '현재 시장에 상장한 날'이라 이전상장·재상장 종목(실측: 지에프씨생명과학 `listingDate`=2025-06-30이지만 2022-12-23부터 거래)이 신규 상장으로 둔갑한다. 로컬 가격 데이터 시작일은 실제 첫 거래일보다 이를 수 없으므로 둘 중 이른 쪽이 '처음 상장한 날'의 최선 추정이다(`universe_pit.first_listed_date`). 상장일도 데이터 시작일도 없는 종목은 조용히 통과시키지 않고 **제외 후 경고**한다. ④ **생존 편향 없음**: 상폐 종목도 상장일을 갖고 있어, 그 해 상장했다가 이후 상폐된 종목이 코호트에 그대로 포함된다. ⑤ **개념과 구간의 분리**: "신규 상장 종목"에는 시기가 없다. 날짜를 지어내면 무단 확정이고 개념까지 비우면 사용자가 말한 제한이 조용히 사라지므로, 조건의 factor/value와 같은 방식으로 **개념(`new_listing_only`)과 구간(`listing_from`/`listing_to`, YYYY-MM-DD)을 분리**한다 — 개념만 있으면 완결성 검증이 대상 시기를 되묻고(칩: 올해/작년 상장·최근 1년/3년 내 상장), 구간이 정해지기 전까지 엔진에는 아무것도 넘어가지 않는다(`compile_partial`). 구간이 있으면 개념은 자명하므로 스키마가 정규화한다(양 레이어 `UniverseSpec`·`ParsedStrategy` 동형). ⑥ **백테스트 창 하한 클램프**: 2026년 상장 종목을 2022년부터 백테스트하는 것은 불가능하다(그 종목들이 존재하지 않던 구간). `enforce_strategy_minimums`가 창 시작을 `listing_from`으로 끌어올리고 사실을 안내한다 — 종료일은 건드리지 않는다(상장 후 보유는 정상). 연도 언급은 **상장 시기이지 검증 기간이 아니다**(인터프리터 프롬프트 규칙 6-0-3) — '2020년부터 백테스트'처럼 검증 기간을 따로 말한 경우에만 `backtest.start_date`를 채운다. 프론트의 기간 배지도 명시 날짜가 있으면 상대 기간 라벨("5년") 대신 실제 창을 보여준다(라벨과 실행 구간이 어긋나던 2026-07-29 사고). ⑥-1 **확정된 창을 다시 묻지 않는다**: 창이 코호트로 확정되면 백테스트 기간 슬롯은 **질문이 끝난 필드**다(`strategy_slots._decided` ③). 이 판정이 provenance가 아니라 `_decided`에 있어야 하는 이유는, provenance는 "사용자가 말했나"만 답하므로 시스템이 결정했고 협상 대상도 아닌 값을 표현할 수 없어 영원히 '미언급'으로 남기 때문이다 — 실측 사고 2026-07-29: 요약 카드에 "2026-01-01 ~ 현재"가 떠 있는데 "어느 기간의 과거 데이터로 백테스트할까요?"를 다시 물었고, 사용자가 "최근 5년"을 골라도 클램프가 도로 덮어쓴다. **판정을 한 곳에 모으는 것만으로는 부족하고, 그 곳이 표현할 수 있는 축이 실제 사례를 모두 덮어야 한다**(FR-STR-019m의 SOT 계약 보강). 프론트는 게이트·진행률 패널이 **같은 술어 하나**(`backtestReadiness.isSlotFilled`)만 부르도록 통합했다 — 게이트만 고치고 패널이 낡은 채 남은 것이 이 사고의 재발 경로였고, 같은 통합이 그때까지 숨어 있던 패널 드리프트 3종을 함께 드러냈다(손절 배지만으로 '매도 조건' 완료 표기, 손절·익절 중 하나만으로 '리스크 관리' 완료 표기, 리밸런싱 '안 함' 결정을 패널이 입력으로 받지 못해 미완료 표기). 계약 픽스처는 '첫 빈 슬롯'만 내보내던 것을 **슬롯별 정답**(`expectedFilledSlots`)까지 내보내도록 확장했다 — 슬롯별로 표시하는 소비자에게는 대조할 정본이 아예 없었던 것이 드리프트가 오래 살아남은 이유다(뮤테이션 검증: 술어 규칙을 하나씩 훼손하면 게이트·패널 양쪽에서 해당 케이스만 실패). ⑦ **유니버스 슬롯 판정**: 신규 상장 지정은 그 자체로 유니버스 명시다(`strategy_slots._has_value`·프론트 `backtestReadiness` 동시 갱신, 계약 픽스처 케이스 추가) — 대상 시기를 되묻는 중이라고 "어떤 시장을 대상으로 할까요?"를 다시 묻지 않는다. provenance(`explicit_fields_from_spec`)도 universe 명시로 센다. ⑧ **기본 시장**: 신규 상장은 대부분 코스닥에 들어오므로 시장 미언급 시 기본값은 KOSPI200이 아니라 양시장이다(섹터 전략의 FR-STR-066 ③과 같은 이유). ⑨ **ETF 배제**: ETF 마스터에는 상장일이 없고 '신규 상장 ETF'는 IPO와 성격이 다르다 — 조용히 무시하지 않고 명시적 미지원으로 알린다(`capability_validator`). ⑩ **공집합 fail-fast**: 구간에 상장한 종목이 하나도 없으면 0거래로 조용히 끝내지 않고 명시적 에러를 낸다(섹터 필터 공집합과 같은 계약). ⑪ `listing_from`/`listing_to`는 canonical DSL(해시)과 `BacktestRequest` 스키마에 포함한다(미선언 시 `model_dump`가 조용히 버림 — `ranking_metric` 0거래 사고와 같은 함정). 되묻는 중인 개념(`new_listing_only`만 참)은 실행 결과를 바꾸지 않으므로 해시에 넣지 않아 기존 전략 해시가 변하지 않는다. ⑫ **빌더 레인 관통**: 전략 빌더는 별도 상태 모델(`BuilderState`)로 슬롯을 모아 마지막에 DSL을 직접 조립하므로, 인터프리터가 해석한 유니버스 제한을 `apply_parsed_seed`가 이어받지 않으면 최종 전략에서 통째로 사라진다 — 실측: "2026년 신규 상장 종목 투자 전략"이 코스피·코스닥 전 종목(삼양홀딩스·CJ대한통운 등) 백테스트로 나갔다. ⑤의 개념/구간 분리를 `BuilderState`에도 그대로 두고, 개념은 시드로 이어받고 대상 시기는 **유니버스 다음 스텝**(`listing_period`)에서 묻는다. 이 스텝의 연도·기간 표현은 전용 파서(`_parse_listing_period` — 4자리 연도는 코호트, '이후/부터'면 상한 없음, 상대 기간은 오늘 기준 하한, 맨숫자는 모호해 미해석, 미래 연도는 거부)가 먼저 소비한다 — 공통 파서로 흘리면 '3개월'이 모멘텀 룩백으로 오귀속된다. `build_parsed_strategy`가 DSL에 싣고, DSL을 만들 수 없는 custom 유형은 `synthesize_prompt`가 문장에 남겨 재파싱이 복원한다. 지정 종목·테마 목록·ETF 모드는 적용 대상이 아니라 묻지도 싣지도 않는다. 빌더 진행 카드의 유니버스 라벨에도 제한을 덧붙인다(시장명만 보이면 전 종목 대상으로 읽힌다). 회귀: `test_new_listing_universe.py`(코호트 필터·만료 없음·상장일 미상·공집합), `test_universe_pit.py`(최초 상장일 추정·이전상장·상폐 포함·연도 코호트·개방 상한), `test_strategy_conversation.py`(되묻기·컴파일·창 클램프·ETF 배제·라운드트립), `test_strategy_builder.py`(시드 이어받기·스텝 질문·연도/상대 기간 파싱·DSL 반영·지정 종목/ETF 배제), `test_strategy_slots.py`(코호트 기간 재질문 금지·값/provenance 필드 집합 일치·가드 비확산), `backtestReadiness.parity.test.ts`(게이트·진행률 패널 두 소비자 × 27케이스 슬롯별 대조).

**FR-BT-016** [데이터 커버리지 투명성, 2026-07-14] 백테스트 결과는 전략이 참조한 데이터 의존 지표(펀더멘털 필터: PER/PBR/PSR/EV-EBITDA/ROE/ROA/마진·성장률/시가총액/배당수익률·배당성향 등)가 백테스트 창에서 실제로 얼마나 존재했는지를 종목·기간 두 축으로 집계한 `dataCoverage` 리포트를 포함해야 한다(`engine/data_coverage.py`). 각 지표에 대해 (기간 커버리지 %, 종목 커버리지 %, 데이터 존재 종목 수, 사용 가능 시작·종료일, used/partial/unused 분류)를 산출하고, 데이터 부족은 숨기지 않고 결과 로그에 투명하게 드러내야 한다. 데이터가 전혀 없으면(unused) "해당 조건은 적용되지 않았다", 기간 커버리지가 60% 미만이면 "결과 해석에 주의가 필요하다", 일부 종목만 데이터가 있으면 "나머지 종목에는 조건이 적용되지 않았다"는 경고를 `warnings` 채널에 합류시켜 사용자가 결과를 오해하지 않게 한다. 기술적 지표(OHLCV에서 항상 계산)는 커버리지 변동이 없어 추적 대상에서 제외한다. (스키마가 표현할 수 없는 진짜 미지원 개념은 파싱 시점 FR-STR-023d의 notices가 담당하고, '지원되지만 데이터가 희소한' 경우를 이 리포트가 담당한다 — 둘이 함께 데이터 부족 전 구간을 정직하게 커버한다.)

#### 3.2.3 성능 메트릭

**FR-BT-020** 백테스트 결과는 다음 메트릭을 포함해야 한다:

| 메트릭 | 설명 |
|--------|------|
| Total Return | 총 수익률 (%) |
| CAGR | 연평균 복리 수익률 (%) |
| Buy & Hold Return | 벤치마크 지수 ETF 매수 후 보유 수익률 (비교용, FR-BT-020d) |
| Max Drawdown (MDD) | 최대 낙폭 (%) |
| Sharpe Ratio | 위험 조정 수익률 |
| Sortino Ratio | 하방 위험 조정 수익률 |
| Win Rate | 승률 (%) |
| Profit Factor | 총이익 / 총손실. 손실 거래가 0건이면 정의되지 않으므로 `null`(표시는 ∞) |
| Kelly Criterion | 켈리 기준 최적 베팅 비율 (%) = W − (1−W)/R, R = 평균수익률 ÷ 평균손실률. 승·패 한쪽 표본이 없으면 `null` |
| Volatility | 연 환산 변동성 (%) |
| Exposure | 포지션 보유일 비율 (%) |
| Max Drawdown Duration | 최장 수중(underwater) 기간 (거래일) |
| Expectancy | 평균 거래 수익률 (%) |
| Recovery Factor | 순이익 / 최대 낙폭 금액 |
| 월별/연도별 수익률 | 기간별 수익 분해 (달력 월 기준, 월말 equity 대비) |
| 롤링 수익률 | 매 거래일 기준 직전 1/3/6/12개월 구간 수익률 라인 차트 — 월별 수익률 표와 탭으로 전환, 불완전 창(백테스트 시작 이전으로 나가는 구간)은 제외 |
| 종목별 통계 | 개별 종목 성과 분석 |

**FR-BT-020b** Profit Factor 등 통계는 계산값을 조작 없이 그대로 보고해야 한다(클램프·조건부 재정의 금지). 소표본(거래 30건 미만)은 값 조작 대신 경고로 고지한다. Sortino의 하방편차는 전체 기간에 대한 목표 미달분 RMS(표준 정의)로 계산하며, Sharpe/Sortino는 연 무위험수익률 옵션(`risk_free_rate`, 기본 0)을 지원해야 한다. (감사 C3/H4/M7)

**FR-BT-020d-1** 연환산 기준은 전 지표가 하나를 공유해야 한다(엔진 v12.0). 연수는 **달력 경과일 ÷ 365.25**로 세고(거래일 수 ÷ 252는 KRX 실제 거래일 연 246.5일보다 분모가 커서 CAGR을 약 2% 과대계상한다), Sharpe·Sortino·Volatility의 연환산 계수는 KRX 실측 √246, 표준편차는 표본(ddof=1)을 쓴다. 1년 미만 구간도 CAGR을 정의대로 연환산하되(총수익률을 CAGR 칸에 그대로 넣지 않는다) 연환산이 잡음을 증폭한다는 사실을 경고로 고지한다. 종목별 CAGR은 같은 행 `totalReturn`과 **같은 분모**(해당 종목 누적 진입원가)를 써야 한다.

**FR-BT-020d-2** 값이 정의되지 않는 지표는 0으로 채우면 안 된다. Profit Factor는 손실 거래 0건이면 분모가 0이라 `null`(=∞)로, Kelly는 승·패 한쪽 표본이 없으면 `null`로 내보내고, 표시·저장·AI 리포트 프롬프트 어느 경로에서도 `?? 0`으로 합치지 않는다(전승한 전략이 손익비 0=최악으로 표시되던 회귀). 숫자 서식(`:.2f` 등)을 강제하는 소비처(백엔드 디버그 로그·최적화 리포트)는 `null`을 문자열(∞)로 우회해야 하며 — 서식 예외가 응답 500으로 둔갑한 사고 — 점수·랭킹 소비처(종합 점수·배치 랭킹 스냅샷·리서치 최소 손익비 게이트)는 `null`을 상한(999/∞)으로 접는다. 0으로 접는 소비처가 하나라도 남으면 같은 사고가 재발한다. 초과수익(α)은 **같은 기간 기준**끼리만 뺀다 — 연율값(CAGR)에서 벤치마크 구간 누적 수익률을 빼지 않으며, 벤치마크가 구간 일부만 덮으면(`benchmark_partial`) 값을 내지 않는다.

**FR-BT-020c** 시스템은 결과 신뢰성에 영향을 주는 요인을 경고 채널로 공시해야 한다: 매도 거래세 반영 여부, 소표본 통계, 벤치마크 ETF 상장 이전 구간, 벤치마크 분배금 미반영(전략만 토탈리턴), 대형주 판정의 정적 주식수 근사, AI 모델 학습기간과 백테스트 기간의 중첩(인샘플 편향), 리밸런싱 비중 미리셋, 전일 거래대금 한도를 초과한 매수 체결(시장충격 위험). (감사 H1/H2/H5/H7/H8)

**FR-BT-020d** [벤치마크 선택·커버리지, 2026-08-07 / 엔진 v11.0] 벤치마크는 "이 전략을 쓰지 않았다면 대신 들고 있었을 것"의 대체재여야 하므로, 백테스트가 실제로 다루는 시장을 따라가야 한다. ⓐ [시장 판정] `universe_id`의 시장 토큰으로 지수 ETF를 고른다 — 코스닥 단독(`kosdaq`·`kosdaq150` — 코스피200과 달리 별도 지수 ETF를 쓰지 않아 코스닥 전체와 같은 상품이 벤치마크다)은 KODEX KOSDAQ 150, 코스피를 포함하면(코스피+코스닥 혼합 포함) KODEX 코스피, 그 외(kospi200·etf)는 KODEX 200. 혼합 유니버스는 대형주 200종목 지수보다 코스피 전 종목 지수가 가깝다(회귀 전에는 코스닥을 먼저 검사하는 순서 탓에 KODEX KOSDAQ 150과 비교됐다). ⓑ [심볼 기반 추론] 지정 종목·테마 유니버스는 `strategy_converter`가 `universe_id`를 `None`으로 지우므로 시장 정보가 사라진다 — 이 경우 보유 심볼의 실제 시장을 마스터의 `market` 필드로 다수결 판정해(`universe_pit.dominant_market`, 동수는 KOSPI) 벤치마크를 고르고, 판정 불가(ETF 등)면 KODEX 200으로 둔다. 회귀 전에는 코스닥 종목만 담긴 백테스트도 항상 KODEX 200과 비교됐다. ⓒ [커버리지] 벤치마크 지수가 아직 존재하지 않던 구간은 값을 채우지 않는다 — 수익곡선(`benchmark_equity`)의 해당 구간은 `null`로 내보내며, 0이나 초기자본으로 채워 "그때 벤치마크는 제자리였다"는 평탄한 가짜 선을 그리지 않는다. `buyAndHoldReturn`은 벤치마크가 실제로 존재한 구간 기준이다(뒤채우기 구간은 수익률 0%라 누적곱이 같아 값 자체는 종전과 동일하다). ⓓ [기간 불일치 공시] ⓒ의 결과로 벤치마크는 자기 존재 구간만, 전략은 전체 구간을 복리로 쌓으므로 두 값의 기간이 다르다. 이 불일치는 데이터로 메울 수 없으므로 FR-BT-020c의 경고 채널로 고지해야 하며, 값을 보정해 감추지 않는다. ⓔ [라벨 정본] 표시용 벤치마크 이름은 엔진이 내려주는 `benchmark_label`이 정본이다 — 프론트가 `universeId`로 다시 추정하면 ⓑ의 심볼 기반 판정과 어긋난다.

**FR-BT-020e** [초과수익률 표시, 2026-08-08] 백테스트 결과 화면은 전략 수익률과 벤치마크 수익률의 차이를 **초과수익률**로 표시해야 한다(결과 화면 '리스크 및 성과 분석' 첫 행, 최종 자산 오른쪽). ⓐ [정의·단위] `초과수익률 = 전략 총수익률(%) - 벤치마크 총수익률(%)`이며 단위는 **%p**(퍼센트 포인트)다 — CAGR 기준이 아니다(엔진이 벤치마크 CAGR을 산출하지 않으며, 두 값을 서로 다른 기간 환산 규칙으로 계산하면 잣대가 어긋난다). ⓑ [부호 무관] 두 수익률이 모두 음수여도 산술 차이는 그대로 성립한다. 다만 이때의 양수 초과수익률은 '덜 하락했다'는 뜻이지 이익이 아니므로 툴팁에 이를 명시해야 하며, 손실을 성과로 보이게 하는 색 강조를 쓰지 않는다(같은 행의 다른 지표와 동일한 무채색 표기). ⓒ [비교 불가 시 숨김] `benchmark_partial`이 true면(FR-BT-020d ⓒ/ⓓ — 벤치마크가 구간 일부만 덮어 두 수익률의 기간이 다름) 숫자를 내지 않고 `-`로 표시한다. 기간이 다른 두 값의 차이는 비교값이 아니므로, 경고 문구를 옆에 다는 것으로 대체하지 않는다(사용자는 숫자를 읽고 경고는 읽지 않는다). ⓓ [규제] 초과수익률은 과거 데이터 기준 사실 표시로만 쓴다 — '우수/선방' 같은 평가 표현, 전략 간 우열 판단, 전략 목록의 기본 정렬 키로 사용하지 않는다(투자 추천 금지 원칙).

**FR-BT-021** 백테스트 결과는 에퀴티커브(자산 가치 추이), 거래 내역(매수/매도 시점, 가격, 수익), 종목별 기여도를 시각화해야 한다.

**FR-BT-022** [전략 검증 전문가 리포트, 2026-07-21] Premium AI 백테스트 리포트는 화면에 이미 표시된 지표 수치를 다시 읽어주는 요약이 아니라, "왜 이런 결과가 나왔는지 / 무엇을 아직 신뢰하면 안 되는지 / 다음에 무엇을 검증해야 하는지"에 답하는 **전략 검증 전문가(Strategy Validation Expert)** 리포트를 생성해야 하며, 다음 10개 섹션으로 구성한다: ① 핵심 요약(Executive Summary) ② 핵심 통찰(Top Insights) ③ 강점 ④ 약점 ⑤ 숨은 위험(Hidden Risks) ⑥ 과최적화 분석 ⑦ 전략 성향(Strategy Profile) ⑧ 검증 로드맵(Validation Roadmap) ⑨ 개선 우선순위 ⑩ 최종 평가(Final Verdict). 정확도가 중요한 항목(과적합 등급·전략 성향 태그·검증 로드맵·개선 우선순위)은 결정론으로 산출하고 LLM은 그 근거 위에서 서술만 담당해야 한다(기존 하이브리드 정책 확장). ⓐ [결정론 근거 pack] 엔진이 이미 계산한 확장 지표(`monthlyReturns`/`yearlyReturns`로 수익 시간 집중도, `maxDrawdownDuration`로 수중 지속, `expectancy`·`winRate`로 '높은 승률·낮은 기대수익', `trades`로 표본 적정성, `avgHoldingDays`·연 거래수로 회전율, `perAssetStats`로 종목 집중)를 해석된 fact 문장으로 만들어 프롬프트에 주입해 근거 없는 추측을 막는다(`backend/ai/report_evidence.py::build_evidence_pack`). ⓑ [숫자 반복 금지·위험 우선·추천 금지] 프롬프트는 '화면의 숫자를 그대로 다시 읽지 말고 의미를 설명', '근거 필수', '장점보다 위험 먼저', '투자·종목·매수/매도 시점·전략 추천 금지, 다음에 무엇을 검증할지에 초점'을 명시해야 한다. ⓒ [검증 로드맵] 거래수 적음→몬테카를로, 성과 시간 집중→워크포워드, 짧은 기간→장기 백테스트, 단일 시장→다른 시장, 소수 종목→종목 확대, 파라미터 존재→민감도 분석을 결정론 규칙으로 각 항목에 '왜/지금' 근거와 함께 제시하되, 특정 파라미터 값을 담은 실험 제안(advisor `suggested_experiments`)은 로드맵에 병합하지 않는다(구체적 DSL 값 제안 회피). ⓓ [점수 인지형 개선 우선순위 — DSL 금지] 개선 우선순위는 전략 점수를 고려해 분기해야 한다: 점수가 높으면(신뢰도 충분) 전략 수정 대신 추가 검증(워크포워드·몬테카를로·민감도)을, 점수가 낮거나 구조적 문제가 명확하면 검증 반복 대신 전략 수준 방향성(구조 단순화, 아이디어 재검토, 특정 시장 과의존 확인, 재구성 후 재백테스트)을 권해야 한다. 어느 경우에도 구체적 DSL 수정(특정 손절/익절 값, 지표 추가/삭제, 파라미터 값 변경, 신규 매수/매도 조건)은 제안하지 않는다. LLM 출력은 서술 8섹션(executive_summary·top_insights·strengths·weaknesses·hidden_risks·overfitting_analysis·strategy_profile_note·final_verdict) JSON으로만 받고, 등급·태그·로드맵·개선안 구조는 코드가 결정론적으로 병합한다. 파싱 실패(프롬프트 에코·미닫힘 `<think>`)는 `degraded`로 표시해 캐시·저장하지 않고 재생성을 유도한다(FR-BT-022는 FR-BT-016·FR-BT-020c의 투명성 원칙과 함께 결과 오해 방지를 담당). 화면은 SCORE 게이지 + 3 다이얼(성장성/안정성/일관성) 헤더를 유지하고 그 아래 10섹션을 배치하되, 핵심(핵심 요약·핵심 통찰·숨은 위험·최종 평가)은 펼치고 나머지는 접어(점진적 표시) 보여준다.

#### 3.2.4 백테스트 이력 관리

**FR-BT-030** 시스템은 백테스트 실행 이력을 저장하고 조회할 수 있어야 한다.

**FR-BT-031** 백테스트 이력은 전략명, 유니버스, 조건, 핵심 메트릭(CAGR, MDD, Sharpe), 실행 일시를 포함해야 한다.

**FR-BT-031b** [이력 이름 정본, 2026-07-25] 백테스트 기록 카드의 이름은 사용자가 저장한 전략명 또는 사용자 프롬프트여야 하며, 캐시 저장 경로가 붙이는 해시 자리표시자(`전략 <8자해시>`)가 노출되면 안 된다. 같은 `cacheKey` 행에 두 저장 경로가 경합한다: ① 클라이언트 자동 저장(`POST /api/backtest/history`)은 result 이벤트 수신 즉시 실행되고, ② 서버 캐시 저장(`saveCachedResult`)은 SSE 스트림 종료 후에 실행되므로 ②가 뒤늦게 ①의 행을 덮어쓸 수 있다. 따라서 두 경로 모두 상대의 결과를 되돌리지 않아야 한다 — ①은 기존 이름이 자리표시자가 아닐 때만 유지하고(`isPlaceholderStrategyName`), ②는 기존 이름이 자리표시자일 때만 이름을 갱신하며 이미 노출된 행(`isVisible=true`)을 다시 숨기지 않는다.

**FR-BT-031c** [기록 목록 표시 캐시, 2026-08-13 개정] 백테스트 기록 목록(`/backtest`)은 사용자가 **방금 실행·저장한 기록이 빠진 목록을 보여서는 안 된다.** 목록은 클라이언트가 조회하며(`GET /api/backtest/history`), 조회 결과는 세션 메모리 캐시(`lib/backtest-history-cache.ts`)에 담아 다음 진입에 즉시 그린다(로딩 없음) — 이 캐시는 목록이 바뀌는 순간 **반드시 버려야** 한다: ① 결과 자동 저장과 ② 전략 저장 시의 `POST /api/backtest/history`(`components/strategy/backtest/BacktestDashboard.tsx`)는 요청 발행 시점에 `invalidateBacktestHistoryCache()`를 호출하고, ③ 카드 삭제는 지운 항목을 뺀 목록으로 캐시를 갱신한다(`app/backtest/BacktestHistoryView.tsx`). 캐시가 없으면 로딩 인디케이터를 노출한다(`app/backtest/BacktestHistoryLoading.tsx` — 라우트 fallback `loading.tsx`와 공용). 목록 조회 본체는 `lib/server/backtest-history-list.ts`를 `/api/backtest/history` GET과 공유해 경로가 갈라지지 않게 한다. 비로그인·비활성 계정은 401 → 빈 목록으로 empty state를 보여준다. **주의:** 목록을 서버 컴포넌트에서 조회해 넘기면(`dynamic = "force-dynamic"`) 탭 진입마다 서버 왕복을 기다려 매번 로딩이 노출되므로 그 방식으로 되돌리지 않는다.

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

**FR-BT-052** [재무 팩터 음수 데이터 처리, 2026-07-21] 재무 비율(PER/PBR/ROE/PCR/EV·EBITDA/EV·EBIT)은 분모(순이익·자기자본·영업활동현금흐름·EBITDA·EBIT)가 0 이하일 때 값을 계산하지 않고 null로 처리해야 한다(음수 값을 그대로 반환하지 않는다). 상태코드(`NEGATIVE_EARNINGS`/`NEGATIVE_EQUITY`/`NEGATIVE_CASHFLOW`/`NEGATIVE_EBIT`/`NEGATIVE_EBITDA`/`DIVIDE_BY_ZERO`/`MISSING_DATA`)는 `engine/fundamental_status.py`의 순수 함수가 원천 드라이버 값(eps/자기자본/ocf/ebitda/ebit)으로부터 API·리포트 응답 시점에 즉석 판정하며, parquet에 별도 컬럼으로 저장하지 않는다(단일 진실 소스). PSR·ROA는 분모(매출·총자산)가 통상 항상 양수이므로 기존 계산 방식을 유지한다.

**FR-BT-052b** 성장률(매출액/영업이익/순이익/EPS/EBITDA/영업활동현금흐름/잉여현금흐름 증가율)은 직전·당기 값의 흑자/적자 조합에 따라 다음과 같이 분류해야 한다: 흑자→흑자는 일반 증가율 공식, 적자→적자는 적자 규모 개선/악화(`LOSS_NARROWED`/`LOSS_WIDENED`), 적자→흑자는 `TURNAROUND`, 흑자→적자는 `LOSS_TRANSITION`으로 분류하며 이 네 경우 모두 일반 증가율 수치 대신 상태코드로 표현한다. 매출액증가율은 매출이 항상 양수라는 전제로 예외로 둔다(변경 없음). 성장률·상태코드는 `engine/fundamental_fetcher.py::_compute_derived_annual_metrics`가 raw 값(연도별 eps/ebitda/영업활동현금흐름/FCF/영업이익/net_margin×매출)을 직접 비교해 계산하며, KIS가 직접 제공하는 영업이익·순이익 증가율(흑자↔적자 전환기에 부호가 왜곡될 수 있음)은 신뢰하지 않고 이 로컬 재계산으로 대체한다.

**FR-BT-052c** 계산 불가로 판정된 재무 비율·성장률은 종목 필터링·랭킹(가치+퀄리티 스코어)·분위수 계산에서 자동 배제되어야 한다(잘못된 기본값·중립값으로 대체 금지). `backtest_engine.py`의 value+quality 랭킹은 결측 PBR/ROE를 `fillna(1.0)`/`fillna(0.0)` 같은 센티널로 채우지 않고 NaN을 percentile rank까지 보존해야 하며, 이때 가중치가 0인 팩터의 NaN이 다른 팩터의 유효한 점수까지 함께 배제시켜서는 안 된다(가중치 0인 팩터는 무시).

**FR-BT-052d** EV/EBIT은 대차대조표 부채·현금을 별도로 조회하지 않고, EV=EV/EBITDA(KIS 제공 비율)×EBITDA(raw)로 역산한 값을 EBIT(raw 영업이익)으로 나누어 산출한다(EBITDA≤0이면 EV 자체를 역산할 수 없어 EBIT 부호와 무관하게 계산 불가로 처리). FCF는 영업활동현금흐름-CAPEX(DART 재무제표 유형·무형자산 취득 합계)로 산출하며, 시가총액 대비 FCF 배율(FCF Yield)은 이번 범위에 포함하지 않는다(raw FCF 금액과 증가율만 지원).

**FR-BT-052e** [현금흐름 3분류 수집, 2026-08-05] 시스템은 DART 현금흐름표(CF)의 활동별 총계 세 가지 — 영업활동(`operating_cash_flow`)·투자활동(`investing_cash_flow`)·재무활동(`financing_cash_flow`) — 을 이미 연도별로 호출 중인 `fnlttSinglAcntAll.json` 동일 응답에서 파싱해 저장해야 하며, 이를 위해 추가 API 호출을 발생시켜서는 안 된다. 값은 `operating_cash_flow`와 동일하게 raw 원 단위로 저장한다(억원 환산 금지 — PCR 계산이 `market_cap×1e8/ocf` 기준이다). 총계 행 선택은 **계정ID 일치를 계정명 일치보다 우선**해야 한다: 계정명만으로 고르면 "영업활동에서창출된현금흐름"(`ifrs-full_CashFlowsFromUsedInOperations` — 이자·법인세 차감 **전** 소계)을 총계로 오인한다(2026-08-05 포스코인터내셔널 실측). 해당 활동이 제출본에 없으면 키를 생략해야 하며 0으로 대체하지 않는다(결측과 0의 의미가 다르다). KIS·공공데이터포털(금융위원회 기업재무정보)에는 현금흐름표가 없어 OpenDART가 유일한 출처다(2026-08-05 전수 확인 — KIS `finance/cash-flow` 404, FSC는 요약재무제표·재무상태표·손익계산서 3종만). 본 항은 데이터 수집 범위만 정의한다 — 조건 지표 승격은 FR-BT-052f.

**FR-BT-052f** [현금흐름 3분류 조건 지표 승격, 2026-08-05] 영업·투자·재무활동 현금흐름은 전략 조건 필터로 지원되어야 하며, 필터가 쓰는 값의 단위는 **억원**이어야 한다(`operating_cf_amount`/`investing_cf_amount`/`financing_cf_amount`). DART 원천값은 raw 원이라 그대로 노출하면 "1,000억 이상"이 1억 배 어긋나므로, raw 컬럼(`operating_cash_flow` 등, PCR·FCF 계산 기준)은 유지한 채 억원 환산본을 파생 컬럼으로 따로 저장한다 — `market_cap`·`net_income`과 같은 관례. 투자·재무활동은 통상 음수(자산 취득·차입 상환)이므로 부호를 보존한 값을 그대로 비교하며, 절댓값으로 바꾸거나 부호를 뒤집어 해석해서는 안 된다. 절대 금액과 증가율은 서로 다른 지표다: "영업활동현금흐름 1,000억 이상"은 `operating_cf_amount`, "영업활동현금흐름 증가율 10%"는 `ocf_growth`로 갈려야 하며 어느 쪽도 다른 쪽을 잠식해서는 안 된다. 어느 분류인지 특정되지 않은 맨 "현금흐름" 언급은 결정적으로 고를 수 없으므로 `unsupported.cash_flow`(현금흐름 배율 FCF/PCF 조건)를 유지해 LLM 위임 신호로 쓰고, 3분류 필터가 실제로 반영되면 미지원 안내를 억제한다(`_CONCEPT_EXPRESSED_PREDICATES.cash_flow`).

**FR-BT-052g** [지배주주순이익, 2026-08-06] 시스템은 지배기업 소유주에게 귀속되는 당기순이익(`owner_net_income`, 억원)을 연결 전체 당기순이익(`net_income`)과 **별개의 지표**로 수집·노출해야 한다. 기존 `net_income`은 KIS 순이익률×매출액이라 비지배지분이 섞인 연결 전체 값이며(삼성전자 2023 실측: 전체 154,843억 = 지배 144,734 + 비지배 10,137), 지주회사·자회사 비중이 큰 기업에서 둘은 크게 갈리므로 한쪽을 다른 쪽으로 대체하거나 뭉뚱그려서는 안 된다. 값은 이미 연도별로 호출 중인 `fnlttSinglAcntAll.json` 동일 응답에서 파싱해야 하며 추가 API 호출을 발생시켜서는 안 된다(FR-BT-052e와 같은 계약). 행 선택의 1순위는 **정본 계정ID 정확 일치**이며, 계정명만으로 채택해서는 안 된다: 계정명 표기가 회사마다 갈리는 데다("지배기업의 소유주에게 귀속되는 당기순이익(손실)"/"지배기업소유주지분"/"지배기업소유주"/"지배주주순이익"), 같은 CIS 섹션의 **총포괄손익** 귀속 행(`…ComprehensiveIncomeAttributableToOwnersOfParent`)이 사실상 같은 계정명을 쓰므로 이름으로 고르면 포괄손익을 순이익으로 오인한다(SK하이닉스 2023 실측). 계정ID 접두는 IFRS 택소노미 전환에 따라 두 벌(2018년 사업보고서까지 `ifrs_`, 2019년부터 `ifrs-full_`)이므로 둘 다 인정해야 한다 — 신형만 보면 2015~2018년이 조용히 결측된다(삼성전자 실측).

정본 계정ID가 없는 제출본은 **같은 응답 안에서 검산(지배 + 비지배 = 당기순이익 `ifrs-full_ProfitLoss`)이 성립할 때만** 구제하며, 검산을 통과하지 못하면 결측으로 남겨야 한다(2026-08-07, 90종목 표본 원인 분류). 구제 대상은 세 가지다: ① 계속영업손익 귀속 계정(`IncomeFromContinuingOperationsAttributableToOwnersOfParent`) — 중단영업이 없을 때만 당기순이익 귀속과 수치가 같으므로, 있으면 검산이 어긋나 자동 탈락한다; ② 계정ID 미사용(`-표준계정코드 미사용-`) 제출본 — 이름으로 후보를 모으되 검산을 통과한 (지배, 비지배) 쌍만 채택한다; ③ 비지배 귀속 행이 아예 없는 제출본 — 비지배를 0으로 놓고 소유주 값 단독으로 검산한다. 귀속 행이 하나도 없으면 재무상태표에서 비지배지분이 없음(비지배지분 = 0 또는 자본총계 = 지배기업소유주지분)을 확인한 뒤에만 당기순이익 전액을 지배주주 귀속으로 본다 — 비지배지분이 실재하는데 귀속 정보가 없으면 총액으로 대체하지 말고 결측으로 남긴다. 검산의 목적은 **이름이 비슷한 다른 개념(총포괄손익, 중단영업이 있는 계속영업손익)을 조용히 채워 넣지 않는 것**이다: 045660 2025년 실측에서 계정ID 없는 "지배기업소유주지분/비지배지분" 쌍의 합이 당기순이익과 어긋나 총포괄 귀속임이 드러났고 검산이 이를 거부했다. DART가 유일한 출처이므로 2015년 이전과 별도재무제표(OFS)만 제출하는 종목은 결측이 정상이며, 결측을 `net_income`으로 대체하거나 0으로 채워서는 안 된다. 사용자 표현 매핑은 귀속 주체를 밝힌 경우("지배주주순이익", "지배기업 소유주 귀속 순이익")에만 이 지표로 가고 맨 "당기순이익"은 `net_income`을 유지해야 한다.

**FR-BT-052h** [연간 재무 레코드의 기간 정합, 2026-08-07 · 엔진 v10.0] 연간 재무 데이터로 저장·노출하는 레코드는 **실제 연간 결산 기간 하나**에 대응해야 하며, 기간이 다른 값이 섞여서는 안 된다. 세 가지를 함께 만족해야 한다.

(1) **KIS 분기 행 배제.** KIS 재무 엔드포인트는 연간(`FID_DIV_CLS_CODE=0`)을 요청해도 최신 분기 한 행을 맨 앞에 끼워 보낸다(현대차 실측: `stac_yymm` 202603, 202512, 202412 …). 파라미터로 뺄 수 없으므로 시스템이 걸러야 한다. 그 행의 비율은 연환산돼 정상이지만 유량은 기중 누적이라 약 1/4이며(현대차: ROE 89%·부채비율 101%인데 EPS 25%·영업이익 22%·EBITDA 23%·당기순이익 25%), 성장률은 분기 행이 직전 연간과 비교돼 순이익증가율 -75%로 오염되고 PER은 `종가÷EPS`라 약 4배로 부푼다(실측 3,220종목 중 2,150종목이 해당). 판정은 **직전 레코드와의 간격**으로 하고(연간 12개월, 분기 3·6·9개월), 최신 한 행만 후보로 본다 — "결산월 최빈값과 다른 레코드를 모두 버리는" 규칙은 결산기를 변경한 회사의 이력 한 무리를 통째로 삭제하므로 쓰지 않는다. 지표별로 골라 버리지 않고 레코드째 배제한다(레지스트리·프롬프트·본 SRS가 이 데이터를 "최근 연간 결산 기준"이라는 단일 계약으로 설명하고, 성장률 체인에 남으면 계속 오염되며, 지표마다 기준 시점이 갈리면 표시에서 설명할 수 없다).

(2) **DART 레코드의 결산일 라벨.** DART 레코드의 `year_end`를 `{bsns_year}-12-31`로 고정해서는 안 된다. `bsns_year`는 **그 결산기가 끝나는 달력 연도**다(실측: 효성오앤비 bsns_year 2023의 당기순이익 12.3억 = KIS 2023-06 레코드 12.4억 / 금비 2024 = KIS 2024-09). 12월로 고정하면 비12월 결산 회사(실측 36종목)의 현금흐름·지배주주순이익·당기순이익·자본총계가 실제 결산일과 다른 날짜에 붙어 같은 회계연도의 KIS 값과 다른 레코드로 갈라진다. 결산월은 **연도별로** 판정해야 한다 — 기업개황(`company.json`)의 `acc_mt`는 '현재' 결산월 하나뿐이라 결산기를 변경한 회사의 변경 이전 연도를 틀리게 만든다(유유제약: 2017년 3월→12월 전환, 전환기 9개월). 사업보고서 이름(`사업보고서 (2016.03)`)이 연도마다 그 해의 결산월을 달고 있으므로 이를 정본으로 쓰고, 공시 목록에 없는 연도만 `acc_mt`로, `acc_mt`마저 실패하면 12월로 폴백한다.

(3) **원공시 접수일 매핑의 결산월 반영.** 사업보고서 이름의 괄호 월은 결산월이므로 `(YYYY.12)`로 하드코딩하면 비12월 결산 회사가 `available_from` 정정일 오염 클램프(2026-08-04 수리)에서 통째로 빠진다. 괄호 월을 캡처해 결산월과 무관하게 연도로 매핑해야 하며, `[기재정정]사업보고서 (…)`도 같은 이름으로 걸리지만 연도별 최소 접수일을 취하는 규칙이 원공시를 고르므로 정정일로 밀리지 않는다. (2)의 연도별 결산월과 (3)의 원공시 접수일은 **같은 조회에서 함께** 얻어야 한다 — 추가 API 호출을 만들지 않는다. 조회 구간은 결산연도 하한 그 해부터 잡는다(12월 결산은 이듬해 제출이지만 6월 결산은 같은 해 9월 제출이라 이듬해부터 훑으면 빠진다).

본 항의 (1)은 최근 구간(직전 결산 공시 이후)의 재무 필터·랭킹 통과 종목과 PER 기반 전략 결과를 바꾸므로 엔진 MAJOR(v10.0)로 올린다 — 저장된 전략의 과거 백테스트 결과는 재현되지 않는다.

**FR-BT-052i** [야간 보강의 신규 봉 결측 처리, 2026-08-08] OHLCV 일일 갱신이 새로 붙인 봉은 재무 컬럼이 비어 있다(pykrx 응답에 재무가 없어 기존 컬럼 기준으로 null을 채운다). 뒤따르는 펀더멘털 보강 단계는 이 결측을 **같은 실행 안에서** 메워야 하며, 보강 여부 판정은 파케이 **마지막 행**을 기준으로 해야 한다. "한 행이라도 값이 있으면 건너뛴다"(`notna().any()`)는 판정은 새 봉의 결측을 캐시 만료(90일) 전까지 방치해, 최근 구간의 재무 필터·랭킹이 종목에 따라 통째로 비게 만든다 — 캐시를 일괄 갱신하면 만료 시계가 초기화되어 증상이 더 길어진다. 보강은 결측만 채우므로(기존 파케이 값 우선) 매 실행 반복해도 기존 값을 덮지 않는다. 종합 팩터 sentinel(`roa`) 컬럼이 아예 없거나 캐시가 만료된 경우 보강 대상이라는 기존 계약은 유지한다.

**구현 파일:**
- `backend/engine/fundamental_status.py` — 상태코드 순수 함수 (신규)
- `backend/engine/fundamental_fetcher.py` — `_compute_derived_annual_metrics`, `_parse_dart_activity_cash_flow`, `_parse_dart_capex`, `_parse_dart_total_equity`
- `backend/engine/fundamental_backfill.py`, `backend/backtest_engine.py`(랭킹), `backend/engine/signals.py`, `backend/intent/condition_builder.py`, `backend/engine/nl_parser.py`, `backend/strategy_conversation/registry/indicator_registry.py`
- `data/fundamental-status-messages.json` — 상태코드 한국어 설명(신규)
- `backend/tests/test_fundamental_status.py`(신규), `backend/tests/test_fundamental_fetcher.py`, `backend/tests/test_backfill_fundamentals.py`, `backend/tests/test_simulator_ranking.py`, `backend/tests/test_backfill_delisted_fundamentals.py`(신규)

**FR-BT-060** [분위(퀀타일) 그룹 비교·비율 선정, 2026-08-06] 시스템은 랭킹 전략(모멘텀·재무 팩터)에서 다음 두 가지 편입 규모 정의를 지원해야 한다.

① **비율 선정**(`max_positions_pct` / `portfolio.selection_percent`): "상위 10% 종목 편입"처럼 개수 대신 비율로 편입 규모를 정의한다. 시뮬레이터는 리밸런싱일마다 그날의 랭킹 후보 수 기준으로 목표 종목 수를 동적으로 계산하며(`count = max(1, round(n×pct/100))`), 비율이 있으면 개수(`max_positions`)는 무시한다.

② **분위 그룹 비교**(`ranking_quantile_groups` / `ranking[].quantile_groups`, 2~10): "지표 낮은 순 정렬 → 종목 수 동일 G개 그룹 → 그룹별 편입/비교"(예: PER 십분위) 요청을 처리한다. 엔진은 랭킹 내림차순 후보를 리밸런싱일마다 종목 수 기준 G등분하고(`select_ranked_targets` — G개 그룹은 서로소·전체 커버), 그룹별로 시뮬레이션을 반복해 `quantileGroups`(그룹별 총수익률·CAGR·MDD·샤프·승률·거래수·최종자산·다운샘플 자산곡선)를 결과에 싣는다. **메인 결과는 1그룹(랭킹 최상위 구간) 포트폴리오**다. 그룹 비교는 그룹별 순수 리밸런싱 기준으로 계산하며(개별 손절/익절/보유기간 미적용 — 동일 규칙 비교), 이를 경고로 고지한다. 랭킹 지표가 없거나 정기 리밸런싱이 없으면 그룹 비교를 조용히 빼지 않고 경고로 드러낸다. 결과 페이지(`QuantileGroupsSection`)는 그룹별 막대 그래프(CAGR/총 수익률/MDD 토글)와 지표 테이블을 표시한다.

되묻기 계약: 편입 규모가 비율·분위 그룹으로 이미 정의된 랭킹 전략에는 "상위 몇 종목을 선택할까요?"를 묻지 않는다(그룹/비율이 종목 수를 대신 정의). 두 필드 모두 미지정(None) 시 canonical DSL에서 제거되어 기존 전략의 `strategy_id` 해시는 변하지 않는다.

**FR-BT-060b** [분위 그룹당 보유 상한, 2026-08-06] 분위 그룹 전략의 '최대 보유' 자리는 **그룹당 보유 상한**(`ranking_group_cap` / 스펙 `portfolio.selection_count`)이다: 각 그룹이 자기 구간에서 랭킹 상위 N종목만 보유하며 모든 그룹에 동일 적용되어 그룹 간 비교 규칙이 같다(미지정 시 그룹 구간 전체 보유). 되묻기는 일반 질문("포트폴리오에 최대 몇 종목을 담을까요?") 대신 전용 질문("각 분위 그룹에 최대 몇 종목을 담을까요?")과 그룹 수 이상에서 시작하는 칩(그룹당 10/20/30종목)을 쓴다 — 백엔드 SOT(`strategy_slots._QUANTILE_MAX_POSITIONS_QUESTION`)와 프론트 미러(`backtestReadiness.QUANTILE_MAX_POSITIONS_PROMPT`)가 동형. cap은 물질화 기본값이 없어 값의 존재가 곧 사용자 답변이므로 provenance 없이 충족 판정한다. 칩/자유 답변의 종목 수는 분위 모드에서 결정적으로 cap에 미러된다(`_apply_prompt_overrides`·`applyDeterministicConditionChoice` — 이미 추출된 값의 자리 배정이지 새 원문 해석이 아니다). 라운드트립: 디컴파일러는 분위 모드의 `selection_count`를 `max_positions`(물질화 10)가 아니라 cap에서 취해 재컴파일 불일치(전 수정 레거시 폴백)를 막는다.

**구현 파일:**
- `backend/engine/simulator.py` — `select_ranked_targets`(밴드/비율/상위 K 선정), 순수 리밸런싱·커스텀 루프 양 경로
- `backend/backtest_engine.py` — 분위 그룹 게이트·그룹 반복 실행·`_quantile_group_summary`
- `backend/schemas.py`(RiskManagement·BacktestResponse), `backend/engine/nl_parser.py`(ParsedStrategy), `backend/engine/strategy_converter.py`
- `backend/strategy_conversation/` — interpreter `models.py`·`prompts.py`, `validation/completeness_validator.py`·`parameter_validator.py`, `compiler/strategy_compiler.py`·`strategy_decompiler.py`, `response/responses.py`
- `components/strategy/backtest/QuantileGroupsSection.tsx`(신규), `types/strategy.ts`, `app/analytics/new/backtestResultMapper.ts`, `lib/strategy-summary.ts`
- `backend/tests/test_quantile_groups_engine.py`(신규), `backend/tests/test_quantile_strategy_lane.py`(신규), `components/strategy/backtest/QuantileGroupsSection.test.tsx`(신규)

**FR-BT-061** [변동성 지표 필터·저변동성 랭킹, 2026-08-10, 엔진 v13.1] 시스템은 종목별 **연환산 변동성**(최근 N일 일수익률 롤링 표준편차 × √246 × 100, N 기본 60 — 연환산 계수는 결과 통계 FR-BT-020d-1과 동일한 KRX 실측값을 공유해 결과 화면의 'Volatility' 지표와 같은 눈금)을 두 가지 방식으로 전략 조건에 지원해야 한다. ① **임계값 필터**(`technical.volatility` → SignalEngine cid `volatility`): '변동성 30% 이하 종목'처럼 비교 연산자 조건. 매수 기본 연산자 `<=`(저변동성), 매도 기본 `>=`. 롤링 창 미충족 구간(NaN)은 신호를 내지 않는다. ② **저변동성 랭킹**(`ranking.volatility` → `ranking_metric='volatility'`): '변동성 낮은 종목 N개'처럼 횡단면 순위 선정 — 모멘텀('return')과 같은 계약(순위=진입, 회전=달력 리밸런싱, 초기 lookback NaN 구간 후보 제외, 대형주 마스크·유동성 게이트 보존). **방향 미지정 기본은 bottom(저변동성 선호)**이다: 엔진 기본이 top인 재무 팩터 랭킹과 달리, 무언의 top은 '가장 출렁이는 종목 선정'으로 전략이 뒤집히므로 온톨로지 polarity(`ranking.volatility`=lower_better)가 bottom을 채우고, 명시적 top은 None으로 접지 않고 그대로 저장한다(컴파일러 — 엔진 기본과 다른 방향만 저장하는 재무 분기 규칙을 그대로 쓰면 top이 삼켜진다). 이 승격으로 변동성은 레지스트리 UNSUPPORTED 목록과 프롬프트 미지원 예시에서 제거되었으나, `nl_parser._UNSUPPORTED_CONCEPT_PATTERNS`의 '변동성' 큐는 **의도적으로 남긴다** — 결정적 추출기는 변동성을 표현하지 못하므로 규칙 기반 레인의 LLM 위임 신호가 필요하고(PCR 승격 선례와 동형), LLM이 전략에 반영하면 `concepts_expressed_in_strategy`의 volatility 술어가 미지원 안내를 억제한다(FR-STR-023d [2026-08-01 확장]과 같은 계약). 회귀: `backend/tests/test_volatility_indicator.py`. [2026-08-10 확장 — 산정 기간 되묻기] 변동성 랭킹에서 산정 기간을 말하지 않으면 기본 60일을 조용히 확정하지 않고 되묻는다(completeness_validator, field `strategy.ranking[0].lookback_days`, 추천 60) — 칩은 '변동성 산정 기간 60/120/200일'이며 칩 정본 표기는 `_apply_prompt_overrides`가 결정적으로 결속한다(칩=값 결속 계약 — 이를 위해 `_UNSUPPORTED_CONCEPT_PATTERNS`의 '변동성' 큐는 '산정기간' lookahead로 칩 표기를 제외한다). 자유 서술 답변은 수정 인터프리터 레인이 처리한다. 모멘텀('return') 랭킹은 기존 계약(60일 물질화) 그대로다. [2026-08-10 정정 — v13.2 backfill 오염] 변동성 패널 계산은 **bfill 전 원시 종가**(`raw_price_df`)에 ffill만 적용해야 한다(`engine.indicators.annualized_volatility_panel`). ffill+bfill된 price_df를 쓰면 상장 전 구간이 첫 가격으로 평평하게 뒤채워져 수익률 0 → 변동성이 0으로 위장되고, 신규 상장 종목이 저변동성 최상위로 선정된다(2022-07-01 실측: 상장 21일째 마스턴프리미어리츠가 '120거래일 변동성 하위 7%'로 매수 + 가짜 초저변동 종목들이 하위권을 채워 진짜 저변동 종목의 표시 백분위가 6~7%로 부풀려짐 — 전 종목 재계산 대조 시 실제 0.6~1.7%). 수익률 관측치가 lookback개 미만이면 NaN(후보 자연 배제). 모멘텀('return') 랭킹은 여전히 bfill된 price_df를 쓴다(상장 후 실수익률로 계산되는 별개 특성 — 이 정정의 범위 밖, 별도 판단 필요).

---


**FR-BT-063** [복합 순위 합산(멀티팩터 랭킹), 2026-08-17, 엔진 v13.4] 시스템은 여러 지표의 횡단면 순위를 합산해 종목을 선정하는 랭킹("ROE 내림차순·유동비율 내림차순·PER 오름차순·PCR 오름차순으로 각 순위를 구해 합산, 합산값이 가장 낮은 상위 10% 편입")을 지원해야 한다. **표현**: `ranking_metric='composite'` + `ranking_components=[{metric, direction, lookback_days?}, ...]`(2개 이상; 구성 지표는 단일 랭킹이 가능한 지표 전부 — 재무 컬럼·기간 수익률·변동성). 해석 스펙에서는 `strategy.ranking` 항목 2개 이상 = 합산이며(합산 지표 이름을 지어내지 않는다), 방향 미지정 항목은 지표의 자연 방향(온톨로지 polarity)으로 컴파일러가 채운다. **계산**: 구성 지표마다 **전 지표가 정의된 종목 풀 안에서** 백분위 순위(방향 기준 좋은 쪽이 높게)를 매겨 **동일 가중 평균**한다 — 이 값의 내림차순은 순위 합산 오름차순과 같은 정렬이다(지표별 유효 종목 수 차이로 인한 가중 왜곡 방지). 어느 한 지표라도 없는 종목은 후보에서 배제한다(중립값 위장 금지). 구성 지표 컬럼이 유니버스 전체에 없으면 조용한 0거래가 아니라 경고. next_open은 1일 shift(look-ahead 방지). 가격 산출 구성 지표의 산정 기간은 구성 지표 자체 값 → 전략 공통 `ranking_lookback_days`(되묻기 칩 답이 결속되는 자리) → 60 순이며, 되묻기는 그 지표가 랭킹 항목 몇 번째에 있든 낸다(`strategy.ranking[i].lookback_days`). 매수 사유·분위 그룹 라벨은 "복합 순위(ROE 높은·PER 낮은) 상위 N%"처럼 구성 지표와 방향을 병기한다. 가중치는 되묻지 않는다(동일 가중이 정의). **미지원 랭킹 지표 처리(같은 날 사고 회귀)**: 검증기는 미지원 랭킹 항목을 오류와 함께 **제거**하고(진입 조건의 kept 계약과 동일), 미지원 보고에는 LLM이 지어낸 내부 식별자 대신 사용자 표현(`source_text`) 또는 평이한 일반 표기를 담는다(내부명 노출 금지 — 'composite_score' 노출 사고). 컴파일러는 등록되지 않은 랭킹 지표를 `'return'`으로 바꿔치는 폴백을 갖지 않는다(사용자가 말하지 않은 수익률 랭킹이 생기던 사고). 디컴파일러는 composite→RankingSpec N개로 왕복하며(가격 지표 `ranking.*` 네임스페이스 정정 포함), canonical DSL은 구성 지표를 정렬해 담고 단일 랭킹 전략에선 키를 내지 않아 기존 `strategy_id` 불변. 프론트 요약 라벨은 "복합 순위 상위 (ROE 높은 순 + PER 낮은 순 순위 합산)".

**구현 파일:**
- `backend/backtest_engine.py` — `_composite_ranking_components`·`_composite_ranking_label`·`_composite_rank_panel`·`_ranking_selection_pool`, 재무 랭킹 컬럼 수집 다중화(`all_fund_rank_values[col][sym]`)
- `backend/engine/nl_parser.py`(RankingComponent·ParsedStrategy.ranking_components·`_normalize_composite_ranking`·`_ranking_metrics_expressed`), `backend/schemas.py`, `backend/engine/strategy_converter.py`, `backend/engine/version.py`(v13.4)
- `backend/strategy_conversation/` — `interpreter/prompts.py`(복합 순위 규칙+예시 4-c), `validation/capability_validator.py`(미지원 랭킹 제거·비노출), `validation/completeness_validator.py`(자리 무관 산정 기간 되묻기), `compiler/strategy_compiler.py`·`strategy_decompiler.py`, `primary.py`(`_RANKING_LOOKBACK_FIELD_RE`), `conversation/change_log.py`
- `lib/strategy-summary.ts`(getRankingLabel composite), `types/strategy.ts`
- `backend/tests/test_composite_ranking_engine.py`(신규), `backend/tests/test_composite_ranking_lane.py`(신규), `lib/strategy-summary.composite-ranking.test.ts`(신규)

**FR-BT-064** [리밸런싱 기간별 결과 비교, 2026-08-18, 엔진 v16.3.1] 백테스트 결과 페이지의 수익률 추이 영역에 '월별 수익률'·'롤링 수익률' 오른쪽 세 번째 탭 **'리밸런싱 기간별 결과'**를 제공해야 한다. 엔진은 **백테스트마다** 메인 시뮬레이션 뒤 같은 입력(가격·신호·랭킹·거래 가능 마스크)으로 `rebalancing_period`만 매일(daily)·매주(weekly)·매월(monthly)·분기(quarterly)·반기(semiannual)·연간(yearly)으로 바꿔 시뮬레이션을 6번 반복하고(분위 그룹 비교 FR-BT-060과 같은 구조 — 1단계 데이터 준비는 재실행하지 않는다), 주기별 CAGR·MDD·샤프·손익비(손실 0건=∞ 유지)·거래 수·회전율(결과 화면과 같은 산식)을 `BacktestResponse.rebalanceComparison`으로 동봉한다. 탭은 별도 실행·버튼 없이 이 표를 바로 보여준다(2026-08-18 사용자 지시 — 처음 도입한 '별도 SSE 실행 + LLM 서술' 방식은 같은 날 폐기). **현재 설정 표시**: 전략의 현재 주기가 6주기 안이면 그 행에 '현재 설정' 배지, 밖이면(리밸런싱 없음·격월) 메인 결과 지표로 참고 행을 덧붙인다. **보유 상한 없는 전략**: 주기가 결과에 영향을 주지 않아도 막지 않고 계산하며 `positionCapAbsent`로 표시해 화면이 "6행이 같을 수 있음"을 안내한다. 한 주기의 실패는 그 행만 error로 남기고 나머지·메인 결과에 영향을 주지 않는다. 화면에는 "과거 데이터 시뮬레이션이며 미래 수익을 보장하지 않음" 안내를 표시하고 AI 서술·추천은 없다. 결과는 백테스트 기록·저장 전략 요약과 함께 저장된다(구버전 결과에는 없음 → 안내). 반기 주기는 이 기능을 위해 엔진에 신설했다(v16.1, 대화 해석기 어휘 미등록).

**구현 파일:**
- `backend/engine/rebalance_comparison.py`(신규 — 6주기 재시뮬레이션·행 요약·회전율), `backend/backtest_engine.py`(분위 그룹 블록 뒤 호출), `backend/schemas.py`(`rebalanceComparison`), `backend/engine/rebalance.py`(semiannual)·`engine/live_signal_utils.py`
- `components/strategy/backtest/rebalanceComparison.ts`·`RebalanceComparisonSection.tsx`(신규), `components/strategy/backtest/BacktestDashboard.tsx`(탭), `app/analytics/new/backtestResultMapper.ts`·`lib/strategy/BacktestService.ts`·`lib/server/backtestCache.ts`(필드 전달·저장), `types/strategy.ts`
- `backend/tests/test_rebalance_comparison.py`·`test_rebalance_dates.py`, `components/__tests__/RebalanceComparisonSection.test.tsx`

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

**FR-VM-003a** [지표 표기 정합, 2026-08-07] 가상계좌 상세 화면의 성과 지표는 라벨과 실제 계산식이 일치해야 한다.
- `누적 수익률` = (총 자산 − 초기 자본) ÷ 초기 자본. 부제는 상단 KPI·성과 분석 탭 모두 "초기 자본 대비"로 통일한다(입출금 기능이 없어 초기 자본은 개설 이후 불변).
- `누적 손익` = 총 자산 − 초기 자본. 실현·평가 손익을 모두 포함하므로 '평가손익'으로 표기하지 않는다.
- `당일 실현손익` = 당일 매도 체결의 실현손익 합계. 평가 변동을 포함하지 않으므로 '당일 손익'으로 표기하지 않으며, 병기하는 퍼센트는 초기 자본 대비임을 명시한다.
- `주식 평가 금액` = 총 자산 − 주문 가능 금액. 매입원가가 아니므로 '투자 금액'으로 표기하지 않는다.

**FR-VM-003b** [성과 추이 실측화, 2026-08-07] 가상계좌 성과 차트는 실제 체결 이력에서만 산출해야 하며, 합성·근사 곡선을 표시해서는 안 된다. 일별 자산 스냅샷이 없으므로 곡선은 매도 체결의 **누적 실현손익**(초기 자본 = 100 지수, `app/virtual-account/performanceSeries.ts`)으로 정의하고, 평가손익 미포함을 화면에 명시한다. 실제로 산출하지 않는 벤치마크(예: KOSPI 200)는 표기하지 않는다.

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
- [스팩(SPAC) 제외, 2026-07-21] 스팩(기업인수목적회사)은 상장·거래 요건을 만족해도 유니버스에서 항상 제외한다 — 종목명에 "스팩"이 포함되면 판정한다(`universe_pit._is_spac`, 리츠 접미사 판정과 동형 패턴; 실측 232개 전량 이 패턴). `resolve_symbols`(실제 백테스트/랭킹/리밸런싱 실행 경로)와 `strategy_converter._load_universe`(캐노니컬 DSL·종목 수 추정 경로) 양쪽에 적용해 추정치와 실행 결과가 어긋나지 않도록 한다.
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

**FR-VM-073** [매매 유니버스 해석 정합, 2026-08-07] 자동매매 신호 대상 유니버스(`resolve_live_universe`, `engine/live_signal_utils.py`)는 표시용 모니터링 목록과 독립적으로 해석되므로(FR-VM-072 마지막 항목과 같은 이유), 그 해석 자체가 다음을 보장해야 한다.

- **상장폐지 종목 제외**: 해석 경로(ETF·KOSPI200·시장·업종·지정 종목·폴백)와 무관하게 최종 결과에서 `data/delisted-stocks.json`(=`DelistedSymbolStore` 원장) 등재 종목을 제거한다. `data/korea-stocks.json`에는 상장 상태 필드가 없어 상폐 종목이 섞여 들어오고(실측 67종목), Stock 테이블에 행이 없는 종목은 FR-VM-066 게이트가 `NORMAL`로 통과시켜 매수까지 도달할 수 있다. 보유 포지션은 유니버스와 별개로 시세·청산 대상에 합류하므로(FR-VM-072) 이 제외가 상폐 보유분의 강제청산을 막지 않는다.
- **유니버스 id 별칭·토큰 일치**: 시장 판정은 부분 문자열이 아니라 `_` 토큰 단위 일치로 한다. 부분일치는 `KOR_KOSPI200`을 "KOSPI 전체"(실측 836종목)로, `KOR_KOSDAQ150`을 "KOSDAQ 전체"(1819종목)로 넓혀 지수 전략이 지수 밖 종목을 매매하게 만든다. 정본이 아닌 표기는 `_UNIVERSE_ALIASES`에 등록해 정본 id로 모은다(`kor_kospi200`·`kospi_200` → `kospi200`, `kor_kosdaq150`·`kosdaq_150` → `kosdaq150`). 별칭에도 토큰에도 없는 표기는 해석 실패로 보아 폴백(모니터링 목록)을 쓴다 — 인식하지 못한 표기를 임의로 넓은 시장으로 확대하지 않는다.
- **지수 유니버스는 구성종목 명부로만 해석**: `kospi200`·`kosdaq150`은 `_INDEX_ROSTERS`가 가리키는 명부 파일(`data/kospi200-cache.json`, `data/kosdaq150-cache.json`)에서만 종목을 얻는다. 명부가 없거나 깨졌으면 해당 시장 전체로 대체하지 않고 폴백으로 떨어진다. 업종 필터를 함께 지정한 경우에도 명부 **안에서만** 걸러야 하며, 명부 밖의 같은 업종 종목을 끌어오지 않는다.
- **지수 명부 출처는 KIS 종목마스터 단일화**: `backend/engine/kis_master.py`가 KIS 종목마스터(`kospi_code.mst`/`kosdaq_code.mst`)의 편입 플래그를 읽고, `backend/scripts/build_index_rosters.py`가 `data/kospi200-cache.json`·`data/kosdaq150-cache.json`을 함께 생성한다. 2026-08-07 조사 결과 KRX 정보데이터시스템(pykrx·FinanceDataReader·직접 호출)은 데이터 조회 bld를 모두 `LOGOUT`으로 거부하고, KRX Open API는 코스닥 150 **가격**만 제공하며, 네이버 `entryJongmok`은 code 파라미터와 무관하게 KOSPI200만 반환한다 — KIS 마스터가 인증 없이 두 지수를 모두 얻을 수 있는 유일한 소스다. 네이버 스크래핑은 KOSPI200 폴백으로만 남긴다(영숫자 신규 상장 코드를 누락해 수동 보정 목록이 필요했다).
- **편입 플래그 위치는 실측으로 특정한다**: `kospi_code.mst` 꼬리 228B의 idx 19(KOSPI200 섹터업종 코드, `'0'` 아닌 값 정확히 200개), `kosdaq_code.mst` 꼬리 222B의 idx 36(KOSDAQ150 Y/N, Y 정확히 150개). 인접 필드가 KOSPI100(100개)·KOSPI50(50개)·KRX300(297개)로 KIS 문서상 순서와 맞고 KOSPI50 ⊂ KOSPI100 ⊂ KOSPI200 포함관계도 성립해 위치가 확증된다.
- **명부 검증 실패 시 기록하지 않는다**: 종목 수(정의값 ±5)·코드 형식·시장 소속을 검증하고 하나라도 실패하면 `MasterLayoutError`로 중단하며 파일을 쓰지 않는다. 잘못된 명부는 조용히 잘못된 유니버스로 백테스트·자동매매를 돌린다. 명부 갱신은 스크립트 재실행 또는 캐시 TTL 만료 시 런타임 재조회로 하며, 30초 주기 매매 루프는 파일만 읽는다.
- **KOSDAQ150 백테스트 해석은 시점 기준 시총 상위 150**: 정적 현재 명부는 그 자체가 생존편향이므로(FR-VM-067의 KOSPI200과 동일 논리) 백테스트는 명부 대신 매 시점 KOSDAQ 시총 상위 150으로 지수를 근사한다. `universe_pit.parse_universe_markets`는 `(markets, index_top_n)`을 돌려주고(`kospi200`→200, `kosdaq150`→150, 그 외 `None`), 엔진이 그 N으로 일별 시총 순위 게이트를 건다. 지수 토큰이 둘 이상이거나(`kosdaq150_kospi200`) 지수에 다른 시장이 섞이면(`kosdaq150_kospi`) 시장별로 순위를 나눠 매길 수 없으므로 순위 게이트를 걸지 않는다 — 전자는 미인식 처리, 후자는 명부 합집합만 쓴다.
- **KOSDAQ150은 KOSDAQ 전체로 폴백하지 않는다**: 명부를 얻지 못하면 `_load_kosdaq150`은 빈 목록을 반환한다. 150종목 지수를 1,700여 종목 시장으로 넓히는 것이 바로 이 요구사항이 막는 사고다(KOSPI200은 기존 동작 유지를 위해 KOSPI 전체 폴백을 남긴다).
- **지정가 대기 주문 게이트**: PENDING 지정가 주문 체결(FR-VM-046)도 진입·청산과 동일하게 상장 상태 게이트를 거쳐야 한다. 가격 조건만으로 체결하면 주문 접수 이후 거래정지·상장폐지된 종목이 그대로 체결된다. 판정은 같은 사이클에서 이미 조회한 상태를 재사용한다(추가 DB 조회 없음).

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

**FR-SA-002c** 열린 추천 전환(FR-SA-002b) 직후에는 **전략 빌더 모드**로 진입해, 사용자의 짧은 답변("일단 코스피", "모멘텀", "3개월")을 역할 밖 거절 없이 전략 필드로 누적해야 한다. 전환 안내를 보낸 직후에는 사용자의 후속 입력을 기다리지 않고 곧바로 빌더의 첫 질문(시장 선택)을 능동적으로 띄워 전략 구성을 시작한다(빈 입력으로 `step`을 호출하면 상태를 바꾸지 않고 현재 질문을 반환하는 계약을 이용 — 질문·옵션 칩의 단일 출처는 백엔드 빌더). 필수 필드(유니버스 → 전략유형 → 기준기간/진입조건 → 보유 종목 수 → 리밸런싱 → 청산 조건) 우선순위 중 가장 먼저 빈 필드 하나만 질문하고, 마지막 청산 조건 단계에서는 손절·익절·트레일링 스탑·보유기간을 한 번에 받는다(청산 조건은 **필수** — 하나 이상 인식되어야 완료되며, 없으면 같은 질문을 다시 한다. 단, 사용자가 청산 조건 자체를 거부하면("없음"·"필요 없어") 같은 질문을 그대로 반복하지 않고 청산 조건이 왜 필요한지 설명하며 되묻는다). 유니버스 해석은 메인 NL 파서와 동일한 의미론을 따른다 — "코스피 전체"는 코스피 전 종목(KOSPI)이지 양시장이 아니며, 시장명 없는 "전체/모두"만 코스피·코스닥 양시장으로 해석한다. 모두 채워지면 별도 텍스트 요약 단계 없이 곧바로 검증된 한국어 프롬프트로 합성해 기존 파싱 파이프라인으로 넘긴 뒤 전략 요약 카드 + 검증 + "백테스트 실행" 버튼을 보여준다(그 버튼이 최종 확인 역할). "취소/그만"은 일반 모드로 복귀하고, "처음부터/새 전략"은 상태를 초기화한 뒤 빌더를 유지하며, "다른 질문 할게"는 일반 모드로 종료한다. 결정적 상태 머신(`intent/strategy_builder.py`)이 parser·state-transition·response-generation을 분리해 처리하고(LLM 불필요), 무상태 라우트 `POST /strategy/builder/step`로 노출한다. 빌더 모드에서는 일반 out-of-scope 거절보다 빌더 파서를 먼저 실행하며, 파싱 실패 시 거절하지 않고 같은 질문을 다시 한다. 빌더 진행 중 용어 정의 질문("손절이 뭐야?")은 필드 답변으로 오인하지 않고, 빌더가 제시하는 어휘(손절·익절·트레일링·리밸런싱·모멘텀·골든크로스·RSI·PBR 등)에 한해 짧은 객관적 정의를 답한 뒤 현재 질문을 이어간다(상태 불변, LLM 불필요, 추천·권유 없음). UI 측면에서, 빌더가 옵션 칩을 보여주는 동안에는 채팅 입력창을 숨겨 사용자가 선택에 집중하도록 한다(칩=`infoSuggestions`는 빌더 전용). 전략 유형 질문에는 가장 오른쪽에 "직접 설명하기" 칩을 두며, 선택 시 자유 서술(custom) 진입 조건 질문(칩 없음)으로 넘어가 채팅 입력창이 다시 나타나 사용자가 자신의 전략을 직접 입력할 수 있다. 청산 조건처럼 자유 서술을 인라인으로 받는 칩-only 단계에는 가장 오른쪽에 "직접 입력" 칩을 두며, 이 칩은 빌더 답변으로 전송하지 않고 채팅 입력창만 다시 띄워(프론트 토글) 사용자가 커스텀 값("15% 손절" 등)을 직접 타이핑하게 한다. [2026-07-21 확장] 빌더 칩(`infoSuggestions`)뿐 아니라 진입조건 누락 등 일반 명확화(clarification) 되묻기의 예시 칩(`clarificationSuggestions`)이 떠 있는 동안에도 동일하게 채팅 입력창을 숨긴다 — 칩과 자유 입력창이 함께 보이면 "직접 입력" 칩을 눌러야 하는 이유가 불분명해지고, 이미 선택지에 답한 상태인데 열린 입력창이 또 물어보는 것처럼 오인되는 문제가 있었다(`chatNavigation.shouldShowChatInputBox`의 `clarificationAwaitingChoice`). 예시 칩이 없는 되묻기(자유 서술만 가능)는 그대로 입력창을 보여준다. [2026-07-31 확장] **선택지가 곧 답의 전부인 슬롯에는 "직접 입력" 칩을 붙이지 않는다** — 현재는 유니버스가 유일하며(지원하는 시장 범위가 코스피200·코스피·코스닥·코스피+코스닥으로 닫혀 있다), 자유 입력 칩은 없는 여지를 만든다. 판정 정본은 `backtestReadiness.isClosedChoiceSlot(field)`이고, 되묻기 메시지가 실어 나르는 `clarificationField`(그 되묻기가 채우는 골격 슬롯)가 유일한 입력이다 — 질문 문구는 사용자 친화 문구로 치환되므로(`makeBuilderQuestionFriendly`) 문구 매칭은 근거가 될 수 없다. 빌더 칩 경로(`withBuilderNavigationSuggestions`)는 유니버스 단계에서 이미 같은 판정을 하고 있었으며, 이로써 두 경로의 유니버스 질문이 동일하게 보인다.

**FR-SA-002c-1** [규제 안전 — 전략 추천 금지] 구체적인 지표·전략 유형 없이 어떤 전략이 우수한지 골라 달라는 **열린 전략 추천 요청**("지금 어떤 전략이 좋을까?", "전략 추천해줘", "무슨 전략을 써야 하나요?")은 전략 우열을 판단·추천하지 않고, 함께 전략을 만들어 백테스트하는 **전략 빌더**로 대화를 전환하는 안내(`QueryIntent.STRATEGY_PICK` + `suggested_reply`)로 응답해야 한다. 전환 안내("어떤 전략이 더 좋은지 판단하거나 추천해 드리지는 않지만, 관심 있는 아이디어를 함께 전략으로 만들어 … 백테스트해 볼 수 있어요") 직후에는 STOCK_PICK(FR-SA-002b/c)과 동일하게 곧바로 빌더 모드로 진입해 첫 질문(시장 선택)을 능동적으로 띄운다. 결정적 감지(`intent/scope.py::is_strategy_pick_request`)는 '전략' 키워드가 있어 STRATEGY_ADVICE로 새기 전에 먼저 잡되, 구체적인 전략 유형·지표(모멘텀·RSI·MACD 등)나 기존 전략 지시어("이 전략"), 정량 스크리닝·수정 명령·특정 종목명이 섞이면 설계 요청이므로 가로채지 않고 일반 전략 흐름에 맡긴다.

**FR-SA-002c-2** [기능 범위 — 미제공 기능 안내] 뉴스·공시·SNS 여론처럼 플랫폼이 제공하지 않는 데이터 분석을 근거로 종목을 고르거나 전략을 만들어 달라는 요청("최근 뉴스가 좋은 종목을 사는 전략을 만들어줘", "호재 있는 종목 골라줘")은 전략 빌더로 진입하지 않고, 해당 기능을 제공하지 않는다는 안내와 함께 다른 투자 아이디어를 유도하는 응답(`QueryIntent.UNSUPPORTED_FEATURE` + `suggested_reply`)으로 답해야 한다(2026-07-12 — '전략' 키워드로 STRATEGY_ADVICE에 새서 빈 전략 파싱→빌더 자동 전환으로 이어지던 사고의 재발 방지). 결정적 감지(`intent/scope.py::is_unsupported_feature_request`)는 뉴스 단어(뉴스·공시·호재·악재·풍문·루머·기사·여론·SNS)가 종목 선정/전략의 근거로 쓰인 경우만 잡되, ① 지원 지표·재무 신호(RSI·이동평균·PBR 등)가 섞인 혼합 요청은 가로채지 않고 일반 전략 흐름에 맡기고(파서가 지원 부분을 살리고 미지원 개념 notice — `engine.nl_parser` "news" 항목 — 로 알림), ② 순수 정의형 질문("공시가 뭐야?")과 ③ 종목명(또는 anaphora)+행동 질문("삼성전자 악재 떴는데 팔까?" → FR-SA-006 종목 질문 전환)은 기존 규칙에 맡긴다. 긴 꼬리 phrasing은 LLM 폴백 분류가 `UNSUPPORTED_FEATURE`로 잡으면 동일 안내를 채운다. 프론트(`maybeRouteNonStrategyQuery`)는 이 intent에서 빌더 스텝·전략 파싱을 호출하지 않고 안내만 표시한 뒤 후속 입력을 기다린다.

**FR-SA-002c-3** [대화 맥락 기반 후속 질문 분류] "다른 예는 없어?", "더 알려줘"처럼 직전 챗봇 답변에 이어지는 **후속 질문**은 문장만 보면 투자 신호가 없어 역할 밖(OFF_TOPIC) 거절로 새면 안 된다(2026-07-12 사고 — 종목 질문 전환 안내가 전략 예시를 보여준 직후 "다른 예는 없어?"가 거절됨). 프론트(`app/analytics/new/chatHistory.ts::selectClassifierHistory`)는 분류(`/query/classify`)와 일반 답변(`/query/general`) 호출에 최근 대화 턴(기본 6턴, 로딩 자리표시자·빈 메시지 제외)을 `history`로 함께 보내고, 백엔드 LLM 폴백 분류(`intent/classifier.py::_classify_with_llm`)는 이를 `[대화 맥락]`/`[최신 입력]`으로 구분해 넘겨 직전 주제의 연속으로 분류한다(직전 주제가 투자면 OFF_TOPIC 금지, 예시·설명 추가 요청은 GENERAL_INVESTMENT). `/query/general`도 같은 맥락(`format_history_context`, 턴당 240자 절단)을 받아 직전 답변과 겹치지 않게 이어서 답한다. 결정적 규칙은 현재 입력만 본다 — 투자 맥락이 있어도 명백한 역할 밖 질문("오늘 날씨 어때?")은 여전히 거절된다.

**FR-SA-002c-4** [활성 전략 중 정의형 질문] 전략 요약이 이미 만들어진 대화에서도 용어 정의·일반 지식 질문("pbr이 뭐야?")은 전략 수정 파싱이 아니라 일반 지식 답변(`/query/general`, history 포함)으로 응답해야 한다(2026-07-17 사고 — `GENERAL_INVESTMENT` 분류가 `hasCurrentStrategy` 게이트에 막혀 수정 파싱으로 흘렀고, 바꿀 필드가 없어 무변경 전략 요약만 다시 렌더링되고 질문은 답변되지 않음). 프론트 대화 결정(`app/analytics/new/conversationDecision.ts::decideConversationTurn`)은 `GENERAL_INVESTMENT`면 활성 전략 여부와 무관하게 `answer_general`로 라우팅하고, `UNKNOWN`은 기존대로 활성 전략이 있으면 전략 입력으로 본다. 전략 카드·백테스트 준비 상태는 답변 후에도 그대로 유지된다(전략을 건드리지 않는 경로). **백엔드 2차 방어선**: 그래도 질문이 수정 파싱 경로로 흘러 인터프리터가 CLARIFY_STRATEGY(패치 없음)+질문으로 응답하면, `strategy_conversation/primary.py::run_primary_modification`은 폴백으로 질문을 버리는 대신 — 단, 결정적 fast-path(`_modify_rule_based`)가 처리할 수 있는 단순 수정은 기존대로 폴백(되묻기가 단순 수정을 가로막지 않게) — 전략을 그대로 유지한 채 질문을 기존 clarification 채널로 전달해 사용자가 무변경 요약 대신 되묻기를 받게 한다. 인터프리터가 질문 대신 `EXPLAIN_INDICATOR`나 `unsupported_features`(패치 없음)로만 보고하는 경우(2026-07-17 실측: `unsupported_features=["PBR 개념 설명 요청"]`)도 침묵 폴백하지 않고 전략을 유지하며, **정의형 질문(결정적 cue `intent.classifier.is_definition_question` — 4B 라벨이 아니라 입력 기준)이면 `/query/general`과 동일한 생성기(`api.intent_routes.generate_general_answer`)로 실제 용어 설명을 만들어 notices 채널로 답한다**(`primary_modify_explain`, 2026-07-19 — "변경하지 않았어요" 안내만 주면 질문이 답변되지 않는다는 사용자 교정). 설명 LLM 미가용이면 준비하지 못했다는 정직한 안내, 정의형 질문이 아닌 진짜 미지원 개념 요청은 미반영 안내를 준다(`primary_modify_unsupported`). 인터프리터 프롬프트(1.2)는 초안이 있어도 용어·개념 설명 질문은 MODIFY가 아니라 EXPLAIN_INDICATOR이며 unsupported_features에 넣지 않도록 계약한다.

**FR-SA-002c-5** [백테스트 설정 기본값 정확 답변] "슬리피지는 몇 %가 기본 값이지?", "현재 셋팅된 슬리피지 값은?"처럼 백테스트 설정(슬리피지·수수료·증권거래세·초기자금·체결 시점)의 기본값·현재값을 묻는 질문에는 LLM 일반답변이 값을 지어내게 두지 않고(2026-07-20 사고 — 전략 분석실이 "기본값은 0%"라고 오답) 코드의 실제 기본값으로 정확히 답해야 한다. 결정적 감지(`intent/platform_defaults.py::is_default_question` — 설정 용어+값 질문 cue, "0.1%로 설정해줘" 같은 값 변경 명령형은 제외)가 분류기 결정 규칙(전략 키워드 게이트보다 먼저)으로 `GENERAL_INVESTMENT`에 라우팅하고, `generate_general_answer`가 LLM 호출 전에 결정적 답변(`platform_defaults.reply`)을 반환한다(LLM 미가용에도 동작). 답변 값은 하드코딩하지 않고 SOT에서 읽는다 — ParsedStrategy 필드 default(수수료 0.015%·슬리피지 0.05%·초기자금 1,000만원·체결 다음 날 시가), `MIN_INITIAL_CAPITAL`(100만원 하한), 시뮬레이터 `DEFAULT_SELL_TAX_RATE`(매도 거래세 0.15%, ETF 유니버스는 0%). 수수료 질문에는 매도 거래세를 동반 안내해 총비용 오해를 막고, 설정 패널에서 변경 가능함(변경 시 그 값 적용)을 함께 알린다. 설정 용어가 언급된 개념 질문("슬리피지가 뭐야?")은 LLM이 설명하되 실제 기본값 사실 블록(`facts_block`)을 프롬프트에 주입해 값 환각을 막는다. 수정 파싱 경로로 오라우팅된 경우의 백스톱(`run_primary_modification`, FR-SA-002c-4)도 이 cue를 질문으로 인정한다.

**FR-SA-002c-6** [레드팀 검증 — 규제·안전·정확성 강화, 2026-07-20] 레드팀 QA 하니스(`scripts/qa_redteam_validation.py`, 145케이스·24유형; 리포트 `docs/qa_redteam_validation_report.md`; 회귀 `backend/tests/test_redteam_validation_fixes.py`)에서 발견한 결함들을 다음과 같이 방어해야 한다. ① [개인 맞춤형 조언 금지] 나이·자산·직업 등 개인 상황에 맞춘 전략·종목 추천 요청("40대인데 나한테 맞는 전략 뭐야?")은 LLM 일반답변으로 흘리지 않고(맞춤 조언 생성 사고 방지) 결정적 감지(`intent/scope.py::is_personal_advice_request`)로 `STRATEGY_PICK`+맞춤 추천 불가 안내로 가로챈다. `/query/general` 시스템 프롬프트도 개인 맞춤 추천을 금지한다. ② [금융 오개념 교정] 오개념을 단정·확인하는 발화("PER이 높을수록 싸다는 거지?", "무조건 사면 된대")는 파싱 경로(교정 기회 없음) 대신 지식 답변 경로(`GENERAL_INVESTMENT`, `is_misconception_assertion`)로 보내 먼저 바로잡는다(구성·수정 동사 동반 시 제외). ③ [실전 매매 미제공] 실계좌 자동매매·대리 투자 요청("자동으로 실전 매매까지 해줘", "내 돈 대신 투자해줘")은 `is_live_trading_request`로 `UNSUPPORTED_FEATURE`+가상계좌 모의투자 안내(가상/모의 언급 시 통과). ④ [해외 종목] 해외 종목 매수·매도 질문은 그 종목의 백테스트를 예시로 제안하지 않고(기능 환각 방지) 국내 시장 대상만 안내하며(`stock_question_redirect(overseas=True)`), 파싱 경로에서도 해외 개별 종목·해외 시장·우선주는 미지원 개념 안내(`_UNSUPPORTED_CONCEPT_PATTERNS`의 overseas/preferred_stock)로 조용히 드롭하지 않는다. ⑤ [기초 용어 정의 정확성] `/query/general` 답변에 PER·PBR·ROE·RSI·MACD·부채비율 등 표준 정의 사실 블록(`intent/glossary_facts.py::facts_block`)을 주입해 소형 LLM의 정의 오류를 막는다. ⑥ [지표 발음 표기] '맥디'→MACD, '알에스아이'→RSI를 분류기·파서 `_compact` 양쪽에서 정규화한다(종목·ai_model 오인 방지).

**FR-STR-023e** [설정값 상한·타당성 방어, 2026-07-20] `enforce_strategy_minimums`(FR-STR-023c의 하한 방어와 대칭)는 상한·타당성도 강제해야 한다. ① 손절/익절/트레일링/MDD 비율이 100%를 초과하면(매수 포지션 손실률 한계 -100%) 반영하지 않고 안내한다. ② 수수료·슬리피지가 상식 상한(10%)을 넘으면 기본값(0.015%/0.05%)으로 복원하고 안내한다. ③ 수수료·거래세·슬리피지보다 작은 극소 손절/익절 폭은 경고를 남긴다(무언 드롭 금지). ④ [백테스트 창 = 보유 데이터 구간, 2026-08-02 개정] 백테스트 창은 `DATA_FLOOR_DATE`(1996-01-01) ~ `data_ceiling_date()`(오늘) 안이어야 하며, 벗어나는 방향에 따라 처리가 다르다(`enforce_backtest_window_bounds`). (a) **시작일만 데이터 이전** — 종전대로 날짜를 유지하고 커버리지 안내만 남긴다(엔진이 가용 구간부터 시작). (b) **종료일이 미래** — 종료일을 오늘로 **절단**하고 알린다. '2035년까지'의 실제 의도는 "가능한 데이터까지"이고, 절단하지 않으면 엔진은 조용히 오늘까지만 돌리는데 요약 카드·결과 배지는 요청한 날짜를 보여줘 **화면과 실행이 어긋난다**(FR-STR-023d의 '화면에 보이는 기간이 곧 실행되는 창이다'와 같은 계약). (c) **창 전체가 데이터 밖**(전부 미래이거나 종료일이 1996년 이전) — `backtest_window_is_empty`가 참이면 창을 **버리고** 기간을 다시 묻는다(초기 자금 상한과 같은 계약: 값 폐기 + `reask_fields`로 explicit provenance 제거 → 되묻기 게이트가 재질문). 이 검사가 없으면 요청이 그대로 통과해 사용자가 전략을 완성하고 실행 버튼을 누른 **뒤에야** 엔진의 "분석 가능한 유효한 데이터가 없습니다" 예외로 알게 된다. 상한 정본은 파케이 조회가 아니라 '오늘'이다 — 파싱 경로에 파일 I/O를 넣지 않으며, 오늘과 마지막 거래일(주말·장 마감 전) 사이의 차이는 엔진이 흡수한다(없는 날짜는 행이 없을 뿐). 설정 패널(`BacktestConfig`)의 '직접 입력' 날짜도 같은 경계를 `min`/`max`로 걸고 벗어나면 실행을 막는다. ⑤ `max_positions`는 스키마 상한(`le=100`)을 넘는 입력("500종목")이 ValidationError로 파싱 전체를 실패시키지 않도록 `_clamp_max_positions` 검증기가 범위로 클램프한다. 모순 필터(PER ≤10 AND PER ≥20)는 검증 agent(`_validate_logical_conflicts`, `LOGICAL_CONFLICT`)가 검출한다. ⑥ [초기 자금 상한 100억원, 2026-08-02] 초기 자금이 `MAX_INITIAL_CAPITAL`(100억원)을 초과하면 **보정하지 않고 값을 버린다**(`enforce_initial_capital_bounds` — 하한 미만은 종전대로 하한으로 클램프). 상한으로 깎아 맞추면 사용자가 말한 적 없는 금액을 시스템이 확정하는 것이고, 그대로 두면 백테스트가 무의미해진다 — 1회 매수 금액(초기 자금 ÷ 최대 보유 종목 수)이 전일 거래대금의 `liquidity_limit_pct`(기본 10%)를 넘으면 엔진이 그 종목의 진입 신호를 통째로 지우므로(`engine/loader.py::check_liquidity`), 자금이 커질수록 전 종목이 "유동성 기준 미달(거래대금 부족)"로 빠진 빈 결과가 나온다(2026-08-02 사용자 보고: 100조 · 최대 12종목 → 1회 매수 8,333억 → 통과에 필요한 전일 거래대금 8.3조/일 → 전 종목 제외). 값을 버린 뒤에는 **provenance(`explicit_fields`)의 `initial_capital`도 함께 떼어내** 되묻기 게이트가 다시 묻게 한다(`main._drop_rejected_provenance`) — 기록만 남으면 되돌아온 기본값 1천만원이 사용자 확정으로 판정돼, 설정하지 못했다는 안내를 읽고도 말한 적 없는 금액으로 백테스트가 실행된다(FR-STR-019k와 같은 계약). 파생 상태(`field_states`)도 함께 무효화해 떼어낸 provenance로 재계산한다. 설정 패널(`BacktestConfig`)의 직접 입력도 같은 상한을 걸어 실행 버튼을 막고 안내한다(대화 레인만 막으면 패널이 그대로 우회로가 된다). 상한값 자체(100억)는 허용한다.

**FR-STR-019f** [수정 경로 결정성·환각 방어, 2026-07-20] 완성된 전략의 수정 요청은 다음을 보장해야 한다. ① [지표 삭제] "RSI 조건 빼줘"는 언급된 지표의 진입/청산 신호만 제거하고 다른 필드(펀더멘털 필터·리스크)를 보존한다(`_extract_signal_removals` — LLM 수정이 요청과 반대로 다른 조건을 지우던 사고 방지). ② [전면 재작성] "완전 다르게 해줘"처럼 정보 없는 재작성 요청은 임의의 새 전략을 만들지 않고 방향을 되묻는다(`full_rewrite_clarification`). ③ [패치 환각 게이트 — 출처 대조, 2026-07-26 개정] LLM 인터프리터(primary 모드)가 낸 패치 중 발화에 근거가 없는 패치는 환각으로 거부한다(`strategy_conversation/primary.py::_patch_provenance_supported` — 후속 질문 "다른 예는 없어?"에 손절·리밸런싱·날짜가 임의 주입되던 사고 방지). 판정은 원문 어휘 스캔이 아니라 **대조**다(nl_interpretation_contract § 3-1 (b)): (i) LLM이 `PatchOp.source_text`로 인용한 원문 조각의 실재 확인(표기 정규화 후 포함), (ii) 패치 수치와 입력 수치의 대조(단위 환산 포함), (iii) 지정 종목의 해석 가능성(마스터 조회). 전량 환각이면 전략을 유지하고 미해석 안내로 응답한다(원문 정규식 질문 판정·레거시 fast-path 상담은 계약 위반이라 제거). **판정 단위는 필드가 아니라 조건 하나다(2026-07-31 개정)** — 같은 조건 객체를 겨냥한 형제 패치(`/entry_conditions/0/{factor,operator,value}`)는 지표를 통째로 갈아끼우는 한 덩어리의 수정이므로 `_patch_group_key`로 묶어 함께 판정하며, 그룹 안에 출처가 확인된 패치가 하나라도 있으면 전부 수락한다(근거 없는 그룹은 그대로 거부). 필드 단위로 따로 판정하면 인용이 한 글자 어긋난 패치만 거부돼 **LLM이 제안한 적 없는 상태**(`ma_crossover <= 50`)가 만들어지고 검증이 연산자 오류로 폴백해 요청이 통째로 사라진다(실사례: "매주조건을 per 50이하로 변경해줘" → LLM이 인용을 '매우조건을'로 오기 → factor 패치만 거부). **인용은 수치 대조를 대신 통과시키지 않는다(2026-08-02 개정)**: (i)의 인용이 실재하더라도, 인용문에 숫자가 있고 패치 값의 숫자와 **10의 거듭제곱 배수**만큼 어긋나면 그 인용은 근거가 아니라 값이 틀렸다는 증거이므로 수락하지 않는다(`_quote_contradicts_value` — 입력 해석이 아니라 LLM 출력 두 조각의 대조다). 실측 사고 2건이 모두 정확히 10배였다: "3억원"→`value=30000000`(3천만원), "1000억원"→`value=10000000000`(100억원, 수치 재요청 1회 후에도 동일). 후자는 인용이 실재해 게이트를 통과했고, 값이 공교롭게 초기 자금 상한(100억)과 같아 FR-STR-023e ⑥의 상한 안내도 뜨지 않은 채 조용히 확정됐다. 판정을 10의 거듭제곱으로 좁히는 이유는 단위 환산에 하나로 정해지지 않은 관례가 있기 때문이다 — "최근 3개월"을 인터프리터는 `lookback_days=90`(달력일), 환산표는 63(거래일)으로 잡으며 둘 다 옳다. 값 안의 `source_text`는 수치 집계에서 제외한다(인용은 원문 조각이라 언제나 입력의 숫자를 포함해 자기 자신과 대조되면 검사가 침묵한다 — `recall_validator._reflected_numbers`와 같은 계약). 자릿수가 어긋난 패치가 전부 거부되면 전략은 무변경으로 유지되고 미해석 안내가 나가며, 해당 설정은 explicit provenance가 붙지 않아 되묻기 게이트가 다시 묻는다. 아울러 factor가 교체된 조건에 남는 이전 지표의 파라미터는 `conversation/patch_applier.py::_drop_stale_parameters`가 registry 기준으로 떨어낸다(LLM 출력에 대한 결정론 정규화 — 남겨두면 "'PER'에 알 수 없는 파라미터 short_period"로 같은 폴백이 재발). **③-1 [생성 턴 조건 출처 대조, 2026-08-14]** 같은 출처 인용 대조를 **새 전략 생성 턴의 조건**에도 적용한다(`_drop_fabricated_conditions`) — 인터프리터가 프롬프트 예시 코퍼스의 조건("거래대금 50억 원 이상")을 인용문까지 지어내 사용자가 말하지 않은 조건을 조용히 추가하는 것을 전수 예시 검증(81개)에서 재현했다. 인용(`source_text`)이 입력에 실재하지 않는 조건은 빼고 안내한다. 단 인용 전체 포함이 실패해도 **4자 연속 조각**이 입력에 있으면 통과시킨다 — LLM이 인용을 가볍게 다듬는 경우(조사 생략·어순 변화)에 진짜 조건을 오살하면 이 가드가 막으려는 조용한 소실을 스스로 일으키기 때문이다(완전 조작 인용은 4자 조각조차 공유하지 않는다). 인용이 없는 조건은 대조 불가이므로 건드리지 않고 완결성 검증의 되묻기에 맡긴다. 아울러 **온톨로지 선언이 '매도 신호'인 개념**(`concept.dead_cross` 등)을 인터프리터가 `entry_conditions`에 앉히면, 청산이 비어 있는 경우에 한해 선언대로 청산 레인으로 옮긴다(`_fill_deterministic_condition_params` ③ — 연산자 덮어쓰기와 같은 선언 기반 정규화이며 원문을 읽지 않는다). "골든크로스 매수, 데드크로스 매도" 예시에서 명시한 매도 규칙이 사라지고 진입에 동일 매수 신호 2개가 남은 채 "언제 팔까요?"를 되묻던 사고의 방어선이다(프롬프트 예시 3-0-1이 1차 방어이나 temperature 0에서도 배치가 흔들려 고정되지 않았다). 인용에 매수 계열 표기가 있으면(역발상 진입) 옮기지 않는다. ④ [내부명 비노출] 미지원 안내 문구에 내부 식별자(`strategy_evaluation` 등)를 노출하지 않고 사람이 읽는 라벨로 치환한다(`_humanize_features` — 매핑된 내부명만 대상, FCF·technical.beta 등 사용자 어휘는 유지). ⑤ [LLM 수치 드리프트 교정 — 기본 비활성, 2026-07-26 개정] 결정적 추출 보정(`engine.nl_parser._apply_prompt_overrides`)은 기본값 off다(FR-STR-019j — 원문 정규식이 LLM 해석을 덮어쓰는 것은 계약 위반). 수치 드리프트는 수치 반영 대조(recall_validator)→LLM 재생성이 담당하며, 롤백은 `STRATEGY_PROMPT_OVERRIDE_MODE=on`. ⑥ [값 없는 수정 요청 3단 되묻기, 2026-07-24] 바꿀 내용이 불완전한 수정 요청은 수정 파싱으로 보내지 않는다 — LLM diff가 전부 null이라 무변경 전략만 조용히 재렌더링된다. 프론트 결정 레이어(`conversationDecision.ts` `MODIFICATION_CLARIFICATIONS`)가 구체도 순서로 결정적으로 가로채 되묻는다. (a) **필드 층**: 필드는 언급했지만 값이 없는 발화("손절 바꿔줘", "리밸런싱 주기 바꿀 수 있어?")는 그 필드의 값 칩(손절/트레일링/MDD/종목 수/보유기간/리밸런싱/초기자금/백테스트 기간 — 익절은 기존 `buildTakeProfitPercentagePrompt`가 담당)으로 되묻는다. 값 칩은 완결 지시문이라 재전송 시 가로채지지 않고 백엔드 결정론 fast-path(`_modify_rule_based`)가 처리하며, 칩별 추출 계약은 `STRATEGY_UI_SETTING_SUGGESTIONS`(백엔드 테스트)가 검증한다. (b) **영역 층**: 영역만 언급한 발화("진입 신호를 바꾸고 싶어")는 그 영역의 옵션 칩으로 되묻는다. (c) **catch-all 층**: 영역·필드도 없는 메타 요청("조건을 변경할 수 있어?", area=`condition`)은 영역 칩(진입 신호/청산 신호/유니버스/포트폴리오/리스크)으로 되묻고, 영역 칩은 재전송 시 (b)로 다시 가로채지는 2단계 플로우라 백엔드에 도달하지 않는다 — 백엔드 칩 계약 테스트(`test_strategy_ui_exposes_only_suggestions_covered_by_backend_contract`)가 이 5칩을 프론트 가로챔 예외로 명시한다. 값이 이미 명시된 발화(`explicitPattern`, catch-all은 `EXPLICIT_CONDITION_TARGET_PATTERN`)와 삭제/유지 발화는 기존 수정 경로에 맡긴다. 값 칩이 fast-path에 남으려면 `_MODIFY_FIELD_CUES`가 칩 어휘를 커버해야 한다(매월/매년 등 주기 어휘 누락으로 LLM에 새던 것 보정). (d) **종목 변경 의향** [2026-07-26]: 구체 종목명 없는 대상 종목 교체 의향("종목을 변경/교체 할 수 있나?", "다른 종목으로 하고 싶어", `missing_target_symbols_change`)은 **칩 없이**(suggestions 빈 배열 — 특정 종목 선택지를 내밀면 추천 소지, 사용자 결정) 채팅 입력 안내만 응답한다("삼성전자만으로 백테스트해줘"·"현대약품은 빼줘"·"반도체 관련주로 바꿔줘" 예시 포함 — 교체·제외·추가는 백엔드 수정 경로가 자유 발화로 처리, FR-STR-068 ⑥). 구체 종목명이 함께 온 발화("종목을 삼성전자로 바꿔줘")는 topicPattern의 어미 인접성(종목+조사+동사 직결)이 깨져 가로채지 않고 수정 파싱으로 통과한다. 또한 결정론 즉답(respond) 턴은 현재 전략이 있으면 '현재까지 이해한 전략입니다' 요약 카드(`builderPresentation`)를 답변과 항상 함께 표시한다(사용자 지시 — 안내가 전략 맥락 없이 떠 있지 않도록).

**FR-SA-002d** [전략별 특화 빌더 — STATE_SPECIFIC_STRATEGY_BUILDER] 사용자가 특정 전략명(볼린저·RSI·MACD·이동평균(골든크로스)·돌파·모멘텀·거래량·스토캐스틱·CCI·가치·과매도 반등)을 이름으로 지목하면, 시드(`seed_state`→`_parse_strategy_type`)가 그 유형을 미리 채워 첫 질문에서 확인하고 일반 종목 선정 메뉴("어떤 방식으로 종목을 고를까요?")를 다시 띄우지 않는다(지목된 전략 유실 방지). 유형이 정해지면 하드코딩된 고정 순서 대신 **전략별 파라미터 스텝 레지스트리**(`STRATEGY_PARAM_STEPS`)를 구동해 그 전략의 핵심 파라미터만 묻는다 — RSI: 기간·과매도/과매수; 이동평균: SMA/EMA·단기/장기; MACD: 크로스오버/제로선; 돌파/모멘텀: 기준일; CCI: 기간·기준값; 거래량: 평균 기간; 가치: PBR/ROE. 초보자는 각 스텝에서 '기본값'으로 표준값을 채울 수 있다.

시드는 업종/섹터도 기억한다(2026-07-11) — 종목 질문 전환(FR-SA-006) 뒤 "반도체 주도주로 전략을 만들어줘"처럼 사용자가 업종을 말하면 `seed_state`가 NL 파서의 결정적 섹터 추출(`_extract_sector`, FR-STR-066)로 `BuilderState.sector`를 미리 채우고("주도주"는 모멘텀 유형으로 인식), 종목 고르는 질문을 다시 묻지 않고 빠진 필드만 질문한다. 기억한 업종은 첫 질문 도입부에서 확인되며 합성 프롬프트("코스피 반도체 업종 종목 중 …")와 직접 조립 DSL(`ParsedStrategy.sector`)까지 흐른다. 섹터는 질문으로 묻지 않는다(시드 전용).

업종/테마 언급을 결정적으로 매핑하지 못한 경우("원자로 관련주 전략을 만들자")에도 조용히 버리지 않아야 한다(2026-07-12) — 시드와 대화 중 입력 모두에서 목록 밖 업종 언급을 감지하면(`BuilderState.sector_unresolved`+원문 `sector_hint`, NL 파서의 미지원 섹터 감지 재사용) ① 먼저 **LLM 해석기**(`llm_extract_sector` — 지원 업종 전체 목록(39개)을 담은 매핑 프롬프트, 라우트가 `_llm_available()`일 때 주입)가 정본 업종으로 매핑을 시도한다('원자로'→'에너지/원자력', 'K뷰티'→'화장품/패션'). 목록은 `universe_pit.sectors_for_llm_prompt()`(단일 출처, 메인 파싱 COMPACT 프롬프트와 공유)를 쓰며, 이름만으로 분류 관례를 오해하기 쉬운 업종에는 짧은 주석을 붙인다 — '전력설비 관련주'가 이름 연상('전력→유틸리티')으로 통신/유틸리티(실제: 통신사·한전 등 사업자)에 매핑되던 사고의 재발 방지(변압기·전력설비 제조=에너지/원자력, 전선 제조=IT 하드웨어). 출력은 반드시 `normalize_sector`로 재검증하며(목록 밖 이름 지어내기 무시), 성공 시 `sector`로 반영해 확인 문장("○○ 업종 대상(으)로 이해했어요")과 요약 배지까지 관통한다(안내 없음). ② 매핑 불가(null)·LLM 미가용·예외 시에만 "말씀하신 업종/테마는 아직 지원 목록에 없어 업종 제한 없이 진행돼요 + 지원 업종 예시" 안내를 **한 번만** 표시하고(표시 후 플래그 소비, 즉시 confirmed되는 경우엔 `notices` 채널) 현재 질문을 이어간다. 사용자가 대화 중 지원 업종을 말하면("기계/장비 업종으로") `parse_input`이 캐치해 `sector`로 반영하고 확인 문장으로 응답한다. 안내 없이 전체 시장으로 백테스트되던 침묵 유실의 회귀 방지(test_seed_unsupported_sector_notice_shown_once, test_unresolved_sector_resolved_by_llm_resolver).

**FR-SA-002e** [빌더 조건 수정 규칙 — 진행 중 삭제·선행 설정·값 없는 변경, 2026-07-26] 전략 빌더는 선형 설문이 아니라 **언제든 수정 가능한 편집 과정**이다: 어느 단계에서든 이미 결정된 조건을 삭제·추가·변경할 수 있어야 하며, 판정은 전부 결정적 규칙(정규식 cue)으로 한다(LLM 분류기 없음). ① **REMOVE**: 삭제 cue(빼·삭제·제거·없애·지워·취소)가 **채워진 필드**를 지목하면(`_parse_removal`) 그 필드만 비우고 삭제 안내("손절 -10% 조건을 제거했습니다" — 손절은 항상 마이너스 표기, FR-STR-030b)와 함께 기존 진행 위치로 복귀한다. 대상: 청산 개별(손절/익절/트레일링/보유기간)·"청산" 전부·필터 종류별(거래대금/추세/RSI)·"필터" 전부·업종 제한·테마 종목 제한·보유 종목 수. 채워진 필드만 대상이라 일반 어휘("코스닥 빼고")가 오염되지 않으며, "손절 취소해줘"의 '취소'는 빌더 취소 제어어보다 삭제로 우선 해석한다(맨 '취소'는 여전히 빌더 취소). 청산 값이 모두 사라지면 청산 단계를 다시 열고(필수 유지), 리밸런싱 삭제는 필수 항목이라 비우는 대신 '안 함'으로 명시 변경한다. 업종 삭제 문구의 '업종' 언급은 미지원 업종 되묻기(FR-SA-002d)로 새지 않는다. ② **SET-ahead**: 현재 질문과 무관하게 미리 말한 청산 조건("보유 종목 수 질문 중 '손절 10% 걸어줘'")은 키워드 앵커 청산 파서로 흡수해 `risk_done`까지 완료하고(시드 `apply_parsed_seed`와 동일 계약 — 이미 준 값은 다시 묻지 않음) 캡처 확인 문장("10% 손절 조건으로 하겠습니다") 후 진행 위치를 유지한다. 필터는 '필터' 명시가 있을 때만 흡수한다(파라미터 단계의 "60일 이동평균" 답이 추세 필터로 새는 오귀속 방지). ③ **값 없는 변경**: 변경 cue(바꾸/바꿔/바꿀/변경 등)는 있는데 새 값이 전혀 파싱되지 않으면(`_parse_valueless_change`) 값 없는 무변경 재렌더링 대신 해당 필드를 비워 그 질문으로 자연 복귀시킨다("시장 바꿔줘"→시장 질문, "전략 바꿀래"→유형 질문+특화 파라미터 리셋). 청산은 값을 유지한 채 단계만 다시 열어(마지막 단계 재질문 안내) 새 값이 기존을 덮어쓰게 한다. ④ **호환성 검토**: 가치 전략이 설정된 상태의 ETF 유니버스 변경은 적용하지 않고 이유와 우회 경로("전략 바꿔줘")를 안내한다(BF-12 역방향). 업종도 변경 cue가 있으면 덮어쓴다(유니버스·유형과 동일 계약, BF-05 확장). 특정 종목 지정은 여전히 MODIFY 대상이 아니다(BF-11 유지 — 단일 종목 테스트 경로 안내). 회귀: `backend/tests/test_builder_modify_rules.py`, 퍼징 게이트 `scripts/qa_builder_fuzz.py` 0실패 유지.

**FR-SA-002c-7** [테마 관련 투자 언급 라우팅 + 일반 답변 용어 정의 사실 주입, 2026-07-24] ① 테마/업종 '관련 투자' 언급("ess 관련 투자", "2차전지 관련 투자", "반도체 관련주", "원자로 테마주")은 전략 동사가 없어도 투자 아이디어 제시이므로 일반 지식 답변이 아니라 **전략 설계(STRATEGY_ADVICE)**로 결정적으로 라우팅해야 한다(`intent/classifier.py::_THEME_INVEST_CUE` — 빌더 시드 → 섹터/용어 그라운딩 체인 FR-STR-069/070 관통). 실측 사고(2026-07-24): "ess 관련 투자"가 LLM 일반답변으로 새서 ESS를 '에너지 효율성·저탄소·지속 가능성'으로 환각 정의하고 성장 잠재력 평가까지 답변. 가드: 열린 추천 요청("AI 관련주 추천해 주세요" — `is_stock_pick_request`)은 기존 STOCK_PICK 리다이렉트 유지, 종목명+행동 질문("삼성전자 관련주 살까?")은 STOCK_ANALYSIS 유지, 정의형 질문(`pure_definition`)은 가로채지 않는다. ② 그래도 일반 지식 답변 경로로 가는 테마 용어 질문("ESS가 뭐야?")을 위해 `/query/general`(`generate_general_answer`)은 LLM 호출 전에 **검증된 용어 정의 사실 블록**(`engine/term_grounding.py::general_facts_block`)을 프롬프트에 주입해야 한다 — 지식그래프 시드 개념(description) → 어휘집(검색 학습분) → 검색 그라운딩(둘 다 미스 + 검색 가능 시, 학습 결과 어휘집 저장으로 재검색 금지) 순. 블록은 정의와 모순되는 서술·시장 전망·성장 잠재력 평가를 금지하는 지시를 포함한다. 기초 용어 질문(glossary/기본값 facts가 이미 커버)은 검색 폴백을 건너뛰고(`allow_search=False`), 정본 섹터로 해석되는 용어(반도체 등)도 검색하지 않는다. 사실 주입 실패는 답변 자체를 막지 않는다(best-effort).

**FR-SA-002c-8** [읽기 전용 질문 라벨 — 진행 상태 되묻기·결과 수치 설명, 2026-08-11] 사용자가 **이미 정해진 것을 되묻는** 발화("내가 지금까지 뭘 정했지?", "아까 손절 몇 퍼센트로 했었지?", "지금 몇 단계까지 왔어?")와 **이미 나온 백테스트 결과의 수치를 묻는** 발화("MDD -35%면 심한 거야?", "샤프지수 1.2면 어느 정도야?", "승률은 높은데 수익이 왜 마이너스야?", "이 결과 믿을 만해?")에는 전용 라벨 `QueryIntent.STRATEGY_STATUS` / `QueryIntent.RESULT_EXPLAIN`이 있어야 한다.

*배경(2026-08-11 커버리지 프로브 실측)*: 라벨이 없을 때 9B는 같은 입력을 `STRATEGY_ADVICE`↔`UNKNOWN`으로 흔들었고(8회 반복 시 5:3, 7:1), 라벨 자리에 제어값을 넣는 출력(`{"intent": "NONE"}`)까지 냈다 — 이는 JSON 파손이 아니라 **고를 라벨이 없어서 생긴 증상**이며, `normalize_intent_label`이 걸러 "해석 실패"로 보고됐다. 유형별 4문항 중 각 2건이 UNKNOWN으로 떨어졌고, 라벨 추가 후 8문항 전부 제자리로 갔다(못 알아들음 5→0, 해석 실패 2→0).

① **읽기 전용 계약**: 두 라벨은 `_EFFECT_BLOCKED_INTENTS`에 들어 `workflow_effect`와 `clarify_target`이 항상 NONE/None으로 강등된다. 규제 때문이 아니라 **묻기만 하는 발화가 상태를 바꾸면 안 되기 때문**이다 — "아까 손절 몇 퍼센트였지?"가 ROLLBACK으로 새면 묻기만 한 사용자의 전략이 되감긴다. 규제 게이트가 아니므로 정형 거절 문구(`suggested_reply`)는 달지 않는다.

② **진행 상태 답변은 LLM을 쓰지 않는다**: 확정 설정·진행 단계는 이미 화면 상태에 있으므로 `currentStrategyPresentation()`이 만든 요약·진행 카드가 답이다(`conversationDecision.ts` → `action: "respond"`). LLM에 맡기면 사용자가 정한 적 없는 값을 지어낸다. 전략이 없으면 "아직 정해진 조건이 없어요"로 안내한다.

③ **결과 수치 설명은 사실 주입 필수**: 화면이 실제 결과를 사실 블록으로 만들어(`app/analytics/new/backtestResultFacts.ts`) `/query/general`의 새 `facts` 필드로 넘기고, 백엔드는 이를 `[사실]`로 프롬프트 맨 앞에 주입한다. 주입이 없으면 LLM이 사용자의 결과가 아닌 남의 숫자를 지어낸다. 값이 없는 지표는 줄을 만들지 않는다(0으로 채우면 "거래 0건" 같은 거짓 사실이 된다). 결과가 없으면 답변 레인을 아예 부르지 않고 안내로 끝낸다. `facts`가 있으면 설정 기본값 결정론 답변(FR-SA-002c-5)과 용어 검색 그라운딩(FR-SA-002c-7)은 건너뛴다 — 묻는 대상이 플랫폼 설정도 용어도 아니다.

④ **[규제 안전] 결과 설명의 경계**: 전용 시스템 프롬프트(`_RESULT_SYSTEM_PROMPT`)가 지표의 의미와 수치 간 관계까지만 허용하고 우열 평가·권유·전망·타 전략 비교를 금지한다. 판단을 요구하는 질문("이 결과 믿을 만해?")에는 평가 대신 과거 데이터 시뮬레이션이라는 사실과 워크포워드·몬테카를로 검증으로 견고성을 확인할 수 있다는 안내를 준다. 프롬프트 지시만으로는 9B가 완전히 지키지 못하므로(실측: "샤프 지수 1.21은 위험 조정 후 수익성이 긍정적인 수준") 출력 필터 `guardrails.strip_metric_grading`이 등급 표현("양호·우수·긍정적·안정적·효율적…")이 든 문장을 걷어낸다. 이 필터는 결과 설명 경로 전용이며 공용 `_FORBIDDEN`(행동 지시 금지)과 축이 다르다 — 합치면 AI 리포트 등 기존 호출부 출력까지 바뀐다. 지표 **간 관계** 설명("승률이 높아도 평균 손실이 크면 총손익은 마이너스")은 남긴다.

**FR-SA-002c-9** [종목 지표 값 조회 — 규제 게이트를 라벨과 직교하는 축으로 분리, 2026-08-11] "삼성전자 PER이 얼마야?", "카카오 부채비율 몇 퍼센트야?", "현대차 배당수익률 알려줘"처럼 **특정 종목의 지표 값을 묻기만 하는** 발화에는 값으로 답해야 한다. CLAUDE.md는 객관적인 과거 데이터 표시와 재무 지표 제공을 **명시적으로 허용**하며, 금지 대상은 추천·전망·매수 시점 제안이다. 그런데 `STOCK_ANALYSIS` 라벨 하나가 "삼성전자 사도 될까?"(금지)와 "삼성전자 PER 얼마야?"(허용)를 같은 거절 문구로 묶고 있었다(2026-08-11 커버리지 프로브: 사실 조회 6문항 전부 차단).

① **직교 축**: `IntentInterpretation.fact_metric`(닫힌 목록, `intent/stock_facts.py`)을 `workflow_effect`·`clarify_target`과 같은 계약으로 신설한다 — LLM은 목록에서 지표만 제안하고 성립 여부는 결정론이 정한다. 성립 조건 셋을 모두 만족해야 한다: 라벨이 `STOCK_ANALYSIS`, 정규화된 지표가 있음, 종목 정본 매핑 성공 + 국내 종목. 하나라도 어긋나면 기존 거절 안내 그대로다(안전 방향).

② **[규제 안전] 축은 답변 자유도를 열지 않는다 — 이것이 이 설계의 안전 근거다.** LLM은 "어떤 지표를 물었나"만 고르고, 답변 문장은 `stock_facts.metric_answer`가 데이터에서 읽어 **정해진 틀**에 채운다(값·기준일·"매수·매도 판단이나 종목 추천은 제공하지 않습니다"). 높다·낮다·싸다 같은 해석은 붙이지 않는다. 따라서 축이 오판돼도 최악은 '숫자를 보여준다'이지 '사도 된다고 말한다'가 아니다. 회귀 `test_stock_fact_lookup.py::test_fact_answer_never_evaluates_even_if_axis_misfires`가 이 성질을 LLM 없이 고정한다.

③ **프롬프트 배제 규칙**: 규칙 16(값만 묻는 경우에만 — "PER 낮은데 사도 될까?"는 매수 판단이므로 null)과 규칙 17(종목 고르는 **조건**으로 쓴 지표는 null — "PER 10 이하 종목으로 전략"은 STRATEGY_ADVICE)이 게이트 누수를 막는 유일한 장치다. 실측: 판단 요청 3문항·판단 혼합 1문항·스크리닝 1문항·평가 요구 1문항 모두 거절 유지.

③-1 **지표 목록 표기는 '사용자 표기 → 키' 순**(2026-08-11): `키 — 라벨` 순으로 실으면 9B가 '영업이익률' 같은 한국어 지표명을 키로 잇지 못한다(실측 5/5 미추출, 온도 무관 — 모델은 목록을 '입력 표기 → 출력'으로 읽는다). 순서를 뒤집고 도입부에 `'네이버 영업이익률 알려줘' → operating_margin` 예시를 추가해 10/10. 회귀는 프롬프트 표기 자체를 고정한다(`test_stock_fact_lookup.py`).

④ **데이터 정본은 백테스트 엔진과 같은 종목별 parquet**(`data/ohlcv/<symbol>.parquet`)이다. KIS 실시간을 쓰지 않는 이유는 엔진 결과와 같은 값을 보여야 하고 외부 호출 실패가 답변을 좌우하면 안 되기 때문이다. 최신 행이 결측일 수 있으므로(재무는 분기 갱신) 뒤에서부터 유효값을 찾고 **그 값이 실제로 관측된 날짜**를 함께 밝힌다. 52주 최고·최저는 저장값이 아니라 최근 252거래일에서 계산하며, 이때 날짜는 '기준일'이 아니라 '그 값이 기록된 날'로 따로 표기한다. 값이 없으면 추정하지 않고 없다고 밝힌다.

⑤ **전략 진행 중 예외**: `hasCurrentStrategy`일 때 STOCK_ANALYSIS를 파싱 레인으로 넘기는 기존 가드(종목 추가 요청 삼킴 방지)는 `factMetric`이 있으면 건너뛴다 — 넘기지 않으면 전략 작성 중에는 값 질문이 영영 답변되지 않는다. 지표와 종목이 모두 확정된 발화는 "종목을 추가해 달라"는 수정 요청일 수 없다.

⑥ **계측**: 게이트 판정은 라벨만으로 세면 안 된다 — `report_intent_coverage.py`·`qa_intent_coverage_probe.py`의 `_is_gated`는 `fact_metric`이 있으면 '끊김'으로 세지 않는다. 라벨만 세면 게이트 분리의 효과가 리포트에서 보이지 않는다.

**FR-SA-002c-10** [구조화 출력 LLM은 greedy — 어댑터 2갈래 분리, 2026-08-11] 의도 분류·지표 키 선택·빌더 ops JSON·용어 추출처럼 **정답을 고르는** LLM 호출은 `temperature=0`(greedy)이어야 하고, 표현이 매번 달라져야 하는 산문 답변(`/query/general`)만 샘플링해야 한다.

*배경*: `api/intent_routes.py`의 어댑터 하나(`_mlx_llm`)가 `temperature=0.3, top_p=0.9`로 두 갈래를 모두 처리했다. 0.3은 산문 쪽에 맞춘 값이고(`nl_parser.chat` 주석: "temperature>0이면 표현이 매번 달라지도록 샘플링한다 — 코치용") 분류가 같은 어댑터를 쓰면서 **딸려온 것이지 분류를 위해 고른 값이 아니었다**. 전략 해석기(`llm_strategy_interpreter`)와 파싱 검증기(`parse_validator`)는 이미 `temperature=0`을 쓰고 있었다 — 구조화 출력엔 0이라는 기준이 코드베이스에 서 있었고 이 모듈만 예외였다.

*증상(실측 2026-08-11)*: 같은 입력 '코스닥 상장사 수가 몇 개야?'가 5회 중 `GENERAL_INVESTMENT`↔`UNKNOWN`으로 갈렸다(greedy 전환 후 5/5 고정). 라벨이 흔들리면 ① 같은 질문에 다른 답이 나가고 ② QA 하니스가 flaky해져 회귀를 놓치며 ③ 버그 재현이 안 된다.

*수정*: 공통 본체 `_chat(…, temperature, top_p)` 위에 용도가 이름에 드러나는 두 어댑터를 둔다 — `_mlx_llm_structured`(temperature 0.0 / top_p 1.0)와 `_mlx_llm_prose`(0.3 / 0.9). 5개 호출부 중 4개(분류, 빌더 리스크·업종 추출, 빌더 자유서술 ops, 용어 추출)가 structured, 답변 생성 1개만 prose다. `generate_general_answer`는 **한 함수 안에서 둘을 모두** 쓴다 — 용어 추출은 구조화, 답변 생성은 산문.

*회귀*: `test_llm_adapter_split.py`가 **배선**을 고정한다(값이 아니라 배선의 문제였으므로 — 다시 하나로 합쳐지면 증상이 조용히 돌아온다).

*검증(레드팀 156발화 라벨 대조, 2026-08-11)*: 레드팀 145케이스의 실제 발화 156개(중복 제거)를 temp 0.3 vs 0으로 분류해 대조 — 152/156 동일, 갈린 4건은 전부 **greedy가 0.3의 최빈값을 고정**한 것으로 판명(예: '잘 나가는 기업' 0.3=OFF_TOPIC 5/UNKNOWN 3 → greedy=OFF_TOPIC, '널스탁전자…' 0.3=STOCK_PICK 6/STOCK_ANALYSIS 2 → greedy=STOCK_PICK). 단발 대조에서 회귀처럼 보인 것은 0.3 컬럼이 1표본이라 희귀 분기를 뽑은 착시였고, greedy는 새 답을 만들지 않고 분산만 제거한다. PARSE_FAIL 1건은 일시 오류(재현 0/4).

**FR-SA-002c-11** [업종·테마 소속 목록 — 추천 요청과 분리, 2026-08-11] "반도체 업종에 어떤 회사들이 있어?", "2차전지 테마 종목 목록 보여줘"처럼 **어떤 종목이 속해 있는지 목록·구성을 묻기만 하는** 발화에는 소속 목록으로 답해야 한다(사용자 결정 2026-08-11 — 소속은 분류 사실이지 추천이 아니다). 종전에는 `STOCK_PICK` 라벨 하나가 "뭐 살까?"(열린 추천, 거절·빌더 전환)와 소속 질문을 같은 거절로 묶었다(커버리지 프로브: market_fact 목록 질문 2건 차단).

① **직교 축**: `IntentInterpretation.list_scope` — `fact_metric`(FR-SA-002c-9)과 같은 계약. LLM은 범위 표기를 원문 그대로 짧게 추출만 하고('반도체'·'코스피200'), 정본 성립은 `intent/stock_lists.resolve_listing`이 정한다 — 시장·지수 사전(코스피200=편입 캐시 `kospi200-cache.json`, 코스피·코스닥=마스터 market 필드. "코스피 200 지수는 약 403개" 환각의 결정론 대체, 실측 2026-08-11 — 실제 200) → 섹터 사전(`expand_legacy_sector`, '2차전지'→'이차전지' 동의어 포함) → 지식그래프 테마(`theme_listed_companies`, **그래프 조회만** — 검색 학습 체인은 타지 않는다). 미해석은 기존 안내 그대로(목록을 지어내지 않는다). 성립 라벨은 `STOCK_PICK`·`GENERAL_INVESTMENT`·`UNKNOWN`이다 — 구성·종수 질문('코스피200에 몇 종목?')은 라벨이 마땅치 않아 UNKNOWN으로 떨어지는데, 축은 정본 매핑+결정론 목록이라 UNKNOWN에서 열어도 오판의 최악이 '소속 목록 표시'다. `STRATEGY_ADVICE`에서 열면 스크리닝 조건이 목록으로 새고, 규제 거절 라벨에서 열면 정형 안내가 우회된다.

①-1 **출력 형식이 규칙보다 강하다(재확인)**: 시장·지수 추출 규칙과 예시를 넣어도 출력 형식 줄이 `"<업종/테마 표기>"`로 좁으면 9B가 '코스피200'을 채우지 않는다(실측 — 규칙·예시 무시, 출력 형식 줄을 `"<업종/테마/시장/지수 표기>"`로 넓히자 즉시 추출). 축 확장 시 규칙·예시와 **출력 형식 줄을 함께** 갱신할 것(`project_interpreter_output_shape_authority`와 동일 교훈).

② **[규제 안전] 답변은 결정론 목록에서 끝난다**: 총원 + 가나다순 회사명(코드) + "매수 추천이 아닙니다" + 전략 전환 안내. **정렬은 가나다순** — 시가총액·수익률순은 객관적 데이터라도 순위 암시를 만든다. 표시는 40곳 상한으로 자르되(채팅 버블 스크롤 벽 방지) 총원은 항상 밝힌다 — 절단은 표시뿐이며 백테스트 유니버스 종수 상한 절단 금지 원칙과 충돌하지 않는다. 상폐 종목 제외(현재 상장 기준). 프롬프트 규칙 19("살 만한/좋은 거"처럼 고르는 표현이 섞이면 null — 추천 요청 유지)·20(조건이 붙으면 전략 설계, 뜻 질문도 null)이 게이트 누수를 막는다. 실측: 소속 질문 2건 목록 응답, "살 만한/좋은 거" 2건 거절 유지, 스크리닝 1건 STRATEGY_ADVICE.

③ 전략 진행 중 파싱 레인 가로채기는 `listScope`면 예외(factMetric과 동일 — 안 그러면 작성 중 소속 질문이 영영 미답변). 계측 `_is_gated`도 이 축을 반영한다.

결정적 시드가 못 잡는 긴 꼬리 표현은 regex를 늘리지 않고 **파싱 파이프라인의 LLM 레이어가 해결한다**(2026-07-11, 하이브리드 원칙): 빈 전략으로 빌더에 전환될 때(FR-SA-002c의 빈 전략 전환) 프론트가 룰 파스→LLM 검증 교정(FR-STR-019~020)→LLM 폴백이 이미 해석한 최종 `ParsedStrategy` dump를 `BuilderStepRequest.seed_parsed`로 함께 넘기고, 빌더는 `apply_parsed_seed`로 결정적 시드가 놓친 필드를 이어받는다. 이어받는 필드는 ParsedStrategy 기본값과 사용자 언급을 구분할 수 있는 None-기본 필드(sector — 정본명 재정규화, 미지원 업종은 무시 — 와 청산 조건 손절/익절/트레일링/보유기간)로 한정하며(universe·max_positions·rebalancing_period는 기본값 오염 위험으로 제외), 결정적 시드가 이미 채운 값이 항상 우선한다. 검증 레이어 프롬프트에는 업종 제한 누락("반도체 중심으로" 등)을 sector 교정으로 채우되 사용자가 말하지 않은 업종은 지어내지 못하게 하는 규칙을 명시한다.

완성 시 **한국어 프롬프트 재파싱 왕복 없이 `build_parsed_strategy`가 `ParsedStrategy`(entry/exit `TechnicalSignal` + 랭킹/재무필터/리스크)를 직접 조립**하고 기존 `to_backtest_request`로 요청을 만든다(라우트가 confirmed 시 `parsed`+`backtest_request`+`notices`를 내려주고, 프론트는 `applyBuilderConfirmedStrategy`로 그대로 소비 — 파라미터 유실 방지). custom(자유 서술)만 DSL을 만들 수 없어 `prompt` 재파싱 경로로 폴백한다.

파라미터·신호는 **엔진(`engine/signals.py`·`_tech_signal_to_condition`)이 실제 반영하는 것만** 묻고 조립한다(답을 조용히 버리는 것 방지): 볼린저는 하단/상단 밴드 터치만(기간·표준편차·중심선 변형 미반영), 스토캐스틱은 크로스오버만(level 모드는 `TechnicalSignal.mode` literal로 표현 불가), MACD fast/slow/signal·히스토그램 미반영. **ATR는 엔진 전무이므로 빌더 유형으로 제공하지 않는다.** '볼린저'는 breakout('돌파')보다, 'RSI'는 mean_reversion(과매도 반등)보다 먼저 판정한다.

**[Tier 2 — 옵션 진입 필터]** 기술적 진입 전략(momentum·value·custom 제외)에는 핵심 파라미터 뒤 옵션 "필터" 스텝 1개를 둔다. 진입 신호와 **AND로 결합되는 게이트**를 `ParsedStrategy.entry_filters`(빌더 전용 채널)로 담아 `to_backtest_request`가 `type='filter'` 조건으로 내보내면, 엔진(`generate_signals`)이 signal 버킷과 분리해 항상 AND 결합한다. 지원 필터: ① 추세("EMA200 위에서만") — `ema` 평가자에 지속 상태 `mode='above'/'below'` 신설(크로스오버가 아니라 매 봉 close vs EMA 판정), ② 거래대금(유동성) — 기존 `trading_value`(≥ N억) 재사용, ③ RSI 결합("RSI 30 이하일 때만") — 기존 `rsi` compare 재사용. "없음"·무매치도 옵션이라 완료 처리하며, 자유 입력으로 복수 필터 동시 지정 가능. `entry_filters`는 canonical DSL 해시에 포함해 필터만 다른 전략의 캐시 충돌을 막는다. 원시 "평균 거래량 이상" 전용 평가자는 미구현(거래대금 유동성 필터로 대체).

**FR-SA-003 / FR-SA-004 / FR-SA-005** [제거됨 2026-07-10] 개별 종목 분석 파이프라인(종목 해석→parquet 분석→객관적 상태 등급→LLM 설명, `/stock/analyze`·`StockAnalysisPanel`)은 삭제됐다. 종목명 해석(`symbol_resolver`·`stock_master`)은 의도 분류용으로, `guardrails`(금지 표현 필터)는 `/query/general`용으로, `news_service`는 advisor 뉴스 보강용으로 유지된다.

**FR-SA-006** [규제 안전 — 유사투자자문업 회피] 특정 종목명 + 매수·매도·보유·전망 질문(`STOCK_ANALYSIS` 의도)에는 분석·판단·추천을 제공하지 않고, 다음을 담은 전환 안내(`suggested_reply`, `intent/scope.py::stock_question_redirect`)로 응답해야 한다: ① 매수·매도 판단과 종목 추천을 제공하지 않는다는 명시, ② 언급된 종목에서 출발한 **전략 설계 예시**로의 유도. 예시는 엔진이 실제 실행할 수 있는 개념만 사용해야 한다. 언급 종목의 섹터를 알면(예: 삼성전자→반도체) '그 종목이 속한 업종 종목만 대상으로 최근 3개월 수익률 상위 5종목 매수' 전략을 첫 예시로 쓴다(FR-STR-066 섹터 유니버스 지원). 섹터를 모르면 종목의 시장에 맞춘 예시를 쓴다(KOSPI→코스피200 대형주 모멘텀, KOSDAQ→코스닥 모멘텀). 공통 예시: 저평가 우량주 가치 스크리닝, RSI 과매도 반등. 예시 문구는 실제로 파싱·실행 가능해야 한다(회귀: test_stock_question_redirect_sector_example_is_parseable). 안내 문구 자체가 행동 지시 표현(`guardrails._FORBIDDEN`)을 포함해서는 안 된다. 프론트는 전환 안내 후 **전략 빌더 모드로 자동 진입하지 않고 사용자의 후속 답변을 기다린다**(2026-07-11) — 안내가 이미 그 종목 기반의 구체적 전략 예시를 제시하므로 빌더의 첫 질문("어떤 시장을 대상으로 할까요?")이 예시를 덮으면 안 된다(STOCK_PICK의 즉시 빌더 진입과 의도적으로 다름, 회귀: page.stock-redirect.test.tsx). 사용자가 예시를 골라 답하면 일반 전략 파싱 흐름이 처리한다. **이미 전략이 활성인 상태에서는 이 전환 안내로 가로채지 않는다**(2026-07-26 개정) — 전략 진행 중 종목명이 섞인 발화("제주반도체도 추가해줘")는 분류기가 STOCK_ANALYSIS로 오분류해도 수정 요청일 수 있으므로, 프론트 턴 중재(`conversationDecision.ts`)가 STOCK_PICK/STRATEGY_PICK/ONBOARDING과 동일하게 수정 파싱(`parse_strategy`, 백엔드 LLM 해석)으로 보낸다(실측 사고: 테마 유니버스 전략에 종목 추가 요청이 canned 안내에 삼켜짐. 회귀: conversationDecision.test.ts). 전환 안내는 활성 전략이 없을 때만 표시한다.

**FR-SA-007** [워크플로 제어 — 멈춤·이어하기·취소·초기화·되돌리기, 2026-07-30] 사용자 입력은 "무엇에 대한 발화인가"(`QueryIntent`)와 **"진행 중인 전략 작성을 어떻게 제어하는가"**(`WorkflowEffect`)라는 두 직교 축으로 해석해야 한다. 한 발화가 전략 요청이면서 동시에 취소일 수 없으므로 두 축은 겹치지 않는다. 제어 값은 `NONE`(기본 — 워크플로에 영향 없음)·`UPDATE`·`PAUSE`·`RESUME`·`CANCEL`·`RESTART`·`ROLLBACK` 7종이다. ① **판정은 LLM만 한다** — 기존 의도 분류 LLM의 출력 형태에 `workflow_effect` 키를 더해 한 번의 호출로 라벨과 함께 얻는다(`intent/interpreter.py`). 원문 정규식으로 제어어를 찾지 않는다(자연어 해석 계약). 표기 불량·미출력은 `NONE`으로 떨어지며, 이것이 라벨 분류를 실패시키지 않는다. ② **성립 여부는 결정론 코드가 정한다**(`intent/classifier.py::_resolve_workflow`) — [규제 안전] `STOCK_ANALYSIS`·`STOCK_PICK`·`STRATEGY_PICK`·`ONBOARDING`·`PERSONAL_ADVICE`·`LIVE_TRADING`·`UNSUPPORTED_FEATURE`·`GREETING`·`OFF_TOPIC` 9개 게이트 라벨에서는 제어를 인정하지 않는다(제어 한마디로 맞춤 조언·실계좌 매매 안내가 삼켜지면 안 됨). 진행 중인 전략이 없으면 `PAUSE`·`CANCEL`·`RESTART`·`ROLLBACK`은 성립하지 않고, 직전 상태가 `PAUSED`가 아니면 `RESUME`도 성립하지 않는다. 불성립은 오류가 아니라 `NONE` 강등이며 기존 대화 흐름은 그대로 이어진다. ③ **상태는 서버에 저장하지 않는다** — `WorkflowStatus`(IDLE/ACTIVE/PAUSED/CANCELLED)를 프론트가 `/query/classify` 요청에 에코한다(`previous_explicit_fields`·`pending_ask`와 같은 무상태 계약). 분류에 실패해도 이 값을 잃지 않아야 한다(실패가 사용자의 '멈춤'을 조용히 해제하면 안 됨). ④ **실행 범위** — `CANCEL`·`RESTART`만 전략 초안을 폐기하며(대화 기록·화면은 유지), `PAUSE`는 조건을 보존하고 `RESUME`은 진행을 이어간다. ⑤ **부가 질문은 워크플로를 멈추지 않는다** — 용어 질문·잡담("PER이 뭐야?")은 `NONE`이며 전략 State를 유지한 채 답변한다(FR-SA-002c-4와 같은 계약). `PAUSE`는 사용자가 명시적으로 요청했을 때만 쓴다. ⑥ **`ROLLBACK`은 감지하되 실행하지 않는다** — 변경 이력(Event Sourcing)이 없어 되돌릴 대상을 특정할 수 없으므로, 일반 거절 대신 미지원 사실과 지원 가능한 대안(바꾸고 싶은 조건을 직접 말하기)을 안내한다. 안내 문구는 라벨·효과를 키로 한 확정 문장이며 LLM이 짓지 않는다. 회귀: `backend/tests/test_intent_interpreter.py`, `app/analytics/new/conversationDecision.test.ts`.

**FR-SA-008** [되돌리기 — 변경 이력과 대상 판정, 2026-07-30] 사용자는 진행 중인 전략의 이전 상태로 되돌릴 수 있어야 한다("아까 바꾼 거 취소해", "ETF로 바꾸기 전으로 돌아가", "PER 조건 지운 것만 되돌려"). FR-SA-007의 `ROLLBACK` 효과가 이 요구사항으로 실행된다. ① **스냅샷 되감기이지 상태 재구성이 아니다** — 각 턴의 `ParsedStrategy` 전체가 이미 스냅샷이므로 이벤트를 되감아 상태를 만들지 않는다. ② **레인 분리**: 변경 산출은 결정론(`change_log.changed_field_names` — 값이 달라진 최상위 필드 **이름**. 사람이 읽는 로그 문장(`_diff_fields`)은 되돌리기 대상으로 쓸 수 없다), 보관은 클라이언트+세션 스냅샷(백엔드 무상태 계약 유지), 대상 판정은 LLM(`/strategy/rollback/resolve` — 원문 해석이므로 정규식 금지), 대조는 결정론, 복원은 스냅샷을 보유한 클라이언트. ③ **임의 보정 금지**: LLM이 지어낸 턴 번호를 '가장 최근 턴'으로 떨어뜨리거나, 그 턴에서 바뀌지 않은 필드를 되돌리려 하면 안 된다 — 사용자가 의도하지 않은 변경이 조용히 사라진다. 되돌리기는 작업을 지우는 동작이므로 모든 실패(LLM 미가용·출력 불량·없는 번호·목록 밖 필드·되돌릴 이력 없음)는 **되묻기로 종결**한다. ④ **provenance 동반 복원**: 되돌린 필드의 '사용자가 말했다' 기록(FR-STR-019k)도 함께 되돌린다 — 남기면 되돌아온 질문을 이미 답한 것으로 보고 건너뛴다. 필드 단위 복원은 되돌린 필드의 provenance만 맞추고 나머지는 유지한다(이후 턴의 답변은 여전히 유효하다). ⑤ **모델 슬롯**: 이 판정은 라벨 분류가 아니라 이력 목록 위의 추론이므로 인터프리터와 같은 9B 슬롯을 쓴다(실측 2026-07-30: 같은 프롬프트에서 4B 1/7 → 9B 5/7, 프롬프트 보강 후 4B 5/7·9B 7/7). 잘못 고른 턴은 사용자가 쌓아온 전략을 지우므로 슬롯을 아끼지 않는다. ⑥ **이력 표기**: 판정 LLM에 주는 이력에는 전략 값을 싣지 않고 무엇이 바뀌었는지만 싣되, 필드 이름은 `stop_loss_pct(손절)`처럼 사용자 어휘를 함께 표기한다 — 영문 이름만으로는 "손절 바꾼 거 되돌려"가 그 필드와 이어지지 않아 엉뚱한 턴이 선택된다(실측). ⑦ **대상 없는 요청**('되돌려', '취소해')은 가장 최근 변경을 되돌린다. ⑧ 필드 단위 복원은 전략이 새 조합이므로 `/strategy/compile`로 백테스트 요청을 재생성하고, 재생성에 실패하면 복원을 포기하고 현 상태를 유지한다(실행 불가 전략을 남기지 않는다). 회귀: `backend/tests/test_rollback.py`, `app/analytics/new/rollback.test.ts`.

**FR-SA-009** [사용자 정정과 Action 메타데이터, 2026-07-30] ① **정정(CORRECT)**: 직전 해석이 틀렸다고 지적하면서 올바른 지시를 함께 주는 발화("아니, 그런 뜻이 아니라 ~야")는 되돌리기(FR-SA-008)와 구분해 처리해야 한다 — 되돌린 **뒤** 그 발화로 다시 해석한다. 판정 기준은 **올바른 지시가 함께 있는가**이며, 되돌릴 지점은 LLM에 묻지 않는다(정정은 언제나 방금 한 해석을 겨냥하므로 직전 변경으로 결정론이 정해진다). 되돌릴 State가 없으면 정정이 아니라 새 요청이므로 `NONE` 강등 후 일반 파스로 흐른다. **사과·해명 문구를 붙이지 않는다** — 재해석 결과가 그대로 답이다(설계 스펙 § 20 "잘못 해석한 내용을 변명하지 마라"). ② **Action 메타데이터**: DAG 노드는 `requires`(필요한 State 필드)·`produces`(채우는 필드)·`invalidated_by`(무효화 트리거)를 갖는다. 이 값들은 **도구의 정적 성질이므로 LLM에 묻지 않고** 결정론 표(`dag._TOOL_EFFECTS`)가 채운다 — 프롬프트 출력 형태를 늘리면 소형 모델이 잡음을 내고 prefill 예산만 소비한다(FR-STR-019o·019p). LLM이 실어 보내도 알려진 도구면 표가 우선한다. ③ **Action 상태**: `PENDING`/`READY`/`RUNNING`/`COMPLETED`/`BLOCKED`/`INVALIDATED`/`FAILED`/`SKIPPED`. 완료 집합만으로는 "왜 실행되지 않았나"를 구분할 수 없다. **무효화된 노드는 목록에서 삭제하지 않고 `INVALIDATED`로 남긴다** — 지우면 무엇이 왜 취소됐는지 추적할 수 없고, 계획 LLM이 같은 노드를 다시 발행한다. ④ **무효화 규칙**: 씨앗은 **이미 완료된** 노드뿐이다(실행 전 노드를 씨앗으로 삼으면 정상 선행 실행이 무효로 잡힌다). 무효화는 의존 방향으로 연쇄하며, `invalidated_by`를 선언하지 않은 노드는 무효화되지 않는다. ⑤ **`preconditions` 미구현**: 표현식 평가 DSL이 필요한데 LLM 환각 여지가 크고 평가 실패가 '무시'로 떨어져 장식용이 된다 — 같은 제약을 `depends_on` 사슬과 검증·컴파일 게이트가 이미 구조로 강제한다. 회귀: `backend/tests/test_dag_planner.py`, `backend/tests/test_intent_interpreter.py`, `app/analytics/new/rollback.test.ts`.

**FR-SA-010** [확정(CONFIRM) — 값이 아니라 상태를 바꾸는 답, 2026-07-30] 시스템이 제시한 현재값을 사용자가 그대로 받아들이는 답변("최대 10종목" 칩 클릭, "응 그걸로 해줘")은 **값을 바꾸지 않으면서 상태를 PROVISIONAL → CONFIRMED로 올리는 연산**이며, 값 변경과 구분해 처리해야 한다. 설계 스펙 § 7의 State Patch 연산 중 이 코드베이스에서 새 능력인 것은 `CONFIRM` 하나다 — `INVALIDATE`·`MARK_CONFLICT`·`MARK_NOT_APPLICABLE`은 매 턴 전략 전체에 재실행되는 검증기가 이미 산출하고(`validate_capability`·`validate_conflicts`·`field_state.slot_status_overrides`), `REVALIDATE`는 파이프라인이 무조건 재검증하므로 지시할 대상이 없으며, `ROLLBACK`은 FR-SA-008에서 턴·필드 단위로 구현됐다. **상태를 패치로 저장하지 않는다** — 이 코드베이스의 상태는 저장되지 않고 계산되며(FR-STR-019q), 패치로 기록하면 같은 판정이 두 곳에서 갈라져 `strategy_slots`를 SOT로 모은 이유를 되돌린다. ① **결정론 레인(칩)**: 값이 안 바뀌는 칩에는 표현 불가한 칩과 **현재값을 그대로 가리키는 칩** 둘이 섞여 있으므로 구분해야 한다 — 구분 없이 전부 탈락시키면 시스템이 물어놓고 화면에 보여준 값을 사용자가 선택할 방법이 사라진다(실측 결함: "최대 몇 종목?"에서 `최대 10종목`, "초기 자금?"에서 `1,000만원`, "어느 기간?"에서 `최근 5년 데이터`가 선택지에서 소실). 구분은 **프로브**로 한다(그 필드를 현재값이 아닌 값으로 바꿔 둔 State에 칩을 적용해 현재값으로 되돌아오는지). "패치가 비었으니 직전 질문 필드의 확정"으로 추정해서는 안 된다 — 그 추정은 아무 뜻도 결속되지 않은 칩을 사용자 확정으로 둔갑시켜 되묻기를 삼킨다. 확정 칩은 `pending_ask.chip_confirms`로 값 결속(`chip_bindings`)과 **채널을 나눠** 에코한다(섞으면 무변경 패치가 되어 '반영 없음'으로 떨어진다). ② **LLM 레인(자유 서술)**: 확정이라는 판정은 원문 해석이므로 LLM(`CONFIRM_RECOMMENDATION`)이 하고, **무엇을 확정했는지는 묻지 않는다** — 확정은 언제나 직전 질문에 대한 답이므로 `pending_ask.topic`으로 결정론이 정한다(FR-SA-009 ①의 되돌림 지점과 같은 이유). 물어본 적이 없거나 확정 가능 슬롯이 아니면 임의로 고르지 않고 기존 경로로 넘긴다(말하지 않은 값 확정 금지). ③ **확정 가능 필드**는 물질화 기본값이 있는 단일 스칼라 설정 4개(최대 보유·리밸런싱·백테스트 기간·초기 자본)다. 기본값이 없는 필드(진입·청산·손절·익절)에는 확정할 대상이 없고, `universe`는 여러 속성의 합이라 '그 값 그대로'가 하나로 정해지지 않는다. ④ **잔여**: `리밸런싱 안 함` 칩은 결정적 칩 추출기가 그 문구를 인식하지 못해 여전히 탈락한다 — 인식시키려면 사용자 원문에 쓰이는 추출기의 어휘를 넓혀야 하므로 금지되며(대원칙 1), 올바른 해법은 planner가 칩 발행 시 값을 함께 선언하는 구조다. 회귀: `backend/tests/test_chip_answer.py`, `backend/tests/test_modify_roundtrip_migration.py`.

**FR-SA-011** [하이브리드 상태 모델 — 영속·계산·산출물의 분리, 2026-07-30] 대화 State의 상태는 한 종류가 아니며, **저장할 것과 매 턴 계산할 것을 나눈다**. 나누는 기준은 재계산 비용이다. ① **Persisted User State**(`ValueStatus`: UNKNOWN·INFERRED·PROVISIONAL·CONFIRMED) — 사용자가 제공·확정한 원본 값. 정본은 `ParsedStrategy`(값)와 `explicit_fields`(provenance)이며, 값을 `{value, status, …}`로 감싸지 않는다(FR-STR-019q ①). ② **Derived Runtime State**(`DerivedStatus`: APPLICABLE·NOT_APPLICABLE·INVALID·CONFLICTED) — **전략 State에 저장하지 않는다.** 현재 전략 전체를 기준으로 결정론 evaluator가 매 턴 계산하며(`validation/pipeline.py` → `field_state.py` → `strategy_slots.evaluate`, 실측 0.12ms), 진행률·경고·다음 질문·실행 가능 여부는 이 계산 결과를 쓴다. **가역성이 요구사항이다**: 유니버스가 ETF로 바뀌면 기존 PER 조건은 삭제하지도 NOT_APPLICABLE로 저장하지도 않고 원본 값을 유지한 채 현재 계산 결과만 NOT_APPLICABLE로 표시하며, 다시 KOSPI로 바뀌면 **별도의 역방향 Patch 없이** 자동으로 APPLICABLE이 되어야 한다(저장하면 그 되돌림을 LLM이 발행해야 하고, 빠뜨리면 멀쩡한 조건에 '적용 불가'가 영구히 남는다). ③ **Persisted Artifact State**(`ArtifactStatus`: VALID·STALE·INVALIDATED·FAILED) — Tool·Knowledge Graph·외부 검색 산출물처럼 재생성이 비싼 결과. "아직 맞나"를 재실행으로 확인할 수 없으므로 **무엇을 근거로 만들었는지**(`source_key`)를 저장하고 근거만 대조해 결정론으로 무효화한다. 판정이 조회를 트리거해서는 안 된다(표시용 호출이 네트워크를 타면 실패가 파스를 깬다). 근거를 대조할 상대가 저장돼 있지 않은 경우(미지 테마)의 VALID는 '반증 없음'이며 `basis_verified=false`로 구분한다. ④ **타입 분리**: 두 축을 같은 이름으로 섞지 않는다 — 하나로 합치면 "값은 확정인데 지금 유니버스에서 못 쓴다"가 표현되지 않는다. `NodeStatus`(작업 실행 상태)와 `ArtifactStatus`(산출물 유효성)도 분리한다. ⑤ **파이프라인 불변조건**: 파생 상태 계산과 전략 전체 검증은 Planner 출력과 무관하게 매 턴 실행된다 — 계산하는 레인이 일부뿐이면 값이 비는 게 아니라 클라이언트가 직전 턴 사본을 계속 쓴다(실측: 칩 답변으로 값이 바뀌어도 상태 맵이 이전 턴 것으로 남았다). ⑥ **Patch 허용목록**: `add`/`replace`/`remove`만 허용하며 JSON Patch wire format을 유지한다(개명은 수정 RAG 코퍼스·프롬프트·LLM 레인 재검증을 요구하므로 별도 마이그레이션). `MARK_NOT_APPLICABLE`·`MARK_INVALID`·`MARK_CONFLICT`·`REVALIDATE`는 **존재하지 않는 것이 계약**이며 허용목록과 적용기 거부로 코드에 남긴다 — NOT_APPLICABLE·INVALID·CONFLICTED 판정은 LLM이 생성하지 않고 결정론 코드가 계산한다. ⑦ **비권위 메타데이터**: `source`·`updated_at`·`confidence`는 저장하되 상태 판정·진행률·사용자 노출·분기 조건에 사용하지 않으며, 권위 있는 provenance 채널과 섞지 않는다(섞으면 언젠가 판정에 새어 든다). `confidence`는 필드별 producer가 없으므로 '이 필드를 마지막으로 바꾼 해석의 확신도'로만 해석한다. ⑧ **`INFERRED`는 producer 없음** — enum·스키마에만 유지하고 새 추론 로직을 추가하지 않는다. 회귀: `backend/tests/test_field_state.py`, `backend/tests/test_strategy_slots.py`, `app/analytics/new/builderProgressPresentation.test.ts`.

**FR-SA-012** [검색 목적 구조화 — 관계 근거 검증 상태 노출, 2026-07-31, 부분 구현] 외부 검색·Knowledge Graph 조회 결과를 State에 반영할 때, 검증 수준이 다른 근거를 하나로 뭉개지 않는다. 유일한 실제 검색 경로(`engine/term_grounding.py`)를 대조한 결과 요구되는 검증 단계 대부분(결과를 바로 CONFIRMED로 쓰지 않음 — `normalize_sector` 닫힌 목록 게이트, 관계 근거 교차지지 2건 이상만 `verified`·미만은 그래프 진입 자체를 차단, 산업 분야 여부 게이트로 사실과 테마성 추정 구분, TTL 기반 재검색·시점 편향 notice)는 **이미 구현돼 있었다.** 이번 작업이 채운 것은 하나: 회사별 관계 근거(`relation_type`·`direct`·`verified`·`source_count`)가 테마 유니버스 적용 시 `target_symbols`로 평탄화되며 **통째로 버려지고 있었다** — "직접 사업 관계로 교차검증됨"과 "테마 성격의 간접 연관·근거 미검증"의 구분이 사용자에게는 균질한 한 문장으로만 보였다. `_relation_evidence_disclosure`(`engine/nl_parser.py`)가 새 판정 없이 기존 계산 결과만 읽어 두 그룹의 개수를 안내 문구에 노출한다 — 관계 원장이 없는 종목(카탈로그 공식 분류·시드 큐레이션)은 다른 경로로 신뢰가 이미 확립돼 있어 disclosure를 붙이지 않으며(원장 미가입=미검증 오판 금지), 전부 직접·교차검증이면 구분해 얻을 정보가 없으므로 문구를 늘리지 않는다. **의도적으로 하지 않은 것**: 고정 검색 쿼리 템플릿(FR-STR-069 실측 튜닝값)을 LLM 생성으로 바꾸지 않았다 — 지연 증가와 회귀 위험 대비 이득이 없다(사용자 결정 2026-07-31, 범위를 검증 상태 노출로 한정). `search_goal`/`queries`/`required_evidence` 구조의 명시적 타입화와 ETF 후보 검색 같은 신규 검색 유형은 격차로 남는다. 회귀: `backend/tests/test_theme_universe_autoapply.py`.

**FR-SA-013** [종목 선정 범위 — 지정과 후보군의 구분, 2026-07-31] 지정 종목 목록에는 성격이 다른 두 가지가 같은 모양으로 저장된다 — ① 사용자가 직접 지목한 종목 ② 테마·개념 조회가 채운 관련 상장사. 이를 구분하지 않고 "지정 종목이 있으면 선정 없음"으로 처리하면 **후보군을 지정으로 오인해 사용자가 말한 선정 기준이 조용히 사라진다**(실측: "이차전지 관련주 중 최근 60일 수익률 상위 10종목" → 랭킹 비활성·보유 수 36으로 36종목 전부 매수. 사용자가 말한 랭킹과 종목 수가 동시에 증발). ① **판정은 저장하지 않고 계산한다**(FR-SA-011 ② 파생 상태와 같은 계약) — 값에서 온전히 유도되며, 저장하면 테마 교체 시 함께 갱신해야 하는 두 번째 진실이 생긴다. ② **범위 3종**: 지정 종목 없음=`UNIVERSE`(유니버스 전체가 선정 대상), 테마 유래이면서 선정 기준(랭킹)이 있으면 `CANDIDATE_POOL`(그중에서 선정 — 랭킹·보유 수 유지), 그 외 `EXPLICIT`(전부 매수·선정 없음). ③ **테마 유래여도 선정 기준이 없으면 `EXPLICIT`이다** — 무엇을 기준으로 자를지 아무도 말하지 않았으므로 임의로 상위 N곳만 남기지 않는다(테마 유니버스 절단 금지 결정 유지). 구분의 근거는 종목의 출처 기록(`theme_universe`)이며 새로 판정하지 않는다. ④ **표시가 실행과 일치해야 한다** — 배지가 "지정 N개 균등 투자"라고 하는데 엔진은 랭킹으로 M개만 사면 화면이 거짓말을 한다. 프론트의 범위 판정은 백엔드 정본의 미러이며, 규칙 변경 시 양쪽을 함께 고친다. ⑤ **`goal`(스펙 § 6 잔여)은 구현하지 않는다** — 사용자 원문(`description`)과 빌더의 전략 유형이 이미 그 자리를 차지하고 있고 구조화된 목표를 읽을 소비자가 없다. 유일한 소비자 후보였던 질문 우선순위 동적화는 하지 않기로 결정됐다. 회귀: `backend/tests/test_selection_scope.py`, `lib/strategy-summary.selection-scope.test.ts`.

**FR-SA-014** [변경 영향 범위 — 무효화·재유효화 전이 관측, 2026-07-31] 값이 달라진 필드 목록(FR-SA-008 `changed_fields`)만으로는 "이번 변경으로 무엇이 쓸 수 없게 됐나"를 답할 수 없다 — 유니버스를 ETF로 바꾸면 값이 바뀐 것은 유니버스 하나지만 영향은 기존 재무 조건까지 번진다. 그리고 파생 상태는 저장하지 않으므로(FR-SA-011 ②) 현재 값만으로는 **"원래부터 적용 불가였던 것"과 "방금 적용 불가가 된 것"이 구분되지 않는다.** ① **전이는 직전 턴 계산 결과와의 대조로만 관측된다** — 입력은 직전 파생 상태의 무상태 에코이며(FR-STR-019k·pending_ask와 같은 계약), 상태를 저장하는 것이 아니라 저장하지 않는 계산값 두 벌을 비교한다. ② **산출**: 값이 달라진 필드, 쓸 수 있던 칸이 쓸 수 없게 된 슬롯(APPLICABLE→NOT_APPLICABLE·INVALID·CONFLICTED), 쓸 수 없던 칸이 다시 쓸 수 있게 된 슬롯. **재유효화를 함께 내는 이유는 되돌림이 일어났다는 증거가 여기에만 남기 때문이다** — 파생 상태를 저장하지 않기로 한 대가로 "되돌려서 다시 유효해졌다"는 사실이 어디에도 기록되지 않는데, 두 계산 결과의 차이가 그것을 복원한다. ③ **재검증 목록은 만들지 않는다** — 파이프라인이 매 턴 전략 전체를 재검증하므로(FR-SA-011 ⑤) 그 목록은 항상 모든 필드라 정보를 주지 않는다. ④ **사용자 문구를 새로 만들지 않는다** — 적용 불가 안내는 capability validator가 이미 담당하며, 중복 안내는 같은 말을 두 번 하는 것이다. 이 산출물은 내부 추적 기록이며 사용자가 요청하지 않는 한 노출하지 않는다. ⑤ **나머지 내부 출력 블록**(해석·상태 패치·검증·DAG 변경·다음 액션·응답 계획)은 이미 각각의 자리에 구현돼 있으므로 한 구조로 묶는 리팩터는 수행하지 않는다 — 동작 이득이 없다. 회귀: `backend/tests/test_impact.py`.

**FR-SA-015** [부가 발화는 열려 있는 되묻기를 삼키지 않는다, 2026-07-31] 전략을 만드는 중 답을 기다리는 되묻기가 있는 상태에서 들어온 **부가 발화**(인사·역할 밖·미제공 기능·맞춤 조언·실계좌 매매 안내 라벨과 용어·지식 질문)는 정해진 안내로 답한 뒤 **그 질문을 선택지와 함께 그대로 다시 물어야 한다**. 설계 스펙 § 21(부가 질문은 워크플로를 유지한다)은 FR-SA-007에서 "워크플로를 PAUSE하지 않는다"로만 구현됐는데, 화면에서는 되묻기 블록이 **마지막 assistant 메시지에만** 렌더되므로 부가 발화 한 마디로 질문과 선택지가 통째로 사라졌다(실측: 리밸런싱 되묻기 중 "안녕" → 인사 응답만 남고 질문·칩 소실, 사용자 신고 2026-07-31). ① **판정을 새로 하지 않는다** — 분류 LLM 라벨로 이미 갈린 분기(`decideConversationTurn`)에 `preservesOpenQuestion` 표시만 붙이며 원문을 다시 읽지 않는다(대원칙 1). ② **자기 질문을 던지는 턴에는 붙이지 않는다** — 익절 값 되묻기·보유 기간 질문 같은 `respond` 턴에 붙이면 질문이 두 개 겹친다. ③ **다시 세우는 것은 화면 상태뿐이다** — 되묻기 스냅샷(질문·선택지·그때의 요약 카드·되돌아가기 상태)을 그대로 복원하므로 전략 파싱을 다시 돌리지 않고, 칩 클릭의 결정론 귀속(`clarificationSuggestions` 일치)과 `pending_ask` 에코도 유지된다. 안내문과 되묻기가 한 메시지에 함께 오므로 요약 카드는 한 번만 그린다. ④ **스냅샷은 되묻기를 그린 턴이 기록하고 질문 없는 턴이 지운다** — 답을 받은 뒤에도 남으면 이미 끝난 질문을 다시 묻는다. 회귀: `app/analytics/new/page.side-turn-keeps-clarification.test.tsx`.

**FR-SA-016** [후속 질문 턴 — 다음 할 일은 진행 골격 순서가 정한다, 2026-07-31] "어떻게 해야 할까?" 같은 후속 질문(`answer_follow_up`)에는 **아직 정하지 않은 조건을 진행 골격 순서대로** 되묻는다. 질문·선택지·진행률은 **한 판정**(`getNextMissingBacktestCondition` — 되묻기 게이트·진행률 패널과 같은 유일한 술어 `isSlotFilled`)에서 나와야 한다. ① **출처가 갈리면 반드시 어긋난다** — 이 요구사항은 두 단계의 실측 결함에서 나왔다: (a) 검증 agent 응답만 '전략 검증' 말풍선으로 띄워 진행률도 선택지도 없었고(사용자는 다음에 무엇을 어떤 값으로 정할지 화면에서 알 수 없다), (b) 그 문구를 되묻기 질문 자리에 넣자 **질문("익절 조건을 입력해 주세요")과 선택지(리밸런싱 칩)가 서로 다른 항목**이 됐다. ② **검증 agent 문구를 질문으로 쓰지 않는다** — 검증 agent는 미완성 전략이면 어떤 후속 질문에도 자기 순서의 "X 조건을 입력해 주세요"만 돌려주므로 진행 순서와 어긋날 수 있고, 그것을 질문으로 승격하면 상태와 무관하게 매번 같은 항목만 묻게 된다. ③ **정할 것이 남아 있으면 검증 agent를 호출하지 않는다** — 답이 이미 상태에 있으므로 LLM 왕복이 없다(응답 지연 감소). 정할 것이 없으면(전략 완성) 그때는 검증 agent의 진단이 답이므로 기존 '전략 검증' 말풍선 경로 그대로다. ④ **되묻기는 열린 질문으로 기록된다**(FR-SA-015 ④) — 이후 부가 발화가 들어와도 살아남는다. 칩 클릭은 기존 결정론 귀속 경로(`clarificationSuggestions` 일치 → `applyDeterministicConditionChoice`)를 그대로 타므로 백엔드 왕복이 늘지 않는다. 회귀: `app/analytics/new/page.followup-validation-clarification.test.tsx`.

**FR-SA-017** [턴 중재 구조 — 상태 평가와 액션 선택의 분리, 2026-07-31] 대화 턴의 처리 방식은 "매 턴 State를 재평가하고 지금 실행 가능한 Action을 고른다"는 구조여야 한다. 상태 재평가 축은 이미 그랬으나(FR-SA-011 ② 파생 상태 매 턴 계산) **액션 선택 축은 그렇지 않았다** — 중재자(`decideConversationTurn`)가 고정 순서의 원문 술어 if 체인이었고, 슬롯 상태를 입력으로 **받지조차 않았다**(`ConversationContext`에 `stage`·`hasCurrentStrategy`·`builderMode`·`pending*` 4종 플래그뿐, `getNextMissingBacktestCondition` 미참조). FR-SA-015·016의 세 사고가 모두 이 결손의 증상이다. ① **상태 주입** — `ConversationContext.slots`에 진행 골격 판정 결과(다음에 정할 조건)를 싣는다. 판정 자체는 정본 술어 하나(`isSlotFilled`)로만 하고 중재자는 결과만 본다(중재자를 순수 함수로 유지 — 같은 판정이 두 곳에서 갈라지지 않게). ② **액션 계층 명시** — L0 워크플로 제어(라벨) / L1 진행 중인 하위 대화(상태) / L2 발화가 지목한 규칙(원문) / L3 라벨 분기 / L4 **상태 기본 액션**(`ask_next_condition`) / L5 파싱 폴백. **L2가 L4를 이긴다**(사용자 결정) — 사용자가 특정 항목을 지목했으면("손절 바꿔줘") 진행 순서가 그것을 덮어써서는 안 된다. **L5를 L4가 가로채서도 안 된다** — 새 조건을 말한 발화까지 되묻기로 흡수하면 방금 말한 조건이 반영되지 않는다("새 정보인가"의 판정자는 파서 LLM이다). ③ **응답 조립기 일원화**(`turnMessage.ts`) — assistant 메시지를 만드는 자리를 하나로 모으고 규칙을 계약으로 고정한다: 전략이 있으면 카드를 항상 동반, 되묻기 선택지는 결정론 귀속 채널(`clarificationSuggestions`)로만 발행, 부가 발화는 열린 되묻기를 복원하되 스스로 질문을 던지는 턴에는 복원하지 않는다. 칩 채널 둘(`clarificationSuggestions`/`infoSuggestions`)은 클릭 의미가 다르므로(결정론 귀속 vs 새 발화 재전송) 합치지 않는다. ④ **핸들러 단일화** — 액션당 구현은 하나다. 자리표시자 유무(append vs patch)가 분류 전/후 핸들러를 두 벌로 갈라 한쪽만 고치는 드리프트를 낳았으므로(FR-SA-015 수정도 분류 후 사본만 고쳤다) `emitAssistant`가 그 차이를 흡수한다. 네트워크를 타는 액션에만 로딩 자리표시자를 띄운다. ⑤ **L2의 원문 정규식은 이관하지 못한 부채로 남는다** — 계층으로 드러내 이관 대상을 코드에서 보이게 하되, 새 규칙을 L2에 추가하지 않는다(nl_interpretation_contract § 11). 회귀: `app/analytics/new/conversationDecision.test.ts`(계층 5건), `app/analytics/new/turnMessage.test.ts`(조립 계약 7건).

**FR-SA-018** [되묻기 판정 부분 이관 — clarify_target, 2026-07-31] "바꿀 대상은 말했는데 값이 없다"는 판정은 의미 해석이므로 LLM이 해야 한다(대원칙 1). 이관 전에는 프론트 정규식 3종이 원문을 읽어 판정했다(`getModificationClarification` 15패턴·`buildTakeProfitPercentagePrompt`·`buildFundamentalFactorPrompt` 16패턴). ① **축 하나를 추가한다** — `workflow_effect`(FR-SA-007) 선례와 동일하게 기존 분류 호출의 출력 형태에 `clarify_target` 키를 더한다(LLM 호출 증가 0회, `max_tokens` 180→220). ② **LLM은 닫힌 목록에서 대상만 고른다**(`intent/clarify_targets.py`: 설정 필드 9 + 영역 7 + 재무 지표 키 26 — 지표 키의 정본은 `data/fundamental-factors.json` 하나이며 프롬프트 목록도 거기서 생성한다). 목록 밖 표기·미출력은 None으로 떨어진다. ③ **성립 검증은 결정론이 한다** — 규제 게이트 라벨 9종에서는 None(정형 안내가 되묻기로 삼켜지지 않게), 진행 중인 전략이 없으면 None. 강등은 거부가 아니라 기존 흐름 유지다. ④ **문구는 LLM이 짓지 않는다** — 라벨을 키로 기존 표에서 문구·선택지를 고른다(`clarificationForTarget`). 이관으로 사용자에게 보이는 표현이 바뀌지 않는 것이 요구사항이다. ⑤ **프론트는 재심하지 않는다** — 백엔드 검증을 통과한 라벨을 그대로 쓰고, 정규식이 LLM 판정을 뒤집는 안전망을 두지 않는다. ⑥ **순서 제약** — 되묻기 판정은 분류 이후에만 가능하므로 후속 질문 분기(FR-SA-016)도 분류 뒤로 내려야 한다. 그러지 않으면 지목과 후속 질문 표현이 겹치는 발화("영업이익률을 추가해 볼까?")를 진행 순서가 가로챈다. ⑦ **부분 이관이다**(사용자 결정) — 기간 하한·실행 확인·연구 지표·기간 비교는 즉답 경로로 남긴다. 이관된 3종은 분류 왕복 1회가 새로 생기며, 그 지연을 감수한 선택이다. 회귀: `backend/tests/test_intent_interpreter.py`, `app/analytics/new/conversationDecision.test.ts`, `app/analytics/new/page.scroll.test.tsx`.

**FR-SA-019** [전략 유지 턴의 안내 — 사실 한 문장 + 상태가 답하는 다음 행동, 2026-07-31] 요청을 반영하지 못해 전략을 그대로 두는 턴(미지원 개념·해석 실패)은 같은 전략을 다시 보여주는 것으로 끝나서는 안 된다. 사용자는 "왜 그대로인지"와 "그래서 지금 무엇을 하면 되는지" 둘 다 알아야 한다. ① **안내는 사실 한 문장까지가 몫이다** — 무엇을 왜 넣지 못했는지만 말하고("'수급' 조건은 지원하지 않아 전략에 넣지 못했어요. 나머지 조건은 그대로입니다"), 다음 행동은 진행 상태가 답한다(다음에 정할 조건 되묻기 — FR-SA-016, 또는 완성 상태의 실행 가능 안내). 안내 문구에 다음 행동을 따로 써넣지 않는다 — 같은 말을 두 곳에서 만들면 갈라진다. ② **안내와 되묻기는 같은 화면에 함께 있어야 한다** — 안내 카드가 요약 블록 안에만 있어 되묻기가 뜨는 턴에서는 **통째로 렌더되지 않았다**(실측 결함: 미반영 사유가 조용히 사라짐). 안내를 요약·되묻기와 독립적으로 렌더한다. ③ **발화 전체를 조건 이름으로 인용하지 않는다** — 인터프리터가 `unsupported_features`에 발화를 통째로 담는 오라벨이 실재하며("어떻게 해야 할까?"), 그대로 인용하면 뜻이 통하지 않는 안내가 나간다. LLM 출력과 입력 문자열의 **대조**로 감지해(원문 의미 해석이 아니다, 계약 § 3-1) 조건 이름 없이 사실만 말한다. ④ **대안 지표를 조용히 제시하지 않는다** — 미지원 개념을 비슷한 지표로 대체하는 것은 사용자가 말하지 않은 조건을 만드는 일이다(대원칙). 회귀: `backend/tests/test_strategy_conversation.py`, `app/analytics/new/page.notice-with-clarification.test.tsx`.

**FR-SA-020** [유지/변경 선택 — 지금 설정된 항목의 체크박스 목록, 2026-07-31] 무엇을 바꿀지 말하지 않은 수정 요청(`clarify_target=condition`)에는 영역 칩 5개 대신 **지금 설정된 항목을 값과 함께** 보여주고 그대로 둘 것을 고르게 한다. 사용자는 화면의 값을 보며 판단하고, 고르지 않은 항목만 다시 답한다. ① **목록은 상태에서 만든다**(`strategyItems.listStrategyItems`) — 인터프리터가 낸 확인 질문 문장("ROE 10% 조건을 유지하시겠습니까?")을 파싱해 만들면 LLM 자유 텍스트를 정규식으로 해석하는 구조가 되고(대원칙 1 위반) 각 줄의 필드 결속도 LLM 판단에 의존한다. 값이 곧 항목이면 결속이 공짜로 성립하고, 라벨은 요약 카드의 포매터를 재사용해 같은 값이 화면 두 곳에서 다르게 보이지 않는다. ② **기본은 전부 체크(현 상태 유지)** — 아무것도 건드리지 않고 제출하면 전략이 그대로 남는다. 파괴적 방향이 기본값이 되어서는 안 된다. ③ **비우는 방식은 슬롯 판정이 정한다** — 값의 존재가 곧 완료인 항목(진입·청산 신호·손절·익절·보유기간)은 **값을 지우고**, 기본값이 물질화되는 설정(유니버스·종목 수·리밸런싱·기간·초기 자본)은 값이 아니라 **provenance(`explicit_fields`)를 지운다**(값을 0/""로 만들면 백엔드 스키마와 싸우게 되고, 이 슬롯들의 완료 조건은 애초에 provenance다). 어느 쪽이든 **진행률 언체크가 같은 술어(`isSlotFilled`)로 자동 성립**한다 — '값은 있는데 미확정'이라는 축을 새로 만들어 진행률이 그것을 따로 읽게 하면 같은 판정이 두 곳으로 갈라진다(FR-STR-019q가 피하려던 구조). ④ **재질문은 대기열이 순서를 잡는다** — 비운 항목의 슬롯을 진행 골격 순서로 모아 하나씩 묻고, **물어보는 순간 대기열에서 뺀다**(답하지 않아도 그 슬롯은 비어 있으므로 상태 기본 액션(FR-SA-016)이 나중에 다시 데려간다 — 질문이 사라지지 않는다). 슬롯 단위로 중복을 제거하므로 같은 슬롯의 항목 둘을 비워도 한 번만 묻는다. ⑤ **백엔드 왕복이 없다** — 사용자가 화면에 보이는 값을 직접 고른 것이라 재해석할 원문이 없다. ⑥ **보여줄 항목이 없으면 기존 영역 칩으로 되돌아간다**(빈 목록에 '선택 완료'만 띄우지 않는다). 회귀: `app/analytics/new/page.keep-items.test.tsx`.

**FR-SA-021** [열린 질문은 분류 맥락에 포함된다, 2026-07-31] 시스템이 방금 던진 질문에 대한 답("아니야", "응", "그건 아니고")은 인사·잡담으로 분류되어서는 안 된다. 답인지 아닌지는 의미 판정이므로 LLM이 하지만, **판정 재료가 전달되지 않으면 LLM도 알 수 없다.** 실측 결함 2건이 겹쳐 "아니야"가 GREETING으로 분류되고 인사 응답이 나갔다. ① **되묻기가 분류 맥락에서 누락됐다** — `selectClassifierHistory`가 assistant 메시지에서 `infoText ?? coachText ?? clarification` 중 **앞의 하나만** 골랐는데, FR-SA-015 이후 한 메시지가 안내문과 되묻기를 **함께** 싣게 되면서 우리가 방금 던진 질문이 맥락에서 사라졌다(기능 추가가 다른 기능의 입력을 조용히 없앤 상호작용). 있는 것을 모두 싣는다. ② **"답을 기다리는 질문"이라는 사실 자체가 전달되지 않았다** — 히스토리에 섞여 들어가는 것과 "이 발화는 이 질문에 대한 답일 수 있다"고 명시하는 것은 다르다. `active_strategy`·`workflow_status`와 같은 무상태 에코로 `pending_question`을 넘기고(프론트 `openClarificationRef`가 출처), 프롬프트 규칙 4-1이 "그 답으로 보이는 짧은 발화는 GREETING·OFF_TOPIC이 아니다"를 명시한다. ③ **프론트가 재판정하지 않는다** — "짧은 부정 답변이면 인사가 아니다" 같은 결정론 보정을 넣지 않는다. 그것은 원문 의미 판정이며 정규식이 LLM을 재심하는 구조다(대원칙 1). 재료만 주고 판정은 LLM에 맡긴다. ④ **잔여**: 부정 답변("아니야")의 **후속 처리**는 별도 축이다 — 지금은 전략 파싱 레인으로 흘러 "해석하지 못했어요" 안내와 함께 열린 질문이 유지된다(인사 응답보다는 정직하지만 최선은 아니다). 긍정 확정(`CONFIRM_RECOMMENDATION`, FR-SA-010)의 대칭인 거절 축은 도입하지 않았다. 회귀: `backend/tests/test_intent_interpreter.py`, `app/analytics/new/chatHistory.test.ts`, `app/analytics/new/page.side-turn-keeps-clarification.test.tsx`.

**FR-SA-022** [되묻기 답변은 파스 레인이 해석한다 — 질문 문맥의 전달, 2026-07-31] 시스템이 던진 질문의 답은 되묻기 레인이 다시 가로채서는 안 되고, 어느 필드의 답인지는 **그 질문**이 정한다. 실측 결함: 초기자금 되묻기에 '3억원'이라고 답하면 같은 질문이 무한 반복됐다. ① **`clarify_target`은 '값이 함께 왔는가'를 판정하지 않는다** — 값이 실린 발화에도 대상 라벨이 그대로 나온다(실측 4/4). 프롬프트 규칙 10('값이 함께 있으면 null')은 산문 규칙이라 9B가 지키지 않고, `_resolve_clarify_target`의 결정론 검증은 규제 라벨·활성 전략만 본다. FR-SA-018 이관 전 정규식 경로가 갖고 있던 `explicitPattern` 게이트가 이관에서 사라진 자리다 — **그 불변식의 테스트는 이제 호출되지 않는 함수를 검증하고 있어 초록으로 남았다**(레인을 옮길 때 테스트도 함께 옮기지 않으면 가드가 죽은 줄 모른다). ② **차단은 상태로 한다**(사용자 결정) — 답을 기다리는 되묻기가 열려 있으면(`hasOpenClarification`) L2'는 개입하지 않고 L5 파싱으로 흘린다. '값이 있는가'를 프론트가 원문에서 다시 판정하지 않는다(대원칙 1 — 정규식이 LLM을 재심하는 구조 금지). ③ **분류는 유지한다**(사용자 결정) — 되묻기 답변 턴에도 규제 게이트(맞춤 조언·실계좌·미제공 기능·OFF_TOPIC)가 걸려야 하므로 분류 왕복을 건너뛰지 않는다. 차단 대상은 되묻기 레인 하나다. ④ **질문을 파스 레인에 에코한다** — `pending_ask`·`previous_coach_text`와 같은 무상태 컨텍스트 에코로 `pending_question`을 넘기고(출처=`openClarificationRef`), 인터프리터 사용자 프롬프트가 '답을 기다리는 질문' 블록으로 싣는다. 귀속은 LLM이 한다 — 실측: 같은 답 '10%'가 손절 질문에서는 `/risk_management/stop_loss`, 익절 질문에서는 `/risk_management/take_profit`으로 갈린다(질문이 없으면 손절로 고정). 캐시 키에도 포함한다(같은 답이라도 질문이 다르면 귀속이 다르다). ⑤ **열린 되묻기의 기록처는 하나다** — `respond` 액션으로 나가는 되묻기(L2')도 `openClarificationRef`에 남긴다(`opensClarification` 표시). 기록이 없으면 다음 턴이 그 답을 새 발화로 재분류한다. ⑥ **수치 반영 대조에서 패치 인용을 제외한다** — 패치의 `source_text`는 사용자 원문 조각이라 값이 틀려도 입력의 숫자를 포함한다. 실측: '3억원' 답변에 `value=30000000`(10배 축소)+`source_text="3억원"`이 나왔고 인용의 3이 앵커 '3억'의 후보 3과 맞아 검사가 침묵, 3천만원이 조용히 확정됐다(조건 배열에서는 이미 제외하던 것을 패치에는 적용하지 않은 누락). 값 자체의 교정은 프롬프트 규칙 11-2(금액 단위 환산표)로 LLM 레인에서 한다 — 결정론 후처리 보정은 금지다(§ 3-1). ⑦ **대가**: 되묻기 중 값 없는 **다른** 필드 요청은 되묻기 없이 무변경 파스 후 다음 조건 질문으로 흐른다(사용자 결정 — 항상 차단). 회귀: `app/analytics/new/page.clarify-answer.test.tsx`, `app/analytics/new/conversationDecision.test.ts`, `backend/tests/test_strategy_conversation.py`, `backend/tests/test_recall_validator.py`, `backend/tests/test_nl_cache.py`.

**FR-SA-023** [자유 입력 답변의 값 귀속 — QA 86케이스 기반 교정, 2026-07-31] 되묻기의 '직접 입력' 답변을 슬롯 8종 × 표현 43종 × 질문 2계열(진행 골격/수정)로 실측한 결과 16건이 실패했고 원인이 넷으로 갈렸다. 값이 **다른 슬롯으로 새는 사고는 0건**이었다(FR-SA-022의 질문 에코가 귀속을 담당). ① **조건 객체 패치의 JSON 붕괴** — 패치 값이 3단 중첩(패치 → 조건 → parameters)이면 9B가 조건 객체의 닫는 중괄호를 빠뜨린다. 1회 복구 요청에도 같은 출력이라(2/2) 청산 조건 답변이 전량 해석 실패였다. **닫는 괄호 삽입만으로 설명되는 붕괴**는 형식 정규화로 복구하되(`_close_unbalanced_containers` — `_repair_operator_token_drift`와 같은 자리), 절단(닫는 괄호 전무)은 복구하지 않는다 — 잘린 조건을 완성하면 사용자가 말하지 않은 전략이 된다. ② **인용문의 자리가 둘** — `source_text`는 패치 자신(`PatchOp`)과 조건 객체(`StrategyCondition`) 양쪽에 있는 필드다. 환각 게이트가 패치 쪽만 읽어, 조건 안에 정확히 인용한 패치가 '근거 없음'으로 거부됐다(수치가 없는 발화라 수치 대조로도 구제되지 않는다). 두 자리를 모두 본다 — 지어낸 인용은 여전히 거부된다. ③ **없는 인덱스를 겨냥한 필드 패치** — 조건 배열이 비었는데 `replace /exit_conditions/0/factor`를 낸다. 같은 인덱스를 겨냥한 형제 패치를 조건 추가 하나로 합친다(`_promote_patches_on_absent_condition`). **LLM이 이미 낸 필드만** 모으며 factor가 없으면 승격하지 않는다 — 불완전한 조건을 만들어 검증을 통과시키는 것이 조용한 오해석의 시작이다. ④ **버킷 밖 기간 표기** — period는 `1y/3y/5y/full` 넷뿐이라 '전체 기간'의 `"all"`, '10년'의 `"10y"`가 Literal에서 탈락해 패치가 통째로 폐기됐다. 뜻이 같은 표기(`all`·`전체`·`5년`)는 정본 값으로 정규화하고, **버킷이 아닌 연수·개월은 가장 가까운 버킷으로 올리지 않고 명시 날짜 창으로 바꾼다**(`nl_parser._extract_backtest_dates`와 같은 정본 정책 — 버킷으로 올리면 사용자가 말한 적 없는 창이 된다). ⑤ **미반영 수치 안내를 수정 레인에도 배선한다** — 초기 파스 레인에만 있어, 재요청 후에도 남은 값 오차가 조용히 확정됐다(실측: '60일 신고가'가 lookback 300, '최근 1년'이 5y 그대로). 값을 코드가 만들어 채우는 것은 § 3-1이 금지하므로 남는 선택지는 정직하게 알리는 것뿐이다. **[2026-08-01 폐지]** 이 안내는 두 레인 모두에서 걷어냈다 — 라벨이 맥락 없는 숫자 나열이 되고 이미 반영된 조건이 자주 걸려 정보값이 없다는 사용자 판단(FR-STR-019j ⑤). 아래 '결과'의 3건 중 2건이 이 안내로 드러나던 것이라, 그만큼은 이제 사용자에게 보이지 않는다. ⑥ **되묻기는 실패가 아니다** — '볼린저밴드 상단'에 기준 기간을, 'RSI 30 이하'에 RSI 기간을 묻는 것은 정상 동작이다(말하지 않은 값을 기본값으로 확정 금지). QA 판정도 PASS/FAIL과 별도로 센다. **결과**: 86케이스 70 PASS → **79 PASS · 4 되묻기 · 3 실패**. 남은 3건은 모델 샘플링 흔들림이며 2건은 ⑤의 미반영 안내로 사용자에게 드러난다. 하니스: `scripts/qa_free_input.py`. 회귀: `backend/tests/test_strategy_conversation.py`(브래킷 복구·인덱스 승격·인용 자리·기간 정규화).

**FR-SA-024** [되묻기 축의 값 판정 — 조건부 규칙 대신 값 추출, 2026-08-17] 값을 실은 수정 요청("손절을 -15%로 해줘")에는 값을 되묻지 않는다. FR-SA-022 ①이 진단한 결함(9B가 규칙 10 '값이 함께 있으면 null'을 지키지 않음)은 FR-SA-022 ②의 상태 차단으로는 **되묻기가 열려 있지 않은 첫 수정 발화**를 막지 못해 재발했다(실측 greedy 9B: 값 동반 발화 9종 전부 대상 출력). ① **출력 형태로 푼다** — 분류 LLM은 `clarify_target`을 직접 내지 않고 `modify_target`(바꾸려는 대상, 닫힌 목록)·`modify_value`(그 대상에 주려는 값의 원문 표기)·`modify_removes`(지우라는 요청인가)를 **각각 뽑는다**. 조건부로 비우라는 산문 규칙은 지켜지지 않았고, 값을 뽑게 하면 지켜진다(출력 형태가 규칙보다 강하다 — FR-STR-019p). ② **되묻기 승격은 결정론**(`clarify_targets.resolve_clarify_target`) — 대상이 목록 안이고 값 표기가 없고 삭제도 아닐 때만 `clarify_target`이 성립한다. 값 표기의 **내용**은 읽지 않는다(그 해석은 파스 레인 LLM 몫) — 표기 유무만 보는 형식 정규화다. `'없음'`은 null 표기로 보지 않는다('리밸런싱 없음으로'는 값이다). ③ **삭제 요청도 되묻지 않는다** — '손절 없애줘'에 손절 값을 묻던 것(FR-SA-018 이후 잔존)이 같은 축으로 닫힌다. ④ **프롬프트 문구 민감도** — 규칙 10 예시를 길게 늘였을 때 같은 greedy 9B가 경계 발화 2건('조건을 변경할 수 있어?'·'영업이익률을 추가해 볼까?')에서 흔들렸고 짧은 형태에서 `classify()` 실경로 25/25였다. 이 축의 프롬프트를 바꾸면 실모델 재측정이 요구사항이다. ⑤ **같은 카드로 묻는다** — 되묻기 레인(L2')의 질문은 `respond` 액션이라 `infoText`+`infoSuggestions`(맨 텍스트+칩)로 나가 08-16에 통일한 되묻기 카드와 달랐다. `buildTurnMessage`가 `opensClarification` 응답을 `clarification` 채널로 조립한다 — 같은 성격의 질문은 같은 카드다. 회귀: `backend/tests/test_intent_interpreter.py`, `app/analytics/new/turnMessage.test.ts`.

#### 3.6.x Agent 관찰성 (Observability)

**FR-OBS-001** [LangSmith Trace 관찰 계층 — 관찰만 하고 제어하지 않는다, 2026-07-31] 전략 대화 Agent(Planner → Action DAG → Tool → State → Responder)의 실행 과정을 LangSmith Trace로 추적·평가할 수 있어야 한다. **이 계층은 Agent를 제어하지 않는다** — 실행 경로·분기·되묻기 조건·폴백 판정·반환값·예외 전파 중 어느 것도 바꾸지 않는 것이 계약이며, 위반은 관찰성 기능의 실패로 본다.

① **기본 비활성** — `LANGSMITH_TRACING`이 참이 아니면 완전한 no-op이고 langsmith를 import조차 하지 않는다(오버헤드·외부 전송 0). 활성화하면 사용자 원문·전략 State·LLM 프롬프트 전문이 외부(LangSmith)로 전송되므로, prod 활성화는 별도 결정 사항이다. 롤백은 환경변수 삭제 하나로 끝나야 한다(코드 변경 불요).

② **계측은 기존 단일 통로에만 건다** — 루트 `_run_nl_parse`, Tool `tools/base.py::call`, LLM `_default_ollama_chat`(공유 `ChatFn` 계약), Planner `plan_strategy_dag`, Interpreter `interpret`. 각각 본체를 별도 함수로 분리하고 래퍼가 span만 연다. 계측을 실행 코드 전반에 흩으면 새 레인이 생길 때마다 빠뜨리고, 관찰이 실행 코드의 모양을 바꾸게 된다.

③ **관찰 실패가 실행 실패가 되어서는 안 된다** — langsmith 장애·직렬화 실패는 debug 로그로만 남기고 통과시킨다. 반대로 **감싼 코드의 예외는 삼키지 않는다**(기록 후 그대로 재전파) — 삼키면 폴백 판정이 뒤집힌다.

④ **Parent-Child 계층이 항상 유지되어야 한다** — Trace → Planner → (Action → Tool · State · LLM) → Responder. Action span과 Tool span은 분리한다(관찰 재사용 `call_cache` 히트를 '도구를 불렀다'와 구분하기 위해). **스레드 경계가 이 요구사항의 실패 지점이다**: 부모 추적은 contextvar 기반이라 스레드를 건너지 않으므로, shadow planner 2종과 SSE 후행 검증은 부모를 명시 전파해야 한다 — 하지 않으면 span이 조용히 고아 Trace가 되고 계층이 끊긴 것을 아무도 눈치채지 못한다.

⑤ **없는 값을 지어내지 않는다** — `NLParseRequest`는 무상태 에코 계약이라 `user_id`가 없고, 관찰 계층이 요청 스키마를 늘리는 것은 실행 경로 변경이므로 `user_id=None`으로 남긴다. 대화는 `session_id(턴 N) == strategy_id(턴 N-1)` 사슬로 잇는다(진짜 세션 키가 아니므로 한 세션 전체 필터는 불가 — 요청 계약에 세션 필드가 생기면 `observability/identity.py`만 바꾼다). Cost는 self-hosted(Ollama/Modal)라 단가가 없어 싣지 않는다. 토큰 수는 Ollama 응답의 `prompt_eval_count`/`eval_count`를 읽어 기록한다.

⑥ **실패 원인이 종류로 남아야 한다** — 예외로 끝나지 않는 실패(폴백 `None` 반환)도 `trace.error(kind, ...)`로 기록한다: `PlannerOutputParseError`·`DagContractError`·`ToolContractError`·`ToolError`·`OutputGuardRejected`·`NoProgress`·`TurnBudgetExhausted`.

⑦ **Evaluation은 결정론이다** — LLM judge를 쓰지 않는다(채점이 비결정적이면 회귀 테스트로 쓸 수 없다). 6축: DAG 구조 적합성, 불필요 Action 비율, State 변경의 선언 여부, Tool 선택 적절성, 응답 계약 준수, 턴 진전. **판정 근거가 없으면 점수를 내지 않는다**(`score=None`, 집계 제외) — 근거 없는 0점은 대시보드를 거짓으로 만든다.

⑧ **되묻기는 실패가 아니다** — Dataset에 정답 전략(reference output)을 두지 않는다. 말하지 않은 값을 기본값으로 확정하지 않는 것이 Agent의 계약이므로, 정답을 못 박으면 그 계약을 어기는 쪽이 통과한다. evaluator도 `SKIPPED`(채워진 슬롯 재질문 가드 동작)를 낭비로 세지 않고, 되묻기 종료를 만점으로 친다.

⑨ **자연어 해석 계약 준수** — 관찰 계층은 사용자 원문의 의미를 판정하지 않는다. evaluator의 검사 입력은 Agent가 만든 구조화 출력(DAG·노드 상태·생성된 질문 문자열)과 Dataset이 사람 손으로 붙인 라벨뿐이다. `backend/observability/`에 원문 패턴 매칭을 추가해서는 안 된다.

구현: `backend/observability/`, 상세 `docs/observability.md`. 회귀: `backend/tests/test_observability_tracing.py`(no-op·예외 전파·지표), `test_observability_hierarchy.py`(계층·스레드 경계·대조군), `test_observability_parse_root.py`(반환값 불변·Responder·식별자), `test_observability_evaluators.py`(6축·Dataset).

**FR-OBS-002** [로컬 Trace 레코더 — LangSmith 없이 같은 정보를 로컬에, 2026-08-02] FR-OBS-001의 span 파사드가 수집하는 것(계층·입출력·메타데이터·소요 시간·오류·성능 지표)과 동일한 정보를 외부 전송 없이 로컬에 남길 수 있어야 한다. 요청 하나가 끝날 때 ① 콘솔에 span 트리(`[AGENT-TRACE]`, 값은 raw JSON 한 줄이 아니라 `key = value` 컬럼 — FR과 무관한 로그 가독성 계약과 동일)와 ② `backend/logs/agent_traces/YYYY-MM-DD.jsonl`에 Trace 한 줄(전체 트리 구조 보존)을 남긴다.

① **기본 활성** — 외부 전송이 없으므로 LangSmith와 달리 opt-out이다(`AGENT_TRACE_LOCAL=0`으로 끔). 두 sink는 서로 독립이며 둘 다 꺼져 있을 때만 span이 완전한 no-op이다. ② **실행 계층 무변경** — 기록처 추가는 `observability/` 내부(파사드 `tracing.py` + 레코더 `local_trace.py`)에서 끝나야 하고, chokepoint 5곳의 호출부는 바뀌지 않는다. FR-OBS-001의 계약(예외 재전파·관찰 실패 무해·원문 패턴 매칭 금지)을 그대로 상속한다. ③ **방출 후 소급 수정 금지** — SSE 후행 검증처럼 루트 방출 뒤 도착하는 span은 같은 `trace_id`의 별도 레코드(`late_attach`)로 남긴다. 방출된 트리를 소급 수정하면 파일과 콘솔이 어긋난다. ④ 테스트 스위트는 기본 꺼짐이다(`tests/conftest.py`) — span마다 콘솔·파일을 쏟으면 테스트 출력이 관찰이 아니라 소음이 된다.

구현: `backend/observability/local_trace.py`. 회귀: `backend/tests/test_local_trace.py`(트리 기록·지표·오류·no-op·late_attach·컬럼 렌더링).

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

**FR-ADM-001** 관리자 콘솔은 `/console` 단일 URL 하나만 존재해야 하며(하위 페이지 없음), 내부 탭(Overview/Architecture/Users/Backtests/Virtual Accounts/Strategies/Plans/Knowledge/Agents/Q&A Logs/Audit Logs) 전환으로 모든 기능을 제공해야 한다. Agents 탭(2026-07-29)은 플랫폼 AI 파이프라인 9종의 설계 구조를 agent별 서브탭·흐름도(노드 유형 색상 범례: 입력/AI 판단/자동 규칙/지식·데이터/안전장치/사용자 확인/결과물)로 시각화한다 — 내부 변수명이 아닌 운영자 친화 명칭으로 표기하는 정적 스냅샷(`components/admin/AgentsTab.tsx`)이며, 파이프라인 구조 변경 시 함께 갱신한다. Architecture 탭(2026-08-14)은 서비스 전체의 계층 구조·설계를 8개 서브탭(구조 그래프/전체 조감도/대화→백테스트 여정/백테스트 엔진/데이터 파이프라인/가상매매/배포 구조/규제 안전 계층)으로 시각화하며 — 구조 그래프(기본 서브탭)는 핵심 구성 요소 16개 노드와 호출·데이터 흐름 18개 엣지를 SVG 다이어그램으로 그린다 —, 상세 데이터가 있는 카드는 클릭 시 상세 패널(요약·핵심 설계·운영 메모/사고 이력·구현 위치, ESC/배경 클릭으로 닫힘)을 연다 — 같은 원칙의 정적 스냅샷(`components/admin/ArchitectureTab.tsx`, 정본 문서=`docs/software_architecture.md`·`docs/deployment.md`)이며, 시스템 계층·경계·데이터 흐름이 바뀌면 함께 갱신한다.

**FR-ADM-002** 모든 관리자 페이지·API는 서버에서 `requireAdmin()`(JWT + `User.role='ADMIN'` + `status='ACTIVE'`)으로 권한을 검증해야 한다. 검증 실패 시 404를 반환해 콘솔의 존재 자체를 숨긴다. UI 숨김만으로는 보안으로 인정하지 않는다.

**FR-ADM-003** ADMIN 권한은 관리자 화면/API로 부여·변경할 수 없어야 하며, 초기에는 데이터베이스에서만 변경한다.

**FR-ADM-004** 관리자의 모든 변경 작업은 `AdminAuditLog`에 관리자·시간·대상·작업 종류·변경 전/후 값·IP를 기록해야 하며, 감사 로그 삭제 기능은 제공하지 않는다.

**FR-ADM-005** 관리자는 사용자 관리(플랜 변경·정지·활성화·삭제(soft)·백테스트 사용량 조정), 가상계좌 관리(일시 중지·재개·초기화·삭제), 전략 관리(비활성화·삭제(soft)), 플랜 한도 오버라이드(`PlanConfig` — 월 백테스트/전략 수/가상계좌 수, null=기본값 복원, 전략 -1=무제한)를 수행할 수 있어야 한다. 자기 자신에 대한 정지·삭제는 차단된다.

**FR-ADM-006** 관리자 화면·API 응답에는 비밀번호, OAuth/Access/Refresh Token, Secret Key, API Key 등 민감 정보를 포함하지 않아야 한다.

**FR-ADM-007** 전략연구소 대화는 **질문 하나와 그 턴의 답변**을 한 건으로 `ChatQaLog`에 기록해야 한다(2026-08-15). 기록 항목은 사용자(비로그인은 null)·대화 세션 id·턴 번호·질문 원문·화면에 뜬 답변 텍스트·답변 종류(error/clarification/strategy/coach/info/text)·칩 선택 여부·응답 소요 시간이다. 기록 시점은 그 턴의 메시지 갱신이 멎은 때이며(스트리밍 완료 판정), 기록 전송 실패는 대화를 중단시키지 않는다. 관리자는 Q&A Logs 탭에서 내용 검색·사용자·답변 종류·대화 단위로 조회하며, 감사 로그와 같이 삭제 API는 제공하지 않는다. 이 기록은 답변 품질 점검용이며 사용자에게 노출하지 않는다. 보관 기간 제한은 두지 않는다(관측 계층 Trace 원문의 3일 보관 정책과 별개 채널 — 실측 기준 질문+답변 한 건 약 2KB).

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
| NFR-REL-010 | [요청 취소 전파, 2026-08-18] 전략연구소에서 사용자가 분석 중 '대화 종료'를 누르면 진행 중인 서버 작업도 멈춰야 한다. ① 프론트: 대화 단위 `AbortController` 하나가 그 대화의 모든 요청(분류·파싱 SSE·빌더 스텝·검증·백테스트 스트림)을 끊고, 끊긴 턴은 뒤처리(오류 버블·빌더 상태 복원)를 하지 않는다(`isChatAbort`). ② Next 프록시: `fetchBackend`가 호출자 signal(`req.signal` — 클라이언트 연결 종료 시 abort)을 타임아웃과 결합해 백엔드 연결을 함께 끊는다(예전엔 타임아웃 signal이 덮어써 백엔드 연결이 예산까지 살아 있었다). ③ 백엔드: SSE 요청(`/strategy/parse-stream`, `/strategy/builder/step-stream`)마다 취소 토큰(`backend/cancellation.py`)을 워커 스레드에 묶어, 제너레이터가 정상 종료 전에 닫히면(Starlette 연결 종료 취소) 토큰을 취소한다 — 모든 LLM 호출의 공통 관문(`_ollama_open_with_retry`·워밍업·후행 검증)이 다음 호출을 열지 않고(`OperationCancelled`, BaseException이라 `except Exception` 폴백에 삼켜지지 않음), 워커가 연 HTTP 소켓은 urllib 전역 opener 추적으로 즉시 닫아 진행 중인 Ollama 생성까지 끊는다(요청 컨텍스트 취소 → GPU 반환). 취소된 요청의 결과는 파스 캐시에 저장하지 않는다(폴백 저품질 결과가 다음 대화의 캐시 히트로 새는 것 방지). 비스트리밍 엔드포인트(분류·일반 답변·코치)와 백테스트 엔진 본체는 서버 쪽 취소 대상이 아니다(연결만 끊긴다). 회귀: `backend/tests/test_request_cancellation.py`, `app/analytics/new/page.endChat.test.tsx`, `lib/server/backend.test.ts` |
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
- LanguageToggle: 상단 내비게이션 프로필 사진 왼쪽의 KR/EN 표시 언어 토글 (`lib/i18n/LanguageToggle.tsx`)

### 7.3 다국어(i18n) — 영어 표시 [2026-08-18]

**FR-UI-i18n-001 표시 언어 토글**: 상단 내비게이션의 프로필 사진 왼쪽에 KR/EN 토글을 둔다. 선택은 쿠키(`nullstock.lang`, 1년)와 localStorage에 함께 영속하고, 새로고침으로 전체 화면을 새 언어로 다시 그린다(모듈 상수·useMemo·세션 캐시에 남은 옛 언어 문자열이 섞여 보이는 상태를 구조적으로 배제). 서버 렌더는 쿠키를 읽어(`lib/i18n/server.ts getRequestLanguage`) `<html lang>`·metadata·서버 컴포넌트를 같은 언어로 그린다.

**FR-UI-i18n-002 사전 계약**: 소스의 한국어 원문이 곧 사전 키다 — `t("한국어 원문", ...args)`(`lib/i18n/index.ts`), 자리표시자 `{0}` `{1}`. 사전(`lib/i18n/en.ts`)에 없는 키는 원문(한국어)을 그대로 돌려준다(빈칸·깨진 화면 금지). 커버리지 게이트 `tests/i18n-coverage.test.ts`가 소스의 모든 `t()` 키와 렌더 지점에서 번역되는 상수(칩·질문·라벨 맵, `scripts/i18n_extract_keys.js RENDER_SITE_FILES`)의 사전 등재를 강제한다.

**FR-UI-i18n-003 번역은 표시 전용**: 백엔드로 보내는 값(파서 프롬프트 원문, 되묻기 칩 에코 `pending_ask.chips`, 비교 대상 문자열, 슬롯 라벨 키 `PROGRESS_LABEL_TO_SLOT`)은 감싸지 않는다. 칩은 한국어 정본 문자열로 결속(chip_bindings)·전송하고 표시만 `t(chip)`으로 옮긴다. 사용자 말풍선·infoText·notices·되묻기 질문도 렌더 지점에서 `t()`로 옮기므로 백엔드 결정론 문구(슬롯 질문·칩·검증 이슈)는 사전에 원문 그대로 등재한다.

**FR-UI-i18n-004 모듈 상수 금지**: `t()`는 렌더·이벤트 핸들러 안에서만 호출한다. 모듈 최상위 상수에서 호출하면 서버 프로세스 수명 동안 첫 언어로 고정된다 — 상수는 한국어 키를 두고 표시 지점에서 `t(item.label)`로 감싼다.

**FR-UI-i18n-005 숫자·날짜·금액**: 날짜는 `getLocale()`(ko-KR/en-US), 억·만·조 단위 금액은 영어에서 compact 표기(`formatCompactNumberEn`, ₩1.5B)·원 단위는 `₩` 접두. 종목명은 한국어 정본을 유지한다(영문명 데이터 없음 — 알려진 한계).

**FR-UI-i18n-006 예시 전략**: 예시 카드·미리보기의 제목·본문은 영어로 표시하고, 미리보기 textarea의 영문 프롬프트를 파서에 그대로 보낸다(인터프리터 LLM이 영어 입력을 해석함 — 2026-08-18 로컬 실측). 영문 예시의 전수 파싱 검증(`qa_template_detect`)은 후속 과제.

**FR-UI-i18n-007 백엔드 자유 서술**: Next 프록시 `fetchBackend`가 요청 쿠키의 언어를 `X-UI-Language` 헤더로 넘기고, 백엔드 미들웨어가 `ui_language` 컨텍스트에 묶는다(파싱 스레드는 다시 bind). 인터프리터·일반 지식 답변·AI 리포트는 사용자 프롬프트 **끝**에 영어 지시를 덧붙인다(시스템 프롬프트 프리픽스 캐시 보존, JSON 키·enum·칩은 불변). 백엔드 결정론 안내문의 대부분(primary.py notices·검증기·planner asks)은 아직 한국어다 — 값이 섞인 템플릿은 `ui_language.msg(ko, en, **values)`로 옮긴다(잔여 미지원 안내부터 적용).

**제외**: 운영 콘솔(`/console`, `components/admin/`)은 번역 대상이 아니다.

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
