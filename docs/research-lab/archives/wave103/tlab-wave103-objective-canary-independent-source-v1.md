# Wave103 objective canary v1 — independent SOURCE review

**No actionable findings. SOURCE ACCEPT within the stated literal domain; this is neither an executed test nor runtime admission.** Reviewed current 63-line `canary.py`, 31-line README and author freeze. All three hashes match Root's assigned versions. The author of this review did not implement the canary. B FIRST remains byte-identical and was not edited; C FIRST was not opened.

## Independent mathematical reconstruction

Let q=1/log2(3), u=9/20 and v=11/[20(1+q)]. Discounts for ranks 1–3 are (1,q,1/2). IDCG is 1 for singleton Y and 1+q for Y={b,c}; these denominators depend on full Y and never on the predicted order. Source lines13–14 and26–28 implement that original formula directly, separately from the normalized-gain coefficients at line20.

The six expected NDCG values reduce to the following expressions. They are hand-derived symbolic expressions, not runtime output.

| Permutation | Basket mixture | Singleton control |
|---|---|---|
| a,b,c | u+v(q+1/2) | 9/20+11q/20 |
| a,c,b | u+v(q+1/2) | 9/20+11/40 |
| b,a,c | uq+3v/2 | 11/20+9q/20 |
| b,c,a | u/2+v(1+q)=31/40 | 31/40 |
| c,a,b | uq+3v/2 | 9q/20+11/40 |
| c,b,a | u/2+v(1+q)=31/40 | 11q/20+9/40 |

For the basket mixture q>1/2 and u>v, so putting a first is strictly better than second or third; b/c are exchangeable. For the singleton control, descending coefficients (11/20,9/20,0) give the unique best order b,a,c. This verifies both the six-permutation domain and the claimed contrast without relying on the proposed script's numbers.

BCE coefficients at lines21/39 are correctly the marginal Bayes **probabilities**: basket (9/20,11/20,11/20), control (9/20,11/20,0). If scores mean logits, the interior minimizers are the corresponding logits; monotonicity leaves these rankings unchanged. The README's generic word “scores” is interpreted in this probability sense, not as a claim that probabilities equal optimal raw logits. Query normalization by the same |C|=3 cannot alter the order. No classifier is fitted.

## PairLogit risk and symmetry

Source lines22–24 weight each positive×negative pair by 1/[m(3−m)]. Both declared outcomes have two such pairs, so every per-outcome pair weight is 1/2 and the per-query sum is exactly one (lines35–36).

Basket directed masses are a>b=a>c=9/40, b>a=c>a=11/40, and b>c=c>b=0. Therefore win=9/20 and lose=11/20. Setting s_b=s_c=0, s_a=d gives exactly

R(d)=(9/20)softplus(−d)+(11/20)softplus(d).

R'(d)=[(11/20)e^d−9/20]/(1+e^d), and R''(d)=e^d/(1+e^d)^2>0. Thus d*=log(9/11)<0 is the unique minimum in this family. The sign and risk expression in lines50–59 agree. Symmetry is legitimate here: before setting b=c, the full risk is a sum of two identical strictly convex functions of s_a−s_b and s_a−s_c, with no b/c comparison. Its minimizing differences coincide; a common score shift is irrelevant. Evaluating d*, 0 and −d* is a useful numerical witness only; the analytical derivative, not three sampled points, establishes the minimum.

For the singleton control the nonzero masses are a>b=a>c=9/40, b>a=b>c=11/40. Candidate c is never positive, so decreasing s_c strictly decreases its incoming pair losses towards zero. There is no finite full-score minimizer for c. The `if name == "basket_mixture"` guard at line49 correctly prevents imposing b=c or calculating a misleading finite control optimum. README lines15/17 explicitly state the relevant boundary.

## Domain, side effects and readiness

All literal Y are nonempty proper subsets of distinct C=(a,b,c); hence m=h, IDCG(Y∩C)/IDCG(Y)=1 and no zero pair denominator occurs. Source lines32–36 report these quantities without using project artifacts. Every score is evaluated at one fixed X across future outcomes. This is an abstract mature-outcome distribution, not actual query, candidate or purchase data.

Only standard-library json/math/fractions/itertools are imported. The body has no file input/output, environment access, network, subprocess, native backend, random search, model or fit; its only output is one finite JSON report. Set membership does not introduce reduction-order nondeterminism: loops run over fixed tuples/permutations, and displayed Y is sorted. There is no hard-coded acceptance verdict. `softplus` uses the stable max/log1p/exp form; the literal win/lose are strictly positive.

The future 5 CPU /8 wall /128 MiB /64 KiB limit is explicitly an external Root-owned envelope, not enforced by this script. That wrapper has not been reviewed or admitted here; startup/resource compliance and actual stdout size remain unmeasured. No source defect requires repair before Root independently considers that optional one-run proposal, and this canary does not delay the primary Task1 result.

Historical README HYP035 is treated only as provenance for the existing TLAB-008/L03 contrast, not as reopening that alias or creating a new hypothesis/gate. Nothing here demonstrates actual CatBoost objective/weight defaults, REES46 performance, model gain, exposure correction or finite-sample learnability.

Verification actually performed: source reading, line mapping, symbolic hand derivation, file metadata/hash checks and report readback. Prototype imports, syntax compilation, tests and execution: **0**. Actual coverage outputs, raw/DB/Q/C/Y/model reads, canonical writes, Git and network: **0**. No implementation changes were made. STOP after readback.
