# Software Requirements Specification (SRS)
# Simons — 종합 투자 시뮬레이션 플랫폼

> **문서 버전:** v1.3
> **작성일:** 2026-04-01
> **최종 갱신일:** 2026-04-22
> **프로젝트명:** Simons
> **상태:** 작성 중

---

## 목차

1. [소개](#1-소개)
2. [전체 시스템 설명](#2-전체-시스템-설명)
3. [기능 요구사항](#3-기능-요구사항)
   - 3.1 [전략 설계](#31-전략-설계)
   - 3.2 [백테스트 엔진](#32-백테스트-엔진)
   - 3.3 [AI/ML 시스템](#33-aiml-시스템)
   - 3.4 [가상 매매 시스템](#34-가상-매매-시스템)
   - 3.5 [포트폴리오 관리](#35-포트폴리오-관리)
   - 3.6 [시장 데이터 및 분석](#36-시장-데이터-및-분석)
   - 3.7 [사용자 관리](#37-사용자-관리)
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
| 중급 트레이더 | 기술적 분석 활용 | 시그널 블록 조합, 전략 파라미터 튜닝 |
| 고급 퀀트 | 알고리즘 트레이딩 연구 | AI 모델 결합, Optuna 최적화, XAI 분석 |

---

## 3. 기능 요구사항

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
| `hold_period_days` | `int` | 보유 기간 (일) |
| `rebalancing_period` | `Optional[str]` | 리밸런싱 주기 (`monthly` / `quarterly` 등) |
| `stop_loss_pct` | `Optional[float]` | 손절선 (%) |
| `take_profit_pct` | `Optional[float]` | 익절선 (%) |
| `backtest_period` | `str` | 백테스트 기간 (`1y` / `3y` / `5y`) |
| `initial_capital` | `int` | 초기 투자금 (원) |

**FR-STR-003** 사용자는 파싱된 전략을 대화형으로 수정할 수 있어야 한다 (점진적 수정 모드).

**FR-STR-004** 시스템은 파싱 결과 요약 (유니버스, 필터, 시그널, 리스크 설정)을 사용자가 확인할 수 있도록 표시해야 한다.

**FR-STR-005** 지원 LLM 백엔드:
- MLX (Apple Silicon 최적, 기본값): `mlx-community/Qwen2.5-32B-Instruct-4bit`
- Ollama (범용): `qwen2.5:32b`

#### 3.1.2 블록 기반 전략 빌더 (레거시 / 고급 편집)

**FR-STR-010** 시스템은 5단계 위자드 방식의 블록 조합 전략 빌더를 제공해야 한다.

| 단계 | 이름 | 내용 |
|------|------|------|
| Step 1 | 유니버스 선택 | KOSPI / KOSDAQ / KOSPI200 등, 펀더멘탈 필터 적용 |
| Step 2 | 진입/청산 조건 | 시그널 블록 조합으로 매수/매도 조건 설계 |
| Step 3 | 포지션·리스크 | 포지션 크기, SL/TP/TS, 최대 보유일 |
| Step 4 | 백테스트 설정 | 기간, 초기자본, 수수료율, 슬리피지 |
| Step 5 | 결과 리포트 | 수익률, Sharpe, MDD, 거래내역, 에퀴티커브 |

#### 3.1.3 시그널 블록

**FR-STR-020** 시스템은 다음 29개 시그널 블록을 지원해야 한다.

**기술적 지표 (15개)**

| 블록 ID | 이름 | 핵심 파라미터 |
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

| 블록 ID | 이름 | 핵심 파라미터 |
|---------|------|--------------|
| `trading_value` | 거래대금 필터 | operator, value (억원) |
| `market_cap` | 시가총액 필터 | operator, value |
| `per` | PER 필터 | operator, value |
| `pbr` | PBR 필터 | operator, value |
| `roe_or_gpa` | ROE/GPA 필터 | metric, operator, value |
| `debt_ratio` | 부채비율 필터 | operator, value |
| `trading_suspension` | 거래정지 제외 | exclude |

**수급 (1개)**

| 블록 ID | 이름 | 핵심 파라미터 |
|---------|------|--------------|
| `investor_net_buy` | 기관/외인 순매수 | investorType, period, minAmount |

**리스크 (4개)**

| 블록 ID | 이름 | 핵심 파라미터 |
|---------|------|--------------|
| `price_limit_exit` | 손절/익절 | stopLossPct, takeProfitPct |
| `max_holding_days` | 최대 보유기간 | value |
| `trailing_stop` | 트레일링 스탑 | percentage |

**AI/ML (1개)**

| 블록 ID | 이름 | 핵심 파라미터 |
|---------|------|--------------|
| `ai_model` | AI 상승 예측 | threshold, direction |

#### 3.1.4 리스크 관리 설정

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

#### 3.1.5 전략 저장 및 관리

**FR-STR-040** 사용자는 전략을 저장하고 이름 및 설명을 부여할 수 있어야 한다.

**FR-STR-041** 시스템은 전략의 타입을 자동 분류해야 한다 (가치투자 / 모멘텀 / 기술적분석 / AI 혼합 / 기타).

**FR-STR-042** 사용자는 저장된 전략을 불러와 편집하거나 재실행할 수 있어야 한다.

#### 3.1.6 독립형 배치 테스트

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

#### 3.1.7 Content-addressed Strategy ID

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

**FR-BT-013** 다중 종목 동시 진입 시그널 발생 시 스코어 기반 랭킹으로 우선순위를 결정해야 한다.

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

**FR-AI-003** AI 시그널 블록(`ai_model`)은 임계값(threshold)과 방향(direction)을 파라미터로 받아 전략 시그널로 통합되어야 한다.

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

**FR-NEWS-031** 백엔드 미가동 시 Next.js API Route는 seed 데이터를 폴백으로 반환해야 한다 (개발/테스트 환경 지원).

#### 3.6.5 뉴스 UI — NewsImpactPanel

**FR-NEWS-040** `NewsImpactPanel` 컴포넌트는 다음을 표시해야 한다:
- 최신 Alpha 시그널 배지 (방향, 신뢰도, 이벤트 유형)
- 위험 경보 수준 (low / medium / high)
- 뉴스 목록 (제목, 출처, 시각, 감성, 임팩트 점수)

**FR-NEWS-041** `app/stock-order/page.tsx`의 "뉴스·공시" 탭은 `NewsImpactPanel`을 사용해야 한다.

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

### 4.2 신뢰성

| ID | 요구사항 |
|----|---------|
| NFR-REL-001 | 백테스트 엔진은 개별 종목 오류 발생 시 해당 종목을 건너뛰고 전체 실행을 지속해야 한다 |
| NFR-REL-002 | 가상 시장 데이터 소스 장애 시 다음 우선순위 소스로 자동 폴백해야 한다 |
| NFR-REL-003 | DB 트랜잭션 실패 시 롤백 처리해야 한다 |
| NFR-REL-004 | 배치 실행 상태는 `BatchRun`/`BatchRunCandidate`에 체크포인트 저장되어야 한다 |
| NFR-REL-005 | 서버 재시작 후 다음 `batch-runs` 요청이 들어오면 incomplete batch를 복구해 재개할 수 있어야 한다 |

### 4.3 유지보수성

| ID | 요구사항 |
|----|---------|
| NFR-MNT-001 | 백엔드 테스트 커버리지: pytest 기준 핵심 엔진 모듈 80% 이상 |
| NFR-MNT-002 | 프론트엔드 테스트: Vitest 기반 주요 컴포넌트 단위 테스트 |
| NFR-MNT-003 | 새 시그널 블록 추가 시 `signals.py`와 `strategy-blocks.ts` 두 파일만 수정하면 되는 구조 유지 |

### 4.4 보안

| ID | 요구사항 |
|----|---------|
| NFR-SEC-001 | API 키 등 민감 정보는 `.env` 파일로 관리하며 소스코드에 하드코딩 금지 |
| NFR-SEC-002 | 사용자 입력(자연어 전략 프롬프트 포함)은 서버 전달 전 길이 제한(최대 2,000자) 적용 |
| NFR-SEC-003 | SQL Injection 방지: Prisma ORM의 파라미터화된 쿼리 사용 |

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
BatchRun ──── BatchRunCandidate ──── Strategy (배치 실행)
Strategy ──── VirtualAccount                   (전략-가상계좌 연결)
VirtualAccount ──── VirtualPosition            (가상 포지션)
VirtualAccount ──── VirtualOrder               (가상 주문)
VirtualAccount ──── VirtualMarketState         (가상 시장 상태)
VirtualMarketLog                               (시장 갱신 로그)
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

#### VirtualAccount
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | String PK | |
| name | String | 계좌명 |
| initialCash | Float | 초기 투자금 |
| currentCash | Float | 현재 잔고 |
| strategyId | String? | 연결된 전략 ID |
| strategyName | String? | 연결된 전략명 |
| tradingMode | String | manual / auto / signal |
| createdAt | DateTime | |
| updatedAt | DateTime | |

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
| GET | `/health` | 서버 헬스체크 |

### 6.2 Next.js API Routes

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET/POST | `/api/strategy` | 전략 목록 조회 / 저장 |
| GET/PUT/DELETE | `/api/strategy/[id]` | 전략 상세 조회 / 수정 / 삭제 |
| POST | `/api/strategy/parse` | 자연어 전략 파싱 프록시 |
| POST | `/api/strategy/backtest-stream` | 단일 전략 백테스트 실행 (SSE) |
| POST | `/api/strategy/save-with-backtest` | 전략 저장 + 백테스트 결과 함께 저장 |
| GET/POST | `/api/strategy/batch-runs` | 배치 실행 시작 / 최근 이력 조회 / 상세 조회 / 취소 |
| GET/POST | `/api/virtual-account` | 가상계좌 목록 조회 / 생성 |
| GET/PUT/DELETE | `/api/virtual-account/[id]` | 가상계좌 상세 / 수정 / 삭제 |
| GET/POST | `/api/virtual-market/[accountId]` | 가상 시장 상태 조회 / 시작 |
| POST | `/api/virtual-market/[accountId]/refresh` | 가상 시장 수동 갱신 |
| GET | `/api/dashboard/strategy-list` | 대시보드용 전략 목록 |
| GET/POST | `/api/watchlist` | 관심종목 조회 / 추가 |
| DELETE | `/api/watchlist/[id]` | 관심종목 삭제 |
| GET | `/api/news/symbol/[symbol]` | 종목별 뉴스 목록 (page, page_size, as_of) |
| GET | `/api/news/impact/[symbol]` | 종목 Alpha 시그널 (latest_alpha, risk_alert_level) |
| GET | `/api/news/top` | 주요 시장 뉴스 피드 |

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

### 8.3 개발 제약

| 항목 | 내용 |
|------|------|
| 테스트 | 코드 수정 시 반드시 전체 유닛 테스트 통과 확인 |
| 하위 호환 | `BacktestRequest` / `BacktestResponse` 스키마 변경 시 프론트엔드와 동시 수정 |
| DB 마이그레이션 | Prisma 스키마 변경 시 `npx prisma migrate dev` 실행 및 기존 데이터 호환성 검토 |
