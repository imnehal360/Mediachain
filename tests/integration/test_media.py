import shutil

import pytest

from mediachain import MediaChain
from mediachain.core.config import ProcessingConfig
from mediachain.core.models import ExecutionContext, RetrievalFilter, SpeechSegment
from mediachain.loaders.local import LocalLoader
from mediachain.modalities.audio.ffmpeg import command
from mediachain.modalities.video.sampling import IntervalSampler, SceneSampler
from mediachain.processors.text import TextProcessor

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg unavailable")


async def test_delayed_audio_uses_original_timeline(tmp_path):
    pytest.importorskip("av")
    path = tmp_path / "delayed.mp4"
    await command(
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=blue:s=160x120:r=10:d=4",
        "-itsoffset",
        "1.5",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=2",
        "-c:v",
        "mpeg4",
        "-c:a",
        "aac",
        str(path),
    )

    class Speech:
        model_id, model_version = "fixture", "1"

        async def transcribe(self, path):
            return [SpeechSegment(text="late audio", start_time=0.1, end_time=1.8)]

    class Vision:
        model_id, model_version = "fixture", "1"

        async def describe(self, path, prompt):
            return "blue screen"

    chain = MediaChain(
        data_dir=tmp_path / "data",
        speech=Speech(),
        vision=Vision(),
        config=ProcessingConfig(frame_interval=1),
    )
    asset = await chain.add(str(path))
    docs = await chain.documents.list_documents(
        RetrievalFilter(media_ids=[asset.id], modalities=["audio"])
    )
    assert 1.5 < docs[0].start_time < 1.7
    assert 3.1 < docs[0].end_time < 3.4


async def test_scene_and_interval_sampling_and_limits(tmp_path):
    pytest.importorskip("av")
    path = tmp_path / "scenes.mp4"
    await command(
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=blue:s=160x120:r=10:d=1",
        "-f",
        "lavfi",
        "-i",
        "color=c=red:s=160x120:r=10:d=1",
        "-filter_complex",
        "[0:v][1:v]concat=n=2:v=1:a=0[out]",
        "-map",
        "[out]",
        "-c:v",
        "mpeg4",
        str(path),
    )
    frames = [item async for item in SceneSampler().sample(path, tmp_path)]
    assert len(frames) == 2
    assert frames[1][1] == pytest.approx(1.0, abs=0.1)
    with pytest.raises(Exception, match="limit"):
        _ = [item async for item in IntervalSampler(0.1, max_frames=1).sample(path, tmp_path)]


async def test_pdf_empty_and_html_cleaning(tmp_path):
    from pypdf import PdfWriter

    pdf = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(pdf)
    result = await TextProcessor().process(await LocalLoader().load(str(pdf)), ExecutionContext())
    assert not result.documents and result.warnings
    html = tmp_path / "page.html"
    html.write_text("<h1>Visible</h1><script>secret script</script><p>Content</p>")
    result = await TextProcessor().process(await LocalLoader().load(str(html)), ExecutionContext())
    assert result.documents[0].content == "Visible Content"
