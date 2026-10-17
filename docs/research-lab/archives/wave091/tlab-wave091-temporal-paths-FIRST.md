# Wave091 independent FIRST — temporal paths, roles and selector population

Bounded SOURCE-only author A. Recommendation: **two refinements of existing IDs; NEW 0, ADMIT 0**. Neither proposes a new quality mechanism or necessary completion gate. Generic strict-past, known-availability, peer exclusion and maturity requirements duplicate rounds013/022/048 and are not counted again.

Primary orientation: [Hippasus v1, §§3/6/7](https://arxiv.org/html/2602.02025v1) explores acyclic table paths without revisiting a table, ranks using semantic scores plus coverage/uniqueness/size ratio, and preserves base rows using first-occurrence deduplication. [V2, §§4.2/4.3](https://arxiv.org/html/2602.02025v2) retains these path/join contracts while changing semantic routing and feature selection. Its adaptive method is not attributed to v1. Neither provides our query–candidate/full-purchase-target contract. Frozen provenance and Root bibliographic acceptance were read and hash-verified; embedded PVLDB DOI is not attributed to Hippasus. Implementation/artifact/license/reuse readiness remains UNKNOWN.

Current source: feature_programs.py fixes nominal user/item roles, strict-past raw-event context, six supported grains through manual_features.py, and only reviewed count/distinct/recency templates. It does not implement arbitrary relational paths or the following nested aggregate. manual_features.py preserves exact (query_id,product_id) identity and aggregates source roles before joining C; candidate_pilot.py constructs C before opening fullY. Thus these are future transfer specifications, not findings against installed code.

## 1. Table acyclicity versus repeated semantic roles

**Dedup:** refine HYP-011 within HYP-002/HYP-046, TLAB-005/016. Round001 already proposes user→distinct viewed items→global item state→user reference; rounds011/013 specify grain/multiplicity. The delta is an explicit reachability falsifier for transferring Hippasus’s table-node path constraint, rather than another temporal predicate.

**Mechanism:** the raw-table expression needs Events twice: user→Events(history views)→Item→Events(global views). Reusing a physical table in two roles need not create a cyclic semantic computation. A table-name visited set rejects this expression; role-unrolled aliases or an explicit preaggregated ItemState can represent it. This does not establish that expanding paths improves ranking.

**Counterhypothesis:** table acyclicity intentionally defines a narrower feature space; supplying ItemState already solves the representation problem. Aggregation is also outside default JEX’s first-row semantics, so failure cannot be blamed solely on path enumeration.

**Falsifiable prediction / smallest exact future experiment, UNRUN:** set t=2026-10-10T00:00:00Z, h=w=24h, with six distinct row instances: (u1,p10,view,t−4h) twice; (u1,p20,view,t−3h); (u2,p10,view,t−2h); (u3,p10,view,t−1h); (u2,p20,view,t−1h). Every row is known before t under the declared event-time assumption. Freeze Q={u1,u3} at t and C={p10,p20} per query, independent of labels. Global V10=4,V20=2; D1={10,20},D3={10}. For existing HYP-011’s mean-log reference, A1=(ln5+ln3)/2 and A3=ln5. Candidate contrasts are (½ln(5/3),−½ln(5/3)) for u1 and (0,ln(3/5)) for u3. Event-weighting D1 instead yields (⅓ln(5/3),−⅔ln(5/3)), exposing a separate bag/set mistake.

Freeze three specifications: physical-table acyclic enumerator, role-unrolled enumerator, and explicit preaggregated ItemState enumerator. Hold the independent aggregation definition fixed; record reachability separately from four scalar comparisons. Add one excluded global peer at t and one future row solely as noninterference variants; reverse input order. Scope ≤8 source rows, 2Q, 4C, three representations, ≤24 scalar comparisons; no ranking/model test. Proposed cap ≤10 CPU seconds/20 wall seconds/128MiB RSS/64KiB scratch, 0 fits/API; cost and adequacy UNKNOWN, not granted.

**Rule:** accept this refinement if the role/raw expression is excluded by the physical-table specification but alias/preaggregation versions reproduce the literal values and invariances; otherwise reject the proposed reachability counterexample or mark ambiguity inconclusive. Any parity claim must separately pass set/bag semantics. Task1 benefit: state precisely which existing automation family a relational proposer can express, without presenting endpoint/table-name matching as semantic coverage. The query-constant subtraction still does not improve standalone popularity ordering.

## 2. Path coverage has a candidate-row measure

**Dedup:** refine HYP-002/HYP-046 and TLAB-004/005/006/016; wave089 already distinguishes row training risk from query/fullY evaluation. Delta: a concrete label-free PEX path-priority reversal, before training, caused only by candidate multiplicity.

**Mechanism / counterhypothesis:** coverage over base candidate rows weights q by |Cq|. Counter: that population sensitivity is intentional and may help the downstream learner; query-balanced coverage is not automatically superior or a mandatory invariant.

**Prediction / smallest exact future experiment, UNRUN:** freeze two mature positive queries qA,qB at t, fullY_A={a},fullY_B={b}, and two one-hop paths with equal frozen semantic scores, one-row lookup tables known before t, and uniqueness=1. Base path-A FK is non-NULL exactly on qA rows; path-B FK exactly on qB rows. Policy0 has C_A={a},C_B={b,c,d}; policy1 adds e,f,g to C_A only. All added items are strict-past eligible nonpositives, with supplied scores below original items; a and b rank first. No C change is proposed for the canonical experiment.

PEX coverage changes A/B from 1/4 versus 3/4 to 4/7 versus 3/7. Size ratio is identical across paths within each policy (1/4 then1/7); with default weights, Score(A)−Score(B) is −1/12 then +1/42. Query-averaged coverage stays 1/2 each with a fixed tie rule; both queries’ supplied fullY-normalized NDCG remain1. Test exactly 2Q,2 fullY memberships,7 unique candidate items/11 policy memberships,2 lookup rows,4 path scores,4 query metrics; no fit. Proposed cap ≤5 CPU seconds/10 wall seconds/128MiB/64KiB scratch; cost/adequacy UNKNOWN, not granted.

**Rule:** agreement supports only the possible selection-measure reversal; disagreement rejects the arithmetic/specification. Declare the selector population and freeze C before any transfer comparison; do not infer utility, leakage, or an obligation to replace PEX. Task1 benefit: avoid treating row/target-distribution preservation as preservation of the query-macro decision problem.

READY for separate skeptic review; STOP after immutable hash/readback. No helper, peer FIRST, current091 discussion, raw data, SQL, tests, models, installation, API execution, project writes, Git mutation, new queue, gates or grants.
