# 세션 회고 (2026-04-20 ~ 2026-04-21)

## 작업 내용

Strategy Research Agent 전체 설계 및 구현. 14개 파일 신규 생성, prisma 스키마 확장, main.py 라우터 등록.

### 주요 설계 결정

**HoldoutGuard 구현 방식:**
DataLoader에 `max_end_date` 파라미터를 추가하는 방식 대신, BacktestEngine이 이미 `req.get('endDate')`를 지원하므로 request 레벨에서 `endDate`를 클램핑하는 방식을 선택. 기존 캐시된 로더에 손대지 않아 backwards-compatible하고 더 단순하다.

**스코어링 스케일 불일치 해결:**
`CAGR + Sharpe + PF - MDD + Robustness` 수식은 각 항의 스케일이 달라 CAGR(~0.15)이 Sharpe(~1.0)에 묻히는 문제가 있었다. 각 항을 `tanh(x / normalization)`으로 감싸 [-1, 1]로 정규화한 뒤 가중치 합산. robustness+mdd_penalty 가중치(0.50)를 수익 관련(0.50) 이상으로 설정해 "수익보다 견고성 우선" 원칙을 수치로 구현.

**Monte Carlo 미존재 문제:**
CLAUDE.md에 monte_carlo.py가 언급되어 있었지만 실제로 파일이 없었다. 블록 부트스트랩(block_size=21, log-return 재샘플링) 방식으로 신규 구현.

**Optuna 과적합 방지:**
n_trials를 `sqrt(search_space_cardinality)`로 상한을 두어 탐색 공간이 작은 템플릿에서 반복 최적화로 인한 in-sample 과적합을 방지.

### 구현된 파일
- `backend/engine/monte_carlo.py`
- `backend/research/` (agent, generator, search_space, scoring, safeguards, events, prescreen, robustness, promoter, __init__)
- `backend/research/templates/` (momentum, mean_reversion, value, volume_breakout, ai_signal, __init__)
- `backend/api/__init__.py`, `backend/api/research_routes.py`
- `prisma/schema.prisma` — User.planTier, ResearchRun, ResearchCandidate, ResearchEvent 추가

### 테스트
- `backend/tests/test_research_agent.py` — 25개 테스트, 전체 통과
- 기존 백엔드 전체 테스트 330개 — 0 실패 (회귀 없음)
- pytest 실행 방법: `python -m pytest` (bare `pytest`는 sys.path에 backend/ 미포함)

## 배운 점 / 트러블슈팅

**`ModuleNotFoundError: No module named 'research'`:**
`cd backend && pytest tests/` 로 실행하면 pytest가 sys.path에 backend/를 추가하지 않아 `engine`, `research` 임포트가 실패한다. `python -m pytest tests/`로 실행하면 cwd가 sys.path에 자동으로 들어가 해결. 기존 테스트들도 동일한 이슈가 있었으나 이번 세션에서 확인됨.

**FastAPI `AssertionError: Status code 204 must not have a response body`:**
`@router.delete(..., status_code=204)` + `return None`은 FastAPI에서 자동 직렬화를 시도해 오류 발생. `Response(status_code=204)`를 명시적으로 반환하는 방식으로 수정.

---

# 세션 회고 (2026-04-17 ~ 2026-04-20)

## 배운 점

### NL 인터페이스의 결과 매핑 누락 패턴
`app/analytics/new/page.tsx`의 `setResult()` 블록은 백엔드 `raw` 응답을 프론트엔드 `BacktestResult` 타입으로 수동으로 매핑하는 구조다. 필드를 하나씩 나열하는 방식이라 **백엔드에 필드가 추가되거나 기존 필드가 있어도 여기서 빠지면 조용히 undefined가 된다.** 이번 세션에서 이 패턴으로 인한 버그가 두 개나 있었다:
- `universeId: raw.universe_id` 누락 → 유니버스 로그 항상 KOSPI
- `benchmarkLabel: raw.benchmark_label` 누락 → 매수 후 보유 툴팁 항상 KODEX 200

`BacktestService.ts`는 `pythonResult.universe_id`, `pythonResult.benchmark_label`을 제대로 매핑하고 있었는데, NL 인터페이스 쪽만 놓쳤다.

### universe_id가 backtest request에 없었던 구조적 원인
`strategy_converter.py`의 `to_backtest_request()`는 NL 파서가 반환한 `ParsedStrategy.universe` (리스트)를 심볼 목록으로 변환만 하고 `universe_id` 문자열을 request dict에 포함시키지 않았다. 백엔드 엔진은 `req.get('universe_id')`로 벤치마크와 로그를 결정하므로, `universe_id`가 없으면 항상 KOSPI/KODEX200 폴백으로 떨어졌다.

---

## 결정

- `universe_id` 변환 규칙: `["KOSDAQ"]` → `"kosdaq"`, `["KOSPI", "KOSDAQ"]` → `"kosdaq_kospi"` (sorted join). `BacktestDashboard`의 `UNIVERSE_NAMES`에 `kospi_kosdaq`, `kosdaq_kospi` 항목 추가.
- `BacktestDashboard` 메트릭 그리드에서 "총 수익" 카드는 `col-span-2`로 2셀을 차지하도록 고정.

---

## 실수 / 아쉬운 점

- 첫 번째 버그 수정(`app/analytics/new/page.tsx`에 `universeId` 추가)이 부분 수정이었다. 근본 원인인 `strategy_converter.py`의 `universe_id` 누락을 먼저 확인했어야 했는데, 프론트엔드 매핑 문제만 먼저 고쳤다. 덕분에 사용자가 다시 리포트해서 두 번에 걸쳐 수정했다.
- `benchmarkLabel` 누락도 `universeId` 수정 시 같이 발견하고 고쳤어야 했다. `setResult()` 블록 전체를 한 번에 점검했다면 한 번에 잡을 수 있었다.

---

## 다음 할 일

- `app/analytics/new/page.tsx`의 `setResult()` 블록 전체를 `BacktestResult` 타입과 대조해 누락 필드 없는지 전수 점검. `monthlyReturns`, `yearlyReturns`가 현재 빈 객체 `{}`로 하드코딩되어 있어 월별/연도별 수익률 탭이 NL 결과에서 표시되지 않을 가능성 있음.
- NL 인터페이스에서 캐시 히트 시 (`fromCache: true`) 반환되는 결과도 동일한 매핑 경로를 타는지 확인 필요.
