# MediaChain

MediaChain is a Python framework for turning text, audio, and video into searchable,
timestamped evidence. It combines replaceable model and storage adapters, hybrid retrieval,
grounded responses, workflows, bounded tool agents, and an optional authenticated API.

!!! warning "Alpha software"

    Version 0.1.0 is a developer preview. Public APIs may change before 1.0, and production
    deployments must account for the limitations described in the deployment guide.

The published package is available on [PyPI](https://pypi.org/project/mediachain/).
The Python SDK and repository React application are distinct: the base SDK uses lexical retrieval
without an LLM; the configured local app adds MiniLM, Whisper, and Ollama.

## Start with local text

```bash
pip install mediachain
```

```python
from mediachain import MediaChain

mc = MediaChain(data_dir=".mediachain")
asset = mc.add_sync("notes.txt")
response = mc.ask_sync("What are the main ideas?", media_ids=[asset.id])

print(response.answer)
for source in response.sources:
    print(source)
```

The default text path works without cloud credentials or model downloads. Continue with the
[five-minute quickstart](getting-started.md), then read about
[retrieval and grounding](retrieval-and-grounding.md).

## Choose a path

- **Library users:** start with installation, ingestion, and querying in the quickstart.
- **Adapter authors:** read the extension contracts and API reference.
- **Service operators:** read deployment and validation before exposing the API.

## Media and application guides

- [Complete local model-backed text, PDF, audio, and video setup](local-media.md)
- [Web app, YouTube imports, agent analysis, and saved conversations](web-application.md)
- [Dated validation results and limitations](VALIDATION.md)
