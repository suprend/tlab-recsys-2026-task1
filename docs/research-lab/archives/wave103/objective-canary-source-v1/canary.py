"""Literal objective contrast; source-only proposal, not evidence of execution."""
import json
import math
from fractions import Fraction
from itertools import permutations

C = ("a", "b", "c")
CASES = {
    "basket_mixture": ((Fraction(9, 20), {"a"}), (Fraction(11, 20), {"b", "c"})),
    "singleton_control": ((Fraction(9, 20), {"a"}), (Fraction(11, 20), {"b"})),
}

def idcg(y):
    return sum(1 / math.log2(r + 1) for r in range(1, min(20, len(y)) + 1))

def softplus(x):
    return max(x, 0) + math.log1p(math.exp(-abs(x)))

def summarize(outcomes):
    coefficients = {i: sum(float(p) * (i in y) / idcg(y) for p, y in outcomes) for i in C}
    marginal = {i: sum((p for p, y in outcomes if i in y), Fraction()) for i in C}
    pairs = {(i, j): sum((p / (len(y) * (len(C) - len(y)))
             for p, y in outcomes if i in y and j not in y), Fraction())
             for i in C for j in C if i != j}
    options = []
    for order in permutations(C):
        value = sum(float(p) * sum((i in y) / math.log2(r + 1)
                    for r, i in enumerate(order[:20], 1)) / idcg(y) for p, y in outcomes)
        options.append({"order": list(order), "expected_ndcg20": value})
    options.sort(key=lambda row: (-row["expected_ndcg20"], row["order"]))
    result = {
        "outcomes": [{"probability": str(p), "Y": sorted(y), "m": len(y),
                      "h": len(y.intersection(C)),
                      "coverage_factor": idcg(y.intersection(C)) / idcg(y),
                      "query_pair_weight_sum": str(sum((Fraction(1, len(y) * (len(C) - len(y)))
                                                       for i in C for j in C if i in y and j not in y), Fraction()))}
                     for p, y in outcomes],
        "expected_normalized_gain": coefficients,
        "bce_bayes_coefficients": {i: str(marginal[i]) for i in C},
        "directed_pair_coefficients": {f"{i}>{j}": str(v) for (i, j), v in pairs.items()},
        "all_six_ndcg_options": options,
    }
    return result, pairs

def main():
    report = {"X": "fixed observed context across outcomes", "K": 20, "C": list(C), "cases": {}}
    for name, outcomes in CASES.items():
        report["cases"][name], pairs = summarize(outcomes)
        if name == "basket_mixture":
            win = pairs[("a", "b")] + pairs[("a", "c")]
            lose = pairs[("b", "a")] + pairs[("c", "a")]
            d_star = math.log(float(win / lose))
            risk = lambda d: sum(float(v) * softplus(({"a": d, "b": 0, "c": 0}[j])
                         - ({"a": d, "b": 0, "c": 0}[i])) for (i, j), v in pairs.items())
            report["cases"][name]["symmetric_pairlogit"] = {
                "constraint": "s_b=s_c=0; d=s_a", "win_mass": str(win), "lose_mass": str(lose),
                "risk_formula": "win_mass*softplus(-d)+lose_mass*softplus(d)",
                "stationary_d": d_star, "risk_at_stationary_d": risk(d_star),
                "risk_at_zero": risk(0), "risk_at_opposite_d": risk(-d_star)}
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))

if __name__ == "__main__":
    main()
