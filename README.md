# MediaChain

MediaChain is a Python 3.11+ framework for turning text, audio, and video into searchable,
timestamped evidence. It provides a shared data model, replaceable model/storage adapters,
hybrid retrieval, grounded RAG, workflows, bounded tool agents, and an optional authenticated API.

Version 0.1.0 is an alpha developer preview. Public APIs may change before 1.0. See
[validation](docs/VALIDATION.md) for what has actually been tested and
[deployment limitations](docs/DEPLOYMENT.md) before operating a multi-user service.

The authenticated API includes a responsive black-and-red web workspace for uploads, processing,
grounded Q&A, summaries, citations, and timestamped audio/video evidence. Production Compose runs
only the application and worker; PostgreSQL, Redis, Qdrant, object storage, and model endpoints are
configured as hosted services through environment variables.

## Install

Once the first public release is available on PyPI:

```bash
pip install mediachain
```

Until then, install from a local checkout:

```bash
uv sync --dev
uv run python examples/text_qa.py notes.txt "What does this say about artificial intelligence?"
```

If macOS ignores uv's generated editable `.pth` file because it has a hidden filesystem flag, use
`uv sync --no-editable --dev`. The test suite also adds `src` to its import path explicitly.

The base package requires only Pydantic. Local text processing uses SQLite, filesystem storage,
deterministic lexical embeddings, and an extractive evidence response. Models, services, cloud
credentials, FFmpeg and FastAPI are not needed to import or use this path.

```python
import asyncio
from mediachain import MediaChain


async def main():
    mc = MediaChain(data_dir=".mediachain")
    asset = await mc.add("notes.txt")
    response = await mc.ask(
        "What does this say about artificial intelligence?", media_ids=[asset.id]
    )
    summary = await mc.summarize(media_ids=[asset.id])
    print(response.answer)
    print(response.sources)
    print(summary.answer)


asyncio.run(main())
```

`add_sync`, `ask_sync`, and `summarize_sync` are available outside an active event loop. `load`
stores an asset without processing it; `process(asset_id)` processes/indexes it; `summarize`
produces a grounded summary from retrieved evidence; `delete(asset_id)` removes managed data.
Repeated ingestion and processing are idempotent. Cache keys include content, configuration and model
identity/version; changing processing configuration produces a new committed document generation.

## Use real speech, vision and language models

Install FFmpeg, then the extras you need:

```bash
uv sync --dev --extra speech --extra media --extra embeddings --extra http --extra pdf
```

```python
from mediachain import MediaChain
from mediachain.embeddings.local import SentenceTransformerEmbeddings
from mediachain.models.providers import FasterWhisperSpeech, HTTPChatModel, HTTPVisionModel
from mediachain.storage.vector import MemoryVectorStore

mc = MediaChain(
    llm=HTTPChatModel("your-chat-model", "http://localhost:8001/v1"),
    speech=FasterWhisperSpeech("base"),
    vision=HTTPVisionModel("your-vision-model", "http://localhost:8001/v1"),
    embeddings=SentenceTransformerEmbeddings(),
    vector_store=MemoryVectorStore(),
)
asset = await mc.add("lecture.mp4")
response = await mc.ask(
    "What did the professor explain about transformers, and what diagram appeared on screen?",
    media_ids=[asset.id],
)
print(response.answer)
print(response.sources)
```

HTTP adapters use the chat-completions protocol, including image data URLs for vision. Supply
`api_key` when required. The chat provider must follow the documented JSON answer instruction.
Speech/embedding weights download lazily on first use. Pin actual model revisions or immutable local
model artifacts in deployments: mutable aliases cannot automatically invalidate caches.

Video processing reuses AudioProcessor, decodes frames with PyAV, and processes the two streams
concurrently. Interval and scene sampling are replaceable. Transcript and visual evidence retain
original-media timestamps, including audio stream offsets. Visual observation windows describe
sampled frames; they do not assert that a screen remained unchanged between frames.

Hosted OpenAI-compatible adapters are available for transcription, diarization, embeddings, chat,
and vision. Scanned PDFs can render bounded pages for OCR through a configured vision endpoint.
Generated answers can optionally receive a second evidence-verification pass before being returned.

Hugging Face Inference Providers are supported natively for timestamped speech recognition and
feature-extraction embeddings, and through Hugging Face's chat-completions router for chat, vision,
and OCR. Set `SPEECH_PROVIDER=huggingface` and `EMBEDDING_PROVIDER=huggingface`; see `.env.example`
for the complete hosted configuration. Provider availability and free inference credits are limited,
so deployments should surface failed jobs and monitor usage rather than assuming unlimited inference.

## Load remote media deliberately

The default SDK loader accepts trusted local paths only. To load HTTPS media, inject `HTTPSLoader`
with an explicit host allowlist and a staging directory. Redirects, credentials, non-HTTPS URLs and
private-address DNS results are rejected.

```python
from pathlib import Path

from mediachain import MediaChain
from mediachain.loaders.http import HTTPSLoader

mc = MediaChain(
    loader=HTTPSLoader({"media.example.com"}, Path(".mediachain/downloads")),
)
asset = await mc.add("https://media.example.com/interview.mp4")
```

## Reference applications

- [Text QA](examples/text_qa.py): no external models required.
- [Audio QA](examples/audio_qa.py): local Faster-Whisper transcription and timestamped retrieval.
- [Interactive video QA](examples/video_qa.py): real speech, vision, embeddings and grounded generation.
- [Synthetic fixture generator](examples/generate_fixture.py): original speech and a simple diagram,
  using espeak or macOS `say`, Pillow and FFmpeg. No copyrighted third-party media is needed.

```bash
uv run python examples/generate_fixture.py
# Set MODEL_BASE_URL, CHAT_MODEL, VISION_MODEL, and MODEL_API_KEY if needed.
uv run python examples/video_qa.py .mediachain/fixture/lecture.mp4
```

Deterministic end-to-end tests use generated video and explicitly mocked model outputs. They test
media handling and orchestration, not recognition quality. The reference application uses real
configured adapters and does not substitute mock answers.

## Retrieval and grounding

Use `RetrievalFilter(media_ids=..., modalities=..., sources=..., start_time=..., end_time=...,
metadata=...)` with `ask(..., filters=...)`. Times are finite nonnegative seconds; both boundaries
must be supplied. Filters apply before ranking and temporal expansion. Audio/visual overlaps are
associated only within the same original media asset. Result fusion deduplicates document IDs.
Embedding spaces include model, version and dimensions; incompatible spaces are never compared.

RAG builds a bounded evidence context and resolves only citation IDs present in that context.
Unknown citations and malformed model responses raise `GroundingError`. No evidence yields an
explicit insufficient-evidence response. Citation validation cannot prove every generated sentence
is entailed; applications needing stronger guarantees require an additional verification stage.

## Extend and deploy

- [Documentation home](docs/index.md) and [five-minute quickstart](docs/getting-started.md).
- [Architecture](docs/ARCHITECTURE.md) and [engineering decisions](docs/DECISIONS.md).
- [Interfaces, plugins, workflows and agents](docs/EXTENDING.md).
- [Public API reference](docs/api-reference.md).
- [API, Docker Compose and operations](docs/DEPLOYMENT.md).
- [Implementation phases and acceptance record](docs/IMPLEMENTATION_PLAN.md).
- [Executed checks and remaining validation](docs/VALIDATION.md).
- [Contributing](CONTRIBUTING.md), [security policy](SECURITY.md), and
  [changelog](CHANGELOG.md).

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src/mediachain
uv build
uv run python benchmarks/retrieval.py --documents 100
```

Licensed under MIT. The supplied requirements remain in [srs.md](srs.md).
