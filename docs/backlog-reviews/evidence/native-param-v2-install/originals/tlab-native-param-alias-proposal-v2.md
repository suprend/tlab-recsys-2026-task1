# Bayesian representation alias V2 — context-only repair proposal

The independent V1 review found a supported nested/list behavior change: both
old comparators reject captured[E]/[A] and [[E]]/[[A]] at the Bayesian path,
whereas V1 grants the new scalar alias below lists because old list recursion
retains the path. The real authenticated B spec has a scalar there; no actual
accepted-spec/CBM-pin runtime bypass was demonstrated. V1source/report/15PASS
results and the independent witness remain immutable.

V2 changes only eligibility for the newly introduced representation alias. A
private `_scalar_alias` context defaults true, propagates through dictionary
recursion, and becomes false beneath any list. The float branch consults that
flag only for its new alias. Existing path values, schema/type checks, abs1e-12
and learning_rate tolerance are unchanged. In particular, original learning
list and nested-list tolerance behavior is preserved. The Bayesian direct
scalar from the actual captured B remains the same observed canonical-float32
AND exact-ten-significant-digit alias; arbitrary same-bin/adjacentULP values
remain rejected. No general native serialization documentation claim is made.

Two immutable TMP proposal sources:
- Production `/tmp/tlab-heldout-predictions-bayesian-alias-proposal-v2.py`
  SHA437a054be9b7d47072c240b73b3b713ddef943cb3b04e96d88c8279b41f56af4.
- Independent oracle `/tmp/tlab-heldout-prediction-audit-bayesian-alias-proposal-v2.py`
  SHA3b378274041623ba37dcb5a53a115458f02af4f2665f10821875aaf099d3cf75.

One saved-only author process ran17methods: inherited15regressions plus two
focused controls. Actual original ASTs both RED→bothV2 GREEN at the complete
captured model and minimum direct scalar. List controls demonstrate originals
RED→V1 GREEN→V2 RED for one/two lists, Bayesian list field, and a list containing
a Bayesian dictionary. Learning list/nested-list observed representations stay
GREEN as originally; meaningful learning perturbation and unrelated list
floats stay RED. Reaped tool7de799 EXIT0; external fulltime-p .04wall,
.03user+.00sys rounded (conservative CPUupper.05); observedSELF CPU.041472,
peak27,885,568B before final receipt/exit. CPU30 hard fence/alarm60 and peak
assert512MiB; children0/nativeimports0/loads0/predict0/fit0/sourceDB-Y0.
Test `/tmp/test_tlab_native_parameter_alias_proposal_v2.py`
SHA3f743b878ca1a780743ed71182da4258278b8582316c57c0e1d7e4723f67c6ab. No additional author process is needed.

The original project e1b06…/c552…/fc50… hashes are freshly unchanged. Current
original28CODE, accepted source/core/parity, original failed018 outputs and
failed_unknown_cleanup/unknowntrue V6 receipt remain unchanged. The separate
one-native-LOAD diagnosis grant remains consumed. No new source replay, model
load, scoring, fit,439, target access or publication occurred. This is still a
proposal pending the SAME independent reviewer's narrow V2 recheck and Root
adoption/new caller pins; real015 remains CLOSED. Root separately allows the
reviewer's one focused saved-only process15CPU20wall512MiB,0native.
