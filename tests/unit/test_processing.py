from pathlib import Path

import pytest

from mediachain.core.config import ProcessingConfig
from mediachain.core.models import ExecutionContext, MediaAsset, Modality, SpeechSegment
from mediachain.loaders.local import LocalLoader
from mediachain.modalities.video.sampling import IntervalSampler
from mediachain.processors.audio import AudioProcessor
from mediachain.processors.text import TextProcessor
from mediachain.processors.video import VideoProcessor


def test_video_sampling_adapts_to_long_media():
    class Vision:
        model_id, model_version = "vision", "1"

    processor = VideoProcessor(
        Vision(),
        sampler=IntervalSampler(interval=5, max_frames=120),
    )
    asset = MediaAsset(
        id="video",
        source="video.mp4",
        media_type=Modality.VIDEO,
        content_hash="hash",
        duration=4980,
    )
    sampler = processor._sampler_for(asset)
    assert isinstance(sampler, IntervalSampler)
    assert sampler.interval == pytest.approx(41.5)
    assert sampler.max_frames == 120


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


async def test_audio_assigns_overlapping_hosted_speaker(tmp_path):
    class Speech:
        model_id, model_version = "speech", "1"

        async def transcribe(self, audio_path: Path):
            return [SpeechSegment(text="Hello", start_time=2, end_time=5)]

    class Diarization:
        model_id, model_version = "diarization", "1"

        async def diarize(self, audio_path: Path):
            return [SpeechSegment(text="", speaker="speaker-1", start_time=1, end_time=6)]

    path = tmp_path / "a.wav"
    path.write_bytes(b"fixture")
    asset = await LocalLoader().load(str(path))
    docs = await AudioProcessor(Speech(), Diarization()).transcribe(asset, path, ExecutionContext())
    assert docs[0].metadata["speaker"] == "speaker-1"
    assert docs[0].provenance[-1].operation == "diarize"


async def test_scanned_pdf_uses_configured_ocr(tmp_path):
    PdfWriter = pytest.importorskip("pypdf").PdfWriter
    path = tmp_path / "scan.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(path)

    class OCR:
        model_id, model_version = "hosted-ocr", "1"

        async def extract(self, document_path: Path):
            return ["Scanned invoice total is 42 dollars"]

    asset = await LocalLoader().load(str(path))
    result = await TextProcessor(ocr=OCR()).process(asset, ExecutionContext())
    assert result.documents[0].content == "Scanned invoice total is 42 dollars"
    assert result.documents[0].metadata["page"] == 1
    assert result.documents[0].metadata["processing"]["ocr"] == ["hosted-ocr", "1"]


async def test_loader_limits_and_owner_identity(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("abc")
    with pytest.raises(Exception, match="limit"):
        await LocalLoader(max_bytes=2).load(str(path))
    loader = LocalLoader()
    assert (await loader.load(str(path), "a")).id != (await loader.load(str(path), "b")).id
