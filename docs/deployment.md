# Simons 배포 가이드 — 로컬 LLM(GPU) + 단일 박스

이 문서는 Simons를 **자체 GPU 서버 1대**에 **로컬 LLM(Ollama)** 으로 배포하는 절차서다.
외부 LLM API를 쓰지 않고 9B 모델을 인하우스로 구동하는 것을 전제로 한다.

> 관련 파일(이미 저장소에 있음): [`Dockerfile`](../Dockerfile) · [`docker-compose.yml`](../docker-compose.yml) · [`Caddyfile`](../Caddyfile) · [`.dockerignore`](../.dockerignore)

---

## 0. 핵심 결론 (요약)

- **로컬 LLM 전제** → 전략 코칭이 **9B 모델**을 쓰고, 9B는 CPU에서 1~2분이라 **GPU 필수**.
- **단일 GPU 박스 1대에 전부** 올린다(Next.js·FastAPI·스케줄러·뉴스·Ollama·SQLite). Docker Compose로 한 번에 기동.
- **1순위 호스팅: Hetzner GEX44** (RTX 4000 Ada 20GB / 64GB RAM / 14코어, **€184/mo**). 9B에 VRAM 여유, GPU 포함 최저가.
- 외부 API·서버리스·다중 VM 분리는 **지금 단계에선 부적합**(아래 이유). 트래픽이 커지면 §13.

### 왜 단일 박스 모놀리스인가
Simons는 **상태(stateful) + 상시 실행 + 무거운 컴퓨팅 + 로컬파일 결합** 앱이다.

- **메인 DB가 SQLite**(`prisma/prisma/dev.db`, **현재 11GB**) → 단일 프로세스 + 영속 디스크 필수. 로컬 파일이라 원격에 못 둠 → 앱과 **반드시 같은 박스**.
- **Next.js가 python을 직접 실행**: `app/api/backtest/explain/route.ts`가 `python backend/ai/xai_engine.py`를 spawn하고, 여러 라우트가 `data/` 파일을 `fs`로 읽음 → 웹·백엔드가 **node+python+코드+데이터를 한 파일시스템에서 공유**해야 함(=합본 이미지).
- **로컬 parquet 직접 읽기**: `data/ohlcv/*`(324MB), `data/training_data_v3.parquet`(144MB) → 영속 디스크.
- **상시 데몬 2개**: 스케줄러(`scripts/scheduler.py`, 매일 00:00 KST OHLCV 동기화) + VirtualTrader(`backend/engine/virtual_trader.py`, FastAPI 인프로세스 자동매매).
- **로컬 LLM**: 코치/NL파서/요약이 **기본적으로 Ollama**로 9B를 호출(`resolve_llm_backend()`가 백엔드 결정, 기본값 ollama. `OLLAMA_HOST`로 주소 지정). MLX는 맥 dev에서 `LLM_BACKEND=mlx`로 옵트인할 때만.

→ 서버리스(Vercel) 불가, 앱 티어 다중 분리 불가. **GPU 박스 1대 + Docker**가 정답.

---

## 1. 아키텍처

```
┌─────────────── GPU 서버 1대 (예: Hetzner GEX44) ───────────────┐
│                                                                │
│  호스트:  Ollama (9B, GPU 네이티브, OLLAMA_HOST=0.0.0.0:11434)  │
│                                                                │
│  Docker Compose (docker-compose.yml):                          │
│    ├─ caddy        443/80 → web (자동 TLS)                      │
│    ├─ web          Next.js (프론트 + 86 API 라우트)            │
│    ├─ backend      FastAPI + VirtualTrader                     │
│    ├─ scheduler    매일 OHLCV 동기화                           │
│    ├─ news-worker  Celery (뉴스 수집/분석)                     │
│    ├─ news-scheduler                                           │
│    ├─ redis                                                    │
│    └─ postgres     뉴스 전용(또는 Supabase로 외부화)          │
│                                                                │
│  영속 볼륨(호스트 bind):                                       │
│    ./prisma/prisma  → 11GB SQLite (메인 DB = 코치 코퍼스)      │
│    ./data           → 9GB parquet/json + Chroma 벡터스토어     │
└────────────────────────────────────────────────────────────────┘
```

**합본 이미지 1개**([`Dockerfile`](../Dockerfile))를 빌드해 web·backend·scheduler·news-* 가 공유한다. Next가 python을 spawn하는 모놀리스 구조라 분리가 불가능하기 때문이다.

---

## 2. 호스팅 선택

### 1순위 — Hetzner GEX44 (단일 GPU 박스, 권장)

| 항목 | 사양 | 적합성 |
|---|---|---|
| GPU | RTX 4000 SFF Ada **20GB** | 9B Q4(~6GB)에 VRAM 3배 여유, fp16(~18GB)도 가능. 40~55 tok/s → 코치 응답 **8~15초** |
| CPU | i5-13500, **14코어** | 백테스트(vectorbt/optuna) + 웹 동시 처리 |
| RAM | **64GB** | parquet + 다중 백테스트 + OS 페이지캐시(11GB DB 핫셋) |
| 디스크 | 2×1.92TB NVMe | 11GB DB + 9GB data + 백업 충분 |
| 비용 | **€184/mo + €79(1회)** | GPU 포함 최저가(AWS 서울의 1/3~1/4) |
| 위치 | Falkenstein (EU) | ⚠️ 한국까지 ~250ms |

### 트레이드오프 — EU 저비용 vs 한국 저지연
GEX44는 EU 전용이라 한국 사용자·KIS/KRX/DART API까지 ~250ms.
- **대부분의 경우 괜찮음(권장)**: 일봉 백테스트·리서치 도구이고 HFT가 아님. 코치 응답은 이미 8~15초라 +250ms 무의미.
- **한국 저지연/데이터 residency가 중요하면** → 2순위. **금융 데이터 국내보관 규제 여부를 먼저 확인**할 것(있으면 EU 불가).

### 2순위 — 한국 리전 (저지연 우선, 비용↑)
| 옵션 | 비용(상시) | 특징 |
|---|---|---|
| Naver Cloud / KT Cloud GPU | 영업 견적 | 한국 DC, 데이터 residency, KIS/KRX 근접 |
| AWS 서울 g5/g6 (A10/L4 24GB) | g5 ~$1.0/hr ≈ **$730/mo**(+RDS 등) | 표준·안정적, GEX44의 3~4배 |

### 3순위 — 서버리스 GPU (코칭 트래픽이 적고 산발적일 때)
싼 CPU 앱 박스 + RunPod/Modal 서버리스 GPU(Ollama)로 분리. **scale-to-zero**라 안 쓰면 0원이지만 **콜드스타트**(RunPod 5~20초, Modal 2~4초)로 첫 코치 응답이 느림. 코치가 하루 몇 GPU-시간 수준이면 GEX44보다 쌀 수 있음.

### 동시 처리량(현실 인지)
- **둘러보기**(페이지/조회): 수십~100명 쾌적
- **백테스트**: 약 4~8건 동시(코어 수). 데드락 가드로 각 건은 단일 스레드
- **코치(LLM)**: 앱 레벨 전역 추론 락은 **Ollama에선 no-op**(MLX 전용)이라 동시 코칭이 가능하다. 동시 처리량은 호스트의 **`OLLAMA_NUM_PARALLEL` + VRAM**이 결정(9B 1건 8~15초). 천장을 더 올리려면 §13.

---

## 3. 사전 준비물

### 발급/확보할 키 (`.env`)
| 변수 | 용도 |
|---|---|
| `KRX_API_KEY` | KRX 시세 |
| `KIS_APP_KEY` / `KIS_APP_SECRET` | 한국투자증권 API(자동매매) |
| `DART_API_KEY` | DART 공시 |
| `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_ANON_KEY` | 프론트 Supabase 인증 |
| `JWT_SECRET`, `SCHEDULER_SECRET` | 인증/스케줄러 보호(임의 난수) |
| `OPENAI_API_KEY`, `GOOGLE_API_KEY` | (옵션) LLM 보조 — 로컬 전제에선 미사용 가능 |

### 확정할 것
- **운영 9B 모델명** — Ollama `pull` 대상 + `NL_OLLAMA_MODEL` 값(예: `gemma2:9b` 등). VRAM 사이징도 여기서 결정.

---

## 4. 서버 초기 셋업

```bash
# OS: Ubuntu 22.04/24.04 LTS

# 1) 방화벽: 22(본인 IP), 80, 443만. 3000/8000/11434/5432는 외부 차단
# 2) swap (빌드/로드 OOM 방지)
sudo fallocate -l 8G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# 3) NVIDIA 드라이버 확인
nvidia-smi

# 4) Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # 재로그인

# 5) Ollama (호스트 직접 설치 — 컨테이너 아님, GPU 네이티브)
curl -fsSL https://ollama.com/install.sh | sh
```

> **Ollama는 왜 호스트?** 컨테이너 GPU 패스스루(nvidia-container-toolkit) 설정을 피하려고. 컨테이너는 `host.docker.internal:11434`로 접속한다(compose에 설정됨).

---

## 5. LLM (Ollama 9B) 구성

```bash
# 9B 모델 받기 (모델명은 §3에서 확정한 값)
ollama pull <YOUR_9B_MODEL>

# 컨테이너가 닿도록 0.0.0.0 바인딩 + 모델 상주 설정
sudo systemctl edit ollama
#   [Service]
#   Environment="OLLAMA_HOST=0.0.0.0:11434"     # 기본 127.0.0.1이면 컨테이너에서 접속 불가
#   Environment="OLLAMA_KEEP_ALIVE=-1"          # 9B를 VRAM에 상주(매 요청 재로딩 방지)
#   Environment="OLLAMA_NUM_PARALLEL=2"         # 동시 코치 요청(VRAM 여유 내에서)
sudo systemctl restart ollama

# 확인
curl http://localhost:11434/api/tags     # 9B 모델이 보이면 OK
```

---

## 6. 소스 · 데이터 · DB 시드

```bash
sudo mkdir -p /srv/simons && sudo chown $USER /srv/simons
cd /srv/simons && git clone <REPO_URL> app && cd app
```

### 11GB SQLite 시드 (메인 DB = 코치 코퍼스)
git 불가·재생성 불가(누적된 실 백테스트 결과). **파일을 그대로 전송**:
```bash
# 로컬(Mac)에서: 일관된 스냅샷 → 압축 전송
sqlite3 prisma/prisma/dev.db ".backup '/tmp/dev-seed.db'"
rsync -azP /tmp/dev-seed.db user@server:/srv/simons/app/prisma/prisma/dev.db
```
- 옮긴 뒤 **서버 사본이 정본**이 되어 거기서 계속 커짐. RAM 11GB 안 먹음(SQLite는 디스크 페이징).
- Chroma 벡터스토어(코치가 함께 사용)도 `data/` 안에 있으니 같이 전송하거나 서버에서 재생성.

### parquet 데이터 시드
```bash
# 전송하거나, 서버에서 동기화 스크립트로 생성(수십 분)
python3 scripts/sync_data.py
```

### 메인 DB 마이그레이션
```bash
npx prisma migrate deploy    # 11GB 기존 DB에 스키마 차이만 적용(안전). migrate dev 아님
```

---

## 7. 환경변수 (`.env`)

저장소 루트에 생성(커밋 금지 — `.gitignore` 처리됨):

```dotenv
# --- 도메인/TLS ---
DOMAIN="simons.example.com"

# --- 메인 DB (SQLite, 영속) ---
DATABASE_URL="file:./prisma/dev.db"

# --- 뉴스 Postgres (박스 내 컨테이너) ---
NEWSV2_PG_PASSWORD="<random>"
NEWSV2_DB_URL="postgresql+asyncpg://simons:<random>@postgres:5432/simons_news"
#   ↑ Supabase로 빼려면 이 줄을 Supabase 주소로 바꾸고 compose의 postgres 서비스 삭제

# --- 프론트 ---
NEXT_PUBLIC_SUPABASE_URL="https://<proj>.supabase.co"
NEXT_PUBLIC_SUPABASE_ANON_KEY="<anon-key>"
BACKEND_URL="http://backend:8000"
APP_URL="https://simons.example.com"

# --- 로컬 LLM (Ollama) ---
# LLM_BACKEND 기본값이 ollama라 보통 불필요. 맥 dev에서 MLX를 쓸 때만 LLM_BACKEND=mlx
OLLAMA_HOST="http://host.docker.internal:11434"
NL_OLLAMA_MODEL="<YOUR_9B_MODEL>"

# --- 외부 API ---
KRX_API_KEY="..."
KIS_APP_KEY="..."
KIS_APP_SECRET="..."
DART_API_KEY="..."

# --- 시크릿 ---
JWT_SECRET="<random>"
SCHEDULER_SECRET="<random>"

# --- 벡터스토어/캐시 경로 ---
ADVISOR_CHROMA_PATH="/app/data/chroma"
NUMBA_CACHE_DIR="/tmp/numba"
MPLCONFIGDIR="/tmp/mpl"

# --- 기동 데드락 가드 (필수! §9) ---
KMP_DUPLICATE_LIB_OK="TRUE"
OMP_NUM_THREADS="1"
POLARS_MAX_THREADS="1"
```

---

## 8. Docker 빌드 & 기동

```bash
docker compose build      # 합본 이미지(node+python) 1회 빌드 — 수 GB, 시간 소요
docker compose up -d      # 전체 기동
docker compose logs -f backend   # 모델/기동 로그 확인
```

**서비스 구성**([`docker-compose.yml`](../docker-compose.yml)):

| 서비스 | 역할 | 비고 |
|---|---|---|
| `web` | Next.js (프론트 + API 라우트) | python spawn·fs 위해 data 볼륨 공유 |
| `backend` | FastAPI + VirtualTrader | `OLLAMA_HOST`로 호스트 Ollama 접속 |
| `scheduler` | 매일 OHLCV 동기화 | **단일 인스턴스**(중복 금지) |
| `news-worker` / `news-scheduler` | 뉴스 수집/분석 Celery | |
| `redis`, `postgres` | 뉴스 인프라 | postgres는 Supabase로 대체 가능 |
| `caddy` | TLS 리버스 프록시 | 443 → web:3000 |

> **합본 이미지 주의**: `backend/requirements.txt`에 **mlx-lm이 있으면 리눅스 빌드 실패**(맥 전용). 코드에서 조건부 import되므로 리눅스에선 Ollama만 쓰면 됨. requirements에 OS 라이브러리가 더 필요하면 [`Dockerfile`](../Dockerfile)의 `apt-get` 줄을 보강하며 반복.

---

## 9. 기동 데드락 가드 (필수)

이 가드 3종이 없으면 백엔드가 startup에서 **무한정지**한다(XGBoost OpenMP 충돌, Polars rayon latch). `.env`에 반드시 포함(§7) — compose가 backend에 주입한다.

```
KMP_DUPLICATE_LIB_OK=TRUE   # OpenMP 중복 로드 segfault 회피
OMP_NUM_THREADS=1
POLARS_MAX_THREADS=1        # AI 인프로세스 백테스트 polars 무한정지 회피
```

---

## 10. 백업

### 11GB SQLite — Litestream 권장
매일 11GB 풀 카피는 낭비. **Litestream로 WAL 변경분을 S3/R2에 연속 복제**:
- 거의 실시간 백업, 장애 시 11GB DB 그대로 복원, 증분이라 저렴
- 대안: 주간 `sqlite3 .backup` + 압축 오프사이트(RPO 큼)

### 그 외
- **postgres(뉴스)**: `pg_dump` 일배치 또는 Supabase 자체 백업
- **Chroma·parquet**: 백테스트/`sync_data`로 재생성 가능(우선순위 낮음, 단 재생성 느림)

---

## 11. 운영

```bash
# 업데이트 배포
git pull && docker compose build && docker compose up -d
npx prisma migrate deploy        # 스키마 변경 시

# 로그 / 상태
docker compose logs -f <service>
docker compose ps
curl -s http://localhost:8000/model/status   # LLM 로딩 상태
```
- `restart: unless-stopped`로 크래시 자동 복구
- VirtualTrader는 backend 컨테이너 내부 동작 → backend 살아있으면 함께 동작

---

## 12. 배포 전 체크리스트

- [ ] `nvidia-smi` GPU 인식 + `ollama pull <9B>` 완료, `curl :11434/api/tags` 확인
- [ ] Ollama `OLLAMA_HOST=0.0.0.0` (컨테이너 접근 가능)
- [ ] `backend/requirements.txt`에 mlx-lm 없음(리눅스 빌드 통과)
- [ ] 11GB `prisma/prisma/dev.db` 시드 전송 + 영속 bind 마운트 확인
- [ ] `data/`(parquet + chroma) 준비
- [ ] §9 데드락 가드 3종 주입
- [ ] `.env`의 `DOMAIN` 지정 + Caddy TLS 발급
- [ ] 방화벽 80/443만 개방
- [ ] Litestream 백업 가동

---

## 13. 스케일 한계 / 향후 과제

현재 구성은 **단일 박스·단일 백엔드 프로세스**까지 안전. 트래픽이 커지면:

1. **코치 동시성** — 앱 레벨 전역 락은 Ollama에서 이미 해제(no-op)됨. 천장은 호스트 `OLLAMA_NUM_PARALLEL` + VRAM. 상향해도 부족하면 **Ollama를 별도 GPU 인스턴스/서버리스로 분리**(`OLLAMA_HOST`만 변경).
2. **11GB SQLite 무한 증가** — `BacktestResult`가 백테스트마다 누적. 쓰기 락 경합·백업 부담이 커지면 **그 테이블만 Postgres로 분리**(뉴스 PG에 합침, 단 코치 `sqlite3` 직접 조회라 코드 변경). 더 가벼운 대안: 오래된 결과 **아카이브/프루닝**.
3. **앱 수평 확장** — 웹/API를 여러 대로 늘리려면 SQLite→Postgres 이관 + **VirtualTrader·스케줄러는 반드시 단일 워커**로 분리(중복 주문/중복 동기화 방지).

지금 단계에선 위 모두 **YAGNI**. 단일 GPU 박스로 시작하고 병목이 실제로 보일 때 1번부터.
