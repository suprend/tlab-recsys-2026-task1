"""UTC intervals and strict-past replay primitives shared by experiments.

These functions do not choose a prediction target, impute observation before
the source starts, or order simultaneous events. Naive datetimes are rejected:
callers must explicitly attach UTC to the dataset's documented UTC timestamps.
"""

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TypeVar

UTC = timezone.utc
T = TypeVar('T')


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError('A datetime is required')
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('Timestamp must be timezone-aware; source timestamps are UTC')
    return value.astimezone(UTC)


def _positive_duration(value: timedelta) -> None:
    if not isinstance(value, timedelta):
        raise TypeError('Duration must be a timedelta')
    if value <= timedelta(0):
        raise ValueError('Duration must be positive')


@dataclass(frozen=True)
class TimeInterval:
    """An explicitly bounded interval; endpoints are normalized to UTC."""

    start: datetime
    end: datetime
    include_start: bool
    include_end: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, 'start', _utc(self.start))
        object.__setattr__(self, 'end', _utc(self.end))
        if self.end <= self.start:
            raise ValueError('Interval end must follow its start')
        if type(self.include_start) is not bool or type(self.include_end) is not bool:
            raise TypeError('Endpoint policies must be explicit booleans')

    def contains(self, timestamp: datetime) -> bool:
        value = _utc(timestamp)
        lower = value >= self.start if self.include_start else value > self.start
        upper = value <= self.end if self.include_end else value < self.end
        return lower and upper


def history_window(anchor: datetime, lookback: timedelta) -> TimeInterval:
    """Return [anchor-lookback, anchor), excluding all peers at the anchor."""
    _positive_duration(lookback)
    anchor = _utc(anchor)
    return TimeInterval(anchor - lookback, anchor, True, False)


def closed_utc_days(anchor: datetime, days: int) -> TimeInterval:
    """Return completed UTC days; this is different from a rolling window."""
    if type(days) is not int or days <= 0:
        raise ValueError('days must be a positive integer')
    midnight = _utc(anchor).replace(hour=0, minute=0, second=0, microsecond=0)
    return TimeInterval(midnight - timedelta(days=days), midnight, True, False)


def target_window(
    anchor: datetime,
    horizon: timedelta,
    *,
    include_anchor: bool,
    include_end: bool,
) -> TimeInterval:
    """Define relevance explicitly; the project has not fixed these policies."""
    _positive_duration(horizon)
    anchor = _utc(anchor)
    return TimeInterval(anchor, anchor + horizon, include_anchor, include_end)


def label_is_mature(
    target: TimeInterval,
    *,
    available_before: datetime,
    availability_delay: timedelta = timedelta(0),
) -> bool:
    """Can the full target be observed from events available strictly before c?

    A right-open target ending at c is mature. A right-closed target needs an
    availability cutoff strictly after its endpoint. Delay is an explicit
    assumption about availability, not a delay estimated from future outcomes.
    """
    if not isinstance(availability_delay, timedelta):
        raise TypeError('availability_delay must be a timedelta')
    if availability_delay < timedelta(0):
        raise ValueError('availability_delay must be nonnegative')
    cutoff = _utc(available_before) - availability_delay
    return target.end < cutoff if target.include_end else target.end <= cutoff


@dataclass(frozen=True)
class SourceCoverage:
    requested_seconds: float
    observed_seconds: float

    @property
    def fraction(self) -> float:
        return self.observed_seconds / self.requested_seconds

    @property
    def complete(self) -> bool:
        return self.observed_seconds == self.requested_seconds


def source_coverage(
    window: TimeInterval, *, source_start: datetime, source_end: datetime
) -> SourceCoverage:
    """Time overlap with a source [S,E), not user exposure or account age."""
    start, end = _utc(source_start), _utc(source_end)
    if end <= start:
        raise ValueError('Source end must follow source start')
    observed = max(timedelta(0), min(window.end, end) - max(window.start, start))
    return SourceCoverage(
        requested_seconds=(window.end - window.start).total_seconds(),
        observed_seconds=observed.total_seconds(),
    )


def observed_history_age(
    anchor: datetime, first_observed_at: datetime | None
) -> timedelta | None:
    """Age of an observation strictly before anchor, never registration age.

    No past observation (including a tied or future first observation) returns
    None. Appending future data therefore cannot manufacture a past age.
    """
    anchor = _utc(anchor)
    if first_observed_at is None:
        return None
    first = _utc(first_observed_at)
    return anchor - first if first < anchor else None


def timestamp_batches(
    events: Iterable[T], *, timestamp: Callable[[T], datetime]
) -> Iterator[tuple[datetime, tuple[T, ...]]]:
    """Group an ordered stream globally by time, without ordering its peers.

    Consumers must read features for the whole batch before applying any of
    its events to state. The function does not sort; descending input raises.
    Memory is bounded by the largest timestamp group, not the whole stream.
    """
    current: datetime | None = None
    batch: list[T] = []
    for event in events:
        value = _utc(timestamp(event))
        if current is not None and value < current:
            raise ValueError('Events must be ordered by timestamp')
        if current is not None and value != current:
            yield current, tuple(batch)
            batch = []
        current = value
        batch.append(event)
    if current is not None:
        yield current, tuple(batch)
