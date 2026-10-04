"""Content-free structured timing records; never log provider payloads."""

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager

from mediachain.core.models import ExecutionContext, TraceEvent

logger = logging.getLogger("mediachain")


@contextmanager
def span(context: ExecutionContext, name: str) -> Iterator[None]:
    started = time.perf_counter()
    status = "ok"
    try:
        yield
    except BaseException:
        status = "error"
        raise
    finally:
        event = TraceEvent(
            name=name, duration_ms=(time.perf_counter() - started) * 1000, status=status
        )
        context.traces.append(event)
        logger.info("mediachain.span", extra={"run_id": context.run_id, **event.model_dump()})
