# R3 batching regression v1 — independent SOURCE review

**SOURCE BLOCKED: one confirmed fixture defect; do not execute v1.** Candidate SHA256 `4608abf379eab7fc091c20fc8fb56a805063ad65018aaadd480f882968e0d965`; combined manifest `d78611b5190f69a7fc33ce09e0a92ff79cd5c0b0c59013aac77e651c4319c27b`. Inspected full new test/contract metadata and relevant combined compiler, protocol and independent rich-schema helper sources; exact pins attached. No project execution occurred.

## Confirmed P2 — make protocol caps cover both declared days

`tests/test_feature_batch_invariance.py:204-206` and`:258-260` declare `[Oct10,Oct12)` with `max_users_per_day=3`, but `max_anchors=3/max_candidate_pairs=660`. Actual `create_manual_features` calls `validate_protocol` immediately (`scripts/manual_features.py:158`), whose`:138-142` requires anchors≥days×daily cap and pairs≥anchors×220. Concrete static witness:2×3=6>3, so both methods raise `ValueError('Anchor budget is smaller than the declared daily sampling cap')` before any materialization/invariance/mutant checks. Raising only anchors to6 would then fail1320>660 at the next gate.

Expected: reach all schedules and explicitly wrong numeric mutant witnesses. Actual: protocol refusal is outside the intended expected-AssertionError blocks. Fix the **fresh version** in both sites to caps6/1320 while preserving the actual3Q/5C/22-event fixture. These are declared potential-budget metadata, not new actual rows, runtime allowance or a scientific grant. Keep v1 immutable; this review did not change it.

## Conditional trace of the remaining logic

After that repair, the normal method invokes actual compiler SQL (`:125`) through nine registries and three schedules. Each schedule has a private connection; successive calls reuse it. Whole-call anchors sort FIRST→SECOND, while split schedules begin SECOND and later revisit FIRST, providing real stale-TEMP/order pressure. Full keyed45/48-field scalars compare exact types/NULL/values; every bundle preserves B45 and its three extras use independent row/set arithmetic (`:71-92,220-240`). Helpers supply literal schema/semantics, not producer expected values. Imports of the rich helper only define its unused tests; no model loader/body is called.

Both negative controls are **discriminating source/state mutations**, not fake output-vector corruption:

- Candidate-conditioned denominator (`:265-280`) adds a real candidate-item SEMI JOIN only to category aggregation. At A/category100, ITEM supplies one view; noncandidate90 supplies three within-window views. The excluded earlier row does not count. Correct denominator4/share1/4 becomes denominator1/share1.0. The mutant must first produce those explicit wrong numbers, then fail the same independent literal oracle.
- Stale metadata (`:284-310`) executes the first anchor's actual metadata query, then skips its replacement. FIRST's ITEM category100 survives at SECOND instead of clean200. At SECOND, category100 has ITEM's old view plus one recent noncandidate90 view: denominator2, numerator1, ratio1/2. Normal200 has four views, including two noncandidate80 views: ratio1/4. Explicit category100/2/0.5 checks prevent unrelated exceptions/schema failures from counting as detection. Proxy delegation/close remains real.

## Coverage limits, not additional blockers

Only one query per anchor has nonempty C. The schedules therefore do not change the same-anchor candidate-item union; candidate-conditioned denominator bias is detected by literal gold, not by a demonstrated metamorphic batch difference. A future fixture with two distinct nonempty Q at one anchor could strengthen that axis without changing the present claim's finite scope.

The22 source rows are below24; total event+Q+C inputs are30, so a future grant must state which bound it means. No Y relation is created; named-label absence is asserted and the compiler path calls no target builder. Fixed C does not prove retrieval/Y lineage. Future peers/suffix and independent extras exercise strict-time cases, but this body is not a full future-suffix comparison or independent arithmetic oracle for every B45 field. In particular, do not infer exhaustive pre-source exclusion proof from one pre-source row plus metamorphic equality.

AST parse and candidate/freeze/basepins/combined hashes verified. Intended bounds56 compiler calls/76 anchor batches/29 connections are source counts, not observations. CPU/wall/RSS/cleanup cost UNKNOWN; tests/imports/SQL/native/ML/data reads UNRUN. No canonical/Git mutation. Recheck corrected caps and unchanged mutant witnesses in v2 before any separately authorized bounded CODE run. Freeze/readback then STOP.
