# SOURCE review — ranking-parity repair

**Qualified SOURCE PASS; no supported defect found in this four-file repair.** Frozen manifest SHA256 `fd56691c289dd06ebd8db74860a3e84ec342382dc01717c1d79795ae536fce59`. This closes the inspected parity-predicate gap at source level; it does not establish runtime/native serialization or historical output correctness.

## Production and oracle wiring

`repository/scripts/strong_baseline.py:312–324` retains tree count, exact vector shape, finiteness and `rtol=0,atol=1e-12`, then compares actual complete `train_baselines.rankings` results. Worker line 404 calls that helper as the real rank stage before metric evaluation (406) and NPZ save (407). All queries and all candidate positions participate, including empty targets and positions after 20. Numeric differences within tolerance remain legal when ordering stays equal.

Each oracle owns its own local `ranking_order` and `score_parity` (`strong_output_audit.py:18–26`; `strong_recovery_audit.py:19–27`). These compare the complete lexicographic permutation for the same group/item keys. The oracle does not import production ranking/metric helpers. `scored` reuses the oracle-local order and still truncates only for metric calculation; parity itself never truncates.

Actual successful-prefix calls use `score_parity(pred,pp,g,it,...)` at output oracle line 322 / recovery line 404. Failed-arm partial-prefix calls use `score_parity(score,replay,g,it,...)` at 306 / 388. Actual NPZ methods call the same oracle-local predicate at 245 / 324 after existing exact field/key/integer-dtype checks. Numerical and ranking requirements therefore apply both to reloaded prefix scores and saved vectors. Metadata hashes remain separate checks.

## Meaning of the eight proposed regressions

The new test file compiles extracted actual definitions, the actual worker rank-stage assignment, both actual oracle successful/partial acceptance expressions and the actual NPZ methods. It does not merely substitute a new guard and test that substitute. Extraction excludes controllers, imports and native prediction callbacks; explicit imports of CatBoost/DuckDB fail in the test seam.

Cases materially distinguish the intended contract: the no-tie `[5e-13,0]→[0,5e-13]` swap; legal tolerance with unchanged order; changes confined to nonpositive queries; positions21/22; NPZ-only rank corruption; wrong shape/nonfinite/over-tolerance/tree count; empty/singleton and exact item-ID ties. The explicit wiring method checks the two required oracle calls as well. Some checks encode source structure, but behavioral literal fixtures supply independent expectations. They are meaningful native-free regressions of the defect, not quality tests.

Limit: extracted statements demonstrate predicates and arguments when run; they cannot establish full controller reachability, actual native loads or a physical CBM roundtrip. No claim of eight passed tests is made.

## Integration and verification boundary

Verified all four output hashes/byte counts, four diff hashes, three base copies against the frozen originals, exact reconstruction of the three existing-file diffs, declared input pins, and manifest/handoff/freeze bindings. Four outputs were parsed as syntax only. Producer SHA is `209f03d114aed5fa93bf860b40cabdd69f5040ae7a81e45c0788ae590ebd03c6`.

The public recipe source pin still needs explicit integration/review. Concurrent `numeric_feature_names` changes are outside this repair: tests extract the actual candidate `rankings`/`QueryRanking` definitions without an old whole-file hash assertion, but combined source closure and bounded CODE remain pending. Inspected source helper/metric definitions are the frozen pinned versions; no newer combined bytes are approved here.

Executed only source reads/searches, stdlib AST parsing, textual diff reconstruction, hashing/JSON and readback. No tests, project-function execution/imports, native/model/data reads, SQL, predictions or fits; canonical/Git files and own FIRST/R2 remain unchanged. STOP.
