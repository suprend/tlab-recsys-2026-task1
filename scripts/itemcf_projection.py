"""One-query exact ItemCF projection over caller-supplied complete postings."""

from bisect import bisect_left
from math import sqrt


class LimitExceeded(RuntimeError):
    """A caller's finite input/work limit was exceeded; no partial result."""


def project_itemcf(user_id, candidates, latest21, postings, *,
                   max_members, max_work, check, cache_pairs=0):
    """Inputs are exact ints, tuples and a dict of sorted distinct-user tuples.

    postings keys must be exactly candidates union latest21, including known
    empty tuples. Missing keys are incomplete input, not known zero. The caller
    guarantees complete snapshot membership and correctly ordered latest21.
    max_work charges validation, membership upper bounds, history and merge
    visits; it is not CPU time. check() supplies the caller's external check.
    The local cache stores only raw intersections and never personalized scores.
    """
    if type(user_id) is not int:
        raise ValueError("query user_id must be an exact int, not NULL/bool")
    for name, value in (("max_members", max_members), ("max_work", max_work),
                        ("cache_pairs", cache_pairs)):
        if type(value) is not int or value < 0:
            raise ValueError(name + " must be a finite nonnegative int")
    if cache_pairs > 4400 or not callable(check):
        raise ValueError("cache_pairs <= 4400 and callable check required")
    work = 0

    def charge(amount=1):
        nonlocal work
        work += amount
        if work > max_work:
            raise LimitExceeded("max_work exceeded")
        check()

    charge()
    for name, values, cap in (("candidates", candidates, 220),
                              ("latest21", latest21, 21)):
        if type(values) is not tuple or len(values) > cap:
            raise ValueError(name + " must be a bounded tuple")
        seen = set()
        for value in values:
            charge()
            if type(value) is not int or value in seen:
                raise ValueError(name + " requires distinct exact int IDs")
            seen.add(value)
    required = set(candidates) | set(latest21)
    if type(postings) is not dict or len(postings) != len(required):
        raise ValueError("postings must cover exactly the required item keys")
    for item in postings:
        charge()
        if type(item) is not int:
            raise ValueError("postings item keys must be exact ints")
    if set(postings) != required:
        raise ValueError("missing or unexpected postings item")
    vectors = dict(postings)  # Bounded owned key map; tuple members are immutable.
    total = 0
    for vector in vectors.values():
        charge()
        if type(vector) is not tuple:
            raise ValueError("each posting must be an immutable tuple")
        total += len(vector)
        if total > max_members:
            raise LimitExceeded("max_members exceeded before member validation")
    own = {}
    for item, vector in vectors.items():
        previous = None
        for member in vector:
            charge()
            if type(member) is not int or previous is not None and member <= previous:
                raise ValueError("posting users must be sorted distinct exact ints")
            previous = member
        # Membership comes from the FULL posting, never from latest21.
        charge(1 + len(vector).bit_length())
        position = bisect_left(vector, user_id)
        own[item] = int(position < len(vector) and vector[position] == user_id)
    raw_cache = {}

    def raw_intersection(left, right):
        key = (min(left, right), max(left, right))
        if key in raw_cache:
            return raw_cache[key]
        a, b = vectors[left], vectors[right]
        i = j = common = 0
        while i < len(a) and j < len(b):
            charge()
            if a[i] == b[j]:
                common += 1
                i += 1
                j += 1
            elif a[i] < b[j]:
                i += 1
            else:
                j += 1
        if len(raw_cache) < cache_pairs:
            raw_cache[key] = common
        return common

    rows = []
    for candidate in candidates:
        charge()
        history = []
        for item in latest21:
            charge()
            if item != candidate and len(history) < 20:
                history.append(item)
        a = len(vectors[candidate]) - own[candidate]
        total_score = best = 0.0
        supported = maximum_support = defined = 0
        for item in history:
            charge()
            c = raw_intersection(candidate, item) - own[candidate] * own[item]
            b = len(vectors[item]) - own[item]
            maximum_support = max(maximum_support, c)
            if a > 0 and b > 0:
                defined += 1
                if c >= 3:
                    supported += 1
                    score = (c / (c + 10)) * (c / sqrt(a * b))
                    total_score += score
                    best = max(best, score)
        count = len(history)
        rows.append(dict(product_id=candidate,
                         itemcf_mean=total_score / count if count else 0.0,
                         itemcf_max=best, history_n=count,
                         supported_pairs=supported, pair_support_max=maximum_support,
                         defined_fraction=defined / count if count else None,
                         no_history=count == 0, candidate_cold=a == 0))
    charge()
    return rows
