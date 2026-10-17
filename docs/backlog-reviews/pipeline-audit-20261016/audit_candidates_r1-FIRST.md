# Candidate generator: independent FIRST

Frozen HEAD `c538de4097322715fccac494e2b2becc3279e8e1`; current-file audit, no diff baseline. Manifest SHA-256 `7e2e871f148beac5b9fce3aa23970b370db0c8fdc9eac89958fb6342a4d2a41a`.

## Scope and call paths

Full inspection: `scripts/candidate_pilot.py`, `scripts/development_collection.py`, `scripts/protocol_manifest.py`, `scripts/temporal_contract.py`; `tests/test_candidate_pilot.py`, `tests/test_candidate_reachability.py`, `tests/test_development_collection.py`; both `configs/protocols/clock-{48h,7d}.json` and all three `configs/development/{train,selection,confirmation}.json`.

Context inspection: `scripts/anchor_pilot.py:1–294`, `scripts/manual_features.py:1–245,300–418`, `scripts/train_baselines.py:35–235`, `scripts/model_data.py:1–201`, `scripts/feature_programs.py:1–155`. Requirements/dedup: `docs/experiments/candidate-pilot.md`, `docs/candidate-generation/{01-exact-reference,02-popularity,03-recent-repeat}.md`; portions/searches of candidate-generation index/04, experiments anchor/manual/development, `docs/backlog.md`, `docs/research-lab/index.md`. Precise source pins and inspection depth are in the companion JSON. No peer FIRST or review conclusions were read.

Traced paths: `create_queries → create_labels → candidate.run → create_candidates → verify_catalog → coverage_report`; collection `prepare_execution_plan → verify_producer_approval → produce/_verify_run → candidate/feature lineage → aggregate_collection`; downstream `verify_collection → numeric_feature_names/prepare_model_data`, plus typed-program base schema.

## Confirmed actionable defects

**None supported in this inspected scope.** This does not establish runtime execution, complete artifact correctness or absence of every possible leak.

The inspected code supports these specific conclusions:

- Popularity is purchase `count(DISTINCT user_id)` with explicit non-NULL user/product filters, lower-inclusive/upper-exclusive window, then descending buyer count and ascending ID (`candidate_pilot.py:61–70`). Duplicate purchase rows do not add buyer votes. Recent groups by query/product before ordering by maximum event time and ID; NULL products are removed and bought products remain (`:72–78`).
- Union uses `bool_or` flags, source-specific minimum ranks, latest recent timestamp and full popularity-count join, including recent-only products (`:82–95`). It performs no refill; quota sum must equal `max_unique` after protocol/generator checks (`protocol_manifest.py:123–124`, `candidate_pilot.py:48–49`). Row/per-query caps are checked (`:100–106`). Empty sources remain empty.
- All retrieval reads exclude timestamp peers/future rows. Candidate generation does not reference Y; Q's maturity field is deterministic provenance validation, not an outcome-based sampler. Strict-past catalog verification is separate from Y (`:110–123`). Full labels join only after C exists; zero-C Q and unretreived/cold targets survive the left joins (`:140–164`).
- Q diagnostics use raw event rows for history length, distinct non-NULL products separately, and a fixed 7-day history regardless of 48h/7d eligibility (`anchor_pilot.py:160–175`). This distinction is intentional, including users whose only eligible event has NULL product.
- Candidate category uses the latest global strictly-past timestamp; known+NULL mixtures are ambiguous. Event-category aggregates retain historical category IDs; category denominators range over all matching events, beyond C (`manual_features.py:124–143,175–205`). Ages/coverage describe observation, not exposure, registration age or stock.
- Retrieval flags/ranks/full purchase-buyer counts, missingness/coverage/age context are available in the base model schema and preserved when adding bundles (`train_baselines.py:188–195`, `feature_programs.py:19–24,53–66,135–151`). This is shared context, not an extra feature-automation discovery.
- Collection source/config/registry/code fingerprints bind to approval and producer dependencies; candidate lineage binds exact independent Q/Y, feature lineage binds accepted Q/Y/C. Aggregation checks exact C↔F keys and unchanged retrieval columns (`development_collection.py:205–233,236–318,393–417`). The downstream collection consumer additionally binds actual source/registry/code/phase bodies and shard cover (`train_baselines.py:104–124`). I found no supported input-substitution path.

## Boundaries and existing limitations

No raw events, DuckDB/Parquet, models, credentials, ignored artifacts or moving checkout were read. Existing tests were read, never executed. No project imports, SQL, worker/native/ML calls or fitting were performed. Hash/readback checks concern source/report bytes only. Artifact acceptances and historical measured numbers were not independently replayed.

The v1 generator's small fixed C, finite observed history, ID tie-breaking and no-refill are documented choices, not correctness findings. `validate_queries` explicitly does not reconstruct the sampling proof (`candidate_pilot.py:25`). Mechanical collection checks explicitly leave independent semantic output acceptance external (`development_collection.py:239,418–419`). Declared calendar coverage cannot prove raw source completeness. Final/reused selection cannot become a new independent evaluation reservation.

## Quality hypotheses: existing IDs only

1. **HYP-004 refinement, no new ID:** the marginal benefit of recent20 may persist after matching actual unique C size. Mechanism: direct-history products add personally relevant targets beyond global demand. Counter: gains come only from extra candidates or overlap-induced size differences. Prediction: gained-minus-lost full-Y hits remain positive on size-matched Q comparisons, particularly repeat-pair targets. Nearest experiment: prospective, separately versioned popularity220 versus P200+R20, with fixed union/refill and matched-size policy; no ranker fits initially. v1's pop≤200 cannot run that comparison unchanged. Benefit to Task1: distinguish retrieval ceiling from feature/ranker limitations. Cost UNKNOWN; no execution grant.

2. **HYP-031 refinement, no new ID:** short-window demand can recover nonrepeat targets absent from stable 7d popularity. Counter: apparent gain is noise or generic freshness. Prediction: `170global+30trend+20recent` beats both frozen P200+R20 and `170global+30top1d+20recent` on gained-minus-lost full-Y targets under matched-size policy. Nearest experiment is the existing bounded retrieval-only design, prospectively frozen on an eligible new development reservation. Benefit: identify a cheap complementary source before changing Task1 feature automation. Cost UNKNOWN; no claimed gain or new gate.

## Most discriminating proposed independent check

A separately authorized tiny literal oracle combining actual `create_queries → create_candidates → create_manual_features` should contain: raw duplicate buyers, popularity and recency ties, product IDs 0/negative/NULL, NULL users, anchor/window-boundary events, full source overlap, empty popularity, and a latest category bucket mixing known+NULL. Compare exact Q/C tuples, flags/ranks/counts and category/masks to hand-written expected values; permute peers and append future/label rows. Acceptance: unchanged literal outputs and no Y access before materializing C/F, plus strict-past catalog membership. Rejection: any differing pair/provenance/category/mask or outcome-dependent Q/C/F. A separate collection mutation check should alter the pinned source path/body, registry or phase without renewing approval and require rejection before features. Proposed only; **no tests run**.
