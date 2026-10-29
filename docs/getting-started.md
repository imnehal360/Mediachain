# Getting started

MediaChain 0.1.0 is a published **alpha** Python framework. Install it from
[PyPI](https://pypi.org/project/mediachain/). Public interfaces may change before 1.0.

## Requirements and installation

Use Python 3.11 or newer; CI exercises Python 3.11?3.13. The base package needs only Pydantic.
Create a virtual environment with your installed Python:

```bash
python -m venv .venv
```

On Windows PowerShell, activate it with:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install "mediachain==0.1.0"
```

On macOS/Linux:

```bash
source .venv/bin/activate
python -m pip install "mediachain==0.1.0"
```

## First runnable example

Save this as `quickstart.py`, then run `python quickstart.py`:

```python
from pathlib import Path
from mediachain import MediaChain

Path("notes.txt").write_text(
    "MediaChain turns media into searchable evidence. "
    "Saturn has rings made of ice and rock.", encoding="utf-8"
)
mc = MediaChain(data_dir=".mediachain")
asset = mc.add_sync("notes.txt")
response = mc.ask_sync("What are Saturn rings made of?", media_ids=[asset.id])
print(response.answer)
for source in response.sources:
    print(source.model_dump())
```

The expected answer starts with **Retrieved evidence (no generation model configured)** and
includes matching text plus source references. This is retrieval, not a generated explanation.
No API keys, model downloads, FFmpeg, or Ollama are needed for this example.

## Defaults versus configured AI

| Component | Default `MediaChain()` | Configured local reference app |
| --- | --- | --- |
| Embeddings | `HashEmbeddings`, lexical hashing, 256 dimensions | MiniLM, 384 dimensions |
| Answers | Extractive evidence; no LLM | Qwen through Ollama |
| Speech | Not configured | Faster Whisper base, CPU INT8 |
| Vision/OCR | Not configured | Qwen vision/OCR |
| Metadata/documents | SQLite | SQLite |
| Vectors | In-memory, restored from stored documents when queried | Same default store |
| Conversations | Each SDK `ask` is stateless | API/UI saves conversations in SQLite |

`MediaChain()` does not automatically load `.env` or start Ollama. Inject SDK adapters explicitly.
The repository startup script loads `.env` and constructs them for the reference application.

## Optional packages

| Extra | Enables |
| --- | --- |
| `pdf` | Extractable PDF text via pypdf |
| `media` | PyAV and Pillow for video frames |
| `speech` | Faster Whisper transcription |
| `embeddings` | Sentence Transformers semantic embeddings |
| `http` | HTTP model adapters |
| `ocr` | PDF page rendering; also configure a vision model |
| `youtube` | yt-dlp and packaged dependencies; Node.js and FFmpeg are separate |
| `api` | FastAPI/Uvicorn API dependencies |
| `server` / `cloud` | Hosted storage, cache, job queue, and object adapters |

For example: `python -m pip install "mediachain[pdf]"`. Extras install dependencies, not model
configuration. See [local media](local-media.md) for a complete model-backed example.

## Async applications

Inside an existing event loop, use `await mc.add(...)`, `await mc.ask(...)`, and
`await mc.summarize(...)`. In scripts, wrap those calls in an async function and call
`asyncio.run(main())`. Do not call sync wrappers from an active event loop.

`load(source)` copies a file without processing; `process(asset_id)` processes and indexes it.
`add(source)` performs both. `delete(asset_id)` removes its managed media and indexed evidence.

## Storage and ownership

The chosen data directory contains `metadata.sqlite` and managed originals in `objects/`.
Documents persist across restarts; the vector index and processing cache are in memory by default.
A new client lazily rebuilds searchable vectors for selected stored documents. Reuse the original
asset ID or obtain assets with `await mc.metadata.list_assets("local")`.

The SDK owner defaults to `local`; the repository local web app uses `local-user`. These are
separate scopes. Pass matching `owner_id` values when using multiple owners.

## Development checkout

```bash
git clone https://github.com/imnehal360/Mediachain.git
cd Mediachain
uv sync --dev
uv run pytest -q
```

A PyPI install does not include the React UI, repository launch scripts, or examples directory.
Use a checkout for those. See [the web application guide](web-application.md).
