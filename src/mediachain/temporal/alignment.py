"""Interval relations never cross original media identities."""

from mediachain.core.models import Document, Event, Interval


def overlaps(left: Interval, right: Interval) -> bool:
    return (
        left.start_time is not None
        and left.end_time is not None
        and right.start_time is not None
        and right.end_time is not None
        and left.start_time <= right.end_time
        and right.start_time <= left.end_time
    )


def align(documents: list[Document]) -> list[tuple[str, str]]:
    """Return cross-modal overlaps, including sampled instants at boundaries."""
    ordered = sorted(
        (d for d in documents if d.start_time is not None),
        key=lambda d: (d.asset_id, d.start_time or 0),
    )
    pairs = []
    for i, left in enumerate(ordered):
        for right in ordered[i + 1 :]:
            if right.asset_id != left.asset_id:
                break
            if (
                left.end_time is not None
                and right.start_time is not None
                and right.start_time > left.end_time
            ):
                break
            if left.modality != right.modality and overlaps(left, right):
                pairs.append((left.id, right.id))
    return pairs


def nearby(events: list[Event], asset_id: str, timestamp: float, radius: float = 5) -> list[Event]:
    if timestamp < 0 or radius < 0:
        raise ValueError("timestamp and radius must be nonnegative")
    window = Interval(start_time=max(0, timestamp - radius), end_time=timestamp + radius)
    return [e for e in events if e.asset_id == asset_id and overlaps(e, window)]
