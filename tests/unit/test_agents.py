import json

import pytest

from mediachain.agents.runtime import Agent, AgentLimits
from mediachain.core.errors import BudgetExceeded, ConfigurationError
from mediachain.core.models import ChatOutput, ExecutionContext
from mediachain.embeddings.local import HashEmbeddings
from mediachain.plugins.registry import PluginRegistry
from mediachain.storage.cache import MemoryCache, cache_key


class Tool:
    name, description = "search_text", "Search text"
    calls = 0

    async def invoke(self, arguments, context):
        self.calls += 1
        return {"evidence": "hello"}


class Model:
    model_id, model_version = "fixture", "1"

    def __init__(self, actions):
        self.actions = iter(actions)

    async def generate(self, messages):
        action = next(self.actions)
        return ChatOutput(
            content=action if isinstance(action, str) else json.dumps(action), token_usage=5
        )


async def test_agent_tools_and_budgets():
    tool = Tool()
    ctx = ExecutionContext()
    result = await Agent(Model([{"tool": "search_text"}, {"answer": "hello"}]), [tool]).run(
        "question", ctx
    )
    assert result == "hello" and tool.calls == 1
    assert any(t.name == "tool.search_text" for t in ctx.traces)
    with pytest.raises(ConfigurationError):
        await Agent(Model([{"tool": "shell"}]), [tool]).run("question")
    with pytest.raises(BudgetExceeded):
        await Agent(Model([{"tool": "search_text"}]), [tool], AgentLimits(max_tool_calls=0)).run(
            "q"
        )
    with pytest.raises(BudgetExceeded):
        await Agent(Model([{"answer": "hello"}]), [], AgentLimits(max_tokens=1)).run("q")


async def test_agent_detailed_run_tracks_tools_and_accepts_fenced_json():
    tool = Tool()
    run = await Agent(
        Model(
            [
                '```json\n{"tool":"search_text","arguments":{"query":"hello"}}\n```',
                {
                    "answer": "Grounded answer",
                    "citation_ids": ["doc-1"],
                    "insufficient_evidence": False,
                },
            ]
        ),
        [tool],
    ).run_detailed("question")
    assert run.answer == "Grounded answer"
    assert run.citation_ids == ["doc-1"]
    assert run.steps[0].tool == "search_text"
    assert run.steps[0].arguments == {"query": "hello"}
    assert run.token_usage == 10


def test_agent_parser_uses_first_complete_json_action():
    action = Agent._parse_action(
        '{"tool":"search_text","arguments":{"query":"hello"}}\n'
        '{"answer":"placeholder","citation_ids":["invented"]}'
    )
    assert action.tool == "search_text"
    assert action.answer is None


async def test_agent_repairs_a_malformed_model_action():
    run = await Agent(
        Model(
            [
                "I found the answer but forgot the required schema.",
                {
                    "answer": "No evidence was available.",
                    "insufficient_evidence": True,
                },
            ]
        ),
        [],
    ).run_detailed("question")
    assert run.answer == "No evidence was available."
    assert run.insufficient_evidence is True


def test_registry():
    registry = PluginRegistry()
    registry.register("embeddings", "local", HashEmbeddings())
    assert registry.get("embeddings", "local").space.dimensions == 256
    with pytest.raises(ConfigurationError):
        registry.register("processor", "bad", object())
    with pytest.raises(ConfigurationError):
        registry.register("embeddings", "new", HashEmbeddings(), api_version="9")


async def test_cache_version_and_expiration():
    cache = MemoryCache()
    first = cache_key("hash", {"interval": 1}, "model", "1")
    assert first != cache_key("hash", {"interval": 1}, "model", "2")
    assert first != cache_key("hash", {"interval": 2}, "model", "1")
    await cache.set(first, "value", ttl=-1)
    assert await cache.get(first) is None
