# Architecture

`MediaChain` orchestrates Loader → Processor → EmbeddingModel → DocumentStore/VectorStore
→ HybridRetriever → ContextBuilder → ChatModel → grounded ModelResponse.
Text, speech segments, and frame descriptions all become Documents with immutable source identity,
timestamps, processing configuration and model provenance. Binary content stays in ObjectStore.

Core uses only the standard library and Pydantic v2. Protocols define asynchronous boundaries.
Optional adapters import their dependencies only when constructed or called. AudioProcessor is
injected into VideoProcessor; there is only one transcription path. FFmpeg handles probing and audio
extraction; PyAV streams decoded frames in a worker thread. Sampling policy is replaceable.

SQLite and filesystem storage support local development. PostgreSQL persists metadata and documents;
Qdrant indexes one explicit embedding space per collection; Redis caches serialized values; ARQ runs
server jobs. Local jobs are explicitly ephemeral. An index generation is staged before the metadata
commit; retrieval reads only committed document IDs, and old generations are garbage-collected.

Temporal functions operate on validated closed intervals (touching boundaries overlap). Retrieval
filters before ranking, fuses keyword and vector ranks, expands overlapping cross-modal evidence,
and optionally reranks. RAG citations are resolved only from retrieved evidence identifiers.

Workflows are validated DAGs executed with asyncio task groups, bounded policies and trace events.
Agents select allowlisted tools through structured JSON, with step/call/time/token budgets. They
have no implicit shell, filesystem or network authority.

The optional API authenticates bearer keys to owner IDs, authorizes every media/job/query operation,
streams bounded uploads to managed storage, and schedules processing. The Python SDK is trusted
local code; arbitrary remote URLs are disabled by default. Production services use shared storage
and ARQ; a deployment factory constructs dependencies identically for workers and API.
