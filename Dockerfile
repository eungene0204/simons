# Simons 합본 앱 이미지 (node + python)
# ─────────────────────────────────────────────────────────────────────────────
# 이 앱은 모놀리스다: Next.js(app/api)가 child_process로 python(backend/ai/xai_engine.py)을
# 직접 실행하고, fs로 data/ 파일을 읽는다. 따라서 웹·백엔드·스케줄러·뉴스워커가 모두
# "node + python + 전체 코드"를 필요로 한다 → 이미지 하나로 굽고 서비스별 command만 다르게.
#
# ⚠️ 초안: requirements에 OS 라이브러리가 더 필요한 패키지가 있으면 빌드가 실패할 수 있다.
#    그럴 땐 아래 apt-get 줄에 필요한 -dev 패키지를 추가하며 반복한다.
# ⚠️ mlx-lm은 macOS 전용이므로 backend/requirements.txt에 들어있으면 안 된다(리눅스 빌드 실패).
#    코드에서 조건부 import되므로 리눅스에선 Ollama 경로만 쓰면 된다.
# ─────────────────────────────────────────────────────────────────────────────
FROM node:24-slim

# Python 3.11 + 빌드도구 + sqlite(11GB DB 조회) + openssl(prisma) + curl
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-dev build-essential \
        sqlite3 openssl curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---------- Python 의존성 (레이어 캐시를 위해 코드보다 먼저) ----------
COPY backend/requirements.txt backend/requirements-news-v2.txt ./backend/
# torch는 GPU 없는 앱박스용 CPU 휠로 설치(GPU는 Modal에만).
# amd64(배포 타깃): PyPI 기본 torch는 ~2.5GB CUDA 빌드라 낭비 → +cpu 휠 선설치.
#   이후 requirements의 torch==2.12.0이 2.12.0+cpu로 충족되어 재설치 안 됨.
# arm64 linux: PyPI torch가 이미 CPU-only(+cpu 휠 없음) → 건너뛰고 requirements가 설치.
ARG TARGETARCH
RUN if [ "$TARGETARCH" = "amd64" ]; then \
        pip3 install --no-cache-dir --break-system-packages \
            torch==2.12.0+cpu --extra-index-url https://download.pytorch.org/whl/cpu ; \
    fi
RUN pip3 install --no-cache-dir --break-system-packages \
        -r backend/requirements.txt -r backend/requirements-news-v2.txt

# ---------- Node 의존성 ----------
COPY package*.json ./
COPY prisma ./prisma
RUN npm ci

# ---------- 앱 코드 ----------
COPY . .

# Prisma 클라이언트 생성 + Next 프로덕션 빌드
RUN npx prisma generate && npm run build

ENV PYTHONPATH=/app:/app/backend \
    PYTHONUNBUFFERED=1 \
    NODE_ENV=production

# 기본은 백엔드. 다른 서비스는 compose에서 command를 덮어쓴다.
WORKDIR /app/backend
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
