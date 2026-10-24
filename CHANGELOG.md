# Changelog

Notable changes to MediaChain are recorded here. The project follows Semantic Versioning after the
public API stabilizes; during the 0.x alpha series, minor versions may contain breaking changes.

## Unreleased

### Added

- Public documentation site configuration and API reference.
- GitHub workflows for documentation and trusted PyPI publishing.
- Contributor and security guidance.
- Responsive authenticated web workspace for media ingestion and grounded Q&A.
- Hosted S3-compatible storage, Qdrant API-key authentication, and hosted speech/embedding adapters.
- Grounded summarization and liveness API endpoints.
- Dependency readiness checks, strict hosted configuration validation, renewable worker leases,
  richer job lifecycle timestamps, and desktop/mobile browser tests.
- Database-level retrieval predicates and collection pagination.
- Redis-backed owner rate limits, security headers, request IDs, structured request logs, and stale
  job reconciliation.
- Hosted diarization, vision-backed scanned-PDF OCR, and optional second-pass evidence verification.

### Changed

- Docker Compose now runs only the API/UI and worker; data infrastructure is externally hosted.

## 0.1.0

### Added

- Local text, audio, and video ingestion pipelines.
- Timestamped hybrid retrieval and grounded responses.
- Replaceable provider, storage, workflow, agent, and plugin interfaces.
- Optional authenticated API, worker, PostgreSQL, Redis, and Qdrant deployment.
- Unit, integration, end-to-end, safety, and retrieval baseline tests.
