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

1. Provision hosted PostgreSQL, Redis, Qdrant, and S3-compatible object storage.
2. Copy `.env.example` to `.env`; add the hosted service URLs/credentials and a JSON mapping of
   strong bearer keys to owner IDs in `MEDIACHAIN_API_KEYS`.
3. Add hosted chat, vision, transcription, and embedding model settings when available. The API
   still supports extractive text answers before model credentials are supplied.
4. `docker compose up --build` starts only the MediaChain API/UI and ARQ worker. It never starts
   local database, queue, vector-database, or object-storage containers.
5. Open the UI, enter a workspace bearer key, and upload media; or use the REST endpoints directly.

API binds localhost. Terminate TLS at a reverse proxy before exposing it externally. Infrastructure
ports are not published. Configure backups, encryption at rest, request-rate limits and operational
monitoring for your deployment. Store secrets outside the image. Pin provider model revisions for
repeatable results; `main` and provider aliases can change without the cache knowing.

`GET /health` reports process liveness without disclosing configuration. `GET /ready` checks the
configured PostgreSQL, Redis, Qdrant, and object-storage clients and returns HTTP 503 when a
dependency is unavailable. Compose enables `MEDIACHAIN_REQUIRE_HOSTED_SERVICES`, causing startup to
fail clearly if any required hosted service setting or workspace-key mapping is missing.

API and workers share the same hosted services and provider configuration. `/data` is an ephemeral
decode/cache area when S3 is configured, not the durable system of record. Worker jobs use ARQ's queue;
processing and API deletion take a renewable Redis lease. Jobs time out after 1800s; the initial
lease lasts 3600s and is refreshed every five minutes while work continues. At API or worker startup,
jobs left running beyond the lease are reconciled to a retryable failed state. Direct SDK writers must use the same lease in
multi-process deployments. API uploads are content-addressed; simultaneous identical uploads write
identical bytes atomically.

Authenticated endpoints are limited per owner through Redis in hosted mode. Responses include a
request ID and defensive browser headers; logs record JSON request metadata without credentials or
request bodies. Set `MEDIACHAIN_ALLOWED_ORIGINS` and `MEDIACHAIN_TRUSTED_HOSTS` for the deployment.
Collection endpoints accept bounded `limit` and `offset` parameters and return `X-Total-Count`.

### Railway deployment from GitHub

No local services are required. Create one Railway project, add PostgreSQL and Redis, then create two
services from the same GitHub repository:

1. For the public service named `api`, set its Railway config-file path to `/railway.api.json` and
   generate a public domain.
2. For the private service named `worker`, set its config-file path to `/railway.worker.json`. Do not
   generate a public domain for the worker.
3. Put the non-secret settings and secret placeholders from `.env.example` into Railway Shared
   Variables, then reference them from both services. Use Railway reference variables for the hosted
   PostgreSQL and Redis connection URLs.
4. Add the Qdrant Cloud URL/database key and the S3-compatible bucket credentials. Add the Hugging
   Face token once and use it for the model, OCR, speech, and embedding key variables.
5. Set `MEDIACHAIN_TRUSTED_HOSTS` to the generated API hostname. Keep allowed origins blank when the
   React workspace is served from the same API domain.
6. Enable GitHub autodeploy only after CI passes. The API `/ready` health check blocks a rollout when
   PostgreSQL, Redis, Qdrant, or object storage is unavailable.

The tracked `.env.example` contains names only. The local `.env` is ignored by Git and must never be
used to transfer secrets through the repository; Railway's Variables raw editor accepts the same
format. Railway configuration is split because the API has an HTTP health check while the ARQ worker
does not expose a port.

Processing failure preserves previous committed documents. Vector staging can leave unreachable
rows after failure; queries only search committed document IDs. Retrying the same asset or deleting
it cleans stale vectors. Cross-service writes are not a distributed transaction.

PostgreSQL applies media, modality, source, timestamp, and JSON metadata predicates before eligible
document IDs are sent to Qdrant. Hybrid lexical ranking still operates over that scoped candidate
set; very large corpora will additionally need backend-native full-text indexing.

## Validation commands

```
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src/mediachain
uv build
```

PostgreSQL, Redis/ARQ, and remote Qdrant integration tests require disposable services explicitly
selected with `MEDIACHAIN_TEST_POSTGRES`, `MEDIACHAIN_TEST_REDIS`, and
`MEDIACHAIN_TEST_QDRANT`. Tests create/delete only unique test IDs. The PostgreSQL and Qdrant tests
close and recreate their clients to prove restart persistence; PostgreSQL also verifies stale-job
reconciliation and cascading cleanup. The default suite still skips these tests when URLs are absent.

For a disposable full-stack qualification, run:

```bash
docker compose -f docker-compose.test.yml up --build --detach
bash tests/smoke/compose.sh
docker compose -f docker-compose.test.yml down --volumes --remove-orphans
```

This test-only stack starts PostgreSQL, Redis, Qdrant, and SeaweedFS alongside the API and ARQ worker.
The smoke test uploads and processes text through the public API, checks grounded retrieval, restarts
the API and worker, checks persisted retrieval again, and deletes the asset. It binds only the API to
`127.0.0.1:18000`; disposable service ports remain internal. Do not use its fixed test credentials
or unencrypted service network as a production configuration.

CI has a real-service integration job plus this Compose smoke job. Live model-provider quality must
still be validated with deployment-specific credentials; see VALIDATION.md for actual local results.

Provider documentation consulted during implementation:
[Qdrant async API](https://qdrant.tech/documentation/tutorials-develop/async-api/),
[PyAV documentation](https://pyav.org/docs/stable/),
[ARQ documentation](https://arq-docs.helpmanual.io/).

### macOS editable-install troubleshooting

If Python cannot import `mediachain` after sync and the generated editable `.pth` file has a hidden
filesystem flag, use `uv sync --no-editable` and `uv run --no-editable ...`. Python can ignore hidden
`.pth` files. The final local validation used this regular installation; rerun sync after source edits.
