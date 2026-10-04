"""PostgreSQL JSONB persistence through an injected asyncpg pool."""

from __future__ import annotations

from typing import Any

from mediachain.core.models import Document, Job, MediaAsset, RetrievalFilter


class PostgresStore:
    def __init__(self, pool: Any):
        self.pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> PostgresStore:
        import asyncpg

        store = cls(await asyncpg.create_pool(dsn))
        async with store.pool.acquire() as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS mc_assets(id TEXT PRIMARY KEY, owner TEXT NOT NULL, body JSONB NOT NULL);
                CREATE TABLE IF NOT EXISTS mc_documents(id TEXT PRIMARY KEY, asset_id TEXT NOT NULL REFERENCES mc_assets(id) ON DELETE CASCADE, body JSONB NOT NULL);
                CREATE INDEX IF NOT EXISTS mc_documents_asset ON mc_documents(asset_id);
                CREATE TABLE IF NOT EXISTS mc_jobs(id TEXT PRIMARY KEY, asset_id TEXT NOT NULL REFERENCES mc_assets(id) ON DELETE CASCADE, body JSONB NOT NULL);
            """)
        return store

    async def put_asset(self, asset: MediaAsset) -> None:
        await self.pool.execute(
            "INSERT INTO mc_assets VALUES($1,$2,$3::jsonb) ON CONFLICT(id) DO UPDATE SET body=EXCLUDED.body, owner=EXCLUDED.owner",
            asset.id,
            asset.owner_id,
            asset.model_dump_json(),
        )

    async def get_asset(self, asset_id: str) -> MediaAsset | None:
        value = await self.pool.fetchval("SELECT body::text FROM mc_assets WHERE id=$1", asset_id)
        return MediaAsset.model_validate_json(value) if value else None

    async def list_assets(self, owner_id: str) -> list[MediaAsset]:
        rows = await self.pool.fetch(
            "SELECT body::text AS body FROM mc_assets WHERE owner=$1 ORDER BY id", owner_id
        )
        return [MediaAsset.model_validate_json(r["body"]) for r in rows]

    async def delete_asset(self, asset_id: str) -> None:
        await self.pool.execute("DELETE FROM mc_assets WHERE id=$1", asset_id)

    async def replace_documents(self, asset_id: str, documents: list[Document]) -> None:
        if any(d.asset_id != asset_id for d in documents):
            raise ValueError("Document belongs to another asset")
        async with self.pool.acquire() as db, db.transaction():
            await db.execute("DELETE FROM mc_documents WHERE asset_id=$1", asset_id)
            await db.executemany(
                "INSERT INTO mc_documents VALUES($1,$2,$3::jsonb)",
                [(d.id, d.asset_id, d.model_dump_json()) for d in documents],
            )

    async def list_documents(self, filters: RetrievalFilter) -> list[Document]:
        rows = await self.pool.fetch(
            "SELECT body::text AS body FROM mc_documents WHERE ($1::text[] IS NULL OR asset_id=ANY($1))",
            filters.media_ids,
        )
        return [d for r in rows if filters.matches(d := Document.model_validate_json(r["body"]))]

    async def delete_documents(self, asset_id: str) -> None:
        await self.pool.execute("DELETE FROM mc_documents WHERE asset_id=$1", asset_id)

    async def put_job(self, job: Job) -> None:
        await self.pool.execute(
            "INSERT INTO mc_jobs VALUES($1,$2,$3::jsonb) ON CONFLICT(id) DO UPDATE SET body=EXCLUDED.body",
            job.id,
            job.media_id,
            job.model_dump_json(),
        )

    async def get_job(self, job_id: str) -> Job | None:
        value = await self.pool.fetchval("SELECT body::text FROM mc_jobs WHERE id=$1", job_id)
        return Job.model_validate_json(value) if value else None

    async def close(self) -> None:
        await self.pool.close()

    async def list_jobs(self, owner_id: str) -> list[Job]:
        rows = await self.pool.fetch(
            "SELECT j.body::text AS body FROM mc_jobs j JOIN mc_assets a ON j.asset_id=a.id WHERE a.owner=$1",
            owner_id,
        )
        return [Job.model_validate_json(row["body"]) for row in rows]
