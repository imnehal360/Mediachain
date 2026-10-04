"""Measured local baseline. Run with: uv run python benchmarks/retrieval.py --documents 1000"""

import argparse
import asyncio
import json
import platform
import tempfile
import time
from pathlib import Path

from mediachain import MediaChain
from mediachain.core.config import ProcessingConfig


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--documents", type=int, default=100)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        chain = MediaChain(
            data_dir=root / "index", config=ProcessingConfig(chunk_size=200, chunk_overlap=0)
        )
        source = root / "sample.txt"
        source.write_text(
            "Artificial intelligence connects data and reasoning. ".ljust(200) * args.documents
        )
        start = time.perf_counter()
        asset = await chain.add(str(source))
        ingest = time.perf_counter() - start
        start = time.perf_counter()
        response = await chain.ask("artificial intelligence", [asset.id])
        query = time.perf_counter() - start
        print(
            json.dumps(
                {
                    "python": platform.python_version(),
                    "platform": platform.platform(),
                    "embedding": chain.embeddings.space.model_dump(),
                    "input_blocks": args.documents,
                    "ingest_seconds": ingest,
                    "query_seconds": query,
                    "sources": len(response.sources),
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
