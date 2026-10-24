"""PostgreSQL JSONB persistence through an injected asyncpg pool."""

from __future__ import annotations

import json
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
                CREATE INDEX IF NOT EXISTS mc_documents_modality ON mc_documents((body->>'modality'));
                CREATE INDEX IF NOT EXISTS mc_documents_source ON mc_documents((body->>'source'));
                CREATE INDEX IF NOT EXISTS mc_documents_metadata ON mc_documents USING GIN((body->'metadata'));
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

    async def list_assets(
        self, owner_id: str, limit: int | None = None, offset: int = 0
    ) -> list[MediaAsset]:
        rows = await self.pool.fetch(
            "SELECT body::text AS body FROM mc_assets WHERE owner=$1 ORDER BY id LIMIT $2 OFFSET $3",
            owner_id,
            limit,
            offset,
        )
        return [MediaAsset.model_validate_json(r["body"]) for r in rows]

    async def count_assets(self, owner_id: str) -> int:
        return int(
            await self.pool.fetchval("SELECT COUNT(*) FROM mc_assets WHERE owner=$1", owner_id)
        )

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
            """
            SELECT body::text AS body FROM mc_documents
            WHERE ($1::text[] IS NULL OR asset_id=ANY($1))
              AND ($2::text[] IS NULL OR body->>'modality'=ANY($2))
              AND ($3::text[] IS NULL OR body->>'source'=ANY($3))
              AND ($4::double precision IS NULL OR (
                    (body->>'start_time') IS NOT NULL
                AND (body->>'end_time') IS NOT NULL
                AND (body->>'start_time')::double precision <= $5
                AND (body->>'end_time')::double precision >= $4
              ))
              AND body->'metadata' @> $6::jsonb
            """,
            filters.media_ids,
            [str(value) for value in filters.modalities] if filters.modalities else None,
            filters.sources,
            filters.start_time,
            filters.end_time,
            json.dumps(filters.metadata),
        )
        return [Document.model_validate_json(row["body"]) for row in rows]

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

    async def healthcheck(self) -> bool:
        return await self.pool.fetchval("SELECT 1") == 1

    async def list_jobs(
        self, owner_id: str, limit: int | None = None, offset: int = 0
    ) -> list[Job]:
        rows = await self.pool.fetch(
            """SELECT j.body::text AS body FROM mc_jobs j JOIN mc_assets a ON j.asset_id=a.id
            WHERE a.owner=$1 ORDER BY j.id LIMIT $2 OFFSET $3""",
            owner_id,
            limit,
            offset,
        )
        return [Job.model_validate_json(row["body"]) for row in rows]

    async def count_jobs(self, owner_id: str) -> int:
        return int(
            await self.pool.fetchval(
                "SELECT COUNT(*) FROM mc_jobs j JOIN mc_assets a ON j.asset_id=a.id WHERE a.owner=$1",
                owner_id,
            )
        )

    async def list_stale_jobs(self, updated_before: float) -> list[Job]:
        rows = await self.pool.fetch(
            """
            SELECT body::text AS body FROM mc_jobs
            WHERE body->>'status'='running'
              AND (body->>'updated_at')::double precision < $1
            """,
            updated_before,
        )
        return [Job.model_validate_json(row["body"]) for row in rows]
