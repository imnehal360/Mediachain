import asyncio

import httpx
import pytest

from mediachain import MediaChain
from mediachain.api.app import create_app
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
