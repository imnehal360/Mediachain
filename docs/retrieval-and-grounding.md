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
