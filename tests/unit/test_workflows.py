import asyncio

import pytest

from mediachain.chains.runnable import Branch, Function, Parallel, Retry
from mediachain.core.models import ExecutionContext
from mediachain.workflows.dag import Node, Workflow


async def test_pipe_parallel_branch_trace():
    add = Function(lambda n: n + 1)
    chain = (
        add
        | Parallel(left=add, right=Function(lambda n: n * 2))
        | Function(lambda d: sum(d.values()))
    )
    context = ExecutionContext()
    assert await chain.ainvoke(2, context) == 10
    assert len(context.traces) == 4
    assert await Branch(lambda n: n > 0, add, Function(lambda n: 0)).ainvoke(-1) == 0


async def test_dag_fan_in_and_validation():
    workflow = Workflow(
        [
            Node("a", Function(lambda x: x + 1)),
            Node("b", Function(lambda x: x * 2)),
            Node("join", Function(lambda d: d["a"] + d["b"]), ("a", "b")),
        ]
    )
    assert (await workflow.ainvoke(3))["join"] == 10
    with pytest.raises(ValueError, match="cycle"):
        Workflow([Node("a", Function(str), ("b",)), Node("b", Function(str), ("a",))])
    with pytest.raises(ValueError, match="Unknown"):
        Workflow([Node("a", Function(str), ("missing",))])


async def test_retry_timeout_cancellation_and_sibling_cleanup():
    calls = 0

    async def flaky(x):
        nonlocal calls
        calls += 1
        if calls < 2:
            raise ConnectionError()
        return x

    assert await Retry(Function(flaky), backoff=0).ainvoke(3) == 3
    with pytest.raises(TimeoutError):
        await Retry(Function(lambda _: asyncio.sleep(1)), attempts=1, timeout=0.01).ainvoke(None)
    stopped = asyncio.Event()

    async def slow(x):
        try:
            await asyncio.sleep(10)
        finally:
            stopped.set()

    async def fail(x):
        await asyncio.sleep(0.01)
        raise ValueError("boom")

    with pytest.raises(ExceptionGroup):
        await Parallel(slow=Function(slow), failure=Function(fail)).ainvoke(None)
    assert stopped.is_set()
    task = asyncio.create_task(Retry(Function(slow), timeout=20).ainvoke(None))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
