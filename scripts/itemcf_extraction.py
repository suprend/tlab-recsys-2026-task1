"""Bounded ItemCF input extraction; caller authenticates and supervises the source.

The injected zero-argument opener must return a NEW read-only DuckDB connection
to the authenticated typed9 database. Ownership transfers on return: this module
closes it, also on failure. The opener owns cleanup if opening itself fails.
No DuckDB import, source path, SQL identifier, execution grant or CLI lives here.
"""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from scripts.itemcf_projection import LimitExceeded


_FIELDS = ("event_time", "event_type", "product_id", "category_id",
           "category_code", "brand", "price", "user_id", "user_session")
_TYPES = ("TIMESTAMP", "VARCHAR", "BIGINT", "BIGINT", "VARCHAR", "VARCHAR",
          "DECIMAL(12,2)", "BIGINT", "VARCHAR")
_MAX_INT = 2**63 - 1


@dataclass(frozen=True)
class ItemCFQuery:
    query_id: str
    user_id: int
    candidates: tuple[int, ...]


@dataclass(frozen=True)
class SourceContract:
    """Caller-authenticated row descriptor and half-open UTC coverage, not proof."""
    rows: int
    start: datetime
    end: datetime


@dataclass(frozen=True)
class ExtractionLimits:
    """Finite descriptor/Python-work limits, NOT native CPU/RSS/physical IO caps."""
    max_scan_rows: int
    max_members: int
    max_work: int


@dataclass(frozen=True)
class ItemCFSnapshot:
    query_id: str
    user_id: int
    candidates: tuple[int, ...]
    latest21: tuple[int, ...]
    postings: dict[int, tuple[int, ...]]


def _integer(value, name):
    if type(value) is not int or not -2**63 <= value <= _MAX_INT:
        raise ValueError(name + " must be an exact signed BIGINT, not NULL/bool/float")


def _clock(value, name):
    if (type(value) is not datetime or value.utcoffset() != timedelta(0)
            or value.microsecond):
        raise ValueError(name + " must be an aware second-precision UTC datetime")


@contextmanager
def _owned(open_source):
    connection = open_source()
    try:
        yield connection
    except BaseException as primary:
        try:
            connection.close()
        except BaseException as secondary:
            # Cleanup failure must not replace the original budget/SQL/interrupt.
            primary.add_note("Connection close also failed: " + type(secondary).__name__)
        raise
    else:
        connection.close()


def extract_itemcf_snapshot(open_source, queries, *, b, source, limits, check):
    """Return Q/C in input order, H21 and complete exact-key global postings.

    Both history and graph are VIEW-only on [b-7d,b). History filters NULL
    products before distinct/cap21; graph includes every non-NULL source user.
    Ties: latest event DESC, sha256(UTF8 canonical signed decimal item) ASC,
    exact item ASC. All required keys exist, including known-empty tuples.

    2*source.rows is a conservative TWO-full-pass descriptor, not a physical
    scan measurement or source authentication. max_work additionally charges
    bounded Python visits; max_members counts DISTINCT global item/user pairs.
    Limit failures return nothing. Native SQL still needs caller supervision:
    check() runs around calls and cannot interrupt a blocked execute/fetch.
    """
    if type(source) is not SourceContract or type(limits) is not ExtractionLimits:
        raise ValueError("Explicit SourceContract and ExtractionLimits required")
    _integer(source.rows, "source.rows")
    if source.rows < 0:
        raise ValueError("source.rows must be nonnegative")
    for name in ("max_scan_rows", "max_members", "max_work"):
        value = getattr(limits, name)
        _integer(value, name)
        if value < 0 or name == "max_members" and value == _MAX_INT:
            raise ValueError(name + " must allow a finite nonnegative limit+1")
    _clock(b, "b")
    _clock(source.start, "source.start")
    _clock(source.end, "source.end")
    b = b.astimezone(timezone.utc)
    if b.hour or b.minute or b.second:
        raise ValueError("b must be a daily UTC midnight anchor")
    start = b - timedelta(days=7)
    if not source.start <= start < b <= source.end:
        raise ValueError("Authenticated source coverage must contain [b-7d,b)")
    work = 2 * source.rows
    if work > limits.max_scan_rows or work > limits.max_work:
        raise LimitExceeded("Two-full-pass source descriptor exceeds scan/work limit")
    # All descriptor and payload refusal happens BEFORE check or source opening.
    if type(queries) is not tuple or len(queries) > 100:
        raise ValueError("queries must be a tuple of at most 100 ItemCFQuery values")
    seen_queries = set()
    users = set()
    validation_work = 0
    for query in queries:
        if (type(query) is not ItemCFQuery or type(query.query_id) is not str
                or not 1 <= len(query.query_id) <= 256 or "\x00" in query.query_id
                or query.query_id in seen_queries):
            raise ValueError("Bounded distinct string query_id required")
        seen_queries.add(query.query_id)
        _integer(query.user_id, "query.user_id")
        users.add(query.user_id)
        if type(query.candidates) is not tuple or len(query.candidates) > 220:
            raise ValueError("candidates must be a tuple of at most 220 exact IDs")
        seen_candidates = set()
        for item in query.candidates:
            _integer(item, "candidate")
            if item in seen_candidates:
                raise ValueError("Candidate IDs must be distinct within each query")
            seen_candidates.add(item)
        validation_work += 1 + len(query.candidates)
    work += validation_work
    if work > limits.max_work:
        raise LimitExceeded("max_work exceeded during preflight")
    if not callable(open_source) or not callable(check):
        raise ValueError("Callable guarded read-only opener and check required")

    def charge(amount=0):
        nonlocal work
        work += amount
        if work > limits.max_work:
            raise LimitExceeded("max_work exceeded; no partial extraction")
        check()

    def execute(connection, sql, parameters=None):
        charge()
        result = connection.execute(sql, [] if parameters is None else parameters)
        charge()
        return result

    def rows(result, size=1024):
        while True:
            charge()
            batch = result.fetchmany(size)
            charge(len(batch))
            if not batch:
                return
            yield from batch

    if not queries:
        charge()
        return ()
    histories = {user: [] for user in users}
    begin, end = start.replace(tzinfo=None), b.replace(tzinfo=None)
    charge()
    with _owned(open_source) as connection:
        # Schema is verified; content/row-count/precision completeness is the
        # authenticated caller contract, not inferred from this metadata query.
        schema = list(rows(execute(connection, "DESCRIBE events"), 16))
        if [tuple(row[:2]) for row in schema] != list(zip(_FIELDS, _TYPES)):
            raise ValueError("Exact ordered typed9 events schema required")
        placeholders = ",".join("?" for _ in users)
        history_sql = """
            WITH recent AS (
                SELECT user_id, product_id, max(event_time) AS last_time
                FROM events
                WHERE event_type = 'view'
                  AND user_id IS NOT NULL AND product_id IS NOT NULL
                  AND event_time >= ? AND event_time < ?
                  AND user_id IN (""" + placeholders + """)
                GROUP BY user_id, product_id
            ), ranked AS (
                SELECT user_id, product_id, last_time,
                       row_number() OVER (
                           PARTITION BY user_id ORDER BY last_time DESC,
                           sha256(CAST(product_id AS VARCHAR)) ASC, product_id ASC
                       ) AS position
                FROM recent
            )
            SELECT user_id, product_id, last_time FROM ranked
            WHERE position <= 21 ORDER BY user_id, position
        """
        result = execute(connection, history_sql, [begin, end, *sorted(users)])
        for user, item, last_time in rows(result):
            _integer(user, "history user")
            _integer(item, "history item")
            if (user not in histories or len(histories[user]) >= 21
                    or item in histories[user] or type(last_time) is not datetime
                    or last_time.tzinfo is not None or last_time.microsecond
                    or not begin <= last_time < end):
                raise ValueError("Invalid/incomplete typed history result")
            histories[user].append(item)
        required = set()
        for query in queries:
            charge(1 + len(query.candidates) + len(histories[query.user_id]))
            required.update(query.candidates)
            required.update(histories[query.user_id])
        # Values are shared immutable tuples across query maps, never H21-capped.
        vectors = {item: [] for item in required}
        if required:
            placeholders = ",".join("?" for _ in required)
            posting_sql = """
                SELECT product_id, user_id FROM events
                WHERE event_type = 'view'
                  AND product_id IS NOT NULL AND user_id IS NOT NULL
                  AND event_time >= ? AND event_time < ?
                  AND product_id IN (""" + placeholders + """)
                GROUP BY product_id, user_id
                ORDER BY product_id, user_id LIMIT ?
            """
            result = execute(connection, posting_sql,
                             [begin, end, *sorted(required), limits.max_members + 1])
            count = 0
            previous = None
            for item, user in rows(result, min(1024, limits.max_members + 1)):
                count += 1
                if count > limits.max_members:
                    raise LimitExceeded("max_members exceeded; postings are not truncated")
                _integer(item, "posting item")
                _integer(user, "posting user")
                pair = (item, user)
                if item not in vectors or previous is not None and pair <= previous:
                    raise ValueError("Postings must be sorted distinct exact item/user pairs")
                previous = pair
                vectors[item].append(user)
        frozen = {}
        for item, members in vectors.items():
            charge(1 + len(members))
            frozen[item] = tuple(members)
        snapshots = []
        for query in queries:
            history = tuple(histories[query.user_id])
            keys = set(query.candidates) | set(history)
            charge(1 + len(keys))
            snapshots.append(ItemCFSnapshot(query.query_id, query.user_id,
                                           query.candidates, history,
                                           {item: frozen[item] for item in sorted(keys)}))
        charge()
    # Includes the successful close in the original cooperative lifetime.
    charge()
    return tuple(snapshots)
