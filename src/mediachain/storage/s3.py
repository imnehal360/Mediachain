"""S3-compatible object storage with a bounded local processing cache."""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile
from typing import Any


class S3ObjectStore:
    """Persist originals remotely and materialize them only when processing needs a path."""

    def __init__(
        self,
        bucket: str,
        cache_dir: str | Path,
        *,
        prefix: str = "mediachain",
        region: str | None = None,
        endpoint_url: str | None = None,
        client: Any = None,
    ):
        if not bucket:
            raise ValueError("S3 bucket is required")
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.cache_dir = Path(cache_dir).resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        if client is None:
            import boto3

            client = boto3.client("s3", region_name=region, endpoint_url=endpoint_url)
        self.client = client

    def _remote_key(self, key: str) -> str:
        candidate = PurePosixPath(key)
        if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
            raise ValueError("Object key escapes storage prefix")
        return "/".join(part for part in (self.prefix, candidate.as_posix()) if part)

    def _cache_path(self, key: str) -> Path:
        remote = self._remote_key(key)
        path = (self.cache_dir / remote).resolve()
        if not path.is_relative_to(self.cache_dir) or path == self.cache_dir:
            raise ValueError("Object key escapes cache root")
        return path

    async def put(self, key: str, source: Path) -> str:
        remote = self._remote_key(key)
        target = self._cache_path(key)

        def upload() -> None:
            self.client.upload_file(str(source), self.bucket, remote)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

        await asyncio.to_thread(upload)
        return str(target)

    async def resolve(self, key: str) -> Path:
        remote = self._remote_key(key)
        target = self._cache_path(key)
        if target.is_file():
            return target

        def download() -> None:
            target.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(dir=target.parent, delete=False) as temp:
                temporary = Path(temp.name)
            try:
                self.client.download_file(self.bucket, remote, str(temporary))
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)

        await asyncio.to_thread(download)
        return target

    async def delete(self, key: str) -> None:
        remote = self._remote_key(key)
        target = self._cache_path(key)

        def remove() -> None:
            self.client.delete_object(Bucket=self.bucket, Key=remote)
            target.unlink(missing_ok=True)

        await asyncio.to_thread(remove)

    async def healthcheck(self) -> bool:
        await asyncio.to_thread(self.client.head_bucket, Bucket=self.bucket)
        return True
