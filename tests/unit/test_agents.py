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
        return ChatOutput(content=json.dumps(next(self.actions)), token_usage=5)


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
