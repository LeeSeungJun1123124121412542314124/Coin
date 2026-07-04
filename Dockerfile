# syntax=docker/dockerfile:1
# ─── Stage 1: 프론트엔드 빌드 ──────────────────────────────────
FROM node:22-slim AS frontend-build

WORKDIR /build/frontend
COPY dashboard/frontend/package*.json ./
RUN npm ci --prefer-offline

COPY dashboard/frontend/ .
RUN npm run build
# 결과물: /build/frontend/dist/


# ─── Stage 2: Python 앱 ────────────────────────────────────────
FROM python:3.12-slim AS app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/crypto-volatility-bot \
    PORT=8080

WORKDIR /app

# Python 의존성 설치 (lock constraints 사용)
COPY requirements-lock.txt /tmp/requirements-lock.txt
COPY crypto-volatility-bot/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -c /tmp/requirements-lock.txt -r /tmp/requirements.txt

# 소스 복사
COPY crypto-volatility-bot/ ./crypto-volatility-bot/
COPY dashboard/backend/ ./dashboard/backend/

# 프론트엔드 빌드 결과물 복사
COPY --from=frontend-build /build/frontend/dist/ ./dashboard/frontend/dist/

EXPOSE 8080

CMD exec python -m uvicorn dashboard.backend.main:create_application --factory --host 0.0.0.0 --port "${PORT:-8080}"
