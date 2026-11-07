FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
ENV VITE_API_BASE_URL=/api/v1
RUN npm run build

FROM python:3.11-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/ ./backend/
RUN pip install --no-cache-dir -r backend/requirements.lock.txt && pip install --no-cache-dir --no-deps -e ./backend
COPY docs/contract_snapshot.json ./docs/contract_snapshot.json
COPY scripts/container_runtime.py ./scripts/container_runtime.py
COPY --from=frontend /build/dist ./frontend/dist
RUN useradd --create-home --uid 10001 app && mkdir /data && chown app:app /data
USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=5 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3)"
CMD ["python", "scripts/container_runtime.py"]
