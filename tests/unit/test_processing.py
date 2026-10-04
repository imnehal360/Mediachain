from pathlib import Path

import pytest

from mediachain.core.config import ProcessingConfig
from mediachain.core.models import ExecutionContext, SpeechSegment
from mediachain.loaders.local import LocalLoader
from mediachain.processors.audio import AudioProcessor
from mediachain.processors.text import TextProcessor


async def test_text_chunking(tmp_path):
    path = tmp_path / "test.txt"
    path.write_text("abcdefghijklmnopqrstuvwxyz")
    asset = await LocalLoader().load(str(path))
    result = await TextProcessor(ProcessingConfig(chunk_size=10, chunk_overlap=2)).process(
        asset, ExecutionContext()
    )
    assert [d.content for d in result.documents] == ["abcdefghij", "ijklmnopqr", "qrstuvwxyz"]
    assert all(d.source == str(path) for d in result.documents)
    assert result == await TextProcessor(ProcessingConfig(chunk_size=10, chunk_overlap=2)).process(
        asset, ExecutionContext()
    )


async def test_audio_provenance(tmp_path):
    class Speech:
        model_id, model_version = "fake", "1"

        async def transcribe(self, audio_path: Path):
            return [SpeechSegment(text="Revenue grows", start_time=120, end_time=140)]

    path = tmp_path / "a.wav"
    path.write_bytes(b"fixture")
    asset = await LocalLoader().load(str(path))
    docs = await AudioProcessor(Speech()).transcribe(asset, path, ExecutionContext())
    assert docs[0].start_time == 120
    assert docs[0].provenance[0].model_id == "fake"
    assert docs[0].asset_id == asset.id


async def test_loader_limits_and_owner_identity(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("abc")
    with pytest.raises(Exception, match="limit"):
        await LocalLoader(max_bytes=2).load(str(path))
    loader = LocalLoader()
    assert (await loader.load(str(path), "a")).id != (await loader.load(str(path), "b")).id
