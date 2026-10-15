# Independent cross-review of Retrieval B by Retrieval A

15 October2026. Read RB’s frozen report/ledger only after freezing RA’s first draft. Reviewed canonical HYP053/054, recent-repeat, ItemCF, graph/multi-interest and fusion contracts, plus the four primary papers. A helper independently checked SPARC/CAPTS. No author files, shared repository files or Git changed; no actual data/DB/Y/model/native job/fit/download/API inference. One tiny literal combinatoric check ran: RB2’s pair counts/degrees are equal and its ab completion differs. This is correctness evidence for the example, not purchase evidence.

| Candidate | Disposition | What survives |
|---|---|---|
| RB1 | **refine**; literal gate only | Mass-dependent quota allocation is a narrow HYP053 refinement; learned SPARC deferred. |
| RB2 | **accept-needs-pilot**, merged with RA-02 | Exact conjunction beyond pairwise projection survives as one new mechanism; not two independently new ideas. |
| RB3 | **refine**; real-source gate deferred | External item repeatability can be a distinct admission statistic, but recurrence calibration and threshold/fill policy remain unresolved. |
| RB4 | **refine**; reject unobserved-output oracle, defer that equal-call pilot | Either lawful on-demand routing or fully paid cached-result admission; those are different experiments. |

None is an execution approval. Current C, model procedure and closed actual heldout remain unchanged.

## RB1 — quota allocation is source-supported, but its implementation is an adaptation

[SPARC §3.5](https://arxiv.org/html/2508.09090v1#S3.SS5) supports multiple code-conditioned retrieval paths and probability-based quotas. It does not specify largest-remainder rounding or isolate that rule as an independent ablation. Its sampled positive+99-negative protocol cannot establish full-Y candidate Recall. No verified author implementation was found in the inspected primary material; do not imply code reproduction.

Canonical HYP053 fixes top3 category lists and20/20/20 slots, so **varying only their quotas using past mass** is a real, narrow contrast. Merely replacing categories with codes is not new. HYP068’s score pooling does not by itself decide quotas, but neither licenses a new generic multi-interest family. Freeze p’s exact estimator, selected-category normalization, missing/zero policy and availability before downstream rows. Literal probabilities alone authorize only a mechanical fixture. A past category-share proxy is feasible but is not a calibrated probability of buying within24h.

**Exact cheapest falsifier:** scale the quota to6; list A=a1…a6, B=b1…b3, C=c1…c3, deterministic tie B<C. Mass(.8,.1,.1) must give(5,1,0), fixed quotas(2,2,2), hard top-interest(6,0,0). Mass(.34,.33,.33) must give(2,2,2). Identical lists in all interests must underfill after dedup, with no deeper fetch. Twelve literal IDs,0fits/0Y. RB’s original60-slot/≤12-ID example is useful for arithmetic but can easily hide the admission contrast behind exhausted lists; the scaled fixture avoids that.

**Matched control:** same ordered lists, p, selection masks and fetch semantics; mass quota versus equal quota. A hard-top-interest arm is a separate contrast because it normally makes fewer retrieval calls. Charge all list materialization and inspected IDs: fetching top60 from all three lists costs180 IDs even if only60 are admitted. Native and size-matched results both remain necessary.

## RB2 — valid separating example, one shared RA/RB hypothesis

[NPA §§3–5](https://arxiv.org/html/2401.16433v1#S3) learns combination-pattern/context representations for basket/playlist completion. The paper supports pattern conditioning, but does not prove RB’s exact-count surrogate or our next24h purchase estimand. The report correctly declines random partial-basket splits, present-item exclusion and semantic complement claims. No NPA author code was verified in this review.

RB’s worlds A=`abc,ade,bdf,cef`, B=`abd,ace,bcf,def` have identical pair counters, item degree2 and session degree3. A tiny literal calculation confirmed this. With prefix ab, A has abc while B has abd. Equal-weight incidence projections and degree-normalized two-hop item projections therefore coincide; exact triple supports differ. Say **these specified pairwise projections**, not every conceivable hypergraph representation: learned weights or nonlinear encoding may already inspect triple identities.

This is substantively the same mechanism as RA-02 despite different papers and letter renaming. Merge provenance and retain one conjunctive-completion hypothesis. It is distinct from existing ItemCF/walks and NB-F03’s pairwise action/category relation. HyperHawkes linear propagation alone is not an implementation of it.

**Matched control:** identical admitted historical triples, support/weights, prefix seeds and leave-query-user-out provenance; exact two-seed firing versus pairwise projection. Fix action type once, e.g. view; do not mix all actions while also changing the conjunction. Require minimum distinct external-user support, or expressly state self-inclusive semantics in both arms.

**Exact cheapest falsifier:** RB’s eight sets, pairwise equality, exact ab completion, within-bucket permutation/duplicate invariance, and suffix-at-t rejection. This fixture already passes algebraically; an implementation still has to pass it. Session sets must remain observed proxies: they do not identify orders, current cart state, complements or substitutes. At query only the latest observed prefix is available; source training sets cannot be completed using later suffixes.

**Before real source access:** resolve “at least two” versus subsets≤45. With10 prefix items,45 covers pairs only; all subsets of size≥2 number1013. Declare exactly two antecedents/triples for the first gate. Add separate caps on admitted raw rows, sessions, distinct items/session, stored keys/memberships and intersection/postings work. Output60/100queries alone bounds none of those. Overflow must stop or mark source unsupported according to a frozen policy, with discarded-session coverage reported.

## RB3 — observational repeatability survives; calibrated recurrence does not

[TREx §5.1–5.3](https://arxiv.org/html/2405.01143v1#S5) multiplies item-specific repetition and user-interest scores, thresholds repeat candidates and fills remaining places with exploration. The [author code](https://raw.githubusercontent.com/lynEcho/TREX/main/repetition/repeat.py) confirms separate item and user factors and a `no_item` ablation; its original basket input is not REES46. RB’s fraction of external users with≥2 purchase-seconds is its own simpler statistic, not the paper’s powered-frequency formula or calibrated posterior.

The narrow delta is real if the item prior changes admission while identical user purchase histories, recency/frequency, support masks and candidate eligibility are held fixed. It refines repeat-history retrieval; it does not duplicate NB-F02’s elapsed-time residual survival. However, buyers observed early have more opportunity to repeat than late entrants. Same-second dedup removes exact counting ambiguity but not retries on later seconds. October left censoring and administrative follow-up therefore limit interpretation to a fixed-window historical fraction.

**Matched control:** identical repeat support, user score, threshold/fill algorithm and exploration list; item-specific prior versus one common past pooled prior. Give both arms the same missing/low-support mask and record denominator/risk-age support. No threshold grid. Define the final score scale before freezing a threshold; “threshold0.5” is not portable across user-frequency multipliers.

**Exact cheapest falsifier:** the advertised .8/.1 fractions cannot be realized with only four total users. Use query user q with one purchase of each SKU, and three external users with purchase-seconds (a,b) counts(2,1),(2,1),(1,2): eleven records total, priors2/3 and1/3 after self-exclusion. Swap external a/b records, leave q unchanged; threshold1/2 with common user factor1 must swap admission. Add duplicates, same-second ties, zero denominator and q-only support. This stays within the proposed12-record cap.

Clarify the exploration-fill policy: dynamic fill within a fixed precomputed60-list may be legitimate if predeclared; scanning deeper after overlap is refill. Bound repeat evaluations≤20 **plus** all60 exploration IDs, distinct-user prior state and source rows scanned. Until these semantics/global ceilings exist, defer the real-source pilot. Do not infer “replenishment” from this fraction.

## RB4 — exact marginal uniqueness is unavailable before retrieval

[CAPTS §§3.2–3.3](https://arxiv.org/html/2602.12564v1#S3.SS2) predicts trigger/channel value and uniqueness, routes triggers, then retrieves. Exact output overlap constructs offline supervision. Its nearline cache stores long-term triggers/scores, not all seed×channel result lists. Its uniqueness concerns channels of a trigger, whereas RB’s greedy marginal yield also compares different seeds. RB’s cheap policy is an adaptation, not the published inference method.

**Exact cheapest falsifier:** after calling h1→{a,b}, two worlds have indistinguishable available inputs. A: uncalled h2→{a,b}, h3→{c,d}; B: uncalled h2→{c,d}, h3→{a,b}. With no cached outputs, identical router features/results/seed must produce the same second call. Choosing h3 in A and h2 in B while billing only two calls proves hidden-output access. Literal lookup stubs should log every cell and ID inspected. No fits/Y are needed.

**Two lawful refinements:** (a) on-demand selection uses only prior features or frozen predictions; learned value attribution requires mature historical outcomes and separate fits; or (b) all candidate cell outputs are genuinely cached before t. Then comparison is **admission from a paid cache**, and its prebuild/refresh, inspected cells/IDs and staleness must be charged. Building three depth2 cells costs three builds/six IDs, even if two are finally admitted. A cache miss cannot be filled for free. Identical per-query cell reads alone do not establish equal total retrieval cost.

**Matched control:** for cached admission use the identical frozen all-cell cache and paid read budget, latest seeds versus greedy unique yield. For on-demand routing use identical channels, number/depth of executed calls and lawful pre-call inputs. Record quality after actual-size matching; duplicate concentration may contain the relevant items, so larger unique yield is not purchase gain. Full learned CAPTS remains deferred because watch-time signals and a channel stack are absent.

## Common acceptance boundary

The native P140/R20/source60 versus original global ranks141–200 is correctly paired and no-refill. Stable interleaved prefixes at `m_q=min(actual sizes)` give equal counts and are valid **diagnostics**; they can trim common P/R items differently and therefore do not isolate a source effect alone. Preserve native results, per-source retained counts, source overlaps and both gained/lost full-Y hits. Freeze interleave/ties before labels. Preserve eligibility48h, daily00UTC, bottom-hash≤2000 beforeY, full target horizon and empty mature queries; a new mechanism gets no new query selection rule.

RB honestly says global build ceilings are unfinished. That is a correct reason to keep actual pilots deferred, not an adequate execution contract. Each proposal needs finite scan/state/build/lookup/output and failure bounds plus available_at/versioned cache/prior identity; literal fixture success establishes only semantic separation. After dedup, RB1/RB3 are refinements, RB2/RA02 is one new family, and RB4 can survive only after its information/cost contract is repaired. No quality or causal lift is established.
