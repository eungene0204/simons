# Software Requirements Specification (SRS)
# Simons — 종합 투자 시뮬레이션 플랫폼

> **문서 버전:** v1.6
> **작성일:** 2026-04-01
> **최종 갱신일:** 2026-06-12
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
   - 3.6b [개별 종목 분석 에이전트 (Stock Analysis Agent)](#36b-개별-종목-분석-에이전트-stock-analysis-agent)
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
| `backtest_period` | `str` | 백테스트 기간 (`1y` / `3y` / `5y`) |
| `initial_capital` | `int` | 초기 투자금 (원) |

**FR-STR-003** 사용자는 파싱된 전략을 대화형으로 수정할 수 있어야 한다 (점진적 수정 모드).

**FR-STR-004** 시스템은 파싱 결과 요약 (유니버스, 필터, 시그널, 리스크 설정)을 사용자가 확인할 수 있도록 표시해야 한다.

**FR-STR-005** 지원 LLM 백엔드:
- MLX (Apple Silicon 최적, 기본값): `mlx-community/Qwen3.5-9B-OptiQ-4bit`
- Ollama (범용): `qwen3.5:9b`

**FR-STR-013** 시스템은 자연어 전략 파싱 요청을 SSE로 처리할 수 있어야 하며, 파싱 완료 전 `accepted` 및 `skeleton` 이벤트를 반환해야 한다.

**FR-STR-014** 시스템은 명확한 정량 조건(PBR/PER/ROE, 보유 기간, 포지션 수, 손절/익절/트레일링 스탑 등)을 deterministic extractor로 우선 파싱하여 불필요한 LLM 호출을 줄여야 한다.

**FR-STR-015** 시스템은 LLM이 tail-truncated JSON을 반환한 경우 가능한 범위에서 JSON을 복구해야 하며, 복구 실패 시 500 오류 대신 안전한 fallback ParsedStrategy를 반환해야 한다.

**FR-STR-016** 시스템은 파싱 직후 백테스트를 자동 실행하면 안 된다. 백테스트는 사용자가 명시적으로 실행 버튼을 누른 경우에만 시작해야 한다.

**FR-STR-017** 시스템은 파싱 응답 생성 시 불필요한 전체 유니버스 심볼 해석을 지연하고, 실제 백테스트 실행 시점에 필요한 종목 해석을 수행해야 한다.

**FR-STR-018** 시스템은 "박스권을 위로 돌파", "N일 고점/신고가 돌파" 등 서술형 돌파 표현을 `breakout` 진입/청산 신호로 인식하고, 표현에서 lookback 기간(N일, 명시 없으면 박스권 기본 20일/52주는 252일)을 추출해야 한다.

**FR-STR-019** 자연어 표현/키워드 대응은 케이스별 정규식을 무한정 추가하는 방식이 아니라 하이브리드로 처리해야 한다: 핵심·빈출 시그널(`ma_crossover`, `breakout`, `volume_spike` 등 서술형 지표)은 결정적 규칙으로 빠르게 처리하고, 긴 꼬리 표현은 LLM 프롬프트의 few-shot 예시로 위임한다. 이때 LLM 환각 방지 키워드 검증은 서술형 지표에 대해서는 건너뛰고 모델 출력을 신뢰해야 한다 (과도한 검증이 올바른 서술형 파싱 결과를 거부하는 것을 방지).

**FR-STR-021** 시스템은 "최근 N일/N거래일/N개월 수익률이 높은 종목 상위 K개"와 같은 상대강도(모멘텀) 랭킹 표현을 인식하여 `ranking_metric="return"`과 `ranking_lookback_days`(미지정 시 60일 기본)를 추출해야 하며, 랭킹 전략에 리밸런싱 주기가 명시되지 않은 경우 `monthly`를 기본값으로 적용해야 한다.

**FR-STR-022** 시스템은 진입 의도가 있는 자연어 입력에서 파싱 결과에 진입 신호/펀더멘털 필터/랭킹 기준이 모두 비어 조용히 누락된 경우, 사용자에게 명확화 질문과 대안 제안(클릭 가능한 칩)을 표시해야 한다. 이때 일반적인 누락 사례와 "엔진이 아직 지원하지 않는 상대강도 랭킹 표현" 사례를 구분하여 각각 다른 안내 문구와 대안을 제공해야 한다 (서로 다른 원인이므로 동일한 메시지로 뭉뚱그리면 안 됨). 이 명확화는 최초 파싱에서만 표시하며, 이후 점진적 수정에서는 표시하지 않는다.

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

**FR-STR-020** 시스템은 다음 29종 시그널·필터 조건을 인식·평가해야 한다.

**기술적 지표 (15개)**

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
| `dividend_yield` | 배당수익률 | operator, value |
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

#### 3.2.2 시뮬레이터 규칙

**FR-BT-010** 리스크 종료(SL/TP/TS/MaxHold)는 당일 close 감지 후 당일 close 가격으로 체결해야 한다 (일봉 기반 현실적 시뮬레이션).

**FR-BT-011** 처리 순서는 반드시 Exit → Risk Evaluation → Entry 순서를 지켜야 한다 (벡터화 3단계).

**FR-BT-012** 트레일링 스탑은 `peak_price` 배열로 추적하며, 진입 시 초기화하고 청산 시 리셋해야 한다.

**FR-BT-013** 다중 종목 동시 진입 시그널 발생 시 스코어 기반 랭킹으로 우선순위를 결정해야 한다 (PBR/ROE 복합 스코어 또는 `ranking_metric="return"` 모멘텀 — 최근 N일 수익률 상위 K종목 선정).

**FR-BT-014** 시스템은 `rebalancing_period`(daily/monthly/quarterly/yearly)가 지정된 전략에 대해 달력 기준 리밸런싱(reconstitution)을 수행해야 한다: 각 주기의 첫 거래일에 후보를 랭킹 상위 K로 재선정하고, 목표 집합에서 빠진 보유 종목은 매도, 신규 편입 종목은 매수, 유지 종목은 그대로 둬야 한다.

**FR-BT-015** 리밸런싱 실행 방식은 전략의 봉중간 리스크 관리(SL/TP/트레일링 스탑/최대 보유기간) 사용 여부에 따라 분기해야 한다: 봉중간 리스크가 없는 순수 리밸런싱은 비중 리셋이 정확한 네이티브 목표비중 방식(vbt `from_orders(size_type='targetpercent')`)으로 처리하고, 봉중간 리스크가 혼재하면 현실적 체결(다음 봉 가격 청산)을 보존하는 커스텀 reconstitution 루프(`from_signals`)로 처리해야 한다.

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
| 월별/연도별 수익률 | 기간별 수익 분해 |
| 종목별 통계 | 개별 종목 성과 분석 |

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

**FR-VM-044** 가상 시장 갱신 이력은 `VirtualMarketLog`에 기록되어야 한다 (날짜, 종목, 시그널 유형, 가격, 액션).

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

**FR-VM-068** `/virtual-account/[id]` 페이지는 비정상 상장 상태 종목에 대해 `DelistingRiskBanner`를 표시해야 한다. 배너는 상태 배지, D-N 카운트다운, 강제청산 버튼을 포함해야 한다.

**FR-VM-069** 모든 자동 처리 이벤트(청산, 차단, 상태변경)는 `DelistingAuditLog`에 기록되어야 한다.

**FR-VM-070** 백테스트 엔진은 **수정주가(adjusted price)**를 연속적으로 반영해야 한다. 소스 데이터는 정방향 액면분할만 조정돼 있고 역분할·감자·정지후재개·단일 오류프린트는 미조정이라 ±30% 가격제한을 넘는 불가능한 일간 점프가 남는다(가짜 손절·수익 유발). `loader._sanitize_corporate_actions`(`preprocess_data` 내)가 이를 처리한다:
- 단일 오류프린트(다음 바 반등) → 양옆 보간 중립화.
- 지속 레벨변화(역분할/감자/정지재개) → 점프 비율로 과거 전체를 역조정(OHLC 동일 스케일).
- 정리매매(시계열 끝 하락 크래시, `_CA_TAIL_GUARD`바 내)는 역조정하지 않는다 — 상장폐지 손실이 수익곡선에 남아야 한다.

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

#### 3.5.2a 사용자 자산 지갑

**FR-ASSET-001** 신규 사용자는 최초 bootstrap 시 기본 가상 자산 10,000,000원을 지급받아야 한다.

**FR-ASSET-002** 사용자는 사용 가능 자산 범위 안에서만 가상계좌 초기 투자금을 배정할 수 있어야 한다.

**FR-ASSET-003** 가상계좌 생성 시 초기 투자금은 사용자 `availableCash`에서 차감되고, 동일 금액이 계좌 `currentCash`로 설정되어야 한다.

**FR-ASSET-004** 총 자산은 저장값이 아니라 `availableCash + 모든 ACTIVE 가상계좌 현재 가치 합계`로 계산해야 한다.

**FR-ASSET-005** 가상계좌 삭제 요청은 포지션 강제 매도, 계좌 현금 합산, 사용자 `availableCash` 반환, 계좌 `CLOSED` 전환을 하나의 트랜잭션으로 처리해야 한다.

**FR-ASSET-005a** 가상계좌 카드의 삭제 버튼을 누르면 삭제 전 확인 모달을 표시해야 하며, 모달은 보유 종목이 현재가 기준으로 강제 매도된다는 경고를 명확히 알려야 한다.

**FR-ASSET-006** 자산 이동 내역은 `AssetLedger`에 `INITIAL_GRANT`, `ACCOUNT_ALLOCATION`, `ACCOUNT_LIQUIDATION_RETURN`, `FORCE_SELL` 타입으로 기록해야 한다.

**FR-ASSET-007** `availableCash`, 계좌 현금, 평가금액은 음수가 될 수 없으며 잘못된 입력은 즉시 거부해야 한다.

**FR-ASSET-008** `CLOSED` 계좌는 신규 주문과 재정산 요청을 거부해야 한다.

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

### 3.6b 개별 종목 분석 에이전트 (Stock Analysis Agent)

> 전략 설계(스크리닝)와 별개로, 사용자의 개별 종목 질문("삼성전자 어때?", "005930 분석해줘")에 응답하는 에이전트. 의도 분류 → 종목 해석 → 로컬 데이터 기반 분석 → 규칙 기반 추천 + LLM 설명 흐름으로 동작한다.

**FR-SA-001** 시스템은 사용자 입력을 `STRATEGY` / `STOCK_ANALYSIS` / `GENERAL` 의도로 분류해야 하며, 분류는 결정적 규칙을 우선 적용하고 모호한 경우에만 LLM으로 폴백해야 한다 (`backend/intent/classifier.py`).

**FR-SA-002** 펀더멘털 스크리닝 표현("PBR 1 이하 저평가 종목 찾아줘")은 `STOCK_ANALYSIS`가 아니라 `STRATEGY`로 분류해야 한다 (조건으로 종목을 고르는 것은 스크리닝이므로).

**FR-SA-003** 종목 분석은 자연어에서 종목을 해석(`symbol_resolver.find_in_text`, 별칭/영문티커 포함)하고, 해석에 실패하면 422로 "종목을 찾지 못했어요" 재질문을 반환해야 한다. 종목 마스터(`stock_master.py`)를 Ground Truth로 사용한다.

**FR-SA-004** 분석의 1차 데이터 소스는 로컬 parquet(가격/기술/펀더멘털)이며, 데이터가 없으면 임의 생성 없이 '데이터 없음'/`INSUFFICIENT_DATA`로 표시해야 한다. 뉴스 감성은 news_v2 저장소를 조회한다.

**FR-SA-005** 추천(매수/관망 등)은 규칙 엔진(`recommendation_engine.py`)이 결정하고 LLM은 설명만 생성해야 한다. AI 예측 점수는 매매 결정에서 제외하며, 입증된 가치(하방 방어)에 한해 "AI 하방 리스크 게이지"로만 노출하고 "매매 신호 아님"을 명시해야 한다 (FR-AI-004).

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
- Sidebar: 좌측 네비게이션
- VirtualAccountDrawer: 우측 슬라이딩 패널 (가상계좌 상세)
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
