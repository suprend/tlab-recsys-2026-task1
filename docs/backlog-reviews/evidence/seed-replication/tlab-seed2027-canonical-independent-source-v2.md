# Independent canonical proposal V2 targeted SOURCE re-review

Verdict: **qualified SOURCE PASS for the V1 P2 correction and documentation changes; no supported new finding in this targeted scope.** The V1 finding/report remains preserved. This is neither installed-suite verification nor actual run/output acceptance.

## Fix assessment

Read the actual V2 tests and exact V1→V2 test/document diffs, V2 integration note, harness, receipt, summary, original stderr/stdout and source readback. `tests/test_replicate_frozen_seed.py:100-112` now compares `set(sys.modules)` before/after the Fake pair and filters new module names by root `catboost`/`duckdb`, including submodules. It no longer fails merely because unrelated discovery already loaded a backend. This closes the confirmed V1 P2.

The new regression at `113-122` preloads a synthetic `duckdb` ModuleType, runs the same Fake pair, accepts no new backend modules, then inserts a distinct synthetic DuckDB submodule and requires the same assertion to fail. Context-managed dictionary patches restore pre-existing module state. This targets both halves of the isolation rule without loading a real backend. The rule proves no newly appearing backend module names during this operation; it is not a universal detector of attempted imports of already cached modules or native work. No broader claim is needed.

All fifteen previous methods remain; only the narrow assertion changed and one regression was added. A separate read-only helper independently examined the actual changed lines and documentation and found the P2 closed with no new issue. No test or harness was executed by this reviewer.

## Documentation assessment

`docs/experiments/seed-replication.md:7` now distinguishes historical Mac/M3 execution from source-only assessed/unconfirmed Linux execution, closing the V1 evidence qualification. Line42 correctly identifies matched-k300/600/1200 as NDCG@20-only and explicitly says matched-k Recall is not computed; this matches unchanged caller curve storage. Line50 describes16 Fake scenarios, newly added backend module checks and the preloaded synthetic sentinel regression. Historical d35cfb6 input scope, reused-development interpretation, absent native/quality/resource claims remain intact.

## Recorded synthetic evidence and freshness

Read the actual original log:16 named methods report `ok`, `Ran 16 tests`, `OK`. `FAKE-SUMMARY.json` records16 discovered/run, zero failures/errors/skips, empty final backend set and enabled backend import blocker. The proposal-only harness installs that blocker before discovery and exits nonzero on failure, unexpected final backend modules or wrong method count. `TEST-RECEIPT.json` preserves original exit0, no retry/timeout, measured0.446401s wall,0.233272s child CPU and0.057560s supervisor CPU. These are inspected reported synthetic results, not an independent rerun or full-project discovery/native verification.

Fresh byte checks in `/tmp/tlab-seed2027-canonical-independent-source-v2-pins.json` show:

- All eleven V2 manifest file entries match.
- V1's six entries and manifest remain unchanged; prior manifest SHA256 is still `7b46fe5bf3119f104c5bd75ebe52d0bc3b899824a2d2521c21d68d647adf8a40`.
- Caller and builder are byte-identical V1/V2: caller `bb2fe7c9bbfbb9c3e1c71c352108f0fd6426eb90fa4da94096ba22f61261296c`, builder `2038a9b1fba537f9a30b617381b5234bcf70f9b322a634af410f0a40d942f6dd`.
- Active private frozen caller and request-v2 hashes remain the reviewed `bb2fe7…296c` and `bf196214c206d99c1cfd18cc2d42036da7fd0343c8c4ed3ff3788b843075a5d1`.

Only the two requested review artifacts were written. No target imports/execution, tests, backend/native/SQL calls, real input/model/export/report bodies, network, Git, canonical writes or runtime/session18199 access occurred. Hashing the permitted frozen source/request files does not inspect or alter runtime state. Existing caller/builder review conclusions carry forward through exact byte equality; this re-review adds no execution claim or new gate.

Stopped after final fresh byte/readback check.
