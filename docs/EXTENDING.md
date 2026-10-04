# Interfaces and extensions

The exact contracts live in `src/mediachain/core/interfaces.py`; all I/O methods are async.
Core serializable types live in `core/models.py`. Models reject extra fields and invalid times.
`ProcessingConfig` validates chunk sizes, sampling intervals and resource limits.

| Contract | Input → output | Initial implementation |
|---|---|---|
| Loader | path/URL, owner → MediaAsset | LocalLoader, opt-in HTTPSLoader |
| Processor | asset, context → ProcessingResult; fingerprint() | TextProcessor, AudioProcessor, VideoProcessor |
| ChatModel | ChatMessage[] → ChatOutput | HTTPChatModel |
| VisionModel | image path, prompt → description | HTTPVisionModel |
| SpeechToTextModel | audio path → SpeechSegment[] | FasterWhisperSpeech |
| DiarizationModel | audio path → speaker-labeled SpeechSegment[] | User-provided optional adapter |
| TextToSpeechModel | text, destination → path | Extension contract |
| EmbeddingModel | text[] → vector[]; space | HashEmbeddings, SentenceTransformerEmbeddings |
| NativeMediaEmbeddingModel | paths → vector[]; space | Extension contract |
| Reranker | query, results → ordered results | SentenceTransformerReranker |
| VectorStore | upsert/search/delete with explicit space | MemoryVectorStore, QdrantVectorStore |
| DocumentStore | atomic asset replacement, filtered read, delete | SQLiteStore, PostgresStore |
| MetadataStore | asset/job CRUD | SQLiteStore, PostgresStore |
| ObjectStore | source file/key → stored file reference | FileObjectStore |
| Cache | serialized get/set/delete/delete_prefix | MemoryCache, RedisCache |
| Retriever | query, filters, limit → RetrievalResult[] | HybridRetriever |
| Runnable | value, context → value | Function, Sequence, Parallel, Branch, Retry, Workflow |
| Tool | validated JSON arguments, context → JSON-compatible result | MediaTool |
| FrameSampler | media path, destination → async (path, seconds) iterator | IntervalSampler, SceneSampler |

## Register a plugin

```python
from mediachain.plugins.registry import PluginRegistry
from mediachain.embeddings.local import HashEmbeddings
from mediachain import MediaChain

registry = PluginRegistry()
registry.register("embeddings", "my-local", HashEmbeddings(512), api_version="1")
mc = MediaChain(embeddings=registry.get("embeddings", "my-local"))
```

Implement the selected Protocol (including its async methods), then register the instance. Registration
checks required members and the declared API version; Python runtime protocol checks do not prove full
signature or return-type correctness. Use mypy and adapter contract tests as well. Duplicate names fail.

The top-level package exports the main SDK types: `MediaChain`, `ProcessingConfig`, `Document`,
`MediaAsset`, `ModelResponse`, `RetrievalFilter`, `SourceReference`, `ExecutionContext` and
`Modality`. Subpackages export their primary adapters so common extension imports work from
`mediachain.loaders`, `mediachain.processors`, `mediachain.embeddings`, `mediachain.models`,
`mediachain.storage`, `mediachain.retrieval`, `mediachain.rag`, `mediachain.chains`,
`mediachain.workflows`, `mediachain.agents` and `mediachain.plugins`.

SDK `register_processor(modality, processor)` and `register_loader(loader)` replace processing behavior.
Providers must include a stable, truthful model identifier/version in their fingerprints.

## Compose trusted operations

```python
from mediachain.chains.runnable import Function, Parallel, Branch, Retry
from mediachain.workflows.dag import Workflow, Node

pipeline = Function(str.strip) | Function(str.upper)
result = await pipeline.ainvoke(" hello ")
workflow = Workflow(
    [
        Node("length", Function(len)),
        Node("uppercase", Function(str.upper)),
        Node("join", Function(lambda outputs: outputs), ("length", "uppercase")),
    ]
)
result = await workflow.ainvoke("hello")
```

Sync functions run in threads. Cancellation propagates through task groups; native thread work may
finish after cancellation. Retry only selected transient exceptions (default timeout/connection errors)
and only use it around idempotent operations. Context trace events contain operation names/durations,
not prompts or media. `Function` is trusted application code, never a tool for model-generated code.

## Tools and agents

`Agent(model, media_tools(mc, owner_id), AgentLimits(...))` selects tools using JSON. Pass an
`ExecutionContext(owner_id=...)` matching the tool owner. Tool permissions are fixed at construction.
Frame extraction is available only when an output directory is explicitly supplied. Returned frame
files are caller-owned derived artifacts and their retention/deletion must be managed by the caller.
Token limits are checked after each response when reported by the provider; set the provider's
`max_tokens` as well to bound a single request. Missing usage cannot be measured. Agent final text is
not a structured grounded RAG response; use `MediaChain.ask` when source validation is required.
