# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# --- test stage ---
FROM base AS test
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY . .
CMD ["pytest", "tests/unit", "tests/e2e", "-v", "--tb=short", \
     "--cov=app", "--cov-report=term-missing", "--cov-fail-under=80"]

# --- production stage ---
FROM base AS production
RUN useradd -m -u 1000 appuser
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=appuser:appuser app/ app/
COPY --chown=appuser:appuser config/ config/
USER appuser
ENV PORT=8080
EXPOSE 8080
CMD ["python", "-m", "uvicorn", "app.main:create_application", "--factory", "--host", "0.0.0.0", "--port", "8080"]
