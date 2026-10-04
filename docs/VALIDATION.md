# Validation record

## Executed checks

Verified on macOS 26.6.2 (arm64), Python 3.11.15. FFmpeg/ffprobe and PyAV were available.
These are actual local results, not claims about other operating systems or live model quality.

| Check | Result |
|---|---|
| `.venv/bin/pytest -q` against the installed package | 39 passed, 2 service tests skipped |
| Redis cache + ARQ worker integration, explicitly configured disposable Unix socket | 1 passed |
| `.venv/bin/mypy src/mediachain` | No issues in 52 source files |
| `.venv/bin/ruff check .` | Passed |
| `.venv/bin/ruff format --check .` | Passed |
| `uv lock --check --offline` | Lockfile consistent; 104 packages resolved |
| `uv build --offline` | Wheel and source distribution built |
| Regular package installation and import | Passed; imports from site-packages |
| Text QA example against installed package | Passed in a temporary working directory |
| SDK grounded summarization and public exports | Covered by end-to-end tests |
| Distribution inventory | Package modules present; no environment, tools or dependency cache bundled |
| Optional-dependency import guard | Core import does not load FastAPI, PyAV, Redis, Qdrant, asyncpg or ML libraries |

The full default suite skips PostgreSQL and Redis unless disposable service URLs are supplied.
Redis was tested separately with Redis 8.8.0 and ARQ 0.28.0, exercising a real queued processing job,
cache namespace deletion and persisted job completion. The isolated socket was absent after the
interrupted session ended; no Redis configuration or persistent service was installed.

A fresh final run used a regular installation (`uv sync --no-editable --dev --extra api --extra media
--extra pdf --extra server --extra http`). On this machine, macOS hidden-file flags on uv's generated
editable `.pth` file caused Python 3.11 to ignore it. A regular install avoids that environment issue.
If it occurs locally, use `uv sync --no-editable`; repeat sync after changing source code.

## Coverage exercised

- Domain serialization, finite/nonnegative/paired timestamp validation, stable IDs and configuration.
- Text chunks, HTML cleaning, empty PDF extraction, bounded input and per-owner content identities.
- Real FFmpeg audio extraction/probing and PyAV decoding with explicitly mocked speech/vision/LLM
  providers. Audio-only and combined audio/video paths preserve original source references.
- Scene/interval sampling, frame limits, delayed audio stream offsets and temporal overlaps.
- SQLite persistence, atomic replacement, deletion and memory vector-space/dimension validation.
- Qdrant's real embedded client: namespaces, filtering and deletion.
- Retrieval modality/time/owner scoping, hybrid fusion, temporal expansion and deduplication.
- Evidence context limits, missing evidence, unknown citation rejection and token accounting.
- Sequential/parallel/conditional execution, DAG dependency validation, cycles, retries, timeouts,
  cancellation and sibling cleanup.
- Tool allowlists and call/token budgets, registry compatibility and content-cache invalidation.
- API authentication, cross-owner denial, file limits, structured errors, processing jobs and deletion.
- Concurrent ingestion, failed-index staging, prior-generation preservation and all-generation cache deletion.

## Measured local baseline

Command: `.venv/bin/python benchmarks/retrieval.py --documents 100`.
Input: 100 generated text blocks; lexical-hash embedding model version 1, 256 dimensions;
SQLite metadata/documents and memory vectors; no neural model inference.

Latest measured run: ingestion **0.010733 s**, query **0.001571 s**, 8 source references.
The script reports the runtime/platform and its exact configuration. This is a tiny functional
baseline, not a production throughput claim or a neural-retrieval quality benchmark. Whitespace
normalization means input blocks do not correspond one-to-one with indexed chunks.

## Not executed / remaining limits

- PostgreSQL integration: no disposable PostgreSQL service was available. An opt-in transaction and
  cascade test is included. The asyncpg adapter imports and type-checks.
- Docker Compose deployment: Docker was not available. Build/deployment files are provided but the
  containers and Linux dependency installation have not been exercised here.
- Real Faster-Whisper/Sentence Transformers downloads, hosted/local VLM inference and real chat
  generation: no model artifacts or configured inference endpoint/credentials were supplied. The
  reference video application uses real adapters; deterministic test outputs are never represented
  as actual recognition or generated answers from a live provider.
- CI matrix for Python 3.11–3.13 on Linux is defined, but remote CI has not run.
- TTS, diarization and native media embeddings are extension contracts; diarization is integrated
  when supplied, but no built-in diarization model is bundled. Scanned-PDF OCR is not implemented.
- Large-corpus backend-native metadata/keyword indexing, stronger entailment verification, renewable
  distributed leases and complete crash-status reconciliation are follow-up production work.

See DEPLOYMENT.md for retention, concurrency and operational boundaries. This validation supports an
initial reusable release, not a claim that every production deployment or foundation model has been
qualified.
