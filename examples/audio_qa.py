"""Real local transcription: uv run --extra speech python examples/audio_qa.py podcast.wav"""

import argparse
import asyncio

from mediachain import MediaChain
from mediachain.models.providers import FasterWhisperSpeech


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("file")
    parser.add_argument("--model", default="base")
    parser.add_argument("--question", default="What was said about artificial intelligence?")
    args = parser.parse_args()
    chain = MediaChain(speech=FasterWhisperSpeech(args.model))
    asset = await chain.add(args.file)
    print((await chain.ask(args.question, [asset.id])).model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
