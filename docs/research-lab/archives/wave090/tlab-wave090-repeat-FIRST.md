# Wave090 author A FIRST — purchase repetition is not prior-any-event familiarity

First actual clock observation: **2026-10-17 03:42:50 UTC**. This is an observation after dispatch, not a reconstructed exact research start. Source checkout observed at `7cc04e02b5169583a08dc790b3d823925fd80199`. Exact local SHA-256, byte lengths, filesystem permissions, Git modes/blob identities, and primary URLs are in the accompanying `-pins.json`.

**Disposition proposed: NEW 0, two refinements, ADMIT 0.** No canonical IDs, tasks, gates or grants are requested. These are independent mechanism-specific refinements of existing TLAB-004/006/007/014 and HYP-004/direct-history policy, with the second informing HYP-002 / TLAB-016/019. They do not establish a current actionable retrieval bottleneck or a quality gain. All experiments below are **UNRUN**; proposed budgets are ceilings with adequacy **UNKNOWN**.

## Blind scope and current state

I formed these proposals without reading any wave090 peer output, peer discussion, skeptic draft, or other wave090 artifacts. I read the canonical queue, research index/journal, historical candidate implementation/contracts, earlier author/review dispositions and accepted historical reports. The queue is `docs/backlog.md`; this FIRST is not a parallel queue. No project imports, data/DB/model/SQL/native execution, tests, fits, inference, dataset download, network writes, Git mutation, issue or allocation occurred. Only the three assigned temporary artifacts are written. Root alone coordinates, publishes and commissions later critique.

The supplied current boundary is retained: seven audited fixes / 89 unique synthetic methods and finite QYC/F/Prepared accepted; corrected ordinary native CLI, callback-abort and cold-shell remain UNRUN. Science and old native allocations are CLOSED; remainder UNKNOWN. The proposed one-attempt 50 CPU-s / 65 wall-s, one fit of at most eight synthetic trees, is a pending human question and is not borrowed here. Historical final B=.459825 / W=.464947 with CI crossing zero and adaptive 1189/403 on reused selection remain historical/exploratory. Fourteen of nineteen accepted, 014 continuous, 010–013 optional/deferred. Wave090 original due 03:45 UTC / 06:45 MSK on 17 October; next original 04:30 UTC on the unchanged 45-minute grid. Deadline 25 October 23:59, timezone UNKNOWN, unchanged.

## What the actual implementation identifies

`create_candidates` in `scripts/candidate_pilot.py` reads events and Q, validates the no-refill union contract, counts distinct purchase-users in `[t−168h,t)` for popular200 and ranks each user's distinct products by the latest **view/cart/purchase** in that same window for recent20. Product ID only breaks ties. Purchases are retained; source overlap is deduplicated without refill. C is materialized before labels are joined, and an independent strict-past catalog check verifies C⊆U(t).

`create_labels` in `scripts/anchor_pilot.py` constructs full distinct non-NULL purchase Y for mature horizons. Its `pair_seen_before` is computed from **any event type** for the pair over the observed source prefix, not purchase events and not merely seven days. `coverage_report` names this field's slice `repeat_targets`. The existing candidate and heuristic reports explicitly state the same semantics. Consequently the historical 71/73 retrieved repeat-pair targets and 70/73 recent top20 hits are about prior-any-event familiarity. They do not measure repeat purchases. This is a semantic limit already disclosed in the reports, not a newly found implementation bug.

Historical new-pair targets in that pilot have 21/48 in C and 6/48 in recent top20; this records losses at both stages for that exact small development sample. It does not identify the effect, cost or feasibility of a replacement source, nor a transferable split on future dates. The full-Y ceiling from waves073/086 and frozen-score knockout from087 remain useful accounting. Neither is independent evidence that the largest actionable improvement lies in retrieval. Cold-outside-U, omitted known items, weak ordering of retrieved positives, and quota displacement require different interventions.

## Primary reading and transfer boundary

- [RepeatNet, Ren et al.](https://irlab.science.uva.nl/wp-content/papercite-data/pdf/ren-repeatnet-2019.pdf), §3: mode probabilities depend on the observed session prefix; repeat and explore decoders have different item supports. The running target is the next click. Its joint-mode-loss discussion also cautions that membership in past history need not identify the generating mode. I borrow the separation of supports, not its neural architecture or a claimed purchase gain.
- [Li et al., A Next Basket Recommendation Reality Check](https://arxiv.org/html/2109.14233v2), §5.1: repeat/explore accuracy is evaluated on corresponding target subsets; §5.5 stratifies by repetition ratios. A ratio computed from the ground-truth basket is a retrospective analysis variable. Their basket protocol does not make it an available feature for our midnight query.
- [Li et al., TREx](https://arxiv.org/html/2405.01143v1), §5: separate repeat scores include item and user components and a threshold determines repeat admission before exploration fills remaining positions. Its evaluation critique warns that attractive aggregate and beyond-accuracy results can coexist with weak exploratory utility. This motivates conditional audits; it does not license a calibrated threshold or replenishment interpretation in REES46.

No order ID, stock, current completed basket or future purchase time is available in our contract. October-prefix absence is left-censored observed history, not proof that a customer never bought the item.

## Refinement 1 — semantic aliasing can select the wrong remedy for an identical ceiling

**Existing homes:** TLAB-004/006/007/014, HYP-004 and candidate-generation/03 direct-history policy. Not a new repeat model. The full-prefix purchase-source idea already exists in03; RB3 already refines item-repeatability admission. This proposal instead sharpens the *diagnosis that would justify choosing between those remedies*.

**Mechanism.** Let A_q be products with any own event before t; P_q products with an own purchase before t; U_q all globally observed products before t. P_q⊆A_q⊆U_q. Partition each identifiable full-Y target into four disjoint types: P_q (observed purchase repeat), A_q\P_q (familiar, never observed bought), U_q\A_q (new personal pair), and outside U_q (catalog-cold). The existing binary repeat flag merges the first two. Within the first two, mark whether there is eligible seven-day history and, if so, whether recent rank exceeds20. These are different source failures, not interchangeable names for exploration.

**Counterhypothesis.** The disclosed any-event split is sufficient for the practical choice because genuine prior-purchase omissions are negligible, purchase-prefix coverage is too short, or a longer purchase source costs more and displaces stronger candidates. A mechanically clearer partition need not improve ranking or justify extra computation.

**Precise falsifiable prediction / smallest legal experiment.** Two isolated invented worlds; one predeclared query `(u=1,t=2019-10-10 00:00 UTC)` each; four events per world, eight row instances total. Current clock48h candidate settings remain popular200/recent20/no-refill. Use item a=101, b=202 and external user v=2:

| Event UTC | User/item | World P | World V |
|---|---|---|---|
| Oct1 00:00 | u/a | purchase | view |
| Oct9 00:00 | v/b | purchase | purchase |
| Oct9 23:00 | u/b | view | view |
| Oct10 01:00 | u/a | purchase | purchase |

Supply Q independently of labels, with unique query ID and declared complete calendar/maturity premises; this is a candidate semantic fixture, not proof of production hash sampling. Call actual `create_candidates` with no label table, then catalog verification, then independent target construction. **Prediction, not observed output:** both worlds give U={a,b}, C={b}, full Y={a}, any-event-repeat=true, identical zero retrieval Recall and zero fixed-C NDCG ceiling. Purchase-repeat=true only in P. A separately defined full-prefix purchase list contains a only in P, while a seven-day purchase list contains a in neither world. Thus identical current ceilings and existing repeat flags cannot distinguish an old-purchase omission from an old-view omission.

Exact nearest-test units: two candidate builds, two catalog checks, two post-C label constructions, two query outputs/eight physical event rows; zero fits, scores or real-data reads. A may be inserted only by the separately specified historical source, never by consulting Y. This toy does not compare equal-size treatment pools or show source superiority.

**Budget / decision.** Proposed isolated source-fixture ceiling: 10 CPU-s / 30 wall-s / 256 MiB RSS, one worker, zero ML. Adequacy UNKNOWN; existing unrelated canary timing is not a measurement of this fixture. Accept only the diagnostic refinement if exact sets/flags above hold and source masks derive strictly from `<t`; reject the proposed witness if actual source contracts contradict any predicted row. If masking uses Y or wrong history scope, repair before accepting. Any future real-source screen requires a separate bounded authorization and complete scan/state/cost contract; do not infer support from this toy or reopen reserved data.

**Benefit to Task1.** Prevents spending automation effort on repurchase timing when the deficit is familiarity/exploration, or crediting a generic recent feature as replenishment learning. A reusable typed audit can attach observed-prefix action semantics to generated features without modifying fixed-C B/W or adding a new model family.

## Refinement 2 — a future repetition-ratio router can manufacture an unavailable automation advantage

**Existing homes:** HYP-002 / TLAB-016/019, TLAB-006/007/014 and existing repeat-source policies; merge with the established proposer-information/chronology and source-allocation contracts. This is distinct from refinement1: it tests policy information availability, not the meaning of a target's history flag. No claim that the current pipeline has this leakage.

**Mechanism.** A set-valued next24h target may contain both repeat and explore purchases. An oracle future ratio rho_q=|Y_q∩P_q|/|Y_q| cannot choose repeat/explore quotas, feature templates or scores at t. A legal policy may use candidate-level past membership and a prefix-predicted ratio fitted on sufficiently mature earlier outcomes; it must give the same decisions for an identical prefix and frozen fitted state. Historical mode-specific metrics may guide a prospective design, but using the evaluated query's ratio as a gate changes its information boundary.

**Counterhypothesis.** Prefix features already predict enough mode variation, and ordinary B41 interactions capture it; explicit routing adds nothing after full-B alias removal. The toy below establishes an information limit only, not absence of statistical predictability or impossibility of a useful learned router.

**Precise falsifiable prediction / smallest legal experiment.** Three isolated worlds share these three prefix events: u1 purchase a101 on Oct8 00:00; v2 purchase b202 on Oct9 00:00; u1 view a101 on Oct9 23:00. Same t=Oct10 00:00 and current candidate config. Their suffixes are respectively u1 purchase a at01:00, purchase b at01:00, and purchases a and b in the same01:00 peer bucket. Three copies of the three-row prefix plus four suffix rows = **13 row instances**, three Q, three actual candidate builds and three later label constructions. No fitted router or model is needed.

**Prediction, not observed output:** C={a,b}, prefix P={a}, A={a}, candidate history masks and every deterministic frozen past-only decision are equal across all three worlds. Post-C Y sets are {a}, {b}, {a,b}, giving oracle ratios1,0,1/2. A proposed gate reading that ratio must change or otherwise depend on unavailable labels; a legal prefix implementation must remain invariant. The mixed world specifically falsifies the simplification that every query has one exclusive repeat/explore class. Same-second suffix order changes no sets and supplies no observed ordering.

For future fixed-C feature evaluation, retain original full Y, K=20, full-Y IDCG and the same positive-query cohort. Report mode-specific target counts/hits and **additive DCG contributions divided by the common full-Y IDCG**, whose sum recovers total NDCG. Do not average separate mode-normalized NDCGs or drop mixed/off-C queries and call it the original estimand. Candidate ceiling attribution remains total/full-Y bookkeeping; a single ideal-order ceiling need not decompose into independently attainable per-mode optima.

**Budget / decision.** Proposed source-fixture ceiling: 10 CPU-s / 30 wall-s / 256 MiB RSS, one worker; zero ML/real-source access. Adequacy UNKNOWN. Accept the chronology refinement only if equal prefixes produce exactly equal C/masks/legal decisions while label-derived ratios differ as specified. Reject any candidate router that fails this invariance before considering quality. A learned past-only router needs its own mature-training/build-availability contract, matched compute/tuning and genuinely future evaluation; no new experiment or grant is admitted here.

**Benefit to Task1.** Makes a repeat/explore automation proposal portable as a declared temporal contract rather than a hindsight-specific trick. Candidate masks are legal, reusable annotations; prior-purchase7d indicators may already be functions of B41, so alias checks precede extra features. The current eight-bundle grammar, B/W outputs and final table remain unchanged.

## Deduplication and stopping decision

Already covered and not proposed anew: adding recent/history sources (03), item repeatability and threshold-fill (RB3), probability-derived category quotas (RB1/HYP-053), full-Y fixed-C ceilings (073/086), frozen-score source knockout (087), source completeness (087), and adaptive-selection validity. Two mode-specific reports do not create independent evidence from the same targets. No RepeatNet/TREx fit, new quota grid, data download, refreshed final test or extra mandatory Task1 gate follows.

The actionable decision now is **retain current Task1 comparison; qualify the meaning of historical repeat and bottleneck language**. These source-only falsifiers could cheaply reject a semantically wrong future design under separate authorization. Whether either refinement changes a useful retrieval or feature policy on actual data, its support, downstream gain, transfer and total cost are UNKNOWN. Freeze this FIRST and wait for Root's separate skeptic; no further author work or peer reading follows this submission.
