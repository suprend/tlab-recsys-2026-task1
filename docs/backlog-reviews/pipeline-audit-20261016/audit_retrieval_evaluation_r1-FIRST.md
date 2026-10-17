# Independent FIRST — retrieval, evaluation, cost

Frozen current-file audit: HEAD `c538de4097322715fccac494e2b2becc3279e8e1`; manifest SHA256 `7e2e871f148beac5b9fce3aa23970b370db0c8fdc9eac89958fb6342a4d2a41a`. Original paths below are relative to `/Users/mdpospelov/tlab-recsys-2026/`. Exact file hashes and partial-read boundaries are in the companion pins file. This is one axis, not coverage of all 632 files.

## Confirmed defects

**None supported in the inspected retrieval/evaluator path.** This does not establish runtime correctness, source reconstruction, absence of all leakage, or quality of a future retrieval source. Existing corrected proposals are not reported again as new defects.

## Scope and static witnesses

Read complete `scripts/{candidate_pilot,heuristic_baselines,ranking_metrics,protocol_manifest,temporal_contract,itemcf_extraction,itemcf_projection,heldout_evaluation}.py`; `anchor_pilot.py:142–277`, `model_data.py:87–198`, `train_baselines.py:322–340` plus relevant caller searches. Read all 12 candidate-generation notes, their index and three grouped reviews; target-research `{index,03-candidates,05-evaluation}`; candidate/heuristic/strong experiment notes, task1 requirements, protocol48h/7d/selection configs, selected backlog/index passages, and published aggregate excerpts. Instruction/dispatch inputs are separately pinned. No other current FIRST or independent083 draft was read.

**Full Y is retained.** `anchor_pilot.py:227–234` builds binary purchases from Q/time, independently of C. `candidate_pilot.py:61–95` reads past events/Q only; `:110–123` checks C⊆strict-past U; `:140–164` left-joins C onto full labels. `heuristic_baselines.py:131–152` retains every Q and all targets; `:190–193` slices original top20 hits rather than reranking a reduced label set. `model_data.py:143–153` keeps full targets apart from candidate-row labels. `train_baselines.py:330–335` passes those targets to the evaluator. Heldout `:89–105,115–121` likewise builds independent full Y before evaluation.

`ranking_metrics.py:117–133` uses |Y| for Recall/AP and min(K,|Y|) for IDCG. Empty mature Y is undefined per-query, censored Y remains None; `:144–191` separately aggregates four estimands. Bootstrap `:230–247` pairs user multiplicities and recomputes the requested query/user ratio. I found no macro/micro substitution in these inspected computations.

## Evidence deficits and existing limitations

1. **Stage losses are only partly observable in published aggregates.** Selection007 aggregate `:17–22` gives Y=96, U-supported=96, C-supported=65: 0 catalog misses and 31 retrieval misses. For its recent heuristic, `:165–179` gives 53 top20 hits, hence another 12 ranking misses; target-micro new/repeat hits are 3/38 and 50/58. New-pair means no previous event of that pair, not catalog-cold (`anchor_pilot.py:241–253`). All selection targets being catalog-seen is weak coverage for cold behavior, not evidence cold misses cannot occur.

2. Selected W/R2 aggregate line1 gives **query-macro** Recall .5919765166340509; candidate query-macro ceiling is .684931506849315. The .092955 difference is a same-estimand Recall gap. Subtracting .591977 from micro65/96 or converting it into a target count would be invalid. Candidate Recall is also not an NDCG ceiling. The inspected W aggregate does not publish W top20 micro hits or new/repeat stage decomposition. `real015-heldout-aggregate.json:45–67,82` publishes final metrics/fullY total, not the per-period U→C→top20 diagnosis. Heldout core `:109–124` has C/target support but no cold/repeat provenance. This is a diagnostic/reporting gap, **not a demonstrated wrong metric**; saved private artifacts may permit a separate audit.

3. **Equal-size and equal-work claims remain unexecuted.** HYP-004 is explicitly blocked for popularity220: protocol `:118–124` caps popularity at200; accepted union/no-refill is not that experiment (`backlog.md:284`, candidate-pilot note`:58`). HYP-053 replaces global ranks141–200 with category slots; no-refill underfill and source overlap can change actual |C|. Its size-matched curve requires a predeclared order, retaining the native-policy result (`04-category-brand-price.md:19,35,42`). Matched |C| controls scoring/output size, not category-state or graph-build work.

4. HYP-061 needs a new refill-control and a declared meaning of “outside original union”: original200+20 versus reduced150+20 are different pools (`review-05-08.md:9`). HYP-062 changes activity-weighted graph scores, not pair enumeration cost. K100/top50/cap220 do not bound Σᵥmᵥ(mᵥ−1)/2 construction (`05-itemcf.md:33–35`). Actual extraction `:90–94,115–117` explicitly limits descriptors/Python work, with native supervision external; projection merge visits `:86–99` concern requested fixed-C pairs. **TLAB-012/HYP-001 fixed-C features are distinct from retrieval061/062** (`backlog.md:256,280`). HYP-012 is a separate semantic/blinded/grammar design (`:319`). No retrieval build speed or quality follows from the fixed-C440000-pair bound.

## Quality hypotheses — existing IDs only

**HYP-053 refinement:** category allocation may recover supported new pairs missed by global head. Counter: displaced global hits, underfill, or selection noise explain the apparent gain. Nearest experiment: one prospectively fixed category configuration against unchanged no-refill C₀; report gained/lost full-Y targets, both micro and macro, native/matched-size curves, then downstream frozen-scorer NDCG. It informs a potential alternative Task1 pipeline, not feature-automation superiority. CPU/label budget **UNKNOWN/CLOSED**; old proposed30min/6GB is not a grant. Reused selection is exploratory; opened25–31 is not fresh confirmation.

**HYP-061/062 refinement:** weighted ItemCF may add different new-pair support; counter: head removal/truncation alone changes apparent gain. First a single authorized snapshot must measure exact graph construction and source support before a fair refill comparison. Keep source grain, K, support threshold, self-policy, allocation and full Y fixed; change weighting alone. Construction cost **UNKNOWN**, scientific allowance **CLOSED**. No new hypothesis ID warranted.

## Most discriminating independent check

If separately authorized, independently reconstruct U→C→top20 integer counts and new/repeat partitions for the already frozen B/W predictions, then reconcile each full-Y query metric and the published aggregate. Accept only exact counts/key coverage and numeric agreement; any missing target, oracle insertion, partition mismatch, or macro-as-micro conversion rejects the report. This needs no fit and grants none; real-data/CPU allowance remains UNKNOWN. A tiny hand fixture with Y₁={a}, C₁=[a], Y₂={b,c,d}, U₂={b,c}, C₂=[b] must yield candidate micro1/2, positive-query macro2/3 and q₂ NDCG@3≈.469279; add empty/censored queries without changing conditional denominators.

**Verification actually executed:** static source/document reads and SHA256/readback only. No tests, project imports, SQL execution, native/ML calls, raw DB/Parquet/model reads, or real data analyses. STOP after FIRST freeze.
