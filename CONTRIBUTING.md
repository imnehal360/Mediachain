# Contributing to MediaChain

MediaChain welcomes focused bug reports, documentation improvements, adapters, and tests. Version
0.1 is an alpha, so discuss substantial public API changes in an issue before implementing them.

## Development setup

```bash
git clone https://github.com/imnehal360/Mediachain.git
cd MediaChain
uv sync --dev
uv run pytest -q
```

If macOS ignores uv's editable `.pth` file because it has a hidden filesystem flag, run
`uv sync --no-editable --dev`. The pytest configuration includes `src` explicitly.

## Required checks

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src/mediachain
uv build
```

PostgreSQL and Redis tests are opt-in and require disposable service URLs. Never point the service
tests at data you need to keep. See `docs/VALIDATION.md` for the current validation boundary.

## Pull requests

- Keep changes scoped and include tests for behavior changes.
- Update public docstrings and guides when changing user-facing APIs.
- Add a changelog entry under `Unreleased`.
- Do not commit credentials, downloaded model weights, generated media, or local databases.
- Use conventional, imperative commit subjects when practical.
