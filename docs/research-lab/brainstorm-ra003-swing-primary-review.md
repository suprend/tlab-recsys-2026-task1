# RA003 / RA3-01 Swing — independent source and finite-bound review

Reviewed 2026-10-15. Owner: `/root/brainstorm_models_a/ra003_swing_primary_review`. Scope: the named frozen RA003 report/ledger/manifest, historical ItemCF documentation at `f842553`, primary paper and author-linked repository source. No real events, SQL, Y, models, fits, native build, downloaded dataset/weights, repository edits or author edits. Only this helper note was written. The research skill was applied. No children were spawned.

**Disposition: retain RA3-01 as a distinct ItemCF refinement, with a conditional pilot only after the declared completeness/degree gates.** The synthetic scores and stated query-local arithmetic bounds pass. Source access has improved since the author's freeze: the actual exact implementation is readable and exposes a factor-two convention difference from rendered Algorithm 1. Update the source ledger and freeze output-filter ordering before implementation; this is not evidence of a recommendation gain or executable validation.

## Primary-source audit

- The arXiv submission is v1, 2026-09-15 08:42:59 UTC, by Runhao Jiang and Renchi Yang. Its metadata calls it a technical report for SIGMOD 2027; that future venue label is not a completed-publication date. [arXiv metadata](https://arxiv.org/abs/2609.16850v1).
- The report attributes Swing to Yang 2020. Equation 1 and Algorithm 1 use the full shared-item set, with smoothing alpha, typically 1; Algorithm 1 excludes diagonal users but enumerates both orders. The score-error guarantees concern Swing estimation. A future-purchase recall guarantee does not follow. The paper explicitly links HKBU-LAGAS/K-ASC in §6, establishing first-party provenance. [2026 report §§2.1–2.3, 4.4, 6](https://arxiv.org/html/2609.16850v1).
- Swing predates this report: the 2020 primary source explicitly proposes it. That source also gives an activity-weighted Swing variant. RA3-01 is therefore a new explicit local refinement, not a new 2024–26 recommendation principle or the full weighted 2020 variant. [Yang et al. 2020, §2.1](https://arxiv.org/html/2010.05525v1).
- The repository README names the same paper and gcc 8.5.0. The paper-to-repository link matters more for ownership than the organization name alone. [author repository](https://github.com/HKBU-LAGAS/K-ASC).

Code inspection was read-only through the GitHub connector, pinned to commit `caaffbc592672503df708cdcc62ba556e3cb3cee` (committer timestamp 2026-09-15T07:01:32Z). Browser source retrieval initially failed for the code tree, raw URL and blob URL; the connector then succeeded. `code/main.cpp` returned 404 because the actual tree has `code/src/main.cc`, `code/src/algo.cc` and headers. Do not retain “implementation files inaccessible” as the current review conclusion, and do not infer author fault from the earlier access limitation.

`ExactSwing` iterates `j<i`, intersects complete user item sets, calculates the reciprocal of alpha plus the intersection cardinality, and increments every intersected item. `FastExactSwing` uses the same unordered-pair convention. No removal of q or target j appears between intersection and denominator calculation. [algo.cc lines 119–174](https://github.com/HKBU-LAGAS/K-ASC/blob/caaffbc592672503df708cdcc62ba556e3cb3cee/code/src/algo.cc#L119-L174). The configuration defaults alpha to 1. [utils.h line 133](https://github.com/HKBU-LAGAS/K-ASC/blob/caaffbc592672503df708cdcc62ba556e3cb3cee/code/include/utils.h#L133). The inspected evaluation routine excludes the current query item from ranked results. [main.cc lines 32–38](https://github.com/HKBU-LAGAS/K-ASC/blob/caaffbc592672503df708cdcc62ba556e3cb3cee/code/src/main.cc#L32-L38).

Consequently, the rendered paper Algorithm 1 and the inspected exact implementation differ by factor two on off-diagonal item scores. RA's declared unordered convention matches the inspected exact source and is half the literal rendered ordered convention. With one fixed alpha and no absolute score threshold, multiplying every anchor score by two preserves per-anchor ranking, summed rankings and product-ID ties. This does not establish all ASC/K-ASC code paths or compiled correctness; they were not audited or run. A threshold or calibration added later would need the convention stated explicitly.

## Literal mechanism and historical non-alias check

Read the immutable `f842553:docs/candidate-generation/05-itemcf.md` (SHA256 `f8a35655402279d89d86586a310d4166aa11a2ffdffe83b07123d5710bd8a21a`). Its activity weighting is `w_v=1/max(1,m_v−1)`, replacing c and d by weighted sums while checking raw co-user support. It is a single-user activity statistic; it does not contain the pair-specific shared-profile denominator. The baseline's normalization and support shrinkage cannot separate the supplied equal-statistic fixture.

Recomputed using Python standard-library `Fraction`, `combinations` and `permutations`, on the invented six profiles only:

| Statistic | Candidate a | Candidate b |
|---|---:|---:|
| Co-users / item degree | 3 / 3 | 3 / 3 |
| Query degree | 6 | 6 |
| Degree of each contributing user | 3 | 3 |
| Frozen weighted c / weighted target d | 3/2 / 3/2 | 3/2 / 3/2 |
| Weighted query d | 3 | 3 |
| Distinct unordered user pairs | 3 | 3 |
| Shared items per pair, including q and target | 3 | 2 |
| Constant-pair-weight control | 3 | 3 |
| RA unordered Swing, alpha=1 | 3/4 | 1 |
| Rendered ordered score | 3/2 | 2 |

Thus ordinary cosine, weighted cosine, support shrinkage, Jaccard and lift tie, while Swing reverses the tied top-1 outcome when a precedes b by ID. This proves a non-alias for those declared controls on one literal graph; it does not establish an exhaustive absence of equivalent mechanisms elsewhere in the backlog. The report's narrower novelty wording is appropriate.

## Query-local bounds and source semantics

The advertised bounds are valid conservative arithmetic **conditional on complete whole profiles and the pre-score gates**:

| Bound | Derivation | Result |
|---|---|---:|
| Pairs per admitted anchor | choose(32,2) | 496 |
| Four-anchor merge comparisons | 4 × 496 × 64 | 126,976 |
| Four-anchor score increments | 4 × 496 × 32 | 63,488 |
| Four-anchor co-count profile-edge visits | 4 × 32 × 32 | 4,096 |
| Discovered IDs, loose bound | 4 × 32 × 32 | 4,096 |

The 64-comparison bound is conservative for sorted two-pointer intersections of two profiles of length at most 32. Alpha and filtering do not alter those loop ceilings. Top 100/20 limits output; the degree gates, not K, bound exact discovery. Three independently charged source arms remain conservative, although gates, degree lookup, weighted normalizations, selection and serialization still require separate accounting. These are not full CPU or physical-I/O bounds.

The declared policy is internally consistent if interpreted as: remove the query user before co-user floors, anchor audience tests, popularity counts and exact scoring; reject entire background profiles with full-window degree above 32; reject anchors with remaining audience above 32; do not clip or replace rejected anchors. The same admitted graph and filters must be used by both controls. This changes the target graph relative to unrestricted ItemCF and must retain unsupported queries in evaluation.

One implementation detail needs explicit freezing: define the excluded source-anchor set as the first four canonical R20 items before gates, and apply that set identically before each per-anchor top-100 selection and the final top-20 selection. Removing only the currently scored q would allow another selected seed to consume output slots; filtering only after top-K changes the effective quota. Keep those seed items inside user profiles when computing denominators. Bought items can still remain in final C under the declared canonical rules.

The physical-completeness conditions are honest stop gates, not demonstrated feasibility. A complete manifest must cover the full `[c−7d,c)` interval and all relevant events needed to decide full user degree. The 10,000-user discovery cap must count all encountered discovery users, not only admitted ones. A prefix or partial profile can make a true degree-33 user look degree-32 and invalidate both admission and the bound's semantics. Abort before pilot if complete inputs cannot fit the total raw/decoded-byte/row/CPU/RSS limits. The parent review owns the common full-Y/equal-size and aggregate cost audit.

## Concrete cheap falsifiers before any pilot

1. Require exact fixture outputs a=3/4, b=1 and constant-weight outputs 3,3. Diagonal pairs, missing q/j denominator terms or a different pair convention without the declared scaling fail this check.
2. Add a two-co-user fixture: the pair score is positive but the source is excluded by the raw three-co-user floor. Remove a query user from a three-user candidate audience and require exclusion before top-K.
3. Add boundary fixtures: a complete degree-32 profile passes, degree-33 profile is removed whole; remaining anchor audiences 32/33 pass/reject. A 33-user anchor containing the excluded query user must be re-evaluated at 32 before the gate.
4. Add two-anchor output fixture: both selected source-anchor IDs are absent from every source arm, while both remain in denominator intersections; stable ID ties and pre-top-K filtering agree across arms.
5. Reject incomplete source manifests, truncated histories, row prefixes represented as complete, gated-query deletion or refill. No recommendation metric is authorized or required for these source-only checks.

## Input integrity

Initial snapshot SHA256 values were taken before content review; final values were recomputed after source/math review and match exactly:

| Frozen input | Initial = final SHA256 |
|---|---|
| manifest.json | `675c1ecf644dfe45d44779814d31b02dd03d00f46c7a1cd4e6ef3ccc03a742dd` |
| tlab-brainstorm-retrieval-a-round-003.md | `19ed927b0db8ba13c3ee2e6bc0368bcecb809e7d1e0ffcb844a78617b90c6c5c` |
| tlab-brainstorm-retrieval-a-round-003-ledger.json | `4fcf833eab669ce4a331514dbcfd36e1192b455132fc570f7fccd6bcdbd6f490` |

Snapshot directory: `/var/folders/gb/j1q8qm811b3gjd3gk93fh22h0000gn/T/tlab-ra003-review-snapshot-uuhimx9p`. Report and ledger hashes also equal the expected manifest values. Final on-disk note readback and link/number checks were performed; no author artifact was changed.
