# syntax=docker/dockerfile:1.7

# ---------- Stage 1: frontend build ----------
FROM node:22-alpine AS frontend-build
WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund

COPY frontend/ ./
RUN npm run build


# ---------- Stage 2: backend runtime ----------
FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DFM_ALERT_STATIC_DIR=/app/static

# uv: 빠른 의존성 설치
COPY --from=ghcr.io/astral-sh/uv:0.5.8 /uv /usr/local/bin/uv

WORKDIR /app

# 의존성 먼저 설치 (캐시 효율)
COPY backend/pyproject.toml ./pyproject.toml
RUN uv pip install --system --no-cache .

# 백엔드 소스
COPY backend/src ./src
ENV PYTHONPATH=/app/src

# 프론트엔드 빌드 산출물
COPY --from=frontend-build /frontend/dist /app/static

# 비루트 사용자
RUN useradd --create-home --uid 10001 app && chown -R app:app /app
USER app

EXPOSE 8000

CMD ["uvicorn", "dfm_bq_load_alerter.main:app", "--host", "0.0.0.0", "--port", "8000"]
