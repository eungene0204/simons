# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

한국/글로벌 주식 퀀트 투자 플랫폼. 사용자가 조건 블록을 조합하여 투자 전략을 설계하고, 백테스트(과거 데이터)와 가상매매(모의 시장)로 전략을 검증하는 풀스택 웹 서비스.

## 개발 명령어

### 서버 실행
```bash
npm run dev          # Next.js 프론트엔드 (port 3000)
npm run dev:backend  # FastAPI 백엔드 (port 8000)
npm run dev:all      # 프론트엔드 + 백엔드 + 스케줄러 동시 실행
```

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

### DB 관리
```bash
npm run db:migrate    # Prisma 마이그레이션
npm run db:generate   # Prisma Client 재생성
npm run db:studio     # Prisma Studio GUI
```

### 빌드/린트
```bash
npm run build   # prisma generate + next build
npm run lint    # ESLint
```

## 아키텍처

### 전체 흐름
1. **프론트엔드** — 사용자가 StrategyComposer에서 전략(유니버스 + 진입조건 + 청산조건 + 리스크)을 구성
2. **BacktestService** — `UniverseResolver`로 종목 목록 확정 후 `/api/backtest/run`으로 요청
3. **Next.js API Route** (`/api/backtest/run`) — 중복 요청 캐싱 프록시 역할, FastAPI(`:8000/backtest`)로 전달
4. **FastAPI 백엔드** — `BacktestEngine.run_backtest()` 실행, VectorBT 기반 포트폴리오 시뮬레이션 후 결과 반환

### 백엔드 엔진 파이프라인 (`backend/`)
```
BacktestEngine.run_backtest()
  ├── DataLoader          — data/ohlcv/*.parquet 로드 (in-memory cache)
  ├── IndicatorEngine     — StockDataFrame으로 MA/RSI/MACD/BB 등 계산 (Polars→Pandas)
  ├── SignalEngine        — 조건별 boolean ndarray 벡터화 평가
  │     ├── generate_signals(): signals OR 결합, filters AND 결합
  │     └── _eval_vec(): 조건 하나를 전체 시계열 boolean 배열로 반환
  ├── Simulator           — VectorBT Portfolio.from_signals()로 거래 시뮬레이션
  │     └── 리스크 관리(SL/TP/TS/MaxHold): 당일 close 감지 → 당일 close 청산 주입
  └── ResultHandler       — 수익률/CAGR/Sharpe/MaxDD 등 지표 계산 후 직렬화
```

**Simulator 설계 원칙:**
- 리스크 종료(SL/TP/TS/MaxHold): 당일 close 감지 → `exits_values[i]`에 당일 close 가격 주입
- trailing_stop: `peak_price` 배열로 추적, entry 시 초기화, exit 시 리셋
- 벡터화 Step 순서 고정: Step1(퇴장 처리) → Step2(리스크 평가/주입) → Step3(진입 처리)

### 프론트엔드 구조 (`app/`, `components/`, `lib/`)
- `app/` — Next.js App Router 페이지 + API 라우트
- `app/api/` — 인증(login/register), backtest(run/cache), universe, virtual-account 등 API 라우트
- `components/strategy/` — 전략 빌더 UI
  - `StrategyComposer.tsx` / `StrategyComposerV2.tsx` — 메인 전략 편집기
  - `steps/Step1~Step5` — 유니버스 → 조건 → 리스크 → 백테스트 → 리포트 마법사
  - `backtest/` — BacktestDashboard, BacktestSummaryCard, MonteCarloPanel, WalkForwardModal, XAIModal
- `lib/strategy/BacktestService.ts` — 프론트엔드 백테스트 실행 오케스트레이터
- `lib/strategy/pipeline/UniverseResolver.ts` — 유니버스별 종목 목록 캐싱
- `lib/strategy-blocks.ts` — 29KB, 전략 조건 블록 정의 (UI용)
- `types/strategy.ts` — 핵심 타입: `StrategyDSL`, `Condition`, `ConditionGroup`, `RiskManagement`

### 데이터
- `data/ohlcv/` — 4052개 한국 주식 OHLCV Parquet 파일 (`{symbol}.parquet`)
- `prisma/prisma/dev.db` — SQLite (Strategy, BacktestHistory, BacktestResult, Stock, User)

### AI 모델 (`backend/ai/`, `model/`)
- `ai_engine.py` — XGBoost 기반 AI 예측 엔진 (lazy load, 서버 시작 시 프리로드)
- `xai_engine.py` — SHAP 기반 설명 가능 AI
- 조건 블록 ID: `ai_model`, `ai_drop_model`

### 추가 기능 (`backend/engine/`)
- `monte_carlo.py` — 몬테카를로 시뮬레이션
- `walk_forward.py` — 워크포워드 분석
- `optuna_optimizer.py` — 전략 파라미터 최적화 (Optuna)
- `vectorbt_native.py` — VectorBT 네이티브 비교
- `virtual_trader.py` — 가상매매 실시간 트레이더
- `providers/` — 시장 데이터 공급자 (KIS API, pykrx, yfinance, KRX API)

## 코드 설계 원칙

코드를 작성하거나 수정할 때 반드시 [`docs/coding_rules.md`](docs/coding_rules.md)의 원칙들을 준수한다.
(SOLID, DRY, KISS, YAGNI, SoC, LoD, Composition Over Inheritance, Boy Scout Rule, Fail Fast)

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

### 계획서 완료 표시 자동 업데이트
작업 완료 시 `docs/PROJECT_PLAN.md`의 해당 항목을 자동으로 `✅ 완료`로 업데이트한다.

### UI 가이드라인 준수
새 페이지나 컴포넌트 작성 시 반드시 `docs/UI_GUIDELINES.md`를 참고한다.
 기존 페이지 수정 시도 가이드라인과 불일치하는 부분이 있으면 맞춰서 수정할 것
