# Release checklist

## Before each release

- Confirm the distribution name on PyPI and the public project name.
- Add repository, documentation, and issue-tracker URLs to `pyproject.toml`.
- Confirm CI passes on every supported Python version.
- Build the documentation with warnings treated as errors.
- Run all tests, linting, formatting, and type checking.
- Validate the wheel in a clean environment using the README quickstart.
- Optionally publish a candidate to TestPyPI; verify the final published PyPI package in a clean environment.
- Configure a PyPI Trusted Publisher for the `pypi` GitHub environment.
- Create a GitHub release and tag matching `mediachain.__version__`.

## Release commands

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src/mediachain
uv build
```

The publishing workflow builds distributions from the tagged commit and uploads the resulting wheel
and source archive through PyPI Trusted Publishing. Never reuse a version number: PyPI releases are
immutable.
