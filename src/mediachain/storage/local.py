"""SQLite metadata/documents and confined filesystem objects for local development."""

from __future__ import annotations

import asyncio
import os
import shutil
import sqlite3
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from mediachain.core.models import Document, Job, MediaAsset, RetrievalFilter


class SQLiteStore:
    """One short transaction per call, offloaded from the event loop."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path == ":memory:":
            raise ValueError("Use a temporary file; connections are opened per transaction")
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY, owner TEXT NOT NULL, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY, asset_id TEXT NOT NULL, body TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS documents_asset ON documents(asset_id);
                CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, asset_id TEXT NOT NULL, body TEXT NOT NULL);
            """)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=30)

    async def _execute(self, sql: str, args: tuple[Any, ...] = (), read: bool = False) -> list[Any]:
        def execute() -> list[Any]:
            with self._connect() as db:
                cursor = db.execute(sql, args)
                return cursor.fetchall() if read else []

        return await asyncio.to_thread(execute)

    async def put_asset(self, asset: MediaAsset) -> None:
        await self._execute(
            "INSERT OR REPLACE INTO assets VALUES(?,?,?)",
            (asset.id, asset.owner_id, asset.model_dump_json()),
        )

    async def get_asset(self, asset_id: str) -> MediaAsset | None:
        rows = await self._execute("SELECT body FROM assets WHERE id=?", (asset_id,), True)
        return MediaAsset.model_validate_json(rows[0][0]) if rows else None

    async def list_assets(self, owner_id: str) -> list[MediaAsset]:
        rows = await self._execute(
            "SELECT body FROM assets WHERE owner=? ORDER BY id", (owner_id,), True
        )
        return [MediaAsset.model_validate_json(row[0]) for row in rows]

    async def delete_asset(self, asset_id: str) -> None:
        def delete() -> None:
            with self._connect() as db:
                db.execute("DELETE FROM documents WHERE asset_id=?", (asset_id,))
                db.execute("DELETE FROM jobs WHERE asset_id=?", (asset_id,))
                db.execute("DELETE FROM assets WHERE id=?", (asset_id,))

        await asyncio.to_thread(delete)

    async def replace_documents(self, asset_id: str, documents: list[Document]) -> None:
        if any(d.asset_id != asset_id for d in documents):
            raise ValueError("Cannot write documents for another asset")

        def replace() -> None:
            with self._connect() as db:
                db.execute("DELETE FROM documents WHERE asset_id=?", (asset_id,))
                db.executemany(
                    "INSERT INTO documents VALUES(?,?,?)",
                    [(d.id, d.asset_id, d.model_dump_json()) for d in documents],
                )

        await asyncio.to_thread(replace)

    async def list_documents(self, filters: RetrievalFilter) -> list[Document]:
        if filters.media_ids == []:
            return []
        sql = "SELECT body FROM documents"
        args: tuple[str, ...] = ()
        if filters.media_ids is not None:
            sql += " WHERE asset_id IN (" + ",".join("?" for _ in filters.media_ids) + ")"
            args = tuple(filters.media_ids)
        rows = await self._execute(sql, args, True)
        docs = [Document.model_validate_json(row[0]) for row in rows]
        return [d for d in docs if filters.matches(d)]

    async def delete_documents(self, asset_id: str) -> None:
        await self._execute("DELETE FROM documents WHERE asset_id=?", (asset_id,))

    async def put_job(self, job: Job) -> None:
        await self._execute(
            "INSERT OR REPLACE INTO jobs VALUES(?,?,?)",
            (job.id, job.media_id, job.model_dump_json()),
        )

    async def get_job(self, job_id: str) -> Job | None:
        rows = await self._execute("SELECT body FROM jobs WHERE id=?", (job_id,), True)
        return Job.model_validate_json(rows[0][0]) if rows else None

    async def list_jobs(self, owner_id: str) -> list[Job]:
        rows = await self._execute(
            "SELECT jobs.body FROM jobs JOIN assets ON jobs.asset_id=assets.id WHERE assets.owner=?",
            (owner_id,),
            True,
        )
        return [Job.model_validate_json(row[0]) for row in rows]


class FileObjectStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root) or path == self.root:
            raise ValueError("Object key escapes storage root")
        return path

    async def put(self, key: str, source: Path) -> str:
        target = self._path(key)

        def copy() -> None:
            target.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(dir=target.parent, delete=False) as temp:
                temporary = Path(temp.name)
            try:
                shutil.copyfile(source, temporary)
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)

        await asyncio.to_thread(copy)
        return str(target)

    async def resolve(self, key: str) -> Path:
        return self._path(key)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._path(key).unlink, missing_ok=True)
