# Retrieval and grounding

MediaChain converts text chunks, transcript segments, and sampled frame descriptions into a shared
document model. Each document retains its original asset identity, modality, timestamps, processing
configuration, and model provenance.

## Scope a query

Pass media IDs directly or use `RetrievalFilter` for modality, source, timestamp, and metadata
constraints:

```python
from mediachain import RetrievalFilter

filters = RetrievalFilter(
    media_ids=[asset.id],
    start_time=30.0,
    end_time=90.0,
)
response = await mc.ask("What changed during this interval?", filters=filters)
```

Both time boundaries must be supplied and must be finite, nonnegative seconds. Filters are applied
before ranking and temporal expansion.

## Understand grounded responses

The RAG layer builds a bounded context from retrieved documents. A configured chat provider must
return citations that refer to identifiers in that context. Unknown citations and malformed model
responses fail instead of being silently accepted.

Citation validation proves that a cited source was retrieved; it does not prove that every generated
claim is semantically entailed. High-stakes applications should add a verification stage or human
review.

When no chat model is configured, MediaChain returns an extractive evidence response. When no
evidence matches, it returns an explicit insufficient-evidence result.

## Local semantic embeddings versus the default baseline

The base SDK uses 256-dimensional `HashEmbeddings`: deterministic lexical feature hashing,
not a trained semantic model. Inject `SentenceTransformerEmbeddings` for MiniLM's native
384-dimensional semantic vectors. The local application example does this explicitly.
Changing only the dimensions setting does not change a model's output size; an incompatible
size is rejected. Switching models requires compatible vectors to be regenerated.

Text, transcript segments, and frame descriptions are all embedded as **text**. This release
does not directly embed raw audio or video. Current text chunks use character boundaries;
MiniLM's input length is bounded and long token sequences can be truncated. See the
[model documentation](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2).

## Conversation context

The SDK does not retain previous `ask` calls. The application conversation API stores successful
turns and supplies bounded recent context to interpret follow-ups. It still performs retrieval;
previous model answers are not authoritative source evidence. See
[conversations](web-application.md#persistent-conversations).
