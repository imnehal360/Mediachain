# Implementation and acceptance plan

The primary requirements are `../srs.md`. Each phase depends on those above it.

1. **Foundation:** packaging; all domain models; typed async contracts; execution context.
   Accept: timestamp/identity/serialization tests, core import without optional dependencies.
2. **Unified processing:** local loaders, PDF/text chunks, timestamped speech and sampled video;
   shared audio path, configurable scene/interval policies. Accept: deterministic provider tests
   and real synthetic media decode/probe tests, no blocking media I/O on the event loop.
3. **Models/storage:** real provider adapters, SQLite/filesystem, memory vectors, PostgreSQL,
   Qdrant, Redis. Accept: persistence, namespace/dimension rejection, idempotency and deletion.
4. **Temporal/retrieval:** overlaps, nearby/filtering, hybrid fusion, scoped temporal expansion.
   Accept: same-source alignment, prefiltered retrieval, disjoint spaces and dedup tests.
5. **RAG/workflows:** bounded evidence contexts, validated citation IDs; pipes and validated DAGs.
   Accept: unsupported citations rejected; retries/timeouts/cancellation/cycles exercised.
6. **Agents/extensibility:** allowlisted bounded tool runtime, registry, caching, tracing.
   Accept: budget/permission rejection, cache invalidation and compatibility tests.
7. **API/deployment:** authenticated owner-scoped endpoints, local jobs and ARQ, Compose.
   Accept: HTTP integration tests covering ownership, upload limits, processing and deletion.
8. **Validation:** text/audio/video examples, reference app, synthetic fixture generation,
   measured benchmark, packaging and full checks. Accept: deterministic full multimodal test,
   real media decode test and documented live-provider/service verification limits.

## Verification record

Updated after each phase. Live credentials and external services are never assumed available.

## Phase completion reports

Implementation exists across all eight phases. Validation requiring unavailable providers or services
is explicitly pending; this is an initial release, not an assertion of full production qualification.

| Phase | Implemented components and primary files | Executed verification | Limitations and next step |
|---|---|---|---|
| 1 — Foundation | `pyproject.toml`, `uv.lock`, `core/models.py`, `core/interfaces.py`, `core/config.py`, `core/errors.py`; architecture and decision records | Seven model/configuration tests; import guard; full-package mypy and Ruff checks pass | CI for other Python/OS combinations remains to run |
| 2 — Unified processing | `loaders/local.py`, `loaders/http.py`, `processors/{text,audio,video,ocr}.py`, `modalities/audio/ffmpeg.py`, `modalities/video/sampling.py` | Processing unit tests; real FFmpeg/PyAV media tests for offsets, sampling and scenes; deterministic OCR and diarization tests; text/audio/video end-to-end tests | Recognition and OCR quality require configured hosted providers |
| 3 — Models/storage | `models/providers.py`, `embeddings/local.py`, `storage/{local,vector,postgres,qdrant,cache}.py` | Three storage unit tests; embedded Qdrant test; real Redis test; provider modules import and type-check | PostgreSQL service integration and live inference remain unexecuted |
| 4 — Temporal/retrieval | `temporal/alignment.py`, `retrieval/hybrid.py` | Temporal, retrieval filtering/fusion and multimodal end-to-end tests pass | Python-side candidate filtering targets bounded corpora; add backend-native search for scale |
| 5 — RAG/workflows | `rag/engine.py`, `chains/runnable.py`, `workflows/dag.py` | Grounding/context and optional answer-verification tests; workflow tests cover pipes, branching, DAGs, retries, timeout and cancellation | Model verification reduces unsupported answers but is not a formal entailment proof |
| 6 — Agents/extensibility | `agents/{runtime,tools}.py`, `plugins/registry.py`, `observability/tracing.py`, cache integration in `runtime/client.py` | Three agent/plugin/cache tests and six safety/lifecycle tests pass | Usage limits depend on provider-reported tokens; derived tool frame retention belongs to caller |
| 7 — API/deployment | `api/app.py`, `runtime/{jobs,server}.py`, `Dockerfile`, `docker-compose.yml`, `docker-compose.test.yml`, `.env.example` | API tests pass; real-service and full-stack Compose CI jobs cover persistence, restart, recovery and deletion; server adapters import and type-check | Docker and PostgreSQL were unavailable locally; the new jobs require their first remote CI run before qualification |
| 8 — Validation/reference apps | `tests/`, `examples/`, `benchmarks/retrieval.py`, `.github/workflows/ci.yml`, README and operational docs | Current source suite: 50 passed, 3 service tests skipped; frontend: 9 Playwright checks passed, 1 skipped; Redis test separately passed; wheel/sdist built; measured lexical baseline recorded | Run reference video QA with configured real inference providers; run remote CI and infrastructure tests |

The first dependency download was slow, so foundation/unit checks initially used complete downloaded
archives. Full installed-environment checks superseded those preliminary results. Bugs fixed during
verification include type annotations, async filesystem access, delayed audio alignment, oversized
request status handling, and local packaging behavior. See [VALIDATION.md](VALIDATION.md) for exact
results, commands and the remaining verification boundaries.
