"""Reference application: real speech, vision and grounded chat generation."""

import argparse
import asyncio
import os

from mediachain import MediaChain
from mediachain.core.config import ProcessingConfig
from mediachain.embeddings.local import SentenceTransformerEmbeddings
from mediachain.models.providers import FasterWhisperSpeech, HTTPChatModel, HTTPVisionModel


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video")
    parser.add_argument(
        "--question",
        default="What did the speaker say about artificial intelligence, and what was displayed on screen at that moment?",
    )
    parser.add_argument("--interval", type=float, default=2)
    args = parser.parse_args()
    base_url = os.environ["MODEL_BASE_URL"]
    api_key = os.environ.get("MODEL_API_KEY", "")
    chain = MediaChain(
        speech=FasterWhisperSpeech(os.environ.get("SPEECH_MODEL", "base")),
        vision=HTTPVisionModel(os.environ["VISION_MODEL"], base_url, api_key),
        llm=HTTPChatModel(os.environ["CHAT_MODEL"], base_url, api_key),
        embeddings=SentenceTransformerEmbeddings(),
        config=ProcessingConfig(frame_interval=args.interval),
    )
    asset = await chain.add(args.video)
    while True:
        response = await chain.ask(args.question, [asset.id])
        print(response.answer)
        for reference in response.sources:
            print(
                f"  {reference.modality}: {reference.start_time:.2f}–{reference.end_time:.2f}s ({reference.source})"
            )
        question = await asyncio.to_thread(input, "\nNext question (empty to quit): ")
        if not question.strip():
            break
        args.question = question


if __name__ == "__main__":
    asyncio.run(main())
