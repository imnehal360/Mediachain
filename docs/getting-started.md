# Getting started

## Requirements

- Python 3.11 or newer
- FFmpeg only when processing audio or video
- Optional provider credentials only when using a hosted chat or vision model

## Install

After the first public release:

```bash
python -m pip install mediachain
```

For development from a checkout:

```bash
uv sync --dev
uv run pytest -q
```

If macOS ignores the editable installation, run `uv sync --no-editable --dev`.

## Ingest and query text

Create `notes.txt`, then run:

```python
from mediachain import MediaChain

mc = MediaChain(data_dir=".mediachain")
asset = mc.add_sync("notes.txt")

answer = mc.ask_sync(
    "What are the main ideas?",
    media_ids=[asset.id],
)

print(answer.answer)
print(answer.sources)
```

The default configuration stores metadata and documents in SQLite, copies source files into
managed filesystem storage, and rebuilds the in-memory vector index after a restart.

## Use async APIs

Applications already running an event loop should use the async methods:

```python
asset = await mc.add("notes.txt")
answer = await mc.ask("What are the main ideas?", media_ids=[asset.id])
```

Do not call the synchronous wrappers from an active event loop.

## Add optional capabilities

```bash
python -m pip install "mediachain[http,media,pdf,speech,embeddings]"
```

Audio and video require configured speech and/or vision providers. See the examples directory and
the extension guide for provider construction and custom adapters.

## Next steps

- Learn how retrieval scopes and citations work.
- Configure model and storage adapters through the public API.
- Read the deployment limitations before running a multi-user service.
