import sys
from pathlib import Path
from types import ModuleType

import pytest

from mediachain.core.errors import RemoteMediaError
from mediachain.loaders.youtube import _download, validate_youtube_url


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=abcdefghijk",
        "https://youtu.be/abcdefghijk",
        "https://music.youtube.com/watch?v=abcdefghijk&list=example",
        "https://www.youtube.com/live/abcdefghijk",
    ],
)
def test_validate_youtube_video_urls(url):
    assert validate_youtube_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "http://youtube.com/watch?v=abcdefghijk",
        "https://example.com/watch?v=abcdefghijk",
        "https://www.youtube.com/playlist?list=example",
        "https://user:password@youtube.com/watch?v=abcdefghijk",
        "https://youtube.com:444/watch?v=abcdefghijk",
    ],
)
def test_validate_youtube_rejects_unsafe_or_non_video_urls(url):
    with pytest.raises(RemoteMediaError):
        validate_youtube_url(url)


def test_youtube_download_is_single_bounded_video(monkeypatch, tmp_path):
    captured = {}

    class FakeYoutubeDL:
        def __init__(self, options):
            captured.update(options)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def extract_info(self, url, download):
            assert download is True
            assert (
                captured["match_filter"]({"duration": 120, "is_live": False}, incomplete=False)
                is None
            )
            output = Path(captured["outtmpl"].replace("%(ext)s", "mp4"))
            output.write_bytes(b"video")
            return {
                "title": "A Podcast: Episode 1?",
                "duration": 120,
                "webpage_url": url,
            }

    package = ModuleType("yt_dlp")
    package.YoutubeDL = FakeYoutubeDL  # type: ignore[attr-defined]
    utils = ModuleType("yt_dlp.utils")
    utils.DownloadError = RuntimeError  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "yt_dlp", package)
    monkeypatch.setitem(sys.modules, "yt_dlp.utils", utils)
    monkeypatch.setattr(
        "mediachain.loaders.youtube.shutil.which",
        lambda command: f"C:/tools/{command}.exe",
    )

    result = _download(
        "https://youtu.be/abcdefghijk",
        tmp_path,
        max_bytes=100,
        max_duration_seconds=3600,
    )
    assert result.path.name == "download.mp4"
    assert result.title == "A Podcast Episode 1"
    assert result.duration == 120
    assert captured["noplaylist"] is True
    assert captured["max_filesize"] == 100
    assert captured["remote_components"] == []
    assert captured["js_runtimes"]["node"]["path"].endswith("node.exe")
