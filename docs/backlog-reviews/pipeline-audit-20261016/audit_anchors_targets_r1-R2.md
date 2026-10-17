# R2 — crossed challenge of leakage redteam

**Verdict: retain the peer’s scoped no-confirmed-leakage result; add two claim/test refinements, no new P0–P3 finding.** Peer FIRST SHA256 `6a5de244b0c08ddf551de40c4b71e9fe1e21e417a6a05aed4e741de23a0e56d5` and pins match its freeze. My FIRST remains unchanged. Frozen HEAD `c538de4097322715fccac494e2b2becc3279e8e1`.

## Exact additional scope

Read peer FIRST/pins/freeze; static caller ranges: reproduce_frozen_comparison125–172,205–478,520–705; heldout_reporting_worker1–333; run_heldout_reporting128–194; feature_program_control73–131; heldout_predictions1–182; model_data85–200; heldout_evaluation108–162; development_training22–91; train_development151–220; ranking_metrics114–134; source_import16–30; manual_features124–144; train_baselines188–195; targeted recipe and caller indexes. Supporting temporal/anchor/compiler/heldout policy evidence inherits my frozen FIRST scope. R2 pins distinguish these ranges from whole-file coverage.

## Challenges resolved

1. **Generic helpers do not authenticate clocks or training provenance.** `heldout_predictions.verify_model` checks actual loaded300 trees, exact feature order, numeric channels and effective parameters (68–83); a future-trained model with identical metadata could satisfy this helper. That is not a production counterexample: worker `load_model` requires the model’s original retained hash before load (heldout_reporting_worker172–177), and `run_heldout_reporting.prepare_owner` obtains choice through the fixed external acceptance consumer (154–173). That consumer checks the hard-coded acceptance digest, model/output/observer closure and pinned winner (feature_program_control81–128). Thus native metadata is **not proof of fit cutoff**; the historical source/formula/clock claim rests on externally accepted provenance. This pass did not authenticate those actual artifacts. Keep the peer’s qualification explicit.

2. **Public reproduction cannot silently substitute arbitrary recipe/fit state.** Exact recipe hash is required (reproduce_frozen_comparison256–264), verified source snapshots are compiled (127–170), run builds fixed train/selection periods (650–672), and actual fresh models fit a train-only Pool and are saved/reloaded/rechecked (529–584). Full development exports may exist before fitting; physical read order alone is not temporal leakage because the Pool receives train x/y only. No selection-derived fitted transform was found on this numeric path.

3. **Same-second / metadata challenge fails under the stated event-time contract.** Counters use `<anchor` (manual_features141), and last-past metadata aggregation cannot consume a future clean category. The heldout source’s past-filtered view additionally limits the reused helpers. A late-arriving row with an earlier event_time remains an unresolvable witness: typed9 has no arrival timestamp (source_import19–20). This supports the peer’s documented-assumption classification, not a real-data no-leak proof.

4. **Off-C/fullY denominator challenge fails.** Public preparation builds full targets independently of feature rows (reproduce_frozen_comparison420–433). Heldout rankings pass the unfiltered full set (heldout_evaluation115–121), and recall/AP/idealDCG use its count (ranking_metrics117,131–133). Empty C with positive Y remains a miss.

## Refine the proposed independent check

Check actual callers, with fixed external authority: anchor/future suffixes and peer permutations must preserve earlier Q/C/F/x; off-C purchases must change fullY denominators without entering C. Add a different-weight model with identical native metadata: production must reject its hash before loading. **Changing validation outcomes may legitimately change selected prefix** (development_training77); demand invariance of train rows/Pool inputs, not the selected model. The ordinary helper also requires positive fullY validation before fit (57), so a zero-positive mutation should test its explicit rejection rather than assert universal fit continuation. All witnesses remain UNRUN/cost UNKNOWN.

No new quality hypothesis/ID/admission. No tests, project imports, SQL, native/ML, raw data, models or getters were executed/read. Static text/hash/readback only; actual arrival-clock and training-data provenance remain unverified. STOP after freeze/readback.
