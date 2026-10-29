# Local models: text, PDF, audio, and video

This guide uses the SDK installed from PyPI. It runs models on your computer; no hosted API
key is required. Dependencies and model weights need internet access for their initial download.
Local inference speed depends on hardware and input length. Start with a short clip.

## Install dependencies and tools

In your activated Python environment:

```bash
python -m pip install "mediachain[http,media,pdf,ocr,speech,embeddings]==0.1.0"
```

Install [FFmpeg](https://ffmpeg.org/download.html) and put both `ffmpeg` and `ffprobe` on PATH.
Install [Ollama](https://docs.ollama.com/quickstart), open it, and download the configured model:

```bash
ffmpeg -version
ffprobe -version
ollama pull qwen3-vl:2b-instruct
```

If Ollama is not already serving, run `ollama serve` in another terminal and leave it running.
The example connects to its local chat-completions endpoint at `http://127.0.0.1:11434/v1`.
The Qwen model is used for both answers and images; see its [model page](https://ollama.com/library/qwen3-vl).

## Complete SDK program

Save as `local_media.py`:

```python
import argparse
import asyncio
from mediachain import MediaChain, ProcessingConfig
from mediachain.embeddings.local import SentenceTransformerEmbeddings
from mediachain.models.providers import FasterWhisperSpeech, HTTPChatModel, HTTPVisionModel
from mediachain.processors.ocr import VisionPDFOCR


def build_chain():
    model = "qwen3-vl:2b-instruct"
    endpoint = "http://127.0.0.1:11434/v1"
    vision = HTTPVisionModel(model, endpoint)
    return MediaChain(
        data_dir=".mediachain",
        llm=HTTPChatModel(model, endpoint),
        speech=FasterWhisperSpeech("base", device="cpu", compute_type="int8"),
        vision=vision,
        ocr=VisionPDFOCR(vision, max_pages=200),
        embeddings=SentenceTransformerEmbeddings(),
        config=ProcessingConfig(
            frame_interval=5, max_frames=120, speech_timeout=7200,
        ),
    )


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file")
    parser.add_argument("question")
    args = parser.parse_args()
    mc = build_chain()
    asset = await mc.add(args.file)
    response = await mc.ask(args.question, media_ids=[asset.id])
    print(response.answer)
    for source in response.sources:
        print(source.model_dump())


if __name__ == "__main__":
    asyncio.run(main())
```

Use an existing input file:

```bash
python local_media.py notes.txt "What does the text say about Saturn?"
python local_media.py document.pdf "What is the main finding?"
python local_media.py recording.wav "What did the speaker say about the deadline?"
python local_media.py lecture.mp4 "What did the speaker explain about the diagram?"
```

These are separate invocations; choose one appropriate to your file. Generated answers require
matching evidence and a model that follows the grounded JSON response instructions. A small local
model can return malformed output or insufficient evidence; successful startup is not a guarantee
of answer quality.

## What each media path does

- **Text/Markdown/HTML:** extract text, normalize whitespace, split into overlapping character
  chunks (1,200 characters, overlap 150 by default), then embed and index. HTML scripts/styles
  are excluded. MiniLM uses 384-dimensional semantic embeddings; the default SDK hash encoder
  is a different, non-neural baseline.
- **PDF:** pypdf extracts text; when a page is empty and OCR is configured, rendered PDF pages
  are sent to vision OCR and its text fills empty pages. The OCR implementation can render
  nonempty pages too and is capped by `max_pages`; it is not a layout-preserving PDF parser.
- **Audio:** FFprobe inspects streams; FFmpeg extracts audio; Whisper produces timestamped
  segments that are embedded and indexed. Transcript timings are aligned to the original media,
  clipped to its duration, and entirely out-of-range segments are dropped.
- **Video:** transcription and sampled-frame descriptions run concurrently. Both text forms
  are embedded with timestamps. Short clips use the requested interval; long clips spread
  samples across the duration to fit the frame budget. Visual descriptions can miss events
  between samples.

Whisper and MiniLM load lazily. First use can include weight downloads; later use requires
those cached files. Ollama must remain available while generating answers or frame descriptions.
The two-hour speech timeout is separate from per-call vision/model timeouts; it is not a speed
estimate. There is no progress percentage or partial-query support in the current processing path.

## Questions and summaries

SDK `ask` calls do not remember earlier turns. Ask self-contained questions, or use the persistent
conversation API in the [web application guide](web-application.md). `summarize` uses retrieved,
bounded evidence; it does not guarantee an exhaustive reading of a long recording or document.
