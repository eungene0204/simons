# Simons 배포 가이드 — Vultr + Modal + Supabase 하이브리드

이 문서는 Simons의 **실제 운영 중인(as-built)** 배포 구성을 설명한다. 앱 전체는 **Vultr CPU 박스** 1대에 Docker Compose로 올리고, LLM(코치/NL파서/뉴스요약)만 **Modal 서버리스 GPU**에서 Ollama로 서빙한다. 앱 DB는 **Supabase Postgres**, 도메인은 **Namecheap**에서 구매해 Vultr IP로 DNS 연결했다.

> 관련 파일: [`Dockerfile`](../Dockerfile) · [`docker-compose.yml`](../docker-compose.yml) · [`Caddyfile`](../Caddyfile) · [`.dockerignore`](../.dockerignore) · [`modal_ollama.py`](../modal_ollama.py) · [`.env.production.example`](../.env.production.example) · [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)

---

## 0. 핵심 결론 (요약)

- **앱**: Vultr CPU 전용 박스(GPU 없음) 1대 — Docker Compose로 web(Next.js)/backend(FastAPI)/scheduler/news 인프라(redis+postgres)/caddy 기동.
- **LLM**: 자체 GPU 호스팅 대신 **Modal 서버리스 GPU**(`modal_ollama.py`, L4, scale-to-zero)에서 Ollama로 서빙. 앱은 `OLLAMA_HOST` env 하나로 Modal 엔드포인트를 가리킨다.
- **DB**: 옛 SQLite(`prisma/prisma/dev.db`, 11GB)를 폐기하고 **Supabase Postgres**(Pro 플랜)로 완전 이관 완료(2026-07-09~10, fresh start — 과거 데이터는 이관하지 않음). Prisma(Next.js)와 Python 백엔드(`backend/db.py`, psycopg) 둘 다 같은 Postgres를 쓴다.
- **도메인/TLS**: **Namecheap**에서 구매한 `nullstock.im`을 Vultr IP로 A레코드 연결, Caddy가 Let's Encrypt로 자동 TLS 발급.
- **CI/CD**: GitHub Actions 단일 워크플로(`ci.yml`)가 테스트 통과 후 **main push마다 자동으로 Vultr에 SSH 배포 + `prisma migrate deploy`까지 실행**. 수동 배포 불필요.

### 왜 이 구성인가 (경위)

원래 계획은 "로컬 GPU 1대에 9B LLM까지 전부"(Hetzner 등 GPU 박스)였으나, 상시 가동 GPU 비용(€184/mo~) 대비 코치 트래픽이 산발적이라 낭비가 컸다. **LLM만 서버리스 GPU(Modal)로 분리**해 안 쓰면 0원(scale-to-zero)으로 만들고, 나머지(웹/백엔드/스케줄러/DB 클라이언트)는 **싼 CPU 박스(Vultr)** 에 남겼다. Next.js가 python을 직접 spawn하고 `data/` 파일을 fs로 읽는 모놀리스 구조라 웹·백엔드 분리는 여전히 불가능 — 이 부분은 원안과 동일하게 **합본 이미지 1개**를 web/backend/scheduler가 공유한다.

메인 DB는 원래 SQLite(로컬 파일, 앱과 같은 박스 필수)였으나, 트래픽 증가와 Postgres의 동시성·수평확장 이점 때문에 **Supabase Postgres로 이관**했다(§6). DB가 외부화되면서 "메인 DB가 로컬 파일이라 앱과 같은 박스 필수"라는 예전 제약은 사라졌지만, 여전히 python spawn·fs 읽기 구조 때문에 웹·백엔드는 한 박스에 남아 있다.

---

## 1. 아키텍처

```
┌──────────── Namecheap (도메인/DNS) ────────────┐
│  nullstock.im / www.nullstock.im               │
│  A 레코드 → 137.220.41.38                       │
└──────────────────────┬──────────────────────────┘
                        │
┌───────────────────────▼──────────────────────── Vultr 박스 (앱, CPU only) ───┐
│  137.220.41.38 · Ubuntu · 2 vCPU/15GB/112GB · /opt/simons                    │
│                                                                               │
│  Docker Compose (docker-compose.yml):                                        │
│    ├─ caddy        443/80 → web (Let's Encrypt 자동 TLS)                      │
│    ├─ web          Next.js (프론트 + API 라우트)                              │
│    ├─ backend      FastAPI + VirtualTrader — OLLAMA_HOST로 Modal 호출         │
│    ├─ scheduler    매일 OHLCV 동기화 (단일 인스턴스)                          │
│    ├─ redis        news_v2 celery 브로커 (backend가 워커 자체 spawn)          │
│    └─ postgres     news_v2 전용 로컬 Postgres (수집 현재 비활성화)            │
│                                                                               │
│  영속 볼륨(호스트 bind): ./data (parquet/json + chroma)                       │
└───────────────────────┬───────────────────────────────────────────────────────┘
                        │ OLLAMA_HOST (Modal-Key/Modal-Secret 프록시 인증)
┌───────────────────────▼──────────────────────── Modal (서버리스 GPU LLM) ────┐
│  app: simons-ollama · GPU: L4 · min_containers=0 (scale-to-zero)             │
│  https://eugene204--simons-ollama-ollama-server.modal.run                   │
│  모델: hf.co/unsloth/Qwen3.5-4B-GGUF:Q4_K_M (Ollama 네이티브 /api/chat, /v1) │
└───────────────────────────────────────────────────────────────────────────────┘
                        │ DATABASE_URL / DIRECT_URL (pgbouncer 풀러 경유)
┌───────────────────────▼──────────────────────── Supabase (Postgres, 앱 DB) ──┐
│  프로젝트 ref: ydyvilnpmiadinmsoecu · 리전: us-west-1 (N. California) · PG17 │
│  Pro 플랜 · 앱 메인 DB(Prisma 스키마) + Supabase Auth(구글 로그인)            │
│  Vultr가 IPv4-only라 Direct connection 불가 → 반드시 pooler 경유             │
└───────────────────────────────────────────────────────────────────────────────┘
```

**합본 이미지 1개**([`Dockerfile`](../Dockerfile))를 빌드해 web·backend·scheduler가 공유한다. Next.js가 `app/api/backtest/explain/route.ts`에서 `python backend/ai/xai_engine.py`를 spawn하고 여러 라우트가 `data/`를 fs로 읽기 때문에 웹·백엔드가 node+python+코드+데이터를 한 파일시스템에서 공유해야 해서다.

---

## 2. 인프라 구성 요소

### Vultr (앱 박스)
| 항목 | 값 |
|---|---|
| IP | `137.220.41.38` |
| OS | Ubuntu 26.04 |
| 스펙 | 2 vCPU / 15GB RAM / 112GB 디스크 + swap 8G |
| 코드 경로 | `/opt/simons` (git, GitHub **deploy key** 등록됨) |
| SSH | `ssh -i ~/.ssh/vultr_simons root@137.220.41.38` |
| 방화벽 | 22(등록된 IP만)/80/443만 개방. 3000/8000/5432/6379는 외부 차단 |

GPU가 없으므로 로컬 LLM은 돌리지 않는다. 백테스트(vectorbt/optuna)·웹·스케줄러 CPU 워크로드만 처리한다.

### Modal (서버리스 GPU LLM)
| 항목 | 값 |
|---|---|
| 앱 이름 | `simons-ollama` (계정 profile: `eugene204`, `~/.modal.toml`) |
| 엔드포인트 | `https://eugene204--simons-ollama-ollama-server.modal.run` (proxy auth 필수) |
| GPU | L4, `min_containers=0`(scale-to-zero), `scaledown_window=300`초 |
| 모델 | `hf.co/unsloth/Qwen3.5-4B-GGUF:Q4_K_M`(파서/코치) + `hf.co/unsloth/Qwen3.5-9B-GGUF:Q4_K_M`(AI 리포트) — 2모델 동시 서빙(`modal_ollama.py` `MODELS`) |
| 소스 | [`modal_ollama.py`](../modal_ollama.py) — Ollama를 그대로 web_server로 노출(`/api/chat`, `/v1`) |
| 배포 | `modal deploy modal_ollama.py` |

> **2모델 구성(2026-07-21)**: AI 리포트(백테스트 총평)만 9B를 쓰도록 `SUMMARIZE_OLLAMA_MODEL`로 분리했다. 나머지(NL 파서/코치)는 `NL_OLLAMA_MODEL`(4B) 유지. Modal 볼륨에 두 모델을 모두 캐시하고, `.env`의 두 모델명이 각각 `MODELS`에 있어야 한다.
> **인터프리터 9B 승격(2026-07-26)**: 전략 인터프리터(strategy_conversation)는 전용 슬롯 `STRATEGY_INTERPRETER_MODEL`(9B)을 쓴다 — 미설정 시 `NL_OLLAMA_MODEL`(4B)로 폴백하므로 prod `.env`에 명시해야 shadow/primary가 9B로 돈다. 9B는 SUMMARIZE와 같은 모델이라 Modal 추가 배포 불요.

**모델 전환/추가 절차(3단계)**:
1. `.venv/bin/modal run modal_ollama.py::download_model` — `MODELS`의 모든 모델을 볼륨(`simons-ollama-models`)에 캐시(~2분/모델)
2. `.venv/bin/modal deploy modal_ollama.py`
3. Vultr `/opt/simons/.env`의 `NL_OLLAMA_MODEL`/`SUMMARIZE_OLLAMA_MODEL`을 동일 모델명으로 변경 후:
   ```bash
   cd /opt/simons && docker compose up -d --no-build --no-deps --force-recreate backend web
   ```
   (`env_file`이라 `restart`가 아니라 `recreate` 필요. postgres/redis는 보존됨)

**콜드스타트 대응(중요 — 3중 방어)**: scale-to-zero 컨테이너로의 첫 POST는 body가 유실되므로 다음이 모두 필요하다.
- **Body 없는 GET `/api/tags`로 선warmup**한 뒤 POST(`_ollama_ensure_warm`, 예산 200초)
- 네이티브 `/api/chat` 사용 + `think:false` + `options.num_ctx=16384`(`/v1` 엔드포인트는 num_ctx 무시하므로 반드시 `/api/chat`)
- Next 프록시(`lib/server/backend.ts`)는 Node 내장 fetch(undici) 기본 `headersTimeout=300s`를 우회하기 위해 **undici 자체 `Agent({headersTimeout:0, bodyTimeout:0})`** 사용, `COACH_TIMEOUT_MS=560000`

콜드 e2e 실측: 첫 요청 ~90~320초(모델 크기·컨테이너 상태에 따라), 5분 내 재요청은 웜(수초).

### Supabase (앱 DB + Auth)
| 항목 | 값 |
|---|---|
| 프로젝트 ref | `ydyvilnpmiadinmsoecu` |
| 리전 | us-west-1 (N. California) — Vultr가 미국 서부(시애틀 인근)라 맞춤 선택 |
| 플랜 | Pro |
| PG 버전 | 17.6 |
| 용도 | Prisma 메인 스키마(앱 DB) + Supabase Auth(구글 로그인) |

**연결은 반드시 pooler 경유** — Vultr 박스가 IPv4-only라 Supabase Direct connection(IPv6)을 못 쓴다.
- `DATABASE_URL` (런타임) = **Transaction pooler**, 포트 6543, `?pgbouncer=true`
- `DIRECT_URL` (마이그레이션/Prisma `directUrl`) = **Session pooler**, 포트 5432
- 형식: `postgresql://postgres.<ref>:<password>@aws-0-us-west-1.pooler.supabase.com:<port>/postgres`

Python 백엔드는 `backend/db.py`(psycopg v3 어댑터, sqlite3와 유사한 인터페이스)로 동일 DB에 접근한다. 이관은 **fresh start**(옛 SQLite 데이터 이관 안 함) + **뉴스 DB는 이관 대상에서 제외**(수집 자체가 중단 상태라 로컬 postgres 컨테이너에 그대로 둠).

### Namecheap (도메인/DNS)
- 도메인 `nullstock.im`을 Namecheap에서 구매.
- Namecheap DNS에 A레코드: `www.nullstock.im`, `nullstock.im`(apex) 둘 다 → `137.220.41.38`.
- TLS는 Namecheap이 아니라 **Caddy가 Let's Encrypt로 자동 발급**(HTTP-01 챌린지) — Namecheap 쪽은 DNS만 담당.
- `.env`: `DOMAIN=www.nullstock.im`, `APEX_DOMAIN=nullstock.im`([`Caddyfile`](../Caddyfile)이 apex→www 301 리다이렉트 처리).
- ⚠️ **raw IP로는 ACME 발급 불가** — DNS가 해석되기 전에 컨테이너를 띄우면 Let's Encrypt 요청이 반복 실패해 rate limit 위험. DNS 전파 확인 후 `DOMAIN` 설정할 것.

---

## 3. 사전 준비물

### 발급/확보할 키 (`.env` — [`.env.production.example`](../.env.production.example) 참고)
| 변수 | 용도 |
|---|---|
| `OLLAMA_HOST` | Modal Ollama 엔드포인트 |
| `MODAL_KEY` / `MODAL_SECRET` | Modal proxy auth (웹 콘솔 Settings에서 발급) |
| `NL_OLLAMA_MODEL` | 파서/코치용 모델 — Modal이 서빙 중인 모델명과 반드시 동일(4B) |
| `SUMMARIZE_OLLAMA_MODEL` | AI 리포트(백테스트 총평) 전용 모델(9B). 미설정 시 `NL_OLLAMA_MODEL`로 폴백. Modal `MODELS`에 포함돼야 함 |
| `STRATEGY_INTERPRETER_MODEL` | 전략 인터프리터(strategy_conversation) 전용 모델(9B). 미설정 시 `NL_OLLAMA_MODEL`(4B)로 폴백 — shadow/primary 모두 이 슬롯을 읽으므로 prod에 명시 필수 |
| `DATABASE_URL` / `DIRECT_URL` | Supabase Postgres (transaction/session pooler) |
| `NEWSV2_PG_PASSWORD` | 로컬 news_v2 Postgres 컨테이너 비밀번호 |
| `KRX_API_KEY` | KRX 시세 |
| `KIS_APP_KEY` / `KIS_APP_SECRET` | 한국투자증권 API(자동매매) |
| `DART_API_KEY` | DART 공시 |
| `PUBLIC_DATA_SERVICE_KEY` | 공공데이터포털 |
| `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_ANON_KEY` | 프론트 Supabase Auth(구글 로그인) — **빌드 타임에 번들 인라인**이라 값 채운 뒤 반드시 재빌드 |
| `TOSS_SECRET_KEY` / `NEXT_PUBLIC_TOSS_CLIENT_KEY` | 토스페이먼츠 자동결제·빌링(유료 플랜 정기 구독). 실결제 전 테스트 키→**빌링 계약된** 라이브 상점 키로 교체 필수(§9). `NEXT_PUBLIC_TOSS_CLIENT_KEY`는 **빌드 타임 번들 인라인**(Dockerfile ARG + compose build args 배선) — 값 변경 시 재빌드 필수 |
| `JWT_SECRET`, `SCHEDULER_SECRET` | 인증/스케줄러 보호(임의 난수) |
| `DOMAIN`, `APEX_DOMAIN` | Caddy TLS 대상 도메인 |

---

## 4. 서버 초기 셋업 (Vultr)

```bash
# OS: Ubuntu 26.04

# 1) 방화벽: 22(본인 IP), 80, 443만
# 2) swap (빌드 OOM 방지)
sudo fallocate -l 8G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# 3) Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # 재로그인
```

> GPU 박스가 아니므로 NVIDIA 드라이버·Ollama 호스트 설치는 불필요 — LLM은 전부 Modal에서 서빙한다.

---

## 5. 소스 · 데이터 시드

```bash
sudo mkdir -p /opt/simons && cd /opt/simons
git clone <REPO_URL> . # 또는 GitHub deploy key로 clone
```

### DB 시드는 불필요
Supabase는 fresh start로 이관했으므로 SQLite 백업/rsync 같은 시딩 절차가 없다. 스키마는 배포 시 CI/CD가 `prisma migrate deploy`로 자동 적용한다(§8).

### parquet 데이터 동기화
정본(source of truth)은 프로덕션 박스 자신이다. 로컬 개발 환경에서 프로덕션 데이터를 당겨오려면:
```bash
npm run pull-data          # scripts/mirror_data.py — 프로덕션 → 로컬
npm run pull-data:check    # 드라이런
```
`.env`의 `DATA_MIRROR_REMOTE=root@137.220.41.38:/opt/simons` / `DATA_MIRROR_SSH_KEY`가 대상을 지정한다. **프로덕션에는 이 두 변수를 절대 설정하지 말 것**(자기 자신을 미러하게 됨).

---

## 6. 환경변수 (`.env`)

`.env.production.example`을 `/opt/simons/.env`로 복사 후 값을 채운다(커밋 금지):

```dotenv
# --- LLM (Modal 서버리스 GPU) ---
OLLAMA_HOST=https://eugene204--simons-ollama-ollama-server.modal.run
MODAL_KEY=wk-...
MODAL_SECRET=ws-...
NL_OLLAMA_MODEL=hf.co/unsloth/Qwen3.5-4B-GGUF:Q4_K_M

# --- 앱 DB (Supabase Postgres, pooler 경유) ---
DATABASE_URL=postgresql://postgres.ydyvilnpmiadinmsoecu:<password>@aws-0-us-west-1.pooler.supabase.com:6543/postgres?pgbouncer=true
DIRECT_URL=postgresql://postgres.ydyvilnpmiadinmsoecu:<password>@aws-0-us-west-1.pooler.supabase.com:5432/postgres

# --- 뉴스 Postgres (박스 내 로컬 컨테이너 — Supabase 아님) ---
NEWSV2_PG_PASSWORD=<random>

# --- 프론트 Supabase Auth ---
# ⚠ 빌드 타임 인라인 — 값 채운 뒤 반드시 docker compose build 재실행
NEXT_PUBLIC_SUPABASE_URL=https://ydyvilnpmiadinmsoecu.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon-key>

# --- 토스페이먼츠(유료 플랜 정기 구독 — 자동결제/빌링 계약된 MID 키) ---
TOSS_SECRET_KEY=<live-secret-key>
NEXT_PUBLIC_TOSS_CLIENT_KEY=<live-client-key>

# --- 외부 API ---
KRX_API_KEY=...
KIS_APP_KEY=...
KIS_APP_SECRET=...
DART_API_KEY=...
PUBLIC_DATA_SERVICE_KEY=...

# --- 시크릿 ---
JWT_SECRET=<random>
SCHEDULER_SECRET=<random>

# --- 도메인(Namecheap DNS → Caddy 자동 TLS) ---
DOMAIN=www.nullstock.im nullstock.im
APEX_DOMAIN=nullstock.im

# --- 기동 데드락 가드 (필수! §7) ---
KMP_DUPLICATE_LIB_OK=TRUE
OMP_NUM_THREADS=1
POLARS_MAX_THREADS=1
```

---

## 7. 기동 데드락 가드 (필수)

이 가드 3종이 없으면 백엔드가 startup에서 **무한정지**한다(XGBoost OpenMP 충돌, Polars rayon latch). `.env`에 반드시 포함 — compose가 backend에 주입한다.

```
KMP_DUPLICATE_LIB_OK=TRUE   # OpenMP 중복 로드 segfault 회피
OMP_NUM_THREADS=1
POLARS_MAX_THREADS=1        # AI 인프로세스 백테스트 polars 무한정지 회피
```

---

## 8. Docker 빌드 & 기동 / CI-CD 자동배포

수동 기동(최초 셋업 또는 긴급 시):
```bash
docker compose build      # 합본 이미지(node+python) 빌드
docker compose up -d      # 전체 기동
npx prisma migrate deploy # 스키마 반영 (Supabase Postgres, shadow DB 불필요)
docker compose logs -f backend
```

**평상시는 완전 자동**: `.github/workflows/ci.yml`의 `deploy` job이 `main` push마다(또는 `workflow_dispatch`) 다음을 SSH로 실행한다.
```
git fetch origin main && git reset --hard origin/main
docker compose build --pull --force-rm
docker compose run --rm --workdir /app backend npx prisma migrate deploy   # Supabase에 자동 적용
docker compose up -d --remove-orphans
```
- `reset --hard`인 이유: 박스가 런타임 산출물(`data/universe-history.json` 등)로 더럽혀져 ff-only pull이 실패하기 때문.
- 마이그레이션 실패 시 `set -e`로 배포가 중단되고 **구버전 컨테이너가 계속 떠 있어 서비스는 안 죽는다**.
- 필수 GitHub Secrets: `VULTR_SSH_HOST`(=137.220.41.38), `VULTR_SSH_USER`, `VULTR_SSH_KEY`.

**서비스 구성**([`docker-compose.yml`](../docker-compose.yml)):

| 서비스 | 역할 | 비고 |
|---|---|---|
| `web` | Next.js (프론트 + API 라우트) | python spawn·fs 위해 `data` 볼륨 공유 |
| `backend` | FastAPI + VirtualTrader | `OLLAMA_HOST`로 Modal 접속, Supabase Postgres에 DB 접근 |
| `scheduler` | 매일 OHLCV 동기화 | **단일 인스턴스**(중복 금지) |
| `redis`, `postgres` | 뉴스(news_v2) 인프라 | postgres는 **로컬 컨테이너**(Supabase 아님). 뉴스 수집은 현재 `NEWSV2_COLLECTION_ENABLED=false`로 비활성 |
| `caddy` | TLS 리버스 프록시 | 443/80 → web:3000, Namecheap DNS 대상 도메인에 Let's Encrypt |

> 뉴스 celery 워커/스케줄러는 별도 서비스가 아니라 `backend`가 startup에서 직접 spawn한다(이중 디스패치 방지).

> **합본 이미지 주의**: `backend/requirements.txt`에 mlx-lm이 있으면 리눅스 빌드 실패(맥 전용, 코드에서 조건부 import). torch는 `+cpu` 휠로 선설치(Modal에만 GPU가 있으므로 앱 박스엔 CPU torch로 충분).

---

## 9. 배포 전 체크리스트

- [ ] `curl <Modal 엔드포인트>/api/tags`가 Modal-Key/Modal-Secret 헤더로 200 응답(모델 목록에 `NL_OLLAMA_MODEL`·`SUMMARIZE_OLLAMA_MODEL` 두 모델 모두 포함)
- [ ] `backend/requirements.txt`에 mlx-lm 없음(리눅스 빌드 통과)
- [ ] Supabase `DATABASE_URL`(6543+pgbouncer)/`DIRECT_URL`(5432) pooler 경유로 설정, Direct connection 아님
- [ ] `data/`(parquet + chroma) 준비(`npm run pull-data` 또는 스케줄러가 채움)
- [ ] §7 데드락 가드 3종 주입
- [ ] `.env`의 `DOMAIN`/`APEX_DOMAIN` 지정 + Namecheap DNS가 Vultr IP로 해석됨을 확인 후 기동(TLS rate limit 방지)
- [ ] 방화벽 80/443만 개방(3000/8000/5432/6379 비공개)
- [ ] 토스페이먼츠 **자동결제(빌링) 계약 완료된 상점의 라이브 키**로 교체 — 테스트 키로 실결제 불가, 빌링 미계약 키는 `NOT_SUPPORTED_METHOD` 에러
- [ ] prod DB에 빌링 마이그레이션 적용 확인(`User.tossBillingKey`/`subscriptionPlanId`/`nextBillingAt`/`subscriptionCanceledAt`/`billingFailCount` — CI 배포는 마이그레이션을 실행하지 않음)
- [ ] GitHub Secrets(`VULTR_SSH_HOST/USER/KEY`) 등록 확인

---

## 10. 백업

### Supabase Postgres (앱 DB)
Pro 플랜의 자동 백업(일별/PITR, 플랜 조건에 따름)에 의존. 별도 스크립트 불필요 — 예전 SQLite Litestream 방식은 이관 후 폐기.

### 로컬 news Postgres
`postgres` 컨테이너(`pgdata` 볼륨)는 뉴스 수집이 비활성 상태라 우선순위 낮음. 필요 시 `pg_dump` 또는 재생성(수집 재개 시 재구축 가능).

### parquet/chroma (`data/`)
`npm run pull-data`(프로덕션이 정본) 또는 재수집 스크립트로 재생성 가능 — 우선순위 낮음.

---

## 11. 운영

```bash
# 수동 재배포(보통은 git push main으로 자동)
git pull && docker compose build && docker compose up -d
npx prisma migrate deploy        # 스키마 변경 시(자동배포는 이미 포함)

# 로그 / 상태
docker compose logs -f <service>
docker compose ps
curl -s http://localhost:8000/model/status   # Modal LLM 연결 상태

# LLM 모델 전환은 §2 "모델 전환 절차(3단계)" 참고
```
- `restart: unless-stopped`로 크래시 자동 복구
- VirtualTrader는 backend 컨테이너 내부 동작 → backend 살아있으면 함께 동작

---

## 12. 스케일 한계 / 향후 과제

- **Modal 콜드스타트(~90~320초)**: scale-to-zero 트레이드오프. 완화책(GET warmup, num_ctx, undici 타임아웃)은 이미 적용됨(§2). 더 줄이려면 `scaledown_window` 상향(상시과금↑) 또는 `min_containers=1`.
- **Vultr 2 vCPU**: 백테스트 동시 처리량이 코어 수에 비례. 느려지면 인스턴스 리사이즈.
- **앱 수평 확장**: DB는 이미 Postgres(Supabase)로 외부화되어 있어 이전보다 수월하지만, **VirtualTrader·scheduler는 반드시 단일 워커**로 유지해야 한다(중복 주문/중복 동기화 방지) — 여러 대로 늘리려면 이 두 서비스만 별도 분리.
- **뉴스 시스템**: 현재 수집 비활성(`NEWSV2_COLLECTION_ENABLED=false`). 재개 시 로컬 postgres 컨테이너 부하·Supabase 통합 여부를 재검토.

지금 단계에선 위 모두 YAGNI. 병목이 실제로 보일 때 대응한다.
