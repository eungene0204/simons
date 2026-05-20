# News System v2 — Pre-fetch & Cache Architecture

> 사용자가 종목 페이지의 뉴스탭을 열었을 때 **즉시(< 200ms)** 캐시된 최신 뉴스가 표시되도록 하는 종합 설계.
> 외부 뉴스 API는 **사전 수집(pre-fetch) 워커**가 호출하며, 뉴스탭은 절대 외부 호출을 트리거하지 않는다.

---

## 1. 전체 시스템 아키텍처

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                         Stock News Tab Request Flow                            │
└───────────────────────────────────────────────────────────────────────────────┘

[Next.js NewsTab]
      │ GET /api/stocks/{symbol}/news
      ▼
[Next.js Route Handler]  ── proxies ──▶  [FastAPI /v2/news/{symbol}]
                                                  │
                                                  ▼
                                ┌───────────────────────────────┐
                                │   NewsService.get_for_symbol  │
                                └───────────────────────────────┘
                                                  │
                                                  ▼
                                  ┌── Redis HIT  ──▶ return  (status=READY|STALE)
                                  │
                                  ├── Redis MISS, PG HIT
                                  │     ├── stale? enqueue refresh_stale_news
                                  │     └── return PG snapshot (READY|STALE)
                                  │
                                  └── PG MISS
                                        ├── enqueue collect_news(symbol, priority=high)
                                        ├── priority_score += 50
                                        └── return status=COLLECTING (empty items)


┌───────────────────────────────────────────────────────────────────────────────┐
│                         Pre-fetch Pipeline (Async)                             │
└───────────────────────────────────────────────────────────────────────────────┘

[APScheduler — every minute]
      │  reads PriorityScore tier
      ▼
[enqueue_collect_for_tier(Tier1/2/3)]
      │
      ▼
[Celery worker: collect_news]
      │
      ▼
[Provider fetch]  ─▶  [Normalizer]  ─▶  [Deduplicator]
                                              │
                                              ▼
                                  [Persist news_articles row]
                                              │
                                              ▼
                                  [Celery: analyze_news (AI Agent)]
                                              │     - summary
                                              │     - sentiment
                                              │     - impact_level
                                              │     - market_effect
                                              │     - related_symbols
                                              ▼
                                  [Persist analysis fields]
                                              │
                                              ▼
                                  [Redis SET news:{symbol}  (TTL 10m)]
                                              │
                                              ▼
                                  [Metrics: collector_runs_total, dedup_rate]
```

### 핵심 원칙

| 원칙 | 적용 |
|---|---|
| SoC | `repository` (DB) / `cache` (Redis) / `agent` (AI) / `service` (orchestration) / `api` (HTTP) 분리 |
| Fail Fast | Redis/Celery/DB 미설정 시 `config.py`에서 명시적 raise. 단, Redis는 graceful degrade (no-cache mode). |
| KISS / YAGNI | 종목별 단일 캐시 키 `news:{symbol}`. 페이지네이션은 PG limit으로 처리, Redis는 첫 페이지만 캐시. |
| Composition | `NewsService`는 `Repository + Cache + Queue + Agent`를 주입받음. 상속 없음. |
| DRY | Normalizer/Deduplicator는 단일 모듈. provider 코드 재사용. |

---

## 2. 폴더 구조

```
backend/news_v2/
├── __init__.py
├── config.py                  # Settings (env vars, Redis URL, DB DSN, tier intervals)
├── logging_setup.py           # structlog config — JSON logs
├── models.py                  # SQLAlchemy ORM models
├── repository.py              # Repository pattern — DB I/O only
├── cache.py                   # Redis client + NewsCache abstraction
├── dedup.py                   # Title normalize + SHA256 + (optional) embedding cosine
├── priority.py                # PriorityScore computation + Tier assignment
├── agent.py                   # AINewsAgent — wraps LLM/heuristic analysis
├── service.py                 # NewsService — orchestrator (used by API + workers)
├── celery_app.py              # Celery app factory + broker config
├── tasks.py                   # collect_news / analyze_news / refresh_stale_news / dedup / sentiment
├── scheduler.py               # APScheduler — tier cadence
├── api.py                     # FastAPI APIRouter (/v2/news/...)
└── observability.py           # Prometheus counters + histograms

backend/tests/
├── test_news_v2_dedup.py
├── test_news_v2_priority.py
├── test_news_v2_repository.py
└── test_news_v2_service.py

app/api/stocks/[symbol]/news/route.ts   # Next.js proxy → FastAPI
lib/hooks/useStockNews.ts               # SWR hook
types/news-v2.ts                        # FE types
components/stock/NewsImpactPanel.tsx    # status-aware UI (modified)

docker-compose.news-v2.yml              # Redis + PostgreSQL
backend/requirements-news-v2.txt        # incremental deps
docs/news-system-v2.md                  # this file
```

---

## 3. DB 스키마 (PostgreSQL — Prisma-portable)

```sql
-- news_articles : canonical normalized articles
CREATE TABLE news_articles (
  id                BIGSERIAL PRIMARY KEY,
  symbol            VARCHAR(16)  NOT NULL,
  title             TEXT         NOT NULL,
  normalized_title  TEXT         NOT NULL,
  summary           TEXT,
  source            VARCHAR(64)  NOT NULL,
  url               TEXT         NOT NULL,
  published_at      TIMESTAMPTZ  NOT NULL,
  sentiment         VARCHAR(16),               -- positive/neutral/negative
  sentiment_score   REAL,                      -- -1.0 ~ 1.0
  impact_level      VARCHAR(16),               -- low/medium/high
  market_effect     TEXT,                      -- short LLM verbatim
  related_symbols   TEXT[],                    -- additional impacted tickers
  ai_summary        TEXT,
  embedding         VECTOR(384),               -- pgvector (optional)
  hash              CHAR(64)     NOT NULL,     -- SHA256(normalized_title)
  status            VARCHAR(16)  NOT NULL DEFAULT 'analyzed',
  created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  UNIQUE (symbol, hash)
);

CREATE INDEX idx_news_articles_symbol_pub ON news_articles (symbol, published_at DESC);
CREATE INDEX idx_news_articles_hash       ON news_articles (hash);
CREATE INDEX idx_news_articles_published  ON news_articles (published_at DESC);
-- Optional: ANN index on embedding (pgvector ivfflat)

-- priority_scores : tier learning for scheduler
CREATE TABLE news_priority_scores (
  symbol           VARCHAR(16) PRIMARY KEY,
  score            DOUBLE PRECISION NOT NULL DEFAULT 0,
  tier             SMALLINT  NOT NULL DEFAULT 3,        -- 1=hot, 2=warm, 3=cold
  last_collected   TIMESTAMPTZ,
  last_viewed      TIMESTAMPTZ,
  view_count_24h   INTEGER   NOT NULL DEFAULT 0,
  watchlist_count  INTEGER   NOT NULL DEFAULT 0,
  search_count_24h INTEGER   NOT NULL DEFAULT 0,
  volatility       REAL      NOT NULL DEFAULT 0,
  turnover         REAL      NOT NULL DEFAULT 0,
  ai_importance    REAL      NOT NULL DEFAULT 0,
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_priority_tier ON news_priority_scores (tier, score DESC);

-- collection_status : per-symbol state machine
CREATE TABLE news_collection_status (
  symbol             VARCHAR(16) PRIMARY KEY,
  status             VARCHAR(20) NOT NULL DEFAULT 'NOT_COLLECTED',
                     -- NOT_COLLECTED | COLLECTING | READY | STALE | NO_NEWS_FOUND | FAILED
  last_success_at    TIMESTAMPTZ,
  last_attempt_at    TIMESTAMPTZ,
  last_error         TEXT,
  attempt_count      INTEGER NOT NULL DEFAULT 0,
  in_flight_job_id   VARCHAR(64),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ingestion_log : audit trail
CREATE TABLE news_v2_ingestion_log (
  id            BIGSERIAL PRIMARY KEY,
  symbol        VARCHAR(16) NOT NULL,
  provider      VARCHAR(32) NOT NULL,
  job_id        VARCHAR(64),
  started_at    TIMESTAMPTZ NOT NULL,
  finished_at   TIMESTAMPTZ,
  fetched       INTEGER NOT NULL DEFAULT 0,
  deduped       INTEGER NOT NULL DEFAULT 0,
  inserted      INTEGER NOT NULL DEFAULT 0,
  status        VARCHAR(16) NOT NULL,
  error         TEXT
);
CREATE INDEX idx_ingestion_symbol_time ON news_v2_ingestion_log (symbol, started_at DESC);
```

> **SQLite 호환**: `pgvector`/`TEXT[]`/`TIMESTAMPTZ`는 SQLite에 없음. 개발 환경에서는 `embedding`을 `BLOB`, `related_symbols`를 JSON 문자열로 저장하는 SQLAlchemy 타입 어댑터로 처리한다 (`models.py`의 `JSONList`, `Vector` 커스텀 타입).

### Status enum 정의

| status | 의미 | UI |
|---|---|---|
| `NOT_COLLECTED` | DB에 한 번도 수집된 적 없음 | "뉴스를 수집하고 있습니다" |
| `COLLECTING` | 수집 작업이 큐에 enqueue되어 처리 중 | spinner + "수집 중..." |
| `READY` | 신선한 데이터 존재 | 정상 리스트 |
| `STALE` | TTL 만료 — 백그라운드 refresh 트리거됨, 캐시 응답은 즉시 |  옅은 표시 + 자동 새로고침 |
| `NO_NEWS_FOUND` | 수집 시도 후 결과 0건 | "최근 뉴스 없음" |
| `FAILED` | 수집 실패 + retry 한도 초과 | 에러 카드 + 재시도 버튼 |

---

## 4. Redis 캐시 전략

| Key | Value | TTL | 용도 |
|---|---|---|---|
| `news:{symbol}` | JSON list (top 20 articles) | **600s (10m)** | 뉴스탭 1차 응답 |
| `news:status:{symbol}` | enum string | 60s | 상태 빠른 확인 |
| `news:lock:{symbol}` | `1` | 180s | single-flight (collect 중복 방지) |
| `news:priority:tier:{n}` | sorted set, member=symbol, score=priority | persistent | 스케줄러가 Tier별 종목 조회 |
| `news:counters:views:{symbol}` | INCR, EXPIRE 24h | 24h | priority_score 입력 |
| `news:circuit:{provider}` | error rate | 300s | provider별 circuit breaker |

### 조회 흐름

```
get_for_symbol(symbol):
    cached = redis.get(f"news:{symbol}")
    if cached:
        status = redis.get(f"news:status:{symbol}") or READY
        if status == STALE:
            enqueue(refresh_stale_news, symbol)
        return Response(status=status, source=redis, items=cached)

    db_rows = repo.list_recent(symbol)
    if db_rows:
        redis.setex(f"news:{symbol}", 600, serialize(db_rows))
        return Response(status=READY, source=postgres, items=db_rows)

    if redis.set(f"news:lock:{symbol}", "1", nx=True, ex=180):
        enqueue(collect_news, symbol, priority="high")
        repo.bump_priority(symbol, +50)
    return Response(status=COLLECTING, items=[])
```

### Invalidation

- `collect_news` 완료 시 `redis.del("news:{symbol}")` → 다음 요청이 새 데이터를 PG에서 채워 캐시.
- TTL은 stale 판정 기준이지만, 신선도가 중요한 종목은 `priority.tier == 1` → 5분 TTL로 단축.

---

## 5. Queue Architecture (Celery)

### Broker
- **Production**: Redis (`redis://redis:6379/1`)
- **Dev**: 동일 (docker-compose가 redis 단일 인스턴스 제공)

### Result backend
- 짧은 작업이라 결과 저장은 불필요 → `result_backend = None`로 두고, 상태는 PG `news_collection_status` 테이블에서 관리.

### Queues

| 큐 | 작업 | 우선순위 | 동시성 |
|---|---|---|---|
| `news.collect.high` | Tier1 종목 collect_news | high | 8 |
| `news.collect.default` | Tier2/3 collect_news | normal | 4 |
| `news.analyze` | AI 분석 (CPU/GPU bound) | normal | 2 |
| `news.maintenance` | refresh_stale_news / dedup / cleanup | low | 2 |

### Task 정의 (요약 — 코드는 `tasks.py`)

| 함수 | 트리거 | 동작 |
|---|---|---|
| `collect_news(symbol)` | 스케줄러 / on-demand miss | provider fetch → normalize → dedup → persist → enqueue analyze |
| `analyze_news(article_id)` | collect 완료 | AI agent 호출, 결과 PG 업데이트 → Redis 무효화 |
| `refresh_stale_news(symbol)` | stale 응답 | collect_news와 동일하지만 우선순위 낮음 |
| `deduplicate_news(symbol)` | 야간 maintenance | embedding cosine 기반 추가 dedup |
| `update_sentiment(article_id)` | 모델 업데이트 시 | 기존 article 재분석 |

### Retry 정책

```python
@celery_app.task(
    bind=True,
    autoretry_for=(ProviderError, ConnectionError, TimeoutError),
    retry_backoff=True,           # exponential
    retry_backoff_max=600,        # cap at 10m
    retry_jitter=True,
    max_retries=5,
    acks_late=True,               # only ack after success
    reject_on_worker_lost=True,
)
def collect_news(self, symbol: str): ...
```

- **Dead-letter**: max_retries 초과 → `news.dlq` 큐로 publish + `collection_status.status = FAILED`.
- **Fail-fast**: 4xx provider 응답 (rate limit 제외)은 즉시 fail, retry 안 함.

---

## 6. Scheduler (APScheduler)

### Tier별 cadence

| Tier | 기준 | 주기 |
|---|---|---|
| 1 | priority_score >= 1000 또는 거래대금 상위 50 | **2분** |
| 2 | priority_score >= 200 또는 관심종목 등록자 >= 5 | **10분** |
| 3 | 나머지 (수집 이력 있는 종목) | **60분** |

### 실행

- `APScheduler` `AsyncIOScheduler`를 FastAPI lifespan에서 시작 (단일 인스턴스), **단 leader election이 필요한 멀티 인스턴스 운영에서는 별도 scheduler 프로세스로 분리**.
- 실행: `enqueue_collect_for_tier(tier)` → 해당 tier symbol N개를 jitter 분산해 collect 큐에 push.
- jitter: 동시에 1000개 push 방지를 위해 ±25% 랜덤 지연.

```python
scheduler.add_job(enqueue_tier, "interval", minutes=2, args=[1], id="tier1")
scheduler.add_job(enqueue_tier, "interval", minutes=10, args=[2], id="tier2")
scheduler.add_job(enqueue_tier, "interval", minutes=60, args=[3], id="tier3")
scheduler.add_job(recompute_priority, "cron", minute="*/30", id="priority")
scheduler.add_job(prune_old_news,    "cron", hour=3,        id="cleanup")
```

---

## 7. Priority Score 계산

```
priority_score =
    0.30 * normalize(turnover_24h)        +   # 거래대금
    0.20 * normalize(volatility_30d)      +   # 변동성
    0.20 * normalize(view_count_24h)      +   # 사용자 조회수
    0.15 * normalize(watchlist_count)     +   # 관심종목 등록 수
    0.10 * normalize(search_count_24h)    +   # 검색량
    0.05 * ai_importance                      # AI 중요도 (0~1)

view_bonus = 50    # 뉴스탭 조회 시 즉시 가산
```

- normalize: 종목 전체에서 percentile rank → 0~100.
- 가중치는 `config.PRIORITY_WEIGHTS`로 외부화.
- 30분마다 `recompute_priority` 작업이 전체 종목 재계산 후 `tier` 결정 + Redis sorted set 갱신.

---

## 8. AI News Agent

### 책임
- 단일 article을 받아 다음 필드를 산출:
  ```json
  {
    "summary": "...",
    "sentiment": "positive | neutral | negative",
    "sentiment_score": 0.82,
    "impact_level": "low | medium | high",
    "market_effect": "...",
    "related_symbols": ["005930", "000660"]
  }
  ```
- 구현은 LLM(Google Gemini, 기존 `GOOGLE_API_KEY` 활용) 또는 휴리스틱(키워드 기반) 둘 다 지원.
- `agent.py`의 `AINewsAgent` 인터페이스로 추상화 → 백테스트/테스트에서 fake 주입 가능.

### 비용 통제
- 같은 `hash`는 캐시 (`agent_cache:{hash}` Redis 24h).
- 일일 분석 건수 cap: `AI_DAILY_BUDGET=2000`. 초과 시 휴리스틱 fallback.

---

## 9. FastAPI 구현 — 응답 스키마

```python
# /v2/news/{symbol}
class NewsItem(BaseModel):
    id: int
    title: str
    summary: Optional[str]
    source: str
    url: str
    published_at: datetime
    sentiment: Optional[Literal["positive", "neutral", "negative"]]
    sentiment_score: Optional[float]
    impact_level: Optional[Literal["low", "medium", "high"]]
    market_effect: Optional[str]
    related_symbols: list[str] = []

class NewsResponse(BaseModel):
    status: Literal["READY", "STALE", "COLLECTING", "NOT_COLLECTED", "NO_NEWS_FOUND", "FAILED"]
    source: Literal["redis", "postgres", "queue"]
    stale: bool
    items: list[NewsItem]
    fetched_at: Optional[datetime]
    message: Optional[str] = None
```

---

## 10. Next.js 통합

- `/api/stocks/[symbol]/news` → FastAPI `/v2/news/{symbol}` 단순 프록시 (서버사이드, 짧은 timeout).
- `useStockNews(symbol)` SWR 훅:
  ```ts
  useSWR(`/api/stocks/${symbol}/news`, fetcher, {
    refreshInterval: data?.status === "COLLECTING" ? 3000 : 60_000,
    revalidateOnFocus: true,
    keepPreviousData: true,
  })
  ```
- `NewsImpactPanel`은 `data.status`에 따른 분기 UI.

---

## 11. 성능 목표

| 지표 | 목표 |
|---|---|
| p50 응답 (Redis hit) | < 30ms |
| p95 응답 (PG hit) | < 200ms |
| p99 응답 (cold miss → COLLECTING) | < 200ms |
| Redis hit ratio (전체) | > 85% |
| Tier1 데이터 신선도 | < 3분 |
| 중복 기사 비율 | < 3% |

---

## 12. Error Handling & Retry

### 계층별 전략

| 계층 | 실패 모드 | 전략 |
|---|---|---|
| Redis 연결 | TimeoutError | log + bypass → PG로 직행 (no-cache mode) |
| PG 연결 | OperationalError | 5xx 응답, 알림 |
| Provider 4xx | non-retryable | log + status=FAILED, 30분 cool-down |
| Provider 5xx/timeout | retryable | exponential backoff (max 5회) |
| AI Agent quota | quota exceeded | heuristic fallback, sentiment_score=0 |
| Celery worker crash | acks_late=True | broker가 자동 재전달 |

### Circuit Breaker
- provider별 최근 5분 에러율 > 30% → 10분간 호출 차단 (`news:circuit:{provider}` Redis key).
- AI agent도 동일 패턴 (분당 timeout > 5 → 5분 휴리스틱 모드).

---

## 13. Scalability

| 차원 | 전략 |
|---|---|
| 종목 수 (수천 → 수만) | priority tier로 호출량 비선형 증가 제한. Tier3는 60분/회. |
| QPS (뉴스탭 조회) | Redis가 1차 흡수. p99 < 200ms 유지. |
| 워커 수 평행 확장 | Celery는 stateless. `--concurrency` 조정으로 수평 확장. |
| DB 쓰기 부하 | dedup이 1차 필터 (히트율 30~50%). 야간 vacuum + 90일 이전 파티션 삭제. |
| Redis 메모리 | 키당 평균 5KB × 10000 종목 ≈ 50MB. allkeys-lru policy. |
| 멀티 인스턴스 scheduler | redis lock (`SETNX news:scheduler:leader`)로 leader 1개만 enqueue. |

---

## 14. Production Deployment

### 컴포넌트 토폴로지

```
[Nginx / ALB]
  ├─▶ [Next.js (PM2 cluster, N replicas)]
  └─▶ [FastAPI (uvicorn workers, M replicas)]
            ├─▶ [PostgreSQL (primary + read replica)]
            └─▶ [Redis (sentinel HA)]
                  ▲
                  │
[Celery worker pool] ──┘
  ├─ news.collect.high  (8 workers)
  ├─ news.collect.default (4 workers)
  ├─ news.analyze (2 workers, GPU 옵션)
  └─ news.maintenance (2 workers)

[Scheduler — single leader (APScheduler + redis lock)]
```

### 환경 변수

| Key | Default | 설명 |
|---|---|---|
| `NEWSV2_DB_URL` | — | PostgreSQL DSN |
| `NEWSV2_REDIS_URL` | `redis://localhost:6379/1` | Cache + broker |
| `NEWSV2_CELERY_BROKER` | (= REDIS_URL) | Celery broker |
| `NEWSV2_TIER1_INTERVAL_S` | 120 | Tier1 cadence |
| `NEWSV2_TIER2_INTERVAL_S` | 600 | Tier2 cadence |
| `NEWSV2_TIER3_INTERVAL_S` | 3600 | Tier3 cadence |
| `NEWSV2_CACHE_TTL_S` | 600 | news:{symbol} TTL |
| `NEWSV2_AI_DAILY_BUDGET` | 2000 | AI agent 일일 호출 한도 |
| `NEWSV2_ENABLED` | `true` | 마스터 스위치 (false면 모든 v2 작업 no-op) |

### Health endpoints
- `/v2/news/_health` → redis/db/queue 각각 ping.
- `/metrics` → Prometheus.

---

## 15. 예제 코드

→ `backend/news_v2/` 디렉토리의 각 파일 참고.

핵심 흐름 예시 (`service.py`):

```python
async def get_for_symbol(self, symbol: str, limit: int = 20) -> NewsResponse:
    self.cache.incr_view_counter(symbol)
    self.repo.bump_priority(symbol, delta=self.cfg.view_bonus)

    cached = await self.cache.get_articles(symbol)
    if cached:
        status = await self.cache.get_status(symbol) or "READY"
        if status == "STALE":
            self.queue.enqueue_refresh(symbol)
        return NewsResponse(status=status, source="redis", items=cached, stale=status == "STALE")

    rows = await self.repo.list_recent(symbol, limit=limit)
    if rows:
        await self.cache.set_articles(symbol, rows)
        return NewsResponse(status="READY", source="postgres", items=rows, stale=False)

    if await self.cache.acquire_collect_lock(symbol):
        self.queue.enqueue_collect(symbol, priority="high")
    await self.cache.set_status(symbol, "COLLECTING")
    return NewsResponse(status="COLLECTING", source="queue", items=[], stale=False,
                       message="뉴스를 수집하고 있습니다.")
```

---

## 16. Type Definitions

→ `types/news-v2.ts`

---

## 17. Repository Pattern

- `repository.py`는 **순수 DB 입출력만** 책임.
- Service 레이어는 비즈니스 룰 (priority bump, status 전이, AI 호출 결정 등)을 담당.
- 트랜잭션 경계는 service에서 `async with session.begin():` 으로 명시.

```python
class NewsRepository(Protocol):
    async def list_recent(self, symbol: str, limit: int) -> list[Article]: ...
    async def upsert_article(self, a: Article) -> bool: ...    # True if inserted (new hash)
    async def bump_priority(self, symbol: str, delta: float) -> None: ...
    async def set_status(self, symbol: str, status: str, error: Optional[str] = None) -> None: ...
    async def list_symbols_in_tier(self, tier: int, limit: int) -> list[str]: ...
```

---

## 18. Service Layer 분리

| 모듈 | 책임 | 의존성 (주입) |
|---|---|---|
| `NewsService` | 뉴스탭 조회 orchestration | repo, cache, queue |
| `CollectorService` | provider fetch + normalize + dedup + persist | repo, providers, dedup |
| `AnalysisService` | AI agent 호출 + 결과 저장 | repo, agent, cache |
| `PriorityService` | 점수/tier 재계산 + 분포 갱신 | repo, cache |
| `MaintenanceService` | 오래된 데이터 삭제 + 재중복제거 | repo |

각 service는 **stateless**, 의존성은 생성자로 주입 → 테스트는 fake로 대체.

---

## 19. Monitoring

### Prometheus 메트릭

| 이름 | 종류 | 라벨 |
|---|---|---|
| `newsv2_request_total` | counter | symbol, status, source |
| `newsv2_request_latency_seconds` | histogram | route |
| `newsv2_cache_hits_total` | counter | layer (redis/postgres) |
| `newsv2_collect_runs_total` | counter | provider, status |
| `newsv2_collect_latency_seconds` | histogram | provider |
| `newsv2_dedup_rate` | gauge | provider |
| `newsv2_ai_calls_total` | counter | model, outcome |
| `newsv2_queue_depth` | gauge | queue |
| `newsv2_dlq_size` | gauge | — |

### Alerting (예시)
- p95 latency > 500ms 5분 지속 → page
- DLQ size > 50 → ticket
- Redis hit ratio < 70% 30분 지속 → ticket
- AI budget 90% 도달 → notify

---

## 20. Logging

- 구조화 JSON 로그 (`structlog`), 모든 로그에 `correlation_id` (요청 헤더 `X-Request-Id` 또는 신규).
- Celery task는 task_id + symbol을 로그 컨텍스트에 자동 주입.
- 레벨:
  - `INFO`: collect 시작/완료, status 전이
  - `WARN`: dedup rate 급등, AI fallback
  - `ERROR`: provider/AI/DB 예외 (스택 포함)
- PII 없음 (사용자 ID 등은 로그에서 hash).
- 로그 적재: stdout → fluentbit → ELK/Loki.

---

## 부록 — Phase 분할

이 설계는 **Phase A (인프라 없이 SQLite/단일 프로세스로도 동작)** 와 **Phase B (Redis/Celery/PG로 풀 확장)** 두 단계로 점진 적용 가능하다.

- `config.NEWSV2_ENABLED=false` 면 모든 v2 경로 비활성화 (기존 뉴스 시스템 유지).
- `NEWSV2_REDIS_URL` 미설정 → Redis 우회 (PG-only).
- `NEWSV2_CELERY_BROKER` 미설정 → in-process `BackgroundTasks` fallback.

이 점진 도입으로 운영 리스크를 최소화한다.
