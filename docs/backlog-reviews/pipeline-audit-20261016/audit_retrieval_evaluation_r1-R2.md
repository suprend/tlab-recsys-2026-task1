# R2 crossed review — candidate FIRST

Peer: `audit_candidates_r1-FIRST.md`, SHA256 `9aecc38c843fc5c471543753a9a01dd98076c68abf9c279eab723a5255c1b9d0`. Peer report/pins freeze and all36 peer source hashes verified. Own FIRST/report pins remain byte-identical. Frozen HEAD/manifest unchanged; original source paths map to `/Users/mdpospelov/tlab-recsys-2026/`.

## Verdict

**No new confirmed implementation defect.** Peer no-findings survives the requested adversarial cases within inspected scope. One concrete correction is needed in its proposed check, not in production code.

**Oracle proposal clarification, peer FIRST:41.** The literal `create_queries → create_candidates → create_manual_features` sequence is incomplete: `anchor_pilot.py:187` inserts `label_is_mature=None`; candidate validation `:26–32` rejects NULL maturity before producing C. Normal `build_pilot` calls `create_labels` between these functions (`anchor_pilot.py:291–293`), intentionally reading future target outcomes. For a no-Y tiny oracle, explicitly set calendar-only maturity from declared horizon/source bounds, as the existing reachability test already does (`tests/test_candidate_reachability.py:91–102`). Alternatively test the actual wrapper, allowing independent target creation and coverage reads, while asserting no outcome dependence in Q/C/F values. “No Y access before C/F” should be scoped to pure retrieval/materialization calls, not the whole pipeline. No runtime failure was executed here.

## Counterexamples checked against source

- **Duplicates/NULL/ties:** popularity excludes NULL users/items and counts distinct buyers (`candidate_pilot.py:61–70`). Recent groups by query/product before cap20 and ranks maximum time DESC/ID ASC (`:72–78`); repeated views cannot consume20 distinct slots. SQL does not discard valid0/negative IDs. Global peers at t are excluded; lower bound is inclusive. Peer permutations do not introduce an ordering inside a timestamp bucket.
- **Union:** with P={p1,p2}, R={p2,r1}, actual C has3 items, not quota4. p2 retains both flags/ranks; r1 receives its full buyer count even outside popular top-list (`:82–95`). No refill is deliberate. Recent retrieval20 is distinct from the ItemCF latest21/self-excluded history20 rule (`itemcf_projection.py:103–109`); changing one cannot be called the same experiment.
- **Fixed C:** anchors are iterated separately (`candidate_pilot.py:55–60`); pools may change daily/per user. Fixed means exact identical Q/pair set between compared feature branches, not one monthly item list. Collection checks compare C/F keys and retrieval columns (`development_collection.py:405–417`), supporting the peer claim.
- **Context availability:** manual metadata selects last global time<t, resolves known+NULL ambiguity, and leaves historical event-category keys attached (`manual_features.py:124–143,175–205`). Q maturity is not exported through manual pair columns (`:170–172`). Feature/model schema carries retrieval context (`feature_programs.py:19–24,53–66`); it is shared B input, not newly discovered automation. Event-time availability remains an explicit assumption, not verified ingestion latency.

## Retrieval proposals

Peer HYP004/031 refinements remain existing hypotheses, not executed wins. Gained hits alone are insufficient: C₀={a,b}, C₁={b,c}, Y={a,c} has gained1/lost1/net0 despite a useful-looking new source. Equal quotas also do not ensure equal actual |C|; freeze matched-size source order before Y and retain native-policy results. Publish both estimands, U→C→top20 integer counts, cold/new/repeat partitions and size/work ledger. Equal |C| does not equal source-build cost. These refinements align with my FIRST diagnostic gap; they do not grant fits or a fresh final reservation. Cost/budget UNKNOWN/CLOSED; no new ID needed.

Static text/hash/readback only. No tests, project imports, SQL, raw data, models, native/ML execution or scientific runs. Optional083 drafts were not needed or read. FIRST immutable; R2 frozen; STOP.
