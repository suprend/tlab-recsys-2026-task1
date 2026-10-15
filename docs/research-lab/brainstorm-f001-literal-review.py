"""Independent literal arithmetic only: no project imports, I/O inputs or fitted models."""
from collections import Counter
from math import log
import json

def jaccard(a, b):
    return len(a & b) / len(a | b) if a | b else None

common = [("purchase", "i", 40), ("purchase", "j", 80),
          ("view", "a", 90), ("view", "b", 91),
          ("view", "c", 60), ("view", "d", 61)]
worlds = [common + [("view", "a", 20), ("view", "b", 21),
                    ("view", "c", 0), ("view", "d", 1)],
          common + [("view", "c", 20), ("view", "d", 21),
                    ("view", "a", 0), ("view", "b", 1)]]
def views(events, end):
    return {i for k, i, t in events if k == "view" and end - 24 <= t < end and i != "i"}
def summary(events):
    items = {i for _, i, _ in events}
    return {i: (sum(k == "view" and p == i for k, p, _ in events),
                max((t for k, p, t in events if k == "view" and p == i), default=None))
            for i in items}
assert summary(worlds[0]) == summary(worlds[1])
f01 = [{"specific": jaccard(views(e, 100), views(e, 40)),
        "generic": jaccard(views(e, 100), views(e, 80))} for e in worlds]
assert f01 == [{"specific": 1.0, "generic": 0.0}, {"specific": 0.0, "generic": 0.0}]

# Hand-declared monotone curves and four literal risk-set contributions.
f02 = {"conditional_curve_A": 1 - (2/6)/(4/6),
       "conditional_curve_B": 1 - (2/6)/(3/6),
       "unconditional_both": 1 - 5/6,
       "retain_censored_S2": (3/4)*(2/3),
       "drop_censored_S2": (2/3)*(1/2),
       "retain_censored_residual_1_to_2": 1 - ((3/4)*(2/3))/(3/4),
       "drop_censored_residual_1_to_2": 1 - ((2/3)*(1/2))/(2/3)}
assert abs(f02["conditional_curve_A"] - 0.5) < 1e-12
assert abs(f02["conditional_curve_B"] - 1/3) < 1e-12

# Each transition denotes a two-event literal session, two sessions per world.
transitions = [[("cart", "A", "purchase", "B"), ("cart", "C", "purchase", "D")],
               [("purchase", "B", "cart", "A"), ("cart", "C", "purchase", "D")]]
def association(edges, x, y):
    n = len(edges)
    cells = Counter(edges)
    row = sum(a == x for a, b in edges)
    col = sum(b == y for a, b in edges)
    return log((cells[x, y] + 1)/(row*col/n + 1))
typed = [[(a, b) for ka, a, kb, b in ts if (ka, kb) == ("cart", "purchase")] for ts in transitions]
pooled = [[edge for _, a, _, b in ts for edge in [(a, b), (b, a)]] for ts in transitions]
f03 = {"typed": [association(e, "A", "B") for e in typed],
       "pooled_symmetric": [association(e, "A", "B") for e in pooled]}
assert f03["typed"][0] != f03["typed"][1]
assert f03["pooled_symmetric"][0] == f03["pooled_symmetric"][1]
ambiguous_peers = [("cart", "E"), ("cart", "F")]
assert len(set(ambiguous_peers)) != 1
assert len(set(reversed(ambiguous_peers))) != 1

def js(p, q):
    m = [(a+b)/2 for a, b in zip(p, q)]
    return sum(v*log(v/w)/2 for vals in [p, q] for v, w in zip(vals, m) if v)
def f04_units(scale):
    day1 = [scale*x/(scale*2 + 1) for x in [-2, -1, 0, 1, 2]]
    day2 = [scale*x/(scale*4 + 1) for x in [-3.6, -2, 0, 2, 3.6]]
    limit = max(abs(x) for x in day1)  # frozen first-block in-range/overflow bins
    p = [sum(abs(x) <= limit for x in day1)/5, sum(abs(x) > limit for x in day1)/5]
    q = [sum(abs(x) <= limit for x in day2)/5, sum(abs(x) > limit for x in day2)/5]
    drift = js(p, q)
    return {"day1_hist": p, "day2_hist": q, "JS": drift, "score": 1/(1+drift)}
f04 = {"units_1": f04_units(1), "equivalent_units_100": f04_units(100),
       "stable_vs_alternating_same_pooled_JS": [js([.5,.5], [.5,.5]), js([.8,.2], [.2,.8])]}
assert f04["units_1"]["JS"] > 0
assert f04["equivalent_units_100"]["JS"] == 0
assert f04["stable_vs_alternating_same_pooled_JS"][1] > 0

print(json.dumps({"scope": "literal_arithmetic_only", "real_data_rows": 0,
                  "native_fits": 0, "database_opens": 0,
                  "literal_event_rows_f01": 20, "literal_event_rows_f03": 8,
                  "f01": f01, "f02": f02, "f03": f03, "f04": f04}, indent=2))
