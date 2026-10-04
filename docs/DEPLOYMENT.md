# Deployment

## Local SDK

Install Python 3.11+ and uv, then run `uv sync --dev`. Only Pydantic is required for the base package.
Optional extras: `api`, `media`, `pdf`, `speech`, `embeddings`, `http`, `server`.
FFmpeg/ffprobe must be on PATH for audio/video processing; PyAV is in `media`.

SQLite persists assets/documents; filesystem storage copies original media. The memory vector index
is rebuilt from committed documents on first SDK query after restart. This local configuration is for
small corpora, not multi-process writes. Hash embeddings and extractive responses work offline; they
are a lexical baseline and evidence view, not neural inference.

## Authenticated API + worker

1. Copy `.env.example` to `.env`; set a PostgreSQL password and a JSON mapping of strong bearer keys
   to owner IDs in `MEDIACHAIN_API_KEYS`. Set models/provider URL/credentials as needed.
2. `docker compose up --build` starts API, ARQ worker, PostgreSQL, Redis and Qdrant.
3. Upload multipart `file` to `POST /api/v1/media` with `Authorization: Bearer <key>`.
4. POST `/api/v1/media/{id}/process`; poll `/api/v1/jobs/{id}` until completed or failed.
5. POST `/api/v1/query` with `{"question":"...","media_ids":["..."]}`.
6. DELETE `/api/v1/media/{id}` removes committed documents, vectors, managed original and cache.

API binds localhost. Terminate TLS at a reverse proxy before exposing it externally. Infrastructure
ports are not published. Configure backups, encryption at rest, request-rate limits and operational
monitoring for your deployment. Store secrets outside the image. Pin provider model revisions for
repeatable results; `main` and provider aliases can change without the cache knowing.

API and workers share `/data` and the same models/configuration. Worker jobs use ARQ's queue;
processing and API deletion take a Redis lease. Jobs time out after 1800s, before the 3600s lease expiry.
The lease is deliberately bounded; do not increase job timeout beyond the lease without adding
renewal. A worker crash can leave a job marked running until operational reconciliation; job status
is not a complete crash-recovery state machine. Direct SDK writers must use the same lease in
multi-process deployments. API uploads are content-addressed; simultaneous identical uploads write
identical bytes atomically.

Processing failure preserves previous committed documents. Vector staging can leave unreachable
rows after failure; queries only search committed document IDs. Retrying the same asset or deleting
it cleans stale vectors. Cross-service writes are not a distributed transaction.

The first implementation prefilters documents in Python and sends eligible IDs to Qdrant. It is
correct for scoped retrieval but requires bounded corpora; large-scale retrieval needs backend-native
metadata predicates, pagination and keyword indexing. It does not claim unlimited scale.

## Validation commands

```
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src/mediachain
uv build
```

PostgreSQL/Redis/ARQ integration tests require disposable services explicitly selected via
`MEDIACHAIN_TEST_POSTGRES` and `MEDIACHAIN_TEST_REDIS`. Tests create/delete only unique test IDs.
Qdrant contract tests use the real client's embedded implementation. Container deployment and live
provider quality must be validated in the target environment; see VALIDATION.md for actual results.

Provider documentation consulted during implementation:
[Qdrant async API](https://qdrant.tech/documentation/tutorials-develop/async-api/),
[PyAV documentation](https://pyav.org/docs/stable/),
[ARQ documentation](https://arq-docs.helpmanual.io/).

### macOS editable-install troubleshooting

If Python cannot import `mediachain` after sync and the generated editable `.pth` file has a hidden
filesystem flag, use `uv sync --no-editable` and `uv run --no-editable ...`. Python can ignore hidden
`.pth` files. The final local validation used this regular installation; rerun sync after source edits.
