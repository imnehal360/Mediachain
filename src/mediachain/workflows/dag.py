"""Validated DAG executor. Each node receives named dependency outputs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from mediachain.chains.runnable import Runnable
from mediachain.core.models import ExecutionContext


@dataclass(frozen=True)
class Node:
    name: str
    runnable: Runnable
    dependencies: tuple[str, ...] = field(default_factory=tuple)


class Workflow(Runnable):
    def __init__(self, nodes: list[Node], concurrency: int = 4):
        if concurrency <= 0:
            raise ValueError("concurrency must be positive")
        self.nodes = {n.name: n for n in nodes}
        if len(self.nodes) != len(nodes):
            raise ValueError("Duplicate workflow node names")
        self.concurrency = concurrency
        self.order: list[str] = []
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(name: str) -> None:
            if name not in self.nodes:
                raise ValueError(f"Unknown workflow dependency: {name}")
            if name in visiting:
                raise ValueError("Workflow contains a cycle")
            if name in visited:
                return
            visiting.add(name)
            for dependency in self.nodes[name].dependencies:
                visit(dependency)
            visiting.remove(name)
            visited.add(name)
            self.order.append(name)

        for node in nodes:
            visit(node.name)

    async def ainvoke(self, value: Any, context: ExecutionContext | None = None) -> dict[str, Any]:
        ctx = context or ExecutionContext()
        semaphore = asyncio.Semaphore(self.concurrency)
        tasks: dict[str, asyncio.Task[Any]] = {}

        async def run(node: Node) -> Any:
            inputs = (
                {name: await tasks[name] for name in node.dependencies}
                if node.dependencies
                else value
            )
            async with semaphore:
                return await node.runnable.ainvoke(inputs, ctx)

        async with asyncio.TaskGroup() as group:
            for name in self.order:
                tasks[name] = group.create_task(run(self.nodes[name]))
        return {name: task.result() for name, task in tasks.items()}
