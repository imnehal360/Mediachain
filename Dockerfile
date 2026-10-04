FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgomp1 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN uv sync --frozen --no-dev --extra api --extra server --extra http --extra media --extra pdf --extra speech --extra embeddings
RUN useradd --create-home --uid 10001 mediachain && mkdir /data && chown mediachain:mediachain /data
USER mediachain
ENV MEDIACHAIN_DATA_DIR=/data
ENV PATH=/app/.venv/bin:$PATH
EXPOSE 8000
CMD ["uvicorn", "mediachain.runtime.server:app", "--host", "0.0.0.0", "--port", "8000"]
