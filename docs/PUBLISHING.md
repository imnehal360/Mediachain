# Publishing MediaChain to PyPI

Version **0.1.0** was published on 29 October 2026. The steps below are release-maintenance
instructions; existing maintainers should use the active project publisher rather than register
a new pending publisher for an already-created project.

MediaChain is packaged as `mediachain`; developers import `MediaChain` from `mediachain`.
The base install requires Python 3.11+ and Pydantic. Optional extras install media, speech,
embedding, API, and storage integrations. FFmpeg and Ollama remain separate system dependencies;
the Python wheel does not bundle the repository's React web application, downloaded models,
local configuration, or user data.

## Prepare a release

1. Confirm that you own the PyPI project name, or that the name can be registered.
   A missing public project page does not guarantee that PyPI will permit the name.
2. Set the same release version in `pyproject.toml` and `src/mediachain/__init__.py`.
3. Run the tests and build the distributions:

   ```powershell
   uv run pytest -q
   uv build
   uvx twine check --strict dist/*
   ```

4. Inspect both archives and install the wheel into a clean environment. Do not upload
   `.env`, `.mediachain/`, downloaded models/tools, or IDE configuration.
5. Commit and push the reviewed release source before creating its GitHub release.

## Configure PyPI Trusted Publishing

Create a PyPI account and configure a pending publisher at
<https://pypi.org/manage/account/publishing/> using:

| Field | Value |
| --- | --- |
| Project name | `mediachain` |
| GitHub owner | `imnehal360` |
| Repository | `Mediachain` |
| Workflow filename | `publish.yml` |
| Environment | `pypi` |

In the GitHub repository, configure the `pypi` environment with release approval protection.
The existing `.github/workflows/publish.yml` builds and publishes when a GitHub release is
published. A release tag such as `v0.1.0` must match the package version. This workflow uses
short-lived credentials from Trusted Publishing; no PyPI API token needs to be shared in chat.

Publishing a GitHub release triggers the upload. Complete account setup, checks, and review
before doing so. Uploaded release filenames cannot be reused for a different build.

## After publication

Verify the new release in a fresh Python environment:

```powershell
python -m pip install mediachain
python -c "from mediachain import MediaChain; import mediachain; print(mediachain.__version__)"
```

For optional functionality, install the relevant extras, for example:

```powershell
python -m pip install "mediachain[media,pdf,speech,embeddings,http,youtube]"
```

The published project page is <https://pypi.org/project/mediachain/>.
Documentation changes can be deployed from GitHub without a package release. The README shown
on PyPI belongs to its uploaded distribution and is not updated by pushing README edits to GitHub;
updated distribution documentation appears with a subsequent package version. See the [official publishing guide](https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/).
