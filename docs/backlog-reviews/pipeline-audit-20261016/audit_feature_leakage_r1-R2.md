# Crossed R2 — manual producer cleanup finding

**Verdict: CONFIRM peer P2 at `scripts/manual_features.py:390-399`, particularly394.** Frozen HEAD `c538de4097322715fccac494e2b2becc3279e8e1`; original paths relative to `/Users/mdpospelov/tlab-recsys-2026/`. Peer FIRST/pins/freeze and reviewed source hashes match. My FIRST remains unchanged.

The supported failure-audit contract is explicit in `docs/experiments/manual-features.md:54-56`; existing tests exercise early timeout and connection-open failure (`tests/test_manual_features.py:366-383`). No claim about incorrect existing feature values follows.

## Independent control-flow trace

1. Before connection assignment, `con=None` (`:287`). A registry/provenance timeout enters `except`, sets failed, re-raises (`:387-389`); finally skips close and writes the attempt report. A failed `duckdb.connect` similarly leaves `con=None`; after identification, report/run manifests are written. This matches current negative fixtures.
2. After open succeeds (`:357-360`), including a guard failure immediately after connection assignment, `con` is non-None. Any later stage/timeout error enters `except`, but a subsequent close error escapes `finally` before receipt writes (`:394` before`:397-399`). The primary exception no longer controls the outward exception. **Qualification:** normal Python chaining retains it in close-error `__context__`; it is not erased from a complete traceback, but the caught/top-level exception and structured child receipt are wrong/missing.
3. Successful body sets complete only in memory (`:386`). Close then raising produces no failed report/run manifest: the body `except` cannot catch its own finally. Exported F may already exist (`:378-384`). The attempt/identified directory is preserved; no deletion occurs, and existing identified output is refused on another invocation (`:345-349`). Thus this is missing failure evidence, not persisted false acceptance or an automatic retry.
4. The enclosing development collection calls this exact runner (`development_collection.py:563-565`). Its `except BaseException` and finally persist outer failed report/state (`:571-582`) when their sinks work. That does not recreate the absent child report or restore the primary error. The typed-program producer instead calls `create_manual_features` directly (`feature_program_collection.py:427-428`); do not attribute this runner bug to that distinct route.

## Scope qualification / related runners

One Python `close()` fault with a healthy report destination suffices; disk-full, failed JSON sink, process kill or other compound OS failures are unnecessary to demonstrate the defect. Static inspection establishes the branch, **not** how often real DuckDB close raises. Errors before attempt-directory creation, and failure of the receipt sink itself, remain separate limitations.

Limited search plus surrounding-source inspection found the same unguarded close-before-receipt pattern in `anchor_pilot.py:361-367`, `candidate_pilot.py:264-269`, `heuristic_baselines.py:359-369`. These are propagation candidates for one cleanup fix/review, not independently runtime-reproduced incidents. `feature_program_collection.py:267-269` is a verification helper with no child receipt at that boundary. The metadata runner already captures cleanup errors and continues receipt persistence (`metadata_price_features.py:505-551`); its behavior is useful comparison, not proof of every sink failure being handled.

## Proposed bounded CODE check — UNRUN

After a separate Root grant, extend the existing sealed tiny `ManualRunnerTests` route, patching connection creation **after fixture setup**. A forwarding proxy delegates actual SQL/interrupt methods; its close first closes the real toy connection, then raises a unique OSError. Run: successful body+close fault; actual compiler completion followed by unique primary TimeoutError+close fault; early preconnection timeout as control. Preserve literal originals and record the exact caught exception identity, chained/recorded cleanup cause, directory contents and readable report.

Accept repair only if both close-fault cases persist failed child receipt, never complete acceptance; primary timeout remains the outward primary when present; both causes are recorded and resources closed. Reject on missing/stale receipt, lost primary identity or automatic retry. All project imports/tests/SQL/native/data execution remain UNRUN; only frozen text and stdlib hash/report packaging occurred. Freeze/readback then STOP.
