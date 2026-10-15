# Independent heldout source audit core

This additive module computes an independent expected source result on a caller-owned private DuckDB connection. It has no CLI, filesystem reader/writer, execution claim, acceptance writer, target API, model loader, prediction or fit. Code review does not authorize a heldout run or grant a resource allowance.

## Interface and trust boundary

`tests.oracles.heldout_source_audit.audit_source(con, lock, authenticated_choice=..., days=..., load_day=..., check=...)` checks exactly the seven fixed UTC dates October25–31,2019. `audit_day(..., relations=...)` is useful for bounded tests or a future role adapter; its result alone cannot prove whole-period coverage. `load_day(con, day)` exposes four distinct safely named relations: `queries`, `candidates`, `base_features`, and `extra_features`; extras are `None` exactly when W=B. Day records use the accepted contract's eight fields and typed refs/counts. No ref is opened by this module.

The caller must authenticate lock/choice, source bytes, code and each output ref before calling; pure `heldout_contract.validate_lock` validates the supplied snapshot, not external approval. The caller supplies `heldout_raw_events` with TIMESTAMP event_time, VARCHAR event_type, BIGINT product_id/user_id/category_id. Additional source fields are ignored. Nullable integer keys remain native SQL/Python integers; pandas transport is absent. The connection must use two threads. The caller owns its memory/spill limits, persistent deadline/interrupt, CPU/RSS accounting, source read-only attachment and closing/finalization. `check` is a trusted resource callback, invoked around SQL and during bounded sample streaming; it must not run another query on the same active connection. Temporary `_hsa_` state is replaced on each day, with no whole-period B45/57-wide materialization.

This core does not authenticate immutable files or prove they stay unchanged after its return. A future role adapter must pin/repin output bytes, preserve failed markers, exclusively consume execution before paid work, and obtain a full-lifetime parent receipt and independent source acceptance. The owner/worker contract describes those future seams; they are not implemented here.

## Independent formulas and exhaustive scope

Expected Q/C are reconstructed **before** using any supplied feature domain. Expected values do not call producer query/candidate helpers, its compiler, generated schema or an AST evaluator. The only imported production component is the pure heldout policy/authority validator. Schemas, names and selected formulas are independently spelled out and checked against the authenticated B41/W feature order.

For each anchor the raw prefix is `[October1,t)`. Q eligibility counts raw view/cart/purchase events in inclusive-lower48h, retains eligible NULL-product users, and applies bottom-SHA2026 user sampling before labels. All Q10 fields are checked, including raw7d history diagnostics, exact distinct nonNULL products, UTC active days and calendar-only maturity. Maturity relies on declared archive completeness; observed extrema cannot establish it. Candidate popularity is distinct nonNULL purchase users7d, globally sorted count-descending/product-ascending top200. Recent products use each expected user's three actions7d, max time descending/product ascending top20. The deduplicated union has no refill; repeated bought items remain. All eight C fields, strict-past catalog existence and every keyed row are compared with multiset equality.

Domains follow expected Q/C: all Q users, including emptyC, distinct C items and Q-user/item pairs. B45 retains exact C identities plus Q-user/anchor. Every row's global latest-timestamp category bucket includes every peer/NULL/duplicate across users. One known category without NULL is clean; mixed/competing buckets are missing and ambiguous, without older backoff. History presence, observed ages and declared24/168h coverage are exhaustive. Other core18 fields receive exhaustive type/range/finite/NULL/missing-mask checks.

Only the chosen branch is evaluated and broadcast onto every C row: I1 raw pair action counts24h; I2 full-prefix pair-cart recency/mask plus raw item-cart count24h; R1 raw user action counts24h, including NULL product; R2 exact distinct nonNULL action users24/168/24h per item. Observed empty counts equal zero. Recency uses integer microseconds divided by one million. Integer/boolean/NULL comparisons are exact, selected recency absolute tolerance1e−9 seconds, B double comparisons use absolute/relative1e−12. W=B computes no extra relation or values. Historical purchases on October25 may lawfully influence October26; events at or after the current anchor cannot influence its result.

## Sampled core18 proof and evidence

Each date samples up to four bottom-hash expected pairs, plus up to one pair for each source-derived stratum: pair-view7d support, missing category, ambiguous category, pair-purchase7d support and pair-view/purchase recency older than7d. The deduplicated union has at most nine pairs/day. Available and selected counts are emitted per stratum. Independent streamed raw-row arithmetic and source scalar queries compare all18 core values for these pairs, with category counters using historical event categories and global denominators outside C. Samples are selected from raw support, not supplied feature values.

Evidence contains aggregate day/whole-domain counts, exact supplied output inventory, chosen scalar count, sampled pair/comparison counts and explicit `baseline_formula_values_complete=False`. Status is `source_core_checked_pending_external_acceptance`; it is not an external seal. Chosen0/3 formulas and source Q/C/domain/metadata coverage are exhaustive; no field claims all B18 source formulas were proven. No user/product IDs or raw rows are returned in evidence. The tiny negative control deliberately shows a structurally legal unsampled B18 corruption can pass this sampled boundary.

## Synthetic verification and remaining limits

Run only the public synthetic tests:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -W error::ResourceWarning -m unittest tests.test_heldout_source_audit -v
```

The largest raw fixture has21 events. Actual fixture outputs are generated by the accepted producer; expected audit formulas remain independent, with literal gold and producer-helper poisoning checks. Tests cover all five choices, raw repeats, NULL distinct counting, exact BIGINT beyond2^53,48/24h boundaries, full-prefix recency, global metadata peers/category move, off-C category denominator, legal25→26 history, future suffix, all-seven/empty partitions, eligible emptyC, jointQ/C/F omission with updated refs/counts, legal chosen corruption, sampled B18 corruption, duplicate rows, schema/mask faults, no file IO and callback aborts. A separate201-row **preaggregated count-only** ordering fixture checks top200/top20 tie order and overlap/no-refill. It does not prove full raw-source saturation or bottom2000 selection at scale.

First draft test setup lacked PYTHONPATH; a later draft exposed a wrong test patch module and an invalid two-column UPDATE subquery. These failed runs are preserved in temporary audit logs; corrected fixture commands/tests passed. Initial source smoke also exposed DuckDB's refusal of prepared parameters in CREATE VIEW; raw prefix now uses internally validated fixed datetime literals, with no raw source materialization. No actual raw/private package/model/Y input was opened. Runtime sufficiency and full-scale cost remain unmeasured; source download, bootstrap/regeneration, heldout owner execution and target/prediction verification are separate work.
