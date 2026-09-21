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

### 2.4 지역 기반 서비스 구조

KR/EN 언어 토글 대신 URL 경로로 지역 서비스를 나눈다.

| 항목 | 한국 서비스 | 글로벌 서비스 |
|------|------------|--------------|
| URL | `www.nullstock.im` | `www.nullstock.im/us` |
| 언어 | 한국어 전용 | 영어 전용 |
| 지원 시장 | KOSPI·KOSDAQ·ETF·미국 주식 | NYSE·NASDAQ·AMEX·ETF |
| 통화 | KRW | USD |
| 결제 | Toss Payments | PayPal Checkout (Stripe 확장 대비) |

- 자동 지역 리다이렉트는 하지 않는다 — `www.nullstock.im/*`는 무조건 한국 서비스이며 글로벌 서비스는 `/us` 경로로만 진입한다(2026-09-15 폐지: 국가 헤더가 없는 배포에서 Accept-Language 폴백이 브라우저 언어가 영어인 한국 방문자를 첫 방문 시 `/us`로 보내던 사고). 입력한 URL을 그대로 존중하고 마지막 방문 지역을 쿠키 `nullstock.region`에 기억한다.
- 백테스트 엔진은 지역별로 분리하지 않고 하나를 공유하며, 시장별 차이(캘린더·데이터 공급자·통화·심볼)만 추상화한다.
- SEO(메타·hreflang·sitemap)와 가격(`lib/pricing/kr.ts`·`us.ts`)은 지역별로 관리한다. SEO 문구·구조화 데이터의 정본은 `lib/seo/site.ts`이며, 검색 노출 문구도 규제 안전 원칙(추천·전망·수익 보장 표현 금지)을 따른다. 검색엔진 소유 확인은 `.env`의 `GOOGLE_SITE_VERIFICATION`·`NAVER_SITE_VERIFICATION`으로 낸다.

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

**FR-STR-019n** [칩=값 결속 계약, 2026-07-29] 사용자에게 보여주는 선택지 칩은 **우리 agent가 만들어 낸 열거형 옵션**이므로, 그 칩이 뜻하는 전략 값은 칩을 발행하는 순간 이미 확정돼 있어야 하고 클릭은 그 값을 꺼내 쓰는 행위여야 한다 — 칩 문구를 다시 해석(LLM 재파싱·정규식 재추출)해서는 안 된다. ① **발행 시 결속**: 조건 슬롯 ask의 칩은 `primary._bind_chips`가 발행 시점의 State에 적용해 `{필드: 값}` 패치로 확정하고, `pending_ask.chip_bindings`로 프론트에 에코한다(무상태 컨텍스트 에코 계약 — 프론트는 열지 않고 그대로 되돌려 보낸다). ② **결속 실패 = 노출 금지**: 값이 결속되지 않는 칩은 엔진이 표현할 수 없는 조건이므로 사용자에게 **아예 보여주지 않는다**(`clarification_suggestions`도 결속된 칩 목록으로 재구성, 전부 탈락이면 질문만 남기고 자유 서술로 받는다). planner LLM은 칩 문구를 자유롭게 지어내므로 이 게이트가 없으면 미지원 개념이 그대로 선택지로 나간다 — 실측 사고 2026-07-29: `volume_multiple`이 registry에 `_unsupported`이고 거래량 **하락**은 지표 자체가 없는데 '거래량 급감(전일 대비 1/2 이하) 시 매도'가 칩으로 노출됐고, 사용자가 그걸 클릭하자 "요청을 전략 조건으로 해석하지 못했어요"로 끝났다(우리가 제안한 선택지를 우리가 못 알아듣는 자기모순). 결속 성공만으로는 충분하지 않다 — **미지원 개념을 언급하는 칩은 부분 결속에 성공해도 노출하지 않는다**(`_mentioned_unsupported_concepts` 검사 — 칩 텍스트는 planner LLM 출력이므로 결정론 레인이다. 실측 사고 2026-08-02: '거래량 급증(전일 대비 3배) 시 매수'가 '거래량 급증'만 `volume_spike`로 결속돼 게이트를 통과했고, 배수 조건은 조용히 소실된 채 노출 — 클릭하면 `volume_multiple` 미지원 안내로 끝났다). 이 사고를 계기로 **planner 칩 노출 자체를 폐지했다**(2026-08-02 사용자 결정 — 모든 옵션 칩은 하드코딩 정본이어야 지원을 확신할 수 있다): 조건·설정 슬롯 ask의 칩은 `_bound_ask_with_slot_fallback`이 planner 칩을 폐기하고 **항상** 슬롯 SOT 정본(`engine.strategy_slots.suggestions_for_topic` ← `_QUESTIONS`)으로 대체해 발행한다. 라벨을 공유하는 슬롯(리스크 관리 = 손절·익절)은 topic만으로 어느 필드인지 정할 수 없으므로 `ask_field_for_topic`이 State(parsed·거부 목록)에서 아직 비어 있는 첫 필드의 칩을 고른다 — 실측 사고 2026-09-14: 손절 -9%를 말한 뒤 planner가 "익절 기준을 정할까요?"를 냈는데 손절 칩이 붙어, 사용자가 '손절 -15%'를 누르자 손절값만 바뀌고 같은 질문이 반복됐다(질문에 답하지 못하는 칩 = 이 계약의 위반). ETF 유니버스에는 재무 칩(PER·ROE)이 제외되며(`universe_capabilities` — ETF는 기업 재무 사용 불가, 결속 검사는 유니버스 호환성을 보지 않으므로 정본 선별 단계에서 걸러야 한다), topic이 슬롯에 매칭되지 않으면 칩 없이 질문만 남는다(LLM 칩으로 메우지 않는다). 유니버스 범위 칩(④)과 미해결 업종·종목 후보 칩은 관찰된 카탈로그/리졸버 후보 표기 그대로라(결정론 데이터) 이 대체의 대상이 아니다. ③ **description은 값이 아니다**: `description`은 발화 원문 보관 필드라 전략을 바꾸지 않는다 — 이 필드만 달라진 칩은 결속 실패로 판정한다. 이 구분이 없어 `run_chip_answer`가 무변경을 "칩 답변 확정"으로 오보고하던 구멍이 있었다(사용자는 답했는데 아무것도 안 바뀐 화면을 본다). ④ **유니버스 범위 칩은 예외**: 칩이 카탈로그 후보 표기 그대로라 결속이 이미 보장돼 있고(`_planner_scope_ask`), 발행 시 결속을 시도하면 테마 상장사 조회가 칩 수만큼 반복돼 발행 지연이 커진다 — 클릭 시 `_apply_universe_chip`이 결정론으로 적용한다. ⑤ **출력 가드 동기화**: 규제 가드가 칩 문구를 바꾸면 결속 키가 어긋나므로 살아남은 칩의 결속만 남긴다(`output_guard.finalize_user_response`) — 결속을 잃은 칩은 칩 문구 결정적 추출 안전망으로 강등된다. ⑥ **하위 호환**: `chip_bindings` 없는 구 에코는 기존 결정적 추출 경로를 그대로 탄다. 회귀: `test_chip_answer.py`(미결속 칩 미노출·미지원 개념 언급 칩 미노출·전량 탈락 시 칩 제거·description-only 미적용·결속값 직접 적용·재계획 칩 정본 대체), `test_slot_clarification_chips.py`(planner 칩 정본 대체·ETF 재무 칩 제외·정본 칩 결속 실증).

**FR-STR-019o** [전략 파스 지연 예산, 2026-07-29] 전략 파스 1회의 지연은 **LLM 호출 횟수 × (prefill + 생성)** 으로만 결정된다 — 실측(로컬 9B) 결과 테마·KG 조회 등 비-LLM 작업은 전부 합쳐 74ms(0.0%)였고, 나머지 100%가 LLM이었다. 따라서 지연 대책은 **호출 횟수를 줄이거나 prefill을 재사용하는 것**뿐이며, 타임아웃 상향은 대책이 아니다. ① **prefill이 생성보다 비싸다**: 인터프리터 system 프롬프트는 20,470자(~8,900 tok)이고 콜드 prefill 43.6초 vs 캐시 적중 0.4초(총 호출 60.2초 → 7.5초, 109배). 고정 system 프롬프트는 대화마다 바뀌지 않으므로 **startup에 한 번 흘려 KV 프리픽스 캐시를 채운다**(`main._kick_system_prompt_prefill` → `nl_parser._ollama_prefill_system_prompt`, 인터프리터·planner 각 1회, num_predict=1, keep_alive=-1). 모델 가중치 적재(`_kick_local_ollama_model_preload`)로는 해결되지 않는 별개 비용이다 — 가중치가 올라와 있어도 prefill은 호출마다 다시 계산된다. ② **planner 재계획 금지**: planner는 mode=primary인 모든 턴에서 파스 최선두(`_plan_first`)로 이미 돌므로, 그 실패를 근거로 되묻기 단계에서 **다시 계획하면 안 된다**. 예산 소진은 실패가 아니라 검증 리포트 고정 질문으로 폴백하는 정상 경로다 — 재시도 분기를 두면 실패가 비용을 두 배로 만든다(실측: 한 파스에서 planner 6회 호출, 148초 + 84초). ③ **턴 예산 2**(`dag_planner_max_turns`, 롤백 `STRATEGY_DAG_PLANNER_MAX_TURNS=4`): warm 캐시에서도 planner 1턴이 40~56초라 예산이 곧 지연이다. 발행→도구 관찰→수정 발행이 통상 흐름이고 그 이상은 값을 거의 못 얻는다. ④ **측정 규율**: 이 계층의 지연 실측은 머신 부하에 극단적으로 민감하다(같은 인터프리터 호출이 load 11에서 21초, load 90에서 43초). 벽시계 비교는 부하가 안정된 상태에서만 유효하며, 부하와 무관한 정본 지표는 **LLM 호출 횟수와 prefill 토큰 수**다. ⑤ **프롬프트 예산**(2026-07-30): 시스템 프롬프트는 prefill 비용에 직결되므로 **파이프라인이 읽지 않는 출력 채널을 LLM에 요구하지 않는다** — `status`·`missing_fields`·`assumptions`는 각각 `run_validation` 재판정·`validate_completeness` 결정론 산출·소비자 부재로 죽은 채널이어서 형태와 규칙에서 제거했다(20,470자→19,441자). 다만 **형태(`_OUTPUT_SHAPE`)에서 키를 빼는 것과 규칙 문장을 빼는 것은 힘이 다르다** — 형태에 없는 키는 규칙이 아무리 상세해도 9B가 채우지 않으므로, 살아 있는 필드는 반드시 형태에 남긴다(FR-STR-019p). ⑥ **워밍업은 추론과 같은 `num_ctx`로 한다**(2026-07-30, 필수 계약): Ollama 러너는 **적재 시점 옵션으로 뜨고**, 다른 `num_ctx` 요청이 오면 러너를 갈아끼운다. 워밍업(`_ollama_preload_model`·`_ollama_prefill_system_prompt`)은 `keep_alive=-1`로 러너를 **영구 고정**하므로, 워밍업이 추론과 다른 컨텍스트로 적재하면 교체가 끝나지 않고 이후 **모든 추론 호출이 무한 대기**한다 — 지연이 아니라 완전 정지다. 실측 사고: 워밍업이 `num_ctx`를 싣지 않아 러너가 모델 최대 컨텍스트(262144)로 고정 → `num_ctx=16384` 추론이 240초+ 무응답(러너 CPU 0%, 신규 러너 미기동) → 파스 1회 480초 → 프론트 프록시 120초 예산 초과로 `The operation was aborted due to timeout`. 같은 모델·같은 질문이 `num_ctx` 생략 시 0.8초, 지정 시 240초+였고, 워밍업에 `_OLLAMA_NUM_CTX`를 실은 뒤 파스가 19.9초로 복귀했다. 또한 컨텍스트가 다르면 prefill KV 캐시가 **다른 러너에 쌓여** ① 자체가 무효가 된다. 이 규칙은 `parse_validator._VALIDATION_NUM_CTX` 주석이 이미 명문화한 것으로(당시 증상은 '호출마다 콜드 페널티'), `keep_alive=-1` 고정이 더해지며 치명도가 올라갔다. 회귀 가드: `test_ollama_warmup_uses_same_num_ctx_as_inference`. **워밍업 시점의 일치만으로는 부족하다**(2026-08-27 재발): 러너는 머신 전역 자원이라 체크아웃별로 격리되지 않으므로, 우리가 올바르게 고정한 뒤에도 **다른 프로세스가 다시 어긋나게 고정할 수 있다** — 실측 사고에서는 `_OLLAMA_NUM_CTX`를 20480→32768로 올린 뒤 옛 커밋을 담은 임시 워크트리에서 백엔드가 한 번 뜨며 20480짜리 러너를 `keep_alive=-1`로 재고정했고, 그 프로세스가 종료된 뒤에도 고정이 남아 이후 **모든 파싱이 240초를 채우고** `The operation was aborted due to timeout`으로 실패했다(대조 실측: `num_ctx=20480` 요청 0.55초 / `32768` 요청 45초 무응답, 트레이스는 LLM 호출 1건이 `duration_ms≈240,000`·`error_kind=OperationCancelled`). 따라서 **추론을 열기 직전에 매번 러너 정합을 확인한다** — `nl_parser._ollama_align_runner_num_ctx`가 `GET /api/ps`(로컬 실측 <1ms)로 적재된 9B 러너의 `context_length`를 읽고, `_OLLAMA_NUM_CTX`와 다르면 `keep_alive=0`으로 내려 우리 요청이 자기 컨텍스트로 새 러너를 띄우게 한다(적재 ~3초). 호출 지점은 셋이다 — 추론 공통 관문(`_ollama_open_with_retry`, **취소 확인 뒤** 첫 시도에서 1회), 워밍업 적재(`_ollama_preload_model` — 어긋난 러너 위에 고정 요청을 얹으면 그것부터 멈춘다), 공통 관문을 지나지 않는 후행 검증(`parse_validator._run_validation_llm`, `NL_VALIDATOR_MODEL`로 다른 모델을 쓰는 중이면 9B 슬롯과 무관하므로 건너뛴다). 가드의 조회·해제 실패는 삼킨다(가드가 새 실패 경로가 되면 안 된다) 하고, 원격(Modal)은 러너 고정 개념이 없어 로컬에서만 동작한다. 회귀 가드: `test_ollama_guard_releases_runner_pinned_at_other_num_ctx`·`test_ollama_guard_keeps_runner_that_already_matches`·`test_ollama_guard_is_noop_when_no_runner_loaded`·`test_ollama_guard_swallows_probe_failure`·`test_ollama_inference_gate_aligns_runner_before_opening`·`test_ollama_preload_aligns_runner_before_pinning`. **같은 조사에서 드러난 두 개의 구조적 결함**(둘 다 이 증상 계열의 진짜 뿌리다): **(가) 저장소 안의 값 중복** — `num_ctx`가 여러 파일에 숫자 리터럴로 흩어져 있고, 같은 9B 슬롯에 다른 값을 보내는 코드가 **하나만 있어도 그것을 실행하는 순간 머신 전체의 파싱이 멈춘다**. 실제로 `backend/scripts/build_modify_corpus.py`가 `num_ctx: 4096`을 하드코딩한 채 남아 있었고(2026-08-23 `qa_intent_open_pick_scope.py` 16384 하드코딩에 이은 세 번째 재발), 돌리기만 하면 같은 사고가 났을 지뢰였다. 값 일치를 사람의 주의력에 맡기지 않고 소스 스캔으로 강제한다 — `test_no_source_hardcodes_a_num_ctx_literal`(AST로 `num_ctx`에 숫자 리터럴이 붙은 자리만 잡아 산문·주석은 오탐하지 않는다, 뮤테이션 검증 완료). 통과 방법은 하나 — `_OLLAMA_NUM_CTX`를 import해서 쓴다. **(나) 예산 위계 역전** — 백엔드 단일 호출 상한(`_OLLAMA_MAX_ATTEMPT_TIMEOUT_S=240`)이 프론트 프록시 예산(`route.ts` `timeoutMs=240_000`)과 **정확히 같아** 언제나 프록시가 경주에서 이겼다. 그래서 백엔드는 원인을 말할 기회를 **구조적으로** 얻지 못했고, 사용자에게는 두 번 연속 원인과 무관한 `The operation was aborted due to timeout`만 떴다(2026-08-26 컨텍스트 초과 400 오분류, 2026-08-27 러너 재고정). 게다가 관문의 `timeout` 인자는 **한 번도 쓰이지 않는 죽은 파라미터**였다(문서화된 '단일 long timeout'과 코드가 불일치). 수정: 콜드스타트가 없는 **로컬 전용 상한** `_OLLAMA_LOCAL_MAX_ATTEMPT_TIMEOUT_S=200`을 두어 백엔드가 먼저 실패하게 하고, 그 실패를 `_ollama_timeout_error`가 **원인을 붙인 문구**로 바꾼다(적재된 러너의 `num_ctx`를 읽어 불일치면 그것을 지목 — `main.parse_nl_strategy_stream`이 `str(exc)`를 SSE `error.detail`로 실어 보내므로 이 문자열이 곧 사용자가 보는 화면이다). 240초를 넘겨야 성공하던 호출은 어차피 프록시가 끊었으므로 상한을 낮춰 잃는 성공 케이스는 없다. 원격(Modal)은 콜드스타트 무응답이 정상 범주라 종전 상한·원본 예외를 그대로 쓴다. 회귀: `test_local_llm_budget_is_smaller_than_the_frontend_proxy_budget`(route.ts를 직접 읽어 위계를 강제)·`test_local_timeout_names_the_runner_mismatch`·`test_remote_timeout_is_passed_through_untouched`. **의도적으로 하지 않은 것**: 워밍업의 `keep_alive=-1`을 유한값으로 바꾸는 안은 기각했다 — 고아 고정이 자동 만료되는 이득보다 idle 언로드로 KV 프리픽스 캐시를 잃어 다음 파스가 ①의 43.6초 prefill을 다시 무는 손해가 크고, 고아 고정은 정합 가드가 이미 다음 호출에서 치유한다. 실측으로도 `keep_alive=-1` 자체는 교체를 막지 않았다(1b 모델 대조: `-1`이어도 num_ctx 교체 1.14초). ⑦ **서버 부재는 워밍업 실패와 다른 사건이다**(2026-08-01): 적재·prefill 실패는 "첫 호출 시 lazy 로드"로 복구되므로 무시해도 되지만, 로컬 Ollama **서버 자체가 죽어 있으면** 그 전제가 성립하지 않는다 — 백엔드는 LLM 없이 조용히 기동하고, 사용자에게는 파싱 회귀로 보인다(실측 사고: 전략 문장이 `intent=UNKNOWN`(호출조차 못 해 0.0초)으로 분류돼 프론트가 일반답변 경로로 보내고, 그 LLM도 없어 "해당 주제에 대한 일반적인 설명을 준비하지 못했습니다" 폴백 — 분류·파싱·일반답변 세 레인이 동시에 죽는다). 따라서 startup은 워밍업 **전에** 서버 생사를 확인하고(`main._local_ollama_reachable`: GET `/api/tags`, 3초), 닿지 못하면 적재·prefill을 건너뛰고 조치 방법과 함께 로그로 알린다. 로컬 dev는 `brew services start ollama`로 부팅 시 자동 기동한다(수동 기동 의존이 사고의 배경이었다). 회귀 가드: `test_startup_model_preload.py::test_unreachable_local_ollama_warns_and_skips_preload`.

**FR-STR-019oa** [분류 종결 유니버스의 planner 재제시 생략, 2026-09-16] State 없는 planner-first 턴에서 실행 도구가 `classify_universe`뿐이고 판정이 전부 종결 종류(MARKET·SECTOR·SINGLE_STOCK·ETF·NOT_UNIVERSE)면 관찰을 LLM에 다시 제시하지 않고 `universe_settled`로 종결해야 한다. 근거: 그 턴이 낼 수 있는 조건 ask는 파스 뒤 결정론 게이트 통과 시에만 채택되고 칩은 슬롯 정본이라, 3일 실측 638턴 중 630턴의 호출이 버려졌다(같은 날 OpenRouter 무료 한도 1,000건이 예시 게이트 2회에 소진). 요청당 LLM 호출 5→4. 판정 입력은 도구 관찰값이며 사용자 원문이 아니다. CONCEPT 체인·State 있는 재계획 턴은 대상이 아니다. 회귀 `tests/test_dag_planner.py::test_settled_classification_*`.

**FR-STR-019ob** [원문만 보는 파스 호출의 병렬 요청, 2026-09-17] 초기 파스에서 사용자 원문만 입력으로 받고 서로의 출력을 입력으로 받지 않는 세 호출 — planner-first, 인터프리터, 조건 누락 대조의 구절 나열 — 은 OpenRouter 레인에서 동시에 보내야 한다. 결과를 합치는 순서(planner 결과 적용·구절 대조·기간 회수·업종 해석)는 순차와 같게 코드가 지키며, LLM이 보는 입출력은 순차와 동일해야 한다(출력 형태·프롬프트를 바꾸는 절감은 이 요구사항의 범위가 아니다 — 같은 날 빈 키 생략 실험이 120B에서 etf_theme 소실·말하지 않은 체결 시점 채움을 재현해 기각됐다). 워커 스레드에는 요청 컨텍스트(취소 토큰·trace 부모·진행 표시)를 복사해 넘긴다. 로컬·폴백 Ollama 레인은 한 슬롯에 줄을 서 이득이 없고 긴 인터프리터 프리픽스 캐시만 밀려나므로 순차를 유지한다. 롤백 `STRATEGY_PARALLEL_PARSE=off`. 실측(120B, 예시 12개 on/off 교차): 턴 시간 중앙 9.55→4.91초, 12개 중 11개 단축, LLM 호출 수 동일. 구절 나열은 1차 해석 전에 보내므로 인터프리터가 해석 실패로 끝나는 턴에서는 호출 1건이 소비된다(3일 트레이스 469턴 중 해당 0건). 회귀 `backend/tests/test_parallel_parse.py`.

**FR-STR-019p** [출력 형태 권위 — 살아 있는 필드는 형태에 싣는다, 2026-07-30] 인터프리터 LLM(9B)에게 **출력 형태(`_OUTPUT_SHAPE`)에 없는 키는 규칙 문장으로 요구할 수 없다.** 형태에 없으면 모델은 그 자리를 `null`로 내거나 아예 생략하며, 이는 사용자가 말한 값을 조용히 잃는 사고로 직결된다. ① **실측 사고**: 조건 예시가 재무 조건 하나뿐이라 `parameters` 키가 형태에 없었고, 규칙 5-3이 `short_period=1`/`long_period=N` 매핑을 상세히 규정했음에도 "20일선을 깨고 내려오면 매도"·"주가가 20일선을 상향 돌파"·"20일선이 60일선을 골든크로스"가 1차 출력에서 `parameters=null`로 나왔다 — 사용자가 말한 기간이 사라져 완결성 검증이 "단기 기간을 몇으로 할까요?"라고 되물었다(이미 답한 값 재질문). `etf_theme`(FR-STR-067, 2026-07-27)과 동일한 실패 방식이다. ② **수정**: 형태의 `entry_conditions`에 `parameters`를 채운 크로스오버 조건을 함께 싣고, 단일 이동평균 문장의 worked example(예시 3-1)과 긴 요청 예시(4-2)에 파라미터를 명시한다 — 후자는 이동평균이 하나만 언급됐는데 다른 예시의 20/60을 베껴 **말하지 않은 60을 지어내던** 무단 확정을 차단한다. ③ **형식 정규화**: `parameters: null`은 빈 dict와 같은 뜻이므로 `StrategyCondition._coerce_parameters`가 흡수한다 — 종전에는 `dict_type` ValidationError로 출력 전체가 버려져 복구 재요청 1회(수 초)를 무조건 태웠고, 재요청 결과도 기간을 채워 오지 않았다. ④ **검증 규율**: 프롬프트 규칙만 고치고 형태를 그대로 두는 변경은 이 계층에서 효과를 보증하지 못한다 — 실제 모델로 같은 문장을 반복 실행해 확인한다(수정 검증: 5문장×3회 15/15, `repairs=0`, 기간 되묻기 소멸, 비-이동평균 전략에 유령 크로스오버 조건 유입 없음). ⑤ **같은 교훈이 배포 직후 재발**: 죽은 채널 제거(FR-STR-019o ⑤) 작업에서 예시 1의 clarification_questions worked example(`{"field":"strategy.entry_conditions[0].value", ...}`)을 함께 지웠는데, 그 예시가 프롬프트 전체에서 `ClarificationQuestion` 객체 형태를 보여주는 유일한 자리였다(형태의 `clarification_questions`는 원래도 빈 배열이라 형태 자체는 스키마를 가르치지 못한다). 결과: 9B가 되묻기 항목을 낼 때 필수 필드 `field`를 빠뜨려 StrategyIntent 검증 실패→복구 재시도(`MAX_REPAIR_ATTEMPTS=1`)도 같은 방식으로 실패→`InterpreterError`로 **전략 전체가 버려졌다** — "20일 고점을 넘기는 날 매수"처럼 완전히 파싱 가능한 입력까지 빈 전략(`interpretation_failed`, universe=KOSPI200 기본값)으로 끝났다. 실측: `qa_template_detect.py --category 기술분석 --refresh` 20개 중 5개 치명(모두 동일한 `유니버스=KOSPI200 · max_pos=10` 고정값 — 프롬프트 내용과 무관해 실제 해석 실패가 아니라 스키마 거부로 의심할 신호였다). 수정: 형태의 `clarification_questions`에 `field` 키를 채운 worked example을 다시 싣는다. **검증 함정**: 직접 스크립트로 인터프리터를 호출하는 진단은 `.env`를 로드하지 않는다 — `load_dotenv()`는 `main.py` 임포트에만 걸려 있어, `main.py`를 거치지 않는 스크립트는 `STRATEGY_INTERPRETER_MODEL`이 비어 코드 기본값(`qwen3:8b`, prod 모델과 다른 모델)으로 조용히 폴백한다 — 이 세션에서 그 폴백 때문에 회귀를 놓치고 "9B로 검증됨"이라고 잘못 보고할 뻔했다. 인터프리터를 직접 호출해 검증할 때는 `STRATEGY_INTERPRETER_MODEL`을 명시적으로 export하거나, HTTP `/strategy/parse` 엔드포인트(서버 프로세스는 항상 `.env`를 로드)를 통해 검증한다. ⑥ **구조적 가드**(2026-07-30): 같은 사고가 두 번 난 뒤 회귀 테스트를 개별 필드 단위가 아니라 **불변식**으로 세웠다 — `test_output_shape_objects_expose_all_live_fields`는 형태에 **구체적 객체로** 등장하는 모델(`universe`·`portfolio`·`risk_management`·`backtest`·`entry_conditions[]`·`clarification_questions[]`)의 스키마 필드가 형태에 빠짐없이 노출되는지 검사한다. 스키마에 필드를 추가하고 형태 갱신을 잊으면 실패하며, 일부러 빼는 필드는 `_SHAPE_OMISSIONS`에 **이유와 함께** 등록해야 한다(형태에서 빼는 것을 의식적 결정으로 강제). 검사 대상을 '구체적 객체'로 한정한 근거: `ranking: []`처럼 빈 배열로만 등장하는 자리는 잘못된 키 집합을 각인시키지 않아 규칙·예시만으로 정상 동작한다(실측) — 위험한 것은 **일부 키만 보여준 객체**이며, 모델이 그 키 집합을 완전한 것으로 취급한다. 현재 등록된 의도적 누락: `max_position_weight`(엔진 미지원 — 노출하면 오류 출력을 유도), `value_source`(모델 validator 계산값), `recommended_value`·`requires_confirmation`(Registry가 독립 공급), `recommendation_reason`(선택적 서술). 뮤테이션 검증 완료(신규 필드 주입 시 실패, 원복 시 통과). ⑦ **필수의 경계 — 침묵은 거부, '없음'은 명시적 null**(2026-08-16): ⑤의 가드는 "스키마가 `field` 누락을 거부한다"는 전제 위에 서 있는데, 종전 `field: str`은 **명시적 `null`까지 함께 거부**했다. `intent=NON_STRATEGY_REQUEST`에는 가리킬 전략 필드가 애초에 없어 9B가 정직하게 `field=null`을 내는데, 스키마가 그것을 튕겨 수리 재요청으로 넘어갔고 **재요청이 없는 필드를 지어냈다**. 실측: "내 돈 3천만원 대신 투자해줘"의 1차 출력은 `unsupported_features=["내 돈"]`에 "주식 투자 전략을 구체적으로 설계해 드릴까요?"로 대리투자를 받아주지 않았으나, 재생성본이 `field="backtest.initial_capital"`·`recommended_value=30000000`인 초기자본 질문으로 바꿔 **규제 대상 요청을 전략 설정으로 받아 적었다** — 1차 출력이 더 옳았고 스키마가 그것을 거부한 것이 원인이다(수리 재요청이 원출력의 옳은 판단을 훼손하는 같은 구조: `salvage_clarification_questions`, 2026-08-10). 수정: `field: Optional[str]`을 **기본값 없이** 선언한다(Pydantic v2에서 필수·nullable) — 키 누락은 계속 거부해 ⑤의 가드를 그대로 유지하고, '가리킬 필드 없음'은 명시적 `null`로만 말하게 한다. 소비처 중 `q.field`를 정규식에 직접 넣던 `primary._clarification_items`만 `q.field or ""`로 막았다(나머지는 이미 falsy·None 안전). 발견 경로: 인터프리터 원출력 수집 하니스(`scripts/qa_interpreter_raw_capture.py`)의 319건 baseline — 원출력이 어디에도 저장되지 않아 이 계열 결함이 보이지 않던 상태였다. 회귀: `test_clarification_question_without_a_field_path_validates`, `test_build_clarification_items_survives_a_null_field`(둘 다 `test_interpretation_authority.py`), 기존 `test_clarification_question_missing_field_key_is_rejected`와 공존.
**FR-STR-019q** [필드 상태 축 — '해당 없음'과 '완료'의 분리, 2026-07-30] 진행 골격 필드의 충족 판정은 `filled: bool` 하나로 표현할 수 없다. 그 불리언은 서로 다른 셋을 같은 값으로 뭉갠다 — ① 사용자가 말한 값 ② 기본값이 물질화된 미확인 값 ③ 물을 대상이 아닌 항목. 특히 ③이 '완료'로 표시돼 **단일 종목 전략의 리밸런싱 칸에 체크가 켜지고 진행률이 실제보다 높게** 보였다. 따라서 `engine/strategy_slots.py`(FR-STR-019m의 판정 SOT)는 `filled`와 **독립된 상태 축**(`FieldStatus` 7종: UNKNOWN·CONFIRMED·INFERRED·PROVISIONAL·INVALID·CONFLICTED·NOT_APPLICABLE)을 함께 산출해야 한다. ① **스키마를 감싸지 않는다** — 설계 스펙 § 5의 `{value, status, source, ...}` 래핑은 컴파일러·디컴파일러·patch_applier·엔진 변환기·프론트를 전부 깨뜨린다. 값의 표현은 그대로 두고 상태만 옆에 다는 사이드카여야 한다. ② **새 판정을 만들지 않는다** — UNKNOWN/CONFIRMED/PROVISIONAL/NOT_APPLICABLE은 기존 3축(`_decided`·`_has_value`·`_explicit_ok`)의 재해석이고, INVALID(지표 미해석·미지원)와 조건 단위 NOT_APPLICABLE(ETF×기업 재무지표)은 검증 후 `StrategySpec`에서 구조적으로 재판정하며(`validation/field_state.py`), CONFLICTED만 `conflict_validator`가 판정한 자리에서 슬롯을 함께 기록한다(`ValidationReport.conflicted_slots` — 오류 문장만으로는 어느 필드가 모순인지 알 수 없다). 같은 규칙의 두 번째 구현은 반드시 갈라지므로 금지한다. INVALID와 NOT_APPLICABLE을 나누는 기준은 해결책이다 — 전자는 지표를 바꾸고 후자는 유니버스를 바꾼다. ③ **`filled` 판정을 바꾸지 않는다** — 상태 축은 표시 전용이며 되묻기 게이트·백테스트 실행 버튼·planner의 `filled_slots`는 도입 전과 동일하게 동작해야 한다. `status_overrides`도 상태만 덮고, 값이 없는 필드(UNKNOWN)는 덮지 않는다(모순일 수 없다). 무회귀의 근거는 계약 픽스처(`__fixtures__/slot-judgments.json`) 재생성 시 **무변동**이다. ④ **진행률 표시** — 'NOT_APPLICABLE'은 분자·분모 양쪽에서 뺀다(`countProgress`). 완료로 세면 진행률이 부풀고, 미완료로 세면 영원히 채울 수 없다. INVALID·CONFLICTED는 분모에 남는다(해결해야 할 칸이다). 백엔드 `field_states`는 SSE 프록시 화이트리스트에 실려야 하며, 누락 시 표시만 이전으로 회귀하고 흐름은 그대로다. ⑤ **미구현**: 설계 스펙 § 5의 `source`·`confidence`·`updated_at`·`dependencies`·`invalidated_by` 메타데이터(현행 `ValueSource`·provenance가 source의 부분집합을 담당), INFERRED 산출(열거형 정의만 — 슬롯 단위로 롤업할 소비자가 없어 미리 만들지 않는다). **[2026-08-02 개정 — '최대 보유' NOT_APPLICABLE 경계]**: 지정 종목 모드의 '최대 보유'(진행률 카드 '포트폴리오' 칸)가 종목 수와 무관하게 NOT_APPLICABLE로 계산돼, 다종목 지정(HBM 테마 33곳)에서 요약 카드는 '지정 종목 33개 균등 투자'를 보여주는데 진행률 카드만 '해당 없음'을 표시하는 모순이 있었다. 판정 경계를 리밸런싱과 동일한 단독/다종목 축으로 통일한다(`strategy_slots._status_only_not_applicable`): 단독 종목(지정 1개)만 해당 없음(포트폴리오 자체가 없다), 다종목 지정은 보유 수가 종목 수로 확정된 완료(APPLICABLE·CONFIRMED, 진행률 분모 포함). filled 판정은 불변(③ 계약 유지). 회귀: `test_strategy_slots.py::test_multi_symbol_max_positions_is_applicable_and_confirmed`. **[2026-09-14 개정 — 칩 레인의 낡은 상태 축]**: 칩 답변은 백엔드 왕복 없이 프론트 State에 적용되는데(`handleSuggestionClick` 결정론 레인), 진행률 카드가 덧씌우는 `field_states`는 직전 파스 턴의 판정 그대로였다. 리밸런싱 없이 파스된 전략에 '분기'·'비중 조정' 칩을 답하면 요약 카드에는 방식이 보이는데 진행률의 '리밸런싱 방식'은 파스 시점의 '해당 없음'에 머물렀다(체크 없음·분모 제외). 수리: 칩 적용 직후 `refreshFieldStatesAfterChoice`가 **답한 칸의 항목을 지워** 프론트 complete 술어(백엔드 filled와 동형)로 되돌리고, 리밸런싱을 답한 때만 딸린 '리밸런싱 방식' 칸을 주기 유무에 따라 지우거나 NOT_APPLICABLE로 둔다(백엔드 `_decided` ①의 사본 하나 — 새 판정을 만들지 않는 ② 계약 유지). 칩 턴의 '돌아가기'는 걷어내기 전 맵을 `previousStepState.fieldStates`로 복원한다. 회귀: `builderProgressPresentation.test.ts::refreshFieldStatesAfterChoice`.

**FR-STR-019r** [유니버스 확인 질문 무응답 소멸 안내, 2026-08-02] Agent Architecture Audit(Planner→Action DAG→State) 재현: 유니버스 범위 확인 질문("'ESS'는 '전력저장장치(ESS)' 테마예요, 이 범위로 바꿀까요?")이 대기 중일 때 사용자가 그 확인과 무관한 답(예: 매수 조건 칩)을 하면, DAG가 그 질문을 재질문·안내 없이 버리고 다음 화제로 넘어갔다 — 유니버스는 이전 값에 그대로 머무는데 사용자는 그 사실을 알 방법이 없었다. `strategy_conversation/planner/dag.py`의 `NodeStatus.INVALIDATED`(§ 12.2 설계 의도: "무효화된 노드는 삭제하지 않고 남긴다")는 실제로는 `_trace_final_statuses`를 통해 관측(trace)에만 쓰이고 사용자 응답에는 배선돼 있지 않았다. `main._flag_unresolved_universe_ask`(모든 반환 지점이 지나는 `_finalize_parse_result`의 마지막 단계)가 최소 보정을 한다: 직전 턴 `pending_ask.topic`이 유니버스 확인이었고, 이번 턴의 `pending_ask.topic`도 유니버스가 아니며, 유니버스 관련 필드(`universe`·`sector`·`theme_universe`·`etf_theme`·`target_symbols`)가 이전 턴과 완전히 동일하면 — 그 질문이 아직 답변되지 않았다는 `notices`를 덧붙인다. 판정은 두 턴의 topic 라벨(LLM/planner 출력)과 필드값 동일성 비교뿐이며 사용자 원문을 다시 읽지 않는다(계약 § 판정 기준). 슬롯 완결성 재질문(예: 매도 조건이 매 턴 반복되는 것)은 대상이 아니다 — 그건 서로 다른 진행 골격 슬롯(EXIT vs STOP_LOSS/TAKE_PROFIT)이 독립적으로 비어 있는 정상 동작이다(`engine/strategy_slots._has_value` 참고). 같은 감사에서 발견된 별개 사고(대원칙 1 위반 — `intent/condition_builder.py::clarification_for_add`가 수정 턴마다 `request.prompt` 원문에 정규식 cue 매칭을 돌려 인터프리터를 아예 호출하지 않고 응답을 확정했다, 예: "ESS 종목 중에서 거래대금 상위만 넣어줘"가 "ESS"·랭킹 요청을 통째로 무시하고 "거래대금 몇억 이상?"만 반환·LLM 호출 0회)는 `main.py`의 그 호출 제거로 수정했다 — 값 없는 조건 추가는 `validate_intent`→`validate_completeness`가 인터프리터의 구조화 출력을 보고 이미 동일한 모양의 되묻기를 낸다(중복 로직 제거, 새 판정 추가 아님). 회귀: `test_modify_roundtrip_migration.py`(`test_add_cue_reaches_interpreter_instead_of_raw_regex_shortcut`, `test_unresolved_universe_ask_is_flagged_when_topic_shifts_without_change`, `test_universe_ask_not_flagged_when_universe_actually_changed`, `test_universe_ask_not_flagged_when_still_the_open_question`).

**FR-STR-019s** [검증 거부의 정직한 보고 + 대조 게이트 단위 공백, 2026-08-02] Agent Architecture Audit #3(멀티턴 에코 하니스 25턴 실측) 결함 8건 수정. 핵심 계약 4개: ① **검증 거부는 해석 실패가 아니다** — 수정 턴에서 패치 적용 후 검증 오류(코스피+PER→ETF의 capability 충돌 등)가 나면 llm_first에서는 폴백("해석하지 못했어요" 오보고) 대신 전략 무변경 + 검증기 오류 문장을 그대로 되묻기로 전달해야 한다(`primary._capability_conflict_clarification`). 유니버스 변경 턴의 해소 칩은 검증기 unsupported 표기와 패치된 State에서 결정론 조립하며, **pending_ask 결속 없이** 내보낸다 — 복합 의미("제거+전환") 칩을 결속 프로브가 절반만 결속시키면 클릭이 결정론 레인에서 부분 적용된다(실측). ② **§ 3-1 수치 대조의 단위 환산표는 복합 수사 단위(천만·백만·십만)를 포함해야 한다** — "5천만원"이 "5천"으로 절단되면 게이트가 정당한 패치를 자릿수 모순으로 거부한다(자릿수 오류 검출력은 유지). ③ **미반영(notices-only) 응답은 답을 기다리던 질문을 되붙인다**(`primary._reattach_open_question` — FR-SA-015의 파스 레인 등가물, 에코된 pending_ask/pending_question 전달만). **[2026-08-29 보강] 되붙이는 질문이 진행 골격 슬롯의 정본 문구면 그 슬롯의 정본 칩도 함께 되붙인다** — 프론트 게이트가 물은 슬롯 질문에는 백엔드 pending_ask가 없어 질문 문자열만 돌아갔는데, 우선순위 마커(`modify_unapplied`)가 프론트 게이트를 이기므로 칩 있는 같은 질문 대신 **무칩 사본**이 그려져 선택지 박스가 사라지고 채팅 입력창만 남았다(실측: 매수 조건 되묻기 중 "제이콘텐트리 종목을 추가해줘"). 슬롯 판정은 우리가 발행한 정본 문구의 정확 일치(`strategy_slots.slot_for_question` — 원문 해석이 아니라 표기 정규화), 칩은 슬롯 SOT에서 가져와 발행 시점에 결속한다(칩=값 결속 계약 유지). 프론트는 되붙은 질문이 게이트가 물었을 그 질문과 같으면 슬롯 필드도 함께 물려받는다 — 필드가 비면 닫힌 선택지인 시장 질문에 '직접 입력'이 되살아난다. ④ **planner 턴 예산은 무진전 반복만 막는다** — 직전 턴이 새 관찰을 만들었으면 +2턴 연장하고, list_concept_candidates 후보가 정확히 1개면 그 정본 표기의 kg_theme_companies 조회는 LLM 판단이 아니라 결정론 에필로그다(후보 2개 이상은 범위 ask — 자동 조회 금지). 부수: Artifact 상태 레인(FR-SA-011)·field_metadata는 직렬화된 dict 입력도 수용해야 하며(라이브 경로 모양 — 인스턴스만 주입하는 테스트는 사각), 비-SSE `/strategy/parse` 응답 모델은 `field_states`를 노출해야 한다. 분류 프롬프트 규칙 4-2(작업 제어 발화는 규제 게이트 라벨이 아니다)와 인터프리터 예시 3-0(기간 없는 골든크로스=정본 5/20, 오타 변형 포함)은 라이브 실측으로 검증(15/15·3/3). 회귀: `test_agent_audit3_fixes.py`, `test_dag_planner.py`.


**FR-STR-019t** [손절·익절 단일 표현 + 청산 역할 검증, 2026-08-05] ① **손절·익절은 정본 자리(risk_management)에 한 번만 남긴다** — 인터프리터가 조건 목록에 factor=`risk_management.*`로 실어 보낸 항목은 형식 정규화가 값을 빈 risk_management 필드로 흡수한 뒤 목록에서 제거한다(`interpreter/models.py::_absorb_risk_field_conditions` — 2026-08-06 FR-STR-019v에서 `_absorb_scalar_slot_conditions`로 확장·개명). 손절은 의미상 청산 규칙이 맞으므로(사용자 판정 2026-08-05) 이 중복은 환각이 아니라 표현 자리 문제다. 값도 없고 필드도 비어 있으면 제거하지 않는다(조용한 누락 금지 — 미지원 팩터 안내 레인이 담당). ② **capability 검증은 청산 조건의 역할 호환(기술적 신호만 가능)을 검사해 위반을 에러로 보고해야 한다** — 에러 없이 READY로 통과하면 전량 컴파일이 첫 위반에서 `StrategyCompileError`로 전략 전체를 버리고 "해석하지 못했어요"로 강등된다(2026-08-05 사고: 9B가 손절 -8%를 `fundamental.roe_or_gpa<=-100` 청산 조건으로 미러링 — 현금흐름 3분류 지표 승격이 프롬프트 지표 카탈로그를 바꿔, 미러의 착지 팩터가 미등록(검증 에러→부분 컴파일 드롭으로 생존)에서 등록 팩터(검증 통과→전량 컴파일 폭발)로 이동하며 발현. 온도 0에서 결정적 재현). 검증 에러가 있으면 부분 컴파일이 해당 조건만 제외하고 "'…' 조건은 전략에 반영하지 못했어요" 안내를 붙인다. ③ **미러와 실제 발화를 구분한다** — 역할 위반 청산 조건이 진입에 이미 있는 팩터의 복제이면서 원문 근거(`source_text`)가 없으면 9B 미러 드리프트로 보고 **에러·안내 없이** 검증이 제거한다(진입에 정상 반영된 같은 지표가 "반영하지 못했어요"로 읽히던 실측 혼란, 2026-08-05 2차 수정). 원문 근거가 있거나 진입에 없는 팩터는 사용자가 실제로 말한 청산일 수 있으므로 ②의 에러+안내 경로를 유지한다(조용한 누락 금지). 회귀: `backend/tests/test_strategy_conversation.py`(risk 필드 흡수 2건, 미러 무안내 정규화 1건, 실발화 재무 청산 안내 1건).

**FR-STR-019u** [명시한 매매 규칙의 조용한 소실 차단, 2026-08-05] 전수 예시 QA(81개)가 드러낸 규칙 소실 3종을 각 레인의 원인에서 수정한다. ① **자기 선(線)을 둘 가진 지표의 부등호는 임계값을 요구하지 않는다** — `technical.ema`의 `>`·`<`는 "5일 EMA가 20일 EMA 위/아래"라는 두 선의 관계이고 컴파일러도 값 없이 `mode`(above/below)로 바인딩한다(`_compile_technical`). 완결성 검증이 이를 임계값 누락으로 보면 조건이 값 미정으로 제외돼 사용자가 명시한 진입·청산이 통째로 사라진다. 판정 기준은 spec에 `short_period`·`long_period`가 함께 있는지다. ② **미러 복제 판정은 방향으로 한다** — 반대 방향 청산은 교차(`crosses_*`)뿐 아니라 부등호로도 표현되므로(`>` 진입 / `<` 청산), 예외를 이벤트 연산자에만 열어 두면 정당한 청산이 미러로 오인돼 삭제된다. 연산자를 up/down으로 환산해 진입 방향과 다르면 새 정보로 보존한다(같은 방향 복제는 종전대로 삭제). ③ **되묻기 판정은 값이 담긴 버킷을 모두 본다** — 거래대금은 `fundamental.trading_value`(필터)와 `technical.trading_value`(신호) 두 정본을 가지며 후자로 해석되면 값이 `entry_signals`에 담긴다. 필터 버킷만 조회하면 사용자가 이미 준 값을 다시 묻는다(값이 없는 신호는 종전대로 되묻는다). 부수: LLM이 내는 낱말 연산자(`above`/`below`/`golden_cross`)를 정본 표기로 형식 정규화하고(`_OPERATOR_ALIASES` — 표기만 보고 결정 가능한 동의어), 프롬프트에 예시 4-6(재무 여러 개 뒤에 오는 숫자 없는 기술 신호)·4-7(진입과 반대 방향 청산, 정본 연산자 표기)을 추가해 리콜 누락을 LLM 레인에서 잡는다(PROMPT_VERSION 2.7). 회귀: `test_strategy_conversation.py`(반대 방향 청산 보존, 자기 선 비교 무임계값), `test_nl_parser_overrides.py`(값 있는 신호 인정, 값 없는 신호 되묻기 유지).

**FR-STR-019v** [스칼라 슬롯 미러 흡수 전면화, 2026-08-06] FR-STR-019t ①의 흡수 판정을 risk_management 정확 표기에서 **스칼라 설정 슬롯 전체**로 넓힌다(`interpreter/models.py::_absorb_scalar_slot_conditions` + `_scalar_slot_target`). 배경 사고 2건: 인터프리터가 `portfolio.hold_period_days=25`를 정상 반영하고 **같은 사실을** 조건 목록에 factor=`hold_period_days`(맨 이름)·`portfolio.hold_period_days`로 한 번 더 실어, Registry 부재로 컴파일에서 드롭된 복제가 "'보유는 최대 25거래일' 조건은 전략에 반영하지 못했어요"라는 **거짓 미반영 안내**를 만들었다(40거래일 케이스 동일). 트레이스 전수 조사(4일치 조건 관측 2,366건)에서 Registry 밖 factor는 7종뿐이고 6종이 이 미러였다: `risk_management.stop_loss`(1)·`stop_loss`(8)·`fundamental.stop_loss`(4, 오염 네임스페이스)·`portfolio.hold_period_days`(8)·`hold_period_days`(8)·`time.days_held`(16, 프롬프트 금지에도 출력). 나머지 1종(`technical.beta`)만 진짜 미지원 개념으로 안내가 정당하다. 계약: ① 판정 대상은 risk_management·portfolio·backtest 세 스펙의 필드 — 네임스페이스 정확 표기, 유일한 맨 이름, 그리고 마지막 세그먼트 재조회(오염 네임스페이스 대응. Registry 정본 id 68종의 마지막 세그먼트와 무충돌 확인). 동의어 `days_held`/`max_holding_days`→`portfolio.hold_period_days`는 표기만으로 결정 가능한 형식 정규화다. ② 맨 이름 `period`는 제외 — 지표 파라미터 이름과 겹쳐 흡수하면 사용자가 말한 적 없는 백테스트 창을 지어낸다. ③ 값 흡수는 대상 스펙의 자체 검증(`model_validate`)을 통과할 때만 — RiskSpec 크기 규약·BacktestSpec 버킷 정규화가 그대로 적용되고, 검증 실패 값은 흡수하지 않고 조건으로 남겨 안내 레인으로 보낸다. ④ 값도 없고 슬롯도 비어 있으면 제거하지 않는다(조용한 누락 금지 — 종전과 동일). universe(리스트형)·ranking 미러는 관측 0건 + ranking 정본 팩터는 capability_validator가 이미 ranking 배열로 정규화하므로 이번 범위 밖. 회귀: `test_strategy_conversation.py` 7건(맨 이름·빈 슬롯 흡수·backtest 흡수·`period` 비흡수·무값 보존·`time.days_held`·오염 네임스페이스).

**FR-STR-019w** [되묻기 질문 문구·칩의 단일 정본 + 표현 통일, 2026-08-16 사용자 지시] 사용자에게 던지는 **질문의 문구와 선택지 칩**은 `backend/engine/strategy_slots.py` 하나가 authoring해야 하며(FR-STR-019m이 *판정*을 모은 것과 같은 계약의 문구 판), 질문은 경로와 무관하게 **같은 되묻기 카드(박스)** 로 표시해야 한다. 배경: 같은 유니버스 질문 하나가 네 벌로 갈려 있었다 — ① 정본 표(`_QUESTIONS`, 칩 2개) ② 프론트 게이트 표(`backtestReadiness.SLOT_PROMPTS`, 칩 4개) ③ 빌더(`intent/strategy_builder.next_question`, 칩 5개) ④ 렌더 직전 치환표(`makeBuilderQuestionFriendly` — ①②의 문장을 통째로 다른 문장으로 갈아끼움). ④ 때문에 **표에 적힌 문구가 화면 문구가 아니었고**, 한쪽만 고치면 치환이 조용히 빗나가 낡은 문구가 나갔다. 표시도 갈렸다 — 게이트 질문은 박스 카드(하단 고정·'대화 종료' 포함), 빌더 질문은 맨 텍스트+칩이라, 열린 추천(STRATEGY_PICK)으로 들어온 사용자는 같은 성격의 첫 질문을 다른 모양으로 받았다. 계약: ① **문구 정본은 백엔드 하나** — `_QUESTIONS`(슬롯 9종) + `BUILDER_QUESTIONS`(빌더 세부 질문)가 **화면에 나갈 최종 문구**를 그대로 담고, 상황별 변형(분위 그룹·랭킹의 '최대 보유')도 같은 표의 변형 항목이다(`slot_question(field, variant)`). ② **프론트는 정본이 생성한 픽스처만 읽는다** — `scripts/export_slot_prompts.py` → `app/analytics/new/__fixtures__/slot-prompts.json`, 최신성은 `test_strategy_slots.py::test_frontend_prompt_fixture_is_current`가 잠근다(판정 픽스처 `slot-judgments.json`과 같은 방식). 픽스처는 손으로 고치지 않는다. ③ **칩 어휘는 두 레인의 답 해석기가 모두 읽을 수 있어야 한다** — 빌더 레인(`strategy_builder._parse_*`)과 게이트 레인(프론트 `deterministicConditionFlow`). 한쪽만 읽는 표기를 넣으면 그 레인에서 클릭이 조용히 LLM 왕복으로 떨어진다. 통합 결과 유니버스 칩은 5종(코스피·코스닥·코스피200·코스피·코스닥 전체·ETF), 리밸런싱·손절·익절 거부 칩은 자기완결 표기(`리밸런싱 안 함`·`손절 안 함`·`익절 안 함`)로 통일한다(카드가 하단에 고정되면 질문과 칩이 떨어져 "안 함"만으로는 무엇을 거부하는지 알 수 없다). 이전 표기는 프론트 해석 맵에 별칭으로 남긴다(세션에 남아 있던 이전 질문의 칩도 같은 결과여야 한다). ④ **'직접 입력'은 답이 아니라 UI 토글**이므로 어느 표에도 넣지 않는다 — 프론트 `withBuilderNavigationSuggestions`가 붙이며, 유니버스처럼 선택지가 닫힌 슬롯에는 붙이지 않는다. 되묻기 카드는 빌더 질문에 자유 입력 칩을 **덧붙이지 않는다**(두 판정이 겹치면 닫힌 선택지에 '직접 입력'이 되살아난다). ⑤ **빌더 질문은 되묻기 채널로 나간다** — `clarification`/`clarificationSuggestions`(안내문·연구 지표 도입부 같은 질문 아닌 앞말만 `infoText`). 채널을 모으면 박스·칩 규칙·하단 고정·'대화 종료' 배치가 저절로 같아진다. 되묻기 카드는 `msg.parsed` 유무와 무관하게 그려야 한다(빌더 턴에는 아직 전략이 없다). 부수 효과: 카드는 **지금 답할 질문 하나만** 그리므로 답이 끝난 빌더 질문은 대화에서 사라진다(게이트 레인의 기존 동작과 동일 — 정해진 내용은 '현재까지 이해한 전략입니다' 요약 카드가 잇는다). ⑥ **빌더 질문의 답은 빌더가 받는다** — 두 레인의 칩이 같은 필드에 담기므로 `handleSuggestionClick`이 `builderQuestion`으로 갈라놓지 않으면 게이트의 결정론 적용이 빌더 단계의 답을 가로채 State가 갈라진다. ⑦ **어느 질문인지의 판정은 문구 대조로** 한다 — 문구 안의 낱말("청산 조건"·"리밸런싱")로 보면 정본이 표현을 바꾸는 순간 판정이 조용히 헛돈다(테스트 포함). 회귀: `test_strategy_slots.py`(픽스처 최신성, 빌더·게이트 문구 동일성), `page.strategy-pick-notice.test.tsx`(열린 추천 경로의 첫 질문이 박스 카드로 나가고 안내문은 카드 밖). **[2026-08-16 2차 — 빌더 '전략 유형' 질문 폐지]**: 1차 통합 후에도 빌더는 매수 조건 자리를 자기 질문("어떤 방식으로 종목을 고를까요?" + 유형 설명 불릿 8줄 + 유형 이름 칩)으로 물어, 사용자가 같은 슬롯을 경로에 따라 전혀 다른 화면으로 받았다(불릿과 칩이 같은 목록의 중복 표기이기도 했다). 빌더의 전략 유형 단계를 없애고 ENTRY 슬롯 질문·칩을 그대로 쓴다. ⑧ **칩 어휘 통일이 불가능한 지점을 결속으로 푼다** — 정본 칩을 빌더 정규식에 다시 통과시키면 표기 겹침으로 오분류된다(실측 3종: 'MACD 골든크로스 매수'→golden_cross, '골든크로스(5일/20일)'의 5→모멘텀 기준 기간, 'PER 10 이하'→미인식 무한 재질문). 어휘를 덧붙여 가려내는 것은 대원칙 1이 금지하는 방향이고 겹침도 남는다. 그래서 칩=값 결속 계약대로 **클릭을 재해석하지 않고** 발행 시 정해진 값을 적용한다(`strategy_builder._ENTRY_CHIP_PATCHES`, 정확 일치만·성립하지 않아 내놓지 않은 칩은 결속 거부). 값은 게이트 레인의 결속과 **같은 전략**이 되도록 맞춘다 — 게이트가 엔진 기본값에 맡기는 파라미터(이동평균 종류·RSI 기간·OBV 기간)도 함께 결속해, 같은 칩이 경로에 따라 다른 전략이 되지 않게 하고 빌더가 뒤이어 되묻지도 않게 한다. ⑨ **빌더 상태가 표현할 수 없는 칩은 자유 서술로 넘긴다** — 재무 조건(PER·ROE)은 `BuilderState`에 자리가 없으므로 `strategy_type=custom` + `entry_rule`로 두어 프론트가 파서 레인으로 보낸다(칩을 목록에서 빼면 다시 두 벌이 된다). ⑩ **모멘텀(상위 K)은 정본 목록에 합류한다** — 빌더에만 있던 선택지라 통합 시 사라질 뻔했다. 게이트 레인도 같은 칩을 쓰므로 랭킹 결속(`ranking_metric`·`ranking_lookback_days`)을 프론트 결정론 적용에 추가한다. ⑪ **성립하지 않는 선택지만 정본에서 뺀다**(`strategy_slots.entry_chips` — ETF는 기업 재무 칩 제외, 단일 종목은 횡단면 랭킹 제외). 레인별 목록을 새로 만들지 않는다. ⑫ **되돌아가기는 답이 아니라 컨트롤**이므로 칩 목록에서 빼고 되묻기 카드 우상단 '돌아가기' 버튼으로 통일한다(게이트 레인과 같은 자리). 회귀 추가: 정본 칩 전수 결속·소화 보증(백엔드/프론트 양쪽), ETF·단일 종목 제외 목록, 돌아가기 버튼. **[2026-08-16 3차 — 매도 칩을 매수 칩의 반대로]**: ⑬ 같은 슬롯 쌍(매수·매도)의 선택지는 **서로 뒤집은 짝**이어야 한다(사용자 지시). 매도 칩 3종만 있던 것을 매수 칩과 같은 순서의 미러로 채운다 — 골든크로스→데드크로스, RSI 과매도→과매수, MACD 골든→데드, 볼린저 하단→상단, 고점 돌파→저점 이탈(대응 없는 '20일 보유 후 청산'은 기간 기반 청산이라 끝에). 문구만 맞추면 '반대'라는 설명이 거짓이 될 수 있으므로 **두 칩이 실제로 결속되는 값을 대조**해 지표·기간이 같고 방향만 다른지 회귀로 고정한다. ⑭ **미러를 넣지 못하는 세 경우와 그 이유**: 거래량 급증 — 엔진은 OBV 하락 전환 매도를 지원하나 파서에 그 매도 표현이 없어 칩이 값에 결속되지 않는다(결속 안 되는 칩은 planner ask 경로에서 조용히 사라져 같은 슬롯이 경로마다 다른 선택지를 보인다. 어휘를 덧붙여 결속시키는 것은 대원칙 1 금지 방향이므로 하지 않는다) / 모멘텀 상위 — 랭킹 전략의 청산은 매도 신호가 아니라 리밸런싱 편출이다(FR-BT-015b) / PER·ROE — 재무 지표는 청산 조건이 될 수 없다(역할 검증, FR-STR-019t ②). 노출하는 매도 칩이 **하나도 빠짐없이** 결속되는지를 회귀가 지킨다. [2026-08-23 요약 카드는 최신 한 장만] 진행 상태를 잇는 전략 요약 카드(`BuilderStrategyOverview` — '현재까지 이해한 전략입니다')는 **대화에서 가장 아래(최신) 한 장만** 그려야 한다. 빌더 턴마다 새 assistant 메시지가 붙고 각자 요약을 들고 있어, 메시지별로 그리면 같은 제목의 카드가 대화에 쌓인다(열린 추천 안내가 첫 턴에 붙자 안내 위·아래로 카드가 두 장 보였다). 카드는 지나간 턴의 기록이 아니라 **지금 상태**이므로 ⑤의 '답이 끝난 질문은 사라지고 정해진 내용은 요약 카드가 잇는다'와 같은 계약이다. 구현: `latestBuilderPresentationIndex`로 두 렌더 자리를 모두 잠근다. 회귀 `app/analytics/new/page.builderSummaryCard.test.tsx`.

**FR-STR-019w-1** [선택지 묶음 표시 + 자유 입력창 앞세우기, 2026-09-04] 정본 칩 목록에 성격이 다른 칩이 섞여 있으면(매수 조건: 시점 신호·순위로 담기·종목 필터) 프론트는 묶음 소제목으로 갈라 **표시만** 바꾼다 — 묶음 정본은 `app/analytics/new/choiceOptionGroups.ts`이고 키는 칩 문자열 그대로이며, 칩 문구·값·순번(묶음을 가로질러 연속)은 바꾸지 않는다(FR-STR-019w의 단일 정본 계약 유지). 묶음이 둘 이상 드러날 때만 묶고, 정본에 없는 칩은 제목 없는 꼬리 묶음으로 보존한다. 묶인 목록은 '직접 입력' 칩 대신 자유 입력창을 칩 위에 처음부터 열어 둔다(필터+신호 조합은 칩 하나로 고를 수 없으므로 자유 서술이 진입로다); 입력창의 답은 칩 답과 같은 경로로 보낸다. 평평한 목록의 '직접 입력' 칩 동작(FR-SA-002c의 칩 노출 중 하단 입력창 숨김)은 그대로다.

**FR-STR-019w-2** [되묻기 카드 '돌아가기'의 경로 무관 보장, 2026-09-04 사용자 지시] 되묻기 카드의 '돌아가기'는 카드를 만든 경로와 무관하게 있어야 한다. 이전에는 칩으로 답한 턴(게이트 레인)과 빌더 턴에만 붙고, 자유 서술('직접 입력')로 답하거나 처음 전략을 적어 넣어 **파스를 거친 턴**의 카드(예: 리밸런싱 방식 질문)에는 되돌릴 상태가 남지 않아 버튼이 없었다. 파스 레인은 파스 **전** 상태(parsed·provenance·거부 목록·백테스트 요청·변경 이력·필드 상태/메타·Artifact·pending_ask·원문)를 카드에 남기고, '돌아가기'는 그 카드와 그 답(직전 사용자 버블)부터 끝까지 지운 뒤 상태를 통째로 되돌린다 — 변경 이력에 지운 턴이 남거나 다음 파스 요청이 지운 턴의 상태를 에코하면 안 된다. 열린 되묻기 기록(`pending_question` 에코)도 되돌아온 카드의 질문으로 되돌린다(남기면 다음 자유 답변이 지워진 질문의 답으로 해석된다). 최초 파싱의 첫 질문에서 돌아가면 되돌아갈 전략이 없으므로 대화를 비우고 적어 넣은 원문을 입력창에 되돌린다. 회귀: `page.back-after-parse.test.tsx`.

**FR-STR-019x** [억원 단위 지표의 '조' 환산 계약, 2026-08-18] 정본 단위가 **억원**인 지표(`fundamental.market_cap`·`trading_value`·`net_income`·`ebit`·현금흐름 3종 등)의 임계값은 억원 단위 숫자여야 하며, '조'는 ×10,000으로 환산한다("1조"=10000, "2조 5000억"=25000). 사고: "시가총액 1조 원 이상"에 인터프리터 9B가 `value=100000`을 냈고(억원 기준 10조 — 사용자 요청의 10배), 검증·컴파일·표시가 모두 그 값을 정직하게 옮겨 요약 카드에 `시총 >= 10조`로 나갔다. 값 자체는 범위(0~10,000,000억) 안이라 파라미터 검증에 걸리지 않는다. 수치 대조(`recall_validator._candidates` — '조'는 맨값을 후보에서 제외)는 이 오변환을 **탐지**하지만 재생성 요청은 2026-08-07 폐지됐고 잔여 안내도 2026-08-01 폐지됐으므로, 실제 방어선은 1차 프롬프트뿐이다. 대응: 원 단위 금액 규칙(11-2, 초기자금)과 **단위가 다르다는 사실을 명시한** 억원 환산표를 프롬프트 규칙 11-2-1로 신설한다(PROMPT_VERSION 3.8). 결정론 후처리로 값을 10배 나누는 보정은 하지 않는다 — 대원칙 1의 금지 사항(검증 실패 시 임의 보정)이며, 지표별 단위를 원문에서 되짚는 순간 해석 레인 침범이다. 회귀: `test_recall_validator.py::test_prompt_states_eok_unit_conversion_for_amount_factors`(프롬프트 계약), 라이브 실측 4/4(시총 1조/2조5000억/5000억, 거래대금 50억, 초기자금 3억원과 시총 1조 혼재 문장 포함). **② 예시 QA 게이트는 임계값까지 대조한다** — 이 사고는 예시 40번("대형주 PBR·ROE 월간 조건")에서 났고 2026-08-14 전수 검증(81개)에 포함돼 있었는데도 `치명 0`으로 통과했다. 원인은 커버리지 검사가 `_has_fund`로 **지표 존재만** 보고 값을 읽지 않은 것이다(하니스 정제판이 SL/TP 값 대조를 오탐 때문에 걷어낸 뒤 값을 비교하는 항목은 종목 수 하나뿐이었다). 파싱 캐시의 git 이력은 같은 문장이 프롬프트 변경마다 10000↔100000을 오갔음을 보여준다(07-28 정상 → 08-05·08-07 오류 → 08-08 정상 → 08-14 오류) — 값을 보지 않는 게이트가 매번 초록불을 켰다. 대응: 금액 임계값(시가총액·거래대금)을 **QA 쪽 ground truth**(`expected_amount_thresholds` — `nl_parser._extract_amount_value`의 조×10,000+억 산술 합산, ETF 테마 기대값과 같은 자리)와 대조해 어긋나면 치명으로 세운다. 기대값 추출이 지표명 뒤 금액 하나만 잡으므로 대조는 **기대값이 파싱 결과에 포함되는가**로만 하고(상·하한 예시의 부분 추출 오탐 방지), 지표 자체가 없는 경우는 미탐지 레인(되묻기 예외 포함)에 맡겨 이중 계수하지 않는다. 회귀: `test_qa_template_detect_verdict.py`(자릿수 오차 치명·정상 무판정·부재 침묵·부분 추출 무오탐·환산 정확도 5건). **③ 대조 대상은 '모든 값'이다**(2026-08-18 사용자 지시 — "모든걸 얼마인지 확인해"). 금액만 보면 같은 유형이 다른 지표에서 그대로 재발하므로 세 층으로 넓힌다: ⓐ **재무 임계값 전부**(PBR·PER·ROE·부채비율… `expected_fundamental_thresholds`) ⓑ **스칼라 설정**(손절·익절·리밸런싱 주기·보유기간·백테스트 기간·초기자본·트레일링·MDD — `expected_scalar_values`, 결정적 추출기가 이미 있는 항목은 그대로 QA 정본으로 쓴다) ⓒ **신호 수치**(이동평균 기간·신고가 룩백·오실레이터 기준값 — `expected_signal_numbers`). ⓒ의 대조는 **지표 귀속을 판정하지 않는다**: 지표별 추출기를 쓰면 한 문장에 지표가 둘 이상일 때 옆 지표의 숫자를 집어 온다(실측 오탐 — `_extract_technical_signals`가 volume_spike 기간을 5로 기대). 하니스 초판이 값 대조를 통째로 걷어낸 이유가 이것이므로, 단위 어휘에 붙은 숫자만 읽고 "그 숫자가 신호 어딘가에 남았는가"만 본다(포함 대조). '20일 평균 거래대금 30억'의 창(20일)은 지표 정의에 내장돼 파싱 필드에 자리가 없으므로 대조 대상에서 제외한다(정상 예시 3건이 붉어진 실측). 넷째 층으로 **미대조 수치**(프롬프트의 숫자 중 전략 어디에도 없는 것)를 참고 표시로 남겨 어느 그물에도 안 걸리는 값이 없게 한다(서수·횟수가 정상적으로 남지 않으므로 게이트는 붉히지 않는다). 종목 수는 기존 `intended_positions` 검사가 값을 대조하므로 중복 계수하지 않는다. **넓힌 대조가 실제로 찾아낸 결함이 FR-STR-019y다** — 81개 전수에서 오탐 0·진짜 결함 5건. **④ 잉여(중복) 대조**(2026-08-18 추가): ①~③은 전부 결손 방향(빠졌나·값이 틀렸나)이라 "남는 게 붙었나"를 보지 않았고, 예시 51('EMA 데드크로스 청산')이 `exit_signals`에 완전히 같은 신호 2개로 파싱된 채 08-17 전수 검증을 치명 0으로 통과했다 — 리포트 요약엔 '청산=ema,ema'로 찍혀 있었지만 판정 항목이 아니었다(원인은 9B가 청산을 두 조각으로 내고 결정론 교정이 둘을 같은 신호로 수렴시킨 것 — capability 검증의 동일 조건 중복 제거로 수정). 같은 역할(진입 신호·청산 신호·재무 조건) 안에서 **모든 필드가 같은** 조건이 반복되면 치명으로 세운다(`duplicated_conditions` — null 필드는 없는 것으로 보고 비교, 지표·기간·연산자·값이 하나라도 다르면 다른 조건). 회귀: `test_qa_template_detect_verdict.py`(동일 청산 중복 치명·상이 기간 무판정 2건). 캐시 재판정으로 예시 51만 붉어짐을 확인한 뒤 라이브 재파싱으로 초록 복귀(81/81 치명 0).

**FR-STR-019y** [사용자가 이름 붙여 부른 선의 소실 차단, 2026-08-18] 이동평균 조건에서 **사용자가 말한 기간**은 엔진까지 그대로 도달해야 하며, 말하지 않은 기간이 만들어져서는 안 된다. 예시 QA 값 대조(FR-STR-019x ③)가 81개에서 찾은 결함 5건은 모두 이 계약 위반이었고, 원인은 세 레이어에 나뉘어 있었다. ① **컴파일러가 두 번째 선을 버렸다** — `ema`의 부등호를 무조건 '가격 vs EMA 하나'(`mode=above/below`)로 접으면서 `short_period`를 지워, "20일 EMA가 60일 EMA 위에 있는"이 "가격이 60일 EMA 위"라는 다른 전략이 됐다(예시 22·26·80). 판정을 **LLM이 실제로 채운 파라미터**로 바꿔(registry 기본값으로 판정하면 없던 선이 생긴다) 두 기간이 다 주어지면 두 선의 관계로 컴파일한다. ② **컴파일러가 없는 선을 만들었다** — 한 선만 주어졌을 때 나머지 칸을 registry 기본값(20/60)으로 채워 "20일 EMA 이탈"이 20/60 교차가 되거나 20/20 자기 교차(영원히 발화하지 않는 청산)가 됐다. 한 선만 있으면 상대는 종가이며, 그 사실은 기간이 아니라 '선이 하나뿐'이라는 형태가 말한다(`short_period=None`). ③ **엔진 변환기가 기간을 읽지 않았다** — 컴파일러는 단일 선의 기간을 `long_period`에 담는데 `strategy_converter`는 `period`만 읽어, 가격 vs EMA 조건이 사용자가 말한 기간과 무관하게 **항상 20일**로 백테스트됐다(엔진 v16.0 — 결과값 변경). ④ **인터프리터 출력 보정**(`_fill_deterministic_condition_params`): 조건의 인용(source_text)이 두 선을 모두 부르는데 기간이 하나면 인용대로 복원하고, 한 선만 부르는데 인용에 없는 기간이 있거나 두 기간이 같으면 그 지어낸 숫자만 걷어낸다 — **새 숫자는 만들지 않는다**(상태/교차 구분은 LLM이 낸 연산자가 이미 말한다). 입력은 사용자 원문이 아니라 LLM이 스스로 남긴 짧은 인용이므로 § 3-2 지식 조회다(`_explicit_breakout_lookback`과 같은 자리). ⑤ **신고가 룩백은 인용이 이긴다** — 인용이 기간을 명시했는데 파라미터가 다르면 파라미터가 틀린 것이다(수정 패치 `_quote_contradicts_value`와 같은 계약: LLM 출력 두 조각의 대조). 종전 가드가 값이 `None`일 때만 채워, 인용은 '20일 신고가 돌파'인데 `lookback_period=10`인 조건이 그대로 통과했다(예시 18). ⑥ **'위에 있는'은 상태이고 '돌파'는 이벤트다** — 종전에는 두 EMA의 지속 상태를 엔진이 표현할 수 없어, 기간을 살리면 교차 이벤트(정배열 내내 참이어야 할 조건이 교차 당일 하루로 축소)가 되고 상태로 옮기면 한 선을 버려야 했다. 엔진에 두 EMA 상태 평가를 신설하고(`ema` + 두 기간 + `mode=above/below`, 벡터·행 경로 동일 의미, 엔진 v16.0) 컴파일러가 부등호를 **기간을 버리지 않고** mode로 옮긴다. ⑦ **EMA를 말했으면 지표도 EMA다** — 엔진에서 `ma_crossover`는 단순이동평균(`close_N_sma`), `ema`는 EMA 컬럼을 쓴다. 프롬프트 규칙 5-3에 '종가 vs EMA' 표기가 없어 SMA 예시를 그대로 가져오는 드리프트가 있었고(예시 26·53), 규칙을 보강(PROMPT_VERSION 3.9)한 뒤에도 남는 드리프트는 인용이 EMA를 지목하면 factor를 되돌리는 선언 기반 정규화로 막는다(`_quotes_ema`). ⑧ **종가 표기는 두 지표가 같다** — `ema.short_period` 최소값이 2여서 정본 표기(`short_period=1`=종가)가 검증 오류가 됐고, 그 오류는 안내도 질문도 없이 **부분 컴파일로 조용히** 흘렀다(실측 `오류=1`인데 notices·clarification 모두 비어 있음). `ma_crossover`와 같이 최소값 1로 맞춘다. ⑨ **EMA 관용 표현도 EMA 잎에 착지한다** — '골든크로스/데드크로스'는 개념(`concept.*_cross`)으로 착지하고 그 전개 대상이 SMA라, "EMA 데드크로스가 나오면 청산"이 단순이동평균 교차가 됐다(⑦의 두 번째 경로 — 잎 조건만 보던 가드가 개념 경로를 지나쳤고, 숫자 5/20은 그대로라 값 대조 게이트도 통과했다. 예시 29·51·64·73·77). 인용이 EMA를 지목하면 개념을 EMA 잎으로 착지시키고 **개념 선언의 정본 기간(5/20)은 빈 자리에만** 옮긴다(잎 기본값 20/60으로 떨어지면 사용자가 말한 적 없는 기간이 된다). EMA를 말하지 않은 '골든크로스'는 종전대로 SMA다. ⑩ **다른 슬롯의 문구로 만든 매매 신호는 뺀다** — "최대 보유 기간은 25거래일"을 인용으로 달고 이동평균 청산 조건이 만들어졌다(예시 73): 인용이 입력에 실재하므로 출처 대조(FR-STR-019f ③-1)를 통과하고, 값 대조도 숫자만 보므로 통과한다. 이동평균 조건인데 ⓐ 인용에 이동평균 어휘가 하나도 없고 ⓑ 인용이 이미 제 자리를 가진 설정(보유 기간·손절·익절·종목 수·리밸런싱·초기자금 등)의 문구면 근거 없음으로 보고 **안내와 함께** 뺀다. ⓑ를 함께 요구하는 이유는 '추세가 확실히 잡힌 종목만'처럼 **정성 표현을 이동평균으로 매핑하는 것이 정당한 해석**이기 때문이며(프롬프트 규칙 2), ⓐ만으로 자르면 이 가드가 막으려던 조용한 소실을 스스로 일으킨다(실측 오탐). 슬롯 어휘 중 숫자를 요구하는 항목('종목'·'보유')은 숫자가 붙어 있을 때만 인정한다 — 낱말만으로 보면 전략 서술 어디에나 나온다. **리스크 항목은 어순을 가리지 않는다(2026-09-16)**: 종전 판정이 '손절→숫자' 한 방향만 봐서 "데드크로스가 나오거나 **-8% 손절 시 매도**하는 전략"의 손절 구절을 인용한 `ma_crossover(1,20)` 청산 조건이 그대로 통과했고(재표본 3/3, 손절 -8%는 제 칸에 정상 반영된 채로 **이중 생성**), 화면에는 사용자가 말한 적 없는 '종가가 20일선 하향 이탈'이 매도 조건으로 떴다. 어휘는 늘리지 않고 방향만 양쪽으로 연다 — '20일선 이탈 시 손절'처럼 인용에 이동평균 어휘가 있으면 ⓐ에서 이미 빠져나가므로 정당한 청산은 닿지 않는다. **인용이 입력 전체이고 같은 출력이 다른 칸도 채웠으면 이 판정에 보내지 않는다(2026-09-17)**: 120B가 문장 전체를 인용으로 단 `ma_crossover(1,20)` 매수 조건을 지어냈고, 이 가드가 조건을 빼면서 "'<문장 전체>'는 이동평균 조건이 아니어서 매매 신호로 반영하지 않았어요"를 내 **사용자 문장을 통째로 되돌려주고 말한 적 없는 내부 분류를 노출**했다(같은 턴 조건 구절 나열은 빈 목록). 같은 출력이 랭킹·종목 수·리밸런싱·손절·기간·자본·유니버스 중 하나라도 채웠다면 입력 전체는 조각이 아니므로 규칙 4의 **출력 형식 위반**이다(조건 하나뿐인 입력은 입력 전체가 정당한 조각 — 사용자 결정 (a), 출력 필드의 값 존재만 대조). ⓐ 인터프리터가 생성 턴에서 스키마 수리와 같은 1회 예산으로 오류를 되돌려 재생성하고(재생성본이 스키마를 깨면 원출력으로 진행) ⓑ 그래도 남은 조건은 출처 대조 가드가 **안내 없이** 빼 Trace에만 남긴다(사용자 결정 A안). 사용자가 말한 랭킹·손절·종목 수·리밸런싱·기간·자본은 그대로 보존된다. **⑩ⓐⓑ와 신고가 오분류 교정(⑦ 계열)의 판정 근거는 LLM의 조건 인용 대조다(2026-09-17 이관)**: 종전 한국어·영어 어휘 정규식(`_MA_VOCAB_RE`·`_OTHER_SLOT_VOCAB_RE`·`_BREAKOUT_QUOTE_RE`·`_BOLLINGER_VOCAB_RE`)은 인용의 의미를 판정하는 대원칙 1 위반이라 삭제했다. `interpreter/quote_check.py`가 이동평균·볼린저 조건마다 조건을 평이한 한국어로 옮겨 적어 보여주고("매도 — 5일 이동평균선이 20일 이동평균선을 아래로 교차하면") 항목마다 `expresses`(yes/no/unclear)·`describes`(moving_average/bollinger/new_high_breakout/other) enum을 받는다. 결정론은 enum 소속만 본다: 분명한 no만 안내와 함께 제거(인용 25자 초과면 따옴표 없이 일반 문구), new_high_breakout이면 breakout 교정, unclear·enum 밖·호출 실패는 판정 없음(교정·제거 안 함, 정규식 폴백 없음). 호출은 그런 조건이 있는 생성 턴(트레이스 실측 ≈49%)과 그런 조건이 새로 들어온 수정 턴만, 턴당 1회, planner-first 대기와 겹치게 메인 스레드에서. **칸 분류 질문 폐기(같은 날 9B 게이트 회귀)**: 첫 이관은 "인용이 어느 칸에 관한 말인가"를 라벨 목록으로 물었고, 로컬 9B가 "데드크로스가 나오면 매도"를 손절로 분류해 예시 67의 실제 청산 조건을 지웠다(치명 4/4, 같은 39호출 재생 시 실제 조건 12개 탈락 판정 — 이동평균 이탈 청산과 손절은 둘 다 '파는 말'). 조건 중심 질문으로 바꾼 뒤 같은 39호출(조건 66개) 9B 재생: 실제 조건 탈락 0, 알려진 조작 5건(13:30 문장 전체·'5종목'·'-15% 손절'·'-8% 손절 시 매도'·'최대 보유 기간은 25거래일') 전부 제거, 신고가 오분류 4건(KR 2·EN 1·게이트 실측 1) 전부 교정. **제거 조건 교정(2026-09-19, 120B 게이트)**: 분명한 no만으로 빼던 판정이 120B에서 멀쩡한 조건을 지웠다 — 예시 53 "20일 EMA를 이탈하면 청산"·"종가가 5일 EMA를 회복하는 시점"이 "이동평균 조건이 아니어서" 거짓 안내와 함께 사라져 청산 규칙 소실(게이트+재표본 4회 중 2회), 예시 8 "20일 이동평균선 근처"는 매수 조건 0개. 120B는 세부만 다른 이동평균 조건에 no/moving_average를 답한다. 제거는 **no이면서 describes=other**일 때만으로 좁혔다(프롬프트 불변, 결정론 술어만). 트레이스 재생(09-17~19 실제 대조 입력 42묶음·조건 72개, 모델별 2회): 120B 오제거 17/104→1/104·설정 문구 조작 제거 12/12 유지, 9B 오제거 2/106→0/106·조작 제거 12/12→**8/12**(9B가 '5종목'·'-15% 손절' 인용에 moving_average를 답함 — 알려진 후퇴). 기각안 둘: describes에 setting 라벨 추가(120B가 '손절 -8% 도달'에도 moving_average — 조작 제거 2~6/12), 인용 속 지표 낱말 옮겨 적기(9B가 설정 문구를 통째로 옮겨 조작 제거 0/12, 120B 호출 실패 3/86). 회귀: `test_strategy_conversation.py` 13건(두 선 보존·지어낸 기간 제거·자기 교차 수리·단일 선 상태 필터 불변·룩백 인용 우선·변환기 기간 전달·두 EMA 상태 보존·EMA 치환 교정·종가 표기 READY·EMA 개념 착지·SMA 개념 불변·슬롯 문구 신호 제거·정성 매핑 생존 — 슬롯·돌파 4+2건은 2026-09-17 스텁 LLM 조건 인용 대조 응답으로 개정) + 입력 전체 인용 6건(13:30 원출력 픽스처 — 1회 재생성 후 무안내 제거·설정 보존 / 재생성본 채택·질문 미복원 / 재생성본 스키마 붕괴 시 원출력 진행 / 수리 예산 공유 / 가드 단독 정규화 동일성 / 조건 하나뿐인 입력 무재생성·다른 칸 동반 시 재생성) + 조건 인용 대조 5건(예시 67 이동평균 청산 유지·설정 문구 조작 제거와 25자 상한·실패/unclear fail-open·호출 범위·생성 턴 배선), `test_engine_signals.py` 1건(상태는 지속·교차는 하루·역배열), `test_own_line_comparison_needs_no_threshold_value` 개정(부등호에 임계값을 요구하지 않는다는 본래 계약은 유지하고, 두 기간 보존으로 단언을 바꿈).

**FR-STR-019z** [지표 배지의 내부 이름 노출 금지 + 평균 거래대금의 레인, 2026-08-18] 전략 요약·결과 배지는 **어떤 경우에도 엔진 내부 식별자를 그대로 보여주지 않는다**. 사용자 신고: 진입 신호 배지에 `trading_value`가 변수명 그대로 노출됐다. 원인은 두 겹이다. ① **표시 레인** — `getSignalLabel`(`lib/strategy-summary.ts`)의 마지막 폴백이 `INDICATOR_LABELS`에 없는 지표를 원본 id로 되돌려 준다. 엔진 `TechnicalSignal.indicator` Literal은 17종인데 라벨 맵은 13종이어서 `trading_value`·`williams_r`·`mfi`·`roc` 네 지표가 노출 대기 상태였다(먼저 도달한 것이 거래대금이었을 뿐이다). 대응: 네 지표의 라벨을 채우고, 거래대금 신호는 임계 금액이 빠지면 조건을 읽을 수 없으므로 진입 게이트 배지와 같은 표기로 금액을 함께 싣는다(`거래대금 30억 이상`, 단위=억원). 라벨 맵이 엔진 Literal보다 뒤처지면 같은 누출이 새 지표마다 재발하므로 **대조를 게이트로 만든다** — `test_nl_parser_overrides.py::test_every_engine_indicator_has_a_frontend_badge_label`이 Literal 전체가 라벨 맵에 있는지 확인한다(수정 전 상태에서 실패함을 확인). ② **해석 레인** — 그 배지가 나온 이유는 스크리닝 조건이 신호 레인으로 갔기 때문이다. "최근 20일 평균 거래대금이 30억 원 이상인 종목만 대상으로 … 20일 신고가 돌파가 나오면 진입"에서 9B가 거래대금을 `technical.trading_value`(당일 하루치 트리거)로 냈다. `fundamental.trading_value`(일평균 스크리닝)와는 백테스트 의미가 다르다 — 하루라도 30억을 넘긴 날 진입 vs 20일 평균 30억 이상 종목만 편입. 라이브 재현(temperature 0) 결과 **두 '20일'이 겹칠 때만** 재현되고 돌파 기간을 50일로 바꾸거나 '일평균'으로 바꾸면 정상이었다 — 숫자 충돌로 두 조건을 같은 계열로 묶은 오분류다. 대응은 LLM 레인에서만 한다(대원칙 1 — 원문을 정규식으로 되짚어 레인을 뒤집는 안전망은 금지): registry 두 잎의 notes를 '기간 평균=fundamental / 당일 하루치=technical'로 가르고, 산문 규칙 5-2에 같은 문장을 넣고, **같은 형태의 예시 4-8**을 추가한다(PROMPT_VERSION 4.0). 산문 규칙만으로는 고쳐지지 않았다 — 예시를 넣은 뒤에야 정상화됐다(project_interpreter_output_shape_authority의 재확인). 검증: 라이브 4/4(신고 발화·일평균·최근 60일 평균·당일 트리거 — 트리거 케이스가 technical에 남는 것까지), 거래대금 포함 예시 25개 파싱을 QA 캐시와 대조해 **회귀 0**(차이 2건 — 신고 발화의 레인 교정과, 예시 23의 근거 없는 청산 신호 `ma_crossover`(전 필드 null) 소멸. 둘 다 개선 방향). 회귀 테스트: 위 라벨 대조, `strategySummary.test.ts`(거래대금 배지 금액 표기·내부 이름 무노출 3종), `test_strategy_conversation.py::test_prompt_routes_average_trading_value_to_the_screening_lane`(프롬프트 계약).

**FR-STR-019aa** [보유 기간을 '미지원'으로 신고하고 값을 버리는 사고 + 결손을 보지 않던 QA 게이트, 2026-08-18] 지원되는 설정은 미지원으로 신고되어서는 안 되며, 사용자가 말한 스칼라 값이 사라지면 QA 게이트가 붉어져야 한다. 발단: FR-STR-019z의 프롬프트 변경 검증 중 예시 32('손절 -7%, 보유 기간 상한 40거래일')의 보유기간이 사라졌다. ① **귀속**: 대조군 실험(HEAD + 같은 분량의 무의미한 문단)에서도 동일하게 소실 — 특정 문구가 아니라 **프롬프트가 조금이라도 흔들리면 문장 끝 조건이 밀려나는** 취약성이다. ② **정체**: 값이 그냥 사라진 것이 아니라 `unsupported_features=['최대 보유 기간 40거래일']`로 옮겨 갔다 — LLM이 스스로 '최대 보유 기간'이라 부른 개념을 프롬프트 규칙 5는 지원한다고 명시하므로 **두 출력 조각이 서로 모순**이고, 사용자에게는 지원되는 개념이 "지원하지 않아 반영하지 못했어요"로 안내된다(예시 55 '15거래일 정도만 보유'에서 그 안내가 실제로 나갔다). ③ **프롬프트 레인 3회 시도의 실측**: 미지원 목록에 '상한은 지원'을 덧붙이면 **악화**(정상이던 변형까지 소실), 규칙 5 표기 추가는 무효, 직접 부정문은 3건 중 2건만 회복. ④ **대응**: 모순 해소를 결정론으로 한다 — `primary._fill_deterministic_condition_params` ④가 미지원 신고 문구에서 (보유 동사 + 기간 수치)를 읽어 슬롯이 비어 있을 때만 채우고 그 항목을 미지원 목록에서 뺀다. 하한('최소 N개월'·'N개월 이상')은 실제 미지원이라 건드리지 않는다. 입력은 사용자 원문이 아니라 LLM이 스스로 낸 짧은 문자열이므로 § 3-2이며, '신고가 룩백은 인용이 이긴다'(FR-STR-019y ⑤)와 같은 자리다. ⑤ **게이트 두 구멍**(같은 사고가 81개 전수에서 `치명 0`으로 통과한 이유): 대조 루프가 `파싱값이 None이면 건너뛰기`라 **값 오차는 잡고 소실은 침묵**했고, 기대값 추출기가 '보유 기간 상한 N거래일'·'15거래일 정도만 보유' 표기를 읽지 못해 목록에 오르지도 못했다. 결손을 치명으로 세우고 두 표기를 검사 쪽에서 보완한다(제품 해석 경로의 어휘는 늘리지 않는다 — 대원칙 1). ⑥ **게이트를 조이자 기대값의 헐거움이 드러났다**: `_extract_hold_period_days`는 '최근 한 달 박스권'·'최근 3개월 상대강도'처럼 기간만 나오는 문장도 보유기간으로 읽어 오탐 4건을 냈다(두 결함이 서로를 가려 온 셈이다) — 기대값은 '보유 기간' 명사이거나 기간 표기 옆에 보유 동사가 있을 때만 세운다. 회귀: `test_strategy_conversation.py`(술어 9종·복구·하한 불변·기존 값 보존), `test_qa_template_detect_verdict.py`(소실 치명·정상 무판정·기대값 추출). 검증: 라이브 3/3(문장 끝 상한 복구·최대 표기·하한 음성대조), 예시 55 재파싱 `hold=15`+틀린 안내 소멸, 전수 81개 재판정 치명 0.

**FR-STR-019bb** [조건 누락 대조 패스 — 나열된 조건 중 하나가 밀리는 결함, 2026-08-18] 입력이 말한 조건은 전략·되묻기·미지원 중 **어딘가에는 반드시 남아야 한다**. 사고: "…시가총액 2000억 원 이상 종목에서 매출 성장률이 양호하고 PBR이 과도하게 높지 않은 기업만…"에서 PBR이 **조건에도 되묻기에도 미지원 목록에도 없이** 사라졌다(9B, temperature 0 재현). ① **성질**: 특정 지표나 정성 표현의 문제가 아니다 — 순서를 바꾸면 둘 다 나오고, PBR만 남기면 이번엔 시가총액(숫자 조건)이 빠지며, 문장이 짧아지면 정상이다. 나열된 조건 중 하나가 밀리는 **회수(recall) 결함**이며 보유 기간 소실(FR-STR-019aa)과 같은 계열이다. ② **막다른 길 셋**(전부 실측): 프롬프트 규칙 4-1을 넓히면 효과가 없을 뿐 아니라 무관한 예시의 보유기간이 무너진다 · `num_ctx`를 32768로 올려도 동일(컨텍스트 부족이 아니다) · 원문을 어휘 매칭해 되살리는 결정론은 대원칙 1 금지(원문 해석). ③ **2차 패스의 과제 설계가 핵심이다**: 1차 출력을 그대로 보여주고 "무엇이 빠졌나"를 물으면 9B는 `{"missing": []}`을 내고(차집합 판단 실패), 반대로 자유롭게 시키면 '추세가 확실히 잡힌 종목만'→`technical.roc`, 문장에 없는 AI 예측 조건까지 만들어 **없던 되묻기**를 낳는다. 그래서 LLM에게는 '조건을 말한 구절 나열'이라는 추출만 시키고 **대조는 결정론**이 한다(`interpreter/condition_recall.py`). ④ **되살리는 조건은 가드 4개를 모두 통과해야 한다**: 구절이 입력에 실재할 것(`_quote_has_echo` — 환각 조건 가드와 같은 대조) · 구절이 지표를 **이름으로 부를 것**(`indicator_registry.factor_ids_named_in` — 정성 표현의 지표 매핑은 1차 해석의 몫이고 이 패스는 되살리는 그물이지 해석하는 자리가 아니다) · 이미 다른 조건의 근거로 쓰인 구절 제외(결정론 보정이 지표를 바꾼 조건을 원래 지표로 되살려 같은 문구가 두 조건이 되던 실측) · registry가 아는 factor일 것. **값은 만들지 않는다**(MISSING으로 두고 되묻기 레인이 질문한다). 한 턴 회수 상한 3개. ⑤ **폐지된 '전체 재생성'(2026-08-07)과 다른 점**: 재생성은 1차와 같은 정보로 다시 만들게 해 47%가 바이트 동일이었다. 이 패스는 과제 자체가 다르고(나열), 1차 결과를 덮어쓰지 않는다(추가만 한다). ⑥ **배선·비용**: `primary.run_primary_parse`의 결정론 보정 뒤·환각 가드 앞. 생성 턴당 LLM 호출이 1회 늘고, prod 기본 on이다(2026-08-19 사용자 결정 — 롤백은 `STRATEGY_CONDITION_RECALL=off`). 주입 스텁(테스트·QA 하니스)은 chat 핸들이 없어 자동 비활성. 회귀: `test_strategy_conversation.py` 5종(회수·정성표현 차단·환각 차단·중복 근거 차단·형식 붕괴). 검증: 예시 81개 전수 **치명 0 · 미탐지 0**(직전 실행의 미탐지 1건이 이 패스로 해소). ⑦ **설정 슬롯도 같은 결함을 겪는다 — 백테스트 기간 회수(2026-09-16)**: "…손절은 -8%, 최대 5종목, **최근 1년**, 초기 자본 1000만원으로 백테스트해 주세요"에서 1차 해석이 기간만 빠뜨려(period=null) 사용자가 **이미 말한 값**을 되묻기로 다시 답해야 했고(같은 문장 API 재표본에서는 5y로 뒤바뀌기도 했다), 컴파일은 말한 적 없는 기본값 `5y`로 채웠다. 조건 회수와 같은 계약이다 — LLM은 '기간을 말한 구절'을 찾아 `<N>y`/`<N>m`/`full`로 **옮겨 적기만** 하고(FR-STR-019z 기간 표기 계약과 같은 형태), 결정론은 ⓐ 인용이 입력에 실재하는지 대조하고(`_quote_has_echo`) ⓑ 표기를 정본 버킷·날짜 창으로 정규화하며(`BacktestSpec`) ⓒ **이미 값이 있으면 절대 덮어쓰지 않는다**(빈 칸을 채우는 그물이지 1차 해석을 교정하는 자리가 아니다). 인용을 내지 않으면 채우지 않는다 — 대조할 수 없는 값은 되묻기에 맡긴다. 기간이 빈 턴에서만 호출하므로 대부분의 턴에는 추가 호출이 없다. 조건 추출 프롬프트에 얹지 않고 별도 프롬프트로 둔 이유는 프롬프트 분량 회귀 계약(FR-STR-019cc) 때문이다. 회귀: `test_backtest_period_recall_restores_a_dropped_period` 6단언(회수·덮어쓰기 금지·환각 인용 차단·무인용 차단·버킷 밖 날짜 창·형식 붕괴).

**FR-STR-019cc** [청산절이 매수 칸에 앉아 반대 방향 매수 신호로 뒤집히는 침묵 왜곡, 2026-09-08] 사용자가 매도 규칙으로 말한 조건은 exit_conditions에 착지해야 하며, 매수 칸에 앉은 매도 방향 교차 신호가 매수 신호로 컴파일되어서는 안 된다. 사고: KR 예시 81개 전수 게이트(OpenRouter nemotron-120b 레인)에서 예시 81("반도체 업종 … 먼저 적용하고, 그중 … 8종목 동일 비중으로 담고 싶습니다. 월간 리밸런싱, 20일선 이탈 시 청산, 손절 -8%")의 청산 규칙이 사라지고 `entry_signals`에 `ma_crossover(1/20) buy`가 남았다(3/3 재현). 트레이스 원본 확인 결과 **LLM 출력 자체**가 `technical.ma_crossover crosses_below(1/20) source_text="20일선 이탈 시 청산"`을 entry_conditions에 냈다 — 하류가 옮긴 것이 아니다. ① **원인은 프롬프트 예시 4-3의 단계 서술 규칙**: 예시 문장이 이 예시와 거의 같고(청산절만 없음) 해설이 "'먼저 적용하고 → 그중'은 … 세 조건 모두 entry_conditions"라고 못 박아, 같은 단계 문형이 오면 뒤에 붙은 청산절까지 entry로 따라 들어갔다(대조 실험: 업종 교체 2/2 재현·단계 문형 제거 2/2 정상·청산절 문두 이동 1/2 재현, 같은 청산 문구의 다른 예시 30개는 전부 정상). 규칙 문구를 늘리지 않고 **형태로 고친다** — 예시 입력에 청산절을 실어 exit_conditions 출력을 보이고, 해설을 '걸러내는 세 조건은 entry, 문장 끝 청산절은 exit'로 바꿨다(PROMPT_VERSION 5.1). ② **재배치 가드(`primary._fill_deterministic_condition_params` ③)가 잎 팩터를 못 봤다** — 대상이 `concept.dead_cross`류 개념명뿐이어서 잎 형태(`technical.ma_crossover`/`technical.ema` + `crosses_below`)는 지나쳤다. registry가 crosses_below를 데드크로스(매도 방향)로 선언하고 엔진이 교차 방향을 signal_type으로만 정하므로 같은 선언 기반 정규화로 넓힌다(청산이 비어 있을 때만, 인용에 매수 계열 표기가 있으면 불이동 — 영어 buy/enter 포함, 해석 레인 KR/US 공유). ③ **컴파일러가 연산자를 읽지 않았다** — `_compile_technical`은 ma_crossover/ema에서 기간만 옮기고 역할대로 buy를 붙여 "아래로 이탈하면 청산"이 "위로 뚫으면 매수"가 됐다. 이동평균·EMA·MACD에서 역할과 반대인 교차 방향은 `StrategyCompileError`(오실레이터 임계값 누락과 같은 계약), 검증기(`capability_validator`)도 같은 모순을 에러로 남겨 READY→전량 컴파일이 전략 전체를 던지지 않고 부분 컴파일이 그 조건만 제외+'반영하지 못했어요' 안내로 흐르게 한다(청산 역할 규칙 2026-08-05와 같은 이유). 볼린저처럼 방향이 역할로 고정되지 않는 지표는 건드리지 않는다. ④ **게이트 판정 부수 발견**: 같은 전수 실행의 치명 8건 중 6건은 외부 API 요청 단위 일시 실패(`interpretation_failed` 빈 전략 — 재파싱 전부 정상)였고 1건은 값 흔들림(4회 중 1회 bimonthly)이었다 — 붉은 항목은 재표본 3회로 flake와 결함을 먼저 가른다. 실패 응답은 nl_cache에 저장되지 않아 재요청이 새 호출이 되고, 실제 레인은 `runtime.interpreter.model_name`으로 확인한다(`runtime.backend`는 요청 슬롯명). 회귀: `test_strategy_conversation.py` 6건(잎 데드크로스 재배치·매수 표기 불이동 KR/EN·청산 존재 시 불변·컴파일러 방향 거부/정방향·볼린저 회귀 없음·검증기 에러→부분 컴파일 제외·프롬프트 예시 4-3 형태).

**FR-STR-020c** `correctedStrategy`의 `universe` 필드는 원문 기준 결정적 추출(`_extract_explicit_universe`)과 다르면 항상 결정적 추출값으로 되돌려야 한다. 유니버스는 KOSPI/KOSDAQ/KOSPI200 어휘 매핑일 뿐이라 교정 LLM이 개선할 여지가 없고, 되돌리지 않으면 유니버스 확대로 인한 심각한 성능 저하만 남는다(단, `max_positions` 등 숫자 필드의 정당한 교정은 그대로 존중한다). (실사례 2026-07-05: "KOSPI 대형주 중에서 PBR이 1배 이하인 종목..." 프롬프트가 룰 파싱 잔여 미해석으로 LLM 검증을 타고, 교정본이 유니버스를 KOSPI200→KOSPI로 되돌려 200종목이 전체 코스피(800+ 종목)로 확대 → 백테스트가 크게 느려져 전략연구소 화면이 멈춘 것처럼 보임.)

**FR-STR-020d** SSE 파싱 경로(`/strategy/parse-stream`)에서 LLM 검증은 비차단(후행)이어야 한다: 룰 파스 결과를 먼저 `result` 이벤트로 전송하고, 검증은 스트림을 연 채 후행 실행하며(`_run_nl_parse`의 defer_holder → `_complete_deferred_validation`), 교정이 적용된 경우에만 `result_update` 이벤트로 갱신본을 후속 전송한다. 파싱 캐시도 교정본으로 갱신해 동일 프롬프트 재요청이 교정 전 결과를 반환하지 않아야 한다. 후행 검증 중에는 `validating` stage 이벤트를 보내지 않아야 하며(프론트가 로딩 표시로 되돌아가 요약이 사라지는 회귀 방지), 프론트(`parsed_updated` 이벤트)는 사용자가 이미 백테스트를 실행/완료한 뒤 도착한 교정은 무시해야 한다(실행 스냅샷 일관성). 후행 검증 대기는 프록시 스트림 예산(120s) 미만으로 상한을 두고 초과 시 결과를 폐기한 채 스트림을 닫는다. 비스트림 `/strategy/parse`는 인라인 검증을 유지한다.

**FR-STR-021** 시스템은 "최근 N일/N거래일/N개월 수익률이 높은 종목 상위 K개"와 같은 상대강도(모멘텀) 랭킹 표현을 인식하여 `ranking_metric="return"`과 `ranking_lookback_days`(미지정 시 60일 기본)를 추출해야 하며, 랭킹 전략에 리밸런싱 주기가 명시되지 않은 경우 `monthly`를 기본값으로 적용해야 한다. 단, 회전 수단이 없는 펀더멘털 스크리닝 전략의 기본 월간 리밸런싱은 사용자가 리밸런싱을 명시적으로 거부한 경우("리밸런싱 없이 계속 보유")에는 주입하지 않고 `none`(매수 후 계속 보유)으로 보존해야 한다 — 랭킹 전략은 회전이 달력 리밸런싱으로만 동작하므로(엔진 제약) 거부 표현이 있어도 유지한다.

**FR-STR-022** 시스템은 진입 의도가 있는 자연어 입력에서 파싱 결과에 진입 신호/펀더멘털 필터/랭킹 기준이 모두 비어 조용히 누락된 경우, 사용자에게 명확화 질문과 대안 제안(클릭 가능한 칩)을 표시해야 한다. 이때 일반적인 누락 사례와 "엔진이 아직 지원하지 않는 상대강도 랭킹 표현" 사례를 구분하여 각각 다른 안내 문구와 대안을 제공해야 한다 (서로 다른 원인이므로 동일한 메시지로 뭉뚱그리면 안 됨). 첫 파싱에서는 백엔드가 보낸 구체적 안내를 우선 사용한다. [2026-07-19 확장] ETF 유니버스 전략("etf를 사는 전략은 어때?")도 별도 사례로 구분한다 — ETF에는 개별 기업 재무지표(PER·PBR·ROE)가 없으므로 재무 필터 예시 칩(일반 안내)을 그대로 보여주면 오답이며, ETF에 통용되는 가격·추세 기반 방식(이동평균 추세추종·모멘텀/신고가 돌파·RSI 평균회귀·MACD·정기 리밸런싱)의 예시 칩으로 진입 조건을 묻는다(`nl_parser._ETF_PRODUCT_QUESTION`). 임계값 되묻기("PER은 몇 이하로 할까요?")보다 이 안내가 우선하며, 기술 신호가 이미 추출된 경우에는 되묻지 않고 그대로 실행한다(ETF는 정식 지원 유니버스 — FR-STR-067). ETF 전략에 기업 재무지표가 실제로 섞인 경우는 FR-STR-067 ④의 충돌 되묻기가 먼저 가로챈다. [2026-07-21 확장] `etf_theme`가 특정 ETF 상품명과 정확히 일치하는 경우("kodex 반도체 etf를 매수"→etf_theme="KODEX 반도체")는 "여러 ETF 중 고르는" 뉘앙스의 일반 문구(`_ETF_PRODUCT_QUESTION`의 '정기 리밸런싱' 등) 대신, 상품명·종목코드를 확정해 보여주는 전용 문구(`_ETF_PRODUCT_QUESTION` → `_ETF_SINGLE_PRODUCT_QUESTION`, `universe_pit.resolve_single_etf_product`로 정확 매칭 판정)로 되묻는다 — 이미 단일 상품이 지정됐는데도 열린 테마처럼 되물어 "또 어떤 ETF를 살지 묻는다"고 오인하는 사고를 방지한다("반도체" 같은 열린 테마 키워드는 그대로 일반 문구를 유지).

**FR-STR-023** 시스템은 매수(종목 선정) 기준이 전혀 없는 전략(진입 신호·펀더멘털 필터·랭킹 기준이 모두 비어 백테스트가 0매매로 끝나는 경우)에 대해 백테스트 실행을 막아야 한다. 이 판정은 실제 백테스트로 전달되는 병합된 전략을 기준으로 하므로 최초 파싱뿐 아니라 점진적 수정 이후에도 적용되어야 하며, 매수 기준이 빠진 상태에서는 "백테스트 실행" 버튼을 노출하지 않고 최소 조건을 입력하도록 명확화 안내를 표시해야 한다. (청산·리스크 설정만으로는 살 종목을 선정할 수 없으므로 매수 기준으로 인정하지 않는다.)

**FR-STR-023b** 백테스트 결과 화면의 "프롬프트" 배지(진입 신호 / 청산 신호)는 사용자가 정의한 전략 요약을 그대로 표시해야 한다 — 진입 신호 섹션은 `entryBlocks`(진입 신호·펀더멘털 필터)만 렌더링하고, 비어 있으면 섹션을 숨긴다. 진입 신호·청산 신호가 섞인 `blockNames` 폴백으로 떨어져선 안 된다(매수 기준 없이 익절만 있는 전략에서 청산 배지가 진입에 누출되던 버그 방지). 이는 표시 전용이며 백테스트 엔진은 진입 조건을 `fundamental_filters`+`entry_signals`로, 청산 조건을 `exit_signals`로 분리해 구성하므로(`strategy_converter.to_backtest_request`) 실행 DSL에는 누출이 없다.

**FR-STR-023c** 시스템은 전략 설정값의 하한선을 강제해야 한다(`enforce_strategy_minimums`, 규칙/LLM/수정 모드 무관 모든 파싱 경로 뒤에서 적용). 하한 미만 입력은 자동 보정/제거하고, 사용자에게 보정 내용을 전략 요약과 함께 비차단(non-blocking) 방식으로 안내해야 한다. 안내는 매수 기준 명확화(`clarification`)와 달리 전략 요약 카드를 숨기지 않는다(`notices` 채널).

**FR-STR-023d** 시스템은 스키마(`ParsedStrategy`)가 표현할 수 없는 미지원 개념(배당·섹터·변동성·수급·분할매도·거래량 배수("평소 대비 N배" — `volume_spike`는 OBV 크로스오버라 배수 임계값 표현 불가) 등, `nl_parser._UNSUPPORTED_CONCEPT_PATTERNS`)이 프롬프트에 언급되면, LLM 폴백 위임(부분 파싱 침묵 누락 방지)과 별개로 사용자에게 해당 조건이 "아직 직접 지원되지 않아 반영되지 않았거나 다르게 해석됐을 수 있다"는 안내를 `notices` 채널로 제공해야 한다(`build_unsupported_concept_notice`). LLM 폴백조차 스키마 제약으로 이 개념들을 정확히 표현할 수 없으므로, 조용한 유사 해석 대신 명시적으로 알리고 전략 요약 확인을 유도한다. [2026-07-14 확장] 데이터 파이프라인이 없는 흔한 퀀트 팩터도 같은 채널로 안내한다: ROIC(투하자본이익률), 베타, 이자보상배율, 피오트로스키/알트만 점수, 회전율(재고·매출채권 등), 자사주 매입, PCF/주가현금흐름(기존 cash_flow 항목 확장). (ETF/ETN은 2026-07-19 같은 날 잠시 `etf_product` 항목으로 이 목록에 추가되었다가 ETF 정식 유니버스 승격(FR-STR-067)으로 즉시 제거되었다 — 개념 구현 시 목록에서 제거하는 원칙의 적용 사례.) **단 EV/EBITDA(에비타)는 KIS other-major-ratios 배선(2026-07-14)으로, 배당수익률·배당성향·배당성장률은 KIS 예탁원 배당 API 배선(2026-07-14)으로 데이터가 확보되어 지원 지표로 승격되었으므로 미지원 목록에서 제거되었다**(수치 있는 배당수익률/배당성향/배당성장률 필터가 추출되면 `배당` 안내를 억제하는 조건부 제외 방식 — 수치 없는 막연한 '배당주/배당 성장주' 언급만 미지원 안내 유지) — 데이터 파이프라인 구현 시 목록에서 제거하는 원칙의 실제 적용 사례. 이 안내는 최초 파싱과 수정 요청 모두에 적용된다(`_build_parse_result` 공유). 지원 지표(영업이익률·순이익률·매출총이익률 등 마진류)는 절대 미지원 목록에 넣지 않는다(오폴백 방지) — 해당 팩터의 데이터 파이프라인을 구현하면 목록에서 제거해야 한다. [2026-07-24 확장 — 흑자/적자 승격] 흑자/적자 '여부'(`profitability_sign`)는 parquet의 연간 `eps` 컬럼으로 표현 가능해 지원 지표로 승격되었다: "흑자 기업"·"적자 제외/아닌"→`eps > 0`, "적자 기업만"→`eps < 0`을 값 없는 키워드 조건으로 결정적으로 추출한다(`nl_parser._keyword_profitability_operator` — 흑자 여부를 순이익증가율(net_income_growth)로 바꿔 해석하는 것은 부호 조건≠변화율 조건 오귀속이므로 금지, LLM 폴백 프롬프트에도 명시). 단 ① 흑자전환·적자탈출·N년 연속 흑자 같은 부호 전환/연속(시계열) 표현은 단일 시점 부호 필터로 왜곡되므로 emit하지 않고 미지원 안내로 남기며(목록 제거가 아닌 조건화 — 항목명 `profitability_transition`, 추출 가드와 동일 패턴 공유), ② "영업활동현금흐름이 흑자"·"영업이익 흑자"처럼 순이익이 아닌 항목의 부호 언급은 키워드 직전 문맥 가드로 eps 바꿔치기를 차단하고 LLM에 위임한다. 아울러 백테스트 전 결정적 검증(`ai/strategy_validation_agent.py`)의 지원 조건 화이트리스트는 재무 지표를 하드코딩 사본이 아니라 엔진 SOT(`engine.signals.FUNDAMENTAL_CIDS`)에서 직접 파생해야 한다 — 사본 드리프트로 엔진이 지원하는 순이익증가율이 "지원하지 않는 필드"로 오탐 차단되던 사고의 재발 방지(회귀: `test_engine_supported_metrics_are_not_flagged_unsupported`). [2026-07-29 확장 — 보유 기간 하한] `hold_period_days`는 **만료 시 강제 청산(상한)**만 표현한다. "최소 보유 기간은 3개월"·"최소 6개월은 들고" 같은 **하한**(그 전에는 팔지 않기)은 반대 개념이므로 상한으로 뒤집어 확정하지 않고(`_MIN_HOLD_PERIOD_PATTERN`으로 추출 제외) 미지원 개념(`min_hold_period`)으로 안내한다 — 예시 카드 "부채비율·ROE 보유 조건"의 '최소 보유 기간 3개월'이 요약에 "최대 63일 보유 후 매도"로 표기되던 2026-07-29 사고. 인터프리터 프롬프트(v2.0)에도 같은 계약을 명시했고(하한은 `unsupported_features`), 패턴은 보유 동사·'보유 기간' 명사가 붙은 형태만 잡아 "최근 3개월 이상 상승"(모멘텀 룩백)을 오탐하지 않는다. [2026-08-01 확장 — 표현된 개념은 안내에서 뺀다] 미지원 개념 어휘가 언급됐어도 **컴파일 결과가 그 개념을 실제로 표현했으면** 안내를 내지 않는다(`concepts_expressed_in_strategy` — 섹터·배당의 조건부 제외와 같은 계약, 판정 입력은 컴파일 결과와 입력 **수치**뿐이며 원문 어휘를 다시 읽지 않는다). ① `cash_flow` — 현금흐름 '수준/흑자 여부'는 여전히 미지원이지만 증가율(`ocf_growth`·`fcf_growth`)은 지원 지표이므로, 그 필터의 임계값이 **입력 수치에 있으면**(§ 3-1 수치 대조) 안내를 뺀다. 임계값이 입력에 없으면(예: '현금흐름이 흑자' → `ocf_growth>=0`) 인터프리터가 지어낸 유사 대체이므로 안내를 유지한다 — 조용한 의미 변경 방지. ② `ema_alignment` — '정배열'은 두 선의 상하 관계(crossover 표기, 프롬프트 규칙 5-3)로 표현되므로 전략에 이동평균 비교 신호가 있으면 안내를 뺀다(세 선 이상 나열의 부분 표현은 이 술어가 구분하지 못한다 — 알려진 한계). 아울러 인터프리터의 `unsupported_features`를 그대로 인용하던 **파싱 경로 안내는 폐지**했다(사용자 판단): LLM 자유 서술 채널이라 내부 사정("unsupported_features에 기록합니다")·지원되는 필드명(`risk_management.stop_loss`)·발화 조각이 그대로 노출됐고, 미지원 개념 안내는 이 결정론 게이트가 이미 담당한다. 조용한 누락 방지는 제외 조건 안내(결정론 대조)가 맡는다(미반영 수치 안내는 2026-08-01 폐지 — FR-STR-019j ⑤). 수정 경로의 미반영 안내(FR-SA-019)는 그대로 유지된다 — 그쪽은 전략이 그대로인 이유를 말하는 유일한 채널이다. [2026-08-12 — 잔여 미지원 안내 부활(가드 부착), 사용자 결정] 무필터 인용 폐지 후 **목록 밖 새 개념**(34개 패턴에 없고, LLM이 조건으로 뽑지도 되묻지도 않고 `unsupported_features`로만 보고한 개념)이 어떤 안내도 없이 사라지는 틈이 남았다. 파싱 경로에 수정 레인(FR-SA-019)에서 검증된 가드를 얹어 한정 부활한다(`strategy_conversation/primary.py` 잔여 미지원 안내 블록): ① 발화 전체 에코 오라벨이면 침묵(`_reported_features_echo_input`) ② 내부 식별자는 평이화(`_humanize_features`), 스키마 필드 경로(`technical.beta` 등)는 제외(그 조건의 탈락은 제외 조건 안내가 source_text로 이미 알린다) ③ `_UNSUPPORTED_CONCEPT_PATTERNS`(34개)에 매칭되는 항목은 제외 — 그 목록의 안내와 의도적 억제(이미 반영·값 대기)는 이 결정론 게이트 소관이라 다시 내면 중복이거나 오탐 부활이다. **영문 개념 ID 표기('volatility' 등)도 같은 제외 대상**이다 — LLM이 한글 대신 ID로 보고하면 한글 패턴을 뚫고 결정론 게이트 안내와 중복된다(섀도 대조 실측, 회귀 `test_primary_unsupported_concept_id_token_excluded`) ④ 되묻기 질문·이월 큐·기존 notices·값 대기 라벨이 다루는 항목은 제외(모순 방지). 판정 입력은 전부 LLM 출력·자기 응답 문자열이다(라벨 정규식 매칭은 `concepts_covered_by_pending`과 같은 계약 — 원문을 읽지 않는다). 통과한 잔여 중 이름이 길이 상한(25자, `_QUOTED_FEATURE_MAX_LEN`) 이하인 항목만 "'X' 조건은 지원하지 않아 전략에 반영하지 못했어요"로 지목하고, **상한 초과 발화 조각은 지목 없이 "말씀하신 조건 중 일부는 지원하지 않아 전략에 반영하지 못했어요"로 뭉뚱그린다**(2026-08-12 사용자 결정 — 레드팀 실측 3-4의 자기 말 반 토막 인용 방지, 회귀 `test_primary_unsupported_long_fragment_not_quoted`). [2026-08-13 — 인터프리터 미지원 보고 일관성 + 모순 라벨 강등] 섀도 대조 반복 실측으로 두 가지를 확정했다. ① **프롬프트 v3.5**: 규칙 3에 유사 대체 금지(ROIC→ROA·흑자전환→eps 부호·시장 대비→수익률 랭킹·현금흐름 흑자→증가율·우선주→보통주·일부 익절→전량 take_profit)와 자주 놓치는 미지원 개념 목록을 명시(보고 17→45건/64). 단 **프롬프트 분량 임계 실측**: 규칙을 더 늘리자 복합 정상 입력("PER 10 이하이고 ROE 15%…")의 출력 JSON이 바깥 객체를 닫지 않고 조기 종료했다 — 대조 예시 블록을 제거·압축해 해소했고, 하니스 `_control` 대조군 4건이 재발을 감시한다. ② **UNSUPPORTED_REQUEST 모순 라벨 강등**(`strategy_conversation/primary.py`): 라벨 정의·규칙·대조 예시 세 차례 프롬프트 반복으로도 9B가 미지원 개념 섞인 전략 서술을 UNSUPPORTED_REQUEST로 밀어내는 드리프트가 고정되지 않아(15/64), 구체 미지원 개념 보고(역할 밖 행위 보고 제외 — 종목 추천·시장 전망·전략 우열은 거절 유지)가 있으면 CREATE_STRATEGY로 강등하고 CREATE 레인으로 재검증한다. 전략 골격이 없으면 빈 골격으로 진행해 "지원하지 않아요 안내 + 조건 되묻기" 턴이 된다. 최종 성적(하니스 68케이스): 해석 실패 0(개선 전 8), LLM 레인 잔여 격차 2건(현금흐름 흑자 여부·ROIC — 결정론 게이트가 커버, **게이트 유지 근거**). 회귀 `test_primary_unsupported_request_label_demoted_with_concrete_features` 외 2건, 하니스 `scripts/qa_unsupported_shadow.py`. 회귀: `test_primary_notices_unlisted_unsupported_feature` 외 4건. [2026-08-13 — 이중 기입 허위 신고 수정, 프롬프트 v3.6] 9B가 '최대 보유 기간은 20거래일'을 `hold_period_days=20`에 정상 반영하고도 같은 표현을 `unsupported_features`에 이중 기입해, 잔여 미지원 안내가 "반영됐는데 지원하지 않는다"는 모순 안내를 냈다(temperature 0 결정적 재현). 절제 실험으로 유발원을 확정: 규칙 3 목록·규칙 5 끝의 '**최소** 보유 기간=미지원' 언급에 모델이 사용자의 '최대'를 혼동해 끌려갔다(수치 체크리스트는 원인 아님). 수정은 규칙 4-1에 이중 기입 금지 일반 규칙("이미 필드·조건에 값으로 반영한 표현은 지원된 것 — `unsupported_features`에 다시 넣지 않는다, 한 표현은 한 곳에만")을 추가 — 지원/미지원 근접 쌍 클래스 전체(최대/최소 보유 기간, 신고가/신저가 등)를 커버한다. 실측: 사고 입력 허위 신고 소멸 + '최소 보유 기간' 입력의 미지원 신고·`hold_period_days` 미오염 유지 + 예시 카드 40거래일 복합 입력 정상. 회귀 `test_interpreter_prompt_forbids_double_entry_of_reflected_expressions`. [2026-08-14 — 값-대기 이중 기입 차단] 같은 이중 기입이 **값-대기 조건**에서도 재현됐다(예시 '매출성장·PBR 추세 조건'): LLM이 `pending_conditions`에 올린 조건을 `unsupported_features`에도 **사용자 표현**("매출 성장률이 양호하고")으로 함께 신고해, 라벨("매출액증가율") 기준 제외를 뚫고 "지원하지 않아 전략에 반영하지 못했어요"라는 거짓 안내가 값 확인 대기 중인 조건에 붙었다. 잔여 미지원 안내의 제외 조건에 **`pending_conditions[].source_text` 포함 대조**를 더한다(`_covered_by_pending_texts` — 4자 미만 조각은 우연 일치가 잦아 제외, 판정은 LLM 출력 ↔ 자기 응답 채널의 표기 대조뿐이다). 미반영 **수치** 안내 폐지(FR-STR-019j ⑤)는 그대로 유지된다. [2026-09-13 — 근사 반영 조건의 조각 이중 기입 차단] 같은 이중 기입이 **근사 반영(`approximated: true`) 조건**에서 반대 모양으로 재현됐다: '큰 폭으로 하락한 뒤 반등 신호가 있을 때만 진입하고 싶어'를 LLM이 문장 전체 인용의 RSI 조건으로 반영하면서 같은 문장의 **조각** '큰 폭으로 하락한 뒤'를 `unsupported_features`에 이중 기입 → 근사 안내("RSI로 가깝게 반영했어요")와 잔여 미지원 안내("지원하지 않아 반영하지 못했어요")가 한 응답에 실렸다. 인용이 25자 상한을 넘어 근사 안내가 문장을 인용하지 않았고(covered_text 대조 불발), source_text 포함 대조는 보고 조각이 인용을 **감싸는** 방향만 봐서 조각 ⊂ 인용 모양은 새어 나갔다. 잔여 미지원 안내의 제외 조건에 **근사 반영 조건의 인용문 안에 든 조각** 대조를 더한다(`_covered_by_approximated_texts`). 반대 방향을 모든 조건에 열면 "평소보다 3배" 같은 진짜 미지원 보고까지 삼켜지므로 `approximated` 신고가 붙은 조건에 한정한다 — 근사 안내가 이미 그 문장을 다뤘으므로 같은 문장의 일부를 미지원이라 다시 말하는 것은 모순이다. 판정은 LLM 출력끼리의 표기 포함 대조뿐이다. 회귀 `test_primary_approximated_condition_fragment_not_noticed_as_unsupported`·`test_covered_by_approximated_texts_only_for_approximated_conditions`. [2026-08-10 — 변동성 승격] 변동성은 FR-BT-061(연환산 변동성 필터·저변동성 랭킹, 엔진 v13.1)로 지원 지표로 승격되었다. 다만 결정적 추출기는 여전히 변동성을 표현하지 못하므로 '변동성' 큐는 LLM 위임 신호로 목록에 남기고(PCR과 동형), 전략에 반영되면 `concepts_expressed_in_strategy`의 volatility 술어(ranking_metric='volatility' 또는 volatility 신호 존재)가 안내를 억제한다. [2026-09-08 — 반영된 유니버스 표현의 거짓 미반영 안내 차단(가드 ⑤)] planner-first가 **유니버스로 실제 반영한 표현**(테마 상장사 적용·학습 섹터 병합·분류 반영 확인·지정 종목 복구, 후보 1개 정본 표기의 전파 포함)은 잔여 미지원 안내에서 제외한다. 실측 사고: '생명보험 관려주 투자 전략을 만들어줘'가 생명보험 테마 상장사 5곳으로 정상 반영됐는데, 인터프리터가 같은 표현을 `unsupported_features`("생명보험 관려주")에 이중 기입해 요약 카드(유니버스 생명보험 5종목)와 "'생명보험 관려주' 조건은 지원하지 않아 전략에 반영하지 못했어요"가 한 응답에 함께 나갔다 — 종전 프루닝은 term-in 체인이 해석한 표현(`unresolved_sector_terms`)만 근거로 삼았고, planner가 반영한 표현은 그 목록에서 이미 빠져 있어 어느 프루닝에도 걸리지 않았다. 근거는 해석 완료(`resolved`)가 아니라 **유니버스 반영**(`_apply_planner_first_universe`의 세 번째 반환값 `applied`)이다 — `resolved`에는 반영할 필드가 없는 NOT_UNIVERSE 판정이 섞여 있어 그것으로 지우면 진짜 미지원 개념까지 침묵한다. 회귀 `test_primary_planner_applied_universe_term_not_noticed_as_unsupported`·`test_single_candidate_source_term_marked_resolved`. **[2026-09-10 개정 — '실적'은 미지원 개념이 아니다]**: 미지원 개념 목록의 `earnings` 항은 **실적 전망·이벤트**(컨센서스·추정치·목표주가·어닝서프라이즈·실적 발표일)만 가리킨다. 지난 실적 자체(매출·영업이익·순이익·이익률·성장률)는 정식 지원 지표이고 "실적 대비 가격"은 PER의 한국어 정의이므로, 종전의 맨 '실적' 패턴은 **정확히 반영된 요청에 미지원 안내를 붙였다**(실측 사고 2026-09-10: PER 조건으로 반영된 "실적 대비 가격이 낮은 종목"에 "'실적/컨센서스 조건'은 아직 직접 지원되지 않아요"가 함께 나갔다). 라벨도 '실적 전망·발표 이벤트(컨센서스·목표주가 등) 조건'으로 바꾼다. 회귀 `test_nl_parser_overrides.py::test_earnings_notice_covers_only_forward_looking_expressions`·`::test_per_request_carries_no_unsupported_notice`. **[2026-09-10 이관 — 판정을 LLM 레인으로]**: 이 안내의 판정 입력이 사용자 원문이라는 것 자체가 대원칙 1 위반(재심 구조)이었고, 낱말 하나('실적')를 좁히는 것으로는 같은 사고가 다른 낱말에서 반복된다(실측: '배당을 재투자하는 전략' → 기본 지원 기능인 배당 재투자에 "'배당 조건'은 아직 직접 지원되지 않아요"). 인터프리터 primary 레인에서는 다음 두 채널이 정본이며 원문 정규식 안내는 돌지 않는다(`main._build_parse_result` — 원문 스캔 스위치 `scan_prompt_for_sector`와 같은 기준. 레거시 레인은 종전 동작 유지). ① **미지원**: LLM의 `unsupported_features`(+검증기의 registry 판정)를 `primary`의 잔여 미지원 안내가 낸다. 이관에 맞춰 그 채널의 '정본 목록 34개 개념은 제외' 규칙을 폐지하고(제외를 남기면 보고된 개념이 어디서도 안내되지 않는다) 영문 개념 ID는 정본 한국어 라벨로 옮긴다(`_humanize_features`). 이미 반영·값 대기·질문이 다루는 항목의 제외는 그 채널 자신의 가드(source_text·pending 대조·`concepts_expressed_in_strategy`)가 맡는다. ② **근사 반영**: 정확히 같은 지표가 없어 가까운 지표로 대신 반영한 조건은 LLM이 `approximated: true`로 **스스로 신고**하고(출력 형태 키 1줄 + 규칙 1줄, PROMPT_VERSION 5.4), 시스템은 그 신고를 문구로 옮기기만 한다(`primary._approximation_notices` — "'{인용}'은(는) 정확히 표현할 수 없어 {지표}(으)로 가깝게 반영했어요"). ③ **지표 대체 감지**(신고 누락 대비): 조건의 인용이 이름으로 부른 지표(`indicator_registry.factor_ids_named_in`)에 그 조건의 factor가 없으면 대체로 보고 같은 안내를 낸다(`primary._substituted_factor` — "ROIC 15% 이상"→ROE, "거래대금이 평소보다 늘어난"→거래량 급증). 가장 위험한 대체에서 모델은 approximated 신고도 미지원 보고도 하지 않으므로 ②만으로는 조용히 지나간다. 판정 입력은 둘 다 LLM 출력(인용↔factor)이고 인용이 어떤 지표도 이름으로 부르지 않으면 판정하지 않는다. 합성 개념 전개(골든크로스→ma_crossover)는 별칭이 같은 canonical을 가리키므로 오탐이 아니다. 이로써 2026-09-03에 기록된 '레인으로 끄면 근사 반영 알림이 사라진다'는 비용을 원문 재심 없이 갚는다. 회귀: `test_nl_parser_overrides.py::test_build_parse_result_skips_raw_prompt_unsupported_notice_on_primary_lane`·`test_strategy_conversation.py::test_primary_notices_approximated_condition`·`::test_primary_exact_condition_carries_no_approximation_notice`·`::test_primary_notices_listed_unsupported_features`·`::test_primary_notices_substituted_factor_without_flag`·`::test_primary_expanded_concept_is_not_reported_as_substitution`. 프롬프트 분량 대조(실경로 interpret(), 8문형 A/B + 흔들린 2문형 N=3 재측정): 빈 전략 0건·조건 구성 동일 — 1차 측정이 무효였던 이유는 `prompts.build_system_prompt` monkeypatch가 인터프리터에 닿지 않기 때문이다(생성자에서 캐시한 `_system_prompt`를 갈아 끼워야 한다). [2026-09-15 — 거래량 배수 지표 승격(엔진 v16.10)] '거래량이 20일 평균보다 1.5배 많은'의 배수를 120B가 어디에도 남기지 않았다(unsupported_features [] · approximated false · notices [] — 규칙 5-2의 'unsupported_features에도 넣으세요'는 규칙 문장이라 안 지켜졌다). 오전에는 배수를 `value`에 옮겨 적게 하고 검증기가 걷어 근사 안내를 내는 것으로 막았으나, 사용자 결정(같은 날)으로 **엔진이 배수를 직접 지원**한다: 새 기술 지표 `technical.volume_ratio`(엔진 `volume_ratio` — 당일 거래량 ÷ 직전 N일 평균 거래량, 당일은 평균에서 제외, 부등호·배수 임계 비교, 매매사유 "거래량이 {N}일 평균의 {배}배 이상"). 프롬프트 6.0 규칙 5-2가 배수 표현을 이 지표로 보내고, LLM이 옛 자리(volume_spike+value)에 내면 검증기가 지표만 옮긴다(값·기간 불변, 연산자 없으면 '이상' — `capability_validator`). 미지원 목록(`_UNSUPPORTED_CONCEPT_PATTERNS`)과 레지스트리의 `unsupported.volume_multiple`은 구현 시 제거 원칙대로 삭제. 회귀 `tests/test_volume_ratio_indicator.py` 10건. 백테스트 전 결정적 검증(`ai/strategy_validation_agent.py`)의 기술 지표 화이트리스트에도 `volume_ratio`·`relative_return`을 추가했고 파리티 테스트가 `engine.data_resolver.TECHNICAL_IDS` 전수를 대조한다(재무 지표의 FUNDAMENTAL_CIDS 대조와 같은 원칙). [2026-09-13 확장 — 시장 대비 초과수익률] 근사 반영 안내(LLM `approximated` 신고 채널)는 조건뿐 아니라 랭킹 항목(`RankingSpec.approximated`)도 대상이다. 다만 '시장보다 덜 떨어진'·'시장보다 강한'·'시장 수익률을 웃도는' 종목은 더 이상 근사가 아니라 정확 지표 **`technical.relative_return`**(종목 N거래일 수익률 − 상장 시장 지수 N거래일 수익률, %p; 엔진 `relative_return`, v16.7.0)으로 표현한다 — 인터프리터는 operator `>`·value 0·`parameters.period`(거래일 환산, 3개월=63)로 출력하고('시장보다 더 떨어진'만 `<`), 시스템은 지수 시계열 저장소 `data/index/{KOSPI,KOSDAQ}.parquet`(토스 Open API 2014-07~ 정본 + KIS 1996~2014-06 보충, `scripts/backfill_index_history.py`, 야간 `sync_data.py` 갱신)에서 종목의 상장 시장 지수 종가를 날짜 조인(`engine/market_index.attach_index_close`)해 계산한다. 지수가 없으면(미국 종목·파일 부재) 조건은 NaN→False로 fail-closed이며, 미국 유니버스에서는 검증기가 오류+제거+안내한다(미국 지수 시계열 미수집 — 보류).
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
  execution_delay_days?: number     // 신호 후 N거래일 지연 체결 (next_open 전용, 기본 1)
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

**FR-BT-010f** [적용 거래 비용 결과 동봉, 2026-09-14] 백테스트 결과는 엔진이 실제로 적용한 거래 비용(매수·매도 수수료율, 슬리피지율, 매도 거래세율 — 고정 세율이면 값, 시행일 기준 법정 세율 스케줄이면 구간의 최저·최고)을 `tradingCosts`로 동봉해야 한다(`engine/simulator.py applied_trading_costs`, 시뮬레이터와 같은 해석). 결과 화면 "프롬프트" 요약의 '거래 비용' 행, '백테스트 로그' 창의 `거래 비용: …` 줄, CSV/JSON 내보내기는 설정 화면의 현재 값이 아니라 이 동봉값을 보인다 — 동봉이 없는 구버전 결과에는 행을 만들지 않는다(현재 설정값을 적용값처럼 보이는 것은 거짓 안내). 결과 DTO의 새 필드는 프론트 매핑 **4지점**(`lib/strategy/BacktestService.ts`, `app/analytics/new/backtestResultMapper.ts`(채팅 레인 SSE 결과), `components/strategy/RunAllTestsModal.tsx`, `app/analytics/[id]/page.tsx`(기록 재실행))에 모두 배선해야 한다 — 2026-09-14 채팅 레인 매퍼 한 곳이 빠져 백엔드가 동봉한 값이 결과 화면 '거래 비용' 행과 로그 줄에 끝내 나타나지 않았다(회귀: `backtestResultMapper.test.ts`).
**FR-BT-010g** [요청한 거래 비용의 관통, 2026-09-14] 사용자가 문장으로 요청한 수수료율·슬리피지율(인터프리터 `backtest.fee_rate`·`slippage_rate`, %)은 그 백테스트 한 건의 `options.fee_rate`·`slippage_rate`로 실려 첫 실행·재실행·워크포워드·수정 턴까지 같은 값으로 돌아야 한다. ① 원문을 다시 읽어 값을 덮어쓰는 결정론 코드를 두지 않는다 — `engine/nl_parser._apply_prompt_overrides`의 수수료·슬리피지 블록은 `수수료0.1%` 붙여쓰기 형태만 인식하고 못 뽑으면 기본값을 써 넣어 "슬리피지를 0.1%로 바꿔줘"·"슬리피지는 그대로 두고"를 0.05%로 되돌렸으므로 제거했다(대원칙 1, 회귀 `test_nl_parser_overrides.py::test_prompt_overrides_do_not_touch_llm_fee_and_slippage`). 상식 상한(10% 초과 → 기본값 복원+안내)만 결정론이 지킨다. ② 재실행 요청은 패널 값 > 요청이 실은 값 > 기본값 순으로 비용을 정한다(`app/analytics/new/backtestOptions.applyRunCosts`, 채팅 화면·기록 페이지 공용) — 종전에는 패널 값이 없으면 곧장 하드코딩 기본값으로 떨어져 기록 페이지 워크포워드가 요청값을 지웠다. ③ 설정 패널 초기값은 요청(또는 결과가 적용한 `tradingCosts`, 없으면 저장 DSL)의 값을 보이고 0%도 값으로 다룬다(`??`). ④ 수정 턴은 인터프리터 패치 `/backtest/fee_rate`·`/backtest/slippage_rate`가 컴파일까지 관통한다(회귀 `test_strategy_conversation.py::test_modify_primary_applies_fee_and_slippage_patches`). 매수·매도 수수료 분리와 거래세율은 자연어 요청 대상이 아니다(옵션 API 전용).
**FR-BT-010h** [사용자가 말한 거래 비용의 전략 요약 표시 + 거래세 요청, 2026-09-14] 사용자가 수수료·슬리피지·거래세를 특정 값으로 말하면 대화 화면 전략 요약 카드('현재까지 이해한 전략입니다')에 '거래 비용' 행으로 **말한 항목만** 보인다(항목당 한 줄, 정본 순서 수수료→슬리피지→거래세, `builderProgressPresentation.tradingCostParts`). 근거는 provenance(`explicit_fields`의 `fee_rate`·`slippage_rate`·`sell_tax_rate` — 인터프리터 출력의 non-null·수정 패치 경로)이며 값의 존재가 아니다 — 컴파일러가 수수료 0.015%·슬리피지 0.05%를 물질화하므로 값만 보면 기본값이 사용자 확정처럼 보인다. 이 세 필드는 되묻기 슬롯이 아니다(질문하지 않는다). 거래세는 인터프리터 `backtest.sell_tax_rate`(%, 프롬프트 규칙 11-2-2, PROMPT_VERSION 5.7) → `ParsedStrategy.sell_tax_rate`(기본 None=시행일 기준 법정 세율, 물질화 없음) → 말한 때만 요청 `options.sell_tax_rate`로 실린다(없으면 시뮬레이터가 법정 세율 스케줄). 검증 범위 0~10%. 결과 화면의 적용 비용 행(FR-BT-010f)이 실제 적용값을 따로 보인다. 매수·매도 수수료 분리는 여전히 자연어 요청 대상이 아니다.

**FR-BT-011** 처리 순서는 반드시 이월 청산 방출 → Exit → Risk Evaluation → Rebalance → Entry 순서를 지켜야 한다 (벡터화 단계). 청산이 예정된 종목은 같은 날 재진입할 수 없다(동일 셀 매수·매도 주문 충돌 금지).

**FR-BT-011b** [손절 종목 대체 편입, 2026-09-17 사용자 결정, 엔진 v16.12.0] 순위가 있는 달력 회전(선정=진입, 매수 조건 없음 — 커스텀 루프 경로)에서 **손절로 청산이 결정된 종목은 그 리밸런싱 기간의 목표 집합에서 빠지고**, 빈자리는 그 리밸런싱일 랭킹의 다음 순위 후보가 채운다(`engine/simulator.py` — 리밸런싱 단계 뒤·진입 단계 앞). ① 후보 순서는 리밸런싱일 선정과 같은 범위다: 상위 K·상위 X%는 리밸런싱일 후보 전체(가용·유동성·시총 마스크를 통과한 목록)에서 선정 밖 순위부터, 분위 그룹은 자기 구간 안(그룹당 상한 밖)만. 이미 목표·보유·청산 대기인 종목과 이번 기간에 손절된 종목은 건너뛴다. ② 남은 후보가 없으면 다음 리밸런싱일까지 현금이다. ③ 체결 가능 여부(거래정지 등)는 원래 목표 종목과 같이 거래일마다 판정한다 — next_open이면 손절 청산과 같은 시가에 대체 매수된다. ④ 다음 리밸런싱일에 기간 기록이 비워져 손절 종목도 다시 정상 후보다. 리밸런싱일 장중에 손절된 종목은 새 기간의 손절로 본다. ⑤ 대체 매수의 사유는 "손절 종목 대체 편입 (리밸런싱일 순위 N위)"(`trade_reason.STOP_LOSS_REFILL`, 시뮬레이터 `entry_reason_overrides` → result_handler가 신호 사유보다 우선) — 상위 K 편입 사유로 적으면 K+1위 종목이 상위 K에 든 것처럼 읽힌다. 비중 유지(weights_only) 방식도 같은 규칙이다. **범위 밖(종전 동작 유지, 미결정)**: 익절·트레일링 스탑·보유 기간 만료 청산(같은 기간 목표에 남아 다음 거래일 재매수 가능), 매수 조건이 후보를 정하는 전략(그날 매수 신호가 켜져 있으면 재매수), 순위 패널이 없는 회전. 배경: 종전엔 손절 종목이 목표 집합에 남아 "목표가 채워질 때까지 빈 슬롯을 메우는" 계약에 따라 다음 거래일에 다시 매수됐다(2026-09-17 실측: 아티스트컴퍼니 2024-01 손절→재매수 3회). 회귀: `backend/tests/test_stop_loss_refill.py`.

**FR-BT-012** 트레일링 스탑은 `peak_price` 배열로 추적하며(고점 갱신은 장중 고가 기준), 진입 시 초기화하고 청산 시 리셋해야 한다.

**FR-BT-013** 다중 종목 동시 진입 시그널 발생 시 스코어 기반 랭킹으로 우선순위를 결정해야 한다 (PBR/ROE 복합 스코어 또는 `ranking_metric="return"` 모멘텀 — 최근 N일 수익률 상위 K종목 선정). 진입 조건 없는 모멘텀 랭킹의 후보 풀은 유동성 게이트와 대형주(시가총액 상위) 마스크를 반드시 보존해야 한다. (감사 C4)

**FR-BT-013b** [랭킹 lookback의 워밍업 가격, 2026-09-17, 엔진 v16.12.0] 가격에서 산출하는 랭킹 패널(N거래일 수익률 `return`·시장 대비 초과수익률 `relative_return`·변동성 `volatility`·복합 순위의 가격 구성 지표·랭킹을 말하지 않은 전략의 후보 우선순위)은 **창 시작 전 워밍업 구간의 종가를 포함해** 계산해야 한다 — 창의 첫 거래일부터 순위가 정의된다. phase1이 창 절단 전 프레임에서 워밍업 포함 종가(`engine/phase1.window_boundary_prep`, 창 종가와 같은 전처리)를 따로 싣고, 엔진은 그 패널로 계산한 뒤 창 인덱스로 되돌린다. 창 종가 패널(`raw_price_df`)은 가용성·상장·상폐 판정용 의미를 그대로 유지한다. 관측이 lookback 미만인 종목(창 안 상장·워밍업 중 상장)은 여전히 lookback 봉이 쌓일 때까지 NaN(후보 배제, v13.3)이고, 시장 지수 종가도 같은 날짜축으로 붙는다. lookback이 기본 워밍업(400 캘린더일)을 넘으면 워밍업을 `lookback × 1.6 + 40`일로 늘린다. 세션 캐시·Phase1 프로세스 풀·워크포워드 창 병렬·AI 경로 모두 같은 산출물을 쓴다. 배경: 종전엔 창으로 잘린 종가로 계산해 첫 lookback 거래일 동안 전략이 현금으로 앉아 있었다(2026-09-17 실측: 60거래일 수익률 상위 5종목·월간, 2023-09-18 시작 → 첫 매수 2024-01-02). **창 첫날의 N일 지연(같은 날 추가 결정)**: next_open(`execution_delay_days` N)의 shift는 창 직전 N거래일을 원천으로 삼아야 한다 — 창 첫날(=첫 리밸런싱일)의 매수·매도 신호, 순위(수익률·변동성·초과수익률·재무·복합·후보 우선순위), 유동성·시총 마스크는 창 직전 N번째 거래일까지의 정보로 정하고 첫날 시가에 체결한다(창 중간 리밸런싱일과 같은 규칙, 룩어헤드 없음). phase1이 창 직전 N+1봉(`window_boundary_prep`)을 싣고 신호·전일 거래대금 유동성은 그 봉을 이어 붙인 프레임에서 계산하며(`symbol_signals`, 스레드·프로세스 풀·AI 경로 공용, 세션 캐시 키에 N 포함), 엔진은 창 직전 N거래일(전 종목 창 직전 봉의 합집합 중 마지막 N일)을 앞에 붙여 민 뒤 창만 남긴다. 창 이전 봉이 없는 종목(창 안 신규 상장)은 원천이 없어 첫날 선정되지 않고, 상폐·데이터 종료 강제청산과 `raw_price_df` 가용성 의미는 불변이다. 창 첫 봉의 교차 신호·유동성도 창 직전 봉을 보므로 same_close에서도 첫날 값이 달라질 수 있다(둘째 봉 이후는 불변). 예외: AI 하락 랭킹 청산 주입(`rank_exits`)은 창 안 shift 그대로다(창 첫날엔 보유가 없어 N=1에선 영향 없음). 종전엔 창 안에서만 밀어 첫날이 늘 비었다(실측: 2023-09-18 시작 → 첫 매수 2023-10-04). 회귀: `backend/tests/test_ranking_warmup_prices.py`.

**FR-BT-013c** [수익률·낙폭 지표의 기준 = 초기자본, 2026-09-17, 엔진 v16.12.0] 자산곡선(`equity`)의 첫 값은 첫 거래일 **종가 기준 평가액**이며, 첫날 시가 체결이 있으면(FR-BT-013b next_open 첫날 체결, same_close 첫날 신호) 초기자본과 다르다. 모든 수익률·손익·낙폭 지표는 초기자본을 기준점으로 삼아야 한다. ① 결과는 `initialCapital`(초기자본)을 동봉하고(응답 스키마 선언), 프론트 결과 매퍼 4지점(`lib/strategy/BacktestService.ts`·`app/analytics/new/backtestResultMapper.ts`·`components/strategy/RunAllTestsModal.tsx`·`app/analytics/[id]/page.tsx`)은 그 값을 쓴다 — 동봉이 없는 옛 결과만 `equity[0]`으로 대신한다. ② 최대낙폭·최장 낙폭 기간·회복계수는 초기자본을 출발 고점으로 포함한 곡선으로 계산한다(`ResultHandler.anchored_equity`·`max_drawdown_pct` — vbt `max_drawdown`은 곡선만 봐 첫날 낙폭을 놓친다). 분위 그룹 요약·리밸런싱 기간 비교표의 낙폭·샤프도 같은 규약(첫날 수익률 = 첫 평가액 ÷ 초기자본 − 1, vbt `returns`와 동일). ③ 워크포워드 OOS 연결 곡선은 창마다 그 창의 초기자본으로 정규화한다. ④ 몬테카를로(백엔드 `engine/monte_carlo.py`·프론트 `OptimizationPage.runMonteCarloSimulation`)는 첫 값이 초기자본과 다르면 첫날 수익률을 표본에 넣는다(같으면 종전 표본). ⑤ 벤치마크의 첫날 수익률은 창 직전 종가 대비로 잡아 전략과 같은 출발점(첫 거래일 시가 전)에 맞춘다 — 창 직전 값이 없으면 0. 총수익률·총손익·CAGR·샤프는 vbt가 원래 초기자본 기준이다. 배경: 첫날 체결 도입 직후 로그가 "초기자금: 9,748,557원", 카드 ROI가 +42.11%(실제 +38.54%)로 나갔다. 회귀: `backend/tests/test_initial_capital_base.py`, `components/strategy/backtest/BacktestDashboard.initialCapital.test.tsx`.

**FR-BT-014** 시스템은 `rebalancing_period`(daily/monthly/quarterly/yearly)가 지정된 전략에 대해 달력 기준 리밸런싱(reconstitution)을 수행해야 한다: 각 주기의 첫 거래일에 후보를 랭킹 상위 K로 재선정하고, 목표 집합에서 빠진 보유 종목은 매도, 신규 편입 종목은 매수, 유지 종목은 그대로 둬야 한다.

**FR-BT-015** 리밸런싱 실행 방식은 전략의 봉중간 리스크 관리(SL/TP/트레일링 스탑/최대 보유기간) 사용 여부에 따라 분기해야 한다: 봉중간 리스크가 없는 순수 리밸런싱은 비중 리셋까지 수행하는 네이티브 목표비중 방식으로 처리하고, 봉중간 리스크가 혼재하면 현실적 체결을 보존하는 커스텀 reconstitution 루프로 처리하되 유지 종목의 비중이 리셋되지 않음을 경고로 고지해야 한다. (감사 H8)

**FR-BT-015b** 매도 거래의 청산 사유 라벨은 실제 청산 트리거를 구분해 표시해야 한다: 손절/익절/트레일링 스탑/보유기간 만료/상장폐지/데이터 종료/백테스트 종료는 각각의 정밀 라벨로 표시하고, 리밸런싱일에 목표 집합에서 빠져(조건 미충족·랭킹 이탈) 매도된 종목은 "리밸런싱 제외 (목표 종목 이탈)"로 표시해야 한다. 신호·리스크로 설명되지 않는 리밸런싱 편출을 추상적 "전략 매도 조건 충족"으로 뭉개지 않도록, 시뮬레이터(순수·커스텀 루프 두 경로)가 체결일 기준 정밀 사유를 기록하고 결과 처리기가 이를 우선 적용한다. 결과 요약 카드에는 `rebalancing_period`가 `none`이 아니면 리밸런싱 주기 배지를 노출해야 한다. 손절/익절/트레일링 스탑 라벨은 시뮬레이터가 청산을 감지한 시점의 확정 사유(exit_reason_overrides)를 정본으로 사용해야 하며, 실현수익률 크기로 사유를 사후 추론(예: `수익률 ≈ -손절%±1%`)해서는 안 된다 — 봉중간 스탑은 종가(same_close)·익일 시가(next_open)·갭 체결로 실현수익률이 스탑 기준선과 어긋나므로 크기 추론은 진짜 손절을 누락하거나 무관한 매도를 손절로 오귀속한다. (프런트엔드 `resolveTradeReason`도 손실률 기반 재라벨을 하지 않고 백엔드 정본 라벨을 그대로 표시한다.) "백테스트 종료" 라벨은 **사유 없는 기말 강제 정산에만** 붙인다 — 마지막 봉에 발동한 시뮬레이터 확정 사유(손절·익절·트레일링·리밸런싱 편출)와 전략 매도 신호 사유는 마지막 날이라는 이유로 덮어쓰지 않는다(과거에는 마지막 날짜의 모든 매도를 날짜만 보고 "백테스트 종료"로 재라벨했다). 단, 실현수익률-근접 추론은 기말 강제 정산과 우연히 일치하기 쉬워 마지막 봉에서는 채택하지 않는다.

**FR-STR-067** [ETF 유니버스, 2026-07-19] 시스템은 ETF(상장지수펀드)를 백테스트 가능한 독립 유니버스(`universe=["ETF"]`, `universe_id="etf"`)로 지원해야 한다. ① **데이터**: ETF 마스터는 `data/etf-master.json`(FDR ETF/KR 목록 ∩ 로컬 OHLCV 커버리지, `backend/scripts/build_etf_master.py`로 생성·멱등, git 추적이라 커밋·배포로 prod 반영)이며, 엔진은 창 안에서 가격 데이터가 존재하는 ETF만 as-of로 해석한다(`universe_pit.resolve_etf_symbols`). 상폐 ETF는 `backend/scripts/backfill_delisted_etf.py`로 백필됐다(2026-07-19 완료) — FDR KRX-DELISTING엔 ETF가 없고(수익증권 그룹=구식 공모펀드), openapi.krx.co.kr Open API는 증권상품 엔드포인트 미승인(401)이라, data.krx.co.kr 로그인 세션(.env KRX_ID/KRX_PW)으로 'ETF 전종목 시세'(MDCSTAT04301)를 2015-01~현재 전 거래일(3,012거래일) 스윕해 수집했다. **주의**: pykrx의 `get_etf_ticker_list(과거일)`는 현재 상장 종목의 부분집합만 반환해 상폐분을 못 잡는다(2020-02-28 실측: 시세 화면 451종목 vs 멤버십 350종목) — 반드시 일별 전종목 시세 화면을 직접 스윕해야 point-in-time이 된다. 재개 가능 캐시=data/cache/krx-etf-daily/(gitignore, 3,012개 파일), 산출물=data/etf-delisted.json(git 추적, 244종목) → build_etf_master.py가 병합(코드 재사용 시 현재 상장분 우선). 상폐 244종목 중 다수(30종목)는 만기매칭형 채권 ETF(설계상 목표 만기에 자동 상환)였다. 상폐 ETF의 강제청산은 주식과 동일하게 "상장폐지"로 라벨된다(`get_delisting_dates` ETF 마스터 병합). 마스터에 상폐분이 백필된 후로는 ETF 백테스트가 생존 편향 경고를 남기지 않는다(`etf_master_includes_delisted`). **부수 발견**: 백필 후 전체 ETF 유니버스 E2E 검증 중 `DataLoader.load_symbol_data`가 ETF에도 무조건 재무 enrichment(ROE 등)를 시도해 종목마다 KIS 재무비율 API가 헛되이 실패(500)하는 것을 발견 — ETF는 재무제표가 없어 이 데이터가 애초에 쓰이지 않으므로(④의 유니버스별 팩터 레지스트리) `is_etf_symbol` 판정으로 건너뛰게 수정, 전체 ETF 백테스트 Phase1이 16.1s→7.4s로 단축되고 로그 소음이 사라졌다. ② **미혼합**: ETF 유니버스는 주식 시장(KOSPI/KOSDAQ/KOSPI200)과 절대 혼합하지 않는다 — 파서·인터프리터 스키마가 ["ETF"] 단독으로 정규화하고("코스피 ETF"도 ETF — 상품 유형이 시장 언급보다 우선), 엔진은 ETF 마스터만 조회한다. 종목 섹터 분류(sector)는 ETF에 적용되지 않아 비운다. ③ **테마/상품명 필터**(`ParsedStrategy.etf_theme` → `BacktestRequest.etf_theme`, canonical DSL 포함 — None이면 키 제거로 기존 해시 불변): "반도체 ETF"→"반도체", "KODEX 200"→상품명을 결정적으로 추출하되, 어휘집 유지 대신 **ETF 마스터 이름과의 자기검증 매칭**으로 판정한다(`universe_pit.extract_etf_theme` — 상품명 전체 매칭 우선, 'ETF' 직전 토큰의 접미사 중 마스터 이름과 매칭되는 것만 테마로 인정; "사는 ETF"의 '사는'은 매칭 0이라 무시). 엔진 필터(`filter_etf_by_theme`)는 정확한 상품명 일치가 있으면 그 종목만, 없으면 이름 포함 매칭 전체를 대상으로 하고, 매칭 0이면 전체 ETF 유지+warnings 안내(조용한 왜곡 방지). ④ **유니버스별 팩터 검증**(`engine/universe_capabilities.py` — 단일 진실 소스): ETF는 여러 기업을 묶은 상품이라 기업 재무지표(PER·PBR·ROE·부채비율·배당성향 등 재무제표 파생 전부와 시가총액 — ETF에선 AUM이라 의미가 다름)를 전략 조건으로 쓸 수 없고, 가격·거래량 파생 지표(기술 지표 전부, 거래대금)만 허용한다. ETF 전략에 재무지표가 섞이면 **조용히 무시하지 않고** 이유 설명("ETF는 개별 기업이 아니라 여러 종목을 묶은 상품이므로 …을 조건으로 사용할 수 없습니다")+기술 지표 대안 제안 칩으로 되묻는다 — 최초 파싱 경로는 `nl_parser.detect_etf_factor_conflict`(정성 언급 "PER 낮은 ETF" 포함, 진입 누락 되묻기보다 우선), LLM 인터프리터 경로는 `capability_validator`(오류+suggested_fixes)가 담당한다. LLM 프롬프트(인터프리터 규칙 6-1, SYSTEM_PROMPT/MODIFY_PROMPT, 수정 RAG knowledge)에도 동일 계약을 명시해 임의 생성·조용한 제거를 금지한다. ⑤ **체결 비용**: ETF 매도에는 증권거래세가 부과되지 않으므로 명시 옵션이 없으면 `sell_tax_rate=0`으로 시뮬레이션한다. ⑥ **빌더/프론트**: 전략 빌더 시장 선택지에 ETF를 포함하고, ETF 유니버스에서는 가치 전략(PBR/ROE) 선택지를 제시·수락하지 않는다. 전략 요약 유니버스 배지는 "ETF"(+테마 배지 "반도체 테마"/"KODEX 200")로 표시한다. ⑦ **향후 확장**: 유니버스별 지원 팩터는 `universe_capabilities`에서 독립 관리한다(미국주식·채권 등 신규 유니버스는 항목 추가로 확장).

**FR-STR-068** [단일/지정 종목 백테스트, 2026-07-20] 시스템은 사용자가 특정 종목과 전략을 함께 언급하면("삼성전자에 골든크로스 전략을 적용해줘", "005930에 MACD 전략", "하이닉스에 RSI 과매도 전략") 유니버스(종목 선정) 백테스트와 분리된 **단일/지정 종목 백테스트**로 실행해야 한다. ① **모드 분리**: `ParsedStrategy.target_symbols`(종목코드 목록)가 비어 있으면 기존 유니버스 모드, 채워져 있으면 지정 종목 모드다. 변환기(`to_backtest_request`)는 지정 종목 모드에서 `symbols=[지정 코드]`, `universe_id=None`(엔진이 PIT 재해석·섹터 필터를 적용하지 않고 목록을 그대로 사용 — 기존 엔진 계약 재사용), `sector/etf_theme=None`, `backtest_mode="single_asset"`, 표시용 `target_stocks`(코드→등록명)를 만든다. 자금 배분은 지정 종목 수 기준 균등(단일이면 100%, `position_size_pct=100/n`, `max_positions=n`)이며 횡단면 랭킹(`ranking_enabled`)은 끈다. ② **결정적 종목 해석**: 종목명·통칭 별칭·6자리 코드→정규 종목코드 변환은 LLM이 아니라 `stock_analysis/symbol_resolver`(korea-stocks.json 정본) 기반 결정적 추출(`nl_parser._extract_target_symbols`)이 담당하고, LLM은 이 필드를 출력하지 않는다(스키마 설명으로 금지). LLM Interpreter Primary 경로(`STRATEGY_INTERPRETER_MODE=primary`)에서도 컴파일 후 같은 결정적 추출로 채운다(`primary._override_target_symbols` — 날짜 오버라이드와 동형; StrategySpec에 지정 종목 개념이 없어 누락 시 유니버스 전략으로 조용히 넓어지는 사고 방지). 이때 지정 종목이면 유니버스형 청산 누락 되묻기(정기 리밸런싱 추천)는 억제하고 ⑤의 보정이 처리한다. 또한 종목명+'테스트' 발화("삼성전자 단일 종목만 테스트 해보자")는 분류기 결정 규칙이 전략 설계로 라우팅한다(LLM 폴백의 STOCK_ANALYSIS 리다이렉트 오분류 방지). 조사 결합 표기("삼성전자에"/"하이닉스로"/"삼성전자만")와 코드+조사("005930에")를 인식하도록 경계 판정을 확장했다(유니코드 \b 함정 — 한글은 단어문자라 코드 뒤 조사에서 경계 실패). ③ **문맥 가드(오폭 방지)**: 예시("삼성전자 같은/처럼"), 업종 서술("~가 속한 반도체 업종", 업종/섹터/관련주/테마/주도주), 제외·부정("빼고/제외/말고")이 섞인 발화에서는 종목 추출을 포기한다 — 종목질문 리다이렉트(FR-SA-006)·전략 빌더가 합성하는 업종 전략 문구가 단일 종목으로 오폭되면 유니버스 전략이 조용히 바뀌는 사고가 된다. 부정·비교 등 모호 발화는 LLM/되묻기에 위임된다(보수적 실패 = 기존 유니버스 의미론 유지). ④ **복수 종목 처리** [2026-07-26 개정 — 되묻기 폐지(사용자 결정)]: 여러 종목이 함께 지정돼도 '한 종목만 고르기' 칩 되묻기(`detect_symbol_ambiguity`)를 내지 않는다 — 언급된 종목 전체를 함께 백테스트하고, 축소·교체는 채팅 수정 요청("삼성전자만으로 백테스트해줘"·"현대약품은 빼줘"·"SK하이닉스로 바꿔줘")이 ⑥의 수정 경로로 처리한다(실측 사고 2026-07-26: 테마 유니버스 10종목 확정 후 "종목을 교체 할 수 있나?" 질문에 종목 선택 칩 10개가 떠 흐름이 끊김 — LLM 수정 경로가 있으므로 채팅 입력만으로 충분). [2026-07-28 개정 — 다종목=포트폴리오] 복수 지정 종목(테마 유니버스 자동 적용 포함)은 단독 종목이 아니라 포트폴리오이므로 리밸런싱 주기를 되묻는다 — 최소 조건 게이트의 단독 종목 면제는 **지정 종목이 정확히 1개**일 때만 적용한다('지정 종목 존재=단독'으로 판정해 질문 없이 기본값 '설정 안 함'으로 확정되던 사고, '모바일솔루션 관련주'). 백엔드 `_missing_backtest_conditions`·프론트 `getNextMissingBacktestCondition` 동일 규칙이며, 칩에 '리밸런싱 안 함'을 포함해 사용자가 결정하고, 명시 거부는 누적 프롬프트 재파싱에서 같은 질문을 반복하지 않는다(`_mentions_rebalancing_negation` 게이트 인지). 요약 카드도 다종목 지정은 사용자가 답하기 전까지 리밸런싱 기본값을 확정된 것처럼 표시하지 않는다(단독 종목 1개는 교체가 없어 기존대로 '설정 안 함' 표시). ⑤ **청산 누락 추천 보정**: 지정 종목 전략에 청산 조건(청산 신호·보유기간·손절/익절/트레일링/MDD·리밸런싱)이 전혀 없으면 조용히 임의 실행하지 않는다 — 크로스오버 계열 진입(ma_crossover/ema/macd)은 반대 신호 청산을 추천 기본값으로 적용하고 notices로 알리며, 그 외 진입은 자동 주입 없이 "기간 종료까지 보유" 사실과 추가 옵션을 notices로 안내한다(`apply_single_asset_adjustments`, `_build_parse_result` 공유 — 최초 파싱·수정·후행 검증 교정 모두 적용). 이 보정 덕에 지정 종목+기술 진입 단독 프롬프트는 룰 fast-path에 남는다(유니버스 전략의 '진입만 있으면 LLM 위임' 게이트 면제). ⑥ **수정 경로**: 종목 교체("SK하이닉스로 바꿔줘" — 별칭 표면형을 잔여 판정에서 차감해 fast-path 유지)·**개별 삭제**("현대약품은 빼줘" — 기존 지정 목록에서 그 종목만 제거)·명시적 시장 전환 시 지정 해제("코스닥 전체로")·업종 전환 시 지정 해제("반도체 업종으로")를 결정적 통합 판정(`_target_change_from_utterance`)이 LLM diff보다 우선 처리하며, 무관 수정("손절 5%로")은 지정을 보존한다. **개별 추가("제주반도체도 추가해줘"=기존 지정과의 합집합)는 결정론이 판정하지 않는다**(2026-07-26 확정 — 추가/교체 구분은 원문 의미 해석이라 regex 어휘 확장 금지, 사용자 지시로 결정적 추가어 판정 철회): LLM 인터프리터 수정 경로가 `/universe/symbols` add 패치(값=사용자 표기 문자열 그대로, 프롬프트 규칙 10-1)로 처리하고, 스키마 정규화·`universe_resolver`·검증 warning이 조용한 소실을 막는다(계약 문서 § 11-2 '막은 구멍 2', 회귀: test_strategy_conversation.py 종목 패치 3케이스). 레거시 결정론 레인은 추가 발화를 구분하지 못한다 — 이는 § 11 격차 1의 이관 대상이지 regex로 메울 결함이 아니다. 같은 사고의 짝 수정: 섹터 변경 판정(`_sector_change_from_utterance`)은 판정 전에 인식된 종목명 표면형을 가린다(`_mask_stock_name_mentions` — 기존 regex의 오해석을 줄이는 방향) — "제주반도체도 추가해줘"의 종목명 내부 조각('반도체'+'도 추가')이 업종 추가로 오폭해 지정 종목 해제까지 연쇄되던 사고 방지(회귀: test_single_asset_backtest.py 마스킹 케이스)(섹터 FR-STR-066 ⑥/⑦과 동형 — rule fast-path·LLM diff 병합·`_apply_prompt_overrides` 세 지점 배선). [2026-07-26 사고 수정] 삭제 판정은 지정/교체 판정보다 **우선**한다 — 문맥 가드(③)가 '빼고/제외/말고'만 알고 '빼줘/빼조(오타)'류 활용형을 놓쳐, "현대약품은 빼조"의 종목 언급이 '새 지정'으로 오독돼 테마 유니버스 10종목이 현대약품 단일 종목으로 교체되던 사고. 삭제 판정(`_removal_mentioned_target_refs`)은 종목 표면형 바로 뒤(종목/주식 명사·조사 허용)에 삭제어(빼/제외/제거/삭제/지워/없애/없이)가 인접해야 성립한다 — 인접 요구가 "현대약품 손절 빼줘"(청산 조건 삭제)와의 혼동을 막는다(섹터 개별 삭제 패턴과 동형). `_extract_target_symbols`도 삭제어 인접 언급은 지정으로 보지 않는다(초기 파싱의 단일 종목 오폭 방지). 회귀: `test_single_asset_backtest.py` 삭제 6케이스. ⑦ **해시/스키마 관통**: `target_symbols`는 canonical DSL(정렬, 빈 값은 키 제거로 기존 해시 불변)에 포함돼 종목별로 다른 strategy_id(캐시 충돌 방지)를 가지며, `BacktestRequest`에 `backtest_mode`/`target_stocks`를 선언해 pydantic extra=ignore 드롭 함정을 막는다. ⑧ **표시**: 전략 요약의 유니버스 배지 대신 "삼성전자 (005930)" 종목 배지("대상 종목" 라벨), 포트폴리오 배지는 "최대 N종목" 대신 "단일 종목 집중 투자"(복수면 "지정 종목 N개 균등 투자")로 표기한다(파싱 카드·실행 요청 요약·저장 DSL 요약 모두). [2026-07-28 확장] 대화 진행 요약 카드('현재까지 이해한 전략입니다', `builderProgressPresentation`)도 같은 표기를 쓴다 — 지정 종목 모드에서 `parsed.max_positions` 기본값을 "최대 보유 10종목"으로 표시하면 변환기 실행값(①의 max_positions=지정 종목 수 균등)과 다른 정보가 노출된다('모바일솔루션 관련주' 카드-실행 불일치). 유니버스 전략의 "최대 보유 N종목" 표기는 불변. ⑨ **비용/기본값**: 수수료·슬리피지·초기자금·기간·체결 시점은 기존 플랫폼 기본값과 시장별 비용 모델(증권거래세 포함)을 그대로 사용하고, 상장폐지 종목 강제청산 등 PIT 의미론도 유니버스 모드와 동일하게 적용된다. 한계: 현재 상장 종목명만 해석된다(상폐 종목명 지정은 미지원 — korea-stocks.json 정본), 해외 종목 별칭은 데이터가 없어 지정으로 승격하지 않는다. ⑩ **LLM 해석 경로**(2026-07-26, 자연어 해석 계약 1a+4): 인터프리터 파이프라인에서는 LLM이 지목한 종목 표현을 `StrategyIntent.universe.symbols`에 원문 그대로 담고(종목코드 환각 금지), `strategy_conversation/registry/universe_resolver.resolve_symbols`가 마스터 조회로 6자리 코드를 확정해 컴파일러가 `target_symbols`에 배선한다. 업종 표현도 같은 모듈의 `resolve_sectors`(정본 사전→지식그래프)로 정본화되며, 해석하지 못한 표현은 조용히 버리지 않고 반환·기록한다. 사용자 원문을 다시 읽는 결정적 추출(`_extract_target_symbols`)은 이 단계에서 폴백으로 공존한다 — 상세는 `docs/nl_interpretation_contract.md`.

**FR-STR-068b** [단일 종목 연구 프로파일 + 프로파일 기반 대화, 2026-07-24] 시스템은 단일 종목이 지정되면 그 종목을 티커 문자열로만 다루지 않고, 백엔드가 종목의 실제 데이터를 결정론적으로 사전 분석한 **구조화된 종목 프로파일**(`StockResearchProfile`)을 생성·캐시하고, 대화(빌더·코치·파싱 안내)가 이를 근거로 동작해야 한다. ① **프로파일 생성**(`engine/stock_profile.py::StockProfileService`): 수정주가·기업행사 보정이 적용된 OHLCV에서 데이터 커버리지(기간·결측률), 설명 통계(연환산 변동성·상승일 비율·왜도/첨도·갭 빈도·MDD/평균 낙폭/회복 기간·거래대금 중앙값·추세 비율), 대표 신호의 발생 횟수·연간 빈도(고정 격자: RSI 임계 교차, 골든크로스 3조합, MACD, 볼린저 상/하단, 돌파 3기간, 거래량 급증, 고점 대비 하락, CCI, 스토캐스틱)를 계산한다. LLM은 원시 시계열을 읽거나 계산하지 않는다 — 직렬화된 프로파일 요약만 전달된다. ② **정직성**: 계산 불가 필드는 null(임의 추정 금지 — 예: 시장지수 상관은 지수 시계열 부재로 null), 파이프라인에 없는 데이터(외국인/기관 수급·공매도·실적 발표일·배당/공시/뉴스 이벤트·시장/업종지수·분봉)는 `unsupported_features`로 선언하고 지원하는 것처럼 표현하지 않는다. 재무 지표는 parquet 병합이 PIT-safe(공시 접수일 available_from, 폴백 결산일+90일)임을 `point_in_time_safe`로 표시한다. ③ **과최적화 방지**: 프로파일은 설명 통계와 신호 빈도만 담는다 — 수익률 기준 사후 최적 파라미터(best value)는 계산·저장·추천하지 않으며, 파라미터는 해석 가능한 탐색 범위(예: RSI 20~40 step 5)만 제안한다. ④ **캐시**: `data/cache/stock_profiles/{symbol}.json`, 소스 fingerprint(parquet mtime+size)+`PROFILE_VERSION`으로 무효화, 섹션(technical/signals/financial)별 fingerprint 기록으로 향후 부분 갱신 지원. ⑤ **질문 템플릿 필터링**(`engine/stock_question_templates.py`): 템플릿이 필요 데이터 피처·최소 신호 횟수·advanced 여부를 선언하고, 선택 로직이 프로파일 근거로 노출/제외를 결정한다. 제외는 조용히 숨기지 않고 이유를 담는다. 단일 종목 기본 질문에 횡단면(종목 선별) 조건은 없다 — 재무 조건(PBR/PER/배당수익률)은 '그 종목의 당시 값' 시계열 신호(advanced)로만, 명시 요청 시 노출한다. 발생 횟수가 최소 기준(10회) 미만이면 희소 신호 경고("기준 완화/기간 연장"), 연간 빈도가 과다(30회 초과)하면 거래비용·슬리피지 경고를 붙인다. ⑥ **파스 흐름 검증**(`engine/single_asset_review.py`): 파싱된 단일 종목 전략의 진입 신호를 격자에 근사('유사 조건 기준' 명시)해 희소/과다 경고, 재무 조건 데이터 미보유 시 "지원할 수 없습니다"+기술 지표 대안 안내, 보유 시 PIT 적용 사실 안내를 비차단 notices로 전달한다(조건 임의 삭제·실행 차단 없음, 프로파일 실패는 파싱을 깨지 않음). ⑦ **빌더 단일 종목 모드**(`BuilderState.single_symbol`): 종목 선별용 질문(유니버스·보유 종목 수·리밸런싱 주기)을 건너뛰고, 첫 질문을 "언제 사고 언제 팔 것인가"(프로파일 신호 횟수를 근거로 선택지 설명)로 바꾸며, 모멘텀 랭킹·가치 스크리닝 선택은 이유 설명+대안과 함께 되묻는다. 확정 시 target_symbols·max_positions=1·리밸런싱 없음으로 DSL을 직접 조립한다. ⑧ **API**: `GET /stock/{symbol}/research-profile`(include_advanced 토글)이 데이터 기간·가능 전략 카테고리·노출 질문(근거 reason·경고)·제외 질문(이유)을 반환한다. reason은 데이터 사실만 담고 수익 보장·우월 표현을 쓰지 않는다(규제 안전). ⑨ **코치**: 단일 종목 전략 코칭 시 프로파일 압축 JSON과 행동 제약(미보유 데이터 지원 표현 금지, 10회 미만 신호 신뢰 경고, 사후 최적값 추천 금지, 미래 예측·수익 보장 금지, null 추정 금지, 선별 대신 진입/청산 질문)을 주입한다. ⑩ **관측성**: 프로파일 버전·노출/제외 질문 수·경고 수를 구조화 로그로 남긴다.

**FR-STR-069** [용어 그라운딩 — 인터넷 검색 기반 업종/테마 용어 학습, 2026-07-24] 시스템은 사용자가 언급한 업종/테마 용어를 내부 지식(결정적 섹터 어휘 + LLM)으로 해석하지 못하는 경우, 인터넷 검색으로 용어의 의미를 학습해 지원 업종으로 매핑해야 한다(`engine/term_grounding.py`). ① **해석 체인**: 빌더의 sector_resolver는 어휘집 결정적 조회 → 내부 지식 LLM 매핑(`llm_extract_sector`, 기존 경로) → 검색 그라운딩 순으로 동작한다(`resolve_sector`, `api/intent_routes.py` 배선). ② **검색 그라운딩**: 미해결 시 LLM이 문장에서 테마 용어를 추출하고("ess 관련 투자 전략" → "ESS"), 네이버 API 허브 검색(백과사전 + 뉴스 `"{용어} 관련주"`·`"{용어} 수혜주"` 각 8건 + 웹문서, 4쿼리 — '수혜주' 쿼리는 2026-07-25 리콜 보강: 스니펫이 제목+요약 2줄뿐이라 '관련주' 기사 표본만으론 본문 종목 나열이 잘리는 실측(BTS 학습 시 넷마블 미포착), 링크 dedupe로 같은 기사의 교차지지 이중 계산은 차단, 스니펫 상한 24)의 스니펫을 근거로 LLM이 정의 한 문장과 지원 업종 매핑을 산출한다. 출력 업종은 반드시 `normalize_sector` 게이트를 통과해야 하며(목록 밖 이름 → None), 실패 시 기존 업종 되묻기 흐름으로 폴백한다. **[2026-08-24] 용어 추출은 문장 입력 전용 단계다** — 호출부가 이미 뽑아낸 용어를 넘기는 경로(`ground_term` 도구: planner·term-in 체인, `resolve_sector(text_is_term=True)`)에서는 추출 LLM이 null을 내도 입력 자체를 검색어로 삼아 검색을 진행한다. 상류가 '유니버스 표현'으로 판정해 넘긴 낱말을 문맥이 떼어진 채 재심사하면 상류 판정과 모순되고 검색이 영영 실행되지 않는다(실측 사고: '블랙핑크 관련주' — planner가 검색을 선택했는데 추출 단계가 `{"term": null}`을 내 네이버 검색이 한 번도 실행되지 않고 되묻기로 종결). 문장 입력(기본 경로)은 기존 계약대로 추출 실패 시 검색하지 않는다(문장 전체를 검색어로 쓰는 회귀 방지). ③ **어휘집 영속 캐시(같은 용어 재검색 금지)**: 검색이 실제 수행되면 결과(원문 용어·정의·매핑 업종·출처 상위 3건·검색 시각)는 매핑 성공/불가 모두 `data/term_lexicon.json`에 저장되고, 이후 같은 용어는 검색·LLM 없이 어휘집에서 결정적으로 해석된다(라틴 약어는 라틴 문자 lookaround 경계 매칭 — 'process'의 'ess' 오매칭 방지). 단, 검색 호출 자체가 실패(네트워크·쿼터·자격증명 없음)한 경우에는 저장하지 않아 복구 후 재시도할 수 있다. 어휘집은 런타임 학습 산출물로 git에 추적하지 않는다(환경별로 자라남). ④ **안전 장치**: 검색 결과 본문은 신뢰할 수 없는 외부 데이터로 취급해 그라운딩 프롬프트가 본문 내 지시·명령·추천을 무시하고 사실 추출만 수행하도록 명시하며, 검색 자격증명(`NAVER_CLIENT_ID`/`NAVER_CLIENT_SECRET`) 미설정 시 그라운딩 단계는 조용히 비활성화되고 기존 체인만 동작한다. **[2026-09-16] 런타임 침묵은 유지하되 기동 시 레인 상태를 로그 한 줄로 드러낸다** (`term_grounding.startup_status_line` — 자격증명이 없으면 경고, 있으면 어휘집 용어 수). 프로덕션 박스 `.env`에 자격증명이 없어 학습 레인이 죽어 있었는데 아무 신호가 없어 '로컬만 되는' 결함으로 보였던 사고 보정이다('석유 관련주' — 어휘집 `data/term_lexicon.json`이 prod에 아예 생성되지 않았다). 배포(CI)는 박스 `.env`의 두 키가 없거나 비어 있을 때 GitHub Secrets 값으로 주입하고, 기동 직후 같은 상태 줄을 배포 로그에 남긴다(`.github/workflows/ci.yml` — 수동으로 채운 값은 덮어쓰지 않는다). ⑤ **'검색 중...' 진행 표시**: 빌더 스텝은 SSE 엔드포인트(`POST /strategy/builder/step-stream`, parse-stream의 stage_holder 폴링 패턴 재사용)로 처리되며, 그라운딩이 인터넷 검색에 실제 진입하면(`resolve_sector`의 `on_search` 콜백) 결과 전에 `{"type":"stage","stage":"searching"}` 이벤트를 흘리고 프론트 로딩 버블이 '분석 중...' 대신 '검색 중...'을 표시한다. [2026-07-25 확장] 개념 해석 체인(어휘집·지식그래프·내부 LLM) 진입 시에도 `resolve_sector`의 `on_kg_lookup` 콜백이 `{"type":"stage","stage":"kg_lookup"}` 이벤트를 흘려 프론트가 '개념 확인 중...'을 표시한다(검색 진입 시 '검색 중...'으로 교체). parse-stream 경로(`_learn_unknown_sector_term`)도 동일하게 배선되며 체인 종료 후 'parsing'으로 복귀한다. 프록시(`app/api/strategy/builder/step/route.ts`)는 URL 계약을 유지한 채 SSE를 파이프하고, 클라이언트 헬퍼는 응답 content-type으로 SSE/JSON을 분기한다(기존 JSON 계약 호환 — 어휘집/내부 LLM 히트처럼 검색이 없는 턴은 stage 이벤트 없이 기존과 동일하게 동작). 기존 `POST /strategy/builder/step`은 호환용으로 유지된다. [2026-08-05 확장] parse-stream의 LLM 인터프리터 기본 경로는 Ollama 응답을 스트리밍(NDJSON)으로 받아 **생성 중인 StrategyIntent 섹션 키를 진행 단계로 방출**한다 — planner-first 유니버스 해석 진입 시 `universe`, 이후 출력이 도달한 섹션에 따라 `universe`/`entry`/`exit`/`risk`/`settings`(프론트 표시: '유니버스 분석 중...'/'매수 조건 분석 중...'/'매도 조건 분석 중...'/'리스크 관리 분석 중...'/'설정 분석 중...'(포트폴리오·백테스트 섹션)). 판정 입력은 사용자 원문이 아니라 LLM이 생성 중인 JSON의 키 위치다(형식 관찰 — 자연어 해석 아님). 수정 턴(patches 출력, 섹션 순서 없음)과 on_chunk 미지원 chat 주입(테스트 스텁·QA 하니스)에는 적용되지 않고 기존 단계 표시로 동작한다. [2026-09-08 확장] LLM 호출 자체가 실패해 전송 계층이 다시 보내는 동안(OpenRouter 상류 일시 오류 재시도·Ollama 레인 폴백 재전송·Modal 콜드스타트 재시도)에는 `{"type":"stage","stage":"retrying"}`가 흘러 프론트가 '재확인 중...'을 표시하고, 재시도가 끝나면(성공·실패 모두) 직전 단계로 되돌아간다(`backend/llm_progress.py` — 요청 단위 진행 holder를 워커 스레드 컨텍스트에 결속, parse-stream·builder step-stream 공통). ⑥ **파싱 경로 사전 학습** [2026-07-25]: 검색 그라운딩은 빌더뿐 아니라 파싱 파이프라인에도 배선된다 — `_run_nl_parse`(main.py)가 파싱 전에 게이트(`nl_parser.mentions_unresolved_sector`: 업종/테마 큐는 있는데 결정적 추출이 실패한 입력, 섹터 되묻기와 동일 판정)를 통과한 입력을 `term_grounding.learn_sector_term`으로 학습한다. 실측 사고: "마운자로 관련주 전략을 만들어보자"가 파싱 경로(인터프리터 primary)로 흘러 검색 없이 미지원 처리 — 그라운딩이 빌더 resolver에만 배선돼 있었음. 학습분 해석은 그래프 단일 경로다 — [2026-07-25 읽기 경로 통합] 학습 노드가 지식그래프 스캔 인덱스에 포함되므로 `_extract_sector`의 KG 폴백(`resolve_sector_from_text`)이 시드·학습 용어를 함께 해석한다(초기 구현의 어휘집 스캔 폴백은 제거됨, FR-STR-070 ③). 해석 성공 시 notices로 해석 사실을 안내하고("'마운자로'은(는) 인터넷 검색으로 확인해 '바이오/제약' 업종 관련으로 해석했어요"), 인터프리터의 업종 질문(`strategy.universe.sectors`)과 같은 테마를 가리키는 미지원 안내는 제거한다(`_prune_clarifications_filled_by_overrides` 확장 — 반영된 전략과 모순되는 되묻기/안내 방지). parse-stream도 검색 진입 시 `stage:"searching"`을 방출하고 프론트가 '검색 중...'을 표시한다. 한계: 현재 버전은 학습한 테마를 기존 지원 업종으로 근사한다 — 종목별 테마 멤버십(시점별 유니버스)은 다루지 않는다. ⑦ **TTL 조건부 재검토** [2026-07-25]: ③의 재검색 금지 계약에 TTL(`TERM_REGROUND_TTL_DAYS`, 기본 90일, 0 이하=영구 캐시)이 적용된다 — `searched_at`이 TTL을 넘긴 **미해결 항목**(매핑 불가 부정 캐시)은 사용자 재언급 시 조건부 재검색을 허용한다(1월에 매핑 불가였던 용어가 7월엔 부상한 테마일 수 있음 — 부정 캐시가 세상 변화에 영영 갇히는 문제 보정). 성공 항목(sector 있음)은 체인 ①에서 즉시 반환되므로 핫패스 재검색이 없고, 배치 재그라운딩(`scripts/kg_relink_audit.py --reground-stale`)이 담당한다. 재학습은 덮어쓰기가 아니라 **병합**(`_merge_entry_edges`)이다 — 기존 엣지의 콘솔 검토 상태(verified/rejected/pending)를 그대로 보존하고 새 제안만 추가한다(rejected 부활·verified 강등 금지). `searched_at`이 없는 레거시 항목은 재검색하지 않는다(보수). ⑧ **검색 소진 시 '전략 불가' 종결 안내** [2026-07-26]: 검색 그라운딩까지 실제 수행됐는데(어휘집 `searched_at` 원장 존재) 업종 매핑도, 테마 유니버스 자동 적용(FR-STR-071 ④)도 실패한 테마 언급('리센즈 관련주')은 오타 정정 되묻기(SECTOR_REASK) 대신 **'관련 상장사를 확인하지 못했고, 관련주를 찾을 수 없어 이 테마로는 전략을 만들 수 없다'는 종결 안내**(사용자 문구 결정 2026-07-26: '인터넷 검색' 표현은 사용자 노출 문구에서 제외 — 판정 조건은 검색 수행 원장 그대로)를 반환해야 한다(`nl_parser.THEME_NOT_FOUND_QUESTION` — 칩에 '업종 상관없음' 미포함: 존재하지 않는 테마를 억지 매핑하거나 테마를 버린 채 조용히 진행하지 않는다). 검색이 아직 수행되지 않았거나 검색 호출 자체가 실패한 용어(어휘집 미저장)는 기존 되묻기를 유지해 정정·재시도 여지를 남긴다. 반대로 테마 유니버스 자동 적용이 관련 상장사를 **찾아 확정한 경우**(parsed.target_symbols 설정)에는 테마 언급이 종목 목록으로 해석 완료된 것이므로 되묻기·종결 안내를 모두 내지 않고 다음 최소 조건 질문으로 전략 만들기를 계속하며, 미지원 개념 안내에서도 'sector'를 제외한다('설정했어요'와 '지원되지 않아요' 공존 모순 방지 — 실측 사고 2026-07-26 '이재명 관련주': 10종목 확정 후에도 업종 되묻기가 떠 흐름이 끊김). 미해결 업종/테마 질문(되묻기·종결 안내 공통)에는 `clarification_priority="sector_unresolved"` 마커가 실리며, 프론트 explicit 설정 게이트와 primary 인터프리터 질문은 priority가 실린 백엔드 질문을 덮어쓰지 않는다(실측 사고 2026-07-26: 백엔드가 섹터 되묻기를 반환했으나 프론트 게이트가 삼켜 일반 시장 질문으로 조용히 강등).

**FR-STR-070** [Investment Knowledge Graph — 투자 지식 그래프 Phase 1, 2026-07-24] 시스템은 투자 개념·산업·공급망·기업·ETF·재무지표·거시경제를 노드(Node)와 관계(Edge)로 잇는 지식 그래프를 유지하고, 자연어 속 개념을 그래프 탐색으로 해석해야 한다(`engine/knowledge_graph.py`, 설계 상세는 `docs/knowledge_graph.md`). ① **그래프 합성(정본 재사용)**: 시드 그래프(`data/knowledge-graph.json`, git 추적·수동 큐레이션 — HBM·SMR·ESS·전력기기·양극재·휴머노이드 로봇 등 개념 30여 개, 관계 100여 개. [2026-07-25] 시드 확장은 Concept–Stock Builder 절차(`docs/kg_concept_builder.md`)를 따른다 — 공식 근거(공시·기업 IR·ETF 공식 자료) 조사 원장을 `data/kg-research/<concept>.json`에 보존하고 Core/Strong 관계만 시드에 편입 — 총 14 Concept: 전고체 배터리·비만치료제·유리기판·액침냉각(기업 엣지 없이 개념 관계만)·폐배터리 리사이클링·우주발사체·탄소배출권(무소속 개념)·전력반도체·CXL·온디바이스 AI(다업종 무소속)·AI 에이전트·양자컴퓨터(기업 엣지 없음)·인공위성·마이크로바이옴)에 섹터 노드(`sector:<정본명>`, `CANONICAL_SECTORS` 자동 생성), 기업 노드(`company:<symbol>`, korea-stocks.json에서 참조 시 자동 생성), ETF 노드(`etf:<symbol>`, etf-master.json), 학습 노드(`learned:<key>`, FR-STR-069의 term_lexicon 오버레이 편입 — 검색 학습이 그래프도 함께 키운다)를 로드 시 합성한다. 정본을 손으로 두 번 적지 않으며, 엣지 끝점·타입은 로드 시 검증되고 시드 무결성 테스트가 위반 0을 단언한다(오타 심볼 fail-fast). ② **관계 어휘**: is_a/part_of/belongs_to/related_to/uses/used_by/used_in/requires/depends_on/supplier/customer/competitor/produced_by/manufactured_by/demanded_by/invests_in/related_company/related_etf/related_metric/related_macro/related_news/related_universe/cause/affected_by/benefits_from/risk_factor/substitute/next_generation/predecessor/successor. ③ **결정적 개념 인식**: 문장 스캔은 개념 노드의 이름·별칭을 대상으로 하되, 자동 생성 노드(sector:/company:/etf:)는 각자 기존 경로(섹터 정규화·종목 인식)가 담당하므로 제외하고, `normalize_sector`가 이미 해석하는 용어(AI·원자력 등)도 인덱스에서 제외해 상류 섹터 어휘와 이중 매칭되지 않는다. [2026-07-25 읽기 경로 통합] **학습 노드(learned:)는 스캔 인덱스에 포함**된다 — 시드·검색 학습 용어를 그래프 단일 경로로 인식하며(어휘집 별도 스캔 폴백 제거), 같은 용어가 시드·학습 양쪽에 있으면 시드가 이긴다(큐레이션 우선). 어휘집(term_lexicon.json)은 지식 저장소가 아니라 **학습 원장**(영속 저장·부정 캐시(매핑 불가 재검색 금지)·pending/rejected 검토 대기열·출처 증거)으로 역할이 한정된다 — 매핑 불가 항목은 노드가 아니므로 스캔에도 없다. 라틴 약어는 lookaround 경계 매칭(FR-STR-069와 동일 관례). ④ **섹터 해석(체인 ①b + 파싱 경로)**: FR-STR-069 해석 체인의 어휘집 조회와 내부 지식 LLM 사이에 그래프 결정적 조회가 배선된다. [2026-07-25 확장] 빌더 resolver뿐 아니라 **파싱 파이프라인의 결정적 섹터 추출(`nl_parser._extract_sector`)**에도 배선된다 — 어휘 밖 테마어(ESS·HBM·SMR)는 업종 큐(섹터/업종/관련/테마) 동반 시 그래프 시드로 해석한다(큐 없는 개념 언급 "금리가 오르면 매수"는 업종 제한으로 오폭하지 않음). `_extract_sector`는 규칙 파스·시드·수정(`_sector_change_from_utterance`)·LLM 폴백 드리프트 복구(`_apply_prompt_overrides`)가 공유하므로 전 경로가 한 번에 커버된다. 실측 사고(2026-07-25): "ess 관련 투자"가 분류는 전략 설계로 됐지만 파싱 경로(빌더 아님)로 흘러 — 인터프리터 UNSUPPORTED_REQUEST 폴백 → 규칙 파서 — KG가 빌더 resolver에만 배선돼 있어 ESS가 조용히 소실되고 빈 전략 최소 조건 게이트로 진입. — 개념에서 소속 엣지(is_a/part_of/belongs_to)만 깊이 3까지 따라 정본 섹터에 닿으면 즉시 반환(시드 개념은 LLM·검색 없이 해석: "SMR" → is_a 원자력 → 에너지/원자력). 서로 다른 섹터 둘 이상에 닿거나(복수 개념 충돌) 데이터센터처럼 의도적으로 다업종인 테마(소속 엣지 없음)는 None으로 기존 되묻기/LLM 폴백을 유지한다. ⑤ **관계 확장 조회**: `related_universe(text)`가 개념 주변을 BFS(기본 깊이 2)로 펼쳐 관련 섹터·상장기업·ETF·개념을 도달 경로(via: "HBM –produced_by→ SK하이닉스")와 함께 반환한다 — 백테스트 유니버스 후보의 객관적 관계 데이터이며 UI 배선은 Phase 2.  ⑦-1 [섹터 노드와 테마 노드의 구분, 2026-07-30] 지식그래프는 **섹터(업종)**와 **테마**를 `category`로 구분한다 — `industry` vs `theme`/`theme_catalog`. 성격이 다르기 때문이다: 섹터는 **전수 분류**(모든 종목이 정확히 하나에 속함)이고 테마는 **큐레이션된 부분집합**(근거 있는 종목만, 없다는 것은 '테마 밖'이라는 올바른 답). 섹터 노드는 `CANONICAL_SECTORS`에서 자동 생성되며 메타를 **정본에서 파생**해 담는다(손으로 두 번 적지 않는다): `synonyms`(`_SECTOR_SYNONYMS` 역방향), `ksic_codes`(`KSIC_SECTOR` 역방향), `member_count`(`_load_sector_map`), `composition_note`(묶음 섹터만), `is_combined`. ⑦-2 [섹터 소속 정본을 KG로, 2026-07-30] 섹터 소속(`company -belongs_to→ sector`)의 정본은 **KG**다. 인터프리터가 지식을 찾는 곳이 KG인데 소속이 `korea-stocks.json`에만 있어 그래프로 "이 섹터에 어떤 종목이 있나"를 답할 수 없었다(`related_universe('원자력')` → `{}`). 소속 데이터는 `data/kg-sector-membership.json` 오버레이에 두고 KG 빌드 시 편입한다 — 3천여 엣지가 손 큐레이션 시드(`knowledge-graph.json`)를 덮지 않게 하는 관례이며 `theme_catalog`·`learned` 오버레이와 동형이다. `universe_pit._load_sector_map`이 그 엣지를 읽고(오버레이 부재 시에만 파일 폴백), `korea-stocks.json`의 `sector` 필드는 **파생 캐시**로 강등됐다(참조부 71곳 호환). 불일치는 `test_stock_file_sector_is_a_derived_cache_of_the_kg`가 잡는다. 주의: 오버레이는 **상폐 종목과 우선주까지** 담아야 한다 — 빼면 섹터 유니버스에 생존 편향·누락이 생긴다(실측 회귀 2건: 상폐 누락 에너지/원자력 72→66, 우선주 상속 누락 72→66). 병합 규칙은 `universe_pit.sector_map_from_files`가 단일 구현을 갖고 오버레이 빌더가 그것을 쓴다. 섹터를 옮기거나 분할하면 개념 엣지도 함께 옮겨야 한다 — 카지노를 레저로 옮겼는데 `casino -part_of→ sector:미디어/엔터` 엣지가 남아 있던 실측 사고를 `test_kg_concept_edges_follow_sector_moves`가 막는다. ⑥ **규제 안전**: 그래프는 생산·공급·소속 등 객관적 관계만 저장·표시하고, 추천·전망·우열 판단을 표현하는 노드/엣지는 만들지 않는다. 한계(Phase 1): 개념→지정 종목/ETF 유니버스 자동 생성, 뉴스 키워드 연결은 미배선 — `docs/knowledge_graph.md`의 Phase 2/3 참조. (검색 그라운딩의 그래프 엣지 자동 생성은 FR-STR-070b로 구현됨.)

**FR-STR-070b** [지식그래프 학습 편입 — 검색 그라운딩의 관계 엣지 자동 생성, 2026-07-25] 검색 그라운딩(FR-STR-069)이 새 용어를 학습할 때 정의·섹터뿐 아니라 기존 시드 개념과의 **관계 엣지**도 함께 학습해 지식그래프를 키워야 한다(`engine/term_grounding.py::_propose_edges`). ① **결정적 후보 탐색(닫힌 세계)**: 후보 앵커는 LLM 탐색이 아니라 검색 스니펫 본문에 실제 등장한 시드 개념(`knowledge_graph.find_concepts` — 자기 자신 제외)만 결정적으로 수집하고, LLM은 그 닫힌 목록 안에서 관계 유형만 고른다(존재하지 않는 노드를 지어내는 환각 차단). 후보 밖 타깃·미허용 유형은 게이트에서 드롭한다. ② **관계 유형 제한**: 학습 엣지는 객관적 관계 서브셋(is_a/part_of/belongs_to/related_to/uses/supplier/competitor)만 허용 — 추천·전망·우열 관계 금지(규제 안전, 프롬프트에도 명시). ③ **자동 승격 + 사후 반려**: 서로 다른 출처(evidence 링크) 2개 이상이 같은 앵커를 지지하면 자동 `verified`, 1개면 `pending`. 신뢰도는 LLM 자기보고가 아니라 출처 수 기반이다. 엣지는 어휘집 엔트리(`edges: [{type, target, support, status, evidence}]`)에 저장되며 git 추적 시드(knowledge-graph.json)에는 쓰지 않는다(시드=수동 큐레이션, 학습분=런타임 산출물 — 출처 분리). ④ **그래프 합성 게이트**: KG 로더는 `verified` 엣지만 그래프에 합성하고(타입·타깃 로더 재검증) pending/rejected는 제외한다. 섹터 매핑 없이 verified 엣지만 있는 용어도 노드로 편입한다. 결정적 섹터 해석(①b)·유니버스 경로에는 시드+verified만 관여한다. ⑤ **관리자 검토**: 운영 콘솔 Knowledge 탭(`/api/admin/knowledge` — requireAdmin 404 은닉·감사 로그)에서 학습 용어·엣지를 검토하고, verified 엣지 사후 반려·pending 수동 승인·잘못 학습된 용어 삭제(삭제 시 다음 언급에 재검색으로 재학습)를 수행한다. 어휘집 파일이 SOT이며 백엔드 로더는 파일 mtime으로 자동 재로드한다. [2026-07-27 UI 정비] 관련 기업 엣지 자동 등록(FR-STR-071 ① 개정) 후 검토 대기열이 아닌 감사·교정 도구로 성격이 바뀌어, 용어 박스는 기본 접힘(헤더에 용어·업종·학습 시각·엣지 수·검토 대기 배지, 클릭 토글)이고 정의·수동 엣지 추가·엣지 목록은 펼침 시에만 표시한다. 검색 입력(용어명·정의·엣지 대상 종목명 부분일치 — "이 종목이 어느 테마로 학습됐나" 역조회)이 목록을 필터링하며 검색 중 일치 항목은 자동으로 펼친다. 실측(2026-07-25): 'CoWoS' 학습 시 LLM이 제안한 'part_of→메모리 반도체'(부정확) 엣지가 출처 1개라 pending으로 억류됨 — 검증 게이트가 의도대로 동작. ⑥ **재연결 감사(역방향 공백 보정)** [2026-07-25]: ①의 후보 탐색은 학습 시점의 그래프만 알므로, **학습 이후 편입된 노드**와의 연결 기회는 영영 없다('bts 관련주' 사고의 역방향 — bts가 kpop-agency 시드보다 먼저 학습됐다면 엣지 부재). `term_grounding.propose_relink_edges`/`relink_lexicon`이 학습 항목의 저장 텍스트(정의+출처 제목)를 현재 그래프로 재스캔해 미연결 개념 노드로 향하는 후보 엣지를 추가한다 — LLM 무관여 결정적 스캔, 저장 텍스트 재해석은 출처 교차지지를 새로 셀 수 없으므로 자동 verified 없이 **전부 pending**(콘솔 승인), rejected 이력 타깃은 부활 금지, company:/etf: 타깃은 제안하지 않음(상장사 매칭은 종목 마스터 기준이라 그래프 성장과 무관 — 학습 시점 수집이 완결), 멱등(재실행 시 무변화). 진입점: 시드 편입 가드 5(`docs/kg_concept_builder.md`) + 주기 감사 `scripts/kg_relink_audit.py`. 실측: 마운자로 → obesity-drug(시드가 학습보다 늦게 편입돼 미연결이었음) pending 제안 확인. ⑦ **수동 엣지 추가** [2026-07-25]: 검색(co-mention)·공시(지분) 어느 경로도 못 잡는 롱테일 관계('LB인베스트먼트=하이브 초기 투자사' — 벤처펀드 경유 초기 투자라 5%룰·출자현황 비노출)는 관리자가 콘솔 Knowledge 탭에서 근거 문구(note)와 함께 직접 추가한다(PATCH addEdge — 허용 유형 화이트리스트·중복 409·감사 로그). 관리자 행위 자체가 사람 검증이므로 즉시 verified(proposed_by=manual, 출처 수 없음 — UI '수동 등록' 표기). KG 로더는 학습 엣지의 note를 그래프로 운반하고 Concept Universe(FR-STR-072)가 그 근거 문구를 이유로, 점수는 시드 최소 등급(0.70)으로 표시한다.

**FR-STR-070c** [KG 시각화 — 운영 콘솔 지식그래프 뷰, 2026-07-25] 관리자는 합성 지식그래프 전체를 운영 콘솔에서 상시 시각적으로 확인할 수 있어야 한다. ① **데이터 경로**: 백엔드 `GET /knowledge/graph`(`api/intent_routes.py`)가 로더 합성 결과(시드+정본 자동 생성 섹터·기업·ETF 노드+verified 학습 오버레이)를 nodes/edges/issues로 덤프하고, Next 프록시 `/api/admin/knowledge/graph`(requireAdmin — 비관리자 404 은닉, 백엔드 미가용 502)가 패스스루한다. 합성 로직의 SOT는 `engine/knowledge_graph.py`이며 프론트는 시드·어휘집 파일을 재합성하지 않는다. ② **표시**: Knowledge 탭의 'KG 시각화' 서브탭(`components/admin/KnowledgeGraphView.tsx`) — 외부 라이브러리 없는 캔버스 포스 레이아웃(반발+링크 스프링+중심 중력, 결정적 나선 초기 배치), 그룹 5종(개념·테마/섹터/학습 용어/상장사/ETF)을 색+도형(원/마름모/사각형)으로 이중 인코딩하고 범례·노드/엣지 카운트를 표시한다(색 단독 식별 금지). 줌/팬/노드 드래그, 호버 툴팁(이름·분류·설명), 노드 클릭 시 이웃 하이라이트+관계 목록("HBM –produced_by→ SK하이닉스") 표시, 로더 검증 경고(issues)가 있으면 노출한다. **테마 레벨 기본 화면(2026-07-27)**: 테마 카탈로그 편입으로 그래프가 노드 3천·엣지 9천 규모(종목이 78%)가 되어, 기본 화면은 종목(상장사) 노드를 숨긴 테마 레벨로 표시한다 — 종목은 노드 선택 시 그 이웃만 연결 노드 곁에서 펼쳐지고(검색으로 숨은 종목을 선택해도 자동 활성), 범례의 '상장사' 칩이 전체 표시 토글을 겸한다. 반발력은 공간 그리드 근사(인접 9칸 정확 계산+원거리 칸 무게중심, 컷오프 400px)로 전체 표시에서도 프레임을 유지하며, 축소 시 라벨은 줌 비례 차수 임계값으로 솎아낸다(학습 용어는 항상 라벨, 노드 크기는 sqrt 차수 스케일). ③ **규제 안전**: 객관적 관계 데이터의 표시일 뿐 추천·전망이 아니다(FR-STR-070 ⑥ 준수).

**FR-STR-070d** [개념↔종목 관계의 근거·관련도, 2026-07-30] 지식그래프의 개념↔상장사 관계는 **왜 연결되는가(근거)**와 **얼마나 직접적인가(관련도)**를 런타임까지 전달해야 한다. ① **원장이 정본**: `data/kg-research/<concept>.json`(FR-STR-070 ①의 조사 원장)에 이미 있는 `relation_type`·`relevance`·`relevance_score`·`reason`·`business_evidence`·`sources`·`verified`를 `engine/kg_research.py`가 읽어 `(concept, symbol)` 인덱스로 만들고, 그래프 빌드가 시드 엣지에 `relation`으로 부착한다. **원장에 없는 관계에는 아무것도 붙이지 않는다** — 근거를 지어내지 않으며, 이 코드가 관계를 새로 판정하지도 않는다. 배선 전에는 원장이 런타임에서 한 번도 읽히지 않아(시드로 옮길 때 엣지 타입과 한 줄 note만 남음) "직접 생산"과 "테마 목록에 함께 있을 뿐"을 구분할 수 없었다. ② **직접 사업 관계의 구분**: `Producer`·`Supplier`만 `direct=true`이고 `Investor`·`Infrastructure`·`Related`는 사실이되 직접 생산·공급이 아니다. 관계 유형 목록은 원장의 실제 어휘에서 도출하며(목록을 먼저 정하고 데이터를 맞추지 않는다), 목록 밖 유형도 버리지 않고 `relation_known=false`로 표시만 한다(걸러내면 새 유형 추가 시 관계가 조용히 사라진다). ③ **근거 출처 구분**: `evidence_source`는 `research`(원장 근거)·`seed`(큐레이션이나 근거 미기재)·`catalog`(테마 카탈로그 수록)·`learned`(검색 학습)이며 **그래프 빌드 시점에 표기**한다 — 읽는 시점에 추론하면 근거 없는 시드 엣지가 카탈로그로 잘못 표기된다(실측). ④ **점수 산출**: Concept Universe(FR-STR-072)는 원장이 있으면 `relevance_score`를 그대로 쓰고, 없을 때만 기존 note 문자열 되파싱(`"(Core 95)"`)으로 폴백한다. ⑤ **[규제 안전] 전망성 관계 금지**: 관계 유형은 과거·현재의 **사실**만 담는다. 설계 스펙이 나열한 '정책 수혜 가능성'은 미래 전망이므로 도입하지 않는다 — 근거로 표기하는 순간 객관적 데이터 표시가 아니라 전망 제공이 된다(FR-STR-070 ⑥). 회귀 테스트가 전망성 어휘(Policy·Beneficiary·Expected·Outlook·Forecast)의 유입을 막고, 별도 테스트가 배포된 원장의 관계 유형이 전부 등록된 사실 유형인지 상시 확인한다. ⑥ **금지**: 관련도 기반 종목 절단·정렬은 하지 않는다(테마 유니버스 종수 상한 절단 금지 — FR-STR-070 계열의 선행 결정). 회귀: `backend/tests/test_kg_research.py`.

**FR-STR-071** [테마 관련 상장사 학습 + 테마 유니버스 되묻기, 2026-07-25] 검색 그라운딩이 테마 용어를 학습할 때 **함께 언급된 국내 상장사**도 관계 엣지로 학습하고, 파싱이 그 목록으로 백테스트 대상을 좁힐 수 있게 해야 한다("마운자로 관련주 전략"이 업종 근사(바이오/제약 전체)로만 실행되던 한계 보정). ① **관련 기업 엣지(결정적 수집)**: `term_grounding._propose_company_edges` — 검색 스니펫 본문에 등장한 상장사를 정본 종목 마스터 매칭(`symbol_resolver.find_in_text`, 해외 제외)으로 수집해 `related_company` 엣지(target=`company:<symbol>`)를 만든다. '출처에 함께 언급됨'은 관계 유형 판단이 필요 없는 객관적 사실이므로 개념 엣지(FR-STR-070b)와 달리 **LLM 무관여**(환각 원천 차단). 신뢰도는 동일 계약: 서로 다른 출처 ≥2 자동 verified / 1개 pending(콘솔 검토·승인). 검색 쿼리에 `"{용어} 관련주"` 뉴스 8건이 추가된다(4건에선 교차지지가 실측 불가 — 전부 pending). ② **first_known_date(시점 편향 1단계 가드)**: 각 기업 엣지에 그 기업이 언급된 **뉴스 보도일(pubDate) 최솟값**을 ISO로 기록한다(뉴스 아닌 출처뿐이면 None, 테마 대표값 폴백은 학습일). 이는 '관련주로 확인된 최초 시점'의 근사일 뿐 정식 시점별 테마 멤버십(DART 공시 기반 검증)이 아니다 — 정식 구현은 별도 프로젝트. ③ **KG 합성**: verified 기업 엣지의 `company:` 타깃은 로더가 정본 노드로 자동 생성한다(정본에 없는 심볼은 issues 없이 조용히 스킵 — 학습 데이터는 시드 무결성 단언 대상이 아님). ④ **테마 유니버스 되묻기**: `nl_parser.detect_theme_universe_clarification` — 테마 큐(관련/테마) 동반 + 종목 미지정 + verified 관련 기업 존재 시, 자동 적용하지 않고 목록·출처 교차 확인 사실·시점 편향 경고를 담아 되묻는다(객관적 관계 데이터 표시, 추천 아님). [2026-07-25 읽기 경로 통합] 조회는 `knowledge_graph.theme_listed_companies` 그래프 단일 경로(깊이 1, `KnowledgeGraph.listed_companies`) — 학습 테마·시드 개념 공통이며, 로더가 학습 엣지의 support/first_known_date를 그래프 엣지에 실어 나르고 verified만 합성되므로 결과는 자동으로 검증분이다. [2026-07-25 개념 1홉 폴백] **학습 앵커**의 직접 상장사 엣지가 하나도 검증되지 않았으면 verified 개념 엣지 1홉 너머 개념의 직접 상장사로 후보를 채운다(`KnowledgeGraph.listed_companies_via_concepts` — 'bts 관련주' 실측 사고: 직접 엣지는 출처 1건 pending인데 verified 개념 엣지(K-팝 기획사, 출처 4건) 너머에 하이브가 있었는데도 업종 근사(미디어/엔터 전체)로 확정됨). 직접 verified 상장사가 있으면 홉은 발동하지 않으며(정밀 목록 우선 — 이웃 개념 상장사로 희석 금지), 시드·카탈로그 앵커는 폴백 대상이 아니다(큐레이션이 직접 엣지를 책임). 뉴스 보도일 없는 홉 상장사의 first_known_date 대표값은 기존 계약대로 학습일(searched_at)로 폴백한다(시점 편향 보수 유지). 칩 왕복 계약: 종목 칩은 "종목명 나열 + '종목 전체를 함께' + 'YYYY년부터'" 형태 — '관련주/테마/업종' 단어를 넣으면 `_TARGET_SYMBOL_CONTEXT_GUARD_RE`가 종목 추출을 차단하므로 금지, '전체를 함께'는 다종목 모호성 되묻기(`detect_symbol_ambiguity`, 집합 의도 큐로 억제 — FR-STR-068 확장)를 잠재우고, 'YYYY년부터'는 명시적 시작일로 해석돼 first_known_date 이전 구간을 배제한다. 업종 칩("… 업종 전체로 백테스트")은 기존 섹터 어휘로 재해석된다. **[2026-07-25 ④ 개정 — 되묻기 폐지·자동 적용(사용자 결정)]**: '이 종목들로만 vs 업종 전체' 되묻기(+Phase 2 공급망 확장 칩)를 폐지하고 `nl_parser.apply_theme_universe`가 되묻기 없이 `target_symbols`를 자동 설정한다(DSL 변환 전 실행 — 지정 종목 모드로 심볼 해석). 설정은 조회된 관련 상장사 **전체**다 — 종수 상한 절단 금지(2026-07-28 '비만치료 관련주' 사고: 안내문 나열용 상한 10이 target_symbols까지 잘라 동률 36곳 중 심볼 앞 10곳만 유니버스가 됨), 안내문의 종목명 나열만 10곳+«외 N곳»으로 축약한다. 빌더 레인(`_theme_patch`)도 동일 계약(theme_label은 synthesize_prompt 재파싱용 전체 이름). 업종 근사(sector)는 해제한다(관련 종목엔 타업종(넷마블·신세계)이 섞여 sector 필터가 남으면 방금 설정한 종목을 도로 걸러냄). 무엇이 어떤 근거로 설정됐는지는 **비차단 notices**로 투명하게 알린다(목록·출처 유형·first_known_date 시점 정보 — 침묵 적용 방지, 객관적 관계 데이터 표시이며 추천 아님). **[2026-08-02 개정 — 적용 안내 비노출(사용자 지시)]**: 이 안내문은 사용자 notices에 싣지 않는다 — 요약 카드('현재까지 이해한 전략')가 설정된 유니버스 종목 전체를 이미 표시해 배너가 중복이다. `apply_theme_companies`/`replace_theme_universe`의 반환 문구(근거 등급·시점 편향 문구 포함)는 적용 성공 신호·진단용으로 구성만 유지하고(회귀: test_theme_universe_autoapply), 모든 호출부(레거시 main·인터프리터 체인·planner·유니버스 칩·테마 교체)가 notices 적재를 중단한다. 시작일은 자르지 않는다(시점 편향은 notice 고지만 — 조용한 기간 축소 방지). 자동 설정된 다종목은 `detect_symbol_ambiguity`를 건너뛴다(집합 의도 자명). ⑤ **우선순위 보호**: ~~테마 되묻기는 유니버스 범위 질문이므로 `clarification_priority="theme_universe"`로 표시되고, 인터프리터 primary의 조건 질문이 이를 덮어쓰지 않는다(`apply_primary_meta` 가드)~~ — ④ 개정으로 되묻기가 사라져 미발동. 필드·프록시 passthrough·프론트 우선 게이트는 스키마 호환으로 유지(항상 None). 실측(2026-07-25): "마운자로 관련주" → 한미약품 verified(출처 2건)·펩트론 pending(1건, 콘솔 승인 대상), 칩 클릭 → symbols=[128940]·startDate=2026-01-01로 결정적 왕복 확인. 한계: 목록 품질은 뉴스 표본에 의존(누락된 관련주는 pending 승인 또는 직접 종목 지정으로 보완), first_known_date는 근사치. **[① 개정 — 관련 기업 엣지는 네이버 금융 분류 기반·자동 등록, 2026-07-27 사용자 지시]** 뉴스 동시언급 수집(`_propose_company_edges`)은 무관 종목 노이즈('다이어트'에 삼성SDI·신한지주·KB금융 등 21개 pending 실측 사고)가 커서 폐기한다. 대체(`_naver_company_edges`): ⓐ 검색 레인이 수집한 네이버 금융 분류 목록(테마+업종, ④a 표기 정합과 공유)에서 LLM이 용어에 대응하는 분류를 **이름 닫힌 목록 안에서만** 고르고(최대 3개, 목록 밖·스코프 제외(인물·정치 등) 이름 드롭), ⓑ 종목은 그 분류의 수록 목록(`naver_theme_live.fetch_group_stocks`, 정본 필터)에서 결정적으로 수집한다. 분류 수록은 객관적 사실이므로 **자동 verified 등록**(콘솔 사후 반려 가능) — support=수록 분류 수, evidence=분류 상세 URL, first_known_date=None. 가드 2겹: 개별 상장사명 용어는 결정적 차단(종목 마스터 정확 일치 — '삼성전자'가 '반도체 대표주'로 확장 방지), 인물·연예 그룹·고유명은 단일 과제 LLM 판별(`_naver_term_is_industry`)이 매핑 전에 차단(분류 매핑 프롬프트에 규칙을 섞으면 소형 모델이 무시하는 실측 — BTS·리센느). 대응 분류 없음·목록 수집 실패면 기업 엣지 없음(뉴스 폴백 없음). 뉴스 쿼리는 정의 그라운딩·개념 엣지(FR-STR-070b) 원천으로 유지. 기존 학습 항목은 `scripts/rebuild_learned_company_edges.py`로 재구축(pending 뉴스 엣지 제거·verified/rejected 보존·네이버 편입 — 2026-07-27 10항목 적용: '다이어트' 21→86 전부 verified, 인물·그룹 4건은 편입 0). **[⑥ 테마 출처 보존 + 수정 턴 테마 교체, 2026-07-30]** 테마로 설정된 지정 종목은 **출처 테마 표기**를 함께 저장한다(`ParsedStrategy.theme_universe`, 수정 초안까지 왕복하도록 `UniverseSpec.theme`). 사고: 토스 관련주 전략에 "쿠팡 관려주로 수정해줘"가 무변경으로 끝났다 — ⓐ 테마 적용이 종목만 남기고 테마명을 지워(`sector=None`) 초안에 출처가 없었고 ⓑ 수정 레인에는 지식 조회 체인이 없어 인터프리터가 종목코드를 직접 알아내야 했으며(실제로는 기존 코드를 복사한 무변경 패치+"종목 코드가 무엇인가요?" 되묻기 — 지식 조회를 사용자에게 떠넘김) ⓒ 그 되묻기는 우선순위 마커가 없어 프론트 설정 게이트의 조건 질문에 덮여 사라졌다. 수정: ⓐ 출처 표기 왕복 ⓑ `primary._resolve_theme_change` — 수정 턴이 새로 넣은 미해결 유니버스 표현을 **검증 전에 떼어** 생성 경로와 같은 체인(카탈로그 후보 2개 이상=범위 되묻기 / 1개=정본 표기 확인 칩(자동 확정 금지) / 0개=KG 직접 조회→검색 학습→되묻기)에 넘긴다. 미지 테마를 검증기에 그대로 넘기면 '지원 섹터 아님' 오류로 수정 레인 전체가 폴백해 요청이 무변경으로 끝난다 ⓒ 적용은 `nl_parser.replace_theme_universe` — **이전 테마에서 온 종목만** 비우고 재조회하며, 사용자가 직접 지목한 종목은 건드리지 않는다(기존 가드 유지), 새 테마 조회 실패 시 원상복구. 정본 섹터로 바꾸는 턴('2차전지 업종으로')도 같은 출처 판정으로 이전 테마 종목을 해제한다(종목 지정이 우선이라 그대로 두면 새 업종이 삼켜짐). 트리거는 `universe.sectors` 패치다 — 별도 필드를 LLM이 채우게 하는 1차 설계는 실측(9B가 생성 규칙 6-0-2와 같은 형태로 낸다)에서 폐기했다. ⓓ 전략 무변경 되묻기(테마 범위·자기 의심·값 없는 수정·개념 질문)는 `clarification_priority`를 달아 프론트 게이트가 삼키지 않게 한다. 회귀: `test_modify_roundtrip_migration.py` 테마 6건. **[⑦ 시장 제약 결정론 반영, 2026-08-02]** 지정 종목 모드는 universe 시장이 실행에 반영되지 않는다(변환기가 target_symbols 우선) — 테마 지정 종목 전략(HBM 33곳)에 "코스피에만 속한 종목으로 변경" 요청 시 인터프리터가 `/universe/markets=[KOSPI]` 패치를 정확히 내고 검증·컴파일을 통과해도 종목 목록이 그대로라 무변경으로 보이던 사고. `nl_parser.filter_target_symbols_by_market`: 유니버스가 단일 시장(KOSPI 또는 KOSDAQ 단독)으로 확정돼 있으면 **테마 유래**(theme_universe 보유) 지정 종목을 종목 마스터(korea-stocks.json) 정본 소속으로 결정론 필터링한다(시장 소속은 지식 조회 — 원문 해석 아님). 가드: 직접 지목 종목(theme_universe=None)은 불변(⑥ ⓒ와 동일 원칙), 필터 결과 0곳이면 미적용(조용한 빈 전략 방지), 마스터에 없는 종목(상폐 등)은 소속 미확인으로 제외. 배선 2곳 — 수정 레인(run_primary_modification 패치 적용 후)과 생성 체인(apply_theme_companies 테마 적용 직후: "코스피에 상장된 HBM 관련주")·테마 교체(replace_theme_universe 경유 시 시장 제약 유지). theme_universe는 보존된다(이후 테마 교체 판정 근거). 회귀: `test_modify_roundtrip_migration.py::test_market_only_patch_filters_theme_symbols`·`test_theme_universe_autoapply.py` 시장 필터 5건. **[⑦-1 시장 전환 재도출 + 미반영 안내, 2026-08-02 2차]** 사고: 코스피로 좁힌 6곳 상태에서 "미안해 코피닥 종목만 선택 해줘" — 인터프리터는 오타를 코스닥으로 정확히 해석해 markets=[KOSDAQ] 패치를 냈으나, 현재 목록에 코스닥이 0곳이라 필터의 빈 목록 가드가 적용을 거부했고 universe만 KOSDAQ으로 뒤집힌 채 안내 없이 끝나 사용자가 '오타 미해석'으로 오인했다. 수정 2겹: ⓐ **테마 전체 재도출** — 현재 목록에 해당 시장 종목이 0이면 목록의 출처인 테마 전체 구성(theme_backtest_companies)에서 다시 좁힌다(시장 전환의 단방향 손실 방지, 코스피 6곳→"코스닥만"=테마 27곳). 현재 목록에 해당 시장 종목이 남아 있으면 재조회하지 않는다 — 수동으로 줄인 목록을 필터가 도로 되살리지 않는다. ⓑ **이해-후-미반영 침묵 금지** — 테마 전체에도 해당 시장 종목이 없으면(`nl_parser.unapplied_market_constraint`) 시장 패치까지 되돌려 전략을 원상 유지하고 "…소속을 찾지 못해 요청을 반영하지 못했어요. 기존 전략을 그대로 유지했어요"를 notices로 알린다(반쪽 상태·무안내 금지). 해석 자체가 실패한 경우(패치 전량 폐기)의 유지 안내는 기존 문구가 담당한다. 회귀: `test_market_switch_rederives_from_full_theme`·`test_unmet_market_constraint_keeps_strategy_and_notifies`.

**FR-STR-071b** [복합 테마구 가드 + 빌더 테마 유니버스 되묻기, 2026-07-25] 시스템은 알려진 테마어에 미지의 수식어가 붙은 **복합 테마구**("반도체 소부장")를 앞 테마어만 잘라 업종으로 단독 확정해서는 안 되며, 빌더 경로에서도 학습·검증된 관련 상장사로 대상을 좁힐 수 있어야 한다(실측 사고 2026-07-25: "반도체 소부장 전략을 만들자"가 업종=반도체로 확정돼 수식어가 조용히 소실됨). ① **복합 테마구 가드**(`nl_parser._compound_theme_hint`): 큐리스 테마어(`_CUE_LESS_SECTOR_TERMS`) 매치 직후의 한글 토큰이 '아는 어휘'(전략 어휘 `_RULE_GUARD_KNOWN_VOCAB`+보강 목록(주도주·수혜주·소재 등)+섹터어+종목명)가 아니면 복합구로 판정 — `_extract_sector`는 단독 확정 대신 그래프(시드·학습) 해석을 시도하고 실패 시 None, `_mentioned_unsupported_concepts`가 업종 큐 없이도 'sector' 미해결로 플래그해 되묻기·검색 학습 게이트(FR-STR-069 ⑥)를 연다. 복합구는 `detect_theme_universe_clarification`의 테마 큐(관련/테마)와도 동급으로 인정된다. 알려진 후속어("반도체 주도주"·"바이오 헬스케어")는 기존 단독 확정을 유지하고, 공백 없는 붙여쓰기는 기존과 동일하게 미감지. ② **큐 없는 미지 테마어(약한 힌트)**(`nl_parser._weak_theme_candidate` + `BuilderState.sector_hint_weak`): 머리명사(전략/종목/주식/투자/포트폴리오) 앞의 미지 한글 명사("소부장 전략")를 빌더 시드에서만 약한 테마 힌트로 그라운딩 체인에 넘긴다. 오탐 여지(수식어)가 있으므로 형용사꼴(ㄴ받침 종결)·아는 어휘는 제외하고, 해석 실패 시 되묻기·안내 없이 조용히 해제한다(강한 힌트(업종 큐·복합구)는 기존대로 되묻기). ③ **검색 학습 우선 순서**(`term_grounding._prefers_search_first`): 복합구·약한 힌트 텍스트는 해석 체인에서 내부 지식 LLM(②)보다 검색 그라운딩(④)을 먼저 시도한다 — LLM이 머리 테마어(반도체)로 근사해 버리면 하위 테마의 정의·관련 상장사가 영영 학습되지 않는 공백 차단. 검색이 업종 매핑에 실패하면 LLM 폴백. 용어 추출 프롬프트는 복합 표현 전체 추출을 지시하고("반도체 소부장"), 추출된 용어가 이미 정본 섹터어면 검색·학습하지 않는다(어휘집 오염 방지 — '반도체' 항목이 학습되면 모든 반도체 언급이 어휘집 히트로 단락). ④ **빌더 테마 유니버스 자동 확정** [2026-07-25 개정 — 되묻기 폐지(사용자 결정)]: 그라운딩/그래프가 테마의 verified 관련 상장사를 알면 빌더는 되묻기 없이 지정 종목 목록으로 즉시 확정한다(`_theme_patch`가 `theme_symbols`·`theme_label` 설정+업종 근사 해제+`theme_reask_done`, 시드 경로·`_consume_sector_notice` 해석 경로 공통). 유니버스 질문은 생략되고 `build_parsed_strategy`가 `target_symbols`로 직접 조립하며(시작일 클램프 없음 — 시점 편향은 파싱 경로 notices가 고지), 합성 프롬프트는 종목명 나열("동진쎄미켐, 원익IPS 종목 중 …" — '업종/테마' 단어 금지, TARGET 가드 함정)로 만든다. 프론트 요약 카드는 `theme_label`을 '대상 종목'으로 표시한다. (종전 `_theme_reask_prompt`/`_answer_theme_reask` 되묻기 기계장치는 제거됨.) 한계: 관련 상장사 목록은 뉴스 co-mention 표본에 의존하며 pending 엣지는 콘솔 승인 전까지 되묻기에 나타나지 않는다(그때까지는 verified 개념 엣지 1홉 폴백(FR-STR-071 ④)이 닿으면 그 개념의 상장사로, 아니면 업종 근사로 동작).

**FR-STR-071c** [테마 카탈로그 표기 정합 우선, 2026-07-27] 관련 종목 조회의 1순위 정본은 외부 카탈로그(네이버 금융 업종별·테마별 종목 — 사용자 지정 1순위 신뢰 소스, 차순위 주달)이며, 뉴스 동시언급 학습 엣지는 카탈로그 미보유 테마의 폴백이어야 한다(실측 사고 2026-07-27: "LCD 부품 관련주"가 카탈로그 'LCD 부품/소재' 44곳 대신 학습 엣지 uses→pcb의 개념 홉(심텍·대덕전자)+지분 홉(심텍홀딩스·대덕)+동시언급(SK하이닉스) 등 무관 종목 5곳으로 왜곡). ① **슬래시 별칭**: 카탈로그 테마명의 슬래시 병기("LCD 부품/소재")는 부분 문자열 스캔에 걸리지 않는 도달 불가 이름이므로, 로더가 결정적 표기 변형("LCD 부품"·"LCD 소재")을 동의어로 생성한다(`knowledge_graph._slash_aliases` — 괄호 안 슬래시 제외, 섹터 어휘·테스트 정본 용어 가드 유지, 의미 해석이 아닌 표기 정규화). ② **학습 앵커 카탈로그 정합**: 검색 학습 노드가 스캔 키를 선점했더라도 표기가 **정확히 일치**(부분·접두 매칭 금지 — FR-STR-071b 가드와 동일 원칙)하는 카탈로그 테마가 있으면(`catalog_theme_nodes`), `theme_listed_companies`는 학습 엣지 대신 카탈로그 수록 종목을 반환하고 `theme_backtest_companies`는 Concept Universe 확장을 생략한다. 카탈로그 정합은 큐레이션 분류라 시점 편향 경고(first_known_date) 대상이 아니다. ③ **네이버 금융 카탈로그 수집**(`scripts/ingest_naver_themes.py`): 업종별·테마별 종목을 주달 카탈로그와 동일한 기계적 가드(정본 심볼·섹터 어휘·시드 중복·테스트 정본 용어)+스코프 제외(인물·정치·이벤트·시장분류 키워드)로 수집해 `data/kg-naver-theme-catalog.json`에 저장하며, 로더는 네이버를 주달보다 먼저 합성한다(같은 표기 겹치면 네이버 승). ④ **게이트 판정 기준 통일**(사고 2차, 2026-07-27): primary 레인의 미해결 섹터 표현 게이트(`primary._sector_terms_for_chain`)는 검증기(capability_validator)와 동일하게 정본 사전(normalize_sector)만으로 판정한다 — 게이트가 KG 층(resolve_sectors)까지 '해석 성공'으로 치면, 검증기가 이미 sectors에서 제거한 표현이 체인에 도달하지 못하고 해석값도 폐기돼 유니버스가 통째로 소실된다. 정본 사전이 못 푸는 표현은 KG가 섹터를 해석할 수 있어도 체인으로 보낸다(테마 상장사 적용이 섹터 근사보다 우선). ⑤ **별칭 일반어 차단**: 슬래시 별칭이 만드는 단독 일반어 조각('카메라모듈/부품'→'부품')은 스캔 어휘가 되면 그 단어를 포함한 모든 질의에 오매칭되므로 차단한다(`_ALIAS_STOPWORDS` — 부품·소재·장비·제품·기기·재료, 수식어 붙은 별칭은 통과). **[2026-07-27 개정 — 전 앵커 확장+라이브 편입(사용자 지시: KG에 없으면 네이버를 항상 우선 검색해 KG에 넣는다)]**: ⑥ ②의 카탈로그 표기 정합을 학습 앵커 한정에서 **전 앵커(시드 포함)**로 확장한다 — 표기가 정확히 일치하는 카탈로그 테마가 있으면 시드 큐레이션 직접 엣지 대신 카탈로그 수록 종목이 유니버스 정의('온디바이스 AI' 시드 2곳 vs 네이버 24곳), 표기 불일치 개념(HBM vs "HBM(고대역폭메모리)")은 시드 직접 엣지 유지. 이에 따라 ③의 네이버 수집에서 시드 중복 가드를 폐지한다(시드와 같은 이름의 테마도 수집 — 스캔 인식은 여전히 시드 우선). ⑦ **네이버 라이브 편입**(`engine/naver_theme_live.py`): KG가 해석하지 못한 테마 용어의 검색 레인(`term_grounding` ④)은 뉴스 검색 학습 전에 네이버 금융 테마·업종 목록을 라이브 조회해 표기 정합(원명·괄호 제거 본체·슬래시 변형, 정확 일치만)을 찾고, 정합 시 수록 종목을 네이버 카탈로그 파일에 병합 저장한다(그래프 mtime 재로드로 즉시 결정적 해석 — 같은 용어 재검색 없음). 정합 없음·수집 실패는 기존 뉴스 검색 학습으로 폴백하며, 배치 수집과 파서·스코프 가드를 공유한다. **[2026-08-02 개정 — 괄호 표기 변형 파생 키]**: ⑧ 정합 인덱스(`_build_catalog_index`)는 괄호 병기 테마명("HBM(고대역폭메모리)")의 결정적 표기 변형 — 괄호 제거 본체("HBM")와 괄호 안 토큰("고대역폭메모리") — 을 파생 키로 더한다(`knowledge_graph._paren_variants`). ingest의 괄호 동의어 승격(make_synonyms)이 시드 중복 토큰을 스캔 어휘 오염 방지로 버려, 시드 앵커(HBM)가 같은 개념의 카탈로그 테마와 영영 정합하지 못하던 공백 보정(실측 사고 2026-08-02: 'HBM 관련주'가 시드 직접 엣지 6곳으로 확정 — 네이버 'HBM(고대역폭메모리)' 33곳 미도달). 등록 규칙: ⓐ 정확 표기 키 항상 우선 — 파생 키가 다른 테마의 정확 표기('전기차')를 가로채지 않는다 ⓑ 카탈로그 간 충돌은 먼저 합성된 네이버 승(_catalog_paths 순서 계약과 동일 — 'hbm': 네이버 'HBM(고대역폭메모리)' vs 주달 '반도체 제품(HBM/HBM3E)') ⓒ 같은 카탈로그 안 다의 파생 키('보안주(정보)'/'보안주(물리)' → 보안주, '원자재(리튬)' 등 9종 → 원자재)는 미등록 — 부분 매칭 자동 확정 금지(FR-STR-071b)와 동일 원칙, 되묻기 선택지(catalog_theme_candidates)로만 남는다 ⓓ 괄호 토큰은 ingest와 동일 일반어 가드(라틴/숫자 포함 또는 한글 4자 이상 — '정보'·'충전소' 같은 조각 차단)+별칭 일반어·테스트 정본 용어·섹터 어휘 가드. 파생 키는 정합 인덱스 전용이며 스캔 어휘에는 영향이 없다(앵커 인식 불변). ⑥의 "표기 불일치 개념(HBM)은 시드 직접 엣지 유지"는 파생 키 정합이 닿는 범위에서 폐지된다. 회귀: `test_knowledge_graph.py::test_catalog_paren_derived_keys`·`test_hbm_real_catalog_universe_composed`. **[2026-09-10 개정 — 일반명사 조회 키 가드]**: ⑨ 유니버스를 좁히지 못하는 일반명사('종목'·'주식'·'기업'·'회사'·'상장사'·'전체'·'시장' 등, `universe_pit.is_generic_stock_term` — **정확 일치**이며 수식어가 붙은 표현('반도체 종목')은 통과)은 ⓐ `classify_universe`가 NOT_UNIVERSE로 종결하고 ⓑ `catalog_theme_candidates`가 후보를 반환하지 않는다. 포함 일치 조회는 일반명사를 주면 무관한 테마를 긁어오고, 후보가 하나뿐이면 결정론 에필로그가 그것을 자동 적용한다 — 실측 사고 2026-09-10: "실적 대비 가격이 낮은 종목을 찾고 싶어"에서 planner가 조건 구를 떼고 남긴 `text="종목"`이 카탈로그 '철강 주요종목'과 포함 일치해, 사용자가 말한 적 없는 철강 11곳이 유니버스로 확정됐다. 판정 입력은 LLM이 뽑은 짧은 표현이고 판정은 표기 대조뿐이다(계약 § 3-2 형식 정규화 — 사용자 원문 해석이 아니다). 회귀: `test_strategy_tools.py::test_classify_universe_rejects_bare_generic_stock_noun`·`::test_generic_noun_yields_no_catalog_theme_candidates`. **[2026-09-10 개정 — 표기 동일성만 자동 확정]**: ⑩ 카탈로그 후보의 자동 확정 기준은 개수가 아니라 **표기 동일성**이다. 후보 표기가 사용자 표현과 같은 것을 가리키면(원 표기·괄호 제거 본체·괄호 안 토큰·슬래시 재조립 — `knowledge_graph._notation_forms`, 후보 항목의 `exact` 플래그) 확인 없이 적용하고('ESS'→'전력저장장치(ESS)'), 이름 안에 글자만 들어 있는 부분 일치는 **후보가 하나여도** 사용자 확인을 받는다('2차전지'→'2차전지 장비'는 장비만으로 좁히는 것이고 '종목'→'철강 주요종목'은 무관하다). 종전 규칙('후보 1개=범위가 갈리지 않음'→결정론 에필로그 자동 조회, 2026-08-02)은 부분 문자열 일치까지 자동 확정으로 밀어 넣어 FR-STR-071b(부분 매칭 자동 확정 금지)와 planner 프롬프트('후보가 1개여도 ask로 확인받으세요')를 코드가 어기고 있었다(실측 사고 2026-09-10: 철강 11곳 무단 확정, 상시적으로는 '2차전지'→장비 38곳 조용한 축소). 확인·범위 되묻기는 개수와 무관하게 결정론(`primary._planner_scope_ask`)이 소유하며 칩은 후보 정본 표기 그대로다. **생성·수정 레인은 같은 기준을 쓴다** — 종전에는 생성이 후보 1개를 전부 자동 적용하고 수정(`_resolve_theme_change`)은 전부 되물어, 같은 표현이 레인에 따라 다르게 처리됐다. 사용자 선택을 기다리는 후보 표기 자체를 planner가 조회해도 적용하지 않는다(자기 선택 차단). 회귀: `test_dag_planner.py::test_partial_match_single_candidate_does_not_auto_requery`·`test_planner_first.py::test_partial_match_single_candidate_asks_for_confirmation`·`::test_partial_match_single_candidate_blocks_silent_application`·`test_modify_roundtrip_migration.py::test_theme_replacement_applies_notation_identity_without_asking`. **[2026-09-16 개정 — 나열식 표기 변형 파생 키]**: ⑪ 정합 인덱스는 나열식 테마명("방위산업/전쟁 및 테러")의 결정적 표기 변형 — 슬래시로 갈린 각 항목과 그 항목을 접속사('및'·'와'·'과')로 한 번 더 나눈 항목 — 을 파생 키로 더한다(`knowledge_graph._listing_variants`). 실측 사고 2026-09-16: "전쟁 관련주" 전략의 유니버스에 여객 항공사(제주항공·에어부산·아시아나항공 등)가 섞였다 — 네이버 테마 '방위산업/전쟁 및 테러'(66곳)가 정본인데 정합 키가 슬래시 변형('전쟁 및 테러')까지만 있어 앵커 '전쟁'이 닿지 못하고 어휘집의 업종 근사(우주항공/방산 2,583곳)로 빠졌다. ①의 `_slash_aliases`와 갈리는 지점은 **접미 처리**다 — 그쪽은 스캔용이라 접미를 모든 부분에 붙이지만("방위산업 및 테러") 여기서는 마지막 항목만 접미를 가져간다("A/B 및 C"는 'A' 또는 'B 및 C'이지 'A 및 C'가 아니다). 가드·등록 규칙은 ⑧과 동일하며(ⓐ정확 표기 우선 ⓑ카탈로그 순서 ⓒ다의 미등록, 두 글자 미만·별칭 일반어·테스트 정본 용어·섹터 어휘 제외) 파생 키는 정합 인덱스 전용이라 스캔 어휘에 영향이 없다. 실측 증분은 전체 493개 테마에서 키 5개('전쟁'·'테러'·'방위산업'·'구제역'·'피지컬 AI')이며 기존 정확 키와의 충돌·다의는 0건이다. 회귀: `test_knowledge_graph.py::test_listing_variants_deterministic_notation`·`::test_catalog_listing_derived_keys`. **⑫ 정합 인덱스는 앵커가 없어도 조회된다(2026-09-16 프로덕션 실측)**: ⑧⑪의 파생 키는 `theme_listed_companies`가 **앵커의 이름·동의어로만** 조회해, 앵커가 없는 환경에서는 영영 닿지 못했다 — '전쟁 관련주'가 로컬(학습 어휘집이 만든 '전쟁' 앵커 보유)에서는 방산 66곳으로 풀리는데 프로덕션(`data/term_lexicon.json` 자체가 없음)에서는 "업종을 인식하지 못했어요"로 끝났다. 스캔 어휘에 파생 키를 넣는 것은 해법이 아니다 — '항공' 같은 두 글자 조각이 스캔에 들어가면 그 낱말을 포함한 모든 문장에 오매칭된다(실측: '항공'은 UAM·항공기부품·우주항공산업 등 6개 이름의 부분 문자열). 그래서 스캔이 비면 **정확 일치로만** 정합 인덱스를 한 번 더 본다: 부분·접두 매칭은 여전히 금지이고, 같은 표기가 두 테마를 가리키면(다의) 자동 확정하지 않고 되묻기에 맡긴다. **교훈**: KG 동작은 로컬에서만 검증하면 안 된다 — 학습 어휘집이 gitignore라 로컬과 prod의 그래프가 다르다. 회귀: `::test_catalog_exact_notation_resolves_without_an_anchor`. **⑬ 되묻기 결정이 카탈로그 조회를 건너뛰지 않는다(2026-09-16 사용자 제보)**: 미해결 표현 구간의 mini-planner(`primary._resolve_sector_terms_planner_primary`)는 planner가 `clarify`를 고르면 테마 상장사 조회·테마 정본 매핑(⑥ · `term_grounding.resolve_kg_theme`, 스위치 `KG_THEME_CANONICAL_MATCH`)을 **통째로 건너뛰고** 되물었다 — planner의 결정 권한은 계약상 '검색(ground_term)할 표현인가, 되물을 표현인가'뿐인데, 그 결정이 결정론 지식 조회까지 삼킨 것이다. 고정 체인(`_resolve_sector_terms_term_in`)은 되묻기 전에 두 조회를 먼저 보므로 두 레인의 순서가 어긋나 있었다. 증상은 ⑫와 같은 '로컬은 되고 prod만 안 되는' 형태다 — 로컬은 학습 어휘집이 `kg_resolve_sector`에 답을 줘 planner가 `resolved`로 끝나므로 clarify 분기에 도달하지 않지만, 어휘집이 없는 prod는 관찰이 비어 planner가 자유롭게 되묻기를 고른다(실측: 같은 '석유'에 120B는 finish, 9B는 clarify). 그 결과 '석유 관련주'가 한쪽에서는 네이버 업종 '석유와가스' 13종목으로 풀리고 다른 쪽에서는 "'섹터 '석유'' 조건은 지원하지 않아 전략에 반영하지 못했어요"로 끝났다 — 카탈로그에 답이 있는데 못 한다고 말한 것이다. 수정: clarify 분기도 되묻기 채택 **전에** `apply_theme_companies` → `_apply_theme_via_canonical_match` 순서를 먼저 밟는다(인터넷 검색 학습은 종전대로 planner 판단에 맡긴다 — 비용이 큰 단계이고 그것이 planner의 고유 결정이다). 회귀: `test_planner_primary_mode.py::test_clarify_does_not_skip_catalog_lookup`·`::test_clarify_theme_companies_applied_before_asking`. **⑬-2 출처 간 같은 테마는 한 노드로 귀속한다(2026-09-16 프로덕션 실측)**: 같은 코드·같은 문장('석유 관련주 …')이 로컬에서는 네이버 업종 '석유와가스' 13곳, 프로덕션에서는 주달 '석유가스' 6곳으로 풀렸다. 두 이름은 접속사 '와' 하나 차이라 공백 무시 키(`_norm_key`)로 묶이지 않아 별개 테마 노드로 남았고, 정본 매핑(`resolve_kg_theme`)·planner·인터프리터 같은 LLM 단계가 둘 중 하나를 **고르는** 순간 그 선택이 레인·표본에 따라 유니버스를 갈랐다(환경 차이가 아니라 LLM 선택 차이 — 코드·데이터·어휘집 조건을 로컬에서 모두 맞춰도 20회 전부 '석유와가스', 프로덕션 세션 기록은 '석유가스'). 수정: 카탈로그 합성(`knowledge_graph._build`)에서 **나중에 합성되는 출처의 테마가 먼저 합성된 출처(네이버, ③의 순서 계약)의 테마와 표기가 공백·붙은 접속사(와·과·및)만 다르고 수록 종목이 하나 이상 겹치면**, 별도 노드를 만들지 않고 1순위 노드의 동의어로 귀속한다(`_catalog_equivalence_key`) — LLM이 어느 표기를 고르거나 적어도 같은 노드·같은 종목·같은 이름으로 풀린다. 같은 출처 안의 이름 차이는 그 출처가 일부러 나눈 분류일 수 있어 접지 않고, 공백 무시 키가 같은 완전 중복(43쌍)은 종전대로 정합 인덱스가 묶는다. 실측 영향은 석유 한 쌍뿐(후보 488→487). 회귀: `test_knowledge_graph.py::test_cross_source_conjunction_variant_folds_into_primary_source`·`::test_cross_source_fold_requires_shared_company_and_different_source`.

**FR-STR-072** [Concept Universe Builder — 개념 중심 유니버스 결정론 생성, 2026-07-25] 시스템은 Concept(테마·기술·제품·인물 IP 등) 입력에 대해 업종(Sector) 전체가 아니라 **해당 Concept와 사업적 관련이 검증된 종목 집합**을 결정론적으로 생성해야 한다(`engine/concept_universe.py::build_concept_universe`). ① **관련도 산출(LLM 자기평가 금지)**: score(0~1)는 KG에 축적된 근거에서만 결정론 산출한다 — 시드 엣지는 note의 원장 점수 "(Core 95)"/"(Producer/Strong 72)" 파싱(표기 없으면 0.70 — 시드 편입 규약상 최소 등급), 학습 verified related_company는 출처 수 기반(0.55+0.05×support, 상한 0.80), verified 개념 1홉 경유는 해당 종목 점수 ×0.85(거리 감쇠) — **경유 대상은 큐레이션된 카테고리 노드(시드·카탈로그)만이며 학습 개체(`learned:`) 간 수평 연결은 경유하지 않는다** [2026-08-24]: 뉴스 공동 언급으로 학습된 개체 간 `related_to`(예: 블랙핑크—BTS, 출처 9건)를 소속 관계처럼 타고 넘으면 상대 개체의 종목이 통째로 수입된다(실측 사고 '블랙핑크 관련주': BTS 경유로 신세계·LB인베스트먼트가 편입 — 13곳 중 2곳). 앵커 자신의 직접 엣지는 차단 대상이 아니다. 같은 계약이 `knowledge_graph.listed_companies_via_concepts`(학습 앵커의 1홉 폴백)에도 적용된다, 카탈로그 테마는 0.45(기본 임계 미만 — 완화 단계에서만). 심볼 중복은 최고 점수 경로만 유지하고 pending/rejected 엣지는 어느 층에도 불참한다(FR-STR-070b 검증 게이트와 동일). ② **선정 규칙**: score ≥ 0.5 기본, 결과가 10개 미만이면 점수순으로 floor 0.30까지 완화하되 **후보 자체가 부족하면 있는 만큼만 반환**한다('최소 10개 보장'을 위한 억지 채움은 억지 테마주 제외 원칙과 모순 — 스펙 대비 의도적 완화). 30개 초과분은 점수순 상위 30개. 크기 경계(완화 중단·상한)가 동점 그룹 한가운데를 지나면 동점 전체를 포함한다 — 같은 근거 점수의 종목 일부만 심볼 번호순으로 남기는 절단은 근거 기반 선정이 아니다(2026-07-28 '비만치료 관련주' 사고: 학습 동률 0.60 36곳이 상한·상한 하류 절단으로 10곳까지 줄어 유니버스가 됨). 정렬은 점수 내림차순+심볼 오름차순 tie-break로 동일 입력에 항상 동일 출력(재현성). 적용 임계는 `threshold_used`/`relaxed` 메타데이터로 투명하게 기록한다. ③ **이유(reason)**: 시드=원장 note(점수 괄호 제거), 학습="검색 출처 N건 함께 언급", 홉="{개념명} 경유 — …" — 전부 저장된 근거의 표시이며 생성이 아니다. ④ **진입점**: `GET /knowledge/concept-universe?q=`(읽기 전용)+CLI `scripts/concept_universe.py`. **테마 되묻기 통합**(2026-07-25 — 'bts 관련 종목' 사고 2차): 전략 대화의 테마 유니버스 되묻기(FR-STR-071)·빌더(`strategy_builder._theme_companies`)는 정밀 목록 대신 확장 뷰 `knowledge_graph.theme_backtest_companies`를 소비한다 — **학습 앵커 한정**으로 Concept Universe 선정(기본 임계 0.5 이상만 — 완화 편입은 백테스트 제안에 불참)으로 후보를 확장하고(직접 학습 엣지 2곳이 컨셉을 대표하지 못하던 문제), 시드·카탈로그 앵커는 큐레이션 직접 엣지 그대로(지분 홉 노이즈 차단 — HBM 되묻기에 지주·계열 편입 방지), 직접 학습 엣지의 뉴스 보도일은 심볼 매칭 이월(시점 편향 경고 유지). `theme_listed_companies`(정밀 목록 — 직접 엣지 우선·이웃 개념 희석 금지) 계약은 불변. 프론트는 `clarification_priority=theme_universe` 되묻기를 explicit 설정 게이트(시장 질문)보다 먼저 표시한다 — 게이트가 이 질문을 삼키면 컨셉 종목 제한 선택지가 사라지고 업종 전체로 조용히 강등된다(실측 회귀, `page.scroll.test.tsx` 가드). ⑤ **규제 안전**: score·이유·정렬은 공시·IR·검색 출처 등 객관적 관계 근거의 표시일 뿐 추천·전망·우열 판단이 아니다. 모르는 개념은 found=false(생성 거부 — 검색 그라운딩 학습 경로로 유도). 실측: BTS→6종목(하이브 0.81 최상위, 미디어/엔터 업종 전체 아님), HBM→6종목(생산 2+장비·소켓 4).

**FR-STR-072b** [지분 관계 레이어 — DART 타법인출자현황 기반 회사 홉, 2026-07-25] Concept Universe는 검색 co-mention이 확률적으로만 잡는 지분 관계('넷마블=하이브 주요 주주')를 **공시 데이터에서 결정론 수집**해 반영해야 한다. ① **수집**(`scripts/build_equity_edges.py`): DART 사업보고서 '타법인 출자현황'(otrCprInvstmntSttus)을 전 상장사 대상으로 스윕해, 피출자 법인명을 정본 종목 마스터에 정규화 매칭(㈜·괄호 병기 제거, 정확 일치만 — 부분 매칭 오탐 차단)하고 **양쪽 모두 상장사 + 기말 지분율 ≥ 5%**인 관계만 `invests_in` 엣지로 `data/kg-equity-edges.json`(git 추적 — 커밋·배포로 prod 반영)에 저장한다. 재개 가능(진행 파일 gitignore)·`--symbols` 부분 수집은 기존 산출물에 병합. 표시명은 DART 원문('㈜하이브 (주1)')이 아니라 정본 종목명. ② **소비 범위 한정**: 이 엣지는 KG 그래프 본체에 합성하지 않고 Concept Universe만 읽는다(mtime 캐시) — related_universe 확장·테마 되묻기 등 기존 그래프 소비자의 의미 변화를 차단한다. ③ **회사 홉**: 유니버스 후보의 주주/피출자사를 후보 점수 ×0.70 감쇠로 1단계만 편입한다(체이닝 금지). 감쇠 0.70이면 부모 점수 0.72 이상만 기본 임계(0.5)를 넘으므로 재벌 지주 관계가 모든 유니버스로 번지지 않는다(자기 제한 — 저점수 부모의 지분 이웃은 완화 단계에서만). 이유는 "{부모명} 주주(공시 근거) — {지분율 note}"로 공시 출처를 명시한다. 실측: 넷마블→하이브 9.2%(2025 사업보고서) 수집, BTS 유니버스에 넷마블 0.57 편입. 한계: 사업연도 시점 기준(연 1회 갱신 권장), 벤처펀드 경유 간접 투자(LB인베스트먼트→하이브)는 공시 비노출 — 수동 엣지(FR-STR-070b ⑦)가 담당.

**FR-STR-074** [미국 테마어 공시 검색 그라운딩, 2026-08-26] /us 레인은 테마 카탈로그(정본 25종)·시드 그래프 밖의 테마 표현을 **SEC 공시 전문검색으로 학습**해 구성 티커로 세울 수 있어야 한다. ① **문제**: 한국은 네이버 테마 명부(285종)와 검색 그라운딩(FR-STR-069)으로 "mRNA 관련주"에 13종목을 세우는데, /us는 카탈로그 미스면 되묻기로 끝났다 — 시장 격리(2026-08-26)로 KR 체인을 끊어 둔 자리에 미국 판이 없었기 때문이다(실측: EN "mrna-Related Stock Investment Strategy" → "카탈로그에서 찾지 못했다"). ② **소스 선택**: 상용 웹검색이 아니라 **EDGAR 전문검색**(efts.sec.gov, API 키 불필요)을 1차 소스로 쓴다 — 결과가 CIK로 오므로 정본(`us-stocks.json`의 cik 5,939곳)에 **결정론 조인**되고(이름 매칭 오폭원 없음), 근거가 기자의 해석이 아니라 **기업 자신의 연차보고서 기술**이라 "구성 목록은 객관적 소속 정보(사실)"라는 규제 계약과도 맞는다. 질의는 테마어 완전일치 구문·10-K/20-F·최근 3년, 상위 3페이지(300건). ③ **입력 계약**: 그라운딩 입력은 **LLM이 뽑은 짧은 테마어**이지 사용자 원문이 아니다(§ 자연어 해석 구조 원칙). 한정어 정규화(`normalize_theme_term` — "mrna-Related"→"mrna", "US cloud software stocks"→"cloud software")는 조회(`resolve_theme`)와 **같은 규칙**을 공유해, 학습한 이름이 다음 턴에 그대로 다시 잡힌다. ④ **언급 ≠ 소속 — 3중 게이트**: (i) **선별력 — 두 신호의 곱**: ① 공시 등장 건수가 흔한 축(>2,000건)이고 ② 상위 20곳의 GICS 섹터 집중도가 50% 미만이면 상투어로 보고 학습하지 않는다. **한쪽만 보면 멀쩡한 테마가 막힌다**(2026-08-27 사용자 실측 사고): 건수만으로 판정하면 'cancer'(4,261건·집중도 95%)·'oncology'(2,946건·95%)가 막히는데 이들은 상위 후보가 전부 항암 기업이라 관련도 순위가 이미 정리한 경우다; 집중도만으로 판정하면 'data center power'(83건·35% — 정보기술 7·산업재 6)가 막히는데 희소 표현의 분산은 상투어를 뜻하지 않는다. 둘 다 걸리는 것만 차단한다 — climate change 10,000·40%, supply chain 10,000·35%, inflation 10,000·40%, cybersecurity 10,000·30%, artificial intelligence 10,000·35%('climate change'를 학습시키면 셸·EOG·BHP·금광이 확정 15곳으로 나온다 — 기후 테마 기업이 아니라 기후 위험을 공시해야 하는 배출 기업이다). 통과 실측: cancer 95%·oncology 95%·mrna 90%·airline 90%·quantum 75%·humanoid robot 75%·cloud software 60%. 판정 입력은 검색 결과의 구조화된 값(히트 수·후보의 GICS 섹터)뿐이다 — 원문도 공시 본문도 읽지 않는다. (ii) **순위**: 후보 정렬은 공시 **건수**가 아니라 검색 **관련도 점수**다 — 건수 정렬은 3년치 보고서를 낸 회사가 모두 동점이라 사실상 알파벳순이 된다(실측 사고). (iii) **확정**: 서로 다른 공시 2건 이상이 지지하는 기업만 verified, 1건은 pending(콘솔 승인 대기 — 그래프에 합성되지 않는다). ⑤ **LLM 소속 심사**: 후보(티커·회사명·GICS 산업·관련도·공시 건수)의 **닫힌 목록** 위에서 LLM이 "그 테마를 사업의 축으로 하는 기업"을 고르고, 목록 밖 티커는 드롭한다(환각 차단). 프롬프트 실측(9B): "확실하지 않으면 고르지 않는다"는 40곳 중 1~2곳만 골라 학습이 성립하지 않았고, "해당하면 모두 고른다" + 제외 사유 예시를 쓴다. **심사는 10곳씩 나눠 묻고 합집합을 만든다** — 한 번에 40곳을 물으면 같은 모델·같은 프롬프트로도 목록 앞머리만 고르고 나머지를 흘린다(E2E 사고 2026-08-26: mRNA 확정 2곳(MRNA·BNTX)으로 최소 구성 게이트에 걸려 "카탈로그에서 찾지 못했다"가 그대로 재현됐다 — 단위 테스트·주입 실험은 통과했는데 실서버에서 드러난 결함이다). 3회 반복 실측: 배치 10 = mRNA 25/25/25·양자컴퓨팅 21/21/21, 단일 호출 = 2/2/2·9/9/9. 묶음이 작을수록 "해당하는 것을 모두 고르라"가 실제 수행 가능한 과제 크기가 된다. ⑥ **최소 구성 게이트**: verified 4곳 미만이면 테마로 세우지 않는다(카탈로그 빌더 MIN_MEMBERS와 같은 눈높이) — 조용히 축소 반영하지 않고 기존 되묻기가 그대로 나간다. ⑦ **학습 원장·재검색 금지**: 결과는 `data/us-term-lexicon.json`에 저장되고 US 지식그래프가 학습 오버레이로 합성(verified만, 별칭 우선순위는 시드 > 카탈로그 > 학습)해 **다음부터는 검색 없이 결정론으로 해석**된다(실측 재조회 0.00s, 최초 학습 ~20s는 EDGAR 3페이지 + 9B 심사). 검색 **실패**(네트워크·차단)는 저장하지 않는다(복구 후 재시도). TTL(`US_TERM_REGROUND_TTL_DAYS`, 기본 90일) 경과분은 조건부 재학습이며 병합이라 콘솔 검토 상태를 잃지 않는다. ⑧ **개별 기업 차단**: 회사명 그 자체("Moderna")는 테마로 학습하지 않는다(단일 종목 지정 경로 소관). 티커는 **대문자 정확 일치**일 때만 종목으로 본다 — 테마어와 티커 철자가 겹치는 실측(mRNA 테마 vs 모더나 티커 MRNA)에서 대소문자를 뭉개면 그 테마가 영영 학습되지 않는다. ⑨ **시장 격리 유지**: 이 모듈은 한국 기계(term_grounding·knowledge_graph·naver_*·nl_parser·symbol_resolver)를 import하지 않는다 — 소스 스캔 테스트가 강제한다. 소스가 미국 공시라 한국 종목이 섞일 경로 자체가 없다. ⑩ **운영 스위치**: `US_TERM_GROUNDING=off`면 카탈로그만 쓰던 종전 동작으로 즉시 되돌아간다. ⑦ **분류 축과 테마 축의 분리(2026-08-27 사용자 지시)**: 종목 범위를 좁히는 표현은 두 축 중 하나다 — **분류**(GICS 섹터·산업: 분류 체계의 정본, 모든 종목이 하나에 속하고 근거가 정의 자체)와 **테마**(공시·ETF 보유로 관측된 소속 집합, 증거와 시점을 가짐). 한 필드(`universe.sectors`)로 들어오므로 해석 앞단에서 축을 판정한다: ① **분류 registry**(`engine/us_industry_registry.py` — 표기 정확 일치, 단수·복수 허용, LLM 불개입) → ② 큐레이션 카탈로그·시드(분류가 표현할 수 없는 특화 테마: AI 반도체·빅테크·GLP-1) → ③ 공시 학습. **분류 우선인 이유**(실측 2026-08-27): 시드의 산업형 테마는 표본 수준이라 'airlines' 4곳 vs 분류 18곳, 'restaurants' 5곳 vs 54곳, 'semiconductors' 20곳 vs 72곳이다 — 업종 이름에는 업종 분류가 답해야 한다. **시드 정리(2026-08-27 사용자 지시)**: 산업명과 겹치던 시드 테마 11종(항공사·태양광·의료기기·외식·생활용품·철강·구리·철도·폐기물·산업가스·데이터센터 리츠)은 분류의 표본에 불과해 **삭제**하고(노드 11·엣지 40 제거), 그 별칭 26개를 분류 registry의 큐레이션 별칭표(_EXTRA_ALIASES)로 이관했다 — 영문은 분류로 한글은 시드 테마로 갈리던 '한 단어가 두 축에 걸치는' 상태를 없앤다. 개념 앵커 semiconductor(반도체 산업)는 하위 테마의 소속 엣지가 붙어 있어 노드로 남기되 표현('반도체'·'semiconductor')은 분류로 통일했다. 실측 근거: 'airline'을 테마로 학습하면 보잉·에어캡이 섞인 22곳이 나오지만 분류 명부는 정확히 18곳이다. **분류 표기 변종 병합**: 정본 라벨에 같은 업종의 표기 변종이 섞여 있어(실측: 'Banks - Regional' 312 / 'Regional Banks' 6 등 토큰 동일 7건 + 약어 2건) 병합하지 않으면 명부에서 종목이 샌다 — 토큰 다중집합이 같으면 결정론 병합(다수 라벨이 정본), 약어·개명 변종만 큐레이션 별칭표. **과대 분류**: 명부가 600곳을 넘는 분류(섹터 단위)는 전개하지 않고 "업종 필터 미지원" 안내로 보낸다 — 테마 학습으로 흘리면 섹터어를 공시에서 배우려 드는 엉뚱한 경로가 열린다. **양방향 축 가드**: 분류 라벨과 같은 표현은 테마로 **학습하지 않고**(쓰기) 원장에 남아 있어도 그래프에 **세우지 않는다**(읽기) — 실측 오염(2026-08-27): 축 판정이 없던 QA 실행에서 'healthcare'가 공시 학습으로 21곳짜리 테마가 돼 그래프에 올라갔고 업종 필터 미지원 계약 테스트가 깨졌다. 출처 축은 `ParsedStrategy.universe_source`(theme_catalog | theme_learned | industry)로 남긴다 — canonical DSL 화이트리스트 밖이라 기존 전략 해시는 불변. ⑧ **테마의 시점(PIT)**: 학습 테마의 각 구성원에 소속을 처음 확인한 공시 제출일(`first_known_date`)을, 테마에는 확정 구성원 중 가장 이른 날짜와 **검색이 들여다본 창의 시작일**(`observed_from`)을 함께 싣는다 — 창이 3년이라 관측일이 전부 그 뒤에 몰리므로 창을 함께 두지 않으면 "3년 전 생긴 테마"로 오독된다. 소비자는 "이 날짜부터는 사실이었다"까지만 주장할 수 있다(한국 KG 테마 엣지의 `first_known_date`와 같은 자리). 백테스트 창과의 결속(경고냐 창 강제냐)은 별건이다. ⑨ 분류 축은 시점 이력이 없다(현행 분류) — 지수 유니버스의 현행 명부 고지와 같은 성격의 한계로, 필터 승격 시 함께 다룬다. ⑪ **회사 앵커 축 — 'X 관련주'(2026-08-27)**: 분류·테마 어디에도 속하지 못하던 세 번째 축을 세운다. **문제**: ⑧의 개별 기업 차단과 지식그래프의 `company:` 노드 격리가 맞물려, 'nvidia 관련주'는 테마로도 단일 종목으로도 설 자리가 없었다 — 표현이 통째로 사라지고 미국 전체 유니버스(5,947종목)만 남았다(실측 2026-08-27: /us "nvidia Related Stock Investment Strategy"). **축 진입 조건은 표기 판정 둘뿐**이다: (i) 범주 접미가 있을 것(`has_group_suffix` — '관련주'·'테마'와 영어 판 "related/linked/stocks/names/companies/shares", 시장 접두 '미국'·'US'는 범주를 바꾸지 않으므로 제외) (ii) 접미를 벗긴 표기가 정본 상장사와 정확히 일치할 것(`us_company_anchor` — 티커는 대문자 정확 일치, 회사명은 영문·한글 모두 대소문자·공백 무시). 접미 없는 'nvidia'는 종전대로 단일 종목 지정 소관이다. **학습은 테마와 같은 기계, 다른 심사 축**이다(공통 몸통 `_ground`): 앵커 회사명으로 EDGAR 전문검색 → CIK 정본 조인 → LLM이 **닫힌 후보 목록** 위에서 "기준 기업과 공급·고객·파트너·경쟁·핵심 기술 의존 관계가 사업에 실재하는가"를 심사한다(테마 프롬프트의 '그 사업을 영위하는가'와 다른 질문 — 같은 프롬프트를 쓰면 9B가 앵커를 테마어로 읽어 후보를 거의 다 버린다). 선별력·관련도 순위·verified 승격·최소 구성 4곳 게이트는 테마 축과 동일하다. **앵커 자신은 후보에 있으면 구성에 포함**한다 — 가장 직접적인 종목이 빠지면 누락으로 읽힌다. **조회 열쇠는 표기가 아니라 앵커 티커**다(`related:NVDA`) — 'Nvidia 관련주'와 'nvidia Related Stock'은 같은 집합이므로 표기를 키로 삼으면 언어별로 갈린다. 그래서 `related:` 노드는 테마 별칭 색인에서 제외한다(별칭 경쟁 없음). **원장 표기는 한국어 정본으로 고정**하고(`term: "Nvidia 관련주"`, `kind: company_related`, `anchor: NVDA`) 표시 라벨만 요청 언어를 따른다(/us는 "Nvidia-related stocks") — 학습 시점의 언어에 따라 원장이 갈리면 같은 집합이 두 이름으로 남는다. 출처 축은 `universe_source="company_related"`. 소비자는 테마 축과 같다: `capability_validator`(학습분 **결정론 조회만** — 검증기는 네트워크·LLM을 부르지 않는다)와 primary의 생성·수정 두 레인. 실측: /us "nvidia Related Stock Investment Strategy" → 후보 40곳·소속 26곳·확정 15곳(NVDA·AMD·INTC·ARM 계열 + CoreWeave·Nebius·IREN 등 인프라 수요처)이 지정 종목으로 전개. ⑫ **분류 판정의 반영 확인(2026-08-27)**: planner-first가 MARKET/SECTOR/SINGLE_STOCK/ETF 분류를 받으면 "해석기가 원래 필드로 표현했을 것"이라고 보고 **확인 없이** 해석 완료로 처리하던 계약을, 전략에 실제로 반영됐는지 값 대조하는 계약으로 바꾼다. 확인 없는 가정은 두 컴포넌트가 서로 "상대가 했겠지"로 어긋나는 순간 표현을 삼킨다 — 위 사고의 직접 원인이다(분류기는 SINGLE_STOCK NVDA로, 해석기는 `universe.sectors`로, 검증기는 그것을 제거). 반영이 없으면 미해결로 남겨 해석 체인·되묻기가 표면화한다(조용한 소실 금지). 대조는 확정값끼리만 하고 사용자 원문을 다시 읽지 않는다. 'NOT_UNIVERSE'(지표 조건 구 오라우팅 백스톱)는 판정 자체가 결론이라 반영할 필드가 없으므로 대조 대상이 아니다. **분류 단계의 접미 가드**도 같은 사고의 공범이다: 종목 해석기가 문구 **안에서** 회사명을 찾는 스캐너(`find_in_text`)를 폴백으로 쓰기 때문에 'nvidia Related Stock'이 NVDA 하나로 접혔다 — 범주 접미가 붙은 표현은 SINGLE_STOCK으로 분류하지 않는다. ⑬ **표기 정규화·미달 항목 자가 치유(2026-08-27)**: (i) 별칭 대조 키(`_norm_key`)는 하이픈을 **공백과 같은 낱말 구분자**로 본다 — 영어 레인이 복합어를 하이픈으로 묶어 내놓기 때문에("humanoid-robotics", "data-center power infrastructure") 하이픈을 남기면 같은 테마가 표기 하나로 카탈로그를 빗나간다(실측: /us 영어 게이트에서 테마 6건이 미해석 → 공시 학습으로 샜다). 정본 별칭과 조회어가 같은 규칙을 통과하므로 짝이 어긋나지 않으며, 충돌 위험은 별칭 충돌 금지 테스트가 감시한다. (ii) **미달 항목의 TTL은 성공분과 다르다** — 확정 구성 4곳 미만은 '이 표현은 테마가 아니다'라는 결론이 아니라 '이번 검색이 세우지 못했다'는 잠정 상태다(표기 정규화 결함·검색 표본·심사 흔들림 어느 것으로도 0곳이 나온다). 90일 고착은 상류를 고쳐도 증상을 남긴다(실측: 하이픈 결함으로 빗나간 테마 3건이 빈 원장 항목으로 굳어 있었다). 재검색 비용은 아끼되(`US_TERM_MISS_REGROUND_TTL_DAYS`, 기본 3일) 자가 치유 주기를 짧게 둔다. ⑭ **ETF 상품 티커 소실 — 프롬프트는 지렛대가 아니다(2026-08-27)**: "Buy SPY when …"이 `markets=["US_ETF"]`(미국 ETF 전체)로 파스돼 **상품 하나가 전체 유니버스로 벌어졌다**. **프롬프트 수정은 전부 기각됐다** — 반복 측정(각 5~10회)에서 규칙을 옮길 때마다 **이기는 티커만 바뀌는 시소**였고, 어느 변형도 커밋 상태(4.8)보다 낫지 않았다: 4.8=URA·DIA·SOXX(3/5), 규칙 6 재배치=URA·SPY·ITA(3/5, 무관한 골든크로스 파스까지 5/5→0/5로 깨뜨림), sectors 예시만=URA·SOXX(2/5, DIA를 10/10→0/10으로 깨뜨림). 프롬프트에는 "SPY·QQQ 같은 ETF 티커는 상품 지정" 규칙이 **이미 있었다** — 분량·배치 문제가 아니라 이 층에서 수렴하지 않는 문제다. **해법은 결정론 복구**(`primary._apply_designated_symbol`): planner가 뽑은 표현을 `classify_universe`가 정본 registry로 SINGLE_STOCK + 티커까지 이미 확정해 두므로, 그 관찰값이 전략에 반영되지 않았으면 지정 종목으로 **적용**한다(⑫의 반영 확인이 만든 자리를 잇는다). 계약은 다른 적용기와 같다 — 입력은 LLM이 뽑은 짧은 표현, 확정은 정본 registry, 이미 지정 종목이 있으면 불개입, 원문은 읽지 않는다. **범주 접미 가드 필수**: 'X 관련주'가 SINGLE_STOCK으로 분류돼 들어오면 적용하지 않는다 — 적용하면 ⑪의 사고(유니버스가 한 종목으로 조용히 좁혀짐)를 그대로 되살린다. 실측(파이프라인 전수, 각 5회): SPY·URA·DIA·SOXX **5/5**, 합 **4/5**로 프롬프트 최고치(3/5)를 넘었고 **프롬프트는 한 글자도 바꾸지 않았다**. **미해결 2종**: (i) ITA — planner가 티커 대신 설명구('US aerospace and defense ETF')를 뽑아 관찰값에 티커가 없다. 원문에서 티커를 다시 긁는 것은 대원칙 1 위반이므로 이 층의 경계다. (ii) 범위 표현의 수식어 축약 — "Among US health care large caps"가 `sectors=["health care"]`로 줄어 8종목 큐레이션 테마가 헬스케어 업종 전체로 벌어진다. 사용자가 'large caps'를 말했다는 사실이 LLM 출력에 남지 않아 결정론 복구가 성립하지 않는다(프롬프트 예시 추가는 DIA를 깨뜨려 기각). **교훈**: LLM 소실은 **N회 반복 + 대조군**으로만 판정한다. 3케이스 표본으로 "해결됐다"고 판단했다가 넓힌 표본에서 반증됐다. ⑮ **분류 축 표기 변종 — '&'와 'and'(2026-08-27)**: 분류 registry의 조회 키(`_norm`)가 '&'를 그대로 둬서 정본 'Aerospace & Defense'와 입력 'aerospace and defense'가 다른 키가 됐다(같은 파일의 `_token_key`는 이미 'and'를 무시하고 있었다 — 두 규칙이 어긋나 있었다). 그 결과 **GICS 산업명이 ⑦의 양방향 축 가드를 통째로 빠져나가** 공시 학습으로 10곳짜리 '테마'가 됐고, /us "On ITA, the US aerospace and defense ETF …"가 ETF 상품 대신 **개별 방산주 10종목 포트폴리오**로 조립됐다(게이트 #81). 표기 변종 판정이지 의미 해석이 아니다 — '&'를 'and'로 정규화해 두 규칙을 맞췄다. 오염된 원장 항목은 제거(읽기 가드가 이미 배제하지만 계약 위반 산출물은 남기지 않는다). 회귀 `test_ampersand_and_and_are_the_same_classification`. ⑯ **ETF 유니버스 × 업종 필터 거절(2026-08-27)**: ETF는 여러 기업을 묶은 **상품**이라 GICS 분류가 없다(정본이 us-etf-master.json이고 종목 정본이 아니다) — 교집합이 항상 공집합이라 전략이 조용히 0종목이 된다(실측: US_ETF 31종 × 'Aerospace & Defense' → 0). ⑮의 축 가드를 복구하자 드러났다(종전에는 산업명이 테마로 둔갑해 이 조합을 가리고 있었다). 검증기는 ETF일 때 sectors를 etf_theme로 승격하며 비우므로 **필터를 붙일 수 있는 자리는 해석 체인뿐**이다 — `_apply_us_industry`가 ETF 유니버스면 적용하지 않고 미해결로 남겨 되묻기가 표면화한다(조용한 공집합 금지, ETF × 기업 재무지표 거절과 같은 계약). 주식 유니버스의 업종 필터는 불변이다. 회귀 `test_us_etf_universe_does_not_take_industry_filter`. ⑰ **미해결로 남기는 것(2026-08-27 측정 확정)**: (i) **ITA 티커** — planner가 티커 대신 설명구를 뽑아 관찰값에 티커가 없다(⑭의 결정론 복구가 닿지 못하는 경계). (ii) **수식어 축약** — "health care large caps"→"health care". (iii) **거래대금 오분류**(게이트 #29) — "daily trading value of $100 million or more"가 `technical.volume_spike > 100`(거래량 급증, 단위 미환산)으로 파스된다(인터프리터 5/5 결정적). 셋 다 **LLM 출력에 사용자가 그 말을 했다는 흔적이 남지 않아** 결정론 복구가 성립하지 않고, 원문 재독은 대원칙 1 위반이다. #29의 보유기간 소실이 안내되지 않는 것은 **버그가 아니라 정책**이다 — 미반영 수치 안내는 2026-08-01 사용자 지시로 폐지됐고 되살리지 않는다(FR-STR-019j ⑤). ⑱ **게이트 사각지대 4종(2026-08-27)**: 위 결함이 오래 보이지 않은 이유다. (i) `--lang en` 하니스가 **지역 신호를 보내지 않았다** — /us는 지역이 곧 표시 언어인데 `language`를 싣지 않아 백엔드가 한국 요청으로 응대했고(지역 격리 미발동·기본 유니버스 KOSPI200), 정작 되묻기 대조 코드는 "--lang en에서는 영어로 온다"를 전제해 하니스가 스스로와 어긋나 있었다. `qa_redteam_validation`·`qa_free_input`·`qa_multiturn_binding`도 같은 누락(사람이 읽는 하니스라 별건). (ii) 테마 판정 술어가 `us_industry`를 보지 않아, 업종 필터 승격 후 멀쩡히 반영된 미국 업종 전략이 '미반영'으로 잡혔다. (iii) ETF 판정이 `universe==["US_ETF"]`를 무조건 정상으로 인정해 상품 지정 소실을 통째로 놓쳤다 — 예시가 티커를 짚었으면(정본 ETF 마스터 자기검증 ground truth) 그 티커가 지정 종목에 있어야 통과로 바꿨다. ⑲ 회귀: `test_us_term_grounding.py`(정규화·정본 조인·관련도 순위·선별력 게이트·닫힌 목록 심사·verified/pending·최소 구성·재검색 금지·검색 실패 미저장·기업명 차단·학습 오버레이 해석·**표기 판정·회사 앵커 학습·앵커 키 조회·체인 전수 회귀**), `test_planner_first.py`(**분류 반영 확인·NOT_UNIVERSE 예외**), `test_us_region_isolation.py`(KR 기계 import 금지·체인 배선).

**FR-STR-075** [이동평균 지속 상태와 조건 라벨의 기간 병기, 2026-09-10, 엔진 v16.6.0] ① **상태와 사건은 다른 조건이다** — "종가가 60일 이동평균 위에 있는 동안"은 매 봉 참인 게이트이고 "60일선 상향 돌파"는 그 하루의 사건이다. 단순이동평균(`technical.ma_crossover`)에는 EMA에만 있던 지속 상태 평가가 없어(FR-STR-019y ⑥) 상태 표현이 교차로 옮겨졌고, 조건이 하루로 좁아졌다. 엔진이 두 SMA(그리고 `short_period=1`=종가 vs SMA)의 지속 상태를 직접 평가하고(`mode` above/below — 벡터·행별 경로 동일 의미), registry 허용 연산자에 `>`·`<`를 열고, 컴파일러는 부등호를 **기간을 버리지 않고** mode로 옮긴다(EMA와 공용 분기). 역컴파일도 상태와 두 기간을 보존한다 — 종전에는 두 선 상태가 라운드트립에서 '가격 vs 한 선'으로 되돌아가 수정 턴이 다른 전략을 만들었다. 인터프리터 프롬프트 5-3은 **사건=`crosses_above`/`crosses_below`, 상태=`>`/`<`**로 갈라 지시한다. ② **조건 라벨은 기간을 버리지 않는다** — 요약 카드·배지의 이동평균 라벨이 방향만 보고 'MA 골든크로스'로 뭉개, "종가 vs 60일선"과 "20일선 vs 60일선"이라는 서로 다른 두 진입 조건이 같은 문구 두 줄로 나갔다(2026-09-10 사용자 지적). 매매사유(`engine/trade_reason.py`)와 같은 문구로 기간을 싣고(`종가가 60일선 상향 돌파`·`20일선-60일선 골든크로스`·`…위 유지`), `short_period=1`은 '1일선'이 아니라 종가로 읽는다. 기간을 모르는 레거시 데이터만 종전 일반 라벨로 폴백한다. ③ **반영한 표현을 미지원으로도 보고하면 안내가 모순된다** — 조건으로 컴파일된 인용을 `unsupported_features`에 이중 기입하면(프롬프트 4-1 위반) 반영된 조건에 "지원하지 않아 반영하지 못했어요"가 붙는다. 잔여 미지원 안내는 전략에 남은 조건의 `source_text`를 감싸는 보고 항목을 제외한다(값-대기 대조와 같은 표기 포함 판정 — 원문을 읽지 않는다). 포함 방향이 한쪽뿐이므로 "평소보다 3배"처럼 조건에 담을 수 없는 짧은 조각은 그대로 안내된다. 같은 규칙을 **다른 인용**으로 다시 부르는 경우(이미 이동평균 하향 돌파 청산이 있는데 다시 말한 '추세 이탈')는 표기 대조로 가릴 수 없어 안내가 그대로 나간다 — 프롬프트 4-1에 조건부 조항을 넣는 우회는 실측에서 다른 청산 답변을 망가뜨려(‘20일 보유 후 청산’의 hold_period_days 미반영, A/B 3회씩 재현) 철회했다. 조건부 규칙 대신 출력 형태로 푸는 길이 나올 때까지 미해결로 둔다. 회귀: `test_engine_signals.py`(상태 지속·교차 하루·사유 기간), `test_strategy_conversation.py`(SMA 상태 컴파일·이중 기입 침묵과 그 경계), `strategySummary.test.ts`(두 조건 라벨 구별·상태 라벨).

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
| 월별/연도별 수익률 | 기간별 수익 분해 (달력 월 기준, 월말 equity 대비) — **표 위에 막대 차트**(2026-08-18): `BacktestChart` `monthly_returns` 히스토그램(lightweight-charts)으로 x축은 백테스트 연도(연 눈금에만 연도 표기, 달 눈금은 비움 — 한 연도 = 막대 12개), 0선 위(상승)는 빨강·아래(하락)는 파랑, 툴팁은 'YYYY년 M월 + 수익률', 범례는 좌상단 가로 한 줄의 '월간 수익/손실' 하나만(자산곡선 계열 '나의 전략'·'벤치마크'는 이 차트에 없는 계열이라 표시하지 않음, 2026-08-18 사용자 신고). 표와 같은 행(최근 N년)을 과거→현재 순으로 그리고 값이 없는 달은 막대가 없다 (`monthlyReturns.ts::buildMonthlyReturnSeries`) |
| 롤링 수익률 | 투자 기간(1·3·6개월·1·2·3년)별 롤링 구간 통계 **라인 차트 + 표**(2026-08-18 — 표 위에 선택 투자 기간의 매 거래일 롤링 수익률 전 구간 라인 차트(`BacktestChart` rolling_returns, 기간 버튼 1·3·6개월·1·2·3년 — 5년은 미지원, 툴팁은 지점이 뜻하는 창을 '시작일 ~ 종료일'로 표기), 아래에 기간별 통계 표) — 매 거래일 진입 창의 구간 수·평균·중앙값·하위 5%·상위 5%·최저·최고 수익률(해당 구간 날짜 병기)·손실 구간 비율·벤치마크 초과 비율·구간 안 평균 MDD·최악 MDD(창 시작을 첫 고점으로 잼). [2026-09-13 재정비] ① **12개월 초과 창(2년·3년)의 수익률은 연환산(CAGR)**으로 표시하고 행 라벨에 '연환산'을 병기한다(1개월 누적과 3년 누적이 같은 열에 놓여 비교 불가하던 문제 — `toDisplayReturn`, 창 단위로 변환한 뒤 통계를 내므로 최저·최고 창은 누적 기준과 같은 창) ② **벤치마크 대비**: 결과의 `benchmark_equity`로 같은 창의 벤치마크 롤링 수익률을 계산해 차트에 초록 선(결측 지점은 선 끊김)과 툴팁 행을 더하고, 표에 '벤치마크 초과 비율'(전략 > 벤치마크인 창 비율, 벤치마크 평균 병기 — 벤치마크가 양 끝 모두 있는 창만 분모) 열을 둔다(벤치마크 없으면 '—'와 안내) ③ 하위 5%·상위 5% 백분위(선형 보간) 열 추가 — 단일 최저·최고 창은 하루 노이즈에 좌우되므로 분포를 병기 ④ 라인 차트는 월별 차트와 같은 BaselineSeries(0 위 빨강·아래 파랑) ⑤ 각주에 '구간 수는 겹치는 창을 모두 센 것이라 독립 표본 수가 아님' 고지. 월별 수익률 표와 탭으로 전환, 창을 담지 못하는 투자 기간은 행 생략, 불완전 창(백테스트 시작 이전으로 나가는 구간)은 제외 (`rollingReturns.ts`, `RollingReturnTable.tsx`) |
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

**FR-BT-031c** [기록 목록 표시 캐시, 2026-08-13 개정] 백테스트 기록 목록(`/backtest`)은 사용자가 **방금 실행·저장한 기록이 빠진 목록을 보여서는 안 된다.** 목록은 클라이언트가 조회하며(`GET /api/backtest/history`), 조회 결과는 세션 메모리 캐시(`lib/backtest-history-cache.ts`)에 담아 다음 진입에 즉시 그린다(로딩 없음) — 이 캐시는 목록이 바뀌는 순간 **반드시 버려야** 한다: ① 결과 자동 저장과 ② 전략 저장 시의 `POST /api/backtest/history`(`components/strategy/backtest/BacktestDashboard.tsx`)는 요청 발행 시점에 `invalidateBacktestHistoryCache()`를 호출하고, ③ 카드 삭제는 지운 항목을 뺀 목록으로 캐시를 갱신한다(`app/backtest/BacktestHistoryView.tsx`). 캐시가 없으면 로딩 인디케이터를 노출한다(`app/backtest/BacktestHistoryLoading.tsx` — 라우트 fallback `loading.tsx`와 공용). 목록 조회 본체는 `lib/server/backtest-history-list.ts`를 `/api/backtest/history` GET과 공유해 경로가 갈라지지 않게 한다. 비로그인·비활성 계정은 401 → 빈 목록으로 empty state를 보여준다. **주의:** 목록을 서버 컴포넌트에서 조회해 넘기면(`dynamic = "force-dynamic"`) 탭 진입마다 서버 왕복을 기다려 매번 로딩이 노출되므로 그 방식으로 되돌리지 않는다. 같은 이유로 상단 메뉴가 가리키는 페이지 중 서버 컴포넌트가 원격 DB를 await 하는 곳(`/dashboard`·`/pricing`)은 라우트 `loading.tsx`를 두고 조회를 한 왕복으로 묶으며(세션 확인은 DB 없는 `getSessionUserId` → 계정 상태·데이터 조회를 `Promise.all`), 서버 조회가 없는 메뉴 페이지(`/analytics`·`/virtual-account`·`/backtest`)는 `Link prefetch`로 전체를 미리 받는다(2026-09-08). 전 페이지가 동적 렌더(루트 레이아웃이 요청 헤더로 지역을 읽음)라 기본 prefetch는 loading 경계까지만 미리 받는다. 같은 맥락에서 서버가 넘긴 초기 데이터로 그릴 수 있는 위젯이 **클라이언트 추가 요청의 응답을 기다린 뒤에야 내용을 그려서는 안 된다** — 계좌별 수익률 차트는 개설 월을 얻으려고 계좌 목록 API를 한 번 더 기다리는 동안 빈 차트를 보였으므로, 개설일을 `AccountMonthlyData`에 동봉해 첫 렌더부터 그린다(2026-09-13, `components/dashboard/AccountProfitChart.tsx`). 클라이언트 재조회는 화면을 갱신하는 용도이지 첫 표시의 전제가 아니다.

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
- 모든 창에서 IS(학습) 구간 종료일 < OOS(검증) 구간 시작일이어야 하며(look-ahead 금지), 학습된 파라미터는 해당 OOS 창에만 적용하고 다음 창에서 재학습한다. OOS 창의 지표 워밍업은 엔진이 startDate 이전으로 동적 프리로드(`max(_max_indicator_period, 랭킹 lookback)` × 1.6 + 40 캘린더일, 최소 400일)해 보장한다 — 랭킹 lookback 패널도 이 프리로드 가격을 쓴다(FR-BT-013b, v16.12.0 이전엔 창으로 잘린 종가만 써 OOS 창 첫 lookback 거래일 동안 순위가 비었다).
- UI가 표시한 학습/검증 거래일 수는 `is_bars`/`oos_bars`로 백엔드에 그대로 전달되어 창 분할에 사용된다(표시 = 실행). 롤링·확장(anchored) 모두 검증 길이를 다 채우는 창만 만들고 마지막 조각 창은 만들지 않는다 — 실행 창 수 = UI 예상 구간 수 `floor((T−is)/oos)`(2026-08-19: 확장 모드가 잘린 마지막 창을 하나 더 만들어 UI보다 1개 많던 표시≠실행 수정). 창 수 상한 24개 초과·데이터 부족 시 명확한 에러를 반환한다.
- 최적화 대상 파라미터 UI 칩은 배지 텍스트가 아니라 **실제 탐색 공간의 경로(path)에서 직접 생성**한다(`buildWalkForwardParameterDescriptors` — 한글 라벨: "MACD 단기", "볼린저 표준편차" 등, 진입/청산 중복 시 구간 접미사). 오버라이드/제외/step 설정은 경로 키로 정확히 해당 파라미터에만 적용된다(레거시 라벨 키는 폴백 지원).
- 사용자가 수정한 파라미터 탐색 범위(min/max/step)는 자동 생성 범위로 재클램프하지 않고 그대로 적용하며, 파라미터별 최적화 제외(`excluded_parameters`)를 지원한다.
- 그리드·베이지안 최적화 모두 의미 제약(단기 < 장기: `shortMA<longMA`, `fastPeriod<slowPeriod`, `shortPeriod<longPeriod`)을 강제한다.
- 목표 지표가 손익비(`profitFactor`)일 때 손실 거래 0건인 조합은 엔진이 `None`(=∞, 0.0과 구분)을 돌려주므로, 그리드·베이지안 모두 `target_sort_value`(grid_optimizer.py 공유)로 ∞를 최대화의 최상값으로 취급해야 한다(None을 정렬 키·optuna 목표값에 그대로 쓰면 그리드는 TypeError로 창 실패, 베이지안은 시도를 FAIL 처리해 무손실 조합이 절대 선택되지 않던 2026-08-19 감사 결함). `/optimize` 응답 스키마의 metrics·target_value도 None을 허용한다.
- 집계는 NaN/Infinity를 표본에서 제외하고 CAGR·총수익·MDD·Sharpe·Calmar·승률·손익비·거래수·평균 거래손익(expectancy)을 제공한다. 모든 창이 실패하면 부분 결과 대신 에러를 반환한다(Fail Fast).
- 설정 화면의 학습·검증 창 길이는 **구간 길이(학습+검증 합)와 학습 비중(20~80%) 두 개의 슬라이더**로 조절한다. 학습 비중을 올리면 학습기간이 늘어난 만큼 검증기간이 줄어 두 기간이 항상 반대로 움직이고, 구간 길이는 그대로 유지된다. 길이를 각각 조절하는 슬라이더(학습기간·검증기간)를 되살리지 않는다 — 검증기간 슬라이더의 최대값이 `전체 기간 − 학습기간`이라 학습을 늘리면 눈금 자체가 줄어, 값이 그대로인데도 손잡이가 오른쪽으로 밀려 "두 기간이 같이 늘어난다"로 보이던 2026-08-19 사고의 원인이다. 학습·검증 비율은 같은 화면의 눈금 막대(고정 개수의 세로 눈금, 학습=파랑·검증=주황)로 함께 보여준다.
- WFE 구간 표시·설명 문구는 과거 데이터에서 관측된 사실만 서술한다("성과 유지 / 대부분 유지 / 일부 감소 / 큰 폭 감소 / 대부분 소실") — "실전에서도 재현될 가능성" 같은 전망, "추가 검증 권장" 같은 행동 제안, "우수·위험" 같은 우열 평가어는 규제 안전 원칙 위반이므로 쓰지 않는다(2026-08-19 정정). 검증 창이 63거래일(약 3개월) 미만이면 설정 화면에서 CAGR 연환산 잡음 안내를 표시한다(실행은 막지 않음). 같은 화면 안의 용어는 학습기간·학습 비중·구간 수·워크포워드 분석으로 통일한다(훈련 비율·분할 수·검증 결과 혼용 금지).
- **WFE(Walk-Forward Efficiency)는 창별 OOS CAGR 평균 ÷ 창별 IS CAGR 평균(연환산끼리, Pardo 정의)** 으로 계산해야 한다. 총수익률(totalReturn)로 나누어서는 안 된다 — IS 창이 OOS 창보다 길어(UI 기본 50%:15%≈3.3배) 완전 정상성 전략(IS=OOS CAGR)조차 WFE≈0.3으로 '과최적화' 판정을 받는다(2026-08-19 감사·수정). IS·OOS 한쪽만 유효한 창은 표본에서 함께 제외해 분자·분모의 창 집합을 일치시킨다. IS 평균 CAGR ≤ 0이면 `wfe_valid=false`로 해석 불가를 알린다. 응답은 `wfe_basis:"cagr"`를 포함하며(스키마 선언 필수), 이 키가 없는 구버전 저장 결과는 UI가 '총수익률 기준 구버전' 안내를 붙여 표시한다.
- 오래 걸리는 작업이므로 **예상 소요 시간을 실행 전에 미리 안내**해야 한다. 총 백테스트 수 = 준비 1회(백엔드가 창 분할 전에 기준 기간을 확인하는 `_get_backtest_dates` 실행) + 구간 수 × (구간당 백테스트 + OOS 1회)이며, 구간당 백테스트는 그리드=조합 수·베이지안=시도 수다. 베이지안 최적화기(`OptunaOptimizer`)의 70/30 단일 홀드아웃 검증(`_holdout_validate`, 옛 이름 `_walk_forward_validate` — 워크포워드가 아니라 한 번 나누는 홀드아웃)은 `optimize(holdout_validation=True)` 옵트인이며 `/optimize` 리포트(`LocalOptimizationAgent`)만 켠다 — 워크포워드는 켜지 않아 창당 백테스트가 정확히 시도 수 + OOS 1회다(2026-08-19: 무조건 실행돼 결과도 안 쓰는 백테스트를 창당 2회씩 낭비하던 결함 수정). 백테스트 1회당 소요는 기준 백테스트(전체 기간) 실측 시간(`result.executionTime`)을 **스케일 없이 그대로** 사용하고(실측상 1회 비용은 구간 길이와 거의 무관 — 종목별 데이터 로드+지표 계산 고정비가 지배적이라, 구간 길이 비율로 선형 스케일하면 수 배 과소추정되어 실행 중 라이브 ETA와 크게 어긋난다), 오차를 감안해 범위(0.7~1.4배)로 표시한다(기준 실측이 없으면 폴백 상수). 실행이 시작되면 SSE로 스트리밍되는 실측 `timing.total`의 지수이동평균으로 남은 백테스트 수를 곱해 **남은 시간(라이브 ETA)을 계속 갱신**한다(`WalkForwardPanel`).
- `POST /walk-forward/stream`은 SSE로 창 단위 진행률(`{type:progress, window, total, is_period, oos_period}`)을 스트리밍하고, 클라이언트 연결 종료(취소 버튼 포함) 시 **시도/조합(=백테스트 1회) 단위로** 협조적으로 취소한다 — `should_cancel` 훅이 창 경계뿐 아니라 그리드 조합 루프(`grid_optimizer`)와 베이지안 trial 콜백(`optuna_optimizer`의 `study.stop()`), OOS 실행 직전까지 배선되어, 취소 후 진행 중이던 백테스트 1회만 마치고 즉시 중단된다(창 전체를 기다리지 않음). 벽시계 제한은 전용 `WALK_FORWARD_TIMEOUT_S`(기본 3600초, 창×시도만큼 백테스트를 반복하므로 단일 백테스트 제한 600초보다 커야 함) 초과 시 error 이벤트로 종료하며, 진행 이벤트가 없는 침묵 구간에는 15초 간격 SSE keep-alive 주석을 내보낸다. Next 프록시(`/api/backtest/walk-forward/stream`)의 안전망 타임아웃은 반드시 백엔드 제한보다 커야 한다(같거나 작으면 프록시가 먼저 끊어 사용자에게 "연결 끊김"으로 보인다). 프론트는 `runWalkForwardStream`으로 소비한다.

**FR-BT-049c** 워크포워드·최적화 성능(`engine/prep_cache.py`, `engine/wfa_workers.py`, `BacktestEngine.optimization_session()`):
- 최적화(그리드·베이지안)와 워크포워드는 지표(metrics)만 쓰는 백테스트를 같은 날짜 범위에서 반복하므로 **최적화 세션** 안에서 실행해야 한다. 세션 동안 엔진은 종목별 Phase1 산출물(지표 계산 df·전처리 pdf·리졸버 로그)을 (종목·워밍업 시작일·기간 경계·배당 옵션·구조 파라미터 서명) 키로 재사용하고, 결과 화면 전용 부가 산출물(리밸런싱 6주기 비교)은 만들지 않는다. **결과 지표·거래·자산곡선은 세션 유무와 무관하게 동일해야 한다**(회귀 테스트가 on/off를 대조).
- 구조 파라미터(지표 컬럼을 결정하는 기간류) 화이트리스트 `STRUCTURAL_PARAM_KEYS`는 `IndicatorEngine.calculate`·`DataResolver._get_required_columns`가 params에서 읽는 이름 전부를 포함해야 한다(소스 스캔 테스트). 임계값·방향 등 비구조 파라미터는 키에서 제외되어 캐시 적중을 만든다. 예산은 `BACKTEST_PREP_CACHE_MB`(기본 2048)로 묶고 LRU로 비운다. 세션은 요청 간에 살아남지 않는다(야간 데이터 갱신 후 낡은 값 금지).
- 워크포워드 창은 서로 독립이므로 `WALK_FORWARD_WORKERS`(기본 min(cpu−1, 8, 창 수), 1=순차)가 2 이상이면 **spawn 프로세스 풀**로 병렬 실행한다. 병렬 결과는 순차와 동일해야 한다(창 독립·옵튜나 시드 고정). fork는 쓰지 않는다(부모 스레드·Polars/OpenMP 상태 상속 데드락). 워커는 `BacktestEngine.worker_spec()`으로 같은 엔진을 다시 만든다 — 이 메서드가 없는 엔진(테스트 스텁)은 순차로 돈다. 워커의 Phase1 스레드 수는 `BACKTEST_PHASE1_THREADS`(코어÷워커, 최대 4)로 낮춘다. [2026-09-17] 세션 캐시 예산·Phase1 스레드는 **띄운 워커 수가 아니라 실제로 도는 창 수**로 나눠 창 작업마다 넘긴다(`WindowPool.window_resources`, 환경변수로 고정한 값은 존중). 풀은 창 수를 알기 전에 힌트(슬라이더 경로=`MAX_WINDOWS`)로 워커 8개를 띄우므로, 워커 수로 나누면 창 3개짜리 실행이 캐시 1/8(256MB)·스레드 1로 돌았다 — 코스피 PER·PBR 10년 전략 실측: 종목 준비물이 담기지 않아 적중 0(LRU라 일부만 담기면 한 종목도 적중하지 못한다), 시도당 약 23초 vs 캐시가 다 담기면 약 9초. 진행 이벤트 `workers`도 창 수를 넘지 않는다(프론트 "8개 구간 동시 실행" 표기 사고). **알려진 한계**: 전 시장·장기 전략의 세션 준비물(10년 약 1.8GB, 5년 창 약 0.9GB)은 총예산 2048MB를 창 수로 나누면 여전히 넘칠 수 있다 — 총예산 상향은 운영 메모리(Modal WFA 24GB) 결정이라 보류.
- 병렬 진행 이벤트는 창별 이벤트에 합산 필드 `windows_done`·`trials_done`·`workers`·`active_windows`를 붙이며, 프론트(`WalkForwardModal`)는 이 필드가 있으면 합산 진행률·'실행 중 구간'·워커 수로 나눈 라이브 ETA를 표시한다. 순차 이벤트에는 이 필드가 없다(기존 계약 유지). 실행 전 예상 소요 시간은 캐시를 반영해 (준비 1 + 구간×2)회 전체 비용 + 나머지 시도 10% 비용으로 추정한다.
- 취소는 부모가 mp.Event를 세우면 워커가 시도(백테스트 1회) 경계에서 협조적으로 멈춘다. 워커 프로세스가 죽으면(BrokenProcessPool) 워커 수를 줄이라는 명확한 오류로 끝낸다.
- **Phase1 프로세스 풀**(`engine/phase1.py`, `engine/phase1_pool.py`): 종목별 준비 계산은 GIL에 묶여 스레드로는 코어를 못 쓰므로, `BACKTEST_PHASE1_WORKERS`(기본 min(cpu−1, 8), ≤1=엔진 안 스레드 경로)가 2 이상이고 종목 수가 `BACKTEST_PHASE1_POOL_MIN_SYMBOLS`(기본 8) 이상이면 상주 spawn 워커 풀에 종목을 결정적 샤딩(crc32(종목) % n)으로 나눠 돌린다. 종목별 파이프라인은 `phase1.process_symbol`(피클 가능한 ctx 입력, 부수효과는 반환값) 하나가 정본이며 스레드 경로와 풀 경로의 결과는 동일해야 한다(회귀 테스트가 대조). 최적화 세션은 워커에 브로드캐스트되어 워커별 캐시가 같은 규칙으로 적중한다. AI 백테스트(Phase2 일괄 추론)는 스레드 경로를 유지한다. 워커는 부모 사망 시 스스로 종료하고, 워커 사망은 명확한 오류로 끝내며 다음 호출에서 재기동한다. 워크포워드 창 워커 안에서는 코어÷창 워커 크기로 중첩해 총 프로세스가 코어 수를 넘지 않게 한다.
- 리밸런싱 기간별 비교(FR-BT-064)는 풀이 있으면 시뮬레이션 직후 워커에 선제출해 결과 정리(Format)와 겹쳐 계산하고, 워커 실패 시 동기 경로로 재계산한다. 보유 상한이 없어 주기가 결과에 영향을 주지 못하는 전략(`rebalance_applies`=False, 시뮬레이터 `rebalance_mode`와 동일 조건)은 한 번만 시뮬레이션하고 6행을 복제한다 — 두 경로 모두 결과는 동기 6회 실행과 동일해야 한다(회귀 테스트가 대조).

**FR-BT-049d** [표시 일치 — 검증 안내·매매 사유·로그·축, 2026-09-17 PER·PBR 워크스루 실측] ① 백테스트 전 결정적 검증(`ai/strategy_validation_agent.py`)은 정기 리밸런싱(`rebalancing_period`≠none)을 청산 수단으로 센다 — 슬롯 정본(`engine/strategy_slots.py` EXIT 술어)과 같은 기준이며, 빠뜨리면 편출 매도가 있는 랭킹 전략 요약 카드 아래 "청산 조건을 입력해 주세요"가 떴다. ② 매매 사유의 연산자 낱말은 평가 경로와 같다: `>`=초과, `>=`=이상, `<`=미만, `<=`=이하(`engine/trade_reason.py`, 엔진 v16.11.1) — `PER > 0` 전략이 "PER 0 이상"으로 찍히던 결함. ③ 결과 화면 백테스트 로그의 칼마 비율·최종자산은 지표 카드와 같은 값·같은 원화 정수 표기를 쓴다(`BacktestDashboard.resolveCalmar`, `formatAccountMoney`) — 로그만 "Calmar: 0.00"·"22,349,475.411원"이었다. ④ 자산곡선 축·툴팁의 원화 축약은 음수 눈금에도 적용한다("-1000만", 생숫자 "-10000000" 금지). 몬테카를로 분포 차트는 원래 순서 기준선 라벨이 잘리지 않게 위 여백을 둔다.

**FR-BT-049b** 지표 기간 파라미터화(`engine/indicator_columns.py`): MACD(fastPeriod/slowPeriod/signalPeriod), 스토캐스틱(period), 볼린저밴드(period/stdDev)는 전략 DSL에 명시된 값으로 계산해야 한다. 기본값(12/26/9, KDJ 9, BOLL 20±2σ)이면 기존 stockstats 컬럼을 그대로 사용해 과거 백테스트 결과와의 동일성을 보존하고, 파라미터 지정 시 파라미터화 컬럼(`macd_f,s,g` / `kdjk_n` / `boll_ub_n[_kpX]`)을 계산한다. 워밍업 산정(`_max_indicator_period`)도 동일 파라미터를 반영해야 한다.

**FR-BT-050** 몬테카를로 시뮬레이션(프론트 `OptimizationPage.tsx`, in-browser 실행):
- 방식은 ① equity curve 일별 로그수익률의 **고정 블록** 부트스트랩 — 블록 1일(독립 재표본)/5·10·21일(자기상관 보존) —, ② **가변 블록(Stationary bootstrap, `blockMethod:"stationary"`)** — 평균 블록 길이(5·10·21일)만 맞춰 기하분포 가변 블록으로 고정 블록의 경계 효과를 완화 —, ③ 거래 재표본(trade bootstrap) 중 사용자가 선택하고 UI에 방식을 명시한다. seed 고정으로 재현 가능해야 한다.
- **블록 길이 제안**: 전략의 평균 보유기간(`avgHoldingDays`)을 근거로 기본 블록 길이를 제안해(1/5/10/21일) 한 번에 적용할 수 있는 힌트를 제공한다(검증 방식 선택을 돕는 통계적 제안일 뿐 투자 판단이 아니며, 사용자가 자유롭게 다른 방식을 선택할 수 있다). 화면 어휘는 "보유기간 기준 블록 길이"로 쓰고 '추천'을 쓰지 않는다.
- 거래 재표본은 체결 기록(tradesList, 폴백 signals)에서 종목별 **수량 기반 FIFO** 매칭으로 완결 거래를 복원하고, 각 거래를 **자본 대비 기여도(손익금 ÷ 진입시점 계좌자산 = return-on-equity)**로 환산해 복원추출한다. 이로써 실제 포지션 사이징(전액이 아닌 일부만 투입, 동시 다종목 보유)이 반영되어 거래 재표본 복리가 다종목 전략의 CAGR·MDD를 과장하지 않는다. **손익금은 엔진이 매도 체결에 실어 주는 순손익(`signals[].pnl`, 수수료·거래세 차감)을 사용해야 한다** — 체결가 차액(수량×(매도가−매수가))은 비용 전 총손익이라 왕복 0.45%가 빠져 분포가 낙관적으로 치우친다(2026-08-19 감사). `pnl`이 없는 구버전 결과만 차액으로 강등하고 그 사실을 결과(`tradeCosts:"gross"`)·실행 설정 표시·쉬운 설명에 고지한다. 체결 수량·일별 자산곡선이 없어 사이징을 복원할 수 없으면 가격수익률로 강등하고 그 사실을 결과에 표시(`tradeSizing`)한다. 완결 거래 20건 미만이면 명확한 에러를 반환하고, MDD가 거래 단위 경로 기준(거래 도중 낙폭 미반영)임을 UI에 명시한다. 거래 모드의 Sharpe는 거래당 평균÷표준편차×√(연간 거래 수)로 정의가 달라 표에 "Sharpe(거래 단위)"로 구분 표기하고 백테스트 샤프와 직접 비교할 수 없음을 각주로 둔다.
- **연환산 기준은 백테스트 엔진과 동일**해야 한다: 연수는 `dates`의 달력 경과일 ÷ 365.25(없으면 봉수 ÷ KRX 246일), Sharpe 연환산 계수는 √246. 봉수÷252·√252를 쓰면 연수를 ~2% 적게 잡아 원래 순서 재구성 CAGR이 결과 탭 CAGR과 어긋난다(2026-08-19 수정, `backtestYears`, 리서치용 `engine/monte_carlo.py`도 동일).
- 결과는 CAGR·Sharpe·MDD 각각에 대해 최소/5%/25%/중앙값/75%/95%/최대/표준편차(표 형태)와 CAGR·MDD 분포 히스토그램, 양수 CAGR 확률, MDD 30% 초과 확률을 제공한다. 단일 표본 최소/최대는 반복 횟수에 따라 불안정하므로 대표 지표(스탯 카드)로는 사용하지 않는다.
- **원래 순서 위치 표시(MDD 전용)**: 재표본하지 않은 원래 순서의 CAGR·MDD를 시뮬레이션과 동일한 기준으로 재구성하되(`observed`), 분포 내 위치(백분위)는 **MDD에만** 제공한다 — 스탯 카드("원래 순서 MDD", 시나리오 N%가 이보다 깊음)·MDD 히스토그램 기준선·쉬운 설명 문장. CAGR은 성장배수의 곱이라 순서와 무관하고 부트스트랩 분포가 관측 평균을 중심으로 만들어져 관측 CAGR이 구조적으로 늘 분포 한가운데(실측 8시드×3방식 전부 47~59 백분위)에 오므로, CAGR 위치 카드·"상단 치우침=순서 의존" 해석은 두지 않는다(2026-08-19 감사로 폐지, 되살리지 말 것). CAGR 카드는 분포 중앙값+하위 5% 경계로 대체한다. 화면 라벨은 "실제"가 아니라 "원래 순서"로 쓴다(재구성 값이라 결과 탭의 백테스트 값과 정의가 다를 수 있음). 구버전 저장 결과(`observed` 없음)는 표본 최대 MDD 카드로 폴백한다.
- 일별 독립 재표본(blockSize 1)은 자기상관·변동성 군집·추세가 깨진다는 한계를 UI 설명과 쉬운 설명 문장에 명시한다.
- **회복(낙폭 지속) 지표**: 각 시나리오의 최장 언더워터(고점 아래에 머문 최장 스텝 수 — returns 모드는 거래일, trades 모드는 거래 건) 분포(`underwater`)를 산출해 쉬운 설명 문장으로 중앙값·상위 5%를 제공한다. 최장 구간이 기간 끝까지 이어져 고점을 회복하지 못한 시나리오 비율(`underwaterUnrecoveredRatio`)을 함께 집계해, 미회복이 있으면 그 비율과 함께 위 수치가 회복 소요가 아니라 하한(검열된 값)임을 쉬운 설명에 고지하고, 비율이 0일 때만 "모든 시나리오가 기간 안에 회복"으로 서술한다. 비율이 없는 구버전 저장 결과는 회복 여부를 단정하지 않는 중립 문구만 쓴다(2026-08-21 — "회복하기까지 걸린 기간"으로 단정하던 문구가 미회복 구간을 회복 완료처럼 읽히게 했던 문제 수정).
- **표본 충분성**(`sufficiency`): 근사 독립 표본 수(returns=포인트수÷블록길이, trades=완결 거래 수)가 임계치(30) 미만이면 결과 화면 경고 배너와 쉬운 설명 문장으로 "분포는 참고용"임을 고지한다.
- **실행 설정 표시**: 결과 화면에 이 결과를 만든 실행 파라미터(방식 라벨·반복 횟수·seed, 거래 재표본이면 완결 거래 수·사이징 방식·거래 비용 반영 여부)를 노출한다(`data-testid="monte-carlo-run-params"`). 값은 실행 결과 객체(`nIterations`/`blockMethod`/`blockSize`/`mode`/`seed`/`tradeCount`/`tradeSizing`/`tradeCosts`)에서 직접 읽어, 실행 후 설정을 바꿔도 결과와 어긋나지 않게 한다(`seed`는 결과·저장 스냅샷에 포함해 불러오기 시 복원). 이 블록은 2026-07-21 화면 간소화 때 삭제됐다가 사이징·비용 강등 고지가 사라진 문제로 2026-08-19 복원됐다 — 다시 제거하지 않는다.
- **검증 대상 전략 표시**: 몬테카를로 화면 상단에 이 검증이 대상으로 삼는 전략의 구성(유니버스·진입 조건·청산 조건·포지션/리밸런싱/리스크)을 사람이 읽는 라벨(PBR≤1·MACD 골든크로스 등)로 노출한다. 라벨은 `BacktestDashboard`가 이미 만든 `strategySummary`(entryBlocks/exitBlocks/…)를 그대로 전달받아 렌더하며 별도 파싱을 하지 않는다. 구조화 요약이 없으면 `promptText`로 폴백한다. (표시는 현재 대시보드의 백테스트 전략 기준이며, 다른 전략의 저장 결과를 불러온 경우 요약은 현재 전략을 가리킨다.)
- 실행은 청크 단위로 진행률을 표시하고 취소 가능해야 하며, 유효 equity 포인트가 최소 요구치(max(30, blockSize×3)) 미만이면 명확한 에러를 반환한다.
- 모든 문구는 서술적 통계 표현만 사용하고 투자 추천·미래 성과 보장 표현을 금지한다(규제 안전 원칙).

**FR-BT-051b** 검증 결과 쉬운 설명 섹션(`ResultPlainSummary.tsx`): 전략 최적화(워크포워드·몬테카를로) 결과 화면에는 결과 수치를 일상 언어 문장으로 풀어 주는 "쉽게 이해하기" 섹션을 항상 표시해야 한다. 문장은 결과 데이터에서 결정적으로 생성하며(LLM 미사용), 검증 방법 요약·검증 구간/시나리오 성과·승패 구간 수(또는 수익/손실 시나리오 비중)·WFE(계산 불가/음수 포함) 또는 낙폭 분포·과거 데이터 기반 면책 문구를 포함한다. 모든 문장은 과거 서술형 통계 표현만 사용하고 추천·전망 표현을 금지한다(규제 안전 원칙). [2026-09-17] 몬테카를로 첫 문장은 **실제로 고른 재표본 방식**을 말한다 — 일별 독립이면 "일별 수익률을 무작위로 다시 섞어", N일 고정 블록이면 "N거래일씩 묶어 무작위로 다시 이어 붙여", 가변 블록이면 "평균 N거래일 길이(가변)의 구간으로 묶어"(21일 블록 실행에 일별 문구가 나가던 결함). 낙폭 지속 문장은 단위별 템플릿으로 조사를 맞추고("거래일이었습니다"/"거래였습니다") 천 단위 구분을 쓴다.

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

**FR-BT-052j** [DART 일일 허용량 소진의 미완성 캐시 처리, 2026-08-17] 재무 조회의 DART 단계가 일일 허용량 초과(status 020)로 끝나면 시스템은 그 결과를 **'데이터 없음'과 구분**해야 하며, KIS 값만 담긴 레코드를 완성본(90일 유효) 캐시로 저장해서는 안 된다. 허용량 소진은 예외(`DartQuotaExhausted`)로 호출자에 전달하고, 호출자는 KIS 값은 보존하되 캐시에 미완성 표시(`dart_pending`)를 남겨야 한다. 미완성 캐시는 당일에는 그대로 읽어(허용량이 바닥난 DART를 다시 두드리지 않음) 다음 날부터 만료로 취급해 정규 조회 경로가 KIS+DART를 다시 받아 완성하도록 해야 한다. 근거(2026-08-04 사고): 전수 백필이 04시경 허용량에 걸린 뒤 약 420개 활성 종목이 DART 유래 항목(지배주주순이익·당기순이익 정본·영업/투자/재무현금흐름·CAPEX·FCF·자본총계) 없이 완성본으로 캐시돼 이후 모든 백필·재병합이 건너뛰었고, 파케이엔 해당 컬럼이 통째로 비었다. 근본 수정 이전에 만들어진 미완성 캐시(DART 응답이 한 번도 병합되지 않은 캐시)는 `scripts/repair_dart_pending_fundamentals.py`가 DART만 재조회해 완성한다(KIS 재조회 없음, 허용량 소진 시 종료코드 3으로 중단·재실행 시 남은 종목만 대상). DART 기업코드 매핑(`data/dart_corpcode.json`)은 신규 상장사가 누락되면 그 종목의 DART 단계가 조용히 생략되므로 같은 스크립트의 `--refresh-corpcode`로 **추가만** 갱신한다(기존 매핑 불변).

**FR-BT-052k** [KIS 0 자리표시자 연도 배제 + Naver 보충, 2026-08-17 · 엔진 v14.0] KIS 재무 엔드포인트가 재무를 싣지 않은 회사·연도에 돌려주는 **0 자리표시자 행**(EPS·BPS·SPS가 동시에 0)을 시스템은 값으로 받아서는 안 되며, 레코드째 배제해 '데이터 없음'으로 다뤄야 한다. 근거(2026-08-17 실측): 삼진제약(005500)은 재무비율·손익계산서·재무상태표 22개 연도 전부 `eps 0.00·sps 0·bps 0.00·부채비율 0.0000`(당좌비율만 46.06)이고, 연결재무제표를 만들지 않는 회사와 KIS 이력 시작 전 연도(2004~2009 다수)가 이렇다. 0을 진짜 값으로 forward-fill한 결과 활성 124종목(동국제강·케이카·크라운제과·삼진제약·현대약품 …)이 최근 1년 내내 PER·PBR·PSR·ROE null로 가치 필터에서 통째로 사라졌고, 부채비율 0이 '부채비율 ≤ N' 필터를 **거짓 통과**했다(활성 636종목이 어느 연도엔가 해당). 판정은 EPS·BPS·SPS 셋의 동시 0으로 한정한다 — 실존 기업이 순자산 0·매출 0·이익 0을 동시에 결산할 수는 없고, 매출 0인 스팩(BPS>0)이나 자본잠식(BPS<0)은 걸리지 않는다. 자리표시자가 있던 종목만 Naver 주요재무정보(최근 3~4개년 EPS/BPS/ROE/부채비율)로 보충하되 같은 연도는 KIS 값이 이기며, 자리표시자 없이 온전한 KIS 결과엔 Naver를 호출하지 않는다. 배제된 연도는 필터가 fail-closed로 제외하고, 직전 정상 연도가 있으면 기존 forward-fill 규칙(다음 결산까지)대로 이어진다 — 이는 fill 모델의 특성이며 이 항목이 바꾸지 않는다. **PSR은 폴백으로 메운다(엔진 v14.1)**: Naver 보충에 SPS·매출이 없으므로, 같은 DART 손익계산서 응답의 매출액(`ifrs-full_Revenue`, 추가 호출 0)을 `revenue`(억원)로 저장하고 `psr`이 비어 있는 날만 일별 실측 `market_cap ÷ revenue`로 채운다(`fill_psr_from_market_cap` — enrich·`rebuild_fundamental_columns` 단일 정의, PCR과 같은 구조라 주식수 근사 왜곡 없음). **폴백 전용**이다 — KIS SPS가 있는 날의 `psr`(종가÷SPS)은 불변이라 기존 PSR 결과는 바뀌지 않고 공백만 메우며, `revenue`는 필터·배지에 노출하지 않는다. DART가 없는 구간(2015년 이전·매출 계정 없는 제출본)은 여전히 공백이다. 기존 캐시·parquet은 `scripts/repair_kis_placeholder_fundamentals.py`가 엔진과 같은 경로(`fetch_fundamentals(use_cache=False)`)로 재조회하고, parquet은 **자리표시자 서명 행(eps=bps=sps=0)의 연간 재무 컬럼·PER/PBR/PSR을 먼저 비운 뒤** 재구축한다(`rebuild_fundamental_columns`는 캐시가 모르는 날의 기존 값을 보존하므로 비우지 않으면 옛 0이 남는다; 서명은 parquet 자체에서 나오므로 옛 캐시 없이 프로덕션에서도 같은 결과 — `--rebuild-only --since`). 스크립트는 KIS 토큰을 **먼저 확보**한 뒤 시작한다(발급 1분/1회 제한으로 토큰이 없으면 KIS 단계가 조용히 None이 되어 Naver 3개년만으로 완성본 캐시가 덮이는 사고가 실측됐다). DART 허용량 소진(dart_pending)이면 옛 캐시를 복원하고 종료코드 3으로 멈춘다.

**FR-BT-052l** [연간 재무 forward-fill 상한 + 재무 조회 미도달 구분 + 미러 stall 재시도, 2026-08-18 · 엔진 v15.0] (1) **forward-fill 상한 15개월**: 연간 재무 레코드 하나는 공개일(available_from, 없으면 결산일+90일)부터 **최대 15개월**(결산 주기 12개월 + 사업보고서 제출 지연 약 3개월)만 일별 시리즈에 이어지고, 그 안에 다음 레코드가 오면 거기서 끊기며 안 오면 키별로 '데이터 없음'이 되어 필터가 fail-closed로 제외한다. 근거(2026-08-17 실측): 무제한 forward-fill 탓에 레코드가 빈 연도(KIS 자리표시자 제거·미제출·상폐 후·DART 결손)에 직전 값이 그대로 남아 부국증권은 2013년 값이 2024년까지 10년간 이어졌고 활성 208종목·20.9만 종목-일이 15개월을 넘긴 stale 값이었다. 매년 정상 보고하는 회사는 다음 레코드가 15개월 안에 와서 결과가 바뀌지 않는다. 상수 `FUNDAMENTAL_FILL_MAX_MONTHS`. (2) **재구축 의미 정리**: `rebuild_fundamental_columns`는 캐시가 지배하는 구간(가장 이른 공개일 이후 — `cache_coverage_start`)에서 캐시로 만든 시리즈가 **NaN까지 포함해 통째로** 이긴다. 종전 '값이 있는 날만 덮고 나머지 보존'은 자리표시자를 걷어내 빈 연도와 상한을 넘긴 stale 날에 옛 값을 되살렸다. 캐시가 지배하기 전 날(초기 pykrx 이력)만 기존 값을 보존한다. 기존 parquet은 전 활성 종목 재구축으로 회수한다(로컬·프로덕션, `repair_kis_placeholder_fundamentals.py --rebuild-only`). (3) **KIS 미도달 ≠ KIS에 없음**: `_fetch_fundamentals_from_kis`는 토큰 발급 실패(1분당 1회 제한 등)에만 `None`, KIS에 닿았지만 재무가 없으면 빈 리스트를 돌려주고, `fetch_fundamentals`는 `None`이면 Naver·DART 값을 `kis_pending` 표시로 캐시해(dart_pending과 같은 규칙: 당일은 읽고 다음 날 만료) 다시 받게 하며 부정 캐시(7일)를 남기지 않는다. 근거: 2026-08-17 수리 스크립트 첫 실행에서 토큰 403 뒤 2분간 30여 종목이 KIS 이력 없이 Naver 3개년만으로 90일 완성본 캐시가 됐다. (4) **미러 stall 재시도**: `scripts/mirror_data.py`는 rsync 무전송 중단을 300초로 두고, 스톨·네트워크 계열 종료코드(10·12·30·35)면 15초 후 최대 5회 이어서 재시도한다(옮긴 파일은 임시파일→rename으로 원자적이라 재시도가 남은 파일만 잇는다; `--partial`은 깨진 parquet을 남기므로 쓰지 않는다). 근거: 2026-08-17 큰 델타(수천 파일·1GB+) pull이 정상 전송 중에도 120초 stall로 4회 끊겼고 로컬 스케줄러 21:15 pull도 같은 이유로 실패했다.

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


**FR-BT-063** [복합 순위 합산(멀티팩터 랭킹), 2026-08-17, 엔진 v13.4] 시스템은 여러 지표의 횡단면 순위를 합산해 종목을 선정하는 랭킹("ROE 내림차순·유동비율 내림차순·PER 오름차순·PCR 오름차순으로 각 순위를 구해 합산, 합산값이 가장 낮은 상위 10% 편입")을 지원해야 한다. **표현**: `ranking_metric='composite'` + `ranking_components=[{metric, direction, lookback_days?}, ...]`(2개 이상; 구성 지표는 단일 랭킹이 가능한 지표 전부 — 재무 컬럼·기간 수익률·변동성). 해석 스펙에서는 `strategy.ranking` 항목 2개 이상 = 합산이며(합산 지표 이름을 지어내지 않는다), 방향 미지정 항목은 지표의 자연 방향(온톨로지 polarity)으로 컴파일러가 채운다. **계산**: 구성 지표마다 **전 지표가 정의된 종목 풀 안에서** 백분위 순위(방향 기준 좋은 쪽이 높게)를 매겨 **동일 가중 평균**한다 — 이 값의 내림차순은 순위 합산 오름차순과 같은 정렬이다(지표별 유효 종목 수 차이로 인한 가중 왜곡 방지). 어느 한 지표라도 없는 종목은 후보에서 배제한다(중립값 위장 금지). 구성 지표 컬럼이 유니버스 전체에 없으면 조용한 0거래가 아니라 경고. next_open은 1일 shift(look-ahead 방지). 가격 산출 구성 지표의 산정 기간은 구성 지표 자체 값 → 전략 공통 `ranking_lookback_days`(되묻기 칩 답이 결속되는 자리) → 60 순이며, 되묻기는 그 지표가 랭킹 항목 몇 번째에 있든 낸다(`strategy.ranking[i].lookback_days`). 매수 사유·분위 그룹 라벨은 "복합 순위(ROE 높은·PER 낮은) 상위 N%"처럼 구성 지표와 방향을 병기한다. 가중치는 되묻지 않는다(동일 가중이 정의). **미지원 랭킹 지표 처리(같은 날 사고 회귀)**: 검증기는 미지원 랭킹 항목을 오류와 함께 **제거**하고(진입 조건의 kept 계약과 동일), 미지원 보고에는 LLM이 지어낸 내부 식별자 대신 사용자 표현(`source_text`) 또는 평이한 일반 표기를 담는다(내부명 노출 금지 — 'composite_score' 노출 사고). 컴파일러는 등록되지 않은 랭킹 지표를 `'return'`으로 바꿔치는 폴백을 갖지 않는다(사용자가 말하지 않은 수익률 랭킹이 생기던 사고). 디컴파일러는 composite→RankingSpec N개로 왕복하며(가격 지표 `ranking.*` 네임스페이스 정정 포함), canonical DSL은 구성 지표를 정렬해 담고 단일 랭킹 전략에선 키를 내지 않아 기존 `strategy_id` 불변. 프론트 요약 라벨은 "복합 순위 상위 (ROE 높은 순 + PER 낮은 순 순위 합산)".

**구현 파일:**
- `backend/backtest_engine.py` — `_composite_ranking_components`·`_composite_ranking_label`·`_composite_rank_panel`·`_ranking_selection_pool`, 재무 랭킹 컬럼 수집 다중화(`all_fund_rank_values[col][sym]`)
- `backend/engine/nl_parser.py`(RankingComponent·ParsedStrategy.ranking_components·`_normalize_composite_ranking`·`_ranking_metrics_expressed`), `backend/schemas.py`, `backend/engine/strategy_converter.py`, `backend/engine/version.py`(v13.4)
- `backend/strategy_conversation/` — `interpreter/prompts.py`(복합 순위 규칙+예시 4-c), `validation/capability_validator.py`(미지원 랭킹 제거·비노출), `validation/completeness_validator.py`(자리 무관 산정 기간 되묻기), `compiler/strategy_compiler.py`·`strategy_decompiler.py`, `primary.py`(`_RANKING_LOOKBACK_FIELD_RE`), `conversation/change_log.py`
- `lib/strategy-summary.ts`(getRankingLabel composite), `types/strategy.ts`
- `backend/tests/test_composite_ranking_engine.py`(신규), `backend/tests/test_composite_ranking_lane.py`(신규), `lib/strategy-summary.composite-ranking.test.ts`(신규)

**FR-BT-064** [리밸런싱 기간별 결과 비교, 2026-08-18, 엔진 v16.3.1] 백테스트 결과 페이지의 수익률 추이 영역에 '월별 수익률'·'롤링 수익률' 오른쪽 세 번째 탭 **'리밸런싱 기간별 결과'**를 제공해야 한다. 엔진은 **백테스트마다** 메인 시뮬레이션 뒤 같은 입력(가격·신호·랭킹·거래 가능 마스크)으로 `rebalancing_period`만 매일(daily)·매주(weekly)·매월(monthly)·분기(quarterly)·반기(semiannual)·연간(yearly)으로 바꿔 시뮬레이션을 6번 반복하고(분위 그룹 비교 FR-BT-060과 같은 구조 — 1단계 데이터 준비는 재실행하지 않는다), 주기별 CAGR·MDD·샤프·손익비(손실 0건=∞ 유지)·거래 수·회전율(결과 화면과 같은 산식)을 `BacktestResponse.rebalanceComparison`으로 동봉한다. 탭은 별도 실행·버튼 없이 이 표를 바로 보여준다(2026-08-18 사용자 지시 — 처음 도입한 '별도 SSE 실행 + LLM 서술' 방식은 같은 날 폐기). 표 위에는 **주기별 막대 그래프**(TradingView lightweight-charts 히스토그램 — 자산곡선·월별 수익률 차트와 같은 라이브러리)를 두어 지표 토글(CAGR 기본·MDD·샤프·손익비)로 전환하며, 월별 수익률 막대 차트와 같은 모습(색·격자·범례·툴팁)으로 그리고 현재 설정은 눈금 라벨 '(현재)'로 표시하며 실패 주기·손익비 ∞는 막대 없이 라벨·툴팁 자리만 둔다(같은 날 사용자 지시). **현재 설정 표시**: 전략의 현재 주기가 6주기 안이면 그 행에 '현재 설정' 배지, 밖이면(리밸런싱 없음·격월) 메인 결과 지표로 참고 행을 덧붙인다. **보유 상한 없는 전략**: 주기가 결과에 영향을 주지 않아도 막지 않고 계산하며 `positionCapAbsent`로 표시해 화면이 "6행이 같을 수 있음"을 안내한다. 한 주기의 실패는 그 행만 error로 남기고 나머지·메인 결과에 영향을 주지 않는다. 화면에는 "과거 데이터 시뮬레이션이며 미래 수익을 보장하지 않음" 안내를 표시하고 AI 서술·추천은 없다. 결과는 백테스트 기록·저장 전략 요약과 함께 저장된다(구버전 결과에는 없음 → 안내). 반기 주기는 이 기능을 위해 엔진에 신설했다(v16.1, 대화 해석기 어휘 미등록).

**FR-BT-067** [리밸런싱 방식 선택 — 종목 교체 / 비중 유지, 2026-08-26, 엔진 v16.4.0] 리밸런싱에는 **종목을 바꾸는 방식**만 있는 것이 아니라 **같은 종목의 비중을 원래 비율로 되돌리는 방식**도 있다(10종목 균등 투자에서 오른 종목은 오른 만큼 팔고 내린 종목은 내린 만큼 더 사서 균등을 유지). 시스템은 사용자가 리밸런싱을 켰을 때 둘 중 무엇인지 **묻고**, 답을 엔진까지 실어야 한다. **표현**: `ParsedStrategy.rebalance_method` = `reconstitute`(기본·종전 동작) | `weights_only`. **엔진 의미론**: ① `reconstitute` — 리밸런싱일마다 후보(매수 조건·랭킹)에서 목표 종목을 다시 골라 목표 밖 보유를 편출한다(청산 사유 '리밸런싱 제외'). ② `weights_only` — **편출 없음**. 보유 종목에 동일가중 목표비중을 다시 줘 초과분은 부분 매도(청산 사유 '리밸런싱 비중 조정'), 미달분은 추가 매수하고, 목표 종목 수에 미달하는 **빈 자리만** 그날 후보로 채운다. **트림 청산 사유**(`리밸런싱 비중 조정 (목표 비중 초과분 매도)`)는 방식과 무관하게 붙는다 — 순수 경로는 종목 교체에서도 리밸런싱일마다 비중을 리셋하므로 같은 부분 매도가 일어나며, 사유가 없으면 매도 조건을 하나도 말하지 않은 전략의 거래 내역에 '전략 매도 조건 충족'이 찍힌다(2026-08-26 정리, 라벨만 바뀌고 체결·지표는 불변). 매도 조건·손절·익절은 방식과 무관하게 그대로 작동하며, 그렇게 빈 자리도 기존 슬롯 채우기 규칙으로 채운다(2026-08-26 사용자 결정). 두 시뮬레이터 경로(순수 `from_orders` 목표비중·리스크 혼재 커스텀 루프)가 같은 계약을 지키며, 커스텀 루프는 종전에 비중 리셋 자체가 없었으므로 `weights_only`에서만 리밸런싱일에 보유 전체 목표비중을 다시 준다. **되묻기**: 진행 골격에 '리밸런싱 방식' 칸(`engine/strategy_slots.py`의 `REBALANCE_METHOD`)이 리밸런싱 바로 뒤에 서고, 칩은 "종목 교체 리밸런싱"·"비중 조정 리밸런싱 (균등 유지)" 두 개다(칩=값 결속 정본 표 `REBALANCE_METHOD_CHIP_VALUES` — 원문 정규식을 타지 않는다). 리밸런싱을 하지 않는 전략·단독 종목에서는 '해당 없음'이라 묻지 않는다. **시장과는 무관하다**(2026-08-27 미국 레인 합류) — 방식은 통화·세금처럼 시장이 정하는 값이 아니라 포트폴리오 운영 규칙이므로 미국 전략도 같은 질문·같은 두 칩을 받는다(초기 자본이 시장별 변형(달러 칩)을 갖는 것과 다른 축이다). /us 표시는 프론트 사전이 옮긴다 — 질문·칩의 영어 번역이 `lib/i18n/en.ts`에 없으면 한국어가 그대로 나가므로, 슬롯 픽스처의 한글 문구가 사전에 있는지 테스트가 강제한다(`tests/slot-prompts-i18n.test.ts` — 기존 i18n 커버리지는 소스의 t() 호출만 스캔해 이 자리를 못 본다). 리밸런싱 주기와 라벨을 공유하지 않는 이유는 planner가 보는 `filled_slots`에서 "리밸런싱이 안 찼다"로만 보여 이미 답한 **주기를 다시 묻기** 때문이다. **하위 호환**: 방식을 말하지 않은 기존 전략·저장 결과는 `reconstitute`라 결과값이 바뀌지 않고, canonical DSL도 기본값을 키에서 빼 `strategy_id` 해시가 불변이다.

**구현 파일:**
- `backend/engine/rebalance_comparison.py`(신규 — 6주기 재시뮬레이션·행 요약·회전율), `backend/backtest_engine.py`(분위 그룹 블록 뒤 호출), `backend/schemas.py`(`rebalanceComparison`), `backend/engine/rebalance.py`(semiannual)·`engine/live_signal_utils.py`
- `components/strategy/backtest/rebalanceComparison.ts`·`RebalanceComparisonSection.tsx`(신규), `components/strategy/backtest/BacktestDashboard.tsx`(탭), `app/analytics/new/backtestResultMapper.ts`·`lib/strategy/BacktestService.ts`·`lib/server/backtestCache.ts`(필드 전달·저장), `types/strategy.ts`
- `backend/tests/test_rebalance_comparison.py`·`test_rebalance_dates.py`, `components/__tests__/RebalanceComparisonSection.test.tsx`

**FR-BT-068** [편향 감사 수리 1차, 2026-09-02, 엔진 v16.5.0] 백테스트는 다음을 만족해야 한다. (a) 거래정지 상태로 데이터가 끝나는 종목(정지 꼬리 상폐)의 보유 포지션은 그 종목의 **마지막 실봉**에서 강제 정산한다 — 정지 마스크가 강제청산을 지워 백테스트 종료까지 동결가로 남겨선 안 된다. (b) 한국 가격제한(±30%) 전제의 코퍼레이트 액션 역보정은 **한국 종목에만** 적용한다 — 미국 종목의 실제 갭은 과거 시계열을 다시 스케일하지 않고 손익에 남긴다. (c) 증권거래세는 `sell_tax_rate` 미명시 시 **매도 봉 날짜의 시행일 기준 법정 세율**(농특세 포함, 0.30%~0.15%)을 적용하고, 명시(0 포함)하면 전 구간 고정한다. 결과 고지에 적용 세율(범위)을 밝힌다. (d) 리밸런싱 비중 리셋의 부분 매도(트림)에도 매도 비용(수수료+거래세)을 물린다. (e) KOSPI200·KOSDAQ150 유니버스의 시총 상위 N 판정은 일별 **실측 시가총액**을 정본으로 하고, 실측이 없는 셀만 현재 상장주식수 × 주가로 근사하며 근사 비율을 고지한다. (f) 거래 비용 옵션의 음수는 거절하고(Fail Fast), 수수료와 슬리피지가 모두 0이면 고지한다. (g) 생존편향 고지는 미국 유니버스뿐 아니라 미국 지정 종목·테마 경로, 그리고 한국 시장 유니버스의 상폐 이력 하한(마스터 `delistingFloor`) 이전 구간에도 붙인다. AI 신호는 학습 구간뿐 아니라 **검증 구간** 겹침도 고지한다. (h) 최적화 시행 횟수는 상한을 둔다(최적화 200, 워크포워드 창당 100). 최적화 결과 표시와 리포트는 인샘플임을 밝히고, 전체 기간으로 고른 설정값의 후반 30% 재실행을 아웃오브샘플 검증·신뢰도·실전 적용 판단으로 표현하지 않는다.

**FR-BT-069** [신호 후 N거래일 지연 체결, 2026-09-14, 엔진 v16.9.0] 시스템은 `next_open` 체결에서 신호 봉과 체결 봉의 간격을 N거래일로 지정할 수 있어야 한다(`risk.execution_delay_days` / `options.execution_delay_days`, 기본 1=다음 거래일 시가). ① **의미**: 지연 N이면 신호 봉의 N번째 거래일 **시가**에 체결한다 — 엔진이 진입·청산 신호, 랭킹·유효 마스크, 유동성 게이트, 시총(대형주) 마스크, AI 하락 랭킹 청산을 모두 N일 shift한다(종전 1일 shift의 일반화, 룩어헤드 없음). 달력 리밸런싱은 체결일이 주기 첫 거래일로 고정돼 있으므로 편입·편출 근거가 N일 전 정보가 된다(체결일은 그대로). ② **강제청산**: 상폐·데이터 종료 종목의 강제청산 신호는 phase1이 마지막 가용 봉의 N봉 앞에 두어 shift 뒤 마지막 봉에 실린다(종목 길이가 N+1 미만이면 신호를 만들지 않는다). ③ **리스크 청산은 지연하지 않는다**: 손절·익절·트레일링은 보호 주문이므로 종전대로 장중 감지 → 다음 거래일 시가 체결이다. ④ **검증(Fail Fast)**: 1 미만·정수 아님은 거절, `same_close`(current_close)에 1 초과 값은 조용히 무시하지 않고 거절한다. 값은 options → risk 순으로 읽어 프론트 배선 누락으로 조용히 사라지지 않게 한다. ⑤ **캐시**: 백테스트 캐시 키에 지연 값을 포함한다. ⑥ **범위**: 엔진·DSL·API·캐시까지이며, 대화 레인(인터프리터 스펙·되묻기)은 미착수(가상계좌는 FR-VM-075). ⑦ **표시**: 결과 화면 '프롬프트' 팝오버와 기록 요약에 '체결' 행(익일 시가 / 당일 종가 / 신호 후 N번째 거래일 시가)을 실행 요청(options → risk, 엔진과 같은 순서)에서 파생해 보인다(`lib/strategy-summary.ts::formatExecutionText`). 회귀: `backend/tests/test_execution_delay.py`, `app/api/strategy/backtest-cache.test.ts`.

**FR-BT-070** [전문가형 퀀트 전략 요소, 2026-09-19, 엔진 v16.14.0] 엔진은 다음을 opt-in으로 지원해야 하며, 새 필드를 쓰지 않는 전략의 결과는 변경 전과 비트 단위로 같아야 한다(게이트 픽스처 30개 HEAD 대조 해시 일치). ① **최근 제외 수익률**(`ranking_skip_days`, 구성 지표 `skip_days`) — 12-1 모멘텀 = t-252 → t-21 구간 수익률(`indicators.lookback_return_panel`), 제외 기간 ≥ 산정 기간이면 거절. ② **묶음 점수**(구성 지표 `group`) — 같은 묶음은 먼저 백분위를 평균해 한 점수로 만들고, 그 점수와 다른 묶음·단독 지표를 동일 가중 평균한다(품질 지표 수가 많다고 품질 가중이 커지지 않게). ③ **변동성 역비중**(`allocation_type='inverse_volatility'`, `allocation_lookback_days`) — 리밸런싱일 목표 비중 ∝ 1/σ(N일 연환산, 신호와 같은 지연), σ 미정의 종목은 후보에서 제외, 순수 리밸런싱·조건 루프 두 경로 모두. 정기 리밸런싱이 없으면 경고 후 동일 비중(완전 위험기여 균등(ERC)은 미지원 — 2026-09-19 사용자 결정). ④ **시장 국면 필터**(`market_regime` = 지수 KOSPI/KOSDAQ·이동평균 기간·약세 노출 %) — 지수 종가 < N일 SMA인 날 목표 노출을 줄이고, 국면이 바뀐 날 보유 비중을 기준 비중 × 새 노출로 다시 맞춘다(축소 매도 사유 `MARKET_REGIME_REDUCE`). 노출 0%는 전량 현금화 후 신규 편입 없음. 판정은 신호와 같은 지연(next_open이면 전일 판정, 창 첫날은 창 직전). 결과 경고로 약세 일수와 노출을 고지한다. 지수 파일이 없으면 경고 후 미적용. ⑤ **거래대금 평균 기간**(`trading_value` 필터 `period`, 종전 20일 고정 — 'N일 평균'을 말해도 20일로 계산되던 조용한 왜곡). ⑥ **재무 지표** `roic`(영업이익 × (1 − 유효세율) ÷ (자본총계 + 이자부부채 − 현금및현금성자산), 유효세율은 세전이익 > 0일 때 [0, 0.5]로 자름, 투하자본 ≤ 0이면 결측)·`fcf_margin`(FCF ÷ 매출액). 원재료는 같은 DART 응답에서 파싱하며(`fundamental_fetcher.parse_dart_roic_inputs` — 이자부부채는 차입금·사채, 리스 제외, 유동 합계 계정이 있으면 구성 계정과 이중 계상하지 않음), 과거 구간은 `scripts/backfill_roic_fcf_margin.py`로 채운다. ⑦ **데이터 적재 대기('준비 중') 채널**(2026-09-20 사용자 지시): 기능·해석·엔진 배선이 끝났고 과거 데이터만 없는 지표(`indicator_registry.DATA_PENDING_METRICS` — 현재 `fundamental.roic`·`fundamental.fcf_margin`)는 검증 파이프라인이 조건·랭킹에서 제거하고 `ValidationReport.preparing_features`로 보고하며, 사용자에게는 **미지원과 다른 문구**로 알린다("…은(는) 아직 준비 중인 기능이라 이번 전략에는 반영하지 못했어요. 데이터 준비가 끝나면 사용하실 수 있어요."). 되묻기 칩에서도 제외한다. 그대로 두면 엔진이 값 없는 컬럼에 fail-closed로 걸려 **거래 0건 백테스트**가 나가고 그 사실은 결과 경고 한 줄로만 남는다(2026-09-20 실측). 적재가 끝나면 그 집합에서 지우는 것만으로 조건·랭킹·칩이 함께 살아난다(회귀: `test_backfilled_data_turns_the_metrics_on`·`test_backfilled_metrics_are_offered_as_chips_again`). **2026-09-21 집합을 비웠다** — ROIC·FCF 마진 백필(3,001종목)과 운영 반영이 끝나 두 지표가 정상 지표가 됐다. 채널 자체는 `data_pending` 픽스처로 회귀를 유지한다(다음 지표가 이 자리를 쓴다). 계획이 없는 개념(실적 추정치 등)은 이 채널이 아니라 종전대로 UNSUPPORTED다 — 지키지 못할 약속을 하지 않는다. 회귀: `backend/tests/test_engine_v16_14_portfolio_features.py`, `test_quant_portfolio_features_lane.py`, 결과 동일성 게이트 픽스처 `quant_quality_momentum_regime`·`momentum_12_1_regime_cash`.

**FR-BT-071** [재무 지표 — FCF 수익률·연속 배당 연수, 2026-09-20, 엔진 v16.15.0] 엔진은 조건 필터와 랭킹 구성 지표로 다음 두 지표를 지원해야 하며, 쓰지 않는 전략의 결과는 불변이다. ① `fcf_yield`(FCF 수익률, %) = 잉여현금흐름(영업현금흐름−CAPEX, 최근 연간 결산, raw 원) ÷ (일별 시가총액 억원 × 1e8) × 100 — 정의 자리는 `fundamental_fetcher.recompute_fcf_yield` 하나(PCR과 같은 계약: enrich·시총 재구축이 공유), 시가총액 비양수·결측이면 null, 음의 FCF는 음의 수익률로 둔다. ② `dividend_streak_years`(연속 배당 연수, 년) = 직전 달력 연도부터 거슬러 올라가며 현금배당(ex-date별 주당배당의 연간 합 > 0)이 끊기지 않고 이어진 연도 수 — 진행 중인 올해는 세지 않고(연말 결산 배당의 ex-date가 12월 말이라 해가 지나야 확정, 시점 정합), 데이터 시작 전 연도는 끊긴 것으로 본다(보수적 하한). 분기 배당은 연도 하나로만 센다. ③ 두 컬럼이 parquet에 없어도(백필 전) `data_resolver`가 기존 컬럼(fcf·market_cap·dividends·date)에서 런타임 계산해야 한다 — 재료가 있는 지표를 '준비 중'으로 미루지 않는다. ④ 해석 레인: `unsupported.fcf_yield`는 `fundamental.fcf_yield`로 승격(별칭 'FCF Yield'·'잉여현금흐름수익률'·맨 'fcf'), `fundamental.dividend_streak_years`(별칭 '연속 배당', '연속 배당 연수'; 'N년 연속 배당' = `>= N`)를 레지스트리·온톨로지(밸류에이션/배당, 높을수록 선호)에 등재해 프롬프트 어휘에 실린다. 레거시 규칙 파서·조건 빌더에는 원문 정규식을 추가하지 않는다(대원칙 1) — 공유 `fundamental-factors.json`의 키에 원문 패턴이 없으면 건너뛴다. 표시: 요약 카드 라벨 'FCF 수익률'·'연속 배당 연수', 영어 'FCF yield'·'Consecutive dividend years', 되묻기 칩 'FCF 수익률 5% 이상/이하'·'연속 배당 연수 3년 이상/이하'.

**FR-BT-072** [시장 국면 필터 — 변동성 급등 판정, 2026-09-20, 엔진 v16.16.0] 시장 국면 필터(`market_regime`)는 약세 판정 종류 `triggers`(`below_ma`·`volatility_spike`, 없으면 `below_ma`)를 지원해야 한다. `volatility_spike`는 지수 일간 수익률의 N일 표준편차(`volatility_period`, 없으면 20거래일)가 그 값의 직전 252거래일 평균의 `volatility_multiple`배(1 초과 10 이하) **이상**인 날이다. 두 판정이 함께 있으면 OR(하나만 충족해도 목표 노출을 `exposure_pct`%로 축소)이고 변동성 단독 사용도 가능하다. AND 결합은 지원하지 않는다. 기준선이 아직 정의되지 않은 초기 구간은 전액 투자다. 판정 지연·노출 재조정 규칙은 FR-BT-070 ④와 같다. 매매 사유·결과 경고는 판정 종류별 템플릿(이동평균/변동성/둘 중 하나)을 쓰며 변동성 산정 기간을 표기한다. `triggers`가 없는 기존 요청의 결과·전략 해시는 불변이다(`MarketRegime.to_request`).

**FR-BT-073** [잔차 반전 시그널 랭킹, 2026-09-20, 엔진 v16.17.0] 엔진은 랭킹 지표 `residual_reversal`을 opt-in으로 지원해야 하며, 쓰지 않는 전략의 결과·전략 해시는 불변이다. ① **원점수**(종목별, 유니버스 무관): 종목 일간 수익률을 [절편, 자기 상장 시장 지수 일간 수익률, 소속 섹터 평균 일간 수익률]에 직전 L거래일 회귀하고, 그 잔차 중 최근 K거래일 합을 **회귀 구간(L일) 잔차 표준편차**(자유도 L−3)로 나눈다. 섹터 평균은 **전체 상장 종목** 동일가중, **자기 제외**다(사용자 결정 2026-09-20). ② **시그널**: 전략 유니버스 횡단면(그날 가격이 있는 종목)에서 상하위 1% 윈저라이즈 → z-score → 부호 반전. 순위·지연(next_open이면 전일 시그널)·후보 풀·매수 사유 계약은 다른 가격 산출 랭킹과 같다. ③ **개방 파라미터는 이산값만**: 회귀 룩백 `ranking_lookback_days` ∈ {60, 120, 250}, 잔차 누적 기간 `ranking_accumulation_days` ∈ {3, 5, 10, 20}, 기본 (60, 5). 윈저라이즈 비율·정규화·부호 반전·설명변수는 고정이며 노출하지 않는다. 허용 밖 값과 '회귀 룩백 < 누적 기간'은 엔진이 거절한다(`residual_factor.validate_params`). ④ **지표 전용 가격**: 백테스트 옵션(배당 반영·기간 절단)과 무관하게 파일 전체 이력에 수정주가 + 배당 토탈리턴 + 기업행위 정제를 적용한 종가를 쓴다 — 옵션마다 시그널이 달라지면 사전계산을 공유할 수 없다. ⑤ **fail-closed**: 시장·섹터를 모르는 종목(미국·ETF·마스터 밖), 회귀 구간에 결측이 하나라도 있는 날, 시장·섹터 수익률이 공선인 날, 섹터에 다른 종목이 없는 날은 NaN → 후보 배제. 지수 시계열이 없거나 정의되는 종목이 없으면 결과 경고(`RANK_METRIC_DATA_MISSING`)로 알린다. ⑥ **사전계산 캐시**(`data/factor_cache`): 기본 조합 원점수와 모든 조합의 공통 재료(전 종목 수익률·섹터 합/개수)를 디스크에 두되, 데이터 지문(가격 파일명·크기·mtime + 지수 파일 + 섹터 소속 + 계산식 버전)이 현재와 같을 때만 읽는다. 다르면 같은 계산 함수로 그 자리에서 계산한다. 원점수는 종목(열) 단위 독립 누적합이고 항상 같은 달력(코스피 지수 거래일 전체)의 첫 행에서 시작하므로 **사전계산과 온디맨드의 값은 비트 단위로 같아야 한다**. 구축은 `backend/scripts/build_residual_factor_cache.py`(야간 `sync_data.py` 7단계). ⑦ **정본 DSL**: 두 파라미터를 정본 DSL에 싣는다 — 컴파일러가 말하지 않은 값까지 기본값으로 확정해 싣으므로 조합마다 `strategy_id`가 다르고, 말하지 않은 전략과 (60, 5)를 말한 전략은 같은 id다. ⑧ 복합 순위 합산의 구성 지표로는 지원하지 않는다(단독 랭킹 전용). 한계: 섹터 소속은 현재 시점 분류다(과거 소속 이력 없음). 공매도(시그널 하위 매도)·달러 중립·섹터 순노출 제한·변동성 타깃 레버리지·누적 손실 디레버리징은 미지원이다. 회귀: `backend/tests/test_residual_reversal.py`, 결과 동일성 게이트 픽스처 `residual_reversal_default_daily`·`residual_reversal_120_10_weekly`.

**FR-BT-074** [종목당 비중 상한, 2026-09-20, 엔진 v16.18.0] 엔진은 `risk.max_position_weight_pct`(%, 0 초과 100 미만일 때만 유효)를 opt-in으로 지원해야 하며, 값이 없거나 걸리지 않는 전략의 결과·전략 해시는 비트 단위로 불변이다. ① 상한은 **편입·리밸런싱 시점의 종목별 목표 비중**에 건다(min) — 순수 리밸런싱 경로의 목표 비중 행(동일가중·변동성 역비중, 시장 국면 노출을 곱하기 전 기준 비중), 조건 루프 경로의 진입 비중·비중 유지 리밸런싱의 비중 리셋(`simulator._weight_cap`·`_entry_base_size`). 역변동성에서는 **최종 비중에만** 건다(기준 비중을 먼저 자르면 상한에 걸리지 않은 종목까지 줄어든다). ② 잘린 몫은 다른 종목에 **재배분하지 않고 현금**으로 남는다(사용자 확인 대기 중인 구현 결정 — 동일가중은 재배분할 곳이 없다). ③ 상한 × 최대 종목 수 < 100%면 결과 경고(`POSITION_WEIGHT_CAP_LEAVES_CASH`)로 투자 가능한 최대 비중을 알린다. ④ 상시 감시가 아니다 — 보유 중 주가 상승으로 상한을 넘은 비중은 다음 리밸런싱의 비중 리셋이 되돌린다. ⑤ 컨버터는 `position_size_pct`(1회 매수 비중 — 가상계좌 자동매매가 읽는다)도 상한을 넘지 않게 낸다. 회귀: `backend/tests/test_position_weight_cap.py`, 결과 동일성 게이트 픽스처 `weight_cap_momentum_monthly`·`weight_cap_signal_loop_inverse_vol`.

**FR-BT-075** [실적 서프라이즈 시그널·섹터 비중 상한·유니버스 사전 필터, 2026-09-20, 엔진 v16.19.0] 엔진은 다음 셋을 opt-in으로 지원해야 하며, 값이 없는 전략의 결과·전략 해시는 비트 단위로 불변이다. ① **랭킹 지표 `pead`**(`engine/earnings_factor.py`): 종목별로 가장 최근 발표된 분기의 SUE(그 분기 EPS − 전년 동기 EPS를, 그 값을 끝으로 하는 직전 8개 분기 같은 차이의 표본표준편차로 나눈 값)와 발표일 초과수익률(발표일 직전 거래일 종가 → 발표 2거래일 후 종가 수익률 − 같은 구간 자기 상장 시장 지수 수익률)을 각각 그날 횡단면에서 상하위 1% 윈저라이즈 후 z-score로 표준화해 **평균**한 값이 시그널이다(클수록 상위). 발표 자격 창은 `risk.ranking_entry_delay_days`(기본 2)부터 `risk.ranking_expiry_days`(기본 60) 거래일까지이며 그 밖은 NaN이라 후보에서 빠진다 — '발표 후 N일이 지난 종목만 편입하고 M일이 지나면 제외'가 시그널 자체로 표현된다. 새 분기가 발표되면 옛 분기 시그널은 그 날 끊긴다. fail-closed: 전년 동기 분기 없음(결산일 간격 11~13개월로 **날짜 대조**, 목록에서 4칸 앞이 아니다)·표본 미달·표준편차 0·구간 가격 결측·분기 실적 미수집은 NaN이다. 재료는 잔차 반전과 공유한다(`residual_factor.return_materials` — 지표 전용 전체 이력이라 백테스트 창·워밍업 길이에 값이 흔들리지 않는다). ETF·미국 시장·복합 순위 합산은 오류 + 제거 + 미지원 안내. 계산 불가 시 결과 경고(`RANK_METRIC_DATA_MISSING`) 후 실패한다(조용한 0거래 금지). 원재료는 DART 분기보고서의 3개월 EPS와 공시 접수일(`engine/quarterly_earnings.py` — 4분기는 연간 − 3분기 누적, 연결/별도는 종목 단위로 고정, **2016년 이후**만 가용). 발표일은 **원공시** 접수일이어야 한다[2026-09-21] — 재무 조회 API의 접수번호는 정정본을 가리키므로 공시검색에서 결산월별 최초 접수일을 받아 min 클램프한다(정정일을 발표일로 쓰면 몇 년 전 분기가 정정일에 새 발표로 자격 창에 들어오고 최신 분기 시그널을 끊는다). EPS 값은 정정 후 값이다(API 한계). ② **섹터별 비중 상한** `risk.max_sector_weight_pct`(%, 0 초과 100 미만일 때만 유효): 같은 섹터 종목의 목표 비중 **합**이 상한을 넘으면 그 섹터 안에서 비례 축소한다(섹터 안 상대 비중 보존 — 원소별 min이 아니다). 잘린 몫은 재배분하지 않고 현금이며, 종목당 상한(FR-BT-074) **뒤에** 적용한다. 섹터를 모르는 종목과 구성원이 하나뿐인 섹터는 제약 대상이 아니다. 조건 루프 경로는 목표 비중 행렬이 희소(NaN=주문 없음)하므로 보유 목표 비중을 추적해 매 거래일 집행한다. ③ **유니버스 사전 필터**: `risk.universe_market_cap_top_n`은 매 거래일 실측 시가총액 상위 N종목만 남긴다(지수 상위 N 마스크의 일반화 — 특정 지수의 구성종목이 아니라 그 시점 순위임을 결과 경고 `MARKET_CAP_TOP_N`으로 고지), `risk.universe_liquidity_exclude_bottom_pct`는 `universe_liquidity_lookback_days`(기본 20)거래일 평균 거래대금의 그날 횡단면 백분위 하위 X%를 제외한다(결과 경고 `LIQUIDITY_PERCENTILE_EXCLUDED`). 둘 다 next_open이면 신호와 같은 지연을 적용한다. 회귀: `backend/tests/test_earnings_factor.py`, `test_quarterly_earnings.py`, `test_sector_weight_cap.py`.

**FR-BT-076** [정액 적립식(DCA), 2026-09-21, 엔진 v16.20.0·프롬프트 6.7] 엔진은 지정 종목을 납입 일정대로 조건 없이 사 모으는 정액 적립식 백테스트를 opt-in으로 지원해야 하며, 납입 필드를 쓰지 않는 전략의 결과는 변경 전과 비트 단위로 같아야 한다. ① **요청**: `risk.contribution_amount`(회차 납입액)·`risk.contribution_period`(daily|weekly|monthly|bimonthly|quarterly|semiannual|yearly) — 둘 다 있어야 하고 `backtest_mode=single_asset`(지정 종목)에서만 받는다. 매수·매도 조건, 랭킹, 손절·익절·트레일링·보유 기간과 섞인 요청과 유니버스 요청은 조용히 무시하지 않고 거절한다(Fail Fast). 범위를 지정 종목으로 한정한 이유는 체결 장부(vectorbt `from_orders`)가 회차 입금을 받지 못해 일반 전략 위의 납입은 근사 재계산이 필요하기 때문이다(2026-09-21 사용자 결정). ② **장부**(`engine/contributions.py`, 일반 체결 경로와 분리): 첫 봉은 초기 자본(1회차), 이후 리밸런싱 달력과 같은 규칙(각 주기의 첫 거래일)으로 납입하고 그 봉의 체결가(next_open=시가, same_close=종가) × (1+슬리피지)에 매수 수수료를 붙여 산다. 달력만으로 정해지는 매수라 신호 지연이 없다. 납입금은 종목별 예산으로 균등하게 나누고 정수 주만 사며 잔돈은 그 종목 예산에 이월한다 — 1주 값이 예산보다 비싸면 그 회차는 건너뛰고 다음 회차에 합쳐 사며(결과 경고로 고지), 납입일에 거래할 수 없는 종목(상장 전·거래정지)은 거래 가능해지는 첫 봉에 산다. 매도는 없고 기말 보유분은 종가로 평가한다. ③ **수익률**: 자산곡선은 납입으로도 오르므로 `totalReturn`·`cagr`·`maxDrawdown`·`sharpe`·`sortino`·`volatility`·`calmar`는 **시간가중 수익률** r[t] = 평가액[t] ÷ (평가액[t-1] + 납입[t]) − 1 로 계산해 일반 백테스트와 같은 뜻을 유지한다(기존 키를 재정의하지 않는다). 납입 시점·금액을 반영한 수치는 새 결과 키 `contributions` = {period, amount, count, totalContributed, finalValue, profit, simpleReturn, moneyWeightedReturn(XIRR, 해가 없으면 null), cumulative[]}에 싣고, `totalProfit`은 평가액 − 총 납입액이다. 매도가 없어 승률·Profit Factor·켈리 등 거래 통계는 계산하지 않는다(0/null + 결과 경고). ④ **벤치마크**: 목돈 1회 곡선과 적립 곡선의 비교는 성립하지 않으므로 `benchmark_equity`도 같은 날 같은 금액을 넣은 곡선이다(`buyAndHoldReturn`은 시간가중 기준이라 그대로). ⑤ **대화 레인**: 인터프리터는 `backtest.contribution_amount`(초기 자본과 같은 옮겨 적기 계약 — 말한 표기를 그대로, 환산은 결정론 코드)·`backtest.contribution_period`를 출력 형태에 가진다. 주기 표기는 리밸런싱 주기와 같은 표로 정규화한다. 납입액·주기 중 한쪽만 말했거나 사 모을 종목을 지정하지 않았으면 기본값으로 채우지 않고 되묻는다. 조건·랭킹·손절과 섞이면 적립 설정을 빼고 무엇이 빠졌는지 안내한다(조용한 제거 금지). ⑥ **최소 조건 게이트**: 적립식은 납입 일정이 곧 매수 규칙이고 매도가 없으므로 매수·매도 조건, 손절·익절, 리밸런싱·리밸런싱 방식 슬롯은 '해당 없음'이다 (정본 `strategy_slots._decided`, 프론트 미러 `backtestReadiness.ts`·`builderProgressPresentation.ts`, 계약 픽스처 `slot-judgments.json`). ⑦ **표시**: 결과 화면은 `contributions`가 있으면 '최종÷초기−1' 계산을 쓰지 않고, 승률·손익비 자리에 총 납입액·단순 수익률·금액가중 수익률을 보인다. 회귀: `backend/tests/test_contributions.py`.

**FR-VA-DCA** [가상계좌 정기 납입, 2026-09-21] 자동매매 계좌의 전략이 정액 적립식(FR-BT-076의 판정과 같다 — 납입액·주기가 둘 다 있는 지정 종목 전략이고 조건·랭킹·손절과 섞이지 않음)이면 자동매매 루프가 납입 회차를 실행해야 한다. ① **회차**: 1회차는 계좌의 초기 자본이다(입금 없이 지정 종목 매수 시작 — 백테스트 첫 봉과 같은 규약). 이후 체결 창이고 오늘 시세가 있는 거래일에, 마지막 납입 기록일과 오늘의 주기 키(`live_signal_utils._period_key`, 백테스트 달력과 같은 주기 어휘)가 다르면 새 회차다. ② **놓친 납입일**(2026-09-21 사용자 결정): 서버가 꺼져 납입일을 놓쳐도 같은 주기 안에 돌아오면 그날 납입하고, 한 주기를 통째로 놓치면 그 회차는 건너뛴다(소급 입금 없음). ③ **플랜 한도**(같은 날 결정): 적립 계좌는 플랜 모의 투자금 전액이 아니라 **전략의 초기 자본**(플랜 투자금 이하)으로 시작하고, 초기 자본 + 누적 납입이 생성 시점의 플랜 투자금(`VirtualAccount.contributionCap`)을 넘지 않는다 — 남은 한도만큼만 넣고, 한도에 닿은 주기는 `CONTRIBUTION_CAPPED`로 닫는다. ④ **중복 방지**: 입금 기록 `VirtualCashEvent`의 `(accountId, date)` 유니크가 '하루 한 번'의 정본이며 입금 기록과 잔액·누적 납입 증가는 한 트랜잭션이다(루프는 30초마다 체결 창에 다시 들어오고 프로세스 재시작도 있다). 시세가 없는 날은 회차를 쓰지 않는다. ⑤ **매수**: 입금 뒤 계좌 현금 전부를 지정 종목에 균등하게 나눠 정수 주로 산다 — 1주도 못 산 몫은 계좌 현금에 남아 다음 회차 예산에 합쳐진다(백테스트 장부는 종목별 예산 이월, 계좌는 계좌 단위 이월). next_open 경로는 신호가 난 종목만 시세를 받으므로 적립 계획이 있으면 지정 종목을 시세 대상에 포함한다. 납입 매수는 신호 로그에 매수(`entry`)로 기록하고 사유 문구로 구분한다. 수동(manual) 계좌에는 납입하지 않는다. ⑥ **수익률**(같은 날 결정): 계좌 수익률의 분모는 **총 납입액** = `initialCash + contributedCash`다 — 계좌 상세·카드·개요, 계좌 대시보드 API, 대시보드 계좌 목록·전략 목록·월별 수익률(가중치 포함), 내 정보 합산, 관리자 목록이 같은 분모를 쓴다(`lib/virtual-account/contributions.ts`). 납입이 없는 계좌는 누적 납입이 0이라 종전 값과 같다. 일별 자산 기록이 없어 시간가중 수익률은 제공하지 않는다. ⑦ 관리자 초기화는 납입 기록과 누적 납입도 지운다. 마이그레이션 `20260921000000_add_virtual_cash_event`(가산 — 컬럼 2개·테이블 1개, 배포가 `prisma migrate deploy`로 자동 적용). 회귀: `backend/tests/test_virtual_contributions.py`, `lib/virtual-account/contributions.test.ts`.

**구현 파일:** `backend/engine/transaction_tax.py`(신규), `backend/engine/simulator.py`(`_resolve_fee_rates` 벡터·`_run_orders`), `backend/engine/loader.py`(`sanitize_corporate_actions`), `backend/engine/phase1.py`(US 플래그·`market_cap` 동봉), `backend/engine/universe_pit.py`(`delisting_floor`), `backend/backtest_engine.py`, `backend/schemas.py`, `backend/ai/local_optimization_agent.py`, `app/analytics/new/page.tsx`, `lib/i18n/en.ts`. 회귀: `backend/tests/test_bias_audit_fixes.py`, `test_transaction_tax.py`, `test_engine_simulator.py`.

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

**FR-VM-001a** [백테스트 결과에서 계좌 개설, 2026-08-24] 백테스트 결과 화면에서 방금 검증한 전략을 운용 전략으로 하는 가상계좌를 바로 만들 수 있어야 한다.
- 계좌 생성 모달은 전략 목록 대신 해당 백테스트 전략을 고정해 표시하며(`CreateAccountModal`의 `presetStrategy`), 계좌 이름은 전략 이름으로 미리 채운다. 전략 내용은 결과 화면 '내 전략' 팝오버와 같은 라벨·값 행(유니버스/진입 신호/청산 신호/백테스트 기간/초기 자본/리스크)으로 표시한다.
- 가상계좌는 추적 종목·자동매매 신호를 위해 `Strategy` 행을 참조하므로, 계좌 생성 전에 `POST /api/strategy/ensure`로 전략 행을 확정한다. 이 경로는 **같은 DSL의 전략이 이미 저장돼 있으면 그 id·이름을 그대로 사용**하고(사용자가 붙인 이름을 덮어쓰지 않는다), 없을 때만 저장한다. 이때 **실행한 백테스트 결과도 함께 저장**한다(결과 행이 없으면 저장 전략 목록에서 그 전략을 눌렀을 때 결과 화면이 비어 버린다). 이미 결과 행이 있으면 덮어쓰지 않는다 — AI 리포트까지 붙여 저장한 행을 보존한다.
- 매매 방식(전략 시뮬레이션)은 이 경로에서만 기본 ON으로 연다. 가상계좌 목록에서 전략을 골라 만드는 기존 경로의 기본값은 OFF를 유지한다.
- 저장이 필요한데 플랜의 저장 전략 수 한도를 넘으면 계좌를 만들지 않고 한도 안내를 표시한다(FR-PLAN-003).

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

KIS WebSocket 시세 캐시는 신선도 한도(300초)를 넘긴 틱을 서빙하면 안 되며(초과 시 REST 폴백 체인으로 강등), 구독 등록이 `MAX SUBSCRIBE OVER`로 거부되면 세션을 재연결해 서버 구독 상태를 클라이언트 LRU와 재정합해야 한다(재연결 쿨다운 60초). WS 구독 상한(기본 14종목)은 배치 크기와 무관하게 예외 없이 강제한다 — 상한보다 큰 배치는 최신 종목만 남긴다. 전일대비(diff) 필드는 부호가 포함될 수 있으므로 방향은 부호 필드로만 판정하고 변동폭은 절대값으로 쓴다. (2026-08-24 사고: 30종목 배치가 배치 보호 예외로 상한을 통과 → KIS 세션 등록 정원 초과 → 구독 desync로 틱이 끊긴 뒤 캐시가 아침 09:01 시세를 하루 종일 서빙. 회귀: `backend/tests/test_kis_realtime_providers.py`, `test_kis_ws_lru.py`, `test_market_data.py`)

한국 종목 **2종목 이상 배치 조회**는 토스증권 Open API 배치 시세(`engine/providers/toss_kr.py`, `/api/v1/prices` 200종목/1요청, 환경변수 `TOSS_INVEST_CLIENT_ID/SECRET`)가 REST 체인보다 먼저 받는다 — 종목별 개별 호출인 KIS REST/Naver를 N번 때리는 낭비와 WS 구독 압력을 제거한다. 단건 조회는 OHLC·거래량을 제공하는 기존 KIS REST 체인을 유지하고, 배치 레인 실패·미응답 종목은 기존 폴백 체인이 흡수한다. 토스 응답에는 현재가·통화만 있어 전일종가는 로컬 한국 파케이(`data/ohlcv`)로 보강하며, `lastPrice`에는 시간외 가격이 반영된다(장외 시간 등락률은 참고치). 시세 조회 전용 — 주문·계좌 API는 사용하지 않는다.

**FR-VM-044** 가상 시장 갱신 이력은 `VirtualMarketLog`에 기록되어야 한다 (날짜, 종목코드, 종목명, 시그널 유형, 가격, 액션). [2026-09-13 — 사유(reason) 계약] 로그의 `reason`은 거래 내역 매매사유와 같은 **세그먼트 페이로드**(`engine/trade_reason.py` 인코딩 문자열: 정본 템플릿+인자)로 저장하고, 표시 문장은 프론트(`lib/trade-reason.ts::tradeReasonText` → `SignalLog`)가 번역·계좌 통화를 입혀 만든다. 자동매매(`engine/virtual_trader.py`)의 리스크 청산·리밸런싱 편출·강제청산 사유와 라이브 랭킹 사유(`live_signal_utils`)도 f-string이 아니라 템플릿(`LIVE_STOP_LOSS`·`LIVE_TAKE_PROFIT`·`LIVE_TRAILING_STOP`(최고가=금액 인자)·`LIVE_MAX_HOLDING`·`LIVE_FORCED_LIQUIDATION`·`LIVE_RANK_POSITION`)으로 만들고, 조건 사유와의 병합은 `_merge_exit_reason`이 세그먼트로 잇는다(문자열 덧셈 금지). 사유 종류 판별은 `tr.first_template`, 감사 로그는 `tr.text` 한국어 문장. 사고: 엔진 조건 사유가 2026-09-01부터 인코딩 페이로드로 바뀌었는데 이 레인은 문자열을 그대로 저장·표시해 매매 신호 카드에 `RJ[{"t":…}]`가 노출됐고, 같은 카드가 USD 계좌 가격을 "202.55원"으로 표기했다(`SignalLog` `currency` prop으로 수리). 구버전 평문 사유는 그대로 표시된다(마이그레이션 불필요 — 이미 저장된 인코딩 행도 이제 문장으로 렌더링된다). 회귀 `components/__tests__/SignalLog.test.tsx`(사유·통화 4건)·`backend/tests/test_virtual_trader_signals.py::test_live_exit_reasons_are_segment_payloads`·`::test_live_reason_templates_render_korean`.

**FR-VM-045** 자동 실행과 시그널 알림은 계좌·종목·시그널 유형별로 **하루 1회**만 기록/실행되어야 한다 (30초 평가 틱마다 중복 알림 금지).

**FR-VM-046** PENDING 지정가 주문 체결은 두 경로(백엔드 VirtualTrader 루프, 브라우저 fill 라우트) 어느 쪽에서든 `status = 'PENDING'` 조건부 갱신으로 **원자적으로 선점**해야 하며, 동일 주문이 두 번 체결되어서는 안 된다. 매도 체결 시 보유 수량이 부족하면 주문을 `CANCELLED` 처리한다.

**FR-VM-047** 가상계좌 거래 비용 모델은 백테스트 엔진과 정합해야 한다: 수수료 0.015%, 증권거래세(매도) 0.15%(백테스트 기본값과 동일), 시장가 슬리피지 0.05%, KRX 호가단위(2023-01 개편 기준).

**FR-VM-048** 백엔드(Python)가 Prisma 관리 테이블의 DateTime 컬럼에 기록할 때는 Prisma와 동일한 **epoch ms 정수** 포맷을 사용해야 한다 (포맷 혼재 시 SQLite 정렬이 왜곡됨). 읽기는 epoch ms 정수와 ISO 문자열(레거시)을 모두 허용한다.

**FR-VM-049** 자동매매는 **계좌 시장의 당일(한국 계좌 KST, 미국 계좌 ET) 날짜의 시세만** 사용해야 한다. 시세의 `date`가 오늘이 아니거나 없으면(평일 공휴일의 KRX 휴장, 데이터 소스 장애) 해당 종목의 진입·청산·리스크 청산·지정가 체결을 모두 보류한다. 별도의 휴장일 캘린더 없이 이 가드가 휴장일 매매를 방지한다.

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

**FR-VM-067b** [종목 마스터 신선도 — 생존 편향이 조용히 되살아나는 것을 막는다, 2026-09-16] 시점 유니버스의 진실 소스인 `data/stock-master.json`은 가격 동기화와 같은 주기로 갱신돼야 한다. ① **갱신 방식은 제자리 병합**이다(`backend/scripts/refresh_stock_master.py`) — 전체 재빌드(`build_stock_master.py`)는 마스터에 누적된 섹터 후처리(묶음 분류 분할 `split_combined_sectors.py`, 외과 패치)를 되돌리므로 일상 갱신에 쓰지 않는다. 갱신은 로컬 OHLCV 커버리지(`dataStart`/`dataEnd`/`hasOhlcv`) 재스캔, FDR `KRX-DELISTING`의 신규 상장폐지 반영, 신규 상장 종목 추가와 활성 행의 상장주식수·종목명 갱신만 수행하고 `sector`/`industry`는 보존한다(멱등). ② **배선**: 일일 스케줄러(`scripts/scheduler.py::run_update`)가 데이터 동기화 직후 실행한다. ③ **as-of 결과가 비면 고지한다**: 마스터가 백테스트 구간을 담지 못해 `resolve_symbols`가 빈 목록을 반환하면 엔진은 프론트가 보낸 **현재 상장 종목** 목록으로 진행하되 결과 경고(`PIT_UNIVERSE_MASTER_STALE`)를 남긴다 — 종전에는 조용히 폴백해 생존 편향 제거가 꺼진 사실이 드러나지 않았다. 실측 사고(2026-09-16): 마스터가 2026-06-13 생성본에서 멈춰 ⓐ 그 뒤 상장폐지된 24종목이 유니버스에서 통째로 빠지고 ⓑ 2026-06-14 이후 시작하는 모든 창의 as-of 해석이 0종목이었다(경고 없음). 회귀: `tests/test_refresh_stock_master.py`.

**FR-VM-068** `/virtual-account/[id]` 페이지는 비정상 상장 상태 종목에 대해 `DelistingRiskBanner`를 표시해야 한다. 배너는 상태 배지, D-N 카운트다운, 강제청산 버튼을 포함해야 한다. 단, `TRADING_SUSPENDED`는 목록 행의 '거래정지' 배지로만 표시하고 배너는 띄우지 않는다.

**FR-VM-068b** [상장폐지 원장은 '폐지 완료'만 담는다 — 거래정지·폐지결정과의 구분, 2026-09-16] 상장 상태는 두 저장소가 나눠 표현한다. ① **`Stock.listingStatus`**(7단계 상태 머신)가 거래정지(`TRADING_SUSPENDED`)·상장적격성 심사(`DELISTING_REVIEW`)·상장폐지 결정(`DELISTING_SCHEDULED`)을 표현하고 매수·매도 허용 규칙을 결정한다. ② **`data/delisted-stocks.json`(DelistedSymbolStore)은 폐지가 완료된 종목만** 담는다 — 원장에 오르면 시세 조회가 provider 체인 진입 전에 끊기고(`market_data.get_price`), 라이브 신호 유니버스에서 제외되며, 가상계좌 평가가 0원이 된다. 따라서 **아직 상장 상태인 단계(거래정지·심사·폐지결정·정리매매)를 원장에 올려서는 안 된다**(정리매매 기간에는 매도할 수 있어야 한다). ③ **자동 등록의 유일한 신호는 KRX 명부 이탈**이다(`scripts/sync_data.py` — 종목 목록 갱신이 성공한 회차에 한해, 한 회 이탈이 `MAX_AUTO_DELIST_PER_SYNC`=20을 넘으면 KRX 조회 누락으로 보고 등록하지 않는다). DART 공시(`/market/dart/notices`)는 `listingStatus`만 갱신하고 원장에 쓰지 않는다. ④ **확정 판정의 정본은 `engine.listing_status.is_confirmed_delisting` 한 곳**이다 — 낱말 목록 사본을 다른 모듈이 들고 있어서는 안 된다(실측 사고: 일일 스케줄러가 2026-09-15 수리 이전의 사본을 들고 있어 '상장폐지 및 정리매매 절차 미진행' 공시로 정상 거래 종목을 원장에 올렸다). 확정 판정은 절차 보류 낱말(미진행·이의신청·보류·중단)과 **효력정지 가처분 계류**(기각·각하·취하가 함께 있지 않은 '가처분')를 확정에서 제외한다 — 가처분 계류 종목을 `DELISTING_SCHEDULED`로 보면 `AUTO_LIQUIDATE` 정책이 보유 포지션을 강제청산한다. ⑤ **오등록 정정**: 공시 동기화는 `DELISTED`를 강등하지 않으므로(폐지 완료는 번복하지 않는다는 정상 계약) 잘못 등록된 종목은 스스로 회복하지 못한다. 원장 해제(`DELETE /market/delist/{symbol}`)가 원장과 `listingStatus`를 함께 되돌린다(`clear_delisted_status`). 회귀: `tests/test_listing_status.py`, `tests/test_listing_status_db.py`, `tests/test_sync_data_status.py`.

**FR-VM-068c** [종목명은 공식 회사명 — 사명 변경 매일 반영, 2026-09-16] 현재 상장 명부 `data/korea-stocks.json`의 `name`은 KRX KIND 상장법인목록의 **공식 회사명**(거래소 약칭 아님 — '현대자동차'이지 '현대차'가 아니다)이다. ① 일일 스케줄러가 종목 마스터 갱신 뒤 `backend/scripts/refresh_stock_names.py`로 종목코드별 이름을 대조해 **이름만** 교체한다(sector·industry·market·name_en 보존, 행 추가·삭제 없음). 대조 출처는 DART 기업 고유번호 목록(corpCode.xml)의 corp_name이다 — 프로덕션 박스 IP가 kind.krx.co.kr에서 403으로 차단되며, DART corp_name은 KIND 회사명과 현재 상장 2,649종목 전부 일치한다(2026-09-16 실측). DART 목록엔 상장폐지 법인의 등기 법인명도 있으므로 대상은 종목 마스터의 현재 상장 종목으로 한정한다. ② 명부는 git 추적 파일이라 배포(`git reset --hard`)가 되돌리므로 스케줄러 기동 시에도 같은 갱신을 수행한다. ③ 사명이 바뀐 경우(공백·대소문자 차이 제외) 옛 이름을 `data/stock-name-history.json`의 `renames`에 사건(`source`, `observedOn`)으로 남기고 구 사명 별칭표를 기존 가드(모호·현재 등록명 충돌·3자 미만 제외)로 다시 계산해 옛 이름으로도 계속 인식되게 한다. 월별 스냅샷 재집계는 이 사건을 보존한다. ④ 출처 응답 이상 가드: 조회 행이 명부의 80% 미만이거나 사명 변경이 명부의 5%를 넘으면 쓰지 않고 중단한다. ⑤ 이름 소비자는 재시작 없이 따라간다 — 백엔드 종목 해석기(`symbol_resolver`)와 프론트 이름 맵(`getStockNameMap`)은 파일 변경 시각이 바뀌면 다시 읽는다. 최초 적용 25종목(세기상사→우양피앤엘 등).

**FR-VM-069** 모든 자동 처리 이벤트(청산, 차단, 상태변경)는 `DelistingAuditLog`에 기록되어야 한다.

**FR-VM-070** 백테스트 엔진은 **수정주가(adjusted price)**를 연속적으로 반영해야 한다. 소스 데이터는 정방향 액면분할만 조정돼 있고 역분할·감자·정지후재개·단일 오류프린트는 미조정이라 ±30% 가격제한을 넘는 불가능한 일간 점프가 남는다(가짜 손절·수익 유발). `loader._sanitize_corporate_actions`(`preprocess_data` 내)가 이를 처리한다:
- 단일 오류프린트(다음 바 반등) → 양옆 보간 중립화.
- 지속 레벨변화(역분할/감자/정지재개) → 점프 비율로 과거 전체를 역조정(OHLC 동일 스케일).
- 정리매매(시계열 끝 하락 크래시, `_CA_TAIL_GUARD`바 내)는 역조정하지 않는다 — 상장폐지 손실이 수익곡선에 남아야 한다.

**FR-VM-071** 가상계좌 모니터링(추적) 종목 목록은 상장폐지(`DELISTED`) 및 매매거래정지(`TRADING_SUSPENDED`) 종목을 포함하지 않아야 한다. 모든 모니터링 종목 진입 경로(전략 백테스트 상위 종목, 유니버스 기본 종목, 사용자 수동 지정)는 `filterMonitorableSymbols`(`lib/strategy-tracked-symbols.ts`)를 거쳐야 한다. [2026-09-13 — 계좌 통화 일치] 같은 모든 진입 경로는 **계좌 통화의 시장 종목만** 남겨야 한다(`filterSymbolsForCurrency` — USD 계좌에 한국 6자리 코드, KRW 계좌에 미국 티커 금지; 전략 시작 `strategy-start.ts`·계좌 생성·전략 교체 `virtual-account/[id]`·수동 지정 `virtual-market/[accountId]` POST/PATCH 전부). 전략 유니버스 id는 저장 형태 세 가지(`settings.universe.id`·`settings.universe_id`·`settings.canonical_strategy_dsl.universe[0]`)에서 읽고(`savedUniverseId`), 알 수 없을 때의 기본값은 계좌 통화를 따른다(USD=sp500, KRW=kospi200). 백테스트 상위 종목이 계좌 통화와 다르면 버리고 유니버스로 넘어간다. 사고: prod USD 계좌 2개(S&P 500 전략 'us-test-account', 'nvidia 관련주')가 KOSPI 상위 20종목을 모니터링 — 전략이 백테스트 요청형(`universe_id: "sp500"`)으로 저장돼 2026-08-26의 미국 분기(`settings.universe.id`만 읽음)가 닿지 않아 기본값 kospi200으로 떨어졌고, 통화 가드가 없어 그대로 저장됐다. 이미 저장된 목록은 자동으로 바뀌지 않으며 전략 시작/교체 시 재해석된다. 회귀 `app/api/virtual-account/tracked-symbol-filter.test.ts`(5건)·`app/api/virtual-market/[accountId]/route.test.ts`(USD 2건).

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
- **지정 종목 목록은 저장 형태 세 가지를 모두 읽는다** [2026-09-07]: `target_symbols`(DSL 정본) → `canonical_strategy_dsl.target_symbols`(백테스트 요청 `to_backtest_request`를 그대로 저장한 전략) → `backtest_mode == "single_asset"`인 전략의 최상위 `symbols`. 종전에는 첫 번째만 읽어 뒤 두 형태의 지정 종목 전략이 계좌 모니터링 목록(백테스트 상위 10종목)으로 폴백했다(실측: 21종목 전략이 10종목만 매매). 유니버스 모드의 `symbols`는 백테스트 시점에 풀어 둔 유니버스 스냅샷이므로 매매 대상으로 쓰지 않는다 — 과거 명단을 고정하면 생존편향(FR-VM-067 논리)이 자동매매로 넘어온다.
- **미국 유니버스는 백테스트와 같은 명부로 해석** [2026-09-05]: `sp500`·`nasdaq100`·`dow30`·`nasdaq`·`us`·`us_etf`는 `universe_pit.us_universe_kind`/`resolve_us_symbols`(현행 지수 명부·미국 마스터·ETF 마스터, 파케이 보유분)로 푼다. 종전에는 어느 분기에도 걸리지 않아 계좌 모니터링 목록(한국 코드)으로 폴백했고, 통화 격리 가드가 전부 제외해 미국 계좌의 매수 후보가 항상 0개였다. 명부가 비어도 한국 종목으로 채우지 않는다 — 폴백 목록 중 미국 티커만 남긴다.
- **지정가 대기 주문 게이트**: PENDING 지정가 주문 체결(FR-VM-046)도 진입·청산과 동일하게 상장 상태 게이트를 거쳐야 한다. 가격 조건만으로 체결하면 주문 접수 이후 거래정지·상장폐지된 종목이 그대로 체결된다. 판정은 같은 사이클에서 이미 조회한 상태를 재사용한다(추가 DB 조회 없음).

---


**FR-VM-074** [미국 계좌 집행 창·시세 병합, 2026-09-05] 전략 시그널 집행 창(`_is_strategy_execution_window`)은 계좌 통화의 시장 시계로 판정해야 한다 — 한국 계좌는 next_open=09:00~09:05 KST·current_close=15:30 KST, 미국 계좌는 정규장 개장 후 5분·정규장 종료 분(ET, 토스 장 운영 달력의 세션을 우선해 조기 종료 13:00도 반영, 달력 부재 시 09:30/16:00 고정). 종전 KST 고정 판정은 미국 장중(KST 밤~새벽)에 창을 한 번도 열지 않아 전략 매수·매도 시그널이 매 틱 지워졌다(리스크 청산·지정가 체결만 동작). 장중 판정(`us_market_calendar.is_open`)의 종료 시각은 분 단위로 비교한다(16:00:30 틱이 장외로 판정되면 종료 분 집행 창에 닿지 못한다). 가격만 주는 시세 소스(토스 US: `lastPrice`만, open/high/low/volume=0)를 실시간 봉에 병합할 때 0 이하의 OHLCV는 "값 없음"으로 보고 새 당일 봉은 시가·고가·저가=현재가, 거래량=직전 봉 값으로 둔다(0을 덮어쓰면 고저가 기반 지표가 무너진다). 보유 세션 수(`count_holding_sessions`)의 진입 날짜는 종목 시장의 현지 시간대(미국=America/New_York)로 환산한다.

**FR-VM-075** [예약 주문 큐 — 신호 후 N거래일 지연 체결의 자동매매 대응, 2026-09-14] 전략의 `risk.execution_delay_days`가 1보다 크고 체결 시점이 `next_open`이면 가상계좌 자동매매는 전략 신호를 즉시 집행하지 않고 **예약 주문 큐**(`VirtualScheduledOrder`, `engine/virtual_scheduled_orders.py`)에 넣어야 한다. ① **예약**: 신호가 난 날(지연 1이었다면 체결됐을 날, 계좌 시장 날짜)의 집행 창에서 진입·전략 매도·리밸런싱 편출 신호를 행으로 만들고 신호 로그에 `scheduled`로 남긴다. 같은 계좌·종목·방향의 미집행 예약이 있거나 이미 보유(매수)/미보유(매도)면 만들지 않는다(멱등 — 신호가 며칠 이어져도 한 건). ② **집행**: `signalDate` 뒤 `delayDays-1` 거래 세션(그 종목 봉+오늘 실시간 봉, `count_holding_sessions`와 같은 자)이 지난 첫 집행 창에서 시장가로 집행한다(백테스트 v16.9.0의 "신호 봉의 N번째 거래일 시가"와 동형). 창을 놓치면 다음 창으로 이월한다. 집행 시점에 보유·보유 종목 수 상한·현금·상장 상태를 다시 검사하며, 조건이 무너진 예약은 `SKIPPED`(코드: NO_POSITION·ALREADY_HELD·MAX_POSITIONS·INSUFFICIENT_CASH·ALREADY_EXITED_TODAY)로 닫고 신호 로그에 `skipped`로 남긴다. 예약 당시 전략(`strategyId`)과 계좌의 현재 전략이 다르면 `CANCELLED`(STRATEGY_CHANGED). 수동 모드는 만기일에 `notified` 로그 후 `NOTIFIED`. 집행 사유는 원 신호 사유 뒤에 `LIVE_DELAYED_FILL`("신호 후 {N}거래일 지연 체결 (신호일 {날짜})") 세그먼트를 병합한다. ③ **큐를 거치지 않는 것**: 손절·익절·트레일링·보유일 청산과 상장폐지 강제청산은 종전대로 감지 즉시 집행한다(백테스트와 동일). 지정가 대기 주문(`VirtualOrder` PENDING)도 무관. ④ 지연 1(기본)은 종전 즉시 집행 그대로다. ⑤ 미착수: 예약 목록 화면·수동 취소 UI(현재는 신호 로그의 예약/스킵 배지로만 보인다). 회귀: `backend/tests/test_virtual_scheduled_orders.py`.

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

플랜 정의(`lib/plans.ts`): Free(초기 투자금 1,000만원·계좌 1개·전략 3개·월 백테스트 50회),
Pro(5,000만원·10개·50개·500회), Premium(1억원·30개·무제한·1,000회). 기본 가입자는 Free.
유료 플랜 가격은 월간 Pro 25,000원·Premium 49,000원, 연간(1년 선불) Pro 240,000원·Premium 470,000원
(월 가격 × 12에서 20% 이상 할인). 한도는 결제 주기와 무관하게 동일하다.

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
첫 주기 결제 승인으로만 시작되어야 한다.
- 결제 주문(`POST /api/payment/order`)의 금액은 서버의 플랜 정의(`lib/plans.ts`)에서만 계산하고
  `PaymentOrder`에 기록해야 하며, 클라이언트가 보낸 금액은 신뢰하지 않아야 한다.
- 체크아웃은 카드 등록창(`payment.requestBillingAuth`, method=CARD)을 사용하고, 결제 전 화면에
  월 자동갱신 결제 조건(상품명·금액·자동 청구·해지 방법)을 고지해야 한다(약관 제12조 1·7항).
- 구독 승인(`POST /api/payment/confirm`)은 successUrl로 돌아온 `customerKey`를 서버 저장
  `User.tossCustomerKey`와 대조해 불일치 시 거부해야 하고, `authKey`로 빌링키를 발급
  (`/v1/billing/authorizations/issue`)한 뒤 첫 달 이용료를 서버 저장 주문 금액으로 즉시 청구
  (`/v1/billing/{billingKey}`)해야 한다. 청구 성공 시에만 `planTier`·`planStartDate`·
  `tossBillingKey`·`subscriptionPlanId`·`billingCycle`·`nextBillingAt`(월간 +1개월, 연간 +12개월)을
  갱신한다.
- 동일 주문의 승인 재요청(성공 페이지 새로고침 등)은 중복 승인 없이 기존 결과를 반환해야 한다
  (멱등키=orderId).
- `POST /api/user/plan`은 FREE 전환(다운그레이드)만 허용해 결제 없는 유료 전환을 차단해야 하며,
  FREE 전환 시 빌링키·구독 상태를 모두 해제해 이후 자동 청구가 발생하지 않아야 한다.
- 시크릿 키(`TOSS_SECRET_KEY`)와 빌링키(`User.tossBillingKey`)는 서버 전용이며 클라이언트에 노출되지
  않아야 한다. `customerKey`는 이메일·회원번호 등 유추 가능한 값이 아닌 사용자당 1회 생성된
  UUID(`User.tossCustomerKey`)를 사용해야 한다.
- 인증 실패/취소(failUrl)는 승인 API를 호출하지 않고 오류 코드에 따른 안내와 재시도 경로만 제공해야
  한다.

**FR-PLAN-011a** 구독은 해지 전까지 결제 주기마다 자동 갱신 결제되어야 한다.
- 인-프로세스 스케줄러가 매시 정각(주말 포함) 갱신 잡(`processDueBillingRenewals`)을 실행해
  `nextBillingAt`이 지난 구독을 빌링키로 청구하고, 성공 시 `nextBillingAt`을 예정 시각 기준
  구독의 청구 주기만큼(월간 +1개월, 연간 +12개월) 굴려야 한다(재시도 지연으로 결제 주기가 밀리지
  않아야 한다). 갱신 결제도 `PaymentOrder`에 기록한다.
- 청구 실패 시 1일 후 재시도하고, 연속 3회 실패하면 FREE로 전환하며 빌링 상태를 해제해야 한다.
  한 구독의 처리 실패가 다른 구독의 갱신을 막지 않아야 한다.
- 해지(`POST /api/payment/billing/cancel`)는 즉시 FREE 전환이 아니라 해지 예약
  (`subscriptionCanceledAt`)으로 처리해야 한다 — 이미 결제된 기간에는 유료 플랜을 유지하고, 다음
  결제일에 청구 없이 FREE로 전환한다(약관 제12조 8항). 해지 재요청은 멱등 처리한다.
- 요금제 페이지는 자동갱신 중인 현재 플랜에 다음 결제일과 해지 수단을, 해지 예약 시 만료일을
  표시해야 한다.

**FR-PLAN-011b** [연간 결제, 2026-09-13] 유료 플랜은 월간·연간 두 결제 주기로 제공되어야 한다.
- 요금제 페이지는 결제 주기 선택(월간/연간)을 제공하고, 연간 선택 시 연 금액·월 환산 금액·할인율을
  함께 표시해야 한다. 표기 할인율은 실제 할인율을 넘지 않아야 한다(모든 유료 플랜 20% 이상 할인).
  무료 플랜은 주기와 무관하게 월 0원으로 표시한다.
- 주기는 주문 생성 시점에 서버가 확정해 `PaymentOrder.billingCycle`에 기록하고, 승인 단계는 그 값으로
  결제 금액과 다음 결제일을 정해 `User.billingCycle`에 저장해야 한다(클라이언트가 승인 시점에 주기를
  바꿔치기할 수 없어야 한다). 잘못된 주기 값은 월간으로 보정하지 않고 거부한다.
- 연간 구독 기간 중에는 플랜·주기 변경을 막아야 한다 — 즉시 재결제로 갈아타면 이미 낸 잔여 기간(최대
  11개월)이 소멸하기 때문이다. 화면은 유료 플랜 변경 버튼을 잠그고 사유를 안내하며, 서버
  (`POST /api/payment/order`)도 같은 조건을 재검증해 409로 거부해야 한다. 해지(FREE 전환)는 주기와
  무관하게 항상 가능해야 한다.
- 연간 구독의 해지도 월간과 같이 해지 예약으로 처리한다 — 만료일(다음 결제일)까지 유료 플랜을
  유지하고 그 시점에 청구 없이 FREE로 전환한다. 시스템은 중도 자동 환불을 수행하지 않는다.
- 약관(제11조·제12조)은 연간 결제를 다음과 같이 규정한다: 결제 주기(월간/연간) 선택과 한도 불변,
  연간 기간 중 플랜·주기 변경 제한(해지는 항상 가능), 그리고 **연간 중도 해지 정산** — 고객센터
  신청 시 결제 금액에서 `이용 개월 수 × 월간 정가`를 공제한 잔액을 환불한다(개시한 달=1개월, 할인은
  12개월 유지 조건이라 정산에 미반영, 공제액 ≥ 결제 금액이면 환불 0, 제3항의 사용 후 환불 제한은
  연간 정산에 적용하지 않음, 환불 시 유료 플랜 즉시 종료). 근거: 1년 선불은 방문판매법상 계속거래로
  중도 해지 시 잔여 대금 환급 의무가 있어 사용 후 환불 제한 조항만으로는 충돌한다. 정산은 운영자가
  수동 처리한다(자동화 미구현).
- 백테스트 사용량 리셋 주기는 결제 주기와 무관하게 1개월 롤링을 유지한다(FR-PLAN-010).

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

**FR-SA-002c-1** [규제 안전 — 전략 추천 금지] 구체적인 지표·전략 유형 없이 어떤 전략이 우수한지 골라 달라는 **열린 전략 추천 요청**("지금 어떤 전략이 좋을까?", "전략 추천해줘", "무슨 전략을 써야 하나요?")은 전략 우열을 판단·추천하지 않고, 함께 전략을 만들어 백테스트하는 **전략 빌더**로 대화를 전환하는 안내(`QueryIntent.STRATEGY_PICK` + `suggested_reply`)로 응답해야 한다. 전환 안내("어떤 전략이 더 좋은지 판단하거나 추천해 드리지는 않지만, 관심 있는 아이디어를 함께 전략으로 만들어 … 백테스트해 볼 수 있어요") 직후에는 STOCK_PICK(FR-SA-002b/c)과 동일하게 곧바로 빌더 모드로 진입해 첫 질문(시장 선택)을 능동적으로 띄운다. 결정적 감지(`intent/scope.py::is_strategy_pick_request`)는 '전략' 키워드가 있어 STRATEGY_ADVICE로 새기 전에 먼저 잡되, 구체적인 전략 유형·지표(모멘텀·RSI·MACD 등)나 기존 전략 지시어("이 전략"), 정량 스크리닝·수정 명령·특정 종목명이 섞이면 설계 요청이므로 가로채지 않고 일반 전략 흐름에 맡긴다. [2026-08-23 성과 목표만 있는 요청] 종목을 고르는 조건 없이 **백테스트 결과 지표**(CAGR·MDD·수익률·샤프지수·승률)를 최대화·최소화해 달라는 요청("CAGR를 최대화하고 MDD를 최소화하는 전략을 만들자", "수익률 극대화 전략 만들어줘")도 열린 전략 추천이다 — 성과 지표는 시뮬레이션의 **결과**이지 종목 선별 기준이 아니므로, 그 결과를 내 줄 전략을 대신 골라 달라는 요청과 같다. 분류는 LLM 레인(`intent/interpreter.SYSTEM_PROMPT`의 STRATEGY_PICK 정의)이 하며, 성과 목표에 선별 기준이 함께 있거나("코스닥에서 수익률 높은 전략") 진행 중인 전략의 성과를 개선해 달라는 요청이면 설계·수정 요청(STRATEGY_ADVICE)이다. 라이브 회귀 게이트: `scripts/qa_intent_open_pick_scope.py`.

**FR-SA-002c-2** [기능 범위 — 미제공 기능 안내] 뉴스·공시·SNS 여론처럼 플랫폼이 제공하지 않는 데이터 분석을 근거로 종목을 고르거나 전략을 만들어 달라는 요청("최근 뉴스가 좋은 종목을 사는 전략을 만들어줘", "호재 있는 종목 골라줘")은 전략 빌더로 진입하지 않고, 해당 기능을 제공하지 않는다는 안내와 함께 다른 투자 아이디어를 유도하는 응답(`QueryIntent.UNSUPPORTED_FEATURE` + `suggested_reply`)으로 답해야 한다(2026-07-12 — '전략' 키워드로 STRATEGY_ADVICE에 새서 빈 전략 파싱→빌더 자동 전환으로 이어지던 사고의 재발 방지). 결정적 감지(`intent/scope.py::is_unsupported_feature_request`)는 뉴스 단어(뉴스·공시·호재·악재·풍문·루머·기사·여론·SNS)가 종목 선정/전략의 근거로 쓰인 경우만 잡되, ① 지원 지표·재무 신호(RSI·이동평균·PBR 등)가 섞인 혼합 요청은 가로채지 않고 일반 전략 흐름에 맡기고(파서가 지원 부분을 살리고 미지원 개념 notice — `engine.nl_parser` "news" 항목 — 로 알림), ② 순수 정의형 질문("공시가 뭐야?")과 ③ 종목명(또는 anaphora)+행동 질문("삼성전자 악재 떴는데 팔까?" → FR-SA-006 종목 질문 전환)은 기존 규칙에 맡긴다. 긴 꼬리 phrasing은 LLM 폴백 분류가 `UNSUPPORTED_FEATURE`로 잡으면 동일 안내를 채운다. 프론트(`maybeRouteNonStrategyQuery`)는 이 intent에서 빌더 스텝·전략 파싱을 호출하지 않고 안내만 표시한 뒤 후속 입력을 기다린다.

**FR-SA-002c-3** [대화 맥락 기반 후속 질문 분류] "다른 예는 없어?", "더 알려줘"처럼 직전 챗봇 답변에 이어지는 **후속 질문**은 문장만 보면 투자 신호가 없어 역할 밖(OFF_TOPIC) 거절로 새면 안 된다(2026-07-12 사고 — 종목 질문 전환 안내가 전략 예시를 보여준 직후 "다른 예는 없어?"가 거절됨). 프론트(`app/analytics/new/chatHistory.ts::selectClassifierHistory`)는 분류(`/query/classify`)와 일반 답변(`/query/general`) 호출에 최근 대화 턴(기본 6턴, 로딩 자리표시자·빈 메시지 제외)을 `history`로 함께 보내고, 백엔드 LLM 폴백 분류(`intent/classifier.py::_classify_with_llm`)는 이를 `[대화 맥락]`/`[최신 입력]`으로 구분해 넘겨 직전 주제의 연속으로 분류한다(직전 주제가 투자면 OFF_TOPIC 금지, 예시·설명 추가 요청은 GENERAL_INVESTMENT). `/query/general`도 같은 맥락(`format_history_context`, 턴당 240자 절단)을 받아 직전 답변과 겹치지 않게 이어서 답한다. 결정적 규칙은 현재 입력만 본다 — 투자 맥락이 있어도 명백한 역할 밖 질문("오늘 날씨 어때?")은 여전히 거절된다.

**FR-SA-002c-4** [활성 전략 중 정의형 질문] 전략 요약이 이미 만들어진 대화에서도 용어 정의·일반 지식 질문("pbr이 뭐야?")은 전략 수정 파싱이 아니라 일반 지식 답변(`/query/general`, history 포함)으로 응답해야 한다(2026-07-17 사고 — `GENERAL_INVESTMENT` 분류가 `hasCurrentStrategy` 게이트에 막혀 수정 파싱으로 흘렀고, 바꿀 필드가 없어 무변경 전략 요약만 다시 렌더링되고 질문은 답변되지 않음). 프론트 대화 결정(`app/analytics/new/conversationDecision.ts::decideConversationTurn`)은 `GENERAL_INVESTMENT`면 활성 전략 여부와 무관하게 `answer_general`로 라우팅하고, `UNKNOWN`은 기존대로 활성 전략이 있으면 전략 입력으로 본다. 전략 카드·백테스트 준비 상태는 답변 후에도 그대로 유지된다(전략을 건드리지 않는 경로). **백엔드 2차 방어선**: 그래도 질문이 수정 파싱 경로로 흘러 인터프리터가 CLARIFY_STRATEGY(패치 없음)+질문으로 응답하면, `strategy_conversation/primary.py::run_primary_modification`은 폴백으로 질문을 버리는 대신 — 단, 결정적 fast-path(`_modify_rule_based`)가 처리할 수 있는 단순 수정은 기존대로 폴백(되묻기가 단순 수정을 가로막지 않게) — 전략을 그대로 유지한 채 질문을 기존 clarification 채널로 전달해 사용자가 무변경 요약 대신 되묻기를 받게 한다. 인터프리터가 질문 대신 `EXPLAIN_INDICATOR`나 `unsupported_features`(패치 없음)로만 보고하는 경우(2026-07-17 실측: `unsupported_features=["PBR 개념 설명 요청"]`)도 침묵 폴백하지 않고 전략을 유지하며, **정의형 질문(결정적 cue `intent.classifier.is_definition_question` — 4B 라벨이 아니라 입력 기준)이면 `/query/general`과 동일한 생성기(`api.intent_routes.generate_general_answer`)로 실제 용어 설명을 만들어 notices 채널로 답한다**(`primary_modify_explain`, 2026-07-19 — "변경하지 않았어요" 안내만 주면 질문이 답변되지 않는다는 사용자 교정). 설명 LLM 미가용이면 준비하지 못했다는 정직한 안내, 정의형 질문이 아닌 진짜 미지원 개념 요청은 미반영 안내를 준다(`primary_modify_unsupported`). 인터프리터 프롬프트(1.2)는 초안이 있어도 용어·개념 설명 질문은 MODIFY가 아니라 EXPLAIN_INDICATOR이며 unsupported_features에 넣지 않도록 계약한다.

**FR-SA-002c-5** [백테스트 설정 기본값 정확 답변] "슬리피지는 몇 %가 기본 값이지?", "현재 셋팅된 슬리피지 값은?"처럼 백테스트 설정(슬리피지·수수료·증권거래세·초기자금·체결 시점)의 기본값·현재값을 묻는 질문에는 LLM 일반답변이 값을 지어내게 두지 않고(2026-07-20 사고 — 전략 분석실이 "기본값은 0%"라고 오답) 코드의 실제 기본값으로 정확히 답해야 한다. 결정적 감지(`intent/platform_defaults.py::is_default_question` — 설정 용어+값 질문 cue, "0.1%로 설정해줘" 같은 값 변경 명령형은 제외)가 분류기 결정 규칙(전략 키워드 게이트보다 먼저)으로 `GENERAL_INVESTMENT`에 라우팅하고, `generate_general_answer`가 LLM 호출 전에 결정적 답변(`platform_defaults.reply`)을 반환한다(LLM 미가용에도 동작). 답변 값은 하드코딩하지 않고 SOT에서 읽는다 — ParsedStrategy 필드 default(수수료 0.015%·슬리피지 0.05%·초기자금 1,000만원·체결 다음 날 시가), `MIN_INITIAL_CAPITAL`(100만원 하한), 시뮬레이터 `DEFAULT_SELL_TAX_RATE`(매도 거래세 0.15%, ETF 유니버스는 0%). 수수료 질문에는 매도 거래세를 동반 안내해 총비용 오해를 막고, 설정 패널에서 변경 가능함(변경 시 그 값 적용)을 함께 알린다. 설정 용어가 언급된 개념 질문("슬리피지가 뭐야?")은 LLM이 설명하되 실제 기본값 사실 블록(`facts_block`)을 프롬프트에 주입해 값 환각을 막는다. 수정 파싱 경로로 오라우팅된 경우의 백스톱(`run_primary_modification`, FR-SA-002c-4)도 이 cue를 질문으로 인정한다.

**FR-SA-002c-6** [레드팀 검증 — 규제·안전·정확성 강화, 2026-07-20] 레드팀 QA 하니스(`scripts/qa_redteam_validation.py`, 145케이스·24유형; 리포트 `docs/qa_redteam_validation_report.md`; 회귀 `backend/tests/test_redteam_validation_fixes.py`)에서 발견한 결함들을 다음과 같이 방어해야 한다. ① [개인 맞춤형 조언 금지] 나이·자산·직업 등 개인 상황에 맞춘 전략·종목 추천 요청("40대인데 나한테 맞는 전략 뭐야?")은 LLM 일반답변으로 흘리지 않고(맞춤 조언 생성 사고 방지) 결정적 감지(`intent/scope.py::is_personal_advice_request`)로 `STRATEGY_PICK`+맞춤 추천 불가 안내로 가로챈다. `/query/general` 시스템 프롬프트도 개인 맞춤 추천을 금지한다. ② [금융 오개념 교정] 오개념을 단정·확인하는 발화("PER이 높을수록 싸다는 거지?", "무조건 사면 된대")는 파싱 경로(교정 기회 없음) 대신 지식 답변 경로(`GENERAL_INVESTMENT`, `is_misconception_assertion`)로 보내 먼저 바로잡는다(구성·수정 동사 동반 시 제외). ③ [실전 매매 미제공] 실계좌 자동매매·대리 투자 요청("자동으로 실전 매매까지 해줘", "내 돈 대신 투자해줘")은 `is_live_trading_request`로 `UNSUPPORTED_FEATURE`+가상계좌 모의투자 안내(가상/모의 언급 시 통과). ④ [해외 종목] 해외 종목 매수·매도 질문은 그 종목의 백테스트를 예시로 제안하지 않고(기능 환각 방지) 국내 시장 대상만 안내하며(`stock_question_redirect(overseas=True)`), 파싱 경로에서도 해외 개별 종목·해외 시장·우선주는 미지원 개념 안내(`_UNSUPPORTED_CONCEPT_PATTERNS`의 overseas/preferred_stock)로 조용히 드롭하지 않는다. ⑤ [기초 용어 정의 정확성] `/query/general` 답변에 PER·PBR·ROE·RSI·MACD·부채비율 등 표준 정의 사실 블록(`intent/glossary_facts.py::facts_block`)을 주입해 소형 LLM의 정의 오류를 막는다. [2026-09-17 레인 이관] 질문에 **어떤 용어가 나왔는지는 LLM이 짧은 문자열 목록으로 추출**하고(`glossary_facts.extract_terms`, 구조화 호출), 결정론 코드는 그 문자열을 정본 용어 별칭에 대조(소문자·공백 제거·괄호 앞뒤 후보)만 한다 — 종전 원문 정규식은 `\bper\b`가 "PER과"를 놓쳐(한글도 단어 문자) 정의가 주입되지 않았고, 답변이 PER을 "예상 순이익" 기준으로 설명했다. 아울러 답변에 **한자·가나가 섞이면 고치지 않고 오류를 알려 한 번 다시 생성**하며, 재생성도 섞이면 답하지 않는다(실측 "주가가一株당 순이익"). ⑥ [지표 발음 표기] '맥디'→MACD, '알에스아이'→RSI를 분류기·파서 `_compact` 양쪽에서 정규화한다(종목·ai_model 오인 방지).

**FR-STR-023e** [설정값 상한·타당성 방어, 2026-07-20] `enforce_strategy_minimums`(FR-STR-023c의 하한 방어와 대칭)는 상한·타당성도 강제해야 한다. ① 손절/익절/트레일링/MDD 비율이 100%를 초과하면(매수 포지션 손실률 한계 -100%) 반영하지 않고 안내한다. ② 수수료·슬리피지가 상식 상한(10%)을 넘으면 기본값(0.015%/0.05%)으로 복원하고 안내한다. ③ 수수료·거래세·슬리피지보다 작은 극소 손절/익절 폭은 경고를 남긴다(무언 드롭 금지). ④ [백테스트 창 = 보유 데이터 구간, 2026-08-02 개정] 백테스트 창은 `DATA_FLOOR_DATE`(1996-01-01) ~ `data_ceiling_date()`(오늘) 안이어야 하며, 벗어나는 방향에 따라 처리가 다르다(`enforce_backtest_window_bounds`). (a) **시작일만 데이터 이전** — 종전대로 날짜를 유지하고 커버리지 안내만 남긴다(엔진이 가용 구간부터 시작). (b) **종료일이 미래** — 종료일을 오늘로 **절단**하고 알린다. '2035년까지'의 실제 의도는 "가능한 데이터까지"이고, 절단하지 않으면 엔진은 조용히 오늘까지만 돌리는데 요약 카드·결과 배지는 요청한 날짜를 보여줘 **화면과 실행이 어긋난다**(FR-STR-023d의 '화면에 보이는 기간이 곧 실행되는 창이다'와 같은 계약). (c) **창 전체가 데이터 밖**(전부 미래이거나 종료일이 1996년 이전) — `backtest_window_is_empty`가 참이면 창을 **버리고** 기간을 다시 묻는다(초기 자금 상한과 같은 계약: 값 폐기 + `reask_fields`로 explicit provenance 제거 → 되묻기 게이트가 재질문). 이 검사가 없으면 요청이 그대로 통과해 사용자가 전략을 완성하고 실행 버튼을 누른 **뒤에야** 엔진의 "분석 가능한 유효한 데이터가 없습니다" 예외로 알게 된다. 상한 정본은 파케이 조회가 아니라 '오늘'이다 — 파싱 경로에 파일 I/O를 넣지 않으며, 오늘과 마지막 거래일(주말·장 마감 전) 사이의 차이는 엔진이 흡수한다(없는 날짜는 행이 없을 뿐). 설정 패널(`BacktestConfig`)의 '직접 입력' 날짜도 같은 경계를 `min`/`max`로 걸고 벗어나면 실행을 막는다. ⑤ `max_positions`는 스키마 상한(`le=100`)을 넘는 입력("500종목")이 ValidationError로 파싱 전체를 실패시키지 않도록 `_clamp_max_positions` 검증기가 범위로 클램프한다. 모순 필터(PER ≤10 AND PER ≥20)는 검증 agent(`_validate_logical_conflicts`, `LOGICAL_CONFLICT`)가 검출한다. ⑥ [초기 자금 상한 100억원, 2026-08-02] 초기 자금이 `MAX_INITIAL_CAPITAL`(100억원)을 초과하면 **보정하지 않고 값을 버린다**(`enforce_initial_capital_bounds` — 하한 미만은 종전대로 하한으로 클램프). 상한으로 깎아 맞추면 사용자가 말한 적 없는 금액을 시스템이 확정하는 것이고, 그대로 두면 백테스트가 무의미해진다 — 1회 매수 금액(초기 자금 ÷ 최대 보유 종목 수)이 전일 거래대금의 `liquidity_limit_pct`(기본 10%)를 넘으면 엔진이 그 종목의 진입 신호를 통째로 지우므로(`engine/loader.py::check_liquidity`), 자금이 커질수록 전 종목이 "유동성 기준 미달(거래대금 부족)"로 빠진 빈 결과가 나온다(2026-08-02 사용자 보고: 100조 · 최대 12종목 → 1회 매수 8,333억 → 통과에 필요한 전일 거래대금 8.3조/일 → 전 종목 제외). 값을 버린 뒤에는 **provenance(`explicit_fields`)의 `initial_capital`도 함께 떼어내** 되묻기 게이트가 다시 묻게 한다(`main._drop_rejected_provenance`) — 기록만 남으면 되돌아온 기본값 1천만원이 사용자 확정으로 판정돼, 설정하지 못했다는 안내를 읽고도 말한 적 없는 금액으로 백테스트가 실행된다(FR-STR-019k와 같은 계약). 파생 상태(`field_states`)도 함께 무효화해 떼어낸 provenance로 재계산한다. 설정 패널(`BacktestConfig`)의 직접 입력도 같은 상한을 걸어 실행 버튼을 막고 안내한다(대화 레인만 막으면 패널이 그대로 우회로가 된다). 상한값 자체(100억)는 허용한다.

**FR-STR-019f** [수정 경로 결정성·환각 방어, 2026-07-20] 완성된 전략의 수정 요청은 다음을 보장해야 한다. ① [지표 삭제] "RSI 조건 빼줘"는 언급된 지표의 진입/청산 신호만 제거하고 다른 필드(펀더멘털 필터·리스크)를 보존한다(`_extract_signal_removals` — LLM 수정이 요청과 반대로 다른 조건을 지우던 사고 방지). ② [전면 재작성] "완전 다르게 해줘"처럼 정보 없는 재작성 요청은 임의의 새 전략을 만들지 않고 방향을 되묻는다(`full_rewrite_clarification`). ③ [패치 환각 게이트 — 출처 대조, 2026-07-26 개정] LLM 인터프리터(primary 모드)가 낸 패치 중 발화에 근거가 없는 패치는 환각으로 거부한다(`strategy_conversation/primary.py::_patch_provenance_supported` — 후속 질문 "다른 예는 없어?"에 손절·리밸런싱·날짜가 임의 주입되던 사고 방지). 판정은 원문 어휘 스캔이 아니라 **대조**다(nl_interpretation_contract § 3-1 (b)): (i) LLM이 `PatchOp.source_text`로 인용한 원문 조각의 실재 확인(표기 정규화 후 포함), (ii) 패치 수치와 입력 수치의 대조(단위 환산 포함), (iii) 지정 종목의 해석 가능성(마스터 조회). 전량 환각이면 전략을 유지하고 미해석 안내로 응답한다(원문 정규식 질문 판정·레거시 fast-path 상담은 계약 위반이라 제거). **거부 사유가 (iii)일 때 안내를 가른다(2026-08-29 개정)** — 패치 값이 발화에 그대로 실재하는 이름이면 모델이 지어냈을 수 없으므로(구 사명·미등록·오타), '전략 변경으로 해석하지 못했다'가 아니라 **그 이름을 찾지 못했다**고 알린다(`_unresolvable_symbol_names` — LLM 출력과 원문의 포함 대조이며 의미 해석이 아니다). 실측 사고: 구 사명 '제이콘텐트리'(현 콘텐트리중앙 036420)가 마스터에 없어 환각으로 판정돼 종목 추가 요청이 무변경+미해석 안내로 끝났다 — 사용자는 분명히 종목을 말했는데 원인을 알 방법이 없었다. 상장이 유지되고 종목코드도 같은 구 사명은 registry가 해석한다 — 손으로 적지 않고 KRX 월별 전종목 스냅샷(2000-01~ MDCSTAT01501) 대조로 전수 수집하며(`backend/scripts/build_stock_name_history.py` → `data/stock-name-history.json`), 모호한 이름(지금 다른 상장사가 쓰는 이름·두 코드가 나눠 쓴 이름·3자 미만)은 등재하지 않는다(무매칭이 오해석보다 안전). 남는 미등록 이름은 이 안내로 원인을 드러낸다. **구 사명으로 담긴 종목은 이름이 바뀌었다는 사실을 알린다(2026-08-29 사용자 요청)** — 요약 카드에는 현재 등록명만 뜨므로, 정본 표기로 조용히 바꿔치기하면 사용자에게는 엉뚱한 종목이 담긴 것으로 보인다(`_renamed_symbol_notices` — 생성·수정 두 레인 공통, LLM이 종목명으로 낸 짧은 문자열만 대상이라 테마 전개로 따라 들어온 종목에는 붙지 않는다). **판정 단위는 필드가 아니라 조건 하나다(2026-07-31 개정)** — 같은 조건 객체를 겨냥한 형제 패치(`/entry_conditions/0/{factor,operator,value}`)는 지표를 통째로 갈아끼우는 한 덩어리의 수정이므로 `_patch_group_key`로 묶어 함께 판정하며, 그룹 안에 출처가 확인된 패치가 하나라도 있으면 전부 수락한다(근거 없는 그룹은 그대로 거부). 필드 단위로 따로 판정하면 인용이 한 글자 어긋난 패치만 거부돼 **LLM이 제안한 적 없는 상태**(`ma_crossover <= 50`)가 만들어지고 검증이 연산자 오류로 폴백해 요청이 통째로 사라진다(실사례: "매주조건을 per 50이하로 변경해줘" → LLM이 인용을 '매우조건을'로 오기 → factor 패치만 거부). **인용은 수치 대조를 대신 통과시키지 않는다(2026-08-02 개정)**: (i)의 인용이 실재하더라도, 인용문에 숫자가 있고 패치 값의 숫자와 **10의 거듭제곱 배수**만큼 어긋나면 그 인용은 근거가 아니라 값이 틀렸다는 증거이므로 수락하지 않는다(`_quote_contradicts_value` — 입력 해석이 아니라 LLM 출력 두 조각의 대조다). 실측 사고 2건이 모두 정확히 10배였다: "3억원"→`value=30000000`(3천만원), "1000억원"→`value=10000000000`(100억원, 수치 재요청 1회 후에도 동일). 후자는 인용이 실재해 게이트를 통과했고, 값이 공교롭게 초기 자금 상한(100억)과 같아 FR-STR-023e ⑥의 상한 안내도 뜨지 않은 채 조용히 확정됐다. 판정을 10의 거듭제곱으로 좁히는 이유는 단위 환산에 하나로 정해지지 않은 관례가 있기 때문이다 — "최근 3개월"을 인터프리터는 `lookback_days=90`(달력일), 환산표는 63(거래일)으로 잡으며 둘 다 옳다. 값 안의 `source_text`는 수치 집계에서 제외한다(인용은 원문 조각이라 언제나 입력의 숫자를 포함해 자기 자신과 대조되면 검사가 침묵한다 — `recall_validator._reflected_numbers`와 같은 계약). 자릿수가 어긋난 패치가 전부 거부되면 전략은 무변경으로 유지되고 미해석 안내가 나가며, 해당 설정은 explicit provenance가 붙지 않아 되묻기 게이트가 다시 묻는다. 아울러 factor가 교체된 조건에 남는 이전 지표의 파라미터는 `conversation/patch_applier.py::_drop_stale_parameters`가 registry 기준으로 떨어낸다(LLM 출력에 대한 결정론 정규화 — 남겨두면 "'PER'에 알 수 없는 파라미터 short_period"로 같은 폴백이 재발). **③-1 [생성 턴 조건 출처 대조, 2026-08-14]** 같은 출처 인용 대조를 **새 전략 생성 턴의 조건**에도 적용한다(`_drop_fabricated_conditions`) — 인터프리터가 프롬프트 예시 코퍼스의 조건("거래대금 50억 원 이상")을 인용문까지 지어내 사용자가 말하지 않은 조건을 조용히 추가하는 것을 전수 예시 검증(81개)에서 재현했다. 인용(`source_text`)이 입력에 실재하지 않는 조건은 빼고 안내한다. 단 인용 전체 포함이 실패해도 **4자 연속 조각**이 입력에 있으면 통과시킨다 — LLM이 인용을 가볍게 다듬는 경우(조사 생략·어순 변화)에 진짜 조건을 오살하면 이 가드가 막으려는 조용한 소실을 스스로 일으키기 때문이다(완전 조작 인용은 4자 조각조차 공유하지 않는다). 인용이 없는 조건은 대조 불가이므로 건드리지 않고 완결성 검증의 되묻기에 맡긴다. **랭킹 거울 껍데기는 이 대조에 앞서 안내 없이 걷는다(2026-09-19)** — 인터프리터가 "PER, PBR, EV/EBITDA가 낮고"를 지표별 값 없는 조건("PER이 낮은", 방향 연산자만)으로 쪼개면서 같은 지표를 종합 점수 랭킹에도 내면, 쪼갠 인용은 입력에 없어 랭킹이 이미 반영한 조건에 '확인되지 않아' 거짓 안내가 붙었고(3줄), 검증기의 거울 정리는 `operator is None`만 봐 "EV/EBITDA 기준값?"을 되물었다. 판정은 `capability_validator.ranking_mirrored_by`(값 없음 + 랭킹 방향과 비충돌, 랭킹 자리에 낸 조건 지표는 `_RANKING_CANONICAL`로 같은 개념 대조)로 두 곳이 공유하며, 걷는 조건의 인용이 다른 지표 이름이면(FCF Yield→FCF 마진) `carry_approximation`이 인용을 랭킹으로 옮겨 검증기 바꿔치기 규칙이 미지원으로 알린다(조용한 대체 금지). 회귀 `tests/test_ranking_mirror_conditions.py`. 아울러 **온톨로지 선언이 '매도 신호'인 개념**(`concept.dead_cross` 등)을 인터프리터가 `entry_conditions`에 앉히면, 청산이 비어 있는 경우에 한해 선언대로 청산 레인으로 옮긴다(`_fill_deterministic_condition_params` ③ — 연산자 덮어쓰기와 같은 선언 기반 정규화이며 원문을 읽지 않는다). "골든크로스 매수, 데드크로스 매도" 예시에서 명시한 매도 규칙이 사라지고 진입에 동일 매수 신호 2개가 남은 채 "언제 팔까요?"를 되묻던 사고의 방어선이다(프롬프트 예시 3-0-1이 1차 방어이나 temperature 0에서도 배치가 흔들려 고정되지 않았다). 인용에 매수 계열 표기가 있으면(역발상 진입) 옮기지 않는다. ④ [내부명 비노출] 미지원 안내 문구에 내부 식별자(`strategy_evaluation` 등)를 노출하지 않고 사람이 읽는 라벨로 치환한다(`_humanize_features` — 매핑된 내부명만 대상, FCF·technical.beta 등 사용자 어휘는 유지). ⑤ [LLM 수치 드리프트 교정 — 기본 비활성, 2026-07-26 개정] 결정적 추출 보정(`engine.nl_parser._apply_prompt_overrides`)은 기본값 off다(FR-STR-019j — 원문 정규식이 LLM 해석을 덮어쓰는 것은 계약 위반). 수치 드리프트는 수치 반영 대조(recall_validator)→LLM 재생성이 담당하며, 롤백은 `STRATEGY_PROMPT_OVERRIDE_MODE=on`. ⑥ [값 없는 수정 요청 3단 되묻기, 2026-07-24] 바꿀 내용이 불완전한 수정 요청은 수정 파싱으로 보내지 않는다 — LLM diff가 전부 null이라 무변경 전략만 조용히 재렌더링된다. 프론트 결정 레이어(`conversationDecision.ts` `MODIFICATION_CLARIFICATIONS`)가 구체도 순서로 결정적으로 가로채 되묻는다. (a) **필드 층**: 필드는 언급했지만 값이 없는 발화("손절 바꿔줘", "리밸런싱 주기 바꿀 수 있어?")는 그 필드의 값 칩(손절/트레일링/MDD/종목 수/보유기간/리밸런싱/초기자금/백테스트 기간 — 익절은 기존 `buildTakeProfitPercentagePrompt`가 담당)으로 되묻는다. 값 칩은 완결 지시문이라 재전송 시 가로채지지 않고 백엔드 결정론 fast-path(`_modify_rule_based`)가 처리하며, 칩별 추출 계약은 `STRATEGY_UI_SETTING_SUGGESTIONS`(백엔드 테스트)가 검증한다. (b) **영역 층**: 영역만 언급한 발화("진입 신호를 바꾸고 싶어")는 그 영역의 옵션 칩으로 되묻는다. (c) **catch-all 층**: 영역·필드도 없는 메타 요청("조건을 변경할 수 있어?", area=`condition`)은 영역 칩(진입 신호/청산 신호/유니버스/포트폴리오/리스크)으로 되묻고, 영역 칩은 재전송 시 (b)로 다시 가로채지는 2단계 플로우라 백엔드에 도달하지 않는다 — 백엔드 칩 계약 테스트(`test_strategy_ui_exposes_only_suggestions_covered_by_backend_contract`)가 이 5칩을 프론트 가로챔 예외로 명시한다. 값이 이미 명시된 발화(`explicitPattern`, catch-all은 `EXPLICIT_CONDITION_TARGET_PATTERN`)와 삭제/유지 발화는 기존 수정 경로에 맡긴다. 값 칩이 fast-path에 남으려면 `_MODIFY_FIELD_CUES`가 칩 어휘를 커버해야 한다(매월/매년 등 주기 어휘 누락으로 LLM에 새던 것 보정). (d) **종목 변경 의향** [2026-07-26]: 구체 종목명 없는 대상 종목 교체 의향("종목을 변경/교체 할 수 있나?", "다른 종목으로 하고 싶어", `missing_target_symbols_change`)은 **칩 없이**(suggestions 빈 배열 — 특정 종목 선택지를 내밀면 추천 소지, 사용자 결정) 채팅 입력 안내만 응답한다("삼성전자만으로 백테스트해줘"·"현대약품은 빼줘"·"반도체 관련주로 바꿔줘" 예시 포함 — 교체·제외·추가는 백엔드 수정 경로가 자유 발화로 처리, FR-STR-068 ⑥). 구체 종목명이 함께 온 발화("종목을 삼성전자로 바꿔줘")는 topicPattern의 어미 인접성(종목+조사+동사 직결)이 깨져 가로채지 않고 수정 파싱으로 통과한다. 또한 결정론 즉답(respond) 턴은 현재 전략이 있으면 '현재까지 이해한 전략입니다' 요약 카드(`builderPresentation`)를 답변과 항상 함께 표시한다(사용자 지시 — 안내가 전략 맥락 없이 떠 있지 않도록).

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

**FR-SA-013** [종목 선정 범위 — 지정과 후보군의 구분, 2026-07-31] 지정 종목 목록에는 성격이 다른 두 가지가 같은 모양으로 저장된다 — ① 사용자가 직접 지목한 종목 ② 테마·개념 조회가 채운 관련 상장사. 이를 구분하지 않고 "지정 종목이 있으면 선정 없음"으로 처리하면 **후보군을 지정으로 오인해 사용자가 말한 선정 기준이 조용히 사라진다**(실측: "이차전지 관련주 중 최근 60일 수익률 상위 10종목" → 랭킹 비활성·보유 수 36으로 36종목 전부 매수. 사용자가 말한 랭킹과 종목 수가 동시에 증발). ① **판정은 저장하지 않고 계산한다**(FR-SA-011 ② 파생 상태와 같은 계약) — 값에서 온전히 유도되며, 저장하면 테마 교체 시 함께 갱신해야 하는 두 번째 진실이 생긴다. ② **범위 3종**: 지정 종목 없음=`UNIVERSE`(유니버스 전체가 선정 대상), 테마 유래이면서 선정 기준(랭킹)이 있으면 `CANDIDATE_POOL`(그중에서 선정 — 랭킹·보유 수 유지), 그 외 `EXPLICIT`(전부 매수·선정 없음). ③ **테마 유래여도 선정 기준이 없으면 `EXPLICIT`이다** — 무엇을 기준으로 자를지 아무도 말하지 않았으므로 임의로 상위 N곳만 남기지 않는다(테마 유니버스 절단 금지 결정 유지). 구분의 근거는 종목의 출처 기록(`theme_universe`)이며 새로 판정하지 않는다. **[2026-09-16 개정 — '선정 기준'의 범위]** ③의 '기준'은 랭킹 하나가 아니라 **랭킹·보유 종목 수·비율 선정** 셋 중 하나다. 종전 규칙은 "아무도 자를 기준을 말하지 않았다"를 전제했는데, 사용자가 **보유 종목 수를 직접 말했다면** 그 전제가 성립하지 않는다 — 실측 사고: "전쟁 관련주 중 … 골든크로스 매수 … **최대 5종목**"(랭킹 미언급)이 66종목 전부 균등 매수로 나갔다(컴파일된 전략에는 `max_positions=5`가 남아 있는데 `strategy_converter`가 `max_positions=len(target_symbols)`·`position_size_pct=100/N`으로 덮었고, 요약 카드도 '지정 종목 66개 균등 투자'로 바뀌어 사용자가 말한 값이 질문도 안내도 없이 사라졌다). 동점 처리는 새로 만들지 않는다 — 신호 충족 종목이 빈 자리보다 많은 날은 유니버스 전략에서도 생기고 엔진이 기본 순서로 담으며 결과 로그에 경고를 남긴다. 후보군 경로는 같은 처리를 그대로 탄다. **provenance**: 랭킹·비율은 미언급이면 null이라 값의 존재가 곧 사용자 답변이지만, 보유 수는 기본값 10이 물질화되므로 값만으로는 '10이라고 말했다'와 '아무 말 없었다'가 같아 보인다 — 컴파일러가 `StrategyIntent.portfolio.selection_count is not None`을 `ParsedStrategy.max_positions_explicit`에 남긴다(LLM이 채우지 않는 내부 표식). **라운드트립**: 디컴파일러는 `selection_count`에 물질화된 값을 채울 수밖에 없어(비우면 수정 턴마다 사용자가 말한 종목 수가 10으로 되돌아간다) 재컴파일이 이 표식을 복원하지 못한다. 그래서 수정 레인은 `primary.NON_ROUNDTRIP_FIELDS`(description·entry_filters·max_positions_explicit)로 **이월**하고, 이번 턴이 실제로 바꿨는지는 패치 경로로 판정한다(`explicit_fields_from_patches`가 같은 이유로 spec 대신 경로를 보는 것과 동일한 계약). 회귀: `test_selection_scope.py` 4건 추가·`test_position_count_provenance_is_not_recoverable_by_roundtrip`·프론트 미러 4건. ④ **표시가 실행과 일치해야 한다** — 배지가 "지정 N개 균등 투자"라고 하는데 엔진은 랭킹으로 M개만 사면 화면이 거짓말을 한다. 프론트의 범위 판정은 백엔드 정본의 미러이며, 규칙 변경 시 양쪽을 함께 고친다. ⑤ **`goal`(스펙 § 6 잔여)은 구현하지 않는다** — 사용자 원문(`description`)과 빌더의 전략 유형이 이미 그 자리를 차지하고 있고 구조화된 목표를 읽을 소비자가 없다. 유일한 소비자 후보였던 질문 우선순위 동적화는 하지 않기로 결정됐다. 회귀: `backend/tests/test_selection_scope.py`, `lib/strategy-summary.selection-scope.test.ts`.

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

**FR-SA-023-1** [백테스트 기간 출력 형태 — 옮겨 적기, 2026-09-07] FR-SA-023 ④의 "버킷 밖 연수는 명시 날짜 창"은 정책으로는 맞았지만 **LLM에게 조건 분기를 시키는 프롬프트 규칙**("넷뿐, 그 밖은 오늘 기준으로 계산해 start_date/end_date")으로 구현돼 있었다. 실측(09-07): 되묻기 답 "10년 데이터를 사용해줘"에 9B(08-26 통과)·nemotron-120b(09-06 전환 후) 모두 `period="full"`을 냈다(7회 중 6회). 합법 버킷이라 Literal 검증·인용 대조 게이트 어느 것도 잡지 못하고 카드에 '전체'가 확정됐다. 규칙 문구를 늘리지 않고 **출력 형태를 바꾼다**: 인터프리터는 사용자가 말한 기간을 `<N>y`/`<N>m`/`full`로 옮겨 적기만 하고(프롬프트 5.0), 버킷 판정·날짜 창 변환·일수 근사(달력일 ±31)는 `BacktestSpec._normalize_period`(결정론)가 한다. 7년 초과 일수→`full`, 300일→`1y`로 올리던 구 매핑은 사용자가 말한 적 없는 창이라 폐기하고, 최소 기간(1년) 미달은 값을 버려 슬롯이 빈 채 되묻기로 오르게 한다. 같은 사고의 둘째 겹: 수정 턴 재계획이 이전 턴 에코(`previous_explicit_fields`)만 받아 방금 답한 슬롯을 빈 칸으로 보고 재질문했다(날짜를 정확히 답해도 재발) — 칩 확정 레인처럼 이번 턴 패치로 판정한 명시 필드를 재계획 **전에** 계산해 넘긴다. 관찰: LLM span 이름은 `llm_backend.active_chat_model`(실제 레인 모델)로 찍는다 — Ollama 슬롯명으로 찍혀 OpenRouter 모델의 드리프트를 로컬 9B 회귀로 오독했다. 게이트: 프롬프트·LLM 레인/모델 변경 시 `scripts/qa_free_input.py modify/fill`을 바뀐 레인으로 돌린다(CLAUDE.md 필수 규칙).

**FR-SA-023-3** [슬롯 답변의 수치 소실 차단, 2026-09-10] 되묻기 답변이 **설정 슬롯**을 가리키는데도 값이 사라지면 안 된다. 실측(캐시 우회 반복 호출): '20일 보유 후 청산' 0/4, '한 달 지나면 정리' 1/4에서 `portfolio.hold_period_days`가 비었다. 원인은 셋이고 레인이 다르다. ① **해석 드리프트** — 'N일 보유'의 N을 이동평균 기간으로 읽어 `ma_crossover` 청산을 만든다. 프롬프트의 보유 기간 항이 이 오독을 직접 금지한다('N일 보유의 N은 이동평균 기간이 아니다'). 지표 기반 청산('20일선 이탈 시 청산')은 종전대로 조건으로 남는다(대조군 3/3). ② **환각 게이트의 과잉 거부** — 숫자 없는 인용에 숫자 값을 실은 패치는 거부하는데(초안 숫자 복사 방지, 2026-08-10), '한 달'처럼 **한글 수사로 말한 기간**은 숫자 앵커가 서지 않아 정당한 환산값(1개월=21거래일)이 함께 버려졌다. `recall_validator`의 앵커 추출이 한글 수사 기간 표기를 숫자 토큰으로 인식한다 — 귀속은 하지 않는다(모듈 § 3-1 계약 유지). ③ **지어낸 factor 아래의 슬롯 값** — 이름은 매번 달라도(`time.days_held`·`concept.time_based_exit`) 파라미터 키는 스키마 이름 그대로다. `StrategySpec`의 스칼라 슬롯 흡수는 factor 이름뿐 아니라 **파라미터 키**로도 성립한다(지표 파라미터 이름과 겹치지 않는다). ④ 미해석 factor 안내는 사용자 표현을 인용하고, 인용이 없으면 네임스페이스 접두·영문 경로 꼴 이름을 일반 표기로 가린다(내부명 노출 금지). **측정 계약**: `/strategy/parse`는 (프롬프트·초안·질문·prompt_version) 키로 프로세스 내 캐시를 쓰므로, 같은 입력의 반복 측정은 캐시 키를 비틀어야(요청 `model` 접미사) 실측이다 — 비틀지 않으면 첫 응답의 반향을 N회로 오독한다.

**FR-SA-023-2** [초기 자금 출력 형태 — 옮겨 적기, 2026-09-10] 금액도 기간(FR-SA-023-1)과 같은 계약이다. 종전 프롬프트 11-2는 환산표(1억=100000000 …)를 외우게 했고, nemotron-120b는 **문장 안에서는 맞히고 금액만 던진 되묻기 답변에서 틀렸다**(실측 09-10: '초기자금 2억5000만원으로 백테스트' 3/3 정확, 되묻기 답 '2억5000만원' 3/3이 25,000,000 — 10배 축소). 이 오차를 잡을 안전망도 없었다: 원문 정규식 보정은 계약상 기본 off이고, 10배 가드(`_quote_contradicts_value`)는 인용 앵커를 토큰별로만 봐 '2억'·'5000만'은 알아도 합산값 2.5억을 후보로 갖지 않는다. ① **인터프리터는 사용자가 말한 금액 표기를 그대로 옮겨 적는다**('2억5000만원'·'$10,000') — 환산은 하지 않는다. ② **환산은 결정론 코드**(`BacktestSpec._normalize_amount`, before 검증기)가 한다 — 조·억·천만·백만·만을 자리마다 합산하고, 수사 없는 단위('천만원')는 1로, 한글 수사(일~십)는 숫자로 읽으며, 달러·맨숫자·쉼표 표기와 K/million 접미는 숫자 그대로 취한다(통화 해석은 엔진 몫). ③ **풀 수 없는 표기는 값을 지어내지 않는다** — 원값을 그대로 두어 스키마 검증이 실패하게 하고, 패치 경로는 제외+안내로 흐른다. ④ 앞자리 숫자만 떼는 공용 `_coerce_number`는 금액에서 분리한다(그대로 두면 '2억5000만원'이 2가 된다). 회귀: `test_strategy_conversation.py`(환산 17종+거절), `test_nl_parser_overrides.py`(롤백 경로의 '억+만' 배수 버그 — '천' 없이도 천만을 곱해 '2억5000만원'이 502억이 됐다).

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

**FR-USR-001b** [이메일 가입 보안, 2026-08-20 구현] 이메일 가입은 인증번호로 이메일 소유를
증명해야 완료된다. `/api/register/request-code`가 6자리 인증번호를 메일로 발송하고(SHA-256
해시만 `EmailVerification` 테이블에 저장, 10분 만료), `/api/register`가 코드 검증(타이밍세이프
비교, 시도 5회 상한) 후 계정을 생성하고 로그인 쿠키를 발급한다(자동 로그인). 보안 장치:
가입 여부 비노출(이미 가입된 이메일에도 동일 응답 — 대신 "이미 가입됨" 안내 메일 발송),
레이트리밋(IP 시간당 20회/가입 시도 30회, 이메일당 시간당 5회, 재발송 60초 쿨다운 — 쿨다운은
가입 여부 분기 전에 소비해 응답 차이를 없앤다), 비밀번호 정책(8~72자·영문+숫자), 만 14세
이상·약관 동의 필수. SMTP 미설정 시 개발은 콘솔 출력, 프로덕션은 발송 실패(Fail Fast — 인증
없는 가입이 조용히 열리지 않는다). 레이트리미터는 인메모리(단일 박스 배포 전제). UI는
`/register`(2단계) + `/login`(이메일 로그인). 상단 내비게이션의 로그인 버튼은 OAuth를 바로
시작하지 않고 선택 모달(Google로 시작하기 / 이메일로 시작하기)을 연다(2026-08-20, 전략연구소
진입 모달도 동일 선택지).
**테스트용 한시 기능** — 킬 스위치 `EMAIL_SIGNUP_ENABLED=off`(2026-08-20)로 가입·이메일 로그인
페이지는 랜딩 리다이렉트(종전 동작), API는 404로 닫힌다. 기본값 켜짐, 요청 시점 판정(재빌드 불필요).
`EMAIL_SIGNUP_VERIFICATION=off`(2026-08-20, 테스트 기간 사용자 지시)면 인증번호 단계를 건너뛰고
1단계에서 바로 가입한다 — 비밀번호 정책·레이트리밋·중복 확인·약관 동의는 그대로. env 삭제 시 인증 요구 복원.
**2026-09-14 off 전환(사용자 지시 "이메일 로그인 시스템을 끄자, 지우지 말고, 구글 로그인만")** — 로컬·prod `.env`에 `EMAIL_SIGNUP_ENABLED=off`. 같은 날 킬 스위치 사각지대 2곳 보완: `/api/login` 이메일·비밀번호 분기도 404(페이지만 막고 API가 열려 있었다 — Google 토큰 분기는 그대로), 로그인 선택 모달(상단 내비·전략연구소 진입) 두 곳의 "이메일로 시작하기" 버튼은 루트 레이아웃이 내려 주는 `EmailLoginOptionProvider` 컨텍스트로 숨기고 부제를 "Google 계정으로 시작하세요"로 바꾼다. 코드·테이블은 보존, env 줄 삭제로 복원.

**FR-USR-001c** [게스트(테스터) 계정, 2026-09-14 구현] 운영자가 발급한 아이디(`guest_`+네 자리)와
비밀번호(5자)로 `/guest`에서 입장할 수 있어야 한다. 게스트는 별도 테이블 없이 User 행이며
이메일이 합성 도메인(`@guest.nullstock.im`)이라는 점으로만 구분한다. 기본 플랜은 PREMIUM(결제·갱신
없음). `POST /api/guest/login`은 아이디를 합성 이메일로만 조회하고(일반 회원 이메일 통과 불가)
레이트리밋(IP 15분 30회·아이디 15분 10회)으로 짧은 비밀번호를 보호하며, 쿠키 계약은 `/api/login`과
같다. 관리자 콘솔 Users 탭은 게스트/일반 회원 필터와 GUEST 배지로 게스트 활동(전략·계좌·백테스트
사용량·최근 로그인)을 본다. 발급은 `scripts/create-guest-accounts.ts`. 게스트는 본인 계정 삭제와
결제·플랜 변경(무료 전환 포함)을 할 수 없다 — 서버가 403으로 거부하고, 요금제·설정 화면은 버튼을
잠근 채 안내문을 먼저 보여준다(구독 없는 PREMIUM이라 무료 전환이 곧 회복 불가한 강등이기 때문).
**입장 링크(2026-09-17)**: 발급 스크립트는 아이디·비밀번호 대신 입장 링크 `https://www.nullstock.im/guest#<아이디>.<비밀값>`을
출력한다. 비밀값은 32바이트 난수(base64url 43자)이며 그 계정의 비밀번호로 bcrypt 저장한다(테이블·서명 키 추가 없음).
코드는 프래그먼트(`#` 뒤)에 두어 서버 요청·접속 로그·Referer에 실리지 않고, `/guest` 화면이 읽자마자 주소창에서 지운 뒤
`POST /api/guest/login {invite}` 본문으로만 보낸다. 링크 입장에는 아이디별 레이트리밋을 걸지 않는다(네 자리 아이디에
틀린 비밀번호를 넣어 링크 받은 사람을 잠그는 공격 차단, IP 제한은 유지). 링크 폐기=비밀번호 재발급 또는 계정 삭제.
아이디·비밀번호 폼 입장도 그대로 동작한다.
**이용 기한(2026-09-17)**: `User.accessExpiresAt`(nullable, null=무기한)이 지난 계정은 status가 ACTIVE여도 로그인(`/api/guest/login` 403
"이용 기간이 끝난 계정입니다.")과 기존 세션(`getCurrentUser`·`assertActiveUser`·대시보드·요금제 페이지·리서치 프록시) 모두 거부한다.
판정 정본은 `lib/accountAccess.ts::isAccountUsable`이며 요청 시각에 비교하므로 예약 작업 없이 그 시각부터 막힌다.
2026-09-17 발급한 입장 링크 계정 20개(id 30~49)는 2026-10-01 00:00 KST 만료. 마이그레이션 `20260917000000_add_user_access_expires_at`은 prod 적용 완료.



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

**FR-STR-076** [사용자용 대화 로그 — 계정별 저장·30건 LRU, 2026-09-14] 전략연구소는 로그인 사용자의 지난 대화를 **계정별로 서버(DB)에 저장**하고 화면 왼쪽 목록에서 다시 열거나 지울 수 있어야 한다(`StrategyChatLog`, `/api/strategy-chat-log`). ① 목록·저장·삭제는 세션 사용자로만 묶이며 비로그인은 401이다 — 다른 계정의 대화는 어떤 경로로도 보이지 않는다(NFR-SEC-006·010). ② 계정당 최대 30건이고, 초과분은 **가장 오래 쓰지 않은 대화부터 지운다(LRU)**. "쓴다"는 대화가 진전된 것(메시지 수 변화)이며 열어 보기만 한 대화는 순서를 바꾸지 않는다. ③ 제목은 서버가 첫 사용자 발화의 첫 줄을 표시 길이만 잘라 만든다(원문 의미 판정 없음). ④ 저장은 갱신이 멎은 뒤 한 번 보내고, 상한(2,000,000자)을 넘는 스냅샷은 백테스트 결과를 떨어뜨려 보낸다. ⑤ 브라우저에는 진행 중 대화 스냅샷만 남으며 계정 격리 규칙(NFR-SEC-010)을 따른다. 회귀: `lib/server/strategyChatLog.test.ts`, `app/api/strategy-chat-log/[sessionId]/route.test.ts`, `app/analytics/new/page.chatLog.test.tsx`.
**FR-STR-077** [시총 규모 표현 '중형주' = 시가총액 밴드 + 예시 게이트의 '미지원 안내=치명' 계약, 2026-09-14] ① '소형주'·'중소형주'는 시총 상한, **'중형주'는 시총 하한·상한 두 조건**이며 값은 항상 사용자에게 되묻는다(기본값 확정 금지). LLM이 이 규모 라벨을 sectors·unsupported_features에 내더라도 시스템은 그 **라벨(LLM 출력)**을 시가총액 조건으로 정본 매핑한다(`_normalize_size_class_labels` — 원문을 읽지 않는다). 범위를 이미 말했으면("3000억 이상 2조 이하 중형주") 라벨만 걷어내고 조건은 그대로다. ② 시총 밴드는 되묻기 큐·칩·필터 병합에서 **한쪽 방향이 다른 쪽 답에 덮이거나 건너뛰어지면 안 된다**: 큐 항목은 방향(`direction`)까지 보고 기충족을 판정하고, 상한 칩은 하한 추천값보다 큰 값(2/3/5조)만 제시하며, 금액 지표(시총·거래대금)의 필터 병합은 (지표, 방향) 단위로 갱신한다. ③ '상대강도 상위 N%'의 정본은 기간 수익률 랭킹(`ranking.return`)이다 — LLM이 `technical.relative_return`을 랭킹 지표로 내면 검증기가 정규화하고, 같은 표현으로 entry에 이중 생성된 초과수익률 조건(값 0/null)은 걷어내되 "기간 수익률 랭킹으로 반영했어요"로 알린다(조용한 제거 금지). 값이 있는 초과수익률 조건은 별도 조건으로 공존한다. **[2026-09-15 보강 — 매도 슬롯]** 같은 이중 생성이 **청산** 조건으로도 나온다(prod 레인 실측 4/4: '시장 대비 수익률 상위 5종목을 매월 교체'가 랭킹으로 정상 반영되고도 `relative_return > 0` 청산 조건을 함께 냄 — "시장을 이기면 판다"는 사용자가 말한 적 없고 뜻도 뒤집힌 매도 규칙). 중복 제거가 진입·청산 두 슬롯을 모두 본다. 단 청산 슬롯에서는 **방향이 뒤집힌 것만**(`>`·`>=`·연산자 없음) 드리프트로 보고 '시장보다 못하면 매도'(`<`)는 살린다(검증기의 교차 방향×역할 모순과 같은 계약). 안내 문구는 랭킹 정본별로 고정한다 — 기간 수익률 랭킹이면 종전 문구, 시장 대비 초과수익률 랭킹이면 "'X'은(는) 시장 대비 초과수익률 랭킹으로 반영했어요"(display_name 보간은 영어 응답에 한국어가 새어 금지). 회귀 `test_relative_return_indicator.py::test_primary_prunes_inverted_relative_return_exit_beside_ranking`·`::test_primary_keeps_underperform_exit_condition`. **[2026-09-15 개정 — 엔진 v16.10]** 랭킹 자리의 `technical.relative_return`은 더 이상 기간 수익률 랭킹으로 근사하지 않는다 — 새 랭킹 지표 **`ranking.relative_return`**(엔진 `relative_return`: 종목 N거래일 수익률 − **자기 상장 시장** 지수 N거래일 수익률의 횡단면 순위, `engine/market_index.relative_return_panel`이 종목별 시장 지수 패널을 빼서 산출)로 정본 착지한다. 코스피·코스닥을 함께 담아도 종목마다 제 지수를 빼므로 정확하고, 복합 순위 합산의 구성 지표로도 쓴다. 지수가 없는 종목(미국)은 NaN → 후보 배제, 미국 유니버스에서는 조건과 같은 계약으로 검증기가 오류+제거+안내. 오전에 넣었던 '순위가 같아/가깝게 반영' 안내는 폐지. 프롬프트 6.0 랭킹 규칙에 '시장 대비 수익률 상위 N종목'→`relative_return` 랭킹을 명시('상대강도 상위'·'수익률 상위'는 종전대로 ranking.return). 회귀 `test_relative_return_indicator.py`(랭킹 정본 착지·미국 거절·지수 패널·컴파일). ④ 네임스페이스만 틀린 지표 ID(`fundamental.adx`)는 잎 이름이 유일한 **지원** 지표로 해석한다(미지원 항목은 제외 — 내부명 노출 금지 회귀 유지). ⑤ 예시 게이트(`scripts/qa_template_detect.py`)는 "지원하지 않아 전략에 반영하지 못했어요"·"조건은 전략에 반영하지 못했어요" 안내를 **치명**으로 센다 — 우리가 내보내는 예시가 그 안내를 내면 예시가 엔진 밖 개념을 약속했거나 파서가 지원 개념을 미지원으로 오판한 것이며, 근사 반영 안내("…로 가깝게 반영했어요")·값-대기 안내는 치명이 아니다. 회귀: `tests/test_qa_template_detect_verdict.py`, `tests/test_slot_clarification_chips.py`(밴드 칩·큐), `tests/test_nl_parser_overrides.py`(밴드 병합), `tests/test_relative_return_indicator.py`(랭킹 정규화), `tests/test_strategy_conversation.py`(라벨 정본 매핑·중복 제거·리스크 에코·잎 폴백).

**FR-STR-078** [거래대금 배수 지표 — 거래대금의 자기 평균 대비 비교, 2026-09-18, 엔진 v16.13.0] ① "최근 거래대금이 30일 평균보다 높은"·"거래대금이 20일 평균의 2배 이상"처럼 **억원 금액 없이 거래대금을 자기 N일 평균과 비교**하는 조건은 기술 지표 `trading_value_ratio`(당일 거래대금(종가×거래량) ÷ **직전** N일 평균 거래대금, 당일 제외, 배수 임계와 부등호 비교)로 표현해야 한다 — 거래량 급증(OBV 교차)이나 거래량 배수로 근사하지 않는다. "평균보다 높은"은 `>` 1배, 배수를 말하면 그 배수다(인터프리터 프롬프트 6.1 규칙 5-2). ② 금액 임계("거래대금 100억 이상", "60일 평균 거래대금 50억 이상")는 종전대로 `trading_value`다. ③ LLM이 옛 자리(`trading_value` + 평균 기간 `period`, 값 없음)로 내면 검증기(`capability_validator`)가 **출력 형태만 보고** 지표를 옮긴다(값·기간·연산자 불변). 금액이 인용에 있으면 금액 검산이 값을 먼저 채우므로 옮기지 않는다. ④ 조건 인용의 뜻을 어휘 정규식이 다시 읽어 지표를 바꾸는 교정은 두지 않는다(대원칙 1 — 종전 `_mentions_volume_surge` 재분류 삭제, 같은 인용에 안내가 두 줄 나가던 원인). ⑤ 근사·대체 탐지는 같은 이름('거래대금')을 공유하는 변형(금액 임계·평균 대비 배수)을 대체로 판정하지 않는다(`indicator_registry.with_same_name_variants`). ⑥ 금액도 평균 기간도 없는 거래대금 조건(해석기가 평균 비교를 기간 없이 `fundamental.trading_value`로 낸 형태 — 120B 실측 4회 중 1회)은 거래대금 비교 대상 대조(`interpreter/trading_value_check.py`, LLM)가 인용마다 금액 비교(`amount`)·자기 평균 비교(`own_average`)·판단 불가(`unclear`)를 답하고, 평균 비교면 평균 기간·배수·부등호를 인용 그대로 옮겨 적는다. 결정론은 enum·범위 확인과 지표 이동만 하며, 실패·`unclear`·범위 밖 값은 조건을 그대로 두어 금액을 되묻는다(조용한 대체 금지). '일평균 거래대금이 높은'처럼 평균 거래대금 **수준**을 말한 표현은 금액 비교다. 회귀: `backend/tests/test_trading_value_ratio_indicator.py`, `test_strategy_conversation.py::test_trading_value_average_comparison_lands_on_trading_value_ratio` 외 3건.

**FR-STR-079** [전문가형 퀀트 전략 해석, 2026-09-19, 프롬프트 6.2] 인터프리터는 FR-BT-070의 요소를 다음 자리로 옮겨야 한다. ① 12-1 모멘텀 → 수익률 랭킹 하나(`lookback_days`=252, `skip_days`=21). ② 여러 지표를 종합한 점수 → 지표마다 랭킹 항목 + 같은 `group`(점수 이름을 metric으로 지어내지 않음). ③ 변동성 역비중·리스크 패리티 → `portfolio.weighting='inverse_volatility'`(리스크 패리티는 역변동성으로 **가깝게 반영**했다고 안내), 변동성 기간을 말하지 않으면 되묻는다(칩 20/60/120일). ④ '코스피가 N일선 아래면 비중 축소/현금 보유' → `strategy.market_filter`(종목 이동평균 조건 금지). 줄일 비율을 말하지 않았으면 되묻는다(칩 0%·30%·50%, 2026-09-19 사용자 결정) — 답 전에는 값 대기 채널(`pending_conditions` '시장 국면 필터')에 올리고 엔진 요청에 싣지 않는다. 미국 지수 국면은 미지원 안내. ⑤ '손절은 적용하지 않는다'처럼 쓰지 않겠다고 말한 설정 → `strategy.declined`(항목마다 그 설정을 말한 원문 인용 필수 — 인용 없는 항목은 받지 않는다; 120B가 손절만 말했는데 익절까지 거부로 낸 실측). 미지원 보고 금지. ⑥ 'N일 평균 거래대금' → `parameters.period`. ⑦ ROIC·FCF 마진은 지원 지표(종전 미지원 안내). 결정론 정리(전부 LLM 출력끼리 또는 LLM 인용↔레지스트리 대조, 원문 미사용): 랭킹과 같은 지표의 연산자·값 없는 매수 조건 껍데기 제거(계열 `class.*` 껍데기는 인용이 부른 지원 지표 둘 이상이 랭킹에 있을 때), 랭킹 자리의 `technical.volatility` → `ranking.volatility`, 인용이 미지원 개념만 부르는 랭킹(추정치 인용으로 만든 시장 대비 수익률 등) 제거+미지원 보고, 같은 인용을 미지원으로도 보고한 랭킹 제거. 조건 누락 대조 패스(`condition_recall`)는 랭킹·국면 필터·미지원 보고가 이미 다룬 구절과 랭킹 정본의 같은 개념 조건 지표(변동성·ROC·초과수익률)를 되살리지 않고, 미지원 개념만 부르는 구절은 미지원 보고로 올린다 — 운영의 "'…'는 이동평균 조건이 아니어서…" 안내와 로컬의 20/60 골든크로스 매수 조건 둔갑이 이 경로였다. 실적 추정치(컨센서스) 상향은 데이터 원천이 없어 미지원(사용자 결정: 보류). 회귀: `backend/tests/test_quant_portfolio_features_lane.py`.

**FR-STR-080** [시장 변동성 급등 해석, 2026-09-20, 프롬프트 6.3] 인터프리터는 "시장 변동성이 급등(급격히 확대)하면 현금 비중 확대"를 종목 조건·랭킹이 아니라 `strategy.market_filter`의 `triggers`(`volatility_spike`)로 옮겨야 하며, "…이거나"로 이동평균 판정과 함께 말했으면 둘 다 넣는다. "둘 다 충족할 때만"은 `unsupported_features`로 신고한다. 급등 배수(`volatility_multiple`)를 말하지 않았으면 기본값으로 확정하지 않고 되묻는다(칩 1.5배·2배·2.5배, `engine/strategy_slots.MARKET_REGIME_VOL_MULTIPLE_CHIP_VALUES`, 2026-09-20 사용자 결정) — 답하기 전에는 값 대기 채널에 올리고 엔진 요청에 싣지 않는다. 변동성 산정 기간은 묻지 않는다(엔진이 20거래일로 계산하고 요약·결과에 표기). 이동평균 기간은 `below_ma` 판정이 있을 때만 묻는다. `triggers` 키를 빠뜨린 출력은 채워진 값 자리로 판정 종류를 정한다(형식 정규화).

**FR-STR-081** [잔차 반전 시그널 해석, 2026-09-20, 프롬프트 6.4] 인터프리터는 '수익률을 시장수익률과 섹터 평균수익률에 회귀시킨 잔차를 누적해 잔차 변동성으로 나누고 z-score로 표준화·부호 반전한 시그널 상위 N종목'을 랭킹 하나(`ranking.residual_reversal`, `lookback_days`=말한 회귀 기간, `accumulation_days`=말한 잔차 누적 기간, 말하지 않았으면 null)로 옮기고, 회귀·윈저라이즈·z-score·부호 반전을 미지원으로 보고하지 않으며, 시그널 하위 종목 매도(공매도)·달러 중립 구절만 `unsupported_features`에 남겨야 한다. 검증·컴파일(전부 LLM이 낸 구조화 값이 입력): ① 말하지 않은 파라미터는 **되묻지 않고** 기본값(60/5)으로 확정한다(사용자 결정 2026-09-20 — 다른 가격 산출 랭킹의 '산정 기간 되묻기'와 다른 계약이다). ② 허용 밖 값은 기본값으로 바꿔치지 않는다 — 검증 오류 + 컴파일 시 비움 + 허용값을 되묻는 무칩 질문. ③ '회귀 룩백 < 누적 기간'은 검증 오류. ④ 다른 랭킹에 붙은 `accumulation_days`는 오류 + 제거. ⑤ ETF 유니버스(섹터 없음)·미국 유니버스(지수 시계열 없음)·다른 순위 기준과의 합산은 오류 + 랭킹 제거 + 미지원 보고. 표시: 요약 카드 '잔차 반전 시그널 상위 (회귀 N일·누적 M일)'(값 대기 중에는 '(기간 미정)'), 매수 사유 '잔차 반전 시그널(회귀 N일·누적 M일) 상위 P%'. 회귀: `backend/tests/test_residual_reversal.py`, `app/analytics/new/strategySummary.test.ts`.

**FR-STR-082** [종목당 비중 상한 해석, 2026-09-20, 프롬프트 6.5] 인터프리터는 '종목당 비중은 N%를 상한으로'·'한 종목에 최대 N%까지만'을 `portfolio.max_weight_percent`=N으로 옮기고 미지원으로 보고하지 않아야 한다(출력 형태에 키 노출 + 규칙 1줄 — 형태에 키가 없으면 모델이 규칙이 있어도 채우지 않는다). 검증: 0 초과 100 이하가 아니면 오류 + 제거. 컴파일: `ParsedStrategy.max_position_weight_pct` → 정본 DSL(값이 없으면 키 제거 — 기존 해시 불변) → 엔진 요청 `risk.max_position_weight_pct`. 디컴파일로 왕복한다(수정 턴 보존). 표시: 요약 카드 보유 줄 '종목당 비중 상한 N%', 변경 이력 라벨 '종목당 비중 상한'. 회귀: `backend/tests/test_position_weight_cap.py`, `app/analytics/new/strategySummary.test.ts`.

**FR-STR-083** [실적 서프라이즈·섹터 상한·유니버스 필터 해석, 2026-09-20, 프롬프트 6.6] 인터프리터는 ① 'SUE와 발표일 초과수익률을 z-score로 표준화해 평균한 시그널 상위 N종목'류 서술을 `ranking=[{metric:'pead', entry_delay_days, expiry_days}]` 하나로 옮기고(SUE 계산·초과수익률·z-score·윈저라이즈·평균은 지표에 포함돼 있어 미지원으로 보고하지 않는다), ② '섹터별(업종별) 비중은 N%를 상한으로'를 `portfolio.max_sector_weight_percent`=N으로 옮긴다(**종목당 상한과 다른 칸** — 섹터·업종을 말했으면 이쪽이다), ③ '시가총액 상위 N종목 중'을 `universe.market_cap_top_n`, '최근 N일 평균 거래대금 하위 X%를 제외'를 `universe.liquidity_exclude_bottom_percent`·`liquidity_lookback_days`로 옮긴다(지수 이름을 말한 것은 markets다). 말하지 않은 값은 지어내지 않으며, 발표 자격 창의 범위 밖 값은 기본값으로 바꿔치지 않고 비운 채 되묻는다(잔차 반전과 같은 계약). ④ 이미 반영한 설정을 미지원으로 **중복 신고**하지 않아야 한다(규칙 4-1). 이 규칙은 실측에서 지켜지지 않으며(2026-09-20: `execution_timing`·`fee_rate`가 정확히 채워진 채 같은 문구가 미지원으로도 보고됐다), 출력 형태로 강제하려던 시도(설정 반영 인용 채널)는 A/B 실측에서 **기각**됐다 — 모델이 채널을 채우지 않고 체결 시점 해석만 뒤집혔다. 따라서 안내 레인이 방어한다: 잔여 미지원 안내는 **내부 식별자를 담은 보고를 안내하지 않는다**(점 있는 경로 `technical.beta`에 더해 점 없는 밑줄 식별자 `fee_rate`·`max_sector_weight_percent`까지 — 반영 사실을 적으며 미지원으로 신고하는 형태를 걸러내고, 내부명이 화면에 노출되는 것도 막는다). 식별자가 없는 신고는 그대로 안내된다(조용한 소실 금지). ⑤ [2026-09-21 보강] 합성 시그널 랭킹이 **계산 안에 이미 품은 것**은 다시 묻거나 미지원으로 안내하지 않는다(`indicator_registry.RANKING_INGREDIENTS`·`ranking_covers`): (a) 잔여 미지원 안내는 보고 조각이 이름으로 부른 지표가 전부 전략에 남은 랭킹 자신이거나 그 재료 지표(pead → EPS·초과수익률)일 때, 지표 이름이 없으면 그 랭킹의 내장 처리 이름(윈저라이즈·z-score·표준화)을 담았을 때 제외한다 — 다른 지표를 하나라도 부르면 안내한다. (b) 계열 껍데기 조건(`class.*`)의 인용이 랭킹 자신·재료만 부르면 랭킹의 거울로 걷는다. (c) 조건 회수 패스는 재료 지표와, 유니버스 사전 필터 칸과 같은 말(지표 이름 + 그 칸의 수치를 담은 구절)을 되살리지 않는다 — 같은 지표의 다른 조건은 되살린다. (d) 계열 껍데기에는 근사 반영 안내를 내지 않는다(반영된 지표가 없고 내부 식별자가 노출된다). 대조 입력은 전부 LLM 출력과 레지스트리·구조화 값이다. ⑥ [2026-09-21] `universe.market_cap_top_n`은 **유니버스 명시**다(provenance `universe` — 시장 질문을 다시 하지 않는다. 거래대금 하위 % 제외 단독은 명시가 아니다). 시장을 말하지 않았으면 모집단은 양시장(KOSPI+KOSDAQ)이다 — KOSPI200 기본값이면 상위 N이 성립하지 않는다. 요약(파싱 카드·진행 카드)은 유니버스 행에 '시가총액 상위 N종목'·'N일 평균 거래대금 하위 X% 제외'를, 진행 카드는 '섹터별 비중 상한' 행을 싣는다. 회귀: `backend/tests/test_sector_weight_cap.py`, `test_leftover_notice_internal_names.py`, `test_pead_ranking_lane.py`.

**FR-STR-084** [KR 지역 격리 — 미국 시장 요청 거절, 2026-09-21] KR 레인(표시 언어 ko)은 한국 시장 전용이며, 미국 시장을 대상으로 한 전략 요청은 전략을 만들지 않고 거절 안내로 끝내야 한다 — "죄송합니다. 현재 저는 한국 주식시장만 지원하고 있습니다." + 국내 전환 제안 한 줄(`primary.KR_ONLY_MARKET_REFUSAL`, 되묻기 채널 `clarification_priority="region_market_unsupported"`). ① **사고**: "매월 첫 거래일마다 S&P500 ETF를 100만 원씩 매수합니다…"가 `markets=["ETF"]`(**한국 ETF**) + `symbols=["S&P500 ETF"]`(미해석)로 조립돼 미국 요청이 **국내 ETF 전략**으로 조용히 바뀌어 나갔다(2026-09-21 실측, 120B). 미국 신호가 구조화 출력 어디에도 남지 않아 시장 enum만 보는 가드로는 잡히지 않는다. ② **판정 근거 셋** — ①② 결정론, ③만 LLM(원문은 읽지 않는다): (i) `universe.markets ∩ US_MARKETS` (ii) `universe.symbols`를 registry가 **미국 티커로 푼** 경우("애플"→AAPL·SPY) (iii) registry가 못 푼 표현의 상장 시장을 LLM에 묻는다(`interpreter/market_region_check.py` — 입력은 **LLM이 뽑은 짧은 문자열**, 출력은 KR/US/OTHER/UNKNOWN enum, 한국 상장 해외지수 ETF는 KR). ③ **fail-open**: 판정 실패·JSON 불성립·항목 수 불일치·UNKNOWN은 거절하지 않고 종전대로 진행한다(보조 판정이 턴을 깨지 않는다, quote_check와 같은 원칙). 호출은 미해석 표현이 있는 턴만, 한 턴 한 번. ④ **적용 범위**: 생성 턴(`run_primary_parse` — 컴파일 전)과 수정 턴(`run_primary_modification` — 패치 적용 전, ③의 대상은 이번 턴에 새로 들어온 표현만). /us 반대 방향 가드(`_us_region_kr_market_refusal`)와 언어로 배타적이다. ⑤ **KR 레인의 미국 전략 지원 철회**: 종전에는 KR 사용자도 미국 유니버스 전략을 만들 수 있었고 통화 체계까지 갖춰져 있었다(`strategy_slots.is_us_market_strategy` — 달러 초기 자본). 대화 레인에서 그 경로가 닫힌 것이며, 엔진·가상계좌의 통화 인지 계약(/us 소관)은 불변이다. ⑥ **게이트 영향**: `qa_template_detect.py --source us`는 입력 언어와 무관하게 지역 신호(`language=en`)를 실어 보낸다 — 안 실으면 미국 예시 100건이 전부 이 거절에 걸려 한국어 원문 게이트가 파싱 품질을 보지 못한다. ⑦ 회귀: `test_kr_region_isolation.py`(시장 enum 6종·한국 시장 불개입·en 레인 불개입·미국 티커·미해석 표현 US/KR·fail-open·chat 없음·only_terms·enum 밖 드롭·항목 수 불일치·무호출).

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
| NFR-REL-010 | [요청 취소 전파, 2026-08-18] 전략연구소에서 사용자가 분석 중 '대화 종료'를 누르면 진행 중인 서버 작업도 멈춰야 한다. ① 프론트: 대화 단위 `AbortController` 하나가 그 대화의 모든 요청(분류·파싱 SSE·빌더 스텝·검증·백테스트 스트림)을 끊고, 끊긴 턴은 뒤처리(오류 버블·빌더 상태 복원)를 하지 않는다(`isChatAbort`). ② Next 프록시: `fetchBackend`가 호출자 signal(`req.signal` — 클라이언트 연결 종료 시 abort)을 타임아웃과 결합해 백엔드 연결을 함께 끊는다(예전엔 타임아웃 signal이 덮어써 백엔드 연결이 예산까지 살아 있었다). ③ 백엔드: SSE 요청(`/strategy/parse-stream`, `/strategy/builder/step-stream`)마다 취소 토큰(`backend/cancellation.py`)을 워커 스레드에 묶어, 제너레이터가 정상 종료 전에 닫히면(Starlette 연결 종료 취소) 토큰을 취소한다 — 모든 LLM 호출의 공통 관문(`_ollama_open_with_retry`·워밍업·후행 검증)이 다음 호출을 열지 않고(`OperationCancelled`, BaseException이라 `except Exception` 폴백에 삼켜지지 않음), 워커가 연 HTTP 소켓은 urllib 전역 opener 추적으로 즉시 닫아 진행 중인 Ollama 생성까지 끊는다(요청 컨텍스트 취소 → GPU 반환). 취소된 요청의 결과는 파스 캐시에 저장하지 않는다(폴백 저품질 결과가 다음 대화의 캐시 히트로 새는 것 방지). 비스트리밍 엔드포인트(분류·일반 답변·코치)와 백테스트 엔진 본체는 서버 쪽 취소 대상이 아니다(연결만 끊긴다). 회귀: `backend/tests/test_request_cancellation.py`, `app/analytics/new/page.endChat.test.tsx`, `lib/server/backend.test.ts` |

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
| NFR-SEC-006 | 사용자에게 귀속된 데이터(계좌·주문·포지션·전략·검증 결과·관심종목·백테스트 기록·가상 계좌 시장 상태·시그널 로그)를 반환하거나 변경하는 API는 경로·본문의 id를 그대로 조회 키로 쓰지 않고, 세션에서 얻은 사용자로 쿼리를 묶어야 한다(`getOwnershipContext()`+`withOwnership()`, 계좌 하위 자원은 `findOwnedAccountId()`). 소유자가 아니면 404로 응답해 자원의 존재 여부를 노출하지 않는다. 소유자가 없는 공유 행(cacheKey 기준 `BacktestHistory`)은 `UserBacktestHistory` 연결로 소유를 판정한다 |
| NFR-SEC-007 | 인증·권한에 쓰이는 시크릿이 없으면 열지 않고 닫는다(fail closed). `JWT_SECRET` 미설정 시 운영에서 세션 토큰을 서명·검증하지 않고 즉시 실패하며(기본 키 대체 금지), `SCHEDULER_SECRET` 미설정 시 운영에서 스케줄러 배치 API를 전면 차단한다. 확인 시점은 모듈 로드가 아니라 사용 시점이다 — Next 프로덕션 빌드의 페이지 데이터 수집 단계에는 런타임 환경변수가 없다 |
| NFR-SEC-008 | 대조만 하면 되는 값(비밀번호·이메일 인증번호)은 단방향 해시로 저장한다(bcrypt / SHA-256). 원문을 되돌려 써야 하는 자격증명(토스 자동결제 빌링키)은 AES-256-GCM으로 암호화해 저장하며(`lib/server/fieldCrypto.ts`, 키는 `FIELD_ENCRYPTION_KEY`), 키가 없으면 평문으로 저장하지 않고 거부한다. 카드번호·CVC 등 결제수단 원문은 수집·저장하지 않는다(PSP가 보관) |
| NFR-SEC-009 | 목적을 다한 개인정보·운영 로그는 보존기간이 지나면 자동 파기한다(`lib/server/dataRetention.ts`, 매일 04:00 KST). 기간: AI 대화 기록 90일, 이메일 인증번호 만료 후 1일, 결제 웹훅 수신 기록 180일, 관리자 작업 기록 3년. 법정 보존 의무가 있는 기록(`PaymentOrder` 5년)과 개인정보처리방침이 계정 종료 시까지 보유를 약속한 이용자 데이터(모의투자 기록)는 파기 대상에서 제외한다. 기간은 개인정보처리방침 제4조와 일치해야 한다 |
| NFR-SEC-010 | 브라우저 저장소(localStorage·sessionStorage)에 남기는 사용자 귀속 데이터(전략연구소 진행 중 대화 스냅샷 — 대화 로그는 2026-09-14 계정별 DB로 이관)는 한 계정의 것만 있어야 한다. 저장소마다 주인 표식(로그인 사용자 id)을 두고 읽기 전에 지금 계정과 대조해, 다른 계정·표식 없음·비로그인이면 지운다(`components/strategy/strategyChatStorage.ts`). 화면은 계정이 확정된 뒤에만 저장된 대화를 읽고 쓰며, 로그아웃은 표식까지 모두 지운다(2026-09-14 게스트 계정에서 다른 계정의 대화 기록이 보인 사고) |

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
- 이용약관·개인정보처리방침 하단의 '사업자 정보'는 전자상거래법 제10조 표시 항목(상호·사업자등록번호·통신판매업신고번호·대표자·주소·전화번호·이메일)을 이 순서로 모두 표시한다(2026-09-13 통신판매업신고번호 추가). 값은 환경변수(`COMPANY_NAME`·`BUSINESS_REGISTRATION_NUMBER`·`BUSINESS_MAIL_ORDER_NUMBER`·`BUSINESS_REPRESENTATIVE_NAME`·`BUSINESS_ADDRESS`·`BUSINESS_PHONE`·`BUSINESS_EMAIL`)에서 읽고, 박스 `.env`에 없을 때 '미정'으로 새지 않도록 연락처·신고번호는 `docker-compose.yml`에 기본값을 둔다. 영문(/us) 표기는 `lib/i18n/en.ts`가 값까지 번역한다.
- 화면 하단 상시 푸터(전략연구소 등)의 사업자 정보에는 전화번호를 표시하지 않는다(2026-09-14 지시) — 전자상거래법 제10조 표시 의무는 이용약관·개인정보처리방침 하단의 '사업자 정보'가 충족한다. 푸터 정본은 `components/strategy/StrategyExampleTabs.tsx`의 `BUSINESS_INFO_LINE_1/2`(한국어 원문=`lib/i18n/en.ts` 번역 키).

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
