# Wave069 C: zero new ideas; refinement of 018/019 within 014

Verified shared-context SHA and all26 snapshot hashes. Actual trainer/helper/baseline hashes match frozen copies; the builder currently proves source plus two plans only.

**Mechanism.** Actual `main` parses flags, then `run` uses original `load_runtime`, collection-lineage verification, real preparation, exact native classifier, helper and selector. FakeML tests replace loader/data/class/selector; DevelopmentRuntimeTests monkeypatch ROOT and simulate approvals. Neither establishes ordinary native CLI.

**Concrete route/gap.** Copied `scripts` has no `__init__.py`. [`-I`](https://docs.python.org/3.12/using/cmdline.html) excludes cwd/script directory; prepending the copy alone still permits a later regular `scripts` package to shadow its namespace (local CPython PathFinder1496–1522). A minimal future `-I -B` launcher inserts the physical project, rejects non-copy `scripts` spec/path or `scripts.*` `__file__`/ROOT, then `runpy.run_module('scripts.train_development',run_name='__main__',alter_sys=True)` with real arguments. Leave modules unchanged; shadowing stops before fit. [Import semantics](https://docs.python.org/3.12/reference/import.html).

**Observer.** Capture original `CatBoostClassifier.fit`; wrap only that method with entry/return counters and `return original(self,*args,**kwargs)`, preserving arguments, return and exceptions; restore finally. Native class identity survives the helper's exact-type guard. Count entry means attempt, not completion; original return plus full tree_count8 establishes completion. This observes native work; replacing runtime/helper/selector/results would not.

**Counterhypothesis/prediction.** Self-reported success hides extra fitting or wrong modules. Predict one original-method entry/return, unchanged copied provenance, full8, eight real selector points, independently correct selection and serialization.

**Minimum experiment — UNRUN.** After actual Q/Y/C/F reviews, genuine acceptances and adopted verifier, issue one supervised CLI fit≤8trees. Independently stage all eight full-model prefixes; use literal fullY and manual-F's D/2 oracle, including empty-C positive Q; verify earliest global1e-12-band tree, all3 retained Q and three-row selected/full/reloaded scores and rankings. Callback-abort stays separately UNRUN.

**Budget/decision.** Actual costs and remaining allowance unknown; prior native grant CLOSED. Existing20CPU/45wall proposal requires a new explicit grant, no retry. Accept only complete matching evidence and reaped exit; reject mismatch or provenance substitution. No new IDs/gates/grants. Task1 benefit: closes ordinary-path engineering uncertainty; establishes no quality superiority.
