FROM node:22-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgomp1 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
COPY --from=frontend /app/frontend/dist ./frontend/dist
RUN uv sync --frozen --no-dev --extra api --extra server --extra cloud --extra http --extra huggingface --extra media --extra pdf --extra ocr
RUN useradd --create-home --uid 10001 mediachain && mkdir /data && chown mediachain:mediachain /data
USER mediachain
ENV MEDIACHAIN_DATA_DIR=/data
ENV PATH=/app/.venv/bin:$PATH
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn mediachain.runtime.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
