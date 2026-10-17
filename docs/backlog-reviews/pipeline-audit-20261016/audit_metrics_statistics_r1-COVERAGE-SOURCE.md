# COVERAGE-SOURCE — second independent review

Reviewed the exact two additive candidates and patch under `/tmp/tlab-audit-coverage-regressions-v1`; candidate hashes, handoff/manifest/freeze and dependency scope are pinned. Frozen production baseline remains c538de4097. Both candidate ASTs parse; one test method per file. **Suitable ordinary synthetic CODE additions, with one narrow test-coverage correction below. No production defect established.**

## P3 — Assert B44 projection dtypes inside the all8 loop

New target `tests/test_feature_programs_all_bundles_rich.py:329–335` checks projected values/keys using `np.testing.assert_array_equal`, without the explicit dtype checks used for B41 at287–289. Value equality alone does not enforce float32/int32/int64. Static mutation witness, UNRUN: leave the base branch correct but return a B44 matrix converted from float32 to float64; exactly preserved values/NaNs still satisfy these equality assertions although the claimed B44 typed contract is violated. Add assertions on every projected `x.dtype`, `group.dtype`, `items.dtype` (and preferably44-column shape/calendar) or use strict dtype-aware comparisons. This is a defect in the new regression's claimed coverage, not evidence that today's loader returns wrong types.

## Independent gold and fixture adequacy

`test_source_import_independent_order.py:43–88,109–155` spells out all nine fields, types, nullable vocabulary, canonical quoted UTF-8 CSV bytes, physical DESCRIBE order and explicit SELECT independently. It never constructs expected order from producer FIELDS/TYPES/SCHEMA. Three distinct integer/string sentinels, exact >2^60 IDs, comma/quote/newline, Unicode, empty NULL and literal "NULL" distinguish swaps and parsing damage. Hardcoded bytes independently check the input writer too. Current importer contract accepts signed IDs/negative decimal and has the asserted output paths/metadata.

All8 uses local B45 ordinal/type literals, local bundle semantics/insertion rules, independent raw-row/set calculations and first-row gold (`test_feature_programs_all_bundles_rich.py:23–240,267–335`). Manual derivation agrees: L03 ITEM has5 views/4 carts/2 purchases in168h; L05 distinct viewer/cart/purchaser counts2/2/1; L08 OLD cart age777600 seconds. Thus purchase→cart substitution is discriminating, and duplicate/NULL/lower-bound/off-source/peer/future cases carry signal. Actual compiler/generator and label-free loader execute in the proposed bodies; fixed Q/C intentionally do not prove retrieval lineage.

Category values are independently inferred from handwritten HISTORY, never copied from actual F. However B45 metadata gold is algorithmic, unlike the literal all8 first-row gold. Optional hard gold can pin A/ITEM→100, A/OTHER→200, A/COLD→NULL, B/ITEM→100, B/OLD→200, with ambiguity false and only COLD missing. Current fixture does not exercise a latest-second category conflict; existing category tests remain separate. B41/B44 expected arrays independently preserve NULL→NaN, ordered keyed values and empty-C query retention; dtype caveat above remains.

## Integration verification still required

After combining candidates: freeze/hash the final complete isolated checkout and patch; re-review any changed producer/config dependency against the literals and verify additive test-path ownership. Run exactly the two named methods under a separately issued one-child budget, preserving failures and measuring startup/import/cleanup. Recheck final typed dtypes, full schema order, both history variants, all8 appended matrices and source canonical bytes. Neither candidate patches compiler/loader semantics; blocking CatBoost/tsfresh is a capability guard. Their synthetic DuckDB calls are ordinary CODE, not CatBoost native/fit/callback/E2E evidence. Avoid broad discovery, which includes existing unconditional native tests.

Static text/AST/hash/readback only. No project imports, tests, SQL, model/native operations or real-data execution here. Runtime/resource cost and mutant outcomes remain UNRUN/UNKNOWN. Previous FIRST/R2 unchanged. Freeze/readback; STOP.
