import httpx
import pytest

from mediachain import MediaChain
from mediachain.api.app import create_app


async def test_conversations_persist_sources_context_and_owner(tmp_path, monkeypatch):
    chain = MediaChain(data_dir=tmp_path)
    path = tmp_path / "notes.txt"
    path.write_text("Saturn has rings made of ice and rock.")
    asset = await chain.add(str(path), owner_id="alice")
    original = chain.ask
    questions = []

    async def ask(question, *args, **kwargs):
        questions.append(question)
        return await original(question, *args, **kwargs)

    monkeypatch.setattr(chain, "ask", ask)
    app = create_app(chain, api_keys={"a": "alice", "b": "bob"})
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer a"},
    ) as client:
        chat = (await client.post("/api/v1/conversations", json={"media_ids": [asset.id]})).json()
        url = "/api/v1/conversations/" + chat["id"]
        for question in ("What are Saturn's rings made of?", "Explain that further"):
            response = await client.post(
                url + "/messages", json={"question": question, "media_ids": [asset.id]}
            )
            assert response.status_code == 200, response.text
        saved = response.json()
        assert len(saved["messages"]) == 4
        assert saved["messages"][1]["response"]["sources"][0]["media_id"] == asset.id
        assert "Saturn's rings" in questions[-1]
        assert "Current question: Explain that further" in questions[-1]
        client.headers["Authorization"] = "Bearer b"
        assert (await client.get(url)).status_code == 404
        assert (await client.post(url + "/messages", json={"question": "hello"})).status_code == 404
        assert (await client.get("/api/v1/conversations")).json() == []
    restarted = create_app(MediaChain(data_dir=tmp_path), api_keys={"a": "alice"})
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=restarted),
        base_url="http://test",
        headers={"Authorization": "Bearer a"},
    ) as client:
        assert (await client.get(url)).json() == saved
        assert (await client.get("/api/v1/conversations")).json()[0][
            "title"
        ] == "What are Saturn's rings made of?"


async def test_failed_turn_does_not_erase_history(tmp_path, monkeypatch):
    chain = MediaChain(data_dir=tmp_path)
    app = create_app(chain, api_keys={"a": "alice"})
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer a"},
    ) as client:
        chat = (await client.post("/api/v1/conversations", json={})).json()
        url = "/api/v1/conversations/" + chat["id"]

        async def fail(*args, **kwargs):
            raise TimeoutError("model timed out")

        monkeypatch.setattr(chain, "ask", fail)
        with pytest.raises(TimeoutError):
            await client.post(url + "/messages", json={"question": "hello"})
        assert (await client.get(url)).json()["messages"] == []
