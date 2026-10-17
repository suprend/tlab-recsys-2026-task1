# Independent SOURCE review — rich coverage additions

**Accept the two frozen test sources for a separately supervised bounded CODE run; no confirmed P0–P3 defects found. Runtime acceptance is pending.** Scope: complete candidate patch/files, manifest, handoff, freeze and dependency-pin metadata; frozen compiler/generator/inference/importer contracts. No moving source or runtime artifacts were read. Candidate files are additive at absent target paths; a complete isolated checkout is required.

## Evidence from source

`tests/test_feature_programs_all_bundles_rich.py` has independently spelled B45 ordered names/types (`60–92`), all8 semantic tables (`102–129`), ordinal insertion rules (`153–168`), raw-row/set reference arithmetic (`171–244`) and literal first-row gold (`145–149`). Expected values never call production schema/expression/expected-value helpers. Generator/registry contents are actual inputs under test, not inputs to the expected-value interpreter.

I manually verified all first-row gold: L01=(4,2,3), L02=(3,1,1), L03=(5,4,2), L04=(1,2,2), L05=(2,2,1), L06=(18000,3,false), L07=(14400,2,false), L08=(18000,2,false). Duplicate raw views count twice; projected NULL products/users do not enter distinct sets. The168h purchase lower endpoint is included and its one-second-earlier peer excluded.24h boundaries, a pre-source cart, empty-C Q, cold item,9-day old cart, latest metadata and reversed global-peer/future suffix are present. L08 OLD recency777600 is correct (`321–322`).

The prior hypothetical L03 purchase→cart compiler mutant must fail: ITEM’s168h purchase count2 and cart count4 differ, checked against both independent interpreter and literal tuple (`313–320`). This is a static implication, not an executed mutation result.

Actual `inference.load_inference_data` is called for B41 (`283`) and all8 B44 projections (`326`), with only its path root patched. These are real label-free loader calls, not copied SQL expressions. Assertions bind Q including emptyC, int64 item IDs above2^60, int32 groups, float32 X, NaN values, B preservation, append order and suffix/permutation equality (`280–292,329–372`). Compiler output schema must equal independent F48 order; all45 prior fields must remain equal (`303–306`).

`tests/test_source_import_independent_order.py` independently fixes raw header/profile/types/nullable vocabulary and distinct numeric/string sentinels. Canonical all-quoted UTF8 expected bytes are literal (`79–89`), checked against actual importer stream and witness (`96–108`). Independent report schema, ordered DESCRIBE and explicit nine-column SELECT (`109–157`) prevent a coordinated production FIELDS/TYPES/order change from silently redefining the oracle. Commas, doubled quotes, newlines, Unicode, empty→NULL, literal NULL text, signed bigint and Decimal values are meaningfully distinct.

## Remaining boundaries

The fixture fixes Q/C and does not prove retrieval lineage, actual F57 acceptance, `program_model_data`, training/fullY composition, native ML/callback behavior, current data quality or model benefit. It uses whole-second timestamps and small single-chunk arrays. The B oracle is independent code with literal corroboration, not a universal proof. EmptyQ is covered elsewhere, not newly here. Both tests block CatBoost/tsfresh roots; top-level imports are stdlib only.

This review covers the pinned candidate and original dependencies, not other pending producer/helper fixes or their final combined behavior. The handoff correctly calls its45CPU/75wall/1GiB limits a proposal. **All proposed resource costs remain UNKNOWN; no run/grant/retry is issued here.**

Executed: source/line inspection, independent manual arithmetic, stdlib AST parse and SHA/readback. Not executed: project imports, test bodies, SQL, native/ML APIs, data/model reads, fits or predictions. Readback PASS; SOURCE review frozen; STOP.
