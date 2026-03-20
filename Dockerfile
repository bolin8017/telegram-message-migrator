# Stage 1: Build the React SPA
FROM node:22-slim AS frontend-builder

WORKDIR /build/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm install --no-audit --no-fund

COPY frontend/ ./
RUN npm run build
# Vite outputs to ../app/static/dist → /build/app/static/dist

# Stage 2: Install Python dependencies
FROM python:3.12-slim AS python-builder

WORKDIR /build

COPY pyproject.toml README.md ./
COPY app/ app/
RUN pip install --no-cache-dir --prefix=/install .

# Stage 3: Production runtime
FROM python:3.12-slim

RUN groupadd --system app && useradd --system --gid app --create-home app

WORKDIR /app

# Copy installed Python packages
COPY --from=python-builder /install /usr/local

# Copy application code
COPY app/ app/

# Copy frontend build output
COPY --from=frontend-builder /build/app/static/dist/ app/static/dist/

# Create data directories and set ownership
RUN mkdir -p /data/sessions /data/logs && chown -R app:app /data

ENV PYTHONUNBUFFERED=1
ENV SESSION_DIR=/data/sessions
ENV DB_PATH=/data/data.db

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
