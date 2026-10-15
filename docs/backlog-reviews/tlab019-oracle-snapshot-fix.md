# 019 observer context snapshot correction

Final entry `tlab-verify019-outputs.py` SHA **03b9c22fec7a42f136cd0e6017767411fdb856dab1a1220eb613ee6d012ccaab**, ready for independent narrow review/publication. Reviewed18d45 retained byteexact as `tlab-verify019-outputs-18d45-reviewed.py` (18d45b266dd7666669dd1948eb926b38e613c0921f70daa18092c25a24924a0e).

The context parser now consumes exactly the `raw` byte snapshot whose hash matched the controller-issued digest. Shared `read_raw_json(raw)` preserves duplicate-key/nonfinite rejection and strict UTF-8; ordinary read(path) delegates to that parser. Observer.__init__ no longer opens the path again for interpretation. Later physical repinning remains a separate integrity check and cannot replace the immutable parsing guarantee.

Three deterministic checks PASS: patched context byte source would substitute allowance1→300 on a second read, while patched high-level read fails if called; constructor uses the single original verified snapshot and keeps allowance1. Wrong issuer hash rejects before parser invocation. Duplicate keys/NaN/Infinity still reject. Tests use only own temporary JSON/context and observer code; no actual source, SQL, Pool, model, prediction or fit. Syntax parsed. Evidence: `tlab019-oracle-snapshot-checks.py`, `tlab019-oracle-snapshot-results.json`.

The independently reported native18d45 saved-model compatibility probe remains evidence from its reviewer, not a new actual experiment by this agent. LR/portable checkout fixes are unchanged. Actual019 remains HOLD until independent final entry acceptance and public exact pins; no budgets or execution approvals are issued here.
