# Wave063 blind B FIRST — compact sibling compatibility

**Disposition:** zero new mechanisms. Refine existing TLAB-010/HYP-003/086 and `refinement-category-text-controls`; keep taxonomy/text optional and deferred.

**Mechanism:** three physical columns: weighted sibling mass S, weighted known-path coverage R, and one shared unusable flag M. Select distinct products viewed during `[t−7d,t)`, weight each by its last-view decay, half-life three days, and let W include every selected product. A sibling has the candidate's immediate parent, the same path depth, and a different complete path. S is sibling weight/W; R is known-path weight/W. If the candidate path is unavailable/one-component or W=0, both scalars are NaN and M=true; otherwise M=false. Unknown history contributes no supported sibling mass but remains in W.

**As-of boundary:** use the candidate's latest global product timestamp bucket strictly before t, including all peers. Bind historical text at each selected last-view timestamp. Conflicting ID→paths, missing codes, and known/NULL peer mixtures are unavailable; no older clean fallback. Record mapping-first-seen at each binding cutoff. Later-month recovery candidates cannot fill earlier paths.

**Analytical prediction:** keep all numeric IDs/events unchanged; exchange `p.b` and `q.c` between a viewed noncandidate product and an unviewed product, while the candidate stays `p.a`. B41, retrieval, all eight existing bundles, complete-code identity overlap, code multiplicities and tree shape stay equal. S changes 1→0; R=1 and M=false in both. This distinguishes cross-leaf compatibility, not English understanding. Consistent opaque renaming preserves S; pretrained-vector assignment needs its separate existing control.

**Nearest finite future experiment — UNRUN:** first ≤12 invented records for this pair plus missing/conflict/future-append cases; then exactly three fresh fixed-recipe fits on one separately reserved development domain: B41, B41+three true-tree columns, B41+three columns after one frozen depth-stratified leaf-path permutation. Keep Q/C, mature fullY, weights, estimands and B-relative Recall rule identical; permutation preserves code equality and masks. Complete preparation/fit/verification/failure cost is UNKNOWN, with no inherited 016 allocation.

**Goal benefit/counterhypothesis:** isolate whether sibling structure adds purchase-ranking information without recovering false names. B41 may suffice, coverage may dominate, or sibling preference may be wrong. No utility claim or current protocol/pool change follows.

---

## Analytical appendix — not executed

### Literal pair

Fix `t=2019-10-10T00:00:00Z`, one query for user `u`, and fixed `C={c}`. Each world contains these three view records. All times, actor/product/category IDs, actions and other numeric fields are identical across worlds. IDs are nominal opaque values.

| Time | User | Product | Numeric category | World A raw code | World B raw code |
|---|---|---|---|---|---|
| t−2d | v | c | alpha | p.a | p.a |
| t−2d | v | z | gamma | q.c | p.b |
| t−1d | u | h | beta | p.b | q.c |

No ID has multiple observed nonempty paths within either world. Each raw path is first observed at its row timestamp. Candidate metadata comes from its globally latest product bucket at `t−2d<t`; history product h is bound at its last-view bucket `t−1d`. This example supplies no dataset-level source coverage/maturity claim. A future fixture must declare complete seven-day source coverage separately; no labels are needed for the literal comparison.

The sole selected history product is h. Its weight is `w=2^(−1/3)>0`; hence W=w. Candidate c has parent p. In A, h is a distinct same-depth leaf under p, so `(S,R,M)=(1,1,false)`. In B, h has parent q, so `(S,R,M)=(0,1,false)`.

The source-level equality claim follows analytically from the pinned compiler: `manual_features.py` never references `category_code`; the eight generated bundles use the same numeric event columns. Every current compiler input is unchanged, including candidate category ID and its ambiguity/missing state. Product/user/pair/count/recency/distinct/coverage inputs and retrieval information are therefore unchanged. This is not an executed all-column fixture or empirical model result.

The product code multiset is `{p.a,p.b,q.c}` in both worlds. The observed prefix tree has two leaves below p and one below q in both. Complete-code equality of h and c is false in both; all complete-code equivalence relations are preserved by the global leaf-code bijection. Parent membership is the deliberately changed relation. Thus marginal hierarchy shape and exact code identity do not alone determine S.

### Prospective binding and closure

For a candidate, first identify the latest global product timestamp tau strictly below t. Inspect all product peers there. For a historical product selected by its last view s, inspect that product's complete timestamp peer bucket at s and retain the historical event ID rather than replacing it with the candidate-time ID. A path is supported only by a consistent nonempty raw code in the binding bucket and an unambiguous ID→path relation within that binding prefix. All nonempty paths per ID are retained; multiple paths are a conflict, never a majority vote. An all-NULL bucket is missing; a known/NULL mixture is ambiguous. Neither uses an older bucket or a later dictionary. A candidate prefix excludes t; a historical prefix includes its already observed event bucket s, with `mapping_first_seen<=s`. No future suffix can alter an earlier binding. These are proposed conservative text semantics, not a claim that the current compiler implements text resolution.

Let K_j indicate an available history path and A_j indicate sibling membership. For an available candidate with at least two path components and nonempty selected history:

`S = sum_j w_j*K_j*A_j / sum_j w_j`

`R = sum_j w_j*K_j / sum_j w_j`

Both have exactly the same unusable condition M, so the declared output is exactly two numeric scalars plus their shared Boolean flag. The no-known-history case has `(S,R,M)=(0,0,false)` and means zero *supported* sibling mass, with explicit zero coverage; it does not assert true incompatibility. Empty history or unavailable candidate has `(NaN,NaN,true)`. No extra auto-generated mask is silently assumed. Adopting this closure would require its own prospective schema/operator review because the current eight-bundle grammar cannot express it.

The finite literal stage would include the displayed pair, a same-timestamp known/NULL peer bucket, a conflicting ID→path, an empty history, and a future-only mapping. Its exact ≤12-row layout must be frozen before execution. No case was run here.

The future three-fit comparison has one fixed true tree and one fixed permutation among available complete paths within depth strata, shared by candidate and history mappings. The same permutation preserves duplicate codes, complete-code equality, known/OOV status, depth and the leaf/path multiset, while changing shared parents. It tests assignment of hierarchy relations to categories. It does not identify natural-language meaning or establish superiority over every hierarchy summary. A dense encoder contrast would separately preserve the vector multiset and permute ready vectors, as the existing HYP-086 refinement requires; that contrast is outside these three fits.

Freeze the permutation vocabulary from a strict past-fit snapshot. For this proposed comparison, a complete code outside that vocabulary is unavailable in both arms; no full-month string list, later-source enrichment or post-freeze vocabulary expansion is allowed. Event-time availability remains necessary even for a code already present in the frozen vocabulary. No IDF is used in this sibling-mass family.

Future cost must include strict-past mapping construction, timestamp peer resolution, history selection/weights, dictionary and join state, materialization of all three columns, three fits, score/metric verification, rejected attempts and storage. No measured cost, cap feasibility, new data download, model call, target look, runtime import, test, SQL or Git operation is claimed.

### Provenance and independence

Source version: `/tmp/tlab-wave063-shared-context-v2.json`, SHA-256 `54739939c34080e710e85b1013ef5207fc5c6127128205bc1a487b45ea25ede3`, prepared `2026-10-16T07:30:21.468014+00:00`. All 17 snapshot hashes were read and matched. Primary external works read: zero. No peer wave063 FIRST/pins/messages, helpers or canonical writes were used before this freeze. Root alone decides adoption. Existing optional branch and original task/deadline remain unchanged.
