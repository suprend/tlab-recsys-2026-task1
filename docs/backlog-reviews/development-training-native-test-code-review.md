# Independent native integration-test source review V1

No supported P1/P2 finding in this candidate. Review is CODE-only; native compatibility, feasibility and execution success remain unobserved.

The new module's default discovery path imports only os/unittest; the opt-in decorator skips the case before native/helper imports (`/tmp/tlab-development-training-native-test-v1.py:2–30`). Checkout-relative imports and the documented locked-venv/PYTHONPATH invocation avoid embedded private source paths.

The opted case uses the actual helper, exact native classifier, existing callback/accounting and actual selector. Fit/selector spies call their captured real implementations, prohibit a second call and check the weights, callback-only fit kwargs, full ceiling and validation identity (lines66–92). They are not fake replacements for training or selection. Full/selected identity, full8 retention and selected shrink-to1 are checked.

The independent oracle reconstructs integer-item tie ordering, DCG, full-target IDCG and the three-positive-query denominator without production metric/layout helpers (lines103–135). It includes retrieved+off-C, off-C-only and empty-C positives. Every prefix is compared, then earliest-in-global-band selection is derived independently. Identical validation rows intentionally make the curve flat: this exercises ties and real shrink, not a non-flat late maximum or model quality.

Source accounting is complete for the stated public operations: at most one fit, one staged iterator/eight checkpoints, eleven direct predictions, one disk save and one disk load. Pool, native imports, model copy/shrink and cleanup are additionally paid work. Selected/prefix/reloaded/full-retention raw-score parity is checked. Patches restore on Python failures; TemporaryDirectory cleans its CBM on Python context exit. This does not claim kill-proof cleanup, native failure injection or automatic retries.

The45CPU/60wall body guard starts before native imports and remains cooperative. The proposed60CPU/90wall/1GiB whole-process allocation requires separately issued external supervision; no hard native/RSS containment or budget grant is inferred. Unknown6CPUh and closed allowances are unchanged.

All requested raw inputs were copied before analysis. Twelve source/metadata snapshot and current-original pins matched; AST/source inspection only, no candidate imports/execution/tests/fixtures/native/data/model/Y/job/helper/network/Git/project writes or publisher contact. This is neither CLI/CV/quality confirmation nor runtime authority.
