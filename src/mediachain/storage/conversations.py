"""Owner-scoped SQLite conversations; successful turns are committed atomically."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from pathlib import Path
from typing import Any
from uuid import uuid4


class ConversationStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute(
                "CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY, owner TEXT NOT NULL, updated REAL NOT NULL, body TEXT NOT NULL)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS conversations_owner ON conversations(owner, updated)"
            )

    async def list_chats(self, owner: str) -> list[dict[str, Any]]:
        def read() -> list[dict[str, Any]]:
            with sqlite3.connect(self.path) as db:
                rows = db.execute(
                    "SELECT body FROM conversations WHERE owner=? ORDER BY updated DESC LIMIT 100",
                    (owner,),
                ).fetchall()
                return [
                    {k: v for k, v in json.loads(row[0]).items() if k != "messages"} for row in rows
                ]

        return await asyncio.to_thread(read)

    async def get(self, conversation_id: str, owner: str) -> dict[str, Any]:
        def read() -> dict[str, Any]:
            with sqlite3.connect(self.path) as db:
                row = db.execute(
                    "SELECT body FROM conversations WHERE id=? AND owner=?",
                    (conversation_id, owner),
                ).fetchone()
                if row is None:
                    raise KeyError("Unknown conversation")
                return json.loads(row[0])

        return await asyncio.to_thread(read)

    async def create(self, owner: str, media_ids: list[str] | None) -> dict[str, Any]:
        chat: dict[str, Any] = {
            "id": uuid4().hex,
            "title": "New chat",
            "media_ids": media_ids,
            "messages": [],
            "updated_at": time.time(),
        }
        await self.save(chat, owner)
        return chat

    async def save(self, chat: dict[str, Any], owner: str) -> None:
        def write() -> None:
            with sqlite3.connect(self.path) as db:
                db.execute(
                    "INSERT INTO conversations VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET updated=excluded.updated, body=excluded.body WHERE conversations.owner=excluded.owner",
                    (chat["id"], owner, chat["updated_at"], json.dumps(chat)),
                )

        await asyncio.to_thread(write)
