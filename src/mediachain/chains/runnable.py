"""Composable asynchronous operations with synchronous convenience execution."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from typing import Any

from mediachain.core.models import ExecutionContext
from mediachain.observability.tracing import span


class Runnable:
    async def ainvoke(self, value: Any, context: ExecutionContext | None = None) -> Any:
        raise NotImplementedError

    def __or__(self, other: Runnable) -> Runnable:
        return Sequence(self, other)

    def invoke(self, value: Any) -> Any:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.ainvoke(value))
        raise RuntimeError("Use ainvoke inside an event loop")


class Function(Runnable):
    """Wrap a trusted function; synchronous work is moved off the event loop."""

    def __init__(self, function: Callable[..., Any], name: str | None = None):
        self.function, self.name = function, name or function.__name__

    async def ainvoke(self, value: Any, context: ExecutionContext | None = None) -> Any:
        ctx = context or ExecutionContext()
        with span(ctx, self.name):
            if inspect.iscoroutinefunction(self.function):
                return await self.function(value)
            result = await asyncio.to_thread(self.function, value)
            return await result if inspect.isawaitable(result) else result


class Sequence(Runnable):
    def __init__(self, *steps: Runnable):
        self.steps = steps

    async def ainvoke(self, value: Any, context: ExecutionContext | None = None) -> Any:
        ctx = context or ExecutionContext()
        for step in self.steps:
            value = await step.ainvoke(value, ctx)
        return value


class Parallel(Runnable):
    def __init__(self, **branches: Runnable):
        self.branches = branches

    async def ainvoke(self, value: Any, context: ExecutionContext | None = None) -> dict[str, Any]:
        ctx = context or ExecutionContext()
        async with asyncio.TaskGroup() as group:
            tasks = {
                name: group.create_task(branch.ainvoke(value, ctx))
                for name, branch in self.branches.items()
            }
        return {name: task.result() for name, task in tasks.items()}


class Branch(Runnable):
    def __init__(self, predicate: Callable[[Any], bool], yes: Runnable, no: Runnable):
        self.predicate, self.yes, self.no = predicate, yes, no

    async def ainvoke(self, value: Any, context: ExecutionContext | None = None) -> Any:
        return await (self.yes if self.predicate(value) else self.no).ainvoke(value, context)


class Retry(Runnable):
    def __init__(
        self,
        child: Runnable,
        attempts: int = 3,
        backoff: float = 0.25,
        timeout: float = 60,
        retry_on: tuple[type[Exception], ...] = (TimeoutError, ConnectionError),
    ):
        if attempts < 1 or backoff < 0 or timeout <= 0:
            raise ValueError("Invalid retry policy")
        self.child, self.attempts, self.backoff, self.timeout = child, attempts, backoff, timeout
        self.retry_on = retry_on

    async def ainvoke(self, value: Any, context: ExecutionContext | None = None) -> Any:
        for attempt in range(self.attempts):
            try:
                async with asyncio.timeout(self.timeout):
                    return await self.child.ainvoke(value, context)
            except self.retry_on:
                if attempt + 1 == self.attempts:
                    raise
                await asyncio.sleep(self.backoff * 2**attempt)
        raise AssertionError("Unreachable")
