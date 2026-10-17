# Wave091 — join execution and consolidation, independent FIRST

**Decision:** refine/merge existing HYP-046 and HYP-002/TLAB-016; no new ID, task, admission, gate or quality claim. Two concrete semantic witnesses extend Round013 beyond duplicate keys and strict-past checks. All proposed experiments are UNRUN; cost and budget adequacy UNKNOWN.

## Source boundary and dedup

[Hippasus v1 §7](https://arxiv.org/html/2602.02025v1#S7) describes inner joins over the suffix, one outer join to the base, first-occurrence deduplication, and selecting the lowest-null version of a repeated feature. [V2 §4.3](https://arxiv.org/html/2602.02025v2#S4.SS3) repeats these execution/consolidation rules, explicitly claiming equality of joined values under deterministic ordering and fixed deduplication. These are distinct versions; v2's adaptive semantic machinery is not v1 evidence. The provenance scout establishes citation identity, not available code, artifact license, dataset identity or reproducibility. Its original GitHub artifact and later anonymous artifact do not provide inspectable implementation here.

HYP-046 already requires full policy identity and forbids merging query-constant with candidate-conditioned nodes. Round013 already covers fanout, ambiguous metadata, ID/code grain, taxonomy membership and empty outer rows. Thus the contributions below are sharper counterexamples and tests inside existing families, not new mechanisms of predictive improvement.

## HYP-046 refinement: inner suffix can erase a valid prefix value

**Mechanism:** distinguish preservation of base rows/labels from preservation of each partially matched feature. Use the literal paper rewrite only where all retained prefix values survive suffix reduction, or reconstruct the partial matches.

**Counterhypothesis:** deterministic ordering and fixed deduplication suffice for sequential-left versus suffix-inner equivalence. Stronger alternative: an unstated total-match assumption or implementation repair might exclude this witness; actual code remains UNKNOWN.

**Minimal exact unit and prediction:** one query q, C={(q,p1),(q,p2)}; product rows p1=(brand B,category NULL), p2=(brand C,category 10); category row 10=(code a). Every PK is unique; the nullable FK is valid; no duplicate, fanout, future row or conflicting bucket exists. All metadata is observed/available before t. Sequential C LEFT Product LEFT Category yields brands [B,C], codes [NULL,a]. Product INNER Category followed by C LEFT suffix yields brands [NULL,C], codes [NULL,a]. Both retain exactly two base pairs and the same target distribution, yet brand support falls 2→1. This is a hand-derived counterexample to the described unrestricted equivalence claim, not a detected Hippasus implementation failure.

Freeze fullY(q)={p2,p3}, with p3 outside C. Neither plan may discard p3, relabel NULL, or filter C using match success. Pair labels [0,1] and fullY remain byte/equality-identical; preserving only label frequencies is insufficient to prove pairwise binding.

**Time-correct distinguishing experiment:** independently enumerate the five input rows and compare two literal relational definitions at one anchor; then add the control with p1.category=10, where both plans agree. Check exact ordered keys, brand/code values, NULL masks and fullY, not only row counts. Include an empty-C query whose fullY remains represented outside the F table. No model or quality evaluation is needed.

**Proposed bound:** ≤12 input/output row instances per fixture, two fixtures, ≤10 CPU seconds/20 wall seconds/128 MiB/1 thread/64 KiB outputs; zero data scans, fits or API calls. Preparation, checks and cleanup included; stop on mismatch or exhaustion, no retry. Adequacy UNKNOWN; this is a proposal, not an allocation. Accept the bounded semantic restriction if the literal mismatch/control are independently reproduced; reject universal rewrite equivalence. Reject this applicability claim if a documented enforced precondition excludes nullable or partial suffix matches.

**Task1 benefit:** prevents an optimization of automatic feature calculation from silently changing a supported scalar into missing while all Q/C/Y shape checks pass. Current one-event-table aggregation does not implement this multi-table path; no present compiler defect or speedup follows.

## HYP-046/HYP-002 refinement: role identity precedes density selection

**Mechanism:** treat a feature as endpoint column plus relationship role, anchor, population/support, temporal resolution and NULL policy. Consolidate only proved-equivalent expressions. A denser path can instead define a different feature.

**Counterhypothesis:** reaching the same table/column makes two paths interchangeable; lowest NULL ratio safely picks the better realization.

**Minimal exact unit and prediction:** reuse q and two candidates. Product p1 has category A; p2 has unknown category. The same Category table contains A→code a and B→code b; q's user's favorite_category is B. Candidate→Category yields [a,NULL], whereas query-user→favorite_category→Category yields [b,b]. All keys are unique, all values are prior, and C/fullY are fixed. Density prefers the second column (0 versus 1/2 NULL), replacing candidate category with a query-constant preference. No amount of row preservation proves equality. NULL denotes unknown candidate metadata; it does not authorize substitution from another role.

**Experiment and decision:** independently enumerate these two role-qualified paths, their support/masks and keys; then a positive control routes both paths through the same candidate category mapping. Accept consolidation only in that control after complete value/support equivalence; reject endpoint-name/density equivalence in the role witness. Proposed joint cap with the first experiment: ≤40 row instances, four fixtures, ≤20 CPU/40 wall seconds/128 MiB/1 thread/128 KiB output, zero fits/API/data scans; adequacy UNKNOWN, UNRUN and ungranted.

**Task1 benefit/transfer:** existing latest raw code versus ID dictionary already has explicit recovery/conflict semantics; density cannot override that policy. Retain unknown/ambiguous/support states. The abstraction transfers to a relational schema with multiple roles pointing at one dimension; no additional public dataset pilot is proposed. Any such pilot first needs exact upstream identity, schema/version, available-time assumptions and artifact/data licenses. Those remain UNKNOWN for Hippasus benchmarks, including Northwind.

## Metadata and unchanged scope

First observed tool UTC: 2026-10-17T04:27:28Z; exact start UNKNOWN. Blind FIRST: no current wave091 peer draft, discussion or helper was read/used before freeze. Common provenance read; prior published waves/contracts read in relevant slices, not a complete semantic audit. Root alone coordinates and publishes canonical Git. Local HEAD observed d2d2aac4715dfff8bf3f0be20ac27f6d8f42bb1d, clean; publication of that later checkpoint remains Root-pending. Native CLI/callback/cold-shell UNRUN; new 50 CPU/65 wall one-fit≤8 synthetic question PENDING, no issue/allocation/runtime. Old science/native CLOSED/remainder UNKNOWN; seven fixes/89 synthetic/finite QYC-F-Prepared remain accepted in their scopes. Final CI crosses zero; adaptive1189/403 exploratory; 14/19 accepted,014 continuous,010–013 optional/deferred. Original due04:30 UTC/07:30 MSK17Oct, next05:15 UTC and 45-minute grid unchanged; deadline25Oct23:59 timezone UNKNOWN. No canonical mutation, downloads, SQL/tests/raw data/model/project imports, network writes or paid execution.
