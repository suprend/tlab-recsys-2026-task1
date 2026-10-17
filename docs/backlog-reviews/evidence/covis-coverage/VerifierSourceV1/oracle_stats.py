"""Independent SOURCE-only coverage statistics; no readers or execution entry point.

The only authoritative analysis source used to author this module is the sealed
NEXTSTAGE-PLAN-v2.md identified in STATS-SOURCE-NOTE.md.  calculate() operates on
already authenticated, materialized records and never constructs candidates.
"""

import hashlib
import math
import random


ARMS = (
    "C0",
    "count",
    "cos",
    "matched_popular",
    "matched_count",
    "matched_cos",
)
SLICES = ("full", "new", "repeat")
CONTRASTS = (
    ("cos-C0", 2, 0),
    ("count-C0", 1, 0),
    ("cos-count", 2, 1),
    ("matched_cos-matched_popular", 5, 3),
)


def _require_int_set(value, container_type, location):
    if type(value) is not container_type:
        raise TypeError(location + " has the wrong set type")
    if any(type(item) is not int for item in value):
        raise TypeError(location + " contains a non-exact-int item ID")


def _empty_point_totals():
    return {
        "positive_queries": [0, 0, 0],
        "target_mass": [0, 0, 0],
        "hits": [0] * 18,
        "hit_any": [0] * 18,
        "recall_sum": [0.0] * 18,
        "oracle_ndcg20_sum": [0.0] * 18,
        "contrast_sum": [0.0] * 12,
    }


def _empty_user_vector():
    return {
        "positive_queries": [0, 0, 0],
        "contrast_sum": [0.0] * 12,
    }


def _type7(sorted_values, probability):
    """The caller supplies at least one finite value in ascending order."""
    position = (len(sorted_values) - 1) * probability
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    fraction = position - lower_index
    lower_value = sorted_values[lower_index]
    return lower_value + fraction * (
        sorted_values[upper_index] - lower_value
    )


def calculate(records, draws=2000, seed=61061, check=lambda: None):
    """Return {summary, _bootstrap}; all undefined quantities are None.

    This function is deterministic and has no I/O.  The supplied check callback
    may interrupt validation, aggregation or a draw by raising an exception.
    Input sets are read only.  Source caps permit zero through 6000 query rows;
    production frame cardinality and upstream lineage belong to the caller.
    """
    if type(records) is not list:
        raise TypeError("records must be an exact list")
    if len(records) > 6000:
        raise ValueError("the query frame exceeds 6000 records")
    if type(draws) is not int or draws < 1:
        raise ValueError("draws must be a positive exact int")
    if type(seed) is not int:
        raise TypeError("seed must be an exact int")
    if not callable(check):
        raise TypeError("check must be callable")
    check()

    seen_queries = set()
    all_user_ids = set()
    required_keys = {"query_id", "user_id", "targets", "prior", "arms"}
    expected_arms = set(ARMS)
    for row_number, record in enumerate(records):
        if row_number % 32 == 0:
            check()
        if type(record) is not dict or not required_keys.issubset(record):
            raise TypeError("each record must be a dict with all required keys")
        query_id = record["query_id"]
        if type(query_id) is not str or not query_id.isascii():
            raise TypeError("query_id must be an exact ASCII str")
        if query_id in seen_queries:
            raise ValueError("duplicate query_id")
        seen_queries.add(query_id)
        user_id = record["user_id"]
        if type(user_id) is not int:
            raise TypeError("user_id must be an exact int")
        all_user_ids.add(user_id)
        _require_int_set(record["targets"], set, "targets")
        _require_int_set(record["prior"], set, "prior")
        arms = record["arms"]
        if type(arms) is not dict or set(arms) != expected_arms:
            raise TypeError("arms must be a dict with exactly the six arm names")
        for arm in ARMS:
            _require_int_set(arms[arm], frozenset, "arms[" + arm + "]")

    # ASCII query-ID order fixes point reductions and within-user boot vectors.
    ordered_records = sorted(records, key=lambda row: row["query_id"])
    user_ids = sorted(all_user_ids)
    user_vectors = {user_id: _empty_user_vector() for user_id in user_ids}
    totals = _empty_point_totals()
    discounts = [0.0]
    for rank in range(1, 21):
        discounts.append(discounts[-1] + 1.0 / math.log2(rank + 1))

    for row_number, record in enumerate(ordered_records):
        if row_number % 32 == 0:
            check()
        targets = record["targets"]
        prior = record["prior"]
        target_slices = (targets, targets - prior, targets & prior)
        vector = user_vectors[record["user_id"]]
        for slice_index, slice_targets in enumerate(target_slices):
            mass = len(slice_targets)
            if mass == 0:
                continue
            totals["positive_queries"][slice_index] += 1
            totals["target_mass"][slice_index] += mass
            vector["positive_queries"][slice_index] += 1
            oracle_denominator = discounts[min(20, mass)]
            row_recalls = []
            for arm_index, arm in enumerate(ARMS):
                metric_index = slice_index * len(ARMS) + arm_index
                hits = len(record["arms"][arm] & slice_targets)
                recall = hits / mass
                row_recalls.append(recall)
                totals["hits"][metric_index] += hits
                totals["hit_any"][metric_index] += int(hits > 0)
                totals["recall_sum"][metric_index] += recall
                totals["oracle_ndcg20_sum"][metric_index] += (
                    discounts[min(20, hits)] / oracle_denominator
                )
            for contrast_index, (_, left, right) in enumerate(CONTRASTS):
                difference = row_recalls[left] - row_recalls[right]
                paired_index = slice_index * 4 + contrast_index
                totals["contrast_sum"][paired_index] += difference
                vector["contrast_sum"][paired_index] += difference

    # A zero-Y user remains in user_ids.  Its vector is exactly zero and can be
    # skipped during bootstrap reduction without changing the random frame.
    positive_vectors = [
        (index, user_vectors[user_id])
        for index, user_id in enumerate(user_ids)
        if user_vectors[user_id]["positive_queries"][0] > 0
    ]
    query_count = len(records)
    user_count = len(user_ids)
    slice_summary = {}
    for slice_index, slice_name in enumerate(SLICES):
        slice_summary[slice_name] = {
            "positive_queries": totals["positive_queries"][slice_index],
            "target_mass": totals["target_mass"][slice_index],
        }

    arm_summary = {}
    for arm_index, arm in enumerate(ARMS):
        arm_summary[arm] = {}
        for slice_index, slice_name in enumerate(SLICES):
            metric_index = slice_index * len(ARMS) + arm_index
            positives = totals["positive_queries"][slice_index]
            mass = totals["target_mass"][slice_index]
            hits = totals["hits"][metric_index]
            hit_any = totals["hit_any"][metric_index]
            arm_summary[arm][slice_name] = {
                "hits": hits,
                "macro_recall": (
                    totals["recall_sum"][metric_index] / positives
                    if positives else None
                ),
                "micro_recall": hits / mass if mass else None,
                "hit_any": hit_any,
                "hit_any_over_positive_queries": (
                    hit_any / positives if positives else None
                ),
                "hit_any_over_all_queries": (
                    hit_any / query_count if query_count else None
                ),
                "oracle_ndcg20": (
                    totals["oracle_ndcg20_sum"][metric_index] / positives
                    if positives else None
                ),
            }

    draw_denominators = {name: [] for name in SLICES}
    draw_contrasts = {
        name: {slice_name: [] for slice_name in SLICES}
        for name, _, _ in CONTRASTS
    }
    multiplicity_sha256 = []
    rng = random.Random(seed)
    for draw_index in range(draws):
        check()
        multiplicities = [0] * user_count
        # Exactly M calls to randrange(M) per draw, including zero-Y users.
        # M == 0 is an empty frame: no RNG calls and every draw is undefined.
        for sample_index in range(user_count):
            if sample_index % 256 == 0:
                check()
            multiplicities[rng.randrange(user_count)] += 1
        multiplicity_sha256.append(
            hashlib.sha256(
                b"".join(count.to_bytes(4, "big") for count in multiplicities)
            ).hexdigest()
        )
        draw_positive_queries = [0, 0, 0]
        draw_sums = [0.0] * 12
        for vector_number, (user_index, vector) in enumerate(positive_vectors):
            if vector_number % 256 == 0:
                check()
            multiplicity = multiplicities[user_index]
            if multiplicity == 0:
                continue
            for slice_index in range(3):
                draw_positive_queries[slice_index] += (
                    multiplicity * vector["positive_queries"][slice_index]
                )
            # Ascending signed user ID fixes the between-user reduction order.
            for contrast_index in range(12):
                draw_sums[contrast_index] += (
                    multiplicity * vector["contrast_sum"][contrast_index]
                )
        for slice_index, slice_name in enumerate(SLICES):
            positives = draw_positive_queries[slice_index]
            draw_denominators[slice_name].append(positives)
            for contrast_index, (name, _, _) in enumerate(CONTRASTS):
                draw_contrasts[name][slice_name].append(
                    draw_sums[slice_index * 4 + contrast_index] / positives
                    if positives else None
                )

    contrast_summary = {}
    for contrast_index, (name, _, _) in enumerate(CONTRASTS):
        contrast_summary[name] = {}
        for slice_index, slice_name in enumerate(SLICES):
            positives = totals["positive_queries"][slice_index]
            estimate = (
                totals["contrast_sum"][slice_index * 4 + contrast_index] / positives
                if positives else None
            )
            values = draw_contrasts[name][slice_name]
            defined_values = sorted(value for value in values if value is not None)
            defined_count = len(defined_values)
            undefined_count = draws - defined_count
            is_primary = name == "cos-C0" and slice_name == "full"
            interval_allowed = bool(defined_count) and (
                not is_primary or undefined_count == 0
            )
            ci95 = (
                [_type7(defined_values, 0.025), _type7(defined_values, 0.975)]
                if interval_allowed else None
            )
            contrast_summary[name][slice_name] = {
                "estimate": estimate,
                "ci95": ci95,
                "defined_draws": defined_count,
                "undefined_draws": undefined_count,
                "interval_basis": (
                    "all-draws-required" if is_primary else "conditional-on-defined"
                ),
            }

    primary = contrast_summary["cos-C0"]["full"]
    matched = contrast_summary["matched_cos-matched_popular"]["full"]
    primary_point_pass = (
        primary["estimate"] >= 0.005 if primary["estimate"] is not None else None
    )
    primary_lower_pass = (
        primary["ci95"][0] > 0.0 if primary["ci95"] is not None else None
    )
    matched_point_pass = (
        matched["estimate"] > 0.0 if matched["estimate"] is not None else None
    )
    passed = bool(primary_point_pass and primary_lower_pass and matched_point_pass)
    if totals["positive_queries"][0] == 0:
        decision = "inconclusive"
        reason = "N_PLUS_ZERO"
    elif primary["undefined_draws"] > 0:
        decision = "inconclusive"
        reason = "UNDEFINED_PRIMARY_DRAWS"
    elif passed:
        decision = "propose_optional_continuation"
        reason = "ALL_PROSPECTIVE_CRITERIA_MET"
    elif primary["ci95"] is not None and primary["ci95"][1] <= 0.0:
        decision = "reject_current_cosine_continuation"
        reason = "PRIMARY_UPPER95_NONPOSITIVE"
    else:
        decision = "inconclusive"
        reason = "PROSPECTIVE_CRITERION_NOT_MET"

    summary = {
        "schema": "tlab.hyp061.independent-coverage-stats.v1",
        "frame": {
            "queries": query_count,
            "users": user_count,
            "positive_queries": totals["positive_queries"][0],
            "zero_target_queries": query_count - totals["positive_queries"][0],
            "target_mass": totals["target_mass"][0],
        },
        "slices": slice_summary,
        "arms": arm_summary,
        "contrasts": contrast_summary,
        "bootstrap": {
            "draws": draws,
            "seed": seed,
            "frame": "all-distinct-query-users-including-zero-target-users",
            "sampling": "M-users-with-replacement-shared-across-arms-and-slices",
            "interval": "95-percent-percentile-type7",
            "primary": {"contrast": "cos-C0", "slice": "full"},
        },
        "continuation": {
            "passed": passed,
            "decision": decision,
            "reason": reason,
            "native_cos_ge_0_005": primary_point_pass,
            "native_cos_lower95_gt_0": primary_lower_pass,
            "matched_cos_gt_0": matched_point_pass,
        },
    }
    check()
    return {
        "summary": summary,
        "_bootstrap": {
            "query_ids": [record["query_id"] for record in ordered_records],
            "user_ids": user_ids,
            "draw_denominators": draw_denominators,
            "draw_contrasts": draw_contrasts,
            "multiplicity_sha256": multiplicity_sha256,
            "multiplicity_encoding": "ascending-signed-user-ID uint32 big-endian counts",
        },
    }
