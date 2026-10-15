# Wave005 independent skeptic review

**Disposition:** merge A005-01 and M5-01 into one HYP046 refinement; retain A005-02 as a compatible append-only DISTINCT specialization within that refinement; keep M5-02/SUDAF deferred. No new HYP is warranted. No confirmed algebra/source defect blocks the proposed source-free correctness gate. There is no accepted full44-column implementation, measured physical saving, real-source affordability or new execution authority.

## Findings and publication requirements

**P3 — Normalize M5-01's four required ledger fields.** In the frozen [models ledger](/tmp/tlab-brainstorm-automation-models-a-wave005-ledger.json), candidate M5-01 uses `prediction`/`cheapest_falsifier`, while its nearest test is a separate top-level object and task1 benefit lives in prose. The required mechanism/testable_prediction/nearest_source_free_experiment/benefit_task1 are semantically present at [MD19](/tmp/tlab-brainstorm-automation-models-a-wave005.md:19),23,29 and51, but are not a complete four-field candidate record. The publisher should normalize them without changing the evidence/disposition. This is a metadata gap, not an algorithm bug. M5-02 is a deferred source/applicability finding, so it must not be padded into a second ready proposal merely to populate a quota.

**Do not count A005-01 and M5-01 as two independent experiment families.** Both start from the same frozen anchor/lower-bound partition and exact operator state. A's count-prefix representation is one eligible flat/additive strategy inside B's capability/cost planner. The additional hierarchy choice remains a distinct *within-family contrast*, not an independently discovered feature/model hypothesis. A005-02 can be compared with generic exact DISTINCT within that same family; it is not a free extra search allowance.

No P0/P1/P2 semantic or arithmetic finding was confirmed in the frozen material. Remaining gaps below are explicit admission limits, largely already disclosed by the authors.

## Frozen scope and verification authority

The [input freeze](/tmp/tlab-wave005-skeptic-review-inputfreeze.json) captured actual contents and SHA256s **before analysis**, at2026-10-15T07:14:41.270724Z. All four match Root's expected identities:

- Features MD:99ef4ea1…; ledger:20d417c8….
- Models MD:71fa683c…; ledger:d7ff4ab8….

The freeze also captures four author-referenced tiny source artifacts after verifying their published hashes, plus immutable context from prior331b1ae29f3e484516893204a4f990c9372f2c25. This makes the ten-row and six-row arithmetic independently inspectable; summaries in the initial four documents alone would not reconstruct every update count. Author documents were not edited. Research/code-review skills were used, and a separate primary-source reader independently checked M5-01/M5-02 and legal closure.

Executed verification was bounded Python standard-library arithmetic over invented literals, AST extraction of a literal assignment without executing author code, exact Fraction arithmetic, JSON/schema checks and small research-document hashes. No project module, author script, SQL/DB, ML, source corpus, actual Q/C/Y, model artifact, heldout or paid job was opened/executed. Pure arithmetic pass is not native implementation acceptance.

## Primary-source check

The [DBSP2025 publisher record](https://link.springer.com/article/10.1007/s00778-025-00922-y) confirms8May2025 publication and compositional incremental-maintenance context. This extends an older DBSP line; no academic-newness claim follows. The author [distinct source](https://raw.githubusercontent.com/feldera/feldera/main/crates/dbsp/src/operator/distinct.rs) distinguishes positive-weight per-batch set conversion from incremental changes to accumulated distinct state. [Lifetime analysis](https://www.feldera.com/blog/time-series) makes retention depend on truthful ordering/append-only properties. [Issue1768](https://github.com/feldera/feldera/issues/1768) explicitly records three identical rolling input traces and links its May2024 completion. These support the author's limits; this review did not audit the completion patch or adopt Feldera.

The [DuckDB2025 article](https://duckdb.org/2025/02/10/window-catchup) and [current author source](https://raw.githubusercontent.com/duckdb/duckdb/main/src/function/window/window_distinct_aggregator.cpp) support the exclusion warning: `CanAggregate` requires NO_OTHER exclusion, empty argument ordering and additional aggregate eligibility. Consequently an EXCLUDE GROUP rewrite cannot assume that particular optimized path. Mutable upstream code is not the pinned project engine, and no installed-engine behavior was tested.

µWheel's [pinned plan source](https://github.com/uwheel/uwheel/blob/0ef74900d0facf62928c777dbaa7d9922ea6519f/crates/uwheel/src/wheels/read/plan.rs) was fetched successfully through the GitHub connector after web raw fetches failed. Its cost ranks aggregate operations; landmark cost6 and inverse-landmark child cost+8 do not include physical payload/build/I/O. The [trait](https://github.com/uwheel/uwheel/blob/0ef74900d0facf62928c777dbaa7d9922ea6519f/crates/uwheel/src/aggregator/mod.rs) defaults inverse toNone, and [Roaring implementation](https://github.com/uwheel/uwheel/blob/0ef74900d0facf62928c777dbaa7d9922ea6519f/crates/uwheel/src/aggregator/roaring/mod.rs) retains/merges bitmap payloads. The independent reader confirmed the2026-02-25 commit metadata and primary indexed paper's second-tick/u64SUM limits; direct fullPDF access remained unavailable. M5-01 correctly labels byte/build charging and sparse boundary replay as its own extension.

SUDAF's [2024 article](https://doi.org/10.1145/3649133) and [author bibliography](https://chaozhang-cs.github.io/) support canonical/derivable aggregate-state sharing and older2020 lineage. Direct publisher/full executable author-code access remains unverified. This is sufficient to retain a conceptual negative/application boundary, not admit a new implementation-backed mechanism.

## Per-candidate verdict and four fields

| Candidate | Four-field assessment | Verdict and falsifier |
|---|---|---|
| A005-01 | All four named fields appear in MD/ledger. | Refine/merge HYP046. Count intervals/prefix subtraction are exact for fixed boundaries and multiplicities; fail on any typed-output mismatch or higher complete cost than unchanged005. |
| A005-02 | All four named fields appear in MD/ledger. | Retain as a conditional suboperator. Last qualifying occurrence suffices only for append-only chronological prefixes. Retraction/time travel must reject; repeated versus unique controls must pay map/rank/expiry overhead. |
| M5-01 | All four present semantically; normalize ledger keys. | Refine/merge with A005-01. Algebra-gated flat/hierarchy/inverse selection is meaningful, but construction/payload cost must beat both unchanged005 and flat control. |
| M5-02 | Mechanism and negative falsifier present; no legal frozen-DSL speed prediction/benefit established. | Defer. Mean/variance are outside the frozen grammar; equal moments cannot recover exact DISTINCT, and author executable code is unverified. |

The fixed prior already owns generic shared DAG/CSE/cache under HYP046 and rounds012/033's strong unchanged005 control. These drafts correctly reject a slow direct-list oracle as the primary speed competitor. Neither source names nor a count of SQL calls creates new novelty.

Legal closure is41+3=44: B41 has11 prefix,16 nonratio,2 coverage,2 ratio,8 missing and2 suffix columns. R2/L05 adds three BIGINT item distinct-user counts: view24h,cart168h,purchase24h; no new window coverage or automatic missing column is introduced. This is a static registry/closure check, not a materialized44-column replay.

## Independent arithmetic and counterexamples

- Features fixture: all16 whole count-dictionary and16 DISTINCT-dictionary comparisons reproduce;15 boundary points; before anchor2 raw item views3 versus one distinct viewer; complete category denominator4 versus candidate-filtered3. Count/state truth was checked with separate interval and direct-list formulations. This does not exercise a rank-index implementation, generic expiry engine or all B41/R2 values.
- Models fixture: the ten-event/four-anchor counts, distinct and latest-peer metadata summaries reproduce. Three ranges each require three dyadic pieces: six query combines plus15 complete-tree construction combines=21, against18 flat combines. This is a deliberately unfavorable full-tree fixture, not proof that every hierarchy loses.
- Sixteen disjoint leaf IDs across five hierarchy levels yield80 retained memberships. Smaller compressed bytes remain possible for particular IDs; logical memberships are not measured allocations.
- Width-two expiry over times0,0,1 yields(raw,distinct)=(3,1),(1,1),(0,0). Two panes containingx have union cardinality1, not summed cardinality2; cumulative set subtraction loses a still-valid later copy. Last-occurrence state cannot recover an older copy after deletion of the newest copy.
- Six Fraction moment snapshots reproduce, including duplicate/NULL/boundary cases. There are15 non-NULL membership insertions/removals across the two windows: three shared accumulators give45 adds/subtracts; separate mean/variance accumulators give75. Queues, squaring, finalization, allocation, decoding and physical I/O are excluded, so this ratio is not speedup.
- Bags(0,0,3,3)/(0,1,1,4) share(n,sum,sumSquares)=(4,6,18), but DISTINCT2/3. No legal R2 DISTINCT rewrite follows from moment sharing.

The authors' temporal/metadata obligations are coherent: answer every anchor before all global equal-time peers; historical category counters retain their original event category; latest metadata combines the complete peer block including NULL; category denominators include off-C support; full-prefix recency/first-seen cannot expire with a seven-day counter. The tiny fixtures provide selected witnesses, not exhaustive proof of these obligations across physical output44.

## Physical-cost boundary and next decision

A005-01's P≤J(L+1)+1, S≤6E and dense G(P−1) counters are consistent bounds for the declared count grains. Group/key bytes, sparse predecessor lookup, metadata and sorting remain extra work. A005-02's D map entries plus live memberships still needs per-group rank state; O(P) cannot disappear behind O(D). M5-01 additionally acknowledges possible loss of the compiler's existing count/distinct shared scan. Both drafts correctly charge sink O(F), setup, sorting, validation, readback, failed attempts and cleanup, and separate logical combines/decodes from physical reads, process CPU, wall and peakRSS.

One consolidated source-free gate is sufficient: exact unchanged44-field closure, direct oracle, flat/generic state, optional hierarchy and last-occurrence contrasts; shifted anchors, repeat/all-unique, expiry, NULL, off-C and future/peer cases. The authors' proposed stop caps remain proposals. Passing selected algebra or a full tiny suite would not authorize the six future native invocations, reuse spent016, make source scope affordable or add a dependency to015. Only the coordinator owns canonical integration and any later reservation. B41/W/Q/C/source/heldout contracts remain unchanged.
