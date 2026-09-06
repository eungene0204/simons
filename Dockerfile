# Simons 합본 앱 이미지 (node + python)
# ─────────────────────────────────────────────────────────────────────────────
# 이 앱은 모놀리스다: Next.js(app/api)가 child_process로 python(backend/ai/xai_engine.py)을
# 직접 실행하고, fs로 data/ 파일을 읽는다. 따라서 웹·백엔드·스케줄러·뉴스워커가 모두
# "node + python + 전체 코드"를 필요로 한다 → 이미지 하나로 굽고 서비스별 command만 다르게.
#
# ⚠️ 초안: 의존성에 OS 라이브러리가 더 필요한 패키지가 있으면 빌드가 실패할 수 있다.
#    그럴 땐 아래 apt-get 줄에 필요한 -dev 패키지를 추가하며 반복한다.
# ⚠️ mlx-lm(macOS 전용)은 pyproject.toml의 mac 그룹에 `sys_platform == 'darwin'` 마커로
#    묶여 있어 리눅스 빌드에는 애초에 들어오지 않는다(종전엔 사람이 지켜야 하는 규칙이었다).
# ─────────────────────────────────────────────────────────────────────────────
FROM node:24-slim

# uv — 파이썬 런타임과 의존성을 uv.lock 그대로 재현 설치한다(버전 핀: 빌드 재현성).
# Debian의 python3를 쓰지 않는다. 지금은 node:24-slim이 bookworm이라 우연히 3.11.2지만
# 그건 베이스 이미지 태그가 정하는 값이고, 베이스가 올라가면 예고 없이 따라 올라간다
# (Modal 워커·CI는 3.11 고정). uv가 .python-version의 3.11을 직접 받아 쓰면 세 곳이
# 베이스 이미지와 무관하게 같은 마이너 버전으로 묶인다. 덤으로 --break-system-packages도 사라진다.
COPY --from=ghcr.io/astral-sh/uv:0.12.9 /uv /uvx /usr/local/bin/

# 빌드도구 + sqlite(11GB DB 조회) + openssl(prisma) + curl + CA 저장소
# ca-certificates: uv가 설치한 Python(python-build-standalone)은 /etc/ssl/certs를 신뢰 저장소로
# 쓴다. node:slim 베이스에는 이 디렉터리가 비어 있어 urllib의 모든 https 호출이
# CERTIFICATE_VERIFY_FAILED로 죽는다(2026-09-06 prod 실측: OpenRouter·Modal 모두).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential sqlite3 openssl curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# .venv/bin을 PATH 앞에 둔다 — compose의 `python3 scripts/scheduler.py`, Next의 child_process
# `python backend/ai/xai_engine.py`(app/api/backtest/explain/route.ts)가 이 인터프리터를 잡는다.
ENV UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# ---------- Python 의존성 (레이어 캐시를 위해 코드보다 먼저) ----------
# torch는 GPU 없는 앱박스용 CPU 휠(GPU는 Modal에만) — pyproject의 [tool.uv.sources]가
# 리눅스에서만 pytorch-cpu 인덱스를 보게 해 2.12.0+cpu를 받는다(PyPI 기본 휠은 CUDA 동봉 ~2.5GB).
# --no-default-groups: dev(pytest·modal CLI)·mac(mlx) 그룹 제외, 런타임 의존성만.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-default-groups && rm -rf /root/.cache/uv

# ---------- Node 의존성 ----------
COPY package*.json ./
COPY prisma ./prisma
RUN npm ci

# ---------- 앱 코드 ----------
COPY . .

# NEXT_PUBLIC_* 는 next build 시점에 클라이언트 번들로 인라인된다(런타임 env로는 주입 불가).
# Supabase 브라우저 클라이언트(구글 로그인)용 공개 키 → 빌드 인자로 받아 build 동안 노출.
ARG NEXT_PUBLIC_SUPABASE_URL
ARG NEXT_PUBLIC_SUPABASE_ANON_KEY
# 토스페이먼츠 결제위젯(빌링 카드등록창)용 공개 클라이언트 키
ARG NEXT_PUBLIC_TOSS_CLIENT_KEY
# Google Analytics 측정 ID — 없으면 GA 스크립트 자체를 렌더하지 않는다(dev 트래픽 차단)
ARG NEXT_PUBLIC_GA_ID
ENV NEXT_PUBLIC_SUPABASE_URL=$NEXT_PUBLIC_SUPABASE_URL \
    NEXT_PUBLIC_SUPABASE_ANON_KEY=$NEXT_PUBLIC_SUPABASE_ANON_KEY \
    NEXT_PUBLIC_TOSS_CLIENT_KEY=$NEXT_PUBLIC_TOSS_CLIENT_KEY \
    NEXT_PUBLIC_GA_ID=$NEXT_PUBLIC_GA_ID

# Prisma 클라이언트 생성 + Next 프로덕션 빌드
RUN npx prisma generate && npm run build

ENV PYTHONPATH=/app:/app/backend \
    PYTHONUNBUFFERED=1 \
    NODE_ENV=production

# 기본은 백엔드. 다른 서비스는 compose에서 command를 덮어쓴다.
WORKDIR /app/backend
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
