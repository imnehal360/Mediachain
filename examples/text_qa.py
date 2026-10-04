"""Run: uv run python examples/text_qa.py notes.txt 'your question'"""

import argparse
import asyncio

from mediachain import MediaChain


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("file")
    parser.add_argument("question", nargs="?", default="What is artificial intelligence?")
    args = parser.parse_args()
    chain = MediaChain()
    asset = await chain.add(args.file)
    response = await chain.ask(args.question, [asset.id])
    print(response.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
