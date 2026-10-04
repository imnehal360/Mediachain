import json
import shutil
from pathlib import Path

import pytest

from mediachain import MediaChain
from mediachain.core.config import ProcessingConfig
from mediachain.core.models import ChatOutput, RetrievalFilter, SpeechSegment
from mediachain.modalities.audio.ffmpeg import command
from mediachain.temporal.alignment import align


class FixtureSpeech:
    """Deterministic fixture provider, never presented as actual speech recognition."""

    model_id, model_version = "test-speech", "1"
    calls = 0

    async def transcribe(self, path):
        assert path.read_bytes()[:4] == b"RIFF"
        self.calls += 1
        return [
            SpeechSegment(
                text="Artificial intelligence connects data and reasoning.",
                start_time=0.1,
                end_time=1.8,
            )
        ]


class FixtureVision:
    model_id, model_version = "test-vision", "1"

    async def describe(self, path, prompt):
        from PIL import Image

        with Image.open(path) as image:
            assert image.width > 0
        return "A blue screen with a simple chart."


class FixtureChat:
    model_id, model_version = "test-chat", "1"

    async def generate(self, messages):
        evidence = json.loads(messages[-1].content)["evidence"]
        return ChatOutput(
            content=json.dumps(
                {
                    "answer": "The fixture transcript discusses artificial intelligence, while the fixture visual description reports a blue chart.",
                    "citation_ids": [r["citation_id"] for r in evidence],
                }
            )
        )


async def test_text_lifecycle_cache_restart_and_owner(tmp_path):
    source = tmp_path / "notes.txt"
    source.write_text("Artificial intelligence connects data and reasoning.")
    mc = MediaChain(data_dir=tmp_path / "data")
    asset = await mc.add(str(source))
    again = await mc.add(str(source))
    assert again.id == asset.id
    assert len(await mc.documents.list_documents(RetrievalFilter())) == 1
    response = await mc.ask("artificial intelligence", [asset.id])
    assert response.sources[0].media_id == asset.id
    assert response.metadata["mode"] == "extractive"
    summary = await mc.summarize([asset.id], focus="artificial intelligence")
    assert summary.sources[0].media_id == asset.id
    assert summary.metadata["mode"] == "extractive"
    with pytest.raises(KeyError):
        await mc.ask("artificial intelligence", [asset.id], owner_id="other")
    mc = MediaChain(data_dir=tmp_path / "data")
    assert (await mc.ask("artificial intelligence")).sources
    await mc.delete(asset.id)
    assert (await mc.ask("artificial intelligence")).insufficient_evidence
    assert not Path(asset.source).exists()
    assert source.exists()


def test_public_sdk_exports():
    import mediachain

    assert mediachain.MediaChain is MediaChain
    assert mediachain.ProcessingConfig is ProcessingConfig
    assert mediachain.RetrievalFilter is RetrievalFilter


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg is not installed")
async def test_real_decode_mock_models_multimodal_golden(tmp_path):
    pytest.importorskip("av")
    path = tmp_path / "fixture.mp4"
    await command(
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=blue:s=160x120:r=10:d=2",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=2",
        "-shortest",
        "-c:v",
        "mpeg4",
        "-c:a",
        "aac",
        str(path),
    )
    speech = FixtureSpeech()
    mc = MediaChain(
        data_dir=tmp_path / "data",
        speech=speech,
        vision=FixtureVision(),
        llm=FixtureChat(),
        config=ProcessingConfig(frame_interval=0.5),
    )
    asset = await mc.add(str(path))
    docs = await mc.documents.list_documents(RetrievalFilter(media_ids=[asset.id]))
    assert {d.modality for d in docs} == {"audio", "video"}
    assert align(docs)
    response = await mc.ask(
        "What did the speaker say about artificial intelligence, and what was displayed on screen at that moment?",
        [asset.id],
    )
    assert {s.modality for s in response.sources} == {"audio", "video"}
    assert all(s.start_time is not None for s in response.sources)
    assert all(s.source == asset.source for s in response.sources)
    await mc.process(asset.id)
    assert speech.calls == 1
    await mc.delete(asset.id)
    assert not await mc.documents.list_documents(RetrievalFilter())
    assert not mc.vectors.records


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg is not installed")
async def test_audio_only(tmp_path):
    path = tmp_path / "fixture.wav"
    await command(
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=2",
        str(path),
    )
    mc = MediaChain(data_dir=tmp_path / "data", speech=FixtureSpeech())
    asset = await mc.add(str(path))
    response = await mc.ask("artificial intelligence", [asset.id])
    assert response.sources[0].modality == "audio"
    assert response.sources[0].start_time == 0.1
