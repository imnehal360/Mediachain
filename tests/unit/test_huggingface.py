from types import SimpleNamespace

import pytest

from mediachain.models.providers import HuggingFaceEmbeddingModel, HuggingFaceSpeech


class ArrayResult:
    def __init__(self, values):
        self.values = values

    def tolist(self):
        return self.values


async def test_huggingface_timestamped_speech(tmp_path):
    class Client:
        async def automatic_speech_recognition(self, audio, **options):
            assert audio == tmp_path / "audio.wav"
            assert options["model"] == "openai/whisper-large-v3"
            assert options["extra_body"]["return_timestamps"]
            return SimpleNamespace(
                text="Hello world",
                chunks=[SimpleNamespace(text="Hello", timestamp=[1.5, 2.5])],
            )

    model = HuggingFaceSpeech("openai/whisper-large-v3", "token", client=Client())
    segments = await model.transcribe(tmp_path / "audio.wav")
    assert segments[0].text == "Hello"
    assert segments[0].start_time == 1.5
    assert segments[0].end_time == 2.5


async def test_huggingface_embedding_batch_and_dimensions():
    class Client:
        async def feature_extraction(self, texts, **options):
            assert texts == ["one", "two"]
            assert options["normalize"] and options["truncate"]
            return ArrayResult([[1, 0], [0, 1]])

    model = HuggingFaceEmbeddingModel("embedding", "token", 2, client=Client())
    assert await model.embed(["one", "two"]) == [[1.0, 0.0], [0.0, 1.0]]

    model.space = model.space.model_copy(update={"dimensions": 3})
    with pytest.raises(ValueError, match="dimensions"):
        await model.embed(["one", "two"])


async def test_huggingface_speech_falls_back_to_whole_audio_timestamp(tmp_path):
    import wave

    path = tmp_path / "audio.wav"
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16_000)
        audio.writeframes(b"\0\0" * 16_000)

    class Client:
        async def automatic_speech_recognition(self, audio, **options):
            return SimpleNamespace(text="One second", chunks=None)

    model = HuggingFaceSpeech("speech", "token", client=Client())
    assert (await model.transcribe(path))[0].end_time == 1.0
