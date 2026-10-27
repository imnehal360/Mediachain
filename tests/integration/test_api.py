import asyncio
import json
from pathlib import Path

import httpx
import pytest

from mediachain import MediaChain
from mediachain.api.app import create_app
from mediachain.core.models import ChatOutput
from mediachain.loaders.youtube import DownloadedMedia
from mediachain.runtime.jobs import LocalJobQueue


async def test_api_auth_ownership_jobs_query_delete(tmp_path):
    chain = MediaChain(data_dir=tmp_path)
    queue = LocalJobQueue(chain)
    app = create_app(
        chain, api_keys={"alice-key": "alice", "bob-key": "bob"}, queue=queue, max_upload_bytes=100
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.post("/api/v1/query", json={"question": "hello"})).status_code == 401
        client.headers["Authorization"] = "Bearer alice-key"
        upload = await client.post(
            "/api/v1/media",
            files={"file": ("note.txt", b"Artificial intelligence is useful.", "text/plain")},
        )
        assert upload.status_code == 201, upload.text
        asset_id = upload.json()["id"]
        listing = await client.get("/api/v1/media?limit=1&offset=0")
        assert listing.headers["x-total-count"] == "1"
        assert listing.headers["x-content-type-options"] == "nosniff"
        assert listing.headers["x-frame-options"] == "DENY"
        assert listing.headers["x-request-id"]
        job = await client.post(f"/api/v1/media/{asset_id}/process")
        assert job.status_code == 202
        job_id = job.json()["id"]
        for _ in range(100):
            status = await client.get(f"/api/v1/jobs/{job_id}")
            if status.json()["status"] in ("completed", "failed"):
                break
            await asyncio.sleep(0.01)
        assert status.json()["status"] == "completed"
        response = await client.post(
            "/api/v1/query", json={"question": "artificial intelligence", "media_ids": [asset_id]}
        )
        assert response.json()["sources"][0]["media_id"] == asset_id
        summary = await client.post(
            "/api/v1/summarize", json={"media_ids": [asset_id], "focus": "artificial intelligence"}
        )
        assert summary.status_code == 200
        assert summary.json()["sources"][0]["media_id"] == asset_id
        assert (await client.get("/health")).json() == {"status": "ok"}
        assert (await client.get("/ready")).json() == {"status": "ready"}
        client.headers["Authorization"] = "Bearer bob-key"
        for endpoint in (f"/api/v1/media/{asset_id}", f"/api/v1/jobs/{job_id}"):
            assert (await client.get(endpoint)).status_code == 404
        assert (await client.delete(f"/api/v1/media/{asset_id}")).status_code == 404
        assert (
            await client.post("/api/v1/query", json={"question": "hello", "media_ids": [asset_id]})
        ).status_code == 404
        assert not (
            await client.post("/api/v1/query", json={"question": "artificial intelligence"})
        ).json()["sources"]
        client.headers["Authorization"] = "Bearer alice-key"
        assert (
            await client.post("/api/v1/media", files={"file": ("large.txt", b"a" * 101)})
        ).status_code == 413
        assert (
            await client.post("/api/v1/media", files={"file": ("bad.exe", b"abc")})
        ).status_code == 415
        assert (await client.delete(f"/api/v1/media/{asset_id}")).status_code == 204
        assert (await client.get(f"/api/v1/media/{asset_id}")).status_code == 404
    await queue.close()


def test_auth_required(tmp_path):
    with pytest.raises(ValueError):
        create_app(MediaChain(data_dir=tmp_path))


async def test_agent_query_uses_tools_and_returns_observed_citations(tmp_path):
    class AgentModel:
        model_id, model_version = "agent-fixture", "1"
        calls = 0

        async def generate(self, messages):
            self.calls += 1
            if self.calls == 1:
                return ChatOutput(
                    content='{"tool":"search_text","arguments":{"query":"artificial intelligence"}}',
                    token_usage=5,
                )
            return ChatOutput(
                content=json.dumps(
                    {
                        "answer": "The note says artificial intelligence is useful.",
                        "citation_ids": ["1"],
                        "insufficient_evidence": False,
                    }
                ),
                token_usage=7,
            )

    chain = MediaChain(data_dir=tmp_path, llm=AgentModel())
    queue = LocalJobQueue(chain)
    app = create_app(chain, development_owner="local-user", queue=queue)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        upload = await client.post(
            "/api/v1/media",
            files={"file": ("note.txt", b"Artificial intelligence is useful.", "text/plain")},
        )
        asset_id = upload.json()["id"]
        job = await client.post(f"/api/v1/media/{asset_id}/process")
        for _ in range(100):
            status = await client.get(f"/api/v1/jobs/{job.json()['id']}")
            if status.json()["status"] in ("completed", "failed"):
                break
            await asyncio.sleep(0.01)
        response = await client.post(
            "/api/v1/agent/query",
            json={"question": "What does the note say?", "media_ids": [asset_id]},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["answer"] == "The note says artificial intelligence is useful."
        assert payload["sources"][0]["media_id"] == asset_id
        assert payload["token_usage"] == 12
        assert payload["metadata"]["mode"] == "agentic"
        assert payload["metadata"]["tool_calls"][0]["tool"] == "search_text"

        class FallbackModel:
            model_id, model_version = "fallback-fixture", "1"
            calls = 0

            async def generate(self, messages):
                self.calls += 1
                if self.calls == 1:
                    return ChatOutput(
                        content='{"tool":"search_text","arguments":{"query":"useful"}}'
                    )
                if self.calls == 2:
                    return ChatOutput(
                        content=json.dumps(
                            {
                                "answer": "An uncited draft",
                                "citation_ids": [],
                                "insufficient_evidence": False,
                            }
                        )
                    )
                request = json.loads(messages[-1].content)
                citation_id = request["evidence"][0]["citation_id"]
                return ChatOutput(
                    content=json.dumps(
                        {
                            "answer": "The validated fallback answer.",
                            "citation_ids": [citation_id],
                            "insufficient_evidence": False,
                        }
                    )
                )

        chain.rag.llm = FallbackModel()
        fallback = await client.post(
            "/api/v1/agent/query",
            json={"question": "What is useful?", "media_ids": [asset_id]},
        )
        assert fallback.status_code == 200, fallback.text
        assert fallback.json()["answer"] == "The validated fallback answer."
        assert fallback.json()["metadata"]["grounding_fallback"] is True
        assert fallback.json()["metadata"]["tool_calls"][0]["tool"] == "search_text"
    await queue.close()


async def test_local_no_auth_mode_accepts_only_loopback_clients(tmp_path):
    chain = MediaChain(data_dir=tmp_path)
    app = create_app(
        chain,
        development_owner="local-user",
        development_local_only=True,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 12345)),
        base_url="http://localhost",
    ) as client:
        response = await client.get("/api/v1/config")
        assert response.status_code == 200
        assert response.json()["owner"] == "local-user"
        assert response.json()["authentication_required"] is False
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("192.168.1.20", 12345)),
        base_url="http://localhost",
    ) as client:
        response = await client.get("/api/v1/config")
        assert response.status_code == 403
        assert response.json()["error"]["message"] == "Local access only"


async def test_youtube_url_upload_uses_bounded_downloader(tmp_path):
    received = {}

    async def fake_download(url, destination, max_bytes, max_duration):
        received.update(
            url=url,
            destination=destination,
            max_bytes=max_bytes,
            max_duration=max_duration,
        )
        path = destination / "podcast.mp4"
        path.write_bytes(b"downloaded-video")
        return DownloadedMedia(
            path=path,
            title="Local Podcast",
            webpage_url=url,
            duration=321,
        )

    chain = MediaChain(data_dir=tmp_path / "data")
    app = create_app(
        chain,
        development_owner="local-user",
        youtube_download=fake_download,
        max_remote_bytes=123456,
        max_remote_duration_seconds=7200,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/media/url",
            json={"url": "https://youtu.be/abcdefghijk"},
        )
        assert response.status_code == 201, response.text
        asset = response.json()
        assert asset["owner_id"] == "local-user"
        assert asset["media_type"] == "video"
        assert asset["duration"] == 321
        assert asset["metadata"]["original_name"] == "Local Podcast.mp4"
        assert asset["metadata"]["remote_provider"] == "youtube"
        assert Path(received["destination"]).name.startswith("mediachain-youtube-")
        assert received["max_bytes"] == 123456
        assert received["max_duration"] == 7200


async def test_streaming_body_limit_and_validation_privacy(tmp_path):
    chain = MediaChain(data_dir=tmp_path)
    app = create_app(chain, api_keys={"key": "owner"}, max_upload_bytes=100)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer key"},
    ) as client:
        response = await client.post("/api/v1/query", json={"question": "x" * 70000})
        assert response.status_code == 413
        response = await client.post(
            "/api/v1/query", json={"question": "", "secret": "never echo this"}
        )
        assert response.status_code == 422
        assert "never echo this" not in response.text


async def test_api_rate_limit(tmp_path):
    chain = MediaChain(data_dir=tmp_path)
    app = create_app(chain, api_keys={"key": "owner"}, rate_limit_per_minute=1)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer key"},
    ) as client:
        assert (await client.get("/api/v1/config")).status_code == 200
        response = await client.get("/api/v1/config")
        assert response.status_code == 429
        assert response.json()["error"]["message"] == "Rate limit exceeded"
