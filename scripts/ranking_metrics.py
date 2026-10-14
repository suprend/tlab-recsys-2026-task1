"""Binary set-target ranking metrics, independent of retrieval and model code.

Callers supply an already ordered, deterministic list of unique item IDs. Score
ties must be resolved by the caller's declared policy; this module never sorts,
inserts missing positives, or infers target maturity. Full targets determine
Recall, AP and ideal DCG, including targets outside candidates/catalog.
"""

from collections import defaultdict
from collections.abc import Hashable, Iterable, Sequence
from dataclasses import dataclass
import math
import random


METRICS = ("recall", "ndcg", "average_precision", "reciprocal_rank")
ESTIMANDS = (
    "conditional_macro_query", "all_query_zero",
    "conditional_user_macro", "all_user_macro_zero",
)


@dataclass(frozen=True)
class QueryRanking:
    query_id: Hashable
    user_id: Hashable
    ranked_items: Sequence[Hashable]
    targets: Iterable[Hashable] | None
    mature: bool = True

    def __post_init__(self):
        hash(self.query_id)
        hash(self.user_id)
        if not isinstance(self.mature, bool):
            raise ValueError("mature must be a bool")
        if (not isinstance(self.ranked_items, Sequence)
                or isinstance(self.ranked_items, (str, bytes))):
            raise ValueError("ranked_items must be an ordered sequence of item IDs")
        ranked = tuple(self.ranked_items)
        if len(set(ranked)) != len(ranked):
            raise ValueError("duplicate ranked items are not allowed")
        if self.mature and self.targets is None:
            raise ValueError("mature queries require the full target set, even if empty")
        if not self.mature and self.targets is not None:
            raise ValueError("censored queries must use targets=None, not partial labels")
        if isinstance(self.targets, (str, bytes)):
            raise ValueError("targets must contain item IDs, not a string")
        object.__setattr__(self, "ranked_items", ranked)
        if self.targets is not None:
            object.__setattr__(self, "targets", frozenset(self.targets))


@dataclass(frozen=True)
class MetricValues:
    recall: float | None
    ndcg: float | None
    average_precision: float | None
    reciprocal_rank: float | None


@dataclass(frozen=True)
class QueryScore:
    query_id: Hashable
    user_id: Hashable
    mature: bool
    target_count: int | None
    returned_count: int
    hits: int
    metrics: MetricValues


@dataclass(frozen=True)
class Evaluation:
    k: int
    query_count: int
    mature_query_count: int
    censored_query_count: int
    nonempty_query_count: int
    mature_user_count: int
    positive_user_count: int
    nonempty_fraction: float | None
    conditional_macro_query: MetricValues
    all_query_zero: MetricValues
    conditional_user_macro: MetricValues
    all_user_macro_zero: MetricValues


@dataclass(frozen=True)
class BootstrapDifference:
    """Left minus right; undefined draws stay None and are never redrawn.

    The percentile interval uses only defined draws (linear interpolation).
    Counts expose its effective size; no defined draws means no interval.
    User clustering covers user dependence, not common temporal shocks.
    """

    metric: str
    estimand: str
    seed: int
    replicates: int
    user_count: int
    estimate: float | None
    samples: tuple[float | None, ...]
    undefined_draws: int
    interval_95: tuple[float, float] | None


def _positive_integer(value, name, maximum=None):
    if type(value) is not int or value < 1 or (maximum is not None and value > maximum):
        raise ValueError(f"{name} must be a positive integer"
                         + (f" <= {maximum}" if maximum is not None else ""))


def score_query(query: QueryRanking, k: int) -> QueryScore:
    """For empty mature Y, all metrics are undefined; censoring is separate."""
    _positive_integer(k, "k")
    count = len(query.targets) if query.mature else None
    returned = query.ranked_items[:k]
    if not count:
        return QueryScore(query.query_id, query.user_id, query.mature, count,
                          len(returned), 0, MetricValues(None, None, None, None))
    hits = 0
    dcg = ap = rr = 0.0
    for rank, item in enumerate(returned, 1):
        if item in query.targets:
            hits += 1
            dcg += 1 / math.log2(rank + 1)
            ap += hits / rank
            if rr == 0:
                rr = 1 / rank
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(k, count) + 1))
    return QueryScore(query.query_id, query.user_id, True, count, len(returned), hits,
                      MetricValues(hits / count, dcg / ideal, ap / count, rr))


def _score_all(rankings, k):
    _positive_integer(k, "k")
    scores = [score_query(query, k) for query in rankings]
    if len({row.query_id for row in scores}) != len(scores):
        raise ValueError("query IDs must be unique")
    return scores


def _user_totals(scores, metric, conditional):
    # All mature users remain in the cluster population, including empty-only users.
    totals = {}
    for row in scores:
        if not row.mature:
            continue
        total, count = totals.setdefault(row.user_id, (0.0, 0))
        if not conditional or row.target_count:
            total += getattr(row.metrics, metric) or 0.0
            count += 1
        totals[row.user_id] = (total, count)
    return totals


def _estimate(totals, multiplicities, user_macro):
    numerator = denominator = 0.0
    for user, multiplicity in multiplicities.items():
        total, count = totals[user]
        if not count:
            continue
        numerator += multiplicity * (total / count if user_macro else total)
        denominator += multiplicity * (1 if user_macro else count)
    return numerator / denominator if denominator else None


def _aggregate(scores, estimand):
    values = []
    for metric in METRICS:
        totals = _user_totals(scores, metric, estimand.startswith("conditional"))
        values.append(_estimate(totals, dict.fromkeys(totals, 1), "user_macro" in estimand))
    return MetricValues(*values)


def evaluate(rankings: Iterable[QueryRanking], k: int) -> Evaluation:
    """Query macro weights each mature query equally; user macro weights users.

    Conditional variants include only nonempty mature queries (and users with
    at least one such query). Zero variants include all mature queries/users,
    assigning empty Y a zero score. Censored queries enter only their counter.
    """
    scores = _score_all(rankings, k)
    mature = [row for row in scores if row.mature]
    positive = [row for row in mature if row.target_count]
    return Evaluation(
        k, len(scores), len(mature), len(scores) - len(mature), len(positive),
        len({row.user_id for row in mature}), len({row.user_id for row in positive}),
        len(positive) / len(mature) if mature else None,
        *(_aggregate(scores, estimand) for estimand in ESTIMANDS),
    )


def _percentile(sorted_values, probability):
    position = (len(sorted_values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    fraction = position - lower
    return sorted_values[lower] * (1 - fraction) + sorted_values[upper] * fraction


def paired_user_bootstrap(
    left: Iterable[QueryRanking], right: Iterable[QueryRanking], k: int, *,
    metric: str = "ndcg", estimand: str = "conditional_macro_query",
    replicates: int = 1000, seed: int = 0,
) -> BootstrapDifference:
    """Resample all mature users with replacement, keeping every user's queries.

    Paired queries must share IDs, users, maturity and full labels; input order
    may differ. Each draw uses ONE multiplicity for both models. Query macro
    recomputes sum(k_u * score_sum_u) / sum(k_u * query_count_u), not a mean
    of user means. A zero-positive draw in a conditional estimand is None.
    The same seed and the same left cluster order reproduce draws exactly.
    """
    _positive_integer(replicates, "replicates", 1000)
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    if metric not in METRICS or estimand not in ESTIMANDS:
        raise ValueError("unknown metric or estimand")
    left_queries, right_queries = list(left), list(right)
    left_scores, right_scores = _score_all(left_queries, k), _score_all(right_queries, k)
    right_by_id = {query.query_id: query for query in right_queries}
    if {query.query_id for query in left_queries} != set(right_by_id):
        raise ValueError("paired models must have exactly the same query IDs")
    for query in left_queries:
        other = right_by_id[query.query_id]
        if (query.user_id, query.mature, query.targets) != (other.user_id, other.mature, other.targets):
            raise ValueError("paired queries must share users, maturity and full targets")
    conditional = estimand.startswith("conditional")
    user_macro = "user_macro" in estimand
    left_totals = _user_totals(left_scores, metric, conditional)
    right_totals = _user_totals(right_scores, metric, conditional)
    users = list(left_totals)

    def difference(multiplicities):
        first = _estimate(left_totals, multiplicities, user_macro)
        second = _estimate(right_totals, multiplicities, user_macro)
        return first - second if first is not None and second is not None else None

    rng = random.Random(seed)
    samples = []
    for _ in range(replicates):
        multiplicities = defaultdict(int)
        for user in rng.choices(users, k=len(users)):
            multiplicities[user] += 1
        samples.append(difference(multiplicities))
    defined = sorted(value for value in samples if value is not None)
    interval = (_percentile(defined, 0.025), _percentile(defined, 0.975)) if defined else None
    return BootstrapDifference(
        metric, estimand, seed, replicates, len(users), difference(dict.fromkeys(users, 1)),
        tuple(samples), replicates - len(defined), interval,
    )
