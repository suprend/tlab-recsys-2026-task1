# R3 SOURCE review — empty verifier test contract

**PASS for SOURCE only; 0 actionable findings. Runtime UNRUN, cost UNKNOWN, pending Root's separately bounded CODE check.** Target `tests/test_verify_development.py` SHA256 `e7460ab01512f4e2b557b21cab4a9a34a842af80135fd9becc809bf1af98e85c`; candidate manifest SHA256 `a983e77affcb6d1532f975af67818af0a8450fea345278189c10438e98eb6c8f`. Reviewed against pinned combined-v1, not the moving canonical checkout.

## Independent verification of scope

I read the two changed methods, fixture construction/resume/approval code, the actual `run_phase` aggregation/failure/finalization path, and independent verifier lineage/schema/QYC/F/result paths. Independently hashed candidate, metadata and all supplied context pins. Reconstructed the complete unified diff from base/candidate bytes: exact match. AST comparison established **34 other methods unchanged**, precisely one obsolete method removed and two named methods added; prefix/suffix outside that replacement are byte-identical. No reliance on the author's acceptance statement.

## Failure contract retained

Candidate test lines318–341 patch the real `scripts.development_collection.aggregate_collection` symbol only during a fresh `self.build([])`. The same module object is used by `DevelopmentRuntimeTests.execute → run_phase` (`tests/test_development_collection.py:114–115,169–174`). Its first invocation produces real empty anchor/C shards and waits for approvals; its second produces real F and reaches the controlled aggregation fault. `aggregate.assert_called_once()` ensures that the injected seam was reached rather than an earlier incidental error.

The actual combined `scripts/development_collection.py:584–601` catches this exception, writes failed report/state and appends the attempt receipt in `finally`. The test checks failed state and constructs new pinned external expectations naming that actual failed attempt. It does not manufacture a failed producer JSON. Independent verifier `_lineage` first authenticates/read-binds state, plan and attempt (`scripts/verify_development.py:164–172`), then rejects their failed status at `:173–174`, before child opening/source SQL and before counts. The preserved assertions require `VerificationError`, exact `lineage.complete_attempt`, failed evidence and no counts. The old rejection contract remains; it now has a valid trigger independent of the repaired empty-day behavior.

## Positive empty contract / fields / imports

Candidate lines343–353 use real `build([]) → producer → approval → resume → verify`. `build:28–38` replaces the tiny source in an owned temporary fixture and regenerates its plan/producer pins. `build:39–53` obtains the real complete state/child closures and writes the same external expectation fixture used by existing tests. No coverage report or verifier result is fabricated.

All positive asserted result fields exist: initial `fits=0` (`verify_development.py:434`); counts, population, sample_pairs and formula_checks are published on success at `:491–493`; completed lineage/QYC/F markers appear at `:440,482,485`. Two one-day shards are fixed by fixture configuration, so the exact five completed markers match the actual control flow. All-empty populations correctly count zero existing queries rather than calling missing users negatives.

Physical schemas are checked unconditionally for **Q, Y, C and F before counts**, even when files contain zero rows (`:470–473`); `_schema:296–298` requires exact ordered names/types. Missing columns cannot silently pass via zero sampled F formulas. The new positive method does not directly mutate an empty schema, but success necessarily traverses these checks; existing schema-negative tests are unchanged.

The inspected import chain uses stdlib plus DuckDB and project temporal/source/ranking modules. It does not import CatBoost, training modules or fit paths. Existing setUp first builds the usual five-row fixture, and each new method then builds a second empty fixture; those operations must be included in Root's future limit. No source-completeness claim beyond the explicit synthetic interval follows.

No imports of project/source/native modules, tests, SQL, producer/runtime execution, real data/model reads, canonical writes or Git operations were performed. Only text, AST and SHA256 inspection. Frozen output readback follows; STOP.
