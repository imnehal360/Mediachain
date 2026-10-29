# Reference web application, YouTube, agents, and chats

The Python framework and the repository web application are distinct entry points. `pip install
mediachain` installs Python modules; it does not install a built React website, FFmpeg, Node.js,
Ollama, or model weights. The application demonstrates how those framework components fit together.

## Local Windows setup from a checkout

Install Git, [uv](https://docs.astral.sh/uv/), Node.js/npm, FFmpeg/FFprobe, and Ollama. Add their
executables to PATH and open a fresh terminal. Start Ollama before setup. In PowerShell:

```powershell
git clone https://github.com/imnehal360/Mediachain.git
cd Mediachain
uv sync --python 3.13 --dev --extra api --extra media --extra pdf --extra ocr --extra speech --extra embeddings --extra http --extra youtube
Copy-Item .env.local.example .env
powershell -ExecutionPolicy Bypass -File .\scripts\setup-local.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start-local.ps1
```

The copy command is for a fresh checkout: do not overwrite an existing customized `.env`.
If offline Hugging Face flags prevent first-time model downloads, temporarily unset those flags
while downloading the models, then restore them for offline use. Model files require several GB;
exact disk and memory needs depend on installed models and runtime versions.

Open `http://127.0.0.1:8000`. Keep its terminal running. The script uses `.venv` directly, loads
`.env`, configures local tools, and ensures Ollama is reachable. Windows runs one worker without
`--reload` because Uvicorn's reload event loop cannot launch FFmpeg/FFprobe subprocesses.
Restart after code changes; stop an existing listener before launching another server on port 8000.
After frontend changes, rebuild with `npm.cmd --prefix frontend run build`, then refresh the browser.

The local example disables authentication and only accepts loopback clients. Everybody using this
local workspace shares the owner `local-user` and its media/chats. This is not per-person login.
For hosted services, keep authentication enabled and follow [deployment](DEPLOYMENT.md).

## Upload and ask

1. Upload a supported file or paste a public YouTube video URL.
2. Processing starts automatically. The page displays preparation status and a retry action on failure.
3. When ready, ask a question or request a summary. Newly imported media is selected automatically.
4. Open an answer's citation to inspect the source; audio/video references include timestamps.
5. Use Library to manage media and retry existing uploads without downloading them again.

The current job completes transcription, frame descriptions, and indexing before the new media is
available for questions. Download completion alone does not mean it is ready. Polling logs with
`200 OK` are normal status checks; `202 Accepted` means processing was queued, not completed.
Long recordings can take considerable time. Test with 30?60-second clips before long videos.

## YouTube support

Single public HTTPS YouTube video links are supported: normal watch links, `youtu.be`, Shorts,
YouTube Music video links, and completed live recordings. Active/upcoming streams, playlist-only
URLs, channels, and non-YouTube URLs are rejected. Private, restricted, or unavailable videos can
fail. Defaults are four hours and 500 MB; yt-dlp selects a bounded 480p-oriented download.
Node.js, FFmpeg, and the `youtube` extra are required. Only process media you have permission to use.

The API's URL import endpoint stores the downloaded media; the UI then separately requests
processing. For local no-auth mode, this PowerShell example performs both:

```powershell
$body = @{url="https://www.youtube.com/watch?v=YOUR_VIDEO_ID"} | ConvertTo-Json
$asset = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/v1/media/url" -ContentType "application/json" -Body $body
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/v1/media/$($asset.id)/process"
```

Replace the placeholder with a public video you are permitted to process. Authenticated deployments
also require `Authorization: Bearer <workspace-key>` headers. `MediaChain.add(youtube_url)` is not a
YouTube shortcut: the default SDK loader accepts local files. SDK authors can call
`mediachain.loaders.youtube.download_youtube(url, destination, max_bytes, max_duration_seconds)`,
copy the returned file with `await mc.load(str(download.path))` before cleaning staging files,
and then call `await mc.process(asset.id)` with configured models.

Captions-first retrieval, priority timestamp processing, and progressive partial answers are
**not implemented in 0.1.0**. YouTube imports use the same full video pipeline as uploaded files.

## Quick Answer and Agent Analysis

**Quick Answer** retrieves evidence and makes one answer-generation pass when a chat model is
configured. Hybrid retrieval combines keywords and embeddings, optionally pairing overlapping
transcript/visual evidence. Citation IDs are checked against retrieved documents.

**Agent Analysis** uses the configured chat model to choose bounded tools: `search_text`,
`search_audio`, `search_video`, `search_timeline`, `get_transcript`, and `summarize_media`.
Tools are scoped to the current owner and media selection. The UI displays tool activity.
Grounding failures or agent budget/time limits can trigger ordinary grounded-RAG fallback.
Agent mode is unavailable without a chat model; it does not have general shell or computer access.

SDK authors can import `Agent`, `AgentLimits`, and `media_tools` from `mediachain.agents`.
`Agent(llm, media_tools(mc, owner_id="local", media_ids=[asset.id]), AgentLimits())` constructs
an agent; use `await agent.run_detailed(question, ExecutionContext(owner_id="local"))` to run it.
`ExecutionContext` is exported from `mediachain`. Direct agent results are not identical to API
`ModelResponse`: the API additionally resolves and validates observed citation references and
handles grounded-RAG fallback. The optional SDK `extract_frame` tool is enabled only when an
output directory is supplied; it is not included in the default web agent tool list.

## Persistent conversations

Answers remain in a scrollable thread with their questions, citations, and agent activity.
**New chat** begins a separate thread. **Saved conversations** reopens a thread after refreshing,
navigating away, or restarting. History starts with messages saved by this feature; previously
discarded answers cannot be recovered.

The API stores successful question/answer pairs atomically in
`MEDIACHAIN_DATA_DIR/conversations.sqlite`; the local default directory is `.mediachain`.
Recent context (up to six messages, bounded before use) helps interpret follow-ups. Previous
answers are context, not independent evidence: new answers still retrieve authorized source material.
Changing selected media excludes previous context on the next turn. Direct SDK `ask` remains
stateless. Conversations list the latest 100 threads; listing does not delete older stored threads.
This local SQLite conversation store is not a distributed PostgreSQL-backed chat service.

## Relevant REST endpoints

The running API exposes interactive schemas at `http://127.0.0.1:8000/docs`.

| Method/path | Purpose |
| --- | --- |
| `POST /api/v1/media` | Multipart file upload; returns stored asset |
| `POST /api/v1/media/url` | YouTube download; returns stored asset |
| `POST /api/v1/media/{id}/process` | Queue a processing job |
| `GET /api/v1/jobs/{id}` | Check job status/error |
| `POST /api/v1/query` | Quick Answer |
| `POST /api/v1/agent/query` | Agent Analysis |
| `POST /api/v1/summarize` | Grounded summary |
| `GET /api/v1/conversations` | List owner-scoped threads |
| `POST /api/v1/conversations` | Create with `media_ids` or `null` for the authorized library |
| `GET /api/v1/conversations/{id}` | Load messages and responses |
| `POST /api/v1/conversations/{id}/messages` | Send `question`, `media_ids`, and `mode` (`quick`, `agent`, `summary`) |

All conversation endpoints use the same owner access checks as the media API. A failed generation
does not erase successful history. The local in-process queue cannot survive server termination;
restart/retry handling does not resume model work from intermediate checkpoints.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| `ffmpeg`/`ffprobe` missing | Put both on PATH, restart the terminal, use the startup script |
| Windows `NotImplementedError` at subprocess creation | Stop manual reload server; start with the repository script without reload |
| Port 8000 occupied | Stop the old server in its terminal, then restart |
| Ollama connection refused / model missing | Start Ollama; run `ollama list` and pull the configured model |
| Repeated status requests | Normal polling while jobs are queued/running; check UI status |
| Failed processing | Read the terminal traceback; retry the stored asset after resolving its cause |
| Old frontend | Rebuild `frontend`, then Ctrl+F5; do not expect Python code reload to rebuild React |
| Model grounding error | Try a precise, answerable question; verify retrieval and model JSON compliance |

No processing-duration guarantee is provided. Frame sampling may miss brief events, transcription
can be inaccurate, and valid citations do not prove every generated claim is correct.
