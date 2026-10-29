"""Exercise media subprocesses on Uvicorn's actual Windows event loop."""

import shutil
import subprocess
import sys

import pytest


@pytest.mark.skipif(
    sys.platform != "win32" or shutil.which("ffprobe") is None,
    reason="Requires Windows and FFprobe",
)
def test_single_worker_uvicorn_can_run_ffprobe(tmp_path):
    script = tmp_path / "server_probe.py"
    script.write_text(
        """
import asyncio
import uvicorn
from mediachain.modalities.audio.ffmpeg import command

async def app(scope, receive, send):
    assert scope["type"] == "lifespan"
    assert (await receive())["type"] == "lifespan.startup"
    output = await command("ffprobe", "-version")
    assert b"ffprobe version" in output
    print("FFPROBE_OK", type(asyncio.get_running_loop()).__name__, flush=True)
    server.should_exit = True
    await send({"type": "lifespan.startup.complete"})
    assert (await receive())["type"] == "lifespan.shutdown"
    await send({"type": "lifespan.shutdown.complete"})

server = uvicorn.Server(uvicorn.Config(app, workers=1, reload=False, port=0))
server.run()
""",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
    assert "FFPROBE_OK" in result.stdout, result.stderr
    assert "ProactorEventLoop" in result.stdout
