# Validation record

## Current status ? 29 October 2026

MediaChain 0.1.0 is an alpha release published to PyPI. This page distinguishes automated checks,
manual observations, and unqualified behavior. Results describe the checked source and stated
environment, not every supported provider, operating system, or deployment.

### Automated checks

| Check | Result and scope |
| --- | --- |
| Backend tests, Windows / Python 3.13.17 | **74 passed, 3 skipped**, rerun 29 October 2026 |
| Documentation build | `mkdocs build --strict` passed with Python 3.13; local Markdown targets checked, 29 October 2026 |
| Ruff lint | Passed on `src` and `tests`, rerun 29 October 2026 |
| Mypy | Passed, 56 source files, rerun 29 October 2026 |
| Frontend TypeScript/Vite production build | Passed during the persistent-conversation implementation |
| Playwright desktop/mobile flows | 19 passed, 1 expected skip across the full run and corrected history-test rerun |
| Wheel and source archive metadata | Twine strict check passed before publication |
| Fresh PyPI installation, 29 October 2026 | `mediachain==0.1.0` installed from `https://pypi.org/simple`; the exact documented text quickstart ran outside the repository import path and returned evidence/citations |
| Local model-backed guide example | Syntax and adapter/configuration construction checked; model inference was not rerun during this documentation-only change |
| Clean installation of the locally built wheel | Core import, text ingestion, SQLite documents, retrieval, and citations passed with only base dependencies |
| Distribution inventory | Type marker, license, current modules included; private `.env`, user media, tools, caches, and IDE configuration excluded |
| PyPI upload | GitHub publishing workflow succeeded for tag `v0.1.0`, reported and shown on 29 October 2026 |

Backend tests use real FFmpeg/PyAV decoding where available, with deterministic speech/vision
providers for reproducibility. They cover timestamp alignment and duration bounds, adaptive frame
sampling, document/storage lifecycles, hybrid retrieval, grounding schemas, agent tools and budgets,
API ownership, YouTube URL validation/downloader orchestration, and conversation persistence.
The Windows regression explicitly runs FFprobe under Uvicorn's single-worker event loop.

Conversation tests check source references, bounded follow-up context, persistence across backend
recreation, cross-owner denial, and failed-turn handling. Browser tests check retention of previous
answers and citations, reopening after refresh, new chats, uploads, queries, agents, and mobile use.
Browser API fixtures do not measure real model output quality or processing latency.

The three backend skips require external service configuration. They are not passes. Previous
GitHub CI runs exercised the Python 3.11?3.13 matrix and infrastructure/frontend checks, as observed
in the release session. Consult the [actual workflow runs](https://github.com/imnehal360/Mediachain/actions)
for the exact commit, job outcome, and logs; local skips do not establish hosted-service readiness.

### Manual local observations

During the Windows development session, local Ollama/Qwen, Whisper, and MiniLM were configured,
and model-backed text, audio, PDF/OCR, video, and agent flows were exercised. These are functional
observations, not a labeled accuracy study. The user reported successful processing and question
answering for a **16-minute video**, then reported that persistent chat history worked after its fix.
A real YouTube download was also verified during implementation.

Long-video tests exposed Windows reload/subprocess incompatibility and transcript timestamps
extending beyond media duration. Both received code fixes and automated regression coverage.
Earlier failed long runs are not evidence of successful end-to-end processing for those recordings.

## Reproduce checks from a checkout

```bash
uv sync --dev
uv run pytest -q
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy
```

For actual decoder tests, install the `media` extra and put FFmpeg/FFprobe on PATH. If Windows
pytest cannot access an old temporary directory, use a new temporary path and disable its cache:

```powershell
uv run pytest -q --basetemp="$env:LOCALAPPDATA\Temp\mediachain-validation-new" -p no:cacheprovider
```

Use a fresh, dedicated path: pytest may replace its own base temporary directory. For frontend
checks from the repository root:

```powershell
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run build
npm.cmd --prefix frontend test
```

Documentation dependencies are in `requirements-docs.txt`; run `mkdocs build --strict` after
installing them. For release archive checks, follow [Publishing](PUBLISHING.md).

## Limits and interpretation

- No reliable processing-time SLA, retrieval-accuracy score, or broad transcription/vision quality
  benchmark has been established. Do not treat illustrative timings as measured results.
- Vector search and processing caches are in memory by default. SQLite persists documents,
  metadata, and API conversation history; searchable vectors are restored on demand.
- Text chunking is character-based. MiniLM may truncate long token sequences; semantic chunking
  and alternative embedding models have not been introduced in this release.
- Visual evidence describes sampled frames, not continuous understanding of every video moment.
- Citation membership is checked, but this does not prove every answer claim is correct. Summaries
  use bounded retrieved evidence rather than an exhaustive long-document synthesis.
- Caption-first ingestion, progressive partial questions, resumable stage checkpoints, and
  timestamp-priority processing were discussed but are not implemented.
- Full recognition/generation runs are not repeated by unit tests. Model download availability,
  GPU compatibility, private/region-restricted YouTube access, and every hosted provider remain
  environment-dependent. Independent developer onboarding across all platforms is not qualified.
- The local job queue loses active work on termination; SQLite chat storage is intended for the
  single-instance reference app. See [deployment boundaries](DEPLOYMENT.md).

Older development notes described different test counts and macOS-specific experiments. They
are not the current Windows validation record and their tiny lexical-retrieval timings should
not be used as performance claims for the neural multimodal pipeline.
