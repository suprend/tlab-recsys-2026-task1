# Independent NULL-oracle regression source review V1

The regression patch has no supported P1/P2. One P2 affects the separately supplied future runner.

**[P2] Persist timeout evidence before propagating it.** `/tmp/tlab-manual-oracle-null-check-once-v1.py:69–74` uses `subprocess.run(..., capture_output=True, timeout=20)` without a TimeoutExpired handler. A timeout raises before the arm-terminal receipt is written; captured child stdout/stderr are not persisted. This contradicts request line52's timeout-preservation promise and leaves the once-consumed attempt without its corresponding terminal receipt. Minimal repair: catch TimeoutExpired, write the arm's timeout/command/available stdout/stderr receipt, then re-raise the same primary exception; preserve that primary if receipt writing fails. No new controller, retry or scope expansion is needed. Normal unexpected return codes are already persisted before assertion.

Patch scope is exact: removing the added method restores original bytes; reversing the two None filters restores RED; existing methods and the new RED/GREEN method ASTs are unchanged. Production, registry and protocol pins remain unchanged. Both projected nullable IDs are supported by typed9 and SQL DISTINCT omits their NULL values while raw counts retain the rows.

Independent literal trace confirms all18 gold: four strict-past bag rows, user/item views3/3, non-NULL distinct1/1, pair2, recencies7200/1800, category counts3/4 and share0.75, user-category3/share1; cart/purchase counts0 and absent purchase recencyNone. Candidate category100 is known/unambiguous. The different-user event exactly at T tests global exclusion. Both implementations compare separately to gold via subTests.

Predicted RED is exactly two oracle failures2→1; predicted GREEN passes. Neither was executed. Runner correctly supplies canonical __file__/repository import context, selects only the new RED method, and loads precisely13 GREEN ManualFeaturesTests methods, excluding ManualRunnerTests. RED classification checks both oracle feature IDs and the2!=1 trace, without errors/skips/CatBoost imports. Declared hard child CPU10 precedes interpreter exec; wall timeout20 and observed-only RSS are distinct. Startup/tails remain separately paid.

Static source/SHA/AST only; no imports, tests, fixtures, native/SQL/data/model/network/jobs/helpers/Git/canonical writes or coordinator contact. Runtime remains unissued.
